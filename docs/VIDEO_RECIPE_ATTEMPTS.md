# Video Recipe Attempts Log

This document logs all rendering attempts, parameter changes, measured VRAM performance, and eyeball verification verdicts for video recipes in `vram-recipe-lab`.

## Attempt Log

### Attempt #1: Production Canvas Retune & Widget-Fidelity Fix for `ltx_audio`
- **Date**: 2026-08-08
- **Target Recipes**: `ltx_audio_ckpt` & `ltx_audio_gguf`
- **Canvas Resolution**: 832x480, 25 fps, 97 frames (nearest 8n+1 grid to 3.75 s beat = 8 * 12 + 1 = 97)
- **Changes Made**:
  1. **Widget-Fidelity Audit & Distilled LoRA Removal**: Removed force-injected distilled LoRA (`ltx-2.3-22b-distilled-lora-384-1.1.safetensors` @ 1.0) and force-injected 2-stage upscaler (`LTXVLatentUpsampler`).
  2. **Scheduler & Sampler Alignment**: Replaced hardcoded 4-step `ManualSigmas` with official `LTXVScheduler` (`steps: 20`, `max_shift: 2.05`, `base_shift: 0.95`, `stretch: True`, `terminal: 0.1`) matching template `video_ltx2_3_ia2v.json`.
  3. **Production Canvas Re-parameterization**: Retuned resolution from 1920x1088 to 832x480 at 25 fps, 97 frames.
  4. **Standalone VAE Loading for GGUF**: Updated `ltx_audio_gguf` to load `ltx-2.3-22b-dev_video_vae.safetensors` via `VAELoader` to avoid staging unquantized 22B checkpoint weights.

- **Benchmark Results**:
  - `ltx_audio_ckpt` (Safetensors dev checkpoint @ 832x480):
    - Baseline VRAM: 1.34 GB | Peak VRAM: 15.34 GB | Wall Clock: 209.5 s
    - Boot Lane: `lab-8199, sage-free`
    - Status: `FAIL (VRAM 15.34 GB > 14.5 GB)` — standard safetensors checkpoint exceeds 14.5 GB physical VRAM ceiling.
  - `ltx_audio_gguf` (GGUF Q3 + Standalone VAE @ 832x480):
    - Baseline VRAM: 1.39 GB | Peak VRAM: 7.41 GB (Net VRAM: 6.02 GB) | Wall Clock: 261.9 s
    - Boot Lane: `lab-8199, sage-free, clamp-14gb`
    - Status: **`PASS` (Warm Cache Certified - 2 consecutive passes)**
    - Generated Video: [`outputs/ltx_audio_gguf_out_00001_.mp4`](../outputs/ltx_audio_gguf_out_00001_.mp4)

- **Eyeball Verdict**: Pending Jeffrey's eyeball review of generated video [`outputs/ltx_audio_gguf_out_00001_.mp4`](../outputs/ltx_audio_gguf_out_00001_.mp4) to confirm whether removing the distilled LoRA and using 20-step `LTXVScheduler` eliminated the periodic flash defect (~every 0.4s).

### Attempt #2: T2V Mesh Grid Defect Audit & Fix (`ltx_t2v_gguf`)
- **Date**: 2026-08-08
- **Target Recipe**: `ltx_t2v_gguf`
- **Issue**: Regular lattice/mesh grid over textures (e.g. hillside) in rendered clip [`outputs/ltx_t2v_gguf_out_00001_.mp4`](../outputs/ltx_t2v_gguf_out_00001_.mp4) (`eyeball: defect:mesh_grid`).
- **Node-by-Node Diff Audit**:
  1. **Suspect (a) - Tiled VAE Decode Settings (`VAEDecodeTiled`)**:
     - `ltx_t2v_gguf.json` used `tile_size: 512`, `overlap: 64`, `temporal_size: 16`, `temporal_overlap: 4`.
     - On an 832x480 canvas, `tile_size: 512` forces a vertical spatial seam down the center (x=320..512), and `temporal_size: 16` (only 2 latent frames per temporal tile) forces temporal decoding chunking every 16 frames (0.4s). Together, spatial + temporal chunking creates a periodic 3D lattice mesh grid over textures.
     - Template `video_ltx2_3_t2v.json` uses `tile_size: 768`, `overlap: 64`, `temporal_size: 4096` (no temporal chunking), `temporal_overlap: 4`.
  2. **Suspect (b) - Missing T2V Canvas Image Conditioning (`LTXVImgToVideoInplace`)**:
     - `ltx_i2v_gguf.json` (which passed eyeball with zero mesh artifacts) feeds an input image through `ResizeImageMaskNode` -> `LTXVPreprocess` -> `LTXVImgToVideoInplace` (strength: 1.0) into `EmptyLTXVLatentVideo`.
     - `ltx_t2v_gguf.json` omitted nodes 13-16, passing raw unconditioned `EmptyLTXVLatentVideo` to diffusion sampling.
     - Template `video_ltx2_3_t2v.json` includes `EmptyImage` (512x512) -> `ResizeImageMaskNode` -> `LTXVPreprocess` (compression: 18) -> `LTXVImgToVideoInplace` (strength: 1.0).
  3. **Suspect (c) - Sampler/Scheduler**:
     - Sampler (`euler`) and `LTXVScheduler` (20 steps) match between `ltx_i2v_gguf` and `ltx_t2v_gguf`.

