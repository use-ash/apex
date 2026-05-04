"""Semantic search over memory files and conversation transcripts.

Uses Gemini Embedding 2 or Ollama (nomic-embed-text) to embed and search
memory files and Claude Code/Codex session transcripts.

Usage:
    python3 memory_search.py search "query" [--top 5] [--source memory|transcripts]
    python3 memory_search.py index [--force] [--source memory|transcripts]
    python3 memory_search.py status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------------------
# Configuration — all paths configurable via env vars
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIM = 3072
BATCH_SIZE = 10
BATCH_SLEEP = 0.1
MAX_RETRIES = 3

def _default_memory_dir() -> str:
    """Pick the first existing candidate. Workspace path is canonical as of 2026-04-21.

    Historical default `~/.apex/memory` was never populated on this machine —
    actual memory lives under the OpenClaw workspace.
    """
    candidates = [
        Path.home() / ".openclaw" / "workspace" / "memory",
        Path.home() / ".apex" / "memory",  # legacy fallback
    ]
    for c in candidates:
        if c.is_dir():
            return str(c)
    return str(candidates[0])  # workspace path even if missing, so errors are obvious


MEMORY_DIR = Path(os.environ.get("APEX_MEMORY_DIR", _default_memory_dir()))

# Transcript dirs: configurable via env var (comma-separated) or defaults
_DEFAULT_TRANSCRIPT_DIRS = [
    str(Path.home() / ".claude" / "projects"),
]
_transcript_dirs_env = os.environ.get("APEX_TRANSCRIPT_DIRS", "")
if _transcript_dirs_env:
    TRANSCRIPT_DIRS = [Path(p.strip()) for p in _transcript_dirs_env.split(",") if p.strip()]
else:
    TRANSCRIPT_DIRS = [Path(p) for p in _DEFAULT_TRANSCRIPT_DIRS]

INDEX_DIR = Path(
    os.environ.get("APEX_EMBEDDING_INDEX_DIR", str(Path.home() / ".apex" / "state" / "embeddings"))
)

# Embedding backend: "gemini" (default) or "ollama"
EMBEDDING_BACKEND = os.environ.get("APEX_EMBEDDING_BACKEND", "gemini")
OLLAMA_URL = os.environ.get("APEX_OLLAMA_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("APEX_OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_DIM = 768  # nomic-embed-text outputs 768-dim vectors

MEMORY_VECTORS = INDEX_DIR / "memory_vectors.npy"
MEMORY_META = INDEX_DIR / "memory_meta.json"
TRANSCRIPT_VECTORS = INDEX_DIR / "transcript_vectors.npy"
TRANSCRIPT_META = INDEX_DIR / "transcript_meta.json"

TRANSCRIPT_TEXT_LIMIT = 6000  # chars to embed per transcript
PREVIEW_LIMIT = 1000  # chars returned in search results


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
            "GOOGLE_API_KEY not found in environment or ~/.apex/.env"
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
# Gemini embedding with batching and retry
# ---------------------------------------------------------------------------

def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts via Gemini, returning list of float vectors."""
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


