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

## 2026-08-08 — LTX T2V Campaign Close-out

**Status: CLOSED — the three-attempt allowance is exhausted. No fourth LTX T2V
render, including a canonical-file rerun or warm-cache pair, is authorized in
this campaign.** This section is a human-readable evidence close-out under
`docs/LAB_COMPLETION_PLAN.md` P6. It is not a machine receipt, a warm-cache
certification, or a production promotion.

### Attempt history

| Allowed attempt | Preserved evidence | Outcome |
|---|---|---|
| 1 — baseline | `results/ltx_t2v_gguf_run1.json` and `results/ltx_t2v_gguf_run2.json` | Both completed below the VRAM gate, but both were human-labelled `defect:mesh_grid`. |
| 2 — tiled-decode retune | `results/ltx_t2v_gguf_run3.json` | Completed below the VRAM gate and again received `defect:mesh_grid`; tuning a decode boundary did not repair the texture defect. |
| 3 — controlled scheduler/decode factorial | `results/ltx_t2v_gguf_run4.json` (cell A), `results/ltx_t2v_gguf_run5.json` (cell B), and `results/ltx_t2v_gguf_run6.json` (cell C) | A (scheduler disconnected, plain decode) reached 15.03 GiB in 248.3 s and did not remove the defect. B (scheduler connected, official tiled decode) reached 15.04 GiB in 233.7 s and was selected. C (scheduler connected, plain decode) reached 15.14 GiB in 236.9 s and offered no material advantage over B (B-versus-C SSIM 0.950162). All three exceeded the 14.5 GiB gate. |

The factorial establishes two useful boundaries: connecting the scheduler's
latent input materially improves motion coherence, while replacing the official
tiled decode with plain decode does not materially improve the corrected graph
and costs slightly more time and VRAM. The selected cell is therefore **B: the
current canonical graph with corrected `scheduler.latent` wiring and official
tiled decode**.

### Selected-cell evidence and provenance

- Artifact: `outputs/ltx_t2v_gguf_b_scheduler_tiled_out_00001_.mp4`
  (SHA-256
  `728dad458f36b4b4430ac8edbcbbca17abaf03d1fabfeb7b178aff5ede000e2b`;
  2,520,799 bytes; H.264, 832×480, 25 fps, 97 frames, 3.88 s).
- Supporting run receipt: `results/ltx_t2v_gguf_run5.json` (receipt-file
  SHA-256
  `2da0ae35e03d26aaebff0ca71a4d6b31e50e568b0868bd0e257aef07d0f7f72d`).
  It records boot lane `lab-8199, sage-free`, an unreserved 15.04 GiB peak,
  2.71 GiB baseline, 233.7 s duration, one configuration run, a failed VRAM
  gate, and `eyeball: pending`. Its server arguments contain no
  `--reserve-vram` option.
- The preserved run-5 receipt records executable recipe SHA-256
  `5811a55dcbe5499d201c1db3ae174932444c7bb1e22567f105ea70fa0c6c84b0`.
  The transient recipe JSON with those exact bytes was not preserved, so its
  byte-level content cannot be reconstructed from the repository.
- Current canonical recipe: `recipes/ltx_t2v_gguf.json` (exact current-file
  SHA-256
  `6e5d89265fcd83b0192fd98457c43de9bb088dd290c691c33e80092450473826`).
  It selects cell B, but it was canonicalized after run 5 and has not been
  rendered under this exact SHA. The differing hashes must not be treated as an
  identical-run or warm-cache pair.
- Current alias receipt: `results/ltx_t2v_gguf.json` (SHA-256
  `7820d2b6d297424d6d41c928fcdd8dc33fc927fe83db09d8245e63c29a39db81`)
  correctly marks the selection stale because the latest execution was cell C,
  while the current recipe selects B.

Jeffrey's full-video eyeball verdict on the selected B artifact remains
pending. That review may classify the already-rendered artifact, but it does not
authorize another render and cannot convert this result into a warm-cache PASS:
cell B exceeded the VRAM ceiling and has only one configuration run.

### Stop decision

Stop because the authorized attempt budget is spent, the selected graph exceeds
the lab gate, the plain-decode hypothesis was disproved, and no remaining
official-topology change is sanctioned by this campaign. Continuing with knob
tuning would blur the causal result and could falsely imply certification. Any
future higher-precision or alternative-weight comparison must begin as a
separately authorized campaign with a new immutable recipe and its own receipts;
it is not attempt 4 of this campaign.
