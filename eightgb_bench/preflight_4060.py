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
import math
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = REPO_ROOT / "eightgb_bench"
LOCAL_ROOT = BENCH_ROOT / "local"
REPORTS_ROOT = BENCH_ROOT / "reports"
PUBLIC_REPORT_REPO_PATH = Path("eightgb_bench") / "reports" / "physical-rtx4060-8gb-hardware.json"
CONTRACT_PATH = BENCH_ROOT / "contract-v1.json"
SENTINEL_PLAN_ID = "h3-mime-i2v-864x480-f90"
MOTION_DEMO_PLAN_ID = "h3-mime-i2v-motion-demo-f90"
PLAN_IDS = (SENTINEL_PLAN_ID, MOTION_DEMO_PLAN_ID)
# Keep this alias for the original sentinel and existing evidence tests.  All
# new selection goes through the registry below; no caller supplies a path.
PLAN_PATH = BENCH_ROOT / "plans" / "h3_mime_i2v_864x480_f90.json"
PLAN_REGISTRY: dict[str, dict[str, str]] = {
    SENTINEL_PLAN_ID: {
        "plan_filename": "h3_mime_i2v_864x480_f90.json",
        "source_recipe": "recipes/h3_mime_i2v.json",
        "source_name": "h3_mime_i2v",
        "source_recipe_sha256": "fde5775b64ac207ebd33761de18a5ac3a899c57c2880776b66691d6dc23c77c9",
        "source_graph_sha256": "10ecc48db9bd12faba0a3e1485bd699606073221824ba24e238fa8b60b7a4e09",
        "source_prompt_sha256": "17571e18e68017eef580e3007b15c6ef91e55f5e4380f70f5613535258e5debb",
        "status": "BLOCKED_LOCAL_MODEL_ADMISSION",
        "launch_config_filename": "runner-4060-launch.json",
    },
    MOTION_DEMO_PLAN_ID: {
        "plan_filename": "h3_mime_i2v_motion_demo_f90.json",
        "source_recipe": "eightgb_bench/recipes/h3_mime_i2v_motion_demo.json",
        "source_name": "h3_mime_i2v_motion_demo",
        "source_recipe_sha256": "73c4a2e62f947ac62f3463a3cff2ec853fee57ac09377a20603a2e76b52bb2ca",
        "source_graph_sha256": "fe9458566bc5dee8450619fd68e358d2bfb2ca2100372d3c68e2786fa14b02e4",
        "source_prompt_sha256": "6567fed1820de2ce300c93c068bc0d7ece277e3bb205ec90af6bf6a17d8c38c7",
        "status": "PREPARED_FRESH_SEQUENCE_REQUIRED",
        "launch_config_filename": "runner-4060-motion-demo-launch.json",
    },
}
PROFILE_SUFFIX = ".profile.json"
PROFILE_ID_RE = re.compile(r"physical-rtx4060-8gb\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SCOPE = "PHYSICAL_4060_8GB_EXPLORATORY_NOT_5080_CERTIFICATION"
READY_STATUS = "READY_FOR_HUMAN_BOOT_APPROVAL"
READ_ONLY_GPU_INVENTORY_ACTIONS = (
    "network: none; gpu: read-only nvidia-smi inventory; gpu_allocation: none"
)


class PreflightError(ValueError):
    """A local laptop profile or static benchmark input is invalid."""


def _plan_spec(plan_id: str) -> Mapping[str, str]:
    """Return only a code-owned enrolled plan; never accept a path from input."""
    try:
        return PLAN_REGISTRY[plan_id]
    except KeyError as exc:
        raise PreflightError("plan ID is not enrolled for this physical bench") from exc


def plan_path_for_id(plan_id: str) -> Path:
    _plan_spec(plan_id)
    # Preserve the monkeypatchable sentinel alias used by legacy static tests.
    if plan_id == SENTINEL_PLAN_ID:
        return PLAN_PATH
    return BENCH_ROOT / "plans" / _plan_spec(plan_id)["plan_filename"]


def source_recipe_path_for_id(plan_id: str) -> Path:
    return REPO_ROOT / _plan_spec(plan_id)["source_recipe"]


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


def sha256_utf8_text_file(path: Path) -> str:
    """Hash checked-in text consistently across LF and Windows CRLF checkouts."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PreflightError(f"cannot read UTF-8 text file {path}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PreflightError(f"UTF-8 text file has a BOM: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreflightError(f"UTF-8 text file cannot be decoded: {path}") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return sha256_bytes(normalized)


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


def _profile_path(profile_id: str, local_root: Path | None = None) -> Path:
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise PreflightError("profile ID is not enrolled for this physical bench")
    return (LOCAL_ROOT if local_root is None else local_root) / f"{profile_id}{PROFILE_SUFFIX}"


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


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _validated_local_root(*, create: bool) -> Path:
    """Return only the exact non-reparse local state namespace for this bench."""
    bench_root = _validated_path(str(BENCH_ROOT), "physical 4060 bench root", "directory")
    expected = BENCH_ROOT / "local"
    if not _same_path(LOCAL_ROOT, expected):
        raise PreflightError("physical 4060 local state root drifted from eightgb_bench/local")
    if not LOCAL_ROOT.exists():
        if not create:
            raise PreflightError("physical 4060 local state root is absent")
        try:
            LOCAL_ROOT.mkdir(parents=False, exist_ok=False)
        except OSError as exc:
            raise PreflightError(f"cannot create physical 4060 local state root: {exc}") from exc
    local_root = _validated_path(str(LOCAL_ROOT), "physical 4060 local state root", "directory")
    if local_root.parent != bench_root:
        raise PreflightError("physical 4060 local state root escaped the bench root")
    return local_root


def _validated_public_reports_root() -> Path:
    """Return the checked-in, non-reparse public-report namespace only."""
    bench_root = _validated_path(str(BENCH_ROOT), "physical 4060 bench root", "directory")
    expected = BENCH_ROOT / "reports"
    if not _same_path(REPORTS_ROOT, expected):
        raise PreflightError("physical 4060 public report root drifted from eightgb_bench/reports")
    if not REPORTS_ROOT.exists():
        raise PreflightError("physical 4060 public report directory is absent; pull the current lab checkout")
    reports_root = _validated_path(
        str(REPORTS_ROOT), "physical 4060 public report directory", "directory"
    )
    if not _same_path(reports_root.parent, bench_root):
        raise PreflightError("physical 4060 public report directory escaped the bench root")
    return reports_root


def _validated_child_file(root: Path, basename: str, label: str) -> Path | None:
    """Reject a missing or redirected file derived from an enrolled root."""
    candidate = root / basename
    if not candidate.exists():
        return None
    checked = _validated_path(str(candidate), label, "file")
    if not checked.is_relative_to(root):
        raise PreflightError(f"{label} escaped its declared parent root")
    return checked


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
        "programfiles",
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


def _run_readonly(argv: Sequence[str], label: str, *, timeout_s: float = 20.0) -> str:
    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=readonly_environment(),
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(f"{label} timed out after {timeout_s:g} seconds") from exc
    except OSError as exc:
        raise PreflightError(f"cannot run {label}: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip().replace("\n", " ")
        raise PreflightError(f"{label} failed ({completed.returncode}): {stderr[:300]}")
    return completed.stdout.strip()


def _windows_system_directory() -> Path:
    if os.name != "nt":
        raise PreflightError("physical 4060 preflight only supports Windows")
    buffer = ctypes.create_unicode_buffer(32768)
    copied = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if copied == 0 or copied >= len(buffer):
        raise PreflightError("cannot determine the trusted Windows system directory")
    return _validated_path(buffer.value, "trusted Windows system directory", "directory")


def _trusted_nvidia_smi_path() -> Path:
    candidate = _windows_system_directory() / "nvidia-smi.exe"
    return _validated_path(str(candidate), "trusted nvidia-smi", "file")


def _trusted_git_path() -> Path:
    system_directory = _windows_system_directory()
    drive_root = Path(system_directory.anchor)
    candidates = (
        drive_root / "Program Files" / "Git" / "cmd" / "git.exe",
        drive_root / "Program Files" / "Git" / "bin" / "git.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return _validated_path(str(candidate), "trusted Git executable", "file")
    raise PreflightError("trusted Git executable was not found under Program Files")


def query_nvidia_smi() -> list[dict[str, Any]]:
    stdout = _run_readonly(
        [
            str(_trusted_nvidia_smi_path()),
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
    git = str(_trusted_git_path())
    safe_git = [git, "-c", f"safe.directory={comfyui_root}", "-C", str(comfyui_root)]
    commit = _run_readonly([*safe_git, "rev-parse", "HEAD"], "ComfyUI Git")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PreflightError("ComfyUI Git returned an invalid commit")
    dirty = bool(
        _run_readonly([*safe_git, "status", "--porcelain"], "ComfyUI Git status")
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
        "port": 18299,
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


def _validate_plan(plan: Mapping[str, Any], plan_id: str) -> None:
    spec = _plan_spec(plan_id)
    plan_keys = {
        "schema_version",
        "id",
        "status",
        "scope",
        "purpose",
        "engine",
        "video_contract",
        "required_core_nodes",
        "future_node_provider_policy",
        "follow_up_ladder",
        "blockers_before_launch",
    }
    if plan_id == SENTINEL_PLAN_ID:
        plan_keys.add("orientation_only_source")
    else:
        plan_keys.update({"source_recipe", "baseline_sentinel"})
    _require_exact_keys(
        plan,
        plan_keys,
        "plan",
    )
    if _require_int(plan, "schema_version", "plan") != 1:
        raise PreflightError("plan schema_version must be 1")
    if _require_string(plan, "id", "plan") != plan_id:
        raise PreflightError("checked-in physical plan ID drifted from its enrolled registry entry")
    if _require_string(plan, "status", "plan") != spec["status"]:
        raise PreflightError("checked-in physical plan status drifted from its enrolled registry entry")
    if _require_string(plan, "scope", "plan") != SCOPE:
        raise PreflightError("plan scope is not the physical 4060 scope")
    if plan_id == SENTINEL_PLAN_ID:
        orientation = plan.get("orientation_only_source")
        if not isinstance(orientation, dict):
            raise PreflightError("plan.orientation_only_source must be an object")
        _require_exact_keys(
            orientation,
            {"recipe", "recipe_sha256", "receipt", "receipt_sha256", "observed_on_other_machine"},
            "plan.orientation_only_source",
        )
        if _require_string(orientation, "recipe", "plan.orientation_only_source") != spec["source_recipe"]:
            raise PreflightError("plan orientation recipe path drifted")
        if _require_string(orientation, "receipt", "plan.orientation_only_source") != "results/h3_mime_i2v_run1.json":
            raise PreflightError("plan orientation receipt path drifted")
        if _validated_optional_sha256(orientation.get("recipe_sha256"), "plan orientation recipe SHA") != spec["source_recipe_sha256"]:
            raise PreflightError("plan orientation recipe SHA drifted")
        if _validated_optional_sha256(orientation.get("receipt_sha256"), "plan orientation receipt SHA") != "b1bb6a4e5df65c4acd890d39093b7b88ee3f1df00b71a763a43b54673fb60be7":
            raise PreflightError("plan orientation receipt SHA drifted")
        orientation_values = orientation.get("observed_on_other_machine")
        if not isinstance(orientation_values, dict):
            raise PreflightError("plan orientation observed values must be an object")
        if orientation_values.get("peak_vram_gib") != 7.28 or orientation_values.get("peak_host_ram_gib") != 27.56:
            raise PreflightError("plan orientation measurement values drifted")
    else:
        source = plan.get("source_recipe")
        if not isinstance(source, dict):
            raise PreflightError("motion plan.source_recipe must be an object")
        _require_exact_keys(
            source,
            {"path", "name", "recipe_sha256", "graph_sha256", "prompt_sha256"},
            "motion plan.source_recipe",
        )
        expected_source = {
            "path": spec["source_recipe"],
            "name": spec["source_name"],
            "recipe_sha256": spec["source_recipe_sha256"],
            "graph_sha256": spec["source_graph_sha256"],
            "prompt_sha256": spec["source_prompt_sha256"],
        }
        if source != expected_source:
            raise PreflightError("motion plan source recipe binding drifted from its enrolled registry entry")
        baseline = plan.get("baseline_sentinel")
        if not isinstance(baseline, dict):
            raise PreflightError("motion plan.baseline_sentinel must be an object")
        _require_exact_keys(
            baseline, {"plan_id", "recipe", "recipe_sha256", "scope"}, "motion plan.baseline_sentinel"
        )
        if baseline.get("plan_id") != SENTINEL_PLAN_ID or baseline.get("recipe") != PLAN_REGISTRY[SENTINEL_PLAN_ID]["source_recipe"] or baseline.get("recipe_sha256") != PLAN_REGISTRY[SENTINEL_PLAN_ID]["source_recipe_sha256"]:
            raise PreflightError("motion plan sentinel baseline binding drifted")
        scope = baseline.get("scope")
        if not isinstance(scope, str) or "does not measure" not in scope or "must never be reused" not in scope:
            raise PreflightError("motion plan must disclose that sentinel warmth is not reusable")
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
    expected_nodes = {
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        "RandomNoise",
        "BasicGuider",
        "LoadImage",
        "MiniMaxH3ImageToVideo",
        "SamplerCustomAdvanced",
        "BasicScheduler",
        "KSamplerSelect",
        "VAEDecode",
        "VAEDecodeAudio",
        "CreateVideo",
        "SaveVideo",
    }
    if not isinstance(required_nodes, list) or set(required_nodes) != expected_nodes or len(required_nodes) != len(expected_nodes):
        raise PreflightError("plan required node set drifted from the bound H3 MIME source")
    provider_policy = plan.get("future_node_provider_policy")
    if not isinstance(provider_policy, dict):
        raise PreflightError("plan future node provider policy must be an object")
    if provider_policy.get("status") != "NOT_ADMITTED_UNTIL_A_LAPTOP_OWNED_SERVER_PROVES_NODE_SOURCE_AND_COMMIT":
        raise PreflightError("plan node provider policy is not fail-closed")
    whitelist = provider_policy.get("custom_node_whitelist")
    if whitelist != [{"id": "ComfyUI-KJNodes", "git_commit": "b7646ad70a7daa7aeb919ca542274758d26ba2df", "role": "expected MiniMax H3 custom-node provider"}]:
        raise PreflightError("plan custom node whitelist drifted")
    proofs = provider_policy.get("required_live_proof")
    if not isinstance(proofs, list) or len(proofs) < 3:
        raise PreflightError("plan must retain future live node-provider proof requirements")


def _bound_orientation_source(plan: Mapping[str, Any]) -> dict[str, Any]:
    orientation = plan["orientation_only_source"]
    repo_root = _validated_path(str(REPO_ROOT), "repository root", "directory")
    recipe_path = _validated_path(
        str(REPO_ROOT / orientation["recipe"]), "bound orientation recipe", "file"
    )
    receipt_path = _validated_path(
        str(REPO_ROOT / orientation["receipt"]), "bound orientation receipt", "file"
    )
    if not recipe_path.is_relative_to(repo_root) or not receipt_path.is_relative_to(repo_root):
        raise PreflightError("bound orientation evidence escaped the repository")
    recipe = _read_json(recipe_path, "bound orientation recipe")
    receipt = _read_json(receipt_path, "bound orientation receipt")
    if sha256_utf8_text_file(recipe_path) != orientation["recipe_sha256"]:
        raise PreflightError("bound orientation recipe bytes do not match the plan")
    if sha256_utf8_text_file(receipt_path) != orientation["receipt_sha256"]:
        raise PreflightError("bound orientation receipt bytes do not match the plan")
    if recipe.get("name") != "h3_mime_i2v" or receipt.get("recipe") != "h3_mime_i2v":
        raise PreflightError("bound orientation source names do not match H3 MIME")
    contract = recipe.get("contract")
    if not isinstance(contract, dict):
        raise PreflightError("bound orientation recipe has no contract")
    expected_recipe_contract = {
        "width": 864,
        "height": 480,
        "frames": 90,
        "fps": 24.0,
        "duration_s": 3.75,
        "requires_audio": True,
    }
    for key, value in expected_recipe_contract.items():
        if contract.get(key) != value:
            raise PreflightError(f"bound orientation recipe contract drifted at {key}")
    prompt = recipe.get("prompt")
    if not isinstance(prompt, dict):
        raise PreflightError("bound orientation recipe has no prompt graph")
    source_nodes = {node.get("class_type") for node in prompt.values() if isinstance(node, dict)}
    if source_nodes != set(plan["required_core_nodes"]):
        raise PreflightError("bound orientation source nodes do not match the plan")
    expected_receipt = {
        "status": "PASS (cold)",
        "gate_pass": True,
        "pass": False,
        "warm_pass": False,
        "peak_vram_gb": 7.28,
        "peak_host_ram_gb": 27.56,
        "physical_total_vram_gib": 15.9208984375,
        "reserve_vram_gib": 12.0,
        "frame_count": 90,
        "encoded_width": 864,
        "encoded_height": 480,
        "encoded_fps": 24.0,
        "audio_present": True,
        "config_run_count": 1,
    }
    for key, value in expected_receipt.items():
        if receipt.get(key) != value:
            raise PreflightError(f"bound orientation receipt drifted at {key}")
    if receipt.get("recipe_sha256") != orientation["recipe_sha256"]:
        raise PreflightError("bound orientation receipt does not bind the expected source recipe")
    lane = receipt.get("boot_lane")
    if not isinstance(lane, str) or "sage-free" not in lane or "no-pinned" not in lane or "reserve-12gb" not in lane:
        raise PreflightError("bound orientation receipt does not preserve its Sage-free reserve-pressure caveat")
    if receipt.get("audio_ear") != "pending" or receipt.get("audio_ear_source") != "pending_human":
        raise PreflightError("bound orientation receipt human-audio status drifted")
    return {
        "recipe_path": orientation["recipe"],
        "recipe_sha256": orientation["recipe_sha256"],
        "receipt_path": orientation["receipt"],
        "receipt_sha256": orientation["receipt_sha256"],
        "measurement": {
            "peak_vram_gib": receipt["peak_vram_gb"],
            "peak_host_ram_gib": receipt["peak_host_ram_gb"],
            "physical_total_vram_gib": receipt["physical_total_vram_gib"],
            "reserve_vram_gib": receipt["reserve_vram_gib"],
            "status": receipt["status"],
            "gate_pass": receipt["gate_pass"],
            "pass": receipt["pass"],
            "warm_pass": receipt["warm_pass"],
            "human_audio": receipt["audio_ear"],
        },
    }


def _graph_sha256(graph: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(dict(graph)))


def bound_source_recipe(plan: Mapping[str, Any], plan_id: str) -> dict[str, Any]:
    """Validate the code-owned graph that an enrolled physical plan may queue."""
    spec = _plan_spec(plan_id)
    repo_root = _validated_path(str(REPO_ROOT), "repository root", "directory")
    source_path = _validated_path(
        str(source_recipe_path_for_id(plan_id)), "bound physical source recipe", "file"
    )
    if not source_path.is_relative_to(repo_root):
        raise PreflightError("bound physical source recipe escaped the repository")
    if sha256_utf8_text_file(source_path) != spec["source_recipe_sha256"]:
        raise PreflightError("bound physical source recipe bytes do not match the enrolled registry")
    recipe = _read_json(source_path, "bound physical source recipe")
    if recipe.get("name") != spec["source_name"]:
        raise PreflightError("bound physical source recipe name drifted")
    graph = recipe.get("prompt")
    if not isinstance(graph, dict):
        raise PreflightError("bound physical source recipe has no prompt graph")
    node_seven = graph.get("7")
    inputs = node_seven.get("inputs") if isinstance(node_seven, dict) else None
    prompt = inputs.get("prompt") if isinstance(inputs, dict) else None
    if not isinstance(prompt, str) or not prompt:
        raise PreflightError("bound physical source recipe node 7 prompt is malformed")
    graph_sha256 = _graph_sha256(graph)
    prompt_sha256 = sha256_bytes(prompt.encode("utf-8"))
    if graph_sha256 != spec["source_graph_sha256"] or prompt_sha256 != spec["source_prompt_sha256"]:
        raise PreflightError("bound physical source graph or prompt drifted from the enrolled registry")
    contract = recipe.get("contract")
    if not isinstance(contract, dict):
        raise PreflightError("bound physical source recipe has no contract")
    expected_contract = {
        "width": 864,
        "height": 480,
        "frames": 90,
        "fps": 24.0,
        "duration_s": 3.75,
        "requires_audio": True,
    }
    for key, value in expected_contract.items():
        if contract.get(key) != value:
            raise PreflightError(f"bound physical source recipe contract drifted at {key}")
    source_nodes = {node.get("class_type") for node in graph.values() if isinstance(node, dict)}
    if source_nodes != set(plan["required_core_nodes"]):
        raise PreflightError("bound physical source nodes do not match the plan")
    if plan_id == MOTION_DEMO_PLAN_ID:
        sentinel_recipe = _read_json(
            source_recipe_path_for_id(SENTINEL_PLAN_ID), "bound sentinel source recipe"
        )
        sentinel_graph = sentinel_recipe.get("prompt")
        if not isinstance(sentinel_graph, dict):
            raise PreflightError("bound sentinel source recipe has no prompt graph")
        expected_motion_graph = json.loads(json.dumps(sentinel_graph, ensure_ascii=False))
        expected_motion_graph["7"]["inputs"]["prompt"] = prompt
        if graph != expected_motion_graph:
            raise PreflightError(
                "motion-demo graph must differ from the sentinel only at node 7 prompt text"
            )
    return {
        "recipe_path": spec["source_recipe"],
        "recipe_name": spec["source_name"],
        "recipe_sha256": spec["source_recipe_sha256"],
        "graph_sha256": graph_sha256,
        "prompt_sha256": prompt_sha256,
    }


def load_checked_in_plan(plan_id: str) -> tuple[dict[str, Any], str]:
    plan_path = plan_path_for_id(plan_id)
    plan = _read_json(plan_path, "plan")
    _validate_plan(plan, plan_id)
    return plan, sha256_utf8_text_file(plan_path)


def static_check(plan_id: str = SENTINEL_PLAN_ID) -> dict[str, Any]:
    _plan_spec(plan_id)
    contract = _read_json(CONTRACT_PATH, "contract")
    plan, plan_sha256 = load_checked_in_plan(plan_id)
    _validate_contract(contract)
    orientation = _bound_orientation_source(plan) if plan_id == SENTINEL_PLAN_ID else None
    source = bound_source_recipe(plan, plan_id)
    fixture = _validated_path(
        str(REPO_ROOT / "fixtures" / "scene_still.png"), "checked-in scene_still fixture", "file"
    )
    if sha256_file(fixture) != plan["video_contract"]["fixture_sha256"]:
        raise PreflightError("checked-in scene_still fixture does not match the declared plan")
    return {
        "status": "STATIC_CONTRACT_VALID",
        "scope": SCOPE,
        "plan_id": plan_id,
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "plan_sha256": plan_sha256,
        "fixture_sha256": sha256_file(fixture),
        "source_recipe": source,
        **({"orientation_only_source": orientation} if orientation is not None else {}),
        "network_or_gpu_actions": "none",
    }


def static_check_all() -> dict[str, Any]:
    """Validate every enrolled plan without selecting a profile or GPU."""
    results = {plan_id: static_check(plan_id) for plan_id in PLAN_IDS}
    return {
        "status": "STATIC_CONTRACT_VALID",
        "scope": SCOPE,
        "plan_ids": list(PLAN_IDS),
        "plans": results,
        "network_or_gpu_actions": "none",
    }


def hardware_inventory() -> dict[str, Any]:
    """Read the physical laptop hardware before a local profile exists.

    This is intentionally useful even when ComfyUI or any candidate model is
    absent.  It is not an enrollment or a render authorization.
    """
    static = static_check_all()["plans"][SENTINEL_PLAN_ID]
    return {
        "receipt_schema_version": 1,
        "kind": "physical_4060_8gb_hardware_inventory",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "HARDWARE_OBSERVED_NOT_ENROLLED",
        "scope": SCOPE,
        "contract_sha256": static["contract_sha256"],
        "preflight_script_sha256": sha256_file(Path(__file__).resolve()),
        "gpus": query_nvidia_smi(),
        "host_ram": host_ram_snapshot(),
        "next_action": "Write the redacted public hardware finding, commit only it, push it, then await a later written instruction.",
        "network_or_gpu_actions": READ_ONLY_GPU_INVENTORY_ACTIONS,
    }


def _validate_hardware_inventory_receipt(inventory: Mapping[str, Any]) -> None:
    """Fail closed on the raw immutable receipt before public redaction."""
    _require_exact_keys(
        inventory,
        {
            "receipt_schema_version",
            "kind",
            "checked_at_utc",
            "status",
            "scope",
            "contract_sha256",
            "preflight_script_sha256",
            "gpus",
            "host_ram",
            "next_action",
            "network_or_gpu_actions",
        },
        "local hardware inventory receipt",
    )
    if _require_int(inventory, "receipt_schema_version", "local hardware inventory receipt") != 1:
        raise PreflightError("local hardware inventory receipt schema drifted")
    if inventory.get("kind") != "physical_4060_8gb_hardware_inventory":
        raise PreflightError("local hardware inventory receipt kind drifted")
    if inventory.get("status") != "HARDWARE_OBSERVED_NOT_ENROLLED":
        raise PreflightError("local hardware inventory receipt status drifted")
    if inventory.get("scope") != SCOPE:
        raise PreflightError("local hardware inventory receipt scope drifted")
    checked_at = _require_string(inventory, "checked_at_utc", "local hardware inventory receipt")
    try:
        parsed_checked_at = dt.datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreflightError("local hardware inventory receipt timestamp is invalid") from exc
    if parsed_checked_at.tzinfo is None:
        raise PreflightError("local hardware inventory receipt timestamp must include a timezone")
    _require_string(inventory, "next_action", "local hardware inventory receipt")
    if inventory.get("network_or_gpu_actions") != READ_ONLY_GPU_INVENTORY_ACTIONS:
        raise PreflightError("local hardware inventory receipt action scope drifted")
    contract_sha256 = inventory.get("contract_sha256")
    script_sha256 = inventory.get("preflight_script_sha256")
    if not isinstance(contract_sha256, str) or not SHA256_RE.fullmatch(contract_sha256):
        raise PreflightError("local hardware inventory receipt contract SHA-256 is invalid")
    if not isinstance(script_sha256, str) or not SHA256_RE.fullmatch(script_sha256):
        raise PreflightError("local hardware inventory receipt preflight script SHA-256 is invalid")
    rows = inventory.get("gpus")
    if not isinstance(rows, list) or not rows:
        raise PreflightError("local hardware inventory receipt has no GPU rows")
    matching_rows: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise PreflightError("local hardware inventory receipt has a malformed GPU row")
        _require_exact_keys(
            row,
            {"uuid", "name", "memory_total_mib", "driver_version", "driver_model_current"},
            "local hardware inventory GPU",
        )
        _require_string(row, "uuid", "local hardware inventory GPU")
        _require_string(row, "name", "local hardware inventory GPU")
        if _require_int(row, "memory_total_mib", "local hardware inventory GPU") <= 0:
            raise PreflightError("local hardware inventory GPU memory total must be positive")
        _require_string(row, "driver_version", "local hardware inventory GPU")
        _require_string(row, "driver_model_current", "local hardware inventory GPU")
        if row.get("name") == "NVIDIA GeForce RTX 4060 Laptop GPU":
            matching_rows.append(row)
    if len(matching_rows) != 1:
        raise PreflightError("public hardware report requires exactly one RTX 4060 Laptop GPU row")
    selected = matching_rows[0]
    _require_string(selected, "uuid", "public hardware report GPU")
    memory_total_mib = _require_int(selected, "memory_total_mib", "public hardware report GPU")
    if not 7800 <= memory_total_mib <= 8192:
        raise PreflightError("public hardware report GPU is outside the declared physical 8 GB range")
    _require_string(selected, "driver_version", "public hardware report GPU")
    _require_string(selected, "driver_model_current", "public hardware report GPU")
    host_ram = inventory.get("host_ram")
    if not isinstance(host_ram, Mapping):
        raise PreflightError("local hardware inventory receipt has no host-RAM record")
    _require_exact_keys(host_ram, {"total_gib", "available_gib"}, "local hardware inventory host RAM")
    host_total_gib = host_ram.get("total_gib")
    if (
        isinstance(host_total_gib, bool)
        or not isinstance(host_total_gib, (int, float))
        or not math.isfinite(host_total_gib)
    ):
        raise PreflightError("public hardware report host total RAM is invalid")
    if host_total_gib < 30:
        raise PreflightError("public hardware report host RAM is below the declared 30 GiB minimum")


def _load_immutable_local_hardware_receipt(receipt_path: Path) -> tuple[dict[str, Any], str]:
    """Read only the raw local receipt just written by this isolated bench."""
    local_root = _validated_local_root(create=False)
    receipt_dir = local_root / "receipts"
    receipt_dir = _validated_path(
        str(receipt_dir), "physical 4060 local receipt directory", "directory"
    )
    if not _same_path(receipt_dir.parent, local_root):
        raise PreflightError("physical 4060 local receipt directory escaped the local state root")
    checked = _validated_path(
        str(receipt_path), "physical 4060 local hardware receipt", "file"
    )
    if not checked.is_relative_to(receipt_dir):
        raise PreflightError("physical 4060 local hardware receipt escaped the receipt directory")
    raw = checked.read_bytes()
    inventory = _read_json(checked, "physical 4060 local hardware receipt")
    if raw != canonical_bytes(inventory):
        raise PreflightError("physical 4060 local hardware receipt is not canonical immutable JSON")
    _validate_hardware_inventory_receipt(inventory)
    return inventory, sha256_bytes(raw)


def _public_hardware_report_payload(
    inventory: Mapping[str, Any], source_local_receipt_sha256: str
) -> dict[str, Any]:
    """Redact one validated local receipt into a commit-safe public report."""
    _validate_hardware_inventory_receipt(inventory)
    if not SHA256_RE.fullmatch(source_local_receipt_sha256):
        raise PreflightError("public hardware report source receipt SHA-256 is invalid")
    contract_sha256 = inventory["contract_sha256"]
    script_sha256 = inventory["preflight_script_sha256"]
    matching_rows = [
        row for row in inventory["gpus"]
        if row["name"] == "NVIDIA GeForce RTX 4060 Laptop GPU"
    ]
    selected = matching_rows[0]
    memory_total_mib = selected["memory_total_mib"]
    host_total_gib = inventory["host_ram"]["total_gib"]
    hardware = {
        "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU",
        "memory_total_mib": memory_total_mib,
        "host_ram_total_gib": host_total_gib,
    }
    return {
        "report_schema_version": 1,
        "kind": "physical_4060_8gb_hardware_inventory_public",
        "status": "HARDWARE_OBSERVED_NOT_ENROLLED",
        "scope": SCOPE,
        "contract_sha256": contract_sha256,
        "preflight_script_sha256": script_sha256,
        "source_local_receipt_sha256": source_local_receipt_sha256,
        "hardware": hardware,
        "privacy": {
            "raw_gpu_uuid": "omitted; retained only in the ignored eightgb_bench/local hardware receipt",
            "stable_gpu_identifier": "omitted; the source receipt digest is opaque outside the laptop-local evidence store",
        },
        "next_action": "Stop after committing this hardware report. It is not an enrollment, model-admission, server, or render authorization.",
    }


def _public_report_equivalent(existing: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    """Allow repeat inventory without rewriting the first immutable public proof."""
    required = {
        "report_schema_version",
        "kind",
        "status",
        "scope",
        "contract_sha256",
        "preflight_script_sha256",
        "source_local_receipt_sha256",
        "hardware",
        "privacy",
        "next_action",
    }
    _require_exact_keys(existing, required, "existing public hardware report")
    if existing.get("report_schema_version") != 1:
        raise PreflightError("existing public hardware report schema drifted")
    source = existing.get("source_local_receipt_sha256")
    if not isinstance(source, str) or not SHA256_RE.fullmatch(source):
        raise PreflightError("existing public hardware report source receipt SHA-256 is invalid")
    existing_without_source = dict(existing)
    candidate_without_source = dict(candidate)
    existing_without_source.pop("source_local_receipt_sha256")
    candidate_without_source.pop("source_local_receipt_sha256")
    return canonical_bytes(existing_without_source) == canonical_bytes(candidate_without_source)


def write_public_hardware_report(receipt_path: Path) -> Path:
    """Write one deterministic, redacted report in the tracked reports namespace."""
    inventory, source_sha256 = _load_immutable_local_hardware_receipt(receipt_path)
    report = _public_hardware_report_payload(inventory, source_sha256)
    reports_root = _validated_public_reports_root()
    path = reports_root / PUBLIC_REPORT_REPO_PATH.name
    serialized = canonical_bytes(report)
    if path.exists():
        existing = _validated_path(str(path), "physical 4060 public hardware report", "file")
        raw_existing = existing.read_bytes()
        existing_payload = _read_json(existing, "existing public hardware report")
        if raw_existing != canonical_bytes(existing_payload):
            raise PreflightError("existing public hardware report is not canonical immutable JSON")
        if _public_report_equivalent(existing_payload, report):
            return existing
        raise PreflightError(f"public hardware report path already has different bytes: {existing}")
    try:
        with path.open("xb") as handle:
            handle.write(serialized)
    except FileExistsError:
        existing = _validated_path(str(path), "physical 4060 public hardware report", "file")
        raw_existing = existing.read_bytes()
        existing_payload = _read_json(existing, "existing public hardware report")
        if raw_existing == canonical_bytes(existing_payload) and _public_report_equivalent(existing_payload, report):
            return existing
        raise PreflightError(f"public hardware report path already has different bytes: {existing}")
    except OSError as exc:
        raise PreflightError(f"cannot write public hardware report: {path}: {exc}") from exc
    return path


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
    _require_exact_keys(paths, {"python", "comfyui_root", "ffprobe", "model_roots"}, "profile.paths")
    roots = paths.get("model_roots")
    if not isinstance(roots, dict):
        raise PreflightError("profile.paths.model_roots must be an object")
    _require_exact_keys(roots, {"diffusion_models", "text_encoders", "vae"}, "profile.paths.model_roots")
    identity = profile.get("identity")
    if not isinstance(identity, dict):
        raise PreflightError("profile.identity must be an object")
    _require_exact_keys(
        identity,
        {
            "python_sha256", "python_major_minor", "comfyui_git_commit",
            "comfyui_main_py_sha256", "ffprobe_sha256", "model_sha256s",
        },
        "profile.identity",
    )
    for key in ("python_sha256", "comfyui_main_py_sha256", "ffprobe_sha256"):
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


def _validated_ffprobe(value: str, label: str) -> Path:
    path = _validated_path(value, label, "file")
    if path.name.casefold() != "ffprobe.exe":
        raise PreflightError(f"{label} must name ffprobe.exe")
    return path


def _profile_paths(profile: Mapping[str, Any]) -> dict[str, Path]:
    paths = profile["paths"]
    roots = paths["model_roots"]
    return {
        "python": _validated_path(paths["python"], "profile.paths.python", "file"),
        "comfyui_root": _validated_path(paths["comfyui_root"], "profile.paths.comfyui_root", "directory"),
        "ffprobe": _validated_ffprobe(paths["ffprobe"], "profile.paths.ffprobe"),
        "diffusion_models": _validated_path(roots["diffusion_models"], "profile model root diffusion_models", "directory"),
        "text_encoders": _validated_path(roots["text_encoders"], "profile model root text_encoders", "directory"),
        "vae": _validated_path(roots["vae"], "profile model root vae", "directory"),
    }


def _running_python_major_minor() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


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


def _preflight_payload(
    static: Mapping[str, Any],
    profile_id: str,
    plan_id: str,
    profile_path: Path,
    blockers: list[dict[str, str]],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "receipt_schema_version": 2,
        "kind": "physical_4060_8gb_inventory_preflight",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": READY_STATUS if not blockers else blockers[0]["code"],
        "scope": SCOPE,
        "profile_id": profile_id,
        "plan_id": plan_id,
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
        "network_or_gpu_actions": READ_ONLY_GPU_INVENTORY_ACTIONS,
    }


def preflight(profile_id: str, plan_id: str = SENTINEL_PLAN_ID) -> dict[str, Any]:
    # Validate the selected ID before even examining a local-state directory.
    # An arbitrary ID must never redirect this command toward another profile,
    # plan, source graph, or hardware probe.
    _profile_path(profile_id)
    _plan_spec(plan_id)
    static = static_check(plan_id)
    local_root = _validated_local_root(create=False)
    profile_path = _validated_path(
        str(_profile_path(profile_id, local_root)), "laptop-local profile", "file"
    )
    profile = _read_json(profile_path, "laptop-local profile")
    _validate_profile(profile, profile_id)
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
    if blockers:
        return _preflight_payload(static, profile_id, plan_id, profile_path, blockers, observed)

    identity = profile["identity"]
    declared_python = _validated_path(profile["paths"]["python"], "profile.paths.python", "file")
    running_python = _validated_path(str(Path(sys.executable)), "executing Python", "file")
    python_major_minor = _running_python_major_minor()
    python_observed = _observed_file(running_python)
    observed["python"] = {**python_observed, "major_minor": python_major_minor}
    if not _same_path(declared_python, running_python):
        blockers.append(
            _block(
                "BLOCKED_EXECUTING_PYTHON_PATH_DRIFT",
                f"profile declares {declared_python}; executing {running_python}",
            )
        )
        return _preflight_payload(static, profile_id, plan_id, profile_path, blockers, observed)
    if python_major_minor not in profile["policy"]["allowed_python_major_minors"]:
        blockers.append(_block("BLOCKED_PYTHON_VERSION", f"observed {python_major_minor}"))
    _identity_check(blockers, "PYTHON_SHA256", identity["python_sha256"], python_observed["sha256"])
    _identity_check(blockers, "PYTHON_VERSION", identity["python_major_minor"], python_major_minor)

    paths = _profile_paths(profile)
    ffprobe_observed = _observed_file(paths["ffprobe"])
    observed["ffprobe"] = ffprobe_observed
    _identity_check(
        blockers, "FFPROBE_SHA256", identity["ffprobe_sha256"], ffprobe_observed["sha256"]
    )
    if not blockers:
        try:
            version = _run_readonly([str(paths["ffprobe"]), "-version"], "profile ffprobe")
        except PreflightError as exc:
            blockers.append(_block("BLOCKED_FFPROBE_HEALTH", str(exc)))
        else:
            first_line = version.splitlines()[0] if version else ""
            if not first_line.casefold().startswith("ffprobe version "):
                blockers.append(
                    _block("BLOCKED_FFPROBE_HEALTH", "ffprobe -version did not identify ffprobe")
                )
            else:
                observed["ffprobe"]["version"] = first_line
    if blockers:
        return _preflight_payload(static, profile_id, plan_id, profile_path, blockers, observed)
    main_py = _validated_child_file(paths["comfyui_root"], "main.py", "declared ComfyUI main.py")
    if main_py is None:
        blockers.append(_block("BLOCKED_COMFYUI_MAIN_MISSING", f"missing {paths['comfyui_root'] / 'main.py'}"))
        observed["comfyui"] = {"root": str(paths["comfyui_root"]), "main_py": None}
    else:
        main_observed = _observed_file(main_py)
        observed["comfyui"] = {"root": str(paths["comfyui_root"]), "main_py": main_observed}
        _identity_check(blockers, "COMFYUI_MAIN_SHA256", identity["comfyui_main_py_sha256"], main_observed["sha256"])
        try:
            git_observed = _git_identity(paths["comfyui_root"])
        except PreflightError as exc:
            blockers.append(_block("BLOCKED_COMFYUI_GIT_IDENTITY", str(exc)))
        else:
            observed["comfyui"].update(git_observed)
            _identity_check(blockers, "COMFYUI_COMMIT", identity["comfyui_git_commit"], git_observed["commit"])
            if profile["policy"]["require_clean_comfyui_git"] and git_observed["dirty"]:
                blockers.append(_block("BLOCKED_COMFYUI_DIRTY", "declared ComfyUI checkout has uncommitted changes"))

    plan, _ = load_checked_in_plan(plan_id)
    model_observed: dict[str, Any] = {}
    for asset in plan["engine"]["required_assets"]:
        category = asset["category"]
        filename = asset["filename"]
        key = f"{category}/{filename}"
        path = _validated_child_file(paths[category], filename, f"declared model {key}")
        if path is None:
            blockers.append(_block("BLOCKED_MODEL_MISSING", key))
            model_observed[key] = {"path": str(paths[category] / filename), "exists": False}
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
    return _preflight_payload(static, profile_id, plan_id, profile_path, blockers, observed)


def write_receipt(payload: Mapping[str, Any]) -> Path:
    local_root = _validated_local_root(create=True)
    receipt_dir = local_root / "receipts"
    if not receipt_dir.exists():
        try:
            receipt_dir.mkdir(parents=False, exist_ok=False)
        except OSError as exc:
            raise PreflightError(f"cannot create physical 4060 receipt directory: {exc}") from exc
    receipt_dir = _validated_path(str(receipt_dir), "physical 4060 receipt directory", "directory")
    if receipt_dir.parent != local_root:
        raise PreflightError("physical 4060 receipt directory escaped the local state root")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload_digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()[:12]
    nonce = secrets.token_hex(6)
    path = receipt_dir / f"preflight-{now}-{payload_digest}-{nonce}.json"
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
    subparsers.add_parser("static-check", help="validate the checked-in physical 4060 contract and every enrolled plan")
    hardware_parser = subparsers.add_parser(
        "hardware-inventory", help="read only the installed GPU and RAM; no profile or server is needed"
    )
    hardware_parser.add_argument(
        "--write-receipt",
        action="store_true",
        help="write an immutable receipt beneath eightgb_bench/local only",
    )
    hardware_parser.add_argument(
        "--write-public-report",
        action="store_true",
        help="also write one redacted, commit-ready hardware report beneath eightgb_bench/reports",
    )
    preflight_parser = subparsers.add_parser("preflight", help="inspect one fixed laptop-local enrolled profile")
    preflight_parser.add_argument("--profile", required=True, help="only physical-rtx4060-8gb is enrolled")
    preflight_parser.add_argument(
        "--plan", choices=PLAN_IDS, default=SENTINEL_PLAN_ID,
        help="only a checked-in enrolled physical 4060 plan",
    )
    preflight_parser.add_argument("--write-receipt", action="store_true", help="write an immutable receipt beneath eightgb_bench/local only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "static-check":
            print(format_json(static_check_all()), end="")
            return 0
        if args.command == "hardware-inventory":
            payload = hardware_inventory()
            if args.write_public_report:
                local_receipt_path = write_receipt(payload)
                public_report_path = write_public_hardware_report(local_receipt_path)
                print(
                    format_json(
                        {
                            "status": "HARDWARE_OBSERVED_NOT_ENROLLED",
                            "scope": SCOPE,
                            "public_report_path": PUBLIC_REPORT_REPO_PATH.as_posix(),
                            "public_report_sha256": sha256_file(public_report_path),
                            "next_action": "Commit only the redacted public report, push it, report the commit hash, then stop.",
                        }
                    ),
                    end="",
                )
                return 0
            if args.write_receipt:
                payload = dict(payload)
                payload["receipt_path"] = str(write_receipt(payload))
            print(format_json(payload), end="")
            return 0
        if args.command == "preflight":
            payload = preflight(args.profile, args.plan)
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
