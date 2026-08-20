import os
import hashlib
import shutil
from huggingface_hub import hf_hub_download

MODELS_ROOT = r"C:\ComfyUI-Models"
QUARANTINE_DIR = os.path.join(MODELS_ROOT, "quarantine")
TEXT_ENCODERS_DIR = os.path.join(MODELS_ROOT, "text_encoders")

def compute_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(1024*1024), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def main():
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    os.makedirs(TEXT_ENCODERS_DIR, exist_ok=True)
    
    filename = "gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf"
    repo_id = "elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF"
    
    print(f"Downloading {filename} from {repo_id}...")
    # HF_TOKEN is picked up automatically by huggingface_hub
    downloaded_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=QUARANTINE_DIR,
        local_dir_use_symlinks=False
    )
    
    print(f"Hashing {filename}...")
    file_hash = compute_sha256(downloaded_path)
    file_size = os.path.getsize(downloaded_path)
    manifest_entry = f"| {filename} | {file_size} | {file_hash} | Hugging Face |"
    
    final_path = os.path.join(TEXT_ENCODERS_DIR, filename)
    print(f"Moving to {final_path}...")
    if os.path.exists(final_path):
        os.remove(final_path)
    shutil.move(downloaded_path, final_path)
    
    print("\n--- Manifest Entry ---")
    print(manifest_entry)

if __name__ == "__main__":
    main()
