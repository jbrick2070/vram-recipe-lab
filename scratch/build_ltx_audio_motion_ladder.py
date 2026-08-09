#!/usr/bin/env python3
"""Build the immutable LTX IA2V motion-ladder variants.

M0 is the already-rendered ``ltx_audio_gguf_music_opening`` control and is
never rewritten here.  M1 changes only the positive prompt, M2 changes only
the locally documented image-anchor strength, and M3 changes the requested
duration.  The extra M3 audio window and decoded-frame trim are dependent
mechanics needed to express that duration without changing seed, still,
models, sampler, scheduler, canvas, or frame rate.

This builder is offline.  It neither starts nor queries ComfyUI and it never
renders video.  Existing generated files are immutable: an identical rebuild
is accepted and any byte drift aborts.
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
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from duration_match import duration_match


RECIPES = ROOT / "recipes"
FIXTURES = ROOT / "fixtures"
AUDIO_RECEIPTS = FIXTURES / "audio_receipts"

M0_PATH = RECIPES / "ltx_audio_gguf_music_opening.json"
M0_SHA256 = "36432a9535acf26c8b7b936a4afbc427d703b1dbf3ad6653d6e84275dd45d8f0"
M0_NAME = "ltx_audio_gguf_music_opening"

OFFICIAL_TEMPLATE = ROOT / "research" / "comfy_templates" / "video_ltx2_3_ia2v.json"
OFFICIAL_TEMPLATE_SHA256 = (
    "7823a703f472d9c5e6f82c462235ff89a0fa14752ec1fd947c4422cf53e47685"
)
COMFYUI_ROOT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI")
NODE_SOURCE = COMFYUI_ROOT / "comfy_extras" / "nodes_lt.py"
NODE_SOURCE_SHA256 = (
    "9dc42e342a0c4242e5a7cc3a136b746afeee4349ea08c510b7c2c17002e4b6be"
)
COMFYUI_COMMIT = "fe4195f7f4275f2626cbafc703acc3ddde1e5490"

M1_NAME = "ltx_audio_motion_m1_prompt"
M2_NAME = "ltx_audio_motion_m2_soft_anchor"
M3_NAME = "ltx_audio_motion_m3_double_duration"
VARIANT_NAMES = (M1_NAME, M2_NAME, M3_NAME)

M1_PROMPT = (
    "retro-futuristic radio control room matching the supplied image, locked "
    "camera, pronounced continuous environmental motion throughout: instrument "
    "needles sweep, indicator lights pulse in traveling patterns, cooling fans "
    "spin, loose cables sway, and thin atmospheric haze drifts across the room; "
    "visible layered parallax, no scene change, high quality"
)

FPS = 25
BASE_DURATION = Decimal("3.88")
DOUBLE_DURATION = BASE_DURATION * 2
BASE_PLAN = duration_match(BASE_DURATION, "ltx")
DOUBLE_PLAN = duration_match(DOUBLE_DURATION, "ltx")

SOURCE_FIXTURE = "music_opening.wav"
SOURCE_SHA256 = "e3ab5b873ec48d6c99464aa7481bcf86b3c047df5194293664e6f2f3f164541a"
SOURCE_RECEIPT = AUDIO_RECEIPTS / "music_opening.json"
M3_FIXTURE = "ltx_motion_music_opening_7p76s_lufs_minus25p8.wav"
M3_FIXTURE_PATH = FIXTURES / M3_FIXTURE
M3_RECEIPT_PATH = AUDIO_RECEIPTS / f"{Path(M3_FIXTURE).stem}.json"
SAMPLE_RATE = 32_000
M3_SAMPLE_COUNT = 248_320
M3_GAIN_DB = -12.4
TARGET_LUFS = -25.8
LUFS_TOLERANCE = 0.3
FFMPEG_VERSION_PREFIX = "ffmpeg version 8.0.1-full_build-www.gyan.dev"


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


def immutable_write(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"Immutable generated file differs: {path}")
        return
    path.write_bytes(content)


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def verify_local_grounding() -> None:
    if sha256_file(M0_PATH) != M0_SHA256:
        raise RuntimeError("M0 recipe drifted; re-audit before building the ladder")
    if sha256_file(OFFICIAL_TEMPLATE) != OFFICIAL_TEMPLATE_SHA256:
        raise RuntimeError("Frozen official IA2V template drifted")
    if sha256_file(NODE_SOURCE) != NODE_SOURCE_SHA256:
        raise RuntimeError("Installed LTXVImgToVideoInplace source drifted")

    template = json.loads(OFFICIAL_TEMPLATE.read_text(encoding="utf-8"))
    nodes = {
        int(node["id"]): node
        for node in walk_dicts(template)
        if node.get("type") == "LTXVImgToVideoInplace" and "id" in node
    }
    expected = {296: [1, False], 325: [0.7, False]}
    actual = {node_id: nodes[node_id].get("widgets_values") for node_id in expected}
    if actual != expected:
        raise RuntimeError(
            f"Official IA2V strength evidence drifted: {actual!r} != {expected!r}"
        )

    source = NODE_SOURCE.read_text(encoding="utf-8")
    required_source_fragments = (
        'node_id="LTXVImgToVideoInplace"',
        'io.Float.Input("strength", default=1.0, min=0.0, max=1.0)',
        "conditioning_latent_frames_mask[:, :, :t.shape[2]] = 1.0 - strength",
    )
    missing = [fragment for fragment in required_source_fragments if fragment not in source]
    if missing:
        raise RuntimeError(f"Installed strength semantics drifted: {missing!r}")


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


def m3_filter() -> str:
    return (
        f"aresample={SAMPLE_RATE},"
        f"atrim=start_sample=0:end_sample={M3_SAMPLE_COUNT},"
        "asetpts=N/SR/TB,"
        f"volume={M3_GAIN_DB:g}dB"
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
        m3_filter(),
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
        f'-af "{m3_filter()}" -ac 1 -ar {SAMPLE_RATE} '
        "-c:a pcm_f32le -fflags +bitexact -flags:a +bitexact "
        f"fixtures/{M3_FIXTURE}"
    )


def materialize_m3_audio(ffmpeg: str) -> None:
    with tempfile.NamedTemporaryFile(
        prefix=f".{M3_FIXTURE_PATH.stem}.",
        suffix=".tmp.wav",
        dir=FIXTURES,
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        run(derivation_argv(ffmpeg, temporary_path))
        if M3_FIXTURE_PATH.exists():
            if M3_FIXTURE_PATH.read_bytes() != temporary_path.read_bytes():
                raise RuntimeError(
                    f"Immutable derived fixture differs: {M3_FIXTURE_PATH}"
                )
            temporary_path.unlink()
        else:
            os.replace(temporary_path, M3_FIXTURE_PATH)
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
            str(M3_FIXTURE_PATH),
        ]
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise RuntimeError("M3 audio derivative must contain exactly one stream")
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
        "duration_s": float(DOUBLE_DURATION),
        "duration_samples": M3_SAMPLE_COUNT,
        "time_base": f"1/{SAMPLE_RATE}",
    }
    for key, value in expected.items():
        if measured[key] != value:
            raise RuntimeError(
                f"M3 audio contract mismatch: {key}={measured[key]!r}, expected {value!r}"
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
            str(M3_FIXTURE_PATH),
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
            str(M3_FIXTURE_PATH),
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
            f"M3 loudness {loudness['integrated_lufs']:.1f} LUFS is outside "
            f"{TARGET_LUFS:.1f} +/- {LUFS_TOLERANCE:.1f} LU"
        )
    return volume, loudness


def make_m3_audio_receipt(
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
    if sha256_file(source_path) != SOURCE_SHA256:
        raise RuntimeError("Opening-music source fixture drifted")
    if source_receipt.get("sha256") != SOURCE_SHA256:
        raise RuntimeError("Opening-music source receipt hash mismatch")
    if source_receipt.get("ear_gate_pass") is not True:
        raise RuntimeError("Opening-music source has not passed its human ear gate")

    human = copy.deepcopy(source_receipt["human_review"])
    human.update(
        {
            "basis": (
                "Description inherited from the hash-bound, human ear-gated "
                "opening-music source. This duration-control derivative takes "
                "the first 7.76 seconds, resamples to mono 32 kHz float PCM, "
                "and applies only the recorded loudness-match gain."
            ),
            "derived_bytes_separately_auditioned": False,
        }
    )
    return {
        "schema_version": 1,
        "fixture": M3_FIXTURE,
        "sha256": sha256_file(M3_FIXTURE_PATH),
        "bytes": M3_FIXTURE_PATH.stat().st_size,
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
            "sample_count": M3_SAMPLE_COUNT,
            "sample_rate_hz": SAMPLE_RATE,
            "gain_db": M3_GAIN_DB,
        },
        "ffprobe": probe,
        "volumedetect": volume,
        "loudness": {
            "method": "ffmpeg ebur128=peak=true on the complete derived fixture",
            **loudness,
        },
        "matrix_window": {
            "method": (
                "Derived bytes are exactly 248320 samples; measured with "
                "ffmpeg ebur128=peak=true"
            ),
            "start_s": 0.0,
            "duration_s": float(DOUBLE_DURATION),
            "target_lufs": TARGET_LUFS,
            "tolerance_lu": LUFS_TOLERANCE,
            "gain_db": M3_GAIN_DB,
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
                f"duration,duration_ts,time_base:format=duration,size -of json fixtures/{M3_FIXTURE}"
            ),
            "volumedetect": (
                f"ffmpeg -nostdin -hide_banner -nostats -i fixtures/{M3_FIXTURE} "
                "-af volumedetect -f null NUL"
            ),
            "matrix_loudness": (
                f"ffmpeg -nostdin -hide_banner -nostats -i fixtures/{M3_FIXTURE} "
                "-af ebur128=peak=true -f null NUL"
            ),
            "derivation": recorded_derivation_command(),
        },
    }


def plan_json(plan: dict[str, object]) -> dict[str, int | float]:
    def number(value: object) -> int | float:
        if isinstance(value, Fraction):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        raise TypeError(f"Unsupported timing value: {value!r}")

    return {
        "target_s": number(plan["target_seconds"]),
        "frame_count": number(plan["frame_count"]),
        "trim_frames": number(plan["trim_frames"]),
        "rendered_s": number(plan["rendered_s"]),
        "delivered_s": number(plan["delivered_s"]),
        "tail_trim_s": number(plan["tail_trim_s"]),
    }


def motion_metadata(
    cell: str,
    variable: str,
    changed_payload_fields: list[str],
    plan: dict[str, object],
) -> dict[str, Any]:
    return {
        "campaign": "ltx_audio_motion_ladder_v1",
        "cell": cell,
        "control_recipe": M0_NAME,
        "control_recipe_sha256": M0_SHA256,
        "same_seed": 42,
        "same_still": "scene_still.png",
        "same_audio_source": SOURCE_FIXTURE,
        "independent_variable": variable,
        "changed_payload_fields": changed_payload_fields,
        "timing_plan": plan_json(plan),
        "strength_grounding": {
            "socket": "16.inputs.strength",
            "control_value": 1.0,
            "documented_soft_anchor_value": 0.7,
            "official_template": relative(OFFICIAL_TEMPLATE),
            "official_template_sha256": OFFICIAL_TEMPLATE_SHA256,
            "official_template_nodes": {
                "296.widgets_values": [1, False],
                "325.widgets_values": [0.7, False],
            },
            "installed_source": "comfy_extras/nodes_lt.py",
            "installed_source_sha256": NODE_SOURCE_SHA256,
            "comfyui_commit": COMFYUI_COMMIT,
            "semantics": "noise_mask over encoded image frames equals 1.0 - strength",
        },
    }


def add_timing_receipt_contract(recipe: dict[str, Any], plan: dict[str, object]) -> None:
    recipe["experiment"]["timing_plan"] = plan_json(plan)
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


def base_variant(base: dict[str, Any], name: str) -> dict[str, Any]:
    recipe = copy.deepcopy(base)
    recipe["name"] = name
    recipe["prompt"]["75"]["inputs"]["filename_prefix"] = f"{name}_out"
    return recipe


def make_variants(m3_receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    base_bytes = M0_PATH.read_bytes()
    if sha256_bytes(base_bytes) != M0_SHA256:
        raise RuntimeError("M0 recipe drifted while building variants")
    base = json.loads(base_bytes.decode("utf-8"))
    if base["prompt"]["9"]["inputs"] != {"noise_seed": 42}:
        raise RuntimeError("M0 seed contract drifted")

    m1 = base_variant(base, M1_NAME)
    m1["prompt"]["4"]["inputs"]["text"] = M1_PROMPT
    m1["motion_ladder"] = motion_metadata(
        "M1",
        "positive_prompt_motion_vocabulary",
        ["prompt.4.inputs.text"],
        BASE_PLAN,
    )
    add_timing_receipt_contract(m1, BASE_PLAN)

    m2 = base_variant(base, M2_NAME)
    m2["prompt"]["16"]["inputs"]["strength"] = 0.7
    m2["motion_ladder"] = motion_metadata(
        "M2",
        "image_conditioning_strength",
        ["prompt.16.inputs.strength"],
        BASE_PLAN,
    )
    add_timing_receipt_contract(m2, BASE_PLAN)

    m3 = base_variant(base, M3_NAME)
    render_frames = int(DOUBLE_PLAN["frame_count"])
    trim_frames = int(DOUBLE_PLAN["trim_frames"])
    delivered_frames = render_frames - trim_frames
    if delivered_frames != 194 or Decimal(delivered_frames) / FPS != DOUBLE_DURATION:
        raise RuntimeError("Unexpected exact M3 delivery plan")

    m3["contract"].update(
        {
            "frames": delivered_frames,
            "render_frames": render_frames,
            "fps": float(FPS),
            "duration_s": float(DOUBLE_DURATION),
            "target_s": float(DOUBLE_DURATION),
            "rendered_s": float(DOUBLE_PLAN["rendered_s"]),
            "trim_frames": trim_frames,
            "delivered_s": float(DOUBLE_PLAN["delivered_s"]),
        }
    )
    m3["prompt"]["11"]["inputs"]["length"] = render_frames
    m3["prompt"]["20"]["inputs"]["audio"] = M3_FIXTURE
    m3["prompt"]["21"]["inputs"]["duration"] = float(DOUBLE_DURATION)
    trimmed_prompt: dict[str, Any] = {}
    for node_id, node in m3["prompt"].items():
        if node_id == "35":
            trimmed_prompt["34"] = {
                "class_type": "ImageFromBatch",
                "inputs": {
                    "image": ["33", 0],
                    "batch_index": 0,
                    "length": delivered_frames,
                },
            }
        trimmed_prompt[node_id] = node
    m3["prompt"] = trimmed_prompt
    m3["prompt"]["35"]["inputs"]["images"] = ["34", 0]

    m3["experiment"].update(
        {
            "conditioning_fixture": M3_FIXTURE,
            "conditioning_sha256": m3_receipt["sha256"],
            "conditioning_receipt": relative(M3_RECEIPT_PATH),
            "window_duration_s": float(DOUBLE_DURATION),
            "gain_db": M3_GAIN_DB,
            "target_lufs": TARGET_LUFS,
            "measured_lufs": m3_receipt["loudness"]["integrated_lufs"],
        }
    )
    required = m3["topology_contract"]["required_connections"]
    required["34.image"] = ["33", 0]
    required["35.images"] = ["34", 0]
    m3["topology_contract"]["required_class_types"].append("ImageFromBatch")
    m3["motion_ladder"] = motion_metadata(
        "M3",
        "duration",
        [
            "contract timing fields",
            "prompt.11.inputs.length",
            "prompt.20.inputs.audio",
            "prompt.21.inputs.duration",
            "prompt.34 (required decoded-frame trim)",
            "prompt.35.inputs.images",
        ],
        DOUBLE_PLAN,
    )
    m3["motion_ladder"]["duration_mechanics"] = {
        "source_duration_s": float(BASE_DURATION),
        "target_duration_s": float(DOUBLE_DURATION),
        "render_frame_grid": "8n+1 at 25 fps",
        "render_frames": render_frames,
        "decoded_trim_frames": trim_frames,
        "delivered_frames": delivered_frames,
        "tail_trim_s": 0.0,
        "audio_window_policy": (
            "same hash-bound opening-music source, extended from 3.88 to 7.76 "
            "seconds and independently loudness-matched to the frozen matrix target"
        ),
    }
    add_timing_receipt_contract(m3, DOUBLE_PLAN)

    return {M1_NAME: m1, M2_NAME: m2, M3_NAME: m3}


def validate_dag(recipe: dict[str, Any]) -> None:
    prompt = recipe["prompt"]
    node_ids = set(prompt)
    incoming: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for target_id, node in prompt.items():
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
                raise RuntimeError(f"Missing link {source_id} -> {target_id}")
            incoming[target_id].add(source_id)
            outgoing[source_id].add(target_id)

    ready = [node_id for node_id, sources in incoming.items() if not sources]
    visited: set[str] = set()
    while ready:
        node_id = ready.pop()
        visited.add(node_id)
        for target_id in outgoing[node_id]:
            incoming[target_id].remove(node_id)
            if not incoming[target_id]:
                ready.append(target_id)
    if visited != node_ids:
        raise RuntimeError(f"Cycle in {recipe['name']}")

    ancestors = {"75"}
    stack = ["75"]
    while stack:
        target = stack.pop()
        for source in (
            value[0]
            for value in prompt[target].get("inputs", {}).values()
            if isinstance(value, list)
            and len(value) == 2
            and isinstance(value[0], str)
            and isinstance(value[1], int)
        ):
            if source not in ancestors:
                ancestors.add(source)
                stack.append(source)
    if ancestors != node_ids:
        raise RuntimeError(
            f"Nodes do not reach SaveVideo in {recipe['name']}: {sorted(node_ids - ancestors)}"
        )


def main() -> None:
    verify_local_grounding()
    ffmpeg, ffprobe, ffmpeg_version = require_media_tools()
    materialize_m3_audio(ffmpeg)
    probe = probe_audio(ffprobe)
    volume, loudness = measure_audio(ffmpeg)
    receipt = make_m3_audio_receipt(ffmpeg_version, probe, volume, loudness)
    receipt_bytes = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    immutable_write(M3_RECEIPT_PATH, receipt_bytes)

    variants = make_variants(receipt)
    for name, recipe in variants.items():
        validate_dag(recipe)
        path = RECIPES / f"{name}.json"
        content = (json.dumps(recipe, indent=2) + "\n").encode("utf-8")
        immutable_write(path, content)
        json.loads(path.read_text(encoding="utf-8"))
        print(f"{name}: {sha256_file(path)}")
    print(
        f"{M3_FIXTURE}: {receipt['sha256']} "
        f"({probe['duration_s']:.2f}s, {loudness['integrated_lufs']:.1f} LUFS)"
    )


if __name__ == "__main__":
    main()
