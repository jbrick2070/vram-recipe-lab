# Results Ledger

Human-readable ledger table tracking the status of every recipe variant in the lab.

| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |
|---|---|---|---|---|---|
| `t2i_low` | **PASS** | 11.64 | 1.88 | 7.7 | Warm cache (Run #10); boot lane: lab-8199, sage-free |
| `t2i_high` | **PASS** | 13.12 | 1.89 | 6.7 | Warm cache (Run #4); boot lane: lab-8199, sage-free |
| `ltx_i2v_low` | **FAIL** | 10.84 | 1.75 | 7.5 | LTXAV embedding shape mismatch (Run #1) |
| `ltx_i2v_high` | **FAIL** | 10.51 | 1.31 | 6.1 | LTXAV embedding shape mismatch (Run #1) |
| `wan_ti2v_low` | **FAIL** | 15.28 | 1.66 | 19.7 | Peak VRAM 15.28 GB exceeded 14.5 GB gate line |
| `wan_ti2v_high` | **FAIL** | 15.34 | 1.19 | 30.0 | Peak VRAM 15.34 GB exceeded 14.5 GB gate line |
| `ltx_audio_low` | **FAIL** | 10.82 | 1.51 | 4.5 | LTXAV audio connector shape mismatch |
| `ltx_lipsync_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Missing HuMo/lip-sync custom nodes on server |
| `h3_t2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Dry prep complete; predicted peak 11.20 GB; weights missing (42.5 GB) |
| `h3_t2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Dry prep complete; predicted peak 13.20 GB (incl 1.0 GB LoRA margin); weights missing |
| `h3_i2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Dry prep complete; predicted peak 11.80 GB; weights missing (42.5 GB) |
| `h3_i2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Dry prep complete; predicted peak 13.40 GB (incl 1.0 GB LoRA margin); weights missing |
| `h3_r2v_low` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Dry prep complete; predicted peak 12.10 GB; weights missing (42.5 GB) |
| `h3_r2v_best` | **BLOCKED** | 0.00 | 0.00 | 0.0 | Dry prep complete; predicted peak 13.50 GB (incl 1.0 GB LoRA margin); weights missing |
