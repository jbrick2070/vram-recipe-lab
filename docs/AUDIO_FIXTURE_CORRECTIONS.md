# Audio Fixture Truth Corrections

This is an additive correction and supersession ledger. Historical run JSON is
preserved as recorded; this document limits what those receipts and previews
may be cited to prove.

## Canonical Correction

On 2026-08-08 Jeffrey identified by ear that the file formerly named
`fixtures/narration.wav` is the episode interstitial: radio static/noise with
near-zero intelligible speech. It is not a dialogue or narration fixture. The
same bytes now have the truthful name `fixtures/interstitial_static.wav` and
SHA-256:

`182ba04d0dc1b4ff6cb21f1748f6b682c58e67d581971d0d9b83700d7e45bfc1`

The rename does not retroactively change historical receipt identities. It
does invalidate any interpretation that treated those bytes as speech.

## Superseded LTX Interpretations

The following artifacts retain their graph, determinism, timing, VRAM, media,
and visual-quality evidence where those claims do not depend on audio content.
Their speech/narration interpretations are superseded:

| evidence | recorded label | corrected interpretation |
|---|---|---|
| `results/ltx_audio_gguf_run6.json` and `outputs/ltx_audio_gguf_speech_out_00001_.mp4` | speech-conditioning diagnostic | static-interstitial control diagnostic; not speech evidence |
| `results/ltx_audio_gguf_run7.json` | raw music versus speech | raw opening music versus static-interstitial control |
| `results/ltx_audio_gguf_run8.json` | loudness-adjusted music versus speech | loudness-adjusted opening music versus static-interstitial control |
| `results/ltx_audio_gguf_run9.json`, `results/ltx_audio_gguf_run10.json`, and the historical current alias | original narration mux / validated speech diagnostic | original static interstitial mux; deterministic historical static-control pair |
| `outputs/ltx_audio_speech_source_mux.mp4` | speech source mux | static-interstitial source mux |

Consequently, the old comparison may show that opening music and the static
interstitial produced different video, including after the recorded level
adjustment. It does not answer whether speech behaves differently from static
or music, and it cannot support a speech-conditioning-strength claim.

## Superseded H3 Preview Labels

These are preview-label corrections, not changes to the H3 video renders:

| preview | corrected audio content | unaffected evidence |
|---|---|---|
| `outputs/h3_multiclip_1_to_3_otr_mix.mp4` | opening music plus the static interstitial at the clip-2 boundary, not narration | continuation frames, seam measurements, and visual-chain assessment |
| `outputs/h3_r2v_otr_source_mix.mp4` | static interstitial plus music, not dialogue/narration | corrected Ref2VA video evidence |
| `outputs/h3_r2v_otr_source_mix_with_generated_stem_AUDITION_ONLY.mp4` | the same real static/music sources plus the quarantined H3 model stem | corrected Ref2VA video evidence and the requirement to audition the generated stem |

None of these preview files is evidence of dialogue delivery, narration
preservation, lip sync, or speech-responsive motion. They remain historical
artifacts and should not be renamed in place or silently substituted.

## Replacement Evidence Required

The superseded interpretation stays closed until the immutable four-condition
LTX matrix renders `interstitial_static`, `tts_dialogue`, `music_opening`, and
`music_closing` from an identical seed, still, graph, prompt, duration, and
loudness-matched conditioning window. Each clip requires eyeball and ear
review. A single clip is cold experiment evidence, not a warm-cache `PASS`.

The replacement question is: does motion character track audio character? If
the static control and real speech move the same way, verify every conditioning
socket and investigate conditioning strength from the official topology before
changing a quality control.
