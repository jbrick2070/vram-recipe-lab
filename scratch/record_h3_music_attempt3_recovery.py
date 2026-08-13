#!/usr/bin/env python3
"""Seal the attempt-003 stale-PID-receipt incident without cleaning it up.

This recorder is deliberately offline and append-only.  Its default invocation
only prints a deterministic candidate.  ``--write`` is the sole write path and
publishes one fixed recovery receipt with ``O_CREAT | O_EXCL``.  The recorder
never removes ``.server.pid``, probes a process, queries a listener, contacts a
server, acquires the GPU, or renders anything.

The recovery does not turn attempt 003 into a successful campaign.  It proves
that pair 2 is a complete cold/warm machine pair, and that the attempt failed
after the owned server had exited because Windows refused to unlink the
already-stale PID receipt at that attempt.  Attempt 004 may carry pairs 1 and 2 only after
this receipt is published and an independent operator removes the exact pinned
stale receipt under the repository's ownership rules.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))


ATTEMPT_ID = "h3music-20260810T023023Z-97ca44b2-attempt-003"
RESUME_ID = "h3music-20260810T023023Z-97ca44b2-attempt-004"
RECOVERY_ID = f"{ATTEMPT_ID}-recovery-001"
CAMPAIGN_ROOT = Path("results/h3_unconditioned_music_campaign")
LIFECYCLE = CAMPAIGN_ROOT / "lifecycle.jsonl"
RECOVERY = CAMPAIGN_ROOT / "recoveries" / f"{ATTEMPT_ID}-stale-pid-recovery.json"
STALE_PID = Path(".server.pid")
COORDINATOR_MUTEX = Path(".coordinator.mutex")
EXPECTED_RECEIPT_BYTES = 16_216
EXPECTED_RECEIPT_SHA256 = (
    "306d44d4778b7a20921bc40df2594b6a11c0b11030e20e1629cd06f2dcd7442d"
)
PAIR_NAME = "h3_unconditioned_music_motion_small_seed42_f124"
PAIR_LOG = (
    CAMPAIGN_ROOT
    / "server_logs"
    / f"{ATTEMPT_ID}-p02-{PAIR_NAME}.log"
)
OPERATOR_DIRECTORY = CAMPAIGN_ROOT / "operator_logs" / ATTEMPT_ID
OPERATOR_STDOUT = OPERATOR_DIRECTORY / "stdout.log"
OPERATOR_STDERR = OPERATOR_DIRECTORY / "stderr.log"

LIFECYCLE_BYTES = 297_646
LIFECYCLE_SHA256 = "8104b063130b8f6ddb907eaa972ff3a52f8879f970e60663d9df0ee607a83907"
LIFECYCLE_LAST_EVENT_SHA256 = (
    "ad6ad066c8d64b7066c838541f583d4a10b8bc6f5ed30a77eff9ef632b3927ba"
)
STALE_PID_BYTES = b"19256"
STALE_PID_SHA256 = "b1fd70434f75046bb14ecd64255dbea1f5add0142981b29db5f82bddf14116f0"
PAIR_CANONICAL_SHA256 = (
    "a3dd0a5966f6f738b56fbadfd53c95a54789e9481e5b0202bd60d650e8aa3be1"
)
PAIR_SERVER_IDENTITY = {
    "serving_pid": 19_256,
    "process_create_time": 1_786_336_988.58777,
}
PAIR_RUN_IDENTITY_SHA256 = (
    "cb168f4c65fb0e90099200ab34bd09c7479f6b6ff3edf433074ba0d78bd02672"
)
PAIR_COLD_QUEUED_SHA256 = (
    "c2b680a4d03a96a2a2ff398ecdfb58d5d0ed2e3517a17f880a1dfc599d01dfd1"
)
PAIR_WARM_QUEUED_SHA256 = (
    "42592f5b73e3d2806a140a1bc85248045f85d494602625c71ab30ba78d9355b7"
)

FILE_PINS: dict[str, tuple[Path, int, str]] = {
    "pair2_run1": (
        Path(f"results/{PAIR_NAME}_run1.json"),
        63_402,
        "a3bd3aaf1cf60f578d6e472d7894c12041dd32bd14ccce475f5dd966b4f4cff0",
    ),
    "pair2_run2": (
        Path(f"results/{PAIR_NAME}_run2.json"),
        64_214,
        "737b3d4a4473569cbfa6615b01eb3a4143450d2a133cbf99b3990ea71e1c7aa8",
    ),
    "pair2_alias": (
        Path(f"results/{PAIR_NAME}.json"),
        64_214,
        "737b3d4a4473569cbfa6615b01eb3a4143450d2a133cbf99b3990ea71e1c7aa8",
    ),
    "pair2_cold_artifact": (
        Path(f"outputs/{PAIR_NAME}_out_00001_.mp4"),
        860_629,
        "92d044cd5d6f2bffb9e53b5ff5b6917670ff52bbb363309ba0473123ac398541",
    ),
    "pair2_warm_artifact": (
        Path(f"outputs/{PAIR_NAME}_out_00002_.mp4"),
        860_629,
        "92d044cd5d6f2bffb9e53b5ff5b6917670ff52bbb363309ba0473123ac398541",
    ),
    "pair2_manager_log": (
        PAIR_LOG,
        25_081,
        "68b53407712bc42a59167bf5e4fb55aa6fbc8008704a3c695c64e05c56f5f24c",
    ),
    "operator_stdout": (
        OPERATOR_STDOUT,
        3_865,
        "3d805bca0d44bba06b19ea316dbfb9a9753daaeca3b57f1df21f121174f76868",
    ),
    "operator_stderr": (
        OPERATOR_STDERR,
        150,
        "2f0db3bb5cdda0b02311f561265a10d153551f2f6d7999d07fa20b890f687b2e",
    ),
    "attempt2_recovery": (
        CAMPAIGN_ROOT
        / "recoveries"
        / "h3music-20260810T023023Z-97ca44b2-attempt-002-return120-recovery.json",
        31_555,
        "32a9e9403388d76e190082a04937fb83446b4b3617c0a2178cd4eb673de4911d",
    ),
}

SOURCE_PINS: dict[str, tuple[Path, int, str, str]] = {
    "runner": (
        Path("run_recipe.py"),
        174_954,
        "938c72ad5b4cb6565804dde85222103707be67c410b4affec766b6fc9ed7acad",
        "runner",
    ),
    "lab_locks": (
        Path("lab_locks.py"),
        19_611,
        "0200e8620558fe3a7ddf75bf54678439905d6041a65d1c06bd2b2ba01def0ff1",
        "lab_locks",
    ),
    "manager_test_boot": (
        Path("boot_h3_manager_offline_test.cmd"),
        2_556,
        "bce4a81841579226c7aaf8a0bd04cdac25ddfb9b4bcf60f63c0bd9fc740b35a3",
        "manager_test_boot_cmd",
    ),
    "attempt3_campaign": (
        Path("scratch/run_h3_unconditioned_music_campaign.py"),
        118_043,
        "a1073c25caf4749ec095b99fe73b821aa5804c1f23d8d772a74d795af6fd4a0c",
        "campaign",
    ),
    "canonical_campaign": (
        Path("scratch/run_h3_canonical_campaign.py"),
        77_526,
        "0c3246a435d0c9f208ecbca4bc77b172e2a1e3793cbb96332a2e41781fd5cb38",
        "campaign_canonical",
    ),
    "manager_guard": (
        Path("scratch/h3_manager_offline_guard.py"),
        39_609,
        "1b06e5662e9bad8d17aac05d31e393683f3cd450dadbeb86c3763c3a47b2a821",
        "manager_guard",
    ),
    "attempt3_launcher": (
        Path("scratch/start_h3_music_attempt3.ps1"),
        5_788,
        "1a4dac75f14580d407cafc44c6b7503c6db3d7539432b28f4d79d9239fcb6601",
        "operator_launcher",
    ),
    "attempt3_operator_recorder": (
        Path("scratch/record_h3_music_operator_launch.py"),
        32_374,
        "0057321608c679c4d0924421dfc8174c7a7e61227cfc257a31cf1cacdb9fd849",
        "operator_recorder",
    ),
}

EXPECTED_ROWS: tuple[tuple[str, int, str, str], ...] = (
    ("h3music-20260810T023023Z-97ca44b2", 1, "campaign_started", "f01b06798f7529cf9e38f734a1481438bbada3d57faa3774c0cf14d6cdca9ef0"),
    ("h3music-20260810T023023Z-97ca44b2", 2, "campaign_preflight_passed", "006da69b6ad926742a2cd2d0a0c7abddb63a04d0bccb581dcc32a0db9efa717c"),
    ("h3music-20260810T023023Z-97ca44b2", 3, "pair_started", "63ee32714a4228ccde67ae66da6c8ebe997442bc9fbb26948bf918786965d715"),
    ("h3music-20260810T023023Z-97ca44b2", 4, "cold_child_returned", "32a61263ef36a5549512c4c020d696e520ac84d1c9760bb305b55d55e5ca4d4a"),
    ("h3music-20260810T023023Z-97ca44b2", 5, "campaign_failed", "20ec57fc403d782ee292c3bfbd75b70c3d5466fca620f255e8aefaeb5c0bea1b"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 1, "recovery_started", "478037f4dc52adff8b4814a1e424a2c64a04284f33867435f176d1a1244c0053"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 2, "campaign_started", "6e8e66fcf897d50a82232647870539d02b1bb847aa9d0de9b83da2d8f7d1683e"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 3, "campaign_preflight_passed", "f94cf3db25fb9c4fb0cf2439d966fcb1b588365171ec28fba7c8df5db1eb2fca"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 4, "pair_started", "4d25afdb53d1142775b6254ff55ed1b3e0a45cc741b9cd5878bbb65f3349f6a7"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 5, "cold_child_returned", "4f52b4f8665729ddce320d506911811327be07a0c06dc55ff82abfd585a643df"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 6, "cold_verified", "9b07cdf20a1022eeb0b807027713ff97bcd01f2b878ab441be4fddb9e86ba094"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 7, "warm_shutdown_child_returned", "8ad4116ad15e1faeb8fa1296a651fe601e14e99eb23e0ceaa06977e91cddd9cc"),
    ("h3music-20260810T023023Z-97ca44b2-attempt-002", 8, "campaign_failed", "9ce05976ffa45551bb3bc1dbb34d1bdc1f50c81ace67d51fcea46126279ec857"),
    (ATTEMPT_ID, 1, "recovery_started", "61f06906dcb26a902dae8b7949a150cc7fe8d609ebe9810041241c70f71528cf"),
    (ATTEMPT_ID, 2, "campaign_started", "84c16f31a3b755c7173ed51bf32350cb116cb5e649dcc9ddc099fa93b98bf4b6"),
    (ATTEMPT_ID, 3, "campaign_preflight_passed", "38c31fb3c158b5ed8e1e91fc58e8e4ba8057c13e82ce7984fe79554d20a85ad2"),
    (ATTEMPT_ID, 4, "pair_carried_forward", "1d311ff2574d983b0df01283cdf31d6c3f7b0ac1484d29813f1e33308fb71d23"),
    (ATTEMPT_ID, 5, "pair_started", "07c7413ea2d716f047523c46322c3f8b892c354c1abd0f6e6c8dd7e3414f785d"),
    (ATTEMPT_ID, 6, "cold_child_returned", "64d9e8ff2f6b9644dcfd61c502e527bebdb8480ec4bf7db121aec216568c7eca"),
    (ATTEMPT_ID, 7, "cold_verified", "5ffaef7a9ba781cbbee89e04bd9c5a8886956371095288ad61916de3921fcbab"),
    (ATTEMPT_ID, 8, "warm_shutdown_child_returned", "db5d8bb72735ec2e107fcb7ff8010e96a6b810f905e66dc6f2bcb2350dab3995"),
    (ATTEMPT_ID, 9, "campaign_failed", LIFECYCLE_LAST_EVENT_SHA256),
)

SHUTDOWN_START_LINE = "[SERVER] Shutting down verified lab server (PID 19256)..."
SHUTDOWN_FAILURE_LINE = (
    "[SERVER] server exited but PID receipt removal failed: [WinError 32] "
    "The process cannot access the file because it is being used by another "
    "process: 'C:\\\\Users\\\\jeffr\\\\Documents\\\\ComfyUI\\\\vram-recipe-lab\\\\.server.pid'"
)
STDERR_LINE = (
    "[H3 MUSIC CAMPAIGN FAILED] CampaignError: "
    f"{PAIR_NAME} post-shutdown is not clean: server_pid_receipt_exists=True"
)


class RecoveryError(RuntimeError):
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


def snapshot_file(
    root: Path,
    relative: Path,
    label: str,
    *,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    lexical = Path(os.path.abspath(os.fspath(root / relative)))
    if not os.path.lexists(lexical):
        raise RecoveryError(f"missing {label}: {relative.as_posix()}")
    before = lexical.lstat()
    if _is_reparse(lexical) or not stat.S_ISREG(before.st_mode):
        raise RecoveryError(f"{label} is not a regular non-reparse file")
    if int(before.st_nlink) != 1:
        raise RecoveryError(f"{label} must have exactly one hardlink")
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(lexical, flags)
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
    after = lexical.lstat()

    def identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_nlink),
            int(value.st_size),
            int(value.st_mtime_ns),
        )

    sealed_identity = identity(before)
    if (
        sealed_identity != identity(descriptor_before)
        or sealed_identity != identity(descriptor_after)
        or sealed_identity != identity(after)
        or int(before.st_mode) != int(after.st_mode)
        or int(descriptor_before.st_mode) != int(descriptor_after.st_mode)
        or _is_reparse(lexical)
        or not stat.S_ISREG(after.st_mode)
        or not stat.S_ISREG(descriptor_after.st_mode)
        or int(after.st_nlink) != 1
        or len(raw) != after.st_size
    ):
        raise RecoveryError(f"{label} changed during read")
    digest = sha256_bytes(raw)
    if expected_bytes is not None and len(raw) != expected_bytes:
        raise RecoveryError(f"{label} byte-count pin drifted")
    if expected_sha256 is not None and digest != expected_sha256:
        raise RecoveryError(f"{label} SHA-256 pin drifted")
    return raw, {
        "path": relative.as_posix(),
        "bytes": len(raw),
        "sha256": digest,
        "device": int(after.st_dev),
        "inode": int(after.st_ino),
        "mode": int(after.st_mode),
        "descriptor_mode": int(descriptor_after.st_mode),
        "link_count": int(after.st_nlink),
        "mtime_ns": int(after.st_mtime_ns),
        "regular_file": True,
        "reparse_point": False,
    }


class ExistingCoordinatorMutex:
    """Lock the existing one-byte lab carrier without creating or writing it."""

    def __init__(self, root: Path):
        self.root = Path(os.path.abspath(os.fspath(root)))
        self.path = self.root / COORDINATOR_MUTEX
        self._handle: Any = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self.acquired:
            raise RecoveryError("recovery coordinator is already held")
        _, snapshot = snapshot_file(
            self.root,
            COORDINATOR_MUTEX,
            "pre-existing coordinator carrier",
            expected_bytes=1,
            expected_sha256="6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
        )
        handle = None
        locked = False
        try:
            # r+b is pre-existing-only and permits the Windows byte-range lock;
            # no write is performed anywhere in this class.
            handle = self.path.open("r+b", buffering=0)
            descriptor = os.fstat(handle.fileno())
            if (
                int(descriptor.st_dev) != snapshot["device"]
                or int(descriptor.st_ino) != snapshot["inode"]
                or int(descriptor.st_nlink) != snapshot["link_count"]
                or int(descriptor.st_size) != snapshot["bytes"]
                or int(descriptor.st_mtime_ns) != snapshot["mtime_ns"]
                or not stat.S_ISREG(descriptor.st_mode)
            ):
                raise RecoveryError("coordinator carrier changed before lock")
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            after = self.path.lstat()
            if (
                _is_reparse(self.path)
                or not stat.S_ISREG(after.st_mode)
                or int(after.st_dev) != snapshot["device"]
                or int(after.st_ino) != snapshot["inode"]
                or int(after.st_mode) != snapshot["mode"]
                or int(after.st_nlink) != snapshot["link_count"]
                or int(after.st_size) != snapshot["bytes"]
                or int(after.st_mtime_ns) != snapshot["mtime_ns"]
            ):
                raise RecoveryError("coordinator carrier changed during lock")
        except (OSError, IOError) as exc:
            raise RecoveryError(f"lab coordinator is held or unavailable: {exc}") from exc
        except Exception:
            raise
        finally:
            if handle is not None and (not locked or sys.exc_info()[0] is not None):
                if locked:
                    try:
                        handle.seek(0)
                        if sys.platform == "win32":
                            import msvcrt

                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except (OSError, IOError):
                        pass
                handle.close()
        if handle is None or not locked:
            raise RecoveryError("failed to acquire pre-existing coordinator carrier")
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError) as exc:
            raise RecoveryError(f"could not release lab coordinator: {exc}") from exc
        finally:
            handle.close()
            self._handle = None


def validate_lifecycle(raw: bytes) -> dict[str, Any]:
    if len(raw) != LIFECYCLE_BYTES or sha256_bytes(raw) != LIFECYCLE_SHA256:
        raise RecoveryError("attempt-003 lifecycle full-file pin drifted")
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise RecoveryError("attempt-003 lifecycle encoding/framing drifted")
    lines = raw.splitlines()
    if len(lines) != len(EXPECTED_ROWS):
        raise RecoveryError("attempt-003 lifecycle must contain exactly 22 rows")
    records: list[dict[str, Any]] = []
    previous: str | None = None
    for ledger_sequence, (line, expected) in enumerate(
        zip(lines, EXPECTED_ROWS, strict=True), start=1
    ):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RecoveryError(f"lifecycle row {ledger_sequence} is malformed") from exc
        if not isinstance(row, dict):
            raise RecoveryError("lifecycle row is not an object")
        body = dict(row)
        digest = body.pop("event_sha256", None)
        expected_campaign, expected_sequence, expected_event, expected_sha = expected
        if digest != sha256_bytes(canonical_bytes(body)):
            raise RecoveryError("lifecycle canonical event SHA mismatch")
        if (
            row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_id") != expected_campaign
            or row.get("campaign_sequence") != expected_sequence
            or row.get("event") != expected_event
            or digest != expected_sha
            or row.get("previous_event_sha256") != previous
        ):
            raise RecoveryError(f"lifecycle row {ledger_sequence} identity drifted")
        previous = digest
        records.append(row)

    warm = records[20].get("details") or {}
    warm_outcome = warm.get("outcome") or {}
    if (
        warm_outcome.get("returncode") != 0
        or warm_outcome.get("descendant_server_instances") != []
        or warm.get("pair_index") != 2
    ):
        raise RecoveryError("attempt-003 warm shutdown child outcome drifted")
    terminal = records[21].get("details") or {}
    expected_failure_state = {
        "gpu_lock_exists": False,
        "suite_lock_exists": False,
        "server_pid_receipt_exists": True,
        "server_pid_receipt": 19_256,
        "server_pid_create_time": None,
        "queue_quarantine_exists": False,
        "listener_pids_8199": [],
        "expected_server_identity_live": False,
    }
    if (
        terminal.get("status") != "FAILED"
        or terminal.get("error_type") != "CampaignError"
        or terminal.get("error")
        != f"{PAIR_NAME} post-shutdown is not clean: server_pid_receipt_exists=True"
        or terminal.get("completed_pair_count") != 1
        or terminal.get("carried_pair_count") != 1
        or terminal.get("new_verified_pair_count") != 0
        or terminal.get("failure_state") != expected_failure_state
        or terminal.get("owned_server_cleanup") != {"attempted": False}
        or terminal.get("stopped_without_force_or_additional_render") is not True
    ):
        raise RecoveryError("attempt-003 terminal failure semantics drifted")
    sources = (records[14].get("details") or {}).get("sources")
    if not isinstance(sources, dict):
        raise RecoveryError("attempt-003 lifecycle source evidence is absent")
    return {
        "records": records,
        "sources": sources,
        "prefix": {
            "path": LIFECYCLE.as_posix(),
            "bytes": LIFECYCLE_BYTES,
            "sha256": LIFECYCLE_SHA256,
            "row_count": 22,
            "last_event_sha256": LIFECYCLE_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
        },
        "terminal_failure": {
            "status": "FAILED",
            "error": terminal["error"],
            "completed_pair_count": 1,
            "carried_pair_count": 1,
            "new_verified_pair_count": 0,
            "failure_state": expected_failure_state,
        },
    }


def validate_operator_streams(
    stdout_raw: bytes, stderr_raw: bytes
) -> dict[str, Any]:
    try:
        stdout_lines = stdout_raw.decode("utf-8").splitlines()
        stderr_lines = stderr_raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RecoveryError("operator stream is not UTF-8") from exc
    if (
        len(stdout_lines) != 67
        or stdout_lines[64] != SHUTDOWN_START_LINE
        or stdout_lines[65] != SHUTDOWN_FAILURE_LINE
        or stdout_lines[66] != "[LOCK] Released .gpu.lock and coordinator"
        or stderr_lines != [STDERR_LINE]
    ):
        raise RecoveryError("operator shutdown/failure transcript drifted")
    return {
        "shutdown_start": {
            "line_number": 65,
            "text": SHUTDOWN_START_LINE,
            "line_sha256": sha256_bytes(SHUTDOWN_START_LINE.encode("utf-8")),
        },
        "receipt_unlink_failure": {
            "line_number": 66,
            "text": SHUTDOWN_FAILURE_LINE,
            "line_sha256": sha256_bytes(SHUTDOWN_FAILURE_LINE.encode("utf-8")),
        },
        "coordinator_release": {
            "line_number": 67,
            "text": stdout_lines[66],
            "line_sha256": sha256_bytes(stdout_lines[66].encode("utf-8")),
        },
        "campaign_failure": {
            "line_number": 1,
            "text": STDERR_LINE,
            "line_sha256": sha256_bytes(STDERR_LINE.encode("utf-8")),
        },
    }


def _snapshot_fixed_files(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    snapshots: dict[str, Any] = {}
    raws: dict[str, bytes] = {}
    for label, (relative, expected_bytes, expected_sha) in FILE_PINS.items():
        raw, snapshot = snapshot_file(
            root,
            relative,
            label,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha,
        )
        raws[label] = raw
        snapshots[label] = snapshot
    if raws["pair2_run2"] != raws["pair2_alias"]:
        raise RecoveryError("pair2 alias is not byte-identical to warm run2")
    distinct_groups = (
        ("pair2_run1", "pair2_run2", "pair2_alias"),
        ("pair2_cold_artifact", "pair2_warm_artifact"),
        ("operator_stdout", "operator_stderr"),
    )
    for group in distinct_groups:
        paths = [root / FILE_PINS[label][0] for label in group]
        for left_index, left in enumerate(paths):
            for right in paths[left_index + 1 :]:
                try:
                    if os.path.samefile(left, right):
                        raise RecoveryError(f"hardlinked evidence in group: {group}")
                except RecoveryError:
                    raise
                except OSError as exc:
                    raise RecoveryError("cannot prove evidence-file independence") from exc
    return snapshots, raws


def _snapshot_source_files(
    root: Path,
    lifecycle_sources: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    snapshots: dict[str, Any] = {}
    raws: dict[str, bytes] = {}
    for label, (relative, expected_bytes, expected_sha, lifecycle_label) in SOURCE_PINS.items():
        raw, snapshot = snapshot_file(
            root,
            relative,
            label,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha,
        )
        if lifecycle_sources is not None:
            recorded = lifecycle_sources.get(lifecycle_label) or {}
            if (
                recorded.get("bytes") != expected_bytes
                or recorded.get("sha256") != expected_sha
            ):
                raise RecoveryError(f"attempt-003 lifecycle source pin drifted: {label}")
        snapshots[label] = snapshot
        raws[label] = raw
    return snapshots, raws


def _module_from_bytes(name: str, path: Path, raw: bytes) -> ModuleType:
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(path))
    if spec is None:
        raise RecoveryError(f"cannot create frozen module spec: {name}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        code = compile(raw, str(path), "exec", dont_inherit=True)
        exec(code, module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


@contextmanager
def frozen_campaign_modules(
    root: Path, source_raws: Mapping[str, bytes]
):
    injected_names = (
        "h3_manager_offline_guard",
        "run_h3_canonical_campaign",
        "_h3_attempt3_frozen_campaign",
    )
    previous = {name: sys.modules.get(name) for name in injected_names}
    try:
        _module_from_bytes(
            "h3_manager_offline_guard",
            root / SOURCE_PINS["manager_guard"][0],
            source_raws["manager_guard"],
        )
        _module_from_bytes(
            "run_h3_canonical_campaign",
            root / SOURCE_PINS["canonical_campaign"][0],
            source_raws["canonical_campaign"],
        )
        frozen = _module_from_bytes(
            "_h3_attempt3_frozen_campaign",
            root / SOURCE_PINS["attempt3_campaign"][0],
            source_raws["attempt3_campaign"],
        )
        yield frozen
    finally:
        for name in reversed(injected_names):
            old = previous[name]
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def _verify_pairs(
    root: Path,
    lifecycle_sources: Mapping[str, Any],
    frozen_campaign: ModuleType,
) -> dict[str, Any]:
    if Path(os.path.abspath(os.fspath(root))) != ROOT:
        raise RecoveryError("full pair verification is fixed to the real lab root")
    preserved_pair1 = frozen_campaign.verify_attempt2_preserved_evidence()
    specs = frozen_campaign.load_specs()
    spec = specs[1]
    pair2 = frozen_campaign.verify_pair(
        spec,
        2,
        ATTEMPT_ID,
        lifecycle_sources,
        ROOT / PAIR_LOG,
        cold_run_number=1,
        cold_config_run_count=1,
        warm_run_number=2,
        warm_config_run_count=2,
        allowed_run_numbers=(1, 2),
    )
    canonical_pair2 = sha256_bytes(frozen_campaign.canon.canonical_bytes(pair2))
    if canonical_pair2 != PAIR_CANONICAL_SHA256:
        raise RecoveryError("pair2 full-verifier result hash drifted")
    cold = pair2["cold"]
    warm = pair2["warm"]
    if (
        cold["server_instance"] != PAIR_SERVER_IDENTITY
        or warm["server_instance"] != PAIR_SERVER_IDENTITY
        or cold["run_identity_sha256"] != PAIR_RUN_IDENTITY_SHA256
        or warm["run_identity_sha256"] != PAIR_RUN_IDENTITY_SHA256
        or cold["queued_prompt_sha256"] != PAIR_COLD_QUEUED_SHA256
        or warm["queued_prompt_sha256"] != PAIR_WARM_QUEUED_SHA256
    ):
        raise RecoveryError("pair2 identity binding drifted")
    pair1 = preserved_pair1["pair"]
    return {
        "pair1": {
            "source_campaign_id": frozen_campaign.RESUME_CAMPAIGN_ID,
            "canonical_result_sha256": frozen_campaign.sha256_bytes(
                frozen_campaign.canon.canonical_bytes(pair1)
            ),
            "cold_receipt_sha256": pair1["cold"]["receipt_sha256"],
            "warm_receipt_sha256": pair1["warm"]["receipt_sha256"],
            "manager_log_sha256": pair1["final_manager_log"]["log"]["sha256"],
            "status": "CARRIED_FORWARD_MACHINE_COMPLETE",
            "human_judgment": "PENDING",
        },
        "pair2": {
            "source_campaign_id": ATTEMPT_ID,
            "canonical_result_sha256": canonical_pair2,
            "cold_receipt_sha256": cold["receipt_sha256"],
            "warm_receipt_sha256": warm["receipt_sha256"],
            "cold_artifact_sha256": cold["artifact"]["sha256"],
            "warm_artifact_sha256": warm["artifact"]["sha256"],
            "manager_log_sha256": pair2["final_manager_log"]["log"]["sha256"],
            "server_instance": cold["server_instance"],
            "run_identity_sha256": cold["run_identity_sha256"],
            "cold_queued_prompt_sha256": cold["queued_prompt_sha256"],
            "warm_queued_prompt_sha256": warm["queued_prompt_sha256"],
            "cold_peak_vram_gb": cold["peak_vram_gb"],
            "warm_peak_vram_gb": warm["peak_vram_gb"],
            "cold_duration_s": cold["duration_s"],
            "warm_duration_s": warm["duration_s"],
            "status": "RECOVERABLE_MACHINE_COMPLETE",
            "human_judgment": "PENDING",
        },
    }


def _build_receipt_locked(root: Path) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    lifecycle_raw, lifecycle_snapshot = snapshot_file(
        root,
        LIFECYCLE,
        "attempt-003 lifecycle",
        expected_bytes=LIFECYCLE_BYTES,
        expected_sha256=LIFECYCLE_SHA256,
    )
    lifecycle = validate_lifecycle(lifecycle_raw)
    fixed, raws = _snapshot_fixed_files(root)
    sources, source_raws = _snapshot_source_files(root, lifecycle["sources"])
    stale_raw, stale_snapshot = snapshot_file(
        root,
        STALE_PID,
        "stale PID receipt",
        expected_bytes=len(STALE_PID_BYTES),
        expected_sha256=STALE_PID_SHA256,
    )
    if stale_raw != STALE_PID_BYTES:
        raise RecoveryError("stale PID receipt bytes drifted")
    for forbidden in (Path(".gpu.lock"), Path(".suite.lock"), Path(".queue.quarantine.json")):
        if os.path.lexists(root / forbidden):
            raise RecoveryError(f"unexpected lock/quarantine exists: {forbidden}")
    transcript = validate_operator_streams(
        raws["operator_stdout"], raws["operator_stderr"]
    )
    with frozen_campaign_modules(root, source_raws) as frozen_campaign:
        pairs = _verify_pairs(
            root,
            lifecycle["sources"],
            frozen_campaign,
        )
    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-003-stale-pid-recovery",
        "recovery_id": RECOVERY_ID,
        "failed_campaign_id": ATTEMPT_ID,
        "resume_campaign_id": RESUME_ID,
        "status": "ATTEMPT_003_FAILED_PAIR2_MACHINE_RECOVERED",
        "success": True,
        "recording_time": {
            "included": False,
            "reason": "deterministic pre-publication candidate; filesystem publication metadata is non-authoritative",
        },
        "immutable_evidence": {
            "lifecycle": {
                "snapshot": lifecycle_snapshot,
                "prefix": lifecycle["prefix"],
                "terminal_failure": lifecycle["terminal_failure"],
            },
            "pair_files": {
                key: value
                for key, value in fixed.items()
                if key.startswith("pair2_")
            },
            "operator_streams": {
                "stdout": fixed["operator_stdout"],
                "stderr": fixed["operator_stderr"],
                "transcript": transcript,
            },
            "stale_pid_receipt": {
                **stale_snapshot,
                "utf8_text": "19256",
                "pid": 19_256,
                "present_during_recovery_recording": True,
            },
            "attempt2_recovery": fixed["attempt2_recovery"],
        },
        "source_sha256s": sources,
        "full_pair_verification": pairs,
        "incident_classification": {
            "classification": "EXPECTED_SERVER_EXITED_STALE_PID_RECEIPT_UNLINK_FAILED",
            "warm_child_returncode": 0,
            "shutdown_requested": True,
            "owned_server_pid": 19_256,
            "lifecycle_post_child_listener_pids_8199": [],
            "lifecycle_post_child_expected_server_identity_live": False,
            "operator_stdout_reports_server_exited": True,
            "operator_stdout_reports_windows_unlink_error": True,
            "campaign_failure_trigger": "post-shutdown clean-state gate found .server.pid",
            "ambiguous_live_server": False,
            "authority": "attempt lifecycle plus exact operator stdout/stderr; recorder performs no live probes",
        },
        "certification_effect": {
            "attempt_003_status": "FAILED",
            "attempt_003_ledger_completed_pair_count": 1,
            "pair1_machine_complete": True,
            "pair2_machine_pair_recoverable_and_complete": True,
            "human_judgment": "PENDING",
            "promotion_or_study_pass_granted": False,
            "campaign_complete_granted": False,
        },
        "recovery_policy": {
            "resume_campaign_id": RESUME_ID,
            "carry_pair_indices": [1, 2],
            "execute_pair_indices": list(range(3, 12)),
            "next_pair_index": 3,
            "remaining_pair_count": 9,
            "executions_per_pair": 2,
            "remaining_execution_count": 18,
            "stale_receipt_cleanup": {
                "performed_by_this_recorder": False,
                "permitted_before_receipt_publication": False,
                "operator_must_match_exact_bytes_and_sha256": True,
                "operator_must_independently_reprove_pid_dead_and_listener_absent": True,
                "attempt004_must_start_from_clean_state": True,
            },
        },
        "anti_mutation": {
            "failed_lifecycle_appended_or_rewritten": False,
            "pair_receipt_or_artifact_modified": False,
            "operator_stream_modified": False,
            "stale_pid_receipt_deleted_by_recorder": False,
            "process_or_listener_queried_by_recorder": False,
            "server_or_gpu_queried_by_recorder": False,
            "render_started_by_recorder": False,
            "otr_touched": False,
            "recorder_source_self_hash_included": False,
            "recorder_source_self_hash_exclusion_reason": "avoid self-referential receipt; attempt004 pins recorder source externally",
        },
    }


@contextmanager
def held_coordinator(root: Path):
    root = Path(os.path.abspath(os.fspath(root)))
    # Hash every local evidence source before the critical section.  Campaign
    # modules are later executed only from a second, under-lock byte snapshot.
    _snapshot_source_files(root)
    mutex = ExistingCoordinatorMutex(root)
    mutex.acquire()
    try:
        yield mutex
    finally:
        mutex.release()


def build_receipt(root: Path = ROOT) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    with held_coordinator(root):
        return _build_receipt_locked(root)


def exclusive_write(
    root: Path,
    payload: Mapping[str, Any],
    *,
    coordinator: Any,
    final_payload_builder: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    destination = Path(os.path.abspath(os.fspath(root / RECOVERY)))
    if getattr(coordinator, "acquired", False) is not True:
        raise RecoveryError("recovery publication requires the held lab coordinator")
    encoded = receipt_bytes(payload)
    digest = sha256_bytes(encoded)
    if len(encoded) != EXPECTED_RECEIPT_BYTES or digest != EXPECTED_RECEIPT_SHA256:
        raise RecoveryError("recovery candidate byte-count/SHA-256 pin drifted")
    final_payload = final_payload_builder()
    final_encoded = receipt_bytes(final_payload)
    if final_encoded != encoded:
        raise RecoveryError("recovery evidence changed before O_EXCL publication")
    if (
        len(final_encoded) != EXPECTED_RECEIPT_BYTES
        or sha256_bytes(final_encoded) != EXPECTED_RECEIPT_SHA256
    ):
        raise RecoveryError("final recovery candidate byte-count/SHA-256 pin drifted")
    parent = destination.parent
    if not os.path.lexists(parent):
        parent.mkdir(parents=True, exist_ok=False)
    if _is_reparse(parent) or not parent.is_dir():
        raise RecoveryError("recovery parent is not a real directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise RecoveryError(f"recovery receipt already exists: {RECOVERY.as_posix()}") from exc
    try:
        written = 0
        while written < len(encoded):
            count = os.write(fd, encoded[written:])
            if count <= 0:
                raise RecoveryError("short O_EXCL recovery receipt write")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    published = destination.read_bytes()
    if published != encoded:
        raise RecoveryError("published recovery receipt differs from intended bytes")
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
        help=f"publish fixed append-only receipt {RECOVERY.as_posix()}",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    args = parse_args(argv)
    try:
        root = Path(os.path.abspath(os.fspath(root)))
        with held_coordinator(root) as coordinator:
            payload = _build_receipt_locked(root)
            if not args.write:
                if not args.quiet:
                    sys.stdout.write(receipt_bytes(payload).decode("utf-8"))
                return 0
            published = exclusive_write(
                root,
                payload,
                coordinator=coordinator,
                final_payload_builder=lambda: _build_receipt_locked(root),
            )
        if not args.quiet:
            print(json.dumps({"status": "CREATED", "recovery_receipt": published}, indent=2))
        return 0
    except Exception as exc:
        print(f"[H3 MUSIC RECOVERY3 FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
