#!/usr/bin/env python
"""Run the complete OTR-side WAN cost ladder as one owned campaign.

The default invocation is read-only and prints the exact runbook.  ``--run``
is the only execution switch.  It captures the quiescent baseline before boot,
starts the existing OTR WAN launcher, proves the listener is its direct child
or the exact certified one-hop Windows venv child,
runs every immutable run1/run2 pair in order, reduces the receipts, and shuts
down only that same PID/create-time/argv identity in a ``finally`` block.

This LAB-owned orchestrator never edits OTR and never adopts a listener that
was present before it started.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Sequence

import psutil


LAB_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = LAB_ROOT / "scratch"
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
RESULT_ROOT = LAB_ROOT / "results" / "otr_side" / "wan_cost_ladder"
ATTEMPT_ID = "attempt-004"
PRIOR_FAILED_LIFECYCLE = RESULT_ROOT / "campaign_lifecycle.json"
PRIOR_FAILED_LIFECYCLE_SHA256 = (
    "442013facb8b261763a9d559270a6ca2302692c27629c94d29d4817b8c57c211"
)
ATTEMPT_002_LIFECYCLE = RESULT_ROOT / "attempts" / "attempt-002.json"
ATTEMPT_002_LIFECYCLE_SHA256 = (
    "a0c0e2eda3b760b4387cee157898043fcfcebe9a16e4842997c2270fd4a07e99"
)
ATTEMPT_002_BASELINE = RESULT_ROOT / "baselines" / "attempt-002.json"
ATTEMPT_002_BASELINE_SHA256 = (
    "88f607f553a4f55c6d442c9b27f85748e84a15030a7e3522ac10918a1172ce10"
)
ATTEMPT_002_SERVER_LOG = (
    RESULT_ROOT / "evidence" / "attempt-002" / "wan_cost_ladder.server.log"
)
ATTEMPT_002_SERVER_LOG_SHA256 = (
    "7523896db30d08b4f7e0557a4ab5c5ce1f4be17b3c01294a99d3264362dde71c"
)
ATTEMPT_002_RECOVERY = (
    RESULT_ROOT / "attempts" / "attempt-002_offline_incident_recovery.json"
)
ATTEMPT_002_RECOVERY_SHA256 = (
    "77b42b7069e53b31d9694fabcbd54a0b6317b27b3a2d2a02cbf089390049fc4f"
)
ATTEMPT_003_LIFECYCLE = RESULT_ROOT / "attempts" / "attempt-003.json"
ATTEMPT_003_LIFECYCLE_SHA256 = (
    "f90ae20856f8c00c10163303fb8d28656db594069cda73c2b9735530111f61a3"
)
ATTEMPT_003_BASELINE = RESULT_ROOT / "baselines" / "attempt-003.json"
ATTEMPT_003_BASELINE_SHA256 = (
    "5e7de2b54bb7b5431d2841b7e099902e9852512552a81be30b484ddebf86fbc5"
)
ATTEMPT_003_SERVER_LOG = (
    RESULT_ROOT / "evidence" / "attempt-003" / "wan_cost_ladder.server.log"
)
ATTEMPT_003_SERVER_LOG_SHA256 = (
    "a3b177447b58b6f050fd20d56f87e881cba8aa79c5d65408b8a1ffca81f52f97"
)
ATTEMPT_003_RECOVERY = (
    RESULT_ROOT / "attempts" / "attempt-003_ownership_incident_recovery.json"
)
ATTEMPT_003_RECOVERY_SHA256 = (
    "ea625fe56a533853b4bb6b383f544152a5780799ae36073a73f0875bb3602bfd"
)
BASELINE = RESULT_ROOT / "baselines" / f"{ATTEMPT_ID}.json"
TELEMETRY_ROOT = RESULT_ROOT / "telemetry" / ATTEMPT_ID
FIT_RECEIPT = RESULT_ROOT / "fits" / f"{ATTEMPT_ID}.json"
LIFECYCLE_RECEIPT = RESULT_ROOT / "attempts" / f"{ATTEMPT_ID}.json"
LAUNCHER = OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"
MODEL_PATHS = OTR_ROOT / "scripts" / "_otr_headless_model_paths.yaml"
SERVER_OUTPUT = Path(r"C:\Users\jeffr\Documents\ComfyUI\output")
EVIDENCE_ROOT = RESULT_ROOT / "evidence" / ATTEMPT_ID
EVIDENCE_CLIP_ROOT = EVIDENCE_ROOT / "clips"
SERVER_LOG = EVIDENCE_ROOT / "wan_cost_ladder.server.log"
MANAGER_BOOT_GUARD = EVIDENCE_ROOT / "manager_boot_guard.json"
SERVER_PORT = 8000
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")
REQUIRED_COMFYUI_URL = "http://127.0.0.1:8000"
BOOT_ENV_PREFIXES_CLEARED = ("OTR_WAN_TI2V_", "OTR_FASTWAN_8GB_")
BOOT_ENV_KEYS_CLEARED = {
    "COMFYUI_URL",
    "OTR_C7",
    "OTR_ENABLE_HUMO",
    "OTR_ENABLE_LTX_VIDEO",
    "OTR_FORCE_ENGINE_MAP",
    "OTR_HEADLESS_RESERVE_VRAM_GB",
    "OTR_SOURCE_SNAPSHOT_MANIFEST",
    "OTR_TEST_MODE",
    "OTR_VIDEO_LANDSCAPE_CANVAS",
    "HUGGINGFACE_HUB_TOKEN",
    "HF_API_TOKEN",
}


class CampaignError(RuntimeError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CampaignError(f"Cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FIXTURES = _load(
    "wan_cost_campaign_fixtures", SCRATCH / "build_wan_cost_ladder_fixtures.py"
)
SIDECAR = _load("wan_cost_campaign_sidecar", SCRATCH / "wan_cost_ladder_sidecar.py")
MANAGER_GUARD = _load(
    "wan_cost_campaign_manager_guard", SCRATCH / "manager_offline_guard.py"
)
OTR_SIDE = _load("wan_cost_campaign_identity", SCRATCH / "otr_resource_sidecar.py")
OWNERSHIP = _load("wan_cost_campaign_ownership", SCRATCH / "wan_cost_ownership.py")
sys.path.insert(0, str(LAB_ROOT))
from lab_locks import GpuLease  # noqa: E402


def owned_boot_command() -> list[str]:
    return [
        os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
        "/d",
        "/c",
        str(LAUNCHER),
        str(SERVER_LOG),
        "WAN",
    ]


def expected_raw_receipts() -> list[Path]:
    return [
        TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run{run}.json"
        for engine, lengths in FIXTURES.LADDERS.items()
        for frames in lengths
        for run in (1, 2)
    ]


def expected_clip_evidence() -> list[Path]:
    return [
        EVIDENCE_CLIP_ROOT / f"{engine}_f{frames:03d}_run{run}.mp4"
        for engine, lengths in FIXTURES.LADDERS.items()
        for frames in lengths
        for run in (1, 2)
    ]


def _pinned_prior_snapshot(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    snapshot = SIDECAR.BASE.stable_file_snapshot(path)
    if snapshot.get("exists") is not True or snapshot.get("sha256") != expected_sha256:
        raise CampaignError(f"{label} is absent or changed: {path}")
    return snapshot


def prior_failed_attempt_evidence() -> dict[str, Any]:
    snapshot = _pinned_prior_snapshot(
        PRIOR_FAILED_LIFECYCLE,
        PRIOR_FAILED_LIFECYCLE_SHA256,
        "Legacy attempt-001 lifecycle",
    )
    try:
        payload = json.loads(PRIOR_FAILED_LIFECYCLE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Legacy attempt-001 lifecycle is unreadable: {exc}") from exc
    if (
        payload.get("status") != "invalid"
        or payload.get("raw_receipts") != []
        or payload.get("server") is not None
    ):
        raise CampaignError("Legacy attempt-001 is not the expected pre-boot failure")
    attempt_002_lifecycle = _pinned_prior_snapshot(
        ATTEMPT_002_LIFECYCLE,
        ATTEMPT_002_LIFECYCLE_SHA256,
        "Attempt-002 lifecycle",
    )
    attempt_002_baseline = _pinned_prior_snapshot(
        ATTEMPT_002_BASELINE,
        ATTEMPT_002_BASELINE_SHA256,
        "Attempt-002 baseline",
    )
    attempt_002_log = _pinned_prior_snapshot(
        ATTEMPT_002_SERVER_LOG,
        ATTEMPT_002_SERVER_LOG_SHA256,
        "Attempt-002 incident server log",
    )
    attempt_002_recovery = _pinned_prior_snapshot(
        ATTEMPT_002_RECOVERY,
        ATTEMPT_002_RECOVERY_SHA256,
        "Attempt-002 recovery receipt",
    )
    lifecycle_payload = json.loads(ATTEMPT_002_LIFECYCLE.read_text(encoding="utf-8"))
    recovery_payload = json.loads(ATTEMPT_002_RECOVERY.read_text(encoding="utf-8"))
    attempt_002_telemetry = list((RESULT_ROOT / "telemetry" / "attempt-002").glob("*"))
    attempt_002_clips = list(
        (RESULT_ROOT / "evidence" / "attempt-002" / "clips").glob("*")
    )
    log_text = MANAGER_GUARD.ANSI_RE.sub(
        "", ATTEMPT_002_SERVER_LOG.read_text(encoding="utf-8", errors="replace")
    )
    if (
        lifecycle_payload.get("status") != "invalid"
        or lifecycle_payload.get("raw_receipts") != []
        or recovery_payload.get("success") is not True
        or ((recovery_payload.get("attempt_evidence") or {}).get("telemetry_file_count"))
        != 0
        or attempt_002_telemetry
        or attempt_002_clips
        or "[ComfyUI-Manager] network_mode: public" not in log_text
        or "default cache updated:" not in log_text
        or "FETCH ComfyRegistry Data" not in log_text
    ):
        raise CampaignError("Attempt-002 incident/recovery evidence contract drifted")
    attempt_003_lifecycle = _pinned_prior_snapshot(
        ATTEMPT_003_LIFECYCLE,
        ATTEMPT_003_LIFECYCLE_SHA256,
        "Attempt-003 lifecycle",
    )
    attempt_003_baseline = _pinned_prior_snapshot(
        ATTEMPT_003_BASELINE,
        ATTEMPT_003_BASELINE_SHA256,
        "Attempt-003 baseline",
    )
    attempt_003_log = _pinned_prior_snapshot(
        ATTEMPT_003_SERVER_LOG,
        ATTEMPT_003_SERVER_LOG_SHA256,
        "Attempt-003 ownership-incident server log",
    )
    attempt_003_recovery = _pinned_prior_snapshot(
        ATTEMPT_003_RECOVERY,
        ATTEMPT_003_RECOVERY_SHA256,
        "Attempt-003 ownership recovery receipt",
    )
    lifecycle_003 = json.loads(ATTEMPT_003_LIFECYCLE.read_text(encoding="utf-8"))
    baseline_003 = json.loads(ATTEMPT_003_BASELINE.read_text(encoding="utf-8"))
    recovery_003 = json.loads(ATTEMPT_003_RECOVERY.read_text(encoding="utf-8"))
    telemetry_003 = list((RESULT_ROOT / "telemetry" / "attempt-003").glob("*"))
    clips_003 = list((RESULT_ROOT / "evidence" / "attempt-003" / "clips").glob("*"))
    guard_003 = RESULT_ROOT / "evidence" / "attempt-003" / "manager_boot_guard.json"
    config_003 = Path(
        str(
            (((baseline_003.get("manager_config") or {}).get("config") or {}).get(
                "path"
            ) or "")
        )
    )
    scan_003 = MANAGER_GUARD.scan_boot_log_prefix(
        ATTEMPT_003_SERVER_LOG,
        config_003,
        expected_url=REQUIRED_COMFYUI_URL,
        require_pre_prompt=True,
    )
    recovery_hashes = recovery_003.get("attempt_evidence") or {}
    roles = [row.get("role") for row in recovery_003.get("verified_owned_chain") or []]
    if (
        lifecycle_003.get("status") != "invalid"
        or lifecycle_003.get("raw_receipts") != []
        or lifecycle_003.get("server") is not None
        or "Listener parent 9124 is not owned launcher PID 24908"
        not in "\n".join(lifecycle_003.get("errors") or [])
        or recovery_003.get("success") is not True
        or recovery_003.get("status")
        != "INVALID_PRE_MEASUREMENT_OWNERSHIP_CHECK_FALSE_NEGATIVE_RECOVERED"
        or (recovery_003.get("recovery") or {}).get("render_or_prompt_submitted")
        is not False
        or (recovery_003.get("recovery") or {}).get("port_8000_listener_count_after")
        != 0
        or (recovery_003.get("postconditions") or {}).get("telemetry_file_count")
        != 0
        or (recovery_003.get("postconditions") or {}).get("rendered_clip_file_count")
        != 0
        or (recovery_hashes.get("lifecycle") or {}).get("sha256")
        != ATTEMPT_003_LIFECYCLE_SHA256
        or (recovery_hashes.get("baseline") or {}).get("sha256")
        != ATTEMPT_003_BASELINE_SHA256
        or (recovery_hashes.get("server_log") or {}).get("sha256")
        != ATTEMPT_003_SERVER_LOG_SHA256
        or roles != ["serving-python", "windows-venv-python-shim", "owned-cmd-launcher"]
        or telemetry_003
        or clips_003
        or guard_003.exists()
        or scan_003.get("status") != "pass"
        or scan_003.get("errors") != []
    ):
        raise CampaignError("Attempt-003 ownership incident/recovery evidence drifted")
    return {
        "legacy_attempt_001": {
            "attempt_id": "legacy-attempt-001",
            "disposition": "immutable_in_place",
            "receipt": snapshot,
            "status": payload.get("status"),
            "raw_receipt_count": len(payload.get("raw_receipts") or []),
            "server_was_booted": payload.get("server") is not None,
        },
        "attempt_002_offline_incident": {
            "attempt_id": "attempt-002",
            "disposition": "immutable_in_place_invalid_pre_measurement",
            "lifecycle": attempt_002_lifecycle,
            "baseline": attempt_002_baseline,
            "server_log": attempt_002_log,
            "recovery_receipt": attempt_002_recovery,
            "measurement_accepted": False,
            "telemetry_file_count": 0,
            "rendered_clip_file_count": 0,
            "observed_manager_markers": [
                "network_mode: public",
                "default cache updated:",
                "FETCH ComfyRegistry Data",
            ],
            "recovery_status": recovery_payload.get("status"),
        },
        "attempt_003_ownership_incident": {
            "attempt_id": "attempt-003",
            "disposition": "immutable_in_place_invalid_pre_measurement",
            "lifecycle": attempt_003_lifecycle,
            "baseline": attempt_003_baseline,
            "server_log": attempt_003_log,
            "recovery_receipt": attempt_003_recovery,
            "measurement_accepted": False,
            "telemetry_file_count": 0,
            "rendered_clip_file_count": 0,
            "manager_boot_guard_created": False,
            "verified_chain_roles": roles,
            "offline_boot_log_scan": {
                "status": scan_003.get("status"),
                "prefix_sha256": scan_003.get("prefix_sha256"),
                "startup_complete_marker_count": len(
                    scan_003.get("startup_complete_markers") or []
                ),
                "forbidden_network_marker_count": len(
                    scan_003.get("forbidden_network_markers") or []
                ),
                "forbidden_credential_marker_count": len(
                    scan_003.get("forbidden_credential_markers") or []
                ),
            },
            "recovery_status": recovery_003.get("status"),
        },
    }


def campaign_execution_plan() -> dict[str, Any]:
    """Retarget the frozen workload into append-only attempt-004 evidence."""
    plan = copy.deepcopy(FIXTURES.execution_plan())
    baseline_argv = plan["desktop_baseline_argv"]
    baseline_argv[baseline_argv.index("--output") + 1] = str(BASELINE)
    boot = plan["boot_existing_otr_lane_via_start_process"]
    boot["ArgumentList"][0] = str(SERVER_LOG)
    boot["note"] = "Existing OTR WAN launcher; runtime log is LAB-owned evidence."
    for pair in plan["pairs_in_required_sequence"]:
        engine = pair["engine"]
        frames = int(pair["model_render_frames"])
        for key in ("pair_first_argv", "warm_second_argv"):
            argv = pair[key]
            run = 1 if key == "pair_first_argv" else 2
            replacements = {
                "--output": str(
                    TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run{run}.json"
                ),
                "--desktop-baseline-receipt": str(BASELINE),
                "--server-log": str(SERVER_LOG),
            }
            if key == "warm_second_argv":
                replacements["--previous-receipt"] = str(
                    TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run1.json"
                )
            for option, value in replacements.items():
                argv[argv.index(option) + 1] = value
            argv.extend(["--manager-boot-guard", str(MANAGER_BOOT_GUARD)])
    reducer_base = [
        str(PYTHON),
        str(SCRATCH / "reduce_wan_cost_ladder.py"),
        "--attempt-id",
        ATTEMPT_ID,
        "--output",
        str(FIT_RECEIPT),
    ]
    plan["reducer_check_argv"] = list(reducer_base)
    plan["reducer_write_argv"] = [*reducer_base, "--write"]
    return plan


def runbook() -> dict[str, Any]:
    plan = campaign_execution_plan()
    manager_preboot = MANAGER_GUARD.launcher_offline_evidence(LAUNCHER)
    pairs = []
    for pair in plan["pairs_in_required_sequence"]:
        engine = pair["engine"]
        frames = int(pair["model_render_frames"])
        pairs.append(
            {
                **pair,
                "pair_first_cache_buster": SIDECAR.canonical_cache_buster(
                    engine, frames, "pair_first"
                ),
                "warm_second_cache_buster": SIDECAR.canonical_cache_buster(
                    engine, frames, "warm_second"
                ),
            }
        )
    return {
        "campaign_attempt_id": ATTEMPT_ID,
        "prior_failed_attempt": prior_failed_attempt_evidence(),
        "execution_switch": [str(PYTHON), str(Path(__file__).resolve()), "--run"],
        "manager_offline_check": {
            "user_directory_authority": manager_preboot["derivation"],
            "manager_source": manager_preboot["manager_source"],
            "config": manager_preboot["config"],
            "required": (
                "exact launcher --user-directory before boot; exact serving argv "
                "--user-directory after identification; same config path/SHA; "
                "network_mode=offline; clean full-log checks before every prompt"
            ),
            "enforced_by": [
                str(SCRATCH / "capture_wan_cost_baseline.py"),
                str(SCRATCH / "wan_cost_ladder_sidecar.py"),
                str(Path(__file__).resolve()),
            ],
        },
        "baseline_capture": plan["desktop_baseline_argv"],
        "owned_boot": {
            "argv": owned_boot_command(),
            "port": SERVER_PORT,
            "ownership_proof": (
                "port had no listener before launch; serving main.py is the "
                "direct child, or the one narrow Windows exception: exact venv "
                "python shim directly under the Popen cmd launcher with identical "
                "main.py argv[1:], bounded creation times, and exact executables; "
                "port/model-path/output argv identity is receipt-bound"
            ),
            "environment_contract": {
                "set": {
                    "OTR_HEADLESS_PORT": "8000",
                    "COMFYUI_URL": REQUIRED_COMFYUI_URL,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    **MANAGER_GUARD.OFFLINE_CREDENTIAL_ENVIRONMENT,
                },
                "clear_exact": sorted(BOOT_ENV_KEYS_CLEARED),
                "clear_prefixes": list(BOOT_ENV_PREFIXES_CLEARED),
                "reason": (
                    "prevent stale reserve, model-file, prequalification, "
                    "recipe, max-frame, or alternate-lane overrides from "
                    "changing the frozen production workload; prevent any real "
                    "HF credential or HKCU fallback from crossing the offline boot"
                ),
            },
        },
        "one_resident_server": {
            "allowed": True,
            "scope": "all 16 legs",
            "warm_proof": (
                "within each cell, run1 then run2 are consecutive on identical "
                "serving PID/create-time/argv and fixture/baseline hashes; run2 "
                "hash-binds run1 and the append-only inter-run log gap must have "
                "no execution marker"
            ),
        },
        "pairs_in_required_sequence": pairs,
        "reducer_check": plan["reducer_check_argv"],
        "reducer_write": plan["reducer_write_argv"],
        "expected_raw_receipts": [str(path) for path in expected_raw_receipts()],
        "expected_clip_evidence": [str(path) for path in expected_clip_evidence()],
        "expected_final_receipts": [
            str(BASELINE),
            str(MANAGER_BOOT_GUARD),
            str(FIT_RECEIPT),
            str(LIFECYCLE_RECEIPT),
        ],
        "shutdown_proof": (
            "re-identify port 8000 and revalidate the exact captured direct-or-one-hop "
            "owned chain before terminate/kill; then require serving, optional venv "
            "shim, and cmd launcher exited and port 8000 has no listener"
        ),
    }


def _run_checked(argv: Sequence[str], label: str, *, capture: bool = False) -> str:
    print(f"[wan-cost-campaign] START {label}", flush=True)
    result = subprocess.run(
        list(argv),
        cwd=str(LAB_ROOT),
        check=False,
        text=True,
        capture_output=capture,
        env=campaign_child_environment(),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise CampaignError(
            f"{label} exited {result.returncode}" + (f": {detail}" if detail else "")
        )
    print(f"[wan-cost-campaign] DONE {label}", flush=True)
    return result.stdout if capture else ""


def campaign_child_environment(
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    environment, _credential_evidence = (
        MANAGER_GUARD.pin_offline_credential_environment(source)
    )
    environment.pop("COMFYUI_URL", None)
    environment["COMFYUI_URL"] = REQUIRED_COMFYUI_URL
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def production_boot_environment(
    source: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str], dict[str, Any]]:
    environment = dict(os.environ if source is None else source)
    removed = sorted(
        key
        for key in environment
        if key in BOOT_ENV_KEYS_CLEARED
        or any(key.startswith(prefix) for prefix in BOOT_ENV_PREFIXES_CLEARED)
    )
    for key in removed:
        environment.pop(key, None)
    environment, credential_evidence = (
        MANAGER_GUARD.pin_offline_credential_environment(environment)
    )
    environment["OTR_HEADLESS_PORT"] = str(SERVER_PORT)
    environment["COMFYUI_URL"] = REQUIRED_COMFYUI_URL
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    credential_errors = MANAGER_GUARD.offline_credential_environment_errors(
        environment
    )
    if credential_errors:
        raise CampaignError("; ".join(credential_errors))
    return environment, removed, credential_evidence


def _same_server(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        int(left.get("serving_pid") or -1) == int(right.get("serving_pid") or -2)
        and float(left.get("process_create_time") or -1)
        == float(right.get("process_create_time") or -2)
        and left.get("argv") == right.get("argv")
        and int(left.get("parent_pid") or -1) == int(right.get("parent_pid") or -2)
    )


def _listener_pids(port: int) -> list[int]:
    return sorted(
        {
            int(row["pid"])
            for row in OTR_SIDE._listener_rows(port)
            if row.get("pid") is not None
        }
    )


def verify_owned_server_chain(
    server: dict[str, Any],
    launcher: psutil.Process,
    expected_launcher_argv: Sequence[str],
    *,
    process_factory: Any = psutil.Process,
) -> dict[str, Any]:
    """Prove only the Popen launcher or its certified one-hop venv child owns server."""
    try:
        return OWNERSHIP.capture_verified_chain(
            server,
            launcher,
            expected_launcher_argv,
            process_factory=process_factory,
        )
    except OWNERSHIP.OwnershipError as exc:
        raise CampaignError(str(exc)) from exc


def _wait_for_owned_server(
    launcher: psutil.Process,
    expected_launcher_argv: Sequence[str],
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error = "listener not observed"
    while time.monotonic() < deadline:
        try:
            server = OTR_SIDE.identify_expected_otr_server(
                SERVER_PORT, MODEL_PATHS, SERVER_OUTPUT
            )
        except Exception as exc:  # listener is expected to be absent during boot
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
            continue
        # Once an exact OTR listener is visible, ancestry failure is terminal.
        # Retrying could silently adopt a different process on the same port.
        server["ownership_chain"] = verify_owned_server_chain(
            server, launcher, expected_launcher_argv
        )
        return server
    raise CampaignError(f"Owned OTR WAN server did not boot: {last_error}")


def _verify_measured_receipt(path: Path) -> dict[str, Any]:
    payload, _snapshot = SIDECAR._json_evidence(path, TELEMETRY_ROOT, "raw receipt")
    if payload.get("status") != "measured" or payload.get("errors") != []:
        raise CampaignError(f"Raw receipt is not measured-clean: {path}")
    return payload


def _shutdown_owned_server(
    server: dict[str, Any] | None,
    launcher: psutil.Process | None,
    expected_launcher_argv: Sequence[str] | None,
) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "attempted": server is not None,
        "identity_reverified": False,
        "server_exit_confirmed": False,
        "launcher_exit_confirmed": False,
        "intermediary_exit_confirmed": None,
        "port_8000_listener_pids_after": None,
        "forced_server_kill": False,
        "errors": [],
    }
    if server is None:
        if launcher is not None and launcher.is_running():
            proof["errors"].append(
                "No positively identified server; owned launcher left for manual inspection"
            )
        return proof
    if launcher is None or expected_launcher_argv is None:
        proof["errors"].append("Owned server has no launcher identity")
        return proof
    try:
        current = OTR_SIDE.identify_expected_otr_server(
            SERVER_PORT, MODEL_PATHS, SERVER_OUTPUT
        )
        if not _same_server(current, server):
            raise CampaignError("Port 8000 server identity changed; refusing termination")
        current_chain = verify_owned_server_chain(
            current, launcher, expected_launcher_argv
        )
        if current_chain != server.get("ownership_chain"):
            raise CampaignError("Owned server process chain changed; refusing termination")
        proof["identity_reverified"] = True
        process = psutil.Process(int(server["serving_pid"]))
        if not (
            float(process.create_time()) == float(server["process_create_time"])
            and process.cmdline() == server["argv"]
        ):
            raise CampaignError("Serving PID was recycled; refusing termination")
        process.terminate()
        try:
            process.wait(timeout=20)
        except psutil.TimeoutExpired:
            # Identity was reverified immediately above; this force-kill cannot
            # target a recycled or foreign process.
            process.kill()
            process.wait(timeout=10)
            proof["forced_server_kill"] = True
        proof["server_exit_confirmed"] = not psutil.pid_exists(process.pid)
        intermediary_identity = current_chain.get("intermediary")
        if intermediary_identity is not None:
            try:
                intermediary = psutil.Process(int(intermediary_identity["pid"]))
            except psutil.NoSuchProcess:
                proof["intermediary_exit_confirmed"] = True
            else:
                try:
                    if (
                        float(intermediary.create_time())
                        != float(intermediary_identity["process_create_time"])
                        or intermediary.cmdline() != intermediary_identity["argv"]
                    ):
                        raise CampaignError(
                            "Venv intermediary identity changed after server exit"
                        )
                    try:
                        intermediary.wait(timeout=10)
                    except psutil.TimeoutExpired:
                        intermediary.terminate()
                        intermediary.wait(timeout=10)
                    proof["intermediary_exit_confirmed"] = not intermediary.is_running()
                except psutil.NoSuchProcess:
                    proof["intermediary_exit_confirmed"] = True
        else:
            proof["intermediary_exit_confirmed"] = True
        try:
            launcher.wait(timeout=10)
        except psutil.TimeoutExpired:
            launcher.terminate()
            launcher.wait(timeout=10)
        proof["launcher_exit_confirmed"] = not launcher.is_running()
        proof["port_8000_listener_pids_after"] = _listener_pids(SERVER_PORT)
        if proof["port_8000_listener_pids_after"]:
            raise CampaignError(
                f"Port 8000 still has listener(s): {proof['port_8000_listener_pids_after']}"
            )
    except Exception as exc:
        proof["errors"].append(f"{type(exc).__name__}: {exc}")
    return proof


def post_shutdown_manager_audit(
    server: dict[str, Any] | None,
    manager_preboot: dict[str, Any],
    server_log_snapshot: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Audit a known server, or explicitly decline server inference pre-identification."""
    if server is None:
        return (
            {
                "status": "not_applicable_pre_identification",
                "reason": (
                    "No serving argv was positively ownership-identified; refusing "
                    "to fabricate server-derived Manager evidence from an empty argv"
                ),
                "launcher_preboot_config": manager_preboot,
                "server_log_snapshot": server_log_snapshot,
                "errors": [],
            },
            [],
        )
    try:
        manager_post_shutdown = MANAGER_GUARD.server_offline_evidence(
            server.get("argv") or [], manager_preboot
        )
        post_shutdown_log_scan = MANAGER_GUARD.scan_boot_log_prefix(
            SERVER_LOG,
            Path(manager_post_shutdown["config"]["path"]),
            expected_url=REQUIRED_COMFYUI_URL,
            require_pre_prompt=False,
        )
        errors = MANAGER_GUARD.validate_runtime_log_binding(
            post_shutdown_log_scan, SERVER_LOG
        )
        return (
            {
                "status": "pass" if not errors else "fail",
                "config": manager_post_shutdown,
                "log_scan": post_shutdown_log_scan,
                "errors": errors,
            },
            errors,
        )
    except Exception as exc:
        errors = [f"{type(exc).__name__}: {exc}"]
        return {"status": "fail", "errors": errors}, errors


