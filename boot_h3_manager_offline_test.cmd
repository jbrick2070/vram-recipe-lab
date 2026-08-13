@echo off
rem TEST-ONLY H3 Manager-offline proof lane. The default boot_lab_server.cmd
rem remains byte-for-byte unchanged and Manager-disabled.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HF_HOME=C:\ComfyUI-Models\huggingface
set LAB_PORT=8199

if not "%LAB_MANAGER_OFFLINE_PROBE%"=="1" (
  echo [h3-manager-test-boot] LAB_MANAGER_OFFLINE_PROBE=1 is required
  exit /b 64
)
if not defined LAB_MANAGER_PROBE_LOG (
  echo [h3-manager-test-boot] LAB_MANAGER_PROBE_LOG is required
  exit /b 64
)
if not "%HF_TOKEN%"=="offline-disabled" (
  echo [h3-manager-test-boot] non-secret HF_TOKEN sentinel is required
  exit /b 64
)
if not "%HUGGING_FACE_HUB_TOKEN%"=="offline-disabled" (
  echo [h3-manager-test-boot] non-secret HUGGING_FACE_HUB_TOKEN sentinel is required
  exit /b 64
)
if not "%HF_HUB_OFFLINE%"=="1" (
  echo [h3-manager-test-boot] HF_HUB_OFFLINE=1 is required
  exit /b 64
)
if not "%TRANSFORMERS_OFFLINE%"=="1" (
  echo [h3-manager-test-boot] TRANSFORMERS_OFFLINE=1 is required
  exit /b 64
)
if not "%PIP_NO_INDEX%"=="1" (
  echo [h3-manager-test-boot] PIP_NO_INDEX=1 is required
  exit /b 64
)
if not "%PIP_DISABLE_PIP_VERSION_CHECK%"=="1" (
  echo [h3-manager-test-boot] PIP_DISABLE_PIP_VERSION_CHECK=1 is required
  exit /b 64
)
if not "%UV_OFFLINE%"=="1" (
  echo [h3-manager-test-boot] UV_OFFLINE=1 is required
  exit /b 64
)
if not "%GIT_TERMINAL_PROMPT%"=="0" (
  echo [h3-manager-test-boot] GIT_TERMINAL_PROMPT=0 is required
  exit /b 64
)
if defined HUGGINGFACE_HUB_TOKEN (
  echo [h3-manager-test-boot] alternate HUGGINGFACE_HUB_TOKEN must be scrubbed
  exit /b 64
)
if defined HF_API_TOKEN (
  echo [h3-manager-test-boot] alternate HF_API_TOKEN must be scrubbed
  exit /b 64
)

set EXTRA_ARGS=
if defined LAB_RESERVE_VRAM_GB set EXTRA_ARGS=--reserve-vram %LAB_RESERVE_VRAM_GB%
if defined LAB_DISABLE_PINNED set EXTRA_ARGS=%EXTRA_ARGS% --disable-pinned-memory
if defined LAB_CACHE_CLASSIC set EXTRA_ARGS=%EXTRA_ARGS% --cache-classic

echo [h3-manager-test-boot] headless ComfyUI on port %LAB_PORT% %EXTRA_ARGS%
C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe ^
  C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py ^
  --port %LAB_PORT% --cuda-malloc --user-directory C:\Users\jeffr\Documents\ComfyUI ^
  --output-directory C:\Users\jeffr\Documents\ComfyUI\vram-recipe-lab\outputs ^
  --extra-model-paths-config "%~dp0comfy_model_paths.yaml" ^
  --disable-metadata --disable-all-custom-nodes ^
  --whitelist-custom-nodes ComfyUI-GGUF ComfyUI-KJNodes ComfyUI-Manager %EXTRA_ARGS% ^
  >> "%LAB_MANAGER_PROBE_LOG%" 2>&1
