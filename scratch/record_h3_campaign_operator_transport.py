#!/usr/bin/env python3
"""Prepare and seal local operator transport for the two H3 campaigns.

The default ``--plan`` operation is read-only.  ``--prepare`` is the only
pre-launch write path: it claims a unique operator directory and creates both
redirect logs and ``preflight.json`` with exclusive-create semantics.
``--finalize`` runs only after ``Start-Process -Wait`` and binds the observed
process exit to stable stdout/stderr snapshots, unchanged source hashes, and a
verified terminal lifecycle record.  It never starts, stops, adopts, probes,
or cleans up a ComfyUI process.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping, Sequence


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")
LAUNCHER_REL = Path("scratch/start_h3_campaign_operator.ps1")
RECORDER_REL = Path("scratch/record_h3_campaign_operator_transport.py")
ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,120}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
TERMINAL_EVENTS = {"campaign_completed", "campaign_failed"}
CANONICAL_CAMPAIGN_SHA256 = (
    "e9a7aef3c29fde2e60a53076a6a250d786b4c6d558f4aadd40640fc34e79ba28"
)
CANONICAL_BUILDER_SHA256 = (
    "4dd33941f2c88fb5fcf7ddf2aaa0205cc2c805db941b83288639e8657f7158a4"
)
FROZEN_RUNNER_SHA256 = (
    "85a841a4a040dfcad1d57911a583bc1345d8872c67880cc4fb68c636fe65f4ac"
)
FOLLOWUP_CAMPAIGN_SHA256 = (
    "7633992e6c8ee5566b757b2296700839cfd029803e0590a5081d82d86cf8e441"
)
FOLLOWUP_BUILDER_SHA256 = (
    "23a536c5542fbc6a7a524c19b60c50d7a52cf514e56d81dd5465df704535404a"
)


class TransportError(RuntimeError):
    """Operator transport evidence could not be proven exactly."""


@dataclass(frozen=True)
class Profile:
    mission: str
    campaign_rel: Path
    operator_root_rel: Path
    source_relatives: tuple[tuple[str, Path], ...]
    frozen_hashes: Mapping[str, str]

    def lifecycle_rel(self, campaign_id: str) -> Path:
        if self.mission == "canonical":
            return Path("results/h3_canonical_canvas_campaign/lifecycle.jsonl")
        return Path(
            f"results/h3_music_followup_campaign/campaigns/{campaign_id}/lifecycle.jsonl"
        )


COMMON_SOURCES = (
    ("runner", Path("run_recipe.py")),
    ("lab_locks", Path("lab_locks.py")),
    ("manager_test_boot", Path("boot_h3_manager_offline_test.cmd")),
    ("manager_guard", Path("scratch/h3_manager_offline_guard.py")),
    ("operator_launcher", LAUNCHER_REL),
    ("operator_recorder", RECORDER_REL),
)

PROFILES: dict[str, Profile] = {
    "canonical": Profile(
        mission="canonical",
        campaign_rel=Path("scratch/run_h3_canonical_campaign.py"),
        operator_root_rel=Path(
            "results/h3_canonical_canvas_campaign/operator_logs"
        ),
        source_relatives=(
            ("campaign", Path("scratch/run_h3_canonical_campaign.py")),
            (
                "builder",
                Path("scratch/build_h3_canonical_canvas_ladders.py"),
            ),
            *COMMON_SOURCES,
            (
                "recipe_i2v_f107",
                Path("recipes/h3_i2v_canonical_832x480_f107.json"),
            ),
            (
                "recipe_i2v_f192",
                Path("recipes/h3_i2v_canonical_832x480_f192.json"),
            ),
            (
                "recipe_i2v_f277",
                Path("recipes/h3_i2v_canonical_832x480_f277.json"),
            ),
            (
                "recipe_r2v_f107",
                Path(
                    "recipes/h3_r2v_refaudio_canonical_832x480_f107_seed43.json"
                ),
            ),
            (
                "recipe_r2v_f192",
                Path(
                    "recipes/h3_r2v_refaudio_canonical_832x480_f192_seed43.json"
                ),
            ),
            (
                "recipe_r2v_f277",
                Path(
                    "recipes/h3_r2v_refaudio_canonical_832x480_f277_seed43.json"
                ),
            ),
        ),
        frozen_hashes={
            "campaign": CANONICAL_CAMPAIGN_SHA256,
            "builder": CANONICAL_BUILDER_SHA256,
            "runner": FROZEN_RUNNER_SHA256,
        },
    ),
    "followup": Profile(
        mission="followup",
        campaign_rel=Path("scratch/run_h3_music_followup_campaign.py"),
        operator_root_rel=Path(
            "results/h3_music_followup_campaign/operator_logs"
        ),
        source_relatives=(
            ("campaign", Path("scratch/run_h3_music_followup_campaign.py")),
            ("builder", Path("scratch/build_h3_music_followup.py")),
            *COMMON_SOURCES,
            (
                "descriptor_wrapper",
                Path("scratch/h3_music_machine_descriptors/analyze_manifest.py"),
            ),
            (
                "descriptor_analyzer",
                Path("scratch/h3_music_machine_descriptors/analyze.py"),
            ),
        ),
        frozen_hashes={
            "campaign": FOLLOWUP_CAMPAIGN_SHA256,
            "builder": FOLLOWUP_BUILDER_SHA256,
            "runner": FROZEN_RUNNER_SHA256,
        },
    ),
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def followup_compact_bytes(value: Any) -> bytes:
    # The follow-up coordinator deliberately includes the JSONL newline in
    # each event body's retained SHA.  Its canonical_compact() does the same.
    return canonical_bytes(value) + b"\n"


def pretty_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def validate_id(value: str, label: str) -> str:
    if ID_RE.fullmatch(value) is None:
        raise TransportError(f"{label} must match [A-Za-z0-9_.-]{{1,120}}")
    return value


def validate_modes(
    profile: Profile,
    *,
    campaign_id: str,
    operator_run_id: str,
    resume: bool,
    resume_from_campaign_id: str | None,
) -> None:
    validate_id(campaign_id, "campaign id")
    validate_id(operator_run_id, "operator run id")
    if resume_from_campaign_id is not None:
        validate_id(resume_from_campaign_id, "resume source campaign id")
    if profile.mission == "canonical":
        if resume:
            raise TransportError("canonical transport does not accept --resume")
        if resume_from_campaign_id == campaign_id:
            raise TransportError("canonical resume source must differ from campaign id")
    elif resume_from_campaign_id is not None:
        raise TransportError("follow-up transport does not accept --resume-from-campaign-id")


def require_real_directory(path: Path, label: str) -> None:
    if not os.path.lexists(path) or _is_reparse(path) or not path.is_dir():
        raise TransportError(f"{label} is not a real directory: {path}")


def ensure_real_tree(root: Path, relative: Path) -> Path:
    root = _absolute(root)
    require_real_directory(root, "workspace root")
    current = root
    for part in relative.parts:
        if part in ("", ".", ".."):
            raise TransportError("operator path contains an unsafe component")
        current = current / part
        if os.path.lexists(current):
            require_real_directory(current, "operator parent")
        else:
            current.mkdir(exist_ok=False)
            require_real_directory(current, "created operator parent")
    return current


def stable_file(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    path = _absolute(path)
    if not os.path.lexists(path) or _is_reparse(path):
        raise TransportError(f"missing or reparse {label}: {path}")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or int(before.st_nlink) != 1:
        raise TransportError(f"{label} is not an independent regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
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
    # Windows may expose executable permission bits differently through a path
    # stat and an already-open descriptor.  File type is checked independently;
    # the durable identity fields must remain exact across all four snapshots.
    keys = ("st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns")
    identities = [
        tuple(int(getattr(value, key)) for key in keys)
        for value in (before, descriptor_before, descriptor_after, after)
    ]
    if (
        len(set(identities)) != 1
        or not all(
            stat.S_ISREG(value.st_mode)
            for value in (before, descriptor_before, descriptor_after, after)
        )
        or _is_reparse(path)
        or len(raw) != int(after.st_size)
    ):
        raise TransportError(f"{label} changed during stable read")
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


def source_evidence(
    root: Path, profile: Profile, python: Path = PYTHON
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    raw, evidence["python_executable"] = stable_file(python, "Comfy venv Python")
    if not raw.startswith(b"MZ"):
        raise TransportError("Comfy venv Python does not have a Windows executable header")
    for label, relative in profile.source_relatives:
        raw, item = stable_file(root / relative, label)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise TransportError(f"{label} source has a UTF-8 BOM")
        evidence[label] = item
    for label, expected in profile.frozen_hashes.items():
        actual = evidence.get(label, {}).get("sha256")
        if actual != expected:
            raise TransportError(
                f"frozen {profile.mission} {label} SHA drifted: {actual} != {expected}"
            )
    return evidence


def operator_paths(
    root: Path, profile: Profile, operator_run_id: str
) -> dict[str, Path]:
    directory = _absolute(root / profile.operator_root_rel / operator_run_id)
    return {
        "directory": directory,
        "stdout": directory / "stdout.log",
        "stderr": directory / "stderr.log",
        "preflight": directory / "preflight.json",
        "receipt": directory / "launch.json",
    }


def campaign_arguments(
    root: Path,
    profile: Profile,
    campaign_id: str,
    *,
    resume: bool,
    resume_from_campaign_id: str | None,
) -> list[str]:
    arguments = [
        "-B",
        "-u",
        str(_absolute(root / profile.campaign_rel)),
        "--run",
        "--campaign-id",
        campaign_id,
    ]
    if profile.mission == "canonical" and resume_from_campaign_id is not None:
        arguments.extend(["--resume-from-campaign-id", resume_from_campaign_id])
    if profile.mission == "followup" and resume:
        arguments.append("--resume")
    return arguments


def _triplet(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in ("path", "bytes", "sha256")}


def lifecycle_initial(
    path: Path,
    profile: Profile,
    campaign_id: str,
    *,
    resume: bool,
    resume_from_campaign_id: str | None,
) -> dict[str, Any]:
    path = _absolute(path)
    if not os.path.lexists(path):
        if profile.mission == "followup" and resume:
            raise TransportError("follow-up resume lifecycle does not exist")
        if profile.mission == "canonical" and resume_from_campaign_id is not None:
            raise TransportError("canonical resume-source lifecycle does not exist")
        return {"path": str(path), "exists": False, "bytes": 0, "sha256": None}
    raw, snapshot = stable_file(path, "initial lifecycle")
    current = validate_lifecycle(
        raw, profile, campaign_id, require_terminal=False
    )
    if profile.mission == "canonical":
        if current["campaign_event_count"]:
            raise TransportError("canonical campaign id already exists in lifecycle")
        if resume_from_campaign_id is not None:
            resumed = validate_lifecycle(
                raw, profile, resume_from_campaign_id, require_terminal=True
            )
            if resumed["terminal"]["event"] != "campaign_failed":
                raise TransportError("canonical resume source is not sealed FAILED")
    elif resume:
        if current["campaign_event_count"] == 0:
            raise TransportError("follow-up resume campaign is absent from lifecycle")
        if (
            current["terminal"] is not None
            and current["terminal"]["event"] == "campaign_completed"
        ):
            raise TransportError("follow-up resume campaign is already complete")
    else:
        raise TransportError("new follow-up campaign lifecycle already exists")
    return {"exists": True, **snapshot}


def build_plan(
    *,
    root: Path,
    profile: Profile,
    campaign_id: str,
    operator_run_id: str,
    resume: bool = False,
    resume_from_campaign_id: str | None = None,
    python: Path = PYTHON,
    include_sources: bool = True,
) -> dict[str, Any]:
    root = _absolute(root)
    validate_modes(
        profile,
        campaign_id=campaign_id,
        operator_run_id=operator_run_id,
        resume=resume,
        resume_from_campaign_id=resume_from_campaign_id,
    )
    require_real_directory(root, "workspace root")
    paths = operator_paths(root, profile, operator_run_id)
    arguments = campaign_arguments(
        root,
        profile,
        campaign_id,
        resume=resume,
        resume_from_campaign_id=resume_from_campaign_id,
    )
    lifecycle = _absolute(root / profile.lifecycle_rel(campaign_id))
    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3-local-operator-transport-plan",
        "authority": "operator transport only",
        "default_read_only": True,
        "mission": profile.mission,
        "campaign_id": campaign_id,
        "operator_run_id": operator_run_id,
        "working_directory": str(root),
        "executable": str(_absolute(python)),
        "arguments": arguments,
        "argv": [str(_absolute(python)), *arguments],
        "resume": resume,
        "resume_from_campaign_id": resume_from_campaign_id,
        "operator_directory": str(paths["directory"]),
        "stdout_log": str(paths["stdout"]),
        "stderr_log": str(paths["stderr"]),
        "preflight_receipt": str(paths["preflight"]),
        "launch_receipt": str(paths["receipt"]),
        "lifecycle": str(lifecycle),
        "process_contract": {
            "api": "Windows Start-Process",
            "window_style": "Hidden",
            "wait": True,
            "pass_thru": True,
            "exit_code_source": "System.Diagnostics.Process.ExitCode after -Wait",
            "start_time_source": "System.Diagnostics.Process.StartTime after -Wait",
            "end_time_source": "System.Diagnostics.Process.ExitTime after -Wait",
        },
        "write_contract": {
            "operator_directory": "unique atomic directory claim",
            "stdout_log": "os.open O_CREAT|O_EXCL before Start-Process",
            "stderr_log": "os.open O_CREAT|O_EXCL before Start-Process",
            "preflight_receipt": "open mode xb",
            "launch_receipt": "open mode xb after terminal lifecycle verification",
        },
        "safety_contract": {
            "starts_only_campaign_process": True,
            "server_or_gpu_probe": False,
            "server_adoption": False,
            "force_or_kill": False,
            "cleanup": False,
            "foreign_or_otr_access": False,
            "campaign_status_changed_by_transport": False,
        },
    }
    if include_sources:
        plan["source_evidence"] = source_evidence(root, profile, python)
    return plan


def write_exclusive(path: Path, raw: bytes, label: str) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise TransportError(f"{label} already exists: {path}") from exc


def create_log_exclusive(path: Path) -> dict[str, Any]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise TransportError(f"operator log already exists: {path}") from exc
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    _, snapshot = stable_file(path, "exclusive-created operator log")
    return snapshot


def prepare(
    *,
    root: Path,
    profile: Profile,
    campaign_id: str,
    operator_run_id: str,
    resume: bool = False,
    resume_from_campaign_id: str | None = None,
    python: Path = PYTHON,
) -> dict[str, Any]:
    plan = build_plan(
        root=root,
        profile=profile,
        campaign_id=campaign_id,
        operator_run_id=operator_run_id,
        resume=resume,
        resume_from_campaign_id=resume_from_campaign_id,
        python=python,
        include_sources=True,
    )
    root = _absolute(root)
    parent = ensure_real_tree(root, profile.operator_root_rel)
    paths = operator_paths(root, profile, operator_run_id)
    try:
        paths["directory"].mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise TransportError(
            f"operator run directory already exists; refusing reuse: {paths['directory']}"
        ) from exc
    require_real_directory(paths["directory"], "claimed operator run directory")
    if paths["directory"].parent != parent:
        raise TransportError("operator run directory escaped its proven parent")
    stdout_initial = create_log_exclusive(paths["stdout"])
    stderr_initial = create_log_exclusive(paths["stderr"])
    initial_lifecycle = lifecycle_initial(
        Path(plan["lifecycle"]),
        profile,
        campaign_id,
        resume=resume,
        resume_from_campaign_id=resume_from_campaign_id,
    )
    payload = {
        "schema_version": 1,
        "kind": "h3-local-operator-transport-preflight",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan": plan,
        "initial_lifecycle": initial_lifecycle,
        "exclusive_log_claims": {
            "stdout": stdout_initial,
            "stderr": stderr_initial,
        },
        "directory_entries_before_preflight": ["stderr.log", "stdout.log"],
        "no_campaign_or_server_process_started_by_recorder": True,
    }
    found = sorted(entry.name for entry in paths["directory"].iterdir())
    if found != payload["directory_entries_before_preflight"]:
        raise TransportError(f"operator directory entries drifted before preflight: {found}")
    write_exclusive(paths["preflight"], pretty_bytes(payload), "preflight receipt")
    found = sorted(entry.name for entry in paths["directory"].iterdir())
    if found != ["preflight.json", "stderr.log", "stdout.log"]:
        raise TransportError(f"operator directory entries drifted after preflight: {found}")
    return payload


def strict_json(path: Path, label: str) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    raw, snapshot = stable_file(path, label)
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise TransportError(f"{label} is not BOM-free newline-terminated UTF-8")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransportError(f"{label} JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise TransportError(f"{label} is not a JSON object")
    return value, raw, snapshot


def validate_preflight(
    preflight: Mapping[str, Any],
    expected_plan: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> datetime:
    expected_keys = {
        "schema_version",
        "kind",
        "prepared_at_utc",
        "plan",
        "initial_lifecycle",
        "exclusive_log_claims",
        "directory_entries_before_preflight",
        "no_campaign_or_server_process_started_by_recorder",
    }
    if (
        set(preflight) != expected_keys
        or preflight.get("schema_version") != 1
        or preflight.get("kind") != "h3-local-operator-transport-preflight"
        or preflight.get("plan") != expected_plan
        or preflight.get("directory_entries_before_preflight")
        != ["stderr.log", "stdout.log"]
        or preflight.get("no_campaign_or_server_process_started_by_recorder") is not True
    ):
        raise TransportError("transport preflight shape, plan, or source hashes drifted")
    prepared_value = preflight.get("prepared_at_utc")
    if not isinstance(prepared_value, str):
        raise TransportError("transport prepared time is missing")
    prepared = parse_utc(prepared_value, "transport prepared time")
    claims = preflight.get("exclusive_log_claims")
    if not isinstance(claims, dict) or set(claims) != {"stdout", "stderr"}:
        raise TransportError("exclusive log claims are missing or malformed")
    empty_sha = sha256_bytes(b"")
    for label, path in (("stdout", paths["stdout"]), ("stderr", paths["stderr"])):
        claim = claims.get(label)
        if (
            not isinstance(claim, dict)
            or claim.get("path") != str(path)
            or claim.get("bytes") != 0
            or claim.get("sha256") != empty_sha
            or claim.get("link_count") != 1
            or claim.get("regular_file") is not True
            or claim.get("reparse_point") is not False
        ):
            raise TransportError(f"exclusive-created {label} claim drifted")
    initial = preflight.get("initial_lifecycle")
    if (
        not isinstance(initial, dict)
        or initial.get("path") != expected_plan.get("lifecycle")
        or not isinstance(initial.get("exists"), bool)
    ):
        raise TransportError("initial lifecycle evidence is malformed")
    if initial.get("exists") is False and initial != {
        "path": expected_plan.get("lifecycle"),
        "exists": False,
        "bytes": 0,
        "sha256": None,
    }:
        raise TransportError("absent initial lifecycle evidence drifted")
    if initial.get("exists") is True and (
        isinstance(initial.get("bytes"), bool)
        or not isinstance(initial.get("bytes"), int)
        or initial.get("bytes") < 0
        or not isinstance(initial.get("sha256"), str)
        or SHA256_RE.fullmatch(initial.get("sha256")) is None
        or initial.get("link_count") != 1
        or initial.get("regular_file") is not True
        or initial.get("reparse_point") is not False
    ):
        raise TransportError("present initial lifecycle evidence drifted")
    return prepared


def validate_lifecycle(
    raw: bytes,
    profile: Profile,
    campaign_id: str | None,
    *,
    require_terminal: bool,
) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf") or (raw and not raw.endswith(b"\n")):
        raise TransportError("lifecycle is not BOM-free newline-terminated JSONL")
    rows: list[dict[str, Any]] = []
    previous: str | None = None
    campaign_sequences: dict[str, int] = {}
    for index, line in enumerate(raw.splitlines(), start=1):
        if not line:
            raise TransportError("lifecycle contains a blank row")
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportError(f"lifecycle row {index} is invalid: {exc}") from exc
        if not isinstance(row, dict):
            raise TransportError(f"lifecycle row {index} is not an object")
        retained = row.get("event_sha256")
        if not isinstance(retained, str) or SHA256_RE.fullmatch(retained) is None:
            raise TransportError(f"lifecycle row {index} event hash is invalid")
        body = {key: value for key, value in row.items() if key != "event_sha256"}
        if profile.mission == "canonical":
            row_campaign = row.get("campaign_id")
            expected_campaign_sequence = campaign_sequences.get(row_campaign, 0) + 1
            valid = (
                row.get("schema_version") == 1
                and row.get("ledger_sequence") == index
                and isinstance(row_campaign, str)
                and ID_RE.fullmatch(row_campaign) is not None
                and row.get("campaign_sequence") == expected_campaign_sequence
                and row.get("previous_event_sha256") == previous
                and retained == sha256_bytes(canonical_bytes(body))
                and isinstance(row.get("event"), str)
                and isinstance(row.get("details"), dict)
            )
            if valid:
                campaign_sequences[row_campaign] = expected_campaign_sequence
        else:
            row_campaign = row.get("campaign_id")
            valid = (
                row.get("sequence") == index
                and isinstance(row_campaign, str)
                and ID_RE.fullmatch(row_campaign) is not None
                and row.get("previous_event_sha256") == previous
                and retained == sha256_bytes(followup_compact_bytes(body))
                and isinstance(row.get("event"), str)
                and isinstance(row.get("data"), dict)
            )
        if not valid:
            raise TransportError(f"lifecycle hash chain or schema failed at row {index}")
        previous = retained
        rows.append(row)
    if (
        profile.mission == "followup"
        and campaign_id is not None
        and any(row.get("campaign_id") != campaign_id for row in rows)
    ):
        raise TransportError("follow-up lifecycle contains a foreign campaign id")
    campaign_rows = (
        [row for row in rows if row.get("campaign_id") == campaign_id]
        if campaign_id is not None
        else []
    )
    terminal: dict[str, Any] | None = None
    if campaign_id is not None and campaign_rows:
        last = campaign_rows[-1]
        if last.get("event") in TERMINAL_EVENTS:
            payload_key = "details" if profile.mission == "canonical" else "data"
            status = (last.get(payload_key) or {}).get("status")
            terminal = {
                "event": last.get("event"),
                "status": status,
                "event_sha256": last.get("event_sha256"),
                "previous_event_sha256": last.get("previous_event_sha256"),
                "campaign_sequence": (
                    last.get("campaign_sequence")
                    if profile.mission == "canonical"
                    else last.get("sequence")
                ),
                "ledger_sequence": (
                    last.get("ledger_sequence")
                    if profile.mission == "canonical"
                    else last.get("sequence")
                ),
            }
    if require_terminal and terminal is None:
        raise TransportError("campaign lifecycle is not sealed by a terminal event")
    if require_terminal and terminal["ledger_sequence"] != len(rows):
        raise TransportError("campaign terminal event is not the final lifecycle row")
    return {
        "row_count": len(rows),
        "last_event_sha256": previous,
        "campaign_event_count": len(campaign_rows),
        "terminal": terminal,
    }


def parse_utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransportError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TransportError(f"{label} is not explicitly UTC")
    return parsed


def validate_appended_lifecycle_suffix(
    raw: bytes,
    prefix_bytes: int,
    profile: Profile,
    campaign_id: str,
    *,
    resume: bool,
) -> dict[str, Any]:
    if prefix_bytes and raw[prefix_bytes - 1 : prefix_bytes] != b"\n":
        raise TransportError("initial lifecycle prefix does not end at a row boundary")
    suffix = raw[prefix_bytes:]
    if not suffix or not suffix.endswith(b"\n"):
        raise TransportError("appended lifecycle suffix is empty or partial")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(suffix.splitlines(), start=1):
        if not line:
            raise TransportError("appended lifecycle suffix contains a blank row")
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportError(
                f"appended lifecycle suffix row {index} is invalid: {exc}"
            ) from exc
        if not isinstance(row, dict) or row.get("campaign_id") != campaign_id:
            raise TransportError(
                "appended lifecycle suffix contains a foreign campaign id"
            )
        rows.append(row)
    expected_first = (
        "campaign_resumed"
        if profile.mission == "followup" and resume
        else "campaign_started"
    )
    if rows[0].get("event") != expected_first:
        raise TransportError(
            f"appended lifecycle suffix does not begin with {expected_first}"
        )
    return {
        "bytes": len(suffix),
        "sha256": sha256_bytes(suffix),
        "row_count": len(rows),
        "first_event": rows[0].get("event"),
        "last_event": rows[-1].get("event"),
        "all_rows_campaign_id": campaign_id,
    }


def finalize(
    *,
    root: Path,
    profile: Profile,
    campaign_id: str,
    operator_run_id: str,
    pid: int,
    started_at_utc: str,
    ended_at_utc: str,
    exit_code: int,
    resume: bool = False,
    resume_from_campaign_id: str | None = None,
    python: Path = PYTHON,
) -> dict[str, Any]:
    validate_modes(
        profile,
        campaign_id=campaign_id,
        operator_run_id=operator_run_id,
        resume=resume,
        resume_from_campaign_id=resume_from_campaign_id,
    )
    if isinstance(pid, bool) or pid <= 0:
        raise TransportError("observed process PID must be positive")
    started = parse_utc(started_at_utc, "process start time")
    ended = parse_utc(ended_at_utc, "process end time")
    if ended < started:
        raise TransportError("observed process end precedes its start")
    if isinstance(exit_code, bool) or not (-(2**31) <= exit_code <= 2**32 - 1):
        raise TransportError("observed process exit code is outside the supported range")
    root = _absolute(root)
    paths = operator_paths(root, profile, operator_run_id)
    require_real_directory(paths["directory"], "operator run directory")
    found = sorted(entry.name for entry in paths["directory"].iterdir())
    if found != ["preflight.json", "stderr.log", "stdout.log"]:
        raise TransportError(f"operator directory entries drifted before finalize: {found}")
    preflight, preflight_raw, preflight_snapshot = strict_json(
        paths["preflight"], "transport preflight"
    )
    expected_plan = build_plan(
        root=root,
        profile=profile,
        campaign_id=campaign_id,
        operator_run_id=operator_run_id,
        resume=resume,
        resume_from_campaign_id=resume_from_campaign_id,
        python=python,
        include_sources=True,
    )
    prepared = validate_preflight(preflight, expected_plan, paths)
    if started < prepared:
        raise TransportError("observed process start precedes transport prepare")
    stdout_raw, stdout = stable_file(paths["stdout"], "operator stdout")
    stderr_raw, stderr = stable_file(paths["stderr"], "operator stderr")
    claims = preflight["exclusive_log_claims"]
    for label, snapshot in (("stdout", stdout), ("stderr", stderr)):
        claim = claims.get(label)
        if not isinstance(claim, dict):
            raise TransportError(f"exclusive {label} claim is missing")
        for identity_key in ("path", "device", "inode", "mode", "link_count"):
            if claim.get(identity_key) != snapshot.get(identity_key):
                raise TransportError(f"exclusive-created {label} log identity changed")
    lifecycle_path = Path(expected_plan["lifecycle"])
    lifecycle_raw, lifecycle_snapshot = stable_file(
        lifecycle_path, "terminal campaign lifecycle"
    )
    initial = preflight.get("initial_lifecycle")
    if not isinstance(initial, dict):
        raise TransportError("initial lifecycle evidence is missing")
    prefix_bytes = initial.get("bytes")
    prefix_sha = initial.get("sha256")
    if isinstance(prefix_bytes, bool) or not isinstance(prefix_bytes, int) or prefix_bytes < 0:
        raise TransportError("initial lifecycle byte count is invalid")
    if len(lifecycle_raw) <= prefix_bytes:
        raise TransportError("campaign appended no lifecycle bytes")
    if sha256_bytes(lifecycle_raw[:prefix_bytes]) != (
        prefix_sha if prefix_bytes else sha256_bytes(b"")
    ):
        if not (prefix_bytes == 0 and prefix_sha is None):
            raise TransportError("initial lifecycle prefix changed during campaign")
    if initial.get("exists") is True:
        for identity_key in ("path", "device", "inode", "mode", "link_count"):
            if initial.get(identity_key) != lifecycle_snapshot.get(identity_key):
                raise TransportError("initial lifecycle file identity changed during campaign")
    lifecycle = validate_lifecycle(
        lifecycle_raw, profile, campaign_id, require_terminal=True
    )
    appended_lifecycle = validate_appended_lifecycle_suffix(
        lifecycle_raw,
        prefix_bytes,
        profile,
        campaign_id,
        resume=resume,
    )
    terminal = lifecycle["terminal"]
    expected_event = "campaign_completed" if exit_code == 0 else "campaign_failed"
    expected_status = "COMPLETE" if exit_code == 0 else "FAILED"
    if terminal.get("event") != expected_event or terminal.get("status") != expected_status:
        raise TransportError(
            "process exit and terminal lifecycle status disagree: "
            f"exit={exit_code}, terminal={terminal}"
        )
    receipt = {
        "schema_version": 1,
        "kind": "h3-local-operator-transport-launch",
        "authority": "operator transport only",
        "mission": profile.mission,
        "campaign_id": campaign_id,
        "operator_run_id": operator_run_id,
        "transport_status": "COMPLETED" if exit_code == 0 else "FAILED",
        "process_observation": {
            "pid": pid,
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "exit_code": exit_code,
            "observation_source": expected_plan["process_contract"],
            "working_directory": expected_plan["working_directory"],
            "executable": expected_plan["executable"],
            "argv": expected_plan["argv"],
        },
        "source_evidence": expected_plan["source_evidence"],
        "preflight_receipt": _triplet(preflight_snapshot),
        "operator_streams": {
            "stdout": _triplet(stdout),
            "stderr": _triplet(stderr),
            "stdout_snapshot_after_wait": True,
            "stderr_snapshot_after_wait": True,
            "exclusive_create_identity_retained": True,
        },
        "lifecycle": {
            "file": _triplet(lifecycle_snapshot),
            "initial_prefix": initial,
            "appended_bytes": len(lifecycle_raw) - prefix_bytes,
            "appended_suffix": appended_lifecycle,
            "row_count": lifecycle["row_count"],
            "campaign_event_count": lifecycle["campaign_event_count"],
            "last_event_sha256": lifecycle["last_event_sha256"],
            "terminal": terminal,
            "whole_file_hash_chain_verified": True,
        },
        "stdout_was_empty": len(stdout_raw) == 0,
        "stderr_was_empty": len(stderr_raw) == 0,
        "certification_effect": {
            "campaign_status_changed": False,
            "render_or_recipe_certification_granted": False,
            "human_quality_judgment_granted": False,
        },
        "server_or_gpu_cleanup_attempted": False,
        "server_adoption_attempted": False,
        "force_or_kill_attempted": False,
    }
    write_exclusive(paths["receipt"], pretty_bytes(receipt), "launch receipt")
    _, receipt_snapshot = stable_file(paths["receipt"], "published launch receipt")
    found = sorted(entry.name for entry in paths["directory"].iterdir())
    if found != ["launch.json", "preflight.json", "stderr.log", "stdout.log"]:
        raise TransportError(f"operator directory entries drifted after finalize: {found}")
    return {
        "status": "RECORDED",
        "transport_status": receipt["transport_status"],
        "mission": profile.mission,
        "campaign_id": campaign_id,
        "operator_run_id": operator_run_id,
        "receipt": _triplet(receipt_snapshot),
        "terminal": terminal,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument("--mission", choices=sorted(PROFILES), required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--operator-run-id", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--resume-from-campaign-id")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--started-at-utc")
    parser.add_argument("--ended-at-utc")
    parser.add_argument("--exit-code", type=int)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    args = parse_args(argv)
    profile = PROFILES[args.mission]
    operation = "finalize" if args.finalize else "prepare" if args.prepare else "plan"
    common = {
        "root": root,
        "profile": profile,
        "campaign_id": args.campaign_id,
        "operator_run_id": args.operator_run_id,
        "resume": args.resume,
        "resume_from_campaign_id": args.resume_from_campaign_id,
    }
    try:
        if operation == "plan":
            result = build_plan(**common)
        elif operation == "prepare":
            result = prepare(**common)
        else:
            if None in (
                args.pid,
                args.started_at_utc,
                args.ended_at_utc,
                args.exit_code,
            ):
                raise TransportError(
                    "--finalize requires --pid, --started-at-utc, --ended-at-utc, and --exit-code"
                )
            result = finalize(
                **common,
                pid=args.pid,
                started_at_utc=args.started_at_utc,
                ended_at_utc=args.ended_at_utc,
                exit_code=args.exit_code,
            )
    except Exception as exc:
        print(f"[H3 OPERATOR TRANSPORT ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
