# Physical RTX 4060 / 8 GB bench

This is a separate physical benchmark lane, not an extension of the 5080 lab.
It uses only `eightgb_bench/local/` in the laptop checkout, its own loopback
port (`127.0.0.1:18299`), direct argv, and independent lock/receipt/output
namespaces. It never imports or calls `run_recipe.py`, `boot_lab_server.cmd`,
the Front Office dispatcher, or top-level results aliases.

The complete controller policy is the tracked
[`rtx-4060-lab` skill](../.claude/skills/rtx-4060-lab/SKILL.md). Read it before
using the laptop bridge or this runner.

## Candidate and evidence standard

The first physical candidate is MiniMax H3 MIME image-to-video with native
audio: 864x480, 90 frames, 24 fps, 20 steps, seed 42. Its 5080 orientation
receipt measured 7.28 GiB VRAM and 27.56 GiB host RAM. That is a reason to
try the laptop, not a laptop result.

Only an immutable receipt from `runner_4060.py` counts as physical evidence.
Screenshots, agent messages, model-download logs, and reserve-vram results do
not. A full result needs cold, warm-1, and warm-2 executions, exact media
contract checks, shutdown proof, and human audio/visual review.

## Fixed safety boundary

- Only profile ID `physical-rtx4060-8gb` and plan
  `h3-mime-i2v-864x480-f90` are accepted.
- The runner starts ComfyUI only with a direct argument list at
  `127.0.0.1:18299`; it never starts a shell command.
- SageAttention, Manager, reserve-vram, pinned memory, inherited CUDA
  selectors, proxy/token environment variables, and unwhitelisted custom
  nodes are rejected.
- The actual server must prove the selected GPU UUID, direct argv, empty queue,
  fourteen required node classes, and all four exact H3 model names before
  admission.
- Before it launches, the runner requires the enrolled GPU to be genuinely
  idle (at most 0.5 GiB already allocated) and at least 8 GiB host RAM free.
  Stop a Qwen or other local GPU worker first; it cannot share this benchmark.
- A cache nonce is used only after source-graph validation and after pinning
  the audited ComfyUI 0.32 cache/runtime sources. Every leg must report an
  `execution_cached` event with no fresh-branch node cached.
- Passing terminal receipts are written only after the owned server has exited,
  released port 18299, and yielded a post-shutdown resource sample. A failed
  shutdown produces only a failure receipt.

## Laptop sequence

The laptop may have local commits that are not on `origin/main`. Preserve
them; do not reset, force-push, or discard them.

1. Read `AGENTS.md` and the `rtx-4060-lab` skill. Check `git status --short`
   and `git log --oneline origin/main..HEAD`.
2. Pull the released runner with `git pull --rebase origin main` only while the
   checkout is clean. Stop and report a conflict rather than choosing a side.
3. Run the offline gates using the exact already-installed ComfyUI Python:

   ```powershell
   & <laptop-Comfy-python.exe> -B .\eightgb_bench\preflight_4060.py static-check
   & <laptop-Comfy-python.exe> -B -m unittest discover -s tests -p test_8gb_preflight.py -v
   & <laptop-Comfy-python.exe> -B -m unittest discover -s tests -p test_8gb_runner.py -v
   ```

4. Build only the ignored local profile and launch config from
   `profile-template.json` and `runner-4060-launch-template.json`. The actual
   ComfyUI root, KJNodes root, Python path, model roots, raw GPU UUID, and file
   hashes stay inside `eightgb_bench/local/`; never commit or paste them into a
   handoff. The profile also pins one already-installed `ffprobe.exe` by
   absolute path and SHA-256; the runner never searches `PATH` and does not
   download or install FFmpeg.
5. Run `preflight --profile physical-rtx4060-8gb --write-receipt`. Blank
   identity hashes deliberately fail closed while showing locally observed
   values. Pin those values in the ignored profile and repeat until the result
   is `READY_FOR_HUMAN_BOOT_APPROVAL`.
6. Run exactly one no-prompt admission:

   ```powershell
   & <laptop-Comfy-python.exe> -B .\eightgb_bench\runner_4060.py admit --profile physical-rtx4060-8gb
   ```

   It either writes local admission/shutdown receipts and exits cleanly, or it
   writes a failure receipt and stops. It does not queue a video prompt.
7. The lead controller reviews the admission receipt before authorizing the
   three-leg render command. Do not issue ad-hoc ComfyUI commands.

## How to describe a result

- **Comfortable target:** every leg is at or below 7.5 GiB VRAM and 28 GiB host
  RAM.
- **TIGHT_8GB:** all three legs complete with valid media and remain inside the
  measured physical GPU capacity and retain at least 4 GiB available host RAM,
  but one or more exceed a comfortable target.
  This is an interesting real-world result, not a recommended configuration.
- **Failure:** OOM, bad media, cache/identity drift, queue/ownership failure,
  or incomplete shutdown. Do not call it an 8 GB fit.

Until all three legs and human review exist, never say that MiniMax H3—or all
8 GB cards—are supported.
