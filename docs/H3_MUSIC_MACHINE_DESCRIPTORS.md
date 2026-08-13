# ADVISORY -- machine descriptors; hears nothing the operator has not ruled on; PENDING_HUMAN fields unaffected

This is a machine-description report, not a verdict. It does not close, fill,
or reinterpret any `PENDING_HUMAN` field in the H3 unconditioned-music study.

## Capability check

I attempted native ingestion of the requested control artifact,
`outputs/h3_unconditioned_music_scene_seed42_f124_out_00002_.mp4`. I extracted
and transcoded its selected audio stream to a local MP3 for attempted playback,
then delivered that as a native audio item. No auditory percept or transcription
was exposed to me. I also had no native moving-video playback channel. I
therefore did **not** hear or watch the clip; I could only read its bytes and
locally computed outputs. Track A was not performed. The report below is Track
B only.

The separate transcript supplied by Jeffrey says another local agent viewed
frames but could not hear the audio. That does not transfer sensory perception
to this agent and was used only as a QA lead, not as clip evidence.

## Reproducible method and command provenance

Everything ran offline from the repository root with the already-installed
FFmpeg 8.0.1, Python 3.10, and NumPy 1.26.4. The environment versions came from
`ffmpeg -version` and
`python -c "import sys,numpy; print(sys.version); print(numpy.__version__)"`.
Nothing was installed or downloaded. The exact driver command was:

```powershell
python -B scratch/h3_music_machine_descriptors/analyze.py --result-dir scratch/h3_music_machine_descriptors/run_20260810_v3
```

The driver script is
`scratch/h3_music_machine_descriptors/analyze.py` (SHA-256
`24cc09b0a7a187d7cf7a5dee0ab5547ad4b8bf64d40641ace86c1c8f571a5b3f`).
Its full-precision result and exact, fully expanded per-clip commands are in
`scratch/h3_music_machine_descriptors/run_20260810_v3/descriptors.json`
(SHA-256
`0828641f854c9fadbd4c1b70c1c714e04a4c17aee683def9cc02ec4d33aa65f2`).
Those hashes came from the exact commands
`Get-FileHash -Algorithm SHA256 scratch/h3_music_machine_descriptors/analyze.py`
and
`Get-FileHash -Algorithm SHA256 scratch/h3_music_machine_descriptors/run_20260810_v3/descriptors.json`.
For every table row, the exact command behind a tag is stored in that row's
`commands` object at the following key; these are literal absolute command
strings, not templates:

- `[C0]` `C0_probe`: FFprobe audio-stream metadata.
- `[C1]` `C1_ebur128`: `ebur128=peak=true`; the final `Summary` supplies
  integrated LUFS, LRA, and true peak.
- `[C2]` `C2_silencedetect`: `silencedetect=noise=-40dB:d=0.2`.
- `[C3]` `C3_astats`: `astats=metadata=0:reset=0`; channel sections supply RMS,
  flat factor, and FFmpeg peak count.
- `[C4]` `C4_pcm_extract`: mono, 48 kHz, signed 16-bit PCM to NumPy.
- `[C5]` `C5_scene_scores`: all-frame `lavfi.scene_score` extraction.
- `[A]` the exact driver command above applies the pinned NumPy calculations
  to `[C4]` and matches `[C4]` buckets with `[C5]` buckets.

The table's command tags are citations: for example, the Q2-B LUFS number is
produced by Q2-B's exact `records[].commands.C1_ebur128` string and parsed by
`[A]`. A second run in `run_20260810_v4` reproduced every record and metric
exactly.

NumPy definitions under `[A]`: complete, non-overlapping 50 ms Hann windows;
centroid from magnitude-weighted frequency; flux as the mean positive binwise
change between consecutive L1-normalized magnitude spectra; periodicity as the
largest overlap-energy-normalized autocorrelation coefficient in the
0.25–2.00 s lag band after global mean removal; and energy ratios for low
20–250 Hz, mid 250–2,000 Hz, and high 2,000–24,000 Hz. No loudness
normalization was applied. The alignment proxy is Pearson correlation across
matching, complete 0.5 s buckets between mean FFmpeg frame-change scene score
and linear mono PCM RMS. The first-frame zero sentinel and incomplete terminal
buckets are excluded. It is a crude zero-lag association, not proof of motion
semantics, audiovisual synchronization, causality, or event alignment.

Presentation rounding only: ebur128 values retain FFmpeg's 0.1-unit output;
silence time uses 0.001 s; RMS uses 0.01 dB; centroid uses 0.1 Hz; flux,
periodicity, lag, and correlation use 0.001; band ratios use 0.1 percentage
point. Full precision remains in the pinned JSON.

## Objective descriptors

