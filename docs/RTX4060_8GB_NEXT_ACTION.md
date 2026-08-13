# RTX 4060 next action: write, commit, push, stop

The laptop has no approved video-model assets. Its only job now is to make a
redacted, commit-ready proof of the physical hardware. It must **write the
report, commit it, and push it**; a chat summary alone is not the deliverable.

## Execute exactly this

From the separate laptop checkout:

```powershell
git pull --ff-only origin main
& <any-already-installed-python.exe> -B .\eightgb_bench\preflight_4060.py hardware-inventory --write-receipt --write-public-report
git status --short
git add -- eightgb_bench/reports/physical-rtx4060-8gb-hardware.json
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 1 -or $staged[0] -ne 'eightgb_bench/reports/physical-rtx4060-8gb-hardware.json') { throw "Refusing to commit anything except the one redacted 4060 hardware report." }
git diff --cached --check
git commit -m "Record physical RTX 4060 hardware inventory"
git push origin main
git log -1 --oneline
```

Use only an already-installed Python. Do not install Python for this task.
The inventory command writes a raw, timestamped receipt under the ignored
`eightgb_bench/local/` directory and writes one redacted report under
`eightgb_bench/reports/`. The raw GPU UUID and any stable GPU identifier must
remain local; the tracked report binds only the opaque SHA-256 of that local
receipt.

## Commit gate

Commit and push only if the command succeeds and prints both
`"status": "HARDWARE_OBSERVED_NOT_ENROLLED"` and `public_report_path`.
The report creator also requires exactly one `NVIDIA GeForce RTX 4060 Laptop
GPU`, 7,800 through 8,192 MiB total VRAM, and at least 30 GiB physical host
RAM. If it exits nonzero or produces no `public_report_path`, do not stage or
commit anything: return the exact error instead.

## Stop condition

After the push, report the commit hash, the report path, and the reported GPU
and RAM values, then stop. Do not download or install anything, boot ComfyUI,
open port 8199, transfer model files, create a profile, run `preflight`, or
render. The committed report is hardware proof only, not a model admission or
render authorization.
