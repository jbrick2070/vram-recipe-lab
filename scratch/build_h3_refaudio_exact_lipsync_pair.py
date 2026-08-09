#!/usr/bin/env python3
"""Build the immutable exact-fixture H3 Ref2VA lip-sync pair.

The earlier rendered prompt-followup recipes remain historical evidence and
are deliberately never rewritten here.  This builder hash-pins the seed-42
recipe only as a topology source, then removes its second image reference and
uses the repository's raw ``tts_dialogue.wav`` fixture.  The two generated
recipes differ only by identity, RandomNoise seed, SaveVideo prefix, and the
two topology assertions that mirror those execution values.

This module is completely offline.  It does not boot or query ComfyUI.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
FIXTURES = ROOT / "fixtures"

SOURCE_RECIPE = RECIPES / "h3_r2v_refaudio_tts_lipsync.json"
EXPECTED_SOURCE_RECIPE_SHA256 = (
    "930289e8b719c59392a18b0e81ef40ce0ea8d1b5a19e80c30f929533e3bdf0c5"
)

PORTRAIT_FIXTURE = FIXTURES / "portrait.png"
PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
TTS_FIXTURE = FIXTURES / "tts_dialogue.wav"
TTS_SHA256 = "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"

SEED42_NAME = "h3_r2v_refaudio_tts_lipsync_exact_seed42"
SEED43_NAME = "h3_r2v_refaudio_tts_lipsync_exact_seed43"
SEED42_PREFIX = f"{SEED42_NAME}_out"
SEED43_PREFIX = f"{SEED43_NAME}_out"
SEEDS = (42, 43)

ACTION_PROMPT = (
    "A medium close shot of <Picture 1> speaking directly to camera, "
    "lip movements matching <Audio 1> precisely."
)

UNET_NAME = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
CLIP_NAME = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE_NAME = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE_NAME = "minimax_h3_audio_vae_fp32.safetensors"

EXPECTED_NODE_CLASSES = {
    "1": "UNETLoader",
    "2": "CLIPLoader",
    "3": "VAELoader",
    "4": "VAELoader",
    "5": "RandomNoise",
    "6": "BasicGuider",
    "7": "MiniMaxH3ReferenceToVideo",
    "8": "SamplerCustomAdvanced",
    "9": "VAEDecode",
    "10": "CreateVideo",
    "11": "LoadImage",
    "12": "SaveVideo",
    "13": "KSamplerSelect",
    "14": "BasicScheduler",
    "15": "VAEDecodeAudio",
    "16": "LoadAudio",
}


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
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            paths.update(
                difference_paths(left_item, right_item, f"{path}[{index}]")
            )
        return paths
    return set() if left == right else {path}


def iter_links(value: Any, path: str = "") -> Iterator[tuple[str, str, int]]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    ):
        yield path, value[0], value[1]


def source_consumers(prompt: dict[str, Any], source_node: str) -> set[tuple[str, str]]:
    consumers: set[tuple[str, str]] = set()
    for target_id, node in prompt.items():
        for input_name, value in node.get("inputs", {}).items():
            for socket_path, source_id, _ in iter_links(value, input_name):
                if source_id == source_node:
                    consumers.add((target_id, socket_path))
    return consumers


def validate_dag(prompt: dict[str, Any], recipe_name: str) -> None:
    node_ids = set(prompt)
    incoming = {node_id: set() for node_id in node_ids}
    outgoing = {node_id: set() for node_id in node_ids}
    for target_id, node in prompt.items():
        for input_name, value in node.get("inputs", {}).items():
            for socket_path, source_id, output_index in iter_links(value, input_name):
                if source_id not in node_ids:
                    raise RuntimeError(
                        f"{recipe_name}: {target_id}.{socket_path} has missing source "
                        f"{source_id}"
                    )
                if output_index < 0:
                    raise RuntimeError(
                        f"{recipe_name}: {target_id}.{socket_path} has negative output"
                    )
                incoming[target_id].add(source_id)
                outgoing[source_id].add(target_id)

    original_incoming = copy.deepcopy(incoming)
    ready = sorted(
        (node_id for node_id, sources in incoming.items() if not sources), key=int
    )
    visited: list[str] = []
    while ready:
        node_id = ready.pop(0)
        visited.append(node_id)
        for target_id in sorted(outgoing[node_id], key=int):
            incoming[target_id].remove(node_id)
            if not incoming[target_id]:
                ready.append(target_id)
                ready.sort(key=int)
    if len(visited) != len(node_ids):
        raise RuntimeError(f"{recipe_name}: graph contains a cycle")

    if prompt.get("12", {}).get("class_type") != "SaveVideo":
        raise RuntimeError(f"{recipe_name}: node 12 is not the SaveVideo terminal")
    reachable = {"12"}
    stack = ["12"]
    while stack:
        target_id = stack.pop()
        for source_id in original_incoming[target_id]:
            if source_id not in reachable:
                reachable.add(source_id)
                stack.append(source_id)
    if reachable != node_ids:
        unreachable = sorted(node_ids - reachable, key=int)
        raise RuntimeError(
            f"{recipe_name}: nodes do not reach SaveVideo: {unreachable}"
        )


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
            f"expected one required-value assertion for {node_id}.{input_name}, "
            f"found {len(matches)}"
        )
    matches[0]["equals"] = value


def load_source() -> dict[str, Any]:
    raw = require_hash(
        SOURCE_RECIPE,
        EXPECTED_SOURCE_RECIPE_SHA256,
        "rendered H3 RefAudio topology source",
    )
    require_hash(PORTRAIT_FIXTURE, PORTRAIT_SHA256, "portrait fixture")
    require_hash(TTS_FIXTURE, TTS_SHA256, "raw TTS dialogue fixture")
    source = json.loads(raw.decode("utf-8"))
    if source.get("name") != "h3_r2v_refaudio_tts_lipsync":
        raise RuntimeError("hash-pinned topology source has unexpected identity")
    return source


def exact_experiment_metadata() -> dict[str, Any]:
    return {
        "campaign": "h3_ref2va_exact_ordered_lipsync_pair_v1",
        "variant": "portrait_plus_raw_tts_only",
        "matrix_role": "two-take exact-fixture H3 character-lane decision",
        "independent_variable": "random_noise_seed",
        "pair_recipe_names": [SEED42_NAME, SEED43_NAME],
        "pair_seeds": list(SEEDS),
        "fixture_policy": (
            "Exactly portrait.png as Picture 1 and raw tts_dialogue.wav as Audio 1; "
            "no scene image, derived audio, video, first frame, or last frame"
        ),
        "prompt_policy": (
            "Exact action prompt requests a medium close speaking performance with "
            "lip movements matching Audio 1 precisely"
        ),
        "conditioning_policy": (
            "Raw LoadAudio feeds only MiniMaxH3ReferenceToVideo."
            "ref_audios.ref_audio_0"
        ),
        "output_audio_policy": (
            "CreateVideo receives only VAEDecodeAudio decoded from the sampled "
            "target audiovisual latent"
        ),
        "external_source_mux": False,
        "render_status": "unrendered",
        "behavioral_claim_status": "unrendered and unproven",
        "required_human_gate": "Jeffrey judges visible lip synchronization",
        "topology_source_recipe": "recipes/h3_r2v_refaudio_tts_lipsync.json",
        "topology_source_recipe_sha256": EXPECTED_SOURCE_RECIPE_SHA256,
        "topology_source_mutation_policy": (
            "Source is historical rendered evidence and is read-only; replacements "
            "receive new immutable identities"
        ),
        "pairwise_execution_diff_whitelist": [
            "prompt.5.inputs.noise_seed",
            "prompt.12.inputs.filename_prefix",
        ],
    }


def exact_topology_contract(
    source_topology: dict[str, Any], seed: int, output_prefix: str
) -> dict[str, Any]:
    topology = copy.deepcopy(source_topology)
    topology["profile"] = "minimax_h3_ref2va_exact_portrait_raw_tts_v1"
    topology["intent"] = (
        "Official Ref2VA and res_multistep/simple/20 topology with exactly one "
        "portrait and one raw standalone dialogue reference; delivered audio is "
        "the model-native target latent decode only"
    )
    topology["origin"] = {
        "builder": "scratch/build_h3_refaudio_exact_lipsync_pair.py",
        "source_recipe": "recipes/h3_r2v_refaudio_tts_lipsync.json",
        "source_recipe_sha256": EXPECTED_SOURCE_RECIPE_SHA256,
        "source_recipe_edited": False,
        "original_implementation": True,
        "third_party_workflow_json_copied": False,
    }
    topology["installed_schema"]["reference_socket_paths"] = [
        "ref_images.ref_image_0",
        "ref_audios.ref_audio_0",
    ]
    topology["fixture_hashes"] = {
        "portrait.png": PORTRAIT_SHA256,
        "tts_dialogue.wav": TTS_SHA256,
    }
    topology["required_nodes"] = copy.deepcopy(EXPECTED_NODE_CLASSES)
    topology["required_connections"].pop("7.ref_images.ref_image_1", None)
    topology["required_absent_inputs"] = sorted(
        set(topology["required_absent_inputs"])
        | {"7.ref_images.ref_image_1"}
    )
    topology["required_absent_sockets"] = sorted(
        set(topology["required_absent_sockets"])
        | {"7.ref_images.ref_image_1"}
    )
    topology["required_input_values"] = [
        assertion
        for assertion in topology["required_input_values"]
        if assertion.get("node") != "17"
    ]
    replace_required_value(topology, "5", "noise_seed", seed)
    replace_required_value(topology, "7", "prompt", ACTION_PROMPT)
    topology["required_input_values"].extend(
        [
            {"node": "16", "input": "audio", "equals": "tts_dialogue.wav"},
            {
                "node": "12",
                "input": "filename_prefix",
                "equals": output_prefix,
            },
        ]
    )
    topology["audio_path_contract"] = {
        "conditioning_source": "16.LoadAudio -> 7.ref_audios.ref_audio_0",
        "sampled_target": (
            "7.LATENT -> 8.SamplerCustomAdvanced -> 15.VAEDecodeAudio"
        ),
        "delivery": "15.AUDIO -> 10.CreateVideo.audio",
        "create_video_audio_required": ["15", 0],
        "create_video_audio_forbidden": ["16", 0],
        "external_source_mux": False,
    }
    topology["matrix_diff_whitelist"] = [
        "name",
        "prompt.5.inputs.noise_seed",
        "prompt.12.inputs.filename_prefix",
        "topology_contract.required_input_values[seed].equals",
        "topology_contract.required_input_values[prefix].equals",
    ]
    topology["intentional_divergences"] = [
        "The official UI subgraph is flattened to the pinned local API prompt",
        "The lab canvas is 864x480 at 124 frames and 24 fps",
        "portrait.png is the only image and is ordered as Picture 1",
        "raw tts_dialogue.wav is the only audio and is ordered as Audio 1",
        "there is no Picture 2 socket, tag, scene image, video, first frame, or last frame",
        "source audio never connects to CreateVideo; only sampled target audio is decoded",
    ]
    return topology


def build_recipe(name: str, seed: int, output_prefix: str) -> dict[str, Any]:
    if (name, seed, output_prefix) not in {
        (SEED42_NAME, 42, SEED42_PREFIX),
        (SEED43_NAME, 43, SEED43_PREFIX),
    }:
        raise ValueError("exact pair identity/seed/prefix tuple is not authorized")

    source = load_source()
    prompt = copy.deepcopy(source["prompt"])
    prompt.pop("17")
    prompt["5"]["inputs"]["noise_seed"] = seed
    prompt["7"]["inputs"].pop("ref_images.ref_image_1")
    prompt["7"]["inputs"]["prompt"] = ACTION_PROMPT
    prompt["16"]["inputs"] = {"audio": "tts_dialogue.wav"}
    prompt["12"]["inputs"]["filename_prefix"] = output_prefix
    prompt = dict(sorted(prompt.items(), key=lambda item: int(item[0])))

    recipe = {
        "name": name,
        "tier": "experiment",
        "blocked": False,
        "experiment": exact_experiment_metadata(),
        "contract": copy.deepcopy(source["contract"]),
        "topology_contract": exact_topology_contract(
            source["topology_contract"], seed, output_prefix
        ),
        "prompt": prompt,
        "workflow": copy.deepcopy(source["workflow"]),
    }
    recipe["contract"]["reference_audio_duration_s"] = 10.0
    validate_recipe(recipe, seed, output_prefix)
    return recipe


def build_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    seed42 = build_recipe(SEED42_NAME, 42, SEED42_PREFIX)
    seed43 = build_recipe(SEED43_NAME, 43, SEED43_PREFIX)
    validate_pair(seed42, seed43)
    return seed42, seed43


def validate_recipe(recipe: dict[str, Any], seed: int, output_prefix: str) -> None:
    prompt = recipe["prompt"]
    classes = {
        node_id: node.get("class_type") for node_id, node in prompt.items()
    }
    if classes != EXPECTED_NODE_CLASSES:
        raise RuntimeError(f"{recipe['name']}: exact node set drift: {classes!r}")
    if "17" in prompt:
        raise RuntimeError(f"{recipe['name']}: scene image node 17 survived")

    image_nodes = [
        (node_id, node)
        for node_id, node in prompt.items()
        if node.get("class_type") == "LoadImage"
    ]
    audio_nodes = [
        (node_id, node)
        for node_id, node in prompt.items()
        if node.get("class_type") == "LoadAudio"
    ]
    if image_nodes != [("11", {"class_type": "LoadImage", "inputs": {"image": "portrait.png"}})]:
        raise RuntimeError(f"{recipe['name']}: exact portrait fixture set changed")
    if audio_nodes != [("16", {"class_type": "LoadAudio", "inputs": {"audio": "tts_dialogue.wav"}})]:
        raise RuntimeError(f"{recipe['name']}: exact raw TTS fixture set changed")

    ref_inputs = prompt["7"]["inputs"]
    reference_keys = {
        key
        for key in ref_inputs
        if key.startswith("ref_images.")
        or key.startswith("ref_audios.")
        or key.startswith("ref_videos.")
        or key.startswith("ref_video_audios.")
    }
    if reference_keys != {
        "ref_images.ref_image_0",
        "ref_audios.ref_audio_0",
    }:
        raise RuntimeError(
            f"{recipe['name']}: exact reference socket set changed: {reference_keys}"
        )
    if ref_inputs["ref_images.ref_image_0"] != ["11", 0]:
        raise RuntimeError(f"{recipe['name']}: Picture 1 ordering changed")
    if ref_inputs["ref_audios.ref_audio_0"] != ["16", 0]:
        raise RuntimeError(f"{recipe['name']}: Audio 1 ordering changed")
    if ref_inputs["ref_image_size"] != "match":
        raise RuntimeError(f"{recipe['name']}: ref_image_size must remain match")
    if ref_inputs["prompt"] != ACTION_PROMPT:
        raise RuntimeError(f"{recipe['name']}: action prompt changed")
    tags = set(re.findall(r"<(?:Picture|Video|Audio) \d+>", ACTION_PROMPT))
    if tags != {"<Picture 1>", "<Audio 1>"}:
        raise RuntimeError(f"{recipe['name']}: reference tags changed: {tags}")

    encoded = canonical_json_bytes(recipe)
    if b"scene_still.png" in encoded or b"<Picture 2>" in encoded:
        raise RuntimeError(f"{recipe['name']}: removed Picture 2 fixture/tag survived")
    if source_consumers(prompt, "16") != {("7", "ref_audios.ref_audio_0")}:
        raise RuntimeError(f"{recipe['name']}: raw source audio escaped conditioning")
    audio_decoders = [
        node_id
        for node_id, node in prompt.items()
        if node.get("class_type") == "VAEDecodeAudio"
    ]
    if audio_decoders != ["15"]:
        raise RuntimeError(f"{recipe['name']}: target audio decoder set changed")
    if prompt["15"]["inputs"] != {"samples": ["8", 0], "vae": ["4", 0]}:
        raise RuntimeError(f"{recipe['name']}: native target audio decode changed")
    if prompt["10"]["inputs"].get("audio") != ["15", 0]:
        raise RuntimeError(f"{recipe['name']}: CreateVideo does not use target audio")

    if prompt["5"]["inputs"] != {"noise_seed": seed}:
        raise RuntimeError(f"{recipe['name']}: exact seed changed")
    if prompt["12"]["inputs"]["filename_prefix"] != output_prefix:
        raise RuntimeError(f"{recipe['name']}: output prefix changed")
    if prompt["13"]["inputs"] != {"sampler_name": "res_multistep"}:
        raise RuntimeError(f"{recipe['name']}: sampler family changed")
    if prompt["14"]["inputs"] != {
        "model": ["1", 0],
        "scheduler": "simple",
        "steps": 20,
        "denoise": 1.0,
    }:
        raise RuntimeError(f"{recipe['name']}: simple/20 scheduler topology changed")
    if prompt["1"]["inputs"] != {
        "unet_name": UNET_NAME,
        "weight_dtype": "default",
    }:
        raise RuntimeError(f"{recipe['name']}: Ref2VA model pin changed")
    if prompt["2"]["inputs"]["clip_name"] != CLIP_NAME:
        raise RuntimeError(f"{recipe['name']}: text encoder pin changed")
    if prompt["3"]["inputs"] != {"vae_name": VIDEO_VAE_NAME}:
        raise RuntimeError(f"{recipe['name']}: video VAE pin changed")
    if prompt["4"]["inputs"] != {"vae_name": AUDIO_VAE_NAME}:
        raise RuntimeError(f"{recipe['name']}: audio VAE pin changed")
    validate_dag(prompt, recipe["name"])


def _mirrored_value_paths(recipe: dict[str, Any]) -> tuple[str, str]:
    values = recipe["topology_contract"]["required_input_values"]
    seed_indexes = [
        index
        for index, assertion in enumerate(values)
        if (assertion.get("node"), assertion.get("input"))
        == ("5", "noise_seed")
    ]
    prefix_indexes = [
        index
        for index, assertion in enumerate(values)
        if (assertion.get("node"), assertion.get("input"))
        == ("12", "filename_prefix")
    ]
    if len(seed_indexes) != 1 or len(prefix_indexes) != 1:
        raise RuntimeError("seed/prefix topology mirrors are not unique")
    return (
        f"topology_contract.required_input_values[{seed_indexes[0]}].equals",
        f"topology_contract.required_input_values[{prefix_indexes[0]}].equals",
    )


def validate_pair(seed42: dict[str, Any], seed43: dict[str, Any]) -> None:
    execution_diff = difference_paths(seed42["prompt"], seed43["prompt"])
    expected_execution_diff = {
        "5.inputs.noise_seed",
        "12.inputs.filename_prefix",
    }
    if execution_diff != expected_execution_diff:
        raise RuntimeError(
            f"pair execution drift is not seed/prefix-only: {sorted(execution_diff)}"
        )

    seed_path, prefix_path = _mirrored_value_paths(seed42)
    full_diff = difference_paths(seed42, seed43)
    expected_full_diff = {
        "name",
        "prompt.5.inputs.noise_seed",
        "prompt.12.inputs.filename_prefix",
        seed_path,
        prefix_path,
    }
    if full_diff != expected_full_diff:
        raise RuntimeError(
            f"pair drift exceeds identity/seed/prefix: {sorted(full_diff)}"
        )


def immutable_write(path: Path, payload: bytes) -> bool:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Immutable generated recipe differs: {path}")
        return False
    path.write_bytes(payload)
    return True


def write_pair(output_dir: Path = RECIPES) -> dict[str, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, bool] = {}
    for recipe in build_pair():
        path = output_dir / f"{recipe['name']}.json"
        payload = canonical_json_bytes(recipe)
        changed = immutable_write(path, payload)
        if path.read_bytes() != payload:
            raise RuntimeError(f"generated recipe did not round-trip exactly: {path}")
        outcomes[recipe["name"]] = changed
    return outcomes


def main() -> None:
    for name, changed in write_pair().items():
        print(f"{name}: {'created' if changed else 'unchanged'}")


if __name__ == "__main__":
    main()
