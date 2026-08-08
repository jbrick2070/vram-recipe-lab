# Engine Matrix (Beta)

This document tracks engine candidate evaluations in ram-recipe-lab.

| recipe | tier | status | peak VRAM (GB) | wall clock (s) | gated | pass consecutive | boot lane | last run | notes |
|---|---|---|---|---|---|---|---|---|---|
| t2i_low | smoke | PASS | 9.48 | 0.0 | yes | 2/2 | lab-8199, sage-free, clamp-8gb | 2026-08-08 | Warm cache (Run #13); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| t2i_high | smoke | PASS | 9.60 | 0.0 | yes | 2/2 | lab-8199, sage-free, clamp-8gb | 2026-08-08 | Warm cache (Run #7); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| wan_ti2v_low | smoke | PASS | 8.28 | 0.0 | yes | 2/2 | lab-8199, sage-free, clamp-8gb | 2026-08-08 | Warm cache (Run #9); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| wan_ti2v_high | smoke | PASS | 11.79 | 0.0 | yes | 2/2 | lab-8199, sage-free | 2026-08-08 | Warm cache (Run #6); boot lane: lab-8199, sage-free |
| wan_i2v_14b_low | smoke | FAIL (execution error) | 15.28 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Run #1; boot lane: lab-8199, sage-free |
| wan_i2v_14b_high | smoke | FAIL (execution error) | 15.34 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Run #1; boot lane: lab-8199, sage-free |
| ltx_t2v_low | smoke | FAIL (VRAM 15.38 GB > 14.5 GB) | 15.38 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #3; boot lane: lab-8199, sage-free |
| ltx_t2v_high | smoke | PASS | 14.45 | 0.0 | yes | 2/2 | lab-8199, sage-free | 2026-08-08 | Warm cache (Run #5); boot lane: lab-8199, sage-free |
| ltx_i2v_low | smoke | FAIL (VRAM 15.41 GB > 14.5 GB) | 15.41 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #16; boot lane: lab-8199, sage-free |
| ltx_i2v_high | smoke | PASS | 14.50 | 0.0 | yes | 2/2 | lab-8199, sage-free | 2026-08-08 | Warm cache (Run #5); boot lane: lab-8199, sage-free |
| ltx_audio_low | smoke | FAIL (VRAM 15.45 GB > 14.5 GB) | 15.45 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #5; boot lane: lab-8199, sage-free |
| ltx_audio_high | smoke | FAIL (VRAM 14.52 GB > 14.5 GB) | 14.52 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #5; boot lane: lab-8199, sage-free |
| ltx_lipsync_low | smoke | UNMEASURED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #0; boot lane: lab-8199, sage-free |
| h3_t2v_low | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | Missing weight/recipe data |
| h3_i2v_low | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | Missing weight/recipe data |
| h3_r2v_low | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | Missing weight/recipe data |
