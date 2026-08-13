import subprocess
import re
import numpy as np
import wave
import sys
import os
import glob
from PIL import Image

clips = {
    'Q-CONTROL': 'h3_unconditioned_music_scene_seed42_f124_out_00003_.mp4',
    'Q2-B': 'h3_unconditioned_music_motion_small_seed42_f124_out_00002_.mp4',
    'Q2-C': 'h3_unconditioned_music_motion_large_seed42_f124_out_00002_.mp4',
    'Q3_43': 'h3_unconditioned_music_scene_seed43_f124_out_00002_.mp4',
    'Q3_44': 'h3_unconditioned_music_scene_seed44_f124_out_00002_.mp4',
    'Q3_45': 'h3_unconditioned_music_scene_seed45_f124_out_00002_.mp4',
    'Q3_46': 'h3_unconditioned_music_scene_seed46_f124_out_00002_.mp4',
    'Q4-B': 'h3_unconditioned_music_score_seed42_f124_out_00002_.mp4',
    'Q4-C': 'h3_unconditioned_music_sfx_seed42_f124_out_00002_.mp4',
    'Q5-192': 'h3_unconditioned_music_scene_seed42_f192_out_00002_.mp4',
    'Q5-277': 'h3_unconditioned_music_scene_seed42_f277_out_00002_.mp4',
}

base_dir = "outputs"
scratch_dir = "scratch"

def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout + result.stderr

results = {}

for label, filename in clips.items():
    filepath = os.path.join(base_dir, filename)
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        continue
    
    print(f"Processing {label}...")
    res = {}
    
    # 1. ffmpeg ebur128
    ebur_out = run_cmd(['ffmpeg', '-i', filepath, '-filter:a', 'ebur128', '-f', 'null', '-'])
    lufs_m = re.search(r'I:\s+([-\d\.]+)\sLUFS', ebur_out)
    lra_m = re.search(r'LRA:\s+([-\d\.]+)\sLU', ebur_out)
    tp_m = re.search(r'True peak:\s+([-\d\.]+)\sdBTP', ebur_out)
    res['LUFS'] = float(lufs_m.group(1)) if lufs_m else None
    res['LRA'] = float(lra_m.group(1)) if lra_m else None
    res['TruePeak'] = float(tp_m.group(1)) if tp_m else None

    # 2. ffmpeg silencedetect
    silence_out = run_cmd(['ffmpeg', '-i', filepath, '-af', 'silencedetect=noise=-40dB:d=0.2', '-f', 'null', '-'])
    scount_m = re.findall(r'silence_start', silence_out)
    res['SilenceCount'] = len(scount_m)
    res['SilenceTime'] = sum(float(x.group(1)) for x in re.finditer(r'silence_duration: ([\d\.]+)', silence_out))

    # 3. ffmpeg astats
    astats_out = run_cmd(['ffmpeg', '-i', filepath, '-af', 'astats=metadata=1:reset=1', '-f', 'null', '-'])
    rms_m = re.search(r'Overall RMS level ([-\d\.]+)', astats_out)
    flat_m = re.search(r'Overall Flat factor: ([-\d\.]+)', astats_out)
    pcount_m = re.search(r'Overall Peak count: (\d+)', astats_out)
    res['RMS_Overall'] = float(rms_m.group(1)) if rms_m else None
    res['FlatFactor'] = float(flat_m.group(1)) if flat_m else None
    res['PeakCount'] = int(pcount_m.group(1)) if pcount_m else None

    # 4. python/numpy on 16-bit PCM
    wav_path = os.path.join(scratch_dir, f"{label}.wav")
    run_cmd(['ffmpeg', '-y', '-i', filepath, '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1', wav_path])
    
    with wave.open(wav_path, 'r') as wf:
        n_frames = wf.getnframes()
        sr = wf.getframerate()
        audio_data = wf.readframes(n_frames)
        audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    # 50ms windows
    win_len = int(0.05 * sr)
    n_wins = len(audio) // win_len
    centroids = []
    flux = []
    prev_mag = None
    
    # 0.5s buckets for RMS
    bucket_len = int(0.5 * sr)
    n_buckets = len(audio) // bucket_len
    audio_rms = []
    for i in range(n_buckets):
        b = audio[i*bucket_len : (i+1)*bucket_len]
        audio_rms.append(np.sqrt(np.mean(b**2) + 1e-10))

    low_e, mid_e, high_e = 0, 0, 0
    for i in range(n_wins):
        window = audio[i*win_len : (i+1)*win_len]
        fft = np.fft.rfft(window)
        mag = np.abs(fft)
        freqs = np.fft.rfftfreq(win_len, 1/sr)
        
        sum_mag = np.sum(mag) + 1e-10
        centroid = np.sum(freqs * mag) / sum_mag
        centroids.append(centroid)
        
        if prev_mag is not None:
            flux.append(np.sum((mag - prev_mag)**2))
        prev_mag = mag
        
        low_e += np.sum(mag[freqs < 250]**2)
        mid_e += np.sum(mag[(freqs >= 250) & (freqs < 4000)]**2)
        high_e += np.sum(mag[freqs >= 4000]**2)

    total_e = low_e + mid_e + high_e + 1e-10
    res['LowRatio'] = low_e / total_e
    res['MidRatio'] = mid_e / total_e
    res['HighRatio'] = high_e / total_e
    res['Centroid_Mean'] = np.mean(centroids)
    res['Centroid_Std'] = np.std(centroids)
    res['Flux_Mean'] = np.mean(flux) if flux else 0

    # Periodicity score via autocorrelation
    ac = np.correlate(audio, audio, mode='full')
    ac = ac[len(ac)//2:]
    min_lag = int(0.25 * sr)
    max_lag = int(2.0 * sr)
    if len(ac) > max_lag:
        peak_idx = np.argmax(ac[min_lag:max_lag]) + min_lag
        res['Periodicity'] = ac[peak_idx] / (ac[0] + 1e-10)
    else:
        res['Periodicity'] = 0

    # 5. Alignment proxy
    # Extract frames at 2fps
    frame_dir = os.path.join(scratch_dir, f"{label}_frames")
    os.makedirs(frame_dir, exist_ok=True)
    run_cmd(['ffmpeg', '-y', '-i', filepath, '-vf', 'fps=2,scale=320:180,format=gray', os.path.join(frame_dir, 'frame_%03d.png')])
    
    frames = sorted(glob.glob(os.path.join(frame_dir, '*.png')))
    motion_energy = []
    prev_frame = None
    for f in frames:
        img = np.array(Image.open(f)).astype(float)
        if prev_frame is not None:
            diff = np.mean((img - prev_frame)**2)
            motion_energy.append(diff)
        prev_frame = img

    # Match buckets (motion_energy has one less element than frames)
    # audio_rms has one element per 0.5s bucket.
    # The first difference motion_energy[0] corresponds to the transition from bucket 0 to 1.
    # Let's just compare motion_energy to audio_rms[1:]
    min_len = min(len(motion_energy), len(audio_rms)-1)
    if min_len > 1:
        corr = np.corrcoef(motion_energy[:min_len], audio_rms[1:min_len+1])[0,1]
        res['AlignmentCorr'] = corr
    else:
        res['AlignmentCorr'] = 0
        
    results[label] = res
    print(res)

import json
with open('scratch/results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("Done!")
