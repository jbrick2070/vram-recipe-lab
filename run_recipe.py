#!/usr/bin/env python3
"""
run_recipe.py — Recipe execution runner and preflight enforcement harness
for ComfyUI workflow VRAM recipe benchmarking.

Talks to lab server at http://127.0.0.1:8199.
Self-boots lab server via boot_lab_server.cmd if down, tracking PID in .server.pid.
Windows 11 / RTX 5080 Laptop (16 GB, 14.5 GB gate ceiling).
"""

import os
import sys
import time
import json
import copy
import csv
import hashlib
import importlib.util
import io
import math
import re
import stat
import statistics
import psutil
import shutil
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import lab_locks

# --- Constants & Paths ---
REPO_ROOT = Path(__file__).parent.resolve()
LOCKFILE_PATH = REPO_ROOT / ".gpu.lock"
SUITE_LOCKFILE_PATH = REPO_ROOT / ".suite.lock"
COORDINATOR_MUTEX_PATH = REPO_ROOT / ".coordinator.mutex"
LAB_LOCKS_SOURCE_PATH = Path(lab_locks.__file__).resolve()
QUEUE_QUARANTINE_PATH = REPO_ROOT / ".queue.quarantine.json"
SERVER_PID_FILE = REPO_ROOT / ".server.pid"
SERVER_IDLE_GATE_FILE = REPO_ROOT / ".server.idle-gate.json"
SERVER_LOG_FILE = REPO_ROOT / "server.log"
BOOT_CMD = REPO_ROOT / "boot_lab_server.cmd"
RESULTS_DIR = REPO_ROOT / "results"
FIXTURES_DIR = REPO_ROOT / "fixtures"
AUDIO_RECEIPTS_DIR = FIXTURES_DIR / "audio_receipts"
MODELS_MANIFEST = REPO_ROOT / "models_manifest.md"
RESULTS_LEDGER = REPO_ROOT / "RESULTS.md"
ENGINE_MATRIX_BETA = REPO_ROOT / "ENGINE_MATRIX_BETA.md"
COMFYUI_ROOT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI")
MODEL_ROOTS = [
    Path(r"C:\ComfyUI-Models\checkpoints"),
    Path(r"C:\ComfyUI-Models\diffusion_models"),
    Path(r"C:\ComfyUI-Models\unet"),
    Path(r"C:\ComfyUI-Models\text_encoders"),
    Path(r"C:\ComfyUI-Models\clip"),
    Path(r"C:\ComfyUI-Models\vae"),
    Path(r"C:\ComfyUI-Models\loras"),
    Path(r"C:\ComfyUI-Models\upscale_models"),
    Path(r"C:\ComfyUI-Models\latent_upscale_models"),
    Path(r"C:\ComfyUI-Models\audio_encoders"),
    Path(r"C:\ComfyUI-Models\model_patches"),
]

LAB_PORT = "8199"
COMFY_SERVER_URL = f"http://127.0.0.1:{LAB_PORT}"
VRAM_GATE_GB = 14.5
RECEIPT_SCHEMA_VERSION = 3
# Operator-authorized desktop-use lane.  A render may start with ordinary
# desktop applications attached to the WDDM GPU, but the measured absolute
# desktop baseline must not exceed 3.0 GiB.  The independent 14.5 GiB absolute
# peak gate remains authoritative during the render itself, while known render
# and compute workloads remain hard pre-boot and pre-prompt blockers.
GPU_IDLE_STANDARD_BASELINE_MAX_MB = 2048
GPU_IDLE_BASELINE_MAX_MB = 3072
GPU_IDLE_ELEVATED_BASELINE_STAMP = (
    "elevated-baseline lane, operator-authorized 2026-08-10"
)
GPU_IDLE_INDEX = 0
GPU_IDLE_SAMPLE_COUNT = 5
GPU_IDLE_SAMPLE_INTERVAL_S = 0.2
GPU_IDLE_WDDM_UNMETERED_MEMORY_TOKEN = "[N/A]"
GPU_IDLE_REQUIRED_DRIVER_MODEL = "WDDM"
GPU_IDLE_DISPLAY_ACTIVE_MEASURED_STATES = frozenset({"Enabled", "Disabled"})
GPU_IDLE_EVIDENCE_KEY = "preboot_gpu_idle_gate"
GPU_IDLE_INTERNAL_STATS_KEY = "_vram_lab_preboot_gpu_idle_gate"
GPU_IDLE_SIDECAR_KEY = "preboot_gpu_idle_gate_sidecar"
GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY = "_vram_lab_preboot_gpu_idle_gate_sidecar"
PREQUEUE_WORKLOAD_SCAN_EVIDENCE_KEY = "prequeue_known_workload_scan"
PREQUEUE_WORKLOAD_SCAN_CONTRACT_KEY = "prequeue_known_workload_scan_contract"
GPU_IDLE_CURRENT_RUNNER_EXCLUSION_SCHEMA = (
    "pid",
    "process_create_time",
    "resolved_runner_path",
    "narrowly_verified",
    "excluded_pid_only",
    "process_identity",
    "verified_windows_venv_launcher",
    "expected_excluded_process_count",
)
GPU_IDLE_VERIFIED_VENV_LAUNCHER_SCHEMA = (
    "pid",
    "process_create_time",
    "expected_launcher_path",
    "direct_child_pid",
    "direct_parent_verified",
    "launcher_identity_live",
    "child_identity_live",
    "argv_tail_matches_child",
    "both_exact_runner_target",
    "child_executable_differs",
    "creation_delta_s",
    "narrowly_verified",
    "excluded_pid_only",
    "process_identity",
)
GPU_IDLE_EXCLUDED_CURRENT_RUNNER_ROW_SCHEMA = (
    "pid",
    "process_create_time",
    "reason",
)
PREQUEUE_OWNED_SERVER_EXCLUSION_SCHEMA = (
    "pid",
    "process_create_time",
    "server_instance",
    "process_identity",
    "argv_match",
    "narrowly_verified",
    "excluded_pid_only",
    "verified_windows_venv_launcher",
    "expected_excluded_process_count",
)
PREQUEUE_VERIFIED_SERVER_VENV_LAUNCHER_SCHEMA = (
    "pid",
    "process_create_time",
    "expected_launcher_path",
    "direct_child_pid",
    "direct_parent_verified",
    "launcher_identity_live",
    "child_identity_live",
    "argv_tail_matches_child",
    "both_exact_validated_server_argv",
    "child_executable_differs",
    "creation_delta_s",
    "narrowly_verified",
    "excluded_pid_only",
    "process_identity",
    "argv_match",
)
PREQUEUE_EXCLUDED_OWNED_SERVER_ROW_SCHEMA = (
    "pid",
    "process_create_time",
    "reason",
)
GPU_IDLE_PROCESS_IDENTITY_SCHEMA = (
    "pid",
    "exists",
    "name",
    "executable",
    "command_line",
    "process_create_time",
    "identity_errors",
)
GPU_IDLE_MODEL_WORKLOAD_MARKERS = (
    "main.py",
    "run_recipe.py",
    "torchrun",
    "stable-diffusion",
    "automatic1111",
    "invokeai",
    "diffusers",
    "text-generation",
    "vllm",
    "ollama",
    "kobold",
    "eng_wan_",
    "eng_fastwan_",
    "eng_humo",
    "minimax",
)
MIN_FREE_DISK_GB = 5.0
BOOT_TIMEOUT_S = 120
POLL_INTERVAL_S = 0.2  # 200ms VRAM polling interval
COMPLETION_TIMEOUT_FLAG = "--completion-timeout-s"
DEFAULT_COMPLETION_TIMEOUT_S = 1800
MAX_COMPLETION_TIMEOUT_S = 7200
SERVER_PID_UNLINK_ATTEMPTS = 20
SERVER_PID_UNLINK_RETRY_S = 0.1
REQUIRED_CUSTOM_NODE_WHITELIST = frozenset({"ComfyUI-GGUF", "ComfyUI-KJNodes"})
MANAGER_PROBE_ENV = "LAB_MANAGER_OFFLINE_PROBE"
MANAGER_PROBE_LOG_ENV = "LAB_MANAGER_PROBE_LOG"
MANAGER_PROBE_CLI_FLAG = "--manager-offline-test"
MANAGER_PROBE_PHASE_FLAG = "--manager-probe-phase"
MANAGER_PROBE_CANONICAL_JOB_C_RECIPES = frozenset(
    {
        "h3_i2v_canonical_832x480_f107",
        "h3_i2v_canonical_832x480_f192",
        "h3_i2v_canonical_832x480_f277",
        "h3_r2v_refaudio_canonical_832x480_f107_seed43",
        "h3_r2v_refaudio_canonical_832x480_f192_seed43",
        "h3_r2v_refaudio_canonical_832x480_f277_seed43",
    }
)
MANAGER_PROBE_SHORT_JOB_RECIPES = frozenset(
    {
        "h3_jobd_lipsync_refaudio_seed43_f192",
    }
)
# Closed recipe-to-log-root map. Prefix scopes are intentionally limited to
# the two named music missions; Job C uses exact names so unrelated canonical
# recipes cannot opt Manager into the lab boot lane.
MANAGER_PROBE_SCOPES = (
    (
        "h3-unconditioned-music-mission1",
        frozenset(),
        "h3_unconditioned_music_",
        RESULTS_DIR / "h3_unconditioned_music_campaign" / "server_logs",
    ),
    (
        "h3-canonical-canvas-job-c",
        MANAGER_PROBE_CANONICAL_JOB_C_RECIPES,
        None,
        RESULTS_DIR / "h3_canonical_canvas_campaign" / "server_logs",
    ),
    (
        "h3-music-followup",
        frozenset(),
        "h3_music_followup_",
        RESULTS_DIR / "h3_music_followup_campaign" / "server_logs",
    ),
    (
        "h3-short-jobs",
        MANAGER_PROBE_SHORT_JOB_RECIPES,
        None,
        RESULTS_DIR / "h3_short_jobs" / "server_logs",
    ),
)
MANAGER_PROBE_GUARD_SOURCE = REPO_ROOT / "scratch" / "h3_manager_offline_guard.py"
MANAGER_PROBE_CUSTOM_NODE = "ComfyUI-Manager"
MANAGER_PROBE_BOOT_CMD = REPO_ROOT / "boot_h3_manager_offline_test.cmd"
MANAGER_PROBE_USER_DIRECTORY = Path(r"C:\Users\jeffr\Documents\ComfyUI")
SUITE_CACHE_NONCE_INPUT = "_vram_lab_cache_nonce"
SUITE_CACHE_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
SUITE_CACHE_RUNTIME_SOURCES = {
    "execution.py": "dcac4074826ac9121624ad113f6027684650579da626e24a4011617aae5f3fc0",
    "comfy_execution/caching.py": "26b5b768dff3f2e6fe8279aa6ff645dd87b698d4610744f848a85b1ab543e3a4",
    "comfy_extras/nodes_custom_sampler.py": "3fb59bf45aaf19b2f87099b559c789f94716a90088c6c4ac8a85c53b3c99c59b",
}
STANDALONE_CACHE_RUNTIME_SOURCES = {
    **SUITE_CACHE_RUNTIME_SOURCES,
    "nodes.py": "aa7e2a87bb7c1b43273736eef9fcf4811cb55497c5bde2e201135b244b97431a",
    "comfy_execution/graph.py": "bb602b45f396a3ca666d2e50af4d4cf542819c427b39ee93f2b4c816cc74d3fa",
    "comfy_execution/graph_utils.py": "be44a89007f99e4c90308f1e5f9063fa44497eec08d7cd1bb528fc35d7c727ac",
    "comfy_api/latest/_io.py": "495aefa059aad4eed4181aa7fbb415679d3f269651e9fc6f542bdac1b99dd40f",
}

_MINIMAX_H3_REFERENCE_CLASS = "MiniMaxH3ReferenceToVideo"
_MINIMAX_H3_AUTOGROW_SOCKET_SPECS = {
    "ref_images": ("ref_image_", 9),
    "ref_videos": ("ref_video_", 3),
    "ref_video_audios": ("ref_video_audio_", 3),
    "ref_audios": ("ref_audio_", 3),
}


def enforce_lab_port() -> None:
    """Reject inherited port overrides before any network or process action."""
    inherited = os.environ.get("LAB_PORT")
    if inherited is not None and inherited.strip() != LAB_PORT:
        raise PreflightError(
            3,
            "Lab port",
            f"LAB_PORT must be literal {LAB_PORT}; refusing forbidden override {inherited!r}",
        )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    """Return a SHA-256 digest for bytes already captured for use."""
    return hashlib.sha256(content).hexdigest()


def probe_audio_fixture(path: Path) -> Dict[str, Any]:
    """Run the ear-gate ffprobe and volumedetect measurements on an audio fixture."""
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels,channel_layout,duration:format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    metadata = json.loads(probe.stdout)
    streams = metadata.get("streams", [])
    if not streams:
        raise ValueError("ffprobe found no audio stream")
    stream = streams[0]
    duration = metadata.get("format", {}).get("duration") or stream.get("duration")
    volume = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", "volumedetect", "-f", "null", "NUL",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", volume)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", volume)
    if not mean_match or not max_match or duration is None:
        raise ValueError("ffprobe/volumedetect output was incomplete")
    return {
        "codec_name": stream.get("codec_name"),
        "sample_rate_hz": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "duration_s": round(float(duration), 3),
        "mean_volume_db": float(mean_match.group(1)),
        "max_volume_db": float(max_match.group(1)),
    }


def git_commit(path: Path) -> str:
    """Return the checked-out Git commit, or an empty string outside Git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def git_dirty(path: Path) -> Optional[bool]:
    """Report whether a Git worktree has tracked or untracked changes."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def stable_identity(payload: Dict[str, Any]) -> str:
    """Hash a deterministic run-configuration payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_suite_cache_nonce(argv: List[str], is_suite: bool) -> Optional[str]:
    """Parse the suite-only executor cache nonce without treating it as recipe state."""

    positions = [index for index, value in enumerate(argv) if value == "--suite-cache-nonce"]
    if len(positions) > 1:
        raise ValueError("--suite-cache-nonce may be supplied only once")
    if not positions:
        if is_suite:
            raise ValueError("--suite requires --suite-cache-nonce")
        return None
    if not is_suite:
        raise ValueError("--suite-cache-nonce is allowed only for an authorized --suite child")
    index = positions[0]
    if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
        raise ValueError("--suite-cache-nonce requires a value")
    nonce = argv[index + 1]
    if SUITE_CACHE_NONCE_PATTERN.fullmatch(nonce) is None:
        raise ValueError(
            "--suite-cache-nonce must be 1-160 characters from A-Z, a-z, 0-9, _ . : -"
        )
    return nonce


def parse_standalone_cache_nonce(argv: List[str], is_suite: bool) -> Optional[str]:
    """Parse executor-only cache metadata for an ordinary lab run.

    This is the standalone counterpart to the suite nonce.  It is deliberately
    unavailable to suite children, whose parent supplies the stricter
    ``--suite-cache-nonce`` contract.
    """

    positions = [index for index, value in enumerate(argv) if value == "--executor-cache-nonce"]
    if len(positions) > 1:
        raise ValueError("--executor-cache-nonce may be supplied only once")
    if not positions:
        return None
    if is_suite:
        raise ValueError("--executor-cache-nonce is not allowed for a --suite child")
    index = positions[0]
    if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
        raise ValueError("--executor-cache-nonce requires a value")
    nonce = argv[index + 1]
    if SUITE_CACHE_NONCE_PATTERN.fullmatch(nonce) is None:
        raise ValueError(
            "--executor-cache-nonce must be 1-160 characters from A-Z, a-z, 0-9, _ . : -"
        )
    return nonce


def parse_completion_timeout_s(argv: List[str]) -> int:
    """Parse one bounded completion timeout, preserving the legacy default."""

    positions = [
        index for index, value in enumerate(argv) if value == COMPLETION_TIMEOUT_FLAG
    ]
    if len(positions) > 1:
        raise ValueError(f"{COMPLETION_TIMEOUT_FLAG} may be supplied only once")
    if any(
        isinstance(value, str) and value.startswith(f"{COMPLETION_TIMEOUT_FLAG}=")
        for value in argv
    ):
        raise ValueError(
            f"{COMPLETION_TIMEOUT_FLAG} requires one separate integer value"
        )
    if not positions:
        return DEFAULT_COMPLETION_TIMEOUT_S

    index = positions[0]
    if index + 1 >= len(argv):
        raise ValueError(f"{COMPLETION_TIMEOUT_FLAG} requires an integer value")
    raw_value = argv[index + 1]
    if not isinstance(raw_value, str) or re.fullmatch(r"[1-9][0-9]*", raw_value) is None:
        raise ValueError(
            f"{COMPLETION_TIMEOUT_FLAG} must be an integer from 1 to "
            f"{MAX_COMPLETION_TIMEOUT_S}"
        )
    value = int(raw_value)
    if value > MAX_COMPLETION_TIMEOUT_S:
        raise ValueError(
            f"{COMPLETION_TIMEOUT_FLAG} must be an integer from 1 to "
            f"{MAX_COMPLETION_TIMEOUT_S}"
        )
    return value


def suite_cache_runtime_sha256s() -> Dict[str, str]:
    """Pin the exact Comfy core behavior used by the executor-only cache nonce.

    These files prove three properties: raw prompt inputs participate in cache
    signatures, undeclared inputs are filtered before node execution, and
    RandomNoise declares/executes only ``noise_seed``.  Any core drift requires
    a fresh audit rather than silently changing suite semantics.
    """

    actual: Dict[str, str] = {}
    for relative_name, expected_hash in SUITE_CACHE_RUNTIME_SOURCES.items():
        source = COMFYUI_ROOT / Path(relative_name)
        if not source.is_file():
            raise ValueError(f"Suite cache runtime source is missing: {relative_name}")
        digest = sha256_file(source)
        if digest != expected_hash:
            raise ValueError(
                f"Suite cache runtime source changed: {relative_name} "
                f"(expected {expected_hash}, found {digest})"
            )
        actual[relative_name] = digest
    return actual


def standalone_cache_runtime_sha256s() -> Dict[str, str]:
    """Pin cache/filter behavior plus the legacy core KSampler implementation."""

    actual: Dict[str, str] = {}
    for relative_name, expected_hash in STANDALONE_CACHE_RUNTIME_SOURCES.items():
        source = COMFYUI_ROOT / Path(relative_name)
        if not source.is_file():
            raise ValueError(f"Standalone cache runtime source is missing: {relative_name}")
        digest = sha256_file(source)
        if digest != expected_hash:
            raise ValueError(
                f"Standalone cache runtime source changed: {relative_name} "
                f"(expected {expected_hash}, found {digest})"
            )
        actual[relative_name] = digest
    return actual


def prompt_descendants(prompt: Dict[str, Any], source_id: str) -> List[str]:
    """Return the source node and every node whose inputs transitively consume it."""

    descendants = {str(source_id)}
    changed = True
    while changed:
        changed = False
        for node_id, node in prompt.items():
            normalized_id = str(node_id)
            if normalized_id in descendants or not isinstance(node, dict):
                continue
            for value in node.get("inputs", {}).values():
                if any(link_source in descendants for _, link_source, _ in iter_prompt_links(value)):
                    descendants.add(normalized_id)
                    changed = True
                    break
    return sorted(descendants, key=lambda value: (len(value), value))


def prompt_output_ancestors(prompt: Dict[str, Any]) -> List[str]:
    """Return only nodes that feed a declared file-output sink."""

    reachable = {
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") in {"SaveImage", "SaveVideo"}
    }
    stack = list(reachable)
    while stack:
        node_id = stack.pop()
        node = prompt.get(node_id, {})
        for value in node.get("inputs", {}).values():
            for _, source_id, _ in iter_prompt_links(value):
                if source_id in prompt and source_id not in reachable:
                    reachable.add(source_id)
                    stack.append(source_id)
    return sorted(reachable, key=lambda value: (len(value), value))


def apply_suite_cache_nonce(
    prompt: Dict[str, Any], nonce: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Inject queue-only cache metadata into RandomNoise without changing semantics.

    The immutable recipe is validated before this function runs.  On the pinned
    Comfy core, cache signatures include this raw key while ``get_input_data``
    filters it because RandomNoise does not declare it.  The node therefore sees
    the exact original ``noise_seed`` and the official graph topology is intact.
    """

    if SUITE_CACHE_NONCE_PATTERN.fullmatch(nonce) is None:
        raise ValueError("Invalid suite cache nonce")
    if not isinstance(prompt, dict):
        raise ValueError("Suite prompt must be a dictionary")
    noise_nodes = [
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") == "RandomNoise"
    ]
    if len(noise_nodes) != 1:
        raise ValueError(
            f"Suite cache control requires exactly one RandomNoise node, found {noise_nodes}"
        )
    noise_id = noise_nodes[0]
    original_inputs = prompt[noise_id].get("inputs")
    if not isinstance(original_inputs, dict):
        raise ValueError("RandomNoise inputs must be a dictionary")
    if set(original_inputs) != {"noise_seed"}:
        raise ValueError(
            "RandomNoise must expose only its declared noise_seed before cache metadata injection"
        )
    recipe_seed = original_inputs.get("noise_seed")
    if isinstance(recipe_seed, bool) or not isinstance(recipe_seed, int):
        raise ValueError("RandomNoise noise_seed must be an integer")

    queued_prompt = copy.deepcopy(prompt)
    queued_prompt[noise_id]["inputs"][SUITE_CACHE_NONCE_INPUT] = nonce
    fresh_node_ids = prompt_descendants(queued_prompt, noise_id)
    reachable_node_ids = prompt_output_ancestors(queued_prompt)
    stable_node_ids = sorted(
        (node_id for node_id in reachable_node_ids if node_id not in fresh_node_ids),
        key=lambda value: (len(value), value),
    )
    sampler_ids = sorted(
        node_id
        for node_id in fresh_node_ids
        if queued_prompt[node_id].get("class_type") == "SamplerCustomAdvanced"
    )
    if not sampler_ids:
        raise ValueError("RandomNoise does not reach a SamplerCustomAdvanced node")
    return queued_prompt, {
        "mode": "pinned-undeclared-randomnoise-input",
        "nonce": nonce,
        "noise_node_id": noise_id,
        "recipe_noise_seed": recipe_seed,
        "fresh_node_ids": fresh_node_ids,
        "stable_node_ids": stable_node_ids,
        "reachable_node_ids": reachable_node_ids,
        "sampler_node_ids": sampler_ids,
    }


def apply_standalone_cache_nonce(
    prompt: Dict[str, Any], nonce: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Force a fresh sampler/output branch while preserving declared inputs.

    The pinned Comfy executor hashes every raw API input but forwards only
    declared inputs to V3 ``RandomNoise`` and the legacy ``KSampler`` /
    ``SamplerCustom`` nodes.
    Injecting this queue-only key therefore invalidates the sampler branch
    without changing the seed, graph bytes, or node call arguments.
    """

    if SUITE_CACHE_NONCE_PATTERN.fullmatch(nonce) is None:
        raise ValueError("Invalid standalone cache nonce")
    if not isinstance(prompt, dict):
        raise ValueError("Standalone prompt must be a dictionary")
    candidates = [
        (str(node_id), node.get("class_type"))
        for node_id, node in prompt.items()
        if isinstance(node, dict)
        and node.get("class_type") in {"RandomNoise", "KSampler", "SamplerCustom"}
    ]
    if len(candidates) != 1:
        raise ValueError(
            "Standalone cache control requires exactly one RandomNoise, KSampler, "
            "or SamplerCustom "
            f"source node, found {candidates}"
        )
    source_id, source_class = candidates[0]
    original_inputs = prompt[source_id].get("inputs")
    if not isinstance(original_inputs, dict):
        raise ValueError(f"{source_class} inputs must be a dictionary")
    if SUITE_CACHE_NONCE_INPUT in original_inputs:
        raise ValueError("Immutable recipe already contains executor cache metadata")

    seed_key = "seed" if source_class == "KSampler" else "noise_seed"
    if source_class == "RandomNoise" and set(original_inputs) != {seed_key}:
        raise ValueError("RandomNoise must expose only its declared noise_seed")
    recipe_seed = original_inputs.get(seed_key)
    if isinstance(recipe_seed, bool) or not isinstance(recipe_seed, int):
        raise ValueError(f"{source_class} {seed_key} must be an integer")

    queued_prompt = copy.deepcopy(prompt)
    queued_prompt[source_id]["inputs"][SUITE_CACHE_NONCE_INPUT] = nonce
    fresh_node_ids = prompt_descendants(queued_prompt, source_id)
    reachable_node_ids = prompt_output_ancestors(queued_prompt)
    stable_node_ids = sorted(
        (node_id for node_id in reachable_node_ids if node_id not in fresh_node_ids),
        key=lambda value: (len(value), value),
    )
    if source_class == "RandomNoise":
        sampler_ids = sorted(
            node_id
            for node_id in fresh_node_ids
            if queued_prompt[node_id].get("class_type") == "SamplerCustomAdvanced"
        )
    else:
        sampler_ids = [source_id]
    if not sampler_ids:
        raise ValueError(f"{source_class} does not reach a supported sampler node")
    reachable = set(reachable_node_ids)
    if source_id not in reachable or not set(sampler_ids).issubset(reachable):
        raise ValueError(
            f"{source_class} cache-control source and sampler must feed a file-output sink"
        )
    fresh_output_ids = [
        node_id
        for node_id in fresh_node_ids
        if queued_prompt[node_id].get("class_type") in {"SaveImage", "SaveVideo"}
    ]
    if not fresh_output_ids:
        raise ValueError(f"{source_class} does not reach a SaveImage or SaveVideo sink")
    return queued_prompt, {
        "mode": "pinned-undeclared-sampler-input",
        "nonce": nonce,
        "source_node_id": source_id,
        "source_class_type": source_class,
        "seed_input": seed_key,
        "recipe_seed": recipe_seed,
        "fresh_node_ids": fresh_node_ids,
        "stable_node_ids": stable_node_ids,
        "reachable_node_ids": reachable_node_ids,
        "sampler_node_ids": sampler_ids,
        "fresh_output_node_ids": fresh_output_ids,
    }


def execution_cache_evidence(
    messages: Any, cache_control: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Prove the nonce-controlled sampling/output branch was not served from cache."""

    if cache_control is None:
        return {}
    cached_nodes: set[str] = set()
    cache_event_found = False
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, (list, tuple)) or len(message) < 2:
                continue
            if message[0] != "execution_cached" or not isinstance(message[1], dict):
                continue
            nodes = message[1].get("nodes")
            if isinstance(nodes, list):
                cache_event_found = True
                cached_nodes.update(str(node_id) for node_id in nodes)
    expected_fresh = {str(node_id) for node_id in cache_control.get("fresh_node_ids", [])}
    cached_fresh = sorted(expected_fresh & cached_nodes, key=lambda value: (len(value), value))
    evidence = dict(cache_control)
    evidence.update(
        {
            "cache_event_found": cache_event_found,
            "cached_node_ids": sorted(cached_nodes, key=lambda value: (len(value), value)),
            "cached_fresh_node_ids": cached_fresh,
            "fresh_execution_proved": cache_event_found and not cached_fresh,
        }
    )
    return evidence


def extract_output_path(outputs: Dict[str, Any]) -> str:
    """Return the first file artifact emitted by a ComfyUI history payload."""
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ["images", "gifs", "videos", "audio", "animated"]:
            items = node_output.get(key)
            if not isinstance(items, list) or not items:
                continue
            item = items[0]
            if isinstance(item, dict):
                filename = item.get("filename", "")
            elif isinstance(item, str):
                filename = item
            else:
                filename = ""
            if filename:
                return filename
    return ""


