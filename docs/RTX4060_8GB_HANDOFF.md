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

The current immediate instruction is in
[RTX4060_8GB_NEXT_ACTION.md](RTX4060_8GB_NEXT_ACTION.md). It first pulls the
released isolated runner and runs offline tests, then creates only ignored
laptop-local enrollment files before a no-prompt admission.

1. Use a **separate checkout** of this repository on the 4060. Do not point it
   at the 5080 checkout, its `results/`, outputs, locks, port owner, or model
   manifest.
2. Do not download models or install packages for this campaign. Existing,
   lawful local assets can be inventoried; otherwise the result is blocked.
3. Open a new Codex task on the laptop and give it this instruction:

   ```text
   Read AGENTS.md and .claude/skills/rtx-4060-lab/SKILL.md first. Work only in
   this laptop checkout. Do not download/install anything, do not touch a 5080
   or OTR path, and never use port 8199. Follow
   docs/RTX4060_8GB_NEXT_ACTION.md exactly. Stop on a Git conflict, profile
   drift, model/node mismatch, foreign listener, lock, or failed shutdown.
   ```

4. The profile and launch configuration are laptop-private ignored files. The
   specified `preflight` may read and hash local assets; it does not boot a
   server or allocate a model. The subsequent `admit` command may boot only the
   isolated loopback server and must shut it down without queuing a prompt.

`hardware-inventory` only reads `nvidia-smi` and Windows RAM state. The
profile preflight reads local paths, the executing Python, and ComfyUI Git only
after hardware identity passes. The isolated admission owns only port 18299,
proves the direct argv and live model/node surface, and records shutdown proof.

## Future render gate

Only after a separately reviewed direct-argv 4060 runner exists:

1. Admit the exact model and core nodes from an owned, Sage-free,
   no-Manager, no-reserve, no-pinned-memory server on `127.0.0.1:18299`.
2. Run one cold leg, then warm-1 and warm-2 sequentially under the laptop's
   own GPU-UUID-bound lock and its own results/output/log namespaces.
3. Treat 7.5 GiB peak VRAM and 28 GiB peak host RAM as the comfortable target.
   A valid run within real measured capacity but above either target is
   `TIGHT_8GB`, not a recommended configuration, and must disclose its peaks.
4. Prove the declared video contract and ask for human review. Any OOM,
   timeout, bad media, model drift, server-ownership error, or headroom miss
   stops the ladder.
5. Only then try the 5.17-second H3 video-only cell, followed by the
   8-second H3 native-audio cell if the prior cell remains comfortably inside
   those gates. Each is a fresh laptop experiment, not an extrapolation.

Every future receipt must say
`PHYSICAL_4060_8GB_EXPLORATORY_NOT_5080_CERTIFICATION` until it earns a
separate promotion decision. Do not rewrite historical 5080 evidence.
