# Execution Ladder

## 1. Inventory

Run static tests or the inventory-only preflight. It may read local hardware,
files, and Git identity but must not boot ComfyUI, bind a port, acquire a GPU
lease, queue a prompt, install anything, or download anything.

## 2. Admission

Require a ready private profile, current physical model fingerprints, direct
argv, loopback port 18299, empty queue, and the H3 node set. The lane is
Sage-free, Manager-free, reserve-free, and has pinned memory disabled. All
runtime writes stay in `eightgb_bench/local/`.

## 3. Render

Only the lead agent may authorize the H3 MIME campaign. Run one owned server
and one leg at a time: `cold`, `warm-1`, then `warm-2`. Stop after any OOM,
media defect, ownership drift, or failed shutdown proof.

Each enrolled candidate is fixed: MiniMax H3 native-audio I2V, 864x480, 90
frames, 24 fps, 20 steps, seed 42. `h3-mime-i2v-864x480-f90` is the immutable
sentinel. `h3-mime-i2v-motion-demo-f90` and
`h3-mime-i2v-action-demo-f90` are separate fixed prompt-only demos whose
graphs differ from the sentinel only at H3 node 7 prompt text. The latter is a
short nuclear-control-room alarm story, not a baseline replacement. The 5080
result is sentinel orientation only; it is not prompt-matched evidence for
either derived demo.

Never reuse a prior plan's cache warmth, receipt, output, or human review. Each
derived demo requires its own newly admitted cold/warm-1/warm-2 sequence.

## 4. Interpret

- At or below 7.5 GiB VRAM and 28 GiB host RAM: comfortable target.
- A valid run inside measured physical capacity but above either target:
  record `TIGHT_8GB`, disclose peaks, and keep it non-promotable until human
  review.
- OOM, invalid media, or incomplete shutdown: failure, never a fit claim.

Machine success is not a public 8 GB claim. A public result requires all three
hash-bound legs and human visual-and-audio review.

## Git handoff

Require a clean, known branch before remote work. Use `git pull --rebase origin
main` only when it is clean and conflict-free; stop at a conflict. Never use
`reset`, `checkout --`, `clean`, force-push, or a broad stash. Commit only
scoped tracked code or redacted evidence after a staged-file gate and
`git diff --cached --check`.
