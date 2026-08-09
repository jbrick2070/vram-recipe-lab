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
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"
SERVER_URL = "http://127.0.0.1:8199"
BOOT_CMD = REPO_ROOT / "boot_lab_server.cmd"

REQUIRED_RECIPES = [
    "t2i_low", "t2i_high",
    "wan_ti2v_low", "wan_ti2v_high",
    "wan_i2v_14b_low", "wan_i2v_14b_high",
    "ltx_t2v_ckpt", "ltx_t2v_gguf", "ltx_t2v_fullhd_experimental",
    "ltx_i2v_ckpt", "ltx_i2v_gguf", "ltx_i2v_fullhd_experimental",
    "ltx_audio_ckpt", "ltx_audio_gguf", "ltx_audio_fullhd_experimental", "ltx_lipsync_low",
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
    import run_recipe
    run_recipe.check_server_up_and_ownership()


def shutdown_server():
    import run_recipe

    result = run_recipe.shutdown_lab_server()
    if result.get("success") is not True:
        raise RuntimeError(
            "Verified lab-server shutdown failed; ownership receipt was retained: "
            f"{result.get('reason', 'unknown reason')}"
        )


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
