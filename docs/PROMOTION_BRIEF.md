# Promotion Brief

Date: 2026-08-08

## Executive verdict

Nothing in this campaign is fully promoted for OTR delivery yet. The corrected
H3 best recipes have useful individual warm-machine evidence, but the canonical
suite remains a formal `MACHINE SUITE FAIL`: T1's absolute peak rose 0.330 GiB
over T0, above the frozen 0.250 GiB creep tolerance. Every H3 artifact also
retains its required human video/audio gate.

| Lane | Machine evidence | Human gate | Promotion state |
|---|---|---|---|
| `h3_t2v_best` | Corrected cold/warm pair passed; 9.14 GiB warm peak | Video and native audio pending | Not promoted; overall suite failed |
| `h3_i2v_best` | Corrected cold/warm pair passed; 9.15 GiB warm peak | Video and native audio pending | Not promoted; overall suite failed |
| `h3_r2v_best` | Corrected flat-V3-socket cold/warm pair passed; 8.42 GiB warm peak | Video pending; native audio is objectively near-silent | Not promoted; overall suite failed |
| LTX four-condition audio matrix | Four valid cold diagnostics and source-delivery previews | Comparative eye/ear review pending in receipts | Experimental evidence only |
| `ltx_t2v_gguf` selected cell B | Best existing candidate, but 15.04 GiB unreserved and attempt limit exhausted | Video pending | Campaign closed without certification |
| `h3_r2v_refaudio_tts_dialogue` | One valid 7.15 GiB cold smoke; native target audio, not source mux | Eye/ear behavior pending | Experimental; static/music cells held |
| `h3_mime_i2v` | One valid 7.28 GiB cold proof; exact 90 frames / 3.750 s | Jeffrey approved one continuation; formal soundscape line pending | Experimental; not warm/promoted |
| `h3_mime_r2v` | One valid 7.23 GiB cold proof; exact 90 frames / 3.750 s | Video and inverted ear gate pending | Final authorized mime render; not warm/promoted |

## H3 best evidence

The newest canonical suite completed all eleven children on one verified
Sage-free, no-pinned, cache-classic, reserve-12 GiB server. Every child passed
its own media, provenance, VRAM, and cache-execution gate. Cold/warm pairs were
deterministic and byte-identical while the sampler/decode/output path executed
fresh on each nonce-bound run.

The durable suite result is nevertheless a failure and must remain one:

- [current suite receipt](../results/h3_best_suite.json)
- [immutable suite archive](../results/h3_best_suite_20260809T005057.839368Z-9aad38bfd43c48da91e9853dc3e409d0.json)
- alias/archive SHA-256:
  `9cedbc3ab06e2ec056defa77fb1be5a679986b25570e2e3855644808f815666f`
- formal residual failure after correcting the confounded net-peak comparison:
  T1 absolute peak rose from 8.81 to 9.14 GiB, or 0.330 GiB, above the 0.250
  GiB tolerance.

Individual warm receipts remain useful machine evidence, not suite promotion:

- [H3 T2V warm receipt](../results/h3_t2v_best_run4.json) and
  [artifact](../outputs/h3_t2v_best_out_00004_.mp4)
- [H3 I2V warm receipt](../results/h3_i2v_best_run4.json) and
  [artifact](../outputs/h3_i2v_best_out_00004_.mp4)
- [corrected H3 R2V warm receipt](../results/h3_r2v_best_run4.json) and
  [artifact](../outputs/h3_r2v_best_out_00004_.mp4)

The R2V evidence before the dotted-socket repair is superseded. Nested
`ref_images`/`ref_audios` objects were ignored by Comfy's V3 input finalizer;
only flat keys such as `ref_images.ref_image_0` are executable sockets. The
corrected R2V warm receipt proves portrait loader node 11 is a reachable cached
ancestor. Do not use older R2V receipts to support reference-conditioning
claims.

## LTX evidence

The four-condition audio matrix is complete exactly once per condition:

