"""Fail-closed storage checks shared by H3 suite execution and validation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CURRENT_CHILD_RECEIPT_SCHEMA_VERSION = 3
CACHE_CONTROL_MODE = "pinned-undeclared-randomnoise-input"
CACHE_NONCE_INPUT = "_vram_lab_cache_nonce"
CACHE_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
WARM_CACHE_ROLES = frozenset({"sentinel_reference", "candidate_warm"})
_CHILD_RECEIPT_FIELDS = (
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
    "final_suite_cache_runtime_sha256s",
)
_CHILD_NUMERIC_FIELDS = (
    ("peak_vram_gib", "peak_vram_gb"),
    ("baseline_vram_gib", "baseline_vram_gb"),
    ("peak_host_ram_gib", "peak_host_ram_gb"),
    ("duration_s", "duration_s"),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_finite_real(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_symlink_reparse_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _strict_directory(path: Path, label: str) -> Path:
    lexical = _absolute_lexical(path)
    try:
        if not os.path.lexists(lexical):
            raise ValueError(f"{label} is missing")
        if _is_symlink_reparse_or_junction(lexical):
            raise ValueError(f"{label} is a symlink or reparse point/junction")
        resolved = lexical.resolve(strict=True)
        if resolved != lexical or not resolved.is_dir():
            raise ValueError(f"{label} does not resolve to its exact derived directory")
        return resolved
    except ValueError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{label} cannot be proved: {exc}") from exc


def _strict_regular_file(root: Path, relative: Path, label: str) -> Path:
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise ValueError(f"{label} escapes its required root")
    lexical = root / relative
    try:
        component = root
        for part in relative.parts:
            component = component / part
            if os.path.lexists(component) and _is_symlink_reparse_or_junction(component):
                raise ValueError(
                    f"{label} contains a symlink or reparse point/junction"
                )
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
        if resolved != lexical or not resolved.is_file():
            raise ValueError(f"{label} is not an exact regular file")
        return resolved
    except ValueError:
        raise
    except FileNotFoundError:
        raise ValueError(f"{label} is missing")
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{label} cannot be proved: {exc}") from exc


def _node_sort_key(value: str) -> tuple[int, str]:
    return len(value), value


def _iter_prompt_link_sources(value: Any):
    """Mirror the runner's recursive Comfy API-link recognition exactly."""

    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
        yield value[0]
        return
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_prompt_link_sources(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_prompt_link_sources(child)


def _prompt_descendants(prompt: Mapping[str, Any], source_id: str) -> list[str]:
    descendants = {source_id}
    changed = True
    while changed:
        changed = False
        for node_id, node in prompt.items():
            if not isinstance(node_id, str) or not isinstance(node, Mapping):
                raise ValueError("suite prompt node IDs and node payloads must be objects")
            if node_id in descendants:
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, Mapping):
                raise ValueError(f"suite prompt node {node_id} inputs must be an object")
            if any(
                source in descendants
                for value in inputs.values()
                for source in _iter_prompt_link_sources(value)
            ):
                descendants.add(node_id)
                changed = True
    return sorted(descendants, key=_node_sort_key)


def _prompt_output_ancestors(prompt: Mapping[str, Any]) -> list[str]:
    reachable = {
        node_id
        for node_id, node in prompt.items()
        if isinstance(node_id, str)
        and isinstance(node, Mapping)
        and node.get("class_type") in {"SaveImage", "SaveVideo"}
    }
    stack = list(reachable)
    while stack:
        node_id = stack.pop()
        node = prompt.get(node_id)
        if not isinstance(node, Mapping):
            raise ValueError(f"suite prompt node {node_id} must be an object")
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ValueError(f"suite prompt node {node_id} inputs must be an object")
        for value in inputs.values():
            for source_id in _iter_prompt_link_sources(value):
                if source_id in prompt and source_id not in reachable:
                    reachable.add(source_id)
                    stack.append(source_id)
    return sorted(reachable, key=_node_sort_key)