- **Planned Fix**:
  1. Re-align `VAEDecodeTiled` in `ltx_t2v_gguf.json` to `tile_size: 768`, `overlap: 64`, `temporal_size: 4096`, `temporal_overlap: 4` (matching template Node 251).
  2. Add `EmptyImage` (832x480) -> `ResizeImageMaskNode` (832x480, lanczos) -> `LTXVPreprocess` (compression: 18) -> `LTXVImgToVideoInplace` (strength: 1.0) to `ltx_t2v_gguf.json` matching clean `ltx_i2v_gguf` graph structure and template `video_ltx2_3_t2v.json`.

### Attempt #3: Standard-Topology Controlled Campaign

- **Date**: 2026-08-08
- **Correction to Attempt #2**: the planned EmptyImage/canvas-guide path was not actually implemented in the Attempt #2 artifact. More importantly, every local LTX recipe omitted the optional `LTXVScheduler.latent` edge. At 97 frames and 832x480, omission makes core ComfyUI assume 4,096 tokens instead of the actual 5,070-token latent.
- **LTX T2V factorial**, same model/seed/prompt/canvas/encoder:
  - A, decode only: scheduler disconnected + plain decode. 15.03 GB, 248.3 s, 24,099 video bytes/frame. Plain decode did not remove the texture issue and failed the 14.5 GB gate.
  - B, scheduler only: scheduler connected to the official pre-sampler combined AV latent + tiled decode 768/64/4096/4. 15.04 GB, 233.7 s, 25,304 video bytes/frame. Vehicle motion became coherent through the clip.
  - C, combined: corrected scheduler + plain decode. 15.14 GB, 236.9 s, 25,542 video bytes/frame. B-vs-C SSIM was 0.950; plain decode showed no material quality advantage and cost slightly more time/VRAM.
- **Selection**: keep tiled decode and connect `LTXVScheduler.latent`. The unreserved 16 GB artifacts are useful high-VRAM diagnostics but do not pass the 14.5 GB production gate. Human eyeball remains pending on B.

### H3 I2V: Official Sampler Alignment

- The still was already wired and active; the failed recipe also already used plain `VAEDecode`.
- Replaced legacy `KSampler(euler, CFG 6, negative conditioning)` with the frozen official topology: `RandomNoise`, `res_multistep`, `BasicScheduler(simple, 20, denoise=1)`, `BasicGuider`, and `SamplerCustomAdvanced`.
- Legacy artifact: pink-dot corruption, 28,080 video bytes/frame, mean frame delta 41.121.
- Corrected artifact: coherent through the final frame, 5,246 video bytes/frame, mean frame delta 9.171, frame-zero SSIM 0.847 / PSNR 29.00 dB against the node-resized still.
- Two consecutive corrected renders were byte-identical (`9908f357...`) and passed the machine/VRAM gate at 7.07/7.15 GB. Machine warm-cache status: **PASS**; promotion remains pending Jeffrey's full-video eyeball under the H3 human-review rule. The second full run took 239.5 s with Legion performance mode active.

### LTX IA2V: Static Interstitial vs Music (Speech Interpretation Superseded)

