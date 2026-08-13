#!/usr/bin/env python3
"""Fail-closed lab campaign for the six H3 canonical-canvas recipes.

The default invocation is a read-only JSON runbook.  Only ``--run`` executes.
Every model render is delegated to ``run_recipe.py`` so this orchestrator never
acquires or bypasses the lab GPU lease itself.  Each recipe runs cold, then
immediately warm on the same owned server; the warm child receives ``--shutdown``.

The lifecycle is an append-only, hash-chained JSONL ledger.  No OTR path is
read or written by this module.
"""

from __future__ import annotations

import argparse
import configparser
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import psutil

try:
    import h3_manager_offline_guard as manager_guard
except ModuleNotFoundError:  # Package import under pytest.
    from scratch import h3_manager_offline_guard as manager_guard


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUTS = ROOT / "outputs"
CAMPAIGN_RESULTS = RESULTS / "h3_canonical_canvas_campaign"
LIFECYCLE = CAMPAIGN_RESULTS / "lifecycle.jsonl"
LOG_ROOT = CAMPAIGN_RESULTS / "server_logs"
RUNNER = ROOT / "run_recipe.py"
LAB_LOCKS = ROOT / "lab_locks.py"
BOOT_CMD = ROOT / "boot_lab_server.cmd"
TEST_BOOT_CMD = ROOT / "boot_h3_manager_offline_test.cmd"
MANAGER_GUARD = ROOT / "scratch" / "h3_manager_offline_guard.py"
BUILDER = ROOT / "scratch" / "build_h3_canonical_canvas_ladders.py"
CAMPAIGN_SOURCE = Path(__file__).resolve()
ACTUAL_MANAGER_CONFIG = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini"
)
LAB_MANAGER_CONFIG = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\user\__manager\config.ini"
)
ACTUAL_USER_DIRECTORY = Path(r"C:\Users\jeffr\Documents\ComfyUI")
COMFYUI_MAIN = Path(
    r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py"
)
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")

GPU_LOCK = ROOT / ".gpu.lock"
SUITE_LOCK = ROOT / ".suite.lock"
SERVER_PID = ROOT / ".server.pid"
QUEUE_QUARANTINE = ROOT / ".queue.quarantine.json"
IDLE_GATE_SIDECAR = ROOT / ".server.idle-gate.json"
LAB_PORT = 8199
EXPECTED_BOOT_LANE = "lab-8199, sage-free, manager-offline-test, no-pinned"
CAMPAIGN_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,80}")
EXPECTED_STANDALONE_CACHE_SOURCES = {
    "execution.py",
    "comfy_execution/caching.py",
    "comfy_extras/nodes_custom_sampler.py",
    "nodes.py",
    "comfy_execution/graph.py",
    "comfy_execution/graph_utils.py",
    "comfy_api/latest/_io.py",
}
EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS = [
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
]
ELEVATED_BASELINE_THRESHOLD_GB = 2.0
ELEVATED_BASELINE_STAMP = (
    "elevated-baseline lane, operator-authorized 2026-08-10"
)
EXPECTED_REDACTED_WORKLOAD_PROCESS_SCHEMA = [
    "pid",
    "process_create_time",
    "process_basename",
    "executable_basename",
    "target_basename",
    "matched_markers",
    "match_basis",
    "argv_sha256",
]
EXPECTED_CURRENT_RUNNER_EXCLUSION_SCHEMA = [
    "pid",
    "process_create_time",
    "resolved_runner_path",
    "narrowly_verified",
    "excluded_pid_only",
    "process_identity",
    "verified_windows_venv_launcher",
    "expected_excluded_process_count",
]
EXPECTED_VERIFIED_WINDOWS_VENV_LAUNCHER_SCHEMA = [
    "pid",
    "process_create_time",
    "expected_launcher_path",
    "direct_child_pid",
    "direct_parent_verified",
    "launcher_identity_live",
    "child_identity_live",
    "argv_tail_matches_child",
    "both_exact_runner_target",
    "child_executable_differs",
    "creation_delta_s",
    "narrowly_verified",
    "excluded_pid_only",
    "process_identity",
]
EXPECTED_EXCLUDED_CURRENT_RUNNER_ROW_SCHEMA = [
    "pid",
    "process_create_time",
    "reason",
]
EXPECTED_OWNED_LAB_SERVER_EXCLUSION_SCHEMA = [
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
EXPECTED_VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA = [
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
EXPECTED_EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA = [
    "pid",
    "process_create_time",
    "reason",
]


def expected_known_workload_classifier_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "token-aware-positive-known-workload-classifier",
        "python_script_markers": ["main.py", "run_recipe.py"],
        "other_markers": [
            marker
            for marker in EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS
            if marker not in {"main.py", "run_recipe.py"}
        ],
        "positive_match_sources": [
            "process_basename",
            "executable_basename",
            "actual_python_script_or_module_target",
        ],
        "arbitrary_later_argv_values_ignored": True,
        "exact_exclusions_run_before_classifier": True,
        "optional_current_windows_venv_launcher_exclusion": (
            "one direct parent only; exact sys.prefix/Scripts/python.exe; launcher "
            "argv[1:] equals real child argv[1:]; both target run_recipe.py; live "
            "PID/create-times; real child executable differs; ordered creation delta <=5s"
        ),
        "current_runner_exclusion_schema": list(
            EXPECTED_CURRENT_RUNNER_EXCLUSION_SCHEMA
        ),
        "verified_windows_venv_launcher_schema": list(
            EXPECTED_VERIFIED_WINDOWS_VENV_LAUNCHER_SCHEMA
        ),
        "excluded_current_runner_row_schema": list(
            EXPECTED_EXCLUDED_CURRENT_RUNNER_ROW_SCHEMA
        ),
        "unreadable_or_unmatched_python_is_advisory": True,
        "redacted_process_schema": list(
            EXPECTED_REDACTED_WORKLOAD_PROCESS_SCHEMA
        ),
        "argv_sha256_bytes": "UTF-8 canonical JSON argv list",
    }


def expected_operator_idle_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "operator-authorized-desktop-baseline-policy",
        "preboot_baseline_advisory_threshold_mib": 3072.0,
        "preboot_baseline_threshold_gating": False,
        "elevated_baseline_threshold_mib": 2048.0,
        "elevated_baseline_condition": (
            "recorded baseline is strictly greater than 2.0 GiB"
        ),
        "elevated_baseline_stamp": ELEVATED_BASELINE_STAMP,
        "known_render_compute_processes_block": True,
        "utilization_descriptors_non_gating": True,
        "pair_cold_warm_baseline_drift_advisory_gib": 0.5,
        "pair_drift_threshold_gating": False,
        "pair_drift_condition": (
            "compare each same-identity warm baseline_vram_gb to the prior cold "
            "leg; record absolute drift and threshold exceedance without blocking"
        ),
        "prequeue_known_workload_scan_contract": {
            "schema_version": 1,
            "kind": "per-leg-immediate-prequeue-known-workload-scan-contract",
            "timing": (
                "every cold and warm leg, after queue-idle and baseline/drift "
                "measurements, immediately before POST /prompt"
            ),
            "model_workload_markers": list(
                EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS
            ),
            "known_workload_classifier": (
                expected_known_workload_classifier_contract()
            ),
            "exact_exclusions": [
                (
                    "current run_recipe PID + create time + resolved "
                    "run_recipe.py argv"
                ),
                (
                    "optional one-hop direct Windows venv launcher at "
                    "sys.prefix/Scripts/python.exe with identical argv tail, exact "
                    "runner targets, live PID/create-times, distinct child executable, "
                    "and <=5s creation delta"
                ),
                (
                    "owned port-8199 serving PID + create time + exact "
                    "self-reported server argv (with only its Python "
                    "interpreter prefix permitted)"
                ),
                (
                    "optional one-hop direct owned-server Windows venv launcher at "
                    "sys.prefix/Scripts/python.exe with identical argv tail, both "
                    "exact validated self-reported server argv, live PID/create-times, "
                    "distinct serving-child executable, and <=5s creation delta"
                ),
            ],
            "owned_lab_server_exclusion_schema": list(
                EXPECTED_OWNED_LAB_SERVER_EXCLUSION_SCHEMA
            ),
            "verified_owned_server_windows_venv_launcher_schema": list(
                EXPECTED_VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA
            ),
            "excluded_owned_lab_server_row_schema": list(
                EXPECTED_EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA
            ),
            "owned_server_launcher_boot_lineage": (
                "not inferred when unavailable; only the exact serving PID direct "
                "parent may be excluded, never arbitrary ancestors"
            ),
            "python_without_readable_argv_blocks": False,
            "advisory_unreadable_processes_retained": True,
            "listener_binding_required_before_and_after_scan": True,
            "warm_leg_scan_required": True,
            "blocking_condition": "any known render/compute workload is live",
        },
        "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
        "authorized_on": "2026-08-10",
    }


def load_runner_verifier(runner_path: Path) -> Any:
    """Load the hash-bound local runner's retained-evidence validators."""

    module_name = "_h3_canonical_receipt_runner"
    spec = importlib.util.spec_from_file_location(module_name, runner_path)
    if spec is None or spec.loader is None:
        raise CampaignError(f"cannot load runner verifier: {runner_path}")
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
    for name in (
        "current_runner_exclusion_validation_errors",
        "owned_lab_server_exclusion_validation_errors",
        "gpu_idle_gate_validation_errors",
        "prequeue_known_workload_scan_validation_errors",
        "shutdown_lab_server",
    ):
        if not callable(getattr(module, name, None)):
            raise CampaignError(f"run_recipe.py no longer exposes verifier {name}")
    return module

RECIPE_PINS: tuple[tuple[str, str, str, int], ...] = (
    (
        "h3_i2v_canonical_832x480_f107",
        "00cf050221589d83e814c06f395b48ed9ca6f86d875d338d7dacf8eeb42c4e88",
        "i2v",
        107,
    ),
    (
        "h3_i2v_canonical_832x480_f192",
        "9aa2a3552abb22c8261fd855443e74646b09fcf67d77459b3987f7b5ff4bc1eb",
        "i2v",
        192,
    ),
    (
        "h3_i2v_canonical_832x480_f277",
        "441c47228a06e8cc3c8b6fc9b92a26d6042da7b546205bc7495485fce85bb7a0",
        "i2v",
        277,
    ),
    (
        "h3_r2v_refaudio_canonical_832x480_f107_seed43",
        "fc578f336938874f7c7e7833e9394654aa0ed245e95121fb6ace2991208acb99",
        "r2v_refaudio",
        107,
    ),
    (
        "h3_r2v_refaudio_canonical_832x480_f192_seed43",
        "a6666b11343137dc1d87d4d901066ccbb4b42b435d7f9d766983db2ec3469a4e",
        "r2v_refaudio",
        192,
    ),
    (
        "h3_r2v_refaudio_canonical_832x480_f277_seed43",
        "aef0c1f3e682dfa888c8962e2e181d8c08afb420c1666078caa8448f90477023",
        "r2v_refaudio",
        277,
    ),
)


class CampaignError(RuntimeError):
    """The campaign could not prove a required invariant."""


@dataclass(frozen=True)
class Layout:
    root: Path = ROOT
    results: Path = RESULTS
    outputs: Path = OUTPUTS
    lifecycle: Path = LIFECYCLE
    runner: Path = RUNNER
    lab_locks: Path = LAB_LOCKS
    boot_cmd: Path = BOOT_CMD
    test_boot_cmd: Path = TEST_BOOT_CMD
    manager_guard_path: Path = MANAGER_GUARD
    builder: Path = BUILDER
    campaign_source: Path = CAMPAIGN_SOURCE
    actual_manager_config: Path = ACTUAL_MANAGER_CONFIG
    lab_manager_config: Path = LAB_MANAGER_CONFIG
    actual_user_directory: Path = ACTUAL_USER_DIRECTORY
    comfyui_main: Path = COMFYUI_MAIN
    python: Path = PYTHON
    gpu_lock: Path = GPU_LOCK
    suite_lock: Path = SUITE_LOCK
    server_pid: Path = SERVER_PID
    queue_quarantine: Path = QUEUE_QUARANTINE
    idle_gate_sidecar: Path = IDLE_GATE_SIDECAR


DEFAULT_LAYOUT = Layout()


@dataclass(frozen=True)
class RecipeSpec:
    name: str
    sha256: str
    mode: str
    frames: int
    path: Path
    prefix: str
    fixture_hashes: Mapping[str, str]


