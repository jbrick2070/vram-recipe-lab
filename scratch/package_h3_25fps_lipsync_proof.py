#!/usr/bin/env python3
"""Package the authorized cold seed-43 H3 render into two 25 fps review clips.

The source model render remains immutable.  Both review copies discard its
joint-latent audio and mux the hash-pinned raw TTS fixture from timestamp zero:

* ``raw`` relabels 192 source frames at 25 fps (7.68 s, intentional drift).
* ``fixed`` nearest-resamples the same 8.00 s content to 200 frames at 25 fps.

This is a local ffmpeg delivery proof, not another model render or a warm
certification.  No judgment is made here; the generated receipt always leaves
human review pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PORTRAIT_FIXTURE = ROOT / "fixtures" / "portrait.png"
PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
TTS_FIXTURE = ROOT / "fixtures" / "tts_dialogue.wav"
TTS_SHA256 = "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
SOURCE_RECIPE = ROOT / "recipes" / "h3_jobd_lipsync_refaudio_seed43_f192.json"
SOURCE_RECIPE_NAME = "h3_jobd_lipsync_refaudio_seed43_f192"
SOURCE_RECIPE_SHA256 = (
    "510bd4e6dc96d635460d65f975652bf15f2862f098de2b7e7f2b6964cce23eb7"
)
SOURCE_RECEIPT_BASENAME = f"{SOURCE_RECIPE_NAME}_run1.json"
SOURCE_ARTIFACT_BASENAME = f"{SOURCE_RECIPE_NAME}_out_00001_.mp4"
SOURCE_BOOT_LANE = (
    "lab-8199, sage-free, manager-offline-test, no-pinned, "
    "cache-classic, reserve-12gb"
)

SOURCE_WIDTH = 832
SOURCE_HEIGHT = 480
SOURCE_FRAMES = 192
SOURCE_FPS = Fraction(24, 1)
RAW_FRAMES = 192
FIXED_FRAMES = 200
DELIVERY_FPS = Fraction(25, 1)
RAW_DURATION_S = Fraction(RAW_FRAMES, DELIVERY_FPS)
FIXED_DURATION_S = Fraction(FIXED_FRAMES, DELIVERY_FPS)

RAW_BASENAME = "h3_ref2va_seed43_raw_192f_at25_drift.mp4"
FIXED_BASENAME = "h3_ref2va_seed43_resampled_200f_at25_fix.mp4"


@dataclass(frozen=True)
class Variant:
    label: str
    frames: int
    duration_s: Fraction
    video_filter: str
    basename: str


VARIANTS = (
    Variant(
        label="raw_192_frames_labeled_25fps_drift",
        frames=RAW_FRAMES,
        duration_s=RAW_DURATION_S,
        video_filter="settb=AVTB,setpts=N/(25*TB)",
        basename=RAW_BASENAME,
    ),
    Variant(
        label="nearest_resample_200_frames_25fps_duration_fix",
        frames=FIXED_FRAMES,
        duration_s=FIXED_DURATION_S,
        video_filter="fps=fps=25:start_time=0:round=near",
        basename=FIXED_BASENAME,
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")


def duration_text(value: Fraction) -> str:
    return f"{float(value):.6f}"


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {variant.label: output_dir / variant.basename for variant in VARIANTS}


def ffmpeg_command(
    source: Path,
    tts: Path,
    output: Path,
    variant: Variant,
    *,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    duration = duration_text(variant.duration_s)
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-n",
        "-i",
        str(source),
        "-i",
        str(tts),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        variant.video_filter,
        "-frames:v",
        str(variant.frames),
        "-r",
        "25",
        "-fps_mode",
        "cfr",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-x264-params",
        "scenecut=0:open-gop=0",
        "-af",
        f"atrim=start=0:end={duration},asetpts=PTS-STARTPTS",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        duration,
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-metadata:s:v:0",
        f"title={variant.label}",
        "-metadata:s:a:0",
        "title=clean_tts_dialogue_from_t0",
        str(output),
    ]


def build_plan(
    source: Path,
    source_receipt: Path,
    output_dir: Path,
    *,
    tts: Path = TTS_FIXTURE,
    ffmpeg: str = "ffmpeg",
) -> dict[str, Any]:
    paths = output_paths(output_dir)
    variants: list[dict[str, Any]] = []
    for variant in VARIANTS:
        row = asdict(variant)
        row["duration_s"] = float(variant.duration_s)
        row["duration_fraction"] = (
            f"{variant.duration_s.numerator}/{variant.duration_s.denominator}"
        )
        row["output"] = str(paths[variant.label])
        row["command"] = ffmpeg_command(
            source, tts, paths[variant.label], variant, ffmpeg=ffmpeg
        )
        variants.append(row)
    return {
        "schema_version": 1,
        "kind": "h3_25fps_lipsync_delivery_proof_plan",
        "source_recipe": str(SOURCE_RECIPE),
        "source_recipe_sha256": SOURCE_RECIPE_SHA256,
        "source_video": str(source),
        "source_run_receipt": str(source_receipt),
        "conditioning_audio": str(tts),
        "conditioning_audio_sha256": TTS_SHA256,
        "source_contract": {
            "width": SOURCE_WIDTH,
            "height": SOURCE_HEIGHT,
            "frames": SOURCE_FRAMES,
            "fps": float(SOURCE_FPS),
            "duration_s": SOURCE_FRAMES / float(SOURCE_FPS),
            "seed": 43,
            "evidence_role": "authorized cold review source only; noncertifying",
            "expected_run_number": 1,
            "expected_gate_pass": True,
            "expected_pass": False,
            "expected_warm_pass": False,
        },
        "delivery_contract": {
            "fps": float(DELIVERY_FPS),
            "raw_frames": RAW_FRAMES,
            "raw_duration_s": float(RAW_DURATION_S),
            "fixed_frames": FIXED_FRAMES,
            "fixed_duration_s": float(FIXED_DURATION_S),
            "fixed_resample_policy": "ffmpeg fps filter, nearest source frame",
            "audio_policy": (
                "discard source audio; mux exact raw tts_dialogue.wav from timestamp zero"
            ),
            "human_review": "PENDING_HUMAN",
            "judgment_policy": "packager makes no lip-sync judgment",
            "certification_status": "NONCERTIFYING_REVIEW_COPIES",
        },
        "variants": variants,
    }


def _run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def ffprobe(path: Path, *, ffprobe_bin: str = "ffprobe") -> dict[str, Any]:
    return _run_json(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )


def _one_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any]:
    streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == codec_type
    ]
    if len(streams) != 1:
        raise RuntimeError(f"expected exactly one {codec_type} stream, found {len(streams)}")
    return streams[0]


def _require_stream_types(
    probe: dict[str, Any], expected: tuple[str, ...], *, label: str
) -> None:
    observed = tuple(
        str(stream.get("codec_type")) for stream in probe.get("streams", [])
    )
    if observed != expected:
        raise RuntimeError(
            f"{label}: expected exact stream types {expected!r}, found {observed!r}"
        )


def _frame_count(stream: dict[str, Any]) -> int:
    value = stream.get("nb_read_frames") or stream.get("nb_frames")
    if value in (None, "N/A"):
        raise RuntimeError("ffprobe did not expose a decoded video frame count")
    return int(value)


def _rate(stream: dict[str, Any]) -> Fraction:
    value = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    if value in (None, "N/A", "0/0"):
        raise RuntimeError("ffprobe did not expose a usable video frame rate")
    return Fraction(value)


def _duration(probe: dict[str, Any], stream: dict[str, Any]) -> float:
    value = stream.get("duration")
    if value in (None, "N/A"):
        value = probe.get("format", {}).get("duration")
    if value in (None, "N/A"):
        raise RuntimeError("ffprobe did not expose a video or container duration")
    return float(value)


def validate_tts_fixture(probe: dict[str, Any]) -> dict[str, Any]:
    _require_stream_types(probe, ("audio",), label="raw TTS fixture")
    audio = _one_stream(probe, "audio")
    if audio.get("codec_name") != "pcm_s16le":
        raise RuntimeError("raw TTS fixture is not signed 16-bit PCM")
    if int(audio.get("sample_rate", 0)) != 44100:
        raise RuntimeError("raw TTS fixture is not 44.1 kHz")
    if int(audio.get("channels", 0)) != 1:
        raise RuntimeError("raw TTS fixture is not mono")
    if int(audio.get("bits_per_sample", 0)) != 16:
        raise RuntimeError("raw TTS fixture is not 16-bit")
    duration = _duration(probe, audio)
    if abs(duration - 10.0) > (1.0 / 44100.0):
        raise RuntimeError(f"raw TTS fixture is not exactly 10.0 s: {duration}")
    return {
        "codec": audio["codec_name"],
        "sample_rate_hz": int(audio["sample_rate"]),
        "channels": int(audio["channels"]),
        "bits_per_sample": int(audio["bits_per_sample"]),
        "duration_s": duration,
    }


def validate_source(source: Path, tts: Path, probe: dict[str, Any]) -> None:
    if sha256_file(PORTRAIT_FIXTURE) != PORTRAIT_SHA256:
        raise RuntimeError("portrait fixture hash drift")
    if sha256_file(tts) != TTS_SHA256:
        raise RuntimeError("raw TTS fixture hash drift")
    if sha256_file(SOURCE_RECIPE) != SOURCE_RECIPE_SHA256:
        raise RuntimeError("seed-43 192-frame source recipe hash drift")
    _require_stream_types(probe, ("video", "audio"), label="source render")
    video = _one_stream(probe, "video")
    audio = _one_stream(probe, "audio")
    if (int(video["width"]), int(video["height"])) != (SOURCE_WIDTH, SOURCE_HEIGHT):
        raise RuntimeError("source video is not 832x480")
    if _frame_count(video) != SOURCE_FRAMES:
        raise RuntimeError("source video does not contain exactly 192 decoded frames")
    if _rate(video) != SOURCE_FPS:
        raise RuntimeError(f"source video is not native 24 fps: {_rate(video)}")
    duration = _duration(probe, video)
    if abs(duration - 8.0) > (1.0 / float(SOURCE_FPS)):
        raise RuntimeError(f"source video duration is not 8.0 s within one frame: {duration}")
    audio_start = float(audio.get("start_time", 0.0))
    if abs(audio_start) > (1.0 / float(SOURCE_FPS)):
        raise RuntimeError(f"source native audio does not begin at t0: {audio_start}")
    audio_duration = _duration(probe, audio)
    if abs(audio_duration - 8.0) > (1.0 / float(SOURCE_FPS)):
        raise RuntimeError(
            "source native audio duration is not 8.0 s within one frame: "
            f"{audio_duration}"
        )
    if not source.is_file():
        raise RuntimeError(f"source video disappeared during validation: {source}")


def validate_source_receipt(source: Path, receipt_path: Path) -> dict[str, Any]:
    expected_source = ROOT / "outputs" / SOURCE_ARTIFACT_BASENAME
    expected_receipt = ROOT / "results" / SOURCE_RECEIPT_BASENAME
    if os.path.normcase(os.path.abspath(source)) != os.path.normcase(
        os.path.abspath(expected_source)
    ):
        raise RuntimeError(
            f"source must be the exact authorized Job-D cold artifact: {expected_source}"
        )
    if os.path.normcase(os.path.abspath(receipt_path)) != os.path.normcase(
        os.path.abspath(expected_receipt)
    ):
        raise RuntimeError(
            f"source receipt must be the exact Job-D run-1 receipt: {expected_receipt}"
        )
    raw = receipt_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError("source run receipt has a UTF-8 BOM")
    receipt = json.loads(raw.decode("utf-8"))
    if receipt.get("recipe") != SOURCE_RECIPE_NAME:
        raise RuntimeError(
            f"source receipt recipe mismatch: {receipt.get('recipe')!r}"
        )
    if receipt.get("recipe_sha256") != SOURCE_RECIPE_SHA256:
        raise RuntimeError("source receipt recipe SHA-256 mismatch")
    source_sha256 = sha256_file(source)
    if receipt.get("artifact_sha256") != source_sha256:
        raise RuntimeError("source receipt artifact SHA-256 mismatch")
    if receipt.get("gate_pass") is not True:
        raise RuntimeError("source run receipt is not a cold machine gate pass")
    if receipt.get("pass") is not False or receipt.get("warm_pass") is not False:
        raise RuntimeError(
            "source must remain a noncertifying cold review run "
            "(pass=false, warm_pass=false)"
        )
    run_number = receipt.get("run_number")
    run_count = receipt.get("run_count")
    config_run_count = receipt.get("config_run_count")
    if run_number != 1 or run_count != 1 or config_run_count != 1:
        raise RuntimeError("source run receipt is not the exact authorized cold run-1")
    boot_lane = receipt.get("boot_lane")
    if boot_lane != SOURCE_BOOT_LANE:
        raise RuntimeError(
            "source run receipt boot lane is not the exact Job-D lane: "
            f"{boot_lane!r}"
        )
    server_argv = receipt.get("server_argv")
    if not isinstance(server_argv, list) or not all(
        isinstance(value, str) for value in server_argv
    ):
        raise RuntimeError("source run receipt has no valid server_argv")
    if "--disable-pinned-memory" not in server_argv:
        raise RuntimeError("source server argv lacks --disable-pinned-memory")
    if "--cache-classic" not in server_argv:
        raise RuntimeError("source server argv lacks --cache-classic")
    if "--use-sage-attention" in server_argv:
        raise RuntimeError("source server argv is not SageAttention-free")
    port_positions = [
        index for index, value in enumerate(server_argv) if value == "--port"
    ]
    if (
        len(port_positions) != 1
        or port_positions[0] + 1 >= len(server_argv)
        or server_argv[port_positions[0] + 1] != "8199"
    ):
        raise RuntimeError("source server argv is not bound to lab port 8199")
    reserve_positions = [
        index for index, value in enumerate(server_argv) if value == "--reserve-vram"
    ]
    if len(reserve_positions) != 1 or reserve_positions[0] + 1 >= len(server_argv):
        raise RuntimeError("source server argv lacks one exact --reserve-vram value")
    try:
        reserve_vram = float(server_argv[reserve_positions[0] + 1])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("source server argv has an invalid --reserve-vram value") from exc
    if reserve_vram != 12.0:
        raise RuntimeError(
            f"source server argv is not reserve-12gb: {reserve_vram!r}"
        )
    fixtures = receipt.get("fixture_sha256s")
    expected_fixtures = {
        "portrait.png": PORTRAIT_SHA256,
        "tts_dialogue.wav": TTS_SHA256,
    }
    if fixtures != expected_fixtures:
        raise RuntimeError("source receipt does not bind the exact portrait + TTS fixtures")
    expected_media = {
        "encoded_width": SOURCE_WIDTH,
        "encoded_height": SOURCE_HEIGHT,
        "encoded_frame_count": SOURCE_FRAMES,
        "encoded_fps": float(SOURCE_FPS),
        "audio_present": True,
    }
    for key, expected in expected_media.items():
        if receipt.get(key) != expected:
            raise RuntimeError(
                f"source receipt media contract mismatch for {key}: "
                f"{receipt.get(key)!r}"
            )
    receipt_audio_duration = receipt.get("audio_duration_s")
    if not isinstance(receipt_audio_duration, (int, float)) or abs(
        float(receipt_audio_duration) - 8.0
    ) > (1.0 / float(SOURCE_FPS)):
        raise RuntimeError("source receipt does not prove 8.0 s native audio")
    manager_probe = receipt.get("manager_offline_probe")
    pre_queue = (
        manager_probe.get("pre_queue") if isinstance(manager_probe, dict) else None
    )
    if not isinstance(pre_queue, dict):
        raise RuntimeError("source receipt lacks the Manager pre-queue offline proof")
    mode = pre_queue.get("log_scan", {}).get(
        "authoritative_server_reported_mode", {}
    )
    if (
        pre_queue.get("valid") is not True
        or pre_queue.get("verified_before_this_prompt") is not True
        or pre_queue.get("require_no_prior_prompt") is not True
        or mode.get("resolved_mode") != "offline"
        or mode.get("mode_precedes_first_execution") is not True
    ):
        raise RuntimeError(
            "source receipt does not prove network_mode: offline before its prompt"
        )
    output_path = receipt.get("output_path")
    if output_path != SOURCE_ARTIFACT_BASENAME:
        raise RuntimeError("source run receipt does not name the exact run-1 artifact")
    if receipt.get("artifact_bytes") != source.stat().st_size:
        raise RuntimeError("source receipt artifact byte count mismatch")
    recorded_relative = Path(output_path.replace("\\", "/"))
    if (
        recorded_relative.is_absolute()
        or not recorded_relative.parts
        or any(part in {".", ".."} for part in recorded_relative.parts)
    ):
        raise RuntimeError("source receipt output_path is not contained in outputs/")
    outputs_root = (ROOT / "outputs").resolve()
    recorded = (outputs_root / recorded_relative).resolve()
    try:
        recorded.relative_to(outputs_root)
    except ValueError as exc:
        raise RuntimeError(
            "source receipt output_path escapes the lab outputs directory"
        ) from exc
    if recorded != source.resolve():
        raise RuntimeError(
            f"source path does not match receipt output_path: {recorded}"
        )
    return {
        "path": str(receipt_path),
        "sha256": sha256_file(receipt_path),
        "recipe": receipt["recipe"],
        "recipe_sha256": receipt["recipe_sha256"],
        "artifact_sha256": receipt["artifact_sha256"],
        "gate_pass": receipt["gate_pass"],
        "pass": receipt["pass"],
        "boot_lane": boot_lane,
        "server_argv": server_argv,
        "run_number": run_number,
        "run_count": run_count,
        "config_run_count": config_run_count,
        "warm_pass": receipt.get("warm_pass"),
        "fixture_sha256s": fixtures,
        "manager_offline_pre_queue": pre_queue,
    }


def validate_output(probe: dict[str, Any], variant: Variant) -> dict[str, Any]:
    _require_stream_types(probe, ("video", "audio"), label=variant.label)
    video = _one_stream(probe, "video")
    audio = _one_stream(probe, "audio")
    frames = _frame_count(video)
    rate = _rate(video)
    duration = _duration(probe, video)
    expected_duration = float(variant.duration_s)
    if (int(video["width"]), int(video["height"])) != (SOURCE_WIDTH, SOURCE_HEIGHT):
        raise RuntimeError(f"{variant.label}: output canvas drift")
    if frames != variant.frames:
        raise RuntimeError(
            f"{variant.label}: expected {variant.frames} frames, found {frames}"
        )
    if rate != DELIVERY_FPS:
        raise RuntimeError(f"{variant.label}: expected 25 fps, found {rate}")
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise RuntimeError(f"{variant.label}: video is not H.264 yuv420p")
    if abs(duration - expected_duration) > (1.0 / float(DELIVERY_FPS)):
        raise RuntimeError(
            f"{variant.label}: duration {duration} exceeds one-frame tolerance"
        )
    audio_start = float(audio.get("start_time", 0.0))
    if abs(audio_start) > (1.0 / float(DELIVERY_FPS)):
        raise RuntimeError(
            f"{variant.label}: audio does not start at t0 within one frame: {audio_start}"
        )
    audio_duration_value = audio.get("duration")
    if audio_duration_value in (None, "N/A"):
        raise RuntimeError(f"{variant.label}: audio stream duration is unavailable")
    audio_duration = float(audio_duration_value)
    if abs(audio_duration - expected_duration) > (1.0 / float(DELIVERY_FPS)):
        raise RuntimeError(
            f"{variant.label}: audio duration {audio_duration} exceeds one-frame tolerance"
        )
    if audio.get("codec_name") != "aac":
        raise RuntimeError(f"{variant.label}: audio is not AAC")
    if int(audio.get("sample_rate", 0)) != 48000 or int(
        audio.get("channels", 0)
    ) != 2:
        raise RuntimeError(f"{variant.label}: audio is not 48 kHz stereo")
    container_duration_value = probe.get("format", {}).get("duration")
    if container_duration_value in (None, "N/A"):
        raise RuntimeError(f"{variant.label}: container duration is unavailable")
    container_duration = float(container_duration_value)
    if abs(container_duration - expected_duration) > (1.0 / float(DELIVERY_FPS)):
        raise RuntimeError(
            f"{variant.label}: container duration {container_duration} exceeds "
            "one-frame tolerance"
        )
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "frames": frames,
        "fps": float(rate),
        "duration_s": duration,
        "audio_duration_s": audio_duration,
        "audio_codec": audio.get("codec_name"),
        "audio_sample_rate_hz": int(audio["sample_rate"]),
        "audio_channels": int(audio["channels"]),
        "audio_start_time_s": audio_start,
        "container_duration_s": container_duration,
    }


def immutable_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise RuntimeError(f"refusing to replace existing receipt: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def package(
    source: Path,
    source_receipt: Path,
    output_dir: Path,
    receipt: Path,
    *,
    tts: Path = TTS_FIXTURE,
    ffmpeg: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> dict[str, Any]:
    source = source.resolve()
    source_receipt = source_receipt.resolve()
    tts = tts.resolve()
    output_dir = output_dir.resolve()
    receipt = receipt.resolve()
    if not source.is_file():
        raise RuntimeError(f"source render is missing: {source}")
    if not tts.is_file():
        raise RuntimeError(f"TTS fixture is missing: {tts}")
    if not source_receipt.is_file():
        raise RuntimeError(f"source run receipt is missing: {source_receipt}")
    if receipt.exists():
        raise RuntimeError(f"refusing to replace existing receipt: {receipt}")

    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing:
        raise RuntimeError(f"refusing to replace existing review output: {existing}")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_probe = ffprobe(source, ffprobe_bin=ffprobe_bin)
    tts_probe = ffprobe(tts, ffprobe_bin=ffprobe_bin)
    validate_source(source, tts, source_probe)
    tts_probe_evidence = validate_tts_fixture(tts_probe)
    source_receipt_evidence = validate_source_receipt(source, source_receipt)
    plan = build_plan(
        source, source_receipt, output_dir, tts=tts, ffmpeg=ffmpeg
    )
    output_rows: list[dict[str, Any]] = []
    try:
        for variant, row in zip(VARIANTS, plan["variants"]):
            command = row["command"]
            subprocess.run(command, check=True)
            output = Path(row["output"])
            probe = ffprobe(output, ffprobe_bin=ffprobe_bin)
            verified = validate_output(probe, variant)
            output_rows.append(
                {
                    "label": variant.label,
                    "path": str(output),
                    "sha256": sha256_file(output),
                    "ffprobe": verified,
                    "command": command,
                }
            )
    except Exception:
        for path in paths.values():
            if path.exists():
                path.unlink()
        raise

    ffmpeg_version = subprocess.run(
        [ffmpeg, "-version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()[0]
    payload = {
        "schema_version": 1,
        "kind": "h3_25fps_lipsync_delivery_proof_receipt",
        "measurement_status": "NOT_A_MODEL_MEASUREMENT",
        "evidence_scope": (
            "local deterministic delivery transform; model measurements come only "
            "from the hash-bound run_recipe receipt"
        ),
        "plan": plan,
        "source_video_sha256": sha256_file(source),
        "source_run_receipt": source_receipt_evidence,
        "source_probe": {
            "width": SOURCE_WIDTH,
            "height": SOURCE_HEIGHT,
            "frames": SOURCE_FRAMES,
            "fps": float(SOURCE_FPS),
            "duration_s": _duration(source_probe, _one_stream(source_probe, "video")),
            "container_duration_s": float(source_probe["format"]["duration"]),
        },
        "conditioning_audio_sha256": sha256_file(tts),
        "conditioning_audio_probe": tts_probe_evidence,
        "packager_sha256": sha256_file(Path(__file__).resolve()),
        "ffmpeg_version": ffmpeg_version,
        "outputs": output_rows,
        "human_review": "PENDING_HUMAN",
        "judgment": None,
    }
    immutable_write(receipt, canonical_json_bytes(payload))
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="native 832x480x192 H3 mp4")
    parser.add_argument(
        "--source-receipt",
        type=Path,
        required=True,
        help="run_recipe immutable receipt that hash-binds the source mp4",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs", help="review output directory"
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "results" / "comparisons" / "h3_25fps_lipsync_proof.json",
    )
    parser.add_argument("--tts", type=Path, default=TTS_FIXTURE)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the deterministic plan without reading media or writing files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        plan = build_plan(
            args.source.resolve(),
            args.source_receipt.resolve(),
            args.output_dir.resolve(),
            tts=args.tts.resolve(),
            ffmpeg=args.ffmpeg,
        )
        sys.stdout.buffer.write(canonical_json_bytes(plan))
        return 0
    package(
        args.source,
        args.source_receipt,
        args.output_dir,
        args.receipt,
        tts=args.tts,
        ffmpeg=args.ffmpeg,
        ffprobe_bin=args.ffprobe,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
