# MiniMax H3 Ref2VA external-audio evidence

## Headline conclusion: RefAudio reconstructs; it does not compose

H3's joint-latent RefAudio path largely **reconstructs its conditioning input**
rather than composing a new soundtrack. In the opening-music cell, the first
3.88 seconds of native decoded target audio strongly correlate with the supplied
reference. The original approximately-0.94 finding is confirmed more strongly by a
receipt-bound PCM recheck at 0.969528. The approximately 1.287-second continuation
tail is the only portion outside the reference window and therefore the only portion
unambiguously not within-window reconstruction; correlation alone does not prove that
the aligned window contains no novel detail.
This is not a source-file mux, but it is also not evidence of independent audio
generation. Consequently, audio-conditioned H3 is **not the lab's audio-generator
lane**. Mini Mime must be tested unconditioned: picture in, no `LoadAudio` reference,
and only the model's own sampled audio out.

Status as of 2026-08-09: **the original neutral-prompt TTS and opening-music cells
remain cold evidence; the prompt-only speaking retest now has two cold machine-gated
takes; exact lip sync, seed consistency, and all applicable human ear gates remain
pending**. The static RefAudio control remains unrendered.

This note records why the three `h3_r2v_refaudio_*` recipes are legitimate tests of
MiniMax H3 reference-audio conditioning, what the available examples do and do not
prove, and what must still be demonstrated on this lab rig. No third-party workflow
JSON was copied into the recipes.

## Bottom line

- MiniMax H3 Ref2VA has a real standalone-audio conditioning input. ComfyUI encodes
  every `ref_audios` item with the H3 Audio VAE and places the resulting audio latent
  in the model's `minimax_refs` conditioning payload. This is different from attaching
  an already-existing soundtrack to a finished video.
- The lab's source `LoadAudio` node feeds only
  `MiniMaxH3ReferenceToVideo.ref_audios.ref_audio_0`. The source WAV never feeds
  `CreateVideo.audio`.
- The saved soundtrack comes only from `VAEDecodeAudio`, which decodes the sampled
  target AV latent. It is therefore model-native target audio, not a source-audio mux.
- Official material establishes the socket and prompt semantics, but the official
  ComfyUI R2V template leaves its audio-reference sockets unwired. Community graphs
  corroborate the wiring; they do not establish successful behavior on this rig.
- The TTS-dialogue and opening-music cells each completed as valid cold machine gate
  passes. They used the same seed, images, prompt, graph, duration, and lane; only the
  receipt-bound reference WAV and output identity differ.
- The music cell strongly reconstructs the 3.88-second reference in its native target
  soundtrack (receipt-bound aligned waveform correlation 0.969528 and block-RMS
  envelope correlation 0.964007), while the TTS cell preserves much less of its
  source waveform. This is not a
  direct source mux: both tracks come exclusively from the sampled target latent.
- The original TTS cell leaves lip-sync **untested**: its neutral wide-scene prompt
  defined `<Picture 1>` and `<Audio 1>` but never instructed the subject to speak or
  articulate to the audio. The earlier no-lipsync conclusion is retracted. Music is
  `ok-experimental`, but its visual motion remains a steady camera push rather than
  following the beat. The static control remains unrendered.

## Official semantics

### MiniMax model contract

