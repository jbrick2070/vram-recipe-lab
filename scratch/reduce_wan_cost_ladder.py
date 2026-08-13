#!/usr/bin/env python
"""Reduce immutable WAN cost-ladder receipts into candidate cost rows.

No number is accepted from a summary field.  The reducer re-reads every raw
200 ms sample, re-hashes the shared quiescent baseline receipt, verifies each
cold/warm pair and exact N-frame segment receipt, then fits the warm runs.
Missing, invalid, non-consecutive, or mixed-identity evidence withholds the fit.

The row uses OTR's existing unit and resolution contract:

    demand_mib = conservative_machine_wide_peak_mib - quiescent_desktop_baseline_mib
    demand = overhead + per_frame_at_ref * frames * (832*480)/(1472*832)

Least squares describes shape; the reported candidate is an upper envelope.
It remains CANDIDATE evidence until OTR qualifies it through its own
``prepare()+render_clip`` lifecycle.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable


LAB_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = LAB_ROOT / "scratch"
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
RESULT_ROOT = LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder"
TELEMETRY_BASE = RESULT_ROOT / "telemetry"
EVIDENCE_BASE = RESULT_ROOT / "evidence"
FIT_BASE = RESULT_ROOT / "fits"
TELEMETRY_ROOT = TELEMETRY_BASE
EVIDENCE_ROOT = EVIDENCE_BASE
EVIDENCE_CLIP_ROOT = EVIDENCE_ROOT / "clips"
DEFAULT_OUTPUT = RESULT_ROOT / "wan_cost_ladder_fit.json"
ACTIVE_ATTEMPT_ID: str | None = None
ATTEMPT_ID_PATTERN = re.compile(r"attempt-\d{3}")
LADDERS = {
    "wan_ti2v": (25, 65, 93, 129, 177),
    "fastwan_8gb": (25, 93, 177),
}
MEASURED_CANVAS = (832, 480)
REFERENCE_CANVAS = (1472, 832)
CURRENT_ROW = {"overhead_mb": 7000.0, "per_frame_mb": 185.0}
RECIPE_IDS = {
    "wan_ti2v": "wan22_ti2v_5b_i2v_single_pass_v1",
    "fastwan_8gb": "fastwan22_ti2v_5b_dmd3_i2v_v1",
}
EFFECTIVE_VIDEO_SEED = 944021193
REQUIRED_COMFYUI_URL = "http://127.0.0.1:8000"


class ReductionError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReductionError(f"Cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load("wan_cost_reducer_shared", SCRATCH / "humo_diet_sidecar.py")
BASELINE_SCHEMA = _load(
    "wan_cost_reducer_baseline_schema", SCRATCH / "capture_wan_cost_baseline.py"
)
MANAGER_GUARD = _load(
    "wan_cost_reducer_manager_guard", SCRATCH / "manager_offline_guard.py"
)
OWNERSHIP = _load("wan_cost_reducer_ownership", SCRATCH / "wan_cost_ownership.py")


def configure_attempt(attempt_id: str) -> None:
    global TELEMETRY_ROOT, EVIDENCE_ROOT, EVIDENCE_CLIP_ROOT, DEFAULT_OUTPUT
    global ACTIVE_ATTEMPT_ID
    if ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is None:
        raise ReductionError(f"Invalid campaign attempt id: {attempt_id!r}")
    ACTIVE_ATTEMPT_ID = attempt_id
    TELEMETRY_ROOT = TELEMETRY_BASE / attempt_id
    EVIDENCE_ROOT = EVIDENCE_BASE / attempt_id
    EVIDENCE_CLIP_ROOT = EVIDENCE_ROOT / "clips"
    DEFAULT_OUTPUT = FIT_BASE / f"{attempt_id}.json"


def receipt_path(engine: str, frames: int, run: int) -> Path:
    return TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run{run}.json"


def expected_paths() -> list[Path]:
    return [
        receipt_path(engine, frames, run)
        for engine, lengths in LADDERS.items()
        for frames in lengths
        for run in (1, 2)
    ]


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_stable_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = BASE.stable_file_snapshot(path)
    if not snapshot.get("exists"):
        raise ReductionError(f"Missing receipt: {path}")
    raw = path.read_bytes()
    if len(raw) != snapshot["bytes"] or BASE.sha256_bytes(raw) != snapshot["sha256"]:
        raise ReductionError(f"Receipt changed after stable snapshot: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReductionError(f"Receipt is not UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ReductionError(f"Receipt root is not a mapping: {path}")
    return payload, snapshot


def _same_server(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        int(left.get("serving_pid") or -1) == int(right.get("serving_pid") or -2)
        and float(left.get("process_create_time") or -1)
        == float(right.get("process_create_time") or -2)
        and left.get("argv") == right.get("argv")
        and int(left.get("parent_pid") or -1) == int(right.get("parent_pid") or -2)
    )


def validated_recorded_launcher_argv(
    recorded: list[str], server_log: Path
) -> list[str]:
    """Accept Windows path spelling only after canonical command equivalence."""
    canonical = [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/c",
        str(OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"),
        str(server_log),
        "WAN",
    ]
    if not OWNERSHIP.launcher_argv_matches(recorded, canonical):
        raise ReductionError(
            "Recorded launcher argv is not semantically the canonical "
            "cmd/OTR-script/attempt-log/WAN command"
        )
    return list(recorded)


def _recompute_peaks(receipt: dict[str, Any]) -> dict[str, float]:
    sampler = receipt.get("sampler") or {}
    if sampler.get("coverage_errors"):
        raise ReductionError(f"Sampler coverage errors: {sampler['coverage_errors']}")
    if float(sampler.get("interval_s") or 0) != 0.2:
        raise ReductionError("Raw receipt is not a 200 ms sample series")
    samples = sampler.get("samples") or []
    if int(sampler.get("sample_count") or 0) != len(samples) or not samples:
        raise ReductionError("Raw sampler count is empty or inconsistent")
    values = [float(row["vram_used_mib"]) for row in samples]
    sidecar_peak = max(values)
    if not math.isclose(
        sidecar_peak, float(sampler.get("peak_vram_mib")), abs_tol=1e-9
    ):
        raise ReductionError("Stored sampler peak does not match retained samples")
    if not math.isclose(
        sidecar_peak, float(receipt.get("sidecar_peak_vram_mib")), abs_tol=1e-9
    ):
        raise ReductionError("Top-level sidecar peak does not match retained samples")
    clips = (receipt.get("node_episode_manifest_payload") or {}).get("clips") or []
    if len(clips) != 1:
        raise ReductionError("Cannot recover one adapter peak from the episode manifest")
    try:
        adapter_peak = float(clips[0].get("vram_peak_mb"))
    except (TypeError, ValueError) as exc:
        raise ReductionError("Adapter render-window peak is not numeric") from exc
    if adapter_peak <= 0:
        raise ReductionError("Adapter render-window peak is not positive")
    if not math.isclose(
        adapter_peak,
        float(receipt.get("adapter_render_peak_vram_mib")),
        abs_tol=1e-9,
    ):
        raise ReductionError("Top-level adapter peak does not match the manifest")
    conservative_peak = max(sidecar_peak, adapter_peak)
    if not math.isclose(
        conservative_peak,
        float(receipt.get("warm_peak_vram_mib")),
        abs_tol=1e-9,
    ):
        raise ReductionError("Top-level warm peak is not max(sidecar, adapter)")
    derivation = receipt.get("warm_peak_derivation") or {}
    expected_source = (
        "adapter_render_window_100ms"
        if adapter_peak >= sidecar_peak
        else "sidecar_machine_wide_200ms"
    )
    if (
        derivation.get("operation") != "max"
        or derivation.get("inputs")
        != ["sidecar_peak_vram_mib", "adapter_render_peak_vram_mib"]
        or derivation.get("selected_source") != expected_source
    ):
        raise ReductionError("Warm peak derivation receipt is inconsistent")
    return {
        "sidecar_peak_mib": sidecar_peak,
        "adapter_render_peak_mib": adapter_peak,
        "conservative_peak_mib": conservative_peak,
    }


def _baseline(receipt: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    binding = receipt.get("quiescent_desktop_baseline") or {}
    snapshot = binding.get("receipt") or {}
    path = Path(str(snapshot.get("path") or ""))
    payload, current = load_stable_json(path)
    if current.get("sha256") != snapshot.get("sha256"):
        raise ReductionError("Quiescent baseline receipt hash drifted")
    errors = BASELINE_SCHEMA.receipt_validation_errors(
        payload, int(payload.get("gpu_index", -1))
    )
    if errors:
        raise ReductionError(
            "Quiescent baseline no longer satisfies its conjunctive WDDM schema: "
            + "; ".join(errors)
        )
    value = float(payload.get("vram_used_mib"))
    if not math.isclose(value, float(binding.get("vram_used_mib")), abs_tol=1e-9):
        raise ReductionError("Receipt copied a different quiescent baseline value")
    samples = payload.get("samples") or []
    recomputed = max(float(row["vram_used_mib"]) for row in samples)
    if len(samples) != 5 or not math.isclose(value, recomputed, abs_tol=1e-9):
        raise ReductionError("Baseline value is not max(five retained samples)")
    return value, current


def _rendered_clip_evidence(receipt: dict[str, Any], label: str) -> dict[str, Any]:
    binding = receipt.get("rendered_clip") or {}
    source_before = binding.get("source_before") or {}
    source_after = binding.get("source_after") or {}
    evidence = binding.get("evidence") or {}
    freshness = binding.get("freshness_window") or {}
    state_files = binding.get("fresh_state_files") or {}
    path = Path(str(evidence.get("path") or ""))
    expected = EVIDENCE_CLIP_ROOT / f"{label}.mp4"
    if path.resolve() != expected.resolve() or not path.is_file():
        raise ReductionError(f"{label} lab clip evidence path is absent or unexpected")
    current = BASE.stable_file_snapshot(path)
    manifest = receipt.get("node_episode_manifest_payload") or {}
    clips = manifest.get("clips") or []
    manifest_path = str(clips[0].get("path") or "") if len(clips) == 1 else ""
    if (
        binding.get("source_stable_during_copy") is not True
        or freshness.get("within_window") is not True
        or int(freshness.get("replay_started_at_ns") or -1)
        != int(receipt.get("started_at_ns") or -2)
        or not (
            int(freshness.get("replay_started_at_ns") or 0)
            <= int(freshness.get("source_mtime_ns") or -1)
            <= int(freshness.get("captured_at_ns") or -2)
        )
        or binding.get("manifest_path") != manifest_path
        or state_files.get("node_episode_report")
        != receipt.get("node_episode_report_after")
        or state_files.get("node_episode_manifest")
        != receipt.get("node_episode_manifest_after")
        or any(
            not (state or {}).get("exists")
            or not (state or {}).get("sha256")
            or not (
                int(receipt.get("started_at_ns") or 0)
                <= int((state or {}).get("mtime_ns") or -1)
                <= int(freshness.get("captured_at_ns") or -2)
            )
            for state in state_files.values()
        )
        or set(state_files)
        != {"node_episode_report", "node_episode_manifest"}
        or source_before != source_after
        or int(evidence.get("bytes") or 0) <= 0
        or evidence.get("bytes") != source_before.get("bytes")
        or evidence.get("sha256") != source_before.get("sha256")
        or current.get("bytes") != evidence.get("bytes")
        or current.get("sha256") != evidence.get("sha256")
    ):
        raise ReductionError(f"{label} rendered clip is not hash/freshness bound")
    return {
        "path": str(path),
        "bytes": int(current["bytes"]),
        "sha256": current["sha256"],
        "source_mtime_ns": int(freshness["source_mtime_ns"]),
    }


def _manager_offline_evidence(receipt: dict[str, Any], label: str) -> dict[str, Any]:
    binding = receipt.get("manager_offline_guard") or {}
    guard_snapshot = binding.get("boot_guard_receipt") or {}
    guard_path = EVIDENCE_ROOT / "manager_boot_guard.json"
    guard_payload, current_guard = load_stable_json(guard_path)
    if (
        current_guard.get("sha256") != guard_snapshot.get("sha256")
        or guard_payload != binding.get("boot_guard_payload")
        or guard_payload.get("kind")
        != "wan-cost-ladder-manager-offline-boot-guard"
        or guard_payload.get("status") != "pass"
        or guard_payload.get("campaign_attempt_id") != ACTIVE_ATTEMPT_ID
    ):
        raise ReductionError(f"{label} Manager boot guard receipt drifted")
    guarded_server = guard_payload.get("server_instance") or {}
    if not _same_server(guarded_server, receipt.get("server_instance") or {}):
        raise ReductionError(f"{label} guard server differs from raw receipt server")
    recorded_launcher_argv = list(
        (guarded_server.get("ownership_chain") or {}).get(
            "expected_launcher_argv"
        )
        or []
    )
    recorded_launcher_argv = validated_recorded_launcher_argv(
        recorded_launcher_argv,
        EVIDENCE_ROOT / "wan_cost_ladder.server.log",
    )
    chain_errors = OWNERSHIP.validate_chain_receipt(
        guarded_server.get("ownership_chain") or {},
        guarded_server,
        recorded_launcher_argv,
    )
    if chain_errors:
        raise ReductionError(f"{label} owned-process chain failed: {chain_errors}")
    boot_environment = guard_payload.get("boot_environment") or {}
    credential_errors = (
        MANAGER_GUARD.validate_offline_credential_environment_evidence(
            boot_environment.get("offline_credentials") or {}
        )
    )
    if credential_errors:
        raise ReductionError(
            f"{label} production boot credential proof failed: {credential_errors}"
        )
    if boot_environment.get("set") != {
        "OTR_HEADLESS_PORT": "8000",
        "COMFYUI_URL": REQUIRED_COMFYUI_URL,
        "PYTHONDONTWRITEBYTECODE": "1",
        **MANAGER_GUARD.OFFLINE_CREDENTIAL_ENVIRONMENT,
    }:
        raise ReductionError(f"{label} production boot environment pins drifted")
    source = guard_payload.get("source") or {}
    guard_source = (SCRATCH / "manager_offline_guard.py").resolve()
    if (
        Path(str(source.get("path") or "")).resolve() != guard_source
        or source.get("sha256") != sha256_file(guard_source)
    ):
        raise ReductionError(f"{label} Manager guard source hash drifted")
    log_path = EVIDENCE_ROOT / "wan_cost_ladder.server.log"
    boot_scan = guard_payload.get("boot_log_scan") or {}
    if guard_payload.get("authoritative_server_reported_mode") != boot_scan.get(
        "authoritative_server_reported_mode"
    ):
        raise ReductionError(
            f"{label} authoritative server-reported Manager mode field drifted"
        )
    errors = MANAGER_GUARD.validate_log_prefix_binding(boot_scan, log_path)
    if errors:
        raise ReductionError(f"{label} Manager boot prefix failed: {errors}")
    baseline_binding = receipt.get("quiescent_desktop_baseline") or {}
    baseline_path = Path(
        str((baseline_binding.get("receipt") or {}).get("path") or "")
    )
    baseline_payload, _baseline_snapshot = load_stable_json(baseline_path)
    baseline_sha = (
        ((baseline_payload.get("manager_config") or {}).get("config") or {}).get(
            "sha256"
        )
    )
    scans = {}
    for phase in ("pre_render", "post_render"):
        config = binding.get(f"{phase}_config") or {}
        config_errors = MANAGER_GUARD.validate_offline_evidence(
            config, require_current_hash=True
        )
        if config_errors:
            raise ReductionError(
                f"{label} Manager {phase} config failed: {config_errors}"
            )
        if ((config.get("config") or {}).get("sha256")) != baseline_sha:
            raise ReductionError(f"{label} Manager {phase} crossed baseline config SHA")
        scan = binding.get(f"{phase}_full_log_scan") or {}
        scan_errors = MANAGER_GUARD.validate_runtime_log_binding(scan, log_path)
        if scan_errors:
            raise ReductionError(
                f"{label} Manager {phase} full-log scan failed: {scan_errors}"
            )
        scans[phase] = {
            "config_sha256": (config.get("config") or {}).get("sha256"),
            "authoritative_server_reported_mode": scan.get(
                "authoritative_server_reported_mode"
            ),
            "log_prefix_bytes": scan.get("prefix_bytes"),
            "log_prefix_sha256": scan.get("prefix_sha256"),
        }
    return {
        "boot_guard_sha256": current_guard["sha256"],
        "baseline_manager_config_sha256": baseline_sha,
        "authoritative_server_reported_mode": guard_payload.get(
            "authoritative_server_reported_mode"
        ),
        "boot_offline_credentials": boot_environment.get("offline_credentials"),
        "phases": scans,
    }


def validate_cell_pair(
    engine: str,
    frames: int,
    first: dict[str, Any],
    warm: dict[str, Any],
    first_snapshot: dict[str, Any],
) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    manager_artifacts: dict[str, dict[str, Any]] = {}
    expected = (
        (first, "pair_first", f"{engine}_f{frames:03d}_run1"),
        (warm, "warm_second", f"{engine}_f{frames:03d}_run2"),
    )
    for receipt, role, label in expected:
        if (
            receipt.get("kind") != "wan-cost-ladder-raw-telemetry"
            or receipt.get("status") != "measured"
            or receipt.get("errors") != []
            or receipt.get("engine") != engine
            or int(receipt.get("model_render_frames") or 0) != frames
            or int(receipt.get("delivered_frames") or 0) != frames - 1
            or receipt.get("run_role") != role
            or receipt.get("label") != label
            or (
                ACTIVE_ATTEMPT_ID is not None
                and receipt.get("campaign_attempt_id") != ACTIVE_ATTEMPT_ID
            )
            or (receipt.get("gpu_lease") or {}).get("release", {}).get("success") is not True
            or ((receipt.get("manager_config") or {}).get("config") or {}).get(
                "network_mode"
            )
            != "offline"
            or (receipt.get("replay_result") or {}).get("success") is not True
        ):
            raise ReductionError(f"Invalid {label} receipt contract")
        manager_artifacts[role] = _manager_offline_evidence(
            receipt, label
        )
        server = receipt.get("server_instance") or {}
        serving_pid = int(server.get("serving_pid") or -1)
        listeners = server.get("listeners") or []
        endpoint = receipt.get("replay_endpoint") or {}
        command_environment = (receipt.get("command") or {}).get("environment") or {}
        replay_credential = (
            receipt.get("replay_result") or {}
        ).get("offline_credential_environment") or {}
        command_credential_errors = (
            MANAGER_GUARD.validate_offline_credential_environment_evidence(
                command_environment.get("offline_credentials") or {}
            )
        )
        expected_replay_credential = {
            "validated": True,
            "nonsecret_sentinel_length": len(
                MANAGER_GUARD.OFFLINE_TOKEN_SENTINEL
            ),
            "set_key_names": sorted(
                MANAGER_GUARD.OFFLINE_CREDENTIAL_ENVIRONMENT
            ),
            "scrubbed_key_names_absent": list(
                MANAGER_GUARD.SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS
            ),
            "ambient_values_never_read_or_returned": True,
        }
        if (
            endpoint.get("validated") is not True
            or endpoint.get("required_url") != REQUIRED_COMFYUI_URL
            or endpoint.get("replay_reported_url") != REQUIRED_COMFYUI_URL
            or int(endpoint.get("serving_pid") or -2) != serving_pid
            or endpoint.get("process_create_time") != server.get("process_create_time")
            or endpoint.get("listeners") != listeners
            or command_environment.get("required") != REQUIRED_COMFYUI_URL
            or command_environment.get("pinned_child_value") != REQUIRED_COMFYUI_URL
            or command_environment.get("python_dont_write_bytecode") != "1"
            or (receipt.get("replay_result") or {}).get("comfyui_url")
            != REQUIRED_COMFYUI_URL
            or (receipt.get("replay_result") or {}).get("python_dont_write_bytecode")
            is not True
            or command_credential_errors
            or replay_credential != expected_replay_credential
        ):
            raise ReductionError(f"{label} replay endpoint is not receipt-bound")
        if not listeners or any(
            row.get("address") not in {"127.0.0.1", "::1"}
            or int(row.get("port") or -1) != 8000
            or int(row.get("pid") or -1) != serving_pid
            for row in listeners
        ):
            raise ReductionError(f"{label} server listener is not owned loopback:8000")
        artifacts[role] = _rendered_clip_evidence(receipt, label)
        manifest = receipt.get("node_episode_manifest_payload") or {}
        report = receipt.get("node_episode_report_payload") or {}
        if manifest.get("canvas") != {"w": 832, "h": 480}:
            raise ReductionError(f"{label} manifest canvas drifted")
        trace = report.get("trace") or []
        if (
            len(trace) != 1
            or trace[0].get("shot_id") != "shot_b001"
            or int(trace[0].get("video_seed") or -1) != EFFECTIVE_VIDEO_SEED
            or trace[0].get("final_engine") != engine
        ):
            raise ReductionError(f"{label} fixed effective seed/engine was not proved")
        clips = manifest.get("clips") or []
        if len(clips) != 1 or clips[0].get("engine_id") != engine:
            raise ReductionError(f"{label} does not contain one requested-engine clip")
        if (
            clips[0].get("recipe") != RECIPE_IDS[engine]
            or clips[0].get("quant") != "Q5_K_M"
            or clips[0].get("use_lora") != (engine == "fastwan_8gb")
            or clips[0].get("render_canvas") != "832x480"
        ):
            raise ReductionError(f"{label} production recipe identity drifted")
        segments = clips[0].get("segments") or []
        if (
            int(clips[0].get("frame_count") or 0) != frames - 1
            or len(segments) != 1
            or int(segments[0].get("render_frames") or 0) != frames
            or int(segments[0].get("drop_head") or 0) != 0
            or int(segments[0].get("trim_tail") or 0) != 1
            or int(segments[0].get("native_frame_count") or 0) != frames
        ):
            raise ReductionError(f"{label} does not prove exact N-frame model execution")
    if not _same_server(first.get("server_instance") or {}, warm.get("server_instance") or {}):
        raise ReductionError(f"{engine} f{frames} warm pair crossed server identity")
    previous = warm.get("previous_pair_receipt") or {}
    if previous.get("sha256") != first_snapshot.get("sha256"):
        raise ReductionError(f"{engine} f{frames} warm receipt does not hash-bind run1")
    first_log_end = ((first.get("server_log") or {}).get("ending") or {})
    warm_log_start = ((warm.get("server_log") or {}).get("starting") or {})
    gap = warm.get("inter_run_log_gap") or {}
    if (
        gap.get("prefix_sha256_reverified") is not True
        or gap.get("execution_markers_found") != []
        or int(gap.get("previous_end_offset") or -1)
        != int(first_log_end.get("bytes") or -2)
        or int(gap.get("current_start_offset") or -1)
        != int(warm_log_start.get("bytes") or -2)
    ):
        raise ReductionError(f"{engine} f{frames} runs were not consecutive")
    if first.get("fixture") != warm.get("fixture"):
        raise ReductionError(f"{engine} f{frames} fixture changed within warm pair")
    if int(first.get("cache_buster") or 0) == int(warm.get("cache_buster") or 0):
        raise ReductionError(f"{engine} f{frames} reused a Comfy cache identity")
    baseline_first, baseline_snapshot_first = _baseline(first)
    baseline_warm, baseline_snapshot_warm = _baseline(warm)
    if (
        baseline_snapshot_first.get("sha256") != baseline_snapshot_warm.get("sha256")
        or not math.isclose(baseline_first, baseline_warm, abs_tol=1e-9)
    ):
        raise ReductionError(f"{engine} f{frames} baseline changed within pair")
    first_peaks = _recompute_peaks(first)
    warm_peaks = _recompute_peaks(warm)
    first_peak = first_peaks["conservative_peak_mib"]
    warm_peak = warm_peaks["conservative_peak_mib"]
    demand = warm_peak - baseline_warm
    if demand < 0:
        raise ReductionError(f"{engine} f{frames} warm demand is negative")
    if not math.isclose(demand, float(warm.get("cost_row_demand_mib")), abs_tol=1e-9):
        raise ReductionError(f"{engine} f{frames} stored demand does not recompute")
    return {
        "engine": engine,
        "model_render_frames": frames,
        "delivered_frames": frames - 1,
        "pair_first_peak_mib": first_peak,
        "pair_first_sidecar_peak_mib": first_peaks["sidecar_peak_mib"],
        "pair_first_adapter_render_peak_mib": first_peaks[
            "adapter_render_peak_mib"
        ],
        "warm_peak_mib": warm_peak,
        "warm_sidecar_peak_mib": warm_peaks["sidecar_peak_mib"],
        "warm_adapter_render_peak_mib": warm_peaks["adapter_render_peak_mib"],
        "quiescent_desktop_baseline_mib": baseline_warm,
        "warm_demand_mib": demand,
        "warm_duration_s": float(warm.get("duration_s")),
        "rendered_clip_evidence": artifacts,
        "manager_offline_evidence": manager_artifacts,
        "server_pid": int((warm.get("server_instance") or {})["serving_pid"]),
        "receipt_sha256s": {
            "pair_first": first_snapshot["sha256"],
            "warm_second": None,
        },
    }


def fit_upper_envelope(points: Iterable[tuple[int, float]]) -> dict[str, Any]:
    pts = [(int(length), float(demand)) for length, demand in points]
    if len(pts) < 3 or len({length for length, _ in pts}) < 3:
        raise ReductionError("Cost fit requires at least three distinct measured lengths")
    n = float(len(pts))
    sx = sum(length for length, _ in pts)
    sy = sum(demand for _, demand in pts)
    sxx = sum(length * length for length, _ in pts)
    sxy = sum(length * demand for length, demand in pts)
    denominator = n * sxx - sx * sx
    if denominator == 0:
        raise ReductionError("Cost fit is degenerate")
    raw_slope = (n * sxy - sx * sy) / denominator
    intercept = (sy - raw_slope * sx) / n
    slope = max(0.0, raw_slope)
    if slope != raw_slope:
        intercept = sy / n
    residuals = [demand - (intercept + slope * length) for length, demand in pts]
    max_positive = max(residuals + [0.0])
    overhead = math.ceil((intercept + max_positive) * 10.0) / 10.0
    slope_stored = math.ceil(slope * 1000.0) / 1000.0
    scale = (MEASURED_CANVAS[0] * MEASURED_CANVAS[1]) / (
        REFERENCE_CANVAS[0] * REFERENCE_CANVAS[1]
    )
    per_frame_ref = math.ceil((slope_stored / scale) * 1000.0) / 1000.0
    envelope_predictions = [overhead + slope_stored * length for length, _ in pts]
    if any(prediction + 1e-9 < demand for prediction, (_, demand) in zip(envelope_predictions, pts)):
        raise ReductionError("Rounded upper envelope undercuts a measured point")
    return {
        "unit": "MiB of demand above the quiescent desktop baseline",
        "points": [
            {"model_render_frames": length, "warm_demand_mib": demand}
            for length, demand in pts
        ],
        "least_squares_measured_canvas": {
            "overhead_mb": intercept,
            "per_frame_mb": raw_slope,
        },
        "upper_envelope_measured_canvas": {
            "overhead_mb": overhead,
            "per_frame_mb": slope_stored,
        },
        "resolution_basis": {
            "measured_canvas": list(MEASURED_CANVAS),
            "reference_canvas": list(REFERENCE_CANVAS),
            "measured_over_reference": scale,
        },
        "candidate_row_at_1472x832": {
            "overhead_mb": overhead,
            "per_frame_mb": per_frame_ref,
        },
        "residuals_mb": residuals,
        "max_positive_residual_mb": max_positive,
        "max_absolute_residual_mb": max(abs(value) for value in residuals),
        "slope_was_clamped_nonnegative": slope != raw_slope,
    }


def non_monotonic_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: int(row["model_render_frames"]))
    findings = []
    for left, right in zip(ordered, ordered[1:]):
        if float(right[key]) < float(left[key]):
            findings.append(
                {
                    "from_frames": left["model_render_frames"],
                    "to_frames": right["model_render_frames"],
                    "from_value": left[key],
                    "to_value": right[key],
                    "decrease": float(left[key]) - float(right[key]),
                }
            )
    return findings


def reduce(receipts: dict[Path, tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    missing = [str(path) for path in expected_paths() if path not in receipts]
    if missing:
        raise ReductionError(f"Ladder incomplete; missing {len(missing)} receipt(s): {missing}")
    engine_rows: dict[str, list[dict[str, Any]]] = {engine: [] for engine in LADDERS}
    for engine, lengths in LADDERS.items():
        for frames in lengths:
            first, first_snapshot = receipts[receipt_path(engine, frames, 1)]
            warm, warm_snapshot = receipts[receipt_path(engine, frames, 2)]
            row = validate_cell_pair(engine, frames, first, warm, first_snapshot)
            row["receipt_sha256s"]["warm_second"] = warm_snapshot["sha256"]
            engine_rows[engine].append(row)

    all_baselines = {
        float(row["quiescent_desktop_baseline_mib"])
        for rows in engine_rows.values()
        for row in rows
    }
    if len(all_baselines) != 1:
        raise ReductionError(f"Campaign mixed quiescent baselines: {sorted(all_baselines)}")
    fits = {}
    for engine, rows in engine_rows.items():
        fits[engine] = fit_upper_envelope(
            (int(row["model_render_frames"]), float(row["warm_demand_mib"]))
            for row in rows
        )
        fits[engine]["non_monotonic_warm_peak"] = non_monotonic_rows(rows, "warm_peak_mib")
        fits[engine]["non_monotonic_warm_demand"] = non_monotonic_rows(
            rows, "warm_demand_mib"
        )
        fits[engine]["candidate_only"] = True
        fits[engine]["qualification_required"] = (
            "OTR prepare()+render_clip lifecycle with the candidate row installed"
        )

    return {
        "schema_version": 1,
        "kind": "wan-cost-ladder-candidate-fit",
        "status": "MEASURED_CANDIDATE_ONLY",
        "measured": "OTR-side production wrapper, warm second consecutive runs",
        "campaign_attempt_id": ACTIVE_ATTEMPT_ID,
        "canvas": list(MEASURED_CANVAS),
        "reference_canvas": list(REFERENCE_CANVAS),
        "quiescent_desktop_baseline_mib": next(iter(all_baselines)),
        "current_disqualified_row": CURRENT_ROW,
        "cells": engine_rows,
        "fits": fits,
        "interpretation": [
            "Each warm cell preserves the raw machine-wide 200 ms sidecar peak and OTR's independent 100 ms render-window peak; the fitted peak is their conservative maximum.",
            "Candidate demand subtracts one receipt-bound pre-server quiescent desktop baseline, never warm retained residency.",
            "Model render frames N are fitting inputs; the production assembler's N-1 delivery is not substituted.",
            "Non-monotonic observations are preserved and never smoothed away.",
            "Final qualification must occur in OTR through prepare()+render_clip; this lab fit alone cannot ship a row.",
        ],
        "source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
    }


def load_existing() -> dict[Path, tuple[dict[str, Any], dict[str, Any]]]:
    rows = {}
    for path in expected_paths():
        if path.is_file():
            rows[path] = load_stable_json(path)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--attempt-id")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.attempt_id:
        configure_attempt(args.attempt_id)
    receipts = load_existing()
    missing = [str(path) for path in expected_paths() if path not in receipts]
    if missing:
        print(
            json.dumps(
                {
                    "status": "PENDING_MEASUREMENTS",
                    "present": len(receipts),
                    "required": len(expected_paths()),
                    "missing": missing,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    try:
        payload = reduce(receipts)
    except Exception as exc:
        print(f"[wan-cost-reducer] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.write:
        output = Path(args.output) if args.output else DEFAULT_OUTPUT
        if not output.is_absolute() or output.suffix.lower() != ".json":
            raise ReductionError("Output must be an absolute JSON path")
        try:
            output.resolve().relative_to(DEFAULT_OUTPUT.parent.resolve())
        except ValueError as exc:
            raise ReductionError(f"Output escapes {DEFAULT_OUTPUT.parent}: {output}") from exc
        BASE.atomic_create_json(output, payload)
        print(f"[wan-cost-reducer] wrote {output}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
