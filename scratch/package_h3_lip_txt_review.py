#!/usr/bin/env python3
"""Create source-window review copies for the completed H3-LIP-TXT A/B.

Measured artifacts and run receipts remain untouched.  This offline packager
stream-copies each measured video stream and muxes only the exact, sample-bound
window from the immutable source WAV for Jeffrey's eyes and ears.  It is not a
render and never boots or queries ComfyUI.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import os
import subprocess
import sys
import uuid
import wave
from pathlib import Path
from typing import Any, Iterator

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mux_source_delivery
import run_recipe

from scratch import build_h3_lip_txt_campaign as candidates
from scratch import h3_lip_txt_common as common
from scratch import h3_lip_txt_window as window


REVIEW_SCHEMA_VERSION = 1
REVIEW_RECEIPT = common.RESULTS / "comparisons" / "h3_lip_txt_review_package.json"
DEFAULT_OUTPUT_DIR = common.OUTPUTS / "h3_lip_txt_review"
ROLE_SPECS = {
    ("native", 42): common.CONTROL_RECIPE_NAME,
    ("native", 43): candidates.SEED43_CONTROL_RECIPE_NAME,
    ("transcript_aware", 42): candidates.CANDIDATE_NAME_BY_SEED[42],
    ("transcript_aware", 43): candidates.CANDIDATE_NAME_BY_SEED[43],
}
BUNDLE_FIELDS = (
    "runner_sha256",
    "comfyui_git_commit",
    "server_argv",
    "model_fingerprints",
    "lab_locks_sha256",
)


class ReviewError(common.H3LipTxtError):
    """A review delivery would not faithfully bind a measured H3-LIP-TXT run."""


class ReviewLease:
    """A small local lease to prevent two review publishers sharing output names."""

    def __init__(self, receipt_path: Path):
        self.path = receipt_path.with_name(f".{receipt_path.stem}.lock")
        self.token = uuid.uuid4().hex
        self.acquired = False

    def __enter__(self) -> "ReviewLease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("xb") as handle:
                handle.write((self.token + "\n").encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise ReviewError(f"Another review package owns {self.path.name}") from exc
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


def _path_arg(value: str) -> Path:
    return Path(value).resolve()


def _receipt_archive(path: Path, expected_recipe: str) -> tuple[dict[str, Any], bytes]:
    receipt, raw = common.load_json_object(path)
    try:
        relative = path.resolve().relative_to(common.RESULTS.resolve())
    except ValueError as exc:
        raise ReviewError("Run receipt must be under results/") from exc
    run_number = receipt.get("run_number")
    if (
        receipt.get("recipe") != expected_recipe
        or isinstance(run_number, bool)
        or not isinstance(run_number, int)
        or run_number < 1
        or relative.parent != Path(".")
        or relative.name != f"{expected_recipe}_run{run_number}.json"
    ):
        raise ReviewError(
            f"Review input must be an immutable {expected_recipe}_runN archive"
        )
    return receipt, raw


def _recipe_for_receipt(receipt: dict[str, Any]) -> tuple[dict[str, Any], Path, bytes]:
    recipe_name = receipt["recipe"]
    recipe_path = common.RECIPES / f"{recipe_name}.json"
    recipe, raw = common.load_json_object(recipe_path)
    if common.sha256_bytes(raw) != receipt.get("recipe_sha256"):
        raise ReviewError(f"Run receipt recipe SHA drifted: {recipe_name}")
    if recipe.get("name") != recipe_name:
        raise ReviewError(f"Recipe identity drifted: {recipe_name}")
    return recipe, recipe_path, raw


def _artifact_for_receipt(receipt: dict[str, Any]) -> Path:
    output_name = receipt.get("output_path")
    if not isinstance(output_name, str) or Path(output_name).name != output_name:
        raise ReviewError("Run receipt has an unsafe output artifact name")
    artifact = common.OUTPUTS / output_name
    if not artifact.is_file():
        raise ReviewError(f"Measured artifact is missing: {artifact}")
    if common.sha256_file(artifact) != receipt.get("artifact_sha256"):
        raise ReviewError(f"Measured artifact hash drifted: {artifact.name}")
    return artifact


def _expected_control(seed: int) -> tuple[Path, str]:
    try:
        return candidates.CONTROL_BY_SEED[seed]
    except KeyError as exc:
        raise ReviewError(f"Unsupported control seed: {seed}") from exc


def load_take(
    role: str,
    seed: int,
    receipt_path: Path,
    transcript_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Validate one immutable machine run before it can receive a review mux."""
    try:
        expected_recipe = ROLE_SPECS[(role, seed)]
    except KeyError as exc:
        raise ReviewError(f"Unsupported review role/seed: {role}/{seed}") from exc
    receipt, receipt_raw = _receipt_archive(receipt_path, expected_recipe)
    recipe, recipe_path, recipe_raw = _recipe_for_receipt(receipt)
    artifact = _artifact_for_receipt(receipt)
    if receipt.get("gate_pass") is not True or receipt.get("provenance_unchanged") is not True:
        raise ReviewError(f"Take did not pass immutable machine/provenance gates: {expected_recipe}")
    if "sage-free" not in str(receipt.get("boot_lane") or ""):
        raise ReviewError(f"Take did not run Sage-free: {expected_recipe}")
    if receipt.get("fixture_sha256s") != {
        "portrait.png": common.PORTRAIT_SHA256,
        "tts_dialogue.wav": common.SOURCE_AUDIO_SHA256,
    }:
        raise ReviewError(f"Take fixture binding drifted: {expected_recipe}")
    if recipe.get("contract", {}).get("frames") != common.TARGET_FRAMES or recipe.get("contract", {}).get("fps") != common.TARGET_FPS:
        raise ReviewError(f"Take timing contract drifted: {expected_recipe}")
    if recipe.get("prompt", {}).get("5", {}).get("inputs", {}).get("noise_seed") != seed:
        raise ReviewError(f"Take seed drifted: {expected_recipe}")
    metrics = run_recipe.probe_media_metrics(artifact)
    if not run_recipe.media_artifact_is_valid(
        metrics, recipe["contract"], requires_audio=True
    ):
        raise ReviewError(f"Measured artifact no longer passes exact media gates: {artifact.name}")
    if role == "native":
        control_path, control_sha = _expected_control(seed)
        if recipe_path != control_path or common.sha256_bytes(recipe_raw) != control_sha:
            raise ReviewError(f"Native take is not the hash-pinned seed-{seed} control")
        if seed == 43 and receipt["run_number"] < 2:
            raise ReviewError(
                "Native seed-43 run1 is historical orientation evidence; run a fresh _run2 or later"
            )
    else:
        control, _, _ = candidates._load_hash_pinned_control(seed)
        candidates.validate_candidate(recipe, control, transcript_receipt)
    return {
        "role": role,
        "seed": seed,
        "recipe": expected_recipe,
        "recipe_path": common.repo_relative(recipe_path),
        "recipe_sha256": common.sha256_bytes(recipe_raw),
        "run_receipt": common.repo_relative(receipt_path),
        "run_receipt_sha256": common.sha256_bytes(receipt_raw),
        "receipt": receipt,
        "artifact": artifact,
        "artifact_sha256": common.sha256_file(artifact),
        "media_metrics": metrics,
    }


