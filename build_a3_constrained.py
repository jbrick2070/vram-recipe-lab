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

# 5. The Path A3 Constrained Motion Prompt
constrained_prompt = "close-up of a brutal space engineer speaking the attached audio, lips perfectly in sync, head and shoulders dominant in frame, sharp hand gestures at the edge of frame, intense expression, slight body lean, camera mostly locked with a subtle push-in, highly detailed"

# Find the CLIPTextEncode node (Node 5)
data['prompt']['5']['inputs']['text'] = constrained_prompt

with open('recipes/ltx_2_5_a2v_path_a3_constrained.json', 'w') as f:
    json.dump(data, f, indent=2)
