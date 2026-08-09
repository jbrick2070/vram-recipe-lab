# Session Report - Audio Conditioning, H3 Best, and Mini Mime

Date: 2026-08-08

## Completion status

The authorized machine work for this lab session is complete. The four-cell LTX
audio experiment, LTX T2V close-out, corrected H3 best cold/warm suite, one H3
RefAudio TTS smoke, one Mini Mime I2V proof, and the single user-approved R2V
mime follow-up all have durable receipts and artifacts. No additional mime
variant was rendered.

The session is complete as a truthful lab milestone, not as a blanket promotion:

- the newest H3 suite is a formal `MACHINE SUITE FAIL` on its frozen creep
  tolerance even though all eleven children passed individually;
- all H3 human video/audio gates remain pending unless separately noted by the
  operator;
- the LTX matrix is cold experimental evidence, not warm certification; and
- Mini Mime is stopped after the one approved R2V proof; formal human eye/ear
  fields and soundscape descriptions remain incomplete.

The controlling promotion summary is [PROMOTION_BRIEF.md](PROMOTION_BRIEF.md).

## Work completed

### 1. Audio fixture truth and ear gate

The former `fixtures/narration.wav` was identified by human audition as the
episode's radio-static interstitial, not narration. Its bytes were preserved
under `fixtures/interstitial_static.wav`, and historical speech claims were
superseded rather than rewritten. New real fixtures include `tts_dialogue.wav`
and `music_closing.wav`.

Every conditioning fixture now has a hash-bound audio receipt with ffprobe,
volume/loudness evidence, and a human content description requirement. The LTX
matrix uses deterministic 3.88-second, 32 kHz mono loudness-matched derivatives;
delivery previews separately mux the untouched source fixture.

Evidence:

- [fixture corrections](AUDIO_FIXTURE_CORRECTIONS.md)
- [fixture policy](../fixtures/FIXTURES.md)
- [audio receipts](../fixtures/audio_receipts/)

### 2. Four-condition LTX audio matrix

All four cells ran exactly once on one reserve-12 GiB server identity. Each
produced a valid 97-frame / 3.88-second conditioning diagnostic and a separately
receipted source-delivery preview whose video elementary stream is unchanged.

| Condition | Peak VRAM | Wall time | Diagnostic receipt | Source-delivery preview |
|---|---:|---:|---|---|
| Interstitial/static control | 9.25 GiB | 213.7 s | [receipt](../results/ltx_audio_gguf_interstitial_static.json) | [video](../outputs/ltx_audio_gguf_interstitial_static_SOURCE_DELIVERY.mp4) |
| TTS dialogue | 7.82 GiB | 181.3 s | [receipt](../results/ltx_audio_gguf_tts_dialogue.json) | [video](../outputs/ltx_audio_gguf_tts_dialogue_SOURCE_DELIVERY.mp4) |
| Opening music | 7.73 GiB | 185.3 s | [receipt](../results/ltx_audio_gguf_music_opening.json) | [video](../outputs/ltx_audio_gguf_music_opening_SOURCE_DELIVERY.mp4) |
| Closing music | 7.89 GiB | 189.3 s | [receipt](../results/ltx_audio_gguf_music_closing.json) | [video](../outputs/ltx_audio_gguf_music_closing_SOURCE_DELIVERY.mp4) |

These rows remain `PASS (cold)`, `1/2`, non-promotable, and human-pending. No
rerender is authorized by this experiment. The open human question is whether
motion character changes between static, speech, and the two music excerpts.

### 3. LTX T2V close-out

The three-attempt allowance was already exhausted. Scheduler-latent wiring, not
plain VAE decode, was the material coherence fix; corrected scheduler plus the
official tiled decode is the selected cell B. Its existing artifact peaked at
15.04 GiB unreserved and remains human-pending. No fourth render was run.

- [controlling escalation record](ESCALATE.md)
- [selected cell B artifact](../outputs/ltx_t2v_gguf_b_scheduler_tiled_out_00001_.mp4)

### 4. H3 official-topology and harness repair

The best I2V/R2V recipes were aligned with the frozen official H3 sampler and
native joint video/audio decode topology. The R2V audit then found a silent
Comfy V3 integration defect: nested `ref_images` and `ref_audios` dictionaries
were ignored. Five recipes were regenerated with flat dotted inputs such as
`ref_images.ref_image_0` and `ref_audios.ref_audio_0`; runtime and paper guards
now reject the broken nested form.

The prior R2V artifacts are invalid as reference-conditioning evidence. A
corrected low smoke and the corrected best pair visibly preserve the supplied
portrait, and the warm receipt proves portrait loader node 11 is an executable
cached ancestor.

The runner/suite was also hardened around port 8199 ownership, durable locks,
queue quarantine, immutable archives, recipe/runner/helper hashes, exact
fixture overwrite/readback, per-stream media duration, cache-nonce proof,
suite final-boundary rehashing, and fail-closed cleanup. `--cache-classic` plus
a pinned executor-only RandomNoise cache nonce forces fresh sampler/decode/
output execution without changing seed 42 or official declared sockets.

### 5. Corrected H3 best suite

The canonical sequence `W0,S0,T0,T1,S1,I0,I1,S2,R0,R1,S3` completed on one
verified Sage-free, no-pinned, cache-classic, reserve-12 GiB server. All eleven
children passed their own machine/media/provenance gates, and all candidate warm
legs proved stable loader/conditioning hits with a fresh sampler/output branch.

| Pair | Cold peak | Warm peak | Warm result |
|---|---:|---:|---|
| H3 T2V best | 8.81 GiB | 9.14 GiB | Individual warm machine pass; human pending |
| H3 I2V best | 9.14 GiB | 9.15 GiB | Individual warm machine pass; human pending |
| Corrected H3 R2V best | 9.20 GiB | 8.42 GiB | Individual warm machine pass; human pending |

