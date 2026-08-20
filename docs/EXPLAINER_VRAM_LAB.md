# THE 14.5 GIGABYTE LINE
### What one laptop GPU actually rendered, and what it only claimed to

**Estimated runtime:** ~2:56 (≈145 wpm, dry narration)
**Visual style:** 3D wireframe / isometric vector motion graphics
**Audio:** dry narration, no music (optional non-musical cue — see AUDIO SYSTEM)
**Pipeline:** NotebookLM-compatible scene blocks
**Palette:** locked — graphite (#1B1F24), paper-white (#F2EFE8), meter-green (#4FC08D), amber (#E8A33D)
**Data convention:** SOLID meter-green = receipt-backed measurement · DASHED amber = inference, projection, or pending human verdict
**Scene count:** 9 (+ end card)
**Narration word count:** ~425

---

## AUDIO SYSTEM

One cue only: a 200-millisecond sampling tick, the same interval the runner uses to poll VRAM
and host RAM during execution. Clinical, never melodic. It runs under Scenes 02 through 08 and
accelerates slightly as measured peaks climb toward the ceiling plane. Visual accent pulses sync
to the tick. **The tick cuts to silence the moment Scene 09 begins.** The coda and end card are
silent.

---

## SCENE 01 — COLD OPEN: TWO IDENTICAL CLIPS

**VISUAL:** Black. Two isometric wireframe render volumes drift in from opposite edges, identical
in every dimension: 832 by 480, 193 frames, stacked as a translucent graphite lattice. A
meter-green timer bar runs beneath each. The left bar crawls the full width of frame. The right
bar completes almost instantly and then just sits there while the left one is still moving. Camera
holds, unblinking, on the gap.

**NARRATION:** Two clips. Same canvas. Eight-thirty-two by four-eighty, one hundred ninety-three
frames. Both deliver 7.72 seconds of video. Both were rendered warm, on the same machine, on the
same night. One took 407.5 seconds. The other took 13.8. Nothing changed except which engine was
loaded.

**ON-SCREEN TEXT:** SAME CANVAS · 832x480 · 193 FRAMES · 407.5 s vs 13.8 s · results/comparisons/general_video_speed_pair.json

**TRANSITION:** The two timer bars rotate up into vertical columns and become the first two bars of
a measurement chart — the camera pulls back to reveal the chart is the floor of a much larger room.

---

## SCENE 02 — THE LINE

**VISUAL:** Wide isometric hall. A single paper-white plane hangs horizontally across the whole
space at a fixed height, labeled at its edge. Below it, dozens of thin meter-green columns rise
from the floor grid — one per recipe. To the left, three stacked wireframe cabinets glow faintly:
recipes, receipts, tests.

**NARRATION:** This lab exists because the original pipeline had a VRAM guard that was never called.
Renders ran unchecked into out-of-memory crashes that corrupted the allocator. So the lab set a
hard line: 14.5 gigabytes on a 16-gigabyte laptop GPU, sampled every 200 milliseconds. Nothing
passes on one run. Nothing passes without a receipt.

**ON-SCREEN TEXT:** HARD GATE 14.5 GB · 16 GB RTX 5080 LAPTOP · 82 RECIPES · 276 RECEIPTS · 51 TEST FILES · PREFLIGHT.md

**TRANSITION:** Camera drops to floor level and tracks along the column row until four columns
ahead are seen puncturing the paper-white plane.

---

## SCENE 03 — THE FLOOR IS THE POINT

**VISUAL:** Four solid meter-green columns pass straight through the ceiling plane. Where each
breaks the surface, the plane flares paper-white and holds a small numeric tag. The columns are not
deleted, dimmed, or moved. They stay in the chart, over-height, permanently.

**NARRATION:** Four engines went over the line and stayed in the record. LTX text-to-video at
15.38. LTX audio at 15.45. A canonical H3 image-to-video at 15.39. WAN's 14-billion-parameter
image-to-video crashed outright at 15.28. Failures are not removed here. A deleted failure is just
a claim with better manners.

**ON-SCREEN TEXT:** OVER CEILING · 15.28 / 15.38 / 15.39 / 15.45 GB · RECORDED, NOT REMOVED · RESULTS.md

**TRANSITION:** The tallest broken column drops back below the plane as the camera orbits — the
same column, re-measured.

---

## SCENE 04 — THE EXONERATION

**VISUAL:** One column isolated on a turntable pedestal. Two ghosted wireframe versions of itself
stand behind it: the failed run, over-height and solid; the passing run, shorter. A thin
paper-white caliper drops between the passing column's top and the ceiling plane, and the gap it
measures is almost too small to see.

**NARRATION:** The engine that crashed was re-run at controlled settings and passed warm, twice, at
13.93 gigabytes. Against a 12-gigabyte target card, its cold headroom measured one tenth of a
gigabyte. It is exonerated and it is tight. Both facts ship together.

**ON-SCREEN TEXT:** WAN I2V 14B · WARM PASS 13.93 GB · HEADROOM 0.10 GB · results/wan_i2v_14b_exoneration_832x480_f33_run2.json

**TRANSITION:** The caliper swings horizontal and becomes the axis of the speed chart from Scene 01,
now fully drawn.

---

## SCENE 05 — THE CROWN

**VISUAL:** The normalized speed pair, isometric. Two solid meter-green volumes labeled by engine.
A ratio figure assembles glyph by glyph in the air between them. Both volumes carry small
"2 of 2 warm" seals on their faces.

**NARRATION:** Named: LTX Video distilled, two billion parameters, against WAN text-image-to-video,
five billion. Same canvas, same delivered duration, both warm, both proven to have actually
executed. LTX rendered 1.79 render-seconds per output-second. WAN rendered 52.78. Measured
advantage: 29.5 times.

**ON-SCREEN TEXT:** LTX DISTILLED 2B · 29.528986x · 1.787565 vs 52.784974 RENDER-s / OUTPUT-s · docs/PROMOTION_BRIEF.md

**TRANSITION:** The winning volume compresses — visibly shrinking in place — and the camera follows
it down into a lower gallery.

---

## SCENE 06 — THE DIET

**VISUAL:** A character-model wireframe on a scale platform. Two solid meter-green readouts on the
wall: the production measurement, then the clamped measurement, lower. Below both, a DASHED amber
readout flickers and does not resolve. Nothing in the model's node graph is shown changing — the
graph hangs beside it, static, its links unedited.

**NARRATION:** The character engine measured just over 15 gigabytes in production. Clamped to a
13-gigabyte budget it passed warm at 12.84, with zero changes to the generation graph. Pushed to
12, it failed at 12.28 net. The failed run is the one the file still points at.

**ON-SCREEN TEXT:** HuMo 1.7B · 15.12 GB PRODUCTION → 12.84 GB CLAMP-13 WARM · CLAMP-12 FAIL 12.28 NET · docs/HUMO_DIET.md

**TRANSITION:** The static node graph rotates to face camera and dissolves into a suite tree of
eleven child nodes.

---

## SCENE 07 — ELEVEN OF ELEVEN, AND STILL A FAIL

**VISUAL:** A vertical suite tree. Eleven child gates light solid meter-green in sequence, top to
bottom. At the root, a single amber DASHED bracket measures the drift between two runs of the same
child — 0.330 against a limit of 0.250 — and the root node refuses to turn green.

**NARRATION:** The big H3 suite passed all eleven of its child gates. It still failed. One child's
peak drifted 0.330 gigabytes above its own earlier run, against a limit of 0.250. Eleven passes do
not outvote one measured drift. The suite stays failed until the drift is explained.

**ON-SCREEN TEXT:** 11/11 CHILD GATES PASS · SUITE FAIL · PEAK CREEP +0.330 GB (LIMIT 0.250) · ENGINE_MATRIX_BETA.md

**TRANSITION:** The unlit root node detaches and floats forward until it fills frame as a blank
paper-white panel — a human review card.

---

## SCENE 08 — THE PART A MACHINE CANNOT SIGN

**VISUAL:** Two lip-sync takes side by side as solid meter-green wireframe heads with their measured
values locked beneath them. Above both, an empty amber DASHED signature box. Far right, in dashed
amber, an isometric 8-gigabyte laptop sits alone with one solid meter-green tag on its chassis and
an empty receipt tray beside it.

**NARRATION:** Two speaking takes cleared the machine gate: 6.71 and 6.51 gigabytes, about five
minutes each. Whether the lips are right is not a number, and no receipt claims it is. Same rule on
the eight-gigabyte question. That laptop is real and inventoried — 8188 megabytes. It has a
hardware report and no render. Everything past that is dashed.

**ON-SCREEN TEXT:** H3 SEEDS 42/43 · 6.71 / 6.51 GB · HUMAN PENDING — RTX 4060 · 8188 MiB · HARDWARE_OBSERVED_NOT_ENROLLED · eightgb_bench/reports/

**TRANSITION:** All solid geometry drains from the room, leaving only the paper-white ceiling plane
in black. Audio cue cuts.

---

## SCENE 09 — CODA: WHAT THE LAB ACTUALLY PRODUCED

**VISUAL:** Silent. The empty hall from Scene 02, now dark, with the columns gone. The ceiling plane
remains, alone, and slowly rotates edge-on until it is a single paper-white line across black.

**NARRATION:** The deliverable is not a favorite engine. It is 276 receipts where the failures are
still readable, the tight passes are still labeled tight, and the parts no machine can judge are
still unsigned. The line was never about speed. It was about knowing which number you are allowed
to quote.

**ON-SCREEN TEXT:** MEASURED · RECORDED · UNSIGNED WHERE UNPROVEN

**TRANSITION:** The line thins to nothing. Two seconds of black.

---

## END CARD / SOURCES

**VISUAL:** Black. Citation list scrolls in meter-green monospace.
**NARRATION:** (silent — 2 seconds of black before end card)
**ON-SCREEN TEXT:**
SOURCES
• vram-recipe-lab — RESULTS.md (per-recipe measured peaks, warm-pass status)
• vram-recipe-lab — ENGINE_MATRIX_BETA.md (engine rows, suite creep gate)
• vram-recipe-lab — PREFLIGHT.md (origin: uncalled VRAM guard; 200 ms sampling; 14.5 GB ceiling)
• vram-recipe-lab — AGENTS.md (hard rules: warm-cache gating, clamp semantics, marginal-pass rule)
• vram-recipe-lab — docs/PROMOTION_BRIEF.md (normalized speed crown, casting recommendations)
• vram-recipe-lab — docs/HUMO_DIET.md (clamp-floor diet, clamp-12 failure)
• results/comparisons/general_video_speed_pair.json (29.528986x normalized pair)
• results/wan_i2v_14b_exoneration_832x480_f33_run2.json (warm pass, 13.93 GB)
• eightgb_bench/reports/physical-rtx4060-8gb-hardware.json (8188 MiB, not enrolled)

---

**Runtime estimate:** ~2:56 at ≈145 wpm
**Scene count:** 9 (+ end card)
**Narration word count:** ~425

**Production notes:**
- Strongest beat is Scene 01. Do not explain the gap before Scene 05 names the engines — the
  withheld name is the retention.
- Hold Scene 03 two beats longer than it feels comfortable. The over-height columns staying in
  frame *is* the argument; cutting fast reads as an apology.
- Scene 07 is the thesis scene for a technical audience. If any scene earns extra runtime, it is
  this one.
- If runtime must come down: collapse Scenes 03 and 04 into one "broken and re-measured" beat
  (saves ~35 seconds) before touching anything else.
- Every solid meter-green value on screen traces to a committed receipt path in the sources list.
  Anything not in that list must render dashed amber, including the entire 8 GB question.
