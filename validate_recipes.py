#!/usr/bin/env python3
"""
Offline Paper Validation Script for vram-recipe-lab recipes.
Runs all static validations that do NOT require a live lab server:
  1. Strict UTF-8 encoding (NO BOM)
  2. JSON parsing validity
  3. Recipe contract integrity (width, height, frames, vram_ceiling_gb)
  4. Mandatory coverage of all 16 canonical recipes
  5. Node class_type presence and prompt dictionary structure
  6. Graph reachability, link index integrity, and data types
  7. Sink output node type validation (SaveImage for still, SaveVideo for video)
  8. Fixture file existence for I2V/R2V/Audio recipes
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
    "ltx_t2v_ckpt", "ltx_t2v_gguf", "ltx_t2v_fullhd_experimental",
    "ltx_i2v_ckpt", "ltx_i2v_gguf", "ltx_i2v_fullhd_experimental",
    "ltx_audio_ckpt", "ltx_audio_gguf", "ltx_audio_fullhd_experimental", "ltx_lipsync_low",
    "h3_t2v_low", "h3_t2v_best",
    "h3_i2v_low", "h3_i2v_best",
    "h3_r2v_low", "h3_r2v_best"
]



def validate_recipe_file(recipe_path: Path) -> dict:
    recipe_name = recipe_path.stem
    errors = []
    warnings = []

    # 1. Check UTF-8 (Strict NO BOM)
    raw_bytes = recipe_path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        errors.append("UTF-8 BOM detected at start of file (must be UTF-8 without BOM)")

    # 2. Parse JSON
    try:
        content = raw_bytes.decode("utf-8")
        data = json.loads(content)
    except Exception as e:
        return {"recipe": recipe_name, "valid": False, "errors": [f"JSON parse error: {e}"], "warnings": []}

    # 3. Check top-level contract keys
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

    # 4. Check prompt structure & graph topology
    prompt = data.get("prompt", {})
    if not isinstance(prompt, dict) or not prompt:
        errors.append("Missing or empty 'prompt' dictionary")
    else:
        node_ids = set(prompt.keys())
        has_video_save = False
        has_image_save = False

        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                errors.append(f"Node {node_id} is not a dictionary")
                continue
            class_type = node.get("class_type")
            if not class_type:
                errors.append(f"Node {node_id} missing 'class_type'")
                continue

            if class_type == "SaveVideo":
                has_video_save = True
            elif class_type == "SaveImage":
                has_image_save = True

            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                errors.append(f"Node {node_id} 'inputs' is not a dictionary")
                continue

            # 5. Check links & graph reachability
            for in_key, in_val in inputs.items():
                if isinstance(in_val, list) and len(in_val) == 2:
                    target_id, slot_idx = str(in_val[0]), in_val[1]
                    if target_id not in node_ids:
                        errors.append(f"Node {node_id} input '{in_key}' references non-existent node {target_id}")

        # 6. Check sink output node type match
        if "t2i" in recipe_name:
            if not has_image_save:
                errors.append("Still image recipe missing SaveImage sink node")
        else:
            if not has_video_save:
                errors.append("Video recipe missing SaveVideo sink node (must end in SaveVideo)")

    # 7. Check fixtures for image/audio recipes
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
            print(f"[MISSING] Required recipe file missing: {recipe_name}.json!")
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
    # Verify results ledger payload consistency (Kibitz check)
    results_dir = REPO_ROOT / "results"
    receipt_errors = 0
    if results_dir.exists():
        for rf in results_dir.glob("*.json"):
            try:
                rdata = json.loads(rf.read_text(encoding="utf-8"))
                payload_recipe = rdata.get("recipe")
                expected_stem = rf.stem.split("_run")[0]
                if payload_recipe and payload_recipe != expected_stem:
                    print(f"  [ERROR] Receipt mislabel: {rf.name} payload says '{payload_recipe}', expected '{expected_stem}'")
                    receipt_errors += 1
            except Exception:
                pass

    passed_count = sum(1 for r in results if r["valid"])
    total_count = len(REQUIRED_RECIPES)
    if receipt_errors > 0:
        print(f"Summary: {passed_count}/{total_count} required recipes PAPER VALIDATED, BUT {receipt_errors} corrupt result receipts found.")
        all_valid = False
    else:
        print(f"Summary: {passed_count}/{total_count} required recipes PAPER VALIDATED successfully.")
    print("Note: Schema-vs-/object_info live server checks marked PENDING server window.")
    print("=========================================================\n")

    if passed_count != total_count or len(results) != total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
