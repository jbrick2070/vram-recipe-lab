import json
import os
import argparse

def route_scene(scene_text, scene_type='action'):
    '''
    Routes an OTR script scene to the correct LTX 2.5 Golden T2V Recipe
    (Action Foley or Cinematic Music). LTX 2.5 is no longer used for A2V Lip Sync.
    '''
    output_recipe = 'recipes/queued_scene_render.json'
    
    if scene_type == 'action':
        print("[ROUTER] Route A Selected: Dynamic Action Foley (8-step T2V)")
        template = 'recipes/ltx_2_5_golden_t2v_action_foley.json'
        modifier = "ambient room tone, cinematic motion. No speech, no voices, pure action."
        
    elif scene_type == 'mood':
        print("[ROUTER] Route B Selected: Cinematic Music & Mood (8-step T2V)")
        template = 'recipes/ltx_2_5_golden_t2v_cinematic_music.json'
        modifier = "tense sci-fi soundtrack playing, orchestral swells, mysterious atmosphere."
        
    else:
        print(f"[ROUTER] Unknown route: {scene_type}")
        return

    if not os.path.exists(template):
        print(f"Error: Template {template} not found.")
        return

    with open(template, 'r') as f:
        data = json.load(f)
        
    # Inject prompt logic
    final_prompt = f"{scene_text} {modifier}"
    
    if '5' in data['prompt']:
        data['prompt']['5']['inputs']['text'] = final_prompt
        
    with open(output_recipe, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"[ROUTER] Successfully queued scene to {output_recipe}")
    print(f"         Final Prompt: {final_prompt}")
    print("[POST-PROCESS] Note: Remember to duck native audio ratio when muxing TTS.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OTR Engine Scene Router')
    parser.add_argument('--scene', type=str, required=True, help='The scene description')
    parser.add_argument('--type', type=str, choices=['action', 'mood'], default='action')
    
    args = parser.parse_args()
    route_scene(args.scene, args.type)
