# MiniMax H3 VRAM & Host RAM Budget Analysis

## Hardware & Operating System Invariants
- **GPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB VRAM, 14.5 GB / 14,848 MiB Hard Gate Ceiling)
- **Host System RAM**: 63.4 GB total RAM
- **Platform**: Windows 11, PyTorch 2.10.0+cu130, CUDA 13.0, SageAttention (disabled on H3 stock boot lane)
- **Boot Lane**: `lab-8199, sage-free` <!-- Grounding Citation: ComfyUI Issue #15263 confirms --use-sage-attention causes silent QK noise corruption on H3 DiT -->
- **Windows Portable Launch Command**:
  ```powershell
  .\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --reserve-vram 2 --fast-disk --preview-method none
  ```

---

## Model Weight Footprint & Total Stack Size

| Component | Model Checkpoint File | Weight Size (GiB) | Offload & Residency Strategy |
|---|---|---|---|
| **DiT Backbone (T2V/I2V)** | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 20.97 GiB | **Layerwise Offload**. Swaps 32 transformer blocks into host system RAM (~268 GB NVMe read traffic). |
| **DiT Backbone (R2V)** | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 20.97 GiB | Replaces FL2VA backbone for multimodal reference conditioning. |
| **Text Encoder** | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15.69 GiB | **Encode-Then-Unload**. Purged from VRAM before DiT sampling initialization. |
| **Video VAE** | `minimax_h3_video_vae_fp16.safetensors` | 5.21 GiB | Tiled temporal & spatial video decode. Loaded during VAE decode. |
| **Audio VAE** | `minimax_h3_audio_vae_fp32.safetensors` | 0.61 GiB | Audio latent decode. Resident during audio synthesis phase. |
| **Total Active Stack** | FL2VA + Qwen3-VL + Video VAE + Audio VAE | **42.48 GiB (~45.6 GB)** | Fits in 63.4 GB system RAM with >18 GB OS headroom. |

---

## Multi-Lane Preset Matrix & Telemetry

### 1. `MMH3_HQ_480P_GATE145` (Certified Production Target)
- **Resolution**: **864×480**
- **Length**: **124 frames** (5.17s @ 24 fps, `17k+5` grid k=7)
- **Steps**: 20 steps
- **Measured VRAM Peak**: **7.4 – 7.6 GB** (Controlled 8GB physical GPU test, [`Tomiigo/minimax-h3-16gb`](https://github.com/Tomiigo/minimax-h3-16gb))
- **Measured Host RAM**: ~10 GB
- **Wall Clock**: ~180 seconds
- **Gate Verdict**: **PASS** (Safely under 14.5 GB / 14,848 MiB gate ceiling).

### 2. `MMH3_HQ_NATIVE_EXPERIMENTAL` (Experimental Native Lane)
- **Resolution**: **1344×768**
- **Length**: **124 frames** (5.17s @ 24 fps)
- **Steps**: 20 steps
- **Measured VRAM Peak**: **14.6 – 15.3 GB** (Actual RTX 5080 16GB test, [`note.com/tnsor_works`](https://note.com/tnsor_works/n/n5405bf0154d9))
- **Measured Host RAM**: ~30 GB
- **Wall Clock**: ~525 seconds
- **Gate Verdict**: **EXPERIMENTAL** (Exceeds 14.5 GB / 14,848 MiB gate ceiling). Produce native resolution via 864x480 generation + separate LTX 2.3 ×2 upscale pass after unloading H3.

### 3. `MMH3_Q3Q2_6GB_PREVIEW` (Portable Preview Lane)
- **Model Stack**: GGUF Q3 DiT (`MiniMax-H3-FL2VA-Q3_K_M.gguf`, 15.58 GB) + Q2 Qwen3-VL (`qwen3vl-32B-MiniMax-H3-Q2_K.gguf`, 8.49 GB)
- **Resolution**: 864×480 / 960×544
- **Length**: 124 frames, 20 steps
- **Measured VRAM Peak**: Unmeasured (runs on 6GB RTX 3060 card)
- **Gate Verdict**: **Portable Preview Lane** (low motion fidelity and character consistency).
