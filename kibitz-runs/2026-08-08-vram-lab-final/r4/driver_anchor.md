VERDICT: yes-with-fixes. The plan has converged; implementation remains blocked only by the explicitly named coordinator/receipt/topology/mux/timing gates.

MUST-FIX BEFORE BUILD:
1. [P2/P7] Implement and race-test the unified coordinator lease before any GPU run. No environment-only authorization, two-lock check sequence, or delete-and-recreate stale recovery may remain.
2. [P7] Implement exclusive monotonic child archives, atomic aliases, unique under-lock suite receipts, exact canonical sequence and pair/sentinel/server continuity. Suite receipt validation must replay those invariants, not trust booleans.
3. [P7] Make live lane pinned-memory and installed-schema commit checks bidirectional; make exact mode-specific absent sockets and node sets enforceable.
4. [P5] Implement/test the separate original-source mux receipt and elementary-video hash equality before calling matrix outputs delivery previews.
5. [P8] Implement/test Mini Mime target/delivered timing fields and one-frame media gate before its one render.
6. [P7/P9] Make confirmed server shutdown part of final suite PASS and write final evidence before coordinator release.

SHOULD-FIX:
1. [P4] Rerun full tests, paper validator, Codex review and owned live `/object_info` validation after the fixes; freeze code before matrix execution.
2. [P7] Rename candidate roles from cold/warm to first/repeat where physical cache coldness is not established, while retaining the repository's second-consecutive warm certification field.

OPTIONAL / NICE-TO-HAVE:
- Blinded human matrix review and motion-energy analysis remain post-render aids, never gates.

CUT THESE:
1. No new LTX T2V render.
2. No R2V Mini Mime before human I2V approval.
3. No portability refactor, runtime audio normalization or model-cache free endpoint.

VERIFY-AT-BUILD checklist:
- owned port 8199 and exact server PID/create-time;
- dynamic-combo dotted inputs against live `/object_info`;
- same server instance and exact run counters across H3 suite;
- stale/collision/concurrent lock tests;
- source remux elementary video hash equality;
- Mini Mime 90-frame/3.750-second delivered timing;
- shutdown refusal/termination failures produce FAIL and preserve evidence;
- no locks, listener or lab process remain after completion.
