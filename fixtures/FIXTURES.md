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
| `interstitial_static.wav` | the episode interstitial: radio static/noise with near-zero intelligible speech | non-speech-control condition for audio-conditioned behavior tests |
| `tts_dialogue.wav` | real character TTS dialogue | speech condition and lip-sync input |
| `music_opening.wav` | the frozen episode opening-music excerpt | opening-music condition |
| `music_closing.wav` | the frozen episode closing-music excerpt | closing-music condition |

The audio descriptions above record Jeffrey's ear verdict from the 2026-08-08
driver briefing. They deliberately do not make an unsupported claim about the
presence or absence of vocals in either music fixture.

## Audio Probe and Loudness Facts

Measurements below were made locally with FFmpeg/ffprobe
`8.0.1-full_build-www.gyan.dev`. `volumedetect` values cover the complete
source file. Matrix-window values cover exactly seconds `0.00` through `3.88`;
LUFS is the final integrated summary from `ebur128=peak=true`.

| file | SHA-256 | ffprobe | full-file `volumedetect` | first 3.88 s |
|---|---|---|---|---|
| `interstitial_static.wav` | `182ba04d0dc1b4ff6cb21f1748f6b682c58e67d581971d0d9b83700d7e45bfc1` | PCM f32le, 32,000 Hz, mono, 4.100 s, 524,880 bytes | mean -29.5 dB; max -1.0 dB | mean -29.4 dB; max -1.0 dB; -25.8 LUFS |
| `tts_dialogue.wav` | `30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1` | PCM s16le, 44,100 Hz, mono, 10.000 s, 882,078 bytes | mean -21.8 dB; max -4.8 dB | mean -24.1 dB; max -6.2 dB; -20.7 LUFS |
| `music_opening.wav` | `e3ab5b873ec48d6c99464aa7481bcf86b3c047df5194293664e6f2f3f164541a` | PCM f32le, 32,000 Hz, mono, 12.100 s, 1,548,880 bytes | mean -12.5 dB; max -1.0 dB | mean -12.3 dB; max -1.0 dB; -13.7 LUFS |
| `music_closing.wav` | `449b9964c1d3efea751ecf26310c6240a28f07dad985d9e3093e5a1354625545` | PCM f32le, 32,000 Hz, mono, 8.100 s, 1,036,880 bytes | mean -17.4 dB; max -1.0 dB | mean -16.1 dB; max -1.0 dB; -15.9 LUFS |

The four-condition campaign uses the static control's -25.8 LUFS matrix window
as its no-amplification target. Constant gains measured for the exact window
are `0.0`, `-5.1`, `-12.1`, and `-9.9` dB for static, TTS, opening music, and
closing music respectively. The loudness-matched conditioning derivatives are
separate, hash-frozen fixtures; final delivery still muxes each untouched
source file.

## Audio Ear Gate

Before any audio fixture is referenced by a recipe, its hash-bound receipt in
`fixtures/audio_receipts/` must contain:

- exact fixture name, SHA-256, byte count, probe tool/version, and command;
- codec, sample format/rate, channel count, and duration from `ffprobe`;
- full-file `volumedetect` mean and maximum levels;
- for a conditioned excerpt, its exact start/duration, loudness algorithm,
  input level, applied gain, measured output level, and tolerance;
- a human approval status, reviewer/date, audition scope, content class, and a
  one-line description of what was actually heard.

The file hash and receipt must agree before upload. A filename, ledger role, or
generation prompt is not an ear verdict. Missing, stale, or unapproved receipt
means the fixture cannot be used.

## Derived Continuation Fixtures

These PNGs are deterministic frame extractions from recorded lab artifacts, not
new source-generation fixtures. They exist only to reproduce the H3 multi-clip
continuation experiment.

| file | derived from | SHA-256 | use it for |
|---|---|---|---|
| `h3_clip1_last.png` | final encoded frame of `h3_i2v_low_official_sampler_out_00002_.mp4` | `fcf0c3840f2ab54bdfcbf09649c1320cd159e54d6f53c0f7d3306c36d70dd3d7` | clip 1 -> clip 2 handoff |
| `h3_clip2_last.png` | final encoded frame of `h3_i2v_continuation_clip2_out_00001_.mp4` | `3fdc668234db997699d533c150125bce4b5837ed6f2e22c761a1de5edc381544` | clip 2 -> clip 3 handoff |

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
