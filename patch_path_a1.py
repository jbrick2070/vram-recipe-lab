import json

with open('recipes/ltx_2_5_a2v_path_a_action.json', 'r') as f:
    data = json.load(f)

# Remove old masking
if '14' in data['prompt']: del data['prompt']['14']
if '15' in data['prompt']: del data['prompt']['15']

# Hook Concat directly to Audio Encode
data['prompt']['30']['inputs']['audio_latent'] = ['13', 0]

# Add LTXVSetAudioVideoMaskByTime
data['prompt']['100'] = {
    'class_type': 'LTXVSetAudioVideoMaskByTime',
    'inputs': {
        'av_latent': ['30', 0],
        'positive': ['20', 0],
        'negative': ['20', 1],
        'model': ['90', 0],
        'vae': ['2', 0],
        'audio_vae': ['3', 0],
        'start_time': 0.0,
        'end_time': 10.0,
        'video_fps': 25.0,
        'mask_video': True,
        'mask_audio': False
    }
}

# Update CFG Guider to use output of mask node
data['prompt']['10']['inputs']['positive'] = ['100', 0]
data['prompt']['10']['inputs']['negative'] = ['100', 1]

# Update Sampler to use output of mask node
data['prompt']['31']['inputs']['latent_image'] = ['100', 2]

with open('recipes/ltx_2_5_a2v_path_a1_gate.json', 'w') as f:
    json.dump(data, f, indent=2)
