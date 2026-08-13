# MiniMax H3: five-candidate lab handoff for OTR

- **Status:** research and campaign design ready; H3-LIP-TXT is current-runner eligible after its transcript-window receipt, while H3-C032 remains behind the minimal front office
- **Research cutoff:** 2026-08-12, America/Los_Angeles
- **Lab snapshot:** [`e7398fdae74a10512a16004f7499575e68d5c882`](https://github.com/jbrick2070/vram-recipe-lab/commit/e7398fdae74a10512a16004f7499575e68d5c882)
- **OTR snapshot:** [`v2.0-alpha@c06128daa181ff802bc3bf79112e539eda1d8a02`](https://github.com/jbrick2070/ComfyUI-OldTimeRadio/tree/c06128daa181ff802bc3bf79112e539eda1d8a02)
- **Machine queue:** [`../research/h3_lab_candidate_campaign_2026-08-12.json`](../research/h3_lab_candidate_campaign_2026-08-12.json)
- **Runner prerequisite:** [`RUNNER_DIVISION_FRONT_OFFICE_2026-08-12.md`](RUNNER_DIVISION_FRONT_OFFICE_2026-08-12.md) and its [machine specification](../research/runner_division_front_office_2026-08-12.json)

## Executive verdict

Build the minimal Runner Division before profile-delta campaigns, then test exactly five H3 candidates. `H3-LIP-TXT` is the deliberate prompt-only exception: it may run now on the current runner after a fresh control and an unambiguous transcript-window receipt. Every row below has a credible path to a material gain. Nothing else enters this wave.

| Priority | Campaign | Material payoff sought | Worth the lab time? | Promotion threshold |
|---:|---|---|---|---|
| P0 | `H3-C032` | first-party memory/stability fixes and a trustworthy new baseline | **YES** | no regression; clean H3 VAE/A/V behavior; OTR smokes later |
| P0 | `H3-LIP-TXT` | visibly better lip synchronization for no runtime dependency | **YES** | both fixed seeds better or noninferior after a hash-bound transcript-window receipt |
| P1 | `H3-KJ-EXACT` | lower peak VRAM without approximate attention | **YES** | ≥0.50 GiB or ≥10% lower same-surface peak, ≤10% time penalty |
| P1 | `H3-SAGE-AUTO` | a potentially large sampling-speed win on Blackwell | **YES, controlled high-risk probe** | ≥25% lower end-to-end wall; clean I2V plus both Ref2VA seeds |
| P1 | `H3-T8` | the strongest credible render-time improvement | **YES after asset admission** | ≥40% lower end-to-end wall; lip-sync, identity, motion, and audio noninferior |

The active order is: **fresh native control and transcript window → current-runner H3-LIP-TXT → minimal Runner Front Office and all-82 R0 → fresh H3-C032 controls → KJ exact and Sage as separate branches → Turbo 8**. Never stack candidates until each passes alone.

## 1. The bench starts fresh

Existing receipts remain useful history, but none is a control for this campaign. The new front office changes runner identity, environment selection, output namespaces, and evidence binding. Therefore every comparison receives a fresh control and candidate under the same frozen Runner Division bundle.

The historical receipts say only that H3 has run on this RTX 5080 Laptop 16 GB:

| Historical lane | Recorded absolute peak | Recorded wall | Use now |
|---|---:|---:|---|
| `h3_t2v_low` | 6.37 GiB | 492.2 s | orientation only |
| `h3_r2v_low` | 7.20 GiB | 260.6 s | orientation only |
| `h3_i2v_suite_sentinel` | 7.44 GiB | 218.9 s | choose its graph shape, not its number |
| H3 768p-class I2V/T2V/R2V cells | 8.42–9.15 GiB | 936.5–1,182.5 s | orientation only |
| exact Ref2VA speech seeds 42/43 | 6.71/6.51 GiB | 305.3/297.8 s | artifacts need human phoneme review; not controls |

The prior H3 best suite remains a suite failure because its T1 peak rose 0.330 GiB over T0 against the 0.250 GiB creep gate. No child receipt turns that suite into a pass.

The post-campaign census found 82 checked-in recipes: 70 have same-name current aliases and 12 have none; six top-level aliases are orphaned for removed recipes. Of the 70 matched aliases, 58 use modern schemas (57 v3 and one v2) and 12 are legacy; 29 appear warm and six are marked promotion-ready. Two aliases bind active runner SHA-256 `6d6ac785…682776`, but **zero promotion-ready receipts bind it**. The method, predicates, and read commits are recorded in [`../research/handoff_census_2026-08-12.json`](../research/handoff_census_2026-08-12.json). This is why the lab must recertify claims rather than inherit them.

### Runner Division gate

Before `H3-C032`:

1. implement and statically test the minimal sealed front office described in the runner proposal: enrolled profile IDs only, direct argv launch, pinned Python/ComfyUI/node/model-path/argv identity, receipt profile/launch-spec binding, per-cell namespaces, and stale display;
2. enroll separate pinned profiles for ComfyUI 0.31.1/KJ 1.3.9 and ComfyUI 0.32.0/KJ 1.3.9;
3. keep the runner bundle identical while profiles hold version-specific roots, venvs, core hashes, user/input/output/temp/log paths, and package inventories;
4. complete the all-82-recipe R0 static census and the representative R1 parity panel;
5. recertify the two unique H3 shipping contracts with fresh controls;
6. display old receipts as historical in the front-office index without modifying their bytes.

The front office selects only an enrolled profile ID; it never accepts an arbitrary ComfyUI/Python root. The floor runner remains responsible for port 8199 ownership, the GPU lock, queue isolation, `/object_info`, fixtures, VRAM monitoring, artifact gates, cleanup, and immutable receipts.

The ACL-protected GPU-UUID mutex, model content-admission manifests, receipt-schema-v4 full field set, cross-clone contention tests, and recipe schema v2 are deferred. `H3-LIP-TXT` does not wait for this gate: it is allowed on the current runner only after its transcript-window receipt and fresh native control establish the comparison surface.

## 2. Corrections to the starting material

| Starting claim | Evidence-backed correction | Lab consequence |
|---|---|---|
| “H3 is fully usable on 16 GB” | This machine has historical successful 16 GB receipts; official sources do not certify a universal 16 GB threshold. | Make only receipt-bound claims after fresh Runner Division runs. |
| “Local H3 goes to 2K” | Local weights are H3-Base. Context-IR and Regenerate-2K are not released; the full 2K workflow is hosted. | The pinned official Comfy 16:9 control is 1344x768; no local 2K claim. |
| “Official footprint is ~42.5 GB” | The pruned/quantized Comfy-Org repack is 42.471 GB decimal for one task-family stack. FL2VA plus Ref2VA is 63.441 GB. | Count both task checkpoints for OTR capacity planning. |
| “ComfyUI 0.30+ is enough” | Native support began in 0.30.0; 0.32.0 adds relevant H3 VAE and peak-memory fixes. | Test 0.32 as the new first-party candidate baseline. |
| “Sage is proven here” | The old local probe used an explicit H3 FP16-PV path and failed with Windows `0x80000003`, a 1,801.5 s timeout, and no artifact. | Do not repeat that path. Test only the newer generic per-model KJ `auto` route, isolated and fail-fast. |
| “A non-H3 Sage parity gap justifies Runner Division” | `launch.sage_attention` is dead/unwired profile metadata: at OTR `c06128da…`, `nodes/_otr_shared/boot_contracts.py:171-175` states that no launcher passes an attention flag. Production is Sage-free; the live H3 `assert_sage_not_patched` safeguard remains separate. | Remove this rationale from Runner Division. Track the field for deletion from the profile schema or end-to-end wiring; it cannot justify architecture. |
| “Turbo means four steps” | Current evidence supports 6–8 as the serious lane; four steps can smear fast motion. | Test v4 at eight steps first; four steps gets no inherited verdict. |
| “Community W4A8/INT8 VAE numbers prove our gain” | File size and other-GPU reports do not establish lower peak or speed on this graph; ComfyUI 0.32 may already remove much of the VAE residency. | They are not in this five-candidate wave. |

First-party sources: pinned [MiniMax H3 model-card revision](https://huggingface.co/MiniMaxAI/MiniMax-H3/tree/939557dc319dd91227e30195a763f272ba7f8765), [ComfyUI native-support PR #15224](https://github.com/Comfy-Org/ComfyUI/pull/15224), [ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.32.0), and the [ComfyUI H3 tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3).

## 3. Reproducible official surface

### Exact Comfy-Org ComfyUI repack

Revision: `Comfy-Org/MiniMax-H3@014cd40f7e177756c6b2473c0d93b1c89a790dd2`.

| File | Exact bytes | SHA-256 | Role |
|---|---:|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 20,970,379,616 | `e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a` | T2VA/I2VA/first-last |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 20,970,379,616 | `9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779` | Ref2VA |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15,687,142,551 | `35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6` | text/vision encoder |
| `minimax_h3_video_vae_fp16.safetensors` | 5,207,808,496 | `7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522` | video VAE |
| `minimax_h3_audio_vae_fp32.safetensors` | 605,254,808 | `8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48` | audio VAE |

Hash the locally admitted files once into the new profile-specific model manifest. A later fast-fingerprint change requires a full rehash before allocation. Do not rewrite an old receipt.

### Pinned official workflow controls

Workflow-template commit: `5c75d9f137bb27706a70dd337dac6249b2e51ded`.

- [T2V JSON](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_t2v.json)
- [I2V / first-last JSON](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_i2v.json)
- [R2V JSON](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_r2v.json)

All use native video/audio decode and a 20-step `res_multistep`/`simple` baseline. The lab executes audited API recipes derived from these controls; it does not run downloaded UI graphs directly.

H3-Base produces 4–15 s at 24 fps with 32 kHz stereo. The conservative launch contract requires an image or video alongside reference audio: the August 3 MiniMax announcement says audio cannot be the sole reference, while newer first-party wording is less restrictive. OTR's image+audio route satisfies both readings.

## 4. Five admitted campaigns

### `H3-C032` — native ComfyUI 0.32

**Why this can matter:** v0.32 includes [H3 VAE chunked I/O](https://github.com/Comfy-Org/ComfyUI/pull/15446), an [H3 peak-memory lifetime fix](https://github.com/Comfy-Org/ComfyUI/pull/15486), and the nested-tensor tiled-decode fix in its release notes. It is also the prerequisite baseline for every later optimization.

**Independent variable:** only the ComfyUI core profile:

- A: `0.31.1@fe4195f7f4275f2626cbafc703acc3ddde1e5490`, KJ `1.3.9@b7646ad70a7daa7aeb919ca542274758d26ba2df`;
- B: `0.32.0@c2bcbecd82ec5ae66594340b395c24ef0217b238`, the same KJ revision.

Recipe schema v2 keeps one logical prompt and resolves it against each profile. The comparison verifier must prove equal prompt hashes and a complete surface diff containing only the enrolled core/profile fields and their version-specific source hashes.

**Fresh cells:** I2V sentinel, Ref2VA seeds 42 and 43, then the pinned official 1344x768 I2V control if the smaller cells are clean. Each profile gets a fresh process, one cold/JIT-classified run, and two warm campaign runs. Compare the second warm runs. If close to a threshold, repeat in A-B-B-A fresh-boot order.

**Gate:** exact media contract; no black/grid/tile/color/audio defect; candidate peak ≤ control +0.25 GiB; wall ≤ control +5%; human full-clip and ear review. Record which H3 fixes were reached. Passing this campaign changes the lab baseline first; OTR still needs separate lane smokes.

### `H3-LIP-TXT` — transcript-aware Ref2VA

**Why this can matter:** a [complete Tlano Ref2VA example](https://github.com/tlano-z/ComfyUI-MiniMax-H3-Workflows-For3060/blob/359ea78cb7eeb0d52ee13487bca014ade312c8ef/MiniMax-H3_R2V_Turbo_Lip-sync/MiniMax-H3_R2V_Turbo_Lip-sync.json) repeats the spoken line in the H3 prompt. Prompt construction adds no model or runtime dependency and directly targets OTR's unresolved lip-sync quality.

The Tlano graph is topology evidence only. Its active Turbo, TAE preview, and INT8 video VAE do not enter this prompt-only A/B; its repository launch guidance must not turn on global Sage for H3.

**No transcript assumption:** `tts_dialogue.wav` is 10.000 s while the target is 124/24 = 5.1667 s. Before writing a candidate prompt, create an immutable transcript-window receipt that binds:

- source fixture hash `30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1`;
- fresh native-control artifact/receipt hashes;
- the source interval that best aligns with the generated 5.1667 s audio stem, found by full-file sliding correlation and confirmed by ear;
- exact start/end samples and seconds, transcript text, reviewer/date, confidence, and method;
- a separate hash for the canonical UTF-8 transcript text.

If alignment is ambiguous, stop this campaign. Do not guess that the relevant text is the full file or the first 5.1667 seconds.

**Independent variable:** prompt text only. Keep full source fixture, portrait, seeds 42/43, 864x480, 124 frames, 24 fps, `ref_image_size=match`, `res_multistep`, `simple`, 20 steps, models, and graph links unchanged.

**Prompt pattern:**

```text
Use <Picture 1> as the sole character and identity reference. The character
speaks directly to camera using <Audio 1>. Precisely synchronize mouth shapes,
pauses, expression, and final mouth closure to <Audio 1>. Preserve identity,
clothing, framing, and one speaker throughout. No subtitle or extra dialogue.

Audio:
Voice:"<HASH-BOUND VERBATIM TRANSCRIPT FOR THE VERIFIED TARGET WINDOW>"
```

**Gate:** identical-seed native/transcript A/B for 42 and 43. Human review covers onset, consonant closures, vowels, pauses, phrase boundaries, final closure, identity, extra/dropped speech, and cross-seed consistency. Both seeds must improve or hold; one lucky take does not pass. OTR would keep muxing its untouched master audio.

### `H3-KJ-EXACT` — exact low-memory branch

**Why this can matter:** current KJNodes at [`6ab7e8130e449ed2c0037589bcf84146ceb7fc9c`](https://github.com/kijai/ComfyUI-KJNodes/tree/6ab7e8130e449ed2c0037589bcf84146ceb7fc9c) adds H3-specific token/head chunking intended to reduce transient sampling memory without changing the math:

- `MiniMaxChunkFeedForward`: `chunks=2`, `seq_threshold=4096`;
- `MiniMaxLowVRAMAttention`: `head_chunks=4`;
- `MiniMaxH3TokenCounter`: observational packed-token measurement.

The enrolled KJ revision must include the [unsafe-pickle security fix](https://github.com/kijai/ComfyUI-KJNodes/commit/073efb07419f56cc714e099a82e49fbc23ad9263). If the pinned source is not already admitted locally, the cell remains unqueued until the operator supplies/authorizes it under repository policy.

**Fresh cells on the passed 0.32 profile:** plugin-present/bypassed control; FFN-only; attention-head-only; pair only after both individual cells pass. Each ordered patch chain gets a fresh process. The token counter is receipt-bound and must not alter the sampled branch.

**Gate:** ≥0.50 GiB absolute or ≥10% same-surface peak reduction, ≤10% wall penalty, exact graph/model/seed/sampler/decode surface, pixel/audio comparison, and human review. Upstream “identical” is a lab hypothesis until the paired receipts prove it here.

### `H3-SAGE-AUTO` — most-likely working Sage challenger

**Why this can matter:** the [official ComfyUI tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3) recommends the generic KJ Sage patch in the model path. A large sampling-speed win would materially improve OTR value even though the previous local Sage experiment failed.

This is a different route from the failed receipt:

| Old negative probe | New admitted probe |
|---|---|
| H3-specific explicit FP16-PV kernel | generic UI node `Patch Sage Attention KJ` |
| `sageattn_qk_int8_pv_fp16_cuda` | `sage_attention="auto"` |
| old KJ profile | enrolled KJ `6ab7e8…` or separately reviewed later pin |
| 1,801.5 s timeout | 600 s hard ceiling on the first sentinel |

The code class is spelled `PathchSageAttentionKJ`; its UI name is `Patch Sage Attention KJ`. Use `allow_compile=false`. Keep the boot argv globally Sage-free; this is only a per-model `optimized_attention_override` between model load and guider. The current KJ generic path lets SageAttention choose the backend and includes an int32-row-offset contiguity guard.

**Preflight:** pin the SageAttention package and complete environment inventory; run `MiniMaxH3TokenCounter`; abort if it warns that the packed range is unsafe; validate the node and inputs from live `/object_info`; run a plugin-present/bypassed SDPA control first.

**Escalation ladder:**

1. fresh-process 864x480, 124-frame I2V sentinel, fixed seed, no reference audio;
2. one cold/JIT-classified probe with a 600 s ceiling, then two clean warm campaign runs;
3. only after clean I2V, run exact Ref2VA seed 42 and seed 43 with native video/audio decode;
4. if close to passing, repeat the pair A-B-B-A with fresh process boundaries.

**Isolation:** no global Sage flag, explicit FP16-PV route, H3-specific memory-efficient Sage patch, Turbo, Spectrum, FirstBlockCache, KJ exact-memory patch, or other accelerator in this campaign.

**Immediate abort:** Windows fatal exception, CUDA illegal access, OOM, timeout, black/noise/grid output, audio corruption, foreign queue entry, uncertain prompt state, or unproved cleanup. The process and its compiled-kernel cache are then quarantined; they never return to a baseline lane.

**Gate:** ≥25% lower end-to-end wall at unchanged graph surface, peak ≤ control +0.25 GiB, two clean warm campaign receipts, machine A/V gates, and human full-clip review for I2V plus both Ref2VA speech seeds. Sage becomes only a new experimental OTR profile if it clears all three outputs.

### `H3-T8` — Turbo at eight steps

**Why this can matter:** Turbo is the strongest credible large speed thesis, with pinned code, complete graphs, and example output. It is worth the maintenance only if the gain remains large after exact OTR-shaped quality review.

**Preferred route:** [Larry MiniMax H3 Turbo](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo/tree/546b5028f4934f5129eb6c7142c2f3e461dfddbf), pinned after the audio-reference AdaLN-row fix, plus [`minimax_h3_turbo_v4_step600_ema.safetensors`](https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora) at strength 1.0 and eight steps.

**Compatibility references:** the [drbaph pruned-conversion graph](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/blob/498f1e2ca02e10a598f21267739f30073f68eb10/fl_minimax_h3_turbo_lora_example_workflow.json) and the [Tlano Ref2VA lip-sync graph](https://github.com/tlano-z/ComfyUI-MiniMax-H3-Workflows-For3060/blob/359ea78cb7eeb0d52ee13487bca014ade312c8ef/MiniMax-H3_R2V_Turbo_Lip-sync/MiniMax-H3_R2V_Turbo_Lip-sync.json). Choose and pin one provenance route before admission; do not mix conversions/settings. The drbaph conversion removes incompatible AdaLN pairs and must be labeled as such.

No Turbo weight is currently admitted. Operator authorization to acquire it is only the first gate: also record creator terms, H3 grant scope, expected bytes/hash, quarantine inspection, and model-manifest admission. Never redistribute the weight.

**Fresh cells:** native 20-step I2V control versus Turbo 8; native versus Turbo 8 for Ref2VA seeds 42/43 after the transcript campaign resolves. No Sage, Spectrum, TAE in the headless benchmark, W4A8, or four-step claim.

**Gate:** ≥40% lower end-to-end wall at identical canvas/frames/delivery; both speech seeds human-noninferior; no doubled/dropped syllables, identity drift, frozen motion, fast-motion smear, audio click, duration change, or final-mouth regression. Turbo 4 may be proposed only after Turbo 8 passes and receives a separate verdict.

## 5. Lab execution and evidence contract

For every campaign cell:

1. use a trusted recipe and enrolled profile under the frozen Runner Division bundle;
2. acquire the global GPU-UUID mutex and port-8199/server lease before any HTTP request;
3. verify exact Python, ComfyUI, package, custom-node, model, fixture, graph, launch, GPU, and output identities;
4. use run-private user/input/output/temp/log/cache namespaces;
5. validate JSON, topology, widget/input schemas, and every `class_type` against live `/object_info`;
6. run a fresh matched control; prior receipts never supply the comparison number;
7. classify compile/load runs as cold; the repository's second-consecutive-run rule remains the basic PASS, while these campaigns require two warm measurements for comparison;
8. record baseline/absolute VRAM, host RAM, sampling/decode/total wall where instrumented, media contract, artifact/model/graph/node/profile/runner hashes, stdout/stderr/log hash, and cleanup proof;
9. bind machine receipt, artifact, full-clip human review, and transcript receipt by SHA-256 without editing machine archives;
10. generate comparison documents through the deterministic builder and its exact-file tests;
11. stop on the campaign's significance gate; do not rescue a miss by stacking another accelerator;
12. leave OTR untouched.

| Claim | Minimum significance |
|---|---|
| lower VRAM | ≥0.50 GiB or ≥10% lower same-surface peak; ≤10% wall penalty |
| Sage speed | ≥25% lower end-to-end wall plus clean I2V and two Ref2VA speech outputs |
| Turbo speed | ≥40% lower end-to-end wall plus noninferior A/V and identity |
| lip-sync | both fixed seeds visibly better or noninferior across the hash-bound speech window |
| core migration | no A/V/media regression, ≤0.25 GiB peak increase, ≤5% wall increase |

## 6. OTR promotion shape

The current OTR H3 contracts are pinned at the snapshot:

- [`h3_low_video` adapter](https://github.com/jbrick2070/ComfyUI-OldTimeRadio/blob/c06128daa181ff802bc3bf79112e539eda1d8a02/nodes/_otr_video_engines/eng_minimax_h3.py) and [lane-19 receipt](https://github.com/jbrick2070/ComfyUI-OldTimeRadio/blob/c06128daa181ff802bc3bf79112e539eda1d8a02/docs/evidence/lane_receipts/lane19-h3_low_video.md);
- [`h3_low_audio_in` profile](https://github.com/jbrick2070/ComfyUI-OldTimeRadio/blob/c06128daa181ff802bc3bf79112e539eda1d8a02/config/profiles/otr_h3_low_audio_in.json) and [lane-20 receipt](https://github.com/jbrick2070/ComfyUI-OldTimeRadio/blob/c06128daa181ff802bc3bf79112e539eda1d8a02/docs/evidence/lane_receipts/lane20-h3_low_audio_in.md).

At this OTR HEAD, 51 tracked profile JSON files (excluding `widget_mapping`) yield 32 shipping rows and 22 unique video-engine IDs. Four H3 rows collapse to these two registered contracts. The 21 closed lane packets include lane 19 and lane 20 as those registered adapters plus lane 21 `h3_low_mime`, a standalone runner that is deliberately not registered and therefore is not a third H3 shipping contract.

They use a Sage-free H3 boot, 864x480, 20 steps, 24-to-25 fps duration-preserving delivery, and external source-audio muxing. A passing candidate becomes a **new experimental adapter/profile** first. It does not mutate either shipping lane in place.

- Transcript promotion belongs in the Ref2VA prompt builder and requires exact beat transcript/window provenance.
- KJ exact promotion requires a pinned dependency/profile and only proceeds if its VRAM gain is material.
- Sage promotion remains a per-model graph patch in a distinct profile; it never flips the shared H3 boot flag.
- Turbo promotion receives a distinct loader/sampler/profile and its own model admission receipt.
- Native H3 generated/reconstructed audio remains diagnostic; OTR's untouched master track remains authoritative.

Every proposal needs OTR preflight requirements, engine-matrix/test updates, provenance/license notes, a same-beat comparison, and a new live smoke receipt after separate authorization to work in OTR.

## 7. License and distribution gate

The default [MiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) excludes the United States, European Union, United Kingdom, and Republic of Korea and is non-transferable. This repository records a separate August 8 authorization in [`H3_LICENSE_GRANT.md`](H3_LICENSE_GRANT.md) for the named grantee **“Blueberrky Kale Yoga Books,”** conditioned on the complete request and authorization email.

Operationally, that record supports the named grantee's stated US local/offline/noncommercial/no-hosting/no-weight-redistribution lane, subject to authenticity and the full terms. It does not automatically authorize Jeffrey personally, collaborators, downstream users, commercial service, derivative-weight redistribution, or worldwide public display of outputs into every excluded territory.

Before any broader use:

- preserve the full request and email; seek confirmation of the grantee spelling;
- keep all base/quant/LoRA/VAE weights local and never bundle or mirror them;
- review every creator's terms and the H3 base terms;
- treat workflow/integration sharing as a separate license review, not automatically harmless;
- require machine-generation disclosure on public output and separately verify territorial display rights;
- do not use H3 outputs to improve a different AI model except as the governing license permits.

This is an operational gate, not legal advice.

## 8. Ready-to-paste lab directive

```text
Read AGENTS.md, BOOT.md, PREFLIGHT.md,
docs/RUNNER_DIVISION_FRONT_OFFICE_2026-08-12.md,
docs/H3_LAB_CANDIDATE_HANDOFF_2026-08-12.md, and
research/h3_lab_candidate_campaign_2026-08-12.json in full.

First, run H3-LIP-TXT on the current runner only after a fresh native control
and an unambiguous hash-bound transcript-window receipt. Prompt text is its sole
independent variable; use fresh same-runner controls and candidates for both
seeds. Treat every old receipt as immutable history, never as a new control.

Then build only the minimal Runner Front Office: enrolled profile-ID selection,
pinned Python/ComfyUI/node/model-path/argv identity, direct argv launch,
profile and launch-spec receipt binding, per-cell output/result/log namespaces,
and a computed stale display. Preserve port 8199 ownership, `.gpu.lock`,
`/object_info`, fixture/media gates, VRAM monitoring, append-only receipts, and
cleanup proof. Defer the GPU-UUID ACL mutex, content-admission manifests,
receipt-schema-v4 full field set, cross-clone tests, and recipe schema v2.

After the all-82-recipe R0 and minimal front-office checks, run H3-C032 as a
matched fresh 0.31.1/0.32.0 pair. Enroll the reviewed KJ profile and test
H3-KJ-EXACT and H3-SAGE-AUTO as separate branches; Sage uses only the generic
per-model auto patch on a globally Sage-free H3 boot and stops at the first
corruption, timeout, or cleanup uncertainty. H3-T8 remains unqueued until its
artifact is explicitly authorized and admitted. Do not touch OTR and do not
download any asset.

Move nothing into OTR unless an individual campaign clears its machine,
significance, full-clip human, provenance, and license gates and Jeffrey gives
a separate promotion verdict.
```

## Bottom line

This is no longer a grab bag of community optimizers. It is a fresh-bench program with five plausible wins: **better core → better lip-sync → exact lower memory → carefully retried Sage → Turbo speed**. The Runner Division makes every answer attributable—and lets the lab discover that an old “truth,” including the Sage failure, was only true for the surface that produced it.
