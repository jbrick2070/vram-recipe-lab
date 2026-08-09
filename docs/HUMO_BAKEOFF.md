# HuMo Production-Lane Bakeoff

Date: 2026-08-09

## Result

Measurement coverage is **COMPLETE**: three HuMo clips were measured through OTR's
existing production wrapper, and the two receipt-bound H3 challenger clips were
already complete. The character-lane decision is **PENDING_HUMAN** across all five
review clips and four categories: HuMo 1.7B (two takes), HuMo 14B FP8, H3 seed 42,
and H3 seed 43. No OTR-side measurement is represented as a lab-gate pass.
[Five-clip comparison receipt](../results/otr_side/humo_character_lane_bakeoff.json)

The machine evidence separates two useful facts. HuMo 1.7B completed the nearly
duration-matched workload at a lower render-to-artifact cost than either H3 take,
while H3 used much less peak VRAM and host RAM. HuMo 14B reached the production
wrapper's 97-frame cap, so its shorter 3.880-second output is not a normalized speed
competitor to the 5.16-second clips. Quality, synchronization, onset, and identity
still belong to Jeffrey's eyes and ears.

## Fixture and route contract

Every take used byte-identical copies of the same two conditioning fixtures:

| Fixture | SHA-256 | Contract evidence |
|---|---|---|
| `fixtures/portrait.png` | `3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad` | [HuMo 1.7B take 1 receipt](../results/otr_side/humo_1_7b_bakeoff_take1.json); [H3 seed 42 receipt](../results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json) |
| `fixtures/tts_dialogue.wav` | `30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1` | [HuMo 1.7B take 1 receipt](../results/otr_side/humo_1_7b_bakeoff_take1.json); [H3 seed 42 receipt](../results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json) |

The source TTS fixture is **10.000 seconds**, but fixture-byte parity is not
workload-duration parity. HuMo 1.7B delivered **480x832, 129 frames at 25 fps / 5.160
seconds**; H3 delivered **864x480, 124 frames at 24 fps / 5.167 seconds**; and HuMo
14B delivered **480x832, 97 frames at 25 fps / 3.880 seconds**. The corresponding
[HuMo 1.7B](../results/otr_side/humo_1_7b_bakeoff_take1.json),
[H3](../results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json), and
[HuMo 14B](../results/otr_side/humo_14b_fp8_bakeoff_take1.json) receipts carry those
probes and durations.

The OTR leg used the smallest existing single-clip route:
`scripts/_otr_single_engine_smoke.py` through the production
`OTR_VideoRenderBatch` wrapper, booted by `scripts/_otr_soak_server_launch.cmd` in
the `HUMO` lane. The production engine IDs were `humo_1.7B` and `humo`; no graph,
engine implementation, or production profile was edited. A lab-owned sidecar sampled
`nvidia-smi` VRAM and `psutil.virtual_memory().used` every 200 ms. For HuMo, wall time
means sidecar command start through durable artifact save. Each receipt preserves the
boot lane and exact argv.

The single-clip probe has no `--profile` argument. Therefore
`otr_w45_humo_1_7b` and `otr_w45_humo` were production-profile references for the
equivalent engine defaults, not applied profile JSONs, and no full 45-word campaign
ran. The registered portrait 14B FP8 engine ID is `humo`. The receipts pin the exact
runner and production-wrapper source hashes so this distinction is auditable.

## Five-clip measurement table

`Wall/output` is `render-to-artifact seconds / delivered video seconds`. HuMo peak
RAM is system-wide used RAM from the sidecar; the H3 receipts' `peak_host_ram_gb`
uses the lab's corresponding host-RAM measure. HuMo rows are OTR-side measurements,
not warm-cache certifications or lab-gate results.

