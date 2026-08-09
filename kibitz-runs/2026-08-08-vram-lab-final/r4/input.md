# Final Lab Completion Plan

Status: pre-render hardening. OTR integration is out of scope. All work is
local/offline except explicitly requested local CLI reviews. Nothing is pushed.

## P1. Outcome

Produce receipt-grounded evidence for four audio-character conditions, close
the exhausted LTX T2V campaign honestly, machine-certify the three official-
topology H3 best recipes with a VRAM-creep suite, and render one experimental
Mini Mime I2V proof. Finish with `docs/PROMOTION_BRIEF.md` and
`docs/SESSION_REPORT.md`, then commit locally without pushing.

## P2. Non-negotiable invariants

- Only the owned SageAttention-free lab server on `127.0.0.1:8199` may run.
  Port 8188 is never queried or touched. A live unreceipted 8199 is an abort.
- Renders are sequential under one Windows coordinator lease. Standalone runs
  own the GPU lease; a suite owns the coordinator/GPU lease for its full life,
  and only direct child runners with the suite nonce, owner PID/create-time and
  parent relationship may re-enter it. Stale receipts are never deleted outside
  the coordinator, and release requires the same nonce still on disk.
- Global pass ceiling is 14.5 GiB. A 14.25-14.50 GiB result is marginal and
  not promotable. Direct `reserve-12gb` is offload pressure, not 12 GiB-card
  emulation.
- Official workflow topology is frozen evidence. Required nodes, connections,
  fixed sampler values, frozen-template hashes, nested links, output indices,
  required live inputs, and graph reachability fail closed.
- H3 promotion always needs separate hash-bound human video and native-audio
  decisions. Generated H3 audio is audition-only except the deliberately
  experimental Mini Mime payload, which has an inverted human ear gate.
- New recipes/results never inherit a prior human verdict. Historical run
  receipts remain immutable; truth corrections are additive.

## P3. Implemented pre-render foundation

- `narration.wav` was truthfully renamed `interstitial_static.wav`; prior
  speech conclusions are superseded in `docs/AUDIO_FIXTURE_CORRECTIONS.md`.
- Every referenced audio fixture has a hash-bound probe, volume, loudness and
  human-description receipt. The runner re-probes before upload and includes
  the receipt hash in run identity and final provenance validation.
- Four exact 3.88-second, mono 32 kHz float conditioning WAVs are frozen near
  -25.8 LUFS. Their four LTX IA2V recipes differ only in condition metadata,
  `LoadAudio` basename and output prefix. No gain node was inserted.
- H3 T2V/I2V/R2V best recipes use the official `RandomNoise -> BasicGuider ->
  res_multistep -> BasicScheduler(simple,20) -> SamplerCustomAdvanced` bundle
  and native joint-audio decode. R2V uses Ref2VA and `<Picture 1>`.
- `duration_match.py` maps H3 `17k+5 @ 24` and LTX `8n+1 @ 25` using exact
  Decimal/Fraction arithmetic. Whole-frame removals and sub-frame endpoint
  trims are distinct. All real timed ledger lines/music slots are tests.
- Mini Mime I2V is a 90-frame/3.750-second low H3 clone delivering native H3
  audio. Its prompt bans dialogue, voices, vocals, humming and music.
- Current offline evidence: 47 unit tests and 28 discovered recipes pass.

## P4. Required pre-render reviews

1. Run the full driver-aware Kibitz R1-R4 arc with the ComfyUI profile. Codex
   Desktop is the anchor/judge; Antigravity and Claude Code are independent
   reviewers. Ground every claim against the repository.
2. Run `codex exec review --uncommitted --ephemeral` after integrating fixes.
3. Run the paper validator and full tests, then an owned 8199 `/object_info`
   validation of every changed workflow without queueing a prompt.
4. Abort if the worktree, recipe, runner, fixture, model or receipt provenance
   changes during a render campaign.

## P5. Four-condition LTX audio matrix

Run exactly once each on the same live server and `reserve-12gb` lane:

1. `ltx_audio_gguf_interstitial_static`
2. `ltx_audio_gguf_tts_dialogue`
3. `ltx_audio_gguf_music_opening`
4. `ltx_audio_gguf_music_closing`