def next_run_state(
    previous: Dict[str, Any],
    run_identity_sha256: str,
    previous_run_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Keep execution numbering monotonic while resetting certification on identity changes."""
    previous_counter = (
        previous_run_number
        if previous_run_number is not None
        else previous.get("run_count", previous.get("run_number", 0))
    )
    previous_run_count = (
        previous_counter
        if isinstance(previous_counter, int)
        and not isinstance(previous_counter, bool)
        and previous_counter >= 0
        else 0
    )
    same_identity = bool(run_identity_sha256) and previous.get("run_identity_sha256") == run_identity_sha256
    raw_config_count = previous.get("config_run_count", 0)
    previous_config_count = (
        raw_config_count
        if same_identity
        and isinstance(raw_config_count, int)
        and not isinstance(raw_config_count, bool)
        and raw_config_count >= 1
        else 0
    )
    previous_gate_pass = bool(
        same_identity
        and previous.get("gate_pass") is True
        and _receipt_status_is_consistent(previous)
    )
    return {
        "run_count": previous_run_count + 1,
        "config_run_count": previous_config_count + 1,
        "same_identity": same_identity,
        "previous_gate_pass": previous_gate_pass,
    }


class ReceiptHistoryError(RuntimeError):
    """Raised when a run-receipt history cannot be extended safely."""


_COLD_GATE_PASS_STATUSES = frozenset({"PASS (cold)", "PASS (cold, marginal)"})
_WARM_GATE_PASS_STATUSES = frozenset({"PASS", "PASS (marginal)"})
_ALL_GATE_PASS_STATUSES = _COLD_GATE_PASS_STATUSES | _WARM_GATE_PASS_STATUSES


def _receipt_status_is_consistent(payload: Dict[str, Any]) -> bool:
    """Require emitted machine booleans and PASS status to describe one state."""
    gate_pass = payload.get("gate_pass")
    warm_pass = payload.get("warm_pass")
    pass_value = payload.get("pass")
    status_value = payload.get("status")
    if not all(isinstance(value, bool) for value in (gate_pass, warm_pass, pass_value)):
        return False
    if pass_value is not warm_pass:
        return False
    if warm_pass:
        return gate_pass and status_value in _WARM_GATE_PASS_STATUSES
    if gate_pass:
        return status_value in _COLD_GATE_PASS_STATUSES
    return status_value not in _ALL_GATE_PASS_STATUSES


def _is_symlink_or_reparse_point(path: Path) -> bool:
    """Return true for a symlink or Windows reparse-point path."""
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _strict_results_root(results_dir: Path) -> Path:
    """Resolve a real results directory without following a reparse root."""
    lexical = Path(os.path.abspath(os.fspath(results_dir)))
    if not os.path.lexists(lexical):
        raise ReceiptHistoryError(f"Results directory is missing: {lexical}")
    try:
        if _is_symlink_or_reparse_point(lexical):
            raise ReceiptHistoryError(
                f"Results directory is a symlink or reparse point: {lexical}"
            )
        resolved = lexical.resolve(strict=True)
    except ReceiptHistoryError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ReceiptHistoryError(f"Cannot prove results directory identity: {exc}") from exc
    if resolved != lexical or not resolved.is_dir():
        raise ReceiptHistoryError(
            f"Results directory does not resolve to its exact derived path: {lexical}"
        )
    return resolved


def _strict_history_file(path: Path, results_root: Path, label: str) -> Path:
    """Require one direct, regular, non-reparse child of the results root."""
    lexical = results_root / path.name
    if path != lexical or not os.path.lexists(lexical):
        raise ReceiptHistoryError(f"{label} path is not the exact derived results path")
    try:
        if _is_symlink_or_reparse_point(lexical):
            raise ReceiptHistoryError(f"{label} is a symlink or reparse point: {lexical.name}")
        resolved = lexical.resolve(strict=True)
    except ReceiptHistoryError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ReceiptHistoryError(f"Cannot prove {label} path identity: {exc}") from exc
    if resolved != lexical or resolved.parent != results_root or not resolved.is_file():
        raise ReceiptHistoryError(f"{label} is not an exact regular results file")
    return resolved


def strict_output_artifact_path(
    output_name: Any, outputs_dir: Optional[Path] = None
) -> Path:
    """Resolve one nonempty regular artifact without leaving the real outputs root."""
    if not isinstance(output_name, str) or not output_name.strip():
        raise ValueError("output artifact path must be nonempty text")
    candidate = Path(output_name.replace("\\", "/"))
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        raise ValueError("output artifact path must be relative and contained in outputs/")

    outputs_lexical = Path(
        os.path.abspath(os.fspath(outputs_dir or (REPO_ROOT / "outputs")))
    )
    try:
        if not os.path.lexists(outputs_lexical):
            raise ValueError("outputs directory is missing")
        if _is_symlink_or_reparse_point(outputs_lexical):
            raise ValueError("outputs directory is a symlink or reparse point")
        outputs_root = outputs_lexical.resolve(strict=True)
        if outputs_root != outputs_lexical or not outputs_root.is_dir():
            raise ValueError("outputs directory does not resolve to its exact path")

        lexical = outputs_root / candidate
        component = outputs_root
        for part in candidate.parts:
            component = component / part
            if os.path.lexists(component) and _is_symlink_or_reparse_point(component):
                raise ValueError("output artifact path contains a symlink or reparse point")
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(outputs_root)
    except ValueError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"output artifact path cannot be proved: {exc}") from exc
    if resolved != lexical or not resolved.is_file():
        raise ValueError("output artifact is not an exact regular file under outputs/")
    try:
        if resolved.stat().st_size <= 0:
            raise ValueError("output artifact is empty")
    except OSError as exc:
        raise ValueError(f"output artifact size cannot be proved: {exc}") from exc
    return resolved


def _receipt_run_number(payload: Dict[str, Any], path: Path) -> int:
    """Return a strictly typed positive receipt counter."""
    value = payload.get("run_number", payload.get("run_count"))
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReceiptHistoryError(
            f"Receipt {path.name} has an invalid positive integer run number: {value!r}"
        )
    run_count = payload.get("run_count")
    if run_count is not None and (
        isinstance(run_count, bool)
        or not isinstance(run_count, int)
        or run_count < 1
        or run_count != value
    ):
        raise ReceiptHistoryError(
            f"Receipt {path.name} has an invalid or inconsistent run_count: {run_count!r}"
        )
    return value


def _validate_modern_history_payload(payload: Dict[str, Any], path: Path) -> None:
    """Reject type-confused modern evidence before it can become machine_previous."""
    modern = any(
        marker in payload
        for marker in (
            "receipt_schema_version",
            "run_identity_sha256",
            "identity",
            "runner_sha256",
            "provenance_unchanged",
        )
    )
    if not modern:
        return
    if "receipt_schema_version" in payload:
        schema = payload.get("receipt_schema_version")
        if (
            isinstance(schema, bool)
            or not isinstance(schema, int)
            or schema not in {1, 2, RECEIPT_SCHEMA_VERSION}
        ):
            raise ReceiptHistoryError(
                f"Modern receipt {path.name} has invalid receipt_schema_version: {schema!r}"
            )
    for field in ("pass", "gate_pass", "warm_pass"):
        if not isinstance(payload.get(field), bool):
            raise ReceiptHistoryError(
                f"Modern receipt {path.name} field {field} must be an actual boolean"
            )
    config_count = payload.get("config_run_count")
    if (
        isinstance(config_count, bool)
        or not isinstance(config_count, int)
        or config_count < 1
    ):
        raise ReceiptHistoryError(
            f"Modern receipt {path.name} config_run_count must be a positive integer"
        )
    if not isinstance(payload.get("status"), str) or not payload["status"]:
        raise ReceiptHistoryError(f"Modern receipt {path.name} status must be nonempty text")
    if not _receipt_status_is_consistent(payload):
        raise ReceiptHistoryError(
            f"Modern receipt {path.name} has inconsistent pass/gate/warm/status fields"
        )


def _decode_receipt(path: Path) -> Tuple[Dict[str, Any], bytes]:
    """Read a receipt as strict UTF-8 JSON and retain its exact bytes."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ReceiptHistoryError(f"Receipt has a UTF-8 BOM: {path.name}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptHistoryError(f"Malformed receipt {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReceiptHistoryError(f"Receipt must contain a JSON object: {path.name}")
    return payload, raw


def audit_run_history(results_dir: Path, recipe_name: str) -> Dict[str, Any]:
    """Audit the mutable alias and immutable run archives before allocation.

    The next execution number is derived from every known receipt.  A rolled
    back alias, malformed file, mismatched recipe label, or archive whose
    payload disagrees with its filename fails closed instead of risking an
    overwrite of historical evidence.  Legacy aliases may contain additive
    review annotations; their byte-parity state is surfaced so a suite can
    require exact parity for each newly written child.
    """
    results_root = _strict_results_root(results_dir)
    archive_pattern = re.compile(rf"^{re.escape(recipe_name)}_run([1-9][0-9]*)\.json$")
    archive_paths = sorted(
        path
        for path in results_root.iterdir()
        if path.name.startswith(f"{recipe_name}_run")
    )
    alias_path = results_root / f"{recipe_name}.json"
    alias_exists = os.path.lexists(alias_path)
    if alias_exists:
        alias_path = _strict_history_file(alias_path, results_root, "Current receipt")
    for path in archive_paths:
        _strict_history_file(path, results_root, "Run archive")
        if alias_exists:
            try:
                if os.path.samefile(path, alias_path):
                    raise ReceiptHistoryError(
                        f"Run archive {path.name} is the same file as the mutable current alias"
                    )
            except ReceiptHistoryError:
                raise
            except OSError as exc:
                raise ReceiptHistoryError(
                    f"Cannot distinguish run archive {path.name} from the mutable current alias: {exc}"
                ) from exc

    archives: Dict[int, Dict[str, Any]] = {}
    archive_bytes: Dict[int, bytes] = {}
    for path in archive_paths:
        match = archive_pattern.match(path.name)
        if not match:
            raise ReceiptHistoryError(f"Unexpected run-receipt filename: {path.name}")
        number = int(match.group(1))
        if number in archives:
            raise ReceiptHistoryError(f"Duplicate run number {number} for {recipe_name}")
        payload, raw = _decode_receipt(path)
        payload_number = _receipt_run_number(payload, path)
        if payload_number != number:
            raise ReceiptHistoryError(
                f"Archive {path.name} contains run number {payload_number}, expected {number}"
            )
        payload_recipe = payload.get("recipe")
        if payload_recipe and payload_recipe != recipe_name:
            raise ReceiptHistoryError(
                f"Archive {path.name} labels recipe {payload_recipe!r}, expected {recipe_name!r}"
            )
        _validate_modern_history_payload(payload, path)
        archives[number] = payload
        archive_bytes[number] = raw

    current: Dict[str, Any] = {}
    current_bytes = b""
    current_number = 0
    if alias_exists:
        current, current_bytes = _decode_receipt(alias_path)
        payload_recipe = current.get("recipe")
        if payload_recipe and payload_recipe != recipe_name:
            raise ReceiptHistoryError(
                f"Current receipt labels recipe {payload_recipe!r}, expected {recipe_name!r}"
            )
        current_number = _receipt_run_number(current, alias_path)
        _validate_modern_history_payload(current, alias_path)

    max_archive = max(archives, default=0)
    if current_number < max_archive:
        raise ReceiptHistoryError(
            f"Current receipt is rolled back to run {current_number}; archive run {max_archive} exists"
        )
    if current_number > max_archive and (
        current.get("receipt_schema_version") in {1, 2, 3}
        or current.get("run_identity_sha256")
    ):
        raise ReceiptHistoryError(
            f"Current modern receipt run {current_number} has no matching immutable archive"
        )
    alias_archive_match = (
        current_number not in archive_bytes
        or current_bytes == archive_bytes[current_number]
    )

    max_run_number = max(current_number, max_archive)
    if max_archive and max_archive >= current_number:
        machine_previous = archives[max_archive]
        machine_previous_source = f"archive_run{max_archive}"
    else:
        machine_previous = current
        machine_previous_source = "current_alias"
    next_archive = results_root / f"{recipe_name}_run{max_run_number + 1}.json"
    if next_archive.exists():
        raise ReceiptHistoryError(f"Target run archive already exists: {next_archive.name}")
    return {
        "current": current,
        "current_bytes": current_bytes,
        "current_number": current_number,
        "alias_archive_match": alias_archive_match,
        "archives": archives,
        "archive_bytes": archive_bytes,
        "max_run_number": max_run_number,
        "machine_previous": machine_previous,
        "machine_previous_source": machine_previous_source,
        "next_run_number": max_run_number + 1,
        "alias_path": alias_path,
        "next_archive_path": next_archive,
    }


def write_run_receipts_atomic(
    payload: Dict[str, Any], archive_path: Path, alias_path: Path
) -> bytes:
    """Create an immutable archive exclusively, then atomically replace alias."""
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())

    temp_path = alias_path.with_name(f".{alias_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, alias_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return encoded


def referenced_fixtures(recipe_data: Dict[str, Any]) -> List[str]:
    """Return literal local fixture names referenced by LoadImage/LoadAudio nodes."""
    prompt = recipe_data.get("prompt", recipe_data)
    found = set()
    fixture_inputs = {"LoadImage": "image", "LoadAudio": "audio"}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        input_name = fixture_inputs.get(node.get("class_type"))
        if not input_name:
            continue
        value = node.get("inputs", {}).get(input_name)
        if isinstance(value, str) and value:
            normalized = value.replace("\\", "/")
            candidate = Path(normalized)
            if candidate.is_absolute() or len(candidate.parts) != 1 or normalized in {".", ".."}:
                raise ValueError(f"Fixture reference must be a basename inside fixtures/: {value}")
            found.add(normalized)
    return sorted(found)


def referenced_audio_fixtures(recipe_data: Dict[str, Any]) -> List[str]:
    """Return literal fixture basenames referenced by LoadAudio nodes."""
    prompt = recipe_data.get("prompt", recipe_data)
    found = set()
    for node in prompt.values():
        if not isinstance(node, dict) or node.get("class_type") != "LoadAudio":
            continue
        value = node.get("inputs", {}).get("audio")
        if not isinstance(value, str) or not value:
            continue
        normalized = value.replace("\\", "/")
        candidate = Path(normalized)
        if candidate.is_absolute() or len(candidate.parts) != 1 or normalized in {".", ".."}:
            raise ValueError(f"Audio fixture reference must be a basename inside fixtures/: {value}")
        found.add(normalized)
    return sorted(found)


def validate_fixture_hash_contract(
    recipe_data: Dict[str, Any], fixture_payloads: Dict[str, bytes]
) -> None:
    """Enforce optional hash pins for referenced fixture basenames before upload.

    ``fixture_hashes`` may intentionally pin only a subset of the recipe's loader
    fixtures (for example, shared visual controls while audio remains receipt-bound).
    Every declared pin must nevertheless be a safe, actually referenced basename and
    must match the exact queued bytes. Unpinned referenced fixtures remain part of the
    normal provenance hash map returned by ``check_fixtures_uploaded``.
    """
    topology = recipe_data.get("topology_contract", {})
    if not isinstance(topology, dict):
        return
    expected_hashes = topology.get("fixture_hashes")
    if expected_hashes is None:
        return
    if not isinstance(expected_hashes, dict):
        raise ValueError("topology_contract.fixture_hashes must be a dictionary")

    normalized_hashes: Dict[str, str] = {}
    for fixture_name, expected_hash in expected_hashes.items():
        if not isinstance(fixture_name, str) or not fixture_name:
            raise ValueError(
                "topology_contract.fixture_hashes keys must be non-empty fixture basenames"
            )
        normalized = fixture_name.replace("\\", "/")
        candidate = Path(normalized)
        if (
            candidate.is_absolute()
            or candidate.drive
            or len(candidate.parts) != 1
            or normalized in {".", ".."}
        ):
            raise ValueError(
                "topology_contract.fixture_hashes key must be a basename inside fixtures/: "
                f"{fixture_name}"
            )
        if not isinstance(expected_hash, str) or re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_hash
        ) is None:
            raise ValueError(
                "topology_contract.fixture_hashes value must be a 64-character SHA-256 "
                f"for {fixture_name}"
            )
        normalized_hashes[normalized] = expected_hash.lower()

    referenced_names = set(referenced_fixtures(recipe_data))
    pinned_names = set(normalized_hashes)
    unreferenced_pins = sorted(pinned_names - referenced_names)
    if unreferenced_pins:
        raise ValueError(
            "topology_contract.fixture_hashes contains unreferenced/extra fixture pins: "
            f"{unreferenced_pins}"
        )

    missing_payloads = sorted(pinned_names - set(fixture_payloads))
    if missing_payloads:
        raise ValueError(
            f"Pinned fixture payloads are missing before upload: {missing_payloads}"
        )

    mismatches = sorted(
        fixture_name
        for fixture_name, expected_hash in normalized_hashes.items()
        if sha256_bytes(fixture_payloads[fixture_name]) != expected_hash
    )
    if mismatches:
        raise ValueError(
            f"Pinned fixture SHA-256 mismatch before upload: {mismatches}"
        )


def validate_audio_fixture_receipt(fixture_name: str, fixture_bytes: Optional[bytes] = None) -> str:
    """Enforce the probe + human-description ear gate and return its receipt hash."""
    receipt_path = AUDIO_RECEIPTS_DIR / f"{Path(fixture_name).stem}.json"
    if not receipt_path.is_file():
        raise ValueError(f"Audio ear-gate receipt missing: {receipt_path.relative_to(REPO_ROOT)}")
    raw_receipt = receipt_path.read_bytes()
    if raw_receipt.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"Audio ear-gate receipt has a UTF-8 BOM: {receipt_path.name}")
    try:
        receipt = json.loads(raw_receipt.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Audio ear-gate receipt is invalid JSON: {receipt_path.name}: {exc}") from exc

    if fixture_bytes is None:
        fixture_path = FIXTURES_DIR / fixture_name
        if not fixture_path.is_file():
            raise ValueError(f"Audio fixture missing: {fixture_name}")
        fixture_bytes = fixture_path.read_bytes()
    human_review = receipt.get("human_review", {})
    ffprobe_receipt = receipt.get("ffprobe", {})
    volume_receipt = receipt.get("volumedetect", {})
    matrix_window = receipt.get("matrix_window", {})
    commands = receipt.get("commands", {})
    failures = []
    if receipt.get("schema_version") != 1:
        failures.append("schema_version must be 1")
    if receipt.get("fixture") != fixture_name:
        failures.append("fixture label mismatch")
    if receipt.get("sha256") != sha256_bytes(fixture_bytes):
        failures.append("fixture SHA-256 mismatch")
    if receipt.get("ear_gate_pass") is not True:
        failures.append("ear_gate_pass is not true")
    if not all(human_review.get(key) for key in ("reviewer", "reviewed_at", "content_class", "description")):
        failures.append("human description/reviewer fields are incomplete")
    if not all(key in ffprobe_receipt for key in ("codec_name", "sample_rate_hz", "channels", "duration_s")):
        failures.append("ffprobe fields are incomplete")
    if not all(key in volume_receipt for key in ("mean_volume_db", "max_volume_db")):
        failures.append("volumedetect fields are incomplete")
    if not all(key in commands for key in ("ffprobe", "volumedetect", "matrix_loudness")):
        failures.append("reproduction commands are incomplete")
    numeric_matrix_fields = ("duration_s", "target_lufs", "tolerance_lu", "gain_db", "matched_lufs")
    if not matrix_window.get("method") or not all(
        isinstance(matrix_window.get(key), (int, float)) and math.isfinite(float(matrix_window[key]))
        for key in numeric_matrix_fields
    ):
        failures.append("matrix loudness method/values are incomplete")
    elif abs(float(matrix_window["matched_lufs"]) - float(matrix_window["target_lufs"])) > float(matrix_window["tolerance_lu"]) + 1e-6:
        failures.append("matrix loudness falls outside its declared tolerance")

    try:
        measured = probe_audio_fixture(FIXTURES_DIR / fixture_name)
        exact_fields = ("codec_name", "sample_rate_hz", "channels")
        for key in exact_fields:
            if measured[key] != ffprobe_receipt.get(key):
                failures.append(f"live ffprobe mismatch: {key}")
        if abs(measured["duration_s"] - float(ffprobe_receipt.get("duration_s", -1))) > 0.01:
            failures.append("live ffprobe mismatch: duration_s")
        if abs(measured["mean_volume_db"] - float(volume_receipt.get("mean_volume_db", 999))) > 0.11:
            failures.append("live volumedetect mismatch: mean_volume_db")
        if abs(measured["max_volume_db"] - float(volume_receipt.get("max_volume_db", 999))) > 0.11:
            failures.append("live volumedetect mismatch: max_volume_db")
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"live ffprobe/volumedetect failed: {exc}")
    if failures:
        raise ValueError(f"Audio ear-gate receipt failed for {fixture_name}: {', '.join(failures)}")
    return sha256_bytes(raw_receipt)


def audio_receipt_sha256s(recipe_data: Dict[str, Any]) -> Dict[str, str]:
    """Validate and hash every audio ear-gate receipt used by a recipe."""
    return {
        fixture_name: validate_audio_fixture_receipt(fixture_name)
        for fixture_name in referenced_audio_fixtures(recipe_data)
    }


