import json

with open('recipes/ltx_2_5_t2v_path_a.json', 'r') as f:
    data = json.load(f)

# Update to purely visual prompt
data['prompt']['5']['inputs']['text'] = 'Cinematic medium shot of a furious news anchor in a dim studio, monitors flickering behind him, slow push-in. He slams both fists on the desk, papers scattering, looking extremely angry, highly detailed.'

with open('recipes/ltx_2_5_t2v_path_a_visual.json', 'w') as f:
    json.dump(data, f, indent=2)
