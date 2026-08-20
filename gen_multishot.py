import json
import os

base_json = 'recipes/ltx_2_5_golden_t2v_action_foley.json'
with open(base_json, 'r') as f:
    base_data = json.load(f)

# Common edits
base_data['prompt']['1']['inputs']['unet_name'] = 'LTX-2.5-Distilled-Q5_K_M.gguf'
base_data['prompt']['4']['inputs']['clip_name'] = 'gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf'
base_data['prompt']['11']['inputs']['width'] = 832
base_data['prompt']['11']['inputs']['height'] = 480
base_data['prompt']['11']['inputs']['length'] = 161
base_data['prompt']['6']['inputs']['text'] = ''
base_data['prompt']['8']['inputs']['sampler_name'] = 'euler_ancestral_cfg_pp'
base_data['prompt']['10']['inputs']['video_cfg'] = 1.0
base_data['prompt']['10']['inputs']['audio_cfg'] = 1.0

# Prompt
p_text = "A rain-streaked detective's office at night, venetian blind shadows across a cluttered desk, the detective leaning back in a worn leather chair as he speaks, cigarette smoke in the lamp's cone of light, rain drumming on the window. A hard cut transitions to a reverse angle from behind his shoulder, the same office and the same low amber lamplight, revealing a woman in a wet overcoat in the doorway, her face half-lit, the rain continuing unbroken across the cut."

# Config B logic (assuming we'll use Config B if ManualSigmas fails again, but let's just make it Config B for now, we can manually change to Config A if Config A wins the bakeoff)
config_multishot = json.loads(json.dumps(base_data))
config_multishot['prompt']['5']['inputs']['text'] = p_text
config_multishot['prompt']['7']['inputs']['latent'] = ["11", 0]

with open('recipes/plan_b_multishot.json', 'w') as f:
    json.dump(config_multishot, f, indent=2)

print("Generated Multishot JSON")
