#!/usr/bin/env python3
"""Build the immutable per-model MiniMax H3 SageAttention experiment.

The normal lab boot remains Sage-free.  This recipe inserts the locally
installed KJNodes model-clone patch into one I2V graph and selects the explicit
FP16-PV CUDA implementation.  It neither changes a global ComfyUI flag nor
changes any repository default.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
COMFY_WORKSPACE = ROOT.parent
MODEL_ROOT = Path(r"C:\ComfyUI-Models")

BASE_RECIPE = RECIPES / "h3_i2v_suite_sentinel.json"
MODELS_MANIFEST = ROOT / "models_manifest.md"
BOOT_SCRIPT = ROOT / "boot_lab_server.cmd"
KJ_ROOT = COMFY_WORKSPACE / "custom_nodes" / "ComfyUI-KJNodes"
KJ_NODE_SOURCE = KJ_ROOT / "nodes" / "model_optimization_nodes.py"
KJ_REGISTRY_SOURCE = KJ_ROOT / "__init__.py"
SAGE_CORE_SOURCE = (
    COMFY_WORKSPACE
    / ".venv"
    / "Lib"
    / "site-packages"
    / "sageattention"
    / "core.py"
)

RECIPE_NAME = "h3_i2v_sage_patch_fp16pv_experimental"
OUTPUT_PREFIX = "h3_i2v_sage_patch_fp16pv_experimental_out"
PATCH_NODE_ID = "16"
PATCH_CLASS_TYPE = "PathchSageAttentionKJ"
SAGE_MODE = "sageattn_qk_int8_pv_fp16_cuda"

EXPECTED_BASE_RECIPE_SHA256 = (
    "3a838a63521f6266293a3f5796e0f25d41187f3c47e3665493c8938779be2f53"
)
EXPECTED_MODELS_MANIFEST_SHA256 = (
    "7379b5fac6e087e28a5158622b491983f6718c00b1e6cc35725b1a452df653e6"
)
EXPECTED_BOOT_SCRIPT_SHA256 = (
    "5f9c313a050e2cec6356c9d31b54cb7e0f1825b0a5314ec7eec436466036ccb4"
)
EXPECTED_KJ_NODE_SOURCE_SHA256 = (
    "910dfaa00c67238ca4227d9373ad0930a4e2c86880969dabe7de3cd8ce83f563"
)
EXPECTED_KJ_REGISTRY_SOURCE_SHA256 = (
    "8da7e12f52cabd71b06e44d733ee359fba3ea3ec07cebcceaf29e9c24eaffec2"
)
EXPECTED_SAGE_CORE_SOURCE_SHA256 = (
    "72cb42a7af2a643da5316887eee79dc2851a1e83746dfca2cc1adf6d7acec8be"
)
KJ_GIT_COMMIT = "b7646ad70a7daa7aeb919ca542274758d26ba2df"
SAGE_PACKAGE_VERSION = "2.2.0+cu130torch2.9.0andhigher.post4"

FL2VA_NAME = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
REF2VA_NAME = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
FL2VA_SIZE = 20_970_379_616
FL2VA_SHA256 = "e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a"
WAN_LIGHTX_NAME = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
WAN_LIGHTX_SIZE = 738_005_744
WAN_LIGHTX_SHA256 = "85c4a61c30e0497aa44b91d93a893b624708461a56fe5485183b28fa07e2dfb3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} hash changed: expected {expected}, found {actual}")


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError(f"UTF-8 BOM is forbidden: {path}")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_safetensors_header(path: Path) -> tuple[int, dict[str, Any]]:
    with path.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise RuntimeError(f"Truncated safetensors header length: {path}")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length <= 0 or header_length > 64 * 1024 * 1024:
            raise RuntimeError(f"Implausible safetensors header length: {path}")
        raw_header = handle.read(header_length)
    header = json.loads(raw_header.decode("utf-8"))
    if not isinstance(header, dict):
        raise RuntimeError(f"Invalid safetensors header object: {path}")
    return header_length, header


def h3_quantization_summary(path: Path) -> dict[str, Any]:
    header_length, header = read_safetensors_header(path)
    tensor_entries = {key: value for key, value in header.items() if key != "__metadata__"}
    dtype_counts = Counter(entry["dtype"] for entry in tensor_entries.values())
    quant_entries = {
        key: entry for key, entry in tensor_entries.items() if key.endswith(".comfy_quant")
    }
    records = Counter()
    data_start = 8 + header_length
    with path.open("rb") as handle:
        for entry in quant_entries.values():
            start, end = entry["data_offsets"]
            handle.seek(data_start + start)
            record = json.loads(handle.read(end - start).decode("utf-8"))
            records[json.dumps(record, sort_keys=True)] += 1
    expected_record = {
        "format": "int8_tensorwise",
        "convrot": True,
        "convrot_groupsize": 256,
    }
    expected_key = json.dumps(expected_record, sort_keys=True)
    if len(quant_entries) != 200 or records != Counter({expected_key: 200}):
        raise RuntimeError("Local H3 FL2VA quantization records changed")
    return {
        "header_bytes": header_length,
        "tensor_count": len(tensor_entries),
        "dtype_counts": dict(sorted(dtype_counts.items())),
        "quant_record_count": len(quant_entries),
        "quant_record": expected_record,
    }


def wan_lightx_header_summary(path: Path) -> dict[str, Any]:
    header_length, header = read_safetensors_header(path)
    keys = [key for key in header if key != "__metadata__"]
    block_ids = sorted(
        {
            int(match.group(1))
            for key in keys
            if (match := re.search(r"(?:^|\.)blocks\.(\d+)\.", key))
        }
    )
    if block_ids != list(range(40)):
        raise RuntimeError("Local LightX2V file is no longer the known 40-block Wan LoRA")
    if not any(".cross_attn.k_img." in key for key in keys):
        raise RuntimeError("Local LightX2V file lost its Wan k_img key-family evidence")
    return {
        "header_bytes": header_length,
        "tensor_count": len(keys),
        "block_count": len(block_ids),
        "block_range": [block_ids[0], block_ids[-1]],
        "key_family_evidence": "diffusion_model.blocks.*.cross_attn.k_img.*",
        "architecture": "Wan I2V 14B; incompatible with MiniMax H3",
    }


def local_speed_stack_inventory() -> dict[str, Any]:
    """Return hash-pinned local facts without querying a server or network."""
    require_file_hash(
        MODELS_MANIFEST,
        EXPECTED_MODELS_MANIFEST_SHA256,
        "models manifest",
    )
    diffusion_dir = MODEL_ROOT / "diffusion_models"
    lora_dir = MODEL_ROOT / "loras"
    h3_names = sorted(
        path.name
        for path in diffusion_dir.iterdir()
        if path.is_file() and re.search(r"(?i)(?:minimax|h3)", path.name)
    )
    if h3_names != [FL2VA_NAME, REF2VA_NAME]:
        raise RuntimeError(f"Local H3 diffusion inventory changed: {h3_names}")
    lightx_paths = sorted(
        (path for path in lora_dir.rglob("*") if path.is_file() and "lightx" in path.name.lower()),
        key=lambda path: path.as_posix().lower(),
    )
    if [path.name for path in lightx_paths] != [WAN_LIGHTX_NAME]:
        raise RuntimeError(
            f"Local LightX2V LoRA inventory changed: {[path.name for path in lightx_paths]}"
        )

    fl2va_path = diffusion_dir / FL2VA_NAME
    wan_lightx_path = lora_dir / WAN_LIGHTX_NAME
    if fl2va_path.stat().st_size != FL2VA_SIZE:
        raise RuntimeError("Local H3 FL2VA byte size changed")
    if wan_lightx_path.stat().st_size != WAN_LIGHTX_SIZE:
        raise RuntimeError("Local Wan LightX2V LoRA byte size changed")

    return {
        "evidence_scope": "offline manifest and actual local model directories",
        "models_manifest": {
            "path": "models_manifest.md",
            "sha256": EXPECTED_MODELS_MANIFEST_SHA256,
        },
        "current_h3_i2v_weight": {
            "model_basename": FL2VA_NAME,
            "model_subdir": "diffusion_models",
            "bytes": FL2VA_SIZE,
            "sha256": FL2VA_SHA256,
            "quantization": h3_quantization_summary(fl2va_path),
            "classification": "INT8 tensorwise ConvRot; not W4A8-mixed",
        },
        "kijai_h3_w4a8_mixed": {
            "status": "BLOCKED_MISSING_WEIGHT",
            "buildable": False,
            "local_filename": None,
            "sha256": None,
            "reason": (
                "No MiniMax H3 W4A8/mixed diffusion weight exists in the hash-pinned "
                "manifest or actual local diffusion_models directory"
            ),
        },
        "h3_lightx2v_four_step": {
            "status": "BLOCKED_MISSING_LORA",
            "buildable": False,
            "local_filename": None,
            "sha256": None,
            "reason": (
                "No MiniMax H3 LightX2V four-step distillation LoRA exists in the "
                "hash-pinned manifest or actual local loras directory"
            ),
            "confusable_local_wan_lora": {
                "model_basename": WAN_LIGHTX_NAME,
                "model_subdir": "loras",
                "bytes": WAN_LIGHTX_SIZE,
                "sha256": WAN_LIGHTX_SHA256,
                **wan_lightx_header_summary(wan_lightx_path),
            },
        },
        "per_model_sage_fp16pv": {
            "status": "BUILDABLE_UNRENDERED_HUMAN_GATE_REQUIRED",
            "buildable": True,
            "class_type": PATCH_CLASS_TYPE,
            "mode": SAGE_MODE,
            "allow_compile": False,
            "local_package_version": SAGE_PACKAGE_VERSION,
            "sm120_source_evidence": (
                "The hash-pinned SageAttention core contains an explicit sm120 dispatch "
                "branch; H3 visual correctness remains unproven until the human gate"
            ),
        },
    }


def build_recipe() -> dict[str, Any]:
    require_file_hash(BASE_RECIPE, EXPECTED_BASE_RECIPE_SHA256, "I2V sentinel source")
    require_file_hash(BOOT_SCRIPT, EXPECTED_BOOT_SCRIPT_SHA256, "Sage-free boot script")
    require_file_hash(KJ_NODE_SOURCE, EXPECTED_KJ_NODE_SOURCE_SHA256, "KJ patch source")
    require_file_hash(
        KJ_REGISTRY_SOURCE,
        EXPECTED_KJ_REGISTRY_SOURCE_SHA256,
        "KJ node registry",
    )
    require_file_hash(
        SAGE_CORE_SOURCE,
        EXPECTED_SAGE_CORE_SOURCE_SHA256,
        "SageAttention core",
    )
    kj_source_text = KJ_NODE_SOURCE.read_text(encoding="utf-8")
    kj_registry_text = KJ_REGISTRY_SOURCE.read_text(encoding="utf-8")
    sage_core_text = SAGE_CORE_SOURCE.read_text(encoding="utf-8")
    if f"class {PATCH_CLASS_TYPE}" not in kj_source_text:
        raise RuntimeError(f"KJ patch class spelling changed: {PATCH_CLASS_TYPE}")
    if f'"{PATCH_CLASS_TYPE}"' not in kj_registry_text:
        raise RuntimeError(f"KJ patch registry key changed: {PATCH_CLASS_TYPE}")
    if SAGE_MODE not in kj_source_text:
        raise RuntimeError(f"KJ explicit Sage mode is unavailable: {SAGE_MODE}")
    if 'elif arch == "sm120"' not in sage_core_text:
        raise RuntimeError("Local SageAttention core lost its sm120 source branch")

    source = read_json(BASE_RECIPE)
    recipe = copy.deepcopy(source)
    recipe["name"] = RECIPE_NAME
    recipe["tier"] = "experiment"
    recipe["blocked"] = False
    recipe["experiment"] = {
        "campaign": "h3_per_model_sage_attention_v1",
        "variant": "i2v_fp16pv_same_canvas",
        "matrix_role": "same-canvas per-model attention comparison",
        "independent_variable": "per_model_attention_override",
        "baseline_recipe": "recipes/h3_i2v_suite_sentinel.json",
        "baseline_recipe_sha256": EXPECTED_BASE_RECIPE_SHA256,
        "comparison_contract": {
            "same_prompt": True,
            "same_seed": True,
            "same_canvas": "864x480",
            "same_frames": 124,
            "same_scheduler": True,
            "same_sampler": True,
            "same_models": True,
            "artifact_identity_only_difference": OUTPUT_PREFIX,
        },
        "attention_patch": {
            "class_type": PATCH_CLASS_TYPE,
            "node_id": PATCH_NODE_ID,
            "mode": SAGE_MODE,
            "allow_compile": False,
            "scope": (
                "model.clone().model_options.transformer_options."
                "optimized_attention_override"
            ),
            "patched_model_consumers": ["6.BasicGuider", "14.BasicScheduler"],
            "global_boot_flag_enabled": False,
            "global_default_changed": False,
            "boot_lane": "lab-8199, sage-free",
            "boot_script": "boot_lab_server.cmd",
            "boot_script_sha256": EXPECTED_BOOT_SCRIPT_SHA256,
        },
        "source_provenance": {
            "kj_git_commit": KJ_GIT_COMMIT,
            "kj_node_source": "custom_nodes/ComfyUI-KJNodes/nodes/model_optimization_nodes.py",
            "kj_node_source_sha256": EXPECTED_KJ_NODE_SOURCE_SHA256,
            "kj_registry_source": "custom_nodes/ComfyUI-KJNodes/__init__.py",
            "kj_registry_source_sha256": EXPECTED_KJ_REGISTRY_SOURCE_SHA256,
            "sage_core_source": ".venv/Lib/site-packages/sageattention/core.py",
            "sage_core_source_sha256": EXPECTED_SAGE_CORE_SOURCE_SHA256,
            "sage_package_version": SAGE_PACKAGE_VERSION,
        },
        "execution_graph_diff_whitelist": [
            "prompt.16",
            "prompt.6.inputs.model",
            "prompt.14.inputs.model",
            "prompt.12.inputs.filename_prefix",
        ],
        "behavioral_claim_status": "unrendered and unproven",
        "speed_stack_inventory": local_speed_stack_inventory(),
        "human_gate": {
            "status": "pending",
            "mandatory": True,
            "machine_pass_is_insufficient": True,
            "compare_against": "h3_i2v_suite_sentinel same-canvas artifact",
            "pass_requires": [
                "human eyeball=ok with named human source and review timestamp",
                "no noise field, corruption, color collapse, or attention artifacts",
                "coherent subject, camera motion, and temporal continuity",
                "native video and audio remain perceptually intact",
            ],
        },
    }
    recipe["contract"]["mode"] = "i2v_sage_patch_fp16pv_experimental"
    recipe["contract"]["required_boot_lane"] = "lab-8199, sage-free"

    topology = recipe["topology_contract"]
    topology["profile"] = "minimax_h3_i2v_per_model_sage_fp16pv_v1"
    topology["intent"] = (
        "Same-canvas official MiniMax H3 I2V sentinel with one explicit KJNodes "
        "per-model FP16-PV SageAttention override on a normal Sage-free lab boot"
    )
    topology["required_nodes"][PATCH_NODE_ID] = PATCH_CLASS_TYPE
    topology["required_class_types"].append(PATCH_CLASS_TYPE)
    topology["required_connections"][f"{PATCH_NODE_ID}.model"] = ["1", 0]
    topology["required_connections"]["6.model"] = [PATCH_NODE_ID, 0]
    topology["required_connections"]["14.model"] = [PATCH_NODE_ID, 0]
    prefix_assertions = [
        assertion
        for assertion in topology["required_input_values"]
        if (assertion.get("node"), assertion.get("input"))
        == ("12", "filename_prefix")
    ]
    if len(prefix_assertions) != 1:
        raise RuntimeError(
            f"Expected one sentinel filename-prefix assertion, found {len(prefix_assertions)}"
        )
    prefix_assertions[0]["equals"] = OUTPUT_PREFIX
    topology["required_input_values"].extend(
        [
            {
                "node": PATCH_NODE_ID,
                "input": "sage_attention",
                "equals": SAGE_MODE,
            },
            {
                "node": PATCH_NODE_ID,
                "input": "allow_compile",
                "equals": False,
            },
        ]
    )
    topology["supporting_node_sources"] = {
        "custom_nodes/ComfyUI-KJNodes/nodes/model_optimization_nodes.py": (
            EXPECTED_KJ_NODE_SOURCE_SHA256
        ),
        "custom_nodes/ComfyUI-KJNodes/__init__.py": (
            EXPECTED_KJ_REGISTRY_SOURCE_SHA256
        ),
        ".venv/Lib/site-packages/sageattention/core.py": (
            EXPECTED_SAGE_CORE_SOURCE_SHA256
        ),
        "boot_lab_server.cmd": EXPECTED_BOOT_SCRIPT_SHA256,
    }
    topology["attention_patch_contract"] = {
        "class_type": PATCH_CLASS_TYPE,
        "mode": SAGE_MODE,
        "allow_compile": False,
        "input_model": ["1", 0],
        "output_consumers": ["6.model", "14.model"],
        "per_model_clone": True,
        "global_boot_flag_enabled": False,
        "global_default_changed": False,
        "human_gate_required": True,
    }
    topology["intentional_divergences"].extend(
        [
            "Node 16 clones UNETLoader output and installs the explicit FP16-PV optimized-attention override",
            "Both BasicGuider.model and BasicScheduler.model consume the same patched model clone",
            "The lab boot remains Sage-free and no global attention flag or repository default changes",
            "The unique SaveVideo prefix isolates the experimental artifact",
            "A warm machine pass cannot promote this variant without the mandatory side-by-side human visual gate",
        ]
    )

    prompt = recipe["prompt"]
    prompt[PATCH_NODE_ID] = {
        "class_type": PATCH_CLASS_TYPE,
        "inputs": {
            "model": ["1", 0],
            "sage_attention": SAGE_MODE,
            "allow_compile": False,
        },
    }
    prompt["6"]["inputs"]["model"] = [PATCH_NODE_ID, 0]
    prompt["14"]["inputs"]["model"] = [PATCH_NODE_ID, 0]
    prompt["12"]["inputs"]["filename_prefix"] = OUTPUT_PREFIX
    recipe["prompt"] = dict(sorted(prompt.items(), key=lambda item: int(item[0])))

    recipe["receipt_requirements"] = {
        "schema_version": 1,
        "human_visual_gate": {
            "status": "pending_human",
            "required_fields": [
                "eyeball",
                "eyeball_source",
                "eyeball_reviewed_at",
                "human_video_description",
                "human_video_scope",
            ],
            "pass_values": {
                "eyeball": "ok",
                "eyeball_source": "human",
                "human_video_scope": "full artifact and same-canvas baseline comparison",
            },
        },
    }
    return recipe


def write_recipe(output_dir: Path = RECIPES) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{RECIPE_NAME}.json"
    payload = canonical_json_bytes(build_recipe())
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Immutable generated recipe differs: {path}")
        return False
    path.write_bytes(payload)
    return True


def main() -> None:
    changed = write_recipe()
    print(f"{RECIPE_NAME}: {'created' if changed else 'unchanged'}")


if __name__ == "__main__":
    main()
