---
name: rtx-4060-lab
description: Operate, inspect, or delegate work to the isolated physical RTX 4060 ComfyUI video bench through its local SSH-tunneled Codex bridge. Use when a request mentions the 4060 laptop, 8 GB video-model experiments, the physical H3 MIME probe, remote 4060 logs or preflight, or safe handoff between Codex, Claude, and other coding agents.
---

# RTX 4060 Local Lab

Treat the 4060 as a separate physical bench. It is not a 5080 runner, a source
of production receipts, or permission to change top-level lab state.

Read [bridge boundary](references/bridge-boundary.md) before using the bridge.
When that health check passes and a controller must actually use the bridge,
read [healthy bridge control](references/bridge-control.md).
Read [execution ladder](references/execution-ladder.md) before admission or a
render.
If a bridge check says unhealthy, read [SSH bridge health and recovery](references/ssh-bridge-health.md)
before attempting any 4060 lab action.

## Scope

- Work only in the laptop checkout and `eightgb_bench/local/` for mutable 4060
  state. Never touch the 5080 runner, port 8199, its locks, outputs, receipts,
  or OTR.
- Select only profile `physical-rtx4060-8gb` and one of three enrolled plans:
  `h3-mime-i2v-864x480-f90` (the immutable sentinel) or
  `h3-mime-i2v-motion-demo-f90` (a separate prompt-only demo), or
  `h3-mime-i2v-action-demo-f90` (a fixed short emergency-story demo). Never accept an
  arbitrary root, Python executable, port, environment, shell command, source
  workflow, or free-text prompt.
- The motion-demo plan uses its own fixed checked-in recipe and private local
  launch-config filename. It must earn a new cold/warm-1/warm-2 sequence; it
  never inherits sentinel warmth or historical receipts.
- The action-demo plan is an independent fixed prompt-only story cell. It also
  requires its own private launch config, admission, and cold/warm-1/warm-2
  sequence; it never inherits warmth, receipts, or review from either prior plan.
- Mutate the 4060 only through `eightgb_bench/runner_4060.py`. Do not issue
  ad-hoc ComfyUI commands.
- Prefer `gpt-5.3-codex-spark` for bounded remote work. Escalate only for an
  evidenced problem. Do not use Qwen or load an LLM on the 5080.

## Hard stops

Do not download models, install packages, use cloud APIs, expose a listener,
or use the retired direct-LAN endpoint. Stop and report on profile/model/node
drift, a lock or quarantine receipt, a foreign listener, a Git conflict, an
OOM, defective media, or incomplete shutdown proof.

Evidence comes only from the isolated runner's immutable receipts. A screenshot,
app-server message, or 5080 reserve result is orientation—not a physical 4060
pass. Preserve receipt bytes, keep commits narrow, and never force-push,
reset, discard a local edit, or fabricate a result.
