# Session Handoff — vram-recipe-lab campaign (2026-08-08, Fable window closing)

**For the next Claude window.** Read this + the memory files first:
`~\.claude\projects\...\memory\vram-recipe-lab.md` (deep state, corrections,
landmark results) and `otr-mime-scoping-facts.md` (banked OTR architecture
facts) and `one-big-prompt-rule.md` (Jeffrey wants ONE consolidated agent
prompt, always; reissue whole on additions).

## Where the campaign stands

The lab (this repo) is 4 days old, pushed through `9429ae0`+, and OPERATIONAL:
hardened gate (10-step preflight, warm-run rule, receipts, ear gates, clamp
lanes, coordinator/nonce leases), 185 tests. Codex is the lab driver (agy was
retired after 3 provenance incidents; Codex earned trust). Claude verifies
receipts-vs-claims and pushes; agy/Codex never push.

## Live threads (in flight RIGHT NOW)

1. **Codex is executing the final consolidated close-out order** (10 items,
   in chat + effectively authoritative): same-canvas speed pair (wan_ti2v vs
   ltx_video @832x480); HuMo lane feasibility + full HuMo-vs-H3 lip-sync
   BAKEOFF in one harness (H3 lip-sync was CONFIRMED after prompt fix — the
   earlier "no lipsync" claim was retracted: old prompt defined tags but
   never instructed mouth movement); ltx_audio HQ ladder (lane runs at half
   its 14.5 budget — push canvas/frames); wan_i2v_14b exoneration re-test at
   832x480x33 clamp-12; speed-stack recon (kijai w4a8 + lightx2v 4-step,
   EXTERNAL-REPORTED 3.6x); Sage patch probe (eyeball-gated, sm_120 silent-
   noise risk); motion ladder M0-M3 (LTX reads near-still); UNCONDITIONED
   mime clip (conditioned H3 parrots input audio at 0.94 correlation);
   intel absorb; final PROMOTION_BRIEF + SESSION_REPORT.
2. **Jeffrey judges clips as they land** (eyeball+ear gates are human-only).
   Bakeoff judging criteria: lips, onset lag (HuMo F7 = 100-200ms), identity
   hold, wall-clock cost.
3. **OTR-side**: Fable made ONE OTR edit — `eng_wan_i2v.py` now declares
   `render_canvas = (832, 480)` (same O1 canvas-fallthrough fix ti2v got
   2026-08-02; likely cause of the 15.3GB lab FAIL). AST-verified. Jeffrey
   has the commit block; may not have committed/pushed yet — CHECK.

## The agreed integration sequence (after Codex's session report)

1. Claude writes `docs/2026-08-XX-SPEC-lab-findings-into-otr.md` in the OTR
   repo (grounded in promotion brief + receipts + the OTR file:line map in
   memory). Spec covers: ltx_audio HQ settings transcription into
   eng_ltx_av; F1 wiring (`assert_frame_affordable` has ZERO call sites —
   populate with lab envelopes); wan_i2v keep/retire ruling; H3 adapter
   (eng_h3_*.py — the subtle bit is FrameContract has no offset field and
   H3's grid is 17k+5 @24fps; k=5=90f=3.750s=default beat; enumerate
   discrete_frames or add offset); boot lane needs sage-free +
   --disable-pinned-memory (61->26GB host RAM); do NOT put H3 in
   audio_conditioned_video family (mouth_policy inheritance); do NOT touch
   the audio spine (V-1, SHA-frozen master).
2. Jeffrey runs `/kibitz-plugin:kibitz` on the spec (driver = Claude window).
3. Codex implements in OTR, one commit per item, regression per CLAUDE.md.
4. Claude verifies, Jeffrey pushes, ONE episode render = acceptance test.

## Key verdicts already settled (don't relitigate)

- Three-role casting: sprint lane = LTX fast/2B + wan_ti2v 5B (needs
  same-canvas tiebreak); workhorse lips = HuMo 1.7B; hero lips = H3
  (pending bakeoff). H3 ~2x LTX and ~9x Wan cost per output-second.
- OTR's `eng_ltx_av.py` is AHEAD of the lab's LTX recipes (4 recipes,
  LoRA/scheduler exclusivity, tiled-decode fix, two-stage IA2V). Lab's LTX
  contribution = measurement only. Seed lab recipes from eng_*.py, never
  vendor templates.
- H3: licensed (written grant, docs/H3_LICENSE_GRANT.md, grantee Blueberry
  Kale Yoga Books), weights byte-verified on disk, 4.36GB net clamped,
  renders clean sage-free, identity-ref works, continuation chains at SSIM
  0.82/0.90, audio stem = 0.94-correlation re-encode of input (audition-only).
- wan_i2v_14b: candidate for retirement toward wan_ti2v UNLESS the canvas
  fix + clamp re-test exonerates it.

## Parked for OTR 2.1 (seeds planted, do not start)

Mime-play OTR scoping (facts banked in memory; must be UNCONDITIONED);
public "5080 lab" repo distillation (receipts + RAM column = moat; fixtures
stay home, users bring their own); one-command bootstrap (ride ComfyUI
Desktop, never wrap Comfy); model-download metadata sweep (hash-matched,
ultracode fan-out for provenance); distribution research prompt (Jeffrey has
it, runs in a repo-less chat, report gets filed as
research/DISTRIBUTION_RESEARCH.md). Reddit post reddit_post_v2_1.md ships
with the repo + mime clip as demo; keep license mention low-key (one
"made with MiniMax H3" credit + AI-disclosure line).

## Standing rules (hard-won this week)

Ledger is the only truth — summaries lie; verify receipts before pushing.
One big prompt, never minis. Blast radius routes work: Codex = precise
production edits, agy = volume/review lanes, Claude = spec/verify/push.
Human eyes+ears gate every new lane. EXTERNAL-REPORTED tag on any number we
didn't measure. GPU idle check before renders. UTF-8 no BOM. Never push from
agents.

## Kickoff for the next window

"Read docs/SESSION_HANDOFF_2026-08-08.md in vram-recipe-lab + the three
memory files. Then: if Codex's session report is in, audit receipts-vs-claims
and push; then write the OTR integration spec per the handoff's sequence."
