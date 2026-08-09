"""Build deterministic close-out comparison receipts from immutable run archives."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import torch
import numpy as np
from scipy.signal import correlate, correlation_lags


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "results" / "comparisons"
COMFY_ROOT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI")
KJ_ROOT = Path(r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-KJNodes")
GGUF_ROOT = Path(r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-GGUF")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def load_receipt(relative_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = ROOT / relative_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    output_name = payload.get("output_path")
    artifact_path = ROOT / "outputs" / output_name if output_name else None
    if artifact_path is not None:
        if not artifact_path.is_file() or artifact_path.stat().st_size <= 0:
            raise RuntimeError(f"Missing artifact for {relative_path}: {artifact_path}")
        actual_artifact_sha = sha256_file(artifact_path)
        if actual_artifact_sha != payload.get("artifact_sha256"):
            raise RuntimeError(f"Artifact hash drift for {relative_path}")
    evidence = {
        "artifact_path": f"outputs/{output_name}" if output_name else None,
        "artifact_sha256": payload.get("artifact_sha256"),
        "recipe": payload["recipe"],
        "recipe_sha256": payload["recipe_sha256"],
        "receipt_path": relative_path.replace("\\", "/"),
        "receipt_sha256": sha256_file(path),
        "run_number": payload["run_number"],
    }
    return payload, evidence


def measured(payload: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        **evidence,
        "baseline_vram_gib": payload.get("baseline_vram_gb"),
        "delivered_seconds": payload.get("delivered_s")
        or payload.get("container_delivered_s")
        or payload.get("container_duration_s"),
        "encoded_fps": payload.get("encoded_fps"),
        "encoded_frames": payload.get("encoded_frame_count"),
        "height": payload.get("encoded_height"),
        "machine_gate_pass": payload.get("gate_pass") is True,
        "peak_vram_gib": payload.get("peak_vram_gb"),
        "status": payload.get("status"),
        "wall_seconds": payload.get("duration_s"),
        "warm_pass": payload.get("warm_pass") is True,
        "width": payload.get("encoded_width"),
    }


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def project_version(path: Path) -> str:
    for line in (path / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version ="):
            return line.split('"', 2)[1]
    raise RuntimeError(f"No project version in {path}")


def write_once(output_dir: Path, filename: str, payload: dict[str, Any]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    raw = canonical_bytes(payload)
    if path.exists() and path.read_bytes() != raw:
        raise RuntimeError(f"Immutable close-out evidence differs: {path}")
    if not path.exists():
        path.write_bytes(raw)
        return "created"
    return "unchanged"


def h3_latent_t(frames: int) -> int:
    if frames % 17 != 5:
        raise ValueError(f"Illegal H3 frame count: {frames}")
    return 2 if frames <= 5 else ((frames - 5) // 17) * 5 + 2


def visual_tokens(width: int, height: int, frames: int) -> int:
    if width % 32 or height % 32:
        raise ValueError("H3 token estimate requires /32 canvas dimensions")
    return (width // 32) * (height // 32) * h3_latent_t(frames)


def decode_mono_f32(path: Path, sample_rate: int = 32000) -> np.ndarray:
    raw = subprocess.check_output(
        [
            "ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar",
            str(sample_rate), "-f", "f32le", "-",
        ]
    )
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def aligned_audio_metrics(
    source_path: Path, target_path: Path, sample_rate: int = 32000
) -> dict[str, Any]:
    source = decode_mono_f32(source_path, sample_rate)
    target = decode_mono_f32(target_path, sample_rate)
    max_lag = sample_rate // 2
    search_target = target[: len(source) + max_lag]
    cross = correlate(
        search_target - search_target.mean(),
        source - source.mean(),
        mode="full",
        method="fft",
    )
    lags = correlation_lags(len(search_target), len(source), mode="full")
    in_window = (lags >= -max_lag) & (lags <= max_lag)
    candidate = int(lags[in_window][int(np.argmax(cross[in_window]))])

    def aligned(lag: int) -> tuple[np.ndarray, np.ndarray]:
        if lag >= 0:
            count = min(len(source), len(target) - lag)
            return source[:count], target[lag : lag + count]
        count = min(len(source) + lag, len(target))
        return source[-lag : -lag + count], target[:count]

    best: tuple[float, int, np.ndarray, np.ndarray] | None = None
    for lag in range(candidate - 4, candidate + 5):
        source_aligned, target_aligned = aligned(lag)
        value = float(np.corrcoef(source_aligned, target_aligned)[0, 1])
        if best is None or value > best[0]:
            best = (value, lag, source_aligned, target_aligned)
    if best is None:
        raise RuntimeError("Could not align RefAudio source and target")
    waveform_r, lag_samples, source_aligned, target_aligned = best
    block_samples = 1024
    blocks = len(source_aligned) // block_samples
    source_rms = np.sqrt(
        np.mean(
            source_aligned[: blocks * block_samples].reshape(blocks, block_samples) ** 2,
            axis=1,
        )
    )
    target_rms = np.sqrt(
        np.mean(
            target_aligned[: blocks * block_samples].reshape(blocks, block_samples) ** 2,
            axis=1,
        )
    )
    return {
        "alignment_lag_samples": lag_samples,
        "alignment_lag_seconds": round(lag_samples / sample_rate, 6),
        "analysis_sample_rate_hz": sample_rate,
        "decoded_source_samples": len(source),
        "decoded_target_samples": len(target),
        "rms_envelope_block_samples": block_samples,
        "rms_envelope_pearson_r": round(float(np.corrcoef(source_rms, target_rms)[0, 1]), 6),
        "waveform_pearson_r": round(waveform_r, 6),
    }


def build_documents() -> dict[str, dict[str, Any]]:
    wan, wan_ev = load_receipt("results/wan_ti2v_5b_cmp_832x480_f193_run4.json")
    ltx, ltx_ev = load_receipt("results/ltx_video_2b_distilled_cmp_832x480_f193_run2.json")
    wan_m = measured(wan, wan_ev)
    ltx_m = measured(ltx, ltx_ev)
    if (wan_m["width"], wan_m["height"], wan_m["encoded_frames"]) != (832, 480, 193):
        raise RuntimeError("WAN speed-pair media contract drift")
    if (ltx_m["width"], ltx_m["height"], ltx_m["encoded_frames"]) != (832, 480, 193):
        raise RuntimeError("LTX speed-pair media contract drift")
    mp_frames = 832 * 480 * 193 / 1_000_000
    for lane in (wan_m, ltx_m):
        lane["megapixel_frames"] = round(mp_frames, 6)
        lane["megapixel_frames_per_second"] = round(
            mp_frames / lane["wall_seconds"], 6
        )
        lane["render_seconds_per_output_second"] = round(
            lane["wall_seconds"] / lane["delivered_seconds"], 6
        )
    speed_pair = {
        "comparison": "same_canvas_general_video_speed_pair",
        "controls": {
            "canvas": "832x480",
            "delivered_seconds": 7.72,
            "fps": 25,
            "frames": 193,
            "measurement": "second consecutive true execution with executor nonce",
        },
        "derived_formulae": {
            "megapixel_frames": "width * height * encoded_frames / 1e6",
            "megapixel_frames_per_second": "megapixel_frames / wall_seconds",
            "render_seconds_per_output_second": "wall_seconds / delivered_seconds",
        },
        "lanes": [wan_m, ltx_m],
        "ltx_wall_clock_speedup_over_wan": round(
            wan_m["wall_seconds"] / ltx_m["wall_seconds"], 6
        ),
        "status": "COMPLETE",
        "winner_by_normalized_warm_wall_clock": "ltx_video_2b_distilled_cmp_832x480_f193",
        "unnormalized_reported_rows": [
            {
                "canvas": None,
                "frames": 25,
                "model": "ltx_8gb (details not supplied)",
                "ranking_eligible": False,
                "source": "Jeffrey consolidated order, 2026-08-09",
                "status": "UNNORMALIZED",
                "steps": None,
                "wall_seconds": 20.3,
            },
            {
                "canvas": None,
                "frames": 193,
                "model": "ltx_video (details not supplied)",
                "ranking_eligible": False,
                "source": "Jeffrey consolidated order, 2026-08-09",
                "status": "UNNORMALIZED",
                "steps": None,
                "wall_seconds": 83.8,
            },
        ],
    }

    lipsync_takes: list[dict[str, Any]] = []
    for label, receipt_path, expected_seed in (
        ("A", "results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run1.json", 42),
        ("B", "results/h3_r2v_refaudio_tts_lipsync_exact_seed43_run1.json", 43),
    ):
        receipt, evidence = load_receipt(receipt_path)
        recipe = json.loads((ROOT / "recipes" / f"{receipt['recipe']}.json").read_text("utf-8"))
        actual_seed = recipe["prompt"]["5"]["inputs"]["noise_seed"]
        if actual_seed != expected_seed:
            raise RuntimeError(f"Unexpected H3 take seed for {label}")
        if receipt.get("gate_pass") is not True or receipt.get("warm_pass") is not False:
            raise RuntimeError(f"H3 take {label} is not the expected cold-only gate pass")
        row = measured(receipt, evidence)
        row.update(
            {
                "fixture_sha256s": receipt["fixture_sha256s"],
                "human_lipsync_verdict": "pending_jeffrey_full_clip_review",
                "label": label,
                "seed": actual_seed,
                "status": "GATE PASS (cold-only)",
            }
        )
        lipsync_takes.append(row)
    lipsync_package = {
        "comparison": "h3_lipsync_two_take_lab_package",
        "fixture_contract": {
            "actual_conditioning_inputs": [
                "fixtures/portrait.png",
                "fixtures/tts_dialogue.wav",
            ],
            "comparison_caveat": "None: this pair uses the ordered portrait plus raw-TTS contract exactly.",
            "raw_tts_dialogue_path": "fixtures/tts_dialogue.wav",
            "raw_tts_dialogue_sha256": sha256_file(ROOT / "fixtures" / "tts_dialogue.wav"),
        },
        "human_decision": "pending",
        "lab_scope": "H3 only; HuMo wrapper is outside the lab whitelist and was not run",
        "mean_h3_wall_seconds": round(
            sum(row["wall_seconds"] for row in lipsync_takes) / len(lipsync_takes), 6
        ),
        "otr_side_open_decision": "Compare these exact portrait and raw-TTS hashes against HuMo outside this lab.",
        "status": "LAB_HALF_COMPLETE_TWO_COLD_MACHINE_GATES",
        "takes": lipsync_takes,
        "technical_screen_review": {
            "method": "Codex manual review of sampled-frame contact sheets",
            "reviewed_at": "2026-08-09T02:51:09-07:00",
            "scope": (
                "Both receipt-bound artifacts show stable faces and visibly distinct mouth "
                "shapes in sampled frames. This is not a phoneme-sync, pause-settling, "
                "cross-seed-consistency, or human promotion verdict."
            ),
            "takes": [
                {
                    "artifact_path": row["artifact_path"],
                    "artifact_sha256": row["artifact_sha256"],
                    "label": row["label"],
                    "observation": "Visible mouth-shape variation in sampled frames",
                }
                for row in lipsync_takes
            ],
        },
    }

    refaudio_music, refaudio_music_ev = load_receipt(
        "results/h3_r2v_refaudio_music_opening_run1.json"
    )
    refaudio_source = ROOT / "fixtures" / "ltx_matrix_music_opening_3p88s_gain_minus12db.wav"
    refaudio_target = ROOT / refaudio_music_ev["artifact_path"]
    refaudio_reconstruction = {
        "analysis": aligned_audio_metrics(refaudio_source, refaudio_target),
        "conclusion": (
            "The original approximately-0.94 finding is confirmed more strongly by this "
            "receipt-bound PCM recheck: H3 largely reconstructs the conditioning music "
            "instead of composing an independent soundtrack."
        ),
        "continuation_tail_seconds_by_stream_duration": round(
            refaudio_music["audio_duration_s"] - 3.88, 6
        ),
        "decoder_command": "ffmpeg -v error -i <input> -ac 1 -ar 32000 -f f32le -",
        "reference_window_seconds": 3.88,
        "scope": (
            "Objective audio similarity only; this does not establish visual beat response "
            "or a human listening verdict."
        ),
        "source_fixture_path": "fixtures/ltx_matrix_music_opening_3p88s_gain_minus12db.wav",
        "source_fixture_sha256": sha256_file(refaudio_source),
        "source_run": refaudio_music_ev,
        "status": "RECONSTRUCTION_CONFIRMED",
    }

    human_reviews: list[dict[str, Any]] = []
    for alias_path, immutable_path in (
        (
            "results/h3_r2v_refaudio_tts_dialogue.json",
            "results/h3_r2v_refaudio_tts_dialogue_run1.json",
        ),
        (
            "results/h3_r2v_refaudio_music_opening.json",
            "results/h3_r2v_refaudio_music_opening_run1.json",
        ),
    ):
        alias, alias_ev = load_receipt(alias_path)
        immutable = ROOT / immutable_path
        human_reviews.append(
            {
                "current_alias": alias_ev,
                "eyeball": alias["eyeball"],
                "eyeball_reviewed_at": alias["eyeball_reviewed_at"],
                "eyeball_source": alias["eyeball_source"],
                "human_video_description": alias["human_video_description"],
                "human_video_scope": alias["human_video_scope"],
                "immutable_machine_receipt_path": immutable_path,
                "immutable_machine_receipt_sha256": sha256_file(immutable),
            }
        )
    refaudio_human_reviews = {
        "comparison": "h3_refaudio_human_review_amendments",
        "reviews": human_reviews,
        "scope": (
            "Hash-bound human annotations on mutable current aliases; immutable machine "
            "run archives remain unchanged."
        ),
        "status": "HUMAN_REVIEW_FIELDS_FROZEN",
    }

    hq_rows: list[dict[str, Any]] = []
    for rung, receipt_path in (
        ("H1_canvas_1024x576", "results/ltx_audio_hq_h1_1024x576_run2.json"),
        ("H2_duration_193f", "results/ltx_audio_hq_h2_193f_run2.json"),
        ("H3_canvas_and_duration", "results/ltx_audio_hq_h3_1024x576_193f_run2.json"),
    ):
        receipt, evidence = load_receipt(receipt_path)
        row = measured(receipt, evidence)
        if not row["warm_pass"]:
            raise RuntimeError(f"HQ rung is not warm-pass: {rung}")
        row["rung"] = rung
        hq_rows.append(row)
    hq_ladder = {
        "best_machine_certified_configuration": "H3_canvas_and_duration",
        "comparison": "ltx_audio_hq_ladder",
        "human_eyeball": "pending_jeffrey_full_clip_review",
        "rungs": hq_rows,
        "sampled_frame_technical_screen": (
            "No obvious mesh/noise/collapse in 1 fps contact sheets; not a human promotion verdict"
        ),
        "status": "COMPLETE_THREE_WARM_PASSES",
    }

    wan_cold, wan_cold_ev = load_receipt(
        "results/wan_i2v_14b_exoneration_832x480_f33_run1.json"
    )
    wan_warm, wan_warm_ev = load_receipt(
        "results/wan_i2v_14b_exoneration_832x480_f33_run2.json"
    )
    wan_i2v = {
        "cold": measured(wan_cold, wan_cold_ev),
        "comparison": "wan_i2v_14b_exoneration",
        "lane": "clamp-12gb, no-pinned",
        "status": "VIABLE_BUT_COLD_MARGIN_IS_ONLY_0.10_GIB",
        "verdict": (
            "Exonerated at 832x480x33, but the cold net allocation was 11.90/12 GiB; "
            "keep WAN TI2V as the safer default"
        ),
        "warm": measured(wan_warm, wan_warm_ev),
    }

    motion_rows: list[dict[str, Any]] = []
    for label, receipt_path, variable in (
        ("M0", "results/ltx_audio_gguf_music_opening_run1.json", "control"),
        ("M1", "results/ltx_audio_motion_m1_prompt_run1.json", "motion vocabulary prompt"),
        ("M2", "results/ltx_audio_motion_m2_soft_anchor_run1.json", "strength 1.0 to 0.7"),
        ("M3", "results/ltx_audio_motion_m3_double_duration_run1.json", "duration 3.88 to 7.76 s"),
    ):
        receipt, evidence = load_receipt(receipt_path)
        row = measured(receipt, evidence)
        row.update({"label": label, "single_variable": variable})
        motion_rows.append(row)
    motion_ladder = {
        "comparison": "ltx_audio_motion_ladder",
        "human_ranking": "pending_jeffrey_full_clip_review",
        "sampled_frame_technical_screen": {
            "M0_M1_M2": "near-still composition at 1 fps samples",
            "M3": "slow camera translation/zoom across the longer clip",
            "scope": "contact-sheet observation only; no claim of beat response",
        },
        "status": "COMPLETE_FOUR_LABELED_ARTIFACTS",
        "variants": motion_rows,
    }

    mime, mime_ev = load_receipt(
        "results/h3_mime_i2v_ledger_music_closing_8s_run1.json"
    )
    mime_receipt = {
        "comparison": "h3_unconditioned_mini_mime",
        "human_inverted_ear_gate": {
            "coherent_diegetic_sync": "pending",
            "no_speech_like_or_vocal_like_content_of_any_intelligibility": "pending",
        },
        "ledger_binding": "fixtures/ledger.json#/music/1",
        "machine_evidence": measured(mime, mime_ev),
        "no_external_audio_conditioning": True,
        "sampled_frame_technical_screen": (
            "Coherent camera move from operators toward radio equipment; no obvious frame collapse"
        ),
        "status": "ONE_COLD_MACHINE_PASS_HUMAN_EYES_AND_EARS_PENDING",
        "strict_gate_amendment": (
            "This comparison receipt supersedes the rendered recipe metadata's weaker "
            "none_intelligible wording. Any speech-like or vocal-like content fails, "
            "whether intelligible or not."
        ),
    }
    mime_audio_qa = {
        "artifact_path": mime_receipt["machine_evidence"]["artifact_path"],
        "artifact_sha256": mime_receipt["machine_evidence"]["artifact_sha256"],
        "commands": {
            "loudness": (
                "ffmpeg -hide_banner -nostats -i <artifact> -map 0:a:0 "
                "-af loudnorm=I=-24:LRA=7:TP=-2:print_format=json -f null NUL"
            ),
            "silence": (
                "ffmpeg -hide_banner -nostats -i <artifact> -map 0:a:0 "
                "-af silencedetect=noise=<threshold>dB:d=<duration> -f null NUL"
            ),
        },
        "ffmpeg_version": "8.0.1-full_build-www.gyan.dev",
        "loudnorm_input_summary": {
            "integrated_lufs": -31.32,
            "loudness_range_lu": 1.0,
            "threshold_lufs": -41.32,
            "true_peak_dbtp": -13.55,
        },
        "human_inverted_ear_gate": "pending",
        "silence_detect": {
            "tests": [
                {"events": 0, "minimum_duration_seconds": 0.1, "threshold_db": -50},
                {"events": 0, "minimum_duration_seconds": 0.2, "threshold_db": -40},
                {"events": 0, "minimum_duration_seconds": 0.2, "threshold_db": -35},
            ],
        },
        "source_receipt_path": mime_receipt["machine_evidence"]["receipt_path"],
        "source_receipt_sha256": mime_receipt["machine_evidence"]["receipt_sha256"],
        "scope": (
            "Objective stream-level QA only. It does not establish absence of speech/vocals "
            "or coherent diegetic synchronization."
        ),
    }

    sage, sage_ev = load_receipt(
        "results/h3_i2v_sage_patch_fp16pv_experimental_run1.json"
    )
    sage_log_excerpt = ROOT / "results" / "evidence" / "h3_sage_patch_failure_excerpt.txt"
    sage_probe = {
        "comparison": "h3_per_model_sage_fp16pv_probe",
        "external_reported_scope": {
            "claimed_speedup": (
                "3x on sm_86, supplied as EXTERNAL-REPORTED challenge context; exact public "
                "wording was not independently verified"
            ),
            "silent_noise_risk": (
                "EXTERNAL-REPORTED failure mode for global Sage behavior; this experiment "
                "used a distinct per-model KJ patch"
            ),
            "silent_noise_source": "https://github.com/Comfy-Org/ComfyUI/issues/15263",
        },
        "error_evidence": {
            "captured_lines": [
                "Windows fatal exception: code 0x80000003",
                "File C:/Users/jeffr/Documents/ComfyUI/custom_nodes/ComfyUI-KJNodes/nodes/model_optimization_nodes.py, line 35 in sage_func",
                "Exception Code: 0x80000003",
            ],
            "source_line_range": "server.log:81263-81325",
            "source_log_sha256_at_capture": "d290df8d4a863f070c5edc76df8dedae04e9b539445245341fa989fcc5b75923",
            "tracked_excerpt_path": "results/evidence/h3_sage_patch_failure_excerpt.txt",
            "tracked_excerpt_sha256": sha256_file(sage_log_excerpt),
        },
        "machine_evidence": measured(sage, sage_ev),
        "output_produced": False,
        "status": "FAIL_KERNEL_EXCEPTION_TIMEOUT_CLEANUP_PROVED",
        "verdict": "Do not enable this per-model Sage mode on the measured sm_120 environment",
    }

    mime_tokens = visual_tokens(864, 480, 192)
    lipsync_tokens = visual_tokens(864, 480, 124)
    token_recipe_path = ROOT / "recipes" / "h3_r2v_refaudio_tts_lipsync_exact_seed42.json"
    token_recipe = json.loads(token_recipe_path.read_text(encoding="utf-8"))
    token_check = {
        "external_reported_claim": {
            "canvas_reported": "692x692 nominal; /32 execution estimate rounds to 704x704",
            "frames": 192,
            "gpu_vram_gib_reported": 8,
            "output_visual_tokens_derived": visual_tokens(704, 704, 192),
            "source": "https://www.youtube.com/watch?v=qc5C4P_5p6o&lc=UgwaJdwHq6aaxVwX8-V4AaABAg",
            "status": "EXTERNAL-REPORTED commenter anecdote; no memory ceiling inferred",
            "wall_seconds_reported": 210,
        },
        "feasibility_estimator": {
            "formula": "(width/32) * (height/32) * video_latent_t",
            "sources": [
                "https://huggingface.co/MiniMaxAI/MiniMax-H3",
                "ComfyUI 0.31.1 commit fe4195f7f4275f2626cbafc703acc3ddde1e5490",
            ],
            "status": "EXTERNAL-REPORTED/DERIVED feasibility estimator; not a VRAM law",
        },
        "local_checks": [
            {
                "canvas": "864x480",
                "frames": 124,
                "latent_t": h3_latent_t(124),
                "measured_peak_vram_gib": lipsync_takes[0]["peak_vram_gib"],
                "output_visual_tokens": lipsync_tokens,
                "receipt_path": lipsync_takes[0]["receipt_path"],
                "receipt_sha256": lipsync_takes[0]["receipt_sha256"],
                "artifact_sha256": lipsync_takes[0]["artifact_sha256"],
            },
            {
                "canvas": "864x480",
                "frames": 192,
                "latent_t": h3_latent_t(192),
                "measured_peak_vram_gib": mime_receipt["machine_evidence"]["peak_vram_gib"],
                "output_visual_tokens": mime_tokens,
                "receipt_path": mime_receipt["machine_evidence"]["receipt_path"],
                "receipt_sha256": mime_receipt["machine_evidence"]["receipt_sha256"],
                "artifact_sha256": mime_receipt["machine_evidence"]["artifact_sha256"],
            },
        ],
        "round_length_fact": (
            "192 = 17*11+5 and 192/24 = 8.000 s; it is the only integer-second "
            "17k+5 length in the documented 124-362 frame range"
        ),
        "scope": (
            "Output visual tokens only; excludes reference, audio, and text tokens and is "
            "a feasibility estimator rather than a VRAM predictor"
        ),
        "ref_image_size_check": {
            "receipt_path": lipsync_takes[0]["receipt_path"],
            "receipt_sha256": lipsync_takes[0]["receipt_sha256"],
            "recipe_path": "recipes/h3_r2v_refaudio_tts_lipsync_exact_seed42.json",
            "recipe_sha256": sha256_file(token_recipe_path),
            "value": token_recipe["prompt"]["7"]["inputs"]["ref_image_size"],
        },
        "vocal_separation_claim": {
            "claim": "Vocal separation reportedly improves lip synchronization",
            "source": "https://www.youtube.com/watch?v=qc5C4P_5p6o",
            "status": "EXTERNAL-REPORTED creator advice; not measured locally",
        },
    }

    sage_recipe = ROOT / "recipes" / "h3_i2v_sage_patch_fp16pv_experimental.json"
    sage_payload = json.loads(sage_recipe.read_text(encoding="utf-8"))
    speed_stack = {
        "download_performed": False,
        "h3_lightx2v_4step": sage_payload["experiment"]["speed_stack_inventory"][
            "h3_lightx2v_four_step"
        ],
        "h3_w4a8_mixed": sage_payload["experiment"]["speed_stack_inventory"][
            "kijai_h3_w4a8_mixed"
        ],
        "proposal": (
            "If Jeffrey authorizes downloads later, fetch the Kijai H3 W4A8-mixed FL2VA "
            "weight and the official/Kijai H3 LightX2V four-step LoRA into quarantine, hash "
            "them into models_manifest.md, then run a new immutable H3 I2V turbo campaign."
        ),
        "source_recipe_path": "recipes/h3_i2v_sage_patch_fp16pv_experimental.json",
        "source_recipe_sha256": sha256_file(sage_recipe),
        "status": "BLOCKED_MISSING_BOTH_ASSETS",
    }

    nvidia = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=driver_version,memory.total,name",
            "--format=csv,noheader",
        ],
        text=True,
    ).strip()
    driver, memory_total, gpu_name = [part.strip() for part in nvidia.split(",", 2)]
    environment = {
        "active_custom_node_whitelist": ["ComfyUI-GGUF", "ComfyUI-KJNodes"],
        "comfyui": {"commit": git_head(COMFY_ROOT), "version": "0.31.1"},
        "cuda_runtime": torch.version.cuda,
        "distribution_seed": "2.1",
        "flashattention2": "absent and unsupported on this platform",
        "gpu": {
            "compute_capability": list(torch.cuda.get_device_capability(0)),
            "driver": driver,
            "memory_total": memory_total,
            "name": gpu_name,
        },
        "kj_nodes": {
            "commit": git_head(KJ_ROOT),
            "pyproject_sha256": sha256_file(KJ_ROOT / "pyproject.toml"),
            "version": project_version(KJ_ROOT),
        },
        "comfyui_gguf": {
            "nodes_py_sha256": sha256_file(GGUF_ROOT / "nodes.py"),
            "pyproject_sha256": sha256_file(GGUF_ROOT / "pyproject.toml"),
            "version": project_version(GGUF_ROOT),
        },
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "sageattention": importlib.metadata.version("sageattention"),
        "torch": torch.__version__,
    }

    return {
        "environment_2p1.json": environment,
        "general_video_speed_pair.json": speed_pair,
        "h3_lipsync_ab_package.json": lipsync_package,
        "h3_refaudio_human_reviews.json": refaudio_human_reviews,
        "h3_refaudio_reconstruction.json": refaudio_reconstruction,
        "h3_mime_audio_qa.json": mime_audio_qa,
        "h3_mime_unconditioned.json": mime_receipt,
        "h3_sage_patch_probe.json": sage_probe,
        "h3_speed_stack_inventory.json": speed_stack,
        "h3_token_budget_check.json": token_check,
        "ltx_audio_hq_ladder.json": hq_ladder,
        "ltx_motion_ladder.json": motion_ladder,
        "wan_i2v_14b_exoneration.json": wan_i2v,
    }


def main() -> None:
    documents = build_documents()
    for filename, payload in documents.items():
        print(f"{filename}: {write_once(OUTPUT_DIR, filename, payload)}")


if __name__ == "__main__":
    main()
