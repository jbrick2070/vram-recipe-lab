# H3 Unconditioned Music Study

Status: **MACHINE COMPLETE; HUMAN REVIEW `PENDING_HUMAN`.**
Campaign `h3music-20260810T023023Z-97ca44b2-attempt-005` completed all 11
cold/warm pairs at lifecycle row 88 / ledger sequence 88 / campaign sequence
23. The 22 canonical study legs are machine-valid evidence only; they do not
establish that H3 composes music or that any clip is visually acceptable.

## Question

When MiniMax H3 receives a picture but no audio-conditioning input, does its
joint latent produce repeatable, prompt-responsive, duration-stable native
music or coherent sound? The graph's own sampled audio must reach
`VAEDecodeAudio -> CreateVideo.audio` untouched. There is no input audio and no
post-render mux.

The prepared study separates four questions:

1. **Job 0 — motion-prompt sanity:** exact scene control A, small wordless
   body/hands action B, and a larger start/middle/end physical beat C.
2. **Job 1 — seed repeatability:** the exact scene prompt at seeds 42–46.
3. **Job 2 — audio-language response:** exact A, warm wordless orchestral score
   B, and synchronized diegetic SFX-only/no-dialogue C at seed 42.
4. **Job 3 — duration survival:** exact scene prompt at 124, 192, and 277 model
   frames at seed 42.

No automated or agent-authored quality verdict is permitted. Native clips are
delivered for Jeffrey's ears and eyes.

## Historical evidence boundary

The remembered positive-music artifact
`outputs/h3_r2v_best_out_00001_.mp4` (SHA-256
`51d803d53a61e67d3e2dd5772f817da6edc1b8bdc5571e851463037adf2d2d5f`)
is a **lineage/listening anchor only**. Its receipt binds recipe SHA
`599718d4ee5b1a04309a4352cded8167c4e51075a9f858bdbf3468a53aae6a4e`,
whose obsolete nested `ref_images` container was not the current flat dotted V3
socket. It therefore cannot prove picture-conditioned music behavior.

The current topology-safe source is `recipes/h3_r2v_best.json` at SHA-256
`20e584cc016bdc5bdb857b00923c7ae838174724e3c20be0dfc322a809392eda`.
Its flat-V3 run-4 artifact SHA is
`b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed`,
but no ear verdict was recorded. It also ran on the ordinary
Manager-disabled lane, so it is not execution-reusable under this campaign's
new runtime-offline proof requirement.

The prior directed-SFX mime result is hypothesis context only, pinned by
`results/comparisons/h3_mime_unconditioned.json` SHA-256
`eff2269b8127e6895a18adc8a883eb135d19d36e5550ca5d1e62adad326c1c61`.

## Immutable matrix and exact reuse

The exact A/seed-42/124-frame recipe is shared across Job 0A, Job 1 seed 42,
Job 2A, and Job 3 f124. Reuse is valid only if one cold/warm pair proves the
same immutable recipe SHA, fixtures, model fingerprints, server identity,
offline-Manager evidence, receipts, and artifacts. This reduces 14 logical
cells to **11 physical cells / 22 actual executions**, saving three pairs / six
executions without dropping a comparison.

| Pair | Physical recipe | Logical role(s) | Single generation variable vs shared A |
|---:|---|---|---|
| 1 | `h3_unconditioned_music_scene_seed42_f124` | Job 0A; Job 1 seed42; Job 2A; Job 3 f124 | shared exact control |
| 2 | `h3_unconditioned_music_motion_small_seed42_f124` | Job 0B | prompt only |
| 3 | `h3_unconditioned_music_motion_large_seed42_f124` | Job 0C | prompt only |
| 4 | `h3_unconditioned_music_scene_seed43_f124` | Job 1 seed43 | seed only |
| 5 | `h3_unconditioned_music_scene_seed44_f124` | Job 1 seed44 | seed only |
| 6 | `h3_unconditioned_music_scene_seed45_f124` | Job 1 seed45 | seed only |
| 7 | `h3_unconditioned_music_scene_seed46_f124` | Job 1 seed46 | seed only |
| 8 | `h3_unconditioned_music_score_seed42_f124` | Job 2B | prompt only |
| 9 | `h3_unconditioned_music_sfx_seed42_f124` | Job 2C | prompt only |
| 10 | `h3_unconditioned_music_scene_seed42_f192` | Job 3 f192 | frame length only |
| 11 | `h3_unconditioned_music_scene_seed42_f277` | Job 3 f277 | frame length only |