- Corrected audio guide mask from 1.0 to the official frozen-guide value 0.0 and connected the scheduler latent.
- Fixture-truth correction: the input then named `narration.wav` was later identified by Jeffrey as the episode static interstitial with near-zero intelligible speech. It is now `interstitial_static.wav`; see `docs/AUDIO_FIXTURE_CORRECTIONS.md`.
- Input preservation check: aligned waveform correlation is only 0.055 because the Audio VAE reconstructs phase, but log-spectral correlation with the static interstitial is 0.790 versus 0.066 for the old mask-1 output. Mask 0 therefore preserves conditioning content but not an authoritative waveform.
- Frozen real-OTR controls, same still/seed/prompt/trim:
  - static interstitial control: mean frame delta 0.09349; 1,606 video bytes/frame
  - music raw: 0.10704; 1,683 video bytes/frame
  - music -12 dB: 0.11583; 1,757 video bytes/frame
- Both music conditions differed from the static control, including after the recorded level adjustment. The response is subtle, but this evidence does not compare music with speech and does not establish speech-conditioning behavior.
- **Production policy**: use real TTS/music to condition motion, discard VAE-reconstructed audio, and externally mux the untouched source track. Generated model audio, if ever retained, is a separately screened ambience/SFX stem and must never replace narration.
- The historical static-control recipe was then run twice unchanged on the direct `reserve-12gb` lane. It passed cold at 9.06 GB / 197.1 s and warm at 8.55 GB / 185.1 s. Both MP4s are byte-identical (`76134eb5...`), their video stream exactly matches the earlier static-control diagnostic, and decoded source-vs-mux audio PSNR is 169.663 dB. That pair remains valid machine evidence for its historical identity, not speech evidence.
- **Conclusion superseded**: no speech-versus-music conclusion survives this fixture correction. A new four-condition, loudness-matched matrix using static, verified TTS dialogue, opening music, and closing music is required; all four clips remain pending eyeball and ear review.

### LTX IA2V: Four-Condition Matrix Execution

- The corrected matrix was subsequently rendered exactly once per cell, in the
  prescribed order, on one `lab-8199, sage-free, reserve-12gb` server instance.
  Every diagnostic artifact contains 97 frames and valid 3.88-second video and
  audio streams. These are intentionally cold experimental results, not warm
  certifications.

| condition | peak / baseline VRAM | wall clock | machine result |
|---|---|---|---|
| static interstitial control | 9.25 / 2.59 GB | 213.7 s | cold gate pass |
| verified TTS dialogue | 7.82 / 2.97 GB | 181.3 s | cold gate pass |
| opening music | 7.73 / 3.14 GB | 185.3 s | cold gate pass |
| closing music | 7.89 / 2.87 GB | 189.3 s | cold gate pass |

- Each cell also has a passing source-delivery mux receipt. Those previews copy the
  exact diagnostic video stream and mux the untouched source fixture; they do not
  replace the loudness-matched conditioning diagnostic as the experiment of record.
- All four human eyeball/ear comparisons remain pending. The unresolved question is
  whether motion character changes with static, speech, opening music, and closing
  music. No second matrix render is authorized by this exactly-once experiment.

### H3 I2V: Last-Frame Continuation Chain

- Tested a three-clip chain using the corrected official H3 sampler stack. Each next clip receives the prior encoded clip's final frame through `MiniMaxH3ImageToVideo.first_frame`; the continuation prompt explicitly asks for the same camera direction, room, lighting, lens, and scale.
- Clip 1 is the byte-identical machine warm-pass H3 I2V artifact; human promotion remains pending. Clip 2 used seed 43 and clip 3 used seed 44 so the sequence advances instead of reproducing the same motion.
- Clip 1 -> 2 seam: SSIM 0.816250 / PSNR 31.58 dB between the prior final frame and next first frame.
- Clip 2 -> 3 seam: SSIM 0.900289 / PSNR 33.45 dB. Contact-sheet review shows a coherent rightward glide from the control-room operators into the analog meter wall with no flash, cut, or corruption.
- Clip 2 measured 7.06 GB peak and 246.1 s; clip 3 measured 6.80 GB and 252.3 s. Both were valid cold passes on the direct `reserve-12gb` lane. They are intentionally different recipe identities, so they are not a two-run warm certification pair.
- Assembly removes frame zero from clips 2 and 3 to avoid holding the handoff frame twice. The resulting sequence is 370 frames / 15.417 s at 24 fps.
- Preview policy follows the audio finding: the model clips remain silent. `h3_multiclip_1_to_3_music_mux.mp4` uses the real frozen music excerpt, while the historically named `h3_multiclip_1_to_3_otr_mix.mp4` uses that music at -12 dB plus the untouched static interstitial beginning at the clip-2 boundary. It does not contain narration; the visual continuation evidence is unaffected.
- This proves last-frame chaining is viable for controlled pans and environmental shots. It does not prove identity lock for faces, fast action, or arbitrary scene changes; those need their own seam campaign.

