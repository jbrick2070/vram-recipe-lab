#!/usr/bin/env python3
"""Static, fail-closed front-office primitives for the VRAM recipe lab.

This module deliberately has no ComfyUI launcher.  It enrolls a named bench
profile, resolves a sealed *plan*, and indexes historical receipts without
altering them.  The floor-runner integration that can execute a plan is kept
separate so a current-runner campaign cannot be silently moved to a new
runner bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).parent.resolve()
PROFILE_DIR = REPO_ROOT / "bench_profiles"
CAMPAIGN_DIR = REPO_ROOT / "campaigns"
RECIPE_DIR = REPO_ROOT / "recipes"
RESULTS_DIR = REPO_ROOT / "results"
RUNTIME_DIR = REPO_ROOT / ".runtime"

PROFILE_SCHEMA_VERSION = 1
CAMPAIGN_SCHEMA_VERSION = 1
LAUNCH_SPEC_SCHEMA_VERSION = 1
LAB_PORT = "8199"

_ID_RE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_RECIPE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\.json\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
_NODE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")

PROFILE_STATUSES = frozenset({"ENROLLED_STATIC_ONLY"})
CAMPAIGN_STATUSES = frozenset({"STATIC_ONLY", "BLOCKED_PROFILE_ENROLLMENT"})
FORBIDDEN_BOOT_TOKENS = frozenset(
    {
        "--use-sage-attention",
        "--listen",
        "--enable-cors-header",
        "--enable-manager",
    }
)
ALLOWED_PROFILE_ENVIRONMENT = frozenset({"PYTHONUTF8", "PYTHONIOENCODING", "HF_HOME"})
RESTRICTED_PARENT_ENV_PREFIXES = (
    "LAB_",
    "COMFY",
    "CUDA",
    "SAGE",
    "TORCH_",
    "TRITON_",
)
RESTRICTED_PARENT_ENV_NAMES = frozenset(
    {
        "PYTHONPATH",
        "PYTHONHOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "HF_TOKEN",
        "HUGGINGFACE_HUB_TOKEN",
        "HF_HUB_CACHE",
    }
)


class FrontOfficeError(ValueError):
    """Base error for an invalid static front-office input."""


class ProfileValidationError(FrontOfficeError):
    """An enrolled profile does not match its declared surface."""


class CampaignValidationError(FrontOfficeError):
    """A campaign or cell is malformed or cannot be planned."""


class LaunchSpecValidationError(FrontOfficeError):
    """A sealed static launch specification is forged or stale."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one JSON spelling used for semantic identity hashes."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FrontOfficeError(f"cannot canonicalize JSON value: {exc}") from exc
    return text.encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FrontOfficeError(f"{label} must be a JSON object")
    return value


def _require_exact_keys(value: Any, required: Iterable[str], label: str) -> dict[str, Any]:
    mapping = _require_mapping(value, label)
    expected = set(required)
    actual = set(mapping)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        detail: list[str] = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise FrontOfficeError(f"{label} has " + "; ".join(detail) + " keys")
    return mapping


def _require_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise FrontOfficeError(f"{label} must be a lowercase dashed identifier")
    return value


def _require_node_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _NODE_ID_RE.fullmatch(value):
        raise FrontOfficeError(f"{label} is not a safe node identifier")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FrontOfficeError(f"{label} must be a lowercase SHA-256")
    return value