The builder validates all one-variable graph diffs after ignoring only the
unique output filename prefix used for evidence isolation. The Job 0 action
prompts contain no audio request and avoid `restrained`, `slow`, `stable`, and
`subtle`.

## Offline-Manager contradiction and resolution

The ordinary H3 boot deliberately uses `--disable-all-custom-nodes` with only
GGUF and KJNodes whitelisted, so it cannot truthfully emit a
`[ComfyUI-Manager] network_mode: offline` line. The narrow test-only solution
is explicit `--manager-offline-test` runner authorization:

- `boot_lab_server.cmd` remains byte-for-byte unchanged and Manager-disabled;
- the runner selects the separate test-only
  `boot_h3_manager_offline_test.cmd`, whose exact whitelist adds only
  `ComfyUI-Manager`;
- each cold/warm pair gets a new, absent server log under
  `results/h3_unconditioned_music_campaign/server_logs/`;
- the runner creates that log atomically with exclusive-create at byte zero
  and writes one canonical preboot state record before the boot script may
  append to it;
- that byte-zero record proves the Manager `startup-scripts` directory is
  empty; `restore-snapshot.json`, `install-scripts.txt`, and
  `pip_auto_fix.list` are absent; Manager's four dependency imports succeed;
  and the installed torch/frontend/OpenCV package state makes `PIPFixer` a
  no-op; the proof also requires `use_uv=False` and a successful local-only
  `venv python -m pip list` view matching the distribution metadata;
- those no-install/no-restore conditions are recomputed after Manager
  prestartup, after each render, and at campaign boundaries; any drift aborts;
- the advisory effective config must say `offline`, while the authoritative
  gate is exactly one server-reported `network_mode: offline` value before
  Manager startup completion and before the first prompt;
- any missing, public, duplicate, late, network/fetch/update, dependency-install,
  restore, startup-script, package-fixer, or Manager-restart marker aborts;
- ANSI stripping is applied only after the raw canonical preboot line; a BOM,
  ANSI prefix, whitespace, or any other byte before that marker fails the
  byte-zero gate;
- offline non-secret environment pins include Hugging Face/Transformers plus
  `PIP_NO_INDEX=1` and `UV_OFFLINE=1`; Manager/core/prestartup/PIPFixer source
  hashes and the preboot state hash are bound into each receipt and run
  identity;
- the log is rescanned after each render and again after shutdown.

This is not a fabricated receipt line and does not change the default boot.

## Execution and recovery chain

Every canonical leg used `run_recipe.py`, a unique executor-cache nonce, the
SageAttention-free Manager-offline test lane, `--disable-pinned-memory`,
`cache-classic`, and direct `reserve-12gb` pressure. This is a reserve lane,
not a `clamp-12gb` target-card claim. Each cold/warm pair ran sequentially on
one owned server and shut that server down after the warm leg.

### Attempts 001–003

Attempt-001 produced control run 1, then stopped before a warm leg because the
campaign verifier looked for the queued-prompt SHA in the wrong receipt
subobject and the ownership monitor applied the ordinary H3 argv shape to this
Manager test lane. The guarded manual cleanup remains recorded in the
exclusive-create 7,610-byte receipt with SHA-256
`e153ba610110e1fb5a637d1ddfa4f0144f60982e88be018d08534f7ddf4371df`.
Control run 1 records 7.58 GiB / 908.8 s and artifact
`h3_unconditioned_music_scene_seed42_f124_out_00001_.mp4`, but it has no
same-server warm mate. It is the one original orphan cold and is not one of the
22 canonical study legs.

