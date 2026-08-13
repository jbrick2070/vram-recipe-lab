# RTX 4060: update, check, commit, push, stop

This is one small task. The laptop has an older checkout and no video models.
Its job is to update safely, record its physical hardware, commit that finding,
push it, and stop.

## 1. Make the old checkout clean, without losing its preflight edit

Run these commands from the laptop repository root:

```powershell
git stash push -m "preserve-old-4060-preflight-before-update" -- eightgb_bench/preflight_4060.py
git pull --ff-only origin main
git status --short
```

The stash safely preserves the old `preflight_4060.py` change. Do **not** run
`git stash pop`; the pulled version is the new instruction set. The last
command should print nothing. If it prints anything, or if any of these three
commands fails, stop and return its complete output—do not use `reset`,
`checkout`, `clean`, or force push.

## 2. Create the laptop's one finding

Use the already-installed Windows Python launcher; do not install Python for
this task:

```powershell
py -3 -B .\eightgb_bench\preflight_4060.py hardware-inventory --write-public-report
```

It reads only `nvidia-smi` and Windows RAM. It does **not** download models,
install packages, boot ComfyUI, open a port, or render. A successful command
creates exactly this redacted finding:

```text
eightgb_bench/reports/physical-rtx4060-8gb-hardware.json
```

If the command fails or does not print `public_report_path`, stop and return
the error. Do not make a profile or fix missing models.

## 3. Commit and push only that finding

```powershell
git status --short
git add -- eightgb_bench/reports/physical-rtx4060-8gb-hardware.json
git diff --cached --check
git diff --cached --name-only
git commit -m "Record physical RTX 4060 hardware inventory"
git push origin main
git log -1 --oneline
```

Before `git add`, `git status --short` must show only the new hardware report.
Before the commit, `git diff --cached --name-only` must show exactly one path:
`eightgb_bench/reports/physical-rtx4060-8gb-hardware.json`. If either command
shows anything else, stop and return the output.

## 4. Stop and report

Return only the pushed commit hash and the redacted report path. The result is
hardware evidence only—not model admission, a ComfyUI authorization, or an
8 GB video-model claim.