`L/R` means left/right channel. `Sil n/s` means detected interval count and
total time below the configured threshold. Threshold crossings can split one
low-level region into multiple intervals, so interval count is not an audible
stutter count. FFmpeg `Peak count` is the count of samples attaining the
measured peak, not a count of acoustic events. FFmpeg `Flat factor` is its
time-domain astats statistic, not spectral flatness; zero does not classify
tone, noise, or music. LRA here is raw FFmpeg output over short clips, not a
robust program-length dynamics measure. The artifact shown in each row is the
exact file analyzed from Jeffrey's list.
Artifact selection follows those literal filenames, which are the canonical
cold copies. Although the request parenthetically preferred warm
representatives, each selected file is SHA-256-identical to its warm mate, so
every byte-derived metric is also exactly the warm mate's metric; no file
substitution occurred.

`PCM s` includes complete decoded AAC frames and padding. It can therefore be
slightly longer than the container duration recorded in the study report; this
is a decoder-duration convention, not extra generated content.

| Clip and exact artifact | PCM s `[A/C4]` | I LUFS / LRA LU / TP dBFS `[A/C1]` | Sil n / s `[A/C2]` | RMS dBFS L/R; flat L/R; peak count L/R `[A/C3]` | Centroid mean ± SD Hz `[A/C4]` | Flux `[A/C4]` | Periodicity r @ lag s `[A/C4]` | Energy low / mid / high % `[A/C4]` | Scene-score↔RMS r `[A/C4/C5]` |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| Q-CONTROL — `h3_unconditioned_music_scene_seed42_f124_out_00002_.mp4` | 5.184 | -56.2 / 0.2 / -48.0 | 1 / 5.184 | -58.26/-58.16; 0/0; 2/2 | 2436.9 ± 324.6 | 0.247 | 0.693 @ 0.275 | 78.4 / 20.0 / 1.6 | -0.114 |
| Q2-B — `h3_unconditioned_music_motion_small_seed42_f124_out_00001_.mp4` | 5.184 | -24.0 / 21.5 / -8.2 | 5 / 4.789 | -36.18/-36.07; 0/0; 2/2 | 2303.3 ± 639.2 | 0.267 | 0.044 @ 0.708 | 13.6 / 85.4 / 1.0 | -0.203 |
| Q2-C — `h3_unconditioned_music_motion_large_seed42_f124_out_00001_.mp4` | 5.184 | -23.1 / 2.8 / -5.3 | 4 / 2.803 | -31.73/-31.60; 0/0; 2/2 | 2193.1 ± 1076.7 | 0.274 | 0.026 @ 0.308 | 20.3 / 56.9 / 22.8 | -0.667 |
| Q3 seed 43 — `h3_unconditioned_music_scene_seed43_f124_out_00001_.mp4` | 5.184 | -56.1 / 0.3 / -37.2 | 2 / 5.182 | -56.75/-56.77; 0/0; 2/2 | 2505.5 ± 244.4 | 0.292 | 0.130 @ 0.945 | 62.2 / 34.5 / 3.3 | 0.210 |
| Q3 seed 44 — `h3_unconditioned_music_scene_seed44_f124_out_00001_.mp4` | 5.184 | -13.9 / 1.4 / -0.8 | 2 / 1.164 | -17.41/-17.29; 0/0; 2/2 | 1862.5 ± 1414.9 | 0.420 | 0.097 @ 0.640 | 40.7 / 58.6 / 0.7 | -0.610 |
| Q3 seed 45 — `h3_unconditioned_music_scene_seed45_f124_out_00001_.mp4` | 5.184 | -13.9 / 2.9 / -2.2 | 2 / 1.550 | -17.46/-17.49; 0/0; 2/2 | 3418.7 ± 3226.6 | 0.459 | 0.103 @ 1.053 | 19.0 / 79.9 / 1.1 | 0.269 |
| Q3 seed 46 — `h3_unconditioned_music_scene_seed46_f124_out_00001_.mp4` | 5.184 | -41.0 / 2.2 / -17.0 | 5 / 4.673 | -46.03/-46.00; 0/0; 2/2 | 2478.7 ± 604.9 | 0.271 | 0.149 @ 1.799 | 59.7 / 37.6 / 2.8 | 0.454 |
| Q4-B — `h3_unconditioned_music_score_seed42_f124_out_00001_.mp4` | 5.184 | -21.5 / 0.5 / -12.5 | 0 / 0.000 | -24.36/-23.28; 0/0; 2/2 | 756.7 ± 138.6 | 0.114 | 0.301 @ 0.337 | 18.3 / 81.7 / 0.0 | -0.294 |
| Q4-C — `h3_unconditioned_music_sfx_seed42_f124_out_00001_.mp4` | 5.184 | -51.4 / 0.2 / -42.4 | 1 / 5.184 | -53.56/-53.46; 0/0; 2/2 | 2672.2 ± 349.9 | 0.253 | 0.671 @ 0.325 | 74.8 / 22.1 / 3.1 | 0.320 |
| Q5-192 — `h3_unconditioned_music_scene_seed42_f192_out_00001_.mp4` | 8.000 | -18.3 / 9.2 / -4.9 | 7 / 5.962 | -27.60/-27.59; 0/0; 2/2 | 2300.3 ± 733.8 | 0.298 | 0.118 @ 0.704 | 13.2 / 85.4 / 1.4 | -0.096 |
| Q5-277 — `h3_unconditioned_music_scene_seed42_f277_out_00001_.mp4` | 11.552 | -28.9 / 15.0 / -3.5 | 11 / 9.835 | -35.91/-35.77; 0/0; 2/2 | 2347.9 ± 718.1 | 0.300 | 0.058 @ 1.999 | 76.7 / 22.8 / 0.5 | -0.170 |

