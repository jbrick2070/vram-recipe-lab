# Kibitz R1 Driver Anchor Review — vram-recipe-lab Suite Hardening

**Target System**: `vram-recipe-lab` (Standalone Repository)  
**Profile**: ComfyUI Custom-Node Profile  
**Driver**: Antigravity (Local UI Driver)  
**Date**: 2026-08-07  

---

## Executive Verdict

**VERDICT**: **READY FOR FAN-OUT & HARDENING** (16/16 recipes paper-validated with strict `SaveVideo` sinks and `17k+5` / `/32` grid compliance; harness life-cycle hardened with `.server.pid` and `.gpu.lock` cleanup across all exit paths).

---

## Code-Grounded Audit Findings

### 1. `recipes/*.json` (All 16 Canonical Recipes)
- [x] **CONFIRMED**: All 16 canonical recipes (`t2i_low`, `t2i_high`, `wan_ti2v_low`, `wan_ti2v_high`, `wan_i2v_14b_low`, `wan_i2v_14b_high`, `ltx_i2v_low`, `ltx_i2v_high`, `ltx_audio_low`, `ltx_lipsync_low`, `h3_t2v_low`, `h3_t2v_best`, `h3_i2v_low`, `h3_i2v_best`, `h3_r2v_low`, `h3_r2v_best`) exist in API prompt format without UI wrapper clutter.
- [x] **CONFIRMED**: All video recipes chain video generation (`MiniMaxH3*ToVideo` / `VAEDecode` / `CreateVideo`) directly into `SaveVideo` (`class_type`: `"SaveVideo"`, `inputs`: `{"video": ["<node_id>", 0], "filename_prefix": "..."}`).
- [x] **CONFIRMED**: All MiniMax H3 recipes specify **124 frames** (17×7 + 5 = 124, exact `17k+5` grid math) and **864×480** resolution (864/32 = 27, 480/32 = 15, exact `/32` grid math).
- [x] **CONFIRMED**: Still image recipes (`t2i_low`, `t2i_high`) terminate in `SaveImage`.

### 2. `run_recipe.py` (Harness & Gating Invariants)
- [x] **CONFIRMED**: Pass gate requires history execution status == `"success"` AND non-empty output artifacts on disk.
- [x] **CONFIRMED**: VRAM sampler runs in a dedicated thread at 200ms intervals; peak <= baseline + 0.2 GB triggers INVALID measurement failure (preventing sampler misses).
- [x] **CONFIRMED**: Lockfile (`.gpu.lock`) is acquired atomically via `O_CREAT | O_EXCL` and removed in `finally:`.
- [x] **CONFIRMED**: Server PID receipt (`.server.pid`) is unlinked on all exit paths (boot failure, execution exception, shutdown).
- [x] **CONFIRMED**: Warm cache consecutive pass rule enforces `is_prev_pass` check on second consecutive run <= 14.5 GB.

### 3. `validate_recipes.py` (Static Offline Validation)
- [x] **CONFIRMED**: Enforces mandatory checking for all 16 canonical recipes in `REQUIRED_RECIPES`; fails if any recipe file is missing or deleted.
- [x] **CONFIRMED**: Enforces strict UTF-8 encoding without BOM (`raw_bytes.startswith(b"\xef\xbb\xbf")`).
- [x] **CONFIRMED**: Validates graph reachability, node link indices, input dictionary structure, and mandatory `SaveVideo` sink node presence for all video recipes.

### 4. `boot_lab_server.cmd` & `PREFLIGHT.md`
- [x] **CONFIRMED**: Preflight Check #2 enforces **2.5 GB (2560 MB)** GPU idle ceiling and concurrent host system RAM tracking.
- [x] **CONFIRMED**: Preflight Check #3 verifies port 8199 ownership via `.server.pid` receipt before querying `/system_stats`.

---

## Must-Fix Items for Panel Evaluation

1. **Verify `UnetLoaderGGUF` vs Native Loaders**: Confirm input widget schema compatibility for GGUF and official UNET loaders across all recipe topologies.
2. **Verify Boot-Lane Flag Variant Staging**: Confirm that custom H3 launch flags (`--disable-pinned-memory --reserve-vram 2`) remain staged as boot-lane variants rather than hardcoded in `boot_lab_server.cmd`.
