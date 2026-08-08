#!/usr/bin/env python3
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()

t2v = json.loads((REPO_ROOT / "recipes" / "ltx_t2v_gguf.json").read_text(encoding="utf-8"))
i2v = json.loads((REPO_ROOT / "recipes" / "ltx_i2v_gguf.json").read_text(encoding="utf-8"))

tmpl_t2v = json.loads((REPO_ROOT / "research" / "comfy_templates" / "video_ltx2_3_t2v.json").read_text(encoding="utf-8"))

print("=== t2v Nodes count:", len(t2v['prompt']), "vs i2v Nodes count:", len(i2v['prompt']))

print("\n=== Nodes present in t2v vs i2v ===")
t2v_classes = {nid: n['class_type'] for nid, n in t2v['prompt'].items() if isinstance(n, dict)}
i2v_classes = {nid: n['class_type'] for nid, n in i2v['prompt'].items() if isinstance(n, dict)}

print("\nt2v node map:")
for nid, c in sorted(t2v_classes.items(), key=lambda x: int(x[0])):
    print(f"  Node {nid:2s}: {c:30s} inputs: {list(t2v['prompt'][nid].get('inputs', {}).keys())}")

print("\ni2v node map:")
for nid, c in sorted(i2v_classes.items(), key=lambda x: int(x[0])):
    print(f"  Node {nid:2s}: {c:30s} inputs: {list(i2v['prompt'][nid].get('inputs', {}).keys())}")

# Check template video_ltx2_3_t2v.json nodes
print("\n=== Template video_ltx2_3_t2v.json Subgraph Nodes ===")
sub = tmpl_t2v['definitions']['subgraphs'][0]
for n in sub['nodes']:
    print(f"  Node {n['id']}: {n['type']:30s} widgets: {n.get('widgets_values')}")
