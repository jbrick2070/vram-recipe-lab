@echo off
rem Lab headless ComfyUI boot -- cloned from OTR's VERIFIED recipe
rem (_otr_soak_server_launch.cmd, docs/VIDEO_BUILD_HANDOFF.md). See BOOT.md.
rem This boot passes NO --use-sage-attention: lab servers are Sage-free by
rem construction, which is exactly what MiniMax H3 requires.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HF_HOME=C:\ComfyUI-Models\huggingface
if not defined LAB_PORT set LAB_PORT=8199
echo [lab-boot] headless ComfyUI on port %LAB_PORT%
C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe ^
  C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py ^
  --port %LAB_PORT% --cuda-malloc --user-directory C:\Users\jeffr\Documents\ComfyUI ^
  --output-directory C:\Users\jeffr\Documents\ComfyUI\vram-recipe-lab\outputs ^
  --extra-model-paths-config "%~dp0comfy_model_paths.yaml" ^
  --disable-metadata ^
  >> "%~dp0server.log" 2>&1
