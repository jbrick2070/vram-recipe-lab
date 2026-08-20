# What actually runs: LTX 2.5 on a 16 GB laptop GPU

**Findings report — measured 2026-08-19 on one machine, with receipts.**

LTX 2.5 generates video and its own audio in a single joint pass, and it runs on a
16 GB consumer laptop GPU. This report states what was measured, what it cost, what
did not fit, and what nobody has verified yet. Sixteen cells were run. Every number
below is bound to a receipt in [`results/`](../results/); every graph is a drop-in
API-format file in [`recipes/`](../recipes/).

Nothing here was quantized by this lab. The weights are other people's builds,
downloaded as published, and measured. Credit is at the bottom, and it matters.

---

## The bench

| | |
|---|---|
| GPU | RTX 5080 Laptop, 16 GB — 15.92 GiB addressable, Blackwell sm_120 |
| Stack | Windows 11, Python 3.12, torch 2.10.0, CUDA 13.0 |
| Attention | SDPA, **Sage-free** — the boot passes no `--use-sage-attention` |
| Output tested | 832x480, 97 frames, 25 fps = 3.88 s, video + native audio |
| Sampling | VRAM and host RAM polled every 200 ms across every run |

---

## Four findings

**1. It fits, and it fits by almost nothing.** Absolute peak across all sixteen runs:
**15.47 – 15.60 GiB**. On a card that addresses 15.92 GiB, that leaves **0.32 GiB** of
headroom at worst. Close your browser.

**2. You cannot tune your way under it.** The peak did not move when steps changed
(8 vs 20), when guidance changed (CFG 1.0 vs 3.0), when quantization changed (Q3_K_M
vs Q5_K_M), or when mode changed (t2v / i2v / a2v). The floor is set by the weights
and the decode, not by sampler settings. If you are trying to fit LTX 2.5 into 14 GB
by lowering steps, that is not a lever. Sixteen gigabytes is the requirement here, not a
recommendation.

**3. Without a loader patch, the audio never loads.** ComfyUI-GGUF cannot load LTX 2.5
out of the box, for two unrelated reasons — and the second one silently disables the
one feature that makes 2.5 worth running. See *The patch* below.

**4. The fastest complete audio-video cell finished in 77.7 seconds** for 3.88 seconds
of finished output — roughly 20x the clip's own length, on a laptop, sound included.

---

## The patch

Both fixes live in one file:
[`scratch/patches/ComfyUI-GGUF-ltx25-gemma4.patch`](../scratch/patches/ComfyUI-GGUF-ltx25-gemma4.patch),
applied inside the `ComfyUI-GGUF` custom-node directory.

1. **The text encoder is rejected outright.** LTX 2.5 uses a Gemma-4 12B encoder, and
   `gemma4` is not in `TXT_ARCH_LIST`. One word.

2. **The audio path cannot load.** Three LTX-AV parameters are stored as BF16 but never
   pass through `GGMLOps`, so they must be dequantized at load. The stock loader only
   dequantizes BF16 tensors of rank 1 or lower, and these are higher rank:

   ```
   audio_embeddings_connector.learnable_registers
   keyframes_abs_pos_embedding
   video_embeddings_connector.learnable_registers
   ```

   The first is the audio embeddings connector. Without the patch, native audio — the
   entire reason to run 2.5 — does not load.

---

## What works

Distilled, 8 steps, `LTXVDualCFGGuider` at video 1.0 / audio 1.0, sampler
`euler_ancestral`, Q3_K_M weights with the Gemma-4 encoder, 832x480x97 at 25 fps.

| Recipe | Wall clock | Peak VRAM | What it does |
|---|---:|---:|---|
| [`golden_t2v_cinematic_music`](../recipes/ltx_2_5_golden_t2v_cinematic_music.json) | **77.7 s** | 15.47 GiB | Scene plus score |
| [`t2v_path_a`](../recipes/ltx_2_5_t2v_path_a.json) | 87.0 s | 15.52 GiB | The bare distilled lane |
| [`t2v_path_a_visual`](../recipes/ltx_2_5_t2v_path_a_visual.json) | 87.2 s | 15.48 GiB | Visual-led variant |
| [`golden_t2v_action_foley`](../recipes/ltx_2_5_golden_t2v_action_foley.json) | **93.0 s** | 15.51 GiB | Action plus matched foley |
| [`a2v_path_a_action`](../recipes/ltx_2_5_a2v_path_a_action.json) | 106.4 s | 15.48 GiB | Audio-conditioned video |

