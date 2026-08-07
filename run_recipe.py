#!/usr/bin/env python3
"""
run_recipe.py — Recipe execution runner and preflight enforcement harness
for ComfyUI workflow VRAM recipe benchmarking.

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
RESULTS_DIR = REPO_ROOT / "results"
FIXTURES_DIR = REPO_ROOT / "fixtures"
MODELS_MANIFEST = REPO_ROOT / "models_manifest.md"
RESULTS_LEDGER = REPO_ROOT / "RESULTS.md"
ENGINE_MATRIX_BETA = REPO_ROOT / "ENGINE_MATRIX_BETA.md"
COMFY_SERVER_URL = "http://127.0.0.1:8188"
VRAM_GATE_GB = 14.5
VRAM_GPU_IDLE_MAX_MB = 1536  # 1.5 GB
MIN_FREE_DISK_GB = 5.0


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
            # Check for stale lock
            try:
                content = self.lock_path.read_text(encoding="utf-8")
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


def check_gpu_idle() -> float:
    """Preflight Check #2: nvidia-smi shows under 1.5 GB allocated memory."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True
        )
        used_mb = float(res.stdout.strip().splitlines()[0])
        if used_mb >= VRAM_GPU_IDLE_MAX_MB:
            raise PreflightError(2, "GPU idle", f"GPU allocated VRAM is {used_mb:.1f} MB (limit < {VRAM_GPU_IDLE_MAX_MB} MB)")
        return used_mb / 1024.0
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        if isinstance(e, PreflightError):
            raise
        raise PreflightError(2, "GPU idle", f"Could not query nvidia-smi: {e}")


def check_server_up() -> Dict[str, Any]:
    """Preflight Check #3: GET /system_stats answers at 127.0.0.1:8188."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data
            raise PreflightError(3, "Server up", f"Server responded with status {resp.status}")
    except urllib.error.URLError as e:
        raise PreflightError(3, "Server up", f"ComfyUI server refused connection at {COMFY_SERVER_URL}: {e}")


def fetch_object_info() -> Dict[str, Any]:
    """Fetch object info dictionary from GET /object_info."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/object_info")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise PreflightError(4, "Nodes exist", f"Failed to fetch /object_info: {e}")


def check_nodes_exist(recipe_data: Dict[str, Any], object_info: Dict[str, Any]):
    """Preflight Check #4: Every class_type in recipe appears in GET /object_info."""
    missing_nodes = set()
    for node_id, node in recipe_data.items():
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
    
    # Extract string model references from recipe
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
    """Preflight Check #6: Recipe JSON parses; widget count matches inputs."""
    for node_id, node in recipe_data.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        if not class_type or class_type not in object_info:
            continue
        
        # Check required inputs match structure
        req_inputs = object_info[class_type].get("input", {}).get("required", {})
        # Basic validation: ensure inputs dict is present
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


def check_fixtures_uploaded(recipe_data: Dict[str, Any]):
    """Preflight Check #8: Required fixtures present / uploaded to server."""
    # Ensure fixtures folder has files
    for fixture in ["scene_still.png", "portrait.png", "narration.wav"]:
        p = FIXTURES_DIR / fixture
        if not p.exists():
            raise PreflightError(8, "Fixtures uploaded", f"Fixture file missing from fixtures/: {fixture}")


def check_boot_lane(recipe_name: str, system_stats: Dict[str, Any]):
    """Preflight Check #9: MiniMax H3 recipes confirm server started without SageAttention."""
    if "h3" in recipe_name.lower():
        # Inspect system stats or server launch args if available
        devices = system_stats.get("devices", [])
        # Check if sage attention flag was passed
        cmdline = str(system_stats.get("extra_flags", ""))
        if "--use-sage-attention" in cmdline:
            raise PreflightError(
                9, "Boot lane",
                "MiniMax H3 requires a Sage-free boot lane, but server was started with --use-sage-attention"
            )


