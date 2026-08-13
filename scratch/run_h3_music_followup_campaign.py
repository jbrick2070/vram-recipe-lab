#!/usr/bin/env python3
"""Fail-closed coordinator for the queued H3 music follow-up mission.

The default invocation prints a read-only runbook.  Only ``--run`` may create
recipes or launch children.  Job 1 is a local-schema rejection finding, not a
render.  Jobs 2-4 are eleven ordered exploratory cold legs; every leg delegates
one prompt to ``run_recipe.py`` with Manager offline proof and ``--shutdown``.
No conditional bonus is implemented.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
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
from typing import Any, Mapping, Sequence

import psutil

import build_h3_music_followup as builder
import h3_manager_offline_guard as manager_guard


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_ROOT = ROOT / "results" / "h3_music_followup_campaign"
SERVER_LOGS = CAMPAIGN_ROOT / "server_logs"
CAMPAIGNS = CAMPAIGN_ROOT / "campaigns"
RUNNER = ROOT / "run_recipe.py"
LAB_LOCKS = ROOT / "lab_locks.py"
TEST_BOOT = ROOT / "boot_h3_manager_offline_test.cmd"
MANAGER_GUARD = ROOT / "scratch" / "h3_manager_offline_guard.py"
DESCRIPTOR_WRAPPER = (
    ROOT / "scratch" / "h3_music_machine_descriptors" / "analyze_manifest.py"
)
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")
COMFYUI_MAIN = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py")
COMFY_USER = Path(r"C:\Users\jeffr\Documents\ComfyUI")
EXPECTED_BOOT_LANE = (
    "lab-8199, sage-free, manager-offline-test, no-pinned, "
    "cache-classic, reserve-12gb"
)
EXPECTED_PORTRAIT_SHA256 = (
    "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
)
CAMPAIGN_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,80}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
LAB_PORT = 8199
ELEVATED_BASELINE_THRESHOLD_GB = 2.0
ELEVATED_BASELINE_STAMP = (
    "elevated-baseline lane, operator-authorized 2026-08-10"
)
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


class CampaignError(RuntimeError):
    """Campaign evidence could not prove a required invariant."""


@dataclass(frozen=True)
class Layout:
    root: Path = ROOT
    campaign_root: Path = CAMPAIGN_ROOT
    server_logs: Path = SERVER_LOGS
    campaigns: Path = CAMPAIGNS
    runner: Path = RUNNER
    lab_locks: Path = LAB_LOCKS
    test_boot: Path = TEST_BOOT
    manager_guard: Path = MANAGER_GUARD
    descriptor_wrapper: Path = DESCRIPTOR_WRAPPER
    descriptor_analyzer: Path = DESCRIPTOR_WRAPPER.with_name("analyze.py")
    builder: Path = Path(builder.__file__).resolve()
    python: Path = PYTHON
    comfyui_main: Path = COMFYUI_MAIN
    comfy_user: Path = COMFY_USER
    outputs: Path = ROOT / "outputs"
    results: Path = ROOT / "results"
    gpu_lock: Path = ROOT / ".gpu.lock"
    suite_lock: Path = ROOT / ".suite.lock"
    server_pid: Path = ROOT / ".server.pid"
    server_idle_gate: Path = ROOT / ".server.idle-gate.json"
    queue_quarantine: Path = ROOT / ".queue.quarantine.json"


DEFAULT_LAYOUT = Layout()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def campaign_id_now() -> str:
    return datetime.now(timezone.utc).strftime("h3followup-%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)


def validate_campaign_id(value: str) -> str:
    if CAMPAIGN_ID_RE.fullmatch(value) is None:
        raise CampaignError("campaign id must match [A-Za-z0-9_.-]{1,80}")
    return value


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = int(getattr(os.lstat(path), "st_file_attributes", 0))
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def require_safe_regular(path: Path, root: Path, label: str) -> Path:
    lexical_root = Path(os.path.abspath(os.fspath(root)))
    lexical = Path(os.path.abspath(os.fspath(path)))
    if os.path.lexists(lexical_root) and is_reparse_or_symlink(lexical_root):
        raise CampaignError(f"{label} root is a reparse point: {lexical_root}")
    try:
        relative = lexical.relative_to(lexical_root)
    except ValueError as exc:
        raise CampaignError(f"{label} escapes {lexical_root}: {lexical}") from exc
    component = lexical_root
    for part in relative.parts:
        component = component / part
        if os.path.lexists(component) and is_reparse_or_symlink(component):
            raise CampaignError(f"{label} path contains a reparse point: {component}")
    if not os.path.lexists(lexical) or not lexical.is_file():
        raise CampaignError(f"{label} is not a regular file: {lexical}")
    try:
        if lexical.resolve(strict=True) != lexical:
            raise CampaignError(f"{label} does not resolve exactly: {lexical}")
    except OSError as exc:
        raise CampaignError(f"cannot resolve {label}: {lexical}: {exc}") from exc
    return lexical


def require_safe_directory(path: Path, root: Path, label: str) -> Path:
    lexical_root = Path(os.path.abspath(os.fspath(root)))
    lexical = Path(os.path.abspath(os.fspath(path)))
    if os.path.lexists(lexical_root) and is_reparse_or_symlink(lexical_root):
        raise CampaignError(f"{label} root is a reparse point: {lexical_root}")
    try:
        relative = lexical.relative_to(lexical_root)
    except ValueError as exc:
        raise CampaignError(f"{label} escapes {lexical_root}: {lexical}") from exc
    component = lexical_root
    for part in relative.parts:
        component = component / part
        if os.path.lexists(component) and is_reparse_or_symlink(component):
            raise CampaignError(f"{label} path contains a reparse point: {component}")
    if not lexical.is_dir() or lexical.resolve(strict=True) != lexical:
        raise CampaignError(f"{label} is not an exact real directory: {lexical}")
    return lexical


def canonical_compact(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def canonical_pretty(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def strict_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CampaignError(f"{label} contains a UTF-8 BOM")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CampaignError(f"{label} must be a JSON object")
    return value, raw


def write_exclusive_json(path: Path, payload: Any) -> dict[str, Any]:
    raw = canonical_pretty(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return {"path": str(path), "bytes": len(raw), "sha256": sha256_bytes(raw)}


def require_exact_json(path: Path, payload: Any, label: str) -> dict[str, Any]:
    expected = canonical_pretty(payload)
    if path.exists():
        require_safe_regular(path, path.parent, label)
        actual = path.read_bytes()
        if actual != expected:
            raise CampaignError(f"{label} exists with different bytes: {path}")
        return {"path": str(path), "bytes": len(actual), "sha256": sha256_bytes(actual)}
    return write_exclusive_json(path, payload)


def source_evidence(layout: Layout) -> dict[str, dict[str, Any]]:
    paths = {
        "runner": layout.runner,
        "lab_locks": layout.lab_locks,
        "test_boot": layout.test_boot,
        "manager_guard": layout.manager_guard,
        "builder": layout.builder,
        "descriptor_wrapper": layout.descriptor_wrapper,
        "descriptor_analyzer": layout.descriptor_analyzer,
    }
    evidence = {}
    for label, path in paths.items():
        safe = require_safe_regular(path, layout.root, f"{label} source")
        evidence[label] = {
            "path": str(safe),
            "bytes": safe.stat().st_size,
            "sha256": sha256_file(safe),
        }
    return evidence


def require_sources(expected: Mapping[str, Any], layout: Layout, label: str) -> None:
    actual = source_evidence(layout)
    if actual != expected:
        raise CampaignError(f"source evidence drift at {label}")


def load_runner_verifier(layout: Layout = DEFAULT_LAYOUT) -> Any:
    module_name = "_h3_music_followup_receipt_runner"
    spec = importlib.util.spec_from_file_location(module_name, layout.runner)
    if spec is None or spec.loader is None:
        raise CampaignError(f"cannot load runner verifier: {layout.runner}")
    root_text = str(layout.root)
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
        "gpu_idle_gate_contract",
        "gpu_idle_gate_validation_errors",
        "operator_idle_policy_contract",
        "known_workload_classifier_contract",
        "current_runner_exclusion_validation_errors",
        "owned_lab_server_exclusion_validation_errors",
        "redacted_workload_process_validation_errors",
        "prequeue_known_workload_scan_contract",
        "prequeue_known_workload_scan_validation_errors",
        "stable_identity",
        "apply_standalone_cache_nonce",
    ):
        if not callable(getattr(module, name, None)):
            raise CampaignError(f"run_recipe.py no longer exposes verifier {name}")
    if not isinstance(getattr(module, "STANDALONE_CACHE_RUNTIME_SOURCES", None), dict):
        raise CampaignError("run_recipe.py lacks the standalone cache source contract")
    return module


def campaign_dir(campaign_id: str, layout: Layout = DEFAULT_LAYOUT) -> Path:
    return layout.campaigns / campaign_id


def lifecycle_path(campaign_id: str, layout: Layout = DEFAULT_LAYOUT) -> Path:
    return campaign_dir(campaign_id, layout) / "lifecycle.jsonl"


def manager_log_path(
    campaign_id: str, spec: builder.FollowupSpec, layout: Layout = DEFAULT_LAYOUT
) -> Path:
    return layout.server_logs / f"{campaign_id}-o{spec.order:02d}-{spec.name}.log"


def expected_nonce(campaign_id: str, spec: builder.FollowupSpec) -> str:
    return f"h3followup:{campaign_id}:o{spec.order:02d}:cold"


def child_command(
    campaign_id: str, spec: builder.FollowupSpec, layout: Layout = DEFAULT_LAYOUT
) -> list[str]:
    command = [
        str(layout.python),
        "-B",
        str(layout.runner),
        str(spec.recipe_path),
        "--disable-pinned-memory",
        "--manager-offline-test",
        "--manager-probe-phase",
        "cold",
        "--executor-cache-nonce",
        expected_nonce(campaign_id, spec),
        "--completion-timeout-s",
        str(spec.timeout_s),
        "--shutdown",
    ]
    if "--force" in command or "--suite" in command:
        raise CampaignError("follow-up legs may not use --force or --suite")
    return command


def child_environment(log_path: Path, source: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(source if source is not None else os.environ)
    for key in (
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
    ):
        environment.pop(key, None)
    environment.update(manager_guard.OFFLINE_ENVIRONMENT)
    environment["LAB_RESERVE_VRAM_GB"] = "12"
    environment["LAB_CACHE_CLASSIC"] = "1"
    environment["LAB_MANAGER_PROBE_LOG"] = str(log_path.resolve())
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    manager_guard.offline_environment_evidence(environment)
    return environment


def descriptor_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(source if source is not None else os.environ)
    for key in manager_guard.SCRUBBED_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    environment.update(manager_guard.OFFLINE_ENVIRONMENT)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    manager_guard.offline_environment_evidence(environment)
    return environment


def planned_specs(skip_job4: bool) -> tuple[builder.FollowupSpec, ...]:
    return tuple(
        spec for spec in builder.followup_specs() if not skip_job4 or spec.job != 4
    )


def runbook(
    campaign_id: str, *, skip_job4: bool = False, layout: Layout = DEFAULT_LAYOUT
) -> dict[str, Any]:
    campaign_id = validate_campaign_id(campaign_id)
    plan = builder.plan_payload(include_job4=not skip_job4)
    specs = planned_specs(skip_job4)
    return {
        "schema_version": 1,
        "campaign": "H3_MUSIC_FOLLOWUP",
        "campaign_id": campaign_id,
        "default_action": "READ_ONLY_RUNBOOK",
        "execution_requires": "--run",
        "job1": plan["job1"],
        "new_render_leg_count": len(specs),
        "job_counts": {
            "job1_render_legs": 0,
            "job2": sum(spec.job == 2 for spec in specs),
            "job3": sum(spec.job == 3 for spec in specs),
            "job4": sum(spec.job == 4 for spec in specs),
        },
        "ordered_legs": [
            {
                **item,
                "argv": child_command(campaign_id, spec, layout),
                "manager_log": str(manager_log_path(campaign_id, spec, layout)),
                "exploratory_single_cold_leg": True,
                "shutdown_in_same_child": True,
                "quality_judgment": "PENDING_HUMAN",
            }
            for item, spec in zip(plan["recipes"], specs)
        ],
        "manager_network_mode": "offline",
        "boot_lane": EXPECTED_BOOT_LANE,
        "operator_idle_policy": expected_operator_idle_policy(),
        "hardened_idle_requires_absent": [
            ".gpu.lock",
            ".suite.lock",
            ".server.pid",
            ".server.idle-gate.json",
            ".queue.quarantine.json",
            "listener on 127.0.0.1:8199",
        ],
        "persistent_root_coordinator_mutex_is_not_debris": True,
        "conditional_bonus_implemented": False,
        "warm_certification_claimed": False,
        "quality_judgment": "PENDING_HUMAN",
    }


class AppendOnlyLifecycle:
    def __init__(self, path: Path, campaign_id: str) -> None:
        self.path = path
        self.campaign_id = campaign_id
        self.events = self._read_and_verify()

    def _read_and_verify(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        require_safe_regular(self.path, self.path.parent, "campaign lifecycle")
        raw = self.path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or (raw and not raw.endswith(b"\n")):
            raise CampaignError("lifecycle must be BOM-free, newline-terminated JSONL")
        events = []
        previous = None
        for sequence, line in enumerate(raw.splitlines(), start=1):
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CampaignError(f"invalid lifecycle line {sequence}: {exc}") from exc
            if not isinstance(event, dict):
                raise CampaignError(f"lifecycle line {sequence} is not an object")
            retained = event.get("event_sha256")
            body = {key: value for key, value in event.items() if key != "event_sha256"}
            if (
                event.get("sequence") != sequence
                or event.get("campaign_id") != self.campaign_id
                or event.get("previous_event_sha256") != previous
                or retained != sha256_bytes(canonical_compact(body))
            ):
                raise CampaignError(f"lifecycle hash chain failed at line {sequence}")
            previous = retained
            events.append(event)
        return events

    def append(self, kind: str, data: Mapping[str, Any]) -> dict[str, Any]:
        body = {
            "sequence": len(self.events) + 1,
            "campaign_id": self.campaign_id,
            "timestamp": utc_now(),
            "event": kind,
            "previous_event_sha256": (
                self.events[-1]["event_sha256"] if self.events else None
            ),
            "data": dict(data),
        }
        event = {**body, "event_sha256": sha256_bytes(canonical_compact(body))}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write(canonical_compact(event))
            handle.flush()
            os.fsync(handle.fileno())
        self.events.append(event)
        return event

    def last(self, kind: str, recipe: str | None = None) -> dict[str, Any] | None:
        for event in reversed(self.events):
            if event.get("event") != kind:
                continue
            if recipe is not None and (event.get("data") or {}).get("recipe") != recipe:
                continue
            return event
        return None


class CoordinatorLease:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.token = canonical_compact(
            {"kind": "h3-music-followup-coordinator", "pid": os.getpid(), "nonce": secrets.token_hex(16)}
        )

    def __enter__(self) -> "CoordinatorLease":
        try:
            with self.path.open("xb") as handle:
                handle.write(self.token)
        except FileExistsError as exc:
            raise CampaignError(f"coordinator lease already exists: {self.path}") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self.path.read_bytes() != self.token:
                raise CampaignError("coordinator lease bytes changed; refusing removal")
            self.path.unlink()
        except FileNotFoundError as missing:
            raise CampaignError("coordinator lease disappeared") from missing


def runtime_state(layout: Layout = DEFAULT_LAYOUT) -> dict[str, Any]:
    try:
        listeners = []
        for connection in psutil.net_connections(kind="tcp"):
            local = connection.laddr
            if (
                connection.status == psutil.CONN_LISTEN
                and local
                and int(local.port) == LAB_PORT
            ):
                listeners.append(
                    {"ip": str(local.ip), "port": int(local.port), "pid": connection.pid}
                )
    except (psutil.AccessDenied, OSError) as exc:
        raise CampaignError(f"cannot prove port {LAB_PORT} idle: {exc}") from exc
    return {
        "gpu_lock_exists": os.path.lexists(layout.gpu_lock),
        "suite_lock_exists": os.path.lexists(layout.suite_lock),
        "server_pid_receipt_exists": os.path.lexists(layout.server_pid),
        "server_idle_gate_receipt_exists": os.path.lexists(layout.server_idle_gate),
        "queue_quarantine_exists": os.path.lexists(layout.queue_quarantine),
        "listeners_8199": sorted(listeners, key=lambda item: (item["ip"], item["pid"] or -1)),
    }


def require_clean_state(state: Mapping[str, Any], label: str) -> None:
    expected = {
        "gpu_lock_exists": False,
        "suite_lock_exists": False,
        "server_pid_receipt_exists": False,
        "server_idle_gate_receipt_exists": False,
        "queue_quarantine_exists": False,
        "listeners_8199": [],
    }
    if dict(state) != expected:
        raise CampaignError(f"{label} is not hardened-idle: {state}")


def expected_server_argv(layout: Layout = DEFAULT_LAYOUT) -> list[str]:
    return [
        str(layout.comfyui_main),
        "--port",
        "8199",
        "--cuda-malloc",
        "--user-directory",
        str(layout.comfy_user),
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
        "--reserve-vram",
        "12",
        "--disable-pinned-memory",
        "--cache-classic",
    ]


def manager_identity(evidence: Mapping[str, Any]) -> dict[str, Any]:
    advisory = evidence.get("advisory_config") or {}
    scan = evidence.get("log_scan") or {}
    authority = scan.get("authoritative_server_reported_mode") or {}
    source = scan.get("source_proof") or {}
    preboot = scan.get("preboot_records") or [{}]
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
        "prestartup_state_sha256": (scan.get("current_prestartup_state") or {}).get(
            "state_sha256"
        ),
        "preboot_record_sha256": (preboot[0].get("record") or {}).get("record_sha256"),
        "log_path": evidence.get("log_path"),
        "serving_pid": evidence.get("serving_pid"),
        "serving_process_create_time_ns": evidence.get("serving_process_create_time_ns"),
    }


def verify_manager_receipt(
    receipt: Mapping[str, Any], log_path: Path, sources: Mapping[str, Any]
) -> dict[str, Any]:
    bundle = receipt.get("manager_offline_probe")
    if not isinstance(bundle, dict) or bundle.get("provenance_unchanged") is not True:
        raise CampaignError("Manager offline receipt bundle is missing or changed")
    pre = bundle.get("pre_queue")
    post = bundle.get("post_render")
    if not isinstance(pre, dict) or not isinstance(post, dict):
        raise CampaignError("Manager pre/post evidence is missing")
    expected_offline = manager_guard.offline_environment_evidence(
        dict(manager_guard.OFFLINE_ENVIRONMENT)
    )
    argv = receipt.get("server_argv")
    if not isinstance(argv, list):
        raise CampaignError("Manager receipt lacks server argv")
    for label, phase in (("pre_queue", pre), ("post_render", post)):
        if (
            phase.get("enabled") is not True
            or phase.get("valid") is not True
            or phase.get("log_path") != str(log_path.resolve())
            or phase.get("offline_environment") != expected_offline
        ):
            raise CampaignError(f"Manager {label} identity drift")
        if (phase.get("guard_source") or {}).get("sha256") != sources["manager_guard"]["sha256"]:
            raise CampaignError(f"Manager {label} guard source drift")
        if (phase.get("test_boot_source") or {}).get("sha256") != sources["test_boot"]["sha256"]:
            raise CampaignError(f"Manager {label} boot source drift")
        scan = phase.get("log_scan")
        if not isinstance(scan, dict):
            raise CampaignError(f"Manager {label} scan is absent")
        binding_errors = manager_guard.validate_scan_binding(scan, log_path, argv)
        authority = scan.get("authoritative_server_reported_mode") or {}
        if (
            binding_errors
            or authority.get("announcement_count") != 1
            or authority.get("observed_values") != ["offline"]
            or authority.get("resolved_mode") != "offline"
            or authority.get("mode_precedes_startup_completion") is not True
            or authority.get("mode_precedes_first_execution") is not True
            or scan.get("network_markers") != []
            or scan.get("mutation_markers") != []
        ):
            raise CampaignError(f"Manager {label} offline authority failed: {binding_errors}")
    if (
        pre.get("require_no_prior_prompt") is not True
        or (pre.get("log_scan") or {}).get("require_pre_prompt") is not True
        or (pre.get("log_scan") or {}).get("execution_markers") != []
    ):
        raise CampaignError("Manager cold gate was not proved before the prompt")
    markers = (post.get("log_scan") or {}).get("execution_markers") or []
    got_prompt = sum("got prompt" in row.get("markers", []) for row in markers)
    executed = sum("Prompt executed in" in row.get("markers", []) for row in markers)
    if got_prompt != 1 or executed != 1:
        raise CampaignError("Manager log does not prove exactly one prompt execution")
    identity = manager_identity(pre)
    if identity != manager_identity(post):
        raise CampaignError("Manager immutable identity changed during the leg")
    if (receipt.get("identity") or {}).get("manager_offline_probe_identity") != identity:
        raise CampaignError("run identity does not bind Manager offline proof")
    scope = identity.get("recipe_scope") or {}
    if (
        scope.get("scope") != "h3-music-followup"
        or scope.get("match_type") != "prefix"
        or scope.get("match_value") != "h3_music_followup_"
    ):
        raise CampaignError("Manager recipe scope is not the closed follow-up lane")
    return {"pre_queue": pre, "post_render": post, "identity": identity}


def verify_recipe(spec: builder.FollowupSpec) -> str:
    expected = builder.canonical_json(builder.build_recipe(spec))
    safe_recipe = require_safe_regular(
        spec.recipe_path, builder.RECIPES_DIR, "generated follow-up recipe"
    )
    if safe_recipe.read_bytes() != expected:
        raise CampaignError(f"generated recipe bytes drifted: {spec.recipe_path}")
    return sha256_bytes(expected)


def finite_positive(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def verify_operator_idle_measurement(
    receipt: Mapping[str, Any], label: str
) -> dict[str, Any]:
    baseline = receipt.get("baseline_vram_gb")
    peak = receipt.get("peak_vram_gb")
    absolute_peak = receipt.get("absolute_peak_vram_gb")
    net_peak = receipt.get("net_peak_vram_gb")
    finite_nonnegative_baseline = (
        isinstance(baseline, (int, float))
        and not isinstance(baseline, bool)
        and math.isfinite(float(baseline))
        and float(baseline) >= 0.0
    )
    if (
        not finite_nonnegative_baseline
        or not finite_positive(peak)
        or float(peak) <= float(baseline) + 0.2
        or float(peak) > 14.5
        or not finite_positive(absolute_peak)
        or float(absolute_peak) != float(peak)
        or not finite_positive(net_peak)
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
    expected_baseline_advisory = {
        "schema_version": 1,
        "kind": "per-leg-prequeue-baseline-advisory",
        "baseline_vram_gb": float(baseline),
        "advisory_threshold_gb": 3.0,
        "threshold_exceeded": float(baseline) > 3.0,
        "gating": False,
        "disposition": "record-only; proceed regardless of baseline",
    }
    expected_drift_advisory = {
        "schema_version": 1,
        "kind": "same-identity-cold-warm-baseline-drift-advisory",
        "applicable": False,
        "measurement_available": False,
        "previous_baseline_vram_gb": None,
        "current_baseline_vram_gb": float(baseline),
        "absolute_drift_gb": None,
        "advisory_threshold_gb": 0.5,
        "threshold_exceeded": False,
        "gating": False,
        "disposition": "record-only; no same-identity prior leg",
    }
    if receipt.get("baseline_advisory") != expected_baseline_advisory:
        raise CampaignError(f"{label} baseline advisory is inconsistent")
    if (
        receipt.get("cold_warm_baseline_drift_advisory")
        != expected_drift_advisory
    ):
        raise CampaignError(f"{label} cold baseline-drift advisory is inconsistent")
    return {
        "baseline_vram_gb": float(baseline),
        "absolute_peak_vram_gb": float(absolute_peak),
        "net_peak_vram_gb": float(net_peak),
        "elevated_baseline_lane": elevated,
        "baseline_lane_stamp": expected_stamp,
        "vram_measurement": expected_measurement,
        "baseline_advisory": expected_baseline_advisory,
        "cold_warm_baseline_drift_advisory": expected_drift_advisory,
    }


def verify_exact_leg_file_sets(
    campaign_id: str,
    spec: builder.FollowupSpec,
    layout: Layout,
) -> dict[str, Path]:
    archive = layout.results / f"{spec.name}_run1.json"
    alias = layout.results / f"{spec.name}.json"
    artifact = layout.outputs / spec.expected_artifact_name
    attempt_log = manager_log_path(campaign_id, spec, layout)
    run_receipts = sorted(layout.results.glob(f"{spec.name}_run*.json"))
    artifacts = sorted(layout.outputs.glob(f"{spec.output_prefix}_*.mp4"))
    attempt_logs = sorted(layout.server_logs.glob(f"*-{spec.name}.log"))
    if run_receipts != [archive]:
        raise CampaignError(f"receipt archive set is not exact for {spec.name}: {run_receipts}")
    if artifacts != [artifact]:
        raise CampaignError(f"artifact set is not exact for {spec.name}: {artifacts}")
    if attempt_logs != [attempt_log]:
        raise CampaignError(f"Manager attempt-log set is not exact for {spec.name}: {attempt_logs}")
    require_safe_regular(alias, layout.results, "receipt alias")
    require_safe_regular(archive, layout.results, "run-1 receipt archive")
    require_safe_regular(artifact, layout.outputs, "native MP4 artifact")
    require_safe_regular(attempt_log, layout.server_logs, "Manager attempt log")
    return {
        "archive": archive,
        "alias": alias,
        "artifact": artifact,
        "attempt_log": attempt_log,
    }


def verify_preboot_idle_gate(
    receipt: Mapping[str, Any],
    sources: Mapping[str, Any],
    server_instance: Mapping[str, Any],
    layout: Layout,
) -> dict[str, Any]:
    gate = receipt.get("preboot_gpu_idle_gate")
    if not isinstance(gate, dict):
        raise CampaignError("cold receipt lacks preboot GPU idle-gate evidence")
    runner = load_runner_verifier(layout)
    contract = runner.gpu_idle_gate_contract()
    identity = receipt.get("identity") or {}
    if (
        gate.get("contract") != contract
        or receipt.get("preboot_gpu_idle_gate_contract") != contract
        or identity.get("preboot_gpu_idle_gate_contract") != contract
        or (contract.get("collector") or {}).get("path") != sources["runner"]["path"]
        or (contract.get("collector") or {}).get("sha256") != sources["runner"]["sha256"]
    ):
        raise CampaignError("idle-gate contract/source is not bound into run identity")
    policy = contract.get("policy") or {}
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
    for key, expected in expected_policy.items():
        if policy.get(key) != expected:
            raise CampaignError(f"idle-gate policy field {key} drifted")
    if policy.get("model_workload_markers") != EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS:
        raise CampaignError("idle-gate process markers drifted")
    expected_keys = {
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
        set(gate) != expected_keys
        or gate.get("schema_version") != 1
        or gate.get("kind") != "run-recipe-preboot-wddm-idle-gate"
        or gate.get("status") != "measured"
        or gate.get("gate_ran") is not True
        or gate.get("sample_count") != 5
        or gate.get("sampling_interval_s") != 0.2
        or gate.get("port_8199_listener_pids_before") != []
        or gate.get("port_8199_listener_pids_after") != []
        or gate.get("server_instance") != dict(server_instance)
        or gate.get("policy") != policy
        or gate.get("collector") != contract.get("collector")
    ):
        raise CampaignError("cold idle-gate top-level evidence is not exact")
    errors = runner.gpu_idle_gate_validation_errors(gate, dict(server_instance))
    if errors:
        raise CampaignError(f"cold idle-gate independent validation failed: {errors}")
    samples = gate.get("samples")
    if not isinstance(samples, list) or len(samples) != 5:
        raise CampaignError("cold idle-gate does not retain five samples")
    previous_wall = 0
    previous_monotonic = 0
    for index, sample in enumerate(samples):
        forbidden = (
            sample.get("forbidden_process_scan")
            if isinstance(sample, dict)
            else None
        )
        advisories = (
            forbidden.get("advisory_unreadable_processes")
            if isinstance(forbidden, dict)
            else None
        )
        if (
            not isinstance(forbidden, dict)
            or forbidden.get("classifier_contract")
            != expected_known_workload_classifier_contract()
            or forbidden.get("blocking_processes") != []
            or not isinstance(advisories, list)
            or any(
                runner.redacted_workload_process_validation_errors(
                    row, "advisory"
                )
                for row in advisories
            )
        ):
            raise CampaignError(
                f"cold idle-gate sample {index} workload scan is invalid"
            )
        if (
            not isinstance(sample, dict)
            or sample.get("sample_index") != index
            or not isinstance(sample.get("sampled_at_ns"), int)
            or isinstance(sample.get("sampled_at_ns"), bool)
            or sample["sampled_at_ns"] <= previous_wall
            or not isinstance(sample.get("sampled_monotonic_ns"), int)
            or isinstance(sample.get("sampled_monotonic_ns"), bool)
            or sample["sampled_monotonic_ns"] <= previous_monotonic
            or not finite_positive(sample.get("host_ram_total_bytes"))
            or not isinstance(sample.get("host_ram_used_bytes"), (int, float))
            or isinstance(sample.get("host_ram_used_bytes"), bool)
            or float(sample["host_ram_used_bytes"]) < 0
            or float(sample["host_ram_used_bytes"])
            > float(sample["host_ram_total_bytes"])
        ):
            raise CampaignError(f"cold idle-gate sample {index} time/host evidence drift")
        previous_wall = sample["sampled_at_ns"]
        previous_monotonic = sample["sampled_monotonic_ns"]
    return dict(gate)


def verify_idle_gate_sidecar_receipt(
    receipt: Mapping[str, Any],
    gate: Mapping[str, Any],
    server_instance: Mapping[str, Any],
    layout: Layout,
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
    identity = snapshot.get("identity") if isinstance(snapshot, dict) else None
    canonical_sidecar = (
        json.dumps(
            dict(gate),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != expected_keys
        or Path(os.path.abspath(str(snapshot.get("path", ""))))
        != Path(os.path.abspath(os.fspath(layout.server_idle_gate)))
        or snapshot.get("bytes") != len(canonical_sidecar)
        or snapshot.get("sha256") != sha256_bytes(canonical_sidecar)
        or not isinstance(identity, list)
        or len(identity) != 6
        or any(isinstance(value, bool) or not isinstance(value, int) for value in identity)
        or not stat.S_ISREG(identity[2])
        or identity[3] != 1
        or identity[4] != len(canonical_sidecar)
        or snapshot.get("evidence_sha256") != gate.get("evidence_sha256")
        or snapshot.get("server_instance") != dict(server_instance)
    ):
        raise CampaignError("cold idle-gate sidecar receipt is not exactly bound")
    if "preboot_gpu_idle_gate_sidecar" in (receipt.get("identity") or {}):
        raise CampaignError("variable idle-gate sidecar entered stable run identity")
    return dict(snapshot)


def verify_prequeue_known_workload_scan(
    receipt: Mapping[str, Any],
    runner: Any,
    server_instance: Mapping[str, Any],
    server_argv: Sequence[str],
) -> dict[str, Any]:
    contract = runner.prequeue_known_workload_scan_contract()
    expected_contract = expected_operator_idle_policy()[
        "prequeue_known_workload_scan_contract"
    ]
    identity = receipt.get("identity") or {}
    evidence = receipt.get("prequeue_known_workload_scan")
    if (
        contract != expected_contract
        or receipt.get("prequeue_known_workload_scan_contract") != contract
        or not isinstance(identity, dict)
        or identity.get("prequeue_known_workload_scan_contract") != contract
        or not isinstance(evidence, dict)
    ):
        raise CampaignError("prequeue known-workload contract/evidence is not bound")
    errors = runner.prequeue_known_workload_scan_validation_errors(
        evidence, dict(server_instance), list(server_argv)
    )
    if errors:
        raise CampaignError(
            f"prequeue known-workload independent validation failed: {errors}"
        )
    owned_errors = runner.owned_lab_server_exclusion_validation_errors(
        evidence.get("owned_lab_server_exclusion"),
        dict(server_instance),
        list(server_argv),
        evidence.get("excluded_owned_lab_server"),
    )
    if owned_errors:
        raise CampaignError(
            "prequeue owned-server exclusion independent validation failed: "
            f"{owned_errors}"
        )
    advisories = evidence.get("advisory_unreadable_processes")
    if not isinstance(advisories, list) or any(
        runner.redacted_workload_process_validation_errors(row, "advisory")
        for row in advisories
    ):
        raise CampaignError("prequeue unreadable-process advisory evidence is invalid")
    return dict(evidence)


def verify_receipt(
    campaign_id: str,
    spec: builder.FollowupSpec,
    sources: Mapping[str, Any],
    layout: Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    if os.path.lexists(layout.server_idle_gate):
        raise CampaignError(
            "--shutdown did not remove the immutable server idle-gate sidecar"
        )
    recipe_sha = verify_recipe(spec)
    exact_paths = verify_exact_leg_file_sets(campaign_id, spec, layout)
    archive = exact_paths["archive"]
    alias = exact_paths["alias"]
    receipt, archive_raw = strict_json(archive, "immutable run-1 receipt")
    _, alias_raw = strict_json(alias, "current receipt alias")
    if archive_raw != alias_raw:
        raise CampaignError(f"receipt alias differs from run-1 archive: {spec.name}")
    expected = {
        "receipt_schema_version": 3,
        "recipe": spec.name,
        "recipe_sha256": recipe_sha,
        "run_number": 1,
        "run_count": 1,
        "config_run_count": 1,
        "completion_timeout_s": spec.timeout_s,
        "gate_pass": True,
        "pass": False,
        "warm_pass": False,
        "accepted_prompt": True,
        "blocked": False,
        "valid_measurement": True,
        "requires_human_eyeball": True,
        "eyeball": "pending",
        "promotion_ready": False,
        "certification_scope": "machine-only",
        "boot_lane": EXPECTED_BOOT_LANE,
        "reserve_vram_gib": 12.0,
        "clamp_target_gib": None,
        "encoded_width": 1344,
        "encoded_height": 768,
        "encoded_frame_count": spec.frames,
        "encoded_fps": 24.0,
        "audio_present": True,
        "audio_codec": "aac",
        "provenance_unchanged": True,
        "provenance_validation_error": "",
        "server_instance_unchanged": True,
    }
    mismatches = {
        key: {"expected": value, "actual": receipt.get(key)}
        for key, value in expected.items()
        if receipt.get(key) != value
    }
    if receipt.get("status") not in {"PASS (cold)", "PASS (cold, marginal)"}:
        mismatches["status"] = {"expected": "cold gate pass", "actual": receipt.get("status")}
    if mismatches:
        raise CampaignError(f"receipt invariant drift for {spec.name}: {mismatches}")
    if receipt.get("runner_sha256") != sources["runner"]["sha256"]:
        raise CampaignError("receipt runner SHA is not campaign-bound")
    if receipt.get("lab_locks_sha256") != sources["lab_locks"]["sha256"]:
        raise CampaignError("receipt lab_locks SHA is not campaign-bound")
    if receipt.get("fixture_sha256s") != {"portrait.png": EXPECTED_PORTRAIT_SHA256}:
        raise CampaignError("portrait fixture identity drift")
    if (
        receipt.get("audio_receipt_sha256s") != {}
        or (receipt.get("identity") or {}).get("audio_receipt_sha256s") != {}
        or (receipt.get("identity") or {}).get("fixture_sha256s")
        != {"portrait.png": EXPECTED_PORTRAIT_SHA256}
    ):
        raise CampaignError("unconditioned fixture/audio-receipt identity drift")
    peak = receipt.get("peak_vram_gb")
    baseline = receipt.get("baseline_vram_gb")
    vram_measurement = verify_operator_idle_measurement(receipt, spec.name)
    if (
        not finite_positive(receipt.get("duration_s"))
        or not finite_positive(receipt.get("baseline_host_ram_gb"))
        or not finite_positive(receipt.get("peak_host_ram_gb"))
        or float(receipt["peak_host_ram_gb"])
        < float(receipt["baseline_host_ram_gb"])
    ):
        raise CampaignError("cold machine measurement is not a valid 14.5-GiB gate sample")
    marginal = float(peak) >= 14.25
    if (
        receipt.get("marginal") is not marginal
        or (receipt.get("status") == "PASS (cold, marginal)") is not marginal
    ):
        raise CampaignError("marginal cold status does not match measured peak VRAM")
    identity = receipt.get("identity") or {}
    server_instance = receipt.get("server_instance")
    if (
        not isinstance(identity, dict)
        or not isinstance(server_instance, dict)
        or not isinstance(server_instance.get("serving_pid"), int)
        or isinstance(server_instance.get("serving_pid"), bool)
        or server_instance["serving_pid"] <= 0
        or not finite_positive(server_instance.get("process_create_time"))
        or identity.get("server_instance") != server_instance
        or receipt.get("final_server_instance") != server_instance
        or identity.get("recipe_sha256") != recipe_sha
        or identity.get("runner_sha256") != sources["runner"]["sha256"]
        or identity.get("lab_locks_sha256") != sources["lab_locks"]["sha256"]
        or identity.get("completion_timeout_s") != spec.timeout_s
        or identity.get("boot_lane") != EXPECTED_BOOT_LANE
        or identity.get("server_argv") != expected_server_argv(layout)
        or receipt.get("server_argv") != expected_server_argv(layout)
    ):
        raise CampaignError("run identity or server argv drift")
    runner_verifier = load_runner_verifier(layout)
    if runner_verifier.operator_idle_policy_contract() != expected_operator_idle_policy():
        raise CampaignError("runner operator idle policy contract drift")
    if runner_verifier.stable_identity(identity) != receipt.get("run_identity_sha256"):
        raise CampaignError("stable run identity SHA does not recompute")
    prequeue_workload_scan = verify_prequeue_known_workload_scan(
        receipt, runner_verifier, server_instance, expected_server_argv(layout)
    )
    idle_gate = verify_preboot_idle_gate(
        receipt, sources, server_instance, layout
    )
    idle_gate_sidecar = verify_idle_gate_sidecar_receipt(
        receipt, idle_gate, server_instance, layout
    )
    models = receipt.get("model_fingerprints")
    expected_model_names = {
        "minimax_h3_audio_vae_fp32.safetensors",
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "minimax_h3_video_vae_fp16.safetensors",
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    }
    if (
        not isinstance(models, dict)
        or set(models) != expected_model_names
        or identity.get("model_fingerprints") != models
        or any(
            not isinstance(value, dict)
            or value.get("resolved") is not True
            or not Path(str(value.get("path", ""))).is_absolute()
            or not finite_positive(value.get("bytes"))
            or not finite_positive(value.get("mtime_ns"))
            for value in models.values()
        )
    ):
        raise CampaignError("resolved model fingerprint identity is unproved")
    comfy_commit = receipt.get("comfyui_git_commit")
    if (
        not isinstance(comfy_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", comfy_commit) is None
        or identity.get("comfyui_git_commit") != comfy_commit
    ):
        raise CampaignError("ComfyUI commit identity drift")
    cache = receipt.get("execution_cache_control")
    queued_prompt, expected_cache = runner_verifier.apply_standalone_cache_nonce(
        builder.build_recipe(spec)["prompt"], expected_nonce(campaign_id, spec)
    )
    expected_queued_sha = runner_verifier.stable_identity(queued_prompt)
    if (
        not isinstance(cache, dict)
        or any(cache.get(key) != value for key, value in expected_cache.items())
        or cache.get("fresh_execution_proved") is not True
        or cache.get("cache_event_found") is not True
        or cache.get("cached_fresh_node_ids") != []
        or cache.get("cached_node_ids") != []
        or set(cache)
        != set(expected_cache)
        | {
            "cache_event_found",
            "cached_node_ids",
            "cached_fresh_node_ids",
            "fresh_execution_proved",
        }
    ):
        raise CampaignError("fresh cold sampler/output execution is unproved")
    queued_sha = receipt.get("queued_prompt_sha256")
    if queued_sha != expected_queued_sha:
        raise CampaignError("queued prompt SHA does not bind the nonce-injected prompt")
    runtime_sources = dict(runner_verifier.STANDALONE_CACHE_RUNTIME_SOURCES)
    if (
        receipt.get("standalone_cache_runtime_sha256s") != runtime_sources
        or receipt.get("final_standalone_cache_runtime_sha256s") != runtime_sources
        or identity.get("standalone_cache_runtime_sha256s") != runtime_sources
        or receipt.get("suite_cache_runtime_sha256s") != {}
        or receipt.get("final_suite_cache_runtime_sha256s") != {}
        or "suite_cache_runtime_sha256s" in identity
    ):
        raise CampaignError("standalone cache runtime source identity drift")
    log_path = exact_paths["attempt_log"]
    manager = verify_manager_receipt(receipt, log_path, sources)
    expected_output = spec.expected_artifact_name
    if receipt.get("output_path") != expected_output:
        raise CampaignError(f"unexpected output path: {receipt.get('output_path')}")
    artifact = exact_paths["artifact"].resolve()
    try:
        artifact.relative_to(layout.outputs.resolve())
    except ValueError as exc:
        raise CampaignError("artifact path escapes outputs") from exc
    if not artifact.is_file():
        raise CampaignError(f"artifact is missing: {artifact}")
    artifact_sha = sha256_file(artifact)
    audio_duration = receipt.get("audio_duration_s")
    container_duration = receipt.get("container_duration_s")
    if (
        receipt.get("artifact_sha256") != artifact_sha
        or receipt.get("artifact_bytes") != artifact.stat().st_size
        or not finite_positive(receipt.get("artifact_bytes"))
        or not finite_positive(audio_duration)
        or not finite_positive(container_duration)
        or abs(float(audio_duration) - float(container_duration)) > 0.1
        or not finite_positive(receipt.get("audio_stream_bytes"))
        or not finite_positive(receipt.get("audio_bitrate"))
    ):
        raise CampaignError("artifact hash/size/native-audio evidence drift")
    return {
        "recipe": spec.name,
        "recipe_sha256": recipe_sha,
        "receipt_path": str(archive),
        "receipt_sha256": sha256_bytes(archive_raw),
        "artifact_path": str(artifact),
        "artifact_name": expected_output,
        "artifact_sha256": artifact_sha,
        "artifact_bytes": artifact.stat().st_size,
        "status": receipt["status"],
        **vram_measurement,
        "wall_clock_s": receipt.get("duration_s"),
        "manager": manager,
        "preboot_gpu_idle_gate": idle_gate,
        "preboot_gpu_idle_gate_sidecar": idle_gate_sidecar,
        "prequeue_known_workload_scan": prequeue_workload_scan,
        "quality_judgment": "PENDING_HUMAN",
    }


def run_child(
    command: Sequence[str],
    environment: Mapping[str, str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    non_controlling_watchdog_s: int,
) -> dict[str, Any]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
        # Deliberately do not terminate, kill, or otherwise control the child
        # on a coordinator clock.  The render child owns its pinned
        # --completion-timeout-s and its proven cleanup path.  If it does not
        # return, keeping this coordinator attached is safer than orphaning an
        # active server/GPU job.  The value below is expectation metadata only.
        returncode = process.wait()
    require_safe_regular(stdout_path, cwd, "child stdout log")
    require_safe_regular(stderr_path, cwd, "child stderr log")
    return {
        "returncode": int(returncode),
        "owned_child_pid": process.pid,
        "non_controlling_watchdog_s": non_controlling_watchdog_s,
        "coordinator_process_control_on_watchdog": False,
        "stdout": {"path": str(stdout_path), "sha256": sha256_file(stdout_path), "bytes": stdout_path.stat().st_size},
        "stderr": {"path": str(stderr_path), "sha256": sha256_file(stderr_path), "bytes": stderr_path.stat().st_size},
    }


def descriptor_manifest_payload(spec: builder.FollowupSpec, run: Mapping[str, Any]) -> dict[str, Any]:
    receipt_relative = Path(run["receipt_path"]).resolve().relative_to(ROOT).as_posix()
    return {
        "schema_version": 1,
        "campaign": "H3_MUSIC_FOLLOWUP",
        "clips": [
            {
                "label": f"J{spec.job}-{spec.cell}",
                "filename": run["artifact_name"],
                "sha256": run["artifact_sha256"],
                "recipe": spec.name,
                "recipe_sha256": run["recipe_sha256"],
                "receipt_path": receipt_relative,
                "receipt_sha256": run["receipt_sha256"],
            }
        ],
        "quality_judgment": "PENDING_HUMAN",
    }


def verify_descriptors(
    spec: builder.FollowupSpec,
    run: Mapping[str, Any],
    result_path: Path,
    manifest_path: Path,
    layout: Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    require_safe_regular(manifest_path, layout.root, "descriptor manifest")
    require_safe_regular(result_path, layout.root, "descriptor result")
    payload, raw = strict_json(result_path, "descriptor result")
    records = payload.get("records")
    retained_manifest = payload.get("manifest") or {}
    retained_wrapper = payload.get("wrapper") or {}
    retained_analyzer = payload.get("pinned_analyzer") or {}
    if (
        payload.get("kind") != "h3-music-followup-machine-descriptors"
        or payload.get("quality_judgment") != "PENDING_HUMAN"
        or not isinstance(records, list)
        or len(records) != 1
        or retained_manifest.get("path") != str(manifest_path.resolve())
        or retained_manifest.get("sha256") != sha256_file(manifest_path)
        or retained_wrapper.get("path") != str(layout.descriptor_wrapper.resolve())
        or retained_wrapper.get("sha256") != sha256_file(layout.descriptor_wrapper)
        or retained_analyzer.get("path") != str(layout.descriptor_analyzer.resolve())
        or retained_analyzer.get("sha256")
        != "24cc09b0a7a187d7cf7a5dee0ab5547ad4b8bf64d40641ace86c1c8f571a5b3f"
        or retained_analyzer.get("sha256") != sha256_file(layout.descriptor_analyzer)
    ):
        raise CampaignError("descriptor result shape drift")
    record = records[0]
    if (
        record.get("recipe") != spec.name
        or record.get("input_sha256") != run["artifact_sha256"]
        or record.get("recipe_sha256") != run["recipe_sha256"]
        or record.get("quality_judgment") != "PENDING_HUMAN"
        or (record.get("receipt_binding") or {}).get("receipt_sha256")
        != run["receipt_sha256"]
        or set((record.get("commands") or {}))
        != {"C0_probe", "C1_ebur128", "C2_silencedetect", "C3_astats", "C4_pcm_extract", "C5_scene_scores"}
    ):
        raise CampaignError("descriptor evidence is not command/receipt-bound")
    metrics = record.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise CampaignError("descriptor metrics are absent")
    for key, value in metrics.items():
        values = value if isinstance(value, list) else [value]
        for scalar in values:
            if scalar is None:
                continue
            if isinstance(scalar, bool) or not isinstance(scalar, (int, float)) or not math.isfinite(float(scalar)):
                raise CampaignError(f"descriptor metric {key} is not finite numeric evidence")
    return {
        "path": str(result_path),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "command_ids": sorted(record["commands"]),
        "quality_judgment": "PENDING_HUMAN",
    }


def render_evidence_paths(
    campaign_id: str, spec: builder.FollowupSpec, directory: Path, layout: Layout
) -> list[Path]:
    operator = directory / "operator_logs"
    return [
        layout.results / f"{spec.name}_run1.json",
        layout.results / f"{spec.name}.json",
        layout.outputs / spec.expected_artifact_name,
        manager_log_path(campaign_id, spec, layout),
        operator / f"o{spec.order:02d}-{spec.name}.stdout.log",
        operator / f"o{spec.order:02d}-{spec.name}.stderr.log",
    ]


def execute_campaign(
    campaign_id: str,
    *,
    resume: bool = False,
    skip_job4: bool = False,
    layout: Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    campaign_id = validate_campaign_id(campaign_id)
    directory = campaign_dir(campaign_id, layout)
    if resume:
        if not directory.is_dir():
            raise CampaignError(f"resume campaign does not exist: {directory}")
    else:
        directory.mkdir(parents=True, exist_ok=False)
    layout.server_logs.mkdir(parents=True, exist_ok=True)
    require_safe_directory(layout.campaign_root, layout.results, "follow-up campaign root")
    require_safe_directory(layout.server_logs, layout.campaign_root, "Manager log root")
    require_safe_directory(layout.campaigns, layout.campaign_root, "campaigns root")
    require_safe_directory(directory, layout.campaigns, "campaign directory")
    specs = planned_specs(skip_job4)
    current_plan = runbook(campaign_id, skip_job4=skip_job4, layout=layout)
    plan_sha = sha256_bytes(canonical_compact(current_plan))
    ledger = AppendOnlyLifecycle(lifecycle_path(campaign_id, layout), campaign_id)
    # One global follow-up lease prevents two campaign IDs from racing toward
    # the runner.  run_recipe.py still remains the only owner of .gpu.lock.
    lease_path = layout.campaign_root / ".coordinator.lock"
    sources: dict[str, Any] = {}
    completed: list[dict[str, Any]] = []
    with CoordinatorLease(lease_path):
        try:
            if not layout.python.is_file():
                raise CampaignError(f"pinned Python is missing: {layout.python}")
            materialization = builder.materialize_recipes(specs)
            for spec in specs:
                verify_recipe(spec)
            sources = source_evidence(layout)
            initial_state = runtime_state(layout)
            require_clean_state(initial_state, "campaign entry")
            launch_path = directory / "operator_launch.json"
            launch_payload = {
                "schema_version": 1,
                "kind": "h3-music-followup-operator-launch",
                "campaign_id": campaign_id,
                "plan": current_plan,
                "plan_sha256": plan_sha,
                "sources": sources,
                "materialization": materialization,
                "initial_hardened_idle_state": initial_state,
                "render_authority": "run_recipe.py only",
                "conditional_bonus_authorized": False,
                "quality_judgment": "PENDING_HUMAN",
            }
            if resume:
                require_safe_regular(
                    launch_path, directory, "operator launch receipt"
                )
                launch, launch_raw = strict_json(launch_path, "operator launch receipt")
                if (
                    launch.get("schema_version") != 1
                    or launch.get("kind") != "h3-music-followup-operator-launch"
                    or launch.get("campaign_id") != campaign_id
                    or launch.get("plan") != current_plan
                    or launch.get("plan_sha256") != plan_sha
                    or launch.get("sources") != sources
                    or launch.get("conditional_bonus_authorized") is not False
                    or launch.get("quality_judgment") != "PENDING_HUMAN"
                ):
                    raise CampaignError("resume plan/source/launch receipt drift")
                if ledger.last("campaign_completed") is not None:
                    raise CampaignError("campaign is already complete")
                started = ledger.last("campaign_started")
                if started is None or (started.get("data") or {}).get("plan_sha256") != plan_sha:
                    raise CampaignError("resume lifecycle plan drift")
                ledger.append(
                    "campaign_resumed",
                    {
                        "plan_sha256": plan_sha,
                        "launch_receipt_sha256": sha256_bytes(launch_raw),
                        "hardened_idle_state": initial_state,
                    },
                )
            else:
                if ledger.events:
                    raise CampaignError("new campaign lifecycle unexpectedly exists")
                launch_receipt = write_exclusive_json(launch_path, launch_payload)
                ledger.append(
                    "campaign_started",
                    {
                        "plan_sha256": plan_sha,
                        "launch_receipt": launch_receipt,
                        "render_leg_count": len(specs),
                        "quality_judgment": "PENDING_HUMAN",
                    },
                )
            job1_event_data = {
                **current_plan["job1"],
                "render_leg_count": 0,
                "job1b_skipped": True,
            }
            retained_job1 = ledger.last("job1_local_schema_rejection")
            if retained_job1 is None:
                ledger.append(
                    "job1_local_schema_rejection",
                    job1_event_data,
                )
            elif retained_job1.get("data") != job1_event_data:
                raise CampaignError("retained Job 1 schema finding drift")

            for spec in specs:
                require_sources(sources, layout, f"before {spec.name}")
                verify_recipe(spec)
                before = runtime_state(layout)
                require_clean_state(before, f"before {spec.name}")
                completed_event = ledger.last("leg_completed", spec.name)
                rendered_event = ledger.last("leg_rendered", spec.name)
                run = None
                if completed_event is not None:
                    run = verify_receipt(campaign_id, spec, sources, layout)
                    manifest_path = directory / "descriptor_manifests" / f"o{spec.order:02d}-{spec.name}.json"
                    descriptor_path = (
                        directory / "descriptors" / f"o{spec.order:02d}-{spec.name}" / "descriptors.json"
                    )
                    descriptor = verify_descriptors(
                        spec, run, descriptor_path, manifest_path, layout
                    )
                    completed.append({"order": spec.order, "recipe": spec.name, "run": run, "descriptors": descriptor})
                    continue
                if rendered_event is not None:
                    run = verify_receipt(campaign_id, spec, sources, layout)
                else:
                    evidence_paths = render_evidence_paths(campaign_id, spec, directory, layout)
                    existing = [
                        str(path) for path in evidence_paths if os.path.lexists(path)
                    ]
                    output_glob = list(layout.outputs.glob(f"{spec.output_prefix}_*.mp4"))
                    attempt_log_glob = list(
                        layout.server_logs.glob(f"*-{spec.name}.log")
                    )
                    if existing or output_glob or attempt_log_glob:
                        archives_exist = evidence_paths[0].is_file() and evidence_paths[1].is_file()
                        if (
                            archives_exist
                            and all(path.is_file() for path in evidence_paths)
                            and attempt_log_glob == [evidence_paths[3]]
                        ):
                            for operator_log in evidence_paths[4:]:
                                require_safe_regular(
                                    operator_log,
                                    directory,
                                    "recovered render operator log",
                                )
                            run = verify_receipt(campaign_id, spec, sources, layout)
                            ledger.append(
                                "leg_rendered",
                                {
                                    "order": spec.order,
                                    "job": spec.job,
                                    "cell": spec.cell,
                                    "recipe": spec.name,
                                    "recovered_after_coordinator_gap": True,
                                    "run": run,
                                    "post_shutdown_hardened_idle_state": before,
                                },
                            )
                        else:
                            raise CampaignError(
                                f"ambiguous partial render evidence for {spec.name}; refusing retry: "
                                f"{existing + [str(path) for path in output_glob + attempt_log_glob]}"
                            )
                    else:
                        log_path = manager_log_path(campaign_id, spec, layout)
                        operator = directory / "operator_logs"
                        stdout_path = operator / f"o{spec.order:02d}-{spec.name}.stdout.log"
                        stderr_path = operator / f"o{spec.order:02d}-{spec.name}.stderr.log"
                        command = child_command(campaign_id, spec, layout)
                        ledger.append(
                            "leg_started",
                            {
                                "order": spec.order,
                                "job": spec.job,
                                "cell": spec.cell,
                                "recipe": spec.name,
                                "argv": command,
                                "manager_log": str(log_path),
                                "hardened_cold_idle_state": before,
                                "single_exploratory_leg": True,
                                "warm_certification_claimed": False,
                            },
                        )
                        outcome = run_child(
                            command,
                            child_environment(log_path),
                            layout.root,
                            stdout_path,
                            stderr_path,
                            spec.timeout_s + 600,
                        )
                        ledger.append(
                            "render_child_returned",
                            {"order": spec.order, "recipe": spec.name, "outcome": outcome},
                        )
                        if outcome["returncode"] != 0:
                            raise CampaignError(f"run_recipe child failed for {spec.name}: {outcome}")
                        after = runtime_state(layout)
                        require_clean_state(after, f"after {spec.name} --shutdown")
                        run = verify_receipt(campaign_id, spec, sources, layout)
                        ledger.append(
                            "leg_rendered",
                            {
                                "order": spec.order,
                                "job": spec.job,
                                "cell": spec.cell,
                                "recipe": spec.name,
                                "recovered_after_coordinator_gap": False,
                                "run": run,
                                "post_shutdown_hardened_idle_state": after,
                            },
                        )

                if run is None:
                    raise CampaignError(f"internal missing run evidence: {spec.name}")
                descriptor_root = directory / "descriptors" / f"o{spec.order:02d}-{spec.name}"
                descriptor_result = descriptor_root / "descriptors.json"
                manifest_path = directory / "descriptor_manifests" / f"o{spec.order:02d}-{spec.name}.json"
                manifest = descriptor_manifest_payload(spec, run)
                manifest_receipt = require_exact_json(manifest_path, manifest, "descriptor manifest")
                if descriptor_result.is_file():
                    descriptor = verify_descriptors(
                        spec, run, descriptor_result, manifest_path, layout
                    )
                else:
                    if descriptor_root.exists():
                        raise CampaignError(f"partial descriptor directory blocks continuation: {descriptor_root}")
                    operator = directory / "operator_logs"
                    desc_stdout = operator / f"o{spec.order:02d}-{spec.name}.descriptor.stdout.log"
                    desc_stderr = operator / f"o{spec.order:02d}-{spec.name}.descriptor.stderr.log"
                    if desc_stdout.exists() or desc_stderr.exists():
                        raise CampaignError(f"partial descriptor logs block continuation: {spec.name}")
                    command = [
                        str(layout.python),
                        "-B",
                        str(layout.descriptor_wrapper),
                        "--manifest",
                        str(manifest_path),
                        "--result-dir",
                        str(descriptor_root),
                    ]
                    outcome = run_child(
                        command,
                        descriptor_environment(),
                        layout.root,
                        desc_stdout,
                        desc_stderr,
                        600,
                    )
                    if outcome["returncode"] != 0:
                        raise CampaignError(f"descriptor child failed for {spec.name}: {outcome}")
                    descriptor = verify_descriptors(
                        spec, run, descriptor_result, manifest_path, layout
                    )
                    descriptor["child_outcome"] = outcome
                item = {
                    "order": spec.order,
                    "job": spec.job,
                    "cell": spec.cell,
                    "recipe": spec.name,
                    "run": run,
                    "manifest": manifest_receipt,
                    "descriptors": descriptor,
                    "quality_judgment": "PENDING_HUMAN",
                }
                completed.append(item)
                ledger.append("leg_completed", item)

            if [item["recipe"] for item in completed] != [spec.name for spec in specs]:
                raise CampaignError("final completed-leg order/count drift")
            final_state = runtime_state(layout)
            require_clean_state(final_state, "campaign final state")
            require_sources(sources, layout, "campaign final audit")
            final_audit = []
            for spec in specs:
                run = verify_receipt(campaign_id, spec, sources, layout)
                manifest_path = directory / "descriptor_manifests" / f"o{spec.order:02d}-{spec.name}.json"
                descriptor_path = directory / "descriptors" / f"o{spec.order:02d}-{spec.name}" / "descriptors.json"
                descriptor = verify_descriptors(
                    spec, run, descriptor_path, manifest_path, layout
                )
                final_audit.append(
                    {
                        "order": spec.order,
                        "recipe": spec.name,
                        "receipt_sha256": run["receipt_sha256"],
                        "artifact_sha256": run["artifact_sha256"],
                        "descriptors_sha256": descriptor["sha256"],
                        "prequeue_workload_scan_sha256": run[
                            "prequeue_known_workload_scan"
                        ]["evidence_sha256"],
                        "prequeue_advisory_unreadable_process_count": len(
                            run["prequeue_known_workload_scan"][
                                "advisory_unreadable_processes"
                            ]
                        ),
                        "preboot_advisory_unreadable_process_counts": [
                            len(
                                sample["forbidden_process_scan"][
                                    "advisory_unreadable_processes"
                                ]
                            )
                            for sample in run["preboot_gpu_idle_gate"]["samples"]
                        ],
                        "preboot_display_active": {
                            "target": run["preboot_gpu_idle_gate"]["target_gpu"][
                                "display_active"
                            ],
                            "samples": [
                                sample["display_active"]
                                for sample in run["preboot_gpu_idle_gate"]["samples"]
                            ],
                            "gating": False,
                        },
                        "preboot_current_runner_exclusion_count": run[
                            "preboot_gpu_idle_gate"
                        ]["current_runner_exclusion"][
                            "expected_excluded_process_count"
                        ],
                        "prequeue_current_runner_exclusion_count": len(
                            run["prequeue_known_workload_scan"][
                                "excluded_current_runner"
                            ]
                        ),
                        "prequeue_owned_server_exclusion_count": len(
                            run["prequeue_known_workload_scan"][
                                "excluded_owned_lab_server"
                            ]
                        ),
                        "vram": {
                            key: run[key]
                            for key in (
                                "baseline_vram_gb",
                                "absolute_peak_vram_gb",
                                "net_peak_vram_gb",
                                "elevated_baseline_lane",
                                "baseline_lane_stamp",
                            )
                        },
                        "baseline_advisory": run["baseline_advisory"],
                        "cold_warm_baseline_drift_advisory": run[
                            "cold_warm_baseline_drift_advisory"
                        ],
                    }
                )
            completion_payload = {
                "schema_version": 1,
                "kind": "h3-music-followup-completion",
                "campaign_id": campaign_id,
                "status": "COMPLETE",
                "render_leg_count": len(specs),
                "job1_render_leg_count": 0,
                "final_hardened_idle_state": final_state,
                "final_evidence_audit": final_audit,
                "conditional_bonus_executed": False,
                "quality_judgment": "PENDING_HUMAN",
            }
            completion = require_exact_json(
                directory / "completion_receipt.json",
                completion_payload,
                "completion receipt",
            )
            ledger.append("campaign_completed", {**completion_payload, "completion_receipt": completion})
            return {
                "status": "COMPLETE",
                "campaign_id": campaign_id,
                "render_leg_count": len(specs),
                "lifecycle": str(ledger.path),
                "completion_receipt": completion,
                "quality_judgment": "PENDING_HUMAN",
            }
        except Exception as exc:
            try:
                state = runtime_state(layout)
            except Exception as state_exc:
                state = {"probe_error": f"{type(state_exc).__name__}: {state_exc}"}
            try:
                ledger.append(
                    "campaign_failed",
                    {
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "completed_leg_count": len(completed),
                        "failure_state": state,
                        "server_or_gpu_cleanup_attempted": False,
                        "retry_after_ambiguous_partial_evidence": False,
                        "campaign_evidence_bytes_preserved": True,
                    },
                )
            except Exception as ledger_exc:
                raise CampaignError(
                    f"campaign failed ({type(exc).__name__}: {exc}) and lifecycle append failed ({ledger_exc})"
                ) from exc
            raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute the authorized legs")
    parser.add_argument("--campaign-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-job4", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.resume and not args.run:
        raise CampaignError("--resume requires --run")
    if args.resume and not args.campaign_id:
        raise CampaignError("--resume requires --campaign-id")
    campaign_id = validate_campaign_id(args.campaign_id or (campaign_id_now() if args.run else "DRY-RUN"))
    if not args.run:
        sys.stdout.buffer.write(
            canonical_pretty(runbook(campaign_id, skip_job4=args.skip_job4))
        )
        return 0
    try:
        result = execute_campaign(
            campaign_id,
            resume=args.resume,
            skip_job4=args.skip_job4,
        )
    except Exception as exc:
        print(f"[H3 MUSIC FOLLOW-UP FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
