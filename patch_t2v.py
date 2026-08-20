import json

with open('recipes/ltx_2_5_t2v_gguf.json', 'r') as f:
    data = json.load(f)

data['prompt']['90'] = {
    'class_type': 'LTXVModalityGuidance',
    'inputs': {
        'model': ['1', 0],
        'modality_scale': 3.0,  # Standard baseline scale
        'start_percent': 0.0,
        'end_percent': 1.0
    }
}
data['prompt']['10']['inputs']['model'] = ['90', 0]

with open('recipes/ltx_2_5_t2v_gguf.json', 'w') as f:
    json.dump(data, f, indent=2)
