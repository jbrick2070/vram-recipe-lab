# Envelope ladders — completed measurement report

Status: **COMPLETE WITH A MACHINE-GATE FAILURE AND A SEPARATE REVIEW PROOF** on 2026-08-10. Jobs A and B are measured. Job A is packaged; Job B has an append-only recovered fit after a post-render reducer defect. Job C stopped at its first cold cell after exceeding the 14.5 GiB ceiling and was operator-skipped. A later, separately authorized cold review source completed Job D without reopening Job C.

## Job A — HuMo 14B diet boot

All four legs used the exact HuMo 14B production graph, seed 7, `--reserve-vram 2.921`, `--disable-pinned-memory`, portrait and raw-TTS fixture parity, and a cold→warm pair on one owned server per orientation. Human quality parity was initially pending and was later ruled PARITY below.

| Orientation | Canvas | Role | Peak VRAM | Wall time | Result | Numeric receipt |
|---|---:|---:|---:|---:|---|---|
| Portrait | 480×832×97 | cold | 13.14 GiB | 294.1 s | PASS (cold) | [`humo_14b_diet_portrait_480x832_f97_run1.json`](../results/humo_14b_diet_portrait_480x832_f97_run1.json) |
| Portrait | 480×832×97 | warm | 13.22 GiB | 285.3 s | PASS | [`humo_14b_diet_portrait_480x832_f97_run2.json`](../results/humo_14b_diet_portrait_480x832_f97_run2.json) |
| Landscape | 832×480×97 | cold | 13.17 GiB | 287.8 s | PASS (cold) | [`humo_14b_diet_landscape_832x480_f97_run1.json`](../results/humo_14b_diet_landscape_832x480_f97_run1.json) |
| Landscape | 832×480×97 | warm | **13.06 GiB** | 288.6 s | **PASS** | [`humo_14b_diet_landscape_832x480_f97_run2.json`](../results/humo_14b_diet_landscape_832x480_f97_run2.json) |

Plain answer: **yes, HuMo 14B fits under 14.5 GiB with the diet boot at the canonical 832×480 landscape canvas.** The warm landscape peak is 13.06 GiB, leaving 1.44 GiB of headroom. The central hash-bound evidence package is [`humo_14b_diet_envelope.json`](../results/humo_diet/humo_14b_diet_envelope.json).

The human-review artifact [`humo_14b_diet_ab_production_vs_reserve2p921_warm.mp4`](../outputs/humo_14b_diet_ab_production_vs_reserve2p921_warm.mp4) places the original unclamped production portrait clip beside the warm diet portrait clip and maps the exact raw TTS fixture once from time zero. Jeffrey later ruled it PARITY below.

**RULED by Jeffrey 2026-08-10: PARITY** ("look the same to me"). The 14B diet
boot is machine-certified AND human-approved: 13.06 GiB warm at the canonical
landscape canvas, zero perceived quality cost. The hero cast (`humo_14B_169`
under the `humo_diet` boot contract) is CLOSED.

