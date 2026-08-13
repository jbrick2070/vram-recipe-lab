#!/usr/bin/env python3
"""Correct and seal the failed H3 music attempt-004 recovery authority.

The default mode is read-only.  It validates the complete 65-row lifecycle,
re-runs the hash-pinned attempt-004 full pair verifier for pairs 1-9, and
classifies pair-10 run1 as a non-certifying timeout with no artifact.  It does
not inspect processes, listeners, locks, GPU state, or any server.

An earlier recovery receipt named a nonexistent pair-11 recipe.  This recorder
hash-pins that receipt as unusable, leaves it untouched, and supersedes it with
a new correction receipt.  ``--write`` is the only write path and uses
``O_CREAT | O_EXCL``.  The corrected authority permits only attempt-005 and
only four new legs: pair10 run2 cold/run3 warm and the canonical pair11 run1
cold/run2 warm.
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
from typing import Any, Iterator, Mapping, Sequence


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

BASE_ID = "h3music-20260810T023023Z-97ca44b2"
ATTEMPT_ID = f"{BASE_ID}-attempt-004"
RESUME_ID = f"{BASE_ID}-attempt-005"
SUPERSEDED_RECOVERY_ID = f"{ATTEMPT_ID}-recovery-001"
RECOVERY_ID = f"{ATTEMPT_ID}-recovery-002"

CAMPAIGN_ROOT = Path("results/h3_unconditioned_music_campaign")
LIFECYCLE = CAMPAIGN_ROOT / "lifecycle.jsonl"
SUPERSEDED_RECOVERY = (
    CAMPAIGN_ROOT / "recoveries" / f"{ATTEMPT_ID}-timeout-recovery.json"
)
RECOVERY = (
    CAMPAIGN_ROOT
    / "recoveries"
    / f"{ATTEMPT_ID}-timeout-recovery-correction-001.json"
)
OPERATOR_DIRECTORY = CAMPAIGN_ROOT / "operator_logs" / ATTEMPT_ID
OPERATOR_STDOUT = OPERATOR_DIRECTORY / "stdout.log"
OPERATOR_STDERR = OPERATOR_DIRECTORY / "stderr.log"
OPERATOR_LAUNCH_RECEIPT = OPERATOR_DIRECTORY / "launch.json"
COORDINATOR_MUTEX = Path(".coordinator.mutex")

PAIR10 = "h3_unconditioned_music_scene_seed42_f192"
PAIR11 = "h3_unconditioned_music_scene_seed42_f277"
PAIR11_RECIPE_SHA256 = (
    "96621cd7c7ae5ae086c03fd43133f9d6eeecb177e06c05eff9ecbc791d561288"
)
ERRONEOUS_PAIR11 = "h3_unconditioned_music_motion_large_seed42_f192"
PAIR10_RUN1 = Path(f"results/{PAIR10}_run1.json")
PAIR10_ALIAS = Path(f"results/{PAIR10}.json")
PAIR10_LOG = CAMPAIGN_ROOT / "server_logs" / f"{ATTEMPT_ID}-p10-{PAIR10}.log"

LIFECYCLE_BYTES = 1_513_119
LIFECYCLE_SHA256 = "1fb0ea686f0acd30e83e2f294d717afebf471381b3eb9d2138a12f6a10734c69"
LIFECYCLE_ROWS = 65
LIFECYCLE_LAST_EVENT_SHA256 = (
    "b66526982583393059c25d6c67cad3b8fdae4a51239111dc19d15681c14df80f"
)

SOURCE_PINS: dict[str, tuple[Path, int, str, str]] = {
    "attempt4_campaign": (
        Path("scratch/run_h3_unconditioned_music_campaign.py"),
        152_154,
        "aed15f895e5837e181d639ee7e04bed638e904ea91911a190b31051bf3482a19",
        "campaign",
    ),
    "runner": (
        Path("run_recipe.py"),
        180_403,
        "0224d6ec6db4962f0332bf53e031cd71e2818ccca4a919479c829e64cbfc4bf8",
        "runner",
    ),
    "attempt4_launcher": (
        Path("scratch/start_h3_music_attempt4.ps1"),
        5_708,
        "163650d79321cbda6ca8287fdf7551acca4ee54fbcee17b75e14bfb0cac6ae69",
        "attempt4_operator_launcher",
    ),
    "attempt4_operator_recorder": (
        Path("scratch/record_h3_music_attempt4_operator_launch.py"),
        24_435,
        "053fd5fd22ba6c6132636a6946d2b4da6184d8f631a88970120afad77906059e",
        "attempt4_operator_recorder",
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
}

FILE_PINS: dict[str, tuple[Path, int, str]] = {
    "superseded_recovery": (
        SUPERSEDED_RECOVERY,
        59_642,
        "a76d05fb4d0d01afa90b705ba654af6c8b56344bd93478e653fa9a3146e1f88f",
    ),
    "operator_stdout": (
        OPERATOR_STDOUT,
        27_710,
        "f5725b2bc6bbce93dcc682ae5716b8e8b056ca7f2cb8099f364c795acfed890e",
    ),
    "operator_stderr": (
        OPERATOR_STDERR,
        127,
        "b06421405eaea1da951fc837038d4b255bfa8652571adcfbf4c92120aca0a130",
    ),
    "pair10_failed_run1": (
        PAIR10_RUN1,
        37_593,
        "4ab72334bc80d8155d1b1d1466258922a7a9e1ad2e289f37b07a510115d164bf",
    ),
    "pair10_failed_alias": (
        PAIR10_ALIAS,
        37_593,
        "4ab72334bc80d8155d1b1d1466258922a7a9e1ad2e289f37b07a510115d164bf",
    ),
    "pair10_manager_log": (
        PAIR10_LOG,
        22_893,
        "22d1e7264febfe962cbda12f9365fc633f28af2cb9c079fc253138f5698edfb1",
    ),
}

PAIR_RESULT_SHA256S = {
    1: "b47abc5895f9e0a6bbeb3d4da4a2490213dba168fa1aa4505257bfd5f4103f22",
    2: "a3dd0a5966f6f738b56fbadfd53c95a54789e9481e5b0202bd60d650e8aa3be1",
    3: "21ea1f8d0075915135ef7e2d3a535af5383b16ae4a29189992d48738f914dfc9",
    4: "2b5b1c576888a228713b89842fc9fc39322f38dc599fab9d2235647c8512047b",
    5: "4b2fd091f1a264ceee6e43556c1d2908c2a78138d0fe40334965149e81e38f99",
    6: "e515f5663a251b5fa7750396423e998c769ad6d0de9722c24d8cda0abe1daf7d",
    7: "3bf2ec0437db5d8b4b77ddbb256dad6eb9df17c44e99fba4b711090532788aae",
    8: "0b5356f0516aa4a57a22f8a65026113beca98c18d73346bc4d632c9dbb3479e0",
    9: "cc98b1d1f14d61a2a5bd052d30b6b9fb8f5992a40c5825b4f64f56a2b55b4c75",
}

PAIR_NAMES = {
    1: "h3_unconditioned_music_scene_seed42_f124",
    2: "h3_unconditioned_music_motion_small_seed42_f124",
    3: "h3_unconditioned_music_motion_large_seed42_f124",
    4: "h3_unconditioned_music_scene_seed43_f124",
    5: "h3_unconditioned_music_scene_seed44_f124",
    6: "h3_unconditioned_music_scene_seed45_f124",
    7: "h3_unconditioned_music_scene_seed46_f124",
    8: "h3_unconditioned_music_score_seed42_f124",
    9: "h3_unconditioned_music_sfx_seed42_f124",
    10: PAIR10,
    11: PAIR11,
}

ABSENT_PATHS = (
    OPERATOR_LAUNCH_RECEIPT,
    Path(f"results/{PAIR10}_run2.json"),
    Path(f"results/{PAIR10}_run3.json"),
    Path(f"outputs/{PAIR10}_out_00001_.mp4"),
    Path(f"outputs/{PAIR10}_out_00002_.mp4"),
    Path(f"outputs/{PAIR10}_out_00003_.mp4"),
    Path(f"results/{PAIR11}.json"),
    Path(f"results/{PAIR11}_run1.json"),
    Path(f"results/{PAIR11}_run2.json"),
    Path(f"outputs/{PAIR11}_out_00001_.mp4"),
    Path(f"outputs/{PAIR11}_out_00002_.mp4"),
    CAMPAIGN_ROOT / "server_logs" / f"{ATTEMPT_ID}-p11-{PAIR11}.log",
)

CLEAN_STATE = {
    "gpu_lock_exists": False,
    "suite_lock_exists": False,
    "server_pid_receipt_exists": False,
    "server_pid_receipt": None,
    "server_pid_create_time": None,
    "queue_quarantine_exists": False,
    "listener_pids_8199": [],
    "expected_server_identity_live": False,
}


class RecoveryError(RuntimeError):
    """Frozen attempt evidence or recovery authority is invalid."""


class ExistingCoordinatorMutex:
    """Byte-lock the existing one-byte carrier without creating or writing it."""

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
        if not os.path.lexists(self.path):
            raise RecoveryError("pre-existing coordinator carrier is absent")
        if _is_reparse(self.path) or not self.path.is_file():
            raise RecoveryError("coordinator carrier is not a regular file")
        before = self.path.stat()
        raw = self.path.read_bytes()
        if (
            raw != b"\0"
            or len(raw) != 1
            or sha256_bytes(raw)
            != "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
        ):
            raise RecoveryError("coordinator carrier byte/SHA pin drifted")
        handle = None
        locked = False
        try:
            # r+b is pre-existing-only and is required by Windows byte locking.
            # This class never invokes a write operation on the carrier.
            handle = self.path.open("r+b", buffering=0)
            descriptor = os.fstat(handle.fileno())
            if (
                int(descriptor.st_dev) != int(before.st_dev)
                or int(descriptor.st_ino) != int(before.st_ino)
                or int(descriptor.st_size) != 1
                or int(descriptor.st_mtime_ns) != int(before.st_mtime_ns)
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
            after = self.path.stat()
            if (
                _is_reparse(self.path)
                or int(after.st_dev) != int(before.st_dev)
                or int(after.st_ino) != int(before.st_ino)
                or int(after.st_size) != 1
                or int(after.st_mtime_ns) != int(before.st_mtime_ns)
            ):
                raise RecoveryError("coordinator carrier changed during lock")
        except (OSError, IOError) as exc:
            raise RecoveryError(f"lab coordinator is held or unavailable: {exc}") from exc
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


def snapshot_file(
    root: Path,
    relative: Path,
    label: str,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> tuple[bytes, dict[str, Any]]:
    path = Path(os.path.abspath(os.fspath(root / relative)))
    if not os.path.lexists(path):
        raise RecoveryError(f"required evidence is absent: {relative.as_posix()}")
    if _is_reparse(path) or not path.is_file():
        raise RecoveryError(f"evidence is not a regular file: {relative.as_posix()}")
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise RecoveryError(f"cannot read stable {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(raw) != after.st_size:
        raise RecoveryError(f"evidence changed while reading: {label}")
    digest = sha256_bytes(raw)
    if len(raw) != expected_bytes or digest != expected_sha256:
        raise RecoveryError(f"immutable byte/SHA pin drifted: {label}")
    return raw, {
        "path": relative.as_posix(),
        "bytes": len(raw),
        "sha256": digest,
    }


def require_absent(root: Path, relative: Path) -> dict[str, Any]:
    path = Path(os.path.abspath(os.fspath(root / relative)))
    if os.path.lexists(path):
        raise RecoveryError(f"expected absent evidence exists: {relative.as_posix()}")
    return {"path": relative.as_posix(), "absent": True}


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RecoveryError(f"{label} has a UTF-8 BOM")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"{label} is not a JSON object")
    return value


def _expected_attempt4_events() -> list[str]:
    events = [
        "recovery_started",
        "campaign_started",
        "campaign_preflight_passed",
        "pair_carried_forward",
        "pair_carried_forward",
    ]
    for _ in range(3, 10):
        events.extend(
            [
                "pair_started",
                "cold_child_returned",
                "cold_verified",
                "warm_shutdown_child_returned",
                "pair_verified",
            ]
        )
    events.extend(["pair_started", "cold_child_returned", "campaign_failed"])
    return events


def validate_lifecycle(raw: bytes) -> dict[str, Any]:
    if len(raw) != LIFECYCLE_BYTES or sha256_bytes(raw) != LIFECYCLE_SHA256:
        raise RecoveryError("attempt-004 lifecycle full-file pin drifted")
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise RecoveryError("attempt-004 lifecycle encoding/framing drifted")
    lines = raw.splitlines()
    if len(lines) != LIFECYCLE_ROWS:
        raise RecoveryError("attempt-004 lifecycle must contain exactly 65 rows")
    records: list[dict[str, Any]] = []
    previous: str | None = None
    campaign_sequences: dict[str, int] = {}
    for ledger_sequence, line in enumerate(lines, start=1):
        row = _parse_json(line, f"lifecycle row {ledger_sequence}")
        body = dict(row)
        digest = body.pop("event_sha256", None)
        campaign_id = row.get("campaign_id")
        if not isinstance(campaign_id, str):
            raise RecoveryError("lifecycle campaign id is malformed")
        campaign_sequences[campaign_id] = campaign_sequences.get(campaign_id, 0) + 1
        if (
            digest != sha256_bytes(canonical_bytes(body))
            or row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_sequence") != campaign_sequences[campaign_id]
            or row.get("previous_event_sha256") != previous
        ):
            raise RecoveryError(f"lifecycle row {ledger_sequence} identity/hash drifted")
        previous = digest
        records.append(row)
    if previous != LIFECYCLE_LAST_EVENT_SHA256:
        raise RecoveryError("attempt-004 lifecycle terminal SHA drifted")

    attempt4 = records[22:]
    if (
        len(attempt4) != 43
        or any(row.get("campaign_id") != ATTEMPT_ID for row in attempt4)
        or [row.get("event") for row in attempt4] != _expected_attempt4_events()
    ):
        raise RecoveryError("attempt-004 event schedule drifted")
    carried = attempt4[3:5]
    if [row.get("details", {}).get("pair_index") for row in carried] != [1, 2]:
        raise RecoveryError("attempt-004 carried-pair boundary drifted")
    verified_rows: dict[int, dict[str, Any]] = {}
    for row in attempt4:
        details = row.get("details") or {}
        if row.get("event") == "pair_verified":
            index = details.get("pair_index")
            if index not in range(3, 10) or details.get("recipe") != PAIR_NAMES[index]:
                raise RecoveryError("attempt-004 verified-pair identity drifted")
            if details.get("post_shutdown_state") != CLEAN_STATE:
                raise RecoveryError("attempt-004 pair did not record clean shutdown")
            verified_rows[index] = details
    if sorted(verified_rows) != list(range(3, 10)):
        raise RecoveryError("attempt-004 must contain verified pairs 3-9 exactly")
    pair10_started = attempt4[-3].get("details") or {}
    pair10_child = attempt4[-2].get("details") or {}
    if (
        pair10_started.get("pair_index") != 10
        or pair10_started.get("recipe") != PAIR10
        or pair10_child.get("pair_index") != 10
        or (pair10_child.get("outcome") or {}).get("returncode") != 0
    ):
        raise RecoveryError("attempt-004 pair10 child boundary drifted")
    terminal = attempt4[-1].get("details") or {}
    if terminal != {
        "status": "FAILED",
        "error_type": "CampaignError",
        "error": f"{PAIR10} run 1 field gate_pass drift: False != True",
        "completed_pair_count": 9,
        "carried_pair_count": 2,
        "new_verified_pair_count": 7,
        "resume_attempt_001": False,
        "resume_attempt_002": False,
        "resume_attempt_003": True,
        "failure_state": CLEAN_STATE,
        "pending_cold_child_outcome": pair10_child.get("outcome"),
        "owned_server_cleanup": {"attempted": False},
        "stopped_without_force_or_additional_render": True,
    }:
        raise RecoveryError("attempt-004 terminal failure semantics drifted")
    sources = (attempt4[1].get("details") or {}).get("sources")
    if not isinstance(sources, dict):
        raise RecoveryError("attempt-004 lifecycle source map is absent")
    return {
        "records": records,
        "attempt4_records": attempt4,
        "sources": sources,
        "verified_rows": verified_rows,
        "prefix": {
            "path": LIFECYCLE.as_posix(),
            "bytes": LIFECYCLE_BYTES,
            "sha256": LIFECYCLE_SHA256,
            "row_count": LIFECYCLE_ROWS,
            "last_event_sha256": LIFECYCLE_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
        },
        "terminal_failure": {
            "status": "FAILED",
            "error": terminal["error"],
            "completed_pair_count": 9,
            "carried_pair_count": 2,
            "new_verified_pair_count": 7,
            "failure_state": CLEAN_STATE,
            "owned_server_cleanup": {"attempted": False},
            "stopped_without_force_or_additional_render": True,
        },
    }


def _snapshot_sources(
    root: Path, lifecycle_sources: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, bytes]]:
    snapshots: dict[str, Any] = {}
    raws: dict[str, bytes] = {}
    for label, (relative, size, digest, lifecycle_label) in SOURCE_PINS.items():
        raw, snapshot = snapshot_file(
            root,
            relative,
            label,
            expected_bytes=size,
            expected_sha256=digest,
        )
        recorded = lifecycle_sources.get(lifecycle_label) or {}
        if recorded.get("bytes") != size or recorded.get("sha256") != digest:
            raise RecoveryError(f"attempt-004 lifecycle source pin drifted: {label}")
        snapshots[label] = snapshot
        raws[label] = raw
    return snapshots, raws


def _snapshot_fixed(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    snapshots: dict[str, Any] = {}
    raws: dict[str, bytes] = {}
    for label, (relative, size, digest) in FILE_PINS.items():
        raw, snapshot = snapshot_file(
            root,
            relative,
            label,
            expected_bytes=size,
            expected_sha256=digest,
        )
        snapshots[label] = snapshot
        raws[label] = raw
    if raws["pair10_failed_run1"] != raws["pair10_failed_alias"]:
        raise RecoveryError("pair10 failed alias is not byte-identical to run1")
    return snapshots, raws


def validate_superseded_recovery(raw: bytes) -> dict[str, Any]:
    receipt = _parse_json(raw, "superseded attempt-004 recovery receipt")
    policy = receipt.get("recovery_policy") or {}
    pair11 = policy.get("pair11") or {}
    if (
        receipt.get("receipt_kind")
        != "h3-unconditioned-music-attempt-004-timeout-recovery"
        or receipt.get("recovery_id") != SUPERSEDED_RECOVERY_ID
        or receipt.get("failed_campaign_id") != ATTEMPT_ID
        or receipt.get("resume_campaign_id") != RESUME_ID
        or policy.get("carry_pair_indices") != list(range(1, 10))
        or policy.get("execute_pair_indices") != [10, 11]
        or policy.get("new_leg_count") != 4
        or pair11.get("recipe") != ERRONEOUS_PAIR11
    ):
        raise RecoveryError("superseded recovery error boundary drifted")
    if pair11.get("recipe") == PAIR11:
        raise RecoveryError("superseded recovery unexpectedly names canonical pair11")
    return {
        "recovery_id": SUPERSEDED_RECOVERY_ID,
        "classification": "UNUSABLE_RESUME_AUTHORITY",
        "exact_error": {
            "field": "recovery_policy.pair11.recipe",
            "recorded": ERRONEOUS_PAIR11,
            "required": PAIR11,
        },
        "superseded_by_recovery_id": RECOVERY_ID,
        "must_not_authorize_render": True,
        "must_not_be_deleted_or_overwritten": True,
    }


def validate_operator_and_timeout(raws: Mapping[str, bytes]) -> dict[str, Any]:
    try:
        stdout = raws["operator_stdout"].decode("utf-8")
        stderr = raws["operator_stderr"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecoveryError("attempt-004 operator stream is not UTF-8") from exc
    expected_error = (
        f"[H3 MUSIC CAMPAIGN FAILED] CampaignError: {PAIR10} run 1 field "
        "gate_pass drift: False != True"
    )
    if stderr.splitlines() != [expected_error]:
        raise RecoveryError("attempt-004 operator stderr drifted")
    for marker in (
        "Wall Clock:    1800.0 s",
        "Status:        TIMEOUT (exceeded 1800s; owned server shutdown proved)",
        "[LOCK] Released .gpu.lock and coordinator",
    ):
        if marker not in stdout:
            raise RecoveryError("attempt-004 operator timeout transcript drifted")
    receipt = _parse_json(raws["pair10_failed_run1"], "pair10 failed run1")
    required = {
        "receipt_schema_version": 3,
        "recipe": PAIR10,
        "run_number": 1,
        "run_count": 1,
        "config_run_count": 1,
        "status": "TIMEOUT (exceeded 1800s; owned server shutdown proved)",
        "gate_pass": False,
        "pass": False,
        "warm_pass": False,
        "duration_s": 1800.0,
        "peak_vram_gb": 10.69,
        "baseline_vram_gb": 1.97,
        "output_path": "",
        "prompt_id": "0373b418-2b93-4d2d-97bf-fa518010adf0",
        "run_identity_sha256": "feff83eaa67a24f7e9becc7d0b14ac304b6c95213819586cb504937708fc9dbf",
        "queued_prompt_sha256": "5f2efb8f55e329ae4334e9dae988e1e62fa84cd684775d0d27f4eff8ad52b92b",
        "final_server_instance": {},
    }
    for field, expected in required.items():
        if receipt.get(field) != expected:
            raise RecoveryError(f"pair10 failed run1 field drifted: {field}")
    cleanup = receipt.get("orphan_cleanup") or {}
    if (
        cleanup.get("pid") != 38_876
        or cleanup.get("process_exited") is not True
        or cleanup.get("listener_exited") is not True
        or cleanup.get("receipt_removed") is not True
        or cleanup.get("success") is not True
    ):
        raise RecoveryError("pair10 owned-server shutdown proof drifted")
    manager = receipt.get("manager_offline_probe") or {}
    if (
        (manager.get("pre_queue") or {}).get("valid") is not True
        or (manager.get("post_render") or {}).get("valid") is not False
        or b"[ComfyUI-Manager] network_mode: offline" not in raws["pair10_manager_log"]
        or b"Prompt executed in" in raws["pair10_manager_log"]
    ):
        raise RecoveryError("pair10 Manager offline/timeout evidence drifted")
    return {
        "operator_stderr_terminal_line": expected_error,
        "timeout_seconds": 1800,
        "sampling_steps_completed": 20,
        "artifact_finalized": False,
        "qualifying_cold_leg": False,
        "receipt": receipt,
    }


def _module_from_bytes(name: str, path: Path, raw: bytes) -> ModuleType:
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(path))
    if spec is None:
        raise RecoveryError(f"cannot create frozen module spec: {name}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


@contextmanager
def frozen_campaign_modules(
    root: Path, source_raws: Mapping[str, bytes]
) -> Iterator[ModuleType]:
    names = (
        "h3_manager_offline_guard",
        "run_h3_canonical_campaign",
        "_h3_attempt4_frozen_campaign",
    )
    previous = {name: sys.modules.get(name) for name in names}
    try:
        _module_from_bytes(
            names[0], root / SOURCE_PINS["manager_guard"][0], source_raws["manager_guard"]
        )
        _module_from_bytes(
            names[1],
            root / SOURCE_PINS["canonical_campaign"][0],
            source_raws["canonical_campaign"],
        )
        frozen = _module_from_bytes(
            names[2],
            root / SOURCE_PINS["attempt4_campaign"][0],
            source_raws["attempt4_campaign"],
        )
        yield frozen
    finally:
        for name in reversed(names):
            prior = previous[name]
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior


def verify_completed_pairs(
    root: Path,
    lifecycle: Mapping[str, Any],
    source_raws: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    if Path(os.path.abspath(os.fspath(root))) != ROOT:
        raise RecoveryError("full pair verification is fixed to the real lab root")
    sources = lifecycle["sources"]
    records = lifecycle["attempt4_records"]
    with frozen_campaign_modules(root, source_raws) as campaign:
        specs = campaign.load_specs()
        if (
            len(specs) != 11
            or [spec.name for spec in specs]
            != [PAIR_NAMES[index] for index in range(1, 12)]
            or specs[9].name != PAIR10
            or specs[9].frames != 192
            or specs[10].name != PAIR11
            or specs[10].frames != 277
            or specs[10].sha256 != PAIR11_RECIPE_SHA256
        ):
            raise RecoveryError("canonical eleven-spec campaign tail drifted")
        preserved = campaign.verify_attempt3_preserved_evidence()
        pairs = {1: preserved["pair1"], 2: preserved["pair2"]}
        recorded = {
            int(row["details"]["pair_index"]): row["details"]["pair"]
            for row in records
            if row.get("event") == "pair_verified"
        }
        carried = {
            int(row["details"]["pair_index"]): row["details"]["pair"]
            for row in records
            if row.get("event") == "pair_carried_forward"
        }
        if pairs[1] != carried.get(1) or pairs[2] != carried.get(2):
            raise RecoveryError("attempt-004 carried pair evidence drifted")
        for index in range(3, 10):
            spec = specs[index - 1]
            pair = campaign.verify_pair(
                spec,
                index,
                ATTEMPT_ID,
                sources,
                campaign.pair_log_path(spec, index, ATTEMPT_ID),
            )
            if pair != recorded.get(index):
                raise RecoveryError(f"pair {index} differs from lifecycle verification")
            pairs[index] = pair
        results = []
        for index in range(1, 10):
            pair = pairs[index]
            digest = sha256_bytes(campaign.canon.canonical_bytes(pair))
            if digest != PAIR_RESULT_SHA256S[index]:
                raise RecoveryError(f"pair {index} full-verifier hash drifted")
            source_campaign = (
                f"{BASE_ID}-attempt-002"
                if index == 1
                else (f"{BASE_ID}-attempt-003" if index == 2 else ATTEMPT_ID)
            )
            results.append(
                {
                    "pair_index": index,
                    "recipe": PAIR_NAMES[index],
                    "source_campaign_id": source_campaign,
                    "canonical_result_sha256": digest,
                    "cold_receipt_sha256": pair["cold"]["receipt_sha256"],
                    "warm_receipt_sha256": pair["warm"]["receipt_sha256"],
                    "cold_artifact_sha256": pair["cold"]["artifact"]["sha256"],
                    "warm_artifact_sha256": pair["warm"]["artifact"]["sha256"],
                    "manager_log_sha256": pair["final_manager_log"]["log"]["sha256"],
                    "status": "MACHINE_COMPLETE",
                    "human_judgment": "PENDING_HUMAN",
                }
            )
        return results


def recovery_policy() -> dict[str, Any]:
    return {
        "resume_campaign_id": RESUME_ID,
        "carry_pair_indices": list(range(1, 10)),
        "execute_pair_indices": [10, 11],
        "new_leg_count": 4,
        "pair10": {
            "recipe": PAIR10,
            "preserved_noncertifying_run_numbers": [1],
            "cold_run_number": 2,
            "cold_config_run_count": 1,
            "warm_run_number": 3,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2, 3],
        },
        "pair11": {
            "recipe": PAIR11,
            "preserved_noncertifying_run_numbers": [],
            "cold_run_number": 1,
            "cold_config_run_count": 1,
            "warm_run_number": 2,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2],
        },
        "all_other_pair_execution_forbidden": True,
        "attempt004_run1_must_not_be_reclassified_or_overwritten": True,
        "new_pair10_cold_and_warm_must_share_one_new_owned_server": True,
        "new_pair11_cold_and_warm_must_share_one_new_owned_server": True,
    }


def build_receipt(root: Path = ROOT) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    lifecycle_raw, lifecycle_snapshot = snapshot_file(
        root,
        LIFECYCLE,
        "attempt-004 lifecycle",
        expected_bytes=LIFECYCLE_BYTES,
        expected_sha256=LIFECYCLE_SHA256,
    )
    lifecycle = validate_lifecycle(lifecycle_raw)
    source_snapshots, source_raws = _snapshot_sources(root, lifecycle["sources"])
    fixed, fixed_raws = _snapshot_fixed(root)
    superseded = validate_superseded_recovery(fixed_raws["superseded_recovery"])
    timeout = validate_operator_and_timeout(fixed_raws)
    absences = [require_absent(root, relative) for relative in ABSENT_PATHS]
    pairs = verify_completed_pairs(root, lifecycle, source_raws)
    return {
        "receipt_schema_version": 1,
        "receipt_kind": (
            "h3-unconditioned-music-attempt-004-timeout-recovery-correction"
        ),
        "recovery_id": RECOVERY_ID,
        "failed_campaign_id": ATTEMPT_ID,
        "resume_campaign_id": RESUME_ID,
        "status": (
            "ATTEMPT_004_FAILED_PAIRS_1_THROUGH_9_MACHINE_COMPLETE_CORRECTED"
        ),
        "success": True,
        "recording_time": {
            "included": False,
            "reason": "deterministic immutable-evidence receipt",
        },
        "immutable_evidence": {
            "superseded_recovery": {
                "snapshot": fixed["superseded_recovery"],
                **superseded,
            },
            "lifecycle": {
                "snapshot": lifecycle_snapshot,
                "prefix": lifecycle["prefix"],
                "terminal_failure": lifecycle["terminal_failure"],
            },
            "sources": source_snapshots,
            "operator_streams": {
                "stdout": fixed["operator_stdout"],
                "stderr": fixed["operator_stderr"],
                "launch_receipt_absent": absences[0],
            },
            "pair10_failed_run1": {
                "receipt": fixed["pair10_failed_run1"],
                "alias": fixed["pair10_failed_alias"],
                "manager_log": fixed["pair10_manager_log"],
                "classification": {
                    key: value for key, value in timeout.items() if key != "receipt"
                },
                "receipt_fields": timeout["receipt"],
            },
            "required_absences": absences,
        },
        "full_pair_verification": pairs,
        "canonical_unfinished_specs": [
            {
                "pair_index": 10,
                "recipe": PAIR10,
                "frames": 192,
            },
            {
                "pair_index": 11,
                "recipe": PAIR11,
                "recipe_sha256": PAIR11_RECIPE_SHA256,
                "frames": 277,
            },
        ],
        "certification_effect": {
            "superseded_recovery_usable_as_authority": False,
            "attempt004_status": "FAILED",
            "pairs_1_through_9_machine_complete": True,
            "pair10_run1_machine_pair_leg": False,
            "pair10_run1_historical_orphan_only": True,
            "pair10_machine_complete": False,
            "pair11_machine_complete": False,
            "human_judgment": "PENDING_HUMAN",
            "campaign_complete_granted": False,
            "promotion_or_study_pass_granted": False,
        },
        "recovery_policy": recovery_policy(),
        "anti_mutation": {
            "superseded_recovery_deleted_or_overwritten": False,
            "failed_lifecycle_appended_or_rewritten": False,
            "existing_receipt_artifact_or_log_modified": False,
            "operator_stream_modified": False,
            "process_listener_lock_or_gpu_queried": False,
            "server_contacted": False,
            "render_started": False,
            "network_used": False,
            "otr_touched": False,
            "recorder_source_self_hash_included": False,
        },
    }


@contextmanager
def held_coordinator(root: Path) -> Iterator[ExistingCoordinatorMutex]:
    mutex = ExistingCoordinatorMutex(root)
    mutex.acquire()
    try:
        yield mutex
    finally:
        mutex.release()


def exclusive_write(
    root: Path,
    payload: Mapping[str, Any],
    *,
    coordinator: ExistingCoordinatorMutex,
) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(root)))
    if coordinator.acquired is not True:
        raise RecoveryError("recovery publication requires the held coordinator")
    destination = root / RECOVERY
    encoded = receipt_bytes(payload)
    parent = destination.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=False)
    if _is_reparse(parent) or not parent.is_dir():
        raise RecoveryError("recovery parent is not a real directory")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
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
        raise RecoveryError("published recovery receipt differs from candidate")
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
        with held_coordinator(root) as coordinator:
            payload = build_receipt(root)
            final_payload = build_receipt(root)
            if receipt_bytes(final_payload) != receipt_bytes(payload):
                raise RecoveryError("recovery evidence changed before publication")
            published = exclusive_write(root, payload, coordinator=coordinator)
        if not args.quiet:
            print(json.dumps({"status": "CREATED", "recovery_receipt": published}, indent=2))
        return 0
    except Exception as exc:
        print(f"[H3 MUSIC RECOVERY4 FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