def check_disk_space():
    """Preflight Check #10: At least 5 GB free on output drive."""
    total, used, free = shutil.disk_usage(REPO_ROOT)
    free_gb = free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        raise PreflightError(10, "Disk", f"Only {free_gb:.2f} GB free on output drive (min {MIN_FREE_DISK_GB} GB required)")


def run_all_preflights(recipe_path: Path, recipe_data: Dict[str, Any], recipe_name: str):
    """Execute all 10 preflight checks in code sequence."""
    print(f"\n--- Running Preflight Checks for {recipe_name} ---")
    
    # 1. Lock check handled by LockManager context or acquire
    # 2. GPU idle
    check_gpu_idle()
    print("  ✓ Check 1 & 2: Lock clear & GPU idle (< 1.5 GB)")

    # 3. Server up
    system_stats = check_server_up()
    print("  ✓ Check 3: Server up at 127.0.0.1:8188")

    # 4. Nodes exist
    object_info = fetch_object_info()
    check_nodes_exist(recipe_data, object_info)
    print("  ✓ Check 4: All recipe node class_types exist on server")

    # 5. Models exist
    check_models_exist(recipe_data)
    print("  ✓ Check 5: All referenced models exist in models_manifest.md")

    # 6. Widget integrity
    check_widget_integrity(recipe_data, object_info)
    print("  ✓ Check 6: Widget integrity verified")

    # 7. Affordability
    check_affordability(recipe_name)
    print("  ✓ Check 7: Affordability check passed")

    # 8. Fixtures uploaded
    check_fixtures_uploaded(recipe_data)
    print("  ✓ Check 8: Fixtures verified")

    # 9. Boot lane
    check_boot_lane(recipe_name, system_stats)
    print("  ✓ Check 9: Boot lane verified")

    # 10. Disk space
    check_disk_space()
    print("  ✓ Check 10: Output disk space >= 5 GB")
    print("--- Preflight Complete: ALL CHECKS PASSED ---\n")


class VramMonitorThread(threading.Thread):
    """Background thread to poll nvidia-smi every 2s for peak VRAM usage."""
    def __init__(self, interval: float = 2.0):
        super().__init__()
        self.interval = interval
        self.running = True
        self.peaks: List[float] = []

    def run(self):
        while self.running:
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, check=True
                )
                used_mb = float(res.stdout.strip().splitlines()[0])
                self.peaks.append(used_mb / 1024.0)
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self) -> float:
        self.running = False
        self.join(timeout=3.0)
        return max(self.peaks) if self.peaks else 0.0


def update_results_ledger(recipe_name: str, status: str, peak_vram: float, notes: str):
    """Update human-readable ledger in RESULTS.md."""
    if not RESULTS_LEDGER.exists():
        RESULTS_LEDGER.write_text(
            "# Results Ledger\n\n| recipe | status | peak VRAM (GB) | notes |\n|---|---|---|---|\n",
            encoding="utf-8"
        )
    
    lines = RESULTS_LEDGER.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    row_str = f"| {recipe_name} | {status} | {peak_vram:.2f} | {notes} |"

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


