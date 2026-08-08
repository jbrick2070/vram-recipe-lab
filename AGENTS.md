# AGENTS.md — Repository Hard Rules & Operating Guidelines

This file defines the strict operating constraints for agents working in `vram-recipe-lab`. Every agent must re-read these rules at the start of every session.

## Hard Rules

1. **VRAM Ceiling**: The VRAM pass line is **14.5 GB**. The 16 GB physical VRAM on the RTX 5080 Laptop (Blackwell sm_120) is the absolute hardware ceiling, not the target limit.
2. **Platform & Torch Invariants**:
   - OS: Windows 11, Python 3.12/3.10, PyTorch 2.10.0, CUDA 13.0, SageAttention + SDPA.
   - **FlashAttention-2 does NOT exist for this platform** (no wheel for torch 2.10 + CUDA 13 + sm_120). Never install it, suggest it, or attempt to build/debug toward it.
3. **100% Offline & Local**: No cloud APIs, no remote endpoints, no API keys, no paid services.
4. **Lab Server Management (Port 8199)**:
   - The lab boots its OWN headless ComfyUI server on **`127.0.0.1:8199`** via `boot_lab_server.cmd`.
   - Never query or touch Jeffrey's interactive instance (port 8188) or OTR's headless servers.
   - If port 8199 is answering BUT no local PID receipt (`.server.pid`) exists, abort preflight immediately (`Unrecognized server on 8199 without PID receipt`). Do NOT adopt it or kill it.
   - When booted, track the PID in `.server.pid`. Always shut down recorded lab server processes upon completing session runs.
5. **Zero Weight Downloads**: Do NOT download any model. Query the running lab server instance (`http://127.0.0.1:8199`) for available models and write `models_manifest.md`. Recipes may only reference models present in `models_manifest.md`. Missing models must be marked `BLOCKED` in `RESULTS.md`.
6. **UTF-8 Encoding (No BOM)**: All text, code, and JSON files must be UTF-8 encoded without BOM. Never write Python or JSON via PowerShell `Set-Content` or `Out-File`.
7. **Sequential Execution & Lockfile**: Render execution must be strictly sequential (one render at a time). `run_recipe.py` must acquire `.gpu.lock` atomically and refuse to queue if a lock exists.
8. **Workflow JSON Integrity**: After editing any workflow JSON:
   - Validate JSON parsing.
   - Verify every node's input widget count matches its `widgets_values` array length.
   - Verify all node `class_type`s exist on the server via `GET /object_info`.
9. **Warm Cache Gating**: A recipe is only considered `PASS` when `results/<recipe_name>.json` records a passing **second consecutive run** (warm cache) with peak VRAM <= 14.5 GB.
10. **MiniMax H3 Safeguards**:
    - All H3 renders require a **SageAttention-free** ComfyUI boot lane (`lab-8199, sage-free`) to prevent silent corruption into noise.
    - All H3 runs are marked `BLOCKED` until weights exist on disk.
11. **Living Beta Matrix & Results**:
    - Update `ENGINE_MATRIX_BETA.md` and `RESULTS.md` after every gated run.
    - Never touch the OTR repo or edit the snapshot in `research/`.
12. **Clamp Lane & Reserve VRAM**:
    - Setting `LAB_RESERVE_VRAM_GB` (or passing `--clamp <N>`) instructs `boot_lab_server.cmd` to append `--reserve-vram %LAB_RESERVE_VRAM_GB%`.
    - Boot lane string is recorded as `lab-8199, sage-free, clamp-<N>gb`.
    - **Clamp Pass Line**: A `clamp-<N>gb` run passes when `(peak_vram_gb - baseline_vram_gb) <= N GB`, since desktop baseline VRAM is not part of the recipe's allocated footprint.
    - Clamp lane runs validate that low-VRAM profiles stay within tight physical hardware limits (e.g. 8 GB VRAM targets) by using PyTorch reserve-vram allocation limits.