Attempt-002 preserved that orphan, then created canonical pair 1 as run 2
cold/configuration 1 and run 3 warm/configuration 2 on one server. The warm
child returned 120 after receipt, artifact, cache, and shutdown evidence were
complete but before `pair_verified` could be appended. The cause remains
`UNKNOWN_UNPROVED`. The pair passed the frozen verifier and was sealed for
carry-forward by
`h3music-20260810T023023Z-97ca44b2-attempt-002-return120-recovery.json`
(31,555 bytes, SHA-256
`32a9e9403388d76e190082a04937fb83446b4b3617c0a2178cd4eb673de4911d`).

Attempt-003 carried pair 1 and completed pair 2. Its warm child returned 0 and
the owned server exited, but Windows failed to unlink `.server.pid`; the
post-shutdown clean-state gate therefore kept the attempt FAILED. The
exclusive-create stale-PID recovery
`h3music-20260810T023023Z-97ca44b2-attempt-003-stale-pid-recovery.json`
(16,216 bytes, SHA-256
`306d44d4778b7a20921bc40df2594b6a11c0b11030e20e1629cd06f2dcd7442d`)
classifies the incident as
`EXPECTED_SERVER_EXITED_STALE_PID_RECEIPT_UNLINK_FAILED`, carries pairs 1–2,
and requires the next attempt to re-prove a clean start.

### Attempt-004 timeout and corrected sealed recovery

Attempt-004 passed that clean preflight, carried pairs 1–2, and completed pairs
3–9. Pair 10 run 1 then reached all 20/20 sampler steps and began the audio/video
decode stage, but the 1,800-second completion timeout expired before any output
artifact finalized. Its immutable receipt remains
`TIMEOUT (exceeded 1800s; owned server shutdown proved)`, with 10.69 GiB peak,
1.97 GiB baseline, 1,800.0 s wall time, and no artifact. It is the one failed
historical timeout and is not a canonical study leg.

The first sealed timeout recovery remains immutable at 59,642 bytes / SHA-256
`a76d05fb4d0d01afa90b705ba654af6c8b56344bd93478e653fa9a3146e1f88f`,
but it recorded the wrong pair-11 recipe and is classified
`UNUSABLE_RESUME_AUTHORITY`. It must not authorize a render. The corrected
exclusive-create recovery
`h3music-20260810T023023Z-97ca44b2-attempt-004-timeout-recovery-correction-001.json`
(60,939 bytes, SHA-256
`fef1ef0401b5e4f13dc11b7405224e6b792a1a18c3b607fce806468f598f7dcd`)
is the sole attempt-005 authority. It carries pairs 1–9, schedules pair 10 as
run 2 cold/run 3 warm, and schedules the corrected
`h3_unconditioned_music_scene_seed42_f277` pair 11 as run 1 cold/run 2 warm:
four new legs total.

### Attempt-005 terminal

Attempt-005 carried nine pairs and executed two pairs / four new legs. Pair 10
used artifacts `...f192_out_00001_.mp4` and
`...f192_out_00002_.mp4`; the preserved failed run 1 did not consume an
artifact index. Pair 11 used `...f277_out_00001_.mp4` and
`...f277_out_00002_.mp4`.

The append-only lifecycle terminates at row/ledger sequence 88, attempt
campaign sequence 23, event `campaign_completed`, status `COMPLETE`, event
SHA-256
`7813ad0be79a53b9e8265e7ef784b28beef9d222cc0007ee265c08abedd50c48`.
The terminal counts are 11 pairs, nine carried, two executed, four new
executions, and 22 canonical study legs, plus one original orphan cold and one
failed historical timeout. Its final state records no GPU/suite lock, no
`.server.pid`, no quarantine, and no listener on 8199.

### Durable operator-gap audit — not a launch receipt

The planned attempt-005 operator
`results/h3_unconditioned_music_campaign/operator_logs/h3music-20260810T023023Z-97ca44b2-attempt-005/launch.json`
was not published; this is the post-run recorder gap. It remains absent. No
exact process end time or independently recoverable exit code is claimed, and
no `launch.json` may be reconstructed from the campaign's self-report.

