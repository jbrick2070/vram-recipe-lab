#!/usr/bin/env python3
"""Analyze and certify the H3-LIP-TXT source-audio window.

This is deliberately offline.  It decodes an already-rendered native H3 audio
stream and scans every legal start sample inside ``tts_dialogue.wav``.  It does
not boot ComfyUI, submit a prompt, change a recipe, or infer a transcript.

Two independent, full-file representations must agree before a human may bind
verbatim text to the selected window:

* 80--7500 Hz sample-level normalized correlation;
* 20 ms log-RMS envelope normalized correlation.

Weak, tied, or disagreeing results are published as ``AMBIGUOUS_STOP`` and do
not unlock candidate recipe generation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
import unicodedata
import wave
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy import __version__ as SCIPY_VERSION
from scipy import signal

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scratch import h3_lip_txt_common as common


ANALYSIS_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 1
KIND = "h3_lip_txt_transcript_window"
SPEECH_BAND_HZ = (80.0, 7500.0)
ENVELOPE_FRAME_SAMPLES = 882  # 20 ms at 44.1 kHz
PEAK_SEPARATION_SAMPLES = common.SAMPLE_RATE_HZ // 2
METHOD_AGREEMENT_SAMPLES = int(0.040 * common.SAMPLE_RATE_HZ)
MIN_TOP_SCORE = 0.05
MIN_PEAK_MARGIN = 0.05
ROBUST_MAD_MULTIPLIER = 6.0
BLOCK_SAMPLES = common.SAMPLE_RATE_HZ // 2
MIN_BLOCK_SCORE = 0.05
MIN_DISTRIBUTED_BLOCKS = 3


class WindowError(common.H3LipTxtError):
    """A source-window analysis or receipt violation."""


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(command), capture_output=True, check=False, timeout=180
        )
    except OSError as exc:
        raise WindowError(f"Could not execute {command[0]!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise WindowError(f"Timed out decoding audio with {command[0]!r}") from exc
    if completed.returncode != 0:
        raise WindowError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed


def ffmpeg_version() -> str:
    completed = _run(["ffmpeg", "-version"])
    return completed.stdout.decode("utf-8", errors="replace").splitlines()[0]


def probe_native_audio_stream(path: Path) -> dict[str, Any]:
    """Bind the decode origin to native stream presentation-time metadata."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,start_time,duration,time_base,nb_frames:format=duration,start_time",
        "-of",
        "json",
        str(path),
    ]
    completed = _run(command)
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WindowError("ffprobe emitted invalid native-audio metadata") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise WindowError("Fresh control must expose exactly one selected native audio stream")
    stream = streams[0]
    try:
        start_s = float(stream.get("start_time"))
        duration_s = float(stream.get("duration"))
    except (TypeError, ValueError) as exc:
        raise WindowError("Fresh control native-audio stream lacks numeric timing metadata") from exc
    if not math.isfinite(start_s) or abs(start_s) > 1e-6:
        raise WindowError(
            "Fresh control native audio does not start at timestamp zero; "
            "do not infer a sample-zero lip-sync origin"
        )
    if not math.isfinite(duration_s) or duration_s + 1e-9 < (
        common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ
    ):
        raise WindowError("Fresh control native audio is shorter than the target span")
    return {"ffprobe_argv": command, "stream": stream, "format": payload.get("format")}


def decode_f32le(
    path: Path, *, trim_samples: int | None = None
) -> tuple[np.ndarray, list[str]]:
    """Decode first audio stream as mono 44.1 kHz f32 PCM, optionally hard-trimmed."""
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(common.SAMPLE_RATE_HZ),
    ]
    if trim_samples is not None:
        if trim_samples < 1:
            raise WindowError("PCM trim length must be positive")
        command.extend(
            [
                "-af",
                f"atrim=end_sample={trim_samples},asetpts=PTS-STARTPTS",
            ]
        )
    command.extend(["-f", "f32le", "-"])
    completed = _run(command)
    if len(completed.stdout) % 4:
        raise WindowError(f"Decoded PCM is not float32-aligned: {path}")
    samples = np.frombuffer(completed.stdout, dtype="<f4").copy()
    if not samples.size or not np.isfinite(samples).all():
        raise WindowError(f"Decoded PCM is empty or non-finite: {path}")
    return samples, command


def pcm_bytes(samples: np.ndarray) -> bytes:
    return np.asarray(samples, dtype="<f4").tobytes(order="C")


def verify_source_fixture() -> dict[str, Any]:
    common.require_sha256(
        common.SOURCE_AUDIO, common.SOURCE_AUDIO_SHA256, "H3-LIP-TXT source fixture"
    )
    source_receipt, source_receipt_raw = common.load_json_object(
        common.SOURCE_AUDIO_RECEIPT
    )
    if source_receipt.get("sha256") != common.SOURCE_AUDIO_SHA256:
        raise WindowError("Existing TTS audio receipt does not bind the source fixture")
    probe = source_receipt.get("ffprobe")
    if not isinstance(probe, dict) or probe != {
        "codec_name": "pcm_s16le",
        "sample_rate_hz": common.SAMPLE_RATE_HZ,
        "channels": 1,
        "channel_layout": None,
        "duration_s": 10.0,
    }:
        raise WindowError("Existing TTS audio receipt has an unexpected audio contract")
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
        raise WindowError("Could not read source WAV contract") from exc
    expected = {
        "channels": 1,
        "sample_width_bytes": 2,
        "sample_rate_hz": common.SAMPLE_RATE_HZ,
        "frames": common.SOURCE_SAMPLES,
        "compression": "NONE",
    }
    if observed != expected:
        raise WindowError(f"Source WAV contract drift: {observed!r}")
    return {
        "path": common.repo_relative(common.SOURCE_AUDIO),
        "sha256": common.SOURCE_AUDIO_SHA256,
        "audio_receipt": common.repo_relative(common.SOURCE_AUDIO_RECEIPT),
        "audio_receipt_sha256": common.sha256_bytes(source_receipt_raw),
        "sample_rate_hz": common.SAMPLE_RATE_HZ,
        "total_samples": common.SOURCE_SAMPLES,
        "duration_s": common.SOURCE_SAMPLES / common.SAMPLE_RATE_HZ,
        "wave_contract": observed,
    }


