#!/usr/bin/env python3
"""Build the single cold Ref2VA review source authorized for Job D."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_recipe  # noqa: E402


SOURCE = ROOT / "recipes" / "h3_r2v_refaudio_canonical_832x480_f192_seed43.json"
SOURCE_SHA256 = "a6666b11343137dc1d87d4d901066ccbb4b42b435d7f9d766983db2ec3469a4e"
TARGET_NAME = "h3_jobd_lipsync_refaudio_seed43_f192"
TARGET = ROOT / "recipes" / f"{TARGET_NAME}.json"
OUTPUT_PREFIX = f"{TARGET_NAME}_out"
REQUIRED_BOOT_LANE = (
    "lab-8199, sage-free, manager-offline-test, no-pinned, "
    "cache-classic, reserve-12gb"
)


class BuildError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load_source() -> dict[str, Any]:
    payload = SOURCE.read_bytes()
    actual = sha256_bytes(payload)
    if actual != SOURCE_SHA256:
        raise BuildError(f"source SHA drift: {actual} != {SOURCE_SHA256}")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise BuildError("source recipe is not an object")
    return value


def build() -> dict[str, Any]:
    recipe = copy.deepcopy(load_source())
    recipe["name"] = TARGET_NAME
    recipe["tier"] = "experiment"
    recipe["experiment"] = {
        "campaign": "h3_short_jobs_20260810",
        "job": "D_24_to_25_fps_lipsync_proof",
        "variant": "cold_ref2va_review_source",
        "measurement_state": "unrendered",
        "exploratory_single_leg": True,
        "warm_certification_claimed": False,
        "source_recipe": {
            "path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": SOURCE_SHA256,
        },
        "quality_judgment": "PENDING_HUMAN",
    }
    contract = recipe["contract"]
    contract["mode"] = "r2v_refaudio_jobd_review_source"
    contract["required_boot_lane"] = REQUIRED_BOOT_LANE
    recipe["receipt_requirements"] = {
        "review_source_gate": {
            "required_runs": 1,
            "required_run_number": 1,
            "required_config_run_count": 1,
            "gate_pass_required": True,
            "pass_required": False,
            "warm_pass_required": False,
            "certification_effect": False,
            "peak_vram_gb_lte": 14.5,
            "required_boot_lane": REQUIRED_BOOT_LANE,
        },
        "manager_offline_gate": {
            "required": True,
            "required_announcement": "[ComfyUI-Manager] network_mode: offline",
            "must_precede_first_prompt": True,
            "network_markers_required_empty": True,
            "mutation_markers_required_empty": True,
        },
        "preboot_gpu_idle_gate_contract": run_recipe.gpu_idle_gate_contract(),
        "operator_idle_policy": run_recipe.operator_idle_policy_contract(),
        "completion_timeout_s": 3600,
        "post_shutdown_clean_state_required": True,
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
    recipe["prompt"]["12"]["inputs"]["filename_prefix"] = OUTPUT_PREFIX

    topology = recipe["topology_contract"]
    values = topology.get("required_input_values") or []
    matches = [
        row
        for row in values
        if row.get("node") == "12" and row.get("input") == "filename_prefix"
    ]
    if len(matches) != 1:
        raise BuildError("source topology does not bind exactly one output prefix")
    matches[0]["equals"] = OUTPUT_PREFIX
    validate(recipe)
    return recipe


def validate(recipe: dict[str, Any]) -> None:
    if recipe.get("name") != TARGET_NAME:
        raise BuildError("target recipe name drift")
    prompt = recipe.get("prompt") or {}
    node7 = prompt.get("7", {}).get("inputs", {})
    if (node7.get("width"), node7.get("height"), node7.get("length")) != (
        832,
        480,
        192,
    ):
        raise BuildError("Job D dimensions/frame count drift")
    if prompt.get("5", {}).get("inputs", {}).get("noise_seed") != 43:
        raise BuildError("Job D seed drift")
    if prompt.get("11", {}).get("class_type") != "LoadImage":
        raise BuildError("Job D portrait input is missing")
    if prompt.get("16", {}).get("class_type") != "LoadAudio":
        raise BuildError("Job D raw TTS input is missing")
    if node7.get("ref_images.ref_image_0") != ["11", 0]:
        raise BuildError("Job D portrait connection drift")
    if node7.get("ref_audios.ref_audio_0") != ["16", 0]:
        raise BuildError("Job D audio connection drift")
    if recipe["contract"].get("required_boot_lane") != REQUIRED_BOOT_LANE:
        raise BuildError("Job D boot lane drift")
    if recipe["receipt_requirements"].get("operator_idle_policy") != run_recipe.operator_idle_policy_contract():
        raise BuildError("operator idle policy drift")
    if recipe["receipt_requirements"].get("preboot_gpu_idle_gate_contract") != run_recipe.gpu_idle_gate_contract():
        raise BuildError("preboot GPU idle contract drift")


def main() -> int:
    payload = canonical_bytes(build())
    if TARGET.exists():
        if TARGET.read_bytes() != payload:
            raise BuildError(f"refusing to overwrite drifted target: {TARGET}")
        action = "existing_exact"
    else:
        TARGET.write_bytes(payload)
        action = "created"
    print(
        json.dumps(
            {
                "status": "ok",
                "action": action,
                "path": str(TARGET),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
