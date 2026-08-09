# Session Handoff — 2026-08-09 (supersedes 2026-08-08 handoff)

**Next Claude window: read this + memory files** (`vram-recipe-lab.md`,
`otr-mime-scoping-facts.md`, `one-big-prompt-rule.md`). The 08-08 handoff's
"live threads" are DONE; this is the current truth.

## Campaign status: COMPLETE, pushed at `a26ef9b`

Engine matrix CLOSED — every shipping engine + H3 measured, same fixtures,
same instruments. Final docs: docs/PROMOTION_BRIEF.md, SESSION_REPORT.md,
HUMO_BAKEOFF.md. 282 tests, 48 recipes validated.

**The final twist:** production HuMo 1.7B peaks 15.12–15.23 GiB (OVER the
14.5 gate; 14B at 15.0) while H3 Ref2VA does the same job at 6.5–6.7 GiB,
~35% slower. The shipping face lane lives in the allocator-corruption zone
F1 warns about. Other finals: LTX distilled 2B 29.5x faster than WAN at
same canvas; best ltx_audio HQ = 1024x576x193 warm ~7.4 GiB; wan_i2v_14b
viable clamp-12 but tight (canvas fix landed in OTR eng_wan_i2v.py —
render_canvas (832,480), may be uncommitted, CHECK); Sage patch FAILED on
sm_120 (never enable); H3 turbo BLOCKED (kijai w4a8 + lightx2v not on
disk); mime clip at exact 8.000s with invented audio (ear gate pending).

## Pending HUMAN verdicts (Jeffrey)

1. Character-lane bakeoff: 3 HuMo clips vs 2 H3 clips (all in his chat;
   also outputs\humo_*bakeoff*.mp4 + h3_r2v_refaudio_tts_lipsync_exact_*).
   Judge: lips, onset lag (HuMo F7 = 100-200ms), identity, cost. Jeffrey
   may pre-screen via Gemini (rubric prompt given, engines anonymized A/B);
   record as gemini-advisory in HUMO_BAKEOFF.md — human verdict rules.
2. Motion ladder ranking M0-M3 (ltx_audio_motion_m*.mp4).
3. Mime ear gate (h3_mime_i2v_ledger_music_closing_8s — invented audio;
   pass = no speech-like content + diegetic sync).

## Live mission: "HuMo VRAM diet" (new Codex/Gemini window running it)

Full prompt was issued (TTS-flow-focused; phases R/0/1/2/3 — community
intel sweep first, clamp floor second, levers third, HUMO_DIET.md diff
last). **CORRECTION TO ITS PHASE 0:** the window reported BLOCKED because
`WanHuMoImageToVideo` has no definition in Documents\custom_nodes — but it
only searched custom_nodes. H3's nodes live in COMFY CORE
(C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\comfy_extras\) and
WanHuMo is likely core too; the bakeoff RAN HuMo successfully on 2026-08-09,
so the class exists and loads. Instruct it: search the core tree
(comfy_extras\nodes_wan*.py etc.); if core, the lab server already serves
it with NO whitelist change — un-BLOCK and proceed to Phase 1 (clamp floor:
reproduce bakeoff HuMo 1.7B in-lab under --clamp 13 / --clamp 12
no-pinned; target <= 13.5; name the VRAM hog — 1.7B fp16 DiT is only
~3.4 GB, the memory goes elsewhere).

## After verdicts: the integration sequence (unchanged)

1. Claude writes docs/2026-08-XX-SPEC-lab-findings-into-otr.md in the OTR
   repo: ltx_audio HQ transcription (1024x576x193); F1 wiring with
   measured envelopes; wan_i2v keep/retire ruling; H3 adapter (17k+5
   FrameContract offset problem; sage-free + --disable-pinned-memory boot;
   NOT audio_conditioned_video family; audio spine untouched); character-
   lane ruling per bakeoff verdict + HUMO_DIET result.
2. Jeffrey runs /kibitz-plugin:kibitz on the spec (Claude window drives).
3. Codex implements in OTR, one commit per item. 4. Claude verifies,
   Jeffrey pushes, ONE episode render = acceptance test.

## Parked (2.1 — do not start): mime OTR scoping (UNCONDITIONED only),
public "5080 lab" repo (receipts + host-RAM column = moat), bootstrap-on-
ComfyUI-Desktop, model-metadata sweep, distribution research prompt
(Jeffrey has it), Reddit post reddit_post_v2_1.md.

## Rules that survived the week
Ledger>summaries; verify receipts before push; one big prompt only; blast
radius routes agents (Codex=precise, agy=volume, Claude=spec/verify/push);
human eyes+ears gate every lane; EXTERNAL-REPORTED on unmeasured numbers;
agents never push.

## Kickoff line for the new window
"Read docs/SESSION_HANDOFF_2026-08-09.md in vram-recipe-lab + memory
files. First: give me the corrected un-BLOCK instruction for the HuMo-diet
window (core-tree search). Then stand by for my bakeoff/motion/mime
verdicts and write the OTR integration spec."
