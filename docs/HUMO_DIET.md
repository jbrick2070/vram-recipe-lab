# HuMo 1.7B VRAM Diet

Date: 2026-08-09

## Result

The HuMo 1.7B diet reached its machine target without changing a generation node,
model, or widget. The winning immutable run is the second consecutive clamp-13
execution: **12.84 GiB absolute peak** in **243.0 seconds**, below the campaign's
**13.5 GiB** target. It is a warm machine pass, but quality parity remains
`PENDING_HUMAN`; this document does not promote it before Jeffrey compares the A/B.
[Phase 1 comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json)

The mutable current alias intentionally tells a later truth: run 3 probed the stricter
clamp-12 lane and failed that lane at **14.47 GiB absolute / 12.28 GiB net** in
**259.8 seconds**. That failure does not rewrite the immutable clamp-13 warm pass, and
it was not followed by a forced duplicate. [Immutable run 2 winner](../results/humo_1p7b_diet_run2.json),
[immutable run 3 clamp-12 failure](../results/humo_1p7b_diet_run3.json), and
[current alias](../results/humo_1p7b_diet.json)

## Phase 0: production-lane feasibility

The production HuMo adapter resolves entirely to ComfyUI core and `comfy_extras`
classes. The live lab server exposed all **14** required classes and the exact Whisper
audio encoder; `missing_classes` is empty. No HuMo custom-node pack,
`LAB_EXTRA_WHITELIST` extension, download, or install was required.
[Live no-prompt feasibility receipt](../results/humo_diet/phase0_lane_feasibility.json)

The diet recipe was seeded from OTR's `_build_graph`, not a vendor template. Its HuMo
generation path preserves the production models, fixtures, prompt, canvas, frame
count, seed, sampler, scheduler, step count, shift, and plain decode. The lab's
`CreateVideo` / `SaveVideo` tail is delivery instrumentation, not a generation or diet
lever. [Phase 1 comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json)

## Phase 1: clamp floor

All values below are frozen with source-receipt and telemetry hashes in the
[Phase 1 comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json).

| Lane and immutable evidence | Cache state | Absolute peak | Wall time | Machine result |
|---|---|---:|---:|---|
| [clamp-13 run 1](../results/humo_1p7b_diet_run1.json) | cold | 14.21 GiB | 223.0 s | Cold gate pass; above the 13.5 GiB diet target |
| [clamp-13 run 2](../results/humo_1p7b_diet_run2.json) | warm | **12.84 GiB** | 243.0 s | **Warm machine winner; diet target met** |
| [clamp-12 run 3](../results/humo_1p7b_diet_run3.json) | cold, fresh server | 14.47 GiB | 259.8 s | Clamp-12 FAIL at 12.28 GiB net; stopped without `--force` |

The production OTR measurements were unclamped at **15.118164** and **15.231445
GiB**. They record what that lane chose to spend, not HuMo's allocation floor.
Against those measurements, the clamp-13 warm result lowers the observed absolute
peak to **12.84 GiB** while keeping the generation graph unchanged.
[OTR take 1](../results/otr_side/humo_1_7b_bakeoff_take1.json),
[OTR take 2](../results/otr_side/humo_1_7b_bakeoff_take2.json), and
[Phase 1 comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json)

### Where the VRAM goes

The largest staged weight in the server log is WanTE/UMT5 at **6419 MB**, compared
with **3320 MB** for the HuMo DiT. That does not prove the text encoder remains
resident. The measured fresh-run runtime peak occurs in HuMo denoising: **14.210
GiB** on clamp-13 cold and **14.466 GiB** on clamp-12 cold. The warm run records
**12.227 GiB** during denoising and its **12.841 GiB** overall maximum during decode.
The evidence therefore names the combined HuMo denoise/decode working set as the
runtime hog, not the 1.7B DiT file size by itself; encoder residency is explicitly
unproved. [Phase-linked telemetry analysis](../results/humo_diet/phase1_clamp_floor_comparison.json)

## Exact OTR-to-diet settings diff

