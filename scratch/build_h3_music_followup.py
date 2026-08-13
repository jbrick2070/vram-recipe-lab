#!/usr/bin/env python3
"""Build the queued H3 music follow-up recipes without rendering anything.

The builder is deliberately flat-V3-only.  The historical music-positive
recipe is bound only by a receipt SHA; its exact bytes are no longer present.
Consequently Job 1 is emitted as a structural/provenance finding and never as
an executable nested-container recipe.
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
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = ROOT / "recipes"
SCORE_SOURCE = RECIPES_DIR / "h3_unconditioned_music_score_seed42_f124.json"
FLAT_SOURCE = RECIPES_DIR / "h3_r2v_best.json"
ORIGIN_RECEIPT = ROOT / "results" / "h3_r2v_best_run1.json"
ORIGIN_ARTIFACT = ROOT / "outputs" / "h3_r2v_best_out_00001_.mp4"
RUNNER = ROOT / "run_recipe.py"

SCORE_SOURCE_SHA256 = "52a4e231b3314d619bcf87b5d62a6bfedfd28e37a4c038638fc1bc896db199f8"
FLAT_SOURCE_SHA256 = "20e584cc016bdc5bdb857b00923c7ae838174724e3c20be0dfc322a809392eda"
ORIGIN_RECEIPT_SHA256 = "561b79dd88acf9aae9bbe19f62974a2eb59900b8fadb60592479fb1307e6c3f8"
ORIGIN_ARTIFACT_SHA256 = "51d803d53a61e67d3e2dd5772f817da6edc1b8bdc5571e851463037adf2d2d5f"
MISSING_PINNED_OLD_RECIPE_SHA256 = (
    "599718d4ee5b1a04309a4352cded8167c4e51075a9f858bdbf3468a53aae6a4e"
)
NEAREST_NESTED_GIT_COMMIT = "b4fb869c8bc98bb5b9d1c713a3428f5e1ff698d4"
NEAREST_NESTED_GIT_BLOB = "c2eaa864aec7c336d7acabb04847f95c4f597b63"
NEAREST_NESTED_SHA256 = "b81a51f7cbdd3ddfb058505bd12cea10561706cb15a00419cea876f2ebaf03b1"

PREFIX = "h3_music_followup_"
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
EXPECTED_NESTED_REJECTION = (
    "Node 7 (MiniMaxH3ReferenceToVideo) input 'ref_images' is a nested V3 "
    "autogrow container that ComfyUI ignores; use direct dotted sockets such "
    "as 'ref_images.ref_image_0'"
)
IDENTITY_SENTENCE = (
    "Use <Picture 1> as the exact character identity and appearance reference. "
)
PRESERVATION_SENTENCE = (
    "Preserve their face, hair, clothing, and proportions while the camera "
    "makes a slow cinematic move. "
)
DIM_SCENE = (
    "Place that person in a dim, hushed vintage radio control room. "
)
BRIGHT_SCENE = (
    "Place that person in a bright, lively radio control room with morning "
    "light and bustling activity. "
)


class BuildError(RuntimeError):
    """Raised when pinned sources or generated recipe invariants drift."""


@dataclass(frozen=True)
class FollowupSpec:
    order: int
    job: int
    cell: str
    name: str
    prompt: str
    seed: int
    frames: int
    timeout_s: int

    @property
    def recipe_path(self) -> Path:
        return RECIPES_DIR / f"{self.name}.json"

    @property
    def output_prefix(self) -> str:
        return f"{self.name}_out"

    @property
    def expected_artifact_name(self) -> str:
        return f"{self.output_prefix}_00001_.mp4"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def score_prompt() -> str:
    source = load_pinned_json(SCORE_SOURCE, SCORE_SOURCE_SHA256)
    return str(source["prompt"]["7"]["inputs"]["prompt"])


def _mood_prompt(scene: str, soundtrack: str) -> str:
    return IDENTITY_SENTENCE + scene + PRESERVATION_SENTENCE + soundtrack


def followup_specs() -> tuple[FollowupSpec, ...]:
    """Return the exact authorized flat-V3 execution order.

    Job 1 is intentionally absent.  It is a structural finding until an
    independently durable compatibility preflight can accept a reconstruction.
    The conditional bonus is also intentionally absent pending Jeffrey's choice.
    """

    q4b = score_prompt()
    raw = (
        (2, "2a", "mood_dim_lighthearted_seed42_f124", _mood_prompt(
            DIM_SCENE,
            "The model-native soundtrack is a warm lighthearted orchestral score.",
        ), 42, 124, 2_400),
        (2, "2b", "mood_dim_tense_seed42_f124", _mood_prompt(
            DIM_SCENE,
            "The model-native soundtrack is a tense orchestral drama score.",
        ), 42, 124, 2_400),
        (2, "2c", "mood_bright_lighthearted_seed42_f124", _mood_prompt(
            BRIGHT_SCENE,
            "The model-native soundtrack is a warm lighthearted orchestral score.",
        ), 42, 124, 2_400),
        (2, "2d", "mood_bright_noir_seed42_f124", _mood_prompt(
            BRIGHT_SCENE,
            "The model-native soundtrack is tense driving noir strings.",
        ), 42, 124, 2_400),
        (2, "2e", "mood_dim_ragtime_seed42_f124", _mood_prompt(
            DIM_SCENE,
            "The model-native soundtrack is playful ragtime piano.",
        ), 42, 124, 2_400),
        (3, "seed43", "score_seed43_f124", q4b, 43, 124, 2_400),
        (3, "seed44", "score_seed44_f124", q4b, 44, 124, 2_400),
        (3, "seed45", "score_seed45_f124", q4b, 45, 124, 2_400),
        (3, "seed46", "score_seed46_f124", q4b, 46, 124, 2_400),
        (4, "f192", "score_seed42_f192", q4b, 42, 192, 3_600),
        (4, "f277", "score_seed42_f277", q4b, 42, 277, 5_400),
    )
    return tuple(
        FollowupSpec(
            order=index,
            job=job,
            cell=cell,
            name=PREFIX + suffix,
            prompt=prompt,
            seed=seed,
            frames=frames,
            timeout_s=timeout,
        )
        for index, (job, cell, suffix, prompt, seed, frames, timeout) in enumerate(
            raw, start=1
        )
    )


def load_pinned_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not path.is_file():
        raise BuildError(f"missing pinned source: {path}")
    payload = path.read_bytes()
    actual = sha256_bytes(payload)
    if actual != expected_sha256:
        raise BuildError(f"source SHA drift for {path}: {actual} != {expected_sha256}")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"invalid UTF-8 JSON source {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BuildError(f"source is not a JSON object: {path}")
    return parsed


def _replace_required_value(
    values: list[dict[str, Any]], node: str, input_name: str, replacement: Any
) -> None:
    matches = [
        item
        for item in values
        if item.get("node") == node and item.get("input") == input_name
    ]
    if len(matches) != 1:
        raise BuildError(
            f"expected one topology required value for {node}.{input_name}, found {len(matches)}"
        )
    matches[0]["equals"] = replacement


def build_recipe(spec: FollowupSpec) -> dict[str, Any]:
    source = load_pinned_json(SCORE_SOURCE, SCORE_SOURCE_SHA256)
    recipe = copy.deepcopy(source)
    recipe["name"] = spec.name
    recipe["tier"] = "experiment"
    recipe["contract"]["mode"] = "r2v_unconditioned_music_followup"
    recipe["contract"]["frames"] = spec.frames
    recipe["contract"]["duration_s"] = spec.frames / 24.0

    prompt = recipe["prompt"]
    prompt["5"]["inputs"]["noise_seed"] = spec.seed
    prompt["7"]["inputs"]["prompt"] = spec.prompt
    prompt["7"]["inputs"]["length"] = spec.frames
    prompt["12"]["inputs"]["filename_prefix"] = spec.output_prefix

    topology = recipe["topology_contract"]
    topology["intent"] = (
        "Queued H3 music follow-up on the current flat dotted V3 picture-reference "
        "topology with untouched jointly sampled native audio"
    )
    required_values = topology["required_input_values"]
    _replace_required_value(required_values, "5", "noise_seed", spec.seed)
    _replace_required_value(required_values, "7", "prompt", spec.prompt)
    _replace_required_value(required_values, "7", "length", spec.frames)
    if topology["required_connections"].get("7.ref_images.ref_image_0") != ["11", 0]:
        raise BuildError("source lost the required flat dotted V3 picture socket")
    if "7.ref_images" not in topology["required_absent_inputs"]:
        raise BuildError("source no longer explicitly rejects nested ref_images")
    topology["intentional_divergences"] = [
        "Derived from the pinned mission-1 Q4-B flat-V3 score recipe",
        f"Follow-up Job {spec.job} cell {spec.cell}; exploratory single leg",
        f"Seed {spec.seed}, length {spec.frames}, and the declared prompt are receipt-bound",
        "Unique output prefix is evidence plumbing only",
        "No audio-conditioning input and no external mux are present",
    ]

    recipe.pop("study", None)
    recipe["followup"] = {
        "schema_version": 1,
        "campaign": "H3_MUSIC_FOLLOWUP",
        "execution_order": spec.order,
        "job": spec.job,
        "cell": spec.cell,
        "exploratory_single_leg": True,
        "warm_certification_claimed": False,
        "source_recipe": {
            "path": str(SCORE_SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": SCORE_SOURCE_SHA256,
        },
        "manager_offline_required": True,
        "sage_attention_allowed": False,
        "disable_pinned_memory_required": True,
        "cache_mode": "classic",
        "reserve_vram_gib": 12,
        "completion_timeout_s": spec.timeout_s,
        "preboot_gpu_idle_gate_required": {
            "status": "measured",
            "gate_ran": True,
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
            "display_active_allowed_measured_states": ["Disabled", "Enabled"],
            "display_active_recorded_non_gating": True,
            "port_8199_listener_required_absent": True,
        },
        "operator_idle_policy": {
            "baseline_vram_recorded_advisory": True,
            "baseline_numeric_rejection": False,
            "pair_baseline_drift_gate": "not applicable; exploratory single cold leg",
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
        "post_shutdown_idle_gate_sidecar_required_absent": True,
        "native_audio_path": "SamplerCustomAdvanced -> VAEDecodeAudio -> CreateVideo.audio",
        "quality_judgment": "PENDING_HUMAN",
        "conditional_bonus_authorized": False,
    }
    validate_generated_recipe(recipe, spec)
    return recipe


def validate_generated_recipe(recipe: dict[str, Any], spec: FollowupSpec) -> None:
    if recipe.get("name") != spec.name or not spec.name.startswith(PREFIX):
        raise BuildError("generated recipe name drift")
    nodes = recipe.get("prompt")
    if not isinstance(nodes, dict) or set(nodes) != {
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"
    }:
        raise BuildError("generated recipe node set drift")
    inputs = nodes["7"]["inputs"]
    if inputs.get("ref_images.ref_image_0") != ["11", 0] or "ref_images" in inputs:
        raise BuildError("generated recipe is not flat dotted V3")
    if any(key.startswith("ref_audios") for key in inputs):
        raise BuildError("generated recipe unexpectedly conditions on audio")
    if nodes["10"]["inputs"].get("audio") != ["15", 0]:
        raise BuildError("native audio is not connected to CreateVideo")
    if nodes["15"]["inputs"].get("samples") != ["8", 0]:
        raise BuildError("audio decode is not connected to sampled joint latent")
    if nodes["5"]["inputs"].get("noise_seed") != spec.seed:
        raise BuildError("generated seed drift")
    if inputs.get("prompt") != spec.prompt or inputs.get("length") != spec.frames:
        raise BuildError("generated prompt/length drift")
    if nodes["12"]["inputs"].get("filename_prefix") != spec.output_prefix:
        raise BuildError("generated output prefix drift")
    followup = recipe.get("followup") or {}
    expected_idle = {
        "status": "measured",
        "gate_ran": True,
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
        "redacted_process_schema": list(REDACTED_WORKLOAD_PROCESS_SCHEMA),
        "desktop_graphics_signals_retained_but_not_required": True,
        "display_active_allowed_measured_states": ["Disabled", "Enabled"],
        "display_active_recorded_non_gating": True,
        "port_8199_listener_required_absent": True,
    }
    expected_operator_policy = {
        "baseline_vram_recorded_advisory": True,
        "baseline_numeric_rejection": False,
        "pair_baseline_drift_gate": (
            "not applicable; exploratory single cold leg"
        ),
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
    }
    if followup.get("preboot_gpu_idle_gate_required") != expected_idle:
        raise BuildError("generated idle-gate requirement drift")
    if followup.get("operator_idle_policy") != expected_operator_policy:
        raise BuildError("generated operator idle policy drift")


def _load_runner_validator() -> Any:
    """Load only the local runner module needed for its schema validator."""

    module_name = "_h3_music_followup_runner_validator"
    spec = importlib.util.spec_from_file_location(module_name, RUNNER)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load local schema validator: {RUNNER}")
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
    validator = getattr(module, "minimax_h3_autogrow_input_errors", None)
    if not callable(validator):
        raise BuildError("run_recipe.py no longer exposes the H3 autogrow validator")
    return validator


def nested_structural_reconstruction(flat: dict[str, Any]) -> dict[str, Any]:
    """Make an in-memory shape reconstruction without claiming historical bytes."""

    prompt = copy.deepcopy(flat["prompt"])
    inputs = prompt["7"]["inputs"]
    link = inputs.pop("ref_images.ref_image_0", None)
    if link != ["11", 0] or "ref_images" in inputs:
        raise BuildError("flat source cannot be structurally reconstructed as expected")
    inputs["ref_images"] = {"ref_image_0": link}
    return prompt


def job1_structural_finding() -> dict[str, Any]:
    receipt = load_pinned_json(ORIGIN_RECEIPT, ORIGIN_RECEIPT_SHA256)
    if receipt.get("recipe_sha256") != MISSING_PINNED_OLD_RECIPE_SHA256:
        raise BuildError("origin receipt no longer binds the expected missing recipe SHA")
    if sha256_file(ORIGIN_ARTIFACT) != ORIGIN_ARTIFACT_SHA256:
        raise BuildError("origin artifact SHA drift")
    flat = load_pinned_json(FLAT_SOURCE, FLAT_SOURCE_SHA256)
    flat_inputs = flat["prompt"]["7"]["inputs"]
    if flat_inputs.get("ref_images.ref_image_0") != ["11", 0]:
        raise BuildError("current flat source no longer binds portrait.png")
    reconstructed_prompt = nested_structural_reconstruction(flat)
    validator = _load_runner_validator()
    errors = validator(reconstructed_prompt)
    if errors != [EXPECTED_NESTED_REJECTION]:
        raise BuildError(
            "local schema validator did not produce the pinned nested-container "
            f"rejection: {errors!r}"
        )
    return {
        "schema_version": 1,
        "job": 1,
        "disposition": "LOCAL_SCHEMA_REJECTED_NO_RENDER",
        "exact_pinned_old_recipe_bytes_present": False,
        "pinned_old_recipe_sha256": MISSING_PINNED_OLD_RECIPE_SHA256,
        "absence_audit_scope": (
            "2026-08-10 read-only audit of the worktree, reachable revisions, and "
            "unreachable Git blobs; the exact pinned bytes were not found"
        ),
        "origin_receipt": {
            "path": str(ORIGIN_RECEIPT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": ORIGIN_RECEIPT_SHA256,
        },
        "origin_artifact": {
            "path": str(ORIGIN_ARTIFACT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": ORIGIN_ARTIFACT_SHA256,
        },
        "nearest_recoverable_nested_source": {
            "git_commit": NEAREST_NESTED_GIT_COMMIT,
            "git_blob": NEAREST_NESTED_GIT_BLOB,
            "sha256": NEAREST_NESTED_SHA256,
            "equals_pinned_old_recipe": False,
            "metadata_only_not_executable": True,
        },
        "structural_diff": {
            "mission_described_nested_shape_reconstructed_in_memory": {
                "ref_images": {"ref_image_0": ["11", 0]}
            },
            "current_shape": {"ref_images.ref_image_0": ["11", 0]},
            "current_topology_contract_requires_nested_absent": True,
            "audio_decode_branch_structurally_unchanged": (
                "SamplerCustomAdvanced -> VAEDecodeAudio -> CreateVideo.audio"
            ),
        },
        "compatibility_preflight": {
            "status": "REJECTED_BY_LOCAL_LAB_SCHEMA_VALIDATOR",
            "error_verbatim": errors[0],
            "validator": {
                "path": str(RUNNER.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(RUNNER),
                "function": "minimax_h3_autogrow_input_errors",
            },
            "candidate_basis": (
                "In-memory structural reconstruction from the pinned current flat "
                "source; it is not the missing historical recipe bytes."
            ),
            "authority_limit": (
                "This is an enforced local lab-runner schema rejection under the "
                "installed V3 socket semantics. No server was booted or queried, no "
                "prompt was queued, and this is not evidence of a node runtime error."
            ),
        },
        "execution_authorized": False,
        "job1b_render_leg_count": 0,
        "causal_claim_limit": (
            "Historical nested versus flat output differences compare ineffective versus valid "
            "picture conditioning and do not alone prove an audio-branch regression."
        ),
        "quality_judgment": "PENDING_HUMAN",
    }


def plan_payload(include_job4: bool = True) -> dict[str, Any]:
    specs = [spec for spec in followup_specs() if include_job4 or spec.job != 4]
    recipes = []
    for spec in specs:
        payload = canonical_json(build_recipe(spec))
        recipes.append(
            {
                "order": spec.order,
                "job": spec.job,
                "cell": spec.cell,
                "name": spec.name,
                "path": str(spec.recipe_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_bytes(payload),
                "seed": spec.seed,
                "frames": spec.frames,
                "timeout_s": spec.timeout_s,
                "expected_artifact": spec.expected_artifact_name,
            }
        )
    return {
        "schema_version": 1,
        "campaign": "H3_MUSIC_FOLLOWUP",
        "job1": job1_structural_finding(),
        "recipes": recipes,
        "new_render_leg_count": len(recipes),
        "job4_included": include_job4,
        "conditional_bonus_included": False,
        "quality_judgment": "PENDING_HUMAN",
    }


def materialize_recipes(specs: Iterable[FollowupSpec]) -> list[dict[str, Any]]:
    written = []
    for spec in specs:
        recipe = build_recipe(spec)
        payload = canonical_json(recipe)
        path = spec.recipe_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise BuildError(f"refusing to overwrite drifted recipe: {path}")
            disposition = "existing_exact"
        else:
            with path.open("xb") as handle:
                handle.write(payload)
            disposition = "created_exclusive"
        written.append(
            {
                "path": str(path),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "disposition": disposition,
            }
        )
    return written


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="materialize new recipe files")
    parser.add_argument("--skip-job4", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    specs = tuple(
        spec for spec in followup_specs() if not args.skip_job4 or spec.job != 4
    )
    payload = plan_payload(include_job4=not args.skip_job4)
    if args.write:
        payload["materialization"] = materialize_recipes(specs)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
