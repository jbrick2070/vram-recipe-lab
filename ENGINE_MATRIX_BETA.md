# Engine Matrix (Beta)

This document tracks engine candidate evaluations in `vram-recipe-lab`.

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
| h3_t2v_best | suite child | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 9.14 | 1033.3 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | T1 is a valid warm child, but its absolute peak rose 0.330 GiB over T0 and formally failed the suite creep gate |
| h3_i2v_low | smoke | INVALID (sampler missed peak) | 6.05 | 0.6 | yes | 0/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Measured on box (INVALID (sampler missed peak)) |
| h3_r2v_low | smoke | GATE PASS (cold-only); HUMAN PENDING | 7.20 | 260.6 | yes | 1/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | Corrected V3 dotted-socket run #5; old nested-socket runs 3/4 are superseded |
| h3_i2v_best | suite child | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 9.15 | 1182.5 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | Valid I0/I1 pair; overall suite and human gates remain failed/pending respectively |
| h3_r2v_best | suite child | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 8.42 | 936.5 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | Valid V3 dotted-socket R0/R1 pair supersedes old defective R2V socket evidence; overall suite still failed |
| ltx_audio_ckpt | smoke | FAIL (VRAM 15.34 GB > 14.5 GB) | 15.34 | 209.5 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Measured on box |
| ltx_audio_gguf | gguf | STALE/SUPERSEDED (fixture truth correction) | 8.55 | 185.1 | yes | 0/2 | lab-8199, sage-free, reserve-12gb | 2026-08-08 | Historical deterministic static-control pair; not speech evidence |
| ltx_audio_gguf_interstitial_static | gguf experiment | GATE PASS (cold experimental); HUMAN PENDING | 9.25 | 213.7 | yes | 1/2 | lab-8199, sage-free, reserve-12gb | 2026-08-08 | Exactly one matrix run; no warm certification; eyeball/ear comparison pending |
| ltx_audio_gguf_tts_dialogue | gguf experiment | GATE PASS (cold experimental); HUMAN PENDING | 7.82 | 181.3 | yes | 1/2 | lab-8199, sage-free, reserve-12gb | 2026-08-08 | Exactly one matrix run; no warm certification; eyeball/ear comparison pending |
| ltx_audio_gguf_music_opening | gguf experiment | GATE PASS (cold experimental); HUMAN PENDING | 7.73 | 185.3 | yes | 1/2 | lab-8199, sage-free, reserve-12gb | 2026-08-08 | Exactly one matrix run; no warm certification; eyeball/ear comparison pending |
| ltx_audio_gguf_music_closing | gguf experiment | GATE PASS (cold experimental); HUMAN PENDING | 7.89 | 189.3 | yes | 1/2 | lab-8199, sage-free, reserve-12gb | 2026-08-08 | Exactly one matrix run; no warm certification; eyeball/ear comparison pending |
| ltx_i2v_gguf | smoke | PASS (legacy lane semantics) | 7.17 | 268.0 | yes | 2/2 | reserve-14gb (legacy label was clamp-14gb) | 2026-08-08 | Valid artifact; not target-card evidence |
| ltx_t2v_gguf | gguf | CLOSED (selected B stale; no rerun authorized) | 15.14 | 236.9 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Three-attempt allowance exhausted; selected B remains uncertified; see `docs/ESCALATE.md` |
| h3_i2v_continuation_experimental | experimental | MACHINE PASS (cold); HUMAN PENDING | 6.80 | 252.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Clip-3 identity only; promotion pending eyeball |
| h3_i2v_suite_sentinel | suite child | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 7.44 | 218.9 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | S3 receipt is valid; it does not convert the overall suite failure into a pass |
| h3_best_suite | suite | MACHINE SUITE FAIL; HUMAN PENDING | 9.15 | 8055.0 | yes | 0/1 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | All 11 child gates passed; after net-metric correction, formal failure is T1 absolute peak +0.330 GiB over T0 (limit 0.250) |
| h3_r2v_refaudio_tts_dialogue | experiment | GATE PASS (cold-only); HUMAN EYE/EAR PENDING | 7.15 | 249.0 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | 124 frames/5.167 s valid; strong objective image conditioning; native generated audio -21.4 LUFS; no promotion |
| h3_r2v_refaudio_static_control | experiment | UNRENDERED/HELD | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | never | TTS and opening-music cold cells exist; static control remains unrendered |
| h3_r2v_refaudio_music_opening | experiment | GATE PASS (cold-only); HUMAN EYE/EAR PENDING | 7.18 | 249.0 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | 124 frames/5.167 s valid; native audio -23.1 LUFS; strong music reconstruction but no objective beat-to-motion proof; no promotion |
| h3_mime_i2v | experiment | GATE PASS (cold-only); HUMAN VISUAL OK; FORMAL EAR FIELDS PENDING | 7.28 | 178.9 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Exact 90 frames/3.750 s; native audio -27.5 LUFS; Jeffrey said the images look good and authorized one R2V proof; one-line soundscape receipt field pending |
| h3_mime_r2v | experiment | GATE PASS (cold-only); HUMAN VISUAL OK; EAR PENDING | 7.23 | 188.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Exact 90 frames/3.750 s; strong objective portrait stability; native audio about -40.5 LUFS; final authorized mime render, no promotion |
