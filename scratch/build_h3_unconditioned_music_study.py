#!/usr/bin/env python
"""Build the immutable H3 unconditioned-music study matrix.

The default invocation is read-only and prints the exact build plan.  ``--write``
creates missing recipes, but never replaces an existing path.  Every recipe is
derived from the current flat-dotted-V3 ``h3_r2v_best`` prompt graph; the old
nested-reference artifact is retained only as a confounded historical anchor.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
SOURCE = RECIPES / "h3_r2v_best.json"
SOURCE_SHA256 = "20e584cc016bdc5bdb857b00923c7ae838174724e3c20be0dfc322a809392eda"

BASE_PROMPT = (
    "Use <Picture 1> as the exact character identity and appearance reference. "
    "Place that person in a vintage radio control room under warm analog lighting; "
    "preserve their face, hair, clothing, and proportions while the camera makes "
    "a slow cinematic move."
)
SMALL_MOTION_PROMPT = (
    "Use <Picture 1> as the exact character identity and appearance reference. "
    "Place that person in a vintage radio control room under warm analog lighting; "
    "preserve their face, hair, clothing, and proportions. In a wordless sequence, "
    "the person reaches for a console dial, turns it with one hand, leans in to "
    "listen, then reacts with a visible change of posture and expression. Use a "
    "simple medium camera view that keeps the body and hands clearly visible."
)
LARGE_MOTION_PROMPT = (
    "Use <Picture 1> as the exact character identity and appearance reference. "
    "Place that person in a vintage radio control room under warm analog lighting; "
    "preserve their face, hair, clothing, and proportions. In a wordless physical "
    "beat with a clear start, middle, and end, the person crosses to the console, "
    "urgently works several large controls with both hands, recoils as the equipment "
    "flares to life, then regains composure and decisively throws a master switch. "
    "Use a simple medium-wide camera view that keeps the full action, body, and hands "
    "clearly visible."
)
SCORE_PROMPT = BASE_PROMPT + (
    " The model-native soundtrack is a warm, wordless orchestral score."
)
SFX_PROMPT = BASE_PROMPT + (
    " Generate synchronized diegetic sound effects only, with no dialogue, no "
    "intelligible speech, no voices, no vocals, and no music."
)

FORBIDDEN_JOB0_WORDS = ("restrained", "slow", "stable", "subtle")
SHARED_CONTROL = "h3_unconditioned_music_scene_seed42_f124"

SOURCE_EVIDENCE = {
    "current_flat_v3_recipe": {
        "path": "recipes/h3_r2v_best.json",
        "sha256": SOURCE_SHA256,
    },
    "current_flat_v3_warm_receipt": {
        "path": "results/h3_r2v_best_run4.json",
        "sha256": "f9844aa215302e7f7828e707ae41cd2d9f584953efabe17745c3168d827f3b81",
    },
    "current_flat_v3_artifact": {
        "path": "outputs/h3_r2v_best_out_00004_.mp4",
        "sha256": "b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed",
        "ear_verdict": "not_recorded",
    },
    "confounded_positive_music_anchor": {
        "path": "outputs/h3_r2v_best_out_00001_.mp4",
        "sha256": "51d803d53a61e67d3e2dd5772f817da6edc1b8bdc5571e851463037adf2d2d5f",
        "receipt_path": "results/h3_r2v_best_run1.json",
        "receipt_sha256": "561b79dd88acf9aae9bbe19f62974a2eb59900b8fadb60592479fb1307e6c3f8",
        "recipe_sha256": "599718d4ee5b1a04309a4352cded8167c4e51075a9f858bdbf3468a53aae6a4e",
        "disposition": (
            "lineage/human anchor only: its obsolete nested ref_images socket was "
            "not the current flat dotted V3 picture-conditioning graph"
        ),
    },
    "directed_sfx_mime_failure": {
        "recipe_path": "recipes/h3_mime_i2v_ledger_music_closing_8s.json",
        "recipe_sha256": "8c3d5f7b193b5006a895c2e153addb6032c36cbb01e3952ff98b1753bfb2e7ca",
        "receipt_path": "results/h3_mime_i2v_ledger_music_closing_8s_run1.json",
        "receipt_sha256": "75aadb094351446bba7804744d66901e96a1673e10d8be144287894241c7fd57",
        "comparison_path": "results/comparisons/h3_mime_unconditioned.json",
        "comparison_sha256": "eff2269b8127e6895a18adc8a883eb135d19d36e5550ca5d1e62adad326c1c61",
        "disposition": "historical hypothesis input; not reusable execution evidence",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def source_recipe() -> dict[str, Any]:
    raw = SOURCE.read_bytes()
    if sha256_bytes(raw) != SOURCE_SHA256:
        raise RuntimeError("h3_r2v_best source bytes drifted")
    payload = json.loads(raw.decode("utf-8"))
    prompt = payload["prompt"]
    inputs = prompt["7"]["inputs"]
    if (
        prompt["7"]["class_type"] != "MiniMaxH3ReferenceToVideo"
        or inputs.get("prompt") != BASE_PROMPT
        or inputs.get("width") != 1344
        or inputs.get("height") != 768
        or inputs.get("length") != 124
        or inputs.get("ref_image_size") != "match"
        or inputs.get("ref_images.ref_image_0") != ["11", 0]
        or "ref_images" in inputs
        or prompt["5"]["inputs"].get("noise_seed") != 42
        or prompt["11"]["inputs"].get("image") != "portrait.png"
        or prompt["15"]["inputs"].get("samples") != ["8", 0]
        or prompt["10"]["inputs"].get("audio") != ["15", 0]
    ):
        raise RuntimeError("h3_r2v_best flat-V3/native-audio source contract drifted")
    return payload


def evidence_receipts() -> dict[str, Any]:
    verified = copy.deepcopy(SOURCE_EVIDENCE)
    for row in verified.values():
        for path_key, sha_key in (
            ("path", "sha256"),
            ("receipt_path", "receipt_sha256"),
            ("recipe_path", "recipe_sha256"),
            ("comparison_path", "comparison_sha256"),
        ):
            if path_key not in row:
                continue
            path = ROOT / row[path_key]
            expected = row.get(sha_key)
            if not path.is_file() or expected is None or sha256_file(path) != expected:
                raise RuntimeError(f"pinned study evidence drifted: {path}")
    return verified


def cell_specs() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = [
        {
            "name": SHARED_CONTROL,
            "prompt": BASE_PROMPT,
            "seed": 42,
            "frames": 124,
            "roles": ["job0_A", "job1_seed42", "job2_A", "job3_f124"],
            "variable": "shared exact control",
        },
        {
            "name": "h3_unconditioned_music_motion_small_seed42_f124",
            "prompt": SMALL_MOTION_PROMPT,
            "seed": 42,
            "frames": 124,
            "roles": ["job0_B"],
            "variable": "prompt only versus shared control",
        },
        {
            "name": "h3_unconditioned_music_motion_large_seed42_f124",
            "prompt": LARGE_MOTION_PROMPT,
            "seed": 42,
            "frames": 124,
            "roles": ["job0_C"],
            "variable": "prompt only versus shared control",
        },
    ]
    cells.extend(
        {
            "name": f"h3_unconditioned_music_scene_seed{seed}_f124",
            "prompt": BASE_PROMPT,
            "seed": seed,
            "frames": 124,
            "roles": [f"job1_seed{seed}"],
            "variable": "noise seed only versus shared control",
        }
        for seed in (43, 44, 45, 46)
    )
    cells.extend(
        (
            {
                "name": "h3_unconditioned_music_score_seed42_f124",
                "prompt": SCORE_PROMPT,
                "seed": 42,
                "frames": 124,
                "roles": ["job2_B"],
                "variable": "prompt only versus shared control",
            },
            {
                "name": "h3_unconditioned_music_sfx_seed42_f124",
                "prompt": SFX_PROMPT,
                "seed": 42,
                "frames": 124,
                "roles": ["job2_C"],
                "variable": "prompt only versus shared control",
            },
        )
    )
    cells.extend(
        {
            "name": f"h3_unconditioned_music_scene_seed42_f{frames}",
            "prompt": BASE_PROMPT,
            "seed": 42,
            "frames": frames,
            "roles": [f"job3_f{frames}"],
            "variable": "frame length only versus shared control",
        }
        for frames in (192, 277)
    )
    return cells


def required_value_rows(seed: int, prompt_text: str, frames: int) -> list[dict[str, Any]]:
    return [
        {"node": "5", "input": "noise_seed", "equals": seed},
        {"node": "7", "input": "prompt", "equals": prompt_text},
        {"node": "7", "input": "width", "equals": 1344},
        {"node": "7", "input": "height", "equals": 768},
        {"node": "7", "input": "length", "equals": frames},
        {"node": "7", "input": "ref_image_size", "equals": "match"},
        {"node": "11", "input": "image", "equals": "portrait.png"},
    ]


def build_recipe(source: dict[str, Any], cell: dict[str, Any]) -> dict[str, Any]:
    recipe = copy.deepcopy(source)
    name = str(cell["name"])
    seed = int(cell["seed"])
    frames = int(cell["frames"])
    prompt_text = str(cell["prompt"])
    recipe["name"] = name
    recipe["tier"] = "experiment"
    recipe["blocked"] = False
    recipe["study"] = {
        "schema_version": 1,
        "campaign": "H3_UNCONDITIONED_MUSIC",
        "logical_roles": list(cell["roles"]),
        "single_variable_claim": cell["variable"],
        "source_recipe": SOURCE_EVIDENCE["current_flat_v3_recipe"],
        "source_evidence": SOURCE_EVIDENCE,
        "historical_positive_anchor_is_execution_reusable": False,
        "historical_positive_anchor_confound": (
            "nested ref_images input was not the current flat dotted V3 socket"
        ),
        "new_manager_compliant_control_required": True,
        "manager_runtime_authority": (
            "exactly one server-log [ComfyUI-Manager] network_mode: offline "
            "announcement before prompt execution"
        ),
        "quality_judgment": "out of scope; deliver native clips without judgment",
        "native_audio_policy": {
            "audio_conditioning_inputs": [],
            "external_mux": False,
            "decode": "SamplerCustomAdvanced -> VAEDecodeAudio -> CreateVideo.audio",
        },
    }
    recipe["contract"].update(
        {
            "engine": "minimax_h3",
            "mode": "r2v_unconditioned_music_study",
            "width": 1344,
            "height": 768,
            "frames": frames,
            "fps": 24.0,
            "duration_s": frames / 24.0,
            "requires_audio": True,
            "requires_manager_offline_probe": True,
            "vram_ceiling_gb": 14.5,
        }
    )
    topology = recipe["topology_contract"]
    topology["intent"] = (
        "Current flat dotted V3 MiniMax H3 Ref2VA graph with picture reference only "
        "and untouched jointly sampled native audio output"
    )
    topology["required_input_values"] = [
        row
        for row in topology["required_input_values"]
        if not (row.get("node"), row.get("input"))
        in {
            ("5", "noise_seed"),
            ("7", "prompt"),
            ("7", "width"),
            ("7", "height"),
            ("7", "length"),
            ("7", "ref_image_size"),
            ("11", "image"),
        }
    ] + required_value_rows(seed, prompt_text, frames)
    topology["intentional_divergences"] = [
        "Derived byte-for-byte from the current flat-dotted-V3 h3_r2v_best graph",
        f"Study cell uses seed {seed}, length {frames}, and its declared prompt variable",
        "The output filename prefix is unique evidence plumbing, not a generation variable",
        "No LoadAudio node or reference-audio socket exists; sampled native audio is not muxed or replaced",
    ]
    graph = recipe["prompt"]
    graph["5"]["inputs"]["noise_seed"] = seed
    graph["7"]["inputs"]["prompt"] = prompt_text
    graph["7"]["inputs"]["width"] = 1344
    graph["7"]["inputs"]["height"] = 768
    graph["7"]["inputs"]["length"] = frames
    graph["12"]["inputs"]["filename_prefix"] = f"{name}_out"
    return recipe


def validate_matrix(recipes: dict[str, dict[str, Any]]) -> None:
    if len(recipes) != 11 or SHARED_CONTROL not in recipes:
        raise RuntimeError("study must contain exactly eleven unique physical cells")
    shared = recipes[SHARED_CONTROL]
    if shared["study"]["logical_roles"] != [
        "job0_A",
        "job1_seed42",
        "job2_A",
        "job3_f124",
    ]:
        raise RuntimeError("shared-control logical-role reuse drifted")
    for name, recipe in recipes.items():
        prompt = recipe["prompt"]
        inputs = prompt["7"]["inputs"]
        classes = [row["class_type"] for row in prompt.values()]
        if (
            "LoadAudio" in classes
            or "AudioAdjustVolume" in classes
            or "TrimAudioDuration" in classes
            or any(key.startswith("ref_audio") or "audio" in key for key in inputs if key != "audio_vae")
            or prompt["15"]["inputs"] != {"samples": ["8", 0], "vae": ["4", 0]}
            or prompt["10"]["inputs"].get("audio") != ["15", 0]
            or inputs.get("ref_images.ref_image_0") != ["11", 0]
            or "ref_images" in inputs
        ):
            raise RuntimeError(f"{name} is not flat-V3 picture-only/native-audio")
        if name.endswith("motion_small_seed42_f124") or name.endswith(
            "motion_large_seed42_f124"
        ):
            lowered = inputs["prompt"].lower()
            if any(word in lowered for word in FORBIDDEN_JOB0_WORDS):
                raise RuntimeError(f"{name} retained forbidden low-motion language")
            if any(word in lowered for word in ("audio", "sound", "music", "voice")):
                raise RuntimeError(f"{name} mentions audio despite Job0 contract")
    # Generation-graph comparisons ignore only the evidence filename prefix.
    def normalized_graph(recipe: dict[str, Any]) -> dict[str, Any]:
        graph = copy.deepcopy(recipe["prompt"])
        graph["12"]["inputs"]["filename_prefix"] = "<evidence-prefix>"
        return graph

    control_graph = normalized_graph(shared)
    for name, recipe in recipes.items():
        candidate = normalized_graph(recipe)
        differing = []
        for node_id in sorted(control_graph, key=int):
            left = control_graph[node_id]
            right = candidate[node_id]
            if left["class_type"] != right["class_type"]:
                differing.append(f"{node_id}.class_type")
            keys = set(left["inputs"]) | set(right["inputs"])
            differing.extend(
                f"{node_id}.inputs.{key}"
                for key in sorted(keys)
                if left["inputs"].get(key) != right["inputs"].get(key)
            )
        expected = set()
        if recipe["prompt"]["5"]["inputs"]["noise_seed"] != 42:
            expected.add("5.inputs.noise_seed")
        if recipe["prompt"]["7"]["inputs"]["prompt"] != BASE_PROMPT:
            expected.add("7.inputs.prompt")
        if recipe["prompt"]["7"]["inputs"]["length"] != 124:
            expected.add("7.inputs.length")
        if set(differing) != expected or len(expected) > 1:
            raise RuntimeError(
                f"{name} violates one-variable graph contract: {differing}"
            )


def build_matrix() -> dict[str, dict[str, Any]]:
    source = source_recipe()
    evidence_receipts()
    recipes = {
        str(cell["name"]): build_recipe(source, cell) for cell in cell_specs()
    }
    validate_matrix(recipes)
    return recipes


def plan(recipes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for cell in cell_specs():
        name = str(cell["name"])
        encoded = canonical_bytes(recipes[name])
        rows.append(
            {
                "name": name,
                "path": str(RECIPES / f"{name}.json"),
                "sha256": sha256_bytes(encoded),
                "seed": cell["seed"],
                "frames": cell["frames"],
                "logical_roles": cell["roles"],
                "single_variable_claim": cell["variable"],
            }
        )
    return {
        "campaign": "H3_UNCONDITIONED_MUSIC",
        "default_read_only": True,
        "source": SOURCE_EVIDENCE,
        "logical_cells": 14,
        "unique_physical_cells": len(rows),
        "warm_gate_executions": len(rows) * 2,
        "saved_by_exact_control_reuse": {
            "unique_cells": 3,
            "warm_gate_executions": 6,
        },
        "cells": rows,
    }


def write_recipes(recipes: dict[str, dict[str, Any]]) -> None:
    RECIPES.mkdir(parents=True, exist_ok=True)
    for name, recipe in recipes.items():
        path = RECIPES / f"{name}.json"
        encoded = canonical_bytes(recipe)
        if path.exists():
            if path.read_bytes() != encoded:
                raise FileExistsError(f"refusing to replace immutable recipe: {path}")
            continue
        path.write_bytes(encoded)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    recipes = build_matrix()
    if args.write:
        write_recipes(recipes)
    print(json.dumps(plan(recipes), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
