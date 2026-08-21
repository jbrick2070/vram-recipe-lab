"""Map registered OTR engines to shipped ComfyUI reference templates.

The engine roster comes from OTR's real video and image registries.  Files that
look like adapters but are not registered are not engines and never appear.
Matching is fail-closed: generic weights and one-token family resemblance score
zero, ties remain ambiguous, and I2V/T2V sibling evidence is reported explicitly
instead of allowing filename sort order to choose a workflow.

Read-only.  No server, model load, GPU, or network.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import math
import os
import re
import sys
from collections import Counter
from typing import Any, Iterable

from diffomatic import OTR_ROOT, _isolated_otr_nodes


TEMPLATES = (
    r"C:\Users\jeffr\Documents\ComfyUI\.venv\Lib\site-packages"
    r"\comfyui_workflow_templates_json\templates"
)

WEIGHT_RE = re.compile(
    r"[\w.\-]+\.(?:safetensors|gguf|pth|ckpt|pt|bin)", re.IGNORECASE
)

_PROCEDURAL_FAMILIES = {"abstract", "static_motion", "procedural", "visualizer"}
_PROCEDURAL_NAMES = {
    "still_motion": "ffmpeg motion on a still, not a model workflow",
    "still_pan": "ffmpeg motion on a still, not a model workflow",
    "still_flat": "static/ffmpeg still lane, not a model workflow",
    "still_word": "static/ffmpeg word-card lane, not a model workflow",
    "viz_green": "procedural visualiser, not a model workflow",
    "viz_mxc_cpu": "procedural visualiser, not a model workflow",
    "viz_mxc_mandala": "procedural visualiser, not a model workflow",
    "viz_camera": "procedural visualiser, not a model workflow",
}


def weights_in_text(text: str) -> set[str]:
    return {match.group(0).lower() for match in WEIGHT_RE.finditer(text)}


def stem_tokens(filename: str) -> set[str]:
    """Model-identity tokens from one weight basename."""
    base = re.sub(
        r"\.(safetensors|gguf|pth|ckpt|pt|bin)$", "", filename.lower()
    )
    parts = re.split(r"[^a-z0-9.]+", base)
    drop = {
        "safetensors", "gguf", "fp8", "fp16", "bf16", "int8", "e4m3fn",
        "scaled", "comfy", "convrot", "distilled", "model", "transformer",
        "checkpoint", "final", "pruned", "step", "steps", "v1", "v2",
        "vae", "clip", "encoder", "text", "audio", "video", "base", "",
    }
    out = set()
    for part in parts:
        if part in drop or len(part) < 3:
            continue
        if re.fullmatch(r"q\d+(?:[a-z0-9]*)?", part):
            continue
        if part in {"k", "m", "s", "0", "1", "2", "b"}:
            continue
        out.add(part)
    return out


def _source_text_for_engine(engine, kind: str) -> tuple[str, str]:
    try:
        path = inspect.getsourcefile(type(engine)) or ""
    except TypeError:
        # Registry objects outlive the temporary isolated ``nodes`` import used
        # to discover them.  Once that namespace is restored, inspect quite
        # reasonably cannot resolve their module; the registered kind + concrete
        # class module still identify the source deterministically.
        module_name = type(engine).__module__.rsplit(".", 1)[-1]
        path = os.path.join(
            OTR_ROOT, "nodes", f"_otr_{kind}_engines", module_name + ".py"
        )
    if not path or not os.path.isfile(path):
        return path, ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return path, ""

    base = os.path.splitext(os.path.basename(path))[0]
    companion = os.path.join(
        os.path.dirname(path), base.removeprefix("eng_") + "_recipe.py"
    )
    if os.path.isfile(companion):
        try:
            with open(companion, "r", encoding="utf-8", errors="replace") as handle:
                text += "\n" + handle.read()
        except OSError:
            pass
    return path, text


def _infer_engine_role(engine) -> str:
    name = str(getattr(engine, "name", "") or "").lower()
    required = tuple(getattr(engine, "required_inputs", ()) or ())
    family = str(getattr(engine, "family", "") or "").lower()
    if name == "ltx_audio_in":
        return "ia2v"
    if name == "minimax_h3_audio_in":
        return "r2v"
    if name.startswith("humo"):
        return "ia2v"
    if name in {"wan_ti2v", "fastwan_8gb"}:
        return "ti2v"
    if "init_image" in required or family in {
        "image_to_video", "audio_conditioned_video", "audio_driven_face",
    }:
        return "i2v"
    if family == "text_to_video":
        return "t2v"
    return "unknown"


def _no_reference_reason(engine) -> str:
    name = str(getattr(engine, "name", ""))
    family = str(getattr(engine, "family", "") or "").lower()
    module = type(engine).__module__.rsplit(".", 1)[-1].lower()
    if name in _PROCEDURAL_NAMES:
        return _PROCEDURAL_NAMES[name]
    if family in _PROCEDURAL_FAMILIES or module.startswith("eng_viz"):
        return "procedural renderer, not a model workflow"
    if "cloud" in module or module.startswith("eng_google"):
        return "external provider lane, not a local ComfyUI model workflow"
    if name == "mesh_stage" or module == "eng_mesh_stage":
        return "hybrid Hunyuan3D plus Blender stage, not an end-to-end Comfy video workflow"
    return ""


def _registered_engine_records(otr_root: str = OTR_ROOT) -> list[tuple[str, Any]]:
    records = []
    with _isolated_otr_nodes(otr_root):
        for kind in ("video", "image"):
            package = f"nodes._otr_{kind}_engines"
            importlib.import_module(package)
            registry = importlib.import_module(f"{package}.registry")
            for name in registry.all_engine_names():
                engine = registry.get_engine(name)
                if str(getattr(engine, "name", "")) != str(name):
                    # Registry aliases are lookups, not additional engine rows.
                    continue
                records.append((kind, engine))
    return records


def scan_engines(registrations: Iterable[tuple[str, Any]] | None = None) -> dict[str, dict]:
    """Describe only objects present in OTR's actual registries."""
    registrations = list(registrations) if registrations is not None else _registered_engine_records()
    engines = {}
    for kind, engine in registrations:
        name = str(getattr(engine, "name", "") or "")
        if not name:
            continue
        path, text = _source_text_for_engine(engine, kind)
        key = f"{kind}:{name}"
        engines[key] = {
            "engine": name,
            "kind": kind,
            "module": type(engine).__module__.rsplit(".", 1)[-1],
            "path": path,
            "weights": weights_in_text(text),
            "role": _infer_engine_role(engine),
            "no_reference_reason": _no_reference_reason(engine),
        }
    return engines


