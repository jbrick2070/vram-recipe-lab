import os
import hashlib
import subprocess
import shutil
import time

MODELS = {
    "diffusion_models": [
        ("ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors?download=true")
    ],
    "vae": [
        ("ltx-2.5-video-vae-bf16.safetensors", "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-video-vae-bf16.safetensors?download=true"),
        ("ltx-2.5-audio-vae-bf16.safetensors", "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-audio-vae-bf16.safetensors?download=true")
    ],
    "text_encoders": [
        ("gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors?download=true"),
        ("gemma4_e2b_it_bf16.safetensors", "https://huggingface.co/Comfy-Org/gemma-4/resolve/main/text_encoders/gemma4_e2b_it_bf16.safetensors?download=true")
    ],
    "latent_upscale_models": [
        ("ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors", "https://huggingface.co/Lightricks/LTX-2.5/resolve/main/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors?download=true")
    ]
}

QUARANTINE_DIR = r"C:\ComfyUI-Models\quarantine"
MODELS_ROOT = r"C:\ComfyUI-Models"

def compute_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(1024*1024), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def download_file(url, target_path):
    token = os.environ.get("HF_TOKEN")
    # Use -C - to resume if partial
    cmd = ["curl.exe", "-C", "-", "-L", "-o", target_path]
    if token:
        cmd.extend(["-H", f"Authorization: Bearer {token}"])
    cmd.append(url)
    
    subprocess.run(cmd, check=True)

def main():
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    manifest_entries = []
    
    for category, files in MODELS.items():
        for filename, url in files:
            print(f"\nProcessing {filename}...")
            
            target_dir = os.path.join(MODELS_ROOT, category)
            os.makedirs(target_dir, exist_ok=True)
            
            final_path = os.path.join(target_dir, filename)
            
            if os.path.exists(final_path) and os.path.getsize(final_path) > 10 * 1024 * 1024:
                print(f"Already exists (and is >10MB): {final_path}")
                # We will still hash it for the manifest
                file_hash = compute_sha256(final_path)
                file_size = os.path.getsize(final_path)
                manifest_entries.append(f"| {filename} | {file_size} | {file_hash} | Hugging Face |")
                continue
            elif os.path.exists(final_path):
                print(f"File exists but is too small ({os.path.getsize(final_path)} bytes), deleting...")
                os.remove(final_path)
                
            quarantine_path = os.path.join(QUARANTINE_DIR, filename)
            
            print(f"Downloading to {quarantine_path}...")
            download_file(url, quarantine_path)
            print(f"Downloaded {filename}")
                
            print(f"Hashing {filename}...")
            file_hash = compute_sha256(quarantine_path)
            file_size = os.path.getsize(quarantine_path)
            
            manifest_entries.append(f"| {filename} | {file_size} | {file_hash} | Hugging Face |")
            
            print(f"Moving to {final_path}...")
            shutil.move(quarantine_path, final_path)
            
    if manifest_entries:
        print("\n--- Manifest Entries ---")
        print("\n".join(manifest_entries))
    else:
        print("All models already exist.")

if __name__ == "__main__":
    main()
