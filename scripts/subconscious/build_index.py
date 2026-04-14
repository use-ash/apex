#!/usr/bin/env python3
"""Build the metacognition retrieval index.

Embeds chatmine extractions and high-value assistant messages from DB
snapshots into a numpy vector index for real-time retrieval during
agent turns.

Usage:
    python3 build_index.py build [--force]
    python3 build_index.py status
    python3 build_index.py search "query" [--top 5]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Import config for workspace/state paths
from config import WORKSPACE, STATE_DIR

# ---------------------------------------------------------------------------
# Index paths
# ---------------------------------------------------------------------------

METACOG_DIR = os.path.join(STATE_DIR, "metacognition")
VECTORS_FILE = os.path.join(METACOG_DIR, "metacognition_vectors.npy")
META_FILE = os.path.join(METACOG_DIR, "metacognition_meta.json")
CHATMINE_DIR = os.path.join(STATE_DIR, "chatmine")
DB_SNAPSHOTS_DIR = os.path.join(STATE_DIR, "db_snapshots")

# ---------------------------------------------------------------------------
# Embedding config — mirrors memory_search.py
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIM = 3072
BATCH_SIZE = 10
BATCH_SLEEP = 0.1
MAX_RETRIES = 3

EMBEDDING_BACKEND = os.environ.get("APEX_EMBEDDING_BACKEND", "gemini")
OLLAMA_URL = os.environ.get("APEX_OLLAMA_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("APEX_OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_DIM = 768

# Text limits
MAX_EMBED_CHARS = 6000  # max chars to embed per document
PREVIEW_LIMIT = 2000  # chars stored in metadata for retrieval display
DB_MIN_CONTENT_LEN = 2000  # min assistant message length to index from DB

# Analytical keywords — assistant messages containing these are higher signal
ANALYTICAL_KEYWORDS = {
    "first principles", "analysis", "architecture", "design",
    "trade-off", "tradeoff", "recommendation", "because",
    "root cause", "the reason", "fundamentally", "implementation",
    "strategy", "approach", "conclusion", "summary",
    "layer 1", "layer 2", "layer 3", "layer 4",
}


# ---------------------------------------------------------------------------
# Gemini API key + client
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        for env_path in [
            Path.home() / ".apex" / ".env",
            Path.home() / ".openclaw" / ".env",
        ]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("GOOGLE_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip("'\"")
                        break
            if key:
                break
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY not found in environment or ~/.apex/.env / ~/.openclaw/.env"
        )
    return key


_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=_get_api_key())
    return _client


# ---------------------------------------------------------------------------
# Embedding — Gemini
# ---------------------------------------------------------------------------

def _embed_batch_gemini(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
            )
            return [emb.values for emb in response.embeddings]
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = 2 ** attempt
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Embedding failed after {MAX_RETRIES} retries")


# ---------------------------------------------------------------------------
# Embedding — Ollama fallback
# ---------------------------------------------------------------------------

def _embed_batch_ollama(texts: list[str]) -> list[list[float]]:
    import urllib.request
    payload = json.dumps({"model": OLLAMA_EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["embeddings"]


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------

def _get_embed_dim() -> int:
    return OLLAMA_EMBED_DIM if EMBEDDING_BACKEND == "ollama" else EMBEDDING_DIM


def _embed_batch(texts: list[str]) -> list[list[float]]:
    if EMBEDDING_BACKEND == "ollama":
        return _embed_batch_ollama(texts)
    return _embed_batch_gemini(texts)


def _embed_single(text: str) -> np.ndarray:
    vectors = _embed_batch([text])
    return np.array(vectors[0], dtype=np.float32)


def _embed_texts(texts: list[str], label: str = "") -> np.ndarray:
    all_vectors: list[list[float]] = []
    total = len(texts)
    for i in range(0, total, BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        if label:
            print(f"  Embedding {label}: {min(i + BATCH_SIZE, total)}/{total}...")
        vectors = _embed_batch(batch)
        all_vectors.extend(vectors)
        if i + BATCH_SIZE < total:
            time.sleep(BATCH_SLEEP)
    return np.array(all_vectors, dtype=np.float32)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(query_vec: np.ndarray, index_vecs: np.ndarray) -> np.ndarray:
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(index_vecs, axis=1, keepdims=True) + 1e-10
    index_norm = index_vecs / norms
    return index_norm @ query_norm


# ---------------------------------------------------------------------------
# Document extraction — Chatmine
# ---------------------------------------------------------------------------

def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _extract_chatmine_docs() -> list[dict]:
    """Extract embeddable documents from chatmine extraction files.

    Each chatmine dir has dated JSON files with keys:
    decisions, bugs_fixed, features_built, lessons, topics

    We aggregate all items from a single JSON file into ONE document
    (one embedding per chat-day), keeping the document count manageable.
    """
    docs = []
    chatmine_path = Path(CHATMINE_DIR)
    if not chatmine_path.is_dir():
        print(f"  No chatmine dir at {CHATMINE_DIR}")
        return docs

    chat_dirs = sorted(chatmine_path.iterdir())
    print(f"  Scanning {len(chat_dirs)} chatmine directories...")

    for chat_dir in chat_dirs:
        if not chat_dir.is_dir():
            continue
        chat_id = chat_dir.name

        for json_file in sorted(chat_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            date_str = json_file.stem  # e.g. "2026-04-07"

            # Aggregate all items from this file into a single document
            parts: list[str] = []
            for category, items in data.items():
                if not isinstance(items, list) or not items:
                    continue
                parts.append(f"[{category}]")
                for item in items:
                    text = item if isinstance(item, str) else str(item)
                    if len(text.strip()) >= 20:
                        parts.append(f"- {text.strip()}")

            combined = "\n".join(parts)
            if len(combined) < 50:
                continue

            docs.append({
                "text": combined[:MAX_EMBED_CHARS],
                "source": "chatmine",
                "category": "aggregated",
                "chat_id": chat_id,
                "date": date_str,
                "hash": _content_hash(combined),
            })

    return docs


def _extract_chatmine_summaries() -> list[dict]:
    """Extract summary.md files from chatmine directories."""
    docs = []
    chatmine_path = Path(CHATMINE_DIR)
    if not chatmine_path.is_dir():
        return docs

    for chat_dir in sorted(chatmine_path.iterdir()):
        if not chat_dir.is_dir():
            continue
        summary_file = chat_dir / "summary.md"
        if summary_file.exists():
            content = summary_file.read_text().strip()
            if len(content) >= 50:
                docs.append({
                    "text": content[:MAX_EMBED_CHARS],
                    "source": "chatmine_summary",
                    "category": "summary",
                    "chat_id": chat_dir.name,
                    "date": "",
                    "hash": _content_hash(content),
                })

    return docs


# ---------------------------------------------------------------------------
# Document extraction — DB snapshot
# ---------------------------------------------------------------------------

def _has_analytical_keywords(text: str) -> bool:
    """Check if text contains analytical keywords suggesting high-value content."""
    text_lower = text.lower()
    matches = sum(1 for kw in ANALYTICAL_KEYWORDS if kw in text_lower)
    return matches >= 2  # at least 2 keyword hits


def _extract_db_docs() -> list[dict]:
    """Extract high-value assistant messages from DB snapshot.

    Filters:
    - role = 'assistant'
    - content length > DB_MIN_CONTENT_LEN
    - Contains analytical keywords (at least 2)
    """
    docs = []

    # Find latest DB snapshot
    snapshots_path = Path(DB_SNAPSHOTS_DIR)
    if not snapshots_path.is_dir():
        print(f"  No DB snapshots dir at {DB_SNAPSHOTS_DIR}")
        return docs

    # Prefer dev snapshot, fall back to prod
    db_path = None
    for candidate in ["latest_dev.db", "latest_prod.db"]:
        p = snapshots_path / candidate
        if p.exists():
            # Resolve symlink
            db_path = p.resolve()
            break

    if not db_path or not db_path.exists():
        print("  No DB snapshot found")
        return docs

    print(f"  Reading DB snapshot: {db_path.name}")

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            """SELECT id, chat_id, content, created_at
               FROM messages
               WHERE role = 'assistant'
                 AND LENGTH(content) > ?
               ORDER BY created_at DESC""",
            (DB_MIN_CONTENT_LEN,),
        )

        total_scanned = 0
        for row in cursor:
            msg_id, chat_id, content, created_at = row
            total_scanned += 1

            if not _has_analytical_keywords(content):
                continue

            # Truncate for embedding
            embed_text = content[:MAX_EMBED_CHARS]
            docs.append({
                "text": embed_text,
                "source": "db_assistant",
                "category": "assistant_message",
                "chat_id": chat_id,
                "date": created_at[:10] if created_at else "",
                "hash": _content_hash(content),
                "msg_id": msg_id,
                "full_length": len(content),
            })

        conn.close()
        print(f"  DB: scanned {total_scanned} messages, {len(docs)} passed analytical filter")

    except Exception as e:
        print(f"  ERROR reading DB snapshot: {e}")

    return docs


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------

def build_index(force: bool = False) -> dict:
    """Build or incrementally update the metacognition index.

    Returns:
        {"total": N, "new": N, "kept": N, "sources": {...}}
    """
    os.makedirs(METACOG_DIR, exist_ok=True)

    # Load existing index if not forcing
    existing_meta: list[dict] = []
    existing_vectors = None
    if not force and os.path.exists(META_FILE) and os.path.exists(VECTORS_FILE):
        existing_meta = json.loads(Path(META_FILE).read_text())
        existing_vectors = np.load(VECTORS_FILE)

    existing_by_hash = {m["hash"]: (i, m) for i, m in enumerate(existing_meta)}

    # Extract documents from all sources
    print("Extracting documents...")
    chatmine_docs = _extract_chatmine_docs()
    summary_docs = _extract_chatmine_summaries()
    db_docs = _extract_db_docs()
    all_docs = chatmine_docs + summary_docs + db_docs

    print(f"\n  Total documents: {len(all_docs)}")
    print(f"    Chatmine items: {len(chatmine_docs)}")
    print(f"    Chatmine summaries: {len(summary_docs)}")
    print(f"    DB assistant messages: {len(db_docs)}")

    if not all_docs:
        print("  No documents to index.")
        return {"total": 0, "new": 0, "kept": 0}

    # Separate into keep vs embed
    to_embed: list[dict] = []
    kept: list[tuple[int, dict]] = []

    for doc in all_docs:
        h = doc["hash"]
        if h in existing_by_hash:
            idx, old_meta = existing_by_hash[h]
            kept.append((idx, old_meta))
        else:
            to_embed.append(doc)

    print(f"\n  To embed: {len(to_embed)} new documents")
    print(f"  Keeping: {len(kept)} existing embeddings")

    if not to_embed:
        print("  Index is up to date.")
        return {
            "total": len(kept),
            "new": 0,
            "kept": len(kept),
            "sources": _count_sources(existing_meta),
        }

    # Embed new documents
    texts = [doc["text"] for doc in to_embed]
    try:
        new_vectors = _embed_texts(texts, label="metacognition")
    except Exception as e:
        print(f"\n  ERROR embedding: {e}")
        return {"total": len(kept), "new": 0, "kept": len(kept), "error": str(e)}

    # Build final index
    all_meta: list[dict] = []
    vector_list: list[np.ndarray] = []

    # Kept entries
    for idx, meta in kept:
        all_meta.append(meta)
        vector_list.append(existing_vectors[idx])

    # New entries
    for i, doc in enumerate(to_embed):
        meta_entry = {
            "hash": doc["hash"],
            "source": doc["source"],
            "category": doc["category"],
            "chat_id": doc.get("chat_id", ""),
            "date": doc.get("date", ""),
            "content_preview": doc["text"][:PREVIEW_LIMIT],
        }
        if "msg_id" in doc:
            meta_entry["msg_id"] = doc["msg_id"]
        if "full_length" in doc:
            meta_entry["full_length"] = doc["full_length"]
        all_meta.append(meta_entry)
        vector_list.append(new_vectors[i])

    # Save
    final_vectors = np.stack(vector_list) if vector_list else np.zeros(
        (0, _get_embed_dim()), dtype=np.float32
    )
    np.save(VECTORS_FILE, final_vectors)
    Path(META_FILE).write_text(json.dumps(all_meta, indent=2))

    result = {
        "total": len(all_meta),
        "new": len(to_embed),
        "kept": len(kept),
        "sources": _count_sources(all_meta),
    }
    print(f"\n  Index saved: {result['total']} documents total")
    print(f"  Sources: {json.dumps(result['sources'])}")
    return result


def _count_sources(meta: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in meta:
        src = m.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(query: str, top_k: int = 5) -> list[dict]:
    """Search the metacognition index.

    Args:
        query: Natural language search query.
        top_k: Number of results to return.

    Returns:
        List of {score, source, category, date, content_preview} sorted by score.
    """
    if not os.path.exists(VECTORS_FILE) or not os.path.exists(META_FILE):
        print("Index not built. Run: python3 build_index.py build")
        return []

    vectors = np.load(VECTORS_FILE)
    meta = json.loads(Path(META_FILE).read_text())

    if len(meta) == 0:
        return []

    query_vec = _embed_single(query)
    scores = _cosine_similarity(query_vec, vectors)

    results = []
    for i, score in enumerate(scores):
        entry = meta[i]
        results.append({
            "score": float(score),
            "source": entry.get("source", ""),
            "category": entry.get("category", ""),
            "chat_id": entry.get("chat_id", ""),
            "date": entry.get("date", ""),
            "content_preview": entry.get("content_preview", ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def index_status() -> dict:
    """Return index statistics."""
    if not os.path.exists(META_FILE):
        return {"built": False, "total": 0}

    meta = json.loads(Path(META_FILE).read_text())
    vec_size = os.path.getsize(VECTORS_FILE) if os.path.exists(VECTORS_FILE) else 0

    return {
        "built": True,
        "total": len(meta),
        "index_size_mb": round(vec_size / 1024 / 1024, 2),
        "last_updated": time.ctime(os.path.getmtime(META_FILE)),
        "sources": _count_sources(meta),
        "embed_backend": EMBEDDING_BACKEND,
        "embed_dim": _get_embed_dim(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(
        description="Build and query the metacognition retrieval index"
    )
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="Build/update the index")
    p_build.add_argument("--force", action="store_true", help="Re-embed everything")

    sub.add_parser("status", help="Show index statistics")

    p_search = sub.add_parser("search", help="Search the index")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--top", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    if args.command == "build":
        print(f"Building metacognition index (force={args.force})...\n")
        result = build_index(force=args.force)
        print(f"\nResult: {json.dumps(result, indent=2)}")

    elif args.command == "status":
        info = index_status()
        print("Metacognition Index Status:")
        for k, v in info.items():
            print(f"  {k}: {v}")

    elif args.command == "search":
        results = search(args.query, top_k=args.top)
        if not results:
            print("No results found.")
            return
        for i, r in enumerate(results, 1):
            print(f"\n{'=' * 60}")
            print(f"  #{i}  score={r['score']:.4f}  source={r['source']}  category={r['category']}")
            print(f"  chat_id={r['chat_id']}  date={r['date']}")
            print(f"{'=' * 60}")
            preview = r["content_preview"][:500]
            print(preview)
            if len(r["content_preview"]) > 500:
                print("  ...")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
