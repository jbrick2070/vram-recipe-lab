#!/usr/bin/env python
"""Replay one immutable node-92 bundle with an inert cache buster.

This LAB-owned shim preserves OTR's existing ``otr_visual_smoke`` replay path.
It changes exactly one outer ComfyUI input: ``OTR_VideoRenderBatch.oom_index``.
That widget is inert when mode is ``episode`` but makes two otherwise identical
prompts execute instead of returning the prior cached history.

No OTR file is modified.  A machine-readable result line is printed so the
200 ms sidecar can bind the prompt id, executed set, prompt hash, and node output
to its immutable telemetry receipt.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
OTR_SCRIPTS = OTR_ROOT / "scripts"
OTR_VISUAL_SMOKE = OTR_SCRIPTS / "otr_visual_smoke.py"
EXPECTED_BUNDLE_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_cost_ladder_measurement"
)
RESULT_PREFIX = "WAN_COST_REPLAY_RESULT="
REQUIRED_COMFYUI_URL = "http://127.0.0.1:8000"
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


class ReplayError(RuntimeError):
    pass


def validate_comfyui_endpoint(environment: dict[str, str] | None = None) -> str:
    """Refuse any endpoint except the positively owned OTR port-8000 lane."""
    source = os.environ if environment is None else environment
    value = str(source.get("COMFYUI_URL") or "")
    if value != REQUIRED_COMFYUI_URL:
        raise ReplayError(
            "COMFYUI_URL must be pinned exactly to "
            f"{REQUIRED_COMFYUI_URL}, found {value!r}"
        )
    return value


def validate_offline_credential_environment(
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Self-attest the child boundary without reading or returning token values."""
    source = os.environ if environment is None else environment
    wrong = sorted(
        key
        for key, expected in OFFLINE_CREDENTIAL_ENVIRONMENT.items()
        if source.get(key) != expected
    )
    present_scrubbed = sorted(
        key for key in SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS if key in source
    )
    known = set(OFFLINE_CREDENTIAL_ENVIRONMENT) | set(
        SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS
    )
    case_variants = sorted(
        key for key in source if key.upper() in known and key != key.upper()
    )
    if wrong or present_scrubbed or case_variants:
        raise ReplayError(
            "Offline credential environment contract failed for key name(s): "
            + ", ".join(wrong + present_scrubbed + case_variants)
        )
    return {
        "validated": True,
        "nonsecret_sentinel_length": len(OFFLINE_TOKEN_SENTINEL),
        "set_key_names": sorted(OFFLINE_CREDENTIAL_ENVIRONMENT),
        "scrubbed_key_names_absent": list(SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS),
        "ambient_values_never_read_or_returned": True,
    }


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "otr_visual_smoke_wan_cost_replay", OTR_VISUAL_SMOKE
    )
    if spec is None or spec.loader is None:
        raise ReplayError(f"Cannot load OTR visual-smoke harness: {OTR_VISUAL_SMOKE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_prompt_sha256(prompt: dict[str, Any]) -> str:
    encoded = json.dumps(
        prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inject_cache_buster(prompt: dict[str, Any], cache_buster: int) -> dict[str, Any]:
    """Return a deep copy whose only changed value is node-92 ``oom_index``."""
    if not 1 <= int(cache_buster) <= 399:
        raise ReplayError("cache_buster must be in the live node schema range 1..399")
    result = copy.deepcopy(prompt)
    if set(result) != {"92"}:
        raise ReplayError(f"Expected exactly pruned node 92, found {sorted(result)}")
    spec = result["92"]
    if spec.get("class_type") != "OTR_VideoRenderBatch":
        raise ReplayError("Pruned node 92 is not OTR_VideoRenderBatch")
    inputs = spec.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("mode") != "episode":
        raise ReplayError("Cache busting is allowed only for mode=episode")
    if "oom_index" not in inputs:
        raise ReplayError("Live workflow schema did not serialize node-92 oom_index")
    inputs["oom_index"] = int(cache_buster)
    return result


def _within(path: Path, root: Path) -> Path:
    resolved = Path(os.path.abspath(os.fspath(path)))
    boundary = Path(os.path.abspath(os.fspath(root)))
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise ReplayError(f"Bundle escapes expected root {boundary}: {resolved}") from exc
    return resolved


def validate_bundle(bundle: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle = _within(bundle, EXPECTED_BUNDLE_ROOT)
    contract_path = bundle / "fixture_contract.json"
    ledger_path = bundle / "baked_ledger.json"
    if not contract_path.is_file() or not ledger_path.is_file():
        raise ReplayError(f"Incomplete WAN cost bundle: {bundle}")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    engine = str(contract.get("engine") or "")
    frames = int(contract.get("model_render_frames") or 0)
    expected_name = f"{engine}_f{frames:03d}"
    if bundle.name != expected_name:
        raise ReplayError(f"Bundle name {bundle.name!r} does not match {expected_name!r}")
    shots = ((ledger.get("video") or {}).get("shots") or [])
    if len(shots) != 1 or shots[0].get("engine_id") != engine:
        raise ReplayError("Bundle ledger engine binding drifted")
    plan = shots[0].get("coverage_plan") or {}
    segments = plan.get("segments") or []
    expected_segment = {
        "index": 0,
        "render_frames": frames,
        "drop_head": 0,
        "trim_tail": 1,
    }
    if (
        int(shots[0].get("target_frame_count") or 0) != frames - 1
        or plan.get("target_visible_frames") != frames - 1
        or plan.get("join_mode") != "single"
        or segments != [expected_segment]
    ):
        raise ReplayError("Bundle does not prove exact N-render/N-1-delivery coverage")
    return contract, ledger


def _node_output_texts(entry: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for node_output in (entry.get("outputs") or {}).values():
        for value in (node_output.get("text") or []):
            texts.append(str(value))
    return texts


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    pinned_url = validate_comfyui_endpoint()
    credential_environment = validate_offline_credential_environment()
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1" or not sys.dont_write_bytecode:
        raise ReplayError(
            "Replay must run with PYTHONDONTWRITEBYTECODE=1 to keep OTR read-only"
        )
    bundle = _within(Path(args.bundle), EXPECTED_BUNDLE_ROOT)
    contract, _ = validate_bundle(bundle)
    harness = _load_harness()
    ok, problems = harness.preflight_bundle(str(bundle))
    if not ok:
        raise ReplayError("Bundle preflight failed: " + "; ".join(problems))

    if str(OTR_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(OTR_SCRIPTS))
    from otr_api import (  # noqa: E402
        COMFYUI_URL,
        fetch_schemas,
        load_workflow,
        poll_history,
        submit_prompt,
    )
    import requests  # noqa: E402

    if COMFYUI_URL != pinned_url:
        raise ReplayError(
            f"otr_api endpoint drifted after import: {COMFYUI_URL!r} != {pinned_url!r}"
        )

    ledger_path = bundle / "baked_ledger.json"
    manifest_path = bundle / "bundle_manifest.json"
    ledger_json = ledger_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    master = str(manifest.get("baked_master") or "")
    workflow_path = Path(args.workflow) if args.workflow else Path(harness.WORKFLOW_PATH)
    schemas = fetch_schemas()
    workflow = load_workflow(str(workflow_path))
    base_prompt = harness.build_pruned_prompt(
        workflow,
        schemas,
        ledger_json=ledger_json,
        master_audio_path=master,
        engine=None,
        keep_validator=False,
    )
    harness.assert_prompt_pruned(base_prompt, keep_validator=False)
    prompt = inject_cache_buster(base_prompt, args.cache_buster)
    harness.assert_prompt_pruned(prompt, keep_validator=False)

    before_master = harness.sha256_file(master) if master and os.path.isfile(master) else ""
    prompt_sha = canonical_prompt_sha256(prompt)
    print(
        "[wan-cost-replay] submitting engine=%s frames=%s cache_buster=%s prompt_sha256=%s"
        % (
            contract["engine"],
            contract["model_render_frames"],
            args.cache_buster,
            prompt_sha,
        ),
        flush=True,
    )
    prompt_id = submit_prompt(prompt)
    status, error = poll_history(prompt_id, timeout_s=args.timeout)
    history = requests.get(
        "%s/history/%s" % (COMFYUI_URL, prompt_id), timeout=15
    ).json()
    entry = history.get(prompt_id, {}) if isinstance(history, dict) else {}
    executed = harness.executed_node_set(entry)
    executed_ok, executed_detail = harness.verify_executed(
        executed, keep_validator=False
    )
    after_master = harness.sha256_file(master) if master and os.path.isfile(master) else ""
    result = {
        "schema_version": 1,
        "kind": "wan-cost-ladder-cachebust-replay",
        "comfyui_url": pinned_url,
        "python_dont_write_bytecode": True,
        "offline_credential_environment": credential_environment,
        "engine": contract["engine"],
        "model_render_frames": int(contract["model_render_frames"]),
        "delivered_frames": int(contract["delivered_frames"]),
        "cache_buster": int(args.cache_buster),
        "cache_buster_field": "OTR_VideoRenderBatch.oom_index",
        "cache_buster_inert_contract": "mode=episode",
        "prompt_id": str(prompt_id),
        "prompt_sha256": prompt_sha,
        "status": status,
        "error": str(error or ""),
        "executed": executed_detail,
        "master_audio_unchanged": bool(before_master and before_master == after_master),
        "master_audio_sha256": before_master,
        "node_output_texts": _node_output_texts(entry),
        "bundle": str(bundle),
        "fixture_contract_sha256": harness.sha256_file(str(bundle / "fixture_contract.json")),
        "baked_ledger_sha256": harness.sha256_file(str(ledger_path)),
    }
    success = (
        status == "SUCCESS"
        and not error
        and executed_ok
        and result["master_audio_unchanged"]
    )
    result["success"] = success
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)
    print("[wan-cost-replay] %s" % ("PASS" if success else "FAIL"), flush=True)
    return (0 if success else 1), result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--cache-buster", required=True, type=int)
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--workflow", default="")
    args = parser.parse_args(argv)
    if args.timeout < 60:
        parser.error("--timeout must be at least 60 seconds")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        code, _ = run(parse_args(argv))
        return code
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "kind": "wan-cost-ladder-cachebust-replay",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(RESULT_PREFIX + json.dumps(failure, sort_keys=True), flush=True)
        print(f"[wan-cost-replay] FAIL: {failure['error']}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