def _receipt_time(receipt: dict[str, Any], recipe: str) -> dt.datetime:
    value = receipt.get("timestamp")
    if not isinstance(value, str) or not value:
        raise ReviewError(f"Freshness timestamp is missing: {recipe}")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewError(f"Freshness timestamp is invalid: {recipe}") from exc
    if parsed.tzinfo is None:
        raise ReviewError(f"Freshness timestamp lacks an offset: {recipe}")
    return parsed.astimezone(dt.timezone.utc)


def validate_shared_runner_bundle(
    takes: list[dict[str, Any]], transcript_receipt: dict[str, Any]
) -> dict[str, Any]:
    native42 = next(
        take for take in takes if take["role"] == "native" and take["seed"] == 42
    )
    bound_control = transcript_receipt["fresh_native_control"]
    if (
        native42["run_receipt"] != bound_control["receipt"]
        or native42["run_receipt_sha256"] != bound_control["receipt_sha256"]
        or native42["artifact_sha256"] != bound_control["artifact_sha256"]
    ):
        raise ReviewError(
            "Native seed-42 review take is not the fresh control bound by the transcript receipt"
        )
    baseline = native42["receipt"]
    baseline_time = _receipt_time(baseline, native42["recipe"])
    for take in takes:
        receipt = take["receipt"]
        mismatches = [
            field
            for field in BUNDLE_FIELDS
            if receipt.get(field) != baseline.get(field)
        ]
        if mismatches:
            raise ReviewError(
                f"Runner bundle differs from fresh native seed42 for {take['recipe']}: {mismatches}"
            )
        if take is not native42 and _receipt_time(receipt, take["recipe"]) < baseline_time:
            raise ReviewError(
                f"Take predates the fresh native seed42 control: {take['recipe']}"
            )
    return {field: copy.deepcopy(baseline.get(field)) for field in BUNDLE_FIELDS}