The suite receipt remains `MACHINE SUITE FAIL`. T1 rose 0.330 GiB over T0,
exceeding the frozen 0.250 GiB absolute-peak creep tolerance. Cross-run
`net_peak_vram_gib` failures were later proven algebraically confounded by
changing pre-run baselines and removed from future comparison logic, while net
peak remains required diagnostic evidence. The immutable receipt was not
rewritten; under the corrected evaluator it still fails on T1's real peak
delta.

- [suite alias](../results/h3_best_suite.json)
- [immutable suite archive](../results/h3_best_suite_20260809T005057.839368Z-9aad38bfd43c48da91e9853dc3e409d0.json)
- receipt SHA-256:
  `9cedbc3ab06e2ec056defa77fb1be5a679986b25570e2e3855644808f815666f`

### 6. H3 RefAudio TTS smoke

One corrected standalone-audio Ref2VA smoke ran; static and music cells were
intentionally held.

- [receipt](../results/h3_r2v_refaudio_tts_dialogue.json)
- [artifact](../outputs/h3_r2v_refaudio_tts_dialogue_out_00001_.mp4)
- cold peak 7.15 GiB from a 2.46 GiB baseline; 249.0 seconds
- 124 unique frames, 864x480, 24 fps; 5.167-second video and AAC audio
- strong technical portrait-plus-scene conditioning
- generated soundtrack approximately -21.4 LUFS
- near-zero zero-lag waveform correlation with the source derivative, proving
  the delivered audio is native target audio rather than source mux/copy

This is a technical viability result, not proof that H3 followed the TTS's
phonemes, timing, or character. Human eye/ear review remains pending.

### 7. Mini Mime I2V and R2V proofs

One Mini Mime I2V clip rendered from `scene_still.png`. Jeffrey then explicitly
approved continuing to one portrait-only R2V proof.

- [receipt](../results/h3_mime_i2v.json)
- [artifact](../outputs/h3_mime_i2v_out_00001_.mp4)
- cold peak 7.28 GiB from a 2.52 GiB baseline; 178.9 seconds
- exact target/rendered/delivered duration: 3.750 seconds
- exact 90 frames at 864x480 and 24 fps; no trim or tail correction
- valid native AAC soundtrack approximately -27.5 LUFS with no clipping

Objective I2V QA found 90 unique frames, no freeze/black event, and a non-silent
native track. Jeffrey's approval authorized the R2V continuation, but the formal
I2V receipt still awaits his one-line soundscape description.

The R2V follow-up is also a valid cold-only proof:

- [receipt](../results/h3_mime_r2v.json)
- [artifact](../outputs/h3_mime_r2v_out_00001_.mp4)
- cold peak 7.23 GiB from a 2.61 GiB baseline; 188.3 seconds
- exact target/rendered/delivered duration: 3.750 seconds
- exact 90 frames at 864x480 and 24 fps
- strong objective portrait stability in representative frames
- valid but very quiet native soundtrack near -40.5 LUFS

R2V human eye/ear review remains pending. No additional mime variant is
authorized, and neither cold-only result is warm-certified or promoted.

## Failures and stops preserved

- The newest H3 suite remains a formal machine failure; individual child passes
  are not presented as suite certification.
- Earlier R2V/reference-audio evidence with nested V3 Autogrow inputs is
  superseded and must not support conditioning claims.
- LTX T2V is hard-closed after three attempts and exceeds the unreserved gate.
- LTX matrix rows are single cold experiments, never warm passes.
- RefAudio static/music variants were not run; Mini Mime stopped after the one
  explicitly approved R2V proof.
- All open human eye/ear gates remain explicit; none were fabricated from
  objective media measurements.

## Review and verification

- The requested driver-aware Kibitz R1-R4 campaign ran with the ComfyUI profile.
  Codex Desktop acted as anchor and sole judge; Antigravity and Claude Code were
  the independent local reviewers where their lanes returned usable output.
  Artifacts are under `kibitz-runs/2026-08-08-vram-lab-final/`.
- Four `codex exec review` attempts were launched during the campaign. Each
  timed out without a usable verdict; none is represented as a successful
  review. The final orphaned reviewer PID was verified by command line and
  terminated without touching the Codex app or lab server.
- A later read-only Antigravity review supplied by Jeffrey returned CLEAN on the
  nonce/cache and corrected-sentinel scope, with two verified P2s subsequently
  addressed (`live_schema_check.py` shutdown verification and `--high-ram`
  classic-cache labeling).
- Final frozen-tree verification: 185/185 offline tests passed; 33/33 recipes
  paper-validated; strict UTF-8/no-BOM and `git diff --check` passed; no lab
  PID, GPU/suite lock, quarantine file, or port-8199 listener remained.
- The local-only commit follows this report; no push is authorized.

## Human review queue

1. Compare the four LTX loudness-matched diagnostics for motion character.
2. Review H3 T2V/I2V/R2V best video and generated audio; note that corrected
   R2V's native track is objectively near-silent.
3. Review the RefAudio TTS smoke for useful reference behavior.
4. Supply the one-line I2V soundscape description and review R2V Mini Mime for
   absence of speech/vocal-like content and diegetic sync.

Pending human review defers promotion and any further mime work, but it does not
invalidate the completed machine evidence above.

## Safety and repository state

Every render used the owned `127.0.0.1:8199` lab lane and shut down its verified
server. No model weights were downloaded. Port 8188 and OTR servers were not
touched. The final commit is local only; no push is authorized.
