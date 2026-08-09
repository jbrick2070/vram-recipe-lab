VERDICT: yes-with-fixes. The plan is well-grounded in the existing codebase (`run_recipe.py`, `run_h3_suite.py`, `validate_recipes.py`), but requires minor specification tightening in P5 (external source preview muxing command/receipt details) and P7/P8 before build locking.

MUST-FIX BEFORE BUILD:
1. [P5] Missing execution details for external source-delivery preview muxing and mux receipt.
   - Defect: P5 mandates creating a source-delivery preview by copying the video stream and externally muxing the original hash-bound source fixture trimmed to 3.88s, preserving a mux receipt and proving video stream SHA-256 is unchanged. However, `run_recipe.py` does not automatically perform external muxing or write mux receipts for LTX audio recipes. Without specifying the exact script/ffmpeg command line and output receipt path, an implementor could omit or inconsistently format the preview mux and receipt.
   - Concrete fix: Add an explicit post-processing step in P5 detailing the ffmpeg command (`ffmpeg -i outputs/<recipe>.mp4 -ss 0 -t 3.88 -i fixtures/<source>.wav -c:v copy -c:a aac outputs/<recipe>_source_preview.mp4`) and writing a JSON receipt `<recipe>_source_preview_receipt.json` containing the input/output elementary video stream SHA-256 hashes to verify video stream immutability.

2. [P7] Baseline reference for sentinel VRAM creep check needs explicit pinning to S0.
   - Defect: P7 specifies failing on ">0.25 GiB rise in candidate repeat or sentinel peak/net/settled median", but does not explicitly state that all sentinel comparisons (S1, S2, S3) use S0 as the reference baseline. In `run_h3_suite.py` (`evaluate_suite` lines 183-195), S1, S2, S3 are each evaluated against S0.
   - Concrete fix: Update P7 text to explicitly state: "All sentinel creep evaluations (S1, S2, S3) compare peak VRAM, net peak VRAM, and post-settle median VRAM against the S0 baseline."

3. [P8] Clarify Mini Mime duration tolerance enforcement mechanism.
   - Defect: P8 states "The generic media gate must enforce the target-duration tolerance when that contract is present." In `run_recipe.py` (`media_artifact_is_valid` line 531), video length is validated via `expected_frames` (90 frames) and `expected_fps` (24 fps), which equates to 3.750s ± 1 frame.
   - Concrete fix: Specify in P8 that duration tolerance enforcement (3.750s target ± 1 frame @ 24 fps) is operationalized through the `contract.frames` (90) and `contract.fps` (24) fields in `recipes/h3_mime_i2v.json` evaluated by `media_artifact_is_valid()`.

SHOULD-FIX:
1. [P2 / P7] Align terminology for suite lease validation.
   - Defect: P2 refers to re-entry using "suite nonce, owner PID/create-time", whereas `run_h3_suite.py` (`SuiteLock`) and `run_recipe.py` (`LockManager` line 574) validate re-entry via `LAB_SUITE_OWNER_PID` environment variable and process existence checks without a separate disk nonce token.
   - Concrete fix: Replace "suite nonce" in P2 with "owner PID environment variable (`LAB_SUITE_OWNER_PID`) and `.suite.lock` owner verification".

2. [P7] Clarify settled VRAM sampling context.
   - Defect: P7 describes sampling settled VRAM after every child, but does not explicitly mention that sampling occurs while the persistent lab server process on port 8199 remains online between child runner invocations.
   - Concrete fix: Clarify in P7 that settled VRAM is measured from the persistent lab server on port 8199 after child process completion and prior to launching the next child.

OPTIONAL / NICE-TO-HAVE:
1. [P4] Add a explicit check to verify that `.server.pid` is cleaned up after non-suite standalone runs if `--shutdown` is specified.

CUT THESE:
1. [P7] "The live lane must prove pinned-memory presence/absence in both directions."
   - Why safe to cut: `suites/h3_best_suite.json` explicitly locks `"disable_pinned_memory": true` in `boot_lane`. Testing both true and false in a single run of the 11-step suite is impossible without restarting/reconfiguring the server mid-suite, which P7 explicitly prohibits ("server-instance changes... aborts").

VERIFY-AT-BUILD checklist:
1. [ASSUMPTION] Lab server is bound strictly to `127.0.0.1:8199` and port 8188 is untouched. Verify via `run_recipe.py:check_server_up_and_ownership`.
2. [ASSUMPTION] SageAttention is disabled/absent in the lab server boot environment. Verify via `boot_lab_server.cmd` and `server.log`.
3. [ASSUMPTION] Audio fixtures (`interstitial_static.wav`, `tts_dialogue.wav`, `music_opening.wav`, `music_closing.wav`) in `fixtures/` match their receipts in `fixtures/audio_receipts/`. Verify via `validate_recipes.py` and `run_recipe.py:validate_audio_fixture_receipt`.
4. [ASSUMPTION] `recipes/h3_mime_i2v.json` prompt omits dialogue/vocal prompts and sets `frames=90`, `fps=24`. Verify via `validate_recipes.py`.
5. [ASSUMPTION] `nvidia-smi` is accessible in system PATH for VRAM polling. Verify via `run_recipe.py:query_gpu_vram_mb()`.
