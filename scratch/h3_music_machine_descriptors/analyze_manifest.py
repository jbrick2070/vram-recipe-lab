#!/usr/bin/env python3
"""Run the pinned H3 descriptor analyzer over a receipt-bound clip manifest.

This wrapper is local-only and render-free.  It makes the mission-1 analyzer
usable for newly created clips without changing that analyzer's historical
hard-coded comparison set.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
RESULTS = ROOT / "results"
ANALYZER = Path(__file__).resolve().with_name("analyze.py")
ANALYZER_SHA256 = "24cc09b0a7a187d7cf7a5dee0ab5547ad4b8bf64d40641ace86c1c8f571a5b3f"
HEX64 = frozenset("0123456789abcdef")


class ManifestError(RuntimeError):
    """The descriptor manifest or its bound evidence is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def require_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in HEX64 for character in value)
    ):
        raise ManifestError(f"{label} must be a lowercase SHA-256 digest")
    return value


def resolve_relative_under(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ManifestError(f"{label} must be a non-empty repo-relative path")
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ManifestError(f"{label} escapes {root}") from exc
    return candidate


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ManifestError(f"{label} contains a UTF-8 BOM")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError(f"{label} must be a JSON object")
    return payload


def validate_manifest_structure(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema_version") != 1:
        raise ManifestError("manifest schema_version must be 1")
    if payload.get("quality_judgment") != "PENDING_HUMAN":
        raise ManifestError("manifest must preserve quality_judgment=PENDING_HUMAN")
    clips = payload.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ManifestError("manifest clips must be a non-empty list")
    labels: set[str] = set()
    filenames: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(clips, start=1):
        if not isinstance(raw, dict):
            raise ManifestError(f"clip {index} must be an object")
        label = raw.get("label")
        filename = raw.get("filename")
        recipe = raw.get("recipe")
        if not isinstance(label, str) or not label.strip():
            raise ManifestError(f"clip {index} label must be non-empty")
        if label in labels:
            raise ManifestError(f"duplicate clip label: {label}")
        labels.add(label)
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not filename.endswith(".mp4")
        ):
            raise ManifestError(f"clip {index} filename must be an MP4 basename")
        if filename in filenames:
            raise ManifestError(f"duplicate clip filename: {filename}")
        filenames.add(filename)
        if not isinstance(recipe, str) or not recipe.startswith("h3_music_followup_"):
            raise ManifestError(f"clip {index} recipe is outside the follow-up lane")
        validated.append(
            {
                **raw,
                "label": label,
                "filename": filename,
                "recipe": recipe,
                "sha256": require_sha256(raw.get("sha256"), f"clip {index} sha256"),
                "recipe_sha256": require_sha256(
                    raw.get("recipe_sha256"), f"clip {index} recipe_sha256"
                ),
                "receipt_sha256": require_sha256(
                    raw.get("receipt_sha256"), f"clip {index} receipt_sha256"
                ),
            }
        )
    return validated


def verify_clip(entry: dict[str, Any]) -> dict[str, Any]:
    receipt_path = resolve_relative_under(
        RESULTS, entry.get("receipt_path"), f"{entry['label']} receipt_path"
    )
    if not receipt_path.is_file():
        raise ManifestError(f"missing receipt: {receipt_path}")
    actual_receipt_sha = sha256_file(receipt_path)
    if actual_receipt_sha != entry["receipt_sha256"]:
        raise ManifestError(
            f"receipt SHA drift for {entry['label']}: {actual_receipt_sha}"
        )
    receipt = load_json(receipt_path, "receipt")
    filename = entry["filename"]
    artifact = (OUTPUTS / filename).resolve()
    try:
        artifact.relative_to(OUTPUTS.resolve())
    except ValueError as exc:
        raise ManifestError(f"artifact escapes outputs: {filename}") from exc
    if not artifact.is_file():
        raise ManifestError(f"missing artifact: {artifact}")
    actual_artifact_sha = sha256_file(artifact)
    expected_fields = {
        "receipt_schema_version": 3,
        "recipe": entry["recipe"],
        "recipe_sha256": entry["recipe_sha256"],
        "output_path": filename,
        "artifact_sha256": entry["sha256"],
        "run_number": 1,
        "config_run_count": 1,
        "gate_pass": True,
        "pass": False,
        "warm_pass": False,
        "audio_present": True,
        "valid_measurement": True,
    }
    mismatches = {
        key: {"expected": expected, "actual": receipt.get(key)}
        for key, expected in expected_fields.items()
        if receipt.get(key) != expected
    }
    if receipt.get("status") not in {"PASS (cold)", "PASS (cold, marginal)"}:
        mismatches["status"] = {
            "expected": "cold gate-pass status",
            "actual": receipt.get("status"),
        }
    if actual_artifact_sha != entry["sha256"]:
        mismatches["artifact_file_sha256"] = {
            "expected": entry["sha256"],
            "actual": actual_artifact_sha,
        }
    if receipt.get("artifact_bytes") != artifact.stat().st_size:
        mismatches["artifact_bytes"] = {
            "expected": artifact.stat().st_size,
            "actual": receipt.get("artifact_bytes"),
        }
    if mismatches:
        raise ManifestError(
            f"receipt/artifact binding failed for {entry['label']}: {mismatches}"
        )
    return {
        "receipt_path": str(receipt_path),
        "receipt_sha256": actual_receipt_sha,
        "artifact_path": str(artifact),
        "artifact_sha256": actual_artifact_sha,
        "artifact_bytes": artifact.stat().st_size,
    }


def load_analyzer() -> Any:
    actual = sha256_file(ANALYZER)
    if actual != ANALYZER_SHA256:
        raise ManifestError(f"pinned analyzer SHA drift: {actual} != {ANALYZER_SHA256}")
    spec = importlib.util.spec_from_file_location("_h3_pinned_descriptor_analyzer", ANALYZER)
    if spec is None or spec.loader is None:
        raise ManifestError(f"cannot load analyzer: {ANALYZER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analyze_manifest(manifest_path: Path, result_dir: Path) -> Path:
    manifest_path = manifest_path.resolve()
    manifest = load_json(manifest_path, "manifest")
    clips = validate_manifest_structure(manifest)
    analyzer = load_analyzer()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ManifestError("ffmpeg and ffprobe must already be on PATH")
    evidence = [verify_clip(entry) for entry in clips]
    result_dir = result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for entry, binding in zip(clips, evidence):
        record = analyzer.analyze_clip(
            entry["label"],
            entry["filename"],
            entry["sha256"],
            ffmpeg,
            ffprobe,
            result_dir,
        )
        record["receipt_binding"] = binding
        record["recipe"] = entry["recipe"]
        record["recipe_sha256"] = entry["recipe_sha256"]
        record["quality_judgment"] = "PENDING_HUMAN"
        records.append(record)
    ffmpeg_version, _ = analyzer.run_text([ffmpeg, "-version"])
    ffprobe_version, _ = analyzer.run_text([ffprobe, "-version"])
    payload = {
        "schema_version": 1,
        "kind": "h3-music-followup-machine-descriptors",
        "manifest": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
        },
        "wrapper": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "pinned_analyzer": {
            "path": str(ANALYZER),
            "sha256": ANALYZER_SHA256,
        },
        "python_executable": sys.executable,
        "python_version": sys.version,
        "numpy_version": analyzer.np.__version__,
        "ffmpeg_executable": ffmpeg,
        "ffmpeg_version": ffmpeg_version.splitlines()[0],
        "ffprobe_executable": ffprobe,
        "ffprobe_version": ffprobe_version.splitlines()[0],
        "analysis_command": analyzer.display_command(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                "--manifest",
                str(manifest_path),
                "--result-dir",
                str(result_dir),
            ]
        ),
        "definitions": {
            "spectral_windows": "non-overlapping complete 50 ms windows, Hann-weighted, mono 48 kHz signed 16-bit PCM",
            "spectral_flux": "mean sum of positive binwise changes between consecutive L1-normalized magnitude spectra",
            "periodicity": "largest overlap-energy-normalized autocorrelation coefficient at a 0.25-2.00 s lag after global mean removal",
            "bands_hz": [[low, high] for low, high in analyzer.BANDS_HZ],
            "alignment": "Pearson r across matching complete 0.5 s buckets: mean ffmpeg lavfi.scene_score versus linear mono PCM RMS; first-frame zero sentinel and incomplete terminal bucket excluded",
            "interpretation_limit": "Machine descriptors do not determine music presence, mood, quality, usability, or causation.",
        },
        "records": records,
        "quality_judgment": "PENDING_HUMAN",
    }
    result_path = result_dir / "descriptors.json"
    with result_path.open("xb") as handle:
        handle.write(canonical_json(payload))
    return result_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyze_manifest(args.manifest, args.result_dir)
    print(result)
    print(sha256_file(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
