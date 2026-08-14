# Runner Division: dynamic lab front office

- **Status:** sealed direct dispatch implemented; the first cold plumbing smoke passed and the first sealed current-profile H3 native-A/V smoke is prepared
- **Date:** 2026-08-12, revised 2026-08-13
- **Repository snapshot:** `ca929db50556600607f3cf4be1c19e114aa5a421`
- **Purpose:** let the lab compare pinned ComfyUI environments without weakening the existing ownership, isolation, evidence, or GPU-safety rules
- **Machine-readable proposal:** [`../research/runner_division_front_office_2026-08-12.json`](../research/runner_division_front_office_2026-08-12.json)

## Executive decision

The present `run_recipe.py` is a strong **single-bench execution guard**. It owns port 8199, fails closed on unknown servers, freezes recipe/runner identity, validates `/object_info`, checks fixtures and media, monitors VRAM/RAM, and writes append-only receipts.

It is not yet the right **comparative-lab front office**. The ComfyUI root, Python environment, boot command, output directory, custom-node surface, and several core source hashes are hard-coded. Changing ComfyUI from 0.31.1 to 0.32.0 therefore cannot be isolated cleanly without changing runner identity and path assumptions.

The fix is a division of responsibility:

| Division | May decide | Must not decide |
|---|---|---|
| Front Office (`labctl.py`) | campaign, cell, pinned bench profile, run order | graph math, promotion verdict, arbitrary paths or shell text |
| Bench Registry (`bench_profiles/*.json`) | exact Python/ComfyUI/user/output/custom-node/model-manifest identity | runtime overrides, downloads, mutable aliases |
| Floor Runner (`run_recipe.py`) | validate and execute one sealed cell | choose its own bench or relax the sealed plan |
| Evidence Office | verify immutable receipts, paired comparisons, human-review bindings | queue work or rewrite source receipts |
| Promotion Desk | decide whether a passed result may be proposed to OTR | mutate OTR during a lab campaign |

The old runner is not discarded. Its safety machinery becomes the floor runner under a stricter, machine-readable front office.

### Historical static milestone (2026-08-12)

The repository now contains the safe, non-executing half of this design:
`front_office.py`, `labctl.py`, strict v1 profile/campaign schemas, one verified
`comfy0311-h3` bridge profile, sealed static launch specifications, derived
per-cell namespaces, an all-recipe offline census, and an immutable
`STALE_FOR_ACTIVE_RUNNER` display index. `labctl launch` fails closed with
`DIRECT_LAUNCH_NOT_INTEGRATED`; it cannot boot ComfyUI, acquire the GPU, or
queue a prompt.

This was intentional at the static milestone. The execution update below keeps
the historical profile and receipt bytes intact rather than relabeling them.

### Execution update (2026-08-13)

The Front Office now seals an execution specification and invokes the pinned
floor runner through a direct argument vector (`shell=False`). The floor runner
revalidates that specification before taking the existing global GPU lease or
touching port 8199. It owns the server, queue, `/object_info`, fixture,
measurement, append-only receipt, and cleanup machinery exactly as before.

The new dispatchable `comfy0320-h3` profile pins the actual clean ComfyUI
`0.32.0 @ c2bcbecd82ec5ae66594340b395c24ef0217b238` installation. Its
namespaces are distinct per campaign/cell/profile for outputs, results, logs,
user state, and ComfyUI's `--temp-directory` base. Every Front Office receipt
binds the profile, sealed launch specification, direct argv, sanitized
environment, runner/front-office bundles, and one-time execution claim.

Execution specifications are single-use and terminal: the current milestone
forces a fresh cold server, proves shutdown before writing a machine pass, and
marks the receipt cold-only. It cannot inherit a warm result or certify
warm-cache performance. The first allowed smoke is
`front-office-r1/t2i-low-smoke`, a `SaveImage` plumbing check; it does not
claim video or audio media-gate coverage.

