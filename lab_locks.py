"""Process-safe coordinator, suite, and GPU leases for the local render lab.

The JSON files are auditable ownership receipts.  The actual cross-process
coordinator is an OS-held byte-range lock, so checking persistent receipts and
creating a new lease happen inside one critical section.
"""

from __future__ import annotations

import json
import math
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

import psutil


SUITE_OWNER_PID_ENV = "LAB_SUITE_OWNER_PID"
SUITE_OWNER_CREATE_TIME_ENV = "LAB_SUITE_OWNER_CREATE_TIME"
SUITE_NONCE_ENV = "LAB_SUITE_NONCE"
LOCK_SCHEMA_VERSION = 1


class LeaseError(RuntimeError):
    """Raised when a coordinator or receipt lease cannot be proved."""


_LOCAL_GUARD = threading.Lock()
_LOCAL_COORDINATORS: set[str] = set()


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def process_create_time(pid: int) -> float:
    """Return a process creation timestamp, rejecting inaccessible identities."""
    try:
        value = float(psutil.Process(pid).create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise LeaseError(f"cannot verify process identity for PID {pid}: {exc}") from exc
    if not math.isfinite(value) or value <= 0:
        raise LeaseError(f"invalid process creation time for PID {pid}")
    return value


def process_identity_is_live(pid: int, expected_create_time: float) -> bool:
    """Return true only when both PID and creation time still identify a process."""
    if pid <= 0 or not math.isfinite(expected_create_time) or expected_create_time <= 0:
        return False
    try:
        actual = float(psutil.Process(pid).create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    return math.isclose(actual, expected_create_time, rel_tol=0.0, abs_tol=0.001)


def _is_verified_windows_venv_launcher_chain(
    owner_pid: int, owner_create_time: float
) -> bool:
    """Allow only the one-hop uv/venv launcher chain used on Windows.

    A Windows virtual-environment ``python.exe`` can remain as a launcher
    between the suite owner and the real interpreter.  This deliberately does
    not authorize arbitrary descendants: the intermediary must be the exact
    current venv launcher, must be a direct child of the nonce-bound owner, and
    must have launched this process with the identical argument vector.
    """
    if os.name != "nt" or not process_identity_is_live(owner_pid, owner_create_time):
        return False
    try:
        venv_prefix = Path(sys.prefix).resolve()
        expected_launcher = (venv_prefix / "Scripts" / "python.exe").resolve()
        if (
            sys.prefix == sys.base_prefix
            or not (venv_prefix / "pyvenv.cfg").is_file()
            or os.path.normcase(str(Path(sys.executable).resolve()))
            != os.path.normcase(str(expected_launcher))
        ):
            return False

        child = psutil.Process(os.getpid())
        launcher = psutil.Process(os.getppid())
        if launcher.ppid() != owner_pid:
            return False
        if os.path.normcase(str(Path(launcher.exe()).resolve())) != os.path.normcase(
            str(expected_launcher)
        ):
            return False
        if os.path.normcase(str(Path(child.exe()).resolve())) == os.path.normcase(
            str(expected_launcher)
        ):
            return False

        launcher_argv = launcher.cmdline()
        child_argv = child.cmdline()
        if (
            len(launcher_argv) < 2
            or len(child_argv) < 2
            or launcher_argv[1:] != child_argv[1:]
        ):
            return False

        launcher_created = float(launcher.create_time())
        child_created = float(child.create_time())
        return (
            owner_create_time <= launcher_created + 0.001
            and launcher_created <= child_created + 0.001
            and child_created - launcher_created <= 5.0
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
        return False


def new_lock_receipt(role: str, *, nonce: str | None = None) -> dict[str, Any]:
    """Build the complete identity receipt required for every persisted lease."""
    pid = os.getpid()
    return {
        "lock_schema_version": LOCK_SCHEMA_VERSION,
        "pid": pid,
        "process_create_time": process_create_time(pid),
        "nonce": nonce or secrets.token_hex(32),
        "role": role,
        "created_at_unix": time.time(),
    }


def _encoded_receipt(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write_all(fd: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(fd, content[offset:])
        if written <= 0:
            raise OSError("short write while creating lock receipt")
        offset += written
    os.fsync(fd)


def create_receipt_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    """Create one receipt atomically; never overwrite an existing owner."""
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        _write_all(fd, _encoded_receipt(payload))
    finally:
        os.close(fd)


def read_lock_receipt(path: Path) -> dict[str, Any]:
    """Read and strictly validate a persisted ownership receipt."""
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise LeaseError(f"{path.name} contains a UTF-8 BOM")
        payload = json.loads(raw.decode("utf-8"))
    except LeaseError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LeaseError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LeaseError(f"{path.name} is not a JSON object")
    try:
        schema = int(payload["lock_schema_version"])
        pid = int(payload["pid"])
        create_time = float(payload["process_create_time"])
        nonce = str(payload["nonce"])
        role = str(payload["role"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LeaseError(f"{path.name} lacks a complete owner identity") from exc
    if schema != LOCK_SCHEMA_VERSION:
        raise LeaseError(f"{path.name} uses unsupported lock schema {schema}")
    if pid <= 0 or not math.isfinite(create_time) or create_time <= 0:
        raise LeaseError(f"{path.name} contains an invalid process identity")
    if len(nonce) < 32 or not role:
        raise LeaseError(f"{path.name} contains an invalid nonce or role")
    return payload


def _same_owner(receipt: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    try:
        return (
            int(receipt.get("pid") or 0) == int(expected.get("pid") or 0)
            and math.isclose(
                float(receipt.get("process_create_time") or 0.0),
                float(expected.get("process_create_time") or 0.0),
                rel_tol=0.0,
                abs_tol=0.001,
            )
            and str(receipt.get("nonce") or "") == str(expected.get("nonce") or "")
            and str(receipt.get("role") or "") == str(expected.get("role") or "")
        )
    except (TypeError, ValueError):
        return False


def _refuse_existing_receipt(path: Path, label: str) -> None:
    """Fail closed on every persistent lease receipt.

    The OS coordinator prevents concurrent acquisition, but a surviving receipt
    is durable evidence that the previous owner's release was not proved.  PID
    death or reuse is therefore diagnostic context, never authority to delete
    that evidence automatically.  Recovery requires manual inspection/removal.
    """
    if not os.path.lexists(path):
        return
    try:
        receipt = read_lock_receipt(path)
        detail = (
            f"PID {receipt['pid']} ({receipt['role']}, "
            f"create_time={receipt['process_create_time']})"
        )
    except LeaseError as exc:
        detail = f"unreadable or malformed receipt: {exc}"
    raise LeaseError(
        f"{label} receipt {path.name} already exists ({detail}); "
        "manual inspection and removal are required"
    )


def _unlink_matching(path: Path, expected: Mapping[str, Any]) -> str | None:
    """Unlink only the exact nonce-bound owner receipt, returning an error string."""
    if not path.exists():
        return f"{path.name} disappeared before release"
    try:
        current = read_lock_receipt(path)
    except LeaseError as exc:
        return str(exc)
    if not _same_owner(current, expected):
        return f"refusing to remove {path.name}: owner nonce or identity changed"
    try:
        path.unlink()
    except OSError as exc:
        return f"could not remove {path.name}: {exc}"
    return None


class CoordinatorMutex:
    """An OS-held, non-blocking byte lock kept for the complete outer lease."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = None
        self._key = _path_key(self.path)

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self.acquired:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCAL_GUARD:
            if self._key in _LOCAL_COORDINATORS:
                raise LeaseError("render coordinator is already held by this process")
            _LOCAL_COORDINATORS.add(self._key)
        handle = None
        try:
            handle = self.path.open("a+b", buffering=0)
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            if handle is not None:
                handle.close()
            with _LOCAL_GUARD:
                _LOCAL_COORDINATORS.discard(self._key)
            raise LeaseError(f"render coordinator is held by another process: {exc}") from exc
        self._handle = handle

    def release(
        self,
        *,
        on_error: Callable[[LeaseError], None] | None = None,
    ) -> None:
        handle = self._handle
        if handle is None:
            return
        error: LeaseError | None = None
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError) as exc:
            error = LeaseError(f"could not release render coordinator: {exc}")
            if on_error is not None:
                try:
                    # The coordinator handle is deliberately still open here,
                    # so a caller can durably checkpoint a fail-closed result
                    # before close releases the OS lock as a final backstop.
                    on_error(error)
                except Exception as callback_exc:
                    error = LeaseError(
                        f"{error}; coordinator-release failure checkpoint failed: "
                        f"{callback_exc}"
                    )
        finally:
            handle.close()
            self._handle = None
            with _LOCAL_GUARD:
                _LOCAL_COORDINATORS.discard(self._key)
        if error is not None:
            raise error


class GpuLease:
    """Standalone GPU owner or verified re-entry into a parent suite lease."""

    def __init__(
        self,
        gpu_path: Path,
        suite_path: Path,
        coordinator_path: Path,
        *,
        suite_child: bool = False,
        environment: Mapping[str, str] | None = None,
    ):
        self.gpu_path = Path(gpu_path)
        self.suite_path = Path(suite_path)
        self.coordinator = CoordinatorMutex(Path(coordinator_path))
        self.suite_child = bool(suite_child)
        self.environment = environment if environment is not None else os.environ
        self.owner: dict[str, Any] | None = None
        self.acquired = False
        self.reentrant_suite = False

    def _verify_suite_child(self) -> dict[str, Any]:
        try:
            owner_pid = int(self.environment[SUITE_OWNER_PID_ENV])
            owner_create_time = float(self.environment[SUITE_OWNER_CREATE_TIME_ENV])
            nonce = str(self.environment[SUITE_NONCE_ENV])
        except (KeyError, TypeError, ValueError) as exc:
            raise LeaseError("--suite requires a complete suite owner token") from exc
        if len(nonce) < 32:
            raise LeaseError("--suite nonce is missing or malformed")
        if not process_identity_is_live(owner_pid, owner_create_time):
            raise LeaseError(f"suite owner PID {owner_pid} is dead or was reused")
        if os.getppid() != owner_pid and not _is_verified_windows_venv_launcher_chain(
            owner_pid, owner_create_time
        ):
            raise LeaseError(
                f"--suite caller is not a direct child or verified one-hop venv child "
                f"of owner PID {owner_pid}"
            )
        suite_receipt = read_lock_receipt(self.suite_path)
        gpu_receipt = read_lock_receipt(self.gpu_path)
        expected = {
            "pid": owner_pid,
            "process_create_time": owner_create_time,
            "nonce": nonce,
            "role": "suite",
        }
        if not _same_owner(suite_receipt, expected):
            raise LeaseError("suite owner environment does not match .suite.lock")
        if not _same_owner(gpu_receipt, expected):
            raise LeaseError("suite owner environment does not match .gpu.lock")
        if not process_identity_is_live(owner_pid, owner_create_time):
            raise LeaseError(f"suite owner PID {owner_pid} died during authorization")
        return suite_receipt

    def acquire(self) -> None:
        if self.acquired:
            return
        if self.suite_child:
            self.owner = self._verify_suite_child()
            self.reentrant_suite = True
            self.acquired = True
            return

        self.coordinator.acquire()
        try:
            _refuse_existing_receipt(self.suite_path, "suite lease")
            _refuse_existing_receipt(self.gpu_path, "GPU lease")
            self.owner = new_lock_receipt("standalone")
            create_receipt_exclusive(self.gpu_path, self.owner)
            self.acquired = True
        except Exception:
            self.owner = None
            self.coordinator.release()
            raise

    def release(self) -> None:
        if not self.acquired:
            return
        if self.reentrant_suite:
            self.acquired = False
            self.reentrant_suite = False
            self.owner = None
            return
        errors: list[str] = []
        try:
            if self.owner is None:
                errors.append("standalone GPU owner identity was lost")
            else:
                error = _unlink_matching(self.gpu_path, self.owner)
                if error:
                    errors.append(error)
        finally:
            try:
                self.coordinator.release()
            except LeaseError as exc:
                errors.append(str(exc))
            self.acquired = False
            self.owner = None
        if errors:
            raise LeaseError("; ".join(errors))


class SuiteLease:
    """Own the coordinator and GPU for a complete suite and authorize children."""

    def __init__(self, suite_path: Path, gpu_path: Path, coordinator_path: Path):
        self.suite_path = Path(suite_path)
        self.gpu_path = Path(gpu_path)
        self.coordinator = CoordinatorMutex(Path(coordinator_path))
        self.owner: dict[str, Any] | None = None
        self.acquired = False

    @property
    def nonce(self) -> str | None:
        return str(self.owner["nonce"]) if self.owner else None

    def acquire(self) -> None:
        if self.acquired:
            return
        self.coordinator.acquire()
        created: list[Path] = []
        try:
            _refuse_existing_receipt(self.suite_path, "suite lease")
            _refuse_existing_receipt(self.gpu_path, "GPU lease")
            self.owner = new_lock_receipt("suite")
            create_receipt_exclusive(self.suite_path, self.owner)
            created.append(self.suite_path)
            create_receipt_exclusive(self.gpu_path, self.owner)
            created.append(self.gpu_path)
            self.acquired = True
        except Exception:
            if self.owner is not None:
                for path in reversed(created):
                    _unlink_matching(path, self.owner)
            self.owner = None
            self.coordinator.release()
            raise

    def child_environment(
        self, base: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        if not self.acquired or self.owner is None:
            raise LeaseError("suite child environment requested without an owned lease")
        result: MutableMapping[str, str] = dict(base if base is not None else os.environ)
        result[SUITE_OWNER_PID_ENV] = str(self.owner["pid"])
        result[SUITE_OWNER_CREATE_TIME_ENV] = repr(float(self.owner["process_create_time"]))
        result[SUITE_NONCE_ENV] = str(self.owner["nonce"])
        return dict(result)

    def release(
        self,
        *,
        checkpoint: Callable[[Sequence[str]], None] | None = None,
    ) -> None:
        if not self.acquired:
            return
        errors: list[str] = []
        try:
            if self.owner is None:
                errors.append("suite owner identity was lost")
            else:
                for path in (self.gpu_path, self.suite_path):
                    error = _unlink_matching(path, self.owner)
                    if error:
                        errors.append(error)
            if checkpoint is not None:
                try:
                    # Receipt-removal failures are known while the Windows
                    # coordinator is still held.  The suite uses this boundary
                    # to write either PASS or FAIL before the OS unlock.
                    checkpoint(tuple(errors))
                except Exception as exc:
                    errors.append(f"suite release checkpoint failed: {exc}")
                    try:
                        checkpoint(tuple(errors))
                    except Exception as retry_exc:
                        errors.append(
                            f"suite release failure checkpoint retry failed: {retry_exc}"
                        )
        finally:
            try:
                self.coordinator.release(
                    on_error=(
                        (lambda exc: checkpoint(tuple([*errors, str(exc)])))
                        if checkpoint is not None
                        else None
                    )
                )
            except LeaseError as exc:
                errors.append(str(exc))
            self.acquired = False
            self.owner = None
        if errors:
            raise LeaseError("; ".join(errors))
