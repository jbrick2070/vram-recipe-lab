#!/usr/bin/env python3
"""Record the attempt-005 post-run operator-capture gap without filling it in.

The campaign's durable lifecycle, receipts, artifacts, and Manager-offline logs
are independently rehashed.  The absent operator launch receipt is preserved as
an absence: this recorder never invents a process exit code, an exact process
end time, or a PowerShell capture.  Default invocation is read-only.  ``--write``
is the only publication path and uses the existing coordinator plus O_EXCL.

This module performs local file reads only.  It does not inspect processes,
listeners, servers, GPUs, locks other than the pre-existing coordinator byte,
or any network endpoint.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
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
ATTEMPT_ID = f"{BASE_ID}-attempt-005"
CAMPAIGN_ROOT = Path("results/h3_unconditioned_music_campaign")
LIFECYCLE = CAMPAIGN_ROOT / "lifecycle.jsonl"
OPERATOR_DIRECTORY = CAMPAIGN_ROOT / "operator_logs" / ATTEMPT_ID
STDOUT = OPERATOR_DIRECTORY / "stdout.log"
STDERR = OPERATOR_DIRECTORY / "stderr.log"
LAUNCH_RECEIPT = OPERATOR_DIRECTORY / "launch.json"
RECOVERY = CAMPAIGN_ROOT / "recoveries" / (
    f"{ATTEMPT_ID}-operator-gap-recovery.json"
)
GAP_RECORDER = Path("scratch/record_h3_music_attempt5_operator_gap_recovery.py")

RECOVERY4_RECORDER = Path("scratch/record_h3_music_attempt4_recovery.py")
RECOVERY4_RECEIPT = CAMPAIGN_ROOT / "recoveries" / (
    f"{BASE_ID}-attempt-004-timeout-recovery-correction-001.json"
)

LIFECYCLE_BYTES = 3_745_152
LIFECYCLE_SHA256 = (
    "6eb9d815b5fbb9dd09edb07ae68a8a49c052bb81e346daf7b616e1d8984697ab"
)
LIFECYCLE_LAST_EVENT_SHA256 = (
    "7813ad0be79a53b9e8265e7ef784b28beef9d222cc0007ee265c08abedd50c48"
)
STDOUT_BYTES = 1_898_814
STDOUT_SHA256 = (
    "141187131ce3455ccf568fd1697e8f713dbda208bd6218ad8a1aeb66056268c8"
)
STDERR_BYTES = 0
STDERR_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)

FINAL_SOURCE_PINS: dict[str, tuple[Path, int, str]] = {
    "campaign": (
        Path("scratch/run_h3_unconditioned_music_campaign.py"),
        201_061,
        "fbc2653c2171a4bfab0b54491a4c512055d1594003abdbb3c17db64a72148b54",
    ),
    "attempt5_operator_launcher": (
        Path("scratch/start_h3_music_attempt5.ps1"),
        5_381,
        "909c609677601467b43ac4a275ae7fe118be49b478c55a42658f82274c4c31f2",
    ),
    "attempt5_operator_recorder": (
        Path("scratch/record_h3_music_attempt5_operator_launch.py"),
        31_649,
        "5250cdb89f6834305179897a24063ebe8e377681199830e1a32e8fb482709aa5",
    ),
    "runner": (
        Path("run_recipe.py"),
        182_105,
        "0c7c636e36d1573852a5ad2c71cb06a826dea97eb34b16ab605ecafb530b83c9",
    ),
    "attempt4_recovery_recorder": (
        RECOVERY4_RECORDER,
        38_580,
        "d35ec3c0ddc3ae495c4bc56d5166a716f0da57cfbcb32ac6876373ab61528335",
    ),
    "attempt4_recovery_receipt": (
        RECOVERY4_RECEIPT,
        60_939,
        "fef1ef0401b5e4f13dc11b7405224e6b792a1a18c3b607fce806468f598f7dcd",
    ),
}

PAIR_NAMES = [
    "h3_unconditioned_music_scene_seed42_f124",
    "h3_unconditioned_music_motion_small_seed42_f124",
    "h3_unconditioned_music_motion_large_seed42_f124",
    "h3_unconditioned_music_scene_seed43_f124",
    "h3_unconditioned_music_scene_seed44_f124",
    "h3_unconditioned_music_scene_seed45_f124",
    "h3_unconditioned_music_scene_seed46_f124",
    "h3_unconditioned_music_score_seed42_f124",
    "h3_unconditioned_music_sfx_seed42_f124",
    "h3_unconditioned_music_scene_seed42_f192",
    "h3_unconditioned_music_scene_seed42_f277",
]
PAIR_SOURCE_CAMPAIGNS = [
    f"{BASE_ID}-attempt-002",
    f"{BASE_ID}-attempt-003",
    *([f"{BASE_ID}-attempt-004"] * 7),
    ATTEMPT_ID,
    ATTEMPT_ID,
]
EXPECTED_ATTEMPT_EVENTS = [
    "recovery_started",
    "campaign_started",
    "campaign_preflight_passed",
    *(["pair_carried_forward"] * 9),
    "pair_started",
    "cold_child_returned",
    "cold_verified",
    "warm_shutdown_child_returned",
    "pair_verified",
    "pair_started",
    "cold_child_returned",
    "cold_verified",
    "warm_shutdown_child_returned",
    "pair_verified",
    "campaign_completed",
]
SUCCESS_COUNTS = {
    "actual_execution_count": 4,
    "carried_pair_count": 9,
    "evidence_execution_count": 24,
    "executed_pair_count": 2,
    "failed_historical_execution_count": 1,
    "logical_cell_count": 14,
    "new_execution_count": 4,
    "orphan_historical_cold_count": 1,
    "pair_count": 11,
    "study_leg_count": 22,
    "valid_orphan_historical_cold_count": 1,
}
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
NO_CERTIFICATION_EFFECT = {
    "effect": "NONE",
    "campaign_status_changed": False,
    "campaign_completion_granted": False,
    "recipe_or_pair_certification_granted": False,
    "human_quality_judgment_granted": False,
    "promotion_or_study_pass_granted": False,
}


class OperatorGapError(RuntimeError):
    """The post-run evidence is absent, mutable, or semantically inconsistent."""


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


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _same_path(left: Any, right: Any) -> bool:
    if not isinstance(left, (str, os.PathLike)) or not isinstance(
        right, (str, os.PathLike)
    ):
        return False
    return os.path.normcase(os.path.abspath(os.fspath(left))) == os.path.normcase(
        os.path.abspath(os.fspath(right))
    )


def _require_under(path: Path, parent: Path, label: str) -> None:
    absolute = os.path.normcase(os.path.abspath(os.fspath(path)))
    boundary = os.path.normcase(os.path.abspath(os.fspath(parent)))
    try:
        common = os.path.commonpath([absolute, boundary])
    except ValueError as exc:
        raise OperatorGapError(f"{label} is outside its required root") from exc
    if common != boundary:
        raise OperatorGapError(f"{label} is outside its required root")


def snapshot_path(
    path: Path | str,
    label: str,
    *,
    require_single_link: bool = True,
) -> tuple[bytes, dict[str, Any]]:
    """Read a stable regular file through one descriptor.

    Campaign-owned evidence must be independent.  Lifecycle-recorded runtime
    sources may be package-manager hardlinks, so their recorded inode and bytes
    are verified without pretending their link count is one.
    """
    absolute = _absolute(path)
    if not os.path.lexists(absolute) or _is_reparse(absolute):
        raise OperatorGapError(f"missing or reparse {label}")
    before = absolute.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or int(before.st_nlink) < 1
        or (require_single_link and int(before.st_nlink) != 1)
    ):
        qualification = "independent " if require_single_link else ""
        raise OperatorGapError(f"{label} is not a {qualification}regular file")
    fd = os.open(absolute, os.O_RDONLY | getattr(os, "O_BINARY", 0))
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
    after = absolute.lstat()

    def identity(value: os.stat_result) -> tuple[int, ...]:
        return (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_nlink),
            int(value.st_size),
            int(value.st_mtime_ns),
        )

    if (
        identity(before) != identity(after)
        or identity(before) != identity(descriptor_before)
        or identity(before) != identity(descriptor_after)
        or int(before.st_mode) != int(after.st_mode)
        or int(descriptor_before.st_mode) != int(descriptor_after.st_mode)
        or not stat.S_ISREG(descriptor_before.st_mode)
        or not stat.S_ISREG(descriptor_after.st_mode)
        or _is_reparse(absolute)
        or len(raw) != int(after.st_size)
    ):
        raise OperatorGapError(f"{label} changed during descriptor read")
    return raw, {
        "path": str(absolute),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "device": int(after.st_dev),
        "inode": int(after.st_ino),
        "mode": int(after.st_mode),
        "link_count": int(after.st_nlink),
        "mtime_ns": int(after.st_mtime_ns),
        "regular_file": True,
        "reparse_point": False,
    }


class SnapshotCache:
    """Avoid re-reading duplicate immutable evidence within one candidate build."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[bytes, dict[str, Any]]] = {}

    def read(
        self,
        path: Path | str,
        label: str,
        *,
        require_single_link: bool = True,
    ) -> tuple[bytes, dict[str, Any]]:
        absolute = _absolute(path)
        key = f"{os.path.normcase(str(absolute))}|single={require_single_link}"
        if key not in self._items:
            self._items[key] = snapshot_path(
                absolute, label, require_single_link=require_single_link
            )
        raw, evidence = self._items[key]
        return raw, dict(evidence)