def capture_provenance_snapshot(recipe_path: Path, recipe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Capture final provenance without losing a completed run receipt on drift/errors."""
    try:
        return {
            "valid": True,
            "error": "",
            "recipe_sha256": sha256_file(recipe_path),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "lab_locks_sha256": sha256_file(LAB_LOCKS_SOURCE_PATH),
            "fixture_sha256s": fixture_sha256s(recipe_data),
            "audio_receipt_sha256s": audio_receipt_sha256s(recipe_data),
            "model_fingerprints": model_fingerprints(recipe_data),
        }
    except Exception as exc:
        return {
            "valid": False,
            "error": f"{type(exc).__name__}: {exc}",
            "recipe_sha256": "",
            "runner_sha256": "",
            "lab_locks_sha256": "",
            "fixture_sha256s": {},
            "audio_receipt_sha256s": {},
            "model_fingerprints": {},
        }


def fixture_sha256s(recipe_data: Dict[str, Any]) -> Dict[str, str]:
    """Hash every literal fixture so run identity changes with its inputs."""
    hashes: Dict[str, str] = {}
    for fixture_name in referenced_fixtures(recipe_data):
        fixture_path = FIXTURES_DIR / fixture_name
        if fixture_path.is_file():
            hashes[fixture_name] = sha256_file(fixture_path)
    return hashes


def referenced_model_names(recipe_data: Dict[str, Any]) -> List[str]:
    """Collect literal weight filenames from known ComfyUI loader inputs."""
    model_input_names = {
        "ckpt_name",
        "unet_name",
        "vae_name",
        "clip_name",
        "text_encoder",
        "audio_encoder_name",
        "lora_name",
        "model_name",
    }
    prompt = recipe_data.get("prompt", recipe_data)
    names = set()
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        for key, value in node.get("inputs", {}).items():
            if key in model_input_names and isinstance(value, str) and value:
                names.add(value.replace("\\", "/"))
    return sorted(names)


def model_fingerprints(recipe_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Fingerprint referenced local weights without hashing multi-gigabyte files."""
    fingerprints: Dict[str, Dict[str, Any]] = {}
    for model_name in referenced_model_names(recipe_data):
        relative = Path(model_name)
        resolved = next(
            (root / relative for root in MODEL_ROOTS if (root / relative).is_file()),
            None,
        )
        if resolved is None:
            fingerprints[model_name] = {"resolved": False}
            continue
        stat = resolved.stat()
        fingerprints[model_name] = {
            "resolved": True,
            "path": str(resolved),
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return fingerprints


def probe_media_metrics(path: Path) -> Dict[str, Any]:
    """Collect non-gating encoded-stream diagnostics from an output artifact."""
    metrics: Dict[str, Any] = {"artifact_bytes": path.stat().st_size}
    try:
        stream_proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-count_frames", "-show_streams",
                "-show_format", "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        packet_proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_packets",
                "-show_entries", "packet=stream_index,size", "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(stream_proc.stdout)
        packets = json.loads(packet_proc.stdout).get("packets", [])
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if not video:
            metrics["media_probe_error"] = "no video stream"
            return metrics

        video_index = int(video.get("index", 0))
        audio_index = int(audio.get("index", -1)) if audio else -1
        video_bytes = sum(int(p.get("size", 0) or 0) for p in packets if int(p.get("stream_index", -1)) == video_index)
        audio_bytes = sum(int(p.get("size", 0) or 0) for p in packets if int(p.get("stream_index", -1)) == audio_index)
        frame_value = video.get("nb_read_frames") or video.get("nb_frames") or 0
        frame_count = int(frame_value) if str(frame_value).isdigit() else 0

        fps_text = video.get("avg_frame_rate", "0/0")
        numerator, denominator = (fps_text.split("/", 1) + ["1"])[:2]
        fps = float(numerator) / float(denominator) if float(denominator) else 0.0
        format_duration = info.get("format", {}).get("duration")
        video_duration = video.get("duration")
        audio_duration = audio.get("duration") if audio else None
        metrics.update({
            "encoded_frame_count": frame_count,
            "artifact_bytes_per_frame": round(metrics["artifact_bytes"] / frame_count, 2) if frame_count else None,
            "video_stream_bytes": video_bytes,
            "video_stream_bytes_per_frame": round(video_bytes / frame_count, 2) if frame_count else None,
            "audio_stream_bytes": audio_bytes,
            "video_codec": video.get("codec_name", ""),
            "pixel_format": video.get("pix_fmt", ""),
            "encoded_width": video.get("width"),
            "encoded_height": video.get("height"),
            "encoded_fps": round(fps, 6),
            "audio_present": audio is not None,
            "audio_codec": audio.get("codec_name", "") if audio else "",
            "audio_bitrate": int(audio.get("bit_rate", 0) or 0) if audio else 0,
            "container_duration_s": round(float(format_duration), 6) if format_duration is not None else None,
            "video_duration_s": round(float(video_duration), 6) if video_duration is not None else None,
            "audio_duration_s": round(float(audio_duration), 6) if audio_duration is not None else None,
        })
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        metrics["media_probe_error"] = str(exc)
    return metrics


def media_fingerprint(metrics: Dict[str, Any]) -> Tuple[Any, ...]:
    """Fields that must match before encoded-size comparisons are meaningful."""
    return (
        metrics.get("video_codec"),
        metrics.get("pixel_format"),
        metrics.get("encoded_width"),
        metrics.get("encoded_height"),
        metrics.get("encoded_fps"),
        metrics.get("encoded_frame_count"),
    )


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_finite_real(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def media_contract_is_valid(contract: Any) -> bool:
    """Require a complete, finite, positive video measurement contract."""
    if not isinstance(contract, dict):
        return False
    if not all(_positive_integer(contract.get(field)) for field in ("frames", "width", "height")):
        return False
    if not _positive_finite_real(contract.get("fps")):
        return False
    duration_fields = [field for field in ("target_s", "duration_s") if field in contract]
    if not duration_fields or not all(
        _positive_finite_real(contract.get(field)) for field in duration_fields
    ):
        return False
    return True


def bitrate_anomaly_fields(recipe_name: str, metrics: Dict[str, Any], boot_lane: str) -> Dict[str, Any]:
    """Compare against >=3 distinct, explicitly human-approved clean artifacts."""
    current_bpf = metrics.get("video_stream_bytes_per_frame")
    if not current_bpf:
        return {"bitrate_anomaly": False, "bitrate_baseline_status": "unavailable"}

    fingerprint = media_fingerprint(metrics)
    approved_values = []
    artifact_hashes = set()
    for receipt_path in RESULTS_DIR.glob(f"{recipe_name}_run*.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("eyeball") != "ok" or receipt.get("eyeball_source") != "human":
                continue
            if not receipt.get("eyeball_reviewed_at"):
                continue
            if receipt.get("boot_lane") != boot_lane:
                continue
            if media_fingerprint(receipt) != fingerprint:
                continue
            value = receipt.get("video_stream_bytes_per_frame")
            output_name = receipt.get("output_path")
            try:
                output_file = strict_output_artifact_path(output_name)
            except ValueError:
                continue
            if not value:
                continue
            artifact_hash = sha256_file(output_file)
            if receipt.get("artifact_sha256") != artifact_hash:
                continue
            if artifact_hash in artifact_hashes:
                continue
            artifact_hashes.add(artifact_hash)
            approved_values.append(float(value))
        except (OSError, ValueError, json.JSONDecodeError):
            continue

    if len(approved_values) < 3:
        return {
            "bitrate_anomaly": False,
            "bitrate_baseline_status": f"provisional:{len(approved_values)}-of-3-clean-artifacts",
            "clean_baseline_sample_count": len(approved_values),
        }

    clean_median = statistics.median(approved_values)
    ratio = float(current_bpf) / clean_median if clean_median else 0.0
    return {
        "bitrate_anomaly": ratio > 2.0,
        "bitrate_baseline_status": "clean-same-lane-median",
        "clean_baseline_sample_count": len(approved_values),
        "clean_median_video_stream_bytes_per_frame": round(clean_median, 2),
        "bitrate_ratio_to_clean_median": round(ratio, 3),
    }


def media_artifact_is_valid(
    metrics: Dict[str, Any],
    contract: Optional[Dict[str, Any]] = None,
    requires_audio: bool = False,
) -> bool:
    """Require a decodable, complete artifact matching its recipe contract."""
    if (
        metrics.get("media_probe_error")
        or not _positive_integer(metrics.get("encoded_frame_count"))
        or not _positive_integer(metrics.get("video_stream_bytes"))
        or not _positive_integer(metrics.get("encoded_width"))
        or not _positive_integer(metrics.get("encoded_height"))
        or not _positive_finite_real(metrics.get("encoded_fps"))
    ):
        return False

    contract = contract or {}
    if not media_contract_is_valid(contract):
        return False
    expected_frames = int(contract["frames"])
    expected_width = int(contract["width"])
    expected_height = int(contract["height"])
    expected_fps = float(contract["fps"])
    expected_duration = float(contract.get("target_s", contract.get("duration_s")))
    if int(metrics["encoded_frame_count"]) != expected_frames:
        return False
    if int(metrics["encoded_width"]) != expected_width:
        return False
    if int(metrics["encoded_height"]) != expected_height:
        return False
    if abs(float(metrics["encoded_fps"]) - expected_fps) > 0.01:
        return False
    tolerance = (1.0 / expected_fps) + 1e-9
    for duration_field in ("container_duration_s", "video_duration_s"):
        measured_duration = metrics.get(duration_field)
        if not _positive_finite_real(measured_duration):
            return False
        if abs(float(measured_duration) - expected_duration) > tolerance:
            return False
    if requires_audio and (
        not metrics.get("audio_present")
        or not _positive_integer(metrics.get("audio_stream_bytes"))
    ):
        return False
    if requires_audio:
        audio_duration = metrics.get("audio_duration_s")
        if not _positive_finite_real(audio_duration):
            return False
        if abs(float(audio_duration) - expected_duration) > tolerance:
            return False
    return True


def timing_receipt_fields(recipe_data: Dict[str, Any], media_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Materialize an explicit planned-vs-ffprobe timing receipt when requested."""
    timing_requirements = recipe_data.get("receipt_requirements", {}).get("timing")
    if not isinstance(timing_requirements, dict):
        return {}
    timing_plan = recipe_data.get("experiment", {}).get("timing_plan", {})
    contract = recipe_data.get("contract", {})
    target_s = float(timing_plan.get("target_s", contract.get("target_s", 0.0)) or 0.0)
    container_delivered_s = float(media_metrics.get("container_duration_s") or 0.0)
    video_delivered_s = float(media_metrics.get("video_duration_s") or 0.0)
    audio_value = media_metrics.get("audio_duration_s")
    audio_delivered_s = float(audio_value) if audio_value is not None else None
    fps = float(contract.get("fps") or 0.0)
    tolerance_s = float(
        timing_requirements.get("absolute_duration_error_lte_s")
        or (1.0 / fps if fps else 0.0)
    )
    duration_error_s = container_delivered_s - target_s
    return {
        "target_s": target_s,
        "frame_count": int(timing_plan.get("frame_count", contract.get("frames", 0)) or 0),
        "trim_frames": int(timing_plan.get("trim_frames", contract.get("trim_frames", 0)) or 0),
        "rendered_s": float(timing_plan.get("rendered_s", 0.0) or 0.0),
        "delivered_s": container_delivered_s,
        "container_delivered_s": container_delivered_s,
        "video_delivered_s": video_delivered_s,
        "audio_delivered_s": audio_delivered_s,
        "planned_delivered_s": float(timing_plan.get("delivered_s", target_s) or target_s),
        "tail_trim_s": float(timing_plan.get("tail_trim_s", 0.0) or 0.0),
        "duration_error_s": round(duration_error_s, 6),
        "duration_tolerance_s": tolerance_s,
        "duration_within_tolerance": (
            abs(duration_error_s) <= tolerance_s + 1e-9
            and abs(video_delivered_s - target_s) <= tolerance_s + 1e-9
            and (
                audio_delivered_s is None
                or abs(audio_delivered_s - target_s) <= tolerance_s + 1e-9
            )
        ),
        "video_duration_error_s": round(video_delivered_s - target_s, 6),
        "audio_duration_error_s": (
            round(audio_delivered_s - target_s, 6)
            if audio_delivered_s is not None
            else None
        ),
        "duration_measurement_source": "ffprobe format.duration plus per-stream duration",
    }


def pending_human_audio_fields(recipe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Seed explicit pending fields for Mini Mime's human-only inverted ear gate."""
    inverted = recipe_data.get("receipt_requirements", {}).get("inverted_ear_gate")
    if not isinstance(inverted, dict):
        return {}
    return {
        "audio_ear": "pending",
        "audio_ear_source": "pending_human",
        "audio_ear_reviewed_at": None,
        "soundscape_description": "",
        "speech_or_vocal_like_content": "pending",
        "diegetic_sync": "pending",
        "inverted_ear_gate_pass": False,
    }


def promotion_ready_for_run(
    warm_pass: bool, is_marginal: bool, requires_human_eyeball: bool
) -> bool:
    """Only fully warm, non-marginal, non-human-pending evidence is promotable."""
    return bool(warm_pass and not is_marginal and not requires_human_eyeball)


def recipe_requires_human_eyeball(recipe_data: Dict[str, Any]) -> bool:
    """Honor explicit recipe gates while preserving the mandatory H3 gate."""
    contract = recipe_data.get("contract", {})
    if not isinstance(contract, dict):
        return False
    return bool(
        contract.get("engine") == "minimax_h3"
        or contract.get("requires_human_eyeball") is True
    )


class PreflightError(Exception):
    """Raised when a preflight check fails."""
    def __init__(self, check_num: int, name: str, reason: str):
        self.check_num = check_num
        self.name = name
        self.reason = reason
        super().__init__(f"Preflight Check #{check_num} [{name}] FAILED: {reason}")


_manager_probe_guard_module: Any = None


def manager_probe_requested() -> bool:
    """Return the validated test-only Manager opt-in state."""
    raw = os.environ.get(MANAGER_PROBE_ENV)
    if raw in (None, ""):
        if os.environ.get(MANAGER_PROBE_LOG_ENV):
            raise PreflightError(
                9,
                "Boot lane",
                f"{MANAGER_PROBE_LOG_ENV} is set without {MANAGER_PROBE_ENV}=1",
            )
        return False
    if raw != "1":
        raise PreflightError(
            9,
            "Boot lane",
            f"{MANAGER_PROBE_ENV} must be exactly 1 when present",
        )
    return True


def manager_probe_phase(argv: List[str]) -> Optional[str]:
    """Parse the cold/warm proof phase for the explicit Manager test lane."""
    positions = [
        index for index, value in enumerate(argv) if value == MANAGER_PROBE_PHASE_FLAG
    ]
    if len(positions) > 1:
        raise ValueError(f"{MANAGER_PROBE_PHASE_FLAG} may be supplied only once")
    if not positions:
        if manager_probe_requested():
            raise ValueError(
                f"{MANAGER_PROBE_CLI_FLAG} requires "
                f"{MANAGER_PROBE_PHASE_FLAG} cold|warm"
            )
        return None
    index = positions[0]
    if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
        raise ValueError(f"{MANAGER_PROBE_PHASE_FLAG} requires cold or warm")
    phase = argv[index + 1]
    if phase not in {"cold", "warm"}:
        raise ValueError(f"{MANAGER_PROBE_PHASE_FLAG} must be cold or warm")
    if not manager_probe_requested():
        raise ValueError(
            f"{MANAGER_PROBE_PHASE_FLAG} is allowed only with "
            f"{MANAGER_PROBE_CLI_FLAG}"
        )
    return phase


def manager_probe_identity(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Return the immutable subset that may safely enter cold/warm identity."""
    if evidence.get("enabled") is not True:
        return {}
    advisory = evidence.get("advisory_config") or {}
    scan = evidence.get("log_scan") or {}
    authority = scan.get("authoritative_server_reported_mode") or {}
    source = scan.get("source_proof") or {}
    return {
        "recipe_scope": evidence.get("recipe_scope"),
        "guard_source": evidence.get("guard_source"),
        "test_boot_source": evidence.get("test_boot_source"),
        "offline_environment": evidence.get("offline_environment"),
        "advisory_config_path": (advisory.get("snapshot") or {}).get("path"),
        "advisory_config_sha256": (advisory.get("snapshot") or {}).get("sha256"),
        "authoritative_server_reported_mode": authority.get("resolved_mode"),
        "manager_source_sha256s": {
            key: (source.get(key) or {}).get("sha256")
            for key in (
                "manager_prestartup",
                "manager_server",
                "manager_core",
                "comfy_folder_paths",
                "manager_util",
            )
        },
        "prestartup_state_sha256": (
            (scan.get("current_prestartup_state") or {}).get("state_sha256")
        ),
        "preboot_record_sha256": (
            ((scan.get("preboot_records") or [{}])[0].get("record") or {}).get(
                "record_sha256"
            )
        ),
        "log_path": evidence.get("log_path"),
        "serving_pid": evidence.get("serving_pid"),
        "serving_process_create_time_ns": evidence.get(
            "serving_process_create_time_ns"
        ),
    }


def manager_probe_recipe_scope(recipe_name: str) -> Dict[str, Any]:
    """Resolve exactly one closed Manager recipe scope or fail closed."""

    if (
        not isinstance(recipe_name, str)
        or re.fullmatch(r"[A-Za-z0-9_.-]+", recipe_name) is None
    ):
        raise PreflightError(9, "Boot lane", "Manager probe recipe name is invalid")
    matches = []
    for scope_name, exact_names, prefix, log_root in MANAGER_PROBE_SCOPES:
        exact_match = recipe_name in exact_names
        prefix_match = bool(prefix and recipe_name.startswith(prefix))
        if exact_match or prefix_match:
            matches.append(
                {
                    "scope": scope_name,
                    "match_type": "exact" if exact_match else "prefix",
                    "match_value": recipe_name if exact_match else prefix,
                    "log_root": Path(log_root),
                }
            )
    if len(matches) != 1:
        raise PreflightError(
            9,
            "Boot lane",
            "Manager offline probe recipe scope must match exactly one closed "
            f"allowlist entry; found {len(matches)} for {recipe_name!r}",
        )
    return matches[0]


def manager_probe_log_path(recipe_name: str) -> Path:
    """Resolve the attempt-unique Manager log without permitting path escape."""
    if not manager_probe_requested():
        return SERVER_LOG_FILE
    scope = manager_probe_recipe_scope(recipe_name)
    raw = os.environ.get(MANAGER_PROBE_LOG_ENV, "")
    path = Path(raw)
    if not raw or not path.is_absolute() or path.suffix.lower() != ".log":
        raise PreflightError(
            9,
            "Boot lane",
            f"{MANAGER_PROBE_LOG_ENV} must be an absolute .log path",
        )
    log_root = Path(scope["log_root"])
    lexical_root = Path(os.path.abspath(os.fspath(log_root)))
    lexical = Path(os.path.abspath(os.fspath(path)))
    if not os.path.lexists(lexical_root):
        raise PreflightError(9, "Boot lane", "Manager probe log root is absent")
    if _is_symlink_or_reparse_point(lexical_root):
        raise PreflightError(
            9, "Boot lane", "Manager probe log root is a symlink/reparse point"
        )
    try:
        if lexical_root.resolve(strict=True) != lexical_root:
            raise PreflightError(
                9, "Boot lane", "Manager probe log root does not resolve exactly"
            )
        lexical.relative_to(lexical_root)
        component = lexical_root
        for part in lexical.relative_to(lexical_root).parts[:-1]:
            component = component / part
            if os.path.lexists(component) and _is_symlink_or_reparse_point(component):
                raise PreflightError(
                    9,
                    "Boot lane",
                    "Manager probe log path contains a symlink/reparse point",
                )
        if os.path.lexists(lexical) and _is_symlink_or_reparse_point(lexical):
            raise PreflightError(
                9, "Boot lane", "Manager probe log is a symlink/reparse point"
            )
        resolved = lexical.resolve()
        if resolved != lexical:
            raise PreflightError(
                9, "Boot lane", "Manager probe log path does not resolve exactly"
            )
    except PreflightError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise PreflightError(
            9, "Boot lane", f"Cannot prove Manager probe log containment: {exc}"
        ) from exc
    try:
        resolved.relative_to(lexical_root)
    except ValueError as exc:
        raise PreflightError(
            9,
            "Boot lane",
            f"Manager probe log must stay under {log_root}",
        ) from exc
    return resolved


def load_manager_probe_guard() -> Any:
    """Load the H3-specific guard only for the explicit test lane."""
    global _manager_probe_guard_module
    if _manager_probe_guard_module is not None:
        return _manager_probe_guard_module
    if not MANAGER_PROBE_GUARD_SOURCE.is_file():
        raise PreflightError(
            9,
            "Boot lane",
            f"Manager probe guard is missing: {MANAGER_PROBE_GUARD_SOURCE}",
        )
    spec = importlib.util.spec_from_file_location(
        "h3_manager_offline_guard_runtime", MANAGER_PROBE_GUARD_SOURCE
    )
    if spec is None or spec.loader is None:
        raise PreflightError(9, "Boot lane", "Cannot load Manager probe guard")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _manager_probe_guard_module = module
    return module


def initialize_manager_probe_log(log_path: Path) -> Dict[str, Any]:
    """Exclusively create a byte-zero log with the prestartup no-op record."""
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(str(log_path), flags, 0o600)
        try:
            guard = load_manager_probe_guard()
            preboot_line = guard.preboot_log_line(
                MANAGER_PROBE_USER_DIRECTORY, dict(os.environ)
            )
            written = os.write(fd, preboot_line)
            if written != len(preboot_line):
                raise OSError("short write for Manager preboot record")
            os.fsync(fd)
        finally:
            os.close(fd)
        retained = log_path.read_bytes()
        if retained != preboot_line:
            raise OSError("exclusive Manager probe log preboot record drifted")
        return {
            "path": str(log_path.resolve()),
            "bytes": len(retained),
            "sha256": sha256_bytes(retained),
            "exclusive_create": True,
            "preboot_record_starts_at_byte_zero": True,
        }
    except Exception as exc:
        raise PreflightError(
            3,
            "Server up",
            "Could not atomically create and state-bind the byte-zero "
            f"Manager probe log: {exc}",
        ) from exc


def manager_probe_evidence(
    recipe_name: str,
    argv: List[str],
    *,
    require_pre_prompt: bool,
) -> Dict[str, Any]:
    """Prove the test-only Manager lane from its unique live server log."""
    if not manager_probe_requested():
        return {
            "enabled": False,
            "default_manager_disabled": True,
        }
    scope = manager_probe_recipe_scope(recipe_name)
    log_path = manager_probe_log_path(recipe_name)
    if not log_path.is_file():
        raise PreflightError(9, "Boot lane", f"Manager probe log is absent: {log_path}")
    try:
        guard = load_manager_probe_guard()
        environment = guard.offline_environment_evidence(dict(os.environ))
        config = guard.config_evidence(argv)
        if require_pre_prompt:
            scan = guard.wait_for_pre_prompt_gate(
                log_path,
                argv,
                expected_url=COMFY_SERVER_URL,
            )
        else:
            scan = guard.scan_log(
                log_path,
                argv,
                expected_url=COMFY_SERVER_URL,
                require_pre_prompt=False,
            )
        scan_errors = guard.validate_scan_binding(scan, log_path, argv)
        if scan_errors:
            raise guard.ManagerProbeError("; ".join(scan_errors))
        serving_pid = listener_pid(int(LAB_PORT))
        if serving_pid is None:
            raise guard.ManagerProbeError("lab listener PID is absent")
        process_created_ns = int(psutil.Process(serving_pid).create_time() * 1e9)
        if int(scan["log"]["mtime_ns"]) < process_created_ns:
            raise guard.ManagerProbeError("Manager probe log predates serving process")
        return {
            "enabled": True,
            "valid": True,
            "recipe_scope": {
                "scope": scope["scope"],
                "match_type": scope["match_type"],
                "match_value": scope["match_value"],
                "log_root": str(Path(scope["log_root"]).resolve()),
            },
            "verified_before_this_prompt": True,
            "require_no_prior_prompt": require_pre_prompt,
            "log_path": str(log_path),
            "serving_pid": serving_pid,
            "serving_process_create_time_ns": process_created_ns,
            "offline_environment": environment,
            "advisory_config": config,
            "log_scan": scan,
            "guard_source": {
                "path": str(MANAGER_PROBE_GUARD_SOURCE.resolve()),
                "sha256": sha256_file(MANAGER_PROBE_GUARD_SOURCE),
            },
            "test_boot_source": {
                "path": str(MANAGER_PROBE_BOOT_CMD.resolve()),
                "sha256": sha256_file(MANAGER_PROBE_BOOT_CMD),
            },
        }
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError(
            9,
            "Boot lane",
            f"Manager offline probe failed: {type(exc).__name__}: {exc}",
        ) from exc


class LockManager:
    """GPU lease facade that maps coordinator failures to preflight errors."""

    def __init__(
        self,
        lock_path: Path = LOCKFILE_PATH,
        *,
        suite_child: bool = False,
        suite_lock_path: Optional[Path] = None,
        coordinator_path: Optional[Path] = None,
        environment: Optional[Dict[str, str]] = None,
    ):
        self.lock_path = Path(lock_path)
        self._lease = lab_locks.GpuLease(
            self.lock_path,
            Path(suite_lock_path or SUITE_LOCKFILE_PATH),
            Path(coordinator_path or COORDINATOR_MUTEX_PATH),
            suite_child=suite_child,
            environment=environment,
        )
        self._context_owns_acquisition = False

    @property
    def acquired(self) -> bool:
        return self._lease.acquired

    @property
    def owner(self) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._lease.owner)

    def acquire(self):
        try:
            self._lease.acquire()
        except (lab_locks.LeaseError, OSError) as exc:
            raise PreflightError(1, "Lock", str(exc)) from exc
        if self._lease.reentrant_suite:
            print(f"[LOCK] Re-entered suite GPU lease (child PID {os.getpid()})")
        else:
            print(f"[LOCK] Acquired coordinator and .gpu.lock (PID {os.getpid()})")

    def release(self):
        if not self.acquired:
            return
        was_reentrant = self._lease.reentrant_suite
        try:
            self._lease.release()
        except lab_locks.LeaseError as exc:
            raise PreflightError(1, "Lock release", str(exc)) from exc
        if was_reentrant:
            print("[LOCK] Left suite GPU lease intact for parent")
        else:
            print("[LOCK] Released .gpu.lock and coordinator")

    def __enter__(self):
        if not self.acquired:
            self.acquire()
            self._context_owns_acquisition = True
        else:
            self._context_owns_acquisition = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._context_owns_acquisition:
            self.release()
        self._context_owns_acquisition = False


def query_gpu_vram_mb() -> float:
    """Query current GPU VRAM usage in MB via nvidia-smi."""
    res = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True
    )
    return float(res.stdout.strip().splitlines()[0])


def query_gpu_total_gib() -> float:
    """Query physical GPU memory in GiB using nvidia-smi's MiB value."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip().splitlines()[0]) / 1024.0


def reserve_for_target_gib(physical_total_gib: float, target_gib: float) -> float:
    """Translate a target-card budget into ComfyUI --reserve-vram semantics."""
    if not math.isfinite(target_gib) or target_gib <= 0:
        raise ValueError("Clamp target must be positive")
    if target_gib > physical_total_gib:
        raise ValueError(
            f"Clamp target {target_gib:.3f} GiB exceeds physical VRAM {physical_total_gib:.3f} GiB"
        )
    return max(0.0, physical_total_gib - target_gib)


def validate_reserve_gib(value: float, physical_total_gib: float) -> float:
    """Validate direct ComfyUI reserve-vram input."""
    if not math.isfinite(value) or value < 0:
        raise ValueError("Direct reserve-vram must be a finite, nonnegative GiB value")
    if value >= physical_total_gib:
        raise ValueError(
            f"Direct reserve-vram {value:g} GiB must be below physical VRAM {physical_total_gib:.3f} GiB"
        )
    return value


def query_host_ram_gb() -> float:
    """Query current host system RAM usage in GB via psutil."""
    return psutil.virtual_memory().used / (1024.0 ** 3)


class ResourceMonitorThread(threading.Thread):
    """Background thread polling GPU VRAM and Host System RAM at 200ms interval."""

    def __init__(self, interval: float = 0.2):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak_vram_gb = 0.0
        self.peak_host_ram_gb = 0.0
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                vram_mb = query_gpu_vram_mb()
                vram_gb = vram_mb / 1024.0
                if vram_gb > self.peak_vram_gb:
                    self.peak_vram_gb = vram_gb

                host_gb = query_host_ram_gb()
                if host_gb > self.peak_host_ram_gb:
                    self.peak_host_ram_gb = host_gb
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self) -> Tuple[float, float]:
        self._stop_event.set()
        self.join(timeout=2.0)
        return self.peak_vram_gb, self.peak_host_ram_gb


def get_recorded_pid() -> Optional[int]:
    """Retrieve recorded lab server PID from .server.pid."""
    if os.path.lexists(SERVER_PID_FILE):
        try:
            content = SERVER_PID_FILE.read_text(encoding="utf-8-sig", errors="ignore").strip()
            if content:
                pid = int(content)
                if psutil.pid_exists(pid):
                    return pid
        except (ValueError, OSError):
            pass
    return None


def cleanup_stale_pid_receipt() -> bool:
    """Remove a stale owned-server receipt and its exact sidecar after clear proof."""
    if not os.path.lexists(SERVER_PID_FILE):
        return False
    try:
        receipt = _snapshot_server_pid_receipt()
        pid = int(receipt["pid"])
    except (ServerPidReceiptError, KeyError, TypeError, ValueError) as exc:
        print(f"[SERVER] Keeping unverifiable .server.pid receipt: {exc}")
        return False
    if psutil.pid_exists(pid):
        return False
    cleanup = shutdown_lab_server()
    return bool(cleanup.get("success") and cleanup.get("receipt_removed"))


class GpuIdleGateError(RuntimeError):
    """Raised when pre-boot WDDM quiescence cannot be proved."""


def _idle_run_nvidia_smi(argv: List[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GpuIdleGateError(f"nvidia-smi query failed: {exc}") from exc


def _idle_csv_rows(stdout: str) -> List[List[str]]:
    return [
        [field.strip() for field in row]
        for row in csv.reader(io.StringIO(stdout))
        if row and any(field.strip() for field in row)
    ]


def _idle_finite_nonnegative(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise GpuIdleGateError(f"Non-numeric {label}: {value!r}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise GpuIdleGateError(f"Invalid {label}: {value!r}")
    return parsed


def gpu_idle_gate_contract() -> Dict[str, Any]:
    """Return the stable policy/source contract that may enter run identity."""

    runner = Path(__file__).resolve()
    return {
        "schema_version": 1,
        "kind": "run-recipe-preboot-wddm-idle-gate-contract",
        "gpu_index": GPU_IDLE_INDEX,
        "port": int(LAB_PORT),
        "sample_count": GPU_IDLE_SAMPLE_COUNT,
        "sampling_interval_s": GPU_IDLE_SAMPLE_INTERVAL_S,
        "aggregation": "maximum of five conjunctively quiescent WDDM samples",
        "policy": {
            "maximum_vram_used_mib": float(GPU_IDLE_BASELINE_MAX_MB),
            "vram_used_mib_threshold_gating": True,
            "operator_idle_policy": operator_idle_policy_contract(),
            "gpu_utilization_recorded_non_gating": True,
            "memory_utilization_recorded_non_gating": True,
            "recognized_unmetered_wddm_memory_token": (
                GPU_IDLE_WDDM_UNMETERED_MEMORY_TOKEN
            ),
            "numeric_or_unknown_process_memory_tokens_block": True,
            "live_process_identity_required": True,
            "desktop_graphics_signals_retained_but_not_required": True,
            "model_workload_markers": list(GPU_IDLE_MODEL_WORKLOAD_MARKERS),
            "known_workload_classifier": known_workload_classifier_contract(),
            "port_8199_listener_required_absent": True,
            "same_gpu_lease_required_each_sample": True,
            "required_driver_model": GPU_IDLE_REQUIRED_DRIVER_MODEL,
            "display_active_allowed_measured_states": sorted(
                GPU_IDLE_DISPLAY_ACTIVE_MEASURED_STATES
            ),
            "display_active_recorded_non_gating": True,
            "current_runner_exclusion": (
                "exact real runner PID/create-time/target plus at most one verified "
                "direct Windows venv launcher stub"
            ),
        },
        "collector": {
            "path": str(runner),
            "sha256": sha256_file(runner),
        },
    }


def operator_idle_policy_contract() -> Dict[str, Any]:
    """Return the stable operator authorization bound into run identity."""

    return {
        "schema_version": 1,
        "kind": "operator-authorized-desktop-baseline-policy",
        "preboot_baseline_maximum_mib": float(
            GPU_IDLE_BASELINE_MAX_MB
        ),
        "preboot_baseline_threshold_gating": True,
        "elevated_baseline_threshold_mib": float(
            GPU_IDLE_STANDARD_BASELINE_MAX_MB
        ),
        "elevated_baseline_condition": "recorded baseline is strictly greater than 2.0 GiB",
        "elevated_baseline_stamp": GPU_IDLE_ELEVATED_BASELINE_STAMP,
        "known_render_compute_processes_block": True,
        "utilization_descriptors_non_gating": True,
        "pair_cold_warm_baseline_drift_advisory_gib": 0.5,
        "pair_drift_threshold_gating": False,
        "pair_drift_condition": (
            "compare each same-identity warm baseline_vram_gb to the prior cold leg; "
            "record absolute drift and threshold exceedance without blocking"
        ),
        PREQUEUE_WORKLOAD_SCAN_CONTRACT_KEY: prequeue_known_workload_scan_contract(),
        "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
        "authorized_on": "2026-08-10",
    }


def prequeue_known_workload_scan_contract() -> Dict[str, Any]:
    """Return stable semantics for the mandatory per-leg prequeue process scan."""

    return {
        "schema_version": 1,
        "kind": "per-leg-immediate-prequeue-known-workload-scan-contract",
        "timing": (
            "every cold and warm leg, after queue-idle and baseline/drift measurements, "
            "immediately before POST /prompt"
        ),
        "model_workload_markers": list(GPU_IDLE_MODEL_WORKLOAD_MARKERS),
        "known_workload_classifier": known_workload_classifier_contract(),
        "exact_exclusions": [
            "current run_recipe PID + create time + resolved run_recipe.py argv",
            (
                "optional one-hop direct Windows venv launcher at "
                "sys.prefix/Scripts/python.exe with identical argv tail, exact runner "
                "targets, live PID/create-times, distinct child executable, and <=5s creation delta"
            ),
            (
                "owned port-8199 serving PID + create time + exact self-reported "
                "server argv (with only its Python interpreter prefix permitted)"
            ),
            (
                "optional one-hop direct owned-server Windows venv launcher at "
                "sys.prefix/Scripts/python.exe with identical argv tail, both exact "
                "validated self-reported server argv, live PID/create-times, distinct "
                "serving-child executable, and <=5s creation delta"
            ),
        ],
        "owned_lab_server_exclusion_schema": list(
            PREQUEUE_OWNED_SERVER_EXCLUSION_SCHEMA
        ),
        "verified_owned_server_windows_venv_launcher_schema": list(
            PREQUEUE_VERIFIED_SERVER_VENV_LAUNCHER_SCHEMA
        ),
        "excluded_owned_lab_server_row_schema": list(
            PREQUEUE_EXCLUDED_OWNED_SERVER_ROW_SCHEMA
        ),
        "owned_server_launcher_boot_lineage": (
            "not inferred when unavailable; only the exact serving PID direct parent "
            "may be excluded, never arbitrary ancestors"
        ),
        "python_without_readable_argv_blocks": False,
        "advisory_unreadable_processes_retained": True,
        "listener_binding_required_before_and_after_scan": True,
        "warm_leg_scan_required": True,
        "blocking_condition": "any known render/compute workload is live",
    }


def known_workload_classifier_contract() -> Dict[str, Any]:
    """Return the shared token-aware cold/prequeue classifier contract."""

    return {
        "schema_version": 1,
        "kind": "token-aware-positive-known-workload-classifier",
        "python_script_markers": ["main.py", "run_recipe.py"],
        "other_markers": [
            marker
            for marker in GPU_IDLE_MODEL_WORKLOAD_MARKERS
            if marker not in {"main.py", "run_recipe.py"}
        ],
        "positive_match_sources": [
            "process_basename",
            "executable_basename",
            "actual_python_script_or_module_target",
        ],
        "arbitrary_later_argv_values_ignored": True,
        "exact_exclusions_run_before_classifier": True,
        "optional_current_windows_venv_launcher_exclusion": (
            "one direct parent only; exact sys.prefix/Scripts/python.exe; launcher "
            "argv[1:] equals real child argv[1:]; both target run_recipe.py; live "
            "PID/create-times; real child executable differs; ordered creation delta <=5s"
        ),
        "current_runner_exclusion_schema": list(
            GPU_IDLE_CURRENT_RUNNER_EXCLUSION_SCHEMA
        ),
        "verified_windows_venv_launcher_schema": list(
            GPU_IDLE_VERIFIED_VENV_LAUNCHER_SCHEMA
        ),
        "excluded_current_runner_row_schema": list(
            GPU_IDLE_EXCLUDED_CURRENT_RUNNER_ROW_SCHEMA
        ),
        "unreadable_or_unmatched_python_is_advisory": True,
        "redacted_process_schema": [
            "pid",
            "process_create_time",
            "process_basename",
            "executable_basename",
            "target_basename",
            "matched_markers",
            "match_basis",
            "argv_sha256",
        ],
        "argv_sha256_bytes": "UTF-8 canonical JSON argv list",
    }


def vram_receipt_fields(
    baseline_vram_gb: float, peak_vram_gb: float
) -> Dict[str, Any]:
    """Build honest absolute/baseline/net per-leg receipt measurements."""

    try:
        baseline = float(baseline_vram_gb)
        peak = float(peak_vram_gb)
    except (TypeError, ValueError) as exc:
        raise ValueError("VRAM receipt measurements must be numeric") from exc
    if (
        not math.isfinite(baseline)
        or not math.isfinite(peak)
        or baseline < 0
        or peak < baseline
    ):
        raise ValueError(
            "VRAM receipt measurements must be finite, nonnegative, and peak >= baseline"
        )

    # nvidia-smi reports MiB; three decimals after dividing by 1024 retain
    # approximately one-MiB resolution. Compute the displayed net from the
    # displayed operands so the receipt remains arithmetically self-consistent.
    recorded_baseline = round(baseline, 3)
    recorded_peak = round(peak, 3)
    recorded_net = round(recorded_peak - recorded_baseline, 3)
    elevated = recorded_baseline > (
        float(GPU_IDLE_STANDARD_BASELINE_MAX_MB) / 1024.0
    )
    stamp = GPU_IDLE_ELEVATED_BASELINE_STAMP if elevated else None
    return {
        "peak_vram_gb": recorded_peak,
        "absolute_peak_vram_gb": recorded_peak,
        "baseline_vram_gb": recorded_baseline,
        "net_peak_vram_gb": recorded_net,
        "elevated_baseline_lane": elevated,
        "baseline_lane_stamp": stamp,
        "vram_measurement": {
            "units": "GiB (nvidia-smi MiB / 1024)",
            "baseline_measurement_point": (
                "immediately before prompt queue; includes owned lab server and desktop load"
            ),
            "baseline_absolute_gib": recorded_baseline,
            "peak_absolute_gib": recorded_peak,
            "net_peak_gib": recorded_net,
            "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
        },
    }


def prompt_baseline_advisory(baseline_vram_gb: float) -> Dict[str, Any]:
    """Evaluate the hard per-leg pre-prompt absolute baseline gate."""

    try:
        baseline = float(baseline_vram_gb)
    except (TypeError, ValueError) as exc:
        raise PreflightError(
            2, "GPU idle", f"Pre-queue baseline is not numeric: {baseline_vram_gb!r}"
        ) from exc
    limit_gib = float(GPU_IDLE_BASELINE_MAX_MB) / 1024.0
    if not math.isfinite(baseline) or baseline < 0:
        raise PreflightError(
            2, "GPU idle", f"Pre-queue baseline is invalid: {baseline_vram_gb!r}"
        )
    recorded = round(baseline, 3)
    return {
        "schema_version": 1,
        "kind": "per-leg-prequeue-baseline-gate",
        "baseline_vram_gb": recorded,
        "maximum_threshold_gb": limit_gib,
        "threshold_exceeded": recorded > limit_gib,
        "gating": True,
        "disposition": (
            "abort before prompt" if recorded > limit_gib else "proceed"
        ),
    }


def pair_baseline_drift_advisory(
    baseline_vram_gb: float,
    previous_result: Dict[str, Any],
    config_run_count: int,
) -> Dict[str, Any]:
    """Describe same-identity cold/warm baseline drift without gating execution."""

    threshold = 0.5
    if config_run_count < 2:
        return {
            "schema_version": 1,
            "kind": "same-identity-cold-warm-baseline-drift-advisory",
            "applicable": False,
            "measurement_available": False,
            "previous_baseline_vram_gb": None,
            "current_baseline_vram_gb": round(float(baseline_vram_gb), 3),
            "absolute_drift_gb": None,
            "advisory_threshold_gb": threshold,
            "threshold_exceeded": False,
            "gating": False,
            "disposition": "record-only; no same-identity prior leg",
        }
    try:
        current = float(baseline_vram_gb)
        previous = float(previous_result["baseline_vram_gb"])
    except (KeyError, TypeError, ValueError):
        return {
            "schema_version": 1,
            "kind": "same-identity-cold-warm-baseline-drift-advisory",
            "applicable": True,
            "measurement_available": False,
            "previous_baseline_vram_gb": None,
            "current_baseline_vram_gb": round(float(baseline_vram_gb), 3),
            "absolute_drift_gb": None,
            "advisory_threshold_gb": threshold,
            "threshold_exceeded": None,
            "gating": False,
            "disposition": "record-only; prior baseline unavailable",
        }
    if not all(math.isfinite(value) and value >= 0 for value in (current, previous)):
        return {
            "schema_version": 1,
            "kind": "same-identity-cold-warm-baseline-drift-advisory",
            "applicable": True,
            "measurement_available": False,
            "previous_baseline_vram_gb": None,
            "current_baseline_vram_gb": (
                round(current, 3) if math.isfinite(current) and current >= 0 else None
            ),
            "absolute_drift_gb": None,
            "advisory_threshold_gb": threshold,
            "threshold_exceeded": None,
            "gating": False,
            "disposition": "record-only; drift inputs invalid",
        }
    recorded_current = round(current, 3)
    recorded_previous = round(previous, 3)
    drift = round(abs(recorded_current - recorded_previous), 3)
    return {
        "schema_version": 1,
        "kind": "same-identity-cold-warm-baseline-drift-advisory",
        "applicable": True,
        "measurement_available": True,
        "previous_baseline_vram_gb": recorded_previous,
        "current_baseline_vram_gb": recorded_current,
        "absolute_drift_gb": drift,
        "advisory_threshold_gb": threshold,
        "threshold_exceeded": drift > threshold,
        "gating": False,
        "disposition": "record-only; proceed regardless of drift",
    }


def _idle_target_gpu_identity(gpu_index: int = GPU_IDLE_INDEX) -> Dict[str, Any]:
    argv = [
        "nvidia-smi",
        "-i",
        str(gpu_index),
        "--query-gpu=index,uuid,name,memory.total,driver_model.current,display_active",
        "--format=csv,noheader,nounits",
    ]
    result = _idle_run_nvidia_smi(argv)
    rows = _idle_csv_rows(result.stdout)
    if len(rows) != 1 or len(rows[0]) != 6:
        raise GpuIdleGateError(f"Unexpected target-GPU identity rows: {rows!r}")
    index, uuid_value, name, total, driver_model, display_active = rows[0]
    if int(index) != int(gpu_index) or not uuid_value.startswith("GPU-"):
        raise GpuIdleGateError(f"Target GPU identity mismatch: {rows[0]!r}")
    if driver_model != GPU_IDLE_REQUIRED_DRIVER_MODEL:
        raise GpuIdleGateError(
            "Pre-boot unmetered-client policy requires exact WDDM driver mode; "
            f"found driver_model={driver_model!r}, display_active={display_active!r}"
        )
    if display_active not in GPU_IDLE_DISPLAY_ACTIVE_MEASURED_STATES:
        raise GpuIdleGateError(
            f"Unexpected display_active measured state: {display_active!r}"
        )
    return {
        "gpu_index": int(index),
        "gpu_uuid": uuid_value,
        "gpu_name": name,
        "vram_total_mib": _idle_finite_nonnegative(total, "GPU total memory"),
        "driver_model_current": driver_model,
        "display_active": display_active,
        "query_argv": argv,
        "raw_stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
    }


def _idle_query_gpu_activity(
    gpu_index: int, expected_uuid: str
) -> Dict[str, Any]:
    argv = [
        "nvidia-smi",
        "-i",
        str(gpu_index),
        "--query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu,utilization.memory,pstate,driver_model.current,display_active",
        "--format=csv,noheader,nounits",
    ]
    result = _idle_run_nvidia_smi(argv)
    rows = _idle_csv_rows(result.stdout)
    if len(rows) != 1 or len(rows[0]) != 10:
        raise GpuIdleGateError(f"Unexpected target-GPU activity rows: {rows!r}")
    (
        index,
        uuid_value,
        name,
        used,
        total,
        gpu_util,
        memory_util,
        pstate,
        driver_model,
        display_active,
    ) = rows[0]
    if int(index) != int(gpu_index) or uuid_value != expected_uuid:
        raise GpuIdleGateError(
            f"Target GPU changed during idle gate: index={index!r}, "
            f"uuid={uuid_value!r}"
        )
    used_mib = _idle_finite_nonnegative(used, "used VRAM")
    total_mib = _idle_finite_nonnegative(total, "total VRAM")
    gpu_percent = _idle_finite_nonnegative(gpu_util, "GPU utilization")
    memory_percent = _idle_finite_nonnegative(memory_util, "memory utilization")
    if used_mib > total_mib or gpu_percent > 100 or memory_percent > 100:
        raise GpuIdleGateError("nvidia-smi target-GPU activity values are out of range")
    if driver_model != GPU_IDLE_REQUIRED_DRIVER_MODEL:
        raise GpuIdleGateError(
            "Target GPU left exact WDDM driver mode during idle gate: "
            f"driver_model={driver_model!r}, display_active={display_active!r}"
        )
    if display_active not in GPU_IDLE_DISPLAY_ACTIVE_MEASURED_STATES:
        raise GpuIdleGateError(
            f"Unexpected display_active measured state: {display_active!r}"
        )
    return {
        "gpu_index": int(index),
        "gpu_uuid": uuid_value,
        "gpu_name": name,
        "vram_used_mib": used_mib,
        "vram_total_mib": total_mib,
        "gpu_utilization_percent": gpu_percent,
        "memory_utilization_percent": memory_percent,
        "performance_state": pstate,
        "driver_model_current": driver_model,
        "display_active": display_active,
        "query_argv": argv,
        "raw_stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
    }


def _idle_process_identity(pid: int) -> Dict[str, Any]:
    identity: Dict[str, Any] = {
        "pid": int(pid),
        "exists": False,
        "name": None,
        "executable": None,
        "command_line": None,
        "process_create_time": None,
        "identity_errors": [],
    }
    try:
        process = psutil.Process(pid)
        identity["exists"] = True
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        identity["identity_errors"].append(f"process: {type(exc).__name__}: {exc}")
        return identity
    for key, getter in (
        ("name", process.name),
        ("executable", process.exe),
        ("command_line", process.cmdline),
        ("process_create_time", process.create_time),
    ):
        try:
            value = getter()
            identity[key] = list(value) if key == "command_line" else value
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
            identity["identity_errors"].append(f"{key}: {type(exc).__name__}: {exc}")
    return identity


def _idle_command_line_has_exact_runner(command_line: Any) -> bool:
    expected = os.path.normcase(str(Path(__file__).resolve()))
    argv = [str(value) for value in command_line or []]
    target = _workload_python_target(argv)
    if target.get("kind") != "script" or not target.get("identity"):
        return False
    try:
        resolved = os.path.normcase(str(Path(str(target["identity"])).resolve()))
    except (OSError, RuntimeError):
        return False
    return resolved == expected


def _idle_verified_current_windows_venv_launcher(
    child_identity: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Prove the one direct Windows venv launcher stub for this real runner."""

    if os.name != "nt" or sys.prefix == sys.base_prefix:
        return None
    try:
        venv_prefix = Path(sys.prefix).resolve()
        expected_launcher = (venv_prefix / "Scripts" / "python.exe").resolve()
        if not (venv_prefix / "pyvenv.cfg").is_file():
            return None
        child_pid = int(child_identity["pid"])
        child_created = float(child_identity["process_create_time"])
        launcher_pid = int(os.getppid())
        launcher_identity = _idle_process_identity(launcher_pid)
        launcher_created = float(launcher_identity["process_create_time"])
        launcher_argv = [
            str(value) for value in launcher_identity.get("command_line") or []
        ]
        child_argv = [str(value) for value in child_identity.get("command_line") or []]
        launcher_exe = Path(str(launcher_identity.get("executable"))).resolve()
        child_exe = Path(str(child_identity.get("executable"))).resolve()
        direct_parent_verified = psutil.Process(child_pid).ppid() == launcher_pid
        launcher_live = lab_locks.process_identity_is_live(
            launcher_pid, launcher_created
        )
        child_live = lab_locks.process_identity_is_live(child_pid, child_created)
        exact = (
            launcher_identity.get("exists") is True
            and launcher_pid > 0
            and launcher_pid != child_pid
            and direct_parent_verified
            and os.path.normcase(str(launcher_exe))
            == os.path.normcase(str(expected_launcher))
            and os.path.normcase(str(child_exe))
            != os.path.normcase(str(expected_launcher))
            and len(launcher_argv) >= 2
            and len(child_argv) >= 2
            and launcher_argv[1:] == child_argv[1:]
            and _idle_command_line_has_exact_runner(launcher_argv)
            and _idle_command_line_has_exact_runner(child_argv)
            and launcher_live
            and child_live
            and launcher_created <= child_created + 0.001
            and child_created - launcher_created <= 5.0
        )
        if not exact:
            return None
        return {
            "pid": launcher_pid,
            "process_create_time": launcher_created,
            "expected_launcher_path": str(expected_launcher),
            "direct_child_pid": child_pid,
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_runner_target": True,
            "child_executable_differs": True,
            "creation_delta_s": round(child_created - launcher_created, 6),
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": launcher_identity,
        }
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        RuntimeError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        return None


def _idle_retained_process_identity_validation_errors(
    value: Any, label: str
) -> List[str]:
    errors = []
    if not isinstance(value, dict) or set(value) != set(
        GPU_IDLE_PROCESS_IDENTITY_SCHEMA
    ):
        return [f"{label} process identity shape is invalid"]
    pid = value.get("pid")
    created = value.get("process_create_time")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        errors.append(f"{label} process identity PID is invalid")
    if (
        not isinstance(created, (int, float))
        or isinstance(created, bool)
        or not math.isfinite(float(created))
        or float(created) <= 0
    ):
        errors.append(f"{label} process identity create time is invalid")
    if value.get("exists") is not True:
        errors.append(f"{label} process identity was not retained as live")
    for field in ("name", "executable"):
        if not isinstance(value.get(field), str) or not value.get(field):
            errors.append(f"{label} process identity {field} is invalid")
    argv = value.get("command_line")
    if (
        not isinstance(argv, list)
        or len(argv) < 2
        or not all(isinstance(token, str) for token in argv)
    ):
        errors.append(f"{label} process identity argv is invalid")
    identity_errors = value.get("identity_errors")
    if not isinstance(identity_errors, list) or not all(
        isinstance(error, str) for error in identity_errors
    ):
        errors.append(f"{label} process identity error evidence is invalid")
    return errors


def current_runner_exclusion_validation_errors(
    exclusion: Any, excluded_current_runner: Optional[Any] = None
) -> List[str]:
    """Validate retained real-runner and optional one-hop launcher evidence.

    This validator intentionally performs no process queries.  It independently
    checks that the immutable evidence records the same narrow relationship that
    was proved live by the collector, and optionally checks the exact rows that
    the process enumeration excluded.
    """

    errors = []
    if not isinstance(exclusion, dict) or set(exclusion) != set(
        GPU_IDLE_CURRENT_RUNNER_EXCLUSION_SCHEMA
    ):
        return ["current runner exclusion shape is invalid"]

    pid = exclusion.get("pid")
    created = exclusion.get("process_create_time")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        errors.append("current runner exclusion PID is invalid")
    if (
        not isinstance(created, (int, float))
        or isinstance(created, bool)
        or not math.isfinite(float(created))
        or float(created) <= 0
    ):
        errors.append("current runner exclusion create time is invalid")
    if exclusion.get("narrowly_verified") is not True:
        errors.append("current runner exclusion narrow proof is absent")
    if exclusion.get("excluded_pid_only") is not True:
        errors.append("current runner exclusion is not PID-only")
    if exclusion.get("resolved_runner_path") != str(Path(__file__).resolve()):
        errors.append("current runner exclusion path is wrong")

    child_identity = exclusion.get("process_identity")
    errors.extend(
        _idle_retained_process_identity_validation_errors(
            child_identity, "current runner"
        )
    )
    child_argv = []
    child_executable = None
    if isinstance(child_identity, dict):
        child_argv = child_identity.get("command_line") or []
        child_executable = child_identity.get("executable")
        if child_identity.get("pid") != pid:
            errors.append("current runner retained PID does not match")
        try:
            if not math.isclose(
                float(child_identity.get("process_create_time")),
                float(created),
                rel_tol=0.0,
                abs_tol=0.001,
            ):
                errors.append("current runner retained create time does not match")
        except (TypeError, ValueError):
            pass
        if not _idle_command_line_has_exact_runner(child_argv):
            errors.append("current runner retained argv does not target this runner")

    launcher = exclusion.get("verified_windows_venv_launcher")
    expected_count = 1
    launcher_pid = None
    launcher_created = None
    if launcher is not None:
        expected_count = 2
        if not isinstance(launcher, dict) or set(launcher) != set(
            GPU_IDLE_VERIFIED_VENV_LAUNCHER_SCHEMA
        ):
            errors.append("verified Windows venv launcher shape is invalid")
        else:
            launcher_pid = launcher.get("pid")
            launcher_created = launcher.get("process_create_time")
            try:
                launcher_pid_valid = (
                    isinstance(launcher_pid, int)
                    and not isinstance(launcher_pid, bool)
                    and launcher_pid > 0
                    and launcher_pid != pid
                )
                launcher_created_valid = (
                    isinstance(launcher_created, (int, float))
                    and not isinstance(launcher_created, bool)
                    and math.isfinite(float(launcher_created))
                    and float(launcher_created) > 0
                )
            except (TypeError, ValueError):
                launcher_pid_valid = False
                launcher_created_valid = False
            if not launcher_pid_valid:
                errors.append("verified Windows venv launcher PID is invalid")
            if not launcher_created_valid:
                errors.append("verified Windows venv launcher create time is invalid")
            if os.name != "nt" or sys.prefix == sys.base_prefix:
                errors.append("verified Windows venv launcher is outside a Windows venv")
            expected_launcher_path = str(
                (Path(sys.prefix).resolve() / "Scripts" / "python.exe").resolve()
            )
            try:
                launcher_path_matches = (
                    os.path.normcase(
                        str(Path(str(launcher.get("expected_launcher_path"))).resolve())
                    )
                    == os.path.normcase(expected_launcher_path)
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                launcher_path_matches = False
            if not launcher_path_matches:
                errors.append("verified Windows venv launcher path is wrong")
            if launcher.get("direct_child_pid") != pid:
                errors.append("verified Windows venv launcher child PID is wrong")
            for flag in (
                "direct_parent_verified",
                "launcher_identity_live",
                "child_identity_live",
                "argv_tail_matches_child",
                "both_exact_runner_target",
                "child_executable_differs",
                "narrowly_verified",
                "excluded_pid_only",
            ):
                if launcher.get(flag) is not True:
                    errors.append(f"verified Windows venv launcher {flag} proof is absent")

            launcher_identity = launcher.get("process_identity")
            errors.extend(
                _idle_retained_process_identity_validation_errors(
                    launcher_identity, "Windows venv launcher"
                )
            )
            launcher_argv = []
            launcher_executable = None
            if isinstance(launcher_identity, dict):
                launcher_argv = launcher_identity.get("command_line") or []
                launcher_executable = launcher_identity.get("executable")
                if launcher_identity.get("pid") != launcher_pid:
                    errors.append("verified Windows venv launcher retained PID is wrong")
                try:
                    if not math.isclose(
                        float(launcher_identity.get("process_create_time")),
                        float(launcher_created),
                        rel_tol=0.0,
                        abs_tol=0.001,
                    ):
                        errors.append(
                            "verified Windows venv launcher retained create time is wrong"
                        )
                except (TypeError, ValueError):
                    pass
                try:
                    retained_exe_matches = (
                        os.path.normcase(
                            str(Path(str(launcher_executable)).resolve())
                        )
                        == os.path.normcase(expected_launcher_path)
                    )
                except (OSError, RuntimeError, TypeError, ValueError):
                    retained_exe_matches = False
                if not retained_exe_matches:
                    errors.append(
                        "verified Windows venv launcher retained executable is wrong"
                    )
                if not _idle_command_line_has_exact_runner(launcher_argv):
                    errors.append(
                        "verified Windows venv launcher argv does not target this runner"
                    )
            if list(launcher_argv[1:]) != list(child_argv[1:]):
                errors.append("verified Windows venv launcher argv tail differs from child")
            try:
                child_executable_differs = (
                    os.path.normcase(str(Path(str(child_executable)).resolve()))
                    != os.path.normcase(expected_launcher_path)
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                child_executable_differs = False
            if not child_executable_differs:
                errors.append(
                    "verified Windows venv launcher child executable is not distinct"
                )
            try:
                observed_delta = float(created) - float(launcher_created)
                retained_delta = float(launcher.get("creation_delta_s"))
                if (
                    not math.isfinite(observed_delta)
                    or not math.isfinite(retained_delta)
                    or observed_delta < -0.001
                    or observed_delta > 5.0
                    or not math.isclose(
                        retained_delta,
                        round(observed_delta, 6),
                        rel_tol=0.0,
                        abs_tol=0.000001,
                    )
                ):
                    errors.append("verified Windows venv launcher creation delta is invalid")
            except (TypeError, ValueError):
                errors.append("verified Windows venv launcher creation delta is invalid")

    retained_count = exclusion.get("expected_excluded_process_count")
    if (
        not isinstance(retained_count, int)
        or isinstance(retained_count, bool)
        or retained_count != expected_count
    ):
        errors.append("current runner expected exclusion count is invalid")

    if excluded_current_runner is not None:
        if not isinstance(excluded_current_runner, list):
            errors.append("excluded current runner rows are not a list")
        else:
            expected_rows = {}
            rows_valid = True
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                expected_rows[pid] = (
                    float(created) if isinstance(created, (int, float)) else created,
                    "exact current run_recipe process",
                )
            else:
                rows_valid = False
            if (
                isinstance(launcher_pid, int)
                and not isinstance(launcher_pid, bool)
                and launcher_pid > 0
            ):
                expected_rows[launcher_pid] = (
                    float(launcher_created)
                    if isinstance(launcher_created, (int, float))
                    else launcher_created,
                    "exact verified direct Windows venv launcher stub",
                )
            observed_rows = {}
            rows_valid = rows_valid and len(excluded_current_runner) == expected_count
            for row in excluded_current_runner:
                if not isinstance(row, dict) or set(row) != set(
                    GPU_IDLE_EXCLUDED_CURRENT_RUNNER_ROW_SCHEMA
                ):
                    rows_valid = False
                    continue
                row_pid = row.get("pid")
                row_created = row.get("process_create_time")
                if (
                    not isinstance(row_pid, int)
                    or isinstance(row_pid, bool)
                    or row_pid <= 0
                    or not isinstance(row_created, (int, float))
                    or isinstance(row_created, bool)
                    or not math.isfinite(float(row_created))
                    or float(row_created) <= 0
                    or not isinstance(row.get("reason"), str)
                    or row_pid in observed_rows
                ):
                    rows_valid = False
                    continue
                observed_rows[row_pid] = (float(row_created), row.get("reason"))
            if set(observed_rows) != set(expected_rows):
                rows_valid = False
            else:
                for row_pid, (expected_created, expected_reason) in expected_rows.items():
                    observed_created, observed_reason = observed_rows[row_pid]
                    if (
                        not isinstance(expected_created, (int, float))
                        or not math.isclose(
                            observed_created,
                            float(expected_created),
                            rel_tol=0.0,
                            abs_tol=0.001,
                        )
                        or observed_reason != expected_reason
                    ):
                        rows_valid = False
            if not rows_valid:
                errors.append("excluded current runner rows are not exact")
    return errors


def _idle_current_runner_exclusion() -> Dict[str, Any]:
    """Prove the real runner and, when present, its one Windows venv stub."""

    pid = os.getpid()
    identity = _idle_process_identity(pid)
    create_time = identity.get("process_create_time")
    if (
        identity.get("exists") is not True
        or not isinstance(create_time, (int, float))
        or isinstance(create_time, bool)
        or not math.isfinite(float(create_time))
        or float(create_time) <= 0
        or not _idle_command_line_has_exact_runner(identity.get("command_line"))
    ):
        raise GpuIdleGateError(
            "Current run_recipe process cannot be narrowly identified for exclusion"
        )
    launcher = _idle_verified_current_windows_venv_launcher(identity)
    exclusion = {
        "pid": pid,
        "process_create_time": float(create_time),
        "resolved_runner_path": str(Path(__file__).resolve()),
        "narrowly_verified": True,
        "excluded_pid_only": True,
        "process_identity": identity,
        "verified_windows_venv_launcher": launcher,
        "expected_excluded_process_count": 2 if launcher is not None else 1,
    }
    validation_errors = current_runner_exclusion_validation_errors(exclusion)
    if validation_errors:
        raise GpuIdleGateError(
            "Current run_recipe exclusion evidence is invalid: "
            + "; ".join(validation_errors)
        )
    return exclusion


def _idle_desktop_graphics_signals(identity: Dict[str, Any]) -> List[str]:
    name = str(identity.get("name") or "").lower()
    executable = str(identity.get("executable") or "").lower()
    command_line = " ".join(
        str(value) for value in identity.get("command_line") or []
    ).lower()
    signals = []
    if "--type=gpu-process" in command_line:
        signals.append("chromium_or_electron_gpu_process")
    if "--video-capture-use-gpu-memory-buffer" in command_line:
        signals.append("desktop_video_capture_service")
    if "windows-mcp.exe" in command_line:
        signals.append("desktop_control_helper")
    if (
        name == "dwm.exe"
        and executable.replace("/", "\\").endswith("\\windows\\system32\\dwm.exe")
        and identity.get("process_create_time") is not None
    ):
        signals.append("windows_desktop_compositor")
    if "\\windows\\systemapps\\" in executable:
        signals.append("windows_system_ui")
    if "\\windowsapps\\" in executable and name not in {"python.exe", "pythonw.exe"}:
        signals.append("packaged_windows_ui")
    if name in {
        "explorer.exe",
        "shellhost.exe",
        "applicationframehost.exe",
        "systemsettings.exe",
        "snagiteditor.exe",
    }:
        signals.append("interactive_desktop_application")
    return sorted(set(signals))


def _workload_basename(value: Any) -> Optional[str]:
    text = str(value or "").replace("\\", "/").rstrip("/")
    return text.rsplit("/", 1)[-1].lower() if text else None


def _workload_is_python_basename(value: Optional[str]) -> bool:
    return bool(
        value
        and re.fullmatch(
            r"(?:python|pythonw|py)(?:\d+(?:\.\d+)*)?(?:\.exe)?", value
        )
    )


def _workload_python_target(argv: List[str]) -> Dict[str, Any]:
    """Parse only Python interpreter options and its actual script/module target."""

    if not argv:
        return {"kind": None, "identity": None, "basename": None}
    start = 1 if _workload_is_python_basename(_workload_basename(argv[0])) else 0
    index = start
    options_with_separate_value = {"-W", "-X", "--check-hash-based-pycs"}
    while index < len(argv):
        token = str(argv[index])
        lowered = token.lower()
        if token == "--":
            index += 1
            if index >= len(argv):
                break
            target = str(argv[index])
            return {
                "kind": "script",
                "identity": target.replace("\\", "/").lower(),
                "basename": _workload_basename(target),
            }
        if lowered == "-m":
            if index + 1 >= len(argv):
                break
            module = str(argv[index + 1]).lower()
            return {
                "kind": "module",
                "identity": module,
                "basename": module.rsplit(".", 1)[-1] or None,
            }
        if lowered == "-c" or lowered.startswith("-c") and len(lowered) > 2:
            return {"kind": "inline", "identity": None, "basename": None}
        if lowered == "-" or lowered in {"-h", "--help", "-v", "--version"}:
            return {"kind": "interpreter-only", "identity": None, "basename": None}
        if lowered.startswith("-"):
            if token in options_with_separate_value:
                index += 2
            else:
                index += 1
            continue
        return {
            "kind": "script",
            "identity": token.replace("\\", "/").lower(),
            "basename": _workload_basename(token),
        }
    return {"kind": None, "identity": None, "basename": None}


def _workload_argv_sha256(argv: Any) -> str:
    canonical_argv = [str(value) for value in (argv or [])]
    encoded = json.dumps(
        canonical_argv, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _redacted_workload_process(
    info: Dict[str, Any],
    target_basename: Optional[str],
    matched_markers: List[str],
    match_basis: List[str],
) -> Dict[str, Any]:
    try:
        created = float(info.get("create_time"))
        if not math.isfinite(created) or created <= 0:
            created = None
    except (TypeError, ValueError):
        created = None
    return {
        "pid": int(info.get("pid") or 0),
        "process_create_time": created,
        "process_basename": _workload_basename(info.get("name")),
        "executable_basename": _workload_basename(info.get("exe")),
        "target_basename": target_basename,
        "matched_markers": sorted(set(matched_markers)),
        "match_basis": sorted(set(match_basis)),
        "argv_sha256": _workload_argv_sha256(info.get("cmdline")),
    }


def classify_known_workload_process(info: Dict[str, Any]) -> Dict[str, Any]:
    """Shared token-aware positive classifier for cold and prequeue scans."""

    argv = [str(value) for value in info.get("cmdline") or []]
    process_basename = _workload_basename(info.get("name"))
    executable_basename = _workload_basename(info.get("exe"))
    argv0_basename = _workload_basename(argv[0]) if argv else None
    is_python = any(
        _workload_is_python_basename(value)
        for value in (process_basename, executable_basename, argv0_basename)
    )
    target = (
        _workload_python_target(argv)
        if is_python
        else {"kind": None, "identity": None, "basename": None}
    )
    matched = []
    bases = []
    if target.get("kind") == "script" and target.get("basename") in {
        "main.py",
        "run_recipe.py",
    }:
        matched.append(str(target["basename"]))
        bases.append("python_script_target")
    other_markers = [
        marker
        for marker in GPU_IDLE_MODEL_WORKLOAD_MARKERS
        if marker not in {"main.py", "run_recipe.py"}
    ]
    sources = (
        ("process_basename", process_basename),
        ("executable_basename", executable_basename),
        ("python_script_or_module_target", target.get("identity")),
    )
    for marker in other_markers:
        for basis, value in sources:
            if value and marker in str(value).lower():
                matched.append(marker)
                bases.append(basis)
    if matched:
        classification = "blocking_positive_known_workload"
    elif is_python:
        classification = "advisory_unreadable_or_unmatched_python"
        bases = ["advisory_python_without_positive_marker"]
    else:
        classification = "clear"
        bases = []
    return {
        "classification": classification,
        "redacted_process": _redacted_workload_process(
            info, target.get("basename"), matched, bases
        ),
    }


def redacted_workload_process_validation_errors(
    value: Any, expected_classification: str
) -> List[str]:
    """Validate one deterministic redacted blocker/advisory process row."""

    errors = []
    expected = set(known_workload_classifier_contract()["redacted_process_schema"])
    if not isinstance(value, dict) or set(value) != expected:
        return ["redacted process row shape is invalid"]
    pid = value.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        errors.append("redacted process PID is invalid")
    created = value.get("process_create_time")
    if created is not None and (
        not isinstance(created, (int, float))
        or isinstance(created, bool)
        or not math.isfinite(float(created))
        or float(created) <= 0
    ):
        errors.append("redacted process create time is invalid")
    for field in ("process_basename", "executable_basename", "target_basename"):
        scalar = value.get(field)
        if scalar is not None and (
            not isinstance(scalar, str)
            or not scalar
            or scalar != scalar.lower()
            or "/" in scalar
            or "\\" in scalar
        ):
            errors.append(f"redacted process {field} is invalid or leaks a path")
    markers = value.get("matched_markers")
    bases = value.get("match_basis")
    allowed_markers = set(GPU_IDLE_MODEL_WORKLOAD_MARKERS)
    allowed_positive_bases = {
        "python_script_target",
        "process_basename",
        "executable_basename",
        "python_script_or_module_target",
    }
    exclusion_bases = {
        "current_runner_exclusion_mismatch",
        "owned_server_exclusion_mismatch",
    }
    if (
        not isinstance(markers, list)
        or not all(isinstance(marker, str) for marker in markers)
        or (markers and markers != sorted(set(markers)))
        or (
            all(isinstance(marker, str) for marker in markers or [])
            and not set(markers or []).issubset(allowed_markers)
        )
    ):
        errors.append("redacted process markers are invalid")
    if (
        not isinstance(bases, list)
        or not all(isinstance(basis, str) for basis in bases)
        or (bases and bases != sorted(set(bases)))
    ):
        errors.append("redacted process match basis is invalid")
    elif expected_classification == "advisory" and isinstance(markers, list):
        if markers != [] or bases != ["advisory_python_without_positive_marker"]:
            errors.append("advisory process row contains positive blocking evidence")
    elif expected_classification == "blocking" and isinstance(markers, list):
        positive = (
            bool(markers)
            and bool(bases)
            and set(bases).issubset(allowed_positive_bases)
            and (
                not set(markers).intersection({"main.py", "run_recipe.py"})
                or "python_script_target" in bases
            )
        )
        exclusion = not markers and len(bases) == 1 and bases[0] in exclusion_bases
        if not (positive or exclusion):
            errors.append("blocking process row lacks positive or exclusion evidence")
    else:
        errors.append("redacted process expected classification is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", str(value.get("argv_sha256") or "")) is None:
        errors.append("redacted process argv SHA-256 is invalid")
    return errors


def _redacted_workload_process_is_valid(
    value: Any, expected_classification: str
) -> bool:
    return not redacted_workload_process_validation_errors(
        value, expected_classification
    )


def _redacted_exclusion_mismatch(
    info: Dict[str, Any], basis: str
) -> Dict[str, Any]:
    classified = classify_known_workload_process(info)["redacted_process"]
    classified["matched_markers"] = []
    classified["match_basis"] = [basis]
    return classified


def _idle_process_info_matches_verified_launcher(
    info: Dict[str, Any], current_runner_exclusion: Dict[str, Any]
) -> bool:
    if current_runner_exclusion_validation_errors(current_runner_exclusion):
        return False
    launcher = current_runner_exclusion.get("verified_windows_venv_launcher")
    if not isinstance(launcher, dict):
        return False
    retained = launcher.get("process_identity") or {}
    try:
        launcher_pid = int(launcher["pid"])
        launcher_created = float(launcher["process_create_time"])
        return (
            int(info.get("pid") or 0) == launcher_pid
            and math.isclose(
                float(info.get("create_time")),
                launcher_created,
                rel_tol=0.0,
                abs_tol=0.001,
            )
            and os.path.normcase(str(Path(str(info.get("exe"))).resolve()))
            == os.path.normcase(str(Path(launcher["expected_launcher_path"]).resolve()))
            and [str(value) for value in info.get("cmdline") or []]
            == [str(value) for value in retained.get("command_line") or []]
            and _idle_command_line_has_exact_runner(info.get("cmdline"))
            and psutil.Process(int(current_runner_exclusion["pid"])).ppid()
            == launcher_pid
            and lab_locks.process_identity_is_live(launcher_pid, launcher_created)
            and lab_locks.process_identity_is_live(
                int(current_runner_exclusion["pid"]),
                float(current_runner_exclusion["process_create_time"]),
            )
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        return False


def _idle_forbidden_process_scan(
    current_runner_exclusion: Dict[str, Any],
) -> Dict[str, Any]:
    exclusion_errors = current_runner_exclusion_validation_errors(
        current_runner_exclusion
    )
    if exclusion_errors:
        raise GpuIdleGateError(
            "Current runner exclusion cannot be used for process scan: "
            + "; ".join(exclusion_errors)
        )
    blockers = []
    advisories = []
    excluded = []
    scanned = 0
    try:
        iterator = psutil.process_iter(
            ["pid", "name", "exe", "cmdline", "create_time"], ad_value=None
        )
        for process in iterator:
            scanned += 1
            info = process.info
            pid = int(info["pid"])
            command_line = [str(value) for value in info.get("cmdline") or []]
            if pid == int(current_runner_exclusion["pid"]):
                observed_create_time = info.get("create_time")
                exact_current = (
                    isinstance(observed_create_time, (int, float))
                    and not isinstance(observed_create_time, bool)
                    and math.isclose(
                        float(observed_create_time),
                        float(current_runner_exclusion["process_create_time"]),
                        rel_tol=0.0,
                        abs_tol=0.001,
                    )
                    and _idle_command_line_has_exact_runner(command_line)
                )
                if exact_current:
                    excluded.append(
                        {
                            "pid": pid,
                            "process_create_time": float(observed_create_time),
                            "reason": "exact current run_recipe process",
                        }
                    )
                else:
                    blockers.append(
                        _redacted_exclusion_mismatch(
                            info, "current_runner_exclusion_mismatch"
                        )
                    )
                continue
            launcher = current_runner_exclusion.get("verified_windows_venv_launcher")
            if isinstance(launcher, dict) and pid == int(launcher.get("pid") or 0):
                if _idle_process_info_matches_verified_launcher(
                    info, current_runner_exclusion
                ):
                    excluded.append(
                        {
                            "pid": pid,
                            "process_create_time": float(info["create_time"]),
                            "reason": "exact verified direct Windows venv launcher stub",
                        }
                    )
                else:
                    blockers.append(
                        _redacted_exclusion_mismatch(
                            info, "current_runner_exclusion_mismatch"
                        )
                    )
                continue
            classified = classify_known_workload_process(info)
            if classified["classification"] == "blocking_positive_known_workload":
                blockers.append(classified["redacted_process"])
            elif classified["classification"] == "advisory_unreadable_or_unmatched_python":
                advisories.append(classified["redacted_process"])
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, ValueError) as exc:
        raise GpuIdleGateError(
            f"Independent process scan could not be completed: {exc}"
        ) from exc
    return {
        "scanned_process_count": scanned,
        "model_workload_markers": list(GPU_IDLE_MODEL_WORKLOAD_MARKERS),
        "classifier_contract": known_workload_classifier_contract(),
        "current_runner_exclusion": current_runner_exclusion,
        "excluded_current_runner": excluded,
        "blocking_processes": blockers,
        "advisory_unreadable_processes": advisories,
    }


def _prequeue_normalize_argv(argv: Any) -> List[str]:
    return [str(value).replace("\\", "/").lower() for value in (argv or [])]


def _prequeue_reported_server_argv_is_lab(server_argv: Any) -> bool:
    normalized = _prequeue_normalize_argv(server_argv)
    expected_main = str(COMFYUI_ROOT / "main.py").replace("\\", "/").lower()
    expected_output = str(REPO_ROOT / "outputs").replace("\\", "/").lower()
    try:
        return (
            len(normalized) >= 5
            and normalized[0] == expected_main
            and normalized.count("--port") == 1
            and normalized[normalized.index("--port") + 1] == str(LAB_PORT)
            and normalized.count("--output-directory") == 1
            and normalized[normalized.index("--output-directory") + 1]
            == expected_output
        )
    except (ValueError, IndexError):
        return False


def _prequeue_server_argv_match(
    actual_argv: Any, server_argv: Any, executable: Any
) -> Dict[str, Any]:
    actual = _prequeue_normalize_argv(actual_argv)
    reported = _prequeue_normalize_argv(server_argv)
    executable_normalized = _prequeue_normalize_argv([executable])
    mode = None
    if actual == reported:
        mode = "exact-self-reported-argv"
    elif (
        len(actual) == len(reported) + 1
        and actual[1:] == reported
        and executable_normalized
        and actual[0] == executable_normalized[0]
        and Path(actual[0]).name.lower() in {"python.exe", "pythonw.exe"}
    ):
        mode = "exact-self-reported-argv-plus-python-interpreter-prefix"
    return {
        "matches": mode is not None and _prequeue_reported_server_argv_is_lab(server_argv),
        "match_mode": mode,
        "actual_argv": list(actual_argv or []),
        "reported_server_argv": list(server_argv or []),
    }


def _prequeue_verified_owned_server_windows_venv_launcher(
    child_identity: Dict[str, Any], server_argv: List[str]
) -> Optional[Dict[str, Any]]:
    """Prove the serving process's one direct Windows venv launcher stub."""

    if os.name != "nt" or sys.prefix == sys.base_prefix:
        return None
    try:
        venv_prefix = Path(sys.prefix).resolve()
        expected_launcher = (venv_prefix / "Scripts" / "python.exe").resolve()
        if not (venv_prefix / "pyvenv.cfg").is_file():
            return None
        child_pid = int(child_identity["pid"])
        child_created = float(child_identity["process_create_time"])
        child_argv = [str(value) for value in child_identity.get("command_line") or []]
        child_exe = Path(str(child_identity.get("executable"))).resolve()
        launcher_pid = int(psutil.Process(child_pid).ppid())
        launcher_identity = _idle_process_identity(launcher_pid)
        launcher_created = float(launcher_identity["process_create_time"])
        launcher_argv = [
            str(value) for value in launcher_identity.get("command_line") or []
        ]
        launcher_exe = Path(str(launcher_identity.get("executable"))).resolve()
        direct_parent_verified = psutil.Process(child_pid).ppid() == launcher_pid
        launcher_live = lab_locks.process_identity_is_live(
            launcher_pid, launcher_created
        )
        child_live = lab_locks.process_identity_is_live(child_pid, child_created)
        child_argv_match = _prequeue_server_argv_match(
            child_argv, server_argv, child_identity.get("executable")
        )
        launcher_argv_match = _prequeue_server_argv_match(
            launcher_argv, server_argv, launcher_identity.get("executable")
        )
        exact = (
            launcher_identity.get("exists") is True
            and child_pid > 0
            and launcher_pid > 0
            and launcher_pid not in {child_pid, os.getpid()}
            and direct_parent_verified
            and os.path.normcase(str(launcher_exe))
            == os.path.normcase(str(expected_launcher))
            and os.path.normcase(str(child_exe))
            != os.path.normcase(str(expected_launcher))
            and len(launcher_argv) >= 2
            and len(child_argv) >= 2
            and launcher_argv[1:] == child_argv[1:]
            and child_argv_match["matches"] is True
            and launcher_argv_match["matches"] is True
            and launcher_live
            and child_live
            and launcher_created <= child_created + 0.001
            and child_created - launcher_created <= 5.0
        )
        if not exact:
            return None
        return {
            "pid": launcher_pid,
            "process_create_time": launcher_created,
            "expected_launcher_path": str(expected_launcher),
            "direct_child_pid": child_pid,
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_validated_server_argv": True,
            "child_executable_differs": True,
            "creation_delta_s": round(child_created - launcher_created, 6),
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": launcher_identity,
            "argv_match": launcher_argv_match,
        }
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        RuntimeError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        return None


def owned_lab_server_exclusion_validation_errors(
    exclusion: Any,
    expected_server_instance: Optional[Dict[str, Any]] = None,
    expected_server_argv: Optional[List[str]] = None,
    excluded_owned_lab_server: Optional[Any] = None,
) -> List[str]:
    """Validate retained serving-process and optional direct-launcher evidence."""

    errors = []
    if not isinstance(exclusion, dict) or set(exclusion) != set(
        PREQUEUE_OWNED_SERVER_EXCLUSION_SCHEMA
    ):
        return ["owned lab server exclusion shape is invalid"]
    pid = exclusion.get("pid")
    created = exclusion.get("process_create_time")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        errors.append("owned lab server exclusion PID is invalid")
    if (
        not isinstance(created, (int, float))
        or isinstance(created, bool)
        or not math.isfinite(float(created))
        or float(created) <= 0
    ):
        errors.append("owned lab server exclusion create time is invalid")
    if exclusion.get("narrowly_verified") is not True:
        errors.append("owned lab server exclusion narrow proof is absent")
    if exclusion.get("excluded_pid_only") is not True:
        errors.append("owned lab server exclusion is not PID-only")

    server_instance = exclusion.get("server_instance")
    try:
        valid_server_instance = (
            isinstance(server_instance, dict)
            and set(server_instance) == {"serving_pid", "process_create_time"}
            and int(server_instance.get("serving_pid") or 0) == pid
            and math.isclose(
                float(server_instance.get("process_create_time")),
                float(created),
                rel_tol=0.0,
                abs_tol=0.000001,
            )
        )
    except (TypeError, ValueError):
        valid_server_instance = False
    if not valid_server_instance:
        errors.append("owned lab server instance binding is invalid")
    if expected_server_instance is not None and server_instance != expected_server_instance:
        errors.append("owned lab server expected instance binding is wrong")

    child_identity = exclusion.get("process_identity")
    errors.extend(
        _idle_retained_process_identity_validation_errors(
            child_identity, "owned lab server"
        )
    )
    child_argv = []
    child_executable = None
    if isinstance(child_identity, dict):
        child_argv = child_identity.get("command_line") or []
        child_executable = child_identity.get("executable")
        if child_identity.get("pid") != pid:
            errors.append("owned lab server retained PID does not match")
        try:
            if not math.isclose(
                float(child_identity.get("process_create_time")),
                float(created),
                rel_tol=0.0,
                abs_tol=0.000001,
            ):
                errors.append("owned lab server retained create time does not match")
        except (TypeError, ValueError):
            pass

    retained_child_match = exclusion.get("argv_match")
    server_argv = (
        expected_server_argv
        if expected_server_argv is not None
        else (
            retained_child_match.get("reported_server_argv")
            if isinstance(retained_child_match, dict)
            else None
        )
    )
    if (
        not isinstance(server_argv, list)
        or not all(isinstance(token, str) for token in server_argv)
        or not _prequeue_reported_server_argv_is_lab(server_argv)
    ):
        errors.append("owned lab server reported argv binding is invalid")
        server_argv = []
    recomputed_child_match = _prequeue_server_argv_match(
        child_argv, server_argv, child_executable
    )
    if (
        retained_child_match != recomputed_child_match
        or recomputed_child_match.get("matches") is not True
    ):
        errors.append("owned lab server retained argv proof is invalid")

    launcher = exclusion.get("verified_windows_venv_launcher")
    expected_count = 1
    launcher_pid = None
    launcher_created = None
    if launcher is not None:
        expected_count = 2
        if not isinstance(launcher, dict) or set(launcher) != set(
            PREQUEUE_VERIFIED_SERVER_VENV_LAUNCHER_SCHEMA
        ):
            errors.append("owned-server Windows venv launcher shape is invalid")
        else:
            launcher_pid = launcher.get("pid")
            launcher_created = launcher.get("process_create_time")
            if (
                not isinstance(launcher_pid, int)
                or isinstance(launcher_pid, bool)
                or launcher_pid <= 0
                or launcher_pid == pid
            ):
                errors.append("owned-server Windows venv launcher PID is invalid")
            if (
                not isinstance(launcher_created, (int, float))
                or isinstance(launcher_created, bool)
                or not math.isfinite(float(launcher_created))
                or float(launcher_created) <= 0
            ):
                errors.append(
                    "owned-server Windows venv launcher create time is invalid"
                )
            if os.name != "nt" or sys.prefix == sys.base_prefix:
                errors.append(
                    "owned-server Windows venv launcher is outside a Windows venv"
                )
            expected_launcher_path = str(
                (Path(sys.prefix).resolve() / "Scripts" / "python.exe").resolve()
            )
            try:
                launcher_path_matches = (
                    os.path.normcase(
                        str(Path(str(launcher.get("expected_launcher_path"))).resolve())
                    )
                    == os.path.normcase(expected_launcher_path)
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                launcher_path_matches = False
            if not launcher_path_matches:
                errors.append("owned-server Windows venv launcher path is wrong")
            if launcher.get("direct_child_pid") != pid:
                errors.append("owned-server Windows venv launcher child PID is wrong")
            for flag in (
                "direct_parent_verified",
                "launcher_identity_live",
                "child_identity_live",
                "argv_tail_matches_child",
                "both_exact_validated_server_argv",
                "child_executable_differs",
                "narrowly_verified",
                "excluded_pid_only",
            ):
                if launcher.get(flag) is not True:
                    errors.append(
                        f"owned-server Windows venv launcher {flag} proof is absent"
                    )

            launcher_identity = launcher.get("process_identity")
            errors.extend(
                _idle_retained_process_identity_validation_errors(
                    launcher_identity, "owned-server Windows venv launcher"
                )
            )
            launcher_argv = []
            launcher_executable = None
            if isinstance(launcher_identity, dict):
                launcher_argv = launcher_identity.get("command_line") or []
                launcher_executable = launcher_identity.get("executable")
                if launcher_identity.get("pid") != launcher_pid:
                    errors.append(
                        "owned-server Windows venv launcher retained PID is wrong"
                    )
                try:
                    if not math.isclose(
                        float(launcher_identity.get("process_create_time")),
                        float(launcher_created),
                        rel_tol=0.0,
                        abs_tol=0.001,
                    ):
                        errors.append(
                            "owned-server Windows venv launcher retained create time is wrong"
                        )
                except (TypeError, ValueError):
                    pass
                try:
                    launcher_executable_matches = (
                        os.path.normcase(
                            str(Path(str(launcher_executable)).resolve())
                        )
                        == os.path.normcase(expected_launcher_path)
                    )
                except (OSError, RuntimeError, TypeError, ValueError):
                    launcher_executable_matches = False
                if not launcher_executable_matches:
                    errors.append(
                        "owned-server Windows venv launcher executable is wrong"
                    )
            if list(launcher_argv[1:]) != list(child_argv[1:]):
                errors.append(
                    "owned-server Windows venv launcher argv tail differs from child"
                )
            try:
                child_executable_differs = (
                    os.path.normcase(str(Path(str(child_executable)).resolve()))
                    != os.path.normcase(expected_launcher_path)
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                child_executable_differs = False
            if not child_executable_differs:
                errors.append(
                    "owned-server Windows venv launcher child executable is not distinct"
                )
            retained_launcher_match = launcher.get("argv_match")
            recomputed_launcher_match = _prequeue_server_argv_match(
                launcher_argv, server_argv, launcher_executable
            )
            if (
                retained_launcher_match != recomputed_launcher_match
                or recomputed_launcher_match.get("matches") is not True
            ):
                errors.append(
                    "owned-server Windows venv launcher argv proof is invalid"
                )
            try:
                observed_delta = float(created) - float(launcher_created)
                retained_delta = float(launcher.get("creation_delta_s"))
                if (
                    not math.isfinite(observed_delta)
                    or not math.isfinite(retained_delta)
                    or observed_delta < -0.001
                    or observed_delta > 5.0
                    or not math.isclose(
                        retained_delta,
                        round(observed_delta, 6),
                        rel_tol=0.0,
                        abs_tol=0.000001,
                    )
                ):
                    errors.append(
                        "owned-server Windows venv launcher creation delta is invalid"
                    )
            except (TypeError, ValueError):
                errors.append(
                    "owned-server Windows venv launcher creation delta is invalid"
                )

    retained_count = exclusion.get("expected_excluded_process_count")
    if (
        not isinstance(retained_count, int)
        or isinstance(retained_count, bool)
        or retained_count != expected_count
    ):
        errors.append("owned lab server expected exclusion count is invalid")

    if excluded_owned_lab_server is not None:
        if not isinstance(excluded_owned_lab_server, list):
            errors.append("excluded owned lab server rows are not a list")
        else:
            expected_rows = {}
            rows_valid = True
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                expected_rows[pid] = (
                    float(created) if isinstance(created, (int, float)) else created,
                    "exact owned port-8199 server PID/create-time/argv",
                )
            else:
                rows_valid = False
            if (
                isinstance(launcher_pid, int)
                and not isinstance(launcher_pid, bool)
                and launcher_pid > 0
            ):
                expected_rows[launcher_pid] = (
                    float(launcher_created)
                    if isinstance(launcher_created, (int, float))
                    else launcher_created,
                    "exact verified direct Windows venv owned-server launcher stub",
                )
            observed_rows = {}
            rows_valid = rows_valid and len(excluded_owned_lab_server) == expected_count
            for row in excluded_owned_lab_server:
                if not isinstance(row, dict) or set(row) != set(
                    PREQUEUE_EXCLUDED_OWNED_SERVER_ROW_SCHEMA
                ):
                    rows_valid = False
                    continue
                row_pid = row.get("pid")
                row_created = row.get("process_create_time")
                if (
                    not isinstance(row_pid, int)
                    or isinstance(row_pid, bool)
                    or row_pid <= 0
                    or not isinstance(row_created, (int, float))
                    or isinstance(row_created, bool)
                    or not math.isfinite(float(row_created))
                    or float(row_created) <= 0
                    or not isinstance(row.get("reason"), str)
                    or row_pid in observed_rows
                ):
                    rows_valid = False
                    continue
                observed_rows[row_pid] = (float(row_created), row.get("reason"))
            if set(observed_rows) != set(expected_rows):
                rows_valid = False
            else:
                for row_pid, (expected_created, expected_reason) in expected_rows.items():
                    observed_created, observed_reason = observed_rows[row_pid]
                    if (
                        not isinstance(expected_created, (int, float))
                        or not math.isclose(
                            observed_created,
                            float(expected_created),
                            rel_tol=0.0,
                            abs_tol=0.001,
                        )
                        or observed_reason != expected_reason
                    ):
                        rows_valid = False
            if not rows_valid:
                errors.append("excluded owned lab server rows are not exact")
    return errors


def _prequeue_owned_server_exclusion(
    server_instance: Dict[str, Any], server_argv: List[str]
) -> Dict[str, Any]:
    try:
        exact_shape = set(server_instance) == {"serving_pid", "process_create_time"}
        pid = int(server_instance["serving_pid"])
        expected_created = float(server_instance["process_create_time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PreflightError(
            2, "GPU idle", f"Owned server identity is malformed before prompt: {exc}"
        ) from exc
    if (
        not exact_shape
        or pid <= 0
        or not math.isfinite(expected_created)
        or expected_created <= 0
        or pid == os.getpid()
    ):
        raise PreflightError(
            2, "GPU idle", "Owned server identity is invalid before prompt"
        )
    identity = _idle_process_identity(pid)
    try:
        observed_created = float(identity.get("process_create_time"))
    except (TypeError, ValueError) as exc:
        raise PreflightError(
            2, "GPU idle", "Owned server process create time is unavailable before prompt"
        ) from exc
    argv_match = _prequeue_server_argv_match(
        identity.get("command_line"), server_argv, identity.get("executable")
    )
    if (
        identity.get("exists") is not True
        or not math.isfinite(observed_created)
        or not math.isclose(
            observed_created, expected_created, rel_tol=0.0, abs_tol=0.000001
        )
        or argv_match["matches"] is not True
    ):
        raise PreflightError(
            2,
            "GPU idle",
            "Owned server PID/create-time/argv could not be re-proved before prompt",
        )
    launcher = _prequeue_verified_owned_server_windows_venv_launcher(
        identity, server_argv
    )
    exclusion = {
        "pid": pid,
        "process_create_time": observed_created,
        "server_instance": copy.deepcopy(server_instance),
        "process_identity": identity,
        "argv_match": argv_match,
        "narrowly_verified": True,
        "excluded_pid_only": True,
        "verified_windows_venv_launcher": launcher,
        "expected_excluded_process_count": 2 if launcher is not None else 1,
    }
    validation_errors = owned_lab_server_exclusion_validation_errors(
        exclusion, server_instance, server_argv
    )
    if validation_errors:
        raise PreflightError(
            2,
            "GPU idle",
            "Owned server exclusion evidence is invalid: "
            + "; ".join(validation_errors),
        )
    return exclusion


def _prequeue_process_info_matches_server_exclusion(
    info: Dict[str, Any], exclusion: Dict[str, Any]
) -> bool:
    if owned_lab_server_exclusion_validation_errors(exclusion):
        return False
    identity = exclusion.get("process_identity") or {}
    try:
        return (
            int(info.get("pid") or 0) == int(exclusion.get("pid") or -1)
            and math.isclose(
                float(info.get("create_time")),
                float(exclusion.get("process_create_time")),
                rel_tol=0.0,
                abs_tol=0.000001,
            )
            and _prequeue_normalize_argv(info.get("cmdline"))
            == _prequeue_normalize_argv(identity.get("command_line"))
            and _prequeue_normalize_argv([info.get("exe")])
            == _prequeue_normalize_argv([identity.get("executable")])
        )
    except (TypeError, ValueError):
        return False


def _prequeue_process_info_matches_server_launcher(
    info: Dict[str, Any], exclusion: Dict[str, Any]
) -> bool:
    if owned_lab_server_exclusion_validation_errors(exclusion):
        return False
    launcher = exclusion.get("verified_windows_venv_launcher")
    if not isinstance(launcher, dict):
        return False
    retained = launcher.get("process_identity") or {}
    try:
        launcher_pid = int(launcher["pid"])
        launcher_created = float(launcher["process_create_time"])
        child_pid = int(exclusion["pid"])
        child_created = float(exclusion["process_create_time"])
        return (
            int(info.get("pid") or 0) == launcher_pid
            and math.isclose(
                float(info.get("create_time")),
                launcher_created,
                rel_tol=0.0,
                abs_tol=0.001,
            )
            and os.path.normcase(str(Path(str(info.get("exe"))).resolve()))
            == os.path.normcase(
                str(Path(str(launcher["expected_launcher_path"])).resolve())
            )
            and [str(value) for value in info.get("cmdline") or []]
            == [str(value) for value in retained.get("command_line") or []]
            and psutil.Process(child_pid).ppid() == launcher_pid
            and lab_locks.process_identity_is_live(launcher_pid, launcher_created)
            and lab_locks.process_identity_is_live(child_pid, child_created)
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        RuntimeError,
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):
        return False


def prequeue_known_workload_scan_validation_errors(
    evidence: Dict[str, Any],
    expected_server_instance: Optional[Dict[str, Any]] = None,
    expected_server_argv: Optional[List[str]] = None,
) -> List[str]:
    """Validate the immutable receipt-facing per-leg prequeue scan evidence."""

    errors = []
    expected_keys = {
        "schema_version",
        "kind",
        "status",
        "scan_ran",
        "sampled_at_ns",
        "sampled_at_utc",
        "completed_at_ns",
        "contract",
        "server_instance",
        "server_argv",
        "listener_pid_before",
        "listener_pid_after",
        "current_runner_exclusion",
        "owned_lab_server_exclusion",
        "scanned_process_count",
        "excluded_current_runner",
        "excluded_owned_lab_server",
        "blocking_processes",
        "advisory_unreadable_processes",
        "scan_errors",
        "evidence_sha256",
    }
    if set(evidence) != expected_keys:
        errors.append("prequeue workload scan contains missing/extra fields")
    if evidence.get("schema_version") != 1:
        errors.append("prequeue workload scan schema_version is not 1")
    if evidence.get("kind") != "per-leg-immediate-prequeue-known-workload-scan":
        errors.append("prequeue workload scan kind is wrong")
    if (
        evidence.get("status") != "clean"
        or evidence.get("scan_ran") is not True
        or evidence.get("blocking_processes") != []
        or evidence.get("scan_errors") != []
    ):
        errors.append("prequeue workload scan is not clean")
    advisories = evidence.get("advisory_unreadable_processes")
    if not isinstance(advisories, list) or not all(
        _redacted_workload_process_is_valid(value, "advisory")
        for value in advisories
    ):
        errors.append("prequeue workload advisory evidence is malformed")
    retained_hash = evidence.get("evidence_sha256")
    unhashed = copy.deepcopy(evidence)
    unhashed.pop("evidence_sha256", None)
    if retained_hash != stable_identity(unhashed):
        errors.append("prequeue workload scan evidence SHA-256 is invalid")
    if evidence.get("contract") != prequeue_known_workload_scan_contract():
        errors.append("prequeue workload scan contract drifted")
    server_instance = evidence.get("server_instance")
    if expected_server_instance is not None and server_instance != expected_server_instance:
        errors.append("prequeue workload scan server instance binding is wrong")
    server_argv = evidence.get("server_argv")
    if expected_server_argv is not None and server_argv != expected_server_argv:
        errors.append("prequeue workload scan server argv binding is wrong")
    try:
        serving_pid = int((server_instance or {}).get("serving_pid") or 0)
    except (TypeError, ValueError):
        serving_pid = 0
    if (
        serving_pid <= 0
        or evidence.get("listener_pid_before") != serving_pid
        or evidence.get("listener_pid_after") != serving_pid
    ):
        errors.append("prequeue workload scan listener binding is wrong")
    current = evidence.get("current_runner_exclusion") or {}
    server = evidence.get("owned_lab_server_exclusion") or {}
    excluded_current = evidence.get("excluded_current_runner") or []
    excluded_server = evidence.get("excluded_owned_lab_server") or []
    if current_runner_exclusion_validation_errors(current, excluded_current):
        errors.append("prequeue workload scan current runner exclusion is not exact")
    if owned_lab_server_exclusion_validation_errors(
        server, server_instance, server_argv, excluded_server
    ):
        errors.append("prequeue workload scan owned server exclusion is not exact")
    if isinstance(excluded_current, list) and isinstance(excluded_server, list):
        current_pids = {
            row.get("pid") for row in excluded_current if isinstance(row, dict)
        }
        server_pids = {
            row.get("pid") for row in excluded_server if isinstance(row, dict)
        }
        if current_pids.intersection(server_pids):
            errors.append("prequeue workload scan exclusion PID sets overlap")
    try:
        expected_current_count = int(
            current.get("expected_excluded_process_count") or 0
        )
        expected_server_count = int(
            server.get("expected_excluded_process_count") or 0
        )
        if int(evidence.get("scanned_process_count") or 0) < (
            expected_current_count + expected_server_count
        ):
            errors.append("prequeue workload scan did not enumerate all exclusions")
        sampled_at_ns = int(evidence.get("sampled_at_ns") or 0)
        completed_at_ns = int(evidence.get("completed_at_ns") or 0)
        if sampled_at_ns <= 0 or completed_at_ns < sampled_at_ns:
            errors.append("prequeue workload scan timestamps are invalid")
    except (TypeError, ValueError):
        errors.append("prequeue workload scan numeric evidence is malformed")
    return errors


def collect_prequeue_known_workload_scan(
    server_instance: Dict[str, Any], server_argv: List[str]
) -> Dict[str, Any]:
    """Scan every process immediately before every cold/warm prompt queue."""

    sampled_at_ns = time.time_ns()
    current_exclusion = _idle_current_runner_exclusion()
    server_exclusion = _prequeue_owned_server_exclusion(server_instance, server_argv)
    serving_pid = int(server_exclusion["pid"])
    try:
        listener_before = listener_pid(int(LAB_PORT), strict=True)
    except Exception as exc:
        raise PreflightError(
            2, "GPU idle", f"Could not re-prove port {LAB_PORT} before prompt: {exc}"
        ) from exc
    if listener_before != serving_pid:
        raise PreflightError(
            2, "GPU idle", "Owned server is no longer the port-8199 listener before prompt"
        )

    blockers = []
    advisories = []
    excluded_current = []
    excluded_server = []
    scan_errors = []
    scanned = 0
    try:
        iterator = psutil.process_iter(
            ["pid", "name", "exe", "cmdline", "create_time"], ad_value=None
        )
        for process in iterator:
            scanned += 1
            info = process.info
            pid = int(info["pid"])
            name = str(info.get("name") or "")
            executable = str(info.get("exe") or "")
            command_line = [str(value) for value in info.get("cmdline") or []]
            if pid == int(current_exclusion["pid"]):
                try:
                    exact_current = (
                        math.isclose(
                            float(info.get("create_time")),
                            float(current_exclusion["process_create_time"]),
                            rel_tol=0.0,
                            abs_tol=0.001,
                        )
                        and _idle_command_line_has_exact_runner(command_line)
                    )
                except (TypeError, ValueError):
                    exact_current = False
                if exact_current:
                    excluded_current.append(
                        {
                            "pid": pid,
                            "process_create_time": float(info["create_time"]),
                            "reason": "exact current run_recipe process",
                        }
                    )
                else:
                    blockers.append(
                        _redacted_exclusion_mismatch(
                            info, "current_runner_exclusion_mismatch"
                        )
                    )
                continue
            launcher = current_exclusion.get("verified_windows_venv_launcher")
            if isinstance(launcher, dict) and pid == int(launcher.get("pid") or 0):
                if _idle_process_info_matches_verified_launcher(info, current_exclusion):
                    excluded_current.append(
                        {
                            "pid": pid,
                            "process_create_time": float(info["create_time"]),
                            "reason": "exact verified direct Windows venv launcher stub",
                        }
                    )
                else:
                    blockers.append(
                        _redacted_exclusion_mismatch(
                            info, "current_runner_exclusion_mismatch"
                        )
                    )
                continue
            if pid == serving_pid:
                if _prequeue_process_info_matches_server_exclusion(
                    info, server_exclusion
                ):
                    excluded_server.append(
                        {
                            "pid": pid,
                            "process_create_time": float(info["create_time"]),
                            "reason": (
                                "exact owned port-8199 server PID/create-time/argv"
                            ),
                        }
                    )
                else:
                    blockers.append(
                        _redacted_exclusion_mismatch(
                            info, "owned_server_exclusion_mismatch"
                        )
                    )
                continue
            server_launcher = server_exclusion.get(
                "verified_windows_venv_launcher"
            )
            if (
                isinstance(server_launcher, dict)
                and pid == int(server_launcher.get("pid") or 0)
            ):
                if _prequeue_process_info_matches_server_launcher(
                    info, server_exclusion
                ):
                    excluded_server.append(
                        {
                            "pid": pid,
                            "process_create_time": float(info["create_time"]),
                            "reason": (
                                "exact verified direct Windows venv owned-server "
                                "launcher stub"
                            ),
                        }
                    )
                else:
                    blockers.append(
                        _redacted_exclusion_mismatch(
                            info, "owned_server_exclusion_mismatch"
                        )
                    )
                continue
            classified = classify_known_workload_process(info)
            if classified["classification"] == "blocking_positive_known_workload":
                blockers.append(classified["redacted_process"])
            elif classified["classification"] == "advisory_unreadable_or_unmatched_python":
                advisories.append(classified["redacted_process"])
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, ValueError) as exc:
        scan_errors.append(f"process enumeration failed: {type(exc).__name__}: {exc}")

    current_exclusion_errors = current_runner_exclusion_validation_errors(
        current_exclusion, excluded_current
    )
    if current_exclusion_errors:
        scan_errors.append(
            "current run_recipe/verified-launcher exclusions were not observed exactly"
        )
    server_exclusion_errors = owned_lab_server_exclusion_validation_errors(
        server_exclusion, server_instance, server_argv, excluded_server
    )
    if server_exclusion_errors:
        scan_errors.append(
            "owned lab server/verified-launcher exclusions were not observed exactly"
        )
    try:
        listener_after = listener_pid(int(LAB_PORT), strict=True)
    except Exception as exc:
        listener_after = None
        scan_errors.append(f"post-scan listener proof failed: {type(exc).__name__}: {exc}")
    if listener_after != serving_pid:
        scan_errors.append("owned server is no longer the port-8199 listener after scan")

    evidence = {
        "schema_version": 1,
        "kind": "per-leg-immediate-prequeue-known-workload-scan",
        "status": "clean" if not blockers and not scan_errors else "blocked",
        "scan_ran": True,
        "sampled_at_ns": sampled_at_ns,
        "sampled_at_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(sampled_at_ns / 1e9)
        ),
        "completed_at_ns": time.time_ns(),
        "contract": prequeue_known_workload_scan_contract(),
        "server_instance": copy.deepcopy(server_instance),
        "server_argv": list(server_argv),
        "listener_pid_before": listener_before,
        "listener_pid_after": listener_after,
        "current_runner_exclusion": current_exclusion,
        "owned_lab_server_exclusion": server_exclusion,
        "scanned_process_count": scanned,
        "excluded_current_runner": excluded_current,
        "excluded_owned_lab_server": excluded_server,
        "blocking_processes": blockers,
        "advisory_unreadable_processes": advisories,
        "scan_errors": scan_errors,
    }
    evidence["evidence_sha256"] = stable_identity(evidence)
    if blockers or scan_errors:
        raise PreflightError(
            2,
            "GPU idle",
            "Immediate prequeue known-workload scan blocked: "
            "redacted_blocking_processes="
            + json.dumps(blockers, sort_keys=True, separators=(",", ":"))
            + "; scan_errors="
            + json.dumps(scan_errors, sort_keys=True, separators=(",", ":")),
        )
    validation_errors = prequeue_known_workload_scan_validation_errors(
        evidence, server_instance, server_argv
    )
    if validation_errors:
        raise PreflightError(
            2,
            "GPU idle",
            "Immediate prequeue scan evidence is invalid: "
            + "; ".join(validation_errors),
        )
    return evidence


def _idle_classify_process_row(
    row: Dict[str, Any], expected_uuid: str, identity: Dict[str, Any]
) -> Dict[str, Any]:
    desktop_signals = _idle_desktop_graphics_signals(identity)
    evidence = {
        **row,
        "process_identity": identity,
        "desktop_graphics_signals": desktop_signals,
        "desktop_signal_status": (
            "recognized" if desktop_signals else "unrecognized-non-workload-client"
        ),
        "blocking_reasons": [],
        "classification": "blocked",
    }
    reasons: List[str] = evidence["blocking_reasons"]
    if row.get("gpu_uuid") != expected_uuid:
        reasons.append("process row is not bound to the selected GPU UUID")
    token = str(row.get("used_gpu_memory_token") or "")
    if token != GPU_IDLE_WDDM_UNMETERED_MEMORY_TOKEN:
        try:
            numeric = float(token)
        except ValueError:
            reasons.append(f"unknown per-process memory token {token!r}")
        else:
            reasons.append(f"numeric per-process GPU allocation reported ({numeric} MiB)")
    if identity.get("exists") is not True:
        reasons.append("NVIDIA process PID cannot be re-identified")
    create_time = identity.get("process_create_time")
    if (
        not isinstance(create_time, (int, float))
        or isinstance(create_time, bool)
        or not math.isfinite(float(create_time))
        or float(create_time) <= 0
    ):
        reasons.append("NVIDIA process create time is unavailable")
    workload = classify_known_workload_process(
        {
            "pid": row.get("pid"),
            "name": identity.get("name") or row.get("nvidia_process_name"),
            "exe": identity.get("executable"),
            "cmdline": identity.get("command_line"),
            "create_time": identity.get("process_create_time"),
        }
    )
    evidence["known_workload_classification"] = workload
    if workload["classification"] == "blocking_positive_known_workload":
        reasons.append(
            "positive known workload marker(s): "
            f"{workload['redacted_process']['matched_markers']}"
        )
    if not reasons:
        evidence["classification"] = "allowed_unmetered_wddm_desktop_client"
    return evidence


def _idle_query_process_evidence(
    gpu_index: int, expected_uuid: str
) -> Dict[str, Any]:
    argv = [
        "nvidia-smi",
        "-i",
        str(gpu_index),
        "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ]
    result = _idle_run_nvidia_smi(argv)
    parsed = []
    for fields in _idle_csv_rows(result.stdout):
        if len(fields) != 4 or not fields[1].isdigit():
            parsed.append(
                {
                    "raw_fields": fields,
                    "classification": "blocked",
                    "blocking_reasons": ["malformed NVIDIA process row"],
                }
            )
            continue
        gpu_uuid, pid_text, process_name, memory = fields
        row = {
            "gpu_uuid": gpu_uuid,
            "pid": int(pid_text),
            "nvidia_process_name": process_name,
            "used_gpu_memory_token": memory,
        }
        parsed.append(
            _idle_classify_process_row(
                row, expected_uuid, _idle_process_identity(int(pid_text))
            )
        )
    blockers = [
        {
            "pid": row.get("pid"),
            "blocking_reasons": row.get("blocking_reasons") or [],
        }
        for row in parsed
        if row.get("classification") != "allowed_unmetered_wddm_desktop_client"
    ]
    return {
        "target_gpu_index": int(gpu_index),
        "target_gpu_uuid": expected_uuid,
        "query_argv": argv,
        "raw_stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
        "row_count": len(parsed),
        "rows": parsed,
        "blocking_rows": blockers,
    }


def _idle_same_lock_owner(
    left: Dict[str, Any], right: Dict[str, Any]
) -> bool:
    try:
        return (
            int(left.get("lock_schema_version") or 0)
            == int(right.get("lock_schema_version") or 0)
            and int(left.get("pid") or 0) == int(right.get("pid") or 0)
            and math.isclose(
                float(left.get("process_create_time") or 0.0),
                float(right.get("process_create_time") or 0.0),
                rel_tol=0.0,
                abs_tol=0.001,
            )
            and str(left.get("nonce") or "") == str(right.get("nonce") or "")
            and str(left.get("role") or "") == str(right.get("role") or "")
        )
    except (TypeError, ValueError):
        return False


def _idle_lock_evidence(
    expected_owner: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        before = LOCKFILE_PATH.lstat()
        if (
            _is_symlink_or_reparse_point(LOCKFILE_PATH)
            or not stat.S_ISREG(before.st_mode)
            or int(before.st_nlink) != 1
        ):
            raise GpuIdleGateError(
                "GPU lock receipt is not an exact single-link regular file"
            )
        raw = LOCKFILE_PATH.read_bytes()
        receipt = lab_locks.read_lock_receipt(LOCKFILE_PATH)
        retained = LOCKFILE_PATH.read_bytes()
        after = LOCKFILE_PATH.lstat()
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns")
        if raw != retained or any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            raise GpuIdleGateError("GPU lock receipt changed while it was sampled")
    except GpuIdleGateError:
        raise
    except (OSError, lab_locks.LeaseError) as exc:
        raise GpuIdleGateError(f"GPU lock receipt cannot be verified: {exc}") from exc
    role = str(receipt.get("role") or "")
    authorized = False
    authorization = "unproved"
    if role == "standalone":
        try:
            current_created = float(psutil.Process(os.getpid()).create_time())
            authorized = int(receipt.get("pid") or 0) == os.getpid() and math.isclose(
                float(receipt.get("process_create_time") or 0.0),
                current_created,
                rel_tol=0.0,
                abs_tol=0.001,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
            authorized = False
        authorization = "current standalone owner"
    elif role == "suite":
        receipt_pid = int(receipt.get("pid") or 0)
        receipt_created = float(receipt.get("process_create_time") or 0.0)
        if receipt_pid == os.getpid():
            authorized = lab_locks.process_identity_is_live(
                receipt_pid, receipt_created
            )
            authorization = "current suite owner"
        else:
            try:
                owner_pid = int(os.environ[lab_locks.SUITE_OWNER_PID_ENV])
                owner_created = float(
                    os.environ[lab_locks.SUITE_OWNER_CREATE_TIME_ENV]
                )
                owner_nonce = os.environ[lab_locks.SUITE_NONCE_ENV]
                receipt_matches_environment = (
                    receipt_pid == owner_pid
                    and math.isclose(
                        receipt_created,
                        owner_created,
                        rel_tol=0.0,
                        abs_tol=0.001,
                    )
                    and str(receipt.get("nonce") or "") == owner_nonce
                )
                direct_child = os.getppid() == owner_pid
                launcher_chain = lab_locks._is_verified_windows_venv_launcher_chain(
                    owner_pid, owner_created
                )
                authorized = bool(
                    receipt_matches_environment
                    and lab_locks.process_identity_is_live(owner_pid, owner_created)
                    and (direct_child or launcher_chain)
                )
            except (KeyError, TypeError, ValueError):
                authorized = False
            authorization = "nonce-bound suite child"
    expected_owner_matches = (
        expected_owner is None or _idle_same_lock_owner(receipt, expected_owner)
    )
    authorized = authorized and expected_owner_matches
    return {
        "path": str(LOCKFILE_PATH.resolve()),
        "receipt": receipt,
        "receipt_sha256": sha256_bytes(raw),
        "authorization": authorization,
        "matches_expected_owner": expected_owner_matches,
        "matches_acquired_owner": authorized,
    }


def _idle_listener_evidence(port: int = int(LAB_PORT)) -> Dict[str, Any]:
    rows = []
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError) as exc:
        raise GpuIdleGateError(
            f"Could not enumerate listener ownership for port {port}: {exc}"
        ) from exc
    for connection in connections:
        local = connection.laddr
        local_port = (
            getattr(local, "port", local[1] if len(local) > 1 else None)
            if local
            else None
        )
        if connection.status != psutil.CONN_LISTEN or local_port != port:
            continue
        rows.append(
            {
                "pid": connection.pid,
                "local_address": str(local),
                "owner_known": connection.pid is not None,
            }
        )
    return {
        "port": port,
        "listeners": rows,
        "listener_pids": sorted(
            {int(row["pid"]) for row in rows if row["pid"] is not None}
        ),
        "unknown_owner_count": sum(1 for row in rows if row["pid"] is None),
    }


def _idle_evaluate_sample(
    activity: Dict[str, Any],
    process_evidence: Dict[str, Any],
    lock_evidence: Dict[str, Any],
    listener_evidence: Dict[str, Any],
    forbidden_processes: Dict[str, Any],
) -> List[str]:
    errors = []
    if activity.get("driver_model_current") != GPU_IDLE_REQUIRED_DRIVER_MODEL:
        errors.append("selected GPU is not in exact WDDM driver mode")
    try:
        used_vram_mib = float(activity["vram_used_mib"])
    except (KeyError, TypeError, ValueError):
        errors.append("selected GPU used VRAM is not numeric")
    else:
        if not math.isfinite(used_vram_mib) or used_vram_mib < 0:
            errors.append("selected GPU used VRAM is invalid")
        elif used_vram_mib > float(GPU_IDLE_BASELINE_MAX_MB):
            errors.append(
                "selected GPU absolute baseline exceeds 3072 MiB"
            )
    if process_evidence.get("target_gpu_uuid") != activity.get("gpu_uuid"):
        errors.append("NVIDIA process evidence is not bound to the sampled GPU UUID")
    if process_evidence.get("blocking_rows"):
        errors.append(
            f"NVIDIA process evidence has "
            f"{len(process_evidence['blocking_rows'])} blocking row(s)"
        )
    if listener_evidence.get("listeners"):
        errors.append(f"port {LAB_PORT} listener(s) appeared")
    if listener_evidence.get("unknown_owner_count"):
        errors.append(f"port {LAB_PORT} listener ownership is incomplete")
    if lock_evidence.get("matches_acquired_owner") is not True:
        errors.append("GPU lock receipt no longer matches the acquired owner")
    if current_runner_exclusion_validation_errors(
        forbidden_processes.get("current_runner_exclusion"),
        forbidden_processes.get("excluded_current_runner"),
    ):
        errors.append("current run_recipe/verified-launcher exclusion proof is wrong")
    if forbidden_processes.get("blocking_processes"):
        errors.append(
            "independent process scan found %s forbidden/unknown workload(s)"
            % len(forbidden_processes["blocking_processes"])
        )
    return errors


def _idle_finalize_evidence(
    evidence: Dict[str, Any], server_instance: Dict[str, Any]
) -> Dict[str, Any]:
    finalized = copy.deepcopy(evidence)
    finalized["server_instance"] = copy.deepcopy(server_instance)
    finalized.pop("evidence_sha256", None)
    finalized["evidence_sha256"] = stable_identity(finalized)
    return finalized


def _idle_owned_server_reuse_evidence(
    server_instance: Dict[str, Any]
) -> Dict[str, Any]:
    evidence = {
        "schema_version": 1,
        "kind": "run-recipe-preboot-wddm-idle-gate",
        "status": "not-rerun-owned-server-reuse",
        "gate_ran": False,
        "reason": (
            "verified owned lab server already active; no fresh idle sampling claimed"
        ),
        "contract": gpu_idle_gate_contract(),
    }
    return _idle_finalize_evidence(evidence, server_instance)


def gpu_idle_gate_validation_errors(
    evidence: Dict[str, Any],
    expected_server_instance: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Independently recompute the receipt-facing idle-gate assertions."""

    errors = []
    if evidence.get("schema_version") != 1:
        errors.append("idle gate schema_version is not 1")
    if evidence.get("kind") != "run-recipe-preboot-wddm-idle-gate":
        errors.append("idle gate kind is wrong")
    retained_hash = evidence.get("evidence_sha256")
    unhashed = copy.deepcopy(evidence)
    unhashed.pop("evidence_sha256", None)
    if retained_hash != stable_identity(unhashed):
        errors.append("idle gate evidence SHA-256 is invalid")
    if evidence.get("contract") != gpu_idle_gate_contract():
        errors.append("idle gate contract drifted")
    server_instance = evidence.get("server_instance")
    if not isinstance(server_instance, dict):
        errors.append("idle gate server instance is absent")
    else:
        try:
            valid_server_instance = (
                set(server_instance) == {"serving_pid", "process_create_time"}
                and int(server_instance.get("serving_pid") or 0) > 0
                and math.isfinite(float(server_instance.get("process_create_time")))
                and float(server_instance.get("process_create_time")) > 0
            )
        except (TypeError, ValueError):
            valid_server_instance = False
        if not valid_server_instance:
            errors.append("idle gate server instance shape/values are invalid")
        if (
            expected_server_instance is not None
            and server_instance != expected_server_instance
        ):
            errors.append("idle gate server instance binding is wrong")

    status = evidence.get("status")
    if status == "not-rerun-owned-server-reuse":
        expected_reuse_keys = {
            "schema_version",
            "kind",
            "status",
            "gate_ran",
            "reason",
            "contract",
            "server_instance",
            "evidence_sha256",
        }
        if evidence.get("gate_ran") is not False:
            errors.append("owned-server reuse marker claims the idle gate ran")
        if evidence.get("reason") != (
            "verified owned lab server already active; no fresh idle sampling claimed"
        ):
            errors.append("owned-server reuse reason is not exact")
        if set(evidence) != expected_reuse_keys:
            errors.append("owned-server reuse marker contains missing/extra fields")
        return errors
    if status != "measured" or evidence.get("gate_ran") is not True:
        errors.append("cold idle gate is not measured")
        return errors

    expected_cold_keys = {
        "schema_version",
        "kind",
        "status",
        "gate_ran",
        "gpu_index",
        "target_gpu",
        "sample_count",
        "sampling_interval_s",
        "aggregation",
        "policy",
        "contract",
        "port_8199_listener_pids_before",
        "port_8199_listener_pids_after",
        "current_runner_exclusion",
        "gpu_lock_owner",
        "samples",
        "summary",
        "collector",
        "server_instance",
        "evidence_sha256",
    }
    if set(evidence) != expected_cold_keys:
        errors.append("cold idle gate contains missing/extra fields")

    target = evidence.get("target_gpu") or {}
    samples = evidence.get("samples") or []
    contract = evidence.get("contract") or {}
    if evidence.get("aggregation") != contract.get("aggregation"):
        errors.append("cold idle gate aggregation drifted from its contract")
    if evidence.get("policy") != contract.get("policy"):
        errors.append("cold idle gate policy drifted from its contract")
    if evidence.get("collector") != contract.get("collector"):
        errors.append("cold idle gate collector drifted from its contract")
    if int(evidence.get("gpu_index", -1)) != GPU_IDLE_INDEX:
        errors.append("cold idle gate GPU index is wrong")
    if (
        not str(target.get("gpu_uuid") or "").startswith("GPU-")
        or target.get("gpu_index") != GPU_IDLE_INDEX
    ):
        errors.append("cold idle gate target GPU binding is invalid")
    if target.get("driver_model_current") != GPU_IDLE_REQUIRED_DRIVER_MODEL:
        errors.append("cold idle gate target GPU is not WDDM")
    if target.get("display_active") not in GPU_IDLE_DISPLAY_ACTIVE_MEASURED_STATES:
        errors.append("cold idle gate target display measured state is invalid")
    if (
        evidence.get("sample_count") != GPU_IDLE_SAMPLE_COUNT
        or len(samples) != GPU_IDLE_SAMPLE_COUNT
    ):
        errors.append("cold idle gate does not retain exactly five samples")
    if evidence.get("sampling_interval_s") != GPU_IDLE_SAMPLE_INTERVAL_S:
        errors.append("cold idle gate sampling interval is not 200 ms")
    if evidence.get("port_8199_listener_pids_before") != []:
        errors.append("port 8199 was occupied before the idle gate")
    if evidence.get("port_8199_listener_pids_after") != []:
        errors.append("port 8199 was occupied after the idle gate")
    exclusion = evidence.get("current_runner_exclusion") or {}
    if current_runner_exclusion_validation_errors(exclusion):
        errors.append("current runner exclusion is not narrowly bound")
    gpu_lock_owner = evidence.get("gpu_lock_owner") or {}
    try:
        valid_lock_owner = (
            int(gpu_lock_owner.get("lock_schema_version") or 0)
            == lab_locks.LOCK_SCHEMA_VERSION
            and int(gpu_lock_owner.get("pid") or 0) > 0
            and float(gpu_lock_owner.get("process_create_time") or 0.0) > 0
            and len(str(gpu_lock_owner.get("nonce") or "")) >= 32
            and str(gpu_lock_owner.get("role") or "") in {"standalone", "suite"}
        )
    except (TypeError, ValueError):
        valid_lock_owner = False
    if not valid_lock_owner:
        errors.append("cold idle gate GPU lock owner is invalid")

    uuid_value = target.get("gpu_uuid")
    for index, sample in enumerate(samples):
        prefix = f"sample {index}"
        if sample.get("sample_index") != index:
            errors.append(f"{prefix} index is wrong")
        if (
            sample.get("gpu_index") != GPU_IDLE_INDEX
            or sample.get("gpu_uuid") != uuid_value
        ):
            errors.append(f"{prefix} target GPU binding is wrong")
        if sample.get("driver_model_current") != GPU_IDLE_REQUIRED_DRIVER_MODEL:
            errors.append(f"{prefix} is not WDDM")
        if sample.get("display_active") not in GPU_IDLE_DISPLAY_ACTIVE_MEASURED_STATES:
            errors.append(f"{prefix} display measured state is invalid")
        try:
            vram = float(sample["vram_used_mib"])
            gpu_util = float(sample["gpu_utilization_percent"])
            memory_util = float(sample["memory_utilization_percent"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{prefix} activity is malformed")
            continue
        if (
            not all(math.isfinite(value) for value in (vram, gpu_util, memory_util))
            or min(vram, gpu_util, memory_util) < 0
            or gpu_util > 100
            or memory_util > 100
        ):
            errors.append(f"{prefix} activity is non-finite/out of range")
        if math.isfinite(vram) and vram > float(GPU_IDLE_BASELINE_MAX_MB):
            errors.append(f"{prefix} exceeds the 3072 MiB absolute baseline gate")
        if sample.get("quiescent") is not True or sample.get("quiescence_errors") != []:
            errors.append(f"{prefix} is not classified quiescent")
        listeners = sample.get("port_8199_listener_evidence") or {}
        if (
            listeners.get("port") != int(LAB_PORT)
            or listeners.get("listeners") != []
            or listeners.get("listener_pids") != []
            or listeners.get("unknown_owner_count") != 0
        ):
            errors.append(f"{prefix} observed an occupied/unowned port 8199")
        lock = sample.get("gpu_lock") or {}
        if lock.get("matches_acquired_owner") is not True:
            errors.append(f"{prefix} does not prove the GPU lease")
        if lock.get("matches_expected_owner") is not True:
            errors.append(f"{prefix} does not match the captured GPU lease owner")
        if not _idle_same_lock_owner(lock.get("receipt") or {}, gpu_lock_owner):
            errors.append(f"{prefix} GPU lease owner/nonce drifted")
        processes = sample.get("nvidia_process_evidence") or {}
        if (
            processes.get("target_gpu_index") != GPU_IDLE_INDEX
            or processes.get("target_gpu_uuid") != uuid_value
            or processes.get("blocking_rows") != []
        ):
            errors.append(f"{prefix} NVIDIA process evidence is not clean/bound")
        rows = processes.get("rows") or []
        if processes.get("row_count") != len(rows):
            errors.append(f"{prefix} NVIDIA process row count is inconsistent")
        for row in rows:
            identity = row.get("process_identity") or {}
            recomputed = _idle_classify_process_row(
                {
                    "gpu_uuid": row.get("gpu_uuid"),
                    "pid": row.get("pid"),
                    "nvidia_process_name": row.get("nvidia_process_name"),
                    "used_gpu_memory_token": row.get("used_gpu_memory_token"),
                },
                str(uuid_value),
                identity,
            )
            if (
                row.get("classification")
                != "allowed_unmetered_wddm_desktop_client"
                or row.get("blocking_reasons") != []
                or row.get("used_gpu_memory_token")
                != GPU_IDLE_WDDM_UNMETERED_MEMORY_TOKEN
                or row.get("classification") != recomputed.get("classification")
                or row.get("blocking_reasons")
                != recomputed.get("blocking_reasons")
                or row.get("desktop_graphics_signals")
                != recomputed.get("desktop_graphics_signals")
                or row.get("desktop_signal_status")
                != recomputed.get("desktop_signal_status")
                or row.get("known_workload_classification")
                != recomputed.get("known_workload_classification")
            ):
                errors.append(f"{prefix} contains an unqualified NVIDIA process row")
        forbidden = sample.get("forbidden_process_scan") or {}
        expected_forbidden_keys = {
            "scanned_process_count",
            "model_workload_markers",
            "classifier_contract",
            "current_runner_exclusion",
            "excluded_current_runner",
            "blocking_processes",
            "advisory_unreadable_processes",
        }
        if set(forbidden) != expected_forbidden_keys:
            errors.append(f"{prefix} independent process scan shape is invalid")
        if forbidden.get("blocking_processes") != []:
            errors.append(f"{prefix} independent process scan is not clean")
        if forbidden.get("classifier_contract") != known_workload_classifier_contract():
            errors.append(f"{prefix} independent process classifier contract drifted")
        blockers = forbidden.get("blocking_processes")
        advisories = forbidden.get("advisory_unreadable_processes")
        if not isinstance(blockers, list) or not all(
            _redacted_workload_process_is_valid(value, "blocking")
            for value in blockers
        ):
            errors.append(f"{prefix} independent process blockers are malformed")
        if not isinstance(advisories, list) or not all(
            _redacted_workload_process_is_valid(value, "advisory")
            for value in advisories
        ):
            errors.append(f"{prefix} independent process advisories are malformed")
        if int(forbidden.get("scanned_process_count") or 0) <= 0:
            errors.append(f"{prefix} independent process scan retained no evidence")
        if forbidden.get("current_runner_exclusion") != exclusion:
            errors.append(f"{prefix} current runner exclusion binding drifted")
        excluded = forbidden.get("excluded_current_runner") or []
        if current_runner_exclusion_validation_errors(exclusion, excluded):
            errors.append(f"{prefix} current runner exclusion is not exact")

    if samples:
        summary = evidence.get("summary") or {}
        try:
            expected_summary = {
                "max_vram_used_mib": max(
                    float(row["vram_used_mib"]) for row in samples
                ),
                "max_gpu_utilization_percent": max(
                    float(row["gpu_utilization_percent"]) for row in samples
                ),
                "max_memory_utilization_percent": max(
                    float(row["memory_utilization_percent"]) for row in samples
                ),
            }
            if summary != expected_summary:
                errors.append("cold idle gate summary was not recomputed")
        except (KeyError, TypeError, ValueError):
            errors.append("cold idle gate summary inputs are malformed")
    return errors


class ServerIdleGateSidecarError(RuntimeError):
    """Raised when the owned-server idle-gate sidecar cannot be proved."""


def _server_idle_gate_bytes(evidence: Dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                evidence,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ServerIdleGateSidecarError(
            f"idle-gate evidence is not canonical JSON: {exc}"
        ) from exc


def _server_idle_gate_stat_identity(value: os.stat_result) -> Tuple[int, ...]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_mode),
        int(value.st_nlink),
        int(value.st_size),
        int(value.st_mtime_ns),
    )


def snapshot_server_idle_gate_sidecar(
    expected_server_instance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Stably read and independently validate the immutable cold-gate sidecar."""

    path = SERVER_IDLE_GATE_FILE
    if not os.path.lexists(path):
        raise ServerIdleGateSidecarError("server idle-gate sidecar is absent")
    try:
        before = path.lstat()
        if (
            _is_symlink_or_reparse_point(path)
            or not stat.S_ISREG(before.st_mode)
            or int(before.st_nlink) != 1
        ):
            raise ServerIdleGateSidecarError(
                "server idle-gate sidecar is not an exact single-link regular file"
            )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(str(path), flags)
        try:
            descriptor_before = os.fstat(fd)
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            descriptor_after = os.fstat(fd)
        finally:
            os.close(fd)
        after = path.lstat()
    except ServerIdleGateSidecarError:
        raise
    except OSError as exc:
        raise ServerIdleGateSidecarError(
            f"cannot snapshot server idle-gate sidecar: {exc}"
        ) from exc

    identity = _server_idle_gate_stat_identity(before)
    if (
        identity != _server_idle_gate_stat_identity(descriptor_before)
        or identity != _server_idle_gate_stat_identity(descriptor_after)
        or identity != _server_idle_gate_stat_identity(after)
        or _is_symlink_or_reparse_point(path)
        or not stat.S_ISREG(after.st_mode)
        or int(after.st_nlink) != 1
        or len(raw) != int(after.st_size)
    ):
        raise ServerIdleGateSidecarError(
            "server idle-gate sidecar changed while it was read"
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ServerIdleGateSidecarError("server idle-gate sidecar contains a UTF-8 BOM")
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServerIdleGateSidecarError(
            f"server idle-gate sidecar is invalid JSON: {exc}"
        ) from exc
    if not isinstance(evidence, dict):
        raise ServerIdleGateSidecarError(
            "server idle-gate sidecar is not a JSON object"
        )
    if raw != _server_idle_gate_bytes(evidence):
        raise ServerIdleGateSidecarError(
            "server idle-gate sidecar bytes are not canonical"
        )
    errors = gpu_idle_gate_validation_errors(evidence, expected_server_instance)
    if evidence.get("status") != "measured" or evidence.get("gate_ran") is not True:
        errors.append("server idle-gate sidecar does not contain a measured cold gate")
    if errors:
        raise ServerIdleGateSidecarError("; ".join(errors))
    metadata = {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "identity": list(identity),
        "evidence_sha256": evidence["evidence_sha256"],
        "server_instance": copy.deepcopy(evidence["server_instance"]),
    }
    return {
        "evidence": evidence,
        "metadata": metadata,
        "raw": raw,
    }


def create_server_idle_gate_sidecar(
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """O_EXCL-create and re-prove the cold gate bound to the new server."""

    errors = gpu_idle_gate_validation_errors(
        evidence, evidence.get("server_instance") if isinstance(evidence, dict) else None
    )
    if evidence.get("status") != "measured" or evidence.get("gate_ran") is not True:
        errors.append("only measured cold idle evidence may create the sidecar")
    if errors:
        raise ServerIdleGateSidecarError(
            "refusing invalid server idle-gate sidecar evidence: " + "; ".join(errors)
        )
    content = _server_idle_gate_bytes(evidence)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(SERVER_IDLE_GATE_FILE), flags, 0o600)
        try:
            offset = 0
            while offset < len(content):
                written = os.write(fd, content[offset:])
                if written <= 0:
                    raise OSError("short write for server idle-gate sidecar")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ServerIdleGateSidecarError(
            f"cannot exclusively create server idle-gate sidecar: {exc}"
        ) from exc
    retained = snapshot_server_idle_gate_sidecar(evidence["server_instance"])
    if retained["evidence"] != evidence or retained["raw"] != content:
        raise ServerIdleGateSidecarError(
            "server idle-gate sidecar changed after exclusive creation"
        )
    return retained


def _remove_server_idle_gate_sidecar_after_proved_exit(
    pid: int, original: Dict[str, Any]
) -> Tuple[bool, str]:
    """Remove only the exact cold-gate sidecar after PID and port are clear."""

    try:
        current = snapshot_server_idle_gate_sidecar(
            original.get("metadata", {}).get("server_instance")
        )
    except ServerIdleGateSidecarError as exc:
        return False, f"server idle-gate sidecar drifted: {exc}"
    if (
        current.get("metadata") != original.get("metadata")
        or current.get("raw") != original.get("raw")
    ):
        return False, "server idle-gate sidecar identity/content drifted before removal"
    if psutil.pid_exists(pid):
        return False, f"recorded PID {pid} became live before sidecar removal"
    try:
        serving_pid = listener_pid(int(LAB_PORT), strict=True)
        live_stats = query_server_stats()
    except Exception as exc:
        return False, f"could not re-prove clear port {LAB_PORT}: {exc}"
    if serving_pid is not None or live_stats is not None:
        return False, f"port {LAB_PORT} became live before sidecar removal"
    try:
        SERVER_IDLE_GATE_FILE.unlink()
    except OSError as exc:
        return False, f"could not remove server idle-gate sidecar: {exc}"
    if os.path.lexists(SERVER_IDLE_GATE_FILE):
        return False, "server idle-gate sidecar path was replaced during removal"
    return True, ""


def _snapshot_server_idle_gate_sidecar_for_cleanup(
    pid: int,
    expected_process_create_time: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Seal the sidecar, when present, and prove that it belongs to ``pid``."""

    if not os.path.lexists(SERVER_IDLE_GATE_FILE):
        return None
    snapshot = snapshot_server_idle_gate_sidecar()
    server_instance = snapshot.get("metadata", {}).get("server_instance")
    if not isinstance(server_instance, dict) or set(server_instance) != {
        "serving_pid",
        "process_create_time",
    }:
        raise ServerIdleGateSidecarError(
            "server idle-gate sidecar has an invalid server_instance shape"
        )
    try:
        serving_pid = int(server_instance["serving_pid"])
        create_time = float(server_instance["process_create_time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ServerIdleGateSidecarError(
            f"server idle-gate sidecar has an invalid server identity: {exc}"
        ) from exc
    if serving_pid != int(pid):
        raise ServerIdleGateSidecarError(
            f"server idle-gate sidecar PID {serving_pid} does not match receipt PID {pid}"
        )
    if (
        not math.isfinite(create_time)
        or create_time <= 0
        or (
            expected_process_create_time is not None
            and create_time != round(float(expected_process_create_time), 6)
        )
    ):
        raise ServerIdleGateSidecarError(
            "server idle-gate sidecar process creation time does not match the owned PID"
        )
    return snapshot


def check_gpu_idle(
    expected_gpu_lock_owner: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Preflight Check #2: prove five conjunctively idle WDDM samples."""

    try:
        contract = gpu_idle_gate_contract()
        runner_exclusion = _idle_current_runner_exclusion()
        retained_gpu_lock_owner = copy.deepcopy(expected_gpu_lock_owner)
        listeners_before = _idle_listener_evidence()
        if listeners_before["listeners"]:
            raise GpuIdleGateError(
                f"Port {LAB_PORT} already has listener evidence: "
                f"{listeners_before['listeners']}"
            )
        target = _idle_target_gpu_identity(GPU_IDLE_INDEX)
        samples = []
        all_errors = []
        redacted_blockers: Dict[str, Dict[str, Any]] = {}
        for index in range(GPU_IDLE_SAMPLE_COUNT):
            sampled_ns = time.time_ns()
            activity = _idle_query_gpu_activity(
                GPU_IDLE_INDEX, str(target["gpu_uuid"])
            )
            processes = _idle_query_process_evidence(
                GPU_IDLE_INDEX, str(target["gpu_uuid"])
            )
            lock = _idle_lock_evidence(retained_gpu_lock_owner)
            if retained_gpu_lock_owner is None:
                retained_gpu_lock_owner = copy.deepcopy(lock.get("receipt"))
            if not isinstance(retained_gpu_lock_owner, dict):
                raise GpuIdleGateError("GPU lock owner snapshot is missing")
            listeners = _idle_listener_evidence()
            forbidden = _idle_forbidden_process_scan(runner_exclusion)
            for blocker in forbidden.get("blocking_processes") or []:
                redacted_blockers[stable_identity(blocker)] = blocker
            errors = _idle_evaluate_sample(
                activity, processes, lock, listeners, forbidden
            )
            host = psutil.virtual_memory()
            samples.append(
                {
                    "sample_index": index,
                    "sampled_at_ns": sampled_ns,
                    "sampled_at_utc": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(sampled_ns / 1e9)
                    ),
                    "sampled_monotonic_ns": time.monotonic_ns(),
                    **activity,
                    "host_ram_used_bytes": int(host.used),
                    "host_ram_total_bytes": int(host.total),
                    "port_8199_listener_evidence": listeners,
                    "gpu_lock": lock,
                    "nvidia_process_evidence": processes,
                    "forbidden_process_scan": forbidden,
                    "quiescence_errors": errors,
                    "quiescent": not errors,
                }
            )
            all_errors.extend(f"sample {index}: {error}" for error in errors)
            if index != GPU_IDLE_SAMPLE_COUNT - 1:
                time.sleep(GPU_IDLE_SAMPLE_INTERVAL_S)
        listeners_after = _idle_listener_evidence()
        if listeners_after["listeners"]:
            all_errors.append(
                f"post-sample port {LAB_PORT} listener(s): "
                f"{listeners_after['listeners']}"
            )
        if all_errors:
            raise GpuIdleGateError(
                "GPU is not quiescent: "
                + "; ".join(all_errors)
                + "; redacted_blocking_processes="
                + json.dumps(
                    [redacted_blockers[key] for key in sorted(redacted_blockers)],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        return {
            "schema_version": 1,
            "kind": "run-recipe-preboot-wddm-idle-gate",
            "status": "measured",
            "gate_ran": True,
            "gpu_index": GPU_IDLE_INDEX,
            "target_gpu": target,
            "sample_count": len(samples),
            "sampling_interval_s": GPU_IDLE_SAMPLE_INTERVAL_S,
            "aggregation": contract["aggregation"],
            "policy": contract["policy"],
            "contract": contract,
            "port_8199_listener_pids_before": listeners_before["listener_pids"],
            "port_8199_listener_pids_after": listeners_after["listener_pids"],
            "current_runner_exclusion": runner_exclusion,
            "gpu_lock_owner": retained_gpu_lock_owner,
            "samples": samples,
            "summary": {
                "max_vram_used_mib": max(
                    float(row["vram_used_mib"]) for row in samples
                ),
                "max_gpu_utilization_percent": max(
                    float(row["gpu_utilization_percent"]) for row in samples
                ),
                "max_memory_utilization_percent": max(
                    float(row["memory_utilization_percent"]) for row in samples
                ),
            },
            "collector": contract["collector"],
        }
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError(
            2,
            "GPU idle",
            f"Five-sample WDDM idle gate failed: {type(exc).__name__}: {exc}",
        ) from exc


def query_server_stats() -> Optional[Dict[str, Any]]:
    """Query GET /system_stats at 127.0.0.1:8199."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        pass
    return None


def query_queue_state() -> Dict[str, Any]:
    """Return ComfyUI's running/pending queue state from the owned lab port."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/queue")
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PreflightError(3, "Queue idle", f"Could not verify the lab queue: {exc}") from exc
    if not isinstance(payload, dict):
        raise PreflightError(3, "Queue idle", "Lab /queue response is not a JSON object")
    return payload


def write_queue_quarantine(reason: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Persist a fail-closed marker when orphan work or cleanup is uncertain."""
    payload = {
        "quarantine_schema_version": 1,
        "reason": reason,
        "details": details or {},
        "pid": os.getpid(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = QUEUE_QUARANTINE_PATH.with_name(
        f".{QUEUE_QUARANTINE_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, QUEUE_QUARANTINE_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_queue_idle() -> Dict[str, Any]:
    """Fail closed if any prior prompt is running/pending or quarantine exists."""
    if QUEUE_QUARANTINE_PATH.exists():
        raise PreflightError(
            3,
            "Queue idle",
            f"Durable queue quarantine is present: {QUEUE_QUARANTINE_PATH.name}",
        )
    state = query_queue_state()
    running = state.get("queue_running")
    pending = state.get("queue_pending")
    if not isinstance(running, list) or not isinstance(pending, list):
        raise PreflightError(3, "Queue idle", "Lab /queue omitted running/pending lists")
    if running or pending:
        write_queue_quarantine(
            "orphan-or-foreign ComfyUI queue work detected before prompt",
            {
                "queue_running_count": len(running),
                "queue_pending_count": len(pending),
                "listener_pid": listener_pid(int(LAB_PORT)),
            },
        )
        raise PreflightError(
            3,
            "Queue idle",
            f"Lab queue is not empty (running={len(running)}, pending={len(pending)}); quarantined",
        )
    return state


def listener_pid(port: int, *, strict: bool = False) -> Optional[int]:
    """Return the PID listening on a port, optionally failing on unknown state."""
    try:
        for connection in psutil.net_connections(kind="inet"):
            local = connection.laddr
            local_port = getattr(local, "port", local[1] if len(local) > 1 else None) if local else None
            if connection.status == psutil.CONN_LISTEN and local_port == port:
                if strict and connection.pid is None:
                    raise RuntimeError(
                        f"listener on port {port} exists but its PID is unavailable"
                    )
                return connection.pid
    except (psutil.AccessDenied, OSError) as exc:
        if strict:
            raise RuntimeError(
                f"could not enumerate listener ownership for port {port}: {exc}"
            ) from exc
        return None
    return None


def verified_server_instance() -> Dict[str, Any]:
    """Return the owned listener identity so a reboot resets warm-cache state."""
    recorded_pid = get_recorded_pid()
    serving_pid = listener_pid(int(LAB_PORT))
    if not recorded_pid or serving_pid != recorded_pid or not is_expected_lab_server_pid(recorded_pid):
        raise PreflightError(
            3,
            "Server identity",
            "Could not prove that the recorded lab PID is the active port-8199 listener",
        )
    try:
        create_time = psutil.Process(recorded_pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise PreflightError(3, "Server identity", f"Could not read lab process create time: {exc}") from exc
    return {
        "serving_pid": recorded_pid,
        "process_create_time": round(float(create_time), 6),
    }


def is_expected_lab_server_pid(pid: int) -> bool:
    """Verify that a PID is the configured ComfyUI lab process, not just live."""
    try:
        argv = psutil.Process(pid).cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    normalized = [str(arg).replace("\\", "/").lower() for arg in argv]
    expected_main = str(COMFYUI_ROOT / "main.py").replace("\\", "/").lower()
    expected_output = str(REPO_ROOT / "outputs").replace("\\", "/").lower()
    try:
        port_index = normalized.index("--port")
        output_index = normalized.index("--output-directory")
        return (
            expected_main in normalized
            and normalized[port_index + 1] == str(LAB_PORT)
            and normalized[output_index + 1] == expected_output
        )
    except (ValueError, IndexError):
        return False


def terminate_owned_process_tree(pid: int) -> bool:
    """Terminate a recorded process tree and report whether every captured PID exited."""
    if not pid or not psutil.pid_exists(pid):
        return True
    processes = []
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        processes = children + [parent]
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
        _, alive = psutil.wait_procs(processes, timeout=10)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=5)
        return not alive
    except (psutil.NoSuchProcess, psutil.TimeoutExpired, OSError):
        return not psutil.pid_exists(pid)


def boot_lab_server(recipe_name: Optional[str] = None) -> Dict[str, Any]:
    """Boot lab server headlessly via boot_lab_server.cmd and wait for health-check."""
    manager_probe = manager_probe_requested()
    if manager_probe and recipe_name is None:
        raise PreflightError(
            3, "Server up", "Manager probe boot requires a closed recipe scope"
        )
    active_boot_cmd = MANAGER_PROBE_BOOT_CMD if manager_probe else BOOT_CMD
    if not active_boot_cmd.exists():
        raise PreflightError(3, "Server up", f"Lab boot command missing: {active_boot_cmd}")

    active_server_log = (
        manager_probe_log_path(recipe_name) if manager_probe else SERVER_LOG_FILE
    )
    if manager_probe and not active_server_log.parent.is_dir():
        raise PreflightError(
            3,
            "Server up",
            f"Manager probe log directory is absent: {active_server_log.parent}",
        )
    if manager_probe and active_server_log.exists():
        raise PreflightError(
            3,
            "Server up",
            f"Manager probe requires an attempt-unique absent log: {active_server_log}",
        )
    cleanup_stale_pid_receipt()
    if os.path.lexists(SERVER_PID_FILE):
        raise PreflightError(
            3,
            "Server up",
            "An existing .server.pid receipt could not be proved stale; refusing to overwrite it",
        )
    if os.path.lexists(SERVER_IDLE_GATE_FILE):
        raise PreflightError(
            2,
            "GPU idle",
            "An orphan .server.idle-gate.json exists before boot; refusing to overwrite it",
        )
    if manager_probe:
        initialize_manager_probe_log(active_server_log)
    print(f"[SERVER] Launching lab server via {active_boot_cmd.name} on port {LAB_PORT}...")
    
    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(
        ["cmd.exe", "/c", str(active_boot_cmd)],
        cwd=str(REPO_ROOT),
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    
    SERVER_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"[SERVER] Recorded server PID {proc.pid} in .server.pid")

    try:
        start = time.time()
        while time.time() - start < BOOT_TIMEOUT_S:
            stats = query_server_stats()
            if stats:
                launched_pids = {proc.pid}
                try:
                    launched_pids.update(child.pid for child in psutil.Process(proc.pid).children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
                serving_pid = listener_pid(int(LAB_PORT))
                if serving_pid is None:
                    raise PreflightError(3, "Server up", f"Could not prove ownership of the listener on port {LAB_PORT}")
                if serving_pid not in launched_pids or not is_expected_lab_server_pid(serving_pid):
                    raise PreflightError(
                        3,
                        "Server up",
                        f"Port {LAB_PORT} was claimed by PID {serving_pid}, outside the process tree this runner launched",
                    )
                SERVER_PID_FILE.write_text(str(serving_pid), encoding="utf-8")
                print(f"[SERVER] Updated .server.pid to serving PID {serving_pid}")
                print(f"[SERVER] Lab server online on port {LAB_PORT} after {time.time()-start:.1f}s")
                return stats
            time.sleep(3.0)

        log_tail = ""
        if active_server_log.exists():
            try:
                log_lines = active_server_log.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                log_tail = "\n".join(log_lines[-15:])
            except Exception as e:
                log_tail = f"(Could not read {active_server_log}: {e})"

        raise PreflightError(3, "Server up", f"Lab server failed to boot on port {LAB_PORT} within 120s.\nTail of server.log:\n{log_tail}")
    except Exception:
        terminated = terminate_owned_process_tree(proc.pid)
        if terminated and not os.path.lexists(SERVER_IDLE_GATE_FILE) and SERVER_PID_FILE.exists():
            SERVER_PID_FILE.unlink(missing_ok=True)
        elif terminated and os.path.lexists(SERVER_IDLE_GATE_FILE):
            print(
                "[SERVER] Boot cleanup found an unexpected idle-gate sidecar; "
                "preserving it and .server.pid for manual inspection."
            )
        elif not terminated:
            print(
                f"[SERVER] Boot cleanup could not prove PID {proc.pid} exited; "
                "keeping .server.pid for manual inspection."
            )
        raise


def check_server_up_and_ownership(
    recipe_name: Optional[str] = None,
    expected_gpu_lock_owner: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Verify ownership first; check desktop VRAM only before booting a new server."""
    cleanup_stale_pid_receipt()
    stats = query_server_stats()
    pid_receipt = get_recorded_pid()

    if stats:
        serving_pid = listener_pid(int(LAB_PORT))
        if (
            pid_receipt
            and serving_pid == pid_receipt
            and is_expected_lab_server_pid(pid_receipt)
        ):
            ensure_queue_idle()
            server_instance = verified_server_instance()
            try:
                sidecar = snapshot_server_idle_gate_sidecar(server_instance)
            except ServerIdleGateSidecarError as exc:
                raise PreflightError(
                    2,
                    "GPU idle",
                    "Owned lab server has no valid persisted cold idle gate: "
                    f"{exc}",
                ) from exc
            retained = dict(stats)
            retained[GPU_IDLE_INTERNAL_STATS_KEY] = (
                _idle_owned_server_reuse_evidence(server_instance)
            )
            retained[GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY] = sidecar["metadata"]
            return retained
        else:
            raise PreflightError(
                3, "Server up",
                f"Unrecognized server already answering on port {LAB_PORT} without valid PID receipt. Refusing to adopt or kill it."
            )

    if pid_receipt or os.path.lexists(SERVER_PID_FILE):
        raise PreflightError(
            3,
            "Server up",
            f"A PID receipt ({pid_receipt or 'unverifiable'}) exists but no verified lab server answers on port {LAB_PORT}. Refusing to overwrite the receipt.",
        )
    if os.path.lexists(SERVER_IDLE_GATE_FILE):
        raise PreflightError(
            2,
            "GPU idle",
            "Orphan .server.idle-gate.json exists without an owned lab server; "
            "manual inspection is required",
        )

    idle_evidence = check_gpu_idle(expected_gpu_lock_owner)
    print("  [OK] Check 2: Five-sample WDDM idle gate passed")
    stats = boot_lab_server(recipe_name)
    try:
        server_instance = verified_server_instance()
        finalized = _idle_finalize_evidence(idle_evidence, server_instance)
        errors = gpu_idle_gate_validation_errors(finalized, server_instance)
        if errors:
            raise ServerIdleGateSidecarError("; ".join(errors))
        sidecar = create_server_idle_gate_sidecar(finalized)
        ensure_queue_idle()
        retained = dict(stats)
        retained[GPU_IDLE_INTERNAL_STATS_KEY] = finalized
        retained[GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY] = sidecar["metadata"]
        return retained
    except Exception as exc:
        cleanup = shutdown_lab_server()
        raise PreflightError(
            2,
            "GPU idle",
            "Could not bind the measured idle gate to the booted lab server: "
            f"{type(exc).__name__}: {exc}; cleanup={cleanup}",
        ) from exc


class ServerPidReceiptError(RuntimeError):
    """Raised when the exact owned-server PID receipt cannot be re-proved."""


def _snapshot_server_pid_receipt(
    expected_pid: Optional[int] = None,
) -> Dict[str, Any]:
    """Read one stable regular PID receipt without following a reparse point."""

    path = SERVER_PID_FILE
    if not os.path.lexists(path):
        raise ServerPidReceiptError("PID receipt is absent")
    try:
        before = path.lstat()
        if _is_symlink_or_reparse_point(path) or not stat.S_ISREG(before.st_mode):
            raise ServerPidReceiptError(
                "PID receipt is not an exact regular non-reparse file"
            )
        if int(before.st_nlink) != 1:
            raise ServerPidReceiptError("PID receipt must have exactly one hardlink")

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(str(path), flags)
        try:
            descriptor_before = os.fstat(fd)
            chunks = []
            while True:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            descriptor_after = os.fstat(fd)
        finally:
            os.close(fd)
        after = path.lstat()
    except ServerPidReceiptError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ServerPidReceiptError(f"cannot snapshot PID receipt: {exc}") from exc

    def identity(value: os.stat_result) -> Tuple[int, int, int, int, int, int]:
        return (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_mode),
            int(value.st_nlink),
            int(value.st_size),
            int(value.st_mtime_ns),
        )

    sealed_identity = identity(before)
    if (
        sealed_identity != identity(descriptor_before)
        or sealed_identity != identity(descriptor_after)
        or sealed_identity != identity(after)
        or _is_symlink_or_reparse_point(path)
        or not stat.S_ISREG(after.st_mode)
        or int(after.st_nlink) != 1
        or len(raw) != int(after.st_size)
    ):
        raise ServerPidReceiptError("PID receipt changed while it was read")
    try:
        pid = int(raw.decode("utf-8-sig").strip())
    except (UnicodeError, ValueError) as exc:
        raise ServerPidReceiptError(f"PID receipt content is invalid: {exc}") from exc
    if pid <= 0:
        raise ServerPidReceiptError("PID receipt must contain a positive PID")
    if expected_pid is not None and pid != expected_pid:
        raise ServerPidReceiptError(
            f"PID receipt changed from proved-exited PID {expected_pid} to {pid}"
        )
    return {
        "pid": pid,
        "raw": raw,
        "identity": sealed_identity,
    }


def _remove_server_pid_receipt_after_proved_exit(
    pid: int, original: Dict[str, Any]
) -> Tuple[bool, str]:
    """Retry only receipt unlink while re-proving the same exited server."""

    last_error = ""
    for attempt in range(1, SERVER_PID_UNLINK_ATTEMPTS + 1):
        try:
            current = _snapshot_server_pid_receipt(expected_pid=pid)
        except ServerPidReceiptError as exc:
            return False, f"PID receipt identity/content drifted: {exc}"
        if (
            current.get("identity") != original.get("identity")
            or current.get("raw") != original.get("raw")
        ):
            return False, "PID receipt identity/content drifted before removal"

        if psutil.pid_exists(pid):
            return False, f"recorded PID {pid} became live before receipt removal"
        try:
            serving_pid = listener_pid(int(LAB_PORT), strict=True)
            live_stats = query_server_stats()
        except Exception as exc:
            return False, f"could not re-prove clear port {LAB_PORT}: {exc}"
        if serving_pid is not None or live_stats is not None:
            return False, (
                f"port {LAB_PORT} became live before receipt removal "
                f"(listener_pid={serving_pid})"
            )

        try:
            SERVER_PID_FILE.unlink()
        except FileNotFoundError as exc:
            return False, f"PID receipt disappeared before verified removal: {exc}"
        except OSError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < SERVER_PID_UNLINK_ATTEMPTS:
                time.sleep(SERVER_PID_UNLINK_RETRY_S)
            continue
        if os.path.lexists(SERVER_PID_FILE):
            return False, "PID receipt path was replaced during verified removal"
        return True, ""

    return False, (
        "receipt removal still failed after "
        f"{SERVER_PID_UNLINK_ATTEMPTS} attempts: {last_error}"
    )


def shutdown_lab_server() -> Dict[str, Any]:
    """Stop the verified lab server and return machine-checkable cleanup proof.

    The PID receipt is deliberately retained whenever identity, termination, or
    listener shutdown cannot be proved.  A caller may therefore make its own
    PASS conditional on ``result["success"]`` without parsing console text.
    """
    result: Dict[str, Any] = {
        "success": False,
        "had_receipt": os.path.lexists(SERVER_PID_FILE),
        "had_idle_gate_sidecar": os.path.lexists(SERVER_IDLE_GATE_FILE),
        "pid": None,
        "pid_verified": False,
        "termination_attempted": False,
        "termination_reported_success": False,
        "process_exited": False,
        "listener_exited": False,
        "receipt_removed": False,
        "idle_gate_sidecar_validated": False,
        "idle_gate_sidecar_removed": False,
        "reason": "",
    }

    if not os.path.lexists(SERVER_PID_FILE):
        live_stats = query_server_stats()
        serving_pid = listener_pid(int(LAB_PORT))
        if live_stats is not None or serving_pid is not None:
            result["reason"] = "port 8199 is live without an owned PID receipt"
            print(f"[SERVER] {result['reason']}; refusing cleanup.")
            return result
        if os.path.lexists(SERVER_IDLE_GATE_FILE):
            result["reason"] = (
                "orphan .server.idle-gate.json exists without an owned PID receipt"
            )
            print(f"[SERVER] {result['reason']}; preserving it for inspection.")
            return result
        result.update(
            success=True,
            process_exited=True,
            listener_exited=True,
            reason="no owned server receipt and no live listener",
        )
        return result

    try:
        receipt_snapshot = _snapshot_server_pid_receipt()
        pid = int(receipt_snapshot["pid"])
    except (ServerPidReceiptError, KeyError, TypeError, ValueError) as exc:
        result["reason"] = f"could not verify .server.pid: {exc}"
        print(f"[SERVER] {result['reason']}; keeping receipt.")
        return result
    result["pid"] = pid

    if not psutil.pid_exists(pid):
        try:
            sidecar_snapshot = _snapshot_server_idle_gate_sidecar_for_cleanup(pid)
        except ServerIdleGateSidecarError as exc:
            result["reason"] = f"could not verify server idle-gate sidecar: {exc}"
            print(f"[SERVER] {result['reason']}; keeping receipt and sidecar.")
            return result
        if sidecar_snapshot is None:
            result["reason"] = (
                "verified stale PID receipt has no mandatory server idle-gate sidecar"
            )
            print(f"[SERVER] {result['reason']}; keeping receipt.")
            return result
        result["idle_gate_sidecar_validated"] = True
        live_stats = query_server_stats()
        serving_pid = listener_pid(int(LAB_PORT))
        if live_stats is not None or serving_pid is not None:
            result["reason"] = (
                f"recorded PID {pid} is gone but port {LAB_PORT} still has an unverified server"
            )
            print(f"[SERVER] {result['reason']}; keeping receipt.")
            return result
        result["process_exited"] = True
        result["listener_exited"] = True
        sidecar_removed, sidecar_error = (
            _remove_server_idle_gate_sidecar_after_proved_exit(
                pid, sidecar_snapshot
            )
        )
        if not sidecar_removed:
            result["reason"] = (
                "server already exited but idle-gate sidecar removal failed: "
                f"{sidecar_error}"
            )
            print(f"[SERVER] {result['reason']}")
            return result
        result["idle_gate_sidecar_removed"] = True
        if os.path.lexists(SERVER_IDLE_GATE_FILE):
            result["reason"] = (
                "idle-gate sidecar path reappeared before stale PID receipt removal"
            )
            print(f"[SERVER] {result['reason']}; preserving the PID receipt.")
            return result
        receipt_removed, removal_error = _remove_server_pid_receipt_after_proved_exit(
            pid, receipt_snapshot
        )
        if not receipt_removed:
            result["reason"] = (
                "server already exited but PID receipt removal failed: "
                f"{removal_error}"
            )
            print(f"[SERVER] {result['reason']}")
            return result
        result["receipt_removed"] = True
        if os.path.lexists(SERVER_IDLE_GATE_FILE):
            result["reason"] = (
                "idle-gate sidecar path appeared after stale PID receipt removal"
            )
            print(f"[SERVER] {result['reason']}; preserving the unknown sidecar.")
            return result
        result.update(
            success=True,
            reason="recorded server was already stopped and port is clear",
        )
        print(f"[SERVER] Confirmed stale PID {pid} is gone; removed .server.pid receipt.")
        return result

    if not is_expected_lab_server_pid(pid):
        result["reason"] = f"recorded PID {pid} failed lab command-line verification"
        print(f"[SERVER] {result['reason']}; keeping receipt.")
        return result
    result["pid_verified"] = True

    try:
        process_create_time = psutil.Process(pid).create_time()
        sidecar_snapshot = _snapshot_server_idle_gate_sidecar_for_cleanup(
            pid, process_create_time
        )
    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        OSError,
        ServerIdleGateSidecarError,
    ) as exc:
        result["reason"] = f"could not verify server idle-gate sidecar: {exc}"
        print(f"[SERVER] {result['reason']}; keeping receipt and sidecar.")
        return result
    if sidecar_snapshot is None:
        result["reason"] = (
            "verified live PID receipt has no mandatory server idle-gate sidecar"
        )
        print(f"[SERVER] {result['reason']}; keeping receipt.")
        return result
    result["idle_gate_sidecar_validated"] = True

    serving_pid = listener_pid(int(LAB_PORT))
    live_stats = query_server_stats()
    if serving_pid not in (None, pid) or (
        live_stats is not None and serving_pid != pid
    ):
        result["reason"] = (
            f"port {LAB_PORT} ownership does not match verified recorded PID {pid}"
        )
        print(f"[SERVER] {result['reason']}; refusing to terminate or adopt either process.")
        return result

    print(f"[SERVER] Shutting down verified lab server (PID {pid})...")
    result["termination_attempted"] = True
    try:
        terminated = bool(terminate_owned_process_tree(pid))
    except Exception as exc:
        result["reason"] = f"termination raised an error: {exc}"
        print(f"[SERVER] {result['reason']}; keeping receipt.")
        return result
    result["termination_reported_success"] = terminated
    result["process_exited"] = not psutil.pid_exists(pid)
    post_listener = listener_pid(int(LAB_PORT))
    post_stats = query_server_stats()
    result["listener_exited"] = post_listener is None and post_stats is None

    if not (terminated and result["process_exited"] and result["listener_exited"]):
        result["reason"] = (
            f"shutdown proof failed (terminated={terminated}, "
            f"process_exited={result['process_exited']}, listener_exited={result['listener_exited']})"
        )
        print(f"[SERVER] {result['reason']}; keeping .server.pid.")
        return result

    sidecar_removed, sidecar_error = (
        _remove_server_idle_gate_sidecar_after_proved_exit(pid, sidecar_snapshot)
    )
    if not sidecar_removed:
        result["reason"] = (
            "server exited but idle-gate sidecar removal failed: "
            f"{sidecar_error}"
        )
        print(f"[SERVER] {result['reason']}; keeping .server.pid.")
        return result
    result["idle_gate_sidecar_removed"] = True
    if os.path.lexists(SERVER_IDLE_GATE_FILE):
        result["reason"] = (
            "idle-gate sidecar path reappeared before PID receipt removal"
        )
        print(f"[SERVER] {result['reason']}; keeping .server.pid.")
        return result

    receipt_removed, removal_error = _remove_server_pid_receipt_after_proved_exit(
        pid, receipt_snapshot
    )
    if not receipt_removed:
        result["reason"] = f"server exited but PID receipt removal failed: {removal_error}"
        print(f"[SERVER] {result['reason']}")
        return result
    result["receipt_removed"] = True
    if os.path.lexists(SERVER_IDLE_GATE_FILE):
        result["reason"] = "idle-gate sidecar path appeared after PID receipt removal"
        print(f"[SERVER] {result['reason']}; preserving the unknown sidecar.")
        return result
    result.update(
        success=True,
        reason="verified server process and listener exited",
    )
    print(f"[SERVER] Process {pid} and listener exited; removed .server.pid receipt.")
    return result


class SuiteParentWatchdog(threading.Thread):
    """Terminate orphan suite-child work if its nonce-bound parent disappears."""

    def __init__(
        self,
        owner_pid: int,
        owner_create_time: float,
        *,
        interval_s: float = 0.25,
        cleanup_fn=None,
        exit_fn=None,
    ):
        super().__init__(daemon=True, name="suite-parent-watchdog")
        self.owner_pid = int(owner_pid)
        self.owner_create_time = float(owner_create_time)
        self.interval_s = float(interval_s)
        self.cleanup_fn = cleanup_fn or shutdown_lab_server
        self.exit_fn = exit_fn or os._exit
        self._stop_event = threading.Event()

    def parent_alive(self) -> bool:
        return lab_locks.process_identity_is_live(self.owner_pid, self.owner_create_time)

    def run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            if self.parent_alive():
                continue
            cleanup: Dict[str, Any] = {
                "success": False,
                "reason": "suite watchdog cleanup did not return",
            }
            try:
                try:
                    cleanup_result = self.cleanup_fn()
                    if isinstance(cleanup_result, dict):
                        cleanup = cleanup_result
                    else:
                        cleanup = {
                            "success": False,
                            "reason": "suite watchdog cleanup returned invalid evidence",
                        }
                except BaseException as exc:
                    cleanup = {
                        "success": False,
                        "reason": f"suite watchdog cleanup raised {type(exc).__name__}: {exc}",
                    }
                if cleanup.get("success") is not True:
                    try:
                        write_queue_quarantine(
                            "suite parent died while child was active and server cleanup was not proved",
                            {
                                "suite_owner_pid": self.owner_pid,
                                "suite_owner_create_time": self.owner_create_time,
                                "cleanup": cleanup,
                            },
                        )
                    except BaseException:
                        # The orphaned child must still terminate even when the
                        # best-effort quarantine checkpoint itself cannot be written.
                        pass
            finally:
                self.exit_fn(97)
            return

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=max(1.0, self.interval_s * 4))


def start_suite_parent_watchdog() -> SuiteParentWatchdog:
    """Start a watchdog from the already-verified suite child environment."""
    try:
        owner_pid = int(os.environ[lab_locks.SUITE_OWNER_PID_ENV])
        owner_create_time = float(os.environ[lab_locks.SUITE_OWNER_CREATE_TIME_ENV])
    except (KeyError, TypeError, ValueError) as exc:
        raise PreflightError(1, "Suite parent", "Verified suite parent identity is missing") from exc
    watchdog = SuiteParentWatchdog(owner_pid, owner_create_time)
    watchdog.start()
    return watchdog


def fetch_object_info() -> Dict[str, Any]:
    """Fetch object info dictionary from GET /object_info."""
    try:
        req = urllib.request.Request(f"{COMFY_SERVER_URL}/object_info")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise PreflightError(4, "Nodes exist", f"Failed to fetch /object_info from {COMFY_SERVER_URL}: {e}")


def check_nodes_exist(recipe_data: Dict[str, Any], object_info: Dict[str, Any]):
    """Preflight Check #4: Every class_type in recipe appears in GET /object_info."""
    prompt_dict = recipe_data.get("prompt", recipe_data)
    missing_nodes = set()
    for node_id, node in prompt_dict.items():
        if isinstance(node, dict) and "class_type" in node:
            class_type = node["class_type"]
            if class_type not in object_info:
                missing_nodes.add(class_type)

    if missing_nodes:
        raise PreflightError(4, "Nodes exist", f"Missing server node class types: {sorted(list(missing_nodes))}")


def check_models_exist(recipe_data: Dict[str, Any]):
    """Preflight Check #5: Every referenced model appears in models_manifest.md."""
    if not MODELS_MANIFEST.exists():
        raise PreflightError(5, "Models exist", "models_manifest.md missing from repo root")

    manifest_text = MODELS_MANIFEST.read_text(encoding="utf-8")
    
    referenced_models = set()
    def scan_values(obj):
        if isinstance(obj, str):
            if any(obj.endswith(ext) for ext in [".safetensors", ".ckpt", ".pth", ".bin", ".gguf", ".onnx"]):
                referenced_models.add(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                scan_values(v)
        elif isinstance(obj, list):
            for item in obj:
                scan_values(item)

    scan_values(recipe_data)

    missing = [m for m in referenced_models if m not in manifest_text]
    if missing:
        raise PreflightError(5, "Models exist", f"Models missing from manifest: {missing}")


def iter_prompt_links(value: Any, path: str = ""):
    """Yield nested Comfy API links as (socket path, source id, output index)."""
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
    ):
        yield path, value[0], value[1]
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_prompt_links(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield from iter_prompt_links(child, child_path)


def minimax_h3_autogrow_input_errors(prompt_dict: Dict[str, Any]) -> List[str]:
    """Reject V3 autogrow inputs that ComfyUI would ignore or cannot finalize."""
    errors: List[str] = []
    if not isinstance(prompt_dict, dict):
        return errors

    for node_id, node in prompt_dict.items():
        if not isinstance(node, dict) or node.get("class_type") != _MINIMAX_H3_REFERENCE_CLASS:
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        for container, (prefix, _) in _MINIMAX_H3_AUTOGROW_SOCKET_SPECS.items():
            if container in inputs:
                errors.append(
                    f"Node {node_id} ({_MINIMAX_H3_REFERENCE_CLASS}) input '{container}' "
                    "is a nested V3 autogrow container that ComfyUI ignores; use direct "
                    f"dotted sockets such as '{container}.{prefix}0'"
                )

        for input_name, value in inputs.items():
            if not isinstance(input_name, str):
                continue
            for container, (prefix, count) in _MINIMAX_H3_AUTOGROW_SOCKET_SPECS.items():
                namespace = f"{container}."
                if not input_name.startswith(namespace):
                    continue
                member_name = input_name[len(namespace):]
                allowed_members = {f"{prefix}{index}" for index in range(count)}
                if member_name not in allowed_members:
                    errors.append(
                        f"Node {node_id} ({_MINIMAX_H3_REFERENCE_CLASS}) input "
                        f"'{input_name}' is not a valid V3 autogrow socket"
                    )
                if not (
                    isinstance(value, list)
                    and len(value) == 2
                    and isinstance(value[0], str)
                    and isinstance(value[1], int)
                    and not isinstance(value[1], bool)
                    and value[1] >= 0
                ):
                    errors.append(
                        f"Node {node_id} ({_MINIMAX_H3_REFERENCE_CLASS}) input "
                        f"'{input_name}' must be a direct Comfy link [node_id, output_index]"
                    )
                break

    return errors


def check_installed_schema_contract(
    recipe_data: Dict[str, Any], system_stats: Dict[str, Any]
) -> None:
    """Require the running ComfyUI version and checkout to match a frozen topology contract."""
    topology = recipe_data.get("topology_contract", {})
    if not isinstance(topology, dict):
        return
    installed_schema = topology.get("installed_schema")
    if installed_schema is None:
        return
    if not isinstance(installed_schema, dict):
        raise PreflightError(
            6,
            "Widget integrity",
            "topology_contract.installed_schema must be a dictionary",
        )

    expected_version = installed_schema.get("comfyui_version")
    expected_commit = installed_schema.get("git_commit")
    if not isinstance(expected_version, str) or not expected_version.strip():
        raise PreflightError(
            6,
            "Widget integrity",
            "topology_contract.installed_schema.comfyui_version must be a non-empty string",
        )
    if not isinstance(expected_commit, str) or not expected_commit.strip():
        raise PreflightError(
            6,
            "Widget integrity",
            "topology_contract.installed_schema.git_commit must be a non-empty string",
        )

    actual_version = system_stats.get("system", {}).get("comfyui_version")
    actual_commit = git_commit(COMFYUI_ROOT)
    errors = []
    if actual_version != expected_version:
        errors.append(
            f"Frozen topology requires ComfyUI {expected_version}, live server reports {actual_version!r}"
        )
    if actual_commit.lower() != expected_commit.lower():
        errors.append(
            f"Frozen topology requires ComfyUI commit {expected_commit}, installed checkout is {actual_commit or '<unavailable>'}"
        )

    has_node_source = "node_source" in installed_schema
    has_node_source_hash = "node_source_sha256" in installed_schema
    if has_node_source != has_node_source_hash:
        errors.append(
            "topology_contract.installed_schema.node_source and node_source_sha256 "
            "must be declared together"
        )
    elif has_node_source:
        node_source = installed_schema.get("node_source")
        expected_source_hash = installed_schema.get("node_source_sha256")
        if not isinstance(node_source, str) or not node_source.strip():
            errors.append(
                "topology_contract.installed_schema.node_source must be a non-empty relative path"
            )
        if not isinstance(expected_source_hash, str) or re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_source_hash
        ) is None:
            errors.append(
                "topology_contract.installed_schema.node_source_sha256 must be a "
                "64-character SHA-256"
            )

        if (
            isinstance(node_source, str)
            and node_source.strip()
            and isinstance(expected_source_hash, str)
            and re.fullmatch(r"[0-9a-fA-F]{64}", expected_source_hash) is not None
        ):
            normalized_source = node_source.replace("\\", "/")
            source_parts = normalized_source.split("/")
            source_relative = Path(normalized_source)
            if (
                source_relative.is_absolute()
                or source_relative.drive
                or any(part in {"", ".", ".."} for part in source_parts)
            ):
                errors.append(
                    "topology_contract.installed_schema.node_source must be a traversal-free "
                    "relative path inside the installed ComfyUI root"
                )
            else:
                try:
                    comfy_root = COMFYUI_ROOT.resolve()
                    source_path = (comfy_root / source_relative).resolve()
                    source_path.relative_to(comfy_root)
                except (OSError, ValueError):
                    errors.append(
                        "topology_contract.installed_schema.node_source escapes the installed "
                        f"ComfyUI root: {node_source}"
                    )
                else:
                    if not source_path.is_file():
                        errors.append(
                            "Frozen topology node source is missing from the installed ComfyUI "
                            f"root: {node_source}"
                        )
                    else:
                        try:
                            actual_source_hash = sha256_file(source_path)
                        except OSError as exc:
                            errors.append(
                                f"Could not hash frozen topology node source {node_source}: {exc}"
                            )
                        else:
                            if actual_source_hash.lower() != expected_source_hash.lower():
                                errors.append(
                                    "Frozen topology node source SHA-256 changed: "
                                    f"{node_source} (expected {expected_source_hash.lower()}, "
                                    f"found {actual_source_hash})"
                                )
    if errors:
        raise PreflightError(6, "Widget integrity", "; ".join(errors))


def check_widget_integrity(recipe_data: Dict[str, Any], object_info: Dict[str, Any]):
    """Preflight Check #6: Recipe JSON parses; widget count & input structure validated against server object_info schema."""
    prompt_dict = recipe_data.get("prompt", recipe_data)
    errors: List[str] = minimax_h3_autogrow_input_errors(prompt_dict)
    for node_id, node in prompt_dict.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        if not class_type:
            raise PreflightError(6, "Widget integrity", f"Node {node_id} missing class_type")
        if not isinstance(inputs, dict):
            raise PreflightError(6, "Widget integrity", f"Node {node_id} inputs is not a dictionary")

        for input_name, value in inputs.items():
            for socket_path, source_id, output_index in iter_prompt_links(value, input_name):
                if source_id not in prompt_dict:
                    errors.append(
                        f"Node {node_id} ({class_type}) input '{socket_path}' references missing node {source_id}"
                    )
                if not isinstance(output_index, int) or isinstance(output_index, bool) or output_index < 0:
                    errors.append(
                        f"Node {node_id} ({class_type}) input '{socket_path}' has invalid output index {output_index!r}"
                    )
                elif source_id in prompt_dict:
                    source_class = prompt_dict[source_id].get("class_type")
                    source_outputs = object_info.get(source_class, {}).get("output", [])
                    if source_outputs and output_index >= len(source_outputs):
                        errors.append(
                            f"Node {node_id} ({class_type}) input '{socket_path}' requests output {output_index} "
                            f"from {source_id} ({source_class}), which exposes {len(source_outputs)} outputs"
                        )

        if class_type in object_info:
            info = object_info[class_type]
            req_inputs = info.get("input", {}).get("required", {})
            opt_inputs = info.get("input", {}).get("optional", {})
            schema_keys = set(req_inputs.keys()) | set(opt_inputs.keys())
            supplied_schema_keys = {
                key if key in schema_keys else key.split(".", 1)[0]
                for key in inputs
            }
            missing_required = sorted(set(req_inputs) - supplied_schema_keys)
            for in_key in missing_required:
                errors.append(f"Node {node_id} ({class_type}) is missing required input '{in_key}'")
            for in_key in inputs:
                schema_key = in_key if in_key in schema_keys else in_key.split(".", 1)[0]
                if schema_key not in schema_keys:
                    errors.append(
                        f"Node {node_id} ({class_type}) input '{in_key}' is not in the live server schema"
                    )

    topology = recipe_data.get("topology_contract", {})
    if topology:
        if not isinstance(topology, dict):
            errors.append("topology_contract must be a dictionary")
        else:
            if topology.get("schema_version", 1) != 1:
                errors.append("topology_contract.schema_version must be 1")

            frozen_template = topology.get("frozen_template")
            if frozen_template is not None:
                if not isinstance(frozen_template, dict):
                    errors.append("topology_contract.frozen_template must be a dictionary")
                else:
                    template_name = frozen_template.get("path")
                    expected_hash = frozen_template.get("sha256")
                    try:
                        template_path = (REPO_ROOT / str(template_name)).resolve()
                        template_path.relative_to(REPO_ROOT)
                        if not template_path.is_file():
                            errors.append(f"Frozen template is missing: {template_name}")
                        elif sha256_file(template_path) != expected_hash:
                            errors.append(f"Frozen template hash changed: {template_name}")
                    except (OSError, ValueError):
                        errors.append(f"Frozen template path escapes the repository: {template_name}")

            required_nodes = topology.get("required_nodes", {})
            if not isinstance(required_nodes, dict):
                errors.append("topology_contract.required_nodes must be a dictionary")
            else:
                for required_id, expected_class in required_nodes.items():
                    actual_class = prompt_dict.get(str(required_id), {}).get("class_type")
                    if actual_class != expected_class:
                        errors.append(
                            f"Official topology node {required_id} must be {expected_class}, found {actual_class}"
                        )

                exact_node_set = topology.get("exact_node_set", False)
                if not isinstance(exact_node_set, bool):
                    errors.append("topology_contract.exact_node_set must be true or false")
                elif exact_node_set:
                    expected_node_ids = {str(node_id) for node_id in required_nodes}
                    actual_node_ids = {str(node_id) for node_id in prompt_dict}
                    extra_node_ids = sorted(actual_node_ids - expected_node_ids, key=str)
                    missing_node_ids = sorted(expected_node_ids - actual_node_ids, key=str)
                    if extra_node_ids:
                        errors.append(
                            f"Official topology exact_node_set contains unexpected nodes: {extra_node_ids}"
                        )
                    if missing_node_ids:
                        errors.append(
                            f"Official topology exact_node_set is missing nodes: {missing_node_ids}"
                        )

            required_connections = topology.get("required_connections", {})
            if not isinstance(required_connections, dict):
                errors.append("topology_contract.required_connections must be a dictionary")
            else:
                for socket, expected in required_connections.items():
                    if not isinstance(socket, str) or "." not in socket:
                        errors.append(f"Invalid declared socket {socket!r}")
                        continue
                    declared_node, input_name = socket.split(".", 1)
                    actual = prompt_dict.get(declared_node, {}).get("inputs", {}).get(input_name)
                    if actual != expected:
                        errors.append(
                            f"Official topology socket {socket} must be {expected!r}, found {actual!r}"
                        )

            required_values = topology.get("required_input_values", [])
            if not isinstance(required_values, list):
                errors.append("topology_contract.required_input_values must be a list")
            else:
                for assertion in required_values:
                    if not isinstance(assertion, dict):
                        errors.append(f"Invalid required input assertion: {assertion!r}")
                        continue
                    required_id = str(assertion.get("node"))
                    input_name = assertion.get("input")
                    expected = assertion.get("equals")
                    actual = prompt_dict.get(required_id, {}).get("inputs", {}).get(input_name)
                    if actual != expected:
                        errors.append(
                            f"Official topology value {required_id}.{input_name} must be {expected!r}, found {actual!r}"
                        )

            required_absent_inputs = topology.get("required_absent_inputs", [])
            if not isinstance(required_absent_inputs, list):
                errors.append("topology_contract.required_absent_inputs must be a list")
            else:
                for socket in required_absent_inputs:
                    if not isinstance(socket, str) or "." not in socket:
                        errors.append(f"Invalid absent-input socket {socket!r}")
                        continue
                    declared_node, input_name = socket.split(".", 1)
                    inputs = prompt_dict.get(declared_node, {}).get("inputs", {})
                    if isinstance(inputs, dict) and input_name in inputs:
                        errors.append(
                            f"Official topology input {socket} must be absent, found {inputs[input_name]!r}"
                        )

            forbidden = set(topology.get("forbidden_class_types", []))
            present_forbidden = sorted(
                {
                    node.get("class_type")
                    for node in prompt_dict.values()
                    if isinstance(node, dict) and node.get("class_type") in forbidden
                }
            )
            if present_forbidden:
                errors.append(f"Official topology contains forbidden node classes: {present_forbidden}")

            required_classes = set(topology.get("required_class_types", []))
            present_classes = {
                node.get("class_type") for node in prompt_dict.values() if isinstance(node, dict)
            }
            missing_classes = sorted(required_classes - present_classes)
            if missing_classes:
                errors.append(f"Official topology is missing required node classes: {missing_classes}")

            terminal_node = topology.get("terminal_node")
            if terminal_node is not None:
                terminal = prompt_dict.get(str(terminal_node), {})
                if terminal.get("class_type") not in {"SaveImage", "SaveVideo"}:
                    errors.append(f"Official topology terminal node {terminal_node} is not a save sink")

            if topology.get("require_all_nodes_reachable") is True:
                sink_ids = {
                    node_id
                    for node_id, node in prompt_dict.items()
                    if isinstance(node, dict)
                    and (
                        object_info.get(node.get("class_type"), {}).get("output_node") is True
                        or node.get("class_type") in {"SaveImage", "SaveVideo"}
                    )
                }
                reachable = set(sink_ids)
                stack = list(sink_ids)
                while stack:
                    current = stack.pop()
                    for value in prompt_dict[current].get("inputs", {}).values():
                        for _, source_id, _ in iter_prompt_links(value):
                            if source_id in prompt_dict and source_id not in reachable:
                                reachable.add(source_id)
                                stack.append(source_id)
                dead_nodes = sorted(set(prompt_dict) - reachable, key=str)
                if dead_nodes:
                    errors.append(f"Official topology has nodes disconnected from every output: {dead_nodes}")

    if errors:
        raise PreflightError(6, "Widget integrity", "; ".join(errors))


def check_affordability(
    recipe_name: str,
    recipe_sha256: str,
    boot_lane: str,
    is_force: bool = False,
):
    """Refuse an unchanged, known-over-gate recipe/lane unless explicitly forced."""
    if is_force:
        return
    result_file = RESULTS_DIR / f"{recipe_name}.json"
    if result_file.exists():
        try:
            prev = json.loads(result_file.read_text(encoding="utf-8"))
            last_peak = prev.get("peak_vram_gb", 0.0)
            same_recipe = prev.get("recipe_sha256") == recipe_sha256
            same_lane = prev.get("boot_lane") == boot_lane
            prior_status = str(prev.get("status", ""))
            known_vram_failure = (
                last_peak > VRAM_GATE_GB
                or "net VRAM" in prior_status
                or prior_status.startswith("FAIL (VRAM")
            )
            prior_gate_failed = prev.get("gate_pass") is False or (
                "gate_pass" not in prev and known_vram_failure
            )
            if same_recipe and same_lane and prior_gate_failed and known_vram_failure:
                raise PreflightError(
                    7, "Affordability estimate",
                    f"Last identical recipe/lane failed its VRAM gate ({prior_status}; peak {last_peak:.2f} GB). Refusing unchanged re-run."
                )
        except json.JSONDecodeError:
            pass


def upload_fixtures(fixture_payloads: Dict[str, bytes]):
    """Overwrite exact fixture basenames and prove the server stored those bytes."""
    if not FIXTURES_DIR.exists():
        return

    for fixture_name, content in fixture_payloads.items():
        fix_file = FIXTURES_DIR / fixture_name
        try:
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            body = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
                "true\r\n"
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="type"\r\n\r\n'
                "input\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; filename="{fix_file.name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

            req = urllib.request.Request(
                f"{COMFY_SERVER_URL}/upload/image",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                upload_result = json.loads(response.read().decode("utf-8"))
            if (
                upload_result.get("name") != fix_file.name
                or upload_result.get("subfolder", "") != ""
                or upload_result.get("type") != "input"
            ):
                raise ValueError(f"server stored fixture under unexpected identity: {upload_result}")

            view_query = urllib.parse.urlencode({
                "filename": fix_file.name,
                "type": "input",
                "fixture_sha256": sha256_bytes(content),
            })
            view_req = urllib.request.Request(
                f"{COMFY_SERVER_URL}/view?{view_query}",
                headers={"Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(view_req, timeout=10) as response:
                stored_content = response.read()
            if sha256_bytes(stored_content) != sha256_bytes(content):
                raise ValueError("server readback SHA-256 does not match queued fixture bytes")
            print(f"[FIXTURE] Uploaded and verified fixture {fix_file.name} in server input directory")
        except Exception as exc:
            raise PreflightError(8, "Fixtures uploaded", f"Failed to upload {fixture_name}: {exc}") from exc


def check_fixtures_uploaded(recipe_data: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Capture fixtures, enforce audio ear receipts, upload, and return both hash sets."""
    try:
        fixture_names = referenced_fixtures(recipe_data)
        audio_fixture_names = referenced_audio_fixtures(recipe_data)
    except ValueError as exc:
        raise PreflightError(8, "Fixtures uploaded", str(exc)) from exc
    fixture_payloads: Dict[str, bytes] = {}
    for fixture in fixture_names:
        p = FIXTURES_DIR / fixture
        if not p.is_file():
            raise PreflightError(8, "Fixtures uploaded", f"Fixture file missing from fixtures/: {fixture}")
        fixture_payloads[fixture] = p.read_bytes()

    try:
        validate_fixture_hash_contract(recipe_data, fixture_payloads)
    except ValueError as exc:
        raise PreflightError(8, "Fixtures uploaded", str(exc)) from exc

    audio_receipt_hashes: Dict[str, str] = {}
    try:
        for fixture_name in audio_fixture_names:
            audio_receipt_hashes[fixture_name] = validate_audio_fixture_receipt(
                fixture_name, fixture_payloads[fixture_name]
            )
    except (KeyError, ValueError) as exc:
        raise PreflightError(8, "Fixtures uploaded", str(exc)) from exc

    upload_fixtures(fixture_payloads)
    fixture_hashes = {name: sha256_bytes(content) for name, content in fixture_payloads.items()}
    return fixture_hashes, audio_receipt_hashes


def check_boot_lane(
    recipe_name: str,
    system_stats: Dict[str, Any],
    manager_phase: Optional[str] = None,
):
    """Preflight Check #9: Confirm the isolated, offline, Sage-free lab lane."""
    argv = system_stats.get("system", {}).get("argv", [])
    if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
        raise PreflightError(9, "Boot lane", "Live server argv must be a list of strings")
    manager_probe = manager_probe_requested()
    extra_flags = str(argv)
    if "--use-sage-attention" in extra_flags:
        raise PreflightError(
            9, "Boot lane",
            "Server was started with --use-sage-attention; lab boot lane must be sage-free."
        )

    if argv.count("--disable-all-custom-nodes") != 1:
        raise PreflightError(
            9,
            "Boot lane",
            "Live server argv must contain exactly one --disable-all-custom-nodes",
        )
    manager_present = any("comfyui-manager" in value.lower() for value in argv)
    if manager_present and not manager_probe:
        raise PreflightError(
            9,
            "Boot lane",
            "ComfyUI-Manager is forbidden in the offline lab boot lane",
        )
    if manager_probe and not manager_present:
        raise PreflightError(
            9,
            "Boot lane",
            "Manager offline probe requested but ComfyUI-Manager is not whitelisted",
        )

    whitelist_flag = "--whitelist-custom-nodes"
    if argv.count(whitelist_flag) != 1:
        raise PreflightError(
            9,
            "Boot lane",
            "Live server argv must contain exactly one --whitelist-custom-nodes",
        )
    whitelist_index = argv.index(whitelist_flag)
    whitelist_values: List[str] = []
    for value in argv[whitelist_index + 1:]:
        if value.startswith("--"):
            break
        whitelist_values.append(value)
    expected_whitelist = set(REQUIRED_CUSTOM_NODE_WHITELIST)
    if manager_probe:
        expected_whitelist.add(MANAGER_PROBE_CUSTOM_NODE)
    if (
        len(whitelist_values) != len(expected_whitelist)
        or set(whitelist_values) != expected_whitelist
    ):
        raise PreflightError(
            9,
            "Boot lane",
            "Live server custom-node whitelist must contain exactly "
            f"{sorted(expected_whitelist)}; found {whitelist_values}",
        )

    expected_reserve = os.environ.get("LAB_RESERVE_VRAM_GB")
    if expected_reserve:
        try:
            reserve_index = argv.index("--reserve-vram")
            actual_reserve = float(argv[reserve_index + 1])
            if abs(actual_reserve - float(expected_reserve)) > 0.01:
                raise ValueError
        except (ValueError, IndexError):
            raise PreflightError(
                9,
                "Boot lane",
                f"Live server argv does not contain expected --reserve-vram {expected_reserve}",
            )
    elif "--reserve-vram" in argv:
        raise PreflightError(9, "Boot lane", "Live server has an unexpected --reserve-vram setting")

    expected_no_pinned = bool(os.environ.get("LAB_DISABLE_PINNED"))
    actual_no_pinned = "--disable-pinned-memory" in argv
    if expected_no_pinned != actual_no_pinned:
        expectation = "contain" if expected_no_pinned else "omit"
        raise PreflightError(
            9,
            "Boot lane",
            f"Live server argv must {expectation} --disable-pinned-memory for this lane",
        )

    expected_cache_classic = bool(os.environ.get("LAB_CACHE_CLASSIC"))
    # ComfyUI makes --high-ram imply classic caching internally.  Treat it as
    # the same effective cache mode so the recorded lane cannot understate it.
    actual_cache_classic = "--cache-classic" in argv or "--high-ram" in argv
    if expected_cache_classic != actual_cache_classic:
        expectation = "contain" if expected_cache_classic else "omit"
        raise PreflightError(
            9,
            "Boot lane",
            f"Live server argv must {expectation} --cache-classic for this lane",
        )
    conflicting_cache_flags = {
        flag for flag in ("--cache-none", "--cache-lru", "--cache-ram") if flag in argv
    }
    if expected_cache_classic and conflicting_cache_flags:
        raise PreflightError(
            9,
            "Boot lane",
            "Suite cache-classic lane has conflicting cache flags: "
            f"{sorted(conflicting_cache_flags)}",
        )
    return manager_probe_evidence(
        recipe_name,
        argv,
        require_pre_prompt=manager_phase == "cold",
    )


def check_disk_space():
    """Preflight Check #10: At least 5 GB free on output drive."""
    total, used, free = shutil.disk_usage(REPO_ROOT)
    free_gb = free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        raise PreflightError(10, "Disk", f"Only {free_gb:.2f} GB free on output drive (min {MIN_FREE_DISK_GB} GB required)")


def run_all_preflights(
    recipe_path: Path,
    recipe_data: dict,
    recipe_name: str,
    recipe_sha256: str,
    boot_lane: str,
    is_force: bool = False,
    manager_phase: Optional[str] = None,
    expected_gpu_lock_owner: Optional[Dict[str, Any]] = None,
):
    """Run all 10 preflight safety and validity checks before acquiring lock."""
    print(f"--- Running Preflight Checks for {recipe_name} ---")

    print("  [OK] Check 1: Atomic GPU lock held by this runner")
    system_stats = check_server_up_and_ownership(
        recipe_name, expected_gpu_lock_owner
    )
    preboot_gpu_idle_gate = system_stats.pop(GPU_IDLE_INTERNAL_STATS_KEY, None)
    preboot_gpu_idle_gate_sidecar = system_stats.pop(
        GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY, None
    )
    if not isinstance(preboot_gpu_idle_gate, dict):
        raise PreflightError(
            2,
            "GPU idle",
            "Server preflight omitted the immutable pre-boot idle/reuse evidence",
        )
    idle_errors = gpu_idle_gate_validation_errors(preboot_gpu_idle_gate)
    if idle_errors:
        raise PreflightError(
            2,
            "GPU idle",
            "Invalid pre-boot idle/reuse evidence: " + "; ".join(idle_errors),
        )
    if not isinstance(preboot_gpu_idle_gate_sidecar, dict):
        raise PreflightError(
            2,
            "GPU idle",
            "Server preflight omitted the persisted cold idle-gate sidecar snapshot",
        )
    if (
        preboot_gpu_idle_gate_sidecar.get("path")
        != str(SERVER_IDLE_GATE_FILE.resolve())
        or preboot_gpu_idle_gate_sidecar.get("server_instance")
        != preboot_gpu_idle_gate.get("server_instance")
    ):
        raise PreflightError(
            2,
            "GPU idle",
            "Idle-gate sidecar snapshot is not bound to this server/evidence",
        )
    if preboot_gpu_idle_gate.get("status") == "measured" and (
        preboot_gpu_idle_gate_sidecar.get("evidence_sha256")
        != preboot_gpu_idle_gate.get("evidence_sha256")
    ):
        raise PreflightError(
            2,
            "GPU idle",
            "Cold receipt evidence does not match the persisted idle-gate sidecar",
        )
    print(f"  [OK] Check 3: Lab server up & owned at 127.0.0.1:{LAB_PORT}")

    object_info = fetch_object_info()
    check_nodes_exist(recipe_data, object_info)
    print("  [OK] Check 4: All recipe node class_types exist on server")

    check_models_exist(recipe_data)
    print("  [OK] Check 5: All referenced models exist in models_manifest.md")

    check_installed_schema_contract(recipe_data, system_stats)
    check_widget_integrity(recipe_data, object_info)
    print("  [OK] Check 6: Widget integrity and frozen topology schema verified")

    check_affordability(recipe_name, recipe_sha256, boot_lane, is_force=is_force)
    print("  [OK] Check 7: Affordability check passed")

    queued_fixture_sha256s, queued_audio_receipt_sha256s = check_fixtures_uploaded(recipe_data)
    print("  [OK] Check 8: Fixtures and audio ear-gate receipts verified")

    manager_offline_probe = check_boot_lane(
        recipe_name, system_stats, manager_phase=manager_phase
    )
    print("  [OK] Check 9: Boot lane verified (lab-8199, sage-free)")

    check_disk_space()
    print("  [OK] Check 10: Output disk space >= 5 GB")
    print("--- Preflight Complete: ALL CHECKS PASSED ---\n")
    return (
        system_stats,
        queued_fixture_sha256s,
        queued_audio_receipt_sha256s,
        manager_offline_probe,
        preboot_gpu_idle_gate,
        preboot_gpu_idle_gate_sidecar,
    )


class VramMonitorThread(threading.Thread):
    """Background thread polling nvidia-smi every 200ms (0.2s) for peak VRAM usage."""
    def __init__(self, interval: float = POLL_INTERVAL_S):
        super().__init__()
        self.interval = interval
        self.running = True
        self.peaks: List[float] = []

    def run(self):
        while self.running:
            try:
                used_mb = query_gpu_vram_mb()
                self.peaks.append(used_mb / 1024.0)
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self) -> float:
        self.running = False
        self.join(timeout=3.0)
        return max(self.peaks) if self.peaks else 0.0


def update_results_ledger(recipe_name: str, status: str, peak_vram: float, baseline_vram: float, wall_clock: float, notes: str):
    """Update human-readable ledger in RESULTS.md with wall clock and baseline VRAM."""
    if not RESULTS_LEDGER.exists():
        RESULTS_LEDGER.write_text(
            "# Results Ledger\n\n| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |\n|---|---|---|---|---|---|\n",
            encoding="utf-8"
        )
    
    lines = RESULTS_LEDGER.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    header_idx = -1

    for idx, line in enumerate(lines):
        if line.startswith("# Results Ledger"):
            header_idx = idx

    # If file header needs restoring to 6-column format
    if header_idx != -1 and len(lines) > header_idx + 4:
        if "| baseline VRAM" not in lines[header_idx + 4]:
            lines[header_idx + 4] = "| recipe | status | peak VRAM (GB) | baseline VRAM (GB) | wall clock (s) | notes |"
            lines[header_idx + 5] = "|---|---|---|---|---|---|"

    row_str = f"| {recipe_name} | {status} | {peak_vram:.2f} | {baseline_vram:.2f} | {wall_clock:.1f} | {notes} |"

    for line in lines:
        if line.startswith(f"| {recipe_name} |"):
            new_lines.append(row_str)
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(row_str)

    RESULTS_LEDGER.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[LEDGER] Updated RESULTS.md entry for {recipe_name}: {status}")


def update_engine_matrix_beta(
    recipe_name: str,
    tier: str,
    status: str,
    peak_vram: float,
    wall_clock: float,
    gated: str,
    pass_consecutive: str,
    boot_lane: str,
    notes: str,
):
    """Update one row using the matrix's current ten-column schema."""
    if not ENGINE_MATRIX_BETA.exists():
        return

    today = time.strftime("%Y-%m-%d")
    lines = ENGINE_MATRIX_BETA.read_text(encoding="utf-8").splitlines()
    
    peak_str = f"{peak_vram:.2f}" if peak_vram > 0 else "N/A"
    wall_str = f"{wall_clock:.1f}" if wall_clock > 0 else "N/A"
    row_str = (
        f"| {recipe_name} | {tier} | {status} | {peak_str} | {wall_str} | "
        f"{gated} | {pass_consecutive} | {boot_lane} | {today} | {notes} |"
    )
    
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"| {recipe_name} |"):
            new_lines.append(row_str)
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(row_str)

    ENGINE_MATRIX_BETA.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[MATRIX] Updated ENGINE_MATRIX_BETA.md for {recipe_name}")


def main():
    try:
        enforce_lab_port()
    except PreflightError as exc:
        print(f"[PREFLIGHT ABORT] {exc}")
        return 1
    if len(sys.argv) < 2:
        print(
            "Usage: python run_recipe.py <path_to_recipe.json> [--suite] "
            "[--shutdown] [--completion-timeout-s <1-7200>]"
        )
        sys.exit(1)

    recipe_path = Path(sys.argv[1]).resolve()
    is_suite = "--suite" in sys.argv
    do_shutdown = "--shutdown" in sys.argv
    is_force = "--force" in sys.argv
    manager_probe_flag_count = sys.argv.count(MANAGER_PROBE_CLI_FLAG)
    if manager_probe_flag_count > 1:
        print(f"Error: {MANAGER_PROBE_CLI_FLAG} may be supplied only once")
        return 2
    manager_offline_test = manager_probe_flag_count == 1
    ambient_manager_probe = os.environ.get(MANAGER_PROBE_ENV)
    if manager_offline_test:
        if ambient_manager_probe not in (None, "", "1"):
            print(f"Error: conflicting {MANAGER_PROBE_ENV} value")
            return 2
        os.environ[MANAGER_PROBE_ENV] = "1"
    elif ambient_manager_probe not in (None, ""):
        print(
            f"Error: {MANAGER_PROBE_ENV} cannot enable Manager without "
            f"{MANAGER_PROBE_CLI_FLAG}"
        )
        return 2
    elif os.environ.get(MANAGER_PROBE_LOG_ENV):
        print(
            f"Error: {MANAGER_PROBE_LOG_ENV} cannot be set without "
            f"{MANAGER_PROBE_CLI_FLAG}"
        )
        return 2
    try:
        manager_phase = manager_probe_phase(sys.argv)
    except ValueError as exc:
        print(f"Error: invalid Manager probe phase: {exc}")
        return 2
    tier = "suite" if is_suite else "smoke"
    try:
        suite_cache_nonce = parse_suite_cache_nonce(sys.argv, is_suite)
        standalone_cache_nonce = parse_standalone_cache_nonce(sys.argv, is_suite)
    except ValueError as exc:
        print(f"Error: invalid executor cache control: {exc}")
        return 2
    try:
        completion_timeout_s = parse_completion_timeout_s(sys.argv)
    except ValueError as exc:
        print(f"Error: invalid completion timeout: {exc}")
        return 2
    executor_cache_nonce = suite_cache_nonce or standalone_cache_nonce
    
    reserve_vram_text = os.environ.get("LAB_RESERVE_VRAM_GB")
    reserve_vram_gib = None
    clamp_target_gib = None
    physical_total_vram_gib = None
    disable_pinned = bool(os.environ.get("LAB_DISABLE_PINNED"))
    cache_classic = bool(os.environ.get("LAB_CACHE_CLASSIC"))
    clamp_positions = [i for i, arg in enumerate(sys.argv) if arg == "--clamp"]
    try:
        if len(clamp_positions) > 1:
            raise ValueError("--clamp may be supplied only once")
        if clamp_positions:
            clamp_index = clamp_positions[0]
            if clamp_index + 1 >= len(sys.argv) or sys.argv[clamp_index + 1].startswith("--"):
                raise ValueError("--clamp requires a numeric target-card GiB value")
            clamp_target_gib = float(sys.argv[clamp_index + 1])
            physical_total_vram_gib = query_gpu_total_gib()
            reserve_vram_gib = reserve_for_target_gib(physical_total_vram_gib, clamp_target_gib)
            reserve_vram_text = f"{reserve_vram_gib:.3f}".rstrip("0").rstrip(".")
            os.environ["LAB_RESERVE_VRAM_GB"] = reserve_vram_text
        elif reserve_vram_text is not None:
            physical_total_vram_gib = query_gpu_total_gib()
            reserve_vram_gib = validate_reserve_gib(float(reserve_vram_text), physical_total_vram_gib)
            reserve_vram_text = f"{reserve_vram_gib:.3f}".rstrip("0").rstrip(".")
            os.environ["LAB_RESERVE_VRAM_GB"] = reserve_vram_text
    except (ValueError, subprocess.SubprocessError, FileNotFoundError) as exc:
        print(f"Error: invalid VRAM lane configuration: {exc}")
        sys.exit(2)

    for arg in sys.argv:
        if arg == "--disable-pinned-memory":
            disable_pinned = True
            os.environ["LAB_DISABLE_PINNED"] = "1"

    lane_parts = ["lab-8199", "sage-free"]
    if manager_offline_test:
        lane_parts.append("manager-offline-test")
    if disable_pinned:
        lane_parts.append("no-pinned")
    if cache_classic:
        lane_parts.append("cache-classic")
    if clamp_target_gib is not None:
        lane_parts.append(f"clamp-{clamp_target_gib:g}gb (reserve-{reserve_vram_gib:.3f}gb)")
    elif reserve_vram_gib is not None:
        lane_parts.append(f"reserve-{reserve_vram_gib:g}gb")
    boot_lane_str = ", ".join(lane_parts)

    if not recipe_path.exists():
        print(f"Error: Recipe file not found: {recipe_path}")
        sys.exit(1)

    recipe_name = recipe_path.stem
    if manager_offline_test:
        try:
            manager_probe_recipe_scope(recipe_name)
        except PreflightError as exc:
            print(f"Error: {exc}")
            return 2
    RESULTS_DIR.mkdir(exist_ok=True)
    lock_manager: Optional[LockManager] = None
    suite_parent_watchdog: Optional[SuiteParentWatchdog] = None
    prompt_request_started = False
    prompt_terminal_proved = False
    prompt_cleanup_proved = False
    try:
        try:
            queued_recipe_bytes = recipe_path.read_bytes()
            recipe_data = json.loads(queued_recipe_bytes.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"Error: Failed to parse recipe JSON: {e}")
            sys.exit(1)
        tier = str(recipe_data.get("tier", tier))
        requires_human_eyeball = recipe_requires_human_eyeball(recipe_data)

        # Check for BLOCKED status in recipe metadata
        if recipe_data.get("blocked", False):
            print(f"\n[BLOCKED] Recipe {recipe_name} is BLOCKED (required weights not present on disk).")
            print("[BLOCKED] No run receipt or ledger state was mutated because no gated run occurred.")
            return

        queued_recipe_sha256 = sha256_bytes(queued_recipe_bytes)
        queued_runner_sha256 = sha256_file(Path(__file__).resolve())
        queued_lab_locks_sha256 = sha256_file(LAB_LOCKS_SOURCE_PATH)
        try:
            queued_cache_runtime_sha256s = (
                suite_cache_runtime_sha256s() if suite_cache_nonce is not None else {}
            )
            queued_standalone_cache_runtime_sha256s = (
                standalone_cache_runtime_sha256s()
                if standalone_cache_nonce is not None
                else {}
            )
        except ValueError as exc:
            print(f"Error: executor cache runtime contract is not frozen: {exc}")
            return 1
        repo_git_commit = git_commit(REPO_ROOT)
        repo_git_dirty = git_dirty(REPO_ROOT)

        # Own the GPU lane before checking/booting port 8199. This prevents two
        # runners from racing through preflight and overwriting each other's PID
        # receipt before either queues a prompt.
        lock_manager = LockManager(suite_child=is_suite)
        lock_manager.acquire()
        if is_suite:
            suite_parent_watchdog = start_suite_parent_watchdog()

        # Execute all 10 Preflight checks
        try:
            (
                system_stats,
                queued_fixture_sha256s,
                queued_audio_receipt_sha256s,
                queued_manager_probe_evidence,
                queued_preboot_gpu_idle_gate,
                queued_preboot_gpu_idle_gate_sidecar,
            ) = run_all_preflights(
                recipe_path,
                recipe_data,
                recipe_name,
                queued_recipe_sha256,
                boot_lane_str,
                is_force=is_force,
                manager_phase=manager_phase,
                expected_gpu_lock_owner=lock_manager.owner,
            )
        except PreflightError as e:
            print(f"\n[PREFLIGHT ABORT] {e}")
            sys.exit(1)

        comfyui_git_commit = git_commit(COMFYUI_ROOT)
        queued_model_fingerprints = model_fingerprints(recipe_data)
        server_argv = system_stats.get("system", {}).get("argv", [])
        server_instance = verified_server_instance()
        queued_gpu_idle_gate_contract = queued_preboot_gpu_idle_gate.get("contract")
        if queued_gpu_idle_gate_contract != gpu_idle_gate_contract():
            raise PreflightError(
                2,
                "GPU idle",
                "Pre-boot idle evidence contract does not match the running collector",
            )
        if (
            (queued_gpu_idle_gate_contract.get("collector") or {}).get("sha256")
            != queued_runner_sha256
        ):
            raise PreflightError(
                2,
                "GPU idle",
                "Pre-boot idle collector SHA does not match the queued runner SHA",
            )
        if queued_preboot_gpu_idle_gate.get("server_instance") != server_instance:
            raise PreflightError(
                2,
                "GPU idle",
                "Pre-boot idle/reuse evidence is not bound to the verified server instance",
            )
        if (
            queued_preboot_gpu_idle_gate_sidecar.get("server_instance")
            != server_instance
        ):
            raise PreflightError(
                2,
                "GPU idle",
                "Persisted cold idle-gate sidecar is not bound to the verified server",
            )
        identity_payload = {
            "recipe_sha256": queued_recipe_sha256,
            "runner_sha256": queued_runner_sha256,
            "lab_locks_sha256": queued_lab_locks_sha256,
            "fixture_sha256s": queued_fixture_sha256s,
            "audio_receipt_sha256s": queued_audio_receipt_sha256s,
            "model_fingerprints": queued_model_fingerprints,
            "boot_lane": boot_lane_str,
            "server_argv": server_argv,
            "server_instance": server_instance,
            "comfyui_git_commit": comfyui_git_commit,
            "completion_timeout_s": completion_timeout_s,
            "preboot_gpu_idle_gate_contract": queued_gpu_idle_gate_contract,
            "operator_idle_policy": operator_idle_policy_contract(),
            PREQUEUE_WORKLOAD_SCAN_CONTRACT_KEY: (
                prequeue_known_workload_scan_contract()
            ),
        }
        if queued_manager_probe_evidence.get("enabled") is True:
            identity_payload["manager_offline_probe_identity"] = (
                manager_probe_identity(queued_manager_probe_evidence)
            )
        if queued_cache_runtime_sha256s:
            # The nonce value is deliberately excluded: it is executor metadata,
            # not declared recipe state.  The pinned runtime semantics are part
            # of identity, while the recipe SHA continues to bind noise_seed.
            identity_payload["suite_cache_runtime_sha256s"] = queued_cache_runtime_sha256s
        if queued_standalone_cache_runtime_sha256s:
            # The nonce is deliberately excluded from identity.  It changes
            # executor cache identity only; recipe bytes continue to bind the
            # declared seed and graph.
            identity_payload["standalone_cache_runtime_sha256s"] = (
                queued_standalone_cache_runtime_sha256s
            )
        run_identity_sha256 = stable_identity(identity_payload)
        result_file = RESULTS_DIR / f"{recipe_name}.json"
        try:
            initial_history = audit_run_history(RESULTS_DIR, recipe_name)
        except ReceiptHistoryError as exc:
            raise PreflightError(1, "Receipt history", str(exc)) from exc
        previous_result = initial_history["machine_previous"]
        run_state = next_run_state(
            previous_result,
            run_identity_sha256,
            previous_run_number=initial_history["max_run_number"],
        )
        run_count = run_state["run_count"]
        config_run_count = run_state["config_run_count"]
        is_warm_cache = config_run_count >= 2 and run_state["previous_gate_pass"]

        # Execute Recipe under Lock
        with lock_manager as lock:
            ensure_queue_idle()
            # 1. Record baseline VRAM and Host RAM before run
            baseline_vram_gb = query_gpu_vram_mb() / 1024.0
            try:
                baseline_advisory = prompt_baseline_advisory(baseline_vram_gb)
                baseline_drift_advisory = pair_baseline_drift_advisory(
                    baseline_vram_gb, previous_result, config_run_count
                )
            except PreflightError as exc:
                print(f"[PREFLIGHT ABORT] {exc}")
                return 1
            baseline_host_ram_gb = query_host_ram_gb()
            print(f"[RESOURCES] Baseline GPU VRAM: {baseline_vram_gb:.2f} GB | Host RAM: {baseline_host_ram_gb:.2f} GB")
            if baseline_advisory["threshold_exceeded"]:
                print(
                    "[PREFLIGHT ABORT] GPU idle: pre-queue absolute baseline "
                    "exceeds 3.0 GiB."
                )
                return 1
            if baseline_drift_advisory.get("measurement_available") is True:
                print(
                    "[ADVISORY, NON-GATING] Cold/warm baseline drift: "
                    f"{baseline_drift_advisory['absolute_drift_gb']:.3f} GiB."
                )

            # 2. Start Resource monitor thread BEFORE /prompt POST
            monitor = ResourceMonitorThread(interval=POLL_INTERVAL_S)
            monitor.start()
            start_time = time.time()

            print(f"Queueing prompt for {recipe_name}...")
            prompt_dict = recipe_data.get("prompt", recipe_data)
            cache_control: Optional[Dict[str, Any]] = None
            if suite_cache_nonce is not None:
                try:
                    prompt_dict, cache_control = apply_suite_cache_nonce(
                        prompt_dict, suite_cache_nonce
                    )
                except ValueError as exc:
                    monitor.stop()
                    print(f"Error: suite cache nonce could not be applied safely: {exc}")
                    return 1
            elif standalone_cache_nonce is not None:
                try:
                    prompt_dict, cache_control = apply_standalone_cache_nonce(
                        prompt_dict, standalone_cache_nonce
                    )
                except ValueError as exc:
                    monitor.stop()
                    print(f"Error: standalone cache nonce could not be applied safely: {exc}")
                    return 1
            queued_prompt_sha256 = stable_identity(prompt_dict)
            prompt_payload = {"prompt": prompt_dict}
            req_data = json.dumps(prompt_payload).encode("utf-8")
            req = urllib.request.Request(f"{COMFY_SERVER_URL}/prompt", data=req_data, headers={"Content-Type": "application/json"})
            try:
                prequeue_known_workload_scan = collect_prequeue_known_workload_scan(
                    server_instance, server_argv
                )
            except PreflightError as exc:
                monitor.stop()
                print(f"[PREFLIGHT ABORT] {exc}")
                return 1
            accepted_prompt = False
            orphan_cleanup: Dict[str, Any] = {}
            prompt_request_started = True
            try:
                with urllib.request.urlopen(req) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    prompt_id = res_json.get("prompt_id")
                    if not prompt_id:
                        raise urllib.error.URLError("/prompt response omitted prompt_id")
                    accepted_prompt = True
                    print(f"Queued successfully (Prompt ID: {prompt_id})")
            except Exception as e:
                monitor.stop()
                orphan_cleanup = shutdown_lab_server()
                prompt_cleanup_proved = orphan_cleanup.get("success") is True
                if orphan_cleanup.get("success") is not True:
                    write_queue_quarantine(
                        "prompt acceptance was uncertain and owned-server shutdown was not proved",
                        {"error": str(e), "cleanup": orphan_cleanup},
                    )
                print(f"Error queueing prompt safely: {e}; cleanup={orphan_cleanup}")
                return 1

            # 3. Poll history until completion (keep monitor running!)
            completed = False
            execution_success = False
            output_path = ""
            target_file = None
            outputs = {}
            messages: Any = []
            while time.time() - start_time < completion_timeout_s:
                time.sleep(0.5)
                try:
                    with urllib.request.urlopen(f"{COMFY_SERVER_URL}/history/{prompt_id}") as hresp:
                        hist = json.loads(hresp.read().decode("utf-8"))
                        if prompt_id in hist:
                            completed = True
                            prompt_terminal_proved = True
                            prompt_hist = hist[prompt_id]
                            status_obj = prompt_hist.get("status", {})
                            status_str = status_obj.get("status_str", "")
                            completed_flag = status_obj.get("completed", False)
                            messages = status_obj.get("messages", [])
                            outputs = prompt_hist.get("outputs", {})
                            
                            has_error = (status_str != "success") or (not completed_flag) or (not outputs)
                            for m in messages:
                                if isinstance(m, (list, tuple)) and len(m) >= 2 and m[0] == "execution_error":
                                    has_error = True
                            
                            if not has_error:
                                output_path = extract_output_path(outputs)
                                
                                if not output_path:
                                    execution_success = False
                                    print(f"[ERROR] Execution for prompt {prompt_id} produced no output artifact (output_path is empty)!")
                                else:
                                    try:
                                        target_file = strict_output_artifact_path(output_path)
                                    except ValueError as exc:
                                        execution_success = False
                                        target_file = None
                                        print(
                                            f"[ERROR] Output file '{output_path}' is not a safe "
                                            f"nonempty artifact under outputs/: {exc}"
                                        )
                                    else:
                                        execution_success = True
                            else:
                                execution_success = False
                                print(f"[ERROR] ComfyUI execution failed for prompt {prompt_id}: status_str='{status_str}', outputs={bool(outputs)} (keys: {list(outputs.keys())}), messages={messages}")
                            break
                except Exception:
                    pass

            duration_s = time.time() - start_time

            # Stop GPU/RAM monitoring immediately after ComfyUI history
            # completes. ffprobe is post-render QA and must not contaminate the
            # measured render peak or leave the monitor alive on probe failure.
            peak_vram_gb, peak_host_ram_gb = monitor.stop()
            cache_evidence = execution_cache_evidence(messages, cache_control)

            if accepted_prompt and not completed:
                orphan_cleanup = shutdown_lab_server()
                prompt_cleanup_proved = orphan_cleanup.get("success") is True
                if orphan_cleanup.get("success") is not True:
                    write_queue_quarantine(
                        "accepted prompt did not reach a terminal history state and cleanup was not proved",
                        {"prompt_id": prompt_id, "cleanup": orphan_cleanup},
                    )

            media_metrics: Dict[str, Any] = {}
            expects_video = any(
                isinstance(node, dict) and node.get("class_type") == "SaveVideo"
                for node in recipe_data.get("prompt", recipe_data).values()
            )
            requires_audio = any(
                isinstance(node, dict)
                and node.get("class_type") == "CreateVideo"
                and "audio" in node.get("inputs", {})
                for node in recipe_data.get("prompt", recipe_data).values()
            )
            if execution_success and target_file is not None:
                media_metrics["artifact_sha256"] = sha256_file(target_file)
                if expects_video:
                    media_metrics.update(probe_media_metrics(target_file))
                    media_metrics.update(timing_receipt_fields(recipe_data, media_metrics))
                    media_metrics.update(bitrate_anomaly_fields(recipe_name, media_metrics, boot_lane_str))
            media_valid = (
                media_artifact_is_valid(
                    media_metrics,
                    recipe_data.get("contract", {}),
                    requires_audio=requires_audio,
                )
                if execution_success and expects_video
                else execution_success
            )
            if media_metrics.get("bitrate_anomaly"):
                print(
                    "[EYEBALL PRIORITY] bitrate-anomaly: video bytes/frame is "
                    f"{media_metrics.get('bitrate_ratio_to_clean_median')}x the clean same-lane median"
                )

            # Ensure peaks are at least baselines
            peak_vram_gb = max(peak_vram_gb, baseline_vram_gb)
            peak_host_ram_gb = max(peak_host_ram_gb, baseline_host_ram_gb)
            vram_receipt = vram_receipt_fields(baseline_vram_gb, peak_vram_gb)

            # 5. Invalid measurement guard: peak <= baseline + 0.2 GB means sampler missed render
            is_measurement_valid = peak_vram_gb > (baseline_vram_gb + 0.2)

            final_provenance = capture_provenance_snapshot(recipe_path, recipe_data)
            final_recipe_sha256 = final_provenance["recipe_sha256"]
            final_runner_sha256 = final_provenance["runner_sha256"]
            final_lab_locks_sha256 = final_provenance["lab_locks_sha256"]
            final_fixture_sha256s = final_provenance["fixture_sha256s"]
            final_audio_receipt_sha256s = final_provenance["audio_receipt_sha256s"]
            final_model_fingerprints = final_provenance["model_fingerprints"]
            final_manager_probe_evidence: Dict[str, Any] = {
                "enabled": False,
                "default_manager_disabled": True,
            }
            manager_probe_unchanged = True
            if queued_manager_probe_evidence.get("enabled") is True:
                try:
                    final_manager_probe_evidence = manager_probe_evidence(
                        recipe_name,
                        server_argv,
                        require_pre_prompt=False,
                    )
                    queued_config_sha = (
                        (queued_manager_probe_evidence.get("advisory_config") or {})
                        .get("snapshot", {})
                        .get("sha256")
                    )
                    final_config_sha = (
                        (final_manager_probe_evidence.get("advisory_config") or {})
                        .get("snapshot", {})
                        .get("sha256")
                    )
                    manager_probe_unchanged = bool(
                        final_manager_probe_evidence.get("valid") is True
                        and manager_probe_identity(final_manager_probe_evidence)
                        == manager_probe_identity(queued_manager_probe_evidence)
                        and final_manager_probe_evidence.get("guard_source")
                        == queued_manager_probe_evidence.get("guard_source")
                        and final_manager_probe_evidence.get("offline_environment")
                        == queued_manager_probe_evidence.get("offline_environment")
                        and final_manager_probe_evidence.get("log_path")
                        == queued_manager_probe_evidence.get("log_path")
                        and int(final_manager_probe_evidence.get("serving_pid") or -1)
                        == int(queued_manager_probe_evidence.get("serving_pid") or -2)
                        and final_config_sha == queued_config_sha
                    )
                    if not manager_probe_unchanged:
                        raise PreflightError(
                            9,
                            "Boot lane",
                            "Manager offline probe identity/config/source changed during render",
                        )
                except PreflightError as exc:
                    manager_probe_unchanged = False
                    final_manager_probe_evidence = {
                        "enabled": True,
                        "valid": False,
                        "error": str(exc),
                    }
                    if not final_provenance["error"]:
                        final_provenance["error"] = str(exc)
            try:
                final_server_instance = verified_server_instance()
                server_instance_unchanged = final_server_instance == server_instance
            except PreflightError as exc:
                final_server_instance = {}
                server_instance_unchanged = False
                if not final_provenance["error"]:
                    final_provenance["error"] = str(exc)
            provenance_unchanged = (
                final_provenance["valid"]
                and final_recipe_sha256 == queued_recipe_sha256
                and final_runner_sha256 == queued_runner_sha256
                and final_lab_locks_sha256 == queued_lab_locks_sha256
                and final_fixture_sha256s == queued_fixture_sha256s
                and final_audio_receipt_sha256s == queued_audio_receipt_sha256s
                and final_model_fingerprints == queued_model_fingerprints
                and manager_probe_unchanged
                and server_instance_unchanged
            )
            if queued_cache_runtime_sha256s:
                try:
                    final_cache_runtime_sha256s = suite_cache_runtime_sha256s()
                except ValueError as exc:
                    final_cache_runtime_sha256s = {}
                    provenance_unchanged = False
                    if not final_provenance["error"]:
                        final_provenance["error"] = str(exc)
                else:
                    if final_cache_runtime_sha256s != queued_cache_runtime_sha256s:
                        provenance_unchanged = False
                        if not final_provenance["error"]:
                            final_provenance["error"] = (
                                "Suite cache runtime sources changed during render"
                            )
            else:
                final_cache_runtime_sha256s = {}

            if queued_standalone_cache_runtime_sha256s:
                try:
                    final_standalone_cache_runtime_sha256s = (
                        standalone_cache_runtime_sha256s()
                    )
                except ValueError as exc:
                    final_standalone_cache_runtime_sha256s = {}
                    provenance_unchanged = False
                    if not final_provenance["error"]:
                        final_provenance["error"] = str(exc)
                else:
                    if (
                        final_standalone_cache_runtime_sha256s
                        != queued_standalone_cache_runtime_sha256s
                    ):
                        provenance_unchanged = False
                        if not final_provenance["error"]:
                            final_provenance["error"] = (
                                "Standalone cache runtime sources changed during render"
                            )
            else:
                final_standalone_cache_runtime_sha256s = {}

            # gate_pass = this run individually passed the VRAM ceiling
            # warm_pass = two consecutive gate passes (the final certification)
            is_marginal = False
            if not completed:
                gate_pass = False
                warm_pass = False
                if orphan_cleanup.get("success") is True:
                    status = (
                        f"TIMEOUT (exceeded {completion_timeout_s}s; owned server shutdown proved)"
                    )
                else:
                    status = "QUARANTINED (accepted prompt cleanup could not be proved)"
            elif not execution_success:
                gate_pass = False
                warm_pass = False
                if not outputs or not output_path:
                    status = "FAIL (no artifact output)"
                else:
                    status = "ERROR (execution error)"
            elif not media_valid:
                gate_pass = False
                warm_pass = False
                status = "FAIL (invalid or undecodable video artifact)"
            elif not provenance_unchanged:
                gate_pass = False
                warm_pass = False
                status = "INVALID (recipe, runner, fixture, model, or server instance changed during render)"
            elif executor_cache_nonce is not None and cache_evidence.get(
                "fresh_execution_proved"
            ) is not True:
                gate_pass = False
                warm_pass = False
                status = "INVALID (sampler/output cache bypass not proved)"
            elif standalone_cache_nonce is not None and is_warm_cache and not set(
                cache_evidence.get("stable_node_ids", [])
            ).issubset(set(cache_evidence.get("cached_node_ids", []))):
                gate_pass = False
                warm_pass = False
                status = "INVALID (warm stable-node cache hits not proved)"
            elif not is_measurement_valid:
                gate_pass = False
                warm_pass = False
                status = "INVALID (sampler missed peak)"
                print(f"[WARNING] Invalid measurement! Peak ({peak_vram_gb:.2f} GB) <= baseline ({baseline_vram_gb:.2f} GB) + 0.2 GB. Refusing PASS.")
            elif peak_vram_gb > VRAM_GATE_GB:
                gate_pass = False
                warm_pass = False
                status = f"FAIL (VRAM {peak_vram_gb:.2f} GB > {VRAM_GATE_GB} GB)"
            elif clamp_target_gib is not None:
                target_limit = clamp_target_gib
                vram_delta = peak_vram_gb - baseline_vram_gb
                if vram_delta > target_limit:
                    gate_pass = False
                    warm_pass = False
                    status = f"FAIL (net VRAM {vram_delta:.2f} GB > clamp {target_limit} GB)"
                else:
                    gate_pass = True
                    warm_pass = is_warm_cache
                    is_marginal = (
                        vram_delta >= (target_limit - 0.25)
                        or peak_vram_gb >= (VRAM_GATE_GB - 0.25)
                    )
                    if is_marginal:
                        status = "PASS (marginal)" if is_warm_cache else "PASS (cold, marginal)"
                    else:
                        status = "PASS" if is_warm_cache else "PASS (cold)"
            else:
                gate_pass = True
                warm_pass = is_warm_cache
                is_marginal = (peak_vram_gb >= (VRAM_GATE_GB - 0.25))
                if is_marginal:
                    status = "PASS (marginal)" if is_warm_cache else "PASS (cold, marginal)"
                else:
                    status = "PASS" if is_warm_cache else "PASS (cold)"

            print(f"\n--- Run Summary ---")
            print(f"Recipe:        {recipe_name}")
            print(f"Run Count:     {run_count} (configuration run {config_run_count}; {'Warm cache' if is_warm_cache else 'Cold cache'})")
            print(f"Baseline VRAM: {vram_receipt['baseline_vram_gb']:.3f} GiB | Host RAM: {baseline_host_ram_gb:.2f} GB")
            print(f"Peak VRAM:     {vram_receipt['absolute_peak_vram_gb']:.3f} GiB (Gate <= {VRAM_GATE_GB} GiB)")
            print(f"Net Peak VRAM: {vram_receipt['net_peak_vram_gb']:.3f} GiB (peak minus this leg's baseline)")
            if vram_receipt["baseline_lane_stamp"] is not None:
                print(f"Baseline Lane: {vram_receipt['baseline_lane_stamp']}")
            print(f"Peak Host RAM: {peak_host_ram_gb:.2f} GB")
            print(f"Wall Clock:    {duration_s:.1f} s")
            print(f"Boot Lane:     {boot_lane_str}")
            print(f"Status:        {status}")

            iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            res_payload = {
                "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
                "recipe": recipe_name,
                "run_number": run_count,
                "config_run_count": config_run_count,
                "completion_timeout_s": completion_timeout_s,
                "status": status,
                "gate_pass": gate_pass,
                "pass": warm_pass,
                "warm_pass": warm_pass,
                "marginal": is_marginal,
                "eyeball": "pending",
                "requires_human_eyeball": requires_human_eyeball,
                "promotion_ready": promotion_ready_for_run(
                    warm_pass, is_marginal, requires_human_eyeball
                ),
                "certification_scope": "machine-only" if requires_human_eyeball else "machine",
                "recipe_sha256": queued_recipe_sha256,
                "runner_sha256": queued_runner_sha256,
                "lab_locks_sha256": queued_lab_locks_sha256,
                "fixture_sha256s": queued_fixture_sha256s,
                "audio_receipt_sha256s": queued_audio_receipt_sha256s,
                "model_fingerprints": queued_model_fingerprints,
                "provenance_unchanged": provenance_unchanged,
                "provenance_validation_error": final_provenance["error"],
                "run_identity_sha256": run_identity_sha256,
                "identity": identity_payload,
                "queued_prompt_sha256": queued_prompt_sha256,
                "execution_cache_control": cache_evidence,
                "operator_idle_policy": operator_idle_policy_contract(),
                PREQUEUE_WORKLOAD_SCAN_CONTRACT_KEY: (
                    prequeue_known_workload_scan_contract()
                ),
                PREQUEUE_WORKLOAD_SCAN_EVIDENCE_KEY: prequeue_known_workload_scan,
                "preboot_gpu_idle_gate_contract": queued_gpu_idle_gate_contract,
                GPU_IDLE_EVIDENCE_KEY: queued_preboot_gpu_idle_gate,
                GPU_IDLE_SIDECAR_KEY: queued_preboot_gpu_idle_gate_sidecar,
                "manager_offline_probe": {
                    "pre_queue": queued_manager_probe_evidence,
                    "post_render": final_manager_probe_evidence,
                    "provenance_unchanged": manager_probe_unchanged,
                },
                "suite_cache_runtime_sha256s": queued_cache_runtime_sha256s,
                "final_suite_cache_runtime_sha256s": final_cache_runtime_sha256s,
                "standalone_cache_runtime_sha256s": queued_standalone_cache_runtime_sha256s,
                "final_standalone_cache_runtime_sha256s": (
                    final_standalone_cache_runtime_sha256s
                ),
                "git_commit": repo_git_commit,
                "git_dirty": repo_git_dirty,
                "comfyui_git_commit": comfyui_git_commit,
                "server_argv": server_argv,
                "server_instance": server_instance,
                "final_server_instance": final_server_instance,
                "server_instance_unchanged": server_instance_unchanged,
                "clamp_target_gib": clamp_target_gib,
                "reserve_vram_gib": reserve_vram_gib,
                "physical_total_vram_gib": physical_total_vram_gib,
                **vram_receipt,
                "baseline_advisory": baseline_advisory,
                "cold_warm_baseline_drift_advisory": baseline_drift_advisory,
                "peak_host_ram_gb": round(peak_host_ram_gb, 2),
                "baseline_host_ram_gb": round(baseline_host_ram_gb, 2),
                "duration_s": round(duration_s, 1),
                "output_path": output_path,
                "boot_lane": boot_lane_str,
                "timestamp": iso_timestamp,
                "prompt_id": prompt_id,
                "valid_measurement": is_measurement_valid,
                "run_count": run_count,
                "blocked": False,
                "accepted_prompt": accepted_prompt,
                "orphan_cleanup": orphan_cleanup,
                **media_metrics,
                **pending_human_audio_fields(recipe_data),
            }
            final_history = audit_run_history(RESULTS_DIR, recipe_name)
            if (
                final_history["max_run_number"] != initial_history["max_run_number"]
                or final_history["current_bytes"] != initial_history["current_bytes"]
            ):
                raise ReceiptHistoryError(
                    f"Receipt history changed during run for {recipe_name}; refusing to overwrite evidence"
                )
            run_receipt_file = initial_history["next_archive_path"]
            if run_count != initial_history["next_run_number"]:
                raise ReceiptHistoryError(
                    f"Allocated run {run_count} disagrees with audited next run "
                    f"{initial_history['next_run_number']}"
                )
            write_run_receipts_atomic(res_payload, run_receipt_file, result_file)

            display_status = status
            if requires_human_eyeball and gate_pass:
                display_status += " (machine; human pending)"
            ledger_note = f"Run #{run_count}; boot lane: {boot_lane_str}"
            if executor_cache_nonce is not None:
                ledger_note += "; executor cache nonce"
                if cache_evidence.get("fresh_execution_proved") is True:
                    ledger_note += "; sampler/output execution proved"
                else:
                    ledger_note += "; sampler/output execution unproved"
            if media_metrics.get("bitrate_anomaly"):
                ledger_note += "; bitrate-anomaly (priority eyeball, non-gating)"
            if vram_receipt["baseline_lane_stamp"] is not None:
                ledger_note += f"; {vram_receipt['baseline_lane_stamp']}"
            if baseline_advisory["threshold_exceeded"]:
                ledger_note += "; baseline >3.0 GiB advisory (non-gating)"
            if baseline_drift_advisory.get("threshold_exceeded") is True:
                ledger_note += "; cold/warm baseline drift >0.5 GiB advisory (non-gating)"
            update_results_ledger(recipe_name, display_status, peak_vram_gb, baseline_vram_gb, duration_s, ledger_note)
            matrix_note = f"Measured on box ({display_status})"
            if media_metrics.get("bitrate_anomaly"):
                matrix_note += "; bitrate-anomaly"
            if vram_receipt["baseline_lane_stamp"] is not None:
                matrix_note += f"; {vram_receipt['baseline_lane_stamp']}"
            if baseline_advisory["threshold_exceeded"]:
                matrix_note += "; baseline >3.0 GiB advisory (non-gating)"
            if baseline_drift_advisory.get("threshold_exceeded") is True:
                matrix_note += "; baseline drift >0.5 GiB advisory (non-gating)"
            pass_consecutive = "2/2" if warm_pass else ("1/2" if gate_pass else "0/2")
            update_engine_matrix_beta(
                recipe_name,
                tier,
                display_status,
                peak_vram_gb,
                duration_s,
                "yes",
                pass_consecutive,
                boot_lane_str,
                matrix_note,
            )
    finally:
        owns_coordinator = lock_manager is not None and lock_manager.acquired
        if prompt_request_started and not prompt_terminal_proved and not prompt_cleanup_proved and owns_coordinator:
            emergency_cleanup = shutdown_lab_server()
            prompt_cleanup_proved = emergency_cleanup.get("success") is True
            if not prompt_cleanup_proved:
                write_queue_quarantine(
                    "prompt request started but terminal completion and emergency cleanup were not proved",
                    {"cleanup": emergency_cleanup},
                )
        if suite_parent_watchdog is not None:
            suite_parent_watchdog.stop()
        if do_shutdown and owns_coordinator and not is_suite:
            shutdown_lab_server()
        elif do_shutdown and not owns_coordinator:
            print("[SERVER] Skipping shutdown because this runner never acquired the coordinator")
        elif do_shutdown and is_suite:
            print("[SERVER] Suite child leaves shutdown to its coordinator-owning parent")
        if lock_manager is not None:
            lock_manager.release()


if __name__ == "__main__":
    raise SystemExit(main())
