# Kibitz Round 1 — H3 unconditioned-music attempt-005 recovery plan
Reviewer: Claude (Sonnet 4.6)
Focus: High-level arc / creative coherence, scope, assumption surface, correctness of high-level claims
Date: 2026-08-10

---

## VERDICT

**CONDITIONAL PASS — 4 MUST-FIX gaps before build.**

The narrative arc is clean and coherent: preserve every byte of attempt-004, publish an O_EXCL recovery receipt first, execute exactly four new legs, then update docs only on success. The boundary conditions are correctly stated. The scope is tight and the plan does not invent unnecessary structure.

However, four concrete implementation sites in the existing code will fail at runtime if the plan is executed as written, because the plan describes desired behavior without specifying which functions must change and how. These are not nitpicks — each one would block a leg, produce a duplicate render, or corrupt the lifecycle. They are listed below in descending severity.

Three SHOULD-FIX items address underspecified but recoverable gaps. Nothing should be cut — the plan is already lean.

---

## MUST-FIX BEFORE BUILD

### M1 — `ensure_pristine_pair()` has no branch for the pair-10 attempt-005 case

**Source:** `scratch/run_h3_unconditioned_music_campaign.py` lines 1287–1320

The existing code has exactly one special branch: `if resume_attempt_001 and pair_index == 1` (allows `_run1.json` + existing artifact). For all other cases it falls through to `canon.ensure_pristine_history()`, which rejects the presence of any run receipt.

Pair 10 enters attempt-005 with `_run1.json` present (the timed-out receipt) and **no artifact**. `canon.ensure_pristine_history()` will see the `_run1.json` and raise. The plan (step 4) describes the desired schedule — "allowed receipts 1-3, preserving failed run 1" — but does not specify that a new branch must be added to `ensure_pristine_pair()` to explicitly tolerate a receipt-without-artifact for pair 10.

**Required:** Add a branch for `resume_attempt_004 and pair_index == 10` that verifies `_run1.json` is present and matches the pinned SHA-256 from the plan (line 12: `4ab72334bc80d8155d1b1d1466258922a7a9e1ad2e289f37b07a510115d164bf`), verifies no artifact exists, and then permits execution of run 2 cold and run 3 warm. Without this branch, the first pair-10 execute leg will crash before any render.

---

### M2 — `expected_operator_campaign_argv()` is hardwired to `RESUME_ATTEMPT3_CAMPAIGN_ID` and raises for any other attempt_id

**Source:** `scratch/run_h3_unconditioned_music_campaign.py` lines 763–784, 787–822

`expected_operator_campaign_argv()` constructs the expected argv using `RESUME_ATTEMPT3_CAMPAIGN_ID` unconditionally and raises `CampaignError` if called with any other `attempt_id`. `validate_campaign_process_identity()` mirrors this — its error messages are also hardwired to attempt-004 language.

Plan step 3 says "exact launcher/recorder paths" and "require a clean owned-lab state before appending any attempt-005 lifecycle row," but does not identify these two functions as requiring generalization or duplication. The O_EXCL receipt (step 1) and the attempt-005 coordinator mode (step 3) will both call validation paths that currently only know about attempt-004 identity.

**Required:** Either generalize `expected_operator_campaign_argv()` to accept the new campaign id, or add a `RESUME_ATTEMPT4_CAMPAIGN_ID`-keyed branch analogous to the existing one. The plan must name this explicitly — "exact launcher/recorder paths" is not sufficient specification for a function that raises on unfamiliar input.

---

### M3 — The completion-window CLI option does not specify receipt schema propagation

**Source:** `run_recipe.py` line 3757 (`RUNNER_COMPLETION_TIMEOUT_S = 1800`); `verify_run_receipt()` in `scratch/run_h3_unconditioned_music_campaign.py` (checks `receipt_schema_version: 3`)

Plan step 2 says: add a fail-closed runner CLI option, accept one integer in a bounded range, record the selected value in each receipt. This is a real new feature — the hardcoded constant is confirmed at line 3757 with no CLI path.

What the plan does not say: whether adding `completion_timeout_s` to the receipt JSON requires a schema version bump (`RECEIPT_SCHEMA_VERSION = 3` → 4), or whether the verifier must be updated to validate the new field, or whether historical receipts (pairs 1-9, pair 10 run 1) without the field are accepted as `null`/absent.

`verify_run_receipt()` performs per-field validation. If it starts requiring `completion_timeout_s` for all receipts, it will fail on the 19 carried/historical receipts. If it does not validate it at all, the "recorded in each receipt" requirement is untestable.

**Required:** The plan must specify: (a) whether schema version increments, (b) whether `verify_run_receipt()` accepts `null` or absent `completion_timeout_s` for receipts predating step 2, and (c) what the verifier checks for attempt-005 receipts specifically.

[ASSUMPTION] The plan assumes adding a field to receipts is backward-compatible without schema versioning. This is not safe given the existing verifier's field-by-field validation pattern.

---

### M4 — The attempt-005 operator `.ps1` launcher and recorder files are not named

**Source:** `results/h3_unconditioned_music_campaign/` directory structure (operator_logs for attempts 003 and 004 both contain a `.ps1` launcher and a recorder Python file); `source_evidence()` lines 443–583 pins SHA-256/bytes for these for both attempts

Plan step 6 says: "Create a new attempt-005 operator directory atomically; on terminal exit, create a launch receipt bound to process identity, argv, stdout/stderr identities, the lifecycle hash chain, and the terminal event."

Plan step 1 says: "publish an O_EXCL attempt-004 recovery receipt" before editing any pinned source.

