# WAN inter-shot VRAM retention findings

Date: 2026-08-09
Scope: measurement and diagnosis only; no OTR fix
Status: `MEASUREMENT_COMPLETE_WITH_OFFLINE_POLICY_INCIDENT`

## Headline result

The failure is **reproduced and order-dependent in the measured WAN family**.
With `wan_ti2v`, the production wrapper completed the exact historical
two-segment chain -- [177 frames plus 25 frames, with the chain head drop and
tail trim producing exactly 200 delivered frames](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json)
-- then correctly refused the [65-frame follow-on shot because only 20 frames
were affordable at 9,665 MB free](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json).
The same shots and controls completed when their order was reversed: the
[65-frame shot ran first and the 200-frame chain ran last](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json).
The S4 `NO silent resize` refusal remains correct behavior.

The intent verdict is **MIXED**: the WAN UNET is deliberately kept for all
segments in one beat, while OTR deliberately skips its stronger residue flush
between consecutive beats using the same engine. ComfyUI's smart-memory and
allocator policy can therefore leave a same-engine warm plateau. The evidence
does **not** support an additive WanVAE leak: the VAE loader is segment-local,
the wrapper's `post` sample is taken before beat teardown, and the measured
inter-shot plateau is bounded rather than growing with every VAE staging.

Within the cross-engine set, `fastwan_8gb` reproduced the refusal, but it is a
subclass of `WanTi2vEngine`, not an independent family. `ltx_video` completed
both shots. This supports **WAN-family-specific in this measured set**, not the
broader claim that no other engine can retain VRAM. The frozen comparison and
all acceptance decisions are in the [comparison receipt](../results/otr_side/wan_retention/comparison.json).

## Measurement contract and excluded attempt

The existing OTR production-tail route ran
[node 92 through `scripts/otr_visual_smoke.py`](../results/otr_side/wan_retention/comparison.json).
A lab-owned sidecar held the lab GPU lease and
sampled `nvidia-smi` VRAM plus system RAM every
[200 ms](../results/otr_side/wan_retention/comparison.json), while independently
tailing the production server log. Each accepted leg used a positively
identified OTR server, and accepted legs used distinct instances. Phase 1 reused
its server only after the excluded pre-render refusal, which rendered nothing;
it was therefore not a process-fresh start. These are OTR-side diagnostic
measurements, **not** lab warm-gate certifications.

The first WAN replay is explicitly excluded. Its fixture omitted the exact
historical coverage plan and refused before rendering, so it did not reproduce
inter-shot retention. The immutable [raw invalid attempt](../results/otr_side/wan_retention/telemetry/phase1_wan_ti2v_long_first.json)
is preserved, and the [attempt audit](../results/otr_side/wan_retention/comparison.json)
marks it rejected. No number from that attempt appears in a measured row below.

## Accepted legs

All VRAM values in this table are the standalone sidecar's `nvidia-smi`
surface. `Lease/admission boundary` is the last 200 ms sample at or before the
second shot's lease event; the parenthesized value is retention above that
leg's start baseline. In the long-first arms, assembly and the next lease were
observed in the same polling interval, but the evidence definition remains
lease-bound. `Terminal` is the last sample after prompt completion/failure
cleanup and is not an inter-shot measurement.

