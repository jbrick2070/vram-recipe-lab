#!/usr/bin/env python
"""Truthful, H3-lab-specific ComfyUI-Manager offline boot evidence.

This helper never enables Manager.  It validates the narrow test lane after the
boot script has explicitly whitelisted Manager: the effective config is advisory,
while the attempt-unique server log is the runtime authority.
"""

from __future__ import annotations

import configparser
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANAGER_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-Manager"
)
MANAGER_PRESTARTUP = MANAGER_ROOT / "prestartup_script.py"
MANAGER_SERVER = MANAGER_ROOT / "glob" / "manager_server.py"
MANAGER_CORE = MANAGER_ROOT / "glob" / "manager_core.py"
MANAGER_UTIL = MANAGER_ROOT / "glob" / "manager_util.py"
COMFY_FOLDER_PATHS = Path(
    r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\folder_paths.py"
)
EXPECTED_PYTHON = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe"
)
REQUIRED_MODE = "offline"
OFFLINE_ENVIRONMENT = {
    "HF_TOKEN": "offline-disabled",
    "HUGGING_FACE_HUB_TOKEN": "offline-disabled",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "UV_OFFLINE": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
SCRUBBED_ENVIRONMENT_KEYS = ("HUGGINGFACE_HUB_TOKEN", "HF_API_TOKEN")
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PREBOOT_MARKER = "[vram-lab-manager-preboot] "
MODE_RE = re.compile(
    r"\[ComfyUI-Manager\]\s+network_mode:\s*(\S+)\s*$", re.IGNORECASE
)
STARTUP_MARKER = "[ComfyUI-Manager] All startup tasks have been completed."
EXECUTION_MARKERS = (
    "got prompt",
    "execution_start",
    "Prompt executed in",
)
NETWORK_PATTERNS = (
    re.compile(r"\[ComfyUI-Manager\].*default cache updated:", re.IGNORECASE),
    re.compile(r"FETCH\s+ComfyRegistry\s+Data", re.IGNORECASE),
    re.compile(r"FETCH\s+DATA\s+from:", re.IGNORECASE),
    re.compile(r"\bStart fetching\.\.\.", re.IGNORECASE),
    re.compile(r"\bFetching done\.", re.IGNORECASE),
    re.compile(r"\bFETCH FAILED:", re.IGNORECASE),
    re.compile(r"\bStart updating\.\.\.", re.IGNORECASE),
    re.compile(r"\bStart update check\.\.\.", re.IGNORECASE),
    re.compile(r"\bUpdate done\.", re.IGNORECASE),
    re.compile(r"\bUpdate check done\.", re.IGNORECASE),
    re.compile(r"\bAll extensions are already up-to-date\.", re.IGNORECASE),
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
MUTATION_PATTERNS = (
    re.compile(r"ComfyUI-Manager:\s+installing dependencies\.", re.IGNORECASE),
    re.compile(r"\[ComfyUI-Manager\]\s+Restore snapshot\.", re.IGNORECASE),
    re.compile(
        r"\[ComfyUI-Manager\]\s+Starting dependency installation/\(de\)activation",
        re.IGNORECASE,
    ),
    re.compile(r"ComfyUI-Manager:\s+EXECUTE\s+=>", re.IGNORECASE),
    re.compile(r"\bInstall:\s+pip packages for\s+['\"]", re.IGNORECASE),
    re.compile(r"\bpython package is uninstalled\b", re.IGNORECASE),
    re.compile(r"\brestore PyTorch to\b", re.IGNORECASE),
    re.compile(
        r"\bdependenc(?:y|ies) (?:in pip_auto_fix\.json )?were fixed\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\[ComfyUI-Manager\]\s+Restarting to reapply dependency installation",
        re.IGNORECASE,
    ),
)
REQUIRED_DEPENDENCY_IMPORTS = ("git", "toml", "rich", "chardet")
PIP_FIXER_SINGLETON_PACKAGES = (
    "torch",
    "torchvision",
    "torchaudio",
    "comfyui_frontend_package",
)
PIP_FIXER_OPENCV_PACKAGES = (
    "opencv_contrib_python",
    "opencv_contrib_python_headless",
    "opencv_python",
    "opencv_python_headless",
)


class ManagerProbeError(RuntimeError):
    pass


_manager_pip_list_evidence_cache: dict[str, Any] | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_file(path: Path) -> dict[str, Any]:
    lexical = Path(os.path.abspath(os.fspath(path)))
    if not os.path.lexists(lexical):
        raise ManagerProbeError(f"file is missing: {lexical}")
    attributes = getattr(lexical.lstat(), "st_file_attributes", 0)
    if lexical.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise ManagerProbeError(f"file is a symlink/reparse point: {lexical}")
    if lexical.resolve(strict=True) != lexical or not lexical.is_file():
        raise ManagerProbeError(f"file does not resolve exactly: {lexical}")
    before = lexical.stat()
    raw = lexical.read_bytes()
    after = lexical.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
        or len(raw) != after.st_size
    ):
        raise ManagerProbeError(f"file changed during stable read: {lexical}")
    return {
        "path": str(lexical),
        "bytes": int(after.st_size),
        "mtime_ns": int(after.st_mtime_ns),
        "device": int(after.st_dev),
        "inode": int(after.st_ino),
        "sha256": sha256_bytes(raw),
    }


def _stable_text(path: Path) -> tuple[str, dict[str, Any]]:
    snapshot = stable_file(path)
    lexical = Path(snapshot["path"])
    raw = lexical.read_bytes()
    after = stable_file(lexical)
    if (
        after != snapshot
        or len(raw) != snapshot["bytes"]
        or sha256_bytes(raw) != snapshot["sha256"]
    ):
        raise ManagerProbeError(f"file changed after snapshot: {path}")
    try:
        return raw.decode("utf-8"), snapshot
    except UnicodeError as exc:
        raise ManagerProbeError(f"file is not UTF-8: {path}") from exc


def _stable_directory(path: Path, *, require_empty: bool = False) -> dict[str, Any]:
    """Snapshot one real directory without following links or reparse points."""
    lexical = Path(os.path.abspath(os.fspath(path)))
    if not os.path.lexists(lexical):
        raise ManagerProbeError(f"directory is missing: {lexical}")
    before_lstat = lexical.lstat()
    attributes = getattr(before_lstat, "st_file_attributes", 0)
    if lexical.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise ManagerProbeError(f"directory is a symlink/reparse point: {lexical}")
    if lexical.resolve(strict=True) != lexical or not lexical.is_dir():
        raise ManagerProbeError(f"directory does not resolve exactly: {lexical}")
    before = lexical.stat()
    entries = sorted(entry.name for entry in lexical.iterdir())
    after = lexical.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
        or before.st_dev != after.st_dev
    ):
        raise ManagerProbeError(f"directory changed during stable read: {lexical}")
    if require_empty and entries:
        raise ManagerProbeError(
            f"directory must be empty before Manager prestartup: {lexical}: {entries}"
        )
    return {
        "path": str(lexical),
        "entries": entries,
        "entry_count": len(entries),
        "mtime_ns": int(after.st_mtime_ns),
        "device": int(after.st_dev),
        "inode": int(after.st_ino),
    }