def _receipt_archive_identity(path: Path, receipt: dict[str, Any]) -> None:
    try:
        relative = path.resolve().relative_to(common.RESULTS.resolve())
    except ValueError as exc:
        raise WindowError("Fresh control receipt must be under results/") from exc
    recipe = receipt.get("recipe")
    run_number = receipt.get("run_number")
    if recipe != common.CONTROL_RECIPE_NAME or isinstance(run_number, bool) or not isinstance(run_number, int):
        raise WindowError("Control receipt does not identify the exact seed-42 native control")
    expected_name = f"{recipe}_run{run_number}.json"
    if relative.name != expected_name or relative.parent != Path("."):
        raise WindowError("Control evidence must be its immutable top-level _runN archive")
    if run_number < 2:
        raise WindowError("H3-LIP-TXT requires a fresh native control, not historical run1")


def validate_fresh_control(control_receipt: Path, control_artifact: Path) -> dict[str, Any]:
    """Bind the requested analysis to an immutable, current-runner native control."""
    receipt, receipt_raw = common.load_json_object(control_receipt)
    _receipt_archive_identity(control_receipt, receipt)
    control_recipe_raw = common.require_sha256(
        common.CONTROL_RECIPE,
        common.CONTROL_RECIPE_SHA256,
        "seed-42 native control recipe",
    )
    if receipt.get("recipe_sha256") != common.CONTROL_RECIPE_SHA256:
        raise WindowError("Control receipt recipe SHA does not bind the current seed-42 control")
    if receipt.get("gate_pass") is not True or receipt.get("provenance_unchanged") is not True:
        raise WindowError("Fresh control did not pass its immutable machine/provenance gates")
    if "sage-free" not in str(receipt.get("boot_lane") or ""):
        raise WindowError("Fresh control was not recorded in a Sage-free lane")
    runner_path = common.ROOT / "run_recipe.py"
    current_runner_sha = common.sha256_file(runner_path)
    if receipt.get("runner_sha256") != current_runner_sha:
        raise WindowError(
            "Fresh control does not bind the active runner bytes; select the current-runner archive"
        )
    output_name = receipt.get("output_path")
    if not isinstance(output_name, str) or Path(output_name).name != output_name:
        raise WindowError("Control receipt has an unsafe output artifact name")
    expected_artifact = (common.OUTPUTS / output_name).resolve()
    if control_artifact.resolve() != expected_artifact:
        raise WindowError("Provided control artifact does not match the immutable receipt output_path")
    if not control_artifact.is_file():
        raise WindowError(f"Fresh control artifact is missing: {control_artifact}")
    artifact_sha = common.sha256_file(control_artifact)
    if artifact_sha != receipt.get("artifact_sha256"):
        raise WindowError("Fresh control artifact hash does not match its receipt")
    return {
        "recipe": common.CONTROL_RECIPE_NAME,
        "recipe_path": common.repo_relative(common.CONTROL_RECIPE),
        "recipe_sha256": common.sha256_bytes(control_recipe_raw),
        "run_number": receipt["run_number"],
        "receipt": common.repo_relative(control_receipt),
        "receipt_sha256": common.sha256_bytes(receipt_raw),
        "artifact": common.repo_relative(control_artifact),
        "artifact_sha256": artifact_sha,
        "runner_sha256": current_runner_sha,
        "boot_lane": receipt["boot_lane"],
        "comfyui_git_commit": receipt.get("comfyui_git_commit"),
        "server_argv": receipt.get("server_argv"),
        "model_fingerprints": receipt.get("model_fingerprints"),
        "lab_locks_sha256": receipt.get("lab_locks_sha256"),
    }


def speech_band(samples: np.ndarray) -> np.ndarray:
    nyquist = common.SAMPLE_RATE_HZ / 2.0
    sos = signal.butter(
        6,
        [SPEECH_BAND_HZ[0] / nyquist, SPEECH_BAND_HZ[1] / nyquist],
        btype="bandpass",
        output="sos",
    )
    filtered = signal.sosfiltfilt(sos, np.asarray(samples, dtype=np.float64))
    if not np.isfinite(filtered).all():
        raise WindowError("Speech-band filter produced non-finite samples")
    return filtered


