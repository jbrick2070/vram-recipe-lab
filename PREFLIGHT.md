# Preflight Checklist

Run BEFORE queuing every clip — implemented in code inside `run_recipe.py`, not performed by hand. Any failed check aborts the run with a named reason; nothing gets queued on a failed preflight.

Context: OTR shipped three engines whose VRAM preflight guard (`assert_frame_affordable`) was written but never called — every coverage-planned segment renders unchecked, and an in-process CUDA OOM corrupts the allocator (see `research/2026-08-03-PROBLEM-STATEMENT-minimax-h3.md`, section 4, F1). This lab does not repeat that mistake. The preflight is wired in from day one and `run_recipe.py` refuses to queue without it.

1. **Lock** — `.gpu.lock` does not exist. Create it atomically (`O_CREAT | O_EXCL`); store PID and timestamp; remove on exit, even on error.
2. **GPU idle** — `nvidia-smi` shows under 1.5 GB already allocated. If something else is using the GPU, abort; do not queue behind it.
3. **Server up / Lab Server Ownership** — `GET /system_stats` answers at `127.0.0.1:8199`.
   - If port 8199 answers BUT no PID receipt (`.server.pid`) exists from this session, abort with reason: `Unrecognized server answering on 8199 without PID receipt` (do NOT adopt or kill it).
   - If port 8199 is down, launch `boot_lab_server.cmd` detached, write `.server.pid`, and health-check `GET http://127.0.0.1:8199/system_stats` every 3s up to 120s. On boot failure, read tail of `server.log` and report real error.
4. **Nodes exist** — every `class_type` in the recipe appears in `GET /object_info` at `127.0.0.1:8199`. Missing node = BLOCKED, never an install.
5. **Models exist** — every model file the recipe references appears in `models_manifest.md`. Missing model = BLOCKED, never a download.
6. **Widget integrity** — recipe JSON parses; every node's widget count matches its `widgets_values` length.
7. **Affordability estimate** — before the first-ever run of a recipe, estimate VRAM from weights size + resolution x frame count and record it in the results entry. After a measured run exists, the measured peak replaces the estimate and the preflight refuses configurations whose last measured peak exceeded 14.5 GB (no re-running known-failing configs unchanged).
8. **Fixtures uploaded** — required fixtures are present on the server (upload via API if absent). Never regenerate a fixture.
9. **Boot lane** — confirm boot lane is `lab-8199, sage-free` (server started without `--use-sage-attention`). Record the boot lane in the results entry.
10. **Disk** — at least 5 GB free on the output drive.
