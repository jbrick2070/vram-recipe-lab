#!/usr/bin/env python3
"""Build the two H3-LIP-TXT transcript-aware candidates, offline only.

The candidates are deep copies of the committed exact native controls. After a
PASS transcript-window receipt exists, their only execution-surface difference
from the same-seed control is the H3 prompt text. This script never boots
ComfyUI or renders a clip.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scratch import build_h3_refaudio_exact_lipsync_pair as exact
from scratch import h3_lip_txt_common as common
from scratch import h3_lip_txt_window as window
from validate_recipes import topology_contract_errors


SEED43_CONTROL_RECIPE_NAME = "h3_r2v_refaudio_tts_lipsync_exact_seed43"
SEED43_CONTROL_RECIPE = common.RECIPES / f"{SEED43_CONTROL_RECIPE_NAME}.json"
SEED43_CONTROL_RECIPE_SHA256 = (
    "159467e9e9d25b07b95e5cd46a16c8c45af0449f0ab838285697d259f7339712"
)

CANDIDATE_NAME_BY_SEED = {
    42: "h3_r2v_refaudio_tts_lipsync_transcript_seed42",
    43: "h3_r2v_refaudio_tts_lipsync_transcript_seed43",
}
CONTROL_BY_SEED = {
    42: (common.CONTROL_RECIPE, common.CONTROL_RECIPE_SHA256),
    43: (SEED43_CONTROL_RECIPE, SEED43_CONTROL_RECIPE_SHA256),
}

PROMPT_PREFIX = (
    "Use <Picture 1> as the sole character and identity reference. The character "
    "speaks directly to camera using <Audio 1>. Precisely synchronize mouth shapes, "
    "pauses, expression, and final mouth closure to <Audio 1>. Preserve identity, "
    "clothing, framing, and one speaker throughout. No subtitle or extra dialogue.\n\n"
    "Audio:\nVoice:\""
)
PROMPT_SUFFIX = "\""


class CandidateError(common.H3LipTxtError):
    """A candidate recipe would violate the H3-LIP-TXT controlled comparison."""


def transcript_prompt(transcript: str) -> str:
    if not transcript or "\x00" in transcript:
        raise CandidateError("Canonical transcript text is missing")
    return PROMPT_PREFIX + transcript + PROMPT_SUFFIX


def _load_hash_pinned_control(seed: int) -> tuple[dict[str, Any], Path, str]:
    try:
        path, expected_sha = CONTROL_BY_SEED[seed]
    except KeyError as exc:
        raise CandidateError(f"Unsupported H3-LIP-TXT seed: {seed}") from exc
    raw = common.require_sha256(path, expected_sha, f"seed-{seed} native control recipe")
    control, parsed_raw = common.load_json_object(path)
    if raw != parsed_raw:
        raise CandidateError(f"Control recipe read changed during validation: {path}")
    if control.get("name") != path.stem:
        raise CandidateError(f"Control recipe identity drift: {path}")
    if control.get("prompt", {}).get("5", {}).get("inputs", {}).get("noise_seed") != seed:
        raise CandidateError(f"Control seed drift: {path}")
    return control, path, expected_sha


def _replace_required_input(
    topology: dict[str, Any], node: str, input_name: str, value: Any
) -> None:
    values = topology.get("required_input_values")
    if not isinstance(values, list):
        raise CandidateError("Control topology has no required_input_values list")
    matches = [
        assertion
        for assertion in values
        if isinstance(assertion, dict)
        and assertion.get("node") == node
        and assertion.get("input") == input_name
    ]
    if len(matches) != 1:
        raise CandidateError(
            f"Expected one topology assertion for {node}.{input_name}, got {len(matches)}"
        )
    matches[0]["equals"] = value


def _candidate_experiment(
    seed: int,
    control_path: Path,
    control_sha: str,
    transcript_receipt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "campaign": "H3-LIP-TXT",
        "arm": "transcript_aware",
        "matrix_role": "same-runner prompt-only native-vs-transcript-aware comparison",
        "independent_variable": "prompt_text_only",
        "candidate_recipe_names": [
            CANDIDATE_NAME_BY_SEED[42],
            CANDIDATE_NAME_BY_SEED[43],
        ],
        "pair_seeds": [42, 43],
        "seed": seed,
        "control_recipe": common.repo_relative(control_path),
        "control_recipe_sha256": control_sha,
        "transcript_window_receipt": transcript_receipt["receipt_path"],
        "transcript_window_receipt_sha256": transcript_receipt["receipt_sha256"],
        "transcript_utf8_sha256": transcript_receipt["transcript"]["utf8_sha256"],
        "source_fixture": "fixtures/tts_dialogue.wav",
        "source_fixture_sha256": common.SOURCE_AUDIO_SHA256,
        "fixture_policy": (
            "Exactly portrait.png as Picture 1 and the full raw tts_dialogue.wav "
            "as Audio 1; the recorded transcript window informs prompt text only and "
            "does not trim or replace conditioning audio."
        ),
        "execution_diff_from_same_seed_control": [
            "prompt.7.inputs.prompt",
        ],
        "output_audio_policy": "Native sampled target audio only; no source-audio mux node",
        "render_status": "unrendered",
        "behavioral_claim_status": "unrendered and unproven",
        "required_human_gate": "Jeffrey judges both same-seed source-window review copies",
    }


def build_candidate(seed: int, transcript_receipt: dict[str, Any]) -> dict[str, Any]:
    control, control_path, control_sha = _load_hash_pinned_control(seed)
    transcript = transcript_receipt["transcript"]["verbatim_utf8"]
    candidate = copy.deepcopy(control)
    candidate_name = CANDIDATE_NAME_BY_SEED[seed]
    candidate["name"] = candidate_name
    candidate["experiment"] = _candidate_experiment(
        seed, control_path, control_sha, transcript_receipt
    )
    candidate["prompt"]["7"]["inputs"]["prompt"] = transcript_prompt(transcript)

    topology = candidate["topology_contract"]
    topology["profile"] = "minimax_h3_ref2va_h3_lip_txt_v1"
    topology["intent"] = (
        "Exact Ref2VA native-audio topology copied from the same-seed native control; "
        "only prompt text is transcript-aware while the raw full source fixture remains "
        "the sole Audio 1 conditioning input"
    )
    origin = copy.deepcopy(topology.get("origin") or {})
    origin.update(
        {
            "builder": "scratch/build_h3_lip_txt_campaign.py",
            "control_recipe": common.repo_relative(control_path),
            "control_recipe_sha256": control_sha,
            "control_recipe_edited": False,
            "transcript_window_receipt": transcript_receipt["receipt_path"],
            "transcript_window_receipt_sha256": transcript_receipt["receipt_sha256"],
        }
    )
    topology["origin"] = origin
    _replace_required_input(topology, "7", "prompt", candidate["prompt"]["7"]["inputs"]["prompt"])
    topology["h3_lip_txt_prompt_evidence"] = {
        "transcript_window_receipt": transcript_receipt["receipt_path"],
        "transcript_window_receipt_sha256": transcript_receipt["receipt_sha256"],
        "transcript_utf8_sha256": transcript_receipt["transcript"]["utf8_sha256"],
        "prompt_text_only": True,
    }
    topology["candidate_vs_same_seed_control_execution_diff"] = [
        "prompt.7.inputs.prompt",
    ]
    validate_candidate(candidate, control, transcript_receipt)
    return candidate


def validate_candidate(
    candidate: dict[str, Any], control: dict[str, Any], transcript_receipt: dict[str, Any]
) -> None:
    name = candidate.get("name")
    prompt = candidate.get("prompt")
    if not isinstance(name, str) or not isinstance(prompt, dict):
        raise CandidateError("Candidate lacks a name or prompt graph")
    expected_seed = next(
        (
            seed
            for seed, candidate_name in CANDIDATE_NAME_BY_SEED.items()
            if candidate_name == name
        ),
        None,
    )
    if expected_seed is None:
        raise CandidateError(f"Unauthorized candidate name: {name!r}")
    expected_prompt = transcript_prompt(transcript_receipt["transcript"]["verbatim_utf8"])
    if prompt.get("7", {}).get("inputs", {}).get("prompt") != expected_prompt:
        raise CandidateError("Candidate prompt is not the canonical transcript-aware prompt")
    tags = set(re.findall(r"<(?:Picture|Video|Audio) \d+>", expected_prompt))
    if tags != {"<Picture 1>", "<Audio 1>"}:
        raise CandidateError(f"Candidate prompt reference tags drifted: {tags!r}")
    if (
        prompt.get("12", {}).get("inputs", {}).get("filename_prefix")
        != control.get("prompt", {}).get("12", {}).get("inputs", {}).get("filename_prefix")
    ):
        raise CandidateError("Candidate SaveVideo prefix changed; the A/B must be prompt-only")
    execution_diff = exact.difference_paths(control["prompt"], prompt)
    allowed_execution_diff = {
        "7.inputs.prompt",
    }
    if execution_diff != allowed_execution_diff:
        raise CandidateError(
            "Candidate changes more than prompt text: "
            f"{sorted(execution_diff)!r}"
        )
    if candidate.get("contract") != control.get("contract") or candidate.get("workflow") != control.get("workflow"):
        raise CandidateError("Candidate changed its fixed contract or workflow")
    if exact.source_consumers(prompt, "16") != {("7", "ref_audios.ref_audio_0")}:
        raise CandidateError("Raw source audio escaped the sole H3 conditioning socket")
    if prompt.get("10", {}).get("inputs", {}).get("audio") != ["15", 0]:
        raise CandidateError("CreateVideo must retain native sampled target audio")
    if prompt.get("7", {}).get("inputs", {}).get("ref_image_size") != "match":
        raise CandidateError("ref_image_size must remain match")
    if prompt.get("5", {}).get("inputs", {}).get("noise_seed") != expected_seed:
        raise CandidateError("Candidate seed changed")
    if prompt.get("14", {}).get("inputs", {}) != {
        "model": ["1", 0],
        "scheduler": "simple",
        "steps": 20,
        "denoise": 1.0,
    }:
        raise CandidateError("Candidate scheduler/steps changed")
    if prompt.get("13", {}).get("inputs") != {"sampler_name": "res_multistep"}:
        raise CandidateError("Candidate sampler changed")
    exact.validate_dag(prompt, name)
    topology_errors = topology_contract_errors(candidate, prompt)
    if topology_errors:
        raise CandidateError("Topology contract rejected candidate: " + "; ".join(topology_errors))
    experiment = candidate.get("experiment")
    if not isinstance(experiment, dict):
        raise CandidateError("Candidate experiment provenance is missing")
    if (
        experiment.get("transcript_window_receipt") != transcript_receipt["receipt_path"]
        or experiment.get("transcript_window_receipt_sha256")
        != transcript_receipt["receipt_sha256"]
        or experiment.get("transcript_utf8_sha256")
        != transcript_receipt["transcript"]["utf8_sha256"]
    ):
        raise CandidateError("Candidate transcript receipt provenance drifted")


def build_pair(
    transcript_receipt_path: Path = common.TRANSCRIPT_RECEIPT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    transcript_receipt = window.validate_transcript_receipt(transcript_receipt_path)
    seed42 = build_candidate(42, transcript_receipt)
    seed43 = build_candidate(43, transcript_receipt)
    pair_diff = exact.difference_paths(seed42["prompt"], seed43["prompt"])
    expected = {"5.inputs.noise_seed", "12.inputs.filename_prefix"}
    if pair_diff != expected:
        raise CandidateError(
            f"Transcript candidate pair drift is not seed/prefix-only: {sorted(pair_diff)!r}"
        )
    return seed42, seed43


def write_pair(
    transcript_receipt_path: Path = common.TRANSCRIPT_RECEIPT,
    output_dir: Path = common.RECIPES,
) -> dict[str, bool]:
    """Immutably publish candidates after receipt validation; never overwrite drift."""
    seed42, seed43 = build_pair(transcript_receipt_path)
    written: dict[str, bool] = {}
    for candidate in (seed42, seed43):
        payload = common.canonical_json_bytes(candidate, sort_keys=False)
        if payload.startswith(b"\xef\xbb\xbf") or b"\r\n" in payload:
            raise CandidateError("Candidate serialization must be UTF-8/LF without BOM")
        written[candidate["name"]] = common.write_immutable(
            output_dir / f"{candidate['name']}.json", payload
        )
    return written


def _path_arg(value: str) -> Path:
    return Path(value).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transcript-receipt", type=_path_arg, default=common.TRANSCRIPT_RECEIPT
    )
    parser.add_argument("--output-dir", type=_path_arg, default=common.RECIPES)
    args = parser.parse_args()
    try:
        written = write_pair(args.transcript_receipt, args.output_dir)
    except common.H3LipTxtError as exc:
        print(f"[H3-LIP-TXT CANDIDATE FAIL] {exc}", file=sys.stderr)
        return 1
    for name, created in written.items():
        action = "created" if created else "already-identical"
        print(f"[{action}] {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
