# Driver judgment — scoped r4

## Accepted and confirmed

1. Both reviewers correctly identify that “token-aware” needs an exact Windows
   argv algorithm. `run_recipe.py` currently performs unrestricted substring
   matching across every argument. The fix will inspect process/executable
   identity plus the actual Python script/module target, including absolute
   Windows paths, while ignoring unrelated later arguments.
2. Claude correctly identifies a direct contract contradiction:
   `prequeue_known_workload_scan_contract()` still says
   `python_without_readable_argv_blocks: true`. It must become false when
   unreadable Python is advisory.
3. Claude correctly identifies that the current prequeue exception embeds the
   full blocker dictionaries, including complete command lines. The same
   redacted structured format must be used by preboot and prequeue failures.
4. Antigravity correctly requires unreadable Python to live in a separate
   advisory collection; `_idle_evaluate_sample` must evaluate only positively
   classified blockers.
5. Both reviewers correctly require the existing exact current-runner and
   owned-server exclusions to occur before the shared classifier.

## Accepted with refinement

1. Blocker command-line hashing will use canonical JSON bytes for the argv list,
   not space-joined text, so token boundaries are unambiguous. The structured
   evidence retains the full 64-hex SHA-256; human exception text may stay
   compact without weakening the retained value.
2. Script markers (`main.py`, `run_recipe.py`) match the actual Python script
   target basename after Windows/POSIX path normalization. Engine/tool markers
   match process name, executable basename, or the actual script/module target;
   arbitrary later arguments never participate.
3. Tests belong in the existing focused file
   `tests/test_runner_idle_manager_scopes.py`, not the reviewer-suggested
   `tests/test_runner_provenance.py`.

## Rejected

1. Antigravity’s optional `--inspect-idle-scan` flag adds new runtime surface
   and is unnecessary once failed evidence is retained. Rejected.
2. Claude’s proposed live torch allocation probe would deliberately start a
   compute workload and conflicts with the operator’s instruction to stop
   wasting time on desktop-idle strictness. Unknown Python remains advisory by
   explicit operator ruling; actual OOM/14.5 GiB peak is the render outcome.
3. Truncating retained SHA-256 values to 12 hex characters weakens durable
   audit identity for no material benefit. Rejected for retained evidence.
4. A broad desktop/process allowlist is unnecessary and fragile. Rejected.

## External calls actually made

- One scoped round: `r4` only.
- Antigravity CLI: one successful call (`gemini-3.6-flash-high`).
- Claude Code CLI: one successful call (`sonnet`, high effort).
- Omitted by explicit scope: `r1`, `r2`, `r3`, and duplicate Codex CLI lane.
- No quota/credit failure was reported; usage percentages were unavailable.
