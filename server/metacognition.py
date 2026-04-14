"""Metacognition: topic-triggered retrieval from the knowledge index.

Pre-think → embed → search → format prior context for injection into
the agent's system prompt. Adds ~200-500ms to turns that match prior
knowledge; zero cost when the index is empty or the topic doesn't match.

The pre-thinker uses a fast local Ollama model to extract topic keywords
from the user's message. Those keywords are embedded and searched against
the metacognition index built by build_index.py.

Graceful degradation chain:
  - Ollama down → use raw message as search query
  - Embedding API down → try Ollama; both down → skip
  - Index missing → skip
  - Any exception → log and continue without metacognition
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from pathlib import Path

import numpy as np

logger = logging.getLogger("apex.metacognition")

# Use Apex's own log function for visibility in nohup.out
try:
    from log import log as _apex_log
except ImportError:
    _apex_log = lambda msg: None  # noqa: E731

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Index paths — matches build_index.py output location
_SUBCONSCIOUS_DIR = os.environ.get(
    "APEX_SUBCONSCIOUS_DIR",
    str(Path(os.environ.get("APEX_WORKSPACE", os.getcwd())).resolve() / ".subconscious"),
)
METACOG_DIR = os.path.join(_SUBCONSCIOUS_DIR, "metacognition")
VECTORS_FILE = os.path.join(METACOG_DIR, "metacognition_vectors.npy")
META_FILE = os.path.join(METACOG_DIR, "metacognition_meta.json")

# Embedding config
EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIM = 3072
EMBEDDING_BACKEND = os.environ.get("APEX_EMBEDDING_BACKEND", "gemini")
OLLAMA_URL = os.environ.get("APEX_OLLAMA_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("APEX_OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_DIM = 768

# Pre-thinker config — fast local model for keyword extraction
PRETHINKER_MODEL = os.environ.get("APEX_PRETHINKER_MODEL", "qwen3:8b")
PRETHINKER_TIMEOUT = int(os.environ.get("APEX_PRETHINKER_TIMEOUT", "8"))

# Retrieval thresholds
SIMILARITY_THRESHOLD = float(os.environ.get("APEX_METACOG_THRESHOLD", "0.35"))
MAX_RESULTS = int(os.environ.get("APEX_METACOG_MAX_RESULTS", "3"))
MAX_CONTEXT_CHARS = int(os.environ.get("APEX_METACOG_MAX_CHARS", "4000"))

# Turn classifier — skip short/trivial messages
MIN_MESSAGE_LENGTH = 30  # messages shorter than this skip metacognition

# Cached index (loaded once, reloaded when file changes)
_index_cache: dict = {"vectors": None, "meta": None, "mtime": 0}


# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
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
    return key


_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = _get_api_key()
        if not api_key:
            return None
        from google import genai
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _embed_gemini(text: str) -> np.ndarray | None:
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text],
        )
        return np.array(response.embeddings[0].values, dtype=np.float32)
    except Exception as e:
        logger.warning("Gemini embedding failed: %s", e)
        return None


def _embed_ollama(text: str) -> np.ndarray | None:
    try:
        payload = json.dumps({"model": OLLAMA_EMBED_MODEL, "input": [text]}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return np.array(data["embeddings"][0], dtype=np.float32)
    except Exception as e:
        logger.warning("Ollama embedding failed: %s", e)
        return None


def _embed(text: str) -> np.ndarray | None:
    """Embed text with graceful fallback: Gemini → Ollama → None."""
    if EMBEDDING_BACKEND == "ollama":
        vec = _embed_ollama(text)
        return vec if vec is not None else _embed_gemini(text)
    vec = _embed_gemini(text)
    return vec if vec is not None else _embed_ollama(text)


# ---------------------------------------------------------------------------
# Pre-thinker — extract topic keywords via fast local model
# ---------------------------------------------------------------------------

_PRETHINKER_PROMPT = """Extract 3-5 topic keywords from this user message. Return ONLY the keywords separated by commas, nothing else.