def infer_template_role(filename: str, text: str = "") -> str:
    token = filename.lower().replace("-", "_")
    # Preserve role detail before testing shorter overlapping tokens.
    if "image_speech_to_video" in token:
        return "speech_i2v"
    if "ia2v" in token:
        return "ia2v"
    if "r2v" in token:
        return "r2v"
    if "flf2v" in token or "first_last" in token:
        return "flf2v"
    if "ti2v" in token:
        return "ti2v"
    if any(mark in token for mark in (
        "i2v", "image_to_video", "first_frame", "image2video",
    )):
        return "i2v"
    if any(mark in token for mark in ("t2v", "text_to_video", "text2video")):
        return "t2v"
    low = text.lower()
    if '"minimaxh3referencetovideo"' in low:
        return "r2v"
    if '"wanhumoimagetovideo"' in low:
        return "ia2v"
    if '"loadaudio"' in low and '"loadimage"' in low:
        return "ia2v"
    has_image = any(mark in low for mark in (
        '"loadimage"', '"ltxvimgtovideo', '"wanimage', '"image_to_video"'
    ))
    has_empty = any(mark in low for mark in (
        '"emptyltxvlatentvideo"', '"emptyhunyuanlatentvideo"'
    ))
    if has_image and not has_empty:
        return "i2v"
    if has_empty and not has_image:
        return "t2v"
    return "unknown"


def scan_templates(root: str = TEMPLATES) -> dict[str, dict]:
    out = {}
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(root, name)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        out[name] = {
            "path": path,
            "weights": weights_in_text(text),
            "role": infer_template_role(name, text),
        }
    return out


def _strong_family_pair(left_name: str, right_name: str) -> tuple[float, set[str]]:
    left = stem_tokens(left_name)
    right = stem_tokens(right_name)
    shared = left & right
    # A lone "ltx", "wan", "flux", etc. is resemblance, not identity.  Strong
    # cross-quant evidence needs at least two tokens and a shared version/size.
    if len(shared) < 2 or not any(any(ch.isdigit() for ch in token) for token in shared):
        return 0.0, shared
    smaller = min(len(left), len(right))
    if not smaller or len(shared) / smaller < 0.5:
        return 0.0, shared
    return 20.0 + 5.0 * len(shared), shared


def score(engine: dict, template: dict, idf: dict[str, float] | None = None) -> tuple[float, str]:
    """Score rare exact weights or strong per-file cross-quant identity only."""
    engine_weights = set(engine.get("weights") or ())
    template_weights = set(template.get("weights") or ())
    if not engine_weights or not template_weights:
        return 0.0, ""
    idf = idf or {}
    exact = engine_weights & template_weights
    if exact:
        strength = sum(idf.get(weight, 1.0) for weight in exact)
        if strength < 2.0:
            return 0.0, ""
        best = max(exact, key=lambda weight: idf.get(weight, 1.0))
        return 100.0 + strength, f"rare exact weight: {best}"

    best_score = 0.0
    best_shared: set[str] = set()
    for left_name in engine_weights:
        for right_name in template_weights:
            value, shared = _strong_family_pair(left_name, right_name)
            if value > best_score:
                best_score, best_shared = value, shared
    if not best_score:
        return 0.0, ""
    return best_score, "strong family: " + ", ".join(sorted(best_shared))


