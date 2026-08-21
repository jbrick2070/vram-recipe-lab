import ast
import hashlib
import json
import os
import subprocess
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GGUF_NODES = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-GGUF\nodes.py"
)
PATCH_DIR = REPO_ROOT / "scratch" / "patches"
PATCH_PATH = PATCH_DIR / "ComfyUI-GGUF-CLIPLoaderGGUFCPU.patch"
PATCH_MANIFEST = PATCH_DIR / "ComfyUI-GGUF-CLIPLoaderGGUFCPU.json"
EXPECTED_BASE_CLASS_SHA256 = (
    "0ed2ae04224f7e8d3ea74d764742031ee27eb383721c4952c421b213dcf3c34b"
)
INACTIVE_LTXV_RECIPES = {
    # Historical, never-runnable probe: it requires the non-whitelisted
    # ComfyUI-LTXVideo LTXVSetAudioVideoMaskByTime node and omits four inputs
    # that node declares required.  Relabelling its loader would falsely make
    # it look supported; keep the artifact byte-shape outside this migration.
    "ltx_2_5_a2v_path_a1_gate.json",
}


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method(cls: ast.ClassDef, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_installed_cpu_loader_is_additive_and_pins_all_three_devices():
    source = GGUF_NODES.read_text(encoding="utf-8")
    tree = ast.parse(source)
    base = _class(tree, "CLIPLoaderGGUF")
    cpu = _class(tree, "CLIPLoaderGGUFCPU")

    assert [node.id for node in cpu.bases if isinstance(node, ast.Name)] == [
        "CLIPLoaderGGUF"
    ]
    base_source = ast.get_source_segment(source, base)
    assert _sha256(base_source.encode("utf-8")) == EXPECTED_BASE_CLASS_SHA256

    loader_source = ast.get_source_segment(source, _method(cpu, "load_patcher"))
    loader_tree = ast.parse(loader_source)
    model_options = next(
        keyword.value
        for node in ast.walk(loader_tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "model_options"
    )
    assert isinstance(model_options, ast.Dict)
    assert {key.value for key in model_options.keys} == {
        "custom_operations",
        "initial_device",
        "load_device",
        "offload_device",
    }
    rendered = ast.dump(loader_tree)
    assert "GGUFModelPatcher" in rendered
    assert "clone" in rendered
    assert "RuntimeError" in rendered
    assert rendered.count("Name(id='cpu'") >= 3

    mapping = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "NODE_CLASS_MAPPINGS"
            for target in node.targets
        )
    )
    assert isinstance(mapping, ast.Dict)
    entries = {
        key.value: value.id
        for key, value in zip(mapping.keys, mapping.values)
        if isinstance(key, ast.Constant) and isinstance(value, ast.Name)
    }
    assert entries["CLIPLoaderGGUF"] == "CLIPLoaderGGUF"
    assert entries["CLIPLoaderGGUFCPU"] == "CLIPLoaderGGUFCPU"


def _execute_cpu_loader(*, returned_load_device="cpu", returned_offload_device="cpu"):
    source = GGUF_NODES.read_text(encoding="utf-8")
    tree = ast.parse(source)
    cpu_class = _class(tree, "CLIPLoaderGGUFCPU")
    capture = {}
    patcher = types.SimpleNamespace(
        load_device=returned_load_device,
        offload_device=returned_offload_device,
    )
    clip = types.SimpleNamespace(patcher=object())

    def load_text_encoder_state_dicts(**kwargs):
        capture.update(kwargs)
        return clip

    namespace = {
        "CLIPLoaderGGUF": type("CLIPLoaderGGUF", (), {}),
        "torch": types.SimpleNamespace(device=lambda value: value),
        "comfy": types.SimpleNamespace(
            sd=types.SimpleNamespace(
                load_text_encoder_state_dicts=load_text_encoder_state_dicts
            )
        ),
        "folder_paths": types.SimpleNamespace(
            get_folder_paths=lambda _name: ["embeddings"]
        ),
        "GGMLOps": object(),
        "GGUFModelPatcher": types.SimpleNamespace(clone=lambda _old: patcher),
        "logging": types.SimpleNamespace(info=lambda *_args, **_kwargs: None),
    }
    module = ast.Module(body=[cpu_class], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(GGUF_NODES), "exec"), namespace)
    loader = namespace["CLIPLoaderGGUFCPU"]()
    result = loader.load_patcher(["clip.gguf"], "ltxv", [{"weight": 1}])
    return result, capture


