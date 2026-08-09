# HuMo Low-VRAM Community Intel

Research performed 2026-08-09 before the local HuMo VRAM-diet renders. This
file is an external-evidence map, not a lab receipt and not a model-download
authorization.

## Evidence labels

- **VERIFIED / RUN** means the linked source reports a completed run with
  concrete hardware or workflow numbers. It is still **EXTERNAL-REPORTED** and
  is not a local measurement unless the row explicitly cites a lab receipt.
- **VERIFIED / SOURCE-CODE** means the exact control or compatibility statement
  is present in first-party code or documentation. It does not prove a VRAM
  saving on this machine.
- **FOLKLORE** means the source makes a recommendation or quality/performance
  claim without enough run detail to reproduce or rank it.

All URLs were accessed on **2026-08-09**. Publication dates are shown when the
source exposes one. Sources newer than six months were preferred, but HuMo's
public low-VRAM record is concentrated around its September 2025 release; the
few newer low-VRAM guides are Wan-family generalizations, not HuMo tests.

## Executive finding

No HuMo diet lever has two independent **VERIFIED / RUN** sources with
comparable VRAM evidence. The strongest concrete community result is one HuMo
14B Q4_K_M run on a 16 GB card at 832x480, 125 frames, with 28 wrapper blocks
swapped. The commonly repeated 12 GB and 8 GB claims omit measured peak VRAM or
reproducible settings. Therefore **no community lever is promoted directly
into the measured menu**. Phase 1 remains the exact native production graph
under clamp pressure. Wrapper migration, GGUF, a different text encoder, or a
step LoRA remain Phase-2 candidates only when compatible bytes and nodes are
already on disk and each is tested as one isolated change.

## Upstream baseline and wrapper-owned memory controls

| Claim | Evidence | Source URL and date | Tag | Lab consequence |
|---|---|---|---|---|
| HuMo's authors report that the 1.7B model generated one 480p video in about 8 minutes on a 32 GB GPU; they also say visual quality is lower than 17B while audio-visual sync is nearly unaffected. | Author release note with hardware, resolution, time, and qualitative comparison. It does not publish peak VRAM or the clip length. | https://github.com/Phantom-video/HuMo — 2025-09-16 | **VERIFIED / RUN — EXTERNAL-REPORTED** | Useful timing context only. It does not establish a 16 GB or 12 GB floor. |
| The WanVideoWrapper `WanVideoBlockSwap` node exposes `blocks_to_swap` 0–48 (default 20), `offload_img_emb`, `offload_txt_emb`, `use_non_blocking`, and `prefetch_blocks`; its own description says it swaps transformer blocks to CPU to reduce VRAM. | Direct implementation and widget schema. | https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/main/nodes_model_loading.py#L2650-L2691 — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** | Exact wrapper values are transcribable, but the production HuMo graph uses native ComfyUI nodes and exposes none of them. Using them would be a topology migration, not a knob on the current graph. |
| The wrapper also exposes `WanVideoVRAMManagement.offload_percent` from 0.0–1.0 and describes it as more aggressive than block swapping but potentially slower. | Direct implementation and widget schema. | https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/main/nodes_model_loading.py#L2693-L2719 — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** | Same topology-migration limitation. No HuMo-specific measured value was found. |
| With unmerged LoRAs, current wrapper code keeps LoRA buffers with their transformer blocks; the maintainer's worked example says a 1 GB LoRA with 20/40 blocks resident adds about 500 MB and may require swapping two additional blocks. | First-party maintainer documentation and arithmetic, not a HuMo benchmark. | https://github.com/kijai/ComfyUI-WanVideoWrapper#memory-use-update-again — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** | Relevant to HuMo 14B + LightX2V, not the 1.7B no-LoRA production graph. |
| The wrapper maintainer says native Wan support should normally be preferred when the feature already exists in core ComfyUI. | First-party project guidance. | https://github.com/kijai/ComfyUI-WanVideoWrapper#why-should-i-use-custom-nodes-when-wanvideo-works-natively — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** | Supports keeping Phase 1 on the exact native production graph. |

## Reported low-VRAM HuMo workflows