def choose_mapping(engine: dict, ranked: list[dict]) -> dict:
    """Choose only when evidence and modality permit a non-arbitrary choice."""
    base = {
        "engine": engine["engine"],
        "kind": engine["kind"],
        "module": engine["module"],
        "engine_role": engine.get("role", "unknown"),
        "template": None,
        "score": 0.0,
        "why": "",
        "status": "no_match",
        "candidates": ranked[:5],
        "rejected_modality": [],
    }
    reason = engine.get("no_reference_reason")
    if reason:
        base.update(status="no_reference_by_design", why=reason)
        return base
    if not ranked:
        base["why"] = "no rare exact weight or strong model-family evidence"
        return base
    engine_role = engine.get("role", "unknown")
    modality_filtered = False
    if engine_role != "unknown":
        rejected = [row for row in ranked if row.get("role") != engine_role]
        compatible = [row for row in ranked if row.get("role") == engine_role]
        base["rejected_modality"] = rejected[:5]
        if rejected and not compatible:
            base["why"] = (
                f"all weight matches have roles "
                f"{sorted({row.get('role') for row in rejected})}, incompatible "
                f"with explicit {engine_role} engine role"
            )
            return base
        if rejected:
            modality_filtered = True
            ranked = compatible

    top = ranked[0]
    plausible = [row for row in ranked if row["score"] >= top["score"] * 0.8]
    roles = {row["role"] for row in plausible if row["role"] != "unknown"}
    if len(roles) > 1:
        if engine_role != "unknown":
            compatible = [row for row in plausible if row["role"] == engine_role]
            if len(compatible) == 1:
                chosen = compatible[0]
                sibling_names = [row["template"] for row in plausible if row is not chosen]
                base.update(
                    status="role_disambiguated",
                    template=chosen["template"],
                    score=chosen["score"],
                    why=(f"{chosen['why']}; explicit {engine_role} engine role chose "
                         f"this over modality siblings {sibling_names}"),
                )
                return base
        base.update(
            status="ambiguous_role",
            why=("weight evidence spans multiple workflow roles and the engine role "
                 "does not select exactly one"),
        )
        return base

    ties = [row for row in plausible if math.isclose(row["score"], top["score"], rel_tol=0, abs_tol=1e-9)]
    if len(ties) > 1:
        base.update(
            status="ambiguous_template",
            why=f"equal evidence for {[row['template'] for row in ties]}",
        )
        return base

    base.update(
        status="role_disambiguated" if modality_filtered else "matched",
        template=top["template"],
        score=top["score"],
        why=(
            f"{top['why']}; explicit {engine_role} role rejected "
            f"{[row['template'] for row in base['rejected_modality']]}"
            if modality_filtered else top["why"]
        ),
    )
    return base


def build_rows(engines: dict[str, dict], templates: dict[str, dict], min_score: float) -> list[dict]:
    frequency = Counter()
    for template in templates.values():
        frequency.update(template["weights"])
    total = max(1, len(templates))
    idf = {
        weight: (total / (1.0 + count)) ** 0.5 / 4.0
        for weight, count in frequency.items()
    }
    rows = []
    for key in sorted(engines):
        engine = engines[key]
        ranked = []
        if not engine.get("no_reference_reason"):
            for template_name, template in templates.items():
                value, why = score(engine, template, idf)
                if value > 0 and value >= min_score:
                    ranked.append({
                        "template": template_name,
                        "score": value,
                        "why": why,
                        "role": template.get("role", "unknown"),
                    })
            ranked.sort(key=lambda row: (-row["score"], row["template"]))
        rows.append(choose_mapping(engine, ranked))
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_out", default="")
    parser.add_argument("--min-score", type=float, default=1.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.min_score) or args.min_score <= 0:
        parser.error("--min-score must be a finite number greater than zero")

    engines = scan_engines()
    templates = scan_templates()
    if not engines:
        print("INCOMPLETE: OTR registries exposed zero engines", file=sys.stderr)
        return 3
    if not templates:
        print(f"INCOMPLETE: no templates under {TEMPLATES}", file=sys.stderr)
        return 2

    rows = build_rows(engines, templates, args.min_score)
    print(f"registered engines : {len(engines)}")
    print(f"templates          : {len(templates)}\n")
    print("=== MATCHED ===")
    for row in rows:
        if row["template"]:
            marker = "ROLE-DISAMBIGUATED" if row["status"] == "role_disambiguated" else "MATCHED"
            print(
                f"  {row['kind']}:{row['engine']:24s} -> {row['template']:44s} "
                f"[{marker}; {row['score']:.0f}] {row['why'][:100]}"
            )

    unmatched = [row for row in rows if not row["template"]]
    print(f"\n=== UNMATCHED / AMBIGUOUS ({len(unmatched)}) ===")
    for row in unmatched:
        print(
            f"  {row['kind']}:{row['engine']:24s} [{row['status']}] {row['why']}"
        )
        if row["status"].startswith("ambiguous"):
            names = [candidate["template"] for candidate in row["candidates"]]
            print(f"      candidates: {names}")

    print(
        "\nA MISS IS A RESULT. Weak family resemblance, unregistered source files, "
        "and unresolved modality ties never become mappings."
    )
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"status": "ok", "engines": rows}, handle, indent=2)
            handle.write("\n")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
