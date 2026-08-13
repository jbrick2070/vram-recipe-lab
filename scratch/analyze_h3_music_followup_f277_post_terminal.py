#!/usr/bin/env python3
"""Receipt-bound, render-free descriptors for the failed H3 follow-up f277 clip.

This is deliberately a one-shot post-terminal evidence tool.  It reads the
failed render's immutable receipt, recipe, and native-audio artifact; imports
the mission-1 analyzer only after verifying its pinned SHA-256; and writes only
to one new directory under scratch/.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratch"
OUTPUTS = ROOT / "outputs"
RESULTS = ROOT / "results"
RECIPES = ROOT / "recipes"

ANALYZER = SCRATCH / "h3_music_machine_descriptors" / "analyze.py"
ANALYZER_SHA256 = "24cc09b0a7a187d7cf7a5dee0ab5547ad4b8bf64d40641ace86c1c8f571a5b3f"
EXPECTED_VENV_PREFIX = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv")

RECIPE = "h3_music_followup_score_seed42_f277"
RECIPE_PATH = RECIPES / f"{RECIPE}.json"
RECIPE_SHA256 = "8965353ccf49d075f953cf9700119cb4030cface2b909f235d3a7bc8fd739094"
RECEIPT_PATH = RESULTS / f"{RECIPE}_run1.json"
RECEIPT_SHA256 = "5b7e8963c464dc8bcf23accc1cda120234bfd0ea8614eeb885d6f8c3f1cd1124"
ARTIFACT_NAME = f"{RECIPE}_out_00001_.mp4"
ARTIFACT_PATH = OUTPUTS / ARTIFACT_NAME
ARTIFACT_SHA256 = "727c2bbbf3ec969ebf8051b7659f0cd7531fba07abfb52340baf9aa1b2c60a67"
EXPECTED_STATUS = "FAIL (VRAM 14.72 GB > 14.5 GB)"
RESULT_DIR = (
    SCRATCH
    / "h3music-followup-20260810T195909Z-ac3f65ee-attempt-001-f277-post-terminal-descriptors"
)
LABEL = "J4-duration-f277-post-terminal"


class EvidenceError(RuntimeError):
    """Pinned source evidence is missing, changed, or semantically invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json_no_bom(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"cannot read {label}: {path}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise EvidenceError(f"{label} contains a UTF-8 BOM: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid UTF-8 JSON in {label}: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvidenceError(f"{label} must be a JSON object: {path}")
    return payload, raw


def require_exact_file(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise EvidenceError(f"missing {label}: {path}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise EvidenceError(
            f"{label} SHA-256 drift: {actual_sha256} != {expected_sha256}"
        )
    return {
        "path": str(path.resolve()),
        "sha256": actual_sha256,
        "bytes": path.stat().st_size,
    }


def verify_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "receipt_schema_version": 3,
        "recipe": RECIPE,
        "recipe_sha256": RECIPE_SHA256,
        "output_path": ARTIFACT_NAME,
        "artifact_sha256": ARTIFACT_SHA256,
        "artifact_bytes": ARTIFACT_PATH.stat().st_size,
        "run_number": 1,
        "config_run_count": 1,
        "status": EXPECTED_STATUS,
        "gate_pass": False,
        "pass": False,
        "warm_pass": False,
        "promotion_ready": False,
        "valid_measurement": True,
        "audio_present": True,
    }
    mismatches = {
        key: {"expected": expected_value, "actual": receipt.get(key)}
        for key, expected_value in expected.items()
        if receipt.get(key) != expected_value
    }
    if mismatches:
        raise EvidenceError(f"failed receipt binding drift: {mismatches}")
    return {
        "status": receipt["status"],
        "gate_pass": False,
        "pass": False,
        "valid_measurement": True,
        "warm_pass": False,
        "promotion_ready": False,
        "absolute_peak_vram_gb": receipt.get("absolute_peak_vram_gb"),
        "baseline_vram_gb": receipt.get("baseline_vram_gb"),
        "net_peak_vram_gb": receipt.get("net_peak_vram_gb"),
        "certification_effect": False,
        "quality_judgment": "PENDING_HUMAN",
    }


def load_pinned_analyzer() -> Any:
    require_exact_file(ANALYZER, ANALYZER_SHA256, "mission-1 analyzer")
    spec = importlib.util.spec_from_file_location(
        "_h3_music_machine_descriptors_pinned_f277_post_terminal", ANALYZER
    )
    if spec is None or spec.loader is None:
        raise EvidenceError(f"cannot construct analyzer import spec: {ANALYZER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_metrics(metrics: Any) -> None:
    if not isinstance(metrics, dict) or not metrics:
        raise EvidenceError("descriptor metrics are absent")
    for key, value in metrics.items():
        values = value if isinstance(value, list) else [value]
        for scalar in values:
            if scalar is None:
                continue
            if (
                isinstance(scalar, bool)
                or not isinstance(scalar, (int, float))
                or not math.isfinite(float(scalar))
            ):
                raise EvidenceError(f"descriptor metric {key} is not finite numeric evidence")


def write_exclusive_json(path: Path, payload: Any) -> None:
    with path.open("xb") as handle:
        handle.write(canonical_json(payload))


def no_bom_file_evidence(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise EvidenceError(f"generated file contains a UTF-8 BOM: {path}")
    raw.decode("utf-8")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "bytes": len(raw),
        "utf8_no_bom": True,
    }


def main() -> int:
    if Path(sys.prefix).resolve() != EXPECTED_VENV_PREFIX.resolve():
        raise EvidenceError(
            f"must run with pinned Comfy venv: {sys.prefix} != {EXPECTED_VENV_PREFIX}"
        )
    if RESULT_DIR.exists():
        raise EvidenceError(f"exclusive result directory already exists: {RESULT_DIR}")

    script_evidence = require_exact_file(Path(__file__).resolve(), sha256_file(Path(__file__).resolve()), "wrapper")
    analyzer_evidence = require_exact_file(
        ANALYZER, ANALYZER_SHA256, "mission-1 analyzer"
    )
    recipe_evidence = require_exact_file(RECIPE_PATH, RECIPE_SHA256, "recipe")
    receipt_evidence = require_exact_file(RECEIPT_PATH, RECEIPT_SHA256, "failed receipt")
    artifact_evidence = require_exact_file(ARTIFACT_PATH, ARTIFACT_SHA256, "native-audio artifact")
    receipt, receipt_raw = read_json_no_bom(RECEIPT_PATH, "failed receipt")
    if hashlib.sha256(receipt_raw).hexdigest() != RECEIPT_SHA256:
        raise EvidenceError("receipt bytes changed between hash and parse")
    source_render_gate = verify_receipt(receipt)

    analyzer = load_pinned_analyzer()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise EvidenceError("ffmpeg and ffprobe must already be on PATH")

    RESULT_DIR.mkdir(parents=True, exist_ok=False)
    record = analyzer.analyze_clip(
        LABEL,
        ARTIFACT_NAME,
        ARTIFACT_SHA256,
        ffmpeg,
        ffprobe,
        RESULT_DIR,
    )
    if record.get("input_sha256") != ARTIFACT_SHA256:
        raise EvidenceError("analyzer result is not bound to the exact artifact")
    expected_commands = {
        "C0_probe",
        "C1_ebur128",
        "C2_silencedetect",
        "C3_astats",
        "C4_pcm_extract",
        "C5_scene_scores",
    }
    if set(record.get("commands") or {}) != expected_commands:
        raise EvidenceError("analyzer command evidence is incomplete")
    verify_metrics(record.get("metrics"))

    safe_label = LABEL
    expected_logs = [
        RESULT_DIR / f"{safe_label}.{suffix}.log"
        for suffix in ("probe", "ebur128", "silencedetect", "astats", "scene_scores")
    ]
    log_evidence = [no_bom_file_evidence(path) for path in expected_logs]

    record.update(
        {
            "recipe": RECIPE,
            "recipe_sha256": RECIPE_SHA256,
            "receipt_binding": receipt_evidence,
            "source_render_gate": source_render_gate,
            "certification_effect": False,
            "quality_judgment": "PENDING_HUMAN",
        }
    )
    ffmpeg_version, _ = analyzer.run_text([ffmpeg, "-version"])
    ffprobe_version, _ = analyzer.run_text([ffprobe, "-version"])
    payload = {
        "schema_version": 1,
        "kind": "h3-music-followup-f277-post-terminal-machine-descriptors",
        "scope": "scratch-only, render-free descriptor completion after terminal render failure",
        "campaign_id": "h3music-followup-20260810T195909Z-ac3f65ee-attempt-001",
        "wrapper": script_evidence,
        "pinned_analyzer": analyzer_evidence,
        "recipe_binding": recipe_evidence,
        "receipt_binding": receipt_evidence,
        "artifact_binding": artifact_evidence,
        "source_render_gate": source_render_gate,
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "python_version": sys.version,
        "numpy_version": analyzer.np.__version__,
        "ffmpeg_executable": ffmpeg,
        "ffmpeg_version": ffmpeg_version.splitlines()[0],
        "ffprobe_executable": ffprobe,
        "ffprobe_version": ffprobe_version.splitlines()[0],
        "analysis_command": analyzer.display_command(
            [sys.executable, "-B", str(Path(__file__).resolve())]
        ),
        "definitions": {
            "spectral_windows": "non-overlapping complete 50 ms windows, Hann-weighted, mono 48 kHz signed 16-bit PCM",
            "spectral_flux": "mean sum of positive binwise changes between consecutive L1-normalized magnitude spectra",
            "periodicity": "largest overlap-energy-normalized autocorrelation coefficient at a 0.25-2.00 s lag after global mean removal",
            "bands_hz": [[low, high] for low, high in analyzer.BANDS_HZ],
            "alignment": "Pearson r across matching complete 0.5 s buckets: mean ffmpeg lavfi.scene_score versus linear mono PCM RMS; crude proxy, not sync proof",
            "interpretation_limit": "Machine descriptors do not determine music presence, mood, quality, usability, or causation.",
        },
        "logs": log_evidence,
        "records": [record],
        "valid_measurement": True,
        "certification_effect": False,
        "quality_judgment": "PENDING_HUMAN",
    }
    descriptor_path = RESULT_DIR / "descriptors.json"
    write_exclusive_json(descriptor_path, payload)
    descriptor_evidence = no_bom_file_evidence(descriptor_path)

    verification = {
        "schema_version": 1,
        "kind": "h3-music-followup-f277-post-terminal-descriptor-file-verification",
        "descriptor": descriptor_evidence,
        "logs": [no_bom_file_evidence(path) for path in expected_logs],
        "pinned_sources": {
            "wrapper": script_evidence,
            "analyzer": analyzer_evidence,
            "recipe": recipe_evidence,
            "receipt": receipt_evidence,
            "artifact": artifact_evidence,
        },
        "file_count_before_verification_receipt": 6,
        "all_generated_text_utf8_no_bom": True,
        "valid_measurement": True,
        "certification_effect": False,
        "quality_judgment": "PENDING_HUMAN",
    }
    verification_path = RESULT_DIR / "verification.json"
    write_exclusive_json(verification_path, verification)
    verification_evidence = no_bom_file_evidence(verification_path)

    print(descriptor_path)
    print(descriptor_evidence["sha256"])
    print(verification_path)
    print(verification_evidence["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
