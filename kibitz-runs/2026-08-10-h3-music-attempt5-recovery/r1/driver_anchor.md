# Driver anchor — round 1

The active driver inspected `AGENTS.md`, `run_recipe.py`, `scratch/run_h3_unconditioned_music_campaign.py`, the attempt-004 lifecycle, the pair-10 receipt, and its Manager/server log. The failure is a runner deadline during post-sampling decode/save, not VRAM, a model exception, or an offline-policy failure.

Hard boundaries for review:

- No cloud, network, downloads, installs, OTR access, port 8188 access, or parallel GPU work.
- Attempt-004 bytes are immutable. Pairs 1-9 must be carried, never rerendered.
- Pair 10 run 1 is a failed historical receipt with no artifact. A valid retry needs a new-server cold run 2 and immediate warm run 3 because `run_recipe.next_run_state` resets `config_run_count` when the runner identity changes.
- Pair 11 needs run 1/run 2. Exactly four new legs are authorized.
- The global runner currently hard-codes `RUNNER_COMPLETION_TIMEOUT_S = 1800` inside `main`; no timeout argument exists.
- Existing campaign verification supports explicit cold/warm roles and arbitrary monotonic run schedules, but its recovery modes stop at attempt-004 and its pristine-history helper only special-cases the earlier pair-1 recovery.
- Attempt-004 lifecycle is terminal and clean at row 65. Its operator launch receipt is absent because the process failed; stdout/stderr are preserved.
- A retry must remain fail-closed, append-only, Manager-offline, Sage-free, sequential, and owned-server-only.

Judge the proposed plan against the real repository. Prefer the smallest design that preserves the existing evidence contracts. Identify concrete source anchors and required tests. Do not propose executing a render, deleting evidence, touching foreign servers, or weakening verification.
