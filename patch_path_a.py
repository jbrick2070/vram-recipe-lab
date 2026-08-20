import json

with open('recipes/ltx_2_5_t2v_gguf.json', 'r') as f:
    data = json.load(f)

# PATH A: DISTILLED GUIDANCE RESET

# 1. Modality scale to 1.0 (bypass effectively)
data['prompt']['90']['inputs']['modality_scale'] = 1.0

# 2. DualCFG to 1.0
data['prompt']['10']['inputs']['video_cfg'] = 1.0
data['prompt']['10']['inputs']['audio_cfg'] = 1.0

# 3. Sampler to euler_ancestral
data['prompt']['8']['inputs']['sampler_name'] = 'euler_ancestral'

# 4. LTXVScheduler steps to 8
data['prompt']['7']['inputs']['steps'] = 8

# 5. Exact flowing paragraph prompt
data['prompt']['5']['inputs']['text'] = 'Cinematic medium shot of a furious news anchor in a dim studio, monitors flickering behind him, slow push-in. He slams both fists on the desk, papers scattering, and shouts "This ends tonight!" in a harsh, strained American voice. Sharp wooden thuds land in sync with his fists, over a low newsroom hum and distant keyboard clicks. No music.'

with open('recipes/ltx_2_5_t2v_path_a.json', 'w') as f:
    json.dump(data, f, indent=2)