def extract_source_window(
    start_sample: int, end_sample: int, output_path: Path
) -> tuple[str, list[str]]:
    """Make one lossless, sample-exact WAV derived from the full immutable fixture."""
    if end_sample != start_sample + common.TARGET_SAMPLES:
        raise ReviewError("Review source window does not match exact target sample span")
    try:
        with wave.open(str(common.SOURCE_AUDIO), "rb") as source_wave:
            observed = {
                "channels": source_wave.getnchannels(),
                "sample_width_bytes": source_wave.getsampwidth(),
                "sample_rate_hz": source_wave.getframerate(),
                "frames": source_wave.getnframes(),
                "compression": source_wave.getcomptype(),
            }
    except (OSError, wave.Error) as exc:
        raise ReviewError("Could not verify review source WAV") from exc
    expected = {
        "channels": 1,
        "sample_width_bytes": 2,
        "sample_rate_hz": common.SAMPLE_RATE_HZ,
        "frames": common.SOURCE_SAMPLES,
        "compression": "NONE",
    }
    if observed != expected or common.sha256_file(common.SOURCE_AUDIO) != common.SOURCE_AUDIO_SHA256:
        raise ReviewError("Review source WAV bytes or contract drifted")
    temporary = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp.wav"
    )
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-n",
        "-i",
        str(common.SOURCE_AUDIO),
        "-af",
        f"atrim=start_sample={start_sample}:end_sample={end_sample},asetpts=PTS-STARTPTS",
        "-c:a",
        "pcm_s16le",
        str(temporary),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ReviewError(f"Could not extract exact source window: {completed.stderr.strip()}")
        try:
            with wave.open(str(temporary), "rb") as source_window:
                observed = {
                    "channels": source_window.getnchannels(),
                    "sample_width_bytes": source_window.getsampwidth(),
                    "sample_rate_hz": source_window.getframerate(),
                    "frames": source_window.getnframes(),
                    "compression": source_window.getcomptype(),
                }
        except (OSError, wave.Error) as exc:
            raise ReviewError("Could not validate extracted source-window WAV") from exc
        expected = {
            "channels": 1,
            "sample_width_bytes": 2,
            "sample_rate_hz": common.SAMPLE_RATE_HZ,
            "frames": common.TARGET_SAMPLES,
            "compression": "NONE",
        }
        if observed != expected:
            raise ReviewError(f"Extracted source-window contract drifted: {observed!r}")
        payload = temporary.read_bytes()
        common.write_immutable(output_path, payload)
    finally:
        temporary.unlink(missing_ok=True)
    return common.sha256_file(output_path), command


