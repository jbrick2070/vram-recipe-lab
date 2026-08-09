# Preflight Checklist

Run this checklist before queuing every clip. It describes checks enforced by
`run_recipe.py` and `run_h3_suite.py`; it is not a manual substitute for them.
Any failed preflight aborts before `POST /prompt`. Post-render gates are called
out separately below.

The lab exists because OTR's original VRAM guard was written but never called,
allowing unchecked renders and allocator-corrupting CUDA OOMs. This runner must
prove ownership, isolation, inputs, identity, and queue state before allocation.

## Before any prompt

1. **Port isolation first** — `LAB_PORT` is pinned in code to literal `8199`.
   Reject any inherited value other than `8199`—especially `8188`—before any
   network request, GPU query, or process action. All ComfyUI requests target
   `127.0.0.1:8199`; port 8188 is never queried or touched.
2. **Windows coordinator and nonce-bound leases** — a standalone run holds the
   OS byte lock on `.coordinator.mutex` for its full GPU lease and creates a
   `.gpu.lock` receipt bound to PID, process creation time, nonce, and role.
   Stale receipts may be reaped only while the coordinator is held, and release
   removes only the still-matching nonce owner. A suite holds the coordinator
   plus matching `.suite.lock` and `.gpu.lock` receipts for its full lifetime.
   A `--suite` runner may re-enter only as the direct child of the live suite
   owner when owner PID/create-time/nonce from its environment match both
   receipts; the child never releases the parent's leases. A child watchdog
   shuts down owned work if that verified parent disappears.
3. **GPU idle and host-RAM tracking** — before booting a new owned server,
   `nvidia-smi` must report less than 3072 MiB allocated VRAM. An already-owned
   healthy lab server does not repeat this desktop-idle test. Record baseline
   VRAM and host RAM immediately before the prompt, then sample both every
   200 ms through execution. The independent render ceiling remains 14.5 GiB.
4. **Owned server and empty queue** — port 8199 must either be down or be served
   by the expected ComfyUI command, output directory, listener PID, and valid
   `.server.pid`. Never adopt or kill an answering unreceipted or mismatched
   server. If down, boot with `boot_lab_server.cmd`, verify the launched process
   tree owns the listener, and replace the bootstrap PID receipt with the actual
   serving PID. After ownership is proved, require no
   `.queue.quarantine.json` and empty `queue_running` and `queue_pending` lists.
   Any discovered work writes the durable quarantine marker and aborts. Recheck
   queue idle under the lease immediately before `POST /prompt`; the runner does
   not clear quarantine automatically.
5. **Recipe, node, model, and topology validity** — parse the recipe; verify
   every class and installed input schema against `/object_info`; enforce link,
   required-input, output-slot, declared topology, and contract-requested
   reachability checks; and require each referenced model in
   `models_manifest.md`. Missing nodes or weights are BLOCKED, never installed or
   downloaded.
6. **Receipt history is append-only** — audit the mutable current alias and all
   `results/<recipe>_runN.json` archives before allocating a run number. Abort on
   malformed/BOM receipts, unexpected archive names, filename/payload or recipe
   mismatches, duplicate numbers, alias rollback, a modern alias without its
   archive, or an occupied target archive. Derive the next run number from all
   preserved evidence, then re-audit before writing.
7. **Affordability** — when the current receipt matches the exact recipe SHA and
   boot lane, refuse an unchanged configuration whose last known run failed a
   VRAM gate. Only an explicitly authorized `--force` run bypasses this
   known-failure guard.
8. **Exact fixtures and ear gate** — discover only literal `LoadImage` and
   `LoadAudio` basenames, capture their bytes, and validate every audio fixture's
   hash-bound probe/volume/description receipt. Upload each fixture with
   `overwrite=true`; require the returned name, empty subfolder, and input type
   to match exactly; then perform a no-cache `/view` readback whose SHA-256 must
   equal the captured bytes. A rename, overwrite, receipt, or readback mismatch
   aborts. Never regenerate a fixture during a run.
9. **Exact live boot lane** — require sage-free argv and bidirectionally verify
   reserve and pinned-memory state. A requested reserve must appear as the exact
   live `--reserve-vram` value, while an unrequested reserve must be absent. A
   no-pinned lane must contain `--disable-pinned-memory`, while every other lane
   must omit it. Record the full argv and lane.
10. **Disk and frozen execution identity** — require at least 5 GiB free. Bind
    the run identity to recipe and runner bytes, fixture and audio-receipt hashes,
    model fingerprints, boot lane and server argv, ComfyUI commit, and verified
    server instance (`serving_pid` plus process creation time). Recompute
    provenance and server identity after rendering; any change invalidates the
    run and prevents a changed server from inheriting warm-cache state.

## Prompt resolution and post-render gates

- If prompt acceptance is uncertain, or an accepted prompt never reaches
  terminal history, stop the owned server to prove no unresolved GPU work
  survives. If process/listener cleanup cannot be proved, atomically write
  `.queue.quarantine.json`; the outer finalizer repeats unresolved-prompt cleanup
  before releasing the coordinator. No later run may queue while quarantined.
- `ffprobe` must prove a nonempty video stream, contract frame count, dimensions,
  and FPS. When a target duration is declared, both container and video-stream
  durations must be within one video frame. If audio is required, its stream
  must be nonempty and its own duration must independently be within one frame.
  Bitrate anomaly remains priority-review metadata, not a gate.
- Write each run receipt by exclusive creation of the immutable
  `results/<recipe>_runN.json` archive, then atomically replace the current alias
  with the same serialized bytes. A suite re-reads every child and proves exact
  archive/current-alias byte parity. Suite receipts likewise use a unique run ID,
  an exclusively created archive, and an atomically replaced current alias.
- `shutdown_lab_server()` returns structured proof including receipt presence,
  PID verification, termination attempt/result, process exit, listener exit,
  receipt removal, and reason. It retains `.server.pid` whenever proof is
  incomplete. The suite records this object, requires `success: true` for a
  machine pass, writes its final failure/pass checkpoint while still holding the
  coordinator, and only then releases its leases.

## Offline validation commands

Use the ComfyUI virtual environment; system Python does not carry the runner's
`psutil` dependency.

    $env:PYTHONDONTWRITEBYTECODE='1'
    & C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe -m unittest discover -s tests -v
    & C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe validate_recipes.py