Each result is cold experimental evidence, never a warm `PASS`. Stop the
matrix on invalid media, provenance drift, or global VRAM failure. The ComfyUI
artifact is the authoritative conditioning diagnostic and contains the matched
derivative for fair A/B listening. Separately make a clearly named source-
delivery preview by copying its exact video stream and externally muxing the
original hash-bound source fixture trimmed to 3.88 seconds. The source mux is
intentionally not loudness-matched and never replaces the diagnostic artifact.
Preserve a mux receipt and prove the video stream hash did not change. Media
validity means ffprobe succeeds; dimensions/fps/frame count equal the recipe
contract; encoded video packets and required audio are present; and duration
error is no more than one encoded frame. Video equality uses an elementary-
stream SHA-256 produced by stream-copy hashing, not container-file equality.

Human review question: does motion character track audio character? Compare
static against TTS and both music excerpts; identical/effectively identical
motion triggers a conditioning-strength investigation, not tuning.

## P6. LTX T2V close-out

The three-attempt allowance is already exhausted: baseline runs, tiled retune,
then factorial cells A/B/C. No fourth quality topology or certification rerun
is part of this campaign. Existing cell B is the selected canonical graph but
remains human-pending and previously measured 15.04 GiB unreserved. Record the
final evidence in `docs/ESCALATE.md` and hard-close the campaign without another
render.

## P7. H3 best warm-pair and creep suite

Use `lab-8199, sage-free, no-pinned, reserve-12gb`. Keep one suite lock and one
verified server. Sequence:

`W0, S0, T0, T1, S1, I0, I1, S2, R0, R1, S3`

The canonical order and roles live in `suites/h3_best_suite.json`. `W0` and
every `S*` are the same H3 I2V low identity; T/I/R are best recipe cold/warm
pairs. The suite must reject substitutions, reordering, identity changes,
non-monotonic run/config counters, server-instance changes, or archive/current
receipt disagreement before calculating a pass.

Before any child, preflight must match the manifest's exact ordered
`(label, recipe, role)` tuples. Each pair must share a nonempty identity and
verified server PID/create-time, both gate-pass, and increment run/config counts
exactly by one. W0 through S3 share the sentinel identity and every post-W0
sentinel is warm. A restarted server resets warm identity.

Run numbering comes from the current alias plus every archive. Malformed state,
alias rollback, duplicate numbers, or an existing target archive aborts. The
archive is created exclusively; the current alias is atomically replaced from
the same bytes. Suite summaries hash and parse those archival bytes, not a
mutable alias. Suite receipts get a unique run id and are written only while the
coordinator is held; a lock loser writes nothing.
After every child, wait two seconds and sample two seconds of settled VRAM.
Capture the same settled median immediately before each child and record the
post-minus-pre settled delta.
Fail on any invalid child, >14.5 GiB peak, marginal result, non-warm second
identity, or >0.25 GiB rise in candidate repeat or sentinel peak/net/settled
median. Record general failures separately from actual VRAM-creep failures.
Machine suite pass still leaves every best artifact human video/audio pending.
Any abort writes a failure receipt, releases only locks still owned by this
process, and confirms owned server/listener exit before a PASS can survive.
Shutdown is bounded and returns structured evidence. Final status, cleanup
result and `finished_at` are written atomically while the coordinator remains
held; cleanup failure forces FAIL rather than preserving a prior PASS.
The live lane must prove pinned-memory presence/absence in both directions.
H3 contracts enforce the exact node-ID/class set, required absent optional
sockets for each mode, and the declared installed ComfyUI commit/version.

## P8. Mini Mime proof

Only after P5-P7, render one `h3_mime_i2v` from `scene_still.png`. The timing
plan is the documented OTR default 3.750 seconds: 90 H3 frames, no trim. Verify
encoded frames, video/audio streams, and delivered duration within one 24-fps
frame while retaining exact `target_s`, planned/rendered seconds, whole-frame
trim, sub-frame tail and measured `delivered_s` receipt fields. The generic
media gate must enforce the target-duration tolerance when that contract is
present.

Stop before any R2V mime. The inverted ear gate is human-only: no intelligible
speech-like/vocal-like content and coherent diegetic synchronization, plus a
one-line soundscape description bound to artifact SHA. Do not render R2V mime
without that approval. The session may still close with this gate explicitly
`PENDING_HUMAN_AUDITION`; that defers R2V rather than fabricating approval.

## P9. Completion and promotion truth

- `PROMOTION_BRIEF.md` distinguishes machine gates, human gates, stale or
  superseded evidence, experimental Mini Mime, license scope and limitations.
- `SESSION_REPORT.md` is written after the queued machine work and first mime
  proof are complete. It records every receipt/output, failures/stops, review
  calls, tests, server shutdown, and any `PENDING_HUMAN_AUDITION` gate. A
  pending mime verdict defers R2V but does not block truthful session reporting
  or the local commit.
- Run a final Codex review, resolve verified findings, rerun validation/tests,
  commit locally, and never push.