| Setup or claim | Exact reported settings | Source URL and date | Tag | Quality/failure note |
|---|---|---|---|---|
| HuMo 14B GGUF on a 16 GB card | Q4_K_M, 832x480, 125 frames / 5 seconds, 28 blocks swapped; author recommends 64 GB system RAM. | https://www.reddit.com/r/comfyui/comments/1nikvwc/humo_lipsync_available_on_the_wan_video_wrapper/ — 2025-09-16 | **VERIFIED / RUN — EXTERNAL-REPORTED** | Completion is reported, but peak VRAM, wall time, sampler settings, and artifact receipt are absent. It is 14B wrapper evidence, not a native 1.7B result. |
| Proposed HuMo on 12 GB | Same author suggests Q4_K_M, 480x480, 81 frames, 40 swapped blocks and 64 GB RAM, explicitly saying they are “pretty sure” it will work. | https://www.reddit.com/r/comfyui/comments/1nikvwc/humo_lipsync_available_on_the_wan_video_wrapper/ — 2025-09-17 | **FOLKLORE — EXTERNAL-REPORTED** | This is a prediction, not a reported run. It also changes three variables: quant, canvas/frames, and block count. |
| HuMo 1.7B on an 8 GB notebook | A commenter says they use HuMo 1.7B among several mostly quantized models on an RTX 3050 8 GB system. | https://www.reddit.com/r/StableDiffusion/comments/1nub5gb/low_vram_software/ — 2025-09-30 | **FOLKLORE — EXTERNAL-REPORTED** | No HuMo model file, graph, canvas, frames, time, or peak is supplied; the commenter also warns quality may be poor and disk swap is heavy. |
| “HuMo 1.7B should run on 8 GB” | Release-thread commenters infer this from model size and link GGUF files. | https://www.reddit.com/r/comfyui/comments/1nj5okr/humo_17b_is_out/ — 2025-09-17 | **FOLKLORE — EXTERNAL-REPORTED** | No run evidence. Model-file size alone does not include UMT5, Whisper, VAE, activations, or allocator behavior. |
| Recent 8–12 GB lip-sync advice | A June 2026 thread recommends low-resolution close dialogue shots and warns that lip-sync quality is unusually sensitive to resolution. | https://www.reddit.com/r/comfyui/comments/1ufksgc/whats_the_best_lipsync_wf_for_lowvram/ — 2026-06-25 | **FOLKLORE — EXTERNAL-REPORTED** | It is not HuMo-specific and supplies no artifact or VRAM receipt, but it is a useful warning against treating canvas reduction as free. |

## Quantized HuMo weights and text encoders