But `source_evidence()` must pin the attempt-005 operator files, and those files must exist before the O_EXCL receipt can include their hashes. The plan does not name:
- the attempt-005 launcher `.ps1` path
- the attempt-005 recorder Python file path
- where they live in `results/h3_unconditioned_music_campaign/`

Without naming them, the O_EXCL receipt cannot be written completely (step 1 depends on step 6 artifacts that don't exist yet), and `source_evidence()` cannot be updated (step 3 depends on names that are unspecified).

**Required:** Name the attempt-005 operator launcher and recorder files explicitly before the O_EXCL receipt step. The O_EXCL receipt must either (a) defer pinning the launcher/recorder to a post-creation verification receipt, or (b) the plan must clarify the creation ordering so it does not require files that don't exist yet at step 1.

[ASSUMPTION] The plan assumes the operator directory and its files can be created before the O_EXCL receipt without explaining how this ordering works in practice.

---

## SHOULD-FIX

### S1 — `pair_run_schedule()` needs a `resume_attempt_004 and pair_index == 10` branch but the plan does not name it

**Source:** `scratch/run_h3_unconditioned_music_campaign.py` lines 1059–1109

The function has special cases for `pair_index == 1` (all resume modes) and `pair_index == 2` (resume_attempt_003 only). Reviewer question 2 in the plan asks about this directly: "Does changing `run_recipe.py` correctly force pair 10 run 2 to reset to configuration count 1, then run 3 to configuration count 2?"

The answer is: no, and not because of `run_recipe.py`. The schedule for pair 10 (run 2 = cold/config 1, run 3 = warm/config 2, allowed receipts 1–3) requires a `pair_index == 10` branch in `pair_run_schedule()`. Without it, pair 10 will use the default schedule which starts at run 1.

The reviewer question surfaces the gap but the plan does not resolve it. The implementation site is `pair_run_schedule()`, not `run_recipe.py`.

**Required:** The plan (or a follow-up spec) should explicitly list `pair_run_schedule()` as a function requiring a new branch, and confirm that the config-count reset logic lives there, not in `run_recipe.py`.

---

### S2 — Nonce count check does not have a branch for attempt-005

**Source:** `scratch/run_h3_unconditioned_music_campaign.py` lines 1195–1198

```python
expected_nonce_count = 18 if resume_attempt_003 else (20 if resume_attempt_002 else 22)
```

Attempt-005 needs exactly 4 new executor nonces (plan step 4: "Use four unique attempt-005 executor nonces"). The existing chain assigns 22 for the base case. Attempt-005 would need to read as 4 (not 22), but the chain has no branch for `resume_attempt_004`.

This is a correctness check — if the branch is missing, the pre-flight validation will either pass with the wrong expected count or fail with a confusing error.

**Required:** Add `4 if resume_attempt_004 else` to the front of this expression, or restructure it to a lookup by attempt mode.

---

### S3 — No pin for current campaign source bytes in `source_evidence()`

**Source:** `scratch/run_h3_unconditioned_music_campaign.py` lines 128, 443–583

`ATTEMPT2_CAMPAIGN_SOURCE_SHA256` at line 128 pins the coordinator source bytes at the time of attempt-003. An analogous pin for the attempt-004 coordinator (to be used as the "original source bytes" pin in the O_EXCL recovery receipt) is not specified in the plan.

The plan says the O_EXCL receipt must "revalidate... the original source bytes" (step 1). If the attempt-004 coordinator source bytes are not pinned in `source_evidence()`, this revalidation is unimplementable as a check.

**Required:** Either add `ATTEMPT4_CAMPAIGN_SOURCE_SHA256` to `source_evidence()` or specify where the attempt-004 coordinator source hash appears in the recovery receipt data structure.

[ASSUMPTION] The plan assumes "original source bytes" are revalidated but does not say how the expected hash is embedded.

---

## OPTIONAL

### O1 — Reviewer question 1: extending vs. a dedicated coordinator

The plan asks whether extending the existing coordinator is safer than a dedicated attempt-005 coordinator. The answer from the code is: **extend**. The verification helpers (`verify_run_receipt`, `canon.ensure_pristine_history`, `source_evidence`, lifecycle hash chain logic) are not importable in isolation — they are tightly coupled to campaign state. A parallel coordinator would have to duplicate or import them anyway. The risk of drift between two coordinators exceeds the risk of a regression in the existing one.

No action required — the plan's preferred answer (extend) is correct. The reviewer questions are worth stating for the record but not for reversal.

---

## CUT THESE

Nothing. The plan is appropriately scoped. The steps map cleanly onto the existing code structure, the boundary conditions are correctly quoted from attempt-004 terminal state, and the success criteria (11 pairs / 22 legs / 4 new executions / clean shutdown / no unexpected artifacts) are complete and verifiable. No step is speculative or out-of-scope.

---

## Summary table

| ID | Severity | Topic |
|----|----------|-------|
| M1 | MUST-FIX | `ensure_pristine_pair()` has no pair-10 branch for receipt-without-artifact |
| M2 | MUST-FIX | `expected_operator_campaign_argv()` raises for any non-attempt-004 id |
| M3 | MUST-FIX | Completion-window receipt schema propagation unspecified |
| M4 | MUST-FIX | Attempt-005 operator launcher/recorder files unnamed; ordering conflict with O_EXCL receipt |
| S1 | SHOULD-FIX | `pair_run_schedule()` missing pair-10 branch; implementation site is not `run_recipe.py` |
| S2 | SHOULD-FIX | Nonce count check chain missing attempt-004 branch |
| S3 | SHOULD-FIX | Attempt-004 coordinator source bytes not pinned in `source_evidence()` |
| O1 | OPTIONAL | Reviewer question 1 resolved: extend is correct |