def sliding_pearson(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Pearson correlation for every valid source window, using FFT numerator."""
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if source.ndim != 1 or target.ndim != 1 or source.size < target.size:
        raise WindowError("Sliding correlation requires one-dimensional source >= target")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise WindowError("Sliding correlation input contains non-finite values")
    centered_target = target - target.mean()
    target_energy = float(np.dot(centered_target, centered_target))
    if target_energy <= 1e-15:
        raise WindowError("Target audio has insufficient variance for correlation")
    numerator = signal.fftconvolve(source, centered_target[::-1], mode="valid")
    cumulative = np.concatenate(([0.0], np.cumsum(source, dtype=np.float64)))
    cumulative_square = np.concatenate(
        ([0.0], np.cumsum(np.square(source), dtype=np.float64))
    )
    length = target.size
    local_sum = cumulative[length:] - cumulative[:-length]
    local_square = cumulative_square[length:] - cumulative_square[:-length]
    local_energy = local_square - np.square(local_sum) / length
    local_energy = np.maximum(local_energy, 0.0)
    denominator = np.sqrt(local_energy * target_energy)
    scores = np.full(numerator.shape, np.nan, dtype=np.float64)
    valid = denominator > 1e-12
    scores[valid] = numerator[valid] / denominator[valid]
    return scores


def log_rms_envelope(samples: np.ndarray) -> np.ndarray:
    """Return a sample-aligned, centered 20 ms log-RMS envelope.

    The output retains one value per input sample.  That lets its full-file
    sliding correlation evaluate the same legal ``0..213150`` start range as
    the waveform representation, including the exact final source endpoint.
    """
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1 or values.size < ENVELOPE_FRAME_SAMPLES:
        raise WindowError("Audio is too short for a 20 ms envelope")
    left = ENVELOPE_FRAME_SAMPLES // 2
    right = ENVELOPE_FRAME_SAMPLES - left - 1
    padded = np.pad(values, (left, right), mode="reflect")
    squares = np.concatenate(
        ([0.0], np.cumsum(np.square(padded), dtype=np.float64))
    )
    energy = squares[ENVELOPE_FRAME_SAMPLES:] - squares[:-ENVELOPE_FRAME_SAMPLES]
    rms = np.sqrt(np.maximum(energy / ENVELOPE_FRAME_SAMPLES, 0.0))
    return np.log(np.maximum(rms, 1e-12))


def ranked_peaks(
    scores: np.ndarray,
    starts: np.ndarray,
    *,
    limit: int = 5,
    separation_samples: int = PEAK_SEPARATION_SAMPLES,
) -> list[dict[str, Any]]:
    finite = np.isfinite(scores)
    if not finite.any():
        raise WindowError("Correlation produced no finite scores")
    order = np.argsort(np.where(finite, scores, -np.inf))[::-1]
    selected: list[dict[str, Any]] = []
    for index in order:
        if not np.isfinite(scores[index]):
            continue
        start = int(starts[index])
        if any(abs(start - item["start_sample"]) < separation_samples for item in selected):
            continue
        selected.append(
            {
                "index": int(index),
                "start_sample": start,
                "start_s": round(start / common.SAMPLE_RATE_HZ, 9),
                "score": round(float(scores[index]), 9),
            }
        )
        if len(selected) == limit:
            break
    return selected


def representation_summary(
    name: str, scores: np.ndarray, starts: np.ndarray
) -> dict[str, Any]:
    peaks = ranked_peaks(scores, starts)
    finite_scores = scores[np.isfinite(scores)]
    median = float(np.median(finite_scores))
    mad = float(np.median(np.abs(finite_scores - median)))
    first = peaks[0]
    second = peaks[1] if len(peaks) > 1 else None
    margin = float(first["score"] - second["score"]) if second else math.inf
    robust_margin = ROBUST_MAD_MULTIPLIER * mad
    reasons: list[str] = []
    if first["score"] < MIN_TOP_SCORE:
        reasons.append(f"top score {first['score']:.6f} is below {MIN_TOP_SCORE:.6f}")
    if second is None:
        reasons.append("no non-overlapping second peak was available")
    else:
        if margin < MIN_PEAK_MARGIN:
            reasons.append(
                f"top-minus-second margin {margin:.6f} is below {MIN_PEAK_MARGIN:.6f}"
            )
        if margin < robust_margin:
            reasons.append(
                f"top-minus-second margin {margin:.6f} is below {ROBUST_MAD_MULTIPLIER:g} MAD ({robust_margin:.6f})"
            )
    return {
        "representation": name,
        "score_count": int(finite_scores.size),
        "top_peaks_nonoverlap_500ms": peaks,
        "best_start_sample": first["start_sample"],
        "best_start_s": first["start_s"],
        "best_score": first["score"],
        "second_score": second["score"] if second else None,
        "second_start_sample": second["start_sample"] if second else None,
        "top_minus_second": round(margin, 9) if math.isfinite(margin) else None,
        "score_median": round(median, 9),
        "score_mad": round(mad, 9),
        "required_margin": round(max(MIN_PEAK_MARGIN, robust_margin), 9),
        "machine_pass": not reasons,
        "machine_failure_reasons": reasons,
    }


def _pearson_one(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size != right.size or not left.size:
        return None
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = math.sqrt(float(np.dot(left_centered, left_centered) * np.dot(right_centered, right_centered)))
    if denominator <= 1e-12:
        return None
    return float(np.dot(left_centered, right_centered) / denominator)


def block_support(
    source_band: np.ndarray, target_band: np.ndarray, selected_start: int
) -> dict[str, Any]:
    overall_rms = float(np.sqrt(np.mean(np.square(source_band))))
    records: list[dict[str, Any]] = []
    supported_starts: list[int] = []
    for offset in range(0, target_band.size - BLOCK_SAMPLES + 1, BLOCK_SAMPLES):
        source_block = source_band[
            selected_start + offset : selected_start + offset + BLOCK_SAMPLES
        ]
        target_block = target_band[offset : offset + BLOCK_SAMPLES]
        correlation = _pearson_one(source_block, target_block)
        source_rms = float(np.sqrt(np.mean(np.square(source_block))))
        voiced = source_rms >= max(1e-8, overall_rms * 0.10)
        supports = voiced and correlation is not None and correlation >= MIN_BLOCK_SCORE
        if supports and (
            not supported_starts
            or offset - supported_starts[-1] >= common.SAMPLE_RATE_HZ
        ):
            supported_starts.append(offset)
        records.append(
            {
                "offset_sample": offset,
                "offset_s": round(offset / common.SAMPLE_RATE_HZ, 9),
                "source_rms": round(source_rms, 9),
                "voiced": voiced,
                "correlation": round(correlation, 9) if correlation is not None else None,
                "supports_selected_window": supports,
            }
        )
    return {
        "block_samples": BLOCK_SAMPLES,
        "block_s": BLOCK_SAMPLES / common.SAMPLE_RATE_HZ,
        "minimum_block_score": MIN_BLOCK_SCORE,
        "records": records,
        "distributed_support_count": len(supported_starts),
        "minimum_distributed_support_count": MIN_DISTRIBUTED_BLOCKS,
        "machine_pass": len(supported_starts) >= MIN_DISTRIBUTED_BLOCKS,
    }


def analyze_arrays(source_pcm: np.ndarray, target_pcm: np.ndarray) -> dict[str, Any]:
    """Run the full-source analysis over canonical PCM arrays (offline/testable)."""
    source_pcm = np.asarray(source_pcm, dtype=np.float64)
    target_pcm = np.asarray(target_pcm, dtype=np.float64)
    if source_pcm.size != common.SOURCE_SAMPLES:
        raise WindowError(
            f"Source PCM must contain {common.SOURCE_SAMPLES} samples, got {source_pcm.size}"
        )
    if target_pcm.size != common.TARGET_SAMPLES:
        raise WindowError(
            f"Target PCM must contain {common.TARGET_SAMPLES} samples, got {target_pcm.size}"
        )
    source_band = speech_band(source_pcm)
    target_band = speech_band(target_pcm)
    waveform_scores = sliding_pearson(source_band, target_band)
    waveform_starts = np.arange(waveform_scores.size, dtype=np.int64)
    waveform = representation_summary(
        "speech_band_sample_pearson", waveform_scores, waveform_starts
    )

    source_envelope = log_rms_envelope(source_band)
    target_envelope = log_rms_envelope(target_band)
    envelope_scores = sliding_pearson(source_envelope, target_envelope)
    envelope_starts = np.arange(envelope_scores.size, dtype=np.int64)
    envelope = representation_summary(
        "log_rms_envelope_20ms_sample_aligned", envelope_scores, envelope_starts
    )

    selected_start = int(waveform["best_start_sample"])
    support = block_support(source_band, target_band, selected_start)
    reasons: list[str] = []
    if not waveform["machine_pass"]:
        reasons.extend("waveform: " + item for item in waveform["machine_failure_reasons"])
    if not envelope["machine_pass"]:
        reasons.extend("envelope: " + item for item in envelope["machine_failure_reasons"])
    disagreement = abs(
        selected_start - int(envelope["best_start_sample"])
    )
    if disagreement > METHOD_AGREEMENT_SAMPLES:
        reasons.append(
            "waveform/envelope maxima disagree by "
            f"{disagreement} samples (> {METHOD_AGREEMENT_SAMPLES})"
        )
    if not support["machine_pass"]:
        reasons.append(
            "fewer than three distributed voiced 0.5-second blocks support the selected window"
        )
    machine_pass = not reasons
    selection = None
    if machine_pass:
        selection = {
            "start_sample": selected_start,
            "end_sample": selected_start + common.TARGET_SAMPLES,
            "start_s": round(selected_start / common.SAMPLE_RATE_HZ, 9),
            "end_s": round(
                (selected_start + common.TARGET_SAMPLES) / common.SAMPLE_RATE_HZ,
                9,
            ),
            "duration_samples": common.TARGET_SAMPLES,
            "duration_s": common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ,
        }
    return {
        "machine_alignment_status": (
            "UNAMBIGUOUS_MACHINE" if machine_pass else "AMBIGUOUS_STOP"
        ),
        "machine_failure_reasons": reasons,
        "predeclared_thresholds": {
            "speech_band_hz": list(SPEECH_BAND_HZ),
            "peak_nonoverlap_separation_s": PEAK_SEPARATION_SAMPLES
            / common.SAMPLE_RATE_HZ,
            "method_agreement_lte_s": METHOD_AGREEMENT_SAMPLES
            / common.SAMPLE_RATE_HZ,
            "minimum_top_score": MIN_TOP_SCORE,
            "minimum_peak_margin": MIN_PEAK_MARGIN,
            "robust_margin_mad_multiplier": ROBUST_MAD_MULTIPLIER,
            "block_s": BLOCK_SAMPLES / common.SAMPLE_RATE_HZ,
            "minimum_distributed_voiced_blocks": MIN_DISTRIBUTED_BLOCKS,
        },
        "waveform": waveform,
        "envelope": {
            **envelope,
            "frame_samples": ENVELOPE_FRAME_SAMPLES,
            "hop_samples": 1,
            "covered_target_samples": common.TARGET_SAMPLES,
            "legal_source_start_max_sample": common.SOURCE_MAX_START_SAMPLE,
        },
        "block_support": support,
        "selected_window": selection,
        "waveform_scores": waveform_scores,
        "envelope_scores": envelope_scores,
    }


def analyze_control(
    control_receipt: Path,
    control_artifact: Path,
    analysis_out: Path,
    waveform_scores_out: Path,
    envelope_scores_out: Path,
) -> dict[str, Any]:
    """Decode, correlate, and immutably publish the machine-only analysis."""
    source = verify_source_fixture()
    fresh_control = validate_fresh_control(control_receipt, control_artifact)
    source_pcm, source_command = decode_f32le(common.SOURCE_AUDIO)
    if source_pcm.size != common.SOURCE_SAMPLES:
        raise WindowError(
            f"Decoded source has {source_pcm.size} samples, expected {common.SOURCE_SAMPLES}"
        )
    target_probe = probe_native_audio_stream(control_artifact)
    decoded_target_pcm, target_command = decode_f32le(control_artifact)
    if decoded_target_pcm.size < common.TARGET_SAMPLES:
        raise WindowError(
            "Native control audio is shorter than the exact 124-frame target span"
        )
    target_pcm = decoded_target_pcm[: common.TARGET_SAMPLES].copy()
    analysis = analyze_arrays(source_pcm, target_pcm)
    waveform_score_bytes = np.asarray(analysis.pop("waveform_scores"), dtype="<f4").tobytes()
    envelope_score_bytes = np.asarray(analysis.pop("envelope_scores"), dtype="<f4").tobytes()
    common.write_immutable(waveform_scores_out, waveform_score_bytes)
    common.write_immutable(envelope_scores_out, envelope_score_bytes)
    payload = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "kind": KIND,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": analysis["machine_alignment_status"],
        "source_fixture": {
            **source,
            "decoded_f32le_sha256": common.sha256_bytes(pcm_bytes(source_pcm)),
            "decode_argv": source_command,
        },
        "target_contract": {
            "frames": common.TARGET_FRAMES,
            "fps": common.TARGET_FPS,
            "target_samples": common.TARGET_SAMPLES,
            "target_duration_s": common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ,
            "source_legal_start_min_sample": 0,
            "source_legal_start_max_sample": common.SOURCE_MAX_START_SAMPLE,
        },
        "fresh_native_control": fresh_control,
        "native_control_audio": {
            "stream": "0:a:0",
            "selection_policy": (
                "Decode 0:a:0 to mono 44.1 kHz PCM, retain the first exact target "
                "span after FFmpeg timestamp normalization, and explicitly discard any "
                "trailing AAC frame padding. The original stream timing remains in the "
                "hash-bound run receipt/media probe; a nonzero audio start timestamp is "
                "rejected rather than silently offset."
            ),
            "ffprobe": target_probe,
            "decode_argv": target_command,
            "decoded_samples_before_hard_trim": int(decoded_target_pcm.size),
            "hard_trimmed_samples": common.TARGET_SAMPLES,
            "hard_trimmed_f32le_sha256": common.sha256_bytes(pcm_bytes(target_pcm)),
        },
        "analyzer": {
            "path": common.repo_relative(Path(__file__)),
            "sha256": common.sha256_file(Path(__file__)),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scipy": SCIPY_VERSION,
            "ffmpeg": ffmpeg_version(),
            "method": (
                "Full legal-source scan: FFT normalized Pearson on 80-7500 Hz PCM "
                "plus independent 20 ms log-RMS-envelope Pearson; no transcript or "
                "ledger timing informs the search."
            ),
            "score_artifacts": {
                "waveform_f32le": {
                    "path": common.repo_relative(waveform_scores_out),
                    "sha256": common.sha256_bytes(waveform_score_bytes),
                    "count": len(waveform_score_bytes) // 4,
                    "start_sample": 0,
                    "stride_samples": 1,
                },
                "envelope_f32le": {
                    "path": common.repo_relative(envelope_scores_out),
                    "sha256": common.sha256_bytes(envelope_score_bytes),
                    "count": len(envelope_score_bytes) // 4,
                    "start_sample": 0,
                    "stride_samples": 1,
                },
            },
        },
        "alignment": analysis,
    }
    common.write_immutable_json(analysis_out, payload)
    return payload


def _nonempty_string(value: str, label: str) -> str:
    if not value or not value.strip():
        raise WindowError(f"{label} must be nonempty")
    return value


def validate_human_review(review: Any) -> None:
    """Require the complete, dated ear-confirmation record Step 4a calls for."""
    if not isinstance(review, dict):
        raise WindowError("Transcript receipt human review must be an object")
    if review.get("verdict") != "confirmed_ordered_words_and_pauses":
        raise WindowError("Transcript receipt lacks the required ear-confirmed verdict")
    for field in ("reviewer", "reviewed_at", "method", "confirmation"):
        value = review.get(field)
        if not isinstance(value, str) or not value.strip():
            raise WindowError(f"Transcript receipt human review lacks nonblank {field}")
    try:
        reviewed_at = dt.datetime.fromisoformat(
            str(review["reviewed_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise WindowError("Transcript receipt reviewed_at is not ISO-8601") from exc
    if reviewed_at.tzinfo is None:
        raise WindowError("Transcript receipt reviewed_at lacks a UTC offset")
    confidence = review.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise WindowError("Transcript receipt human confidence must be finite in [0, 1]")


def _validate_score_artifact(score: Any, score_name: str) -> None:
    if not isinstance(score, dict):
        raise WindowError(f"Machine analysis lacks {score_name} binding")
    if score.get("count") != common.SOURCE_MAX_START_SAMPLE + 1:
        raise WindowError(f"Machine {score_name} count is not a full legal-source scan")
    if score.get("start_sample") != 0 or score.get("stride_samples") != 1:
        raise WindowError(f"Machine {score_name} sample indexing is not exact")
    score_path = common.repo_path(str(score.get("path") or ""))
    raw = score_path.read_bytes()
    if len(raw) != int(score["count"]) * 4 or len(raw) % 4:
        raise WindowError(f"Machine {score_name} byte size does not match its score count")
    if common.sha256_bytes(raw) != score.get("sha256"):
        raise WindowError(f"Machine {score_name} artifact hash drifted")
    values = np.frombuffer(raw, dtype="<f4")
    if not np.isfinite(values).all():
        raise WindowError(f"Machine {score_name} surface contains non-finite values")


def _recompute_alignment_evidence(
    control_artifact: Path,
) -> tuple[
    np.ndarray,
    list[str],
    np.ndarray,
    list[str],
    np.ndarray,
    np.ndarray,
    dict[str, Any],
]:
    """Recompute every deterministic correlation input/surface from live bytes."""
    source_pcm, source_command = decode_f32le(common.SOURCE_AUDIO)
    if source_pcm.size != common.SOURCE_SAMPLES:
        raise WindowError(
            f"Decoded source has {source_pcm.size} samples, expected {common.SOURCE_SAMPLES}"
        )
    decoded_target_pcm, target_command = decode_f32le(control_artifact)
    if decoded_target_pcm.size < common.TARGET_SAMPLES:
        raise WindowError(
            "Native control audio is shorter than the exact 124-frame target span"
        )
    target_pcm = decoded_target_pcm[: common.TARGET_SAMPLES].copy()
    recomputed = analyze_arrays(source_pcm, target_pcm)
    waveform_scores = np.asarray(recomputed.pop("waveform_scores"), dtype="<f4")
    envelope_scores = np.asarray(recomputed.pop("envelope_scores"), dtype="<f4")
    return (
        source_pcm,
        source_command,
        decoded_target_pcm,
        target_command,
        waveform_scores,
        envelope_scores,
        recomputed,
    )


def validate_analysis(
    analysis_path: Path,
    *,
    required_status: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Revalidate machine evidence before it can become an immutable receipt.

    Analysis JSON is evidence, not an authority: all currently available source,
    runner, control, analyzer, score-surface, and selection bindings are checked
    again before a human statement can unlock candidate recipes.
    """
    analysis, analysis_raw = common.load_json_object(analysis_path)
    if (
        analysis.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION
        or analysis.get("kind") != KIND
    ):
        raise WindowError("Analysis file is not an H3-LIP-TXT alignment analysis")
    status = analysis.get("status")
    if status not in {"UNAMBIGUOUS_MACHINE", "AMBIGUOUS_STOP"}:
        raise WindowError("Analysis has an invalid machine alignment status")
    if required_status is not None and status != required_status:
        raise WindowError(f"Analysis status is {status}, expected {required_status}")
    source = analysis.get("source_fixture")
    target = analysis.get("target_contract")
    control = analysis.get("fresh_native_control")
    native_audio = analysis.get("native_control_audio")
    alignment = analysis.get("alignment")
    analyzer = analysis.get("analyzer")
    if not all(
        isinstance(item, dict)
        for item in (source, target, control, native_audio, alignment, analyzer)
    ):
        raise WindowError("Analysis lacks required evidence object fields")
    verified_source = verify_source_fixture()
    for field, value in verified_source.items():
        if source.get(field) != value:
            raise WindowError(f"Analysis source fixture field drifted: {field}")
    if source.get("decoded_f32le_sha256") is None or not isinstance(source.get("decode_argv"), list):
        raise WindowError("Analysis lacks source PCM/decode provenance")
    expected_target = {
        "frames": common.TARGET_FRAMES,
        "fps": common.TARGET_FPS,
        "target_samples": common.TARGET_SAMPLES,
        "target_duration_s": common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ,
        "source_legal_start_min_sample": 0,
        "source_legal_start_max_sample": common.SOURCE_MAX_START_SAMPLE,
    }
    if target != expected_target:
        raise WindowError("Analysis target sample/frame contract drifted")
    control_receipt_path = common.repo_path(str(control.get("receipt") or ""))
    control_artifact_path = common.repo_path(str(control.get("artifact") or ""))
    verified_control = validate_fresh_control(control_receipt_path, control_artifact_path)
    if control != verified_control:
        raise WindowError("Analysis fresh native control does not verify against current bytes")
    if native_audio.get("stream") != "0:a:0":
        raise WindowError("Analysis decoded the wrong native-control audio stream")
    if native_audio.get("hard_trimmed_samples") != common.TARGET_SAMPLES:
        raise WindowError("Analysis did not hard-trim native audio to the target span")
    if (
        not isinstance(native_audio.get("decoded_samples_before_hard_trim"), int)
        or native_audio["decoded_samples_before_hard_trim"] < common.TARGET_SAMPLES
        or not isinstance(native_audio.get("ffprobe"), dict)
        or not isinstance(native_audio.get("decode_argv"), list)
        or not isinstance(native_audio.get("hard_trimmed_f32le_sha256"), str)
    ):
        raise WindowError("Analysis native-control PCM provenance is invalid")
    analyzer_path = common.repo_path(str(analyzer.get("path") or ""))
    if common.sha256_file(analyzer_path) != analyzer.get("sha256"):
        raise WindowError("Machine analyzer bytes are unavailable or drifted")
    score_artifacts = analyzer.get("score_artifacts")
    if not isinstance(score_artifacts, dict):
        raise WindowError("Machine analysis lacks score-surface artifact bindings")
    _validate_score_artifact(score_artifacts.get("waveform_f32le"), "waveform_f32le")
    _validate_score_artifact(score_artifacts.get("envelope_f32le"), "envelope_f32le")

    # A score file whose hash merely matches its own narrated JSON is not
    # sufficient evidence. Re-run the deterministic decoder/filter/correlation
    # pipeline over the currently hash-bound source and fresh native control and
    # require byte-for-byte score surfaces plus identical summarized decision.
    (
        source_pcm,
        source_command,
        decoded_target_pcm,
        target_command,
        waveform_scores,
        envelope_scores,
        recomputed_alignment,
    ) = _recompute_alignment_evidence(control_artifact_path)
    if source.get("decoded_f32le_sha256") != common.sha256_bytes(pcm_bytes(source_pcm)):
        raise WindowError("Analysis source decoded-PCM hash does not recompute")
    if source.get("decode_argv") != source_command:
        raise WindowError("Analysis source decode command does not recompute")
    if native_audio.get("decoded_samples_before_hard_trim") != int(decoded_target_pcm.size):
        raise WindowError("Analysis decoded native-audio length does not recompute")
    if native_audio.get("decode_argv") != target_command:
        raise WindowError("Analysis native-audio decode command does not recompute")
    if native_audio.get("ffprobe") != probe_native_audio_stream(control_artifact_path):
        raise WindowError("Analysis native-audio ffprobe timing does not recompute")
    target_pcm = decoded_target_pcm[: common.TARGET_SAMPLES]
    if native_audio.get("hard_trimmed_f32le_sha256") != common.sha256_bytes(
        pcm_bytes(target_pcm)
    ):
        raise WindowError("Analysis hard-trimmed native PCM hash does not recompute")
    expected_scores = {
        "waveform_f32le": waveform_scores.tobytes(order="C"),
        "envelope_f32le": envelope_scores.tobytes(order="C"),
    }
    for score_name, expected_bytes in expected_scores.items():
        score_path = common.repo_path(str(score_artifacts[score_name]["path"]))
        if score_path.read_bytes() != expected_bytes:
            raise WindowError(f"Machine {score_name} surface does not recompute")
    if alignment != recomputed_alignment:
        raise WindowError("Analysis alignment decision does not recompute")
    if analyzer.get("python") != sys.version.split()[0]:
        raise WindowError("Analysis Python version does not match the validating runtime")
    if analyzer.get("numpy") != np.__version__ or analyzer.get("scipy") != SCIPY_VERSION:
        raise WindowError("Analysis numerical runtime version does not match")
    if analyzer.get("ffmpeg") != ffmpeg_version():
        raise WindowError("Analysis FFmpeg version does not match the validating runtime")
    if not isinstance(alignment.get("machine_failure_reasons"), list):
        raise WindowError("Analysis lacks machine ambiguity reasons")
    selection = alignment.get("selected_window")
    if status == "UNAMBIGUOUS_MACHINE":
        if not isinstance(selection, dict):
            raise WindowError("Unambiguous analysis lacks a selected window")
        start = selection.get("start_sample")
        end = selection.get("end_sample")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start <= common.SOURCE_MAX_START_SAMPLE
            or end != start + common.TARGET_SAMPLES
        ):
            raise WindowError("Analysis selected window violates exact source sample bounds")
        if alignment["machine_failure_reasons"]:
            raise WindowError("Unambiguous analysis carries machine failure reasons")
    elif selection is not None:
        raise WindowError("Ambiguous analysis must not select a source window")
    return analysis, analysis_raw