| Engine / order | Exact topology and outcome | Baseline -> whole-child peak (GiB) | Lease/admission boundary (GiB) | Terminal (GiB) | Peak host RAM (GiB) | Child wall (s) | Evidence |
|---|---|---:|---:|---:|---:|---:|---|
| `wan_ti2v`, long -> small | [177 + 25 -> 200; then 65 refused, 20 affordable](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [1.151367 -> 12.428711](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [6.260742 (+5.109375)](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [1.260742](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [34.16412](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [514.64](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [receipt](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) |
| `fastwan_8gb`, long -> small | [177 + 25 -> 200; then 65 refused, 20 affordable](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [1.100586 -> 12.572266](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [6.433594 (+5.333008)](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [1.404297](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [39.84045](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [172.719](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [receipt](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) |
| `ltx_video`, long -> small | [169 + 169, drop 1 / trim 137 -> 200; then 169 trimmed to 65; success](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) | [1.25293 -> 14.592773](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) | [4.313477 (+3.060547)](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) | [1.180664](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) | [52.325066](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) | [313.047](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) | [receipt](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json) |
| `wan_ti2v`, small -> long | [65 succeeded; then 177 + 25 -> 200 succeeded](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) | [1.083984 -> 12.378906](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) | [6.254883 (+5.170899)](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) | [1.279297](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) | [33.746197](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) | [660.062](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) | [receipt](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json) |

The LTX peak of [14.592773 GiB](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json)
is above the lab's [14.5 GiB](../AGENTS.md)
global line. Its successful completion is useful as a retention control, but it
is a diagnostic result and **not a gate PASS**. LTX also used its own legal
frame grid, and its durable clips were
[832x448 versus WAN's 832x480](../results/otr_side/wan_retention/comparison.json).
The control holds source assets, seeds, shot targets, and shot controls
constant while allowing engine-coupled segment lengths and delivered canvas;
it is not a canvas-normalized speed/quality comparison or a shipping-profile
qualification.

HuMo was not run. It is neither a topology-equal control nor a cheap optional
leg here: its adapter declares soft-reference continuity
([`eng_humo.py:258-274`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_humo.py)),
which coverage planning routes to `JOIN_JUMP` rather than the strict
first-frame `JOIN_CHAIN`
([`coverage_plan.py:193-197`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/coverage_plan.py)).
The existing production bakeoff measured a HuMo 1.7B take at
[233.779852 seconds](../results/otr_side/humo_1_7b_bakeoff_take1.json), so it
also failed the mission's "if cheap" condition. No HuMo retention value is
inferred.

## Wrapper counters versus the second-shot lease boundary

OTR's internal `render-phase peak / post` log and the sidecar are separate
measurement surfaces. The wrapper takes `post` inside `render_clip`, before
the call returns ([`eng_wan_ti2v.py:1141-1148`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_wan_ti2v.py)).
The `BeatSession` still owns the hoisted model at that point. It closes only
after the segment loop, and assembly follows the close
([`render_driver.py:3478-3482, 3632-3638`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py)).
Therefore wrapper `post` is not the between-shot residency that the next beat
inherits.

| Leg / segment | Wrapper peak / post (MB) | Sidecar segment peak (GiB) | Evidence |
|---|---:|---:|---|
| WAN long-first, segment 0 | [9,324 / 6,725](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [8.811523](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [receipt](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) |
| WAN long-first, segment 1 | [13,026 / 8,102](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [12.428711](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) | [receipt](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json) |
| FastWan long-first, segment 0 | [8,115 / 6,887](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [7.642578](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [receipt](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) |
| FastWan long-first, segment 1 | [13,186 / 8,248](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [12.572266](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) | [receipt](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json) |

For the accepted WAN reproduction, the sample at the second-shot lease/admission boundary was
[6,411 MiB](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json),
and the sample immediately before the refusal was
[6,413 MiB](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json).
The later [1,291 MiB terminal sample](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json)
only proves that prompt failure cleanup eventually reclaimed the plateau; it
does not restore the headroom at the admission point that already refused.

The original problem log remains useful historical context, but it is not a
sidecar receipt: its two wrapper rows were
[10,874 / 8,206 MB and 13,134 / 8,190 MB](../results/otr_side/wan_retention/comparison.json),
followed by a [65-frame request with 19 affordable at 9,617 MB free](../results/otr_side/wan_retention/comparison.json).
The current reproduction independently measures the same failure shape; it
does not relabel those historical counters as sidecar measurements.

## Intent verdict: mixed warm keep and memory-policy retention

### Deliberate behavior

- WAN declares only the UNET as beat-session state and documents why CLIP is
  not hoisted ([`eng_wan_ti2v.py:403-409`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_wan_ti2v.py)).
  `prepare()` loads that UNET once and stores its result in
  `prepared["external_results"]`
  ([`eng_wan_ti2v.py:436-504`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_wan_ti2v.py)).
  Holding it across the segments of one beat is intentional.
- Beat close calls engine teardown exactly once
  ([`beat_session.py:293-315`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/beat_session.py)).
  WAN first drops the strong `external_results` reference
  ([`eng_wan_ti2v.py:545-558`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_wan_ti2v.py));
  the base then detaches tracked patchers, calls engine unload, and waits for
  stability, but explicitly does not call `unload_all_models`
  ([`motion_common.py:612-635`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/motion_common.py)).
- OTR's stronger inter-beat residue release is selected only when the engine
  ID changes ([`render_driver.py:1783-1787`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py)).
  The call-site comment explicitly says consecutive same-engine beats skip the
  flush to preserve reuse
  ([`render_driver.py:3790-3799`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py)).

### Why this is not established as a VAE leak

The WAN graph creates a VAE loader in each segment graph
([`eng_wan_ti2v.py:942-958`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_wan_ti2v.py)),
and ComfyUI loads the VAE patcher on encode/decode demand
([`sd.py:1159-1169, 1255-1269`](../../../../ComfyUI-Installs/ComfyUI/ComfyUI/comfy/sd.py)).
The repeated `WanVAE ... Staged` messages are therefore expected per-segment
load events; the message itself is emitted by
[`model_patcher.py:1985-1990`](../../../../ComfyUI-Installs/ComfyUI/ComfyUI/comfy/model_patcher.py).

More importantly, sidecar data show a plateau, not an accumulating staircase:
the long-first WAN boundary was
[6.260742 GiB](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json),
while the reversed run's boundary after its first shot was
[6.254883 GiB](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json).
Both runs later returned close to their start baselines. Those facts do not
identify the retained allocation's owner, but they contradict the simple
theory that every VAE staging permanently adds another VAE-sized block.

### Memory-policy contribution

ComfyUI's `free_memory()` keeps models until current demand requires space and
only empties cached blocks under its policy conditions
([`model_management.py:855-899`](../../../../ComfyUI-Installs/ComfyUI/ComfyUI/comfy/model_management.py)).
Its prompt executor calls `unload_all_models()` only when smart memory is
disabled
([`execution.py:836-837`](../../../../ComfyUI-Installs/ComfyUI/ComfyUI/execution.py)).
OTR's direct production wrapper has its own teardown path instead of relying on
that executor-end condition. Taken together with the explicit same-engine
flush skip, this makes the best-supported diagnosis:

> **MIXED:** intentional beat-scoped UNET keep plus intentional same-engine
> warm-reuse policy, with ComfyUI smart-memory/allocator retention surviving
> into the next admission. No additive VAE leak is demonstrated.

The nearly identical `nvidia-smi` boundaries in the two WAN orderings also
mean the external plateau alone does not fully explain why one admission
refuses and the other coverage-planned beat completes. Allocator state and the
cost-model/coverage-plan path need boundary instrumentation before ownership is
claimed.

## Cross-engine and order conclusions

- `FastWan8gbEngine` directly subclasses `WanTi2vEngine`
  ([`eng_fastwan_8gb.py:119-123`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_fastwan_8gb.py)).
  Its [same 65-to-20 refusal](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json)
  corroborates a WAN-family behavior, not an independent-family failure.
- LTX completed the semantic [200-frame chain followed by the 65-frame shot](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json).
  Its second-shot lease boundary retained [3.060547 GiB above baseline](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json),
  versus [5.109375 GiB for WAN](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json),
  but its high absolute peak prevents promotion from this diagnostic.
- With the listed fixture controls held constant, reversing shot order changed
  WAN from refusal to success. The
  [comparison receipt](../results/otr_side/wan_retention/comparison.json)
  verifies the engine, source capture, master audio, visual assets, seeds,
  targets, per-shot controls, and coverage plans were otherwise held constant.
  This is a measured planner warning, not permission to hide the defect by
  reordering content.

## Offline-policy incident

The already-booted ComfyUI-Manager startup task automatically attempted
registry refreshes during FastWan, the reverse-order WAN leg, and the LTX leg.
FastWan captured 23 `FETCH ComfyRegistry Data` page-progress markers; the
pinned Manager source proves those markers accompany uncached requests to
`api.comfy.org/nodes`. The WAN append captured `alter-list.json`,
`model-list.json`, and `custom-node-list.json`; the LTX append captured
`api.comfy.org/nodes` and `custom-node-list.json`. The evidence is preserved in
the [immutable FastWan telemetry](../results/otr_side/wan_retention/telemetry/phase3_fastwan_8gb_long_first_planned.json),
the
[immutable WAN telemetry](../results/otr_side/wan_retention/telemetry/phase4_wan_ti2v_small_first_planned.json)
and [immutable LTX telemetry](../results/otr_side/wan_retention/telemetry/phase3_ltx_video_long_first_planned.json).
No model-weight download line appears in any affected appended log, but these
appends are not a complete network audit. The automatic registry traffic
violated this lab's offline operating rule, so overall completion is
`MEASUREMENT_COMPLETE_WITH_OFFLINE_POLICY_INCIDENT`. The affected rows remain
transparent local diagnostics, not offline-clean certifications or gate
passes. Future OTR measurement boots should disable ComfyUI-Manager network
startup tasks before the server starts.

## Recommendations only -- no implementation in this mission

1. **Conditionally run the existing residue freer before a same-engine next
   beat when admission headroom is at risk.** The smallest OTR change surface
   is `_should_reclaim_between_engines()` and its call site at
   [`render_driver.py:1783-1787, 3790-3810`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py).
   Preserve the current fast path when headroom is safe; compare the reclaim
   cost against the recovered affordable-frame budget. Do not change S4's
   margin or silently resize.
2. **Instrument the exact post-close ownership boundary before choosing a
   release primitive.** At
   [`BeatSession.close`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/beat_session.py)
   and immediately before assembly in
   [`render_driver.py`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py),
   record `mem_get_info`, PyTorch allocated/reserved bytes, ComfyUI loaded-model
   identities, and live references to segment results. This separates model
   residency from allocator cache and latent/frame ownership.
3. **If allocator cache is the verified owner, add a surgical cache release
   after beat teardown, not a global model unload.** The candidate belongs in
   [`motion_common.py:612-635`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/motion_common.py)
   or the same-engine branch in `render_driver.py`, using OTR's existing
   `_otr_vram_levers` path. Re-measure warm throughput; do not weaken the
   explicit `never unload_all_models` contract without a separate design
   review.
4. **If Python references are the verified owner, narrow their lifetime at the
   segment/beat boundary.** Audit `rendered`, `segment_rows`, decoded frames,
   and external graph results around
   [`render_driver.py:3466-3638`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py)
   and [`eng_wan_ti2v.py:545-558`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/eng_wan_ti2v.py).
   Release only the proven owner; repeated VAE staging alone is not sufficient
   evidence for a VAE-specific fix.
5. **Keep shot-order sensitivity as a planner warning, not the remedy.** The
   ledger/order interface lives in the shot loop at
   [`render_driver.py:3788-3810`](../../custom_nodes/ComfyUI-OldTimeRadio/nodes/_otr_video_engines/render_driver.py).
   A warning can surface the risk while the release fix is developed, but
   automatic reordering would alter editorial intent and conceal the real
   capability limit.

## Source and worktree caveat

The OTR coding line advanced HEAD concurrently during these measurements, and
the OTR worktree already contained unrelated uncommitted changes. The sidecar
did not snapshot the complete dirty worktree at each render start. Each leg
therefore binds its immutable raw telemetry, fixture bytes, harness hash, and
committed source-object hashes, but those committed hashes are a reproducible
baseline rather than proof of every live Python byte. See each leg's
`source_binding` caveat in the [WAN receipt](../results/otr_side/wan_retention/phase1_wan_ti2v_long_first.json),
[FastWan receipt](../results/otr_side/wan_retention/phase3_fastwan_8gb_long_first.json),
[LTX receipt](../results/otr_side/wan_retention/phase3_ltx_video_long_first.json),
and [reverse-order receipt](../results/otr_side/wan_retention/phase4_wan_ti2v_small_first.json).

The Phase-3 FastWan and LTX raw telemetry embed sidecar SHA-256
`13e7fdcd735ba2db44aeac680955287f6387efe9734287293df572fe0d93bf62`, but
the exact source snapshot was not preserved. The current
`scratch/wan_retention_sidecar.py` is a different revision, and the archived
Phase-1/4 V1 sidecar is a third revision. A local Git/reflog/unreachable-object
recovery check found no copy of the Phase-3 bytes. The immutable telemetry
therefore proves that the running sidecar asserted that hash, not that this
repository can independently reproduce its exact source bytes. This is an
unverified-self-hash caveat on the Phase-3 diagnostic rows; it does not alter
their raw telemetry, fixture, or OTR-source bindings.

This lab mission did not edit OTR production code. Final repository-integrity
claims are limited to the separately verified entry/final comparison; the
pre-existing dirty worktree is not described as clean.
