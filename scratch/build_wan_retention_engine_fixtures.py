#!/usr/bin/env python
"""Build the engine-only Phase-3 WAN-retention comparison bundles.

The production-tail targets, order, source stills, audio, prompt material and
seed fields come from the measured WAN long-first bundle.  The only semantic
variable is ``engine_id``.  Each adapter's coverage plan is necessarily
engine-coupled: FastWan inherits WAN's 4n+1 ladder, while production LTX renders
its fixed 169-frame unit and trims at assembly.

Writes only below ComfyUI's output tree; never writes the OTR repository.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
OTR_VISUAL_SMOKE = OTR_ROOT / "scripts" / "otr_visual_smoke.py"
OUTPUT_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_retention_measurement"
)
SOURCE_DIR = OUTPUT_ROOT / "long_first_planned"
DESTINATIONS = {
    "fastwan_8gb": OUTPUT_ROOT / "fastwan_8gb_long_first_planned",
    "ltx_video": OUTPUT_ROOT / "ltx_video_long_first_planned",
}

FASTWAN_LONG = {
    "target_visible_frames": 200,
    "join_mode": "chain",
    "segments": [
        {"index": 0, "render_frames": 177, "drop_head": 0, "trim_tail": 0},
        {"index": 1, "render_frames": 25, "drop_head": 1, "trim_tail": 1},
    ],
}
FASTWAN_SMALL = {
    "target_visible_frames": 65,
    "join_mode": "single",
    "segments": [
        {"index": 0, "render_frames": 65, "drop_head": 0, "trim_tail": 0},
    ],
}
LTX_LONG = {
    "target_visible_frames": 200,
    "join_mode": "chain",
    "segments": [
        {"index": 0, "render_frames": 169, "drop_head": 0, "trim_tail": 0},
        {"index": 1, "render_frames": 169, "drop_head": 1, "trim_tail": 137},
    ],
}
LTX_SMALL = {
    "target_visible_frames": 65,
    "join_mode": "single",
    "segments": [
        {"index": 0, "render_frames": 169, "drop_head": 0, "trim_tail": 104},
    ],
}


class FixtureError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "otr_visual_smoke_retention_phase3", OTR_VISUAL_SMOKE
    )
    if spec is None or spec.loader is None:
        raise FixtureError(f"Cannot load existing OTR harness: {OTR_VISUAL_SMOKE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git_head() -> str:
    result = subprocess.run(
        ["git", "-C", str(OTR_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def derive(source: dict[str, Any], engine: str) -> dict[str, Any]:
    ledger = copy.deepcopy(source)
    shots = ((ledger.get("video") or {}).get("shots") or [])
    if [shot.get("target_frame_count") for shot in shots] != [200, 65]:
        raise FixtureError("Source bundle is not the measured 200 -> 65 control")
    plans = (
        (FASTWAN_LONG, FASTWAN_SMALL)
        if engine == "fastwan_8gb"
        else (LTX_LONG, LTX_SMALL)
    )
    for shot, plan in zip(shots, plans, strict=True):
        shot["engine_id"] = engine
        shot["family"] = ""
        shot["coverage_plan"] = copy.deepcopy(plan)
        shot.pop("coverage_contract", None)
    ledger["episode_id"] = f"wan_retention_{engine}_long_first_planned_20260809"
    meta = ledger.setdefault("meta", {})
    measurement = meta.setdefault("wan_retention_measurement", {})
    measurement.update(
        {
            "kind": "engine-only-derived-node92-shape-fixture",
            "order": "long_then_small",
            "target_frames": [200, 65],
            "base_engine": "wan_ti2v",
            "engine_variable": "baked_ledger.video.shots[].engine_id",
            "selected_engine": engine,
            "coverage_plan_is_engine_coupled": True,
            "source_ledger_sha256": sha256_file(SOURCE_DIR / "baked_ledger.json"),
        }
    )
    return ledger


def build_one(harness: Any, engine: str, source: dict[str, Any]) -> dict[str, Any]:
    destination = DESTINATIONS[engine]
    if destination.exists():
        raise FixtureError(f"Refusing to overwrite bundle: {destination}")
    master = SOURCE_DIR / "master.wav"
    ledger = derive(source, engine)
    baked, baked_master, manifest = harness.bake_bundle(
        ledger, str(master), str(destination), base_dirs=()
    )
    source_files = {
        "otr_visual_smoke.py": OTR_VISUAL_SMOKE,
        "render_driver.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "render_driver.py",
        "coverage_plan.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "coverage_plan.py",
        "engine.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / ("eng_fastwan_8gb.py" if engine == "fastwan_8gb" else "eng_ltx_video.py"),
        "wan_parent.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "eng_wan_ti2v.py",
    }
    contract = {
        "schema_version": 1,
        "purpose": "Phase-3 engine-only inter-shot retention comparison",
        "comparison_scope": "neutral production-tail diagnostic, not shipping-profile qualification",
        "engine": engine,
        "engine_binding": "baked_ledger.video.shots[].engine_id",
        "order": "long_then_small",
        "targets": [200, 65],
        "topology": "strict-first-frame two-segment long beat followed by one small beat",
        "coverage_plans": [copy.deepcopy(plan) for plan in (
            (FASTWAN_LONG, FASTWAN_SMALL)
            if engine == "fastwan_8gb"
            else (LTX_LONG, LTX_SMALL)
        )],
        "source_bundle": str(SOURCE_DIR),
        "source_ledger_sha256": sha256_file(SOURCE_DIR / "baked_ledger.json"),
        "source_master_sha256": sha256_file(master),
        "otr_repo_head_at_build": git_head(),
        "source_sha256s": {
            label: sha256_file(path) for label, path in source_files.items()
        },
        "notes": [
            "No OTR source, profile, budget, margin, or production recipe was edited.",
            "The target/order/assets are identical to the WAN Phase-1 fixture.",
            "Only engine_id changes; coverage lengths follow the selected adapter's declared frame contract.",
            "HuMo is excluded because its JOIN_JUMP soft-reference topology is not strict-chain comparable.",
        ],
    }
    manifest["wan_retention_measurement_contract"] = contract
    (destination / "bundle_manifest.json").write_bytes(canonical_json_bytes(manifest))
    (destination / "fixture_contract.json").write_bytes(canonical_json_bytes(contract))
    return {
        "destination": str(destination),
        "baked_ledger_sha256": sha256_file(destination / "baked_ledger.json"),
        "baked_master": baked_master,
        "baked_master_sha256": sha256_file(Path(baked_master)),
        "bundle_manifest_sha256": sha256_file(destination / "bundle_manifest.json"),
        "fixture_contract_sha256": sha256_file(destination / "fixture_contract.json"),
    }


def main() -> int:
    source = json.loads((SOURCE_DIR / "baked_ledger.json").read_text(encoding="utf-8"))
    harness = load_harness()
    results = {engine: build_one(harness, engine, source) for engine in DESTINATIONS}
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
