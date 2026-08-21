# Running LTX 2.5 on 16 GB of VRAM

**A guide to what is proven to work, from a lab that measured it.**

LTX 2.5 generates video *and* its own audio in one joint pass. It runs on a
16 GB consumer card. This guide is the working set: the graphs that ran, the
numbers they hit, and the handful of non-obvious things that stop it dead if
you get them wrong.

If you have your own app and you want to plug LTX 2.5 into it, the recipes in
[`recipes/`](recipes/) are drop-in API-format graphs. They ran. Every claim
below is bound to a receipt in [`results/`](results/).

> **2026-08-21 conformance correction.** The original receipts below used the
> stock `CLIPLoaderGGUF`, which can move the 12B Gemma text encoder onto the
> GPU during encode. OTR production already pinned that encoder to CPU, so the
> old lab memory figures describe a heavier lab-only configuration and are not
> current recipe verdicts. Active recipes now use `CLIPLoaderGGUFCPU`; the
> historical receipts remain append-only evidence of what actually ran. No new
> memory claim is made by this correction.

---

## What this is measured on

| | |
|---|---|
| GPU | RTX 5080 Laptop, 16 GB (15.92 GiB addressable), Blackwell sm_120 |
| Stack | Windows 11, Python 3.12, torch 2.10.0, CUDA 13.0 |
| Attention | SDPA. **Sage-free** -- the boot passes no `--use-sage-attention` |
| Output | 832x480, 97 frames, 25 fps = 3.88 s, video + native audio |

**How to read the numbers.** Every figure here is a machine measurement from a
receipt, sampled every 200 ms across the run. **No output in this guide has
been human-reviewed** -- every receipt carries `eyeball: pending` and
`promotion_ready: false`. So "works" means *it runs, it fits, and it produces a
complete audio+video file*. It does not mean anyone has signed off on how it
looks. That distinction is the whole point of the lab, and this guide keeps it.

---

## Historical memory measurements (superseded for current recipes)

**Absolute peak: 15.47 - 15.60 GiB.** Sixteen runs. Every lane, every step
count, every CFG, both quantisations.

That tight clustering was the finding for the original, non-conforming loader.
Peak VRAM **did not move** when we changed
steps (8 vs 20), CFG (1.0 vs 3.0), quantisation (Q3_K_M vs Q5_K_M), or mode
(t2v / i2v / a2v). It is a floor set by the weights and the decode, not by your
sampler settings.

Do not use these figures to grade the CPU-pinned recipes. They remain useful
only for reproducing the older stock-loader receipts.

Net of the desktop-and-server baseline, the render itself accounted for
13.3 - 14.8 GiB; the baseline at measurement time ranged 0.74 - 2.31 GiB. Net
moved around because the allocator expands into whatever room it finds, which
is exactly why **the absolute peak is the number to plan against.**

Headroom on a 15.92 GiB card at 15.60 GiB peak is **0.32 GiB.** It fits. It is
not comfortable. Close your browser.

---

## Before anything runs: the two loader patches

Out of the box, this installed ComfyUI-GGUF version **cannot load LTX 2.5.**
Two weight-decoding fixes live in
[`ComfyUI-GGUF-ltx25-gemma4.patch`](scratch/patches/ComfyUI-GGUF-ltx25-gemma4.patch):

1. **The text encoder is rejected outright.** LTX 2.5 uses a Gemma-4 12B
   encoder, and `gemma4` is not in `TXT_ARCH_LIST`. One word fixes it.

2. **The audio path cannot load -- and this one is genuinely obscure.** Three
   LTX-AV parameters are stored as BF16 but never pass through `GGMLOps`, so
   they need dequantising at load time. The stock loader only dequantises BF16
   tensors of rank 1 or less, and these are not:

   ```
   audio_embeddings_connector.learnable_registers
   keyframes_abs_pos_embedding
   video_embeddings_connector.learnable_registers
   ```

   The first one is the audio embeddings connector. Without the patch, **the
   native audio feature -- the reason to use 2.5 at all -- will not load.**

Apply it inside your `ComfyUI-GGUF` custom node directory. Then apply the
separate additive
[`ComfyUI-GGUF-CLIPLoaderGGUFCPU.patch`](scratch/patches/ComfyUI-GGUF-CLIPLoaderGGUFCPU.patch).
That patch leaves the stock loader unchanged and adds one opt-in node which
sets `initial_device`, `load_device`, and `offload_device` to CPU, then fails
before the first forward if the patcher is not actually CPU-resident. Its
baseline and installed hashes are recorded beside it in
[`ComfyUI-GGUF-CLIPLoaderGGUFCPU.json`](scratch/patches/ComfyUI-GGUF-CLIPLoaderGGUFCPU.json).

