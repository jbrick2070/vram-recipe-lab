# Recipe Execution Results

This file records measured VRAM and runtime performance for every recipe variant.
**Hard Gate Ceiling**: **14.5 GB** (14,848 MiB) physical VRAM peak limit on NVIDIA GeForce RTX 5080 Laptop GPU.

| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |
|---|---|---|---|---|---|
| `t2i_low` | **PASS** | 12.32 | 1.90 | 7.3 | Warm cache (Run #11); boot lane: lab-8199, sage-free |
| `t2i_high` | **PASS** | 13.15 | 1.90 | 6.3 | Warm cache (Run #5); boot lane: lab-8199, sage-free |
| `wan_ti2v_low` | **PASS** | 12.46 | 1.47 | 13.8 | Warm cache (Run #7); boot lane: lab-8199, sage-free |
| `wan_ti2v_high` | **FAIL** | 15.55 | 2.06 | 46.3 | Wan 2.2 5B Q5_K_M GGUF; peak VRAM 15.55 GB > 14.5 GB gate line |
| `wan_i2v_14b_low` | **FAIL** | 15.28 | 1.66 | 19.7 | Wan 2.2 14B FP8; peak VRAM 15.28 GB > 14.5 GB gate line |
| `wan_i2v_14b_high` | **FAIL** | 15.34 | 1.19 | 30.0 | Wan 2.2 14B FP8; peak VRAM 15.34 GB > 14.5 GB gate line |
| `ltx_i2v_low` | **ERROR** | 1.05 | 1.05 | 1.4 | Execution error; graph unmeasured |
| `ltx_i2v_high` | **ERROR** | 10.51 | 1.31 | 6.1 | Execution error; graph unmeasured |
| `ltx_audio_low` | **ERROR** | 10.82 | 1.51 | 4.5 | Execution error; graph unmeasured |
| `ltx_lipsync_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing HuMo/lip-sync custom nodes on server |
| `h3_t2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Weights missing on disk; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_t2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Weights missing on disk; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Weights missing on disk; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_i2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Weights missing on disk; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Weights missing on disk; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| `h3_r2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Weights missing on disk; EXTERNAL-REPORTED peak 7.4-7.6 GB |
| wan_ti2v_high | FAIL | 0.00 | 0.00 | 0.0 | Aborted on Preflight #7 (Affordability estimate): Last measured peak (15.55 GB) exceeded 14.5 GB gate line. Refusing unchanged re-run. |
| ltx_audio_high | FAIL | 0.00 | 0.00 | 0.0 | Aborted on Preflight #4 (Nodes exist): Missing server node class types: ['98ee9e5b-467b-40aa-a534-36033f27d0b4'] |
