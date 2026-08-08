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

