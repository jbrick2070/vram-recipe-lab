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
    - Generated Video: [`outputs/ltx_audio_gguf_out_00001_.mp4`](file:///c:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/outputs/ltx_audio_gguf_out_00001_.mp4)

- **Eyeball Verdict**: Pending Jeffrey's eyeball review of generated video [`outputs/ltx_audio_gguf_out_00001_.mp4`](file:///c:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/outputs/ltx_audio_gguf_out_00001_.mp4) to confirm whether removing the distilled LoRA and using 20-step `LTXVScheduler` eliminated the periodic flash defect (~every 0.4s).

### Attempt #2: T2V Mesh Grid Defect Audit & Fix (`ltx_t2v_gguf`)
- **Date**: 2026-08-08
- **Target Recipe**: `ltx_t2v_gguf`
- **Issue**: Regular lattice/mesh grid over textures (e.g. hillside) in rendered clip [`outputs/ltx_t2v_gguf_out_00001_.mp4`](file:///c:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/outputs/ltx_t2v_gguf_out_00001_.mp4) (`eyeball: defect:mesh_grid`).
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

### LTX IA2V: Speech vs Music Behavior

- Corrected audio guide mask from 1.0 to the official frozen-guide value 0.0 and connected the scheduler latent.
- Input preservation check: aligned waveform correlation is only 0.055 because the Audio VAE reconstructs phase, but log-spectral correlation with narration is 0.790 versus 0.066 for the old mask-1 output. Mask 0 therefore preserves conditioning content but not an authoritative waveform.
- Frozen real-OTR controls, same still/seed/prompt/trim:
  - speech: mean frame delta 0.09349; 1,606 video bytes/frame
  - music raw: 0.10704; 1,683 video bytes/frame
  - music -12 dB: 0.11583; 1,757 video bytes/frame
- Both music conditions differed from speech, including after removing the measured ~12.1 LU level gap. The response is subtle but not explained by loudness alone.
- **Production policy**: use real TTS/music to condition motion, discard VAE-reconstructed audio, and externally mux the untouched source track. Generated model audio, if ever retained, is a separately screened ambience/SFX stem and must never replace narration.
- The selected canonical speech recipe was then run twice unchanged on the direct `reserve-12gb` lane. It passed cold at 9.06 GB / 197.1 s and warm at 8.55 GB / 185.1 s. Both MP4s are byte-identical (`76134eb5...`), their video stream exactly matches the earlier speech-conditioning diagnostic, and decoded source-vs-mux audio PSNR is 169.663 dB. Warm-cache status: **PASS**.

### H3 I2V: Last-Frame Continuation Chain

- Tested a three-clip chain using the corrected official H3 sampler stack. Each next clip receives the prior encoded clip's final frame through `MiniMaxH3ImageToVideo.first_frame`; the continuation prompt explicitly asks for the same camera direction, room, lighting, lens, and scale.
- Clip 1 is the byte-identical machine warm-pass H3 I2V artifact; human promotion remains pending. Clip 2 used seed 43 and clip 3 used seed 44 so the sequence advances instead of reproducing the same motion.
- Clip 1 -> 2 seam: SSIM 0.816250 / PSNR 31.58 dB between the prior final frame and next first frame.
- Clip 2 -> 3 seam: SSIM 0.900289 / PSNR 33.45 dB. Contact-sheet review shows a coherent rightward glide from the control-room operators into the analog meter wall with no flash, cut, or corruption.
- Clip 2 measured 7.06 GB peak and 246.1 s; clip 3 measured 6.80 GB and 252.3 s. Both were valid cold passes on the direct `reserve-12gb` lane. They are intentionally different recipe identities, so they are not a two-run warm certification pair.
- Assembly removes frame zero from clips 2 and 3 to avoid holding the handoff frame twice. The resulting sequence is 370 frames / 15.417 s at 24 fps.
- Preview policy follows the audio finding: the model clips remain silent. `h3_multiclip_1_to_3_music_mux.mp4` uses the real frozen music excerpt, while `h3_multiclip_1_to_3_otr_mix.mp4` uses that real music at -12 dB plus the untouched real narration beginning at the clip-2 boundary. No generated vocals are used.
- This proves last-frame chaining is viable for controlled pans and environmental shots. It does not prove identity lock for faces, fast action, or arbitrary scene changes; those need their own seam campaign.

### H3 R2V: Correct Ref2VA and Generated-Audio Check

- The earlier 492 KB clip that Jeffrey marked visually `ok` was not valid R2V evidence: it loaded the FL2VA UNET and omitted the required `<Picture 1>` prompt assignment. Its visual verdict is retained in the run-2 receipt, but its R2V certification is revoked.
- Corrected `h3_r2v_low` to the installed official topology: Ref2VA weights, explicit `<Picture 1>` identity assignment, official `res_multistep`/`simple`-20 sampler stack, video decode, and separate joint-latent audio decode.
- The corrected clip keeps the supplied portrait identity and facial geometry stable across the full camera move. Two consecutive renders are byte-identical (`f8ae5635...`). Cold: 6.73 GB / 208.1 s. Warm: 6.56 GB / 206.6 s. Machine warm-cache status: **PASS**; human video/audio approval is still pending.
- Generated audio is present at -32.7 dB mean / -14.3 dB peak. Its spectrogram contains broadband and harmonic structure, so metrics alone cannot rule out speech-like or vocal-like material. Treat it as an unknown, audition-required model stem, not as approved ambience.
- Two audition-only previews preserve the real OTR sources: `h3_r2v_otr_source_mix.mp4` uses real narration plus real music; `h3_r2v_otr_source_mix_with_generated_stem_AUDITION_ONLY.mp4` adds the H3 stem at -6 dB beneath that source mix. The second file is explicitly quarantined from delivery until Jeffrey confirms there is no unwanted speech/vocal content.

### H3 Topology Scope

- I2V and R2V now follow the frozen official sampler bundle. The already human-approved H3 T2V low lane intentionally remains the legacy Euler/CFG-6 control; changing it would create a new campaign rather than preserve the approved baseline.
- All three H3 `*_best` recipes remain **UNMEASURED/PENDING**, not certified high-resolution recipes. I2V/R2V contain the corrected official topology; T2V intentionally preserves the legacy control topology.
- Continuation run 1 predates full embedded fixture/runner provenance and its exact transient recipe JSON was not preserved; run 2/current represents clip 3. Future continuation hops must use immutable recipe names instead of mutating one experiment file.
