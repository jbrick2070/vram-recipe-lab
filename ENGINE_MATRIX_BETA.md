# Engine Matrix (Beta)

This document tracks engine candidate evaluations in 
ram-recipe-lab.

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
| h3_t2v_low | smoke | PASS (legacy lane semantics) | 6.37 | 492.2 | yes | 2/2 | reserve-12gb (legacy label was clamp-12gb) | 2026-08-08 | Human-approved artifact; not target-card evidence |
| h3_t2v_best | suite | PENDING (legacy topology, unmeasured) | N/A | N/A | no | 0/2 | lab-8199, sage-free | 2026-08-08 | Not certified |
| h3_i2v_low | smoke | MACHINE PASS; HUMAN PENDING (legacy provenance) | 7.15 | 239.5 | yes | 2/2 | reserve-12gb (legacy label was clamp-12gb) | 2026-08-08 | Deterministic artifact; promotion pending Jeffrey's eyeball |
| h3_r2v_low | smoke | MACHINE PASS; HUMAN AUDIO/VIDEO PENDING | 6.56 | 206.6 | yes | 2/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Deterministic corrected Ref2VA artifact; audition required |
| h3_i2v_best | suite | PENDING (official topology, unmeasured) | N/A | N/A | no | 0/2 | lab-8199, sage-free | 2026-08-08 | Not certified |
| h3_r2v_best | suite | PENDING (official topology, unmeasured) | N/A | N/A | no | 0/2 | lab-8199, sage-free | 2026-08-08 | Not certified |
| ltx_audio_ckpt | smoke | FAIL (VRAM 15.34 GB > 14.5 GB) | 15.34 | 209.5 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Measured on box |
| ltx_audio_gguf | gguf | PASS | 8.55 | 185.1 | yes | 2/2 | lab-8199, sage-free, reserve-12gb | 2026-08-08 | Deterministic source-audio mux |
| ltx_i2v_gguf | smoke | PASS (legacy lane semantics) | 7.17 | 268.0 | yes | 2/2 | reserve-14gb (legacy label was clamp-14gb) | 2026-08-08 | Valid artifact; not target-card evidence |
| ltx_t2v_gguf | gguf | STALE (selected B not rerun) | 15.14 | 236.9 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Latest artifact is variant C; selected B remains uncertified after attempt-limit escalation |
| h3_i2v_continuation_experimental | experimental | MACHINE PASS (cold); HUMAN PENDING | 6.80 | 252.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Clip-3 identity only; promotion pending eyeball |
