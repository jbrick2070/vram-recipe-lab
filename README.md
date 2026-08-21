# vram-recipe-lab

**A measurement lab for fitting video-generation models onto one 16 GB laptop GPU.**

Not a model zoo, not a benchmark suite. It answers one question per model, with
evidence: *does this thing actually run here, what does it cost, and can I prove
it?*

Between 2026-08-07 and 2026-08-19 it produced **473 machine receipts** across
**113 recipes** on an RTX 5080 Laptop (16 GB, Blackwell sm_120) running Windows,
torch 2.10, CUDA 13.

**Start here:** [**Running LTX 2.5 on 16 GB of VRAM**](LTX_2_5_ON_16GB.md) --
the settings, the loader patch, and the drop-in graphs.

---

## Why it exists

The production pipeline this feeds ([ComfyUI-OldTimeRadio](https://github.com/jbrick2070/ComfyUI-OldTimeRadio),
which generates old-time-radio episodes end to end) had a VRAM guard that was
**written but never called.** Renders ran unchecked, hit CUDA OOM, and corrupted
the allocator -- and each failure cost a full session to diagnose because there
was no record of what had actually been asked of the card.

So the lab is built around a single rule: **a run that left no receipt did not
happen.** Everything else follows from that.

## How a measurement works

The lab boots its **own** headless ComfyUI on port 8199 and never touches the
interactive instance or the production servers. Before a single prompt is
queued, [`PREFLIGHT.md`](PREFLIGHT.md) is enforced in code -- not by checklist:

- **Ownership.** An OS byte lock plus nonce-bound lease receipts, so two runs
  can never share the GPU and a crashed run cannot leave a lock that a later
  run silently inherits.
- **A cold card.** `nvidia-smi` must read under 3072 MiB before boot. Baseline
  VRAM and host RAM are recorded immediately before the prompt, then sampled
  **every 200 ms** through execution.
- **A validated graph.** Every node class and input is checked against live
  `/object_info`; every referenced weight must already appear in
  [`models_manifest.md`](models_manifest.md). Missing nodes or weights are
  `BLOCKED` -- never auto-installed, never auto-downloaded.
- **Exact fixtures.** Input images and audio are hash-captured, uploaded, then
  read back and re-hashed. A mismatch aborts. Fixtures are never regenerated
  mid-run, because that would silently invalidate every receipt citing them.
- **Append-only history.** Receipts cannot be overwritten. Run numbers are
  derived from all preserved evidence and re-audited before the write.
- **An affordability guard.** An unchanged recipe whose last run failed its VRAM
  gate is refused rather than re-run. Repeating a known failure is not evidence.
- **A verified boot lane.** Reserve and pinned-memory flags are checked
  bidirectionally against the live server argv and recorded in the receipt, so
  no number is ever attributed to the wrong configuration.

Each run then writes a JSON receipt with around 90 fields: absolute and net peak
VRAM, wall clock, the output file's SHA-256, the recipe's SHA-256, ffprobe'd
canvas / frame count / fps / codecs, and the exact boot lane.

## What "PASS" means here, and what it does not

Two things this repo is careful about, and you should be too when reading it:

**`FAIL` usually means a policy breach, not a crash.** The lab enforces a
**14.5 GiB** working ceiling, chosen so production renders keep headroom on a
16 GB card. A run that peaks at 15.5 GiB is marked FAIL **even though it
rendered a complete, valid file.** Sixteen of the seventeen LTX 2.5 cells are
exactly this case. If you do not share that budget, read those rows as passes.

**A machine pass is not a quality verdict.** Receipts carry a separate `eyeball`
field for human review. Most experimental cells sit at `eyeball: pending` and
`promotion_ready: false`, and nothing in this repo converts a green machine gate
into "it looks good." Third-party numbers are tagged EXTERNAL-REPORTED and are
never restated as local measurements.

## What has been measured

| Finding | Evidence |
|---|---|
| **LTX Video distilled 2B is 29.5x faster than WAN TI2V 5B** on a controlled workload (832x480, 193 frames, 25 fps): 13.8 s vs 407.5 s warm | [`results/comparisons/general_video_speed_pair.json`](results/comparisons/general_video_speed_pair.json) |
| **LTX 2.5 needs a 16 GB card.** 15.47-15.60 GiB absolute peak across all 16 cells, immovable by steps, CFG, or quantisation | [the guide](LTX_2_5_ON_16GB.md) |
| **MiniMax H3 fits an 8 GB laptop.** 7.21 GiB action / 6.79 GiB motion at 864x480, 90 frames, human-approved | [`eightgb_bench/README.md`](eightgb_bench/README.md) |
| **HuMo 1.7B's clamp floor is 12.84 GiB** warm, with zero graph or widget changes | [`docs/HUMO_DIET.md`](docs/HUMO_DIET.md) |
| **Video diffusion damps motion hard.** Gentle prompts collapse into static "live photo" holds across both LTX and H3 -- a model-class property, not a wording problem | [`eightgb_bench/README.md`](eightgb_bench/README.md) |

The full grid, including every failure and every superseded run, is in
[`ENGINE_MATRIX_BETA.md`](ENGINE_MATRIX_BETA.md) and [`RESULTS.md`](RESULTS.md).

## Layout

| Path | What is in it |
|---|---|
| [`recipes/`](recipes/) | 113 API-format ComfyUI graphs, ready to POST to `/prompt` |
| [`results/`](results/) | 473 receipts. One per run, append-only, never edited |
| [`docs/`](docs/) | Per-model findings, VRAM budgets, licence grants, handoffs |
| [`eightgb_bench/`](eightgb_bench/) | The separate 8 GB-card investigation |
| [`tests/`](tests/) | 53 tests over the runner's own gates and receipt integrity |
| [`fixtures/`](fixtures/) | Hash-frozen input images and audio |
| [`scratch/patches/`](scratch/patches/) | Upstream patches, including LTX 2.5 weight decoding and the additive CPU-pinned text loader |
| [`BOOT.md`](BOOT.md) / [`PREFLIGHT.md`](PREFLIGHT.md) | How the server boots and what is enforced before every prompt |

## Using it

The recipes are the reusable part. Each is a plain API-format graph paired with
a same-named receipt proving what it cost. Drop one into your own pipeline,
change the prompt, keep the structural settings -- those are the measured part.

The lab hardware is one specific laptop, so treat the VRAM figures as *this card,
this stack*. The structural findings -- divisibility constraints, which nodes are
load-bearing, where the memory actually goes -- travel.

---

MIT licensed. Model weights carry their own licences; check the vendor's terms
before shipping anything commercial.