def write_final_receipt(
    analysis_path: Path,
    receipt_path: Path,
    *,
    transcript_path: Path | None,
    reviewer: str | None,
    reviewed_at: str | None,
    ear_confirmation: str | None,
    confidence: float | None,
    stop: bool,
) -> dict[str, Any]:
    """Publish either a human-confirmed PASS or a durable AMBIGUOUS_STOP receipt."""
    analysis, analysis_raw = validate_analysis(analysis_path)
    status = analysis.get("status")
    if stop:
        if status != "AMBIGUOUS_STOP":
            raise WindowError("A stop receipt is only allowed when machine alignment is ambiguous")
        payload: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "kind": KIND,
            "status": "AMBIGUOUS_STOP",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_fixture": analysis["source_fixture"],
            "target_contract": analysis["target_contract"],
            "fresh_native_control": analysis["fresh_native_control"],
            "analysis": {
                "path": common.repo_relative(analysis_path),
                "sha256": common.sha256_bytes(analysis_raw),
                "machine_alignment_status": status,
                "machine_failure_reasons": analysis["alignment"]["machine_failure_reasons"],
            },
            "aligned_source_window": None,
            "transcript": None,
            "human_review": {
                "status": "not_performed_after_machine_ambiguity",
                "campaign_action": "STOP_NO_CANDIDATE_RECIPES_OR_RENDERS",
            },
        }
    else:
        if status != "UNAMBIGUOUS_MACHINE":
            raise WindowError("Cannot certify transcript text when machine alignment is ambiguous")
        if transcript_path is None:
            raise WindowError("A PASS receipt requires a verbatim transcript text file")
        transcript, transcript_raw = common.read_canonical_transcript(transcript_path)
        if confidence is None or not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise WindowError("Human confidence must be a finite number between 0 and 1")
        payload = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "kind": KIND,
            "status": "PASS",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_fixture": analysis["source_fixture"],
            "target_contract": analysis["target_contract"],
            "fresh_native_control": analysis["fresh_native_control"],
            "analysis": {
                "path": common.repo_relative(analysis_path),
                "sha256": common.sha256_bytes(analysis_raw),
                "machine_alignment_status": status,
                "analyzer": analysis["analyzer"],
                "alignment": analysis["alignment"],
            },
            "aligned_source_window": analysis["alignment"]["selected_window"],
            "transcript": {
                "verbatim_utf8": transcript,
                "utf8_sha256": common.sha256_bytes(transcript_raw),
                "encoding": "UTF-8 without BOM",
                "normalization": "NFC already present; no normalization applied",
                "terminal_newline": "absent",
            },
            "human_review": {
                "reviewer": _nonempty_string(reviewer or "", "reviewer"),
                "reviewed_at": _nonempty_string(reviewed_at or "", "reviewed_at"),
                "method": "Ear confirmation against the recorded source sample window and native H3 audio stem",
                "confirmation": _nonempty_string(ear_confirmation or "", "ear_confirmation"),
                "confidence": round(float(confidence), 6),
                "verdict": "confirmed_ordered_words_and_pauses",
            },
        }
        validate_human_review(payload["human_review"])
    common.write_immutable_json(receipt_path, payload)
    return payload


