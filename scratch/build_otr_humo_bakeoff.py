#!/usr/bin/env python
"""Build deterministic OTR-side HuMo bakeoff receipts from frozen evidence.

This script never renders, boots, stops, or queries a server. It reopens the
lab-owned telemetry and media artifacts, verifies the captured OTR dirty
baseline, probes every native/review clip, and emits measurement-only receipts.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OTR = Path(r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio")
COMFY_INPUT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\input")
OTR_STAGE = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_humo_lab_bakeoff\inputs"
)
RESULTS = ROOT / "results" / "otr_side"
TELEMETRY = RESULTS / "telemetry"
SOURCE_REPORTS = RESULTS / "source_reports"
FFPROBE = Path(
    shutil.which("ffprobe")
    or r"C:\Users\jeffr\AppData\Local\Microsoft\WinGet\Links\ffprobe.exe"
)
FFMPEG = Path(
    shutil.which("ffmpeg")
    or r"C:\Users\jeffr\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
)

PORTRAIT_SHA = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
TTS_SHA = "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
OTR_HEAD = "15f23044a6f1224a61a39dc38e1e60875a894dd6"

ENTRY_STATUS = [
    " M config/profiles/otr_g4_wan_ti2v.json",
    " M nodes/_otr_video_engines/eng_wan_i2v.py",
    " M tmp/_chain_720.ps1",
    " M tmp/_rearm_gate.ps1",
    " M tmp/_status_bake.ps1",
    "?? config/profiles/otr_sbcov_1.json",
    "?? config/profiles/otr_sbcov_2.json",
    "?? config/profiles/otr_sbcov_3.json",
    "?? config/profiles/otr_sbcov_4.json",
    "?? config/profiles/otr_sbcov_5.json",
    "?? config/profiles/otr_sbcov_6.json",
    "?? config/source_banks/_corpus/_vendor_report.json",
    "?? config/source_banks/_corpus/monkeys_paw.provenance.json",
    "?? config/source_banks/_corpus/monkeys_paw.txt",
    "?? docs/2026-08-08-PROBLEM-STATEMENT-claims-not-performed.md",
    "?? kibitz/",
    "?? uv.lock",
]

ENTRY_FILE_HASHES = {
    "config/profiles/otr_g4_wan_ti2v.json": "789f6703a9bac666c226cd08a2f4bbc682df472c325cc9348e3135a3fdb755cb",
    "nodes/_otr_video_engines/eng_wan_i2v.py": "e8e967145b654bf5c48c875ce920d6ac57b40637091ffa3f53d23686680e2454",
    "tmp/_chain_720.ps1": "f59b9f322fb7c84d5bac88b367082d16e268a8b7125e1e0392f0edaecca7042a",
    "tmp/_rearm_gate.ps1": "ffe1e2824b52f00f86001fee827c2a642f3f0fdae8f2848b059168cefd1517e9",
    "tmp/_status_bake.ps1": "b07be6791fdaa8f5a9649bf27ef0a96bff935951563d663f58c1ea526813a8eb",
    "config/profiles/otr_sbcov_1.json": "050d4a602bdd4902101b089179b8a2c5e6aefb8c4e3df78613c5f6f4b7b6b5c9",
    "config/profiles/otr_sbcov_2.json": "00d51347f1fba5a4adcf4d684c5a234e893b88db57c2bfafc1c8f2709b3d0b8f",
    "config/profiles/otr_sbcov_3.json": "187f792c5447d9d192331e04a674d3bf9f6d45802e2c48de030e10ddbc511493",
    "config/profiles/otr_sbcov_4.json": "8a459c64348347e4954f0e673726cd1aa39483006218a6c98c4fbf11e5f1d23d",
    "config/profiles/otr_sbcov_5.json": "10e2c821e1081f708a39172b13c314fd9e5e10bbabe6f81b242dc5f03259a893",
    "config/profiles/otr_sbcov_6.json": "cfbc25bb1b8b1fa691cb6fe67383a08179ee141f893a5c8f1b3fbe7d7aa9a933",
    "config/source_banks/_corpus/_vendor_report.json": "ed0ddd3ce8766866619e6f67d70a70feee95ec85fa00c9874eb86c0836087d04",
    "config/source_banks/_corpus/monkeys_paw.provenance.json": "ca6ff8acee43e5f1775c5f8bc15d1fd475bdfb60ee4d8e6bfbffd92ab6af969a",
    "config/source_banks/_corpus/monkeys_paw.txt": "df13c3999e1ef2c347e7e53b585838dba5873a64921cca4c9f80cd0bbbdf3acf",
    "docs/2026-08-08-PROBLEM-STATEMENT-claims-not-performed.md": "5c75d1c808227a31e4a504f0233773f13a1a52f44a7e6a9e061c59d5ce268e73",
    "uv.lock": "b28a9d5dd5e5a48d123080e806e0be74ed3a67f8764f9376b7c26d2b2d200036",
}

ROUTE_FILES = [
    "scripts/_otr_soak_server_launch.cmd",
    "scripts/_otr_single_engine_smoke.py",
    "nodes/otr_video_render_batch.py",
    "nodes/_otr_video_engines/render_driver.py",
    "nodes/_otr_video_engines/eng_humo.py",
]

RUNS = [
    {
        "name": "humo_1_7b_bakeoff_take1",
        "engine": "humo_1.7B",
        "model": "HuMo 1.7B fp16",
        "profile": "otr_w45_humo_1_7b",
        "take": 1,
        "telemetry": "humo_1_7b_bakeoff_take1_attempt2.json",
        "failed_preflight": "humo_1_7b_bakeoff_take1.json",
        "source_report": None,
        "native": "humo_1_7b_bakeoff_take1_native_silent.mp4",
        "review": "humo_1_7b_bakeoff_take1.mp4",
        "frames": 129,
        "width": 480,
        "height": 832,
        "fps": 25.0,
    },
    {
        "name": "humo_1_7b_bakeoff_take2",
        "engine": "humo_1.7B",
        "model": "HuMo 1.7B fp16",
        "profile": "otr_w45_humo_1_7b",
        "take": 2,
        "telemetry": "humo_1_7b_bakeoff_take2.json",
        "failed_preflight": None,
        "source_report": "humo_1_7b_bakeoff_take2_node_report.json",
        "native": "humo_1_7b_bakeoff_take2_native_silent.mp4",
        "review": "humo_1_7b_bakeoff_take2.mp4",
        "frames": 129,
        "width": 480,
        "height": 832,
        "fps": 25.0,
    },
    {
        "name": "humo_14b_fp8_bakeoff_take1",
        "engine": "humo",
        "model": "HuMo 14B FP8 + LightX2V 6-step",
        "profile": "otr_w45_humo",
        "take": 1,
        "telemetry": "humo_14b_fp8_bakeoff_take1.json",
        "failed_preflight": None,
        "source_report": "humo_14b_fp8_bakeoff_take1_node_report.json",
        "native": "humo_14b_fp8_bakeoff_take1_native_silent.mp4",
        "review": "humo_14b_fp8_bakeoff_take1.mp4",
        "frames": 97,
        "width": 480,
        "height": 832,
        "fps": 25.0,
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_text(argv: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        encoding="utf-8", errors="strict", check=True,
    )
    return result.stdout


def probe(path: Path) -> dict[str, Any]:
    return json.loads(
        run_text([
            str(FFPROBE), "-v", "error", "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,"
            "r_frame_rate,avg_frame_rate,nb_frames,duration,sample_rate,channels",
            "-of", "json", str(path),
        ])
    )


def stream_hash(path: Path, selector: str) -> str:
    value = run_text([
        str(FFMPEG), "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(path), "-map", selector, "-c", "copy", "-f", "hash",
        "-hash", "sha256", "-",
    ]).strip()
    if not value.startswith("SHA256=") or len(value) != 71:
        raise AssertionError(f"unexpected stream hash output for {path}: {value!r}")
    return value.split("=", 1)[1].lower()


def video_row(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in payload.get("streams", []) if row.get("codec_type") == "video"]
    assert len(rows) == 1, rows
    return rows[0]


def audio_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = [row for row in payload.get("streams", []) if row.get("codec_type") == "audio"]
    assert len(rows) <= 1, rows
    return rows[0] if rows else None


def git_lines(*args: str) -> list[str]:
    return run_text(["git", *args], cwd=OTR).splitlines()


def build_worktree_receipt() -> dict[str, Any]:
    final_head = run_text(["git", "rev-parse", "HEAD"], cwd=OTR).strip()
    final_status = git_lines("status", "--short", "-uall")
    final_hashes = {rel: sha256_file(OTR / rel) for rel in ENTRY_FILE_HASHES}
    assert final_head == OTR_HEAD
    assert final_status == ENTRY_STATUS, (final_status, ENTRY_STATUS)
    assert final_hashes == ENTRY_FILE_HASHES
    return {
        "receipt_schema_version": 1,
        "receipt_kind": "otr-worktree-integrity",
        "measured": "otr-side production lane",
        "entry_head": OTR_HEAD,
        "final_head": final_head,
        "entry_dirty": True,
        "final_dirty": True,
        "clean_claim_possible": False,
        "entry_status_lines": ENTRY_STATUS,
        "final_status_lines": final_status,
        "entry_file_sha256s": ENTRY_FILE_HASHES,
        "final_file_sha256s": final_hashes,
        "nested_untracked_scope": {
            "path": "kibitz/",
            "entry_and_final_top_level_marker": "?? kibitz/",
            "byte_identity_claim": False,
            "note": "Nested untracked repository contents were outside the captured top-level hash scope.",
        },
        "matched_captured_entry_baseline": True,
        "production_code_changed_by_session": False,
        "status": "UNCHANGED RELATIVE TO DIRTY ENTRY BASELINE",
    }


def fixture_contract() -> dict[str, Any]:
    paths = {
        "source_portrait": ROOT / "fixtures" / "portrait.png",
        "source_tts": ROOT / "fixtures" / "tts_dialogue.wav",
        "otr_stage_portrait": OTR_STAGE / "humo_lab_portrait_3ce7b724.png",
        "otr_stage_tts": OTR_STAGE / "humo_lab_tts_30c51f3f.wav",
        "comfy_input_portrait": COMFY_INPUT / "humo_lab_portrait_3ce7b724.png",
        "comfy_input_tts": COMFY_INPUT / "humo_lab_tts_30c51f3f.wav",
    }
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    assert set(hashes.values()) == {PORTRAIT_SHA, TTS_SHA}
    return {
        "fixture_sha256s": {"portrait.png": PORTRAIT_SHA, "tts_dialogue.wav": TTS_SHA},
        "copy_chain": {
            name: {"path": str(path), "bytes": path.stat().st_size, "sha256": hashes[name]}
            for name, path in paths.items()
        },
        "raw_tts_duration_s": 10.0,
    }


def route_fingerprints(profile: str) -> dict[str, Any]:
    files = [*ROUTE_FILES, f"config/profiles/{profile}.json"]
    return {rel: {"bytes": (OTR / rel).stat().st_size, "sha256": sha256_file(OTR / rel)} for rel in files}


def sample_cadence(samples: list[dict[str, Any]]) -> dict[str, float | int]:
    ns = [int(row["sampled_at_ns"]) for row in samples]
    assert len(ns) >= 2 and ns == sorted(ns)
    gaps = [(right - left) / 1e9 for left, right in zip(ns, ns[1:])]
    ordered = sorted(gaps)
    p95 = ordered[math.floor(0.95 * (len(ordered) - 1))]
    return {
        "sample_count": len(ns),
        "mean_gap_s": sum(gaps) / len(gaps),
        "max_gap_s": max(gaps),
        "p95_gap_s": p95,
    }


def build_run_receipt(run: dict[str, Any], worktree_sha: str) -> dict[str, Any]:
    telemetry_path = TELEMETRY / run["telemetry"]
    telemetry = read_json(telemetry_path)
    assert telemetry["status"] == "ok"
    assert telemetry["command_returncode"] == 0
    assert telemetry["command_contract"]["engine"] == run["engine"]
    assert telemetry["command_contract"]["frames"] == run["frames"]
    assert telemetry["command_contract"]["request_seed"] == 7
    assert telemetry["command_contract"]["portrait_sha256"] == PORTRAIT_SHA
    assert telemetry["command_contract"]["audio_sha256"] == TTS_SHA
    assert telemetry["sampler"]["sample_error_count"] == 0

    native = ROOT / "outputs" / run["native"]
    review = ROOT / "outputs" / run["review"]
    native_probe = probe(native)
    review_probe = probe(review)
    native_video = video_row(native_probe)
    review_video = video_row(review_probe)
    assert audio_row(native_probe) is None
    review_audio = audio_row(review_probe)
    assert review_audio is not None
    assert int(review_video["width"]) == run["width"]
    assert int(review_video["height"]) == run["height"]
    assert int(review_video["nb_frames"]) == run["frames"]
    assert float(review_video["duration"]) == run["frames"] / run["fps"]
    assert stream_hash(native, "0:v:0") == stream_hash(review, "0:v:0")
    assert sha256_file(native) == telemetry["artifact_after"]["sha256"]

    source_report = None
    source_report_hash = None
    engine_elapsed = None
    if run["source_report"]:
        source_path = SOURCE_REPORTS / run["source_report"]
        source_report = read_json(source_path)
        source_report_hash = sha256_file(source_path)
        assert source_report["ok"] is True
        assert source_report["engine"] == run["engine"]
        engine_elapsed = float(source_report["elapsed_s"])

    failed_preflight = None
    if run["failed_preflight"]:
        failed_path = TELEMETRY / run["failed_preflight"]
        failed = read_json(failed_path)
        assert failed["status"] == "failed"
        assert failed["command_returncode"] == 1
        failed_preflight = {
            "path": failed_path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(failed_path),
            "accepted_prompt": False,
            "rendered": False,
            "reason": "oom_index cache-buster 4201 exceeded live max 399",
        }

    duration_s = float(telemetry["render_to_artifact_s"])
    output_duration_s = float(review_video["duration"])
    cadence = sample_cadence(telemetry["sampler"]["samples"])
    monitor = {
        "interval_s": float(telemetry["sampler"]["interval_s"]),
        **cadence,
        "sample_error_count": int(telemetry["sampler"]["sample_error_count"]),
        "metric_vram": "nvidia-smi device-total memory.used",
        "metric_host_ram": "psutil.virtual_memory().used system-wide",
        "telemetry_path": telemetry_path.relative_to(ROOT).as_posix(),
        "telemetry_sha256": sha256_file(telemetry_path),
        "sidecar_sha256": sha256_file(ROOT / "scratch" / "otr_resource_sidecar.py"),
    }
    identity = {
        "engine": run["engine"],
        "profile_reference": run["profile"],
        "seed": 7,
        "frames": run["frames"],
        "fixture_sha256s": {"portrait.png": PORTRAIT_SHA, "tts_dialogue.wav": TTS_SHA},
        "route_fingerprints": route_fingerprints(run["profile"]),
        "server_instance": telemetry["server_instance"],
        "telemetry_sha256": monitor["telemetry_sha256"],
    }
    receipt = {
        "receipt_schema_version": 3,
        "receipt_kind": "otr-side-production-measurement",
        "measured": "otr-side production lane",
        "recipe": run["name"],
        "run_number": 1,
        "run_count": 1,
        "engine": run["engine"],
        "model": run["model"],
        "profile_reference": run["profile"],
        "profile_applied": False,
        "profile_note": "Single-clip probe has no --profile; profile names identify equivalent production engine defaults only.",
        "take": run["take"],
        "status": "MEASURED OTR-SIDE; NOT LAB-GATED; PENDING_HUMAN",
        "valid_measurement": True,
        "lab_gate_evaluated": False,
        "gate_pass": None,
        "pass": None,
        "warm_pass": None,
        "marginal": None,
        "promotion_ready": False,
        "certification_scope": "measurement-only",
        "requires_human_eyeball": True,
        "human_verdicts": {"lips": "PENDING_HUMAN", "onset": "PENDING_HUMAN", "identity": "PENDING_HUMAN"},
        "seed_control_exposed": False,
        "seed_requested": None,
        "seed_effective": 7,
        "seed_evidence": "render_driver.build_request(single_0000) deterministically derives request_seed=7",
        "cache_buster": int(telemetry["command_contract"]["cache_buster"]),
        "boot_lane": telemetry["boot_lane"],
        "boot_argv": [
            str(OTR / "scripts" / "_otr_soak_server_launch.cmd"),
            "<server-log>", "HUMO",
        ],
        "server_argv": telemetry["server_instance"]["argv"],
        "server_instance": telemetry["server_instance"],
        "render_argv": telemetry["command"],
        "render_route": "_otr_single_engine_smoke.py -> OTR_VideoRenderBatch(mode=single) -> production HuMo wrapper",
        "route_fingerprints": identity["route_fingerprints"],
        "fixture_sha256s": {"portrait.png": PORTRAIT_SHA, "tts_dialogue.wav": TTS_SHA},
        "fixture_contract": fixture_contract(),
        "monitor": monitor,
        "baseline_vram_gb": float(telemetry["baseline_vram_gib"]),
        "peak_vram_gb": float(telemetry["sampler"]["peak_vram_gib"]),
        "baseline_host_ram_gb": float(telemetry["baseline_host_ram_gib"]),
        "peak_host_ram_gb": float(telemetry["sampler"]["peak_host_ram_gib"]),
        "duration_s": duration_s,
        "duration_definition": "sidecar start through durable native artifact save",
        "command_duration_s": float(telemetry["command_duration_s"]),
        "engine_report_elapsed_s": engine_elapsed,
        "engine_report_path": (f"results/otr_side/source_reports/{run['source_report']}" if run["source_report"] else None),
        "engine_report_sha256": source_report_hash,
        "engine_report_preservation": ("preserved" if source_report else "overwritten by required take 2; not load-bearing"),
        "encoded_width": int(review_video["width"]),
        "encoded_height": int(review_video["height"]),
        "encoded_frame_count": int(review_video["nb_frames"]),
        "encoded_fps": run["fps"],
        "video_duration_s": output_duration_s,
        "audio_duration_s": float(review_audio["duration"]),
        "container_duration_s": float(review_probe["format"]["duration"]),
        "video_codec": review_video["codec_name"],
        "audio_codec": review_audio["codec_name"],
        "audio_sample_rate": int(review_audio["sample_rate"]),
        "audio_channels": int(review_audio["channels"]),
        "output_path": run["review"],
        "artifact_bytes": review.stat().st_size,
        "artifact_sha256": sha256_file(review),
        "native_silent_output_path": run["native"],
        "native_silent_artifact_bytes": native.stat().st_size,
        "native_silent_artifact_sha256": sha256_file(native),
        "native_and_review_video_stream_sha256": stream_hash(native, "0:v:0"),
        "review_audio_policy": "Exact tts_dialogue.wav muxed at t=0; native video stream copied without re-encode.",
        "render_seconds_per_output_second": duration_s / output_duration_s,
        "failed_preflight_attempt": failed_preflight,
        "otr_git_head": OTR_HEAD,
        "otr_git_dirty_at_entry": True,
        "otr_git_unchanged_relative_to_entry": True,
        "otr_worktree_integrity_receipt": "results/otr_side/otr_worktree_integrity.json",
        "otr_worktree_integrity_receipt_sha256": worktree_sha,
        "run_identity_sha256": canonical_sha(identity),
        "timestamp": telemetry["finished_at_utc"],
    }
    return receipt


def build_comparison(receipts: list[dict[str, Any]], receipt_hashes: dict[str, str], worktree_sha: str) -> dict[str, Any]:
    h3_specs = [
        ("h3_seed42", ROOT / "results" / "h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json"),
        ("h3_seed43", ROOT / "results" / "h3_r2v_refaudio_tts_lipsync_exact_seed43_run1.json"),
    ]
    entries: list[dict[str, Any]] = []
    for receipt in receipts:
        entries.append({
            "category": receipt["model"],
            "receipt": f"results/otr_side/{receipt['recipe']}.json",
            "receipt_sha256": receipt_hashes[receipt["recipe"]],
            "artifact": f"outputs/{receipt['output_path']}",
            "artifact_sha256": receipt["artifact_sha256"],
            "seed": receipt["seed_effective"],
            "duration_s": receipt["video_duration_s"],
            "wall_s": receipt["duration_s"],
            "render_seconds_per_output_second": receipt["render_seconds_per_output_second"],
            "peak_vram_gb": receipt["peak_vram_gb"],
            "peak_host_ram_gb": receipt["peak_host_ram_gb"],
            "verdicts": receipt["human_verdicts"],
        })
    for label, path in h3_specs:
        h3 = read_json(path)
        entries.append({
            "category": "H3 Ref2VA",
            "label": label,
            "receipt": path.relative_to(ROOT).as_posix(),
            "receipt_sha256": sha256_file(path),
            "artifact": f"outputs/{h3['output_path']}",
            "artifact_sha256": h3["artifact_sha256"],
            "seed": 42 if label.endswith("42") else 43,
            "duration_s": h3["video_duration_s"],
            "wall_s": h3["duration_s"],
            "render_seconds_per_output_second": h3["duration_s"] / h3["video_duration_s"],
            "peak_vram_gb": h3["peak_vram_gb"],
            "peak_host_ram_gb": h3["peak_host_ram_gb"],
            "verdicts": {"lips": "PENDING_HUMAN", "onset": "PENDING_HUMAN", "identity": "PENDING_HUMAN"},
        })
    return {
        "receipt_schema_version": 1,
        "receipt_kind": "character-lane-bakeoff-package",
        "status": "MEASUREMENT COVERAGE COMPLETE; CASTING PENDING_HUMAN",
        "measurement_category_count": 4,
        "review_clip_count": 5,
        "fixture_sha256s": {"portrait.png": PORTRAIT_SHA, "tts_dialogue.wav": TTS_SHA},
        "fixture_parity": True,
        "workload_duration_parity": False,
        "workload_note": "Raw TTS is 10.000s; H3 delivers 5.167s, HuMo 1.7B 5.160s, HuMo 14B 3.880s.",
        "entries": entries,
        "human_decision": {"lips": "PENDING_HUMAN", "onset": "PENDING_HUMAN", "identity": "PENDING_HUMAN"},
        "otr_worktree_integrity_receipt_sha256": worktree_sha,
    }


def encoded_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write_if_changed(path: Path, payload: dict[str, Any]) -> None:
    raw = encoded_json(payload)
    if path.exists() and path.read_bytes() == raw:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def build_documents(write: bool = True) -> dict[str, dict[str, Any]]:
    worktree = build_worktree_receipt()
    if write:
        write_if_changed(RESULTS / "otr_worktree_integrity.json", worktree)
    worktree_sha = hashlib.sha256(encoded_json(worktree)).hexdigest()
    receipts = [build_run_receipt(run, worktree_sha) for run in RUNS]
    docs = {receipt["recipe"]: receipt for receipt in receipts}
    if write:
        for name, payload in docs.items():
            write_if_changed(RESULTS / f"{name}.json", payload)
    hashes = {name: hashlib.sha256(encoded_json(payload)).hexdigest() for name, payload in docs.items()}
    comparison = build_comparison(receipts, hashes, worktree_sha)
    docs["humo_character_lane_bakeoff"] = comparison
    docs["otr_worktree_integrity"] = worktree
    if write:
        write_if_changed(RESULTS / "humo_character_lane_bakeoff.json", comparison)
    return docs


def main() -> int:
    docs = build_documents(write=True)
    for name, payload in docs.items():
        print(f"{name}: {hashlib.sha256(encoded_json(payload)).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