The old `comfy0311-h3` profile remains historical and invalid against the
current root. `H3-C032` remains blocked: a separate, real 0.31.1 worktree and
profile plus a warm-session protocol are still required for the matched
comparison. No placeholder profile, model download, or OTR edit is authorized.

## Active 2026-08-12 mission scope

This proposal describes a larger eventual system. The active implementation is deliberately smaller: enroll only profile IDs that pin the Python executable, ComfyUI root/version/commit, custom-node whitelist/commits, model-paths config, and canonical argv; launch only direct argv subprocesses; bind profile identity and launch-spec hash into each new receipt; give every cell distinct output/result/log namespaces; and compute `STALE_FOR_ACTIVE_RUNNER` for old receipts without changing their bytes.

Preserve the current floor runner unchanged: port-8199 ownership, `.gpu.lock`, `/object_info` validation, fixture and media gates, VRAM monitoring, append-only receipts, and cleanup proof. The ACL-protected GPU-UUID mutex, model content-admission manifests, receipt-schema-v4 full field set, cross-clone contention tests, and recipe schema v2 are explicitly deferred until bench friction demonstrates a need.

`H3-LIP-TXT` is the one current-runner exception: after a fresh native control and an unambiguous transcript-window receipt, its prompt-only A/B may run before the front office. `H3-C032` remains behind the minimal enrolled-profile front office.

## Non-negotiable policy

1. Port remains literal `127.0.0.1:8199`; one coordinator and one GPU lease exist for the whole campaign cell.
2. No cloud endpoint, API key, automatic installer, model download, custom-node download, or registry refresh is permitted.
3. A bench profile contains resolved, explicit Windows paths. No profile value comes from inherited environment variables.
4. All selected paths must be existing absolute regular paths/directories, must resolve to themselves, and must not traverse a symlink, junction, or reparse point.
5. The profile pins the ComfyUI commit, Python executable, package-lock receipt, custom-node commits/source hashes, model-manifest hash, boot-policy hash, and expected core-source hashes.
6. The front office constructs an argument vector and launches Python directly. It never builds a shell command string.
7. The child environment is rebuilt from a small allowlist. Inherited `LAB_*`, `COMFY*`, `PYTHONPATH`, CUDA allocator, proxy, and attention variables are rejected or cleared unless the profile declares their exact value.
8. The server PID receipt binds the campaign, cell, profile ID/hash, launch-spec hash, nonce, process creation time, listener PID, canonical argv, Python executable, ComfyUI root, user directory, and output directory.
9. A runner, profile, recipe, fixture, node source, model admission receipt, or server-identity change during a cell invalidates the cell.
10. Historical receipts remain immutable historical evidence. They are not same-surface controls for a new runner/profile identity.
11. The H3 boot argv remains free of global Sage flags. The one admitted Sage experiment may use a per-model graph patch only when its campaign cell explicitly names that node and mode.
12. The lab never edits OTR. Promotion produces a proposal and evidence bundle only.

The coordinator must ultimately be a fixed, ACL-protected OS mutex keyed by the verified NVIDIA GPU UUID, not a lock path beneath a selectable environment or repository clone. This prevents two clones from each believing they own the same physical GPU.

### Security boundary

These controls prevent accidents, drift, and false attribution; they do not sandbox arbitrary Python or native code running as Jeffrey's Windows user. An untrusted ComfyUI root, custom node, Python environment, or graph is executable code. Community environments are inspect-only until source-reviewed and enrolled. Anything intentionally untrusted must run under a disposable low-privilege OS sandbox/VM with networking denied and no access to OTR, private documents, credentials, or trusted model stores.

Recipe JSON is executable policy too. The front office accepts only pinned recipes under a trusted non-reparse root and enforces an allowed node/input/resource contract. A downloaded community graph is evidence for topology, never a directly executable campaign cell.

## Proposed repository surface

