#!/usr/bin/env python3
"""Run the frozen H3 best promotion suite sequentially on lab port 8199."""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import lab_locks
import run_recipe
import suite_integrity
import validate_recipes


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = REPO_ROOT / "suites" / "h3_best_suite_cache_classic.json"
SUITE_RESULT = run_recipe.RESULTS_DIR / "h3_best_suite.json"
SUITE_INTEGRITY_SOURCE_PATH = REPO_ROOT / "suite_integrity.py"
CANONICAL_SEQUENCE = (
    ("W0", "h3_i2v_suite_sentinel", "warmup"),
    ("S0", "h3_i2v_suite_sentinel", "sentinel_reference"),
    ("T0", "h3_t2v_best", "candidate_cold"),
    ("T1", "h3_t2v_best", "candidate_warm"),
    ("S1", "h3_i2v_suite_sentinel", "sentinel"),
    ("I0", "h3_i2v_best", "candidate_cold"),
    ("I1", "h3_i2v_best", "candidate_warm"),
    ("S2", "h3_i2v_suite_sentinel", "sentinel"),
    ("R0", "h3_r2v_best", "candidate_cold"),
    ("R1", "h3_r2v_best", "candidate_warm"),
    ("S3", "h3_i2v_suite_sentinel", "sentinel"),
)


class SuiteFailure(RuntimeError):
    pass


class SuiteLock:
    """Own the OS coordinator plus suite/GPU receipts for the full suite."""

    def __init__(
        self,
        path: Path = run_recipe.SUITE_LOCKFILE_PATH,
        *,
        gpu_path: Path | None = None,
        coordinator_path: Path | None = None,
    ):
        self.path = Path(path)
        self._lease = lab_locks.SuiteLease(
            self.path,
            Path(gpu_path or run_recipe.LOCKFILE_PATH),
            Path(coordinator_path or run_recipe.COORDINATOR_MUTEX_PATH),
        )

    @property
    def acquired(self) -> bool:
        return self._lease.acquired

    @property
    def nonce(self) -> str | None:
        return self._lease.nonce

    def acquire(self) -> None:
        try:
            self._lease.acquire()
        except (lab_locks.LeaseError, OSError) as exc:
            raise SuiteFailure(f"Could not acquire suite coordinator: {exc}") from exc

    def child_environment(self, base: dict[str, str]) -> dict[str, str]:
        try:
            return self._lease.child_environment(base)
        except lab_locks.LeaseError as exc:
            raise SuiteFailure(f"Could not authorize suite child: {exc}") from exc

    def release(
        self,
        checkpoint: Callable[[Sequence[str]], None] | None = None,
    ) -> None:
        try:
            self._lease.release(checkpoint=checkpoint)
        except lab_locks.LeaseError as exc:
            raise SuiteFailure(f"Could not release suite coordinator: {exc}") from exc

    def __enter__(self) -> "SuiteLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def require_suite_integrity_source(expected_sha256: str) -> None:
    """Fail if the PASS-critical storage checker changed after suite pinning."""

    try:
        current_sha256 = run_recipe.sha256_file(SUITE_INTEGRITY_SOURCE_PATH)
    except OSError as exc:
        raise SuiteFailure(f"suite_integrity.py could not be rehashed: {exc}") from exc
    if current_sha256 != expected_sha256:
        raise SuiteFailure("suite_integrity.py changed during suite")


def require_suite_cache_evidence(
    suite_run_id_value: str,
    manifest_sequence: list[dict[str, Any]],
    recipe_sha256s: dict[str, str],
    children: list[dict[str, Any]],
    suite_runtime_sha256s: dict[str, str],
) -> None:
    """Re-derive all cache evidence from pinned recipes and current core bytes."""

    try:
        current_runtime_sha256s = run_recipe.suite_cache_runtime_sha256s()
    except ValueError as exc:
        raise SuiteFailure(f"Suite cache runtime contract is not frozen: {exc}") from exc
    failures = suite_integrity.suite_cache_evidence_errors(
        REPO_ROOT,
        suite_run_id_value,
        manifest_sequence,
        recipe_sha256s,
        children,
        suite_runtime_sha256s,
        current_runtime_sha256s,
    )
    if failures:
        raise SuiteFailure(
            "Suite cache evidence verification failed: " + "; ".join(failures)
        )


def load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise SuiteFailure(f"Manifest has a UTF-8 BOM: {path}")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SuiteFailure(f"Invalid suite manifest: {exc}") from exc
    if manifest.get("schema_version") != 1 or not manifest.get("sequence"):
        raise SuiteFailure("Suite manifest must be schema 1 with a non-empty sequence")
    return manifest, raw


