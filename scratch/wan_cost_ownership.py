#!/usr/bin/env python
"""Exact owned-process-chain proof for the OTR WAN cost ladder."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Callable, Sequence

import psutil


LAB_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_SOURCE = Path(__file__).resolve()
POLICY_PRECEDENT = LAB_ROOT / "lab_locks.py"
EXPECTED_VENV_LAUNCHER = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe"
)
PYVENV_CONFIG = EXPECTED_VENV_LAUNCHER.parents[1] / "pyvenv.cfg"
POLICY_NAME = "exact-owned-cmd-direct-or-certified-windows-venv-one-hop"
PRECEDENT_TOKENS = (
    "def _is_verified_windows_venv_launcher_chain(",
    "launcher_argv[1:] != child_argv[1:]",
    "child_created - launcher_created <= 5.0",
)


class OwnershipError(RuntimeError):
    pass


def _source_receipt(path: Path) -> dict[str, Any]:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
        or len(raw) != after.st_size
    ):
        raise OwnershipError(f"Ownership-policy source changed during read: {path}")
    return {
        "path": str(path),
        "bytes": int(after.st_size),
        "mtime_ns": int(after.st_mtime_ns),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _normal_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(value)))


def _same_path(left: str, right: str) -> bool:
    return _normal_path(left) == _normal_path(right)


def _identity(process: psutil.Process) -> dict[str, Any]:
    return {
        "pid": int(process.pid),
        "parent_pid": int(process.ppid()),
        "process_create_time": float(process.create_time()),
        "executable": str(process.exe()),
        "argv": list(process.cmdline()),
    }


def launcher_argv_matches(actual: Sequence[str], expected: Sequence[str]) -> bool:
    if len(actual) != 6 or len(expected) != 6:
        return False
    return (
        _same_path(str(actual[0]), str(expected[0]))
        and [str(value).lower() for value in actual[1:3]] == ["/d", "/c"]
        and _same_path(str(actual[3]), str(expected[3]))
        and _same_path(str(actual[4]), str(expected[4]))
        and str(actual[5]) == "WAN"
    )


def policy_precedent() -> dict[str, Any]:
    text = POLICY_PRECEDENT.read_text(encoding="utf-8")
    missing = [token for token in PRECEDENT_TOKENS if token not in text]
    if missing:
        raise OwnershipError(f"lab_locks one-hop precedent drifted: {missing}")
    return {
        "source": _source_receipt(POLICY_PRECEDENT),
        "required_tokens": list(PRECEDENT_TOKENS),
        "adaptation": (
            "owned cmd launcher -> exact venv python shim -> serving interpreter; "
            "same argv[1:] and <=5s from shim to serving interpreter"
        ),
    }


def validator_source_receipt() -> dict[str, Any]:
    return _source_receipt(VALIDATOR_SOURCE)


def venv_base_interpreter_receipt(
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Derive one exact base ``python.exe`` from one absolute pyvenv home row."""
    config = PYVENV_CONFIG if config_path is None else Path(config_path)
    config_receipt = _source_receipt(config)
    try:
        text = config.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise OwnershipError(f"pyvenv.cfg is not UTF-8: {config}") from exc
    if _source_receipt(config) != config_receipt:
        raise OwnershipError(f"pyvenv.cfg changed during parse: {config}")
    home_values = []
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() == "home":
            home_values.append(value.strip())
    if len(home_values) != 1 or not home_values[0]:
        raise OwnershipError(
            f"pyvenv.cfg must contain exactly one nonempty home row: {config}"
        )
    home = Path(home_values[0])
    if not home.is_absolute():
        raise OwnershipError(f"pyvenv.cfg home is not absolute: {home_values[0]!r}")
    base_interpreter = Path(os.path.abspath(os.fspath(home / "python.exe")))
    if not base_interpreter.is_file():
        raise OwnershipError(
            f"pyvenv.cfg base interpreter is absent: {base_interpreter}"
        )
    return {
        "derivation": "<single absolute pyvenv.cfg home>/python.exe",
        "config": config_receipt,
        "home": str(Path(os.path.abspath(os.fspath(home)))),
        "base_interpreter": _source_receipt(base_interpreter),
    }


