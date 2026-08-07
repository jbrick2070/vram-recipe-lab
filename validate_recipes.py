#!/usr/bin/env python3
"""
Offline Paper Validation Script for vram-recipe-lab recipes.
Runs all static validations that do NOT require a live lab server:
  1. JSON parsing validity & UTF-8 encoding
  2. Recipe contract integrity (width, height, frames, duration)
  3. Node class_type presence and prompt dictionary structure
  4. Link index integrity and reference connections
  5. Fixture file existence for I2V/R2V/Audio recipes
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"
FIXTURES_DIR = REPO_ROOT / "fixtures"

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


def validate_recipe_file(recipe_path: Path) -> dict:
    recipe_name = recipe_path.stem
    errors = []
    warnings = []

    # 1. Parse JSON
    try:
        content = recipe_path.read_text(encoding="utf-8-sig")
        data = json.loads(content)
    except Exception as e:
        return {"recipe": recipe_name, "valid": False, "errors": [f"JSON parse error: {e}"], "warnings": []}

    # 2. Check top-level keys
    if "name" not in data or data["name"] != recipe_name:
        errors.append(f"Name mismatch: expected '{recipe_name}', got '{data.get('name')}'")
    if "contract" not in data or not isinstance(data["contract"], dict):
        errors.append("Missing or invalid 'contract' dictionary")
    else:
        contract = data["contract"]
        for field in ["width", "height", "vram_ceiling_gb"]:
            if field not in contract:
                errors.append(f"Missing contract field: {field}")
        if "t2i" not in recipe_name and "frames" not in contract:
            errors.append("Missing contract field: frames")

    # 3. Check prompt structure
    prompt = data.get("prompt", {})
    if not isinstance(prompt, dict) or not prompt:
        errors.append("Missing or empty 'prompt' dictionary")
    else:
        node_ids = set(prompt.keys())
        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                errors.append(f"Node {node_id} is not a dictionary")
                continue
            if "class_type" not in node:
                errors.append(f"Node {node_id} missing 'class_type'")
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                errors.append(f"Node {node_id} 'inputs' is not a dictionary")
                continue

            # 4. Check links
            for in_key, in_val in inputs.items():
                if isinstance(in_val, list) and len(in_val) == 2:
                    target_id, slot_idx = str(in_val[0]), in_val[1]
                    if target_id not in node_ids:
                        errors.append(f"Node {node_id} input '{in_key}' references non-existent node {target_id}")

    # 5. Check fixtures for image/audio recipes
    if "i2v" in recipe_name or "r2v" in recipe_name:
        fixture_name = "portrait.png" if "r2v" in recipe_name else "scene_still.png"
        p = FIXTURES_DIR / fixture_name
        if not p.exists():
            warnings.append(f"Fixture file missing: {fixture_name}")

    if "audio" in recipe_name:
        p = FIXTURES_DIR / "narration.wav"
        if not p.exists():
            warnings.append(f"Fixture file missing: narration.wav")

    return {
        "recipe": recipe_name,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(prompt) if isinstance(prompt, dict) else 0,
        "blocked": data.get("blocked", False)
    }


def main():
    print("=========================================================")
    print("       vram-recipe-lab :: PAPER VALIDATION SUITE        ")
    print("=========================================================\n")

    results = []
    all_valid = True

    for recipe_name in REQUIRED_RECIPES:
        recipe_path = RECIPES_DIR / f"{recipe_name}.json"
        if not recipe_path.exists():
            print(f"[MISSING] {recipe_name}.json file not found!")
            all_valid = False
            continue

        res = validate_recipe_file(recipe_path)
        results.append(res)

        status_str = "PASS" if res["valid"] else "FAIL"
        blocked_str = "[BLOCKED]" if res["blocked"] else "[ACTIVE]"
        print(f"  {status_str:4s} | {blocked_str:9s} | {recipe_name:20s} ({res['node_count']} nodes)")
        for err in res["errors"]:
            print(f"         +-- ERROR: {err}")
        for warn in res["warnings"]:
            print(f"         +-- WARN:  {warn}")

    print("\n---------------------------------------------------------")
    passed_count = sum(1 for r in results if r["valid"])
    total_count = len(REQUIRED_RECIPES)
    print(f"Summary: {passed_count}/{total_count} recipes PAPER VALIDATED successfully.")
    print("Note: Schema-vs-/object_info live server checks marked PENDING server window.")
    print("=========================================================\n")

    if passed_count != total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