def _embed_texts(texts: list[str], label: str = "") -> np.ndarray:
    """Embed texts via Gemini in batches, returning (N, D) float32 array."""
    all_vectors: list[list[float]] = []
    total = len(texts)
    for i in range(0, total, BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        if label:
            print(f"  Embedding {label}: {min(i + BATCH_SIZE, total)}/{total}...")
        vectors = _embed_batch(batch)
        all_vectors.extend(vectors)
        if i + BATCH_SIZE < total:
            time.sleep(BATCH_SLEEP)
    return np.array(all_vectors, dtype=np.float32)


def _embed_single(text: str) -> np.ndarray:
    """Embed a single text via Gemini, returning (D,) float32 array."""
    vectors = _embed_batch([text])
    return np.array(vectors[0], dtype=np.float32)


# ---------------------------------------------------------------------------
# Ollama embedding backend
# ---------------------------------------------------------------------------

def _embed_batch_ollama(texts: list[str]) -> list[list[float]]:
    """Embed texts using Ollama's /api/embed endpoint."""
    import urllib.request
    payload = json.dumps({"model": OLLAMA_EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        data = json.loads(resp.read())
    return data["embeddings"]


def _embed_texts_ollama(texts: list[str], label: str = "") -> np.ndarray:
    """Embed texts via Ollama in batches, returning (N, D) float32 array."""
    all_vectors: list[list[float]] = []
    total = len(texts)
    for i in range(0, total, BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        if label:
            print(f"  Embedding {label} (ollama): {min(i + BATCH_SIZE, total)}/{total}...")
        vectors = _embed_batch_ollama(batch)
        all_vectors.extend(vectors)
        if i + BATCH_SIZE < total:
            time.sleep(BATCH_SLEEP)
    return np.array(all_vectors, dtype=np.float32)


def _embed_single_ollama(text: str) -> np.ndarray:
    """Embed a single text via Ollama, returning (D,) float32 array."""
    vectors = _embed_batch_ollama([text])
    return np.array(vectors[0], dtype=np.float32)


# ---------------------------------------------------------------------------
# Backend-agnostic embedding dispatch
# ---------------------------------------------------------------------------

def _get_embed_dim() -> int:
    """Return embedding dimension for current backend."""
    return OLLAMA_EMBED_DIM if EMBEDDING_BACKEND == "ollama" else EMBEDDING_DIM


def _do_embed_texts(texts: list[str], label: str = "") -> np.ndarray:
    """Embed texts using the configured backend."""
    if EMBEDDING_BACKEND == "ollama":
        return _embed_texts_ollama(texts, label=label)
    return _embed_texts(texts, label=label)


def _do_embed_single(text: str) -> np.ndarray:
    """Embed a single text using the configured backend."""
    if EMBEDDING_BACKEND == "ollama":
        return _embed_single_ollama(text)
    return _embed_single(text)


# ---------------------------------------------------------------------------
# File hashing and change detection
# ---------------------------------------------------------------------------

def _file_hash(path: Path) -> str:
    """SHA256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _file_mtime(path: Path) -> float:
    return path.stat().st_mtime


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------

def _extract_transcript(path: Path) -> tuple[str, str]:
    """Extract text from a JSONL transcript file.

    Returns (title, text) where title is the first substantive user message
    and text is the concatenated conversation, truncated to TRANSCRIPT_TEXT_LIMIT.
    """
    title = ""
    parts: list[str] = []
    total_chars = 0

    with open(path) as f:
        for line in f:
            if total_chars >= TRANSCRIPT_TEXT_LIMIT:
                break
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = entry.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            if entry.get("isMeta"):
                continue

            message = entry.get("message", {})
            content = message.get("content")
            if not content:
                continue

            text = _extract_text_from_content(content)
            if not text or len(text.strip()) < 10:
                continue

            if text.strip().startswith("<command-name>"):
                continue
            if text.strip().startswith("<local-command"):
                continue

            role = message.get("role", msg_type)
            prefix = "User: " if role == "user" else "Assistant: "

            if not title and role == "user":
                title = text[:200].strip()

            chunk = prefix + text + "\n"
            parts.append(chunk)
            total_chars += len(chunk)

    full_text = "".join(parts)[:TRANSCRIPT_TEXT_LIMIT]
    return title, full_text


def _extract_text_from_content(content) -> str:
    """Extract plain text from message content (string or block array)."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "thinking":
                text_parts.append(block.get("thinking", ""))
        return "\n".join(text_parts)

    return ""


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------

def index_memory(force: bool = False) -> dict:
    """Index memory .md files.

    Args:
        force: If True, re-embed everything. If False, only embed changed files.

    Returns:
        {"indexed": N, "skipped": N}
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    existing_meta: list[dict] = []
    existing_vectors = None
    if not force and MEMORY_META.exists() and MEMORY_VECTORS.exists():
        existing_meta = json.loads(MEMORY_META.read_text())
        existing_vectors = np.load(MEMORY_VECTORS)

    existing_by_file = {m["file"]: (i, m) for i, m in enumerate(existing_meta)}

    md_files = sorted(MEMORY_DIR.glob("*.md"))
    if not md_files:
        print("No memory files found.")
        return {"indexed": 0, "skipped": 0}

    print(f"Indexing memory: scanning {len(md_files)} files...")

    to_embed: list[tuple] = []
    kept: list[tuple] = []

    for path in md_files:
        file_str = str(path)
        h = _file_hash(path)
        mt = _file_mtime(path)

        if file_str in existing_by_file:
            idx, old_meta = existing_by_file[file_str]
            if old_meta["hash"] == h:
                kept.append((idx, old_meta))
                continue

        content = path.read_text()
        to_embed.append((file_str, content, h, mt))

    skipped = len(kept)
    indexed = len(to_embed)

    if indexed == 0:
        print(f"  Memory: {skipped} files up to date, nothing to embed.")
        return {"indexed": 0, "skipped": skipped}

    print(f"  Memory: {indexed} new/changed, {skipped} up to date")

    texts = [item[1] for item in to_embed]
    try:
        new_vectors = _do_embed_texts(texts, label="memory")
    except Exception as e:
        print(f"  ERROR embedding memory files: {e}")
        return {"indexed": 0, "skipped": skipped, "error": str(e)}

    new_meta = []
    for i, (file_str, content, h, mt) in enumerate(to_embed):
        new_meta.append({
            "file": file_str,
            "hash": h,
            "mtime": mt,
            "content_preview": content[:PREVIEW_LIMIT],
        })

    all_meta: list[dict] = []
    vector_list = []

    for idx, meta in kept:
        all_meta.append(meta)
        vector_list.append(existing_vectors[idx])

    for i, meta in enumerate(new_meta):
        all_meta.append(meta)
        vector_list.append(new_vectors[i])

    final_vectors = np.stack(vector_list) if vector_list else np.zeros(
        (0, _get_embed_dim()), dtype=np.float32
    )
    np.save(MEMORY_VECTORS, final_vectors)
    MEMORY_META.write_text(json.dumps(all_meta, indent=2))

    print(f"  Memory index saved: {len(all_meta)} files total")
    return {"indexed": indexed, "skipped": skipped}


def index_transcripts(force: bool = False) -> dict:
    """Index transcript .jsonl files.

    Args:
        force: If True, re-embed everything. If False, only embed changed files.

    Returns:
        {"indexed": N, "skipped": N}
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    existing_meta: list[dict] = []
    existing_vectors = None
    if not force and TRANSCRIPT_META.exists() and TRANSCRIPT_VECTORS.exists():
        existing_meta = json.loads(TRANSCRIPT_META.read_text())
        existing_vectors = np.load(TRANSCRIPT_VECTORS)

    existing_by_file = {m["file"]: (i, m) for i, m in enumerate(existing_meta)}

    jsonl_files: list[Path] = []
    for tdir in TRANSCRIPT_DIRS:
        if tdir.is_dir():
            jsonl_files.extend(sorted(tdir.rglob("*.jsonl")))
    if not jsonl_files:
        print("No transcript files found.")
        return {"indexed": 0, "skipped": 0}

    print(f"Indexing transcripts: scanning {len(jsonl_files)} files...")

    to_embed: list[tuple] = []
    kept: list[tuple] = []

    for path in jsonl_files:
        file_str = str(path)
        h = _file_hash(path)
        mt = _file_mtime(path)

        if file_str in existing_by_file:
            idx, old_meta = existing_by_file[file_str]
            if old_meta["hash"] == h:
                kept.append((idx, old_meta))
                continue

        session_id = path.stem
        try:
            title, text = _extract_transcript(path)
        except Exception as e:
            print(f"  WARNING: Failed to extract {path.name}: {e}")
            continue

        if not text or len(text.strip()) < 50:
            continue

        to_embed.append((file_str, text, title, session_id, h, mt))

    skipped = len(kept)
    indexed = len(to_embed)

    if indexed == 0:
        print(f"  Transcripts: {skipped} files up to date, nothing to embed.")
        return {"indexed": 0, "skipped": skipped}

    print(f"  Transcripts: {indexed} new/changed, {skipped} up to date")

    texts = [item[1] for item in to_embed]
    new_vectors_list = []
    new_meta: list[dict] = []
    failed = 0

    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i : i + BATCH_SIZE]
        batch_items = to_embed[i : i + BATCH_SIZE]
        print(
            f"  Embedding transcripts: "
            f"{min(i + BATCH_SIZE, len(texts))}/{len(texts)}..."
        )
        try:
            if EMBEDDING_BACKEND == "ollama":
                vectors = _embed_batch_ollama(batch_texts)
            else:
                vectors = _embed_batch(batch_texts)
            for j, vec in enumerate(vectors):
                item = batch_items[j]
                file_str, text, title, session_id, h, mt = item
                new_vectors_list.append(np.array(vec, dtype=np.float32))
                new_meta.append({
                    "file": file_str,
                    "hash": h,
                    "mtime": mt,
                    "session_id": session_id,
                    "title": title[:200] if title else "",
                    "content_preview": text[:PREVIEW_LIMIT],
                })
        except Exception as e:
            failed += len(batch_texts)
            print(f"  ERROR embedding batch at {i}: {e}")

        if i + BATCH_SIZE < len(texts):
            time.sleep(BATCH_SLEEP)

    all_meta = []
    vector_list = []

    for idx, meta in kept:
        all_meta.append(meta)
        vector_list.append(existing_vectors[idx])

    for i, meta in enumerate(new_meta):
        all_meta.append(meta)
        vector_list.append(new_vectors_list[i])

    if vector_list:
        final_vectors = np.stack(vector_list)
    else:
        final_vectors = np.zeros((0, _get_embed_dim()), dtype=np.float32)

    np.save(TRANSCRIPT_VECTORS, final_vectors)
    TRANSCRIPT_META.write_text(json.dumps(all_meta, indent=2))

    actual_indexed = len(new_meta)
    print(
        f"  Transcript index saved: {len(all_meta)} files total"
        f"{f' ({failed} failed)' if failed else ''}"
    )
    return {"indexed": actual_indexed, "skipped": skipped}


def index_all(force: bool = False) -> dict:
    """Rebuild index for all sources."""
    return {
        "memory": index_memory(force=force),
        "transcripts": index_transcripts(force=force),
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _load_index(source: str) -> tuple[np.ndarray | None, list[dict]]:
    """Load vectors and metadata for a source."""
    if source == "memory":
        vec_path, meta_path = MEMORY_VECTORS, MEMORY_META
    else:
        vec_path, meta_path = TRANSCRIPT_VECTORS, TRANSCRIPT_META

    if not vec_path.exists() or not meta_path.exists():
        return None, []

    vectors = np.load(vec_path)
    meta = json.loads(meta_path.read_text())
    return vectors, meta


def _cosine_similarity(query_vec: np.ndarray, index_vecs: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and all index vectors."""
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(index_vecs, axis=1, keepdims=True) + 1e-10
    index_norm = index_vecs / norms
    return index_norm @ query_norm


def search(
    query: str,
    top_k: int = 5,
    sources: list[str] | None = None,
) -> list[dict]:
    """Search memory and/or transcripts.

    Args:
        query: Natural language search query.
        top_k: Number of results to return.
        sources: Filter by source type. None = all.
                 Options: ["memory", "transcripts"]

    Returns:
        List of {file, score, content, source} sorted by score descending.
    """
    if sources is None:
        sources = ["memory", "transcripts"]

    for src in sources:
        vec_path = MEMORY_VECTORS if src == "memory" else TRANSCRIPT_VECTORS
        if not vec_path.exists():
            print(f"Index for {src} not found, building...")
            if src == "memory":
                index_memory()
            else:
                index_transcripts()

    query_vec = _do_embed_single(query)

    results = []
    for src in sources:
        vectors, meta = _load_index(src)
        if vectors is None or len(meta) == 0:
            continue

        scores = _cosine_similarity(query_vec, vectors)
        for i, score in enumerate(scores):
            entry = meta[i]
            results.append({
                "file": entry["file"],
                "score": float(score),
                "content": entry.get("content_preview", ""),
                "source": src,
                "title": entry.get("title", ""),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def status() -> dict:
    """Show index statistics."""
    info = {}
    for src, vec_path, meta_path in [
        ("memory", MEMORY_VECTORS, MEMORY_META),
        ("transcripts", TRANSCRIPT_VECTORS, TRANSCRIPT_META),
    ]:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            vec_size = vec_path.stat().st_size if vec_path.exists() else 0
            info[src] = {
                "files": len(meta),
                "index_size_mb": round(vec_size / 1024 / 1024, 2),
                "last_updated": time.ctime(meta_path.stat().st_mtime),
            }
        else:
            info[src] = {"files": 0, "index_size_mb": 0, "last_updated": None}
    return info


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(
        description="Semantic search over memory and transcripts"
    )
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="Search indexed content")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--top", type=int, default=5, help="Number of results")
    p_search.add_argument(
        "--source",
        choices=["memory", "transcripts"],
        help="Search only this source",
    )

    p_index = sub.add_parser("index", help="Build/update index")
    p_index.add_argument(
        "--force", action="store_true", help="Re-embed everything"
    )
    p_index.add_argument(
        "--source",
        choices=["memory", "transcripts"],
        help="Index only this source",
    )

    sub.add_parser("status", help="Show index statistics")

    args = parser.parse_args()

    if args.command == "search":
        srcs = [args.source] if args.source else None
        results = search(args.query, top_k=args.top, sources=srcs)
        if not results:
            print("No results found.")
            return
        for i, r in enumerate(results, 1):
            print(f"\n{'='*60}")
            print(f"  #{i}  score={r['score']:.4f}  source={r['source']}")
            print(f"  file: {r['file']}")
            if r.get("title"):
                print(f"  title: {r['title'][:100]}")
            print(f"{'='*60}")
            preview = r["content"][:500]
            print(preview)
            if len(r["content"]) > 500:
                print("  ...")

    elif args.command == "index":
        if args.source == "memory":
            result = index_memory(force=args.force)
        elif args.source == "transcripts":
            result = index_transcripts(force=args.force)
        else:
            result = index_all(force=args.force)
        print(f"\nResult: {json.dumps(result, indent=2)}")

    elif args.command == "status":
        info = status()
        for src, data in info.items():
            print(f"\n{src}:")
            for k, v in data.items():
                print(f"  {k}: {v}")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
