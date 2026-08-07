# Video Recipe Attempt Logs & Measured Peak Telemetry

## Summary of Measured Video Recipes

Per laboratory guidelines, video recipes were attempted up to 3 times, measuring honest peak VRAM and Host RAM resource consumption on the RTX 5080 Laptop GPU (16 GB, 14.5 GB gate).

---

### 1. `wan_i2v_14b_low` (Wan 2.2 I2V 14B FP8 512x320)
- **Attempt 1**:
  - **Peak VRAM**: **15.28 GB** (Baseline: 1.66 GB) — **EXCEEDED 14.5 GB GATE**
  - **Peak Host RAM**: **43.24 GB** (Baseline: 21.10 GB)
  - **Wall Clock**: 19.7 s (15 sampling steps executed)
  - **Status**: `FAIL (VRAM 15.28 GB > 14.5 GB)`

### 2. `wan_i2v_14b_high` (Wan 2.2 I2V 14B FP8 768x512)
- **Attempt 1**:
  - **Peak VRAM**: **15.34 GB** (Baseline: 1.19 GB) — **EXCEEDED 14.5 GB GATE**
  - **Peak Host RAM**: **44.41 GB** (Baseline: 20.59 GB)
  - **Wall Clock**: 30.0 s (20 sampling steps executed)
  - **Status**: `FAIL (VRAM 15.34 GB > 14.5 GB)`

### 3. `wan_ti2v_low` (Wan 2.2 TI2V 5B Q5_K_M GGUF 512x320)
- **Attempt 1 (Cold)**: Peak VRAM **13.14 GB**, Wall Clock 16.3 s (`PASS (cold)`)
- **Attempt 2 (Warm)**: Peak VRAM **13.15 GB**, Wall Clock 14.6 s (`PASS`)
- **Verdict**: **`PASS`** (fits under 14.5 GB ceiling line).

### 4. `wan_ti2v_high` (Wan 2.2 TI2V 5B Q5_K_M GGUF 768x512)
- **Attempt 1 (Cold)**: Peak VRAM **12.33 GB**, Wall Clock 20.1 s (`PASS (cold)`)
- **Attempt 2 (Warm)**: Peak VRAM **15.55 GB**, Wall Clock 46.3 s (`FAIL`)
- **Verdict**: **`FAIL`** (warm sampling peak 15.55 GB exceeded 14.5 GB ceiling line).

### 5. `ltx_i2v_low` (LTX Video 2.3 I2V 512x320)
- **Attempt 1**: Peak VRAM **10.84 GB**, Wall Clock 7.5 s
- **Status**: **`ERROR`** (wiring/graph fault: LTXAV embedding shape mismatch).

### 6. `ltx_i2v_high` (LTX Video 2.3 I2V 768x512)
- **Attempt 1**: Peak VRAM **10.51 GB**, Wall Clock 6.1 s
- **Status**: **`ERROR`** (wiring/graph fault: LTXAV embedding shape mismatch).

### 7. `ltx_audio_low` (LTX Audio-Conditioned 512x320)
- **Attempt 1**: Peak VRAM **10.82 GB**, Wall Clock 4.5 s
- **Status**: **`ERROR`** (wiring/graph fault: LTXAV audio connector shape mismatch). Logged in `docs/ESCALATE.md`.

### 8. `ltx_lipsync_low` (HuMo / Lip-Sync 512x512)
- **Status**: `BLOCKED` (missing custom nodes on server).
