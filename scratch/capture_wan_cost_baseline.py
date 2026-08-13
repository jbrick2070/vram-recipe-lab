#!/usr/bin/env python
"""Capture a fail-closed Windows/WDDM desktop VRAM baseline.

Windows WDDM reports ordinary desktop graphics clients through
``--query-compute-apps`` with ``used_gpu_memory=[N/A]``.  Treating every one
of those rows as an active CUDA workload makes a clean desktop impossible to
measure; treating the token alone as proof of idleness would be unsafe.  This
collector therefore requires *conjunctive* evidence on the selected GPU:

* the exact GPU index and UUID stay fixed;
* five 200 ms samples stay below the VRAM and utilization ceilings;
* every NVIDIA process row is the recognized unmetered WDDM form and has a
  live desktop-graphics process identity with no model-workload marker;
* port 8000 has no listener before, during, or after sampling; and
* the same nonce-bound lab GPU lease is held for every sample.

Numeric memory rows, unknown tokens or identities, suspicious command lines,
UUID drift, high activity, and any listener all fail closed.  This script
never terminates, adopts, or otherwise changes a process.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import psutil


LAB_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = LAB_ROOT / "scratch"
OUTPUT_ROOT = LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder"
OTR_LAUNCHER = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
    r"\scripts\_otr_soak_server_launch.cmd"
)
SAMPLE_COUNT = 5
SAMPLE_INTERVAL_S = 0.2
MAX_QUIESCENT_VRAM_MIB = 2048.0
MAX_GPU_UTILIZATION_PERCENT = 15.0
MAX_MEMORY_UTILIZATION_PERCENT = 10.0
WDDM_UNMETERED_MEMORY_TOKEN = "[N/A]"
REQUIRED_DRIVER_MODEL = "WDDM"
REQUIRED_DISPLAY_ACTIVE = "Enabled"

# These markers identify model/inference launch surfaces, not ordinary UI
# names.  Their presence always blocks the baseline even when WDDM withholds
# a per-process memory number and global activity happens to be momentarily low.
MODEL_WORKLOAD_MARKERS = (
    "main.py",
    "run_recipe.py",
    "torchrun",
    "stable-diffusion",
    "automatic1111",
    "invokeai",
    "diffusers",
    "text-generation",
    "vllm",
    "ollama",
    "kobold",
    "eng_wan_",
    "eng_fastwan_",
    "eng_humo",
    "minimax",
)


class BaselineError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BaselineError(f"Cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load("wan_cost_baseline_shared", SCRATCH / "humo_diet_sidecar.py")
MANAGER_GUARD = _load(
    "wan_cost_baseline_manager_guard", SCRATCH / "manager_offline_guard.py"
)
sys.path.insert(0, str(LAB_ROOT))
from lab_locks import GpuLease, read_lock_receipt  # noqa: E402


def manager_offline() -> dict[str, Any]:
    try:
        return MANAGER_GUARD.launcher_offline_evidence(OTR_LAUNCHER)
    except Exception as exc:
        raise BaselineError(f"Manager preboot offline proof failed: {exc}") from exc


def listener_pids(port: int) -> list[int]:
    pids = set()
    for row in psutil.net_connections(kind="tcp"):
        if row.status != psutil.CONN_LISTEN or not row.laddr:
            continue
        if int(row.laddr.port) == int(port) and row.pid:
            pids.add(int(row.pid))
    return sorted(pids)


def _run_nvidia_smi(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaselineError(f"nvidia-smi query failed: {exc}") from exc


def _csv_rows(stdout: str) -> list[list[str]]:
    return [
        [field.strip() for field in row]
        for row in csv.reader(io.StringIO(stdout))
        if row and any(field.strip() for field in row)
    ]


def _finite_nonnegative(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise BaselineError(f"Non-numeric {label}: {value!r}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise BaselineError(f"Invalid {label}: {value!r}")
    return parsed


def target_gpu_identity(gpu_index: int) -> dict[str, Any]:
    argv = [
        "nvidia-smi",
        "-i",
        str(gpu_index),
        "--query-gpu=index,uuid,name,memory.total,driver_model.current,display_active",
        "--format=csv,noheader,nounits",
    ]
    result = _run_nvidia_smi(argv)
    rows = _csv_rows(result.stdout)
    if len(rows) != 1 or len(rows[0]) != 6:
        raise BaselineError(f"Unexpected target-GPU identity rows: {rows!r}")
    index, uuid, name, total, driver_model, display_active = rows[0]
    if int(index) != int(gpu_index) or not uuid.startswith("GPU-"):
        raise BaselineError(f"Target GPU identity mismatch: {rows[0]!r}")
    if driver_model != REQUIRED_DRIVER_MODEL or display_active != REQUIRED_DISPLAY_ACTIVE:
        raise BaselineError(
            "Unmetered desktop-client policy requires active WDDM display mode; "
            f"found driver_model={driver_model!r}, display_active={display_active!r}"
        )
    return {
        "gpu_index": int(index),
        "gpu_uuid": uuid,
        "gpu_name": name,
        "vram_total_mib": _finite_nonnegative(total, "GPU total memory"),
        "driver_model_current": driver_model,
        "display_active": display_active,
        "query_argv": argv,
        "raw_stdout_sha256": BASE.sha256_bytes(result.stdout.encode("utf-8")),
    }


def query_gpu_activity(gpu_index: int, expected_uuid: str) -> dict[str, Any]:
    argv = [
        "nvidia-smi",
        "-i",
        str(gpu_index),
        "--query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu,utilization.memory,pstate,driver_model.current,display_active",
        "--format=csv,noheader,nounits",
    ]
    result = _run_nvidia_smi(argv)
    rows = _csv_rows(result.stdout)
    if len(rows) != 1 or len(rows[0]) != 10:
        raise BaselineError(f"Unexpected target-GPU activity rows: {rows!r}")
    (
        index,
        uuid,
        name,
        used,
        total,
        gpu_util,
        memory_util,
        pstate,
        driver_model,
        display_active,
    ) = rows[0]
    if int(index) != int(gpu_index) or uuid != expected_uuid:
        raise BaselineError(
            f"Target GPU changed during baseline: index={index!r}, uuid={uuid!r}"
        )
    used_mib = _finite_nonnegative(used, "used VRAM")
    total_mib = _finite_nonnegative(total, "total VRAM")
    gpu_percent = _finite_nonnegative(gpu_util, "GPU utilization")
    memory_percent = _finite_nonnegative(memory_util, "memory utilization")
    if used_mib > total_mib or gpu_percent > 100 or memory_percent > 100:
        raise BaselineError("nvidia-smi target-GPU activity values are out of range")
    if driver_model != REQUIRED_DRIVER_MODEL or display_active != REQUIRED_DISPLAY_ACTIVE:
        raise BaselineError(
            "Target GPU left active WDDM display mode during baseline: "
            f"driver_model={driver_model!r}, display_active={display_active!r}"
        )
    return {
        "gpu_index": int(index),
        "gpu_uuid": uuid,
        "gpu_name": name,
        "vram_used_mib": used_mib,
        "vram_total_mib": total_mib,
        "gpu_utilization_percent": gpu_percent,
        "memory_utilization_percent": memory_percent,
        "performance_state": pstate,
        "driver_model_current": driver_model,
        "display_active": display_active,
        "query_argv": argv,
        "raw_stdout_sha256": BASE.sha256_bytes(result.stdout.encode("utf-8")),
    }


def _process_identity(pid: int) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "pid": int(pid),
        "exists": False,
        "name": None,
        "executable": None,
        "command_line": None,
        "process_create_time": None,
        "identity_errors": [],
    }
    try:
        process = psutil.Process(pid)
        identity["exists"] = True
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        identity["identity_errors"].append(f"process: {type(exc).__name__}: {exc}")
        return identity
    for key, getter in (
        ("name", process.name),
        ("executable", process.exe),
        ("command_line", process.cmdline),
        ("process_create_time", process.create_time),
    ):
        try:
            value = getter()
            identity[key] = list(value) if key == "command_line" else value
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
            identity["identity_errors"].append(f"{key}: {type(exc).__name__}: {exc}")
    return identity


def _desktop_graphics_signals(identity: dict[str, Any]) -> list[str]:
    name = str(identity.get("name") or "").lower()
    executable = str(identity.get("executable") or "").lower()
    command_line = " ".join(str(value) for value in identity.get("command_line") or []).lower()
    signals = []
    if "--type=gpu-process" in command_line:
        signals.append("chromium_or_electron_gpu_process")
    if "--video-capture-use-gpu-memory-buffer" in command_line:
        signals.append("desktop_video_capture_service")
    if "windows-mcp.exe" in command_line:
        signals.append("desktop_control_helper")
    if (
        name == "dwm.exe"
        and executable.replace("/", "\\").endswith("\\windows\\system32\\dwm.exe")
        and identity.get("process_create_time") is not None
    ):
        signals.append("windows_desktop_compositor")
    if "\\windows\\systemapps\\" in executable:
        signals.append("windows_system_ui")
    if "\\windowsapps\\" in executable and name not in {"python.exe", "pythonw.exe"}:
        signals.append("packaged_windows_ui")
    if name in {
        "explorer.exe",
        "shellhost.exe",
        "applicationframehost.exe",
        "systemsettings.exe",
        "snagiteditor.exe",
    }:
        signals.append("interactive_desktop_application")
    return sorted(set(signals))


def forbidden_process_scan() -> dict[str, Any]:
    """Find live model/inference launchers independently of NVIDIA's table."""
    blockers = []
    scanned = 0
    for process in psutil.process_iter(
        ["pid", "name", "exe", "cmdline", "create_time"], ad_value=None
    ):
        scanned += 1
        info = process.info
        name = str(info.get("name") or "")
        executable = str(info.get("exe") or "")
        command_line = [str(value) for value in info.get("cmdline") or []]
        text = " ".join([name, executable, *command_line]).lower()
        markers = sorted(marker for marker in MODEL_WORKLOAD_MARKERS if marker in text)
        reasons = []
        if markers:
            reasons.append(f"model/inference workload marker(s): {markers}")
        if name.lower() in {"python.exe", "pythonw.exe"} and not command_line:
            reasons.append("Python interpreter identity is unreadable")
        if reasons:
            blockers.append(
                {
                    "pid": int(info["pid"]),
                    "name": name or None,
                    "executable": executable or None,
                    "command_line": command_line or None,
                    "process_create_time": info.get("create_time"),
                    "blocking_reasons": reasons,
                }
            )
    return {
        "scanned_process_count": scanned,
        "model_workload_markers": list(MODEL_WORKLOAD_MARKERS),
        "blocking_processes": blockers,
    }


