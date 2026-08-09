#!/usr/bin/env python
"""Measure one existing OTR single-clip render without changing OTR.

The sidecar launches an already-existing OTR probe command as a child, samples
machine-wide NVIDIA VRAM and host RAM every 200 ms, and writes one append-only
JSON evidence file.  It never boots, queries, or stops a server.  Before launch
it positively identifies the listener by PID and command line; port ownership
alone is not sufficient.

HuMo's native production artifact is silent and its path is generated inside
the engine.  For that route, point ``--artifact-report`` at OTR's durable
``node_single_<engine>.json`` report.  The report is snapshotted before launch,
must change after launch, and must resolve to a non-empty artifact whose mtime
also advances past the command start.  A direct known path can instead be given
with ``--artifact``.

This file is LAB-owned.  It may wrap OTR's existing render harness, but it must
never be copied into or imported by the OTR production repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Iterable, Sequence
import uuid

import psutil


DEFAULT_INTERVAL_S = 0.2
MIB = 1024.0**2
GIB = 1024.0**3


class SidecarError(RuntimeError):
    """A fail-closed measurement or ownership error."""


def utc_timestamp(epoch_ns: int | None = None) -> str:
    value = time.time_ns() if epoch_ns is None else int(epoch_ns)
    seconds, nanos = divmod(value, 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + f".{nanos:09d}Z"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(path: Path, *, include_hash: bool = True) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    if not path.is_file():
        return {"path": str(path), "exists": True, "is_file": False}
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "is_file": True,
        "bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }
    if include_hash:
        payload["sha256"] = sha256_file(path)
    return payload


def snapshot_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if not after.get("exists") or not after.get("is_file"):
        return False
    if not before.get("exists") or not before.get("is_file"):
        return True
    return any(
        before.get(field) != after.get(field)
        for field in ("bytes", "mtime_ns", "sha256")
    )


def nested_value(payload: Any, dotted_path: str) -> Any:
    value = payload
    for part in dotted_path.split("."):
        if not part:
            raise SidecarError(f"Invalid empty component in JSON path {dotted_path!r}")
        if not isinstance(value, dict) or part not in value:
            raise SidecarError(f"JSON path {dotted_path!r} is absent at {part!r}")
        value = value[part]
    return value


def _path_identity(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value))).rstrip("\\/")


def argv_flag_value(argv: Sequence[str], flag: str) -> str | None:
    for index, token in enumerate(argv):
        if token == flag:
            return argv[index + 1] if index + 1 < len(argv) else None
        prefix = flag + "="
        if token.startswith(prefix):
            return token[len(prefix) :]
    return None


def _listener_rows(port: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for connection in psutil.net_connections(kind="tcp"):
        if connection.status != psutil.CONN_LISTEN or not connection.laddr:
            continue
        if int(connection.laddr.port) != int(port):
            continue
        rows.append(
            {
                "address": str(connection.laddr.ip),
                "port": int(connection.laddr.port),
                "pid": int(connection.pid) if connection.pid else None,
            }
        )
    return rows


def identify_expected_otr_server(
    port: int,
    expected_model_paths: Path,
    expected_output_directory: Path,
) -> dict[str, Any]:
    """Return server identity only for the positively owned OTR headless lane."""

    listeners = _listener_rows(port)
    if not listeners:
        raise SidecarError(f"No listener owns requested OTR port {port}")
    if any(row["address"] not in {"127.0.0.1", "::1"} for row in listeners):
        raise SidecarError(f"Port {port} includes a non-loopback listener: {listeners}")
    pids = {row["pid"] for row in listeners}
    if None in pids or len(pids) != 1:
        raise SidecarError(f"Port {port} does not have exactly one identified owner: {listeners}")
    pid = int(next(iter(pids)))
    try:
        process = psutil.Process(pid)
        argv = process.cmdline()
        create_time = float(process.create_time())
        executable = process.exe()
        parent_pid = process.ppid()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        raise SidecarError(f"Cannot inspect listener PID {pid}: {exc}") from exc

    lowered = [str(token).lower() for token in argv]
    if not any(Path(token).name.lower() == "main.py" for token in argv):
        raise SidecarError(f"Listener PID {pid} is not a ComfyUI main.py process")
    port_value = argv_flag_value(argv, "--port")
    if port_value is None or int(port_value) != int(port):
        raise SidecarError(f"Listener PID {pid} argv does not pin --port {port}")
    model_paths = argv_flag_value(argv, "--extra-model-paths-config")
    if model_paths is None or _path_identity(model_paths) != _path_identity(expected_model_paths):
        raise SidecarError(
            f"Listener PID {pid} does not use expected OTR model-path config "
            f"{expected_model_paths}"
        )
    output_directory = argv_flag_value(argv, "--output-directory")
    if output_directory is None or _path_identity(output_directory) != _path_identity(
        expected_output_directory
    ):
        raise SidecarError(
            f"Listener PID {pid} does not use expected OTR output directory "
            f"{expected_output_directory}"
        )
    if not any("_otr_headless_model_paths.yaml" in token for token in lowered):
        raise SidecarError(f"Listener PID {pid} is not the OTR headless model-path lane")
    return {
        "serving_pid": pid,
        "process_create_time": create_time,
        "parent_pid": int(parent_pid),
        "executable": executable,
        "argv": argv,
        "listeners": listeners,
    }


def parse_gpu_csv(stdout: str, gpu_index: int) -> dict[str, float | int]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise SidecarError(f"nvidia-smi returned {len(lines)} rows for GPU {gpu_index}")
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) != 3:
        raise SidecarError(f"Unexpected nvidia-smi row: {lines[0]!r}")
    try:
        memory_used_mib = float(fields[0])
        memory_total_mib = float(fields[1])
        utilization_gpu_percent = float(fields[2])
    except ValueError as exc:
        raise SidecarError(f"Non-numeric nvidia-smi row: {lines[0]!r}") from exc
    values = (memory_used_mib, memory_total_mib, utilization_gpu_percent)
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise SidecarError(f"Invalid nvidia-smi values: {values!r}")
    return {
        "gpu_index": int(gpu_index),
        "vram_used_mib": memory_used_mib,
        "vram_total_mib": memory_total_mib,
        "gpu_utilization_percent": utilization_gpu_percent,
    }


def query_gpu(gpu_index: int) -> dict[str, float | int]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "-i",
            str(gpu_index),
            "--query-gpu=memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return parse_gpu_csv(result.stdout, gpu_index)


def query_machine_sample(gpu_index: int) -> dict[str, Any]:
    sampled_ns = time.time_ns()
    gpu = query_gpu(gpu_index)
    host = psutil.virtual_memory()
    return {
        "sampled_at_utc": utc_timestamp(sampled_ns),
        "sampled_at_ns": sampled_ns,
        **gpu,
        "host_ram_used_bytes": int(host.used),
        "host_ram_total_bytes": int(host.total),
    }


def process_identity(pid: int) -> dict[str, Any]:
    process = psutil.Process(pid)
    return {
        "pid": int(pid),
        "parent_pid": int(process.ppid()),
        "process_create_time": float(process.create_time()),
        "executable": process.exe(),
        "argv": process.cmdline(),
    }


class ResourceSampler(threading.Thread):
    """Fixed-cadence machine sampler with bounded error evidence."""

    def __init__(self, gpu_index: int, root_pid: int, interval_s: float) -> None:
        super().__init__(daemon=True)
        self.gpu_index = int(gpu_index)
        self.root_pid = int(root_pid)
        self.interval_s = float(interval_s)
        self.samples: list[dict[str, Any]] = []
        self.sample_error_count = 0
        self.sample_errors: list[str] = []
        self.processes: dict[tuple[int, float], dict[str, Any]] = {}
        self.peak_process_tree_rss_bytes = 0
        self._stop_event = threading.Event()

    def _record_process_tree(self) -> None:
        try:
            root = psutil.Process(self.root_pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        rss = 0
        for process in processes:
            try:
                identity = process_identity(process.pid)
                self.processes[(identity["pid"], identity["process_create_time"])] = identity
                rss += int(process.memory_info().rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self.peak_process_tree_rss_bytes = max(self.peak_process_tree_rss_bytes, rss)

    def run(self) -> None:
        next_sample = time.monotonic()
        while not self._stop_event.is_set():
            try:
                self.samples.append(query_machine_sample(self.gpu_index))
            except Exception as exc:  # noqa: BLE001 - preserve evidence, keep sampling
                self.sample_error_count += 1
                if len(self.sample_errors) < 20:
                    self.sample_errors.append(f"{type(exc).__name__}: {exc}")
            self._record_process_tree()
            next_sample += self.interval_s
            self._stop_event.wait(max(0.0, next_sample - time.monotonic()))

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=max(2.0, self.interval_s * 5))
        if self.is_alive():
            raise SidecarError("Resource sampler did not stop")

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            raise SidecarError("Resource sampler produced no valid samples")
        return {
            "interval_s": self.interval_s,
            "sample_count": len(self.samples),
            "sample_error_count": self.sample_error_count,
            "sample_errors": self.sample_errors,
            "peak_vram_mib": max(float(row["vram_used_mib"]) for row in self.samples),
            "peak_vram_gib": max(float(row["vram_used_mib"]) for row in self.samples) / 1024.0,
            "peak_host_ram_bytes": max(int(row["host_ram_used_bytes"]) for row in self.samples),
            "peak_host_ram_gib": max(int(row["host_ram_used_bytes"]) for row in self.samples) / GIB,
            "peak_process_tree_rss_bytes": self.peak_process_tree_rss_bytes,
            "peak_process_tree_rss_gib": self.peak_process_tree_rss_bytes / GIB,
            "observed_processes": sorted(
                self.processes.values(), key=lambda row: (row["process_create_time"], row["pid"])
            ),
            "samples": self.samples,
        }


def resolve_report_artifact(report: Path, dotted_path: str) -> Path:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SidecarError(f"Cannot read artifact report {report}: {exc}") from exc
    value = nested_value(payload, dotted_path)
    if not isinstance(value, str) or not value.strip():
        raise SidecarError(f"Artifact JSON path {dotted_path!r} is not a non-empty string")
    artifact = Path(value)
    if not artifact.is_absolute():
        raise SidecarError(f"Artifact report returned a non-absolute path: {artifact}")
    return artifact


def wait_for_artifact(
    *,
    started_ns: int,
    timeout_s: float,
    artifact: Path | None,
    artifact_before: dict[str, Any] | None,
    report: Path | None,
    report_before: dict[str, Any] | None,
    report_key: str,
) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    last_error = "artifact not observed"
    while True:
        report_after: dict[str, Any] | None = None
        candidate = artifact
        try:
            if report is not None:
                report_after = file_snapshot(report)
                if not snapshot_changed(report_before or {}, report_after):
                    raise SidecarError("artifact report did not advance")
                candidate = resolve_report_artifact(report, report_key)
            if candidate is None:
                raise SidecarError("artifact path was not resolved")
            candidate_after = file_snapshot(candidate, include_hash=False)
            if not candidate_after.get("is_file") or int(candidate_after.get("bytes") or 0) <= 0:
                raise SidecarError(f"artifact is absent or empty: {candidate}")
            if int(candidate_after.get("mtime_ns") or 0) < int(started_ns):
                raise SidecarError(f"artifact mtime did not advance past command start: {candidate}")
            if artifact is not None and not snapshot_changed(artifact_before or {}, candidate_after):
                raise SidecarError(f"direct artifact did not change: {candidate}")
            return candidate, candidate_after, report_after
        except SidecarError as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            raise SidecarError(f"Artifact proof timed out after {timeout_s:g}s: {last_error}")
        time.sleep(min(DEFAULT_INTERVAL_S, max(0.01, deadline - time.monotonic())))


def atomic_create_json(path: Path, payload: dict[str, Any]) -> None:
    """Publish complete UTF-8 JSON atomically without overwriting evidence."""

    if path.exists():
        raise FileExistsError(f"Sidecar evidence already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # A hard link publishes the already-complete inode and fails if the
        # append-only destination appeared concurrently.  Both paths are under
        # the same explicit output directory on the lab's NTFS volume.
        os.link(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def require_absolute_existing_file(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise SidecarError(f"{label} must be an absolute path: {path}")
    if not path.is_file():
        raise SidecarError(f"{label} does not exist as a file: {path}")
    return path


def validate_smoke_command(command: Sequence[str]) -> dict[str, Any]:
    if not command:
        raise SidecarError("No wrapped command supplied after --")
    script_indexes = [
        index for index, token in enumerate(command) if Path(token).name == "_otr_single_engine_smoke.py"
    ]
    if len(script_indexes) != 1:
        raise SidecarError("Wrapped command must invoke exactly one _otr_single_engine_smoke.py")
    engine = argv_flag_value(command, "--engine")
    if engine not in {"humo", "humo_1.7B", "humo_1.7B_169", "humo_14B_169"}:
        raise SidecarError(f"Wrapped smoke command is not an explicit HuMo engine: {engine!r}")
    portrait_value = argv_flag_value(command, "--portrait")
    audio_value = argv_flag_value(command, "--audio")
    if portrait_value is None or audio_value is None:
        raise SidecarError("Wrapped smoke command must pass --portrait and --audio")
    portrait = require_absolute_existing_file(portrait_value, "portrait fixture")
    audio = require_absolute_existing_file(audio_value, "audio fixture")
    frames_value = argv_flag_value(command, "--frames")
    try:
        frames = int(frames_value) if frames_value is not None else 25
    except ValueError as exc:
        raise SidecarError(f"Invalid --frames value: {frames_value!r}") from exc
    if frames < 33 or (frames - 1) % 4:
        raise SidecarError(f"HuMo frames must be a legal 4n+1 value >=33, got {frames}")
    buster_value = argv_flag_value(command, "--cache-buster")
    try:
        cache_buster = int(buster_value) if buster_value is not None else 0
    except ValueError as exc:
        raise SidecarError(f"Invalid --cache-buster value: {buster_value!r}") from exc
    if not 1 <= cache_buster <= 399:
        raise SidecarError(
            "HuMo measurement requires a unique --cache-buster in the live "
            "OTR_VideoRenderBatch range 1..399"
        )
    return {
        "engine": engine,
        "frames": frames,
        "request_seed": 7,
        "cache_buster": cache_buster,
        "portrait": str(portrait),
        "portrait_sha256": sha256_file(portrait),
        "audio": str(audio),
        "audio_sha256": sha256_file(audio),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="absolute append-only sidecar JSON path")
    parser.add_argument("--label", required=True)
    parser.add_argument("--boot-lane", required=True)
    parser.add_argument("--cwd", required=True, help="absolute working directory for the smoke command")
    parser.add_argument("--server-port", required=True, type=int)
    parser.add_argument("--expected-server-model-paths", required=True)
    parser.add_argument("--expected-server-output", required=True)
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--interval-s", type=float, default=DEFAULT_INTERVAL_S)
    parser.add_argument("--artifact-wait-s", type=float, default=30.0)
    artifact_group = parser.add_mutually_exclusive_group(required=True)
    artifact_group.add_argument("--artifact", help="absolute known artifact path")
    artifact_group.add_argument("--artifact-report", help="absolute JSON report resolving the artifact")
    parser.add_argument("--artifact-json-path", default="clip.path")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def run(argv: Sequence[str] | None = None) -> tuple[int, dict[str, Any]]:
    args = parse_args(argv)
    output = Path(args.output)
    cwd = Path(args.cwd)
    model_paths = Path(args.expected_server_model_paths)
    server_output = Path(args.expected_server_output)
    artifact = Path(args.artifact) if args.artifact else None
    report = Path(args.artifact_report) if args.artifact_report else None

    for path, label in (
        (output, "output"),
        (cwd, "cwd"),
        (model_paths, "expected server model paths"),
        (server_output, "expected server output"),
        *(([(artifact, "artifact")] if artifact is not None else [])),
        *(([(report, "artifact report")] if report is not None else [])),
    ):
        if path is not None and not path.is_absolute():
            raise SidecarError(f"{label} path must be absolute: {path}")
    if output.exists():
        raise FileExistsError(f"Sidecar evidence already exists: {output}")
    if not cwd.is_dir():
        raise SidecarError(f"Working directory does not exist: {cwd}")
    if not model_paths.is_file():
        raise SidecarError(f"Expected model-path config does not exist: {model_paths}")
    if not server_output.is_dir():
        raise SidecarError(f"Expected server output directory does not exist: {server_output}")
    if args.interval_s <= 0:
        raise SidecarError("Sampling interval must be positive")

    command_contract = validate_smoke_command(args.command)
    server = identify_expected_otr_server(args.server_port, model_paths, server_output)
    baseline = query_machine_sample(args.gpu_index)
    artifact_before = file_snapshot(artifact) if artifact is not None else None
    report_before = file_snapshot(report) if report is not None else None

    started_ns = time.time_ns()
    started_monotonic = time.monotonic()
    process: subprocess.Popen[Any] | None = None
    sampler: ResourceSampler | None = None
    artifact_path: Path | None = None
    artifact_after: dict[str, Any] | None = None
    report_after: dict[str, Any] | None = None
    error = ""
    returncode: int | None = None
    command_identity: dict[str, Any] = {}
    try:
        process = subprocess.Popen(args.command, cwd=str(cwd))
        command_identity = process_identity(process.pid)
        sampler = ResourceSampler(args.gpu_index, process.pid, args.interval_s)
        sampler.start()
        returncode = int(process.wait())
        artifact_path, artifact_after, report_after = wait_for_artifact(
            started_ns=started_ns,
            timeout_s=args.artifact_wait_s,
            artifact=artifact,
            artifact_before=artifact_before,
            report=report,
            report_before=report_before,
            report_key=args.artifact_json_path,
        )
    except Exception as exc:  # noqa: BLE001 - receipt the precise terminal failure
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except Exception as exc:  # noqa: BLE001
                error = error or f"{type(exc).__name__}: {exc}"
    finished_ns = time.time_ns()

    sampler_summary: dict[str, Any] = {}
    if sampler is not None:
        try:
            sampler_summary = sampler.summary()
        except Exception as exc:  # noqa: BLE001
            error = error or f"{type(exc).__name__}: {exc}"
    if artifact_path is not None and artifact_after is not None:
        artifact_after = {**artifact_after, "sha256": sha256_file(artifact_path)}
    if report is not None and report_after is not None:
        report_after = {**report_after, "sha256": sha256_file(report)}

    command_duration_s = time.monotonic() - started_monotonic
    artifact_mtime_ns = int((artifact_after or {}).get("mtime_ns") or 0)
    render_to_artifact_s = (
        (artifact_mtime_ns - started_ns) / 1_000_000_000.0 if artifact_mtime_ns else None
    )
    status = "ok" if returncode == 0 and artifact_after is not None and not error else "failed"
    receipt: dict[str, Any] = {
        "sidecar_schema_version": 1,
        "measured": "otr-side production lane",
        "label": args.label,
        "status": status,
        "error": error,
        "boot_lane": args.boot_lane,
        "gpu_index": int(args.gpu_index),
        "started_at_utc": utc_timestamp(started_ns),
        "finished_at_utc": utc_timestamp(finished_ns),
        "command_duration_s": round(command_duration_s, 6),
        "render_to_artifact_s": (
            round(render_to_artifact_s, 6) if render_to_artifact_s is not None else None
        ),
        "command_returncode": returncode,
        "command": list(args.command),
        "command_process": command_identity,
        "command_contract": command_contract,
        "server_instance": server,
        "baseline_vram_mib": float(baseline["vram_used_mib"]),
        "baseline_vram_gib": float(baseline["vram_used_mib"]) / 1024.0,
        "baseline_host_ram_bytes": int(baseline["host_ram_used_bytes"]),
        "baseline_host_ram_gib": int(baseline["host_ram_used_bytes"]) / GIB,
        "baseline_sample": baseline,
        "sampler": sampler_summary,
        "artifact_report_before": report_before,
        "artifact_report_after": report_after,
        "artifact_before": artifact_before,
        "artifact_after": artifact_after,
    }
    atomic_create_json(output, receipt)
    return (0 if status == "ok" else 1), receipt


def main(argv: Sequence[str] | None = None) -> int:
    try:
        code, receipt = run(argv)
    except Exception as exc:  # validation failed before an output contract existed
        print(f"[otr-sidecar] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2
    print(
        "[otr-sidecar] %s label=%s render_to_artifact_s=%s peak_vram_gib=%s "
        "peak_host_ram_gib=%s"
        % (
            receipt["status"].upper(),
            receipt["label"],
            receipt["render_to_artifact_s"],
            (receipt.get("sampler") or {}).get("peak_vram_gib"),
            (receipt.get("sampler") or {}).get("peak_host_ram_gib"),
        ),
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
