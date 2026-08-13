#!/usr/bin/env python3
"""Build the two closed H3 origin prompt-only recipes without rendering.

The primary recipe preserves the exact prompt from ``h3_r2v_best`` while
removing the picture loader and every reference-image connection.  The
fallback removes only the first ``<Picture 1>`` sentence and is not authorized
unless the primary produces a specific retained reference/tag refusal.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
SOURCE = RECIPES / "h3_r2v_best.json"
RUNNER = ROOT / "run_recipe.py"

SOURCE_SHA256 = "20e584cc016bdc5bdb857b00923c7ae838174724e3c20be0dfc322a809392eda"
PICTURE_SENTENCE = (
    "Use <Picture 1> as the exact character identity and appearance reference. "
)
ORIGIN_PROMPT = (
    "Use <Picture 1> as the exact character identity and appearance reference. "
    "Place that person in a vintage radio control room under warm analog lighting; "
    "preserve their face, hair, clothing, and proportions while the camera makes a "
    "slow cinematic move."
)
FALLBACK_PROMPT = ORIGIN_PROMPT.removeprefix(PICTURE_SENTENCE)

PRIMARY_NAME = "h3_music_followup_origin_prompt_only_exact_seed42_f124"
FALLBACK_NAME = (
    "h3_music_followup_origin_prompt_only_no_picture_sentence_seed42_f124"
)
MANAGER_LOG_SUBSTRING = "network_mode: offline"
ELEVATED_BASELINE_STAMP = (
    "elevated-baseline lane, operator-authorized 2026-08-10"
)
FALLBACK_ERROR_STAGES = frozenset({"prompt_validation", "node_runtime"})
FALLBACK_ERROR_MARKERS = (
    "<picture 1>",
    "picture 1",
    "picture reference",
    "reference image",
    "ref_image",
    "ref_images",
    "no reference",
)


class BuildError(RuntimeError):
    """Raised when a pinned source or generated invariant drifts."""


@dataclass(frozen=True)
class OriginVariant:
    name: str
    prompt: str
    conditional_fallback: bool

    @property
    def path(self) -> Path:
        return RECIPES / f"{self.name}.json"

    @property
    def output_prefix(self) -> str:
        return f"{self.name}_out"


PRIMARY = OriginVariant(PRIMARY_NAME, ORIGIN_PROMPT, False)
FALLBACK = OriginVariant(FALLBACK_NAME, FALLBACK_PROMPT, True)


def variants() -> tuple[OriginVariant, OriginVariant]:
    return PRIMARY, FALLBACK


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def load_source() -> dict[str, Any]:
    if not SOURCE.is_file():
        raise BuildError(f"missing pinned source: {SOURCE}")
    raw = SOURCE.read_bytes()
    actual = sha256_bytes(raw)
    if actual != SOURCE_SHA256:
        raise BuildError(f"source SHA drift: {actual} != {SOURCE_SHA256}")
    try:
        source = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"invalid UTF-8 JSON source: {exc}") from exc
    if source.get("prompt", {}).get("7", {}).get("inputs", {}).get("prompt") != ORIGIN_PROMPT:
        raise BuildError("pinned source no longer contains the exact origin prompt")
    return source


def _load_runner() -> Any:
    module_name = "_h3_origin_prompt_only_runner_contract"
    spec = importlib.util.spec_from_file_location(module_name, RUNNER)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load local runner: {RUNNER}")
    root_text = str(ROOT)
    inserted = root_text not in sys.path
    if inserted:
        sys.path.insert(0, root_text)
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(root_text)
    return module


def current_runner_contracts() -> dict[str, Any]:
    """Return and validate the current hard-idle contracts without I/O probes."""

    runner = _load_runner()
    preboot = runner.gpu_idle_gate_contract()
    operator = runner.operator_idle_policy_contract()
    prequeue = runner.prequeue_known_workload_scan_contract()
    policy = preboot.get("policy") or {}
    if policy.get("maximum_vram_used_mib") != 3072.0:
        raise BuildError("runner preboot maximum is not exactly 3072 MiB")
    if policy.get("vram_used_mib_threshold_gating") is not True:
        raise BuildError("runner preboot 3.0 GiB threshold is not gating")
    if operator.get("preboot_baseline_maximum_mib") != 3072.0:
        raise BuildError("runner operator baseline maximum is not exactly 3072 MiB")
    if operator.get("preboot_baseline_threshold_gating") is not True:
        raise BuildError("runner operator 3.0 GiB threshold is not gating")
    if operator.get("elevated_baseline_threshold_mib") != 2048.0:
        raise BuildError("runner elevated-baseline threshold is not exactly 2048 MiB")
    if operator.get("elevated_baseline_stamp") != ELEVATED_BASELINE_STAMP:
        raise BuildError("runner elevated-baseline stamp drifted")
    if operator.get("known_render_compute_processes_block") is not True:
        raise BuildError("runner no longer blocks known render/compute processes")
    if operator.get("net_peak_formula") != "peak_vram_gb - baseline_vram_gb":
        raise BuildError("runner net-peak formula drifted")
    if (preboot.get("collector") or {}).get("sha256") != sha256_file(RUNNER):
        raise BuildError("runner collector contract does not bind current bytes")
    return {
        "runner": {
            "path": str(RUNNER.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(RUNNER),
        },
        "preboot_gpu_idle_gate_contract": preboot,
        "operator_idle_policy": operator,
        "prequeue_known_workload_scan_contract": prequeue,
    }


def fallback_authorization_errors(evidence: Any) -> list[str]:
    """Fail closed unless evidence proves the one authorized fallback trigger."""

    if not isinstance(evidence, dict):
        return ["fallback evidence must be a dictionary"]
    errors: list[str] = []
    if evidence.get("primary_recipe") != PRIMARY_NAME:
        errors.append("evidence is not bound to the primary recipe")
    if evidence.get("primary_prompt_submission_attempted") is not True:
        errors.append("primary prompt submission was not attempted")
    if evidence.get("primary_artifact_absent") is not True:
        errors.append("primary artifact absence was not proven")
    if evidence.get("error_stage") not in FALLBACK_ERROR_STAGES:
        errors.append("error stage is not prompt validation or node runtime")
    if str(evidence.get("error_node_id")) != "7":
        errors.append("error is not bound to node 7")
    if evidence.get("error_class_type") != "MiniMaxH3ReferenceToVideo":
        errors.append("error is not bound to MiniMaxH3ReferenceToVideo")
    error_text = evidence.get("error_text")
    if not isinstance(error_text, str) or not error_text.strip():
        errors.append("retained error text is absent")
    elif not any(marker in error_text.lower() for marker in FALLBACK_ERROR_MARKERS):
        errors.append("retained error text does not identify a picture/reference refusal")
    return errors


def fallback_is_authorized(evidence: Any) -> bool:
    return not fallback_authorization_errors(evidence)


def _replace_required_value(
    assertions: list[dict[str, Any]], node: str, input_name: str, value: Any
) -> None:
    assertions[:] = [
        row
        for row in assertions
        if not (str(row.get("node")) == node and row.get("input") == input_name)
    ]
    assertions.append({"node": node, "input": input_name, "equals": value})


def build_recipe(
    variant: OriginVariant, *, runner_contracts: dict[str, Any] | None = None
) -> dict[str, Any]:
    if variant not in variants():
        raise BuildError("unknown origin variant")
    source = load_source()
    contracts = copy.deepcopy(runner_contracts or current_runner_contracts())
    recipe = copy.deepcopy(source)
    recipe["name"] = variant.name
    recipe["tier"] = "experiment"
    recipe["blocked"] = False
    recipe["contract"].update(
        {
            "engine": "minimax_h3",
            "mode": "r2v_prompt_only_origin_test",
            "width": 832,
            "height": 480,
            "frames": 124,
            "fps": 24.0,
            "duration_s": round(124 / 24.0, 6),
            "requires_audio": True,
            "requires_manager_offline_probe": True,
            "vram_ceiling_gb": 14.5,
        }
    )

    graph = recipe["prompt"]
    graph.pop("11", None)
    graph["5"]["inputs"]["noise_seed"] = 42
    inputs = graph["7"]["inputs"]
    inputs.pop("ref_images.ref_image_0", None)
    inputs.pop("ref_images", None)
    inputs["prompt"] = variant.prompt
    inputs["width"] = 832
    inputs["height"] = 480
    inputs["length"] = 124
    graph["12"]["inputs"]["filename_prefix"] = variant.output_prefix

    topology = recipe["topology_contract"]
    topology["intent"] = (
        "Prompt-only MiniMax H3 Ref2VA graph: exact origin text experiment with "
        "no LoadImage node, no picture/reference connection, and untouched jointly "
        "sampled native audio"
    )
    topology["required_nodes"].pop("11", None)
    topology["required_class_types"] = [
        value
        for value in topology["required_class_types"]
        if value != "LoadImage"
    ]
    topology["required_connections"].pop("7.ref_images.ref_image_0", None)
    absent = topology["required_absent_inputs"]
    if "7.ref_images.ref_image_0" not in absent:
        absent.append("7.ref_images.ref_image_0")
    assertions = topology["required_input_values"]
    for node, input_name, value in (
        ("5", "noise_seed", 42),
        ("7", "prompt", variant.prompt),
        ("7", "width", 832),
        ("7", "height", 480),
        ("7", "length", 124),
        ("7", "ref_image_size", "match"),
        ("12", "filename_prefix", variant.output_prefix),
    ):
        _replace_required_value(assertions, node, input_name, value)
    topology["intentional_divergences"] = [
        "Derived from the SHA-pinned current h3_r2v_best Ref2VA graph",
        "The LoadImage node and every picture/reference input are absent",
        "Canvas is the operator-requested 832x480; seed 42 and length 124 are fixed",
        (
            "Primary preserves the exact origin prompt verbatim"
            if not variant.conditional_fallback
            else "Fallback removes only the first dangling <Picture 1> sentence"
        ),
        "Sampled native audio remains connected through VAEDecodeAudio to CreateVideo",
        "Unique output prefix is evidence plumbing only",
    ]

    recipe["origin_test"] = {
        "schema_version": 1,
        "campaign": "H3_MUSIC_FOLLOWUP_ORIGIN_PROMPT_ONLY",
        "variant": "fallback-no-picture-sentence" if variant.conditional_fallback else "primary-exact-origin-prompt",
        "source_recipe": {
            "path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": SOURCE_SHA256,
        },
        "source_prompt_sha256": sha256_bytes(ORIGIN_PROMPT.encode("utf-8")),
        "prompt_is_verbatim_origin": not variant.conditional_fallback,
        "no_image_node": True,
        "no_reference_image_input": True,
        "single_cold_review_leg": True,
        "warm_certification_claimed": False,
        "manager_offline_gate": {
            "required": True,
            "required_server_log_substring": MANAGER_LOG_SUBSTRING,
            "must_be_observed_before_prompt_post": True,
            "runner_flag": "--manager-offline-test",
            "phase": "cold",
        },
        "boot_requirements": {
            "server": "127.0.0.1:8199 owned lab server",
            "sage_attention_allowed": False,
            "disable_pinned_memory_required": True,
            "cache_mode": "classic",
            "reserve_vram_gib": 12,
        },
        "runner_contracts": contracts,
        "completion_timeout_s": 2400,
        "native_audio_path": "SamplerCustomAdvanced -> VAEDecodeAudio -> CreateVideo.audio",
        "external_mux": False,
        "quality_judgment": "PENDING_HUMAN",
        "authorization": (
            {
                "default_authorized": False,
                "conditional_only": True,
                "primary_recipe": PRIMARY_NAME,
                "required_error_stages": sorted(FALLBACK_ERROR_STAGES),
                "required_error_node_id": "7",
                "required_error_class_type": "MiniMaxH3ReferenceToVideo",
                "required_error_text_markers_any": list(FALLBACK_ERROR_MARKERS),
                "primary_prompt_submission_attempted_required": True,
                "primary_artifact_absent_required": True,
                "does_not_authorize": [
                    "preboot or prequeue gate refusal",
                    "Manager offline-gate refusal",
                    "timeout",
                    "OOM or VRAM ceiling failure",
                    "server boot failure",
                    "operator interruption",
                ],
            }
            if variant.conditional_fallback
            else {
                "default_authorized": True,
                "conditional_only": False,
                "fallback_recipe": FALLBACK_NAME,
                "fallback_allowed_only_on_specific_retained_reference_tag_refusal": True,
            }
        ),
    }
    validate_generated_recipe(recipe, variant, contracts)
    return recipe


def _local_topology_errors(recipe: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    graph = recipe.get("prompt") or {}
    topology = recipe.get("topology_contract") or {}
    required_nodes = topology.get("required_nodes") or {}
    if set(graph) != set(required_nodes):
        errors.append("exact node set does not match required_nodes")
    for node_id, class_type in required_nodes.items():
        if graph.get(node_id, {}).get("class_type") != class_type:
            errors.append(f"node {node_id} class_type drift")
    for socket, expected in (topology.get("required_connections") or {}).items():
        node_id, input_name = socket.split(".", 1)
        actual = graph.get(node_id, {}).get("inputs", {}).get(input_name)
        if actual != expected:
            errors.append(f"connection {socket} drift")
    for row in topology.get("required_input_values") or []:
        node_id = str(row["node"])
        actual = graph.get(node_id, {}).get("inputs", {}).get(row["input"])
        if actual != row["equals"]:
            errors.append(f"value {node_id}.{row['input']} drift")
    for socket in topology.get("required_absent_inputs") or []:
        node_id, input_name = socket.split(".", 1)
        if input_name in graph.get(node_id, {}).get("inputs", {}):
            errors.append(f"absent input {socket} is present")
    reachable = {str(topology.get("terminal_node"))}
    stack = list(reachable)
    while stack:
        current = stack.pop()
        for value in graph.get(current, {}).get("inputs", {}).values():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and value[0] in graph
                and value[0] not in reachable
            ):
                reachable.add(value[0])
                stack.append(value[0])
    if reachable != set(graph):
        errors.append("not every graph node reaches the terminal SaveVideo node")
    return errors


def validate_generated_recipe(
    recipe: dict[str, Any],
    variant: OriginVariant,
    runner_contracts: dict[str, Any],
) -> None:
    if recipe.get("name") != variant.name:
        raise BuildError("generated name drift")
    graph = recipe.get("prompt") or {}
    inputs = graph.get("7", {}).get("inputs", {})
    classes = [node.get("class_type") for node in graph.values()]
    if "11" in graph or "LoadImage" in classes:
        raise BuildError("generated recipe retained an image node")
    if any(key == "ref_images" or key.startswith("ref_images.") for key in inputs):
        raise BuildError("generated recipe retained a reference-image input")
    if any(
        key.startswith("ref_audios")
        or key.startswith("ref_videos")
        or key.startswith("ref_video_audios")
        for key in inputs
    ):
        raise BuildError("generated recipe retained another reference input")
    if inputs.get("prompt") != variant.prompt:
        raise BuildError("generated prompt drift")
    if (inputs.get("width"), inputs.get("height"), inputs.get("length")) != (
        832,
        480,
        124,
    ):
        raise BuildError("generated canvas or frame length drift")
    if graph.get("5", {}).get("inputs", {}).get("noise_seed") != 42:
        raise BuildError("generated seed drift")
    if graph.get("15", {}).get("inputs") != {"samples": ["8", 0], "vae": ["4", 0]}:
        raise BuildError("native sampled audio decode drift")
    if graph.get("10", {}).get("inputs", {}).get("audio") != ["15", 0]:
        raise BuildError("native audio is not connected to CreateVideo")
    if graph.get("12", {}).get("inputs", {}).get("filename_prefix") != variant.output_prefix:
        raise BuildError("generated output prefix drift")
    origin = recipe.get("origin_test") or {}
    if origin.get("runner_contracts") != runner_contracts:
        raise BuildError("generated runner contracts drift")
    if origin.get("quality_judgment") != "PENDING_HUMAN":
        raise BuildError("generated quality status is not PENDING_HUMAN")
    if variant.conditional_fallback:
        if origin.get("authorization", {}).get("default_authorized") is not False:
            raise BuildError("fallback is incorrectly authorized by default")
    elif origin.get("authorization", {}).get("default_authorized") is not True:
        raise BuildError("primary is not authorized")
    runner = _load_runner()
    autogrow_errors = runner.minimax_h3_autogrow_input_errors(graph)
    if autogrow_errors:
        raise BuildError(f"generated autogrow inputs are invalid: {autogrow_errors}")
    topology_errors = _local_topology_errors(recipe)
    if topology_errors:
        raise BuildError(f"generated topology is invalid: {topology_errors}")


def build_all() -> dict[str, dict[str, Any]]:
    contracts = current_runner_contracts()
    generated = {
        variant.name: build_recipe(variant, runner_contracts=contracts)
        for variant in variants()
    }
    left = copy.deepcopy(generated[PRIMARY_NAME]["prompt"])
    right = copy.deepcopy(generated[FALLBACK_NAME]["prompt"])
    left["7"]["inputs"]["prompt"] = "<variant-prompt>"
    right["7"]["inputs"]["prompt"] = "<variant-prompt>"
    left["12"]["inputs"]["filename_prefix"] = "<evidence-prefix>"
    right["12"]["inputs"]["filename_prefix"] = "<evidence-prefix>"
    if left != right:
        raise BuildError("primary/fallback generation graphs differ beyond prompt/prefix")
    return generated


def write_recipes(generated: dict[str, dict[str, Any]]) -> None:
    RECIPES.mkdir(parents=True, exist_ok=True)
    for name, recipe in generated.items():
        path = RECIPES / f"{name}.json"
        encoded = canonical_json(recipe)
        if path.exists() and path.read_bytes() != encoded:
            raise BuildError(f"refusing to overwrite drifted materialized recipe: {path}")
        if not path.exists():
            path.write_bytes(encoded)


def plan(generated: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "campaign": "H3_MUSIC_FOLLOWUP_ORIGIN_PROMPT_ONLY",
        "render_order": [PRIMARY_NAME, FALLBACK_NAME],
        "primary_render_legs": 1,
        "fallback_max_render_legs": 1,
        "fallback_default_authorized": False,
        "recipes": [
            {
                "name": variant.name,
                "path": str(variant.path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_bytes(canonical_json(generated[variant.name])),
                "conditional_fallback": variant.conditional_fallback,
            }
            for variant in variants()
        ],
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    generated = build_all()
    if args.write:
        write_recipes(generated)
    print(json.dumps(plan(generated), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
