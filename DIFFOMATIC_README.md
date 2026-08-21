# Diffomatic

Diffomatic compares what an OTR engine actually builds with a shipped ComfyUI
reference graph. It reports; it never edits a recipe or recommends a transplant.

```text
python diffomatic_map.py [--json map.json]
python diffomatic.py --template REF.json --ours video:ltx25_video \
  [--recipe-py eng_ltx25.py,ltx25_recipe.py] [--json result.json]
python diffomatic_fleet.py
```

Both tools are offline and CPU-only. They do not start ComfyUI or load models.

## The fail-closed contract

An empty or unsupported comparison exits nonzero. With `--json`, even a failure
writes a receipt carrying `status: error`, a named error code, and every node
and edge count known at the point of refusal. Unexpected loader exceptions are
also converted to `INTERNAL_ERROR` receipts rather than leaking a traceback. A
successful receipt carries total/significant node counts, normalized edge
counts, source hashes, and topology digests for both graphs. Therefore
`0 identical / 0 different` can never masquerade as a clean comparison.
Classes found on only one side retain every instance's execution order and
complete parameter dictionary in both JSON evidence and the text report.

For a dynamic `eng_*` source, Diffomatic:

1. imports the real OTR registry and selects a concrete public engine ID such as
   `video:humo_1.7B` or `video:minimax_h3_audio_in`. Legacy `eng_*` module input
   remains available only when that module selects one adapter unambiguously;
2. uses that adapter's declared `render_canvas` for the fixture (for example,
   `eng_ltx_av` is built at its declared 1024x576, not the former generic
   832x480 guess);
3. binds `_build_graph` by known parameter names and refuses any unknown required
   argument instead of supplying a permissive object that hides mistakes; and
4. resolves every graph-local logical class through that same engine's
   zero-argument `_node_candidates*` declarations. The first declared candidate
   is the engine's preferred concrete class. OTR-local sigma injectors are
   accepted only when the render method explicitly adds their logical id and
   Python class to its executor map. Every other undeclared logical name is an
   error.

Wiring has its own comparison instead of being thrown away. API and OTR wires
are edges only when their source ID exists in the selected graph; an ordinary
literal such as `["not-a-node", 0]` remains a value. UI links are checked against
both endpoint metadata. Each receipt records the normalized edge multiset and
an ID-independent digest built from class, literal, port, and adjacency labels.
Changing a source port or rewiring repeated instances changes the proof even if
node-class counts stay equal.

A `LTXVLatentUpsampler` whose inputs are all edges remains a structural
instance, as do other significant nodes with no literal parameters. This is
essential: the presence and count of such nodes is often the pipeline-stage
finding.

## JSON and UI graphs

API-format (`class_type` plus `inputs`) and UI-format (`nodes`, including one
invoked subgraph) are accepted. Parsing is scope-based, not recursive: metadata,
unused definitions, and wrapper furniture cannot be counted as executed nodes.
Multiple possible executable subgraphs, contradictory links, or a bypassed
intermediary whose runtime rewiring cannot be proven are errors. Inactive source
or sink nodes and their incident links are excluded.

UI exports may carry named widget dictionaries or positional `widgets_values`
arrays. Positional decoding uses the installed node schema, including dynamic
combo children and seed `control_after_generate` companions. A trailing widget
added after an older template was published may use its explicit current-schema
default. A missing schema, dynamic selector, mid-array gap, or count mismatch is
unsupported. Diffomatic never invents `w0`, shifts a value onto a socket, or
calls such a parameter comparison complete.

When an active internal link feeds a UI widget input, its serialized widget
value is dormant fallback state and is removed from the parameter comparison.
Boundary proxy defaults remain visible because they can still define the
engine's public input. Schema-declared image/audio upload widgets accept only
their exact Comfy UI companion shapes; those upload/preview companions are UI
state, while the actual audio filename remains comparable.

## Documentation labels

