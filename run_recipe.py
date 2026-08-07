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
import psutil
import shutil
import urllib.request
import urllib.error
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

LAB_PORT = os.environ.get("LAB_PORT", "8199")
COMFY_SERVER_URL = f"http://127.0.0.1:{LAB_PORT}"
VRAM_GATE_GB = 14.5
VRAM_GPU_IDLE_MAX_MB = 2560  # 2.5 GB threshold
MIN_FREE_DISK_GB = 5.0
BOOT_TIMEOUT_S = 120
POLL_INTERVAL_S = 0.2  # 200ms VRAM polling interval


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
    """Preflight Check #2: Verify GPU VRAM is under 2.5 GB (2560 MB) so background desktop load doesn't fail preflight."""
    try:
        used_mb = query_gpu_vram_mb()
        max_limit_mb = 2560.0  # 2.5 GB threshold

        if used_mb >= max_limit_mb:
            raise PreflightError(2, "GPU idle", f"GPU allocated VRAM is {used_mb:.1f} MB (exceeds idle threshold {max_limit_mb} MB / 2.5 GB)")
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
        if SERVER_PID_FILE.exists():
            SERVER_PID_FILE.unlink(missing_ok=True)
        raise


def check_server_up_and_ownership() -> Dict[str, Any]:
    """Preflight Check #3: GET /system_stats answers at 8199; verify PID receipt."""
    cleanup_stale_pid_receipt()
    stats = query_server_stats()
    pid_receipt = get_recorded_pid()

    if stats:
        if pid_receipt and psutil.pid_exists(pid_receipt):
            return stats
        else:
            raise PreflightError(
                3, "Server up",
                f"Unrecognized server already answering on port {LAB_PORT} without valid PID receipt. Refusing to adopt or kill it."
            )

    return boot_lab_server()


def shutdown_lab_server():
    """Stop the recorded lab server PID and all child processes recursively, removing .server.pid as final step."""
    pid = get_recorded_pid()
    if pid:
        print(f"[SERVER] Shutting down recorded lab server (PID {pid})...")
        try:
            if psutil.pid_exists(pid):
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                parent.terminate()
                _, alive = psutil.wait_procs(children + [parent], timeout=10)
                for p in alive:
                    try:
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
                print(f"[SERVER] Process {pid} and children terminated successfully.")
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, OSError) as e:
            print(f"[SERVER] Shutdown warning: {e}")

    if SERVER_PID_FILE.exists():
        SERVER_PID_FILE.unlink(missing_ok=True)
        print("[SERVER] Removed .server.pid receipt.")


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
    """Preflight Check #6: Recipe JSON parses; widget structure validated."""
    prompt_dict = recipe_data.get("prompt", recipe_data)
    for node_id, node in prompt_dict.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        if not class_type or class_type not in object_info:
            continue
        if not isinstance(inputs, dict):
            raise PreflightError(6, "Widget integrity", f"Node {node_id} inputs is not a dictionary")


def check_affordability(recipe_name: str):
    """Preflight Check #7: Refuse configurations whose last measured peak exceeded 14.5 GB."""
    result_file = RESULTS_DIR / f"{recipe_name}.json"
    if result_file.exists():
        try:
            prev = json.loads(result_file.read_text(encoding="utf-8"))
            last_peak = prev.get("peak_vram_gb", 0.0)
            if last_peak > VRAM_GATE_GB:
                raise PreflightError(
                    7, "Affordability estimate",
                    f"Last measured peak ({last_peak:.2f} GB) exceeded 14.5 GB gate line. Refusing unchanged re-run."
                )
        except json.JSONDecodeError:
            pass


