#!/usr/bin/env python
"""Measure one OTR node-92 retention leg at 200 ms cadence.

This LAB-owned sidecar wraps the existing OTR ``otr_visual_smoke.py replay``
command.  It acquires the lab GPU lease, positively identifies the already
booted OTR server, timestamps child stdout, tails only server-log bytes appended
during the leg, samples machine VRAM/RAM through a post-terminal settle window,
and publishes one immutable raw telemetry receipt.

It does not boot, stop, or modify OTR and performs no phase inference.  A later
receipt builder derives phases from the retained observation-time log events.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence


LAB_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = LAB_ROOT / "scratch"
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
OTR_VISUAL_SMOKE = OTR_ROOT / "scripts" / "otr_visual_smoke.py"
TELEMETRY_ROOT = LAB_ROOT / "results" / "otr_side" / "wan_retention" / "telemetry"
EXPECTED_BUNDLE_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_retention_measurement"
)
DEFAULT_INTERVAL_S = 0.2
DEFAULT_SETTLE_S = 12.0
DEFAULT_MAX_GAP_S = 0.75


class SidecarError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SidecarError(f"Cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load("humo_diet_sidecar_shared", SCRATCH / "humo_diet_sidecar.py")
OTR_SIDE = _load("otr_resource_sidecar_shared", SCRATCH / "otr_resource_sidecar.py")
sys.path.insert(0, str(LAB_ROOT))
from lab_locks import GpuLease, LeaseError  # noqa: E402


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _within(path: Path, root: Path, label: str) -> Path:
    candidate = _absolute(path)
    boundary = _absolute(root)
    try:
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise SidecarError(f"{label} escapes {boundary}: {candidate}") from exc
    return candidate


def _flag_value(command: Sequence[str], flag: str) -> str | None:
    for index, token in enumerate(command):
        if token == flag:
            return command[index + 1] if index + 1 < len(command) else None
        if token.startswith(flag + "="):
            return token[len(flag) + 1 :]
    return None


def validate_command(command: Sequence[str], engine: str) -> dict[str, Any]:
    if not command:
        raise SidecarError("Missing wrapped replay command")
    python = Path(command[0])
    if not python.is_absolute() or not python.is_file() or "python" not in python.name.lower():
        raise SidecarError("Wrapped command must use an absolute Python executable")
    if len(command) < 4 or command[1] != "-u":
        raise SidecarError("Wrapped command must use Python -u for timestamped stdout")
    script = Path(command[2])
    if _absolute(script) != _absolute(OTR_VISUAL_SMOKE):
        raise SidecarError(f"Wrapped command must use existing OTR harness {OTR_VISUAL_SMOKE}")
    if command[3] != "replay":
        raise SidecarError("Wrapped OTR harness command must be replay")
    bundle_text = _flag_value(command, "--bundle")
    if not bundle_text:
        raise SidecarError("Replay command must supply --bundle")
    bundle = _within(Path(bundle_text), EXPECTED_BUNDLE_ROOT, "bundle")
    if bundle.name not in {
        "long_first",
        "small_first",
        "long_first_planned",
        "small_first_planned",
        "fastwan_8gb_long_first_planned",
        "ltx_video_long_first_planned",
    }:
        raise SidecarError(f"Unexpected retention bundle identity: {bundle}")
    manifest = bundle / "bundle_manifest.json"
    ledger = bundle / "baked_ledger.json"
    fixture = bundle / "fixture_contract.json"
    master = bundle / "master.wav"
    for path in (manifest, ledger, fixture, master):
        if not path.is_file():
            raise SidecarError(f"Bundle evidence is missing: {path}")
    ledger_payload = json.loads(ledger.read_text(encoding="utf-8"))
    ledger_engines = {
        str(shot.get("engine_id") or "")
        for shot in (((ledger_payload.get("video") or {}).get("shots")) or [])
        if isinstance(shot, dict)
    }
    if ledger_engines != {engine}:
        raise SidecarError(
            f"Bundle engine binding {sorted(ledger_engines)!r} does not equal {engine!r}"
        )
    timeout = _flag_value(command, "--timeout")
    if timeout is None or int(timeout) < 60:
        raise SidecarError("Replay command must set an explicit timeout >= 60 seconds")
    if _flag_value(command, "--engine") is not None:
        raise SidecarError(
            "--engine is inert in episode mode; engine must be bound by "
            "baked_ledger.video.shots[].engine_id"
        )
    return {
        "argv": list(command),
        "python": str(python),
        "python_sha256": BASE.sha256_file(python),
        "otr_harness": str(script),
        "otr_harness_sha256": BASE.sha256_file(script),
        "engine": engine,
        "engine_binding": "baked_ledger.video.shots[].engine_id",
        "server_bound_force_map": None,
        "bundle": str(bundle),
        "bundle_order": bundle.name,
        "bundle_manifest_sha256": BASE.sha256_file(manifest),
        "baked_ledger_sha256": BASE.sha256_file(ledger),
        "fixture_contract_sha256": BASE.sha256_file(fixture),
        "master_audio_sha256": BASE.sha256_file(master),
        "timeout_s": int(timeout),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--engine", required=True, choices=("wan_ti2v", "fastwan_8gb", "ltx_video", "humo")
    )
    parser.add_argument("--boot-lane", required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--expected-server-model-paths", required=True)
    parser.add_argument("--expected-server-output", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--interval-s", type=float, default=DEFAULT_INTERVAL_S)
    parser.add_argument("--settle-s", type=float, default=DEFAULT_SETTLE_S)
    parser.add_argument("--max-sample-gap-s", type=float, default=DEFAULT_MAX_GAP_S)
    parser.add_argument(
        "--expected-outcome", choices=("success", "refusal", "either"), default="either"
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def _validate_output(value: str) -> Path:
    output = _within(Path(value), TELEMETRY_ROOT, "telemetry output")
    if not output.is_absolute() or output.suffix.lower() != ".json":
        raise SidecarError("Telemetry output must be an absolute JSON path")
    if output.exists():
        raise FileExistsError(f"Telemetry evidence already exists: {output}")
    return output


def _stream(pipe: Any, events: list[dict[str, Any]], errors: list[str]) -> None:
    BASE._stream_child_stdout(pipe, events, errors)


def run(
    argv: Sequence[str] | None = None,
    *,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    sample_query: Callable[[int], dict[str, Any]] = BASE.query_machine_sample,
) -> tuple[int, dict[str, Any]]:
    args = parse_args(argv)
    output = _validate_output(args.output)
    if args.server_port != 8000:
        raise SidecarError("OTR production measurement is pinned to port 8000")
    if args.interval_s != 0.2:
        raise SidecarError("Mission requires exactly 200 ms sampling")
    if args.settle_s < 5.0:
        raise SidecarError("Post-terminal settle window must be at least five seconds")
    command = validate_command(args.command, args.engine)
    model_paths = Path(args.expected_server_model_paths)
    server_output = Path(args.expected_server_output)
    server_log = Path(args.server_log)
    for path, label, is_dir in (
        (model_paths, "model paths", False),
        (server_output, "server output", True),
        (server_log, "server log", False),
    ):
        if not path.is_absolute() or not (path.is_dir() if is_dir else path.is_file()):
            raise SidecarError(f"Missing absolute {label}: {path}")

    lease = GpuLease(
        LAB_ROOT / ".gpu.lock",
        LAB_ROOT / ".suite.lock",
        LAB_ROOT / ".coordinator.mutex",
    )
    lease_owner: dict[str, Any] | None = None
    lease_release = {"success": False, "error": "not attempted"}
    process: Any | None = None
    sampler: Any | None = None
    stdout_thread: threading.Thread | None = None
    stdout_events: list[dict[str, Any]] = []
    stdout_errors: list[str] = []
    errors: list[str] = []
    returncode: int | None = None
    server: dict[str, Any] = {}
    baseline: dict[str, Any] = {}
    log_summary: dict[str, Any] = {}
    samples: list[dict[str, Any]] = []
    report_before: dict[str, Any] = {}
    report_after: dict[str, Any] = {}
    manifest_before: dict[str, Any] = {}
    manifest_after: dict[str, Any] = {}
    started_ns = time.time_ns()
    started_mono_ns = time.monotonic_ns()
    child_end_ns = started_ns
    child_end_mono_ns = started_mono_ns
    telemetry_end_ns = started_ns
    telemetry_end_mono_ns = started_mono_ns
    log_tail: Any | None = None
    report_path = Path(args.expected_server_output) / "otr" / "episodes" / "_shared" / "state" / "node_episode_report.json"
    manifest_path = report_path.with_name("node_episode_manifest.json")
    try:
        lease.acquire()
        lease_owner = dict(lease.owner or {})
        server = OTR_SIDE.identify_expected_otr_server(
            args.server_port, model_paths, server_output
        )
        baseline = sample_query(args.gpu_index)
        report_before = BASE.stable_file_snapshot(report_path)
        manifest_before = BASE.stable_file_snapshot(manifest_path)
        log_start = BASE.stable_file_snapshot(server_log)
        log_tail = BASE.AppendOnlyLogTail(server_log, log_start)
        started_ns = time.time_ns()
        started_mono_ns = time.monotonic_ns()
        process = popen_factory(
            list(args.command),
            cwd=str(OTR_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        if process.stdout is None:
            raise SidecarError("Wrapped replay did not expose stdout")
        stdout_thread = threading.Thread(
            target=_stream,
            args=(process.stdout, stdout_events, stdout_errors),
            daemon=True,
        )
        stdout_thread.start()
        sampler = BASE.ObservationSampler(
            args.gpu_index,
            args.interval_s,
            log_tail,
            sample_query=sample_query,
        )
        sampler.start()
        returncode = int(process.wait())
        child_end_ns = time.time_ns()
        child_end_mono_ns = time.monotonic_ns()
        # The requested inter-shot diagnosis depends on what remains after the
        # terminal result, not just the peak.  Keep the same sampler and log tail
        # alive through a fixed settle window.
        deadline = time.monotonic() + float(args.settle_s)
        while time.monotonic() < deadline:
            time.sleep(min(0.1, deadline - time.monotonic()))
    except BaseException as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        if process is not None and getattr(process, "poll", lambda: 0)() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception as terminate_exc:
                errors.append(f"child termination failed: {terminate_exc}")
        child_end_ns = time.time_ns()
        child_end_mono_ns = time.monotonic_ns()
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except Exception as exc:
                errors.append(f"sampler stop failed: {exc}")
            samples = list(sampler.samples)
            errors.extend(sampler.errors)
        if stdout_thread is not None:
            stdout_thread.join(timeout=10)
            if stdout_thread.is_alive():
                errors.append("stdout reader did not stop")
        telemetry_end_ns = time.time_ns()
        telemetry_end_mono_ns = time.monotonic_ns()
        if log_tail is not None:
            log_summary = log_tail.finish()
            errors.extend(log_summary.get("errors") or [])
        report_after = BASE.stable_file_snapshot(report_path)
        manifest_after = BASE.stable_file_snapshot(manifest_path)
        try:
            lease.release()
            lease_release = {"success": True, "error": ""}
        except (LeaseError, Exception) as exc:
            lease_release = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
            errors.append(f"GPU lease release failed: {exc}")

    errors.extend(stdout_errors)
    try:
        sample_summary = BASE.summarize_samples(
            samples,
            baseline=baseline,
            child_start_mono_ns=started_mono_ns,
            child_end_mono_ns=telemetry_end_mono_ns,
            interval_s=args.interval_s,
            max_gap_s=args.max_sample_gap_s,
            sample_errors=[],
        )
        errors.extend(sample_summary.get("coverage_errors") or [])
    except Exception as exc:
        sample_summary = {"samples": samples, "coverage_errors": [str(exc)]}
        errors.append(f"sample summary failed: {exc}")

    appended_text = "\n".join(
        str(event.get("text") or "") for event in (log_summary.get("events") or [])
    )
    refusal_found = "NO silent resize" in appended_text and "MotionBudgetError" in appended_text
    long_chain_proved = (
        "BEAT shot_b001 assembled from 2 chain segment(s) -> 200 frame(s)" in appended_text
    )
    small_refusal_proved = (
        "shot shot_b003" in appended_text
        and "static frame budget 65 (snapped 65)" in appended_text
        and refusal_found
    )
    success_found = returncode == 0 and "[smoke] PASS" in "\n".join(
        str(event.get("text") or "") for event in stdout_events
    )
    if args.expected_outcome == "refusal" and not (
        returncode != 0 and long_chain_proved and small_refusal_proved
    ):
        errors.append(
            "Expected retention reproduction was not proved: require a completed "
            "177+25 two-segment 200-frame long beat followed by the 65-frame "
            "small-shot S4 refusal"
        )
    if args.expected_outcome == "success" and not success_found:
        errors.append("Expected successful replay was not proved")
    if args.expected_outcome == "either" and not (
        success_found or (returncode != 0 and long_chain_proved and small_refusal_proved)
    ):
        errors.append(
            "Neither a successful full replay nor the exact post-chain 65-frame "
            "S4 refusal was proved"
        )

    receipt = {
        "sidecar_schema_version": 1,
        "kind": "wan-inter-shot-retention-raw-telemetry",
        "sidecar_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": BASE.sha256_file(Path(__file__).resolve()),
        },
        "measured": "otr-side production wrapper",
        "label": args.label,
        "status": "measured" if not errors else "invalid",
        "errors": errors,
        "expected_outcome": args.expected_outcome,
        "observed_outcome": "refusal" if refusal_found else ("success" if success_found else "unproved"),
        "retention_reproduction_evidence": {
            "long_chain_200_proved": long_chain_proved,
            "small_shot_65_refusal_proved": small_refusal_proved,
        },
        "boot_lane": args.boot_lane,
        "engine": args.engine,
        "started_at_ns": started_ns,
        "started_at_utc": BASE.utc_timestamp(started_ns),
        "child_finished_at_ns": child_end_ns,
        "child_finished_at_utc": BASE.utc_timestamp(child_end_ns),
        "telemetry_finished_at_ns": telemetry_end_ns,
        "telemetry_finished_at_utc": BASE.utc_timestamp(telemetry_end_ns),
        "child_duration_s": round((child_end_mono_ns - started_mono_ns) / 1e9, 9),
        "post_terminal_settle_s": float(args.settle_s),
        "command_returncode": returncode,
        "command": command,
        "server_instance": server,
        "gpu_lease": {"owner": lease_owner, "release": lease_release},
        "baseline": baseline,
        "sampler": sample_summary,
        "child_stdout": {
            "timestamps_are_observation_times": True,
            "event_count": len(stdout_events),
            "errors": stdout_errors,
            "events": stdout_events,
        },
        "server_log": log_summary,
        "node_episode_report_before": report_before,
        "node_episode_report_after": report_after,
        "node_episode_manifest_before": manifest_before,
        "node_episode_manifest_after": manifest_after,
        "phase_inference": {
            "performed": False,
            "reason": "Raw samples and observation-time log events retained for deterministic reduction.",
        },
    }
    BASE.atomic_create_json(output, receipt)
    return (0 if receipt["status"] == "measured" else 1), receipt


def main(argv: Sequence[str] | None = None) -> int:
    try:
        code, receipt = run(argv)
    except Exception as exc:
        print(f"[wan-retention-sidecar] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "[wan-retention-sidecar] %s label=%s outcome=%s peak_vram_gib=%s samples=%s"
        % (
            receipt["status"].upper(),
            receipt["label"],
            receipt["observed_outcome"],
            receipt.get("sampler", {}).get("peak_vram_gib"),
            receipt.get("sampler", {}).get("sample_count"),
        ),
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