This is the complete transcribable change list. Every generation node and widget not
listed here remains unchanged.

| Scope | Production bakeoff | Diet winner | OTR integration instruction | Evidence |
|---|---|---|---|---|
| Generation graph and widgets | OTR HuMo 1.7B production graph | **No change** | Change no model, prompt, fixture, canvas, frame, sampler, seed, conditioning, or decode widget | [production receipt](../results/otr_side/humo_1_7b_bakeoff_take1.json); [comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json) |
| Pinned-memory boot flag | flag absent | `--disable-pinned-memory` | Add this flag only to the explicit HuMo diet boot variant | [production argv](../results/otr_side/humo_1_7b_bakeoff_take1.json); [warm diet argv](../results/humo_1p7b_diet_run2.json) |
| Target-card pressure | unclamped; no reserve flag | lab `--clamp 13`, yielding live `--reserve-vram 2.921` on the measured GPU | Express a 13 GiB target-card budget; for this measured host, pass `--reserve-vram 2.921` | [warm diet receipt](../results/humo_1p7b_diet_run2.json) |
| Default boot | existing production default | unchanged | Do not make the diet flags global or alter the default boot | [comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json) |

The lab command-level settings are therefore exactly:

```text
--clamp 13 --disable-pinned-memory
```

The equivalent measured ComfyUI launch delta is exactly:

```text
--reserve-vram 2.921 --disable-pinned-memory
```

The immutable warm receipt preserves the full live argv and the target-card-to-reserve
calculation. [Warm diet receipt](../results/humo_1p7b_diet_run2.json)

## Phase 2 disposition

Phase 2 was correctly skipped. Its quantized encoder, block-swap/offload, tiled
decode, step-reduction LoRA, and smaller-canvas levers were conditional on Phase 1
missing the **13.5 GiB** target; the warm clamp-13 run met it at **12.84 GiB** with
zero generation-graph changes. No asset was downloaded and no quality-cost lever was
introduced. [Phase 1 comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json)

Community research found no low-VRAM lever backed by two independent numerical HuMo
runs, so none was silently promoted into the measured recipe. Unmeasured community
claims remain tagged `EXTERNAL-REPORTED`; missing assets remain blocked.
[Low-VRAM intel sweep](../research/HUMO_LOWVRAM_INTEL.md)

## Quality-parity A/B

The review package places the original OTR production take beside the immutable warm
clamp-13 output, using the same portrait, TTS fixture, production settings, and fixed
seed. [Production-vs-diet A/B](../outputs/humo_1p7b_diet_ab_production_vs_clamp13_warm.mp4)
and [comparison receipt](../results/humo_diet/phase1_clamp_floor_comparison.json)

Side A is the production review video and side B is the lab clamp-13 warm video. The
package uses the exact raw TTS fixture as one shared review soundtrack, and the
comparison receipt hash-binds and probes the assembled artifact. It is a human-review
aid, not new model evidence or a promotion artifact.

All three diet-run artifacts are byte-identical to each other, which proves fixed-seed
repeatability, not perceptual parity with the original wrapper artifact. Jeffrey must
judge lips, onset, identity, temporal stability, and overall image quality. Until that
review, the integration state is **warm machine-certified, human quality
`PENDING_HUMAN`**.

**RULED by Jeffrey 2026-08-09 (A/B full view): PARITY** - "look same to me."
The integration state is now **warm machine-certified AND human
quality-approved**. The diet boot variant (`--reserve-vram 2.921
--disable-pinned-memory`, explicit variant only, default boot unchanged) is
cleared for OTR integration per the Recommendation section below.

## Recommendation

Recommendation: retain the production graph verbatim and add an explicitly selected
HuMo diet boot variant using the two launch flags above. Keep the default boot
unchanged. The measured clamp-13 lane is the candidate production floor; do not use
the stricter clamp-12 lane, and do not invoke Phase 2 levers unless a future controlled
run first shows that the clamp-13 result no longer meets the target. Human A/B approval
and external verification still gate OTR integration.