def validate_transcript_receipt(path: Path = common.TRANSCRIPT_RECEIPT) -> dict[str, Any]:
    """Validate a PASS receipt before it can alter a transcript-aware prompt."""
    receipt, receipt_raw = common.load_json_object(path)
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION or receipt.get("kind") != KIND:
        raise WindowError("Transcript receipt has an unexpected schema or kind")
    if receipt.get("status") != "PASS":
        raise WindowError("Transcript receipt is not a PASS; candidates remain prohibited")
    source = receipt.get("source_fixture")
    target = receipt.get("target_contract")
    control = receipt.get("fresh_native_control")
    alignment = receipt.get("aligned_source_window")
    transcript = receipt.get("transcript")
    review = receipt.get("human_review")
    if not all(isinstance(item, dict) for item in (source, target, control, alignment, transcript, review)):
        raise WindowError("Transcript receipt lacks required object fields")
    verified_source = verify_source_fixture()
    if source.get("path") != "fixtures/tts_dialogue.wav" or source.get("sha256") != common.SOURCE_AUDIO_SHA256:
        raise WindowError("Transcript receipt source fixture binding is wrong")
    for field in ("audio_receipt", "audio_receipt_sha256", "sample_rate_hz", "total_samples"):
        if source.get(field) != verified_source.get(field):
            raise WindowError(f"Transcript receipt source fixture field drifted: {field}")
    if target.get("target_samples") != common.TARGET_SAMPLES or target.get("frames") != common.TARGET_FRAMES or target.get("fps") != common.TARGET_FPS:
        raise WindowError("Transcript receipt target frame/sample contract is wrong")
    start = alignment.get("start_sample")
    end = alignment.get("end_sample")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise WindowError("Transcript receipt alignment samples must be integers")
    if not 0 <= start <= common.SOURCE_MAX_START_SAMPLE or end != start + common.TARGET_SAMPLES:
        raise WindowError("Transcript receipt alignment sample bounds are invalid")
    if control.get("recipe") != common.CONTROL_RECIPE_NAME or control.get("recipe_sha256") != common.CONTROL_RECIPE_SHA256:
        raise WindowError("Transcript receipt does not bind the exact seed-42 native control")
    control_receipt_path = common.repo_path(str(control.get("receipt") or ""))
    control_artifact_path = common.repo_path(str(control.get("artifact") or ""))
    if common.sha256_file(control_receipt_path) != control.get("receipt_sha256"):
        raise WindowError("Transcript receipt's control archive hash drifted")
    if common.sha256_file(control_artifact_path) != control.get("artifact_sha256"):
        raise WindowError("Transcript receipt's control artifact hash drifted")
    verified_control = validate_fresh_control(control_receipt_path, control_artifact_path)
    for field in (
        "recipe",
        "recipe_sha256",
        "run_number",
        "receipt",
        "receipt_sha256",
        "artifact",
        "artifact_sha256",
        "runner_sha256",
        "boot_lane",
        "comfyui_git_commit",
        "server_argv",
        "model_fingerprints",
        "lab_locks_sha256",
    ):
        if control.get(field) != verified_control.get(field):
            raise WindowError(f"Transcript receipt fresh-control field drifted: {field}")
    text = transcript.get("verbatim_utf8")
    if not isinstance(text, str) or not text or text.endswith("\n"):
        raise WindowError("Transcript receipt has no canonical verbatim text")
    if "\r" in text or unicodedata.normalize("NFC", text) != text:
        raise WindowError("Transcript receipt text is not canonical NFC/LF UTF-8")
    encoded = text.encode("utf-8")
    if common.sha256_bytes(encoded) != transcript.get("utf8_sha256"):
        raise WindowError("Transcript receipt text hash is wrong")
    validate_human_review(review)
    analysis = receipt.get("analysis")
    if not isinstance(analysis, dict) or analysis.get("machine_alignment_status") != "UNAMBIGUOUS_MACHINE":
        raise WindowError("Transcript receipt lacks an unambiguous machine alignment")
    analysis_path = common.repo_path(str(analysis.get("path") or ""))
    if common.sha256_file(analysis_path) != analysis.get("sha256"):
        raise WindowError("Transcript receipt's analysis hash drifted")
    analysis_payload, _ = validate_analysis(
        analysis_path, required_status="UNAMBIGUOUS_MACHINE"
    )
    if analysis_payload.get("source_fixture") != source:
        raise WindowError("Transcript receipt source binding disagrees with machine analysis")
    if analysis_payload.get("target_contract") != target:
        raise WindowError("Transcript receipt target contract disagrees with machine analysis")
    if analysis_payload.get("fresh_native_control") != control:
        raise WindowError("Transcript receipt fresh control disagrees with machine analysis")
    analysis_alignment = analysis_payload.get("alignment")
    if not isinstance(analysis_alignment, dict) or analysis_alignment.get("selected_window") != alignment:
        raise WindowError("Transcript receipt aligned window disagrees with machine analysis")
    receipt["receipt_path"] = common.repo_relative(path)
    receipt["receipt_sha256"] = common.sha256_bytes(receipt_raw)
    return receipt


