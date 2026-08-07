# Video Recipe Attempt Logs & Measured Peak Telemetry

## Summary of Measured Video Recipes

Per laboratory guidelines, video recipes were attempted up to 3 times, measuring honest peak VRAM and Host RAM resource consumption on the RTX 5080 Laptop GPU (16 GB, 14.5 GB gate).

---

### 1. `ltx_i2v_low` (LTX Video 2.3 I2V 512x320)
- **Attempt 1**:
  - **Peak VRAM**: **10.84 GB** (Baseline: 1.75 GB)
  - **Peak Host RAM**: **34.50 GB** (Baseline: 21.79 GB)
  - **Wall Clock**: 7.5 s
  - **Status**: `FAIL (execution error)`
  - **Root Cause**: `LTXAV` cross-attention tensor shape mismatch (`Expected size 4096 but got size 2048`) due to `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` requiring dedicated `ltx-2.3-22b-dev_embeddings_connectors.safetensors` or LTXAV conditioning nodes. Peak VRAM footprint accurately measured at 10.84 GB.

### 2. `ltx_i2v_high` (LTX Video 2.3 I2V 768x512)
- **Attempt 1**:
  - **Peak VRAM**: **10.51 GB** (Baseline: 1.31 GB)
  - **Peak Host RAM**: **34.48 GB** (Baseline: 21.27 GB)
  - **Wall Clock**: 6.1 s
  - **Status**: `FAIL (execution error)`
  - **Root Cause**: Same `LTXAV` embedding shape mismatch during sampling phase.

### 3. `wan_ti2v_low` (Wan 2.2 TI2V 14B FP8 512x320)
- **Attempt 1**:
  - **Peak VRAM**: **15.28 GB** (Baseline: 1.66 GB) — **EXCEEDED 14.5 GB GATE**
  - **Peak Host RAM**: **43.24 GB** (Baseline: 21.10 GB)
  - **Wall Clock**: 19.7 s (15 sampling steps executed)
  - **Status**: `FAIL (VRAM 15.28 GB > 14.5 GB / VAE dimension check)`
  - **Root Cause**: Wan 2.2 14B FP8 video sampling consumes 15.28 GB peak VRAM on 512x320 grid without aggressive block offloading, exceeding the 14.5 GB ceiling line.

### 4. `wan_ti2v_high` (Wan 2.2 TI2V 14B FP8 768x512)
- **Attempt 1**:
  - **Peak VRAM**: **15.34 GB** (Baseline: 1.19 GB) — **EXCEEDED 14.5 GB GATE**
  - **Peak Host RAM**: **44.41 GB** (Baseline: 20.59 GB)
  - **Wall Clock**: 30.0 s (20 sampling steps executed)
  - **Status**: `FAIL (VRAM 15.34 GB > 14.5 GB / VAE dimension check)`
  - **Root Cause**: Exceeded 14.5 GB VRAM ceiling during 768x512 sampling.

### 5. `ltx_audio_low` (LTX Audio-Conditioned 512x320)
- **Attempt 1**:
  - **Peak VRAM**: **10.82 GB** (Baseline: 1.51 GB)
  - **Peak Host RAM**: **35.49 GB** (Baseline: 21.23 GB)
  - **Wall Clock**: 4.5 s
  - **Status**: `FAIL (execution error)`
  - **Root Cause**: Audio VAE connector mismatch in LTXAV model.

### 6. `ltx_lipsync_low` (HuMo / Lip-Sync 512x512)
- **Status**: `BLOCKED`
- **Root Cause**: Missing custom nodes on server (`HuMoLipSyncConditioner` / `ComfyUI_RH_HuMo`).
