# Recipe Execution Results

This file records measured VRAM and runtime performance for every recipe variant.
**Hard Gate Ceiling**: **14.5 GB** (14,848 MiB) physical VRAM peak limit on NVIDIA GeForce RTX 5080 Laptop GPU.
**Clamp Pass Line**: For clamp-<N>gb boot lanes, a run passes when (peak_vram_gb - baseline_vram_gb) <= N GB.

| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |
|---|---|---|---|---|---|
| t2i_low | **PASS** | 9.48 | 1.49 | 0.0 | Warm cache (Run #13); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| t2i_high | **PASS** | 9.60 | 1.49 | 0.0 | Warm cache (Run #7); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| wan_ti2v_low | **PASS** | 8.28 | 1.49 | 0.0 | Warm cache (Run #9); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| wan_ti2v_high | **PASS** | 11.79 | 1.16 | 0.0 | Warm cache (Run #6); boot lane: lab-8199, sage-free |
| wan_i2v_14b_low | **FAIL (execution error)** | 15.28 | 1.66 | 0.0 | Run #1; boot lane: lab-8199, sage-free |
| wan_i2v_14b_high | **FAIL (execution error)** | 15.34 | 1.19 | 0.0 | Run #1; boot lane: lab-8199, sage-free |
| ltx_t2v_low | **FAIL (VRAM 15.38 GB > 14.5 GB)** | 15.38 | 1.12 | 0.0 | Run #3; boot lane: lab-8199, sage-free |
| ltx_t2v_high | **PASS** | 14.45 | 1.73 | 0.0 | Warm cache (Run #5); boot lane: lab-8199, sage-free |
| ltx_i2v_low | **FAIL (VRAM 15.41 GB > 14.5 GB)** | 15.41 | 1.34 | 0.0 | Run #16; boot lane: lab-8199, sage-free |
| ltx_i2v_high | **PASS** | 14.50 | 1.60 | 0.0 | Warm cache (Run #5); boot lane: lab-8199, sage-free |
| ltx_audio_low | **FAIL (VRAM 15.45 GB > 14.5 GB)** | 15.45 | 1.65 | 0.0 | Run #5; boot lane: lab-8199, sage-free |
| ltx_audio_high | **FAIL (VRAM 14.52 GB > 14.5 GB)** | 14.52 | 1.35 | 0.0 | Run #5; boot lane: lab-8199, sage-free |
| ltx_lipsync_low | **UNMEASURED** | 0.00 | 0.00 | 0.0 | Run #0; boot lane: lab-8199, sage-free |
| h3_t2v_low | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing weight/recipe data |
| h3_i2v_low | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing weight/recipe data |
| h3_r2v_low | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing weight/recipe data |