def _path_arg(value: str) -> Path:
    return Path(value).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subcommands.add_parser("analyze", help="full-file machine alignment")
    analyze_parser.add_argument("--control-receipt", type=_path_arg, required=True)
    analyze_parser.add_argument("--control-artifact", type=_path_arg, required=True)
    analyze_parser.add_argument(
        "--analysis-out",
        type=_path_arg,
        default=common.ROOT
        / "fixtures/audio_receipts/tts_dialogue_h3_target_window_analysis.json",
    )
    analyze_parser.add_argument(
        "--waveform-scores-out",
        type=_path_arg,
        default=common.ROOT
        / "fixtures/audio_receipts/tts_dialogue_h3_target_window_waveform_scores.f32le",
    )
    analyze_parser.add_argument(
        "--envelope-scores-out",
        type=_path_arg,
        default=common.ROOT
        / "fixtures/audio_receipts/tts_dialogue_h3_target_window_envelope_scores.f32le",
    )
    certify_parser = subcommands.add_parser("certify", help="write PASS or AMBIGUOUS_STOP receipt")
    certify_parser.add_argument("--analysis", type=_path_arg, required=True)
    certify_parser.add_argument("--receipt", type=_path_arg, default=common.TRANSCRIPT_RECEIPT)
    certify_parser.add_argument("--stop", action="store_true")
    certify_parser.add_argument("--transcript-file", type=_path_arg)
    certify_parser.add_argument("--reviewer")
    certify_parser.add_argument("--reviewed-at")
    certify_parser.add_argument("--ear-confirmation")
    certify_parser.add_argument("--confidence", type=float)
    args = parser.parse_args()
    try:
        if args.command == "analyze":
            payload = analyze_control(
                args.control_receipt,
                args.control_artifact,
                args.analysis_out,
                args.waveform_scores_out,
                args.envelope_scores_out,
            )
            print(f"[{payload['status']}] {common.repo_relative(args.analysis_out)}")
        else:
            payload = write_final_receipt(
                args.analysis,
                args.receipt,
                transcript_path=args.transcript_file,
                reviewer=args.reviewer,
                reviewed_at=args.reviewed_at,
                ear_confirmation=args.ear_confirmation,
                confidence=args.confidence,
                stop=args.stop,
            )
            print(f"[{payload['status']}] {common.repo_relative(args.receipt)}")
    except common.H3LipTxtError as exc:
        print(f"[H3-LIP-TXT FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
