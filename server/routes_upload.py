"""File upload and voice transcription routes.

Layer 4: no imports from apex.py — all config re-derived from env.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import mimetypes
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import env
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, Response

from log import log

upload_router = APIRouter()

# ---------------------------------------------------------------------------
# Config (re-derived from env — same source of truth as apex.py)
# ---------------------------------------------------------------------------
_APEX_ROOT = env.APEX_ROOT
UPLOAD_DIR = _APEX_ROOT / "state" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
safe_chmod(UPLOAD_DIR, 0o700)

IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp"}
TEXT_TYPES = {"txt", "py", "json", "csv", "md", "yaml", "yml", "toml", "cfg", "ini", "log",
              "html", "css", "js", "ts", "sh"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10MB
MAX_TEXT_SIZE = 1 * 1024 * 1024     # 1MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024   # 10MB
WHISPER_BIN = env.WHISPER_BIN

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# V2-07: Magic byte signatures for image content validation
_IMAGE_MAGIC = {
    "jpg":  [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png":  [b"\x89PNG\r\n\x1a\n"],
    "gif":  [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],  # RIFF....WEBP
}


def _validate_image_magic(data: bytes, ext: str) -> bool:
    """Check that image file content starts with expected magic bytes."""
    sigs = _IMAGE_MAGIC.get(ext)
    if not sigs:
        return True
    return any(data[:len(sig)] == sig for sig in sigs)


def _normalize_filename(filename: str | None, fallback: str = "upload") -> str:
    safe = Path(filename or fallback).name.replace("\x00", "").strip()
    return safe or fallback


def _guess_mime_type(ext: str) -> str:
    mime, _ = mimetypes.guess_type(f"file.{ext}")
    return mime or ("image/jpeg" if ext in {"jpg", "jpeg"} else "application/octet-stream")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@upload_router.get("/api/uploads/{filename}")
async def api_serve_upload(filename: str):
    """Serve uploaded files by filename (V2-07: replaces absolute path exposure)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    path = (UPLOAD_DIR / filename).resolve()
    if not path.parent == UPLOAD_DIR.resolve() or not path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    ext = path.suffix.lstrip(".").lower()
    mime = _guess_mime_type(ext) if ext in IMAGE_TYPES else "application/octet-stream"
    return Response(content=path.read_bytes(), media_type=mime)


@upload_router.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    filename = _normalize_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    is_image = ext in IMAGE_TYPES
    is_text = ext in TEXT_TYPES
    if not is_image and not is_text:
        return JSONResponse({"error": f"Unsupported file type: .{ext}"}, status_code=400)

    try:
        data = await file.read()
    finally:
        await file.close()

    # V2-07: Validate content matches claimed type via magic bytes
    if is_image and not _validate_image_magic(data, ext):
        return JSONResponse({"error": "File content does not match image type"}, status_code=400)

    max_size = MAX_IMAGE_SIZE if is_image else MAX_TEXT_SIZE
    if len(data) > max_size:
        return JSONResponse({"error": f"File too large ({len(data)} bytes, max {max_size})"}, status_code=400)

    file_id = str(uuid.uuid4())[:8]
    out_name = f"{file_id}.{ext}"
    path = UPLOAD_DIR / out_name
    path.write_bytes(data)
    safe_chmod(path, 0o600)

    result = {
        "id": file_id,
        "name": _normalize_filename(file.filename),
        "url": f"/api/uploads/{out_name}",
        "type": "image" if is_image else "text",
        "ext": ext,
        "size": len(data),
    }
    if is_image:
        result["base64"] = base64.b64encode(data).decode()
        result["mimeType"] = _guess_mime_type(ext)

    log(f"upload: {result['name']} ({len(data)} bytes) → {path}")
    return JSONResponse(result)


@upload_router.post("/api/transcribe")
async def api_transcribe(file: UploadFile = File(...)):
    filename = _normalize_filename(file.filename, "voice.webm")
    try:
        data = await file.read()
    finally:
        await file.close()
    if len(data) > MAX_AUDIO_SIZE:
        return JSONResponse({"error": "Audio too large"}, status_code=400)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    with tempfile.TemporaryDirectory(prefix="apex-whisper-") as tmp_dir:
        input_path = Path(tmp_dir) / f"audio.{ext}"
        input_path.write_bytes(data)
        log(f"transcribing: {len(data)} bytes ({ext})")
        try:
            proc = await asyncio.create_subprocess_exec(
                WHISPER_BIN, str(input_path), "--model", "turbo",
                "--output_format", "json", "--output_dir", tmp_dir,
                "--language", "en",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return JSONResponse({"error": "Whisper binary not found"}, status_code=500)

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            return JSONResponse({"error": "Transcription timed out"}, status_code=504)

        if proc.returncode not in (0, None):
            log(f"whisper failed: {stderr.decode()[:500]}")
            return JSONResponse({"error": "Transcription failed"}, status_code=500)

        import json
        json_path = Path(tmp_dir) / f"{input_path.stem}.json"
        if json_path.exists():
            result = json.loads(json_path.read_text())
            text = result.get("text", "").strip()
            log(f"transcribed: '{text[:60]}...' ({len(text)} chars)")
            return JSONResponse({"text": text})

        log(f"whisper failed: {stderr.decode()[:500] or stdout.decode()[:500]}")
        return JSONResponse({"error": "Transcription failed"}, status_code=500)
