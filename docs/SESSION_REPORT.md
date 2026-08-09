# Session Report - Final Video-Lane Close-Out

Date: 2026-08-09

## Completion status

The consolidated render campaign is machine-complete. It produced the normalized
general-video speed pair, two H3 speaking takes, all three LTX Audio HQ rungs, the WAN
I2V clamp exoneration pair, the H3 asset inventory, one failed per-model Sage probe,
the complete LTX motion ladder, and one corrected unconditioned Mini Mime proof.

This is a truthful lab milestone, not blanket promotion. The remaining work is human:

- Jeffrey must rank the two H3 speaking takes for actual lip sync and consistency and
  compare them with HuMo on the OTR side;
- Jeffrey must approve the best LTX HQ clip and rank M0-M3 for motion and beat response;
- Jeffrey must apply the Mini Mime inverted ear gate; and
- no blocked weight download or additional experimental render is implied.

The controlling recommendation summary is
[PROMOTION_BRIEF.md](PROMOTION_BRIEF.md).

## Consolidated-order outcomes

### 1. Same-canvas speed pair

WAN TI2V 5B and LTX Video distilled 2B both completed warm, nonce-proven executions at
**832x480, 193 frames, 25 fps, and 7.72 delivered seconds**. WAN took **407.5 seconds**
and measured **52.784974 render seconds per output second** and **0.189145
megapixel-frames per second**. LTX took **13.8 seconds** and measured **1.787565** and
**5.585252** on the same normalized metrics. LTX therefore won by **29.528986x** in
warm wall clock. [Normalized speed-pair evidence](../results/comparisons/general_video_speed_pair.json)

The user-reported `ltx_8gb` **20.3 seconds / 25 frames** and `ltx_video`
**83.8 seconds / 193 frames** rows remain `UNNORMALIZED` because canvas, steps, and
exact model were not supplied. They were recorded but excluded from ranking.
[Unnormalized-row provenance](../results/comparisons/general_video_speed_pair.json)

### 2. H3 speaking two-take package

The H3 lab half used the working medium-close speaking prompt with the same portrait
and TTS fixture. Seed 42 completed in **305.3 seconds** at **6.71 GiB** peak; seed 43
completed in **297.8 seconds** at **6.51 GiB** peak. Both are **864x480, 124-frame,
24-fps** cold machine-gated outputs. Artifact, recipe, fixture, and receipt hashes are
packaged in [the H3 A/B evidence](../results/comparisons/h3_lipsync_ab_package.json).

The technical visual screen sees articulation, but true phoneme timing, pause settling,
and cross-seed consistency remain `PENDING_HUMAN`. HuMo was not run because its wrapper
is outside the lab whitelist. The exact-fixture HuMo comparison belongs OTR-side and
is the sole open character-lane casting decision. The corrected H3 graph uses exactly
`portrait.png` plus raw `tts_dialogue.wav`; their hashes are frozen in the package.

The earlier no-lipsync conclusion from the neutral wide-shot RefAudio test remains
retracted: that prompt did not request mouth movement. The current speaking takes are
the first valid prompt-level test; they do not retroactively change the old artifact.

### 3. LTX Audio HQ ladder

Every rung passed a second consecutive true execution. H1 certified
**1024x576 / 97 frames** at a **7.06 GiB** warm peak; H2 certified
**832x480 / 193 frames** at **7.93 GiB**; H3 certified
**1024x576 / 193 frames** at **7.36 GiB**. H3 is the best machine-certified
configuration because it composes the independently fitting canvas and duration
changes. Jeffrey's full-clip quality gate remains pending.
[HQ ladder evidence](../results/comparisons/ltx_audio_hq_ladder.json)

### 4. WAN I2V 14B exoneration

The corrected target-card clamp exonerated WAN I2V 14B at **832x480 / 33 frames**.
The cold run used **11.90/12 GiB net allocation**, leaving only **0.10 GiB** clamp
headroom; the warm run also passed. It is viable, but WAN TI2V remains the safer
default recommendation because the cold clamp margin is tight.
[WAN I2V exoneration evidence](../results/comparisons/wan_i2v_14b_exoneration.json)

### 5. H3 turbo inventory

The Kijai W4A8-mixed H3 diffusion weight and H3-compatible LightX2V four-step LoRA are
both absent. The local LightX-named LoRA belongs to WAN I2V 14B and was not misapplied.
The turbo variant is `BLOCKED_MISSING_BOTH_ASSETS`; no model was downloaded.
[Inventory evidence and no-download proposal](../results/comparisons/h3_speed_stack_inventory.json)

If Jeffrey later authorizes downloads, the proposed next campaign is: quarantine the
two H3 assets, hash them into the local manifest, then build and gate a new immutable
turbo recipe. That proposal does not authorize a download in this session.

### 6. Per-model Sage probe

The explicit KJ per-model FP16-PV Sage variant failed with Windows exception
`0x80000003` at sampler step zero. It timed out after **1801.5 seconds**, produced no
artifact, and the owned server cleanup succeeded.
[Sage probe evidence](../results/comparisons/h3_sage_patch_probe.json)

