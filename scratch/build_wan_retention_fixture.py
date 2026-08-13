#!/usr/bin/env python
"""Build immutable OTR node-92 replay bundles for WAN retention measurement.

The source is an existing production ``node_episode_input.json`` capture.  We
retain the production ledger/assets and make only the diagnostic shape explicit:
one 200-frame shot followed by one 65-frame shot, plus the reversed-order copy.
The engine is deliberately *not* changed here; both shot rows bind
``baked_ledger.video.shots[].engine_id`` to ``wan_ti2v`` before replay.

This script writes only beneath ComfyUI's output tree.  It never writes the OTR
repository and never starts or queries a server.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
OTR_VISUAL_SMOKE = OTR_ROOT / "scripts" / "otr_visual_smoke.py"
SOURCE_CAPTURE = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared\state"
    r"\node_episode_input.json"
)
EPISODES_ROOT = Path(r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes")
OUTPUT_ROOT = EPISODES_ROOT / "_shared" / "wan_retention_measurement"
LONG_FIRST_DIR = OUTPUT_ROOT / "long_first_planned"
SMALL_FIRST_DIR = OUTPUT_ROOT / "small_first_planned"


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


def create_json(path: Path, payload: Any) -> None:
    encoded = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=False)
    with path.open("xb") as handle:
        handle.write(encoded)


def _load_visual_smoke():
    spec = importlib.util.spec_from_file_location("otr_visual_smoke", OTR_VISUAL_SMOKE)
    if spec is None or spec.loader is None:
        raise FixtureError(f"Cannot load existing OTR harness: {OTR_VISUAL_SMOKE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_renamed_master(stale: str) -> Path:
    requested = Path(stale)
    if requested.is_file():
        return requested
    matches = [path for path in EPISODES_ROOT.rglob(requested.name) if path.is_file()]
    if len(matches) != 1:
        raise FixtureError(
            f"Stale master {stale!r} resolved to {len(matches)} candidates: {matches}"
        )
    return matches[0]


def _source_shot(ledger: dict[str, Any], shot_id: str) -> dict[str, Any]:
    matches = [
        shot
        for shot in ((ledger.get("video") or {}).get("shots") or [])
        if isinstance(shot, dict) and shot.get("shot_id") == shot_id
    ]
    if len(matches) != 1:
        raise FixtureError(f"Expected one source shot {shot_id!r}, found {len(matches)}")
    return copy.deepcopy(matches[0])


def derive_ledger(source: dict[str, Any], *, reverse: bool) -> dict[str, Any]:
    ledger = copy.deepcopy(source)
    video = ledger.get("video")
    if not isinstance(video, dict):
        raise FixtureError("Source capture has no video mapping")

    long_shot = _source_shot(ledger, "shot_b001")
    small_shot = _source_shot(ledger, "shot_b003")
    for shot, frames in ((long_shot, 200), (small_shot, 65)):
        shot["engine_id"] = "wan_ti2v"
        shot["family"] = ""
        shot["target_frame_count"] = frames
        shot["render_request_hash"] = ""
        shot["binding_hash"] = ""
        shot["cache_keys"] = {"prompt_hash": "", "request_hash": ""}
        shot.pop("coverage_contract", None)

    # Reconstruct the exact production coverage arithmetic proven by the
    # retained 2026-08-09 failing log.  This stamp is load-bearing: without it
    # render_driver takes WAN's historical single-clip path and asks the
    # (explicitly disqualified) cost row to price 177 frames.  The original
    # production leg instead executed a legal 177 + 25 chain, dropping the
    # duplicated successor head and one surplus tail frame:
    #   177 + (25 - 1 - 1) == 200.
    # The 65-frame successor is already a legal 4n+1 single render.
    long_shot["coverage_plan"] = {
        "target_visible_frames": 200,
        "join_mode": "chain",
        "segments": [
            {"index": 0, "render_frames": 177, "drop_head": 0, "trim_tail": 0},
            {"index": 1, "render_frames": 25, "drop_head": 1, "trim_tail": 1},
        ],
    }
    small_shot["coverage_plan"] = {
        "target_visible_frames": 65,
        "join_mode": "single",
        "segments": [
            {"index": 0, "render_frames": 65, "drop_head": 0, "trim_tail": 0},
        ],
    }

    shots = [small_shot, long_shot] if reverse else [long_shot, small_shot]
    video["shots"] = shots
    video["clip_budget"] = {"total_frames": 265}

    # This is an explicitly hand-built diagnostic fixture. Removing the
    # upstream route freeze prevents a stale captured route from overriding the
    # engine IDs bound directly in baked_ledger.video.shots[].engine_id.
    for key in (
        "execution_groups",
        "roles",
        "roles_effective",
        "routing_env_snapshot",
        "locked_against_audio_rev",
    ):
        video.pop(key, None)

    ledger["meta"] = copy.deepcopy(ledger.get("meta") or {})
    ledger["meta"]["wan_retention_measurement"] = {
        "kind": "derived-node92-shape-fixture",
        "order": "small_then_long" if reverse else "long_then_small",
        "target_frames": [shot["target_frame_count"] for shot in shots],
        "base_engine": "wan_ti2v",
        "engine_variable": "OTR_FORCE_ENGINE_MAP",
        "engine_variable_status": "LEGACY_INCORRECT_DECLARATIVE_LABEL_NOT_ENGINE_AUTHORITY",
        "engine_authority": "baked_ledger.video.shots[].engine_id",
        "coverage_plan_source": (
            "reconstructed exactly from tmp/chip4_boot.log lines 924-926, "
            "947, 963-971 and coverage_plan.partition_beat"
        ),
        "source_capture_sha256": sha256_file(SOURCE_CAPTURE),
    }
    ledger["episode_id"] = (
        "wan_retention_wan_small_first_planned_20260809"
        if reverse
        else "wan_retention_wan_long_first_planned_20260809"
    )
    return ledger


def build_bundle(
    harness: Any,
    ledger: dict[str, Any],
    master: Path,
    destination: Path,
    *,
    order: str,
    source_master_text: str,
) -> dict[str, Any]:
    if destination.exists():
        raise FixtureError(f"Refusing to overwrite bundle: {destination}")
    baked, baked_master, manifest = harness.bake_bundle(
        ledger, str(master), str(destination), base_dirs=()
    )
    contract = {
        "schema_version": 1,
        "purpose": "wan_ti2v inter-shot VRAM retention measurement only",
        "order": order,
        "target_frames": [shot["target_frame_count"] for shot in baked["video"]["shots"]],
        "engine_binding": "baked_ledger.video.shots[].engine_id",
        "source_capture": str(SOURCE_CAPTURE),
        "source_capture_sha256": sha256_file(SOURCE_CAPTURE),
        "source_master_path_as_captured": source_master_text,
        "resolved_master_path": str(master),
        "resolved_master_sha256": sha256_file(master),
        "existing_otr_harness": str(OTR_VISUAL_SMOKE),
        "existing_otr_harness_sha256": sha256_file(OTR_VISUAL_SMOKE),
        "otr_repo_head_at_build": os.popen(
            f'git -C "{OTR_ROOT}" rev-parse HEAD'
        ).read().strip(),
        "notes": [
            "No OTR source or production recipe was edited.",
            "The stale captured master path was rebound to the unique renamed episode file with identical basename.",
            "Only shot selection/order, target-frame shape, exact historical coverage stamps, and removal of the route freeze were derived for diagnosis.",
            "The long plan is the historical 177+25 chain: drop successor head 1 and trim final tail 1 to deliver exactly 200 frames.",
            "The engine is bound by baked_ledger.video.shots[].engine_id; episode --engine is inert.",
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


def build() -> dict[str, Any]:
    if not SOURCE_CAPTURE.is_file():
        raise FixtureError(f"Missing source capture: {SOURCE_CAPTURE}")
    raw = json.loads(SOURCE_CAPTURE.read_text(encoding="utf-8"))
    ledger = raw.get("ledger")
    if isinstance(ledger, str):
        ledger = json.loads(ledger)
    if not isinstance(ledger, dict):
        raise FixtureError("Source capture ledger is not a mapping")
    stale_master = str(raw.get("master_audio_path") or "")
    master = _resolve_renamed_master(stale_master)
    harness = _load_visual_smoke()
    return {
        "long_first": build_bundle(
            harness,
            derive_ledger(ledger, reverse=False),
            master,
            LONG_FIRST_DIR,
            order="long_then_small",
            source_master_text=stale_master,
        ),
        "small_first": build_bundle(
            harness,
            derive_ledger(ledger, reverse=True),
            master,
            SMALL_FIRST_DIR,
            order="small_then_long",
            source_master_text=stale_master,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args(argv)
    result = build()
    if args.print_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for label, row in result.items():
            print(f"{label}: {row['destination']} ({row['baked_ledger_sha256']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
