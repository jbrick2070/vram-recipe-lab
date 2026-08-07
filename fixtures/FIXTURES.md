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
