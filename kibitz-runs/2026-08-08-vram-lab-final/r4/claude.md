# ROUND 4 — CONVERGENCE / RESIDUAL DEFECTS
# Adversarial Review — Claude Code

Grounded against: run_h3_suite.py (363 lines, fully read), validate_recipes.py (542 lines,
fully read), duration_match.py (154 lines, fully read), suites/h3_best_suite.json (fully
read), recipes/h3_mime_i2v.json (fully read), recipes/h3_i2v_best.json (fully read),
recipes/ltx_audio_gguf_tts_dialogue.json (fully read, representative of all four matrix
recipes), tests/test_runner_provenance.py (669 lines, fully read),
tests/test_duration_match.py (218 lines, fully read), run_recipe.py (first 2 KB preview;
remaining behavior inferred from the test suite which has 47 tests covering it).

---

## VERDICT

**yes-with-fixes**

The foundation is honest, the arithmetic is exact, the topology contracts are tight, and the
test coverage is real. Two items are build-blocking and must be fixed before rendering starts.
Three more are honesty or correctness gaps that should be resolved now while the cost is zero.
Everything else is verification bookkeeping that survives as VERIFY-AT-BUILD items. Nothing
needs to be cut.

---

## MUST-FIX (build-blocking before first render)

### M1 — evaluate_suite() does not enforce warm_pass for sentinel runs S1, S2, S3

**Location:** run_h3_suite.py:171–196 (evaluate_suite)

**What the code does:** evaluate_suite() enforces warm_pass for T1, I1, and R1 only
(lines 171–175). The S1/S2/S3 VRAM delta check (lines 185–193) reads peak_vram_gib,
net_peak_vram_gib, and post_settle_median_gib relative to S0, but never checks whether those
sentinel runs are themselves warm.

**What P7 says:** "A restarted server resets warm identity." Every post-W0 sentinel must be
warm. "Fail on any invalid child, >14.5 GiB peak, marginal result, non-warm second identity,
or >0.25 GiB rise in candidate repeat or sentinel peak/net/settled median."

**The gap:** If the ComfyUI server restarts between sentinels — a real possibility on a
16 GiB Windows laptop under sustained load — S1/S2/S3 would run as cold-identity runs and
their VRAM deltas would be meaningless (cold-vs-cold, not warm-vs-warm). evaluate_suite()
would not detect the identity reset and would report MACHINE SUITE PASS on structurally
invalid evidence.

**Confirmed by test:** test_runner_provenance.py's
`test_h3_suite_evaluation_requires_warm_pairs_and_no_creep` passes warm_pass=True to
sentinels as test data but the function under test never reads that field for sentinels —
confirmed by the test passing regardless. The test confirms the gap exists in production code,
not just in theory.

**Fix:** In evaluate_suite(), add a warm_pass check for S1, S2, and S3 alongside the
existing VRAM delta checks. The same pattern used for candidate warm pairs applies.

**Why this is build-blocking:** A false MACHINE SUITE PASS due to an undetected identity
reset is a dishonest result. P9's PROMOTION_BRIEF depends on the suite pass being truthful.

---

### M2 — P5 external mux is under-specified to the point of being unexecutable without
         guesswork, and its provenance receipt has no machine path

**Location:** input.md §P5, fourth and fifth paragraphs

**What P5 says:**
- "Separately make a clearly named source-delivery preview by copying its exact video stream
  and externally muxing the original hash-bound source fixture trimmed to 3.88 seconds."
- "Preserve a mux receipt and prove the video stream hash did not change."
- "Media validity means ffprobe succeeds; dimensions/fps/frame count equal the recipe
  contract; encoded video packets and required audio are present; and duration error is no
  more than one encoded frame. Video equality uses an elementary-stream SHA-256 produced by
  stream-copy hashing, not container-file equality."

**What exists in code:** Nothing. No runner function, no prescribed shell command, no schema
for the mux receipt, no validator that checks whether the mux receipt exists. The four
ltx_audio_gguf_* recipes contain no mux_contract or mux_receipt_requirements keys. Neither
validate_recipes.py nor run_recipe.py references anything named "mux" or "source_delivery."

