import json

with open('recipes/ltx_2_5_t2v_path_a_visual.json', 'r') as f:
    data = json.load(f)

# Update to Pass 1 prompt with active jaw
data['prompt']['5']['inputs']['text'] = 'Dynamic tracking shot of a brutal space engineer speaking animatedly, mouth moving, highly active camera, character moving rapidly, dramatic lighting, 4k resolution.'

with open('recipes/ltx_2_5_path_b_pass1.json', 'w') as f:
    json.dump(data, f, indent=2)