| Artifact or substitution | Public evidence | Source URL and date | Tag | Local status on 2026-08-09 |
|---|---|---|---|---|
| HuMo-1.7B GGUF family | QuantStack publishes Apache-2.0 files from Q3_K_S (986 MB) through Q8_0 (2.05 GB), with Q4_K_M at 1.37 GB; full F16/BF16 GGUF is 3.62 GB. | https://huggingface.co/QuantStack/HuMo-GGUF/tree/021ff2f8b87ac5c86e54f5ba347871420d3b5725/HuMo-1.7B — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** for existence; runtime/quality is **FOLKLORE** until measured | **BLOCKED**: no 1.7B HuMo GGUF is on disk. No download performed. Proposal: if Phase 1 fails, Jeffrey may authorize Q4_K_M plus the already-installed ComfyUI-GGUF pack as a new topology/quality campaign. |
| Quantized UMT5 encoder | ComfyUI-GGUF documents a quantized T5 loader specifically for further VRAM savings. Public UMT5 GGUF repositories include Q3–Q8 variants. | https://github.com/city96/ComfyUI-GGUF and https://huggingface.co/city96/umt5-xxl-encoder-gguf — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** for loader/artifact availability; HuMo savings are **FOLKLORE** | A Q5_K_M UMT5 file exists locally, but the production graph already uses the 6.74 GB FP8 UMT5 and the Q5 swap would require a GGUF CLIP loader. It remains a one-variable D1 candidate only if Phase 1 misses and live schema/model identity checks pass. |
| Production UMT5 FP8 | The production graph already uses `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, not FP16. | Local OTR engine source plus `models_manifest.md` — measured inventory 2026-08-09 | **VERIFIED / SOURCE-CODE and LOCAL BYTES** | There is no honest “switch to FP8” diet lever left; that saving is already baked in. |

## Distillation and step reduction

| Claim | Evidence | Source URL and date | Tag | Applicability |
|---|---|---|---|---|
| LightX2V publishes 4-step/distilled Wan2.1 and Wan2.2 resources and advertises low-resource 14B deployment. | First-party model/support matrix and documentation. | https://github.com/ModelTC/LightX2V — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE**; HuMo performance is **FOLKLORE** | No 1.7B HuMo-compatible distill LoRA was found. The only local LightX2V file is a 14B Wan I2V LoRA and is not shape-compatible with HuMo 1.7B. D4 is **BLOCKED** for this mission. |
| Kijai's public HuMo wrapper example links a LightX2V LoRA and uses HuMo 14B FP8. | Public workflow/model-link evidence. | https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/main/example_workflows/wanvideo_HuMo_example_01.json — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** for graph existence; speed/VRAM/quality are **FOLKLORE** | This is the 14B path, not evidence that the 14B LoRA can be loaded into 1.7B. |

## Known lever-specific failure modes

| Lever | Failure mode | Source URL and date | Tag | Gate response |
|---|---|---|---|---|
| Block swap / non-blocking transfer | Wrapper issue report describes persistent host-RAM growth; the maintainer says non-blocking transfer pins more RAM and disabling it may help. | https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/805 — 2025-07-15 | **VERIFIED / RUN — EXTERNAL-REPORTED** for the reporter's host-RAM failure; not HuMo-specific | Any wrapper experiment must measure host RAM and leave `use_non_blocking=false` initially. |
| Torch compile | Wrapper maintainer reports Windows first runs after model-code/input-shape changes can use drastically more VRAM because of stale/initial Triton compilation caches. | https://github.com/kijai/ComfyUI-WanVideoWrapper#memory-use-update-again — accessed 2026-08-09 | **VERIFIED / SOURCE-CODE** | The native Phase-1 recipe does not add compile. Never compare an uncached compile first run with a settled warm run. |
| Quantization | The concrete HuMo Q4 report does not publish paired quality evidence. A separate 8 GB HuMo anecdote concedes quality may be poor. | https://www.reddit.com/r/comfyui/comments/1nikvwc/humo_lipsync_available_on_the_wan_video_wrapper/ and https://www.reddit.com/r/StableDiffusion/comments/1nub5gb/low_vram_software/ — 2025-09 | **FOLKLORE — EXTERNAL-REPORTED** | Same-seed face identity, articulation, and onset must be eyeballed; file-size savings cannot substitute for quality parity. |
| Canvas reduction | Recent low-VRAM lip-sync discussion warns that mouth quality degrades more visibly than ordinary motion when resolution is reduced. | https://www.reddit.com/r/comfyui/comments/1ufksgc/whats_the_best_lipsync_wf_for_lowvram/ — 2026-06-25 | **FOLKLORE — EXTERNAL-REPORTED** | D5 remains last resort and must be labeled a quality-cost variant. |
| Tiled/temporal decode | No HuMo-specific controlled source was found that proves a VRAM benefit without seams for this exact native VAE path. | Search completed 2026-08-09; no qualifying source | **FOLKLORE** | Do not invent tile values from unrelated engines. Test only if the installed core node exposes an exact applicable control and Phase 1 proves decode is the peak phase. |
| Step reduction | No source establishes that a generic Wan 14B LightX2V LoRA is compatible with HuMo 1.7B or preserves audio-driven lip synchronization. | https://github.com/ModelTC/LightX2V — accessed 2026-08-09 | **FOLKLORE** | D4 is blocked absent a 1.7B-compatible file and direct evidence. |

## Community-informed Phase-2 menu decision

The two-source promotion rule produced **no promoted lever**. Only one concrete
HuMo run supports the Q4 + block-swap combination; all 8–12 GB claims are
predictions or incomplete anecdotes. If the exact native graph misses the local
13.5 GiB target under clamp, the permitted local order remains:

1. **D1, local Q5_K_M UMT5 through the GGUF CLIP loader** — candidate bytes are
   on disk, but compatibility and source schema must be proven live before a
   recipe is authored. This changes only the text-encoder loader/file.
2. **D2, wrapper block swap/offload** — **BLOCKED** because the production graph
   is native and the wrapper pack is not part of this lab lane. Download/install
   or topology migration requires a separate Jeffrey authorization; suggested
   starting values from the one concrete community run are 28 swapped blocks,
   `use_non_blocking=false`, no prefetch, and no embedding offload, but these are
   external starting points rather than recommendations.
3. **D3, tiled decode** — only if phase telemetry identifies VAE decode as the
   peak and an installed core node supplies a topology-compatible control.
4. **D4, step LoRA** — **BLOCKED**: only a 14B Wan I2V LightX2V LoRA is on disk;
   no compatible HuMo 1.7B file was found. Download proposal: Jeffrey may later
   authorize a specifically labeled HuMo-1.7B distill artifact with license,
   base-model hash, and a published same-seed quality comparison.
5. **D5, one /32 canvas step down** — last resort, explicitly a quality-cost
   experiment because lip-sync is resolution-sensitive.

No file was downloaded or installed during this sweep.
