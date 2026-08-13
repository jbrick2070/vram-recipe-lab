# Kibitz-scoped final — attempt-005 recovery

Proceed with one bounded recovery implementation:

1. Publish an O_EXCL attempt-004 recovery receipt while all attempt-004 source pins still match.
2. Add a default-preserving, bounded runner completion-timeout CLI and receipt field.
3. Extend the existing coordinator with exact attempt-005 mode, historical verification, nine carried pairs, pair-10 run2/run3, pair-11 run1/run2, and exactly four nonces/executions.
4. Add exact attempt-005 operator launcher and launch recorder.
5. Test dry-run and failure boundaries, then launch once and monitor to terminal state.

The implementation must explicitly update `ensure_pristine_pair()`, `pair_run_schedule()`, operator argv/process/transport validation, runbook counts, execution slicing, carry/final-audit branches, source pins, parser/main wiring, and success/failure counts. Historical receipts remain schema v3; only new receipts require the exact `completion_timeout_s` field. No qualitative judgment is authorized.
