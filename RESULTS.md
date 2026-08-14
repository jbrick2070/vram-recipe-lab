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
| ltx_t2v_high | **PASS (marginal; non-promotable)** | 14.45 | 1.73 | 0.0 | Warm cache (Run #5); within 0.25 GiB of the 14.5 GiB ceiling; boot lane: lab-8199, sage-free |
| ltx_i2v_low | **FAIL (VRAM 15.41 GB > 14.5 GB)** | 15.41 | 1.34 | 0.0 | Run #16; boot lane: lab-8199, sage-free |
| ltx_i2v_high | **PASS (marginal; non-promotable)** | 14.50 | 1.60 | 0.0 | Warm cache (Run #5); at the 14.5 GiB ceiling; boot lane: lab-8199, sage-free |
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
| h3_i2v_continuation_experimental | MACHINE GATE PASS (cold-only); HUMAN PENDING | 6.80 | 2.32 | 252.3 | Run #2 represents clip 3; seam metrics pass, but promotion awaits Jeffrey's full-video eyeball |
| h3_i2v_suite_sentinel | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 7.44 | 4.23 | 218.9 | Run #9/S3; sentinel execution is valid, but it does not convert the failed suite into a pass |
| h3_best_suite | MACHINE SUITE FAIL; HUMAN PENDING | 9.15 | N/A | 8055.0 | All 11 canonical child gates passed. After correcting cross-child net-peak semantics, the formal failure remains T1 absolute peak +0.330 GiB over T0 (limit 0.250); no suite promotion. |
| h3_r2v_refaudio_tts_dialogue | GATE PASS (cold-only); LIP-SYNC UNTESTED | 7.15 | 2.46 | 249.0 | Retraction: the neutral wide-scene prompt did not request lip-sync. Human amendment: `results/comparisons/h3_refaudio_human_reviews.json` |
| h3_r2v_refaudio_static_control | UNRENDERED/HELD | 0.00 | 0.00 | 0.0 | No run; TTS and opening-music cold cells now exist, but no control was authorized |
| h3_r2v_refaudio_music_opening | GATE PASS (cold-only); OK-EXPERIMENTAL | 7.18 | 2.46 | 249.0 | Human amendment: `results/comparisons/h3_refaudio_human_reviews.json`; audio reconstruction: `results/comparisons/h3_refaudio_reconstruction.json`; not warm/promoted |
| h3_mime_i2v | GATE PASS (cold-only); HUMAN VISUAL OK; FORMAL EAR FIELDS PENDING | 7.28 | 2.52 | 178.9 | Run #1 only; exact 90 frames/3.750 s with native audio at -27.5 LUFS. Jeffrey said the images look good and approved one R2V continuation; the required one-line soundscape description remains pending. |
| h3_mime_r2v | GATE PASS (cold-only); HUMAN VISUAL OK; EAR PENDING | 7.23 | 2.61 | 188.3 | Run #1 only; exact 90 frames/3.750 s, strong objective portrait stability, native audio about -40.5 LUFS; final authorized mime render, not warm or promoted |
| h3_r2v_refaudio_tts_lipsync | HISTORICAL COLD GATE PASS; SUPERSEDED BY EXACT-FIXTURE PAIR | 7.15 | 2.50 | 270.6 | Receipt: `results/h3_r2v_refaudio_tts_lipsync_run1.json`; used derivative TTS plus extra scene reference |
| wan_ti2v_5b_cmp_832x480_f193 | PASS | 12.10 | 7.08 | 407.5 | Receipt: `results/wan_ti2v_5b_cmp_832x480_f193_run4.json`; executor cache nonce; sampler/output execution proved |
| ltx_video_2b_distilled_cmp_832x480_f193 | PASS | 13.11 | 8.28 | 13.8 | Receipt: `results/ltx_video_2b_distilled_cmp_832x480_f193_run2.json`; executor cache nonce; sampler/output execution proved |
| h3_r2v_refaudio_tts_lipsync_seed43 | HISTORICAL COLD GATE PASS; SUPERSEDED BY EXACT-FIXTURE PAIR | 6.83 | 2.18 | 289.4 | Receipt: `results/h3_r2v_refaudio_tts_lipsync_seed43_run1.json`; used derivative TTS plus extra scene reference |
| h3_r2v_refaudio_tts_lipsync_exact_seed42 | GATE PASS (cold-only) (machine; human pending) | 6.71 | 2.15 | 305.3 | Receipt: `results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json`; exact portrait + raw-TTS contract |
| h3_r2v_refaudio_tts_lipsync_exact_seed43 | GATE PASS (cold-only) (machine; human pending) | 6.51 | 5.23 | 297.8 | Receipt: `results/h3_r2v_refaudio_tts_lipsync_exact_seed43_run1.json`; exact portrait + raw-TTS contract |
| ltx_audio_hq_h1_1024x576 | PASS | 7.06 | 2.43 | 248.5 | Receipt: `results/ltx_audio_hq_h1_1024x576_run2.json`; executor cache nonce; sampler/output execution proved |
| ltx_audio_hq_h2_193f | PASS | 7.93 | 2.67 | 341.3 | Receipt: `results/ltx_audio_hq_h2_193f_run2.json`; executor cache nonce; sampler/output execution proved |
| ltx_audio_hq_h3_1024x576_193f | PASS | 7.36 | 2.31 | 585.3 | Receipt: `results/ltx_audio_hq_h3_1024x576_193f_run2.json`; executor cache nonce; sampler/output execution proved |
| wan_i2v_14b_exoneration_832x480_f33 | PASS | 13.93 | 9.93 | 274.2 | Receipt: `results/wan_i2v_14b_exoneration_832x480_f33_run2.json`; clamp-12gb; executor cache nonce; sampler/output execution proved |
| h3_i2v_sage_patch_fp16pv_experimental | TIMEOUT (exceeded 1800s; owned server shutdown proved) | 6.33 | 2.15 | 1801.5 | Receipt: `results/h3_i2v_sage_patch_fp16pv_experimental_run1.json`; no artifact; owned-server cleanup proved; nonce-controlled execution unproved |
| ltx_audio_motion_m1_prompt | GATE PASS (cold-only) | 9.09 | 2.15 | 240.2 | Receipt: `results/ltx_audio_motion_m1_prompt_run1.json`; executor cache nonce; sampler/output execution proved |
| ltx_audio_motion_m2_soft_anchor | GATE PASS (cold-only) | 9.03 | 2.32 | 219.5 | Receipt: `results/ltx_audio_motion_m2_soft_anchor_run1.json`; executor cache nonce; sampler/output execution proved |
| ltx_audio_motion_m3_double_duration | GATE PASS (cold-only) | 8.24 | 2.32 | 400.3 | Receipt: `results/ltx_audio_motion_m3_double_duration_run1.json`; executor cache nonce; sampler/output execution proved |
| h3_mime_i2v_ledger_music_closing_8s | GATE PASS (cold-only) (machine; human pending) | 6.71 | 2.15 | 542.9 | Receipt: `results/h3_mime_i2v_ledger_music_closing_8s_run1.json`; executor cache nonce; sampler/output execution proved |
| h3_i2v_turbo_w4a8_4step | **BLOCKED (missing both assets)** | 0.00 | 0.00 | 0.0 | No run and no download: H3 W4A8-mixed weight and H3 four-step LightX2V LoRA are absent. Evidence: `results/comparisons/h3_speed_stack_inventory.json` |
| humo_1p7b_diet | **WARM MACHINE PASS AT CLAMP-13; HUMAN PARITY PENDING; LATER CLAMP-12 FAIL** | 12.84 winner; 14.47 current alias | 8.69 winner; 2.18 current alias | 243.0 winner; 259.8 current alias | Immutable [run #2](results/humo_1p7b_diet_run2.json) is the warm clamp-13 winner with zero generation-graph/widget changes. Later [run #3](results/humo_1p7b_diet_run3.json) failed clamp-12 at 12.28 GiB net and remains the [current alias](results/humo_1p7b_diet.json); no `--force` repeat. [Comparison](results/humo_diet/phase1_clamp_floor_comparison.json). |

## 2026-08-09 consolidated close-out

This section is the canonical interpretation of the final campaign rows above. It
does not rewrite older immutable receipts or inherit a human verdict across recipes.

| Evidence family | Final machine result | Human/promotion state | Canonical evidence |
|---|---|---|---|
| Same-canvas general-video pair | LTX distilled 2B wins the warm normalized workload by **29.528986x**; WAN/LTX measure **52.784974 / 1.787565 render-s per output-s** and **0.189145 / 5.585252 MP-frames/s** respectively | Rank is machine-normalized; shot quality remains workload-specific | `results/comparisons/general_video_speed_pair.json` |
| H3 speaking A/B | Two cold machine-gated takes, seeds **42/43** | Visible articulation in the technical screen; actual sync and consistency pending Jeffrey; HuMo comparison is OTR-side | `results/comparisons/h3_lipsync_ab_package.json` |
| H3 RefAudio reconstruction | Receipt-bound aligned PCM r=**0.969528** over the 3.88-second music reference | Conditioning reconstruction, not an independent audio-generator lane | `results/comparisons/h3_refaudio_reconstruction.json` |
| LTX Audio HQ ladder | H1/H2/H3 all warm-pass; H3 **1024x576x193** is the best machine-certified composition | Jeffrey full-clip eyeball pending | `results/comparisons/ltx_audio_hq_ladder.json` |
| WAN I2V 14B production floor | Warm-pass; cold net is **11.90/12 GiB** with only **0.10 GiB** target-card headroom | Exonerated but tight; WAN TI2V remains safer default recommendation | `results/comparisons/wan_i2v_14b_exoneration.json` |
| H3 turbo stack | **BLOCKED**: W4A8-mixed H3 weight and H3 four-step LoRA both missing | No download performed; proposal awaits Jeffrey | `results/comparisons/h3_speed_stack_inventory.json` |
| KJ per-model Sage probe | **FAIL**: `0x80000003`, timeout, no output, cleanup proved | Never default on measured sm_120 environment | `results/comparisons/h3_sage_patch_probe.json` |
| LTX motion ladder | M0-M3 artifacts complete | M0/M1/M2 near-still and M3 slow camera move in contact sheets; full ranking and beat response pending, so no inherent-near-still conclusion | `results/comparisons/ltx_motion_ladder.json` |
| Unconditioned Mini Mime | One exact **192-frame / 8.000-second** cold machine pass with native audio | Strict human gate pending: no speech-like/vocal-like content of any intelligibility, plus coherent diegetic sync | `results/comparisons/h3_mime_unconditioned.json`; `results/comparisons/h3_mime_audio_qa.json` |

The previously reported LTX timings of **20.3 seconds / 25 frames** and
**83.8 seconds / 193 frames** are preserved as `UNNORMALIZED` because canvas, step
count, and exact model are unknown. They are not ranking inputs.
Evidence: `results/comparisons/general_video_speed_pair.json`.

The duration/token estimator records **192 = 17*11+5 frames = 8.000 seconds at
24 fps** and is scoped to output visual tokens only; it is not a VRAM predictor.
The public **692x692 / 192-frame / 210-second / 8 GB** result remains
`EXTERNAL-REPORTED` commenter evidence. Evidence:
`results/comparisons/h3_token_budget_check.json`.

Exact distribution-seed 2.1 pins are recorded in
`results/comparisons/environment_2p1.json`.
| humo_14b_diet_portrait_480x832_f97 | PASS (machine; human pending) | 13.22 | 6.87 | 285.3 | Run #2; boot lane: lab-8199, sage-free, no-pinned, reserve-2.921gb; executor cache nonce; sampler/output execution proved |
| humo_14b_diet_landscape_832x480_f97 | PASS (machine; human pending) | 13.06 | 7.09 | 288.6 | Run #2; boot lane: lab-8199, sage-free, no-pinned, reserve-2.921gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed42_f124 | PASS (machine; human pending) | 7.88 | 3.49 | 895.1 | Run #3; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_motion_small_seed42_f124 | PASS (machine; human pending) | 7.58 | 3.42 | 893.0 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_motion_large_seed42_f124 | PASS (machine; human pending) | 8.62 | 3.84 | 1006.8 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed43_f124 | PASS (machine; human pending) | 8.96 | 4.47 | 928.8 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed44_f124 | PASS (machine; human pending) | 8.22 | 3.98 | 1012.1 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed45_f124 | PASS (machine; human pending) | 8.12 | 3.73 | 939.7 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed46_f124 | PASS (machine; human pending) | 7.88 | 3.72 | 882.3 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_score_seed42_f124 | PASS (machine; human pending) | 8.13 | 3.76 | 891.5 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_sfx_seed42_f124 | PASS (machine; human pending) | 7.86 | 3.74 | 897.1 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed42_f192 | PASS (machine; human pending) | 10.44 | 2.52 | 1844.6 | Run #3; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_unconditioned_music_scene_seed42_f277 | PASS (machine; human pending) | 13.83 | 2.15 | 3527.1 | Run #2; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_i2v_canonical_832x480_f107 | FAIL (VRAM 15.39 GB > 14.5 GB) | 15.39 | 2.33 | 178.8 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_dim_lighthearted_seed42_f124 | PASS (cold) (machine; human pending) | 8.14 | 1.83 | 970.3 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved |
| h3_music_followup_mood_dim_tense_seed42_f124 | PASS (cold) (machine; human pending) | 8.21 | 2.13 | 980.5 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_bright_lighthearted_seed42_f124 | PASS (cold) (machine; human pending) | 8.35 | 2.08 | 998.9 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_bright_noir_seed42_f124 | PASS (cold) (machine; human pending) | 8.27 | 2.26 | 976.0 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_dim_ragtime_seed42_f124 | PASS (cold) (machine; human pending) | 8.41 | 2.30 | 990.5 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed43_f124 | PASS (cold) (machine; human pending) | 8.37 | 2.14 | 942.9 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed44_f124 | PASS (cold) (machine; human pending) | 8.05 | 2.13 | 888.9 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed45_f124 | PASS (cold) (machine; human pending) | 8.16 | 2.13 | 901.4 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed46_f124 | PASS (cold) (machine; human pending) | 8.13 | 2.24 | 902.7 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed42_f192 | PASS (cold) (machine; human pending) | 11.06 | 2.24 | 1863.9 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed42_f277 | FAIL (VRAM 14.72 GB > 14.5 GB) | 14.72 | 2.24 | 3594.7 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_jobd_lipsync_refaudio_seed43_f192 | PASS (cold) (machine; human pending) | 6.88 | 2.28 | 436.0 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_origin_prompt_only_exact_seed42_f124 | PASS (cold) (machine; human pending) | 6.44 | 2.11 | 192.5 | Run #1; boot lane: lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb; executor cache nonce; sampler/output execution proved; elevated-baseline lane, operator-authorized 2026-08-10 |
| FO:front-office-r1/t2i-low-smoke/comfy0320-h3/t2i_low | PASS (cold) | 12.55 | 2.37 | 7.8 | Run #1; boot lane: lab-8199, sage-free; elevated-baseline lane, operator-authorized 2026-08-10; Front Office sealed cell |
| FO:front-office-h3-current-r1/i2v-native-av-smoke/comfy0320-h3/h3_i2v_current_profile_av_smoke | FAIL (VRAM 15.11 GB > 14.5 GB) | 15.11 | 2.46 | 170.7 | Run #1; boot lane: lab-8199, sage-free; elevated-baseline lane, operator-authorized 2026-08-10; Front Office sealed cell |
