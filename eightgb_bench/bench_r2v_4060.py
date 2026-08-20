#!/usr/bin/env python3
"""Direct Ref2VA Character Dialogue & Lip-Sync Benchmark for the RTX 4060 Laptop (8 GB).

Runs isolated on loopback port 18299, Sage-free, no-pinned-memory, with
proper /history polling, full VRAM/RAM monitoring, and clean shutdown enforcement.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Mapping

import psutil


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = REPO_ROOT / "eightgb_bench"
LOCAL_ROOT = BENCH_ROOT / "local"
TRANSFER_ROOT = Path(r"D:\4060-transfer")
PORT = 18299
LISTENER = "127.0.0.1"
SERVER_URL = f"http://{LISTENER}:{PORT}"

MODELS = {
    "diffusion_models": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "text_encoders": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae_video": "minimax_h3_video_vae_fp16.safetensors",
    "vae_audio": "minimax_h3_audio_vae_fp32.safetensors",
}

FIXTURES = {
    "image": "portrait.png",
    "audio": "tts_dialogue.wav",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def get_vram_and_ram_gib() -> tuple[float, float, float]:
    """Returns (vram_used_gib, host_ram_used_gib, host_ram_avail_gib)."""
    vram_gib = 0.0
    try:
        smi = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        vram_gib = float(smi.stdout.strip().splitlines()[0]) / 1024.0
    except Exception:
        pass
    ram = psutil.virtual_memory()
    return vram_gib, ram.used / (1024 ** 3), ram.available / (1024 ** 3)


def build_prompt_graph() -> dict[str, Any]:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELS["diffusion_models"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODELS["text_encoders"], "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae_video"]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae_audio"]}},
        "5": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
        "6": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["7", 0]}},
        "7": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "audio_vae": ["4", 0],
                "prompt": (
                    'A cinematic 16:9 widescreen medium close shot of <Picture 1> centered in the frame, '
                    'delivering the exact line "We\'ve detected an anomalous signal on the outer perimeter." '
                    'directly to the camera with an expressive tone matching the timing and cadence of <Audio 1>. '
                    'The room background and lighting naturally fill the full 16:9 widescreen canvas edge-to-edge '
                    'with zero black bars, borders, or pillarboxing. '
                    'His lips, jaw, and facial expression must stay tightly synchronized to the audio.'
                ),
                "width": 864,
                "height": 480,
                "length": 124,
                "ref_image_size": "max",
                "ref_images.ref_image_0": ["11", 0],
                "ref_audios.ref_audio_0": ["16", 0],
            },
        },
        "8": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {"noise": ["5", 0], "guider": ["6", 0], "sampler": ["13", 0], "sigmas": ["14", 0], "latent_image": ["7", 1]},
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": 24.0, "bit_depth": 8, "audio": ["15", 0]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": FIXTURES["image"]}},
        "12": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": "h3_r2v_dialogue_4060_out", "format": "auto", "codec": "auto"}},
        "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "14": {"class_type": "BasicScheduler", "inputs": {"model": ["1", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}},
        "15": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "16": {"class_type": "LoadAudio", "inputs": {"audio": FIXTURES["audio"]}},
    }


def main() -> int:
    print("=== Starting Isolated Physical RTX 4060 Ref2VA Dialogue Benchmark ===")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    cell = LOCAL_ROOT / "cells" / "h3-r2v-dialogue-demo-f124" / run_id
    for folder in ("input", "output", "user", "logs", "base"):
        (cell / folder).mkdir(parents=True, exist_ok=True)
    (cell / "base" / "custom_nodes").mkdir(parents=True, exist_ok=True)

    # 1. Verify and copy fixtures
    fixtures_dir = REPO_ROOT / "fixtures"
    for kind, name in FIXTURES.items():
        src = fixtures_dir / name
        if not src.is_file():
            print(f"ERROR: Fixture {src} not found!")
            return 1
        shutil.copyfile(src, cell / "input" / name)
        print(f"Fixture {name}: {sha256_file(src)[:16]}... staged into cell input.")

    # 2. Write model_paths.yaml
    model_paths_content = (
        "physical_4060:\n"
        "  is_default: true\n"
        '  base_path: "C:/"\n'
        '  diffusion_models: "C:/ComfyUI-Models/diffusion_models"\n'
        '  text_encoders: "C:/ComfyUI-Models/text_encoders"\n'
        '  vae: "C:/ComfyUI-Models/vae"\n'
        f'  custom_nodes: "{str(LOCAL_ROOT / "ComfyUI" / "custom_nodes").replace(os.sep, "/")}"\n'
    )
    (cell / "model_paths.yaml").write_text(model_paths_content, encoding="utf-8")

    # 3. Launch isolated ComfyUI server
    comfy_root = LOCAL_ROOT / "ComfyUI"
    python_exe = sys.executable
    server_cmd = [
        python_exe, str(comfy_root / "main.py"),
        "--listen", LISTENER,
        "--port", str(PORT),
        "--base-directory", str(cell / "base"),
        "--input-directory", str(cell / "input"),
        "--output-directory", str(cell / "output"),
        "--user-directory", str(cell / "user"),
        "--extra-model-paths-config", str(cell / "model_paths.yaml"),
        "--disable-pinned-memory",
        "--disable-metadata",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes", "ComfyUI-KJNodes",
    ]

    log_path = cell / "logs" / "server.log"
    log_file = log_path.open("wb")
    print(f"Booting ComfyUI on port {PORT}...")
    server_proc = subprocess.Popen(
        server_cmd, stdout=log_file, stderr=subprocess.STDOUT,
        env={**os.environ, "CUDA_VISIBLE_DEVICES": "0", "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1"},
    )

    peak_vram = 0.0
    peak_ram = 0.0
    min_avail_ram = 999.0
    baseline_vram = 0.0
    baseline_ram = 0.0

    try:
        # Wait for server readiness
        ready = False
        for _ in range(60):
            time.sleep(2)
            try:
                with urllib.request.urlopen(f"{SERVER_URL}/system_stats", timeout=5) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                pass
        if not ready:
            print("ERROR: Server failed to reach ready state within 120s!")
            return 1
        print("Server is ready and answering /system_stats!")

        baseline_vram, baseline_ram, _ = get_vram_and_ram_gib()
        print(f"Baseline VRAM: {baseline_vram:.2f} GB | Baseline RAM: {baseline_ram:.2f} GB")

        # 4. Queue Ref2VA prompt
        graph = build_prompt_graph()
        payload = json.dumps({"prompt": graph, "client_id": run_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVER_URL}/prompt", data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            prompt_res = json.loads(resp.read().decode("utf-8"))
        prompt_id = prompt_res.get("prompt_id")
        print(f"Prompt queued successfully! Prompt ID: {prompt_id}")
        print("Sampling & Decoding 124 frames @ 20 steps (monitoring VRAM / RAM)...")

        # 5. Monitor execution via /history API
        started = time.monotonic()
        execution_done = False
        while time.monotonic() - started < 1800:
            time.sleep(2.0)
            cur_vram, cur_ram, avail_ram = get_vram_and_ram_gib()
            if cur_vram > peak_vram:
                peak_vram = cur_vram
            if cur_ram > peak_ram:
                peak_ram = cur_ram
            if avail_ram < min_avail_ram:
                min_avail_ram = avail_ram

            # Check ComfyUI history API
            try:
                with urllib.request.urlopen(f"{SERVER_URL}/history/{prompt_id}", timeout=5) as resp:
                    if resp.status == 200:
                        hist_data = json.loads(resp.read().decode("utf-8"))
                        if prompt_id in hist_data:
                            item = hist_data[prompt_id]
                            status_obj = item.get("status", {})
                            if status_obj.get("completed", False) or item.get("outputs"):
                                execution_done = True
                                print(f"Prompt execution completed in history API! Status: {status_obj}")
                                time.sleep(2.0)
                                break
                            elif status_obj.get("status_str") == "error":
                                print(f"Prompt failed with error: {status_obj}")
                                return 1
            except Exception:
                pass

        elapsed = time.monotonic() - started
        if not execution_done:
            print(f"ERROR: Generation timed out after {elapsed:.1f}s!")
            return 1

        # Locate completed output file
        out_files = [f for f in (cell / "output").glob("*.mp4") if f.stat().st_size > 1000]
        if not out_files:
            print("ERROR: No valid MP4 artifact found in output directory!")
            return 1

        output_mp4 = out_files[0]
        print(f"Generation & VAE decoding complete in {elapsed:.1f}s!")
        print(f"Output File: {output_mp4.name} ({output_mp4.stat().st_size} bytes)")
        print(f"Peak VRAM: {peak_vram:.2f} GB | Peak RAM: {peak_ram:.2f} GB")

        # 6. Copy output to Transfer Share
        TRANSFER_ROOT.mkdir(parents=True, exist_ok=True)
        dest_mp4 = TRANSFER_ROOT / f"h3-ref2va-dialogue-16-9-4060-{run_id}.mp4"
        shutil.copyfile(output_mp4, dest_mp4)
        shutil.copyfile(output_mp4, TRANSFER_ROOT / "h3-ref2va-dialogue-16-9-4060.mp4")
        print(f"Delivered output video to transfer share: {dest_mp4}")

        # 7. Write run receipt
        receipt = {
            "status": "MACHINE_PASS_COMFORTABLE_AWAITING_HUMAN_REVIEW" if peak_vram <= 7.5 else "MACHINE_PASS_TIGHT_8GB_AWAITING_HUMAN_REVIEW",
            "run_id": run_id,
            "workload": "864x480, 124 frames @ 24 fps, 20 steps, Ref2VA Dialogue",
            "prompt_id": prompt_id,
            "wall_clock_seconds": round(elapsed, 2),
            "peak_vram_gib": round(peak_vram, 2),
            "baseline_vram_gib": round(baseline_vram, 2),
            "peak_host_ram_gib": round(peak_ram, 2),
            "artifact_bytes": output_mp4.stat().st_size,
            "artifact_sha256": sha256_file(output_mp4),
        }
        (cell / "run.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("\n=== Benchmark Receipt ===")
        print(json.dumps(receipt, indent=2))
        return 0

    finally:
        print("Shutting down ComfyUI server process...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        log_file.close()
        print("Server process cleanly stopped.")


if __name__ == "__main__":
    sys.exit(main())
