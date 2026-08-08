# Escalation Notice: LTXAV Wiring / Embedding Connector Mismatch

## Issue Summary
All three attempted LTX Video 2.3 recipes (`ltx_i2v_low`, `ltx_i2v_high`, `ltx_audio_low`) fail during the sampling phase inside `comfy/ldm/lightricks/embeddings_connector.py`:

```text
RuntimeError: Sizes of tensors must match except in dimension 1. Expected size 4096 but got size 2048 for tensor number 1 in the list.
```

## Traceback Analysis
1. `CheckpointLoaderSimple` loads `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` on the server.
2. `CLIPTextEncode` passes text embeddings (`cross_attn`) into `preprocess_text_embeds`.
3. In `av_model.py` line 579, `self.audio_embeddings_connector(context_audio)` attempts to concatenate learnable registers.
4. The transformer model expects 4096-dim embeddings, but the text encoder produces 2048-dim embeddings, raising a tensor dimension mismatch.

## Status Reclassification
Per laboratory rules, these runs are reclassified as **`ERROR`** (wiring/graph fault; pre-error VRAM measurements of ~10.5–10.8 GB are non-verdictive) rather than `FAIL` (which is reserved for real renders that complete sampling but exceed the 14.5 GB VRAM gate line).

## Escalation to Claude / Opus
To resolve this for future production releases:
- Does LTX Video 2.3 FP8 transformer require a dedicated `ltx-2.3-22b-dev_embeddings_connectors.safetensors` model patcher node?
- Or should LTXAV text encoding use `CLIPLoader` with a specific LTX-3B / LTXAV clip configuration?

## 2026-08-08 — LTX T2V Texture Defect After Three Controlled Variants

The decode/scheduler factorial completed without proving external VAE tiling as
the defect source. Plain and tiled outputs from the corrected scheduler remain
close (SSIM 0.950), while plain decode costs slightly more VRAM and time. The
confirmed scheduler-latent correction materially improves motion coherence, so
the selected candidate is corrected scheduler + official tiled decode.

The selected artifact still needs Jeffrey's full-video eyeball approval. Stop
quality-knob tuning here. If it fails, the next campaign should compare the
locally available Q3 GGUF against a proven higher-precision local weight/topology
under an explicitly high-VRAM lane; do not retune decode boundaries again.
