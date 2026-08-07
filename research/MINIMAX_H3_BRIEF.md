# MiniMax H3 Mission Brief (for the lab agent)

Read `2026-08-03-PROBLEM-STATEMENT-minimax-h3.md` in this folder first. It is the
grounded research. This brief translates it into lab tasks. The OTR pipeline
decision ("does H3 go in the dropdown") is NOT your job — your job is to produce
the MEASUREMENTS that decision is starved of. Section 5 of that doc says it
plainly: "Peak VRAM and wall clock on this box: zero measurements."

## The mission

Attempt low-VRAM MiniMax H3 recipes (t2v first, then i2v, then r2v) that render
under the 14.5 GB gate on this 16 GB RTX 5080 Laptop, and record honest numbers
either way. A well-documented FAIL with a measured peak is a successful outcome.
Seed workflows are in `comfy_templates/` (ComfyUI's own local H3 templates).

## Hard facts from the research — do not relearn these the expensive way

1. **Weights are NOT on disk.** Smallest usable set is 42.5 GB (DiT
   fl2va_pruned_int8_convrot 19.53 GiB + qwen3vl_32b_nvfp4_awq 14.61 GiB +
   video VAE 4.85 GiB + audio VAE 0.56 GiB). No GGUF, no distill exists.
   Downloading is Jeffrey's decision (disk + unread license). Until the models
   manifest shows them, ALL H3 render tasks are BLOCKED in RESULTS.md. Do the
   prep work instead: validate the template JSONs against /object_info, plan
   the offload strategy, write the recipe variants dry.

2. **THE SAGE ATTENTION LANDMINE (Comfy-Org/ComfyUI#15263).** This box runs
   SageAttention. Global `--use-sage-attention` routes H3's DiT through Sage's
   int8 QK path and produces PURE NOISE — video and audio — with NO error.
   The machine gate (clean run, VRAM under limit, output exists) will PASS on
   garbage. Therefore: every H3 run must be on a Sage-free ComfyUI boot lane,
   AND every H3 "PASS" additionally requires a human-eyeball check of the
   output before the ledger row says PASS. Note the boot lane used in every
   H3 results entry.

3. **Fitting 42.5 GB of weights into 14.5 GB peak means aggressive layerwise
   offload into system RAM (63.4 GB available).** The only known third-party
   integration (HM-RunningHub/ComfyUI_RH_MinMaxH3) targets 24 GB GPUs with
   INT8 + offload already applied — treat its settings as a starting point to
   push further, not a proof it fits here. Installing that custom node is a
   BLOCKED entry for Jeffrey to approve, not something you do.

4. **Local envelope:** 33.1B params, short edge 768 (cap 768x1344/32), 24 fps,
   4–15 s on a 17k+5 frame grid. 2K is not available locally. `H3-Context-IR`
   is a HOSTED service — this lab is offline-only, so recipes must not depend
   on it; note the expected quality cost in RESULTS.md instead.

5. **The "3060 renders 5 s in ~9 min" claim is UNVERIFIED folklore.** Do not
   cite it, do not calibrate expectations to it. Your measurements replace it.

## Recipe targets

- `recipes/h3_t2v_low.json` — minimum footprint: shortest legal clip (4 s),
  smallest legal resolution, max offload. Goal: does H3 produce ANYTHING under
  14.5 GB peak on this box?
- `recipes/h3_t2v_high.json` — best quality that still passes the same gate.
- Only after t2v numbers exist: i2v, then r2v variants from the templates.

## What "done" looks like

RESULTS.md rows for each variant with measured peak VRAM, wall clock, boot lane,
and PASS / FAIL / BLOCKED — plus a short honest paragraph: can this box run H3
under the gate, at what cost, or is it physically out of reach? Numbers with
receipts, either direction.