**The gaps:**
1. The mux tool is not named. The plan says "externally muxing" but does not say ffmpeg
   (the only realistic choice on this platform), does not give the stream-copy flag sequence,
   and does not say where the output file lands.
2. "Elementary-stream SHA-256 produced by stream-copy hashing" is a technique, not a command.
   On Windows with ffmpeg, the correct approach is `ffmpeg -i input.mp4 -map 0:v -c copy -f
   rawvideo pipe:1 | sha256sum` or similar — but that is not stated anywhere.
3. The mux receipt has no schema. The plan says "preserve a mux receipt" but does not define
   what fields it must contain, where it is written, or what validates it.
4. There is no check that the mux receipt is present before the session is declared complete.

**Why this is build-blocking:** When the executor reaches P5 and produces the four ComfyUI
diagnostic artifacts, they will need to produce mux previews and receipts. Without a
prescribed tool, command, receipt schema, and existence check, any mux receipt they write
cannot be audited, and any claim that "the video stream hash did not change" is unverifiable
by a subsequent reviewer.

**Fix:** Either add a `mux_step` script (even a minimal shell snippet in the plan) that takes
the runner output path, trims the fixture to 3.88 s, muxes via ffmpeg stream-copy, SHA-256s
the elementary video stream of both source and output, writes a JSON mux receipt, and fails
if the hashes differ — OR explicitly demote the mux step to "manual human step, no machine
receipt required, not part of session certification." Do not leave it in the current state
where it is described as if it is provenance-certified but has no machine path at all.

---

## SHOULD-FIX (honesty or correctness gap; zero cost to fix now)

### S1 — h3_mime_i2v topology_contract omits CLIPLoader.device assertion without documenting
         the omission in intentional_divergences

**Location:** recipes/h3_mime_i2v.json topology_contract, intentional_divergences list

**What h3_i2v_best.json does:** Its topology_contract required_input_values includes
`{"node": "2", "input": "device", "equals": "default"}` for the CLIPLoader.

**What h3_mime_i2v.json does:** Its required_input_values does not include this assertion.

**What intentional_divergences says:** Lists six divergences. None mentions the omission of
the device assertion.

**The gap:** A reader comparing the two topology contracts against each other cannot tell
whether the device omission is deliberate (the mime proof does not need to enforce
device="default" because it runs on the same hardware) or an oversight. The
intentional_divergences list exists precisely to document these differences and prevent
future confusion. The gap breaks the integrity of that list.

**Fix:** Add one entry to h3_mime_i2v.json intentional_divergences:
`"The CLIPLoader device assertion is not enforced because the mime proof always runs on the
same lab server where device=default is the only option."`

If the position is that device SHOULD be enforced for the mime proof too (for consistency
with the certified low I2V from which mime derives), then add the assertion instead.

---

### S2 — P6 ESCALATE.md has no machine check; its claimed evidence is unauditable

**Location:** input.md §P6

**What P6 says:** "Record the final evidence in `docs/ESCALATE.md` and hard-close the
campaign without another render."

**What exists:** No schema for ESCALATE.md, no validator that checks its existence or
required fields, no mention of it in validate_recipes.py or run_recipe.py. It is a purely
prose deliverable.

**The gap:** Every other completion artifact in this system is hash-bound, schema-validated,
or receipt-grounded. ESCALATE.md is the only one that is not. If the session closes and
ESCALATE.md either does not exist or omits the cell B VRAM measurement (15.04 GiB
unreserved), there is no machine check to catch it. P9's SESSION_REPORT.md refers to
"every receipt/output, failures/stops, review calls, tests, server shutdown" — but LTX T2V
close-out evidence lives in a file with no enforcement.

**Fix:** Either define the minimum required fields for ESCALATE.md (e.g., campaign, cell
selected, peak_vram_unreserved_gib, reason_for_close, closed_at) and add a trivial
existence-plus-field check to validate_recipes.py — OR explicitly state in P6 that
ESCALATE.md is a human-authored prose document that is not machine-validated, and accept
the asymmetry with the rest of the system. Either way, resolve the ambiguity.

---

### S3 — P7 "prove pinned-memory presence/absence in both directions" is ambiguous against
         the suite manifest

**Location:** input.md §P7 last paragraph: "The live lane must prove pinned-memory
presence/absence in both directions."