def authoritative_mode_failure_evidence(
    server: dict[str, Any],
) -> dict[str, Any]:
    """Capture explicit observed server-reported modes for any identified-run abort."""
    try:
        derivation = MANAGER_GUARD.argv_user_directory(server.get("argv") or [])
        scan = MANAGER_GUARD.scan_boot_log_prefix(
            SERVER_LOG,
            Path(derivation["manager_config_path"]),
            expected_url=REQUIRED_COMFYUI_URL,
            require_pre_prompt=False,
        )
        authoritative = scan.get("authoritative_server_reported_mode") or {}
        return {
            "status": scan.get("status"),
            "observed_values": authoritative.get("observed_values"),
            "announcement_count": authoritative.get("announcement_count"),
            "resolved_mode": authoritative.get("resolved_mode"),
            "errors": scan.get("errors"),
            "log_prefix_sha256": scan.get("prefix_sha256"),
        }
    except Exception as exc:
        return {
            "status": "scan_failed",
            "observed_values": None,
            "announcement_count": None,
            "resolved_mode": None,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _assert_clean_destination() -> None:
    prior_failed_attempt_evidence()
    collisions = [
        path
        for path in [
            BASELINE,
            FIT_RECEIPT,
            LIFECYCLE_RECEIPT,
            SERVER_LOG,
            MANAGER_BOOT_GUARD,
            *expected_raw_receipts(),
            *expected_clip_evidence(),
        ]
        if path.exists()
    ]
    if collisions:
        raise CampaignError(
            "Append-only campaign destinations already exist: "
            + ", ".join(str(path) for path in collisions)
        )
    listeners = _listener_pids(SERVER_PORT)
    if listeners:
        raise CampaignError(
            f"Port {SERVER_PORT} already has listener(s) {listeners}; refusing adoption"
        )


def execute(boot_timeout_s: float) -> dict[str, Any]:
    _assert_clean_destination()
    prior_attempt = prior_failed_attempt_evidence()
    manager_initial = MANAGER_GUARD.launcher_offline_evidence(LAUNCHER)
    for engine, lengths in FIXTURES.LADDERS.items():
        for frames in lengths:
            SIDECAR.validate_fixture(engine, frames)

    plan = campaign_execution_plan()
    lifecycle: dict[str, Any] = {
        "schema_version": 1,
        "kind": "wan-cost-ladder-owned-campaign-lifecycle",
        "campaign_attempt_id": ATTEMPT_ID,
        "prior_failed_attempt": prior_attempt,
        "status": "invalid",
        "started_at_ns": time.time_ns(),
        "runbook": runbook(),
        "server": None,
        "boot_environment": None,
        "manager_offline": {"initial_preflight": manager_initial},
        "raw_receipts": [],
        "shutdown": None,
        "errors": [],
    }
    launcher_popen: subprocess.Popen[Any] | None = None
    launcher_process: psutil.Process | None = None
    owned_boot_argv: list[str] | None = None
    server: dict[str, Any] | None = None
    manager_preboot = manager_initial
    try:
        _run_checked(plan["desktop_baseline_argv"], "quiescent desktop baseline")
        if not BASELINE.is_file():
            raise CampaignError("Baseline command did not publish its receipt")
        baseline_payload = json.loads(BASELINE.read_text(encoding="utf-8"))
        baseline_manager = baseline_payload.get("manager_config") or {}
        if MANAGER_GUARD.validate_offline_evidence(
            baseline_manager, require_current_hash=True
        ):
            raise CampaignError("Baseline Manager offline evidence is invalid")
        manager_preboot = MANAGER_GUARD.launcher_offline_evidence(LAUNCHER)
        if (
            (manager_preboot.get("config") or {}).get("sha256")
            != (manager_initial.get("config") or {}).get("sha256")
            or (baseline_manager.get("config") or {}).get("sha256")
            != (manager_initial.get("config") or {}).get("sha256")
        ):
            raise CampaignError("Manager config SHA changed between preflight and boot")
        lifecycle["manager_offline"]["baseline"] = baseline_manager
        lifecycle["manager_offline"]["immediately_preboot"] = manager_preboot

        lease = GpuLease(
            LAB_ROOT / ".gpu.lock",
            LAB_ROOT / ".suite.lock",
            LAB_ROOT / ".coordinator.mutex",
        )
        lease.acquire()
        try:
            if _listener_pids(SERVER_PORT):
                raise CampaignError("Port 8000 became occupied after baseline")
            SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
            command = runbook()["owned_boot"]["argv"]
            owned_boot_argv = list(command)
            (
                boot_environment,
                removed_environment_keys,
                credential_environment_evidence,
            ) = production_boot_environment()
            lifecycle["boot_environment"] = {
                "set": {
                    "OTR_HEADLESS_PORT": boot_environment["OTR_HEADLESS_PORT"],
                    "COMFYUI_URL": boot_environment["COMFYUI_URL"],
                    "PYTHONDONTWRITEBYTECODE": boot_environment[
                        "PYTHONDONTWRITEBYTECODE"
                    ],
                    **{
                        key: boot_environment[key]
                        for key in MANAGER_GUARD.OFFLINE_CREDENTIAL_ENVIRONMENT
                    },
                },
                "removed_keys": removed_environment_keys,
                "offline_credentials": credential_environment_evidence,
                "contract": runbook()["owned_boot"]["environment_contract"],
            }
            credential_evidence_errors = (
                MANAGER_GUARD.validate_offline_credential_environment_evidence(
                    credential_environment_evidence
                )
            )
            if credential_evidence_errors:
                raise CampaignError(
                    "Production boot credential contract failed: "
                    + "; ".join(credential_evidence_errors)
                )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            launcher_popen = subprocess.Popen(
                command,
                cwd=str(OTR_ROOT),
                creationflags=creationflags,
                env=boot_environment,
            )
            launcher_process = psutil.Process(launcher_popen.pid)
            server = _wait_for_owned_server(
                launcher_process, owned_boot_argv, boot_timeout_s
            )
            lifecycle["server"] = server
            manager_postboot = MANAGER_GUARD.server_offline_evidence(
                server.get("argv") or [], manager_preboot
            )
            try:
                boot_log_scan = MANAGER_GUARD.wait_for_clean_startup_gate(
                    SERVER_LOG,
                    Path(manager_postboot["config"]["path"]),
                    timeout_s=max(30.0, min(float(boot_timeout_s), 180.0)),
                    expected_url=REQUIRED_COMFYUI_URL,
                )
            except Exception:
                try:
                    failed_scan = MANAGER_GUARD.scan_boot_log_prefix(
                        SERVER_LOG,
                        Path(manager_postboot["config"]["path"]),
                        expected_url=REQUIRED_COMFYUI_URL,
                        require_pre_prompt=True,
                    )
                    authoritative = failed_scan.get(
                        "authoritative_server_reported_mode"
                    ) or {}
                    lifecycle["manager_offline"][
                        "authoritative_mode_incident"
                    ] = {
                        "status": failed_scan.get("status"),
                        "observed_values": authoritative.get("observed_values"),
                        "announcement_count": authoritative.get(
                            "announcement_count"
                        ),
                        "resolved_mode": authoritative.get("resolved_mode"),
                        "errors": failed_scan.get("errors"),
                        "log_prefix_sha256": failed_scan.get("prefix_sha256"),
                    }
                except Exception as scan_exc:
                    lifecycle["manager_offline"][
                        "authoritative_mode_incident"
                    ] = {
                        "status": "scan_failed",
                        "observed_values": None,
                        "announcement_count": None,
                        "resolved_mode": None,
                        "errors": [f"{type(scan_exc).__name__}: {scan_exc}"],
                    }
                raise
            guard_payload = {
                "schema_version": 1,
                "kind": "wan-cost-ladder-manager-offline-boot-guard",
                "campaign_attempt_id": ATTEMPT_ID,
                "status": "pass",
                "created_at_ns": time.time_ns(),
                "server_instance": server,
                "preboot": manager_preboot,
                "post_identification": manager_postboot,
                "boot_log_scan": boot_log_scan,
                "authoritative_server_reported_mode": boot_log_scan[
                    "authoritative_server_reported_mode"
                ],
                "boot_environment": lifecycle["boot_environment"],
                "source": {
                    "path": str((SCRATCH / "manager_offline_guard.py").resolve()),
                    "sha256": SIDECAR.BASE.sha256_file(
                        SCRATCH / "manager_offline_guard.py"
                    ),
                },
            }
            SIDECAR.BASE.atomic_create_json(MANAGER_BOOT_GUARD, guard_payload)
            lifecycle["manager_offline"]["post_identification"] = manager_postboot
            lifecycle["manager_offline"]["boot_guard"] = {
                "path": str(MANAGER_BOOT_GUARD),
                "sha256": SIDECAR.BASE.sha256_file(MANAGER_BOOT_GUARD),
                "log_scan": boot_log_scan,
            }
        finally:
            lease.release()

        for pair in plan["pairs_in_required_sequence"]:
            engine = pair["engine"]
            frames = int(pair["model_render_frames"])
            for argv, role, run in (
                (pair["pair_first_argv"], "pair_first", 1),
                (pair["warm_second_argv"], "warm_second", 2),
            ):
                _run_checked(argv, f"{engine} f{frames:03d} {role}")
                path = TELEMETRY_ROOT / f"{engine}_f{frames:03d}_run{run}.json"
                receipt = _verify_measured_receipt(path)
                if not _same_server(receipt.get("server_instance") or {}, server):
                    raise CampaignError(f"{path.name} crossed the owned server identity")
                lifecycle["raw_receipts"].append(
                    {
                        "path": str(path),
                        "sha256": SIDECAR.BASE.sha256_file(path),
                        "cache_buster": int(receipt["cache_buster"]),
                        "rendered_clip_evidence": receipt.get("rendered_clip"),
                    }
                )

        reducer_preview = _run_checked(
            plan["reducer_check_argv"], "receipt reducer check", capture=True
        )
        preview_payload = json.loads(reducer_preview)
        if preview_payload.get("status") != "MEASURED_CANDIDATE_ONLY":
            raise CampaignError("Reducer preview did not produce measured candidates")
        _run_checked(plan["reducer_write_argv"], "receipt reducer write")
        if not FIT_RECEIPT.is_file():
            raise CampaignError("Reducer did not publish the fit receipt")
        lifecycle["fit_receipt"] = {
            "path": str(FIT_RECEIPT),
            "sha256": SIDECAR.BASE.sha256_file(FIT_RECEIPT),
        }
        manager_final = MANAGER_GUARD.server_offline_evidence(
            server.get("argv") or [], manager_preboot
        )
        final_log_scan = MANAGER_GUARD.scan_boot_log_prefix(
            SERVER_LOG,
            Path(manager_final["config"]["path"]),
            expected_url=REQUIRED_COMFYUI_URL,
            require_pre_prompt=False,
        )
        final_errors = MANAGER_GUARD.validate_runtime_log_binding(
            final_log_scan, SERVER_LOG
        )
        lifecycle["manager_offline"]["final_pre_shutdown"] = {
            "config": manager_final,
            "log_scan": final_log_scan,
            "errors": final_errors,
        }
        if final_errors:
            raise CampaignError(
                "Final pre-shutdown Manager offline audit failed: "
                + "; ".join(final_errors)
            )
    except BaseException as exc:
        if server is not None and not lifecycle["manager_offline"].get(
            "authoritative_mode_incident"
        ):
            lifecycle["manager_offline"]["authoritative_mode_incident"] = (
                authoritative_mode_failure_evidence(server)
            )
        lifecycle["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        shutdown_lease = GpuLease(
            LAB_ROOT / ".gpu.lock",
            LAB_ROOT / ".suite.lock",
            LAB_ROOT / ".coordinator.mutex",
        )
        try:
            shutdown_lease.acquire()
            lifecycle["shutdown"] = _shutdown_owned_server(
                server, launcher_process, owned_boot_argv
            )
        except Exception as exc:
            lifecycle["shutdown"] = {
                "attempted": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        finally:
            try:
                shutdown_lease.release()
            except Exception as exc:
                lifecycle["errors"].append(
                    f"shutdown GPU lease release failed: {type(exc).__name__}: {exc}"
                )

    shutdown = lifecycle.get("shutdown") or {}
    try:
        prior_after = prior_failed_attempt_evidence()
        lifecycle["prior_failed_attempt_after"] = prior_after
        if prior_after != prior_attempt:
            lifecycle["errors"].append(
                "Attempt-001/002/003 immutable evidence changed during attempt-004"
            )
    except Exception as exc:
        lifecycle["errors"].append(
            f"legacy attempt immutability recheck failed: {type(exc).__name__}: {exc}"
        )
    server_log_snapshot = SIDECAR.BASE.stable_file_snapshot(SERVER_LOG)
    post_shutdown_audit, post_shutdown_errors = post_shutdown_manager_audit(
        server, manager_preboot, server_log_snapshot
    )
    lifecycle["manager_offline"]["post_shutdown"] = post_shutdown_audit
    if post_shutdown_errors:
        lifecycle["errors"].append(
            "Post-shutdown Manager offline audit failed: "
            + "; ".join(post_shutdown_errors)
        )
    success = (
        not lifecycle["errors"]
        and len(lifecycle["raw_receipts"]) == 16
        and FIT_RECEIPT.is_file()
        and shutdown.get("identity_reverified") is True
        and shutdown.get("server_exit_confirmed") is True
        and shutdown.get("intermediary_exit_confirmed") is True
        and shutdown.get("launcher_exit_confirmed") is True
        and shutdown.get("port_8000_listener_pids_after") == []
        and shutdown.get("errors") == []
        and server_log_snapshot.get("exists") is True
        and int(server_log_snapshot.get("bytes") or 0) > 0
        and MANAGER_BOOT_GUARD.is_file()
        and ((lifecycle.get("manager_offline") or {}).get("post_shutdown") or {}).get(
            "status"
        )
        == "pass"
    )
    lifecycle["status"] = "measured" if success else "invalid"
    lifecycle["finished_at_ns"] = time.time_ns()
    lifecycle["server_log"] = server_log_snapshot
    lifecycle["source"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": SIDECAR.BASE.sha256_file(Path(__file__).resolve()),
    }
    SIDECAR.BASE.atomic_create_json(LIFECYCLE_RECEIPT, lifecycle)
    return lifecycle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--boot-timeout-s", type=float, default=240.0)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(runbook(), indent=2, sort_keys=True))
        return 0
    if args.boot_timeout_s < 30:
        raise CampaignError("Boot timeout must be at least 30 seconds")
    lifecycle = execute(args.boot_timeout_s)
    print(
        f"[wan-cost-campaign] {lifecycle['status'].upper()} "
        f"raw_receipts={len(lifecycle['raw_receipts'])} "
        f"lifecycle={LIFECYCLE_RECEIPT}",
        flush=True,
    )
    return 0 if lifecycle["status"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
