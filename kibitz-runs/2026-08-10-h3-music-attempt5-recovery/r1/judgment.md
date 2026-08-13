# Driver judgment — round 1

One Claude Code reviewer ran successfully. The driver checked every actionable claim against the repository.

Accepted:

- `ensure_pristine_pair()` must gain an exact pair-10 attempt-005 branch; its current fallback rejects any existing receipt.
- `expected_operator_campaign_argv()`, process identity validation, transport validation, and their attempt labels are attempt-004-specific.
- Attempt-005 receipts must expose and verify the selected completion window while historical receipts remain valid.
- `pair_run_schedule()` needs the pair-10 run2/run3 branch, and the runbook nonce/count logic needs an exact four-leg branch.
- The historical attempt-004 campaign source needs an embedded literal byte/hash pin in the recovery recorder before that source is edited.
- Extending the existing coordinator is the lower-drift design.

Accepted with correction:

- Name the new transport files explicitly, but the attempt-004 recovery receipt does not depend on them. It pins historical attempt-004 sources first; attempt-005 source evidence pins the new launcher/recorder later.
- Keep receipt schema version 3. The current history audit admits schema 3 and does not require an exact key set. `completion_timeout_s` is a backward-compatible field that the attempt-005 verifier requires only for new legs.

Rejected/misread:

- Attempt launchers and recorders do not live inside `results/.../operator_logs`; they live under `scratch/`. The operator directory contains only stream logs and, on a completed wrapper, `launch.json`.
- The verification helpers are importable; prior recovery recorders already load and use coordinator evidence. Their coupling still favors extending the coordinator, but non-importability is not the reason.

No second CLI reviewer is needed. The review produced concrete, repo-confirmed corrections.
