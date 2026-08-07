# AGENTS.md — Repository Hard Rules & Operating Guidelines

This file defines the strict operating constraints for agents working in `vram-recipe-lab`. Every agent must re-read these rules at the start of every session.

## Hard Rules

1. **VRAM Ceiling**: The VRAM pass line is **14.5 GB**. The 16 GB physical VRAM on the RTX 5080 Laptop (Blackwell sm_120) is the absolute hardware ceiling, not the target limit.
2. **Platform & Torch Invariants**:
   - OS: Windows 11, Python 3.12/3.10, PyTorch 2.10.0, CUDA 13.0, SageAttention + SDPA.
   - **FlashAttention-2 does NOT exist for this platform** (no wheel for torch 2.10 + CUDA 13 + sm_120). Never install it, suggest it, or attempt to build/debug toward it.
3. **100% Offline & Local**: No cloud APIs, no remote endpoints, no API keys, no paid services.
4. **Zero Weight Downloads**: Do NOT download any model. Query the running ComfyUI instance (`http://127.0.0.1:8188`) for available models and write `models_manifest.md`. Recipes may only reference models present in `models_manifest.md`. Missing models must be marked `BLOCKED` in `RESULTS.md`.
5. **UTF-8 Encoding (No BOM)**: All text, code, and JSON files must be UTF-8 encoded without BOM. Never write Python or JSON via PowerShell `Set-Content` or `Out-File`.
6. **Sequential Execution & Lockfile**: Render execution must be strictly sequential (one render at a time). `run_recipe.py` must acquire `.gpu.lock` atomically and refuse to queue if a lock exists.
7. **Workflow JSON Integrity**: After editing any workflow JSON:
   - Validate JSON parsing.
   - Verify every node's input widget count matches its `widgets_values` array length.
   - Verify all node `class_type`s exist on the server via `GET /object_info`.
8. **Warm Cache Gating**: A recipe is only considered `PASS` when `results/<recipe_name>.json` records a passing **second consecutive run** (warm cache) with peak VRAM <= 14.5 GB. Never declare a recipe done based solely on JSON structure or a single cold run.
9. **MiniMax H3 Safeguards**:
   - All H3 renders require a **SageAttention-free** ComfyUI boot lane (`--use-sage-attention` disabled) to prevent silent corruption into noise.
   - All H3 runs are marked `BLOCKED` until weights exist on disk.
10. **Living Beta Matrix & Results**:
    - Update `ENGINE_MATRIX_BETA.md` and `RESULTS.md` after every gated run.
    - Never touch the OTR repo or edit the snapshot in `research/`.
