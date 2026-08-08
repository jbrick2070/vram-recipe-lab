#!/usr/bin/env python3
"""
run_recipe.py — Recipe execution runner and preflight enforcement harness
for ComfyUI workflow VRAM recipe benchmarking.

Talks to lab server at http://127.0.0.1:8199.
Self-boots lab server via boot_lab_server.cmd if down, tracking PID in .server.pid.
Windows 11 / RTX 5080 Laptop (16 GB, 14.5 GB gate ceiling).
"""

import os
import sys
import time
import json
import hashlib
import math
import statistics
import psutil
import shutil
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# --- Constants & Paths ---
REPO_ROOT = Path(__file__).parent.resolve()
LOCKFILE_PATH = REPO_ROOT / ".gpu.lock"
SERVER_PID_FILE = REPO_ROOT / ".server.pid"
SERVER_LOG_FILE = REPO_ROOT / "server.log"
BOOT_CMD = REPO_ROOT / "boot_lab_server.cmd"
RESULTS_DIR = REPO_ROOT / "results"
FIXTURES_DIR = REPO_ROOT / "fixtures"
MODELS_MANIFEST = REPO_ROOT / "models_manifest.md"
RESULTS_LEDGER = REPO_ROOT / "RESULTS.md"
ENGINE_MATRIX_BETA = REPO_ROOT / "ENGINE_MATRIX_BETA.md"
COMFYUI_ROOT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI")
MODEL_ROOTS = [
    Path(r"C:\ComfyUI-Models\checkpoints"),
    Path(r"C:\ComfyUI-Models\diffusion_models"),
    Path(r"C:\ComfyUI-Models\unet"),
    Path(r"C:\ComfyUI-Models\text_encoders"),
    Path(r"C:\ComfyUI-Models\clip"),
    Path(r"C:\ComfyUI-Models\vae"),
    Path(r"C:\ComfyUI-Models\loras"),
    Path(r"C:\ComfyUI-Models\upscale_models"),
    Path(r"C:\ComfyUI-Models\latent_upscale_models"),
    Path(r"C:\ComfyUI-Models\audio_encoders"),
    Path(r"C:\ComfyUI-Models\model_patches"),
]

LAB_PORT = os.environ.get("LAB_PORT", "8199")
COMFY_SERVER_URL = f"http://127.0.0.1:{LAB_PORT}"
VRAM_GATE_GB = 14.5
RECEIPT_SCHEMA_VERSION = 2
# Desktop composition fluctuates around 2.5 GB on this workstation. This is
# only a pre-boot contention check; the independent 14.5 GB peak gate remains
# authoritative for render safety and certification.
VRAM_GPU_IDLE_MAX_MB = 3072  # 3.0 GB pre-boot desktop threshold
MIN_FREE_DISK_GB = 5.0
BOOT_TIMEOUT_S = 120
POLL_INTERVAL_S = 0.2  # 200ms VRAM polling interval


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    """Return a SHA-256 digest for bytes already captured for use."""
    return hashlib.sha256(content).hexdigest()


