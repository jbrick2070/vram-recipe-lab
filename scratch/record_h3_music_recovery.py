#!/usr/bin/env python3
"""Record the append-only manual cleanup recovery for H3 attempt-001.

The default mode is read-only: it validates the frozen evidence, takes a local
machine-state observation while holding the existing lab coordinator mutex,
and prints the proposed receipt.  ``--write`` is the sole write path and uses
``O_CREAT | O_EXCL`` so an existing recovery receipt is never replaced.

This recorder never boots or contacts ComfyUI, submits a prompt, renders, or
changes the failed lifecycle.  The shutdown result in the receipt is explicitly
operator-captured; only the current postconditions are machine-observed here.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[1]

FAILED_CAMPAIGN_ID = "h3music-20260810T023023Z-97ca44b2"
RECOVERY_ID = f"{FAILED_CAMPAIGN_ID}-recovery-001"
RESUME_CAMPAIGN_ID = f"{FAILED_CAMPAIGN_ID}-attempt-002"

LIFECYCLE = Path("results/h3_unconditioned_music_campaign/lifecycle.jsonl")
RUN1 = Path("results/h3_unconditioned_music_scene_seed42_f124_run1.json")
ALIAS = Path("results/h3_unconditioned_music_scene_seed42_f124.json")
SERVER_LOG = Path(
    "results/h3_unconditioned_music_campaign/server_logs/"
    "h3music-20260810T023023Z-97ca44b2-p01-"
    "h3_unconditioned_music_scene_seed42_f124.log"
)
ARTIFACT = Path(
    "outputs/h3_unconditioned_music_scene_seed42_f124_out_00001_.mp4"
)
RECOVERY = Path(
    "results/h3_unconditioned_music_campaign/recoveries/"
    "h3music-20260810T023023Z-97ca44b2-manual-cleanup.json"
)

LIFECYCLE_PREFIX_BYTES = 28_706
LIFECYCLE_PREFIX_SHA256 = (
    "fed5a70a832ad4bc9a985e5c136d583ad7338146164eef89bf3bbe3fd917c2cf"
)
LIFECYCLE_LAST_EVENT_SHA256 = (
    "20ec57fc403d782ee292c3bfbd75b70c3d5466fca620f255e8aefaeb5c0bea1b"
)
RUN1_SHA256 = "c1295c435e25419ed771aae044d33806b55e9237e594dcdd6716be519a602b8f"
SERVER_LOG_SHA256 = (
    "b1a99a7b496b5125897d41c44a5278c5b848f9afd6afc8c2e65271b57e6a443d"
)
ARTIFACT_SHA256 = (
    "b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed"
)

RUN1_BYTES = 63_281
SERVER_LOG_BYTES = 22_947
ARTIFACT_BYTES = 909_151
SERVER_PID = 51_136
SERVER_PROCESS_CREATE_TIME = 1_786_329_027.50907

FAILED_ERROR = "executor cache field drift: queued_prompt_sha256"
FAILED_PENDING_MONITOR_ERRORS = [
    "CampaignError: candidate process does not have one expected ComfyUI main.py",
    "CampaignError: receipt server argv length drift: expected 16, found 20",
]

OPERATOR_CAPTURED_SHUTDOWN = {
    "had_receipt": True,
    "listener_exited": True,
    "pid": SERVER_PID,
    "pid_verified": True,
    "process_exited": True,
    "reason": "verified server process and listener exited",
    "receipt_removed": True,
    "success": True,
    "termination_attempted": True,
    "termination_reported_success": True,
}
OPERATOR_CAPTURED_CONSOLE = [
    "[SERVER] Shutting down verified lab server (PID 51136)...",
    "[SERVER] Process 51136 and listener exited; removed .server.pid receipt.",
]

SOURCE_PATHS = {
    "recorder": Path("scratch/record_h3_music_recovery.py"),
    "canonical_campaign_helper": Path("scratch/run_h3_canonical_campaign.py"),
    "run_recipe": Path("run_recipe.py"),
    "lab_locks": Path("lab_locks.py"),
    "manager_guard": Path("scratch/h3_manager_offline_guard.py"),
}

RUNTIME_STATE_KEYS = {
    "gpu_lock_exists",
    "suite_lock_exists",
    "server_pid_receipt_exists",
    "server_pid_receipt",
    "server_pid_create_time",
    "queue_quarantine_exists",
    "listener_pids_8199",
    "expected_server_identity_live",
}


class RecoveryError(RuntimeError):
    """The frozen evidence or current cleanup postconditions are invalid."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def receipt_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(dict(value), sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x400)


