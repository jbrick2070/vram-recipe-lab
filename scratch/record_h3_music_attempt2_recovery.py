#!/usr/bin/env python3
"""Record the append-only recovery companion for H3 music attempt-002.

The default mode is read-only.  It validates the complete frozen attempt-002
lifecycle and every pair-1 evidence surface, loads the exact hash-pinned
attempt-002 campaign source, and invokes that source's full ``verify_pair``
implementation for run2 cold + run3 warm.  It also observes local cleanup
postconditions while holding the pre-existing coordinator mutex.

``--write`` is the sole write path.  It creates one fixed recovery receipt with
``O_CREAT | O_EXCL`` and never appends or rewrites the failed lifecycle.  This
module does not boot or contact ComfyUI, submit a prompt, render, or use the
network.  Return code 120 remains ``UNKNOWN_UNPROVED`` because the child outcome
did not capture stdout/stderr and no causal evidence exists in the ledger.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
from types import ModuleType
from typing import Any, Callable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]

ATTEMPT1_ID = "h3music-20260810T023023Z-97ca44b2"
ATTEMPT2_ID = f"{ATTEMPT1_ID}-attempt-002"
ATTEMPT3_ID = f"{ATTEMPT1_ID}-attempt-003"
RECOVERY_ID = f"{ATTEMPT2_ID}-recovery-001"

CONTROL_NAME = "h3_unconditioned_music_scene_seed42_f124"
LIFECYCLE = Path("results/h3_unconditioned_music_campaign/lifecycle.jsonl")
RECOVERY1 = Path(
    "results/h3_unconditioned_music_campaign/recoveries/"
    f"{ATTEMPT1_ID}-manual-cleanup.json"
)
RUN1 = Path(f"results/{CONTROL_NAME}_run1.json")
RUN2 = Path(f"results/{CONTROL_NAME}_run2.json")
RUN3 = Path(f"results/{CONTROL_NAME}_run3.json")
ALIAS = Path(f"results/{CONTROL_NAME}.json")
ATTEMPT2_LOG = Path(
    "results/h3_unconditioned_music_campaign/server_logs/"
    f"{ATTEMPT2_ID}-p01-{CONTROL_NAME}.log"
)
ARTIFACT1 = Path(f"outputs/{CONTROL_NAME}_out_00001_.mp4")
ARTIFACT2 = Path(f"outputs/{CONTROL_NAME}_out_00002_.mp4")
ARTIFACT3 = Path(f"outputs/{CONTROL_NAME}_out_00003_.mp4")
RECOVERY = Path(
    "results/h3_unconditioned_music_campaign/recoveries/"
    f"{ATTEMPT2_ID}-return120-recovery.json"
)

LIFECYCLE_BYTES = 110_592
LIFECYCLE_SHA256 = (
    "f95b952e97507761d474f6f3701bdd46f69a569c612a864c1a53d5d1b71686f4"
)
ATTEMPT1_PREFIX_BYTES = 28_706
ATTEMPT1_PREFIX_SHA256 = (
    "fed5a70a832ad4bc9a985e5c136d583ad7338146164eef89bf3bbe3fd917c2cf"
)
ATTEMPT1_LAST_EVENT_SHA256 = (
    "20ec57fc403d782ee292c3bfbd75b70c3d5466fca620f255e8aefaeb5c0bea1b"
)
ATTEMPT2_LAST_EVENT_SHA256 = (
    "9ce05976ffa45551bb3bc1dbb34d1bdc1f50c81ace67d51fcea46126279ec857"
)

# Sequence, campaign id, campaign sequence, event, exact canonical event hash.
EXPECTED_LIFECYCLE_ROWS: tuple[tuple[int, str, int, str, str], ...] = (
    (1, ATTEMPT1_ID, 1, "campaign_started", "f01b06798f7529cf9e38f734a1481438bbada3d57faa3774c0cf14d6cdca9ef0"),
    (2, ATTEMPT1_ID, 2, "campaign_preflight_passed", "006da69b6ad926742a2cd2d0a0c7abddb63a04d0bccb581dcc32a0db9efa717c"),
    (3, ATTEMPT1_ID, 3, "pair_started", "63ee32714a4228ccde67ae66da6c8ebe997442bc9fbb26948bf918786965d715"),
    (4, ATTEMPT1_ID, 4, "cold_child_returned", "32a61263ef36a5549512c4c020d696e520ac84d1c9760bb305b55d55e5ca4d4a"),
    (5, ATTEMPT1_ID, 5, "campaign_failed", ATTEMPT1_LAST_EVENT_SHA256),
    (6, ATTEMPT2_ID, 1, "recovery_started", "478037f4dc52adff8b4814a1e424a2c64a04284f33867435f176d1a1244c0053"),
    (7, ATTEMPT2_ID, 2, "campaign_started", "6e8e66fcf897d50a82232647870539d02b1bb847aa9d0de9b83da2d8f7d1683e"),
    (8, ATTEMPT2_ID, 3, "campaign_preflight_passed", "f94cf3db25fb9c4fb0cf2439d966fcb1b588365171ec28fba7c8df5db1eb2fca"),
    (9, ATTEMPT2_ID, 4, "pair_started", "4d25afdb53d1142775b6254ff55ed1b3e0a45cc741b9cd5878bbb65f3349f6a7"),
    (10, ATTEMPT2_ID, 5, "cold_child_returned", "4f52b4f8665729ddce320d506911811327be07a0c06dc55ff82abfd585a643df"),
    (11, ATTEMPT2_ID, 6, "cold_verified", "9b07cdf20a1022eeb0b807027713ff97bcd01f2b878ab441be4fddb9e86ba094"),
    (12, ATTEMPT2_ID, 7, "warm_shutdown_child_returned", "8ad4116ad15e1faeb8fa1296a651fe601e14e99eb23e0ceaa06977e91cddd9cc"),
    (13, ATTEMPT2_ID, 8, "campaign_failed", ATTEMPT2_LAST_EVENT_SHA256),
)

RECOVERY1_BYTES = 7_610
RECOVERY1_SHA256 = (
    "e153ba610110e1fb5a637d1ddfa4f0144f60982e88be018d08534f7ddf4371df"
)
RUN_PINS: dict[str, tuple[Path, int, str]] = {
    "run1": (RUN1, 63_281, "c1295c435e25419ed771aae044d33806b55e9237e594dcdd6716be519a602b8f"),
    "run2": (RUN2, 63_350, "30d6dbc37b906a25909826e8ef68862af4952c7597b793a76982db1a9ebe25cd"),
    "run3": (RUN3, 64_162, "e12a76ebc4e14bb42d2d6f44466364894a6ce65a70b4cbda1057d55cb976829a"),
}
ALIAS_BYTES = 64_162
ALIAS_SHA256 = RUN_PINS["run3"][2]
ATTEMPT2_LOG_BYTES = 25_081
ATTEMPT2_LOG_SHA256 = (
    "1ab05e73202b2e77a5dfb4f4cf350491e1e9a0d0d6c4083204d855be88122b7d"
)
ARTIFACT_BYTES = 909_151
ARTIFACT_SHA256 = (
    "b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed"
)
ARTIFACT_PINS: dict[str, tuple[Path, int, str]] = {
    "run1": (ARTIFACT1, ARTIFACT_BYTES, ARTIFACT_SHA256),
    "run2": (ARTIFACT2, ARTIFACT_BYTES, ARTIFACT_SHA256),
    "run3": (ARTIFACT3, ARTIFACT_BYTES, ARTIFACT_SHA256),
}

PAIR_SERVER_IDENTITY = {
    "serving_pid": 6_824,
    "process_create_time": 1_786_332_252.100749,
}
RUN_IDENTITY_SHA256 = (
    "aaeb2daca2cb317a03ac6437813f9cf958819c44f479927bd0d91934c13d7f01"
)
COLD_QUEUED_SHA256 = (
    "7d49d4ebe51a3cf038e63b19801b3e2f80ec8f536bc955b9c99ddabf97fbb828"
)
WARM_QUEUED_SHA256 = (
    "3f584a9ea76ad1d5b0b5c397ae335ed748c7e65a38d8fdc43124d0b9beb0cf4a"
)
ATTEMPT2_ERROR = f"{CONTROL_NAME} warm child returned 120"

# The new recorder is captured dynamically in the eventual externally pinned
# receipt.  Every pre-existing source that gave attempt-002 its meaning is both
# literal-pinned here and cross-checked against lifecycle row 7 when applicable.
SOURCE_PINS: dict[str, tuple[Path, int, str, str | None]] = {
    "attempt2_campaign": (
        Path("scratch/run_h3_unconditioned_music_campaign.py"),
        74_609,
        "8aec4108559618963b1210ad4a58cdb9d28b55853137746577c4db7da3703e97",
        "campaign",
    ),
    "canonical_campaign_helper": (
        Path("scratch/run_h3_canonical_campaign.py"),
        77_526,
        "0c3246a435d0c9f208ecbca4bc77b172e2a1e3793cbb96332a2e41781fd5cb38",
        "campaign_canonical",
    ),
    "run_recipe": (
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
    "manager_guard": (
        Path("scratch/h3_manager_offline_guard.py"),
        39_609,
        "1b06e5662e9bad8d17aac05d31e393683f3cd450dadbeb86c3763c3a47b2a821",
        "manager_guard",
    ),
    "attempt1_recovery_recorder": (
        Path("scratch/record_h3_music_recovery.py"),
        27_204,
        "7ecc98fa6a9157a1080406d556f0b1df055b0ac00f89367753bbe421c7a84b38",
        "recovery_recorder",
    ),
    "attempt1_recovery_receipt": (
        RECOVERY1,
        RECOVERY1_BYTES,
        RECOVERY1_SHA256,
        None,
    ),
}
RECORDER_SOURCE = Path("scratch/record_h3_music_attempt2_recovery.py")

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
    """Frozen evidence, source provenance, or cleanup state is invalid."""


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
    before_identity = (
        int(before.st_dev), int(before.st_ino), int(before.st_size), int(before.st_mtime_ns)
    )
    after_identity = (
        int(after.st_dev), int(after.st_ino), int(after.st_size), int(after.st_mtime_ns)
    )
    if before_identity != after_identity or len(raw) != int(after.st_size):
        raise RecoveryError(f"evidence changed while being read: {display_path}")
    return raw, {
        "path": display_path,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }


def _pinned(
    root: Path,
    relative: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> tuple[bytes, dict[str, Any]]:
    raw, snapshot = _snapshot(root / relative, relative.as_posix())
    if snapshot["bytes"] != expected_bytes:
        raise RecoveryError(f"immutable byte count drift: {relative.as_posix()}")
    if snapshot["sha256"] != expected_sha256:
        raise RecoveryError(f"immutable SHA drift: {relative.as_posix()}")
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


def _samefile(root: Path, left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(root / left, root / right)
    except OSError as exc:
        raise RecoveryError(
            f"cannot prove file independence: {left.as_posix()} vs {right.as_posix()}: {exc}"
        ) from exc


def _require_pairwise_distinct(root: Path, paths: Sequence[Path], label: str) -> None:
    for left_index, left in enumerate(paths):
        for right in paths[left_index + 1 :]:
            if _samefile(root, left, right):
                raise RecoveryError(
                    f"{label} must be distinct files, not hardlinks: "
                    f"{left.as_posix()} vs {right.as_posix()}"
                )


def _exact_schedule() -> dict[str, Any]:
    return {
        "cold_run_number": 2,
        "cold_config_run_count": 1,
        "warm_run_number": 3,
        "warm_config_run_count": 2,
        "allowed_run_numbers": [1, 2, 3],
        "preserved_historical_run_numbers": [1],
        "reason": (
            "attempt-001 run1 is valid cold evidence, but its server ended; "
            "run2 must therefore be cold on a new server and run3 warm on that same server"
        ),
    }


def validate_lifecycle(raw: bytes) -> dict[str, Any]:
    if len(raw) != LIFECYCLE_BYTES or sha256_bytes(raw) != LIFECYCLE_SHA256:
        raise RecoveryError("attempt-002 lifecycle full-file pin drifted")
    if not raw.endswith(b"\n"):
        raise RecoveryError("attempt-002 lifecycle has a partial trailing row")
    if sha256_bytes(raw[:ATTEMPT1_PREFIX_BYTES]) != ATTEMPT1_PREFIX_SHA256:
        raise RecoveryError("attempt-001 lifecycle prefix SHA drifted")
    if not raw[:ATTEMPT1_PREFIX_BYTES].endswith(b"\n"):
        raise RecoveryError("attempt-001 prefix no longer ends at a row boundary")

    lines = raw.splitlines()
    if len(lines) != len(EXPECTED_LIFECYCLE_ROWS):
        raise RecoveryError("attempt-002 lifecycle must contain exactly thirteen rows")
    records: list[dict[str, Any]] = []
    previous: str | None = None
    for line, expected in zip(lines, EXPECTED_LIFECYCLE_ROWS, strict=True):
        sequence, campaign_id, campaign_sequence, event, event_sha = expected
        row = _parse_json(line, f"lifecycle row {sequence}")
        body = dict(row)
        recorded_sha = body.pop("event_sha256", None)
        if recorded_sha != sha256_bytes(canonical_bytes(body)):
            raise RecoveryError(f"lifecycle row {sequence} canonical event SHA mismatch")
        actual = (
            row.get("ledger_sequence"),
            row.get("campaign_id"),
            row.get("campaign_sequence"),
            row.get("event"),
            recorded_sha,
        )
        if actual != expected:
            raise RecoveryError(f"lifecycle row {sequence} identity drifted")
        if row.get("previous_event_sha256") != previous:
            raise RecoveryError(f"lifecycle row {sequence} breaks the hash chain")
        previous = recorded_sha
        records.append(row)

    recovery_started = records[5].get("details") or {}
    recovery1 = recovery_started.get("recovery_receipt") or {}
    if (
        recovery_started.get("failed_campaign_id") != ATTEMPT1_ID
        or recovery1.get("sha256") != RECOVERY1_SHA256
        or recovery1.get("bytes") != RECOVERY1_BYTES
        or recovery1.get("recovery_id") != f"{ATTEMPT1_ID}-recovery-001"
        or recovery_started.get("resume_policy") != _exact_schedule()
    ):
        raise RecoveryError("attempt-002 recovery-start provenance drifted")

    sources = (records[6].get("details") or {}).get("sources") or {}
    if not isinstance(sources, dict):
        raise RecoveryError("attempt-002 campaign source evidence is absent")
    for _, (relative, expected_bytes, expected_sha, lifecycle_label) in SOURCE_PINS.items():
        if lifecycle_label is None:
            continue
        recorded = sources.get(lifecycle_label) or {}
        if (
            recorded.get("bytes") != expected_bytes
            or recorded.get("sha256") != expected_sha
            or Path(str(recorded.get("path") or "")).name != relative.name
        ):
            raise RecoveryError(
                f"attempt-002 lifecycle source pin drifted: {lifecycle_label}"
            )

    preflight = records[7].get("details") or {}
    if (
        preflight.get("histories_match_attempt_plan") is not True
        or preflight.get("state")
        != {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_pid_receipt": None,
            "server_pid_create_time": None,
            "queue_quarantine_exists": False,
            "listener_pids_8199": [],
            "expected_server_identity_live": False,
        }
    ):
        raise RecoveryError("attempt-002 preflight evidence drifted")

    pair_started = records[8].get("details") or {}
    if (
        pair_started.get("pair_index") != 1
        or pair_started.get("recipe") != CONTROL_NAME
        or pair_started.get("receipt_schedule") != _exact_schedule()
        or Path(str(pair_started.get("manager_log") or "")).name != ATTEMPT2_LOG.name
    ):
        raise RecoveryError("attempt-002 pair-start schedule drifted")

    cold_outcome = ((records[9].get("details") or {}).get("outcome") or {})
    if (
        cold_outcome.get("returncode") != 0
        or cold_outcome.get("runner_pid") != 46_420
        or not math.isclose(
            float(cold_outcome.get("runner_create_time", -1)),
            1_786_332_249.064603,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        or cold_outcome.get("ownership_monitor_errors") != []
        or len(cold_outcome.get("descendant_server_instances") or []) != 1
    ):
        raise RecoveryError("attempt-002 cold child outcome drifted")
    cold_server = cold_outcome["descendant_server_instances"][0]
    if (
        cold_server.get("serving_pid") != PAIR_SERVER_IDENTITY["serving_pid"]
        or not math.isclose(
            float(cold_server.get("process_create_time", -1)),
            PAIR_SERVER_IDENTITY["process_create_time"],
            rel_tol=0.0,
            abs_tol=1e-6,
        )
    ):
        raise RecoveryError("attempt-002 cold child server identity drifted")

    cold_verified = (records[10].get("details") or {}).get("cold") or {}
    if (
        cold_verified.get("receipt_sha256") != RUN_PINS["run2"][2]
        or (cold_verified.get("artifact") or {}).get("sha256") != ARTIFACT_SHA256
        or cold_verified.get("server_instance") != PAIR_SERVER_IDENTITY
        or cold_verified.get("run_identity_sha256") != RUN_IDENTITY_SHA256
        or cold_verified.get("queued_prompt_sha256") != COLD_QUEUED_SHA256
    ):
        raise RecoveryError("attempt-002 cold-verification row drifted")

    warm_outcome = ((records[11].get("details") or {}).get("outcome") or {})
    if (
        warm_outcome
        != {
            "returncode": 120,
            "runner_pid": 48_864,
            "runner_create_time": 1_786_333_170.495429,
            "descendant_server_instances": [],
            "ownership_monitor_errors": [],
        }
    ):
        raise RecoveryError("attempt-002 warm child return-120 evidence drifted")

    terminal = records[12].get("details") or {}
    expected_clean = {
        "gpu_lock_exists": False,
        "suite_lock_exists": False,
        "server_pid_receipt_exists": False,
        "server_pid_receipt": None,
        "server_pid_create_time": None,
        "queue_quarantine_exists": False,
        "listener_pids_8199": [],
        "expected_server_identity_live": False,
    }
    if terminal != {
        "status": "FAILED",
        "error_type": "CampaignError",
        "error": ATTEMPT2_ERROR,
        "completed_pair_count": 0,
        "pending_cold_child_outcome": None,
        "owned_server_cleanup": {"attempted": False},
        "failure_state": expected_clean,
        "stopped_without_force_or_additional_render": True,
    }:
        raise RecoveryError("attempt-002 terminal failure evidence drifted")

    return {
        "current_prefix": {
            "path": LIFECYCLE.as_posix(),
            "bytes": LIFECYCLE_BYTES,
            "sha256": LIFECYCLE_SHA256,
            "row_count": 13,
            "last_event_sha256": ATTEMPT2_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
        },
        "attempt1_prefix": {
            "bytes": ATTEMPT1_PREFIX_BYTES,
            "sha256": ATTEMPT1_PREFIX_SHA256,
            "row_count": 5,
            "last_event_sha256": ATTEMPT1_LAST_EVENT_SHA256,
        },
        "attempt2_terminal_failure": {
            "status": "FAILED",
            "error_type": "CampaignError",
            "error": ATTEMPT2_ERROR,
            "completed_pair_count": 0,
            "warm_child_returncode": 120,
            "warm_child_outcome_event_sha256": EXPECTED_LIFECYCLE_ROWS[11][4],
            "terminal_event_sha256": ATTEMPT2_LAST_EVENT_SHA256,
            "owned_server_cleanup": {"attempted": False},
            "stopped_without_force_or_additional_render": True,
        },
        "attempt2_sources": sources,
    }


def _receipt_disposition(receipt: Mapping[str, Any], run_number: int) -> dict[str, Any]:
    expected = {
        1: (1, "PASS (cold)", True, True, False, False, 1.65, 7.58, 908.8),
        2: (1, "PASS (cold)", True, True, False, False, 1.93, 7.63, 904.4),
        3: (2, "PASS", True, True, True, True, 3.49, 7.88, 895.1),
    }[run_number]
    actual = (
        receipt.get("config_run_count"),
        receipt.get("status"),
        receipt.get("gate_pass"),
        receipt.get("valid_measurement"),
        receipt.get("pass"),
        receipt.get("warm_pass"),
        receipt.get("baseline_vram_gb"),
        receipt.get("peak_vram_gb"),
        receipt.get("duration_s"),
    )
    artifact_path = ARTIFACT_PINS[f"run{run_number}"][0]
    expected_identity = (
        {"serving_pid": 51_136, "process_create_time": 1_786_329_027.50907}
        if run_number == 1
        else PAIR_SERVER_IDENTITY
    )
    expected_run_identity = (
        "11e67d4d6316c81c7d4bae1cd677656c2a4553c03df87be032269ff2ce65d93a"
        if run_number == 1
        else RUN_IDENTITY_SHA256
    )
    expected_queued = {
        1: "d2d41c7f137253778f2d8ce7fc06656d238364344a2263ea572db73bd069f3bd",
        2: COLD_QUEUED_SHA256,
        3: WARM_QUEUED_SHA256,
    }[run_number]
    if (
        receipt.get("run_number") != run_number
        or receipt.get("run_count") != run_number
        or actual != expected
        or receipt.get("server_instance") != expected_identity
        or receipt.get("final_server_instance") != expected_identity
        or receipt.get("run_identity_sha256") != expected_run_identity
        or receipt.get("queued_prompt_sha256") != expected_queued
        or receipt.get("output_path") != artifact_path.name
        or receipt.get("artifact_bytes") != ARTIFACT_BYTES
        or receipt.get("artifact_sha256") != ARTIFACT_SHA256
    ):
        raise RecoveryError(f"run{run_number} receipt semantic disposition drifted")
    return {
        "run_number": run_number,
        "config_run_count": expected[0],
        "status": expected[1],
        "gate_pass": expected[2],
        "valid_measurement": expected[3],
        "pass": expected[4],
        "warm_pass": expected[5],
        "baseline_vram_gb": expected[6],
        "peak_vram_gb": expected[7],
        "duration_s": expected[8],
        "server_instance": expected_identity,
        "run_identity_sha256": expected_run_identity,
        "queued_prompt_sha256": expected_queued,
        "artifact_sha256": ARTIFACT_SHA256,
    }


def collect_immutable_evidence(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    lifecycle_raw, _ = _pinned(root, LIFECYCLE, LIFECYCLE_BYTES, LIFECYCLE_SHA256)
    lifecycle = validate_lifecycle(lifecycle_raw)

    recovery1_raw, recovery1_snapshot = _pinned(
        root, RECOVERY1, RECOVERY1_BYTES, RECOVERY1_SHA256
    )
    recovery1_receipt = _parse_json(recovery1_raw, "attempt-001 recovery receipt")
    if (
        recovery1_receipt.get("recovery_id") != f"{ATTEMPT1_ID}-recovery-001"
        or recovery1_receipt.get("failed_campaign_id") != ATTEMPT1_ID
        or recovery1_receipt.get("success") is not True
        or (recovery1_receipt.get("certification_effect") or {}).get(
            "completed_pair_count"
        )
        != 0
    ):
        raise RecoveryError("attempt-001 recovery receipt semantic binding drifted")

    receipt_raws: dict[str, bytes] = {}
    receipt_snapshots: dict[str, dict[str, Any]] = {}
    dispositions: dict[str, dict[str, Any]] = {}
    for label, (relative, expected_bytes, expected_sha) in RUN_PINS.items():
        raw, snapshot = _pinned(root, relative, expected_bytes, expected_sha)
        receipt_raws[label] = raw
        receipt_snapshots[label] = snapshot
        dispositions[label] = _receipt_disposition(
            _parse_json(raw, f"attempt evidence {label}"), int(label[-1])
        )

    alias_raw, alias_snapshot = _pinned(root, ALIAS, ALIAS_BYTES, ALIAS_SHA256)
    if alias_raw != receipt_raws["run3"]:
        raise RecoveryError("current alias is not byte-equal to immutable run3")
    _require_pairwise_distinct(root, [RUN1, RUN2, RUN3, ALIAS], "run receipts/alias")

    _, log_snapshot = _pinned(
        root, ATTEMPT2_LOG, ATTEMPT2_LOG_BYTES, ATTEMPT2_LOG_SHA256
    )
    artifact_snapshots: dict[str, dict[str, Any]] = {}
    for label, (relative, expected_bytes, expected_sha) in ARTIFACT_PINS.items():
        _, artifact_snapshots[label] = _pinned(
            root, relative, expected_bytes, expected_sha
        )
    _require_pairwise_distinct(
        root, [ARTIFACT1, ARTIFACT2, ARTIFACT3], "run artifacts"
    )

    return {
        "lifecycle": lifecycle,
        "attempt1_recovery_receipt": recovery1_snapshot,
        "run_receipts": receipt_snapshots,
        "run_dispositions": dispositions,
        "alias": {
            **alias_snapshot,
            "byte_equal_to_run3": True,
            "distinct_file_from_run3": True,
        },
        "attempt2_manager_log": log_snapshot,
        "artifacts": artifact_snapshots,
        "file_independence": {
            "run1_run2_run3_alias_pairwise_distinct": True,
            "artifact1_artifact2_artifact3_pairwise_distinct": True,
        },
    }


def collect_source_sha256s(
    root: Path, lifecycle_sources: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    root = Path(root).resolve()
    _, recorder = _snapshot(root / RECORDER_SOURCE, RECORDER_SOURCE.as_posix())
    if recorder["bytes"] <= 0:
        raise RecoveryError("attempt-002 recovery recorder is empty")
    snapshots = {"recorder": recorder}
    for label, (relative, expected_bytes, expected_sha, lifecycle_label) in SOURCE_PINS.items():
        raw, snapshot = _pinned(root, relative, expected_bytes, expected_sha)
        if relative.suffix.lower() in {".py", ".json"} and raw.startswith(b"\xef\xbb\xbf"):
            raise RecoveryError(f"source has a UTF-8 BOM: {relative.as_posix()}")
        if lifecycle_label is not None:
            recorded = lifecycle_sources.get(lifecycle_label) or {}
            if (
                recorded.get("bytes") != snapshot["bytes"]
                or recorded.get("sha256") != snapshot["sha256"]
            ):
                raise RecoveryError(
                    f"current source differs from attempt-002 lifecycle: {label}"
                )
        snapshots[label] = snapshot
    return snapshots


def _load_file_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RecoveryError(f"cannot build import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_exact_attempt2_campaign(root: Path) -> ModuleType:
    """Load only the already hash-validated attempt-002 campaign source."""

    root = Path(root).resolve()
    # Refuse before executing any source if a literal source pin has drifted.
    for _, (relative, expected_bytes, expected_sha, _) in SOURCE_PINS.items():
        if relative.suffix == ".py":
            _pinned(root, relative, expected_bytes, expected_sha)

    scratch = root / "scratch"
    dependency_names = ("run_h3_canonical_campaign", "h3_manager_offline_guard")
    unique_main = "_h3_music_attempt2_frozen_8aec410855961896"
    missing = object()
    prior_modules = {
        name: sys.modules.get(name, missing)
        for name in (*dependency_names, unique_main)
    }
    old_dont_write = sys.dont_write_bytecode
    inserted_path = False
    try:
        sys.dont_write_bytecode = True
        if str(scratch) not in sys.path:
            sys.path.insert(0, str(scratch))
            inserted_path = True
        canonical = _load_file_module(
            dependency_names[0], root / "scratch/run_h3_canonical_campaign.py"
        )
        guard = _load_file_module(
            dependency_names[1], root / "scratch/h3_manager_offline_guard.py"
        )
        module = _load_file_module(
            unique_main, root / "scratch/run_h3_unconditioned_music_campaign.py"
        )
        if module.canon is not canonical or module.manager_guard is not guard:
            raise RecoveryError("attempt-002 campaign loaded unpinned helper modules")
        if (
            Path(module.CAMPAIGN_SOURCE).resolve()
            != (root / "scratch/run_h3_unconditioned_music_campaign.py").resolve()
            or module.FAILED_CAMPAIGN_ID != ATTEMPT1_ID
            or module.RESUME_CAMPAIGN_ID != ATTEMPT2_ID
        ):
            raise RecoveryError("loaded attempt-002 campaign identity drifted")
        return module
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError(f"cannot load exact attempt-002 campaign: {exc}") from exc
    finally:
        sys.dont_write_bytecode = old_dont_write
        if inserted_path:
            try:
                sys.path.remove(str(scratch))
            except ValueError:
                pass
        for name, prior in prior_modules.items():
            if prior is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior


CampaignLoader = Callable[[Path], ModuleType]


def invoke_full_pair_verifier(
    root: Path,
    lifecycle_sources: Mapping[str, Any],
    *,
    campaign_loader: CampaignLoader = load_exact_attempt2_campaign,
) -> dict[str, Any]:
    root = Path(root).resolve()
    campaign = campaign_loader(root)
    try:
        layout = campaign.DEFAULT_LAYOUT
        if Path(layout.root).resolve() != root:
            raise RecoveryError("exact attempt-002 verifier layout points outside evidence root")
        specs = campaign.load_specs(layout)
        if len(specs) != 11 or specs[0].name != CONTROL_NAME:
            raise RecoveryError("attempt-002 verifier control spec ordering drifted")
        schedule = campaign.pair_run_schedule(1, True)
        if schedule != _exact_schedule():
            raise RecoveryError("attempt-002 verifier run schedule drifted")
        log_path = campaign.pair_log_path(specs[0], 1, ATTEMPT2_ID, layout)
        if log_path.resolve() != (root / ATTEMPT2_LOG).resolve():
            raise RecoveryError("attempt-002 verifier Manager log path drifted")
        result = campaign.verify_pair(
            specs[0],
            1,
            ATTEMPT2_ID,
            lifecycle_sources,
            log_path,
            layout,
            cold_run_number=2,
            cold_config_run_count=1,
            warm_run_number=3,
            warm_config_run_count=2,
            allowed_run_numbers=[1, 2, 3],
        )
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError(
            f"full attempt-002 verify_pair did not pass: {type(exc).__name__}: {exc}"
        ) from exc

    cold = result.get("cold") or {}
    warm = result.get("warm") or {}
    log = result.get("final_manager_log") or {}
    if (
        cold.get("receipt_sha256") != RUN_PINS["run2"][2]
        or warm.get("receipt_sha256") != RUN_PINS["run3"][2]
        or (cold.get("artifact") or {}).get("sha256") != ARTIFACT_SHA256
        or (warm.get("artifact") or {}).get("sha256") != ARTIFACT_SHA256
        or cold.get("server_instance") != PAIR_SERVER_IDENTITY
        or warm.get("server_instance") != PAIR_SERVER_IDENTITY
        or cold.get("run_identity_sha256") != RUN_IDENTITY_SHA256
        or warm.get("run_identity_sha256") != RUN_IDENTITY_SHA256
        or cold.get("queued_prompt_sha256") != COLD_QUEUED_SHA256
        or warm.get("queued_prompt_sha256") != WARM_QUEUED_SHA256
        or log.get("status") != "pass"
        or log.get("errors") != []
        or log.get("network_markers") != []
        or log.get("mutation_markers") != []
        or log.get("prefix_bytes") != ATTEMPT2_LOG_BYTES
        or log.get("prefix_sha256") != ATTEMPT2_LOG_SHA256
        or len(log.get("execution_markers") or []) != 4
    ):
        raise RecoveryError("full attempt-002 verify_pair return binding drifted")
    try:
        result_sha = sha256_bytes(canonical_bytes(result))
    except (TypeError, ValueError) as exc:
        raise RecoveryError(f"full verifier returned non-canonical evidence: {exc}") from exc
    return {
        "authority": (
            "scratch/run_h3_unconditioned_music_campaign.py@"
            + SOURCE_PINS["attempt2_campaign"][2]
        ),
        "function": "verify_pair",
        "invoked": True,
        "returned_without_error": True,
        "call": {
            "campaign_id": ATTEMPT2_ID,
            "pair_index": 1,
            "recipe": CONTROL_NAME,
            "cold_run_number": 2,
            "cold_config_run_count": 1,
            "warm_run_number": 3,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2, 3],
            "manager_log": ATTEMPT2_LOG.as_posix(),
        },
        "canonical_result_sha256": result_sha,
        "cold": {
            "receipt_sha256": cold["receipt_sha256"],
            "artifact": cold["artifact"],
            "server_instance": cold["server_instance"],
            "run_identity_sha256": cold["run_identity_sha256"],
            "queued_prompt_sha256": cold["queued_prompt_sha256"],
            "peak_vram_gb": cold["peak_vram_gb"],
            "duration_s": cold["duration_s"],
        },
        "warm": {
            "receipt_sha256": warm["receipt_sha256"],
            "artifact": warm["artifact"],
            "server_instance": warm["server_instance"],
            "run_identity_sha256": warm["run_identity_sha256"],
            "queued_prompt_sha256": warm["queued_prompt_sha256"],
            "peak_vram_gb": warm["peak_vram_gb"],
            "duration_s": warm["duration_s"],
        },
        "final_manager_log": {
            "status": "pass",
            "bytes": log["prefix_bytes"],
            "sha256": log["prefix_sha256"],
            "execution_marker_count": len(log["execution_markers"]),
            "network_markers": [],
            "mutation_markers": [],
        },
    }


@contextmanager
def held_existing_coordinator(root: Path) -> Iterator[dict[str, Any]]:
    """Hold the existing coordinator byte without creating or changing it."""

    path = Path(root).resolve() / ".coordinator.mutex"
    if not os.path.lexists(path):
        raise RecoveryError("coordinator carrier is absent; recorder will not create it")
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
        raise RecoveryError("coordinator carrier bytes changed during observation")


def machine_clean_state(root: Path, coordinator: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical runtime-state shape using only local OS inspection."""

    if coordinator.get("acquired_nonblocking") is not True:
        raise RecoveryError("current state must be observed under the coordinator")
    try:
        import psutil
    except ImportError as exc:
        raise RecoveryError("psutil is required for clean-state observation") from exc

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

    expected_pid = int(PAIR_SERVER_IDENTITY["serving_pid"])
    try:
        actual_create_time = float(psutil.Process(expected_pid).create_time())
    except psutil.NoSuchProcess:
        expected_identity_live = False
    except (psutil.AccessDenied, OSError) as exc:
        raise RecoveryError(f"cannot verify historical server identity: {exc}") from exc
    else:
        expected_identity_live = math.isclose(
            actual_create_time,
            float(PAIR_SERVER_IDENTITY["process_create_time"]),
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
            receipt_create_time = round(float(psutil.Process(receipt_pid).create_time()), 6)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            receipt_create_time = None

    return {
        "gpu_lock_exists": os.path.lexists(root / ".gpu.lock"),
        "suite_lock_exists": os.path.lexists(root / ".suite.lock"),
        "server_pid_receipt_exists": receipt_exists,
        "server_pid_receipt": receipt_pid,
        "server_pid_create_time": receipt_create_time,
        "queue_quarantine_exists": os.path.lexists(root / ".queue.quarantine.json"),
        "listener_pids_8199": sorted(
            set(listeners), key=lambda value: -1 if value is None else value
        ),
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
    campaign_loader: CampaignLoader = load_exact_attempt2_campaign,
) -> dict[str, Any]:
    if isinstance(recorded_at_ns, bool) or not isinstance(recorded_at_ns, int):
        raise RecoveryError("recorded_at_ns must be an integer")
    if recorded_at_ns <= 0:
        raise RecoveryError("recorded_at_ns must be positive")
    if coordinator.get("acquired_nonblocking") is not True:
        raise RecoveryError("recovery receipt must be built under the lab coordinator")
    require_clean_state(current_clean_state)
    root = Path(root).resolve()
    evidence = collect_immutable_evidence(root)
    lifecycle_sources = evidence["lifecycle"]["attempt2_sources"]
    source_sha256s = collect_source_sha256s(root, lifecycle_sources)
    full_verifier = invoke_full_pair_verifier(
        root, lifecycle_sources, campaign_loader=campaign_loader
    )

    return {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-002-return120-recovery",
        "recovery_id": RECOVERY_ID,
        "failed_campaign_id": ATTEMPT2_ID,
        "status": "ATTEMPT_002_FAILED_PAIR1_MACHINE_RECOVERED",
        "recorded_at_ns": recorded_at_ns,
        "recorded_at_utc": _utc_from_ns(recorded_at_ns),
        "immutable_evidence": evidence,
        "failed_incident": {
            **evidence["lifecycle"]["attempt2_terminal_failure"],
            "exit_120_cause": {
                "classification": "UNKNOWN_UNPROVED",
                "causal_claim_asserted": False,
                "operator_attribution_recorded_here": False,
                "operator_attribution": None,
                "reason": (
                    "the hash-chained child outcome records returncode 120 but no "
                    "captured stdout/stderr or other causal evidence"
                ),
            },
        },
        "pair1_machine_verification": {
            "status": "RECOVERABLE_COMPLETE",
            "basis": (
                "recoverable/complete only because the exact attempt-002 source's "
                "full final verify_pair returned without error"
            ),
            "full_final_verifier": full_verifier,
            "cold_disposition": evidence["run_dispositions"]["run2"],
            "warm_disposition": evidence["run_dispositions"]["run3"],
            "same_server_identity": True,
            "distinct_executor_nonce_prompts": True,
            "human_judgment": "PENDING",
            "promotion_granted": False,
        },
        "current_clean_state": dict(current_clean_state),
        "current_clean_state_evidence": {
            "authority": "machine-observed at receipt recording",
            "recorded_at_ns": recorded_at_ns,
            "shape": "scratch.run_h3_canonical_campaign.runtime_state",
            "expected_historical_server_identity": dict(PAIR_SERVER_IDENTITY),
            "coordinator_guard": dict(coordinator),
            "http_or_comfyui_query_performed": False,
        },
        "source_sha256s": source_sha256s,
        "anti_circularity": {
            "exact_attempt_002_campaign_source_included": True,
            "exact_attempt_002_campaign_sha256": SOURCE_PINS["attempt2_campaign"][2],
            "future_attempt_003_main_source_included": False,
            "reason": (
                "attempt-003 must add a literal full-file SHA256 pin for this O_EXCL "
                "receipt after independent audit and publication"
            ),
            "receipt_is_resume_authority_without_external_sha_pin": False,
        },
        "certification_effect": {
            "attempt_002_status": "FAILED",
            "attempt_002_ledger_completed_pair_count": 0,
            "pair1_machine_pair_recoverable_and_complete": True,
            "pair1_completion_basis_is_full_final_verifier_only": True,
            "human_judgment": "PENDING",
            "exit_120_cause": "UNKNOWN_UNPROVED",
            "current_postconditions_are_machine_verified": True,
            "promotion_or_study_pass_granted": False,
        },
        "recovery_policy": {
            "resume_campaign_id": ATTEMPT3_ID,
            "skip_pair_indices": [1],
            "next_pair_index": 2,
            "pair1_reuse_authority": "this externally SHA-pinned recovery receipt",
            "remaining_pair_indices": list(range(2, 12)),
            "remaining_pair_count": 10,
            "executions_per_pair": 2,
            "remaining_execution_count": 20,
            "execution_count_formula": "10 remaining pairs * 2 executions per pair = 20",
            "first_execution": {
                "pair_index": 2,
                "role": "cold",
                "run_number": 1,
                "config_run_count": 1,
            },
        },
        "safety": {
            "failed_lifecycle_appended_or_rewritten": False,
            "artifact_or_run_receipt_modified": False,
            "campaign_source_modified": False,
            "foreign_server_adopted_or_killed_by_recorder": False,
            "shutdown_attempted_by_recorder": False,
            "prompt_or_render_submitted_by_recorder": False,
            "http_or_comfyui_query_performed": False,
            "network_used_by_recorder": False,
        },
        "success": True,
    }


def exclusive_write(root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    destination = root / RECOVERY
    parent = destination.parent
    if not os.path.lexists(parent) or _is_reparse(parent) or not parent.is_dir():
        raise RecoveryError("pre-existing recovery directory is not a real directory")
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
    campaign_loader: CampaignLoader = load_exact_attempt2_campaign,
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
                campaign_loader=campaign_loader,
            )
            published = exclusive_write(Path(root), payload) if args.write else None
    except (RecoveryError, OSError, ValueError) as exc:
        print(
            f"[h3-music-attempt2-recovery] FAIL: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
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