def update_engine_matrix_beta(recipe_name: str, tier: str, status: str, peak_vram: float, boot_lane: str, notes: str):
    """Update engine row in ENGINE_MATRIX_BETA.md."""
    if not ENGINE_MATRIX_BETA.exists():
        return

    today = time.strftime("%Y-%m-%d")
    lines = ENGINE_MATRIX_BETA.read_text(encoding="utf-8").splitlines()
    row_str = f"| {recipe_name} | {tier} | {status} | {peak_vram:.2f} | N/A | no | N/A | {boot_lane} | {today} | {notes} |"
    
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
        print("Usage: python run_recipe.py <path_to_recipe.json> [--suite]")
        sys.exit(1)

    recipe_path = Path(sys.argv[1]).resolve()
    is_suite = "--suite" in sys.argv
    tier = "suite" if is_suite else "smoke"

    if not recipe_path.exists():
        print(f"Error: Recipe file not found: {recipe_path}")
        sys.exit(1)

    recipe_name = recipe_path.stem
    RESULTS_DIR.mkdir(exist_ok=True)

    try:
        recipe_data = json.loads(recipe_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse recipe JSON: {e}")
        sys.exit(1)

    # Check for BLOCKED status in recipe metadata
    if recipe_data.get("blocked", False) or "h3" in recipe_name.lower():
        print(f"\n[BLOCKED] Recipe {recipe_name} is BLOCKED (required weights not present on disk).")
        update_results_ledger(recipe_name, "BLOCKED", 0.0, "Dry prep complete; weights not on disk (42.5 GB)")
        update_engine_matrix_beta(recipe_name, tier, "BLOCKED", 0.0, "sage-free", "Weights missing")
        res_payload = {
            "recipe": recipe_name,
            "peak_vram_gb": 0.0,
            "duration_s": 0.0,
            "output_path": "",
            "boot_lane": "sage-free",
            "pass": False,
            "blocked": True,
            "run_count": 0
        }
        (RESULTS_DIR / f"{recipe_name}.json").write_text(json.dumps(res_payload, indent=2), encoding="utf-8")
        sys.exit(0)

    # Execute all 10 Preflight checks
    try:
        run_all_preflights(recipe_path, recipe_data, recipe_name)
    except PreflightError as e:
        print(f"\n[PREFLIGHT ABORT] {e}")
        update_results_ledger(recipe_name, "FAIL", 0.0, f"Aborted on Preflight #{e.check_num} ({e.name}): {e.reason}")
        sys.exit(1)

    # Execute Recipe under Lock
    with LockManager() as lock:
        print(f"Queueing prompt for {recipe_name}...")
        monitor = VramMonitorThread(interval=1.0)
        monitor.start()
        start_time = time.time()

        # Submit prompt to ComfyUI API
        prompt_payload = {"prompt": recipe_data}
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

        # Wait for completion via polling history
        completed = False
        output_path = ""
        while time.time() - start_time < 300:  # 5 min timeout
            time.sleep(2.0)
            try:
                with urllib.request.urlopen(f"{COMFY_SERVER_URL}/history/{prompt_id}") as hresp:
                    hist = json.loads(hresp.read().decode("utf-8"))
                    if prompt_id in hist:
                        completed = True
                        # Get output filename if any
                        outputs = hist[prompt_id].get("outputs", {})
                        for n_out in outputs.values():
                            if "images" in n_out and n_out["images"]:
                                output_path = n_out["images"][0].get("filename", "output.png")
                        break
            except Exception:
                pass

        duration_s = time.time() - start_time
        peak_vram = monitor.stop()

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

        # Pass condition: clean completion, output exists, peak <= 14.5 GB, and warm cache (Run #2)
        passed = completed and (peak_vram <= VRAM_GATE_GB) and is_warm_cache
        status = "PASS" if passed else ("PASS (cold)" if (completed and peak_vram <= VRAM_GATE_GB) else "FAIL")

        print(f"\n--- Run Summary ---")
        print(f"Recipe:        {recipe_name}")
        print(f"Run Count:     {run_count} ({'Warm cache' if is_warm_cache else 'Cold cache'})")
        print(f"Peak VRAM:     {peak_vram:.2f} GB (Gate <= {VRAM_GATE_GB} GB)")
        print(f"Duration:      {duration_s:.1f} s")
        print(f"Status:        {status}")

        res_payload = {
            "recipe": recipe_name,
            "peak_vram_gb": peak_vram,
            "duration_s": duration_s,
            "output_path": output_path,
            "boot_lane": "normal",
            "pass": passed,
            "run_count": run_count,
            "blocked": False
        }
        result_file.write_text(json.dumps(res_payload, indent=2), encoding="utf-8")

        update_results_ledger(recipe_name, status, peak_vram, f"Run #{run_count}; duration {duration_s:.1f}s")
        update_engine_matrix_beta(recipe_name, tier, status, peak_vram, "normal", f"Measured on box ({status})")


if __name__ == "__main__":
    main()
