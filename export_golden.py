import json

# 1. Golden Lip Sync (Static)
with open('recipes/ltx_2_5_a2v_gguf_q5.json', 'r') as f:
    a2v_data = json.load(f)
# Ensure prompt is static
a2v_data['prompt']['5']['inputs']['text'] = 'Close-up portrait of a brutal space engineer speaking the attached audio, locked-off camera, no motion, highly detailed.'
with open('recipes/ltx_2_5_golden_a2v_static_lipsync.json', 'w') as f:
    json.dump(a2v_data, f, indent=2)

# 2. Golden Action Foley (For Post-Mux TTS)
with open('recipes/ltx_2_5_t2v_path_a_visual.json', 'r') as f:
    foley_data = json.load(f)
# Ensure prompt is pure action, no speech keywords
foley_data['prompt']['5']['inputs']['text'] = 'Dynamic tracking shot of a brutal space engineer slamming his fists on the console. Papers scatter. Heavy mechanical thud, ambient room tone. No speech, no voices.'
with open('recipes/ltx_2_5_golden_t2v_action_foley.json', 'w') as f:
    json.dump(foley_data, f, indent=2)

# 3. Golden Cinematic Music & SFX
with open('recipes/ltx_2_5_t2v_path_a.json', 'r') as f:
    music_data = json.load(f)
# Ensure prompt explicitly calls for music
music_data['prompt']['5']['inputs']['text'] = 'Wide cinematic shot of a ruined starship interior, sparks flying. Epic orchestral tension music playing, deep bass drops, chaotic electronic sci-fi sound effects.'
with open('recipes/ltx_2_5_golden_t2v_cinematic_music.json', 'w') as f:
    json.dump(music_data, f, indent=2)
