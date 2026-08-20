# Engine Matrix (Beta)

This document tracks engine candidate evaluations in `vram-recipe-lab`.

**Measurement coverage: COMPLETE.** Every shipping video engine plus the H3
character challenger now has receipt-bound machine evidence. Character casting is
still `PENDING_HUMAN` across the five-clip HuMo/H3 review package; OTR-side HuMo rows
are measurements, not lab-gate passes. See
[`docs/HUMO_BAKEOFF.md`](docs/HUMO_BAKEOFF.md) and
`results/otr_side/humo_character_lane_bakeoff.json`.

HuMo 1.7B's clamp floor is now also measured: immutable run 2 is a warm machine
winner at **12.84 GiB**, while human quality parity remains pending. The later
clamp-12 failure remains the truthful current alias.
[HuMo diet report](docs/HUMO_DIET.md) and
[Phase 1 comparison receipt](results/humo_diet/phase1_clamp_floor_comparison.json).

| recipe | tier | status | peak VRAM (GB) | wall clock (s) | gated | pass consecutive | boot lane | last run | notes |
|---|---|---|---|---|---|---|---|---|---|
| t2i_low | smoke | PASS | 9.48 | 0.0 | yes | 2/2 | lab-8199, sage-free, clamp-8gb | 2026-08-08 | Warm cache (Run #13); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| t2i_high | smoke | PASS | 9.60 | 0.0 | yes | 2/2 | lab-8199, sage-free, clamp-8gb | 2026-08-08 | Warm cache (Run #7); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| wan_ti2v_low | smoke | PASS | 8.28 | 0.0 | yes | 2/2 | lab-8199, sage-free, clamp-8gb | 2026-08-08 | Warm cache (Run #9); boot lane: lab-8199, sage-free, clamp-8gb (Clamp Pass Line applied) |
| wan_ti2v_high | smoke | PASS | 11.79 | 0.0 | yes | 2/2 | lab-8199, sage-free | 2026-08-08 | Warm cache (Run #6); boot lane: lab-8199, sage-free |
| wan_i2v_14b_low | smoke | FAIL (execution error) | 15.28 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Run #1; boot lane: lab-8199, sage-free |
| wan_i2v_14b_high | smoke | FAIL (execution error) | 15.34 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-07 | Run #1; boot lane: lab-8199, sage-free |
| ltx_t2v_low | smoke | FAIL (VRAM 15.38 GB > 14.5 GB) | 15.38 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #3; boot lane: lab-8199, sage-free |
| ltx_t2v_high | smoke | PASS (marginal; non-promotable) | 14.45 | 0.0 | yes | 2/2 | lab-8199, sage-free | 2026-08-08 | Within 0.25 GiB of the 14.5 GiB ceiling; warm Run #5 |
| ltx_i2v_low | smoke | FAIL (VRAM 15.41 GB > 14.5 GB) | 15.41 | 0.0 | yes | 0/2 | lab-8199, sage-free | 2026-08-08 | Run #16; boot lane: lab-8199, sage-free |
| ltx_i2v_high | smoke | PASS (marginal; non-promotable) | 14.50 | 0.0 | yes | 2/2 | lab-8199, sage-free | 2026-08-08 | At the 14.5 GiB ceiling; warm Run #5 |
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
| h3_i2v_continuation_experimental | experimental | MACHINE GATE PASS (cold-only); HUMAN PENDING | 6.80 | 252.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Clip-3 identity only; promotion pending eyeball |
| h3_i2v_suite_sentinel | suite child | INDIVIDUAL WARM PASS; OVERALL SUITE FAIL; HUMAN PENDING | 7.44 | 218.9 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | S3 receipt is valid; it does not convert the overall suite failure into a pass |
| h3_best_suite | suite | MACHINE SUITE FAIL; HUMAN PENDING | 9.15 | 8055.0 | yes | 0/1 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-08 | All 11 child gates passed; after net-metric correction, formal failure is T1 absolute peak +0.330 GiB over T0 (limit 0.250) |
| h3_r2v_refaudio_tts_dialogue | experiment | GATE PASS (cold-only); LIP-SYNC UNTESTED | 7.15 | 249.0 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Human amendment: `results/comparisons/h3_refaudio_human_reviews.json` |
| h3_r2v_refaudio_static_control | experiment | UNRENDERED/HELD | 0.00 | 0.0 | no | 0/2 | lab-8199, sage-free | never | TTS and opening-music cold cells exist; static control remains unrendered |
| h3_r2v_refaudio_music_opening | experiment | GATE PASS (cold-only); OK-EXPERIMENTAL | 7.18 | 249.0 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Human review: `results/comparisons/h3_refaudio_human_reviews.json`; reconstruction: `results/comparisons/h3_refaudio_reconstruction.json` |
| h3_mime_i2v | experiment | GATE PASS (cold-only); HUMAN VISUAL OK; FORMAL EAR FIELDS PENDING | 7.28 | 178.9 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Exact 90 frames/3.750 s; native audio -27.5 LUFS; Jeffrey said the images look good and authorized one R2V proof; one-line soundscape receipt field pending |
| h3_mime_r2v | experiment | GATE PASS (cold-only); HUMAN VISUAL OK; EAR PENDING | 7.23 | 188.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Exact 90 frames/3.750 s; strong objective portrait stability; native audio about -40.5 LUFS; final authorized mime render, no promotion |
| h3_r2v_refaudio_tts_lipsync | experiment | HISTORICAL COLD GATE PASS; SUPERSEDED | 7.15 | 270.6 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-08 | Derivative TTS plus extra scene; `results/h3_r2v_refaudio_tts_lipsync_run1.json` |
| wan_ti2v_5b_cmp_832x480_f193 | comparison | PASS | 12.10 | 407.5 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-4gb | 2026-08-08 | Receipt: `results/wan_ti2v_5b_cmp_832x480_f193_run4.json` |
| ltx_video_2b_distilled_cmp_832x480_f193 | comparison | PASS | 13.11 | 13.8 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-4gb | 2026-08-08 | Receipt: `results/ltx_video_2b_distilled_cmp_832x480_f193_run2.json` |
| h3_r2v_refaudio_tts_lipsync_seed43 | experiment | HISTORICAL COLD GATE PASS; SUPERSEDED | 6.83 | 289.4 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-09 | Derivative TTS plus extra scene; `results/h3_r2v_refaudio_tts_lipsync_seed43_run1.json` |
| h3_r2v_refaudio_tts_lipsync_exact_seed42 | experiment | GATE PASS (cold-only) (machine; human pending) | 6.71 | 305.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-09 | `results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json`; exact portrait + raw TTS |
| h3_r2v_refaudio_tts_lipsync_exact_seed43 | experiment | GATE PASS (cold-only) (machine; human pending) | 6.51 | 297.8 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-12gb | 2026-08-09 | `results/h3_r2v_refaudio_tts_lipsync_exact_seed43_run1.json`; exact portrait + raw TTS |
| ltx_audio_hq_h1_1024x576 | gguf | PASS | 7.06 | 248.5 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/ltx_audio_hq_h1_1024x576_run2.json` |
| ltx_audio_hq_h2_193f | gguf | PASS | 7.93 | 341.3 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/ltx_audio_hq_h2_193f_run2.json` |
| ltx_audio_hq_h3_1024x576_193f | gguf | PASS | 7.36 | 585.3 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/ltx_audio_hq_h3_1024x576_193f_run2.json` |
| wan_i2v_14b_exoneration_832x480_f33 | exoneration | PASS | 13.93 | 274.2 | yes | 2/2 | lab-8199, sage-free, no-pinned, cache-classic, clamp-12gb (reserve-3.921gb) | 2026-08-09 | Receipt: `results/wan_i2v_14b_exoneration_832x480_f33_run2.json` |
| h3_i2v_sage_patch_fp16pv_experimental | experiment | TIMEOUT (exceeded 1800s; owned server shutdown proved) | 6.33 | 1801.5 | yes | 0/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/h3_i2v_sage_patch_fp16pv_experimental_run1.json`; no artifact; execution unproved |
| ltx_audio_motion_m1_prompt | gguf | GATE PASS (cold-only) | 9.09 | 240.2 | yes | 1/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/ltx_audio_motion_m1_prompt_run1.json` |
| ltx_audio_motion_m2_soft_anchor | gguf | GATE PASS (cold-only) | 9.03 | 219.5 | yes | 1/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/ltx_audio_motion_m2_soft_anchor_run1.json` |
| ltx_audio_motion_m3_double_duration | gguf | GATE PASS (cold-only) | 8.24 | 400.3 | yes | 1/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/ltx_audio_motion_m3_double_duration_run1.json` |
| h3_mime_i2v_ledger_music_closing_8s | experiment | GATE PASS (cold-only) (machine; human pending) | 6.71 | 542.9 | yes | 1/2 | lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Receipt: `results/h3_mime_i2v_ledger_music_closing_8s_run1.json` |
| h3_i2v_turbo_w4a8_4step | proposed turbo | **BLOCKED (missing both assets)** | 0.00 | 0.0 | no | 0/2 | not run | 2026-08-09 | No download; W4A8-mixed H3 weight and H3 four-step LoRA absent. Evidence: `results/comparisons/h3_speed_stack_inventory.json` |
| humo_1_7b_bakeoff (OTR) | production-lane bakeoff | **MEASURED OTR-SIDE; HUMAN PENDING; NOT LAB-GATED** | 15.12-15.23 | 207.5-233.8 | no | 2 measured takes | otr-headless-8000, HUMO, production-wrapper | 2026-08-09 | Fixed request seed 7; 480x832x129 @ 25 fps / 5.160 s. Receipts: `results/otr_side/humo_1_7b_bakeoff_take1.json`, `results/otr_side/humo_1_7b_bakeoff_take2.json` |
| humo_14b_fp8_bakeoff (OTR) | production-lane bakeoff | **MEASURED OTR-SIDE; HUMAN PENDING; NOT LAB-GATED** | 14.98 | 245.9 | no | 1 measured take | otr-headless-8000, HUMO, production-wrapper | 2026-08-09 | Production engine ID `humo`; 480x832x97 @ 25 fps / 3.880 s. Receipt: `results/otr_side/humo_14b_fp8_bakeoff_take1.json` |
| humo_1p7b_diet | clamp-floor certification | **WARM MACHINE PASS AT CLAMP-13; HUMAN PARITY PENDING; CURRENT ALIAS CLAMP-12 FAIL** | 12.84 winner; 14.47 current alias | 243.0 winner; 259.8 current alias | yes | 2/2 at clamp-13 | lab-8199, sage-free, no-pinned, clamp-13gb (reserve-2.921gb) | 2026-08-09 | Zero generation-graph/widget changes. Immutable run 2 is the winner; run 3 remains the current alias and honestly records net 12.28 GiB > clamp-12. [Comparison receipt](results/humo_diet/phase1_clamp_floor_comparison.json) |

## Normalized speed ranking

The only ranking-eligible general-video comparison controls canvas, delivered duration,
frame count, frame rate, and warm execution proof. Values below are derived and frozen
in `results/comparisons/general_video_speed_pair.json`.

| Rank | Engine | Controlled workload | Warm wall | Render-s / output-s | MP-frames / s | Evidence |
|---:|---|---|---:|---:|---:|---|
| 1 | LTX Video distilled 2B | 832x480, 193f, 25 fps, 7.72 s | 13.8 s | 1.787565 | 5.585252 | `results/comparisons/general_video_speed_pair.json` |
| 2 | WAN TI2V 5B | 832x480, 193f, 25 fps, 7.72 s | 407.5 s | 52.784974 | 0.189145 | `results/comparisons/general_video_speed_pair.json` |

LTX is **29.528986x** faster by normalized warm wall clock.
Evidence: `results/comparisons/general_video_speed_pair.json`.

### Unnormalized reports - recorded, not ranked

| Reported label | Wall | Frames | Missing controls | Status | Evidence |
|---|---:|---:|---|---|---|
| `ltx_8gb` | 20.3 s | 25 | Canvas, steps, exact model | **UNNORMALIZED** | `results/comparisons/general_video_speed_pair.json` |
| `ltx_video` | 83.8 s | 193 | Canvas, steps, exact model | **UNNORMALIZED** | `results/comparisons/general_video_speed_pair.json` |

## Final lane matrix

| Capability | Candidate | Machine state | Promotion/human state | Evidence |
|---|---|---|---|---|
| Sprint/general video | LTX Video distilled 2B | Normalized warm winner | Recommended per shot; quality remains content-dependent | `results/comparisons/general_video_speed_pair.json` |
| Workhorse lips | H3 Ref2VA speaking retest | Two cold machine-gated seeds | Visible articulation; exact sync and consistency pending Jeffrey's five-clip HuMo/H3 review | `docs/HUMO_BAKEOFF.md`; `results/comparisons/h3_lipsync_ab_package.json` |
| H3 reference audio | Opening-music RefAudio | Aligned PCM r=**0.969528** over the 3.88-second input | Reconstruction evidence; not an independent audio-generator lane | `results/comparisons/h3_refaudio_reconstruction.json` |
| Hero lips | HuMo incumbent | Three OTR-side production-lane measurements complete; no lab gate | Remains the recommendation pending lips/onset/identity review of all five clips | `docs/HUMO_BAKEOFF.md`; `results/otr_side/humo_1_7b_bakeoff_take1.json`; `results/otr_side/humo_14b_fp8_bakeoff_take1.json` |
| Character-lane bakeoff | HuMo 1.7B / HuMo 14B FP8 / H3 Ref2VA | Three OTR-side HuMo runs plus two lab H3 runs complete | `PENDING_HUMAN`; measurement coverage complete, casting decision open | `docs/HUMO_BAKEOFF.md`; `results/otr_side/humo_character_lane_bakeoff.json` |
| HuMo 1.7B VRAM diet | Production generation graph + clamp-13/no-pinned boot variant | Warm machine pass at **12.84 GiB**; Phase 2 diet levers skipped | Quality parity and OTR integration remain `PENDING_HUMAN` / externally gated | [report](docs/HUMO_DIET.md); [comparison receipt](results/humo_diet/phase1_clamp_floor_comparison.json) |
| LTX Audio HQ | H3 canvas+duration rung | Warm pass at **1024x576x193** | Best machine-certified HQ recommendation; Jeffrey eyeball pending | `results/comparisons/ltx_audio_hq_ladder.json` |
| WAN image-to-video | WAN I2V 14B production floor | Warm pass; cold **11.90/12 GiB** net | Exonerated but tight; WAN TI2V remains safer default | `results/comparisons/wan_i2v_14b_exoneration.json` |
| H3 turbo | W4A8-mixed + four-step LoRA | **BLOCKED**, both assets absent | No download; new campaign only after authorization | `results/comparisons/h3_speed_stack_inventory.json` |
| H3 Sage acceleration | KJ per-model FP16-PV | **FAIL**, kernel exception/timeout/no output | Never default on measured sm_120 environment | `results/comparisons/h3_sage_patch_probe.json` |
| LTX music motion | M0-M3 | Four cold artifacts complete | Technical screen: M0/M1/M2 near-still, M3 slow camera move; human ranking and beat response pending | `results/comparisons/ltx_motion_ladder.json` |
| Mini Mime | Unconditioned H3 I2V | Exact **192f / 8.000 s** cold machine pass | Strict gate pending: no speech-like/vocal-like content of any intelligibility, plus coherent diegetic sync | `results/comparisons/h3_mime_unconditioned.json`; `results/comparisons/h3_mime_audio_qa.json` |

The H3 token estimate remains a feasibility indicator, not a VRAM predictor. The
**692x692 / 192f / 210 s / 8 GB** public result and vocal-separation advice remain
`EXTERNAL-REPORTED`; local measured checks and scope are in
`results/comparisons/h3_token_budget_check.json`.

Distribution seed 2.1 is pinned in `results/comparisons/environment_2p1.json`.
| humo_14b_diet_portrait_480x832_f97 | experiment | PASS (cold) (machine; human pending) | 13.14 | 294.1 | yes | 1/2 | lab-8199, sage-free, no-pinned, reserve-2.921gb | 2026-08-09 | Measured on box (PASS (cold) (machine; human pending)) |
| humo_14b_diet_landscape_832x480_f97 | experiment | PASS (machine; human pending) | 13.06 | 288.6 | yes | 2/2 | lab-8199, sage-free, no-pinned, reserve-2.921gb | 2026-08-09 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed42_f124 | experiment | PASS (machine; human pending) | 7.88 | 895.1 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_motion_small_seed42_f124 | experiment | PASS (machine; human pending) | 7.58 | 893.0 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_motion_large_seed42_f124 | experiment | PASS (machine; human pending) | 8.62 | 1006.8 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-09 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed43_f124 | experiment | PASS (machine; human pending) | 8.96 | 928.8 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed44_f124 | experiment | PASS (machine; human pending) | 8.22 | 1012.1 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed45_f124 | experiment | PASS (machine; human pending) | 8.12 | 939.7 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed46_f124 | experiment | PASS (machine; human pending) | 7.88 | 882.3 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_score_seed42_f124 | experiment | PASS (machine; human pending) | 8.13 | 891.5 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_sfx_seed42_f124 | experiment | PASS (machine; human pending) | 7.86 | 897.1 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed42_f192 | experiment | PASS (machine; human pending) | 10.44 | 1844.6 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_unconditioned_music_scene_seed42_f277 | experiment | PASS (machine; human pending) | 13.83 | 3527.1 | yes | 2/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (machine; human pending)) |
| h3_i2v_canonical_832x480_f107 | measurement | FAIL (VRAM 15.39 GB > 14.5 GB) | 15.39 | 178.8 | yes | 0/2 | lab-8199, sage-free, manager-offline-test, no-pinned | 2026-08-10 | Measured on box (FAIL (VRAM 15.39 GB > 14.5 GB)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_dim_lighthearted_seed42_f124 | experiment | PASS (cold) (machine; human pending) | 8.14 | 970.3 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)) |
| h3_music_followup_mood_dim_tense_seed42_f124 | experiment | PASS (cold) (machine; human pending) | 8.21 | 980.5 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_bright_lighthearted_seed42_f124 | experiment | PASS (cold) (machine; human pending) | 8.35 | 998.9 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_bright_noir_seed42_f124 | experiment | PASS (cold) (machine; human pending) | 8.27 | 976.0 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_mood_dim_ragtime_seed42_f124 | experiment | PASS (cold) (machine; human pending) | 8.41 | 990.5 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed43_f124 | experiment | PASS (cold) (machine; human pending) | 8.37 | 942.9 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed44_f124 | experiment | PASS (cold) (machine; human pending) | 8.05 | 888.9 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed45_f124 | experiment | PASS (cold) (machine; human pending) | 8.16 | 901.4 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed46_f124 | experiment | PASS (cold) (machine; human pending) | 8.13 | 902.7 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed42_f192 | experiment | PASS (cold) (machine; human pending) | 11.06 | 1863.9 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_score_seed42_f277 | experiment | FAIL (VRAM 14.72 GB > 14.5 GB) | 14.72 | 3594.7 | yes | 0/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (FAIL (VRAM 14.72 GB > 14.5 GB)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_jobd_lipsync_refaudio_seed43_f192 | experiment | PASS (cold) (machine; human pending) | 6.88 | 436.0 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| h3_music_followup_origin_prompt_only_exact_seed42_f124 | experiment | PASS (cold) (machine; human pending) | 6.44 | 192.5 | yes | 1/2 | lab-8199, sage-free, manager-offline-test, no-pinned, cache-classic, reserve-12gb | 2026-08-10 | Measured on box (PASS (cold) (machine; human pending)); elevated-baseline lane, operator-authorized 2026-08-10 |
| FO:front-office-r1/t2i-low-smoke/comfy0320-h3/t2i_low | smoke | PASS (cold) | 12.55 | 7.8 | yes | cold-only | lab-8199, sage-free | 2026-08-13 | Measured on box (PASS (cold)); elevated-baseline lane, operator-authorized 2026-08-10 |
| FO:front-office-h3-current-r1/i2v-native-av-smoke/comfy0320-h3/h3_i2v_current_profile_av_smoke | experiment | FAIL (VRAM 15.11 GB > 14.5 GB) | 15.11 | 170.7 | yes | cold-only | lab-8199, sage-free | 2026-08-14 | Measured on box (FAIL (VRAM 15.11 GB > 14.5 GB)); elevated-baseline lane, operator-authorized 2026-08-10 |
| FO:front-office-ltx-current-r1/i2v-current-video-smoke/comfy0320-h3/ltx_video_2b_current_profile_cold_smoke | experiment | PASS (cold) | 13.36 | 24.8 | yes | cold-only | lab-8199, sage-free | 2026-08-14 | Measured on box (PASS (cold)); elevated-baseline lane, operator-authorized 2026-08-10 |
| FO:front-office-h3-t8-current-r1/i2v-action-control-20step/comfy0320-h3/h3_turbo_larry_v4_i2v_action_control | experiment | FAIL (VRAM 15.10 GB > 14.5 GB) | 15.10 | 237.7 | yes | cold-only | lab-8199, sage-free | 2026-08-14 | Measured on box (FAIL (VRAM 15.10 GB > 14.5 GB)); elevated-baseline lane, operator-authorized 2026-08-10 |
| FO:front-office-h3-t8-current-r1/i2v-action-turbo-v4-8step/h3-turbo-larry-v4/h3_turbo_larry_v4_i2v_action_8step | experiment | FAIL (VRAM 15.13 GB > 14.5 GB) | 15.13 | 125.9 | yes | cold-only | lab-8199, sage-free | 2026-08-14 | Measured on box (FAIL (VRAM 15.13 GB > 14.5 GB)); elevated-baseline lane, operator-authorized 2026-08-10 |
| ltx_2_5_a2v_gguf | gguf | FAIL (VRAM 15.56 GB > 14.5 GB) | 15.56 | 276.8 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.56 GB > 14.5 GB)) |
| ltx_2_5_t2v_gguf | gguf | FAIL (VRAM 15.60 GB > 14.5 GB) | 15.60 | 275.9 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.60 GB > 14.5 GB)) |
| ltx_2_5_a2v_gguf_opt | gguf | FAIL (VRAM 15.51 GB > 14.5 GB) | 15.51 | 152.3 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.51 GB > 14.5 GB)) |
| ltx_2_5_a2v_gguf_q5 | gguf | FAIL (VRAM 15.51 GB > 14.5 GB) | 15.51 | 348.5 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.51 GB > 14.5 GB)) |
| ltx_2_5_t2v_mime_gguf | gguf | FAIL (VRAM 15.48 GB > 14.5 GB) | 15.48 | 220.0 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.48 GB > 14.5 GB)) |
| ltx_2_5_t2v_soundtrack_1 | gguf | FAIL (VRAM 15.56 GB > 14.5 GB) | 15.56 | 224.5 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.56 GB > 14.5 GB)) |
| ltx_2_5_t2v_soundtrack_2 | gguf | FAIL (VRAM 15.52 GB > 14.5 GB) | 15.52 | 272.7 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.52 GB > 14.5 GB)) |
| ltx_2_5_t2v_radio_drama | gguf | FAIL (VRAM 15.56 GB > 14.5 GB) | 15.56 | 254.4 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.56 GB > 14.5 GB)) |
| ltx_2_5_t2v_path_a | gguf | FAIL (VRAM 15.52 GB > 14.5 GB) | 15.52 | 87.0 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.52 GB > 14.5 GB)) |
| ltx_2_5_t2v_path_a_visual | gguf | FAIL (VRAM 15.48 GB > 14.5 GB) | 15.48 | 87.2 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.48 GB > 14.5 GB)) |
| ltx_2_5_a2v_path_a_action | gguf | FAIL (VRAM 15.48 GB > 14.5 GB) | 15.48 | 106.4 | yes | 0/2 | lab-8199, sage-free, clamp-14.5gb (reserve-1.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.48 GB > 14.5 GB)) |
| ltx_2_5_path_b_pass1 | gguf | FAIL (VRAM 15.56 GB > 14.5 GB) | 15.56 | 98.9 | yes | 0/2 | lab-8199, sage-free, clamp-15gb (reserve-0.921gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.56 GB > 14.5 GB)) |
| ltx_2_5_a2v_path_a3_constrained | gguf | FAIL (VRAM 15.57 GB > 14.5 GB) | 15.57 | 107.6 | yes | 0/2 | lab-8199, sage-free, clamp-15.5gb (reserve-0.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.57 GB > 14.5 GB)) |
| ltx_2_5_golden_a2v_static_lipsync | gguf | FAIL (VRAM 15.60 GB > 14.5 GB) | 15.60 | 404.6 | yes | 0/2 | lab-8199, sage-free, clamp-15.5gb (reserve-0.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.60 GB > 14.5 GB)); elevated-baseline lane, operator-authorized 2026-08-10 |
| ltx_2_5_golden_t2v_action_foley | gguf | FAIL (VRAM 15.50 GB > 14.5 GB) | 15.50 | 93.0 | yes | 0/2 | lab-8199, sage-free, clamp-15.5gb (reserve-0.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.50 GB > 14.5 GB)) |
| ltx_2_5_golden_t2v_cinematic_music | gguf | FAIL (VRAM 15.47 GB > 14.5 GB) | 15.47 | 77.7 | yes | 0/2 | lab-8199, sage-free, clamp-15.5gb (reserve-0.421gb) | 2026-08-19 | Measured on box (FAIL (VRAM 15.47 GB > 14.5 GB)) |
| config_B_1_dolly | gguf | FAIL (no artifact output) | 15.52 | 14.7 | yes | 0/2 | lab-8199, sage-free, clamp-15.5gb (reserve-0.421gb) | 2026-08-19 | Measured on box (FAIL (no artifact output)) |
