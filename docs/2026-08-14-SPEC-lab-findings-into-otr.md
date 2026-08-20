# Specification: Lab Findings Integration into OTR

- **Document ID**: `OTR-SPEC-2026-08-14-LAB-FINDINGS`
- **Status**: DRAFT / LAB SEALED SPECIFICATION (FOR OTR IMPLEMENTATION REVIEW)
- **Target Repository**: `OTR` (Off The Rails Production Engine)
- **Author**: Antigravity Lab Controller (based on `vram-recipe-lab` evidence)
- **Date**: 2026-08-14

---

## 1. Purpose & Scope

This specification compiles and formalizes the empirical findings, model recipes, VRAM ceilings, and runtime configurations measured in `vram-recipe-lab` into actionable implementation instructions for the **OTR production engine**.

All parameters and architectures specified in this document are bound to immutable, receipt-verified evidence on both the RTX 5080 Laptop GPU (16 GB / Blackwell `sm_120`) and the isolated physical RTX 4060 Laptop GPU (8 GB).

---

## 2. Production Engine Matrix Allocation

| Production Role | Selected Engine | Primary Workload Specification | Peak VRAM | Measured Speed / Headroom | Evidence Reference |
|---|---|---|---|---|---|
| **Sprint / Fast Video** | **LTX Video 2B Distilled** | 832x480, 193f @ 25 fps (7.72s) | **13.11 GiB** | **13.8s warm** (29.53x faster than WAN) | `results/comparisons/general_video_speed_pair.json` |
| **High-Quality AV** | **LTX Audio HQ** | 1024x576, 193f @ 25 fps (7.72s) | **7.36 GiB** | High spatial quality, balanced AV latent | `results/comparisons/ltx_audio_hq_ladder.json` |
| **Hero Character Lipsync** | **HuMo 1.7B (VRAM Diet)** | 480x832, 129f @ 25 fps (5.16s) | **12.84 GiB** | Low latency; fits inside 14.5 GB ceiling via clamp-13 | `docs/HUMO_DIET.md` |
| **Dialogue Video (8 GB)** | **MiniMax H3 (`h3_audioin_lowvram`)** | 864x480, 124f @ 24 fps (5.17s) | **7.00 GiB** | Crisp phoneme lipsync via verbatim quotes + `<Audio 1>`; fits 8 GB cards | `eightgb_bench/local/cells/h3-r2v-dialogue-demo-f124/` |
| **Action Video (8 GB)** | **MiniMax H3 (`h3_lowvram`)** | 864x480, 90f @ 24 fps (3.75s) | **7.21 GiB** | Full physical 8 GB validation; unconditioned sound | `eightgb_bench/local/cells/h3-mime-i2v-action-demo-f90/` |

---

## 3. Lane Specifications & Graph Blueprints

### Lane 1: Sprint Video Lane (`ltx_video_2b_distilled`)
* **Objective**: Rapid iteration and storyboard drafting.
* **Model Configuration**:
  * Checkpoint: `ltx-video-2b-v0.9.1.safetensors` (or distilled 2B counterpart).
  * Sampler: 20-step distilled schedule.
  * Resolution: `832x480` @ 25 fps, 193 frames.
* **Key Implementation Details**:
  * Replaces legacy WAN TI2V 5B for quick iteration passes.
  * Wall-clock duration is reduced from ~407.5 seconds to **13.8 seconds** warm.

---

### Lane 2: High-Quality Audio-Video Lane (`ltx_audio_hq`)
* **Objective**: Episodic scenes requiring combined native soundtrack synthesis and high visual fidelity.
* **Model Configuration**:
  * Resolution: `1024x576` @ 25 fps, 193 frames.
  * VRAM Ceiling: **7.36 GiB** peak (safe on 12 GB and 16 GB hardware).
* **Key Implementation Details**:
  * Full-frame dual latent decoding with direct connection to `CreateVideo.audio`.
  * Verified stable across `H1` (1024x576x97), `H2` (832x480x193), and `H3` (1024x576x193).

---

### Lane 3: Character Dialogue & Lip-Sync (`h3_audioin_lowvram` / HuMo)
* **Objective**: High-accuracy phoneme-synchronous character speech and episodic dialogue clip animation.
* **Architecture Rules**:
  1. **HuMo 1.7B Hero Lane**:
     * Must be deployed with the **Clamp-13 / No-Pinned Memory** boot wrapper (`--reserve-vram 2.921` on 16 GB physical cards, `--disable-pinned-memory`).
     * Prevents the unmanaged 15.23 GiB memory spikes observed in stock OTR runs without altering model weights or graph math.
  2. **MiniMax H3 Low-VRAM Dialogue Lane (`h3_audioin_lowvram`)**:
     * Primary role: Takes an episodic scene/character still (`<Picture 1>`) + generated TTS audio line (`<Audio 1>`) and animates full phoneme-synced dialogue clips in 16:9 widescreen at **7.00 GiB VRAM** (fully compatible with 8 GB cards!).
     * Flat-V3 dotted socket topology: `ref_images.ref_image_0` (`<Picture 1>`) and `ref_audios.ref_audio_0` (`<Audio 1>`).
     * **Mandatory Verbatim Line Injection & Viseme Prompting**:
       Because `Qwen3-VL` (the 32B multimodal text encoder) cross-attends text tokens with both visual visemes and `<Audio 1>` latent tokens, all OTR dialogue prompt builders must inject the literal line text in quotation marks:
       ```text
       A medium close shot of <Picture 1> delivering the exact line "{dialogue_line_text}" directly to the camera with an expressive tone matching the timing and cadence of <Audio 1>. His lips, jaw, and facial expression must stay tightly synchronized to the audio.
       ```
       *Benefit*: Supplying the literal words in quotes prevents phoneme guessing from raw audio waveforms and drastically sharpens lip articulation.

