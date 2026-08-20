# What to run on 8 GB while you wait for LTX 2.5

**Companion to [the 16 GB LTX 2.5 findings](LTX_2_5_FINDINGS_REPORT.md). Same lab, same receipts,
different card.**

LTX 2.5 peaks at **15.47–15.60 GiB** across sixteen measured cells, and that floor did not move for
steps, guidance, quantization, or mode. On an 8 GB card that is not a close call. So this is the
other half of the question: with 8 GB today, what does the evidence actually support?

The short answer is **MiniMax H3**, and the reason is not the one most people expect.

---

## The gate nobody quotes

Every lane below fits inside 8 GB of video memory. Watch the second column.

| Lane | Peak VRAM | Peak host RAM | Wall clock | Canvas / frames |
|---|---:|---:|---:|---|
| `ltx_audio_hq_h1_1024x576` | 7.06 GiB | **44.98 GB** | 248.5 s | 1024x576 / 97 |
| `ltx_i2v_gguf` | 7.17 GiB | **43.32 GB** | 268.0 s | 832x480 / 97 |
| `ltx_audio_hq_h3_1024x576_193f` | 7.36 GiB | **34.19 GB** | 585.3 s | 1024x576 / 193 |
| `ltx_audio_gguf_music_opening` | 7.73 GiB | **49.58 GB** | 185.3 s | 832x480 / 97 |
| `ltx_audio_gguf_tts_dialogue` | 7.82 GiB | **50.11 GB** | 181.3 s | 832x480 / 97 |
| `ltx_audio_gguf_music_closing` | 7.89 GiB | **50.37 GB** | 189.3 s | 832x480 / 97 |
| `ltx_audio_hq_h2_193f` | 7.93 GiB | **45.54 GB** | 341.3 s | 832x480 / 193 |
| — MiniMax H3 lanes, for contrast | 6.05–7.93 GiB | **23.1–30.0 GB** | 179–897 s | 832x480 – 1344x768 |

**LTX 2.3 in GGUF form fits the card and misses the machine.** Those lanes pulled 34 to 50 GB of
system RAM. A typical 8 GB laptop ships with 32 GB, and "7.36 GiB of VRAM" says nothing about that.
If you take one thing from this page: on low-VRAM video work, check host RAM before you check the
GPU. It is the gate that will actually stop you, and almost nobody publishes it.

The H3 lanes are the exception — same VRAM class, 23 to 30 GB of host RAM, comfortably inside a
32 GB machine.

---

## What actually ran on 8 GB hardware

Everything in the table above was measured on the 16 GB bench under reserve pressure. That is
orientation, not proof: the lab's own rule is that only a receipt from the isolated 8 GB runner
counts as physical evidence.

Two H3 engines have that physical evidence, on an RTX 4060 Laptop (8,188 MiB) with 32 GB of system
RAM:

| Engine | Peak VRAM | Peak host RAM | Warm wall clock | Canvas |
|---|---:|---:|---:|---|
| `h3_lowvram` — image-to-video, native sound | **7.21 GiB** | **18.91 GB** | ~410 s / 90 frames, 20 steps | 864x480 @ 24 fps |
| `h3_audioin_lowvram` — audio-conditioned dialogue | **7.00–7.12 GiB** | **18.40 GB** | ~666 s / 124 frames, 20 steps | 864x480 @ 24 fps |

Model stack: MiniMax H3 FL2VA / Ref2VA pruned INT8 ConvRot, Qwen3-VL 32B NVFP4 AWQ text encoder,
FP16 video VAE and FP32 audio VAE. Frame contract is `17k + 5` — 90 frames is 3.75 s, 124 frames is
5.17 s, 192 frames is 8.00 s.

Those 18–19 GB host-RAM figures are the tell that these are genuinely a different machine's
measurements: every 16 GB-bench run in this repository sits at 23 GB or above.

