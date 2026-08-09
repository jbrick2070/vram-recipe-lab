# Session Report - Final Video-Lane Close-Out

Date: 2026-08-09

## Completion status

The consolidated render campaign is machine-complete. It produced the normalized
general-video speed pair, two H3 speaking takes, all three LTX Audio HQ rungs, the WAN
I2V clamp exoneration pair, the H3 asset inventory, one failed per-model Sage probe,
the complete LTX motion ladder, one corrected unconditioned Mini Mime proof, and the
final production-lane HuMo leg: two 1.7B runs plus one 14B FP8 run measured OTR-side.

This is a truthful lab milestone, not blanket promotion. The remaining work is human:

- Jeffrey must judge lips, onset, and identity across the complete five-clip HuMo/H3
  package;
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
and cross-seed consistency remain `PENDING_HUMAN`. The corrected H3 graph uses exactly
`portrait.png` plus raw `tts_dialogue.wav`; their hashes are frozen in the package.
HuMo was correctly excluded from the lab wrapper and has now been measured through its
OTR production wrapper; the resulting five-clip human review is the sole open
character-lane casting decision. [Complete bakeoff](HUMO_BAKEOFF.md)

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

### 10. HuMo production-lane bakeoff

The final character-lane leg used OTR's existing `HUMO` boot lane and smallest
single-clip production-wrapper probe. No OTR graph, profile, or production engine code
was edited. A lab-owned sidecar sampled absolute GPU VRAM and system-wide used RAM at
200 ms intervals from command start through durable artifact save.

That probe has no `--profile` argument. `otr_w45_humo_1_7b` and `otr_w45_humo` were
references for equivalent production engine defaults, not applied profile JSONs; the
exact route used registered engine IDs `humo_1.7B` and `humo`, and no full 45-word
campaign ran. [Receipt-bound route](HUMO_BAKEOFF.md#fixture-and-route-contract)

HuMo 1.7B produced two **480x832, 129-frame, 25-fps / 5.160-second** takes. They took
**233.779852** and **207.513477 seconds**, or **45.306173** and **40.215790 render
seconds per output second**; their absolute VRAM peaks were **15.118164** and
**15.231445 GiB**, and their peak system-RAM readings were **35.136196** and
**36.078560 GiB**. The production probe exposes fixed seed **7**, so both runs used
that seed and produced byte-identical native video rather than an alternate-seed pair.
[HuMo 1.7B take 1 receipt](../results/otr_side/humo_1_7b_bakeoff_take1.json) and
[take 2 receipt](../results/otr_side/humo_1_7b_bakeoff_take2.json)

HuMo 14B FP8 produced one **480x832, 97-frame, 25-fps / 3.880-second** take in
**245.943975 seconds**, or **63.387622 render seconds per output second**, at an
absolute **14.984375 GiB** VRAM peak and **51.629864 GiB** peak system-RAM reading.
Its 97-frame production cap makes it shorter than the 5.16-second comparison clips,
so it is measured but not normalized into the duration-matched speed comparison.
[HuMo 14B receipt](../results/otr_side/humo_14b_fp8_bakeoff_take1.json)

The exact portrait and TTS bytes match the H3 fixture hashes, but the source TTS is
**10.000 seconds**, H3 delivers **5.167 seconds**, HuMo 1.7B delivers **5.160
seconds**, and HuMo 14B delivers **3.880 seconds**. This is fixture parity, not full
workload-duration parity. The native HuMo clips are production-policy silent; review
copies mux the exact source audio at timestamp zero while stream-copying video.
[Five-clip contract and review sheet](HUMO_BAKEOFF.md)

All five lips/onset/identity verdicts remain `PENDING_HUMAN`. The historical F7
**100-200 ms audio-lead** hypothesis remains a listening target, but OTR's later M1
measurement did not reproduce it and instead estimated a roughly **30-60 ms video
lead**. The current review must listen for offset in either direction.
[OTR M1 measurement](../../custom_nodes/ComfyUI-OldTimeRadio/docs/2026-08-02-MEASUREMENT-M1-humo-lipsync-offset.md)

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
- workhorse lips candidate: H3 Ref2VA if the five-clip review confirms sync and
  consistency; and
- hero lips incumbent: HuMo until that same review supports a change.

Measurement coverage is **COMPLETE**; the character-lane decision remains
`PENDING_HUMAN`. [HuMo/H3 bakeoff](HUMO_BAKEOFF.md)

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

All lab campaign renders used the owned offline lab lane; the final HuMo measurements
used the owned OTR production `HUMO` lane. No model weights were downloaded, port 8188
was not touched, and no push is authorized. The OTR worktree was already dirty before
this render-only session. Its HEAD, status lines, and captured file hashes are unchanged
relative to entry, so production OTR code was not altered; it cannot honestly be
described as clean. The pre-existing untracked `kibitz/` marker matches, but nested
contents were outside the byte-identity scope.
[Worktree-integrity receipt](../results/otr_side/otr_worktree_integrity.json)
Final server shutdown is proved by the absence of listeners on ports 8000 and 8199,
and the complete offline test and recipe-validation suites passed. The local lab
commit is the remaining handoff action; no push is authorized.
