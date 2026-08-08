# Frozen Fixtures

Pre-baked inputs from a real OTR episode
(`signal_lost_signal_lost_20260510_140841`, rendered 2026-05-10). These are
FROZEN — never regenerate, never replace, never edit. Every recipe run uses
these same inputs so VRAM and quality comparisons are apples-to-apples across
runs, models, and settings changes.

| file | what it is | use it for |
|---|---|---|
| `ledger.json` | a complete episode ledger | reference for real beat shapes/timings; NOT re-run through story gen |
| `scene_still.png` | a rendered scene still (radio bookend) | image-in for i2v / audio-conditioned video recipes |
| `portrait.png` | a character portrait | face/reference-image recipes (HuMo-shaped, H3 ref lanes) |
| `narration.wav` | a short narration interstitial | audio-in for audio-conditioned video recipes |
| `music_opening.wav` | the frozen opening-music excerpt from the same source episode | music control for audio-conditioned behavior tests |

## Derived Continuation Fixtures

These PNGs are deterministic frame extractions from recorded lab artifacts, not
new source-generation fixtures. They exist only to reproduce the H3 multi-clip
continuation experiment.

| file | derived from | SHA-256 | use it for |
|---|---|---|---|
| `h3_clip1_last.png` | final encoded frame of `h3_i2v_low_official_sampler_out_00002_.mp4` | `fcf0c3840f2ab54bdfcbf09649c1320cd159e54d6f53c0f7d3306c36d70dd3d7` | clip 1 -> clip 2 handoff |
| `h3_clip2_last.png` | final encoded frame of `h3_i2v_continuation_clip2_out_00001_.mp4` | `3fdc668234db997699d533c150125bce4b5837ed6f2e22c761a1de5edc381544` | clip 2 -> clip 3 handoff |

`music_opening.wav` is frozen source material with SHA-256
`e3ab5b873ec48d6c99464aa7481bcf86b3c047df5194293664e6f2f3f164541a`.

## Rules

- Recipes must NOT include story generation, ledger writing, TTS, or still
  generation. The whole point of the lab is testing the terminal render stage
  in isolation: still + audio IN, video OUT, in seconds of setup.
- `run_recipe.py` must upload the needed fixtures to ComfyUI via
  `POST /upload/image` (images) before queuing, so LoadImage nodes can
  reference them by filename. Audio likewise via the appropriate upload route.
- Clip lengths in recipes should mirror real beat lengths from `ledger.json`
  (or the documented beat ladder: 3.75 s default up to ~15-20 s), not arbitrary
  round numbers — relevance to the OTR pipeline is the goal.
- Audio-conditioned production recipes may use a fixture to condition motion,
  but VAE-reconstructed audio is not authoritative. Preserve and externally
  mux the untouched TTS/music source track for final delivery.
- H3 joint-latent audio is a diagnostic stem. It may be mixed quietly beneath
  the real sources only after a human audition confirms it contains useful
  ambience/SFX and no unwanted speech-like or vocal-like material.
- For continuation chains, extract the exact final encoded frame, record its
  source artifact and SHA-256, feed it to the next I2V graph, and remove the
  duplicated first frame from every later clip during assembly.