The per-run receipts for those live in the 8 GB runner's local, gitignored evidence store by
design; the committed public artifact is the redacted hardware inventory at
[`eightgb_bench/reports/physical-rtx4060-8gb-hardware.json`](../eightgb_bench/reports/physical-rtx4060-8gb-hardware.json).
Engine-level figures are recorded in
[the OTR engine proposal](2026-08-14-PROPOSAL-otr-video-engine-updates.md).

---

## One row to be careful with

The same proposal lists `ltx_audio_hq` at **7.36 GiB (8 GB Card)**. That number is real, but it is
the 16 GB bench's `ltx_audio_hq_h3_1024x576_193f` run — and that run used **34.19 GB of host RAM**,
more than a 32 GB machine has. Read that row as a VRAM measurement awaiting an 8 GB confirmation,
not as a cleared 8 GB lane.

---

## Why "someone will quantize it" probably is not the unlock

It is a reasonable hope and the lab's own data argues against it.

The Q3-versus-Q5 A/B on LTX 2.5 changed the peak by **0.05 GiB** — 15.56 against 15.51, on the same
graph at the same steps and guidance. Across every cell, Q3 landed 15.47–15.60 and Q5 landed
15.48–15.57. Quantization moved wall clock by 26% and memory by essentially nothing, because the
floor is set by the weights **plus the decode**, not by the weight format alone.

The distance from 15.47 GiB to under 8 GiB is about 7.5 GiB. That is not a quantization step. What
would plausibly close it is sequential offload or block-swap of the transformer, a genuinely smaller
distilled variant, or a decode path that does not need the joint audio-video tensor resident. If one
of those lands, 8 GB becomes a real question again — and it will need its own measurements, because
none of this generalizes by arithmetic.

*That paragraph is reasoning from measurements, not a measurement. Treat it accordingly.*

---

## So, today

| If you have | Run | Why |
|---|---|---|
| 8 GB VRAM, 32 GB RAM | **MiniMax H3** (`h3_lowvram`, `h3_audioin_lowvram`) | The only lanes with physical 8 GB receipts, and the only ones whose host-RAM draw fits a 32 GB machine |
| 8 GB VRAM, 64 GB RAM | H3, and **LTX 2.3 GGUF is worth testing** | The 2.3 audio lanes measured 7.06–7.93 GiB of VRAM; their 34–50 GB host-RAM draw stops being the blocker |
| 16 GB VRAM | **LTX 2.5** | See [the 16 GB report](LTX_2_5_FINDINGS_REPORT.md) — 77.7 s for 3.88 s of video with its own score |

### One prompting rule that matters more at this size

H3 collapses into static still-holds on passive or ambient prompts. The lab's working template:

```text
[Preserve character identities and room geometry from starting still] +
[Trigger event / alarm / action beat] +
[Character physical reaction and movement] +
[Camera arc / push / pan choreography] +
[Soundtrack SFX directive without dialogue]
```

The same motion-damping shows up on LTX. It is a property of the model class, not of your wording.

---

## How to read any of this

- **Nothing here has been human-reviewed.** Every receipt in this repository carries
  `eyeball: pending` and `promotion_ready: false`. "Works" means it ran, it fit, and it produced a
  complete file.
- **16 GB-bench numbers are orientation for 8 GB, not proof.** Reserve pressure is not hardware
  emulation, and an 8 GB card will offload more, which tends to push host RAM up rather than down.
- **Host RAM deserves the same billing as VRAM.** It is the finding on this page.

| What | Where |
|---|---|
| Recipes and receipts for every lane named here | [`recipes/`](../recipes/), [`results/`](../results/) |
| The 8 GB bench, its rules and its runner | [`eightgb_bench/`](../eightgb_bench/) |
| LTX 2.5 on 16 GB | [`LTX_2_5_ON_16GB.md`](../LTX_2_5_ON_16GB.md), [findings report](LTX_2_5_FINDINGS_REPORT.md) |
| Repository | [github.com/jbrick2070/vram-recipe-lab](https://github.com/jbrick2070/vram-recipe-lab) |

---

*Measured on an RTX 5080 Laptop (16 GB) and an RTX 4060 Laptop (8 GB, 32 GB system RAM).
Repository is MIT licensed; model weights carry their own licences.*
