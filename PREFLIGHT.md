# Preflight Checklist

Run BEFORE queuing every clip — implemented in code inside run_recipe.py, not
performed by hand. Any failed check aborts the run with a named reason; nothing
gets queued on a failed preflight.

Context: OTR shipped three engines whose VRAM preflight guard
(`assert_frame_affordable`) was written but never called — every coverage-planned
segment renders unchecked, and an in-process CUDA OOM corrupts the allocator
(see research/2026-08-03-PROBLEM-STATEMENT-minimax-h3.md, section 4, F1). This
lab does not repeat that mistake. The preflight is wired in from day one and
run_recipe.py refuses to queue without it.

1. **Lock** — `.gpu.lock` does not exist. Create it; remove on exit, even on error.
2. **GPU idle** — nvidia-smi shows under 1.5 GB already allocated. If something
   else is using the GPU, abort; do not queue behind it.
3. **Server up** — GET /system_stats answers at 127.0.0.1:8188.
4. **Nodes exist** — every `class_type` in the recipe appears in GET /object_info.
   Missing node = BLOCKED, never an install.
5. **Models exist** — every model file the recipe references appears in
   models_manifest.md. Missing model = BLOCKED, never a download.
6. **Widget integrity** — recipe JSON parses; every node's widget count matches
   its widgets_values length.
7. **Affordability estimate** — before the first-ever run of a recipe, estimate
   VRAM from weights size + resolution x frame count and record it in the
   results entry. After a measured run exists, the measured peak replaces the
   estimate and the preflight refuses configurations whose last measured peak
   exceeded 14.5 GB (no re-running known-failing configs unchanged).
8. **Fixtures uploaded** — required fixtures are present on the server (upload
   via API if absent). Never regenerate a fixture.
9. **Boot lane** — for MiniMax H3 recipes only: confirm the server was started
   WITHOUT --use-sage-attention (Sage silently corrupts H3 output; see
   research/MINIMAX_H3_BRIEF.md). Record the boot lane in the results entry.
10. **Disk** — at least 5 GB free on the output drive.