The separate exclusive-create post-run audit
`results/h3_unconditioned_music_campaign/recoveries/h3music-20260810T023023Z-97ca44b2-attempt-005-operator-gap-recovery.json`
is 38,010 bytes with SHA-256
`21abba5bffabd2ad9a49365d488adddd00b4a542955c81fbbfb3a8dff1122289`.
It rehashes the terminal lifecycle, finalized operator streams, 22 canonical
receipts/artifacts, and 11 Manager logs while explicitly recording
`launch_receipt_absent=true`,
`must_not_substitute_for_launch_receipt=true`, and
`no_certification_effect=true`. It does not grant campaign completion, pair
certification, a human judgment, promotion, or study pass. The lifecycle's
machine `COMPLETE` state stands on its own evidence.

## Canonical machine measurements

Every value below comes from the named immutable cold/warm receipts. A receipt
entry such as `run1 / run2` means
`results/<physical-recipe>_run1.json` /
`results/<physical-recipe>_run2.json`. Video/audio seconds are container-probe
measurements, not a listening judgment. Artifact indices are the output
suffixes under `outputs/`.

| Pair | Source attempt | Cold / warm receipt | Baseline GiB cold / warm | Peak GiB cold / warm | Wall s cold / warm | Frames @ fps; video / audio s | Artifact index cold / warm |
|---:|---|---|---:|---:|---:|---|---|
| 1 | attempt-002 | `run2 / run3` | 1.93 / 3.49 | 7.63 / 7.88 | 904.4 / 895.1 | 124 @ 24; 5.166667 / 5.167 | `00002 / 00003` |
| 2 | attempt-003 | `run1 / run2` | 1.69 / 3.42 | 7.58 / 7.58 | 902.2 / 893.0 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 3 | attempt-004 | `run1 / run2` | 1.69 / 3.84 | 8.11 / 8.62 | 1,026.6 / 1,006.8 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 4 | attempt-004 | `run1 / run2` | 2.40 / 4.47 | 9.18 / 8.96 | 957.6 / 928.8 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 5 | attempt-004 | `run1 / run2` | 2.24 / 3.98 | 8.43 / 8.22 | 1,036.3 / 1,012.1 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 6 | attempt-004 | `run1 / run2` | 1.99 / 3.73 | 7.88 / 8.12 | 895.2 / 939.7 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 7 | attempt-004 | `run1 / run2` | 1.98 / 3.72 | 7.90 / 7.88 | 911.3 / 882.3 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 8 | attempt-004 | `run1 / run2` | 1.99 / 3.76 | 7.88 / 8.13 | 887.9 / 891.5 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 9 | attempt-004 | `run1 / run2` | 1.97 / 3.74 | 7.87 / 7.86 | 905.7 / 897.1 | 124 @ 24; 5.166667 / 5.167 | `00001 / 00002` |
| 10 | attempt-005 | `run2 / run3` | 1.98 / 2.52 | 10.60 / 10.44 | 1,826.8 / 1,844.6 | 192 @ 24; 8.000000 / 8.000 | `00001 / 00002` |
| 11 | attempt-005 | `run1 / run2` | 1.98 / 2.15 | 13.65 / 13.83 | 3,535.3 / 3,527.1 | 277 @ 24; 11.541667 / 11.542 | `00001 / 00002` |

All 11 cold receipts record `PASS (cold)`; all 11 warm receipts record `PASS`
with `warm_pass=true`. All 22 record valid measurement, a fresh cache-busted
execution, unchanged same-pair server identity/provenance, an AAC stream, and
the shared 1344x768 H.264/24 fps container contract. The largest canonical
peak is pair 11 warm at 13.83 GiB, below the 14.5 GiB ceiling and outside the
14.25–14.50 GiB marginal band. None of these machine gates is a quality rating.

Each cold/warm pair is byte-identical at the artifact layer. This is an
integrity/repeatability fact only:

| Pair | Bytes per cold or warm artifact | Shared artifact SHA-256 |
|---:|---:|---|
| 1 | 909,151 | `b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed` |
| 2 | 860,629 | `92d044cd5d6f2bffb9e53b5ff5b6917670ff52bbb363309ba0473123ac398541` |
| 3 | 1,127,954 | `3f7b98cdd8187972e2c9119006ac56d2921e071b9b4adc977e8adc8eb81beabe` |
| 4 | 852,700 | `cff95b06e823ef91209287cc6dee914a6f4f5e1f161b152e93ece00b67b84ca2` |
| 5 | 1,236,749 | `c17326216587c63dff23b01ec6964720c9ecfcc110575b493b47435605f9c7cf` |
| 6 | 951,919 | `aa1de4095d44112195407fe23beeacdd93ca84b5b9d4927651013bf3528ad020` |
| 7 | 1,270,285 | `bae207d958cf0bd1fed62eba770b716588cccf126eeeaea7b6c77749bf6a5890` |
| 8 | 778,629 | `23cff43d00b2de2a57da492b4e5942606cf25217b522927d19bad208a58d763a` |
| 9 | 853,218 | `70ffb6fa94cec7ecae2ed103b5373a689c5563f4e8feb8f09d3c173a41f81041` |
| 10 | 1,734,045 | `0c6a50a389991ffc5f6b13cc2474c78a484be359014c31f3251302c2c12109ef` |
| 11 | 2,389,745 | `ebd82c654297d938ba2cfdd68d3877af945d797022507433117ee665cc1c22e0` |

## Human review

Machine validation does not answer any of the following fields:

| Human-review field | Value (RULED by Jeffrey 2026-08-10 unless noted) |
|---|---|
| Native audio/music occurrence and coherence | **Music occurs in exactly ONE clip: Q4-B (score-request prompt) - "yes, cinematic score."** Everything else: sound effects, footsteps, an "ah" vocalization, or Mandarin speech. |
| Job 0 body-motion response (AUDIO) | Control: subtle SFX + one "ah", no music. Q2-B small motion: more pronounced SFX, no "ah". Q2-C: not separately ruled. |
| Job 0 body-motion response (VISUAL - does the body act?) | `PENDING_HUMAN` - not ruled this pass. |
| Job 1 seed-level audio/music hit-rate | **0 of 5 produce music on the scene-only prompt.** Seed 42: subtle SFX+"ah"; seed 43: not separately ruled; seeds 44 and 45: MANDARIN SPEECH (the -13.9 LUFS spikes are talk, not music); seed 46: subtle SFX. |
| Job 2 score-vs-SFX prompt comparison | **B (score request): a real cinematic score - but MELANCHOLY.** Operator: "not for a tough native drama radio, but if it was for a more lighthearted piece, yes." So: composition PASS, mood UNSTEERED - the prompt asked for "warm orchestral" and got melancholy. C (SFX-only constraint, the previously rejected style): rejected again - effects only. |
| Job 3 duration-survival | 192f: Mandarin speech. 277f: sound effects, footsteps. No music survival data (Job 3 used the scene-only prompt, which never produces music). |
| Visual integrity comparison | `PENDING_HUMAN` - not ruled this pass. |
| Overall preference / selected clip | Q4-B is the only musical artifact. |

