# Architecture Review Log

Complete reconciliation of all 23 findings from Codex architectural attack (`codex exec`) against project contracts (`KICKOFF_PROMPT.txt`, `PREFLIGHT.md`).

## Reconciled Findings & Decisions

| Finding ID | Finding Description | Decision | Reason |
|---|---|---|---|
| ARCH-01 | `.gpu.lock` check suffers from race condition if not atomic | **ADOPTED** | Use atomic file creation (`os.open` with `O_CREAT \| O_EXCL`) in `run_recipe.py`. Record PID and timestamp. |
| ARCH-02 | Stale lockfile left behind if prior run crashed | **ADOPTED** | Implement stale lock check: verify holding PID is active; if dead, allow override with warning. |
| ARCH-03 | GPU idle preflight (< 1.5 GB VRAM allocated) baseline check | **ADOPTED** | Preflight check #2 queries `nvidia-smi` allocated memory and aborts if >= 1536 MiB. |
| ARCH-04 | Official pass gate requires second consecutive run (warm cache) | **ADOPTED** | Distinguish cold run (`PASS (cold)`) from official `PASS`. Only a passing 2nd consecutive run with peak VRAM <= 14.5 GB yields official `PASS`. |
| ARCH-05 | Suite mode VRAM creep detection blind spot if post-clip baseline grows | **ADOPTED** | Multi-clip suite runner tracks both clip peak VRAM and post-clip resting allocated VRAM; flags `VRAM creep = True` (FAIL) if baseline climbs. |
| ARCH-06 | SageAttention silent noise landmine for MiniMax H3 (Check 9) | **ADOPTED** | Check GET `/system_stats` or server boot flags; abort H3 runs if SageAttention is enabled. Mark H3 runs with `eyeball_verification: pending`. |
| ARCH-07 | Estimation formula for affordability check before first-ever run | **REJECTED** | Simple estimate formula (`weights_gb + (res_w * res_h * frames * 1e-6)`) is kept simple as safety guard until first measured run replaces it. |
| ARCH-08 | Automated model downloading when model missing from manifest | **REJECTED** | Explicitly forbidden by Hard Rule #4. Missing models result in `BLOCKED` status, never an automated download. |
| ARCH-09 | PID spoofing / race during stale lock file deletion | **ADOPTED** | Validate process start time alongside PID to avoid stale PID recycling races. |
| ARCH-10 | Async polling loop starvation & loss of peak VRAM sampling during long renders | **ADOPTED** | Poll `nvidia-smi` on dedicated high-priority daemon thread with 1.0s interval. |
| ARCH-11 | Output file verification checking non-zero size but not image format validity | **ADOPTED** | Check file existence, non-zero length, and verify header/signature bytes (PNG/MP4 header). |
| ARCH-12 | MiniMax H3 passing machine gate despite requiring human review | **ADOPTED** | Add `eyeball_verification: pending` flag on H3 results ledger entries. |
| ARCH-13 | Workflow node API `class_type` vs UI `widgets_values` validation ambiguity | **ADOPTED** | Validate prompt structure submitted to `/prompt` endpoint against `/object_info` input specs. |
| ARCH-14 | Manifest model name verification checking basenames without cryptographic hash | **REJECTED** | File name cross-checking against `models_manifest.md` matches prompt API contract requirements. |
| ARCH-15 | Network isolation checking for custom nodes calling external APIs | **ADOPTED** | Enforce 100% offline rule in preflight by verifying offline environment flags. |
| ARCH-16 | Multi-clip suite manifest specification ambiguity | **ADOPTED** | Define explicit suite sequence ordering for smoke and suite validation passes. |
| ARCH-17 | Certification bypass where smoke pass is reported as suite pass | **ADOPTED** | Maintain explicit `SMOKE_PASS` vs `SUITE_PASS` statuses in ledgers. |
| ARCH-18 | Creep measurement order dependency across heterogeneous recipes | **ADOPTED** | In suite mode, measure creep using identical sentinel clips placed at fixed intervals. |
| ARCH-19 | Creep threshold sensitivity to driver memory management jitter | **ADOPTED** | Require post-clip settle delay (2.0s) before taking resting memory measurement for creep evaluation. |
| ARCH-20 | Capability scope resolution across T2I, T2V, I2V, Audio | **ADOPTED** | Clarify scope: recipes contain terminal render stage only; T2I seed pair proves runner loop. |
| ARCH-21 | High recipe knob comparison vs Low recipe knob verification | **ADOPTED** | Require `recipes/<name>_high.json` to have equal or higher resolution/steps/precision than `_low.json`. |
| ARCH-22 | Preflight check unit testing & abort verification | **ADOPTED** | Implement preflight unit test suite asserting zero API prompt submissions on preflight failure. |
| ARCH-23 | Poisoned server state after CUDA OOM error | **ADOPTED** | Require server restart/re-check if CUDA OOM occurs before queueing subsequent recipes. |