def preflight_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    actual_sequence = tuple(
        (member.get("label"), member.get("recipe"), member.get("role"))
        for member in manifest.get("sequence", [])
        if isinstance(member, dict)
    )
    if actual_sequence != CANONICAL_SEQUENCE:
        raise SuiteFailure(
            "Suite sequence must exactly match the canonical ordered (label, recipe, role) tuples"
        )
    recipe_hashes: dict[str, str] = {}
    labels: set[str] = set()
    for member in manifest["sequence"]:
        label = member.get("label")
        recipe = member.get("recipe")
        if not label or label in labels or not recipe:
            raise SuiteFailure(f"Invalid or duplicate suite member: {member!r}")
        labels.add(label)
        recipe_path = run_recipe.REPO_ROOT / "recipes" / f"{recipe}.json"
        if not recipe_path.is_file():
            raise SuiteFailure(f"Suite recipe is missing: {recipe_path}")
        report = validate_recipes.validate_recipe_file(recipe_path)
        if not report["valid"]:
            raise SuiteFailure(f"Static validation failed for {recipe}: {report['errors']}")
        if report["blocked"]:
            raise SuiteFailure(f"Suite recipe is blocked: {recipe}")
        recipe_hashes[recipe] = run_recipe.sha256_file(recipe_path)
    return recipe_hashes


def establish_suite_server(
    reserve_vram_gib: float, disable_pinned: bool, cache_classic: bool
) -> dict[str, Any]:
    """Boot/verify the fresh suite server under the manifest's exact lane."""
    managed_names = ("LAB_RESERVE_VRAM_GB", "LAB_DISABLE_PINNED", "LAB_CACHE_CLASSIC")
    prior = {name: os.environ.get(name) for name in managed_names}
    try:
        os.environ["LAB_RESERVE_VRAM_GB"] = f"{reserve_vram_gib:g}"
        if disable_pinned:
            os.environ["LAB_DISABLE_PINNED"] = "1"
        else:
            os.environ.pop("LAB_DISABLE_PINNED", None)
        if cache_classic:
            os.environ["LAB_CACHE_CLASSIC"] = "1"
        else:
            os.environ.pop("LAB_CACHE_CLASSIC", None)
        run_recipe.check_server_up_and_ownership()
        return run_recipe.verified_server_instance()
    except run_recipe.PreflightError as exc:
        raise SuiteFailure(f"Could not establish the verified suite server: {exc}") from exc
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def require_suite_server_instance(
    expected_server_instance: dict[str, Any], phase: str
) -> None:
    """Fail closed if the exact server pinned for this suite is no longer serving."""
    try:
        actual = run_recipe.verified_server_instance()
    except run_recipe.PreflightError as exc:
        raise SuiteFailure(f"Verified suite server unavailable {phase}: {exc}") from exc
    if actual != expected_server_instance:
        raise SuiteFailure(
            f"Verified suite server changed {phase}: "
            f"expected {expected_server_instance!r}, got {actual!r}"
        )


def settle_samples(
    manifest: dict[str, Any],
    expected_server_instance: dict[str, Any],
    phase: str,
) -> tuple[list[float], float]:
    delay = float(manifest["settle_before_sampling_s"])
    duration = float(manifest["settle_sample_duration_s"])
    interval = float(manifest["settle_sample_interval_s"])
    if not all(math.isfinite(value) and value > 0 for value in (delay, duration, interval)):
        raise SuiteFailure("Settle timings must be finite positive values")
    require_suite_server_instance(expected_server_instance, f"before {phase} settle delay")
    time.sleep(delay)
    require_suite_server_instance(expected_server_instance, f"after {phase} settle delay")
    count = max(2, int(round(duration / interval)) + 1)
    samples: list[float] = []
    for index in range(count):
        require_suite_server_instance(
            expected_server_instance, f"before {phase} sample {index + 1}/{count}"
        )
        samples.append(round(run_recipe.query_gpu_vram_mb() / 1024.0, 3))
        require_suite_server_instance(
            expected_server_instance, f"after {phase} sample {index + 1}/{count}"
        )
        if index + 1 < count:
            time.sleep(interval)
    return samples, round(statistics.median(samples), 3)


