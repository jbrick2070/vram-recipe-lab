VERDICT: no — the proposed direction is sound, but the current implementation is not runnable because count-only failure evidence and substring classification can repeat the same false stop without identifying its cause.

MUST-FIX BEFORE BUILD:
1. [Repeated local evidence / Relevant code] CONFIRMED — `run_recipe.py::_idle_forbidden_process_scan` searches workload markers as arbitrary substrings across every command-line argument, so review/control-plane text can be misclassified as a live renderer. Use one shared token-aware classifier with an explicit match basis (exact resolved script path, executable identity, or narrowly defined tool token), not free-text substring presence.
2. [Repeated local evidence / Proposed correction 3] CONFIRMED — `check_gpu_idle()` throws a flattened count and loses the retained blocker objects. The two immutable stdout logs therefore cannot identify the process. Emit a deterministic redacted blocker summary before raising; include enough PID/create-time/match-basis evidence to verify or reject the classification on the next stop.
3. [Proposed correction 2] CONFIRMED — unreadable Python is unknown, not positively identified render/compute. Under the operator's latest rule it must be recorded but cannot alone block. Exact foreign renderer identity, numeric NVIDIA compute allocation, and ownership failures remain blocking.
4. [Proposed correction 4] CONFIRMED — cold preboot and immediate prequeue currently have separate process-scan implementations. They must call the same classifier or the cold gate can accept what prequeue rejects (or vice versa).
5. [Proposed correction 6] CONFIRMED — both failed campaign/operator receipts must remain immutable, and a future run needs a new campaign/operator ID because neither failed attempt has a complete pair to carry.

SHOULD-FIX:
1. [Proposed correction 3] CONFIRMED — redact arbitrary command-line values. Retain PID, create time, name/executable basename, matched token, match basis, and command-line SHA-256; this is diagnostic without copying unrelated secrets into durable logs.
2. [Proposed correction 5] CONFIRMED — add a regression fixture where a harmless CLI argument literally mentions `run_recipe.py`, `main.py`, and `minimax`; it must remain advisory while exact executable/script identities still block.

OPTIONAL / NICE-TO-HAVE:
- Record the current zero-blocker read-only rescan as contextual evidence only; it cannot reconstruct the transient historical blocker.

CUT THESE:
1. Do not add a broad desktop-app allowlist. Positive workload identity plus advisory unknowns is smaller and matches the operator ruling.
2. Do not add another VRAM/utilization threshold. The operator explicitly made baseline/utilization descriptive and actual OOM/14.5 GiB peak authoritative.

VERIFY-AT-BUILD checklist:
- CONFIRMED: first and second attempts contain zero prompts, receipts, artifacts, Manager logs, or server descendants.
- Verify mocked exact-path classification for foreign `run_recipe.py` and ComfyUI `main.py`.
- Verify marker text in unrelated arguments does not block.
- Verify a true blocker stops before `/prompt` and emits redacted structured evidence.
- Verify no port-8188 or OTR surface is introduced.
- Verify final source pins, UTF-8/no BOM, durable transport dry plan, and fresh-ID absence before launch.
