#!/usr/bin/env python3
"""
Debug Prompt Error script for vram-recipe-lab.
Boots server if needed, posts a recipe JSON to http://127.0.0.1:8199/prompt,
and prints full server error response body.
"""

import json
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
RECIPE_PATH = REPO_ROOT / "recipes" / "wan_ti2v_low.json"
SERVER_URL = "http://127.0.0.1:8199"
SERVER_PID_FILE = REPO_ROOT / ".server.pid"
BOOT_CMD = REPO_ROOT / "boot_lab_server.cmd"


def is_server_listening() -> bool:
    try:
        req = urllib.request.Request(f"{SERVER_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def boot_server():
    if is_server_listening():
        return

    print(f"[SERVER] Launching lab server via {BOOT_CMD.name} on port 8199...")
    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(
        ["cmd.exe", "/c", str(BOOT_CMD)],
        cwd=str(REPO_ROOT),
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    SERVER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"[SERVER] Recorded server PID {proc.pid} in {SERVER_PID_FILE.name}")

    start_t = time.time()
    while time.time() - start_t < 120:
        if is_server_listening():
            print(f"[SERVER] Lab server online on port 8199 after {time.time() - start_t:.1f}s")
            return
        time.sleep(2)

    raise RuntimeError("Lab server failed to come online on port 8199 within 120s timeout")


def main():
    boot_server()

    recipe_data = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    prompt = recipe_data.get("prompt", {})
    payload = {"prompt": prompt}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{SERVER_URL}/prompt", data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Success: {resp.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.reason}")
        error_body = e.read().decode("utf-8", errors="replace")
        print("\n--- Server Error Details ---")
        print(error_body)
    except Exception as e:
        print(f"Exception: {e}")


if __name__ == "__main__":
    main()
