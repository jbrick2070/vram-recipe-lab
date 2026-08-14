# H3 Turbo Larry v4-600 admission

Status: `ADMITTED_FOR_ONE_SEALED_COLD_I2V_CANDIDATE; LIVE_NODE_PROOF_PENDING`

Jeffrey explicitly authorized this named candidate for one best-use-case test. The weight is stored only under the managed model tree:

`C:\ComfyUI-Models\loras\h3-turbo-larry-v4\minimax_h3_turbo_v4_step600_ema.safetensors`

The runtime profile binds [its own immutable model manifest](../model_admissions/h3-turbo-larry-v4/models_manifest.md). This preserves the legacy root manifest and its historical recipe hashes unchanged.
The machine-readable admission record is [admission.json](../model_admissions/h3-turbo-larry-v4/admission.json).
The required base-H3 authorization is [H3_LICENSE_GRANT.md](H3_LICENSE_GRANT.md) (SHA-256 `d51f6311f5589e512eb12e432565c1a7726242ae9bd0e33323e33501ab72bb35`). It confines this test to the named grantee's local, offline, non-commercial use on operator-owned hardware, with no hosted service or weight redistribution; the underlying Community License remains in force.

| Field | Recorded value |
|---|---|
| Upstream weight source | `larryvrh/MiniMax-H3-Turbo-Lora`, revision `43a74557ac3f6539db8e0f2a959d03feb7a81480` |
| Selected file | `minimax_h3_turbo_v4_step600_ema.safetensors` |
| Upstream declared license | Apache-2.0 (recorded from the authorized model-card retrieval; the safetensors metadata does not embed license text) |
| Exact bytes | 779,849,816 |
| SHA-256 | `5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3` |
| Source node | `Larryvrh/ComfyUI-MiniMax-H3-Turbo` at `546b5028f4934f5129eb6c7142c2f3e461dfddbf` |
| Source-node code license | Apache-2.0 |
| Source-node package | `comfyui-minimax-h3-turbo` 1.2.3; Python >=3.10; declared dependencies `[]` |
| `__init__.py` SHA-256 | `036089da474d9d06fd277fd9686ff05aad913824220dd8a2f5882b271c21022f` |
| Required node support asset | `C:\ComfyUI-Models\custom_node_assets\ComfyUI-MiniMax-H3-Turbo\h3_silu_temb_grid.safetensors`, 5,510,600 bytes, SHA-256 `30eb3c2cc7fb6b470d9717ff840d359313ac27cd64b705e32da1baa10f72d6a8` |

The source checkout is clean and has no submodules. Its static source scan found no package installer, `requirements` file, prestartup hook, subprocess launch, HTTP client, Manager integration, or network call. `node.zip` is not used; it is not unpacked or executed.

The source-backed first use is deliberately narrow:

1. Current ComfyUI 0.32, FL2VA I2V, `864x480`, `124` frames, `24 fps`, seed `42`, and native H3 audio.
2. A fresh 20-step native control and an 8-step Turbo candidate use the identical prompt, fixture, base weights, canvas, seed, native-A/V chain, and `simple` scheduler. The candidate profile's only declared extra surface is the reviewed Turbo node plus its immutable manifest entry; this cold pair is directional evidence, not warm-cache promotion evidence.
3. The candidate alone inserts `MiniMaxH3TurboLoRA` after `UNETLoader`, feeds `MiniMaxH3TurboSampler` into `SamplerCustomAdvanced`, uses strength `1.0`, and uses `low_vram=false` (the upstream sharpest/bypass route).
4. A fresh Front Office profile must prove the two custom node classes through `/object_info` before the prompt can be queued. The global boot remains SageAttention-free.

The linked node source recommends v4-600 at 6–8 steps, says it supports the pruned INT8 H3 base, and identifies fast/high-intensity motion and generated audio as preview areas. That is upstream-source evidence, not a lab quality result.

If this test fails, its terminal receipt is retained and Jeffrey may authorize removal of the LoRA and its managed support asset from `C:\ComfyUI-Models`.