@dataclass(frozen=True)
class ChildOutcome:
    returncode: int
    runner_pid: int | None = None
    runner_create_time: float | None = None
    descendant_server_instances: tuple[Mapping[str, Any], ...] = ()
    ownership_monitor_errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "runner_pid": self.runner_pid,
            "runner_create_time": self.runner_create_time,
            "descendant_server_instances": [
                dict(value) for value in self.descendant_server_instances
            ],
            "ownership_monitor_errors": list(self.ownership_monitor_errors),
        }


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def stable_identity(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(dict(value)))


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def stable_file(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    lexical = Path(os.path.abspath(os.fspath(path)))
    if not os.path.lexists(lexical):
        raise CampaignError(f"missing {label}: {lexical}")
    if _is_reparse(lexical):
        raise CampaignError(f"{label} is a symlink or reparse point: {lexical}")
    before = lexical.stat()
    if not lexical.is_file():
        raise CampaignError(f"{label} is not a regular file: {lexical}")
    raw = lexical.read_bytes()
    after = lexical.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise CampaignError(f"{label} changed during read: {lexical}")
    return raw, {
        "path": str(lexical),
        "bytes": len(raw),
        "mtime_ns": after.st_mtime_ns,
        "sha256": sha256_bytes(raw),
    }


def strict_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw, _ = stable_file(path, label)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CampaignError(f"{label} has a UTF-8 BOM: {path}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise CampaignError(f"{label} is not a JSON object: {path}")
    return value, raw


def load_recipe_specs(layout: Layout = DEFAULT_LAYOUT) -> list[RecipeSpec]:
    specs: list[RecipeSpec] = []
    for name, expected_hash, mode, frames in RECIPE_PINS:
        path = layout.root / "recipes" / f"{name}.json"
        recipe, raw = strict_json(path, f"recipe {name}")
        actual_hash = sha256_bytes(raw)
        if actual_hash != expected_hash:
            raise CampaignError(
                f"recipe hash drift for {name}: expected {expected_hash}, found {actual_hash}"
            )
        if recipe.get("name") != name or recipe.get("blocked") is not False:
            raise CampaignError(f"recipe identity/block state changed: {name}")
        contract = recipe.get("contract") or {}
        expected_contract = (mode, 832, 480, frames, 24.0)
        actual_contract = (
            contract.get("mode"),
            contract.get("width"),
            contract.get("height"),
            contract.get("frames"),
            contract.get("fps"),
        )
        if actual_contract != expected_contract:
            raise CampaignError(
                f"recipe contract drift for {name}: {actual_contract!r}"
            )
        if contract.get("required_boot_lane") != EXPECTED_BOOT_LANE:
            raise CampaignError(f"recipe no-pinned H3 lane drift: {name}")
        requirements = recipe.get("receipt_requirements") or {}
        expected_manager_gate = {
            "required": True,
            "authoritative_source": "pair-unique server log",
            "required_announcement": "[ComfyUI-Manager] network_mode: offline",
            "required_announcement_count": 1,
            "must_precede_startup_completion": True,
            "must_precede_first_prompt": True,
            "network_markers_required_empty": True,
            "mutation_markers_required_empty": True,
        }
        expected_idle_gate = {
            "cold_required": True,
            "warm_policy": (
                "reuse exact owned cold server; no fresh idle sampling claimed"
            ),
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
                EXPECTED_REDACTED_WORKLOAD_PROCESS_SCHEMA
            ),
            "desktop_graphics_signals_retained_but_not_required": True,
            "required_driver_model": "WDDM",
            "display_active_allowed_measured_states": ["Disabled", "Enabled"],
            "display_active_recorded_non_gating": True,
        }
        expected_operator_idle_policy = {
            "baseline_vram_recorded_advisory": True,
            "baseline_numeric_rejection": False,
            "pair_cold_warm_baseline_drift_recorded_advisory": True,
            "pair_baseline_drift_numeric_rejection": False,
            "elevated_baseline_threshold_gb": ELEVATED_BASELINE_THRESHOLD_GB,
            "elevated_baseline_threshold_operator": ">",
            "elevated_baseline_stamp": ELEVATED_BASELINE_STAMP,
            "per_leg_immediate_prequeue_known_workload_scan_required": True,
            "optional_verified_direct_owned_server_windows_venv_launcher_exclusion": True,
            "owned_server_windows_venv_launcher_exclusion_max_count": 1,
            "owned_server_excluded_process_count_allowed": [1, 2],
            "owned_lab_server_exclusion_schema": list(
                EXPECTED_OWNED_LAB_SERVER_EXCLUSION_SCHEMA
            ),
            "verified_owned_server_windows_venv_launcher_schema": list(
                EXPECTED_VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA
            ),
            "excluded_owned_lab_server_row_schema": list(
                EXPECTED_EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA
            ),
            "unreadable_unknown_python_advisory_non_gating": True,
            "redacted_positive_workload_evidence_required": True,
            "absolute_and_net_peak_required": True,
            "net_peak_definition": "peak_vram_gb - baseline_vram_gb",
        }
        if requirements.get("manager_offline_gate") != expected_manager_gate:
            raise CampaignError(f"recipe Manager offline receipt gate drift: {name}")
        if requirements.get("preboot_gpu_idle_gate") != expected_idle_gate:
            raise CampaignError(f"recipe hardened idle receipt gate drift: {name}")
        if requirements.get("operator_idle_policy") != expected_operator_idle_policy:
            raise CampaignError(f"recipe operator idle policy drift: {name}")
        if requirements.get("completion_timeout_s") != {
            107: 1_800,
            192: 3_600,
            277: 5_400,
        }[frames]:
            raise CampaignError(f"recipe completion timeout drift: {name}")
        prompt = recipe.get("prompt") or {}
        save_nodes = [
            node
            for node in prompt.values()
            if isinstance(node, dict) and node.get("class_type") == "SaveVideo"
        ]
        if len(save_nodes) != 1:
            raise CampaignError(f"recipe does not have exactly one SaveVideo: {name}")
        prefix = (save_nodes[0].get("inputs") or {}).get("filename_prefix")
        if prefix != f"{name}_out":
            raise CampaignError(f"recipe output prefix drift for {name}: {prefix!r}")
        fixture_hashes = (recipe.get("topology_contract") or {}).get(
            "fixture_hashes"
        )
        if not isinstance(fixture_hashes, dict) or not fixture_hashes:
            raise CampaignError(f"recipe fixture hash contract missing: {name}")
        specs.append(
            RecipeSpec(
                name=name,
                sha256=actual_hash,
                mode=mode,
                frames=frames,
                path=path,
                prefix=prefix,
                fixture_hashes=dict(fixture_hashes),
            )
        )
    return specs


def manager_config_snapshot(path: Path, label: str) -> dict[str, Any]:
    raw, snapshot = stable_file(path, label)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CampaignError(f"{label} has a UTF-8 BOM")
    parser = configparser.ConfigParser()
    try:
        parser.read_string(raw.decode("utf-8"))
    except (UnicodeDecodeError, configparser.Error) as exc:
        raise CampaignError(f"cannot parse {label}: {exc}") from exc
    mode = parser.get("default", "network_mode", fallback="").strip().lower()
    if mode != "offline":
        raise CampaignError(
            f"{label} network_mode must be offline, found {mode!r}: {path}"
        )
    return {**snapshot, "network_mode": mode, "section": "default"}


def manager_evidence(layout: Layout = DEFAULT_LAYOUT) -> dict[str, Any]:
    actual = manager_config_snapshot(
        layout.actual_manager_config, "actual effective Manager config"
    )
    lab = manager_config_snapshot(layout.lab_manager_config, "lab Manager config")
    if os.path.normcase(actual["path"]) == os.path.normcase(lab["path"]):
        raise CampaignError("actual and lab Manager configs unexpectedly alias")
    return {"actual": actual, "lab": lab, "both_offline": True}


def require_same_manager_evidence(
    baseline: Mapping[str, Any], current: Mapping[str, Any], label: str
) -> None:
    for key in ("actual", "lab"):
        before = baseline.get(key) or {}
        after = current.get(key) or {}
        if (
            before.get("path") != after.get("path")
            or before.get("sha256") != after.get("sha256")
            or after.get("network_mode") != "offline"
        ):
            raise CampaignError(f"Manager {key} config changed at {label}")


def source_evidence(layout: Layout = DEFAULT_LAYOUT) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for label, path in (
        ("runner", layout.runner),
        ("lab_locks", layout.lab_locks),
        ("boot_cmd", layout.boot_cmd),
        ("test_boot_cmd", layout.test_boot_cmd),
        ("manager_guard", layout.manager_guard_path),
        ("builder", layout.builder),
        ("campaign", layout.campaign_source),
    ):
        raw, snapshot = stable_file(path, label)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CampaignError(f"{label} source has a UTF-8 BOM")
        evidence[label] = snapshot
    boot_text = stable_file(layout.boot_cmd, "boot command")[0].decode(
        "utf-8", errors="strict"
    )
    executable_lines = [
        line
        for line in boot_text.splitlines()
        if not line.lstrip().lower().startswith(("rem ", "::"))
    ]
    normalized = re.sub(r"\^\s*\r?\n\s*", " ", "\n".join(executable_lines))
    if normalized.lower().count("--user-directory") != 1:
        raise CampaignError("boot command must have one --user-directory")
    expected_user = str(layout.actual_user_directory).lower()
    if f"--user-directory {expected_user}" not in normalized.lower():
        raise CampaignError("boot command actual user-directory drift")
    if str(layout.comfyui_main).lower() not in normalized.lower():
        raise CampaignError("boot command ComfyUI main.py drift")
    if "--disable-all-custom-nodes" not in normalized:
        raise CampaignError("boot command no longer disables all custom nodes")
    whitelist = re.search(
        r"--whitelist-custom-nodes\s+(.+?)\s+%EXTRA_ARGS%", normalized
    )
    if not whitelist:
        raise CampaignError("boot command whitelist cannot be proved")
    whitelist_nodes = whitelist.group(1).split()
    if whitelist_nodes != ["ComfyUI-GGUF", "ComfyUI-KJNodes"]:
        raise CampaignError(f"boot command whitelist drift: {whitelist_nodes}")
    if "--use-sage-attention" in normalized.lower():
        raise CampaignError("boot command execution path enables global SageAttention")

    test_boot = stable_file(layout.test_boot_cmd, "Manager test boot command")[
        0
    ].decode("utf-8", errors="strict")
    required_test_tokens = (
        'if not "%LAB_MANAGER_OFFLINE_PROBE%"=="1"',
        'if not "%HF_TOKEN%"=="offline-disabled"',
        'if not "%HUGGING_FACE_HUB_TOKEN%"=="offline-disabled"',
        'if not "%HF_HUB_OFFLINE%"=="1"',
        'if not "%TRANSFORMERS_OFFLINE%"=="1"',
        'if not "%PIP_NO_INDEX%"=="1"',
        'if not "%PIP_DISABLE_PIP_VERSION_CHECK%"=="1"',
        'if not "%UV_OFFLINE%"=="1"',
        'if not "%GIT_TERMINAL_PROMPT%"=="0"',
        "if defined HUGGINGFACE_HUB_TOKEN",
        "if defined HF_API_TOKEN",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes ComfyUI-GGUF ComfyUI-KJNodes ComfyUI-Manager",
        '>> "%LAB_MANAGER_PROBE_LOG%" 2>&1',
    )
    if any(token not in test_boot for token in required_test_tokens):
        raise CampaignError("test-only Manager boot contract drifted")
    test_executable = "\n".join(
        line
        for line in test_boot.splitlines()
        if not line.lstrip().lower().startswith(("rem ", "::"))
    )
    if "--use-sage-attention" in test_executable.lower():
        raise CampaignError("Manager test boot enables global SageAttention")
    evidence["boot_contract"] = {
        "user_directory": str(layout.actual_user_directory),
        "default_manager_disabled": True,
        "default_whitelist_custom_nodes": whitelist_nodes,
        "test_boot_script": str(layout.test_boot_cmd),
        "test_opt_in_env": "LAB_MANAGER_OFFLINE_PROBE=1",
        "test_whitelist_custom_nodes": [
            "ComfyUI-GGUF",
            "ComfyUI-KJNodes",
            "ComfyUI-Manager",
        ],
        "manager_runtime_authority": (
            "exactly one pair-log network_mode: offline announcement"
        ),
        "sage_attention_flag": False,
    }
    evidence["manager_runtime_sources"] = manager_guard.source_proof()
    evidence["manager_prestartup_noop_state"] = (
        manager_guard.prestartup_state_evidence(layout.actual_user_directory)
    )
    evidence["manager_advisory_config"] = manager_guard.config_evidence(
        expected_server_argv(layout)
    )
    return evidence


def require_same_source_evidence(
    baseline: Mapping[str, Any], current: Mapping[str, Any], label: str
) -> None:
    for key in (
        "runner",
        "lab_locks",
        "boot_cmd",
        "test_boot_cmd",
        "manager_guard",
        "builder",
        "campaign",
    ):
        before = baseline.get(key) or {}
        after = current.get(key) or {}
        if before.get("path") != after.get("path") or before.get("sha256") != after.get(
            "sha256"
        ):
            raise CampaignError(f"{key} source changed at {label}")
    if baseline.get("boot_contract") != current.get("boot_contract"):
        raise CampaignError(f"boot command contract changed at {label}")
    for key in (
        "manager_runtime_sources",
        "manager_prestartup_noop_state",
        "manager_advisory_config",
    ):
        if baseline.get(key) != current.get(key):
            raise CampaignError(f"{key} changed at {label}")


def require_recipe_unchanged(spec: RecipeSpec) -> None:
    _, snapshot = stable_file(spec.path, f"recipe {spec.name}")
    if snapshot["sha256"] != spec.sha256:
        raise CampaignError(f"recipe hash drift before execution: {spec.name}")


def require_fixtures_unchanged(
    spec: RecipeSpec, layout: Layout = DEFAULT_LAYOUT
) -> None:
    for name, expected_hash in sorted(spec.fixture_hashes.items()):
        candidate = Path(name.replace("\\", "/"))
        if candidate.is_absolute() or len(candidate.parts) != 1:
            raise CampaignError(f"{spec.name} has unsafe fixture identity: {name}")
        _, snapshot = stable_file(
            layout.root / "fixtures" / candidate,
            f"fixture {name} for {spec.name}",
        )
        if snapshot["sha256"] != expected_hash:
            raise CampaignError(f"fixture hash drift before execution: {name}")
    expected_audio_receipt_hashes(spec, layout)


def campaign_id_now() -> str:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"h3canon-{timestamp}-{secrets.token_hex(4)}"


def validate_campaign_id(value: str) -> str:
    if CAMPAIGN_ID_RE.fullmatch(value) is None:
        raise CampaignError(
            "campaign id must be 1-80 characters from A-Z, a-z, 0-9, _, ., -"
        )
    return value


def executor_nonce(campaign_id: str, pair_index: int, role: str) -> str:
    validate_campaign_id(campaign_id)
    if role not in {"cold", "warm"}:
        raise CampaignError(f"invalid cache role: {role}")
    nonce = f"h3canon:{campaign_id}:p{pair_index:02d}:{role}"
    if len(nonce) > 160:
        raise CampaignError("executor nonce exceeds runner limit")
    return nonce


def parse_executor_nonce(nonce: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"h3canon:([A-Za-z0-9_.-]{1,80}):p(\d{2}):(cold|warm)", nonce)
    if match is None:
        raise CampaignError("executor nonce is not a canonical campaign nonce")
    campaign_id = validate_campaign_id(match.group(1))
    pair_index = int(match.group(2))
    if not 1 <= pair_index <= len(RECIPE_PINS):
        raise CampaignError("executor nonce pair index is out of range")
    return campaign_id, pair_index, match.group(3)


def completion_timeout_s(spec: RecipeSpec) -> int:
    try:
        return {107: 1_800, 192: 3_600, 277: 5_400}[spec.frames]
    except KeyError as exc:
        raise CampaignError(
            f"no completion timeout is pinned for {spec.frames} frames"
        ) from exc


def pair_log_path(
    spec: RecipeSpec,
    pair_index: int,
    campaign_id: str,
    layout: Layout = DEFAULT_LAYOUT,
) -> Path:
    validate_campaign_id(campaign_id)
    if not 1 <= pair_index <= len(RECIPE_PINS):
        raise CampaignError("canonical pair index is out of range")
    return (
        layout.results
        / "h3_canonical_canvas_campaign"
        / "server_logs"
        / f"{campaign_id}-p{pair_index:02d}-{spec.name}.log"
    )


def require_attempt_manager_log_set(
    campaign_id: str,
    expected_paths: Sequence[Path],
    layout: Layout = DEFAULT_LAYOUT,
    *,
    label: str,
) -> None:
    validate_campaign_id(campaign_id)
    log_root = layout.results / "h3_canonical_canvas_campaign" / "server_logs"
    found: list[Path] = []
    if os.path.lexists(log_root):
        ensure_real_directory(log_root, "canonical Manager log directory")
        for entry in log_root.iterdir():
            if not entry.name.startswith(f"{campaign_id}-"):
                continue
            if _is_reparse(entry) or not entry.is_file():
                raise CampaignError(f"{label} Manager log is not a real file: {entry}")
            found.append(Path(os.path.abspath(os.fspath(entry))))
    expected = {
        os.path.normcase(os.path.abspath(os.fspath(path))) for path in expected_paths
    }
    actual = {
        os.path.normcase(os.path.abspath(os.fspath(path))) for path in found
    }
    if actual != expected:
        raise CampaignError(
            f"{label} Manager log set drifted: "
            f"found={sorted(path.name for path in found)}"
        )


def child_command(
    spec: RecipeSpec,
    pair_index: int,
    role: str,
    campaign_id: str,
    layout: Layout = DEFAULT_LAYOUT,
) -> list[str]:
    command = [
        str(layout.python),
        str(layout.runner),
        str(spec.path),
        "--disable-pinned-memory",
        "--manager-offline-test",
        "--manager-probe-phase",
        role,
        "--completion-timeout-s",
        str(completion_timeout_s(spec)),
        "--executor-cache-nonce",
        executor_nonce(campaign_id, pair_index, role),
    ]
    if role == "warm":
        command.append("--shutdown")
    if "--force" in command:
        raise CampaignError("campaign commands may never use --force")
    return command


def child_environment(
    log_path: Path, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    environment = dict(source if source is not None else os.environ)
    removed = (
        "LAB_MANAGER_OFFLINE_PROBE",
        "LAB_MANAGER_PROBE_LOG",
        "LAB_RESERVE_VRAM_GB",
        "LAB_DISABLE_PINNED",
        "LAB_CACHE_CLASSIC",
        "LAB_EXTRA_WHITELIST",
        "LAB_SUITE_OWNER_PID",
        "LAB_SUITE_OWNER_CREATE_TIME",
        "LAB_SUITE_NONCE",
        *manager_guard.SCRUBBED_ENVIRONMENT_KEYS,
    )
    for key in removed:
        environment.pop(key, None)
    environment.update(manager_guard.OFFLINE_ENVIRONMENT)
    environment["LAB_MANAGER_PROBE_LOG"] = str(log_path.resolve())
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["LAB_PORT"] = str(LAB_PORT)
    manager_guard.offline_environment_evidence(environment)
    return environment


def runbook(
    campaign_id: str = "DRY-RUN",
    layout: Layout = DEFAULT_LAYOUT,
    resume_from_campaign_id: str | None = None,
) -> dict[str, Any]:
    if resume_from_campaign_id is not None:
        resume_from_campaign_id = validate_campaign_id(resume_from_campaign_id)
    specs = load_recipe_specs(layout)
    pairs = []
    nonces: list[str] = []
    for index, spec in enumerate(specs, start=1):
        cold = child_command(spec, index, "cold", campaign_id, layout)
        warm = child_command(spec, index, "warm", campaign_id, layout)
        nonces.extend(
            (
                cold[cold.index("--executor-cache-nonce") + 1],
                warm[warm.index("--executor-cache-nonce") + 1],
            )
        )
        pairs.append(
            {
                "pair_index": index,
                "recipe": spec.name,
                "recipe_sha256": spec.sha256,
                "mode": spec.mode,
                "frames": spec.frames,
                "completion_timeout_s": completion_timeout_s(spec),
                "manager_log": str(
                    pair_log_path(spec, index, campaign_id, layout)
                ),
                "cold_argv": cold,
                "warm_shutdown_argv": warm,
            }
        )
    if len(set(nonces)) != 12:
        raise CampaignError("executor nonces are not globally unique")
    return {
        "schema_version": 1,
        "campaign": "H3 canonical-canvas envelope",
        "campaign_id": campaign_id,
        "resume_from_campaign_id": resume_from_campaign_id,
        "default_invocation": "read-only; add --run to execute",
        "execution_authority": "run_recipe.py only",
        "manager_gate": {
            "actual_config": str(layout.actual_manager_config),
            "lab_config": str(layout.lab_manager_config),
            "required_network_mode": "offline",
            "advisory_config_checked_before_each_boot_and_after_shutdown": True,
            "manager_loaded_only_by_test_boot": True,
            "authoritative_evidence": (
                "pair-unique server log contains exactly one network_mode: offline "
                "announcement before startup and first prompt"
            ),
            "exact_log_set_required": True,
        },
        "operator_idle_policy": expected_operator_idle_policy(),
        "required_initial_state": {
            "gpu_lock": "absent",
            "suite_lock": "absent",
            "server_pid_receipt": "absent",
            "port_8199_listener": "absent",
            "queue_quarantine": "absent",
            "server_idle_gate_sidecar": "absent",
        },
        "pairs": pairs,
        "lifecycle": str(layout.lifecycle),
        "failure_policy": "stop first failure; no force; no receipt/artifact overwrite",
    }


def _listener_pids(port: int) -> list[int | None]:
    try:
        values = []
        for connection in psutil.net_connections(kind="inet"):
            local = connection.laddr
            local_port = (
                getattr(local, "port", local[1] if len(local) > 1 else None)
                if local
                else None
            )
            if connection.status == psutil.CONN_LISTEN and local_port == port:
                values.append(connection.pid)
        return sorted(set(values), key=lambda value: (-1 if value is None else value))
    except (psutil.AccessDenied, OSError) as exc:
        raise CampaignError(f"cannot inspect port {port} listeners: {exc}") from exc


def _read_pid_receipt(path: Path) -> int | None:
    if not os.path.lexists(path):
        return None
    if _is_reparse(path) or not path.is_file():
        raise CampaignError(f"server PID receipt is not a regular file: {path}")
    try:
        value = int(path.read_text(encoding="utf-8-sig").strip())
    except (OSError, UnicodeError, ValueError) as exc:
        raise CampaignError(f"server PID receipt cannot be verified: {exc}") from exc
    if value <= 0:
        raise CampaignError("server PID receipt is not positive")
    return value


def _identity_live(identity: Mapping[str, Any] | None) -> bool:
    if not identity:
        return False
    pid = identity.get("serving_pid")
    created = identity.get("process_create_time")
    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or isinstance(created, bool)
        or not isinstance(created, (int, float))
    ):
        return False
    try:
        actual = float(psutil.Process(pid).create_time())
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError) as exc:
        raise CampaignError(f"cannot verify expected server process identity: {exc}") from exc
    return math.isclose(actual, float(created), rel_tol=0.0, abs_tol=0.001)


