# AGENTS.md — Repository Hard Rules & Operating Guidelines

This file defines the strict operating constraints for agents working in `vram-recipe-lab`. Every agent must re-read these rules at the start of every session.

## Hard Rules

### Isolated RTX 4060 Bench

When work mentions the physical RTX 4060 laptop, read
`.claude/skills/rtx-4060-lab/SKILL.md` before acting. Its user-authorized SSH
bridge is a local control-plane exception only; its runtime state is isolated
under `eightgb_bench/local/`, uses its own loopback port, and must never touch
the 5080 runner, port 8199, locks, outputs, or receipts.

1. **VRAM Ceiling**: The VRAM pass line is **14.5 GB**. The 16 GB physical VRAM on the RTX 5080 Laptop (Blackwell sm_120) is the absolute hardware ceiling, not the target limit.
2. **Platform & Torch Invariants**:
   - OS: Windows 11, Python 3.12/3.10, PyTorch 2.10.0, CUDA 13.0, SageAttention + SDPA.
   - **FlashAttention-2 does NOT exist for this platform** (no wheel for torch 2.10 + CUDA 13 + sm_120). Never install it, suggest it, or attempt to build/debug toward it.
3. **100% Offline & Local**: No cloud APIs, no remote endpoints, no API keys, no paid services.
4. **Lab Server Management (Port 8199)**:
   - The lab boots its OWN headless ComfyUI server on **`127.0.0.1:8199`** via `boot_lab_server.cmd`.
   - Never query or touch Jeffrey's interactive instance (port 8188) or OTR's headless servers.
   - If port 8199 is answering BUT no local PID receipt (`.server.pid`) exists, abort preflight immediately (`Unrecognized server on 8199 without PID receipt`). Do NOT adopt it or kill it.
   - When booted, track the verified serving PID in `.server.pid`. Always shut down recorded lab server processes upon completing session runs, and remove the receipt only after their exit is confirmed.
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
    - `--clamp <N>` means a target-card budget of N GiB. `run_recipe.py` queries physical VRAM T and passes `--reserve-vram max(0, T-N)` to ComfyUI.
    - The lane records both meanings: `clamp-<N>gb (reserve-<T-N>gb)`. The live server argv must match the computed reserve.
    - Direct `LAB_RESERVE_VRAM_GB=<X>` means ComfyUI reserve/offload pressure X GiB and is labeled `reserve-<X>gb`; it is not a simulated X GiB card.
    - **Clamp Pass Line**: a target-card run must satisfy both the global 14.5 GB peak ceiling and `(peak_vram_gb - baseline_vram_gb) <= N GB`.
    - Reserve-vram induces memory/offload pressure but is not perfect hardware emulation. Historical `clamp-Ngb` receipts before the 2026-08-08 semantics fix used N as the reserve amount and are legacy-labelled evidence only.
13. **Marginal-Pass Rule**: A pass within 0.25 GB of the ceiling (i.e. peak VRAM between 14.25 GB and 14.50 GB on a 14.50 GB gate) is recorded `PASS (marginal)` and is not promotable to production use without a lower-footprint variant.
