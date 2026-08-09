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
| h3_t2v_best | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 9.14 | 4.60 | 1033.3 | Run #4/T1; valid 2/2 recipe pair and sampler/output execution, but the suite remains failed because T1 absolute peak rose 0.330 GiB over T0 |
| h3_i2v_low | INVALID (sampler missed peak) | 6.05 | 6.04 | 0.6 | Run #5; boot lane: lab-8199, sage-free, no-pinned, reserve-12gb |
| h3_r2v_low | GATE PASS (cold-only); HUMAN PENDING | 7.20 | 2.84 | 260.6 | Run #5; corrected V3 flat dotted `ref_images.ref_image_0` socket; prior nested-socket runs 3/4 are superseded and do not form a valid warm pair |
| h3_i2v_best | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 9.15 | 4.63 | 1182.5 | Run #4/I1; valid 2/2 recipe pair and sampler/output execution; no overall suite pass or human promotion |
| h3_r2v_best | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 8.42 | 4.21 | 936.5 | Run #4/R1; valid 2/2 V3 dotted-socket Ref2VA pair superseding the old defective socket encoding; no overall suite pass or human promotion |
| ltx_audio_ckpt | FAIL (VRAM 15.34 GB > 14.5 GB) | 15.34 | 1.43 | 209.5 | Run #3; boot lane: lab-8199, sage-free |
| ltx_audio_gguf | STALE/SUPERSEDED (fixture truth correction) | 8.55 | 2.31 | 185.1 | Historical run #10 was the static interstitial, not speech; current renamed recipe requires fresh evidence |
| ltx_audio_gguf_interstitial_static | GATE PASS (cold experimental); HUMAN PENDING | 9.25 | 2.59 | 213.7 | Run #1 only; exact four-condition matrix cell, not a warm certification; eyeball/ear comparison pending |
| ltx_audio_gguf_tts_dialogue | GATE PASS (cold experimental); HUMAN PENDING | 7.82 | 2.97 | 181.3 | Run #1 only; exact four-condition matrix cell, not a warm certification; eyeball/ear comparison pending |
| ltx_audio_gguf_music_opening | GATE PASS (cold experimental); HUMAN PENDING | 7.73 | 3.14 | 185.3 | Run #1 only; exact four-condition matrix cell, not a warm certification; eyeball/ear comparison pending |
| ltx_audio_gguf_music_closing | GATE PASS (cold experimental); HUMAN PENDING | 7.89 | 2.87 | 189.3 | Run #1 only; exact four-condition matrix cell, not a warm certification; eyeball/ear comparison pending |
| ltx_i2v_gguf | PASS (legacy lane semantics) | 7.17 | 1.86 | 268.0 | Run #2; direct reserve-vram 14; historical `clamp-14gb` label did not simulate a 14 GiB card |
| ltx_t2v_gguf | CLOSED (selected B stale; no rerun authorized) | 15.14 | 2.75 | 236.9 | Latest artifact is variant C and failed the gate; current file selects B. Three-attempt allowance exhausted; see `docs/ESCALATE.md`. |
| h3_i2v_continuation_experimental | MACHINE PASS (cold); HUMAN PENDING | 6.80 | 2.32 | 252.3 | Run #2 represents clip 3; seam metrics pass, but promotion awaits Jeffrey's full-video eyeball |
| h3_i2v_suite_sentinel | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 7.44 | 4.23 | 218.9 | Run #9/S3; sentinel execution is valid, but it does not convert the failed suite into a pass |
| h3_best_suite | MACHINE SUITE FAIL; HUMAN PENDING | 9.15 | — | 8055.0 | All 11 canonical child gates passed. After correcting cross-child net-peak semantics, the formal failure remains T1 absolute peak +0.330 GiB over T0 (limit 0.250); no suite promotion. |
| h3_r2v_refaudio_tts_dialogue | GATE PASS (cold-only); HUMAN EYE/EAR PENDING | 7.15 | 2.46 | 249.0 | Run #1 only; valid 124-frame/5.167 s A/V, strong objective image conditioning, native generated audio -21.4 LUFS; not warm or promoted |
| h3_r2v_refaudio_static_control | UNRENDERED/HELD | 0.00 | 0.00 | 0.0 | No run; TTS and opening-music cold cells now exist, but no control was authorized |
| h3_r2v_refaudio_music_opening | GATE PASS (cold-only); HUMAN EYE/EAR PENDING | 7.18 | 2.46 | 249.0 | Run #1 only; valid 124-frame/5.167 s A/V and native audio -23.1 LUFS. The first 3.88 s strongly reconstruct the reference music (aligned waveform r about 0.94), but objective beat-to-motion evidence is weak; not warm or promoted. |
| h3_mime_i2v | GATE PASS (cold-only); HUMAN VISUAL OK; FORMAL EAR FIELDS PENDING | 7.28 | 2.52 | 178.9 | Run #1 only; exact 90 frames/3.750 s with native audio at -27.5 LUFS. Jeffrey said the images look good and approved one R2V continuation; the required one-line soundscape description remains pending. |
| h3_mime_r2v | GATE PASS (cold-only); HUMAN VISUAL OK; EAR PENDING | 7.23 | 2.61 | 188.3 | Run #1 only; exact 90 frames/3.750 s, strong objective portrait stability, native audio about -40.5 LUFS; final authorized mime render, not warm or promoted |
