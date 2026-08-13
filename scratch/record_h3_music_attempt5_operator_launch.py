#!/usr/bin/env python3
"""Record the completed attempt-005 operator transport with O_EXCL.

The campaign owns rendering and the lifecycle. This post-exit recorder only
binds the launcher-observed exit to exact process self-report, final stream
descriptors, the terminal lifecycle row, and the corrected attempt-004
recovery authority. Default invocation is read-only; ``--write`` is the only
write path. It never probes a server, GPU, listener, lock state, or network.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Callable, Iterator, Mapping, Sequence


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

BASE_ID = "h3music-20260810T023023Z-97ca44b2"
FAILED_ATTEMPT_ID = f"{BASE_ID}-attempt-004"
ATTEMPT_ID = f"{BASE_ID}-attempt-005"
RECOVERY_ID = f"{FAILED_ATTEMPT_ID}-recovery-002"
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")

CAMPAIGN_ROOT = Path("results/h3_unconditioned_music_campaign")
OPERATOR_DIRECTORY = CAMPAIGN_ROOT / "operator_logs" / ATTEMPT_ID
STDOUT = OPERATOR_DIRECTORY / "stdout.log"
STDERR = OPERATOR_DIRECTORY / "stderr.log"
RECEIPT = OPERATOR_DIRECTORY / "launch.json"
LIFECYCLE = CAMPAIGN_ROOT / "lifecycle.jsonl"

CAMPAIGN = Path("scratch/run_h3_unconditioned_music_campaign.py")
LAUNCHER = Path("scratch/start_h3_music_attempt5.ps1")
RECORDER = Path("scratch/record_h3_music_attempt5_operator_launch.py")
RECOVERY4_RECORDER = Path("scratch/record_h3_music_attempt4_recovery.py")
RECOVERY4_RECEIPT = CAMPAIGN_ROOT / "recoveries" / (
    f"{FAILED_ATTEMPT_ID}-timeout-recovery-correction-001.json"
)
RECOVERY4_RECORDER_BYTES = 38_580
RECOVERY4_RECORDER_SHA256 = (
    "d35ec3c0ddc3ae495c4bc56d5166a716f0da57cfbcb32ac6876373ab61528335"
)
RECOVERY4_RECEIPT_BYTES = 60_939
RECOVERY4_RECEIPT_SHA256 = (
    "fef1ef0401b5e4f13dc11b7405224e6b792a1a18c3b607fce806468f598f7dcd"
)

SOURCE_PATHS = {
    "campaign": CAMPAIGN,
    "attempt5_operator_launcher": LAUNCHER,
    "attempt5_operator_recorder": RECORDER,
    "attempt4_recovery_recorder": RECOVERY4_RECORDER,
    "attempt4_recovery_receipt": RECOVERY4_RECEIPT,
}
TRANSPORT_CERTIFICATION_EFFECT = {
    "campaign_status_changed": False,
    "recipe_or_pair_certification_granted": False,
    "human_quality_judgment_granted": False,
}
SUCCESS_LIFECYCLE_ROWS = 88
SUCCESS_TERMINAL_LEDGER_SEQUENCE = 88
SUCCESS_TERMINAL_CAMPAIGN_SEQUENCE = 23
SUCCESS_CLEAN_STATE = {
    "gpu_lock_exists": False,
    "suite_lock_exists": False,
    "server_pid_receipt_exists": False,
    "server_pid_receipt": None,
    "server_pid_create_time": None,
    "queue_quarantine_exists": False,
    "expected_server_identity_live": False,
    "listener_pids_8199": [],
}


class OperatorReceiptError(RuntimeError):
    """Attempt-005 operator evidence is missing, mutable, or inconsistent."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def receipt_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), indent=2, sort_keys=True) + "\n").encode("utf-8")


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def snapshot(root: Path, relative: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    """Read one independent regular file while binding path and descriptor."""
    path = Path(os.path.abspath(os.fspath(Path(root) / relative)))
    if not os.path.lexists(path) or _is_reparse(path):
        raise OperatorReceiptError(f"missing or reparse {label}")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or int(before.st_nlink) != 1:
        raise OperatorReceiptError(f"{label} is not an independent regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        descriptor_before = os.fstat(fd)
        chunks: list[bytes] = []
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

    def identity(value: os.stat_result) -> tuple[int, ...]:
        return (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_mode),
            int(value.st_nlink),
            int(value.st_size),
            int(value.st_mtime_ns),
        )

    if (
        identity(before) != identity(after)
        or identity(before) != identity(descriptor_before)
        or identity(before) != identity(descriptor_after)
        or _is_reparse(path)
        or len(raw) != int(after.st_size)
    ):
        raise OperatorReceiptError(f"{label} changed during descriptor read")
    return raw, {
        "path": str(path),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "device": int(after.st_dev),
        "inode": int(after.st_ino),
        "mode": int(after.st_mode),
        "link_count": 1,
        "mtime_ns": int(after.st_mtime_ns),
        "regular_file": True,
        "reparse_point": False,
    }


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise OperatorReceiptError(f"{label} has a UTF-8 BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorReceiptError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise OperatorReceiptError(f"{label} is not a JSON object")
    return value


def validate_recovery_authority(raw: bytes) -> dict[str, Any]:
    value = _parse_json(raw, "corrected attempt-004 recovery receipt")
    policy = value.get("recovery_policy") or {}
    pair11 = policy.get("pair11") or {}
    effect = value.get("certification_effect") or {}
    superseded = (value.get("immutable_evidence") or {}).get(
        "superseded_recovery"
    ) or {}
    if (
        value.get("receipt_schema_version") != 1
        or value.get("receipt_kind")
        != "h3-unconditioned-music-attempt-004-timeout-recovery-correction"
        or value.get("recovery_id") != RECOVERY_ID
        or value.get("failed_campaign_id") != FAILED_ATTEMPT_ID
        or value.get("resume_campaign_id") != ATTEMPT_ID
        or value.get("success") is not True
        or policy.get("resume_campaign_id") != ATTEMPT_ID
        or policy.get("carry_pair_indices") != list(range(1, 10))
        or policy.get("execute_pair_indices") != [10, 11]
        or policy.get("new_leg_count") != 4
        or pair11.get("recipe")
        != "h3_unconditioned_music_scene_seed42_f277"
        or effect.get("superseded_recovery_usable_as_authority") is not False
        or superseded.get("classification") != "UNUSABLE_RESUME_AUTHORITY"
        or superseded.get("must_not_authorize_render") is not True
        or superseded.get("superseded_by_recovery_id") != RECOVERY_ID
    ):
        raise OperatorReceiptError("corrected recovery authority semantics drifted")
    return {
        "recovery_id": RECOVERY_ID,
        "failed_campaign_id": FAILED_ATTEMPT_ID,
        "resume_campaign_id": ATTEMPT_ID,
        "carry_pair_indices": list(range(1, 10)),
        "execute_pair_indices": [10, 11],
        "new_leg_count": 4,
        "pair11_recipe": pair11["recipe"],
        "superseded_recovery_usable_as_authority": False,
    }


def source_snapshots(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    raws: dict[str, bytes] = {}
    for label, relative in SOURCE_PATHS.items():
        raw, result[label] = snapshot(root, relative, label)
        raws[label] = raw
        if label != "attempt4_recovery_receipt" and raw.startswith(b"\xef\xbb\xbf"):
            raise OperatorReceiptError(f"{label} source has a UTF-8 BOM")
    pins = {
        "attempt4_recovery_recorder": (
            RECOVERY4_RECORDER_BYTES,
            RECOVERY4_RECORDER_SHA256,
        ),
        "attempt4_recovery_receipt": (
            RECOVERY4_RECEIPT_BYTES,
            RECOVERY4_RECEIPT_SHA256,
        ),
    }
    for label, (expected_bytes, expected_sha256) in pins.items():
        current = result[label]
        if (
            current["bytes"] != expected_bytes
            or current["sha256"] != expected_sha256
        ):
            raise OperatorReceiptError(f"literal recovery4 pin drifted: {label}")
    validate_recovery_authority(raws["attempt4_recovery_receipt"])
    return result


def expected_campaign_argv(root: Path) -> list[str]:
    root = Path(os.path.abspath(os.fspath(root)))
    return [
        str(PYTHON),
        "-B",
        "-u",
        str(root / CAMPAIGN),
        "--run",
        "--resume-attempt-004",
        "--campaign-id",
        ATTEMPT_ID,
        "--operator-stdout-log",
        str(root / STDOUT),
        "--operator-stderr-log",
        str(root / STDERR),
    ]


def _source_triplet(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": value.get("path"),
        "bytes": value.get("bytes"),
        "sha256": value.get("sha256"),
    }


def expected_operator_contract(
    root: Path, sources: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    return {
        "authority": "operator transport only",
        "attempt_directory": str(root / OPERATOR_DIRECTORY),
        "stdout_log": str(root / STDOUT),
        "stderr_log": str(root / STDERR),
        "launch_receipt": str(root / RECEIPT),
        "launcher_source": _source_triplet(sources["attempt5_operator_launcher"]),
        "recorder_source": _source_triplet(sources["attempt5_operator_recorder"]),
        "growing_logs_excluded_from_source_evidence": True,
        "certification_effect": {
            **TRANSPORT_CERTIFICATION_EFFECT,
            "exit_120_reclassified_as_success": False,
        },
    }


def validate_attempt_directory(root: Path) -> None:
    path = Path(os.path.abspath(os.fspath(Path(root) / OPERATOR_DIRECTORY)))
    if not os.path.lexists(path) or _is_reparse(path) or not path.is_dir():
        raise OperatorReceiptError("operator attempt directory is not real")
    found = {entry.name for entry in path.iterdir()}
    if found != {"stdout.log", "stderr.log"}:
        raise OperatorReceiptError(
            f"operator attempt directory entries drifted: {sorted(found)}"
        )


def _same_path(value: Any, expected: Path) -> bool:
    if not isinstance(value, (str, os.PathLike)):
        return False
    return os.path.normcase(os.path.abspath(os.fspath(value))) == os.path.normcase(
        os.path.abspath(os.fspath(expected))
    )


def validate_transport_preflight(
    root: Path,
    value: Any,
    contract: Mapping[str, Any],
    stdout_snapshot: Mapping[str, Any],
    stderr_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "contract",
        "attempt_directory_entries",
        "fd_identities",
        "growing_log_bytes_hashed_as_sources",
    }:
        raise OperatorReceiptError("campaign operator preflight shape drifted")
    if value.get("contract") != contract:
        raise OperatorReceiptError("campaign operator preflight contract drifted")
    if value.get("attempt_directory_entries") != ["stderr.log", "stdout.log"]:
        raise OperatorReceiptError("campaign operator preflight entries drifted")
    if value.get("growing_log_bytes_hashed_as_sources") is not False:
        raise OperatorReceiptError("campaign operator logs were hashed as sources")
    identities = value.get("fd_identities")
    if not isinstance(identities, dict) or set(identities) != {"stdout", "stderr"}:
        raise OperatorReceiptError("campaign operator descriptor shape drifted")
    root = Path(os.path.abspath(os.fspath(root)))
    final = {"stdout": stdout_snapshot, "stderr": stderr_snapshot}
    expected_fds = {"stdout": 1, "stderr": 2}
    expected_paths = {"stdout": root / STDOUT, "stderr": root / STDERR}
    for label in ("stdout", "stderr"):
        identity = identities.get(label)
        if (
            not isinstance(identity, dict)
            or identity.get("fd") != expected_fds[label]
            or identity.get("link_count") != 1
            or identity.get("regular_file") is not True
            or not _same_path(identity.get("path"), expected_paths[label])
            or (identity.get("device"), identity.get("inode"))
            != (final[label].get("device"), final[label].get("inode"))
        ):
            raise OperatorReceiptError(
                f"campaign {label} descriptor/final-file identity drifted"
            )
    if (
        identities["stdout"].get("device"),
        identities["stdout"].get("inode"),
    ) == (
        identities["stderr"].get("device"),
        identities["stderr"].get("inode"),
    ):
        raise OperatorReceiptError("campaign operator descriptors are not distinct")
    return dict(value)


def validate_lifecycle(
    raw: bytes, file_snapshot: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise OperatorReceiptError("lifecycle encoding/framing drifted")
    records: list[dict[str, Any]] = []
    previous: str | None = None
    campaign_sequences: dict[str, int] = {}
    for ledger_sequence, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OperatorReceiptError("lifecycle is malformed") from exc
        if not isinstance(row, dict):
            raise OperatorReceiptError("lifecycle row is not an object")
        campaign_id = row.get("campaign_id")
        if not isinstance(campaign_id, str):
            raise OperatorReceiptError("lifecycle campaign id is malformed")
        campaign_sequences[campaign_id] = campaign_sequences.get(campaign_id, 0) + 1
        body = dict(row)
        digest = body.pop("event_sha256", None)
        if (
            row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_sequence") != campaign_sequences[campaign_id]
            or digest != sha256_bytes(canonical_bytes(body))
            or row.get("previous_event_sha256") != previous
        ):
            raise OperatorReceiptError("lifecycle sequence/hash chain drifted")
        previous = digest
        records.append(row)
    attempt = [row for row in records if row.get("campaign_id") == ATTEMPT_ID]
    started = [row for row in attempt if row.get("event") == "campaign_started"]
    terminal = [
        row
        for row in attempt
        if row.get("event") in {"campaign_completed", "campaign_failed"}
    ]
    if (
        len(started) != 1
        or len(terminal) != 1
        or records[-1:] != terminal
        or attempt.index(started[0]) >= attempt.index(terminal[0])
    ):
        raise OperatorReceiptError("attempt-005 lifecycle boundary is not terminal")
    return {
        "records": records,
        "started": started[0],
        "terminal": terminal[0],
        "snapshot": {
            **dict(file_snapshot or {"path": LIFECYCLE.as_posix()}),
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "row_count": len(records),
            "last_event_sha256": terminal[0]["event_sha256"],
            "hash_chain_verified": True,
            "terminal_is_last_row": True,
        },
    }


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OperatorReceiptError(f"{label} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise OperatorReceiptError(f"{label} is invalid: {exc}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise OperatorReceiptError(f"{label} is not UTC")
    return parsed


def validate_campaign_process(
    root: Path,
    value: Any,
    *,
    captured_pid: int,
    captured_started: datetime,
) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    if not isinstance(value, dict) or set(value) != {
        "authority",
        "pid",
        "process_create_time",
        "cwd",
        "invoked_executable",
        "process_image",
        "argv",
    }:
        raise OperatorReceiptError("campaign self-reported process shape drifted")
    create_time = value.get("process_create_time")
    if (
        value.get("authority") != "campaign self-observation via psutil"
        or value.get("pid") != captured_pid
        or isinstance(value.get("pid"), bool)
        or not isinstance(create_time, (int, float))
        or isinstance(create_time, bool)
        or not 0 < float(create_time) < float("inf")
        or abs(captured_started.timestamp() - float(create_time)) > 2.0
        or not _same_path(value.get("cwd"), root)
        or not _same_path(value.get("invoked_executable"), PYTHON)
        or not isinstance(value.get("process_image"), str)
        or not os.path.isabs(value["process_image"])
        or not isinstance(value.get("argv"), list)
        or not value["argv"]
        or not _same_path(value["argv"][0], Path(value["process_image"]))
        or value["argv"][1:] != expected_campaign_argv(root)[1:]
    ):
        raise OperatorReceiptError("campaign self-reported process identity drifted")
    return dict(value)


def _exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def validate_success_completion_boundary(
    lifecycle: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the exact attempt-005 11-pair success boundary."""
    terminal = lifecycle.get("terminal")
    snapshot_value = lifecycle.get("snapshot")
    if not isinstance(terminal, dict) or not isinstance(snapshot_value, dict):
        raise OperatorReceiptError("attempt-005 success lifecycle evidence is absent")
    details = terminal.get("details")
    if not isinstance(details, dict):
        raise OperatorReceiptError("attempt-005 success terminal details are absent")
    expected_counts = {
        "pair_count": 11,
        "carried_pair_count": 9,
        "executed_pair_count": 2,
        "new_execution_count": 4,
        "study_leg_count": 22,
    }
    if (
        not _exact_int(snapshot_value.get("row_count"), SUCCESS_LIFECYCLE_ROWS)
        or not _exact_int(
            terminal.get("ledger_sequence"), SUCCESS_TERMINAL_LEDGER_SEQUENCE
        )
        or not _exact_int(
            terminal.get("campaign_sequence"), SUCCESS_TERMINAL_CAMPAIGN_SEQUENCE
        )
        or any(
            not _exact_int(details.get(field), expected)
            for field, expected in expected_counts.items()
        )
    ):
        raise OperatorReceiptError("attempt-005 success count/sequence boundary drifted")
    pairs = details.get("pairs")
    audit = details.get("final_evidence_audit")
    if not isinstance(pairs, list) or len(pairs) != 11:
        raise OperatorReceiptError("attempt-005 success pair evidence count drifted")
    if not isinstance(audit, list) or len(audit) != 11:
        raise OperatorReceiptError("attempt-005 final evidence audit count drifted")
    if (
        [row.get("pair_index") if isinstance(row, dict) else None for row in audit]
        != list(range(1, 12))
        or [row.get("disposition") if isinstance(row, dict) else None for row in audit]
        != ["CARRIED_FORWARD"] * 9 + ["EXECUTED"] * 2
    ):
        raise OperatorReceiptError("attempt-005 final evidence audit boundary drifted")
    if details.get("final_state") != SUCCESS_CLEAN_STATE:
        raise OperatorReceiptError("attempt-005 success final state is not exactly clean")
    return {
        "lifecycle_row_count": SUCCESS_LIFECYCLE_ROWS,
        "terminal_ledger_sequence": SUCCESS_TERMINAL_LEDGER_SEQUENCE,
        "terminal_campaign_sequence": SUCCESS_TERMINAL_CAMPAIGN_SEQUENCE,
        **expected_counts,
        "final_evidence_audit_count": 11,
        "final_state": dict(SUCCESS_CLEAN_STATE),
        "verified": True,
    }


def build_receipt(
    *,
    root: Path,
    pid: int,
    started_at_utc: str,
    ended_at_utc: str,
    exit_code: int,
    cwd: Path,
    stdout_log: Path,
    stderr_log: Path,
) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or not -(2**31) <= exit_code < 2**31
        or not _same_path(cwd, root)
    ):
        raise OperatorReceiptError("operator process identity/exit input drifted")
    started_time = _parse_utc(started_at_utc, "started_at_utc")
    ended_time = _parse_utc(ended_at_utc, "ended_at_utc")
    if ended_time < started_time:
        raise OperatorReceiptError("operator process end precedes its start")
    if not _same_path(stdout_log, root / STDOUT) or not _same_path(
        stderr_log, root / STDERR
    ):
        raise OperatorReceiptError("operator stream path drifted")

    validate_attempt_directory(root)
    current_sources = source_snapshots(root)
    lifecycle_raw, lifecycle_file = snapshot(root, LIFECYCLE, "lifecycle")
    lifecycle = validate_lifecycle(lifecycle_raw, lifecycle_file)
    stdout_raw, stdout_snapshot = snapshot(root, STDOUT, "operator stdout")
    stderr_raw, stderr_snapshot = snapshot(root, STDERR, "operator stderr")
    if os.path.samefile(root / STDOUT, root / STDERR):
        raise OperatorReceiptError("operator streams resolve to one file")

    started_details = lifecycle["started"].get("details") or {}
    recorded_sources = started_details.get("sources") or {}
    if not isinstance(recorded_sources, dict):
        raise OperatorReceiptError("campaign source evidence is absent")
    for label in SOURCE_PATHS:
        if _source_triplet(recorded_sources.get(label) or {}) != _source_triplet(
            current_sources[label]
        ):
            raise OperatorReceiptError(f"campaign/operator source binding drifted: {label}")

    expected_contract = expected_operator_contract(root, current_sources)
    if started_details.get("operator_logs") != expected_contract:
        raise OperatorReceiptError("campaign operator-log contract drifted")
    transport_preflight = validate_transport_preflight(
        root,
        started_details.get("operator_transport_preflight"),
        expected_contract,
        stdout_snapshot,
        stderr_snapshot,
    )
    campaign_process = validate_campaign_process(
        root,
        started_details.get("campaign_process"),
        captured_pid=pid,
        captured_started=started_time,
    )

    terminal = lifecycle["terminal"]
    expected_terminal = "campaign_completed" if exit_code == 0 else "campaign_failed"
    expected_status = "COMPLETE" if exit_code == 0 else "FAILED"
    if (
        terminal.get("event") != expected_terminal
        or (terminal.get("details") or {}).get("status") != expected_status
    ):
        raise OperatorReceiptError("process exit and lifecycle terminal disagree")
    success_completion_boundary = (
        validate_success_completion_boundary(lifecycle) if exit_code == 0 else None
    )
    recovery_raw, _ = snapshot(
        root, RECOVERY4_RECEIPT, "corrected attempt-004 recovery receipt"
    )
    recovery_authority = validate_recovery_authority(recovery_raw)

    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-005-operator-launch",
        "attempt_id": ATTEMPT_ID,
        "authority": "operator transport only",
        "process": {
            "capture_authority": "PowerShell Start-Process -Wait -PassThru",
            "pid": pid,
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "exit_code": exit_code,
            "cwd": str(root),
            "executable": str(PYTHON),
            "argv": expected_campaign_argv(root),
            "campaign_self_report": campaign_process,
        },
        "sources": current_sources,
        "recovery_authority": {
            **recovery_authority,
            "receipt": _source_triplet(
                current_sources["attempt4_recovery_receipt"]
            ),
            "recorder": _source_triplet(
                current_sources["attempt4_recovery_recorder"]
            ),
        },
        "stdout": stdout_snapshot,
        "stderr": stderr_snapshot,
        "stdout_ends_with_newline": stdout_raw.endswith((b"\n", b"\r")),
        "stderr_ends_with_newline_or_empty": (
            not stderr_raw or stderr_raw.endswith((b"\n", b"\r"))
        ),
        "lifecycle": lifecycle["snapshot"],
        "operator_transport_preflight": transport_preflight,
        "terminal": {
            "event": terminal["event"],
            "status": expected_status,
            "event_sha256": terminal["event_sha256"],
        },
        "success_completion_boundary": success_completion_boundary,
        "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
        "safety": {
            "campaign_or_recipe_file_modified": False,
            "prompt_or_render_submitted_by_recorder": False,
            "server_gpu_listener_or_lock_queried": False,
            "network_used": False,
            "existing_transport_file_overwritten": False,
        },
    }


@contextmanager
def held_coordinator(root: Path) -> Iterator[Any]:
    """Load only the exact frozen recovery4 mutex implementation."""
    root = Path(os.path.abspath(os.fspath(root)))
    raw, _ = snapshot(root, RECOVERY4_RECORDER, "recovery4 coordinator source")
    if (
        len(raw) != RECOVERY4_RECORDER_BYTES
        or sha256_bytes(raw) != RECOVERY4_RECORDER_SHA256
    ):
        raise OperatorReceiptError("recovery4 coordinator implementation pin drifted")
    namespace: dict[str, Any] = {
        "__name__": "_h3_attempt5_frozen_coordinator",
        "__file__": str(root / RECOVERY4_RECORDER),
    }
    try:
        exec(compile(raw, str(root / RECOVERY4_RECORDER), "exec"), namespace)
        mutex_class = namespace["ExistingCoordinatorMutex"]
    except Exception as exc:
        raise OperatorReceiptError(
            f"cannot load exact recovery4 coordinator implementation: {exc}"
        ) from exc
    mutex = mutex_class(root)
    try:
        mutex.acquire()
    except Exception as exc:
        raise OperatorReceiptError(
            f"attempt-005 coordinator is held or unavailable: {exc}"
        ) from exc
    try:
        yield mutex
    finally:
        try:
            mutex.release()
        except Exception as exc:
            raise OperatorReceiptError(
                f"cannot release attempt-005 coordinator: {exc}"
            ) from exc


def exclusive_write(
    root: Path,
    payload: Mapping[str, Any],
    *,
    coordinator: Any,
    final_payload_builder: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    if getattr(coordinator, "acquired", False) is not True:
        raise OperatorReceiptError("launch receipt publication requires the held coordinator")
    final_payload = final_payload_builder()
    raw = receipt_bytes(payload)
    if receipt_bytes(final_payload) != raw:
        raise OperatorReceiptError("launch evidence changed before O_EXCL publication")
    validate_attempt_directory(root)
    destination = Path(os.path.abspath(os.fspath(Path(root) / RECEIPT)))
    if _is_reparse(destination.parent) or not destination.parent.is_dir():
        raise OperatorReceiptError("operator attempt directory is not real")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise OperatorReceiptError("attempt-005 launch receipt already exists") from exc
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OperatorReceiptError("short launch-receipt write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    published = destination.read_bytes()
    if published != raw:
        raise OperatorReceiptError("published launch receipt drifted")
    return {
        "path": RECEIPT.as_posix(),
        "bytes": len(published),
        "sha256": sha256_bytes(published),
    }


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


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    args = parse_args(argv)
    if not args.write:
        if not args.quiet:
            print(
                json.dumps(
                    {
                        "default_read_only": True,
                        "attempt_id": ATTEMPT_ID,
                        "receipt": str(Path(root) / RECEIPT),
                    },
                    indent=2,
                )
            )
        return 0
    try:
        required = (
            args.pid,
            args.started_at_utc,
            args.ended_at_utc,
            args.exit_code,
            args.cwd,
            args.stdout_log,
            args.stderr_log,
        )
        if any(value is None for value in required):
            raise OperatorReceiptError("--write requires complete operator inputs")

        def build() -> dict[str, Any]:
            return build_receipt(
                root=Path(root),
                pid=args.pid,
                started_at_utc=args.started_at_utc,
                ended_at_utc=args.ended_at_utc,
                exit_code=args.exit_code,
                cwd=Path(args.cwd),
                stdout_log=Path(args.stdout_log),
                stderr_log=Path(args.stderr_log),
            )

        with held_coordinator(Path(root)) as coordinator:
            payload = build()
            published = exclusive_write(
                Path(root),
                payload,
                coordinator=coordinator,
                final_payload_builder=build,
            )
        if not args.quiet:
            print(json.dumps({"status": "RECORDED", "receipt": published}, indent=2))
        return 0
    except Exception as exc:
        if not args.quiet:
            print(
                f"[ATTEMPT005 OPERATOR RECEIPT FAILED] {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
