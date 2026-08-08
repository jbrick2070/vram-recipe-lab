# Recipe Execution Results

This file records measured VRAM and runtime performance for every recipe variant.
**Hard Gate Ceiling**: **14.5 GB** (14,848 MiB) physical VRAM peak limit on NVIDIA GeForce RTX 5080 Laptop GPU.

| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |
|---|---|---|---|---|---|
| t2i_low | **PASS** | 9.48 | 1.49 | 4.6 | Warm cache (Run #13); boot lane: lab-8199, sage-free, clamp-8gb |
| t2i_high | **PASS** | 9.60 | 1.49 | 5.7 | Warm cache (Run #7); boot lane: lab-8199, sage-free, clamp-8gb |
| wan_ti2v_low | **PASS** | 8.28 | 1.49 | 11.4 | Warm cache (Run #9); boot lane: lab-8199, sage-free, clamp-8gb |
| wan_ti2v_high | **PASS** | 12.47 | 1.49 | 11.0 | Warm cache (Run #4); boot lane: lab-8199, sage-free |
| wan_i2v_14b_low | **FAIL** | 15.28 | 1.66 | 19.7 | Warm cache (Run #1); boot lane: lab-8199, sage-free |
| wan_i2v_14b_high | **FAIL** | 15.34 | 1.19 | 30.0 | Warm cache (Run #1); boot lane: lab-8199, sage-free |
| ltx_t2v_low | **PASS** | 11.13 | 1.49 | 27.7 | Warm cache (Run #2); boot lane: lab-8199, sage-free |
| ltx_t2v_high | **PASS** | 11.10 | 1.49 | 27.8 | Warm cache (Run #2); boot lane: lab-8199, sage-free |
| ltx_i2v_low | **PASS** | 11.97 | 1.49 | 16.6 | Warm cache (Run #15); boot lane: lab-8199, sage-free |
| ltx_i2v_high | **PASS** | 11.97 | 1.49 | 16.3 | Warm cache (Run #3); boot lane: lab-8199, sage-free |
| ltx_audio_low | **PASS** | 11.07 | 1.49 | 38.3 | Warm cache (Run #3); boot lane: lab-8199, sage-free |
| ltx_audio_high | **PASS** | 11.08 | 1.50 | 39.8 | Warm cache (Run #3); boot lane: lab-8199, sage-free |
| ltx_lipsync_low | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing lip-sync nodes on server |
