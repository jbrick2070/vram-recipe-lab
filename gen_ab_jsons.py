import json

base_json = 'recipes/ltx_2_5_golden_t2v_action_foley.json'
with open(base_json, 'r') as f:
    base_data = json.load(f)

# Use Q3 model to stay safely under 14.5 GB
base_data['prompt']['1']['inputs']['unet_name'] = 'LTX-2.5-Distilled-Q3_K_M.gguf'
base_data['prompt']['4']['inputs']['clip_name'] = 'gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf'
base_data['prompt']['11']['inputs']['width'] = 832
base_data['prompt']['11']['inputs']['height'] = 480
base_data['prompt']['11']['inputs']['length'] = 97
base_data['prompt']['6']['inputs']['text'] = ''
base_data['prompt']['8']['inputs']['sampler_name'] = 'euler_ancestral_cfg_pp'

p_text = '1950s cinematic slow dolly, low-motion noir interior. No speech, no voices.'

# CONFIG A (Manual Sigmas)
config_a = json.loads(json.dumps(base_data))
config_a['prompt']['5']['inputs']['text'] = p_text
config_a['prompt']['7'] = {
    "class_type": "ManualSigmas",
    "inputs": {
        "sigmas_string": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
    }
}
with open('recipes/ab_test/config_A_1_dolly.json', 'w') as f:
    json.dump(config_a, f, indent=2)
    
# CONFIG B (LTXVScheduler)
config_b = json.loads(json.dumps(base_data))
config_b['prompt']['5']['inputs']['text'] = p_text
config_b['prompt']['7']['inputs']['latent'] = ["11", 0]
with open('recipes/ab_test/config_B_1_dolly.json', 'w') as f:
    json.dump(config_b, f, indent=2)

print("Generated Dolly A/B JSONs with Q3 Model")
