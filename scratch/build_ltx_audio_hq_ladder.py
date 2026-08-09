#!/usr/bin/env python3
"""Build immutable LTX IA2V HQ candidates from the certified M0 control.

The campaign is deliberately factorial:

* H1 changes only the canvas from 832x480 to 1024x576.
* H2 changes only duration from 97 frames/3.88 s to 193 frames/7.72 s.
* H3 composes the H1 and H2 payload changes and is not an isolated test.

The H2/H3 conditioning WAV is a deterministic, loudness-matched extension of
the same frozen opening-music source.  This builder is offline: it never boots
or queries ComfyUI and never renders video.  Existing generated files are
immutable; identical rebuilds are accepted and byte drift aborts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from duration_match import duration_match
from validate_recipes import validate_recipe_file


RECIPES = ROOT / "recipes"
FIXTURES = ROOT / "fixtures"
AUDIO_RECEIPTS = FIXTURES / "audio_receipts"

BASE_PATH = RECIPES / "ltx_audio_gguf_music_opening.json"
BASE_NAME = "ltx_audio_gguf_music_opening"
BASE_SHA256 = "36432a9535acf26c8b7b936a4afbc427d703b1dbf3ad6653d6e84275dd45d8f0"

# The completed M0-M3 motion ladder is outside this builder's write surface.
PRESERVED_RECIPE_SHA256S = {
    "ltx_audio_gguf_music_opening.json": BASE_SHA256,
    "ltx_audio_motion_m1_prompt.json": (
        "120de644fe7d3cb701fd42461f7559fce50fb9989b6afbcec8d4e5a0a3576a5a"
    ),
    "ltx_audio_motion_m2_soft_anchor.json": (
        "1bab8effbbdf543858351f91c4c522c12c44b8c71e7c1ae8faa7bee325711b53"
    ),
    "ltx_audio_motion_m3_double_duration.json": (
        "f63016d0dc95fa16713d04d5caca5b01bbcbfba25ad2d791e44cfe7a3d2d085b"
    ),
}

H1_NAME = "ltx_audio_hq_h1_1024x576"
H2_NAME = "ltx_audio_hq_h2_193f"
H3_NAME = "ltx_audio_hq_h3_1024x576_193f"
VARIANT_NAMES = (H1_NAME, H2_NAME, H3_NAME)

BASE_WIDTH = 832
BASE_HEIGHT = 480
HQ_WIDTH = 1024
HQ_HEIGHT = 576
FPS = 25
BASE_FRAMES = 97
LONG_FRAMES = 193
BASE_TARGET = Decimal(BASE_FRAMES) / Decimal(FPS)
LONG_TARGET = Decimal(LONG_FRAMES) / Decimal(FPS)
BASE_PLAN = duration_match(BASE_TARGET, "ltx")
LONG_PLAN = duration_match(LONG_TARGET, "ltx")

SOURCE_FIXTURE = "music_opening.wav"
SOURCE_SHA256 = "e3ab5b873ec48d6c99464aa7481bcf86b3c047df5194293664e6f2f3f164541a"
SOURCE_RECEIPT = AUDIO_RECEIPTS / "music_opening.json"
LONG_FIXTURE = "ltx_hq_music_opening_7p72s_lufs_minus25p8.wav"
LONG_FIXTURE_PATH = FIXTURES / LONG_FIXTURE
LONG_RECEIPT_PATH = AUDIO_RECEIPTS / f"{Path(LONG_FIXTURE).stem}.json"
SAMPLE_RATE = 32_000
LONG_SAMPLE_COUNT = 247_040
LONG_GAIN_DB = -12.4
TARGET_LUFS = -25.8
CONTROL_MEASURED_LUFS = -25.6
LUFS_TOLERANCE = 0.3
FFMPEG_VERSION_PREFIX = "ffmpeg version 8.0.1-full_build-www.gyan.dev"

H1_PROMPT_DIFFS = {
    "11.inputs.width",
    "11.inputs.height",
    "14.inputs.resize_type.width",
    "14.inputs.resize_type.height",
    "23.inputs.width",
    "23.inputs.height",
    "75.inputs.filename_prefix",
}
H2_PROMPT_DIFFS = {
    "11.inputs.length",
    "20.inputs.audio",
    "21.inputs.duration",
    "75.inputs.filename_prefix",
}
H3_PROMPT_DIFFS = H1_PROMPT_DIFFS | H2_PROMPT_DIFFS


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def immutable_write(path: Path, content: bytes) -> bool:
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"Immutable generated file differs: {path}")
        return False
    path.write_bytes(content)
    return True


def verify_preserved_recipes() -> None:
    for filename, expected_hash in PRESERVED_RECIPE_SHA256S.items():
        path = RECIPES / filename
        actual = sha256_file(path)
        if actual != expected_hash:
            raise RuntimeError(
                f"Preserved ladder recipe drifted: {filename}: {actual} != {expected_hash}"
            )


def verify_timing_plans() -> None:
    expected = (
        (BASE_PLAN, BASE_FRAMES, BASE_TARGET),
        (LONG_PLAN, LONG_FRAMES, LONG_TARGET),
    )
    for plan, frames, target in expected:
        if plan["frame_count"] != frames:
            raise RuntimeError(f"Unexpected LTX render-frame plan for {target}: {plan}")
        if plan.get("delivered_frame_count", frames) != frames:
            raise RuntimeError(f"Unexpected LTX delivery-frame plan for {target}: {plan}")
        if plan["trim_frames"] != 0 or plan["tail_trim_s"] != 0:
            raise RuntimeError(f"HQ timing must be an exact untrimmed grid point: {plan}")
        if plan["rendered_s"] != Fraction(frames, FPS):
            raise RuntimeError(f"HQ rendered duration drifted: {plan}")
        if plan["delivered_s"] != target:
            raise RuntimeError(f"HQ delivered duration drifted: {plan}")


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def require_media_tools() -> tuple[str, str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must both be on PATH")
    version = run([ffmpeg, "-version"]).stdout.splitlines()[0]
    if not version.startswith(FFMPEG_VERSION_PREFIX):
        raise RuntimeError(
            f"Expected {FFMPEG_VERSION_PREFIX!r}; found {version!r}"
        )
    return ffmpeg, ffprobe, version


def long_filter() -> str:
    return (
        f"aresample={SAMPLE_RATE},"
        f"atrim=start_sample=0:end_sample={LONG_SAMPLE_COUNT},"
        "asetpts=N/SR/TB,"
        f"volume={LONG_GAIN_DB:g}dB"
    )


def derivation_argv(ffmpeg: str, destination: Path) -> list[str]:
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(FIXTURES / SOURCE_FIXTURE),
        "-map_metadata",
        "-1",
        "-af",
        long_filter(),
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
        str(destination),
    ]


def recorded_derivation_command() -> str:
    return (
        "ffmpeg -nostdin -hide_banner -loglevel error -y "
        f"-i fixtures/{SOURCE_FIXTURE} -map_metadata -1 "
        f'-af "{long_filter()}" -ac 1 -ar {SAMPLE_RATE} '
        "-c:a pcm_f32le -fflags +bitexact -flags:a +bitexact "
        f"fixtures/{LONG_FIXTURE}"
    )


def materialize_long_audio(ffmpeg: str) -> None:
    source = FIXTURES / SOURCE_FIXTURE
    if sha256_file(source) != SOURCE_SHA256:
        raise RuntimeError("Frozen opening-music source drifted")
    with tempfile.NamedTemporaryFile(
        prefix=f".{LONG_FIXTURE_PATH.stem}.",
        suffix=".tmp.wav",
        dir=FIXTURES,
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        run(derivation_argv(ffmpeg, temporary_path))
        if LONG_FIXTURE_PATH.exists():
            if LONG_FIXTURE_PATH.read_bytes() != temporary_path.read_bytes():
                raise RuntimeError(
                    f"Immutable derived fixture differs: {LONG_FIXTURE_PATH}"
                )
            temporary_path.unlink()
        else:
            os.replace(temporary_path, LONG_FIXTURE_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def parse_last(pattern: str, text: str, label: str) -> float:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if not matches:
        raise RuntimeError(f"Could not parse {label} from ffmpeg output")
    return float(matches[-1])


def probe_audio(ffprobe: str) -> dict[str, Any]:
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
            str(LONG_FIXTURE_PATH),
        ]
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise RuntimeError("HQ audio derivative must contain exactly one stream")
    stream = streams[0]
    measured = {
        "codec_name": stream.get("codec_name"),
        "sample_fmt": stream.get("sample_fmt"),
        "sample_rate_hz": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "channel_layout": stream.get("channel_layout"),
        "duration_s": round(float(stream.get("duration") or 0.0), 6),
        "duration_samples": int(stream.get("duration_ts") or 0),
        "time_base": stream.get("time_base"),
    }
    expected = {
        "codec_name": "pcm_f32le",
        "sample_fmt": "flt",
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 1,
        "duration_s": float(LONG_TARGET),
        "duration_samples": LONG_SAMPLE_COUNT,
        "time_base": f"1/{SAMPLE_RATE}",
    }
    for key, value in expected.items():
        if measured[key] != value:
            raise RuntimeError(
                f"HQ audio contract mismatch: {key}={measured[key]!r}, expected {value!r}"
            )
    return measured


def measure_audio(ffmpeg: str) -> tuple[dict[str, float], dict[str, float]]:
    volume_stderr = run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(LONG_FIXTURE_PATH),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "NUL",
        ]
    ).stderr
    loudness_stderr = run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(LONG_FIXTURE_PATH),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "NUL",
        ]
    ).stderr
    volume = {
        "mean_volume_db": parse_last(
            r"mean_volume:\s*(-?[0-9.]+) dB", volume_stderr, "mean volume"
        ),
        "max_volume_db": parse_last(
            r"max_volume:\s*(-?[0-9.]+) dB", volume_stderr, "max volume"
        ),
    }
    loudness = {
        "integrated_lufs": parse_last(
            r"^\s*I:\s*(-?[0-9.]+) LUFS", loudness_stderr, "integrated loudness"
        ),
        "lra_lu": parse_last(
            r"^\s*LRA:\s*(-?[0-9.]+) LU", loudness_stderr, "LRA"
        ),
        "true_peak_dbtp": parse_last(
            r"^\s*Peak:\s*(-?[0-9.]+) dBFS", loudness_stderr, "true peak"
        ),
    }
    if abs(loudness["integrated_lufs"] - TARGET_LUFS) > LUFS_TOLERANCE + 1e-9:
        raise RuntimeError(
            f"HQ loudness {loudness['integrated_lufs']:.1f} LUFS is outside "
            f"{TARGET_LUFS:.1f} +/- {LUFS_TOLERANCE:.1f} LU"
        )
    if loudness["integrated_lufs"] != CONTROL_MEASURED_LUFS:
        raise RuntimeError(
            f"HQ duration window must match M0 measured loudness {CONTROL_MEASURED_LUFS:.1f}; "
            f"found {loudness['integrated_lufs']:.1f} LUFS"
        )
    return volume, loudness


def make_audio_receipt(
    ffmpeg_version: str,
    probe: dict[str, Any],
    volume: dict[str, float],
    loudness: dict[str, float],
) -> dict[str, Any]:
    source_path = FIXTURES / SOURCE_FIXTURE
    source_receipt_bytes = SOURCE_RECEIPT.read_bytes()
    source_receipt = json.loads(source_receipt_bytes.decode("utf-8"))
    if source_receipt.get("fixture") != SOURCE_FIXTURE:
        raise RuntimeError("Opening-music source receipt fixture mismatch")
    if source_receipt.get("sha256") != SOURCE_SHA256:
        raise RuntimeError("Opening-music source receipt hash mismatch")
    if source_receipt.get("ear_gate_pass") is not True:
        raise RuntimeError("Opening-music source has not passed its human ear gate")

    human = copy.deepcopy(source_receipt["human_review"])
    human.update(
        {
            "basis": (
                "Description inherited from the hash-bound, human ear-gated "
                "opening-music source. This HQ duration derivative takes the "
                "first 7.72 seconds, resamples to mono 32 kHz float PCM, and "
                "applies only the recorded loudness-match gain."
            ),
            "derived_bytes_separately_auditioned": False,
        }
    )
    return {
        "schema_version": 1,
        "fixture": LONG_FIXTURE,
        "sha256": sha256_file(LONG_FIXTURE_PATH),
        "bytes": LONG_FIXTURE_PATH.stat().st_size,
        "derived_from": {
            "fixture": SOURCE_FIXTURE,
            "sha256": SOURCE_SHA256,
            "bytes": source_path.stat().st_size,
            "ear_receipt": relative(SOURCE_RECEIPT),
            "ear_receipt_sha256": sha256_bytes(source_receipt_bytes),
        },
        "derivation": {
            "builder": relative(Path(__file__).resolve()),
            "builder_sha256": sha256_file(Path(__file__).resolve()),
            "ffmpeg_version": ffmpeg_version,
            "command": recorded_derivation_command(),
            "start_sample": 0,
            "sample_count": LONG_SAMPLE_COUNT,
            "sample_rate_hz": SAMPLE_RATE,
            "gain_db": LONG_GAIN_DB,
        },
        "ffprobe": probe,
        "volumedetect": volume,
        "loudness": {
            "method": "ffmpeg ebur128=peak=true on the complete derived fixture",
            **loudness,
        },
        "matrix_window": {
            "method": (
                "Derived bytes are exactly 247040 samples; measured with "
                "ffmpeg ebur128=peak=true"
            ),
            "start_s": 0.0,
            "duration_s": float(LONG_TARGET),
            "target_lufs": TARGET_LUFS,
            "tolerance_lu": LUFS_TOLERANCE,
            "gain_db": LONG_GAIN_DB,
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
                f"duration,duration_ts,time_base:format=duration,size -of json fixtures/{LONG_FIXTURE}"
            ),
            "volumedetect": (
                f"ffmpeg -nostdin -hide_banner -nostats -i fixtures/{LONG_FIXTURE} "
                "-af volumedetect -f null NUL"
            ),
            "matrix_loudness": (
                f"ffmpeg -nostdin -hide_banner -nostats -i fixtures/{LONG_FIXTURE} "
                "-af ebur128=peak=true -f null NUL"
            ),
            "derivation": recorded_derivation_command(),
        },
    }


def plan_json(plan: dict[str, object]) -> dict[str, int | float]:
    def number(value: object) -> int | float:
        if isinstance(value, (Fraction, Decimal)):
            return float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        raise TypeError(f"Unsupported timing value: {value!r}")

    return {
        "target_s": number(plan["target_seconds"]),
        "frame_count": number(plan["frame_count"]),
        "delivered_frame_count": number(
            plan.get("delivered_frame_count", plan["frame_count"])
        ),
        "trim_frames": number(plan["trim_frames"]),
        "rendered_s": number(plan["rendered_s"]),
        "delivered_s": number(plan["delivered_s"]),
        "tail_trim_s": number(plan["tail_trim_s"]),
    }


def difference_paths(left: Any, right: Any, path: str = "") -> set[str]:
    if type(left) is not type(right):
        return {path or "<root>"}
    if isinstance(left, dict):
        paths: set[str] = set()
        for key in set(left) | set(right):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                paths.add(child)
            else:
                paths.update(difference_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return {path}
        paths: set[str] = set()
        for index, (a, b) in enumerate(zip(left, right)):
            paths.update(difference_paths(a, b, f"{path}[{index}]"))
        return paths
    return set() if left == right else {path}


def add_common_metadata(
    recipe: dict[str, Any],
    *,
    cell: str,
    variable: str,
    plan: dict[str, object],
    prompt_diffs: set[str],
    contract_diffs: set[str],
    compositional: bool,
) -> None:
    recipe["experiment"]["timing_plan"] = plan_json(plan)
    recipe["experiment"]["hq_campaign"] = "ltx_audio_hq_ladder_v1"
    recipe["experiment"]["hq_cell"] = cell
    recipe["experiment"]["render_status"] = "unrendered"
    recipe["experiment"]["behavioral_claim_status"] = "unrendered and unproven"
    recipe["hq_ladder"] = {
        "campaign": "ltx_audio_hq_ladder_v1",
        "cell": cell,
        "control_recipe": BASE_NAME,
        "control_recipe_sha256": BASE_SHA256,
        "independent_variable": variable,
        "compositional_candidate": compositional,
        "execution_prompt_diff_whitelist": sorted(prompt_diffs),
        "contract_diff_whitelist": sorted(contract_diffs),
        "same_seed": 42,
        "same_still": "scene_still.png",
        "same_audio_source": SOURCE_FIXTURE,
        "timing_plan": plan_json(plan),
        "go_no_go": (
            "Render only after both H1 and H2 are individually machine-valid and "
            "human-acceptable; otherwise H3 is NO-GO."
            if compositional
            else "Independent diagnostic against M0; no promotion claim before render."
        ),
    }
    recipe["receipt_requirements"] = {
        "timing": {
            "required_fields": [
                "target_s",
                "frame_count",
                "trim_frames",
                "rendered_s",
                "delivered_s",
                "duration_error_s",
            ],
            "ffprobe_required": True,
            "absolute_duration_error_lte_s": 1 / FPS,
        }
    }


def make_base_variant(base: dict[str, Any], name: str) -> dict[str, Any]:
    recipe = copy.deepcopy(base)
    recipe["name"] = name
    recipe["prompt"]["75"]["inputs"]["filename_prefix"] = f"{name}_out"
    return recipe


def apply_hq_canvas(recipe: dict[str, Any]) -> None:
    recipe["contract"]["width"] = HQ_WIDTH
    recipe["contract"]["height"] = HQ_HEIGHT
    recipe["prompt"]["11"]["inputs"]["width"] = HQ_WIDTH
    recipe["prompt"]["11"]["inputs"]["height"] = HQ_HEIGHT
    recipe["prompt"]["14"]["inputs"]["resize_type.width"] = HQ_WIDTH
    recipe["prompt"]["14"]["inputs"]["resize_type.height"] = HQ_HEIGHT
    recipe["prompt"]["23"]["inputs"]["width"] = HQ_WIDTH
    recipe["prompt"]["23"]["inputs"]["height"] = HQ_HEIGHT


def apply_long_duration(recipe: dict[str, Any], audio_receipt: dict[str, Any]) -> None:
    recipe["contract"]["frames"] = LONG_FRAMES
    recipe["contract"]["duration_s"] = float(LONG_TARGET)
    recipe["prompt"]["11"]["inputs"]["length"] = LONG_FRAMES
    recipe["prompt"]["20"]["inputs"]["audio"] = LONG_FIXTURE
    recipe["prompt"]["21"]["inputs"]["duration"] = float(LONG_TARGET)
    recipe["experiment"].update(
        {
            "conditioning_fixture": LONG_FIXTURE,
            "conditioning_sha256": audio_receipt["sha256"],
            "conditioning_receipt": relative(LONG_RECEIPT_PATH),
            "window_duration_s": float(LONG_TARGET),
            "gain_db": LONG_GAIN_DB,
            "target_lufs": TARGET_LUFS,
            "measured_lufs": audio_receipt["loudness"]["integrated_lufs"],
        }
    )


def make_variants(audio_receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    verify_preserved_recipes()
    verify_timing_plans()
    base_bytes = BASE_PATH.read_bytes()
    if sha256_bytes(base_bytes) != BASE_SHA256:
        raise RuntimeError("Certified HQ base drifted during build")
    base = json.loads(base_bytes.decode("utf-8"))

    h1 = make_base_variant(base, H1_NAME)
    apply_hq_canvas(h1)
    add_common_metadata(
        h1,
        cell="H1",
        variable="canvas_resolution",
        plan=BASE_PLAN,
        prompt_diffs=H1_PROMPT_DIFFS,
        contract_diffs={"width", "height"},
        compositional=False,
    )

    h2 = make_base_variant(base, H2_NAME)
    apply_long_duration(h2, audio_receipt)
    add_common_metadata(
        h2,
        cell="H2",
        variable="duration",
        plan=LONG_PLAN,
        prompt_diffs=H2_PROMPT_DIFFS,
        contract_diffs={"frames", "duration_s"},
        compositional=False,
    )

    h3 = make_base_variant(base, H3_NAME)
    apply_hq_canvas(h3)
    apply_long_duration(h3, audio_receipt)
    add_common_metadata(
        h3,
        cell="H3",
        variable="canvas_resolution_plus_duration",
        plan=LONG_PLAN,
        prompt_diffs=H3_PROMPT_DIFFS,
        contract_diffs={"width", "height", "frames", "duration_s"},
        compositional=True,
    )

    variants = {H1_NAME: h1, H2_NAME: h2, H3_NAME: h3}
    expected_prompt_diffs = {
        H1_NAME: H1_PROMPT_DIFFS,
        H2_NAME: H2_PROMPT_DIFFS,
        H3_NAME: H3_PROMPT_DIFFS,
    }
    expected_contract_diffs = {
        H1_NAME: {"width", "height"},
        H2_NAME: {"frames", "duration_s"},
        H3_NAME: {"width", "height", "frames", "duration_s"},
    }
    for name, recipe in variants.items():
        prompt_diffs = difference_paths(base["prompt"], recipe["prompt"])
        contract_diffs = difference_paths(base["contract"], recipe["contract"])
        if prompt_diffs != expected_prompt_diffs[name]:
            raise RuntimeError(f"{name}: unexpected prompt diff: {sorted(prompt_diffs)}")
        if contract_diffs != expected_contract_diffs[name]:
            raise RuntimeError(f"{name}: unexpected contract diff: {sorted(contract_diffs)}")
        if recipe["topology_contract"] != base["topology_contract"]:
            raise RuntimeError(f"{name}: topology contract drifted")
        if recipe["prompt"]["9"]["inputs"] != {"noise_seed": 42}:
            raise RuntimeError(f"{name}: seed drifted")
    return variants


def main() -> None:
    verify_preserved_recipes()
    verify_timing_plans()
    ffmpeg, ffprobe, ffmpeg_version = require_media_tools()
    materialize_long_audio(ffmpeg)
    probe = probe_audio(ffprobe)
    volume, loudness = measure_audio(ffmpeg)
    audio_receipt = make_audio_receipt(ffmpeg_version, probe, volume, loudness)
    immutable_write(LONG_RECEIPT_PATH, canonical_json_bytes(audio_receipt))

    variants = make_variants(audio_receipt)
    for name, recipe in variants.items():
        path = RECIPES / f"{name}.json"
        immutable_write(path, canonical_json_bytes(recipe))
        report = validate_recipe_file(path)
        if not report["valid"]:
            raise RuntimeError(f"{name}: paper validation failed: {report['errors']}")
        print(f"{name}: {sha256_file(path)}")
    print(
        f"{LONG_FIXTURE}: {audio_receipt['sha256']} "
        f"({probe['duration_s']:.2f}s, {loudness['integrated_lufs']:.1f} LUFS)"
    )


if __name__ == "__main__":
    main()
