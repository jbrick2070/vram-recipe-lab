"""Run the grounded, CPU-only OTR video-template conformance sweep.

This is a reporting gate, not a recipe editor and not a render benchmark.  It
uses only registered public engine IDs, explicit modality-correct references,
and two visibly labelled qualified baselines where no exact official template
exists.  Any missing roster row, parser error, anonymous positional widget,
missing topology proof, or structural-sentinel failure makes the aggregate run
nonzero.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import diffomatic
import diffomatic_map


ROOT = Path(__file__).resolve().parent
TEMPLATES = Path(diffomatic_map.TEMPLATES)
ENGINE_ROOT = Path(diffomatic.OTR_ROOT) / "nodes" / "_otr_video_engines"


@dataclass(frozen=True)
class Case:
    engine: str
    template: str
    recipe_sources: tuple[str, ...]
    sentinels: dict[str, int]
    relation: str = "exact"
    qualification: str = ""


CASES = (
    Case("ltx25_video", "video_ltx2_5_i2v.json",
         ("eng_ltx25.py", "ltx25_recipe.py"),
         {"LTXVImgToVideoInplace": 2, "SamplerCustomAdvanced": 2,
          "LTXVLatentUpsampler": 1}),
    Case("ltx_audio_in", "video_ltx2_3_ia2v.json", ("eng_ltx_av.py",),
         {"LTXVImgToVideoInplace": 2, "SamplerCustomAdvanced": 2,
          "LTXVLatentUpsampler": 1, "LTXVAudioVAEEncode": 1,
          "LTXVCropGuides": 1}),
    Case("ltx_video", "video_ltx2_3_t2v.json", ("eng_ltx_video.py",),
         {"EmptyLTXVLatentVideo": 1, "SamplerCustomAdvanced": 1,
          "VAEDecodeTiled": 1}),
    Case("wan_i2v", "video_wan2_2_14B_i2v.json",
         ("eng_wan_i2v.py", "wan_recipe.py", "wan_shared.py"),
         {"WanImageToVideo": 1, "KSampler": 1, "VAEDecode": 1}),
    Case("wan_ti2v", "video_wan2_2_5B_ti2v.json",
         ("eng_wan_ti2v.py", "wan_recipe.py", "wan_shared.py"),
         {"Wan22ImageToVideoLatent": 1, "KSampler": 1,
          "VAEDecodeTiled": 1}),
    Case("humo", "video_humo.json", ("eng_humo.py",),
         {"AudioEncoderEncode": 1, "WanHuMoImageToVideo": 1,
          "KSampler": 1, "VAEDecode": 1}),
    Case("humo_1.7B", "video_humo.json", ("eng_humo.py",),
         {"AudioEncoderEncode": 1, "WanHuMoImageToVideo": 1,
          "KSampler": 1, "VAEDecode": 1}),
    Case("humo_1.7B_169", "video_humo.json", ("eng_humo.py",),
         {"AudioEncoderEncode": 1, "WanHuMoImageToVideo": 1,
          "KSampler": 1, "VAEDecode": 1}),
    Case("humo_14B_169", "video_humo.json", ("eng_humo.py",),
         {"AudioEncoderEncode": 1, "WanHuMoImageToVideo": 1,
          "KSampler": 1, "VAEDecode": 1}),
    Case("minimax_h3_video", "video_minimax_h3_i2v.json",
         ("eng_minimax_h3.py",),
         {"MiniMaxH3ImageToVideo": 1, "SamplerCustomAdvanced": 1,
          "VAEDecode": 1}),
    Case("minimax_h3_audio_in", "video_minimax_h3_r2v.json",
         ("eng_minimax_h3.py",),
         {"MiniMaxH3ReferenceToVideo": 1, "LoadAudio": 1,
          "VAELoader": 2, "SamplerCustomAdvanced": 1, "VAEDecode": 1}),
    Case("ltx_8gb", "ltxv_image_to_video.json", ("eng_ltx_8gb.py",),
         {"LTXVImgToVideo": 1, "SamplerCustom": 1, "VAEDecodeTiled": 1},
         relation="qualified",
         qualification=("official graph is LTX 0.9.5 while OTR ships the 0.9.8 "
                        "distilled family")),
    Case("fastwan_8gb", "video_wan2_2_5B_ti2v.json",
         ("eng_fastwan_8gb.py", "eng_wan_ti2v.py", "wan_recipe.py",
          "wan_shared.py"),
         {"Wan22ImageToVideoLatent": 1, "ManualSigmas": 1,
          "OTR_DMDRestartSamplerSelect": 1, "SamplerCustom": 1,
          "VAEDecodeTiled": 1},
         relation="qualified",
         qualification=("official graph proves the Wan 2.2 5B substrate; no "
                        "installed FastWan/DMD template exists")),
)


NO_REFERENCE = {
    "still_motion", "still_pan", "still_flat", "still_word",
    "viz_green", "viz_mxc_cpu", "viz_mxc_mandala", "viz_camera",
    "mesh_stage", "cloud_kling_avatar", "cloud_seedance_2", "cloud_wan_i2v",
    "cloud_wan_i2v_audio", "cloud_vidu_q2_pro_fast_720p", "word_razzle",
    "google_omni_video", "google_veo_video",
}

_RECIPE_ENV_PREFIXES = ("OTR_", "LAB_")
_RECIPE_ENV_NAMES = {"HF_HOME", "COMFYUI_MODELS_ROOT"}


def _sanitize_environment() -> dict:
    """Remove caller recipe overrides before importing or building engines."""
    cleared = sorted(
        key for key in os.environ
        if key in _RECIPE_ENV_NAMES
        or any(key.startswith(prefix) for prefix in _RECIPE_ENV_PREFIXES)
    )
    for key in cleared:
        os.environ.pop(key, None)
    os.environ.update(
        CUDA_VISIBLE_DEVICES="",
        PYTHONUTF8="1",
        OTR_TEST_MODE="1",
    )
    return {
        "policy": "clear OTR_*, LAB_*, HF_HOME, and COMFYUI_MODELS_ROOT",
        "cleared_present_keys": cleared,
        "effective": {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONUTF8": "1",
            "OTR_TEST_MODE": "1",
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _validate_roster() -> tuple[dict[str, dict], list[str]]:
    scanned = {
        row["engine"]: row
        for row in diffomatic_map.scan_engines().values()
        if row["kind"] == "video"
    }
    declared = {case.engine for case in CASES} | NO_REFERENCE
    errors = []
    if set(scanned) != declared:
        errors.append(
            f"roster mismatch: undeclared={sorted(set(scanned) - declared)}, "
            f"missing={sorted(declared - set(scanned))}"
        )
    exact = sum(case.relation == "exact" for case in CASES)
    qualified = sum(case.relation == "qualified" for case in CASES)
    if (len(scanned), exact, qualified, len(NO_REFERENCE)) != (30, 11, 2, 17):
        errors.append(
            "coverage must remain exactly 30 = 11 exact + 2 qualified + 17 "
            f"no-reference; got {len(scanned)} = {exact} + {qualified} + "
            f"{len(NO_REFERENCE)}"
        )
    for engine in NO_REFERENCE:
        if engine in scanned and not scanned[engine].get("no_reference_reason"):
            errors.append(f"{engine}: missing explicit no-reference-by-design reason")
    return scanned, errors


def _validate_case(case: Case, receipt: dict) -> list[str]:
    errors = []
    if receipt.get("status") != "ok":
        return [f"receipt status is {receipt.get('status')!r}"]
    for side in ("reference", "ours"):
        row = receipt.get(side) or {}
        for key in ("total", "significant", "edges"):
            if not isinstance(row.get(key), int) or row[key] <= 0:
                errors.append(f"{side}.{key} is not positive")
        digest = row.get("topology_digest")
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"{side}.topology_digest is missing or malformed")
    provenance = (receipt.get("ours") or {}).get("provenance") or {}
    if provenance.get("engine_id") != case.engine:
        errors.append(
            f"concrete engine mismatch: {provenance.get('engine_id')!r} != "
            f"{case.engine!r}"
        )
    for key in ("engine_class", "engine_module", "render_canvas",
                "builder_signature", "recipe_sources", "fleet_environment"):
        if not provenance.get(key):
            errors.append(f"ours.provenance.{key} is missing")
    reference_provenance = (receipt.get("reference") or {}).get("provenance") or {}
    for key in ("source_sha256", "source_bytes", "template_package_version"):
        if not reference_provenance.get(key):
            errors.append(f"reference.provenance.{key} is missing")
    for difference in receipt.get("differences", []):
        param = str(difference.get("param", ""))
        if re.fullmatch(r"w\d+", param) or re.search(r"(?:^|\.)w\d+(?:\.|$)", param):
            errors.append(f"anonymous positional parameter survived: {param}")

    graph = diffomatic.load_nodes(f"video:{case.engine}")
    classes = Counter(
        node.class_type for node in graph.graph_nodes if not node.boundary
    )
    for class_type, minimum in case.sentinels.items():
        if classes[class_type] < minimum:
            errors.append(
                f"sentinel {class_type} expected >= {minimum}, got "
                f"{classes[class_type]}"
            )
    return errors


def run(out_dir: Path) -> int:
    # Resolve Comfy's schemas before registry inspection imports OTR's separate
    # top-level ``nodes`` package into this long-lived process.  Do this before
    # hiding CUDA: Comfy's schema import probes its default device even though
    # this sweep never loads a model or executes a node.
    schemas = diffomatic.resolve_node_schemas()
    if "CLIPLoader" not in schemas or "RandomNoise" not in schemas:
        print("fleet status: error -- core Comfy widget schemas did not resolve")
        return 1
    environment_audit = _sanitize_environment()
    scanned, errors = _validate_roster()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in CASES:
        label = f"{case.engine}__{Path(case.template).stem}"
        receipt_path = out_dir / f"{label}.json"
        text_path = out_dir / f"{label}.txt"
        template_path = TEMPLATES / case.template
        recipe_paths = [ENGINE_ROOT / name for name in case.recipe_sources]
        command = [
            "--template", str(template_path),
            "--ours", f"video:{case.engine}",
            "--recipe-py", ",".join(map(str, recipe_paths)),
            "--json", str(receipt_path),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            returncode = diffomatic.main(command)
        text_path.write_text(
            stdout.getvalue() + stderr.getvalue(), encoding="utf-8", newline="\n"
        )
        case_errors = []
        receipt = {}
        if returncode != 0:
            case_errors.append(f"diffomatic exited {returncode}")
        if receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                ours = receipt.get("ours")
                if isinstance(ours, dict):
                    provenance = ours.setdefault("provenance", {})
                    provenance["fleet_environment"] = environment_audit
                receipt["fleet_environment"] = environment_audit
                _write_json(receipt_path, receipt)
            except (OSError, json.JSONDecodeError) as exc:
                case_errors.append(f"cannot parse receipt: {exc}")
        else:
            case_errors.append("diffomatic wrote no receipt")
        if receipt:
            case_errors.extend(_validate_case(case, receipt))
        errors.extend(f"{case.engine}: {error}" for error in case_errors)
        rows.append({
            "engine": case.engine,
            "template": case.template,
            "relation": case.relation,
            "qualification": case.qualification,
            "returncode": returncode,
            "status": "ok" if not case_errors else "error",
            "errors": case_errors,
            "receipt": receipt_path.name,
            "report": text_path.name,
            "reference": receipt.get("reference"),
            "ours": receipt.get("ours"),
            "comparison": receipt.get("comparison"),
        })
        print(f"[{rows[-1]['status'].upper():5s}] {case.engine} -> {case.template}")

    no_reference_rows = []
    for engine in sorted(NO_REFERENCE):
        row = scanned.get(engine, {})
        no_reference_rows.append({
            "engine": engine,
            "status": "no_reference_by_design",
            "reason": row.get("no_reference_reason", ""),
            "module": row.get("module", ""),
        })

    summary = {
        "schema_version": 1,
        "status": "ok" if not errors else "error",
        "coverage": {
            "registered_video_engines": len(scanned),
            "exact_reference": 11,
            "qualified_baseline": 2,
            "no_reference_by_design": 17,
        },
        "comparisons": rows,
        "no_reference": no_reference_rows,
        "fleet_environment": environment_audit,
        "errors": errors,
    }
    _write_json(out_dir / "fleet_summary.json", summary)
    print(
        f"fleet status: {summary['status']} -- 11 exact, 2 qualified, "
        f"17 no-reference; {len(errors)} errors"
    )
    return 0 if not errors else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir", type=Path,
        default=ROOT / "template_sweep" / "2026-08-21-grounded",
    )
    args = parser.parse_args(argv)
    return run(args.out_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
