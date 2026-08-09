#!/usr/bin/env python3
"""Build the immutable four-condition LTX audio-conditioning matrix.

This is an offline fixture/recipe builder.  It never starts ComfyUI and never
renders video.  Each condition uses the same 3.88-second, 32 kHz, mono,
float-PCM contract.  Loudness matching is baked into the derived WAV bytes so
the ComfyUI graph remains the frozen LoadAudio -> trim -> encode topology.

Existing outputs are immutable: an identical rebuild is accepted, while a
byte mismatch aborts instead of silently replacing evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
RECEIPTS = FIXTURES / "audio_receipts"
RECIPES = ROOT / "recipes"
BASE_RECIPE = RECIPES / "ltx_audio_gguf.json"

EXPECTED_BASE_RECIPE_SHA256 = (
    "ef403c92349c52b4313d3d71eb2ba5644c3ee49a0b2cbe8e3e8799c1014b19d0"
)
EXPECTED_FFMPEG_VERSION_PREFIX = "ffmpeg version 8.0.1-full_build-www.gyan.dev"
WINDOW_SECONDS = 3.88
SAMPLE_RATE = 32_000
SAMPLE_COUNT = 124_160
TARGET_LUFS = -25.8
TOLERANCE_LU = 0.3


@dataclass(frozen=True)
class Condition:
    key: str
    source_fixture: str
    gain_db: int
    derived_fixture: str
    recipe_name: str
    matrix_role: str


CONDITIONS = (
    Condition(
        key="interstitial_static",
        source_fixture="interstitial_static.wav",
        gain_db=0,
        derived_fixture="ltx_matrix_interstitial_static_3p88s_gain_0db.wav",
        recipe_name="ltx_audio_gguf_interstitial_static",
        matrix_role="non-speech-control",
    ),
    Condition(
        key="tts_dialogue",
        source_fixture="tts_dialogue.wav",
        gain_db=-5,
        derived_fixture="ltx_matrix_tts_dialogue_3p88s_gain_minus5db.wav",
        recipe_name="ltx_audio_gguf_tts_dialogue",
        matrix_role="speech-condition",
    ),
    Condition(
        key="music_opening",
        source_fixture="music_opening.wav",
        gain_db=-12,
        derived_fixture="ltx_matrix_music_opening_3p88s_gain_minus12db.wav",
        recipe_name="ltx_audio_gguf_music_opening",
        matrix_role="opening-music-condition",
    ),
    Condition(
        key="music_closing",
        source_fixture="music_closing.wav",
        gain_db=-10,
        derived_fixture="ltx_matrix_music_closing_3p88s_gain_minus10db.wav",
        recipe_name="ltx_audio_gguf_music_closing",
        matrix_role="closing-music-condition",
    ),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def require_tools() -> tuple[str, str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must both be available on PATH")
    version = run([ffmpeg, "-version"]).stdout.splitlines()[0]
    if not version.startswith(EXPECTED_FFMPEG_VERSION_PREFIX):
        raise RuntimeError(
            "Exact fixture bytes require "
            f"{EXPECTED_FFMPEG_VERSION_PREFIX!r}; found {version!r}"
        )
    return ffmpeg, ffprobe, version


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def receipt_path_for(fixture_name: str) -> Path:
    return RECEIPTS / f"{Path(fixture_name).stem}.json"


def read_source_receipt(condition: Condition) -> tuple[dict[str, Any], bytes]:
    source_path = FIXTURES / condition.source_fixture
    receipt_path = receipt_path_for(condition.source_fixture)
    source_bytes = source_path.read_bytes()
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if receipt.get("fixture") != condition.source_fixture:
        raise RuntimeError(f"Source receipt fixture mismatch: {receipt_path}")
    if receipt.get("sha256") != sha256_bytes(source_bytes):
        raise RuntimeError(f"Source receipt hash mismatch: {receipt_path}")
    if receipt.get("ear_gate_pass") is not True:
        raise RuntimeError(f"Source fixture has not passed the ear gate: {source_path}")
    human = receipt.get("human_review", {})
    if not all(human.get(key) for key in ("reviewer", "reviewed_at", "content_class", "description")):
        raise RuntimeError(f"Source fixture lacks a complete human description: {receipt_path}")
    return receipt, receipt_bytes


def derivation_filter(gain_db: int) -> str:
    return (
        f"aresample={SAMPLE_RATE},"
        f"atrim=start_sample=0:end_sample={SAMPLE_COUNT},"
        "asetpts=N/SR/TB,"
        f"volume={gain_db}dB"
    )


def derivation_argv(
    ffmpeg: str,
    source_path: Path,
    destination_path: Path,
    gain_db: int,
) -> list[str]:
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-map_metadata",
        "-1",
        "-af",
        derivation_filter(gain_db),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_f32le",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        str(destination_path),
    ]


def recorded_derivation_command(condition: Condition) -> str:
    source = f"fixtures/{condition.source_fixture}"
    destination = f"fixtures/{condition.derived_fixture}"
    return " ".join(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel error",
            "-y",
            "-i",
            source,
            "-map_metadata -1",
            "-af",
            f'"{derivation_filter(condition.gain_db)}"',
            "-ac 1",
            f"-ar {SAMPLE_RATE}",
            "-c:a pcm_f32le",
            "-fflags +bitexact",
            "-flags:a +bitexact",
            destination,
        ]
    )


def materialize_derived_audio(ffmpeg: str, condition: Condition) -> Path:
    source_path = FIXTURES / condition.source_fixture
    target_path = FIXTURES / condition.derived_fixture
    with tempfile.NamedTemporaryFile(
        prefix=f".{target_path.stem}.",
        suffix=".tmp.wav",
        dir=FIXTURES,
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        run(derivation_argv(ffmpeg, source_path, temporary_path, condition.gain_db))
        if target_path.exists():
            if target_path.read_bytes() != temporary_path.read_bytes():
                raise RuntimeError(
                    f"Immutable derived fixture differs from rebuild: {target_path}"
                )
            temporary_path.unlink()
        else:
            os.replace(temporary_path, target_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return target_path


def probe_audio(ffprobe: str, path: Path) -> dict[str, Any]:
    result = run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            (
                "stream=codec_name,sample_fmt,sample_rate,channels,channel_layout,"
                "duration,duration_ts,time_base:format=duration,size"
            ),
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise RuntimeError(f"Expected exactly one audio stream in {path}")
    stream = streams[0]
    duration = float(data.get("format", {}).get("duration") or stream["duration"])
    probe = {
        "codec_name": stream.get("codec_name"),
        "sample_fmt": stream.get("sample_fmt"),
        "sample_rate_hz": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "channel_layout": stream.get("channel_layout"),
        "duration_s": round(duration, 6),
        "duration_samples": int(stream.get("duration_ts") or 0),
        "time_base": stream.get("time_base"),
    }
    expected = {
        "codec_name": "pcm_f32le",
        "sample_fmt": "flt",
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 1,
        "duration_s": WINDOW_SECONDS,
        "duration_samples": SAMPLE_COUNT,
        "time_base": f"1/{SAMPLE_RATE}",
    }
    for key, expected_value in expected.items():
        if probe[key] != expected_value:
            raise RuntimeError(
                f"Derived fixture contract mismatch for {path.name}: "
                f"{key}={probe[key]!r}, expected {expected_value!r}"
            )
    return probe


def parse_last(pattern: str, text: str, label: str) -> float:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if not matches:
        raise RuntimeError(f"Could not parse {label} from ffmpeg output")
    return float(matches[-1])


def measure_volumes(ffmpeg: str, path: Path) -> dict[str, float]:
    stderr = run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "NUL",
        ]
    ).stderr
    return {
        "mean_volume_db": parse_last(
            r"mean_volume:\s*(-?[0-9.]+) dB", stderr, "mean volume"
        ),
        "max_volume_db": parse_last(
            r"max_volume:\s*(-?[0-9.]+) dB", stderr, "max volume"
        ),
    }


def measure_loudness(ffmpeg: str, path: Path) -> dict[str, float]:
    stderr = run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "NUL",
        ]
    ).stderr
    return {
        "integrated_lufs": parse_last(
            r"^\s*I:\s*(-?[0-9.]+) LUFS", stderr, "integrated loudness"
        ),
        "lra_lu": parse_last(r"^\s*LRA:\s*(-?[0-9.]+) LU", stderr, "LRA"),
        "true_peak_dbtp": parse_last(
            r"^\s*Peak:\s*(-?[0-9.]+) dBFS", stderr, "true peak"
        ),
    }


def immutable_write(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"Immutable generated file differs: {path}")
        return
    path.write_bytes(content)


def make_receipt(
    condition: Condition,
    source_receipt: dict[str, Any],
    source_receipt_bytes: bytes,
    derived_path: Path,
    ffmpeg_version: str,
    ffprobe: dict[str, Any],
    volume: dict[str, float],
    loudness: dict[str, float],
) -> dict[str, Any]:
    source_path = FIXTURES / condition.source_fixture
    source_window = source_receipt.get("matrix_window", {})
    human = copy.deepcopy(source_receipt["human_review"])
    human.update(
        {
            "basis": (
                "Description inherited from the hash-bound, human ear-gated "
                "source receipt. The derivation only takes the first 3.88 seconds, "
                "resamples to mono 32 kHz float PCM, and applies the recorded gain."
            ),
            "derived_bytes_separately_auditioned": False,
        }
    )
    receipt = {
        "schema_version": 1,
        "fixture": condition.derived_fixture,
        "sha256": sha256_file(derived_path),
        "bytes": derived_path.stat().st_size,
        "derived_from": {
            "fixture": condition.source_fixture,
            "sha256": sha256_file(source_path),
            "bytes": source_path.stat().st_size,
            "ear_receipt": relative(receipt_path_for(condition.source_fixture)),
            "ear_receipt_sha256": sha256_bytes(source_receipt_bytes),
        },
        "derivation": {
            "builder": relative(Path(__file__).resolve()),
            "builder_sha256": sha256_file(Path(__file__).resolve()),
            "ffmpeg_version": ffmpeg_version,
            "command": recorded_derivation_command(condition),
            "start_sample": 0,
            "sample_count": SAMPLE_COUNT,
            "sample_rate_hz": SAMPLE_RATE,
            "gain_db": condition.gain_db,
        },
        "ffprobe": ffprobe,
        "volumedetect": volume,
        "loudness": {
            "method": "ffmpeg ebur128=peak=true on the complete derived fixture",
            **loudness,
        },
        "matrix_window": {
            "method": (
                "Derived bytes are exactly 124160 samples; measured with "
                "ffmpeg ebur128=peak=true"
            ),
            "start_s": 0.0,
            "duration_s": WINDOW_SECONDS,
            "target_lufs": TARGET_LUFS,
            "tolerance_lu": TOLERANCE_LU,
            "input_lufs": source_window.get("input_lufs"),
            "gain_db": condition.gain_db,
            "matched_lufs": loudness["integrated_lufs"],
            "matched_true_peak_dbtp": loudness["true_peak_dbtp"],
        },
        "human_review": human,
        "ear_gate_pass": True,
        "ear_gate_basis": "inherited_from_hash_bound_source_receipt",
        "commands": {
            "ffprobe": (
                "ffprobe -v error -select_streams a:0 -show_entries "
                "stream=codec_name,sample_fmt,sample_rate,channels,channel_layout,"
                "duration,duration_ts,time_base:format=duration,size -of json "
                f"fixtures/{condition.derived_fixture}"
            ),
            "volumedetect": (
                "ffmpeg -nostdin -hide_banner -nostats -i "
                f"fixtures/{condition.derived_fixture} -af volumedetect -f null NUL"
            ),
            "matrix_loudness": (
                "ffmpeg -nostdin -hide_banner -nostats -i "
                f"fixtures/{condition.derived_fixture} "
                "-af ebur128=peak=true -f null NUL"
            ),
            "derivation": recorded_derivation_command(condition),
        },
    }
    delta = abs(receipt["matrix_window"]["matched_lufs"] - TARGET_LUFS)
    if delta > TOLERANCE_LU + 1e-9:
        raise RuntimeError(
            f"{condition.key} loudness {loudness['integrated_lufs']:.1f} LUFS "
            f"is outside target {TARGET_LUFS:.1f} +/- {TOLERANCE_LU:.1f} LU"
        )
    return receipt


def normalized_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(recipe)
    normalized["name"] = "<condition-name>"
    normalized["experiment"] = "<condition-metadata>"
    normalized.pop("topology_contract", None)
    normalized["prompt"]["20"]["inputs"]["audio"] = "<condition-audio>"
    normalized["prompt"]["75"]["inputs"]["filename_prefix"] = "<condition-prefix>"
    # The matrix makes the current CreateVideo default explicit. This is the
    # only value change from the frozen base and is identical in all cells.
    normalized["prompt"]["35"]["inputs"].pop("bit_depth", None)
    # Node 12 is unreachable legacy empty-audio baggage. The official
    # conditioned path uses LoadAudio -> encode -> mask -> concat instead.
    normalized["prompt"].pop("12", None)
    return normalized


def validate_dag(recipe: dict[str, Any]) -> None:
    prompt = recipe.get("prompt", {})
    node_ids = set(prompt)
    incoming: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for target_id, node in prompt.items():
        if not isinstance(node, dict) or not node.get("class_type"):
            raise RuntimeError(f"Malformed node {target_id} in {recipe['name']}")
        for value in node.get("inputs", {}).values():
            if not (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                continue
            source_id = value[0]
            if source_id not in node_ids:
                raise RuntimeError(
                    f"Missing link source {source_id} -> {target_id} in {recipe['name']}"
                )
            incoming[target_id].add(source_id)
            outgoing[source_id].add(target_id)

    ready = [node_id for node_id, sources in incoming.items() if not sources]
    visited: list[str] = []
    while ready:
        node_id = ready.pop()
        visited.append(node_id)
        for target_id in outgoing[node_id]:
            incoming[target_id].remove(node_id)
            if not incoming[target_id]:
                ready.append(target_id)
    if len(visited) != len(node_ids):
        raise RuntimeError(f"Cycle detected in {recipe['name']}")

    sinks = [
        node_id
        for node_id, node in prompt.items()
        if node.get("class_type") == "SaveVideo"
    ]
    if sinks != ["75"]:
        raise RuntimeError(f"Expected SaveVideo node 75 in {recipe['name']}")
    ancestors = {"75"}
    stack = ["75"]
    original_incoming: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for source_id, targets in outgoing.items():
        for target_id in targets:
            original_incoming[target_id].add(source_id)
    while stack:
        target_id = stack.pop()
        for source_id in original_incoming[target_id]:
            if source_id not in ancestors:
                ancestors.add(source_id)
                stack.append(source_id)
    if ancestors != node_ids:
        unused = sorted(node_ids - ancestors, key=int)
        raise RuntimeError(f"Nodes do not reach SaveVideo in {recipe['name']}: {unused}")


def make_recipe(
    base_recipe: dict[str, Any],
    condition: Condition,
    source_receipt: dict[str, Any],
    derived_receipt: dict[str, Any],
) -> dict[str, Any]:
    recipe = copy.deepcopy(base_recipe)
    recipe["name"] = condition.recipe_name
    # Removing this dead node is topology hygiene, not a quality variation.
    # Connecting it would replace the real conditioned latent with empty audio.
    recipe["prompt"].pop("12", None)
    recipe["experiment"] = {
        "campaign": "audio_conditioning_matrix_v1",
        "variant": condition.key,
        "matrix_role": condition.matrix_role,
        "source_fixture": condition.source_fixture,
        "source_sha256": source_receipt["sha256"],
        "conditioning_fixture": condition.derived_fixture,
        "conditioning_sha256": derived_receipt["sha256"],
        "conditioning_receipt": relative(receipt_path_for(condition.derived_fixture)),
        "window_start_s": 0.0,
        "window_duration_s": WINDOW_SECONDS,
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 1,
        "sample_format": "pcm_f32le",
        "gain_db": condition.gain_db,
        "target_lufs": TARGET_LUFS,
        "measured_lufs": derived_receipt["matrix_window"]["matched_lufs"],
        "audio_guide_mask": 0.0,
        "scheduler_latent": "connected_pre_sampler_av",
        "output_audio_policy": (
            "CreateVideo muxes the exact loudness-matched source-derived fixture "
            "used for conditioning. LTXV Audio VAE reconstruction is discarded "
            "and is never authoritative delivery audio."
        ),
        "delivery_audio_policy": (
            "Diagnostic clips mux the matched conditioning derivative. Delivery "
            "must externally mux the untouched original source fixture; derived "
            "audio and Audio-VAE audio are not delivery authority."
        ),
        "source_preservation_policy": (
            "The original hash-bound source fixture remains intact; the matrix "
            "uses only the receipt-bound trim/resample/gain derivative."
        ),
    }
    recipe["topology_contract"] = {
        "profile": "official_ltx_ia2v_source_delivery_v1",
        "required_connections": {
            "6.positive": ["4", 0],
            "6.negative": ["5", 0],
            "6.frame_rate": ["18", 0],
            "7.latent": ["30", 0],
            "14.input": ["13", 0],
            "15.image": ["14", 0],
            "16.vae": ["1", 0],
            "16.image": ["15", 0],
            "16.latent": ["11", 0],
            "21.audio": ["20", 0],
            "22.audio": ["21", 0],
            "22.audio_vae": ["2", 0],
            "24.samples": ["22", 0],
            "24.mask": ["23", 0],
            "30.video_latent": ["16", 0],
            "30.audio_latent": ["24", 0],
            "31.latent_image": ["30", 0],
            "32.av_latent": ["31", 0],
            "33.samples": ["32", 0],
            "35.images": ["33", 0],
            "35.audio": ["21", 0],
            "35.fps": ["18", 0],
            "75.video": ["35", 0],
        },
        "required_class_types": [
            "LoadAudio",
            "TrimAudioDuration",
            "LTXVAudioVAEEncode",
            "SolidMask",
            "SetLatentNoiseMask",
            "LTXVConcatAVLatent",
            "LTXVScheduler",
            "SamplerCustomAdvanced",
            "LTXVSeparateAVLatent",
            "CreateVideo",
            "SaveVideo",
        ],
        "forbidden_class_types": ["AudioAdjustVolume"],
        "require_all_nodes_reachable": True,
    }
    recipe["prompt"]["20"]["inputs"]["audio"] = condition.derived_fixture
    recipe["prompt"]["35"]["inputs"]["bit_depth"] = 8
    recipe["prompt"]["75"]["inputs"]["filename_prefix"] = (
        f"{condition.recipe_name}_out"
    )
    return recipe


def main() -> None:
    ffmpeg, ffprobe_binary, ffmpeg_version = require_tools()
    base_bytes = BASE_RECIPE.read_bytes()
    base_hash = sha256_bytes(base_bytes)
    if base_hash != EXPECTED_BASE_RECIPE_SHA256:
        raise RuntimeError(
            "Base recipe drifted; audit it before rebuilding the immutable matrix: "
            f"expected {EXPECTED_BASE_RECIPE_SHA256}, found {base_hash}"
        )
    base_recipe = json.loads(base_bytes.decode("utf-8"))
    baseline_normalized = normalized_recipe(base_recipe)

    built: list[tuple[Condition, dict[str, Any], dict[str, Any]]] = []
    for condition in CONDITIONS:
        source_receipt, source_receipt_bytes = read_source_receipt(condition)
        derived_path = materialize_derived_audio(ffmpeg, condition)
        probe = probe_audio(ffprobe_binary, derived_path)
        volume = measure_volumes(ffmpeg, derived_path)
        loudness = measure_loudness(ffmpeg, derived_path)
        receipt = make_receipt(
            condition,
            source_receipt,
            source_receipt_bytes,
            derived_path,
            ffmpeg_version,
            probe,
            volume,
            loudness,
        )
        receipt_bytes = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
        immutable_write(receipt_path_for(condition.derived_fixture), receipt_bytes)

        recipe = make_recipe(base_recipe, condition, source_receipt, receipt)
        if normalized_recipe(recipe) != baseline_normalized:
            raise RuntimeError(
                f"{condition.recipe_name} changed topology outside the four allowed fields"
            )
        validate_dag(recipe)
        recipe_path = RECIPES / f"{condition.recipe_name}.json"
        recipe_bytes = (json.dumps(recipe, indent=2) + "\n").encode("utf-8")
        immutable_write(recipe_path, recipe_bytes)
        json.loads(recipe_path.read_text(encoding="utf-8"))
        built.append((condition, receipt, recipe))

    matrix_graph = normalized_recipe(built[0][2])
    for condition, _, recipe in built[1:]:
        if normalized_recipe(recipe) != matrix_graph:
            raise RuntimeError(f"Graph drift between matrix cells: {condition.key}")

    for condition, receipt, recipe in built:
        recipe_path = RECIPES / f"{condition.recipe_name}.json"
        print(
            f"{condition.key}: "
            f"audio={receipt['sha256']} "
            f"recipe={sha256_file(recipe_path)} "
            f"LUFS={receipt['matrix_window']['matched_lufs']:.1f}"
        )


if __name__ == "__main__":
    main()
