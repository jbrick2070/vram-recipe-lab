# Engine Matrix (Beta)

This document tracks engine candidate evaluations in `vram-recipe-lab`.

| recipe | tier | status | peak VRAM (GB) | wall clock (s) | gated | pass consecutive | boot lane | last run | notes |
|---|---|---|---|---|---|---|---|---|---|
| `t2i_low` | smoke | PASS | 12.32 | 7.3 | yes | 2/2 | lab-8199, sage-free | 2026-08-07 | Warm cache (Run #11) |
| `t2i_high` | smoke | PASS | 13.15 | 6.3 | yes | 2/2 | lab-8199, sage-free | 2026-08-07 | Warm cache (Run #5) |
| `wan_ti2v_low` | smoke | PASS | 12.46 | 13.8 | yes | 2/2 | lab-8199, sage-free | 2026-08-07 | Warm cache (Run #7) |
| `wan_ti2v_high` | smoke | FAIL | 15.55 | 46.3 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Wan 2.2 5B Q5_K_M GGUF; peak VRAM > 14.5 GB |
| `wan_i2v_14b_low` | smoke | FAIL | 15.28 | 19.7 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Wan 2.2 14B FP8; peak > 14.5 GB |
| `wan_i2v_14b_high` | smoke | FAIL | 15.34 | 30.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Wan 2.2 14B FP8; peak > 14.5 GB |
| `ltx_i2v_low` | smoke | ERROR | 1.05 | 1.4 | no | 0/2 | lab-8199, sage-free | 2026-08-07 | Execution error; unmeasured |
| `ltx_i2v_high` | smoke | ERROR | 10.51 | 6.1 | no | 0/2 | lab-8199, sage-free | 2026-08-07 | Execution error; unmeasured |
| `ltx_audio_low` | smoke | ERROR | 10.82 | 4.5 | no | 0/2 | lab-8199, sage-free | 2026-08-07 | Execution error; unmeasured |
| `ltx_lipsync_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | Missing HuMo/lip-sync custom nodes |
| `h3_t2v_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_t2v_best` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_best` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_best` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| ltx_audio_high | smoke | PASS | 11.08 | N/A | no | 39.8s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| ltx_audio_low | smoke | PASS | 11.07 | N/A | no | 38.3s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| ltx_i2v_low | smoke | PASS | 11.97 | N/A | no | 16.6s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| ltx_i2v_high | smoke | PASS | 11.97 | N/A | no | 16.3s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| ltx_t2v_low | smoke | PASS | 11.13 | N/A | no | 27.7s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| ltx_t2v_high | smoke | PASS | 11.10 | N/A | no | 27.8s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| wan_ti2v_high | smoke | PASS | 12.47 | N/A | no | 11.0s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| t2i_low | smoke | PASS | 9.48 | N/A | no | 4.6s | lab-8199, sage-free, clamp-8gb | 2026-08-07 | Measured on box (PASS) |
| t2i_high | smoke | PASS | 9.60 | N/A | no | 5.7s | lab-8199, sage-free, clamp-8gb | 2026-08-07 | Measured on box (PASS) |
| wan_ti2v_low | smoke | PASS | 8.28 | N/A | no | 11.4s | lab-8199, sage-free, clamp-8gb | 2026-08-07 | Measured on box (PASS) |