**Ruling synthesis.** On the current flat-V3 lane, H3's unconditioned audio
defaults to diegetic SFX and drifts into Mandarin dialogue at some seeds
(MiniMax's training bias showing through); it composes music ONLY when the
prompt affirmatively asks for a score. The operator's prompting doctrine is
REFINED, not overturned: **positive requests work ("warm orchestral score
underneath" -> real score); negative constraints still fail ("SFX only, no
dialogue" -> rejected, twice).** Ask for what you want; never forbid.
CAVEAT: all of this is measured on a lane the descriptor synthesis (above)
suspects is audio-attenuated by the flat-V3 topology migration - the origin
clip made music from a scene-only prompt on the OLD topology. The topology
A/B decides whether scene-only music is recoverable; the score-request path
works TODAY regardless.

**Benchmark ruling (operator, 2026-08-10):** the origin clip's music
(`h3_r2v_best_out_00001_.mp4`, OLD nested-container topology, scene-only
prompt) is "great music - better than any I heard here," INCLUDING the Q4-B
score. The old-topology artifact therefore outperforms the current lane even
when the current lane is explicitly asked for music. This promotes the
topology A/B from an academic check to the HIGHEST-VALUE follow-up: the best
audio this lab has ever produced came from wiring that no longer exists in
the current recipes.

Recommendation: the music lane is VIABLE TODAY via score-request prompting
(mood steering unproven - Q4-B came out melancholy against a "warm" ask), and
potentially far better if the topology A/B recovers the origin behavior.
Follow-ups in priority order: (a) topology A/B, (b) mood steering, (c)
score-prompt seed sweep, (d) score-prompt duration survival.

## Descriptor synthesis (driver, 2026-08-10) - the topology lead

The machine descriptors (docs/H3_MUSIC_MACHINE_DESCRIPTORS.md, Track B only -
the analyzer honestly reported zero audio perception and skipped subjective
listening) surface a connection this report already contained without drawing:

**Pair 1's artifact and the flat-V3 rebuild of `h3_r2v_best` are the SAME file**
(both SHA `b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed`,
per this report's own matrix and historical-boundary sections). The
descriptors measure that file as NEAR-SILENT: >5.18 s below -40 dB in a
5.167 s clip, signal near the -70 LUFS floor. The remembered origin artifact
(`h3_r2v_best_out_00001_.mp4`, obsolete nested `ref_images` container, same
portrait and prompt) carries the music the operator independently recalled.

Same inputs, new socket topology, audio drops ~40 dB toward the digital
floor. The leading hypothesis is therefore a WIRING/TOPOLOGY regression in
the flat-V3 migration (the same failure shape as the LTX mask=1 defect that
silently discarded audio), NOT a model-capability conclusion. Corroborating
pattern in the descriptors: audio "survives" exactly where extra conditioning
pressure exists - the score-request prompt (only continuous+periodic clip),
motion prompts (flux and mid-band energy jump), and two of five seeds
(-13.9 LUFS spikes) - as if the audio branch is attenuated but not severed.

Proposed follow-up (one pair, cheap): render the obsolete nested-container
graph and the flat-V3 graph side by side, same seed/prompt/fixtures, and diff
the audio branches of the two graphs node by node. If the old graph still
makes music on today's box, the regression is confirmed and the diff IS the
bug report. Ears still rule on everything; PENDING_HUMAN unaffected.

An independent file-reading audit (Antigravity CLI) verified this report
against disk evidence. **VERDICT: ACCEPT WITH DOCUMENTED LIMITATIONS** -- the
measurement table, recipe SHAs, artifact hashes, and the 11 canonical
Manager-offline logs match disk; quality judgments correctly remain
PENDING_HUMAN; HOLD stands.

Corrections the audit established (recorded here because the audit itself
changed no files):

- **Pair 10 timeout values:** the successful attempt-005 pair-10 legs ran
  under a 3,600-second timeout (not 5,400; the failed historical leg used
  1,800), completing at 1,826.8 / 1,844.6 s. Pair 11 used 5,400 s. The
  measured 192-frame executions exceeded 1,800 s ON THIS LANE; that does not
  prove every 192-frame render will.
- **Attempt-001 cleanup filename** is a minor traceability omission, not a
  factual mismatch: the documented 7,610-byte size + SHA identify
  `h3music-20260810T023023Z-97ca44b2-manual-cleanup.json` exactly.
- **Full physical evidence scope:** 24 numbered run receipts, 11
  current-result aliases, 23 MP4 files, 13 server logs, 11 recipes, six
  recovery receipts, plus the complete lifecycle ledger (canonical subset: 22
  receipts, 22 artifacts, 11 Manager logs).
- **Launch provenance:** attempt-005's missing live `launch.json` leaves
  operator-level launch/exit provenance incomplete; the post-run gap audit
  rehashes everything finalized but cannot substitute for it. Execution-level
  evidence is intact.

Methodological limits the audit names (carry into any promotion decision):
Jobs 0/2/3 are seed-42-only, so those comparisons may carry seed-specific
effects; one reference image, so image-level generalizability is untested;
byte-identical cold/warm pairs prove exact-run repeatability, not stochastic
variation or global determinism; container checks do not classify the audio;
the `reserve-12gb` lane measures reserve pressure on this 16 GiB box and is
NOT small-card emulation; the shared control preserves every planned
comparison but is not an independently replicated baseline per arm.