**Operator scheduling rulings, same date:** the Job C re-run is SKIPPED (the
spec's lane 7 ships with the existing 864x480 envelope numbers); Job D and
the prompt-only origin test run NOW. Because Job C is skipped, Job D renders
its own single audio-conditioned f192 source leg on the standard reserve lane.

**Job D RULED by Jeffrey 2026-08-10 (after delivery):** D1 (drift case) and
D2 (fix case) "showed basically the same lip sync - not really good, like a
Japanese dub, but better than nothing." Two conclusions, kept separate:
(1) PERCEPTUAL - at H3's dub-grade base lip quality, the 320 ms drift is not
the dominant visible error at 8 s; (2) STRUCTURAL - the 24->25 conversion is
RETAINED regardless, because it is what makes the delivered frame count match
the 25 fps segment window and the WAV slice (192 frames labeled 25 fps IS a
7.68 s clip against an 8.00 s audio window - a duration-contract violation
before it is ever a lip-sync question). The fix ships on arithmetic; the
perceptual A/B simply shows it costs nothing. Expectation note for casting:
H3 workhorse lips at production length are dub-grade - consistent with the
bakeoff's "OK second," not with hero-grade sync.

The portrait warm runner completed and wrote valid measurement evidence, but its detached command host interrupted normal final cleanup. The exact dead lease owner, verified owned-server shutdown, nonce-matched lock removal, and clean postconditions are recorded separately in [`humo_14b_diet_portrait_480x832_f97_run2_recovery.json`](../results/humo_diet/humo_14b_diet_portrait_480x832_f97_run2_recovery.json). This is not represented as normal runner shutdown proof.

## Job B — WAN/FastWan cost-row ladder

All 16 legs completed sequentially on one positively identified production-wrapper server. Every rung has an immediately consecutive cold→warm pair, 200 ms sidecar evidence, the independent adapter peak, a hash-bound clip copy, and one pre-server quiescent desktop baseline of 1,202 MiB. The server reported exactly one resolved `network_mode: offline` before execution. The recovered fit is [`attempt-004.json`](../results/otr_side/wan_cost_ladder/fits/attempt-004.json), SHA-256 `7ba01cbfb68d9d5316d0f684d240bc1b3443b61d4d98f021e91a14c4daf345c2`.

| Engine | Model frames | Warm absolute peak | Warm demand above desktop | Warm wall time |
|---|---:|---:|---:|---:|
| `wan_ti2v` | 25 | 8,318 MiB | 7,116 MiB | 87.797 s |
| `wan_ti2v` | 65 | 8,455 MiB | 7,253 MiB | 163.406 s |
| `wan_ti2v` | 93 | 8,246 MiB | 7,044 MiB | 213.078 s |
| `wan_ti2v` | 129 | 8,871 MiB | 7,669 MiB | 303.125 s |
| `wan_ti2v` | 177 | 9,606 MiB | 8,404 MiB | 398.782 s |
| `fastwan_8gb` | 25 | 8,279 MiB | 7,077 MiB | 42.578 s |
| `fastwan_8gb` | 93 | 8,729 MiB | 7,527 MiB | 77.000 s |
| `fastwan_8gb` | 177 | 8,641 MiB | 7,439 MiB | 122.000 s |

Candidate rows normalized to OTR's 1472×832 reference canvas:

- `wan_ti2v`: **6,910.8 MB overhead + 25.874 MB/frame**, max absolute residual 412.705 MB. The ladder is nonmonotonic: 65→93 frames decreases by 209 MiB.
- `fastwan_8gb`: **7,317.9 MB overhead + 6.900 MB/frame**, max absolute residual 191.328 MB. The ladder is nonmonotonic: 93→177 frames decreases by 88 MiB.

These are **CANDIDATE values only**. Final qualification still requires OTR's own `prepare()+render_clip` lifecycle with the candidate row installed; the measurements do not silently qualify or modify an OTR cost row.

The original attempt-004 lifecycle remains an immutable `INVALID` receipt because its first offline reducer reconstructed `C:\Windows\System32\cmd.exe` while the recorded process used the case-equivalent `C:\WINDOWS\system32\cmd.exe`. All render evidence was valid; the corrected reducer accepts only this semantic Windows path equivalence and continues to reject drift in switches, launcher script, attempt log, or lane. No rerender was performed. Earlier safe pre-render incidents are preserved rather than rewritten.

## Job C — H3 canonical canvas

The first cold cell, I2V at 832×480×107, completed sampling and artifact output but measured **15.390 GiB absolute peak**, above the hard 14.5 GiB gate. Its own pre-queue baseline was **2.326 GiB**, so the recorded net peak was **13.064 GiB**; wall time was **178.8 s**. The baseline is explicitly stamped `elevated-baseline lane, operator-authorized 2026-08-10`. The immutable numeric receipt is [`h3_i2v_canonical_832x480_f107_run1.json`](../results/h3_i2v_canonical_832x480_f107_run1.json), SHA-256 `180213dc163662f73e4cda2244f75cbabee4cf475e1a390ea650e6e889d10a1c`. Its 426,402-byte artifact is [`h3_i2v_canonical_832x480_f107_out_00001_.mp4`](../outputs/h3_i2v_canonical_832x480_f107_out_00001_.mp4), SHA-256 `3f1148b7817a0f00f6797d5f638e55ada0bbce8345cbf6c303c8ee948f086f42`.

The attempt-006 Manager log contains exactly one authoritative `network_mode: offline` announcement, one queued prompt, and one completed prompt. The pre-queue evidence excludes exactly the verified serving process and its direct Windows-venv launcher. The campaign then stopped before the warm leg or any later pair, as required by its first-failure policy, and the owned server, listener, PID receipt, idle-gate sidecar, and locks all shut down cleanly. Earlier attempts 001–005 produced no Job-C recipe receipt or artifact.

Because no second consecutive run exists, this recipe is not a warm pass. The five later canonical cells remain unrendered; the measured failure is not rerun or silently replaced. Note that 107 frames is below the installed H3 node tooltip's approximate trained range of 124–362; the measurement is reported without reinterpretation.

## Job D — historical pre-authorization state

At this boundary Job D was **BLOCKED, not packaged**. The original packager required the exact warm Job-C Ref2VA 192-frame receipt and artifact. Job C stopped at its first cold I2V cell, so neither required source existed and no substitute clip or review copy was created. A later operator authorization and completion are recorded in the dated section below.

1. 192 frames labeled 25 fps (7.68 s drift case).
2. Duration-preserving nearest-frame resample to 200 frames at 25 fps (8.00 s proposed fix).

The planned copies would discard model audio and mux the exact raw TTS fixture from time zero. Human sync judgment remained pending.

## Historical remaining execution at the Job-C terminal boundary

At that boundary no additional envelope render was authorized: Job C was terminal at the measured hard-gate failure and Job D was dependency-blocked. The later operator authorization superseded only the Job-D portion of this boundary; Job C remained skipped. The separate H3 music follow-up subsequently executed under its own receipts and stop rules: ten cold legs met their machine gate, while its final f277 leg saved a valid artifact but terminated the campaign at a 14.722 GiB hard-gate failure. See [`H3_MUSIC_FOLLOWUP.md`](H3_MUSIC_FOLLOWUP.md).

## Job D operator-authorized completion — 2026-08-10

This dated section supersedes the earlier Job D dependency block and the
Job-D portion of the historical remaining-execution boundary. Jeffrey
explicitly skipped the Job C rerun and authorized one new cold Ref2VA review
source on the standard H3 reserve lane. Job C remains stopped and was not
rerun.

The source used byte-pinned `portrait.png` (SHA-256
`3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad`)
and `tts_dialogue.wav` (SHA-256
`30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1`), seed 43,
832×480, 192 model frames at 24 fps, native model audio, Sage-free Manager
offline-test boot, `--disable-pinned-memory`, cache-classic, and reserve-12gb.
The immutable cold receipt is
[`h3_jobd_lipsync_refaudio_seed43_f192_run1.json`](../results/h3_jobd_lipsync_refaudio_seed43_f192_run1.json),
SHA-256 `64b978d70b54f536c2c28ca90ab8b2eb8362e764989eac8f5c1c78afba8682f5`.
It records a 2.276 GiB baseline, 6.876 GiB absolute peak, 4.600 GiB net peak,
436.0 s wall time, and the exact stamp
`elevated-baseline lane, operator-authorized 2026-08-10`. This is one cold
machine-gated review source only: `pass=false`, `warm_pass=false`, and it has
no certification or promotion effect. Its 441,179-byte native artifact is
[`h3_jobd_lipsync_refaudio_seed43_f192_out_00001_.mp4`](../outputs/h3_jobd_lipsync_refaudio_seed43_f192_out_00001_.mp4),
SHA-256 `2afc918a93dc2e38288bf6b59fc307cd5b17fdde0a124d9f40157eb3fb1df23e`.

The authoritative Manager log contains one `network_mode: offline`
announcement at line 106, before the first prompt at line 142. The source leg
then shut down its owned server and left no lab lock, PID receipt, idle-gate
sidecar, quarantine file, or listener on port 8199. The transport receipt is
[`launch.json`](../results/h3_short_jobs/operator_logs/h3short-jobd-20260811T005836Z-f0f7fb71/launch.json),
SHA-256 `f927be3714678fc3bdb1058da432225774b58f1c40c67703b516968a6a31818e`.

The deterministic packaging receipt is
[`h3_25fps_lipsync_proof.json`](../results/comparisons/h3_25fps_lipsync_proof.json),
SHA-256 `1a77874092aae8ccac0d8e6a12d9a6a8cd75820d53d44d2f2e96aea76bbb62d3`.
Both copies discard the model soundtrack and mux the exact raw
`tts_dialogue.wav` fixture from time zero.

| Copy | Video contract | Duration | Artifact | SHA-256 |
|---|---|---:|---|---|
| D1 drift | Original 192 frames relabeled 25 fps | 7.68 s | [`h3_ref2va_seed43_raw_192f_at25_drift.mp4`](../outputs/h3_ref2va_seed43_raw_192f_at25_drift.mp4) | `ed615f6c38aaa9236ae63c793f1ae9e14b6f62e781be5f9922028d83a7880159` |
| D2 fix | Nearest-frame duration-preserving resample, 200 frames at 25 fps | 8.00 s | [`h3_ref2va_seed43_resampled_200f_at25_fix.mp4`](../outputs/h3_ref2va_seed43_resampled_200f_at25_fix.mp4) | `162e290e55549d16f1851685718876d7474e619644e00c6bb545787eaeac8dc1` |

`PENDING_HUMAN`: whether D1 visibly drifts, whether D2 holds the mouth more
closely to the raw TTS, and whether either review copy is visually usable.
The packager makes no lip-sync or quality judgment. No OTR file was read for
mutation, edited, or pushed.
