# H3 canonical Job C idle-gate recovery — one-round review input

## Objective

Unblock Job C without weakening the operator's remaining rule: a positively
identified foreign render/compute workload must still stop prompt queueing.
Desktop VRAM baseline, utilization, and cold/warm baseline drift are advisory
only. Repository ownership, lock, port-8199, Sage-free, Manager-offline, and
14.5 GiB peak/OOM rules remain unchanged.

## Repeated local evidence

Two fresh campaign IDs stopped before server boot and before any prompt:

1. `h3canonical-20260810T171855Z-62915acd` reported one blocking NVIDIA row
   and one independent forbidden/unknown workload in each of five samples.
2. `h3canonical-20260810T183944Z-62c5b419-attempt-002` reported one
   independent forbidden/unknown workload in each of five samples after the
   NVIDIA WDDM false-positive fix.

Both attempts have immutable operator receipts and terminal failed lifecycle
rows. Both have zero Job C run receipts, zero Job C artifacts, no Manager log,
no server descendant, and clean lock/PID/sidecar/listener state. The second
attempt's retained stdout identifies only the blocker count; the structured
process evidence was discarded when `check_gpu_idle()` raised.

A read-only reproduction immediately after the second failure applied the
current marker scan to all live processes (excluding only the diagnostic
process) and found zero blockers. The blocker was therefore transient or was a
false-positive control-plane/unknown-process classification; its exact identity
is unrecoverable from retained evidence.

## Relevant code

- `run_recipe.py::_idle_forbidden_process_scan` scans every process and blocks
  when any marker is a substring of the concatenated name, executable, and all
  command-line arguments. It also blocks a Python process whose command line is
  unreadable.
- `run_recipe.py::_idle_evaluate_sample` turns any independent-scan blocker
  into a generic count-only error.
- `run_recipe.py::check_gpu_idle` retains rich per-sample process evidence only
  on success; on failure it raises a flattened `GpuIdleGateError` and the child
  exits without a run receipt.
- `run_recipe.py::collect_prequeue_known_workload_scan` repeats the scan on
  every cold/warm leg immediately before `/prompt`, with narrow exclusions for
  the current runner and verified owned lab server.

## Proposed smallest correction

1. Replace arbitrary substring matching with positive, token-aware workload
   classification. Exact script/executable/path tokens for known render tools
   block; an unrelated CLI argument or review prompt merely mentioning
   `run_recipe.py`, `main.py`, or `minimax` does not. Preserve the existing exact
   current-runner exclusion.
2. Treat unreadable/unknown Python identity as recorded advisory evidence, not
   a known render/compute workload. Malformed target-GPU identity, numeric
   NVIDIA compute allocation, a positively matched foreign renderer, port/lock
   ownership drift, and server identity drift still block.
3. When a sample blocks, include a deterministic redacted blocker summary in
   the raised error (PID, create time, process/executable basename, matched
   workload token and match basis, command-line SHA-256). This must make the
   operator stdout sufficient to diagnose another preboot stop without exposing
   arbitrary full command lines.
4. Apply the same positive-classification helper to cold preboot and immediate
   prequeue scans so they cannot disagree.
5. Add mocked tests for: exact foreign `run_recipe.py` and exact ComfyUI
   `main.py` block; marker text inside an unrelated review/CLI argument does not
   block; unreadable Python is advisory; exact owned runner/server exclusions
   remain narrow; failed five-sample evidence reports the redacted identity;
   no `/prompt` occurs on a true blocker.
6. Re-freeze runner, both campaign coordinators/builders/recipes, and durable
   transport hashes. Run the existing focused suites and a read-only plan.
   Start one new campaign ID only after clean ownership preflight. Never reuse
   or overwrite either failed attempt.

## Decision requested from the one-round panel

Find the smallest remaining defect or unsafe ambiguity in this correction.
Prefer a concrete token-aware classifier and auditable failure evidence over a
blanket process allowlist or disabling the known-workload gate.
