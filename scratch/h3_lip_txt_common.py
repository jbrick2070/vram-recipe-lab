#!/usr/bin/env python3
"""Shared, offline-only primitives for the H3-LIP-TXT campaign.

Nothing in this module boots ComfyUI, opens a network connection, or queues a
render.  It exists so the alignment receipt, candidate recipes, and review
package use the same immutable-byte and UTF-8 rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
RECIPES = ROOT / "recipes"
RESULTS = ROOT / "results"
OUTPUTS = ROOT / "outputs"

SOURCE_AUDIO = FIXTURES / "tts_dialogue.wav"
SOURCE_AUDIO_RECEIPT = FIXTURES / "audio_receipts" / "tts_dialogue.json"
SOURCE_AUDIO_SHA256 = (
    "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
)
PORTRAIT_SHA256 = (
    "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
)

SAMPLE_RATE_HZ = 44_100
SOURCE_SAMPLES = 441_000
TARGET_FRAMES = 124
TARGET_FPS = 24
TARGET_SAMPLES = TARGET_FRAMES * SAMPLE_RATE_HZ // TARGET_FPS
if TARGET_FRAMES * SAMPLE_RATE_HZ % TARGET_FPS:
    raise RuntimeError("H3-LIP-TXT target span must be an integer sample count")
SOURCE_MAX_START_SAMPLE = SOURCE_SAMPLES - TARGET_SAMPLES

CONTROL_RECIPE_NAME = "h3_r2v_refaudio_tts_lipsync_exact_seed42"
CONTROL_RECIPE = RECIPES / f"{CONTROL_RECIPE_NAME}.json"
CONTROL_RECIPE_SHA256 = (
    "7b4364f86df260daeddc708547fcde4c61d4059e6cd29ff148d6eee9e08d479c"
)
TRANSCRIPT_RECEIPT = (
    FIXTURES / "audio_receipts" / "tts_dialogue_h3_target_window_transcript.json"
)


class H3LipTxtError(RuntimeError):
    """An evidence or contract violation for this campaign."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(payload: dict[str, Any], *, sort_keys: bool = True) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n"
    ).encode("utf-8")


def load_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load one BOM-free UTF-8 JSON object without silently normalizing it."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise H3LipTxtError(f"Cannot read {path}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise H3LipTxtError(f"UTF-8 BOM is forbidden: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise H3LipTxtError(f"Invalid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise H3LipTxtError(f"Expected a JSON object: {path}")
    return payload, raw


def repo_relative(path: Path) -> str:
    """Return a slash-normalized path only when it stays inside this repository."""
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise H3LipTxtError(f"Path must stay inside the lab repository: {path}") from exc


def repo_path(relative_path: str) -> Path:
    """Resolve a stored repo-relative path and reject traversal or absolute paths."""
    candidate = Path(relative_path.replace("\\", "/"))
    if candidate.is_absolute() or not relative_path or ".." in candidate.parts:
        raise H3LipTxtError(f"Unsafe repository-relative path: {relative_path!r}")
    path = (ROOT / candidate).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise H3LipTxtError(f"Path escapes repository: {relative_path!r}") from exc
    return path


def write_immutable(path: Path, payload: bytes) -> bool:
    """Publish nonempty bytes once; exact replays are idempotent, drift is fatal."""
    if not payload:
        raise H3LipTxtError(f"Refusing to publish a zero-byte artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if path.read_bytes() != payload:
            raise H3LipTxtError(f"Immutable artifact already differs: {path}")
        return False
    return True


def write_immutable_json(path: Path, payload: dict[str, Any]) -> bool:
    return write_immutable(path, canonical_json_bytes(payload))


def read_canonical_transcript(path: Path) -> tuple[str, bytes]:
    """Read the literal prompt text; reject rather than normalize any drift."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise H3LipTxtError("Transcript text must be UTF-8 without BOM")
    try:
        transcript = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise H3LipTxtError("Transcript text is not valid UTF-8") from exc
    if not transcript or "\x00" in transcript:
        raise H3LipTxtError("Transcript text must be nonempty and contain no NUL")
    if "\r" in transcript:
        raise H3LipTxtError("Transcript text must use LF only")
    if transcript.endswith("\n"):
        raise H3LipTxtError(
            "Transcript text must have no terminal newline; its literal UTF-8 bytes are hashed"
        )
    if unicodedata.normalize("NFC", transcript) != transcript:
        raise H3LipTxtError("Transcript text must already be NFC; it is never normalized silently")
    return transcript, raw


def require_sha256(path: Path, expected: str, label: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise H3LipTxtError(f"Missing {label}: {path}") from exc
    actual = sha256_bytes(payload)
    if actual != expected:
        raise H3LipTxtError(
            f"{label} hash drift: expected {expected}, found {actual}: {path}"
        )
    return payload
