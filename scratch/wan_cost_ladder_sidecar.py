#!/usr/bin/env python
"""Measure one WAN/FastWan cost-ladder run at 200 ms cadence.

The sidecar owns the GPU lease, positively identifies the already-booted OTR
production server, requires ComfyUI-Manager offline mode, invokes only the
LAB-owned cache-bust replay shim, and writes one append-only raw receipt.  A
``warm_second`` run must cite the immediately preceding ``pair_first`` receipt;
the server PID/create-time, fixture hashes, quiescent baseline receipt, and log
boundary must match.

It never boots or stops a server and never modifies OTR.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence


LAB_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = LAB_ROOT / "scratch"
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
REPLAY = SCRATCH / "otr_visual_smoke_cachebust.py"
TELEMETRY_ROOT = LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder" / "telemetry"
BASELINE_ROOT = LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder"
EVIDENCE_ROOT = BASELINE_ROOT / "evidence"
EVIDENCE_CLIP_ROOT = EVIDENCE_ROOT / "clips"
BUNDLE_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_cost_ladder_measurement"
)
LADDERS = {
    "wan_ti2v": (25, 65, 93, 129, 177),
    "fastwan_8gb": (25, 93, 177),
}
RECIPE_IDS = {
    "wan_ti2v": "wan22_ti2v_5b_i2v_single_pass_v1",
    "fastwan_8gb": "fastwan22_ti2v_5b_dmd3_i2v_v1",
}
EFFECTIVE_VIDEO_SEED = 944021193
OTR_PIN_PATHS = {
    "_otr_soak_server_launch.cmd": OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd",
    "_otr_headless_model_paths.yaml": OTR_ROOT / "scripts" / "_otr_headless_model_paths.yaml",
    "otr_video_render_batch.py": OTR_ROOT / "nodes" / "otr_video_render_batch.py",
    "otr_visual_smoke.py": OTR_ROOT / "scripts" / "otr_visual_smoke.py",
    "otr_canonical.json": OTR_ROOT / "workflows" / "otr_canonical.json",
    "render_driver.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "render_driver.py",
    "coverage_plan.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "coverage_plan.py",
    "motion_common.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "motion_common.py",
    "wan_shared.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "wan_shared.py",
    "eng_wan_ti2v.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "eng_wan_ti2v.py",
    "eng_fastwan_8gb.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "eng_fastwan_8gb.py",
    "dmd_sampler.py": OTR_ROOT / "nodes" / "_otr_video_engines" / "dmd_sampler.py",
}
DEFAULT_INTERVAL_S = 0.2
DEFAULT_MAX_GAP_S = 0.75
RESULT_PREFIX = "WAN_COST_REPLAY_RESULT="
REQUIRED_COMFYUI_URL = "http://127.0.0.1:8000"
ATTEMPT_ID_PATTERN = re.compile(r"attempt-\d{3}")


class SidecarError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SidecarError(f"Cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load("wan_cost_sidecar_shared", SCRATCH / "humo_diet_sidecar.py")
BASELINE_SCHEMA = _load(
    "wan_cost_sidecar_baseline_schema", SCRATCH / "capture_wan_cost_baseline.py"
)
MANAGER_GUARD = _load(
    "wan_cost_sidecar_manager_guard", SCRATCH / "manager_offline_guard.py"
)
OTR_SIDE = _load("wan_cost_otr_identity", SCRATCH / "otr_resource_sidecar.py")
OWNERSHIP = _load("wan_cost_sidecar_ownership", SCRATCH / "wan_cost_ownership.py")
sys.path.insert(0, str(LAB_ROOT))
from lab_locks import GpuLease, LeaseError  # noqa: E402


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _within(path: Path, root: Path, label: str) -> Path:
    candidate = _absolute(path)
    boundary = _absolute(root)
    try:
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise SidecarError(f"{label} escapes {boundary}: {candidate}") from exc
    return candidate


def canonical_cache_buster(engine: str, frames: int, run_role: str) -> int:
    if engine not in LADDERS or frames not in LADDERS[engine]:
        raise SidecarError(f"Unsupported ladder cell {engine} f{frames}")
    if run_role not in {"pair_first", "warm_second"}:
        raise SidecarError(f"Unsupported run role {run_role!r}")
    engine_offset = 20 if engine == "wan_ti2v" else 220
    index = LADDERS[engine].index(frames)
    return engine_offset + index * 2 + (1 if run_role == "pair_first" else 2)


def canonical_label(engine: str, frames: int, run_role: str) -> str:
    suffix = "run1" if run_role == "pair_first" else "run2"
    return f"{engine}_f{frames:03d}_{suffix}"


def pinned_replay_environment(
    source: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Override, redact, and receipt the sole allowed replay endpoint."""
    environment, credential_evidence = (
        MANAGER_GUARD.pin_offline_credential_environment(source)
    )
    ambient = environment.pop("COMFYUI_URL", None)
    environment["COMFYUI_URL"] = REQUIRED_COMFYUI_URL
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    evidence = {
        "required": REQUIRED_COMFYUI_URL,
        "pinned_child_value": environment["COMFYUI_URL"],
        "ambient_present": ambient is not None,
        "ambient_matched_required": ambient == REQUIRED_COMFYUI_URL,
        "conflicting_ambient_cleared": (
            ambient is not None and ambient != REQUIRED_COMFYUI_URL
        ),
        # Never persist a possibly credential-bearing ambient URL.
        "ambient_value_redacted": ambient is not None,
        "ambient_sha256": (
            BASE.sha256_bytes(str(ambient).encode("utf-8"))
            if ambient is not None
            else None
        ),
        "python_dont_write_bytecode": environment["PYTHONDONTWRITEBYTECODE"],
        "offline_credentials": credential_evidence,
    }
    return environment, evidence


