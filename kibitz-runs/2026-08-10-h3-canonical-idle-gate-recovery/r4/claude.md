VERDICT: yes-with-fixes. Three defects block a safe build: the token-aware
classifier is under-specified in a way that a naive implementation would miss
ComfyUI on Windows paths; the contract field contradicts the proposed advisory
treatment of unreadable Python; and the prequeue error path exposes full
command lines, opposite to the stated redaction goal.

---

MUST-FIX BEFORE BUILD:

1. [§Proposed correction, item 1] Token-aware matching is under-specified for
   absolute Windows path arguments.

   The current code (run_recipe.py:2646) concatenates name+executable+cmdline
   and checks `marker in text`. On Windows, a ComfyUI process invoked as
   `python C:\ComfyUI\main.py --port 8199` produces the argv element
   `C:\ComfyUI\main.py`. Under whitespace-split + exact-equality (one plausible
   reading of "token"), none of the tokens equals `main.py`, so ComfyUI would
   NOT be blocked -- the opposite of the plan's intent. Under path-component
   split (split each element on / and \), `main.py` is a component and DOES
   match. Two valid readings of "token-aware" produce incompatible results for
   the most common real invocation.

   The plan must specify the algorithm precisely. Minimum required text:
   "For markers that are .py filenames (`main.py`, `run_recipe.py`): match when
   any argv element, after splitting on both / and \ path separators, has a
   basename equal to the marker (case-insensitive). This is consistent with
   `_idle_command_line_has_exact_runner` (run_recipe.py:2518-2529). For
   non-filename markers (`minimax`, `eng_wan_`, `vllm`, `torchrun`, etc.):
   match on executable path components and process name only; arbitrary argv
   arguments beyond the script position are excluded."

   Without this the test in item 5 ("marker text inside unrelated CLI argument
   does not block") cannot be correctly implemented because the test itself
   depends on which tokenization is used.

2. [§Proposed correction, item 2 and item 4] `prequeue_known_workload_scan_
   contract()` (run_recipe.py:2218-2240) contains `"python_without_readable_
   argv_blocks": True` at line 2236. Making unreadable Python advisory without
   changing this field produces a contract that is a lie about actual behavior.

   The contract is embedded verbatim in every run receipt and validated by
   `prequeue_known_workload_scan_validation_errors` (run_recipe.py:2851):
   `if evidence.get("contract") != prequeue_known_workload_scan_contract()`.
   New receipts will embed a contract claiming True while the code behaves as
   advisory. The plan must explicitly add: change
   `python_without_readable_argv_blocks` to `False` in
   `prequeue_known_workload_scan_contract()`, and update the docstring.

   Note: `gpu_idle_gate_contract()` at line 2184 auto-updates its
   `collector.sha256` when the source file changes, so that part is automatic.
   Only the explicit key at line 2236 requires a manual change.

3. [§Proposed correction, item 3 and item 4] The prequeue scan
   (`collect_prequeue_known_workload_scan`, run_recipe.py:3059-3063) already
   dumps the raw `blockers` list in the `PreflightError` message:
   `f"blocking_processes={blockers}; scan_errors={scan_errors}"`. That list
   includes unredacted `command_line` fields from lines 3014-3016.

   The plan's item 3 says "include a deterministic redacted blocker summary...
   command-line SHA-256" -- but only explicitly says "in the raised error" for
   the preboot path (which currently has count-only at line 3360-3362). A
   builder following item 3 literally would fix the preboot path (too sparse)
   and miss the prequeue path (too verbose / unredacted).

   The plan must state: apply the same redaction format (PID, create time,
   process basename, matched token, match basis, cmdline SHA-256) to BOTH the
   `GpuIdleGateError` raised in `check_gpu_idle` AND the `PreflightError`
   raised in `collect_prequeue_known_workload_scan`. The existing prequeue
   format exposes full command lines and must be replaced, not supplemented.

---

SHOULD-FIX:

4. [§Proposed correction, item 2] No verify step that the NVIDIA blocking_rows
   check is a sufficient backstop for GPU-active Python processes on WDDM.

   The plan removes the hard block on unreadable Python and says numeric NVIDIA
   compute allocation still blocks (via `process_evidence.get("blocking_rows")`
   in `_idle_evaluate_sample`, run_recipe.py:3345-3349). But on Windows WDDM,
   GPU-active Python processes may not appear in `nvidia-smi
   --query-compute-apps` output -- WDDM can classify GPU use as graphics/display
   rather than compute. The prior false-positive fix (attempt 1 vs. attempt 2)
   shows WDDM row classification on this system is already non-trivial.

   If an unreadable Python process IS consuming GPU memory under WDDM and is
   not emitting a compute row, the advisory-only change silently passes it
   through. Add a verify step: "Confirm at build/first-run time that a
   GPU-active Python process appears in `blocking_rows` before releasing the
   unreadable-Python hard block." If it does not, the advisory-only change is
   unsafe on this hardware.

5. [§Proposed correction, item 1 -- secondary] For short, non-.py markers
   (`minimax`, `eng_wan_`, `kobold`, `vllm`): the plan says "an unrelated CLI
   argument or review prompt merely mentioning minimax does not block," but does
   not state whether these markers match on argv beyond the script position.

   A Windows service named `MiniMaxVideoRenderer` in its display description
   would NOT appear in executable path components, but could appear in
   command-line arguments that an external orchestrator uses to invoke it. The
   fix in item 1 should state explicitly: non-filename markers match on
   executable path components and process name only (same restriction as the
   .py markers after the script-position cut). This prevents a future marker
   addition from silently reverting to full-argv substring matching.

---

OPTIONAL / NICE-TO-HAVE:

- [§Proposed correction, item 3] The plan specifies "command-line SHA-256" for
  redaction. A BLAKE2b-based truncated hash would be faster and sufficient for
  diagnostic disambiguation, but SHA-256 is fine and consistent with the rest
  of the receipt hashing. No action required.

- [§Proposed correction, item 6] Explicitly note that the `collector.sha256`
  in `gpu_idle_gate_contract()` will change automatically because it is
  `sha256_file(runner)` (run_recipe.py:2184). This is not an error, but
  including it in item 6 would make it easier for the builder to confirm the
  re-freeze is complete (expected new hash is knowable before the campaign
  starts).

---

CUT THESE:

None. The plan is already lean. Every item addresses a real gap or a necessary
operational step.

---

VERIFY-AT-BUILD checklist:

VB-1. [MUST-FIX 1 follow-on] After implementing the classifier: run an
  isolated mock scan with a simulated process whose argv element is
  `C:\ComfyUI\main.py` (full Windows absolute path). Confirm it blocks. Run
  again with `python /path/to/review.py --input-file C:\docs\main.py` in argv.
  Confirm it does NOT block (because `main.py` appears only as a non-script
  argument). If the test fails, the path-component split is not working.

VB-2. [MUST-FIX 2 follow-on] After changing `python_without_readable_argv_
  blocks` to `False`: confirm `prequeue_known_workload_scan_contract()` returns
  the updated value. Confirm `gpu_idle_gate_validation_errors` catches
  evidence that embeds the old contract (True), so receipt replay of pre-change
  runs correctly reports contract drift.

VB-3. [MUST-FIX 3 follow-on] After adding redaction to both raise sites:
  confirm that a `PreflightError` (prequeue) and `GpuIdleGateError` (preboot)
  both contain the PID, basename, and matched token for a blocked process, and
  do NOT contain the full command-line string.

VB-4. [SHOULD-FIX 4] Before releasing the unreadable-Python advisory change:
  verify with `nvidia-smi --query-compute-apps=pid,used_gpu_memory
  --format=csv,noheader` that a GPU-active Python process (e.g., a brief torch
  tensor allocation) appears in the output on this WDDM machine. If it does
  not, the blocking_rows backstop is insufficient and the unreadable-Python
  advisory change should be reconsidered.

VB-5. [Pre-existing, now verifiable] Confirm both attempt receipts
  (`62915acd`, `62c5b419-attempt-002`) are immutable and have terminal failed
  lifecycle rows before starting a new campaign. Confirm the new campaign ID
  does not share prefix or reuse any field from either failed attempt.

---

[ASSUMPTION] The plan's "exact identity is unrecoverable" claim is taken at
face value -- the stdout for attempt 2 was confirmed to contain only the
count. No other retained evidence is assumed.

[ASSUMPTION] `_idle_command_line_has_exact_runner` (run_recipe.py:2518-2529)
is the intended reference implementation for path-resolution-based exact
matching. The plan does not cite it explicitly, but it is the only existing
example of the right approach in the codebase.