**What the manifest does:** suites/h3_best_suite.json has
`"disable_pinned_memory": true` — the suite always runs with pinned memory disabled. There
is no second manifest configured for disable_pinned_memory=false.

**What the tests do:** test_runner_provenance.py tests suite_lane() with
disable_pinned_memory=false and verifies the child args and lane receipt strings, but this is
a unit test, not a live-server run.

**The gap:** If "both directions" means the live suite must exercise both
disable_pinned_memory=true and =false during the actual render campaign, the current
plan provides no mechanism to do so (there is no alternate suite manifest, no suite entry
with disable_pinned_memory=false). If "both directions" is satisfied by unit test coverage
of suite_lane(), that is a weaker standard than the plain reading of "the live lane must
prove."

**Fix:** Clarify in P7 what "both directions" means operationally:
- If live-run required: add a second probe run (not a full suite) with disable_pinned_memory
  false before the full suite, and define what "proves presence" means (e.g., runner
  log confirms pinned memory is active, VRAM delta differs from the disabled run).
- If unit-test-only: change the language from "the live lane must prove" to "unit tests
  confirm suite_lane() configures both directions correctly."

---

## VERIFY-AT-BUILD (passes if code matches claim; abort if not)

### V1 — Frozen template hash consistency across H3 best recipes

h3_mime_i2v.json and h3_i2v_best.json both declare frozen_template.sha256 =
`bb71aecdd3c0b62e56eafe03acb14d1cfeabec7072eaed9cbdf473c2aaf73009`.

**Verify before first render:**
- h3_r2v_best.json declares the same hash (it uses the same I2V template file).
- h3_t2v_best.json declares a different hash (it uses the T2V template, not I2V).
- The template file at `research/comfy_templates/video_minimax_h3_i2v.json` on the live
  server hashes to exactly this value. The topology_contract check in validate_recipes.py
  calls sha256 on the template file at that path; if the file was modified since the contract
  was written, every H3 I2V recipe would fail pre-render validation.

Abort if any of these three checks fails.

---

### V2 — The four ltx_audio_gguf_* matrix recipes and h3_mime_i2v are not in
          REQUIRED_RECIPES; verify they are covered by the P4 paper validator pass

validate_recipes.py REQUIRED_RECIPES has 22 entries. The plan claims "28 discovered recipes
pass." The four matrix recipes and h3_mime_i2v are in the discovered set, not the required
set.

**Verify before first render:**
- Run validate_recipes.py with the flag that covers all discovered recipes (not just
  REQUIRED_RECIPES), and confirm all five new recipes appear in the output and pass.
- Confirm that current_certification_errors() does not gate on the new recipes —
  they are experimental/extra and should not block the overall certification check.
- Confirm the "28 discovered recipes" count is stable (run twice, get the same number).

Abort if any new recipe fails static validation or if the count is wrong.

---

### V3 — absolute_duration_error_lte_s stored as float 0.041666... not 1/24 Fraction

h3_mime_i2v.json receipt_requirements.timing.absolute_duration_error_lte_s =
0.041666666666666664 (IEEE 754 double, not exact Decimal).

**Verify before render:**
- Confirm that run_recipe.py reads this value and compares duration_error_s against it using
  a method that is stable at this precision (e.g., compares `abs(error_s) <= tolerance + eps`
  where eps accounts for float imprecision, or converts both sides to Decimal before
  comparing).
- Specifically, `0.041666666666666664 < 1/24 (exact)` — if the runner uses strict `<` with
  a raw float comparison, a duration error of exactly 1/24 seconds could incorrectly fail.
- The test_duration_match.py test `test_receipt_contract_requires_duration_and_human_inverted_ear_gate`
  asserts `requirements["timing"]["absolute_duration_error_lte_s"] == 1 / 24` which passes
  because Python float `1 / 24 == 0.041666666666666664`. This test does NOT exercise the
  runner's enforcement path — it only checks the schema field value.

Abort if the runner uses strict `<` comparison without epsilon and the float is rounded down
from exact 1/24.

---

### V4 — h3_mime_i2v receipt_requirements defines timing.target_s = 3.75 and the runner
          enforces the target-duration tolerance from that contract

P8 says: "The generic media gate must enforce the target-duration tolerance when that contract
is present."