def validate_replay_endpoint_binding(
    server: dict[str, Any],
    environment_evidence: dict[str, Any],
    replay_result: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Bind the pinned child URL to the already-identified serving PID."""
    errors = []
    serving_pid = int(server.get("serving_pid") or -1)
    listeners = list(server.get("listeners") or [])
    if (
        environment_evidence.get("required") != REQUIRED_COMFYUI_URL
        or environment_evidence.get("pinned_child_value") != REQUIRED_COMFYUI_URL
    ):
        errors.append("Replay child environment was not pinned to owned port 8000")
    if replay_result.get("comfyui_url") != REQUIRED_COMFYUI_URL:
        errors.append("Replay result did not self-attest the owned port-8000 URL")
    if (
        environment_evidence.get("python_dont_write_bytecode") != "1"
        or replay_result.get("python_dont_write_bytecode") is not True
    ):
        errors.append("Replay did not prove bytecode writes were disabled")
    credential_errors = (
        MANAGER_GUARD.validate_offline_credential_environment_evidence(
            environment_evidence.get("offline_credentials") or {}
        )
    )
    if credential_errors:
        errors.append(
            "Replay child offline credential environment receipt failed: "
            + "; ".join(credential_errors)
        )
    child_credential = replay_result.get("offline_credential_environment") or {}
    expected_child_credential = {
        "validated": True,
        "nonsecret_sentinel_length": len(MANAGER_GUARD.OFFLINE_TOKEN_SENTINEL),
        "set_key_names": sorted(MANAGER_GUARD.OFFLINE_CREDENTIAL_ENVIRONMENT),
        "scrubbed_key_names_absent": list(
            MANAGER_GUARD.SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS
        ),
        "ambient_values_never_read_or_returned": True,
    }
    if child_credential != expected_child_credential:
        errors.append("Replay child did not self-attest the offline credential contract")
    if not listeners or any(
        row.get("address") not in {"127.0.0.1", "::1"}
        or int(row.get("port") or -1) != 8000
        or int(row.get("pid") or -1) != serving_pid
        for row in listeners
    ):
        errors.append("Owned server listener receipt does not bind loopback:8000 to serving PID")
    binding = {
        "required_url": REQUIRED_COMFYUI_URL,
        "replay_reported_url": replay_result.get("comfyui_url"),
        "serving_pid": serving_pid,
        "process_create_time": server.get("process_create_time"),
        "listeners": listeners,
        "environment": environment_evidence,
        "validated": not errors,
    }
    return binding, errors


def capture_rendered_clip(
    manifest: dict[str, Any],
    *,
    label: str,
    started_ns: int,
    server_output: Path,
    evidence_clip_root: Path | None = None,
    report_snapshot: dict[str, Any] | None = None,
    manifest_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy/hash the one fresh manifest clip into append-only lab evidence."""
    clips = manifest.get("clips") or []
    if len(clips) != 1:
        raise SidecarError("Cannot bind media evidence without exactly one manifest clip")
    clip = clips[0]
    if clip.get("exists") is not True or clip.get("type") != "video":
        raise SidecarError("Manifest clip is not an existing video artifact")
    source = _within(Path(str(clip.get("path") or "")), server_output, "rendered clip")
    if source.suffix.lower() != ".mp4" or not source.is_file():
        raise SidecarError(f"Rendered clip is not an MP4 file: {source}")
    clip_root = evidence_clip_root or EVIDENCE_CLIP_ROOT
    destination = _within(
        clip_root / f"{label}.mp4",
        clip_root,
        "lab clip evidence",
    )
    if destination.exists():
        raise FileExistsError(f"Lab clip evidence already exists: {destination}")

    before = BASE.stable_file_snapshot(source)
    if not before.get("exists") or int(before.get("bytes") or 0) <= 0:
        raise SidecarError(f"Rendered clip is missing or empty: {source}")
    captured_ns = time.time_ns()
    source_mtime_ns = int(before.get("mtime_ns") or 0)
    if not int(started_ns) <= source_mtime_ns <= captured_ns:
        raise SidecarError(
            "Rendered clip mtime is outside this replay's start/capture window"
        )
    state_files = {
        "node_episode_report": dict(report_snapshot or {}),
        "node_episode_manifest": dict(manifest_snapshot or {}),
    }
    for name, snapshot in state_files.items():
        state_mtime_ns = int(snapshot.get("mtime_ns") or 0)
        if (
            not snapshot.get("exists")
            or not snapshot.get("sha256")
            or not int(started_ns) <= state_mtime_ns <= captured_ns
        ):
            raise SidecarError(
                f"Fresh {name} snapshot is not inside this replay's capture window"
            )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        after = BASE.stable_file_snapshot(source)
        for field in ("bytes", "mtime_ns", "sha256"):
            if before.get(field) != after.get(field):
                raise SidecarError(f"Rendered clip changed during evidence copy ({field})")
        temporary_snapshot = BASE.stable_file_snapshot(temporary)
        if (
            temporary_snapshot.get("bytes") != after.get("bytes")
            or temporary_snapshot.get("sha256") != after.get("sha256")
        ):
            raise SidecarError("Lab evidence copy does not hash-match rendered clip")
        os.link(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    evidence = BASE.stable_file_snapshot(destination)
    if (
        not evidence.get("exists")
        or evidence.get("bytes") != before.get("bytes")
        or evidence.get("sha256") != before.get("sha256")
    ):
        raise SidecarError("Published lab clip evidence failed final verification")
    return {
        "capture_method": "byte-copy-to-temp, fsync, exclusive hard-link publish",
        "captured_at_ns": captured_ns,
        "freshness_window": {
            "replay_started_at_ns": int(started_ns),
            "source_mtime_ns": source_mtime_ns,
            "captured_at_ns": captured_ns,
            "within_window": True,
        },
        "manifest_path": str(source),
        "source_before": before,
        "source_after": after,
        "source_stable_during_copy": True,
        "fresh_state_files": state_files,
        "evidence": evidence,
    }


def _json_evidence(path: Path, root: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _within(path, root, label)
    snapshot = BASE.stable_file_snapshot(path)
    if not snapshot.get("exists"):
        raise SidecarError(f"Missing {label}: {path}")
    raw = path.read_bytes()
    if len(raw) != snapshot["bytes"] or BASE.sha256_bytes(raw) != snapshot["sha256"]:
        raise SidecarError(f"{label} changed after stable snapshot: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SidecarError(f"{label} is not UTF-8 JSON: {path}") from exc
    return payload, snapshot


def manager_offline(
    server_argv: Sequence[str], baseline_manager: dict[str, Any]
) -> dict[str, Any]:
    try:
        return MANAGER_GUARD.server_offline_evidence(server_argv, baseline_manager)
    except Exception as exc:
        raise SidecarError(f"Manager serving-argv offline proof failed: {exc}") from exc


def validate_baseline(path: Path, gpu_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, snapshot = _json_evidence(path, BASELINE_ROOT, "desktop baseline receipt")
    errors = BASELINE_SCHEMA.receipt_validation_errors(payload, gpu_index)
    if errors:
        raise SidecarError(
            "Desktop baseline receipt does not satisfy the conjunctive WDDM "
            "quiescence schema: " + "; ".join(errors)
        )
    return payload, snapshot


def validate_fixture(engine: str, frames: int) -> dict[str, Any]:
    bundle = BUNDLE_ROOT / f"{engine}_f{frames:03d}"
    contract, contract_snapshot = _json_evidence(
        bundle / "fixture_contract.json", BUNDLE_ROOT, "fixture contract"
    )
    ledger, ledger_snapshot = _json_evidence(
        bundle / "baked_ledger.json", BUNDLE_ROOT, "baked ledger"
    )
    manifest, manifest_snapshot = _json_evidence(
        bundle / "bundle_manifest.json", BUNDLE_ROOT, "bundle manifest"
    )
    master_value = str(manifest.get("baked_master") or "")
    master_path = _within(Path(master_value), bundle, "baked master")
    master = BASE.stable_file_snapshot(master_path)
    if (
        contract.get("engine") != engine
        or int(contract.get("model_render_frames") or 0) != frames
        or int(contract.get("delivered_frames") or 0) != frames - 1
        or contract.get("canvas") != [832, 480]
    ):
        raise SidecarError("Fixture contract identity drifted")
    shots = ((ledger.get("video") or {}).get("shots") or [])
    expected_segment = {
        "index": 0,
        "render_frames": frames,
        "drop_head": 0,
        "trim_tail": 1,
    }
    if len(shots) != 1 or shots[0].get("engine_id") != engine:
        raise SidecarError("Fixture must bind exactly one shot to the requested engine")
    plan = shots[0].get("coverage_plan") or {}
    if (
        int(shots[0].get("target_frame_count") or 0) != frames - 1
        or plan.get("target_visible_frames") != frames - 1
        or plan.get("join_mode") != "single"
        or plan.get("segments") != [expected_segment]
    ):
        raise SidecarError("Fixture does not render exact N and trim one only at assembly")
    if not manifest_snapshot.get("exists") or not master.get("exists"):
        raise SidecarError("Fixture manifest/master is missing")
    builder = contract.get("fixture_builder_source") or {}
    builder_path = Path(str(builder.get("path") or ""))
    if (
        _absolute(builder_path) != _absolute(SCRATCH / "build_wan_cost_ladder_fixtures.py")
        or BASE.sha256_file(builder_path) != builder.get("sha256")
    ):
        raise SidecarError("Fixture builder source no longer matches its contract pin")
    disk_inventory = contract.get("otr_disk_inventory") or {}
    assets = disk_inventory.get("assets") or {}
    if disk_inventory.get("status") != "AVAILABLE" or not assets:
        raise SidecarError("Fixture did not prove the production asset inventory available")
    for label, row in assets.items():
        path = Path(str(row.get("path") or ""))
        if not path.is_file():
            raise SidecarError(f"Pinned production asset is missing: {label} -> {path}")
        stat = path.stat()
        if (
            int(row.get("bytes") or -1) != int(stat.st_size)
            or int(row.get("mtime_ns") or -1) != int(stat.st_mtime_ns)
        ):
            raise SidecarError(f"Pinned production asset identity drifted: {label}")
    pins = contract.get("otr_source_sha256s") or {}
    expected_labels = {
        "_otr_soak_server_launch.cmd",
        "_otr_headless_model_paths.yaml",
        "otr_video_render_batch.py",
        "otr_visual_smoke.py",
        "otr_canonical.json",
        "render_driver.py",
        "coverage_plan.py",
        "motion_common.py",
        "wan_shared.py",
        "eng_wan_ti2v.py",
    }
    if engine == "fastwan_8gb":
        expected_labels.update({"eng_fastwan_8gb.py", "dmd_sampler.py"})
    if set(pins) != expected_labels:
        raise SidecarError("Fixture OTR source pin surface drifted")
    verified_pins = {}
    for label in sorted(expected_labels):
        path = OTR_PIN_PATHS[label]
        actual = BASE.sha256_file(path)
        if actual != pins[label]:
            raise SidecarError(
                f"Pinned OTR source changed after fixture build: {label} "
                f"expected={pins[label]} actual={actual}"
            )
        verified_pins[label] = {"path": str(path), "sha256": actual}
    return {
        "bundle": str(bundle),
        "contract": contract_snapshot,
        "ledger": ledger_snapshot,
        "manifest": manifest_snapshot,
        "master": master,
        "verified_otr_source_pins": verified_pins,
    }


def _same_server(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        int(left.get("serving_pid") or -1) == int(right.get("serving_pid") or -2)
        and float(left.get("process_create_time") or -1)
        == float(right.get("process_create_time") or -2)
        and left.get("argv") == right.get("argv")
        and int(left.get("parent_pid") or -1) == int(right.get("parent_pid") or -2)
    )


def validate_manager_boot_guard(
    path: Path,
    *,
    attempt_id: str,
    attempt_evidence_root: Path,
    server: dict[str, Any],
    server_log: Path,
    baseline_manager: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = attempt_evidence_root / "manager_boot_guard.json"
    if path.resolve() != expected.resolve():
        raise SidecarError(f"Attempt {attempt_id} must use Manager guard {expected}")
    payload, snapshot = MANAGER_GUARD.stable_json(path)
    if (
        payload.get("kind") != "wan-cost-ladder-manager-offline-boot-guard"
        or payload.get("status") != "pass"
        or payload.get("campaign_attempt_id") != attempt_id
        or not _same_server(payload.get("server_instance") or {}, server)
    ):
        raise SidecarError("Manager boot guard identity/status contract is invalid")
    guarded_server = payload.get("server_instance") or {}
    expected_launcher_argv = [
        os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
        "/d",
        "/c",
        str(OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"),
        str(attempt_evidence_root / "wan_cost_ladder.server.log"),
        "WAN",
    ]
    chain_errors = OWNERSHIP.validate_chain_receipt(
        guarded_server.get("ownership_chain") or {},
        guarded_server,
        expected_launcher_argv,
    )
    if chain_errors:
        raise SidecarError(
            "Manager boot guard owned-process chain failed: "
            + "; ".join(chain_errors)
        )
    boot_environment = payload.get("boot_environment") or {}
    boot_credential_errors = (
        MANAGER_GUARD.validate_offline_credential_environment_evidence(
            boot_environment.get("offline_credentials") or {}
        )
    )
    if boot_credential_errors:
        raise SidecarError(
            "Manager boot guard production credential contract failed: "
            + "; ".join(boot_credential_errors)
        )
    expected_boot_set = {
        "OTR_HEADLESS_PORT": "8000",
        "COMFYUI_URL": REQUIRED_COMFYUI_URL,
        "PYTHONDONTWRITEBYTECODE": "1",
        **MANAGER_GUARD.OFFLINE_CREDENTIAL_ENVIRONMENT,
    }
    if boot_environment.get("set") != expected_boot_set:
        raise SidecarError("Manager boot guard exact production environment pins drifted")
    source = payload.get("source") or {}
    guard_source = (SCRATCH / "manager_offline_guard.py").resolve()
    if (
        Path(str(source.get("path") or "")).resolve() != guard_source
        or source.get("sha256") != BASE.sha256_file(guard_source)
    ):
        raise SidecarError("Manager boot guard source hash drifted")
    for label in ("preboot", "post_identification"):
        errors = MANAGER_GUARD.validate_offline_evidence(
            payload.get(label) or {}, require_current_hash=True
        )
        if errors:
            raise SidecarError(f"Manager boot guard {label} proof failed: {errors}")
    baseline_sha = (baseline_manager.get("config") or {}).get("sha256")
    if any(
        ((payload.get(label) or {}).get("config") or {}).get("sha256")
        != baseline_sha
        for label in ("preboot", "post_identification")
    ):
        raise SidecarError("Manager boot guard crossed the baseline config SHA")
    scan = payload.get("boot_log_scan") or {}
    if payload.get("authoritative_server_reported_mode") != scan.get(
        "authoritative_server_reported_mode"
    ):
        raise SidecarError(
            "Manager guard authoritative server-reported mode field drifted"
        )
    errors = MANAGER_GUARD.validate_log_prefix_binding(scan, server_log)
    if errors:
        raise SidecarError("Manager boot log prefix proof failed: " + "; ".join(errors))
    return payload, snapshot


def inter_run_log_gap(
    previous_ending: dict[str, Any], current_start: dict[str, Any], server_log: Path
) -> dict[str, Any]:
    """Prove an append-only gap carries no intervening prompt execution."""
    if not previous_ending.get("exists") or not current_start.get("exists"):
        raise SidecarError("Warm-pair server log is absent")
    for field in ("device", "inode"):
        if previous_ending.get(field) != current_start.get(field):
            raise SidecarError("Warm-pair server log identity changed")
    old_size = int(previous_ending.get("bytes") or 0)
    new_size = int(current_start.get("bytes") or 0)
    if new_size < old_size:
        raise SidecarError("Warm-pair server log was truncated")
    with server_log.open("rb") as handle:
        prefix = handle.read(old_size)
        gap = handle.read(new_size - old_size)
    if BASE.sha256_bytes(prefix) != previous_ending.get("sha256"):
        raise SidecarError("Warm-pair server log prefix changed after run1")
    text = gap.decode("utf-8", errors="replace")
    execution_markers = (
        "got prompt",
        "Prompt executed in",
        "[OTR video]",
        "OTR_VideoRenderBatch",
        "execution_start",
    )
    found = [marker for marker in execution_markers if marker in text]
    if found:
        raise SidecarError(
            f"Warm run is not consecutive; inter-run log contains execution marker(s) {found}"
        )
    return {
        "previous_end_offset": old_size,
        "current_start_offset": new_size,
        "byte_count": len(gap),
        "sha256": BASE.sha256_bytes(gap),
        "text": text,
        "execution_markers_checked": list(execution_markers),
        "execution_markers_found": found,
        "prefix_sha256_reverified": True,
    }


def validate_previous(
    path: Path,
    *,
    engine: str,
    frames: int,
    fixture: dict[str, Any],
    baseline_snapshot: dict[str, Any],
    server: dict[str, Any],
    attempt_id: str,
    manager_guard_snapshot: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.resolve().parent != (TELEMETRY_ROOT / attempt_id).resolve():
        raise SidecarError("Previous pair receipt crossed the campaign attempt namespace")
    previous, snapshot = _json_evidence(path, TELEMETRY_ROOT, "previous pair receipt")
    if (
        previous.get("kind") != "wan-cost-ladder-raw-telemetry"
        or previous.get("status") != "measured"
        or previous.get("engine") != engine
        or int(previous.get("model_render_frames") or 0) != frames
        or previous.get("run_role") != "pair_first"
        or previous.get("campaign_attempt_id") != attempt_id
        or previous.get("label") != canonical_label(engine, frames, "pair_first")
    ):
        raise SidecarError("Previous receipt is not the matching measured pair_first run")
    if not _same_server(previous.get("server_instance") or {}, server):
        raise SidecarError("Warm pair crossed OTR server PID/create-time/argv identity")
    if previous.get("fixture") != fixture:
        raise SidecarError("Warm pair fixture hashes drifted")
    if (
        (previous.get("quiescent_desktop_baseline") or {}).get("receipt", {}).get("sha256")
        != baseline_snapshot.get("sha256")
    ):
        raise SidecarError("Warm pair cites a different quiescent baseline receipt")
    if not (previous.get("gpu_lease") or {}).get("release", {}).get("success"):
        raise SidecarError("Previous pair receipt did not prove GPU lease release")
    if (
        ((previous.get("manager_offline_guard") or {}).get("boot_guard_receipt") or {}).get(
            "sha256"
        )
        != manager_guard_snapshot.get("sha256")
    ):
        raise SidecarError("Warm pair crossed the Manager boot guard receipt")
    return previous, snapshot


def _stream(pipe: Any, events: list[dict[str, Any]], errors: list[str]) -> None:
    BASE._stream_child_stdout(pipe, events, errors)


def _parse_replay_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    matches = []
    for event in events:
        text = str(event.get("text") or "")
        if text.startswith(RESULT_PREFIX):
            try:
                matches.append(json.loads(text[len(RESULT_PREFIX) :]))
            except json.JSONDecodeError as exc:
                raise SidecarError(f"Malformed replay result marker: {exc}") from exc
    if len(matches) != 1:
        raise SidecarError(f"Expected one replay result marker, found {len(matches)}")
    return matches[0]


def _validate_episode_payload(
    manifest: dict[str, Any], report: dict[str, Any], engine: str, frames: int
) -> list[str]:
    errors = []
    if report.get("ok") is not True or report.get("mode") != "episode":
        errors.append("node episode report does not prove ok episode mode")
    if report.get("engine_histogram") != {engine: 1}:
        errors.append("node episode report engine histogram drifted")
    trace = report.get("trace") or []
    if (
        len(trace) != 1
        or trace[0].get("shot_id") != "shot_b001"
        or int(trace[0].get("video_seed") or -1) != EFFECTIVE_VIDEO_SEED
        or trace[0].get("final_engine") != engine
    ):
        errors.append("node episode trace does not prove the fixed effective seed/engine")
    if manifest.get("canvas") != {"w": 832, "h": 480}:
        errors.append("node episode manifest canvas is not 832x480")
    clips = manifest.get("clips") or []
    if len(clips) != 1:
        errors.append("node episode manifest does not contain exactly one clip")
        return errors
    clip = clips[0]
    if clip.get("engine_id") != engine:
        errors.append("manifest clip engine drifted")
    if clip.get("recipe") != RECIPE_IDS[engine]:
        errors.append("manifest recipe receipt is not the frozen production recipe")
    if clip.get("quant") != "Q5_K_M":
        errors.append("manifest quant receipt is not Q5_K_M")
    if clip.get("use_lora") is not (engine == "fastwan_8gb"):
        errors.append("manifest LoRA identity does not match the requested engine")
    if clip.get("render_canvas") != "832x480":
        errors.append("manifest render_canvas receipt is not 832x480")
    try:
        adapter_peak_mib = float(clip.get("vram_peak_mb"))
    except (TypeError, ValueError):
        errors.append("manifest lacks the adapter's numeric render-window VRAM peak")
    else:
        if not adapter_peak_mib > 0:
            errors.append("manifest adapter render-window VRAM peak is not positive")
    if int(clip.get("frame_count") or 0) != frames - 1:
        errors.append("manifest delivered frame count is not N-1")
    if int(clip.get("target_frame_count") or 0) != frames - 1:
        errors.append("manifest target frame count is not N-1")
    segments = clip.get("segments") or []
    expected = {
        "segment_index": 0,
        "render_frames": frames,
        "drop_head": 0,
        "trim_tail": 1,
    }
    if len(segments) != 1 or any(segments[0].get(k) != v for k, v in expected.items()):
        errors.append("manifest segment receipt does not prove exact N-frame render + tail trim")
    if int(segments[0].get("native_frame_count") or 0) != frames:
        errors.append("manifest native frame count does not equal requested model frames")
    return errors


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--engine", required=True, choices=tuple(LADDERS))
    parser.add_argument("--frames", required=True, type=int)
    parser.add_argument(
        "--run-role", required=True, choices=("pair_first", "warm_second")
    )
    parser.add_argument("--previous-receipt", default="")
    parser.add_argument("--desktop-baseline-receipt", required=True)
    parser.add_argument("--boot-lane", required=True)
    parser.add_argument("--server-port", type=int, default=8000)
    parser.add_argument("--expected-server-model-paths", required=True)
    parser.add_argument("--expected-server-output", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--manager-boot-guard", required=True)
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--interval-s", type=float, default=DEFAULT_INTERVAL_S)
    parser.add_argument("--max-sample-gap-s", type=float, default=DEFAULT_MAX_GAP_S)
    parser.add_argument("--timeout", type=int, default=2400)
    return parser.parse_args(argv)


def run(
    argv: Sequence[str] | None = None,
    *,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    sample_query: Callable[[int], dict[str, Any]] = BASE.query_machine_sample,
) -> tuple[int, dict[str, Any]]:
    args = parse_args(argv)
    if args.frames not in LADDERS[args.engine]:
        raise SidecarError(f"Frame {args.frames} is not in the {args.engine} ladder")
    if args.server_port != 8000:
        raise SidecarError("Production-wrapper ladder is pinned to OTR port 8000")
    if args.interval_s != 0.2:
        raise SidecarError("Mission requires exactly 200 ms sampling")
    if args.timeout < 60:
        raise SidecarError("Timeout must be at least 60 seconds")
    label = canonical_label(args.engine, args.frames, args.run_role)
    requested_output = Path(args.output)
    if not requested_output.is_absolute():
        raise SidecarError("Telemetry output must be absolute")
    output = _within(requested_output, TELEMETRY_ROOT, "telemetry output")
    if output.suffix.lower() != ".json":
        raise SidecarError("Telemetry output must be an absolute JSON path")
    if output.stem != label:
        raise SidecarError(f"Telemetry filename must be {label}.json")
    try:
        telemetry_relative = output.resolve().relative_to(TELEMETRY_ROOT.resolve())
    except ValueError as exc:  # already guarded by _within; retain fail-closed context
        raise SidecarError("Telemetry output is outside the ladder root") from exc
    if len(telemetry_relative.parts) != 2:
        raise SidecarError(
            "Telemetry output must use telemetry/attempt-NNN/<label>.json"
        )
    attempt_id = telemetry_relative.parts[0]
    if ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is None:
        raise SidecarError(f"Invalid append-only campaign attempt id: {attempt_id!r}")
    attempt_evidence_root = EVIDENCE_ROOT / attempt_id
    attempt_clip_root = attempt_evidence_root / "clips"
    if output.exists():
        raise FileExistsError(f"Telemetry evidence already exists: {output}")
    evidence_clip_path = attempt_clip_root / f"{label}.mp4"
    if evidence_clip_path.exists():
        raise FileExistsError(f"Lab clip evidence already exists: {evidence_clip_path}")
    if args.run_role == "pair_first" and args.previous_receipt:
        raise SidecarError("pair_first must not cite a previous receipt")
    if args.run_role == "warm_second" and not args.previous_receipt:
        raise SidecarError("warm_second requires --previous-receipt")

    fixture = validate_fixture(args.engine, args.frames)
    baseline_path = Path(args.desktop_baseline_receipt)
    expected_baseline_path = BASELINE_ROOT / "baselines" / f"{attempt_id}.json"
    if baseline_path.resolve() != expected_baseline_path.resolve():
        raise SidecarError(
            f"Attempt {attempt_id} must use baseline {expected_baseline_path}"
        )
    baseline, baseline_snapshot = validate_baseline(baseline_path, args.gpu_index)
    baseline_manager = baseline.get("manager_config") or {}
    offline: dict[str, Any] = {}
    model_paths = Path(args.expected_server_model_paths)
    server_output = Path(args.expected_server_output)
    server_log = Path(args.server_log)
    if not server_log.is_absolute():
        raise SidecarError(f"Server log must be absolute: {server_log}")
    server_log = _within(server_log, attempt_evidence_root, "lab-owned server log")
    expected_server_log = attempt_evidence_root / "wan_cost_ladder.server.log"
    if server_log.resolve() != expected_server_log.resolve():
        raise SidecarError(
            f"Attempt {attempt_id} must use server log {expected_server_log}"
        )
    manager_guard_path = Path(args.manager_boot_guard)
    if not manager_guard_path.is_absolute():
        raise SidecarError("Manager boot guard path must be absolute")
    for path, name, directory in (
        (model_paths, "model-paths config", False),
        (server_output, "server output", True),
        (server_log, "server log", False),
        (manager_guard_path, "Manager boot guard", False),
    ):
        if not path.is_absolute() or not (path.is_dir() if directory else path.is_file()):
            raise SidecarError(f"Missing absolute {name}: {path}")

    buster = canonical_cache_buster(args.engine, args.frames, args.run_role)
    command = [
        str(Path(sys.executable).resolve()),
        "-u",
        str(REPLAY.resolve()),
        "--bundle",
        fixture["bundle"],
        "--cache-buster",
        str(buster),
        "--timeout",
        str(args.timeout),
    ]
    replay_environment, replay_environment_evidence = pinned_replay_environment()
    lease = GpuLease(
        LAB_ROOT / ".gpu.lock", LAB_ROOT / ".suite.lock", LAB_ROOT / ".coordinator.mutex"
    )
    process: Any | None = None
    sampler: Any | None = None
    stdout_thread: threading.Thread | None = None
    stdout_events: list[dict[str, Any]] = []
    stdout_errors: list[str] = []
    errors: list[str] = []
    samples: list[dict[str, Any]] = []
    server: dict[str, Any] = {}
    previous: dict[str, Any] | None = None
    previous_snapshot: dict[str, Any] | None = None
    lease_owner: dict[str, Any] | None = None
    lease_release = {"success": False, "error": "not attempted"}
    returncode: int | None = None
    log_summary: dict[str, Any] = {}
    report_before: dict[str, Any] = {}
    manifest_before: dict[str, Any] = {}
    report_after: dict[str, Any] = {}
    manifest_after: dict[str, Any] = {}
    report_payload: dict[str, Any] = {}
    manifest_payload: dict[str, Any] = {}
    rendered_clip: dict[str, Any] = {}
    replay_result: dict[str, Any] = {}
    replay_endpoint: dict[str, Any] = {}
    inter_run_gap: dict[str, Any] | None = None
    child_started = False
    started_ns = time.time_ns()
    started_mono_ns = time.monotonic_ns()
    finished_ns = started_ns
    finished_mono_ns = started_mono_ns
    log_tail: Any | None = None
    state = server_output / "otr" / "episodes" / "_shared" / "state"
    report_path = state / "node_episode_report.json"
    manifest_path = state / "node_episode_manifest.json"
    immediate_baseline: dict[str, Any] = {}
    manager_boot_guard: dict[str, Any] = {}
    manager_boot_guard_snapshot: dict[str, Any] = {}
    manager_pre_render: dict[str, Any] = {}
    manager_pre_render_log_scan: dict[str, Any] = {}
    manager_post_render: dict[str, Any] = {}
    manager_post_render_log_scan: dict[str, Any] = {}
    try:
        lease.acquire()
        lease_owner = dict(lease.owner or {})
        server = OTR_SIDE.identify_expected_otr_server(
            args.server_port, model_paths, server_output
        )
        server_argv = list(server.get("argv") or [])
        for required_flag in ("--cuda-malloc", "--disable-metadata"):
            if required_flag not in server_argv:
                raise SidecarError(
                    f"OTR WAN production server argv lacks required {required_flag}"
                )
        forbidden_flags = {
            "--reserve-vram",
            "--lowvram",
            "--novram",
            "--highvram",
            "--disable-pinned-memory",
            "--use-sage-attention",
            "--use-flash-attention",
        }
        present_forbidden = sorted(
            token
            for token in server_argv
            if any(
                token == flag or token.startswith(flag + "=")
                for flag in forbidden_flags
            )
        )
        if present_forbidden:
            raise SidecarError(
                f"Cost ladder requires the unclamped default WAN boot; found {present_forbidden}"
            )
        offline = manager_offline(server_argv, baseline_manager)
        manager_boot_guard, manager_boot_guard_snapshot = validate_manager_boot_guard(
            manager_guard_path,
            attempt_id=attempt_id,
            attempt_evidence_root=attempt_evidence_root,
            server=server,
            server_log=server_log,
            baseline_manager=baseline_manager,
        )
        manager_pre_render = manager_offline(server_argv, baseline_manager)
        manager_pre_render_log_scan = MANAGER_GUARD.scan_boot_log_prefix(
            server_log,
            Path(manager_pre_render["config"]["path"]),
            expected_url=REQUIRED_COMFYUI_URL,
            require_pre_prompt=False,
        )
        manager_pre_errors = MANAGER_GUARD.validate_runtime_log_binding(
            manager_pre_render_log_scan, server_log
        )
        if manager_pre_errors:
            raise SidecarError(
                "Manager pre-render persistent offline audit failed: "
                + "; ".join(manager_pre_errors)
            )
        baseline_samples = baseline.get("samples") or []
        baseline_finished_s = max(
            int(row.get("sampled_at_ns") or 0) for row in baseline_samples
        ) / 1_000_000_000.0
        if baseline_finished_s >= float(server.get("process_create_time") or 0):
            raise SidecarError(
                "Quiescent desktop baseline was not captured before this server boot"
            )
        if (baseline_manager.get("config") or {}).get("sha256") != (
            offline.get("config") or {}
        ).get("sha256"):
            raise SidecarError("Manager offline config changed after baseline capture")
        if args.run_role == "warm_second":
            previous, previous_snapshot = validate_previous(
                Path(args.previous_receipt),
                engine=args.engine,
                frames=args.frames,
                fixture=fixture,
                baseline_snapshot=baseline_snapshot,
                server=server,
                attempt_id=attempt_id,
                manager_guard_snapshot=manager_boot_guard_snapshot,
            )
        immediate_baseline = sample_query(args.gpu_index)
        report_before = BASE.stable_file_snapshot(report_path)
        manifest_before = BASE.stable_file_snapshot(manifest_path)
        log_start = BASE.stable_file_snapshot(server_log)
        if previous is not None:
            prior_end = ((previous.get("server_log") or {}).get("ending") or {})
            inter_run_gap = inter_run_log_gap(prior_end, log_start, server_log)
        log_tail = BASE.AppendOnlyLogTail(server_log, log_start)
        started_ns = time.time_ns()
        started_mono_ns = time.monotonic_ns()
        process = popen_factory(
            command,
            cwd=str(LAB_ROOT),
            env=replay_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        child_started = True
        if process.stdout is None:
            raise SidecarError("Replay child did not expose stdout")
        stdout_thread = threading.Thread(
            target=_stream,
            args=(process.stdout, stdout_events, stdout_errors),
            daemon=True,
        )
        stdout_thread.start()
        sampler = BASE.ObservationSampler(
            args.gpu_index, args.interval_s, log_tail, sample_query=sample_query
        )
        sampler.start()
        returncode = int(process.wait())
        finished_ns = time.time_ns()
        finished_mono_ns = time.monotonic_ns()
    except BaseException as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        if process is not None and getattr(process, "poll", lambda: 0)() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception as terminate_exc:
                errors.append(f"child termination failed: {terminate_exc}")
        finished_ns = time.time_ns()
        finished_mono_ns = time.monotonic_ns()
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except Exception as exc:
                errors.append(f"sampler stop failed: {exc}")
            samples = list(sampler.samples)
            errors.extend(sampler.errors)
        if stdout_thread is not None:
            stdout_thread.join(timeout=10)
            if stdout_thread.is_alive():
                errors.append("stdout reader did not stop")
        if log_tail is not None:
            log_summary = log_tail.finish()
            errors.extend(log_summary.get("errors") or [])
        try:
            if server:
                manager_post_render = manager_offline(
                    list(server.get("argv") or []), baseline_manager
                )
                manager_post_render_log_scan = MANAGER_GUARD.scan_boot_log_prefix(
                    server_log,
                    Path(manager_post_render["config"]["path"]),
                    expected_url=REQUIRED_COMFYUI_URL,
                    require_pre_prompt=False,
                )
                manager_post_errors = MANAGER_GUARD.validate_runtime_log_binding(
                    manager_post_render_log_scan, server_log
                )
                errors.extend(
                    "Manager post-render persistent audit: " + error
                    for error in manager_post_errors
                )
        except Exception as exc:
            errors.append(f"Manager post-render persistent audit failed: {exc}")
        report_after = BASE.stable_file_snapshot(report_path)
        manifest_after = BASE.stable_file_snapshot(manifest_path)
        # Capture the mutable OTR state payloads while the lab GPU lease is
        # still ours. Releasing first would let the next leg overwrite these
        # files between the stable snapshot and the read.
        try:
            report_raw = report_path.read_bytes()
            manifest_raw = manifest_path.read_bytes()
            if (
                len(report_raw) != int(report_after.get("bytes") or -1)
                or BASE.sha256_bytes(report_raw) != report_after.get("sha256")
            ):
                raise SidecarError("node episode report changed while being captured")
            if (
                len(manifest_raw) != int(manifest_after.get("bytes") or -1)
                or BASE.sha256_bytes(manifest_raw) != manifest_after.get("sha256")
            ):
                raise SidecarError("node episode manifest changed while being captured")
            report_payload = json.loads(report_raw.decode("utf-8"))
            manifest_payload = json.loads(manifest_raw.decode("utf-8"))
            rendered_clip = capture_rendered_clip(
                manifest_payload,
                label=label,
                started_ns=started_ns,
                server_output=server_output,
                evidence_clip_root=attempt_clip_root,
                report_snapshot=report_after,
                manifest_snapshot=manifest_after,
            )
        except Exception as exc:
            errors.append(f"episode payload/media capture failed: {exc}")
        try:
            lease.release()
            lease_release = {"success": True, "error": ""}
        except (LeaseError, Exception) as exc:
            errors.append(f"GPU lease release failed: {exc}")
            lease_release = {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    if not child_started:
        raise SidecarError(
            "Pre-execution measurement validation failed; no receipt was published: "
            + "; ".join(errors)
        )
    errors.extend(stdout_errors)
    try:
        sample_summary = BASE.summarize_samples(
            samples,
            baseline=immediate_baseline,
            child_start_mono_ns=started_mono_ns,
            child_end_mono_ns=finished_mono_ns,
            interval_s=args.interval_s,
            max_gap_s=args.max_sample_gap_s,
            sample_errors=[],
        )
        errors.extend(sample_summary.get("coverage_errors") or [])
    except Exception as exc:
        sample_summary = {"samples": samples, "coverage_errors": [str(exc)]}
        errors.append(f"sample summary failed: {exc}")
    try:
        replay_result = _parse_replay_result(stdout_events)
    except Exception as exc:
        errors.append(str(exc))
    if returncode != 0 or replay_result.get("success") is not True:
        errors.append("Cache-bust production replay did not prove success")
    if (
        replay_result.get("engine") != args.engine
        or int(replay_result.get("model_render_frames") or 0) != args.frames
        or int(replay_result.get("cache_buster") or 0) != buster
    ):
        errors.append("Replay result identity does not match the requested cell")
    replay_endpoint, endpoint_errors = validate_replay_endpoint_binding(
        server, replay_environment_evidence, replay_result
    )
    errors.extend(endpoint_errors)
    for label_name, before, after in (
        ("node_episode_report", report_before, report_after),
        ("node_episode_manifest", manifest_before, manifest_after),
    ):
        if (
            not after.get("exists")
            or int(after.get("mtime_ns") or 0) < int(started_ns)
            or (
                after.get("mtime_ns") == before.get("mtime_ns")
                and after.get("sha256") == before.get("sha256")
            )
        ):
            errors.append(f"{label_name} did not advance during the run")
    if report_payload and manifest_payload:
        try:
            errors.extend(
                _validate_episode_payload(
                    manifest_payload, report_payload, args.engine, args.frames
                )
            )
        except Exception as exc:
            errors.append(f"episode payload validation failed: {exc}")
    else:
        errors.append("episode payloads were not captured under the GPU lease")

    appended_text = "\n".join(
        str(event.get("text") or "") for event in (log_summary.get("events") or [])
    )
    assembled_marker = (
        f"BEAT shot_b001 assembled from 1 single segment(s) -> {args.frames - 1} frame(s)"
    )
    if assembled_marker not in appended_text:
        errors.append("Server log lacks exact one-segment assembly proof")
    if args.engine == "fastwan_8gb" and "[OTR_DMDRestart]" not in appended_text:
        errors.append("FastWan run lacks OTR DMD-restart execution marker")

    sidecar_peak_mib = sample_summary.get("peak_vram_mib")
    adapter_peak_mib: float | None = None
    try:
        clips = manifest_payload.get("clips") or []
        if len(clips) == 1:
            adapter_peak_mib = float(clips[0].get("vram_peak_mb"))
    except (TypeError, ValueError):
        adapter_peak_mib = None
    peak_candidates = [
        float(value)
        for value in (sidecar_peak_mib, adapter_peak_mib)
        if isinstance(value, (int, float)) and float(value) > 0
    ]
    conservative_peak_mib = max(peak_candidates) if len(peak_candidates) == 2 else None
    if conservative_peak_mib is None:
        errors.append(
            "Both 200 ms sidecar and 100 ms adapter render-window peaks are required"
        )
    elif float(adapter_peak_mib) >= float(sidecar_peak_mib):
        conservative_peak_source = "adapter_render_window_100ms"
    else:
        conservative_peak_source = "sidecar_machine_wide_200ms"
    desktop_mib = float(baseline["vram_used_mib"])
    demand_mib = (
        conservative_peak_mib - desktop_mib
        if conservative_peak_mib is not None
        else None
    )
    if demand_mib is not None and demand_mib < 0:
        errors.append("Warm peak is below the quiescent desktop baseline")
    receipt = {
        "sidecar_schema_version": 1,
        "kind": "wan-cost-ladder-raw-telemetry",
        "measured": "otr-side production wrapper",
        "status": "measured" if not errors else "invalid",
        "errors": errors,
        "label": label,
        "campaign_attempt_id": attempt_id,
        "engine": args.engine,
        "model_render_frames": args.frames,
        "delivered_frames": args.frames - 1,
        "run_role": args.run_role,
        "warm": args.run_role == "warm_second",
        "boot_lane": args.boot_lane,
        "cache_buster": buster,
        "command": {
            "argv": command,
            "python_sha256": BASE.sha256_file(Path(command[0])),
            "replay_shim_sha256": BASE.sha256_file(REPLAY),
            "returncode": returncode,
            "environment": replay_environment_evidence,
        },
        "replay_endpoint": replay_endpoint,
        "fixture": fixture,
        "manager_config": offline,
        "manager_offline_guard": {
            "boot_guard_receipt": manager_boot_guard_snapshot,
            "boot_guard_payload": manager_boot_guard,
            "pre_render_config": manager_pre_render,
            "pre_render_full_log_scan": manager_pre_render_log_scan,
            "post_render_config": manager_post_render,
            "post_render_full_log_scan": manager_post_render_log_scan,
        },
        "quiescent_desktop_baseline": {
            "receipt": baseline_snapshot,
            "vram_used_mib": desktop_mib,
            "unit_contract": "additional engine demand above quiescent desktop baseline",
        },
        "immediate_pre_render_baseline": immediate_baseline,
        "sidecar_peak_vram_mib": sidecar_peak_mib,
        "adapter_render_peak_vram_mib": adapter_peak_mib,
        "warm_peak_vram_mib": conservative_peak_mib,
        "warm_peak_derivation": {
            "operation": "max",
            "inputs": [
                "sidecar_peak_vram_mib",
                "adapter_render_peak_vram_mib",
            ],
            "selected_source": conservative_peak_source
            if conservative_peak_mib is not None
            else None,
            "rationale": (
                "Conservative machine-wide peak: retain the mandated 200 ms "
                "sidecar and OTR's independent 100 ms render-window probe; do "
                "not let either instrument's cadence underprice the row."
            ),
        },
        "cost_row_demand_mib": demand_mib,
        "started_at_ns": started_ns,
        "started_at_utc": BASE.utc_timestamp(started_ns),
        "finished_at_ns": finished_ns,
        "finished_at_utc": BASE.utc_timestamp(finished_ns),
        "duration_s": round((finished_mono_ns - started_mono_ns) / 1e9, 9),
        "server_instance": server,
        "gpu_lease": {"owner": lease_owner, "release": lease_release},
        "previous_pair_receipt": previous_snapshot,
        "inter_run_log_gap": inter_run_gap,
        "sampler": sample_summary,
        "child_stdout": {
            "timestamps_are_observation_times": True,
            "events": stdout_events,
            "errors": stdout_errors,
        },
        "replay_result": replay_result,
        "server_log": log_summary,
        "node_episode_report_before": report_before,
        "node_episode_report_after": report_after,
        "node_episode_report_payload": report_payload,
        "node_episode_manifest_before": manifest_before,
        "node_episode_manifest_after": manifest_after,
        "node_episode_manifest_payload": manifest_payload,
        "rendered_clip": rendered_clip,
        "source": {
            "path": str(Path(__file__).resolve()),
            "sha256": BASE.sha256_file(Path(__file__).resolve()),
        },
    }
    BASE.atomic_create_json(output, receipt)
    return (0 if receipt["status"] == "measured" else 1), receipt


def main(argv: Sequence[str] | None = None) -> int:
    try:
        code, receipt = run(argv)
    except Exception as exc:
        print(f"[wan-cost-sidecar] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "[wan-cost-sidecar] %s %s peak_mib=%s demand_mib=%s samples=%s"
        % (
            receipt["status"].upper(),
            receipt["label"],
            receipt.get("warm_peak_vram_mib"),
            receipt.get("cost_row_demand_mib"),
            (receipt.get("sampler") or {}).get("sample_count"),
        ),
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