def validate_snapshot(
    current: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> dict[str, Any]:
    if (
        not _same_path(current.get("path"), expected.get("path"))
        or current.get("bytes") != expected.get("bytes")
        or current.get("sha256") != expected.get("sha256")
    ):
        raise OperatorGapError(f"{label} byte/hash/path pin drifted")
    for field in ("mtime_ns", "device", "inode", "link_count"):
        if field in expected and current.get(field) != expected.get(field):
            raise OperatorGapError(f"{label} descriptor pin drifted: {field}")
    return dict(current)


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise OperatorGapError(f"{label} has a UTF-8 BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorGapError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise OperatorGapError(f"{label} is not a JSON object")
    return value


def require_absent(root: Path, relative: Path, label: str) -> dict[str, Any]:
    path = _absolute(Path(root) / relative)
    if os.path.lexists(path):
        raise OperatorGapError(f"{label} must remain absent: {path}")
    return {"path": str(path), "absent": True}


def validate_attempt_directory(root: Path) -> dict[str, Any]:
    directory = _absolute(Path(root) / OPERATOR_DIRECTORY)
    if not os.path.lexists(directory) or _is_reparse(directory) or not directory.is_dir():
        raise OperatorGapError("attempt-005 operator directory is not a real directory")
    entries = sorted(entry.name for entry in directory.iterdir())
    if entries != ["stderr.log", "stdout.log"]:
        raise OperatorGapError(f"operator directory entries drifted: {entries}")
    launch = require_absent(root, LAUNCH_RECEIPT, "operator launch receipt")
    if _same_path(Path(root) / RECOVERY.parent, directory):
        raise OperatorGapError("gap recovery destination must never be the operator directory")
    return {
        "path": str(directory),
        "entries": entries,
        "launch_receipt": launch,
        "launch_receipt_absent": True,
    }


def validate_lifecycle(
    raw: bytes, file_snapshot: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if len(raw) != LIFECYCLE_BYTES or sha256_bytes(raw) != LIFECYCLE_SHA256:
        raise OperatorGapError("finalized lifecycle full-file pin drifted")
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise OperatorGapError("lifecycle encoding/framing drifted")
    records: list[dict[str, Any]] = []
    prior: str | None = None
    campaign_counts: dict[str, int] = {}
    for ledger_sequence, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OperatorGapError("lifecycle is malformed") from exc
        if not isinstance(row, dict) or not isinstance(row.get("campaign_id"), str):
            raise OperatorGapError("lifecycle row shape drifted")
        campaign_id = row["campaign_id"]
        campaign_counts[campaign_id] = campaign_counts.get(campaign_id, 0) + 1
        body = dict(row)
        digest = body.pop("event_sha256", None)
        if (
            row.get("schema_version") != 1
            or row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_sequence") != campaign_counts[campaign_id]
            or digest != sha256_bytes(canonical_bytes(body))
            or row.get("previous_event_sha256") != prior
        ):
            raise OperatorGapError("lifecycle sequence/hash chain drifted")
        prior = digest
        records.append(row)
    attempt = [row for row in records if row["campaign_id"] == ATTEMPT_ID]
    if (
        len(records) != 88
        or len(attempt) != 23
        or [row.get("event") for row in attempt] != EXPECTED_ATTEMPT_EVENTS
        or [row.get("campaign_sequence") for row in attempt] != list(range(1, 24))
        or records[-1:] != attempt[-1:]
        or attempt[-1].get("ledger_sequence") != 88
        or attempt[-1].get("campaign_sequence") != 23
        or attempt[-1].get("event") != "campaign_completed"
        or attempt[-1].get("event_sha256") != LIFECYCLE_LAST_EVENT_SHA256
    ):
        raise OperatorGapError("attempt-005 exact terminal lifecycle boundary drifted")
    started = [row for row in attempt if row.get("event") == "campaign_started"]
    if len(started) != 1:
        raise OperatorGapError("attempt-005 campaign-start evidence drifted")
    return {
        "records": records,
        "attempt": attempt,
        "started": started[0],
        "terminal": attempt[-1],
        "snapshot": {
            **dict(file_snapshot or {"path": LIFECYCLE.as_posix()}),
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
            "row_count": 88,
            "attempt_row_count": 23,
            "terminal_ledger_sequence": 88,
            "terminal_campaign_sequence": 23,
            "last_event_sha256": LIFECYCLE_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
            "terminal_is_last_row": True,
        },
    }


def _iter_snapshot_specs(value: Any, context: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        if (
            {"path", "bytes", "sha256"}.issubset(value)
            and isinstance(value.get("path"), str)
            and isinstance(value.get("bytes"), int)
            and not isinstance(value.get("bytes"), bool)
            and isinstance(value.get("sha256"), str)
        ):
            yield context, value
        for key, child in value.items():
            child_context = f"{context}.{key}" if context else str(key)
            yield from _iter_snapshot_specs(child, child_context)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_snapshot_specs(child, f"{context}[{index}]")


def validate_finalized_sources(
    root: Path,
    recorded: Any,
    cache: SnapshotCache,
) -> dict[str, Any]:
    if not isinstance(recorded, dict):
        raise OperatorGapError("campaign-start source evidence is absent")
    finalized: dict[str, dict[str, Any]] = {}
    for label, (relative, expected_bytes, expected_sha) in FINAL_SOURCE_PINS.items():
        expected = {
            "path": str(_absolute(Path(root) / relative)),
            "bytes": expected_bytes,
            "sha256": expected_sha,
        }
        recorded_value = recorded.get(label)
        if not isinstance(recorded_value, dict):
            raise OperatorGapError(f"recorded finalized source is absent: {label}")
        if any(recorded_value.get(key) != expected[key] for key in ("bytes", "sha256")) or not _same_path(
            recorded_value.get("path"), expected["path"]
        ):
            raise OperatorGapError(f"recorded finalized source pin drifted: {label}")
        _raw, current = cache.read(
            expected["path"],
            f"finalized source {label}",
            require_single_link=False,
        )
        finalized[label] = validate_snapshot(current, expected, label)

    references = list(_iter_snapshot_specs(recorded))
    if len(references) != 33:
        raise OperatorGapError("lifecycle source snapshot-reference count drifted")
    manifest_by_path: dict[str, dict[str, Any]] = {}
    for context, expected in references:
        _raw, current = cache.read(
            expected["path"],
            f"source snapshot {context}",
            require_single_link=False,
        )
        validate_snapshot(current, expected, f"source snapshot {context}")
        key = os.path.normcase(os.path.abspath(expected["path"]))
        prior = manifest_by_path.get(key)
        concise = {
            "path": current["path"],
            "bytes": current["bytes"],
            "sha256": current["sha256"],
        }
        if prior is not None and prior != concise:
            raise OperatorGapError(f"duplicate source snapshot disagrees: {context}")
        manifest_by_path[key] = concise
    if len(manifest_by_path) != 32:
        raise OperatorGapError("lifecycle unique source-file count drifted")
    return {
        "literal_finalized_pins": finalized,
        "lifecycle_snapshot_reference_count": 33,
        "unique_source_file_count": 32,
        "all_recorded_file_sources_rehashed": True,
        "manifest": [manifest_by_path[key] for key in sorted(manifest_by_path)],
    }


def _triplet(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": value.get("path"),
        "bytes": value.get("bytes"),
        "sha256": value.get("sha256"),
    }


def validate_operator_contract(
    root: Path,
    lifecycle: Mapping[str, Any],
    sources: Mapping[str, Any],
    stdout_snapshot: Mapping[str, Any],
    stderr_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    started_details = (lifecycle["started"].get("details") or {})
    terminal_details = (lifecycle["terminal"].get("details") or {})
    contract = started_details.get("operator_logs")
    if not isinstance(contract, dict) or terminal_details.get("operator_logs") != contract:
        raise OperatorGapError("started/terminal operator contract drifted")
    expected_effect = {
        "campaign_status_changed": False,
        "exit_120_reclassified_as_success": False,
        "human_quality_judgment_granted": False,
        "recipe_or_pair_certification_granted": False,
    }
    launcher = FINAL_SOURCE_PINS["attempt5_operator_launcher"]
    recorder = FINAL_SOURCE_PINS["attempt5_operator_recorder"]
    expected = {
        "attempt_directory": str(_absolute(Path(root) / OPERATOR_DIRECTORY)),
        "authority": "operator transport only",
        "certification_effect": expected_effect,
        "growing_logs_excluded_from_source_evidence": True,
        "launch_receipt": str(_absolute(Path(root) / LAUNCH_RECEIPT)),
        "launcher_source": {
            "path": str(_absolute(Path(root) / launcher[0])),
            "bytes": launcher[1],
            "sha256": launcher[2],
        },
        "recorder_source": {
            "path": str(_absolute(Path(root) / recorder[0])),
            "bytes": recorder[1],
            "sha256": recorder[2],
        },
        "stderr_log": str(_absolute(Path(root) / STDERR)),
        "stdout_log": str(_absolute(Path(root) / STDOUT)),
    }
    if contract != expected:
        raise OperatorGapError("exact operator transport contract drifted")
    if _triplet(sources["literal_finalized_pins"]["attempt5_operator_launcher"]) != expected["launcher_source"]:
        raise OperatorGapError("operator launcher/source binding drifted")
    if _triplet(sources["literal_finalized_pins"]["attempt5_operator_recorder"]) != expected["recorder_source"]:
        raise OperatorGapError("operator recorder/source binding drifted")

    preflight = started_details.get("operator_transport_preflight")
    if not isinstance(preflight, dict) or set(preflight) != {
        "attempt_directory_entries",
        "contract",
        "fd_identities",
        "growing_log_bytes_hashed_as_sources",
    }:
        raise OperatorGapError("campaign operator preflight shape drifted")
    if (
        preflight.get("attempt_directory_entries") != ["stderr.log", "stdout.log"]
        or preflight.get("contract") != expected
        or preflight.get("growing_log_bytes_hashed_as_sources") is not False
    ):
        raise OperatorGapError("campaign operator preflight contract drifted")
    identities = preflight.get("fd_identities")
    if not isinstance(identities, dict) or set(identities) != {"stdout", "stderr"}:
        raise OperatorGapError("campaign operator descriptor evidence drifted")
    expected_streams = {
        "stdout": (1, stdout_snapshot, Path(root) / STDOUT),
        "stderr": (2, stderr_snapshot, Path(root) / STDERR),
    }
    for label, (fd_number, final, path) in expected_streams.items():
        identity = identities.get(label)
        if (
            not isinstance(identity, dict)
            or identity.get("fd") != fd_number
            or identity.get("link_count") != 1
            or identity.get("regular_file") is not True
            or not _same_path(identity.get("path"), path)
            or (identity.get("device"), identity.get("inode"))
            != (final.get("device"), final.get("inode"))
        ):
            raise OperatorGapError(f"campaign {label} descriptor binding drifted")
    return {
        "contract": expected,
        "campaign_fd_identities_match_final_streams": True,
        "campaign_growing_streams_excluded_from_source_hashes": True,
        "independent_process_capture_present": False,
    }


def _exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def validate_success_terminal(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    terminal = lifecycle["terminal"]
    details = terminal.get("details")
    if not isinstance(details, dict):
        raise OperatorGapError("attempt-005 terminal details are absent")
    if (
        terminal.get("event") != "campaign_completed"
        or not _exact_int(terminal.get("ledger_sequence"), 88)
        or not _exact_int(terminal.get("campaign_sequence"), 23)
        or details.get("status") != "COMPLETE"
        or details.get("quality_judgment") != "PENDING_HUMAN"
        or any(
            not _exact_int(details.get(field), expected)
            for field, expected in SUCCESS_COUNTS.items()
        )
        or details.get("final_state") != SUCCESS_CLEAN_STATE
    ):
        raise OperatorGapError("attempt-005 exact COMPLETE boundary drifted")
    pairs = details.get("pairs")
    audit = details.get("final_evidence_audit")
    if not isinstance(pairs, list) or len(pairs) != 11:
        raise OperatorGapError("terminal pair evidence count drifted")
    if not isinstance(audit, list) or len(audit) != 11:
        raise OperatorGapError("terminal final-evidence audit count drifted")
    if [row.get("pair_index") if isinstance(row, dict) else None for row in audit] != list(range(1, 12)):
        raise OperatorGapError("terminal final-evidence audit order drifted")
    if [row.get("disposition") if isinstance(row, dict) else None for row in audit] != ["CARRIED_FORWARD"] * 9 + ["EXECUTED"] * 2:
        raise OperatorGapError("terminal final-evidence dispositions drifted")
    return {
        "event": "campaign_completed",
        "status": "COMPLETE",
        "ledger_sequence": 88,
        "campaign_sequence": 23,
        "event_sha256": terminal["event_sha256"],
        "success_counts": dict(SUCCESS_COUNTS),
        "final_state": dict(SUCCESS_CLEAN_STATE),
        "final_evidence_audit_count": 11,
        "quality_judgment": "PENDING_HUMAN",
        "verified": True,
    }


def _validate_manager_offline(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise OperatorGapError(f"{label} Manager evidence is absent")
    mode = value.get("authoritative_server_reported_mode")
    if (
        value.get("kind") != "h3-manager-offline-probe-log-scan"
        or value.get("status") != "pass"
        or value.get("unique_attempt_log_required") is not True
        or value.get("atomically_precreated_empty_required") is not True
        or value.get("preboot_record_starts_at_byte_zero") is not True
        or value.get("start_offset") != 0
        or value.get("errors") != []
        or value.get("network_markers") != []
        or value.get("mutation_markers") != []
        or not isinstance(mode, dict)
        or mode.get("required_mode") != "offline"
        or mode.get("resolved_mode") != "offline"
        or mode.get("observed_values") != ["offline"]
        or mode.get("announcement_count") != 1
        or mode.get("mode_precedes_first_execution") is not True
        or mode.get("mode_precedes_startup_completion") is not True
    ):
        raise OperatorGapError(f"{label} Manager-offline proof drifted")
    return value


def verify_terminal_files(
    root: Path,
    lifecycle: Mapping[str, Any],
    cache: SnapshotCache,
) -> dict[str, Any]:
    details = lifecycle["terminal"]["details"]
    pairs = details["pairs"]
    audit = details["final_evidence_audit"]
    receipts: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    manager_logs: list[dict[str, Any]] = []
    receipt_paths: set[str] = set()
    artifact_paths: set[str] = set()
    manager_paths: set[str] = set()
    expected_dispositions = ["CARRIED_FORWARD"] * 9 + ["EXECUTED"] * 2

    for pair_index, (entry, audit_row) in enumerate(zip(pairs, audit), start=1):
        if not isinstance(entry, dict) or not isinstance(audit_row, dict):
            raise OperatorGapError(f"pair {pair_index} terminal evidence shape drifted")
        recipe = PAIR_NAMES[pair_index - 1]
        source_campaign = PAIR_SOURCE_CAMPAIGNS[pair_index - 1]
        if (
            entry.get("pair_index") != pair_index
            or entry.get("recipe") != recipe
            or audit_row.get("pair_index") != pair_index
            or audit_row.get("recipe") != recipe
            or audit_row.get("source_campaign_id") != source_campaign
            or audit_row.get("disposition") != expected_dispositions[pair_index - 1]
        ):
            raise OperatorGapError(f"pair {pair_index} final audit identity drifted")
        if pair_index <= 9:
            if (
                entry.get("source_campaign_id") != source_campaign
                or entry.get("status") != "CARRIED_FORWARD"
                or entry.get("human_judgment") != "PENDING_HUMAN"
            ):
                raise OperatorGapError(
                    f"pair {pair_index} carried-forward identity drifted"
                )
        elif any(
            field in entry for field in ("source_campaign_id", "status", "human_judgment")
        ):
            raise OperatorGapError(
                f"pair {pair_index} executed-pair terminal shape drifted"
            )
        pair = entry.get("pair")
        if not isinstance(pair, dict):
            raise OperatorGapError(f"pair {pair_index} machine evidence is absent")
        for leg in ("cold", "warm"):
            value = pair.get(leg)
            if not isinstance(value, dict):
                raise OperatorGapError(f"pair {pair_index} {leg} evidence is absent")
            receipt_path = value.get("receipt")
            receipt_sha = value.get("receipt_sha256")
            if not isinstance(receipt_path, str) or not isinstance(receipt_sha, str):
                raise OperatorGapError(f"pair {pair_index} {leg} receipt evidence drifted")
            receipt_absolute = _absolute(receipt_path)
            _require_under(receipt_absolute, Path(root) / "results", "pair receipt")
            receipt_raw, receipt_snapshot = cache.read(
                receipt_absolute, f"pair {pair_index} {leg} receipt"
            )
            if receipt_snapshot["sha256"] != receipt_sha:
                raise OperatorGapError(f"pair {pair_index} {leg} receipt hash drifted")
            _parse_json(receipt_raw, f"pair {pair_index} {leg} receipt")
            receipt_key = os.path.normcase(str(receipt_absolute))
            if receipt_key in receipt_paths:
                raise OperatorGapError("cold/warm receipt paths are not unique")
            receipt_paths.add(receipt_key)
            receipts.append(
                {
                    "pair_index": pair_index,
                    "leg": leg,
                    "path": receipt_snapshot["path"],
                    "bytes": receipt_snapshot["bytes"],
                    "sha256": receipt_snapshot["sha256"],
                }
            )

            expected_artifact = value.get("artifact")
            if not isinstance(expected_artifact, dict):
                raise OperatorGapError(f"pair {pair_index} {leg} artifact evidence drifted")
            artifact_absolute = _absolute(expected_artifact.get("path", ""))
            _require_under(artifact_absolute, Path(root) / "outputs", "pair artifact")
            _artifact_raw, artifact_snapshot = cache.read(
                artifact_absolute, f"pair {pair_index} {leg} artifact"
            )
            validate_snapshot(
                artifact_snapshot,
                expected_artifact,
                f"pair {pair_index} {leg} artifact",
            )
            if not _same_path(value.get("artifact_path"), artifact_absolute):
                raise OperatorGapError(f"pair {pair_index} {leg} artifact path drifted")
            artifact_key = os.path.normcase(str(artifact_absolute))
            if artifact_key in artifact_paths:
                raise OperatorGapError("cold/warm artifact paths are not unique")
            artifact_paths.add(artifact_key)
            artifacts.append(
                {
                    "pair_index": pair_index,
                    "leg": leg,
                    "path": artifact_snapshot["path"],
                    "bytes": artifact_snapshot["bytes"],
                    "sha256": artifact_snapshot["sha256"],
                }
            )

            expected_receipt_hash = audit_row[f"{leg}_receipt_sha256"]
            expected_artifact_hash = audit_row[f"{leg}_artifact_sha256"]
            if receipt_sha != expected_receipt_hash or artifact_snapshot["sha256"] != expected_artifact_hash:
                raise OperatorGapError(f"pair {pair_index} {leg} final audit hashes drifted")

        manager = _validate_manager_offline(
            pair.get("final_manager_log"), f"pair {pair_index}"
        )
        expected_log = manager.get("log")
        if not isinstance(expected_log, dict):
            raise OperatorGapError(f"pair {pair_index} Manager log snapshot is absent")
        manager_absolute = _absolute(expected_log.get("path", ""))
        _require_under(manager_absolute, CAMPAIGN_ROOT_ABSOLUTE(root) / "server_logs", "Manager log")
        _manager_raw, manager_snapshot = cache.read(
            manager_absolute, f"pair {pair_index} final Manager log"
        )
        validate_snapshot(
            manager_snapshot, expected_log, f"pair {pair_index} final Manager log"
        )
        if (
            manager.get("prefix_bytes") != manager_snapshot["bytes"]
            or manager.get("prefix_sha256") != manager_snapshot["sha256"]
            or not _same_path(audit_row.get("manager_log"), manager_absolute)
            or audit_row.get("manager_log_sha256") != manager_snapshot["sha256"]
        ):
            raise OperatorGapError(f"pair {pair_index} Manager final audit drifted")
        manager_key = os.path.normcase(str(manager_absolute))
        if manager_key in manager_paths:
            raise OperatorGapError("each pair must retain one distinct Manager log")
        manager_paths.add(manager_key)
        manager_logs.append(
            {
                "pair_index": pair_index,
                "path": manager_snapshot["path"],
                "bytes": manager_snapshot["bytes"],
                "sha256": manager_snapshot["sha256"],
                "server_reported_network_mode": "offline",
                "status": "pass",
            }
        )

    if len(receipts) != 22 or len(artifacts) != 22 or len(manager_logs) != 11:
        raise OperatorGapError("terminal evidence rehash cardinality drifted")
    recovery_expected = details.get("recovery_receipt")
    if not isinstance(recovery_expected, dict):
        raise OperatorGapError("terminal corrected recovery receipt is absent")
    recovery_raw, recovery_snapshot = cache.read(
        recovery_expected.get("path", ""), "terminal corrected recovery receipt"
    )
    validate_snapshot(
        recovery_snapshot,
        recovery_expected,
        "terminal corrected recovery receipt",
    )
    recovery_value = _parse_json(recovery_raw, "terminal corrected recovery receipt")
    if (
        recovery_value.get("receipt_kind")
        != "h3-unconditioned-music-attempt-004-timeout-recovery-correction"
        or recovery_value.get("resume_campaign_id") != ATTEMPT_ID
    ):
        raise OperatorGapError("terminal corrected recovery authority drifted")
    return {
        "receipt_count": 22,
        "artifact_count": 22,
        "manager_log_count": 11,
        "all_terminal_receipts_rehashed": True,
        "all_terminal_artifacts_rehashed": True,
        "all_final_manager_logs_rehashed": True,
        "all_final_manager_logs_server_reported_offline": True,
        "receipts": receipts,
        "artifacts": artifacts,
        "manager_logs": manager_logs,
        "recovery_receipt": {
            "path": recovery_snapshot["path"],
            "bytes": recovery_snapshot["bytes"],
            "sha256": recovery_snapshot["sha256"],
        },
    }


def CAMPAIGN_ROOT_ABSOLUTE(root: Path) -> Path:
    """Keep campaign-root normalization explicit for evidence boundary checks."""
    return _absolute(Path(root) / CAMPAIGN_ROOT)


def build_receipt(root: Path = ROOT) -> dict[str, Any]:
    root = _absolute(root)
    if not _same_path(root, ROOT):
        raise OperatorGapError("full post-run verification is fixed to the real lab root")
    if _same_path(Path(root) / RECOVERY.parent, Path(root) / OPERATOR_DIRECTORY):
        raise OperatorGapError("recovery destination must not be the operator directory")
    require_absent(root, RECOVERY, "operator-gap recovery receipt")
    directory = validate_attempt_directory(root)
    cache = SnapshotCache()

    lifecycle_raw, lifecycle_snapshot = cache.read(
        Path(root) / LIFECYCLE, "finalized lifecycle"
    )
    lifecycle = validate_lifecycle(lifecycle_raw, lifecycle_snapshot)
    started_details = lifecycle["started"].get("details") or {}
    sources = validate_finalized_sources(root, started_details.get("sources"), cache)

    stdout_raw, stdout_snapshot = cache.read(Path(root) / STDOUT, "operator stdout")
    stderr_raw, stderr_snapshot = cache.read(Path(root) / STDERR, "operator stderr")
    if (
        stdout_snapshot["bytes"] != STDOUT_BYTES
        or stdout_snapshot["sha256"] != STDOUT_SHA256
        or stderr_snapshot["bytes"] != STDERR_BYTES
        or stderr_snapshot["sha256"] != STDERR_SHA256
    ):
        raise OperatorGapError("final operator stream byte/hash pin drifted")
    if os.path.samefile(Path(root) / STDOUT, Path(root) / STDERR):
        raise OperatorGapError("operator streams resolve to the same file")
    if not stdout_raw.endswith((b"\n", b"\r")) or stderr_raw:
        raise OperatorGapError("final operator stream framing drifted")

    operator_contract = validate_operator_contract(
        root, lifecycle, sources, stdout_snapshot, stderr_snapshot
    )
    terminal = validate_success_terminal(lifecycle)
    terminal_files = verify_terminal_files(root, lifecycle, cache)
    gap_recorder_raw, gap_recorder_snapshot = cache.read(
        Path(root) / GAP_RECORDER, "operator-gap recorder source"
    )
    if gap_recorder_raw.startswith(b"\xef\xbb\xbf"):
        raise OperatorGapError("operator-gap recorder source has a UTF-8 BOM")

    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-005-operator-gap-recovery",
        "attempt_id": ATTEMPT_ID,
        "status": "POST_RUN_OPERATOR_CAPTURE_GAP",
        "launch_receipt_absent": True,
        "exact_process_end_time_unknown": True,
        "exit_code_not_independently_recoverable": True,
        "must_not_substitute_for_launch_receipt": True,
        "no_certification_effect": True,
        "recording_time": {
            "included": False,
            "reason": "deterministic immutable-evidence receipt",
        },
        "operator_capture_gap": {
            "independent_operator_capture_present": False,
            "powershell_start_process_capture_claimed": False,
            "captured_pid": None,
            "captured_process_start_time": None,
            "captured_process_end_time": None,
            "captured_exit_code": None,
            "recovered_exit_code": None,
            "campaign_lifecycle_self_report_is_not_independent_operator_capture": True,
        },
        "operator_directory": directory,
        "operator_streams": {
            "stdout": stdout_snapshot,
            "stderr": stderr_snapshot,
            "stdout_ends_with_newline": True,
            "stderr_empty": True,
            "snapshotted_through_stable_regular_file_descriptors": True,
            "rechecked_by_double_build_before_publication": True,
        },
        "lifecycle": lifecycle["snapshot"],
        "campaign_terminal_evidence": terminal,
        "operator_contract": operator_contract,
        "finalized_sources": sources,
        "terminal_file_audit": terminal_files,
        "gap_recorder_source": gap_recorder_snapshot,
        "certification_effect": dict(NO_CERTIFICATION_EFFECT),
        "safety": {
            "campaign_recipe_result_or_document_modified": False,
            "render_or_prompt_submitted": False,
            "process_server_gpu_listener_or_port_queried": False,
            "network_used": False,
            "operator_directory_modified": False,
            "existing_evidence_overwritten": False,
            "start_process_capture_claimed": False,
            "exit_code_or_exact_end_time_invented": False,
        },
    }


@contextmanager
def held_coordinator(root: Path) -> Iterator[Any]:
    """Load only the exact frozen recovery4 coordinator implementation."""
    root = _absolute(root)
    expected = FINAL_SOURCE_PINS["attempt4_recovery_recorder"]
    raw, snapshot = snapshot_path(Path(root) / expected[0], "recovery4 coordinator")
    if snapshot["bytes"] != expected[1] or snapshot["sha256"] != expected[2]:
        raise OperatorGapError("recovery4 coordinator source pin drifted")
    namespace: dict[str, Any] = {
        "__name__": "_h3_attempt5_gap_frozen_coordinator",
        "__file__": str(Path(root) / expected[0]),
    }
    try:
        exec(compile(raw, str(Path(root) / expected[0]), "exec"), namespace)
        mutex_class = namespace["ExistingCoordinatorMutex"]
    except Exception as exc:
        raise OperatorGapError(f"cannot load frozen coordinator: {exc}") from exc
    mutex = mutex_class(root)
    try:
        mutex.acquire()
    except Exception as exc:
        raise OperatorGapError(f"coordinator is held or unavailable: {exc}") from exc
    try:
        yield mutex
    finally:
        try:
            mutex.release()
        except Exception as exc:
            raise OperatorGapError(f"cannot release coordinator: {exc}") from exc


def exclusive_write(
    root: Path,
    payload: Mapping[str, Any],
    *,
    coordinator: Any,
    final_payload_builder: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Double-build under the held coordinator, then publish only with O_EXCL."""
    root = _absolute(root)
    if getattr(coordinator, "acquired", False) is not True:
        raise OperatorGapError("gap-recovery publication requires the held coordinator")
    raw = receipt_bytes(payload)
    final_raw = receipt_bytes(final_payload_builder())
    if final_raw != raw:
        raise OperatorGapError("post-run evidence changed before O_EXCL publication")
    destination = _absolute(Path(root) / RECOVERY)
    if _same_path(destination.parent, Path(root) / OPERATOR_DIRECTORY):
        raise OperatorGapError("gap recovery must never be written in operator logs")
    if not destination.parent.is_dir() or _is_reparse(destination.parent):
        raise OperatorGapError("recovery directory is not a real directory")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise OperatorGapError("operator-gap recovery receipt already exists") from exc
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OperatorGapError("short O_EXCL operator-gap receipt write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    published = destination.read_bytes()
    if published != raw:
        raise OperatorGapError("published operator-gap receipt differs from candidate")
    return {
        "path": RECOVERY.as_posix(),
        "bytes": len(published),
        "sha256": sha256_bytes(published),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"publish fixed O_EXCL receipt {RECOVERY.as_posix()}",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    args = parse_args(argv)
    try:
        if not args.write:
            payload = build_receipt(root)
            if not args.quiet:
                sys.stdout.write(receipt_bytes(payload).decode("utf-8"))
            return 0
        with held_coordinator(Path(root)) as coordinator:
            payload = build_receipt(root)
            published = exclusive_write(
                Path(root),
                payload,
                coordinator=coordinator,
                final_payload_builder=lambda: build_receipt(root),
            )
        if not args.quiet:
            print(json.dumps({"status": "CREATED", "receipt": published}, indent=2))
        return 0
    except Exception as exc:
        if not args.quiet:
            print(
                f"[ATTEMPT005 OPERATOR GAP RECOVERY FAILED] {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
