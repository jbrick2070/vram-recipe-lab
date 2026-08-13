# H3 unconditioned-music attempt-005 recovery plan

## Outcome

Complete the existing 11-pair study without rerendering pairs 1-9. Preserve every attempt-004 byte, treat pair 10 run 1 as an immutable failed historical execution, and execute exactly four new legs: pair 10 cold/warm followed by pair 11 cold/warm. Human music and motion judgments remain `PENDING_HUMAN`; the recommendation remains HOLD pending Jeffrey's eyes/ears.

## Ground truth and boundary

- Attempt id: `h3music-20260810T023023Z-97ca44b2-attempt-004`.
- Terminal lifecycle: 65 rows, 1,513,119 bytes, SHA-256 `1fb0ea686f0acd30e83e2f294d717afebf471381b3eb9d2138a12f6a10734c69`; final event SHA-256 `b66526982583393059c25d6c67cad3b8fdae4a51239111dc19d15681c14df80f`.
- Verified study evidence: pairs 1-9 (18 valid legs). Pairs 1-2 were carried; pairs 3-9 were executed by attempt-004.
- Pair 10 run 1 receipt/alias SHA-256: `4ab72334bc80d8155d1b1d1466258922a7a9e1ad2e289f37b07a510115d164bf`. It timed out at 1,800 seconds after sampling reached 20/20, during decode/save; no artifact exists. Its Manager log is 22,893 bytes, SHA-256 `22d1e7264febfe962cbda12f9365fc633f28af2cb9c079fc253138f5698edfb1`.
- Attempt-004 ended in a clean state: no 8199 listener, PID receipt, GPU/suite lock, or quarantine.

## Proposed implementation

1. Before editing any source pinned by attempt-004, publish an O_EXCL attempt-004 recovery receipt. It must revalidate the complete 65-row hash chain and terminal failure, the original source bytes, pairs 1-9 from their historical lifecycle/source sets, Manager logs, receipts and artifacts, pair 10 run 1 and its lack of artifact, the preserved operator stdout/stderr, and the absence of attempt-004 `launch.json`. It must not invent launcher-observed timestamps or reclassify attempt-004 as successful.
2. Add a fail-closed runner CLI option for the completion window, defaulting to the existing 1,800 seconds. Accept one integer exactly once in a bounded range up to 7,200 seconds and record the selected value in each receipt. Attempt-005 passes 3,600 seconds for pair 10 and 5,400 seconds for pair 11; all ordinary callers retain 1,800 seconds. Add focused parser/default/receipt tests.
3. Add an attempt-005 recovery mode to the existing H3 campaign coordinator (preferred over a parallel ad-hoc renderer). Give it an exact new campaign id, exact launcher/recorder paths, exact attempt-004 lifecycle/recovery pins, and require a clean owned-lab state before appending any attempt-005 lifecycle row.
4. Carry pairs 1-9 with zero executions. Pair 10 schedule is run 2 cold/config 1 and run 3 warm/config 2, allowed receipts 1-3, preserving failed run 1. Pair 11 remains run 1 cold/config 1 and run 2 warm/config 2. Use four unique attempt-005 executor nonces.
5. For each new pair, use the existing Manager-offline, Sage-free, reserve-12 GB lane and the existing cold-then-immediate-warm server lifecycle. The warm child owns verified shutdown. Never use `--force`; never touch 8188 or OTR.
6. Preserve attempt-004 operator stdout/stderr without manufacturing a success receipt for it. Create a new attempt-005 operator directory atomically; on terminal exit, create a launch receipt bound to process identity, argv, stdout/stderr identities, the lifecycle hash chain, and the terminal event.
7. Success requires 11 fully verified pairs, 22 valid study legs, exactly 4 new executions, clean shutdown after both new pairs, final audit entries for all pairs, Manager offline proof for each executed pair, and no unexpected receipts/artifacts/logs. The failed pair-10 run 1 is historical non-study evidence, not a cold leg.
8. On any failure, append a terminal failure row, preserve all bytes, clean up only a positively owned server, and stop without another render.
9. Only after success, update `docs/H3_UNCONDITIONED_MUSIC.md`, `RESULTS.md`, and `ENGINE_MATRIX_BETA.md` from receipts. Leave every qualitative field `PENDING_HUMAN` and the recommendation HOLD.

## Reviewer questions

- Is extending the existing coordinator safer than a dedicated attempt-005 coordinator importing its verification helpers?
- Does changing `run_recipe.py` correctly force pair 10 run 2 to reset to configuration count 1, then run 3 to configuration count 2?
- Which missing fail-closed checks could permit duplicate renders, history drift, operator-receipt ambiguity, or an unowned server action?
- Is 3,600 seconds a defensible bounded timeout after a 29:06 sampling phase, or should the explicit bound differ?
