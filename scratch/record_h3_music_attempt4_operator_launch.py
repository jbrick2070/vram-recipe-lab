#!/usr/bin/env python3
"""Record the completed attempt-004 operator transport with O_EXCL.

The campaign owns the lifecycle.  This post-exit recorder only binds the
launcher-observed process exit to the final stdout/stderr bytes and terminal
lifecycle row.  Default invocation is read-only; ``--write`` is the sole write
path.  It never renders, probes a server/GPU, or changes campaign status.
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
from typing import Any, Callable, Mapping, Sequence

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_ID = "h3music-20260810T023023Z-97ca44b2-attempt-004"
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")
CAMPAIGN_ROOT = Path("results/h3_unconditioned_music_campaign")
OPERATOR_DIRECTORY = CAMPAIGN_ROOT / "operator_logs" / ATTEMPT_ID
STDOUT = OPERATOR_DIRECTORY / "stdout.log"
STDERR = OPERATOR_DIRECTORY / "stderr.log"
RECEIPT = OPERATOR_DIRECTORY / "launch.json"
LIFECYCLE = CAMPAIGN_ROOT / "lifecycle.jsonl"
CAMPAIGN = Path("scratch/run_h3_unconditioned_music_campaign.py")
LAUNCHER = Path("scratch/start_h3_music_attempt4.ps1")
RECORDER = Path("scratch/record_h3_music_attempt4_operator_launch.py")
COORDINATOR_IMPLEMENTATION = Path("scratch/record_h3_music_attempt3_recovery.py")
COORDINATOR_IMPLEMENTATION_BYTES = 39_301
COORDINATOR_IMPLEMENTATION_SHA256 = (
    "6e22075eeb39e1cffdf2d311fc3950bafe2a227849bec376fb6c83e5eeb0ff0b"
)
TRANSPORT_CERTIFICATION_EFFECT = {
    "campaign_status_changed": False,
    "recipe_or_pair_certification_granted": False,
    "human_quality_judgment_granted": False,
}


class OperatorReceiptError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def receipt_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def snapshot(root: Path, relative: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    path = Path(os.path.abspath(os.fspath(root / relative)))
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
    before_identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_mode),
        int(before.st_nlink),
        int(before.st_size),
        int(before.st_mtime_ns),
    )
    after_identity = (
        int(after.st_dev),
        int(after.st_ino),
        int(after.st_mode),
        int(after.st_nlink),
        int(after.st_size),
        int(after.st_mtime_ns),
    )
    descriptor_before_identity = (
        int(descriptor_before.st_dev),
        int(descriptor_before.st_ino),
        int(descriptor_before.st_mode),
        int(descriptor_before.st_nlink),
        int(descriptor_before.st_size),
        int(descriptor_before.st_mtime_ns),
    )
    descriptor_after_identity = (
        int(descriptor_after.st_dev),
        int(descriptor_after.st_ino),
        int(descriptor_after.st_mode),
        int(descriptor_after.st_nlink),
        int(descriptor_after.st_size),
        int(descriptor_after.st_mtime_ns),
    )
    if (
        before_identity != after_identity
        or before_identity != descriptor_before_identity
        or before_identity != descriptor_after_identity
        or _is_reparse(path)
        or len(raw) != after.st_size
    ):
        raise OperatorReceiptError(f"{label} changed during read")
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


def source_snapshots(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for label, relative in (
        ("campaign", CAMPAIGN),
        ("launcher", LAUNCHER),
        ("recorder", RECORDER),
        ("coordinator_implementation", COORDINATOR_IMPLEMENTATION),
    ):
        raw, result[label] = snapshot(root, relative, label)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise OperatorReceiptError(f"{label} source has a UTF-8 BOM")
        if label == "coordinator_implementation" and (
            len(raw) != COORDINATOR_IMPLEMENTATION_BYTES
            or sha256_bytes(raw) != COORDINATOR_IMPLEMENTATION_SHA256
        ):
            raise OperatorReceiptError("coordinator implementation pin drifted")
    return result


def expected_campaign_argv(root: Path) -> list[str]:
    root = Path(os.path.abspath(os.fspath(root)))
    return [
        str(PYTHON),
        "-B",
        "-u",
        str(root / CAMPAIGN),
        "--run",
        "--resume-attempt-003",
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
        "launcher_source": _source_triplet(sources["launcher"]),
        "recorder_source": _source_triplet(sources["recorder"]),
        "growing_logs_excluded_from_source_evidence": True,
        "certification_effect": {
            **TRANSPORT_CERTIFICATION_EFFECT,
            "exit_120_reclassified_as_success": False,
        },
    }


def validate_attempt_directory(root: Path) -> None:
    path = Path(os.path.abspath(os.fspath(root / OPERATOR_DIRECTORY)))
    if not os.path.lexists(path) or _is_reparse(path) or not path.is_dir():
        raise OperatorReceiptError("operator attempt directory is not real")
    found = {entry.name for entry in path.iterdir()}
    if found != {"stdout.log", "stderr.log"}:
        raise OperatorReceiptError(
            f"operator attempt directory entries drifted: {sorted(found)}"
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
    previous = None
    records: list[dict[str, Any]] = []
    for sequence, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OperatorReceiptError("lifecycle is malformed") from exc
        if not isinstance(row, dict) or row.get("ledger_sequence") != sequence:
            raise OperatorReceiptError("lifecycle sequence drifted")
        body = dict(row)
        digest = body.pop("event_sha256", None)
        if (
            digest != sha256_bytes(canonical_bytes(body))
            or row.get("previous_event_sha256") != previous
        ):
            raise OperatorReceiptError("lifecycle hash chain drifted")
        previous = digest
        records.append(row)
    attempt = [row for row in records if row.get("campaign_id") == ATTEMPT_ID]
    started = [row for row in attempt if row.get("event") == "campaign_started"]
    terminal = [
        row
        for row in attempt
        if row.get("event") in {"campaign_completed", "campaign_failed"}
    ]
    if len(started) != 1 or len(terminal) != 1 or terminal[0] is not records[-1]:
        raise OperatorReceiptError("attempt-004 lifecycle boundary is not terminal")
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
        },
    }


def _same_path(value: Any, expected: Path) -> bool:
    if not isinstance(value, (str, os.PathLike)):
        return False
    return os.path.normcase(os.path.abspath(os.fspath(value))) == os.path.normcase(
        os.path.abspath(os.fspath(expected))
    )


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
    expected_stdout = root / STDOUT
    expected_stderr = root / STDERR
    if not _same_path(stdout_log, expected_stdout) or not _same_path(
        stderr_log, expected_stderr
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

    started_row = lifecycle["started"]
    terminal = lifecycle["terminal"]
    started_details = started_row.get("details") or {}
    recorded_sources = started_details.get("sources") or {}
    contract = started_details.get("operator_logs") or {}
    expected_contract = expected_operator_contract(root, current_sources)
    if contract != expected_contract:
        raise OperatorReceiptError("campaign operator-log contract drifted")
    if (
        _source_triplet(recorded_sources.get("campaign") or {})
        != _source_triplet(current_sources["campaign"])
        or _source_triplet(recorded_sources.get("attempt4_operator_launcher") or {})
        != _source_triplet(current_sources["launcher"])
        or _source_triplet(recorded_sources.get("attempt4_operator_recorder") or {})
        != _source_triplet(current_sources["recorder"])
        or _source_triplet(recorded_sources.get("attempt3_recovery_recorder") or {})
        != _source_triplet(current_sources["coordinator_implementation"])
    ):
        raise OperatorReceiptError("campaign/operator source binding drifted")
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
    expected_terminal = "campaign_completed" if exit_code == 0 else "campaign_failed"
    expected_status = "COMPLETE" if exit_code == 0 else "FAILED"
    if (
        terminal.get("event") != expected_terminal
        or (terminal.get("details") or {}).get("status") != expected_status
    ):
        raise OperatorReceiptError("process exit and lifecycle terminal disagree")
    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-004-operator-launch",
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
        "certification_effect": dict(TRANSPORT_CERTIFICATION_EFFECT),
    }


@contextmanager
def held_coordinator(root: Path):
    root = Path(os.path.abspath(os.fspath(root)))
    raw, _ = snapshot(
        root,
        COORDINATOR_IMPLEMENTATION,
        "coordinator implementation",
    )
    if (
        len(raw) != COORDINATOR_IMPLEMENTATION_BYTES
        or sha256_bytes(raw) != COORDINATOR_IMPLEMENTATION_SHA256
    ):
        raise OperatorReceiptError("coordinator implementation pin drifted")
    namespace: dict[str, Any] = {
        "__name__": "_h3_attempt4_frozen_coordinator",
        "__file__": str(root / COORDINATOR_IMPLEMENTATION),
    }
    try:
        exec(
            compile(raw, str(root / COORDINATOR_IMPLEMENTATION), "exec"),
            namespace,
        )
        mutex_class = namespace["ExistingCoordinatorMutex"]
    except Exception as exc:
        raise OperatorReceiptError(
            f"cannot load exact coordinator implementation: {exc}"
        ) from exc
    mutex = mutex_class(root)
    try:
        mutex.acquire()
    except Exception as exc:
        raise OperatorReceiptError(
            f"attempt-004 coordinator is held or unavailable: {exc}"
        ) from exc
    try:
        yield mutex
    finally:
        try:
            mutex.release()
        except Exception as exc:
            raise OperatorReceiptError(
                f"cannot release attempt-004 coordinator: {exc}"
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
    destination = Path(os.path.abspath(os.fspath(root / RECEIPT)))
    parent = destination.parent
    if _is_reparse(parent) or not parent.is_dir():
        raise OperatorReceiptError("operator attempt directory is not real")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise OperatorReceiptError("attempt-004 launch receipt already exists") from exc
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
        print(
            json.dumps(
                {
                    "default_read_only": True,
                    "attempt_id": ATTEMPT_ID,
                    "receipt": str(root / RECEIPT),
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
        print(f"[ATTEMPT004 OPERATOR RECEIPT FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
