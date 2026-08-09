# Promotion Brief

Date: 2026-08-09

## Executive verdict

The machine campaign is complete, but no pending human decision is silently promoted.
The strongest immediate recommendation is the LTX distilled video lane for sprint work:
on the normalized same-canvas warm pair it rendered the identical workload
**29.528986x faster** than WAN TI2V. The character lane remains the only open casting
decision: the OTR production lane now adds two HuMo 1.7B measurements and one HuMo 14B
FP8 measurement to H3's two technically valid speaking takes. Measurement coverage is
complete; Jeffrey still needs to judge lips, onset, and identity across the five clips.
[Complete HuMo/H3 bakeoff](HUMO_BAKEOFF.md)

The HuMo 1.7B VRAM-diet follow-up has now reached its machine target without a graph
change: the immutable clamp-13 warm run peaked at **12.84 GiB**, down from the
production lane's two unclamped **15.118164 / 15.231445 GiB** measurements. This is
a boot-lane candidate, not a quality promotion; production-vs-diet parity remains
`PENDING_HUMAN`. [HuMo diet evidence](HUMO_DIET.md)

The final evidence keeps four boundaries explicit:

- machine certification is not a human quality verdict;
- a cold experimental pass is not a warm production pass;
- H3 RefAudio reconstructs conditioning audio rather than establishing an independent
  audio-composition lane; and
- recommendations below are recommendations, not automatic OTR integration decisions.

## Recommended three-role casting

| Role | Recommendation | Evidence and remaining gate |
|---|---|---|
| Sprint lane | **LTX Video distilled 2B** for fast general-video iteration | Warm normalized winner at the controlled canvas and duration; quality still needs shot-specific review. [Normalized comparison receipt](../results/comparisons/general_video_speed_pair.json) |
| Workhorse lips | **H3 Ref2VA candidate**, conditional on the five-clip review | Two cold machine-gated H3 takes show articulation. The OTR-side HuMo legs are now measured, but exact phoneme sync, pause settling, onset, identity, and consistency remain human-pending. [Complete bakeoff](HUMO_BAKEOFF.md) |
| Hero lips | **HuMo incumbent**, with the HuMo 1.7B clamp-13 diet as the lower-VRAM boot candidate | OTR measured the original production takes; the lab then achieved a **12.84 GiB** warm machine pass with no generation-graph/widget change. Character casting and diet quality parity both remain human-pending. [Complete bakeoff](HUMO_BAKEOFF.md); [diet evidence](HUMO_DIET.md) |

## Normalized general-video speed crown

Both engines rendered **832x480, 193 frames at 25 fps, delivered as 7.72 seconds**;
both measurements are second consecutive true executions with nonce-proven fresh
sampler/output branches. All values and formulae below come from the immutable
[same-canvas comparison receipt](../results/comparisons/general_video_speed_pair.json).

| Warm lane | Wall time | Render seconds / output second | Megapixel-frames / second | Result |
|---|---:|---:|---:|---|
| WAN TI2V 5B | 407.5 s | 52.784974 | 0.189145 | Second |
| LTX Video distilled 2B | 13.8 s | 1.787565 | 5.585252 | **Normalized winner** |

LTX's measured wall-clock advantage is **29.528986x**. Two previously reported LTX
timings remain deliberately outside this ranking because their canvas, steps, and
exact model were not supplied: **20.3 s / 25 frames** and **83.8 s / 193 frames**.
They are `UNNORMALIZED`, not counter-evidence to the controlled crown.
[Unnormalized-row provenance](../results/comparisons/general_video_speed_pair.json)

## Character-lane decider: measurements complete, human verdict open

The corrected action prompt produced two H3 Ref2VA takes using the same portrait and
TTS fixture, with only the seed changing. Seed 42 completed in **305.3 seconds** at a
**6.71 GiB** peak; seed 43 completed in **297.8 seconds** at a **6.51 GiB** peak. Both
deliver **124 frames at 864x480 and 24 fps**. They are cold machine-gated artifacts,
not warm certifications. The fixture hashes, recipes, artifact hashes, and both run
receipts are bundled in the
[H3 lip-sync A/B package](../results/comparisons/h3_lipsync_ab_package.json).
The corrected H3 contract includes exactly `portrait.png` and raw `tts_dialogue.wav`;
there is no second scene image or derived audio. The package freezes both hashes for
the OTR-side HuMo comparison.

The technical screen sees speaking articulation. It does not decide whether mouth
shapes truly track phonemes, settle through pauses, or remain consistent across both
seeds. Jeffrey's full-clip eyes and ears decide those questions.

