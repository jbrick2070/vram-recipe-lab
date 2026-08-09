#!/usr/bin/env python3
"""Create a source-audio delivery preview without re-encoding diagnostic video.

The LTX audio-conditioning artifact remains the experiment of record.  This
helper copies that artifact's encoded video stream byte-for-byte into a second
container and muxes the original hash-bound TTS/music/static fixture trimmed to
the experiment window.  A receipt proves elementary-stream equality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import run_recipe
import validate_recipes


REPO_ROOT = Path(__file__).resolve().parent
DELIVERY_RESULTS = run_recipe.RESULTS_DIR / "delivery"


class DeliveryError(RuntimeError):
    pass


class DeliveryLease:
    """Per-recipe exclusive lease preventing concurrent publish/delete races."""

    def __init__(self, recipe_name: str):
        self.path = DELIVERY_RESULTS / f".{recipe_name}.lock"
        self.token = uuid.uuid4().hex
        self.acquired = False

    def __enter__(self) -> "DeliveryLease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("xb") as handle:
                handle.write((self.token + "\n").encode("ascii"))
        except FileExistsError as exc:
            raise DeliveryError(f"Another delivery build owns {self.path.name}") from exc
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if not self.acquired:
            return
        try:
            if self.path.read_text(encoding="ascii").strip() == self.token:
                self.path.unlink()
        finally:
            self.acquired = False


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def elementary_muxer(codec_name: str) -> str:
    """Return the raw FFmpeg muxer used for encoded video-stream hashing."""
    mapping = {"h264": "h264", "hevc": "hevc", "av1": "obu"}
    try:
        return mapping[codec_name]
    except KeyError as exc:
        raise DeliveryError(f"Unsupported video codec for elementary hashing: {codec_name}") from exc


def video_stream_sha256(path: Path, codec_name: str) -> str:
    """Hash a stream-copied elementary video stream, excluding container bytes."""
    command = [
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
        "-c:v", "copy", "-f", elementary_muxer(codec_name), "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    digest = hashlib.sha256()
    for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise DeliveryError(
            f"Could not hash video stream for {path.name}: {stderr.decode('utf-8', errors='replace')}"
        )
    return digest.hexdigest()


def build_mux_command(
    diagnostic: Path,
    source_audio: Path,
    output: Path,
    start_s: float,
    duration_s: float,
) -> list[str]:
    """Build the deterministic source-delivery mux command."""
    return [
        "ffmpeg", "-v", "error", "-n",
        "-i", str(diagnostic),
        "-ss", f"{start_s:.6f}", "-t", f"{duration_s:.6f}", "-i", str(source_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{duration_s:.6f}", "-movflags", "+faststart", str(output),
    ]


def duration_within_one_frame(measured_s: float, target_s: float, fps: float) -> bool:
    return fps > 0 and abs(measured_s - target_s) <= (1.0 / fps) + 1e-9


def atomic_write_json(path: Path, payload: dict[str, Any]) -> bytes:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return encoded


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise DeliveryError(f"UTF-8 BOM is forbidden: {path}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DeliveryError(f"Expected a JSON object: {path}")
    return value, raw


def create_delivery(recipe_name: str) -> Path:
    if not recipe_name or Path(recipe_name).name != recipe_name:
        raise DeliveryError("Recipe must be a basename stem")
    recipe_path = REPO_ROOT / "recipes" / f"{recipe_name}.json"
    current_result_path = run_recipe.RESULTS_DIR / f"{recipe_name}.json"
    if not recipe_path.is_file() or not current_result_path.is_file():
        raise DeliveryError("Recipe and current diagnostic receipt must both exist")
    recipe, recipe_bytes = load_json(recipe_path)
    diagnostic_alias, diagnostic_alias_bytes = load_json(current_result_path)
    experiment = recipe.get("experiment", {})
    contract = recipe.get("contract", {})
    if experiment.get("campaign") != "audio_conditioning_matrix_v1":
        raise DeliveryError(f"Recipe is not an audio-conditioning matrix cell: {recipe_name}")
    if diagnostic_alias.get("recipe") != recipe_name:
        raise DeliveryError("Diagnostic receipt recipe label does not match")
    recipe_sha = run_recipe.sha256_bytes(recipe_bytes)
    if diagnostic_alias.get("receipt_schema_version") != run_recipe.RECEIPT_SCHEMA_VERSION:
        raise DeliveryError("Diagnostic receipt does not use the current schema")
    (
        diagnostic_receipt,
        diagnostic_receipt_path,
        diagnostic_receipt_bytes,
        archive_errors,
    ) = validate_recipes.matching_run_archive(
        diagnostic_alias,
        recipe_path,
        REPO_ROOT,
        run_recipe.RECEIPT_SCHEMA_VERSION,
    )
    if archive_errors:
        raise DeliveryError("Diagnostic receipt/archive binding failed: " + "; ".join(archive_errors))
    if (
        diagnostic_receipt is None
        or diagnostic_receipt_path is None
        or diagnostic_receipt_bytes is None
    ):
        raise DeliveryError("Diagnostic immutable archive could not be loaded")
    if diagnostic_receipt.get("receipt_schema_version") != run_recipe.RECEIPT_SCHEMA_VERSION:
        raise DeliveryError("Diagnostic immutable archive does not use the current schema")
    if diagnostic_receipt.get("recipe_sha256") != recipe_sha:
        raise DeliveryError("Diagnostic receipt does not certify the current recipe bytes")
    if diagnostic_receipt.get("provenance_unchanged") is not True:
        raise DeliveryError("Diagnostic receipt provenance was not stable")
    if diagnostic_receipt.get("gate_pass") is not True:
        raise DeliveryError("Diagnostic render did not pass its machine gate")

    source_name = str(experiment.get("source_fixture") or "")
    if not source_name or Path(source_name).name != source_name:
        raise DeliveryError("Original source fixture must be a basename")
    source_path = run_recipe.FIXTURES_DIR / source_name
    source_sha = str(experiment.get("source_sha256") or "")
    if not source_path.is_file() or run_recipe.sha256_file(source_path) != source_sha:
        raise DeliveryError("Original source fixture is missing or its hash drifted")
    source_receipt_sha = run_recipe.validate_audio_fixture_receipt(source_name)

    diagnostic_rel = str(diagnostic_receipt.get("output_path") or "")
    diagnostic_candidate = Path(diagnostic_rel.replace("\\", "/"))
    if (
        not diagnostic_rel
        or diagnostic_candidate.is_absolute()
        or len(diagnostic_candidate.parts) != 1
    ):
        raise DeliveryError("Diagnostic artifact path must be a basename inside outputs/")
    diagnostic_path = REPO_ROOT / "outputs" / diagnostic_rel
    if not diagnostic_path.is_file():
        raise DeliveryError(f"Diagnostic artifact is missing: {diagnostic_path}")
    diagnostic_sha = run_recipe.sha256_file(diagnostic_path)
    recorded_sha = str(diagnostic_receipt.get("artifact_sha256") or "")
    if not recorded_sha or diagnostic_sha != recorded_sha:
        raise DeliveryError("Diagnostic artifact hash does not match its receipt")

    start_s = float(experiment.get("window_start_s") or 0.0)
    duration_s = float(experiment.get("window_duration_s") or contract.get("duration_s") or 0.0)
    fps = float(contract.get("fps") or 0.0)
    if not all(math.isfinite(value) for value in (start_s, duration_s, fps)):
        raise DeliveryError("Recipe delivery window/fps must be finite")
    if start_s < 0 or duration_s <= 0 or fps <= 0:
        raise DeliveryError("Recipe lacks a positive delivery duration/fps contract")
    source_probe = run_recipe.probe_audio_fixture(source_path)
    if float(source_probe.get("duration_s") or 0.0) + 1e-9 < start_s + duration_s:
        raise DeliveryError("Original source fixture does not cover the requested delivery window")

    output_path = REPO_ROOT / "outputs" / f"{recipe_name}_SOURCE_DELIVERY.mp4"
    receipt_path = DELIVERY_RESULTS / f"{recipe_name}.json"
    temp_output = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex}.tmp.mp4")
    with DeliveryLease(recipe_name):
        if output_path.exists() or receipt_path.exists():
            raise DeliveryError(f"Delivery output or receipt already exists for {recipe_name}")

        diagnostic_metrics = run_recipe.probe_media_metrics(diagnostic_path)
        codec = str(diagnostic_metrics.get("video_codec") or "")
        before_stream_sha = video_stream_sha256(diagnostic_path, codec)
        command = build_mux_command(diagnostic_path, source_path, temp_output, start_s, duration_s)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            temp_output.unlink(missing_ok=True)
            raise DeliveryError(f"FFmpeg source mux failed: {completed.stderr.strip()}")

        try:
            delivery_metrics = run_recipe.probe_media_metrics(temp_output)
            after_stream_sha = video_stream_sha256(temp_output, codec)
            delivered_s = float(delivery_metrics.get("container_duration_s") or 0.0)
            stream_equal = before_stream_sha == after_stream_sha
            duration_ok = duration_within_one_frame(delivered_s, duration_s, fps)
            media_ok = run_recipe.media_artifact_is_valid(
                delivery_metrics,
                contract,
                requires_audio=True,
            )
            passed = stream_equal and duration_ok and media_ok
            if not passed:
                raise DeliveryError("Delivery verification failed before publish")

            final_recipe_sha = run_recipe.sha256_file(recipe_path)
            final_source_sha = run_recipe.sha256_file(source_path)
            final_diagnostic_sha = run_recipe.sha256_file(diagnostic_path)
            final_archive_sha = run_recipe.sha256_file(diagnostic_receipt_path)
            if final_recipe_sha != recipe_sha:
                raise DeliveryError("Recipe bytes changed during delivery build")
            if final_source_sha != source_sha:
                raise DeliveryError("Source fixture changed during delivery build")
            if final_diagnostic_sha != diagnostic_sha:
                raise DeliveryError("Diagnostic artifact changed during delivery build")
            if final_archive_sha != run_recipe.sha256_bytes(diagnostic_receipt_bytes):
                raise DeliveryError("Diagnostic immutable archive changed during delivery build")
            final_source_receipt_sha = run_recipe.validate_audio_fixture_receipt(source_name)
            if final_source_receipt_sha != source_receipt_sha:
                raise DeliveryError("Source ear-gate receipt changed during delivery build")
            final_alias, final_alias_bytes = load_json(current_result_path)
            if final_alias.get("run_number") != diagnostic_alias.get("run_number"):
                raise DeliveryError("Current diagnostic alias advanced during delivery build")
            _, _, _, final_binding_errors = validate_recipes.matching_run_archive(
                final_alias,
                recipe_path,
                REPO_ROOT,
                run_recipe.RECEIPT_SCHEMA_VERSION,
            )
            if final_binding_errors:
                raise DeliveryError(
                    "Final diagnostic receipt/archive binding failed: "
                    + "; ".join(final_binding_errors)
                )
            try:
                os.link(temp_output, output_path)
            except FileExistsError as exc:
                raise DeliveryError(f"Delivery output was published concurrently: {output_path.name}") from exc
            temp_output.unlink()
        except Exception:
            temp_output.unlink(missing_ok=True)
            raise

        try:
            delivered_s = float(delivery_metrics.get("container_duration_s") or 0.0)
            stream_equal = before_stream_sha == after_stream_sha
            duration_ok = duration_within_one_frame(delivered_s, duration_s, fps)
            media_ok = run_recipe.media_artifact_is_valid(
                delivery_metrics,
                contract,
                requires_audio=True,
            )
            passed = stream_equal and duration_ok and media_ok
            payload = {
            "delivery_schema_version": 1,
            "recipe": recipe_name,
            "status": "PASS" if passed else "FAIL",
            "pass": passed,
            "created_at": utc_now(),
            "policy": "source-audio delivery preview; diagnostic artifact remains experiment of record",
            "recipe_sha256": recipe_sha,
            "diagnostic_gate_scope": "cold experimental gate-pass allowed; not a warm certification",
            "diagnostic_current_alias": str(current_result_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "diagnostic_current_alias_sha256": run_recipe.sha256_bytes(final_alias_bytes),
            "diagnostic_receipt": str(diagnostic_receipt_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "diagnostic_receipt_sha256": run_recipe.sha256_bytes(diagnostic_receipt_bytes),
            "diagnostic_artifact": str(diagnostic_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "diagnostic_artifact_sha256": diagnostic_sha,
            "source_fixture": str(source_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "source_fixture_sha256": source_sha,
            "source_ear_receipt_sha256": source_receipt_sha,
            "window_start_s": start_s,
            "target_s": duration_s,
            "delivered_s": delivered_s,
            "container_delivered_s": delivery_metrics.get("container_duration_s"),
            "video_delivered_s": delivery_metrics.get("video_duration_s"),
            "audio_delivered_s": delivery_metrics.get("audio_duration_s"),
            "fps": fps,
            "duration_error_s": round(delivered_s - duration_s, 6),
            "duration_within_one_frame": duration_ok,
            "video_codec": codec,
            "diagnostic_video_elementary_sha256": before_stream_sha,
            "delivery_video_elementary_sha256": after_stream_sha,
            "video_stream_unchanged": stream_equal,
            "ffmpeg_argv": command,
            "output_path": str(output_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "artifact_sha256": run_recipe.sha256_file(output_path),
            **delivery_metrics,
            }
            atomic_write_json(receipt_path, payload)
        except Exception:
            # The published output is retained for forensic inspection; this
            # process never deletes a path it did not exclusively publish.
            raise
    return receipt_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", help="Audio-matrix recipe stem")
    args = parser.parse_args()
    try:
        receipt = create_delivery(args.recipe)
    except DeliveryError as exc:
        print(f"[DELIVERY FAIL] {exc}")
        return 1
    print(f"[DELIVERY PASS] {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
