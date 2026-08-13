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

**RULED by Jeffrey 2026-08-09** (viewed via the phone review page; H3 clips
judged with the clean TTS muxed over the video — the production condition).
His ranking, verbatim in substance: **"14 FP8 wins; seed 43 an OK second;
1.7B accurate, acceptable; seed 42 something seems wrong, does not seem to
track well."** The ruling is holistic (rank + fitness), recorded per-clip
below; cells reflect the ruling, not separately-judged columns.

| Category | Review clip | Lips | Onset | Identity | Human ruling |
|---|---|---|---|---|---|
| HuMo 14B FP8 | take 1 | PASS | PASS | PASS | **WINNER** |
| H3 Ref2VA seed 43 | review clip | PASS | PASS | PASS | OK second |
| HuMo 1.7B | take 1 | PASS | PASS | PASS | accurate, acceptable |
| HuMo 1.7B | take 2 | PASS | PASS | PASS | byte-identical to take 1 |
| H3 Ref2VA seed 42 | review clip | FAIL | not separately ruled | not separately ruled | "does not seem to track well" |

**Where the human verdict overturned the advisories:** (1) both per-file
advisories rated 14B behind 1.7B on the hand-geometry melt - Jeffrey ranked
14B FIRST; (2) both advisories FAILED H3 on lips outright - Jeffrey passed
seed 43 as an acceptable second, judged with clean TTS over the video.
(3) The seed 42/43 split - identical recipe, prompt, and fixtures, seed the
only variable - establishes that H3 lip quality is SEED-SENSITIVE: it can
pass and fail from the same graph. Any H3 mouth work needs a seed-curation
or retry policy, not a single blessed seed assumption.

For onset, listen without assuming the direction of error. F7 historically proposed
a **100-200 ms audio lead**, but OTR's later M1 measurement did not reproduce that
static offset and instead estimated a roughly **30-60 ms video lead**. The old F7
number is a listening target, not a current known defect. See the
[OTR M1 measurement](../../custom_nodes/ComfyUI-OldTimeRadio/docs/2026-08-02-MEASUREMENT-M1-humo-lipsync-offset.md).

## Gemini advisory (2026-08-09) — ADVISORY ONLY, human verdict rules

Jeffrey pre-screened the five review clips through Gemini. This section records that
advisory verbatim in substance. It does NOT fill the human verdict sheet above; every
cell there remains `PENDING_HUMAN` until Jeffrey's own eyes and ears rule.

| Category | Review clip | Lips | Onset | Identity | Advisory notes |
|---|---|---|---|---|---|
| HuMo 1.7B | take 1 | PASS | PASS (~30-50 ms) | PASS (solid) | Clean audio stem, stable portrait, subtle facial animation. |
| HuMo 1.7B | take 2 | PASS | PASS (~30-50 ms) | PASS (solid) | Reported visually identical to take 1 (consistent with byte-identical seed-7 artifacts). |
| HuMo 14B FP8 | take 1 | PASS | PASS | PASS (high detail) | Sharper texture and lip definition; flagged the 3.880 s truncation (97-frame cap) independently. |
| H3 Ref2VA seed 42 | review clip | FAIL (audio corrupt) | UNCERTAIN | MARGINAL | More head/neck movement; jawline morphing; TTS re-encoded to garbled noise. |
| H3 Ref2VA seed 43 | review clip | FAIL (audio corrupt) | UNCERTAIN | MARGINAL | Same audio corruption; harsher contrast; identity drift over time. |

Advisory pick: HuMo 1.7B as character-lane winner.

**Recorded caveats on this advisory:**

1. **The H3 "Lips FAIL (audio corrupt)" conflates the audition-only audio stem with
   lip performance.** Per the standing audio policy, H3's joint-latent decoded audio
   never ships: OTR discards all engine audio (`has_audio=False`, `-an` on every
   encode) and muxes the frozen TTS master. Garbled reconstruction of the conditioning
   speech is known H3 behavior (the ~0.94 reconstruction-correlation finding), not a
   production defect. The decisive H3 question — do the lips track the TTS timing well
   enough that muxing the real `tts_dialogue.wav` over the video reads as sync — was
   left UNCERTAIN by the advisory and is exactly what the human pass must answer.
   Recommended method: watch the H3 clips muted, or with the original fixture WAV
   played from timestamp zero, and judge mouth timing only.
2. Gemini's ~30-50 ms HuMo onset estimate is numerically consistent with OTR M1's
   30-60 ms video-lead estimate; treat as a corroboration hint, not a measurement.
3. The advisory's H3 jawline-morphing and identity-drift claims are specific,
   falsifiable observations for the human pass to confirm or refute.
4. Positive credibility signals: the advisory independently surfaced the 14B
   truncation and the take-1/take-2 identity, both of which match machine receipts.

### Second advisory (2026-08-09, unnamed video-analysis platform) — NEAR-ZERO WEIGHT

A second AI review was produced from an upload that the platform concatenated
into one ~11-second stream with the audio track stripped; it invented six proxy
"clips" and scored transcripts instead of sound. It cannot be mapped to specific
takes with confidence, cannot judge onset or any acoustic property, and does not
constitute a mime ear-gate ruling. Loose corroboration only: the portrait clip
with the coherent transcript (HuMo) read well; the gibberish-transcript portrait
(H3 audition stem re-transcribed) showed facial flattening/identity drift. One
new falsifiable flag for the human pass: possible finger/prop melting on a
console in the wide (H3-framed) shot. No verdict cell changes on this advisory.