- [interstitial/static receipt](../results/ltx_audio_gguf_interstitial_static.json)
- [TTS dialogue receipt](../results/ltx_audio_gguf_tts_dialogue.json)
- [opening music receipt](../results/ltx_audio_gguf_music_opening.json)
- [closing music receipt](../results/ltx_audio_gguf_music_closing.json)

Each diagnostic used the same graph, seed, still, and 3.88-second loudness-
matched derivative. Each corresponding source-delivery preview preserves the
diagnostic video stream and externally muxes the untouched source fixture.
These are one-run causal comparisons, not warm certifications. The receipts
remain human-pending until the motion-character comparison is recorded.

LTX T2V is hard-closed under the three-attempt rule. The selected scheduler-
corrected, officially tiled cell B artifact is
[here](../outputs/ltx_t2v_gguf_b_scheduler_tiled_out_00001_.mp4), but its
15.04 GiB unreserved peak exceeds the 14.5 GiB line and its exact transient
recipe bytes were not preserved. [ESCALATE.md](ESCALATE.md) is the controlling
close-out; no fourth quality or certification render is authorized.

## H3 RefAudio proof

The corrected TTS smoke is a narrow technical success:

- [cold receipt](../results/h3_r2v_refaudio_tts_dialogue.json)
- [artifact](../outputs/h3_r2v_refaudio_tts_dialogue_out_00001_.mp4)
- 124 frames, 864x480, 24 fps, 5.167-second video and AAC audio
- 7.15 GiB peak from a 2.46 GiB baseline; 249.0 seconds
- strong objective portrait-plus-scene conditioning in sampled frames
- generated audio at approximately -21.4 LUFS
- near-zero zero-lag waveform correlation with the input derivative, confirming
  the delivered track is native target audio rather than source mux/copy

One artifact cannot prove that speech character or timing causally follows the
TTS reference. Human eye/ear review remains required, and the static and music
RefAudio cells stay held until that result is judged useful.

## Mini Mime opportunity

[Mini Mime I2V](../outputs/h3_mime_i2v_out_00001_.mp4) fills the documented OTR
default beat exactly: 90 frames at 24 fps, 3.750-second video/audio/container,
no trim, and no external TTS or music. Its [receipt](../results/h3_mime_i2v.json)
records a 7.28 GiB cold peak and a native soundtrack near -27.5 LUFS. Jeffrey
explicitly approved continuing the experiment to one R2V proof; the formal I2V
receipt still awaits his one-line soundscape description.

The resulting [portrait-only R2V mime](../outputs/h3_mime_r2v_out_00001_.mp4)
also lands exactly at 90 frames / 3.750 seconds. Its
[receipt](../results/h3_mime_r2v.json) records a 7.23 GiB cold peak, strong
objective portrait stability, and a very quiet native soundtrack near
-40.5 LUFS. It is the final authorized mime render and remains human-pending.

This is an experimental format opportunity, not an OTR format decision. The
inverted human ear gate must confirm both:

1. no intelligible speech-like or vocal-like content; and
2. coherent diegetic synchronization between action and sound.

The soundscape description must then be attached to each artifact's SHA-256.
No additional mime variant is authorized. The MIME PLAY format decision remains
deferred to OTR-side scoping even if these human gates later pass.

## Audio delivery policy

For ordinary OTR lanes, real TTS and music fixtures remain delivery authority.
Conditioning derivatives and model-native decoded audio are diagnostic unless a
lane-specific human audition explicitly promotes them. Source-delivery previews
must copy the proven video stream and externally mux the hash-bound source
audio. Mini Mime is the deliberate exception under study: model-native audio is
the payload, so its inverted ear gate is mandatory.

## License and scope

MiniMax's written authorization is documented in
[H3_LICENSE_GRANT.md](H3_LICENSE_GRANT.md). It is conditioned on the operator's
request commitments: local, offline, non-commercial radio-drama production on
the operator's own hardware, no hosted service, and no weight redistribution.
This lab evidence is not a blanket commercial, hosting, redistribution, or OTR
format approval.
