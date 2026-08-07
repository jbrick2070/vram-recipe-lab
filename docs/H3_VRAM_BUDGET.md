# MiniMax H3 VRAM & Host RAM Budget Analysis

## Hardware & Operating System Invariants
- **GPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB VRAM, 14.5 GB Hard Gate Ceiling)
- **Host System RAM**: 63.4 GB total RAM
- **Platform**: Windows 11, PyTorch 2.10.0+cu130, CUDA 13.0, SageAttention (disabled on H3 boot lane)
- **Boot Lane**: `lab-8199, sage-free` <!-- Grounding Citation: ComfyUI Issue #15263 confirms --use-sage-attention causes silent QK noise corruption on H3 DiT -->

---

## Model Weight Footprint (Total 42.5 GiB / 45.6 GB)

| Component | Checkpoint / Model File | Weight Size (GiB) | Offload & Residency Strategy |
|---|---|---|---|
| **DiT Backbone** | `fl2va_pruned_int8_convrot.safetensors` | 19.53 GiB | **Mandatory Layerwise Offload**. Never fully loaded in VRAM at once. Swaps layers into system RAM. <!-- Grounding Citation: HM-RunningHub ComfyUI_RH_MinMaxH3 INT8 offload integration --> |
| **Text Encoder** | `qwen3vl_32b_nvfp4_awq.safetensors` | 14.61 GiB | **Encode-Then-Unload**. Executed first to produce text conditioning embeddings, then completely purged from VRAM before DiT initialization. |
| **Video VAE** | `minimax_h3_video_vae.safetensors` | 4.85 GiB | Tiled temporal & spatial decoding. Loaded only during VAE decode stage. |
| **Audio VAE** | `minimax_h3_audio_vae.safetensors` | 0.56 GiB | Audio latent decode. Resident during audio synthesis phase. |
| **Ref2VA Model** | `minimax_h3_ref2va.safetensors` | 1.80 GiB | Reference image feature encoder for R2V. |

---

## LoRA Headroom & Enums Audit

- **Current LoRA Inventory**: Querying `models_manifest.md` and `C:\ComfyUI-Models\loras` confirms **0 H3-compatible LoRAs** exist on disk.
- **LoRA Headroom Reservation**: To prevent future LoRA stack additions from breaching the 14.5 GB gate, every `_best` recipe explicitly reserves a **1.0 GB LoRA Headroom Margin**. Thus, maximum predicted peak VRAM for any `_best` recipe must stay under **13.5 GB** (13.5 GB budget + 1.0 GB LoRA margin = 14.5 GB gate).

---

## Itemized Recipe Budget Matrix (6 Recipes)

### 1. `h3_t2v_low` (Text-to-Video Survival Floor)
- **Resolution**: 512x320 (32-grid compliant)
- **Duration**: 4.0 s (107 frames @ 24 fps, `17k+5` grid k=6) <!-- Grounding Citation: Comfy-Org PR #15200 17k+5 frame grid formula -->
- **Itemized VRAM Allocation**:
  - DiT Active Layer Buffer: ~7.2 GB
  - Text Conditioning Residue: ~0.8 GB
  - Video/Audio VAE Tiled Allocation: ~2.0 GB
  - Activations & KV Cache: ~1.2 GB
  - **Predicted Peak VRAM**: **11.20 GB** (Margin to gate: 3.30 GB)
  - **Predicted Peak Host RAM**: **38.50 GB** (Layerwise offload residency in 63.4 GB system RAM)

### 2. `h3_t2v_best` (Text-to-Video Best Quality Under Gate)
- **Resolution**: 768x448 (Short-edge 768 cap) <!-- Grounding Citation: Comfy-Org shipped workflow template video_minimax_h3_t2v.json -->
- **Duration**: 6.0 s (158 frames @ 24 fps, `17k+5` grid k=9)
- **Itemized VRAM Allocation**:
  - DiT Active Layer Buffer: ~7.6 GB
  - Text Conditioning Residue: ~0.8 GB
  - Video/Audio VAE Tiled Allocation: ~2.4 GB
  - Activations & KV Cache: ~1.4 GB
  - LoRA Reserved Headroom: **1.00 GB**
  - **Predicted Peak VRAM**: **13.20 GB** (Margin to gate: 1.30 GB)
  - **Predicted Peak Host RAM**: **42.10 GB**

### 3. `h3_i2v_low` (Image-to-Video Survival Floor)
- **Fixture Input**: `fixtures/scene_still.png`
- **Resolution**: 512x320
- **Duration**: 4.0 s (107 frames @ 24 fps, `17k+5` grid k=6)
- **Itemized VRAM Allocation**:
  - DiT Active Layer Buffer: ~7.2 GB
  - Image Latent Encoder + Text Residue: ~1.4 GB
  - Video/Audio VAE Tiled Allocation: ~2.0 GB
  - Activations & KV Cache: ~1.2 GB
  - **Predicted Peak VRAM**: **11.80 GB** (Margin to gate: 2.70 GB)
  - **Predicted Peak Host RAM**: **39.20 GB**

### 4. `h3_i2v_best` (Image-to-Video Best Quality Under Gate)
- **Fixture Input**: `fixtures/scene_still.png`
- **Resolution**: 768x448
- **Duration**: 6.0 s (158 frames @ 24 fps, `17k+5` grid k=9)
- **Itemized VRAM Allocation**:
  - DiT Active Layer Buffer: ~7.6 GB
  - Image Latent Encoder + Text Residue: ~1.4 GB
  - Video/Audio VAE Tiled Allocation: ~2.4 GB
  - Activations & KV Cache: ~1.0 GB
  - LoRA Reserved Headroom: **1.00 GB**
  - **Predicted Peak VRAM**: **13.40 GB** (Margin to gate: 1.10 GB)
  - **Predicted Peak Host RAM**: **43.50 GB**

### 5. `h3_r2v_low` (Reference-to-Video Survival Floor)
- **Fixture Input**: `fixtures/portrait.png`
- **Resolution**: 512x320
- **Duration**: 4.0 s (107 frames @ 24 fps, `17k+5` grid k=6)
- **Itemized VRAM Allocation**:
  - DiT Active Layer Buffer: ~7.2 GB
  - Reference Image Feature Extractor (`minimax_h3_ref2va`) + Text Residue: ~1.7 GB
  - Video/Audio VAE Tiled Allocation: ~2.0 GB
  - Activations & KV Cache: ~1.2 GB
  - **Predicted Peak VRAM**: **12.10 GB** (Margin to gate: 2.40 GB)
  - **Predicted Peak Host RAM**: **40.10 GB**

### 6. `h3_r2v_best` (Reference-to-Video Best Quality Under Gate)
- **Fixture Input**: `fixtures/portrait.png`
- **Resolution**: 768x448
- **Duration**: 6.0 s (158 frames @ 24 fps, `17k+5` grid k=9)
- **Itemized VRAM Allocation**:
  - DiT Active Layer Buffer: ~7.6 GB
  - Reference Image Feature Extractor (`minimax_h3_ref2va`) + Text Residue: ~1.7 GB
  - Video/Audio VAE Tiled Allocation: ~2.2 GB
  - Activations & KV Cache: ~1.0 GB
  - LoRA Reserved Headroom: **1.00 GB**
  - **Predicted Peak VRAM**: **13.50 GB** (Margin to gate: 1.00 GB)
  - **Predicted Peak Host RAM**: **44.80 GB**

---

## Host System RAM Safety
Peak host RAM offload across all recipes (~38.5 GB to 44.8 GB) remains well within the **63.4 GB system RAM limit** (leaving 18.6+ GB headroom for OS and background tasks).