def child_summary(
    member: dict[str, Any],
    receipt: dict[str, Any],
    receipt_path: Path,
    pre_samples: list[float],
    pre_median_gib: float,
    post_samples: list[float],
    post_median_gib: float,
    receipt_bytes: bytes | None = None,
) -> dict[str, Any]:
    peak = float(receipt.get("peak_vram_gb") or 0.0)
    baseline = float(receipt.get("baseline_vram_gb") or 0.0)
    return {
        "label": member["label"],
        "role": member["role"],
        "recipe": member["recipe"],
        "run_number": receipt.get("run_number"),
        "config_run_count": receipt.get("config_run_count"),
        "status": receipt.get("status"),
        "gate_pass": receipt.get("gate_pass"),
        "warm_pass": receipt.get("warm_pass"),
        "requires_human_eyeball": receipt.get("requires_human_eyeball"),
        "eyeball": receipt.get("eyeball"),
        "peak_vram_gib": peak,
        "baseline_vram_gib": baseline,
        "net_peak_vram_gib": round(peak - baseline, 3),
        "peak_host_ram_gib": receipt.get("peak_host_ram_gb"),
        "duration_s": receipt.get("duration_s"),
        "pre_settle_samples_gib": pre_samples,
        "pre_settle_median_gib": pre_median_gib,
        "post_settle_samples_gib": post_samples,
        "post_settle_median_gib": post_median_gib,
        "settled_delta_gib": round(post_median_gib - pre_median_gib, 3),
        "output_path": receipt.get("output_path"),
        "artifact_sha256": receipt.get("artifact_sha256"),
        "recipe_sha256": receipt.get("recipe_sha256"),
        "lab_locks_sha256": receipt.get("lab_locks_sha256"),
        "run_identity_sha256": receipt.get("run_identity_sha256"),
        "server_instance": receipt.get("server_instance"),
        "receipt": str(receipt_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "receipt_sha256": (
            run_recipe.sha256_bytes(receipt_bytes)
            if receipt_bytes is not None
            else run_recipe.sha256_file(receipt_path)
        ),
        "queued_prompt_sha256": receipt.get("queued_prompt_sha256"),
        "execution_cache_control": receipt.get("execution_cache_control"),
        "suite_cache_runtime_sha256s": receipt.get("suite_cache_runtime_sha256s"),
        "final_suite_cache_runtime_sha256s": receipt.get(
            "final_suite_cache_runtime_sha256s"
        ),
    }


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
# Net peak remains required, finite, and receipt-bound evidence, but it is not
# comparable across cache-classic children whose pre-run resident baselines can
# legitimately differ. Absolute peak retains the transient envelope gate; the
# post-settle median is the persistent-creep gate.
_CREEP_COMPARISON_FIELDS = ("peak_vram_gib", "post_settle_median_gib")


def _is_finite_real(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def suite_numeric_failures(child: dict[str, Any]) -> list[str]:
    """Reject type-confused/non-finite counters and measurements before comparison."""
    label = child.get("label", "<unknown>")
    failures: list[str] = []
    for field in ("run_number", "config_run_count"):
        value = child.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            failures.append(f"{label} has invalid positive integer field: {field}")
    for field in _SUITE_REQUIRED_REAL_FIELDS:
        if not _is_finite_real(child.get(field)):
            failures.append(f"{label} has invalid finite numeric field: {field}")
    for field in _SUITE_OPTIONAL_REAL_FIELDS:
        if field in child and not _is_finite_real(child.get(field)):
            failures.append(f"{label} has invalid finite numeric field: {field}")
    for field in _SUITE_SAMPLE_FIELDS:
        samples = child.get(field)
        if not isinstance(samples, list) or not samples or not all(
            _is_finite_real(sample) for sample in samples
        ):
            failures.append(f"{label} has invalid finite numeric samples: {field}")
    if not failures:
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
                failures.append(
                    f"{label} {field} does not match recomputed settled samples "
                    f"({child[field]!r} != {expected_value!r})"
                )
    return failures


def evaluate_suite(children: list[dict[str, Any]], tolerance: float) -> list[str]:
    failures: list[str] = []
    if not _is_finite_real(tolerance) or float(tolerance) < 0:
        return ["Suite tolerance must be a finite non-negative real number"]
    actual_sequence = tuple(
        (child.get("label"), child.get("recipe"), child.get("role"))
        for child in children
    )
    if actual_sequence != CANONICAL_SEQUENCE:
        return ["Suite children do not match the canonical ordered sequence"]
    for child in children:
        failures.extend(suite_numeric_failures(child))
    if failures:
        return failures
    by_label = {child["label"]: child for child in children}
    for child in children:
        if child.get("gate_pass") is not True:
            failures.append(f"{child['label']} did not pass its machine gate: {child.get('status')}")
        if "marginal" in str(child.get("status", "")).lower():
            failures.append(f"{child['label']} is marginal and not promotable")
        cache_control = child.get("execution_cache_control")
        if not isinstance(cache_control, dict):
            failures.append(f"{child['label']} lacks executor cache-control evidence")
        else:
            expected_suffix = f":{child['label']}"
            if (
                cache_control.get("mode")
                != "pinned-undeclared-randomnoise-input"
                or not isinstance(cache_control.get("nonce"), str)
                or not cache_control["nonce"].endswith(expected_suffix)
            ):
                failures.append(f"{child['label']} has invalid executor cache nonce evidence")
            if cache_control.get("recipe_noise_seed") != 42:
                failures.append(f"{child['label']} did not preserve recipe noise seed 42")
            if cache_control.get("fresh_execution_proved") is not True:
                failures.append(f"{child['label']} did not prove fresh sampler/output execution")
            if cache_control.get("cached_fresh_node_ids") != []:
                failures.append(f"{child['label']} reused a nonce-controlled cache entry")
            sampler_ids = cache_control.get("sampler_node_ids")
            if not isinstance(sampler_ids, list) or not sampler_ids:
                failures.append(f"{child['label']} cache evidence has no sampler node")
            if child["label"] in {"S0", "T1", "I1", "R1"}:
                stable_ids = cache_control.get("stable_node_ids")
                cached_ids = cache_control.get("cached_node_ids")
                if (
                    not isinstance(stable_ids, list)
                    or not stable_ids
                    or not isinstance(cached_ids, list)
                    or not set(stable_ids).issubset(set(cached_ids))
                ):
                    failures.append(
                        f"{child['label']} did not preserve every stable loader/conditioning cache hit"
                    )
        queued_prompt_hash = child.get("queued_prompt_sha256")
        if not isinstance(queued_prompt_hash, str) or re.fullmatch(
            r"[0-9a-f]{64}", queued_prompt_hash
        ) is None:
            failures.append(f"{child['label']} queued prompt hash is invalid")

    nonces = [
        child.get("execution_cache_control", {}).get("nonce")
        if isinstance(child.get("execution_cache_control"), dict)
        else None
        for child in children
    ]
    if len(set(nonces)) != len(children):
        failures.append("Suite executor cache nonces are not unique")
    output_paths = [child.get("output_path") for child in children]
    if any(not isinstance(path, str) or not path for path in output_paths):
        failures.append("Suite child output paths are incomplete")
    elif len(set(output_paths)) != len(output_paths):
        failures.append("Suite child output paths are not unique; cached artifact reuse suspected")

    server_instances = [child.get("server_instance") for child in children]
    if not server_instances or not server_instances[0] or any(
        instance != server_instances[0] for instance in server_instances[1:]
    ):
        failures.append("Suite children do not share one verified server instance")

    lock_helper_hashes = [child.get("lab_locks_sha256") for child in children]
    if not lock_helper_hashes or not lock_helper_hashes[0] or any(
        digest != lock_helper_hashes[0] for digest in lock_helper_hashes[1:]
    ):
        failures.append("Suite children do not share one nonempty lab_locks.py hash")

    for cold_label, warm_label in (("T0", "T1"), ("I0", "I1"), ("R0", "R1")):
        cold = by_label[cold_label]
        warm = by_label[warm_label]
        if int(cold.get("config_run_count") or 0) != 1 or cold.get("warm_pass") is not False:
            failures.append(f"{cold_label} is not a fresh cold configuration run")
        if int(warm.get("config_run_count") or 0) != 2:
            failures.append(f"{warm_label} is not configuration run 2")
        identity = cold.get("run_identity_sha256")
        if not identity or warm.get("run_identity_sha256") != identity:
            failures.append(f"{cold_label}/{warm_label} do not share one nonempty run identity")
        if int(warm.get("run_number") or 0) != int(cold.get("run_number") or 0) + 1:
            failures.append(f"{warm_label} run number is not exactly one after {cold_label}")
        if int(warm.get("config_run_count") or 0) != int(cold.get("config_run_count") or 0) + 1:
            failures.append(f"{warm_label} config count is not exactly one after {cold_label}")
        if warm.get("warm_pass") is not True:
            failures.append(f"{warm_label} is not a passing second consecutive identity")
        for field in _CREEP_COMPARISON_FIELDS:
            delta = float(warm[field]) - float(cold[field])
            if delta > tolerance + 1e-9:
                failures.append(
                    f"[VRAM_CREEP] {warm_label} {field} rose {delta:.3f} GiB over {cold_label} "
                    f"(limit {tolerance:.3f})"
                )

    sentinel_labels = ("W0", "S0", "S1", "S2", "S3")
    sentinel_identity = by_label["W0"].get("run_identity_sha256")
    if int(by_label["W0"].get("config_run_count") or 0) != 1 or by_label["W0"].get("warm_pass") is not False:
        failures.append("W0 is not a fresh cold sentinel warm-up")
    if not sentinel_identity:
        failures.append("Sentinel identity is empty")
    for previous_label, current_label in zip(sentinel_labels, sentinel_labels[1:]):
        previous = by_label[previous_label]
        current = by_label[current_label]
        if current.get("run_identity_sha256") != sentinel_identity:
            failures.append(f"{current_label} does not share the W0 sentinel identity")
        if int(current.get("run_number") or 0) != int(previous.get("run_number") or 0) + 1:
            failures.append(f"{current_label} sentinel run number is not exactly one after {previous_label}")
        if int(current.get("config_run_count") or 0) != int(previous.get("config_run_count") or 0) + 1:
            failures.append(f"{current_label} sentinel config count is not exactly one after {previous_label}")
        if current.get("warm_pass") is not True:
            failures.append(f"{current_label} is not warm after W0")

    reference = by_label["S0"]
    for label in ("S1", "S2", "S3"):
        sentinel = by_label[label]
        for field in _CREEP_COMPARISON_FIELDS:
            delta = float(sentinel[field]) - float(reference[field])
            if delta > tolerance + 1e-9:
                failures.append(
                    f"[VRAM_CREEP] {label} {field} rose {delta:.3f} GiB above S0 "
                    f"(limit {tolerance:.3f})"
                )
    return failures


def vram_creep_failures(failures: list[str]) -> list[str]:
    """Return only memory-delta failures, not general certification failures."""
    return [failure for failure in failures if failure.startswith("[VRAM_CREEP]")]


def suite_lane(manifest: dict[str, Any]) -> tuple[float, bool, str, list[str]]:
    """Validate manifest lane settings and derive env/argv receipt labels once."""
    lane = manifest.get("boot_lane")
    if not isinstance(lane, dict):
        raise SuiteFailure("Manifest boot_lane must be a dictionary")
    reserve = float(lane.get("reserve_vram_gib"))
    if not math.isfinite(reserve) or reserve < 0:
        raise SuiteFailure("Manifest reserve_vram_gib must be finite and non-negative")
    disable_pinned = lane.get("disable_pinned_memory")
    if not isinstance(disable_pinned, bool):
        raise SuiteFailure("Manifest disable_pinned_memory must be true or false")
    if lane.get("cache_mode") != "classic":
        raise SuiteFailure("H3 suite boot_lane.cache_mode must be 'classic'")
    parts = ["lab-8199", "sage-free"]
    child_args: list[str] = []
    if disable_pinned:
        parts.append("no-pinned")
        child_args.append("--disable-pinned-memory")
    parts.append("cache-classic")
    parts.append(f"reserve-{reserve:g}gb")
    return reserve, disable_pinned, ", ".join(parts), child_args


def suite_run_id() -> str:
    """Return a collision-resistant filesystem-safe suite execution id."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{uuid.uuid4().hex}"


def _atomic_replace(path: Path, encoded: bytes, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_receipt(
    payload: dict[str, Any], archival_path: Path, *, create_archive: bool = False
) -> bytes:
    """Atomically checkpoint one byte-identical suite archive/current pair."""
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_replace(archival_path, encoded, exclusive=create_archive)
    _atomic_replace(SUITE_RESULT, encoded)
    return encoded


def write_release_receipt(payload: dict[str, Any], archival_path: Path) -> bytes:
    """Publish a final lease checkpoint without a torn self-validating PASS.

    PASS updates the mutable alias first and the uniquely named archive last. If
    that transition tears, the alias cannot validate against the still-failing
    archive. FAIL uses the reverse order so any prior PASS archive is invalidated
    before its alias. Both operations run while the coordinator is still held.
    """

    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if payload.get("machine_pass") is True:
        _atomic_replace(SUITE_RESULT, encoded)
        _atomic_replace(archival_path, encoded)
    else:
        _atomic_replace(archival_path, encoded)
        _atomic_replace(SUITE_RESULT, encoded)
    return encoded


def _append_suite_failure(payload: dict[str, Any], failure: str) -> None:
    if failure not in payload["failures"]:
        payload["failures"].append(failure)


def release_suite_with_evidence(
    suite_lock: SuiteLock,
    payload: dict[str, Any],
    archival_path: Path,
    *,
    provisional_machine_pass: bool,
) -> SuiteFailure | None:
    """Release the suite lease only through a durable fail-closed checkpoint.

    The callback runs after nonce-bound lease-receipt removal is attempted and
    while the OS coordinator is still held.  A coordinator-unlock error invokes
    it again before the handle closes, replacing any provisional PASS with FAIL.
    """

    checkpoint_calls = 0

    def checkpoint(release_errors: Sequence[str]) -> None:
        nonlocal checkpoint_calls
        checkpoint_calls += 1
        normalized_errors = [str(error) for error in release_errors if str(error)]
        if normalized_errors:
            for error in normalized_errors:
                _append_suite_failure(payload, f"Suite lease release failed: {error}")
            payload["lease_release"] = {
                "success": False,
                "reason": "; ".join(normalized_errors),
            }
            payload["machine_pass"] = False
            payload["status"] = "MACHINE SUITE FAIL"
        else:
            payload["lease_release"] = {
                "success": True,
                "reason": "nonce-bound suite/GPU receipts and coordinator released",
            }
            payload["machine_pass"] = bool(provisional_machine_pass)
            payload["status"] = (
                "MACHINE SUITE PASS (human video/audio pending)"
                if payload["machine_pass"]
                else "MACHINE SUITE FAIL"
            )
        payload["promotion_ready"] = False
        payload["finished_at"] = utc_now()
        try:
            write_release_receipt(payload, archival_path)
        except Exception as exc:
            payload["machine_pass"] = False
            payload["status"] = "MACHINE SUITE FAIL"
            payload["lease_release"] = {
                "success": False,
                "reason": f"release checkpoint write failed: {exc}",
            }
            _append_suite_failure(
                payload, f"Suite lease release checkpoint write failed: {exc}"
            )
            # A second fail-only write is safe under the still-held coordinator.
            write_release_receipt(payload, archival_path)
            raise SuiteFailure(f"Could not write suite release checkpoint: {exc}") from exc

    try:
        suite_lock.release(checkpoint=checkpoint)
    except SuiteFailure as exc:
        if checkpoint_calls == 0 or payload.get("machine_pass") is True:
            payload["machine_pass"] = False
            payload["status"] = "MACHINE SUITE FAIL"
            payload["lease_release"] = {"success": False, "reason": str(exc)}
            _append_suite_failure(payload, f"Suite lease release failed: {exc}")
            try:
                write_receipt(payload, archival_path)
            except Exception as write_exc:
                print(
                    f"[SUITE FAIL] Could not checkpoint lease-release failure: {write_exc}",
                    file=sys.stderr,
                    flush=True,
                )
        return exc

    if checkpoint_calls == 0:
        failure = SuiteFailure("Suite lease release omitted its durable checkpoint")
        payload["machine_pass"] = False
        payload["status"] = "MACHINE SUITE FAIL"
        payload["lease_release"] = {"success": False, "reason": str(failure)}
        _append_suite_failure(payload, str(failure))
        write_receipt(payload, archival_path)
        return failure
    return None


def load_new_child_receipt(
    recipe: str, before_history: dict[str, Any]
) -> tuple[dict[str, Any], Path, bytes]:
    """Load the exact newly created archive and prove current-alias byte parity."""
    try:
        after = run_recipe.audit_run_history(run_recipe.RESULTS_DIR, recipe)
    except run_recipe.ReceiptHistoryError as exc:
        raise SuiteFailure(f"Invalid child receipt history for {recipe}: {exc}") from exc
    expected = int(before_history["max_run_number"]) + 1
    if after["max_run_number"] != expected or after["current_number"] != expected:
        raise SuiteFailure(
            f"Child {recipe} recorded run {after['max_run_number']}; expected exactly {expected}"
        )
    if not after["alias_archive_match"]:
        raise SuiteFailure(f"Child {recipe} current alias disagrees with archive run {expected}")
    receipt_path = run_recipe.RESULTS_DIR / f"{recipe}_run{expected}.json"
    receipt_bytes = after["archive_bytes"][expected]
    if after["current_bytes"] != receipt_bytes:
        raise SuiteFailure(f"Child {recipe} alias/archive bytes changed during summary")
    receipt = after["archives"][expected]
    return receipt, receipt_path, receipt_bytes


def main() -> int:
    try:
        run_recipe.enforce_lab_port()
    except run_recipe.PreflightError as exc:
        print(f"[SUITE FAIL] {exc}", file=sys.stderr, flush=True)
        return 1
    manifest_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_MANIFEST
    manifest, manifest_bytes = load_manifest(manifest_path)
    recipe_hashes = preflight_manifest(manifest)
    reserve_vram_gib, disable_pinned, boot_lane, child_lane_args = suite_lane(manifest)
    raw_tolerance = manifest.get("creep_tolerance_gib")
    if not _is_finite_real(raw_tolerance) or float(raw_tolerance) < 0:
        raise SuiteFailure("Creep tolerance must be a finite non-negative real number")
    tolerance = float(raw_tolerance)
    suite_integrity_sha256 = run_recipe.sha256_file(SUITE_INTEGRITY_SOURCE_PATH)
    try:
        suite_cache_runtime_sha256s = run_recipe.suite_cache_runtime_sha256s()
    except ValueError as exc:
        raise SuiteFailure(f"Suite cache runtime contract is not frozen: {exc}") from exc

    run_recipe.RESULTS_DIR.mkdir(exist_ok=True)
    suite_lock = SuiteLock()
    try:
        suite_lock.acquire()
    except SuiteFailure as exc:
        # A lock loser must not write or overwrite any shared suite receipt.
        print(f"[SUITE FAIL] {exc}", file=sys.stderr, flush=True)
        return 1

    run_id = suite_run_id()
    archival_path = run_recipe.RESULTS_DIR / f"h3_best_suite_{run_id}.json"
    payload: dict[str, Any] = {
        "suite_schema_version": 1,
        "suite_run_id": run_id,
        "suite": manifest["name"],
        "status": "RUNNING",
        "machine_pass": False,
        "promotion_ready": False,
        "human_video_review": "pending",
        "native_audio_ear_review": "pending",
        "started_at": utc_now(),
        "manifest": str(manifest_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "manifest_sha256": run_recipe.sha256_bytes(manifest_bytes),
        "runner_sha256": run_recipe.sha256_file(Path(run_recipe.__file__)),
        "lab_locks_sha256": run_recipe.sha256_file(run_recipe.LAB_LOCKS_SOURCE_PATH),
        "suite_runner_sha256": run_recipe.sha256_file(Path(__file__)),
        "suite_integrity_sha256": suite_integrity_sha256,
        "suite_cache_runtime_sha256s": suite_cache_runtime_sha256s,
        "recipe_sha256s": recipe_hashes,
        "boot_lane": boot_lane,
        "creep_tolerance_gib": tolerance,
        "vram_creep": False,
        "vram_creep_failures": [],
        "children": [],
        "failures": [],
        "cleanup": {"success": False, "reason": "not attempted"},
        "fresh_start_cleanup": {"success": False, "reason": "not attempted"},
        "server_instance": None,
        "provisional_machine_pass": False,
        "lease_release": {"success": False, "reason": "not attempted"},
        "coordinator_held_through_final_receipt": True,
        "canonical_sequence_completed": False,
        "suite_evaluation_completed": False,
    }

    env = os.environ.copy()
    env["LAB_RESERVE_VRAM_GB"] = f"{reserve_vram_gib:g}"
    if disable_pinned:
        env["LAB_DISABLE_PINNED"] = "1"
    else:
        env.pop("LAB_DISABLE_PINNED", None)
    env["LAB_CACHE_CLASSIC"] = "1"

    pending_base_exception: BaseException | None = None
    pending_traceback = None
    release_failure: SuiteFailure | None = None
    suite_evaluation_completed = False
    provisional_machine_pass = False
    try:
        write_receipt(payload, archival_path, create_archive=True)
        fresh_start_cleanup = run_recipe.shutdown_lab_server()
        payload["fresh_start_cleanup"] = fresh_start_cleanup
        if fresh_start_cleanup.get("success") is not True:
            failure = (
                "Could not establish a fresh lab server state: "
                f"{fresh_start_cleanup.get('reason')}"
            )
            _append_suite_failure(payload, failure)
            payload["cleanup"] = fresh_start_cleanup
            payload["machine_pass"] = False
            payload["status"] = "MACHINE SUITE FAIL"
            payload["finished_at"] = utc_now()
            # This unique archive/current FAIL is written under the suite
            # coordinator before any child can start, replacing a stale PASS.
            write_receipt(payload, archival_path)
            raise SuiteFailure(failure)
        env = suite_lock.child_environment(env)
        try:
            expected_server_instance = establish_suite_server(
                reserve_vram_gib, disable_pinned, True
            )
            payload["server_instance"] = expected_server_instance
            write_receipt(payload, archival_path)
            for member in manifest["sequence"]:
                recipe = member["recipe"]
                recipe_path = REPO_ROOT / "recipes" / f"{recipe}.json"
                if run_recipe.sha256_file(recipe_path) != recipe_hashes[recipe]:
                    raise SuiteFailure(
                        f"Recipe changed during suite before {member['label']}: {recipe}"
                    )
                try:
                    before_history = run_recipe.audit_run_history(run_recipe.RESULTS_DIR, recipe)
                except run_recipe.ReceiptHistoryError as exc:
                    raise SuiteFailure(f"Invalid pre-child receipt history for {recipe}: {exc}") from exc
                pre_samples, pre_median_gib = settle_samples(
                    manifest,
                    expected_server_instance,
                    f"{member['label']} pre-render",
                )

                print(f"\n[SUITE] {member['label']} -> {recipe} ({member['role']})", flush=True)
                command = [
                    sys.executable,
                    str(REPO_ROOT / "run_recipe.py"),
                    str(recipe_path),
                    "--suite",
                    "--suite-cache-nonce",
                    f"{run_id}:{member['label']}",
                    *child_lane_args,
                ]
                completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
                if completed.returncode != 0:
                    raise SuiteFailure(
                        f"Child runner failed for {member['label']} ({recipe}) "
                        f"with exit {completed.returncode}"
                    )
                receipt, receipt_path, receipt_bytes = load_new_child_receipt(
                    recipe, before_history
                )
                if receipt.get("receipt_schema_version") != run_recipe.RECEIPT_SCHEMA_VERSION:
                    raise SuiteFailure(f"Child {member['label']} did not write the current receipt schema")
                if receipt.get("recipe_sha256") != recipe_hashes[recipe]:
                    raise SuiteFailure(f"Child {member['label']} recipe hash disagrees with suite pin")
                if receipt.get("runner_sha256") != payload["runner_sha256"]:
                    raise SuiteFailure(f"Child {member['label']} runner hash disagrees with suite pin")
                if receipt.get("lab_locks_sha256") != payload["lab_locks_sha256"]:
                    raise SuiteFailure(
                        f"Child {member['label']} lab_locks.py hash disagrees with suite pin"
                    )
                if receipt.get("boot_lane") != boot_lane:
                    raise SuiteFailure(f"Child {member['label']} boot lane disagrees with manifest")
                if receipt.get("provenance_unchanged") is not True:
                    raise SuiteFailure(f"Child {member['label']} provenance was not stable")
                if receipt.get("server_instance_unchanged") is not True:
                    raise SuiteFailure(f"Child {member['label']} server instance changed")
                if receipt.get("server_instance") != expected_server_instance:
                    raise SuiteFailure(
                        f"Child {member['label']} did not use the suite-pinned server instance"
                    )
                cache_child = dict(receipt)
                cache_child["label"] = member["label"]
                cache_child["role"] = member["role"]
                require_suite_cache_evidence(
                    run_id,
                    [member],
                    recipe_hashes,
                    [cache_child],
                    suite_cache_runtime_sha256s,
                )

                post_samples, post_median_gib = settle_samples(
                    manifest,
                    expected_server_instance,
                    f"{member['label']} post-render",
                )
                payload["children"].append(
                    child_summary(
                        member,
                        receipt,
                        receipt_path,
                        pre_samples,
                        pre_median_gib,
                        post_samples,
                        post_median_gib,
                        receipt_bytes,
                    )
                )
                write_receipt(payload, archival_path)
                if receipt.get("gate_pass") is not True:
                    raise SuiteFailure(
                        f"Machine gate failed for {member['label']}: {receipt.get('status')}"
                    )

            if run_recipe.sha256_file(Path(run_recipe.__file__)) != payload["runner_sha256"]:
                raise SuiteFailure("run_recipe.py changed during suite")
            if (
                run_recipe.sha256_file(run_recipe.LAB_LOCKS_SOURCE_PATH)
                != payload["lab_locks_sha256"]
            ):
                raise SuiteFailure("lab_locks.py changed during suite")
            if run_recipe.sha256_file(Path(__file__)) != payload["suite_runner_sha256"]:
                raise SuiteFailure("run_h3_suite.py changed during suite")
            require_suite_integrity_source(payload["suite_integrity_sha256"])
            if run_recipe.suite_cache_runtime_sha256s() != suite_cache_runtime_sha256s:
                raise SuiteFailure("Suite cache runtime sources changed during suite")
            require_suite_server_instance(
                expected_server_instance, "before final suite evaluation"
            )
            storage_failures = suite_integrity.suite_storage_errors(
                REPO_ROOT,
                recipe_hashes,
                payload["children"],
                expected_recipes=[
                    member["recipe"] for member in manifest["sequence"]
                ],
            )
            if storage_failures:
                raise SuiteFailure(
                    "Final suite recipe/artifact verification failed: "
                    + "; ".join(storage_failures)
                )
            require_suite_cache_evidence(
                run_id,
                manifest["sequence"],
                recipe_hashes,
                payload["children"],
                suite_cache_runtime_sha256s,
            )
            failures = evaluate_suite(payload["children"], tolerance)
            suite_evaluation_completed = True
            payload["failures"].extend(failures)
            payload["vram_creep_failures"] = vram_creep_failures(payload["failures"])
            payload["vram_creep"] = bool(payload["vram_creep_failures"])
        except BaseException as exc:
            failure = (
                str(exc)
                if isinstance(exc, Exception)
                else f"{type(exc).__name__}: {exc}"
            )
            if failure not in payload["failures"]:
                payload["failures"].append(failure)
            if not isinstance(exc, Exception):
                pending_base_exception = exc
                pending_traceback = exc.__traceback__
            print(f"[SUITE FAIL] {exc}", file=sys.stderr, flush=True)
        finally:
            # Cleanup and the final checkpoint both happen before coordinator release.
            cleanup = run_recipe.shutdown_lab_server()
            payload["cleanup"] = cleanup
            if cleanup.get("success") is not True:
                failure = f"Lab server shutdown was not proved: {cleanup.get('reason')}"
                if failure not in payload["failures"]:
                    payload["failures"].append(failure)

            actual_sequence = tuple(
                (child.get("label"), child.get("recipe"), child.get("role"))
                for child in payload["children"]
            )
            canonical_sequence_completed = actual_sequence == CANONICAL_SEQUENCE
            payload["canonical_sequence_completed"] = canonical_sequence_completed
            payload["suite_evaluation_completed"] = suite_evaluation_completed
            provisional_machine_pass = (
                canonical_sequence_completed
                and suite_evaluation_completed
                and not payload["failures"]
                and cleanup.get("success") is True
            )
            payload["provisional_machine_pass"] = provisional_machine_pass
            # Never persist PASS before the nonce-bound lease receipts and OS
            # coordinator reach the release checkpoint.
            payload["machine_pass"] = False
            payload["lease_release"] = {
                "success": False,
                "reason": "pending suite lease release checkpoint",
            }
            payload["promotion_ready"] = False
            payload["status"] = (
                "MACHINE SUITE FINALIZING"
                if provisional_machine_pass
                else "MACHINE SUITE FAIL"
            )
            payload["finished_at"] = utc_now()
            write_receipt(payload, archival_path)
    except BaseException as exc:
        # The lease is still held here. If the archive exists, preserve a final
        # failure checkpoint before release; otherwise never create the alias.
        failure = (
            str(exc)
            if isinstance(exc, Exception)
            else f"{type(exc).__name__}: {exc}"
        )
        if not isinstance(exc, Exception) and pending_base_exception is None:
            pending_base_exception = exc
            pending_traceback = exc.__traceback__
        if archival_path.exists():
            provisional_machine_pass = False
            payload["provisional_machine_pass"] = False
            payload["machine_pass"] = False
            payload["promotion_ready"] = False
            payload["status"] = "MACHINE SUITE FAIL"
            if failure not in payload["failures"]:
                payload["failures"].append(failure)
            payload["finished_at"] = utc_now()
            write_receipt(payload, archival_path)
        print(f"[SUITE FAIL] {exc}", file=sys.stderr, flush=True)
    finally:
        release_failure = release_suite_with_evidence(
            suite_lock,
            payload,
            archival_path,
            provisional_machine_pass=provisional_machine_pass,
        )
        if release_failure is not None:
            print(f"[SUITE FAIL] {release_failure}", file=sys.stderr, flush=True)

    if pending_base_exception is not None:
        raise pending_base_exception.with_traceback(pending_traceback)
    if release_failure is not None:
        return 1

    return 0 if payload["machine_pass"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SuiteFailure as exc:
        print(f"[SUITE FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