The production HuMo leg is now complete through OTR's existing wrapper. HuMo 1.7B
delivered two **480x832, 129-frame, 25-fps / 5.160-second** clips in
**233.779852** and **207.513477 seconds** to artifact save, at absolute VRAM peaks of
**15.118164** and **15.231445 GiB**. HuMo 14B FP8 delivered **480x832, 97 frames at
25 fps / 3.880 seconds** in **245.943975 seconds**, at a **14.984375 GiB** peak. These
are OTR-side production-lane measurements and never receive a lab-gate `PASS`.
[HuMo 1.7B take 1](../results/otr_side/humo_1_7b_bakeoff_take1.json),
[take 2](../results/otr_side/humo_1_7b_bakeoff_take2.json), and
[HuMo 14B receipt](../results/otr_side/humo_14b_fp8_bakeoff_take1.json)

The byte-level input contract is exact, but the workload contract is not. The raw TTS
fixture is **10.000 seconds**; H3 delivers **5.167 seconds**, HuMo 1.7B delivers
**5.160 seconds**, and the production-capped HuMo 14B take delivers **3.880 seconds**.
Canvas, frame rate, and frame count also differ. HuMo's production-policy native clips
are silent, so the review copies mux the exact source audio from timestamp zero with a
video stream-copy. See the receipt-bound [five-clip review sheet](HUMO_BAKEOFF.md).

