#!/usr/bin/env python3
"""
Offline Paper Validation Script for vram-recipe-lab recipes.
Runs all static validations that do NOT require a live lab server:
  1. Strict UTF-8 encoding (NO BOM)
  2. JSON parsing validity
  3. Recipe contract integrity (width, height, frames, vram_ceiling_gb)
  4. Mandatory coverage of all 16 canonical recipes
  5. Node class_type presence and prompt dictionary structure
  6. Graph reachability, link index integrity, and data types
  7. Sink output node type validation (SaveImage for still, SaveVideo for video)
  8. Fixture file existence for I2V/R2V/Audio recipes
"""

import json
import hashlib
import math
import os
import stat
import statistics
import sys
from pathlib import Path

import suite_integrity

REPO_ROOT = Path(__file__).parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"
FIXTURES_DIR = REPO_ROOT / "fixtures"
AUDIO_RECEIPTS_DIR = FIXTURES_DIR / "audio_receipts"
CURRENT_RECEIPT_SCHEMA_VERSION = 3

_MINIMAX_H3_REFERENCE_CLASS = "MiniMaxH3ReferenceToVideo"
_MINIMAX_H3_AUTOGROW_SOCKET_SPECS = {
    "ref_images": ("ref_image_", 9),
    "ref_videos": ("ref_video_", 3),
    "ref_video_audios": ("ref_video_audio_", 3),
    "ref_audios": ("ref_audio_", 3),
}

REQUIRED_RECIPES = [
    "t2i_low", "t2i_high",
    "wan_ti2v_low", "wan_ti2v_high",
    "wan_i2v_14b_low", "wan_i2v_14b_high",
    "ltx_t2v_ckpt", "ltx_t2v_gguf", "ltx_t2v_fullhd_experimental",
    "ltx_i2v_ckpt", "ltx_i2v_gguf", "ltx_i2v_fullhd_experimental",
    "ltx_audio_ckpt", "ltx_audio_gguf", "ltx_audio_fullhd_experimental", "ltx_lipsync_low",
    "h3_t2v_low", "h3_t2v_best",
    "h3_i2v_low", "h3_i2v_best",
    "h3_i2v_suite_sentinel",
    "h3_r2v_low", "h3_r2v_best"
]


