# RTX 4060: update, verify, admit, stop

This is the current laptop handoff. It supersedes the older hardware-only
instruction. The laptop may already have two local commits for its hardware
report and Windows text-hash fix; keep them. Do not rerun model downloads,
install packages, touch the 5080/OTR tree, use port 8199, or expose a network
listener.

Read `AGENTS.md` and
[`rtx-4060-lab`](../.claude/skills/rtx-4060-lab/SKILL.md) first.

## 1. Bring the existing checkout forward safely

From the 4060 checkout root, run these exact read-only checks first:

```powershell
git status --short
git log --oneline origin/main..HEAD
git fetch origin main
git log --oneline HEAD..origin/main
```

If the working tree is not clean, or the list of local commits is not known,
stop and report it. Do **not** stash, reset, checkout, clean, force-push, or
discard anything.

When the tree is clean, update it this way:

```powershell
git pull --rebase origin main
```

If Git reports a conflict, stop and return the conflict paths and `git status
--short`. Do not choose “ours” or “theirs” yourself.

## 2. Verify the released runner without starting ComfyUI

Find the already-installed Python that belongs to the laptop’s ComfyUI 0.32
environment. Use that exact executable below; never install Python or use an
arbitrary environment.

```powershell
& <laptop-Comfy-python.exe> -B .\eightgb_bench\preflight_4060.py static-check
& <laptop-Comfy-python.exe> -B -m unittest discover -s tests -p test_8gb_preflight.py -v
& <laptop-Comfy-python.exe> -B -m unittest discover -s tests -p test_8gb_runner.py -v
```

All three must pass before any admission action. If one fails, stop and report
the exact command and output. Do not edit around it without a new instruction.

## 3. Create only private local enrollment files

This step writes **ignored** files under `eightgb_bench/local/`; do not stage
or commit them. Copy these templates:

```powershell
New-Item -ItemType Directory -Force .\eightgb_bench\local | Out-Null
Copy-Item .\eightgb_bench\profile-template.json .\eightgb_bench\local\physical-rtx4060-8gb.profile.json
Copy-Item .\eightgb_bench\runner-4060-launch-template.json .\eightgb_bench\local\runner-4060-launch.json
```

Fill them only with actual local values, all of which remain private:

- The enrolled RTX 4060 Laptop GPU’s UUID and 8,188 MiB identity from the
  local raw inventory receipt.
- The exact Python executable used for the commands above and its hash/version.
- The clean ComfyUI 0.32 root at commit
  `c2bcbecd82ec5ae66594340b395c24ef0217b238`, its `main.py` hash, and the
  same tree’s `custom_nodes/ComfyUI-KJNodes` root.
- The four exact H3 model paths in the existing local model roots, their byte
  counts, and hashes.
- The KJNodes `__init__.py` hash plus its pinned commit
  `b7646ad70a7daa7aeb919ca542274758d26ba2df`.

The templates intentionally begin with blank identities. It is acceptable to
run one inventory-only preflight to learn observed local values:

```powershell
& <laptop-Comfy-python.exe> -B .\eightgb_bench\preflight_4060.py preflight --profile physical-rtx4060-8gb --write-receipt
```

Copy values into the ignored profile locally, then rerun that command until it
returns `READY_FOR_HUMAN_BOOT_APPROVAL`. Do not paste raw UUIDs, absolute paths,
or hashes into chat or Git.

## 4. Perform one controlled no-prompt admission

Only after the profile is ready, run:

```powershell
& <laptop-Comfy-python.exe> -B .\eightgb_bench\runner_4060.py admit --profile physical-rtx4060-8gb
```

This starts an owned Sage-free, Manager-free, reserve-free ComfyUI process on
`127.0.0.1:18299`, checks the live node/model surface, writes local receipts,
and shuts it down. It must not queue a video prompt.

Return only: the status, receipt filenames and hashes, whether shutdown passed,
and any blocker. Do not start the cold/warm render sequence until the lead
controller reviews this admission result.
