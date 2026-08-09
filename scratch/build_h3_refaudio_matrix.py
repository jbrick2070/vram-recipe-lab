#!/usr/bin/env python3
"""Build the immutable three-cell MiniMax H3 Ref2VA audio-reference matrix.

This offline builder starts from the repository-local ``h3_r2v_best`` API
prompt, pins its audited bytes, and makes only the intentional experiment
changes documented below.  Community workflows were used as topology
evidence only; no third-party workflow JSON or custom-node implementation is
read, imported, or copied by this builder.

The source WAV is model conditioning.  It must never be the soundtrack passed
to ``CreateVideo``.  The saved soundtrack is always decoded from the sampled
target AV latent by ``VAEDecodeAudio``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
FIXTURES = ROOT / "fixtures"
AUDIO_RECEIPTS = FIXTURES / "audio_receipts"
BASE_RECIPE = RECIPES / "h3_r2v_best.json"
TTS_DIALOGUE_RECIPE = RECIPES / "h3_r2v_refaudio_tts_dialogue.json"
TTS_LIPSYNC_SEED42_RECIPE = RECIPES / "h3_r2v_refaudio_tts_lipsync.json"
FROZEN_TEMPLATE = ROOT / "research" / "comfy_templates" / "video_minimax_h3_r2v.json"
INSTALLED_COMFY_ROOT = Path.home() / "ComfyUI-Installs" / "ComfyUI" / "ComfyUI"
INSTALLED_NODE_SOURCE = INSTALLED_COMFY_ROOT / "comfy_extras" / "nodes_minimax_h3.py"

EXPECTED_BASE_RECIPE_SHA256 = (
    "20e584cc016bdc5bdb857b00923c7ae838174724e3c20be0dfc322a809392eda"
)
EXPECTED_TTS_DIALOGUE_RECIPE_SHA256 = (
    "85e180b89d7d1adec88407fcc9e2b664d1a13bbbdc543e0c60d965903b62f437"
)
EXPECTED_TTS_LIPSYNC_SEED42_RECIPE_SHA256 = (
    "930289e8b719c59392a18b0e81ef40ce0ea8d1b5a19e80c30f929533e3bdf0c5"
)
EXPECTED_FROZEN_TEMPLATE_SHA256 = (
    "099d24eda6263854818975c7209db6f29ebfd0339936c928f12293d5ab029ffb"
)
EXPECTED_INSTALLED_NODE_SOURCE_SHA256 = (
    "f767df4074b908efb345f5a87c2fd263ba82c12e65bcca932846207cc213e064"
)
COMFYUI_VERSION = "0.31.1"
COMFYUI_GIT_COMMIT = "fe4195f7f4275f2626cbafc703acc3ddde1e5490"

WIDTH = 864
HEIGHT = 480
FRAMES = 124
FPS = 24.0
SEED = 42
AUDIO_WINDOW_S = 3.88
AUDIO_SAMPLE_RATE = 32_000
AUDIO_SAMPLE_COUNT = 124_160
TARGET_LUFS = -25.8
LUFS_TOLERANCE = 0.3

PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
SCENE_STILL_SHA256 = "0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596"

UNET_NAME = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
CLIP_NAME = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE_NAME = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE_NAME = "minimax_h3_audio_vae_fp32.safetensors"

SHARED_PROMPT = (
    "subject_definitions:\n"
    "<Picture 1> is the sole character identity and appearance reference.\n"
    "<Picture 2> is the sole environment, lighting, and composition reference.\n"
    "<Audio 1> is the sole audio reference for the target audiovisual generation.\n\n"
    "summary:\n"
    "[reference generation + audio reference] Create one restrained cinematic shot "
    "in the vintage radio control room from <Picture 2>, preserving the person from "
    "<Picture 1> while <Audio 1> guides the newly generated target audio.\n\n"
    "retention_analysis:\n"
    "<Picture 1>: fully_preserved - Preserve the face, hair, clothing, body proportions, "
    "and recognizable identity.\n"
    "<Picture 2>: fully_preserved - Preserve the room layout, analog equipment, warm "
    "lighting, and spatial composition.\n"
    "<Audio 1>: reference - Its audible content, timbre, rhythm, pacing, and temporal "
    "structure guide newly generated target audio without adding an unrelated source.\n\n"
    "detailed_description:\n"
    "The target video uses a realistic restrained cinematic style. [Shot 1] The person "
    "from <Picture 1> is naturally integrated into the vintage radio control room from "
    "<Picture 2>. Warm analog console light remains stable while the camera makes one "
    "slow, smooth move. Facial identity, clothing, body proportions, equipment placement, "
    "and room geometry remain coherent. Motion is subtle and physically plausible. "
    "<Audio 1> guides the target audio throughout the shot.\n\n"
    "overall_soundscape:\n"
    "The generated soundscape follows only the audible structure referenced from "
    "<Audio 1> and remains synchronized with the restrained visual action.\n\n"
    "non_diegetic_music:\n"
    "Do not add an unrelated score; follow only the role present in <Audio 1>."
)

TTS_LIPSYNC_RECIPE_NAME = "h3_r2v_refaudio_tts_lipsync"
TTS_LIPSYNC_OUTPUT_PREFIX = "h3_r2v_refaudio_tts_lipsync_out"
TTS_LIPSYNC_SEED43_RECIPE_NAME = "h3_r2v_refaudio_tts_lipsync_seed43"
TTS_LIPSYNC_SEED43_OUTPUT_PREFIX = "h3_r2v_refaudio_tts_lipsync_seed43_out"
TTS_LIPSYNC_ALTERNATE_SEED = 43
TTS_LIPSYNC_PROMPT = (
    "subject_definitions:\n"
    "<Picture 1> is the sole character identity and appearance reference.\n"
    "<Picture 2> is the sole environment, lighting, and composition reference.\n"
    "<Audio 1> is the sole dialogue and timing reference for the target audiovisual generation.\n\n"
    "summary:\n"
    "[reference generation + audio reference] Create a medium close shot of <Picture 1> "
    "speaking directly to camera in the vintage radio control room from <Picture 2>, "
    "with lip movements matching <Audio 1> precisely.\n\n"
    "retention_analysis:\n"
    "<Picture 1>: fully_preserved - Preserve the face, hair, clothing, body proportions, "
    "and recognizable identity.\n"
    "<Picture 2>: fully_preserved - Preserve the room layout, analog equipment, warm "
    "lighting, and spatial composition.\n"
    "<Audio 1>: reference - Use its dialogue timing, phoneme pacing, pauses, vocal rhythm, "
    "and audible structure to guide the newly generated target audio and facial performance.\n\n"
    "detailed_description:\n"
    "The target video is one realistic, restrained medium close shot. [Shot 1] The person "
    "from <Picture 1> faces the camera and speaks naturally in the vintage radio control "
    "room from <Picture 2>. Keep the head, jaw, cheeks, and facial identity stable. Lip and "
    "mouth movements match <Audio 1> precisely throughout, including speech onset, phoneme "
    "changes, pauses, and the final mouth closure. Keep body motion subtle, maintain eye "
    "contact with the camera, and avoid cuts or camera motion that obscures the mouth.\n\n"
    "overall_soundscape:\n"
    "The generated dialogue and restrained room ambience follow <Audio 1> and remain "
    "synchronized with the visible speaking performance.\n\n"
    "non_diegetic_music:\n"
    "Do not add music or an unrelated score."
)


@dataclass(frozen=True)
class Cell:
    key: str
    recipe_name: str
    matrix_role: str
    source_fixture: str
    conditioning_fixture: str
    conditioning_sha256: str
    conditioning_receipt_sha256: str
    output_prefix: str
    render_gate: str


CELLS = (
    Cell(
        key="static_control",
        recipe_name="h3_r2v_refaudio_static_control",
        matrix_role="non-speech-control",
        source_fixture="interstitial_static.wav",
        conditioning_fixture="ltx_matrix_interstitial_static_3p88s_gain_0db.wav",
        conditioning_sha256="ecbcf9a38fb3f6c047ab2fd9ac8b4fdccdaa940e5e5e4d2b2c377f29e904177e",
        conditioning_receipt_sha256="848f4079431df90ebe9f8fa34a19259df458c1ab485ef6d764c9155f8becaaf9",
        output_prefix="h3_r2v_refaudio_static_control_out",
        render_gate="defer until the TTS dialogue smoke passes",
    ),
    Cell(
        key="tts_dialogue",
        recipe_name="h3_r2v_refaudio_tts_dialogue",
        matrix_role="speech-condition",
        source_fixture="tts_dialogue.wav",
        conditioning_fixture="ltx_matrix_tts_dialogue_3p88s_gain_minus5db.wav",
        conditioning_sha256="22489ae40a15ec181d72503f8e238dedf54fa1a803b2d27276b4f32baee5e828",
        conditioning_receipt_sha256="f8d38395c0cc5a313e4440a93662e61ed2e0d6206d3725327c5d1bbd07935928",
        output_prefix="h3_r2v_refaudio_tts_dialogue_out",
        render_gate="first and only authorized smoke before the other two cells",
    ),
    Cell(
        key="music_opening",
        recipe_name="h3_r2v_refaudio_music_opening",
        matrix_role="opening-music-condition",
        source_fixture="music_opening.wav",
        conditioning_fixture="ltx_matrix_music_opening_3p88s_gain_minus12db.wav",
        conditioning_sha256="4a7a474bf92a08109b53a3b0422fca708e105295b6f1a6c4587434d4fa808ce0",
        conditioning_receipt_sha256="7ddc592d2b35e521ad2de09323b779cc19f88dac143af33fb6e486db4da9e194",
        output_prefix="h3_r2v_refaudio_music_opening_out",
        render_gate="defer until the TTS dialogue smoke passes",
    ),
)


BASE_NODE_CLASSES = {
    "1": "UNETLoader",
    "2": "CLIPLoader",
    "3": "VAELoader",
    "4": "VAELoader",
    "5": "RandomNoise",
    "6": "BasicGuider",
    "7": "MiniMaxH3ReferenceToVideo",
    "8": "SamplerCustomAdvanced",
    "9": "VAEDecode",
    "10": "CreateVideo",
    "11": "LoadImage",
    "12": "SaveVideo",
    "13": "KSamplerSelect",
    "14": "BasicScheduler",
    "15": "VAEDecodeAudio",
}
EXPERIMENT_NODE_CLASSES = {
    **BASE_NODE_CLASSES,
    "16": "LoadAudio",
    "17": "LoadImage",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError(f"UTF-8 BOM is forbidden: {path}")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return parsed, raw


def require_file_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} drifted: expected {expected}, found {actual}: {path}")


def validate_installed_schema() -> None:
    """Read the installed source only; never query or boot a ComfyUI server."""
    require_file_hash(
        INSTALLED_NODE_SOURCE,
        EXPECTED_INSTALLED_NODE_SOURCE_SHA256,
        "installed MiniMax H3 node source",
    )
    source = INSTALLED_NODE_SOURCE.read_text(encoding="utf-8")
    required_fragments = (
        'io.Autogrow.Input("ref_images"',
        'io.Autogrow.Input("ref_videos"',
        'io.Autogrow.Input("ref_video_audios"',
        'io.Autogrow.Input("ref_audios"',
        'prefix="ref_audio_", min=0, max=3',
        "for audio in (ref_audios or {}).values()",
    )
    missing = [fragment for fragment in required_fragments if fragment not in source]
    if missing:
        raise RuntimeError(f"Installed MiniMax H3 schema is missing: {missing}")


def load_base_recipe() -> dict[str, Any]:
    require_file_hash(BASE_RECIPE, EXPECTED_BASE_RECIPE_SHA256, "h3_r2v_best base recipe")
    base, _ = read_json(BASE_RECIPE)
    if base.get("name") != "h3_r2v_best":
        raise RuntimeError("Pinned base recipe name is not h3_r2v_best")
    classes = {
        node_id: node.get("class_type") for node_id, node in base.get("prompt", {}).items()
    }
    if classes != BASE_NODE_CLASSES:
        raise RuntimeError(f"Pinned base node set drifted: {classes!r}")
    return base


def receipt_path(cell: Cell) -> Path:
    return AUDIO_RECEIPTS / f"{Path(cell.conditioning_fixture).stem}.json"


def load_audio_receipt(cell: Cell) -> tuple[dict[str, Any], bytes]:
    fixture = FIXTURES / cell.conditioning_fixture
    receipt_file = receipt_path(cell)
    require_file_hash(fixture, cell.conditioning_sha256, f"{cell.key} conditioning fixture")
    require_file_hash(
        receipt_file,
        cell.conditioning_receipt_sha256,
        f"{cell.key} conditioning receipt",
    )
    receipt, raw = read_json(receipt_file)
    probe = receipt.get("ffprobe", {})
    matrix = receipt.get("matrix_window", {})
    if receipt.get("fixture") != cell.conditioning_fixture:
        raise RuntimeError(f"Receipt fixture label mismatch for {cell.key}")
    if receipt.get("sha256") != cell.conditioning_sha256:
        raise RuntimeError(f"Receipt fixture hash mismatch for {cell.key}")
    if receipt.get("ear_gate_pass") is not True:
        raise RuntimeError(f"Audio receipt is not ear-gated for {cell.key}")
    expected_probe = {
        "codec_name": "pcm_f32le",
        "sample_fmt": "flt",
        "sample_rate_hz": AUDIO_SAMPLE_RATE,
        "channels": 1,
        "duration_s": AUDIO_WINDOW_S,
        "duration_samples": AUDIO_SAMPLE_COUNT,
        "time_base": f"1/{AUDIO_SAMPLE_RATE}",
    }
    for field, expected in expected_probe.items():
        if probe.get(field) != expected:
            raise RuntimeError(
                f"{cell.key} receipt {field}={probe.get(field)!r}, expected {expected!r}"
            )
    if matrix.get("duration_s") != AUDIO_WINDOW_S:
        raise RuntimeError(f"{cell.key} matrix window is not exactly {AUDIO_WINDOW_S}s")
    matched = float(matrix.get("matched_lufs"))
    if abs(matched - TARGET_LUFS) > LUFS_TOLERANCE + 1e-6:
        raise RuntimeError(f"{cell.key} loudness is outside the matrix tolerance")
    derived = receipt.get("derived_from", {})
    if derived.get("fixture") != cell.source_fixture:
        raise RuntimeError(f"{cell.key} source fixture provenance mismatch")
    return receipt, raw


def evidence_metadata() -> dict[str, Any]:
    return {
        "official": [
            {
                "url": "https://docs.comfy.org/tutorials/video/minimax/minimax-h3",
                "trust": "ComfyUI official documentation",
                "use": "Ref2VA socket limits and exact-order reference tags",
            },
            {
                "url": (
                    "https://github.com/Comfy-Org/ComfyUI/blob/"
                    f"{COMFYUI_GIT_COMMIT}/comfy_extras/nodes_minimax_h3.py#L154-L280"
                ),
                "trust": "installed official ComfyUI core source",
                "license": "GPL-3.0",
                "use": "autogrow reference sockets and genuine audio-latent conditioning",
            },
            {
                "url": "https://huggingface.co/MiniMaxAI/MiniMax-H3",
                "trust": "MiniMax model-author model card",
                "license": "MiniMax H3 Community License Agreement",
                "use": "Ref2VA audio duration and mixed-input contract",
            },
            {
                "url": (
                    "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/"
                    "VIDEO_PROMPT_WRITING_GUIDE_ref_en.md"
                ),
                "trust": "MiniMax model-author prompt guide",
                "license": "MiniMax H3 Community License Agreement",
                "use": "<Audio N> reference-versus-copy semantics",
            },
            {
                "url": (
                    "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/scripts/readme/"
                    "reproducible-768p-ref2va-request.sh"
                ),
                "trust": "MiniMax model-author reproducible Ref2VA request",
                "license": "MiniMax H3 Community License Agreement",
                "use": "reference-video soundtrack then standalone-audio label ordering",
            },
            {
                "url": (
                    "https://github.com/Comfy-Org/workflow_templates/blob/main/templates/"
                    "video_minimax_h3_r2v.json"
                ),
                "trust": "Comfy-Org official frozen topology",
                "license": "MIT",
                "use": "sampler and native target AV decode topology",
                "caveat": "its audio sockets are present but unwired",
            },
        ],
        "community_topology_evidence_only": [
            {
                "url": (
                    "https://github.com/sobaya-0141/Seedance_Madogiwa/blob/"
                    "b27546d848121f2c5f3f687dea00bf4f37523cff/03_SCRIPTS/"
                    "26_kansha_no_bug_ichimankai/ch8_workflow.json"
                ),
                "license": "no repository license found",
                "trust": "validator-accepted API graph; author reported no completed H3 render",
                "use": "topology corroboration only",
                "copied": False,
            },
            {
                "url": (
                    "https://github.com/jtydhr88/ComfyTV/blob/"
                    "4d1f882e4793d3a22d86e6dec60d829ab16e2252/workflows/video/"
                    "local-minimax-h3-r2v.json"
                ),
                "license": "MIT",
                "trust": "maintained community workflow",
                "use": "paired reference-video soundtrack corroboration only",
                "copied": False,
            },
        ],
        "rejected_as_implementation_source": [
            {
                "url": (
                    "https://github.com/Shrek3OnVH5/"
                    "MiniMax-H3-NativeAudio-MusicVideo-Workflow"
                ),
                "license": "no repository license found",
                "reason": "custom NativeAudioLock and direct exact-audio mux confound conditioning",
                "copied": False,
            }
        ],
        "no_license_caveat": (
            "Unlicensed community JSON was inspected only to corroborate socket topology. "
            "This builder and every generated node/value originate from the pinned local "
            "h3_r2v_best recipe, official source contracts, and lab-owned fixtures."
        ),
    }


def topology_contract() -> dict[str, Any]:
    absent_sockets = [
        *(f"7.ref_images.ref_image_{index}" for index in range(2, 9)),
        *(f"7.ref_videos.ref_video_{index}" for index in range(3)),
        *(f"7.ref_video_audios.ref_video_audio_{index}" for index in range(3)),
        *(f"7.ref_audios.ref_audio_{index}" for index in range(1, 3)),
    ]
    connections = {
        "6.model": ["1", 0],
        "6.conditioning": ["7", 0],
        "7.clip": ["2", 0],
        "7.vae": ["3", 0],
        "7.audio_vae": ["4", 0],
        "7.ref_images.ref_image_0": ["11", 0],
        "7.ref_images.ref_image_1": ["17", 0],
        "7.ref_audios.ref_audio_0": ["16", 0],
        "8.noise": ["5", 0],
        "8.guider": ["6", 0],
        "8.sampler": ["13", 0],
        "8.sigmas": ["14", 0],
        "8.latent_image": ["7", 1],
        "14.model": ["1", 0],
        "9.samples": ["8", 0],
        "9.vae": ["3", 0],
        "15.samples": ["8", 0],
        "15.vae": ["4", 0],
        "10.images": ["9", 0],
        "10.audio": ["15", 0],
        "12.video": ["10", 0],
    }
    return {
        "schema_version": 1,
        "profile": "minimax_h3_ref2va_external_audio_diagnostic_v1",
        "intent": (
            "Official Ref2VA conditioning and sampler topology with one standalone "
            "reference WAV; saved audio is model-native target latent decode only"
        ),
        "origin": {
            "builder": "scratch/build_h3_refaudio_matrix.py",
            "base_recipe": "recipes/h3_r2v_best.json",
            "base_recipe_sha256": EXPECTED_BASE_RECIPE_SHA256,
            "original_implementation": True,
            "third_party_workflow_json_copied": False,
        },
        "frozen_template": {
            "path": "research/comfy_templates/video_minimax_h3_r2v.json",
            "sha256": EXPECTED_FROZEN_TEMPLATE_SHA256,
        },
        "installed_schema": {
            "comfyui_version": COMFYUI_VERSION,
            "git_commit": COMFYUI_GIT_COMMIT,
            "node_source": "comfy_extras/nodes_minimax_h3.py",
            "node_source_sha256": EXPECTED_INSTALLED_NODE_SOURCE_SHA256,
            "schema_lines": "154-198",
            "execution_lines": "200-280",
            "reference_socket_paths": [
                "ref_images.ref_image_0",
                "ref_images.ref_image_1",
                "ref_audios.ref_audio_0",
            ],
        },
        "fixture_hashes": {
            "portrait.png": PORTRAIT_SHA256,
            "scene_still.png": SCENE_STILL_SHA256,
        },
        "exact_node_set": True,
        "required_nodes": EXPERIMENT_NODE_CLASSES,
        "required_class_types": list(dict.fromkeys(EXPERIMENT_NODE_CLASSES.values())),
        "required_connections": connections,
        "required_absent_inputs": [
            "7.ref_videos",
            "7.ref_video_audios",
            "7.first_frame",
            "7.last_frame",
            *absent_sockets,
        ],
        "required_absent_sockets": absent_sockets,
        "required_input_values": [
            {"node": "1", "input": "unet_name", "equals": UNET_NAME},
            {"node": "1", "input": "weight_dtype", "equals": "default"},
            {"node": "2", "input": "clip_name", "equals": CLIP_NAME},
            {"node": "2", "input": "type", "equals": "minimax"},
            {"node": "2", "input": "device", "equals": "default"},
            {"node": "3", "input": "vae_name", "equals": VIDEO_VAE_NAME},
            {"node": "4", "input": "vae_name", "equals": AUDIO_VAE_NAME},
            {"node": "5", "input": "noise_seed", "equals": SEED},
            {"node": "7", "input": "prompt", "equals": SHARED_PROMPT},
            {"node": "7", "input": "width", "equals": WIDTH},
            {"node": "7", "input": "height", "equals": HEIGHT},
            {"node": "7", "input": "length", "equals": FRAMES},
            {"node": "7", "input": "ref_image_size", "equals": "match"},
            {"node": "11", "input": "image", "equals": "portrait.png"},
            {"node": "17", "input": "image", "equals": "scene_still.png"},
            {"node": "13", "input": "sampler_name", "equals": "res_multistep"},
            {"node": "14", "input": "scheduler", "equals": "simple"},
            {"node": "14", "input": "steps", "equals": 20},
            {"node": "14", "input": "denoise", "equals": 1.0},
            {"node": "10", "input": "fps", "equals": FPS},
            {"node": "10", "input": "bit_depth", "equals": 8},
        ],
        "forbidden_class_types": [
            "KSampler",
            "CLIPTextEncode",
            "TrimAudioDuration",
            "AudioAdjustVolume",
            "VHS_LoadAudio",
            "H3ReferenceAudio",
            "MiniMaxH3NativeAudioLock",
            "VRGDG_MiniMaxH3AudioDrive",
        ],
        "audio_path_contract": {
            "conditioning_source": "16.LoadAudio -> 7.ref_audios.ref_audio_0",
            "sampled_target": "7.LATENT -> 8.SamplerCustomAdvanced -> 15.VAEDecodeAudio",
            "delivery": "15.AUDIO -> 10.CreateVideo.audio",
            "create_video_audio_required": ["15", 0],
            "create_video_audio_forbidden": ["16", 0],
            "external_source_mux": False,
        },
        "terminal_node": "12",
        "require_all_nodes_reachable": True,
        "matrix_diff_whitelist": [
            "name",
            "experiment.*",
            "prompt.16.inputs.audio",
            "prompt.12.inputs.filename_prefix",
        ],
        "intentional_divergences": [
            "The official UI subgraph is flattened to the pinned local API prompt",
            "The 864x480 lab canvas and deterministic seed 42 replace best-lane dimensions",
            "portrait.png and scene_still.png are ordered as Picture 1 and Picture 2",
            "one receipt-bound 3.88-second WAV is ordered as Audio 1",
            "optional reference videos and paired reference-video soundtracks are absent",
            "source audio never connects to CreateVideo; only sampled target audio is decoded",
        ],
        "evidence": evidence_metadata(),
    }


def make_experiment_metadata(
    cell: Cell, receipt: dict[str, Any], receipt_bytes: bytes
) -> dict[str, Any]:
    matrix = receipt["matrix_window"]
    return {
        "campaign": "h3_ref2va_external_audio_reference_v1",
        "variant": cell.key,
        "matrix_role": cell.matrix_role,
        "independent_variable": "reference_audio_waveform",
        "source_fixture": cell.source_fixture,
        "conditioning_fixture": cell.conditioning_fixture,
        "conditioning_sha256": cell.conditioning_sha256,
        "conditioning_receipt": (
            f"fixtures/audio_receipts/{Path(cell.conditioning_fixture).stem}.json"
        ),
        "conditioning_receipt_sha256": sha256_bytes(receipt_bytes),
        "window_start_s": 0.0,
        "window_duration_s": AUDIO_WINDOW_S,
        "sample_rate_hz": AUDIO_SAMPLE_RATE,
        "sample_count": AUDIO_SAMPLE_COUNT,
        "channels": 1,
        "sample_format": "pcm_f32le",
        "gain_db": matrix["gain_db"],
        "target_lufs": matrix["target_lufs"],
        "measured_lufs": matrix["matched_lufs"],
        "prompt_policy": "byte-identical modality-neutral prompt across all cells",
        "conditioning_policy": "LoadAudio feeds only Ref2VA ref_audios.ref_audio_0",
        "output_audio_policy": (
            "CreateVideo receives only VAEDecodeAudio decoded from the sampled target AV latent"
        ),
        "external_source_mux": False,
        "render_status": "unrendered",
        "render_gate": cell.render_gate,
    }


def build_recipe(
    base: dict[str, Any],
    cell: Cell,
    receipt: dict[str, Any],
    receipt_bytes: bytes,
) -> dict[str, Any]:
    prompt = copy.deepcopy(base["prompt"])
    prompt["2"]["inputs"]["device"] = "default"
    prompt["5"]["inputs"]["noise_seed"] = SEED
    prompt["11"]["inputs"]["image"] = "portrait.png"
    prompt["16"] = {
        "class_type": "LoadAudio",
        "inputs": {"audio": cell.conditioning_fixture},
    }
    prompt["17"] = {
        "class_type": "LoadImage",
        "inputs": {"image": "scene_still.png"},
    }

    conditioning = prompt["7"]["inputs"]
    conditioning.update(
        {
            "clip": ["2", 0],
            "vae": ["3", 0],
            "audio_vae": ["4", 0],
            "prompt": SHARED_PROMPT,
            "width": WIDTH,
            "height": HEIGHT,
            "length": FRAMES,
            "ref_image_size": "match",
            "ref_images.ref_image_0": ["11", 0],
            "ref_images.ref_image_1": ["17", 0],
            "ref_audios.ref_audio_0": ["16", 0],
        }
    )
    for absent in (
        "ref_images",
        "ref_audios",
        "ref_videos",
        "ref_video_audios",
        "first_frame",
        "last_frame",
    ):
        conditioning.pop(absent, None)

    prompt["13"]["inputs"]["sampler_name"] = "res_multistep"
    prompt["14"]["inputs"].update(
        {"model": ["1", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}
    )
    prompt["10"]["inputs"].update(
        {"images": ["9", 0], "audio": ["15", 0], "fps": FPS, "bit_depth": 8}
    )
    prompt["12"]["inputs"]["filename_prefix"] = cell.output_prefix
    prompt = dict(sorted(prompt.items(), key=lambda item: int(item[0])))

    recipe = {
        "name": cell.recipe_name,
        "tier": "experiment",
        "blocked": False,
        "experiment": make_experiment_metadata(cell, receipt, receipt_bytes),
        "contract": {
            "engine": "minimax_h3",
            "mode": "r2v_refaudio",
            "width": WIDTH,
            "height": HEIGHT,
            "frames": FRAMES,
            "fps": FPS,
            "duration_s": round(FRAMES / FPS, 2),
            "reference_audio_duration_s": AUDIO_WINDOW_S,
            "requires_audio": True,
            "required_boot_lane": "lab-8199, sage-free",
            "vram_ceiling_gb": 14.5,
        },
        "topology_contract": topology_contract(),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }
    validate_recipe(recipe, cell)
    return recipe


def iter_links(value: Any, path: str = "") -> Iterator[tuple[str, str, int]]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    ):
        yield path, value[0], value[1]


def validate_dag(prompt: dict[str, Any], recipe_name: str) -> None:
    node_ids = set(prompt)
    incoming = {node_id: set() for node_id in node_ids}
    outgoing = {node_id: set() for node_id in node_ids}
    for target_id, node in prompt.items():
        for input_name, value in node.get("inputs", {}).items():
            for socket_path, source_id, output_index in iter_links(value, input_name):
                if source_id not in node_ids:
                    raise RuntimeError(
                        f"{recipe_name}: {target_id}.{socket_path} has missing source {source_id}"
                    )
                if output_index < 0:
                    raise RuntimeError(
                        f"{recipe_name}: {target_id}.{socket_path} has invalid output index"
                    )
                incoming[target_id].add(source_id)
                outgoing[source_id].add(target_id)

    original_incoming = copy.deepcopy(incoming)
    ready = sorted((node_id for node_id, sources in incoming.items() if not sources), key=int)
    visited: list[str] = []
    while ready:
        node_id = ready.pop(0)
        visited.append(node_id)
        for target_id in sorted(outgoing[node_id], key=int):
            incoming[target_id].remove(node_id)
            if not incoming[target_id]:
                ready.append(target_id)
                ready.sort(key=int)
    if len(visited) != len(node_ids):
        raise RuntimeError(f"{recipe_name}: graph contains a cycle")

    sinks = [
        node_id for node_id, node in prompt.items() if node.get("class_type") == "SaveVideo"
    ]
    if sinks != ["12"]:
        raise RuntimeError(f"{recipe_name}: expected SaveVideo sink node 12, found {sinks}")
    reachable = {"12"}
    stack = ["12"]
    while stack:
        target_id = stack.pop()
        for source_id in original_incoming[target_id]:
            if source_id not in reachable:
                reachable.add(source_id)
                stack.append(source_id)
    if reachable != node_ids:
        missing = sorted(node_ids - reachable, key=int)
        raise RuntimeError(f"{recipe_name}: nodes do not reach SaveVideo: {missing}")


def source_consumers(prompt: dict[str, Any], source_node: str) -> set[tuple[str, str]]:
    consumers: set[tuple[str, str]] = set()
    for target_id, node in prompt.items():
        for input_name, value in node.get("inputs", {}).items():
            for socket_path, source_id, _ in iter_links(value, input_name):
                if source_id == source_node:
                    consumers.add((target_id, socket_path))
    return consumers


def validate_recipe(
    recipe: dict[str, Any],
    cell: Cell,
    expected_prompt: str = SHARED_PROMPT,
    expected_name: str | None = None,
) -> None:
    prompt = recipe.get("prompt", {})
    classes = {node_id: node.get("class_type") for node_id, node in prompt.items()}
    if classes != EXPERIMENT_NODE_CLASSES:
        raise RuntimeError(f"{cell.key}: exact node set mismatch: {classes!r}")
    if recipe.get("name") != (expected_name or cell.recipe_name):
        raise RuntimeError(f"{cell.key}: recipe identity mismatch")
    if prompt["16"]["inputs"] != {"audio": cell.conditioning_fixture}:
        raise RuntimeError(f"{cell.key}: LoadAudio does not name the receipt-bound WAV")

    ref_inputs = prompt["7"]["inputs"]
    nested_groups = {"ref_images", "ref_audios", "ref_videos", "ref_video_audios"}
    if nested_groups & ref_inputs.keys():
        raise RuntimeError(f"{cell.key}: V3 Autogrow inputs must use flat dotted sockets")
    expected_images = {
        "ref_images.ref_image_0": ["11", 0],
        "ref_images.ref_image_1": ["17", 0],
    }
    if {key: ref_inputs.get(key) for key in expected_images} != expected_images:
        raise RuntimeError(f"{cell.key}: exact Picture ordering changed")
    if ref_inputs.get("ref_audios.ref_audio_0") != ["16", 0]:
        raise RuntimeError(f"{cell.key}: exact Audio ordering changed")
    if ref_inputs.get("prompt") != expected_prompt:
        raise RuntimeError(f"{cell.key}: expected action prompt changed")
    tags = set(re.findall(r"<(?:Picture|Video|Audio) \d+>", expected_prompt))
    if tags != {"<Picture 1>", "<Picture 2>", "<Audio 1>"}:
        raise RuntimeError(f"Expected reference tags changed: {tags}")

    if source_consumers(prompt, "16") != {("7", "ref_audios.ref_audio_0")}:
        raise RuntimeError(f"{cell.key}: source WAV escapes the Ref2VA conditioning socket")
    if prompt["15"]["inputs"] != {"samples": ["8", 0], "vae": ["4", 0]}:
        raise RuntimeError(f"{cell.key}: native target audio decode path changed")
    if prompt["10"]["inputs"].get("audio") != ["15", 0]:
        raise RuntimeError(f"{cell.key}: CreateVideo.audio is not native target decode")
    if prompt["10"]["inputs"].get("audio") == ["16", 0]:
        raise RuntimeError(f"{cell.key}: forbidden source mux detected")
    validate_dag(prompt, expected_name or cell.recipe_name)


def normalized_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(recipe)
    normalized["name"] = "<cell-name>"
    normalized["experiment"] = "<cell-experiment>"
    normalized["prompt"]["16"]["inputs"]["audio"] = "<cell-audio>"
    normalized["prompt"]["12"]["inputs"]["filename_prefix"] = "<cell-prefix>"
    return normalized


def difference_paths(left: Any, right: Any, path: str = "") -> set[str]:
    if type(left) is not type(right):
        return {path or "<root>"}
    if isinstance(left, dict):
        paths: set[str] = set()
        for key in set(left) | set(right):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                paths.add(child_path)
            else:
                paths.update(difference_paths(left[key], right[key], child_path))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return {path}
        paths: set[str] = set()
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            paths.update(difference_paths(left_item, right_item, f"{path}[{index}]"))
        return paths
    return set() if left == right else {path}


def pairwise_path_is_allowed(path: str) -> bool:
    return (
        path == "name"
        or path == "experiment"
        or path.startswith("experiment.")
        or path == "prompt.16.inputs.audio"
        or path == "prompt.12.inputs.filename_prefix"
    )


def validate_matrix(recipes: list[dict[str, Any]]) -> None:
    if len(recipes) != len(CELLS):
        raise RuntimeError("RefAudio matrix must contain exactly three cells")
    baseline = normalized_recipe(recipes[0])
    for recipe in recipes[1:]:
        if normalized_recipe(recipe) != baseline:
            raise RuntimeError(f"Graph drift outside matrix variables: {recipe['name']}")
    for index, left in enumerate(recipes):
        for right in recipes[index + 1 :]:
            paths = difference_paths(left, right)
            forbidden = sorted(path for path in paths if not pairwise_path_is_allowed(path))
            if forbidden:
                raise RuntimeError(
                    f"Pairwise drift {left['name']} vs {right['name']}: {forbidden}"
                )


def build_matrix() -> list[dict[str, Any]]:
    require_file_hash(
        FROZEN_TEMPLATE,
        EXPECTED_FROZEN_TEMPLATE_SHA256,
        "frozen official MiniMax H3 R2V template",
    )
    require_file_hash(FIXTURES / "portrait.png", PORTRAIT_SHA256, "portrait fixture")
    require_file_hash(FIXTURES / "scene_still.png", SCENE_STILL_SHA256, "scene fixture")
    validate_installed_schema()
    base = load_base_recipe()
    recipes: list[dict[str, Any]] = []
    for cell in CELLS:
        receipt, receipt_bytes = load_audio_receipt(cell)
        recipes.append(build_recipe(base, cell, receipt, receipt_bytes))
    validate_matrix(recipes)
    return recipes


def load_tts_dialogue_source() -> dict[str, Any]:
    """Load and prove the exact immutable source recipe for the prompt-only clone."""
    require_file_hash(
        TTS_DIALOGUE_RECIPE,
        EXPECTED_TTS_DIALOGUE_RECIPE_SHA256,
        "h3_r2v_refaudio_tts_dialogue clone source",
    )
    source, _ = read_json(TTS_DIALOGUE_RECIPE)
    generated = next(
        recipe
        for recipe in build_matrix()
        if recipe["name"] == "h3_r2v_refaudio_tts_dialogue"
    )
    if source != generated:
        raise RuntimeError("Committed TTS dialogue recipe is not its canonical builder output")
    return source


def build_tts_lipsync_prompt_clone() -> dict[str, Any]:
    """Clone the proven TTS cell, changing only prompt experiment identity."""
    source = load_tts_dialogue_source()
    recipe = copy.deepcopy(source)
    recipe["name"] = TTS_LIPSYNC_RECIPE_NAME

    experiment = copy.deepcopy(source["experiment"])
    experiment.update(
        {
            "campaign": "h3_ref2va_tts_prompt_followup_v1",
            "variant": "tts_lipsync_prompt",
            "matrix_role": "prompt-only speaking-to-camera follow-up",
            "independent_variable": "action_prompt",
            "prompt_policy": (
                "Only the action prompt changes from the hash-pinned TTS dialogue "
                "recipe; graph, fixtures, seed, scheduler, dimensions, and audio paths stay exact"
            ),
            "clone_source_recipe": "recipes/h3_r2v_refaudio_tts_dialogue.json",
            "clone_source_recipe_sha256": EXPECTED_TTS_DIALOGUE_RECIPE_SHA256,
            "action_prompt": (
                "medium close shot of <Picture 1> speaking to camera, with lip "
                "movements matching <Audio 1> precisely"
            ),
            "behavioral_claim_status": "unrendered and unproven",
            "render_status": "unrendered",
            "render_gate": "separately authorized prompt-only follow-up",
            "execution_graph_diff_whitelist": [
                "prompt.7.inputs.prompt",
                "prompt.12.inputs.filename_prefix",
            ],
        }
    )
    recipe["experiment"] = experiment
    recipe["prompt"]["7"]["inputs"]["prompt"] = TTS_LIPSYNC_PROMPT
    recipe["prompt"]["12"]["inputs"][
        "filename_prefix"
    ] = TTS_LIPSYNC_OUTPUT_PREFIX

    prompt_assertions = [
        assertion
        for assertion in recipe["topology_contract"]["required_input_values"]
        if (assertion.get("node"), assertion.get("input")) == ("7", "prompt")
    ]
    if len(prompt_assertions) != 1:
        raise RuntimeError(
            f"Expected one mirrored prompt topology assertion, found {len(prompt_assertions)}"
        )
    prompt_assertions[0]["equals"] = TTS_LIPSYNC_PROMPT

    cell = next(cell for cell in CELLS if cell.key == "tts_dialogue")
    validate_recipe(
        recipe,
        cell,
        expected_prompt=TTS_LIPSYNC_PROMPT,
        expected_name=TTS_LIPSYNC_RECIPE_NAME,
    )
    return recipe


def load_tts_lipsync_seed42_source() -> dict[str, Any]:
    """Load and prove the exact immutable seed-42 lipsync recipe."""
    require_file_hash(
        TTS_LIPSYNC_SEED42_RECIPE,
        EXPECTED_TTS_LIPSYNC_SEED42_RECIPE_SHA256,
        "h3_r2v_refaudio_tts_lipsync seed-42 clone source",
    )
    source, _ = read_json(TTS_LIPSYNC_SEED42_RECIPE)
    if source != build_tts_lipsync_prompt_clone():
        raise RuntimeError(
            "Committed seed-42 lipsync recipe is not its canonical builder output"
        )
    return source


def build_tts_lipsync_seed43_clone() -> dict[str, Any]:
    """Clone the lipsync take with seed as its sole model-execution variable."""
    source = load_tts_lipsync_seed42_source()
    recipe = copy.deepcopy(source)
    recipe["name"] = TTS_LIPSYNC_SEED43_RECIPE_NAME

    experiment = copy.deepcopy(source["experiment"])
    experiment.update(
        {
            "campaign": "h3_ref2va_tts_seed_followup_v1",
            "variant": "tts_lipsync_seed43",
            "matrix_role": "prompt-identical alternate-seed lipsync take",
            "independent_variable": "random_noise_seed",
            "seed_policy": (
                "The RandomNoise seed is the sole model-execution variable from the "
                "hash-pinned seed-42 lipsync take; the unique name and SaveVideo prefix "
                "only isolate artifacts"
            ),
            "clone_source_recipe": "recipes/h3_r2v_refaudio_tts_lipsync.json",
            "clone_source_recipe_sha256": (
                EXPECTED_TTS_LIPSYNC_SEED42_RECIPE_SHA256
            ),
            "source_seed": SEED,
            "alternate_seed": TTS_LIPSYNC_ALTERNATE_SEED,
            "behavioral_claim_status": "unrendered and unproven",
            "render_status": "unrendered",
            "render_gate": "separately authorized alternate-seed follow-up",
            "execution_graph_diff_whitelist": [
                "prompt.5.inputs.noise_seed",
                "prompt.12.inputs.filename_prefix",
            ],
        }
    )
    recipe["experiment"] = experiment
    recipe["prompt"]["5"]["inputs"]["noise_seed"] = TTS_LIPSYNC_ALTERNATE_SEED
    recipe["prompt"]["12"]["inputs"][
        "filename_prefix"
    ] = TTS_LIPSYNC_SEED43_OUTPUT_PREFIX

    seed_assertions = [
        assertion
        for assertion in recipe["topology_contract"]["required_input_values"]
        if (assertion.get("node"), assertion.get("input"))
        == ("5", "noise_seed")
    ]
    if len(seed_assertions) != 1:
        raise RuntimeError(
            "Expected one mirrored 5.noise_seed topology assertion, "
            f"found {len(seed_assertions)}"
        )
    seed_assertions[0]["equals"] = TTS_LIPSYNC_ALTERNATE_SEED
    recipe["topology_contract"]["required_input_values"].append(
        {
            "node": "12",
            "input": "filename_prefix",
            "equals": TTS_LIPSYNC_SEED43_OUTPUT_PREFIX,
        }
    )

    execution_diff = difference_paths(source["prompt"], recipe["prompt"])
    expected_diff = {
        "5.inputs.noise_seed",
        "12.inputs.filename_prefix",
    }
    if execution_diff != expected_diff:
        raise RuntimeError(
            f"Seed-43 lipsync execution drift is not isolated: {sorted(execution_diff)}"
        )
    if recipe["prompt"]["7"]["inputs"]["prompt"] != source["prompt"]["7"][
        "inputs"
    ]["prompt"]:
        raise RuntimeError("Seed-43 lipsync action prompt changed from seed 42")

    cell = next(cell for cell in CELLS if cell.key == "tts_dialogue")
    validate_recipe(
        recipe,
        cell,
        expected_prompt=TTS_LIPSYNC_PROMPT,
        expected_name=TTS_LIPSYNC_SEED43_RECIPE_NAME,
    )
    return recipe


def immutable_write(path: Path, payload: bytes) -> bool:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Immutable generated recipe differs: {path}")
        return False
    path.write_bytes(payload)
    return True


def write_all(output_dir: Path = RECIPES) -> dict[str, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}
    for recipe in build_matrix():
        path = output_dir / f"{recipe['name']}.json"
        payload = canonical_json_bytes(recipe)
        changed = immutable_write(path, payload)
        parsed, raw = read_json(path)
        if parsed != recipe or raw != payload:
            raise RuntimeError(f"Generated recipe did not round-trip byte-exactly: {path}")
        results[recipe["name"]] = changed
    return results


def write_tts_lipsync_prompt_clone(output_dir: Path = RECIPES) -> bool:
    """Create the prompt-only follow-up once and reject any later byte drift."""
    output_dir.mkdir(parents=True, exist_ok=True)
    recipe = build_tts_lipsync_prompt_clone()
    path = output_dir / f"{TTS_LIPSYNC_RECIPE_NAME}.json"
    payload = canonical_json_bytes(recipe)
    changed = immutable_write(path, payload)
    parsed, raw = read_json(path)
    if parsed != recipe or raw != payload:
        raise RuntimeError(f"Generated prompt clone did not round-trip byte-exactly: {path}")
    return changed


def write_tts_lipsync_seed43_clone(output_dir: Path = RECIPES) -> bool:
    """Create the prompt-identical alternate-seed take and reject byte drift."""
    output_dir.mkdir(parents=True, exist_ok=True)
    recipe = build_tts_lipsync_seed43_clone()
    path = output_dir / f"{TTS_LIPSYNC_SEED43_RECIPE_NAME}.json"
    payload = canonical_json_bytes(recipe)
    changed = immutable_write(path, payload)
    parsed, raw = read_json(path)
    if parsed != recipe or raw != payload:
        raise RuntimeError(
            f"Generated seed-43 lipsync clone did not round-trip byte-exactly: {path}"
        )
    return changed


def main() -> None:
    for name, changed in write_all().items():
        action = "created" if changed else "unchanged"
        print(f"{name}: {action}")
    clone_changed = write_tts_lipsync_prompt_clone()
    action = "created" if clone_changed else "unchanged"
    print(f"{TTS_LIPSYNC_RECIPE_NAME}: {action}")
    seed43_changed = write_tts_lipsync_seed43_clone()
    action = "created" if seed43_changed else "unchanged"
    print(f"{TTS_LIPSYNC_SEED43_RECIPE_NAME}: {action}")


if __name__ == "__main__":
    main()