def git_commit(path: Path) -> str:
    """Return the checked-out Git commit, or an empty string outside Git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def git_dirty(path: Path) -> Optional[bool]:
    """Report whether a Git worktree has tracked or untracked changes."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def stable_identity(payload: Dict[str, Any]) -> str:
    """Hash a deterministic run-configuration payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extract_output_path(outputs: Dict[str, Any]) -> str:
    """Return the first file artifact emitted by a ComfyUI history payload."""
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ["images", "gifs", "videos", "audio", "animated"]:
            items = node_output.get(key)
            if not isinstance(items, list) or not items:
                continue
            item = items[0]
            if isinstance(item, dict):
                filename = item.get("filename", "")
            elif isinstance(item, str):
                filename = item
            else:
                filename = ""
            if filename:
                return filename
    return ""


def next_run_state(previous: Dict[str, Any], run_identity_sha256: str) -> Dict[str, Any]:
    """Keep execution numbering monotonic while resetting certification on identity changes."""
    previous_run_count = int(previous.get("run_count", previous.get("run_number", 0)) or 0)
    same_identity = bool(run_identity_sha256) and previous.get("run_identity_sha256") == run_identity_sha256
    previous_config_count = int(previous.get("config_run_count", 0) or 0) if same_identity else 0
    previous_gate_pass = bool(previous.get("gate_pass", False)) if same_identity else False
    return {
        "run_count": previous_run_count + 1,
        "config_run_count": previous_config_count + 1,
        "same_identity": same_identity,
        "previous_gate_pass": previous_gate_pass,
    }


def referenced_fixtures(recipe_data: Dict[str, Any]) -> List[str]:
    """Return literal local fixture names referenced by LoadImage/LoadAudio nodes."""
    prompt = recipe_data.get("prompt", recipe_data)
    found = set()
    fixture_inputs = {"LoadImage": "image", "LoadAudio": "audio"}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        input_name = fixture_inputs.get(node.get("class_type"))
        if not input_name:
            continue
        value = node.get("inputs", {}).get(input_name)
        if isinstance(value, str) and value:
            normalized = value.replace("\\", "/")
            candidate = Path(normalized)
            if candidate.is_absolute() or len(candidate.parts) != 1 or normalized in {".", ".."}:
                raise ValueError(f"Fixture reference must be a basename inside fixtures/: {value}")
            found.add(normalized)
    return sorted(found)


def fixture_sha256s(recipe_data: Dict[str, Any]) -> Dict[str, str]:
    """Hash every literal fixture so run identity changes with its inputs."""
    hashes: Dict[str, str] = {}
    for fixture_name in referenced_fixtures(recipe_data):
        fixture_path = FIXTURES_DIR / fixture_name
        if fixture_path.is_file():
            hashes[fixture_name] = sha256_file(fixture_path)
    return hashes


def referenced_model_names(recipe_data: Dict[str, Any]) -> List[str]:
    """Collect literal weight filenames from known ComfyUI loader inputs."""
    model_input_names = {
        "ckpt_name",
        "unet_name",
        "vae_name",
        "clip_name",
        "text_encoder",
        "lora_name",
        "model_name",
    }
    prompt = recipe_data.get("prompt", recipe_data)
    names = set()
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        for key, value in node.get("inputs", {}).items():
            if key in model_input_names and isinstance(value, str) and value:
                names.add(value.replace("\\", "/"))
    return sorted(names)


def model_fingerprints(recipe_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Fingerprint referenced local weights without hashing multi-gigabyte files."""
    fingerprints: Dict[str, Dict[str, Any]] = {}
    for model_name in referenced_model_names(recipe_data):
        relative = Path(model_name)
        resolved = next(
            (root / relative for root in MODEL_ROOTS if (root / relative).is_file()),
            None,
        )
        if resolved is None:
            fingerprints[model_name] = {"resolved": False}
            continue
        stat = resolved.stat()
        fingerprints[model_name] = {
            "resolved": True,
            "path": str(resolved),
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return fingerprints


def probe_media_metrics(path: Path) -> Dict[str, Any]:
    """Collect non-gating encoded-stream diagnostics from an output artifact."""
    metrics: Dict[str, Any] = {"artifact_bytes": path.stat().st_size}
    try:
        stream_proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-count_frames", "-show_streams",
                "-show_format", "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        packet_proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_packets",
                "-show_entries", "packet=stream_index,size", "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(stream_proc.stdout)
        packets = json.loads(packet_proc.stdout).get("packets", [])
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if not video:
            metrics["media_probe_error"] = "no video stream"
            return metrics

        video_index = int(video.get("index", 0))
        audio_index = int(audio.get("index", -1)) if audio else -1
        video_bytes = sum(int(p.get("size", 0) or 0) for p in packets if int(p.get("stream_index", -1)) == video_index)
        audio_bytes = sum(int(p.get("size", 0) or 0) for p in packets if int(p.get("stream_index", -1)) == audio_index)
        frame_value = video.get("nb_read_frames") or video.get("nb_frames") or 0
        frame_count = int(frame_value) if str(frame_value).isdigit() else 0

        fps_text = video.get("avg_frame_rate", "0/0")
        numerator, denominator = (fps_text.split("/", 1) + ["1"])[:2]
        fps = float(numerator) / float(denominator) if float(denominator) else 0.0
        metrics.update({
            "encoded_frame_count": frame_count,
            "artifact_bytes_per_frame": round(metrics["artifact_bytes"] / frame_count, 2) if frame_count else None,
            "video_stream_bytes": video_bytes,
            "video_stream_bytes_per_frame": round(video_bytes / frame_count, 2) if frame_count else None,
            "audio_stream_bytes": audio_bytes,
            "video_codec": video.get("codec_name", ""),
            "pixel_format": video.get("pix_fmt", ""),
            "encoded_width": video.get("width"),
            "encoded_height": video.get("height"),
            "encoded_fps": round(fps, 6),
            "audio_present": audio is not None,
            "audio_codec": audio.get("codec_name", "") if audio else "",
            "audio_bitrate": int(audio.get("bit_rate", 0) or 0) if audio else 0,
        })
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        metrics["media_probe_error"] = str(exc)
    return metrics


def media_fingerprint(metrics: Dict[str, Any]) -> Tuple[Any, ...]:
    """Fields that must match before encoded-size comparisons are meaningful."""
    return (
        metrics.get("video_codec"),
        metrics.get("pixel_format"),
        metrics.get("encoded_width"),
        metrics.get("encoded_height"),
        metrics.get("encoded_fps"),
        metrics.get("encoded_frame_count"),
    )


def bitrate_anomaly_fields(recipe_name: str, metrics: Dict[str, Any], boot_lane: str) -> Dict[str, Any]:
    """Compare against >=3 distinct, explicitly human-approved clean artifacts."""
    current_bpf = metrics.get("video_stream_bytes_per_frame")
    if not current_bpf:
        return {"bitrate_anomaly": False, "bitrate_baseline_status": "unavailable"}

    fingerprint = media_fingerprint(metrics)
    approved_values = []
    artifact_hashes = set()
    for receipt_path in RESULTS_DIR.glob(f"{recipe_name}_run*.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("eyeball") != "ok" or receipt.get("eyeball_source") != "human":
                continue
            if not receipt.get("eyeball_reviewed_at"):
                continue
            if receipt.get("boot_lane") != boot_lane:
                continue
            if media_fingerprint(receipt) != fingerprint:
                continue
            value = receipt.get("video_stream_bytes_per_frame")
            output_name = receipt.get("output_path")
            output_file = REPO_ROOT / "outputs" / output_name if output_name else None
            if not value or output_file is None or not output_file.is_file():
                continue
            artifact_hash = sha256_file(output_file)
            if receipt.get("artifact_sha256") != artifact_hash:
                continue
            if artifact_hash in artifact_hashes:
                continue
            artifact_hashes.add(artifact_hash)
            approved_values.append(float(value))
        except (OSError, ValueError, json.JSONDecodeError):
            continue

    if len(approved_values) < 3:
        return {
            "bitrate_anomaly": False,
            "bitrate_baseline_status": f"provisional:{len(approved_values)}-of-3-clean-artifacts",
            "clean_baseline_sample_count": len(approved_values),
        }

    clean_median = statistics.median(approved_values)
    ratio = float(current_bpf) / clean_median if clean_median else 0.0
    return {
        "bitrate_anomaly": ratio > 2.0,
        "bitrate_baseline_status": "clean-same-lane-median",
        "clean_baseline_sample_count": len(approved_values),
        "clean_median_video_stream_bytes_per_frame": round(clean_median, 2),
        "bitrate_ratio_to_clean_median": round(ratio, 3),
    }


def media_artifact_is_valid(
    metrics: Dict[str, Any],
    contract: Optional[Dict[str, Any]] = None,
    requires_audio: bool = False,
) -> bool:
    """Require a decodable, complete artifact matching its recipe contract."""
    if (
        metrics.get("media_probe_error")
        or int(metrics.get("encoded_frame_count") or 0) <= 0
        or int(metrics.get("video_stream_bytes") or 0) <= 0
    ):
        return False

    contract = contract or {}
    expected_frames = int(contract.get("frames") or 0)
    expected_width = int(contract.get("width") or 0)
    expected_height = int(contract.get("height") or 0)
    expected_fps = float(contract.get("fps") or 0.0)
    if expected_frames and int(metrics.get("encoded_frame_count") or 0) != expected_frames:
        return False
    if expected_width and int(metrics.get("encoded_width") or 0) != expected_width:
        return False
    if expected_height and int(metrics.get("encoded_height") or 0) != expected_height:
        return False
    if expected_fps and abs(float(metrics.get("encoded_fps") or 0.0) - expected_fps) > 0.01:
        return False
    if requires_audio and (
        not metrics.get("audio_present")
        or int(metrics.get("audio_stream_bytes") or 0) <= 0
    ):
        return False
    return True


class PreflightError(Exception):
    """Raised when a preflight check fails."""
    def __init__(self, check_num: int, name: str, reason: str):
        self.check_num = check_num
        self.name = name
        self.reason = reason
        super().__init__(f"Preflight Check #{check_num} [{name}] FAILED: {reason}")


class LockManager:
    """Atomic GPU Lockfile Manager with stale lock recovery."""

    def __init__(self, lock_path: Path = LOCKFILE_PATH):
        self.lock_path = lock_path
        self.acquired = False

    def acquire(self):
        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text(encoding="utf-8-sig", errors="ignore")
                lock_info = json.loads(content)
                pid = lock_info.get("pid")
                if pid and not psutil.pid_exists(pid):
                    print(f"[LOCK] Removing stale lockfile from dead PID {pid}")
                    self.lock_path.unlink(missing_ok=True)
                else:
                    raise PreflightError(1, "Lock", f".gpu.lock exists (held by PID {pid})")
            except (json.JSONDecodeError, OSError):
                raise PreflightError(1, "Lock", ".gpu.lock exists and cannot be read")

        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            lock_data = json.dumps({"pid": os.getpid(), "time": time.time()}).encode("utf-8")
            os.write(fd, lock_data)
            os.close(fd)
            self.acquired = True
            print(f"[LOCK] Acquired .gpu.lock (PID {os.getpid()})")
        except OSError as e:
            raise PreflightError(1, "Lock", f"Failed atomic lock acquisition: {e}")

    def release(self):
        if self.acquired and self.lock_path.exists():
            try:
                self.lock_path.unlink()
                print("[LOCK] Released .gpu.lock")
            except OSError as e:
                print(f"[LOCK] Warning: failed to remove lockfile: {e}")
            self.acquired = False

    def __enter__(self):
        if not self.acquired:
            self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def query_gpu_vram_mb() -> float:
    """Query current GPU VRAM usage in MB via nvidia-smi."""
    res = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True
    )
    return float(res.stdout.strip().splitlines()[0])


def query_gpu_total_gib() -> float:
    """Query physical GPU memory in GiB using nvidia-smi's MiB value."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip().splitlines()[0]) / 1024.0


def reserve_for_target_gib(physical_total_gib: float, target_gib: float) -> float:
    """Translate a target-card budget into ComfyUI --reserve-vram semantics."""
    if not math.isfinite(target_gib) or target_gib <= 0:
        raise ValueError("Clamp target must be positive")
    if target_gib > physical_total_gib:
        raise ValueError(
            f"Clamp target {target_gib:.3f} GiB exceeds physical VRAM {physical_total_gib:.3f} GiB"
        )
    return max(0.0, physical_total_gib - target_gib)


def validate_reserve_gib(value: float, physical_total_gib: float) -> float:
    """Validate direct ComfyUI reserve-vram input."""
    if not math.isfinite(value) or value < 0:
        raise ValueError("Direct reserve-vram must be a finite, nonnegative GiB value")
    if value >= physical_total_gib:
        raise ValueError(
            f"Direct reserve-vram {value:g} GiB must be below physical VRAM {physical_total_gib:.3f} GiB"
        )
    return value


def query_host_ram_gb() -> float:
    """Query current host system RAM usage in GB via psutil."""
    return psutil.virtual_memory().used / (1024.0 ** 3)


class ResourceMonitorThread(threading.Thread):
    """Background thread polling GPU VRAM and Host System RAM at 200ms interval."""

    def __init__(self, interval: float = 0.2):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak_vram_gb = 0.0
        self.peak_host_ram_gb = 0.0
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                vram_mb = query_gpu_vram_mb()
                vram_gb = vram_mb / 1024.0
                if vram_gb > self.peak_vram_gb:
                    self.peak_vram_gb = vram_gb

                host_gb = query_host_ram_gb()
                if host_gb > self.peak_host_ram_gb:
                    self.peak_host_ram_gb = host_gb
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self) -> Tuple[float, float]:
        self._stop_event.set()
        self.join(timeout=2.0)
        return self.peak_vram_gb, self.peak_host_ram_gb


def get_recorded_pid() -> Optional[int]:
    """Retrieve recorded lab server PID from .server.pid."""
    if SERVER_PID_FILE.exists():
        try:
            content = SERVER_PID_FILE.read_text(encoding="utf-8-sig", errors="ignore").strip()
            if content:
                pid = int(content)
                if psutil.pid_exists(pid):
                    return pid
        except (ValueError, OSError):
            pass
    return None


def cleanup_stale_pid_receipt():
    """Remove .server.pid if it exists but the process is no longer running."""
    if SERVER_PID_FILE.exists():
        pid = get_recorded_pid()
        if not pid:
            print("[SERVER] Cleaning up stale .server.pid receipt")
            SERVER_PID_FILE.unlink(missing_ok=True)


def check_gpu_idle() -> float:
    """Preflight Check #2: Refuse unexpectedly high unrelated desktop GPU load."""
    try:
        used_mb = query_gpu_vram_mb()
        max_limit_mb = float(VRAM_GPU_IDLE_MAX_MB)

        if used_mb >= max_limit_mb:
            raise PreflightError(2, "GPU idle", f"GPU allocated VRAM is {used_mb:.1f} MB (exceeds pre-boot desktop threshold {max_limit_mb:.0f} MB)")
        return used_mb / 1024.0
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        if isinstance(e, PreflightError):
            raise
        raise PreflightError(2, "GPU idle", f"Could not query nvidia-smi: {e}")


def query_server_stats() -> Optional[Dict[str, Any]]:
    """Query GET /system_stats at 127.0.0.1:8199."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        pass
    return None


def listener_pid(port: int) -> Optional[int]:
    """Return the PID listening on the local lab port when psutil can resolve it."""
    try:
        for connection in psutil.net_connections(kind="inet"):
            local = connection.laddr
            local_port = getattr(local, "port", local[1] if len(local) > 1 else None) if local else None
            if connection.status == psutil.CONN_LISTEN and local_port == port:
                return connection.pid
    except (psutil.AccessDenied, OSError):
        return None
    return None


def is_expected_lab_server_pid(pid: int) -> bool:
    """Verify that a PID is the configured ComfyUI lab process, not just live."""
    try:
        argv = psutil.Process(pid).cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    normalized = [str(arg).replace("\\", "/").lower() for arg in argv]
    expected_main = str(COMFYUI_ROOT / "main.py").replace("\\", "/").lower()
    expected_output = str(REPO_ROOT / "outputs").replace("\\", "/").lower()
    try:
        port_index = normalized.index("--port")
        output_index = normalized.index("--output-directory")
        return (
            expected_main in normalized
            and normalized[port_index + 1] == str(LAB_PORT)
            and normalized[output_index + 1] == expected_output
        )
    except (ValueError, IndexError):
        return False


def terminate_owned_process_tree(pid: int) -> bool:
    """Terminate a recorded process tree and report whether every captured PID exited."""
    if not pid or not psutil.pid_exists(pid):
        return True
    processes = []
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        processes = children + [parent]
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
        _, alive = psutil.wait_procs(processes, timeout=10)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=5)
        return not alive
    except (psutil.NoSuchProcess, psutil.TimeoutExpired, OSError):
        return not psutil.pid_exists(pid)


def boot_lab_server() -> Dict[str, Any]:
    """Boot lab server headlessly via boot_lab_server.cmd and wait for health-check."""
    if not BOOT_CMD.exists():
        raise PreflightError(3, "Server up", f"boot_lab_server.cmd missing at {BOOT_CMD}")

    cleanup_stale_pid_receipt()
    print(f"[SERVER] Launching lab server via {BOOT_CMD.name} on port {LAB_PORT}...")
    
    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(
        ["cmd.exe", "/c", str(BOOT_CMD)],
        cwd=str(REPO_ROOT),
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    
    SERVER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"[SERVER] Recorded server PID {proc.pid} in .server.pid")

    try:
        start = time.time()
        while time.time() - start < BOOT_TIMEOUT_S:
            stats = query_server_stats()
            if stats:
                launched_pids = {proc.pid}
                try:
                    launched_pids.update(child.pid for child in psutil.Process(proc.pid).children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
                serving_pid = listener_pid(int(LAB_PORT))
                if serving_pid is None:
                    raise PreflightError(3, "Server up", f"Could not prove ownership of the listener on port {LAB_PORT}")
                if serving_pid not in launched_pids or not is_expected_lab_server_pid(serving_pid):
                    raise PreflightError(
                        3,
                        "Server up",
                        f"Port {LAB_PORT} was claimed by PID {serving_pid}, outside the process tree this runner launched",
                    )
                SERVER_PID_FILE.write_text(str(serving_pid), encoding="utf-8")
                print(f"[SERVER] Updated .server.pid to serving PID {serving_pid}")
                print(f"[SERVER] Lab server online on port {LAB_PORT} after {time.time()-start:.1f}s")
                return stats
            time.sleep(3.0)

        log_tail = ""
        if SERVER_LOG_FILE.exists():
            try:
                log_lines = SERVER_LOG_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                log_tail = "\n".join(log_lines[-15:])
            except Exception as e:
                log_tail = f"(Could not read server.log: {e})"

        raise PreflightError(3, "Server up", f"Lab server failed to boot on port {LAB_PORT} within 120s.\nTail of server.log:\n{log_tail}")
    except Exception:
        terminated = terminate_owned_process_tree(proc.pid)
        if terminated and SERVER_PID_FILE.exists():
            SERVER_PID_FILE.unlink(missing_ok=True)
        elif not terminated:
            print(
                f"[SERVER] Boot cleanup could not prove PID {proc.pid} exited; "
                "keeping .server.pid for manual inspection."
            )
        raise


def check_server_up_and_ownership() -> Dict[str, Any]:
    """Verify ownership first; check desktop VRAM only before booting a new server."""
    cleanup_stale_pid_receipt()
    stats = query_server_stats()
    pid_receipt = get_recorded_pid()

    if stats:
        serving_pid = listener_pid(int(LAB_PORT))
        if (
            pid_receipt
            and serving_pid == pid_receipt
            and is_expected_lab_server_pid(pid_receipt)
        ):
            return stats
        else:
            raise PreflightError(
                3, "Server up",
                f"Unrecognized server already answering on port {LAB_PORT} without valid PID receipt. Refusing to adopt or kill it."
            )

    if pid_receipt:
        raise PreflightError(
            3,
            "Server up",
            f"Live PID receipt {pid_receipt} exists but no verified lab server answers on port {LAB_PORT}. Refusing to overwrite the receipt.",
        )

    check_gpu_idle()
    print("  [OK] Check 2: GPU below the pre-boot desktop threshold")
    return boot_lab_server()


def shutdown_lab_server():
    """Stop only the verified recorded lab process; retain its receipt on failure."""
    pid = get_recorded_pid()
    if not pid:
        if SERVER_PID_FILE.exists():
            SERVER_PID_FILE.unlink(missing_ok=True)
            print("[SERVER] Removed stale .server.pid receipt.")
        return

    if not is_expected_lab_server_pid(pid):
        print(
            f"[SERVER] Refusing to kill PID {pid}: command-line verification failed. "
            "Keeping .server.pid for manual inspection."
        )
        return

    serving_pid = listener_pid(int(LAB_PORT))
    if serving_pid not in (None, pid):
        print(
            f"[SERVER] Port {LAB_PORT} is owned by unrecognized PID {serving_pid}; "
            f"terminating only the separately verified recorded lab PID {pid}."
        )
    else:
        print(f"[SERVER] Shutting down recorded lab server (PID {pid})...")

    terminated = terminate_owned_process_tree(pid)
    if terminated and not psutil.pid_exists(pid) and listener_pid(int(LAB_PORT)) != pid:
        SERVER_PID_FILE.unlink(missing_ok=True)
        print(f"[SERVER] Process {pid} and captured children terminated; removed .server.pid receipt.")
    else:
        print(
            f"[SERVER] Shutdown could not prove PID {pid} exited. "
            "Keeping .server.pid to prevent unsafe adoption or overwrite."
        )


def fetch_object_info() -> Dict[str, Any]:
    """Fetch object info dictionary from GET /object_info."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/object_info")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise PreflightError(4, "Nodes exist", f"Failed to fetch /object_info from {COMFY_SERVER_URL}: {e}")