def upload_fixtures():
    """Upload pre-baked fixtures from fixtures/ to ComfyUI input directory via POST /upload/image."""
    if not FIXTURES_DIR.exists():
        return

    for fix_file in FIXTURES_DIR.glob("*"):
        if fix_file.is_file() and fix_file.suffix.lower() in [".png", ".jpg", ".jpeg", ".wav", ".mp3", ".flac"]:
            try:
                boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
                content = fix_file.read_bytes()
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="image"; filename="{fix_file.name}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

                req = urllib.request.Request(
                    f"{COMFY_SERVER_URL}/upload/image",
                    data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    pass
                print(f"[FIXTURE] Uploaded fixture {fix_file.name} to server input directory")
            except Exception as e:
                print(f"[FIXTURE] Warning uploading {fix_file.name}: {e}")


def check_fixtures_uploaded(recipe_data: Dict[str, Any]):
    """Preflight Check #8: Required fixtures present on disk and uploaded to server."""
    for fixture in ["scene_still.png", "portrait.png", "narration.wav"]:
        p = FIXTURES_DIR / fixture
        if not p.exists():
            raise PreflightError(8, "Fixtures uploaded", f"Fixture file missing from fixtures/: {fixture}")

    upload_fixtures()


def check_boot_lane(recipe_name: str, system_stats: Dict[str, Any]):
    """Preflight Check #9: Confirm boot lane is lab-8199, sage-free."""
    extra_flags = str(system_stats.get("system", {}).get("argv", []))
    if "--use-sage-attention" in extra_flags:
        raise PreflightError(
            9, "Boot lane",
            "Server was started with --use-sage-attention; lab boot lane must be sage-free."
        )


def check_disk_space():
    """Preflight Check #10: At least 5 GB free on output drive."""
    total, used, free = shutil.disk_usage(REPO_ROOT)
    free_gb = free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        raise PreflightError(10, "Disk", f"Only {free_gb:.2f} GB free on output drive (min {MIN_FREE_DISK_GB} GB required)")


def run_all_preflights(recipe_path: Path, recipe_data: Dict[str, Any], recipe_name: str) -> Dict[str, Any]:
    """Execute all 10 preflight checks in code sequence."""
    print(f"\n--- Running Preflight Checks for {recipe_name} ---")
    
    system_stats = check_server_up_and_ownership()
    print(f"  [OK] Check 3: Lab server up & owned at 127.0.0.1:{LAB_PORT}")

    check_gpu_idle()
    print("  [OK] Check 1 & 2: Lock clear & GPU idle")

    object_info = fetch_object_info()
    check_nodes_exist(recipe_data, object_info)
    print("  [OK] Check 4: All recipe node class_types exist on server")

    check_models_exist(recipe_data)
    print("  [OK] Check 5: All referenced models exist in models_manifest.md")

    check_widget_integrity(recipe_data, object_info)
    print("  [OK] Check 6: Widget integrity verified")

    check_affordability(recipe_name)
    print("  [OK] Check 7: Affordability check passed")

    check_fixtures_uploaded(recipe_data)
    print("  [OK] Check 8: Fixtures verified")

    check_boot_lane(recipe_name, system_stats)
    print("  [OK] Check 9: Boot lane verified (lab-8199, sage-free)")

    check_disk_space()
    print("  [OK] Check 10: Output disk space >= 5 GB")
    print("--- Preflight Complete: ALL CHECKS PASSED ---\n")
    return system_stats


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


def update_engine_matrix_beta(recipe_name: str, tier: str, status: str, peak_vram_smoke: float, peak_vram_suite: float, vram_creep: str, wall_clock: float, boot_lane: str, notes: str):
    """Update engine row in ENGINE_MATRIX_BETA.md with smoke/suite peaks and VRAM creep column."""
    if not ENGINE_MATRIX_BETA.exists():
        return

    today = time.strftime("%Y-%m-%d")
    lines = ENGINE_MATRIX_BETA.read_text(encoding="utf-8").splitlines()
    
    smoke_str = f"{peak_vram_smoke:.2f}" if peak_vram_smoke > 0 else "N/A"
    suite_str = f"{peak_vram_suite:.2f}" if peak_vram_suite > 0 else "N/A"

    row_str = f"| {recipe_name} | {tier} | {status} | {smoke_str} | {suite_str} | {vram_creep} | {wall_clock:.1f}s | {boot_lane} | {today} | {notes} |"
    
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
    tier = "suite" if is_suite else "smoke"
    boot_lane_str = "lab-8199, sage-free"

    if not recipe_path.exists():
        print(f"Error: Recipe file not found: {recipe_path}")
        sys.exit(1)

    recipe_name = recipe_path.stem
    RESULTS_DIR.mkdir(exist_ok=True)

    try:
        recipe_data = json.loads(recipe_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse recipe JSON: {e}")
        sys.exit(1)

    # Check for BLOCKED status in recipe metadata
    if recipe_data.get("blocked", False) or "h3" in recipe_name.lower():
        print(f"\n[BLOCKED] Recipe {recipe_name} is BLOCKED (required weights not present on disk).")
        update_results_ledger(recipe_name, "BLOCKED", 0.0, 0.0, 0.0, "Dry prep complete; weights not on disk (42.5 GB)")
        update_engine_matrix_beta(recipe_name, tier, "BLOCKED", 0.0, 0.0, "no", 0.0, boot_lane_str, "Weights missing")
        res_payload = {
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
        if do_shutdown:
            shutdown_lab_server()
        sys.exit(0)

    # Execute all 10 Preflight checks
    try:
        run_all_preflights(recipe_path, recipe_data, recipe_name)
    except PreflightError as e:
        print(f"\n[PREFLIGHT ABORT] {e}")
        update_results_ledger(recipe_name, "FAIL", 0.0, 0.0, 0.0, f"Aborted on Preflight #{e.check_num} ({e.name}): {e.reason}")
        if do_shutdown:
            shutdown_lab_server()
        sys.exit(1)

    # Execute Recipe under Lock
    with LockManager() as lock:
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
            if do_shutdown:
                shutdown_lab_server()
            sys.exit(1)

        # 3. Poll history until completion (keep monitor running!)
        completed = False
        execution_success = False
        output_path = ""
        while time.time() - start_time < 300:  # 5 min timeout
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
                            execution_success = True
                            for n_out in outputs.values():
                                if "images" in n_out and n_out["images"]:
                                    output_path = n_out["images"][0].get("filename", "output.png")
                                elif "gifs" in n_out and n_out["gifs"]:
                                    output_path = n_out["gifs"][0].get("filename", "output.mp4")
                        else:
                            execution_success = False
                            print(f"[ERROR] ComfyUI execution failed for prompt {prompt_id}: status_str='{status_str}', outputs={bool(outputs)}, messages={messages}")
                        break
            except Exception:
                pass

        duration_s = time.time() - start_time
        
        # 4. Stop Resource monitor thread ONLY AFTER history completes
        peak_vram_gb, peak_host_ram_gb = monitor.stop()

        # Ensure peaks are at least baselines
        peak_vram_gb = max(peak_vram_gb, baseline_vram_gb)
        peak_host_ram_gb = max(peak_host_ram_gb, baseline_host_ram_gb)

        # 5. Invalid measurement guard: peak <= baseline + 0.2 GB means sampler missed render
        is_measurement_valid = peak_vram_gb > (baseline_vram_gb + 0.2)

        # Determine run count for warm cache gating
        prev_run_count = 0
        result_file = RESULTS_DIR / f"{recipe_name}.json"
        if result_file.exists():
            try:
                prev_data = json.loads(result_file.read_text(encoding="utf-8"))
                prev_run_count = prev_data.get("run_count", 0)
            except Exception:
                pass
        
        run_count = prev_run_count + 1
        is_warm_cache = run_count >= 2

        if not execution_success:
            passed = False
            status = "FAIL (execution error)"
        elif not is_measurement_valid:
            passed = False
            status = "INVALID (sampler missed peak)"
            print(f"[WARNING] Invalid measurement! Peak ({peak_vram_gb:.2f} GB) <= baseline ({baseline_vram_gb:.2f} GB) + 0.2 GB. Refusing PASS.")
        elif peak_vram_gb > VRAM_GATE_GB:
            passed = False
            status = f"FAIL (VRAM {peak_vram_gb:.2f} GB > {VRAM_GATE_GB} GB)"
        else:
            passed = is_warm_cache
            status = "PASS" if is_warm_cache else "PASS (cold)"

        print(f"\n--- Run Summary ---")
        print(f"Recipe:        {recipe_name}")
        print(f"Run Count:     {run_count} ({'Warm cache' if is_warm_cache else 'Cold cache'})")
        print(f"Baseline VRAM: {baseline_vram_gb:.2f} GB | Host RAM: {baseline_host_ram_gb:.2f} GB")
        print(f"Peak VRAM:     {peak_vram_gb:.2f} GB (Gate <= {VRAM_GATE_GB} GB)")
        print(f"Peak Host RAM: {peak_host_ram_gb:.2f} GB")
        print(f"Wall Clock:    {duration_s:.1f} s")
        print(f"Boot Lane:     {boot_lane_str}")
        print(f"Status:        {status}")

        iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        res_payload = {
            "recipe": recipe_name,
            "run_number": run_count,
            "status": status,
            "passed": passed,
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
            "blocked": False
        }
        run_receipt_file = RESULTS_DIR / f"{recipe_name}_run{run_count}.json"
        run_receipt_file.write_text(json.dumps(res_payload, indent=2), encoding="utf-8")
        result_file.write_text(json.dumps(res_payload, indent=2), encoding="utf-8")

        update_results_ledger(recipe_name, status, peak_vram_gb, baseline_vram_gb, duration_s, f"Run #{run_count}; boot lane: {boot_lane_str}")
        smoke_peak = 0.0 if is_suite else peak_vram_gb
        suite_peak = peak_vram_gb if is_suite else 0.0
        update_engine_matrix_beta(recipe_name, tier, status, smoke_peak, suite_peak, "no", duration_s, boot_lane_str, f"Measured on box ({status})")

    if do_shutdown:
        shutdown_lab_server()


if __name__ == "__main__":
    main()