def stable_idle_gate_sidecar(
    layout: Layout = DEFAULT_LAYOUT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(os.path.abspath(os.fspath(layout.idle_gate_sidecar)))
    if not os.path.lexists(path) or _is_reparse(path) or not path.is_file():
        raise CampaignError(f"idle-gate sidecar is missing or not a real file: {path}")
    if path.resolve(strict=True) != path:
        raise CampaignError("idle-gate sidecar does not resolve exactly")
    identity_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
    )
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or int(before.st_nlink) != 1:
            raise CampaignError(
                "idle-gate sidecar is not an exact single-link regular file"
            )
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            descriptor_before = os.fstat(fd)
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            descriptor_after = os.fstat(fd)
        finally:
            os.close(fd)
        after = path.lstat()
    except CampaignError:
        raise
    except OSError as exc:
        raise CampaignError(f"cannot stably read idle-gate sidecar: {exc}") from exc
    identity = tuple(int(getattr(before, key)) for key in identity_fields)
    if (
        identity
        != tuple(int(getattr(descriptor_before, key)) for key in identity_fields)
        or identity
        != tuple(int(getattr(descriptor_after, key)) for key in identity_fields)
        or identity
        != tuple(int(getattr(after, key)) for key in identity_fields)
        or _is_reparse(path)
        or not stat.S_ISREG(after.st_mode)
        or int(after.st_nlink) != 1
        or len(raw) != int(after.st_size)
    ):
        raise CampaignError("idle-gate sidecar changed during stable read")
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise CampaignError("idle-gate sidecar encoding/framing drifted")
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"idle-gate sidecar JSON is invalid: {exc}") from exc
    if not isinstance(evidence, dict):
        raise CampaignError("idle-gate sidecar is not a JSON object")
    expected_raw = (
        json.dumps(
            evidence,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if raw != expected_raw:
        raise CampaignError("idle-gate sidecar is not canonical JSON")
    unhashed = dict(evidence)
    evidence_sha256 = unhashed.pop("evidence_sha256", None)
    if evidence_sha256 != sha256_bytes(canonical_bytes(unhashed)):
        raise CampaignError("idle-gate sidecar evidence SHA mismatch")
    descriptor = {
        "path": str(path),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "identity": list(identity),
        "evidence_sha256": evidence_sha256,
        "server_instance": evidence.get("server_instance"),
    }
    return evidence, descriptor


def runtime_state(
    expected_server: Mapping[str, Any] | None = None,
    layout: Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    receipt_pid = _read_pid_receipt(layout.server_pid)
    receipt_create_time = None
    if receipt_pid is not None:
        try:
            receipt_create_time = round(
                float(psutil.Process(receipt_pid).create_time()), 6
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            receipt_create_time = None
    sidecar_exists = os.path.lexists(layout.idle_gate_sidecar)
    sidecar = None
    if sidecar_exists:
        _, sidecar = stable_idle_gate_sidecar(layout)
    return {
        "gpu_lock_exists": os.path.lexists(layout.gpu_lock),
        "suite_lock_exists": os.path.lexists(layout.suite_lock),
        "server_pid_receipt_exists": os.path.lexists(layout.server_pid),
        "server_pid_receipt": receipt_pid,
        "server_pid_create_time": receipt_create_time,
        "queue_quarantine_exists": os.path.lexists(layout.queue_quarantine),
        "idle_gate_sidecar_exists": sidecar_exists,
        "idle_gate_sidecar": sidecar,
        "listener_pids_8199": _listener_pids(LAB_PORT),
        "expected_server_identity_live": _identity_live(expected_server),
    }


def require_clean_state(
    state: Mapping[str, Any],
    label: str,
    *,
    require_idle_gate_field: bool = False,
) -> None:
    errors = []
    for field in (
        "gpu_lock_exists",
        "suite_lock_exists",
        "server_pid_receipt_exists",
        "queue_quarantine_exists",
        "expected_server_identity_live",
    ):
        if state.get(field) is not False:
            errors.append(f"{field}={state.get(field)!r}")
    if (
        state.get("idle_gate_sidecar_exists", False) is not False
        or (
            require_idle_gate_field
            and "idle_gate_sidecar_exists" not in state
        )
    ):
        errors.append(
            "idle_gate_sidecar_exists="
            f"{state.get('idle_gate_sidecar_exists')!r}"
        )
    if state.get("listener_pids_8199") != []:
        errors.append(f"listener_pids_8199={state.get('listener_pids_8199')!r}")
    if errors:
        raise CampaignError(f"{label} is not clean: {', '.join(errors)}")


def require_warm_server_state(
    state: Mapping[str, Any],
    identity: Mapping[str, Any],
    label: str,
    idle_gate_sidecar: Mapping[str, Any] | None = None,
) -> None:
    pid = identity.get("serving_pid")
    created = identity.get("process_create_time")
    errors = []
    if state.get("gpu_lock_exists") is not False:
        errors.append("gpu lock remains after cold child")
    if state.get("suite_lock_exists") is not False:
        errors.append("suite lock remains after cold child")
    if state.get("queue_quarantine_exists") is not False:
        errors.append("queue quarantine exists after cold child")
    if idle_gate_sidecar is not None:
        if state.get("idle_gate_sidecar_exists") is not True:
            errors.append("idle-gate sidecar is absent after cold child")
        if state.get("idle_gate_sidecar") != dict(idle_gate_sidecar):
            errors.append("idle-gate sidecar differs from cold receipt")
    elif (
        "idle_gate_sidecar_exists" in state
        and state.get("idle_gate_sidecar_exists") is not True
    ):
        errors.append("idle-gate sidecar is absent after cold child")
    if state.get("server_pid_receipt") != pid:
        errors.append("server PID receipt differs from cold receipt")
    if state.get("listener_pids_8199") != [pid]:
        errors.append("port 8199 listener differs from cold receipt")
    if not math.isclose(
        float(state.get("server_pid_create_time") or -1),
        float(created or -2),
        rel_tol=0.0,
        abs_tol=0.001,
    ):
        errors.append("server process create time differs from cold receipt")
    if state.get("expected_server_identity_live") is not True:
        errors.append("cold server identity is not live before warm")
    if errors:
        raise CampaignError(f"{label}: {'; '.join(errors)}")


def ensure_real_directory(path: Path, label: str) -> Path:
    lexical = Path(os.path.abspath(os.fspath(path)))
    if not os.path.lexists(lexical):
        raise CampaignError(f"missing {label}: {lexical}")
    if _is_reparse(lexical) or not lexical.is_dir():
        raise CampaignError(f"{label} is not a real directory: {lexical}")
    if lexical.resolve(strict=True) != lexical:
        raise CampaignError(f"{label} does not resolve exactly: {lexical}")
    return lexical


def ensure_pristine_history(spec: RecipeSpec, layout: Layout = DEFAULT_LAYOUT) -> None:
    results = ensure_real_directory(layout.results, "results directory")
    outputs = ensure_real_directory(layout.outputs, "outputs directory")
    forbidden: list[str] = []
    alias = results / f"{spec.name}.json"
    if os.path.lexists(alias):
        forbidden.append(str(alias))
    forbidden.extend(
        str(path)
        for path in results.iterdir()
        if path.name.startswith(f"{spec.name}_run")
    )
    forbidden.extend(
        str(path)
        for path in outputs.iterdir()
        if path.name.startswith(spec.prefix)
    )
    if forbidden:
        raise CampaignError(
            f"{spec.name} has pre-existing receipt/artifact evidence; refusing overwrite: "
            + ", ".join(sorted(forbidden))
        )


def _argv_value(argv: Sequence[str], option: str) -> str:
    positions = [index for index, value in enumerate(argv) if value == option]
    if len(positions) != 1 or positions[0] + 1 >= len(argv):
        raise CampaignError(f"server argv must contain one {option}")
    value = argv[positions[0] + 1]
    if value.startswith("--"):
        raise CampaignError(f"server argv {option} has no value")
    return value


def expected_server_argv(layout: Layout = DEFAULT_LAYOUT) -> list[str]:
    return [
        str(layout.comfyui_main),
        "--port",
        str(LAB_PORT),
        "--cuda-malloc",
        "--user-directory",
        str(layout.actual_user_directory),
        "--output-directory",
        str(layout.outputs),
        "--extra-model-paths-config",
        str(layout.root / "comfy_model_paths.yaml"),
        "--disable-metadata",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes",
        "ComfyUI-GGUF",
        "ComfyUI-KJNodes",
        "ComfyUI-Manager",
        "--disable-pinned-memory",
    ]


def validate_server_argv(argv: Any, layout: Layout = DEFAULT_LAYOUT) -> list[str]:
    if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
        raise CampaignError("receipt server_argv is not a string list")
    expected_argv = expected_server_argv(layout)
    if len(argv) != len(expected_argv):
        raise CampaignError(
            f"receipt server argv length drift: expected {len(expected_argv)}, "
            f"found {len(argv)}"
        )
    path_positions = {0, 5, 7, 9}
    for index, (actual, expected) in enumerate(zip(argv, expected_argv)):
        if index in path_positions:
            equal = os.path.normcase(os.path.abspath(actual)) == os.path.normcase(
                os.path.abspath(expected)
            )
        else:
            equal = actual == expected
        if not equal:
            raise CampaignError(
                f"receipt server argv drift at position {index}: "
                f"expected {expected!r}, found {actual!r}"
            )
    if _argv_value(argv, "--port") != "8199":
        raise CampaignError("receipt server argv uses the wrong port")
    if os.path.normcase(os.path.abspath(_argv_value(argv, "--user-directory"))) != os.path.normcase(
        os.path.abspath(layout.actual_user_directory)
    ):
        raise CampaignError("receipt server argv uses the wrong user-directory")
    if os.path.normcase(os.path.abspath(_argv_value(argv, "--output-directory"))) != os.path.normcase(
        os.path.abspath(layout.outputs)
    ):
        raise CampaignError("receipt server argv uses the wrong output-directory")
    required = {
        "--cuda-malloc",
        "--disable-metadata",
        "--disable-pinned-memory",
        "--disable-all-custom-nodes",
    }
    if not required.issubset(argv):
        raise CampaignError("receipt server argv lacks no-pinned/custom-node guard")
    for option in (*required, "--whitelist-custom-nodes"):
        if argv.count(option) != 1:
            raise CampaignError(f"receipt server argv must contain one {option}")
    forbidden = {
        "--use-sage-attention",
        "--reserve-vram",
        "--cache-classic",
        "--cache-none",
    }
    present = sorted(forbidden.intersection(argv))
    if present:
        raise CampaignError(f"receipt server argv contains forbidden lane flags: {present}")
    start = argv.index("--whitelist-custom-nodes") + 1
    whitelist = []
    for value in argv[start:]:
        if value.startswith("--"):
            break
        whitelist.append(value)
    if whitelist != ["ComfyUI-GGUF", "ComfyUI-KJNodes", "ComfyUI-Manager"]:
        raise CampaignError(f"receipt server whitelist drift: {whitelist}")
    return list(argv)


def strict_artifact(
    output_name: Any, expected_name: str, layout: Layout = DEFAULT_LAYOUT
) -> tuple[Path, dict[str, Any]]:
    if output_name != expected_name:
        raise CampaignError(
            f"artifact name mismatch: expected {expected_name}, found {output_name!r}"
        )
    candidate = Path(str(output_name).replace("\\", "/"))
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        raise CampaignError("artifact path is not contained in outputs/")
    outputs = ensure_real_directory(layout.outputs, "outputs directory")
    lexical = outputs / candidate
    if not os.path.lexists(lexical) or _is_reparse(lexical):
        raise CampaignError(f"artifact is missing or reparse-backed: {lexical}")
    resolved = lexical.resolve(strict=True)
    try:
        resolved.relative_to(outputs)
    except ValueError as exc:
        raise CampaignError("artifact escapes outputs directory") from exc
    if resolved != lexical or not resolved.is_file() or resolved.stat().st_size <= 0:
        raise CampaignError("artifact is not an exact nonempty regular output")
    return resolved, {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_real(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _redacted_workload_process_is_valid(
    value: Any, expected_classification: str
) -> bool:
    """Validate the runner's path-free blocker/advisory process evidence."""

    if (
        not isinstance(value, dict)
        or set(value) != set(EXPECTED_REDACTED_WORKLOAD_PROCESS_SCHEMA)
    ):
        return False
    if not _positive_int(value.get("pid")):
        return False
    created = value.get("process_create_time")
    if created is not None and (
        not _finite_real(created) or float(created) <= 0.0
    ):
        return False
    for field in ("process_basename", "executable_basename", "target_basename"):
        scalar = value.get(field)
        if scalar is not None and (
            not isinstance(scalar, str)
            or not scalar
            or scalar != scalar.lower()
            or "/" in scalar
            or "\\" in scalar
        ):
            return False
    markers = value.get("matched_markers")
    bases = value.get("match_basis")
    if (
        not isinstance(markers, list)
        or not all(isinstance(marker, str) for marker in markers)
        or markers != sorted(set(markers))
        or not set(markers).issubset(EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS)
        or not isinstance(bases, list)
        or not all(isinstance(basis, str) for basis in bases)
        or bases != sorted(set(bases))
        or re.fullmatch(r"[0-9a-f]{64}", str(value.get("argv_sha256") or ""))
        is None
    ):
        return False
    positive_bases = {
        "python_script_target",
        "process_basename",
        "executable_basename",
        "python_script_or_module_target",
    }
    exclusion_bases = {
        "current_runner_exclusion_mismatch",
        "owned_server_exclusion_mismatch",
    }
    if expected_classification == "advisory":
        return markers == [] and bases == [
            "advisory_python_without_positive_marker"
        ]
    if expected_classification == "blocking":
        positive = bool(markers) and bool(set(bases).intersection(positive_bases))
        exclusion = not markers and len(bases) == 1 and bases[0] in exclusion_bases
        return positive or exclusion
    if expected_classification == "clear":
        return markers == [] and bases == []
    return False


def verify_operator_idle_measurement(
    receipt: Mapping[str, Any], label: str
) -> dict[str, Any]:
    """Verify the operator-authorized absolute/net VRAM receipt arithmetic."""

    baseline = receipt.get("baseline_vram_gb")
    peak = receipt.get("peak_vram_gb")
    absolute_peak = receipt.get("absolute_peak_vram_gb")
    net_peak = receipt.get("net_peak_vram_gb")
    if (
        not _finite_real(baseline)
        or float(baseline) < 0.0
        or not _finite_real(peak)
        or float(peak) <= float(baseline) + 0.2
        or float(peak) > 14.5
        or not _finite_real(absolute_peak)
        or float(absolute_peak) != float(peak)
        or not _finite_real(net_peak)
    ):
        raise CampaignError(f"{label} operator idle/VRAM measurements are invalid")

    expected_net = round(float(peak) - float(baseline), 3)
    if float(net_peak) != expected_net:
        raise CampaignError(
            f"{label} net peak is not exact receipt arithmetic: "
            f"expected {expected_net}, found {net_peak!r}"
        )
    elevated = float(baseline) > ELEVATED_BASELINE_THRESHOLD_GB
    if receipt.get("elevated_baseline_lane") is not elevated:
        raise CampaignError(f"{label} elevated-baseline boolean is inconsistent")
    expected_stamp = ELEVATED_BASELINE_STAMP if elevated else None
    if receipt.get("baseline_lane_stamp") != expected_stamp:
        raise CampaignError(f"{label} elevated-baseline stamp is inconsistent")
    policy = expected_operator_idle_policy()
    identity = receipt.get("identity") or {}
    if (
        receipt.get("operator_idle_policy") != policy
        or not isinstance(identity, dict)
        or identity.get("operator_idle_policy") != policy
    ):
        raise CampaignError(f"{label} operator idle policy is not identity-bound")
    expected_measurement = {
        "units": "GiB (nvidia-smi MiB / 1024)",
        "baseline_measurement_point": (
            "immediately before prompt queue; includes owned lab server and desktop load"
        ),
        "baseline_absolute_gib": float(baseline),
        "peak_absolute_gib": float(absolute_peak),
        "net_peak_gib": float(net_peak),
        "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
    }
    if receipt.get("vram_measurement") != expected_measurement:
        raise CampaignError(f"{label} VRAM measurement descriptor is inconsistent")
    return {
        "baseline_vram_gb": float(baseline),
        "absolute_peak_vram_gb": float(absolute_peak),
        "net_peak_vram_gb": float(net_peak),
        "elevated_baseline_lane": elevated,
        "baseline_lane_stamp": expected_stamp,
        "vram_measurement": expected_measurement,
    }


def verify_operator_idle_advisories(
    receipt: Mapping[str, Any], *, role: str, label: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = float(receipt["baseline_vram_gb"])
    expected_baseline = {
        "schema_version": 1,
        "kind": "per-leg-prequeue-baseline-advisory",
        "baseline_vram_gb": baseline,
        "advisory_threshold_gb": 3.0,
        "threshold_exceeded": baseline > 3.0,
        "gating": False,
        "disposition": "record-only; proceed regardless of baseline",
    }
    baseline_advisory = receipt.get("baseline_advisory")
    if baseline_advisory != expected_baseline:
        raise CampaignError(f"{label} baseline advisory is inconsistent")
    drift = receipt.get("cold_warm_baseline_drift_advisory")
    expected_keys = {
        "schema_version",
        "kind",
        "applicable",
        "measurement_available",
        "previous_baseline_vram_gb",
        "current_baseline_vram_gb",
        "absolute_drift_gb",
        "advisory_threshold_gb",
        "threshold_exceeded",
        "gating",
        "disposition",
    }
    if (
        not isinstance(drift, dict)
        or set(drift) != expected_keys
        or drift.get("schema_version") != 1
        or drift.get("kind")
        != "same-identity-cold-warm-baseline-drift-advisory"
        or drift.get("current_baseline_vram_gb") != baseline
        or drift.get("advisory_threshold_gb") != 0.5
        or drift.get("gating") is not False
    ):
        raise CampaignError(f"{label} baseline drift advisory is invalid")
    if role == "cold":
        expected_cold = {
            "schema_version": 1,
            "kind": "same-identity-cold-warm-baseline-drift-advisory",
            "applicable": False,
            "measurement_available": False,
            "previous_baseline_vram_gb": None,
            "current_baseline_vram_gb": baseline,
            "absolute_drift_gb": None,
            "advisory_threshold_gb": 0.5,
            "threshold_exceeded": False,
            "gating": False,
            "disposition": "record-only; no same-identity prior leg",
        }
        if drift != expected_cold:
            raise CampaignError(f"{label} cold drift advisory is inconsistent")
    elif role == "warm":
        previous = drift.get("previous_baseline_vram_gb")
        absolute = drift.get("absolute_drift_gb")
        if (
            drift.get("applicable") is not True
            or drift.get("measurement_available") is not True
            or not _finite_real(previous)
            or float(previous) < 0
            or not _finite_real(absolute)
            or float(absolute) < 0
            or drift.get("threshold_exceeded") is not (float(absolute) > 0.5)
            or drift.get("disposition")
            != "record-only; proceed regardless of drift"
        ):
            raise CampaignError(f"{label} warm drift advisory is inconsistent")
    else:
        raise CampaignError("operator idle advisory role must be cold or warm")
    return dict(baseline_advisory), dict(drift)


def verify_prequeue_known_workload_scan(
    receipt: Mapping[str, Any],
    *,
    sources: Mapping[str, Any],
    server_instance: Mapping[str, Any],
    server_argv: list[str],
    label: str,
) -> dict[str, Any]:
    contract = expected_operator_idle_policy()[
        "prequeue_known_workload_scan_contract"
    ]
    identity = receipt.get("identity") or {}
    evidence = receipt.get("prequeue_known_workload_scan")
    if (
        receipt.get("prequeue_known_workload_scan_contract") != contract
        or not isinstance(identity, dict)
        or identity.get("prequeue_known_workload_scan_contract") != contract
        or not isinstance(evidence, dict)
    ):
        raise CampaignError(f"{label} prequeue workload contract/evidence is missing")
    expected_keys = {
        "schema_version",
        "kind",
        "status",
        "scan_ran",
        "sampled_at_ns",
        "sampled_at_utc",
        "completed_at_ns",
        "contract",
        "server_instance",
        "server_argv",
        "listener_pid_before",
        "listener_pid_after",
        "current_runner_exclusion",
        "owned_lab_server_exclusion",
        "scanned_process_count",
        "excluded_current_runner",
        "excluded_owned_lab_server",
        "blocking_processes",
        "advisory_unreadable_processes",
        "scan_errors",
        "evidence_sha256",
    }
    body = dict(evidence)
    retained_hash = body.pop("evidence_sha256", None)
    serving_pid = server_instance.get("serving_pid")
    current = evidence.get("current_runner_exclusion") or {}
    owned = evidence.get("owned_lab_server_exclusion") or {}
    excluded_current = evidence.get("excluded_current_runner") or []
    excluded_server = evidence.get("excluded_owned_lab_server") or []
    advisories = evidence.get("advisory_unreadable_processes")
    runner_path = str(Path(sources["runner"]["path"]).resolve())
    if (
        set(evidence) != expected_keys
        or retained_hash != stable_identity(body)
        or evidence.get("schema_version") != 1
        or evidence.get("kind")
        != "per-leg-immediate-prequeue-known-workload-scan"
        or evidence.get("status") != "clean"
        or evidence.get("scan_ran") is not True
        or evidence.get("contract") != contract
        or evidence.get("server_instance") != dict(server_instance)
        or evidence.get("server_argv") != list(server_argv)
        or evidence.get("listener_pid_before") != serving_pid
        or evidence.get("listener_pid_after") != serving_pid
        or evidence.get("blocking_processes") != []
        or not isinstance(advisories, list)
        or not all(
            _redacted_workload_process_is_valid(value, "advisory")
            for value in advisories
        )
        or evidence.get("scan_errors") != []
        or not _positive_int(evidence.get("sampled_at_ns"))
        or not _positive_int(evidence.get("completed_at_ns"))
        or evidence["completed_at_ns"] < evidence["sampled_at_ns"]
        or not isinstance(evidence.get("sampled_at_utc"), str)
        or not evidence["sampled_at_utc"]
        or not _positive_int(evidence.get("scanned_process_count"))
        or evidence["scanned_process_count"] < 2
    ):
        raise CampaignError(f"{label} prequeue known-workload scan is invalid")
    current_identity = current.get("process_identity") or {}
    current_argv = current_identity.get("command_line") or []
    if (
        current.get("narrowly_verified") is not True
        or current.get("excluded_pid_only") is not True
        or not _positive_int(current.get("pid"))
        or not _finite_real(current.get("process_create_time"))
        or os.path.normcase(str(current.get("resolved_runner_path", "")))
        != os.path.normcase(runner_path)
        or current_identity.get("exists") is not True
        or current_identity.get("pid") != current.get("pid")
        or runner_path not in {
            str(Path(value).resolve())
            for value in current_argv
            if isinstance(value, str) and value.lower().endswith(".py")
        }
    ):
        raise CampaignError(f"{label} current-runner prequeue exclusion is invalid")
    runner_verifier = load_runner_verifier(Path(sources["runner"]["path"]))
    runner_errors = runner_verifier.prequeue_known_workload_scan_validation_errors(
        dict(evidence), dict(server_instance), list(server_argv)
    )
    if runner_errors:
        raise CampaignError(
            f"{label} prequeue runner exclusion validation failed: {runner_errors}"
        )
    owned_errors = runner_verifier.owned_lab_server_exclusion_validation_errors(
        dict(owned),
        dict(server_instance),
        list(server_argv),
        list(excluded_server) if isinstance(excluded_server, list) else excluded_server,
    )
    if owned_errors:
        raise CampaignError(
            f"{label} owned-server prequeue exclusion validation failed: "
            f"{owned_errors}"
        )
    argv_match = owned.get("argv_match") or {}
    owned_expected_count = owned.get("expected_excluded_process_count")
    excluded_serving_rows = [
        row
        for row in excluded_server
        if isinstance(row, dict) and row.get("pid") == serving_pid
    ] if isinstance(excluded_server, list) else []
    if (
        owned.get("narrowly_verified") is not True
        or owned.get("excluded_pid_only") is not True
        or owned.get("pid") != serving_pid
        or owned.get("server_instance") != dict(server_instance)
        or (owned.get("process_identity") or {}).get("exists") is not True
        or argv_match.get("matches") is not True
        or argv_match.get("reported_server_argv") != list(server_argv)
        or argv_match.get("match_mode")
        not in {
            "exact-self-reported-argv",
            "exact-self-reported-argv-plus-python-interpreter-prefix",
        }
        or owned_expected_count not in {1, 2}
        or not isinstance(excluded_server, list)
        or len(excluded_server) != owned_expected_count
        or len(excluded_serving_rows) != 1
        or excluded_serving_rows[0].get("reason")
        != "exact owned port-8199 server PID/create-time/argv"
    ):
        raise CampaignError(f"{label} owned-server prequeue exclusion is invalid")
    return dict(evidence)


def _prompt_link_sources(value: Any, prompt_ids: set[str]) -> list[str]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and value[0] in prompt_ids
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    ):
        return [value[0]]
    sources: list[str] = []
    if isinstance(value, list):
        for child in value:
            sources.extend(_prompt_link_sources(child, prompt_ids))
    elif isinstance(value, dict):
        for child in value.values():
            sources.extend(_prompt_link_sources(child, prompt_ids))
    return sources


def expected_cache_contract(spec: RecipeSpec, nonce: str) -> dict[str, Any]:
    recipe, _ = strict_json(spec.path, f"recipe {spec.name} for cache closure")
    prompt = recipe.get("prompt")
    if not isinstance(prompt, dict):
        raise CampaignError(f"{spec.name} prompt is not an object")
    prompt_ids = {str(node_id) for node_id in prompt}
    candidates = [
        (str(node_id), node.get("class_type"))
        for node_id, node in prompt.items()
        if isinstance(node, dict)
        and node.get("class_type") in {"RandomNoise", "KSampler", "SamplerCustom"}
    ]
    if len(candidates) != 1:
        raise CampaignError(f"{spec.name} cache source is ambiguous: {candidates}")
    source_id, source_class = candidates[0]
    source_inputs = prompt[source_id].get("inputs")
    seed_input = "seed" if source_class == "KSampler" else "noise_seed"
    if not isinstance(source_inputs, dict) or seed_input not in source_inputs:
        raise CampaignError(f"{spec.name} cache source has no declared seed")
    if source_class == "RandomNoise" and set(source_inputs) != {"noise_seed"}:
        raise CampaignError(f"{spec.name} RandomNoise inputs changed")
    recipe_seed = source_inputs[seed_input]
    if isinstance(recipe_seed, bool) or not isinstance(recipe_seed, int):
        raise CampaignError(f"{spec.name} cache source seed is not an integer")

    descendants = {source_id}
    changed = True
    while changed:
        changed = False
        for node_id, node in prompt.items():
            node_id = str(node_id)
            if node_id in descendants or not isinstance(node, dict):
                continue
            links = []
            for value in (node.get("inputs") or {}).values():
                links.extend(_prompt_link_sources(value, prompt_ids))
            if any(link in descendants for link in links):
                descendants.add(node_id)
                changed = True

    reachable = {
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") in {"SaveImage", "SaveVideo"}
    }
    stack = list(reachable)
    while stack:
        node_id = stack.pop()
        for value in (prompt[node_id].get("inputs") or {}).values():
            for source in _prompt_link_sources(value, prompt_ids):
                if source not in reachable:
                    reachable.add(source)
                    stack.append(source)
    order = lambda value: (len(value), value)
    fresh = sorted(descendants, key=order)
    reachable_ids = sorted(reachable, key=order)
    stable = sorted(reachable - descendants, key=order)
    if source_class == "RandomNoise":
        samplers = sorted(
            (
                node_id
                for node_id in descendants
                if prompt[node_id].get("class_type") == "SamplerCustomAdvanced"
            ),
            key=order,
        )
    else:
        samplers = [source_id]
    outputs = sorted(
        (
            node_id
            for node_id in descendants
            if prompt[node_id].get("class_type") in {"SaveImage", "SaveVideo"}
        ),
        key=order,
    )
    if source_id not in reachable or not samplers or not outputs:
        raise CampaignError(f"{spec.name} cache source does not reach sampler/output")
    queued_prompt = copy.deepcopy(prompt)
    queued_prompt[source_id]["inputs"]["_vram_lab_cache_nonce"] = nonce
    return {
        "mode": "pinned-undeclared-sampler-input",
        "nonce": nonce,
        "source_node_id": source_id,
        "source_class_type": source_class,
        "seed_input": seed_input,
        "recipe_seed": recipe_seed,
        "fresh_node_ids": fresh,
        "stable_node_ids": stable,
        "reachable_node_ids": reachable_ids,
        "sampler_node_ids": samplers,
        "fresh_output_node_ids": outputs,
        "queued_prompt_sha256": stable_identity(queued_prompt),
    }


def recipe_model_names(spec: RecipeSpec) -> list[str]:
    recipe, _ = strict_json(spec.path, f"recipe {spec.name} for model identity")
    prompt = recipe.get("prompt") or {}
    model_inputs = {
        "ckpt_name",
        "unet_name",
        "vae_name",
        "clip_name",
        "text_encoder",
        "audio_encoder_name",
        "lora_name",
        "model_name",
    }
    return sorted(
        {
            value.replace("\\", "/")
            for node in prompt.values()
            if isinstance(node, dict)
            for key, value in (node.get("inputs") or {}).items()
            if key in model_inputs and isinstance(value, str) and value
        }
    )


def expected_audio_receipt_hashes(
    spec: RecipeSpec, layout: Layout = DEFAULT_LAYOUT
) -> dict[str, str]:
    recipe, _ = strict_json(spec.path, f"recipe {spec.name} for audio receipts")
    prompt = recipe.get("prompt") or {}
    audio_names = sorted(
        {
            value.replace("\\", "/")
            for node in prompt.values()
            if isinstance(node, dict) and node.get("class_type") == "LoadAudio"
            for value in [(node.get("inputs") or {}).get("audio")]
            if isinstance(value, str) and value
        }
    )
    expected: dict[str, str] = {}
    for name in audio_names:
        candidate = Path(name)
        if candidate.is_absolute() or len(candidate.parts) != 1:
            raise CampaignError(f"{spec.name} has unsafe audio fixture name: {name}")
        receipt = layout.root / "fixtures" / "audio_receipts" / f"{candidate.stem}.json"
        raw, _ = stable_file(receipt, f"audio receipt for {name}")
        expected[name] = sha256_bytes(raw)
    return expected


def validate_model_fingerprints(spec: RecipeSpec, models: Any) -> dict[str, Any]:
    expected_names = recipe_model_names(spec)
    if not isinstance(models, dict) or sorted(models) != expected_names:
        raise CampaignError(f"{spec.name} model fingerprint names drift")
    for name in expected_names:
        row = models[name]
        if not isinstance(row, dict) or row.get("resolved") is not True:
            raise CampaignError(f"{spec.name} model pin is unresolved: {name}")
        path_text = row.get("path")
        if not isinstance(path_text, str):
            raise CampaignError(f"{spec.name} model pin path is missing: {name}")
        model_path = Path(os.path.abspath(path_text))
        normalized_path = str(model_path).replace("\\", "/")
        if not normalized_path.lower().endswith("/" + name.lower()):
            raise CampaignError(f"{spec.name} model pin path/name mismatch: {name}")
        if not os.path.lexists(model_path) or _is_reparse(model_path) or not model_path.is_file():
            raise CampaignError(f"{spec.name} model pin is not a real file: {name}")
        model_stat = model_path.stat()
        if row.get("bytes") != model_stat.st_size or row.get("mtime_ns") != model_stat.st_mtime_ns:
            raise CampaignError(f"{spec.name} model pin stat drift: {name}")
    return dict(models)


def expected_manager_identity(evidence: Mapping[str, Any]) -> dict[str, Any]:
    advisory = evidence.get("advisory_config") or {}
    scan = evidence.get("log_scan") or {}
    authority = scan.get("authoritative_server_reported_mode") or {}
    source = scan.get("source_proof") or {}
    return {
        "recipe_scope": evidence.get("recipe_scope"),
        "guard_source": evidence.get("guard_source"),
        "test_boot_source": evidence.get("test_boot_source"),
        "offline_environment": evidence.get("offline_environment"),
        "advisory_config_path": (advisory.get("snapshot") or {}).get("path"),
        "advisory_config_sha256": (advisory.get("snapshot") or {}).get("sha256"),
        "authoritative_server_reported_mode": authority.get("resolved_mode"),
        "manager_source_sha256s": {
            key: (source.get(key) or {}).get("sha256")
            for key in (
                "manager_prestartup",
                "manager_server",
                "manager_core",
                "comfy_folder_paths",
                "manager_util",
            )
        },
        "prestartup_state_sha256": (
            (scan.get("current_prestartup_state") or {}).get("state_sha256")
        ),
        "preboot_record_sha256": (
            ((scan.get("preboot_records") or [{}])[0].get("record") or {}).get(
                "record_sha256"
            )
        ),
        "log_path": evidence.get("log_path"),
        "serving_pid": evidence.get("serving_pid"),
        "serving_process_create_time_ns": evidence.get(
            "serving_process_create_time_ns"
        ),
    }


def verify_manager_receipt(
    receipt: Mapping[str, Any],
    *,
    log_path: Path,
    argv: Sequence[str],
    role: str,
    recipe_name: str,
    layout: Layout,
) -> dict[str, Any]:
    if role not in {"cold", "warm"}:
        raise CampaignError("Manager receipt role must be cold or warm")
    cold = role == "cold"
    bundle = receipt.get("manager_offline_probe")
    if not isinstance(bundle, dict) or bundle.get("provenance_unchanged") is not True:
        raise CampaignError("Manager receipt bundle is missing or changed")
    pre = bundle.get("pre_queue")
    post = bundle.get("post_render")
    if not isinstance(pre, dict) or not isinstance(post, dict):
        raise CampaignError("Manager pre/post receipt evidence is missing")
    expected_environment = manager_guard.offline_environment_evidence(
        dict(manager_guard.OFFLINE_ENVIRONMENT)
    )
    expected_scope = {
        "scope": "h3-canonical-canvas-job-c",
        "match_type": "exact",
        "match_value": recipe_name,
        "log_root": str(
            (
                layout.results
                / "h3_canonical_canvas_campaign"
                / "server_logs"
            ).resolve()
        ),
    }
    for label, evidence in (("pre", pre), ("post", post)):
        if (
            evidence.get("enabled") is not True
            or evidence.get("valid") is not True
            or evidence.get("log_path") != str(log_path.resolve())
            or evidence.get("offline_environment") != expected_environment
            or evidence.get("recipe_scope") != expected_scope
        ):
            raise CampaignError(f"Manager {label} evidence identity drift")
        if evidence.get("advisory_config") != manager_guard.config_evidence(argv):
            raise CampaignError(f"Manager {label} advisory config drift")
        scan = evidence.get("log_scan")
        if not isinstance(scan, dict):
            raise CampaignError(f"Manager {label} scan is missing")
        errors = manager_guard.validate_scan_binding(scan, log_path, argv)
        if errors:
            raise CampaignError(f"Manager {label} log binding failed: {errors}")
        authority = scan.get("authoritative_server_reported_mode") or {}
        if (
            authority.get("announcement_count") != 1
            or authority.get("observed_values") != ["offline"]
            or authority.get("resolved_mode") != "offline"
            or authority.get("mode_precedes_startup_completion") is not True
            or authority.get("mode_precedes_first_execution") is not True
            or scan.get("network_markers") != []
            or scan.get("mutation_markers") != []
        ):
            raise CampaignError(f"Manager {label} runtime authority failed")
        expected_execution_count = {
            ("cold", "pre"): 0,
            ("cold", "post"): 2,
            ("warm", "pre"): 2,
            ("warm", "post"): 4,
        }[(role, label)]
        if (
            len(scan.get("execution_markers") or []) != expected_execution_count
            or len(scan.get("startup_complete_markers") or []) != 1
            or len(scan.get("config_announcements") or []) != 1
        ):
            raise CampaignError(
                f"Manager {role} {label} phase marker count drifted"
            )
    if (
        pre.get("require_no_prior_prompt") is not cold
        or (pre.get("log_scan") or {}).get("require_pre_prompt") is not cold
    ):
        raise CampaignError("Manager cold/warm pre-prompt phase drift")
    if cold and (pre.get("log_scan") or {}).get("execution_markers") != []:
        raise CampaignError("cold Manager gate was not evaluated before first prompt")
    if expected_manager_identity(pre) != expected_manager_identity(post):
        raise CampaignError("Manager immutable identity changed during render")
    identity = receipt.get("identity") or {}
    expected_identity = expected_manager_identity(pre)
    if identity.get("manager_offline_probe_identity") != expected_identity:
        raise CampaignError("run identity does not bind Manager offline proof")
    return {"pre_queue": pre, "post_render": post, "identity": expected_identity}


def verify_final_log(log_path: Path, argv: Sequence[str]) -> dict[str, Any]:
    scan = manager_guard.scan_log(
        log_path,
        argv,
        expected_url="http://127.0.0.1:8199",
        require_pre_prompt=False,
    )
    errors = manager_guard.validate_scan_binding(scan, log_path, argv)
    if errors:
        raise CampaignError(f"final Manager log audit failed: {errors}")
    authority = scan.get("authoritative_server_reported_mode") or {}
    if (
        authority.get("announcement_count") != 1
        or authority.get("observed_values") != ["offline"]
        or authority.get("resolved_mode") != "offline"
        or scan.get("network_markers") != []
        or scan.get("mutation_markers") != []
        or len(scan.get("execution_markers") or []) != 4
        or len(scan.get("startup_complete_markers") or []) != 1
        or len(scan.get("config_announcements") or []) != 1
    ):
        raise CampaignError("final Manager log does not prove offline prompt execution")
    return scan


def _validate_idle_gate_contract(
    contract: Any,
    sources: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise CampaignError("preboot GPU idle gate contract is missing")
    required = {
        "schema_version": 1,
        "kind": "run-recipe-preboot-wddm-idle-gate-contract",
        "gpu_index": 0,
        "port": LAB_PORT,
        "sample_count": 5,
        "sampling_interval_s": 0.2,
        "aggregation": "maximum of five conjunctively quiescent WDDM samples",
    }
    for field, expected in required.items():
        if contract.get(field) != expected:
            raise CampaignError(f"preboot GPU idle contract field {field} drifted")
    policy = contract.get("policy")
    expected_policy = {
        "advisory_vram_used_mib": 3072.0,
        "vram_used_mib_threshold_gating": False,
        "operator_idle_policy": expected_operator_idle_policy(),
        "gpu_utilization_recorded_non_gating": True,
        "memory_utilization_recorded_non_gating": True,
        "recognized_unmetered_wddm_memory_token": "[N/A]",
        "numeric_or_unknown_process_memory_tokens_block": True,
        "live_process_identity_required": True,
        "desktop_graphics_signals_retained_but_not_required": True,
        "known_workload_classifier": (
            expected_known_workload_classifier_contract()
        ),
        "port_8199_listener_required_absent": True,
        "same_gpu_lease_required_each_sample": True,
        "required_driver_model": "WDDM",
        "display_active_allowed_measured_states": ["Disabled", "Enabled"],
        "display_active_recorded_non_gating": True,
        "current_runner_exclusion": (
            "exact real runner PID/create-time/target plus at most one verified "
            "direct Windows venv launcher stub"
        ),
    }
    if not isinstance(policy, dict):
        raise CampaignError("preboot GPU idle policy is missing")
    for field, expected in expected_policy.items():
        if policy.get(field) != expected:
            raise CampaignError(f"preboot GPU idle policy field {field} drifted")
    markers = policy.get("model_workload_markers")
    if markers != EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS:
        raise CampaignError("preboot GPU idle workload markers drifted")
    collector = contract.get("collector")
    expected_runner = sources.get("runner") or {}
    if (
        not isinstance(collector, dict)
        or os.path.normcase(os.path.abspath(str(collector.get("path", ""))))
        != os.path.normcase(os.path.abspath(str(expected_runner.get("path", ""))))
        or collector.get("sha256") != expected_runner.get("sha256")
    ):
        raise CampaignError("preboot GPU idle collector source drifted")
    return dict(contract)


def verify_preboot_idle_gate(
    receipt: Mapping[str, Any],
    *,
    role: str,
    sources: Mapping[str, Any],
    server_instance: Mapping[str, Any],
    layout: Layout,
) -> dict[str, Any]:
    gate = receipt.get("preboot_gpu_idle_gate")
    if not isinstance(gate, dict):
        raise CampaignError("preboot GPU idle gate receipt is missing")
    if (
        gate.get("schema_version") != 1
        or gate.get("kind") != "run-recipe-preboot-wddm-idle-gate"
    ):
        raise CampaignError("preboot GPU idle gate schema drifted")
    contract = _validate_idle_gate_contract(gate.get("contract"), sources)
    identity = receipt.get("identity") or {}
    if (
        receipt.get("preboot_gpu_idle_gate_contract") != contract
        or identity.get("preboot_gpu_idle_gate_contract") != contract
    ):
        raise CampaignError("run identity does not bind preboot GPU idle contract")
    if gate.get("server_instance") != dict(server_instance):
        raise CampaignError("preboot GPU idle evidence server identity drifted")
    unhashed_gate = dict(gate)
    retained_digest = unhashed_gate.pop("evidence_sha256", None)
    if retained_digest != sha256_bytes(canonical_bytes(unhashed_gate)):
        raise CampaignError("preboot GPU idle evidence SHA mismatch")
    runner_verifier = load_runner_verifier(Path(sources["runner"]["path"]))
    runner_errors = runner_verifier.gpu_idle_gate_validation_errors(
        dict(gate), dict(server_instance)
    )
    if runner_errors:
        raise CampaignError(
            f"preboot GPU idle runner validation failed: {runner_errors}"
        )
    if role == "cold":
        expected_cold_keys = {
            "schema_version",
            "kind",
            "status",
            "gate_ran",
            "gpu_index",
            "target_gpu",
            "sample_count",
            "sampling_interval_s",
            "aggregation",
            "policy",
            "contract",
            "port_8199_listener_pids_before",
            "port_8199_listener_pids_after",
            "current_runner_exclusion",
            "gpu_lock_owner",
            "samples",
            "summary",
            "collector",
            "server_instance",
            "evidence_sha256",
        }
        if (
            set(gate) != expected_cold_keys
            or
            gate.get("status") != "measured"
            or gate.get("gate_ran") is not True
            or gate.get("gpu_index") != 0
            or gate.get("sample_count") != 5
            or gate.get("sampling_interval_s") != 0.2
            or gate.get("aggregation")
            != "maximum of five conjunctively quiescent WDDM samples"
            or gate.get("port_8199_listener_pids_before") != []
            or gate.get("port_8199_listener_pids_after") != []
        ):
            raise CampaignError("cold preboot GPU idle gate did not run as pinned")
        samples = gate.get("samples")
        current_runner = gate.get("current_runner_exclusion") or {}
        target_gpu = gate.get("target_gpu") or {}
        runner_identity = current_runner.get("process_identity") or {}
        expected_runner_path = str(Path(sources["runner"]["path"]).resolve())
        if (
            not isinstance(samples, list)
            or len(samples) != 5
            or not all(isinstance(sample, dict) for sample in samples)
            or not isinstance(target_gpu, dict)
            or not isinstance(current_runner, dict)
            or current_runner.get("narrowly_verified") is not True
            or current_runner.get("excluded_pid_only") is not True
            or os.path.normcase(str(current_runner.get("resolved_runner_path", "")))
            != os.path.normcase(expected_runner_path)
            or not _positive_int(current_runner.get("pid"))
            or not _finite_real(current_runner.get("process_create_time"))
            or float(current_runner["process_create_time"]) <= 0
            or not isinstance(runner_identity, dict)
            or runner_identity.get("exists") is not True
            or runner_identity.get("pid") != current_runner.get("pid")
            or not math.isclose(
                float(runner_identity.get("process_create_time") or 0.0),
                float(current_runner.get("process_create_time") or -1.0),
                rel_tol=0.0,
                abs_tol=0.001,
            )
            or runner_identity.get("identity_errors") != []
            or not isinstance(runner_identity.get("command_line"), list)
            or expected_runner_path not in {
                str(Path(value).resolve())
                for value in runner_identity.get("command_line") or []
                if isinstance(value, str) and value.lower().endswith(".py")
            }
        ):
            raise CampaignError("cold preboot GPU idle gate evidence is incomplete")
        policy = contract["policy"]
        if gate.get("policy") != policy or gate.get("collector") != contract["collector"]:
            raise CampaignError("cold preboot GPU idle retained contract fields drifted")
        if (
            target_gpu.get("gpu_index") != 0
            or not isinstance(target_gpu.get("gpu_uuid"), str)
            or not target_gpu["gpu_uuid"]
            or not isinstance(target_gpu.get("gpu_name"), str)
            or not target_gpu["gpu_name"]
            or not _finite_real(target_gpu.get("vram_total_mib"))
            or float(target_gpu["vram_total_mib"]) <= 0
            or target_gpu.get("driver_model_current") != "WDDM"
            or target_gpu.get("display_active") not in {"Disabled", "Enabled"}
            or not isinstance(target_gpu.get("query_argv"), list)
            or re.fullmatch(
                r"[0-9a-f]{64}", str(target_gpu.get("raw_stdout_sha256", ""))
            )
            is None
        ):
            raise CampaignError("cold preboot GPU target identity is invalid")
        lock_owner = gate.get("gpu_lock_owner") or {}
        lock_owner_keys = {
            "lock_schema_version",
            "pid",
            "process_create_time",
            "nonce",
            "role",
            "created_at_unix",
        }
        if (
            not isinstance(lock_owner, dict)
            or set(lock_owner) != lock_owner_keys
            or lock_owner.get("lock_schema_version") != 1
            or lock_owner.get("pid") != current_runner.get("pid")
            or not math.isclose(
                float(lock_owner.get("process_create_time") or 0.0),
                float(current_runner.get("process_create_time") or -1.0),
                rel_tol=0.0,
                abs_tol=0.001,
            )
            or not isinstance(lock_owner.get("nonce"), str)
            or len(lock_owner["nonce"]) < 32
            or lock_owner.get("role") != "standalone"
            or not _finite_real(lock_owner.get("created_at_unix"))
            or float(lock_owner["created_at_unix"]) <= 0
        ):
            raise CampaignError("cold preboot GPU lock owner is invalid")

        prior_sampled_at_ns = 0
        prior_monotonic_ns = 0
        observed: dict[str, list[float]] = {
            "max_vram_used_mib": [],
            "max_gpu_utilization_percent": [],
            "max_memory_utilization_percent": [],
        }
        for index, sample in enumerate(samples):
            if (
                sample.get("sample_index") != index
                or not _positive_int(sample.get("sampled_at_ns"))
                or not isinstance(sample.get("sampled_at_utc"), str)
                or not sample["sampled_at_utc"]
                or not _positive_int(sample.get("sampled_monotonic_ns"))
                or sample["sampled_at_ns"] <= prior_sampled_at_ns
                or sample["sampled_monotonic_ns"] <= prior_monotonic_ns
            ):
                raise CampaignError(f"cold preboot GPU idle sample {index} time/index drift")
            prior_sampled_at_ns = sample["sampled_at_ns"]
            prior_monotonic_ns = sample["sampled_monotonic_ns"]
            if (
                sample.get("gpu_index") != 0
                or sample.get("gpu_uuid") != target_gpu["gpu_uuid"]
                or sample.get("gpu_name") != target_gpu["gpu_name"]
                or sample.get("vram_total_mib") != target_gpu["vram_total_mib"]
                or sample.get("driver_model_current") != "WDDM"
                or sample.get("display_active") not in {"Disabled", "Enabled"}
                or not isinstance(sample.get("query_argv"), list)
                or re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(sample.get("raw_stdout_sha256", "")),
                )
                is None
                or not _finite_real(sample.get("host_ram_used_bytes"))
                or not _finite_real(sample.get("host_ram_total_bytes"))
                or float(sample["host_ram_used_bytes"]) < 0
                or float(sample["host_ram_total_bytes"])
                < float(sample["host_ram_used_bytes"])
                or sample.get("quiescence_errors") != []
                or sample.get("quiescent") is not True
            ):
                raise CampaignError(f"cold preboot GPU idle sample {index} identity drift")
            activity_fields = (
                ("vram_used_mib", "max_vram_used_mib"),
                ("gpu_utilization_percent", "max_gpu_utilization_percent"),
                (
                    "memory_utilization_percent",
                    "max_memory_utilization_percent",
                ),
            )
            for sample_field, summary_field in activity_fields:
                value = sample.get(sample_field)
                if (
                    not _finite_real(value)
                    or float(value) < 0
                    or (
                        sample_field == "vram_used_mib"
                        and float(value) > float(target_gpu["vram_total_mib"])
                    )
                    or (
                        sample_field != "vram_used_mib"
                        and float(value) > 100.0
                    )
                ):
                    raise CampaignError(
                        f"cold preboot GPU idle sample {index} {sample_field} failed"
                    )
                observed[summary_field].append(float(value))
            listeners = sample.get("port_8199_listener_evidence") or {}
            if (
                listeners.get("port") != LAB_PORT
                or listeners.get("listeners") != []
                or listeners.get("listener_pids") != []
                or listeners.get("unknown_owner_count") != 0
            ):
                raise CampaignError(
                    f"cold preboot GPU idle sample {index} listener evidence failed"
                )
            lock = sample.get("gpu_lock") or {}
            receipt_bytes = (
                json.dumps(
                    lock.get("receipt"),
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            if (
                not isinstance(lock, dict)
                or lock.get("receipt") != lock_owner
                or lock.get("matches_expected_owner") is not True
                or lock.get("matches_acquired_owner") is not True
                or lock.get("receipt_sha256") != sha256_bytes(receipt_bytes)
                or os.path.normcase(os.path.abspath(str(lock.get("path", ""))))
                != os.path.normcase(os.path.abspath(os.fspath(layout.gpu_lock)))
                or lock.get("authorization") != "current standalone owner"
            ):
                raise CampaignError(
                    f"cold preboot GPU idle sample {index} lease evidence failed"
                )
            processes = sample.get("nvidia_process_evidence") or {}
            rows = processes.get("rows")
            if (
                processes.get("target_gpu_index") != 0
                or processes.get("target_gpu_uuid") != target_gpu["gpu_uuid"]
                or not isinstance(processes.get("query_argv"), list)
                or re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(processes.get("raw_stdout_sha256", "")),
                )
                is None
                or not isinstance(rows, list)
                or processes.get("row_count") != len(rows)
                or processes.get("blocking_rows") != []
            ):
                raise CampaignError(
                    f"cold preboot GPU idle sample {index} NVIDIA rows failed"
                )
            for row in rows:
                workload = (
                    row.get("known_workload_classification")
                    if isinstance(row, dict)
                    else None
                )
                workload_class = (
                    workload.get("classification")
                    if isinstance(workload, dict)
                    else None
                )
                redacted = (
                    workload.get("redacted_process")
                    if isinstance(workload, dict)
                    else None
                )
                workload_is_valid = (
                    workload_class == "clear"
                    and _redacted_workload_process_is_valid(redacted, "clear")
                ) or (
                    workload_class
                    == "advisory_unreadable_or_unmatched_python"
                    and _redacted_workload_process_is_valid(redacted, "advisory")
                )
                if (
                    not isinstance(row, dict)
                    or row.get("gpu_uuid") != target_gpu["gpu_uuid"]
                    or row.get("used_gpu_memory_token") != "[N/A]"
                    or row.get("classification")
                    != "allowed_unmetered_wddm_desktop_client"
                    or row.get("blocking_reasons") != []
                    or not isinstance(row.get("desktop_graphics_signals"), list)
                    or not isinstance(row.get("process_identity"), dict)
                    or (row.get("process_identity") or {}).get("exists") is not True
                    or not workload_is_valid
                ):
                    raise CampaignError(
                        f"cold preboot GPU idle sample {index} has an unqualified "
                        "NVIDIA process row"
                    )
            forbidden = sample.get("forbidden_process_scan") or {}
            excluded = forbidden.get("excluded_current_runner")
            advisories = forbidden.get("advisory_unreadable_processes")
            expected_forbidden_keys = {
                "scanned_process_count",
                "model_workload_markers",
                "classifier_contract",
                "current_runner_exclusion",
                "excluded_current_runner",
                "blocking_processes",
                "advisory_unreadable_processes",
            }
            if (
                set(forbidden) != expected_forbidden_keys
                or not _positive_int(forbidden.get("scanned_process_count"))
                or forbidden.get("model_workload_markers")
                != policy["model_workload_markers"]
                or forbidden.get("classifier_contract")
                != expected_known_workload_classifier_contract()
                or forbidden.get("current_runner_exclusion") != current_runner
                or forbidden.get("blocking_processes") != []
                or not isinstance(advisories, list)
                or not all(
                    _redacted_workload_process_is_valid(value, "advisory")
                    for value in advisories
                )
                or not isinstance(excluded, list)
            ):
                raise CampaignError(
                    f"cold preboot GPU idle sample {index} process scan failed"
                )
        expected_summary = {
            field: max(values) for field, values in observed.items()
        }
        if gate.get("summary") != expected_summary:
            raise CampaignError("cold preboot GPU idle summary was not recomputed")
    elif role == "warm":
        expected_warm_keys = {
            "schema_version",
            "kind",
            "status",
            "gate_ran",
            "reason",
            "contract",
            "server_instance",
            "evidence_sha256",
        }
        if (
            set(gate) != expected_warm_keys
            or
            gate.get("status") != "not-rerun-owned-server-reuse"
            or gate.get("gate_ran") is not False
            or gate.get("reason")
            != (
                "verified owned lab server already active; "
                "no fresh idle sampling claimed"
            )
            or "samples" in gate
            or "summary" in gate
        ):
            raise CampaignError("warm run made a fresh or ambiguous GPU idle claim")
    else:
        raise CampaignError("preboot GPU idle gate role must be cold or warm")
    return dict(gate)


def verify_idle_gate_sidecar_receipt(
    receipt: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    role: str,
    server_instance: Mapping[str, Any],
    layout: Layout,
    require_current: bool,
) -> dict[str, Any]:
    snapshot = receipt.get("preboot_gpu_idle_gate_sidecar")
    expected_keys = {
        "path",
        "bytes",
        "sha256",
        "identity",
        "evidence_sha256",
        "server_instance",
    }
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != expected_keys
        or os.path.normcase(os.path.abspath(str(snapshot.get("path", ""))))
        != os.path.normcase(os.path.abspath(os.fspath(layout.idle_gate_sidecar)))
        or not _positive_int(snapshot.get("bytes"))
        or re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("sha256", ""))) is None
        or not isinstance(snapshot.get("identity"), list)
        or len(snapshot["identity"]) != 6
        or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in snapshot["identity"]
        )
        or not stat.S_ISREG(snapshot["identity"][2])
        or snapshot["identity"][4] != snapshot.get("bytes")
        or snapshot["identity"][3] != 1
        or snapshot["identity"][0] < 0
        or snapshot["identity"][1] < 0
        or snapshot["identity"][5] <= 0
        or re.fullmatch(
            r"[0-9a-f]{64}", str(snapshot.get("evidence_sha256", ""))
        )
        is None
        or snapshot.get("server_instance") != dict(server_instance)
    ):
        raise CampaignError(f"{role} idle-gate sidecar receipt is invalid")
    if role == "cold" and snapshot.get("evidence_sha256") != gate.get(
        "evidence_sha256"
    ):
        raise CampaignError("cold idle-gate sidecar does not bind measured evidence")
    if role == "cold":
        expected_raw = (
            json.dumps(
                gate,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if (
            snapshot.get("bytes") != len(expected_raw)
            or snapshot.get("sha256") != sha256_bytes(expected_raw)
        ):
            raise CampaignError(
                "cold idle-gate sidecar bytes do not equal measured evidence"
            )
    if "preboot_gpu_idle_gate_sidecar" in (receipt.get("identity") or {}):
        raise CampaignError("variable idle-gate sidecar entered stable run identity")
    if require_current:
        current_evidence, current_snapshot = stable_idle_gate_sidecar(layout)
        if current_snapshot != snapshot:
            raise CampaignError("live idle-gate sidecar descriptor changed")
        if role != "cold" or current_evidence != dict(gate):
            raise CampaignError("live idle-gate sidecar does not equal cold evidence")
    return dict(snapshot)


def verify_run_receipt(
    spec: RecipeSpec,
    run_number: int,
    nonce: str,
    sources: Mapping[str, Any],
    layout: Layout = DEFAULT_LAYOUT,
    *,
    log_path: Path | None = None,
    role: str | None = None,
    require_sidecar_current: bool = False,
    require_alias_current: bool = True,
) -> dict[str, Any]:
    archive_path = layout.results / f"{spec.name}_run{run_number}.json"
    alias_path = layout.results / f"{spec.name}.json"
    receipt, archive_raw = strict_json(
        archive_path, f"{spec.name} immutable run {run_number} receipt"
    )
    if require_alias_current:
        _, alias_raw = strict_json(alias_path, f"{spec.name} current receipt")
        if alias_raw != archive_raw:
            raise CampaignError(f"{spec.name} current alias != immutable run {run_number}")

    expected_warm = run_number == 2
    if role is None:
        role = "warm" if expected_warm else "cold"
    if role != ("warm" if expected_warm else "cold"):
        raise CampaignError(f"{spec.name} run {run_number} Manager phase drift")
    nonce_campaign_id, nonce_pair_index, nonce_role = parse_executor_nonce(nonce)
    if nonce_role != role:
        raise CampaignError(f"{spec.name} run {run_number} nonce phase drift")
    expected_log_path = pair_log_path(
        spec, nonce_pair_index, nonce_campaign_id, layout
    )
    if log_path is None:
        log_path = expected_log_path
    elif os.path.normcase(os.path.abspath(os.fspath(log_path))) != os.path.normcase(
        os.path.abspath(os.fspath(expected_log_path))
    ):
        raise CampaignError(f"{spec.name} run {run_number} Manager log path drift")
    expected_statuses = (
        {"PASS", "PASS (marginal)"}
        if expected_warm
        else {"PASS (cold)", "PASS (cold, marginal)"}
    )
    required_equal = {
        "receipt_schema_version": 3,
        "recipe": spec.name,
        "run_number": run_number,
        "run_count": run_number,
        "config_run_count": run_number,
        "gate_pass": True,
        "pass": expected_warm,
        "warm_pass": expected_warm,
        "recipe_sha256": spec.sha256,
        "runner_sha256": sources["runner"]["sha256"],
        "lab_locks_sha256": sources["lab_locks"]["sha256"],
        "provenance_unchanged": True,
        "server_instance_unchanged": True,
        "valid_measurement": True,
        "accepted_prompt": True,
        "requires_human_eyeball": True,
        "eyeball": "pending",
        "promotion_ready": False,
        "certification_scope": "machine-only",
        "boot_lane": EXPECTED_BOOT_LANE,
        "clamp_target_gib": None,
        "reserve_vram_gib": None,
        "encoded_width": 832,
        "encoded_height": 480,
        "encoded_frame_count": spec.frames,
        "completion_timeout_s": completion_timeout_s(spec),
    }
    for field, expected in required_equal.items():
        if receipt.get(field) != expected:
            raise CampaignError(
                f"{spec.name} run {run_number} field {field} != {expected!r}: "
                f"{receipt.get(field)!r}"
            )
    baseline_vram = receipt.get("baseline_vram_gb")
    peak_vram = receipt.get("peak_vram_gb")
    duration = receipt.get("duration_s")
    vram_measurement = verify_operator_idle_measurement(
        receipt, f"{spec.name} run {run_number}"
    )
    baseline_advisory, drift_advisory = verify_operator_idle_advisories(
        receipt,
        role=role,
        label=f"{spec.name} run {run_number}",
    )
    if not _finite_real(duration) or float(duration) <= 0:
        raise CampaignError(f"{spec.name} run {run_number} wall duration is invalid")
    marginal = receipt.get("marginal")
    if not isinstance(marginal, bool):
        raise CampaignError(f"{spec.name} run {run_number} marginal flag is invalid")
    rounded_peak = float(peak_vram)
    if rounded_peak > 14.25 and marginal is not True:
        raise CampaignError(f"{spec.name} run {run_number} marginal flag is invalid")
    if rounded_peak < 14.25 and marginal is not False:
        raise CampaignError(f"{spec.name} run {run_number} marginal flag is invalid")
    # At exactly 14.25 the runner's unrounded value is unavailable: either side
    # of the threshold can round here.  The status must still match its boolean.
    expected_marginal = marginal
    if expected_warm:
        expected_status = "PASS (marginal)" if expected_marginal else "PASS"
    else:
        expected_status = (
            "PASS (cold, marginal)" if expected_marginal else "PASS (cold)"
        )
    if receipt.get("status") != expected_status or receipt.get("status") not in expected_statuses:
        raise CampaignError(
            f"{spec.name} run {run_number} has unexpected status {receipt.get('status')!r}"
        )
    encoded_fps = receipt.get("encoded_fps")
    if not _finite_real(encoded_fps) or abs(float(encoded_fps) - 24.0) > 1e-6:
        raise CampaignError(f"{spec.name} run {run_number} encoded fps drift")
    video_duration = receipt.get("video_duration_s")
    if not _finite_real(video_duration) or abs(
        float(video_duration) - spec.frames / 24.0
    ) > 1.0 / 24.0:
        raise CampaignError(f"{spec.name} run {run_number} video duration drift")
    if receipt.get("audio_present") is not True:
        raise CampaignError(f"{spec.name} run {run_number} lost native H3 audio")
    audio_duration = receipt.get("audio_duration_s")
    if (
        not _finite_real(audio_duration)
        or float(audio_duration) <= 0
        or abs(float(audio_duration) - spec.frames / 24.0) > 0.1
    ):
        raise CampaignError(f"{spec.name} run {run_number} audio duration drift")

    argv = validate_server_argv(receipt.get("server_argv"), layout)
    server_instance = receipt.get("server_instance")
    if not isinstance(server_instance, dict):
        raise CampaignError(f"{spec.name} run {run_number} has no server identity")
    if not _positive_int(server_instance.get("serving_pid")):
        raise CampaignError(f"{spec.name} run {run_number} has invalid serving PID")
    created = server_instance.get("process_create_time")
    if (
        isinstance(created, bool)
        or not isinstance(created, (int, float))
        or not math.isfinite(float(created))
        or float(created) <= 0
    ):
        raise CampaignError(f"{spec.name} run {run_number} has invalid create time")
    if receipt.get("final_server_instance") != server_instance:
        raise CampaignError(f"{spec.name} run {run_number} server identity changed")

    identity = receipt.get("identity")
    if not isinstance(identity, dict):
        raise CampaignError(f"{spec.name} run {run_number} identity is missing")
    if stable_identity(identity) != receipt.get("run_identity_sha256"):
        raise CampaignError(f"{spec.name} run {run_number} identity SHA mismatch")
    identity_expected = {
        "recipe_sha256": spec.sha256,
        "runner_sha256": sources["runner"]["sha256"],
        "lab_locks_sha256": sources["lab_locks"]["sha256"],
        "fixture_sha256s": dict(spec.fixture_hashes),
        "boot_lane": EXPECTED_BOOT_LANE,
        "server_argv": argv,
        "server_instance": server_instance,
        "completion_timeout_s": completion_timeout_s(spec),
    }
    for field, expected in identity_expected.items():
        if identity.get(field) != expected:
            raise CampaignError(
                f"{spec.name} run {run_number} identity field {field} drift"
            )
    if receipt.get("fixture_sha256s") != dict(spec.fixture_hashes):
        raise CampaignError(f"{spec.name} run {run_number} fixture hashes drift")
    models = validate_model_fingerprints(spec, receipt.get("model_fingerprints"))
    if identity.get("model_fingerprints") != models:
        raise CampaignError(f"{spec.name} run {run_number} identity model pins drift")
    audio_receipts = receipt.get("audio_receipt_sha256s")
    expected_audio_receipts = expected_audio_receipt_hashes(spec, layout)
    if audio_receipts != expected_audio_receipts or identity.get(
        "audio_receipt_sha256s"
    ) != expected_audio_receipts:
        raise CampaignError(f"{spec.name} run {run_number} audio receipt identity drift")
    comfyui_commit = receipt.get("comfyui_git_commit")
    if not isinstance(comfyui_commit, str) or re.fullmatch(
        r"[0-9a-f]{40}", comfyui_commit
    ) is None:
        raise CampaignError(f"{spec.name} run {run_number} ComfyUI commit is invalid")
    if identity.get("comfyui_git_commit") != comfyui_commit:
        raise CampaignError(f"{spec.name} run {run_number} ComfyUI commit identity drift")

    prequeue_workload_scan = verify_prequeue_known_workload_scan(
        receipt,
        sources=sources,
        server_instance=server_instance,
        server_argv=argv,
        label=f"{spec.name} run {run_number}",
    )

    cache = receipt.get("execution_cache_control")
    if not isinstance(cache, dict):
        raise CampaignError(f"{spec.name} run {run_number} cache evidence missing")
    expected_cache = expected_cache_contract(spec, nonce)
    if (
        cache.get("cache_event_found") is not True
        or cache.get("fresh_execution_proved") is not True
    ):
        raise CampaignError(f"{spec.name} run {run_number} cache nonce/execution unproved")
    for field, expected in expected_cache.items():
        if field == "queued_prompt_sha256":
            continue
        if cache.get(field) != expected:
            raise CampaignError(
                f"{spec.name} run {run_number} cache field {field} drift"
            )
    if cache.get("cached_fresh_node_ids") != []:
        raise CampaignError(f"{spec.name} run {run_number} cache closure is inconsistent")
    cached_ids = cache.get("cached_node_ids")
    if not isinstance(cached_ids, list) or len(set(cached_ids)) != len(cached_ids):
        raise CampaignError(f"{spec.name} run {run_number} cached node list is invalid")
    if not set(cached_ids).issubset(set(expected_cache["stable_node_ids"])):
        raise CampaignError(f"{spec.name} run {run_number} cached nodes escape stable closure")
    if not expected_warm and cached_ids != []:
        raise CampaignError(f"{spec.name} cold run contains cached node hits")
    if expected_warm and not set(expected_cache["stable_node_ids"]).issubset(
        set(cached_ids)
    ):
        raise CampaignError(f"{spec.name} warm run lacks every stable-node cache hit")
    cache_runtime = receipt.get("standalone_cache_runtime_sha256s")
    if (
        not isinstance(cache_runtime, dict)
        or set(cache_runtime) != EXPECTED_STANDALONE_CACHE_SOURCES
        or any(
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in cache_runtime.values()
        )
    ):
        raise CampaignError(f"{spec.name} run {run_number} cache runtime pins invalid")
    if cache_runtime != receipt.get("final_standalone_cache_runtime_sha256s"):
        raise CampaignError(f"{spec.name} run {run_number} cache runtime hashes changed")
    if identity.get("standalone_cache_runtime_sha256s") != cache_runtime:
        raise CampaignError(f"{spec.name} run {run_number} identity omits cache runtime")

    manager = verify_manager_receipt(
        receipt,
        log_path=log_path,
        argv=argv,
        role=role,
        recipe_name=spec.name,
        layout=layout,
    )
    expected_guard = sources.get("manager_guard") or {}
    expected_test_boot = sources.get("test_boot_cmd") or {}
    for phase in (manager["pre_queue"], manager["post_render"]):
        retained_guard = phase.get("guard_source") or {}
        retained_test_boot = phase.get("test_boot_source") or {}
        if (
            retained_guard.get("path") != expected_guard.get("path")
            or retained_guard.get("sha256") != expected_guard.get("sha256")
            or retained_test_boot.get("path") != expected_test_boot.get("path")
            or retained_test_boot.get("sha256") != expected_test_boot.get("sha256")
        ):
            raise CampaignError(
                "Manager guard/test-boot source is not campaign-bound"
            )
    idle_gate = verify_preboot_idle_gate(
        receipt,
        role=role,
        sources=sources,
        server_instance=server_instance,
        layout=layout,
    )
    idle_sidecar = verify_idle_gate_sidecar_receipt(
        receipt,
        idle_gate,
        role=role,
        server_instance=server_instance,
        layout=layout,
        require_current=require_sidecar_current,
    )

    expected_artifact_name = f"{spec.prefix}_{run_number:05d}_.mp4"
    artifact_path, artifact = strict_artifact(
        receipt.get("output_path"), expected_artifact_name, layout
    )
    if receipt.get("artifact_sha256") != artifact["sha256"]:
        raise CampaignError(f"{spec.name} run {run_number} artifact SHA mismatch")
    if receipt.get("artifact_bytes") != artifact["bytes"]:
        raise CampaignError(f"{spec.name} run {run_number} artifact byte count mismatch")
    prompt_sha = receipt.get("queued_prompt_sha256")
    if prompt_sha != expected_cache["queued_prompt_sha256"]:
        raise CampaignError(f"{spec.name} run {run_number} queued prompt SHA drift")
    return {
        "receipt": str(archive_path),
        "receipt_sha256": sha256_bytes(archive_raw),
        "alias": str(alias_path),
        "run_identity_sha256": receipt["run_identity_sha256"],
        "identity": identity,
        "server_instance": server_instance,
        "server_argv": argv,
        "queued_prompt_sha256": prompt_sha,
        "artifact": artifact,
        "artifact_path": str(artifact_path),
        "execution_cache_control": cache,
        "manager_offline_probe": manager,
        "preboot_gpu_idle_gate": idle_gate,
        "preboot_gpu_idle_gate_sidecar": idle_sidecar,
        "prequeue_known_workload_scan": prequeue_workload_scan,
        "peak_vram_gb": receipt.get("peak_vram_gb"),
        "baseline_vram_gb": vram_measurement["baseline_vram_gb"],
        "absolute_peak_vram_gb": vram_measurement["absolute_peak_vram_gb"],
        "net_peak_vram_gb": vram_measurement["net_peak_vram_gb"],
        "elevated_baseline_lane": vram_measurement["elevated_baseline_lane"],
        "baseline_lane_stamp": vram_measurement["baseline_lane_stamp"],
        "baseline_advisory": baseline_advisory,
        "cold_warm_baseline_drift_advisory": drift_advisory,
        "duration_s": receipt.get("duration_s"),
    }


def verify_pair(
    spec: RecipeSpec,
    pair_index: int,
    campaign_id: str,
    sources: Mapping[str, Any],
    cold_snapshot: Mapping[str, Any] | None = None,
    layout: Layout = DEFAULT_LAYOUT,
    log_path: Path | None = None,
) -> dict[str, Any]:
    if log_path is None:
        log_path = pair_log_path(spec, pair_index, campaign_id, layout)
    cold = verify_run_receipt(
        spec,
        1,
        executor_nonce(campaign_id, pair_index, "cold"),
        sources,
        layout,
        log_path=log_path,
        role="cold",
        require_alias_current=False,
    )
    warm = verify_run_receipt(
        spec,
        2,
        executor_nonce(campaign_id, pair_index, "warm"),
        sources,
        layout,
        log_path=log_path,
        role="warm",
    )
    if cold["run_identity_sha256"] != warm["run_identity_sha256"]:
        raise CampaignError(f"{spec.name} cold/warm run identity changed")
    if cold["identity"] != warm["identity"]:
        raise CampaignError(f"{spec.name} cold/warm identity payload changed")
    if cold["server_instance"] != warm["server_instance"]:
        raise CampaignError(f"{spec.name} warm run did not reuse cold server")
    if cold["server_argv"] != warm["server_argv"]:
        raise CampaignError(f"{spec.name} cold/warm server argv changed")
    baseline_drift = abs(
        float(cold["baseline_vram_gb"]) - float(warm["baseline_vram_gb"])
    )
    expected_recorded_drift = round(baseline_drift, 3)
    warm_drift_advisory = warm["cold_warm_baseline_drift_advisory"]
    if (
        warm_drift_advisory.get("previous_baseline_vram_gb")
        != cold["baseline_vram_gb"]
        or warm_drift_advisory.get("current_baseline_vram_gb")
        != warm["baseline_vram_gb"]
        or warm_drift_advisory.get("absolute_drift_gb")
        != expected_recorded_drift
        or warm_drift_advisory.get("threshold_exceeded")
        is not (expected_recorded_drift > 0.5)
    ):
        raise CampaignError(f"{spec.name} cold/warm drift advisory is not receipt-bound")
    if cold["preboot_gpu_idle_gate_sidecar"] != warm[
        "preboot_gpu_idle_gate_sidecar"
    ]:
        raise CampaignError(f"{spec.name} cold/warm idle-gate sidecar changed")
    if cold["preboot_gpu_idle_gate_sidecar"].get(
        "evidence_sha256"
    ) != cold["preboot_gpu_idle_gate"].get("evidence_sha256"):
        raise CampaignError(f"{spec.name} warm reuse is not bound to cold evidence")
    if (
        cold["preboot_gpu_idle_gate"].get("server_instance")
        != warm["preboot_gpu_idle_gate"].get("server_instance")
        or cold["preboot_gpu_idle_gate"].get("server_instance")
        != cold["server_instance"]
    ):
        raise CampaignError(f"{spec.name} idle-gate server identity changed")
    if cold["queued_prompt_sha256"] == warm["queued_prompt_sha256"]:
        raise CampaignError(f"{spec.name} unique executor nonces did not change prompt SHA")
    if cold_snapshot is not None:
        for field in ("receipt_sha256", "artifact"):
            if cold.get(field) != cold_snapshot.get(field):
                raise CampaignError(f"{spec.name} cold evidence changed after warm: {field}")
    extra_receipts = [
        path.name
        for path in layout.results.iterdir()
        if path.name.startswith(f"{spec.name}_run")
        and path.name not in {f"{spec.name}_run1.json", f"{spec.name}_run2.json"}
    ]
    expected_outputs = {
        Path(cold["artifact_path"]).name,
        Path(warm["artifact_path"]).name,
    }
    extra_outputs = [
        path.name
        for path in layout.outputs.iterdir()
        if path.name.startswith(spec.prefix) and path.name not in expected_outputs
    ]
    if extra_receipts or extra_outputs:
        raise CampaignError(
            f"{spec.name} produced unexpected evidence: receipts={extra_receipts}, "
            f"outputs={extra_outputs}"
        )
    return {
        "cold": cold,
        "warm": warm,
        "cold_warm_baseline_drift_gb": expected_recorded_drift,
        "cold_warm_baseline_drift_gating": False,
        "final_manager_log": verify_final_log(log_path, warm["server_argv"]),
    }


def read_lifecycle_records(path: Path) -> list[dict[str, Any]]:
    raw, _ = stable_file(path, "lifecycle ledger")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CampaignError("lifecycle ledger has a UTF-8 BOM")
    if raw and not raw.endswith(b"\n"):
        raise CampaignError("lifecycle ledger ends with a partial record")
    records: list[dict[str, Any]] = []
    previous: str | None = None
    campaign_sequences: dict[str, int] = {}
    for expected_sequence, line in enumerate(raw.splitlines(), start=1):
        if not line:
            raise CampaignError("lifecycle ledger contains a blank record")
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError(f"lifecycle ledger is malformed: {exc}") from exc
        if not isinstance(record, dict):
            raise CampaignError("lifecycle record is not an object")
        if record.get("schema_version") != 1:
            raise CampaignError("lifecycle record schema drifted")
        if record.get("ledger_sequence") != expected_sequence:
            raise CampaignError("lifecycle ledger sequence is not contiguous")
        campaign_id = record.get("campaign_id")
        if not isinstance(campaign_id, str):
            raise CampaignError("lifecycle record campaign id is invalid")
        validate_campaign_id(campaign_id)
        expected_campaign_sequence = campaign_sequences.get(campaign_id, 0) + 1
        if record.get("campaign_sequence") != expected_campaign_sequence:
            raise CampaignError("lifecycle campaign sequence is not contiguous")
        campaign_sequences[campaign_id] = expected_campaign_sequence
        digest = record.get("event_sha256")
        body = dict(record)
        body.pop("event_sha256", None)
        if digest != sha256_bytes(canonical_bytes(body)):
            raise CampaignError("lifecycle event SHA mismatch")
        if record.get("previous_event_sha256") != previous:
            raise CampaignError("lifecycle hash chain is broken")
        if not isinstance(record.get("event"), str) or not record["event"]:
            raise CampaignError("lifecycle event name is invalid")
        if not isinstance(record.get("details"), dict):
            raise CampaignError("lifecycle event details are invalid")
        previous = digest
        records.append(record)
    return records


class AppendOnlyLifecycle:
    def __init__(self, path: Path, campaign_id: str):
        self.path = Path(os.path.abspath(os.fspath(path)))
        self.campaign_id = validate_campaign_id(campaign_id)
        self.campaign_sequence = 0
        self.ledger_sequence = 0
        self.previous_event_sha256: str | None = None
        self._expected_bytes = b""
        self._prepare()

    def _prepare(self) -> None:
        parent = self.path.parent
        if not os.path.lexists(parent):
            parent.mkdir(parents=True, exist_ok=False)
        if _is_reparse(parent) or not parent.is_dir():
            raise CampaignError(f"lifecycle parent is not a real directory: {parent}")
        if not os.path.lexists(self.path):
            return
        if _is_reparse(self.path) or not self.path.is_file():
            raise CampaignError("lifecycle ledger is not a regular file")
        raw = self.path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CampaignError("lifecycle ledger has a UTF-8 BOM")
        previous = None
        campaign_ids = set()
        for expected_sequence, line in enumerate(raw.splitlines(), start=1):
            if not line:
                raise CampaignError("lifecycle ledger contains a blank record")
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CampaignError(f"lifecycle ledger is malformed: {exc}") from exc
            if record.get("ledger_sequence") != expected_sequence:
                raise CampaignError("lifecycle ledger sequence is not contiguous")
            digest = record.get("event_sha256")
            body = dict(record)
            body.pop("event_sha256", None)
            if digest != sha256_bytes(canonical_bytes(body)):
                raise CampaignError("lifecycle event SHA mismatch")
            if record.get("previous_event_sha256") != previous:
                raise CampaignError("lifecycle hash chain is broken")
            previous = digest
            campaign_ids.add(record.get("campaign_id"))
        if self.campaign_id in campaign_ids:
            raise CampaignError(f"campaign id already exists in lifecycle: {self.campaign_id}")
        self.ledger_sequence = len(raw.splitlines())
        self.previous_event_sha256 = previous
        self._expected_bytes = raw

    def append(self, event: str, details: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(event, str) or not event:
            raise CampaignError("lifecycle event must be nonempty text")
        self.campaign_sequence += 1
        self.ledger_sequence += 1
        body = {
            "schema_version": 1,
            "ledger_sequence": self.ledger_sequence,
            "campaign_id": self.campaign_id,
            "campaign_sequence": self.campaign_sequence,
            "event": event,
            "recorded_at_ns": time.time_ns(),
            "previous_event_sha256": self.previous_event_sha256,
            "details": dict(details),
        }
        digest = sha256_bytes(canonical_bytes(body))
        record = {**body, "event_sha256": digest}
        encoded = canonical_bytes(record) + b"\n"
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0)
        fd = os.open(str(self.path), flags, 0o600)
        locked = False
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                raise CampaignError("lifecycle ledger is owned by another writer") from exc
            locked = True
            os.lseek(fd, 0, os.SEEK_SET)
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            before = b"".join(chunks)
            if before != self._expected_bytes:
                raise CampaignError("lifecycle changed since this campaign last verified it")
            os.lseek(fd, 0, os.SEEK_END)
            offset = 0
            while offset < len(encoded):
                written = os.write(fd, encoded[offset:])
                if written <= 0:
                    raise CampaignError("short lifecycle append")
                offset += written
            os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = b"".join(chunks)
            if after != before + encoded:
                raise CampaignError("lifecycle append changed prior bytes")
        finally:
            if locked:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self._expected_bytes = after
        self.previous_event_sha256 = digest
        return record


def verified_resume_prefix(
    resume_from_campaign_id: str,
    specs: Sequence[RecipeSpec],
    sources: Mapping[str, Any],
    initial_manager: Mapping[str, Any],
    layout: Layout = DEFAULT_LAYOUT,
) -> list[dict[str, Any]]:
    resume_id = validate_campaign_id(resume_from_campaign_id)
    records = [
        record
        for record in read_lifecycle_records(layout.lifecycle)
        if record.get("campaign_id") == resume_id
    ]
    if not records:
        raise CampaignError(f"resume campaign is absent from lifecycle: {resume_id}")
    if records[0].get("event") != "campaign_started":
        raise CampaignError("resume campaign does not begin with campaign_started")
    if records[-1].get("event") != "campaign_failed":
        raise CampaignError("resume campaign is not sealed by campaign_failed")
    if any(record.get("event") == "campaign_completed" for record in records):
        raise CampaignError("cannot resume a completed campaign")
    if sum(record.get("event") == "campaign_started" for record in records) != 1:
        raise CampaignError("resume campaign has an ambiguous start record")
    started = records[0].get("details") or {}
    if started.get("sources") != dict(sources):
        raise CampaignError("resume campaign source pins differ from current sources")
    prior_plan = started.get("plan") or {}
    if prior_plan.get("pairs") != runbook(resume_id, layout).get("pairs"):
        raise CampaignError("resume campaign runbook pairs drifted")

    completed_by_index: dict[int, dict[str, Any]] = {}
    for record in records:
        if record.get("event") not in {"pair_verified", "pair_carried"}:
            continue
        details = record.get("details") or {}
        index = details.get("pair_index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= len(specs)
            or index in completed_by_index
        ):
            raise CampaignError("resume campaign completed-pair index is invalid")
        completed_by_index[index] = copy.deepcopy(details)
    if not completed_by_index:
        raise CampaignError("resume campaign has no complete pair to carry")
    expected_indices = list(range(1, len(completed_by_index) + 1))
    if sorted(completed_by_index) != expected_indices:
        raise CampaignError("resume campaign complete pairs are not a strict prefix")
    started_indices: list[int] = []
    allowed_started_indices = set(expected_indices)
    if len(expected_indices) < len(specs):
        allowed_started_indices.add(len(expected_indices) + 1)
    for record in records:
        if record.get("event") != "pair_started":
            continue
        index = (record.get("details") or {}).get("pair_index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index in started_indices
            or index not in allowed_started_indices
        ):
            raise CampaignError(
                "resume campaign failed away from a complete pair boundary"
            )
        started_indices.append(index)
    failed = records[-1].get("details") or {}
    if failed.get("completed_pair_count") != len(expected_indices):
        raise CampaignError("resume campaign failure pair count drifted")

    carried: list[dict[str, Any]] = []
    logs_by_campaign: dict[str, list[Path]] = {}
    for index in expected_indices:
        spec = specs[index - 1]
        row = completed_by_index[index]
        if row.get("pair_index") != index or row.get("recipe") != spec.name:
            raise CampaignError("resume campaign pair identity drifted")
        evidence_campaign_id = validate_campaign_id(
            row.get("evidence_campaign_id") or resume_id
        )
        log_path = pair_log_path(spec, index, evidence_campaign_id, layout)
        audited = verify_pair(
            spec,
            index,
            evidence_campaign_id,
            sources,
            layout=layout,
            log_path=log_path,
        )
        if row.get("pair") != audited:
            raise CampaignError(f"resume pair {index} evidence changed")
        post_state = row.get("post_shutdown_state")
        if not isinstance(post_state, dict):
            raise CampaignError(f"resume pair {index} has no shutdown state")
        require_clean_state(
            post_state,
            f"resume pair {index} recorded shutdown",
            require_idle_gate_field=True,
        )
        after_manager = row.get("manager_after_shutdown")
        if not isinstance(after_manager, dict):
            raise CampaignError(f"resume pair {index} has no Manager shutdown audit")
        require_same_manager_evidence(
            initial_manager,
            after_manager,
            f"resume pair {index} recorded shutdown",
        )
        carried_row = copy.deepcopy(row)
        carried_row["evidence_campaign_id"] = evidence_campaign_id
        carried.append(carried_row)
        logs_by_campaign.setdefault(evidence_campaign_id, []).append(log_path)
    for evidence_campaign_id, expected_logs in logs_by_campaign.items():
        require_attempt_manager_log_set(
            evidence_campaign_id,
            expected_logs,
            layout,
            label="resume prefix",
        )
    for spec in specs[len(carried) :]:
        ensure_pristine_history(spec, layout)
    return carried


def reverify_completed_pairs(
    completed_pairs: Sequence[Mapping[str, Any]],
    specs: Sequence[RecipeSpec],
    sources: Mapping[str, Any],
    layout: Layout = DEFAULT_LAYOUT,
) -> None:
    logs_by_campaign: dict[str, list[Path]] = {}
    for expected_index, row in enumerate(completed_pairs, start=1):
        if expected_index > len(specs):
            raise CampaignError("completed pair count exceeds canonical plan")
        spec = specs[expected_index - 1]
        if row.get("pair_index") != expected_index or row.get("recipe") != spec.name:
            raise CampaignError("completed pair prefix identity drifted")
        evidence_campaign_id = validate_campaign_id(
            str(row.get("evidence_campaign_id", ""))
        )
        log_path = pair_log_path(
            spec, expected_index, evidence_campaign_id, layout
        )
        audited = verify_pair(
            spec,
            expected_index,
            evidence_campaign_id,
            sources,
            layout=layout,
            log_path=log_path,
        )
        if row.get("pair") != audited:
            raise CampaignError(
                f"completed pair {expected_index} evidence changed during continuation"
            )
        logs_by_campaign.setdefault(evidence_campaign_id, []).append(log_path)
    for evidence_campaign_id, logs in logs_by_campaign.items():
        require_attempt_manager_log_set(
            evidence_campaign_id,
            logs,
            layout,
            label="completed-pair audit",
        )


ServerArgvValidator = Callable[[Any, Layout], list[str]]
ExpectedServerArgvBuilder = Callable[[Layout], list[str]]


def _live_server_argv(
    pid: int,
    layout: Layout,
    server_argv_validator: ServerArgvValidator = validate_server_argv,
) -> list[str]:
    try:
        command = psutil.Process(pid).cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise CampaignError(f"cannot inspect candidate lab server argv: {exc}") from exc
    expected_main = os.path.normcase(os.path.abspath(layout.comfyui_main))
    starts = [
        index
        for index, value in enumerate(command)
        if os.path.normcase(os.path.abspath(value)) == expected_main
    ]
    if len(starts) != 1:
        raise CampaignError("candidate process does not have one expected ComfyUI main.py")
    return server_argv_validator(command[starts[0] :], layout)


def _observe_descendant_server(
    runner_pid: int,
    runner_create_time: float,
    layout: Layout,
    server_argv_validator: ServerArgvValidator = validate_server_argv,
) -> dict[str, Any] | None:
    receipt_pid = _read_pid_receipt(layout.server_pid)
    if receipt_pid is None:
        return None
    try:
        runner = psutil.Process(runner_pid)
        if not math.isclose(
            float(runner.create_time()),
            runner_create_time,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise CampaignError("run_recipe child PID was reused during ownership watch")
        descendants = {child.pid for child in runner.children(recursive=True)}
        if receipt_pid not in descendants:
            return None
        server_process = psutil.Process(receipt_pid)
        server_create_time = round(float(server_process.create_time()), 6)
    except psutil.NoSuchProcess:
        return None
    except (psutil.AccessDenied, OSError) as exc:
        raise CampaignError(f"cannot inspect run_recipe child ancestry: {exc}") from exc
    # boot_lab_server.cmd initially receipts its cmd.exe wrapper.  Do not try
    # to classify that transitional process as ComfyUI: an owned serving
    # process is observable only once the receipted PID is the sole 8199
    # listener.  This also prevents a foreign listener from being adopted.
    if _listener_pids(LAB_PORT) != [receipt_pid]:
        return None
    server_argv = _live_server_argv(
        receipt_pid, layout, server_argv_validator
    )
    return {
        "serving_pid": receipt_pid,
        "process_create_time": server_create_time,
        "server_argv": server_argv,
        "observed_descendant_of_runner_pid": runner_pid,
        "runner_process_create_time": runner_create_time,
        "observed_at_ns": time.time_ns(),
    }


def _subprocess_child(
    command: Sequence[str],
    environment: Mapping[str, str],
    cwd: Path,
    layout: Layout,
    server_argv_validator: ServerArgvValidator = validate_server_argv,
) -> ChildOutcome:
    process = subprocess.Popen(list(command), cwd=str(cwd), env=dict(environment))
    errors: list[str] = []
    observations: dict[tuple[int, float], dict[str, Any]] = {}
    try:
        runner_create_time = round(float(psutil.Process(process.pid).create_time()), 6)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        runner_create_time = None
        errors.append(f"runner identity unavailable: {type(exc).__name__}: {exc}")
    while True:
        if runner_create_time is not None:
            try:
                observed = _observe_descendant_server(
                    process.pid,
                    runner_create_time,
                    layout,
                    server_argv_validator,
                )
            except CampaignError as exc:
                message = f"{type(exc).__name__}: {exc}"
                if message not in errors:
                    errors.append(message)
            else:
                if observed is not None:
                    key = (
                        observed["serving_pid"],
                        observed["process_create_time"],
                    )
                    observations[key] = observed
        returncode = process.poll()
        if returncode is not None:
            break
        time.sleep(0.05)
    return ChildOutcome(
        returncode=int(returncode),
        runner_pid=process.pid,
        runner_create_time=runner_create_time,
        descendant_server_instances=tuple(observations.values()),
        ownership_monitor_errors=tuple(errors),
    )


def normalize_child_outcome(value: Any) -> ChildOutcome:
    if isinstance(value, ChildOutcome):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return ChildOutcome(returncode=value)
    raise CampaignError(f"child runner returned an invalid outcome: {value!r}")


def require_observed_child_server(
    outcome: ChildOutcome,
    identity: Mapping[str, Any],
    layout: Layout,
    expected_server_argv_builder: ExpectedServerArgvBuilder = expected_server_argv,
) -> None:
    if outcome.ownership_monitor_errors:
        raise CampaignError(
            "run_recipe child ownership monitor reported errors: "
            + "; ".join(outcome.ownership_monitor_errors)
        )
    expected = (
        identity.get("serving_pid"),
        identity.get("process_create_time"),
    )
    matches = [
        observation
        for observation in outcome.descendant_server_instances
        if (
            observation.get("serving_pid"),
            observation.get("process_create_time"),
        )
        == expected
        and observation.get("server_argv")
        == expected_server_argv_builder(layout)
        and observation.get("observed_descendant_of_runner_pid")
        == outcome.runner_pid
        and observation.get("runner_process_create_time")
        == outcome.runner_create_time
    ]
    if len(matches) != 1:
        raise CampaignError(
            "cold server was not uniquely observed as an exact run_recipe child descendant"
        )


def pending_child_owned_server(
    outcome: ChildOutcome | None,
    state: Mapping[str, Any],
    layout: Layout,
    server_argv_validator: ServerArgvValidator = validate_server_argv,
    expected_server_argv_builder: ExpectedServerArgvBuilder = expected_server_argv,
) -> dict[str, Any] | None:
    if outcome is None:
        return None
    pid = state.get("server_pid_receipt")
    created = state.get("server_pid_create_time")
    if (
        not _positive_int(pid)
        or isinstance(created, bool)
        or not isinstance(created, (int, float))
        or state.get("listener_pids_8199") != [pid]
    ):
        return None
    identity = {"serving_pid": pid, "process_create_time": created}
    try:
        require_observed_child_server(
            outcome,
            identity,
            layout,
            expected_server_argv_builder,
        )
        current_create = round(float(psutil.Process(pid).create_time()), 6)
        if not math.isclose(
            current_create, float(created), rel_tol=0.0, abs_tol=0.001
        ):
            return None
        _live_server_argv(pid, layout, server_argv_validator)
    except (CampaignError, psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None
    return identity


def _default_cleanup() -> dict[str, Any]:
    runner = load_runner_verifier(DEFAULT_LAYOUT.runner)
    shutdown = getattr(runner, "shutdown_lab_server", None)
    if not callable(shutdown):
        raise CampaignError("hash-bound run_recipe.py lacks shutdown_lab_server")
    return shutdown()


def execute_campaign(
    *,
    campaign_id: str | None = None,
    resume_from_campaign_id: str | None = None,
    layout: Layout = DEFAULT_LAYOUT,
    child_runner: Callable[[Sequence[str], Mapping[str, str], Path], Any] | None = None,
    state_probe: Callable[[Mapping[str, Any] | None], dict[str, Any]] | None = None,
    manager_probe: Callable[[], dict[str, Any]] | None = None,
    cleanup_owned_server: Callable[[], dict[str, Any]] = _default_cleanup,
) -> dict[str, Any]:
    campaign_id = validate_campaign_id(campaign_id or campaign_id_now())
    if resume_from_campaign_id is not None:
        resume_from_campaign_id = validate_campaign_id(resume_from_campaign_id)
        if resume_from_campaign_id == campaign_id:
            raise CampaignError("resume campaign id must differ from the new campaign id")
    specs = load_recipe_specs(layout)
    plan = runbook(campaign_id, layout, resume_from_campaign_id)
    sources = source_evidence(layout)
    probe_state = state_probe or (
        lambda expected=None: runtime_state(expected, layout)
    )
    probe_manager = manager_probe or (lambda: manager_evidence(layout))
    invoke_child = child_runner or (
        lambda command, environment, cwd: _subprocess_child(
            command, environment, cwd, layout
        )
    )
    ledger = AppendOnlyLifecycle(layout.lifecycle, campaign_id)
    ledger.append(
        "campaign_started",
        {
            "plan": plan,
            "sources": sources,
            "otr_touched": False,
            "execution_authority": "run_recipe.py only",
            "resume_from_campaign_id": resume_from_campaign_id,
        },
    )
    owned_server: dict[str, Any] | None = None
    pending_cold_outcome: ChildOutcome | None = None
    completed_pairs: list[dict[str, Any]] = []
    carried_pair_count = 0
    try:
        initial_manager = probe_manager()
        initial_state = probe_state(None)
        require_clean_state(
            initial_state,
            "campaign initial state",
            require_idle_gate_field=True,
        )
        if resume_from_campaign_id is not None:
            completed_pairs = verified_resume_prefix(
                resume_from_campaign_id,
                specs,
                sources,
                initial_manager,
                layout,
            )
            carried_pair_count = len(completed_pairs)
            for completed in completed_pairs:
                ledger.append("pair_carried", completed)
        for spec in specs:
            require_recipe_unchanged(spec)
            require_fixtures_unchanged(spec, layout)
        for spec in specs[carried_pair_count:]:
            ensure_pristine_history(spec, layout)
        require_attempt_manager_log_set(
            campaign_id,
            [],
            layout,
            label="new campaign preflight",
        )
        log_root = layout.results / "h3_canonical_canvas_campaign" / "server_logs"
        if not os.path.lexists(log_root):
            log_root.mkdir(parents=False, exist_ok=False)
        ensure_real_directory(log_root, "canonical Manager log directory")
        ledger.append(
            "campaign_preflight_passed",
            {
                "manager": initial_manager,
                "state": initial_state,
                "all_undone_recipe_histories_pristine": True,
                "carried_pair_count": carried_pair_count,
                "carried_from_campaign_id": resume_from_campaign_id,
                "new_campaign_manager_log_set_empty": True,
            },
        )

        for pair_index in range(carried_pair_count + 1, len(specs) + 1):
            spec = specs[pair_index - 1]
            reverify_completed_pairs(completed_pairs, specs, sources, layout)
            expected_current_logs = [
                pair_log_path(
                    specs[row["pair_index"] - 1],
                    row["pair_index"],
                    campaign_id,
                    layout,
                )
                for row in completed_pairs
                if row.get("evidence_campaign_id") == campaign_id
            ]
            require_attempt_manager_log_set(
                campaign_id,
                expected_current_logs,
                layout,
                label=f"pair {pair_index} boundary",
            )
            current_sources = source_evidence(layout)
            require_same_source_evidence(
                sources, current_sources, f"pair {pair_index} before cold boot"
            )
            before_manager = probe_manager()
            require_same_manager_evidence(
                initial_manager, before_manager, f"pair {pair_index} before cold boot"
            )
            before_state = probe_state(None)
            require_clean_state(
                before_state,
                f"pair {pair_index} before cold boot",
                require_idle_gate_field=True,
            )
            require_recipe_unchanged(spec)
            require_fixtures_unchanged(spec, layout)
            ensure_pristine_history(spec, layout)
            log_path = pair_log_path(spec, pair_index, campaign_id, layout)
            if os.path.lexists(log_path):
                raise CampaignError(
                    f"attempt-unique Manager log already exists: {log_path}"
                )
            environment = child_environment(log_path)
            cold_command = child_command(
                spec, pair_index, "cold", campaign_id, layout
            )
            warm_command = child_command(
                spec, pair_index, "warm", campaign_id, layout
            )
            ledger.append(
                "pair_started",
                {
                    "pair_index": pair_index,
                    "recipe": spec.name,
                    "manager_before_boot": before_manager,
                    "manager_log": str(log_path),
                    "completion_timeout_s": completion_timeout_s(spec),
                    "cold_argv": cold_command,
                    "warm_shutdown_argv": warm_command,
                },
            )
            cold_outcome = normalize_child_outcome(
                invoke_child(cold_command, environment, layout.root)
            )
            pending_cold_outcome = cold_outcome
            ledger.append(
                "cold_child_returned",
                {
                    "pair_index": pair_index,
                    "recipe": spec.name,
                    "child_outcome": cold_outcome.as_dict(),
                },
            )
            if cold_outcome.returncode != 0:
                raise CampaignError(
                    f"{spec.name} cold run_recipe child returned {cold_outcome.returncode}"
                )
            cold = verify_run_receipt(
                spec,
                1,
                executor_nonce(campaign_id, pair_index, "cold"),
                sources,
                layout,
                log_path=log_path,
                role="cold",
                require_sidecar_current=True,
            )
            require_observed_child_server(
                cold_outcome, cold["server_instance"], layout
            )
            owned_server = dict(cold["server_instance"])
            pending_cold_outcome = None
            cold_state = probe_state(owned_server)
            require_warm_server_state(
                cold_state,
                owned_server,
                f"{spec.name} cold-to-warm boundary",
                idle_gate_sidecar=cold["preboot_gpu_idle_gate_sidecar"],
            )
            before_warm_manager = probe_manager()
            require_same_manager_evidence(
                initial_manager, before_warm_manager, f"{spec.name} before warm"
            )
            before_warm_sources = source_evidence(layout)
            require_same_source_evidence(
                sources, before_warm_sources, f"{spec.name} before warm"
            )
            require_recipe_unchanged(spec)
            require_fixtures_unchanged(spec, layout)
            ledger.append(
                "cold_verified",
                {
                    "pair_index": pair_index,
                    "recipe": spec.name,
                    "cold": cold,
                    "cold_to_warm_state": cold_state,
                    "manager_before_warm": before_warm_manager,
                },
            )
            warm_outcome = normalize_child_outcome(
                invoke_child(warm_command, environment, layout.root)
            )
            ledger.append(
                "warm_shutdown_child_returned",
                {
                    "pair_index": pair_index,
                    "recipe": spec.name,
                    "child_outcome": warm_outcome.as_dict(),
                },
            )
            if warm_outcome.returncode != 0:
                raise CampaignError(
                    f"{spec.name} warm run_recipe child returned {warm_outcome.returncode}"
                )
            after_warm_sources = source_evidence(layout)
            require_same_source_evidence(
                sources, after_warm_sources, f"{spec.name} after warm"
            )
            require_recipe_unchanged(spec)
            require_fixtures_unchanged(spec, layout)
            pair = verify_pair(
                spec,
                pair_index,
                campaign_id,
                sources,
                cold_snapshot=cold,
                layout=layout,
                log_path=log_path,
            )
            after_state = probe_state(owned_server)
            require_clean_state(
                after_state,
                f"{spec.name} post-warm shutdown",
                require_idle_gate_field=True,
            )
            after_manager = probe_manager()
            require_same_manager_evidence(
                initial_manager, after_manager, f"{spec.name} after warm shutdown"
            )
            completed = {
                "pair_index": pair_index,
                "recipe": spec.name,
                "pair": pair,
                "post_shutdown_state": after_state,
                "manager_after_shutdown": after_manager,
                "evidence_campaign_id": campaign_id,
            }
            completed_pairs.append(completed)
            ledger.append("pair_verified", completed)
            owned_server = None
            require_attempt_manager_log_set(
                campaign_id,
                [
                    pair_log_path(
                        specs[row["pair_index"] - 1],
                        row["pair_index"],
                        campaign_id,
                        layout,
                    )
                    for row in completed_pairs
                    if row.get("evidence_campaign_id") == campaign_id
                ],
                layout,
                label=f"pair {pair_index} completed",
            )
            reverify_completed_pairs(completed_pairs, specs, sources, layout)

        final_state = probe_state(None)
        require_clean_state(
            final_state,
            "campaign final state",
            require_idle_gate_field=True,
        )
        final_manager = probe_manager()
        require_same_manager_evidence(
            initial_manager, final_manager, "campaign final audit"
        )
        final_sources = source_evidence(layout)
        require_same_source_evidence(sources, final_sources, "campaign final audit")
        if len(completed_pairs) != len(specs):
            raise CampaignError("campaign pair count changed before final audit")
        reverify_completed_pairs(completed_pairs, specs, sources, layout)
        final_evidence: list[dict[str, Any]] = []
        for pair_index, (spec, completed) in enumerate(
            zip(specs, completed_pairs), start=1
        ):
            require_recipe_unchanged(spec)
            require_fixtures_unchanged(spec, layout)
            audited_pair = completed["pair"]
            final_evidence.append(
                {
                    "pair_index": pair_index,
                    "recipe": spec.name,
                    "evidence_campaign_id": completed["evidence_campaign_id"],
                    "cold_receipt_sha256": audited_pair["cold"]["receipt_sha256"],
                    "warm_receipt_sha256": audited_pair["warm"]["receipt_sha256"],
                    "cold_artifact_sha256": audited_pair["cold"]["artifact"]["sha256"],
                    "warm_artifact_sha256": audited_pair["warm"]["artifact"]["sha256"],
                    "cold_vram": {
                        key: audited_pair["cold"][key]
                        for key in (
                            "baseline_vram_gb",
                            "absolute_peak_vram_gb",
                            "net_peak_vram_gb",
                            "elevated_baseline_lane",
                            "baseline_lane_stamp",
                        )
                    },
                    "warm_vram": {
                        key: audited_pair["warm"][key]
                        for key in (
                            "baseline_vram_gb",
                            "absolute_peak_vram_gb",
                            "net_peak_vram_gb",
                            "elevated_baseline_lane",
                            "baseline_lane_stamp",
                        )
                    },
                    "cold_warm_baseline_drift_gb": audited_pair[
                        "cold_warm_baseline_drift_gb"
                    ],
                    "cold_warm_baseline_drift_gating": False,
                    "cold_baseline_advisory": audited_pair["cold"][
                        "baseline_advisory"
                    ],
                    "warm_baseline_advisory": audited_pair["warm"][
                        "baseline_advisory"
                    ],
                    "cold_warm_baseline_drift_advisory": audited_pair["warm"][
                        "cold_warm_baseline_drift_advisory"
                    ],
                    "cold_prequeue_workload_scan_sha256": audited_pair["cold"][
                        "prequeue_known_workload_scan"
                    ]["evidence_sha256"],
                    "cold_prequeue_advisory_unreadable_process_count": len(
                        audited_pair["cold"]["prequeue_known_workload_scan"][
                            "advisory_unreadable_processes"
                        ]
                    ),
                    "warm_prequeue_workload_scan_sha256": audited_pair["warm"][
                        "prequeue_known_workload_scan"
                    ]["evidence_sha256"],
                    "warm_prequeue_advisory_unreadable_process_count": len(
                        audited_pair["warm"]["prequeue_known_workload_scan"][
                            "advisory_unreadable_processes"
                        ]
                    ),
                    "cold_preboot_advisory_unreadable_process_counts": [
                        len(
                            sample["forbidden_process_scan"][
                                "advisory_unreadable_processes"
                            ]
                        )
                        for sample in audited_pair["cold"][
                            "preboot_gpu_idle_gate"
                        ]["samples"]
                    ],
                    "cold_preboot_display_active": {
                        "target": audited_pair["cold"][
                            "preboot_gpu_idle_gate"
                        ]["target_gpu"]["display_active"],
                        "samples": [
                            sample["display_active"]
                            for sample in audited_pair["cold"][
                                "preboot_gpu_idle_gate"
                            ]["samples"]
                        ],
                        "gating": False,
                    },
                    "cold_preboot_current_runner_exclusion_count": (
                        audited_pair["cold"]["preboot_gpu_idle_gate"][
                            "current_runner_exclusion"
                        ]["expected_excluded_process_count"]
                    ),
                    "cold_prequeue_current_runner_exclusion_count": len(
                        audited_pair["cold"]["prequeue_known_workload_scan"][
                            "excluded_current_runner"
                        ]
                    ),
                    "warm_prequeue_current_runner_exclusion_count": len(
                        audited_pair["warm"]["prequeue_known_workload_scan"][
                            "excluded_current_runner"
                        ]
                    ),
                    "cold_prequeue_owned_server_exclusion_count": len(
                        audited_pair["cold"]["prequeue_known_workload_scan"][
                            "excluded_owned_lab_server"
                        ]
                    ),
                    "warm_prequeue_owned_server_exclusion_count": len(
                        audited_pair["warm"]["prequeue_known_workload_scan"][
                            "excluded_owned_lab_server"
                        ]
                    ),
                    "manager_log": {
                        key: audited_pair["final_manager_log"]["log"][key]
                        for key in ("path", "bytes", "sha256")
                    },
                }
            )
        ledger.append(
            "campaign_completed",
            {
                "status": "COMPLETE",
                "pair_count": len(completed_pairs),
                "carried_pair_count": carried_pair_count,
                "pairs": completed_pairs,
                "final_state": final_state,
                "final_manager": final_manager,
                "final_sources": final_sources,
                "final_evidence_audit": final_evidence,
            },
        )
        return {
            "status": "COMPLETE",
            "campaign_id": campaign_id,
            "pairs": completed_pairs,
            "carried_pair_count": carried_pair_count,
            "lifecycle": str(layout.lifecycle),
        }
    except Exception as exc:
        failure_state: dict[str, Any]
        cleanup_identity = owned_server
        try:
            failure_state = probe_state(cleanup_identity)
            if cleanup_identity is None:
                cleanup_identity = pending_child_owned_server(
                    pending_cold_outcome, failure_state, layout
                )
                if cleanup_identity is not None:
                    failure_state = probe_state(cleanup_identity)
        except Exception as state_exc:
            failure_state = {"probe_error": f"{type(state_exc).__name__}: {state_exc}"}
        cleanup: dict[str, Any] = {"attempted": False}
        if (
            cleanup_identity is not None
            and failure_state.get("server_pid_receipt")
            == cleanup_identity.get("serving_pid")
            and failure_state.get("listener_pids_8199")
            == [cleanup_identity.get("serving_pid")]
            and failure_state.get("expected_server_identity_live") is True
            and failure_state.get("gpu_lock_exists") is False
            and failure_state.get("suite_lock_exists") is False
        ):
            cleanup = {"attempted": True}
            try:
                result = cleanup_owned_server()
                cleanup["run_recipe_shutdown_result"] = result
                cleanup["post_cleanup_state"] = probe_state(cleanup_identity)
                require_clean_state(
                    cleanup["post_cleanup_state"],
                    "failure cleanup final state",
                    require_idle_gate_field=True,
                )
                cleanup["success"] = True
            except Exception as cleanup_exc:
                cleanup["success"] = False
                cleanup["error"] = (
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                )
        try:
            ledger.append(
                "campaign_failed",
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "completed_pair_count": len(completed_pairs),
                    "carried_pair_count": carried_pair_count,
                    "failure_state": failure_state,
                    "pending_cold_child_outcome": (
                        pending_cold_outcome.as_dict()
                        if pending_cold_outcome is not None
                        else None
                    ),
                    "owned_server_cleanup": cleanup,
                    "stopped_without_force_or_additional_render": True,
                },
            )
        except Exception as ledger_exc:
            raise CampaignError(
                f"campaign failed ({type(exc).__name__}: {exc}) and lifecycle append "
                f"also failed ({type(ledger_exc).__name__}: {ledger_exc})"
            ) from exc
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="execute the six cold/warm pairs; default only prints the runbook",
    )
    parser.add_argument(
        "--campaign-id",
        help="optional unique append-only lifecycle identity",
    )
    parser.add_argument(
        "--resume-from-campaign-id",
        help=(
            "carry only the fully reverified strict pair prefix from a separately "
            "identified, terminally failed campaign"
        ),
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None, *, layout: Layout = DEFAULT_LAYOUT
) -> int:
    args = parse_args(argv)
    if not args.run:
        dry_id = validate_campaign_id(args.campaign_id or "DRY-RUN")
        sys.stdout.buffer.write(
            (
                json.dumps(
                    runbook(dry_id, layout, args.resume_from_campaign_id),
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
        )
        return 0
    try:
        result = execute_campaign(
            campaign_id=args.campaign_id,
            resume_from_campaign_id=args.resume_from_campaign_id,
            layout=layout,
        )
    except Exception as exc:
        print(f"[H3 CAMPAIGN FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