def classify_process_row(
    row: dict[str, Any], expected_uuid: str, identity: dict[str, Any]
) -> dict[str, Any]:
    evidence = {
        **row,
        "process_identity": identity,
        "desktop_graphics_signals": _desktop_graphics_signals(identity),
        "blocking_reasons": [],
        "classification": "blocked",
    }
    reasons: list[str] = evidence["blocking_reasons"]
    if row.get("gpu_uuid") != expected_uuid:
        reasons.append("process row is not bound to the selected GPU UUID")
    token = str(row.get("used_gpu_memory_token") or "")
    if token != WDDM_UNMETERED_MEMORY_TOKEN:
        try:
            numeric = float(token)
        except ValueError:
            reasons.append(f"unknown per-process memory token {token!r}")
        else:
            reasons.append(f"numeric per-process GPU allocation reported ({numeric} MiB)")
    if identity.get("exists") is not True:
        reasons.append("NVIDIA process PID cannot be re-identified")
    if identity.get("process_create_time") is None:
        reasons.append("NVIDIA process create time is unavailable")
    identity_text = " ".join(
        [
            str(identity.get("name") or ""),
            str(identity.get("executable") or ""),
            " ".join(str(value) for value in identity.get("command_line") or []),
            str(row.get("nvidia_process_name") or ""),
        ]
    ).lower()
    markers = sorted(marker for marker in MODEL_WORKLOAD_MARKERS if marker in identity_text)
    if markers:
        reasons.append(f"model/inference workload marker(s): {markers}")
    if not evidence["desktop_graphics_signals"]:
        reasons.append("process identity has no recognized desktop-graphics signal")
    if not reasons:
        evidence["classification"] = "allowed_unmetered_wddm_desktop_client"
    return evidence


