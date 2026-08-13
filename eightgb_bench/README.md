# Physical RTX 4060 / 8 GB bench

This is a deliberately isolated benchmark preparation surface. It is for a
separate checkout on the physical RTX 4060 laptop. It does not change or use
the 5080 runner, receipts, lockfiles, profiles, campaigns, or model manifest.

The first candidate is MiniMax H3 image-to-video with native audio: 864x480,
90 frames, 24 fps, 20 steps. A single 5080 orientation receipt used 7.28 GiB
VRAM and 27.56 GiB host RAM; that makes it worth trying on the physical laptop,
but it is not a 4060 result.

## First laptop action: one straight path

Follow [RTX4060_8GB_NEXT_ACTION.md](../docs/RTX4060_8GB_NEXT_ACTION.md)
exactly. It makes an old checkout clean without discarding its local preflight
edit, then creates and commits one redacted hardware finding. This does not
require ComfyUI, a model, or a local profile.

## Later, only after a new written instruction

Do not create a profile or run the following commands today. They describe the
later inventory phase, after the hardware report has been reviewed and lawful
local assets exist on the laptop.

Copy `profile-template.json` to the ignored local location and replace every
`REPLACE_...` value with a real absolute laptop path:

```powershell
New-Item -ItemType Directory -Force .\eightgb_bench\local | Out-Null
Copy-Item .\eightgb_bench\profile-template.json .\eightgb_bench\local\physical-rtx4060-8gb.profile.json
```

Then run the inventory-only check. It reads local files, Git identity,
`nvidia-smi`, and RAM information. It does not start ComfyUI, open a port,
acquire a GPU lock, or render.

```powershell
& <laptop-Comfy-python.exe> -B .\eightgb_bench\preflight_4060.py static-check
& <laptop-Comfy-python.exe> -B .\eightgb_bench\preflight_4060.py preflight --profile physical-rtx4060-8gb --write-receipt
```

`READY_FOR_HUMAN_BOOT_APPROVAL` only means the laptop is ready for a reviewed
future server-admission step; it is never a render pass. Blank identity hashes
are expected on the first profile run: it reports the observed values, which
must be pinned in the ignored profile before it can become ready. This
inventory deliberately does not accept a model-paths config: a future direct
runner must generate and attest a private one inside `eightgb_bench/local`.

Do not download or install a model to make this check pass. Missing or wrong
files are useful `BLOCKED_*` results. A later physical run requires a cold
leg plus two warm legs below 7.5 GiB VRAM and 28 GiB host RAM, with media and
human review. Until then, do not say the lab has an 8 GB video-model result.