def test_cpu_loader_execution_passes_cpu_for_every_placement_and_clones():
    clip, capture = _execute_cpu_loader()
    assert clip.patcher.load_device == "cpu"
    assert clip.patcher.offload_device == "cpu"
    assert capture["clip_type"] == "ltxv"
    assert capture["state_dicts"] == [{"weight": 1}]
    assert capture["embedding_directory"] == ["embeddings"]
    assert capture["model_options"]["initial_device"] == "cpu"
    assert capture["model_options"]["load_device"] == "cpu"
    assert capture["model_options"]["offload_device"] == "cpu"
    assert capture["model_options"]["custom_operations"] is not None


def test_cpu_loader_fails_before_forward_when_patcher_placement_drifts():
    try:
        _execute_cpu_loader(returned_load_device="cuda:0")
    except RuntimeError as exc:
        assert "requires CPU load/offload placement" in str(exc)
        assert "load_device=cuda:0" in str(exc)
    else:
        raise AssertionError("GPU placement was accepted by the CPU-pinned loader")


def test_patch_receipt_matches_the_installed_target_and_has_no_bom():
    manifest_bytes = PATCH_MANIFEST.read_bytes()
    patch_bytes = PATCH_PATH.read_bytes()
    target_bytes = GGUF_NODES.read_bytes()
    assert not manifest_bytes.startswith(b"\xef\xbb\xbf")
    assert not patch_bytes.startswith(b"\xef\xbb\xbf")
    assert not target_bytes.startswith(b"\xef\xbb\xbf")

    manifest = json.loads(manifest_bytes.decode("utf-8"))
    assert _sha256(target_bytes) == manifest["post_patch_sha256"]
    assert manifest["baseline_sha256"] != manifest["post_patch_sha256"]
    patch_text = patch_bytes.decode("utf-8")
    assert "+class CLIPLoaderGGUFCPU(CLIPLoaderGGUF):" in patch_text
    assert '+    "CLIPLoaderGGUFCPU": CLIPLoaderGGUFCPU,' in patch_text
    assert patch_text.count('"load_device": cpu') == 1
    assert patch_text.count('"offload_device": cpu') == 1


def test_patch_recreates_the_installed_logical_source(tmp_path):
    post = GGUF_NODES.read_text(encoding="utf-8")
    start = post.index("class CLIPLoaderGGUFCPU")
    end = post.index("class DualCLIPLoaderGGUF", start)
    baseline = post[:start] + post[end:]
    baseline = baseline.replace(
        '    "CLIPLoaderGGUFCPU": CLIPLoaderGGUFCPU,\n', ""
    )
    (tmp_path / "nodes.py").write_text(baseline, encoding="utf-8", newline="\n")

    proc = subprocess.run(
        ["git", "apply", str(PATCH_PATH)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "nodes.py").read_text(encoding="utf-8") == post


def _assert_ltxv_recipes_use_cpu_loader(paths):
    covered = []
    for path in sorted(paths):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        data = json.loads(raw.decode("utf-8"))
        prompt = data.get("prompt", data)
        loaders = [
            node
            for node in prompt.values()
            if isinstance(node, dict)
            and node.get("class_type")
            in {"CLIPLoaderGGUF", "CLIPLoaderGGUFCPU"}
            and node.get("inputs", {}).get("type") == "ltxv"
        ]
        if not loaders:
            continue
        if path.name in INACTIVE_LTXV_RECIPES:
            assert loaders[0]["class_type"] == "CLIPLoaderGGUF", path
            continue
        covered.append(path)
        assert len(loaders) == 1, path
        assert loaders[0]["class_type"] == "CLIPLoaderGGUFCPU", path
        assert set(loaders[0]["inputs"]) == {"clip_name", "type"}, path

    return covered


def test_every_tracked_ltxv_recipe_uses_the_cpu_loader_without_input_drift():
    proc = subprocess.run(
        ["git", "ls-files", "recipes/*.json", "recipes/**/*.json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    paths = [REPO_ROOT / row for row in proc.stdout.splitlines() if row]
    covered = _assert_ltxv_recipes_use_cpu_loader(paths)
    assert len(covered) == 25


def test_present_untracked_ltxv_recipes_are_cpu_pinned_too():
    if os.environ.get("LAB_AUDIT_UNTRACKED_LTXV") != "1":
        pytest.skip(
            "opt-in dirty-worktree diagnostic; set LAB_AUDIT_UNTRACKED_LTXV=1"
        )
    proc = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "recipes/*.json",
            "recipes/**/*.json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    paths = [REPO_ROOT / row for row in proc.stdout.splitlines() if row]
    _assert_ltxv_recipes_use_cpu_loader(paths)


def test_golden_generator_emits_the_cpu_loader():
    source = (REPO_ROOT / "gen_golden_i2v.py").read_text(encoding="utf-8")
    assert '"class_type": "CLIPLoaderGGUFCPU"' in source
    assert '"class_type": "CLIPLoaderGGUF"' not in source
    assert "encoding='utf-8'" in source
    assert "newline='\\n'" in source