def _require_git_commit(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _GIT_COMMIT_RE.fullmatch(value):
        raise FrontOfficeError(f"{label} must be a full Git commit")
    return value


def _read_json_no_bom(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FrontOfficeError(f"cannot read {label}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise FrontOfficeError(f"{label} must be UTF-8 without BOM")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontOfficeError(f"{label} is not UTF-8: {exc}") from exc
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise FrontOfficeError(f"{label} is not JSON: {exc}") from exc
    return _require_mapping(parsed, label)


def _normal_case(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _is_unc_path(raw: str) -> bool:
    return raw.startswith("\\\\") or raw.startswith("//")


def _path_components(path: Path) -> list[Path]:
    """Return existing path components from anchor to the selected target."""

    components: list[Path] = []
    cursor = path
    while True:
        components.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    components.reverse()
    return components


def _has_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise FrontOfficeError(f"cannot inspect path component {path}: {exc}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    file_attributes = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(file_attributes & reparse_flag)


def validate_absolute_nonreparse_path(
    value: Any, label: str, expected_kind: str | None = None
) -> Path:
    """Resolve one existing local path while rejecting links, junctions, and UNC paths."""

    if not isinstance(value, str) or not value:
        raise FrontOfficeError(f"{label} must be a nonempty absolute path")
    if _is_unc_path(value):
        raise FrontOfficeError(f"{label} must not be a UNC or network path")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise FrontOfficeError(f"{label} must be an absolute path")
    normalized = Path(os.path.normpath(os.path.abspath(str(candidate))))
    if not normalized.exists():
        raise FrontOfficeError(f"{label} does not exist: {normalized}")
    for component in _path_components(normalized):
        if component.exists() and _has_reparse_point(component):
            raise FrontOfficeError(f"{label} traverses a symlink, junction, or reparse point")
    try:
        resolved = normalized.resolve(strict=True)
    except OSError as exc:
        raise FrontOfficeError(f"{label} cannot be resolved: {exc}") from exc
    if _normal_case(resolved) != _normal_case(normalized):
        raise FrontOfficeError(f"{label} resolves to a different path")
    if expected_kind == "file" and not normalized.is_file():
        raise FrontOfficeError(f"{label} must be a regular file")
    if expected_kind == "directory" and not normalized.is_dir():
        raise FrontOfficeError(f"{label} must be a directory")
    return normalized


def _require_path_inside(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FrontOfficeError(f"{label} escapes its trusted root") from exc


def _verify_hashed_file(section: Mapping[str, Any], label: str) -> Path:
    path = validate_absolute_nonreparse_path(section.get("path"), f"{label}.path", "file")
    expected = _require_sha256(section.get("sha256"), f"{label}.sha256")
    actual = sha256_file(path)
    if actual != expected:
        raise ProfileValidationError(f"{label} SHA-256 drifted")
    return path


def _verification_environment() -> dict[str, str]:
    """Keep local identity probes away from inherited tokens and lab toggles."""

    values: dict[str, str] = {}
    for name in ("SystemRoot", "SYSTEMROOT", "WINDIR", "ComSpec", "COMSPEC", "PATHEXT"):
        value = os.environ.get(name)
        if value:
            values[name] = value
    return values


def _run_local_identity_command(argv: list[str], label: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            shell=False,
            env=_verification_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProfileValidationError(f"cannot inspect {label}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1] if detail else f"exit {result.returncode}"
        raise ProfileValidationError(f"cannot inspect {label}: {suffix}")
    return result.stdout.strip()


def _git_state(root: Path, label: str) -> dict[str, Any]:
    commit = _run_local_identity_command(["git", "-C", str(root), "rev-parse", "HEAD"], label)
    if not _GIT_COMMIT_RE.fullmatch(commit):
        raise ProfileValidationError(f"{label} did not report a full Git commit")
    dirty = _run_local_identity_command(
        ["git", "-C", str(root), "status", "--porcelain"], label
    )
    return {"commit": commit, "dirty": bool(dirty)}


def _python_version(executable: Path) -> str:
    command = "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    return _run_local_identity_command(
        [str(executable), "-I", "-S", "-c", command], "Python executable"
    )


def _pyproject_version(root: Path, label: str) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise ProfileValidationError(f"{label} has no pyproject.toml version record")
    try:
        parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = parsed["project"]["version"]
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise ProfileValidationError(f"cannot read {label} version: {exc}") from exc
    if not isinstance(version, str) or not version:
        raise ProfileValidationError(f"{label} version is invalid")
    return version


def _validate_boot_policy(profile: Mapping[str, Any]) -> None:
    boot = _require_exact_keys(
        profile.get("boot"),
        {"port", "fixed_argv", "forbidden_args", "sage_free"},
        "profile.boot",
    )
    if boot["port"] != LAB_PORT:
        raise ProfileValidationError("profile.boot.port must be literal 8199")
    if boot["sage_free"] is not True:
        raise ProfileValidationError("an H3 bridge profile must be Sage-free")
    if not isinstance(boot["fixed_argv"], list) or not all(
        isinstance(token, str) and token for token in boot["fixed_argv"]
    ):
        raise ProfileValidationError("profile.boot.fixed_argv must be a nonempty argv list")
    if not isinstance(boot["forbidden_args"], list) or not all(
        isinstance(token, str) and token for token in boot["forbidden_args"]
    ):
        raise ProfileValidationError("profile.boot.forbidden_args must be an argv list")
    if "--use-sage-attention" not in boot["forbidden_args"]:
        raise ProfileValidationError("profile must explicitly forbid --use-sage-attention")

    argv = boot["fixed_argv"]
    forbidden = set(boot["forbidden_args"]) | set(FORBIDDEN_BOOT_TOKENS)
    for token in argv:
        lowered = token.lower()
        if token in forbidden or lowered.startswith("--use-sage-attention="):
            raise ProfileValidationError("profile boot policy contains a forbidden Sage/global flag")
        if token.lower() in {"cmd", "cmd.exe", "powershell", "powershell.exe"}:
            raise ProfileValidationError("profile boot policy must be direct argv, never a shell")
        if any(character in token for character in ("\r", "\n", "|", "&", ">", "<")):
            raise ProfileValidationError("profile boot policy contains a shell fragment")

    def exactly_once(flag: str, expected_value: str) -> None:
        if argv.count(flag) != 1:
            raise ProfileValidationError(f"profile boot policy must contain one {flag}")
        index = argv.index(flag)
        if index + 1 >= len(argv) or argv[index + 1] != expected_value:
            raise ProfileValidationError(f"profile boot policy has wrong value for {flag}")

    exactly_once("--port", LAB_PORT)
    exactly_once("--user-directory", "{{USER_DIRECTORY}}")
    exactly_once("--output-directory", "{{OUTPUT_DIRECTORY}}")
    exactly_once("--extra-model-paths-config", "{{MODEL_PATHS_CONFIG}}")
    for required_flag in ("--cuda-malloc", "--disable-metadata", "--disable-all-custom-nodes"):
        if argv.count(required_flag) != 1:
            raise ProfileValidationError(f"profile boot policy must contain one {required_flag}")
    if argv.count("--whitelist-custom-nodes") != 1:
        raise ProfileValidationError("profile boot policy must contain one custom-node whitelist")
    whitelist_index = argv.index("--whitelist-custom-nodes")
    whitelist = argv[whitelist_index + 1 :]
    declared_nodes = [node["id"] for node in profile["custom_nodes"]]
    if whitelist != declared_nodes:
        raise ProfileValidationError("profile custom-node whitelist does not match enrolled nodes")


def validate_profile(profile: Mapping[str, Any]) -> None:
    """Fail closed unless a profile exactly matches its installed local surface."""

    profile = _require_exact_keys(
        profile,
        {
            "schema_version",
            "id",
            "status",
            "purpose",
            "python",
            "comfyui",
            "custom_nodes",
            "model_paths_config",
            "model_manifest",
            "boot",
            "environment",
            "floor_runner",
        },
        "profile",
    )
    if profile["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ProfileValidationError("profile has an unsupported schema_version")
    _require_identifier(profile["id"], "profile.id")
    if profile["status"] not in PROFILE_STATUSES:
        raise ProfileValidationError("profile.status is not enrollment-safe")
    if not isinstance(profile["purpose"], str) or not profile["purpose"].strip():
        raise ProfileValidationError("profile.purpose must be nonempty")

    python = _require_exact_keys(profile["python"], {"path", "sha256", "version"}, "profile.python")
    python_path = _verify_hashed_file(python, "profile.python")
    if not isinstance(python["version"], str) or not re.fullmatch(r"\d+\.\d+\.\d+", python["version"]):
        raise ProfileValidationError("profile.python.version must be an exact X.Y.Z version")
    if _python_version(python_path) != python["version"]:
        raise ProfileValidationError("profile Python version drifted")

    comfyui = _require_exact_keys(
        profile["comfyui"], {"root", "version", "git_commit", "main_py_sha256", "clean"}, "profile.comfyui"
    )
    comfy_root = validate_absolute_nonreparse_path(comfyui["root"], "profile.comfyui.root", "directory")
    _require_git_commit(comfyui["git_commit"], "profile.comfyui.git_commit")
    if not isinstance(comfyui["version"], str) or not re.fullmatch(r"\d+\.\d+\.\d+", comfyui["version"]):
        raise ProfileValidationError("profile.comfyui.version must be an exact X.Y.Z version")
    if comfyui["clean"] is not True:
        raise ProfileValidationError("profile.comfyui.clean must require a clean checkout")
    comfy_state = _git_state(comfy_root, "ComfyUI root")
    if comfy_state["commit"] != comfyui["git_commit"] or comfy_state["dirty"]:
        raise ProfileValidationError("ComfyUI root commit or clean state drifted")
    main_path = comfy_root / "main.py"
    if not main_path.is_file() or sha256_file(main_path) != _require_sha256(
        comfyui["main_py_sha256"], "profile.comfyui.main_py_sha256"
    ):
        raise ProfileValidationError("ComfyUI main.py hash drifted")

    custom_nodes = profile["custom_nodes"]
    if not isinstance(custom_nodes, list) or not custom_nodes:
        raise ProfileValidationError("profile.custom_nodes must be a nonempty list")
    node_ids: list[str] = []
    for index, node_value in enumerate(custom_nodes):
        node = _require_exact_keys(
            node_value,
            {"id", "path", "git_commit", "version", "init_py_sha256"},
            f"profile.custom_nodes[{index}]",
        )
        node_id = _require_node_id(node["id"], f"profile.custom_nodes[{index}].id")
        if node_id in node_ids:
            raise ProfileValidationError("profile custom-node IDs must be unique")
        node_ids.append(node_id)
        node_root = validate_absolute_nonreparse_path(
            node["path"], f"profile.custom_nodes[{index}].path", "directory"
        )
        node_state = _git_state(node_root, f"custom node {node_id}")
        if node_state["commit"] != _require_git_commit(
            node["git_commit"], f"profile.custom_nodes[{index}].git_commit"
        ) or node_state["dirty"]:
            raise ProfileValidationError(f"custom node {node_id} commit or clean state drifted")
        if _pyproject_version(node_root, f"custom node {node_id}") != node["version"]:
            raise ProfileValidationError(f"custom node {node_id} version drifted")
        init_path = node_root / "__init__.py"
        if not init_path.is_file() or sha256_file(init_path) != _require_sha256(
            node["init_py_sha256"], f"profile.custom_nodes[{index}].init_py_sha256"
        ):
            raise ProfileValidationError(f"custom node {node_id} source hash drifted")

    config = _require_exact_keys(profile["model_paths_config"], {"path", "sha256"}, "profile.model_paths_config")
    config_path = _verify_hashed_file(config, "profile.model_paths_config")
    _require_path_inside(config_path, REPO_ROOT, "profile.model_paths_config")
    manifest = _require_exact_keys(profile["model_manifest"], {"path", "sha256"}, "profile.model_manifest")
    manifest_path = _verify_hashed_file(manifest, "profile.model_manifest")
    _require_path_inside(manifest_path, REPO_ROOT, "profile.model_manifest")

    environment = _require_mapping(profile["environment"], "profile.environment")
    if set(environment) != set(ALLOWED_PROFILE_ENVIRONMENT):
        raise ProfileValidationError("profile.environment must use the small allowed environment only")
    if environment.get("PYTHONUTF8") != "1" or environment.get("PYTHONIOENCODING") != "utf-8":
        raise ProfileValidationError("profile environment must pin UTF-8 behavior")
    validate_absolute_nonreparse_path(environment.get("HF_HOME"), "profile.environment.HF_HOME", "directory")

    floor_runner = _require_exact_keys(profile["floor_runner"], {"path", "sha256"}, "profile.floor_runner")
    runner_path = _verify_hashed_file(floor_runner, "profile.floor_runner")
    _require_path_inside(runner_path, REPO_ROOT, "profile.floor_runner")
    _validate_boot_policy(profile)


def _profile_path(profile_id: str, profile_dir: Path = PROFILE_DIR) -> Path:
    _require_identifier(profile_id, "profile ID")
    profile_root = validate_absolute_nonreparse_path(str(profile_dir), "profile registry", "directory")
    path = profile_root / f"{profile_id}.json"
    if not path.is_file():
        raise ProfileValidationError(f"unknown enrolled profile: {profile_id}")
    return path


def load_enrolled_profile(profile_id: str, profile_dir: Path = PROFILE_DIR) -> dict[str, Any]:
    path = _profile_path(profile_id, profile_dir)
    profile = _read_json_no_bom(path, f"profile {profile_id}")
    if profile.get("id") != profile_id:
        raise ProfileValidationError("profile filename and profile.id differ")
    validate_profile(profile)
    return profile


def list_enrolled_profiles(profile_dir: Path = PROFILE_DIR) -> list[str]:
    registry = validate_absolute_nonreparse_path(str(profile_dir), "profile registry", "directory")
    identifiers: list[str] = []
    for path in sorted(registry.glob("*.json")):
        if path.name == "schema-v1.json":
            continue
        identifier = path.stem
        _require_identifier(identifier, f"profile filename {path.name}")
        identifiers.append(identifier)
    return identifiers


def _campaign_path(campaign_id: str, campaign_dir: Path = CAMPAIGN_DIR) -> Path:
    _require_identifier(campaign_id, "campaign ID")
    campaign_root = validate_absolute_nonreparse_path(str(campaign_dir), "campaign registry", "directory")
    path = campaign_root / f"{campaign_id}.json"
    if not path.is_file():
        raise CampaignValidationError(f"unknown campaign: {campaign_id}")
    return path


def validate_campaign(campaign: Mapping[str, Any]) -> None:
    campaign = _require_mapping(campaign, "campaign")
    required = {"schema_version", "id", "status", "purpose", "independent_variable", "profiles", "cells"}
    allowed = required | {"block_reason"}
    unknown = set(campaign) - allowed
    missing = required - set(campaign)
    if unknown or missing:
        detail: list[str] = []
        if missing:
            detail.append("missing " + ", ".join(sorted(missing)))
        if unknown:
            detail.append("unknown " + ", ".join(sorted(unknown)))
        raise CampaignValidationError("campaign has " + "; ".join(detail) + " keys")
    if campaign["schema_version"] != CAMPAIGN_SCHEMA_VERSION:
        raise CampaignValidationError("campaign has an unsupported schema_version")
    _require_identifier(campaign["id"], "campaign.id")
    if campaign["status"] not in CAMPAIGN_STATUSES:
        raise CampaignValidationError("campaign.status is unsupported")
    if not isinstance(campaign["purpose"], str) or not campaign["purpose"].strip():
        raise CampaignValidationError("campaign.purpose must be nonempty")
    if not isinstance(campaign["independent_variable"], str) or not campaign["independent_variable"].strip():
        raise CampaignValidationError("campaign.independent_variable must be nonempty")
    if campaign["status"] == "BLOCKED_PROFILE_ENROLLMENT":
        if not isinstance(campaign.get("block_reason"), str) or not campaign["block_reason"].strip():
            raise CampaignValidationError("blocked campaign must state its profile-enrollment blocker")
    elif "block_reason" in campaign:
        raise CampaignValidationError("an unblocked static campaign must not carry block_reason")
    profiles = campaign["profiles"]
    if not isinstance(profiles, list) or not profiles:
        raise CampaignValidationError("campaign.profiles must be a nonempty list")
    if len(set(profiles)) != len(profiles):
        raise CampaignValidationError("campaign profile IDs must be unique")
    for profile_id in profiles:
        _require_identifier(profile_id, "campaign profile ID")
    cells = campaign["cells"]
    if not isinstance(cells, list) or not cells:
        raise CampaignValidationError("campaign.cells must be a nonempty list")
    seen_cells: set[str] = set()
    for index, cell_value in enumerate(cells):
        cell = _require_exact_keys(
            cell_value,
            {"id", "recipe", "role", "phase", "profiles"},
            f"campaign.cells[{index}]",
        )
        cell_id = _require_identifier(cell["id"], f"campaign.cells[{index}].id")
        if cell_id in seen_cells:
            raise CampaignValidationError("campaign cell IDs must be unique")
        seen_cells.add(cell_id)
        if not isinstance(cell["recipe"], str) or not _RECIPE_NAME_RE.fullmatch(cell["recipe"]):
            raise CampaignValidationError(f"campaign.cells[{index}].recipe must be a simple recipe filename")
        if cell["role"] not in {"control", "candidate", "static"}:
            raise CampaignValidationError(f"campaign.cells[{index}].role is unsupported")
        if not isinstance(cell["phase"], str) or not cell["phase"].strip():
            raise CampaignValidationError(f"campaign.cells[{index}].phase must be nonempty")
        if not isinstance(cell["profiles"], list) or not cell["profiles"]:
            raise CampaignValidationError(f"campaign.cells[{index}].profiles must be nonempty")
        for profile_id in cell["profiles"]:
            _require_identifier(profile_id, f"campaign.cells[{index}].profile")
            if profile_id not in profiles:
                raise CampaignValidationError("cell references a profile outside its campaign")


def load_campaign(campaign_id: str, campaign_dir: Path = CAMPAIGN_DIR) -> dict[str, Any]:
    path = _campaign_path(campaign_id, campaign_dir)
    campaign = _read_json_no_bom(path, f"campaign {campaign_id}")
    if campaign.get("id") != campaign_id:
        raise CampaignValidationError("campaign filename and campaign.id differ")
    validate_campaign(campaign)
    return campaign


def list_campaigns(campaign_dir: Path = CAMPAIGN_DIR) -> list[str]:
    registry = validate_absolute_nonreparse_path(str(campaign_dir), "campaign registry", "directory")
    names: list[str] = []
    for path in sorted(registry.glob("*.json")):
        if path.name == "schema-v1.json":
            continue
        _require_identifier(path.stem, f"campaign filename {path.name}")
        names.append(path.stem)
    return names


def campaign_cell(campaign: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    _require_identifier(cell_id, "cell ID")
    for value in campaign["cells"]:
        if value["id"] == cell_id:
            return value
    raise CampaignValidationError(f"unknown cell {cell_id} for campaign {campaign['id']}")


def _recipe_path(recipe_name: str) -> Path:
    if not isinstance(recipe_name, str) or not _RECIPE_NAME_RE.fullmatch(recipe_name):
        raise CampaignValidationError("recipe must be a simple recipe filename")
    recipe_root = validate_absolute_nonreparse_path(str(RECIPE_DIR), "recipe root", "directory")
    path = recipe_root / recipe_name
    if not path.is_file():
        raise CampaignValidationError(f"campaign recipe is missing: {recipe_name}")
    _require_path_inside(path, recipe_root, "campaign recipe")
    return path


def derive_cell_namespaces(campaign_id: str, cell_id: str, profile_id: str) -> dict[str, str]:
    """Derive collision-free namespaces; this function does not create them."""

    _require_identifier(campaign_id, "campaign ID")
    _require_identifier(cell_id, "cell ID")
    _require_identifier(profile_id, "profile ID")
    suffix = Path(campaign_id) / cell_id / profile_id
    namespaces = {
        "output_directory": REPO_ROOT / "outputs" / suffix,
        "result_directory": REPO_ROOT / "results" / "runs" / suffix,
        "log_directory": REPO_ROOT / "logs" / suffix,
        "user_directory": REPO_ROOT / ".front_office_state" / suffix / "user",
        "temp_directory": REPO_ROOT / ".front_office_state" / suffix / "temp",
    }
    resolved: dict[str, str] = {}
    roots = {
        "output_directory": REPO_ROOT / "outputs",
        "result_directory": REPO_ROOT / "results",
        "log_directory": REPO_ROOT / "logs",
        "user_directory": REPO_ROOT / ".front_office_state",
        "temp_directory": REPO_ROOT / ".front_office_state",
    }
    for key, path in namespaces.items():
        absolute = path.resolve(strict=False)
        _require_path_inside(absolute, roots[key].resolve(strict=False), key)
        resolved[key] = str(absolute)
    if len(set(resolved.values())) != len(resolved):
        raise FrontOfficeError("derived cell namespaces collided")
    return resolved


def sanitized_child_environment(profile: Mapping[str, Any], parent: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the future child's minimal typed environment without inheriting selectors/secrets."""

    del parent  # Deliberate: inherited values must never choose or mutate a bench.
    environment = _require_mapping(profile.get("environment"), "profile.environment")
    if set(environment) != set(ALLOWED_PROFILE_ENVIRONMENT):
        raise ProfileValidationError("profile environment is not minimal and typed")
    result: dict[str, str] = {}
    for key in sorted(ALLOWED_PROFILE_ENVIRONMENT):
        value = environment[key]
        if not isinstance(value, str) or not value:
            raise ProfileValidationError(f"profile environment {key} is invalid")
        result[key] = value
    return result


def inherited_environment_keys_to_strip(parent: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if parent is None else parent
    names: list[str] = []
    for name, value in source.items():
        if not value:
            continue
        upper = name.upper()
        if upper in RESTRICTED_PARENT_ENV_NAMES or upper.startswith(RESTRICTED_PARENT_ENV_PREFIXES):
            names.append(name)
    return sorted(names, key=str.upper)


def canonical_server_argv(profile: Mapping[str, Any], namespaces: Mapping[str, str]) -> list[str]:
    """Return a direct executable argv; no shell string exists in this interface."""

    python = _require_mapping(profile.get("python"), "profile.python")
    comfyui = _require_mapping(profile.get("comfyui"), "profile.comfyui")
    config = _require_mapping(profile.get("model_paths_config"), "profile.model_paths_config")
    boot = _require_mapping(profile.get("boot"), "profile.boot")
    required_namespaces = {"output_directory", "user_directory"}
    if not required_namespaces.issubset(namespaces):
        raise LaunchSpecValidationError("launch namespaces omit an argv placeholder")
    placeholders = {
        "{{USER_DIRECTORY}}": namespaces["user_directory"],
        "{{OUTPUT_DIRECTORY}}": namespaces["output_directory"],
        "{{MODEL_PATHS_CONFIG}}": str(config["path"]),
    }
    args: list[str] = []
    for token in boot["fixed_argv"]:
        if token.startswith("{{") and token not in placeholders:
            raise LaunchSpecValidationError("boot policy contains an unknown placeholder")
        args.append(placeholders.get(token, token))
    return [str(python["path"]), str(Path(comfyui["root"]) / "main.py"), *args]


def front_office_source_hashes() -> dict[str, str]:
    paths = (REPO_ROOT / "front_office.py", REPO_ROOT / "labctl.py")
    return {path.name: sha256_file(path) for path in paths}


def floor_runner_source_hashes() -> dict[str, str]:
    paths = (REPO_ROOT / "run_recipe.py", REPO_ROOT / "lab_locks.py", REPO_ROOT / "boot_lab_server.cmd")
    return {path.name: sha256_file(path) for path in paths}


def active_floor_runner_identity() -> dict[str, Any]:
    source_hashes = floor_runner_source_hashes()
    return {
        "runner_sha256": source_hashes["run_recipe.py"],
        "runner_sources": source_hashes,
        "runner_bundle_sha256": canonical_sha256(source_hashes),
    }


def _semantic_launch_spec(
    campaign: Mapping[str, Any], cell: Mapping[str, Any], profile: Mapping[str, Any], recipe_path: Path
) -> dict[str, Any]:
    namespaces = derive_cell_namespaces(campaign["id"], cell["id"], profile["id"])
    argv = canonical_server_argv(profile, namespaces)
    environment = sanitized_child_environment(profile)
    floor_runner = active_floor_runner_identity()
    office_sources = front_office_source_hashes()
    try:
        recipe_bytes = recipe_path.read_bytes()
    except OSError as exc:
        raise LaunchSpecValidationError(f"cannot read selected recipe: {exc}") from exc
    if recipe_bytes.startswith(b"\xef\xbb\xbf"):
        raise LaunchSpecValidationError("selected recipe has a UTF-8 BOM")
    try:
        json.loads(recipe_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LaunchSpecValidationError(f"selected recipe is not UTF-8 JSON: {exc}") from exc
    return {
        "schema_version": LAUNCH_SPEC_SCHEMA_VERSION,
        "kind": "front_office_static_launch_spec",
        "execution_state": "STATIC_ONLY_NOT_DISPATCHABLE",
        "campaign": {"id": campaign["id"], "sha256": canonical_sha256(campaign)},
        "cell": {"id": cell["id"], "role": cell["role"], "phase": cell["phase"]},
        "profile": {
            "id": profile["id"],
            "sha256": canonical_sha256(profile),
            "status": profile["status"],
        },
        "recipe": {
            "path": str(recipe_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": sha256_bytes(recipe_bytes),
        },
        "namespaces": namespaces,
        "server": {
            "port": LAB_PORT,
            "argv": argv,
            "argv_sha256": canonical_sha256(argv),
            "environment": environment,
            "environment_sha256": canonical_sha256(environment),
            "global_sage_attention": "FORBIDDEN",
        },
        "front_office": {
            "source_sha256s": office_sources,
            "bundle_sha256": canonical_sha256(office_sources),
        },
        "floor_runner": floor_runner,
    }


def build_launch_spec(
    campaign_id: str, cell_id: str, profile_id: str, lease_nonce: str | None = None
) -> dict[str, Any]:
    """Build a static, nonce-bound plan.  It does not start a process or touch the GPU."""

    campaign = load_campaign(campaign_id)
    if campaign["status"] != "STATIC_ONLY":
        raise CampaignValidationError(
            f"campaign {campaign_id} is {campaign['status']}; direct planning is blocked"
        )
    cell = campaign_cell(campaign, cell_id)
    if profile_id not in cell["profiles"]:
        raise CampaignValidationError("selected profile is not enrolled for this campaign cell")
    profile = load_enrolled_profile(profile_id)
    recipe_path = _recipe_path(cell["recipe"])
    nonce = lease_nonce if lease_nonce is not None else secrets.token_hex(16)
    if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
        raise LaunchSpecValidationError("lease nonce must be exactly 32 lowercase hexadecimal characters")
    semantic = _semantic_launch_spec(campaign, cell, profile, recipe_path)
    return {
        "schema_version": LAUNCH_SPEC_SCHEMA_VERSION,
        "kind": "front_office_static_launch_spec",
        "lease_nonce": nonce,
        "launch_spec_sha256": canonical_sha256(semantic),
        "semantic": semantic,
    }


def validate_launch_spec(spec: Mapping[str, Any]) -> None:
    """Rebuild and compare a plan so hand-edited/stale plans fail before integration."""

    spec = _require_exact_keys(
        spec,
        {"schema_version", "kind", "lease_nonce", "launch_spec_sha256", "semantic"},
        "launch specification",
    )
    if spec["schema_version"] != LAUNCH_SPEC_SCHEMA_VERSION or spec["kind"] != "front_office_static_launch_spec":
        raise LaunchSpecValidationError("launch specification schema/kind is invalid")
    if not isinstance(spec["lease_nonce"], str) or not _NONCE_RE.fullmatch(spec["lease_nonce"]):
        raise LaunchSpecValidationError("launch specification lease nonce is invalid")
    _require_sha256(spec["launch_spec_sha256"], "launch_spec_sha256")
    semantic = _require_mapping(spec["semantic"], "launch specification semantic payload")
    try:
        campaign_id = semantic["campaign"]["id"]
        cell_id = semantic["cell"]["id"]
        profile_id = semantic["profile"]["id"]
    except (KeyError, TypeError) as exc:
        raise LaunchSpecValidationError("launch specification identity fields are malformed") from exc
    expected = build_launch_spec(campaign_id, cell_id, profile_id, spec["lease_nonce"])
    if canonical_json_bytes(spec["semantic"]) != canonical_json_bytes(expected["semantic"]):
        raise LaunchSpecValidationError("launch specification semantic content no longer matches live enrollment")
    if spec["launch_spec_sha256"] != expected["launch_spec_sha256"]:
        raise LaunchSpecValidationError("launch specification semantic hash is wrong")


def write_launch_spec(spec: Mapping[str, Any], runtime_dir: Path = RUNTIME_DIR) -> Path:
    """Atomically write a validated static plan; this is intentionally not a launch."""

    validate_launch_spec(spec)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = validate_absolute_nonreparse_path(str(runtime_dir), "runtime directory", "directory")
    semantic = _require_mapping(spec["semantic"], "launch specification semantic payload")
    filename = "-".join(
        (
            "front-office",
            semantic["campaign"]["id"],
            semantic["cell"]["id"],
            semantic["profile"]["id"],
            spec["lease_nonce"],
        )
    ) + ".json"
    destination = runtime_root / filename
    _require_path_inside(destination.resolve(strict=False), runtime_root.resolve(strict=False), "launch specification")
    temporary = runtime_root / (filename + ".tmp")
    temporary.write_bytes(canonical_json_bytes(spec) + b"\n")
    os.replace(temporary, destination)
    return destination


def classify_receipt_for_active_runner(
    receipt: Mapping[str, Any], active: Mapping[str, Any] | None = None
) -> str:
    """Return a display-only status without mutating historical receipt bytes."""

    receipt = _require_mapping(receipt, "receipt")
    active_identity = active_floor_runner_identity() if active is None else _require_mapping(active, "active runner")
    active_runner = _require_sha256(active_identity.get("runner_sha256"), "active runner SHA-256")
    active_bundle = _require_sha256(active_identity.get("runner_bundle_sha256"), "active runner bundle SHA-256")
    front_office = receipt.get("front_office")
    if isinstance(front_office, dict) and isinstance(front_office.get("runner_bundle_sha256"), str):
        bundle = front_office["runner_bundle_sha256"]
        if not _SHA256_RE.fullmatch(bundle):
            return "INVALID_RUNNER_BINDING"
        return "CURRENT_ACTIVE_RUNNER" if bundle == active_bundle else "STALE_FOR_ACTIVE_RUNNER"
    runner = receipt.get("runner_sha256")
    if runner is None and isinstance(receipt.get("identity"), dict):
        runner = receipt["identity"].get("runner_sha256")
    if not isinstance(runner, str) or not _SHA256_RE.fullmatch(runner):
        return "PRE_RUNNER_DIVISION_HISTORY"
    return "CURRENT_ACTIVE_RUNNER" if runner == active_runner else "STALE_FOR_ACTIVE_RUNNER"


def receipt_status_report(results_dir: Path = RESULTS_DIR) -> dict[str, Any]:
    root = validate_absolute_nonreparse_path(str(results_dir), "results directory", "directory")
    active = active_floor_runner_identity()
    entries: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for path in sorted(root.rglob("*.json")):
        try:
            receipt = _read_json_no_bom(path, f"receipt {path}")
        except FrontOfficeError:
            continue
        if "receipt_schema_version" not in receipt and "runner_sha256" not in receipt:
            continue
        status = classify_receipt_for_active_runner(receipt, active)
        relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        entries.append({"path": relative, "display_status": status})
        counts[status] = counts.get(status, 0) + 1
    return {
        "active_runner": active,
        "receipt_count": len(entries),
        "counts": dict(sorted(counts.items())),
        "receipts": entries,
        "immutable": True,
    }


def r0_static_census() -> dict[str, Any]:
    """Offline census: JSON/BOM, enrollment, campaigns, and receipt display state only."""

    recipe_root = validate_absolute_nonreparse_path(str(RECIPE_DIR), "recipe root", "directory")
    recipe_errors: list[dict[str, str]] = []
    recipe_paths = sorted(recipe_root.glob("*.json"))
    for path in recipe_paths:
        try:
            _read_json_no_bom(path, f"recipe {path.name}")
        except FrontOfficeError as exc:
            recipe_errors.append({"path": path.name, "error": str(exc)})
    profile_results: list[dict[str, str]] = []
    for profile_id in list_enrolled_profiles():
        try:
            load_enrolled_profile(profile_id)
            profile_results.append({"id": profile_id, "status": "VALID"})
        except FrontOfficeError as exc:
            profile_results.append({"id": profile_id, "status": "INVALID", "error": str(exc)})
    campaign_results: list[dict[str, str]] = []
    for campaign_id in list_campaigns():
        try:
            campaign = load_campaign(campaign_id)
            status = campaign["status"]
            campaign_results.append({"id": campaign_id, "status": status})
        except FrontOfficeError as exc:
            campaign_results.append({"id": campaign_id, "status": "INVALID", "error": str(exc)})
    return {
        "kind": "front_office_r0_static_census",
        "gpu_or_server_touched": False,
        "recipe_count": len(recipe_paths),
        "recipe_json_bom_errors": recipe_errors,
        "profile_results": profile_results,
        "campaign_results": campaign_results,
        "receipt_status": receipt_status_report(),
        "direct_launch": "DIRECT_LAUNCH_NOT_INTEGRATED",
    }


def format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
