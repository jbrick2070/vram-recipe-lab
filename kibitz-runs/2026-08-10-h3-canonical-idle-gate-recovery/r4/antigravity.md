VERDICT: build-ready as-is? yes-with-fixes. The token-aware classifier rules, unreadable Python data schema, and redacted error formatting require explicit disambiguation to prevent incompatible builder implementations and prequeue server exclusion regressions.

MUST-FIX BEFORE BUILD:
1. [Section 4, Item 1 & Item 4] Ambiguous Token Classification Rules & Prequeue Exclusion Regression Risk
   - Defect: Section 4 Item 1 proposes "token-aware workload classification" without specifying token parsing rules or distinguishing script target paths from option flags/values. Furthermore, applying this to `collect_prequeue_known_workload_scan` (Section 4 Item 4) risks flagging the running owned server process as a foreign blocker if the classification helper does not explicitly accept multiple allowed PIDs (current runner PID and owned server PID).
   - Concrete Fix: Define a shared helper `_is_positive_workload_match(process_info, excluded_pids)` in [run_recipe.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/run_recipe.py#L2594) that accepts a set of `excluded_pids`. Parse `cmdline` into argument tokens; locate the target script/binary token (token 1 after python executable, or token 0 for standalone binaries). Match script markers (`run_recipe.py`, `main.py`, `torchrun`, `vllm`, `ollama`, `automatic1111`, `invokeai`) using `Path(token).name.lower() == marker`. Match engine/model markers (`eng_wan_`, `eng_fastwan_`, `eng_humo`, `minimax`, `diffusers`, `stable-diffusion`, `text-generation`) strictly against the executable name or target script path/name, explicitly ignoring option flags (`--*`) and positional arguments after `--`.

2. [Section 4, Item 3] Undefined Redacted Blocker Summary Schema and SHA-256 Input Standard
   - Defect: Section 4 Item 3 requires a "deterministic redacted blocker summary" including `command-line SHA-256` in raised errors, but does not define the string format for `quiescence_errors` or the exact byte input encoding for SHA-256, creating build-blocking ambiguity for exception formatting and unit test assertions.
   - Concrete Fix: Explicitly specify SHA-256 computation as `hashlib.sha256(" ".join(cmdline).encode("utf-8")).hexdigest()` in [run_recipe.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/run_recipe.py#L2656). Format `quiescence_errors` blocker entries strictly as: `f"blocked process PID {pid} ({exe_basename}): matched workload '{token}' via {match_basis} (create_time={create_time}, cmdline_sha256={sha256[:12]})"`.

3. [Section 4, Item 2] Unreadable Python Advisory Data Schema Unspecified
   - Defect: Section 4 Item 2 specifies treating unreadable Python identity as "recorded advisory evidence, not a known render/compute workload", but does not specify the dict key schema returned by `_idle_forbidden_process_scan`. If unreadable Python processes are not separated from `blocking_processes` in the returned dict, `_idle_evaluate_sample` will still append them to `errors`.
   - Concrete Fix: Update `_idle_forbidden_process_scan` in [run_recipe.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/run_recipe.py#L2594) to return `{"blocking_processes": [...], "advisory_unreadable_processes": [...], "excluded_runner": [...]}`. Update `_idle_evaluate_sample` in [run_recipe.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/run_recipe.py#L3331) to evaluate ONLY `blocking_processes` as blocking errors, while recording `advisory_unreadable_processes` in the sample dictionary for audit retention without raising `GpuIdleGateError`.

SHOULD-FIX:
1. [Section 4, Item 5] Standardize Test Mocking Location and Strategy
   - Defect: Item 5 specifies mocked unit tests for process scanning, but omits the target file location and `psutil.process_iter` mock fixture structure.
   - Concrete Fix: Add tests to [tests/test_runner_provenance.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/tests/test_runner_provenance.py) using `@unittest.mock.patch("psutil.process_iter")` returning mock process objects with controlled `info` dictionaries (`pid`, `name`, `exe`, `cmdline`, `create_time`).

OPTIONAL / NICE-TO-HAVE:
1. [Section 4, Item 3] Add an advisory CLI diagnostic flag `python run_recipe.py --inspect-idle-scan` to print live process classification results to stdout without raising preflight exceptions during troubleshooting.

CUT THESE:
1. [Section 4, Item 3] Full 64-character SHA-256 strings in exception messages. Truncating SHA-256 to 12 hex characters (`sha256[:12]`) in error output is safe to cut and prevents bloated error logs while maintaining audit traceability [ASSUMPTION].

VERIFY-AT-BUILD checklist:
- [ ] **Token Classification Precision**: Run unit tests in [tests/test_runner_provenance.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/tests/test_runner_provenance.py) to confirm CLI options containing marker text (e.g. `--prompt "minimax test"`) do NOT trigger `GpuIdleGateError`.
- [ ] **True Blocker Detection**: Confirm that launching an independent `python main.py` or `python run_recipe.py` process triggers `GpuIdleGateError` with redacted PID, create_time, and matched token in stdout.
- [ ] **Unreadable Python Non-Blocking**: Confirm an unreadable Python process (`cmdline=[]`) populates `advisory_unreadable_processes` without blocking preboot or prequeue gates.
- [ ] **Prequeue Owned Server Pass-Through**: Confirm `collect_prequeue_known_workload_scan` in [run_recipe.py](file:///C:/Users/jeffr/Documents/ComfyUI/vram-recipe-lab/run_recipe.py#L2901) succeeds when the owned ComfyUI server process is running on port 8199.
- [ ] **SageAttention-Free & Port 8199 Invariants**: Confirm server boot scripts use port 8199 and maintain `SAGE_ATTENTION=0` per domain profile.
- [ ] **14.5 GiB VRAM Peak Limit**: Confirm peak VRAM usage during campaign execution remains within the 14.5 GiB review budget per local profile `.kibitz/comfyui.local.md`.
- [ ] **Durable Transport Hash Re-Freeze**: Confirm runner script and coordinator hashes are re-frozen and verified before initiating a new campaign ID.