def validate_chain_receipt(
    chain: dict[str, Any],
    server: dict[str, Any],
    expected_launcher_argv: Sequence[str],
) -> list[str]:
    errors = []
    launcher = chain.get("launcher") or {}
    intermediary = chain.get("intermediary")
    serving = chain.get("serving") or {}
    base_interpreter = chain.get("venv_base_interpreter") or {}
    chain_type = chain.get("chain_type")
    if chain.get("validated") is not True or chain.get("policy") != POLICY_NAME:
        errors.append("owned-chain status/policy drifted")
    if chain.get("validator_source") != validator_source_receipt():
        errors.append("owned-chain validator source drifted")
    if chain.get("policy_precedent") != policy_precedent():
        errors.append("owned-chain lab_locks precedent drifted")
    try:
        expected_base = venv_base_interpreter_receipt()
    except (OwnershipError, OSError) as exc:
        errors.append(f"venv base-interpreter derivation failed: {exc}")
        expected_base = {}
    if base_interpreter != expected_base:
        errors.append("owned-chain pyvenv/base-interpreter receipt drifted")
    if chain.get("expected_launcher_argv") != list(expected_launcher_argv):
        errors.append("owned-chain expected launcher argv drifted")
    if not launcher_argv_matches(launcher.get("argv") or [], expected_launcher_argv):
        errors.append("owned cmd launcher argv does not match campaign command")
    if not _same_path(
        str(launcher.get("executable") or ""), str(expected_launcher_argv[0])
    ):
        errors.append("owned cmd launcher executable drifted")
    if (
        int(serving.get("pid") or -1) != int(server.get("serving_pid") or -2)
        or int(serving.get("parent_pid") or -1) != int(server.get("parent_pid") or -2)
        or float(serving.get("process_create_time") or -1)
        != float(server.get("process_create_time") or -2)
        or serving.get("argv") != server.get("argv")
        or not _same_path(
            str(serving.get("executable") or ""),
            str(server.get("executable") or ""),
        )
    ):
        errors.append("serving process receipt differs from identified listener")
    if not _same_path(
        str(serving.get("executable") or ""),
        str((expected_base.get("base_interpreter") or {}).get("path") or ""),
    ):
        errors.append("serving executable is not the pyvenv-configured base interpreter")
    launcher_created = float(launcher.get("process_create_time") or -1)
    serving_created = float(serving.get("process_create_time") or -2)
    if serving_created + 0.001 < launcher_created:
        errors.append("serving process predates owned cmd launcher")
    if chain_type == "direct-child":
        if intermediary is not None:
            errors.append("direct-child chain unexpectedly retains an intermediary")
        if int(serving.get("parent_pid") or -1) != int(launcher.get("pid") or -2):
            errors.append("direct serving child is not parented by owned cmd launcher")
    elif chain_type == "windows-venv-one-hop":
        intermediary = intermediary or {}
        intermediary_created = float(intermediary.get("process_create_time") or -1)
        if (
            int(serving.get("parent_pid") or -1) != int(intermediary.get("pid") or -2)
            or int(intermediary.get("parent_pid") or -1)
            != int(launcher.get("pid") or -2)
            or not _same_path(
                str(intermediary.get("executable") or ""),
                str(EXPECTED_VENV_LAUNCHER),
            )
            or list(intermediary.get("argv") or [])[1:]
            != list(serving.get("argv") or [])[1:]
            or intermediary_created + 0.001 < launcher_created
            or serving_created + 0.001 < intermediary_created
            or serving_created - intermediary_created > 5.0
        ):
            errors.append("one-hop Windows venv ancestry contract failed")
    else:
        errors.append("owned-chain type is not allowed")
    return errors


def capture_verified_chain(
    server: dict[str, Any],
    launcher: psutil.Process,
    expected_launcher_argv: Sequence[str],
    *,
    process_factory: Callable[[int], psutil.Process] = psutil.Process,
) -> dict[str, Any]:
    if os.name != "nt":
        raise OwnershipError("OTR WAN ownership exception is Windows-only")
    try:
        launcher_identity = _identity(launcher)
        serving_identity = _identity(
            process_factory(int(server.get("serving_pid") or -1))
        )
        parent_pid = int(serving_identity["parent_pid"])
        intermediary = (
            None
            if parent_pid == int(launcher_identity["pid"])
            else _identity(process_factory(parent_pid))
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError) as exc:
        raise OwnershipError(f"Cannot capture owned process chain: {exc}") from exc
    chain = {
        "validated": True,
        "policy": POLICY_NAME,
        "validator_source": validator_source_receipt(),
        "policy_precedent": policy_precedent(),
        "venv_base_interpreter": venv_base_interpreter_receipt(),
        "chain_type": "direct-child" if intermediary is None else "windows-venv-one-hop",
        "launcher": launcher_identity,
        "intermediary": intermediary,
        "serving": serving_identity,
        "expected_launcher_argv": list(expected_launcher_argv),
    }
    errors = validate_chain_receipt(chain, server, expected_launcher_argv)
    if errors:
        raise OwnershipError("; ".join(errors))
    return chain
