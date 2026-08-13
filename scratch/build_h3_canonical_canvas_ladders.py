#!/usr/bin/env python3
"""Build immutable MiniMax H3 canonical-canvas measurement ladders.

This builder is deliberately offline.  It hash-pins two already validated,
rendered lab recipes and changes only the requested 832x480 canvas, the H3
17k+5 model-frame rung, and the SaveVideo artifact identity.  It never boots or
queries ComfyUI and never reads or writes the OTR repository.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
FIXTURES = ROOT / "fixtures"

I2V_SOURCE = RECIPES / "h3_i2v_suite_sentinel.json"
I2V_SOURCE_SHA256 = (
    "3a838a63521f6266293a3f5796e0f25d41187f3c47e3665493c8938779be2f53"
)
REF2VA_SOURCE = RECIPES / "h3_r2v_refaudio_tts_lipsync_exact_seed43.json"
REF2VA_SOURCE_SHA256 = (
    "159467e9e9d25b07b95e5cd46a16c8c45af0449f0ab838285697d259f7339712"
)

SCENE_FIXTURE = FIXTURES / "scene_still.png"
SCENE_SHA256 = "0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596"
PORTRAIT_FIXTURE = FIXTURES / "portrait.png"
PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
TTS_FIXTURE = FIXTURES / "tts_dialogue.wav"
TTS_SHA256 = "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"

WIDTH = 832
HEIGHT = 480
ELEVATED_BASELINE_THRESHOLD_GB = 2.0
ELEVATED_BASELINE_STAMP = (
    "elevated-baseline lane, operator-authorized 2026-08-10"
)
REDACTED_WORKLOAD_PROCESS_SCHEMA = [
    "pid",
    "process_create_time",
    "process_basename",
    "executable_basename",
    "target_basename",
    "matched_markers",
    "match_basis",
    "argv_sha256",
]
OWNED_LAB_SERVER_EXCLUSION_SCHEMA = [
    "pid",
    "process_create_time",
    "server_instance",
    "process_identity",
    "argv_match",
    "narrowly_verified",
    "excluded_pid_only",
    "verified_windows_venv_launcher",
    "expected_excluded_process_count",
]
VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA = [
    "pid",
    "process_create_time",
    "expected_launcher_path",
    "direct_child_pid",
    "direct_parent_verified",
    "launcher_identity_live",
    "child_identity_live",
    "argv_tail_matches_child",
    "both_exact_validated_server_argv",
    "child_executable_differs",
    "creation_delta_s",
    "narrowly_verified",
    "excluded_pid_only",
    "process_identity",
    "argv_match",
]
EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA = [
    "pid",
    "process_create_time",
    "reason",
]
FPS = 24.0
FRAME_RUNGS = (107, 192, 277)
I2V_SEED = 42
REF2VA_SEED = 43
ACTION_PROMPT = (
    "A medium close shot of <Picture 1> speaking directly to camera, "
    "lip movements matching <Audio 1> precisely."
)


def i2v_name(frames: int) -> str:
    return f"h3_i2v_canonical_832x480_f{frames}"


def ref2va_name(frames: int) -> str:
    return f"h3_r2v_refaudio_canonical_832x480_f{frames}_seed43"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_hash(path: Path, expected: str, label: str) -> bytes:
    payload = path.read_bytes()
    actual = sha256_bytes(payload)
    if actual != expected:
        raise RuntimeError(
            f"{label} hash drift: expected {expected}, found {actual}: {path}"
        )
    return payload


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")


def load_source(path: Path, expected_sha256: str, expected_name: str) -> dict[str, Any]:
    raw = require_hash(path, expected_sha256, f"{expected_name} topology source")
    source = json.loads(raw.decode("utf-8"))
    if source.get("name") != expected_name:
        raise RuntimeError(f"hash-pinned source has unexpected identity: {path}")
    return source


def duration_seconds(frames: int) -> float:
    return round(frames / FPS, 6)


def completion_timeout_seconds(frames: int) -> int:
    try:
        return {107: 1_800, 192: 3_600, 277: 5_400}[frames]
    except KeyError as exc:
        raise ValueError(f"no completion timeout is pinned for {frames} frames") from exc


def grid_k(frames: int) -> int:
    if (frames - 5) % 17 != 0:
        raise ValueError(f"H3 frame count is not on the 17k+5 grid: {frames}")
    return (frames - 5) // 17


def replace_required_value(
    topology: dict[str, Any], node_id: str, input_name: str, value: Any
) -> None:
    matches = [
        assertion
        for assertion in topology["required_input_values"]
        if (assertion.get("node"), assertion.get("input"))
        == (node_id, input_name)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one required value for {node_id}.{input_name}, "
            f"found {len(matches)}"
        )
    matches[0]["equals"] = value


def receipt_requirements(frames: int) -> dict[str, Any]:
    duration = duration_seconds(frames)
    return {
        "warm_gate": {
            "required_consecutive_runs": 2,
            "passing_run": "second consecutive run",
            "required_lane": "--disable-pinned-memory",
            "required_boot_lane": "lab-8199, sage-free, manager-offline-test, no-pinned",
            "executor_cache_nonce_required": True,
            "peak_vram_gb_lte": 14.5,
        },
        "manager_offline_gate": {
            "required": True,
            "authoritative_source": "pair-unique server log",
            "required_announcement": "[ComfyUI-Manager] network_mode: offline",
            "required_announcement_count": 1,
            "must_precede_startup_completion": True,
            "must_precede_first_prompt": True,
            "network_markers_required_empty": True,
            "mutation_markers_required_empty": True,
        },
        "preboot_gpu_idle_gate": {
            "cold_required": True,
            "warm_policy": (
                "reuse exact owned cold server; no fresh idle sampling claimed"
            ),
            "sample_count": 5,
            "sampling_interval_s": 0.2,
            "vram_used_recorded_non_gating": True,
            "gpu_utilization_recorded_non_gating": True,
            "memory_utilization_recorded_non_gating": True,
            "known_render_compute_processes_block": True,
            "advisory_unreadable_processes_retained_non_gating": True,
            "shared_positive_workload_classifier_required": True,
            "optional_verified_direct_windows_venv_launcher_exclusion": True,
            "windows_venv_launcher_exclusion_max_count": 1,
            "redacted_process_evidence_required": True,
            "process_scan_result_fields": [
                "blocking_processes",
                "advisory_unreadable_processes",
            ],
            "redacted_process_schema": list(
                REDACTED_WORKLOAD_PROCESS_SCHEMA
            ),
            "desktop_graphics_signals_retained_but_not_required": True,
            "required_driver_model": "WDDM",
            "display_active_allowed_measured_states": ["Disabled", "Enabled"],
            "display_active_recorded_non_gating": True,
        },
        "operator_idle_policy": {
            "baseline_vram_recorded_advisory": True,
            "baseline_numeric_rejection": False,
            "pair_cold_warm_baseline_drift_recorded_advisory": True,
            "pair_baseline_drift_numeric_rejection": False,
            "elevated_baseline_threshold_gb": ELEVATED_BASELINE_THRESHOLD_GB,
            "elevated_baseline_threshold_operator": ">",
            "elevated_baseline_stamp": ELEVATED_BASELINE_STAMP,
            "per_leg_immediate_prequeue_known_workload_scan_required": True,
            "optional_verified_direct_owned_server_windows_venv_launcher_exclusion": True,
            "owned_server_windows_venv_launcher_exclusion_max_count": 1,
            "owned_server_excluded_process_count_allowed": [1, 2],
            "owned_lab_server_exclusion_schema": list(
                OWNED_LAB_SERVER_EXCLUSION_SCHEMA
            ),
            "verified_owned_server_windows_venv_launcher_schema": list(
                VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA
            ),
            "excluded_owned_lab_server_row_schema": list(
                EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA
            ),
            "unreadable_unknown_python_advisory_non_gating": True,
            "redacted_positive_workload_evidence_required": True,
            "absolute_and_net_peak_required": True,
            "net_peak_definition": "peak_vram_gb - baseline_vram_gb",
        },
        "completion_timeout_s": completion_timeout_seconds(frames),
        "timing": {
            "ffprobe_required": True,
            "expected_width": WIDTH,
            "expected_height": HEIGHT,
            "expected_model_frame_count": frames,
            "expected_fps": FPS,
            "expected_duration_s": duration,
            "absolute_duration_error_lte_s": round(1.0 / FPS, 6),
        },
        "required_measured_fields": [
            "baseline_vram_gb",
            "peak_vram_gb",
            "absolute_peak_vram_gb",
            "net_peak_vram_gb",
            "elevated_baseline_lane",
            "baseline_lane_stamp",
            "duration_s",
        ],
    }


def contract(mode: str, frames: int) -> dict[str, Any]:
    duration = duration_seconds(frames)
    payload: dict[str, Any] = {
        "engine": "minimax_h3",
        "mode": mode,
        "width": WIDTH,
        "height": HEIGHT,
        "frames": frames,
        "fps": FPS,
        "target_s": duration,
        "duration_s": duration,
        "model_duration_fraction": f"{frames}/24",
        "h3_frame_grid": "17k+5",
        "h3_grid_k": grid_k(frames),
        "requires_audio": True,
        "required_boot_lane": "lab-8199, sage-free, manager-offline-test, no-pinned",
        "requires_disable_pinned_memory": True,
        "vram_ceiling_gb": 14.5,
    }
    if mode == "r2v_refaudio":
        payload["reference_audio_duration_s"] = 10.0
    return payload


def experiment(mode: str) -> dict[str, Any]:
    names = (
        [i2v_name(frames) for frames in FRAME_RUNGS]
        if mode == "i2v"
        else [ref2va_name(frames) for frames in FRAME_RUNGS]
    )
    return {
        "campaign": "h3_canonical_canvas_envelope_v1",
        "job": "C_h3_canonical_canvas",
        "variant": mode,
        "measurement_state": "unrendered",
        "independent_variable": "model_frame_count",
        "controlled_canvas": "832x480",
        "controlled_fps": FPS,
        "frame_grid": "17k+5",
        "frame_rungs": list(FRAME_RUNGS),
        "ladder_recipe_names": names,
        "execution_order": "cold then warm for each rung; one render at a time",
        "execution_lane": (
            "sage-free Manager offline-test with --disable-pinned-memory"
        ),
        "execution_graph_diff_policy": (
            "Within this mode, prompt graphs differ only at node 7 length and "
            "the node 12 artifact prefix."
        ),
        "job_d_source_recipe": ref2va_name(192),
        "job_d_source_policy": (
            "The seed-43 192-frame Ref2VA rung is also the sole source render "
            "for the separate 25 fps delivery proof; review copies are post-process only."
        ),
        "behavioral_claim_status": "unrendered and unproven",
    }


def build_i2v(frames: int) -> dict[str, Any]:
    grid_k(frames)
    source = load_source(
        I2V_SOURCE, I2V_SOURCE_SHA256, "h3_i2v_suite_sentinel"
    )
    require_hash(SCENE_FIXTURE, SCENE_SHA256, "scene still fixture")

    name = i2v_name(frames)
    prefix = f"{name}_out"
    prompt = copy.deepcopy(source["prompt"])
    prompt["7"]["inputs"]["width"] = WIDTH
    prompt["7"]["inputs"]["height"] = HEIGHT
    prompt["7"]["inputs"]["length"] = frames
    prompt["12"]["inputs"]["filename_prefix"] = prefix

    topology = copy.deepcopy(source["topology_contract"])
    topology["intent"] = (
        "Official AV-complete MiniMax H3 FL2VA I2V topology at OTR's "
        "832x480 canonical canvas for frame-envelope measurement"
    )
    topology["origin"] = {
        "builder": "scratch/build_h3_canonical_canvas_ladders.py",
        "source_recipe": "recipes/h3_i2v_suite_sentinel.json",
        "source_recipe_sha256": I2V_SOURCE_SHA256,
        "source_recipe_edited": False,
        "third_party_workflow_json_copied": False,
    }
    replace_required_value(topology, "7", "width", WIDTH)
    replace_required_value(topology, "7", "height", HEIGHT)
    replace_required_value(topology, "7", "length", frames)
    replace_required_value(topology, "12", "filename_prefix", prefix)
    topology["intentional_divergences"] = [
        "The official UI subgraph is flattened to the hash-pinned local API prompt",
        "Canvas is OTR's canonical 832x480, both dimensions divisible by 32",
        f"Length is the legal H3 17*{grid_k(frames)}+5 = {frames} frame rung",
        "The randomized template seed remains pinned at 42",
        "scene_still.png remains the sole first-frame fixture; last_frame is absent",
        "Both sampled visual and audio latents retain their official native decoders",
        "No MiniMaxH3SigmaShift or SageAttention patch is inserted",
        "Only the SaveVideo prefix changes to give this immutable rung a unique artifact",
    ]

    recipe = {
        "name": name,
        "tier": "measurement",
        "blocked": False,
        "experiment": experiment("i2v"),
        "contract": contract("i2v", frames),
        "receipt_requirements": receipt_requirements(frames),
        "topology_contract": topology,
        "prompt": prompt,
        "workflow": copy.deepcopy(source["workflow"]),
    }
    validate_recipe(recipe, "i2v", frames)
    return recipe


def build_ref2va(frames: int) -> dict[str, Any]:
    grid_k(frames)
    source = load_source(
        REF2VA_SOURCE,
        REF2VA_SOURCE_SHA256,
        "h3_r2v_refaudio_tts_lipsync_exact_seed43",
    )
    require_hash(PORTRAIT_FIXTURE, PORTRAIT_SHA256, "portrait fixture")
    require_hash(TTS_FIXTURE, TTS_SHA256, "raw TTS fixture")

    name = ref2va_name(frames)
    prefix = f"{name}_out"
    prompt = copy.deepcopy(source["prompt"])
    prompt["7"]["inputs"]["width"] = WIDTH
    prompt["7"]["inputs"]["height"] = HEIGHT
    prompt["7"]["inputs"]["length"] = frames
    prompt["12"]["inputs"]["filename_prefix"] = prefix

    topology = copy.deepcopy(source["topology_contract"])
    topology["profile"] = "minimax_h3_ref2va_canonical_832_portrait_raw_tts_v1"
    topology["intent"] = (
        "Official Ref2VA AV topology with one portrait and one raw TTS "
        "reference at OTR's 832x480 canonical canvas for frame-envelope measurement"
    )
    topology["origin"] = {
        "builder": "scratch/build_h3_canonical_canvas_ladders.py",
        "source_recipe": (
            "recipes/h3_r2v_refaudio_tts_lipsync_exact_seed43.json"
        ),
        "source_recipe_sha256": REF2VA_SOURCE_SHA256,
        "source_recipe_edited": False,
        "third_party_workflow_json_copied": False,
    }
    topology.pop("matrix_diff_whitelist", None)
    topology["ladder_execution_diff_whitelist"] = [
        "prompt.7.inputs.length",
        "prompt.12.inputs.filename_prefix",
    ]
    replace_required_value(topology, "7", "width", WIDTH)
    replace_required_value(topology, "7", "height", HEIGHT)
    replace_required_value(topology, "7", "length", frames)
    replace_required_value(topology, "12", "filename_prefix", prefix)
    topology["intentional_divergences"] = [
        "The official UI subgraph is flattened to the hash-pinned local API prompt",
        "Canvas is OTR's canonical 832x480, both dimensions divisible by 32",
        f"Length is the legal H3 17*{grid_k(frames)}+5 = {frames} frame rung",
        "portrait.png remains the sole Picture 1 reference",
        "raw tts_dialogue.wav remains the sole Audio 1 reference",
        "Seed 43 and ref_image_size=match remain fixed across all rungs",
        "Flat V3 dotted sockets ref_images.ref_image_0 and ref_audios.ref_audio_0 are preserved",
        "Source audio remains conditioning-only; only decoded sampled target audio reaches CreateVideo",
        "Only the SaveVideo prefix changes to give this immutable rung a unique artifact",
    ]

    recipe = {
        "name": name,
        "tier": "measurement",
        "blocked": False,
        "experiment": experiment("r2v_refaudio"),
        "contract": contract("r2v_refaudio", frames),
        "receipt_requirements": receipt_requirements(frames),
        "topology_contract": topology,
        "prompt": prompt,
        "workflow": copy.deepcopy(source["workflow"]),
    }
    validate_recipe(recipe, "r2v_refaudio", frames)
    return recipe


def build_recipes() -> dict[str, dict[str, Any]]:
    recipes: dict[str, dict[str, Any]] = {}
    for frames in FRAME_RUNGS:
        i2v = build_i2v(frames)
        ref2va = build_ref2va(frames)
        recipes[i2v["name"]] = i2v
        recipes[ref2va["name"]] = ref2va
    return recipes


def prompt_difference_paths(left: Any, right: Any, path: str = "") -> set[str]:
    if type(left) is not type(right):
        return {path or "<root>"}
    if isinstance(left, dict):
        paths: set[str] = set()
        for key in set(left) | set(right):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                paths.add(child)
            else:
                paths.update(prompt_difference_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return {path}
        paths: set[str] = set()
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            paths.update(
                prompt_difference_paths(left_item, right_item, f"{path}[{index}]")
            )
        return paths
    return set() if left == right else {path}


def validate_recipe(recipe: dict[str, Any], mode: str, frames: int) -> None:
    prompt = recipe["prompt"]
    name = recipe["name"]
    if recipe["contract"]["frames"] != frames:
        raise RuntimeError(f"{name}: contract frame count drift")
    if recipe["contract"]["h3_grid_k"] != grid_k(frames):
        raise RuntimeError(f"{name}: H3 grid mirror drift")
    if (WIDTH % 32, HEIGHT % 32) != (0, 0):
        raise RuntimeError("canonical canvas is no longer /32 legal")
    if prompt["7"]["inputs"]["width"] != WIDTH:
        raise RuntimeError(f"{name}: prompt width drift")
    if prompt["7"]["inputs"]["height"] != HEIGHT:
        raise RuntimeError(f"{name}: prompt height drift")
    if prompt["7"]["inputs"]["length"] != frames:
        raise RuntimeError(f"{name}: prompt frame count drift")
    if prompt["10"]["inputs"]["fps"] != FPS:
        raise RuntimeError(f"{name}: native H3 fps drift")
    if prompt["10"]["inputs"].get("audio") != ["15", 0]:
        raise RuntimeError(f"{name}: native target audio delivery drift")
    if prompt["13"]["inputs"] != {"sampler_name": "res_multistep"}:
        raise RuntimeError(f"{name}: sampler drift")
    if prompt["14"]["inputs"] != {
        "model": ["1", 0],
        "scheduler": "simple",
        "steps": 20,
        "denoise": 1.0,
    }:
        raise RuntimeError(f"{name}: scheduler drift")

    if mode == "i2v":
        if prompt["5"]["inputs"] != {"noise_seed": I2V_SEED}:
            raise RuntimeError(f"{name}: I2V seed drift")
        if prompt["7"]["class_type"] != "MiniMaxH3ImageToVideo":
            raise RuntimeError(f"{name}: I2V conditioning node drift")
        if prompt["7"]["inputs"].get("first_frame") != ["11", 0]:
            raise RuntimeError(f"{name}: I2V first-frame link drift")
        if "last_frame" in prompt["7"]["inputs"]:
            raise RuntimeError(f"{name}: unexpected I2V last frame")
        if any(node["class_type"] == "LoadAudio" for node in prompt.values()):
            raise RuntimeError(f"{name}: unexpected I2V audio conditioning")
    elif mode == "r2v_refaudio":
        if prompt["5"]["inputs"] != {"noise_seed": REF2VA_SEED}:
            raise RuntimeError(f"{name}: Ref2VA seed drift")
        if prompt["7"]["class_type"] != "MiniMaxH3ReferenceToVideo":
            raise RuntimeError(f"{name}: Ref2VA conditioning node drift")
        inputs = prompt["7"]["inputs"]
        expected_reference_sockets = {
            "ref_images.ref_image_0": ["11", 0],
            "ref_audios.ref_audio_0": ["16", 0],
        }
        actual_reference_sockets = {
            key: value
            for key, value in inputs.items()
            if key.startswith(
                ("ref_images.", "ref_audios.", "ref_videos.", "ref_video_audios.")
            )
        }
        if actual_reference_sockets != expected_reference_sockets:
            raise RuntimeError(
                f"{name}: flat dotted reference socket drift: {actual_reference_sockets}"
            )
        if inputs["ref_image_size"] != "match":
            raise RuntimeError(f"{name}: ref_image_size drift")
        if inputs["prompt"] != ACTION_PROMPT:
            raise RuntimeError(f"{name}: action prompt drift")
        if prompt["11"]["inputs"] != {"image": "portrait.png"}:
            raise RuntimeError(f"{name}: portrait fixture drift")
        if prompt["16"]["inputs"] != {"audio": "tts_dialogue.wav"}:
            raise RuntimeError(f"{name}: raw TTS fixture drift")
    else:
        raise RuntimeError(f"unsupported mode: {mode}")


def validate_ladder_graph_diffs(recipes: dict[str, dict[str, Any]]) -> None:
    expected = {"7.inputs.length", "12.inputs.filename_prefix"}
    for name_fn in (i2v_name, ref2va_name):
        prompts = [recipes[name_fn(frames)]["prompt"] for frames in FRAME_RUNGS]
        for left, right in zip(prompts, prompts[1:]):
            actual = prompt_difference_paths(left, right)
            if actual != expected:
                raise RuntimeError(
                    f"ladder graph drift exceeds length/prefix: {sorted(actual)}"
                )


def immutable_write(path: Path, payload: bytes) -> bool:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Immutable generated recipe differs: {path}")
        return False
    path.write_bytes(payload)
    return True


def write_recipes(output_dir: Path = RECIPES) -> dict[str, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    recipes = build_recipes()
    validate_ladder_graph_diffs(recipes)
    outcomes: dict[str, bool] = {}
    for name, recipe in recipes.items():
        path = output_dir / f"{name}.json"
        payload = canonical_json_bytes(recipe)
        outcomes[name] = immutable_write(path, payload)
        if path.read_bytes() != payload:
            raise RuntimeError(f"generated recipe did not round-trip exactly: {path}")
    return outcomes


def main() -> None:
    for name, changed in write_recipes().items():
        print(f"{name}: {'created' if changed else 'unchanged'}")


if __name__ == "__main__":
    main()