def _positive_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_finite_real(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def iter_prompt_links(value, path: str = ""):
    """Yield nested Comfy API links as (socket path, source id, output index)."""
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
        yield path, value[0], value[1]
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_prompt_links(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_prompt_links(child, f"{path}[{index}]")


def minimax_h3_autogrow_input_errors(prompt: dict) -> list[str]:
    """Reject V3 autogrow inputs that ComfyUI would ignore or cannot finalize."""
    errors = []
    if not isinstance(prompt, dict):
        return errors

    for node_id, node in prompt.items():
        if not isinstance(node, dict) or node.get("class_type") != _MINIMAX_H3_REFERENCE_CLASS:
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        for container, (prefix, _) in _MINIMAX_H3_AUTOGROW_SOCKET_SPECS.items():
            if container in inputs:
                errors.append(
                    f"Node {node_id} ({_MINIMAX_H3_REFERENCE_CLASS}) input '{container}' "
                    "is a nested V3 autogrow container that ComfyUI ignores; use direct "
                    f"dotted sockets such as '{container}.{prefix}0'"
                )

        for input_name, value in inputs.items():
            if not isinstance(input_name, str):
                continue
            for container, (prefix, count) in _MINIMAX_H3_AUTOGROW_SOCKET_SPECS.items():
                namespace = f"{container}."
                if not input_name.startswith(namespace):
                    continue
                member_name = input_name[len(namespace):]
                allowed_members = {f"{prefix}{index}" for index in range(count)}
                if member_name not in allowed_members:
                    errors.append(
                        f"Node {node_id} ({_MINIMAX_H3_REFERENCE_CLASS}) input "
                        f"'{input_name}' is not a valid V3 autogrow socket"
                    )
                if not (
                    isinstance(value, list)
                    and len(value) == 2
                    and isinstance(value[0], str)
                    and isinstance(value[1], int)
                    and not isinstance(value[1], bool)
                    and value[1] >= 0
                ):
                    errors.append(
                        f"Node {node_id} ({_MINIMAX_H3_REFERENCE_CLASS}) input "
                        f"'{input_name}' must be a direct Comfy link [node_id, output_index]"
                    )
                break

    return errors


def audio_fixture_receipt_errors(fixture_name: str, fixture_path: Path) -> list[str]:
    """Statically enforce the hash-bound probe and human ear-gate receipt."""
    receipt_path = AUDIO_RECEIPTS_DIR / f"{Path(fixture_name).stem}.json"
    if not receipt_path.is_file():
        return [f"Audio ear-gate receipt missing: {receipt_path.name}"]
    try:
        raw = receipt_path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            return [f"Audio ear-gate receipt has UTF-8 BOM: {receipt_path.name}"]
        receipt = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"Invalid audio ear-gate receipt {receipt_path.name}: {exc}"]

    human = receipt.get("human_review", {})
    probe = receipt.get("ffprobe", {})
    volume = receipt.get("volumedetect", {})
    matrix_window = receipt.get("matrix_window", {})
    commands = receipt.get("commands", {})
    errors = []
    if receipt.get("schema_version") != 1:
        errors.append(f"Audio receipt schema must be 1: {receipt_path.name}")
    if receipt.get("fixture") != fixture_name:
        errors.append(f"Audio receipt fixture label mismatch: {receipt_path.name}")
    if receipt.get("sha256") != hashlib.sha256(fixture_path.read_bytes()).hexdigest():
        errors.append(f"Audio receipt SHA-256 mismatch: {receipt_path.name}")
    if receipt.get("ear_gate_pass") is not True:
        errors.append(f"Audio ear gate is not approved: {receipt_path.name}")
    if not all(human.get(key) for key in ("reviewer", "reviewed_at", "content_class", "description")):
        errors.append(f"Audio human description is incomplete: {receipt_path.name}")
    if not all(key in probe for key in ("codec_name", "sample_rate_hz", "channels", "duration_s")):
        errors.append(f"Audio ffprobe fields are incomplete: {receipt_path.name}")
    if not all(key in volume for key in ("mean_volume_db", "max_volume_db")):
        errors.append(f"Audio volumedetect fields are incomplete: {receipt_path.name}")
    if not all(key in commands for key in ("ffprobe", "volumedetect", "matrix_loudness")):
        errors.append(f"Audio reproduction commands are incomplete: {receipt_path.name}")
    numeric_matrix_fields = ("duration_s", "target_lufs", "tolerance_lu", "gain_db", "matched_lufs")
    if not matrix_window.get("method") or not all(
        isinstance(matrix_window.get(key), (int, float)) and math.isfinite(float(matrix_window[key]))
        for key in numeric_matrix_fields
    ):
        errors.append(f"Audio matrix loudness evidence is incomplete: {receipt_path.name}")
    elif abs(float(matrix_window["matched_lufs"]) - float(matrix_window["target_lufs"])) > float(matrix_window["tolerance_lu"]) + 1e-6:
        errors.append(f"Audio matrix loudness exceeds tolerance: {receipt_path.name}")
    return errors


def topology_contract_errors(data: dict, prompt: dict) -> list[str]:
    """Validate hash-frozen official-topology assertions without a live server."""
    topology = data.get("topology_contract", {})
    if not topology:
        return []
    if not isinstance(topology, dict):
        return ["topology_contract must be a dictionary"]

    errors = []
    if topology.get("schema_version", 1) != 1:
        errors.append("topology_contract.schema_version must be 1")

    installed_schema = topology.get("installed_schema")
    if installed_schema is not None:
        if not isinstance(installed_schema, dict):
            errors.append("topology_contract.installed_schema must be a dictionary")
        else:
            for field in ("comfyui_version", "git_commit"):
                if not isinstance(installed_schema.get(field), str) or not installed_schema[field].strip():
                    errors.append(f"topology_contract.installed_schema.{field} must be a non-empty string")

    frozen_template = topology.get("frozen_template")
    if frozen_template is not None:
        if not isinstance(frozen_template, dict):
            errors.append("topology_contract.frozen_template must be a dictionary")
        else:
            template_name = frozen_template.get("path")
            expected_hash = frozen_template.get("sha256")
            try:
                template_path = (REPO_ROOT / str(template_name)).resolve()
                template_path.relative_to(REPO_ROOT)
                if not template_path.is_file():
                    errors.append(f"Frozen template is missing: {template_name}")
                elif hashlib.sha256(template_path.read_bytes()).hexdigest() != expected_hash:
                    errors.append(f"Frozen template hash changed: {template_name}")
            except (OSError, ValueError):
                errors.append(f"Frozen template path escapes the repository: {template_name}")

    required_nodes = topology.get("required_nodes", {})
    if not isinstance(required_nodes, dict):
        errors.append("topology_contract.required_nodes must be a dictionary")
    else:
        for node_id, expected_class in required_nodes.items():
            actual_class = prompt.get(str(node_id), {}).get("class_type")
            if actual_class != expected_class:
                errors.append(
                    f"Official topology node {node_id} must be {expected_class}, found {actual_class}"
                )

        exact_node_set = topology.get("exact_node_set", False)
        if not isinstance(exact_node_set, bool):
            errors.append("topology_contract.exact_node_set must be true or false")
        elif exact_node_set:
            expected_node_ids = {str(node_id) for node_id in required_nodes}
            actual_node_ids = {str(node_id) for node_id in prompt}
            extra_node_ids = sorted(actual_node_ids - expected_node_ids, key=str)
            missing_node_ids = sorted(expected_node_ids - actual_node_ids, key=str)
            if extra_node_ids:
                errors.append(
                    f"Official topology exact_node_set contains unexpected nodes: {extra_node_ids}"
                )
            if missing_node_ids:
                errors.append(
                    f"Official topology exact_node_set is missing nodes: {missing_node_ids}"
                )

    required_connections = topology.get("required_connections", {})
    if not isinstance(required_connections, dict):
        errors.append("topology_contract.required_connections must be a dictionary")
    else:
        for socket, expected in required_connections.items():
            if not isinstance(socket, str) or "." not in socket:
                errors.append(f"Invalid declared socket {socket!r}")
                continue
            node_id, input_name = socket.split(".", 1)
            actual = prompt.get(node_id, {}).get("inputs", {}).get(input_name)
            if actual != expected:
                errors.append(
                    f"Official topology socket {socket} must be {expected!r}, found {actual!r}"
                )

    required_values = topology.get("required_input_values", [])
    if not isinstance(required_values, list):
        errors.append("topology_contract.required_input_values must be a list")
    else:
        for assertion in required_values:
            if not isinstance(assertion, dict):
                errors.append(f"Invalid required input assertion: {assertion!r}")
                continue
            node_id = str(assertion.get("node"))
            input_name = assertion.get("input")
            expected = assertion.get("equals")
            actual = prompt.get(node_id, {}).get("inputs", {}).get(input_name)
            if actual != expected:
                errors.append(
                    f"Official topology value {node_id}.{input_name} must be {expected!r}, found {actual!r}"
                )

    required_absent_inputs = topology.get("required_absent_inputs", [])
    if not isinstance(required_absent_inputs, list):
        errors.append("topology_contract.required_absent_inputs must be a list")
    else:
        for socket in required_absent_inputs:
            if not isinstance(socket, str) or "." not in socket:
                errors.append(f"Invalid absent-input socket {socket!r}")
                continue
            node_id, input_name = socket.split(".", 1)
            inputs = prompt.get(node_id, {}).get("inputs", {})
            if isinstance(inputs, dict) and input_name in inputs:
                errors.append(
                    f"Official topology input {socket} must be absent, found {inputs[input_name]!r}"
                )

    present_classes = {
        node.get("class_type") for node in prompt.values() if isinstance(node, dict)
    }
    forbidden = set(topology.get("forbidden_class_types", []))
    present_forbidden = sorted(forbidden & present_classes)
    if present_forbidden:
        errors.append(f"Official topology contains forbidden node classes: {present_forbidden}")

    required_classes = set(topology.get("required_class_types", []))
    missing_classes = sorted(required_classes - present_classes)
    if missing_classes:
        errors.append(f"Official topology is missing required node classes: {missing_classes}")

    terminal_node = topology.get("terminal_node")
    if terminal_node is not None:
        terminal = prompt.get(str(terminal_node), {})
        if terminal.get("class_type") not in {"SaveImage", "SaveVideo"}:
            errors.append(f"Official topology terminal node {terminal_node} is not a save sink")

    if topology.get("require_all_nodes_reachable") is True:
        sink_ids = {
            node_id
            for node_id, node in prompt.items()
            if isinstance(node, dict) and node.get("class_type") in {"SaveImage", "SaveVideo"}
        }
        reachable = set(sink_ids)
        stack = list(sink_ids)
        while stack:
            current = stack.pop()
            for value in prompt[current].get("inputs", {}).values():
                for _, source_id, _ in iter_prompt_links(value):
                    if source_id in prompt and source_id not in reachable:
                        reachable.add(source_id)
                        stack.append(source_id)
        dead_nodes = sorted(set(prompt) - reachable, key=str)
        if dead_nodes:
            errors.append(f"Official topology has nodes disconnected from every output: {dead_nodes}")

    return errors



def validate_recipe_file(recipe_path: Path) -> dict:
    recipe_name = recipe_path.stem
    errors = []
    warnings = []

    # 1. Check UTF-8 (Strict NO BOM)
    raw_bytes = recipe_path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        errors.append("UTF-8 BOM detected at start of file (must be UTF-8 without BOM)")

    # 2. Parse JSON
    try:
        content = raw_bytes.decode("utf-8")
        data = json.loads(content)
    except Exception as e:
        return {"recipe": recipe_name, "valid": False, "errors": [f"JSON parse error: {e}"], "warnings": []}

    # 3. Check top-level contract keys
    if "name" not in data or data["name"] != recipe_name:
        errors.append(f"Name mismatch: expected '{recipe_name}', got '{data.get('name')}'")
    if "contract" not in data or not isinstance(data["contract"], dict):
        errors.append("Missing or invalid 'contract' dictionary")
    else:
        contract = data["contract"]
        for field in ["width", "height", "vram_ceiling_gb"]:
            if field not in contract:
                errors.append(f"Missing contract field: {field}")
        for field in ("width", "height"):
            if field in contract and not _positive_integer(contract.get(field)):
                errors.append(f"Contract field {field} must be a positive integer")
        if "vram_ceiling_gb" in contract and not _positive_finite_real(
            contract.get("vram_ceiling_gb")
        ):
            errors.append("Contract field vram_ceiling_gb must be a positive finite real number")

        is_video_recipe = "t2i" not in recipe_name
        if is_video_recipe:
            if "frames" not in contract:
                errors.append("Missing contract field: frames")
            elif not _positive_integer(contract.get("frames")):
                errors.append("Contract field frames must be a positive integer")
            if "fps" not in contract:
                errors.append("Missing contract field: fps")
            elif not _positive_finite_real(contract.get("fps")):
                errors.append("Contract field fps must be a positive finite real number")
            duration_fields = [
                field for field in ("target_s", "duration_s") if field in contract
            ]
            if not duration_fields:
                errors.append("Missing contract field: target_s or duration_s")
            for field in duration_fields:
                if not _positive_finite_real(contract.get(field)):
                    errors.append(
                        f"Contract field {field} must be a positive finite real number"
                    )
        else:
            if "frames" in contract and not _positive_integer(contract.get("frames")):
                errors.append("Contract field frames must be a positive integer")
            if "fps" in contract and not _positive_finite_real(contract.get("fps")):
                errors.append("Contract field fps must be a positive finite real number")
            for field in ("target_s", "duration_s"):
                if field in contract and not _positive_finite_real(contract.get(field)):
                    errors.append(
                        f"Contract field {field} must be a positive finite real number"
                    )

    # 4. Check prompt structure & graph topology
    prompt = data.get("prompt", {})
    if not isinstance(prompt, dict) or not prompt:
        errors.append("Missing or empty 'prompt' dictionary")
    else:
        node_ids = set(prompt.keys())
        has_video_save = False
        has_image_save = False

        errors.extend(minimax_h3_autogrow_input_errors(prompt))

        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                errors.append(f"Node {node_id} is not a dictionary")
                continue
            class_type = node.get("class_type")
            if not class_type:
                errors.append(f"Node {node_id} missing 'class_type'")
                continue

            if class_type == "SaveVideo":
                has_video_save = True
            elif class_type == "SaveImage":
                has_image_save = True

            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                errors.append(f"Node {node_id} 'inputs' is not a dictionary")
                continue

            # 5. Check links & graph reachability
            for in_key, in_val in inputs.items():
                for socket_path, target_id, slot_idx in iter_prompt_links(in_val, in_key):
                    if target_id not in node_ids:
                        errors.append(f"Node {node_id} input '{socket_path}' references non-existent node {target_id}")
                    if not isinstance(slot_idx, int) or isinstance(slot_idx, bool) or slot_idx < 0:
                        errors.append(f"Node {node_id} input '{socket_path}' has invalid output index {slot_idx!r}")

        errors.extend(topology_contract_errors(data, prompt))

        # 6. Check sink output node type match
        if "t2i" in recipe_name:
            if not has_image_save:
                errors.append("Still image recipe missing SaveImage sink node")
        else:
            if not has_video_save:
                errors.append("Video recipe missing SaveVideo sink node (must end in SaveVideo)")

    # 7. Check the literal fixtures referenced by graph loader nodes.
    if isinstance(prompt, dict):
        fixture_inputs = {"LoadImage": "image", "LoadAudio": "audio"}
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            input_name = fixture_inputs.get(node.get("class_type"))
            if not input_name:
                continue
            fixture_name = node.get("inputs", {}).get(input_name)
            if isinstance(fixture_name, str) and fixture_name:
                normalized = fixture_name.replace("\\", "/")
                candidate = Path(normalized)
                if candidate.is_absolute() or len(candidate.parts) != 1 or normalized in {".", ".."}:
                    errors.append(f"Fixture reference escapes fixtures/: {fixture_name}")
                    continue
                p = FIXTURES_DIR / fixture_name
                if not p.is_file():
                    errors.append(f"Referenced fixture missing: {fixture_name}")
                elif node.get("class_type") == "LoadAudio":
                    errors.extend(audio_fixture_receipt_errors(fixture_name, p))

    return {
        "recipe": recipe_name,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(prompt) if isinstance(prompt, dict) else 0,
        "blocked": data.get("blocked", False)
    }


_CURRENT_ALIAS_HUMAN_REVIEW_FIELDS = frozenset(
    {
        "eyeball",
        "eyeball_source",
        "eyeball_reviewed_at",
        "human_video_description",
        "human_video_scope",
        "audio_ear",
        "audio_ear_source",
        "audio_ear_reviewed_at",
        "soundscape_description",
        "speech_or_vocal_like_content",
        "diegetic_sync",
        "inverted_ear_gate_pass",
    }
)

_CURRENT_ALIAS_ADDITIVE_MIGRATION_FIELDS = frozenset(
    {
        "receipt_schema_version",
        "legacy_provenance",
        "legacy_provenance_reason",
    }
)


def matching_run_archive(
    rdata: dict, recipe_file: Path, repo_root: Path, schema_version: int
) -> tuple[dict | None, Path | None, bytes | None, list[str]]:
    """Bind a modern current PASS to immutable machine evidence.

    Human review is intentionally recorded on the mutable current alias after
    a run.  Every other receipt field remains immutable.  The sole historical
    exception is an additive schema marker (and schema-v1 provenance marker)
    on archives that predate receipt schemas.
    """
    errors = []
    recipe_name = recipe_file.stem
    if rdata.get("recipe") != recipe_name:
        errors.append(
            f"current alias recipe {rdata.get('recipe')!r} != certified recipe {recipe_name!r}"
        )

    run_number = rdata.get("run_number")
    if isinstance(run_number, bool) or not isinstance(run_number, int) or run_number < 1:
        errors.append("modern pass requires a positive integer run_number")
        return None, None, None, errors

    archive_name = f"{recipe_name}_run{run_number}.json"
    archive_path = repo_root / "results" / archive_name
    if not os.path.lexists(archive_path):
        errors.append(
            f"modern pass requires matching immutable archive: {archive_path.name} is missing"
        )
        return None, archive_path, None, errors

    try:
        archive_path = immutable_child_receipt_path(
            repo_root,
            recipe_name,
            run_number,
            f"results/{archive_name}",
        )
    except ValueError as exc:
        errors.append(f"invalid immutable archive {archive_name}: {exc}")
        return None, archive_path, None, errors

    try:
        raw = archive_path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("UTF-8 BOM is not allowed")
        archive = json.loads(raw.decode("utf-8"))
        if not isinstance(archive, dict):
            raise ValueError("receipt must contain a JSON object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"invalid immutable archive {archive_path.name}: {exc}")
        return None, archive_path, None, errors

    if archive.get("recipe") != recipe_name:
        errors.append(
            f"immutable archive {archive_path.name} labels recipe {archive.get('recipe')!r}"
        )
    archive_run_number = archive.get("run_number", archive.get("run_count"))
    if (
        isinstance(archive_run_number, bool)
        or not isinstance(archive_run_number, int)
        or archive_run_number < 1
    ):
        errors.append(
            f"immutable archive {archive_path.name} has an invalid run number: "
            f"{archive_run_number!r}"
        )
    elif archive_run_number != run_number:
        errors.append(
            f"immutable archive {archive_path.name} contains run number "
            f"{archive_run_number!r}, expected {run_number}"
        )

    missing = object()
    for field in sorted(set(rdata) | set(archive)):
        if field in _CURRENT_ALIAS_HUMAN_REVIEW_FIELDS:
            continue
        archive_value = archive.get(field, missing)
        alias_value = rdata.get(field, missing)
        if field in _CURRENT_ALIAS_ADDITIVE_MIGRATION_FIELDS and archive_value is missing:
            if field == "receipt_schema_version" or schema_version == 1:
                continue
        if archive_value is missing or alias_value is missing:
            values_match = archive_value is alias_value
        else:
            try:
                values_match = json.dumps(
                    archive_value,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ) == json.dumps(
                    alias_value,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError):
                values_match = False
        if not values_match:
            errors.append(
                f"current alias disagrees with immutable archive machine field: {field}"
            )
    return archive, archive_path, raw, errors


_CURRENT_WARM_PASS_STATUSES = frozenset({"PASS", "PASS (marginal)"})


def certified_output_artifact_path(repo_root: Path, output_name) -> Path:
    """Resolve a nonempty regular artifact through a real, contained outputs path."""
    if not isinstance(output_name, str) or not output_name.strip():
        raise ValueError("certified output artifact path must be nonempty text")
    candidate = Path(output_name.replace("\\", "/"))
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        raise ValueError(
            "certified output artifact path must be relative and contained in outputs/"
        )
    try:
        root = Path(repo_root).resolve(strict=True)
        outputs_lexical = root / "outputs"
        if not os.path.lexists(outputs_lexical):
            raise ValueError("certified outputs directory is missing")
        if _is_symlink_or_reparse_point(outputs_lexical):
            raise ValueError("certified outputs directory is a symlink or reparse point")
        outputs_root = outputs_lexical.resolve(strict=True)
        if outputs_root != outputs_lexical or not outputs_root.is_dir():
            raise ValueError("certified outputs directory does not resolve exactly")

        lexical = outputs_root / candidate
        component = outputs_root
        for part in candidate.parts:
            component = component / part
            if os.path.lexists(component) and _is_symlink_or_reparse_point(component):
                raise ValueError(
                    "certified output artifact path contains a symlink or reparse point"
                )
        artifact = lexical.resolve(strict=True)
        artifact.relative_to(outputs_root)
    except ValueError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"certified output artifact path cannot be proved: {exc}") from exc
    if artifact != lexical or not artifact.is_file():
        raise ValueError("certified output artifact is not an exact regular file")
    try:
        if artifact.stat().st_size <= 0:
            raise ValueError("certified output artifact is empty")
    except OSError as exc:
        raise ValueError(f"certified output artifact size cannot be proved: {exc}") from exc
    return artifact


def manager_probe_identity_from_receipt(evidence: object) -> dict | None:
    """Re-derive the manager probe identity from an immutable receipt payload.

    Early schema-v3 Manager-offline receipts bind this identity only inside
    ``identity``.  Their complete pre-queue evidence remains at
    ``manager_offline_probe.pre_queue`` and must still agree with that binding;
    the immutable receipt bytes must not be rewritten merely to add a later
    top-level convenience copy.
    """
    if not isinstance(evidence, dict) or evidence.get("enabled") is not True:
        return None
    advisory = evidence.get("advisory_config") or {}
    scan = evidence.get("log_scan") or {}
    authority = scan.get("authoritative_server_reported_mode") or {}
    source = scan.get("source_proof") or {}
    return {
        "recipe_scope": evidence.get("recipe_scope"),
        "guard_source": evidence.get("guard_source"),
        "test_boot_source": evidence.get("test_boot_source"),
        "offline_environment": evidence.get("offline_environment"),
        "advisory_config_path": (advisory.get("snapshot") or {}).get("path"),
        "advisory_config_sha256": (advisory.get("snapshot") or {}).get("sha256"),
        "authoritative_server_reported_mode": authority.get("resolved_mode"),
        "manager_source_sha256s": {
            key: (source.get(key) or {}).get("sha256")
            for key in (
                "manager_prestartup",
                "manager_server",
                "manager_core",
                "comfy_folder_paths",
                "manager_util",
            )
        },
        "prestartup_state_sha256": (
            (scan.get("current_prestartup_state") or {}).get("state_sha256")
        ),
        "preboot_record_sha256": (
            ((scan.get("preboot_records") or [{}])[0].get("record") or {}).get(
                "record_sha256"
            )
        ),
        "log_path": evidence.get("log_path"),
        "serving_pid": evidence.get("serving_pid"),
        "serving_process_create_time_ns": evidence.get(
            "serving_process_create_time_ns"
        ),
    }


def current_certification_errors(rdata: dict, recipe_file: Path, repo_root: Path) -> list[str]:
    """Validate a current warm receipt without allowing field deletion to imply legacy."""

    modern_markers = (
        "receipt_schema_version",
        "run_identity_sha256",
        "identity",
        "runner_sha256",
        "lab_locks_sha256",
        "provenance_unchanged",
    )
    if not any(marker in rdata for marker in modern_markers):
        return []

    errors = []
    for field in ("pass", "gate_pass", "warm_pass"):
        if not isinstance(rdata.get(field), bool):
            errors.append(f"modern receipt field {field} must be an actual boolean")
    if rdata.get("pass") is not True:
        return errors

    schema_version = rdata.get("receipt_schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in (1, 2, CURRENT_RECEIPT_SCHEMA_VERSION)
    ):
        errors.append("modern pass requires receipt_schema_version 1, 2, or 3")
        schema_version = 0
    if schema_version == 1 and rdata.get("legacy_provenance") is not True:
        errors.append("schema v1 requires explicit legacy_provenance=true")

    _, _, _, archive_errors = matching_run_archive(
        rdata, recipe_file, repo_root, schema_version
    )
    errors.extend(archive_errors)

    if not recipe_file.is_file():
        errors.append("certified recipe file is missing")
    else:
        current_hash = hashlib.sha256(recipe_file.read_bytes()).hexdigest()
        if rdata.get("recipe_sha256") != current_hash:
            errors.append(
                f"recipe hash {rdata.get('recipe_sha256')} != current {current_hash}"
            )

    identity = rdata.get("identity")
    expected_identity_hash = (
        hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if isinstance(identity, dict)
        else ""
    )
    if not isinstance(identity, dict):
        errors.append("identity payload is missing")
    elif rdata.get("run_identity_sha256") != expected_identity_hash:
        errors.append("identity hash does not recompute")

    if rdata.get("gate_pass") is not True or rdata.get("warm_pass") is not True:
        errors.append("pass requires gate_pass and warm_pass")
    if rdata.get("status") not in _CURRENT_WARM_PASS_STATUSES:
        errors.append("warm pass status must be PASS or PASS (marginal)")
    config_run_count = rdata.get("config_run_count")
    if (
        isinstance(config_run_count, bool)
        or not isinstance(config_run_count, int)
        or config_run_count < 2
    ):
        errors.append("pass requires config_run_count >= 2")
    run_count = rdata.get("run_count")
    if run_count is not None and (
        isinstance(run_count, bool)
        or not isinstance(run_count, int)
        or run_count < 1
        or run_count != rdata.get("run_number")
    ):
        errors.append("pass run_count must be a positive integer equal to run_number")

    if schema_version >= 2:
        required_fields = (
            "runner_sha256",
            "fixture_sha256s",
            "identity",
            "run_identity_sha256",
            "recipe_sha256",
            "artifact_sha256",
            "provenance_unchanged",
            "gate_pass",
            "warm_pass",
            "config_run_count",
            "output_path",
        )
        for field in required_fields:
            if field not in rdata:
                errors.append(f"schema v2 field is missing: {field}")
        if rdata.get("provenance_unchanged") is not True:
            errors.append("pass requires unchanged provenance")
        if isinstance(identity, dict):
            for field, identity_value in identity.items():
                if field == "manager_offline_probe_identity":
                    if field in rdata:
                        if rdata.get(field) != identity_value:
                            errors.append(
                                "top-level field disagrees with identity: "
                                "manager_offline_probe_identity"
                            )
                    else:
                        probe = rdata.get("manager_offline_probe")
                        pre_queue = (
                            probe.get("pre_queue") if isinstance(probe, dict) else None
                        )
                        receipt_identity = manager_probe_identity_from_receipt(pre_queue)
                        # The receipt's runner hash fixes the historical shape.
                        # Re-prove every field that shape claimed, while allowing
                        # later collectors to add identity keys without making the
                        # older immutable receipt appear corrupt.
                        if (
                            not isinstance(identity_value, dict)
                            or not isinstance(receipt_identity, dict)
                            or any(
                                receipt_identity.get(key) != value
                                for key, value in identity_value.items()
                            )
                        ):
                            errors.append(
                                "manager_offline_probe.pre_queue disagrees with "
                                "identity: manager_offline_probe_identity"
                            )
                    continue
                if field not in rdata or rdata.get(field) != identity_value:
                    errors.append(f"top-level field disagrees with identity: {field}")

    if schema_version >= 3:
        lock_hash = rdata.get("lab_locks_sha256")
        if (
            not isinstance(lock_hash, str)
            or len(lock_hash) != 64
            or any(character not in "0123456789abcdef" for character in lock_hash)
        ):
            errors.append("schema v3 field is missing or invalid: lab_locks_sha256")
        if not isinstance(identity, dict) or identity.get("lab_locks_sha256") != lock_hash:
            errors.append("schema v3 identity does not bind lab_locks_sha256")
        lock_helper = repo_root / "lab_locks.py"
        if not lock_helper.is_file():
            errors.append("certified lab_locks.py is missing")
        else:
            current_lock_hash = hashlib.sha256(lock_helper.read_bytes()).hexdigest()
            if lock_hash != current_lock_hash:
                errors.append(
                    f"lab_locks.py hash {lock_hash} != current {current_lock_hash}"
                )

    try:
        output_file = certified_output_artifact_path(repo_root, rdata.get("output_path"))
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if rdata.get("artifact_sha256") != hashlib.sha256(output_file.read_bytes()).hexdigest():
            errors.append("artifact SHA-256 mismatch")

    if rdata.get("promotion_ready") and rdata.get("requires_human_eyeball"):
        if rdata.get("eyeball") != "ok" or rdata.get("eyeball_source") != "human":
            errors.append("H3 promotion requires explicit human eyeball=ok")
    if "marginal" in str(rdata.get("status", "")).lower() and rdata.get("promotion_ready"):
        errors.append("marginal pass cannot be promotion_ready")
    return errors


_SUITE_REQUIRED_REAL_FIELDS = (
    "peak_vram_gib",
    "net_peak_vram_gib",
    "pre_settle_median_gib",
    "post_settle_median_gib",
    "settled_delta_gib",
)
_SUITE_OPTIONAL_REAL_FIELDS = (
    "baseline_vram_gib",
    "peak_host_ram_gib",
    "duration_s",
)
_SUITE_SAMPLE_FIELDS = ("pre_settle_samples_gib", "post_settle_samples_gib")


def _is_finite_real(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _suite_summary_numeric_errors(child: dict) -> list[str]:
    label = child.get("label", "<unknown>")
    errors = []
    for field in ("run_number", "config_run_count"):
        value = child.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"suite child {label} has invalid positive integer field: {field}")
    for field in _SUITE_REQUIRED_REAL_FIELDS:
        if not _is_finite_real(child.get(field)):
            errors.append(f"suite child {label} has invalid finite numeric field: {field}")
    for field in _SUITE_OPTIONAL_REAL_FIELDS:
        if field in child and not _is_finite_real(child.get(field)):
            errors.append(f"suite child {label} has invalid finite numeric field: {field}")
    for field in _SUITE_SAMPLE_FIELDS:
        samples = child.get(field)
        if not isinstance(samples, list) or not samples or not all(
            _is_finite_real(sample) for sample in samples
        ):
            errors.append(f"suite child {label} has invalid finite numeric samples: {field}")
    if not errors:
        pre_median = round(
            statistics.median(float(value) for value in child["pre_settle_samples_gib"]),
            3,
        )
        post_median = round(
            statistics.median(float(value) for value in child["post_settle_samples_gib"]),
            3,
        )
        expected = {
            "pre_settle_median_gib": pre_median,
            "post_settle_median_gib": post_median,
            "settled_delta_gib": round(post_median - pre_median, 3),
        }
        for field, expected_value in expected.items():
            if abs(float(child[field]) - expected_value) > 1e-9:
                errors.append(
                    f"suite child {label} {field} does not match recomputed "
                    f"settled samples ({child[field]!r} != {expected_value!r})"
                )
    return errors


def _is_symlink_or_reparse_point(path: Path) -> bool:
    """Return true for a symlink or Windows reparse-point path component."""
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def immutable_child_receipt_path(
    repo_root: Path,
    child_recipe: str,
    child_run_number: int,
    child_receipt: str,
) -> Path:
    """Resolve only the derived regular archive, never a mutable alias/link."""
    archive_path, _ = suite_integrity.immutable_child_receipt_paths(
        repo_root,
        child_recipe,
        child_run_number,
        child_receipt,
    )
    return archive_path


def suite_receipt_errors(rdata: dict, receipt_file: Path, repo_root: Path) -> list[str]:
    """Validate suite receipts without treating them as single-recipe receipts."""
    errors = []
    if rdata.get("suite_schema_version") != 1:
        errors.append("suite_schema_version must be 1")
    suite_name = rdata.get("suite")
    if not isinstance(suite_name, str) or not suite_name:
        errors.append("suite label is missing")
    elif receipt_file.stem != suite_name and not receipt_file.stem.startswith(f"{suite_name}_"):
        errors.append(
            f"suite receipt filename {receipt_file.stem!r} does not match {suite_name!r}"
        )
    for field in (
        "suite_run_id",
        "status",
        "manifest",
        "manifest_sha256",
        "runner_sha256",
        "lab_locks_sha256",
        "suite_runner_sha256",
        "suite_integrity_sha256",
        "recipe_sha256s",
        "boot_lane",
        "creep_tolerance_gib",
        "children",
        "failures",
        "cleanup",
    ):
        if field not in rdata:
            errors.append(f"suite field is missing: {field}")

    tolerance = rdata.get("creep_tolerance_gib")
    if not _is_finite_real(tolerance) or float(tolerance) < 0:
        errors.append("suite creep_tolerance_gib must be a finite non-negative real number")

    suite_lock_hash = rdata.get("lab_locks_sha256")
    if (
        not isinstance(suite_lock_hash, str)
        or len(suite_lock_hash) != 64
        or any(character not in "0123456789abcdef" for character in suite_lock_hash)
    ):
        errors.append("suite lab_locks_sha256 must be a lowercase SHA-256 digest")
    suite_integrity_hash = rdata.get("suite_integrity_sha256")
    if (
        not isinstance(suite_integrity_hash, str)
        or len(suite_integrity_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in suite_integrity_hash
        )
    ):
        errors.append(
            "suite suite_integrity_sha256 must be a lowercase SHA-256 digest"
        )
    is_current_alias = (
        isinstance(suite_name, str) and receipt_file.name == f"{suite_name}.json"
    )
    if is_current_alias:
        lock_helper = repo_root / "lab_locks.py"
        if not lock_helper.is_file():
            errors.append("suite-pinned lab_locks.py is missing")
        else:
            current_lock_hash = hashlib.sha256(lock_helper.read_bytes()).hexdigest()
            if suite_lock_hash != current_lock_hash:
                errors.append("suite lab_locks.py SHA-256 mismatch")

    manifest_name = rdata.get("manifest")
    manifest_data = None
    if isinstance(manifest_name, str):
        try:
            manifest_path = (repo_root / manifest_name).resolve()
            manifest_path.relative_to(repo_root)
            if not manifest_path.is_file():
                errors.append("suite manifest is missing")
            elif rdata.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
                errors.append("suite manifest SHA-256 mismatch")
            else:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_tolerance = manifest_data.get("creep_tolerance_gib")
                if not _is_finite_real(manifest_tolerance) or float(manifest_tolerance) < 0:
                    errors.append(
                        "suite manifest creep_tolerance_gib must be a finite non-negative real number"
                    )
                elif _is_finite_real(tolerance) and float(tolerance) != float(manifest_tolerance):
                    errors.append("suite creep tolerance disagrees with its hashed manifest")
        except (OSError, ValueError):
            errors.append("suite manifest path escapes the repository")

    children = rdata.get("children")
    if not isinstance(children, list):
        errors.append("suite children must be a list")
    else:
        labels = [
            child.get("label")
            for child in children
            if isinstance(child, dict)
            and isinstance(child.get("label"), str)
            and child.get("label")
        ]
        if len(labels) != len(children):
            errors.append("suite child labels are missing, malformed, or duplicated")
        elif len(set(labels)) != len(labels):
            errors.append("suite child labels are missing, malformed, or duplicated")
        if isinstance(manifest_data, dict):
            expected = [
                (member.get("label"), member.get("recipe"), member.get("role"))
                for member in manifest_data.get("sequence", [])
                if isinstance(member, dict)
            ]
            actual = [
                (child.get("label"), child.get("recipe"), child.get("role"))
                for child in children
                if isinstance(child, dict)
            ]
            if actual and actual != expected[:len(actual)]:
                errors.append("suite child order/recipe/role does not match manifest prefix")
            if rdata.get("machine_pass") is True and actual != expected:
                errors.append("machine-passing suite must contain the exact manifest sequence")

        for child in children:
            if not isinstance(child, dict):
                continue
            errors.extend(_suite_summary_numeric_errors(child))
            child_receipt = child.get("receipt")
            if not isinstance(child_receipt, str):
                errors.append("suite child receipt path is missing")
                continue
            child_recipe = child.get("recipe")
            child_run_number = child.get("run_number")
            if (
                not isinstance(child_recipe, str)
                or not child_recipe
                or Path(child_recipe).name != child_recipe
                or isinstance(child_run_number, bool)
                or not isinstance(child_run_number, int)
                or child_run_number < 1
            ):
                errors.append("suite child cannot derive an exact immutable archive path")
                continue
            try:
                child_path = immutable_child_receipt_path(
                    repo_root,
                    child_recipe,
                    child_run_number,
                    child_receipt,
                )
            except ValueError as exc:
                errors.append(str(exc))
                continue
            try:
                child_raw = child_path.read_bytes()
                if child.get("receipt_sha256") != hashlib.sha256(child_raw).hexdigest():
                    errors.append(f"suite child receipt SHA-256 mismatch: {child_receipt}")
                child_payload = json.loads(child_raw.decode("utf-8"))
                for field in (
                    "recipe",
                    "run_number",
                    "config_run_count",
                    "run_identity_sha256",
                    "status",
                    "gate_pass",
                    "warm_pass",
                    "output_path",
                    "artifact_sha256",
                    "recipe_sha256",
                    "lab_locks_sha256",
                    "server_instance",
                    "queued_prompt_sha256",
                    "execution_cache_control",
                    "suite_cache_runtime_sha256s",
                ):
                    if child.get(field) != child_payload.get(field):
                        errors.append(
                            f"suite child summary disagrees with receipt {child_receipt}: {field}"
                        )
                numeric_pairs = (
                    ("peak_vram_gib", "peak_vram_gb"),
                    ("baseline_vram_gib", "baseline_vram_gb"),
                    ("peak_host_ram_gib", "peak_host_ram_gb"),
                    ("duration_s", "duration_s"),
                )
                for summary_field, receipt_field in numeric_pairs:
                    summary_value = child.get(summary_field)
                    receipt_value = child_payload.get(receipt_field)
                    if not _is_finite_real(summary_value) or not _is_finite_real(receipt_value):
                        errors.append(
                            f"suite child numeric field is invalid for {child_receipt}: {summary_field}"
                        )
                    elif abs(float(summary_value) - float(receipt_value)) > 0.001:
                        errors.append(
                            f"suite child summary disagrees with receipt {child_receipt}: {summary_field}"
                        )
                try:
                    peak_value = child_payload.get("peak_vram_gb")
                    baseline_value = child_payload.get("baseline_vram_gb")
                    net_value = child.get("net_peak_vram_gib")
                    if not all(
                        _is_finite_real(value)
                        for value in (peak_value, baseline_value, net_value)
                    ):
                        raise ValueError
                    expected_net = round(float(peak_value) - float(baseline_value), 3)
                    if abs(float(net_value) - expected_net) > 0.001:
                        errors.append(
                            f"suite child summary disagrees with receipt {child_receipt}: net_peak_vram_gib"
                        )
                except (TypeError, ValueError):
                    errors.append(f"suite child net VRAM is invalid for {child_receipt}")
                if child_payload.get("receipt_schema_version") != CURRENT_RECEIPT_SCHEMA_VERSION:
                    errors.append(
                        f"suite child does not use receipt schema "
                        f"{CURRENT_RECEIPT_SCHEMA_VERSION}: {child_receipt}"
                    )
                if child_payload.get("lab_locks_sha256") != suite_lock_hash:
                    errors.append(
                        f"suite child lab_locks.py hash disagrees with suite pin: {child_receipt}"
                    )
                if child_payload.get("provenance_unchanged") is not True:
                    errors.append(f"suite child provenance is not stable: {child_receipt}")
                if child_payload.get("server_instance_unchanged") is not True:
                    errors.append(f"suite child server instance is not stable: {child_receipt}")
            except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                errors.append(f"suite child receipt path/data is invalid: {child_receipt}")

    if receipt_file.name == f"{suite_name}.json" and isinstance(rdata.get("suite_run_id"), str):
        archival = receipt_file.parent / f"{suite_name}_{rdata['suite_run_id']}.json"
        if not archival.is_file():
            errors.append("current suite alias has no matching archival receipt")
        elif archival.read_bytes() != receipt_file.read_bytes():
            errors.append("current suite alias bytes disagree with its archival receipt")

    if rdata.get("machine_pass") is True:
        suite_cache_runtime_hashes = rdata.get("suite_cache_runtime_sha256s")
        current_cache_runtime_hashes = None
        if not isinstance(suite_cache_runtime_hashes, dict):
            errors.append(
                "machine-passing suite must pin cache runtime source SHA-256 values"
            )
        else:
            try:
                import run_recipe as runner

                current_cache_runtime_hashes = runner.suite_cache_runtime_sha256s()
            except ValueError as exc:
                errors.append(f"suite cache runtime contract is not frozen: {exc}")
            else:
                if suite_cache_runtime_hashes != current_cache_runtime_hashes:
                    errors.append("suite cache runtime source SHA-256 mismatch")
        integrity_helper = repo_root / "suite_integrity.py"
        if not integrity_helper.is_file():
            errors.append("machine-passing suite-pinned suite_integrity.py is missing")
        else:
            current_integrity_hash = hashlib.sha256(
                integrity_helper.read_bytes()
            ).hexdigest()
            if suite_integrity_hash != current_integrity_hash:
                errors.append(
                    "machine-passing suite suite_integrity.py SHA-256 mismatch"
                )
        if rdata.get("failures"):
            errors.append("machine-passing suite cannot contain failures")
        if rdata.get("vram_creep") is not False:
            errors.append("machine-passing suite must record vram_creep=false")
        if not children:
            errors.append("machine-passing suite must contain child receipts")
        cleanup = rdata.get("cleanup")
        if not isinstance(cleanup, dict) or cleanup.get("success") is not True:
            errors.append("machine-passing suite requires proved server cleanup")
        lease_release = rdata.get("lease_release")
        if not isinstance(lease_release, dict) or lease_release.get("success") is not True:
            errors.append("machine-passing suite requires proved suite-lease release")
        if rdata.get("status") != "MACHINE SUITE PASS (human video/audio pending)":
            errors.append("machine-passing suite status is inconsistent")
        if not rdata.get("finished_at"):
            errors.append("machine-passing suite must be finalized")
        recipe_pins = rdata.get("recipe_sha256s")
        if isinstance(manifest_data, dict):
            expected_recipes = [
                member.get("recipe")
                for member in manifest_data.get("sequence", [])
                if isinstance(member, dict)
            ]
        elif isinstance(recipe_pins, dict):
            # The manifest error already blocks PASS, but still re-prove every
            # named pin instead of skipping current-byte checks entirely.
            expected_recipes = list(recipe_pins)
        else:
            expected_recipes = []
        storage_errors = suite_integrity.suite_storage_errors(
            repo_root,
            recipe_pins,
            children,
            expected_recipes=expected_recipes,
        )
        errors.extend(
            f"machine-passing suite storage verification failed: {error}"
            for error in storage_errors
        )
        manifest_sequence = (
            manifest_data.get("sequence") if isinstance(manifest_data, dict) else None
        )
        cache_evidence_errors = suite_integrity.suite_cache_evidence_errors(
            repo_root,
            rdata.get("suite_run_id"),
            manifest_sequence,
            recipe_pins,
            children,
            suite_cache_runtime_hashes,
            current_cache_runtime_hashes,
        )
        errors.extend(
            f"machine-passing suite cache verification failed: {error}"
            for error in cache_evidence_errors
        )
        try:
            import run_h3_suite

            recomputed = run_h3_suite.evaluate_suite(
                children, float(rdata.get("creep_tolerance_gib"))
            )
            if recomputed:
                errors.append(
                    "machine-passing suite fails recomputed evaluation: " + "; ".join(recomputed)
                )
        except (ImportError, TypeError, ValueError, KeyError) as exc:
            errors.append(f"machine-passing suite evaluation could not be recomputed: {exc}")
    return errors


def main():
    print("=========================================================")
    print("       vram-recipe-lab :: PAPER VALIDATION SUITE        ")
    print("=========================================================\n")

    results = []
    all_valid = True

    discovered_names = {path.stem for path in RECIPES_DIR.glob("*.json")}
    recipe_names = REQUIRED_RECIPES + sorted(discovered_names - set(REQUIRED_RECIPES))

    for recipe_name in recipe_names:
        recipe_path = RECIPES_DIR / f"{recipe_name}.json"
        if not recipe_path.exists():
            print(f"[MISSING] Required recipe file missing: {recipe_name}.json!")
            all_valid = False
            continue

        res = validate_recipe_file(recipe_path)
        results.append(res)

        status_str = "PASS" if res["valid"] else "FAIL"
        blocked_str = "[BLOCKED]" if res["blocked"] else "[ACTIVE]"
        print(f"  {status_str:4s} | {blocked_str:9s} | {recipe_name:20s} ({res['node_count']} nodes)")
        for err in res["errors"]:
            print(f"         +-- ERROR: {err}")
        for warn in res["warnings"]:
            print(f"         +-- WARN:  {warn}")

    print("\n---------------------------------------------------------")
    # Verify receipt JSON, payload labels, and any current warm certification.
    results_dir = REPO_ROOT / "results"
    receipt_errors = 0
    if results_dir.exists():
        for rf in results_dir.glob("*.json"):
            try:
                rdata = json.loads(rf.read_text(encoding="utf-8"))
                if "suite_schema_version" in rdata:
                    for invariant_error in suite_receipt_errors(rdata, rf, REPO_ROOT):
                        print(f"  [ERROR] Invalid suite receipt {rf.name}: {invariant_error}")
                        receipt_errors += 1
                    continue
                payload_recipe = rdata.get("recipe")
                if not payload_recipe:
                    print(f"  [ERROR] Receipt missing recipe label: {rf.name}")
                    receipt_errors += 1
                    continue
                expected_stem = rf.stem.split("_run")[0]
                if payload_recipe != expected_stem:
                    print(f"  [ERROR] Receipt mislabel: {rf.name} payload says '{payload_recipe}', expected '{expected_stem}'")
                    receipt_errors += 1
                is_current_receipt = rf.name == f"{payload_recipe}.json"
                recipe_file = RECIPES_DIR / f"{payload_recipe}.json"
                if is_current_receipt:
                    for invariant_error in current_certification_errors(rdata, recipe_file, REPO_ROOT):
                        print(f"  [ERROR] Invalid certification {rf.name}: {invariant_error}")
                        receipt_errors += 1
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"  [ERROR] Malformed receipt {rf.name}: {exc}")
                receipt_errors += 1

    passed_count = sum(1 for r in results if r["valid"])
    total_count = len(recipe_names)
    if receipt_errors > 0:
        print(f"Summary: {passed_count}/{total_count} recipes PAPER VALIDATED, BUT {receipt_errors} receipt integrity errors found.")
        all_valid = False
    else:
        print(f"Summary: {passed_count}/{total_count} canonical/discovered recipes PAPER VALIDATED successfully.")
    print("Note: Schema-vs-/object_info live server checks marked PENDING server window.")
    print("=========================================================\n")

    if not all_valid or passed_count != total_count or len(results) != total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
