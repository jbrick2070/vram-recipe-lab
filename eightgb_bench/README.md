# Physical RTX 4060 / 8 GB bench

This is a deliberately isolated benchmark preparation surface. It is for a
separate checkout on the physical RTX 4060 laptop. It does not change or use
the 5080 runner, receipts, lockfiles, profiles, campaigns, or model manifest.

The first candidate is MiniMax H3 image-to-video with native audio: 864x480,
90 frames, 24 fps, 20 steps. A single 5080 orientation receipt used 7.28 GiB
VRAM and 27.56 GiB host RAM; that makes it worth trying on the physical laptop,
but it is not a 4060 result.

## First laptop action

First record the actual physical GPU UUID and RAM. This does not require
ComfyUI, a model, or a local profile:

```powershell
& <any-local-python.exe> -B .\eightgb_bench\preflight_4060.py hardware-inventory
```

Copy the UUID for the exact `NVIDIA GeForce RTX 4060 Laptop GPU` row into the
profile below. If it reports a different GPU name, VRAM size, or less than
30 GiB total RAM, stop: it is not the declared test hardware.

Then copy `profile-template.json` to the ignored local location and replace every
`REPLACE_...` value with a real absolute laptop path:

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
must be pinned in the ignored profile before it can become ready.

Do not download or install a model to make this check pass. Missing or wrong
files are useful `BLOCKED_*` results. A later physical run requires a cold
leg plus two warm legs below 7.5 GiB VRAM and 28 GiB host RAM, with media and
human review. Until then, do not say the lab has an 8 GB video-model result.
