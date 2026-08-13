#!/usr/bin/env python
"""Fail-closed ComfyUI-Manager offline proof for owned OTR boots.

Manager derives its config from ComfyUI's effective ``--user-directory``.
The OTR launcher and the positively identified serving argv are therefore the
authorities; a guessed default ``user`` directory is never accepted.
"""

from __future__ import annotations

import configparser
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Sequence


LAB_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = LAB_ROOT / "scratch"
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
DEFAULT_LAUNCHER = OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"
MANAGER_PRESTARTUP = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-Manager"
    r"\prestartup_script.py"
)
MANAGER_SERVER = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-Manager"
    r"\glob\manager_server.py"
)
MANAGER_CORE = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-Manager"
    r"\glob\manager_core.py"
)
OTR_HF_TOKEN_SOURCE = OTR_ROOT / "visual" / "_hf_token.py"
COMFY_FOLDER_PATHS = Path(
    r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\folder_paths.py"
)
REQUIRED_NETWORK_MODE = "offline"
OFFLINE_TOKEN_SENTINEL = "offline-disabled"
OFFLINE_CREDENTIAL_ENVIRONMENT = {
    "HF_TOKEN": OFFLINE_TOKEN_SENTINEL,
    "HUGGING_FACE_HUB_TOKEN": OFFLINE_TOKEN_SENTINEL,
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}
SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS = (
    "HUGGINGFACE_HUB_TOKEN",
    "HF_API_TOKEN",
)
KNOWN_CREDENTIAL_ENVIRONMENT_KEYS = tuple(
    sorted(
        set(OFFLINE_CREDENTIAL_ENVIRONMENT)
        | set(SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS)
    )
)
HF_TOKEN_RESOLUTION_RE = re.compile(
    r"\[hf_token\]\s+HF_TOKEN resolved from\s+(.+?)\s+\(len=(\d+)\)",
    re.IGNORECASE,
)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LAUNCHER_USER_DIRECTORY_RE = re.compile(
    r"--user-directory\s+(?:\"([^\"]+)\"|([^\s\^]+))",
    re.IGNORECASE,
)
EXECUTION_MARKERS = (
    "got prompt",
    "execution_start",
    "Prompt executed in",
    "[OTR video]",
    "OTR_VideoRenderBatch",
)
STARTUP_COMPLETE_MARKER = "[ComfyUI-Manager] All startup tasks have been completed."
NETWORK_MARKER_PATTERNS = (
    re.compile(r"\[ComfyUI-Manager\].*default cache updated:", re.IGNORECASE),
    re.compile(r"FETCH\s+ComfyRegistry\s+Data", re.IGNORECASE),
    re.compile(r"FETCH\s+DATA\s+from:", re.IGNORECASE),
    re.compile(r"\bStart fetching\.\.\.", re.IGNORECASE),
    re.compile(r"\bFetching done\.", re.IGNORECASE),
    re.compile(r"\bFETCH FAILED:", re.IGNORECASE),
    re.compile(r"\[ComfyUI-Manager\]\s+Downloading\s+['\"]", re.IGNORECASE),
    re.compile(
        r"\[ComfyUI-Manager\]\s+Failed to perform initial fetching",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://raw\.githubusercontent\.com/ltdrdata/ComfyUI-Manager",
        re.IGNORECASE,
    ),
)