A difference is `DOCUMENTED` only when an explanatory comment is attached to
the exact dictionary parameter/keyword line, or to the named constant referenced
by that line. The reason includes the absolute source path and exact line number.
Broad substring searches and comments many lines away are intentionally not
used. When the same parameter name occurs in multiple stages, a statically
resolved value must select exactly one site; same-value duplicates remain
undocumented rather than borrowing the first nearby comment.

## The fleet receipt

`diffomatic_fleet.py` is the one supported all-video sweep. It checks the live
registered roster is exactly 30 lanes: 11 modality-correct official references,
2 visibly qualified family baselines, and 17 procedural/provider/hybrid lanes
with no end-to-end local Comfy reference by design. It addresses HuMo and H3 by
public engine ID, verifies per-engine structural sentinels, rejects anonymous
widgets, requires positive node/edge counts and topology digests, records the
template package version/bytes/SHA-256 and active OTR source hashes, and exits
nonzero if any case fails. The PowerShell wrapper propagates that aggregate exit
code; it cannot print a successful sweep after a failed child comparison.

Before importing OTR engines, the fleet clears every inherited `OTR_*` and
`LAB_*` recipe override plus `HF_HOME` and `COMFYUI_MODELS_ROOT`, then sets its
fixed CPU-only test environment. Every comparison receipt and the fleet summary
record which keys were present and the effective values, so a caller's shell
cannot silently change the graph being audited.

The 2026-08-21 grounded receipt is under
`template_sweep/2026-08-21-grounded/fleet_summary.json`.

## Decision hash: what transfers from an official template

The comparison is evidence, not a mandate to copy the whole graph. For OTR
recipe work, keep a template element only when all five checks hold:

1. **Same role:** I2V, T2V, audio-in, and FLF2V are different contracts. A
   weight-family match never overrides modality.
2. **Same variable:** an A/B must preserve OTR's still, prompt, negative prompt,
   seed, audio, dimensions, and delivery chain except for the element under
   test.
3. **Output value:** transfer stages that visibly improve the delivered frame
   or continuity (for LTX 2.5, latent upscale plus full-canvas refine), not UI
   convenience, prompt rewriting, preview, or save furniture.
4. **Production fit:** retain OTR's canonical inputs, CPU/offload controls,
   quantized loaders, shot/beat contract, and downstream publish interface.
   Different official weights or canvas defaults are comparison facts, not
   automatic replacements.
5. **Execution proof:** success requires loader/runtime evidence that the added
   stage actually ran, the expected canvas reached decode, and the published
   episode came from that path. Adapter intent alone is not proof.

That is the reusable “logic hash”: preserve the proven quality mechanism,
preserve OTR's contract and safety controls, and reject every unrelated template
difference. A clean diff is not required; an explained, single-variable,
runtime-proven transplant is.

## Mapping rules

`diffomatic_map.py` reads OTR's video and image registries. Unregistered adapter
scaffolds, helper modules, and source files that merely look engine-shaped do not
enter the roster.

Matches require either a rare exact weight filename or strong per-file
cross-quant identity: at least two shared model tokens, including a shared
version/size token, with at least half of the smaller token set covered. A lone
family word such as `ltx`, `wan`, or `flux` scores zero. Generic VAEs and text
encoders also score zero through inverse-document-frequency gating.

I2V/T2V sibling templates are never resolved by alphabetical order. When weight
evidence supports both, the row says so. An engine whose registered capability
explicitly requires an init image can produce `role_disambiguated` with the
discarded sibling candidates retained in JSON; an unknown or non-unique role
produces `ambiguous_role` and no template. Equal non-modality ties similarly
produce `ambiguous_template`.

The mapper's statuses are:

- `matched`: one non-arbitrary evidence winner;
- `role_disambiguated`: I2V/T2V evidence was ambiguous and the engine's declared
  modality selected exactly one candidate;
- `ambiguous_role` or `ambiguous_template`: no template selected;
- `no_match`: no adequate identity evidence; and
- `no_reference_by_design`: a registered procedural/external lane for which an
  upstream local-model workflow is not meaningful.

A miss is a result. Comparing against the wrong graph is worse than leaving a
lane explicitly unmatched.
