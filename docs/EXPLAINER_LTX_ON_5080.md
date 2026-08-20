# THE QUANT IS THE WORKFLOW
### What LTX actually renders on a 16 GB laptop GPU — and what 2.5 has not proven here yet

**Estimated runtime:** ~3:53 (≈145 wpm, dry narration)
**Visual style:** NVIDIA x LTX hybrid — isometric 3D wireframe bench with carbon-and-green telemetry hardware feeding violet cinematic shot cards
**Audio:** dry narration, no music (one non-musical cue — see AUDIO SYSTEM)
**Pipeline:** NotebookLM-compatible scene blocks
**Palette:** locked — carbon (#0C0E10), NVIDIA green (#76B900), LTX violet (#8A5CF6), paper-white (#F2EFE8)
**Data convention:** SOLID NVIDIA green = measured on this hardware, receipt-bound · DASHED LTX violet = upstream claim, vendor spec, or projection with no local run
**Scene count:** 9 (+ end card)
**Narration word count:** ~563

**v2 changes from v1:**
- Re-scoped from the whole-lab retrospective to LTX only, on the 5080 bench.
- Palette relocked from graphite/amber to an NVIDIA-and-LTX split; the two brands now carry the fact/inference convention directly (green = our silicon measured it, violet = LTX says so).
- Every workflow beat now states resolution, frame count, frame rate, step count, VRAM peak, host-RAM peak, and wall clock.
- Added the tested minimum/maximum envelope as its own scene.
- Added operator hardware: the RTX 5080 Laptop main bench and the RTX 4060 Laptop / i9-13900 / 32 GB second box.
- Added the LTX 2.5 scene, held entirely dashed: the lab has no 2.5 weights, recipes, or receipts.

---

## AUDIO SYSTEM

One cue: the 200-millisecond sampling tick the runner uses to poll VRAM and host RAM. Clinical,
never melodic. It runs from Scene 02 through Scene 06, drops out entirely for Scene 07 (the
unproven LTX 2.5 material gets silence, not scoring), returns for one bar under Scene 08, and cuts
for the coda.

## GRAPHIC SYSTEM

Two visual languages, deliberately not blended into mush:

- **NVIDIA side** — carbon-black bench, precision grid floor, chamfered angular panels, telemetry
  HUD readouts, benchmark bars, hard green edge-light. Everything measured lives here, in SOLID
  green line work.
- **LTX side** — floating cinematic shot cards in 16:9 and 1:1, filmstrip stacks, soft violet
  gradient wash, latent-particle dissolves. Everything claimed but untested lives here, in DASHED
  violet.

The two never share a line style. A value moves from violet to green only by earning a receipt.

---

## SCENE 01 — COLD OPEN: SAME MODEL, TWO OUTCOMES

**VISUAL:** Black. Two isometric weight blocks rise on the carbon grid, labeled by file. The left
block is enormous — a 43-gigabyte slab, violet-edged, straining. The right block is a compact
10-gigabyte cube in solid green. Above each, a VRAM meter fills: the left one punches through a
paper-white ceiling plane and flares; the right one stops at less than half height.

**NARRATION:** Same model. Same canvas. Same night. Loaded as the full 43-gigabyte checkpoint, LTX
2.3 peaked at 15.45 gigabytes of video memory and failed the gate. Loaded as a 10-gigabyte
quantized file, the same model peaked at 7.06 and passed twice. On a 16-gigabyte laptop, the
quantization is not an optimization. It is the workflow.

**ON-SCREEN TEXT:** LTX 2.3 22B · fp16 CKPT 15.45 GB FAIL · Q3_K_M GGUF 7.06 GB PASS · RESULTS.md

**TRANSITION:** Camera pulls back from the two blocks to reveal the bench they sit on.

---

## SCENE 02 — THE BENCH

**VISUAL:** Wide isometric hardware bay in carbon and green. Center: the 5080 laptop as a chamfered
wireframe chassis with a live green telemetry readout. Off to the right, smaller and rendered in
dashed violet, sits the second machine — the 4060 laptop — with its specification card floating
beside it. A paper-white ceiling plane runs across the whole bay.

**NARRATION:** The main bench is an RTX 5080 Laptop GPU, measured at 15.92 gibibytes, with a hard
pass line of 14.5. Memory is sampled every 200 milliseconds. Nothing passes on one run, and nothing
passes without a receipt. The second machine is an RTX 4060 Laptop: 8188 mebibytes, an Intel Core
i9-13900, 32 gigabytes of system RAM. It has run no LTX workload at all.

**ON-SCREEN TEXT:** RTX 5080 LAPTOP · 15.92 GiB MEASURED · GATE 14.5 GB — RTX 4060 LAPTOP · 8188 MiB · i9-13900 · 32 GB RAM · NO LTX RUNS

**TRANSITION:** The bench floor scrolls forward and three cinematic shot cards rise out of it in
green, each tagged with its own settings.

---

## SCENE 03 — WHAT WORKS: THE AUDIO-VIDEO LADDER

**VISUAL:** Three solid green shot cards, H1 H2 H3, each with a telemetry strip beneath it holding
resolution, frames, frame rate, steps, VRAM peak, and wall clock. Each card carries a small
waveform in the corner — this stack generates its own audio. All three carry a "2 of 2 WARM" seal.

**NARRATION:** The proven stack is LTX 2.3 22B, Q3_K_M quantized, with the Gemma 3 12B encoder, at
20 steps and 25 frames per second. H1: 1024 by 576, 97 frames, 7.06 gigabytes, 248 seconds. H2: 832
by 480, 193 frames, 7.93 gigabytes, 341 seconds. H3: 1024 by 576, 193 frames, 7.36 gigabytes, 585
seconds. All three passed warm, with native audio and zero duration error.

**ON-SCREEN TEXT:** LTX 2.3 22B Q3_K_M · 20 STEPS · 25 fps · 7.06 / 7.93 / 7.36 GB · WARM 2/2 · docs/PROMOTION_BRIEF.md

**TRANSITION:** The three cards slide left out of frame; one new card drops in fast enough to blur.

---

## SCENE 04 — WHAT WORKS: THE SPRINT LANE

**VISUAL:** A single green shot card with an oversized stopwatch readout. Beside it, a VRAM column
noticeably taller than the ladder's columns. The card has no waveform corner — this lane is silent.

**NARRATION:** The other proven lane is the small one. LTX Video 2B distilled, 8 steps, 832 by 480,
193 frames at 25 frames per second: 13.11 gigabytes peak, 13.8 seconds of wall clock. That is 29.5
times faster than WAN on the identical canvas. It costs almost double the video memory of the 22B
quantized stack, and it produces no audio.

**ON-SCREEN TEXT:** LTX VIDEO 2B DISTILLED · 8 STEPS · 193f @ 25 fps · 13.11 GB · 13.8 s · 29.528986x

**TRANSITION:** The stopwatch face flattens into a horizontal axis and the envelope chart draws
itself across it.

---

## SCENE 05 — THE TESTED ENVELOPE

**VISUAL:** One green rectangle in the middle of a much larger violet dashed rectangle. The green
box is labeled on all four edges with the tested extremes. The violet space around it is empty and
explicitly marked as unrun. Two dashed violet ghost cards float outside the green box: 1920 by 1088
and a 24-frame-per-second lipsync cell.

**NARRATION:** The tested envelope is narrow and worth stating exactly. Frame rate: every gated LTX
run was 25 frames per second. Not one 24 was ever measured. Frames: 97 minimum, 193 maximum warm,
194 maximum cold. Resolution: 832 by 480 minimum, 1024 by 576 maximum. Steps: 8 distilled, 20 full.
Video memory across the passing quantized lanes: 7.06 low, 9.25 high. Full HD recipes exist in the
repository. None has ever been run.

**ON-SCREEN TEXT:** TESTED · 25 fps ONLY · 97–194 FRAMES · 832x480 → 1024x576 · 8 or 20 STEPS · 7.06–9.25 GB — UNRUN · 1920x1088 · 24 fps

**TRANSITION:** The green box stays; the floor beneath it turns transparent to expose a second,
larger meter running underneath the whole bench.

---

## SCENE 06 — THE CEILING NOBODY QUOTES

**VISUAL:** Below the VRAM columns, a much taller system-RAM column rises in green, dwarfing them.
A paper-white 32-gigabyte line cuts across it — and the column is already above the line. To the
side, the three weight files stack up: 10.03, 8.80, 1.35 gibibytes.

**NARRATION:** Video memory is the famous number and the wrong one to plan around. The quantized
lanes that peaked near 7 gigabytes of VRAM peaked between 34 and 50 gigabytes of system RAM. The
full checkpoint run touched 61.2. The weights alone are 10.03 gibibytes of transformer, 8.80 of
text encoder, 1.35 of video VAE. On a 32-gigabyte machine, system RAM is the wall you hit first —
and the 4060 laptop has 32.

**ON-SCREEN TEXT:** HOST RAM PEAK 34.19–50.37 GB · fp16 RUN 61.23 GB · WEIGHTS 10.03 + 8.80 + 1.35 GiB · 4060 BOX HAS 32 GB

**TRANSITION:** All green telemetry drains away. The bay goes dark and a violet gradient rises from
the far end. The tick stops.

---

## SCENE 07 — LTX 2.5: EVERYTHING HERE IS DASHED

**VISUAL:** Entirely violet, entirely dashed, no green anywhere. A large multishot filmstrip
unfurls — connected shot cards holding one character across cuts. Specification text floats beside
it. In the foreground, a green receipt tray sits open and completely empty.

**NARRATION:** LTX 2.5 shipped on August 11th, 2026: 22 billion parameters, open weights, native
multishot, auto duration, 4K HDR, day-one ComfyUI support. LTX reports a 10-second 720p clip in 6.8
seconds on two GB200s. Community quantizations already exist. And in this lab, 2.5 has no weights
on disk, no recipe, and no receipt. Not one frame has been rendered here. Everything in this scene
is somebody else's measurement.

**ON-SCREEN TEXT:** LTX 2.5 · 22B OPEN WEIGHTS · MULTISHOT · 4K HDR · 6.8 s ON 2x GB200 — LOCAL: 0 WEIGHTS · 0 RECIPES · 0 RECEIPTS

**TRANSITION:** The empty receipt tray slides forward into the violet field and one green outline
snaps around it.

---

## SCENE 08 — WHAT THE PORT WOULD COST

**VISUAL:** A dashed violet plan card with four numbered steps, each waiting for a green stamp that
has not landed. Behind it, the 2.3 ladder from Scene 03 sits in solid green as the reference shape.

**NARRATION:** The 2.3 result already dictates the 2.5 method. Take a quantized build, not the full
checkpoint. Start at the proven cell: 832 by 480, 97 frames, 25 frames per second, 20 steps. Run it
cold, then warm, under the same 14.5 gigabyte gate. Watch system RAM first, because on this
evidence that is what fails first. Until those two runs exist, LTX 2.5 here is a plan, not a
result.

**ON-SCREEN TEXT:** PROPOSED FIRST CELL · QUANTIZED BUILD · 832x480 · 97f · 25 fps · 20 STEPS · COLD + WARM · GATE 14.5 GB

**TRANSITION:** The plan card fades. The empty receipt tray remains, alone on the carbon grid.

---

## SCENE 09 — CODA

**VISUAL:** Silent. The bench in darkness. One green line and one violet dashed line run parallel
across black, the same length, never touching.

**NARRATION:** Two lines. One is what this hardware did, timed and written down. The other is what
the model does somewhere else. They look identical on a slide. Only a receipt moves a number from
one line to the other.

**ON-SCREEN TEXT:** MEASURED HERE · CLAIMED ELSEWHERE

**TRANSITION:** Both lines fade. Two seconds of black.

---

## END CARD / SOURCES

**VISUAL:** Black. Citation list scrolls in NVIDIA-green monospace.
**NARRATION:** (silent — 2 seconds of black before end card)
**ON-SCREEN TEXT:**
SOURCES — MEASURED (SOLID)
• vram-recipe-lab RESULTS.md and ENGINE_MATRIX_BETA.md — per-lane VRAM, wall clock, warm status
• results/ltx_audio_hq_h1_1024x576_run2.json · h2_193f_run2 · h3_1024x576_193f_run2 — the ladder
• results/ltx_video_2b_distilled_cmp_832x480_f193_run2.json — 13.11 GB, 13.8 s
• results/comparisons/general_video_speed_pair.json — 29.528986x normalized pair
• results/ltx_audio_low.json · ltx_audio_ckpt.json — 15.45 / 15.34 GB ceiling failures
• PREFLIGHT.md and AGENTS.md — 14.5 GB gate, 200 ms sampling, warm-pass rule
• eightgb_bench/reports/physical-rtx4060-8gb-hardware.json — 8188 MiB, 31.701 GiB RAM

SOURCES — CLAIMED (DASHED)
• Lightricks/LTX-2.5 on Hugging Face — 22B open weights, gated release, community GGUF/NVFP4 quants
• LTX 2.5 launch coverage, 11 Aug 2026 — multishot, auto duration, 4K HDR, 6.8 s on 2x GB200
• ComfyUI day-one LTX 2.5 support announcement
• Operator-reported: Intel Core i9-13900, 32 GB RAM on the 4060 box (no receipt records the CPU)

---

**Runtime estimate:** ~3:53 at ≈145 wpm
**Scene count:** 9 (+ end card)
**Narration word count:** ~563

**Production notes:**
- Scene 01 is the whole thesis in 55 words. If only one scene gets polish, polish that one.
- Scene 06 is the beat nobody else makes. Hold the system-RAM column on screen longer than feels
  right; it is the only place the 32 GB machine's real limit is visible.
- Keep Scene 07 free of every green pixel. The moment a green line appears in the LTX 2.5 scene the
  format's promise breaks.
- Confirm the CPU suffix (H, HX, or HK) before render — the receipt store does not record it, so
  the on-screen label is operator-reported and currently unsuffixed.
- If runtime must come down: Scene 08 can be cut whole without breaking the arc, saving ~40 seconds.
  Scenes 03 and 04 cannot be merged — they are the two different tradeoffs.