def _expected_cache_contract(
    prompt: Mapping[str, Any], nonce: str
) -> tuple[str, dict[str, Any], set[str]]:
    """Derive queued prompt identity and graph closures independently of the runner."""

    if CACHE_NONCE_PATTERN.fullmatch(nonce) is None:
        raise ValueError("derived suite cache nonce is invalid")
    if not isinstance(prompt, dict):
        raise ValueError("manifest-pinned recipe prompt must be an object")
    if any(not isinstance(node_id, str) for node_id in prompt):
        raise ValueError("suite prompt node IDs must be strings")
    noise_ids = [
        node_id
        for node_id, node in prompt.items()
        if isinstance(node, Mapping) and node.get("class_type") == "RandomNoise"
    ]
    if len(noise_ids) != 1:
        raise ValueError(
            "suite cache control requires exactly one RandomNoise node, "
            f"found {noise_ids}"
        )
    noise_id = noise_ids[0]
    noise_node = prompt[noise_id]
    if not isinstance(noise_node, Mapping):
        raise ValueError("RandomNoise node must be an object")
    original_inputs = noise_node.get("inputs")
    if not isinstance(original_inputs, dict):
        raise ValueError("RandomNoise inputs must be an object")
    if set(original_inputs) != {"noise_seed"}:
        raise ValueError("RandomNoise must expose only noise_seed in the pinned recipe")
    recipe_seed = original_inputs.get("noise_seed")
    if isinstance(recipe_seed, bool) or not isinstance(recipe_seed, int):
        raise ValueError("RandomNoise noise_seed must be an integer")

    queued_prompt = copy.deepcopy(prompt)
    queued_prompt[noise_id]["inputs"][CACHE_NONCE_INPUT] = nonce
    fresh_ids = _prompt_descendants(queued_prompt, noise_id)
    reachable_ids = _prompt_output_ancestors(queued_prompt)
    stable_ids = sorted(
        (node_id for node_id in reachable_ids if node_id not in fresh_ids),
        key=_node_sort_key,
    )
    sampler_ids = sorted(
        (
            node_id
            for node_id in fresh_ids
            if isinstance(queued_prompt.get(node_id), Mapping)
            and queued_prompt[node_id].get("class_type") == "SamplerCustomAdvanced"
        ),
        key=_node_sort_key,
    )
    if not sampler_ids:
        raise ValueError("RandomNoise does not reach a SamplerCustomAdvanced node")
    encoded = json.dumps(
        queued_prompt, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return (
        hashlib.sha256(encoded).hexdigest(),
        {
            "mode": CACHE_CONTROL_MODE,
            "nonce": nonce,
            "noise_node_id": noise_id,
            "recipe_noise_seed": recipe_seed,
            "fresh_node_ids": fresh_ids,
            "stable_node_ids": stable_ids,
            "reachable_node_ids": reachable_ids,
            "sampler_node_ids": sampler_ids,
        },
        set(prompt),
    )


def _runtime_hash_mapping(value: Any, label: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    if not isinstance(value, Mapping) or not value:
        return {}, [f"{label} must be a nonempty source SHA-256 mapping"]
    normalized: dict[str, str] = {}
    for source, digest in value.items():
        if not isinstance(source, str) or not source:
            errors.append(f"{label} contains an invalid source path")
            continue
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            errors.append(f"{label} contains an invalid SHA-256 for {source!r}")
            continue
        normalized[source] = digest
    if len(normalized) != len(value):
        errors.append(f"{label} is not an exact string-to-digest mapping")
    return normalized, errors


def suite_cache_evidence_errors(
    repo_root: Path,
    suite_run_id: Any,
    manifest_sequence: Any,
    recipe_sha256s: Any,
    children: Any,
    suite_cache_runtime_sha256s: Any,
    current_cache_runtime_sha256s: Any,
) -> list[str]:
    """Recompute every PASS-critical cache claim from manifest-pinned recipes.

    Both the live suite and paper validator call this function.  Callers supply
    the freshly rehashed Comfy core source mapping so this stdlib-only helper can
    compare each child's queue-time and end-of-render hashes to current bytes.
    """

    errors: list[str] = []
    if not isinstance(suite_run_id, str) or not suite_run_id:
        errors.append("suite cache evidence requires a nonempty suite_run_id")
    if not isinstance(manifest_sequence, list) or not manifest_sequence:
        errors.append("suite cache evidence requires a nonempty manifest sequence")
        sequence: list[Any] = []
    else:
        sequence = manifest_sequence
    if not isinstance(children, list):
        errors.append("suite cache evidence children must be a list")
        child_list: list[Any] = []
    else:
        child_list = children
    if len(sequence) != len(child_list):
        errors.append("suite cache evidence children do not match manifest sequence length")

    pinned_runtime, runtime_errors = _runtime_hash_mapping(
        suite_cache_runtime_sha256s, "suite cache runtime pins"
    )
    current_runtime, current_errors = _runtime_hash_mapping(
        current_cache_runtime_sha256s, "current cache runtime hashes"
    )
    errors.extend(runtime_errors)
    errors.extend(current_errors)
    if pinned_runtime != current_runtime:
        errors.append("suite cache runtime pins do not match current source hashes")

    if not isinstance(recipe_sha256s, Mapping):
        errors.append("suite cache evidence recipe_sha256s must be a mapping")
        pins: dict[str, Any] = {}
    else:
        pins = dict(recipe_sha256s)
    try:
        root = _strict_directory(Path(repo_root), "suite repository root")
        recipes_root = _strict_directory(root / "recipes", "suite recipes root")
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    seen_labels: set[str] = set()
    for index, (member, child) in enumerate(zip(sequence, child_list)):
        if not isinstance(member, Mapping):
            errors.append(f"suite cache manifest member {index} is not an object")
            continue
        if not isinstance(child, Mapping):
            errors.append(f"suite cache child {index} is not an object")
            continue
        label = member.get("label")
        recipe = member.get("recipe")
        role = member.get("role")
        if not all(isinstance(value, str) and value for value in (label, recipe, role)):
            errors.append(f"suite cache manifest member {index} has invalid identity fields")
            continue
        if label in seen_labels:
            errors.append(f"suite cache manifest label is duplicated: {label}")
        seen_labels.add(label)
        if (
            child.get("label") != label
            or child.get("recipe") != recipe
            or child.get("role") != role
        ):
            errors.append(f"suite cache child {label} identity disagrees with manifest")

        pin = pins.get(recipe)
        if not isinstance(pin, str) or re.fullmatch(r"[0-9a-f]{64}", pin) is None:
            errors.append(f"suite cache recipe pin is invalid: {recipe}")
            continue
        if child.get("recipe_sha256") != pin:
            errors.append(f"suite cache child {label} recipe hash disagrees with manifest pin")
        try:
            recipe_path = _strict_regular_file(
                recipes_root, Path(f"{recipe}.json"), f"suite cache recipe {recipe}"
            )
            recipe_raw = recipe_path.read_bytes()
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
            continue
        if hashlib.sha256(recipe_raw).hexdigest() != pin:
            errors.append(f"suite cache recipe SHA-256 mismatch: {recipe}")
            continue
        try:
            recipe_data = json.loads(recipe_raw.decode("utf-8"))
            if not isinstance(recipe_data, dict):
                raise ValueError("recipe root is not an object")
            prompt = recipe_data.get("prompt", recipe_data)
            expected_nonce = f"{suite_run_id}:{label}"
            queued_hash, expected_control, prompt_node_ids = _expected_cache_contract(
                prompt, expected_nonce
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"suite cache recipe {recipe} cannot derive evidence: {exc}")
            continue

        if child.get("queued_prompt_sha256") != queued_hash:
            errors.append(f"suite cache child {label} queued prompt SHA-256 mismatch")
        control = child.get("execution_cache_control")
        if not isinstance(control, Mapping):
            errors.append(f"suite cache child {label} lacks cache-control evidence")
            continue
        expected_fields = {
            *expected_control,
            "cache_event_found",
            "cached_node_ids",
            "cached_fresh_node_ids",
            "fresh_execution_proved",
        }
        if set(control) != expected_fields:
            errors.append(f"suite cache child {label} cache-control field set is not exact")
        for field, expected_value in expected_control.items():
            if control.get(field) != expected_value:
                errors.append(
                    f"suite cache child {label} recomputed {field} mismatch"
                )

        cached_ids = control.get("cached_node_ids")
        if (
            not isinstance(cached_ids, list)
            or any(not isinstance(node_id, str) for node_id in cached_ids)
            or len(set(cached_ids)) != len(cached_ids)
            or cached_ids != sorted(cached_ids, key=_node_sort_key)
        ):
            errors.append(f"suite cache child {label} cached_node_ids are not canonical")
            normalized_cached: list[str] = []
        else:
            normalized_cached = cached_ids
            unknown = set(normalized_cached) - prompt_node_ids
            if unknown:
                errors.append(
                    f"suite cache child {label} cached unknown prompt nodes: "
                    f"{sorted(unknown, key=_node_sort_key)}"
                )
        expected_cached_fresh = sorted(
            set(normalized_cached) & set(expected_control["fresh_node_ids"]),
            key=_node_sort_key,
        )
        if control.get("cached_fresh_node_ids") != expected_cached_fresh:
            errors.append(
                f"suite cache child {label} cached_fresh_node_ids mismatch"
            )
        if expected_cached_fresh:
            errors.append(f"suite cache child {label} reused nonce-controlled nodes")
        if control.get("cache_event_found") is not True:
            errors.append(f"suite cache child {label} lacks an execution_cached event")
        expected_fresh_proof = (
            control.get("cache_event_found") is True and not expected_cached_fresh
        )
        if (
            control.get("fresh_execution_proved") is not expected_fresh_proof
            or expected_fresh_proof is not True
        ):
            errors.append(f"suite cache child {label} did not prove fresh execution")
        if role in WARM_CACHE_ROLES:
            stable_ids = expected_control["stable_node_ids"]
            if not stable_ids or not set(stable_ids).issubset(set(normalized_cached)):
                errors.append(
                    f"suite cache child {label} did not prove every recomputed warm cache hit"
                )

        for field, description in (
            ("suite_cache_runtime_sha256s", "queue-time runtime hashes"),
            ("final_suite_cache_runtime_sha256s", "end-of-render runtime hashes"),
        ):
            child_hashes, child_hash_errors = _runtime_hash_mapping(
                child.get(field), f"suite cache child {label} {description}"
            )
            errors.extend(child_hash_errors)
            if child_hashes != pinned_runtime or child_hashes != current_runtime:
                errors.append(
                    f"suite cache child {label} {description} disagree with suite/current pins"
                )

    return errors


def _normalized_expected_recipes(recipes: Iterable[Any]) -> tuple[set[str], list[str]]:
    expected: set[str] = set()
    errors: list[str] = []
    for recipe in recipes:
        if (
            not isinstance(recipe, str)
            or not recipe
            or Path(recipe).name != recipe
            or "/" in recipe
            or "\\" in recipe
        ):
            errors.append(f"suite manifest recipe name is invalid: {recipe!r}")
            continue
        expected.add(recipe)
    return expected, errors


def _is_valid_recipe_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and Path(value).name == value
        and "/" not in value
        and "\\" not in value
    )


def immutable_child_receipt_paths(
    repo_root: Path,
    child_recipe: str,
    child_run_number: int,
    child_receipt: str,
    *,
    require_current_alias: bool = False,
) -> tuple[Path, Path]:
    """Resolve an exact immutable archive and its distinct mutable alias."""

    if (
        not _is_valid_recipe_name(child_recipe)
        or isinstance(child_run_number, bool)
        or not isinstance(child_run_number, int)
        or child_run_number < 1
    ):
        raise ValueError("suite child cannot derive an exact immutable archive path")
    archive_name = f"{child_recipe}_run{child_run_number}.json"
    expected_receipt = f"results/{archive_name}"
    if child_receipt != expected_receipt:
        raise ValueError(
            f"suite child receipt must be exact immutable archive: {expected_receipt}"
        )

    repository_root = _strict_directory(Path(repo_root), "suite repository root")
    results_root = _strict_directory(
        repository_root / "results", "suite results root"
    )
    archive_path = _strict_regular_file(
        results_root, Path(archive_name), "suite child immutable archive"
    )
    current_alias = results_root / f"{child_recipe}.json"
    if not os.path.lexists(current_alias):
        if require_current_alias:
            raise ValueError("suite child mutable current alias is missing")
        return archive_path, current_alias
    if _is_symlink_reparse_or_junction(current_alias):
        raise ValueError(
            "suite mutable current alias is a symlink or reparse point/junction"
        )
    try:
        resolved_alias = current_alias.resolve(strict=True)
        if (
            resolved_alias != current_alias
            or resolved_alias.parent != results_root
            or not resolved_alias.is_file()
        ):
            raise ValueError(
                "suite mutable current alias is not an exact regular results file"
            )
        if os.path.samefile(archive_path, current_alias):
            raise ValueError(
                "suite child archive is the same file as the mutable current alias"
            )
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(
            "suite child archive identity cannot be distinguished from the mutable "
            f"current alias: {exc}"
        ) from exc
    return archive_path, current_alias


def _child_receipt_errors(
    repo_root: Path,
    child: Mapping[str, Any],
    *,
    require_current_alias: bool,
) -> list[str]:
    label = child.get("label", "<unknown>")
    errors: list[str] = []
    try:
        archive_path, current_alias = immutable_child_receipt_paths(
            repo_root,
            child.get("recipe"),
            child.get("run_number"),
            child.get("receipt"),
            require_current_alias=require_current_alias,
        )
    except ValueError as exc:
        return [f"suite child {label} receipt path is invalid: {exc}"]

    try:
        archive_raw = archive_path.read_bytes()
    except OSError as exc:
        return [f"suite child {label} receipt archive could not be read: {exc}"]
    if hashlib.sha256(archive_raw).hexdigest() != child.get("receipt_sha256"):
        errors.append(f"suite child {label} receipt SHA-256 mismatch")
    try:
        receipt = json.loads(archive_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [*errors, f"suite child {label} receipt JSON is invalid: {exc}"]
    if not isinstance(receipt, dict):
        return [*errors, f"suite child {label} receipt JSON is not an object"]

    for field in _CHILD_RECEIPT_FIELDS:
        if child.get(field) != receipt.get(field):
            errors.append(
                f"suite child {label} summary disagrees with receipt: {field}"
            )
    for summary_field, receipt_field in _CHILD_NUMERIC_FIELDS:
        summary_value = child.get(summary_field)
        receipt_value = receipt.get(receipt_field)
        if not _is_finite_real(summary_value) or not _is_finite_real(receipt_value):
            errors.append(
                f"suite child {label} receipt numeric field is invalid: {summary_field}"
            )
        elif abs(float(summary_value) - float(receipt_value)) > 0.001:
            errors.append(
                f"suite child {label} summary disagrees with receipt: {summary_field}"
            )
    peak = receipt.get("peak_vram_gb")
    baseline = receipt.get("baseline_vram_gb")
    net = child.get("net_peak_vram_gib")
    if not all(_is_finite_real(value) for value in (peak, baseline, net)):
        errors.append(f"suite child {label} receipt net VRAM is invalid")
    elif abs(float(net) - round(float(peak) - float(baseline), 3)) > 0.001:
        errors.append(
            f"suite child {label} summary disagrees with receipt: net_peak_vram_gib"
        )

    if receipt.get("receipt_schema_version") != CURRENT_CHILD_RECEIPT_SCHEMA_VERSION:
        errors.append(f"suite child {label} receipt schema is not current")
    if receipt.get("provenance_unchanged") is not True:
        errors.append(f"suite child {label} receipt provenance is not stable")
    if receipt.get("server_instance_unchanged") is not True:
        errors.append(f"suite child {label} receipt server instance is not stable")

    if require_current_alias:
        try:
            alias_raw = current_alias.read_bytes()
        except OSError as exc:
            errors.append(f"suite child {label} current alias could not be read: {exc}")
        else:
            if alias_raw != archive_raw:
                errors.append(
                    f"suite child {label} latest current alias bytes disagree with archive"
                )
    return errors


def suite_storage_errors(
    repo_root: Path,
    recipe_sha256s: Any,
    children: Any,
    *,
    expected_recipes: Sequence[Any],
) -> list[str]:
    """Re-prove all PASS-critical recipes, receipts, aliases, and artifacts."""

    errors: list[str] = []
    expected, expected_errors = _normalized_expected_recipes(expected_recipes)
    errors.extend(expected_errors)

    if not isinstance(recipe_sha256s, Mapping):
        errors.append("suite recipe_sha256s must be a mapping")
        pins: dict[str, Any] = {}
    else:
        pins = dict(recipe_sha256s)
    pin_names = {recipe for recipe in pins if isinstance(recipe, str) and recipe}
    if pin_names != expected or len(pin_names) != len(pins):
        errors.append("suite recipe pin set does not match manifest recipes")

    try:
        root = _strict_directory(Path(repo_root), "suite repository root")
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    try:
        recipes_root = _strict_directory(root / "recipes", "suite recipes root")
    except ValueError as exc:
        errors.append(str(exc))
        recipes_root = None
    try:
        outputs_root = _strict_directory(root / "outputs", "suite outputs root")
    except ValueError as exc:
        errors.append(str(exc))
        outputs_root = None

    if recipes_root is not None:
        for recipe in sorted(expected):
            pin = pins.get(recipe)
            if not isinstance(pin, str) or len(pin) != 64 or any(
                char not in "0123456789abcdef" for char in pin
            ):
                errors.append(f"suite recipe pin is not a SHA-256 digest: {recipe}")
                continue
            try:
                recipe_path = _strict_regular_file(
                    recipes_root,
                    Path(f"{recipe}.json"),
                    f"suite recipe {recipe}",
                )
                current_hash = _sha256_file(recipe_path)
            except (ValueError, OSError) as exc:
                errors.append(str(exc))
                continue
            if current_hash != pin:
                errors.append(f"suite recipe SHA-256 mismatch: {recipe}")

    if not isinstance(children, list):
        errors.append("suite children must be a list for storage verification")
        return errors
    latest_by_recipe: dict[str, int] = {}
    for index, child in enumerate(children):
        if isinstance(child, Mapping):
            indexed_recipe = child.get("recipe")
            if _is_valid_recipe_name(indexed_recipe):
                latest_by_recipe[indexed_recipe] = index

    for index, child in enumerate(children):
        if not isinstance(child, Mapping):
            errors.append(f"suite child {index} is not a mapping")
            continue
        label = child.get("label")
        if not isinstance(label, str) or not label:
            errors.append(f"suite child {index} label must be a nonempty string")
            continue
        recipe = child.get("recipe")
        if not _is_valid_recipe_name(recipe):
            errors.append(f"suite child {label} recipe must be a simple nonempty string")
            continue
        pin = pins.get(recipe)
        if pin is None:
            errors.append(f"suite child {label} has no manifest-pinned recipe")
        elif child.get("recipe_sha256") != pin:
            errors.append(
                f"suite child {label} recipe_sha256 does not match suite pin"
            )

        errors.extend(
            _child_receipt_errors(
                root,
                child,
                require_current_alias=(latest_by_recipe.get(recipe) == index),
            )
        )

        if outputs_root is None:
            continue
        output_name = child.get("output_path")
        if not isinstance(output_name, str) or not output_name.strip():
            errors.append(f"suite child {label} output path is missing")
            continue
        try:
            artifact_path = _strict_regular_file(
                outputs_root,
                Path(output_name),
                f"suite child {label} output artifact",
            )
            if artifact_path.stat().st_size <= 0:
                errors.append(f"suite child {label} artifact is empty")
                continue
            artifact_hash = _sha256_file(artifact_path)
        except FileNotFoundError:
            errors.append(f"suite child {label} artifact is missing: {output_name}")
            continue
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
            continue
        if artifact_hash != child.get("artifact_sha256"):
            errors.append(f"suite child {label} artifact SHA-256 mismatch")

    return errors
