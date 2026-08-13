#!/usr/bin/env python
"""Build immutable production-wrapper fixtures for the WAN cost ladder.

The fixture source is the already-baked, measured WAN-retention bundle.  One
production shot, its still, prompt material, seed, and master audio are retained.
For a requested model length ``N`` the beat deliberately delivers ``N - 1``
frames from a one-segment coverage plan that renders ``N`` and trims one tail
frame during assembly.  That small distinction is load-bearing: it routes the
request through the production ``prepare()``/``render_clip()`` coverage path and
therefore measures exactly N legal model frames instead of WAN's historical
single-clip floor.

This LAB-owned builder writes only beneath ComfyUI's output tree.  It never
writes OTR, starts a server, queries a server, or downloads an asset.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
OTR_VISUAL_SMOKE = OTR_ROOT / "scripts" / "otr_visual_smoke.py"
SOURCE_DIR = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_retention_measurement\long_first_planned"
)
OUTPUT_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_cost_ladder_measurement"
)
SOURCE_SHOT_ID = "shot_b001"
EFFECTIVE_VIDEO_SEED = 944021193
CANVAS = (832, 480)
REFERENCE_CANVAS = (1472, 832)
LADDERS = {
    "wan_ti2v": (25, 65, 93, 129, 177),
    "fastwan_8gb": (25, 93, 177),
}
MANIFEST_REQUIRED = {
    "Wan2.2-TI2V-5B-Q5_K_M.gguf",
    "umt5-xxl-encoder-Q5_K_M.gguf",
    "wan2.2_vae.safetensors",
    "Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors",
}
PRODUCTION_SETTINGS = {
    "wan_ti2v": {
        "recipe": "wan22_ti2v_5b_i2v_single_pass_v1",
        "unet": "Wan2.2-TI2V-5B-Q5_K_M.gguf",
        "clip": "umt5-xxl-encoder-Q5_K_M.gguf",
        "clip_loader": "CLIPLoaderGGUF",
        "vae": "wan2.2_vae.safetensors",
        "steps": 30,
        "cfg": 5.0,
        "shift": 5.0,
        "sampler": "euler",
        "scheduler": "simple",
        "negative": (
            "low quality, worst quality, blurry, distorted, watermark, text, static"
        ),
        "tiled_decode": {
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 16,
            "temporal_overlap": 8,
        },
    },
    "fastwan_8gb": {
        "recipe": "fastwan22_ti2v_5b_dmd3_i2v_v1",
        "inherits": "wan_ti2v",
        "unet": "Wan2.2-TI2V-5B-Q5_K_M.gguf",
        "clip": "umt5-xxl-encoder-Q5_K_M.gguf",
        "clip_loader": "CLIPLoaderGGUF",
        "vae": "wan2.2_vae.safetensors",
        "lora": "Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors",
        "lora_strength": 1.0,
        "steps": 3,
        "cfg": 1.0,
        "shift": 5.0,
        "sampler": "OTR_DMDRestartSamplerSelect",
        "scheduler": "manual_sigmas",
        "sigmas": "1.0, 0.757, 0.522, 0.0",
        "negative": (
            "low quality, worst quality, blurry, distorted, watermark, text, static"
        ),
        "tiled_decode": {
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 16,
            "temporal_overlap": 8,
        },
    },
}
COMFY_PYTHON = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe"
)
OTR_LAUNCHER = OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"
OTR_MODEL_PATHS = OTR_ROOT / "scripts" / "_otr_headless_model_paths.yaml"
OTR_OUTPUT = Path(r"C:\Users\jeffr\Documents\ComfyUI\output")
SERVER_LOG = OTR_ROOT / "tmp" / "wan_cost_ladder.server.log"
BASELINE_RECEIPT = (
    LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder" / "desktop_baseline.json"
)
TELEMETRY_ROOT = (
    LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder" / "telemetry"
)
PHYSICAL_ASSETS = {
    "unet": Path(r"C:\ComfyUI-Models\diffusion_models\Wan2.2-TI2V-5B-Q5_K_M.gguf"),
    "clip": Path(r"C:\ComfyUI-Models\text_encoders\umt5-xxl-encoder-Q5_K_M.gguf"),
    "vae": Path(r"C:\ComfyUI-Models\vae\wan2.2_vae.safetensors"),
    "fastwan_lora": Path(
        r"C:\ComfyUI-Models\loras\Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors"
    ),
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


def git_head() -> str:
    result = subprocess.run(
        ["git", "-C", str(OTR_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_paths(engine: str) -> dict[str, Path]:
    paths = {
        "_otr_soak_server_launch.cmd": OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd",
        "_otr_headless_model_paths.yaml": OTR_ROOT / "scripts" / "_otr_headless_model_paths.yaml",
        "otr_video_render_batch.py": OTR_ROOT / "nodes" / "otr_video_render_batch.py",
        "otr_visual_smoke.py": OTR_VISUAL_SMOKE,
        "otr_canonical.json": OTR_ROOT / "workflows" / "otr_canonical.json",
        "render_driver.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "render_driver.py",
        "coverage_plan.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "coverage_plan.py",
        "motion_common.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "motion_common.py",
        "wan_shared.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "wan_shared.py",
        "eng_wan_ti2v.py": OTR_ROOT
        / "nodes"
        / "_otr_video_engines"
        / "eng_wan_ti2v.py",
    }
    if engine == "fastwan_8gb":
        paths.update(
            {
                "eng_fastwan_8gb.py": OTR_ROOT
                / "nodes"
                / "_otr_video_engines"
                / "eng_fastwan_8gb.py",
                "dmd_sampler.py": OTR_ROOT
                / "nodes"
                / "_otr_video_engines"
                / "dmd_sampler.py",
            }
        )
    return paths


def verify_production_source(engine: str) -> dict[str, Any]:
    """Fail closed if the adapter no longer contains the pinned recipe literals."""
    wan = source_paths(engine)["eng_wan_ti2v.py"].read_text(encoding="utf-8")
    shared = source_paths(engine)["wan_shared.py"].read_text(encoding="utf-8")
    required = {
        "_otr_soak_server_launch.cmd": [
            'else if /i "%2"=="WAN" (',
            "set OTR_ENABLE_WAN_TI2V=1",
            "--port %OTR_HEADLESS_PORT% --cuda-malloc",
            "--disable-metadata",
        ],
        "_otr_headless_model_paths.yaml": [
            "download_model_base: C:/ComfyUI-Models",
            "custom_nodes: custom_nodes/",
            "C:/ComfyUI-Models/diffusion_models",
            "C:/ComfyUI-Models/text_encoders/",
            "vae: C:/ComfyUI-Models/vae/",
        ],
        "otr_video_render_batch.py": [
            '"oom_index": ("INT", {"default": 20, "min": 0, "max": 399',
            '"Inert in mode=single and mode=episode."',
            'if mode == "episode":',
        ],
        "eng_wan_ti2v.py": [
            '_TI2V_DEFAULT_UNET = "Wan2.2-TI2V-5B-Q5_K_M.gguf"',
            '_TI2V_DEFAULT_CLIP = "umt5-xxl-encoder-Q5_K_M.gguf"',
            'RECIPE_WAN_TI2V = "wan22_ti2v_5b_i2v_single_pass_v1"',
            '"steps": 30',
            '"cfg": 5.0',
            '"shift": 5.0',
            '"sampler": "euler"',
            '"scheduler": "simple"',
            '"vae_tile": 256',
            '"vae_overlap": 64',
            '"vae_temporal": 16',
            '"vae_temporal_overlap": 8',
            "render_canvas = (832, 480)",
        ],
        "wan_shared.py": [
            '"low quality, worst quality, blurry, distorted, watermark, text, static"'
        ],
        "motion_common.py": [
            "_FRAME_COST_REF_PIXELS = 1472 * 832",
            '"wan_ti2v": (7000.0, 185.0)',
            "QUALIFIED_COST_ROWS = frozenset()",
        ],
    }
    texts = {
        "_otr_soak_server_launch.cmd": source_paths(engine)[
            "_otr_soak_server_launch.cmd"
        ].read_text(encoding="utf-8"),
        "_otr_headless_model_paths.yaml": source_paths(engine)[
            "_otr_headless_model_paths.yaml"
        ].read_text(encoding="utf-8"),
        "otr_video_render_batch.py": source_paths(engine)[
            "otr_video_render_batch.py"
        ].read_text(encoding="utf-8"),
        "eng_wan_ti2v.py": wan,
        "wan_shared.py": shared,
        "motion_common.py": source_paths(engine)["motion_common.py"].read_text(
            encoding="utf-8"
        ),
    }
    if engine == "fastwan_8gb":
        fast = source_paths(engine)["eng_fastwan_8gb.py"].read_text(encoding="utf-8")
        texts["eng_fastwan_8gb.py"] = fast
        required["eng_fastwan_8gb.py"] = [
            "class FastWan8gbEngine(_WT.WanTi2vEngine):",
            'RECIPE_FASTWAN_8GB = "fastwan22_ti2v_5b_dmd3_i2v_v1"',
            'FASTWAN_LORA_NAME = "Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors"',
            'FASTWAN_SIGMAS = "1.0, 0.757, 0.522, 0.0"',
            '"steps": 3',
            '"cfg": 1.0',
            '"shift": 5.0',
            '"sampler": "dmd_restart"',
            '"scheduler": "manual_sigmas"',
            '"lora_strength": 1.0',
            "render_canvas = (832, 480)",
            'cands["dmdsampler"] = ("OTR_DMDRestartSamplerSelect",)',
            '_MC.FRAME_COST_MODEL["fastwan_8gb"] = (7000.0, 185.0)',
        ]
    missing = {
        filename: [token for token in tokens if token not in texts[filename]]
        for filename, tokens in required.items()
    }
    missing = {filename: tokens for filename, tokens in missing.items() if tokens}
    if missing:
        raise FixtureError(f"Production adapter literals drifted: {missing}")
    return {
        "status": "VERIFIED_FROM_LOCAL_SOURCE",
        "tokens_checked": {filename: len(tokens) for filename, tokens in required.items()},
        "source_sha256s": {
            filename: sha256_file(source_paths(engine)[filename]) for filename in required
        },
    }


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "otr_visual_smoke_wan_cost_ladder", OTR_VISUAL_SMOKE
    )
    if spec is None or spec.loader is None:
        raise FixtureError(f"Cannot load existing OTR harness: {OTR_VISUAL_SMOKE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source_ledger() -> dict[str, Any]:
    path = SOURCE_DIR / "baked_ledger.json"
    if not path.is_file():
        raise FixtureError(f"Missing source bundle ledger: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FixtureError("Source ledger is not a mapping")
    return payload


def bundle_name(engine: str, frames: int) -> str:
    return f"{engine}_f{frames:03d}"


def bundle_dir(engine: str, frames: int) -> Path:
    return OUTPUT_ROOT / bundle_name(engine, frames)


def derive_ledger(source: dict[str, Any], engine: str, frames: int) -> dict[str, Any]:
    if engine not in LADDERS or frames not in LADDERS[engine]:
        raise FixtureError(f"Unsupported ladder cell: {engine} at {frames} frames")
    if frames < 17 or (frames - 1) % 4:
        raise FixtureError(f"WAN length is not legal 4n+1: {frames}")

    ledger = copy.deepcopy(source)
    source_shots = [
        row
        for row in ((ledger.get("video") or {}).get("shots") or [])
        if isinstance(row, dict) and row.get("shot_id") == SOURCE_SHOT_ID
    ]
    if len(source_shots) != 1:
        raise FixtureError(
            f"Expected exactly one source shot {SOURCE_SHOT_ID!r}, found {len(source_shots)}"
        )
    shot = copy.deepcopy(source_shots[0])
    shot["engine_id"] = engine
    shot["family"] = ""
    # The production coverage executor is selected because trim_tail is nonzero.
    # The adapter renders N; only the episode assembler removes the surplus tail.
    shot["target_frame_count"] = frames - 1
    shot["coverage_plan"] = {
        "target_visible_frames": frames - 1,
        "join_mode": "single",
        "segments": [
            {
                "index": 0,
                "render_frames": frames,
                "drop_head": 0,
                "trim_tail": 1,
            }
        ],
    }
    shot["render_request_hash"] = ""
    shot["binding_hash"] = ""
    shot["cache_keys"] = {"prompt_hash": "", "request_hash": ""}
    shot.pop("coverage_contract", None)

    video = ledger.get("video")
    if not isinstance(video, dict):
        raise FixtureError("Source ledger has no video mapping")
    video["shots"] = [shot]
    video["clip_budget"] = {"total_frames": frames - 1}
    for key in (
        "execution_groups",
        "roles",
        "roles_effective",
        "routing_env_snapshot",
        "locked_against_audio_rev",
    ):
        video.pop(key, None)

    ledger["episode_id"] = f"wan_cost_ladder_{engine}_f{frames:03d}_20260809"
    meta = ledger.setdefault("meta", {})
    meta["wan_cost_ladder_measurement"] = {
        "kind": "lab-owned-production-wrapper-cost-cell",
        "engine": engine,
        "canvas": list(CANVAS),
        "model_render_frames": frames,
        "delivered_frames": frames - 1,
        "assembly_only_trim_tail": 1,
        "one_variable_within_engine": "model_render_frames",
        "source_bundle_ledger_sha256": sha256_file(SOURCE_DIR / "baked_ledger.json"),
        "source_request_seed": int(shot.get("request_seed") or 0),
        "effective_video_seed": EFFECTIVE_VIDEO_SEED,
        "effective_video_seed_derivation": "sha256('shot_b001')[:8] & 0x7fffffff because request_hash is intentionally blank",
    }
    validate_derived(ledger, engine, frames)
    return ledger


def validate_derived(ledger: dict[str, Any], engine: str, frames: int) -> None:
    shots = ((ledger.get("video") or {}).get("shots") or [])
    if len(shots) != 1:
        raise FixtureError("Cost fixture must contain exactly one shot")
    shot = shots[0]
    plan = shot.get("coverage_plan") or {}
    segments = plan.get("segments") or []
    expected = {
        "target_visible_frames": frames - 1,
        "join_mode": "single",
        "segments": [
            {"index": 0, "render_frames": frames, "drop_head": 0, "trim_tail": 1}
        ],
    }
    if shot.get("engine_id") != engine or plan != expected:
        raise FixtureError("Derived engine/coverage contract drifted")
    if int(shot.get("target_frame_count") or 0) != frames - 1:
        raise FixtureError("Delivered-frame target does not match assembly plan")
    visible = sum(
        int(row["render_frames"]) - int(row["drop_head"]) - int(row["trim_tail"])
        for row in segments
    )
    if visible != frames - 1:
        raise FixtureError("Coverage arithmetic does not deliver N-1 frames")
    if int(shot.get("request_seed") or 0) != 0:
        raise FixtureError("Source production seed drifted from zero")
    if shot.get("render_request_hash") or (shot.get("cache_keys") or {}).get("request_hash"):
        raise FixtureError("Fixture request hash must remain blank for a constant shot-id seed")
    derived_seed = int(
        hashlib.sha256(SOURCE_SHOT_ID.encode("utf-8")).hexdigest()[:8], 16
    ) & 0x7FFFFFFF
    if derived_seed != EFFECTIVE_VIDEO_SEED:
        raise FixtureError("Pinned effective video seed derivation drifted")


def inventory_status(manifest_text: str | None = None) -> dict[str, Any]:
    text = (
        (LAB_ROOT / "models_manifest.md").read_text(encoding="utf-8")
        if manifest_text is None
        else manifest_text
    )
    present = sorted(name for name in MANIFEST_REQUIRED if f"`{name}`" in text)
    missing = sorted(MANIFEST_REQUIRED - set(present))
    return {
        "manifest_path": str(LAB_ROOT / "models_manifest.md"),
        "manifest_sha256": sha256_file(LAB_ROOT / "models_manifest.md")
        if manifest_text is None
        else None,
        "required": sorted(MANIFEST_REQUIRED),
        "present": present,
        "missing": missing,
        "status": "AVAILABLE" if not missing else "BLOCKED_MANIFEST_REFRESH_REQUIRED",
        "note": (
            "The default production GGUF UMT5 file is physically present but absent "
            "from the lab's owned live-server manifest; disk presence alone does not "
            "satisfy AGENTS.md rule 5. OTR-side production replay remains the primary route."
        ),
    }


def physical_asset_status() -> dict[str, Any]:
    rows = {}
    for label, path in PHYSICAL_ASSETS.items():
        stat = path.stat() if path.is_file() else None
        rows[label] = {
            "path": str(path),
            "exists": stat is not None,
            "bytes": int(stat.st_size) if stat is not None else 0,
            "mtime_ns": int(stat.st_mtime_ns) if stat is not None else None,
        }
    return {
        "status": "AVAILABLE" if all(row["exists"] for row in rows.values()) else "BLOCKED",
        "assets": rows,
        "scope": "read-only disk inventory; live production adapter preflight remains authoritative",
    }


def execution_plan() -> dict[str, Any]:
    """Return exact argv surfaces without starting a server or a render."""
    baseline_argv = [
        str(COMFY_PYTHON),
        str(LAB_ROOT / "scratch" / "capture_wan_cost_baseline.py"),
        "--output",
        str(BASELINE_RECEIPT),
    ]
    fixture_argv = [
        str(COMFY_PYTHON),
        str(Path(__file__).resolve()),
        "--write",
    ]
    boot_powershell = {
        "FilePath": str(OTR_LAUNCHER),
        "ArgumentList": [str(SERVER_LOG), "WAN"],
        "WindowStyle": "Hidden",
        "note": "Start-Process only after desktop-baseline capture; launcher remains the existing OTR WAN lane.",
    }
    pairs = []
    for engine, lengths in LADDERS.items():
        for frames in lengths:
            first_output = TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run1.json"
            warm_output = TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run2.json"
            common = [
                "--engine",
                engine,
                "--frames",
                str(frames),
                "--desktop-baseline-receipt",
                str(BASELINE_RECEIPT),
                "--boot-lane",
                "otr-8000, WAN, production-wrapper, manager-offline",
                "--server-port",
                "8000",
                "--expected-server-model-paths",
                str(OTR_MODEL_PATHS),
                "--expected-server-output",
                str(OTR_OUTPUT),
                "--server-log",
                str(SERVER_LOG),
                "--interval-s",
                "0.2",
                "--timeout",
                "2400",
            ]
            first = [
                str(COMFY_PYTHON),
                str(LAB_ROOT / "scratch" / "wan_cost_ladder_sidecar.py"),
                "--output",
                str(first_output),
                *common,
                "--run-role",
                "pair_first",
            ]
            warm = [
                str(COMFY_PYTHON),
                str(LAB_ROOT / "scratch" / "wan_cost_ladder_sidecar.py"),
                "--output",
                str(warm_output),
                *common,
                "--run-role",
                "warm_second",
                "--previous-receipt",
                str(first_output),
            ]
            pairs.append(
                {
                    "engine": engine,
                    "model_render_frames": frames,
                    "pair_first_argv": first,
                    "warm_second_argv": warm,
                }
            )
    return {
        "fixture_build_argv": fixture_argv,
        "desktop_baseline_argv": baseline_argv,
        "boot_existing_otr_lane_via_start_process": boot_powershell,
        "pairs_in_required_sequence": pairs,
        "reducer_check_argv": [
            str(COMFY_PYTHON),
            str(LAB_ROOT / "scratch" / "reduce_wan_cost_ladder.py"),
        ],
        "reducer_write_argv": [
            str(COMFY_PYTHON),
            str(LAB_ROOT / "scratch" / "reduce_wan_cost_ladder.py"),
            "--write",
        ],
        "identity_constraints": [
            "Capture the baseline before boot while port 8000 has no listener and no NVIDIA compute process exists.",
            "Use one positively identified OTR listener whose argv pins port 8000, _otr_headless_model_paths.yaml, and the canonical output directory.",
            "For every cell, run pair_first then warm_second with no intervening server-log execution marker; benign append-only log bytes are hash-receipted. Both receipts must have identical serving PID, process_create_time, argv, fixture hashes, and baseline hash.",
            "The sidecar acquires and releases the lab .gpu.lock for every run; never adopt or stop a foreign listener.",
            "Only node-92 oom_index changes between pair runs; it is inert in mode=episode. Engine authority remains baked_ledger.video.shots[0].engine_id.",
        ],
    }


def build_one(harness: Any, source: dict[str, Any], engine: str, frames: int) -> dict[str, Any]:
    destination = bundle_dir(engine, frames)
    if destination.exists():
        raise FixtureError(f"Refusing to overwrite immutable bundle: {destination}")
    master = SOURCE_DIR / "master.wav"
    if not master.is_file():
        raise FixtureError(f"Missing source master: {master}")
    ledger = derive_ledger(source, engine, frames)
    baked, baked_master, manifest = harness.bake_bundle(
        ledger, str(master), str(destination), base_dirs=()
    )
    validate_derived(baked, engine, frames)
    sources = source_paths(engine)
    missing_sources = [str(path) for path in sources.values() if not path.is_file()]
    if missing_sources:
        raise FixtureError(f"Pinned OTR source missing: {missing_sources}")
    contract = {
        "schema_version": 1,
        "purpose": "WAN/FastWan production-canvas cost-row candidate measurement",
        "qualification_state": "candidate only; OTR prepare()+render_clip qualification pending",
        "engine": engine,
        "engine_binding": "baked_ledger.video.shots[0].engine_id",
        "canvas": list(CANVAS),
        "reference_canvas": list(REFERENCE_CANVAS),
        "model_render_frames": frames,
        "delivered_frames": frames - 1,
        "assembly_only_trim_tail": 1,
        "coverage_executor_reason": (
            "one-segment plan has trim_tail=1, so CoveragePlan.requires_coverage_execution "
            "is true and the production prepare()+render_clip lifecycle renders exactly N"
        ),
        "source_shot_id": SOURCE_SHOT_ID,
        "source_request_seed": 0,
        "effective_video_seed": EFFECTIVE_VIDEO_SEED,
        "production_settings": copy.deepcopy(PRODUCTION_SETTINGS[engine]),
        "production_source_verification": verify_production_source(engine),
        "fixture_builder_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "source_bundle": str(SOURCE_DIR),
        "source_bundle_sha256s": {
            name: sha256_file(SOURCE_DIR / name)
            for name in ("baked_ledger.json", "bundle_manifest.json", "fixture_contract.json", "master.wav")
        },
        "otr_repo_head_at_build": git_head(),
        "otr_source_sha256s": {label: sha256_file(path) for label, path in sources.items()},
        "lab_manifest_inventory": inventory_status(),
        "otr_disk_inventory": physical_asset_status(),
        "run_contract": {
            "runs_per_cell": 2,
            "warm_definition": "second consecutive execution on identical owned PID/create_time",
            "cache_buster": "node 92 oom_index only; inert in mode=episode",
            "sampling_interval_s": 0.2,
            "no_engine_override": True,
        },
        "notes": [
            "No OTR source, profile, cost row, margin, frame cap, or production recipe is edited.",
            "Within each engine ladder the only generation variable is model_render_frames.",
            "Rendered N and delivered N-1 are both explicit; fitting uses rendered N.",
            "FastWan is exact only through OTR because OTR_DMDRestartSamplerSelect is production-owned.",
        ],
    }
    manifest["wan_cost_ladder_contract"] = contract
    (destination / "bundle_manifest.json").write_bytes(canonical_json_bytes(manifest))
    (destination / "fixture_contract.json").write_bytes(canonical_json_bytes(contract))
    return {
        "destination": str(destination),
        "engine": engine,
        "model_render_frames": frames,
        "delivered_frames": frames - 1,
        "baked_ledger_sha256": sha256_file(destination / "baked_ledger.json"),
        "master_sha256": sha256_file(Path(baked_master)),
        "bundle_manifest_sha256": sha256_file(destination / "bundle_manifest.json"),
        "fixture_contract_sha256": sha256_file(destination / "fixture_contract.json"),
    }


def plan() -> dict[str, Any]:
    source = _source_ledger()
    cells = []
    for engine, lengths in LADDERS.items():
        for frames in lengths:
            derived = derive_ledger(source, engine, frames)
            cells.append(
                {
                    "engine": engine,
                    "model_render_frames": frames,
                    "delivered_frames": frames - 1,
                    "destination": str(bundle_dir(engine, frames)),
                    "derived_ledger_sha256": hashlib.sha256(
                        canonical_json_bytes(derived)
                    ).hexdigest(),
                }
            )
    return {
        "cells": cells,
        "inventory": inventory_status(),
        "otr_disk_inventory": physical_asset_status(),
        "execution_plan": execution_plan(),
        "production_source_verification": {
            engine: verify_production_source(engine) for engine in LADDERS
        },
    }


def build(selected_engine: str | None = None, selected_frames: int | None = None) -> dict[str, Any]:
    source = _source_ledger()
    harness = _load_harness()
    rows: dict[str, Any] = {}
    for engine, lengths in LADDERS.items():
        if selected_engine and engine != selected_engine:
            continue
        for frames in lengths:
            if selected_frames is not None and frames != selected_frames:
                continue
            name = bundle_name(engine, frames)
            rows[name] = build_one(harness, source, engine, frames)
    if not rows:
        raise FixtureError("Selection did not match a declared ladder cell")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=tuple(LADDERS))
    parser.add_argument("--frames", type=int)
    parser.add_argument(
        "--write", action="store_true", help="create immutable external replay bundles"
    )
    args = parser.parse_args(argv)
    if args.frames is not None and args.engine is None:
        parser.error("--frames requires --engine")
    payload = (
        build(args.engine, args.frames)
        if args.write
        else plan()
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