User message: {message}

Keywords:"""


def _pre_think(message: str) -> str:
    """Use fast local Ollama model to extract topic keywords.

    Falls back to the raw message if Ollama is unavailable.
    """
    try:
        payload = json.dumps({
            "model": PRETHINKER_MODEL,
            "prompt": _PRETHINKER_PROMPT.format(message=message[:500]),
            "stream": False,
            "think": False,
            "options": {"num_predict": 64, "temperature": 0.1},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=PRETHINKER_TIMEOUT) as resp:
            data = json.loads(resp.read())
        raw = data.get("response", "").strip()
        # Strip thinking leakage (some models emit internal reasoning)
        # Take only the last line or content after the last newline
        keywords = raw.split("\n")[-1].strip() if "\n" in raw else raw
        # Remove any <think>...</think> blocks
        if "<think>" in keywords:
            import re
            keywords = re.sub(r"<think>.*?</think>", "", keywords, flags=re.DOTALL).strip()
        if keywords and len(keywords) < 200:  # sanity: keywords should be short
            return keywords
    except Exception as e:
        logger.debug("Pre-thinker unavailable (%s), using raw message", e)

    # Fallback: use the raw message itself
    return message


# ---------------------------------------------------------------------------
# Index loading (with cache)
# ---------------------------------------------------------------------------

def _load_index() -> tuple[np.ndarray | None, list[dict]]:
    """Load metacognition index, using cache if file hasn't changed."""
    if not os.path.exists(VECTORS_FILE) or not os.path.exists(META_FILE):
        return None, []

    current_mtime = os.path.getmtime(META_FILE)
    if _index_cache["meta"] is not None and _index_cache["mtime"] == current_mtime:
        return _index_cache["vectors"], _index_cache["meta"]

    try:
        vectors = np.load(VECTORS_FILE)
        meta = json.loads(Path(META_FILE).read_text())
        _index_cache["vectors"] = vectors
        _index_cache["meta"] = meta
        _index_cache["mtime"] = current_mtime
        logger.info("Metacognition index loaded: %d documents", len(meta))
        return vectors, meta
    except Exception as e:
        logger.warning("Failed to load metacognition index: %s", e)
        return None, []


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _cosine_similarity(query_vec: np.ndarray, index_vecs: np.ndarray) -> np.ndarray:
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(index_vecs, axis=1, keepdims=True) + 1e-10
    index_norm = index_vecs / norms
    return index_norm @ query_norm


def _search_index(query_vec: np.ndarray, top_k: int = 5) -> list[dict]:
    """Search the index with a pre-computed query vector."""
    vectors, meta = _load_index()
    if vectors is None or len(meta) == 0:
        return []

    scores = _cosine_similarity(query_vec, vectors)

    results = []
    for i, score in enumerate(scores):
        if score >= SIMILARITY_THRESHOLD:
            entry = meta[i].copy()
            entry["score"] = float(score)
            results.append(entry)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ---------------------------------------------------------------------------
# Turn classifier
# ---------------------------------------------------------------------------

# Skip patterns — messages that don't benefit from retrieval
_SKIP_PATTERNS = [
    "yes", "no", "ok", "okay", "sure", "thanks", "thank you",
    "got it", "sounds good", "do it", "go ahead", "continue",
    "commit", "push", "merge", "deploy", "restart",
]


def _should_retrieve(message: str) -> bool:
    """Decide whether this message warrants metacognition retrieval.

    Quick messages, confirmations, and pure commands skip retrieval.
    """
    stripped = message.strip().lower().rstrip("!?.")
    if len(stripped) < MIN_MESSAGE_LENGTH:
        return False
    if stripped in _SKIP_PATTERNS:
        return False
    # Single-word messages
    if " " not in stripped:
        return False
    return True


# ---------------------------------------------------------------------------
# Format prior context for injection
# ---------------------------------------------------------------------------