def build_mux_command(video: Path, source_window: Path, output: Path) -> list[str]:
    """Build a lossless c:v-copy MOV review mux with an exact PCM source track."""
    duration_s = common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ
    return [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-n",
        "-i",
        str(video),
        "-i",
        str(source_window),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "pcm_s16le",
        "-t",
        f"{duration_s:.9f}",
        str(output),
    ]


def _publish_review_take(take: dict[str, Any], source_window: Path, output: Path) -> dict[str, Any]:
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp.mov")
    artifact = take["artifact"]
    metrics_before = take["media_metrics"]
    codec = str(metrics_before.get("video_codec") or "")
    if not codec:
        raise ReviewError(f"Measured artifact has no video codec: {artifact.name}")
    before_video_sha = mux_source_delivery.video_stream_sha256(artifact, codec)
    command = build_mux_command(artifact, source_window, temporary)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ReviewError(f"Review mux failed for {artifact.name}: {completed.stderr.strip()}")
        metrics_after = run_recipe.probe_media_metrics(temporary)
        after_video_sha = mux_source_delivery.video_stream_sha256(temporary, codec)
        exact_duration = common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ
        duration_ok = all(
            mux_source_delivery.duration_within_one_frame(
                float(metrics_after.get(field) or 0.0), exact_duration, common.TARGET_FPS
            )
            for field in ("container_duration_s", "video_duration_s", "audio_duration_s")
        )
        recipe, _, _ = _recipe_for_receipt(take["receipt"])
        media_ok = run_recipe.media_artifact_is_valid(
            metrics_after, recipe["contract"], requires_audio=True
        )
        if before_video_sha != after_video_sha or not duration_ok or not media_ok:
            raise ReviewError(f"Review copy verification failed for {artifact.name}")
        common.write_immutable(output, temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "role": take["role"],
        "seed": take["seed"],
        "recipe": take["recipe"],
        "recipe_sha256": take["recipe_sha256"],
        "machine_run_receipt": take["run_receipt"],
        "machine_run_receipt_sha256": take["run_receipt_sha256"],
        "machine_artifact": common.repo_relative(artifact),
        "machine_artifact_sha256": take["artifact_sha256"],
        "review_artifact": common.repo_relative(output),
        "review_artifact_sha256": common.sha256_file(output),
        "review_audio_policy": (
            "The exact sample-window source WAV is muxed as lossless pcm_s16le; "
            "the measured H3 artifact and receipt remain unchanged."
        ),
        "ffmpeg_argv": command,
        "video_codec": codec,
        "machine_video_elementary_sha256": before_video_sha,
        "review_video_elementary_sha256": after_video_sha,
        "video_stream_unchanged": before_video_sha == after_video_sha,
        "duration_target_s": common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ,
        "duration_within_one_frame": duration_ok,
        "media_contract_valid": media_ok,
        "media_metrics": metrics_after,
    }


def _take_paths_from_args(args: argparse.Namespace) -> Iterator[tuple[str, int, Path]]:
    yield "native", 42, args.native_seed42_receipt
    yield "native", 43, args.native_seed43_receipt
    yield "transcript_aware", 42, args.transcript_seed42_receipt
    yield "transcript_aware", 43, args.transcript_seed43_receipt


