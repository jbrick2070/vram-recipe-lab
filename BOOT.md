# Booting the Lab's Own Headless ComfyUI

The lab boots its OWN headless ComfyUI server and never depends on (or touches)
Jeffrey's interactive instance or OTR's headless servers. One command:

    boot_lab_server.cmd

launched detached (e.g. `Start-Process -FilePath .\boot_lab_server.cmd` from
PowerShell, recording the PID for shutdown). The recipe inside is cloned from
OTR's verified headless launcher — do not "improve" it without a reason:

- **Python:** `C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe`
  (the real install's venv — torch 2.10.0 / CUDA 13.0 / sm_120).
- **Entry:** `C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py`.
- **Port:** `8199` (override with env `LAB_PORT`). Chosen to never collide with
  the Desktop app or OTR's headless servers (port 8000 family). ALL lab tools
  talk to `http://127.0.0.1:8199`.
- **`--extra-model-paths-config comfy_model_paths.yaml`** — MANDATORY. Maps
  `C:\ComfyUI-Models\*` model dirs and the Documents `custom_nodes` wrapper
  packs (LTXVideo, KJNodes, VideoHelperSuite, ...). Boot without it and those
  nodes silently vanish from /object_info.
- **`--output-directory ...\vram-recipe-lab\outputs`** — lab renders land in
  the lab, never in the OTR episode tree.
- **`PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`** — MANDATORY. A detached cmd
  inherits the cp1252 console codec and ComfyUI's logger crashes on the first
  emoji it prints (~13 s in, exit 1, "server did not come up").
- **Sage-free by construction:** the boot passes no `--use-sage-attention`.
  This satisfies PREFLIGHT check 9 for MiniMax H3 automatically. If a recipe
  ever needs Sage, that is a per-workflow setting, not a boot flag.

## Health check (before any queue)

Poll `GET http://127.0.0.1:8199/system_stats` every 3 s, up to 120 s. First
200 response = server up. On timeout, read the tail of `server.log` (repo
root, append-mode) and report the actual error — do not just retry.

## Shutdown

Stop the recorded PID (`Stop-Process -Id <pid>`), then confirm the port no
longer answers. Always shut down a server you booted when the session's runs
are done — an idle loaded server holds VRAM that the next preflight's
GPU-idle check (under 1.5 GB) will refuse.

## Rules

- ONE lab server at a time; the `.gpu.lock` discipline applies to booting too.
- Never kill a ComfyUI process the lab did not start (PID receipt or leave it).
- If port 8199 is already answering and no lab PID is recorded, something else
  owns it: abort and report, do not adopt it and do not kill it.
- `outputs/` and `server.log` are runtime artifacts: gitignored, never
  committed, safe to clean between sessions.