The HuMo 1.7B production probe exposes fixed request seed **7** rather than an
alternate-seed control. Its two separately executed native artifacts are byte-identical.
That is fixed-seed repeatability evidence; it does not substitute for an alternate-seed
quality test. [Take receipts](HUMO_BAKEOFF.md#five-clip-measurement-table)

All lips, onset, and identity columns remain `PENDING_HUMAN`. The historical F7 claim
of a **100-200 ms audio lead** is only a listening target: OTR's later M1 measurement
did not reproduce it and instead estimated a roughly **30-60 ms video lead**. The
five-clip decision should therefore listen for offset in either direction rather than
assume the older failure.
[OTR M1 measurement](../../custom_nodes/ComfyUI-OldTimeRadio/docs/2026-08-02-MEASUREMENT-M1-humo-lipsync-offset.md)

The earlier `defect:no_lipsync` verdict on the neutral wide-scene RefAudio clip remains
retracted. That prompt did not ask the subject to speak or synchronize. The original
clip remains valid evidence for RefAudio execution, but not for lip-sync capability.

## HuMo 1.7B VRAM diet

Phase 0 found no missing lane dependency: the production HuMo generation graph uses
ComfyUI core / `comfy_extras` classes, and the live server exposed all **14** required
classes plus the exact Whisper model. No HuMo custom-node pack or
`LAB_EXTRA_WHITELIST` extension, install, or download was needed.
[Live feasibility receipt](../results/humo_diet/phase0_lane_feasibility.json)

Phase 1 reproduced the OTR HuMo 1.7B generation settings and changed only the explicit
boot lane. Clamp-13 cold peaked at **14.21 GiB** in **223.0 seconds**. Its second
consecutive execution was a warm machine pass at **12.84 GiB** in **243.0 seconds**,
meeting the campaign's **13.5 GiB** absolute target. The later fresh-server clamp-12
probe peaked at **14.47 GiB absolute / 12.28 GiB net** in **259.8 seconds** and failed
the stricter **12 GiB** target; no unchanged `--force` repeat was attempted. The
mutable alias therefore remains run 3 `FAIL`, while immutable run 2 remains the
clamp-13 winner. [Frozen clamp-floor comparison](../results/humo_diet/phase1_clamp_floor_comparison.json)

The exact candidate launch delta is `--disable-pinned-memory` plus a lab target-card
`--clamp 13`, which produced `--reserve-vram 2.921` on the measured GPU. Every HuMo
generation node and widget remains unchanged, and the default boot remains unchanged;
OTR integration would add an explicitly selected HuMo diet variant only.
[Transcribable diff and receipts](HUMO_DIET.md#exact-otr-to-diet-settings-diff)

Phase-linked telemetry distinguishes staged size from runtime pressure. WanTE/UMT5 is
the largest staged weight at **6419 MB**, versus **3320 MB** for the HuMo DiT, but the
fresh-run overall peaks occur during HuMo denoising. The warm overall maximum occurs
during decode. The defensible diagnosis is the combined denoise/decode working set,
not DiT file size alone; text-encoder residency is not proved.
[Phase analysis](../results/humo_diet/phase1_clamp_floor_comparison.json)

Phase 2 was skipped because its levers were conditional on missing the target. No
quantized encoder swap, block swap, tiled decode, step LoRA, or canvas reduction was
introduced. The [production-vs-diet A/B](../outputs/humo_1p7b_diet_ab_production_vs_clamp13_warm.mp4)
is ready for Jeffrey's lips/onset/identity and overall-quality review. Recommendation:
retain the production graph and use the diet boot variant only after human parity and
external integration verification. [Complete diet report](HUMO_DIET.md)

## LTX Audio HQ ladder

All three one-variable rungs achieved second-consecutive warm machine passes. H1
raises only the canvas, H2 raises only the duration, and H3 composes both independently
passing changes. The full measurements and receipt hashes live in the
[HQ ladder comparison](../results/comparisons/ltx_audio_hq_ladder.json).

| Rung | Certified configuration | Warm peak | Warm wall time | Recommendation |
|---|---|---:|---:|---|
| H1 | 1024x576, 97 frames | 7.06 GiB | 248.5 s | Machine-certified option |
| H2 | 832x480, 193 frames | 7.93 GiB | 341.3 s | Machine-certified option |
| H3 | 1024x576, 193 frames | 7.36 GiB | 585.3 s | **Best machine-certified HQ configuration** |

H3 is the recipe recommended for OTR transcription, subject to Jeffrey's full-clip
eyeball. The sampled-frame contact-sheet screen found no obvious mesh, noise, or
collapse, but that technical screen is not a promotion verdict.
[HQ ladder evidence](../results/comparisons/ltx_audio_hq_ladder.json)

## WAN I2V 14B exoneration

WAN I2V 14B is viable at the OTR production floor under the corrected target-card
clamp. Its cold run peaked at **14.05 GiB** from a **2.15 GiB** baseline, a net
allocation of **11.90/12 GiB** and only **0.10 GiB** of clamp headroom. Its warm run
passed at a **13.93 GiB** peak. The complete cold/warm evidence is in the
[WAN I2V exoneration comparison](../results/comparisons/wan_i2v_14b_exoneration.json).

Recommendation: retain WAN TI2V as the safer default. I2V 14B is exonerated, but its
cold target-card margin is too tight to displace the lower-risk lane.

## H3 speed-stack and Sage findings

The proposed H3 turbo stack cannot be built from current local assets. Neither the
Kijai W4A8-mixed H3 diffusion weight nor an H3-compatible LightX2V four-step LoRA is
present. The similarly named local LightX file is a WAN I2V 14B LoRA and is
incompatible. No download was performed.
[Inventory receipt](../results/comparisons/h3_speed_stack_inventory.json)

Download proposal, intentionally blocked pending Jeffrey's authorization: acquire the
two H3 assets into quarantine, hash-pin them into `models_manifest.md`, and open a new
immutable turbo campaign. Do not retrofit or rename the local WAN LoRA.

The explicit per-model KJ Sage probe also failed on this measured Blackwell system.
It hit Windows exception `0x80000003` at sampler step zero, timed out after
**1801.5 seconds**, produced no output, and completed owned-server cleanup.
[Sage probe comparison](../results/comparisons/h3_sage_patch_probe.json)
Recommendation: never make this patch the default on the measured environment. This
failure does not authorize the known-bad global Sage boot flag either.

## LTX motion ladder

All four labeled artifacts exist. The contact-sheet technical screen reads M0, M1,
and M2 as near-still compositions; M3 shows a slow camera translation/zoom across its
longer clip. This does **not** justify the stronger finding that the lane is inherently
near-still, because Jeffrey has not yet ranked the full clips or judged beat response.
[Motion-ladder comparison](../results/comparisons/ltx_motion_ladder.json)

Recommendation: present M0-M3 together and wait for Jeffrey's ranking. Do not infer
music responsiveness from sparse frame samples.

## Unconditioned Mini Mime

The corrected Mini Mime proof has picture conditioning and model-native audio output,
with no external audio-conditioning input. It fills its real ledger slot exactly:
**192 frames at 24 fps, delivered as 8.000 seconds**. The cold machine pass peaked at
**6.71 GiB** and took **542.9 seconds**.
[Mime machine comparison](../results/comparisons/h3_mime_unconditioned.json)

Objective FFmpeg 8.0.1 audio QA found **-31.32 LUFS**, **1.00 LU** loudness range,
and a **-13.55 dBTP** true peak. It found zero continuous-silence events at the tested
`-50 dB / 0.10 s`, `-40 dB / 0.20 s`, and `-35 dB / 0.20 s` thresholds. This supports
a continuous, non-silent stream-level read at those tested thresholds; it does not prove absence of
speech/vocals or coherent diegetic synchronization.
[Mime audio QA receipt](../results/comparisons/h3_mime_audio_qa.json)

The inverted human ear gate remains pending: Jeffrey must confirm no speech-like or
vocal-like content at all, intelligible or otherwise, plus coherent diegetic sync. This is one cold
experimental proof, not a warm production promotion.

## Duration and token-budget intel

H3's grid gives **192 = 17*11+5 frames**, exactly **8.000 seconds at 24 fps**; the
duration matcher now includes that case. The feasibility formula
`(width/32) * (height/32) * video_latent_t` is scoped to output visual tokens only. It
does not include reference, audio, or text tokens and is not a VRAM predictor. Local
checks pair **14,985 output visual tokens** with a measured **6.71 GiB** peak and
**23,085 tokens** with **6.71 GiB**; no monotonic memory ceiling is inferred from two
different graphs. [Token-budget evidence](../results/comparisons/h3_token_budget_check.json)

The public report of **692x692 nominal / 192 frames in 210 seconds on an 8 GB laptop**
remains `EXTERNAL-REPORTED` commenter evidence only. Vocal separation reportedly
improves synchronization; it is not measured here. `ref_image_size` remains `match`
for the lab retest. [External-report scope and source](../results/comparisons/h3_token_budget_check.json)

## RefAudio and historical guardrails

The prior controlled RefAudio evidence remains: H3's native music output largely
reconstructed its conditioning input rather than composing a new soundtrack. The
continuation tail is the only portion outside the reference window and thus the only
portion unambiguously not within-window reconstruction; correlation does not exclude
novel detail inside the aligned window. The graph still proves this was native
joint-latent decode rather than a source-file mux. That finding is why Mini Mime was
tested with no external audio input. See [H3_REFAUDIO_EVIDENCE.md](H3_REFAUDIO_EVIDENCE.md)
and the [receipt-bound reconstruction analysis](../results/comparisons/h3_refaudio_reconstruction.json).

The canonical H3 best suite also remains a formal machine failure on its frozen creep
rule, even though its individual candidate pairs passed. Neither this close-out nor
the newer cold experiments rewrites that immutable suite history.
[Suite receipt](../results/h3_best_suite.json)

## Distribution seed 2.1

All values in this table, including source hashes, are frozen in the
[2.1 environment receipt](../results/comparisons/environment_2p1.json).

| Component | Exact pin |
|---|---|
| OS / Python | `Windows-11-10.0.26200-SP0`; `3.12.11` |
| Torch / CUDA | `2.10.0+cu130`; runtime `13.0` |
| GPU | `NVIDIA GeForce RTX 5080 Laptop GPU`; compute capability `12.0`; driver `610.88`; `16303 MiB` total |
| Attention | SageAttention `2.2.0+cu130torch2.9.0andhigher.post4`; FlashAttention-2 absent and unsupported |
| ComfyUI | `0.31.1`; commit `fe4195f7f4275f2626cbafc703acc3ddde1e5490` |
| ComfyUI-GGUF | `1.1.10`; `nodes.py` SHA-256 `16be3b08b13de6279fc432addc628320019fcb24963cbc6b52b248de8f06316e`; `pyproject.toml` SHA-256 `56e3a961454b48eaf90eab45055c6e8ccb4ec7de3ae6461064c69c2298e835fa` |
| ComfyUI-KJNodes | `1.3.9`; commit `b7646ad70a7daa7aeb919ca542274758d26ba2df`; `pyproject.toml` SHA-256 `c91028e05bc560f861eb55c3428f676a8dfc752173a11fb077ac5193f2de3c21` |
| Active custom-node whitelist | `ComfyUI-GGUF`, `ComfyUI-KJNodes` |

## Audio delivery and scope

For ordinary OTR lanes, real TTS and music remain delivery authority. Conditioning
derivatives and model-native decoded audio are diagnostics unless a lane-specific
human audition promotes them. Mini Mime is the deliberate exception under study,
which is why its inverted ear gate is mandatory.

MiniMax's written authorization remains governed by
[H3_LICENSE_GRANT.md](H3_LICENSE_GRANT.md): local, offline, non-commercial use on the
operator's own hardware, with no hosted service or weight redistribution. Nothing in
this brief expands that scope.
