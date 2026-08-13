#!/usr/bin/env python3
"""Exclusive, source-pinned launcher for the two authorized H3 short jobs.

This transport launches exactly one foreground ``run_recipe.py`` child.  It
does not impose an outer render timeout and never terminates or adopts a
server; ownership and shutdown remain entirely inside the runner.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")
RUNNER = ROOT / "run_recipe.py"
RUNNER_SHA256 = "6d6ac785b1e2cdd38505cdc5f418478855ec50d370213b29d8b0ade585682776"
MANAGER_GUARD = ROOT / "scratch" / "h3_manager_offline_guard.py"
MANAGER_GUARD_SHA256 = "1b06e5662e9bad8d17aac05d31e393683f3cd450dadbeb86c3763c3a47b2a821"
BOOT = ROOT / "boot_h3_manager_offline_test.cmd"
BOOT_SHA256 = "bce4a81841579226c7aaf8a0bd04cdac25ddfb9b4bcf60f63c0bd9fc740b35a3"
LAB_LOCKS = ROOT / "lab_locks.py"
LAB_LOCKS_SHA256 = "0200e8620558fe3a7ddf75bf54678439905d6041a65d1c06bd2b2ba01def0ff1"
ORIGIN_BUILDER = ROOT / "scratch" / "build_h3_music_origin_prompt_only.py"
LAUNCH_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,119}")


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    key: str
    recipe_name: str
    recipe_path: Path
    recipe_sha256: str
    timeout_s: int
    manager_root: Path

    @property
    def result_path(self) -> Path:
        return ROOT / "results" / f"{self.recipe_name}_run1.json"

    @property
    def alias_path(self) -> Path:
        return ROOT / "results" / f"{self.recipe_name}.json"

    @property
    def artifact_path(self) -> Path:
        return ROOT / "outputs" / f"{self.recipe_name}_out_00001_.mp4"


JOBS = {
    "jobd": Job(
        "jobd",
        "h3_jobd_lipsync_refaudio_seed43_f192",
        ROOT / "recipes" / "h3_jobd_lipsync_refaudio_seed43_f192.json",
        "510bd4e6dc96d635460d65f975652bf15f2862f098de2b7e7f2b6964cce23eb7",
        3600,
        ROOT / "results" / "h3_short_jobs" / "server_logs",
    ),
    "origin-primary": Job(
        "origin-primary",
        "h3_music_followup_origin_prompt_only_exact_seed42_f124",
        ROOT / "recipes" / "h3_music_followup_origin_prompt_only_exact_seed42_f124.json",
        "c877d6db69aad72b9f5b9333e80d53e4d35deecd09d85192b6d4345c76100428",
        2400,
        ROOT / "results" / "h3_music_followup_campaign" / "server_logs",
    ),
    "origin-fallback": Job(
        "origin-fallback",
        "h3_music_followup_origin_prompt_only_no_picture_sentence_seed42_f124",
        ROOT / "recipes" / "h3_music_followup_origin_prompt_only_no_picture_sentence_seed42_f124.json",
        "63662e6a690360ae06e505aefd586d4d9adbe8198dc0fdbda6e7ac969dd6b53e",
        2400,
        ROOT / "results" / "h3_music_followup_campaign" / "server_logs",
    ),
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def stable_file(path: Path) -> dict[str, Any]:
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise LaunchError(f"file changed while hashing: {path}")
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def require_pin(path: Path, expected: str) -> dict[str, Any]:
    descriptor = stable_file(path)
    if descriptor["sha256"] != expected:
        raise LaunchError(
            f"source pin drift for {path}: {descriptor['sha256']} != {expected}"
        )
    return descriptor


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LaunchError(f"cannot import source: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_fallback_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        raise LaunchError("origin fallback requires --fallback-evidence")
    descriptor = stable_file(path)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LaunchError(f"invalid fallback evidence: {exc}") from exc
    builder = load_module(ORIGIN_BUILDER, "h3_origin_builder_for_launch")
    errors = builder.fallback_authorization_errors(evidence)
    if errors:
        raise LaunchError("fallback is not authorized: " + "; ".join(errors))
    primary = JOBS["origin-primary"]
    if primary.artifact_path.exists():
        raise LaunchError("fallback denied because the primary artifact exists")
    return descriptor


def child_environment(manager_log: Path) -> tuple[dict[str, str], dict[str, Any]]:
    guard = load_module(MANAGER_GUARD, "h3_manager_guard_for_short_leg")
    environment = dict(os.environ)
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
        *guard.SCRUBBED_ENVIRONMENT_KEYS,
    ):
        environment.pop(key, None)
    environment.update(guard.OFFLINE_ENVIRONMENT)
    environment["LAB_RESERVE_VRAM_GB"] = "12"
    environment["LAB_CACHE_CLASSIC"] = "1"
    environment["LAB_MANAGER_PROBE_LOG"] = str(manager_log.resolve())
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    evidence = guard.offline_environment_evidence(environment)
    return environment, evidence


def plan(job: Job, launch_id: str) -> dict[str, Any]:
    if LAUNCH_ID_RE.fullmatch(launch_id) is None:
        raise LaunchError("launch ID must be 8-120 safe characters")
    manager_log = job.manager_root / f"{launch_id}-{job.key}.log"
    operator_dir = ROOT / "results" / "h3_short_jobs" / "operator_logs" / launch_id
    nonce = f"h3short:{launch_id}:{job.key}:cold"
    command = [
        str(PYTHON),
        "-B",
        str(RUNNER),
        str(job.recipe_path),
        "--disable-pinned-memory",
        "--manager-offline-test",
        "--manager-probe-phase",
        "cold",
        "--executor-cache-nonce",
        nonce,
        "--completion-timeout-s",
        str(job.timeout_s),
        "--shutdown",
    ]
    return {
        "job": job.key,
        "launch_id": launch_id,
        "recipe_name": job.recipe_name,
        "command": command,
        "manager_log": str(manager_log.resolve()),
        "operator_dir": str(operator_dir.resolve()),
        "expected_result": str(job.result_path.resolve()),
        "expected_alias": str(job.alias_path.resolve()),
        "expected_artifact": str(job.artifact_path.resolve()),
    }


def ensure_pristine(job: Job, launch_plan: dict[str, Any]) -> None:
    paths = [job.result_path, job.alias_path, job.artifact_path, Path(launch_plan["manager_log"])]
    unexpected = [str(path) for path in paths if path.exists()]
    unexpected.extend(
        str(path)
        for path in (ROOT / "results").glob(f"{job.recipe_name}_run*.json")
        if str(path) not in unexpected
    )
    unexpected.extend(
        str(path)
        for path in (ROOT / "outputs").glob(f"{job.recipe_name}_out_*.mp4")
        if str(path) not in unexpected
    )
    if unexpected:
        raise LaunchError("refusing non-pristine job history: " + ", ".join(unexpected))
    operator_dir = Path(launch_plan["operator_dir"])
    if operator_dir.exists():
        raise LaunchError(f"operator directory already exists: {operator_dir}")


def source_snapshots(job: Job) -> dict[str, Any]:
    return {
        "runner": require_pin(RUNNER, RUNNER_SHA256),
        "recipe": require_pin(job.recipe_path, job.recipe_sha256),
        "manager_guard": require_pin(MANAGER_GUARD, MANAGER_GUARD_SHA256),
        "manager_boot": require_pin(BOOT, BOOT_SHA256),
        "lab_locks": require_pin(LAB_LOCKS, LAB_LOCKS_SHA256),
        "launcher": stable_file(Path(__file__).resolve()),
        "python": stable_file(PYTHON),
    }


def run(job: Job, launch_id: str, fallback_evidence: Path | None) -> int:
    launch_plan = plan(job, launch_id)
    snapshots = source_snapshots(job)
    evidence_descriptor = None
    if job.key == "origin-fallback":
        evidence_descriptor = validate_fallback_evidence(fallback_evidence)
    elif fallback_evidence is not None:
        raise LaunchError("--fallback-evidence is allowed only for origin-fallback")
    ensure_pristine(job, launch_plan)

    manager_log = Path(launch_plan["manager_log"])
    manager_log.parent.mkdir(parents=True, exist_ok=True)
    operator_dir = Path(launch_plan["operator_dir"])
    operator_dir.parent.mkdir(parents=True, exist_ok=True)
    os.mkdir(operator_dir)
    stdout_path = operator_dir / "stdout.log"
    stderr_path = operator_dir / "stderr.log"
    launch_receipt_path = operator_dir / "launch.json"
    preflight_path = operator_dir / "preflight.json"
    environment, environment_evidence = child_environment(manager_log)
    started_ns = time.time_ns()
    preflight = {
        "schema_version": 1,
        "kind": "h3-short-leg-preflight",
        "status": "READY",
        "started_at_ns": started_ns,
        "plan": launch_plan,
        "source_snapshots": snapshots,
        "offline_environment": environment_evidence,
        "fallback_evidence": evidence_descriptor,
    }
    write_exclusive(preflight_path, canonical_bytes(preflight))

    with stdout_path.open("xb") as stdout_handle, stderr_path.open("xb") as stderr_handle:
        process = subprocess.Popen(
            launch_plan["command"],
            cwd=str(ROOT),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        process_create_time = None
        try:
            import psutil

            process_create_time = psutil.Process(process.pid).create_time()
        except Exception:
            process_create_time = None
        returncode = process.wait()
    ended_ns = time.time_ns()

    retained: dict[str, Any] = {}
    for label, path in (
        ("stdout", stdout_path),
        ("stderr", stderr_path),
        ("manager_log", manager_log),
        ("result", job.result_path),
        ("alias", job.alias_path),
        ("artifact", job.artifact_path),
    ):
        retained[label] = stable_file(path) if path.is_file() else None
    result_summary = None
    if job.result_path.is_file():
        value = json.loads(job.result_path.read_text(encoding="utf-8"))
        result_summary = {
            key: value.get(key)
            for key in (
                "status",
                "gate_pass",
                "pass",
                "warm_pass",
                "valid_measurement",
                "run_number",
                "run_count",
                "config_run_count",
                "baseline_vram_gb",
                "peak_vram_gb",
                "absolute_peak_vram_gb",
                "net_peak_vram_gb",
                "elevated_baseline_lane",
                "baseline_lane_stamp",
                "duration_s",
            )
        }
    launch_receipt = {
        "schema_version": 1,
        "kind": "h3-short-leg-operator-launch",
        "status": "COMPLETE" if returncode == 0 else "FAILED",
        "job": job.key,
        "launch_id": launch_id,
        "process": {
            "pid": process.pid,
            "process_create_time": process_create_time,
            "started_at_ns": started_ns,
            "ended_at_ns": ended_ns,
            "returncode": returncode,
        },
        "plan": launch_plan,
        "source_snapshots": snapshots,
        "preflight": stable_file(preflight_path),
        "retained": retained,
        "result_summary": result_summary,
        "fallback_evidence": evidence_descriptor,
        "certification_effect": False,
        "quality_judgment": "PENDING_HUMAN",
    }
    write_exclusive(launch_receipt_path, canonical_bytes(launch_receipt))
    return returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", choices=sorted(JOBS), required=True)
    parser.add_argument("--launch-id", required=True)
    parser.add_argument("--fallback-evidence", type=Path)
    parser.add_argument("--run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    job = JOBS[args.job]
    launch_plan = plan(job, args.launch_id)
    if not args.run:
        print(json.dumps(launch_plan, indent=2, sort_keys=True))
        return 0
    return run(job, args.launch_id, args.fallback_evidence)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaunchError as exc:
        print(f"[H3 SHORT LEG REFUSED] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
