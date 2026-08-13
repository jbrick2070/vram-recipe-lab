# QUEUED LAB MISSION 2 -- H3 music: topology A/B + mood steering

Written 2026-08-10. Mission 1 (the 22-leg unconditioned study) is COMPLETE --
results, audit, and all operator rulings live in
`docs/H3_UNCONDITIONED_MUSIC.md`. This file now carries the FOLLOW-UP mission.
Paste the fenced block below into a lab agent window when the GPU is free.

## What mission 1 established (operator-ruled)

- Scene-only prompts on the current flat-V3 lane: NO music, 0 of 5 seeds --
  subtle SFX, one "ah", and Mandarin speech drift at two seeds.
- Score-request prompt: a REAL cinematic score (the only one), but MELANCHOLY
  against a "warm" ask -- composition works, mood steering unproven.
- The SFX-only/no-dialogue constraint style: rejected, twice.
- Doctrine refined: POSITIVE requests work, NEGATIVE constraints fail.
- **Benchmark:** the origin clip (`h3_r2v_best_out_00001_.mp4`, OLD nested
  ref_images topology, scene-only prompt) is better music than anything in
  the study INCLUDING the score-request clip. The best audio ever produced
  here came from wiring that no longer exists in current recipes.
- Descriptor synthesis: pair 1's artifact == the flat-V3 rebuild of the origin
  recipe (same SHA), measured near-silent. Leading hypothesis: the flat-V3
  migration attenuated the audio branch (LTX mask=1 failure shape).
- Production design note (operator): "our music will have to be well tuned to
  the scene, not just 'orchestral'" -- in a joint AV latent the scene itself
  directs the score, so OTR's future music lane must derive its score request
  from the beat's dramatic intent (which the story pipeline already knows),
  never from boilerplate.

## The prompt to paste

```
LAB MISSION -- H3 music follow-up: topology A/B first, then mood steering.
Read AGENTS.md, RESULTS.md, then docs/H3_UNCONDITIONED_MUSIC.md (rulings +
descriptor synthesis) and docs/QUEUED_MISSION_h3_unconditioned_music.md.

HARD RULES: one render at a time under .gpu.lock; never adopt/kill foreign
servers; no OTR edits; no downloads/installs; receipts every leg; ledger over
summaries; never push. Sage-free + --disable-pinned-memory boot. Offline gate:
the server log must show "network_mode: offline" before the first prompt, or
abort. Deliver every clip with NATIVE audio intact -- no muxing. No quality
verdicts from you; ears rule. Machine descriptors (the mission-1 analyzer at
scratch/h3_music_machine_descriptors/analyze.py) run on every new clip.

JOB 1 -- TOPOLOGY A/B (highest value; do this first).
The origin artifact h3_r2v_best_out_00001_.mp4 was rendered from the OBSOLETE
nested ref_images container; its receipt pins recipe SHA 599718d4... . The
flat-V3 rebuild of the same recipe produces near-silent audio (same SHA as
study pair 1). Question: does the OLD graph still make music on today's box?
  1a. Reconstruct the old nested-container graph from the origin receipt's
      pinned recipe. If the installed H3 node now REJECTS the nested
      container, document the exact rejection verbatim -- that is itself the
      finding (the wiring is unreachable and the regression is upstream).
  1b. If it runs: render it and the current flat-V3 recipe side by side, same
      seed/prompt/fixtures, cold+warm each. Deliver both clips.
  1c. Diff the two GRAPHS node by node, audio-relevant branches especially
      (ref image container shape, audio latent path, any conditioning
      strength defaults that changed between socket styles). The diff is the
      bug report if 1b reproduces the difference.

JOB 2 -- MOOD STEERING x SCENE (the production question).
In a joint AV latent the scene may direct the score more than the words.
Disentangle with a 2x2 plus extremes, all seed 42, f124, score-request style:
  2a. dim hushed control room + "warm lighthearted orchestral score"
  2b. dim hushed control room + "tense orchestral drama score" (the
      operator's house register for the radio-drama product)
  2c. bright lively scene (rewrite the scene: morning light, bustling
      activity) + "warm lighthearted orchestral score"
  2d. bright lively scene + "tense driving noir strings"
  2e. one wildcard: the dim room + "playful ragtime piano" (maximum
      scene/word clash).
Question for the operator's ears: when words and scene disagree, which wins?

JOB 3 -- SCORE-PROMPT SEED SWEEP. The working path's hit rate is unmeasured
(Q4-B was seed 42 only). The exact Q4-B recipe at seeds 43-46 (4 legs).
How many of 5 produce a usable score is the dropdown-entry number.

JOB 4 -- SCORE-PROMPT DURATION. Q4-B prompt at 192f and 277f. Mission 1's
duration legs used the scene-only prompt (which never makes music), so score
survival at length is untested. Note mission-1 wall costs (30 and 59 min);
run these last and skip if the GPU is needed.

If JOB 1b recovers origin-grade music, add ONE bonus leg: the best JOB 2 mood
prompt on the OLD topology, for the operator's direct comparison.

REPORT: docs/H3_MUSIC_FOLLOWUP.md -- receipts per leg, the graph diff from
1c, descriptor table for all new clips, PENDING_HUMAN for every ear question.
```

## What a pass would mean

- JOB 1 recovers music -> the flat-V3 migration is a confirmed audio
  regression; the fix (or a deliberate legacy-socket recipe) restores the
  lab's best-ever audio, and scene-only music comes back on the table.
- JOB 2 shows words win -> OTR can steer mood per beat from story metadata.
  Scene wins -> the music lane's mood control IS scene design, and the prompt
  builder must set mood visually.
- JOB 3's hit rate is the number that decides the dropdown entry
  (`h3_low_mime` or a better-named music lane).
