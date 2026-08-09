#!/usr/bin/env python
"""Capture Phase-1 HuMo diet telemetry around one existing run_recipe.py run.

This LAB-owned sidecar does not boot, query, or stop ComfyUI itself.  It launches
the exact caller-supplied ``run_recipe.py`` command without a shell, samples
machine VRAM and RAM at 200 ms cadence, timestamps child stdout, and tails only
bytes appended to ``server.log`` during the child lifetime.  After the child
exits it independently binds the one new immutable run archive, its current
alias, and the artifact named and hashed by that archive.

No phase labels are inferred here.  The raw samples and observed log/stdout
events are retained so a later, evidence-driven pass can derive phases.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence
import uuid

import psutil


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERVAL_S = 0.2
DEFAULT_MAX_GAP_S = 0.75
MIB = 1024**2
GIB = 1024**3


class SidecarError(RuntimeError):
    """A fail-closed telemetry, path, or evidence-binding error."""


def utc_timestamp(epoch_ns: int | None = None) -> str:
    value = time.time_ns() if epoch_ns is None else int(epoch_ns)
    seconds, nanos = divmod(value, 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + f".{nanos:09d}Z"


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def require_within(path: Path, root: Path, label: str) -> Path:
    candidate = _lexical_absolute(path)
    boundary = _lexical_absolute(root)
    try:
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise SidecarError(f"{label} escapes {boundary}: {candidate}") from exc
    return candidate


def require_safe_chain(path: Path, root: Path, label: str) -> None:
    candidate = require_within(path, root, label)
    boundary = _lexical_absolute(root)
    cursor = candidate
    while True:
        if cursor.exists() and _is_reparse_point(cursor):
            raise SidecarError(f"{label} contains a symlink or reparse point: {cursor}")
        if cursor == boundary:
            break
        cursor = cursor.parent


def stable_file_snapshot(path: Path, *, attempts: int = 3) -> dict[str, Any]:
    """Hash a file only when size/mtime/identity stay fixed across the read."""

    for _ in range(max(1, attempts)):
        try:
            before = path.stat()
        except FileNotFoundError:
            return {"path": str(path), "exists": False, "bytes": 0, "sha256": None}
        if not path.is_file() or _is_reparse_point(path):
            raise SidecarError(f"Evidence path is not a regular non-reparse file: {path}")
        digest = sha256_file(path)
        after = path.stat()
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before == identity_after:
            return {
                "path": str(path),
                "exists": True,
                "bytes": int(after.st_size),
                "mtime_ns": int(after.st_mtime_ns),
                "device": int(after.st_dev),
                "inode": int(after.st_ino),
                "sha256": digest,
            }
    raise SidecarError(f"File changed while it was being hashed: {path}")


def atomic_create_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Telemetry evidence already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json_bytes(payload)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def parse_gpu_csv(stdout: str, gpu_index: int) -> dict[str, float | int]:
    rows = [row.strip() for row in stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise SidecarError(f"nvidia-smi returned {len(rows)} rows for GPU {gpu_index}")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 2:
        raise SidecarError(f"Unexpected nvidia-smi row: {rows[0]!r}")
    try:
        used_mib, total_mib = (float(field) for field in fields)
    except ValueError as exc:
        raise SidecarError(f"Non-numeric nvidia-smi row: {rows[0]!r}") from exc
    if not all(math.isfinite(value) and value >= 0 for value in (used_mib, total_mib)):
        raise SidecarError(f"Invalid nvidia-smi values: {(used_mib, total_mib)!r}")
    if used_mib > total_mib:
        raise SidecarError(f"nvidia-smi used memory exceeds total: {used_mib} > {total_mib}")
    return {
        "gpu_index": int(gpu_index),
        "vram_used_mib": used_mib,
        "vram_total_mib": total_mib,
    }


def query_gpu(gpu_index: int) -> dict[str, float | int]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "-i",
            str(gpu_index),
            "--query-gpu=memory.used,memory.total",
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
    sampled_monotonic_ns = time.monotonic_ns()
    gpu = query_gpu(gpu_index)
    host = psutil.virtual_memory()
    return {
        "sampled_at_ns": sampled_ns,
        "sampled_at_utc": utc_timestamp(sampled_ns),
        "sampled_monotonic_ns": sampled_monotonic_ns,
        **gpu,
        "host_ram_used_bytes": int(host.used),
        "host_ram_total_bytes": int(host.total),
    }


def _decode_line(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


class AppendOnlyLogTail:
    """Observe only bytes appended after the starting server.log size."""

    def __init__(self, path: Path, starting: dict[str, Any]) -> None:
        self.path = path
        self.starting = starting
        self.offset = int(starting.get("bytes") or 0)
        self._identity = (
            (int(starting["device"]), int(starting["inode"]))
            if starting.get("exists")
            else None
        )
        self._pending = b""
        self._pending_start = self.offset
        self._new_digest = hashlib.sha256()
        self.new_bytes = 0
        self.events: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def _emit(self, raw: bytes, start_offset: int, observed_ns: int, observed_mono_ns: int) -> None:
        self.events.append(
            {
                "observed_at_ns": int(observed_ns),
                "observed_at_utc": utc_timestamp(observed_ns),
                "observed_monotonic_ns": int(observed_mono_ns),
                "start_offset": int(start_offset),
                "end_offset": int(start_offset + len(raw)),
                "byte_count": len(raw),
                "raw_base64": base64.b64encode(raw).decode("ascii"),
                "raw_sha256": sha256_bytes(raw),
                "text": _decode_line(raw),
            }
        )

    def poll(self, observed_ns: int | None = None, observed_mono_ns: int | None = None) -> None:
        wall_ns = time.time_ns() if observed_ns is None else int(observed_ns)
        mono_ns = time.monotonic_ns() if observed_mono_ns is None else int(observed_mono_ns)
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            if self._identity is not None:
                self.errors.append("server.log disappeared after observation began")
            return
        if not self.path.is_file() or _is_reparse_point(self.path):
            self.errors.append("server.log is not a regular non-reparse file")
            return
        identity = (int(stat.st_dev), int(stat.st_ino))
        if self._identity is None:
            self._identity = identity
        elif identity != self._identity:
            self.errors.append("server.log identity changed during child lifetime")
            return
        if stat.st_size < self.offset:
            self.errors.append(
                f"server.log truncated from observed offset {self.offset} to {stat.st_size}"
            )
            return
        if stat.st_size == self.offset:
            return
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            appended = handle.read(stat.st_size - self.offset)
        if len(appended) != stat.st_size - self.offset:
            self.errors.append("short read while tailing server.log")
            return
        chunk_start = self.offset
        self.offset += len(appended)
        self.new_bytes += len(appended)
        self._new_digest.update(appended)
        combined = self._pending + appended
        combined_start = self._pending_start if self._pending else chunk_start
        cursor = 0
        while True:
            newline = combined.find(b"\n", cursor)
            if newline < 0:
                break
            raw = combined[cursor : newline + 1]
            self._emit(raw, combined_start + cursor, wall_ns, mono_ns)
            cursor = newline + 1
        self._pending = combined[cursor:]
        self._pending_start = combined_start + cursor

    def finish(self) -> dict[str, Any]:
        ending: dict[str, Any] = {}
        for _ in range(3):
            self.poll()
            ending = stable_file_snapshot(self.path)
            if not ending.get("exists") or int(ending["bytes"]) == self.offset:
                break
        else:
            self.errors.append(
                f"server.log did not stabilize at tailed offset {self.offset}: {ending['bytes']}"
            )
        if self._pending:
            observed_ns = time.time_ns()
            observed_mono_ns = time.monotonic_ns()
            self._emit(self._pending, self._pending_start, observed_ns, observed_mono_ns)
            self._pending = b""
        if ending.get("exists") and int(ending["bytes"]) != self.offset:
            self.errors.append(
                f"server.log did not stabilize at tailed offset {self.offset}: {ending['bytes']}"
            )
        if not self.starting.get("exists") and ending.get("exists"):
            expected_new_bytes = int(ending["bytes"])
        else:
            expected_new_bytes = int(ending.get("bytes") or 0) - int(
                self.starting.get("bytes") or 0
            )
        if expected_new_bytes != self.new_bytes:
            self.errors.append(
                f"server.log appended-byte mismatch: tailed={self.new_bytes} expected={expected_new_bytes}"
            )
        return {
            "starting": self.starting,
            "ending": ending,
            "new_byte_count": self.new_bytes,
            "new_bytes_sha256": self._new_digest.hexdigest(),
            "event_count": len(self.events),
            "events": self.events,
            "errors": self.errors,
            "timestamps_are_observation_times": True,
        }


class ObservationSampler(threading.Thread):
    def __init__(
        self,
        gpu_index: int,
        interval_s: float,
        log_tail: AppendOnlyLogTail,
        sample_query: Callable[[int], dict[str, Any]] = query_machine_sample,
    ) -> None:
        super().__init__(daemon=True)
        self.gpu_index = int(gpu_index)
        self.interval_s = float(interval_s)
        self.log_tail = log_tail
        self.sample_query = sample_query
        self.samples: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self._stop_event = threading.Event()

    def _observe_once(self) -> None:
        try:
            sample = dict(self.sample_query(self.gpu_index))
            if "sampled_monotonic_ns" not in sample:
                sample["sampled_monotonic_ns"] = time.monotonic_ns()
            if "sampled_at_ns" not in sample:
                sample["sampled_at_ns"] = time.time_ns()
            if "sampled_at_utc" not in sample:
                sample["sampled_at_utc"] = utc_timestamp(sample["sampled_at_ns"])
            self.samples.append(sample)
            self.log_tail.poll(sample["sampled_at_ns"], sample["sampled_monotonic_ns"])
        except Exception as exc:  # noqa: BLE001 - record and fail the final receipt
            self.errors.append(f"{type(exc).__name__}: {exc}")

    def run(self) -> None:
        next_sample = time.monotonic()
        while not self._stop_event.is_set():
            self._observe_once()
            next_sample += self.interval_s
            self._stop_event.wait(max(0.0, next_sample - time.monotonic()))

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=max(2.0, self.interval_s * 5))
        if self.is_alive():
            raise SidecarError("Telemetry sampler did not stop")
        self._observe_once()


def summarize_samples(
    samples: Sequence[dict[str, Any]],
    *,
    baseline: dict[str, Any],
    child_start_mono_ns: int,
    child_end_mono_ns: int,
    interval_s: float,
    max_gap_s: float,
    sample_errors: Sequence[str],
) -> dict[str, Any]:
    if not samples:
        raise SidecarError("Telemetry sampler produced no valid samples")
    ordered = sorted(samples, key=lambda row: int(row["sampled_monotonic_ns"]))
    monotonic_values = [int(row["sampled_monotonic_ns"]) for row in ordered]
    gaps = [
        (right - left) / 1_000_000_000.0
        for left, right in zip(monotonic_values, monotonic_values[1:])
    ]
    start_gap = max(0.0, (monotonic_values[0] - child_start_mono_ns) / 1_000_000_000.0)
    end_gap = max(0.0, (child_end_mono_ns - monotonic_values[-1]) / 1_000_000_000.0)
    largest = max([start_gap, end_gap, *gaps], default=0.0)
    coverage_errors = list(sample_errors)
    if largest > max_gap_s:
        coverage_errors.append(
            f"sample gap {largest:.6f}s exceeds maximum {max_gap_s:.6f}s"
        )
    peak_vram_mib = max(float(row["vram_used_mib"]) for row in ordered)
    peak_host_bytes = max(int(row["host_ram_used_bytes"]) for row in ordered)
    return {
        "interval_s": float(interval_s),
        "maximum_allowed_gap_s": float(max_gap_s),
        "sample_count": len(ordered),
        "sample_error_count": len(sample_errors),
        "sample_errors": list(sample_errors),
        "start_to_first_sample_s": round(start_gap, 9),
        "max_inter_sample_gap_s": round(max(gaps, default=0.0), 9),
        "last_sample_to_child_end_s": round(end_gap, 9),
        "largest_coverage_gap_s": round(largest, 9),
        "coverage_errors": coverage_errors,
        "baseline_vram_mib": float(baseline["vram_used_mib"]),
        "baseline_host_ram_bytes": int(baseline["host_ram_used_bytes"]),
        "peak_vram_mib": peak_vram_mib,
        "peak_vram_gib": peak_vram_mib / 1024.0,
        "peak_host_ram_bytes": peak_host_bytes,
        "peak_host_ram_gib": peak_host_bytes / GIB,
        "samples": ordered,
    }


def _stream_child_stdout(pipe: Any, events: list[dict[str, Any]], errors: list[str]) -> None:
    try:
        while True:
            raw = pipe.readline()
            if not raw:
                break
            if isinstance(raw, str):
                raw = raw.encode("utf-8", errors="replace")
            observed_ns = time.time_ns()
            observed_mono_ns = time.monotonic_ns()
            text = _decode_line(raw)
            event = {
                "observed_at_ns": observed_ns,
                "observed_at_utc": utc_timestamp(observed_ns),
                "observed_monotonic_ns": observed_mono_ns,
                "byte_count": len(raw),
                "raw_base64": base64.b64encode(raw).decode("ascii"),
                "raw_sha256": sha256_bytes(raw),
                "text": text,
            }
            events.append(event)
            print(f"[child {event['observed_at_utc']}] {text}", flush=True)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")


def _resolve_command_path(token: str, repo_root: Path) -> Path:
    path = Path(token)
    return _lexical_absolute(path if path.is_absolute() else repo_root / path)


def validate_command(command: Sequence[str], repo_root: Path) -> dict[str, Any]:
    if not command:
        raise SidecarError("No run_recipe.py child command supplied after --")
    executable = Path(command[0])
    if not executable.is_absolute() or not executable.is_file() or _is_reparse_point(executable):
        raise SidecarError("Child Python executable must be an absolute regular file")
    if not executable.name.lower().startswith("python"):
        raise SidecarError(f"Child executable is not a Python interpreter: {executable}")
    runner_indexes = [index for index, token in enumerate(command) if Path(token).name == "run_recipe.py"]
    if len(runner_indexes) != 1:
        raise SidecarError("Child command must invoke exactly one run_recipe.py")
    runner_index = runner_indexes[0]
    interpreter_flags = list(command[1:runner_index])
    if interpreter_flags != ["-u"]:
        raise SidecarError(
            f"Python -u must immediately precede run_recipe.py for streamed stdout: {interpreter_flags}"
        )
    runner = _resolve_command_path(command[runner_index], repo_root)
    expected_runner = _lexical_absolute(repo_root / "run_recipe.py")
    if runner != expected_runner or not runner.is_file() or _is_reparse_point(runner):
        raise SidecarError(f"Child runner must be the lab's existing {expected_runner}")
    if runner_index + 1 >= len(command):
        raise SidecarError("run_recipe.py command is missing its recipe argument")
    if "--suite" in command:
        raise SidecarError("Phase-1 sidecar accepts one standalone recipe, not --suite")
    recipe = _resolve_command_path(command[runner_index + 1], repo_root)
    recipes_root = _lexical_absolute(repo_root / "recipes")
    require_within(recipe, recipes_root, "recipe")
    require_safe_chain(recipe, repo_root, "recipe")
    if recipe.suffix.lower() != ".json" or not recipe.is_file():
        raise SidecarError(f"Recipe is not an existing JSON file: {recipe}")
    try:
        recipe_payload = json.loads(recipe.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SidecarError(f"Cannot decode recipe {recipe}: {exc}") from exc
    if recipe_payload.get("name") != recipe.stem:
        raise SidecarError(
            f"Recipe name {recipe_payload.get('name')!r} does not match stem {recipe.stem!r}"
        )
    return {
        "argv": list(command),
        "executable": str(executable),
        "executable_sha256": sha256_file(executable),
        "runner": str(runner),
        "runner_sha256": sha256_file(runner),
        "recipe": str(recipe),
        "recipe_name": recipe.stem,
        "recipe_sha256": sha256_file(recipe),
    }


def _archive_paths(results_root: Path, recipe_name: str) -> dict[str, Path]:
    prefix = f"{recipe_name}_run"
    archives: dict[str, Path] = {}
    for path in results_root.glob(f"{recipe_name}_run*.json"):
        suffix = path.stem[len(prefix) :]
        if suffix.isdigit() and int(suffix) > 0:
            archives[path.name] = path
    return archives


def snapshot_archives(results_root: Path, recipe_name: str) -> dict[str, dict[str, Any]]:
    require_safe_chain(results_root, results_root.parent, "results directory")
    if not results_root.is_dir():
        raise SidecarError(f"Results directory does not exist: {results_root}")
    return {
        name: stable_file_snapshot(path)
        for name, path in sorted(_archive_paths(results_root, recipe_name).items())
    }


def bind_new_run(
    *,
    repo_root: Path,
    recipe_name: str,
    before_archives: dict[str, dict[str, Any]],
    child_started_ns: int,
) -> dict[str, Any]:
    results_root = _lexical_absolute(repo_root / "results")
    outputs_root = _lexical_absolute(repo_root / "outputs")
    after_paths = _archive_paths(results_root, recipe_name)
    new_names = sorted(set(after_paths) - set(before_archives))
    if len(new_names) != 1:
        raise SidecarError(
            f"Expected exactly one new immutable run archive for {recipe_name}, found {new_names}"
        )
    for name, before in before_archives.items():
        after = stable_file_snapshot(results_root / name)
        if before != after:
            raise SidecarError(f"Pre-existing run archive changed: {name}")
    archive_path = after_paths[new_names[0]]
    require_safe_chain(archive_path, results_root, "new run archive")
    archive = stable_file_snapshot(archive_path)
    if int(archive["mtime_ns"]) < int(child_started_ns):
        raise SidecarError("New run archive predates the child start")
    raw = archive_path.read_bytes()
    if sha256_bytes(raw) != archive["sha256"] or len(raw) != archive["bytes"]:
        raise SidecarError("New run archive changed after its stable snapshot")
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SidecarError(f"New run archive is not UTF-8 JSON: {archive_path}") from exc
    run_suffix = archive_path.stem.rsplit("_run", 1)[-1]
    if receipt.get("recipe") != recipe_name or receipt.get("run_number") != int(run_suffix):
        raise SidecarError("New archive recipe/run_number does not match its immutable filename")

    alias_path = results_root / f"{recipe_name}.json"
    require_safe_chain(alias_path, results_root, "current receipt alias")
    alias = stable_file_snapshot(alias_path)
    alias_raw = alias_path.read_bytes() if alias.get("exists") else b""
    if (
        not alias.get("exists")
        or sha256_bytes(alias_raw) != alias["sha256"]
        or len(alias_raw) != alias["bytes"]
        or alias_raw != raw
    ):
        raise SidecarError("Current receipt alias does not byte-match the new immutable archive")
    try:
        if os.path.samefile(alias_path, archive_path):
            raise SidecarError("Current alias and immutable archive are the same filesystem object")
    except OSError as exc:
        raise SidecarError(f"Cannot distinguish alias from immutable archive: {exc}") from exc

    output_value = receipt.get("output_path")
    expected_hash = receipt.get("artifact_sha256")
    expected_bytes = receipt.get("artifact_bytes")
    if not isinstance(output_value, str) or not output_value.strip():
        raise SidecarError("New receipt has no non-empty output_path")
    relative = Path(output_value)
    if relative.is_absolute():
        raise SidecarError(f"Receipt output_path must be relative to outputs: {relative}")
    artifact_path = require_within(outputs_root / relative, outputs_root, "receipt artifact")
    require_safe_chain(artifact_path, outputs_root, "receipt artifact")
    artifact = stable_file_snapshot(artifact_path)
    if not artifact.get("exists") or int(artifact.get("bytes") or 0) <= 0:
        raise SidecarError(f"Receipt artifact is absent or empty: {artifact_path}")
    if int(artifact["mtime_ns"]) < int(child_started_ns):
        raise SidecarError("Receipt artifact predates the child start")
    if expected_hash != artifact["sha256"]:
        raise SidecarError(
            f"Receipt/artifact SHA-256 mismatch: receipt={expected_hash} actual={artifact['sha256']}"
        )
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int):
        raise SidecarError("Receipt artifact_bytes is not an integer")
    if expected_bytes != artifact["bytes"]:
        raise SidecarError(
            f"Receipt/artifact byte mismatch: receipt={expected_bytes} actual={artifact['bytes']}"
        )
    return {
        "new_archive": archive,
        "current_alias": alias,
        "alias_byte_matches_archive": True,
        "artifact": artifact,
        "archive_receipt": {
            "receipt_schema_version": receipt.get("receipt_schema_version"),
            "recipe": receipt.get("recipe"),
            "run_number": receipt.get("run_number"),
            "run_identity_sha256": receipt.get("run_identity_sha256"),
            "status": receipt.get("status"),
            "gate_pass": receipt.get("gate_pass"),
            "warm_pass": receipt.get("warm_pass"),
            "pass": receipt.get("pass"),
            "output_path": output_value,
            "artifact_sha256": expected_hash,
            "artifact_bytes": expected_bytes,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="absolute append-only telemetry JSON path")
    parser.add_argument("--label", required=True)
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--interval-s", type=float, default=DEFAULT_INTERVAL_S)
    parser.add_argument("--max-sample-gap-s", type=float, default=DEFAULT_MAX_GAP_S)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def _validate_output_path(value: str, repo_root: Path) -> Path:
    output = Path(value)
    if not output.is_absolute() or output.suffix.lower() != ".json":
        raise SidecarError("Telemetry output must be an absolute .json path")
    telemetry_root = _lexical_absolute(repo_root / "results" / "humo_diet" / "telemetry")
    output = require_within(output, telemetry_root, "telemetry output")
    require_safe_chain(output.parent, repo_root, "telemetry output parent")
    if output.exists():
        raise FileExistsError(f"Telemetry evidence already exists: {output}")
    return output


def run(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    sample_query: Callable[[int], dict[str, Any]] = query_machine_sample,
) -> tuple[int, dict[str, Any]]:
    args = parse_args(argv)
    root = _lexical_absolute(repo_root or REPO_ROOT)
    if not root.is_dir() or _is_reparse_point(root):
        raise SidecarError(f"Unsafe or missing lab root: {root}")
    output = _validate_output_path(args.output, root)
    if args.interval_s <= 0:
        raise SidecarError("Sampling interval must be positive")
    if args.max_sample_gap_s < args.interval_s:
        raise SidecarError("Maximum sample gap must be at least the sampling interval")
    command_contract = validate_command(args.command, root)
    recipe_name = command_contract["recipe_name"]
    results_root = _lexical_absolute(root / "results")
    outputs_root = _lexical_absolute(root / "outputs")
    server_log = _lexical_absolute(root / "server.log")
    require_safe_chain(server_log, root, "server.log")
    require_safe_chain(outputs_root, root, "outputs directory")
    if not outputs_root.is_dir():
        raise SidecarError(f"Outputs directory does not exist: {outputs_root}")

    before_archives = snapshot_archives(results_root, recipe_name)
    baseline = sample_query(args.gpu_index)
    # Snapshot immediately before launch so the tailed suffix begins as close
    # as possible to the child's actual lifetime (the baseline query can take
    # materially longer than one 200 ms sampling interval on Windows).
    log_starting = stable_file_snapshot(server_log)

    started_ns = time.time_ns()
    started_mono_ns = time.monotonic_ns()
    child_finished_ns: int | None = None
    child_finished_mono_ns: int | None = None
    process: Any | None = None
    sampler: ObservationSampler | None = None
    stdout_thread: threading.Thread | None = None
    stdout_events: list[dict[str, Any]] = []
    stdout_errors: list[str] = []
    errors: list[str] = []
    returncode: int | None = None
    binding: dict[str, Any] | None = None
    log_tail = AppendOnlyLogTail(server_log, log_starting)
    try:
        process = popen_factory(
            list(args.command),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        if process.stdout is None:
            raise SidecarError("Child stdout pipe was not created")
        stdout_thread = threading.Thread(
            target=_stream_child_stdout,
            args=(process.stdout, stdout_events, stdout_errors),
            daemon=True,
        )
        stdout_thread.start()
        sampler = ObservationSampler(
            args.gpu_index,
            args.interval_s,
            log_tail,
            sample_query=sample_query,
        )
        sampler.start()
        returncode = int(process.wait())
        child_finished_mono_ns = time.monotonic_ns()
        child_finished_ns = time.time_ns()
    except BaseException as exc:  # preserve evidence and stop only our child
        errors.append(f"{type(exc).__name__}: {exc}")
        if process is not None and getattr(process, "poll", lambda: 0)() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception as terminate_exc:  # noqa: BLE001
                errors.append(f"child termination failed: {terminate_exc}")
        child_finished_mono_ns = time.monotonic_ns()
        child_finished_ns = time.time_ns()
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
        if stdout_thread is not None:
            stdout_thread.join(timeout=10)
            if stdout_thread.is_alive():
                errors.append("child stdout reader did not stop")
    telemetry_finished_mono_ns = time.monotonic_ns()
    telemetry_finished_ns = time.time_ns()
    if child_finished_mono_ns is None or child_finished_ns is None:
        child_finished_mono_ns = telemetry_finished_mono_ns
        child_finished_ns = telemetry_finished_ns

    samples = sampler.samples if sampler is not None else []
    sample_errors = sampler.errors if sampler is not None else ["sampler was not started"]
    try:
        sample_summary = summarize_samples(
            samples,
            baseline=baseline,
            child_start_mono_ns=started_mono_ns,
            child_end_mono_ns=child_finished_mono_ns,
            interval_s=args.interval_s,
            max_gap_s=args.max_sample_gap_s,
            sample_errors=sample_errors,
        )
        errors.extend(sample_summary["coverage_errors"])
    except Exception as exc:  # noqa: BLE001
        sample_summary = {"samples": samples, "coverage_errors": [str(exc)]}
        errors.append(f"{type(exc).__name__}: {exc}")
    log_summary = log_tail.finish()
    errors.extend(log_summary["errors"])
    errors.extend(stdout_errors)
    if returncode != 0:
        errors.append(f"child returned nonzero exit code {returncode}")
    if returncode == 0:
        try:
            binding = bind_new_run(
                repo_root=root,
                recipe_name=recipe_name,
                before_archives=before_archives,
                child_started_ns=started_ns,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    receipt: dict[str, Any] = {
        "sidecar_schema_version": 1,
        "kind": "humo-diet-phase1-telemetry",
        "label": args.label,
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "phase_inference": {
            "performed": False,
            "reason": "Phase-1 retains raw observations; phases are derived only after real events exist.",
        },
        "started_at_ns": started_ns,
        "started_at_utc": utc_timestamp(started_ns),
        "child_finished_at_ns": child_finished_ns,
        "child_finished_at_utc": utc_timestamp(child_finished_ns),
        "telemetry_finished_at_ns": telemetry_finished_ns,
        "telemetry_finished_at_utc": utc_timestamp(telemetry_finished_ns),
        "started_monotonic_ns": started_mono_ns,
        "child_finished_monotonic_ns": child_finished_mono_ns,
        "telemetry_finished_monotonic_ns": telemetry_finished_mono_ns,
        "child_duration_s": round(
            (child_finished_mono_ns - started_mono_ns) / 1_000_000_000.0, 9
        ),
        "child_returncode": returncode,
        "command": command_contract,
        "baseline": baseline,
        "sampler": sample_summary,
        "child_stdout": {
            "timestamps_are_observation_times": True,
            "event_count": len(stdout_events),
            "errors": stdout_errors,
            "events": stdout_events,
        },
        "server_log": log_summary,
        "pre_run_archives": before_archives,
        "run_binding": binding,
    }
    atomic_create_json(output, receipt)
    return (0 if receipt["status"] == "ok" else 1), receipt


def main(argv: Sequence[str] | None = None) -> int:
    try:
        code, receipt = run(argv)
    except Exception as exc:
        print(f"[humo-diet-sidecar] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "[humo-diet-sidecar] %s label=%s duration_s=%s peak_vram_gib=%s peak_host_ram_gib=%s"
        % (
            receipt["status"].upper(),
            receipt["label"],
            receipt["child_duration_s"],
            receipt.get("sampler", {}).get("peak_vram_gib"),
            receipt.get("sampler", {}).get("peak_host_ram_gib"),
        ),
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