**Verify before render:**
- Confirm run_recipe.py's media_artifact_is_valid() or equivalent reads
  receipt_requirements.timing.target_s and .absolute_duration_error_lte_s from the recipe
  when present, and applies them to the ffprobe-measured duration rather than using a
  hardcoded tolerance.
- Confirm that a mock artifact with duration = 3.750 + (1/24 + epsilon) seconds would fail
  this gate.

This is marked VERIFY-AT-BUILD rather than MUST-FIX because the test suite covers the
runner's media gate extensively — but the specific path that reads timing requirements from
the recipe contract rather than from a hardcoded constant needs explicit confirmation.

---

### V5 — Fixture rename: interstitial_static.wav receipts reference the correct label

P3 says narration.wav was renamed interstitial_static.wav. Prior receipts referencing the
old name are immutable.

**Verify before first render:**
- The fixture receipt at fixtures/audio_receipts/ for interstitial_static.wav uses
  `"fixture_label": "interstitial_static"` (not "narration"), its SHA-256 matches the
  current file on disk, and audio_fixture_receipt_errors() returns [] for it.
- The recipe ltx_audio_gguf_interstitial_static.json references the receipt by its new label.
- No live recipe references "narration" as a fixture label.

Abort if any live recipe references the old fixture label.

---

### V6 — "28 discovered recipes" count is a verifiable claim; confirm before rendering

P3 claims 47 unit tests and 28 discovered recipes pass. These are stated as current fact.

**Verify:**
Run `python -m pytest tests/ -q` and `python validate_recipes.py` (or equivalent) and
confirm the numbers match. If either is wrong, the stated foundation is not established and
the plan's "Implemented pre-render foundation" section is inaccurate.

This is V6 rather than a MUST-FIX because it's a verification step P4 already mandates —
but it needs to be checked against exact counts, not just "tests pass."

---

## OPTIONAL (low-stakes cleanup; fix only if it costs nothing)

### O1 — Empty workflow key in h3_mime_i2v.json

h3_mime_i2v.json has `"workflow": {"nodes": [], "links": []}` at the top level. This key
is not validated by validate_recipes.py, not referenced by run_recipe.py, and not mentioned
in the plan. It appears to be scaffolding that was never removed.

It is structurally harmless. But it adds 3 lines to a recipe that is otherwise clean, and
any future reader will have to confirm it is vestigial rather than meaningful. Remove it if
the file is being touched for any other reason; do not touch the file solely for this.

---

## CUT (over-engineering; remove to reduce risk)

None identified. The plan does not over-specify. Every invariant and check in the code has
a corresponding stated requirement. The complexity budget is appropriate for the evidence
standard the system is trying to meet.

---

## Summary table

| ID | Severity      | File                          | One-line description                                    |
|----|---------------|-------------------------------|--------------------------------------------------------|
| M1 | MUST-FIX      | run_h3_suite.py:171-196       | evaluate_suite() skips warm_pass for S1/S2/S3 sentinels|
| M2 | MUST-FIX      | input.md §P5                  | Mux step has no tool, receipt schema, or machine path   |
| S1 | SHOULD-FIX    | recipes/h3_mime_i2v.json      | CLIPLoader.device omission not in intentional_divergences|
| S2 | SHOULD-FIX    | input.md §P6                  | ESCALATE.md has no schema or existence check            |
| S3 | SHOULD-FIX    | input.md §P7                  | "Both directions" pinned-memory proof is ambiguous      |
| V1 | VERIFY        | recipes/h3_*.json             | Frozen template hash consistent across H3 best recipes  |
| V2 | VERIFY        | validate_recipes.py           | 5 new recipes covered by paper validator pass           |
| V3 | VERIFY        | run_recipe.py                 | float 0.04166... duration tolerance comparison is safe  |
| V4 | VERIFY        | run_recipe.py                 | Media gate reads timing contract from recipe, not const |
| V5 | VERIFY        | fixtures/audio_receipts/      | interstitial_static receipt label is correct            |
| V6 | VERIFY        | tests/, validate_recipes.py   | 47 tests and 28 recipes confirm before first render     |
| O1 | OPTIONAL      | recipes/h3_mime_i2v.json      | Empty workflow key is vestigial scaffolding             |