| Category | Clip | Seed | Delivered video | Wall to artifact | Wall/output | VRAM baseline -> peak | Peak host RAM | Measurement state | Evidence |
|---|---|---:|---|---:|---:|---:|---:|---|---|
| HuMo 1.7B | [take 1](../outputs/humo_1_7b_bakeoff_take1.mp4) | 7 | 480x832, 129f @ 25 fps, 5.160 s | 233.779852 s | 45.306173 | 2.267578 -> 15.118164 GiB | 35.136196 GiB | OTR-side measured; no lab gate | [receipt](../results/otr_side/humo_1_7b_bakeoff_take1.json) |
| HuMo 1.7B | [take 2](../outputs/humo_1_7b_bakeoff_take2.mp4) | 7 | 480x832, 129f @ 25 fps, 5.160 s | 207.513477 s | 40.215790 | 2.261719 -> 15.231445 GiB | 36.078560 GiB | OTR-side measured; no lab gate | [receipt](../results/otr_side/humo_1_7b_bakeoff_take2.json) |
| HuMo 14B FP8 | [take 1](../outputs/humo_14b_fp8_bakeoff_take1.mp4) | 7 | 480x832, 97f @ 25 fps, 3.880 s | 245.943975 s | 63.387622 | 1.781250 -> 14.984375 GiB | 51.629864 GiB | OTR-side measured; no lab gate | [receipt](../results/otr_side/humo_14b_fp8_bakeoff_take1.json) |
| H3 Ref2VA seed 42 | [review clip](../outputs/h3_r2v_refaudio_tts_lipsync_exact_seed42_out_00001_.mp4) | 42 | 864x480, 124f @ 24 fps, 5.166667 s | 305.3 s | 59.090319 | 2.15 -> 6.71 GiB | 27.27 GiB | Cold machine gate only | [receipt](../results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json) |
| H3 Ref2VA seed 43 | [review clip](../outputs/h3_r2v_refaudio_tts_lipsync_exact_seed43_out_00001_.mp4) | 43 | 864x480, 124f @ 24 fps, 5.166667 s | 297.8 s | 57.638706 | 5.23 -> 6.51 GiB | 27.32 GiB | Cold machine gate only | [receipt](../results/h3_r2v_refaudio_tts_lipsync_exact_seed43_run1.json) |

The H3 prose duration of 5.167 seconds is rounded; the H3 cost rows divide by the
receipt's exact 5.166667-second video duration. The frozen
[five-clip package](../results/otr_side/humo_character_lane_bakeoff.json) independently
records all five derived costs and receipt hashes.

The production single-clip wrapper exposes a fixed request seed of **7**. Both 1.7B
runs therefore document seed 7; their cache-busters forced separate executions but
did not alter generation. Their native video artifacts are byte-identical, which is
repeatability evidence at that fixed seed, not an alternate-seed quality test.
[Take 1 receipt](../results/otr_side/humo_1_7b_bakeoff_take1.json) and
[take 2 receipt](../results/otr_side/humo_1_7b_bakeoff_take2.json)

All three HuMo absolute peaks exceed the lab's 14.5 GiB promotion line, but these runs
were deliberately measured in the OTR production lane and never received a lab gate.
The receipts preserve absolute baseline and peak values so the result is not relabeled
after the fact.

## Review soundtrack policy

The production HuMo wrapper's native clips are silent by policy. Those originals are
preserved as `*_native_silent.mp4`. The five-clip review package uses HuMo copies with
the exact source `tts_dialogue.wav` muxed from timestamp zero while stream-copying the
video; no model-generated soundtrack replaced it. The H3 clips retain their native
joint-latent decoded audio. Fixture-byte parity therefore proves the same conditioning
source, while the review-audio delivery paths remain engine-appropriate.

## Human verdict sheet

| Category | Review clip | Lips | Onset | Identity |
|---|---|---|---|---|
| HuMo 1.7B | take 1 | `PENDING_HUMAN` | `PENDING_HUMAN` | `PENDING_HUMAN` |
| HuMo 1.7B | take 2 | `PENDING_HUMAN` | `PENDING_HUMAN` | `PENDING_HUMAN` |
| HuMo 14B FP8 | take 1 | `PENDING_HUMAN` | `PENDING_HUMAN` | `PENDING_HUMAN` |
| H3 Ref2VA seed 42 | review clip | `PENDING_HUMAN` | `PENDING_HUMAN` | `PENDING_HUMAN` |
| H3 Ref2VA seed 43 | review clip | `PENDING_HUMAN` | `PENDING_HUMAN` | `PENDING_HUMAN` |

For onset, listen without assuming the direction of error. F7 historically proposed
a **100-200 ms audio lead**, but OTR's later M1 measurement did not reproduce that
static offset and instead estimated a roughly **30-60 ms video lead**. The old F7
number is a listening target, not a current known defect. See the
[OTR M1 measurement](../../custom_nodes/ComfyUI-OldTimeRadio/docs/2026-08-02-MEASUREMENT-M1-humo-lipsync-offset.md).

## Repository state

The OTR worktree was already dirty before this render-only session. Entry and final
HEAD, status lines, and every file in the captured hash scope match, so production
code was not altered; the worktree cannot honestly be called clean. The pre-existing
untracked `kibitz/` top-level marker also matches, but nested contents were outside the
byte-identity scope and are not claimed unchanged. See the
[worktree-integrity receipt](../results/otr_side/otr_worktree_integrity.json). The lab
owns the sidecar, copied clips, receipts, and this report.
