#!/usr/bin/env python3
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

import run_recipe

def main():
    stats = run_recipe.check_server_up_and_ownership()
    info = run_recipe.fetch_object_info()
    for cls in ['MiniMaxH3ImageToVideo', 'MiniMaxH3ReferenceToVideo', 'EmptyMiniMaxH3LatentAV']:
        if cls in info:
            print(f"=== {cls} ===")
            print(json.dumps(info[cls], indent=2))

if __name__ == "__main__":
    main()