---

### Lane 4: 8 GB Hardware Action Beat Clips (RTX 4060 Compatible)
* **Objective**: Generation of episodic action/incident clips on 8 GB VRAM GPUs.
* **Model Stack**:
  * Diffusion: `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (INT8)
  * Text Encoder: `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (NVFP4 AWQ)
  * VAEs: `minimax_h3_video_vae_fp16` + `minimax_h3_audio_vae_fp32`
* **Mandatory Prompt Template ("Stills & Beats" Rule)**:
  * *Context*: Lab testing confirmed that passive/subtle prompts collapse H3 into static still-holds.
  * *Rule*: All OTR prompt generators targeting this lane must mandate active verbs and structured beat sequences:
    ```text
    [Preserve character identities and room geometry from starting still] +
    [Trigger Event / Alarm / Action Beat] +
    [Character Physical Reaction & Movement] +
    [Camera Arc / Push / Pan Choreography] +
    [Soundtrack SFX directive without dialogue]
    ```

---

### 3.5. Engine Capabilities, Frame Formulas & Multi-Clip Chaining Matrix

To satisfy OTR's `VIDEO_LANE_PREFLIGHT.md` requirements, every registered video engine defines its exact mathematical frame contract, still parameter behavior, and multi-clip chaining support:

| Engine Adapter | Target FPS | Frame Stepping Formula | Min Frames (s) | Max Frames (s) | First Frame / Still Support | Last Frame Support | Reference Audio | Native Aspect Ratios |
|---|---|---|---|---|---|---|---|---|
| **`eng_ltx_distilled`** | **25.0** | **$8k + 1$** | 25f (1.00s) | 193f (7.72s) | **YES** (`first_frame`) | **YES** (`last_frame`) | None | 16:9 (`832x480`), 9:16 (`480x832`) |
| **`eng_ltx_audio_hq`** | **25.0** | **$8k + 1$** | 97f (3.88s) | 193f (7.72s) | **YES** (`first_frame`) | **YES** (`last_frame`) | Joint Native | 16:9 (`1024x576`, `832x480`) |
| **`eng_h3_audioin_lowvram`** | **24.0** | **$17k + 5$** | 22f (0.92s) | 192f (8.00s) | **YES** (`<Picture 1>`) | NO | **YES** (`<Audio 1>`) | 16:9 (`864x480`, `1024x576`) |
| **`eng_h3_lowvram`** | **24.0** | **$17k + 5$** | 22f (0.92s) | 192f (8.00s) | **YES** (`first_frame`) | **YES** (`last_frame`) | Joint Native | 16:9 (`864x480`) |
| **`eng_wan_ti2v`** *(Legacy)* | **16.0** | **$4k + 1$** | 17f (1.06s) | 81f (5.06s) | **YES** (`first_frame`) | NO | None | 16:9 (`832x480`) |

---

### Multi-Clip Chaining & Still Parameter Rules:

1. **Last-Frame to First-Frame Chaining (`clip[N].last_frame -> clip[N+1].first_frame`)**:
   * For continuous camera/action sequences across multi-clip scenes, OTR extracts the terminal frame of Clip $N$ and feeds it into the `first_frame` input of Clip $N+1$.
   * Supported natively on LTX Video and H3 FL2VA.
2. **Still Parameter Logic & Spatial Bucketing**:
   * All still keyframes must be dimensionally aligned to the engine's latent compression grid (multiples of 32 for H3, multiples of 32 for LTX, multiples of 16 for WAN).
   * For Ref2VA dialogue scenes, `ref_image_size: "max"` ensures full-resolution spatial context is preserved without forced center-cropping or artificial pillarboxing.

---

## 4. Universal Video Motion Prompting Law (LTX, H3, WAN)

Human review across both physical RTX 4060 runs and RTX 5080 campaigns established a critical cross-engine principle:

### The Phenomenon: Architecture-Wide Temporal Damping
Modern video diffusion models (DiT / flow-matching architectures including LTX-Video, MiniMax H3, and WAN) are heavily regularized toward temporal consistency to prevent morphing, warping, and flickering. 
* **The Failure Mode**: When provided with subtle, polite, or purely ambient prompts (e.g., LTX `M0`–`M2`, baseline H3 Mime, or H3 Motion Demo), models choose the lowest-loss temporal path: **freezing the scene into an almost static "live-photo" or photographic still hold**.
* **The Comparative Proof**:
  * *H3 Action Demo (Yesterday)*: High urgency/emergency prompt -> **Strong, dynamic, cinematic motion**.
  * *H3 Motion Demo (Today)*: Gentle camera arc / subtle button press -> **Bland, damped motion**.
  * *LTX Motion Ladder (`M0`–`M2`)*: Ambient holds -> **Near-still frames**; only `M3` (explicit camera push) exhibited real movement.