def query_process_evidence(
    gpu_index: int,
    expected_uuid: str,
    identity_getter=_process_identity,
) -> dict[str, Any]:
    argv = [
        "nvidia-smi",
        "-i",
        str(gpu_index),
        "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ]
    result = _run_nvidia_smi(argv)
    parsed = []
    for fields in _csv_rows(result.stdout):
        if len(fields) != 4 or not fields[1].isdigit():
            parsed.append(
                {
                    "raw_fields": fields,
                    "classification": "blocked",
                    "blocking_reasons": ["malformed NVIDIA process row"],
                }
            )
            continue
        gpu_uuid, pid, process_name, memory = fields
        row = {
            "gpu_uuid": gpu_uuid,
            "pid": int(pid),
            "nvidia_process_name": process_name,
            "used_gpu_memory_token": memory,
        }
        parsed.append(classify_process_row(row, expected_uuid, identity_getter(int(pid))))
    blockers = [
        {
            "pid": row.get("pid"),
            "blocking_reasons": row.get("blocking_reasons") or [],
        }
        for row in parsed
        if row.get("classification") != "allowed_unmetered_wddm_desktop_client"
    ]
    return {
        "target_gpu_index": int(gpu_index),
        "target_gpu_uuid": expected_uuid,
        "query_argv": argv,
        "raw_stdout_sha256": BASE.sha256_bytes(result.stdout.encode("utf-8")),
        "row_count": len(parsed),
        "rows": parsed,
        "blocking_rows": blockers,
    }


def _same_lock_owner(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        return (
            int(left.get("pid") or 0) == int(right.get("pid") or 0)
            and math.isclose(
                float(left.get("process_create_time") or 0),
                float(right.get("process_create_time") or 0),
                rel_tol=0,
                abs_tol=0.001,
            )
            and str(left.get("nonce") or "") == str(right.get("nonce") or "")
            and str(left.get("role") or "") == str(right.get("role") or "")
        )
    except (TypeError, ValueError):
        return False


def lease_evidence(lease: GpuLease) -> dict[str, Any]:
    owner = dict(lease.owner or {})
    current = read_lock_receipt(lease.gpu_path)
    snapshot = BASE.stable_file_snapshot(lease.gpu_path)
    matches = lease.acquired and _same_lock_owner(owner, current)
    return {
        "path": str(lease.gpu_path),
        "owner": current,
        "receipt": snapshot,
        "matches_acquired_owner": matches,
    }


def evaluate_sample(
    activity: dict[str, Any],
    process_evidence: dict[str, Any],
    lock_evidence: dict[str, Any],
    listeners: list[int],
    forbidden_processes: dict[str, Any],
) -> list[str]:
    errors = []
    if activity.get("driver_model_current") != REQUIRED_DRIVER_MODEL:
        errors.append("selected GPU is not in exact WDDM driver mode")
    if activity.get("display_active") != REQUIRED_DISPLAY_ACTIVE:
        errors.append("selected GPU display is not active")
    if float(activity["vram_used_mib"]) > MAX_QUIESCENT_VRAM_MIB:
        errors.append(
            f"used VRAM {activity['vram_used_mib']} MiB exceeds {MAX_QUIESCENT_VRAM_MIB} MiB"
        )
    if float(activity["gpu_utilization_percent"]) > MAX_GPU_UTILIZATION_PERCENT:
        errors.append(
            "GPU utilization %s%% exceeds %s%%"
            % (activity["gpu_utilization_percent"], MAX_GPU_UTILIZATION_PERCENT)
        )
    if float(activity["memory_utilization_percent"]) > MAX_MEMORY_UTILIZATION_PERCENT:
        errors.append(
            "memory utilization %s%% exceeds %s%%"
            % (activity["memory_utilization_percent"], MAX_MEMORY_UTILIZATION_PERCENT)
        )
    if process_evidence.get("target_gpu_uuid") != activity.get("gpu_uuid"):
        errors.append("NVIDIA process evidence is not bound to the sampled GPU UUID")
    if process_evidence.get("blocking_rows"):
        errors.append(
            f"NVIDIA process evidence has {len(process_evidence['blocking_rows'])} blocking row(s)"
        )
    if listeners:
        errors.append(f"port 8000 listener(s) appeared: {listeners}")
    if lock_evidence.get("matches_acquired_owner") is not True:
        errors.append("GPU lock receipt no longer matches the acquired owner")
    if forbidden_processes.get("blocking_processes"):
        errors.append(
            "independent process scan found %s forbidden/unknown workload(s)"
            % len(forbidden_processes["blocking_processes"])
        )
    return errors


def receipt_validation_errors(payload: dict[str, Any], gpu_index: int) -> list[str]:
    """Independently recompute the load-bearing quiescence assertions."""
    errors = []
    target = payload.get("target_gpu") or {}
    policy = payload.get("quiescence_policy") or {}
    samples = payload.get("samples") or []
    uuid = str(target.get("gpu_uuid") or "")
    if payload.get("schema_version") != 2:
        errors.append("baseline schema_version is not 2")
    if payload.get("kind") != "wan-cost-ladder-quiescent-desktop-baseline":
        errors.append("baseline kind is wrong")
    if payload.get("status") != "measured":
        errors.append("baseline status is not measured")
    if int(payload.get("gpu_index", -1)) != int(gpu_index):
        errors.append("baseline GPU index is wrong")
    if int(target.get("gpu_index", -1)) != int(gpu_index) or not uuid.startswith("GPU-"):
        errors.append("baseline target GPU index/UUID binding is invalid")
    if target.get("driver_model_current") != REQUIRED_DRIVER_MODEL:
        errors.append("baseline target GPU is not WDDM")
    if target.get("display_active") != REQUIRED_DISPLAY_ACTIVE:
        errors.append("baseline target GPU display is not active")
    expected_policy = {
        "max_vram_used_mib": MAX_QUIESCENT_VRAM_MIB,
        "max_gpu_utilization_percent": MAX_GPU_UTILIZATION_PERCENT,
        "max_memory_utilization_percent": MAX_MEMORY_UTILIZATION_PERCENT,
        "recognized_unmetered_wddm_memory_token": WDDM_UNMETERED_MEMORY_TOKEN,
        "numeric_or_unknown_process_memory_tokens_block": True,
        "process_identity_and_desktop_graphics_signal_required": True,
        "port_8000_listener_required_absent": True,
        "same_gpu_lease_required_each_sample": True,
        "required_driver_model": REQUIRED_DRIVER_MODEL,
        "required_display_active": REQUIRED_DISPLAY_ACTIVE,
    }
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            errors.append(f"baseline quiescence policy drifted at {key}")
    if payload.get("port_8000_listener_pids_before") != []:
        errors.append("port 8000 was occupied before baseline")
    if payload.get("port_8000_listener_pids_after") != []:
        errors.append("port 8000 was occupied after baseline")
    if payload.get("blocking_nvidia_processes") != []:
        errors.append("baseline retained blocking NVIDIA processes")
    if int(payload.get("sample_count") or 0) != SAMPLE_COUNT or len(samples) != SAMPLE_COUNT:
        errors.append("baseline does not retain exactly five samples")
    if float(payload.get("sampling_interval_s") or 0) != SAMPLE_INTERVAL_S:
        errors.append("baseline sampling interval is not 200 ms")
    if int(payload.get("nvidia_process_observation_count") or 0) != SAMPLE_COUNT:
        errors.append("baseline process observation count is incomplete")
    manager_errors = MANAGER_GUARD.validate_offline_evidence(
        payload.get("manager_config") or {}, require_current_hash=True
    )
    errors.extend(f"Manager preboot proof: {error}" for error in manager_errors)
    if (payload.get("gpu_lease_release") or {}).get("success") is not True:
        errors.append("GPU lease release was not proved")
    source = payload.get("source") or {}
    current_source = Path(__file__).resolve()
    if (
        Path(str(source.get("path") or "")).resolve() != current_source
        or source.get("sha256") != BASE.sha256_file(current_source)
    ):
        errors.append("baseline collector source is not hash-bound to the validator")

    for index, sample in enumerate(samples):
        prefix = f"sample {index}"
        if int(sample.get("sample_index", -1)) != index:
            errors.append(f"{prefix} index is wrong")
        if int(sample.get("gpu_index", -1)) != int(gpu_index) or sample.get("gpu_uuid") != uuid:
            errors.append(f"{prefix} target GPU binding is wrong")
        if sample.get("driver_model_current") != REQUIRED_DRIVER_MODEL:
            errors.append(f"{prefix} target GPU is not WDDM")
        if sample.get("display_active") != REQUIRED_DISPLAY_ACTIVE:
            errors.append(f"{prefix} target GPU display is not active")
        try:
            vram = float(sample.get("vram_used_mib"))
            gpu_util = float(sample.get("gpu_utilization_percent"))
            memory_util = float(sample.get("memory_utilization_percent"))
        except (TypeError, ValueError):
            errors.append(f"{prefix} has non-numeric activity")
            continue
        if vram > MAX_QUIESCENT_VRAM_MIB:
            errors.append(f"{prefix} VRAM exceeds the quiescence ceiling")
        if gpu_util > MAX_GPU_UTILIZATION_PERCENT:
            errors.append(f"{prefix} GPU utilization exceeds the quiescence ceiling")
        if memory_util > MAX_MEMORY_UTILIZATION_PERCENT:
            errors.append(f"{prefix} memory utilization exceeds the quiescence ceiling")
        if sample.get("port_8000_listener_pids") != []:
            errors.append(f"{prefix} observed a port 8000 listener")
        if sample.get("quiescent") is not True or sample.get("quiescence_errors") != []:
            errors.append(f"{prefix} was not classified quiescent")
        lock = sample.get("gpu_lock") or {}
        if lock.get("matches_acquired_owner") is not True:
            errors.append(f"{prefix} did not prove the held GPU lease")
        if (lock.get("owner") or {}).get("nonce") != (
            payload.get("gpu_lease_owner") or {}
        ).get("nonce"):
            errors.append(f"{prefix} GPU lease nonce changed")
        processes = sample.get("nvidia_process_evidence") or {}
        if (
            int(processes.get("target_gpu_index", -1)) != int(gpu_index)
            or processes.get("target_gpu_uuid") != uuid
            or processes.get("blocking_rows") != []
        ):
            errors.append(f"{prefix} NVIDIA process evidence is not clean/bound")
        rows = processes.get("rows") or []
        if int(processes.get("row_count", -1)) != len(rows):
            errors.append(f"{prefix} NVIDIA process row count is inconsistent")
        for row in rows:
            identity = row.get("process_identity") or {}
            recomputed = classify_process_row(
                {
                    "gpu_uuid": row.get("gpu_uuid"),
                    "pid": row.get("pid"),
                    "nvidia_process_name": row.get("nvidia_process_name"),
                    "used_gpu_memory_token": row.get("used_gpu_memory_token"),
                },
                uuid,
                identity,
            )
            if (
                row.get("gpu_uuid") != uuid
                or row.get("used_gpu_memory_token") != WDDM_UNMETERED_MEMORY_TOKEN
                or row.get("classification")
                != "allowed_unmetered_wddm_desktop_client"
                or row.get("blocking_reasons") != []
                or identity.get("exists") is not True
                or identity.get("process_create_time") is None
                or not row.get("desktop_graphics_signals")
                or row.get("classification") != recomputed.get("classification")
                or row.get("blocking_reasons") != recomputed.get("blocking_reasons")
                or row.get("desktop_graphics_signals")
                != recomputed.get("desktop_graphics_signals")
            ):
                errors.append(f"{prefix} contains an unqualified NVIDIA process row")
        forbidden = sample.get("forbidden_process_scan") or {}
        if forbidden.get("blocking_processes") != []:
            errors.append(f"{prefix} independent forbidden-process scan is not clean")
        if int(forbidden.get("scanned_process_count") or 0) <= 0:
            errors.append(f"{prefix} independent process scan retained no evidence")

    if samples:
        try:
            peak = max(float(sample["vram_used_mib"]) for sample in samples)
            max_gpu = max(float(sample["gpu_utilization_percent"]) for sample in samples)
            max_memory = max(
                float(sample["memory_utilization_percent"]) for sample in samples
            )
            if not math.isclose(float(payload.get("vram_used_mib")), peak, abs_tol=1e-9):
                errors.append("baseline peak is not max(retained VRAM samples)")
            if not math.isclose(
                float(payload.get("max_gpu_utilization_percent")), max_gpu, abs_tol=1e-9
            ):
                errors.append("baseline max GPU utilization was not recomputed")
            if not math.isclose(
                float(payload.get("max_memory_utilization_percent")),
                max_memory,
                abs_tol=1e-9,
            ):
                errors.append("baseline max memory utilization was not recomputed")
        except (KeyError, TypeError, ValueError):
            errors.append("baseline aggregate values are malformed")
    return errors


def capture(output: Path, gpu_index: int) -> dict[str, Any]:
    if not output.is_absolute() or output.suffix.lower() != ".json":
        raise BaselineError("Output must be an absolute JSON path")
    try:
        output.resolve().relative_to(OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise BaselineError(f"Output escapes {OUTPUT_ROOT}: {output}") from exc
    if output.exists():
        raise FileExistsError(f"Baseline receipt already exists: {output}")

    lease = GpuLease(
        LAB_ROOT / ".gpu.lock",
        LAB_ROOT / ".suite.lock",
        LAB_ROOT / ".coordinator.mutex",
    )
    lease.acquire()
    lease_owner = dict(lease.owner or {})
    release = {"success": False, "error": "not attempted"}
    receipt: dict[str, Any] | None = None
    try:
        listeners_before = listener_pids(8000)
        if listeners_before:
            raise BaselineError(
                f"Port 8000 already has listener PID(s) {listeners_before}; capture before server boot"
            )
        offline = manager_offline()
        gpu = target_gpu_identity(gpu_index)
        samples = []
        all_errors = []
        for index in range(SAMPLE_COUNT):
            sampled_ns = time.time_ns()
            sampled_monotonic_ns = time.monotonic_ns()
            activity = query_gpu_activity(gpu_index, gpu["gpu_uuid"])
            processes = query_process_evidence(gpu_index, gpu["gpu_uuid"])
            lock = lease_evidence(lease)
            listeners = listener_pids(8000)
            forbidden_processes = forbidden_process_scan()
            errors = evaluate_sample(
                activity, processes, lock, listeners, forbidden_processes
            )
            host = psutil.virtual_memory()
            samples.append(
                {
                    "sample_index": index,
                    "sampled_at_ns": sampled_ns,
                    "sampled_at_utc": BASE.utc_timestamp(sampled_ns),
                    "sampled_monotonic_ns": sampled_monotonic_ns,
                    **activity,
                    "host_ram_used_bytes": int(host.used),
                    "host_ram_total_bytes": int(host.total),
                    "port_8000_listener_pids": listeners,
                    "gpu_lock": lock,
                    "nvidia_process_evidence": processes,
                    "forbidden_process_scan": forbidden_processes,
                    "quiescence_errors": errors,
                    "quiescent": not errors,
                }
            )
            all_errors.extend(f"sample {index}: {error}" for error in errors)
            if index != SAMPLE_COUNT - 1:
                time.sleep(SAMPLE_INTERVAL_S)
        listeners_after = listener_pids(8000)
        if listeners_after:
            all_errors.append(f"post-sample port 8000 listener(s): {listeners_after}")
        if all_errors:
            raise BaselineError("GPU is not quiescent: " + "; ".join(all_errors))
        peak = max(float(row["vram_used_mib"]) for row in samples)
        receipt = {
            "schema_version": 2,
            "kind": "wan-cost-ladder-quiescent-desktop-baseline",
            "measured": "local nvidia-smi before owned OTR server boot",
            "status": "measured",
            "gpu_index": int(gpu_index),
            "target_gpu": gpu,
            "sampling_interval_s": SAMPLE_INTERVAL_S,
            "sample_count": len(samples),
            "vram_used_mib": peak,
            "max_gpu_utilization_percent": max(
                float(row["gpu_utilization_percent"]) for row in samples
            ),
            "max_memory_utilization_percent": max(
                float(row["memory_utilization_percent"]) for row in samples
            ),
            "aggregation": "maximum of five conjunctively quiescent WDDM samples",
            "quiescence_policy": {
                "max_vram_used_mib": MAX_QUIESCENT_VRAM_MIB,
                "max_gpu_utilization_percent": MAX_GPU_UTILIZATION_PERCENT,
                "max_memory_utilization_percent": MAX_MEMORY_UTILIZATION_PERCENT,
                "recognized_unmetered_wddm_memory_token": WDDM_UNMETERED_MEMORY_TOKEN,
                "numeric_or_unknown_process_memory_tokens_block": True,
                "process_identity_and_desktop_graphics_signal_required": True,
                "model_workload_markers": list(MODEL_WORKLOAD_MARKERS),
                "port_8000_listener_required_absent": True,
                "same_gpu_lease_required_each_sample": True,
                "required_driver_model": REQUIRED_DRIVER_MODEL,
                "required_display_active": REQUIRED_DISPLAY_ACTIVE,
            },
            "port_8000_listener_pids_before": listeners_before,
            "port_8000_listener_pids_after": listeners_after,
            "blocking_nvidia_processes": [],
            "nvidia_process_observation_count": len(samples),
            "manager_config": offline,
            "gpu_lease_owner": lease_owner,
            "gpu_lock_path": str(lease.gpu_path),
            "samples": samples,
            "source": {
                "path": str(Path(__file__).resolve()),
                "sha256": BASE.sha256_file(Path(__file__).resolve()),
            },
        }
    finally:
        try:
            lease.release()
            release = {"success": True, "error": ""}
        except Exception as exc:
            release = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        if not release["success"]:
            raise BaselineError(f"GPU lease release failed: {release['error']}")
    if receipt is None:
        raise BaselineError("Baseline capture did not produce a receipt")
    receipt["gpu_lease_release"] = release
    validation_errors = receipt_validation_errors(receipt, gpu_index)
    if validation_errors:
        raise BaselineError(
            "Internal baseline receipt validation failed: " + "; ".join(validation_errors)
        )
    BASE.atomic_create_json(output, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gpu-index", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        receipt = capture(Path(args.output), args.gpu_index)
    except Exception as exc:
        print(f"[wan-cost-baseline] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "[wan-cost-baseline] MEASURED vram_used_mib=%s max_gpu_util=%s%% samples=%s"
        % (
            receipt["vram_used_mib"],
            receipt["max_gpu_utilization_percent"],
            receipt["sample_count"],
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
