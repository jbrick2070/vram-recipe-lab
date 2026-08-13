#!/usr/bin/env python3
"""Inventory-only preflight for the physical RTX 4060 / 8 GB bench.

This module intentionally has no HTTP client, port probe, server launcher,
GPU lock, prompt queue, or render path.  It only reads a fixed local laptop
profile, declared files, Git identity, `nvidia-smi`, and Windows RAM state.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = REPO_ROOT / "eightgb_bench"
LOCAL_ROOT = BENCH_ROOT / "local"
CONTRACT_PATH = BENCH_ROOT / "contract-v1.json"
PLAN_PATH = BENCH_ROOT / "plans" / "h3_mime_i2v_864x480_f90.json"
PROFILE_SUFFIX = ".profile.json"
PROFILE_ID_RE = re.compile(r"physical-rtx4060-8gb\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SCOPE = "PHYSICAL_4060_8GB_EXPLORATORY_NOT_5080_CERTIFICATION"
READY_STATUS = "READY_FOR_HUMAN_BOOT_APPROVAL"


class PreflightError(ValueError):
    """A local laptop profile or static benchmark input is invalid."""


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PreflightError(f"{label} cannot be read: {path}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PreflightError(f"{label} has a UTF-8 BOM: {path}")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreflightError(f"{label} is not UTF-8: {path}") from exc
    try:
        value = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise PreflightError(f"{label} is not JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{label} must be a JSON object: {path}")
    return value


def _require_exact_keys(value: Mapping[str, Any], allowed: Iterable[str], label: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise PreflightError(f"{label} contains unknown keys: {', '.join(unknown)}")


def _require_string(value: Mapping[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str):
        raise PreflightError(f"{label}.{key} must be a string")
    return result


def _require_bool(value: Mapping[str, Any], key: str, label: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise PreflightError(f"{label}.{key} must be a boolean")
    return result


def _require_int(value: Mapping[str, Any], key: str, label: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise PreflightError(f"{label}.{key} must be an integer")
    return result


def _profile_path(profile_id: str) -> Path:
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise PreflightError("profile ID is not enrolled for this physical bench")
    return LOCAL_ROOT / f"{profile_id}{PROFILE_SUFFIX}"


def _reject_placeholder(value: str, label: str) -> None:
    if not value or value.startswith("REPLACE_WITH_"):
        raise PreflightError(f"{label} is still a template placeholder")


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = os.lstat(path).st_file_attributes
    except AttributeError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _validated_path(value: str, label: str, kind: str) -> Path:
    _reject_placeholder(value, label)
    candidate = Path(value)
    rendered = str(candidate)
    if rendered.startswith("\\\\") or rendered.startswith("//"):
        raise PreflightError(f"{label} must not be a UNC path")
    if not candidate.is_absolute():
        raise PreflightError(f"{label} must be an absolute path")
    # Check the spelling supplied by the profile before resolving it.  A
    # resolved path would otherwise hide a junction/symlink component.
    parts = candidate.parts
    if not parts:
        raise PreflightError(f"{label} has no path components")
    supplied_component = Path(parts[0])
    for part in parts[1:]:
        supplied_component = supplied_component / part
        if supplied_component.exists() and _is_reparse_point(supplied_component):
            raise PreflightError(f"{label} crosses a reparse point: {supplied_component}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PreflightError(f"{label} does not resolve: {exc}") from exc
    if kind == "file" and not resolved.is_file():
        raise PreflightError(f"{label} must be a regular file")
    if kind == "directory" and not resolved.is_dir():
        raise PreflightError(f"{label} must be a directory")
    probe = resolved
    while True:
        if _is_reparse_point(probe):
            raise PreflightError(f"{label} crosses a reparse point: {probe}")
        if probe.parent == probe:
            break
        probe = probe.parent
    return resolved


def _validated_optional_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise PreflightError(f"{label} must be a string")
    if value and not SHA256_RE.fullmatch(value):
        raise PreflightError(f"{label} must be blank or a lowercase SHA-256")
    return value


def _block(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _identity_check(
    blockers: list[dict[str, str]],
    code_prefix: str,
    expected: str,
    actual: str,
) -> None:
    if not expected:
        blockers.append(_block(f"BLOCKED_{code_prefix}_UNPINNED", f"observed {actual}"))
    elif expected != actual:
        blockers.append(
            _block(f"BLOCKED_{code_prefix}_DRIFT", f"expected {expected}; observed {actual}")
        )


def readonly_environment(parent: Mapping[str, str] | None = None) -> dict[str, str]:
    """Keep read-only identity probes independent of caller launch settings."""
    source = os.environ if parent is None else parent
    allowed = {
        "appdata",
        "comspec",
        "homedrive",
        "homepath",
        "localappdata",
        "path",
        "pathext",
        "programdata",
        "systemroot",
        "temp",
        "tmp",
        "userprofile",
        "windir",
    }
    result = {key: value for key, value in source.items() if key.casefold() in allowed}
    result.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "HF_HUB_OFFLINE": "1",
            "PIP_NO_INDEX": "1",
        }
    )
    return result


def _run_readonly(argv: Sequence[str], label: str) -> str:
    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=readonly_environment(),
        )
    except OSError as exc:
        raise PreflightError(f"cannot run {label}: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip().replace("\n", " ")
        raise PreflightError(f"{label} failed ({completed.returncode}): {stderr[:300]}")
    return completed.stdout.strip()


def query_nvidia_smi() -> list[dict[str, Any]]:
    stdout = _run_readonly(
        [
            "nvidia-smi",
            "--query-gpu=uuid,name,memory.total,driver_version,driver_model.current",
            "--format=csv,noheader,nounits",
        ],
        "nvidia-smi inventory",
    )
    rows: list[dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        fields = [field.strip() for field in raw_line.split(",")]
        if len(fields) != 5:
            raise PreflightError("nvidia-smi inventory returned an unrecognized row")
        try:
            memory_total_mib = int(float(fields[2]))
        except ValueError as exc:
            raise PreflightError("nvidia-smi reported a nonnumeric memory total") from exc
        rows.append(
            {
                "uuid": fields[0],
                "name": fields[1],
                "memory_total_mib": memory_total_mib,
                "driver_version": fields[3],
                "driver_model_current": fields[4],
            }
        )
    if not rows:
        raise PreflightError("nvidia-smi inventory returned no GPUs")
    return rows


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def host_ram_snapshot() -> dict[str, float]:
    if os.name != "nt":
        raise PreflightError("physical 4060 preflight only supports Windows")
    record = _MemoryStatusEx()
    record.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(record)):
        raise PreflightError("GlobalMemoryStatusEx failed")
    return {
        "total_gib": round(record.ullTotalPhys / (1024**3), 3),
        "available_gib": round(record.ullAvailPhys / (1024**3), 3),
    }


def _git_identity(comfyui_root: Path) -> dict[str, Any]:
    commit = _run_readonly(["git", "-C", str(comfyui_root), "rev-parse", "HEAD"], "ComfyUI Git")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PreflightError("ComfyUI Git returned an invalid commit")
    dirty = bool(
        _run_readonly(["git", "-C", str(comfyui_root), "status", "--porcelain"], "ComfyUI Git status")
    )
    return {"commit": commit, "dirty": dirty}


def _validate_contract(contract: Mapping[str, Any]) -> None:
    _require_exact_keys(
        contract,
        {
            "schema_version",
            "id",
            "scope",
            "status",
            "purpose",
            "public_claim_policy",
            "required_hardware",
            "acceptance_gates",
            "future_boot_policy",
            "explicitly_not_used",
        },
        "contract",
    )
    if _require_int(contract, "schema_version", "contract") != 1:
        raise PreflightError("contract schema_version must be 1")
    if _require_string(contract, "scope", "contract") != SCOPE:
        raise PreflightError("contract scope is not the physical 4060 scope")
    hardware = contract.get("required_hardware")
    if not isinstance(hardware, dict):
        raise PreflightError("contract.required_hardware must be an object")
    if _require_string(hardware, "gpu_name", "contract.required_hardware") != "NVIDIA GeForce RTX 4060 Laptop GPU":
        raise PreflightError("contract must pin the RTX 4060 Laptop GPU name")
    if _require_int(hardware, "vram_total_mib_min", "contract.required_hardware") != 7800:
        raise PreflightError("contract must set the physical 8 GB lower VRAM bound")
    if _require_int(hardware, "vram_total_mib_max", "contract.required_hardware") != 8192:
        raise PreflightError("contract must set the physical 8 GB upper VRAM bound")
    gates = contract.get("acceptance_gates")
    if not isinstance(gates, dict):
        raise PreflightError("contract.acceptance_gates must be an object")
    if gates.get("absolute_peak_vram_gib_lte") != 7.5 or gates.get("absolute_peak_host_ram_gib_lte") != 28:
        raise PreflightError("contract must retain 7.5 GiB VRAM and 28 GiB host-RAM gates")
    policy = contract.get("future_boot_policy")
    if not isinstance(policy, dict):
        raise PreflightError("contract.future_boot_policy must be an object")
    expected = {
        "port": 8199,
        "listener": "127.0.0.1 only",
        "sage_attention": "forbidden",
        "manager": "forbidden",
        "reserve_vram": "forbidden",
        "pinned_memory": "disabled",
        "network": "offline",
    }
    for key, item in expected.items():
        if policy.get(key) != item:
            raise PreflightError(f"contract future boot policy drifted at {key}")


def _validate_plan(plan: Mapping[str, Any]) -> None:
    _require_exact_keys(
        plan,
        {
            "schema_version",
            "id",
            "status",
            "scope",
            "purpose",
            "orientation_only_source",
            "engine",
            "video_contract",
            "required_core_nodes",
            "follow_up_ladder",
            "blockers_before_launch",
        },
        "plan",
    )
    if _require_int(plan, "schema_version", "plan") != 1:
        raise PreflightError("plan schema_version must be 1")
    if _require_string(plan, "id", "plan") != "h3-mime-i2v-864x480-f90":
        raise PreflightError("only the declared first physical H3 MIME cell is allowed")
    if _require_string(plan, "status", "plan") != "BLOCKED_LOCAL_MODEL_ADMISSION":
        raise PreflightError("plan must remain blocked before local model admission")
    if _require_string(plan, "scope", "plan") != SCOPE:
        raise PreflightError("plan scope is not the physical 4060 scope")
    video = plan.get("video_contract")
    if not isinstance(video, dict):
        raise PreflightError("plan.video_contract must be an object")
    expected_video = {
        "fixture": "fixtures/scene_still.png",
        "fixture_sha256": "0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596",
        "width": 864,
        "height": 480,
        "frames": 90,
        "fps": 24,
        "duration_s": 3.75,
        "steps": 20,
        "audio": True,
        "seed": 42,
    }
    for key, item in expected_video.items():
        if video.get(key) != item:
            raise PreflightError(f"plan video contract drifted at {key}")
    engine = plan.get("engine")
    if not isinstance(engine, dict) or not isinstance(engine.get("required_assets"), list):
        raise PreflightError("plan.engine.required_assets must be a list")
    expected_assets = {
        ("diffusion_models", "minimax_h3_fl2va_pruned_int8_convrot.safetensors"): 20970379616,
        ("text_encoders", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"): 15687142551,
        ("vae", "minimax_h3_video_vae_fp16.safetensors"): 5207808496,
        ("vae", "minimax_h3_audio_vae_fp32.safetensors"): 605254808,
    }
    actual_assets: dict[tuple[str, str], int] = {}
    for asset in engine["required_assets"]:
        if not isinstance(asset, dict):
            raise PreflightError("plan contains a non-object asset")
        category = asset.get("category")
        filename = asset.get("filename")
        expected_bytes = asset.get("expected_bytes")
        if not isinstance(category, str) or not isinstance(filename, str) or not isinstance(expected_bytes, int):
            raise PreflightError("plan asset has an invalid shape")
        actual_assets[(category, filename)] = expected_bytes
    if actual_assets != expected_assets:
        raise PreflightError("plan asset set drifted")
    required_nodes = plan.get("required_core_nodes")
    if not isinstance(required_nodes, list) or "MiniMaxH3ImageToVideo" not in required_nodes:
        raise PreflightError("plan must require the native MiniMax H3 image-to-video node")


def static_check() -> dict[str, Any]:
    contract = _read_json(CONTRACT_PATH, "contract")
    plan = _read_json(PLAN_PATH, "plan")
    _validate_contract(contract)
    _validate_plan(plan)
    fixture = REPO_ROOT / "fixtures" / "scene_still.png"
    if not fixture.is_file() or sha256_file(fixture) != plan["video_contract"]["fixture_sha256"]:
        raise PreflightError("checked-in scene_still fixture does not match the declared plan")
    return {
        "status": "STATIC_CONTRACT_VALID",
        "scope": SCOPE,
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "plan_sha256": sha256_file(PLAN_PATH),
        "fixture_sha256": sha256_file(fixture),
        "network_or_gpu_actions": "none",
    }


def hardware_inventory() -> dict[str, Any]:
    """Read the physical laptop hardware before a local profile exists.

    This is intentionally useful even when ComfyUI or any candidate model is
    absent.  It is not an enrollment or a render authorization.
    """
    static = static_check()
    return {
        "kind": "physical_4060_8gb_hardware_inventory",
        "status": "HARDWARE_OBSERVED_NOT_ENROLLED",
        "scope": SCOPE,
        "contract_sha256": static["contract_sha256"],
        "gpus": query_nvidia_smi(),
        "host_ram": host_ram_snapshot(),
        "next_action": "Copy the exact matching GPU UUID into the laptop-local profile template, then declare real local ComfyUI and model paths.",
        "network_or_gpu_actions": "none",
    }


def _validate_profile(profile: Mapping[str, Any], profile_id: str) -> None:
    _require_exact_keys(
        profile,
        {"schema_version", "id", "scope", "expected_gpu", "paths", "identity", "policy"},
        "profile",
    )
    if _require_int(profile, "schema_version", "profile") != 1:
        raise PreflightError("profile schema_version must be 1")
    if _require_string(profile, "id", "profile") != profile_id:
        raise PreflightError("profile ID does not match the selected enrolled ID")
    if _require_string(profile, "scope", "profile") != SCOPE:
        raise PreflightError("profile scope is not the physical 4060 scope")
    gpu = profile.get("expected_gpu")
    if not isinstance(gpu, dict):
        raise PreflightError("profile.expected_gpu must be an object")
    _require_exact_keys(gpu, {"name", "uuid", "memory_total_mib_min", "memory_total_mib_max"}, "profile.expected_gpu")
    if _require_string(gpu, "name", "profile.expected_gpu") != "NVIDIA GeForce RTX 4060 Laptop GPU":
        raise PreflightError("profile must pin the RTX 4060 Laptop GPU name")
    if _require_int(gpu, "memory_total_mib_min", "profile.expected_gpu") != 7800 or _require_int(gpu, "memory_total_mib_max", "profile.expected_gpu") != 8192:
        raise PreflightError("profile GPU memory bounds must be exactly the 8 GB contract")
    uuid = _require_string(gpu, "uuid", "profile.expected_gpu")
    if uuid and not re.fullmatch(r"GPU-[A-Za-z0-9-]+", uuid):
        raise PreflightError("profile expected GPU UUID has an invalid shape")
    paths = profile.get("paths")
    if not isinstance(paths, dict):
        raise PreflightError("profile.paths must be an object")
    _require_exact_keys(paths, {"python", "comfyui_root", "model_paths_config", "model_roots"}, "profile.paths")
    roots = paths.get("model_roots")
    if not isinstance(roots, dict):
        raise PreflightError("profile.paths.model_roots must be an object")
    _require_exact_keys(roots, {"diffusion_models", "text_encoders", "vae"}, "profile.paths.model_roots")
    identity = profile.get("identity")
    if not isinstance(identity, dict):
        raise PreflightError("profile.identity must be an object")
    _require_exact_keys(
        identity,
        {"python_sha256", "python_major_minor", "comfyui_git_commit", "comfyui_main_py_sha256", "model_paths_config_sha256", "model_sha256s"},
        "profile.identity",
    )
    for key in ("python_sha256", "comfyui_main_py_sha256", "model_paths_config_sha256"):
        _validated_optional_sha256(identity.get(key), f"profile.identity.{key}")
    python_major_minor = _require_string(identity, "python_major_minor", "profile.identity")
    if python_major_minor and python_major_minor not in {"3.10", "3.12"}:
        raise PreflightError("profile identity Python version must be blank, 3.10, or 3.12")
    commit = _require_string(identity, "comfyui_git_commit", "profile.identity")
    if commit and not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PreflightError("profile ComfyUI commit must be blank or a full lowercase Git commit")
    model_sha256s = identity.get("model_sha256s")
    if not isinstance(model_sha256s, dict):
        raise PreflightError("profile identity model_sha256s must be an object")
    expected_model_keys = {
        "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "vae/minimax_h3_video_vae_fp16.safetensors",
        "vae/minimax_h3_audio_vae_fp32.safetensors",
    }
    if set(model_sha256s) != expected_model_keys:
        raise PreflightError("profile model SHA keys must exactly match the first physical H3 plan")
    for key, value in model_sha256s.items():
        _validated_optional_sha256(value, f"profile.identity.model_sha256s[{key}]")
    policy = profile.get("policy")
    if not isinstance(policy, dict):
        raise PreflightError("profile.policy must be an object")
    _require_exact_keys(policy, {"require_clean_comfyui_git", "allowed_python_major_minors", "sage_attention", "manager", "reserve_vram", "network"}, "profile.policy")
    if not _require_bool(policy, "require_clean_comfyui_git", "profile.policy"):
        raise PreflightError("profile must require a clean ComfyUI checkout")
    if policy.get("allowed_python_major_minors") != ["3.10", "3.12"]:
        raise PreflightError("profile allowed Python versions drifted")
    if policy.get("sage_attention") is not False or policy.get("manager") is not False:
        raise PreflightError("profile must forbid SageAttention and Manager")
    if policy.get("reserve_vram") != "forbidden" or policy.get("network") != "offline":
        raise PreflightError("profile must retain no-reserve and offline policy")


def _observed_file(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _profile_paths(profile: Mapping[str, Any]) -> dict[str, Path]:
    paths = profile["paths"]
    roots = paths["model_roots"]
    return {
        "python": _validated_path(paths["python"], "profile.paths.python", "file"),
        "comfyui_root": _validated_path(paths["comfyui_root"], "profile.paths.comfyui_root", "directory"),
        "model_paths_config": _validated_path(paths["model_paths_config"], "profile.paths.model_paths_config", "file"),
        "diffusion_models": _validated_path(roots["diffusion_models"], "profile model root diffusion_models", "directory"),
        "text_encoders": _validated_path(roots["text_encoders"], "profile model root text_encoders", "directory"),
        "vae": _validated_path(roots["vae"], "profile model root vae", "directory"),
    }


def _selected_gpu(rows: list[dict[str, Any]], expected_gpu: Mapping[str, Any], blockers: list[dict[str, str]]) -> dict[str, Any] | None:
    expected_name = expected_gpu["name"]
    expected_uuid = expected_gpu["uuid"]
    candidates = [row for row in rows if row["name"] == expected_name]
    if not candidates:
        blockers.append(_block("BLOCKED_GPU_NAME", f"expected {expected_name}; observed {[row['name'] for row in rows]}"))
        return None
    if expected_uuid:
        candidates = [row for row in candidates if row["uuid"] == expected_uuid]
        if not candidates:
            blockers.append(_block("BLOCKED_GPU_UUID_DRIFT", f"expected {expected_uuid}; observed {[row['uuid'] for row in rows]}"))
            return None
    elif len(candidates) == 1:
        blockers.append(_block("BLOCKED_GPU_UUID_UNPINNED", f"observed {candidates[0]['uuid']}"))
    else:
        blockers.append(_block("BLOCKED_GPU_UUID_AMBIGUOUS", f"matching GPU UUIDs {[row['uuid'] for row in candidates]}"))
        return None
    if len(candidates) != 1:
        blockers.append(_block("BLOCKED_GPU_AMBIGUOUS", "more than one matching GPU remained after UUID selection"))
        return None
    selected = candidates[0]
    if not expected_gpu["memory_total_mib_min"] <= selected["memory_total_mib"] <= expected_gpu["memory_total_mib_max"]:
        blockers.append(
            _block(
                "BLOCKED_GPU_VRAM_RANGE",
                f"expected {expected_gpu['memory_total_mib_min']}..{expected_gpu['memory_total_mib_max']} MiB; observed {selected['memory_total_mib']} MiB",
            )
        )
    return selected


def preflight(profile_id: str) -> dict[str, Any]:
    static = static_check()
    profile_path = _profile_path(profile_id)
    profile = _read_json(profile_path, "laptop-local profile")
    _validate_profile(profile, profile_id)
    paths = _profile_paths(profile)
    blockers: list[dict[str, str]] = []
    observed: dict[str, Any] = {}

    gpu_rows = query_nvidia_smi()
    selected_gpu = _selected_gpu(gpu_rows, profile["expected_gpu"], blockers)
    observed["gpus"] = gpu_rows
    observed["selected_gpu"] = selected_gpu

    ram = host_ram_snapshot()
    observed["host_ram"] = ram
    if ram["total_gib"] < 30:
        blockers.append(_block("BLOCKED_HOST_RAM_TOTAL", f"expected at least 30 GiB; observed {ram['total_gib']} GiB"))
    if ram["available_gib"] < 8:
        blockers.append(_block("BLOCKED_HOST_RAM_AVAILABLE", f"need 8 GiB free before any later boot; observed {ram['available_gib']} GiB"))

    identity = profile["identity"]
    python_observed = _observed_file(paths["python"])
    python_major_minor = _run_readonly(
        [str(paths["python"]), "-I", "-S", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        "declared Python identity",
    )
    observed["python"] = {**python_observed, "major_minor": python_major_minor}
    if python_major_minor not in profile["policy"]["allowed_python_major_minors"]:
        blockers.append(_block("BLOCKED_PYTHON_VERSION", f"observed {python_major_minor}"))
    _identity_check(blockers, "PYTHON_SHA256", identity["python_sha256"], python_observed["sha256"])
    _identity_check(blockers, "PYTHON_VERSION", identity["python_major_minor"], python_major_minor)

    main_py = paths["comfyui_root"] / "main.py"
    if not main_py.is_file():
        blockers.append(_block("BLOCKED_COMFYUI_MAIN_MISSING", f"missing {main_py}"))
        observed["comfyui"] = {"root": str(paths["comfyui_root"]), "main_py": None}
    else:
        main_observed = _observed_file(main_py)
        git_observed = _git_identity(paths["comfyui_root"])
        observed["comfyui"] = {"root": str(paths["comfyui_root"]), "main_py": main_observed, **git_observed}
        _identity_check(blockers, "COMFYUI_COMMIT", identity["comfyui_git_commit"], git_observed["commit"])
        _identity_check(blockers, "COMFYUI_MAIN_SHA256", identity["comfyui_main_py_sha256"], main_observed["sha256"])
        if profile["policy"]["require_clean_comfyui_git"] and git_observed["dirty"]:
            blockers.append(_block("BLOCKED_COMFYUI_DIRTY", "declared ComfyUI checkout has uncommitted changes"))

    config_observed = _observed_file(paths["model_paths_config"])
    observed["model_paths_config"] = config_observed
    _identity_check(blockers, "MODEL_PATHS_CONFIG_SHA256", identity["model_paths_config_sha256"], config_observed["sha256"])

    plan = _read_json(PLAN_PATH, "plan")
    model_observed: dict[str, Any] = {}
    for asset in plan["engine"]["required_assets"]:
        category = asset["category"]
        filename = asset["filename"]
        key = f"{category}/{filename}"
        path = paths[category] / filename
        if not path.is_file():
            blockers.append(_block("BLOCKED_MODEL_MISSING", key))
            model_observed[key] = {"path": str(path), "exists": False}
            continue
        file_observed = _observed_file(path)
        model_observed[key] = {"exists": True, **file_observed}
        if file_observed["bytes"] != asset["expected_bytes"]:
            blockers.append(
                _block(
                    "BLOCKED_MODEL_BYTES_DRIFT",
                    f"{key}: expected {asset['expected_bytes']}; observed {file_observed['bytes']}",
                )
            )
        _identity_check(blockers, "MODEL_SHA256", identity["model_sha256s"][key], file_observed["sha256"])
    observed["models"] = model_observed

    fixture = REPO_ROOT / "fixtures" / "scene_still.png"
    fixture_sha256 = sha256_file(fixture)
    observed["fixture"] = {"path": str(fixture), "sha256": fixture_sha256}
    if fixture_sha256 != plan["video_contract"]["fixture_sha256"]:
        blockers.append(_block("BLOCKED_FIXTURE_SHA256_DRIFT", fixture_sha256))

    return {
        "receipt_schema_version": 1,
        "kind": "physical_4060_8gb_inventory_preflight",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": READY_STATUS if not blockers else blockers[0]["code"],
        "scope": SCOPE,
        "profile_id": profile_id,
        "contract_sha256": static["contract_sha256"],
        "plan_sha256": static["plan_sha256"],
        "profile_sha256": sha256_file(profile_path),
        "preflight_script_sha256": sha256_file(Path(__file__).resolve()),
        "blockers": blockers,
        "observed": observed,
        "next_action": (
            "A separately reviewed server-admission and direct-runner implementation is required; this inventory never booted ComfyUI or queued a prompt."
            if not blockers
            else "Fix only the stated local identity or asset blockers, then repeat this inventory-only preflight."
        ),
        "network_or_gpu_actions": "none",
    }


def write_receipt(payload: Mapping[str, Any]) -> Path:
    receipt_dir = LOCAL_ROOT / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nonce = hashlib.sha256(canonical_bytes(payload)).hexdigest()[:12]
    path = receipt_dir / f"preflight-{now}-{nonce}.json"
    serialized = canonical_bytes(payload)
    try:
        with path.open("xb") as handle:
            handle.write(serialized)
    except FileExistsError as exc:
        raise PreflightError(f"immutable preflight receipt already exists: {path}") from exc
    return path


def format_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory-only physical RTX 4060 / 8 GB preflight; never boots ComfyUI or renders."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("static-check", help="validate the checked-in physical 4060 contract and plan")
    subparsers.add_parser("hardware-inventory", help="read only the installed GPU and RAM; no profile or server is needed")
    preflight_parser = subparsers.add_parser("preflight", help="inspect one fixed laptop-local enrolled profile")
    preflight_parser.add_argument("--profile", required=True, help="only physical-rtx4060-8gb is enrolled")
    preflight_parser.add_argument("--write-receipt", action="store_true", help="write an immutable receipt beneath eightgb_bench/local only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "static-check":
            print(format_json(static_check()), end="")
            return 0
        if args.command == "hardware-inventory":
            print(format_json(hardware_inventory()), end="")
            return 0
        if args.command == "preflight":
            payload = preflight(args.profile)
            if args.write_receipt:
                payload = dict(payload)
                payload["receipt_path"] = str(write_receipt(payload))
            print(format_json(payload), end="")
            return 0 if payload["status"] == READY_STATUS else 3
    except PreflightError as exc:
        parser.exit(2, f"physical-4060 preflight: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
