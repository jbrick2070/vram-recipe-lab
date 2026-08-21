# CPU-only wrapper for the fail-closed registered video fleet sweep.
# The Python driver owns the explicit 30-engine roster, modality-correct pairs,
# structural sentinels, topology receipts, and aggregate nonzero exit status.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = "C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe"
$lab = Split-Path -Parent $MyInvocation.MyCommand.Path

$env:CUDA_VISIBLE_DEVICES = ""
$env:PYTHONUTF8 = "1"
$env:OTR_TEST_MODE = "1"

& $python (Join-Path $lab "diffomatic_fleet.py") @args
exit $LASTEXITCODE