### H3 R2V: V3 Dotted-Socket Correction and Supersession

- The earlier 492 KB clip that Jeffrey marked visually `ok` remains invalid R2V
  evidence: it loaded the FL2VA UNET and omitted the required `<Picture 1>` prompt
  assignment. Its historical visual verdict remains in the immutable run-2 receipt,
  but it is not R2V certification.
- Runs 3/4, previously described here as a corrected warm pair, used the obsolete
  nested-container encoding for a `COMFY_AUTOGROW_V3` image input. Optional V3 inputs
  fail silently when encoded that way, so their byte-identical artifact and generated
  audio measurements are superseded as Ref2VA evidence. The receipts remain immutable,
  but the former warm-pass interpretation is withdrawn.
- Current `h3_r2v_low` run 5 uses the installed V3 API spelling
  `ref_images.ref_image_0`, Ref2VA weights, `<Picture 1>`, the official sampler stack,
  and native joint video/audio decode. It is a valid **cold-only** machine gate pass at
  7.20 GB peak / 2.84 GB baseline in 260.6 s. Human video/audio review remains pending;
  it is not a warm pair or a promotion.
- The current `h3_r2v_best` R0/R1 receipts likewise use the flat dotted V3 socket and
  form a valid individual cold/warm pair. That pair supersedes the older best-recipe
  socket evidence, but remains human-pending and does not override the overall H3 suite
  failure below.
- The old audition-only previews remain historical static/music mixes, not narration,
  dialogue, or current dotted-socket Ref2VA evidence. No generated H3 stem is approved
  for delivery without a separate human audition.

### H3 Best Suite: Child Passes, Overall Machine Failure

- The newest canonical sequence completed all 11 children on one
  `lab-8199, sage-free, no-pinned, cache-classic, reserve-12gb` server. Every child
  cleared its own media, provenance, execution, and 14.5 GB gate; T0/T1, I0/I1, and
  R0/R1 are valid individual cold/warm recipe pairs.
- The overall receipt remains **`MACHINE SUITE FAIL`**. T1 rose from 8.81 GB at T0 to
  9.14 GB, an absolute-peak increase of 0.330 GiB against the 0.250 GiB creep limit.
- The immutable receipt also preserves the broader net-peak failure list emitted at
  run time. The corrected policy no longer compares net peak across cache-classic
  children whose resident pre-run baselines differ, so those net deltas are diagnostic
  rather than formal failures. The T1 absolute-peak failure remains and is sufficient
  to keep the suite failed.
- Human video and native-audio review is pending for every H3 best artifact. Individual
  warm evidence must not be summarized as an overall suite pass or promotion.

### H3 RefAudio: TTS and Opening-Music Cold Cells