def check_nodes_exist(recipe_data: Dict[str, Any], object_info: Dict[str, Any]):
    """Preflight Check #4: Every class_type in recipe appears in GET /object_info."""
    prompt_dict = recipe_data.get("prompt", recipe_data)
    missing_nodes = set()
    for node_id, node in prompt_dict.items():
        if isinstance(node, dict) and "class_type" in node:
            class_type = node["class_type"]
            if class_type not in object_info:
                missing_nodes.add(class_type)

    if missing_nodes:
        raise PreflightError(4, "Nodes exist", f"Missing server node class types: {sorted(list(missing_nodes))}")


def check_models_exist(recipe_data: Dict[str, Any]):
    """Preflight Check #5: Every referenced model appears in models_manifest.md."""
    if not MODELS_MANIFEST.exists():
        raise PreflightError(5, "Models exist", "models_manifest.md missing from repo root")

    manifest_text = MODELS_MANIFEST.read_text(encoding="utf-8")
    
    referenced_models = set()
    def scan_values(obj):
        if isinstance(obj, str):
            if any(obj.endswith(ext) for ext in [".safetensors", ".ckpt", ".pth", ".bin", ".gguf", ".onnx"]):
                referenced_models.add(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                scan_values(v)
        elif isinstance(obj, list):
            for item in obj:
                scan_values(item)

    scan_values(recipe_data)

    missing = [m for m in referenced_models if m not in manifest_text]
    if missing:
        raise PreflightError(5, "Models exist", f"Models missing from manifest: {missing}")


def check_widget_integrity(recipe_data: Dict[str, Any], object_info: Dict[str, Any]):
    """Preflight Check #6: Recipe JSON parses; widget count & input structure validated against server object_info schema."""
    prompt_dict = recipe_data.get("prompt", recipe_data)
    for node_id, node in prompt_dict.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        if not class_type:
            raise PreflightError(6, "Widget integrity", f"Node {node_id} missing class_type")
        if not isinstance(inputs, dict):
            raise PreflightError(6, "Widget integrity", f"Node {node_id} inputs is not a dictionary")
        if class_type in object_info:
            info = object_info[class_type]
            req_inputs = info.get("input", {}).get("required", {})
            opt_inputs = info.get("input", {}).get("optional", {})
            schema_keys = set(req_inputs.keys()) | set(opt_inputs.keys())
            for in_key in inputs:
                if in_key not in schema_keys:
                    print(f"[PREFLIGHT WARN] Node {node_id} ({class_type}) input '{in_key}' not found in server object_info schema.")


def check_affordability(
    recipe_name: str,
    recipe_sha256: str,
    boot_lane: str,
    is_force: bool = False,
):
    """Refuse an unchanged, known-over-gate recipe/lane unless explicitly forced."""
    if is_force:
        return
    result_file = RESULTS_DIR / f"{recipe_name}.json"
    if result_file.exists():
        try:
            prev = json.loads(result_file.read_text(encoding="utf-8"))
            last_peak = prev.get("peak_vram_gb", 0.0)
            same_recipe = prev.get("recipe_sha256") == recipe_sha256
            same_lane = prev.get("boot_lane") == boot_lane
            prior_status = str(prev.get("status", ""))
            known_vram_failure = (
                last_peak > VRAM_GATE_GB
                or "net VRAM" in prior_status
                or prior_status.startswith("FAIL (VRAM")
            )
            prior_gate_failed = prev.get("gate_pass") is False or (
                "gate_pass" not in prev and known_vram_failure
            )
            if same_recipe and same_lane and prior_gate_failed and known_vram_failure:
                raise PreflightError(
                    7, "Affordability estimate",
                    f"Last identical recipe/lane failed its VRAM gate ({prior_status}; peak {last_peak:.2f} GB). Refusing unchanged re-run."
                )
        except json.JSONDecodeError:
            pass


def upload_fixtures(fixture_payloads: Dict[str, bytes]):
    """Overwrite exact fixture basenames and prove the server stored those bytes."""
    if not FIXTURES_DIR.exists():
        return

    for fixture_name, content in fixture_payloads.items():
        fix_file = FIXTURES_DIR / fixture_name
        try:
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            body = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
                "true\r\n"
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="type"\r\n\r\n'
                "input\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; filename="{fix_file.name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

            req = urllib.request.Request(
                f"{COMFY_SERVER_URL}/upload/image",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                upload_result = json.loads(response.read().decode("utf-8"))
            if (
                upload_result.get("name") != fix_file.name
                or upload_result.get("subfolder", "") != ""
                or upload_result.get("type") != "input"
            ):
                raise ValueError(f"server stored fixture under unexpected identity: {upload_result}")

            view_query = urllib.parse.urlencode({
                "filename": fix_file.name,
                "type": "input",
                "fixture_sha256": sha256_bytes(content),
            })
            view_req = urllib.request.Request(
                f"{COMFY_SERVER_URL}/view?{view_query}",
                headers={"Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(view_req, timeout=10) as response:
                stored_content = response.read()
            if sha256_bytes(stored_content) != sha256_bytes(content):
                raise ValueError("server readback SHA-256 does not match queued fixture bytes")
            print(f"[FIXTURE] Uploaded and verified fixture {fix_file.name} in server input directory")
        except Exception as exc:
            raise PreflightError(8, "Fixtures uploaded", f"Failed to upload {fixture_name}: {exc}") from exc


def check_fixtures_uploaded(recipe_data: Dict[str, Any]) -> Dict[str, str]:
    """Capture, hash, and upload only the recipe's literal fixture bytes."""
    try:
        fixture_names = referenced_fixtures(recipe_data)
    except ValueError as exc:
        raise PreflightError(8, "Fixtures uploaded", str(exc)) from exc
    fixture_payloads: Dict[str, bytes] = {}
    for fixture in fixture_names:
        p = FIXTURES_DIR / fixture
        if not p.is_file():
            raise PreflightError(8, "Fixtures uploaded", f"Fixture file missing from fixtures/: {fixture}")
        fixture_payloads[fixture] = p.read_bytes()

    upload_fixtures(fixture_payloads)
    return {name: sha256_bytes(content) for name, content in fixture_payloads.items()}


def check_boot_lane(recipe_name: str, system_stats: Dict[str, Any]):
    """Preflight Check #9: Confirm boot lane is lab-8199, sage-free."""
    argv = system_stats.get("system", {}).get("argv", [])
    extra_flags = str(argv)
    if "--use-sage-attention" in extra_flags:
        raise PreflightError(
            9, "Boot lane",
            "Server was started with --use-sage-attention; lab boot lane must be sage-free."
        )

    expected_reserve = os.environ.get("LAB_RESERVE_VRAM_GB")
    if expected_reserve:
        try:
            reserve_index = argv.index("--reserve-vram")
            actual_reserve = float(argv[reserve_index + 1])
            if abs(actual_reserve - float(expected_reserve)) > 0.01:
                raise ValueError
        except (ValueError, IndexError):
            raise PreflightError(
                9,
                "Boot lane",
                f"Live server argv does not contain expected --reserve-vram {expected_reserve}",
            )
    elif "--reserve-vram" in argv:
        raise PreflightError(9, "Boot lane", "Live server has an unexpected --reserve-vram setting")


def check_disk_space():
    """Preflight Check #10: At least 5 GB free on output drive."""
    total, used, free = shutil.disk_usage(REPO_ROOT)
    free_gb = free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        raise PreflightError(10, "Disk", f"Only {free_gb:.2f} GB free on output drive (min {MIN_FREE_DISK_GB} GB required)")


def run_all_preflights(
    recipe_path: Path,
    recipe_data: dict,
    recipe_name: str,
    recipe_sha256: str,
    boot_lane: str,
    is_force: bool = False,
):
    """Run all 10 preflight safety and validity checks before acquiring lock."""
    print(f"--- Running Preflight Checks for {recipe_name} ---")

    print("  [OK] Check 1: Atomic GPU lock held by this runner")
    system_stats = check_server_up_and_ownership()
    print(f"  [OK] Check 3: Lab server up & owned at 127.0.0.1:{LAB_PORT}")

    object_info = fetch_object_info()
    check_nodes_exist(recipe_data, object_info)
    print("  [OK] Check 4: All recipe node class_types exist on server")

    check_models_exist(recipe_data)
    print("  [OK] Check 5: All referenced models exist in models_manifest.md")

    check_widget_integrity(recipe_data, object_info)
    print("  [OK] Check 6: Widget integrity verified")

    check_affordability(recipe_name, recipe_sha256, boot_lane, is_force=is_force)
    print("  [OK] Check 7: Affordability check passed")

    queued_fixture_sha256s = check_fixtures_uploaded(recipe_data)
    print("  [OK] Check 8: Fixtures verified")

    check_boot_lane(recipe_name, system_stats)
    print("  [OK] Check 9: Boot lane verified (lab-8199, sage-free)")

    check_disk_space()
    print("  [OK] Check 10: Output disk space >= 5 GB")
    print("--- Preflight Complete: ALL CHECKS PASSED ---\n")
    return system_stats, queued_fixture_sha256s


class VramMonitorThread(threading.Thread):
    """Background thread polling nvidia-smi every 200ms (0.2s) for peak VRAM usage."""
    def __init__(self, interval: float = POLL_INTERVAL_S):
        super().__init__()
        self.interval = interval
        self.running = True
        self.peaks: List[float] = []

    def run(self):
        while self.running:
            try:
                used_mb = query_gpu_vram_mb()
                self.peaks.append(used_mb / 1024.0)
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self) -> float:
        self.running = False
        self.join(timeout=3.0)
        return max(self.peaks) if self.peaks else 0.0


def update_results_ledger(recipe_name: str, status: str, peak_vram: float, baseline_vram: float, wall_clock: float, notes: str):
    """Update human-readable ledger in RESULTS.md with wall clock and baseline VRAM."""
    if not RESULTS_LEDGER.exists():
        RESULTS_LEDGER.write_text(
            "# Results Ledger\n\n| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |\n|---|---|---|---|---|---|\n",
            encoding="utf-8"
        )
    
    lines = RESULTS_LEDGER.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    header_idx = -1

    for idx, line in enumerate(lines):
        if line.startswith("# Results Ledger"):
            header_idx = idx

    # If file header needs restoring to 6-column format
    if header_idx != -1 and len(lines) > header_idx + 4:
        if "| baseline VRAM" not in lines[header_idx + 4]:
            lines[header_idx + 4] = "| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |"
            lines[header_idx + 5] = "|---|---|---|---|---|---|"

    row_str = f"| {recipe_name} | {status} | {peak_vram:.2f} | {baseline_vram:.2f} | {wall_clock:.1f} | {notes} |"

    for line in lines:
        if line.startswith(f"| {recipe_name} |"):
            new_lines.append(row_str)
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(row_str)

    RESULTS_LEDGER.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[LEDGER] Updated RESULTS.md entry for {recipe_name}: {status}")


def update_engine_matrix_beta(
    recipe_name: str,
    tier: str,
    status: str,
    peak_vram: float,
    wall_clock: float,
    gated: str,
    pass_consecutive: str,
    boot_lane: str,
    notes: str,
):
    """Update one row using the matrix's current ten-column schema."""
    if not ENGINE_MATRIX_BETA.exists():
        return

    today = time.strftime("%Y-%m-%d")
    lines = ENGINE_MATRIX_BETA.read_text(encoding="utf-8").splitlines()
    
    peak_str = f"{peak_vram:.2f}" if peak_vram > 0 else "N/A"
    wall_str = f"{wall_clock:.1f}" if wall_clock > 0 else "N/A"
    row_str = (
        f"| {recipe_name} | {tier} | {status} | {peak_str} | {wall_str} | "
        f"{gated} | {pass_consecutive} | {boot_lane} | {today} | {notes} |"
    )
    
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"| {recipe_name} |"):
            new_lines.append(row_str)
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(row_str)

    ENGINE_MATRIX_BETA.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[MATRIX] Updated ENGINE_MATRIX_BETA.md for {recipe_name}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_recipe.py <path_to_recipe.json> [--suite] [--shutdown]")
        sys.exit(1)

    recipe_path = Path(sys.argv[1]).resolve()
    is_suite = "--suite" in sys.argv
    do_shutdown = "--shutdown" in sys.argv
    is_force = "--force" in sys.argv
    tier = "suite" if is_suite else "smoke"
    
    reserve_vram_text = os.environ.get("LAB_RESERVE_VRAM_GB")
    reserve_vram_gib = None
    clamp_target_gib = None
    physical_total_vram_gib = None
    disable_pinned = bool(os.environ.get("LAB_DISABLE_PINNED"))
    clamp_positions = [i for i, arg in enumerate(sys.argv) if arg == "--clamp"]
    try:
        if len(clamp_positions) > 1:
            raise ValueError("--clamp may be supplied only once")
        if clamp_positions:
            clamp_index = clamp_positions[0]
            if clamp_index + 1 >= len(sys.argv) or sys.argv[clamp_index + 1].startswith("--"):
                raise ValueError("--clamp requires a numeric target-card GiB value")
            clamp_target_gib = float(sys.argv[clamp_index + 1])
            physical_total_vram_gib = query_gpu_total_gib()
            reserve_vram_gib = reserve_for_target_gib(physical_total_vram_gib, clamp_target_gib)
            reserve_vram_text = f"{reserve_vram_gib:.3f}".rstrip("0").rstrip(".")
            os.environ["LAB_RESERVE_VRAM_GB"] = reserve_vram_text
        elif reserve_vram_text is not None:
            physical_total_vram_gib = query_gpu_total_gib()
            reserve_vram_gib = validate_reserve_gib(float(reserve_vram_text), physical_total_vram_gib)
            reserve_vram_text = f"{reserve_vram_gib:.3f}".rstrip("0").rstrip(".")
            os.environ["LAB_RESERVE_VRAM_GB"] = reserve_vram_text
    except (ValueError, subprocess.SubprocessError, FileNotFoundError) as exc:
        print(f"Error: invalid VRAM lane configuration: {exc}")
        sys.exit(2)

    for arg in sys.argv:
        if arg == "--disable-pinned-memory":
            disable_pinned = True
            os.environ["LAB_DISABLE_PINNED"] = "1"

    lane_parts = ["lab-8199", "sage-free"]
    if disable_pinned:
        lane_parts.append("no-pinned")
    if clamp_target_gib is not None:
        lane_parts.append(f"clamp-{clamp_target_gib:g}gb (reserve-{reserve_vram_gib:.3f}gb)")
    elif reserve_vram_gib is not None:
        lane_parts.append(f"reserve-{reserve_vram_gib:g}gb")
    boot_lane_str = ", ".join(lane_parts)

    if not recipe_path.exists():
        print(f"Error: Recipe file not found: {recipe_path}")
        sys.exit(1)

    recipe_name = recipe_path.stem
    RESULTS_DIR.mkdir(exist_ok=True)
    lock_manager: Optional[LockManager] = None
    try:
        try:
            queued_recipe_bytes = recipe_path.read_bytes()
            recipe_data = json.loads(queued_recipe_bytes.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"Error: Failed to parse recipe JSON: {e}")
            sys.exit(1)
        tier = str(recipe_data.get("tier", tier))
        requires_human_eyeball = recipe_data.get("contract", {}).get("engine") == "minimax_h3"

        # Check for BLOCKED status in recipe metadata
        if recipe_data.get("blocked", False):
            print(f"\n[BLOCKED] Recipe {recipe_name} is BLOCKED (required weights not present on disk).")
            update_results_ledger(recipe_name, "BLOCKED", 0.0, 0.0, 0.0, "Dry prep complete; weights not on disk (42.5 GB)")
            update_engine_matrix_beta(
                recipe_name, tier, "BLOCKED", 0.0, 0.0, "yes", "0/2", boot_lane_str, "Weights missing"
            )
            res_payload = {
                "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
                "recipe": recipe_name,
                "peak_vram_gb": 0.0,
                "baseline_vram_gb": 0.0,
                "duration_s": 0.0,
                "output_path": "",
                "boot_lane": boot_lane_str,
                "pass": False,
                "blocked": True,
                "run_count": 0
            }
            (RESULTS_DIR / f"{recipe_name}.json").write_text(json.dumps(res_payload, indent=2), encoding="utf-8")
            return

        queued_recipe_sha256 = sha256_bytes(queued_recipe_bytes)
        queued_runner_sha256 = sha256_file(Path(__file__).resolve())
        repo_git_commit = git_commit(REPO_ROOT)
        repo_git_dirty = git_dirty(REPO_ROOT)

        # Own the GPU lane before checking/booting port 8199. This prevents two
        # runners from racing through preflight and overwriting each other's PID
        # receipt before either queues a prompt.
        lock_manager = LockManager()
        lock_manager.acquire()

        # Execute all 10 Preflight checks
        try:
            system_stats, queued_fixture_sha256s = run_all_preflights(
                recipe_path,
                recipe_data,
                recipe_name,
                queued_recipe_sha256,
                boot_lane_str,
                is_force=is_force,
            )
        except PreflightError as e:
            print(f"\n[PREFLIGHT ABORT] {e}")
            sys.exit(1)

        comfyui_git_commit = git_commit(COMFYUI_ROOT)
        queued_model_fingerprints = model_fingerprints(recipe_data)
        server_argv = system_stats.get("system", {}).get("argv", [])
        identity_payload = {
            "recipe_sha256": queued_recipe_sha256,
            "runner_sha256": queued_runner_sha256,
            "fixture_sha256s": queued_fixture_sha256s,
            "model_fingerprints": queued_model_fingerprints,
            "boot_lane": boot_lane_str,
            "server_argv": server_argv,
            "comfyui_git_commit": comfyui_git_commit,
        }
        run_identity_sha256 = stable_identity(identity_payload)
        result_file = RESULTS_DIR / f"{recipe_name}.json"
        previous_result: Dict[str, Any] = {}
        if result_file.exists():
            try:
                previous_result = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        run_state = next_run_state(previous_result, run_identity_sha256)
        run_count = run_state["run_count"]
        config_run_count = run_state["config_run_count"]
        is_warm_cache = config_run_count >= 2 and run_state["previous_gate_pass"]

        # Execute Recipe under Lock
        with lock_manager as lock:
            # 1. Record baseline VRAM and Host RAM before run
            baseline_vram_gb = query_gpu_vram_mb() / 1024.0
            baseline_host_ram_gb = query_host_ram_gb()
            print(f"[RESOURCES] Baseline GPU VRAM: {baseline_vram_gb:.2f} GB | Host RAM: {baseline_host_ram_gb:.2f} GB")

            # 2. Start Resource monitor thread BEFORE /prompt POST
            monitor = ResourceMonitorThread(interval=POLL_INTERVAL_S)
            monitor.start()
            start_time = time.time()

            print(f"Queueing prompt for {recipe_name}...")
            prompt_dict = recipe_data.get("prompt", recipe_data)
            prompt_payload = {"prompt": prompt_dict}
            req_data = json.dumps(prompt_payload).encode("utf-8")
            req = urllib.request.Request(f"{COMFY_SERVER_URL}/prompt", data=req_data, headers={"Content-Type": "application/json"})
            
            try:
                with urllib.request.urlopen(req) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    prompt_id = res_json.get("prompt_id")
                    print(f"Queued successfully (Prompt ID: {prompt_id})")
            except urllib.error.URLError as e:
                monitor.stop()
                print(f"Error queueing prompt: {e}")
                sys.exit(1)

            # 3. Poll history until completion (keep monitor running!)
            completed = False
            execution_success = False
            output_path = ""
            target_file = None
            outputs = {}
            RUNNER_COMPLETION_TIMEOUT_S = 1800
            while time.time() - start_time < RUNNER_COMPLETION_TIMEOUT_S:  # 1800s (30 min) completion window
                time.sleep(0.5)
                try:
                    with urllib.request.urlopen(f"{COMFY_SERVER_URL}/history/{prompt_id}") as hresp:
                        hist = json.loads(hresp.read().decode("utf-8"))
                        if prompt_id in hist:
                            completed = True
                            prompt_hist = hist[prompt_id]
                            status_obj = prompt_hist.get("status", {})
                            status_str = status_obj.get("status_str", "")
                            completed_flag = status_obj.get("completed", False)
                            messages = status_obj.get("messages", [])
                            outputs = prompt_hist.get("outputs", {})
                            
                            has_error = (status_str != "success") or (not completed_flag) or (not outputs)
                            for m in messages:
                                if isinstance(m, (list, tuple)) and len(m) >= 2 and m[0] == "execution_error":
                                    has_error = True
                            
                            if not has_error:
                                output_path = extract_output_path(outputs)
                                
                                if not output_path:
                                    execution_success = False
                                    print(f"[ERROR] Execution for prompt {prompt_id} produced no output artifact (output_path is empty)!")
                                else:
                                    target_file = REPO_ROOT / "outputs" / output_path
                                    if not target_file.exists() or target_file.stat().st_size == 0:
                                        execution_success = False
                                        print(f"[ERROR] Output file '{output_path}' missing or 0 bytes on disk!")
                                    else:
                                        execution_success = True
                            else:
                                execution_success = False
                                print(f"[ERROR] ComfyUI execution failed for prompt {prompt_id}: status_str='{status_str}', outputs={bool(outputs)} (keys: {list(outputs.keys())}), messages={messages}")
                            break
                except Exception:
                    pass

            duration_s = time.time() - start_time

            # Stop GPU/RAM monitoring immediately after ComfyUI history
            # completes. ffprobe is post-render QA and must not contaminate the
            # measured render peak or leave the monitor alive on probe failure.
            peak_vram_gb, peak_host_ram_gb = monitor.stop()

            media_metrics: Dict[str, Any] = {}
            expects_video = any(
                isinstance(node, dict) and node.get("class_type") == "SaveVideo"
                for node in recipe_data.get("prompt", recipe_data).values()
            )
            requires_audio = any(
                isinstance(node, dict)
                and node.get("class_type") == "CreateVideo"
                and "audio" in node.get("inputs", {})
                for node in recipe_data.get("prompt", recipe_data).values()
            )
            if execution_success and target_file is not None:
                media_metrics["artifact_sha256"] = sha256_file(target_file)
                if expects_video:
                    media_metrics.update(probe_media_metrics(target_file))
                    media_metrics.update(bitrate_anomaly_fields(recipe_name, media_metrics, boot_lane_str))
            media_valid = (
                media_artifact_is_valid(
                    media_metrics,
                    recipe_data.get("contract", {}),
                    requires_audio=requires_audio,
                )
                if execution_success and expects_video
                else execution_success
            )
            if media_metrics.get("bitrate_anomaly"):
                print(
                    "[EYEBALL PRIORITY] bitrate-anomaly: video bytes/frame is "
                    f"{media_metrics.get('bitrate_ratio_to_clean_median')}x the clean same-lane median"
                )

            # Ensure peaks are at least baselines
            peak_vram_gb = max(peak_vram_gb, baseline_vram_gb)
            peak_host_ram_gb = max(peak_host_ram_gb, baseline_host_ram_gb)

            # 5. Invalid measurement guard: peak <= baseline + 0.2 GB means sampler missed render
            is_measurement_valid = peak_vram_gb > (baseline_vram_gb + 0.2)

            final_recipe_sha256 = sha256_file(recipe_path)
            final_runner_sha256 = sha256_file(Path(__file__).resolve())
            final_fixture_sha256s = fixture_sha256s(recipe_data)
            final_model_fingerprints = model_fingerprints(recipe_data)
            provenance_unchanged = (
                final_recipe_sha256 == queued_recipe_sha256
                and final_runner_sha256 == queued_runner_sha256
                and final_fixture_sha256s == queued_fixture_sha256s
                and final_model_fingerprints == queued_model_fingerprints
            )

            # gate_pass = this run individually passed the VRAM ceiling
            # warm_pass = two consecutive gate passes (the final certification)
            if not completed:
                gate_pass = False
                warm_pass = False
                status = f"TIMEOUT (exceeded {RUNNER_COMPLETION_TIMEOUT_S}s runner completion window)"
            elif not execution_success:
                gate_pass = False
                warm_pass = False
                if not outputs or not output_path:
                    status = "FAIL (no artifact output)"
                else:
                    status = "ERROR (execution error)"
            elif not media_valid:
                gate_pass = False
                warm_pass = False
                status = "FAIL (invalid or undecodable video artifact)"
            elif not provenance_unchanged:
                gate_pass = False
                warm_pass = False
                status = "INVALID (recipe, runner, or fixture changed during render)"
            elif not is_measurement_valid:
                gate_pass = False
                warm_pass = False
                status = "INVALID (sampler missed peak)"
                print(f"[WARNING] Invalid measurement! Peak ({peak_vram_gb:.2f} GB) <= baseline ({baseline_vram_gb:.2f} GB) + 0.2 GB. Refusing PASS.")
            elif peak_vram_gb > VRAM_GATE_GB:
                gate_pass = False
                warm_pass = False
                status = f"FAIL (VRAM {peak_vram_gb:.2f} GB > {VRAM_GATE_GB} GB)"
            elif clamp_target_gib is not None:
                target_limit = clamp_target_gib
                vram_delta = peak_vram_gb - baseline_vram_gb
                if vram_delta > target_limit:
                    gate_pass = False
                    warm_pass = False
                    status = f"FAIL (net VRAM {vram_delta:.2f} GB > clamp {target_limit} GB)"
                else:
                    gate_pass = True
                    warm_pass = is_warm_cache
                    is_marginal = (
                        vram_delta >= (target_limit - 0.25)
                        or peak_vram_gb >= (VRAM_GATE_GB - 0.25)
                    )
                    if is_marginal:
                        status = "PASS (marginal)" if is_warm_cache else "PASS (cold, marginal)"
                    else:
                        status = "PASS" if is_warm_cache else "PASS (cold)"
            else:
                gate_pass = True
                warm_pass = is_warm_cache
                is_marginal = (peak_vram_gb >= (VRAM_GATE_GB - 0.25))
                if is_marginal:
                    status = "PASS (marginal)" if is_warm_cache else "PASS (cold, marginal)"
                else:
                    status = "PASS" if is_warm_cache else "PASS (cold)"

            print(f"\n--- Run Summary ---")
            print(f"Recipe:        {recipe_name}")
            print(f"Run Count:     {run_count} (configuration run {config_run_count}; {'Warm cache' if is_warm_cache else 'Cold cache'})")
            print(f"Baseline VRAM: {baseline_vram_gb:.2f} GB | Host RAM: {baseline_host_ram_gb:.2f} GB")
            print(f"Peak VRAM:     {peak_vram_gb:.2f} GB (Gate <= {VRAM_GATE_GB} GB)")
            print(f"Peak Host RAM: {peak_host_ram_gb:.2f} GB")
            print(f"Wall Clock:    {duration_s:.1f} s")
            print(f"Boot Lane:     {boot_lane_str}")
            print(f"Status:        {status}")

            iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            res_payload = {
                "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
                "recipe": recipe_name,
                "run_number": run_count,
                "config_run_count": config_run_count,
                "status": status,
                "gate_pass": gate_pass,
                "pass": warm_pass,
                "warm_pass": warm_pass,
                "eyeball": "pending",
                "requires_human_eyeball": requires_human_eyeball,
                "promotion_ready": False if requires_human_eyeball else warm_pass,
                "certification_scope": "machine-only" if requires_human_eyeball else "machine",
                "recipe_sha256": queued_recipe_sha256,
                "runner_sha256": queued_runner_sha256,
                "fixture_sha256s": queued_fixture_sha256s,
                "model_fingerprints": queued_model_fingerprints,
                "provenance_unchanged": provenance_unchanged,
                "run_identity_sha256": run_identity_sha256,
                "identity": identity_payload,
                "git_commit": repo_git_commit,
                "git_dirty": repo_git_dirty,
                "comfyui_git_commit": comfyui_git_commit,
                "server_argv": server_argv,
                "clamp_target_gib": clamp_target_gib,
                "reserve_vram_gib": reserve_vram_gib,
                "physical_total_vram_gib": physical_total_vram_gib,
                "peak_vram_gb": round(peak_vram_gb, 2),
                "baseline_vram_gb": round(baseline_vram_gb, 2),
                "peak_host_ram_gb": round(peak_host_ram_gb, 2),
                "baseline_host_ram_gb": round(baseline_host_ram_gb, 2),
                "duration_s": round(duration_s, 1),
                "output_path": output_path,
                "boot_lane": boot_lane_str,
                "timestamp": iso_timestamp,
                "prompt_id": prompt_id,
                "valid_measurement": is_measurement_valid,
                "run_count": run_count,
                "blocked": False,
                **media_metrics,
            }
            run_receipt_file = RESULTS_DIR / f"{recipe_name}_run{run_count}.json"
            run_receipt_file.write_text(json.dumps(res_payload, indent=2), encoding="utf-8")
            result_file.write_text(json.dumps(res_payload, indent=2), encoding="utf-8")

            display_status = status
            if requires_human_eyeball and gate_pass:
                display_status += " (machine; human pending)"
            ledger_note = f"Run #{run_count}; boot lane: {boot_lane_str}"
            if media_metrics.get("bitrate_anomaly"):
                ledger_note += "; bitrate-anomaly (priority eyeball, non-gating)"
            update_results_ledger(recipe_name, display_status, peak_vram_gb, baseline_vram_gb, duration_s, ledger_note)
            matrix_note = f"Measured on box ({display_status})"
            if media_metrics.get("bitrate_anomaly"):
                matrix_note += "; bitrate-anomaly"
            pass_consecutive = "2/2" if warm_pass else ("1/2" if gate_pass else "0/2")
            update_engine_matrix_beta(
                recipe_name,
                tier,
                display_status,
                peak_vram_gb,
                duration_s,
                "yes",
                pass_consecutive,
                boot_lane_str,
                matrix_note,
            )
    finally:
        if lock_manager is not None:
            lock_manager.release()
        if do_shutdown:
            shutdown_lab_server()


if __name__ == "__main__":
    main()
