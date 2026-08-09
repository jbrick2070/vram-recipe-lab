# Promotion Brief

Date: 2026-08-09

## Executive verdict

The machine campaign is complete, but no pending human decision is silently promoted.
The strongest immediate recommendation is the LTX distilled video lane for sprint work:
on the normalized same-canvas warm pair it rendered the identical workload
**29.528986x faster** than WAN TI2V. The character lane remains the only open casting
decision: H3 now has two technically valid speaking takes with visible articulation,
but Jeffrey still needs to judge actual synchronization and seed-to-seed consistency
against HuMo on the OTR side.

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
| Workhorse lips | **H3 Ref2VA candidate**, conditional on the OTR-side A/B | Two cold machine-gated speaking takes show articulation, but exact phoneme sync, pause settling, and consistency remain human-pending. [Two-take H3 package](../results/comparisons/h3_lipsync_ab_package.json) |
| Hero lips | **HuMo incumbent** until the exact-fixture OTR A/B says otherwise | HuMo was deliberately not run in this lab because its wrapper is outside the whitelist. The corrected H3 package uses exactly `portrait.png` plus raw `tts_dialogue.wav`. [H3 lab-half package](../results/comparisons/h3_lipsync_ab_package.json) |

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

## Character-lane decider: H3 lab half complete

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
seeds. Jeffrey's full-clip eyes and ears decide those questions. HuMo must be rendered
and compared OTR-side using the documented fixture hashes; it was not attempted here.

The earlier `defect:no_lipsync` verdict on the neutral wide-scene RefAudio clip remains
retracted. That prompt did not ask the subject to speak or synchronize. The original
clip remains valid evidence for RefAudio execution, but not for lip-sync capability.

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