def _format_prior_context(results: list[dict]) -> str:
    """Format search results into a system prompt block."""
    if not results:
        return ""

    parts = ["<prior_knowledge>"]
    parts.append("The following is relevant prior knowledge from previous sessions:")
    total_chars = 0

    for i, r in enumerate(results, 1):
        preview = r.get("content_preview", "")
        source = r.get("source", "unknown")
        category = r.get("category", "")
        date = r.get("date", "")
        score = r.get("score", 0)

        # Trim preview to fit budget
        remaining = MAX_CONTEXT_CHARS - total_chars
        if remaining <= 100:
            break
        preview = preview[:remaining]

        header = f"[{source}/{category}"
        if date:
            header += f" {date}"
        header += f" relevance={score:.2f}]"

        parts.append(f"\n--- Prior #{i} {header} ---")
        parts.append(preview)
        total_chars += len(preview) + len(header) + 30

    parts.append("\n</prior_knowledge>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_prior_context(user_message: str) -> str:
    """Main entry point: retrieve relevant prior knowledge for a user message.

    Returns a formatted prior_knowledge block to inject into the system prompt,
    or empty string if nothing relevant is found.

    This function is designed to be called from agent_sdk._build_turn_payload().
    It handles all errors gracefully and never raises.
    """
    t0 = time.time()
    try:
        # Step 1: classify — should we even try?
        if not _should_retrieve(user_message):
            return ""

        # Step 2: check index exists
        if not os.path.exists(VECTORS_FILE):
            return ""

        # Step 3: pre-think — extract keywords
        search_query = _pre_think(user_message)

        # Step 4: embed the search query
        query_vec = _embed(search_query)
        if query_vec is None:
            return ""

        # Step 5: search
        results = _search_index(query_vec, top_k=MAX_RESULTS)
        if not results:
            return ""

        # Step 6: format
        context = _format_prior_context(results)
        elapsed = time.time() - t0
        _apex_log(
            "Metacognition: %d results in %.0fms (top=%.3f, query=%s)"
            % (len(results), elapsed * 1000, results[0]["score"], search_query[:80])
        )
        return context

    except Exception as e:
        elapsed = time.time() - t0
        _apex_log("Metacognition FAILED in %.0fms: %s" % (elapsed * 1000, e))
        return ""


def test_retrieval(message: str, verbose: bool = False) -> dict:
    """Test endpoint helper — run the full pipeline and return diagnostics.

    Used by /api/metacognition/test for development and debugging.
    """
    t0 = time.time()
    result: dict = {
        "message": message,
        "should_retrieve": False,
        "pre_think_keywords": "",
        "results": [],
        "formatted_context": "",
        "elapsed_ms": 0,
        "index_status": {},
        "error": None,
    }

    try:
        # Index status
        if os.path.exists(META_FILE):
            meta = json.loads(Path(META_FILE).read_text())
            result["index_status"] = {
                "total_documents": len(meta),
                "index_file": VECTORS_FILE,
                "meta_file": META_FILE,
            }
        else:
            result["index_status"] = {"total_documents": 0, "error": "Index not built"}
            result["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
            return result

        # Classify
        result["should_retrieve"] = _should_retrieve(message)
        if not result["should_retrieve"]:
            result["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
            return result

        # Pre-think
        keywords = _pre_think(message)
        result["pre_think_keywords"] = keywords

        # Embed
        query_vec = _embed(keywords)
        if query_vec is None:
            result["error"] = "Embedding failed (both Gemini and Ollama)"
            result["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
            return result

        # Search
        results = _search_index(query_vec, top_k=MAX_RESULTS)
        result["results"] = [
            {
                "score": r["score"],
                "source": r.get("source", ""),
                "category": r.get("category", ""),
                "date": r.get("date", ""),
                "preview": r.get("content_preview", "")[:300] if not verbose else r.get("content_preview", ""),
            }
            for r in results
        ]

        # Format
        result["formatted_context"] = _format_prior_context(results)

    except Exception as e:
        result["error"] = str(e)

    result["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
    return result