```text
labctl.py                         front-office CLI
runner_engine.py                  sealed-profile resolution and direct launch
bench_profiles/schema-v1.json    strict profile schema
bench_profiles/comfy0311.json    frozen bridge bench
bench_profiles/comfy0320.json    frozen candidate bench
campaigns/*.json                 paired cell matrices and gates
.runtime/                         ephemeral nonce-bound launch specifications
results/runs/<campaign>/<cell>/  immutable receipt archives
results/current/<campaign>/      replaceable aliases for that campaign only
outputs/<campaign>/<cell>/       derived, cell-scoped artifacts
comparisons/<campaign>/          deterministic comparison documents
```

`boot_lab_server.cmd` remains a legacy single-bench launcher until parity is proven. The dynamic path should launch `python.exe`, `main.py`, and each argument as a subprocess list so quoting cannot change the command.

## Bench profile contract

The profile is an attestation, not a convenience preset. A profile should contain at least:

| Field | Required meaning |
|---|---|
| `id`, `schema_version` | stable identifier and strict schema |
| `python_executable` | exact venv interpreter path plus admission SHA/version receipt |
| `comfyui_root` | exact checkout path, version, full commit, clean/approved-dirty state |
| `user_directory` | bench-specific state directory; never Jeffrey's interactive instance |
| `output_root` | derived lab-owned namespace, never supplied by the recipe |
| `model_paths_config` | exact file path and SHA-256 |
| `model_manifest` | exact admission ledger and SHA-256; content hashes are recorded once before the campaign |
| `custom_nodes` | explicit whitelist with path, commit, license, source-manifest hash, and import policy |
| `core_source_hashes` | version-specific sources used by cache/topology/evidence logic |
| `package_inventory` | hash of the offline `pip freeze`/wheel admission receipt |
| `boot_policy` | canonical fixed args, allowed cell modifiers, forbidden args, port, attention policy |
| `hardware_contract` | expected GPU UUID/model/VRAM, driver, CUDA runtime, OS |

Large model files need not be rehashed before every run. They must receive a full content SHA-256 admission receipt once; each run then binds that receipt plus path, bytes, mtime, and file identity. Any fast-fingerprint drift forces a fresh full hash before allocation.

Attention policy is per profile and engine family. H3 profiles forbid global Sage. OTR's profile field `launch.sage_attention` is dead, unwired metadata: at current OTR HEAD, `nodes/_otr_shared/boot_contracts.py:171-175` deliberately omits it because no launcher passes `--use-sage-attention`. Production is Sage-free, so the lab's Sage-free boot is production parity. Track the field for deletion from the profile schema or end-to-end wiring; it must not justify Runner Division architecture. The separate live H3 `assert_sage_not_patched` safeguard remains enforcement that actually runs.

## Sealed launch specification

The only executable input to the floor runner is an atomically created, nonce-bound launch specification. It combines one profile, one immutable recipe, and one campaign cell.

Required bindings:

- campaign/cell/profile IDs and SHA-256 values;
- recipe and resolved prompt SHA-256 values;
- floor-runner bundle hash, not only `run_recipe.py`;
- exact Python, ComfyUI, node, package, fixture, model-admission, and core-source identities;
- canonical argv and sanitized environment hash;
- derived result/output/log paths;
- expected server identity and port;
- run-order role: control or candidate;
- cold/warm/JIT classification and timeout policy;
- allowed graph-diff paths and significance/human gates.

Both front office and floor runner validate the specification independently. A raw call to the new floor runner without a live front-office lease may produce a diagnostic, but never a promotable receipt.

## Recipe and environment separation

Today many recipes embed one installed ComfyUI version/commit/source hash. That makes the recipe inseparable from a single bench. Recipe schema v2 should separate:

- **logical recipe:** prompt graph, fixtures, seeds, output/media contract, topology and allowed graph diff;
- **bench attestation:** installed version, commit, node sources, `/object_info` schema, package inventory, boot/runtime policy.