def package_review(
    *,
    transcript_receipt_path: Path,
    take_paths: list[tuple[str, int, Path]],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    package_receipt: Path = REVIEW_RECEIPT,
) -> Path:
    """Build and append-only publish all four review copies plus one package receipt."""
    if package_receipt.exists():
        raise ReviewError(f"Review package receipt already exists: {package_receipt}")
    transcript_receipt = window.validate_transcript_receipt(transcript_receipt_path)
    expected_roles = set(ROLE_SPECS)
    seen_roles = {(role, seed) for role, seed, _ in take_paths}
    if seen_roles != expected_roles or len(take_paths) != len(expected_roles):
        raise ReviewError("Review package requires exactly native/transcript-aware takes for seeds 42 and 43")
    takes = [
        load_take(role, seed, receipt_path, transcript_receipt)
        for role, seed, receipt_path in take_paths
    ]
    bundle = validate_shared_runner_bundle(takes, transcript_receipt)
    aligned = transcript_receipt["aligned_source_window"]
    start_sample = int(aligned["start_sample"])
    end_sample = int(aligned["end_sample"])
    output_dir.mkdir(parents=True, exist_ok=True)
    source_window = output_dir / "tts_dialogue_h3_aligned_source_window.wav"
    with ReviewLease(package_receipt):
        if package_receipt.exists():
            raise ReviewError(f"Review package receipt already exists: {package_receipt}")
        source_window_sha, source_extract_command = extract_source_window(
            start_sample, end_sample, source_window
        )
        delivery_takes: list[dict[str, Any]] = []
        for take in sorted(takes, key=lambda item: (item["role"], item["seed"])):
            output = output_dir / f"{take['role']}_seed{take['seed']}_source_window.mov"
            delivery_takes.append(_publish_review_take(take, source_window, output))
        payload = {
            "review_package_schema_version": REVIEW_SCHEMA_VERSION,
            "campaign": "H3-LIP-TXT",
            "status": "READY_FOR_HUMAN_REVIEW_NO_RATING",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "policy": (
                "Four source-window review copies only. No score, preference, or promotion "
                "claim is made here; both seeds must later be judged noninferior or better."
            ),
            "transcript_window_receipt": transcript_receipt["receipt_path"],
            "transcript_window_receipt_sha256": transcript_receipt["receipt_sha256"],
            "source_fixture": "fixtures/tts_dialogue.wav",
            "source_fixture_sha256": common.SOURCE_AUDIO_SHA256,
            "source_window": {
                "artifact": common.repo_relative(source_window),
                "artifact_sha256": source_window_sha,
                "extract_ffmpeg_argv": source_extract_command,
                "start_sample": start_sample,
                "end_sample": end_sample,
                "sample_rate_hz": common.SAMPLE_RATE_HZ,
                "duration_samples": common.TARGET_SAMPLES,
                "duration_s": common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ,
            },
            "shared_runner_bundle": bundle,
            "takes": delivery_takes,
        }
        # Recheck inputs immediately before the append-only receipt is committed.
        for take in takes:
            if common.sha256_file(take["artifact"]) != take["artifact_sha256"]:
                raise ReviewError(f"Measured artifact changed during review packaging: {take['artifact'].name}")
            receipt_path = common.repo_path(take["run_receipt"])
            if common.sha256_file(receipt_path) != take["run_receipt_sha256"]:
                raise ReviewError(f"Machine receipt changed during review packaging: {receipt_path.name}")
        if common.sha256_file(common.SOURCE_AUDIO) != common.SOURCE_AUDIO_SHA256:
            raise ReviewError("Review source WAV changed during packaging")
        common.write_immutable_json(package_receipt, payload)
    return package_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript-receipt", type=_path_arg, default=common.TRANSCRIPT_RECEIPT)
    parser.add_argument("--native-seed42-receipt", type=_path_arg, required=True)
    parser.add_argument("--native-seed43-receipt", type=_path_arg, required=True)
    parser.add_argument("--transcript-seed42-receipt", type=_path_arg, required=True)
    parser.add_argument("--transcript-seed43-receipt", type=_path_arg, required=True)
    parser.add_argument("--output-dir", type=_path_arg, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--package-receipt", type=_path_arg, default=REVIEW_RECEIPT)
    args = parser.parse_args()
    try:
        result = package_review(
            transcript_receipt_path=args.transcript_receipt,
            take_paths=list(_take_paths_from_args(args)),
            output_dir=args.output_dir,
            package_receipt=args.package_receipt,
        )
    except common.H3LipTxtError as exc:
        print(f"[H3-LIP-TXT REVIEW FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[READY FOR REVIEW] {common.repo_relative(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
