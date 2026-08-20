import json

# A: OTR Static Lip Sync
with open('recipes/ltx_2_5_golden_a2v_static_lipsync.json', 'r') as f:
    a2v_data = json.load(f)
a2v_data['prompt']['5']['inputs']['text'] = '1950s cinematic close-up of a rugged space captain speaking the attached audio into a retro radio microphone. Locked-off camera, entirely static shot, no motion, highly detailed, dramatic noir lighting.'
with open('recipes/ltx_2_5_golden_a2v_static_lipsync.json', 'w') as f:
    json.dump(a2v_data, f, indent=2)

# B: OTR Action Foley
with open('recipes/ltx_2_5_golden_t2v_action_foley.json', 'r') as f:
    foley_data = json.load(f)
foley_data['prompt']['5']['inputs']['text'] = '1950s cinematic tracking shot of a rugged space captain frantically repairing a smoking control console. Sparks flying, heavy mechanical clanking, electric buzz, ambient room tone. No speech, no voices, pure action.'
with open('recipes/ltx_2_5_golden_t2v_action_foley.json', 'w') as f:
    json.dump(foley_data, f, indent=2)

# C: OTR Cinematic Music
with open('recipes/ltx_2_5_golden_t2v_cinematic_music.json', 'r') as f:
    music_data = json.load(f)
music_data['prompt']['5']['inputs']['text'] = '1950s cinematic wide shot of a retro silver rocket ship stranded on a desolate alien landscape. Tense, eerie theremin sci-fi soundtrack playing, orchestral swells, mysterious atmosphere.'
with open('recipes/ltx_2_5_golden_t2v_cinematic_music.json', 'w') as f:
    json.dump(music_data, f, indent=2)