def _normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-.]+", "_", name.strip().lower())


def _installed_distribution_map() -> dict[str, list[dict[str, str]]]:
    """Return the relevant pip metadata without invoking pip or uv."""
    wanted = {
        *PIP_FIXER_SINGLETON_PACKAGES,
        *PIP_FIXER_OPENCV_PACKAGES,
        "comfy",
    }
    found: dict[str, list[dict[str, str]]] = {name: [] for name in sorted(wanted)}
    try:
        distributions = list(importlib.metadata.distributions())
    except Exception as exc:
        raise ManagerProbeError(f"cannot inspect installed distributions: {exc}") from exc
    for distribution in distributions:
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            continue
        name = _normalized_distribution_name(str(raw_name))
        if name not in wanted:
            continue
        found[name].append(
            {
                "distribution_name": str(raw_name),
                "version": str(distribution.version),
            }
        )
    for rows in found.values():
        rows.sort(key=lambda row: (row["distribution_name"].lower(), row["version"]))
    return found


def _manager_pip_list_evidence() -> dict[str, Any]:
    """Prove Manager's configured ``python -m pip list`` path works locally."""
    global _manager_pip_list_evidence_cache
    if _manager_pip_list_evidence_cache is not None:
        return json.loads(json.dumps(_manager_pip_list_evidence_cache))
    command = [str(EXPECTED_PYTHON), "-m", "pip", "list"]
    environment = dict(os.environ)
    environment.update(OFFLINE_ENVIRONMENT)
    for key in SCRUBBED_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            env=environment,
        )
    except Exception as exc:
        raise ManagerProbeError(f"Manager pip-list proof failed: {exc}") from exc
    if completed.returncode != 0:
        raise ManagerProbeError(
            "Manager pip-list proof returned nonzero: "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    parsed: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        values = line.split()
        if not values or values[0] == "Package" or values[0].startswith("-"):
            continue
        if len(values) < 2:
            raise ManagerProbeError(f"Manager pip-list row is malformed: {line!r}")
        name = values[0].lower().replace("-", "_")
        if name in parsed:
            raise ManagerProbeError(f"Manager pip-list contains duplicate {name}")
        parsed[name] = values[1]
    relevant = {
        name: parsed.get(name)
        for name in (
            *PIP_FIXER_SINGLETON_PACKAGES,
            *PIP_FIXER_OPENCV_PACKAGES,
            "comfy",
        )
    }
    evidence = {
        "command": command,
        "returncode": completed.returncode,
        "stdout_sha256": sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(completed.stderr.encode("utf-8")),
        "relevant_versions": relevant,
        "offline_environment": offline_environment_evidence(environment),
    }
    _manager_pip_list_evidence_cache = evidence
    return json.loads(json.dumps(evidence))


def _manager_config_noop_evidence(config_path: Path) -> dict[str, Any]:
    text, snapshot = _stable_text(config_path)
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ManagerProbeError(f"Manager config is invalid: {exc}") from exc
    mode = parser.get("default", "network_mode", fallback="").strip().lower()
    use_uv = parser.get("default", "use_uv", fallback="false").strip().lower()
    if mode != REQUIRED_MODE or use_uv not in {"false", "0", "no", "off"}:
        raise ManagerProbeError(
            "Manager prestartup requires network_mode=offline and use_uv=False; "
            f"found network_mode={mode!r}, use_uv={use_uv!r}"
        )
    return {
        "snapshot": snapshot,
        "network_mode": mode,
        "use_uv": False,
        "pip_list_route": "exact interpreter -m pip list",
    }


def _dependency_import_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for name in REQUIRED_DEPENDENCY_IMPORTS:
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            raise ManagerProbeError(
                f"Manager dependency import {name!r} would trigger install: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        module_path = getattr(module, "__file__", None)
        if not module_path:
            raise ManagerProbeError(f"Manager dependency import has no file: {name}")
        evidence[name] = stable_file(Path(module_path))
    return evidence


def _pip_fixer_noop_evidence(
    distributions: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    errors = []
    for name in PIP_FIXER_SINGLETON_PACKAGES:
        rows = distributions.get(name, [])
        if len(rows) != 1:
            errors.append(f"{name} must have exactly one installed distribution")
    if distributions.get("comfy"):
        errors.append("the conflicting comfy distribution must be absent")
    opencv_rows = {
        name: rows
        for name in PIP_FIXER_OPENCV_PACKAGES
        if (rows := distributions.get(name, []))
    }
    if any(len(rows) != 1 for rows in opencv_rows.values()):
        errors.append("each installed OpenCV variant must have one distribution")
    opencv_versions = {
        row[0]["version"] for row in opencv_rows.values() if len(row) == 1
    }
    if len(opencv_versions) > 1:
        errors.append("installed OpenCV variants must already share one version")
    if errors:
        raise ManagerProbeError("PIPFixer is not proven a no-op: " + "; ".join(errors))
    return {
        "conditions": {
            "comfy_distribution_absent": True,
            "torch_trio_present_and_stable": True,
            "frontend_distribution_present": True,
            "opencv_variants_already_same_version": True,
            "pip_auto_fix_absent": True,
        },
        "relevant_distributions": distributions,
        "opencv_versions": sorted(opencv_versions),
    }


def prestartup_state_evidence(user_directory: Path) -> dict[str, Any]:
    """Prove Manager prestartup has no queued or implicit mutation to perform."""
    lexical_user = Path(os.path.abspath(os.fspath(user_directory)))
    user_snapshot = _stable_directory(lexical_user)
    manager_files = lexical_user / "__manager"
    manager_snapshot = _stable_directory(manager_files)
    startup_scripts = manager_files / "startup-scripts"
    startup_snapshot = _stable_directory(startup_scripts, require_empty=True)
    restore_snapshot = startup_scripts / "restore-snapshot.json"
    install_scripts = startup_scripts / "install-scripts.txt"
    pip_auto_fix = manager_files / "pip_auto_fix.list"
    forbidden = (restore_snapshot, install_scripts, pip_auto_fix)
    present = [str(path) for path in forbidden if os.path.lexists(path)]
    if present:
        raise ManagerProbeError(
            f"Manager prestartup mutation input(s) are present: {present}"
        )
    actual_python = Path(os.path.abspath(sys.executable))
    expected_python = Path(os.path.abspath(os.fspath(EXPECTED_PYTHON)))
    if os.path.normcase(str(actual_python)) != os.path.normcase(str(expected_python)):
        raise ManagerProbeError(
            f"Manager state proof ran under the wrong Python: {actual_python}"
        )
    python_snapshot = stable_file(actual_python)
    imports = _dependency_import_evidence()
    distributions = _installed_distribution_map()
    pip_fixer = _pip_fixer_noop_evidence(distributions)
    config = _manager_config_noop_evidence(manager_files / "config.ini")
    pip_list = _manager_pip_list_evidence()
    pip_versions = pip_list["relevant_versions"]
    metadata_versions = {
        name: (rows[0]["version"] if len(rows) == 1 else None)
        for name, rows in distributions.items()
    }
    if pip_versions != metadata_versions:
        raise ManagerProbeError(
            "Manager pip-list view differs from importlib distribution evidence"
        )
    # Re-read the directories and the forbidden paths after package inspection;
    # this closes races while building the prestartup snapshot.
    if _stable_directory(lexical_user) != user_snapshot:
        raise ManagerProbeError("user directory changed during prestartup proof")
    if _stable_directory(manager_files) != manager_snapshot:
        raise ManagerProbeError("Manager state directory changed during prestartup proof")
    if _stable_directory(startup_scripts, require_empty=True) != startup_snapshot:
        raise ManagerProbeError("Manager startup-scripts changed during prestartup proof")
    late_present = [str(path) for path in forbidden if os.path.lexists(path)]
    if late_present:
        raise ManagerProbeError(
            f"Manager prestartup mutation input(s) appeared during proof: {late_present}"
        )
    payload = {
        "schema_version": 1,
        "kind": "h3-manager-prestartup-noop-state",
        "python": python_snapshot,
        # ComfyUI may rotate its ordinary ``comfyui_<port>.log`` in the user
        # directory during boot.  Bind only the directory object here; the
        # Manager subtree and mutation inputs below remain exact snapshots.
        "user_directory": {
            key: user_snapshot[key] for key in ("path", "device", "inode")
        },
        "manager_files": manager_snapshot,
        "startup_scripts": startup_snapshot,
        "scheduled_mutation_inputs": {
            "restore_snapshot": {"path": str(restore_snapshot), "absent": True},
            "install_scripts": {"path": str(install_scripts), "absent": True},
            "pip_auto_fix": {"path": str(pip_auto_fix), "absent": True},
        },
        "dependency_imports": imports,
        "manager_config": config,
        "manager_pip_list": pip_list,
        "pip_fixer_noop": pip_fixer,
    }
    return {
        **payload,
        "state_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def build_preboot_record(
    user_directory: Path, environment: dict[str, str]
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "kind": "h3-manager-preboot-record",
        "offline_environment": offline_environment_evidence(environment),
        "prestartup_state": prestartup_state_evidence(user_directory),
    }
    return {
        **payload,
        "record_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def preboot_log_line(user_directory: Path, environment: dict[str, str]) -> bytes:
    record = build_preboot_record(user_directory, environment)
    return PREBOOT_MARKER.encode("utf-8") + canonical_json_bytes(record)


def validate_preboot_record(
    record: Any, user_directory: Path
) -> tuple[dict[str, Any] | None, list[str]]:
    errors = []
    if not isinstance(record, dict):
        return None, ["Manager preboot record is not a JSON object"]
    payload = {
        key: value for key, value in record.items() if key != "record_sha256"
    }
    expected_record_sha = sha256_bytes(canonical_json_bytes(payload))
    if (
        record.get("schema_version") != 1
        or record.get("kind") != "h3-manager-preboot-record"
        or record.get("record_sha256") != expected_record_sha
    ):
        errors.append("Manager preboot record identity is invalid")
    expected_environment = offline_environment_evidence(dict(OFFLINE_ENVIRONMENT))
    if record.get("offline_environment") != expected_environment:
        errors.append("Manager preboot offline environment evidence drifted")
    try:
        current_state = prestartup_state_evidence(user_directory)
    except Exception as exc:
        current_state = None
        errors.append(f"Manager prestartup current-state proof failed: {exc}")
    if current_state is not None and record.get("prestartup_state") != current_state:
        errors.append("Manager prestartup state changed after the byte-zero snapshot")
    return current_state, errors


def source_proof() -> dict[str, Any]:
    prestartup, prestartup_receipt = _stable_text(MANAGER_PRESTARTUP)
    server, server_receipt = _stable_text(MANAGER_SERVER)
    core, core_receipt = _stable_text(MANAGER_CORE)
    folder_paths, folder_receipt = _stable_text(COMFY_FOLDER_PATHS)
    manager_util, manager_util_receipt = _stable_text(MANAGER_UTIL)
    required = {
        "prestartup": (
            "folder_paths.get_user_directory(), '__manager'",
            "manager_config_path = os.path.join(manager_files_path, 'config.ini')",
            "def ensure_dependencies():",
            "restore_snapshot_path = os.path.join(manager_files_path, \"startup-scripts\", \"restore-snapshot.json\")",
            "script_list_path = os.path.join(manager_files_path, \"startup-scripts\", \"install-scripts.txt\")",
            "pip_fixer = manager_util.PIPFixer",
            "pip_fixer.fix_broken()",
        ),
        "server": (
            "logging.info(\"[ComfyUI-Manager] network_mode: \" + core.get_config()['network_mode'])",
            STARTUP_MARKER,
        ),
        "core": (
            "'network_mode': 'public',   # public | private | offline",
            "def get_config():",
        ),
        "folder_paths": ("def get_system_user_directory",),
        "manager_util": (
            "def get_pip_cmd(force_uv=False):",
            "def get_installed_packages(renew=False):",
            "class PIPFixer:",
            "def fix_broken(self):",
            "if 'comfy' in new_pip_versions:",
            "torch_rollback(self.prev_pip_versions['torch'])",
            "if 'comfyui_frontend_package' not in new_pip_versions:",
            'pip_auto_fix_path = os.path.join(self.manager_files_path, "pip_auto_fix.list")',
        ),
    }
    texts = {
        "prestartup": prestartup,
        "server": server,
        "core": core,
        "folder_paths": folder_paths,
        "manager_util": manager_util,
    }
    missing = {
        label: [token for token in tokens if token not in texts[label]]
        for label, tokens in required.items()
    }
    missing = {label: values for label, values in missing.items() if values}
    if missing:
        raise ManagerProbeError(f"Manager offline authority source drifted: {missing}")
    return {
        "authority": "attempt-unique server log; config is advisory only",
        "fail_open_default": "public",
        "manager_prestartup": prestartup_receipt,
        "manager_server": server_receipt,
        "manager_core": core_receipt,
        "comfy_folder_paths": folder_receipt,
        "manager_util": manager_util_receipt,
        "required_tokens": {key: list(value) for key, value in required.items()},
    }


def user_directory_from_argv(argv: Sequence[str]) -> Path:
    positions = [index for index, value in enumerate(argv) if value == "--user-directory"]
    if len(positions) != 1 or positions[0] + 1 >= len(argv):
        raise ManagerProbeError("server argv must contain one --user-directory value")
    path = Path(str(argv[positions[0] + 1]))
    if not path.is_absolute():
        raise ManagerProbeError("server --user-directory must be absolute")
    return path.resolve()


def config_evidence(argv: Sequence[str]) -> dict[str, Any]:
    config_path = user_directory_from_argv(argv) / "__manager" / "config.ini"
    text, snapshot = _stable_text(config_path)
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ManagerProbeError(f"Manager config is invalid: {exc}") from exc
    mode = parser.get("default", "network_mode", fallback="").strip().lower()
    if mode != REQUIRED_MODE:
        raise ManagerProbeError(
            f"advisory Manager config must be offline, found {mode!r}: {config_path}"
        )
    return {
        "authority": "advisory precondition; server log is runtime authority",
        "network_mode": mode,
        "snapshot": snapshot,
    }


def offline_environment_evidence(environment: dict[str, str]) -> dict[str, Any]:
    errors = []
    for key, expected in OFFLINE_ENVIRONMENT.items():
        if environment.get(key) != expected:
            errors.append(f"{key} is not pinned to its non-secret offline value")
    for key in SCRUBBED_ENVIRONMENT_KEYS:
        if key in environment:
            errors.append(f"{key} was not scrubbed")
    if errors:
        raise ManagerProbeError("; ".join(errors))
    return {
        "set_nonsecret": dict(OFFLINE_ENVIRONMENT),
        "scrubbed_key_names": list(SCRUBBED_ENVIRONMENT_KEYS),
        "values_are_nonsecret": True,
    }


def _scan_text(
    text: str,
    snapshot: dict[str, Any],
    argv: Sequence[str],
    *,
    expected_url: str,
    require_pre_prompt: bool,
) -> dict[str, Any]:
    raw_preboot_starts_at_byte_zero = text.startswith(PREBOOT_MARKER)
    if raw_preboot_starts_at_byte_zero:
        raw_first_line, separator, manager_output = text.partition("\n")
        # The canonical preboot record is parsed byte-for-byte.  ANSI stripping
        # is permitted only for Manager's subsequently appended output.
        clean = raw_first_line + separator + ANSI_RE.sub("", manager_output)
    else:
        # Preserve diagnostics for a displaced marker, but the raw offset-zero
        # gate below remains irrevocably failed.
        clean = ANSI_RE.sub("", text)
    lines = clean.splitlines()
    user_directory = user_directory_from_argv(argv)
    expected_config = user_directory / "__manager" / "config.ini"
    preboot_rows = []
    preboot_parse_errors = []
    config_rows = []
    mode_rows = []
    startup_rows = []
    execution_rows = []
    network_rows = []
    mutation_rows = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(PREBOOT_MARKER):
            raw_record = stripped[len(PREBOOT_MARKER) :]
            try:
                record = json.loads(raw_record)
            except json.JSONDecodeError as exc:
                record = None
                preboot_parse_errors.append(
                    f"line {number} Manager preboot JSON is invalid: {exc}"
                )
            preboot_rows.append(
                {
                    "line_number": number,
                    "record": record,
                    "line_sha256": sha256_bytes(line.encode("utf-8")),
                }
            )
        if stripped.startswith("** ComfyUI-Manager config path:"):
            config_rows.append(
                {
                    "line_number": number,
                    "path": stripped.split(":", 1)[1].strip(),
                    "line": stripped,
                }
            )
        # Manager writes through Python logging, so the physical line normally
        # begins with an ANSI-coloured ``[INFO]`` prefix.  Match the exact
        # Manager announcement at the end of that line after stripping ANSI.
        mode_match = MODE_RE.search(stripped)
        if mode_match:
            mode_rows.append(
                {
                    "line_number": number,
                    "mode": mode_match.group(1).lower(),
                    "line": stripped,
                }
            )
        if STARTUP_MARKER in stripped:
            startup_rows.append({"line_number": number, "line": stripped})
        found_execution = [marker for marker in EXECUTION_MARKERS if marker in stripped]
        if found_execution:
            execution_rows.append(
                {"line_number": number, "line": stripped, "markers": found_execution}
            )
        patterns = [pattern.pattern for pattern in NETWORK_PATTERNS if pattern.search(stripped)]
        if patterns:
            network_rows.append(
                {"line_number": number, "line": stripped, "patterns": patterns}
            )
        mutation_patterns = [
            pattern.pattern for pattern in MUTATION_PATTERNS if pattern.search(stripped)
        ]
        if mutation_patterns:
            mutation_rows.append(
                {
                    "line_number": number,
                    "line": stripped,
                    "patterns": mutation_patterns,
                }
            )
    observed_modes = [row["mode"] for row in mode_rows]
    preboot_line = preboot_rows[0]["line_number"] if len(preboot_rows) == 1 else None
    mode_line = mode_rows[0]["line_number"] if len(mode_rows) == 1 else None
    startup_line = startup_rows[0]["line_number"] if len(startup_rows) == 1 else None
    first_execution = execution_rows[0]["line_number"] if execution_rows else None
    authority = {
        "announcement_count": len(mode_rows),
        "observed_values": observed_modes,
        "resolved_mode": observed_modes[0] if len(observed_modes) == 1 else None,
        "required_mode": REQUIRED_MODE,
        "mode_line_number": mode_line,
        "startup_complete_line_number": startup_line,
        "first_execution_line_number": first_execution,
        "mode_precedes_startup_completion": (
            mode_line is not None and startup_line is not None and mode_line < startup_line
        ),
        "mode_precedes_first_execution": (
            mode_line is not None
            and (first_execution is None or mode_line < first_execution)
        ),
    }
    errors = list(preboot_parse_errors)
    current_prestartup_state = None
    if (
        len(preboot_rows) != 1
        or preboot_line != 1
        or not raw_preboot_starts_at_byte_zero
    ):
        errors.append(
            "log must contain exactly one Manager preboot record starting at byte zero"
        )
    elif preboot_rows[0]["record"] is not None:
        current_prestartup_state, preboot_errors = validate_preboot_record(
            preboot_rows[0]["record"], user_directory
        )
        errors.extend(preboot_errors)
    first_config = config_rows[0]["line_number"] if config_rows else None
    ordered_rows = [
        value
        for value in (first_config, mode_line, startup_line, first_execution)
        if value is not None
    ]
    if preboot_line is None or any(preboot_line >= value for value in ordered_rows):
        errors.append(
            "Manager preboot record must precede config, mode, startup, and execution"
        )
    if (
        len(config_rows) != 1
        or os.path.normcase(os.path.normpath(config_rows[0]["path"]))
        != os.path.normcase(os.path.normpath(str(expected_config)))
    ):
        errors.append("log does not announce exactly the effective Manager config path")
    if observed_modes != [REQUIRED_MODE]:
        errors.append(f"log must announce exactly one offline mode; observed {observed_modes}")
    if authority["mode_precedes_startup_completion"] is not True:
        errors.append("offline mode does not precede Manager startup completion")
    if authority["mode_precedes_first_execution"] is not True:
        errors.append("offline mode does not precede first prompt execution")
    if len(startup_rows) != 1:
        errors.append("log must contain exactly one Manager startup-complete marker")
    if require_pre_prompt and execution_rows:
        errors.append("prompt execution appeared before the pre-prompt Manager gate")
    if network_rows:
        errors.append(f"log contains {len(network_rows)} network/fetch/update marker(s)")
    if mutation_rows:
        errors.append(f"log contains {len(mutation_rows)} install/restore/mutation marker(s)")
    if f"To see the GUI go to: {expected_url}" not in clean:
        errors.append(f"log does not bind expected GUI URL {expected_url}")
    source = source_proof()
    return {
        "schema_version": 1,
        "kind": "h3-manager-offline-probe-log-scan",
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "log": snapshot,
        "start_offset": 0,
        "unique_attempt_log_required": True,
        "atomically_precreated_empty_required": True,
        "preboot_record_starts_at_byte_zero": raw_preboot_starts_at_byte_zero,
        "prefix_bytes": snapshot["bytes"],
        "prefix_sha256": snapshot["sha256"],
        "expected_config_path": str(expected_config),
        "preboot_records": preboot_rows,
        "current_prestartup_state": current_prestartup_state,
        "config_announcements": config_rows,
        "authoritative_server_reported_mode": authority,
        "startup_complete_markers": startup_rows,
        "execution_markers": execution_rows,
        "network_markers": network_rows,
        "mutation_markers": mutation_rows,
        "require_pre_prompt": require_pre_prompt,
        "expected_gui_url": expected_url,
        "source_proof": source,
    }


def scan_log(
    log_path: Path,
    argv: Sequence[str],
    *,
    expected_url: str = "http://127.0.0.1:8199",
    require_pre_prompt: bool,
) -> dict[str, Any]:
    text, snapshot = _stable_text(log_path)
    return _scan_text(
        text,
        snapshot,
        argv,
        expected_url=expected_url,
        require_pre_prompt=require_pre_prompt,
    )


def wait_for_pre_prompt_gate(
    log_path: Path,
    argv: Sequence[str],
    *,
    expected_url: str = "http://127.0.0.1:8199",
    timeout_s: float = 45.0,
    poll_s: float = 0.25,
) -> dict[str, Any]:
    """Wait for Manager startup, aborting immediately on irrevocable evidence."""
    deadline = time.monotonic() + timeout_s
    last_scan: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if not log_path.is_file():
            time.sleep(poll_s)
            continue
        last_scan = scan_log(
            log_path,
            argv,
            expected_url=expected_url,
            require_pre_prompt=True,
        )
        authority = last_scan.get("authoritative_server_reported_mode") or {}
        observed = authority.get("observed_values") or []
        config_rows = last_scan.get("config_announcements") or []
        expected_config = last_scan.get("expected_config_path")
        wrong_config = any(
            os.path.normcase(os.path.normpath(str(row.get("path", ""))))
            != os.path.normcase(os.path.normpath(str(expected_config)))
            for row in config_rows
        )
        if (
            any(mode != REQUIRED_MODE for mode in observed)
            or len(observed) > 1
            or len(last_scan.get("preboot_records") or []) != 1
            or last_scan.get("current_prestartup_state") is None
            or len(config_rows) > 1
            or wrong_config
            or last_scan.get("network_markers")
            or last_scan.get("mutation_markers")
            or last_scan.get("execution_markers")
            or len(last_scan.get("startup_complete_markers") or []) > 1
        ):
            raise ManagerProbeError(
                "irrevocable Manager offline pre-prompt failure: "
                f"{last_scan.get('errors')}"
            )
        if last_scan.get("status") == "pass" and last_scan.get("errors") == []:
            binding_errors = validate_scan_binding(
                last_scan, log_path, argv, expected_url=expected_url
            )
            if binding_errors:
                raise ManagerProbeError("; ".join(binding_errors))
            return last_scan
        time.sleep(poll_s)
    raise ManagerProbeError(
        f"Manager offline startup gate timed out after {timeout_s:g}s; "
        f"last errors={(last_scan or {}).get('errors')}"
    )


def validate_scan_binding(
    scan: dict[str, Any],
    log_path: Path,
    argv: Sequence[str],
    *,
    expected_url: str = "http://127.0.0.1:8199",
) -> list[str]:
    errors = []
    if (
        scan.get("schema_version") != 1
        or scan.get("kind") != "h3-manager-offline-probe-log-scan"
        or scan.get("status") != "pass"
        or scan.get("errors") != []
    ):
        errors.append("stored Manager probe scan did not pass")
    if (
        scan.get("start_offset") != 0
        or scan.get("unique_attempt_log_required") is not True
        or scan.get("atomically_precreated_empty_required") is not True
        or scan.get("preboot_record_starts_at_byte_zero") is not True
    ):
        errors.append("stored Manager probe scan is not bound from byte zero")
    preboot_rows = scan.get("preboot_records") or []
    if (
        len(preboot_rows) != 1
        or preboot_rows[0].get("line_number") != 1
        or not isinstance(preboot_rows[0].get("record"), dict)
        or scan.get("current_prestartup_state")
        != preboot_rows[0].get("record", {}).get("prestartup_state")
    ):
        errors.append("stored Manager preboot state proof drifted")
    authority = scan.get("authoritative_server_reported_mode") or {}
    if (
        authority.get("announcement_count") != 1
        or authority.get("observed_values") != [REQUIRED_MODE]
        or authority.get("resolved_mode") != REQUIRED_MODE
        or authority.get("mode_precedes_startup_completion") is not True
        or authority.get("mode_precedes_first_execution") is not True
    ):
        errors.append("stored Manager probe authority fields drifted")
    if scan.get("network_markers") != []:
        errors.append("stored Manager probe contains network markers")
    if scan.get("mutation_markers") != []:
        errors.append("stored Manager probe contains mutation markers")
    try:
        resolved_log = log_path.resolve()
        retained_log = scan.get("log") or {}
        prefix_bytes = int(scan.get("prefix_bytes") or 0)
        if (
            prefix_bytes <= 0
            or retained_log.get("path") != str(resolved_log)
            or retained_log.get("bytes") != prefix_bytes
            or retained_log.get("sha256") != scan.get("prefix_sha256")
            or scan.get("expected_gui_url") != expected_url
        ):
            errors.append("Manager probe retained log identity drifted")
        with log_path.open("rb") as handle:
            prefix = handle.read(prefix_bytes)
        if len(prefix) != prefix_bytes or sha256_bytes(prefix) != scan.get(
            "prefix_sha256"
        ):
            errors.append("Manager probe log prefix changed")
        try:
            prefix_text = prefix.decode("utf-8")
        except UnicodeError as exc:
            raise ManagerProbeError("Manager probe log prefix is not UTF-8") from exc
        recomputed = _scan_text(
            prefix_text,
            retained_log,
            argv,
            expected_url=expected_url,
            require_pre_prompt=scan.get("require_pre_prompt") is True,
        )
        semantic_fields = (
            "schema_version",
            "kind",
            "status",
            "errors",
            "start_offset",
            "unique_attempt_log_required",
            "atomically_precreated_empty_required",
            "preboot_record_starts_at_byte_zero",
            "expected_config_path",
            "preboot_records",
            "current_prestartup_state",
            "config_announcements",
            "authoritative_server_reported_mode",
            "startup_complete_markers",
            "execution_markers",
            "network_markers",
            "mutation_markers",
            "require_pre_prompt",
            "expected_gui_url",
            "source_proof",
        )
        for field in semantic_fields:
            if scan.get(field) != recomputed.get(field):
                errors.append(f"Manager probe stored {field} differs from log prefix")
    except Exception as exc:
        errors.append(f"Manager probe binding recheck failed: {exc}")
    return errors


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