## Weights

Fetchers with every source URL: [`scratch/download_ggufs.py`](scratch/download_ggufs.py),
[`scratch/download_ltx25.py`](scratch/download_ltx25.py)

| File | Loader | From |
|---|---|---|
| `LTX-2.5-Distilled-Q3_K_M.gguf` | `UnetLoaderGGUF` | `realrebelai/LTX-2.5_GGUFs` |
| `gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf` | `CLIPLoaderGGUFCPU`, type `ltxv` | `elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF` |
| `ltx-2.5-video-vae-bf16.safetensors` | `VAELoader` | `Lightricks/LTX-2.5` |
| `ltx-2.5-audio-vae-bf16.safetensors` | `VAELoader` | `Lightricks/LTX-2.5` |

**Q3_K_M is the one to use, and the reason is speed, not memory.** The lab ran a
clean A/B -- the same recipe, the same 20 steps and CFG, only the quantisation
swapped ([`a2v_gguf`](results/ltx_2_5_a2v_gguf.json) vs
[`a2v_gguf_q5`](results/ltx_2_5_a2v_gguf_q5.json)):

| Quant | Peak GiB | Wall clock |
|---|---:|---:|
| Q3_K_M | 15.56 | **276.8 s** |
| Q5_K_M | 15.51 | 348.5 s |

**Q5 was 26% slower for the same peak VRAM.** Across every cell, Q3 landed
15.47-15.60 and Q5 landed 15.48-15.57 -- indistinguishable. Quantisation is not
the lever people expect it to be here; it does not buy you headroom.

---

## The settings that work

From [`recipes/ltx_2_5_golden_t2v_cinematic_music.json`](recipes/ltx_2_5_golden_t2v_cinematic_music.json)
-- 22 nodes, and these are the values that matter:

| Node | Setting | Value |
|---|---|---|
| `LTXVScheduler` | steps | **8** |
| | max_shift / base_shift | 2.05 / 0.95 |
| | stretch / terminal | true / 0.1 |
| `KSamplerSelect` | sampler_name | **`euler_ancestral`** (the i2v lane uses `euler_ancestral_cfg_pp`) |
| `LTXVDualCFGGuider` | video_cfg / audio_cfg | **1.0 / 1.0** |
| `LTXVModalityGuidance` | modality_scale | 1.0, across 0.0 to 1.0 |
| `EmptyLTXVLatentVideo` | width x height x length | **832 x 480 x 97** |
| `LTXVEmptyLatentAudio` | frames_number | 97 |
| `VAEDecodeTiled` | tile_size / overlap | **512 / 64** |
| | temporal_size / temporal_overlap | **33 / 4** |

### Six things that will bite you

**1. The audio VAE is required even if you want a silent clip.**
`LTXVEmptyLatentAudio` takes `audio_vae` to *mint* the audio latent, and
`LTXVConcatAVLatent` needs that latent to build the joint tensor the sampler
consumes. A silent lane still loads the audio VAE and still computes the audio
side through all 8 steps -- it only skips `LTXVAudioVAEDecode` at the end.
Discarding the audio never meant avoiding paying for it.

**2. Use an ancestral sampler.** At 8 distilled steps, ancestral sampling is
what keeps motion alive. Non-ancestral samplers freeze the latent at this step
count -- you get a still image with a run time.

**3. Both canvas axes must divide cleanly by 32.** 832/32 = 26, 480/32 = 15.
768x432 fails because 432/32 = 13.5, which corrupts the tensor and takes down
the VAE decode. 1024x576 does not fit.

**4. Frame count must satisfy `(frames - 1) % 8 == 0`.** The model's temporal
downsampling requires it. 97 works. 96 does not.

**5. Connect the scheduler's `latent` port.** Leave it dangling and it silently
falls back to a 4096-token curve, wrecking the motion-shift maths. It still
runs. It just comes out wrong -- the worst kind of failure.

**6. Keep the tiled decode.** `VAEDecodeTiled` at 512/64 with temporal 33/4 is
load-bearing, not a default. Whole-clip decode of 97 frames is exactly the
allocation this lane has no room for.

At CFG 1.0 the negative prompt is inert -- leave it empty. The only steering
channel you have is the positive prompt.

---

## What works, and how well

### Works well -- start here

Text-to-video with native audio, 8 steps, CFG 1.0. Fast and repeatable.

