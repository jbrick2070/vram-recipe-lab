# Recipe Failure Diagnostics — LTX-Video & Wan-Video Suite

## Context & Invariants
- Platform: Windows 11, RTX 5080 Laptop (16 GB physical VRAM, 14.5 GB strict lab ceiling)
- Torch 2.10.0 + CUDA 13.0 + SageAttention + SDPA
- Hardware VRAM Ceiling: 14.5 GB max peak across all runs
- Boot Lane: headless ComfyUI on port 8199 (`boot_lab_server.cmd`)

## Issue 1: `ltx_i2v_low` & `ltx_i2v_high` Execution Error
Executing `ltx_i2v_low` triggers a RuntimeError inside KSampler (Node 8):
```
RuntimeError: Sizes of tensors must match except in dimension 1. Expected size 4096 but got size 2048 for tensor number 1 in the list.
Traceback:
  File "comfy/ldm/lightricks/av_model.py", line 579, in preprocess_text_embeds
    out_audio = self.audio_embeddings_connector(context_audio)[0]
  File "comfy/ldm/lightricks/embeddings_connector.py", line 286, in forward
    hidden_states = torch.cat((hidden_states, learnable_registers[hidden_states.shape[1]:].unsqueeze(0).repeat(hidden_states.shape[0], 1, 1)), dim=1)
```
Questions:
1. Is LTX-Video requiring a specific text encoder / clip model or audio embedding dimension?
2. Are the dimensions of conditioning tensors from `CLIPTextEncode` or `LTXVConditioning` mismatched with what `ltx-video-2.0` expected?

## Issue 2: `wan_ti2v_high` & `wan_i2v_14b_low/high` Preflight #7 Block (VRAM Ceiling)
`run_recipe.py` Preflight Check #7 (Affordability Check) refuses to run recipes whose recorded `peak_vram_gb` in `results/<recipe>.json` exceeded 14.5 GB:
- `wan_ti2v_high`: last measured peak = 15.55 GB
- `wan_i2v_14b_low`: last measured peak = 15.28 GB
- `wan_i2v_14b_high`: last measured peak = 15.34 GB

Questions:
1. Can the 14B Wan recipes or 5B Q5 recipe be optimized (e.g. lowering resolution, frame count, or block swapping) to bring peak VRAM strictly <= 14.5 GB?
2. How should `results/*.json` or recipe parameters be updated so preflight can re-test modified configurations?