The same logical prompt bytes can then run on `comfy0311` and `comfy0320`. The resolved launch specification binds the live schema for each bench, while the comparison verifier proves the prompt objects are identical when the independent variable is only the core revision.

Existing recipe files remain readable through a fail-closed schema-v1 adapter. They do not become schema-v2 evidence until the adapter proves an exact mapping and the mapping is covered by tests.

## Fair paired execution

Every performance or quality claim begins with fresh controls under the new runner bundle. Prior numbers are orientation only.

Default discovery schedule for each control/candidate pair:

1. verify both profiles and all assets without GPU allocation;
2. control: fresh server, cold compile/load run, first warm run, second consecutive warm run;
3. terminate and prove cleanup;
4. candidate: fresh server, cold compile/load run, first warm run, second consecutive warm run;
5. terminate and prove cleanup;
6. compare only the second warm runs;
7. if the result is near its admission threshold, repeat in reverse candidate/control order before deciding.

Never share a server, model cache, output namespace, result alias, or warm classification across profiles or variants. A plugin-present/bypassed control is mandatory before testing a new custom-node patch.

High-risk monkey-patch/kernel campaigns use a fresh process for every ordered patch chain. A CUDA illegal access, kernel exception, OOM, fatal exception, or timeout poisons that process: tear it down, discard its run-private scratch state, quarantine its compiled-kernel cache, and never return it to a baseline lane. A close or disputed comparison uses a counterbalanced fresh-boot order such as A-B-B-A.

## Re-baseline decision

Yes: every **promoted or shipping-relevant lab recipe contract** needs a fresh receipt under the new runner identity. No: the lab should not burn GPU time rerunning every historical experiment, known failure, superseded recipe, or blocked asset.

The current census is **83 checked-in recipes**: 70 have same-name top-level current aliases and 13 have no alias. The results tree retains 6 orphan aliases for removed legacy recipes. Of the 70 matched aliases, 58 use modern receipt schemas (57 v3 and one v2) and 12 are legacy; 29 appear warm, but only 6 are marked promotion-ready. No selected top-level alias binds the active `run_recipe.py` SHA-256 `c3c064…386365`, so the active-runner promotion-ready count is **zero**. The current Front Office plumbing receipt lives in its deliberately separate `results/runs/` namespace and is not part of this historical-alias predicate. The reproducible predicate, source commits, and retained prior receipt are recorded in [`../research/handoff_census_2026-08-13.json`](../research/handoff_census_2026-08-13.json). The runner code is safer than the evidence generation currently displayed; Runner Division must recertify claims, not erase history.

The migration has three tiers:

| Tier | Scope | Work |
|---|---|---|
| R0 static census | all 83 checked-in recipe JSON files | parse, schema, topology, fixture, manifest, profile-compatibility, and graph-diff validation; no GPU |
| R1 runner parity panel | one representative image, silent-video, native-A/V, audio-conditioned, GGUF, H3, LTX, and Wan surface with available assets | fresh control runs under the frozen bridge profile; prove the new front office did not weaken execution or evidence semantics |
| R2 certification set | every recipe whose receipt currently supports a promoted lab result or an OTR shipping video lane | fresh machine and required human gates; the front-office index displays old receipts as `PRE_RUNNER_DIVISION_HISTORY` without modifying their bytes |

Known failures remain known failures unless a new campaign claims to fix them. Experiments rerun only when admitted by a material-gain campaign. No new OTR promotion occurs until its exact recipe family completes R2.

The H3 work does not need to wait for unrelated engine families. `H3-LIP-TXT` may begin on the current runner after its fresh control and unambiguous transcript-window receipt because prompt text is its only independent variable. `H3-C032` and later profile-delta campaigns begin only after the minimal enrolled-profile front office and their required static evidence gates. Full lab recertification can continue afterward.

The current repository has six `promotion_ready=true` aliases that form the minimum known R2 set:

- `ltx_audio_hq_h1_1024x576`;
- `ltx_audio_hq_h2_193f`;
- `ltx_audio_hq_h3_1024x576_193f`;
- `ltx_video_2b_distilled_cmp_832x480_f193`;
- `wan_i2v_14b_exoneration_832x480_f33`;
- `wan_ti2v_5b_cmp_832x480_f193`.

All six bind an older runner hash, not the current checked-in `run_recipe.py`. They remain valid records of what happened, but none is current-runner certification. The existing validator does not presently surface this mismatch, so the Runner Division must add a computed `STALE_FOR_ACTIVE_RUNNER` status.

The lab does not yet contain a source-hash-bound shipping manifest that maps every OTR profile to a lab recipe. Therefore it cannot honestly claim R2 completeness from the lab repository alone. Before R2 closes, import a read-only OTR snapshot manifest and bind at least the H3 shipping mappings to `h3_i2v_low` and the exact RefAudio controls; do not infer completeness from similar names.

At current OTR `v2.0-alpha@c06128daa181ff802bc3bf79112e539eda1d8a02`, 51 tracked profile JSON files (excluding `widget_mapping`) contain 32 shipping rows that collapse to 22 unique video-engine IDs. Four H3 rows collapse to two registered contracts, `h3_low_video` and `h3_low_audio_in`, so those aliases need two renders, not four. All 21 lane packets are now closed: H3 lane 19 and 20 are the registered adapters, while lane 21 (`h3_low_mime`) is a standalone, deliberately unregistered runner—not a third shipping contract. `launch.sage_attention` metadata is dead/unwired and must not be used to claim a non-H3 Sage-production-parity gap. Static/visual wrapper engines may need OTR adapter regression instead of a GPU recipe; the imported manifest must classify that boundary explicitly.

## Minimum runner parity panel

The final inventory should be generated from the repository, but the first panel must cover these behavior classes using present, admitted assets:

- `t2i_low`: image sink and basic VRAM monitoring;
- `wan_ti2v_5b_cmp_832x480_f193`: GGUF video and long sampler path;
- `wan_i2v_14b_exoneration_832x480_f33`: corrected `--clamp` semantics and target-card accounting;
- `ltx_video_2b_distilled_cmp_832x480_f193`: second video family and comparison surface;
- `ltx_audio_hq_h3_1024x576_193f`: native A/V output and audio probe;
- `h3_i2v_suite_sentinel`: H3 joint latent, cache discipline, native A/V decode;
- `h3_r2v_refaudio_tts_lipsync_exact_seed42`: ordered image/audio references and human gate.

If a panel asset is unavailable, mark only that cell `BLOCKED`; do not substitute a different model or download it.

## Evidence schema v4

A promotable receipt should add these fields to the current evidence:

- `front_office_sha256`, `runner_bundle_sha256`, `profile_id`, `profile_sha256`;
- `launch_spec_sha256`, sanitized environment, canonical argv, and direct-launch proof;
- Python executable identity, package-inventory hash, core-source manifest hash;
- custom-node manifest and model-admission receipt hashes;
- campaign/cell/control-or-candidate role and paired-control identity;
- result/output namespace and server-session/cache lineage;
- baseline/candidate surface digests plus an explicit independent-variable path allowlist; any extra diff is `NOT_COMPARABLE`;
- phase timings when available: boot, model load, conditioning, sampling, video decode, audio decode, mux;
- timeout/early-abort reason and cleanup proof;
- comparison-builder version and immutable human-review receipt references.

Comparison documents must be generated by a deterministic builder and included in its exact-file tests. Ad-hoc JSON added under a tested comparison directory is not permitted.

## Sage exception design

The Sage candidate does not restore a global Sage boot. The profile forbids `--use-sage-attention` and equivalent CLI/environment switches.

Only campaign `H3-SAGE-AUTO` may whitelist the graph node `PathchSageAttentionKJ` with:

- KJNodes pin `6ab7e8130e449ed2c0037589bcf84146ceb7fc9c` or a separately reviewed later revision;
- required security ancestor `073efb07419f56cc714e099a82e49fbc23ad9263`;
- `sage_attention="auto"`;
- `allow_compile=false`;
- the token counter attached observationally;
- no Turbo, Spectrum, cache patch, KJ exact-memory patch, or H3-specific FP16-PV patch in the same cell.

The previous explicit FP16-PV probe remains a negative historical receipt, not the control. The new candidate gets a fresh SDPA control on the same new bench. It starts with one 864x480 I2V sentinel and a 600-second hard ceiling. Any fatal exception, timeout, black/noise frame, queue uncertainty, or cleanup uncertainty ends the campaign before Ref2VA is attempted.

## Implementation sequence

The numbered sequence below is the eventual architecture, not a requirement for the active minimal milestone. The active milestone stops after enrolled-profile selection, direct argv launch, receipt profile/launch-spec binding, per-cell namespaces, and stale-display classification. In particular, model-content admission, recipe schema v2, full receipt schema v4, GPU-UUID ACL mutexes, and cross-clone tests remain deferred. Preserve every existing floor-runner safeguard while making that narrow change.

1. Add schemas and tests for bench profiles, campaign cells, and launch specifications.
2. Extract path/boot identity from hard-coded constants into a validated `BenchProfile` object.
3. Replace the shell boot path with direct Python process launch; retain the legacy launcher until parity passes.
4. Namespace outputs, results, logs, PID receipts, and cache lineage by campaign/cell/profile.
5. Move version-specific core-source hashes into profiles.
6. Add model-content admission receipts and custom-node source manifests.
7. Add schema-v1 recipe adapter and schema-v2 logical recipe support.
8. Bind the full runner bundle and front office into receipt schema v4.
9. Update deterministic comparison builders/tests before creating new comparison receipts.
10. Run R0, then R1. Freeze Runner Division v1 only after all safety and parity gates pass.
11. Run the H3 R2 slice, then the paired 0.31.1/0.32.0 migration control.
12. Admit H3 candidates one at a time. OTR remains untouched.

## Acceptance tests before the first GPU run

- rejects missing, dirty-unapproved, wrong-commit, symlinked, junctioned, or reparse-point roots;
- rejects unknown profile keys, duplicate IDs, relative paths, mutable branch names, and abbreviated commits;
- rejects inherited environment overrides and forbidden/global Sage switches;
- rejects a recipe outside the trusted recipe root or a graph node/input/resource outside its campaign allowlist;
- rejects Python/ComfyUI/user/output/model/custom-node path mismatch in live argv;
- rejects an answering port without the matching nonce/profile-bound PID receipt;
- rejects result or artifact escape from its derived campaign namespace;
- rejects result alias/history collisions across profiles;
- rejects cache warmth inherited from a different server, profile, recipe, or variant;
- gives each run private user/input/output/temp/log roots and rejects writes into Jeffrey's interactive ComfyUI state;
- rejects a comparison whose control and candidate runner bundle differ;
- displays any receipt whose runner bundle differs from the active bundle as `STALE_FOR_ACTIVE_RUNNER` without rewriting it;
- rejects a model whose fast fingerprint no longer matches its content-hash admission receipt;
- proves timeout, prompt-uncertainty, and parent-death cleanup/quarantine behavior;
- proves all 83 recipes complete the R0 static census before Runner Division v1 is certified.

## Bottom line

Keep the existing runner's safety heart, but stop asking it to be its own receptionist, bench selector, campaign director, and evidence auditor. A sealed dynamic front office gives the lab clean 0.31.1-versus-0.32.0 comparisons, prevents old receipts from contaminating new claims, and makes future core-version or custom-node trials repeatable without turning paths and environment variables into hidden independent variables.