class ManagerOfflineError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ManagerOfflineError(f"Cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load("wan_manager_guard_shared", SCRATCH / "humo_diet_sidecar.py")


def _stable_text(path: Path, label: str) -> tuple[str, dict[str, Any]]:
    snapshot = BASE.stable_file_snapshot(path)
    if snapshot.get("exists") is not True:
        raise ManagerOfflineError(f"Missing {label}: {path}")
    raw = path.read_bytes()
    if (
        len(raw) != int(snapshot.get("bytes") or -1)
        or BASE.sha256_bytes(raw) != snapshot.get("sha256")
    ):
        raise ManagerOfflineError(f"{label} changed during stable read: {path}")
    try:
        return raw.decode("utf-8"), snapshot
    except UnicodeError as exc:
        raise ManagerOfflineError(f"{label} is not UTF-8: {path}") from exc


def manager_source_proof() -> dict[str, Any]:
    text, snapshot = _stable_text(MANAGER_PRESTARTUP, "Manager prestartup source")
    core_text, core_snapshot = _stable_text(
        COMFY_FOLDER_PATHS, "ComfyUI folder_paths source"
    )
    server_text, server_snapshot = _stable_text(
        MANAGER_SERVER, "Manager server source"
    )
    manager_core_text, manager_core_snapshot = _stable_text(
        MANAGER_CORE, "Manager core source"
    )
    hf_text, hf_snapshot = _stable_text(
        OTR_HF_TOKEN_SOURCE, "OTR HF token resolver source"
    )
    required_tokens = (
        "folder_paths.get_user_directory(), '__manager'",
        "manager_config_path = os.path.join(manager_files_path, 'config.ini')",
    )
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise ManagerOfflineError(
            f"Manager config derivation source drifted; missing {missing}"
        )
    if "def get_system_user_directory" not in core_text:
        raise ManagerOfflineError(
            "ComfyUI core lacks get_system_user_directory; Manager config branch changed"
        )
    server_required_tokens = (
        "logging.info(\"[ComfyUI-Manager] network_mode: \" + core.get_config()['network_mode'])",
        "[ComfyUI-Manager] All startup tasks have been completed.",
        "[ComfyUI-Manager] default cache updated:",
        "[ComfyUI-Manager] Failed to perform initial fetching",
        "Start fetching...",
        "Fetching done.",
    )
    server_missing = [token for token in server_required_tokens if token not in server_text]
    if server_missing:
        raise ManagerOfflineError(
            f"Manager network/startup marker source drifted; missing {server_missing}"
        )
    core_required_tokens = (
        "'network_mode': 'public',   # public | private | offline",
        "def get_config():",
    )
    core_missing = [token for token in core_required_tokens if token not in manager_core_text]
    if core_missing:
        raise ManagerOfflineError(
            f"Manager fail-open config source drifted; missing {core_missing}"
        )
    hf_required_tokens = (
        'token = os.environ.get("HF_TOKEN") or None',
        "token = _read_from_winreg()",
        'source = "HKCU\\\\Environment"',
        "[hf_token] HF_TOKEN resolved from %s (len=%d)",
    )
    hf_missing = [token for token in hf_required_tokens if token not in hf_text]
    if hf_missing:
        raise ManagerOfflineError(
            f"OTR HF token resolver source drifted; missing {hf_missing}"
        )
    return {
        "source": snapshot,
        "comfy_folder_paths_source": core_snapshot,
        "comfy_required_token": "def get_system_user_directory",
        "manager_server_source": server_snapshot,
        "manager_server_required_tokens": list(server_required_tokens),
        "manager_core_source": manager_core_snapshot,
        "manager_core_required_tokens": list(core_required_tokens),
        "mode_authority_contract": {
            "authority": "exactly one server-log resolved network_mode announcement",
            "config_role": "preboot advisory only; missing config defaults public",
            "manager_server_source_line": 29,
            "manager_core_default_source_line": 1774,
        },
        "otr_hf_token_source": hf_snapshot,
        "otr_hf_token_required_tokens": list(hf_required_tokens),
        "offline_credential_environment_contract": {
            "set_nonsecret": dict(OFFLINE_CREDENTIAL_ENVIRONMENT),
            "scrub_key_names": list(SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS),
        },
        "required_tokens": list(required_tokens),
        "derivation": "<effective --user-directory>/__manager/config.ini",
    }


def offline_credential_environment_errors(environment: dict[str, str]) -> list[str]:
    """Validate the child boundary without ever returning ambient token values."""
    errors = []
    for key, expected in OFFLINE_CREDENTIAL_ENVIRONMENT.items():
        if environment.get(key) != expected:
            errors.append(f"{key} is not pinned to the non-secret offline contract")
    for key in SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS:
        if key in environment:
            errors.append(f"{key} was not removed from the child environment")
    case_variants = sorted(
        key
        for key in environment
        if key.upper() in KNOWN_CREDENTIAL_ENVIRONMENT_KEYS
        and key != key.upper()
    )
    if case_variants:
        errors.append(
            "case-variant credential key name(s) survived normalization: "
            + ", ".join(case_variants)
        )
    return errors


def pin_offline_credential_environment(
    source: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return a child environment with no real HF credential crossing the boundary."""
    environment = dict(os.environ if source is None else source)
    ambient_names = sorted(
        {
            key.upper()
            for key in environment
            if key.upper() in KNOWN_CREDENTIAL_ENVIRONMENT_KEYS
        }
    )
    for key in list(environment):
        if key.upper() not in KNOWN_CREDENTIAL_ENVIRONMENT_KEYS:
            continue
        environment.pop(key, None)
    environment.update(OFFLINE_CREDENTIAL_ENVIRONMENT)
    errors = offline_credential_environment_errors(environment)
    if errors:
        raise ManagerOfflineError("; ".join(errors))
    evidence = {
        "schema_version": 1,
        "set_nonsecret": dict(OFFLINE_CREDENTIAL_ENVIRONMENT),
        "scrubbed_key_names": list(SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS),
        "ambient_credential_key_names_present": ambient_names,
        "ambient_values_never_read_or_receipted": True,
        "validation_errors": [],
        "source_proof": {
            "path": str(OTR_HF_TOKEN_SOURCE),
            "sha256": BASE.sha256_file(OTR_HF_TOKEN_SOURCE),
        },
    }
    return environment, evidence


def validate_offline_credential_environment_evidence(
    evidence: dict[str, Any],
) -> list[str]:
    errors = []
    if evidence.get("schema_version") != 1:
        errors.append("offline credential evidence schema drifted")
    if evidence.get("set_nonsecret") != OFFLINE_CREDENTIAL_ENVIRONMENT:
        errors.append("offline credential non-secret pins drifted")
    if evidence.get("scrubbed_key_names") != list(
        SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS
    ):
        errors.append("offline credential scrub key set drifted")
    ambient_names = evidence.get("ambient_credential_key_names_present")
    if not isinstance(ambient_names, list) or ambient_names != sorted(set(ambient_names)):
        errors.append("ambient credential key-name receipt is not sorted and unique")
    elif any(name not in KNOWN_CREDENTIAL_ENVIRONMENT_KEYS for name in ambient_names):
        errors.append("ambient credential receipt contains an unknown key name")
    if evidence.get("ambient_values_never_read_or_receipted") is not True:
        errors.append("offline credential evidence does not attest value redaction")
    if evidence.get("validation_errors") != []:
        errors.append("offline credential child environment did not validate")
    source = evidence.get("source_proof") or {}
    if (
        Path(str(source.get("path") or "")).resolve() != OTR_HF_TOKEN_SOURCE.resolve()
        or source.get("sha256") != BASE.sha256_file(OTR_HF_TOKEN_SOURCE)
    ):
        errors.append("OTR HF token resolver source hash drifted")
    return errors


def manager_config_from_user_directory(user_directory: Path) -> Path:
    supplied = Path(user_directory)
    if not supplied.is_absolute():
        raise ManagerOfflineError(f"User directory is not absolute: {user_directory}")
    directory = Path(os.path.abspath(os.fspath(supplied)))
    return directory / "__manager" / "config.ini"


def launcher_user_directory(launcher: Path = DEFAULT_LAUNCHER) -> dict[str, Any]:
    text, snapshot = _stable_text(launcher, "OTR launcher")
    matches = LAUNCHER_USER_DIRECTORY_RE.findall(text)
    values = [quoted or bare for quoted, bare in matches]
    if len(values) != 1:
        raise ManagerOfflineError(
            f"Expected one literal --user-directory in {launcher}, found {values}"
        )
    supplied = Path(values[0])
    if not supplied.is_absolute():
        raise ManagerOfflineError(
            f"Launcher --user-directory is not absolute: {values[0]!r}"
        )
    user_directory = Path(os.path.abspath(values[0]))
    return {
        "authority": "literal --user-directory in exact OTR launcher source",
        "launcher": snapshot,
        "user_directory": str(user_directory),
        "manager_config_path": str(manager_config_from_user_directory(user_directory)),
    }


def argv_user_directory(argv: Sequence[str]) -> dict[str, Any]:
    indexes = [index for index, value in enumerate(argv) if value == "--user-directory"]
    if len(indexes) != 1 or indexes[0] + 1 >= len(argv):
        raise ManagerOfflineError(
            f"Serving argv must contain exactly one --user-directory: {list(argv)!r}"
        )
    value = str(argv[indexes[0] + 1]).strip()
    if not value or value.startswith("--"):
        raise ManagerOfflineError("Serving argv has an empty --user-directory value")
    supplied = Path(value)
    if not supplied.is_absolute():
        raise ManagerOfflineError(
            f"Serving argv --user-directory is not absolute: {value!r}"
        )
    user_directory = Path(os.path.abspath(value))
    return {
        "authority": "--user-directory in positively identified serving argv",
        "argv_index": indexes[0],
        "user_directory": str(user_directory),
        "manager_config_path": str(manager_config_from_user_directory(user_directory)),
    }


def offline_config_evidence(config_path: Path) -> dict[str, Any]:
    text, snapshot = _stable_text(config_path, "ComfyUI-Manager config")
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ManagerOfflineError(f"Manager config is invalid: {exc}") from exc
    mode = parser.get("default", "network_mode", fallback="").strip().lower()
    if mode != REQUIRED_NETWORK_MODE:
        raise ManagerOfflineError(
            f"ComfyUI-Manager network_mode must be offline, found {mode!r} at {config_path}"
        )
    return {
        **snapshot,
        "network_mode": mode,
        "section": "default",
        "key": "network_mode",
    }


def launcher_offline_evidence(launcher: Path = DEFAULT_LAUNCHER) -> dict[str, Any]:
    derivation = launcher_user_directory(launcher)
    config = offline_config_evidence(Path(derivation["manager_config_path"]))
    return {
        "phase": "preboot",
        "authority": "advisory filesystem precondition; server log is authoritative",
        "config_is_runtime_authority": False,
        "derivation": derivation,
        "manager_source": manager_source_proof(),
        "config": config,
    }


def server_offline_evidence(
    argv: Sequence[str], preboot: dict[str, Any]
) -> dict[str, Any]:
    derivation = argv_user_directory(argv)
    preboot_derivation = preboot.get("derivation") or {}
    if os.path.normcase(derivation["user_directory"]) != os.path.normcase(
        str(preboot_derivation.get("user_directory") or "")
    ):
        raise ManagerOfflineError(
            "Serving argv --user-directory differs from the exact launcher source"
        )
    config = offline_config_evidence(Path(derivation["manager_config_path"]))
    preboot_config = preboot.get("config") or {}
    if (
        os.path.normcase(str(config["path"]))
        != os.path.normcase(str(preboot_config.get("path") or ""))
        or config["sha256"] != preboot_config.get("sha256")
    ):
        raise ManagerOfflineError("Manager config path or SHA changed across server boot")
    return {
        "phase": "post-identification-pre-prompt",
        "authority": "advisory filesystem continuity; server log is authoritative",
        "config_is_runtime_authority": False,
        "derivation": derivation,
        "manager_source": manager_source_proof(),
        "config": config,
        "matches_preboot_path_and_sha": True,
    }


def validate_offline_evidence(
    evidence: dict[str, Any], *, require_current_hash: bool = True
) -> list[str]:
    errors = []
    if evidence.get("config_is_runtime_authority") is not False:
        errors.append("Manager config receipt incorrectly claims runtime authority")
    if "server log is authoritative" not in str(evidence.get("authority") or ""):
        errors.append("Manager config receipt lacks server-log authority disclosure")
    derivation = evidence.get("derivation") or {}
    config = evidence.get("config") or {}
    try:
        expected = manager_config_from_user_directory(
            Path(str(derivation.get("user_directory") or ""))
        )
    except Exception as exc:
        errors.append(f"invalid user-directory derivation: {exc}")
        expected = None
    if expected is not None and os.path.normcase(str(expected)) != os.path.normcase(
        str(derivation.get("manager_config_path") or "")
    ):
        errors.append("Manager config path is not derived from effective user-directory")
    if os.path.normcase(str(config.get("path") or "")) != os.path.normcase(
        str(derivation.get("manager_config_path") or "")
    ):
        errors.append("Manager config evidence path differs from its derivation")
    if config.get("network_mode") != REQUIRED_NETWORK_MODE:
        errors.append("Manager config evidence is not offline")
    try:
        current_source = manager_source_proof()
        retained_source = evidence.get("manager_source") or {}
        if (
            ((retained_source.get("source") or {}).get("sha256"))
            != ((current_source.get("source") or {}).get("sha256"))
            or retained_source.get("required_tokens")
            != current_source.get("required_tokens")
            or retained_source.get("derivation") != current_source.get("derivation")
            or (
                (retained_source.get("comfy_folder_paths_source") or {}).get("sha256")
                != (current_source.get("comfy_folder_paths_source") or {}).get("sha256")
            )
            or retained_source.get("comfy_required_token")
            != current_source.get("comfy_required_token")
            or (
                (retained_source.get("manager_server_source") or {}).get("sha256")
                != (current_source.get("manager_server_source") or {}).get("sha256")
            )
            or retained_source.get("manager_server_required_tokens")
            != current_source.get("manager_server_required_tokens")
            or (
                (retained_source.get("manager_core_source") or {}).get("sha256")
                != (current_source.get("manager_core_source") or {}).get("sha256")
            )
            or retained_source.get("manager_core_required_tokens")
            != current_source.get("manager_core_required_tokens")
            or retained_source.get("mode_authority_contract")
            != current_source.get("mode_authority_contract")
            or (
                (retained_source.get("otr_hf_token_source") or {}).get("sha256")
                != (current_source.get("otr_hf_token_source") or {}).get("sha256")
            )
            or retained_source.get("otr_hf_token_required_tokens")
            != current_source.get("otr_hf_token_required_tokens")
            or retained_source.get("offline_credential_environment_contract")
            != current_source.get("offline_credential_environment_contract")
        ):
            errors.append("Manager config derivation source proof drifted")
    except Exception as exc:
        errors.append(f"Manager source proof failed: {exc}")
    if require_current_hash and expected is not None:
        try:
            current = BASE.stable_file_snapshot(expected)
            if (
                current.get("exists") is not True
                or current.get("sha256") != config.get("sha256")
            ):
                errors.append("Manager config current SHA differs from receipt")
        except Exception as exc:
            errors.append(f"Manager config current hash failed: {exc}")
    return errors


def _normal_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(value.strip()))


def scan_boot_log_prefix(
    log_path: Path,
    expected_config_path: Path,
    *,
    expected_url: str = "http://127.0.0.1:8000",
    require_pre_prompt: bool = True,
) -> dict[str, Any]:
    text, snapshot = _stable_text(log_path, "attempt server log")
    clean = ANSI_RE.sub("", text)
    lines = clean.splitlines()
    config_announcements = []
    mode_announcements = []
    forbidden = []
    credential_resolution_markers = []
    forbidden_credential_markers = []
    execution = []
    execution_count = 0
    first_execution_line_number: int | None = None
    startup_complete = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("** ComfyUI-Manager config path:"):
            config_announcements.append(
                {
                    "line_number": line_number,
                    "path": stripped.split(":", 1)[1].strip(),
                    "line": stripped,
                }
            )
        mode_match = re.search(
            r"\[ComfyUI-Manager\]\s+network_mode:\s*(\S+)",
            stripped,
            flags=re.IGNORECASE,
        )
        if mode_match:
            announced_mode = mode_match.group(1).lower()
            mode_announcements.append(
                {
                    "line_number": line_number,
                    "mode": announced_mode,
                    "line": stripped,
                }
            )
            if announced_mode != REQUIRED_NETWORK_MODE:
                forbidden.append(
                    {
                        "line_number": line_number,
                        "line": stripped,
                        "patterns": ["non-offline Manager network_mode"],
                    }
                )
        if STARTUP_COMPLETE_MARKER in stripped:
            startup_complete.append(
                {"line_number": line_number, "line": stripped}
            )
        markers = [pattern.pattern for pattern in NETWORK_MARKER_PATTERNS if pattern.search(stripped)]
        if markers:
            forbidden.append(
                {"line_number": line_number, "line": stripped, "patterns": markers}
            )
        if "[hf_token]" in stripped:
            resolution_match = HF_TOKEN_RESOLUTION_RE.search(stripped)
            if resolution_match:
                source = resolution_match.group(1).strip()
                length = int(resolution_match.group(2))
                row = {
                    "line_number": line_number,
                    "source": source,
                    "length": length,
                    "line": stripped,
                }
                credential_resolution_markers.append(row)
                if source != "os.environ" or length != len(OFFLINE_TOKEN_SENTINEL):
                    forbidden_credential_markers.append(
                        {
                            **row,
                            "reason": (
                                "HF token resolver did not observe the exact "
                                "non-secret offline sentinel"
                            ),
                        }
                    )
            elif (
                "HF_TOKEN resolved" in stripped
                or "No HF_TOKEN found" in stripped
                or "winreg" in stripped.lower()
                or "HKCU" in stripped
            ):
                forbidden_credential_markers.append(
                    {
                        "line_number": line_number,
                        "line": stripped,
                        "reason": "HF token resolver used or attempted an unpinned path",
                    }
                )
        found_execution = [marker for marker in EXECUTION_MARKERS if marker in stripped]
        if found_execution:
            execution_count += 1
            if first_execution_line_number is None:
                first_execution_line_number = line_number
            if len(execution) < 20:
                execution.append(
                    {
                        "line_number": line_number,
                        "line": stripped,
                        "markers": found_execution,
                    }
                )
    errors = []
    observed_modes = [str(row.get("mode") or "") for row in mode_announcements]
    resolved_mode = observed_modes[0] if len(observed_modes) == 1 else None
    mode_line_number = (
        int(mode_announcements[0]["line_number"])
        if len(mode_announcements) == 1
        else None
    )
    startup_line_number = (
        int(startup_complete[0]["line_number"])
        if len(startup_complete) == 1
        else None
    )
    mode_precedes_startup_completion = (
        mode_line_number is not None
        and startup_line_number is not None
        and mode_line_number < startup_line_number
    )
    mode_precedes_first_execution = (
        mode_line_number is not None
        and (
            first_execution_line_number is None
            or mode_line_number < first_execution_line_number
        )
    )
    source_proof = manager_source_proof()
    authoritative_mode = {
        "authority": "server-reported resolved mode; config files are advisory only",
        "announcement_count": len(mode_announcements),
        "observed_values": observed_modes,
        "resolved_mode": resolved_mode,
        "required_mode": REQUIRED_NETWORK_MODE,
        "mode_line_number": mode_line_number,
        "startup_complete_line_number": startup_line_number,
        "first_execution_line_number": first_execution_line_number,
        "mode_precedes_startup_completion": mode_precedes_startup_completion,
        "mode_precedes_first_execution": mode_precedes_first_execution,
        "gate_evaluated_after_startup_tasks_complete": len(startup_complete) == 1,
        "manager_server_source": source_proof["manager_server_source"],
        "manager_core_default_source": source_proof["manager_core_source"],
        "source_contract": source_proof["mode_authority_contract"],
    }
    if len(config_announcements) != 1 or _normal_path(
        str(config_announcements[0].get("path") if config_announcements else "")
    ) != _normal_path(str(expected_config_path)):
        errors.append(
            "server log does not announce the one expected Manager config path"
        )
    if len(mode_announcements) != 1 or mode_announcements[0].get("mode") != "offline":
        errors.append("server log does not announce exactly one offline Manager mode")
    if not mode_precedes_startup_completion:
        errors.append("authoritative Manager mode does not precede startup completion")
    if not mode_precedes_first_execution:
        errors.append("authoritative Manager mode does not precede first execution")
    if forbidden:
        errors.append(f"server log contains {len(forbidden)} Manager network/update marker(s)")
    if forbidden_credential_markers:
        errors.append(
            "server log contains "
            f"{len(forbidden_credential_markers)} forbidden HF credential marker(s)"
        )
    if len(startup_complete) != 1:
        errors.append("server log does not prove Manager startup tasks completed exactly once")
    if require_pre_prompt and execution_count:
        errors.append("server log contains execution markers before offline boot gate")
    if f"To see the GUI go to: {expected_url}" not in clean:
        errors.append(f"server log does not bind the expected GUI URL {expected_url}")
    raw = log_path.read_bytes()
    prefix_bytes = int(snapshot["bytes"])
    if len(raw) != prefix_bytes or BASE.sha256_bytes(raw) != snapshot["sha256"]:
        raise ManagerOfflineError("Server log changed during boot-prefix capture")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "log_path": str(log_path),
        "start_offset": 0,
        "unique_attempt_log_required": True,
        "prefix_bytes": prefix_bytes,
        "prefix_sha256": snapshot["sha256"],
        "captured_log_snapshot": snapshot,
        "expected_manager_config_path": str(expected_config_path),
        "config_announcements": config_announcements,
        "network_mode_announcements": mode_announcements,
        "authoritative_server_reported_mode": authoritative_mode,
        "forbidden_network_markers": forbidden,
        "hf_token_resolution_contract": {
            "allowed_source": "os.environ",
            "allowed_length": len(OFFLINE_TOKEN_SENTINEL),
            "allowed_value_is_nonsecret_offline_sentinel": True,
            "marker_optional_if_resolver_not_imported": True,
        },
        "hf_token_resolution_markers": credential_resolution_markers,
        "forbidden_credential_markers": forbidden_credential_markers,
        "execution_markers_before_gate": execution,
        "execution_marker_line_count": execution_count,
        "first_execution_line_number": first_execution_line_number,
        "execution_marker_rows_truncated": execution_count > len(execution),
        "startup_complete_markers": startup_complete,
        "require_pre_prompt": require_pre_prompt,
        "expected_gui_url": expected_url,
    }


def authoritative_mode_errors(scan: dict[str, Any]) -> list[str]:
    errors = []
    mode = scan.get("authoritative_server_reported_mode") or {}
    current_source = manager_source_proof()
    if mode.get("authority") != (
        "server-reported resolved mode; config files are advisory only"
    ):
        errors.append("server-reported Manager mode authority label drifted")
    if (
        mode.get("announcement_count") != 1
        or mode.get("observed_values") != [REQUIRED_NETWORK_MODE]
        or mode.get("resolved_mode") != REQUIRED_NETWORK_MODE
        or mode.get("required_mode") != REQUIRED_NETWORK_MODE
    ):
        errors.append("server log does not retain exactly one resolved offline mode")
    if (
        mode.get("mode_precedes_startup_completion") is not True
        or mode.get("mode_precedes_first_execution") is not True
        or mode.get("gate_evaluated_after_startup_tasks_complete") is not True
    ):
        errors.append("server-reported mode/startup/execution order proof failed")
    if (
        (mode.get("manager_server_source") or {}).get("sha256")
        != (current_source.get("manager_server_source") or {}).get("sha256")
        or (mode.get("manager_core_default_source") or {}).get("sha256")
        != (current_source.get("manager_core_source") or {}).get("sha256")
        or mode.get("source_contract") != current_source.get("mode_authority_contract")
    ):
        errors.append("server-reported mode authority source proof drifted")
    return errors


def validate_log_prefix_binding(scan: dict[str, Any], log_path: Path) -> list[str]:
    errors = []
    if scan.get("status") != "pass" or scan.get("errors") != []:
        errors.append("Manager boot log scan did not pass")
    if scan.get("start_offset") != 0 or scan.get("unique_attempt_log_required") is not True:
        errors.append("Manager boot scan is not bound from byte offset zero")
    if scan.get("forbidden_network_markers") != []:
        errors.append("Manager boot log scan retained network markers")
    if scan.get("forbidden_credential_markers") != []:
        errors.append("Manager boot log scan retained forbidden credential markers")
    errors.extend(authoritative_mode_errors(scan))
    if scan.get("hf_token_resolution_contract") != {
        "allowed_source": "os.environ",
        "allowed_length": len(OFFLINE_TOKEN_SENTINEL),
        "allowed_value_is_nonsecret_offline_sentinel": True,
        "marker_optional_if_resolver_not_imported": True,
    }:
        errors.append("Manager boot log credential-resolution contract drifted")
    if int(scan.get("execution_marker_line_count") or 0) != 0:
        errors.append("Manager boot log prefix contains pre-gate execution")
    if len(scan.get("startup_complete_markers") or []) != 1:
        errors.append("Manager boot log prefix lacks startup completion proof")
    try:
        prefix_bytes = int(scan.get("prefix_bytes") or 0)
        with log_path.open("rb") as handle:
            prefix = handle.read(prefix_bytes)
        if len(prefix) != prefix_bytes or BASE.sha256_bytes(prefix) != scan.get(
            "prefix_sha256"
        ):
            errors.append("Manager boot log prefix changed after gate")
    except Exception as exc:
        errors.append(f"Manager boot log prefix recheck failed: {exc}")
    return errors


def validate_runtime_log_binding(scan: dict[str, Any], log_path: Path) -> list[str]:
    errors = []
    if scan.get("status") != "pass" or scan.get("errors") != []:
        errors.append("Manager runtime log scan did not pass")
    if scan.get("start_offset") != 0 or scan.get("unique_attempt_log_required") is not True:
        errors.append("Manager runtime scan is not bound from byte offset zero")
    if scan.get("forbidden_network_markers") != []:
        errors.append("Manager runtime log contains network/update markers")
    if scan.get("forbidden_credential_markers") != []:
        errors.append("Manager runtime log contains forbidden credential markers")
    errors.extend(authoritative_mode_errors(scan))
    if scan.get("hf_token_resolution_contract") != {
        "allowed_source": "os.environ",
        "allowed_length": len(OFFLINE_TOKEN_SENTINEL),
        "allowed_value_is_nonsecret_offline_sentinel": True,
        "marker_optional_if_resolver_not_imported": True,
    }:
        errors.append("Manager runtime log credential-resolution contract drifted")
    if len(scan.get("startup_complete_markers") or []) != 1:
        errors.append("Manager runtime log lacks startup completion proof")
    try:
        prefix_bytes = int(scan.get("prefix_bytes") or 0)
        with log_path.open("rb") as handle:
            prefix = handle.read(prefix_bytes)
        if len(prefix) != prefix_bytes or BASE.sha256_bytes(prefix) != scan.get(
            "prefix_sha256"
        ):
            errors.append("Manager runtime log prefix changed after scan")
    except Exception as exc:
        errors.append(f"Manager runtime log prefix recheck failed: {exc}")
    return errors


def wait_for_clean_startup_gate(
    log_path: Path,
    expected_config_path: Path,
    *,
    timeout_s: float,
    expected_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    if timeout_s < 5:
        raise ManagerOfflineError("Manager startup gate timeout must be at least 5 seconds")
    deadline = time.monotonic() + timeout_s
    last_scan: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            scan = scan_boot_log_prefix(
                log_path,
                expected_config_path,
                expected_url=expected_url,
                require_pre_prompt=True,
            )
        except ManagerOfflineError:
            time.sleep(0.25)
            continue
        last_scan = scan
        announcements = scan.get("config_announcements") or []
        if announcements and any(
            _normal_path(str(row.get("path") or ""))
            != _normal_path(str(expected_config_path))
            for row in announcements
        ):
            raise ManagerOfflineError("Manager announced an unexpected config path")
        modes = scan.get("network_mode_announcements") or []
        if any(row.get("mode") != "offline" for row in modes):
            raise ManagerOfflineError(
                f"Manager announced a non-offline mode: {modes}"
            )
        authoritative_mode = scan.get("authoritative_server_reported_mode") or {}
        if scan.get("startup_complete_markers") and (
            authoritative_mode.get("announcement_count") != 1
            or authoritative_mode.get("observed_values") != [REQUIRED_NETWORK_MODE]
            or authoritative_mode.get("resolved_mode") != REQUIRED_NETWORK_MODE
            or authoritative_mode.get("mode_precedes_startup_completion") is not True
            or authoritative_mode.get("mode_precedes_first_execution") is not True
        ):
            raise ManagerOfflineError(
                "Authoritative server-reported Manager mode failed after startup: "
                f"observed_values={authoritative_mode.get('observed_values')}, "
                f"announcement_count={authoritative_mode.get('announcement_count')}"
            )
        if scan.get("forbidden_network_markers"):
            raise ManagerOfflineError(
                "Manager network/update marker appeared before startup completed"
            )
        if scan.get("forbidden_credential_markers"):
            raise ManagerOfflineError(
                "A real, registry, missing, or malformed HF credential marker "
                "appeared before startup completed"
            )
        if int(scan.get("execution_marker_line_count") or 0) != 0:
            raise ManagerOfflineError("Execution began before Manager offline gate")
        if scan.get("status") == "pass" and scan.get("errors") == []:
            return scan
        time.sleep(0.25)
    raise ManagerOfflineError(
        f"Manager startup offline gate timed out after {timeout_s}s; last scan={last_scan}"
    )


def stable_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    text, snapshot = _stable_text(path, "Manager boot guard receipt")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManagerOfflineError(f"Manager boot guard is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManagerOfflineError("Manager boot guard is not a JSON object")
    return payload, snapshot