Foley and score are the strong suit: audio generated for a scene the same model is
drawing is where a joint model earns its keep over bolting on a separate audio pass.

### The graph values that matter

| Node | Setting | Value |
|---|---|---|
| `LTXVScheduler` | steps | 8 |
| | max_shift / base_shift | 2.05 / 0.95 |
| | stretch / terminal | true / 0.1 |
| `KSamplerSelect` | sampler_name | `euler_ancestral` (i2v lane uses `euler_ancestral_cfg_pp`) |
| `LTXVDualCFGGuider` | video_cfg / audio_cfg | 1.0 / 1.0 |
| `EmptyLTXVLatentVideo` | width x height x length | 832 x 480 x 97 |
| `LTXVEmptyLatentAudio` | frames_number | 97 |
| `VAEDecodeTiled` | tile_size / overlap | 512 / 64 |
| | temporal_size / temporal_overlap | 33 / 4 |

At CFG 1.0 the negative prompt is inert — leave it empty. The positive prompt is the
only steering channel you have.

---

## Six rules that decide whether the graph runs at all

1. **The audio VAE loads even for a silent clip.** `LTXVEmptyLatentAudio` needs it to
   mint the audio latent, and `LTXVConcatAVLatent` needs that latent to build the joint
   tensor. A silent lane still computes the audio side through all 8 steps — it only
   skips the final audio decode. Discarding the audio never meant avoiding paying for it.
2. **Use an ancestral sampler.** At 8 distilled steps, non-ancestral samplers freeze the
   latent: you get a still image with a render time attached.
3. **Both canvas axes must divide by 32.** 832/32 = 26 and 480/32 = 15 are fine.
   768x432 fails — 432/32 = 13.5 corrupts the tensor and takes down the VAE decode.
4. **Frame count must satisfy `(frames - 1) % 8 == 0`.** 97 works. 96 does not.
5. **Connect the scheduler's `latent` port.** Left dangling, it silently falls back to a
   4096-token curve and wrecks the motion-shift math. It still runs. It just comes out
   wrong — the worst kind of failure.
6. **Keep the tiled decode.** `VAEDecodeTiled` at 512/64 with temporal 33/4 is
   load-bearing, not a default. Whole-clip decode of 97 frames is exactly the allocation
   this lane has no room for.

---

## What costs more than it returns

| Lane | Cost | Verdict |
|---|---:|---|
| 20 steps at CFG 3.0 ([`t2v_gguf`](../recipes/ltx_2_5_t2v_gguf.json), [`t2v_radio_drama`](../recipes/ltx_2_5_t2v_radio_drama.json)) | 254.4 – 275.9 s | ~3x the wall clock for an identical peak. Reach for it only if the 8-step output is too static. |
| Q5_K_M instead of Q3_K_M | 348.5 s vs 276.8 s | **26% slower for the same peak** (15.51 vs 15.56 GiB). Quantization is a speed lever here, not a memory lever. |
| Static lip sync ([`golden_a2v_static_lipsync`](../recipes/ltx_2_5_golden_a2v_static_lipsync.json)) | 404.6 s | Runs and produces a file. Slowest cell measured, for the same 3.88 s of output. Not recommended at this memory budget. |

The Q3-vs-Q5 comparison is a clean A/B: same recipe, same steps, same guidance, only the
quantization swapped — [`a2v_gguf`](../results/ltx_2_5_a2v_gguf.json) against
[`a2v_gguf_q5`](../results/ltx_2_5_a2v_gguf_q5.json). Across every cell, Q3 landed
15.47–15.60 and Q5 landed 15.48–15.57. Indistinguishable.

---

## What does not fit

- **161-frame multishot** — spikes to 18–20 GiB. Observed during exploration; no receipt filed.
- **In-graph 2x latent upscaling** — forces a 1664x960x97 decode and hard-OOMs. Run it as a
  separate offline pass instead. Observed; no receipt filed.