def _snapshot(path: Path, display_path: str) -> tuple[bytes, dict[str, Any]]:
    if not os.path.lexists(path):
        raise RecoveryError(f"required evidence is absent: {display_path}")
    if _is_reparse(path) or not path.is_file():
        raise RecoveryError(f"required evidence is not a regular file: {display_path}")
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise RecoveryError(f"cannot read stable evidence {display_path}: {exc}") from exc
    identity_before = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
    )
    identity_after = (
        int(after.st_dev),
        int(after.st_ino),
        int(after.st_size),
        int(after.st_mtime_ns),
    )
    if identity_before != identity_after or len(raw) != int(after.st_size):
        raise RecoveryError(f"evidence changed while being read: {display_path}")
    return raw, {
        "path": display_path,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }


def _pinned(
    root: Path,
    relative: Path,
    expected_sha256: str,
    expected_bytes: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    raw, snapshot = _snapshot(root / relative, relative.as_posix())
    if snapshot["sha256"] != expected_sha256:
        raise RecoveryError(f"immutable SHA drift: {relative.as_posix()}")
    if expected_bytes is not None and snapshot["bytes"] != expected_bytes:
        raise RecoveryError(f"immutable byte count drift: {relative.as_posix()}")
    return raw, snapshot


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RecoveryError(f"{label} has a UTF-8 BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"{label} is not a JSON object")
    return value


def _validate_lifecycle(raw: bytes) -> dict[str, Any]:
    if len(raw) < LIFECYCLE_PREFIX_BYTES:
        raise RecoveryError("attempt-001 lifecycle was truncated")
    prefix = raw[:LIFECYCLE_PREFIX_BYTES]
    if sha256_bytes(prefix) != LIFECYCLE_PREFIX_SHA256:
        raise RecoveryError("attempt-001 lifecycle prefix SHA drifted")
    if not prefix.endswith(b"\n"):
        raise RecoveryError("attempt-001 lifecycle prefix no longer ends at a record boundary")
    prefix_lines = prefix.splitlines()
    if len(prefix_lines) != 5:
        raise RecoveryError("attempt-001 lifecycle prefix must contain exactly five rows")
    if not raw.endswith(b"\n"):
        raise RecoveryError("lifecycle contains a partial trailing record")

    previous = None
    records: list[dict[str, Any]] = []
    for expected_sequence, line in enumerate(raw.splitlines(), start=1):
        if not line:
            raise RecoveryError("lifecycle contains a blank record")
        record = _parse_json(line, f"lifecycle row {expected_sequence}")
        if record.get("ledger_sequence") != expected_sequence:
            raise RecoveryError("lifecycle ledger sequence is not contiguous")
        digest = record.get("event_sha256")
        body = dict(record)
        body.pop("event_sha256", None)
        if digest != sha256_bytes(canonical_bytes(body)):
            raise RecoveryError("lifecycle event SHA mismatch")
        if record.get("previous_event_sha256") != previous:
            raise RecoveryError("lifecycle hash chain is broken")
        previous = digest
        records.append(record)

    first = records[:5]
    if [row.get("campaign_id") for row in first] != [FAILED_CAMPAIGN_ID] * 5:
        raise RecoveryError("attempt-001 lifecycle campaign identity drifted")
    if [row.get("campaign_sequence") for row in first] != [1, 2, 3, 4, 5]:
        raise RecoveryError("attempt-001 campaign sequence drifted")
    final = first[-1]
    details = final.get("details") or {}
    pending = details.get("pending_cold_child_outcome") or {}
    if (
        final.get("event") != "campaign_failed"
        or final.get("event_sha256") != LIFECYCLE_LAST_EVENT_SHA256
        or details.get("status") != "FAILED"
        or details.get("error_type") != "CampaignError"
        or details.get("error") != FAILED_ERROR
        or pending.get("ownership_monitor_errors") != FAILED_PENDING_MONITOR_ERRORS
        or details.get("completed_pair_count") != 0
        or details.get("owned_server_cleanup") != {"attempted": False}
        or details.get("stopped_without_force_or_additional_render") is not True
    ):
        raise RecoveryError("attempt-001 terminal failure evidence drifted")
    failure_state = details.get("failure_state") or {}
    if (
        failure_state.get("server_pid_receipt") != SERVER_PID
        or not math.isclose(
            float(failure_state.get("server_pid_create_time", -1)),
            SERVER_PROCESS_CREATE_TIME,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
    ):
        raise RecoveryError("attempt-001 terminal server identity drifted")

    return {
        "prefix": {
            "bytes": LIFECYCLE_PREFIX_BYTES,
            "sha256": LIFECYCLE_PREFIX_SHA256,
            "row_count": 5,
            "last_event_sha256": LIFECYCLE_LAST_EVENT_SHA256,
        },
        "current_file": {
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "row_count": len(records),
        },
        "terminal_failure": {
            "status": "FAILED",
            "error_type": "CampaignError",
            "error": FAILED_ERROR,
            "pending_monitor_errors": list(FAILED_PENDING_MONITOR_ERRORS),
            "completed_pair_count": 0,
            "owned_server_cleanup": {"attempted": False},
            "stopped_without_force_or_additional_render": True,
        },
    }


def collect_immutable_evidence(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    lifecycle_raw, lifecycle_snapshot = _snapshot(
        root / LIFECYCLE, LIFECYCLE.as_posix()
    )
    lifecycle = _validate_lifecycle(lifecycle_raw)
    lifecycle["current_file"]["path"] = lifecycle_snapshot["path"]

    run1_raw, run1_snapshot = _pinned(root, RUN1, RUN1_SHA256, RUN1_BYTES)
    alias_raw, alias_snapshot = _pinned(root, ALIAS, RUN1_SHA256, RUN1_BYTES)
    try:
        alias_is_run1_samefile = os.path.samefile(root / RUN1, root / ALIAS)
    except OSError as exc:
        raise RecoveryError(f"cannot prove run1/alias file independence: {exc}") from exc
    if alias_is_run1_samefile:
        raise RecoveryError("attempt-001 alias and immutable run1 are the same file")
    if alias_raw != run1_raw:
        raise RecoveryError("attempt-001 alias is not byte-equal to immutable run1")
    receipt = _parse_json(run1_raw, "attempt-001 run1 receipt")
    server = receipt.get("server_instance") or {}
    final_server = receipt.get("final_server_instance") or {}
    expected_server = {
        "serving_pid": SERVER_PID,
        "process_create_time": SERVER_PROCESS_CREATE_TIME,
    }
    if server != expected_server or final_server != expected_server:
        raise RecoveryError("attempt-001 run1 server identity drifted")
    if (
        receipt.get("run_number") != 1
        or receipt.get("run_count") != 1
        or receipt.get("status") != "PASS (cold)"
        or receipt.get("gate_pass") is not True
        or receipt.get("valid_measurement") is not True
        or receipt.get("pass") is not False
        or receipt.get("warm_pass") is not False
    ):
        raise RecoveryError("attempt-001 run1 is no longer exact cold-only evidence")
    if (
        receipt.get("output_path") != ARTIFACT.name
        or receipt.get("artifact_sha256") != ARTIFACT_SHA256
        or receipt.get("artifact_bytes") != ARTIFACT_BYTES
    ):
        raise RecoveryError("attempt-001 run1 artifact binding drifted")

    _, log_snapshot = _pinned(
        root, SERVER_LOG, SERVER_LOG_SHA256, SERVER_LOG_BYTES
    )
    _, artifact_snapshot = _pinned(
        root, ARTIFACT, ARTIFACT_SHA256, ARTIFACT_BYTES
    )
    identity = receipt.get("identity") or {}
    manager_identity = identity.get("manager_offline_probe_identity") or {}
    if (
        Path(str(manager_identity.get("log_path") or "")).name != SERVER_LOG.name
        or manager_identity.get("serving_pid") != SERVER_PID
    ):
        raise RecoveryError("attempt-001 run1 Manager/server-log binding drifted")

    return {
        "campaign_id": FAILED_CAMPAIGN_ID,
        "lifecycle": lifecycle,
        "run1_receipt": run1_snapshot,
        "alias": {
            **alias_snapshot,
            "byte_equal_to_run1": True,
        },
        "server_log": log_snapshot,
        "artifact": artifact_snapshot,
        "server_identity_from_run1": expected_server,
        "run1_disposition": {
            "status": "PASS (cold)",
            "gate_pass": True,
            "valid_measurement": True,
            "pass": False,
            "warm_pass": False,
            "completed_pair": False,
        },
    }


def collect_source_sha256s(root: Path) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for name, relative in SOURCE_PATHS.items():
        _, snapshot = _snapshot(root / relative, relative.as_posix())
        snapshots[name] = snapshot
    return snapshots


@contextmanager
def held_existing_coordinator(root: Path) -> Iterator[dict[str, Any]]:
    """Hold the pre-existing coordinator byte without creating or changing it."""

    path = Path(root).resolve() / ".coordinator.mutex"
    if not os.path.lexists(path):
        raise RecoveryError("coordinator carrier is absent; read-only recorder will not create it")
    if _is_reparse(path) or not path.is_file():
        raise RecoveryError("coordinator carrier is not a regular file")
    before = path.read_bytes()
    if len(before) < 1:
        raise RecoveryError("coordinator carrier has no lockable byte")
    try:
        handle = path.open("r+b", buffering=0)
    except OSError as exc:
        raise RecoveryError(f"cannot open coordinator carrier: {exc}") from exc
    locked = False
    try:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            raise RecoveryError("lab coordinator is held by another process") from exc
        locked = True
        yield {
            "path": ".coordinator.mutex",
            "carrier_preexisted": True,
            "carrier_bytes": len(before),
            "carrier_sha256": sha256_bytes(before),
            "acquired_nonblocking": True,
        }
    finally:
        if locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        else:
            handle.close()
    if path.read_bytes() != before:
        raise RecoveryError("coordinator carrier bytes changed during read-only observation")


def machine_clean_state(
    root: Path, coordinator: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the exact canonical ``runtime_state`` shape using local OS probes."""

    if coordinator.get("acquired_nonblocking") is not True:
        raise RecoveryError("current state must be observed while holding the coordinator")
    try:
        import psutil
    except ImportError as exc:
        raise RecoveryError("psutil is required for machine clean-state observation") from exc

    listeners: list[int | None] = []
    try:
        for connection in psutil.net_connections(kind="inet"):
            local = connection.laddr
            local_port = (
                getattr(local, "port", local[1] if len(local) > 1 else None)
                if local
                else None
            )
            if connection.status == psutil.CONN_LISTEN and local_port == 8199:
                listeners.append(connection.pid)
    except (psutil.AccessDenied, OSError) as exc:
        raise RecoveryError(f"cannot inspect port 8199 listeners: {exc}") from exc
    listener_pids = sorted(
        set(listeners), key=lambda value: -1 if value is None else value
    )

    try:
        actual_create_time = float(psutil.Process(SERVER_PID).create_time())
    except psutil.NoSuchProcess:
        expected_identity_live = False
    except (psutil.AccessDenied, OSError) as exc:
        raise RecoveryError(f"cannot verify historical server identity: {exc}") from exc
    else:
        expected_identity_live = math.isclose(
            actual_create_time,
            SERVER_PROCESS_CREATE_TIME,
            rel_tol=0.0,
            abs_tol=0.001,
        )

    root = Path(root).resolve()
    server_pid_path = root / ".server.pid"
    receipt_exists = os.path.lexists(server_pid_path)
    receipt_pid: int | None = None
    receipt_create_time: float | None = None
    if receipt_exists:
        if _is_reparse(server_pid_path) or not server_pid_path.is_file():
            raise RecoveryError("server PID receipt is not a regular file")
        try:
            receipt_pid = int(server_pid_path.read_text(encoding="utf-8-sig").strip())
        except (OSError, UnicodeError, ValueError) as exc:
            raise RecoveryError(f"server PID receipt cannot be verified: {exc}") from exc
        try:
            receipt_create_time = round(
                float(psutil.Process(receipt_pid).create_time()), 6
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            receipt_create_time = None

    return {
        "gpu_lock_exists": os.path.lexists(root / ".gpu.lock"),
        "suite_lock_exists": os.path.lexists(root / ".suite.lock"),
        "server_pid_receipt_exists": receipt_exists,
        "server_pid_receipt": receipt_pid,
        "server_pid_create_time": receipt_create_time,
        "queue_quarantine_exists": os.path.lexists(root / ".queue.quarantine.json"),
        "listener_pids_8199": listener_pids,
        "expected_server_identity_live": expected_identity_live,
    }


def require_clean_state(state: Mapping[str, Any]) -> None:
    if set(state) != RUNTIME_STATE_KEYS:
        raise RecoveryError("current clean state does not have canonical runtime_state shape")
    for field in (
        "gpu_lock_exists",
        "suite_lock_exists",
        "server_pid_receipt_exists",
        "queue_quarantine_exists",
        "expected_server_identity_live",
    ):
        if state.get(field) is not False:
            raise RecoveryError(f"current clean-state requirement failed: {field}")
    if state.get("server_pid_receipt") is not None:
        raise RecoveryError("current clean-state server PID receipt is not null")
    if state.get("server_pid_create_time") is not None:
        raise RecoveryError("current clean-state server receipt create time is not null")
    if state.get("listener_pids_8199") != []:
        raise RecoveryError("current clean-state port 8199 listener is not absent")


def _utc_from_ns(recorded_at_ns: int) -> str:
    return datetime.fromtimestamp(
        recorded_at_ns / 1_000_000_000, tz=timezone.utc
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")


def build_receipt(
    root: Path,
    current_clean_state: Mapping[str, Any],
    coordinator: Mapping[str, Any],
    *,
    recorded_at_ns: int,
) -> dict[str, Any]:
    if isinstance(recorded_at_ns, bool) or not isinstance(recorded_at_ns, int):
        raise RecoveryError("recorded_at_ns must be an integer")
    if recorded_at_ns <= 0:
        raise RecoveryError("recorded_at_ns must be positive")
    require_clean_state(current_clean_state)
    evidence = collect_immutable_evidence(root)
    sources = collect_source_sha256s(Path(root).resolve())
    if OPERATOR_CAPTURED_SHUTDOWN.get("pid") != SERVER_PID:
        raise RecoveryError("operator shutdown capture does not bind the run1 server PID")

    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-manual-cleanup-recovery",
        "recovery_id": RECOVERY_ID,
        "failed_campaign_id": FAILED_CAMPAIGN_ID,
        "status": "ATTEMPT_001_FAILED_COLD_ONLY_MANUAL_CLEANUP_RECORDED",
        "recorded_at_ns": recorded_at_ns,
        "recorded_at_utc": _utc_from_ns(recorded_at_ns),
        "immutable_evidence": evidence,
        "failed_incident": evidence["lifecycle"]["terminal_failure"],
        "operator_captured_cleanup": {
            "authority": (
                "verbatim operator capture of run_recipe.shutdown_lab_server(); "
                "the recorder did not witness or reconstruct the shutdown"
            ),
            "capture_timestamp": None,
            "capture_timestamp_status": "not present in the operator capture",
            "server_identity_from_immutable_run1": {
                "serving_pid": SERVER_PID,
                "process_create_time": SERVER_PROCESS_CREATE_TIME,
            },
            "shutdown_lab_server_return": dict(OPERATOR_CAPTURED_SHUTDOWN),
            "console_lines": list(OPERATOR_CAPTURED_CONSOLE),
        },
        "current_clean_state": dict(current_clean_state),
        "current_clean_state_evidence": {
            "authority": "machine-observed at receipt recording",
            "recorded_at_ns": recorded_at_ns,
            "shape": "scratch.run_h3_canonical_campaign.runtime_state",
            "expected_server_identity": {
                "serving_pid": SERVER_PID,
                "process_create_time": SERVER_PROCESS_CREATE_TIME,
            },
            "coordinator_guard": dict(coordinator),
            "http_or_comfyui_query_performed": False,
        },
        "source_sha256s": sources,
        "anti_circularity": {
            "main_music_campaign_source_included": False,
            "reason": (
                "the main campaign must add a literal full-file SHA256 pin for this "
                "O_EXCL receipt after publication"
            ),
            "receipt_is_resume_authority_without_external_sha_pin": False,
        },
        "certification_effect": {
            "attempt_001_status": "FAILED",
            "run1_is_valid_cold_evidence": True,
            "run1_is_warm_evidence": False,
            "completed_pair_count": 0,
            "normal_runner_shutdown_proved": False,
            "manual_cleanup_is_operator_captured": True,
            "current_postconditions_are_machine_verified": True,
            "promotion_or_pass_granted": False,
        },
        "recovery_policy": {
            "resume_campaign_id": RESUME_CAMPAIGN_ID,
            "pair_index": 1,
            "preserve_run1_immutable": True,
            "run1_may_not_pair_with_a_later_warm_run": True,
            "run2": {
                "run_number": 2,
                "config_run_count": 1,
                "role": "cold",
                "new_server_identity_required": True,
            },
            "run3": {
                "run_number": 3,
                "config_run_count": 2,
                "role": "warm",
                "must_immediately_follow": "run2",
                "same_server_identity_as": "run2",
                "shutdown_required": True,
            },
        },
        "safety": {
            "failed_lifecycle_appended_or_rewritten": False,
            "artifact_or_run_receipt_modified": False,
            "foreign_server_adopted_or_killed_by_recorder": False,
            "prompt_or_render_submitted_by_recorder": False,
            "network_used_by_recorder": False,
        },
        "success": True,
    }


def exclusive_write(root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    destination = root / RECOVERY
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if _is_reparse(parent) or not parent.is_dir():
        raise RecoveryError("recovery directory is not a real directory")
    encoded = receipt_bytes(payload)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(destination), flags, 0o600)
    except FileExistsError as exc:
        raise RecoveryError(f"recovery receipt already exists: {RECOVERY.as_posix()}") from exc
    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(fd, encoded[offset:])
            if written <= 0:
                raise RecoveryError("short O_EXCL recovery receipt write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    raw, snapshot = _snapshot(destination, RECOVERY.as_posix())
    if raw != encoded:
        raise RecoveryError("published recovery receipt differs from intended bytes")
    return snapshot


StateProbe = Callable[[Path, Mapping[str, Any]], dict[str, Any]]


def main(
    argv: list[str] | None = None,
    *,
    root: Path = ROOT,
    state_probe: StateProbe = machine_clean_state,
    clock_ns: Callable[[], int] = time.time_ns,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"create the fixed append-only receipt {RECOVERY.as_posix()}",
    )
    args = parser.parse_args(argv)
    try:
        with held_existing_coordinator(root) as coordinator:
            state = state_probe(Path(root), coordinator)
            payload = build_receipt(
                Path(root),
                state,
                coordinator,
                recorded_at_ns=clock_ns(),
            )
            if args.write:
                published = exclusive_write(Path(root), payload)
            else:
                published = None
    except (RecoveryError, OSError, ValueError) as exc:
        print(f"[h3-music-recovery] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if published is None:
        sys.stdout.write(receipt_bytes(payload).decode("utf-8"))
    else:
        print(
            json.dumps(
                {"status": "CREATED", "recovery_receipt": published},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