### Production Prompt Engineering Mandates for OTR:
1. **Ban Static / Damping Adjectives**: Strip words like *"subtle"*, *"gentle"*, *"ambient hold"*, and *"slight movement"* from all production prompt generators.
2. **Mandate Kinetic Verbs**: Prompts must declare high-energy physical actions (*"strides across"*, *"turns abruptly"*, *"jumps up"*, *"slams down"*).
3. **Declare Explicit Camera Trajectories**: Always specify a defined camera motion vector (*"rapid push-in"*, *"tracking pan"*, *"sweeping shallow arc"*).
4. **Enforce Cause-and-Effect Event Staging**: Structure prompts around temporal change (*Initial state → Trigger event → Physical reaction*).

---

## 5. System Invariants & Boot Guardrails

Every ComfyUI runner instance spawned by OTR must enforce these runtime invariants:

1. **Memory Flags**:
   * `--disable-pinned-memory`: Mandatory across all production boot lanes to prevent host-RAM fragmentation.
2. **Blackwell `sm_120` & Torch Invariants**:
   * **SageAttention is strictly disabled (`sage-free`)** for MiniMax H3. SageAttention on `sm_120` produces fatal kernel exceptions and silent audio corruption.
   * **FlashAttention-2 is absent**: Never reference or invoke FA2 packages for Torch 2.10 + CUDA 13.0 on Blackwell.
3. **Frame Contract Alignments**:
   * All H3 duration calculations must enforce the exact $(17k + 5)$ latent frame formula:
     * 90 frames = 3.750s @ 24 fps ($k = 5$)
     * 124 frames = 5.167s @ 24 fps ($k = 7$)
     * 192 frames = 8.000s @ 24 fps ($k = 11$)

---

## 6. OTR Prompt Generator Logic & Pipeline Requirements

The OTR prompt builder module (e.g. `otr/prompts/` or prompt generation pipelines) must implement two mandatory prompt-assembly hooks:

### Hook A: Dialogue Viseme Prompt Builder (`build_dialogue_prompt`)
* **Trigger**: Any scene containing character speech or TTS audio.
* **Input**: Character image reference (`<Picture 1>`), audio reference (`<Audio 1>`), and the screenplay ledger line transcript (`line_transcript`).
* **Logic Requirement**:
  1. Pull the exact dialogue text verbatim from the scene ledger.
  2. Escape internal quotes cleanly.
  3. Format the mandatory viseme prompt:
     ```python
     prompt = (
         f'A medium close shot of <Picture 1> delivering the exact line "{line_transcript}" '
         f'directly to the camera with an expressive tone matching the timing and cadence of <Audio 1>. '
         f'His lips, jaw, and facial expression must stay tightly synchronized to the audio.'
     )
     ```

### Hook B: Kinetic Action Prompt Builder (`build_action_prompt`)
* **Trigger**: Any B-roll, action beat, incident, or 8 GB H3 clip.
* **Logic Requirement**:
  1. Sanitize input prompt by filtering out damping words (*"subtle"*, *"gentle"*, *"ambient hold"*, *"slight"*).
  2. Enforce kinetic verb injection, camera displacement vector, and cause-and-effect staging.

---

## 7. OTR Go-Forward Implementation & Verification Checklist

This tagged checklist serves as the acceptance gate during the OTR implementation sprint:

- [ ] **[OTR-BOOT-01]** Verify `--disable-pinned-memory` is applied to all spawned ComfyUI server instances.
- [ ] **[OTR-BOOT-02]** Verify `sage-free` execution lane on Blackwell `sm_120` for MiniMax H3.
- [ ] **[OTR-LANE-01]** Verify LTX Video 2B distilled integration (`832x480x193f @ 25fps`) achieves < 20s warm render times.
- [ ] **[OTR-LANE-02]** Verify LTX Audio HQ recipe integration (`1024x576x193f`).
- [ ] **[OTR-LANE-03]** Verify HuMo 1.7B clamp-13 boot wrapper stays <= 13.5 GiB peak VRAM.
- [ ] **[OTR-PROMPT-01]** **[TAGGED: PROMPT LOGIC]** Verify the dialogue prompt generator pulls the exact line transcript from the ledger and formats the verbatim quotes + `<Audio 1>` viseme template.
- [ ] **[OTR-PROMPT-02]** **[TAGGED: PROMPT LOGIC]** Verify the action prompt generator strips damping adjectives and enforces kinetic verbs/camera vectors.
- [ ] **[OTR-8GB-01]** Verify H3 8 GB action clip generation passes under 8 GB VRAM on physical 4060 hardware.
- [ ] **[OTR-E2E-01]** Execute single end-to-end episode render acceptance test with full audio/video sync.

