# Engine Matrix (Beta)

This document tracks engine candidate evaluations in `vram-recipe-lab`.

| recipe | tier | status | peak VRAM (GB) | wall clock (s) | gated | pass consecutive | boot lane | last run | notes |
|---|---|---|---|---|---|---|---|---|---|
| `t2i_low` | smoke | PASS | 11.64 | 7.7 | yes | 2/2 | lab-8199, sage-free | 2026-08-07 | Warm cache (Run #10) |
| `t2i_high` | smoke | PASS | 13.12 | 6.7 | yes | 2/2 | lab-8199, sage-free | 2026-08-07 | Warm cache (Run #4) |
| `wan_ti2v_low` | smoke | PASS | 13.15 | 14.6 | yes | 2/2 | lab-8199, sage-free | 2026-08-07 | Wan 2.2 5B Q5_K_M GGUF (`UnetLoaderGGUF`) |
| `wan_ti2v_high` | smoke | FAIL | 15.55 | 46.3 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Peak VRAM 15.55 GB > 14.5 GB gate line |
| `wan_i2v_14b_low` | smoke | FAIL | 15.28 | 19.7 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Wan 2.2 14B FP8; peak > 14.5 GB |
| `wan_i2v_14b_high` | smoke | FAIL | 15.34 | 30.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Wan 2.2 14B FP8; peak > 14.5 GB |
| `ltx_i2v_low` | smoke | ERROR | 10.84 | 7.5 | no | 0/2 | lab-8199, sage-free | 2026-08-07 | Wiring fault: LTXAV embedding shape mismatch |
| `ltx_i2v_high` | smoke | ERROR | 10.51 | 6.1 | no | 0/2 | lab-8199, sage-free | 2026-08-07 | Wiring fault: LTXAV embedding shape mismatch |
| `ltx_audio_low` | smoke | ERROR | 10.82 | 4.5 | no | 0/2 | lab-8199, sage-free | 2026-08-07 | Wiring fault: LTXAV audio connector shape mismatch |
| `ltx_lipsync_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | Missing HuMo/lip-sync custom nodes |
| `h3_t2v_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_t2v_best` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_best` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_low` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_best` | smoke | BLOCKED | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | N/A | 864x480 x 124f; weights missing; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| t2i_low | smoke | PASS | 12.32 | N/A | no | 7.3s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| t2i_high | smoke | PASS | 13.15 | N/A | no | 6.3s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| wan_ti2v_low | smoke | PASS (cold) | 12.38 | N/A | no | 12.7s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS (cold)) |
