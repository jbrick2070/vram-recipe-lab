#!/usr/bin/env python3
"""Bind and package the HuMo 14B diet envelope evidence, entirely offline.

This reducer never boots or queries ComfyUI and never edits immutable runner
receipts.  It validates the two cold/warm recipe pairs, their artifacts, the
OTR-side production comparator, and the exact fixture bytes.  The optional A/B
assembly maps only the two source *video* streams and one shared raw TTS input,
so neither source clip's embedded audio can affect the review soundtrack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("results/humo_diet/humo_14b_diet_envelope.json")
AB_OUTPUT = Path("outputs/humo_14b_diet_ab_production_vs_reserve2p921_warm.mp4")

PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
TTS_SHA256 = "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
PRODUCTION_RECEIPT_SHA256 = (
    "ed53c2249b3a23d64bf6b2e06833aef9d7a787c8ae8a05ccd2f915ccfb2d5938"
)
PRODUCTION_ARTIFACT_SHA256 = (
    "796ca4b15b1bd44eb0860ccbe192854f970962986ac0710bfaa04d643c801de0"
)
EXPECTED_FIXTURES = {
    "portrait.png": PORTRAIT_SHA256,
    "tts_dialogue.wav": TTS_SHA256,
}

PRODUCTION_RECEIPT = Path("results/otr_side/humo_14b_fp8_bakeoff_take1.json")
PRODUCTION_ARTIFACT = Path("outputs/humo_14b_fp8_bakeoff_take1.mp4")
PORTRAIT_RUN2_RECOVERY = Path(
    "results/humo_diet/humo_14b_diet_portrait_480x832_f97_run2_recovery.json"
)
PORTRAIT_RUN2_RECOVERY_SHA256 = (
    "bfdd829c766562c8e85d1799ea5c4206ef5c4911ad40b31f443a51af20b4019d"
)
PORTRAIT_RUN2_RECEIPT_SHA256 = (
    "87ddd92834a1ba14544c102623407f8a849ebaa9007a51b11192abe92a19a234"
)
PORTRAIT_FIXTURE = Path("fixtures/portrait.png")
TTS_FIXTURE = Path("fixtures/tts_dialogue.wav")

EXPECTED_BOOT_LANE = "lab-8199, sage-free, no-pinned, reserve-2.921gb"
EXPECTED_RESERVE_GIB = 2.921
GLOBAL_GATE_GIB = 14.5
EXPECTED_FRESH_NODES = {"13", "14", "15", "16"}
EXPECTED_STABLE_NODES = {str(index) for index in range(1, 13)}

RUN_SPECS: dict[str, dict[str, Any]] = {
    "portrait": {
        "recipe": "humo_14b_diet_portrait_480x832_f97",
        "recipe_path": Path("recipes/humo_14b_diet_portrait_480x832_f97.json"),
        "recipe_sha256": "ed4db54cb792733c87a09eeb75fb55d19364422305694bd19768e2a5c11a69c9",
        "engine_id": "humo",
        "width": 480,
        "height": 832,
    },
    "landscape": {
        "recipe": "humo_14b_diet_landscape_832x480_f97",
        "recipe_path": Path("recipes/humo_14b_diet_landscape_832x480_f97.json"),
        "recipe_sha256": "af27ea377c55129ed2400ac63c1cfd6d92a0732e6226f53cb1858c3a8802d232",
        "engine_id": "humo_14B_169",
        "width": 832,
        "height": 480,
    },
}


class EvidenceError(RuntimeError):
    """A required source or evidence relationship did not validate."""


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
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(not raw.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid UTF-8 JSON {path}: {exc}") from exc
    require(isinstance(payload, dict), f"expected JSON object: {path}")
    return payload


def relative_ref(root: Path, path: Path) -> dict[str, Any]:
    path = path.resolve()
    require(path.is_file(), f"missing evidence source: {path}")
    try:
        relative = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise EvidenceError(f"evidence source escapes lab root: {path}") from exc
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def require_pinned(root: Path, relative: Path, expected_sha256: str) -> dict[str, Any]:
    ref = relative_ref(root, root / relative)
    require(
        ref["sha256"] == expected_sha256,
        f"pinned source changed for {relative}: expected {expected_sha256}, got {ref['sha256']}",
    )
    return ref


def ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    require(executable is not None, "ffprobe is required for media binding")
    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size:stream=index,codec_type,codec_name,width,height,"
            "r_frame_rate,nb_frames,duration,sample_rate,channels"
        ),
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    require(completed.returncode == 0, f"ffprobe failed: {completed.stderr.strip()}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid ffprobe JSON for {path}: {exc}") from exc
    require(isinstance(payload, dict), f"unexpected ffprobe payload for {path}")
    return payload


def one_stream(probe: dict[str, Any], kind: str) -> dict[str, Any]:
    streams = [row for row in probe.get("streams", []) if row.get("codec_type") == kind]
    require(len(streams) == 1, f"expected exactly one {kind} stream")
    return streams[0]


def as_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid numeric {label}: {value!r}") from exc


def probe_video_contract(
    path: Path, *, width: int, height: int, frames: int = 97, duration_s: float = 3.88
) -> dict[str, Any]:
    probe = ffprobe(path)
    video = one_stream(probe, "video")
    audio = one_stream(probe, "audio")
    require(video["codec_name"] == "h264", f"unexpected video codec: {path}")
    require(
        (int(video["width"]), int(video["height"])) == (width, height),
        f"unexpected canvas: {path}",
    )
    require(video["r_frame_rate"] == "25/1", f"unexpected frame rate: {path}")
    require(int(video["nb_frames"]) == frames, f"unexpected frame count: {path}")
    require(
        abs(as_float(video["duration"], "video duration") - duration_s) <= 0.001,
        f"unexpected video duration: {path}",
    )
    require(audio["codec_name"] == "aac", f"unexpected audio codec: {path}")
    require(
        abs(as_float(audio["duration"], "audio duration") - duration_s) <= 0.01,
        f"unexpected audio duration: {path}",
    )
    require(
        int(probe["format"]["size"]) == path.stat().st_size,
        f"ffprobe size disagrees with filesystem: {path}",
    )
    return {
        "video_codec": video["codec_name"],
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": 25.0,
        "frame_count": int(video["nb_frames"]),
        "video_duration_s": as_float(video["duration"], "video duration"),
        "audio_codec": audio["codec_name"],
        "audio_sample_rate_hz": int(audio["sample_rate"]),
        "audio_channels": int(audio["channels"]),
        "audio_duration_s": as_float(audio["duration"], "audio duration"),
        "container_duration_s": as_float(probe["format"]["duration"], "container duration"),
    }


def argv_value(argv: list[Any], flag: str) -> str:
    require(flag in argv, f"server argv is missing {flag}")
    index = argv.index(flag)
    require(index + 1 < len(argv), f"server argv has no value after {flag}")
    return str(argv[index + 1])


def run_receipt_path(spec: dict[str, Any], run_number: int) -> Path:
    return Path("results") / f"{spec['recipe']}_run{run_number}.json"


def validate_run(
    root: Path, orientation: str, run_number: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = RUN_SPECS[orientation]
    receipt_relative = run_receipt_path(spec, run_number)
    receipt_path = root / receipt_relative
    receipt_ref = relative_ref(root, receipt_path)
    receipt = read_json(receipt_path)

    require(receipt.get("receipt_schema_version") == 3, "unexpected lab receipt schema")
    require(receipt.get("recipe") == spec["recipe"], "recipe identity mismatch")
    require(receipt.get("recipe_sha256") == spec["recipe_sha256"], "recipe SHA mismatch")
    require(receipt.get("run_number") == run_number, "run number mismatch")
    require(receipt.get("config_run_count") == run_number, "config run count mismatch")
    require(receipt.get("run_count") == run_number, "run count mismatch")
    require(receipt.get("accepted_prompt") is True, "prompt was not accepted")
    require(receipt.get("valid_measurement") is True, "invalid lab measurement")
    require(receipt.get("provenance_unchanged") is True, "provenance changed")
    require(receipt.get("fixture_sha256s") == EXPECTED_FIXTURES, "fixture parity failed")
    require(receipt.get("boot_lane") == EXPECTED_BOOT_LANE, "diet boot lane mismatch")
    require(receipt.get("reserve_vram_gib") == EXPECTED_RESERVE_GIB, "reserve mismatch")
    require(receipt.get("clamp_target_gib") is None, "direct reserve run became clamp run")
    require(receipt.get("requires_human_eyeball") is True, "human gate missing")
    require(receipt.get("eyeball") == "pending", "receipt pre-judges human quality")
    require(receipt.get("promotion_ready") is False, "pending-human run cannot promote")
    require(receipt.get("encoded_width") == spec["width"], "encoded width mismatch")
    require(receipt.get("encoded_height") == spec["height"], "encoded height mismatch")
    require(receipt.get("encoded_frame_count") == 97, "encoded frame count mismatch")
    require(receipt.get("encoded_fps") == 25.0, "encoded fps mismatch")
    require(abs(float(receipt.get("video_duration_s")) - 3.88) <= 0.001, "video duration mismatch")
    require(receipt.get("audio_present") is True, "review audio is absent")

    server_argv = list(receipt.get("server_argv", []))
    require(argv_value(server_argv, "--port") == "8199", "wrong lab port")
    require(
        argv_value(server_argv, "--reserve-vram") == "2.921",
        "live reserve argv mismatch",
    )
    require("--disable-pinned-memory" in server_argv, "no-pinned argv missing")
    require("--use-sage-attention" not in server_argv, "global Sage flag is forbidden")

    cache = receipt.get("execution_cache_control", {})
    role = "cold" if run_number == 1 else "warm"
    expected_nonce = f"job-a-{spec['recipe']}-{role}"
    require(cache.get("nonce") == expected_nonce, "executor cache nonce mismatch")
    require(cache.get("recipe_seed") == 7, "seed mismatch")
    require(cache.get("source_node_id") == "13", "sampler source mismatch")
    require(cache.get("cache_event_found") is True, "cache event missing")
    require(cache.get("fresh_execution_proved") is True, "fresh execution unproved")
    require(set(cache.get("fresh_node_ids", [])) == EXPECTED_FRESH_NODES, "fresh closure mismatch")
    require(set(cache.get("stable_node_ids", [])) == EXPECTED_STABLE_NODES, "stable closure mismatch")
    require(cache.get("cached_fresh_node_ids") == [], "fresh nodes were cached")
    if run_number == 1:
        require(cache.get("cached_node_ids") == [], "cold run unexpectedly cached nodes")
        require(receipt.get("warm_pass") is False, "cold run cannot be warm pass")
        require(receipt.get("pass") is False, "cold run cannot be promotion pass")
    else:
        require(
            set(cache.get("cached_node_ids", [])) == EXPECTED_STABLE_NODES,
            "warm run did not cache every stable node",
        )

    expected_output = f"{spec['recipe']}_out_{run_number:05d}_.mp4"
    require(receipt.get("output_path") == expected_output, "output identity mismatch")
    artifact_path = (root / "outputs" / expected_output).resolve()
    require(artifact_path.parent == (root / "outputs").resolve(), "output escaped outputs directory")
    artifact_ref = relative_ref(root, artifact_path)
    require(receipt.get("artifact_sha256") == artifact_ref["sha256"], "artifact SHA mismatch")
    require(receipt.get("artifact_bytes") == artifact_ref["bytes"], "artifact byte mismatch")
    probe = probe_video_contract(
        artifact_path, width=spec["width"], height=spec["height"]
    )

    row = {
        "role": role,
        "source_refs": {
            "receipt": receipt_ref,
            "artifact": artifact_ref,
        },
        "run_number": run_number,
        "config_run_count": receipt["config_run_count"],
        "status": receipt["status"],
        "valid_measurement": receipt["valid_measurement"],
        "gate_pass": receipt["gate_pass"],
        "warm_pass": receipt["warm_pass"],
        "promotion_pass": receipt["pass"],
        "marginal": receipt["marginal"],
        "human_quality": "PENDING_HUMAN",
        "recipe_sha256": receipt["recipe_sha256"],
        "run_identity_sha256": receipt["run_identity_sha256"],
        "boot_lane": receipt["boot_lane"],
        "server_argv": receipt["server_argv"],
        "server_instance": receipt["server_instance"],
        "executor_cache_nonce": cache["nonce"],
        "metrics": {
            "numeric_source": receipt_ref["path"],
            "baseline_vram_gib": receipt["baseline_vram_gb"],
            "peak_vram_gib": receipt["peak_vram_gb"],
            "baseline_host_ram_gib": receipt["baseline_host_ram_gb"],
            "peak_host_ram_gib": receipt["peak_host_ram_gb"],
            "wall_time_s": receipt["duration_s"],
            "container_duration_s": receipt["container_duration_s"],
        },
        "media_probe": probe,
    }
    return row, receipt


def validate_pair(root: Path, orientation: str) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = RUN_SPECS[orientation]
    recipe_ref = require_pinned(root, spec["recipe_path"], spec["recipe_sha256"])
    cold, cold_receipt = validate_run(root, orientation, 1)
    warm, warm_receipt = validate_run(root, orientation, 2)
    require(cold["recipe_sha256"] == warm["recipe_sha256"], "recipe changed across pair")
    require(cold["run_identity_sha256"] == warm["run_identity_sha256"], "run identity changed")
    require(cold["server_instance"] == warm["server_instance"], "cold/warm server changed")
    require(cold["server_argv"] == warm["server_argv"], "cold/warm server argv changed")
    require(warm_receipt.get("server_instance_unchanged") is True, "warm server continuity unproved")

    peak = float(warm["metrics"]["peak_vram_gib"])
    vram_fit = peak <= GLOBAL_GATE_GIB
    return {
        "orientation": orientation,
        "engine_id": spec["engine_id"],
        "recipe": spec["recipe"],
        "recipe_source": recipe_ref,
        "canvas": {
            "width": spec["width"],
            "height": spec["height"],
            "frames": 97,
            "fps": 25.0,
            "duration_s": 3.88,
        },
        "controls": {
            "seed": 7,
            "same_recipe_sha256": spec["recipe_sha256"],
            "same_owned_server": True,
            "unique_executor_nonce_per_leg": True,
            "fixture_sha256s": EXPECTED_FIXTURES,
            "direct_reserve_vram_gib": EXPECTED_RESERVE_GIB,
            "disable_pinned_memory": True,
        },
        "runs": [cold, warm],
        "warm_vram_verdict": {
            "numeric_source": warm["source_refs"]["receipt"]["path"],
            "peak_vram_gib": peak,
            "gate_gib": GLOBAL_GATE_GIB,
            "fits_under_14p5": vram_fit,
            "headroom_gib": round(GLOBAL_GATE_GIB - peak, 6),
            "lab_gate_pass": warm["gate_pass"],
            "warm_machine_pass": warm["warm_pass"],
            "marginal": warm["marginal"],
            "plain_answer": (
                f"YES: warm {orientation} peak {peak:.2f} GiB is at or below 14.5 GiB."
                if vram_fit
                else f"NO: warm {orientation} peak {peak:.2f} GiB exceeds 14.5 GiB."
            ),
        },
    }, warm_receipt


def validate_production(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_ref = require_pinned(root, PRODUCTION_RECEIPT, PRODUCTION_RECEIPT_SHA256)
    artifact_ref = require_pinned(root, PRODUCTION_ARTIFACT, PRODUCTION_ARTIFACT_SHA256)
    receipt = read_json(root / PRODUCTION_RECEIPT)
    require(receipt.get("measured") == "otr-side production lane", "wrong comparator scope")
    require(receipt.get("lab_gate_evaluated") is False, "OTR receipt cannot claim lab gate")
    require(receipt.get("engine") == "humo", "wrong production engine")
    require(receipt.get("seed_effective") == 7, "production seed mismatch")
    require(receipt.get("fixture_sha256s") == EXPECTED_FIXTURES, "production fixture mismatch")
    require(receipt.get("output_path") == PRODUCTION_ARTIFACT.name, "production path mismatch")
    require(receipt.get("artifact_sha256") == artifact_ref["sha256"], "production SHA mismatch")
    require(receipt.get("artifact_bytes") == artifact_ref["bytes"], "production bytes mismatch")
    probe = probe_video_contract(root / PRODUCTION_ARTIFACT, width=480, height=832)
    return {
        "measurement_scope": receipt["measured"],
        "source_refs": {"receipt": receipt_ref, "artifact": artifact_ref},
        "seed": receipt["seed_effective"],
        "fixture_sha256s": receipt["fixture_sha256s"],
        "boot_lane": receipt["boot_lane"],
        "metrics": {
            "numeric_source": receipt_ref["path"],
            "baseline_vram_gib": receipt["baseline_vram_gb"],
            "peak_vram_gib": receipt["peak_vram_gb"],
            "peak_host_ram_gib": receipt["peak_host_ram_gb"],
            "wall_time_s": receipt["duration_s"],
        },
        "media_probe": probe,
    }, receipt


def validate_portrait_run2_recovery(
    root: Path, warm_receipt: dict[str, Any]
) -> dict[str, Any]:
    recovery_ref = require_pinned(
        root, PORTRAIT_RUN2_RECOVERY, PORTRAIT_RUN2_RECOVERY_SHA256
    )
    recovery = read_json(root / PORTRAIT_RUN2_RECOVERY)
    require(recovery.get("receipt_schema_version") == 1, "unexpected recovery schema")
    require(
        recovery.get("receipt_kind") == "manual-runtime-cleanup-recovery",
        "unexpected recovery kind",
    )
    require(recovery.get("success") is True, "manual cleanup recovery did not succeed")

    associated = recovery.get("associated_run", {})
    warm_path = run_receipt_path(RUN_SPECS["portrait"], 2).as_posix()
    require(associated.get("receipt") == warm_path, "recovery binds wrong run receipt")
    require(
        associated.get("receipt_sha256") == PORTRAIT_RUN2_RECEIPT_SHA256,
        "recovery run-receipt SHA mismatch",
    )
    require(
        sha256_file(root / warm_path) == PORTRAIT_RUN2_RECEIPT_SHA256,
        "portrait run-2 receipt changed after recovery",
    )
    require(
        associated.get("artifact") == f"outputs/{warm_receipt['output_path']}",
        "recovery binds wrong warm artifact",
    )
    require(
        associated.get("artifact_sha256") == warm_receipt.get("artifact_sha256"),
        "recovery artifact SHA mismatch",
    )

    owner = recovery.get("dead_gpu_owner", {})
    require(owner.get("role") == "standalone", "recovered wrong lease role")
    require(owner.get("process_identity_live_before_recovery") is False, "lease owner was not proved dead")
    require(isinstance(owner.get("nonce"), str) and len(owner["nonce"]) == 64, "invalid recovered lease nonce")

    guards = recovery.get("recovery_guards", {})
    require(guards.get("os_coordinator_acquired_nonblocking") is True, "OS coordinator proof missing")
    require(
        guards.get("gpu_receipt_unlinked_only_after_exact_nonce_and_owner_match") is True,
        "exact nonce/owner unlink proof missing",
    )
    require(guards.get("foreign_server_adopted_or_killed") is False, "foreign server was touched")
    require(guards.get("render_or_prompt_submitted") is False, "recovery submitted a prompt")

    shutdown = recovery.get("owned_server_shutdown", {})
    require(
        shutdown.get("pid") == warm_receipt["server_instance"]["serving_pid"],
        "recovery shut down a different server PID",
    )
    for field in (
        "had_receipt",
        "listener_exited",
        "pid_verified",
        "process_exited",
        "receipt_removed",
        "success",
        "termination_attempted",
        "termination_reported_success",
    ):
        require(shutdown.get(field) is True, f"server recovery field is not true: {field}")
    postconditions = recovery.get("postconditions", {})
    require(
        postconditions
        == {
            "gpu_lock_absent": True,
            "suite_lock_absent": True,
            "server_pid_receipt_absent": True,
        },
        "cleanup postconditions are incomplete",
    )
    effect = str(recovery.get("certification_effect", ""))
    require("remains machine evidence" in effect, "recovery loses measurement disposition")
    require("must not be represented as normal runner shutdown proof" in effect, "recovery caveat missing")
    return {
        "source_ref": recovery_ref,
        "status": "RECOVERED_SUCCESSFULLY",
        "normal_runner_shutdown_proved": False,
        "measurement_receipt_status": warm_receipt["status"],
        "measurement_remains_valid": warm_receipt["valid_measurement"],
        "incident": recovery["incident"],
        "certification_effect": effect,
        "dead_gpu_owner": owner,
        "recovery_guards": guards,
        "owned_server_shutdown": shutdown,
        "postconditions": postconditions,
    }


def ab_ffmpeg_argv(warm_output_name: str) -> list[str]:
    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-n",
        "-i",
        str(PRODUCTION_ARTIFACT),
        "-i",
        str(Path("outputs") / warm_output_name),
        "-i",
        str(TTS_FIXTURE),
        "-filter_complex",
        (
            "[0:v]setpts=PTS-STARTPTS,drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':"
            "text='A  Production unclamped 14B':fontcolor=white:fontsize=22:box=1:"
            "boxcolor=black@0.65:boxborderw=8:x=(w-text_w)/2:y=18[left];"
            "[1:v]setpts=PTS-STARTPTS,drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':"
            "text='B  Diet reserve-2.921 warm':fontcolor=white:fontsize=22:box=1:"
            "boxcolor=black@0.65:boxborderw=8:x=(w-text_w)/2:y=18[right];"
            "[left][right]hstack=inputs=2[v]"
        ),
        "-map",
        "[v]",
        "-map",
        "2:a:0",
        "-t",
        "3.88",
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
        "-ac",
        "1",
        "-ar",
        "44100",
        "-movflags",
        "+faststart",
        str(AB_OUTPUT),
    ]


def assemble_ab(root: Path = ROOT) -> Path:
    root = root.resolve()
    portrait, warm_receipt = validate_pair(root, "portrait")
    validate_portrait_run2_recovery(root, warm_receipt)
    validate_production(root)
    require_pinned(root, PORTRAIT_FIXTURE, PORTRAIT_SHA256)
    require_pinned(root, TTS_FIXTURE, TTS_SHA256)
    output = root / AB_OUTPUT
    require(not output.exists(), f"refusing to overwrite existing A/B: {output}")
    executable = shutil.which("ffmpeg")
    require(executable is not None, "ffmpeg is required for A/B assembly")
    argv = ab_ffmpeg_argv(str(warm_receipt["output_path"]))
    command = [executable, *argv[1:]]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    require(completed.returncode == 0, f"ffmpeg A/B assembly failed: {completed.stderr.strip()}")
    probe = probe_video_contract(output, width=960, height=832)
    require(portrait["canvas"]["duration_s"] == probe["container_duration_s"], "A/B duration mismatch")
    return output


def validate_ab(root: Path, warm_output_name: str) -> dict[str, Any]:
    path = root / AB_OUTPUT
    ref = relative_ref(root, path)
    probe = probe_video_contract(path, width=960, height=832)
    require(probe["audio_sample_rate_hz"] == 44100, "A/B audio sample rate mismatch")
    require(probe["audio_channels"] == 1, "A/B soundtrack must be mono")
    require(abs(probe["container_duration_s"] - 3.88) <= 0.001, "A/B duration mismatch")
    return {
        "purpose": "PENDING_HUMAN production-vs-diet portrait quality review",
        "human_review": {
            "status": "PENDING_HUMAN",
            "categories": ["lips", "onset", "identity", "temporal stability", "overall quality"],
        },
        "audio_policy": (
            "Both source audio streams are ignored. The exact raw fixtures/tts_dialogue.wav "
            "is mapped once from timestamp zero and encoded as the one shared mono AAC review track."
        ),
        "not_model_evidence": True,
        "source_paths": {
            "left_video": PRODUCTION_ARTIFACT.as_posix(),
            "right_video": (Path("outputs") / warm_output_name).as_posix(),
            "shared_audio": TTS_FIXTURE.as_posix(),
        },
        "assembly_argv": ab_ffmpeg_argv(warm_output_name),
        "artifact": ref,
        "media_probe": probe,
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    builder_ref = relative_ref(root, Path(__file__).resolve())
    fixtures = {
        "portrait.png": require_pinned(root, PORTRAIT_FIXTURE, PORTRAIT_SHA256),
        "tts_dialogue.wav": require_pinned(root, TTS_FIXTURE, TTS_SHA256),
    }
    production, _production_receipt = validate_production(root)
    portrait, portrait_warm = validate_pair(root, "portrait")
    portrait_cleanup = validate_portrait_run2_recovery(root, portrait_warm)
    landscape, _landscape_warm = validate_pair(root, "landscape")
    ab = validate_ab(root, str(portrait_warm["output_path"]))
    return {
        "comparison": "humo_14b_diet_envelope_job_a",
        "schema_version": 1,
        "measurement_scope": (
            "Four immutable lab runner receipts (portrait and landscape cold/warm), "
            "their hash-bound artifacts, and the immutable OTR-side production comparator."
        ),
        "numeric_provenance_policy": (
            "Every measured number carries a numeric_source receipt path; derived headroom is "
            "computed only from the cited warm receipt peak and the repository's 14.5 GiB gate."
        ),
        "builder": builder_ref,
        "fixture_sources": fixtures,
        "production_portrait_comparator": production,
        "diet_pairs": {
            "portrait": portrait,
            "landscape": landscape,
        },
        "portrait_warm_cleanup_incident": portrait_cleanup,
        "job_a_plain_answer": landscape["warm_vram_verdict"]["plain_answer"],
        "portrait_production_vs_diet_ab": ab,
        "human_review_pending": [
            AB_OUTPUT.as_posix(),
        ],
    }


def prerequisite_report(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    portrait = RUN_SPECS["portrait"]
    ab_required = [
        PRODUCTION_RECEIPT,
        PRODUCTION_ARTIFACT,
        PORTRAIT_FIXTURE,
        TTS_FIXTURE,
        PORTRAIT_RUN2_RECOVERY,
        portrait["recipe_path"],
        run_receipt_path(portrait, 1),
        run_receipt_path(portrait, 2),
    ]
    expected = [
        PRODUCTION_RECEIPT,
        PRODUCTION_ARTIFACT,
        PORTRAIT_FIXTURE,
        TTS_FIXTURE,
        PORTRAIT_RUN2_RECOVERY,
        *(spec["recipe_path"] for spec in RUN_SPECS.values()),
        *(run_receipt_path(spec, run) for spec in RUN_SPECS.values() for run in (1, 2)),
    ]
    missing = [path.as_posix() for path in expected if not (root / path).is_file()]
    return {
        "ready_for_ab": all((root / path).is_file() for path in ab_required),
        "ready_for_full_evidence": not missing and (root / AB_OUTPUT).is_file(),
        "missing": missing,
        "ab_exists": (root / AB_OUTPUT).is_file(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--preflight", action="store_true", help="list missing inputs; never write")
    actions.add_argument("--assemble-ab", action="store_true", help="assemble A/B after portrait warm exists")
    actions.add_argument("--check", action="store_true", help="fail unless committed output is exact")
    parser.add_argument("--root", type=Path, default=ROOT, help="lab repository root")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.preflight:
            report = prerequisite_report(root)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["ready_for_full_evidence"] else 1
        if args.assemble_ab:
            path = assemble_ab(root)
            print(f"[humo-14b-diet-evidence] wrote {path} sha256={sha256_file(path)}")
            return 0
        payload = canonical_json_bytes(build(root))
        output = root / OUTPUT
        if args.check:
            require(output.is_file(), f"missing output: {output}")
            require(output.read_bytes() == payload, f"stale output: {output}")
            print(f"[humo-14b-diet-evidence] PASS: {output}")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists() or output.read_bytes() != payload:
            output.write_bytes(payload)
        print(f"[humo-14b-diet-evidence] wrote {output} sha256={sha256_file(output)}")
        return 0
    except EvidenceError as exc:
        print(f"[humo-14b-diet-evidence] FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