- **Retraction (2026-08-08):** the earlier `defect:no_lipsync` conclusion from
  `h3_r2v_refaudio_tts_dialogue` was not a valid capability test. That recipe defined
  the `<Picture 1>` and `<Audio 1>` references, but its neutral wide-scene prompt did
  not instruct the subject to speak, articulate, or synchronize mouth motion. A public
  [Skill Destiny 8 GB Ref2VA demonstration](https://www.youtube.com/watch?v=qc5C4P_5p6o)
  (**EXTERNAL-REPORTED**) challenged the omission; the exact prompt-only action wording
  used in this lab came from Jeffrey's consolidated order, not a quoted public prompt.
  The lab therefore preserves the original
  clip's valid media/VRAM evidence but replaces the dialogue verdict with
  **UNTESTED - prompt did not request lip-sync**. Only a prompt-only retest may decide
  whether H3 is a character-lane candidate.

- Exactly one `h3_r2v_refaudio_tts_dialogue` smoke was rendered. It is a cold-only
  machine gate pass at 7.15 GB peak / 2.46 GB baseline in 249.0 s, with valid
  124-frame video and native generated audio over 5.167 seconds.
- Objective image-conditioning checks are strong. This establishes that the corrected
  V3 dotted image-reference path is active; it is not a human quality verdict and does
  not by itself prove useful audio-reference behavior.
- The model-native generated soundtrack measures -21.4 LUFS. Human eye/ear review is
  still required for identity quality, intelligibility, synchronization, unwanted
  vocals/noise, and whether the TTS reference had a useful behavioral effect.
- Exactly one matching `h3_r2v_refaudio_music_opening` cell then rendered at
  7.18 GB peak / 2.46 GB baseline in 249.0 s. It also contains valid 124-frame,
  5.167-second native A/V; its soundtrack measures -23.1 LUFS.
- The first 3.88 seconds of the native music output strongly reconstruct the matched
  reference. The original approximately-0.94 result is confirmed by a receipt-bound
  PCM recheck at waveform r=0.969528 and block-RMS-envelope r=0.964007, without any
  source-to-`CreateVideo` mux path. Evidence:
  `results/comparisons/h3_refaudio_reconstruction.json`.
- Objective video analysis did not demonstrate beat-synchronized motion. The first
  TTS clip contains subtle mouth motion, but because its prompt did not request a
  speaking performance it is not valid lip-sync evidence in either direction.
- Static control remains unrendered. Both completed cells are cold experimental
  evidence, not warm certifications or promotion claims.

### H3 Mini Mime: One I2V Proof

- Exactly one `h3_mime_i2v` clip was rendered at 7.28 GB peak / 2.52 GB baseline in
  178.9 s. The artifact is exactly 90 frames and 3.750 seconds with valid native H3
  audio measuring -27.5 LUFS.
- This is cold-only experimental evidence. Jeffrey explicitly approved continuing to
  one R2V mime after reviewing the I2V clip. The formal I2V receipt fields still need
  his one-line soundscape description; that detail is not inferred from objective QA.
- The single authorized `h3_mime_r2v` follow-up then passed its cold machine gate at
  7.23 GB peak / 2.61 GB baseline in 188.3 s. It is also exactly 90 frames and
  3.750 seconds. Representative frames show strong portrait identity stability with
  no obvious sampled collapse; the native soundtrack is very quiet at about
  -40.5 LUFS.
- R2V human eye/ear review remains pending. No more mime variants are authorized, and
  neither cold artifact is warm-certified or promoted.

### H3 Topology Scope

- I2V and R2V now follow the frozen official sampler bundle. The already human-approved H3 T2V low lane intentionally remains the legacy Euler/CFG-6 control; changing it would create a new campaign rather than preserve the approved baseline.
- All three H3 `*_best` recipes now have valid individual cold/warm machine pairs from
  the canonical suite. R2V's current evidence uses the required V3 flat dotted socket.
  The overall suite nevertheless remains **MACHINE SUITE FAIL** on the T1 absolute-peak
  creep gate, and every best artifact remains human video/audio pending. Individual
  child passes are not an overall certification.
- Continuation run 1 predates full embedded fixture/runner provenance and its exact transient recipe JSON was not preserved; run 2/current represents clip 3. Future continuation hops must use immutable recipe names instead of mutating one experiment file.

### Attempt #4: Consolidated Same-Canvas, Character, HQ, and Mime Close-Out

#### Normalized general-video crown

- WAN TI2V 5B and LTX Video distilled 2B rendered the same **832x480 / 193-frame /
  25-fps / 7.72-second** workload on second-consecutive true executions. LTX completed
  in **13.8 seconds** versus WAN's **407.5 seconds**, a **29.528986x** warm wall-clock
  advantage. Normalized throughput was **5.585252 versus 0.189145
  megapixel-frames/second**. Evidence:
  `results/comparisons/general_video_speed_pair.json`.
- The separately reported **20.3-second / 25-frame** and **83.8-second / 193-frame**
  LTX rows lack canvas, steps, and exact model information. They are recorded as
  `UNNORMALIZED` and excluded from the crown. Evidence:
  `results/comparisons/general_video_speed_pair.json`.

#### H3 lip-sync retest after retraction

- The earlier no-lipsync finding remains retracted for the reason recorded above: the
  original wide-scene prompt did not request speech articulation.
- The final exact-fixture speaking retest produced two cold machine-gated takes. Seed
  42 used **305.3 seconds / 6.71 GiB peak**; seed 43 used **297.8 seconds / 6.51 GiB peak**.
  Both artifact and fixture hashes are frozen in
  `results/comparisons/h3_lipsync_ab_package.json`.
- The technical visual screen sees articulation, but actual phoneme synchronization,
  pause settling, and cross-seed consistency remain pending Jeffrey's full-clip
  judgment. HuMo was not run in this lab; its wrapper is outside the whitelist. The
  OTR-side HuMo leg remains the open character-lane decision. The corrected H3 package
  uses exactly `portrait.png` and raw `tts_dialogue.wav`, with no second image or
  derived audio; both fixture hashes are frozen for the OTR comparison.

#### LTX Audio HQ ladder

- H1 canvas-only, H2 duration-only, and composed H3 all completed valid warm pairs.
  H3 at **1024x576 / 193 frames** is the best machine-certified HQ recommendation;
  Jeffrey's full-clip eyeball remains pending. Evidence:
  `results/comparisons/ltx_audio_hq_ladder.json`.

#### WAN I2V 14B exoneration

- The corrected target-card test passed cold and warm at the OTR production floor.
  Cold net allocation was **11.90/12 GiB**, leaving **0.10 GiB** clamp headroom.
  WAN I2V 14B is exonerated, but WAN TI2V remains the safer default recommendation.
  Evidence: `results/comparisons/wan_i2v_14b_exoneration.json`.

#### H3 speed-stack inventory and Sage stop

- The required H3 W4A8-mixed weight and H3 four-step LightX2V LoRA are both absent.
  The turbo variant is `BLOCKED`; no download occurred. The similarly named local
  LoRA is for WAN I2V 14B and was not repurposed. Evidence:
  `results/comparisons/h3_speed_stack_inventory.json`.
- The explicit KJ per-model Sage probe failed at sampler step zero with Windows
  exception `0x80000003`, timed out after **1801.5 seconds**, produced no output, and
  proved owned-server cleanup. It must never be the default on the measured sm_120
  environment. Evidence: `results/comparisons/h3_sage_patch_probe.json`.

#### LTX Audio motion ladder

- M0-M3 all produced labeled cold artifacts. The contact-sheet technical screen reads
  M0/M1/M2 as near-still and M3 as a slow camera move. Jeffrey's ranking and
  beat-response judgment remain pending, so the stronger "inherently near-still"
  conclusion is not recorded. Evidence: `results/comparisons/ltx_motion_ladder.json`.

#### Corrected unconditioned Mini Mime

- The final Mime experiment is separate from the earlier short proofs. It removes all
  external audio conditioning, binds a real ledger slot, and delivered exactly
  **192 frames / 8.000 seconds** with native sampled audio. It is one cold machine
  pass, not a warm certification. Evidence:
  `results/comparisons/h3_mime_unconditioned.json`.
- Objective FFmpeg QA found a continuous native audio stream at **-31.32 LUFS** with
  **1.00 LU** loudness range and **-13.55 dBTP** true peak. This does not answer the
  human questions of whether any speech-like/vocal-like content is present (intelligible
  or otherwise) or whether diegetic synchronization is coherent. Evidence:
  `results/comparisons/h3_mime_audio_qa.json`.

#### External intel boundaries

- The duration matcher now includes **192 = 17*11+5 frames = 8.000 seconds at
  24 fps**. The token formula is output-visual-token feasibility only, not a VRAM
  predictor. Evidence: `results/comparisons/h3_token_budget_check.json`.
- The public **692x692 / 192-frame / 210-second / 8 GB** result and vocal-separation
  advice remain `EXTERNAL-REPORTED`; neither is a local measurement. Reference image
  sizing stays `match`. Evidence: `results/comparisons/h3_token_budget_check.json`.
