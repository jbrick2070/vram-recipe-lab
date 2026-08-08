# LTX Recipe Widget Audit & Deviations Log

This document audits all input parameter deviations and guessed defaults between our LTX recipes (`recipes/ltx_*.json`) and the authoritative ComfyUI templates (`research/comfy_templates/video_ltx2_3_*.json`).

## Audit Summary Table

| Category | Node Class | Template Value (`video_ltx2_3_*.json`) | Recipe Value (`ltx_*.json`) | Impact / Symptom |
|---|---|---|---|---|
| **Scheduler & Sigmas** | `LTXVScheduler` vs `ManualSigmas` | `LTXVScheduler`<br>- `steps`: 20<br>- `max_shift`: 2.05<br>- `base_shift`: 0.95<br>- `stretch`: True<br>- `terminal`: 0.1 | `ManualSigmas`<br>- Hand-typed `'0.85, 0.7250, 0.4219, 0.0'` (4 steps) or `'1.0, 0.99375, ..., 0.0'` (8 steps) | **ROOT CAUSE**: Mis-matched sampling schedule causes severe latent temporal boundary artifacts (periodic flash every ~0.4s / 8 VAE frames). |
| **LoRA Injection** | `LoraLoaderModelOnly` / `LoraLoader` | No distilled LoRA injected on standard dev model path | Force-injected `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` @ strength 1.0 into dev checkpoint & GGUF paths | **ROOT CAUSE**: Distilled LoRA is tuned for specific 4/8-step distilled schedules; force-injecting it into dev model without matching schedule causes visual corruption and high VRAM overhead. |
| **Guider & CFG** | `MultimodalGuider` vs `CFGGuider` | `MultimodalGuider` (`skip_blocks: 29`) with `GuiderParameters` (`VIDEO`: cfg 3, scale 3; `AUDIO`: cfg 7, scale 3) | `CFGGuider` (`cfg: 3.0`) | Reduced multimodal audio-video alignment quality. |
| **Canvas Resolution** | `ResizeImageMaskNode` / `EmptyLTXVLatentVideo` | Production Canvas: 832x480 (or 768x512 in template default) | 1920x1088 (Full HD template default) | Extremely high VRAM usage (exceeding 14.5 GB ceiling on standard checkpoint). |
| **Frame Budget & Rate** | `EmptyLTXVLatentVideo` / `LTXVConditioning` | Production target: 25 fps, 97 frames (nearest 8n+1 grid to 3.75s beat: 8*12+1=97) | 24 fps, 121 frames | Incorrect temporal duration for 3.75s OTR audio beat. |
| **Text Encoder** | `LTXVGemmaCLIPModelLoader` vs `LTXAVTextEncoderLoader` | `LTXVGemmaCLIPModelLoader` (`max_length: 1024`) | `LTXAVTextEncoderLoader` (`text_encoder: gemma_3_12B_it_fp4_mixed.safetensors`) | Valid local model, but loader syntax differs. |
| **VAE Tile Sizes** | `VAEDecodeTiled` | `VAEDecode` or `VAEDecodeTiled` | `tile_size: 512`, `overlap: 64`, `temporal_size: 16`, `temporal_overlap: 4` | Tiled decode prevents OOM at higher resolutions. |

## Enumeration of Guessed Defaults

1. **Sigmas & Schedule**: Conversion code fell back to hardcoded string `'0.85, 0.7250, 0.4219, 0.0'` in `ManualSigmas` instead of linking `LTXVScheduler`. Replaced with `LTXVScheduler` matching template parameters (20 steps, max_shift 2.05, base_shift 0.95).
2. **Distilled LoRA**: Force-injected `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` on standard dev model runs (`_ckpt` and `_gguf`). Replaced/removed for dev model paths so dev model runs pure 20-step schedule without distilled LoRA distortion.
3. **Sampler**: Euler sampler was used correctly (`KSamplerSelect` with `euler`).
4. **CFG & Guider**: Standard `CFGGuider` was used instead of `MultimodalGuider`.
5. **Resolution**: Full HD (1920x1088) was kept from 1080p template instead of production canvas (832x480).

## Corrective Plan
- Replace `ManualSigmas` with `LTXVScheduler` (`steps: 20`, `max_shift: 2.05`, `base_shift: 0.95`, `stretch: True`, `terminal: 0.1`).
- Remove/bypass distilled LoRA force-injection for dev checkpoint (`_ckpt`) and dev GGUF (`_gguf`) recipes.
- Update contract and resolution inputs to 832x480 @ 25 fps, 97 frames (nearest 8n+1 grid to 3.75s beat).
