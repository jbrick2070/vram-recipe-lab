#!/usr/bin/env python3
"""Record attempt-003 operator transport without changing campaign status.

The recorder is read-only by default.  ``--write`` exclusively creates the
fixed ``launch.json`` receipt and then appends a separately hash-chained
``operator_launch_recorded`` event.  If publication stopped after the O_EXCL
receipt but before the event, the same command verifies the existing receipt
byte-for-byte and appends only the missing event.

This surface records PowerShell-captured process provenance and stable stdout /
stderr bytes.  It never upgrades a recipe, pair, or campaign certification;
exit 120 and BrokenPipe-looking stderr remain transport observations only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence

import record_h3_music_recovery as clean_probe
import run_h3_canonical_campaign as canon


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_ID = "h3music-20260810T023023Z-97ca44b2-attempt-003"
OPERATOR_EVENT_ID = f"{ATTEMPT_ID}-operator-launch-001"
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")

CAMPAIGN_RELATIVE = Path("scratch/run_h3_unconditioned_music_campaign.py")
RECORDER_RELATIVE = Path("scratch/record_h3_music_operator_launch.py")
LAUNCHER_RELATIVE = Path("scratch/start_h3_music_attempt3.ps1")
CANONICAL_RELATIVE = Path("scratch/run_h3_canonical_campaign.py")
CLEAN_PROBE_RELATIVE = Path("scratch/record_h3_music_recovery.py")
RUNNER_RELATIVE = Path("run_recipe.py")
LAB_LOCKS_RELATIVE = Path("lab_locks.py")
MANAGER_GUARD_RELATIVE = Path("scratch/h3_manager_offline_guard.py")
MANAGER_BOOT_RELATIVE = Path("boot_h3_manager_offline_test.cmd")
LIFECYCLE_RELATIVE = Path("results/h3_unconditioned_music_campaign/lifecycle.jsonl")
OPERATOR_ROOT_RELATIVE = Path(
    "results/h3_unconditioned_music_campaign/operator_logs"
)
ATTEMPT_DIRECTORY_RELATIVE = OPERATOR_ROOT_RELATIVE / ATTEMPT_ID
STDOUT_RELATIVE = ATTEMPT_DIRECTORY_RELATIVE / "stdout.log"
STDERR_RELATIVE = ATTEMPT_DIRECTORY_RELATIVE / "stderr.log"
RECEIPT_RELATIVE = ATTEMPT_DIRECTORY_RELATIVE / "launch.json"

SOURCE_PATHS = {
    "operator_recorder": RECORDER_RELATIVE,
    "operator_launcher": LAUNCHER_RELATIVE,
    "campaign": CAMPAIGN_RELATIVE,
    "canonical_campaign": CANONICAL_RELATIVE,
    "clean_state_probe": CLEAN_PROBE_RELATIVE,
    "run_recipe": RUNNER_RELATIVE,
    "lab_locks": LAB_LOCKS_RELATIVE,
    "manager_guard": MANAGER_GUARD_RELATIVE,
    "manager_test_boot": MANAGER_BOOT_RELATIVE,
}

CAMPAIGN_SOURCE_LABELS = {
    "campaign": "campaign",
    "campaign_canonical": "canonical_campaign",
    "runner": "run_recipe",
    "lab_locks": "lab_locks",
    "manager_guard": "manager_guard",
    "manager_test_boot_cmd": "manager_test_boot",
}

TERMINAL_EVENTS = {"campaign_completed", "campaign_failed"}
TRANSPORT_CERTIFICATION_EFFECT = {
    "campaign_status_changed": False,
    "recipe_or_pair_certification_granted": False,
    "exit_120_reclassified_as_success": False,
    "human_quality_judgment_granted": False,
}


class OperatorLaunchError(RuntimeError):
    """Operator transport evidence is incomplete, changed, or unsafe."""


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


def _absolute(root: Path, relative: Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(root).resolve() / relative)))


def _same_path(left: str | os.PathLike[str], right: Path) -> bool:
    return os.path.normcase(os.path.abspath(os.fspath(left))) == os.path.normcase(
        os.path.abspath(os.fspath(right))
    )


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x400)


def _require_real_directory(path: Path, label: str) -> None:
    if not os.path.lexists(path):
        raise OperatorLaunchError(f"{label} is absent: {path}")
    if _is_reparse(path) or not path.is_dir():
        raise OperatorLaunchError(f"{label} is not a real directory: {path}")


def stable_snapshot(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if not os.path.lexists(path):
        raise OperatorLaunchError(f"{label} is absent: {path}")
    if _is_reparse(path) or not path.is_file():
        raise OperatorLaunchError(f"{label} is not a real regular file: {path}")
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise OperatorLaunchError(f"cannot read stable {label}: {exc}") from exc
    before_identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
    )
    after_identity = (
        int(after.st_dev),
        int(after.st_ino),
        int(after.st_size),
        int(after.st_mtime_ns),
    )
    if before_identity != after_identity or len(raw) != int(after.st_size):
        raise OperatorLaunchError(f"{label} changed while being read")
    return raw, {
        "path": str(path),
        "device": int(after.st_dev),
        "inode": int(after.st_ino),
        "link_count": int(after.st_nlink),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }


def strict_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw, _ = stable_snapshot(path, label)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise OperatorLaunchError(f"{label} has a UTF-8 BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorLaunchError(f"{label} is not UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise OperatorLaunchError(f"{label} is not a JSON object")
    return value, raw


def source_snapshots(root: Path) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for label, relative in SOURCE_PATHS.items():
        raw, snapshot = stable_snapshot(_absolute(root, relative), f"{label} source")
        if raw.startswith(b"\xef\xbb\xbf"):
            raise OperatorLaunchError(f"{label} source has a UTF-8 BOM")
        snapshots[label] = snapshot
    return snapshots


def expected_paths(root: Path) -> dict[str, Path]:
    root = Path(root).resolve()
    return {
        "root": root,
        "operator_root": _absolute(root, OPERATOR_ROOT_RELATIVE),
        "attempt_directory": _absolute(root, ATTEMPT_DIRECTORY_RELATIVE),
        "stdout": _absolute(root, STDOUT_RELATIVE),
        "stderr": _absolute(root, STDERR_RELATIVE),
        "receipt": _absolute(root, RECEIPT_RELATIVE),
        "lifecycle": _absolute(root, LIFECYCLE_RELATIVE),
        "campaign": _absolute(root, CAMPAIGN_RELATIVE),
    }


def expected_campaign_argv(root: Path) -> list[str]:
    paths = expected_paths(root)
    return [
        str(PYTHON),
        "-u",
        str(paths["campaign"]),
        "--run",
        "--resume-attempt-002",
        "--campaign-id",
        ATTEMPT_ID,
        "--operator-stdout-log",
        str(paths["stdout"]),
        "--operator-stderr-log",
        str(paths["stderr"]),
    ]


def expected_operator_log_contract(
    root: Path, sources: Mapping[str, Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    paths = expected_paths(root)
    source_map = dict(sources or source_snapshots(root))
    return {
        "authority": "operator transport only",
        "attempt_directory": str(paths["attempt_directory"]),
        "stdout_log": str(paths["stdout"]),
        "stderr_log": str(paths["stderr"]),
        "launch_receipt": str(paths["receipt"]),
        "launcher_source": _source_triplet(source_map["operator_launcher"]),
        "recorder_source": _source_triplet(source_map["operator_recorder"]),
        "growing_logs_excluded_from_source_evidence": True,
        "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
    }


def validate_attempt_directory(root: Path) -> dict[str, dict[str, Any]]:
    paths = expected_paths(root)
    _require_real_directory(paths["operator_root"], "operator-log root")
    _require_real_directory(paths["attempt_directory"], "attempt directory")
    receipt_exists = os.path.lexists(paths["receipt"])
    allowed = {"stdout.log", "stderr.log"}
    if receipt_exists:
        allowed.add("launch.json")
    found = {entry.name for entry in paths["attempt_directory"].iterdir()}
    if found != allowed:
        raise OperatorLaunchError(
            f"attempt directory entries drift: {sorted(found)} != {sorted(allowed)}"
        )
    stdout_raw, stdout = stable_snapshot(paths["stdout"], "operator stdout")
    stderr_raw, stderr = stable_snapshot(paths["stderr"], "operator stderr")
    try:
        if os.path.samefile(paths["stdout"], paths["stderr"]):
            raise OperatorLaunchError("operator stdout and stderr are the same file")
    except OperatorLaunchError:
        raise
    except OSError as exc:
        raise OperatorLaunchError(f"cannot distinguish operator logs: {exc}") from exc
    stdout["empty"] = len(stdout_raw) == 0
    stderr["empty"] = len(stderr_raw) == 0
    return {"stdout": stdout, "stderr": stderr}


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OperatorLaunchError(f"{label} must be an ISO-8601 UTC string ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise OperatorLaunchError(f"{label} is invalid: {exc}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise OperatorLaunchError(f"{label} is not UTC")
    return parsed


def validate_capture(capture: Mapping[str, Any], root: Path) -> dict[str, Any]:
    paths = expected_paths(root)
    exact_keys = {
        "authority",
        "pid",
        "started_at_utc",
        "ended_at_utc",
        "exit_code",
        "cwd",
        "stdout_log",
        "stderr_log",
        "argv",
    }
    if set(capture) != exact_keys:
        raise OperatorLaunchError("PowerShell capture field set drift")
    if capture.get("authority") != "PowerShell Start-Process -Wait -PassThru":
        raise OperatorLaunchError("PowerShell capture authority drift")
    pid = capture.get("pid")
    exit_code = capture.get("exit_code")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise OperatorLaunchError("PowerShell-captured PID is invalid")
    if (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or not -(2**31) <= exit_code < 2**31
    ):
        raise OperatorLaunchError("PowerShell-captured exit code is invalid")
    started = _parse_utc(capture.get("started_at_utc"), "started_at_utc")
    ended = _parse_utc(capture.get("ended_at_utc"), "ended_at_utc")
    if ended < started:
        raise OperatorLaunchError("PowerShell process end precedes its start")
    if not _same_path(capture.get("cwd", ""), paths["root"]):
        raise OperatorLaunchError("PowerShell-captured cwd drift")
    if not _same_path(capture.get("stdout_log", ""), paths["stdout"]):
        raise OperatorLaunchError("PowerShell-captured stdout path drift")
    if not _same_path(capture.get("stderr_log", ""), paths["stderr"]):
        raise OperatorLaunchError("PowerShell-captured stderr path drift")
    if capture.get("argv") != expected_campaign_argv(root):
        raise OperatorLaunchError("PowerShell-captured campaign argv drift")
    return dict(capture)


def capture_from_args(args: argparse.Namespace, root: Path) -> dict[str, Any] | None:
    values = {
        "pid": args.pid,
        "started_at_utc": args.started_at_utc,
        "ended_at_utc": args.ended_at_utc,
        "exit_code": args.exit_code,
        "cwd": args.cwd,
        "stdout_log": args.stdout_log,
        "stderr_log": args.stderr_log,
    }
    present = {key: value is not None for key, value in values.items()}
    if not any(present.values()):
        return None
    if not all(present.values()):
        missing = sorted(key for key, is_present in present.items() if not is_present)
        raise OperatorLaunchError(
            f"PowerShell capture arguments are incomplete: {missing}"
        )
    capture = {
        "authority": "PowerShell Start-Process -Wait -PassThru",
        **values,
        "argv": expected_campaign_argv(root),
    }
    return validate_capture(capture, root)


def _source_triplet(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": snapshot.get("path"),
        "bytes": snapshot.get("bytes"),
        "sha256": snapshot.get("sha256"),
    }


def validate_operator_transport_preflight(
    root: Path,
    sources: Mapping[str, Mapping[str, Any]],
    preflight: Any,
    final_logs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    paths = expected_paths(root)
    exact_keys = {
        "contract",
        "attempt_directory_entries",
        "fd_identities",
        "growing_log_bytes_hashed_as_sources",
    }
    if not isinstance(preflight, dict) or set(preflight) != exact_keys:
        raise OperatorLaunchError("attempt-003 operator transport preflight shape drift")
    if preflight.get("contract") != expected_operator_log_contract(root, sources):
        raise OperatorLaunchError("attempt-003 operator transport preflight contract drift")
    if preflight.get("attempt_directory_entries") != ["stderr.log", "stdout.log"]:
        raise OperatorLaunchError("attempt-003 operator transport preflight entries drift")
    if preflight.get("growing_log_bytes_hashed_as_sources") is not False:
        raise OperatorLaunchError("attempt-003 growing operator logs were treated as sources")

    identities = preflight.get("fd_identities")
    if not isinstance(identities, dict) or set(identities) != {"stdout", "stderr"}:
        raise OperatorLaunchError("attempt-003 operator descriptor identity shape drift")
    expected_fds = {"stdout": 1, "stderr": 2}
    resolved: dict[str, dict[str, Any]] = {}
    for label in ("stdout", "stderr"):
        identity = identities.get(label)
        final = final_logs.get(label)
        if not isinstance(identity, dict) or set(identity) != {
            "path",
            "fd",
            "device",
            "inode",
            "link_count",
            "regular_file",
        }:
            raise OperatorLaunchError(
                f"attempt-003 {label} descriptor identity field set drift"
            )
        if not isinstance(final, Mapping):
            raise OperatorLaunchError(f"attempt-003 final {label} snapshot is missing")
        fd = identity.get("fd")
        device = identity.get("device")
        inode = identity.get("inode")
        link_count = identity.get("link_count")
        if fd != expected_fds[label] or isinstance(fd, bool):
            raise OperatorLaunchError(f"attempt-003 {label} descriptor number drift")
        if (
            not isinstance(device, int)
            or isinstance(device, bool)
            or device < 0
            or not isinstance(inode, int)
            or isinstance(inode, bool)
            or inode <= 0
            or link_count != 1
            or isinstance(link_count, bool)
            or identity.get("regular_file") is not True
        ):
            raise OperatorLaunchError(
                f"attempt-003 {label} descriptor identity values are invalid"
            )
        if identity.get("path") != str(paths[label]):
            raise OperatorLaunchError(f"attempt-003 {label} descriptor path drift")
        if final.get("path") != str(paths[label]):
            raise OperatorLaunchError(f"attempt-003 final {label} snapshot path drift")
        if final.get("link_count") != 1:
            raise OperatorLaunchError(
                f"attempt-003 final {label} log link count is not exactly one"
            )
        if (final.get("device"), final.get("inode")) != (device, inode):
            raise OperatorLaunchError(
                f"attempt-003 {label} log identity changed after campaign start"
            )
        resolved[label] = dict(identity)
    if (
        resolved["stdout"]["fd"] == resolved["stderr"]["fd"]
        or (
            resolved["stdout"]["device"],
            resolved["stdout"]["inode"],
        )
        == (
            resolved["stderr"]["device"],
            resolved["stderr"]["inode"],
        )
    ):
        raise OperatorLaunchError("attempt-003 operator descriptors are not distinct")
    return dict(preflight)


def validate_lifecycle(
    root: Path,
    sources: Mapping[str, Mapping[str, Any]],
    final_logs: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = expected_paths(root)
    raw, full_snapshot = stable_snapshot(paths["lifecycle"], "campaign lifecycle")
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise OperatorLaunchError("campaign lifecycle encoding or record boundary drift")
    lines = raw.splitlines(keepends=True)
    records: list[dict[str, Any]] = []
    previous = None
    for expected_sequence, encoded in enumerate(lines, start=1):
        try:
            record = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OperatorLaunchError(
                f"campaign lifecycle row {expected_sequence} is malformed: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise OperatorLaunchError("campaign lifecycle row is not an object")
        if record.get("ledger_sequence") != expected_sequence:
            raise OperatorLaunchError("campaign lifecycle ledger sequence is not contiguous")
        digest = record.get("event_sha256")
        body = dict(record)
        body.pop("event_sha256", None)
        if digest != sha256_bytes(canonical_bytes(body)):
            raise OperatorLaunchError("campaign lifecycle event SHA drift")
        if record.get("previous_event_sha256") != previous:
            raise OperatorLaunchError("campaign lifecycle hash chain is broken")
        previous = digest
        records.append(record)

    attempt_rows = [row for row in records if row.get("campaign_id") == ATTEMPT_ID]
    started_rows = [row for row in attempt_rows if row.get("event") == "campaign_started"]
    terminal_rows = [row for row in attempt_rows if row.get("event") in TERMINAL_EVENTS]
    if len(started_rows) != 1 or len(terminal_rows) != 1:
        raise OperatorLaunchError(
            "attempt-003 lifecycle must contain one campaign_started and one terminal event"
        )
    started = started_rows[0]
    terminal = terminal_rows[0]
    if attempt_rows[-1] != terminal:
        raise OperatorLaunchError("attempt-003 has records after its terminal event")
    details = terminal.get("details") or {}
    expected_status = "COMPLETE" if terminal.get("event") == "campaign_completed" else "FAILED"
    if details.get("status") != expected_status:
        raise OperatorLaunchError("attempt-003 terminal status/event mismatch")

    contract = (started.get("details") or {}).get("operator_logs")
    expected_contract = expected_operator_log_contract(root, sources)
    if contract != expected_contract:
        raise OperatorLaunchError("attempt-003 operator-log contract drift")
    if final_logs is None:
        final_logs = validate_attempt_directory(root)
    preflight = validate_operator_transport_preflight(
        root,
        sources,
        (started.get("details") or {}).get("operator_transport_preflight"),
        final_logs,
    )
    started_sources = (started.get("details") or {}).get("sources")
    if not isinstance(started_sources, dict):
        raise OperatorLaunchError("attempt-003 source evidence is missing")
    for lifecycle_label, current_label in CAMPAIGN_SOURCE_LABELS.items():
        recorded = started_sources.get(lifecycle_label)
        current = sources.get(current_label)
        if not isinstance(recorded, dict) or not isinstance(current, dict):
            raise OperatorLaunchError(
                f"attempt-003 source evidence is missing: {lifecycle_label}"
            )
        if _source_triplet(recorded) != _source_triplet(current):
            raise OperatorLaunchError(
                f"attempt-003 source evidence changed: {lifecycle_label}"
            )

    terminal_index = records.index(terminal)
    prefix_raw = b"".join(lines[: terminal_index + 1])
    event_rows = [
        row for row in records if row.get("campaign_id") == OPERATOR_EVENT_ID
    ]
    if len(event_rows) > 1:
        raise OperatorLaunchError("duplicate operator launch lifecycle records")
    operator_event = event_rows[0] if event_rows else None
    allowed_after_terminal = [operator_event] if operator_event is not None else []
    if records[terminal_index + 1 :] != allowed_after_terminal:
        raise OperatorLaunchError(
            "unexpected lifecycle records follow the attempt-003 terminal event"
        )
    if operator_event is not None and operator_event.get("event") != "operator_launch_recorded":
        raise OperatorLaunchError("operator lifecycle event name drift")

    return {
        "full_snapshot": full_snapshot,
        "prefix": {
            "path": str(paths["lifecycle"]),
            "bytes": len(prefix_raw),
            "sha256": sha256_bytes(prefix_raw),
            "row_count": terminal_index + 1,
            "last_event_sha256": terminal["event_sha256"],
        },
        "started": started,
        "terminal": terminal,
        "operator_event": operator_event,
        "operator_transport_preflight": preflight,
    }


def stderr_observations(stderr_raw: bytes, exit_code: int) -> dict[str, Any]:
    text = stderr_raw.decode("utf-8", errors="replace")
    broken_pipe_token = "BrokenPipeError" in text
    textio_token = "TextIOWrapper" in text or "<stdout>" in text
    return {
        "exit_code_120_observed": exit_code == 120,
        "broken_pipe_token_observed": broken_pipe_token,
        "textio_flush_context_token_observed": textio_token,
        "possible_cpython_broken_pipe_marker_observed": (
            exit_code == 120 and broken_pipe_token and textio_token
        ),
        "diagnostic_authority": "operator stderr byte observation only",
        "cause_confirmed": False,
        "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
    }


def build_receipt(
    root: Path,
    capture: Mapping[str, Any],
    current_clean_state: Mapping[str, Any],
    coordinator: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(root).resolve()
    capture = validate_capture(capture, root)
    clean_probe.require_clean_state(current_clean_state)
    if coordinator.get("acquired_nonblocking") is not True:
        raise OperatorLaunchError("clean state was not observed under the coordinator")
    sources = source_snapshots(root)
    logs = validate_attempt_directory(root)
    stderr_raw, stderr_snapshot = stable_snapshot(
        expected_paths(root)["stderr"], "operator stderr"
    )
    stderr_snapshot["empty"] = len(stderr_raw) == 0
    if stderr_snapshot != logs["stderr"]:
        raise OperatorLaunchError("operator stderr changed between final observations")
    lifecycle = validate_lifecycle(root, sources, logs)
    terminal = lifecycle["terminal"]
    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-music-operator-launch",
        "attempt_id": ATTEMPT_ID,
        "status": "TRANSPORT_CAPTURED",
        "transport_recorded": True,
        "powershell_capture": capture,
        "campaign_argv": expected_campaign_argv(root),
        "campaign_terminal": {
            "event": terminal["event"],
            "status": (terminal.get("details") or {}).get("status"),
            "event_sha256": terminal["event_sha256"],
            "lifecycle_prefix": lifecycle["prefix"],
        },
        "operator_logs": logs,
        "operator_transport_preflight": lifecycle["operator_transport_preflight"],
        "stderr_observations": stderr_observations(
            stderr_raw, int(capture["exit_code"])
        ),
        "current_clean_state": dict(current_clean_state),
        "current_clean_state_evidence": {
            "authority": "machine-observed after campaign exit",
            "coordinator_guard": dict(coordinator),
            "http_or_comfyui_query_performed": False,
        },
        "source_sha256s": sources,
        "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
        "safety": {
            "campaign_or_recipe_file_modified": False,
            "prompt_or_render_submitted_by_recorder": False,
            "foreign_server_adopted_or_killed": False,
            "network_used": False,
            "existing_transport_file_overwritten": False,
        },
    }


def exclusive_write(root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    path = expected_paths(root)["receipt"]
    encoded = receipt_bytes(payload)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise OperatorLaunchError(f"operator launch receipt already exists: {path}") from exc
    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(fd, encoded[offset:])
            if written <= 0:
                raise OperatorLaunchError("short O_EXCL operator launch receipt write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    raw, snapshot = stable_snapshot(path, "operator launch receipt")
    if raw != encoded:
        raise OperatorLaunchError("published operator launch receipt bytes drifted")
    return snapshot


def expected_event_details(
    receipt_snapshot: Mapping[str, Any], lifecycle: Mapping[str, Any]
) -> dict[str, Any]:
    terminal = lifecycle["terminal"]
    return {
        "authority": "operator transport only",
        "attempt_id": ATTEMPT_ID,
        "attempt_terminal_event_sha256": terminal["event_sha256"],
        "launch_receipt": dict(receipt_snapshot),
        "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
    }


def validate_existing_event(
    lifecycle: Mapping[str, Any], receipt_snapshot: Mapping[str, Any]
) -> bool:
    event = lifecycle.get("operator_event")
    if event is None:
        return False
    if event.get("campaign_id") != OPERATOR_EVENT_ID:
        raise OperatorLaunchError("operator lifecycle campaign id drift")
    if event.get("details") != expected_event_details(receipt_snapshot, lifecycle):
        raise OperatorLaunchError("operator lifecycle receipt binding drift")
    return True


def append_event(
    root: Path,
    lifecycle: Mapping[str, Any],
    receipt_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if lifecycle.get("operator_event") is not None:
        raise OperatorLaunchError("operator launch lifecycle event already exists")
    ledger = canon.AppendOnlyLifecycle(expected_paths(root)["lifecycle"], OPERATOR_EVENT_ID)
    ledger.append(
        "operator_launch_recorded",
        expected_event_details(receipt_snapshot, lifecycle),
    )
    refreshed = validate_lifecycle(root, source_snapshots(root))
    if not validate_existing_event(refreshed, receipt_snapshot):
        raise OperatorLaunchError("operator launch lifecycle append was not retained")
    return refreshed["operator_event"]


def _capture_from_existing(receipt: Mapping[str, Any], root: Path) -> dict[str, Any]:
    capture = receipt.get("powershell_capture")
    if not isinstance(capture, dict):
        raise OperatorLaunchError("existing launch receipt lacks PowerShell capture")
    return validate_capture(capture, root)


StateProbe = Callable[[Path, Mapping[str, Any]], dict[str, Any]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--started-at-utc")
    parser.add_argument("--ended-at-utc")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--cwd")
    parser.add_argument("--stdout-log")
    parser.add_argument("--stderr-log")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = ROOT,
    state_probe: StateProbe = clean_probe.machine_clean_state,
) -> int:
    args = parse_args(argv)
    root = Path(root).resolve()
    paths = expected_paths(root)
    try:
        supplied_capture = capture_from_args(args, root)
        existing_receipt: dict[str, Any] | None = None
        existing_raw: bytes | None = None
        if os.path.lexists(paths["receipt"]):
            existing_receipt, existing_raw = strict_json(
                paths["receipt"], "operator launch receipt"
            )
        capture = supplied_capture
        if capture is None and existing_receipt is not None:
            capture = _capture_from_existing(existing_receipt, root)
        if capture is None:
            raise OperatorLaunchError(
                "PowerShell capture arguments are required before receipt publication"
            )

        with clean_probe.held_existing_coordinator(root) as coordinator:
            state = state_probe(root, coordinator)
            payload = build_receipt(root, capture, state, coordinator)
            intended = receipt_bytes(payload)
            lifecycle = validate_lifecycle(root, source_snapshots(root))
            if existing_receipt is not None:
                if existing_raw != intended or existing_receipt != payload:
                    raise OperatorLaunchError(
                        "existing operator launch receipt differs from current exact evidence"
                    )
                _, receipt_snapshot = stable_snapshot(
                    paths["receipt"], "operator launch receipt"
                )
            elif lifecycle.get("operator_event") is not None:
                raise OperatorLaunchError(
                    "operator lifecycle event exists without its launch receipt"
                )
            elif args.write:
                receipt_snapshot = exclusive_write(root, payload)
            else:
                receipt_snapshot = {
                    "path": str(paths["receipt"]),
                    "bytes": len(intended),
                    "sha256": sha256_bytes(intended),
                }

            event_present = validate_existing_event(lifecycle, receipt_snapshot)
            if args.write and not event_present:
                append_event(root, lifecycle, receipt_snapshot)
                event_present = True

        result = {
            "status": (
                "RECORDED"
                if os.path.lexists(paths["receipt"]) and event_present
                else "READ_ONLY_PROPOSAL"
            ),
            "attempt_id": ATTEMPT_ID,
            "receipt": receipt_snapshot,
            "operator_launch_event_present": event_present,
            "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
        }
        if not args.quiet:
            if args.write or existing_receipt is not None:
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            else:
                sys.stdout.write(receipt_bytes(payload).decode("utf-8"))
        return 0
    except (
        OperatorLaunchError,
        clean_probe.RecoveryError,
        OSError,
        ValueError,
        canon.CampaignError,
    ) as exc:
        if not args.quiet:
            print(
                f"[h3-music-operator-launch] FAIL: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
