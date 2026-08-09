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
import hashlib
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
# Desktop composition fluctuates around 2.5 GB on this workstation. This is
# only a pre-boot contention check; the independent 14.5 GB peak gate remains
# authoritative for render safety and certification.
VRAM_GPU_IDLE_MAX_MB = 3072  # 3.0 GB pre-boot desktop threshold
MIN_FREE_DISK_GB = 5.0
BOOT_TIMEOUT_S = 120
POLL_INTERVAL_S = 0.2  # 200ms VRAM polling interval
REQUIRED_CUSTOM_NODE_WHITELIST = frozenset({"ComfyUI-GGUF", "ComfyUI-KJNodes"})
SUITE_CACHE_NONCE_INPUT = "_vram_lab_cache_nonce"
SUITE_CACHE_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
SUITE_CACHE_RUNTIME_SOURCES = {
    "execution.py": "dcac4074826ac9121624ad113f6027684650579da626e24a4011617aae5f3fc0",
    "comfy_execution/caching.py": "26b5b768dff3f2e6fe8279aa6ff645dd87b698d4610744f848a85b1ab543e3a4",
    "comfy_extras/nodes_custom_sampler.py": "3fb59bf45aaf19b2f87099b559c789f94716a90088c6c4ac8a85c53b3c99c59b",
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


class PreflightError(Exception):
    """Raised when a preflight check fails."""
    def __init__(self, check_num: int, name: str, reason: str):
        self.check_num = check_num
        self.name = name
        self.reason = reason
        super().__init__(f"Preflight Check #{check_num} [{name}] FAILED: {reason}")


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
    if SERVER_PID_FILE.exists():
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
    """Remove a stale PID receipt only after both process and port are proved clear."""
    if not SERVER_PID_FILE.exists():
        return False
    try:
        pid = int(SERVER_PID_FILE.read_text(encoding="utf-8-sig").strip())
        if pid <= 0:
            raise ValueError("PID must be positive")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[SERVER] Keeping unverifiable .server.pid receipt: {exc}")
        return False
    if psutil.pid_exists(pid):
        return False
    if query_server_stats() or listener_pid(int(LAB_PORT)) is not None:
        print(
            f"[SERVER] Recorded PID {pid} is gone but port {LAB_PORT} is not proved clear; "
            "keeping .server.pid."
        )
        return False
    try:
        SERVER_PID_FILE.unlink()
    except OSError as exc:
        print(f"[SERVER] Could not remove proved-stale .server.pid: {exc}")
        return False
    print(f"[SERVER] Removed proved-stale .server.pid for dead PID {pid}")
    return True


def check_gpu_idle() -> float:
    """Preflight Check #2: Refuse unexpectedly high unrelated desktop GPU load."""
    try:
        used_mb = query_gpu_vram_mb()
        max_limit_mb = float(VRAM_GPU_IDLE_MAX_MB)

        if used_mb >= max_limit_mb:
            raise PreflightError(2, "GPU idle", f"GPU allocated VRAM is {used_mb:.1f} MB (exceeds pre-boot desktop threshold {max_limit_mb:.0f} MB)")
        return used_mb / 1024.0
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        if isinstance(e, PreflightError):
            raise
        raise PreflightError(2, "GPU idle", f"Could not query nvidia-smi: {e}")


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


def listener_pid(port: int) -> Optional[int]:
    """Return the PID listening on the local lab port when psutil can resolve it."""
    try:
        for connection in psutil.net_connections(kind="inet"):
            local = connection.laddr
            local_port = getattr(local, "port", local[1] if len(local) > 1 else None) if local else None
            if connection.status == psutil.CONN_LISTEN and local_port == port:
                return connection.pid
    except (psutil.AccessDenied, OSError):
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


def boot_lab_server() -> Dict[str, Any]:
    """Boot lab server headlessly via boot_lab_server.cmd and wait for health-check."""
    if not BOOT_CMD.exists():
        raise PreflightError(3, "Server up", f"boot_lab_server.cmd missing at {BOOT_CMD}")

    cleanup_stale_pid_receipt()
    if SERVER_PID_FILE.exists():
        raise PreflightError(
            3,
            "Server up",
            "An existing .server.pid receipt could not be proved stale; refusing to overwrite it",
        )
    print(f"[SERVER] Launching lab server via {BOOT_CMD.name} on port {LAB_PORT}...")
    
    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(
        ["cmd.exe", "/c", str(BOOT_CMD)],
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
        if SERVER_LOG_FILE.exists():
            try:
                log_lines = SERVER_LOG_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                log_tail = "\n".join(log_lines[-15:])
            except Exception as e:
                log_tail = f"(Could not read server.log: {e})"

        raise PreflightError(3, "Server up", f"Lab server failed to boot on port {LAB_PORT} within 120s.\nTail of server.log:\n{log_tail}")
    except Exception:
        terminated = terminate_owned_process_tree(proc.pid)
        if terminated and SERVER_PID_FILE.exists():
            SERVER_PID_FILE.unlink(missing_ok=True)
        elif not terminated:
            print(
                f"[SERVER] Boot cleanup could not prove PID {proc.pid} exited; "
                "keeping .server.pid for manual inspection."
            )
        raise


def check_server_up_and_ownership() -> Dict[str, Any]:
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
            return stats
        else:
            raise PreflightError(
                3, "Server up",
                f"Unrecognized server already answering on port {LAB_PORT} without valid PID receipt. Refusing to adopt or kill it."
            )

    if pid_receipt or SERVER_PID_FILE.exists():
        raise PreflightError(
            3,
            "Server up",
            f"A PID receipt ({pid_receipt or 'unverifiable'}) exists but no verified lab server answers on port {LAB_PORT}. Refusing to overwrite the receipt.",
        )

    check_gpu_idle()
    print("  [OK] Check 2: GPU below the pre-boot desktop threshold")
    stats = boot_lab_server()
    ensure_queue_idle()
    return stats


def shutdown_lab_server() -> Dict[str, Any]:
    """Stop the verified lab server and return machine-checkable cleanup proof.

    The PID receipt is deliberately retained whenever identity, termination, or
    listener shutdown cannot be proved.  A caller may therefore make its own
    PASS conditional on ``result["success"]`` without parsing console text.
    """
    result: Dict[str, Any] = {
        "success": False,
        "had_receipt": SERVER_PID_FILE.exists(),
        "pid": None,
        "pid_verified": False,
        "termination_attempted": False,
        "termination_reported_success": False,
        "process_exited": False,
        "listener_exited": False,
        "receipt_removed": False,
        "reason": "",
    }

    if not SERVER_PID_FILE.exists():
        live_stats = query_server_stats()
        serving_pid = listener_pid(int(LAB_PORT))
        if live_stats or serving_pid is not None:
            result["reason"] = "port 8199 is live without an owned PID receipt"
            print(f"[SERVER] {result['reason']}; refusing cleanup.")
            return result
        result.update(
            success=True,
            process_exited=True,
            listener_exited=True,
            reason="no owned server receipt and no live listener",
        )
        return result

    try:
        text = SERVER_PID_FILE.read_text(encoding="utf-8-sig").strip()
        pid = int(text)
        if pid <= 0:
            raise ValueError("PID must be positive")
    except (OSError, UnicodeError, ValueError) as exc:
        result["reason"] = f"could not verify .server.pid: {exc}"
        print(f"[SERVER] {result['reason']}; keeping receipt.")
        return result
    result["pid"] = pid

    if not psutil.pid_exists(pid):
        live_stats = query_server_stats()
        serving_pid = listener_pid(int(LAB_PORT))
        if live_stats or serving_pid is not None:
            result["reason"] = (
                f"recorded PID {pid} is gone but port {LAB_PORT} still has an unverified server"
            )
            print(f"[SERVER] {result['reason']}; keeping receipt.")
            return result
        result["process_exited"] = True
        result["listener_exited"] = True
        try:
            SERVER_PID_FILE.unlink()
        except OSError as exc:
            result["reason"] = f"server already exited but PID receipt removal failed: {exc}"
            print(f"[SERVER] {result['reason']}")
            return result
        result.update(
            success=True,
            receipt_removed=True,
            reason="recorded server was already stopped and port is clear",
        )
        print(f"[SERVER] Confirmed stale PID {pid} is gone; removed .server.pid receipt.")
        return result

    if not is_expected_lab_server_pid(pid):
        result["reason"] = f"recorded PID {pid} failed lab command-line verification"
        print(f"[SERVER] {result['reason']}; keeping receipt.")
        return result
    result["pid_verified"] = True

    serving_pid = listener_pid(int(LAB_PORT))
    live_stats = query_server_stats()
    if serving_pid not in (None, pid) or (live_stats and serving_pid != pid):
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
    result["listener_exited"] = post_listener is None and not post_stats

    if not (terminated and result["process_exited"] and result["listener_exited"]):
        result["reason"] = (
            f"shutdown proof failed (terminated={terminated}, "
            f"process_exited={result['process_exited']}, listener_exited={result['listener_exited']})"
        )
        print(f"[SERVER] {result['reason']}; keeping .server.pid.")
        return result

    try:
        SERVER_PID_FILE.unlink()
    except OSError as exc:
        result["reason"] = f"server exited but PID receipt removal failed: {exc}"
        print(f"[SERVER] {result['reason']}")
        return result
    result.update(
        success=True,
        receipt_removed=True,
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


def check_boot_lane(recipe_name: str, system_stats: Dict[str, Any]):
    """Preflight Check #9: Confirm the isolated, offline, Sage-free lab lane."""
    argv = system_stats.get("system", {}).get("argv", [])
    if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
        raise PreflightError(9, "Boot lane", "Live server argv must be a list of strings")
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
    if any("comfyui-manager" in value.lower() for value in argv):
        raise PreflightError(
            9,
            "Boot lane",
            "ComfyUI-Manager is forbidden in the offline lab boot lane",
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
    if (
        len(whitelist_values) != len(REQUIRED_CUSTOM_NODE_WHITELIST)
        or set(whitelist_values) != REQUIRED_CUSTOM_NODE_WHITELIST
    ):
        raise PreflightError(
            9,
            "Boot lane",
            "Live server custom-node whitelist must contain exactly "
            f"{sorted(REQUIRED_CUSTOM_NODE_WHITELIST)}; found {whitelist_values}",
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
):
    """Run all 10 preflight safety and validity checks before acquiring lock."""
    print(f"--- Running Preflight Checks for {recipe_name} ---")

    print("  [OK] Check 1: Atomic GPU lock held by this runner")
    system_stats = check_server_up_and_ownership()
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

    check_boot_lane(recipe_name, system_stats)
    print("  [OK] Check 9: Boot lane verified (lab-8199, sage-free)")

    check_disk_space()
    print("  [OK] Check 10: Output disk space >= 5 GB")
    print("--- Preflight Complete: ALL CHECKS PASSED ---\n")
    return system_stats, queued_fixture_sha256s, queued_audio_receipt_sha256s


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
        print("Usage: python run_recipe.py <path_to_recipe.json> [--suite] [--shutdown]")
        sys.exit(1)

    recipe_path = Path(sys.argv[1]).resolve()
    is_suite = "--suite" in sys.argv
    do_shutdown = "--shutdown" in sys.argv
    is_force = "--force" in sys.argv
    tier = "suite" if is_suite else "smoke"
    try:
        suite_cache_nonce = parse_suite_cache_nonce(sys.argv, is_suite)
    except ValueError as exc:
        print(f"Error: invalid suite cache control: {exc}")
        return 2
    
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
        requires_human_eyeball = recipe_data.get("contract", {}).get("engine") == "minimax_h3"

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
        except ValueError as exc:
            print(f"Error: suite cache runtime contract is not frozen: {exc}")
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
            system_stats, queued_fixture_sha256s, queued_audio_receipt_sha256s = run_all_preflights(
                recipe_path,
                recipe_data,
                recipe_name,
                queued_recipe_sha256,
                boot_lane_str,
                is_force=is_force,
            )
        except PreflightError as e:
            print(f"\n[PREFLIGHT ABORT] {e}")
            sys.exit(1)

        comfyui_git_commit = git_commit(COMFYUI_ROOT)
        queued_model_fingerprints = model_fingerprints(recipe_data)
        server_argv = system_stats.get("system", {}).get("argv", [])
        server_instance = verified_server_instance()
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
        }
        if queued_cache_runtime_sha256s:
            # The nonce value is deliberately excluded: it is executor metadata,
            # not declared recipe state.  The pinned runtime semantics are part
            # of identity, while the recipe SHA continues to bind noise_seed.
            identity_payload["suite_cache_runtime_sha256s"] = queued_cache_runtime_sha256s
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
            baseline_host_ram_gb = query_host_ram_gb()
            print(f"[RESOURCES] Baseline GPU VRAM: {baseline_vram_gb:.2f} GB | Host RAM: {baseline_host_ram_gb:.2f} GB")

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
            queued_prompt_sha256 = stable_identity(prompt_dict)
            prompt_payload = {"prompt": prompt_dict}
            req_data = json.dumps(prompt_payload).encode("utf-8")
            req = urllib.request.Request(f"{COMFY_SERVER_URL}/prompt", data=req_data, headers={"Content-Type": "application/json"})
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
            RUNNER_COMPLETION_TIMEOUT_S = 1800
            while time.time() - start_time < RUNNER_COMPLETION_TIMEOUT_S:  # 1800s (30 min) completion window
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

            # 5. Invalid measurement guard: peak <= baseline + 0.2 GB means sampler missed render
            is_measurement_valid = peak_vram_gb > (baseline_vram_gb + 0.2)

            final_provenance = capture_provenance_snapshot(recipe_path, recipe_data)
            final_recipe_sha256 = final_provenance["recipe_sha256"]
            final_runner_sha256 = final_provenance["runner_sha256"]
            final_lab_locks_sha256 = final_provenance["lab_locks_sha256"]
            final_fixture_sha256s = final_provenance["fixture_sha256s"]
            final_audio_receipt_sha256s = final_provenance["audio_receipt_sha256s"]
            final_model_fingerprints = final_provenance["model_fingerprints"]
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

            # gate_pass = this run individually passed the VRAM ceiling
            # warm_pass = two consecutive gate passes (the final certification)
            is_marginal = False
            if not completed:
                gate_pass = False
                warm_pass = False
                if orphan_cleanup.get("success") is True:
                    status = (
                        f"TIMEOUT (exceeded {RUNNER_COMPLETION_TIMEOUT_S}s; owned server shutdown proved)"
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
            elif suite_cache_nonce is not None and cache_evidence.get(
                "fresh_execution_proved"
            ) is not True:
                gate_pass = False
                warm_pass = False
                status = "INVALID (suite sampler/output cache bypass not proved)"
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
            print(f"Baseline VRAM: {baseline_vram_gb:.2f} GB | Host RAM: {baseline_host_ram_gb:.2f} GB")
            print(f"Peak VRAM:     {peak_vram_gb:.2f} GB (Gate <= {VRAM_GATE_GB} GB)")
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
                "suite_cache_runtime_sha256s": queued_cache_runtime_sha256s,
                "final_suite_cache_runtime_sha256s": final_cache_runtime_sha256s,
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
                "peak_vram_gb": round(peak_vram_gb, 2),
                "baseline_vram_gb": round(baseline_vram_gb, 2),
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
            if suite_cache_nonce is not None:
                ledger_note += "; executor cache nonce; sampler/output execution proved"
            if media_metrics.get("bitrate_anomaly"):
                ledger_note += "; bitrate-anomaly (priority eyeball, non-gating)"
            update_results_ledger(recipe_name, display_status, peak_vram_gb, baseline_vram_gb, duration_s, ledger_note)
            matrix_note = f"Measured on box ({display_status})"
            if media_metrics.get("bitrate_anomaly"):
                matrix_note += "; bitrate-anomaly"
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
