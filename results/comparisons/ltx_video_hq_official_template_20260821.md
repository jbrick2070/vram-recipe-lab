# LTX 2.3 silent-video official-template qualification — 2026-08-21

## Decision

Adopt plain `euler` on both stages of OTR's silent `ltx_video` HQ recipe.
Against the exact current control, the official sampler choice materially
reduced the unrequested camera push while preserving the right operator's
turn/reach, the two identities, and full-resolution texture. This is useful for
the silent continuity lane and does not change `ltx_audio_in` or the legacy
single-pass recipe.

Reject the official decoder settings. Decode `768/64/4096/4` lowered measured
VRAM in this cold run but produced no visible improvement over the current
decoder in full frames, native frames, subject crops, texture, seams, or tiles.

The newer dynamic rank-111 LoRA was not installed and was not downloaded. The
official FP8 transport and prompt-enhancer machinery were deliberately excluded.

## Frozen input and topology

- Still: `fixtures/scene_still.png`
  (`0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596`)
- Output contract: silent 1024x576, 97 frames, 25 fps
- Base canvas: 512x288
- Prompt, negative prompt, seed, sigmas, LoRA, guide-image preparation,
  weights, anchors, topology, and output contract were identical across arms.
- No audio or AV node existed in any arm; `CreateVideo` had no audio input.

Live `/object_info` validation passed for every class and input in all three
32-node recipes. The only generative A/B delta was both sampler selectors; the
only generative A/C delta was tiled-decoder `tile_size` and
`temporal_overlap`.

## Results

| Arm | Single changed variable | Wall time | Absolute peak | Artifact | Visual finding | Verdict |
|---|---|---:|---:|---:|---|---|
| A | exact current OTR HQ control | 74.8 s | 14.915 GiB | 928,767 B | Clean identities and turn/reach, but a pronounced unrequested camera push changes the supplied framing | Reject |
| B | both stages use plain `euler` | 56.5 s | 15.071 GiB | 456,206 B | Steadier locked framing; requested turn/reach remains; stable identities and clean native detail; no seams or tiles | Adopt |
| C | decode `768/64/4096/4` | 75.6 s | 14.228 GiB | 930,216 B | Visually indistinguishable from A in full frames, native frames, and subject crops | Reject |

A and B exceeded the lab's absolute 14.5 GiB certification gate, while C
passed it cold. All three are valid completed measurements and playable clips.
Render cost and gate status did not override the visible quality decision.

## Stage-two and delivery proof

Each server run completed the 8-step base sampler, loaded and ran
`LTXVLatentUpsampler`, completed the 3-step refine sampler, then loaded the
video VAE for decode. Each independent receipt reports 1024x576, 97 frames,
25 fps, and `audio_present: false`, proving full-canvas stage-two delivery
rather than a 512x288 base-pass artifact.

Recipes and machine receipts:

- `recipes/ltx_video_hq_20260821_a_control_scene_f97.json`
- `recipes/ltx_video_hq_20260821_b_euler_both_scene_f97.json`
- `recipes/ltx_video_hq_20260821_c_decode768_scene_f97.json`
- `results/ltx_video_hq_20260821_a_control_scene_f97.json`
- `results/ltx_video_hq_20260821_b_euler_both_scene_f97.json`
- `results/ltx_video_hq_20260821_c_decode768_scene_f97.json`

Ignored lab-only clips and inspection sheets live under `outputs/`; nothing
from this qualification was written to OTR's episode or OBS trees.
