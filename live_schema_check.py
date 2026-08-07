#!/usr/bin/env python3
"""
Live Server Schema Validation Script for vram-recipe-lab.
Ensures lab server is online at http://127.0.0.1:8199 (booting if needed),
queries GET http://127.0.0.1:8199/object_info, and validates:
  1. Every node class_type exists on the server.
  2. Every input key in recipe JSON matches required/optional input schema in object_info.
  3. Reports any missing nodes or unknown input keys.
"""

import json
import os
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"
SERVER_URL = "http://127.0.0.1:8199"
SERVER_PID_FILE = REPO_ROOT / ".server.pid"
BOOT_CMD = REPO_ROOT / "boot_lab_server.cmd"

REQUIRED_RECIPES = [
    "t2i_low", "t2i_high",
    "wan_ti2v_low", "wan_ti2v_high",
    "wan_i2v_14b_low", "wan_i2v_14b_high",
    "ltx_i2v_low", "ltx_i2v_high",
    "ltx_audio_low", "ltx_lipsync_low",
    "h3_t2v_low", "h3_t2v_best",
    "h3_i2v_low", "h3_i2v_best",
    "h3_r2v_low", "h3_r2v_best"
]


def is_server_listening() -> bool:
    try:
        req = urllib.request.Request(f"{SERVER_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def boot_server():
    if is_server_listening():
        print(f"[SERVER] Lab server already online at {SERVER_URL}")
        return

    print(f"[SERVER] Launching lab server via {BOOT_CMD.name} on port 8199...")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    proc = subprocess.Popen(
        [str(BOOT_CMD)],
        cwd=str(REPO_ROOT),
        creationflags=creationflags,
        close_fds=True
    )
    SERVER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"[SERVER] Recorded server PID {proc.pid} in {SERVER_PID_FILE.name}")

    start_t = time.time()
    while time.time() - start_t < 120:
        if is_server_listening():
            elapsed = time.time() - start_t
            print(f"[SERVER] Lab server online on port 8199 after {elapsed:.1f}s")
            return
        time.sleep(2)

    raise RuntimeError("Lab server failed to come online on port 8199 within 120s timeout")


def shutdown_server():
    if SERVER_PID_FILE.exists():
        try:
            pid = int(SERVER_PID_FILE.read_text(encoding="utf-8").strip())
            print(f"[SERVER] Shutting down recorded lab server process PID {pid}...")
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            SERVER_PID_FILE.unlink(missing_ok=True)
        except Exception as e:
            print(f"[SERVER] Warning during shutdown: {e}")


def fetch_object_info() -> dict:
    req = urllib.request.Request(f"{SERVER_URL}/object_info")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("=========================================================")
    print("   vram-recipe-lab :: LIVE SERVER SCHEMA CHECK (/object_info)  ")
    print("=========================================================\n")

    boot_server()
    object_info = fetch_object_info()
    print(f"[SERVER] Connected to {SERVER_URL} (Loaded {len(object_info)} node schemas)\n")

    all_valid = True

    for recipe_name in REQUIRED_RECIPES:
        recipe_path = RECIPES_DIR / f"{recipe_name}.json"
        if not recipe_path.exists():
            print(f"[MISSING] {recipe_name}.json file not found!")
            all_valid = False
            continue

        recipe_data = json.loads(recipe_path.read_text(encoding="utf-8"))
        prompt = recipe_data.get("prompt", {})
        
        errors = []
        warnings = []

        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            inputs = node.get("inputs", {})

            if not class_type:
                errors.append(f"Node {node_id} missing 'class_type'")
                continue

            if class_type not in object_info:
                errors.append(f"Node {node_id} class_type '{class_type}' NOT FOUND on server schema")
                continue

            info = object_info[class_type]
            req_inputs = info.get("input", {}).get("required", {})
            opt_inputs = info.get("input", {}).get("optional", {})
            valid_keys = set(req_inputs.keys()) | set(opt_inputs.keys())

            for in_key in inputs:
                if in_key not in valid_keys:
                    warnings.append(f"Node {node_id} ({class_type}) input '{in_key}' not in server schema")

        status_str = "PASS" if not errors else "FAIL"
        blocked_str = "[BLOCKED]" if recipe_data.get("blocked", False) else "[ACTIVE]"
        print(f"  {status_str:4s} | {blocked_str:9s} | {recipe_name:20s} ({len(prompt)} nodes)")
        for err in errors:
            print(f"         +-- ERROR: {err}")
        for warn in warnings:
            print(f"         +-- WARN:  {warn}")

        if errors:
            all_valid = False

    print("\n---------------------------------------------------------")
    print(f"Schema Check Result: {'ALL 16 RECIPES PASSED LIVE SCHEMAS' if all_valid else 'SOME RECIPES FAILED SCHEMAS'}")
    print("=========================================================\n")

    shutdown_server()

    if not all_valid:
        sys.exit(1)


if __name__ == "__main__":
    main()
