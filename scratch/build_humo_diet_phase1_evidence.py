#!/usr/bin/env python
"""Build the deterministic HuMo diet Phase-1 comparison receipt.

This is a read-only evidence reducer.  It never boots or queries ComfyUI and
never edits immutable run receipts, telemetry, or media.  Every measurement in
the generated comparison is either copied from a pinned receipt, recomputed
from pinned 200 ms samples/log observations, or probed from a hash-pinned media
artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("results/humo_diet/phase1_clamp_floor_comparison.json")

PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
TTS_SHA256 = "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
LAB_ARTIFACT_SHA256 = "5a89f88ee8140df2ad7ff6151df4b114bb4e36279bd97bc193068903645264a0"
PRODUCTION_ARTIFACT_SHA256 = "e35527b7cb72a1d113ba27f944badda7b80d104c077a94de762223d9f86b56d9"
AB_ARTIFACT_SHA256 = "5d9e3b7ac916c44db5800715b2b97cba8b58b456c19bb327946f7c8dbe78f9d7"

PINNED_SOURCES = {
    "phase0": (
        "results/humo_diet/phase0_lane_feasibility.json",
        "2077d9c05bbc9065c6454dd8cf5b20f387a299a20c9617ac22e601602d118609",
    ),
    "lab_clamp13_cold_receipt": (
        "results/humo_1p7b_diet_run1.json",
        "0d9e407aaa70915ebe3a59ad77467b59f0c17729c8a4e81a8b0f792db1ca2fa0",
    ),
    "lab_clamp13_cold_telemetry": (
        "results/humo_diet/telemetry/humo_1p7b_diet_clamp13_run1.json",
        "5470b86499082d86b1eadf63aa79362f1dc00b7e9fca91549b0c5d094746706d",
    ),
    "lab_clamp13_warm_receipt": (
        "results/humo_1p7b_diet_run2.json",
        "2efbf36ebfd49fffb3244da750e40e1e15b924277d83476bbd0c974dddb8a935",
    ),
    "lab_clamp13_warm_telemetry": (
        "results/humo_diet/telemetry/humo_1p7b_diet_clamp13_run2.json",
        "774602841c104f073efbfe1c420d401b0d55ce9306ee8149db6102af59155471",
    ),
    "lab_clamp12_cold_receipt": (
        "results/humo_1p7b_diet_run3.json",
        "484e8b8b4d5761ae88f0eb54d435b21eb04e8f33da3a6dd44db47f70448b180d",
    ),
    "lab_clamp12_cold_telemetry": (
        "results/humo_diet/telemetry/humo_1p7b_diet_clamp12_run1.json",
        "c8ffcd056a044998cfb432417ff769dcda7b62aa471add89b8a56f2828dd42fb",
    ),
    "production_take1_receipt": (
        "results/otr_side/humo_1_7b_bakeoff_take1.json",
        "05c9208a85bf41e8057e5776b23831d79be3880fa6b16041926738d7739680cb",
    ),
    "production_take1_telemetry": (
        "results/otr_side/telemetry/humo_1_7b_bakeoff_take1_attempt2.json",
        "500db87942fbe49d9702987da85bb3199f392950822511ed1010a2dd7c8dbecc",
    ),
    "production_take2_receipt": (
        "results/otr_side/humo_1_7b_bakeoff_take2.json",
        "b2ef2069a545bd44ab3f496af671d5257224313c549160569f3b548b79da7063",
    ),
    "production_take2_telemetry": (
        "results/otr_side/telemetry/humo_1_7b_bakeoff_take2.json",
        "4273d090723b09dd6296b1a5dddc0467f32b5f9c3d9adaf8d699bf1cbc14cbb7",
    ),
    "portrait_fixture": ("fixtures/portrait.png", PORTRAIT_SHA256),
    "tts_fixture": ("fixtures/tts_dialogue.wav", TTS_SHA256),
    "production_take1_artifact": (
        "outputs/humo_1_7b_bakeoff_take1.mp4",
        PRODUCTION_ARTIFACT_SHA256,
    ),
    "production_take2_artifact": (
        "outputs/humo_1_7b_bakeoff_take2.mp4",
        PRODUCTION_ARTIFACT_SHA256,
    ),
    "lab_clamp13_cold_artifact": (
        "outputs/humo_1p7b_diet_out_00001_.mp4",
        LAB_ARTIFACT_SHA256,
    ),
    "lab_clamp13_warm_artifact": (
        "outputs/humo_1p7b_diet_out_00002_.mp4",
        LAB_ARTIFACT_SHA256,
    ),
    "lab_clamp12_cold_artifact": (
        "outputs/humo_1p7b_diet_out_00003_.mp4",
        LAB_ARTIFACT_SHA256,
    ),
    "ab_review_artifact": (
        "outputs/humo_1p7b_diet_ab_production_vs_clamp13_warm.mp4",
        AB_ARTIFACT_SHA256,
    ),
}

LAB_RUNS = (
    {
        "id": "clamp13_cold",
        "receipt": "lab_clamp13_cold_receipt",
        "telemetry": "lab_clamp13_cold_telemetry",
        "artifact": "lab_clamp13_cold_artifact",
        "run_number": 1,
        "clamp_target_gib": 13.0,
        "expected_status": "PASS (cold)",
        "expected_warm": False,
        "expected_gate_pass": True,
    },
    {
        "id": "clamp13_warm",
        "receipt": "lab_clamp13_warm_receipt",
        "telemetry": "lab_clamp13_warm_telemetry",
        "artifact": "lab_clamp13_warm_artifact",
        "run_number": 2,
        "clamp_target_gib": 13.0,
        "expected_status": "PASS",
        "expected_warm": True,
        "expected_gate_pass": True,
    },
    {
        "id": "clamp12_cold",
        "receipt": "lab_clamp12_cold_receipt",
        "telemetry": "lab_clamp12_cold_telemetry",
        "artifact": "lab_clamp12_cold_artifact",
        "run_number": 3,
        "clamp_target_gib": 12.0,
        "expected_status": "FAIL (net VRAM 12.28 GB > clamp 12.0 GB)",
        "expected_warm": False,
        "expected_gate_pass": False,
    },
)

PRODUCTION_RUNS = (
    {
        "id": "production_take1",
        "receipt": "production_take1_receipt",
        "telemetry": "production_take1_telemetry",
        "artifact": "production_take1_artifact",
    },
    {
        "id": "production_take2",
        "receipt": "production_take2_receipt",
        "telemetry": "production_take2_telemetry",
        "artifact": "production_take2_artifact",
    },
)

AB_FFMPEG_ARGV = [
    "ffmpeg",
    "-nostdin",
    "-hide_banner",
    "-loglevel",
    "error",
    "-n",
    "-i",
    r"outputs\humo_1_7b_bakeoff_take1.mp4",
    "-i",
    r"outputs\humo_1p7b_diet_out_00002_.mp4",
    "-i",
    r"fixtures\tts_dialogue.wav",
    "-filter_complex",
    (
        "[0:v]drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':"
        "text='A  Production unclamped':fontcolor=white:fontsize=22:box=1:"
        "boxcolor=black@0.65:boxborderw=8:x=(w-text_w)/2:y=18[left];"
        "[1:v]drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':"
        "text='B  Lab clamp-13 warm':fontcolor=white:fontsize=22:box=1:"
        "boxcolor=black@0.65:boxborderw=8:x=(w-text_w)/2:y=18[right];"
        "[left][right]hstack=inputs=2[v]"
    ),
    "-map",
    "[v]",
    "-map",
    "2:a:0",
    "-t",
    "5.16",
    "-r",
    "25",
    "-map_metadata",
    "-1",
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "18",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-movflags",
    "+faststart",
    r"outputs\humo_1p7b_diet_ab_production_vs_clamp13_warm.mp4",
]


class EvidenceError(RuntimeError):
    """Pinned or internally bound evidence did not validate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(not raw.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid UTF-8 JSON {path}: {exc}") from exc
    require(isinstance(payload, dict), f"expected JSON object: {path}")
    return payload


def load_pinned_sources(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    refs: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for source_id, (relative, expected_sha) in PINNED_SOURCES.items():
        path = root / relative
        require(path.is_file(), f"missing pinned source {source_id}: {relative}")
        actual_sha = sha256_file(path)
        require(
            actual_sha == expected_sha,
            f"pinned source changed for {source_id}: expected {expected_sha}, got {actual_sha}",
        )
        refs[source_id] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": actual_sha,
            "bytes": path.stat().st_size,
        }
        paths[source_id] = path
    return refs, paths


def event_ref(event: dict[str, Any], match: str, occurrence: str) -> dict[str, Any]:
    return {
        "match": match,
        "occurrence": occurrence,
        "observed_at_ns": int(event["observed_at_ns"]),
        "observed_at_utc": event["observed_at_utc"],
        "raw_sha256": event["raw_sha256"],
        "log_offsets": [int(event["start_offset"]), int(event["end_offset"])],
    }


def matching_events(events: Iterable[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
    return [event for event in events if pattern in str(event.get("text", ""))]


def one_event(
    events: list[dict[str, Any]], pattern: str, *, occurrence: str = "first"
) -> dict[str, Any]:
    matches = matching_events(events, pattern)
    require(matches, f"missing server-log event: {pattern}")
    require(occurrence in {"first", "last"}, f"invalid occurrence {occurrence}")
    return matches[0] if occurrence == "first" else matches[-1]


def phase_stats(
    samples: list[dict[str, Any]],
    start_ns: int,
    end_ns: int,
    *,
    include_end: bool,
) -> dict[str, Any]:
    selected = [
        sample
        for sample in samples
        if int(sample["sampled_at_ns"]) >= start_ns
        and (
            int(sample["sampled_at_ns"]) <= end_ns
            if include_end
            else int(sample["sampled_at_ns"]) < end_ns
        )
    ]
    require(selected, f"phase has no telemetry samples: {start_ns}..{end_ns}")
    vram_peak = max(selected, key=lambda row: float(row["vram_used_mib"]))
    vram_min = min(selected, key=lambda row: float(row["vram_used_mib"]))
    host_peak = max(selected, key=lambda row: int(row["host_ram_used_bytes"]))
    peak_mib = float(vram_peak["vram_used_mib"])
    min_mib = float(vram_min["vram_used_mib"])
    peak_host_bytes = int(host_peak["host_ram_used_bytes"])
    return {
        "duration_s": round((end_ns - start_ns) / 1_000_000_000.0, 6),
        "sample_count": len(selected),
        "minimum_vram_mib": min_mib,
        "minimum_vram_gib": round(min_mib / 1024.0, 6),
        "peak_vram_mib": peak_mib,
        "peak_vram_gib": round(peak_mib / 1024.0, 6),
        "peak_vram_sampled_at_ns": int(vram_peak["sampled_at_ns"]),
        "peak_vram_sampled_at_utc": vram_peak["sampled_at_utc"],
        "peak_host_ram_bytes": peak_host_bytes,
        "peak_host_ram_gib": round(peak_host_bytes / (1024.0**3), 6),
        "peak_host_ram_sampled_at_ns": int(host_peak["sampled_at_ns"]),
        "peak_host_ram_sampled_at_utc": host_peak["sampled_at_utc"],
    }


def derive_phases(telemetry: dict[str, Any]) -> list[dict[str, Any]]:
    events = list(telemetry["server_log"]["events"])
    samples = list(telemetry["sampler"]["samples"])
    require(events and samples, "phase analysis requires events and samples")
    require(
        telemetry["server_log"]["timestamps_are_observation_times"] is True,
        "server log timestamps must be explicitly observation times",
    )

    prompt = one_event(events, "got prompt")
    whisper_matches = matching_events(events, "Requested to load WhisperLargeV3")
    text_matches = matching_events(events, "Requested to load WanTEModel")
    initial_vae_matches = matching_events(events, "Requested to load WanVAE")
    humo_matches = matching_events(events, "Requested to load WAN21_HuMo")
    if humo_matches:
        humo = humo_matches[0]
        humo_match = "Requested to load WAN21_HuMo"
    else:
        humo = one_event(events, "Model WAN21_HuMo prepared")
        humo_match = "Model WAN21_HuMo prepared"
    decode = one_event(events, "Model WanVAE prepared", occurrence="last")
    complete = one_event(events, "Prompt executed in", occurrence="last")

    start_ns = int(telemetry["started_at_ns"])
    end_ns = int(telemetry["child_finished_at_ns"])
    boundaries: list[tuple[str, int, dict[str, Any] | None]] = [
        ("sidecar_start", start_ns, None),
        ("prompt_accepted", int(prompt["observed_at_ns"]), prompt),
    ]
    if whisper_matches or text_matches or initial_vae_matches:
        require(
            len(whisper_matches) == len(text_matches) == len(initial_vae_matches) == 1,
            "cold conditioning markers are incomplete or duplicated",
        )
        boundaries.extend(
            [
                ("whisper_requested", int(whisper_matches[0]["observed_at_ns"]), whisper_matches[0]),
                ("umt5_requested", int(text_matches[0]["observed_at_ns"]), text_matches[0]),
                ("initial_vae_requested", int(initial_vae_matches[0]["observed_at_ns"]), initial_vae_matches[0]),
                ("humo_requested", int(humo["observed_at_ns"]), humo),
            ]
        )
        names = [
            "runner_boot_and_preflight",
            "prompt_setup",
            "whisper_audio_conditioning",
            "umt5_text_conditioning",
            "initial_vae_conditioning",
            "humo_denoise",
            "vae_decode_and_save",
            "post_prompt_receipt",
        ]
    else:
        boundaries.append(("humo_prepared", int(humo["observed_at_ns"]), humo))
        names = [
            "warm_runner_preflight",
            "cached_conditioning_to_humo",
            "humo_denoise",
            "vae_decode_and_save",
            "post_prompt_receipt",
        ]
    boundaries.extend(
        [
            ("post_sampler_vae_prepared", int(decode["observed_at_ns"]), decode),
            ("prompt_complete", int(complete["observed_at_ns"]), complete),
            ("child_finished", end_ns, None),
        ]
    )
    require(len(names) == len(boundaries) - 1, "phase/boundary count mismatch")
    require(
        all(boundaries[index][1] <= boundaries[index + 1][1] for index in range(len(boundaries) - 1)),
        "server-log phase boundaries are out of order",
    )

    phases = []
    for index, name in enumerate(names):
        start_label, phase_start_ns, start_event = boundaries[index]
        end_label, phase_end_ns, end_event = boundaries[index + 1]
        require(phase_end_ns > phase_start_ns, f"zero/negative phase duration: {name}")
        phase = {
            "phase": name,
            "source_metric": "200 ms nvidia-smi device-total memory.used plus psutil system RAM",
            "start_boundary": {
                "label": start_label,
                "at_ns": phase_start_ns,
            },
            "end_boundary": {
                "label": end_label,
                "at_ns": phase_end_ns,
            },
        }
        if start_event is not None:
            phase["start_boundary"]["event"] = event_ref(
                start_event,
                humo_match if start_event is humo else str(start_event["text"]).strip(),
                "observed",
            )
        if end_event is not None:
            phase["end_boundary"]["event"] = event_ref(
                end_event,
                humo_match if end_event is humo else str(end_event["text"]).strip(),
                "observed",
            )
        phase.update(
            phase_stats(
                samples,
                phase_start_ns,
                phase_end_ns,
                include_end=index == len(names) - 1,
            )
        )
        phases.append(phase)
    return phases


STAGED_RE = re.compile(r"Model (?P<model>\S+) prepared .*? (?P<mb>\d+)MB Staged\.")


def staged_models(telemetry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = {}
    for event in telemetry["server_log"]["events"]:
        match = STAGED_RE.search(str(event.get("text", "")))
        if not match:
            continue
        model = match.group("model")
        size_mb = int(match.group("mb"))
        if model in by_model:
            require(by_model[model]["staged_size_mb"] == size_mb, f"staged size changed for {model}")
            by_model[model]["observation_count"] += 1
            by_model[model]["event_raw_sha256s"].append(event["raw_sha256"])
            continue
        by_model[model] = {
            "model": model,
            "staged_size_mb": size_mb,
            "observation_count": 1,
            "first_observed_at_ns": int(event["observed_at_ns"]),
            "first_observed_at_utc": event["observed_at_utc"],
            "event_raw_sha256s": [event["raw_sha256"]],
        }
    return by_model


def parse_runner_net(status: str) -> float | None:
    match = re.search(r"net VRAM ([0-9]+(?:\.[0-9]+)?) GB", status)
    return float(match.group(1)) if match else None


def validate_lab_run(
    root: Path,
    spec: dict[str, Any],
    refs: dict[str, dict[str, Any]],
    paths: dict[str, Path],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    receipt = read_json(paths[spec["receipt"]])
    telemetry = read_json(paths[spec["telemetry"]])
    require(receipt["receipt_schema_version"] == 3, "unexpected lab receipt schema")
    require(receipt["recipe"] == "humo_1p7b_diet", "unexpected lab recipe")
    require(receipt["run_number"] == spec["run_number"], "lab run number mismatch")
    require(receipt["status"] == spec["expected_status"], "lab run status mismatch")
    require(receipt["warm_pass"] is spec["expected_warm"], "lab warm status mismatch")
    require(receipt["gate_pass"] is spec["expected_gate_pass"], "lab gate mismatch")
    require(receipt["valid_measurement"] is True, "invalid lab measurement")
    require(receipt["clamp_target_gib"] == spec["clamp_target_gib"], "clamp mismatch")
    require(receipt["requires_human_eyeball"] is True, "human gate missing")
    require(receipt["eyeball"] == "pending", "human result must remain pending")
    require(receipt["promotion_ready"] is False, "pending-human run cannot promote")
    require("no-pinned" in receipt["boot_lane"], "no-pinned boot lane missing")

    require(telemetry["kind"] == "humo-diet-phase1-telemetry", "unexpected telemetry kind")
    require(telemetry["status"] == "ok", "telemetry did not close cleanly")
    require(telemetry["child_returncode"] == 0, "runner child failed")
    require(not telemetry["errors"], "sidecar reported errors")
    require(not telemetry["sampler"]["coverage_errors"], "telemetry coverage errors")
    require(telemetry["sampler"]["sample_error_count"] == 0, "telemetry sample errors")
    require(telemetry["run_binding"]["alias_byte_matches_archive"] is True, "alias/archive mismatch")
    archive = telemetry["run_binding"]["new_archive"]
    require(archive["sha256"] == refs[spec["receipt"]]["sha256"], "receipt/telemetry SHA mismatch")
    require(archive["bytes"] == refs[spec["receipt"]]["bytes"], "receipt/telemetry byte mismatch")
    bound_receipt = telemetry["run_binding"]["archive_receipt"]
    require(bound_receipt["run_number"] == receipt["run_number"], "bound run number mismatch")
    require(bound_receipt["status"] == receipt["status"], "bound status mismatch")
    require(bound_receipt["artifact_sha256"] == receipt["artifact_sha256"], "bound artifact mismatch")
    require(telemetry["command"]["recipe_sha256"] == receipt["recipe_sha256"], "recipe SHA mismatch")
    require(telemetry["command"]["runner_sha256"] == receipt["runner_sha256"], "runner SHA mismatch")

    artifact_ref = refs[spec["artifact"]]
    require(receipt["output_path"] == Path(artifact_ref["path"]).name, "lab output path mismatch")
    require(receipt["artifact_sha256"] == artifact_ref["sha256"], "lab artifact SHA mismatch")
    require(receipt["artifact_bytes"] == artifact_ref["bytes"], "lab artifact byte mismatch")
    require(
        telemetry["run_binding"]["artifact"]["sha256"] == artifact_ref["sha256"],
        "telemetry artifact SHA mismatch",
    )

    samples = telemetry["sampler"]["samples"]
    recomputed_peak_mib = max(float(row["vram_used_mib"]) for row in samples)
    require(recomputed_peak_mib == float(telemetry["sampler"]["peak_vram_mib"]), "peak drift")
    require(round(recomputed_peak_mib / 1024.0, 2) == receipt["peak_vram_gb"], "receipt peak drift")
    phases = derive_phases(telemetry)
    phase_peak = max(phase["peak_vram_mib"] for phase in phases)
    require(phase_peak == recomputed_peak_mib, "phase partition lost overall peak")

    runner_net = parse_runner_net(receipt["status"])
    row = {
        "run_id": spec["id"],
        "source_refs": [spec["receipt"], spec["telemetry"], spec["artifact"]],
        "run_number": receipt["run_number"],
        "status": receipt["status"],
        "machine_gate_pass": receipt["gate_pass"],
        "warm_pass": receipt["warm_pass"],
        "human_quality": "PENDING_HUMAN",
        "promotion_ready": False,
        "recipe_sha256": receipt["recipe_sha256"],
        "run_identity_sha256": receipt["run_identity_sha256"],
        "boot_lane": receipt["boot_lane"],
        "server_argv": receipt["server_argv"],
        "fixture_sha256s": receipt["fixture_sha256s"],
        "receipt_metrics": {
            "source_ref": spec["receipt"],
            "baseline_vram_gib": receipt["baseline_vram_gb"],
            "peak_vram_gib": receipt["peak_vram_gb"],
            "runner_reported_net_vram_gib": runner_net,
            "clamp_target_gib": receipt["clamp_target_gib"],
            "reserve_vram_gib": receipt["reserve_vram_gib"],
            "physical_total_vram_gib": receipt["physical_total_vram_gib"],
            "baseline_host_ram_gib": receipt["baseline_host_ram_gb"],
            "peak_host_ram_gib": receipt["peak_host_ram_gb"],
            "render_duration_s": receipt["duration_s"],
            "container_duration_s": receipt["container_duration_s"],
            "encoded_frame_count": receipt["encoded_frame_count"],
            "encoded_fps": receipt["encoded_fps"],
            "encoded_width": receipt["encoded_width"],
            "encoded_height": receipt["encoded_height"],
        },
        "sidecar_metrics": {
            "source_ref": spec["telemetry"],
            "sample_interval_s": telemetry["sampler"]["interval_s"],
            "sample_count": telemetry["sampler"]["sample_count"],
            "baseline_before_child_vram_mib": telemetry["sampler"]["baseline_vram_mib"],
            "peak_vram_mib": telemetry["sampler"]["peak_vram_mib"],
            "peak_vram_gib": round(float(telemetry["sampler"]["peak_vram_mib"]) / 1024.0, 6),
            "peak_host_ram_bytes": telemetry["sampler"]["peak_host_ram_bytes"],
            "peak_host_ram_gib": round(
                int(telemetry["sampler"]["peak_host_ram_bytes"]) / (1024.0**3), 6
            ),
            "child_duration_s": telemetry["child_duration_s"],
            "largest_coverage_gap_s": telemetry["sampler"]["largest_coverage_gap_s"],
            "server_log_new_bytes_sha256": telemetry["server_log"]["new_bytes_sha256"],
            "server_log_event_count": telemetry["server_log"]["event_count"],
        },
        "phase_analysis": {
            "source_ref": spec["telemetry"],
            "boundary_rule": (
                "Half-open windows use first-observed complete server-log records; the final window "
                "includes child end. Log timestamps are observation times, not claimed causal timestamps."
            ),
            "phases": phases,
        },
        "artifact": artifact_ref,
    }
    return row, receipt, telemetry


def validate_production_run(
    spec: dict[str, Any], refs: dict[str, dict[str, Any]], paths: dict[str, Path]
) -> dict[str, Any]:
    receipt = read_json(paths[spec["receipt"]])
    require(receipt["measured"] == "otr-side production lane", "wrong production scope")
    require(receipt["lab_gate_evaluated"] is False, "OTR comparator cannot claim lab gate")
    require(receipt["valid_measurement"] is True, "invalid production measurement")
    require(receipt["human_verdicts"] == {
        "identity": "PENDING_HUMAN",
        "lips": "PENDING_HUMAN",
        "onset": "PENDING_HUMAN",
    }, "production human verdict changed")
    require(receipt["fixture_sha256s"] == {
        "portrait.png": PORTRAIT_SHA256,
        "tts_dialogue.wav": TTS_SHA256,
    }, "production fixture mismatch")
    require(receipt["monitor"]["telemetry_sha256"] == refs[spec["telemetry"]]["sha256"], "production telemetry SHA mismatch")
    artifact_ref = refs[spec["artifact"]]
    require(receipt["output_path"] == Path(artifact_ref["path"]).name, "production output mismatch")
    require(receipt["artifact_sha256"] == artifact_ref["sha256"], "production artifact SHA mismatch")
    require(receipt["artifact_bytes"] == artifact_ref["bytes"], "production artifact byte mismatch")
    return {
        "run_id": spec["id"],
        "source_refs": [spec["receipt"], spec["telemetry"], spec["artifact"]],
        "measurement_scope": receipt["measured"],
        "status": receipt["status"],
        "human_quality": "PENDING_HUMAN",
        "boot_lane": receipt["boot_lane"],
        "fixture_sha256s": receipt["fixture_sha256s"],
        "metrics": {
            "source_ref": spec["receipt"],
            "baseline_vram_gib": receipt["baseline_vram_gb"],
            "peak_vram_gib": receipt["peak_vram_gb"],
            "baseline_host_ram_gib": receipt["baseline_host_ram_gb"],
            "peak_host_ram_gib": receipt["peak_host_ram_gb"],
            "render_duration_s": receipt["duration_s"],
            "container_duration_s": receipt["container_duration_s"],
            "encoded_frame_count": receipt["encoded_frame_count"],
            "encoded_fps": receipt["encoded_fps"],
            "encoded_width": receipt["encoded_width"],
            "encoded_height": receipt["encoded_height"],
            "telemetry_sample_interval_s": receipt["monitor"]["interval_s"],
            "telemetry_sample_count": receipt["monitor"]["sample_count"],
        },
        "artifact": artifact_ref,
    }


def ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    require(executable is not None, "ffprobe is required to bind the A/B media contract")
    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    require(completed.returncode == 0, f"ffprobe failed: {completed.stderr.strip()}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid ffprobe JSON: {exc}") from exc
    video = [stream for stream in payload["streams"] if stream["codec_type"] == "video"]
    audio = [stream for stream in payload["streams"] if stream["codec_type"] == "audio"]
    require(len(video) == len(audio) == 1, "A/B package must have one video and one audio stream")
    return {"video": video[0], "audio": audio[0], "format": payload["format"]}


def build_ab_package(refs: dict[str, dict[str, Any]], paths: dict[str, Path]) -> dict[str, Any]:
    probe = ffprobe(paths["ab_review_artifact"])
    video = probe["video"]
    audio = probe["audio"]
    require(video["codec_name"] == "h264", "unexpected A/B video codec")
    require((int(video["width"]), int(video["height"])) == (960, 832), "unexpected A/B canvas")
    require(video["r_frame_rate"] == "25/1", "unexpected A/B frame rate")
    require(int(video["nb_frames"]) == 129, "unexpected A/B frame count")
    require(float(video["duration"]) == 5.16, "unexpected A/B video duration")
    require(audio["codec_name"] == "aac", "unexpected A/B audio codec")
    require(int(audio["sample_rate"]) == 44100, "unexpected A/B sample rate")
    require(int(audio["channels"]) == 1, "unexpected A/B channel count")
    require(float(audio["duration"]) == 5.16, "unexpected A/B audio duration")
    require(float(probe["format"]["duration"]) == 5.16, "unexpected A/B container duration")
    require(int(probe["format"]["size"]) == refs["ab_review_artifact"]["bytes"], "A/B size drift")
    return {
        "purpose": "PENDING_HUMAN quality-parity review only",
        "policy": (
            "Video A is the OTR production review mux; video B is the lab clamp-13 warm output. "
            "The exact raw TTS fixture is re-encoded once as shared mono AAC for onset/lip judgment. "
            "This is not model evidence or a promotion artifact."
        ),
        "source_refs": [
            "production_take1_artifact",
            "lab_clamp13_warm_artifact",
            "tts_fixture",
            "ab_review_artifact",
        ],
        "assembly_argv": AB_FFMPEG_ARGV,
        "artifact": refs["ab_review_artifact"],
        "probe": {
            "source_ref": "ab_review_artifact",
            "video_codec": video["codec_name"],
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": 25.0,
            "frame_count": int(video["nb_frames"]),
            "video_duration_s": float(video["duration"]),
            "audio_codec": audio["codec_name"],
            "audio_sample_rate_hz": int(audio["sample_rate"]),
            "audio_channels": int(audio["channels"]),
            "audio_duration_s": float(audio["duration"]),
            "container_duration_s": float(probe["format"]["duration"]),
        },
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    refs, paths = load_pinned_sources(root)
    phase0 = read_json(paths["phase0"])
    require(phase0["status"] == "PASS", "Phase 0 did not pass")
    require(phase0["no_prompt_submitted"] is True, "Phase 0 unexpectedly rendered")
    require(not phase0["missing_classes"], "Phase 0 class set incomplete")
    require(phase0["whisper_listed"] is True, "Phase 0 Whisper model missing")
    require(phase0["shutdown_proof"]["success"] is True, "Phase 0 server cleanup incomplete")

    lab_rows: list[dict[str, Any]] = []
    lab_receipts: dict[str, dict[str, Any]] = {}
    lab_telemetry: dict[str, dict[str, Any]] = {}
    for spec in LAB_RUNS:
        row, receipt, telemetry = validate_lab_run(root, spec, refs, paths)
        lab_rows.append(row)
        lab_receipts[spec["id"]] = receipt
        lab_telemetry[spec["id"]] = telemetry

    recipe_shas = {row["recipe_sha256"] for row in lab_rows}
    require(len(recipe_shas) == 1, "Phase-1 recipe changed across runs")
    require(
        lab_rows[0]["run_identity_sha256"] == lab_rows[1]["run_identity_sha256"],
        "clamp-13 cold/warm identities differ",
    )
    require(
        lab_receipts["clamp13_warm"]["pass"] is True
        and lab_receipts["clamp13_warm"]["peak_vram_gb"] <= 13.5,
        "clamp-13 warm run is not the machine winner",
    )
    require(lab_receipts["clamp12_cold"]["pass"] is False, "clamp-12 failure truth changed")

    production_rows = [validate_production_run(spec, refs, paths) for spec in PRODUCTION_RUNS]
    for row in lab_rows:
        require(row["fixture_sha256s"] == {
            "portrait.png": PORTRAIT_SHA256,
            "tts_dialogue.wav": TTS_SHA256,
        }, "lab fixture parity failed")

    cold_stage_tables = {
        run_id: staged_models(lab_telemetry[run_id])
        for run_id in ("clamp13_cold", "clamp12_cold")
    }
    required_stages = {
        "WhisperLargeV3": 1214,
        "WanTEModel": 6419,
        "WanVAE": 241,
        "WAN21_HuMo": 3320,
    }
    for run_id, table in cold_stage_tables.items():
        require(
            {name: table[name]["staged_size_mb"] for name in required_stages} == required_stages,
            f"staged model sizes changed in {run_id}",
        )
    weight_hog = max(required_stages, key=required_stages.get)
    require(weight_hog == "WanTEModel", "unexpected largest staged model")

    by_id = {row["run_id"]: row for row in lab_rows}
    warm = by_id["clamp13_warm"]
    failed = by_id["clamp12_cold"]
    production_peaks = [float(row["metrics"]["peak_vram_gib"]) for row in production_rows]
    warm_peak = float(warm["receipt_metrics"]["peak_vram_gib"])
    staged_evidence = []
    for run_id, source_ref in (
        ("clamp13_cold", "lab_clamp13_cold_telemetry"),
        ("clamp12_cold", "lab_clamp12_cold_telemetry"),
    ):
        staged_evidence.append(
            {
                "run_id": run_id,
                "source_ref": source_ref,
                "models": cold_stage_tables[run_id],
            }
        )

    return {
        "comparison": "humo_1p7b_vram_diet_phase1_clamp_floor",
        "schema_version": 1,
        "measurement_scope": (
            "Local lab Phase-0 schema check plus three immutable Phase-1 runs, their independent "
            "200 ms sidecars, and two OTR-side production comparator receipts."
        ),
        "numeric_provenance_policy": (
            "Receipt metrics cite a pinned receipt source_ref; phase metrics are recomputed from the "
            "pinned telemetry source_ref; media metrics come from ffprobe of a hash-pinned artifact."
        ),
        "source_refs": refs,
        "phase0": {
            "source_ref": "phase0",
            "status": phase0["status"],
            "measured": phase0["measured"],
            "required_class_count": phase0["required_class_count"],
            "missing_class_count": len(phase0["missing_classes"]),
            "whisper_listed": phase0["whisper_listed"],
            "no_prompt_submitted": phase0["no_prompt_submitted"],
            "server_shutdown_proved": phase0["shutdown_proof"]["success"],
        },
        "controls": {
            "source_refs": [
                "lab_clamp13_cold_receipt",
                "lab_clamp13_warm_receipt",
                "lab_clamp12_cold_receipt",
            ],
            "same_recipe_sha256_all_lab_runs": next(iter(recipe_shas)),
            "clamp13_same_server_identity": True,
            "graph_change_count": 0,
            "single_changed_variable": "boot-lane target-card budget: clamp-13 then clamp-12",
            "fixture_sha256s": {
                "portrait.png": PORTRAIT_SHA256,
                "tts_dialogue.wav": TTS_SHA256,
            },
            "canvas": {"width": 480, "height": 832, "frames": 129, "fps": 25.0},
            "human_quality_gate": "PENDING_HUMAN",
        },
        "lab_runs": lab_rows,
        "production_comparators": production_rows,
        "memory_hog_finding": {
            "staged_model_evidence": staged_evidence,
            "largest_staged_weight_component": {
                "model": "WanTEModel (UMT5 text encoder)",
                "staged_size_mb_as_logged": 6419,
                "humo_dit_staged_size_mb_as_logged": 3320,
                "size_ratio_vs_humo_dit": round(6419 / 3320, 6),
                "interpretation": (
                    "WanTEModel/UMT5 is the largest single staged weight payload and is 1.93x the "
                    "logged HuMo DiT size. The logged MB values are staging reports, not direct "
                    "device-residency measurements."
                ),
            },
            "observed_peak_phases": {
                row["run_id"]: max(
                    row["phase_analysis"]["phases"], key=lambda phase: phase["peak_vram_mib"]
                )["phase"]
                for row in lab_rows
            },
            "conclusion": (
                "The static weight hog is WanTEModel/UMT5, but it is not by itself the observed peak "
                "phase. Both cold runs peak during HuMo denoising; the warm winner peaks during VAE "
                "decode. The defensible diagnosis is combined dynamic pipeline/working-set pressure, "
                "not the 3.32 GB logged DiT stage alone. These observations do not prove that UMT5 "
                "weights remain GPU-resident during denoising."
            ),
        },
        "machine_verdict": {
            "phase1_winner": "clamp13_warm",
            "winner_source_refs": warm["source_refs"],
            "comparison_source_refs": [
                "production_take1_receipt",
                "production_take1_telemetry",
                "production_take1_artifact",
                "production_take2_receipt",
                "production_take2_telemetry",
                "production_take2_artifact",
            ],
            "metric_sources": {
                "winner_peak_and_gate": "lab_clamp13_warm_receipt",
                "winner_exact_200ms_curve": "lab_clamp13_warm_telemetry",
                "production_peak_range": [
                    "production_take1_receipt",
                    "production_take2_receipt",
                ],
            },
            "result": "ZERO_GRAPH_CHANGE_MACHINE_WINNER",
            "warm_gate_pass": True,
            "absolute_peak_vram_gib": warm_peak,
            "diet_target_peak_vram_gib": 13.5,
            "diet_target_headroom_gib": round(13.5 - warm_peak, 2),
            "global_gate_peak_vram_gib": 14.5,
            "global_gate_headroom_gib": round(14.5 - warm_peak, 2),
            "production_unclamped_peak_range_gib": [min(production_peaks), max(production_peaks)],
            "reduction_vs_production_range_gib": [
                round(min(production_peaks) - warm_peak, 6),
                round(max(production_peaks) - warm_peak, 6),
            ],
            "human_quality": "PENDING_HUMAN",
            "promotion_ready": False,
            "qualification": (
                "Machine VRAM and warm-cache requirements pass at clamp-13. Full quality parity and "
                "promotion remain blocked on Jeffrey's A/B judgment."
            ),
        },
        "clamp12_stop": {
            "source_refs": failed["source_refs"],
            "status": failed["status"],
            "cold_run_only": True,
            "absolute_peak_vram_gib": failed["receipt_metrics"]["peak_vram_gib"],
            "runner_reported_net_vram_gib": failed["receipt_metrics"]["runner_reported_net_vram_gib"],
            "clamp_target_gib": failed["receipt_metrics"]["clamp_target_gib"],
            "disposition": (
                "STOP_NO_FORCE: the cold run failed the clamp-12 net gate; no identical forced warm "
                "retry is evidence-authorized. This does not invalidate the clamp-13 warm winner."
            ),
        },
        "ab_review_package": build_ab_package(refs, paths),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail unless the committed output is exact")
    parser.add_argument("--root", type=Path, default=ROOT, help="lab repository root")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = root / OUTPUT
    try:
        payload = canonical_json_bytes(build(root))
    except EvidenceError as exc:
        print(f"[humo-diet-evidence] FAIL: {exc}", file=sys.stderr)
        return 1
    if args.check:
        if not output.is_file() or output.read_bytes() != payload:
            print(f"[humo-diet-evidence] FAIL: stale or missing {output}", file=sys.stderr)
            return 1
        print(f"[humo-diet-evidence] PASS: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_bytes() != payload:
        output.write_bytes(payload)
    print(f"[humo-diet-evidence] wrote {output} sha256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
