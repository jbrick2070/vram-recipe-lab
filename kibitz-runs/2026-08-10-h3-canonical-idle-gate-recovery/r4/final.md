# Final scoped r4 recovery plan

1. Add one shared positive-workload classifier used by cold preboot and
   immediate prequeue scans.
   - Exclude only the exactly re-proved current runner first; prequeue also
     excludes the exactly re-proved owned port-8199 server first.
   - For Python, identify the real script/module target while honoring
     interpreter flags. Match `main.py` and `run_recipe.py` by target basename,
     including absolute Windows paths.
   - Match other workload markers only against process name, executable
     basename, or the actual script/module target. Ignore arbitrary later argv
     values, review prompts, filenames passed as data, and option values.
2. Split scan results into `blocking_processes` and
   `advisory_unreadable_processes`. Unreadable/unknown Python is recorded and
   non-gating. Positively matched foreign render/compute identities remain
   blocking.
3. Change the stable contract to state unreadable Python is advisory. Retain
   the operator’s non-gating baseline/utilization/drift policy and exact
   elevated-baseline stamp.
4. Replace raw command-line retention/error output with one deterministic
   redacted schema: PID, create time, process/executable basename, target
   basename, matched marker(s), match basis, and SHA-256 of canonical JSON argv
   bytes. Use it in both preboot and prequeue errors.
5. On a blocked five-sample cold gate, include deduplicated redacted blocker
   evidence in the raised error so the immutable operator stdout identifies the
   cause. Do not write or overwrite a run receipt for a prompt that never
   queued.
6. Add focused mocked tests:
   - exact foreign absolute-path `run_recipe.py` and ComfyUI `main.py` block;
   - exact engine/tool target blocks;
   - marker text in unrelated CLI/review/data arguments does not block;
   - unreadable Python is retained as advisory;
   - current runner and owned server exclusions stay exact;
   - preboot and prequeue errors are redacted and diagnostic;
   - a true blocker prevents `/prompt`.
7. Rebuild source pins and recipe receipt contracts, then run runner,
   canonical, follow-up, packager, and transport suites plus read-only plans.
8. Preserve both zero-render failed attempts. Launch exactly one new campaign
   and operator ID after clean lock/PID/sidecar/listener checks. Do not reuse or
   overwrite prior evidence.

This is the final output of an explicitly scoped one-round r4 review, not a
four-round Kibitz campaign.