### Third advisory (2026-08-09, per-file re-upload) — BEST-STRUCTURED ADVISORY

The clips were re-uploaded individually with a fresh per-file rubric. The reviewer
confirmed audio presence per file (HuMo + H3 + mime: yes; motion ladder raw
artifacts: no audio track) and followed the judge-H3-muted protocol.

| Filename | Lips | Onset | Identity | Note |
|---|---|---|---|---|
| humo_1_7b take1/take2 | PASS | in-sync | PASS | Takes confirmed identical; slight lower-jaw rigidity. |
| humo_14b_fp8 take1 | PASS | in-sync | PASS | Foreground hand/prop geometry melt on the radio console. |
| h3 seed42 (muted) | FAIL | video early ~0.5 s | MARGINAL | Continuous mouth-flapping ignoring phonetic pauses. |
| h3 seed43 (muted) | FAIL | video early ~0.5 s | MARGINAL | Over-articulated jaw unlinked to speech rhythm. |

Advisory pick: HuMo 1.7B. Motion ladder: all four clips scored near-still, a
four-way tie — this CONTRADICTS the contact-sheet receipt's claim of slow camera
translation in M3; human ranking must arbitrate. Mime ear gate: advisory FAIL on
speech-like invented audio (quoted pseudo-words "mis-string in the lost").

**Cross-advisory corroborations worth weight:** (1) the 14B hand-melt was
independently observed in both the first (mangled) review and this per-file
review; (2) the mime clip's invented audio was transcribed as near-identical
pseudo-words by two separate passes ("the string and the lost" / "mis-string in
the lost"), so the speech-like-content FAIL is probably real. **Open
discrepancy:** this reviewer described the mime clip's visual as "a silent
control room pan," not a mime performance — human eyes must confirm what the
clip actually depicts. All cells above remain advisory; the human verdict sheet
is still `PENDING_HUMAN`.

### Fourth advisory (2026-08-09, Gemini deep pass, per-file protocol)

Same per-file rubric, run through Gemini. Its platform ALSO stripped filenames;
it self-reports mapping the clips by description, audio content, and duration —
only M3 (by its ~8 s duration) and the mime (by audio) are firmly identified.

Character lane: identical to the third advisory — HuMo 1.7B PASS/in-sync/PASS
both takes; 14B PASS lips but Identity downgraded to MARGINAL on "severe" hand
geometry melt; both H3 seeds FAIL lips (video early ~0.5 s, mouth motion
unlinked to speech rhythm). **Two independent per-file advisories now agree on
every character-lane cell**, with the only delta being 14B identity
(PASS-with-defect vs MARGINAL) on the same observed hand melt.

Motion ladder: CONTRADICTS the third advisory — reports two of the short clips
as slow push-in motion (which it *assumed* to be M2 and M1; mapping unverified
and partially circular), one static (assumed M0), and M3 as real motion with
cumulative head-geometry melt on seated subjects over the extended duration.
Ranking offered: M2 > M1 > M0 > M3. Because the M0/M1/M2 mapping was guessed
from the very visual qualities being ranked, treat the ordering as weak; the
robust claims are "at least some short-ladder clips show push-in motion"
(vs the third advisory's four-way near-still tie) and "M3 accumulates geometry
melt." Human ranking with known filenames arbitrates.

Mime ear gate: FAIL again — synthesized English speech hallucinations quoted as
"the string and the lost...", the third sighting of this acoustic fingerprint.
Visual described as a "static, unpopulated control room environment," the
SECOND advisory to report no visible mime performer. Sheet remains
`PENDING_HUMAN`.

**Correction (2026-08-09, after checking the recipe):** the "no mime on
screen" observations are NOT a defect. "Mini Mime" is the lab codename for the
capability under test — H3 inventing audio with no audio conditioning, i.e.
performing without a script — not a literal mime performer.
`recipes/h3_mime_i2v_ledger_music_closing_8s.json` conditions on a control-room
scene still and prompts a restrained unpopulated room with "ambient room tone
and synchronized diegetic sound effects only ... No dialogue". The delivered
visual matches the recipe by design; both advisories described it accurately.
The live failure is audio-side only, and it is sharper than first recorded:
the prompt explicitly forbade dialogue, yet the invented audio contains
speech-like garble — an unconditioned-audio prompt-adherence observation.

**Ear-gate criterion relaxed (operator ruling 2026-08-09):** Jeffrey ruled
"if H3 wants talking on its own, fine — not a fail." Speech-like content is
no longer an automatic FAIL; the three advisory FAILs above were judged
against the stricter retired criterion and are moot on that axis. The gate is
now a holistic human audition: does the invented audio work with the scene?
`PENDING_HUMAN` on that question.

## Repository state

The OTR worktree was already dirty before this render-only session. Entry and final
HEAD, status lines, and every file in the captured hash scope match, so production
code was not altered; the worktree cannot honestly be called clean. The pre-existing
untracked `kibitz/` top-level marker also matches, but nested contents were outside the
byte-identity scope and are not claimed unchanged. See the
[worktree-integrity receipt](../results/otr_side/otr_worktree_integrity.json). The lab
owns the sidecar, copied clips, receipts, and this report.
