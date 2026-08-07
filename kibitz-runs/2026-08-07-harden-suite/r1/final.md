# Kibitz R1 Hardened Suite Plan & Synthesis — vram-recipe-lab

**Target**: `vram-recipe-lab` Recipe Suite & Execution Harness  
**Driver**: Antigravity  
**Status**: All verified fixes applied and paper-validated  

---

## Hardened Harness & Recipe Standards

### 1. Warm-Cache Consecutive Pass Rule (`run_recipe.py`)
- **Strict Requirement**: A recipe is marked `PASS` **ONLY** when `is_warm_cache = (run_count >= 2) and prev_passed` is satisfied.
- If run #1 failed or errored, run #2 is classified as a cold run (`PASS (cold)`) and does not stamp final `PASS`.

### 2. Disk Artifact Verification (`run_recipe.py`)
- History execution success (`status_str == "success"`) must be accompanied by actual output file existence on disk (`outputs/<filename>`) with **size > 0 bytes**.
- Missing or zero-byte files force `execution_success = False` and set status to `ERROR (missing output file)`.

### 3. Video Sink Chain Invariant (`recipes/*.json`)
- All 14 video recipes (`h3_*`, `wan_*`, `ltx_*`) chain video sampling and VAE decode into `CreateVideo` -> `SaveVideo` (`class_type`: `"SaveVideo"`, `inputs`: `{"video": ["<node_id>", 0], "filename_prefix": "..."}`).

### 4. Mandatory Recipe Suite Coverage (`validate_recipes.py`)
- Static offline paper validator requires the exact mandatory set of 16 canonical recipes (`t2i_low`, `t2i_high`, `wan_ti2v_low`, `wan_ti2v_high`, `wan_i2v_14b_low`, `wan_i2v_14b_high`, `ltx_i2v_low`, `ltx_i2v_high`, `ltx_audio_low`, `ltx_lipsync_low`, `h3_t2v_low`, `h3_t2v_best`, `h3_i2v_low`, `h3_i2v_best`, `h3_r2v_low`, `h3_r2v_best`).
- Deleting any recipe file causes paper validation failure.
- Enforces strict UTF-8 without BOM (`raw_bytes.startswith(b"\xef\xbb\xbf")`).

### 5. Server PID & GPU Lock Lifecycle
- Atomic GPU lock (`.gpu.lock`) and server PID receipt (`.server.pid`) cleanup are guaranteed on all exit paths, exceptions, and boot errors.