| Recipe | Wall clock | Peak GiB | What it does |
|---|---:|---:|---|
| [`golden_t2v_cinematic_music`](recipes/ltx_2_5_golden_t2v_cinematic_music.json) | **77.7 s** | 15.47 | Scene plus score |
| [`t2v_path_a`](recipes/ltx_2_5_t2v_path_a.json) | 87.0 s | 15.52 | The bare distilled lane |
| [`t2v_path_a_visual`](recipes/ltx_2_5_t2v_path_a_visual.json) | 87.2 s | 15.48 | Visual-led variant |
| [`golden_t2v_action_foley`](recipes/ltx_2_5_golden_t2v_action_foley.json) | **93.0 s** | 15.51 | Action plus matched foley |

78 to 93 seconds for 3.88 s of finished video with its own soundtrack, on a
laptop -- about 20-24x the clip's own length in render time.

**Foley and score are the strong suit.** The audio the model generates for a
scene it is also rendering -- footsteps, room tone, a theremin cue -- is where
the joint model earns its keep over bolting a separate audio pass on afterwards.

### Kind of works -- usable, with caveats

**Audio-conditioned video (a2v).** Feed it audio, get video shaped to it.
[`a2v_path_a_action`](recipes/ltx_2_5_a2v_path_a_action.json) is the quick one
at 106.4 s and 15.48 GiB. It runs clean; nobody has graded the result.

**The 20-step, CFG 3.0 lane.** Recipes like
[`t2v_gguf`](recipes/ltx_2_5_t2v_gguf.json) (275.9 s) and
[`t2v_radio_drama`](recipes/ltx_2_5_t2v_radio_drama.json) (254.4 s) drive the
distilled model with classic guidance. **They work -- and they cost about 3x the
wall clock for identical peak VRAM.** They do produce noticeably larger encodes,
which usually tracks more motion, but that has not been baselined and is not a
quality verdict. Reach for this lane only if the 8-step output is too static for
your scene, and expect to pay in minutes, not gigabytes.

### Tested, not recommended at this VRAM

**Lip sync.** [`golden_a2v_static_lipsync`](recipes/ltx_2_5_golden_a2v_static_lipsync.json)
runs and produces a file -- at **404.6 s**, the slowest cell measured, for the
same 3.88 s of output. We are not recommending it in the 16 GB range. It was
worth testing; it is not worth your render budget yet.

**Historical caution:** the 161-frame multishot receipt did not fit its test
lane. The old claim that in-graph latent upscaling necessarily hard-OOMs is
withdrawn: the lab later decoded 1664x960x97 successfully, and OTR now ships
the latent-upsample plus three-step-refine path. Its real tradeoff is render
time, not a categorical decode failure.

### One prompting note that applies to every lane

Modern video diffusion models damp motion hard. Subtle, gentle, or ambient
prompts collapse into a flat "live photo" hold. If you want movement, write
high-energy kinetic verbs, an explicit camera trajectory, and a clear
cause-and-effect trigger. This held across both LTX and MiniMax H3 in this lab
-- it is a property of the model class, not of your prompt wording.

---

## Drop-in graphs

**API format**, ready to POST to `/prompt` -- 27 of them in [`recipes/`](recipes/).
Each is paired with a receipt of the same name in [`results/`](results/) carrying
peak VRAM, wall clock, the output's SHA-256, and the full boot lane.

**UI format**, drag-and-drop onto the ComfyUI canvas:
[`scratch/ltx_2.5_gguf_workflow.json`](scratch/ltx_2.5_gguf_workflow.json),
[`scratch/video_ltx2_5_t2v.json`](scratch/video_ltx2_5_t2v.json),
[`scratch/video_ltx_2_a2v.json`](scratch/video_ltx_2_a2v.json).
Convert UI to API with [`scratch/convert_to_api.py`](scratch/convert_to_api.py).

---

## Reading a receipt

Every run writes a JSON receipt with around 90 fields. The ones you want:

| Field | Meaning |
|---|---|
| `peak_vram_gb` | Absolute peak across the whole card. **The planning number.** |
| `net_peak_vram_gb` | Peak minus the pre-run baseline |
| `artifact_sha256` | Hash of the actual output file -- the proof it rendered |
| `duration_s` | Wall clock |
| `boot_lane` | Exact server argv: reserve, pinned memory, sage |
| `recipe_sha256` | Hash of the graph that ran, so the pairing cannot drift |
| `eyeball` | Human review. **`pending` on everything here.** |

A run is marked `FAIL` in this repo when it breaks the lab's own **14.5 GiB
policy budget** -- a project constraint, not a hardware limit. Sixteen of the
seventeen 2.5 cells are marked FAIL for exactly that reason **and produced
complete, valid video anyway.** If you do not share that budget, read those
rows as passes.

---

*Measured 2026-08-19. This repository is MIT licensed. Model weights carry
their own licences -- check Lightricks' terms before shipping anything
commercial.*