## Comparative notes for the five study questions

### 1. Native audio occurrence and coherence

All artifacts expose a decodable audio stream and non-empty PCM under `[C0]`
and `[A/C4]`. The objective levels span a wide numeric range: Q-CONTROL
and Q3 seed 43 are near -56 LUFS, while Q3 seeds 44 and 45 are -13.9 LUFS
`[A/C1]`. Q-CONTROL and Q4-C remain below the -40 dB silence threshold for
their entire 5.184 s decoded duration `[A/C2/C4]`; Q4-B has no interval meeting
that threshold `[A/C2]`. These facts establish measurable signal behavior, not
instrumentation, speech, melody, rhythm, development, coherence, or a sensory
category. Periodicity in a very low-level signal can reflect codec-floor or
waveform repetition and is not, by itself, evidence of audible rhythm.

### 2. Job 0 — motion-prompt comparison

Relative to Q-CONTROL, Q2-B and Q2-C have higher integrated level
(-24.0 and -23.1 versus -56.2 LUFS) and less total thresholded time (4.789 and
2.803 versus 5.184 s) `[A/C1/C2]`. Their energy distributions also move from
the control's low-band majority toward a mid-band majority, with Q2-C carrying
22.8% in the high band `[A/C4]`. The crude scene-score/RMS correlations are
-0.114, -0.203, and -0.667 for control, B, and C respectively `[A/C4/C5]`. This is a
descriptor difference across prompts; the correlation signs do not establish
event alignment or causal motion response.

### 3. Job 1 — seeds 42–46

The five scene-prompt seeds span -56.2 to -13.9 LUFS and 1862.5 to 3418.7 Hz
in centroid `[A/C1/C4]`. Seeds 42/control and 43 are close in integrated level
(-56.2 and -56.1 LUFS),
seeds 44 and 45 are both -13.9 LUFS, and seed 46 lies between them at -41.0
LUFS `[A/C1]`. Seed 44 has the lowest centroid of the five at 1862.5 Hz; seed
45 has the highest at 3418.7 Hz and the largest centroid spread at 3226.6 Hz
`[A/C4]`. Periodicity is also split: the very low-level seed-42/control signal
is 0.693, while seeds 43–46 range from 0.097 to 0.149 `[A/C4]`. These are
descriptor differences among the tested seeds, not a population-level hit rate or a
content classification.

### 4. Job 2 — score-language versus SFX-language comparison

Q4-B differs from control and Q4-C on these machine descriptors: it is
-21.5 LUFS, has no detected threshold interval, has the lowest centroid in the
set at 756.7 Hz, and has a periodicity score of 0.301 `[A/C1/C2/C4]`. Q4-C is
-51.4 LUFS, remains under the threshold for 5.184 s, has a 2672.2 Hz centroid,
and has a periodicity score of 0.671 `[A/C1/C2/C4]`. The requested labels
“score” and “SFX” cannot be confirmed from these numbers, and no claim is made
about orchestration, diegetic events, dialogue, or prompt obedience.

### 5. Job 3 — duration comparison

The decoded durations are 5.184, 8.000, and 11.552 s for f124, f192, and f277
`[A/C4]`. Their thresholded times are 5.184, 5.962, and 9.835 s, while their
integrated levels are -56.2, -18.3, and -28.9 LUFS `[A/C1/C2]`. The f192 and
f277 signals have larger loudness ranges than f124 (9.2 and 15.0 versus 0.2 LU)
and low periodicity scores (0.118 and 0.058 versus 0.693) `[A/C1/C4]`. This
describes time-varying level and waveform structure only. Without hearing or
native video playback, it does not establish survival, degradation, stutter,
musical development, or audiovisual continuity near the end.

## Advisory boundary

The crude alignment proxy, spectral descriptors, loudness measurements, and
silence threshold do not replace listening or viewing. Native audio/music
occurrence and coherence, body-motion response, seed-level audio/music hit
rate, score-versus-SFX comparison, duration behavior, visual integrity, and
overall preference all remain `PENDING_HUMAN`.

Recommendation remains **HOLD pending Jeffrey's eyes/ears**.
