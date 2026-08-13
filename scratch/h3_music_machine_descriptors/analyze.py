#!/usr/bin/env python3
"""Reproducible local-only descriptors for the H3 unconditioned-music clips."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[2]
OUTPUTS = REPO / "outputs"
DEFAULT_RESULT_DIR = Path(__file__).resolve().parent / "run"
PCM_SAMPLE_RATE = 48_000
SPECTRAL_WINDOW_S = 0.050
ALIGNMENT_BUCKET_S = 0.500
BANDS_HZ = ((20.0, 250.0), (250.0, 2_000.0), (2_000.0, 24_000.0))

CLIPS = (
    ("Q-CONTROL", "h3_unconditioned_music_scene_seed42_f124_out_00002_.mp4", "b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed"),
    ("Q2-B", "h3_unconditioned_music_motion_small_seed42_f124_out_00001_.mp4", "92d044cd5d6f2bffb9e53b5ff5b6917670ff52bbb363309ba0473123ac398541"),
    ("Q2-C", "h3_unconditioned_music_motion_large_seed42_f124_out_00001_.mp4", "3f7b98cdd8187972e2c9119006ac56d2921e071b9b4adc977e8adc8eb81beabe"),
    ("Q3-seed43", "h3_unconditioned_music_scene_seed43_f124_out_00001_.mp4", "cff95b06e823ef91209287cc6dee914a6f4f5e1f161b152e93ece00b67b84ca2"),
    ("Q3-seed44", "h3_unconditioned_music_scene_seed44_f124_out_00001_.mp4", "c17326216587c63dff23b01ec6964720c9ecfcc110575b493b47435605f9c7cf"),
    ("Q3-seed45", "h3_unconditioned_music_scene_seed45_f124_out_00001_.mp4", "aa1de4095d44112195407fe23beeacdd93ca84b5b9d4927651013bf3528ad020"),
    ("Q3-seed46", "h3_unconditioned_music_scene_seed46_f124_out_00001_.mp4", "bae207d958cf0bd1fed62eba770b716588cccf126eeeaea7b6c77749bf6a5890"),
    ("Q4-B", "h3_unconditioned_music_score_seed42_f124_out_00001_.mp4", "23cff43d00b2de2a57da492b4e5942606cf25217b522927d19bad208a58d763a"),
    ("Q4-C", "h3_unconditioned_music_sfx_seed42_f124_out_00001_.mp4", "70ffb6fa94cec7ecae2ed103b5373a689c5563f4e8feb8f09d3c173a41f81041"),
    ("Q5-192", "h3_unconditioned_music_scene_seed42_f192_out_00001_.mp4", "0c6a50a389991ffc5f6b13cc2474c78a484be359014c31f3251302c2c12109ef"),
    ("Q5-277", "h3_unconditioned_music_scene_seed42_f277_out_00001_.mp4", "ebd82c654297d938ba2cfdd68d3877af945d797022507433117ee665cc1c22e0"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


def run_text(argv: list[str]) -> tuple[str, str]:
    proc = subprocess.run(
        argv,
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command returned {proc.returncode}: {display_command(argv)}\n{proc.stderr}"
        )
    return proc.stdout, proc.stderr


def run_binary(argv: list[str]) -> bytes:
    proc = subprocess.run(
        argv,
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command returned {proc.returncode}: {display_command(argv)}\n"
            + proc.stderr.decode("utf-8", errors="replace")
        )
    return proc.stdout


def parse_finite(text: str, pattern: str, field: str) -> float:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"missing {field}")
    value = float(match.group(1))
    if not math.isfinite(value):
        raise ValueError(f"non-finite {field}: {value}")
    return value


def parse_ebur128(stderr: str) -> dict[str, float]:
    if "Summary:" not in stderr:
        raise ValueError("ebur128 summary missing")
    summary = stderr.rsplit("Summary:", 1)[1]
    return {
        "integrated_lufs": parse_finite(summary, r"^\s*I:\s*([-+]?\d+(?:\.\d+)?)\s+LUFS\s*$", "integrated LUFS"),
        "loudness_range_lu": parse_finite(summary, r"^\s*LRA:\s*([-+]?\d+(?:\.\d+)?)\s+LU\s*$", "LRA"),
        "true_peak_dbfs": parse_finite(summary, r"^\s*Peak:\s*([-+]?\d+(?:\.\d+)?)\s+dBFS\s*$", "true peak"),
    }


def parse_silence(stderr: str) -> dict[str, float | int]:
    starts = [float(value) for value in re.findall(r"silence_start:\s*([-+]?\d+(?:\.\d+)?)", stderr)]
    durations = [float(value) for value in re.findall(r"silence_duration:\s*([-+]?\d+(?:\.\d+)?)", stderr)]
    if len(starts) != len(durations):
        raise ValueError(f"silence interval mismatch: {len(starts)} starts, {len(durations)} durations")
    return {"silence_interval_count": len(starts), "silent_time_s": float(sum(durations))}


def parse_astats(stderr: str, expected_channels: int) -> dict[str, list[float]]:
    metrics: dict[int, dict[str, float]] = {}
    channel: int | None = None
    for raw_line in stderr.splitlines():
        channel_match = re.search(r"\]\s+Channel:\s+(\d+)\s*$", raw_line)
        if channel_match:
            channel = int(channel_match.group(1))
            metrics[channel] = {}
            continue
        if channel is None:
            continue
        if re.search(r"\]\s+Overall\s*$", raw_line):
            channel = None
            continue
        for key, label in (
            ("rms_dbfs", "RMS level dB"),
            ("flat_factor", "Flat factor"),
            ("peak_count", "Peak count"),
        ):
            match = re.search(rf"\]\s+{re.escape(label)}:\s+([-+]?\d+(?:\.\d+)?)\s*$", raw_line)
            if match:
                metrics[channel][key] = float(match.group(1))

    if sorted(metrics) != list(range(1, expected_channels + 1)):
        raise ValueError(f"unexpected astats channels: {sorted(metrics)}")
    for index, values in metrics.items():
        missing = {"rms_dbfs", "flat_factor", "peak_count"} - values.keys()
        if missing:
            raise ValueError(f"channel {index} missing astats fields: {sorted(missing)}")
    return {
        "rms_dbfs_per_channel": [metrics[index]["rms_dbfs"] for index in sorted(metrics)],
        "flat_factor_per_channel": [metrics[index]["flat_factor"] for index in sorted(metrics)],
        "peak_count_per_channel": [metrics[index]["peak_count"] for index in sorted(metrics)],
    }


def full_windows(audio: np.ndarray, window_samples: int) -> np.ndarray:
    count = len(audio) // window_samples
    if count < 2:
        raise ValueError("audio is too short for spectral analysis")
    return audio[: count * window_samples].reshape(count, window_samples)


def periodicity_score(audio: np.ndarray, sample_rate: int) -> tuple[float, float]:
    signal = audio.astype(np.float64, copy=False)
    signal = signal - float(np.mean(signal))
    energy = float(np.dot(signal, signal))
    if energy <= np.finfo(np.float64).tiny:
        return 0.0, 0.0

    fft_size = 1 << (2 * len(signal) - 1).bit_length()
    spectrum = np.fft.rfft(signal, n=fft_size)
    numerator = np.fft.irfft(spectrum * np.conj(spectrum), n=fft_size)[: len(signal)]
    squared = signal * signal
    prefix = np.concatenate(([0.0], np.cumsum(squared)))
    min_lag = int(round(0.25 * sample_rate))
    max_lag = min(int(round(2.0 * sample_rate)), len(signal) - 1)
    lags = np.arange(min_lag, max_lag + 1)
    left_energy = prefix[len(signal) - lags] - prefix[0]
    right_energy = prefix[len(signal)] - prefix[lags]
    denominator = np.sqrt(np.maximum(left_energy * right_energy, np.finfo(np.float64).tiny))
    normalized = numerator[lags] / denominator
    best_offset = int(np.argmax(normalized))
    return float(normalized[best_offset]), float(lags[best_offset] / sample_rate)


def numpy_audio_descriptors(pcm_bytes: bytes) -> tuple[dict[str, Any], np.ndarray]:
    raw = np.frombuffer(pcm_bytes, dtype="<i2")
    if raw.size == 0:
        raise ValueError("decoded PCM is empty")
    audio = raw.astype(np.float64) / 32768.0
    window_samples = int(round(SPECTRAL_WINDOW_S * PCM_SAMPLE_RATE))
    frames = full_windows(audio, window_samples)
    hann = np.hanning(window_samples)
    magnitudes = np.abs(np.fft.rfft(frames * hann[None, :], axis=1))
    powers = magnitudes * magnitudes
    frequencies = np.fft.rfftfreq(window_samples, d=1.0 / PCM_SAMPLE_RATE)

    magnitude_sums = magnitudes.sum(axis=1)
    valid = magnitude_sums > np.finfo(np.float64).tiny
    if not np.all(valid):
        raise ValueError("one or more spectral windows have zero magnitude")
    centroids = (magnitudes * frequencies[None, :]).sum(axis=1) / magnitude_sums

    normalized_magnitudes = magnitudes / magnitude_sums[:, None]
    positive_deltas = np.maximum(normalized_magnitudes[1:] - normalized_magnitudes[:-1], 0.0)
    spectral_flux = positive_deltas.sum(axis=1)

    band_energies = []
    for lower, upper in BANDS_HZ:
        if upper == BANDS_HZ[-1][1]:
            mask = (frequencies >= lower) & (frequencies <= upper)
        else:
            mask = (frequencies >= lower) & (frequencies < upper)
        band_energies.append(float(powers[:, mask].sum()))
    band_total = float(sum(band_energies))
    if band_total <= np.finfo(np.float64).tiny:
        raise ValueError("spectral band energy is zero")
    band_ratios = [value / band_total for value in band_energies]

    periodicity, periodicity_lag_s = periodicity_score(audio, PCM_SAMPLE_RATE)

    bucket_samples = int(round(ALIGNMENT_BUCKET_S * PCM_SAMPLE_RATE))
    bucket_count = len(audio) // bucket_samples
    audio_rms = np.asarray(
        [
            math.sqrt(float(np.mean(audio[start : start + bucket_samples] ** 2)))
            for start in range(0, bucket_count * bucket_samples, bucket_samples)
        ],
        dtype=np.float64,
    )
    if len(audio_rms) != bucket_count:
        raise AssertionError("audio bucket count drift")

    return (
        {
            "pcm_sample_rate_hz": PCM_SAMPLE_RATE,
            "pcm_sample_count": int(len(audio)),
            "pcm_duration_s": float(len(audio) / PCM_SAMPLE_RATE),
            "spectral_window_ms": SPECTRAL_WINDOW_S * 1000.0,
            "spectral_window_count": int(len(frames)),
            "spectral_centroid_mean_hz": float(np.mean(centroids)),
            "spectral_centroid_std_hz": float(np.std(centroids)),
            "spectral_flux_mean": float(np.mean(spectral_flux)),
            "periodicity_score": periodicity,
            "periodicity_best_lag_s": periodicity_lag_s,
            "band_energy_ratio_low_20_250": band_ratios[0],
            "band_energy_ratio_mid_250_2000": band_ratios[1],
            "band_energy_ratio_high_2000_24000": band_ratios[2],
            "alignment_bucket_s": ALIGNMENT_BUCKET_S,
            "audio_rms_bucket_count": int(len(audio_rms)),
        },
        audio_rms,
    )


def parse_scene_scores(stderr: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    current_time: float | None = None
    for line in stderr.splitlines():
        frame_match = re.search(r"\bpts_time:([-+]?\d+(?:\.\d+)?)", line)
        if frame_match:
            current_time = float(frame_match.group(1))
            continue
        score_match = re.search(r"lavfi\.scene_score=([-+]?\d+(?:\.\d+)?)", line)
        if score_match:
            if current_time is None:
                raise ValueError("scene score appeared without a preceding pts_time")
            pairs.append((current_time, float(score_match.group(1))))
            current_time = None
    if not pairs:
        raise ValueError("no ffmpeg scene scores parsed")
    return pairs


def alignment_descriptor(
    scene_scores: list[tuple[float, float]], audio_rms: np.ndarray
) -> dict[str, Any]:
    first_timestamp, first_score = scene_scores[0]
    if first_timestamp != 0.0 or first_score != 0.0:
        raise ValueError(
            f"unexpected first-frame scene sentinel: {(first_timestamp, first_score)}"
        )
    usable_scene_scores = scene_scores[1:]
    bucket_count = len(audio_rms)
    motion_buckets: list[list[float]] = [[] for _ in range(bucket_count)]
    for timestamp, score in usable_scene_scores:
        index = int(math.floor(timestamp / ALIGNMENT_BUCKET_S))
        if 0 <= index < bucket_count:
            motion_buckets[index].append(score)
    populated = [index for index, values in enumerate(motion_buckets) if values]
    if len(populated) != bucket_count:
        raise ValueError(
            f"scene-score buckets incomplete: {len(populated)} populated, {bucket_count} audio buckets"
        )
    motion = np.asarray([float(np.mean(values)) for values in motion_buckets], dtype=np.float64)
    if len(motion) < 3:
        raise ValueError("too few matched alignment buckets")
    if float(np.std(motion)) == 0.0 or float(np.std(audio_rms)) == 0.0:
        correlation = None
    else:
        correlation = float(np.corrcoef(motion, audio_rms)[0, 1])
    return {
        "scene_score_frame_count": len(scene_scores),
        "scene_score_usable_count": len(usable_scene_scores),
        "matched_bucket_count": int(len(motion)),
        "mean_scene_score": float(np.mean(motion)),
        "audio_rms_mean": float(np.mean(audio_rms)),
        "motion_audio_rms_pearson_r": correlation,
    }


def analyze_clip(
    label: str,
    filename: str,
    expected_sha256: str,
    ffmpeg: str,
    ffprobe: str,
    result_dir: Path,
) -> dict[str, Any]:
    path = OUTPUTS / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha256 = sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"{filename} SHA-256 drift: {actual_sha256} != {expected_sha256}")

    probe_command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,channels,channel_layout,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    probe_stdout, probe_stderr = run_text(probe_command)
    probe = json.loads(probe_stdout)
    streams = probe.get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"{filename} expected one selected audio stream, found {len(streams)}")
    channels = int(streams[0]["channels"])

    ebur_command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "NUL",
    ]
    _, ebur_stderr = run_text(ebur_command)

    silence_command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-af",
        "silencedetect=noise=-40dB:d=0.2",
        "-f",
        "null",
        "NUL",
    ]
    _, silence_stderr = run_text(silence_command)

    astats_command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-af",
        "astats=metadata=0:reset=0",
        "-f",
        "null",
        "NUL",
    ]
    _, astats_stderr = run_text(astats_command)

    pcm_command = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(PCM_SAMPLE_RATE),
        "-acodec",
        "pcm_s16le",
        "-f",
        "s16le",
        "pipe:1",
    ]
    pcm = run_binary(pcm_command)

    scene_command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-an",
        "-vf",
        "select='gte(scene,0)',metadata=print",
        "-f",
        "null",
        "NUL",
    ]
    _, scene_stderr = run_text(scene_command)

    numpy_metrics, audio_rms = numpy_audio_descriptors(pcm)
    scene_scores = parse_scene_scores(scene_stderr)
    alignment_metrics = alignment_descriptor(scene_scores, audio_rms)

    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
    logs = {
        "probe": probe_stdout + probe_stderr,
        "ebur128": ebur_stderr,
        "silencedetect": silence_stderr,
        "astats": astats_stderr,
        "scene_scores": scene_stderr,
    }
    for name, content in logs.items():
        (result_dir / f"{safe_label}.{name}.log").write_text(content, encoding="utf-8", newline="\n")

    return {
        "label": label,
        "input": str(path),
        "input_bytes": path.stat().st_size,
        "input_sha256": actual_sha256,
        "probe": probe,
        "commands": {
            "C0_probe": display_command(probe_command),
            "C1_ebur128": display_command(ebur_command),
            "C2_silencedetect": display_command(silence_command),
            "C3_astats": display_command(astats_command),
            "C4_pcm_extract": display_command(pcm_command),
            "C5_scene_scores": display_command(scene_command),
        },
        "metrics": {
            **parse_ebur128(ebur_stderr),
            **parse_silence(silence_stderr),
            **parse_astats(astats_stderr, channels),
            **numpy_metrics,
            **alignment_metrics,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    args = parser.parse_args()
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=False)

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must already be on PATH")

    ffmpeg_version, _ = run_text([ffmpeg, "-version"])
    ffprobe_version, _ = run_text([ffprobe, "-version"])
    records = [
        analyze_clip(label, filename, digest, ffmpeg, ffprobe, result_dir)
        for label, filename, digest in CLIPS
    ]
    payload = {
        "schema_version": 1,
        "repo": str(REPO),
        "analysis_script": str(Path(__file__).resolve()),
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "numpy_version": np.__version__,
        "ffmpeg_executable": ffmpeg,
        "ffmpeg_version": ffmpeg_version.splitlines()[0],
        "ffprobe_executable": ffprobe,
        "ffprobe_version": ffprobe_version.splitlines()[0],
        "analysis_command": display_command([sys.executable, "-B", str(Path(__file__).resolve()), "--result-dir", str(result_dir)]),
        "definitions": {
            "spectral_windows": "non-overlapping complete 50 ms windows, Hann-weighted, mono 48 kHz signed 16-bit PCM",
            "spectral_flux": "mean sum of positive binwise changes between consecutive L1-normalized magnitude spectra",
            "periodicity": "largest overlap-energy-normalized autocorrelation coefficient at a 0.25-2.00 s lag after global mean removal",
            "bands_hz": [[low, high] for low, high in BANDS_HZ],
            "alignment": "Pearson r across matching complete 0.5 s buckets: mean ffmpeg lavfi.scene_score versus linear mono PCM RMS; first-frame zero sentinel and incomplete terminal bucket excluded",
        },
        "records": records,
    }
    result_path = result_dir / "descriptors.json"
    result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(result_path)
    print(sha256(result_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