The probe is a measured failure on sm_120 and must never become the default. It does
not authorize the global Sage flag previously associated with silent-noise failure.

### 7. LTX motion ladder

M0 through M3 all produced labeled cold machine-gated artifacts. The contact-sheet
technical screen reads M0/M1/M2 as near-still and M3 as a slow camera
translation/zoom. Jeffrey's full-clip ranking and beat-response judgment are pending,
so the campaign does **not** conclude that LTX IA2V is inherently near-still.
[Motion-ladder evidence](../results/comparisons/ltx_motion_ladder.json)

### 8. Corrected unconditioned Mini Mime

The final Mime graph has picture input and model-native audio output with no external
audio-conditioning input. It binds a real ledger slot and delivered exactly
**192 frames at 24 fps / 8.000 seconds**. The cold machine pass peaked at
**6.71 GiB** and completed in **542.9 seconds**.
[Mime machine evidence](../results/comparisons/h3_mime_unconditioned.json)

FFmpeg 8.0.1 objective QA measured **-31.32 LUFS**, **1.00 LU** loudness range, and
**-13.55 dBTP** true peak, with zero detected continuous-silence events at each tested
threshold/duration pair. That supports a continuous, non-silent stream-level read at
the tested thresholds, while explicitly leaving noise, distortion, speech/vocal
absence, and diegetic synchronization to
Jeffrey's ears. [Mime audio QA evidence](../results/comparisons/h3_mime_audio_qa.json)

The inverted ear gate remains `PENDING_HUMAN_AUDITION`. No speech-like or vocal-like
content of any intelligibility and coherent diegetic sync must both be confirmed before any Mime
promotion.

### 9. Duration and feasibility intel

The duration matcher now treats **192 frames on H3's 17k+5 grid as exactly 8.000
seconds at 24 fps**. The token estimator is explicitly limited to output visual tokens
and is not a VRAM predictor. The two local checks pair **14,985 tokens / 6.71 GiB** and
**23,085 tokens / 6.71 GiB** across different graphs; no memory ceiling is inferred.
[Duration and token-budget evidence](../results/comparisons/h3_token_budget_check.json)

The public commenter result of **692x692 nominal / 192 frames in 210 seconds on an
8 GB laptop** stays `EXTERNAL-REPORTED`. The same external source reports that vocal
separation can improve synchronization; that was not measured locally. Reference image
sizing remains `match`. [External claim and scope](../results/comparisons/h3_token_budget_check.json)

## Historical evidence preserved

- The original RefAudio no-lipsync verdict is retracted, with its prompt omission
  recorded in [VIDEO_RECIPE_ATTEMPTS.md](VIDEO_RECIPE_ATTEMPTS.md).
- The RefAudio reconstruct-not-compose conclusion remains the reason the final Mime
  graph was unconditioned. [Receipt-bound reconstruction analysis](../results/comparisons/h3_refaudio_reconstruction.json)
- The canonical H3 best suite remains a formal machine failure despite valid
  individual warm pairs. [Immutable suite outcome](../results/h3_best_suite.json)
- LTX T2V remains closed after the exhausted attempt allowance.
  [Controlling escalation record](ESCALATE.md)
- Previous human visual approvals and experimental verdicts remain in their original
  receipts; none is generalized to a new recipe or seed.

## Recommendation state

The final recommended casting is provisional:

- sprint/general video: LTX Video distilled 2B;
- workhorse lips candidate: H3 Ref2VA if the OTR-side A/B confirms sync and
  consistency; and
- hero lips incumbent: HuMo until that same comparison supports a change.

LTX Audio HQ H3 (**1024x576 / 193 frames**) is the best machine-certified HQ recipe,
pending Jeffrey's eyeball.
[HQ recommendation evidence](../results/comparisons/ltx_audio_hq_ladder.json)

## Environment seed and safety

Distribution seed 2.1 pins Windows 11 build `10.0.26200`, Python `3.12.11`, Torch
`2.10.0+cu130`, CUDA runtime `13.0`, SageAttention
`2.2.0+cu130torch2.9.0andhigher.post4`, driver `610.88`, and an RTX 5080 Laptop GPU at
compute capability `12.0`. It pins ComfyUI `0.31.1` at commit
`fe4195f7f4275f2626cbafc703acc3ddde1e5490`, ComfyUI-GGUF `1.1.10`, and
ComfyUI-KJNodes `1.3.9` at commit
`b7646ad70a7daa7aeb919ca542274758d26ba2df`. FlashAttention-2 is absent and
unsupported. [Exact environment receipt](../results/comparisons/environment_2p1.json)

All campaign renders used the owned offline lab lane. No model weights were downloaded,
the OTR repository and port 8188 were not touched, and no push is authorized. The
driver reports the final offline test and paper-validation passes green. The local
commit and final verified clean server/lock state remain the driver's administrative
close-out steps; this report does not claim them before they occur.
