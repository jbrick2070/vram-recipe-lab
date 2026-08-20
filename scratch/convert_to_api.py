import json
import sys

def convert_webui_to_api(webui_path, out_path):
    with open(webui_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Gather all nodes and links
    # The JSON has top level nodes and links, and subgraphs with inner nodes and links.
    # LTX 2.5 workflow uses a subgraph. Let's just flatten all nodes.
    nodes = {}
    links = {}
    
    def add_links(link_list):
        for l in link_list:
            if not l: continue
            if isinstance(l, list):
                # link = [link_id, from_node, from_slot, to_node, to_slot, type]
                link_id = l[0]
                from_node = l[1]
                from_slot = l[2]
                links[link_id] = [str(from_node), from_slot]
            elif isinstance(l, dict):
                link_id = l.get("id")
                from_node = l.get("origin_id")
                from_slot = l.get("origin_slot")
                if link_id is not None:
                    links[link_id] = [str(from_node), from_slot]

    def add_nodes(node_list):
        for n in node_list:
            nodes[str(n["id"])] = n

    add_nodes(data.get("nodes", []))
    add_links(data.get("links", []))
    
    if "definitions" in data and "subgraphs" in data["definitions"]:
        for sg in data["definitions"]["subgraphs"]:
            add_nodes(sg.get("nodes", []))
            add_links(sg.get("links", []))

    # 2. Build API prompt
    prompt = {}
    for node_id, n in nodes.items():
        # Skip subgraph wrapper nodes
        if n.get("type", "").startswith("subgraph"):
            continue
            
        class_type = n["type"]
        inputs = {}
        
        # Add widgets
        if "widgets_values" in n:
            widgets = n["widgets_values"]
            # ComfyUI frontend maps widgets by order. But wait, how do we know widget names?
            # Usually in API format, widgets and inputs are both in the "inputs" dict.
            # Without knowing the widget names, it's hard. But wait, ComfyUI WebUI JSON does NOT store widget names!
            pass

    # Wait, if WebUI JSON doesn't store widget names for widgets_values, how does the frontend generate the API prompt?
    # The frontend has the node definitions (which it fetches from /object_info) and matches the array index to the input name!
    print("Fetching object_info to map widget names...")
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:8199/object_info")
        with urllib.request.urlopen(req) as response:
            object_info = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print("Error fetching object_info:", e)
        return

    for node_id, n in nodes.items():
        if "type" not in n: continue
        class_type = n["type"]
        if class_type not in object_info:
            continue
            
        node_def = object_info[class_type]
        input_def = node_def.get("input", {})
        
        # required inputs
        required = input_def.get("required", {})
        optional = input_def.get("optional", {})
        all_inputs = list(required.keys()) + list(optional.keys())
        
        # categorize into links vs widgets
        # A widget is usually an input whose type is a list (options) or string/int/float, but NOT a standard COMY type like MODEL.
        # Actually, ComfyUI frontend maps widgets_values to the sequential order of widgets.
        
        node_inputs = {}
        
        # 1. Map linked inputs
        if "inputs" in n:
            for inp in n["inputs"]:
                if "link" in inp and inp["link"] is not None:
                    link_id = inp["link"]
                    if link_id in links:
                        node_inputs[inp["name"]] = links[link_id]

        # 2. Map widgets
        if "widgets_values" in n:
            widget_vals = n["widgets_values"]
            widget_idx = 0
            for inp_name, inp_type in required.items():
                # If it's already linked, it's not a widget (unless it was converted, but usually it's not in widgets_values)
                # In ComfyUI, things that can be widgets are types like "INT", "FLOAT", "STRING", "BOOLEAN", or list.
                if isinstance(inp_type, list) and isinstance(inp_type[0], list):
                    pass # Combo box
                elif isinstance(inp_type, list) and inp_type[0] in ["INT", "FLOAT", "STRING", "BOOLEAN"]:
                    pass
                else:
                    # It's a standard link type like MODEL, VAE, etc.
                    continue
                    
                if widget_idx < len(widget_vals):
                    # check if this input was overridden by a link
                    if inp_name not in node_inputs:
                        node_inputs[inp_name] = widget_vals[widget_idx]
                    widget_idx += 1
            
            # do the same for optional
            for inp_name, inp_type in optional.items():
                if isinstance(inp_type, list) and (isinstance(inp_type[0], list) or inp_type[0] in ["INT", "FLOAT", "STRING", "BOOLEAN"]):
                    if widget_idx < len(widget_vals):
                        if inp_name not in node_inputs:
                            node_inputs[inp_name] = widget_vals[widget_idx]
                        widget_idx += 1

        prompt[node_id] = {
            "class_type": class_type,
            "inputs": node_inputs
        }

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(prompt, f, indent=2)
    print("Successfully created API prompt at", out_path)

if __name__ == "__main__":
    convert_webui_to_api("scratch/ltx_2.5_gguf_workflow.json", "recipes/ltx_2_5_t2v_gguf.json")
