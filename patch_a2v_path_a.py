import json

with open('recipes/ltx_2_5_a2v_gguf_q5.json', 'r') as f:
    data = json.load(f)

# PATH A Settings on A2V Lip Sync Graph
# 1. Modality scale to 1.0
data['prompt']['90']['inputs']['modality_scale'] = 1.0

# 2. DualCFG to 1.0
data['prompt']['10']['inputs']['video_cfg'] = 1.0
data['prompt']['10']['inputs']['audio_cfg'] = 1.0

# 3. Sampler to euler_ancestral
data['prompt']['8']['inputs']['sampler_name'] = 'euler_ancestral'

# 4. LTXVScheduler steps to 8
data['prompt']['7']['inputs']['steps'] = 8

# 5. Intense action prompt that previously broke lip sync
data['prompt']['20']['inputs']['text'] = 'Dynamic tracking shot of a brutal space engineer aggressively exclaiming, highly active camera, character moving rapidly, dramatic lighting.'

with open('recipes/ltx_2_5_a2v_path_a_action.json', 'w') as f:
    json.dump(data, f, indent=2)
