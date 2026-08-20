# SEVENTY-SEVEN SECONDS
### LTX 2.5 with native audio on one 16 GB laptop GPU — the graphs that ran and the numbers they hit

**Estimated runtime:** ~4:17 (≈145 wpm, dry narration)
**Visual style:** NVIDIA x LTX hybrid — isometric carbon bench with green telemetry hardware feeding violet cinematic shot cards
**Audio:** dry narration, no music (one non-musical cue — see AUDIO SYSTEM)
**Pipeline:** NotebookLM-compatible scene blocks
**Palette:** locked — carbon (#0C0E10), NVIDIA green (#76B900), LTX violet (#8A5CF6), paper-white (#F2EFE8)
**Data convention:** SOLID NVIDIA green = measured on this bench, receipt-bound · DASHED LTX violet = not receipted here — upstream claim, unrun recipe, or an observation with no receipt filed
**Scene count:** 9 (+ end card)
**Narration word count:** ~622

**v3 changes from v2:**
- Corrected the central error in v2. The lab **does** have LTX 2.5 evidence: 16 measured cells dated 2026-08-19, 20 recipes, a loader patch, and a published guide. v2 was written against a stale `main` and wrongly said zero. Every 2.5 beat is now receipt-bound and green.
- Subject narrowed from "LTX on the 5080" to LTX 2.5 specifically, per the working set in `LTX_2_5_ON_16GB.md`.
- Added the loader-patch scene — without it the native audio path does not load at all.
- Added the six graph tripwires, the Q3-vs-Q5 A/B, and the "what FAIL means here" scene.
- 4060 hardware beat reframed: 2.5's measured floor rules that machine out, and the script says so.

---

## AUDIO SYSTEM

One cue: the 200-millisecond sampling tick the runner uses to poll VRAM. Clinical, never melodic.
It runs from Scene 02 through Scene 07, thins to a single slow pulse under Scene 08 as the human-
review gate appears, and cuts entirely at Scene 09. The coda and end card are silent.

## GRAPHIC SYSTEM

Two visual languages held apart on purpose:

- **NVIDIA side** — carbon bench, precision grid floor, chamfered angular panels, telemetry HUD
  readouts, hard green edge-light. Everything with a receipt lives here in SOLID green.
- **LTX side** — floating cinematic shot cards, filmstrip stacks, soft violet gradient wash,
  latent-particle dissolves. Everything unreceipted lives here in DASHED violet.

A value turns green only by having a receipt path under it. Nothing else earns the color.

---

## SCENE 01 — COLD OPEN: SEVENTY-SEVEN SECONDS

**VISUAL:** Black. A green wall-clock counter runs up from zero. Beside it a violet shot card
builds frame by frame, and a waveform draws itself along the card's lower edge in the same motion —
picture and sound arriving together, not stacked. The counter stops at 77.7.

**NARRATION:** Seventy-seven point seven seconds. That is one 832 by 480 clip, 97 frames at 25
frames per second — three point eight eight seconds of finished video, with its own score, composed
in the same pass that drew the pictures. Not a video model plus an audio model. One joint model, on
one laptop GPU, on a bench that wrote down every number.

**ON-SCREEN TEXT:** LTX 2.5 · 832x480x97 @ 25 fps · 3.88 s OUT · 77.7 s RENDER · VIDEO + NATIVE AUDIO

**TRANSITION:** The shot card docks into a slot on the isometric bench; camera pulls back to the
hardware.

---

## SCENE 02 — THE FLOOR YOU CANNOT TUNE

**VISUAL:** The 5080 chassis in green wireframe with a vertical VRAM meter beside it. Sixteen run
markers stack up the meter and land in a band so tight it reads as one line. A paper-white card
ceiling sits just above at 15.92, and the gap between them is drawn with a caliper too small for
its own label. Off to the right in dashed violet, the 4060 chassis sits at half the meter's height.

**NARRATION:** Sixteen runs. Peak video memory: 15.47 to 15.60 gibibytes. That band did not move
when the lab changed steps, changed guidance, changed quantisation, or changed mode. It is set by
the weights and the decode, not by your sampler. On a card that addresses 15.92, the headroom is
0.32 gibibytes. It fits, and it fits by almost nothing. The 8-gigabyte laptop next to it is not a
tuning problem. It is simply out.

**ON-SCREEN TEXT:** 16 RUNS · PEAK 15.47–15.60 GiB · CARD 15.92 GiB · HEADROOM 0.32 GiB — RTX 4060 · 8188 MiB · CANNOT HOST THIS

**TRANSITION:** The meter dims. A single node panel slides in front of the bench, cracked open.

---

## SCENE 03 — THE PATCH THAT MAKES AUDIO EXIST

**VISUAL:** An exploded loader node in green. Two failure points light in violet, then flip to green
as the patch applies: a rejected encoder label, and three tensor names that pass through the
dequantiser untouched. The audio path, previously a dead violet line, completes in green.

**NARRATION:** Out of the box, ComfyUI's GGUF loader cannot load this model. Two reasons, one patch.
First, the encoder is a Gemma-4 12B, and gemma4 is not in the architecture list — one word. Second,
three LTX audio-video parameters are stored as BF16 above rank one, and the stock loader only
dequantises rank one or lower. One of the three is the audio embeddings connector. Without the
patch, the native audio — the entire reason to run 2.5 — does not load.

**ON-SCREEN TEXT:** ComfyUI-GGUF PATCH · gemma4 → TXT_ARCH_LIST · 3 BF16 TENSORS DEQUANTISED · audio_embeddings_connector.learnable_registers

**TRANSITION:** The repaired loader emits four shot cards that fan out across the bench.

---

## SCENE 04 — THE WORKING SET

**VISUAL:** Four green shot cards in a row, each with a telemetry strip: wall clock, peak, steps,
guidance. A shared settings plate sits beneath them all. Every card carries a waveform corner.

**NARRATION:** Four text-to-video cells, all distilled, all 8 steps, guidance at 1.0 for both video
and audio, sampler euler ancestral, Q3 quantised weights with the Gemma-4 encoder. Cinematic music:
77.7 seconds. The bare distilled lane: 87.0. Its visual-led variant: 87.2. Action with matched
foley: 93.0. Peaks 15.47 through 15.52. That is roughly twenty to twenty-four times the clip's own
length in render time, on a laptop, sound included.

**ON-SCREEN TEXT:** 8 STEPS · CFG 1.0 / 1.0 · euler_ancestral · Q3_K_M + GEMMA-4 · 77.7 / 87.0 / 87.2 / 93.0 s · 15.47–15.52 GiB

**TRANSITION:** The settings plate flips over; six warning cells are engraved on its back.

---

## SCENE 05 — SIX THINGS THAT KILL THE GRAPH

**VISUAL:** Six engraved cells on the plate, each animating its failure in two seconds: a silent
lane still loading the audio VAE; a non-ancestral sampler freezing into a still; a canvas axis
snapping at 13.5; a frame count rejected; a dangling scheduler port; a whole-clip decode blowing
out where the tiled decode holds.

**NARRATION:** Six tripwires. The audio VAE loads even when you want silence — you pay for the
audio either way. Use an ancestral sampler, or 8 steps returns a still image with a render time.
Both canvas axes must divide by 32: 768 by 432 fails, and 1024 by 576 does not fit. Frame count
minus one must divide by 8: 97 works, 96 does not. Connect the scheduler's latent port, or it
silently falls back to the wrong curve and just comes out wrong. And keep the tiled decode at 512
with 64 overlap.

**ON-SCREEN TEXT:** AUDIO VAE ALWAYS LOADS · ANCESTRAL ONLY · AXES % 32 · (FRAMES-1) % 8 · CONNECT scheduler.latent · VAEDecodeTiled 512/64 · TEMPORAL 33/4

**TRANSITION:** Two of the cells detach and become a two-bar comparison chart.

---

## SCENE 06 — THE QUANT TEST EVERYONE GETS BACKWARD

**VISUAL:** Two green bars, same recipe, same 20 steps, only the quantisation swapped. The VRAM
columns are visually identical. The wall-clock bars are not.

**NARRATION:** A clean A-B: same graph, same steps, same guidance, only the quantisation changed.
Q3 peaked at 15.56 and finished in 276.8 seconds. Q5 peaked at 15.51 and took 348.5. Twenty-six
percent slower for a peak difference of five hundredths of a gigabyte. Quantisation here is a speed
lever, not a memory lever. It does not buy headroom.

**ON-SCREEN TEXT:** Q3_K_M 15.56 GiB / 276.8 s · Q5_K_M 15.51 GiB / 348.5 s · +26% TIME · NO HEADROOM GAINED

**TRANSITION:** The chart tips over into a longer horizontal timeline running off the bench edge.

---

## SCENE 07 — THE SLOW LANES, AND THE THREE WALLS

**VISUAL:** A long green timeline with four cells placed along it by wall clock. Past its end,
three dashed violet blocks stand as hard stops, each labeled with what it breaks.

**NARRATION:** Audio-conditioned video runs clean at 106.4 seconds. The classic 20-step guidance
lane runs at 254 to 276 — about three times the wall clock for an identical peak. Static lip sync
completes at 404.6 seconds, the slowest cell measured, and is not recommended at this memory
budget. Three things were not made to work: 161-frame multishot, which spikes to eighteen or twenty
gigabytes; in-graph two-times upscaling, which forces a 1664 by 960 decode and hard fails; and any
canvas past 832 by 480.

**ON-SCREEN TEXT:** a2v 106.4 s · 20-STEP LANE 254.4–275.9 s · LIPSYNC 404.6 s — WALLS: 161f MULTISHOT · IN-GRAPH 2x UPSCALE · CANVAS > 832x480

**TRANSITION:** The timeline drains to black; one paper-white review card rises alone.

---

## SCENE 08 — WHAT "WORKS" MEANS HERE

**VISUAL:** A single card, half green and half violet, split down the middle. The green half lists
machine facts. The violet half is an unsigned review field, blinking, empty. Behind it, sixteen
receipt tiles are stamped FAIL in green — then a paper-white line redraws the threshold they failed
against, well below where they landed.

**NARRATION:** Every one of these runs is marked failed in this repository, and every one produced
a complete audio-video file. They failed a 14.5 gibibyte policy budget the lab set for itself, not
a limit of the hardware. And every receipt still reads eyeball pending, promotion ready false. So
works means it runs, it fits, it outputs. Nobody has yet said it looks good.

**ON-SCREEN TEXT:** 16/16 OVER THE 14.5 GiB POLICY BUDGET · ALL PRODUCED VALID OUTPUT · eyeball: pending · promotion_ready: false

**TRANSITION:** The card's green half stays lit; the violet half fades to nothing.

---

## SCENE 09 — CODA

**VISUAL:** Silent. The bench dark. One green line and one violet dashed line run parallel across
black. The green line is shorter — and it is the only one with tick marks on it.

**NARRATION:** The claim about a model is always longer than the measurement of it. Seventy-seven
seconds, fifteen point four seven, ninety-seven frames — short, checkable, and true on one specific
machine. That is the whole difference between a workflow and a rumor.

**ON-SCREEN TEXT:** MEASURED 2026-08-19 · ONE MACHINE · WRITTEN DOWN

**TRANSITION:** Both lines fade. Two seconds of black.

---

## END CARD / SOURCES

**VISUAL:** Black. Citation list scrolls in NVIDIA-green monospace.
**NARRATION:** (silent — 2 seconds of black before end card)
**ON-SCREEN TEXT:**
SOURCES — MEASURED (SOLID)
• vram-recipe-lab LTX_2_5_ON_16GB.md — the working-set guide, measured 2026-08-19
• results/ltx_2_5_golden_t2v_cinematic_music.json — 77.7 s, 15.47 GiB
• results/ltx_2_5_t2v_path_a.json · t2v_path_a_visual · golden_t2v_action_foley — 87.0 / 87.2 / 93.0 s
• results/ltx_2_5_a2v_gguf.json vs ltx_2_5_a2v_gguf_q5.json — the Q3/Q5 A-B
• results/ltx_2_5_golden_a2v_static_lipsync.json — 404.6 s
• ENGINE_MATRIX_BETA.md and RESULTS.md — all 16 cells, 15.47–15.60 GiB
• scratch/patches/ComfyUI-GGUF-ltx25-gemma4.patch — the loader fix
• recipes/ltx_2_5_*.json — 20 API-format graphs, 16 with receipts

SOURCES — NOT RECEIPTED HERE (DASHED)
• 161-frame multishot and in-graph 2x upscale limits — observed during exploration, no receipt filed
• Quality of any output — no human review exists yet on any 2.5 cell
• RTX 4060 box, i9-13900, 32 GB RAM — operator-reported; no receipt records the CPU

---

**Runtime estimate:** ~4:17 at ≈145 wpm
**Scene count:** 9 (+ end card)
**Narration word count:** ~622

**Production notes:**
- Scene 02 is the load-bearing beat: the flat 15.47–15.60 band across sixteen runs is the finding
  nobody else has published. Hold the sixteen markers on screen until the tightness reads.
- Scene 03 is the one that saves a viewer a wasted evening. Do not compress it for time.
- Scene 08 must not be cut. Without it the script claims quality it has not earned.
- If runtime must come down: Scene 06 can fold into Scene 04 as a single line, saving ~35 seconds.
- Confirm the CPU suffix (H, HX, or HK) before render — no receipt in the repository records it.