The [MiniMax H3 model card](https://huggingface.co/MiniMaxAI/MiniMax-H3)
defines H3-Base-Ref2VA as multimodal reference-to-audio-video generation. Its
published input limits are:

- up to 9 reference images;
- up to 3 reference videos, each 2–15 seconds, with at most 15 seconds total;
- up to 3 standalone reference-audio clips, each 2–15 seconds, with at most
  15 seconds total; and
- standalone audio must be accompanied by an image or video rather than being the
  only reference modality.

Each lab WAV is 3.88 seconds and is accompanied by two images, so the proposed cells
fall inside those official Ref2VA constraints. The same model card describes H3 as
jointly predicting video and audio latents and decoding them through separate visual
and audio VAEs. That is the basis for treating sampled `VAEDecodeAudio` output as the
model's target audio.

### ComfyUI socket and ordering contract

The [official ComfyUI H3 guide](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
documents R2V as accepting a mix of image, video, and audio references. It requires
prompt tags to follow connection order and documents limits of 9 images, 3 videos,
and 3 standalone audio clips.

The installed core implementation matches the pinned official
[`MiniMaxH3ReferenceToVideo` source](https://github.com/Comfy-Org/ComfyUI/blob/fe4195f7f4275f2626cbafc703acc3ddde1e5490/comfy_extras/nodes_minimax_h3.py#L154-L280):

- lines 180–195 define `ref_images`, `ref_videos`, `ref_video_audios`, and
  `ref_audios` as autogrow inputs;
- lines 201–208 resample an audio input when necessary and encode it through the
  Audio VAE;
- lines 234–267 pair `ref_video_audio_N` with `ref_video_N` and emit the soundtrack's
  `<Audio N>` presentation item before its `<Video N>` item; and
- lines 269–279 encode standalone `ref_audios` entries and attach all reference
  blocks as model conditioning.

The implementation processes images first, reference videos and any paired
soundtracks next, then standalone audio. With this experiment's two images, no
videos, and one standalone WAV, the exact labels are therefore:

| Connected socket | Prompt label | Lab fixture |
|---|---|---|
| `ref_images.ref_image_0` | `<Picture 1>` | `portrait.png` |
| `ref_images.ref_image_1` | `<Picture 2>` | `scene_still.png` |
| `ref_audios.ref_audio_0` | `<Audio 1>` | cell-specific 3.88 s WAV |

`ref_video_audios` has a narrower meaning: it carries the soundtrack belonging to a
same-index reference video. It is not an alternate name for a standalone audio
reference, and it is intentionally absent from these three cells.

### Reference is not the same as copy

The model-author's
[full-reference prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)
distinguishes `fully_copy`, `partially_copy`, `reference`, and `weak_reference` for
`<Audio N>`. `reference` means that properties such as timbre, rhythm, style,
dialogue content, or sound texture guide generation without directly copying the
signal.

The lab uses the `reference` relationship and the same modality-neutral prompt in all
three cells. The test asks whether changing only the reference waveform changes the
newly generated target audio in the expected direction. It does not ask ComfyUI to
mux the exact WAV or claim bit-for-bit reproduction.

The model-author's
[reproducible Ref2VA request](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/scripts/readme/reproducible-768p-ref2va-request.sh)
also demonstrates independent `<Audio N>` ordering for a reference-video soundtrack
and a later standalone audio reference.

### `CreateVideo.audio` is delivery, not conditioning

The pinned official
[`CreateVideo` implementation](https://github.com/Comfy-Org/ComfyUI/blob/dec5d9450a5290bcf63430409ea41018e67f41c3/comfy_extras/nodes_video.py#L152-L192)
describes its optional audio input as audio to add to the video and constructs a video
from image and audio components. It does not feed audio back into H3 conditioning.
Consequently, a graph that connects source `LoadAudio` directly to
`CreateVideo.audio` can prove muxing, but cannot prove that H3 generated or responded
to that soundtrack.

## What the available workflows prove

### Official ComfyUI template: native AV topology, audio sockets unwired

The lab-frozen
[`video_minimax_h3_r2v.json`](../research/comfy_templates/video_minimax_h3_r2v.json)
is byte-identical to the
[official template at commit `5c75d9f`](https://github.com/Comfy-Org/workflow_templates/blob/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_r2v.json)
and has SHA-256
`099d24eda6263854818975c7209db6f29ebfd0339936c928f12293d5ab029ffb`.

It establishes the official sampler and native target decode shape:

```text
MiniMaxH3ReferenceToVideo.LATENT
  -> SamplerCustomAdvanced
     -> VAEDecode       -> CreateVideo.images
     -> VAEDecodeAudio  -> CreateVideo.audio
```

However, its `ref_video_audios.ref_video_audio_0` and
`ref_audios.ref_audio_0` sockets both have `link: null`, and the template contains no
`LoadAudio`. It is therefore not an executable external-audio example and cannot by
itself demonstrate either standalone or paired audio-reference behavior.

### Sobaya chapters 8 and 9: pure-core standalone-audio topology only

At pinned commit `b27546d`, the unlicensed Seedance_Madogiwa repository contains two
API-format, core-node-only graphs:

- [chapter 8 workflow](https://github.com/sobaya-0141/Seedance_Madogiwa/blob/b27546d848121f2c5f3f687dea00bf4f37523cff/03_SCRIPTS/26_kansha_no_bug_ichimankai/ch8_workflow.json)
- [chapter 9 workflow](https://github.com/sobaya-0141/Seedance_Madogiwa/blob/b27546d848121f2c5f3f687dea00bf4f37523cff/03_SCRIPTS/26_kansha_no_bug_ichimankai/ch9_workflow.json)

Both graphs wire `LoadAudio` node 205 to
`MiniMaxH3ReferenceToVideo.ref_audios.ref_audio_0` on node 136 and refer to the input
as `<Audio 1>`. Both deliver audio through `SamplerCustomAdvanced` node 125,
`VAEDecodeAudio` node 121, then `CreateVideo` node 130. There is no direct source-audio
connection to `CreateVideo` and no custom H3 node in either graph.

This is strong corroboration that a flattened ComfyUI API graph can represent the
standalone-audio socket correctly. It is not successful render evidence. The author's
[CUDA runbook](https://github.com/sobaya-0141/Seedance_Madogiwa/blob/b27546d848121f2c5f3f687dea00bf4f37523cff/03_SCRIPTS/26_kansha_no_bug_ichimankai/RUNBOOK_CUDA.md#L171-L185)
explicitly says no chapter had rendered because H3 could not run on the author's Mac;
only an equivalent five-image/one-audio graph had passed ComfyUI's synchronous prompt
validation.

The repository has no root license or license-like file at that commit. The lab used
these files as topology evidence only. It copied no JSON, prompt, node IDs, or values
from them.

### ComfyTV: MIT paired reference-video soundtrack topology

The MIT-licensed
[ComfyTV H3 R2V workflow](https://github.com/jtydhr88/ComfyTV/blob/4d1f882e4793d3a22d86e6dec60d829ab16e2252/workflows/video/local-minimax-h3-r2v.json)
corroborates the paired-video contract. Each `LoadVideo` is separated by
`GetVideoComponents`; its frames go to `ref_videos.ref_video_N`, while its extracted
audio goes to the same-index `ref_video_audios.ref_video_audio_N`. Its standalone
`ref_audios.ref_audio_0` socket is null.

This supports the official meaning of `ref_video_audios`, but it is not evidence for a
standalone `LoadAudio` cell and does not replace the lab's controlled experiment. The
repository's [MIT license](https://github.com/jtydhr88/ComfyTV/blob/4d1f882e4793d3a22d86e6dec60d829ab16e2252/LICENSE)
is recorded for source-trust clarity; no workflow JSON was copied.

### Rejected evidence: NativeAudioLock and source mux

The
[MiniMax-H3 NativeAudio MusicVideo workflow](https://github.com/Shrek3OnVH5/MiniMax-H3-NativeAudio-MusicVideo-Workflow/blob/11a95f623b98496923714db99da0aecec672cbd4/workflows/MiniMaxH3_NativeAudio_MusicVideo_TEMPLATE.json)
is explicitly rejected as behavioral evidence and as an implementation source.

Its source path is confounded:

```text
LoadAudio 143 -> TrimAudioDuration 144
                  |-> MiniMaxH3ReferenceToVideo.ref_audios.ref_audio_0
                  `-> MiniMaxH3NativeAudioLock 145 -> exact_audio
                                                   -> CreateVideo.audio
```

The custom `MiniMaxH3NativeAudioLock` also modifies the model/AV-latent sampling path.
Because its `exact_audio` output is the soundtrack delivered to `CreateVideo`, hearing
the source audio in the result cannot show that ordinary Ref2VA conditioning generated
or reproduced it. The repository also has no root license at the pinned commit. None
of its JSON or custom-node code was copied, and `MiniMaxH3NativeAudioLock` is forbidden
by the lab recipes' topology contract.

## The lab's original three-cell experiment

The recipes are generated from the current V3 dotted-socket `h3_r2v_best` topology
plus the official contracts above. Its current R0/R1 receipts form a valid individual
warm pair, while the overall H3 suite remains failed on a separate T1 creep gate:

| Cell | Experimental role | Reference WAV | Runtime status |
|---|---|---|---|
| [`h3_r2v_refaudio_static_control`](../recipes/h3_r2v_refaudio_static_control.json) | static/control | `ltx_matrix_interstitial_static_3p88s_gain_0db.wav` | not run |
| [`h3_r2v_refaudio_tts_dialogue`](../recipes/h3_r2v_refaudio_tts_dialogue.json) | speech condition and first smoke | `ltx_matrix_tts_dialogue_3p88s_gain_minus5db.wav` | cold machine gate pass; human review: lip-sync untested because prompt omitted it |
| [`h3_r2v_refaudio_music_opening`](../recipes/h3_r2v_refaudio_music_opening.json) | music condition | `ltx_matrix_music_opening_3p88s_gain_minus12db.wav` | cold machine gate pass; human `ok-experimental` (clean, steady push, no beat response) |

All three WAVs are receipt-bound, 3.88-second, 32 kHz mono fixtures prepared for the
same comparison window. H3 may resample supported inputs to its Audio VAE rate; these
fixtures are already at the expected 32 kHz.

### Frozen independent-variable contract

The three cells share all generation inputs and settings:

- 864×480, 124 frames at 24 fps;
- seed 42;
- `res_multistep` sampler;
- `BasicScheduler`, `simple`, 20 steps, denoise 1.0;
- the same H3 Ref2VA model, text encoder, video VAE, and audio VAE from
  `models_manifest.md`;
- `portrait.png` as flat V3 socket `ref_images.ref_image_0` / `<Picture 1>`;
- `scene_still.png` as flat V3 socket `ref_images.ref_image_1` / `<Picture 2>`;
- exactly one WAV as flat V3 socket `ref_audios.ref_audio_0` / `<Audio 1>`;
- byte-identical, modality-neutral prompt text; and
- the same 17-node graph and all required/absent sockets.

The only permitted pairwise differences are recipe identity, experiment/fixture
metadata, the `LoadAudio` filename, and the `SaveVideo` prefix. In particular, the
prompt does not say "speech" in one cell and "music" in another; the waveform is the
controlled independent variable.

The source and delivery paths are deliberately disjoint:

```text
portrait.png -----> ref_images.ref_image_0 --\
scene_still.png --> ref_images.ref_image_1 ---+-> MiniMaxH3ReferenceToVideo
cell WAV ---------> ref_audios.ref_audio_0 ---/              |
                                                               v
                                                        target AV latent
                                                               |
                                                               v
                                                    SamplerCustomAdvanced
                                                      |               |
                                                      v               v
                                                 VAEDecode      VAEDecodeAudio
                                                      |               |
                                                      `-----> CreateVideo <---'
                                                                  |
                                                               SaveVideo
```

There are no `ref_videos`, `ref_video_audios`, first-frame, or last-frame inputs. The
source `LoadAudio` node's only consumer is `ref_audios.ref_audio_0`.
`CreateVideo.audio` accepts only `VAEDecodeAudio` from the sampled target latent.
The literal API keys are flat dotted V3 socket names; a nested `ref_images` or
`ref_audios` container is rejected because that obsolete encoding can silently drop
an optional `COMFY_AUTOGROW_V3` condition. Current dotted-socket receipts supersede
the older defective nested-socket R2V evidence.

The deterministic
[`build_h3_refaudio_matrix.py`](../scratch/build_h3_refaudio_matrix.py) pins the base
recipe, official template, installed schema, fixture hashes, node set, connections,
absent sockets, prompt, pairwise-difference whitelist, and immutable output bytes.
[`test_h3_refaudio_matrix.py`](../tests/test_h3_refaudio_matrix.py) checks those claims,
including DAG reachability and refusal to overwrite a drifted immutable recipe.

## Proven and unproven scope

Topology and provenance proven before rendering:

- all three JSON recipes parse and pass the repository paper validator;
- the exact node set, links, tag order, dynamic-socket absences, and terminal
  reachability match the contract;
- source audio has only the Ref2VA conditioning consumer;
- delivered audio has only the sampled target-latent decode source;
- referenced models exist in the local manifest;
- fixture and evidence hashes are pinned; and
- the builder is byte-idempotent and the full local unit suite passes.

The TTS and music run-1 receipts and artifacts now additionally prove:

- the installed standalone-audio path executes to completion on the isolated
  `lab-8199, sage-free, no-pinned, reserve-12gb` lane;
- TTS peak/baseline VRAM are 7.15/2.46 GB and music peak/baseline VRAM are
  7.18/2.46 GB; each took 249.0 seconds and remained below the 14.5 GB global gate;
- each output contains 124 encoded frames, 5.166667 seconds of video, and 5.167
  seconds of native generated audio in a 5.167-second container;
- objective image-conditioning checks are strong, establishing that the corrected
  V3 dotted image-reference path is active without substituting for a human verdict;
  and
- the generated TTS target soundtrack is present at -21.4 LUFS, while the generated
  music soundtrack is present at -23.1 LUFS; and
- the music target preserves its matched reference far more strongly than the TTS
  target. The original approximately-0.94 result is confirmed more strongly by a
  reproducible PCM recheck: aligned waveform correlation 0.969528 and block-RMS
  envelope correlation 0.964007. The generated track continues for approximately
  1.287 seconds beyond the 3.88-second reference window, confirming strong
  model-conditioned reconstruction rather than an independent composition.
  [Receipt-bound analysis](../results/comparisons/h3_refaudio_reconstruction.json)

Still not proven:

- how either result differs from the static-control condition, which remains
  unrendered;
- speech intelligibility or lip synchronization: the first TTS prompt did not request
  a speaking performance or lip-sync, so its subtle lower-face motion is not a valid
  capability test;
- beat-synchronized visual behavior: camera-compensated music-motion correlation was
  weak and did not beat shifted controls convincingly, despite strong audio transfer;
- absence of silence, noise, truncation, or duration anomalies in the decoded target
  soundtrack by human audition; and
- a second consecutive warm-cache pass or any production/promotion claim.

The TTS and music cells are therefore **cold machine evidence, with hash-bound human
video annotations and ear review still pending**. The video annotations are frozen in
[`h3_refaudio_human_reviews.json`](../results/comparisons/h3_refaudio_human_reviews.json).
The result supports H3 Ref2VA as a strong native music-transfer path, but
leaves lip-sync untested and does not establish music-responsive visual motion. Static
control remains unrendered; no warm repeat or promotion is implied.

## Prompt-only speaking retest after the retraction

The retraction above led to a controlled prompt-only retest using a medium-close
speaking instruction. The lab package contains two takes with identical fixture hashes
and graph shape; only the seed and output identity differ:

| Take | Seed | Machine result | Peak | Wall | Artifact/receipt evidence |
|---|---:|---|---:|---:|---|
| A | 42 | Cold machine gate pass | 6.71 GiB | 305.3 s | `results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json` |
| B | 43 | Cold machine gate pass | 6.51 GiB | 297.8 s | `results/h3_r2v_refaudio_tts_lipsync_exact_seed43_run1.json` |

Both rows, their immutable hashes, the shared fixture hashes, and the **864x480,
124-frame, 24-fps** media contract are collected in
[`h3_lipsync_ab_package.json`](../results/comparisons/h3_lipsync_ab_package.json).

The technical visual screen sees articulation in the speaking takes. That is narrower
than a lip-sync verdict. Jeffrey still must review full-clip mouth-shape timing, pause
settling, and cross-seed consistency. The HuMo leg is deliberately outside this lab's
whitelist and must run OTR-side against the exact fixture contract. The final H3 pair
uses only `portrait.png` and raw `tts_dialogue.wav`; no second scene image or derived
audio is present. Until that comparison,
H3 is a character-lane candidate rather than a replacement claim.

This retest does not restore the retracted verdict in either direction. It creates new
evidence under the missing action instruction while preserving the original neutral
clip as a separate, non-capability test.

## Unconditioned Mini Mime follow-through

The reconstruct-not-compose result directly changed the final Mime design. The new
proof has no `LoadAudio` or external audio-conditioning socket: picture in, sampled
joint latent, native audio out. It delivered **192 frames at 24 fps, exactly 8.000
seconds**, with a cold **6.71 GiB** peak. The graph, ledger binding, artifact hash, and
source receipt are frozen in
[`h3_mime_unconditioned.json`](../results/comparisons/h3_mime_unconditioned.json).

Objective FFmpeg 8.0.1 QA measured **-31.32 LUFS**, **1.00 LU** loudness range, and
**-13.55 dBTP** true peak, with zero continuous-silence events in all three configured
threshold/duration probes.
[`h3_mime_audio_qa.json`](../results/comparisons/h3_mime_audio_qa.json) explicitly
limits that finding to stream-level QA. Absence of any speech-like/vocal-like content,
intelligible or otherwise, and coherent diegetic
sync remain the inverted human ear gate; no promotion is inferred.