- **Any canvas past 832x480**, including 1024x576.
- **Anything under 16 GB.** The floor sits at 15.47 GiB with every setting turned down, so the
  model needs a card that can address roughly 16 GB. That is arithmetic from the measured floor,
  not a separate test.

---

## One prompting note

Modern video diffusion models damp motion hard. Subtle, gentle, or ambient prompts
collapse into a flat "live photo" hold. If you want movement, write high-energy kinetic
verbs, an explicit camera trajectory, and a clear cause-and-effect trigger. This held
across both LTX and MiniMax H3 on this bench — it appears to be a property of the model
class, not of prompt wording.

---

## What this report does not claim

- **No output has been human-reviewed.** Every receipt carries `eyeball: pending` and
  `promotion_ready: false`. "Works" means it runs, it fits, and it produces a complete
  audio-video file. Nobody has signed off on how it looks or sounds.
- **All sixteen cells are marked FAIL in the repository** — against a **14.5 GiB policy
  budget this lab sets for itself**, not against the hardware. Every one of them produced
  valid output. If you do not share that budget, read those rows as passes.
- **One machine, one canvas, one frame count.** 832x480x97 at 25 fps is the only geometry
  with receipts, on one 16 GB card. The binding constraint is a memory floor rather than anything
  architecture-specific, so the same settings should hold on other 16 GB NVIDIA cards running the
  same stack — but that is an expectation, not a measurement. Nothing here was tested on a second
  GPU.
- **No weights were quantized, retrained, or modified here.** The only code change is the
  loader patch above.

---

## Weights, and who made them

Everything was downloaded as published and measured as-is. The fetchers, with every
source URL, are [`scratch/download_ggufs.py`](../scratch/download_ggufs.py) and
[`scratch/download_ltx25.py`](../scratch/download_ltx25.py).

| Role | File | Source |
|---|---|---|
| Distilled transformer (used) | `LTX-2.5-Distilled-Q3_K_M.gguf` | [realrebelai/LTX-2.5_GGUFs](https://huggingface.co/realrebelai/LTX-2.5_GGUFs) — community quantization |
| Text encoder (used) | `gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf` | [elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF](https://huggingface.co/elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF) — community quantization |
| Video VAE | `ltx-2.5-video-vae-bf16.safetensors` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) — official |
| Audio VAE | `ltx-2.5-audio-vae-bf16.safetensors` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) — official |
| Also fetched | INT8 ConvRot transformer and encoder, latent upscaler | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) — official |
| Also fetched | `gemma4_e2b_it_bf16.safetensors` | [Comfy-Org/gemma-4](https://huggingface.co/Comfy-Org/gemma-4) |

The model is **LTX 2.5 by Lightricks**. The GGUF builds that make it fit on a 16 GB card
are **community quantizations by their respective authors** — this lab did not produce
them and takes no credit for them. The loader that reads them is
[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF); the patch above is a three-line
change to it, not a fork.

Model weights carry their own licences. Check Lightricks' terms before shipping anything
commercial.

---

## Reproduce it

| What | Where |
|---|---|
| API-format graphs, ready to POST to `/prompt` | [`recipes/ltx_2_5_*.json`](../recipes/) — 20 files, 16 with receipts |
| Receipts: peak VRAM, wall clock, output SHA-256, boot lane | [`results/ltx_2_5_*.json`](../results/) |
| UI-format workflows for drag-and-drop | [`scratch/ltx_2.5_gguf_workflow.json`](../scratch/ltx_2.5_gguf_workflow.json), [`scratch/video_ltx2_5_t2v.json`](../scratch/video_ltx2_5_t2v.json) |
| Loader patch | [`scratch/patches/ComfyUI-GGUF-ltx25-gemma4.patch`](../scratch/patches/ComfyUI-GGUF-ltx25-gemma4.patch) |
| Full working-set guide | [`LTX_2_5_ON_16GB.md`](../LTX_2_5_ON_16GB.md) |
| Repository | [github.com/jbrick2070/vram-recipe-lab](https://github.com/jbrick2070/vram-recipe-lab) |

Each recipe is paired with a receipt of the same name. The receipt records
`recipe_sha256`, so the pairing cannot drift.

---

*Measured 2026-08-19 on a single RTX 5080 Laptop. Repository is MIT licensed.*
