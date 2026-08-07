# Recipe Execution Results

This file records measured VRAM and runtime performance for every recipe variant.
**Hard Gate Ceiling**: **14.5 GB** (14,848 MiB) physical VRAM peak limit on NVIDIA GeForce RTX 5080 Laptop GPU.

| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |
|---|---|---|---|---|---|
| `t2i_low` | **PASS** | 11.64 | 1.88 | 7.7 | Warm cache (Run #10); boot lane: lab-8199, sage-free |
| `t2i_high` | **PASS** | 13.12 | 1.89 | 6.7 | Warm cache (Run #4); boot lane: lab-8199, sage-free |
| `wan_ti2v_low` | **PASS** | 13.15 | 1.80 | 14.6 | Wan 2.2 5B Q5_K_M GGUF (`UnetLoaderGGUF`); warm cache (Run #2) |
| `wan_ti2v_high` | **FAIL** | 15.55 | 2.06 | 46.3 | Wan 2.2 5B Q5_K_M GGUF; peak VRAM 15.55 GB > 14.5 GB gate line |
| `wan_i2v_14b_low` | **FAIL** | 15.28 | 1.66 | 19.7 | Wan 2.2 14B FP8; peak VRAM 15.28 GB > 14.5 GB gate line |
| `wan_i2v_14b_high` | **FAIL** | 15.34 | 1.19 | 30.0 | Wan 2.2 14B FP8; peak VRAM 15.34 GB > 14.5 GB gate line |
| `ltx_i2v_low` | **ERROR** | 10.84 | 1.75 | 7.5 | Wiring/graph fault: LTXAV embedding shape mismatch |
| `ltx_i2v_high` | **ERROR** | 10.51 | 1.31 | 6.1 | Wiring/graph fault: LTXAV embedding shape mismatch |
| `ltx_audio_low` | **ERROR** | 10.82 | 1.51 | 4.5 | Wiring/graph fault: LTXAV audio connector shape mismatch |
| `ltx_lipsync_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing HuMo/lip-sync custom nodes on server |
| `h3_t2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | 864x480 x 124f; weights missing (42.5 GB); EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_t2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | 864x480 x 124f; weights missing (42.5 GB); EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | 864x480 x 124f; weights missing (42.5 GB); EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | 864x480 x 124f; weights missing (42.5 GB); EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | 864x480 x 124f; weights missing (42.5 GB); EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | 864x480 x 124f; weights missing (42.5 GB); EXTERNAL-REPORTED peak 7.4-7.6 GB |
