#!/usr/bin/env python3
"""Direct-argv execution adapter for one sealed Front Office specification.

This module is intentionally the only Front Office surface allowed to create a
child process.  It accepts one already-written execution specification, reloads
and revalidates it beneath ``.runtime``, then invokes the enrolled Python and
floor runner with no caller-selected roots, argv fragments, or environment.
The floor runner remains the only owner of port 8199, locks, GPU work, receipts,
and cleanup.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import front_office


_OS_RUNTIME_ENVIRONMENT = (
    "SystemRoot",
    "SYSTEMROOT",
    "WINDIR",
    "ComSpec",
    "COMSPEC",
    "PATHEXT",
    "PATH",
    "USERNAME",
    "USERDOMAIN",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "ProgramData",
    # NVIDIA's Windows utility resolves local NVML support through this
    # ordinary OS location variable.  It is not a model, CUDA, or attention
    # selector; leaving it out makes the idle gate's local nvidia-smi query
    # fail before the runner can inspect GPU ownership.
    "ProgramFiles",
    "ProgramW6432",
    "LOCALAPPDATA",
    "APPDATA",
)


class DispatchError(front_office.FrontOfficeError):
    """The sealed dispatcher cannot safely invoke the floor runner."""


def sanitized_dispatch_environment(profile: Mapping[str, Any]) -> dict[str, str]:
    """Return the limited OS substrate plus the profile's exact child values.

    ``PATH`` is retained only because the unchanged floor runner invokes its
    locally-installed ``git``/``ffmpeg`` evidence tools by executable name.
    The small Windows user-runtime set is retained because the direct child
    otherwise makes Torch's ``getpass`` import fall back to Unix-only ``pwd``.
    Profile and lab selectors are still rebuilt from the declared profile;
    ambient ``LAB_*``, CUDA, attention, proxy, token, and Python selector
    variables are never inherited.
    """

    environment: dict[str, str] = {}
    for name in _OS_RUNTIME_ENVIRONMENT:
        value = os.environ.get(name)
        if value:
            environment[name] = value
    environment.update(front_office.sanitized_child_environment(profile))
    return environment


def _profile_for_execution_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    semantic = spec.get("semantic")
    if not isinstance(semantic, dict):
        raise DispatchError("execution specification semantic payload is malformed")
    profile_binding = semantic.get("profile")
    if not isinstance(profile_binding, dict):
        raise DispatchError("execution specification profile binding is malformed")
    profile_id = profile_binding.get("id")
    if not isinstance(profile_id, str):
        raise DispatchError("execution specification profile ID is malformed")
    profile = front_office.load_enrolled_profile(profile_id)
    if profile.get("status") != front_office.PROFILE_STATUS_DISPATCHABLE:
        raise DispatchError("selected profile is not ENROLLED_DISPATCHABLE")
    if profile_binding.get("sha256") != front_office.canonical_sha256(profile):
        raise DispatchError("execution specification profile identity drifted")
    return profile


def dispatch_execution_spec(spec_path: str | Path) -> int:
    """Revalidate and launch exactly one profile-pinned floor-runner argv list."""

    # Resolve before use so a relative input is fixed under .runtime, not the
    # caller's current directory.  ``load_execution_spec`` repeats the strict
    # path and semantic checks immediately before launch.
    resolved_spec = front_office.resolve_execution_spec_path(spec_path)
    spec = front_office.load_execution_spec(resolved_spec)
    profile = _profile_for_execution_spec(spec)
    front_office.validate_execution_spec(spec)

    python = profile.get("python")
    floor_runner = profile.get("floor_runner")
    if not isinstance(python, dict) or not isinstance(floor_runner, dict):
        raise DispatchError("live dispatchable profile lacks pinned runner fields")
    executable = python.get("path")
    runner_path = floor_runner.get("path")
    if not isinstance(executable, str) or not isinstance(runner_path, str):
        raise DispatchError("live dispatchable profile has invalid runner paths")
    argv = [executable, runner_path, "--front-office-spec", str(resolved_spec)]

    try:
        completed = subprocess.run(
            argv,
            cwd=str(front_office.REPO_ROOT),
            env=sanitized_dispatch_environment(profile),
            check=False,
            shell=False,
        )
    except OSError as exc:
        raise DispatchError(f"cannot start profile-pinned floor runner: {exc}") from exc
    return int(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch one sealed Front Office execution specification."
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="the Front Office-owned execution specification under .runtime/",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        return dispatch_execution_spec(args.spec)
    except front_office.FrontOfficeError as exc:
        print(f"[FRONT OFFICE DISPATCH ABORT] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
