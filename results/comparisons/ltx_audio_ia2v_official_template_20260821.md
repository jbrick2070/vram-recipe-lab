# LTX 2.3 IA2V official-template qualification — 2026-08-21

## Decision

Retain OTR's current `ltx_audio_in` sampler and decoder settings. The official
template's plain-Euler sampler pair produced a steadier camera but turned the
speaker away and progressively hid the mouth. The official decoder settings
produced no visible improvement in facial detail, texture, seams, or tiles at
matched frames. No OTR code or canonical-workflow change is justified by this
run.

The newer dynamic rank-111 LoRA was not installed and was not downloaded. The
official FP8 transport, prompt enhancer, and reconstructed/generated audio path
were deliberately excluded.

## Frozen inputs and topology

- Still: `fixtures/scene_still.png`
  (`0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596`)
- Audio: `fixtures/ltx_matrix_tts_dialogue_3p88s_gain_minus5db.wav`
  (`22489ae40a15ec181d72503f8e238dedf54fa1a803b2d27276b4f32baee5e828`)
- Output contract: 1024x576, 97 frames, 25 fps
- Base canvas: 512x288
- Prompt, seed, sigmas, LoRA, guide-image preparation, weights, topology, and
  source audio were identical across arms.
- The fixture audio was wired directly to `CreateVideo`; no decoded model audio
  node existed in any arm.

Live `/object_info` validation passed for all three 41-node recipes. The only
generative A/B delta was both sampler selectors; the only generative A/C delta
was the tiled-decoder settings.

## Results

| Arm | Single changed variable | Wall time | Absolute peak | Artifact | Visual finding | Verdict |
|---|---|---:|---:|---:|---|---|
| A | exact current OTR control | 193.4 s | 14.745 GiB | 806,965 B | Strong still/identity fidelity and visible mouth articulation; gradual camera push; no visible seams or tiles | Keep |
| B | both stages use plain `euler` | 157.9 s | 15.078 GiB | 449,168 B | Camera is materially steadier, but the speaker turns toward the monitor and hides the mouth; weaker sound-first/lip-sync framing | Reject |
| C | decode `768/64/4096/4` | 164.6 s | 14.609 GiB | 796,390 B | Same lip-visible motion as A; matched full-frame and face crops show no visible detail, texture, seam, or tile improvement | Reject |

All three are valid completed measurements and playable clips, but none is a
formal lab PASS because each exceeded the absolute 14.5 GiB gate. Render cost
did not determine the quality decision.

## Stage-two proof

Each server log showed the complete 8-step base sampler, then
`Requested to load LatentUpsampler`, then the complete 3-step refine sampler,
then `Requested to load VideoVAE`. Each independent receipt reports 1024x576,
97 frames, and 25 fps, proving that decode occurred at full canvas rather than
the 512x288 base canvas.

Recipes and machine receipts:

- `recipes/ltx_audio_ia2v_20260821_a_control_scene_f97.json`
- `recipes/ltx_audio_ia2v_20260821_b_euler_both_scene_f97.json`
- `recipes/ltx_audio_ia2v_20260821_c_decode768_scene_f97.json`
- `results/ltx_audio_ia2v_20260821_a_control_scene_f97.json`
- `results/ltx_audio_ia2v_20260821_b_euler_both_scene_f97.json`
- `results/ltx_audio_ia2v_20260821_c_decode768_scene_f97.json`

Ignored lab-only clips and inspection sheets live under `outputs/`; nothing from
this qualification was written to OTR's episode or OBS trees.
