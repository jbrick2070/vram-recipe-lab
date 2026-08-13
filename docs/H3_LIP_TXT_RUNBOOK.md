# H3-LIP-TXT Runbook

This is an offline preparation/run-order document. It does not authorize a
render while the GPU is occupied. Every render is a direct `run_recipe.py`
invocation, one at a time; the runner owns the 8199, `.gpu.lock`, fixture,
model, media, and shutdown gates.

## Fixed comparison contract

- Native controls remain `h3_r2v_refaudio_tts_lipsync_exact_seed42` and
  `h3_r2v_refaudio_tts_lipsync_exact_seed43`.
- The only execution-surface difference in each same-seed pair is
  `prompt.7.inputs.prompt`. The SaveVideo prefix remains that seed's native
  control prefix; immutable run receipts, not a graph change, isolate results.
- Both arms retain the full, raw `fixtures/tts_dialogue.wav` conditioning
  input, the portrait, 864x480, 124 frames at 24 fps, `ref_image_size=match`,
  `res_multistep`, `simple`, 20 steps, model pins, graph links, and native
  `VAEDecodeAudio -> CreateVideo` audio delivery.
- No transcript text exists yet. The three phrases in `fixtures/ledger.json`
  are unbound hints, never a source for a candidate prompt.

## 1. Fresh native control and full-file window analysis

After Jeffrey releases the GPU, render a fresh seed-42 native control. Do not
reuse historical `_run1` evidence.

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\run_recipe.py .\recipes\h3_r2v_refaudio_tts_lipsync_exact_seed42.json --shutdown
```

Use the newly created immutable `results/h3_r2v_refaudio_tts_lipsync_exact_seed42_runN.json`
archive and its recorded `output_path` for the analyzer; do not use the mutable
alias or predict an output filename.

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\scratch\h3_lip_txt_window.py analyze `
  --control-receipt .\results\h3_r2v_refaudio_tts_lipsync_exact_seed42_runN.json `
  --control-artifact .\outputs\<output_path_from_that_archive>
```

The analyzer converts both streams to mono 44.1 kHz PCM, hard-trims the native
stem to exactly 227850 samples (124/24 seconds), scans every legal source
start 0..213150, and saves deterministic score artifacts. It requires both a
speech-band waveform correlation and a 20 ms log-RMS-envelope correlation to
agree, with predeclared peak-margin and distributed-voiced-block gates.

If the analysis says `AMBIGUOUS_STOP`, record it and stop the campaign. Do not
write a guessed transcript or generate candidates.

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\scratch\h3_lip_txt_window.py certify `
  --analysis .\fixtures\audio_receipts\tts_dialogue_h3_target_window_analysis.json `
  --stop
```

For `UNAMBIGUOUS_MACHINE`, Jeffrey must confirm the aligned window by ear and
create a literal UTF-8-without-BOM, NFC transcript file with no terminal
newline. Its words, pauses, and ordering must be what he heard; no automated
transcription is used.

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\scratch\h3_lip_txt_window.py certify `
  --analysis .\fixtures\audio_receipts\tts_dialogue_h3_target_window_analysis.json `
  --transcript-file .\scratch\tts_dialogue_h3_verified_transcript.txt `
  --reviewer Jeffrey `
  --reviewed-at 2026-08-12T00:00:00-07:00 `
  --ear-confirmation "Confirmed the recorded interval contains these ordered words and pauses." `
  --confidence 0.95
```

This writes the required append-only receipt:
`fixtures/audio_receipts/tts_dialogue_h3_target_window_transcript.json`.

## 2. Build candidates only after PASS

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\scratch\build_h3_lip_txt_campaign.py
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe .\validate_recipes.py
```

The builder refuses a missing, ambiguous, altered, non-NFC, or hash-drifting
receipt. It writes only the two new transcript-aware recipe JSONs and never
changes a historical recipe or receipt.

## 3. Fresh same-runner A/B legs

The fresh seed-42 control used by the transcript receipt is the native arm for
seed 42. Run the remaining three legs sequentially, each through the runner:

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\run_recipe.py .\recipes\h3_r2v_refaudio_tts_lipsync_transcript_seed42.json --shutdown
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\run_recipe.py .\recipes\h3_r2v_refaudio_tts_lipsync_exact_seed43.json --shutdown
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\run_recipe.py .\recipes\h3_r2v_refaudio_tts_lipsync_transcript_seed43.json --shutdown
```

Use the four fresh immutable archives only: native seed 42, transcript-aware
seed 42, native seed 43, transcript-aware seed 43. The review packager refuses
any runner-bundle, model, server-argv, fixture, or Sage-free-lane mismatch.

## 4. Source-window review package

With those four archive paths, create stream-copy review MOVs. These are
delivery copies, not measurements: their video elementary streams must match
the H3 artifacts, while their lossless PCM listening track is the exact sample
window recorded in the transcript receipt.

```powershell
& C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe `
  .\scratch\package_h3_lip_txt_review.py `
  --native-seed42-receipt .\results\h3_r2v_refaudio_tts_lipsync_exact_seed42_runN.json `
  --transcript-seed42-receipt .\results\h3_r2v_refaudio_tts_lipsync_transcript_seed42_runN.json `
  --native-seed43-receipt .\results\h3_r2v_refaudio_tts_lipsync_exact_seed43_runN.json `
  --transcript-seed43-receipt .\results\h3_r2v_refaudio_tts_lipsync_transcript_seed43_runN.json
```

It writes `results/comparisons/h3_lip_txt_review_package.json` and lossless MOVs under
`outputs/h3_lip_txt_review/`. It intentionally assigns no rating or pass;
Jeffrey decides whether both transcript-aware seeds improve or hold
noninferior.
