# RTX 4060 / 8 GB physical benchmark handoff

## What we are trying to prove

We want an evidence-backed, modest public statement such as:

> This exact RTX 4060 Laptop GPU with 32 GB system RAM ran this named video
> model at these measured settings.

We are **not** trying to infer that every 8 GB GPU, every laptop, MiniMax H3,
or a Turbo LoRA workflow works from 5080 reserve-vram experiments.

## First candidate and why

Start with **MiniMax H3 MIME I2V**, at 864x480, 90 frames, 24 fps, 20 steps,
and native audio. The closest 5080 orientation receipt used 7.28 GiB VRAM and
27.56 GiB RAM. It is the best candidate that has both a genuine video result
and headroom on paper; it is still only one cold run on a 15.92 GiB machine
with reserve pressure, so it proves nothing about the 4060 yet.

The H3 and Wan receipts are useful orientation only:

- H3 I2V and native-audio tests were measured on the 5080 with reserve pressure
  and show variable host-RAM usage. The newer video-only H3 cold run reached
  33.34 GiB host RAM, so it is a follow-up rather than the first 4060 test.
- The short Wan receipt reached 8.28 GiB VRAM, already above an 8 GiB card.
- LTX Video 2B at the measured 832x480 / 193-frame setting needed 13.05-13.11
  GiB VRAM and up to 38.38 GiB RAM; LTX 2.3 and HuMo also exceeded the 32 GB
  host-RAM or 8 GB VRAM envelope at their recorded settings.

## Set up the laptop safely

1. Use a **separate checkout** of this repository on the 4060. Do not point it
   at the 5080 checkout, its `results/`, outputs, locks, port owner, or model
   manifest.
2. Do not download models or install packages for this campaign. Existing,
   lawful local assets can be inventoried; otherwise the result is blocked.
3. Open a new Codex task on the laptop and give it this instruction:

   ```text
   Read AGENTS.md, BOOT.md, PREFLIGHT.md, and docs/RTX4060_8GB_HANDOFF.md.
   Work only in this laptop checkout. Do not download/install anything, do not
   touch a 5080 or OTR path, and do not boot ComfyUI yet. First follow
   eightgb_bench/README.md and report the inventory receipt verbatim.
   ```

4. Run `hardware-inventory` first, copy the actual laptop GPU UUID into the
   profile template, then copy `eightgb_bench/profile-template.json` to the
   ignored path described in its README and fill only real absolute paths.
   Run `static-check`, then the inventory-only `preflight` command.
5. Pin every observed Python, ComfyUI, config, and model hash in the local
   profile and rerun it. Do not proceed until it says
   `READY_FOR_HUMAN_BOOT_APPROVAL`.

The initial inventory calls only `nvidia-smi`, Git, the declared Python
executable, and filesystem reads. It does not start a server, contact a port,
or allocate a model.

## Future render gate

Only after a separately reviewed direct-argv 4060 runner exists:

1. Admit the exact model and core nodes from an owned, Sage-free,
   no-Manager, no-reserve, no-pinned-memory server on `127.0.0.1:8199`.
2. Run one cold leg, then warm-1 and warm-2 sequentially under the laptop's
   own GPU-UUID-bound lock and its own results/output/log namespaces.
3. Require each passing leg to remain at or below 7.5 GiB peak VRAM and 28 GiB
   peak host RAM, leaving real laptop headroom.
4. Prove the declared video contract and ask for human review. Any OOM,
   timeout, bad media, model drift, server-ownership error, or headroom miss
   stops the ladder.
5. Only then try the 5.17-second H3 video-only cell, followed by the
   8-second H3 native-audio cell if the prior cell remains comfortably inside
   those gates. Each is a fresh laptop experiment, not an extrapolation.

Every future receipt must say
`PHYSICAL_4060_8GB_EXPLORATORY_NOT_5080_CERTIFICATION` until it earns a
separate promotion decision. Do not rewrite historical 5080 evidence.
