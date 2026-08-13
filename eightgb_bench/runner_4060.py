#!/usr/bin/env python3
"""Direct-argv runner for the isolated physical RTX 4060 H3 bench.

This is intentionally a new execution surface.  It never imports the 5080
runner, its lock implementation, Front Office, or the top-level results tree.
The only supported workload is the small native-audio H3 MIME cell described
by the checked-in physical-4060 plan.  All mutable state lives under the
ignored ``eightgb_bench/local`` namespace in the laptop checkout.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psutil

try:  # supports both ``python -m`` and direct script invocation
    from . import preflight_4060 as inventory
    from .locks_4060 import BenchLease, LeaseError
except ImportError:  # pragma: no cover - exercised on the laptop direct path
    import preflight_4060 as inventory
    from locks_4060 import BenchLease, LeaseError


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = REPO_ROOT / "eightgb_bench"
LOCAL_ROOT = BENCH_ROOT / "local"
CONTRACT_PATH = BENCH_ROOT / "contract-v1.json"
PLAN_PATH = BENCH_ROOT / "plans" / "h3_mime_i2v_864x480_f90.json"
LAUNCH_CONFIG_PATH = LOCAL_ROOT / "runner-4060-launch.json"
RUNNER_PATH = Path(__file__).resolve()

SCOPE = "PHYSICAL_4060_8GB_EXPLORATORY_NOT_5080_CERTIFICATION"
PROFILE_ID = "physical-rtx4060-8gb"
PLAN_ID = "h3-mime-i2v-864x480-f90"
PORT = 18299
LISTENER = "127.0.0.1"
SERVER_URL = f"http://{LISTENER}:{PORT}"
COMFY032_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
KJ_COMMIT = "b7646ad70a7daa7aeb919ca542274758d26ba2df"
SEQUENCE = ("cold", "warm-1", "warm-2")
POLL_INTERVAL_S = 0.2
STARTUP_TIMEOUT_S = 180
COMPLETION_TIMEOUT_S = 1800
PREBOOT_MAX_VRAM_GIB = 0.5
PREBOOT_MIN_HOST_AVAILABLE_GIB = 8.0
CACHE_NONCE_INPUT = "_physical_4060_cache_nonce"
CACHE_NONCE_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
CACHE_RUNTIME_SOURCES = {
    "execution.py": "dcac4074826ac9121624ad113f6027684650579da626e24a4011617aae5f3fc0",
    "comfy_execution/caching.py": "26b5b768dff3f2e6fe8279aa6ff645dd87b698d4610744f848a85b1ab543e3a4",
    "comfy_extras/nodes_custom_sampler.py": "13892ff513b2fce19d480cf5ed461d7619ab5b39e6915716ee6d21de05b81a28",
    "comfy_api/latest/_io.py": "495aefa059aad4eed4181aa7fbb415679d3f269651e9fc6f542bdac1b99dd40f",
}


class RunnerError(RuntimeError):
    """A physical-4060 admission or run gate failed."""


def canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_utf8_text_file(path: Path) -> str:
    """Normalize line endings only for checked-in UTF-8 text identity inputs."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RunnerError(f"cannot read checked-in UTF-8 text file {path}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RunnerError(f"checked-in UTF-8 text file has a BOM: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunnerError(f"checked-in UTF-8 text file is not UTF-8: {path}") from exc
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RunnerError(f"{label} cannot be read: {path}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RunnerError(f"{label} has a UTF-8 BOM: {path}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"{label} is not UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"{label} must be a JSON object: {path}")
    return value


def _require_exact_keys(value: Mapping[str, Any], allowed: Iterable[str], label: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    missing = sorted(set(allowed) - set(value))
    if unknown or missing:
        fragments = []
        if unknown:
            fragments.append(f"unknown keys: {', '.join(unknown)}")
        if missing:
            fragments.append(f"missing keys: {', '.join(missing)}")
        raise RunnerError(f"{label} has {'; '.join(fragments)}")


def _require_string(value: Mapping[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise RunnerError(f"{label}.{key} must be a nonblank string")
    return result


def _require_bool(value: Mapping[str, Any], key: str, label: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise RunnerError(f"{label}.{key} must be a boolean")
    return result


def _require_int(value: Mapping[str, Any], key: str, label: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise RunnerError(f"{label}.{key} must be an integer")
    return result


def _safe_local_root(*, create: bool) -> Path:
    try:
        return inventory._validated_local_root(create=create)
    except inventory.PreflightError as exc:
        raise RunnerError(str(exc)) from exc


def _safe_local_child(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as exc:
        raise RunnerError(f"cannot resolve local 4060 namespace: {exc}") from exc
    if not resolved_candidate.is_relative_to(resolved_root):
        raise RunnerError("derived path escaped eightgb_bench/local")
    return candidate


def _write_exclusive_json(path: Path, payload: Mapping[str, Any]) -> str:
    data = canonical_bytes(dict(payload))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise RunnerError(f"immutable receipt already exists: {path}") from exc
    return hashlib.sha256(data).hexdigest()


def _json_path_text(path: Path) -> str:
    """Use a JSON scalar as a safe YAML quoted string without a YAML library."""
    return json.dumps(str(path).replace("\\", "/"), ensure_ascii=False)


def load_plan() -> tuple[dict[str, Any], str]:
    plan = _read_json(PLAN_PATH, "physical 4060 plan")
    if plan.get("schema_version") != 1 or plan.get("id") != PLAN_ID:
        raise RunnerError("checked-in physical plan identity drifted")
    if plan.get("scope") != SCOPE:
        raise RunnerError("physical plan scope drifted")
    return plan, sha256_utf8_text_file(PLAN_PATH)


def load_launch_config(profile_id: str) -> tuple[dict[str, Any], str]:
    local_root = _safe_local_root(create=False)
    expected = local_root / "runner-4060-launch.json"
    try:
        config_path = inventory._validated_path(str(expected), "4060 launch config", "file")
    except inventory.PreflightError as exc:
        raise RunnerError(str(exc)) from exc
    config = _read_json(config_path, "4060 launch config")
    _require_exact_keys(config, {"schema_version", "profile_id", "plan_id", "port", "comfyui", "kjnodes", "policy"}, "launch config")
    if _require_int(config, "schema_version", "launch config") != 1:
        raise RunnerError("launch config schema_version must be 1")
    if _require_string(config, "profile_id", "launch config") != profile_id:
        raise RunnerError("launch config may select only the enrolled profile")
    if _require_string(config, "plan_id", "launch config") != PLAN_ID:
        raise RunnerError("launch config may select only the H3 MIME plan")
    if _require_int(config, "port", "launch config") != PORT:
        raise RunnerError(f"launch config port must be the isolated {PORT}")
    comfy = config.get("comfyui")
    if not isinstance(comfy, dict):
        raise RunnerError("launch config.comfyui must be an object")
    _require_exact_keys(comfy, {"version", "git_commit"}, "launch config.comfyui")
    if _require_string(comfy, "version", "launch config.comfyui") != "0.32.0":
        raise RunnerError("physical H3 runner requires ComfyUI version 0.32.0")
    if _require_string(comfy, "git_commit", "launch config.comfyui") != COMFY032_COMMIT:
        raise RunnerError("physical H3 runner requires the declared 0.32.0 commit")
    kjnodes = config.get("kjnodes")
    if not isinstance(kjnodes, dict):
        raise RunnerError("launch config.kjnodes must be an object")
    _require_exact_keys(kjnodes, {"root", "git_commit", "init_py_sha256"}, "launch config.kjnodes")
    _require_string(kjnodes, "root", "launch config.kjnodes")
    if _require_string(kjnodes, "git_commit", "launch config.kjnodes") != KJ_COMMIT:
        raise RunnerError("physical H3 runner requires the declared KJNodes commit")
    init_hash = _require_string(kjnodes, "init_py_sha256", "launch config.kjnodes")
    if re.fullmatch(r"[0-9a-f]{64}", init_hash) is None:
        raise RunnerError("launch config.kjnodes.init_py_sha256 must be lowercase SHA-256")
    policy = config.get("policy")
    if not isinstance(policy, dict):
        raise RunnerError("launch config.policy must be an object")
    _require_exact_keys(policy, {"listener", "sage_attention", "manager", "reserve_vram", "pinned_memory", "network"}, "launch config.policy")
    if _require_string(policy, "listener", "launch config.policy") != LISTENER:
        raise RunnerError("physical runner listener must be loopback")
    if _require_bool(policy, "sage_attention", "launch config.policy") is not False:
        raise RunnerError("SageAttention is forbidden in the physical H3 lane")
    if _require_bool(policy, "manager", "launch config.policy") is not False:
        raise RunnerError("ComfyUI-Manager is forbidden in the physical H3 lane")
    if _require_string(policy, "reserve_vram", "launch config.policy") != "forbidden":
        raise RunnerError("reserve-vram is forbidden in the physical H3 lane")
    if _require_string(policy, "pinned_memory", "launch config.policy") != "disabled":
        raise RunnerError("pinned memory must be disabled in the physical H3 lane")
    if _require_string(policy, "network", "launch config.policy") != "offline":
        raise RunnerError("physical H3 lane must retain offline policy")
    return config, sha256_file(config_path)


def _profile_payload(profile_id: str) -> tuple[dict[str, Any], Path, str]:
    try:
        local_root = inventory._validated_local_root(create=False)
        profile_path = inventory._validated_path(
            str(inventory._profile_path(profile_id, local_root)), "laptop-local profile", "file"
        )
    except inventory.PreflightError as exc:
        raise RunnerError(str(exc)) from exc
    profile = _read_json(profile_path, "laptop-local profile")
    return profile, profile_path, sha256_file(profile_path)


def _git_identity(root: Path, label: str) -> dict[str, Any]:
    try:
        observed = inventory._git_identity(root)
    except inventory.PreflightError as exc:
        raise RunnerError(f"{label} identity failed: {exc}") from exc
    return observed


def cache_runtime_sha256s(comfy_root: Path) -> dict[str, str]:
    """Pin the 0.32 cache/input-filter behavior behind the execution nonce."""
    observed: dict[str, str] = {}
    for relative_name, expected_hash in CACHE_RUNTIME_SOURCES.items():
        source = comfy_root / Path(relative_name)
        try:
            checked = inventory._validated_path(str(source), f"cache runtime source {relative_name}", "file")
        except inventory.PreflightError as exc:
            raise RunnerError(str(exc)) from exc
        actual_hash = sha256_file(checked)
        if actual_hash != expected_hash:
            raise RunnerError(
                f"cache runtime source drifted for {relative_name}; a fresh nonce audit is required"
            )
        observed[relative_name] = actual_hash
    return observed


def verify_model_manifest(
    plan: Mapping[str, Any],
    model_roots: Mapping[str, Path],
    expected_model_hashes: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Hash every admitted model against the enrolled local profile identity."""
    assets = plan.get("engine", {}).get("required_assets")
    if not isinstance(assets, list):
        raise RunnerError("physical plan required assets are malformed")
    manifest: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, Mapping):
            raise RunnerError("physical plan contains a malformed required asset")
        category = asset.get("category")
        filename = asset.get("filename")
        expected_bytes = asset.get("expected_bytes")
        if (
            not isinstance(category, str)
            or not isinstance(filename, str)
            or isinstance(expected_bytes, bool)
            or not isinstance(expected_bytes, int)
        ):
            raise RunnerError("physical plan model asset is malformed")
        root = model_roots.get(category)
        if root is None:
            raise RunnerError(f"profile omitted required model root {category}")
        try:
            model = inventory._validated_path(
                str(root / filename), f"required model {filename}", "file"
            )
        except inventory.PreflightError as exc:
            raise RunnerError(str(exc)) from exc
        if model.stat().st_size != expected_bytes:
            raise RunnerError(f"model bytes drifted for {filename}")
        expected_hash = expected_model_hashes.get(f"{category}/{filename}")
        actual_hash = sha256_file(model)
        if not isinstance(expected_hash, str) or not expected_hash or actual_hash != expected_hash:
            raise RunnerError(f"model SHA-256 drifted for {filename}")
        manifest.append(
            {
                "category": category,
                "filename": filename,
                "bytes": model.stat().st_size,
                "sha256": actual_hash,
            }
        )
    return manifest


def validate_admission_inputs(profile_id: str) -> dict[str, Any]:
    """Do every non-server admission check before any process starts."""
    if profile_id != PROFILE_ID:
        raise RunnerError("only physical-rtx4060-8gb is enrolled")
    plan, plan_hash = load_plan()
    launch, launch_hash = load_launch_config(profile_id)
    profile, profile_path, profile_hash = _profile_payload(profile_id)
    try:
        inventory._validate_profile(profile, profile_id)
        preflight = inventory.preflight(profile_id)
    except inventory.PreflightError as exc:
        raise RunnerError(f"laptop-local profile preflight failed: {exc}") from exc
    if preflight.get("status") != inventory.READY_STATUS:
        raise RunnerError(
            "laptop-local profile is not ready for human boot approval: "
            f"{preflight.get('status')} {preflight.get('blockers')}"
        )
    identity = profile.get("identity")
    if not isinstance(identity, dict) or identity.get("comfyui_git_commit") != COMFY032_COMMIT:
        raise RunnerError("profile does not pin the required 0.32.0 ComfyUI commit")
    paths = profile.get("paths")
    if not isinstance(paths, dict) or not isinstance(paths.get("model_roots"), dict):
        raise RunnerError("profile paths are malformed after preflight")
    try:
        python = inventory._validated_path(paths["python"], "profile Python", "file")
        comfy_root = inventory._validated_path(paths["comfyui_root"], "profile ComfyUI root", "directory")
        ffprobe = inventory._validated_ffprobe(paths["ffprobe"], "profile ffprobe")
        model_roots = {
            name: inventory._validated_path(value, f"profile model root {name}", "directory")
            for name, value in paths["model_roots"].items()
        }
        kjnodes_root = inventory._validated_path(launch["kjnodes"]["root"], "KJNodes root", "directory")
        loaded_kjnodes_root = inventory._validated_path(
            str(comfy_root / "custom_nodes" / "ComfyUI-KJNodes"),
            "ComfyUI-loaded KJNodes root",
            "directory",
        )
        init_py = inventory._validated_path(str(kjnodes_root / "__init__.py"), "KJNodes __init__.py", "file")
    except (KeyError, inventory.PreflightError) as exc:
        raise RunnerError(f"admission path validation failed: {exc}") from exc
    if sha256_file(init_py) != launch["kjnodes"]["init_py_sha256"]:
        raise RunnerError("KJNodes __init__.py SHA-256 drifted from launch config")
    if not inventory._same_path(kjnodes_root, loaded_kjnodes_root):
        raise RunnerError("launch config KJNodes root is not the tree ComfyUI will load")
    kjnodes_git = _git_identity(kjnodes_root, "KJNodes")
    if kjnodes_git.get("commit") != KJ_COMMIT or kjnodes_git.get("dirty"):
        raise RunnerError("KJNodes is not clean at the required commit")
    comfy_git = _git_identity(comfy_root, "ComfyUI")
    if comfy_git.get("commit") != COMFY032_COMMIT or comfy_git.get("dirty"):
        raise RunnerError("ComfyUI is not clean at the required 0.32.0 commit")
    shipped_extra_paths = comfy_root / "extra_model_paths.yaml"
    if shipped_extra_paths.exists():
        raise RunnerError(
            "ComfyUI root has an unmanaged extra_model_paths.yaml; "
            "the physical runner requires its private model-path configuration to be the only extra root"
        )
    ffprobe_observed = {
        "path": str(ffprobe), "bytes": ffprobe.stat().st_size, "sha256": sha256_file(ffprobe)
    }
    if ffprobe_observed["sha256"] != identity.get("ffprobe_sha256"):
        raise RunnerError("ffprobe SHA-256 drifted from the enrolled profile")
    expected_model_hashes = identity.get("model_sha256s")
    if not isinstance(expected_model_hashes, dict):
        raise RunnerError("profile omitted model SHA-256 identities")
    model_manifest = verify_model_manifest(plan, model_roots, expected_model_hashes)
    selected_gpu = preflight.get("observed", {}).get("selected_gpu")
    if not isinstance(selected_gpu, dict) or not isinstance(selected_gpu.get("uuid"), str) or not selected_gpu["uuid"]:
        raise RunnerError("profile preflight did not bind one physical GPU UUID")
    return {
        "plan": plan,
        "plan_sha256": plan_hash,
        "launch": launch,
        "launch_sha256": launch_hash,
        "profile": profile,
        "profile_path": profile_path,
        "profile_sha256": profile_hash,
        "preflight": preflight,
        "python": python,
        "comfy_root": comfy_root,
        "ffprobe": ffprobe,
        "ffprobe_observed": ffprobe_observed,
        "model_roots": model_roots,
        "kjnodes_root": kjnodes_root,
        "loaded_kjnodes_root": loaded_kjnodes_root,
        "kjnodes_git": kjnodes_git,
        "comfy_git": comfy_git,
        "model_manifest": model_manifest,
        "gpu_uuid": selected_gpu["uuid"],
        "cache_runtime_sha256s": cache_runtime_sha256s(comfy_root),
    }


def sanitized_environment(*, gpu_uuid: str | None = None) -> dict[str, str]:
    """Allow only Windows runtime basics and force offline model behavior."""
    source = os.environ
    allowed = {
        "appdata", "comspec", "homedrive", "homepath", "localappdata", "path",
        "pathext", "programdata", "programfiles", "systemroot", "temp", "tmp",
        # PyTorch's Windows compiler-cache path calls getpass.getuser().  Its
        # normal Windows fallback is USERNAME; without it the stdlib falls
        # through to the Unix-only pwd module before ComfyUI can boot.
        "username", "userprofile", "windir",
    }
    environment = {key: value for key, value in source.items() if key.casefold() in allowed}
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PIP_NO_INDEX": "1",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    if gpu_uuid is not None:
        if not re.fullmatch(r"GPU-[A-Za-z0-9-]+", gpu_uuid):
            raise RunnerError("enrolled GPU UUID has an invalid shape")
        environment["CUDA_VISIBLE_DEVICES"] = gpu_uuid
    return environment


def build_model_paths_yaml(model_roots: Mapping[str, Path], custom_nodes_parent: Path) -> str:
    required = ("diffusion_models", "text_encoders", "vae")
    if set(model_roots) != set(required):
        raise RunnerError("physical model roots must be exactly diffusion_models/text_encoders/vae")
    try:
        custom_nodes_parent = inventory._validated_path(
            str(custom_nodes_parent), "ComfyUI custom-node parent", "directory"
        )
    except inventory.PreflightError as exc:
        raise RunnerError(str(exc)) from exc
    lines = ["physical_4060:", "  is_default: true", "  base_path: \"C:/\""]
    for name in required:
        lines.append(f"  {name}: {_json_path_text(model_roots[name])}")
    # With --base-directory set to the private cell, these are the only
    # non-empty search roots.  The parent is needed because Comfy discovers
    # custom-node *directories* beneath it; the whitelist admits KJNodes only.
    lines.append(f"  custom_nodes: {_json_path_text(custom_nodes_parent)}")
    return "\n".join(lines) + "\n"


def build_launch_argv(admission: Mapping[str, Any], cell: Path) -> list[str]:
    input_dir = _safe_local_child(cell, "input")
    output_dir = _safe_local_child(cell, "output")
    user_dir = _safe_local_child(cell, "user")
    model_yaml = _safe_local_child(cell, "model_paths.yaml")
    base_dir = _safe_local_child(cell, "base")
    main_py = Path(admission["comfy_root"]) / "main.py"
    try:
        main_py = inventory._validated_path(str(main_py), "ComfyUI main.py", "file")
    except inventory.PreflightError as exc:
        raise RunnerError(str(exc)) from exc
    return [
        str(admission["python"]), str(main_py),
        "--listen", LISTENER,
        "--port", str(PORT),
        "--base-directory", str(base_dir),
        "--input-directory", str(input_dir),
        "--output-directory", str(output_dir),
        "--user-directory", str(user_dir),
        "--extra-model-paths-config", str(model_yaml),
        "--disable-pinned-memory",
        "--disable-metadata",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes", "ComfyUI-KJNodes",
    ]


def _listener_pid(port: int) -> int | None:
    """Find a loopback-only Windows listener without importing psutil."""
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"cannot inspect local TCP ownership: {exc}") from exc
    if completed.returncode != 0:
        raise RunnerError(f"netstat failed while checking isolated port {port}")
    expected = f"{LISTENER}:{port}"
    foreign = []
    for raw in completed.stdout.splitlines():
        fields = raw.split()
        if len(fields) < 5 or fields[0].upper() != "TCP" or fields[3].upper() != "LISTENING":
            continue
        local, pid_text = fields[1], fields[-1]
        if local.casefold() == expected.casefold():
            try:
                return int(pid_text)
            except ValueError as exc:
                raise RunnerError(f"unparseable listener PID for {expected}") from exc
        if local.endswith(f":{port}"):
            foreign.append(local)
    if foreign:
        raise RunnerError(f"isolated port {port} is listening on a non-loopback address: {foreign}")
    return None


def _http_json(path: str, *, method: str = "GET", payload: Mapping[str, Any] | None = None, timeout_s: float = 15.0) -> dict[str, Any]:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise RunnerError("isolated ComfyUI request path must be an absolute local path")
    data = canonical_bytes(dict(payload)) if payload is not None else None
    request = urllib.request.Request(
        f"{SERVER_URL}{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "Cache-Control": "no-cache"} if data is not None else {"Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=timeout_s
        ) as response:
            decoded = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise RunnerError(f"laptop-owned ComfyUI {path} request failed: {exc}") from exc
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"laptop-owned ComfyUI {path} did not return JSON") from exc
    if not isinstance(parsed, dict):
        raise RunnerError(f"laptop-owned ComfyUI {path} did not return an object")
    return parsed


def _normalized_argv(argv: Sequence[str]) -> list[str]:
    return [str(item).replace("\\", "/").casefold() for item in argv]


def _process_snapshot(pid: int) -> dict[str, Any]:
    try:
        process = psutil.Process(pid)
        command_line = [str(item) for item in process.cmdline()]
        executable = str(process.exe())
        created = float(process.create_time())
        parent_pid = int(process.ppid())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise RunnerError(f"cannot inspect owned 4060 process {pid}: {exc}") from exc
    if not command_line or created <= 0:
        raise RunnerError(f"owned 4060 process {pid} has an invalid identity")
    return {
        "pid": int(pid),
        "process_create_time": created,
        "executable": executable,
        "command_line": command_line,
        "parent_pid": parent_pid,
    }


def _argv_matches_expected(actual_argv: Sequence[str], expected_argv: Sequence[str]) -> bool:
    actual = _normalized_argv(actual_argv)
    expected = _normalized_argv(expected_argv)
    if actual == expected:
        return True
    # A Windows virtual-environment launcher may substitute only argv[0] for
    # the serving child.  Its script and every Comfy argument must remain exact.
    return (
        len(actual) == len(expected)
        and len(actual) >= 2
        and actual[1:] == expected[1:]
        and Path(actual[0]).name in {"python.exe", "pythonw.exe"}
    )


def _listener_owned_by_launcher(listener_pid: int, launcher_pid: int, expected_argv: Sequence[str]) -> dict[str, Any]:
    serving = _process_snapshot(listener_pid)
    if not _argv_matches_expected(serving["command_line"], expected_argv):
        raise RunnerError("isolated listener command line does not match the canonical direct argv")
    lineage = [listener_pid]
    try:
        cursor = psutil.Process(listener_pid)
        while cursor.pid != launcher_pid:
            cursor = cursor.parent()
            if cursor is None:
                break
            lineage.append(int(cursor.pid))
            if len(lineage) > 8:
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise RunnerError(f"cannot prove isolated listener ancestry: {exc}") from exc
    if launcher_pid not in lineage:
        raise RunnerError(
            f"isolated listener PID {listener_pid} is not the direct launcher or its child"
        )
    return {**serving, "launcher_pid": launcher_pid, "lineage_pids": lineage}


def _verify_system_stats_device(
    system_stats: Mapping[str, Any], gpu_uuid: str
) -> dict[str, Any]:
    """Tie Comfy's primary visible GPU to the UUID selected for this launch."""
    try:
        executable = inventory._trusted_nvidia_smi_path()
        completed = subprocess.run(
            [str(executable), "--query-gpu=uuid,name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=10,
            env=sanitized_environment(),
        )
    except (inventory.PreflightError, OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"cannot bind Comfy system statistics to enrolled GPU: {exc}") from exc
    if completed.returncode != 0:
        raise RunnerError("nvidia-smi failed while binding Comfy system statistics")
    enrolled: tuple[str, int] | None = None
    for raw in completed.stdout.splitlines():
        fields = [item.strip() for item in raw.split(",")]
        if len(fields) != 3:
            raise RunnerError("nvidia-smi GPU identity row is malformed")
        if fields[0] == gpu_uuid:
            try:
                enrolled = (fields[1], int(fields[2]))
            except ValueError as exc:
                raise RunnerError("nvidia-smi enrolled GPU memory is malformed") from exc
    if enrolled is None:
        raise RunnerError("nvidia-smi did not return the enrolled GPU UUID")
    devices = system_stats.get("devices")
    if not isinstance(devices, list) or not devices or not isinstance(devices[0], Mapping):
        raise RunnerError("Comfy system_stats omitted its primary device")
    primary = devices[0]
    name = primary.get("name")
    total = primary.get("vram_total")
    if not isinstance(name, str) or not isinstance(total, (int, float)):
        raise RunnerError("Comfy system_stats primary device is malformed")
    total_mib = int(round(float(total) / (1024 * 1024)))
    # Comfy 0.32 may decorate its primary device string with the logical
    # CUDA ordinal and allocator (for example, ``cuda:0 <name> :
    # cudaMallocAsync``).  CUDA_VISIBLE_DEVICES pins the enrolled UUID and
    # therefore the only permitted logical ordinal is cuda:0.  Accept exactly
    # that documented wrapper around the nvidia-smi name--not a substring or
    # arbitrary formatter--and still require the independently observed VRAM.
    wrapped_name = re.fullmatch(
        rf"cuda:0\s+{re.escape(enrolled[0])}\s+:\s+[A-Za-z0-9_.-]+", name
    )
    same_device_name = name == enrolled[0] or wrapped_name is not None
    # Comfy reports bytes while nvidia-smi reports MiB. Allow a small rounding
    # tolerance, but never accept a different device name or capacity.
    if not same_device_name or abs(total_mib - enrolled[1]) > 8:
        raise RunnerError(
            "Comfy primary device does not match the enrolled GPU identity "
            f"(Comfy={name}/{total_mib} MiB; enrolled={enrolled[0]}/{enrolled[1]} MiB)"
        )
    return {
        "gpu_uuid": gpu_uuid,
        "name": enrolled[0],
        "comfy_device_name": name,
        "vram_total_mib": total_mib,
    }


def _schema_option_values(
    object_info: Mapping[str, Any], class_type: str, input_name: str
) -> list[str]:
    """Read a ComfyUI enum input without trusting an ad-hoc server shape."""
    node = object_info.get(class_type)
    if not isinstance(node, Mapping):
        raise RunnerError(f"live schema omitted node {class_type}")
    inputs = node.get("input")
    required = inputs.get("required") if isinstance(inputs, Mapping) else None
    entry = required.get(input_name) if isinstance(required, Mapping) else None
    if not isinstance(entry, list) or not entry or not isinstance(entry[0], list):
        raise RunnerError(f"live schema omitted enum {class_type}.{input_name}")
    values = entry[0]
    if not all(isinstance(value, str) for value in values):
        raise RunnerError(f"live schema enum {class_type}.{input_name} is malformed")
    return list(values)


def validate_live_source_prompt(
    plan: Mapping[str, Any], object_info: Mapping[str, Any]
) -> dict[str, Any]:
    """Prove the checked-in source graph fits the exact live 0.32 schema.

    The cache nonce is injected only *after* this validation.  It is a separate,
    pinned executor behavior, not a silent relaxation of the ordinary graph
    schema.
    """
    source_path = REPO_ROOT / "recipes" / "h3_mime_i2v.json"
    expected_hash = plan.get("orientation_only_source", {}).get("recipe_sha256")
    if not isinstance(expected_hash, str) or sha256_utf8_text_file(source_path) != expected_hash:
        raise RunnerError("bound H3 source recipe bytes drifted before live schema validation")
    recipe = _read_json(source_path, "bound H3 source recipe")
    graph = recipe.get("prompt")
    if not isinstance(graph, Mapping):
        raise RunnerError("bound H3 source recipe prompt is malformed")
    required_nodes = plan.get("required_core_nodes")
    if not isinstance(required_nodes, list) or not all(isinstance(node, str) for node in required_nodes):
        raise RunnerError("physical plan required node list is malformed")
    source_classes = {
        node.get("class_type")
        for node in graph.values()
        if isinstance(node, Mapping)
    }
    if source_classes != set(required_nodes):
        raise RunnerError("bound H3 source graph node set drifted from the physical plan")
    for node_id, node in graph.items():
        if not isinstance(node_id, str) or not isinstance(node, Mapping):
            raise RunnerError("bound H3 source graph contains a malformed node")
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(class_type, str) or not isinstance(inputs, Mapping):
            raise RunnerError(f"bound H3 source node {node_id} is malformed")
        node_schema = object_info.get(class_type)
        schema_input = node_schema.get("input") if isinstance(node_schema, Mapping) else None
        required = schema_input.get("required") if isinstance(schema_input, Mapping) else None
        optional = schema_input.get("optional") if isinstance(schema_input, Mapping) else None
        # ComfyUI 0.32 omits an empty optional section for nodes such as
        # UNETLoader.  Treat only the absent section as empty; any present
        # non-mapping remains malformed so we never broaden a live schema.
        if optional is None:
            optional = {}
        if not isinstance(required, Mapping) or not isinstance(optional, Mapping):
            raise RunnerError(f"live schema for {class_type} is malformed")
        schema_keys = set(required) | set(optional)
        missing = sorted(set(required) - set(inputs))
        unknown = sorted(set(inputs) - schema_keys)
        if missing or unknown:
            raise RunnerError(
                f"bound H3 source node {node_id} schema drifted; "
                f"missing={missing}, unknown={unknown}"
            )
        for value in inputs.values():
            for source_id, output_index in _iter_prompt_link_pairs(value):
                source = graph.get(source_id)
                if not isinstance(source, Mapping):
                    raise RunnerError(
                        f"bound H3 source node {node_id} links missing source {source_id}"
                    )
                source_class = source.get("class_type")
                outputs = object_info.get(source_class, {}).get("output", [])
                if not isinstance(outputs, list) or not outputs:
                    raise RunnerError(
                        f"live schema omitted outputs for linked source {source_id} ({source_class})"
                    )
                if (
                    isinstance(output_index, bool)
                    or not isinstance(output_index, int)
                    or output_index < 0
                    or output_index >= len(outputs)
                ):
                    raise RunnerError(
                        f"bound H3 source node {node_id} requests invalid output "
                        f"{output_index!r} from {source_id} ({source_class})"
                    )
    assets = plan.get("engine", {}).get("required_assets")
    if not isinstance(assets, list):
        raise RunnerError("physical plan required assets are malformed")
    enum_by_category = {
        "diffusion_models": ("UNETLoader", "unet_name"),
        "text_encoders": ("CLIPLoader", "clip_name"),
        "vae": ("VAELoader", "vae_name"),
    }
    model_options: dict[str, dict[str, str]] = {}
    for asset in assets:
        if not isinstance(asset, Mapping):
            raise RunnerError("physical plan contains a malformed required asset")
        category = asset.get("category")
        filename = asset.get("filename")
        if not isinstance(category, str) or not isinstance(filename, str):
            raise RunnerError("physical plan required asset lacks category or filename")
        try:
            class_type, input_name = enum_by_category[category]
        except KeyError as exc:
            raise RunnerError(f"physical plan declares unsupported model category {category}") from exc
        if filename not in _schema_option_values(object_info, class_type, input_name):
            raise RunnerError(
                f"laptop-owned ComfyUI did not expose admitted model {filename} "
                f"in {class_type}.{input_name}"
            )
        model_options[f"{category}/{filename}"] = {
            "class_type": class_type,
            "input": input_name,
        }
    return {
        "source_recipe_sha256": expected_hash,
        "source_node_count": len(graph),
        "model_option_proof": model_options,
    }


def _verify_live_boot(
    system_stats: Mapping[str, Any],
    object_info: Mapping[str, Any],
    plan: Mapping[str, Any],
    launcher_pid: int,
    expected_argv: Sequence[str],
    gpu_uuid: str,
) -> dict[str, Any]:
    listener_pid = _listener_pid(PORT)
    if listener_pid is None:
        raise RunnerError("owned ComfyUI did not own the isolated listener")
    serving = _listener_owned_by_launcher(listener_pid, launcher_pid, expected_argv)
    primary_device = _verify_system_stats_device(system_stats, gpu_uuid)
    argv = [str(item) for item in serving["command_line"]]
    forbidden = ("--use-sage-attention", "--reserve-vram", "--enable-manager")
    if any(flag in argv for flag in forbidden):
        raise RunnerError("laptop-owned ComfyUI argv contains a forbidden H3-lane flag")
    required_pairs = (("--listen", LISTENER), ("--port", str(PORT)))
    for flag, expected in required_pairs:
        if argv.count(flag) != 1 or argv[argv.index(flag) + 1] != expected:
            raise RunnerError(f"laptop-owned ComfyUI argv does not prove {flag} {expected}")
    if argv.count("--disable-pinned-memory") != 1:
        raise RunnerError("laptop-owned ComfyUI argv lacks --disable-pinned-memory")
    if argv.count("--disable-all-custom-nodes") != 1:
        raise RunnerError("laptop-owned ComfyUI argv lacks custom-node lockdown")
    if argv.count("--whitelist-custom-nodes") != 1:
        raise RunnerError("laptop-owned ComfyUI argv lacks an exact custom-node allowlist")
    whitelist_index = argv.index("--whitelist-custom-nodes")
    whitelist = argv[whitelist_index + 1:]
    if whitelist != ["ComfyUI-KJNodes"]:
        raise RunnerError(f"laptop-owned ComfyUI custom-node allowlist drifted: {whitelist}")
    required_nodes = plan.get("required_core_nodes")
    if not isinstance(required_nodes, list) or not all(node in object_info for node in required_nodes):
        missing = sorted(set(required_nodes or []) - set(object_info))
        raise RunnerError(f"laptop-owned ComfyUI object_info lacks required H3 nodes: {missing}")
    source_schema = validate_live_source_prompt(plan, object_info)
    manager_nodes = sorted(name for name in object_info if "manager" in name.casefold())
    if manager_nodes:
        raise RunnerError(f"ComfyUI-Manager surface is forbidden in this lane: {manager_nodes}")
    queue = _http_json("/queue")
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RunnerError("laptop-owned queue is not empty before physical benchmark")
    return {
        "listener_pid": listener_pid,
        "serving_process": serving,
        "server_argv": argv,
        "required_nodes": list(required_nodes),
        "source_schema": source_schema,
        "primary_device": primary_device,
        "manager_nodes": manager_nodes,
        "queue": queue,
        "system_stats_sha256": hashlib.sha256(canonical_bytes(dict(system_stats))).hexdigest(),
        "object_info_sha256": hashlib.sha256(canonical_bytes(dict(object_info))).hexdigest(),
    }


class ResourceMonitor:
    """Capture physical GPU/host-RAM samples only while a prompt is active."""

    def __init__(self, gpu_uuid: str, interval_s: float = POLL_INTERVAL_S) -> None:
        if not re.fullmatch(r"GPU-[A-Za-z0-9-]+", gpu_uuid):
            raise RunnerError("resource monitor requires the enrolled GPU UUID")
        self.gpu_uuid = gpu_uuid
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, float]] = []
        self._error: str | None = None
        self._started = 0.0

    def _sample_details(self) -> tuple[float, float, float]:
        try:
            executable = inventory._trusted_nvidia_smi_path()
        except inventory.PreflightError as exc:
            raise RunnerError(str(exc)) from exc
        try:
            completed = subprocess.run(
                [str(executable), "--query-gpu=uuid,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, encoding="utf-8", errors="strict", check=False, timeout=10,
                env=sanitized_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunnerError(f"nvidia-smi sample failed: {exc}") from exc
        if completed.returncode != 0:
            raise RunnerError("nvidia-smi sample returned nonzero")
        try:
            rows = []
            for raw in completed.stdout.splitlines():
                fields = [item.strip() for item in raw.split(",")]
                if len(fields) != 2:
                    raise ValueError("unexpected nvidia-smi row")
                rows.append((fields[0], float(fields[1]) / 1024.0))
            matches = [used for uuid_value, used in rows if uuid_value == self.gpu_uuid]
            if len(matches) != 1:
                raise ValueError("enrolled GPU UUID was not uniquely measured")
            vram_gib = matches[0]
            host_snapshot = inventory.host_ram_snapshot()
            host_available_gib = float(host_snapshot["available_gib"])
            host_gib = float(host_snapshot["total_gib"] - host_available_gib)
        except (IndexError, ValueError, KeyError, inventory.PreflightError) as exc:
            raise RunnerError(f"resource sample was malformed: {exc}") from exc
        return vram_gib, host_gib, host_available_gib

    def _sample(self) -> tuple[float, float]:
        """Compatibility view used by single-point ownership cleanup checks."""
        vram_gib, host_used_gib, _ = self._sample_details()
        return vram_gib, host_used_gib

    def start(self) -> tuple[float, float]:
        baseline_vram, baseline_host, baseline_available = self._sample_details()
        self._started = time.monotonic()
        self._samples.append(
            {
                "offset_s": 0.0,
                "vram_gib": baseline_vram,
                "host_ram_gib": baseline_host,
                "host_ram_available_gib": baseline_available,
            }
        )
        self._thread = threading.Thread(target=self._run, name="physical-4060-resource-monitor", daemon=True)
        self._thread.start()
        return baseline_vram, baseline_host

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                vram_gib, host_gib, host_available_gib = self._sample_details()
                self._samples.append(
                    {
                        "offset_s": round(time.monotonic() - self._started, 3),
                        "vram_gib": vram_gib,
                        "host_ram_gib": host_gib,
                        "host_ram_available_gib": host_available_gib,
                    }
                )
            except Exception as exc:  # surface after joining, never silently omit a failed meter
                self._error = str(exc)
                self._stop.set()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._error:
            raise RunnerError(f"resource monitor failed: {self._error}")
        if not self._samples:
            raise RunnerError("resource monitor captured no samples")
        return {
            "gpu_uuid": self.gpu_uuid,
            "interval_s": self.interval_s,
            "samples": self._samples,
            "peak_vram_gib": max(sample["vram_gib"] for sample in self._samples),
            "peak_host_ram_gib": max(sample["host_ram_gib"] for sample in self._samples),
            "min_host_ram_available_gib": min(
                sample["host_ram_available_gib"] for sample in self._samples
            ),
            "baseline_vram_gib": self._samples[0]["vram_gib"],
            "baseline_host_ram_gib": self._samples[0]["host_ram_gib"],
            "baseline_host_ram_available_gib": self._samples[0]["host_ram_available_gib"],
        }


def verify_preboot_resources(gpu_uuid: str) -> dict[str, float | str]:
    """Refuse to contend with an already-loaded local GPU worker."""
    monitor = ResourceMonitor(gpu_uuid)
    vram_gib, host_used_gib, host_available_gib = monitor._sample_details()
    if vram_gib > PREBOOT_MAX_VRAM_GIB:
        raise RunnerError(
            f"enrolled RTX 4060 is not idle before boot: {vram_gib:.3f} GiB used "
            f"(maximum {PREBOOT_MAX_VRAM_GIB:.3f} GiB); stop the local GPU worker first"
        )
    if host_available_gib < PREBOOT_MIN_HOST_AVAILABLE_GIB:
        raise RunnerError(
            f"host RAM is too busy before boot: {host_available_gib:.3f} GiB available "
            f"(need {PREBOOT_MIN_HOST_AVAILABLE_GIB:.3f} GiB)"
        )
    return {
        "gpu_uuid": gpu_uuid,
        "vram_gib": vram_gib,
        "host_ram_used_gib": host_used_gib,
        "host_ram_available_gib": host_available_gib,
    }


class OwnedServer:
    """A directly launched, receipt-owned, loopback-only ComfyUI process."""

    def __init__(
        self, argv: Sequence[str], cell: Path, plan: Mapping[str, Any], gpu_uuid: str
    ) -> None:
        self.argv = list(argv)
        self.cell = cell
        self.plan = plan
        self.gpu_uuid = gpu_uuid
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.server_receipt = _safe_local_child(cell, "server.json")
        self.server_nonce = uuid.uuid4().hex
        self.launcher_identity: dict[str, Any] | None = None
        self.live: dict[str, Any] | None = None
        self.preboot_resources: dict[str, float | str] | None = None

    def start(self) -> dict[str, Any]:
        existing = _listener_pid(PORT)
        if existing is not None:
            raise RunnerError(
                f"unrecognized or prior 4060 server owns isolated port {PORT} (PID {existing})"
            )
        self.preboot_resources = verify_preboot_resources(self.gpu_uuid)
        logs = _safe_local_child(self.cell, "logs")
        logs.mkdir(parents=True, exist_ok=True)
        log_path = _safe_local_child(logs, "server.log")
        self.log_handle = log_path.open("xb")
        try:
            self.process = subprocess.Popen(
                self.argv,
                cwd=str(Path(self.argv[1]).parent),
                stdin=subprocess.DEVNULL,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                env=sanitized_environment(gpu_uuid=self.gpu_uuid),
                shell=False,
            )
            self.launcher_identity = _process_snapshot(self.process.pid)
        except (OSError, RunnerError) as exc:
            self.log_handle.close()
            raise RunnerError(f"direct ComfyUI launch failed: {exc}") from exc
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        last_error = "not ready"
        while time.monotonic() < deadline:
            try:
                stats = _http_json("/system_stats", timeout_s=3)
                objects = _http_json("/object_info", timeout_s=10)
                self.live = _verify_live_boot(
                    stats, objects, self.plan, self.process.pid, self.argv, self.gpu_uuid
                )
                self.live["preboot_resources"] = dict(self.preboot_resources)
                receipt = {
                    "server_receipt_schema_version": 1,
                    "nonce": self.server_nonce,
                    "launcher_process": self.launcher_identity,
                    "serving_process": self.live["serving_process"],
                    "port": PORT,
                    "listener": LISTENER,
                    "argv": self.argv,
                    "argv_sha256": hashlib.sha256(canonical_bytes(self.argv)).hexdigest(),
                    "gpu_uuid": self.gpu_uuid,
                    "preboot_resources": self.preboot_resources,
                    "log_path": "logs/server.log",
                    "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                _write_exclusive_json(self.server_receipt, receipt)
                return self.live
            except RunnerError as exc:
                last_error = str(exc)
                if self.process.poll() is not None and _listener_pid(PORT) is None:
                    raise RunnerError(f"owned ComfyUI exited during startup; see {log_path}") from exc
                time.sleep(1)
        raise RunnerError(
            f"owned ComfyUI did not become admissible: {last_error}; see {log_path}"
        )

    @staticmethod
    def _terminate_verified_process(identity: Mapping[str, Any]) -> list[dict[str, Any]]:
        pid = identity.get("pid")
        created = identity.get("process_create_time")
        if not isinstance(pid, int) or not isinstance(created, (int, float)):
            raise RunnerError("owned process identity is malformed")
        snapshot = _process_snapshot(pid)
        if abs(float(snapshot["process_create_time"]) - float(created)) > 0.01:
            raise RunnerError("owned process PID was reused before shutdown")
        process = psutil.Process(pid)
        targets = process.children(recursive=True) + [process]
        observed = []
        for target in targets:
            try:
                observed.append(_process_snapshot(target.pid))
                target.terminate()
            except psutil.NoSuchProcess:
                continue
        _, alive = psutil.wait_procs(targets, timeout=30)
        for target in alive:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                continue
        _, alive = psutil.wait_procs(alive, timeout=15)
        if alive:
            raise RunnerError(f"owned 4060 process tree did not exit: {[item.pid for item in alive]}")
        return observed

    def shutdown(self, reason: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "reason": reason,
            "success": False,
            "server_receipt_path": "server.json" if self.server_receipt.exists() else None,
            "server_receipt_sha256": sha256_file(self.server_receipt) if self.server_receipt.exists() else None,
        }
        try:
            expected_serving: Mapping[str, Any] | None = None
            if self.server_receipt.exists():
                receipt = _read_json(self.server_receipt, "owned 4060 server receipt")
                if receipt.get("nonce") != self.server_nonce:
                    raise RunnerError("refusing shutdown: owned server receipt nonce mismatched")
                expected_serving = receipt.get("serving_process")
            elif self.live is not None:
                expected_serving = self.live.get("serving_process")
            listener_before = _listener_pid(PORT)
            result["listener_before"] = listener_before
            terminated: list[dict[str, Any]] = []
            if listener_before is not None:
                if not isinstance(expected_serving, Mapping):
                    expected_serving = _listener_owned_by_launcher(
                        listener_before,
                        self.process.pid if self.process is not None else -1,
                        self.argv,
                    )
                if listener_before != expected_serving.get("pid"):
                    raise RunnerError(f"refusing shutdown: foreign PID {listener_before} owns isolated port")
                terminated.extend(self._terminate_verified_process(expected_serving))
            if self.launcher_identity is not None:
                try:
                    launcher = _process_snapshot(int(self.launcher_identity["pid"]))
                except RunnerError:
                    launcher = None
                if launcher is not None and (
                    not isinstance(expected_serving, Mapping)
                    or launcher["pid"] != expected_serving.get("pid")
                ):
                    terminated.extend(self._terminate_verified_process(self.launcher_identity))
            listener_after = _listener_pid(PORT)
            if listener_after is not None:
                raise RunnerError(f"owned server shutdown did not release isolated port {PORT}")
            monitor = ResourceMonitor(self.gpu_uuid)
            post_vram, post_host = monitor._sample()
            if post_vram > PREBOOT_MAX_VRAM_GIB:
                raise RunnerError(
                    f"GPU cleanup is not proved after owned server exit: {post_vram:.3f} GiB used"
                )
            result.update(
                {
                    "success": True,
                    "listener_after": listener_after,
                    "terminated_processes": terminated,
                    "post_shutdown_resources": {
                        "gpu_uuid": self.gpu_uuid,
                        "vram_gib": post_vram,
                        "host_ram_gib": post_host,
                    },
                }
            )
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            # A failed ownership/validation branch must never strand the
            # launcher we started.  The launcher identity was snapshotted at
            # Popen time, so this emergency cleanup remains fail-closed against
            # PID reuse and does not touch a foreign listener/process.
            if not result["success"] and self.launcher_identity is not None:
                try:
                    emergency = self._terminate_verified_process(self.launcher_identity)
                    result["emergency_terminated_processes"] = emergency
                    result["listener_after_emergency_cleanup"] = _listener_pid(PORT)
                except Exception as cleanup_exc:
                    result["emergency_cleanup_error"] = str(cleanup_exc)
            if self.log_handle is not None:
                self.log_handle.close()
                self.log_handle = None
        return result


def _fixture_details(plan: Mapping[str, Any]) -> tuple[Path, str, str]:
    contract = plan.get("video_contract")
    if not isinstance(contract, dict):
        raise RunnerError("plan video contract is missing")
    fixture_relative = contract.get("fixture")
    expected_hash = contract.get("fixture_sha256")
    if not isinstance(fixture_relative, str) or not isinstance(expected_hash, str):
        raise RunnerError("plan fixture contract is malformed")
    if Path(fixture_relative).is_absolute() or ".." in Path(fixture_relative).parts:
        raise RunnerError("plan fixture path must stay under the checked-in repository")
    source = REPO_ROOT / fixture_relative
    try:
        source = inventory._validated_path(str(source), "H3 source fixture", "file")
    except inventory.PreflightError as exc:
        raise RunnerError(str(exc)) from exc
    try:
        if not source.is_relative_to(REPO_ROOT.resolve(strict=True)):
            raise RunnerError("plan fixture path escaped the checked-in repository")
    except OSError as exc:
        raise RunnerError(f"cannot resolve checked-in fixture root: {exc}") from exc
    fixture_name = source.name
    if not fixture_name:
        raise RunnerError("plan fixture basename is empty")
    if sha256_file(source) != expected_hash:
        raise RunnerError("checked-in H3 source fixture SHA-256 drifted")
    return source, fixture_name, expected_hash


def _copy_fixture(plan: Mapping[str, Any], cell: Path) -> dict[str, str]:
    source, fixture_name, expected_hash = _fixture_details(plan)
    destination = _safe_local_child(cell, "input", fixture_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256_file(destination) != expected_hash:
        raise RunnerError("private 4060 input fixture copy hash mismatched")
    return {fixture_name: expected_hash}


def _verify_fixture_readback(plan: Mapping[str, Any]) -> None:
    _, fixture_name, expected = _fixture_details(plan)
    query = urllib.parse.urlencode({"filename": fixture_name, "type": "input"})
    request = urllib.request.Request(f"{SERVER_URL}/view?{query}", headers={"Cache-Control": "no-cache"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=15
        ) as response:
            received = response.read()
    except urllib.error.URLError as exc:
        raise RunnerError(f"private fixture readback failed: {exc}") from exc
    if hashlib.sha256(received).hexdigest() != expected:
        raise RunnerError("private fixture readback SHA-256 mismatched")


def _queue_prompt(prompt: Mapping[str, Any], run_id: str) -> str:
    response = _http_json("/prompt", method="POST", payload={"prompt": prompt, "client_id": run_id}, timeout_s=30)
    prompt_id = response.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise RunnerError("ComfyUI prompt response omitted prompt_id")
    return prompt_id


def _safe_output_file(output_root: Path, entry: Mapping[str, Any]) -> Path:
    name = entry.get("filename")
    subfolder = entry.get("subfolder", "")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise RunnerError("ComfyUI output filename is unsafe")
    if not isinstance(subfolder, str) or Path(subfolder).is_absolute() or ".." in Path(subfolder).parts:
        raise RunnerError("ComfyUI output subfolder is unsafe")
    candidate = (output_root / subfolder / name).resolve(strict=True)
    if not candidate.is_relative_to(output_root.resolve(strict=True)) or not candidate.is_file() or candidate.stat().st_size <= 0:
        raise RunnerError("ComfyUI output is absent, empty, or outside the private cell")
    return candidate


def _history_artifact(history: Mapping[str, Any], prompt_id: str, output_root: Path) -> tuple[Path, list[Any], dict[str, Any]]:
    item = history.get(prompt_id)
    if not isinstance(item, dict):
        raise RunnerError("terminal history did not include the queued prompt")
    status = item.get("status")
    if not isinstance(status, dict) or status.get("status_str") != "success" or status.get("completed") is not True:
        raise RunnerError(f"ComfyUI prompt did not complete successfully: {status}")
    messages = status.get("messages", [])
    if not isinstance(messages, list):
        raise RunnerError("ComfyUI history messages are malformed")
    outputs = item.get("outputs")
    if not isinstance(outputs, dict):
        raise RunnerError("ComfyUI history omitted output metadata")
    candidates: list[Mapping[str, Any]] = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("gifs", "videos", "images"):
            entries = node_output.get(key)
            if isinstance(entries, list):
                candidates.extend(entry for entry in entries if isinstance(entry, dict))
    if len(candidates) != 1:
        raise RunnerError(f"expected exactly one private video artifact, found {len(candidates)}")
    return _safe_output_file(output_root, candidates[0]), messages, outputs


def _wait_for_artifact(prompt_id: str, output_root: Path) -> tuple[Path, list[Any], dict[str, Any]]:
    deadline = time.monotonic() + COMPLETION_TIMEOUT_S
    last_error: str | None = None
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            history = _http_json(f"/history/{urllib.parse.quote(prompt_id)}", timeout_s=15)
            if prompt_id not in history:
                continue
            return _history_artifact(history, prompt_id, output_root)
        except RunnerError as exc:
            last_error = str(exc)
            if "did not complete successfully" in last_error:
                raise
    raise RunnerError(f"accepted ComfyUI prompt did not reach terminal history: {last_error or 'timeout'}")


def _fraction_to_float(value: str) -> float:
    if "/" not in value:
        return float(value)
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def probe_media(ffprobe: Path, artifact: Path) -> dict[str, Any]:
    command = [
        str(ffprobe), "-v", "error", "-count_frames", "-count_packets", "-show_streams", "-show_format", "-of", "json", str(artifact),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="strict", check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"ffprobe failed: {exc}") from exc
    if completed.returncode != 0:
        raise RunnerError(f"ffprobe rejected private artifact: {completed.stderr.strip()[:300]}")
    try:
        probe = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerError("ffprobe did not return JSON") from exc
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list):
        raise RunnerError("ffprobe output lacks streams")
    video = next((stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"), None)
    fmt = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    if not isinstance(video, dict) or not isinstance(audio, dict):
        raise RunnerError("private H3 artifact lacks nonempty video or audio stream")
    try:
        frame_count = int(video.get("nb_read_frames") or video.get("nb_frames"))
        metrics = {
            "artifact_sha256": sha256_file(artifact),
            "artifact_bytes": artifact.stat().st_size,
            "encoded_width": int(video["width"]),
            "encoded_height": int(video["height"]),
            "encoded_frame_count": frame_count,
            "encoded_fps": _fraction_to_float(str(video.get("avg_frame_rate") or video.get("r_frame_rate"))),
            "container_duration_s": float(fmt["duration"]),
            "video_duration_s": float(video.get("duration") or fmt["duration"]),
            "audio_duration_s": float(audio.get("duration") or fmt["duration"]),
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "audio_present": True,
            "video_packet_count": int(video.get("nb_read_packets") or 0),
            "audio_packet_count": int(audio.get("nb_read_packets") or 0),
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RunnerError(f"ffprobe media metrics are malformed: {exc}") from exc
    if metrics["artifact_bytes"] <= 0 or metrics["video_packet_count"] <= 0 or metrics["audio_packet_count"] <= 0:
        raise RunnerError("private H3 artifact has an empty stream")
    return metrics


def media_matches_contract(metrics: Mapping[str, Any], contract: Mapping[str, Any]) -> bool:
    try:
        expected_fps = float(contract["fps"])
        expected_duration = float(contract["duration_s"])
        checks = (
            int(metrics["encoded_width"]) == int(contract["width"]),
            int(metrics["encoded_height"]) == int(contract["height"]),
            int(metrics["encoded_frame_count"]) == int(contract["frames"]),
            abs(float(metrics["encoded_fps"]) - expected_fps) <= 0.01,
            bool(metrics["audio_present"]) is bool(contract["audio"]),
            all(abs(float(metrics[field]) - expected_duration) <= (1.0 / expected_fps) + 1e-9 for field in ("container_duration_s", "video_duration_s", "audio_duration_s")),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return all(checks)


def _iter_prompt_links(value: Any):
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
        yield value[0]
        return
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_prompt_links(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_prompt_links(child)


def _iter_prompt_link_pairs(value: Any):
    """Yield exact [node_id, output_index] references from a prompt input."""
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    ):
        yield value[0], value[1]
        return
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_prompt_link_pairs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_prompt_link_pairs(child)


def _prompt_descendants(prompt: Mapping[str, Any], source_id: str) -> list[str]:
    descendants = {source_id}
    changed = True
    while changed:
        changed = False
        for node_id, node in prompt.items():
            normalized = str(node_id)
            if normalized in descendants or not isinstance(node, Mapping):
                continue
            inputs = node.get("inputs", {})
            if isinstance(inputs, Mapping) and any(
                link in descendants
                for value in inputs.values()
                for link in _iter_prompt_links(value)
            ):
                descendants.add(normalized)
                changed = True
    return sorted(descendants, key=lambda value: (len(value), value))


def _prompt_output_ancestors(prompt: Mapping[str, Any]) -> list[str]:
    reachable = {
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, Mapping) and node.get("class_type") == "SaveVideo"
    }
    if not reachable:
        raise RunnerError("cache nonce needs exactly one reachable SaveVideo output")
    stack = list(reachable)
    while stack:
        node_id = stack.pop()
        node = prompt.get(node_id, {})
        inputs = node.get("inputs", {}) if isinstance(node, Mapping) else {}
        if not isinstance(inputs, Mapping):
            continue
        for value in inputs.values():
            for source_id in _iter_prompt_links(value):
                if source_id in prompt and source_id not in reachable:
                    reachable.add(source_id)
                    stack.append(source_id)
    return sorted(reachable, key=lambda value: (len(value), value))


def apply_cache_nonce(prompt: Mapping[str, Any], nonce: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Force the sampler/output branch fresh without changing seed or graph semantics."""
    if CACHE_NONCE_RE.fullmatch(nonce) is None:
        raise RunnerError("invalid physical-4060 cache nonce")
    if not isinstance(prompt, Mapping):
        raise RunnerError("bound H3 source prompt is not an object")
    candidates = [
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, Mapping) and node.get("class_type") == "RandomNoise"
    ]
    if len(candidates) != 1:
        raise RunnerError(f"physical H3 cache nonce requires one RandomNoise node, found {candidates}")
    source_id = candidates[0]
    source = prompt[source_id]
    inputs = source.get("inputs") if isinstance(source, Mapping) else None
    if not isinstance(inputs, Mapping) or set(inputs) != {"noise_seed"}:
        raise RunnerError("RandomNoise must expose only immutable noise_seed before nonce injection")
    seed = inputs.get("noise_seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise RunnerError("RandomNoise noise_seed must be an integer")
    queued = copy.deepcopy(dict(prompt))
    queued[source_id]["inputs"][CACHE_NONCE_INPUT] = nonce
    fresh = _prompt_descendants(queued, source_id)
    reachable = _prompt_output_ancestors(queued)
    samplers = sorted(
        node_id
        for node_id in fresh
        if isinstance(queued.get(node_id), Mapping)
        and queued[node_id].get("class_type") == "SamplerCustomAdvanced"
    )
    outputs = sorted(
        node_id
        for node_id in fresh
        if isinstance(queued.get(node_id), Mapping) and queued[node_id].get("class_type") == "SaveVideo"
    )
    if not samplers or not outputs or source_id not in reachable:
        raise RunnerError("nonce-controlled RandomNoise branch does not reach sampler and SaveVideo")
    return queued, {
        "mode": "pinned-undeclared-randomnoise-input",
        "nonce": nonce,
        "input_name": CACHE_NONCE_INPUT,
        "source_node_id": source_id,
        "recipe_noise_seed": seed,
        "fresh_node_ids": fresh,
        "stable_node_ids": sorted(set(reachable) - set(fresh), key=lambda value: (len(value), value)),
        "reachable_node_ids": reachable,
        "sampler_node_ids": samplers,
        "fresh_output_node_ids": outputs,
    }


def execution_cache_evidence(messages: Sequence[Any], control: Mapping[str, Any]) -> dict[str, Any]:
    cached: set[str] = set()
    event_seen = False
    for message in messages:
        if not isinstance(message, (list, tuple)) or len(message) < 2 or message[0] != "execution_cached":
            continue
        payload = message[1]
        if isinstance(payload, Mapping) and isinstance(payload.get("nodes"), list):
            event_seen = True
            cached.update(str(node) for node in payload["nodes"])
    fresh = {str(item) for item in control["fresh_node_ids"]}
    cached_fresh = sorted(fresh & cached, key=lambda value: (len(value), value))
    return {
        **dict(control),
        "cache_event_seen": event_seen,
        "cached_node_ids": sorted(cached, key=lambda value: (len(value), value)),
        "cached_fresh_node_ids": cached_fresh,
        "fresh_execution_proved": event_seen and not cached_fresh,
    }


def _run_leg(
    label: str,
    plan: Mapping[str, Any],
    cell: Path,
    physical_vram_gib: float,
    physical_host_ram_gib: float,
    gpu_uuid: str,
    ffprobe: Path,
) -> dict[str, Any]:
    if physical_host_ram_gib < 4.0:
        raise RunnerError("profile preflight physical host-RAM capacity is implausibly low")
    prompt = plan.get("source_prompt")
    if prompt is not None:
        raise RunnerError("physical plan must not carry a mutable alternate prompt")
    recipe = _read_json(REPO_ROOT / "recipes" / "h3_mime_i2v.json", "bound H3 source recipe")
    expected_hash = plan.get("orientation_only_source", {}).get("recipe_sha256")
    if sha256_utf8_text_file(REPO_ROOT / "recipes" / "h3_mime_i2v.json") != expected_hash:
        raise RunnerError("bound H3 source recipe bytes drifted")
    graph = recipe.get("prompt")
    if not isinstance(graph, dict):
        raise RunnerError("bound H3 source recipe prompt is malformed")
    queued_prompt, cache_control = apply_cache_nonce(
        graph, f"{label}-{uuid.uuid4().hex}"
    )
    monitor = ResourceMonitor(gpu_uuid)
    baseline_vram, baseline_host = monitor.start()
    started = time.monotonic()
    prompt_id = ""
    try:
        prompt_id = _queue_prompt(queued_prompt, f"physical-4060-{label}-{uuid.uuid4().hex}")
        artifact, messages, outputs = _wait_for_artifact(prompt_id, _safe_local_child(cell, "output"))
    finally:
        metrics = monitor.stop()
    media = probe_media(ffprobe, artifact)
    cache = execution_cache_evidence(messages, cache_control)
    vram_gate = metrics["peak_vram_gib"] <= 7.5
    host_gate = metrics["peak_host_ram_gib"] <= 28.0
    physical_vram_gate = metrics["peak_vram_gib"] <= physical_vram_gib + 1e-6
    physical_host_gate = metrics["min_host_ram_available_gib"] >= 4.0
    media_gate = media_matches_contract(media, plan["video_contract"])
    machine_gate = bool(physical_vram_gate and physical_host_gate and media_gate and cache["fresh_execution_proved"])
    return {
        "label": label,
        "prompt_id": prompt_id,
        "queued_prompt_sha256": hashlib.sha256(canonical_bytes(queued_prompt)).hexdigest(),
        "wall_s": round(time.monotonic() - started, 3),
        "baseline_vram_gib": baseline_vram,
        "baseline_host_ram_gib": baseline_host,
        **metrics,
        **{key: value for key, value in media.items() if key not in metrics},
        "resource_monitor": metrics,
        "media": media,
        "cache": cache,
        "history_output_keys": sorted(outputs),
        "vram_gate_pass": vram_gate,
        "host_ram_gate_pass": host_gate,
        "physical_vram_gate_pass": physical_vram_gate,
        "physical_host_ram_gate_pass": physical_host_gate,
        "minimum_host_ram_available_gib": metrics["min_host_ram_available_gib"],
        "comfortable_target_met": bool(vram_gate and host_gate),
        "media_gate_pass": media_gate,
        "machine_gate_pass": machine_gate,
        "artifact_relative_path": str(artifact.relative_to(cell)),
    }


def create_cell(run_id: str) -> Path:
    local_root = _safe_local_root(create=True)
    cells_root = _safe_local_child(local_root, "cells")
    cells_root.mkdir(parents=True, exist_ok=True)
    plan_root = _safe_local_child(cells_root, PLAN_ID)
    plan_root.mkdir(parents=True, exist_ok=True)
    cell = _safe_local_child(plan_root, run_id)
    cell.mkdir(parents=False, exist_ok=False)
    return cell


def prepare_cell(admission: Mapping[str, Any], cell: Path) -> dict[str, str]:
    for name in ("input", "output", "user", "logs", "base"):
        _safe_local_child(cell, name).mkdir(parents=True, exist_ok=False)
    # ComfyUI 0.32 performs its pre-startup custom-node scan against the
    # base-directory's default custom_nodes path before it incorporates the
    # extra model-paths configuration.  Keep that default root empty and
    # private to this cell; the only admitted provider remains the separately
    # validated KJNodes directory named in model_paths.yaml below.
    _safe_local_child(_safe_local_child(cell, "base"), "custom_nodes").mkdir(
        parents=False, exist_ok=False
    )
    model_yaml = _safe_local_child(cell, "model_paths.yaml")
    model_yaml.write_text(
        build_model_paths_yaml(
            admission["model_roots"], Path(admission["comfy_root"]) / "custom_nodes"
        ),
        encoding="utf-8",
        newline="\n",
    )
    if model_yaml.read_bytes().startswith(b"\xef\xbb\xbf"):
        raise RunnerError("generated model-paths config unexpectedly has a BOM")
    return _copy_fixture(admission["plan"], cell)


def _admission_receipt(
    admission: Mapping[str, Any],
    cell: Path,
    live: Mapping[str, Any],
    argv: Sequence[str],
    fixture_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    model_yaml = _safe_local_child(cell, "model_paths.yaml")
    return {
        "receipt_schema_version": 1,
        "kind": "physical_4060_h3_admission",
        "scope": SCOPE,
        "status": "ADMITTED_NO_PROMPT_QUEUED",
        "profile_id": PROFILE_ID,
        "profile_sha256": admission["profile_sha256"],
        "plan_id": PLAN_ID,
        "plan_sha256": admission["plan_sha256"],
        "launch_config_sha256": admission["launch_sha256"],
        "runner_sha256": sha256_file(RUNNER_PATH),
        "lock_runner_sha256": sha256_file(Path(__file__).with_name("locks_4060.py")),
        "comfyui": admission["comfy_git"],
        "kjnodes": {
            "root": str(admission["kjnodes_root"]),
            "loaded_root": str(admission["loaded_kjnodes_root"]),
            **admission["kjnodes_git"],
            "init_py_sha256": sha256_file(admission["kjnodes_root"] / "__init__.py"),
        },
        "model_manifest": list(admission["model_manifest"]),
        "ffprobe": dict(admission["ffprobe_observed"]),
        "model_paths_sha256": sha256_file(model_yaml),
        "canonical_argv": list(argv),
        "canonical_argv_sha256": hashlib.sha256(canonical_bytes(list(argv))).hexdigest(),
        "live_boot": dict(live),
        "fixture_sha256s": dict(fixture_sha256s),
        "cache_runtime_sha256s": dict(admission["cache_runtime_sha256s"]),
        "policy": {"listener": LISTENER, "port": PORT, "sage_attention": "absent", "manager": "absent", "reserve_vram": "absent", "pinned_memory": "disabled", "network": "offline environment configured", "cuda_visible_devices": "enrolled GPU UUID"},
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def finalize_cell_receipts(
    *,
    cell: Path,
    run_id: str,
    caught: Exception | None,
    shutdown: Mapping[str, Any],
    admission_payload: dict[str, Any] | None,
    run_payload: dict[str, Any] | None,
    result: Mapping[str, Any],
    canonical_argv: Sequence[str] | None,
    live: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Write terminal immutable receipts only after shutdown has been attempted.

    A successful admission/run receipt is deliberately impossible until an
    owned-server shutdown receipt exists and says ``success: true``.  Any
    earlier failure receives its own terminal receipt instead; historical
    receipt bytes are never changed.
    """
    shutdown_path = _safe_local_child(cell, "shutdown.json")
    shutdown_sha = _write_exclusive_json(shutdown_path, shutdown)
    if caught is None and shutdown.get("success") and admission_payload is not None:
        admission_payload["shutdown"] = dict(shutdown)
        admission_payload["shutdown_sha256"] = shutdown_sha
        admission_sha = _write_exclusive_json(
            _safe_local_child(cell, "admission.json"), admission_payload
        )
        finalized = dict(result)
        if run_payload is not None:
            run_payload["admission_sha256"] = admission_sha
            run_payload["shutdown"] = dict(shutdown)
            run_payload["shutdown_sha256"] = shutdown_sha
            run_sha = _write_exclusive_json(_safe_local_child(cell, "run.json"), run_payload)
            finalized = {
                "status": run_payload["status"],
                "run_id": run_id,
                "cell": str(cell),
                "admission_sha256": admission_sha,
                "run_sha256": run_sha,
                "shutdown": dict(shutdown),
            }
        else:
            finalized.update({"admission_sha256": admission_sha, "shutdown": dict(shutdown)})
        return finalized
    failure = {
        "receipt_schema_version": 1,
        "kind": "physical_4060_h3_failure",
        "scope": SCOPE,
        "status": "BLOCKED_OR_FAILED",
        "run_id": run_id,
        "error": str(caught) if caught is not None else "owned server shutdown proof failed",
        "shutdown": dict(shutdown),
        "shutdown_sha256": shutdown_sha,
        "canonical_argv": list(canonical_argv) if canonical_argv is not None else None,
        "live_boot": dict(live) if isinstance(live, Mapping) else None,
        "admission_candidate_sha256": (
            hashlib.sha256(canonical_bytes(admission_payload)).hexdigest()
            if admission_payload is not None
            else None
        ),
    }
    failure_sha = _write_exclusive_json(_safe_local_child(cell, "failure.json"), failure)
    return {
        "status": "BLOCKED_OR_FAILED",
        "run_id": run_id,
        "cell": str(cell),
        "failure_sha256": failure_sha,
        "shutdown": dict(shutdown),
    }


def execute(profile_id: str, *, run_sequence: bool) -> dict[str, Any]:
    admission = validate_admission_inputs(profile_id)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    cell: Path | None = None
    server: OwnedServer | None = None
    shutdown: dict[str, Any] = {"success": False, "reason": "not started"}
    result: dict[str, Any] = {}
    caught: Exception | None = None
    admission_payload: dict[str, Any] | None = None
    run_payload: dict[str, Any] | None = None
    live: Mapping[str, Any] | None = None
    canonical_argv: list[str] | None = None
    fixture_sha256s: dict[str, str] | None = None
    with BenchLease(_safe_local_root(create=True)):
        try:
            cell = create_cell(run_id)
            fixture_sha256s = prepare_cell(admission, cell)
            canonical_argv = build_launch_argv(admission, cell)
            server = OwnedServer(
                canonical_argv, cell, admission["plan"], admission["gpu_uuid"]
            )
            live = server.start()
            _verify_fixture_readback(admission["plan"])
            admission_payload = _admission_receipt(
                admission, cell, live, canonical_argv, fixture_sha256s
            )
            admission_payload["status"] = (
                "ADMITTED_FOR_SEQUENCE" if run_sequence else "ADMITTED_NO_PROMPT_QUEUED"
            )
            if not run_sequence:
                result = {
                    "status": "ADMITTED_NO_PROMPT_QUEUED",
                    "run_id": run_id,
                    "cell": str(cell),
                }
            else:
                legs = []
                observed_gpu = admission["preflight"].get("observed", {}).get("selected_gpu", {})
                observed_ram = admission["preflight"].get("observed", {}).get("host_ram", {})
                physical_vram_gib = float(observed_gpu.get("memory_total_mib", 0)) / 1024.0
                physical_host_ram_gib = float(observed_ram.get("total_gib", 0))
                if physical_vram_gib <= 0 or physical_host_ram_gib <= 0:
                    raise RunnerError("profile preflight omitted physical hardware capacity")
                for label in SEQUENCE:
                    leg = _run_leg(
                        label,
                        admission["plan"],
                        cell,
                        physical_vram_gib,
                        physical_host_ram_gib,
                        admission["gpu_uuid"],
                        admission["ffprobe"],
                    )
                    legs.append(leg)
                    if not leg["machine_gate_pass"]:
                        break
                sequence_complete = len(legs) == len(SEQUENCE)
                all_machine = sequence_complete and all(leg["machine_gate_pass"] for leg in legs)
                comfortable = all(leg["comfortable_target_met"] for leg in legs)
                run_payload = {
                    "receipt_schema_version": 1,
                    "kind": "physical_4060_h3_run_sequence",
                    "scope": SCOPE,
                    "status": (
                        "MACHINE_PASS_COMFORTABLE_AWAITING_HUMAN_REVIEW"
                        if all_machine and comfortable
                        else "MACHINE_PASS_TIGHT_8GB_AWAITING_HUMAN_REVIEW"
                        if all_machine
                        else "MACHINE_GATE_FAILED"
                    ),
                    "run_id": run_id,
                    "profile_id": PROFILE_ID,
                    "profile_sha256": admission["profile_sha256"],
                    "plan_id": PLAN_ID,
                    "plan_sha256": admission["plan_sha256"],
                    "launch_config_sha256": admission["launch_sha256"],
                    "runner_sha256": sha256_file(RUNNER_PATH),
                    "sequence_required": list(SEQUENCE),
                    "physical_capacity": {"vram_gib": physical_vram_gib, "host_ram_gib": physical_host_ram_gib},
                    "comfortable_targets": {"vram_gib_lte": 7.5, "host_ram_gib_lte": 28.0},
                    "legs": legs,
                    "human_review": "pending: no public 8GB claim without visual and audio review",
                }
        except Exception as exc:
            caught = exc
        finally:
            if server is not None:
                shutdown = server.shutdown(
                    "admission complete" if not run_sequence else "sequence complete or failed"
                )
            if cell is not None:
                try:
                    post_shutdown_manifest = verify_model_manifest(
                        admission["plan"],
                        admission["model_roots"],
                        admission["profile"]["identity"]["model_sha256s"],
                    )
                    if post_shutdown_manifest != admission["model_manifest"]:
                        raise RunnerError("admitted model manifest changed during the physical 4060 action")
                    if admission_payload is not None:
                        admission_payload["post_shutdown_model_manifest"] = post_shutdown_manifest
                except Exception as exc:
                    if caught is None:
                        caught = exc
                result = finalize_cell_receipts(
                    cell=cell,
                    run_id=run_id,
                    caught=caught,
                    shutdown=shutdown,
                    admission_payload=admission_payload,
                    run_payload=run_payload,
                    result=result,
                    canonical_argv=canonical_argv,
                    live=live,
                )
    if caught is not None:
        raise caught
    if not shutdown.get("success"):
        raise RunnerError(f"owned 4060 server cleanup was not proved: {shutdown}")
    if run_sequence and result.get("status") == "MACHINE_GATE_FAILED":
        raise RunnerError(
            "physical 4060 sequence failed a machine gate; "
            f"terminal receipt remains at {result.get('cell')}"
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated physical RTX 4060 H3 runner; never uses 5080 lab state.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (("admit", "boot and prove the 4060 lane, then shut down without a prompt"), ("run", "admit then run cold/warm-1/warm-2 H3 MIME sequence")):
        child = subparsers.add_parser(command, help=help_text)
        child.add_argument("--profile", required=True, help="only physical-rtx4060-8gb is accepted")
    args = parser.parse_args(argv)
    try:
        result = execute(args.profile, run_sequence=args.command == "run")
    except (RunnerError, LeaseError) as exc:
        parser.exit(2, f"physical-4060 runner: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
