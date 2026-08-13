#!/usr/bin/env python
"""Reduce immutable WAN-retention telemetry into compact, auditable receipts.

This script is deliberately offline.  It does not query or boot a server, take
the GPU lease, or mutate the OTR repository.  A leg is emitted only when the
raw 200 ms sidecar, fixture bundle, event stream, and expected shot topology
all validate independently.  Invalid attempts remain visible in the
comparison audit but can never become a measured leg receipt.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OTR_ROOT = Path(r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio")
COMFY_MANAGER_ROOT = Path(r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-Manager")
OTR_EPISODES_ROOT = Path(r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes")
TELEMETRY_DIR = Path("results/otr_side/wan_retention/telemetry")
OUTPUT_DIR = Path("results/otr_side/wan_retention")
COMPARISON_OUTPUT = OUTPUT_DIR / "comparison.json"
HISTORICAL_LOG = OTR_ROOT / "tmp" / "chip4_boot.log"
RAW_SIDECAR_PATH = ROOT / "scratch" / "wan_retention_sidecar.py"
LEGACY_RAW_SIDECAR_ARCHIVE = OUTPUT_DIR / "evidence/wan_retention_sidecar_phase1_phase4_v1.py"
LEGACY_RAW_SIDECAR_SHA256 = "b98fac3468ef6c805df5ab9bb341b42b475802cc8772d3a4b6f552955b5bcaec"
COMFY_REGISTRY_SOURCE_OBJECT = "491f847bbc286588175695ea43fa4e13cd14a437:glob/cnr_utils.py"
COMFY_REGISTRY_SOURCE_SHA256 = "4a378c111dccacd2bc4c4082c8b7aae248859259a6b29596173f03e1eb3306f6"

RAW_KIND = "wan-inter-shot-retention-raw-telemetry"
MEASUREMENT_SCOPE = "otr-side production wrapper"
EXPECTED_INTERVAL_S = 0.2
MAX_GAP_S = 0.75
POST_TERMINAL_MIN_S = 12.0
EXPECTED_PORT = 8000
EXPECTED_HOST = "127.0.0.1"

LONG_SHOT_ID = "shot_b001"
SMALL_SHOT_ID = "shot_b003"
LONG_TARGET = 200
SMALL_TARGET = 65
LONG_SEGMENTS = (
    {"index": 0, "render_frames": 177, "drop_head": 0, "trim_tail": 0},
    {"index": 1, "render_frames": 25, "drop_head": 1, "trim_tail": 1},
)
SMALL_SEGMENTS = (
    {"index": 0, "render_frames": 65, "drop_head": 0, "trim_tail": 0},
)
LTX_LONG_SEGMENTS = (
    {"index": 0, "render_frames": 169, "drop_head": 0, "trim_tail": 0},
    {"index": 1, "render_frames": 169, "drop_head": 1, "trim_tail": 137},
)
LTX_SMALL_SEGMENTS = (
    {"index": 0, "render_frames": 169, "drop_head": 0, "trim_tail": 104},
)

REQUIRED_LEGS = {
    "phase1_wan_ti2v_long_first": {
        "engine": "wan_ti2v",
        "order": "long_then_small",
        "output": OUTPUT_DIR / "phase1_wan_ti2v_long_first.json",
    },
    "phase3_fastwan_8gb_long_first": {
        "engine": "fastwan_8gb",
        "order": "long_then_small",
        "output": OUTPUT_DIR / "phase3_fastwan_8gb_long_first.json",
    },
    "phase3_ltx_video_long_first": {
        "engine": "ltx_video",
        "order": "long_then_small",
        "output": OUTPUT_DIR / "phase3_ltx_video_long_first.json",
    },
    "phase4_wan_ti2v_small_first": {
        "engine": "wan_ti2v",
        "order": "small_then_long",
        "output": OUTPUT_DIR / "phase4_wan_ti2v_small_first.json",
    },
}

OTR_SOURCE_PATHS = (
    "scripts/otr_visual_smoke.py",
    "nodes/otr_video_render_batch.py",
    "nodes/_otr_video_engines/render_driver.py",
    "nodes/_otr_video_engines/motion_common.py",
    "nodes/_otr_video_engines/coverage_plan.py",
    "nodes/_otr_video_engines/beat_session.py",
    "nodes/_otr_video_engines/eng_wan_ti2v.py",
    "nodes/_otr_video_engines/eng_fastwan_8gb.py",
    "nodes/_otr_video_engines/eng_ltx_video.py",
)

PEAK_RE = re.compile(
    r"\[OTR video\]\s+(?P<engine>[a-zA-Z0-9_]+) VRAM render-phase peak "
    r"(?P<peak>\d+) MB / post (?P<post>\d+) MB"
)
ASSEMBLY_RE = re.compile(
    r"\[OTR video\] BEAT (?P<shot>\S+) assembled from (?P<segments>\d+) "
    r"chain segment\(s\) -> (?P<frames>\d+) frame\(s\)"
)
REFUSAL_RE = re.compile(
    r"render FAILED \(no fallback\) shot (?P<shot>\S+) engine (?P<engine>[a-zA-Z0-9_]+): "
    r"MotionBudgetError: engine (?P=engine): static frame budget (?P<budget>\d+) "
    r"\(snapped (?P<snapped>\d+)\) exceeds the cost-model's affordable "
    r"(?P<affordable>\d+) frames \(free=(?P<free>\d+) MB, margin=(?P<margin>[0-9.]+)\)\. "
    r"NO silent resize"
)
FASTWAN_MARKER_RE = re.compile(r"\[OTR_DMDRestart\] marker=(?P<marker>[0-9a-f]+)")
LTX_I2V_RE = re.compile(
    r"\[eng_ltx_video\] LTX-I2V: conditioning on init image (?P<image>\S+) "
    r"\((?P<width>\d+)x(?P<height>\d+), length (?P<length>\d+)\)"
)
LTX_HQ_RE = re.compile(
    r"\[eng_ltx_video\] S5 HQ two-stage: base (?P<base_width>\d+)x(?P<base_height>\d+) "
    r"-> upsample x2 -> refine (?P<width>\d+)x(?P<height>\d+), length (?P<length>\d+), "
    r"init (?P<image>\S+) \(silent; recipe=(?P<recipe>[a-z0-9_]+)\)"
)
SMALL_ASSEMBLY_RE = re.compile(
    r"\[OTR video\] BEAT shot_b003 assembled from 1 single segment\(s\) -> 65 frame\(s\)"
)
NETWORK_URL_RE = re.compile(r"https://[^\s\x1b]+")
COMFY_REGISTRY_FETCH_RE = re.compile(
    r"FETCH ComfyRegistry Data(?::\s*\d+/\d+|\s*\[DONE\])"
)

ARTIFACT_SPECS = {
    "phase4_wan_ti2v_small_first": (
        {
            "path": "outputs/otr_side/wan_retention/phase4_wan_small65.mp4",
            "sha256": "538c15b04dd63a27e1dcbd85bfe3b0fcaf09a6d27fff96e06d73c41b39c13e45",
            "bytes": 680309,
            "frames": 65,
            "width": 832,
            "height": 480,
            "production_source_path": (
                "C:/Users/jeffr/Documents/ComfyUI/output/otr/episodes/"
                "wan_retention_wan_small_first_planned_20260809/clips/"
                "shot_b003_character_video_wan_ti2v.mp4"
            ),
            "production_source_mtime_ns": 1786306680400299500,
        },
        {
            "path": "outputs/otr_side/wan_retention/phase4_wan_long200.mp4",
            "sha256": "ebd227ceaafeb698ef83a2365d07a348e9f776324d20589dcd26b1457fca2aed",
            "bytes": 885221,
            "frames": 200,
            "width": 832,
            "height": 480,
            "production_source_path": (
                "C:/Users/jeffr/Documents/ComfyUI/output/otr/episodes/"
                "wan_retention_wan_small_first_planned_20260809/clips/"
                "shot_b001_announcer_visual_wan_ti2v.mp4"
            ),
            "production_source_mtime_ns": 1786307181794219600,
        },
    ),
    "phase3_ltx_video_long_first": (
        {
            "path": "outputs/otr_side/wan_retention/phase3_ltx_long200.mp4",
            "sha256": "7f4b7f66db9b091cb9d715ad60688d360bb7825844da6e61146b2ba944ed3fdd",
            "bytes": 956729,
            "frames": 200,
            "width": 832,
            "height": 448,
            "production_source_path": (
                "C:/Users/jeffr/Documents/ComfyUI/output/otr/episodes/"
                "wan_retention_ltx_video_long_first_planned_20260809/clips/"
                "shot_b001_announcer_visual_ltx_video.mp4"
            ),
            "production_source_mtime_ns": 1786307839724089200,
        },
        {
            "path": "outputs/otr_side/wan_retention/phase3_ltx_small65.mp4",
            "sha256": "38b287496beb001e2c595bc5fc125df02ceac97f756e20fe3581a88e1708099b",
            "bytes": 284666,
            "frames": 65,
            "width": 832,
            "height": 448,
            "production_source_path": (
                "C:/Users/jeffr/Documents/ComfyUI/output/otr/episodes/"
                "wan_retention_ltx_video_long_first_planned_20260809/clips/"
                "shot_b003_character_video_ltx_video.mp4"
            ),
            "production_source_mtime_ns": 1786307933750192200,
        },
    ),
}


class EvidenceError(RuntimeError):
    """Evidence failed a load-bearing validation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def engine_plans(engine: str) -> tuple[tuple[dict[str, int], ...], tuple[dict[str, int], ...]]:
    if engine in {"wan_ti2v", "fastwan_8gb"}:
        return LONG_SEGMENTS, SMALL_SEGMENTS
    if engine == "ltx_video":
        return LTX_LONG_SEGMENTS, LTX_SMALL_SEGMENTS
    raise EvidenceError(f"unsupported retention engine: {engine}")


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(not raw.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid UTF-8 JSON {path}: {exc}") from exc
    require(isinstance(payload, dict), f"expected JSON object: {path}")
    return payload


def source_ref(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    path = path.resolve()
    display = (
        path.relative_to(root.resolve()).as_posix()
        if root is not None and path.is_relative_to(root.resolve())
        else str(path)
    )
    return {"path": display, "sha256": sha256_file(path), "bytes": path.stat().st_size}


def ffprobe_artifact(root: Path, spec: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Bind a durable successful artifact and independently verify its media shape."""

    artifact_path = root / spec["path"]
    require(artifact_path.is_file(), f"durable output artifact missing: {artifact_path}")
    ref = source_ref(artifact_path, root=root)
    require(ref["sha256"] == spec["sha256"], f"artifact SHA drift: {artifact_path}")
    require(ref["bytes"] == spec["bytes"], f"artifact byte-size drift: {artifact_path}")
    production_source = Path(spec["production_source_path"]).resolve()
    require(production_source.is_file(), f"production source artifact missing: {production_source}")
    require(
        production_source.is_relative_to(OTR_EPISODES_ROOT.resolve()),
        f"production source artifact escapes OTR episode output: {production_source}",
    )
    source_ref_payload = source_ref(production_source)
    require(
        source_ref_payload["sha256"] == ref["sha256"],
        f"production source/lab artifact SHA mismatch: {production_source}",
    )
    require(
        source_ref_payload["bytes"] == ref["bytes"],
        f"production source/lab artifact byte-size mismatch: {production_source}",
    )
    source_mtime_ns = production_source.stat().st_mtime_ns
    require(
        source_mtime_ns == int(spec["production_source_mtime_ns"]),
        f"production source artifact mtime drift: {production_source}",
    )
    raw_window = [int(raw["started_at_ns"]), int(raw["child_finished_at_ns"])]
    require(
        raw_window[0] <= source_mtime_ns <= raw_window[1],
        f"production source artifact mtime is outside the raw child window: {production_source}",
    )
    ffprobe = shutil.which("ffprobe")
    require(ffprobe is not None, "ffprobe is required to validate durable output artifacts")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            (
                "format=duration,size:stream=index,codec_type,codec_name,pix_fmt,"
                "width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames,duration"
            ),
            "-of",
            "json",
            str(artifact_path),
        ],
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"ffprobe failed for {artifact_path}")
    try:
        probe = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid ffprobe JSON for {artifact_path}: {exc}") from exc
    streams = probe.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    require(len(video_streams) == 1, f"artifact must contain exactly one video stream: {artifact_path}")
    require(not audio_streams, f"diagnostic artifact unexpectedly contains audio: {artifact_path}")
    video = video_streams[0]
    expected_frames = int(spec["frames"])
    expected_duration_s = expected_frames / 25.0
    require(video.get("codec_name") == "h264", f"artifact codec drift: {artifact_path}")
    require(video.get("pix_fmt") == "yuv420p", f"artifact pixel-format drift: {artifact_path}")
    require(video.get("r_frame_rate") == "25/1", f"artifact frame-rate drift: {artifact_path}")
    require(video.get("avg_frame_rate") == "25/1", f"artifact average frame-rate drift: {artifact_path}")
    require(int(video["width"]) == int(spec["width"]), f"artifact width drift: {artifact_path}")
    require(int(video["height"]) == int(spec["height"]), f"artifact height drift: {artifact_path}")
    require(int(video["nb_frames"]) == expected_frames, f"artifact frame-count drift: {artifact_path}")
    require(int(video["nb_read_frames"]) == expected_frames, f"decoded artifact frame-count drift: {artifact_path}")
    require(
        abs(float(video["duration"]) - expected_duration_s) <= 1 / 25,
        f"artifact stream duration exceeds one-frame tolerance: {artifact_path}",
    )
    require(
        abs(float(probe["format"]["duration"]) - expected_duration_s) <= 1 / 25,
        f"artifact container duration exceeds one-frame tolerance: {artifact_path}",
    )
    require(int(probe["format"]["size"]) == spec["bytes"], f"ffprobe size drift: {artifact_path}")
    return {
        **ref,
        "codec": video["codec_name"],
        "pixel_format": video["pix_fmt"],
        "width": int(video["width"]),
        "height": int(video["height"]),
        "frame_rate": video["r_frame_rate"],
        "frame_count": expected_frames,
        "duration_s": round(float(probe["format"]["duration"]), 6),
        "audio_stream_count": 0,
        "validation": "SHA256_BYTES_AND_FFPROBE_EXACT_SHAPE",
        "production_source": {
            **source_ref_payload,
            "mtime_ns": source_mtime_ns,
            "raw_child_window_ns": raw_window,
            "mtime_within_raw_child_window": True,
            "source_matches_lab_copy": True,
        },
    }


def validate_artifacts(
    root: Path, leg_id: str, observed_outcome: str, raw: dict[str, Any]
) -> dict[str, Any]:
    specs = ARTIFACT_SPECS.get(leg_id)
    if observed_outcome == "success":
        require(specs is not None, f"successful leg has no durable artifact contract: {leg_id}")
        artifacts = [ffprobe_artifact(root, spec, raw) for spec in specs]
        require(
            sorted(artifact["frame_count"] for artifact in artifacts) == [SMALL_TARGET, LONG_TARGET],
            f"successful leg does not bind exact 65/200 artifacts: {leg_id}",
        )
        return {
            "status": "DURABLE_SUCCESS_ARTIFACTS_BOUND",
            "artifacts": artifacts,
            "caveat": "Artifacts prove delivered media shape and bytes; they do not add a visual-quality gate.",
        }
    require(specs is None, f"refused leg must not claim durable successful artifacts: {leg_id}")
    return {
        "status": "NO_DURABLE_CLIP_BY_DESIGN",
        "artifacts": [],
        "caveat": "The production wrapper refused the follow-on shot, so no complete diagnostic artifact set exists.",
    }


def matching_events(events: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
    return [event for event in events if pattern in str(event.get("text", ""))]


def validate_encoded_events(
    events: list[dict[str, Any]], *, offsets: bool, stream_name: str
) -> bytes:
    require(events, f"{stream_name} event stream is empty")
    assembled = bytearray()
    prior_end: int | None = None
    prior_observed_ns = -1
    for index, event in enumerate(events):
        try:
            raw = base64.b64decode(event["raw_base64"], validate=True)
        except Exception as exc:
            raise EvidenceError(f"{stream_name} event {index} has invalid base64: {exc}") from exc
        require(len(raw) == int(event["byte_count"]), f"{stream_name} event {index} byte count drift")
        require(sha256_bytes(raw) == event["raw_sha256"], f"{stream_name} event {index} SHA drift")
        decoded = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        require(decoded == event["text"], f"{stream_name} event {index} text/raw mismatch")
        observed_ns = int(event["observed_at_ns"])
        require(observed_ns >= prior_observed_ns, f"{stream_name} observation times regressed")
        prior_observed_ns = observed_ns
        if offsets:
            start = int(event["start_offset"])
            end = int(event["end_offset"])
            require(end - start == len(raw), f"{stream_name} event {index} offset width drift")
            if prior_end is not None:
                require(start == prior_end, f"{stream_name} event offsets are not contiguous")
            prior_end = end
        assembled.extend(raw)
    return bytes(assembled)


def validate_sampler(raw: dict[str, Any]) -> list[dict[str, Any]]:
    sampler = raw["sampler"]
    samples = list(sampler["samples"])
    require(float(sampler["interval_s"]) == EXPECTED_INTERVAL_S, "sampler is not 200 ms")
    require(not sampler["coverage_errors"], "sampler reports coverage errors")
    require(int(sampler["sample_error_count"]) == 0, "sampler reports sample errors")
    require(not sampler["sample_errors"], "sampler retained sample errors")
    require(len(samples) == int(sampler["sample_count"]), "sample count drift")
    require(len(samples) >= 2, "too few telemetry samples")
    times = [int(sample["sampled_at_ns"]) for sample in samples]
    monotonic_times = [int(sample["sampled_monotonic_ns"]) for sample in samples]
    require(times == sorted(times) and len(set(times)) == len(times), "sample times are not strict")
    require(
        monotonic_times == sorted(monotonic_times)
        and len(set(monotonic_times)) == len(monotonic_times),
        "sample monotonic times are not strict",
    )
    gaps_s = [
        (b - a) / 1_000_000_000.0
        for a, b in zip(monotonic_times, monotonic_times[1:])
    ]
    actual_max_gap = max(gaps_s)
    require(actual_max_gap <= MAX_GAP_S, f"telemetry gap {actual_max_gap:.3f}s exceeds {MAX_GAP_S}s")
    require(
        abs(float(sampler["max_inter_sample_gap_s"]) - round(actual_max_gap, 3)) <= 0.002,
        "reported maximum telemetry gap is not reproducible",
    )
    require(float(sampler["maximum_allowed_gap_s"]) == MAX_GAP_S, "sidecar gap gate drift")
    require(int(sampler["baseline_vram_mib"]) == int(raw["baseline"]["vram_used_mib"]), "baseline drift")
    require(
        abs(float(samples[0]["vram_used_mib"]) - float(sampler["baseline_vram_mib"])) <= 128.0,
        "first 200 ms sample diverged materially from the separately sampled baseline",
    )
    peak_vram = max(float(sample["vram_used_mib"]) for sample in samples)
    peak_host = max(int(sample["host_ram_used_bytes"]) for sample in samples)
    require(peak_vram == float(sampler["peak_vram_mib"]), "VRAM peak is not reproducible")
    require(peak_host == int(sampler["peak_host_ram_bytes"]), "host RAM peak is not reproducible")
    require(float(raw["post_terminal_settle_s"]) >= POST_TERMINAL_MIN_S, "post-terminal settle is too short")
    require(times[0] >= int(raw["started_at_ns"]), "first sample precedes sidecar start")
    require(times[-1] >= int(raw["child_finished_at_ns"]), "samples do not cover child terminal")
    require(times[-1] <= int(raw["telemetry_finished_at_ns"]), "sample follows telemetry finish")
    return samples


def sample_payload(sample: dict[str, Any]) -> dict[str, Any]:
    vram_mib = float(sample["vram_used_mib"])
    host_bytes = int(sample["host_ram_used_bytes"])
    return {
        "sampled_at_ns": int(sample["sampled_at_ns"]),
        "sampled_at_utc": sample["sampled_at_utc"],
        "vram_used_mib": vram_mib,
        "vram_used_gib": round(vram_mib / 1024.0, 6),
        "host_ram_used_bytes": host_bytes,
        "host_ram_used_gib": round(host_bytes / (1024.0**3), 6),
    }


def sample_at_or_before(samples: list[dict[str, Any]], when_ns: int, *, strict: bool = False) -> dict[str, Any]:
    candidates = [
        sample
        for sample in samples
        if int(sample["sampled_at_ns"]) < when_ns
        or (not strict and int(sample["sampled_at_ns"]) == when_ns)
    ]
    require(candidates, f"no telemetry sample before boundary {when_ns}")
    return sample_payload(candidates[-1])


def sample_at_or_after(samples: list[dict[str, Any]], when_ns: int) -> dict[str, Any]:
    candidates = [sample for sample in samples if int(sample["sampled_at_ns"]) >= when_ns]
    require(candidates, f"no telemetry sample after boundary {when_ns}")
    return sample_payload(candidates[0])


def interval_stats(samples: list[dict[str, Any]], start_ns: int, end_ns: int) -> dict[str, Any]:
    selected = [
        sample for sample in samples if start_ns <= int(sample["sampled_at_ns"]) <= end_ns
    ]
    require(selected, f"no telemetry samples in interval {start_ns}..{end_ns}")
    peak_vram = max(selected, key=lambda sample: float(sample["vram_used_mib"]))
    peak_host = max(selected, key=lambda sample: int(sample["host_ram_used_bytes"]))
    return {
        "start_observed_at_ns": start_ns,
        "end_observed_at_ns": end_ns,
        "observation_span_s": round((end_ns - start_ns) / 1_000_000_000.0, 6),
        "sample_count": len(selected),
        "peak_vram": sample_payload(peak_vram),
        "peak_host_ram": sample_payload(peak_host),
    }


def validate_bundle(
    raw: dict[str, Any], *, root: Path = ROOT,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    command = raw["command"]
    bundle = Path(command["bundle"])
    durable_dir = root / OUTPUT_DIR / "fixture_evidence" / bundle.name
    evidence_dir = durable_dir if durable_dir.is_dir() else bundle
    require(evidence_dir.is_dir(), f"fixture evidence missing: {evidence_dir}")
    contract_path = evidence_dir / "fixture_contract.json"
    manifest_path = evidence_dir / "bundle_manifest.json"
    ledger_path = evidence_dir / "baked_ledger.json"
    contract = read_json(contract_path)
    manifest = read_json(manifest_path)
    ledger = read_json(ledger_path)

    parsed_refs = {
        "fixture_contract": source_ref(contract_path, root=root),
        "bundle_manifest": source_ref(manifest_path, root=root),
        "baked_ledger": source_ref(ledger_path, root=root),
    }
    require(parsed_refs["fixture_contract"]["sha256"] == command["fixture_contract_sha256"], "contract SHA drift")
    require(parsed_refs["bundle_manifest"]["sha256"] == command["bundle_manifest_sha256"], "manifest SHA drift")
    require(parsed_refs["baked_ledger"]["sha256"] == command["baked_ledger_sha256"], "ledger SHA drift")
    require(manifest["missing"] == [], "bundle manifest reports missing assets")
    require(manifest["wan_retention_measurement_contract"] == contract, "manifest contract copy drift")
    require(Path(manifest["baked_ledger"]).resolve() == (bundle / "baked_ledger.json").resolve(), "manifest ledger path drift")
    require(Path(manifest["baked_master"]).resolve() == (bundle / "master.wav").resolve(), "manifest master path drift")
    require(manifest["master"]["sha256"] == command["master_audio_sha256"], "manifest master hash drift")
    for asset in manifest["assets"].values():
        require(re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]) is not None, "manifest asset SHA malformed")
        require(Path(asset["bundle"]).parent.name == "assets", "manifest asset bundle path drift")

    purpose = contract["purpose"]
    measurement_meta = ledger["meta"]["wan_retention_measurement"]
    if purpose == "wan_ti2v inter-shot VRAM retention measurement only":
        contract_class = "phase1_or_phase4_wan_reconstruction"
        targets = contract["target_frames"]
        require(contract["existing_otr_harness_sha256"] == command["otr_harness_sha256"], "harness contract drift")
        require(contract["resolved_master_sha256"] == command["master_audio_sha256"], "resolved master drift")
        require(measurement_meta["kind"] == "derived-node92-shape-fixture", "ledger fixture tag missing")
        engine_binding_label = measurement_meta["engine_variable"]
        require(
            engine_binding_label
            in {"OTR_FORCE_ENGINE_MAP", "baked_ledger.video.shots[].engine_id"},
            "engine-binding contract drift",
        )
        if engine_binding_label == "baked_ledger.video.shots[].engine_id":
            require(contract.get("engine_binding") == engine_binding_label, "ledger engine-binding contract drift")
        elif "engine_authority" in measurement_meta:
            require(
                measurement_meta["engine_authority"] == "baked_ledger.video.shots[].engine_id",
                "legacy fixture engine authority drift",
            )
            require(
                measurement_meta.get("engine_variable_status")
                == "LEGACY_INCORRECT_DECLARATIVE_LABEL_NOT_ENGINE_AUTHORITY",
                "legacy fixture engine-variable status drift",
            )
        source_capture_sha256 = contract["source_capture_sha256"]
        control_origin_ledger_sha256 = parsed_refs["baked_ledger"]["sha256"]
        comparison_scope = "exact WAN problem reconstruction"
    elif purpose == "Phase-3 engine-only inter-shot retention comparison":
        contract_class = "phase3_cross_engine_neutral_diagnostic"
        targets = contract["targets"]
        require(contract["comparison_scope"] == "neutral production-tail diagnostic, not shipping-profile qualification", "Phase-3 scope drift")
        require(contract["engine"] == raw["engine"], "Phase-3 contract engine drift")
        require(contract["engine_binding"] == "baked_ledger.video.shots[].engine_id", "Phase-3 engine binding drift")
        require(contract["source_sha256s"]["otr_visual_smoke.py"] == command["otr_harness_sha256"], "Phase-3 harness contract drift")
        require(contract["source_master_sha256"] == command["master_audio_sha256"], "Phase-3 source master drift")
        require(measurement_meta["kind"] == "engine-only-derived-node92-shape-fixture", "Phase-3 ledger fixture tag missing")
        require(measurement_meta["engine_variable"] == "baked_ledger.video.shots[].engine_id", "Phase-3 ledger engine binding drift")
        require(measurement_meta["selected_engine"] == raw["engine"], "Phase-3 selected engine drift")
        source_bundle = root / OUTPUT_DIR / "fixture_evidence" / "long_first_planned"
        source_ledger = source_bundle / "baked_ledger.json"
        source_contract = read_json(source_bundle / "fixture_contract.json")
        require(source_ledger.is_file(), "Phase-3 source ledger is missing")
        require(sha256_file(source_ledger) == contract["source_ledger_sha256"], "Phase-3 source ledger SHA drift")
        source_capture_sha256 = source_contract["source_capture_sha256"]
        control_origin_ledger_sha256 = contract["source_ledger_sha256"]
        comparison_scope = contract["comparison_scope"]
    else:
        raise EvidenceError(f"unsupported fixture purpose: {purpose}")

    shots = ledger["video"]["shots"]
    require(len(shots) == 2, f"expected two diagnostic shots, found {len(shots)}")
    by_id = {shot["shot_id"]: shot for shot in shots}
    require(set(by_id) == {LONG_SHOT_ID, SMALL_SHOT_ID}, "diagnostic shot IDs drift")
    long_shot = by_id[LONG_SHOT_ID]
    small_shot = by_id[SMALL_SHOT_ID]
    expected_long_segments, expected_small_segments = engine_plans(raw["engine"])
    require(
        {shot["engine_id"] for shot in shots} == {raw["engine"]},
        "raw engine is not bound by both ledger shot engine_id fields",
    )
    require(int(long_shot["target_frame_count"]) == LONG_TARGET, "long target drift")
    require(int(small_shot["target_frame_count"]) == SMALL_TARGET, "small target drift")
    require(
        "coverage_plan" in long_shot and "coverage_plan" in small_shot,
        "fixture lacks the exact historical coverage plans; pre-render refusal attempt is not a retention reproduction",
    )
    require(long_shot["coverage_plan"]["join_mode"] == "chain", "long shot is not chained")
    require(
        long_shot["coverage_plan"]["segments"] == list(expected_long_segments),
        f"{raw['engine']} long coverage plan drift",
    )
    require(small_shot["coverage_plan"]["join_mode"] == "single", "small shot is not single")
    require(
        small_shot["coverage_plan"]["segments"] == list(expected_small_segments),
        f"{raw['engine']} small coverage plan drift",
    )

    order = contract["order"]
    if order == "long_then_small":
        expected_ids = [LONG_SHOT_ID, SMALL_SHOT_ID]
        expected_targets = [LONG_TARGET, SMALL_TARGET]
    elif order == "small_then_long":
        expected_ids = [SMALL_SHOT_ID, LONG_SHOT_ID]
        expected_targets = [SMALL_TARGET, LONG_TARGET]
    else:
        raise EvidenceError(f"unsupported fixture order: {order}")
    require([shot["shot_id"] for shot in shots] == expected_ids, "ledger shot order drift")
    require(targets == expected_targets, "contract target order drift")
    require(ledger["meta"]["wan_retention_measurement"]["target_frames"] == expected_targets, "ledger target order drift")
    require(ledger["meta"]["wan_retention_measurement"]["order"] == order, "ledger order drift")
    if contract_class == "phase3_cross_engine_neutral_diagnostic":
        require(
            contract["coverage_plans"]
            == [long_shot["coverage_plan"], small_shot["coverage_plan"]],
            "Phase-3 contract/ledger coverage plan drift",
        )
    require(
        durable_dir.is_dir(),
        f"durable repo-local fixture evidence missing for otherwise valid bundle: {durable_dir}",
    )
    refs = {
        **parsed_refs,
        "master_audio": {
            "path": None,
            "sha256": command["master_audio_sha256"],
            "bytes": None,
            "binding": "HASH_ONLY_FROM_DURABLE_BUNDLE_MANIFEST_AND_RAW_COMMAND",
        },
        "render_time_bundle_observation": {
            "path": str(bundle),
            "binding": "OBSERVED_PATH_ONLY_NOT_PRIMARY_DURABLE_EVIDENCE",
        },
    }
    normalized = {
        "contract_class": contract_class,
        "comparison_scope": comparison_scope,
        "order": order,
        "targets": targets,
        "otr_repo_head_at_build": contract["otr_repo_head_at_build"],
        "source_capture_sha256": source_capture_sha256,
        "control_origin_ledger_sha256": control_origin_ledger_sha256,
    }
    return contract, manifest, ledger, refs, normalized


def validate_command_and_server(raw: dict[str, Any]) -> None:
    command = raw["command"]
    engine = raw["engine"]
    require(command["engine"] == engine, "command/receipt engine drift")
    if raw.get("sidecar_source") is None:
        require(
            command.get("server_bound_force_map") == f"*={engine}",
            "legacy sidecar's declarative force-map label drifted",
        )
    else:
        require(command.get("engine_binding") == "baked_ledger.video.shots[].engine_id", "corrected sidecar engine binding drift")
        require(command.get("server_bound_force_map") is None, "corrected sidecar must not claim server environment proof")
    argv = command["argv"]
    require(len(argv) == 8, f"unexpected harness argv length: {len(argv)}")
    require(argv[1:4] == ["-u", command["otr_harness"], "replay"], "unexpected harness entrypoint")
    require(argv[4] == "--bundle" and argv[5] == command["bundle"], "bundle argv drift")
    require(argv[6] == "--timeout" and int(argv[7]) == int(command["timeout_s"]), "timeout argv drift")
    require(
        Path(command["otr_harness"]).name == "otr_visual_smoke.py",
        "unexpected OTR harness path",
    )
    require(Path(command["python"]).resolve() == Path(argv[0]).resolve(), "child Python argv drift")
    require(sha256_file(Path(command["python"])) == command["python_sha256"], "child Python SHA drift")

    server = raw["server_instance"]
    listeners = server["listeners"]
    require(
        listeners == [{"address": EXPECTED_HOST, "pid": server["serving_pid"], "port": EXPECTED_PORT}],
        "server listener identity drift",
    )
    server_argv = server["argv"]
    require("--port" in server_argv, "server argv has no port")
    port_index = server_argv.index("--port")
    require(int(server_argv[port_index + 1]) == EXPECTED_PORT, "server is not the OTR port-8000 lane")
    require("--output-directory" in server_argv, "server output-directory pin missing")
    require("--extra-model-paths-config" in server_argv, "server model-path pin missing")
    require("--disable-metadata" in server_argv, "server metadata lane drift")
    require(str(EXPECTED_PORT) not in {"8188", "8199"}, "internal port constant error")
    require(float(server["process_create_time"]) < int(raw["started_at_ns"]) / 1e9, "server was not alive before replay")


def validate_raw_envelope(raw: dict[str, Any]) -> list[dict[str, Any]]:
    require(raw["sidecar_schema_version"] == 1, "unsupported raw sidecar schema")
    require(raw["kind"] == RAW_KIND, "wrong telemetry kind")
    require(raw["measured"] == MEASUREMENT_SCOPE, "measurement scope drift")
    require(raw["status"] == "measured", "raw sidecar did not complete")
    require(not raw["errors"], "raw sidecar reports errors")
    require(raw["gpu_lease"]["release"]["success"] is True, "lab GPU lease was not released")
    manifest_before = raw["node_episode_manifest_before"]
    manifest_after = raw["node_episode_manifest_after"]
    report_before = raw["node_episode_report_before"]
    report_after = raw["node_episode_report_after"]
    for label, before, after in (
        ("production manifest", manifest_before, manifest_after),
        ("production report", report_before, report_after),
    ):
        require(before["path"] == after["path"], f"{label} path drift")
        require(before["device"] == after["device"] and before["inode"] == after["inode"], f"{label} file identity drift")
        if raw["observed_outcome"] == "success":
            require(after["exists"] is True and int(after["bytes"]) > 0, f"{label} success snapshot missing")
            require(after["sha256"] != before["sha256"], f"{label} did not advance on success")
            require(int(after["mtime_ns"]) > int(before["mtime_ns"]), f"{label} mtime did not advance")
        else:
            require(before == after, f"{label} changed on failed/refused replay")
    sidecar_source = raw.get("sidecar_source")
    if sidecar_source is not None:
        require(Path(sidecar_source["path"]).name == RAW_SIDECAR_PATH.name, "raw sidecar source path drift")
        require(re.fullmatch(r"[0-9a-f]{64}", sidecar_source["sha256"]) is not None, "raw sidecar source SHA malformed")
    validate_command_and_server(raw)

    log = raw["server_log"]
    require(log["timestamps_are_observation_times"] is True, "server-log clock semantics missing")
    require(not log["errors"], "server-log tail reports errors")
    log_bytes = validate_encoded_events(log["events"], offsets=True, stream_name="server-log")
    require(int(log["event_count"]) == len(log["events"]), "server-log event count drift")
    require(int(log["starting"]["bytes"]) == int(log["events"][0]["start_offset"]), "server-log starting offset drift")
    require(int(log["ending"]["bytes"]) == int(log["events"][-1]["end_offset"]), "server-log ending offset drift")
    require(int(log["new_byte_count"]) == len(log_bytes), "server-log new byte count drift")
    require(log["new_bytes_sha256"] == sha256_bytes(log_bytes), "server-log append SHA drift")

    stdout = raw["child_stdout"]
    require(stdout["timestamps_are_observation_times"] is True, "child stdout clock semantics missing")
    require(not stdout["errors"], "child stdout tail reports errors")
    validate_encoded_events(stdout["events"], offsets=False, stream_name="child-stdout")
    require(int(stdout["event_count"]) == len(stdout["events"]), "child stdout event count drift")
    return validate_sampler(raw)


def indexed_matches(events: list[dict[str, Any]], regex: re.Pattern[str]) -> list[tuple[int, dict[str, Any], re.Match[str]]]:
    matches = []
    for index, event in enumerate(events):
        match = regex.search(str(event.get("text", "")))
        if match:
            matches.append((index, event, match))
    return matches


def event_ref(index: int, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_index": index,
        "observed_at_ns": int(event["observed_at_ns"]),
        "observed_at_utc": event["observed_at_utc"],
        "log_offsets": [int(event["start_offset"]), int(event["end_offset"])],
        "raw_sha256": event["raw_sha256"],
    }


def validate_topology(raw: dict[str, Any], order: str) -> dict[str, Any]:
    events = raw["server_log"]["events"]
    peaks = indexed_matches(events, PEAK_RE)
    assemblies = indexed_matches(events, ASSEMBLY_RE)
    refusals = indexed_matches(events, REFUSAL_RE)
    leases = [(index, event) for index, event in enumerate(events) if "[gpu_residency] lease acquired" in event["text"]]
    prompt_completions = matching_events(events, "Prompt executed in")
    require(len(prompt_completions) == 1, "expected one prompt terminal marker")
    require(len(leases) == 2, f"expected two shot lease acquisitions, found {len(leases)}")
    allowed_peak_labels = (
        {"wan_ti2v", "fastwan_8gb"}
        if raw["engine"] == "fastwan_8gb"
        else {raw["engine"]}
    )
    for _, _, match in peaks:
        require(
            match["engine"] in allowed_peak_labels,
            "render-phase peak belongs to another engine",
        )

    observed = raw["observed_outcome"]
    require(observed in {"success", "refusal"}, f"unsupported observed outcome {observed}")
    if observed == "success":
        require(raw["command_returncode"] == 0, "success has nonzero child return code")
        require(not refusals, "success contains a MotionBudget refusal")
        require(len(assemblies) == 1, "successful topology needs one long-chain assembly")
        completed_long = True
        completed_small = True
    else:
        require(raw["command_returncode"] != 0, "refusal has zero child return code")
        require(len(refusals) == 1, f"expected one primary refusal line, found {len(refusals)}")
        refusal = refusals[0]
        match = refusal[2]
        require(match["engine"] == raw["engine"], "refusal belongs to another engine")
        require(int(match["budget"]) == int(match["snapped"]), "refusal silently snapped the request")
        require(float(match["margin"]) == 0.85, "refusal margin drift")
        if order == "long_then_small":
            require(match["shot"] == SMALL_SHOT_ID, "long-first leg refused before the follow-on small shot")
            require(int(match["budget"]) == SMALL_TARGET, "follow-on refusal is not the 65-frame request")
            require(len(assemblies) == 1, "long-first refusal lacks 200-frame assembly")
            completed_long = True
            completed_small = False
        else:
            require(match["shot"] == LONG_SHOT_ID, "small-first leg did not refuse on the later long shot")
            require(int(match["budget"]) == LONG_SEGMENTS[0]["render_frames"], "later long refusal is not segment zero")
            require(not assemblies, "refused long shot unexpectedly assembled")
            completed_long = False
            completed_small = True

    completed_segment_count = (2 if completed_long else 0) + (1 if completed_small else 0)
    if raw["engine"] in {"wan_ti2v", "fastwan_8gb"}:
        require(
            len(peaks) == completed_segment_count,
            f"WAN-family completed topology needs {completed_segment_count} render-phase markers, found {len(peaks)}",
        )
    elif peaks:
        require(
            len(peaks) == completed_segment_count,
            f"partial optional render-phase marker set: expected {completed_segment_count}, found {len(peaks)}",
        )
    if raw["engine"] == "fastwan_8gb":
        marker_ids = {
            match["marker"]
            for _index, _event, match in indexed_matches(events, FASTWAN_MARKER_RE)
        }
        require(
            len(marker_ids) == completed_segment_count,
            f"FastWan DMD execution markers: expected {completed_segment_count}, found {len(marker_ids)}",
        )
        engine_execution_evidence = {
            "kind": "OTR_DMDRestart unique markers",
            "completed_segment_count": completed_segment_count,
            "unique_marker_ids": sorted(marker_ids),
        }
    elif raw["engine"] == "ltx_video":
        hq_matches = indexed_matches(events, LTX_HQ_RE)
        single_pass_matches = indexed_matches(events, LTX_I2V_RE)
        require(not (hq_matches and single_pass_matches), "LTX mixed recipe markers in one leg")
        if hq_matches:
            ltx_signatures = {
                (
                    match["image"],
                    int(match["width"]),
                    int(match["height"]),
                    int(match["length"]),
                    match["recipe"],
                )
                for _index, _event, match in hq_matches
            }
            marker_kind = "eng_ltx_video S5 HQ two-stage unique init/geometry/length markers"
        else:
            ltx_signatures = {
                (
                    match["image"],
                    int(match["width"]),
                    int(match["height"]),
                    int(match["length"]),
                    "single_pass",
                )
                for _index, _event, match in single_pass_matches
            }
            marker_kind = "eng_ltx_video LTX-I2V unique init/geometry/length markers"
        require(
            len(ltx_signatures) == completed_segment_count,
            f"LTX-I2V execution markers: expected {completed_segment_count}, found {len(ltx_signatures)}",
        )
        require(
            {signature[3] for signature in ltx_signatures} <= {169},
            "LTX execution marker contains a non-169 render length",
        )
        engine_execution_evidence = {
            "kind": marker_kind,
            "completed_segment_count": completed_segment_count,
            "unique_signatures": [list(signature) for signature in sorted(ltx_signatures)],
        }
        if completed_small:
            small_assemblies = indexed_matches(events, SMALL_ASSEMBLY_RE)
            require(len(small_assemblies) == 1, "LTX trimmed 169->65 small-shot assembly proof missing")
            engine_execution_evidence["small_169_to_65_assembly_event"] = event_ref(
                small_assemblies[0][0], small_assemblies[0][1]
            )
    else:
        engine_execution_evidence = {
            "kind": "wan_ti2v render-phase and refusal labels",
            "completed_segment_count": completed_segment_count,
        }

    if completed_long:
        assembly_index, assembly_event, assembly_match = assemblies[0]
        require(assembly_match["shot"] == LONG_SHOT_ID, "wrong shot assembled")
        require(int(assembly_match["segments"]) == 2, "long shot assembly segment count drift")
        require(int(assembly_match["frames"]) == LONG_TARGET, "long shot did not deliver exactly 200 frames")
    else:
        assembly_index = None
        assembly_event = None

    if order == "long_then_small":
        require(
            assembly_index is not None and leases[0][0] < assembly_index < leases[1][0],
            "long assembly/next-shot order drift",
        )
        if peaks:
            require(leases[0][0] < peaks[0][0], "long shot peak preceded its lease")
            require(peaks[0][0] < peaks[1][0] < assembly_index, "long segment order regressed")
            if observed == "success":
                require(leases[1][0] < peaks[2][0], "small render peak preceded its lease")
        if observed == "refusal":
            require(leases[1][0] < refusals[0][0], "small refusal preceded its lease")
        shot_peak_slices = (
            {LONG_SHOT_ID: peaks[:2], SMALL_SHOT_ID: peaks[2:]}
            if peaks
            else {LONG_SHOT_ID: [], SMALL_SHOT_ID: []}
        )
    else:
        require(leases[0][0] < leases[1][0], "small-first lease order drift")
        if observed == "success":
            require(assembly_index is not None and leases[1][0] < assembly_index, "long assembly order drift")
            if peaks:
                require(leases[0][0] < peaks[0][0] < leases[1][0], "small-first render order drift")
                require(leases[1][0] < peaks[1][0] < peaks[2][0] < assembly_index, "later long-chain order drift")
            shot_peak_slices = (
                {SMALL_SHOT_ID: peaks[:1], LONG_SHOT_ID: peaks[1:]}
                if peaks
                else {SMALL_SHOT_ID: [], LONG_SHOT_ID: []}
            )
        else:
            require(leases[1][0] < refusals[0][0], "later long refusal preceded its lease")
            if peaks:
                require(leases[0][0] < peaks[0][0] < leases[1][0], "small-first render order drift")
            shot_peak_slices = (
                {SMALL_SHOT_ID: peaks[:1], LONG_SHOT_ID: []}
                if peaks
                else {SMALL_SHOT_ID: [], LONG_SHOT_ID: []}
            )

    reproduction = raw.get("retention_reproduction_evidence")
    if reproduction is not None and order == "long_then_small" and observed == "refusal":
        require(reproduction.get("long_chain_200_proved") is True, "sidecar reproduction flag disagrees on long chain")
        require(reproduction.get("small_shot_65_refusal_proved") is True, "sidecar reproduction flag disagrees on refusal")

    return {
        "peaks": peaks,
        "assemblies": assemblies,
        "refusals": refusals,
        "leases": leases,
        "shot_peak_slices": shot_peak_slices,
        "completed_long": completed_long,
        "completed_small": completed_small,
        "assembly_index": assembly_index,
        "assembly_event": assembly_event,
        "prompt_completion_index": events.index(prompt_completions[0]),
        "prompt_completion_event": prompt_completions[0],
        "engine_execution_evidence": engine_execution_evidence,
    }


def derive_metrics(raw: dict[str, Any], samples: list[dict[str, Any]], topology: dict[str, Any]) -> dict[str, Any]:
    baseline = sample_payload(raw["baseline"])
    whole = interval_stats(samples, int(raw["started_at_ns"]), int(raw["child_finished_at_ns"]))
    segments: list[dict[str, Any]] = []
    leases_by_shot = (
        {LONG_SHOT_ID: topology["leases"][0], SMALL_SHOT_ID: topology["leases"][1]}
        if raw["fixture_order"] == "long_then_small"
        else {SMALL_SHOT_ID: topology["leases"][0], LONG_SHOT_ID: topology["leases"][1]}
    )
    chronological_shots = (
        (LONG_SHOT_ID, SMALL_SHOT_ID)
        if raw["fixture_order"] == "long_then_small"
        else (SMALL_SHOT_ID, LONG_SHOT_ID)
    )
    for shot_id in chronological_shots:
        shot_peaks = topology["shot_peak_slices"][shot_id]
        start_ns = int(leases_by_shot[shot_id][1]["observed_at_ns"])
        for segment_index, (event_index, event, match) in enumerate(shot_peaks):
            end_ns = int(event["observed_at_ns"])
            stats = interval_stats(samples, start_ns, end_ns)
            segments.append(
                {
                    "shot_id": shot_id,
                    "segment_index": segment_index,
                    "phase_boundary": event_ref(event_index, event),
                    "wrapper_logged_peak_mb": int(match["peak"]),
                    "wrapper_logged_post_mb": int(match["post"]),
                    "sidecar_200ms": stats,
                    "boundary_sample_at_or_after": sample_at_or_after(samples, end_ns),
                }
            )
            start_ns = end_ns

    first_lease_index, first_lease = topology["leases"][0]
    second_lease_index, second_lease = topology["leases"][1]
    refusal_event = topology["refusals"][0][1] if topology["refusals"] else None
    if raw["fixture_order"] == "long_then_small":
        first_shot_id, second_shot_id = LONG_SHOT_ID, SMALL_SHOT_ID
        first_end = topology["assembly_event"]
        second_end = (
            refusal_event
            if refusal_event is not None
            else topology["prompt_completion_event"]
        )
    else:
        first_shot_id, second_shot_id = SMALL_SHOT_ID, LONG_SHOT_ID
        first_end = second_lease
        second_end = (
            refusal_event
            if refusal_event is not None
            else topology["assembly_event"]
        )
    require(first_end is not None and second_end is not None, "shot-window boundary is missing")
    shot_windows = [
        {
            "shot_id": first_shot_id,
            "outcome": "completed",
            "sidecar_200ms": interval_stats(
                samples,
                int(first_lease["observed_at_ns"]),
                int(first_end["observed_at_ns"]),
            ),
        },
        {
            "shot_id": second_shot_id,
            "outcome": (
                "refused_at_admission"
                if refusal_event is not None
                else "completed"
            ),
            "sidecar_200ms": interval_stats(
                samples,
                int(second_lease["observed_at_ns"]),
                int(second_end["observed_at_ns"]),
            ),
        },
    ]

    inter_shot = sample_at_or_before(samples, int(second_lease["observed_at_ns"]))
    inter_shot["event"] = event_ref(second_lease_index, second_lease)
    inter_shot["definition"] = (
        "last 200 ms sidecar sample at or before the second-shot lease/admission event"
    )
    inter_shot["retained_above_start_baseline_gib"] = round(
        inter_shot["vram_used_gib"] - baseline["vram_used_gib"], 6
    )

    refusal_payload = None
    if topology["refusals"]:
        event_index, event, match = topology["refusals"][0]
        refusal_payload = {
            "event": event_ref(event_index, event),
            "shot_id": match["shot"],
            "requested_frames": int(match["budget"]),
            "snapped_frames": int(match["snapped"]),
            "affordable_frames": int(match["affordable"]),
            "free_mb_reported_by_cost_model": int(match["free"]),
            "margin": float(match["margin"]),
            "sample_immediately_before_event": sample_at_or_before(
                samples, int(event["observed_at_ns"]), strict=True
            ),
            "sample_at_or_after_event": sample_at_or_after(samples, int(event["observed_at_ns"])),
        }

    post_samples = [sample for sample in samples if int(sample["sampled_at_ns"]) >= int(raw["child_finished_at_ns"])]
    require(post_samples, "post-terminal window has no samples")
    post_peak = max(post_samples, key=lambda sample: float(sample["vram_used_mib"]))
    post_min = min(post_samples, key=lambda sample: float(sample["vram_used_mib"]))
    post_terminal = {
        "duration_s": round(
            (int(raw["telemetry_finished_at_ns"]) - int(raw["child_finished_at_ns"])) / 1e9,
            6,
        ),
        "sample_count": len(post_samples),
        "first": sample_payload(post_samples[0]),
        "last": sample_payload(post_samples[-1]),
        "minimum": sample_payload(post_min),
        "maximum": sample_payload(post_peak),
    }

    return {
        "clock_semantics": "server-log and child-stdout timestamps are observation times, not producer timestamps",
        "sampler_interval_s": EXPECTED_INTERVAL_S,
        "telemetry_sample_count": len(samples),
        "child_process_duration_s": float(raw["child_duration_s"]),
        "baseline": baseline,
        "whole_child_window": whole,
        "shot_windows": shot_windows,
        "render_segments": segments,
        "inter_shot_boundary": inter_shot,
        "refusal": refusal_payload,
        "post_terminal_cleanup_window": post_terminal,
    }


def comfy_registry_source_binding() -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "-C", str(COMFY_MANAGER_ROOT), "show", COMFY_REGISTRY_SOURCE_OBJECT],
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, "cannot read pinned ComfyUI-Manager registry source")
    require(
        sha256_bytes(completed.stdout) == COMFY_REGISTRY_SOURCE_SHA256,
        "pinned ComfyUI-Manager registry source SHA drift",
    )
    try:
        text = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"ComfyUI-Manager registry source is not UTF-8: {exc}") from exc
    for required in (
        'base_url = "https://api.comfy.org"',
        "sub_uri = f'{base_url}/nodes?page={page}&limit=30",
        "cache_mode=False, silent=True, dont_cache=True",
        'print(f"FETCH ComfyRegistry Data: {page}/{sub_json_obj[\'totalPages\']}")',
    ):
        require(required in text, f"ComfyUI-Manager registry source contract drift: {required}")
    return {
        "git_object": COMFY_REGISTRY_SOURCE_OBJECT,
        "sha256": COMFY_REGISTRY_SOURCE_SHA256,
        "endpoint": "https://api.comfy.org/nodes",
        "semantics": (
            "The pinned source issues uncached page requests to api.comfy.org/nodes and emits the "
            "captured FETCH ComfyRegistry Data marker every fifth page."
        ),
    }


def network_incidents(raw: dict[str, Any]) -> list[dict[str, Any]]:
    incidents = []
    registry_binding: dict[str, Any] | None = None
    for index, event in enumerate(raw["server_log"]["events"]):
        text = str(event.get("text", ""))
        urls = sorted(set(NETWORK_URL_RE.findall(text)))
        if urls:
            incidents.append(
                {
                    "classification": "AUTOMATIC_COMFYUI_MANAGER_REGISTRY_NETWORK_ACTIVITY",
                    "event": event_ref(index, event),
                    "urls": urls,
                }
            )
            continue
        marker = COMFY_REGISTRY_FETCH_RE.search(text)
        if marker is None:
            continue
        if registry_binding is None:
            registry_binding = comfy_registry_source_binding()
        incidents.append(
            {
                "classification": "COMFY_REGISTRY_PAGED_FETCH",
                "event": event_ref(index, event),
                "marker": marker.group(0),
                "urls": [registry_binding["endpoint"]],
                "endpoint_source_binding": registry_binding,
            }
        )
    return incidents


def committed_source_binding(head: str) -> dict[str, Any]:
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "fixture OTR HEAD is malformed")
    sources: dict[str, Any] = {}
    for relative in OTR_SOURCE_PATHS:
        completed = subprocess.run(
            ["git", "-C", str(OTR_ROOT), "show", f"{head}:{relative}"],
            capture_output=True,
            check=False,
        )
        require(completed.returncode == 0, f"cannot read OTR {head}:{relative}")
        sources[relative] = {
            "git_object": f"{head}:{relative}",
            "sha256": sha256_bytes(completed.stdout),
            "bytes": len(completed.stdout),
        }
    return {
        "otr_head_at_fixture_build": head,
        "committed_sources": sources,
        "worktree_at_render": "NOT_CAPTURED",
        "caveat": (
            "The fixture contract binds the OTR commit and the sidecar binds the existing harness byte hash. "
            "The server loaded the live OTR worktree through its ComfyUI custom_nodes path, but the complete "
            "dirty-worktree status and every loaded Python byte hash were not snapshotted at render start. "
            "These committed-source hashes are therefore a reproducible baseline, not proof that no dirty "
            "override existed. Numeric telemetry remains bound to the immutable raw sidecar SHA."
        ),
    }


def committed_line_evidence(head: str, relative: str, needle: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "-C", str(OTR_ROOT), "show", f"{head}:{relative}"],
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"cannot read OTR {head}:{relative}")
    text = completed.stdout.decode("utf-8")
    matches = [
        (index, line)
        for index, line in enumerate(text.splitlines(), start=1)
        if needle in line
    ]
    require(len(matches) == 1, f"static evidence {needle!r}: expected 1 line, found {len(matches)}")
    line_number, line = matches[0]
    return {
        "git_object": f"{head}:{relative}",
        "sha256": sha256_bytes(completed.stdout),
        "line": line_number,
        "evidence": line.strip(),
    }


def leg_key(engine: str, order: str) -> str:
    matches = [
        key
        for key, spec in REQUIRED_LEGS.items()
        if spec["engine"] == engine and spec["order"] == order
    ]
    require(len(matches) == 1, f"unsupported engine/order pair {engine}/{order}")
    return matches[0]


def validate_leg(root: Path, telemetry_path: Path, raw_override: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    raw = copy.deepcopy(raw_override) if raw_override is not None else read_json(telemetry_path)
    samples = validate_raw_envelope(raw)
    contract, manifest, ledger, bundle_refs, normalized_contract = validate_bundle(raw, root=root)
    raw["fixture_order"] = normalized_contract["order"]
    topology = validate_topology(raw, normalized_contract["order"])
    key = leg_key(raw["engine"], normalized_contract["order"])
    expected_outcome = raw["expected_outcome"]
    require(expected_outcome in {"success", "refusal", "either"}, "invalid expected outcome")
    require(expected_outcome == "either" or expected_outcome == raw["observed_outcome"], "observed outcome missed the sidecar contract")

    telemetry_ref = source_ref(telemetry_path, root=root) if raw_override is None else {
        "path": telemetry_path.as_posix(),
        "sha256": "TEST_OVERRIDE",
        "bytes": len(canonical_json_bytes(raw_override)),
    }
    metrics = derive_metrics(raw, samples, topology)
    observed_network_incidents = network_incidents(raw)
    source_binding = committed_source_binding(normalized_contract["otr_repo_head_at_build"])
    require(
        source_binding["committed_sources"]["scripts/otr_visual_smoke.py"]["sha256"]
        == raw["command"]["otr_harness_sha256"],
        "raw harness SHA does not match the fixture-build commit",
    )
    if normalized_contract["contract_class"] == "phase3_cross_engine_neutral_diagnostic":
        phase3_source_paths = {
            "otr_visual_smoke.py": "scripts/otr_visual_smoke.py",
            "render_driver.py": "nodes/_otr_video_engines/render_driver.py",
            "coverage_plan.py": "nodes/_otr_video_engines/coverage_plan.py",
            "engine.py": (
                "nodes/_otr_video_engines/eng_fastwan_8gb.py"
                if raw["engine"] == "fastwan_8gb"
                else "nodes/_otr_video_engines/eng_ltx_video.py"
            ),
            "wan_parent.py": "nodes/_otr_video_engines/eng_wan_ti2v.py",
        }
        for label, path in phase3_source_paths.items():
            require(
                contract["source_sha256s"][label]
                == source_binding["committed_sources"][path]["sha256"],
                f"Phase-3 committed source binding drift: {label}",
            )
    shots = ledger["video"]["shots"]
    long_segments, small_segments = engine_plans(raw["engine"])
    shot_control_rows = []
    for shot in sorted(shots, key=lambda row: row["shot_id"]):
        shot_control_rows.append(
            {
                key: value
                for key, value in shot.items()
                if key
                not in {
                    "engine_id",
                    "profile_id",
                    "family",
                    "coverage_plan",
                    "render_request_hash",
                    "binding_hash",
                    "cache_keys",
                }
            }
        )
    asset_hashes = sorted(asset["sha256"] for asset in manifest["assets"].values())
    shared_source_paths = (
        "scripts/otr_visual_smoke.py",
        "nodes/_otr_video_engines/render_driver.py",
        "nodes/_otr_video_engines/coverage_plan.py",
        "nodes/_otr_video_engines/eng_wan_ti2v.py",
    )
    shared_source_sha256s = {
        path: source_binding["committed_sources"][path]["sha256"]
        for path in shared_source_paths
    }
    if raw.get("sidecar_source") is None:
        legacy_sidecar_path = root / LEGACY_RAW_SIDECAR_ARCHIVE
        require(legacy_sidecar_path.is_file(), "archived legacy sidecar source is missing")
        legacy_sidecar_ref = source_ref(legacy_sidecar_path, root=root)
        require(
            legacy_sidecar_ref["sha256"] == LEGACY_RAW_SIDECAR_SHA256,
            "archived legacy sidecar source SHA drift",
        )
        sidecar_binding = {
            "status": "LEGACY_EXTERNAL_BINDING_ARCHIVED_IN_LAB_EVIDENCE",
            **legacy_sidecar_ref,
            "caveat": (
                "Phase-1/Phase-4 legacy raw receipts predate the self-hash field. The session ledger "
                "externally recorded this sidecar SHA; the raw JSON itself does not prove it, but the "
                "exact source bytes are preserved at this repo-local evidence path."
            ),
        }
        force_status = "LEGACY_INCORRECT_DECLARATIVE_LABEL_NOT_SERVER_ENV_PROOF"
    else:
        sidecar_binding = {
            "status": "EMBEDDED_SELF_HASH",
            "path": raw["sidecar_source"]["path"],
            "sha256": raw["sidecar_source"]["sha256"],
            "caveat": (
                "The raw receipt embeds the sidecar's self-hash, but does not archive the source bytes. "
                "The immutable raw telemetry SHA binds this assertion."
            ),
        }
        force_status = "CORRECTLY_UNCLAIMED"
    artifacts = validate_artifacts(root, key, raw["observed_outcome"], raw)
    receipt = {
        "schema_version": 1,
        "kind": "wan-inter-shot-retention-leg-receipt",
        "leg_id": key,
        "measured": MEASUREMENT_SCOPE,
        "status": "MEASURED_DIAGNOSTIC",
        "gate_status": "NOT_A_LAB_GATE",
        "engine": raw["engine"],
        "fixture_order": normalized_contract["order"],
        "expected_outcome": expected_outcome,
        "observed_outcome": raw["observed_outcome"],
        "boot_lane": raw["boot_lane"],
        "source_refs": {"raw_telemetry": telemetry_ref, **bundle_refs},
        "fixture_contract": {
            "contract_class": normalized_contract["contract_class"],
            "comparison_scope": normalized_contract["comparison_scope"],
            "target_frames_in_order": normalized_contract["targets"],
            "long_chain": list(long_segments),
            "small_single": list(small_segments),
            "ledger_engine_ids": sorted({shot["engine_id"] for shot in shots}),
            "engine_authority": "baked_ledger.video.shots[*].engine_id",
            "sidecar_declared_force_map": raw["command"]["server_bound_force_map"],
            "sidecar_force_map_status": force_status,
            "harness_sha256": raw["command"]["otr_harness_sha256"],
            "raw_sidecar_source_binding": sidecar_binding,
            "source_capture_sha256": normalized_contract["source_capture_sha256"],
            "control_origin_ledger_sha256": normalized_contract["control_origin_ledger_sha256"],
            "load_bearing_shared_source_sha256s": shared_source_sha256s,
            "asset_sha256s": asset_hashes,
            "shot_control_sha256": sha256_bytes(canonical_json_bytes(shot_control_rows)),
            "request_seeds_in_order": [int(shot["request_seed"]) for shot in shots],
        },
        "topology_proof": {
            "long_chain_200_completed": topology["completed_long"],
            "small_65_completed": topology["completed_small"],
            "render_phase_count": len(topology["peaks"]),
            "engine_execution_evidence": topology["engine_execution_evidence"],
            "long_assembly_event": (
                event_ref(topology["assembly_index"], topology["assembly_event"])
                if topology["assembly_event"] is not None
                else None
            ),
            "no_silent_resize_refusal": metrics["refusal"],
        },
        "artifacts": artifacts,
        "metrics": metrics,
        "server_instance": raw["server_instance"],
        "gpu_lease": raw["gpu_lease"],
        "production_state_snapshots": {
            "manifest_before": raw["node_episode_manifest_before"],
            "manifest_after": raw["node_episode_manifest_after"],
            "report_before": raw["node_episode_report_before"],
            "report_after": raw["node_episode_report_after"],
            "policy": (
                "A successful existing node92 replay is expected to advance its output report/manifest; "
                "a refused replay must leave them unchanged. These are metadata/hash snapshots, not "
                "captured file contents."
            ),
        },
        "offline_policy": {
            "status": "INCIDENT" if observed_network_incidents else "NO_NETWORK_URL_OBSERVED_IN_APPENDED_LOG",
            "observed_incidents": observed_network_incidents,
            "model_weight_download_observed_in_appended_log": False,
            "caveat": (
                "The appended production server log shows automatic ComfyUI-Manager registry fetches. No model "
                "weight download line appears in the appended render log, but this is not a complete network "
                "audit. The incident violates the lab's offline operating rule and is disclosed without "
                "altering the immutable measurement."
                if observed_network_incidents
                else "This field only reports URL-bearing lines in the appended server log; it is not a network audit."
            ),
        },
        "source_binding": source_binding,
        "interpretation_guardrail": (
            "NVIDIA/psutil sidecar values are measured at 200 ms. The wrapper's per-segment peak/post MB "
            "counters are preserved alongside them but are a different measurement surface and must not be "
            "substituted for inter-shot nvidia-smi residency. Post-terminal cleanup is not the inter-shot boundary."
        ),
        "engine_binding_caveat": (
            "Legacy Phase-1/Phase-4 telemetry serialized server_bound_force_map from its --engine argument; "
            "it did not inspect the already-running server's environment. New telemetry correctly leaves that "
            "field null. This reducer never trusts it: engine identity is proved from both baked-ledger shot "
            "rows plus engine-specific log/refusal evidence where present."
        ),
    }
    return key, receipt


def audit_attempt(root: Path, telemetry_path: Path) -> tuple[str | None, dict[str, Any] | None, dict[str, Any]]:
    ref = source_ref(telemetry_path, root=root)
    try:
        key, receipt = validate_leg(root, telemetry_path)
    except (EvidenceError, KeyError, IndexError, TypeError, ValueError) as exc:
        return None, None, {
            "source": ref,
            "accepted": False,
            "reason": str(exc),
        }
    return key, receipt, {
        "source": ref,
        "accepted": True,
        "leg_id": key,
        "observed_outcome": receipt["observed_outcome"],
    }


def historical_log_evidence() -> dict[str, Any]:
    require(HISTORICAL_LOG.is_file(), f"historical OTR log missing: {HISTORICAL_LOG}")
    # Do not use splitlines(): tqdm progress records contain bare CR bytes, while
    # the cited OTR line numbers (and rg -n) are LF-delimited physical lines.
    lines = HISTORICAL_LOG.read_text(encoding="utf-8", errors="replace").split("\n")
    assemblies = [
        index
        for index, line in enumerate(lines)
        if ASSEMBLY_RE.search(line)
        and int(ASSEMBLY_RE.search(line)["frames"]) == LONG_TARGET  # type: ignore[index]
    ]
    candidates = []
    for assembly_index in assemblies:
        preceding = [
            (index, PEAK_RE.search(lines[index]))
            for index in range(max(0, assembly_index - 120), assembly_index)
            if PEAK_RE.search(lines[index])
        ]
        following = [
            (index, REFUSAL_RE.search(lines[index]))
            for index in range(assembly_index + 1, min(len(lines), assembly_index + 20))
            if REFUSAL_RE.search(lines[index])
        ]
        if len(preceding) >= 2 and following:
            pair = preceding[-2:]
            refusal = following[0]
            if all(match and match["engine"] == "wan_ti2v" for _, match in pair) and refusal[1] and int(refusal[1]["budget"]) == SMALL_TARGET:
                candidates.append((assembly_index, pair, refusal))
    require(candidates, "historical log has no 200-frame chain followed by a 65-frame refusal")
    assembly_index, pair, refusal = candidates[-1]
    refusal_match = refusal[1]
    require(refusal_match is not None, "historical refusal regex vanished")
    return {
        "evidence_class": "HISTORICAL_WRAPPER_LOG_ONLY_NOT_SIDECAR_MEASURED",
        "source": source_ref(HISTORICAL_LOG),
        "line_numbers_are_one_based": True,
        "segments": [
            {
                "line": index + 1,
                "wrapper_logged_peak_mb": int(match["peak"]),
                "wrapper_logged_post_mb": int(match["post"]),
            }
            for index, match in pair
            if match is not None
        ],
        "assembly": {"line": assembly_index + 1, "delivered_frames": LONG_TARGET, "segment_count": 2},
        "follow_on_refusal": {
            "line": refusal[0] + 1,
            "requested_frames": int(refusal_match["budget"]),
            "affordable_frames": int(refusal_match["affordable"]),
            "free_mb_reported_by_cost_model": int(refusal_match["free"]),
        },
        "guardrail": "These are OTR wrapper log counters without the lab sidecar and are comparison context, not measured receipt rows.",
    }


def build(root: Path = ROOT) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    root = root.resolve()
    telemetry_dir = root / TELEMETRY_DIR
    require(telemetry_dir.is_dir(), f"telemetry directory missing: {telemetry_dir}")
    accepted: dict[str, dict[str, Any]] = {}
    attempt_audit: list[dict[str, Any]] = []
    for telemetry_path in sorted(telemetry_dir.glob("*.json")):
        key, receipt, audit = audit_attempt(root, telemetry_path)
        attempt_audit.append(audit)
        if key is not None and receipt is not None:
            require(key not in accepted, f"multiple valid raw receipts claim leg {key}")
            accepted[key] = receipt

    required_status = {
        key: {
            "status": "MEASURED" if key in accepted else "PENDING",
            "engine": spec["engine"],
            "fixture_order": spec["order"],
            "receipt": spec["output"].as_posix(),
        }
        for key, spec in REQUIRED_LEGS.items()
    }
    phase1 = accepted.get("phase1_wan_ti2v_long_first")
    if phase1 is not None:
        require(phase1["observed_outcome"] == "refusal", "Phase 1 must reproduce the follow-on refusal")

    long_first = [
        receipt for receipt in accepted.values() if receipt["fixture_order"] == "long_then_small"
    ]
    control_hashes = {
        (
            receipt["source_refs"]["master_audio"]["sha256"],
            receipt["fixture_contract"]["source_capture_sha256"],
            receipt["fixture_contract"]["control_origin_ledger_sha256"],
            tuple(
                sorted(
                    receipt["fixture_contract"]["load_bearing_shared_source_sha256s"].items()
                )
            ),
            tuple(receipt["fixture_contract"]["asset_sha256s"]),
            receipt["fixture_contract"]["shot_control_sha256"],
            tuple(receipt["fixture_contract"]["target_frames_in_order"]),
            tuple(receipt["fixture_contract"]["request_seeds_in_order"]),
        )
        for receipt in long_first
    }
    if len(long_first) > 1:
        require(
            len(control_hashes) == 1,
            "Phase-3 cross-engine diagnostic changed assets/seed/targets/shot controls",
        )
    server_identities = [
        (receipt["server_instance"]["serving_pid"], receipt["server_instance"]["process_create_time"])
        for receipt in accepted.values()
    ]
    require(len(server_identities) == len(set(server_identities)), "accepted legs reused a server instance")

    rows = []
    for key in REQUIRED_LEGS:
        receipt = accepted.get(key)
        if receipt is None:
            continue
        metrics = receipt["metrics"]
        whole_peak_gib = metrics["whole_child_window"]["peak_vram"]["vram_used_gib"]
        rows.append(
            {
                "leg_id": key,
                "engine": receipt["engine"],
                "fixture_order": receipt["fixture_order"],
                "observed_outcome": receipt["observed_outcome"],
                "child_process_duration_s": metrics["child_process_duration_s"],
                "baseline_vram_gib": metrics["baseline"]["vram_used_gib"],
                "whole_child_peak_vram_gib": whole_peak_gib,
                "whole_child_peak_host_ram_gib": metrics["whole_child_window"]["peak_host_ram"]["host_ram_used_gib"],
                "global_14_5_gib_ceiling_exceeded": whole_peak_gib > 14.5,
                "headroom_to_14_5_gib": round(14.5 - whole_peak_gib, 6),
                "inter_shot_vram_gib": metrics["inter_shot_boundary"]["vram_used_gib"],
                "inter_shot_retained_above_baseline_gib": metrics["inter_shot_boundary"]["retained_above_start_baseline_gib"],
                "follow_on_refusal_affordable_frames": (
                    metrics["refusal"]["affordable_frames"] if metrics["refusal"] else None
                ),
                "post_terminal_last_vram_gib": metrics["post_terminal_cleanup_window"]["last"]["vram_used_gib"],
                "durable_artifacts": receipt["artifacts"]["artifacts"],
                "receipt": REQUIRED_LEGS[key]["output"].as_posix(),
            }
        )

    phase4 = accepted.get("phase4_wan_ti2v_small_first")
    if phase1 is not None and phase4 is not None:
        p1_control = phase1["fixture_contract"]
        p4_control = phase4["fixture_contract"]
        for field in (
            "source_capture_sha256",
            "asset_sha256s",
            "shot_control_sha256",
            "long_chain",
            "small_single",
        ):
            require(p1_control[field] == p4_control[field], f"order-sensitivity control drift: {field}")
        require(
            phase1["source_refs"]["master_audio"]["sha256"]
            == phase4["source_refs"]["master_audio"]["sha256"],
            "order-sensitivity master audio drift",
        )
        require(phase1["engine"] == phase4["engine"] == "wan_ti2v", "order-sensitivity engine drift")
        require(phase1["observed_outcome"] == "refusal", "long-first control did not refuse")
        require(phase4["observed_outcome"] == "success", "small-first reversal did not complete")
        order_sensitivity = {
            "status": "MEASURED",
            "result": "CONFIRMED_ORDER_DEPENDENT",
            "control_fields_equal": [
                "engine",
                "source capture",
                "master audio",
                "visual assets",
                "per-shot controls and seeds",
                "per-shot target and coverage plan",
            ],
            "long_then_small": {
                "receipt": REQUIRED_LEGS["phase1_wan_ti2v_long_first"]["output"].as_posix(),
                "outcome": phase1["observed_outcome"],
                "small_requested_frames": phase1["metrics"]["refusal"]["requested_frames"],
                "small_affordable_frames": phase1["metrics"]["refusal"]["affordable_frames"],
            },
            "small_then_long": {
                "receipt": REQUIRED_LEGS["phase4_wan_ti2v_small_first"]["output"].as_posix(),
                "outcome": phase4["observed_outcome"],
                "delivered_long_frames": LONG_TARGET,
            },
            "interpretation": (
                "The same WAN shots complete when the 65-frame shot is rendered first, but the 65-frame "
                "shot is refused after the 200-frame chain. This proves order sensitivity; it does not "
                "identify the retained allocation's owner or authorize a planner workaround."
            ),
        }
    else:
        order_sensitivity = {"status": "PENDING", "result": None}

    fastwan = accepted.get("phase3_fastwan_8gb_long_first")
    ltx = accepted.get("phase3_ltx_video_long_first")
    if fastwan is not None:
        fastwan_head = fastwan["source_binding"]["otr_head_at_fixture_build"]
        inheritance = committed_line_evidence(
            fastwan_head,
            "nodes/_otr_video_engines/eng_fastwan_8gb.py",
            "class FastWan8gbEngine(_WT.WanTi2vEngine):",
        )
    else:
        inheritance = None
    if phase1 is None or fastwan is None:
        cross_family_result = "PENDING_WAN_FAMILY_CONTROL"
    elif ltx is None:
        cross_family_result = "WAN_AND_FASTWAN_REFUSAL_REPRODUCED_LTX_PENDING"
    elif ltx["observed_outcome"] == "refusal":
        cross_family_result = "REFUSAL_REPRODUCED_BEYOND_WAN_FAMILY"
    else:
        cross_family_result = "REFUSAL_OBSERVED_ONLY_IN_WAN_FAMILY_IN_THIS_MEASURED_SET"
    cross_engine = {
        "status": "MEASURED" if phase1 is not None and fastwan is not None and ltx is not None else "PARTIAL",
        "result": cross_family_result,
        "wan_ti2v_outcome": phase1["observed_outcome"] if phase1 else None,
        "fastwan_8gb_outcome": fastwan["observed_outcome"] if fastwan else None,
        "ltx_video_outcome": ltx["observed_outcome"] if ltx else None,
        "fastwan_relationship": {
            "classification": "WAN_SUBCLASS_NOT_AN_INDEPENDENT_FAMILY" if inheritance else "PENDING",
            "static_source_evidence": inheritance,
        },
        "humo_disposition": {
            "status": "BLOCKED_NOT_CHEAP_NOT_TOPOLOGY_EQUAL",
            "reason": (
                "HuMo is not a topology-equal control: its adapter uses a soft-reference JOIN_JUMP "
                "route rather than the strict first-frame JOIN_CHAIN under test. No HuMo retention "
                "number is inferred."
            ),
        },
        "guardrail": (
            "FastWan reproduces a WAN-family behavior because it subclasses WanTi2vEngine. Only the "
            "LTX leg decides whether the refusal crosses engine families; this small measured set cannot "
            "prove exclusivity for every other engine."
        ),
        "delivered_geometry_guardrail": {
            "phase4_wan_ti2v": [
                {
                    "frames": artifact["frame_count"],
                    "width": artifact["width"],
                    "height": artifact["height"],
                }
                for artifact in (phase4["artifacts"]["artifacts"] if phase4 else [])
            ],
            "phase3_ltx_video": [
                {
                    "frames": artifact["frame_count"],
                    "width": artifact["width"],
                    "height": artifact["height"],
                }
                for artifact in (ltx["artifacts"]["artifacts"] if ltx else [])
            ],
            "interpretation": (
                "The durable WAN artifacts are 832x480 while the LTX production-wrapper artifacts are "
                "832x448. The LTX leg is therefore a cross-family retention diagnostic, not a canvas-normalized "
                "shipping-profile speed or quality comparison."
            ),
        },
    }

    offline_incident_legs = {
        key: receipt["offline_policy"]["observed_incidents"]
        for key, receipt in accepted.items()
        if receipt["offline_policy"]["status"] == "INCIDENT"
    }
    complete = all(key in accepted for key in REQUIRED_LEGS)

    comparison = {
        "schema_version": 1,
        "kind": "wan-inter-shot-retention-comparison",
        "mission_scope": "measurement and diagnosis only; no OTR fix",
        "complete": complete,
        "completion_status": (
            "MEASUREMENT_COMPLETE_WITH_OFFLINE_POLICY_INCIDENT"
            if complete and offline_incident_legs
            else "MEASUREMENT_COMPLETE"
            if complete
            else "MEASUREMENT_INCOMPLETE"
        ),
        "required_legs": required_status,
        "attempt_audit": attempt_audit,
        "rows": rows,
        "order_sensitivity": order_sensitivity,
        "cross_engine_outcome": cross_engine,
        "historical_context": historical_log_evidence(),
        "offline_policy": {
            "status": "INCIDENT" if offline_incident_legs else "NO_URL_BEARING_LOG_EVENT_OBSERVED",
            "incident_legs": offline_incident_legs,
            "model_weight_download_observed_in_appended_logs": False,
            "caveat": (
                "Automatic ComfyUI-Manager registry network activity was observed in one or more production-server "
                "logs despite the lab offline rule. No model-weight download line was observed, but appended logs "
                "are not a complete network audit. The immutable measurement remains reported with the incident."
                if offline_incident_legs
                else "URL-bearing log-line detection is not a complete network audit."
            ),
        },
        "controls": {
            "long_first_semantic_control_tuple_count": len(control_hashes),
            "assets_seed_targets_and_shot_controls_match": len(long_first) <= 1 or len(control_hashes) == 1,
            "coverage_plan_policy": (
                "WAN/FastWan use the inherited legal 177+25 chain and exact 65 single. LTX uses its "
                "engine-coupled legal 169+169 chain (trim 137) and 169 single (trim 104). This is a "
                "cross-family neutral diagnostic, not shipping-profile equivalence."
            ),
            "accepted_server_instances_are_distinct": len(server_identities) == len(set(server_identities)),
            "human_gate": "NOT_APPLICABLE_MEASUREMENT_ONLY",
        },
        "numeric_provenance_policy": (
            "Only accepted standalone-sidecar receipts are MEASURED. Sidecar peaks and boundary samples are "
            "recomputed from raw 200 ms samples. Wrapper log peak/post values remain separately labeled. "
            "The historical log is never promoted to a measured row."
        ),
    }
    return accepted, comparison


def expected_outputs(root: Path) -> dict[Path, bytes]:
    accepted, comparison = build(root)
    outputs = {root / COMPARISON_OUTPUT: canonical_json_bytes(comparison)}
    for key, receipt in accepted.items():
        outputs[root / REQUIRED_LEGS[key]["output"]] = canonical_json_bytes(receipt)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail unless all currently derivable outputs are exact")
    parser.add_argument("--root", type=Path, default=ROOT, help="lab repository root")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        outputs = expected_outputs(root)
    except EvidenceError as exc:
        print(f"[wan-retention-evidence] FAIL: {exc}", file=sys.stderr)
        return 1
    stale = [path for path, payload in outputs.items() if not path.is_file() or path.read_bytes() != payload]
    if args.check:
        if stale:
            print("[wan-retention-evidence] FAIL: stale/missing outputs:", file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            return 1
        print(f"[wan-retention-evidence] PASS: {len(outputs)} exact output(s)")
        return 0
    for path, payload in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != payload:
            path.write_bytes(payload)
            print(f"[wan-retention-evidence] wrote {path} sha256={sha256_bytes(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
