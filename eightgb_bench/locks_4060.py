#!/usr/bin/env python3
"""Fail-closed, laptop-local leases for the physical RTX 4060 bench.

This module deliberately does not import the 5080 lab lock implementation.
Every receipt it creates is rooted beneath ``eightgb_bench/local`` in the
checkout where it runs.  A stale receipt is a human-visible stop condition;
this small first runner never guesses that another process is dead.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LeaseError(RuntimeError):
    """The physical 4060 bench cannot prove exclusive ownership."""


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_receipt(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        raise LeaseError(f"local lease receipt has a UTF-8 BOM: {path}")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LeaseError(f"local lease receipt is malformed: {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LeaseError(f"local lease receipt is not an object: {path}")
    return parsed


@dataclass
class LocalLease:
    """An O_EXCL receipt lease that cleans up only its matching nonce."""

    path: Path
    role: str
    nonce: str | None = None

    def acquire(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_receipt(self.path)
        if existing is not None:
            raise LeaseError(
                f"{self.role} lease already exists at {self.path}; "
                "do not adopt, overwrite, or reap it automatically"
            )
        self.nonce = secrets.token_hex(16)
        payload = {
            "lease_schema_version": 1,
            "role": self.role,
            "pid": os.getpid(),
            "nonce": self.nonce,
            "created_unix_s": time.time(),
        }
        try:
            with self.path.open("xb") as handle:
                handle.write(_canonical_bytes(payload))
        except FileExistsError as exc:
            raise LeaseError(
                f"{self.role} lease raced at {self.path}; another physical-4060 action owns it"
            ) from exc
        return payload

    def release(self) -> bool:
        if not self.nonce:
            return False
        existing = _read_receipt(self.path)
        if existing is None:
            return False
        if existing.get("nonce") != self.nonce or existing.get("role") != self.role:
            raise LeaseError(
                f"refusing to remove a nonmatching {self.role} lease at {self.path}"
            )
        self.path.unlink()
        self.nonce = None
        return True


class BenchLease:
    """Hold both required physical-laptop leases for one admission/run."""

    def __init__(self, local_root: Path) -> None:
        self.coordinator = LocalLease(local_root / ".coordinator.mutex", "coordinator")
        self.gpu = LocalLease(local_root / ".gpu.lock", "gpu")

    def __enter__(self) -> "BenchLease":
        self.coordinator.acquire()
        try:
            self.gpu.acquire()
        except Exception:
            self.coordinator.release()
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        release_errors: list[Exception] = []
        for lease in (self.gpu, self.coordinator):
            try:
                lease.release()
            except Exception as error:  # cleanup must never silently erase a mismatch
                release_errors.append(error)
        if release_errors and exc_type is None:
            raise release_errors[0]
