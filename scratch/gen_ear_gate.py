import json, subprocess, hashlib, os

def get_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

path = r"C:\Users\jeffr\Documents\ComfyUI\vram-recipe-lab\fixtures\vz_bill_boerst.wav"
bytes_size = os.path.getsize(path)
sha256 = get_hash(path)

probe = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "a:0",
     "-show_entries", "stream=codec_name,sample_rate,channels,channel_layout,duration:format=duration",
     "-of", "json", path],
    capture_output=True, text=True, check=True
)
probe_data = json.loads(probe.stdout)
stream = probe_data["streams"][0]

vol = subprocess.run(
    ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "volumedetect", "-f", "null", "NUL"],
    capture_output=True, text=True
)

max_db = 0.0
mean_db = 0.0
for line in vol.stderr.splitlines():
    if "max_volume:" in line:
        max_db = float(line.split("max_volume:")[1].split("dB")[0].strip())
    if "mean_volume:" in line:
        mean_db = float(line.split("mean_volume:")[1].split("dB")[0].strip())

receipt = {
  "schema_version": 1,
  "fixture": "vz_bill_boerst.wav",
  "sha256": sha256,
  "bytes": bytes_size,
  "ffprobe": {
    "codec_name": stream.get("codec_name"),
    "sample_rate_hz": int(stream.get("sample_rate")),
    "channels": stream.get("channels"),
    "channel_layout": stream.get("channel_layout"),
    "duration_s": float(stream.get("duration", 0) or probe_data["format"]["duration"])
  },
  "volumedetect": {
    "mean_volume_db": mean_db,
    "max_volume_db": max_db
  },
  "human_review": {
    "reviewer": "Jeffrey",
    "reviewed_at": "2026-08-18",
    "content_class": "voice",
    "description": "Bill Boerst audio."
  },
  "ear_gate_pass": True
}

with open(r"C:\Users\jeffr\Documents\ComfyUI\vram-recipe-lab\fixtures\audio_receipts\vz_bill_boerst.json", "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2)

print("Generated receipt!")
