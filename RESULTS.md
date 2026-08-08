# Recipe Execution Results

This file records measured VRAM and runtime performance for every recipe variant.
**Hard Gate Ceiling**: **14.5 GB** (14,848 MiB) physical VRAM peak limit on NVIDIA GeForce RTX 5080 Laptop GPU.
**Clamp Pass Line**: `--clamp N` targets an N GiB card by reserving `physical_total - N` GiB, records both values in the lane, and passes only when both the 14.5 GB absolute peak gate and `(peak_vram_gb - baseline_vram_gb) <= N` hold. Historical short `clamp-Ngb` labels used N as the reserve amount and are legacy evidence.

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
| h3_t2v_low | PASS (legacy lane semantics) | 6.37 | 2.01 | 492.2 | Run #4; direct reserve-vram 12; historical `clamp-12gb` label did not simulate a 12 GiB card |
| h3_t2v_best | PENDING (unmeasured) | 0.00 | 0.00 | 0.0 | Legacy T2V topology preserved as a control; no gated artifact |
| h3_i2v_low | MACHINE PASS; HUMAN PENDING (legacy provenance/lane) | 7.15 | 2.61 | 239.5 | Run #3; deterministic, but promotion awaits Jeffrey's eyeball; historical `clamp-12gb` meant direct reserve 12 |
| h3_r2v_low | MACHINE PASS; HUMAN AUDIO/VIDEO PENDING | 6.56 | 2.31 | 206.6 | Run #4; corrected Ref2VA is deterministic; generated stem requires audition before any use |
| h3_i2v_best | PENDING (unmeasured) | 0.00 | 0.00 | 0.0 | Official topology propagated; no gated artifact |
| h3_r2v_best | PENDING (unmeasured) | 0.00 | 0.00 | 0.0 | Official Ref2VA topology propagated; no gated artifact |
| ltx_audio_ckpt | FAIL (VRAM 15.34 GB > 14.5 GB) | 15.34 | 1.43 | 209.5 | Run #3; boot lane: lab-8199, sage-free |
| ltx_audio_gguf | PASS | 8.55 | 2.31 | 185.1 | Run #10; boot lane: lab-8199, sage-free, reserve-12gb |
| ltx_i2v_gguf | PASS (legacy lane semantics) | 7.17 | 1.86 | 268.0 | Run #2; direct reserve-vram 14; historical `clamp-14gb` label did not simulate a 14 GiB card |
| ltx_t2v_gguf | STALE (selected B not rerun) | 15.14 | 2.75 | 236.9 | Latest artifact is variant C and failed the gate; current file selects B. Attempt limit reached; see escalation log. |
| h3_i2v_continuation_experimental | MACHINE PASS (cold); HUMAN PENDING | 6.80 | 2.32 | 252.3 | Run #2 represents clip 3; seam metrics pass, but promotion awaits Jeffrey's full-video eyeball |
