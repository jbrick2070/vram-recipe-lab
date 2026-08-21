"""Diff a shipped ComfyUI template against the graph an OTR engine runs.

Diffomatic is deliberately a reporter, never a recipe editor.  Its important
contract is fail-closed: an engine that cannot be selected unambiguously, a
builder signature we do not understand, an unresolved logical node name, or an
empty parse is an ERROR.  None of those states may be printed as a clean 0/0
comparison.

Usage::

    python diffomatic.py --template OFFICIAL.json --ours eng_ltx25
                         [--recipe-py eng_ltx25.py,ltx25_recipe.py]
                         [--json receipt.json]

Both UI-format and API-format JSON are accepted.  ``--ours eng_*`` imports the
registered OTR adapter and calls its pure ``_build_graph`` method; it does not
start ComfyUI, load a model, or touch the GPU.
"""
from __future__ import annotations

import argparse
import ast
import functools
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import os
import re
import sys
import textwrap
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterable


OTR_ROOT = r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"

# Node classes whose values or mere presence can change the rendered result.
# Structural nodes remain in the report even when every input is a wire.
SIGNIFICANT = (
    "sampler", "sigma", "schedul", "vaedecode", "addguide", "imgtovideo",
    "cropguides", "dualcfg", "emptyltxv", "conditioning", "createvideo",
    "latentupsampl", "latentupscale", "preprocess", "resize", "guider",
    "concatav", "separateav", "audiovae", "unetloader", "cliploader",
    "vaeloader", "ksampler", "noise", "cfg", "modalityguidance",
    "checkpointloader", "loraloader", "textencoderloader", "emptylatentaudio",
    "modelsampling", "audioencoder", "imagescale", "latentnoisemask",
    "solidmask", "textgenerate", "switch", "mathexpression", "primitive",
    "loadimage", "loadaudio", "savevideo",
)

# Cosmetic or deliberately per-run widgets.  Node presence is still retained.
IGNORE_KEYS = {
    "control_after_generate", "batch_size", "device", "filename_prefix",
    "upload", "image", "text",
}

_ENGINE_ID = re.compile(
    r"^(?:(?P<kind>video|image):)?(?P<identifier>[A-Za-z0-9_.-]+?)(?:\.py)?$"
)
_MISSING = object()


class DiffomaticError(RuntimeError):
    """A comparison state that must never degrade to a clean report."""

    code = "DIFFOMATIC_ERROR"
    exit_code = 3

    def __init__(self, message: str, *, counts: dict | None = None):
        super().__init__(message)
        self.counts = counts or {}


class UnsupportedGraphError(DiffomaticError):
    code = "UNSUPPORTED_GRAPH"
    exit_code = 3


class EmptyGraphError(DiffomaticError):
    code = "EMPTY_GRAPH"
    exit_code = 4


class MissingInputError(DiffomaticError):
    code = "MISSING_INPUT"
    exit_code = 2


class InternalDiffomaticError(DiffomaticError):
    code = "INTERNAL_ERROR"
    exit_code = 5


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    class_type: str
    params: dict
    order: int
    boundary: bool = False


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    source_port: int
    target_id: str
    target_input: str


@dataclass(frozen=True)
class LoadedGraph:
    source: str
    source_kind: str
    nodes: list[tuple[str, dict, int]]
    total_nodes: int
    graph_nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    scope: str = "root"
    provenance: dict = field(default_factory=dict)

    @property
    def significant_nodes(self) -> int:
        return len(self.nodes)

    def counts(self) -> dict:
        return {
            "source": self.source,
            "source_kind": self.source_kind,
            "total": self.total_nodes,
            "significant": self.significant_nodes,
            "edges": len(self.edges),
            "scope": self.scope,
            "topology_digest": _topology_digest(self.graph_nodes, self.edges),
        }


def _is_significant(class_type: str) -> bool:
    low = (class_type or "").lower()
    return any(token in low for token in SIGNIFICANT)


def _is_engine_identifier(source: str) -> bool:
    match = _ENGINE_ID.fullmatch(source or "")
    return bool(
        match
        and (match.group("kind") or match.group("identifier").startswith("eng_"))
    )


def _wire_ref(value: Any, known_ids: set[str]) -> tuple[str, int] | None:
    """Return a graph edge only when its source exists in this graph.

    Comfy API wires and ordinary two-item literal lists share the same JSON
    shape.  Treating every ``[str, int]`` as a wire silently deletes legitimate
    parameter values, so graph membership is the deciding evidence.
    """
    if not (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
        and value[1] >= 0
        and value[0] in known_ids
    ):
        return None
    return value[0], value[1]


def _without_wires(value: Any, known_ids: set[str] | None = None):
    """Remove graph topology from a value while retaining literal containers."""
    if known_ids is not None and _wire_ref(value, known_ids) is not None:
        return _MISSING
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            stripped = _without_wires(item, known_ids)
            if stripped is not _MISSING:
                clean[key] = stripped
        return clean if clean else _MISSING
    if isinstance(value, (list, tuple)):
        clean = []
        for item in value:
            stripped = _without_wires(item, known_ids)
            if stripped is not _MISSING:
                clean.append(stripped)
        return clean if clean else _MISSING
    return value


def _literal_inputs(inputs: dict, known_ids: set[str] | None = None) -> dict:
    out = {}
    for key, value in (inputs or {}).items():
        stripped = _without_wires(value, known_ids)
        if stripped is not _MISSING:
            out[key] = stripped
    return out


def _split_graph_inputs(
    node_id: str, inputs: dict, known_ids: set[str]
) -> tuple[dict, list[GraphEdge]]:
    params = {}
    edges = []
    for key, value in (inputs or {}).items():
        wire = _wire_ref(value, known_ids)
        if wire is not None:
            edges.append(GraphEdge(wire[0], wire[1], node_id, str(key)))
            continue
        stripped = _without_wires(value, known_ids)
        if stripped is not _MISSING:
            params[str(key)] = stripped
    return _flatten_params(params), edges


def _stable_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def _topology_digest(
    nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]
) -> str:
    """ID-independent structural digest that changes on rewiring or port drift."""
    nodes = tuple(nodes)
    edges = tuple(edges)
    if not nodes:
        return ""
    by_id = {node.node_id: node for node in nodes}
    if len(by_id) != len(nodes):
        raise UnsupportedGraphError("duplicate node IDs prevent topology proof")
    for edge in edges:
        if edge.source_id not in by_id or edge.target_id not in by_id:
            raise UnsupportedGraphError(
                f"edge {edge} references a node outside the selected graph scope"
            )

    labels = {
        node.node_id: hashlib.sha256(
            _stable_json([node.class_type, node.params]).encode("utf-8")
        ).hexdigest()
        for node in nodes
    }
    for _ in range(max(1, len(nodes))):
        updated = {}
        for node in nodes:
            incoming = sorted(
                (edge.target_input, edge.source_port, labels[edge.source_id])
                for edge in edges if edge.target_id == node.node_id
            )
            outgoing = sorted(
                (edge.target_input, edge.source_port, labels[edge.target_id])
                for edge in edges if edge.source_id == node.node_id
            )
            payload = [node.class_type, incoming, outgoing]
            updated[node.node_id] = hashlib.sha256(
                _stable_json(payload).encode("utf-8")
            ).hexdigest()
        if updated == labels:
            break
        labels = updated

    canonical = {
        "nodes": sorted(labels.values()),
        "edges": sorted(
            (labels[edge.source_id], edge.source_port,
             labels[edge.target_id], edge.target_input)
            for edge in edges
        ),
    }
    return hashlib.sha256(_stable_json(canonical).encode("utf-8")).hexdigest()


def _make_loaded_graph(
    source: str,
    source_kind: str,
    graph_nodes: Iterable[GraphNode],
    edges: Iterable[GraphEdge],
    *,
    scope: str = "root",
    provenance: dict | None = None,
) -> LoadedGraph:
    graph_nodes = tuple(graph_nodes)
    edges = tuple(edges)
    # Compute now so malformed topology fails during loading, never at receipt
    # formatting after a comparison has already been presented as successful.
    _topology_digest(graph_nodes, edges)
    significant = [
        (node.class_type, node.params, node.order)
        for node in graph_nodes
        if not node.boundary and _is_significant(node.class_type)
    ]
    loaded = LoadedGraph(
        source,
        source_kind,
        significant,
        sum(not node.boundary for node in graph_nodes),
        graph_nodes,
        edges,
        scope,
        provenance or {},
    )
    if not loaded.total_nodes:
        raise EmptyGraphError(f"{source}: parsed zero graph nodes", counts=loaded.counts())
    if not loaded.nodes:
        raise EmptyGraphError(
            f"{source}: parsed {loaded.total_nodes} nodes but zero were analyzable",
            counts=loaded.counts(),
        )
    return loaded


def _legacy_schema_rows(declared: dict) -> list[dict]:
    rows = []
    for section in ("required", "optional"):
        values = declared.get(section, {})
        if not isinstance(values, dict):
            continue
        for input_id, raw in values.items():
            type_spec = raw[0] if isinstance(raw, (tuple, list)) and raw else raw
            options = (
                raw[1]
                if isinstance(raw, (tuple, list))
                and len(raw) > 1
                and isinstance(raw[1], dict)
                else {}
            )
            rows.append({
                "id": str(input_id),
                "kind": "legacy",
                "type": type_spec,
                "spec": dict(options),
            })
    return rows


@functools.lru_cache(maxsize=1)
def resolve_node_schemas() -> dict[str, list[dict]]:
    """Resolve enough schema detail to name positional UI widgets exactly.

    A list of input names is insufficient: DynamicCombo widgets serialize a
    selector plus the selected option's child widgets, and seed widgets append
    a ``control_after_generate`` value.  Returning structured rows lets the
    decoder consume the exact serialized arity.  If a significant UI node has
    widgets but no usable schema, loading fails closed instead of inventing
    ``w0`` names or shifting a value onto a wired input.
    """
    schemas: dict[str, list[dict]] = {}
    comfy_root = r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI"
    if not os.path.exists(comfy_root):
        return schemas

    import glob

    sys.path.insert(0, comfy_root)
    try:
        try:
            comfy_nodes = importlib.import_module("nodes")
            for name, cls in getattr(comfy_nodes, "NODE_CLASS_MAPPINGS", {}).items():
                if not hasattr(cls, "INPUT_TYPES"):
                    continue
                try:
                    declared = cls.INPUT_TYPES()
                    schemas[name] = _legacy_schema_rows(declared)
                except Exception:
                    continue
        except Exception:
            pass

        for folder in ("comfy_extras", "comfy_api_nodes"):
            folder_path = os.path.join(comfy_root, folder)
            if not os.path.isdir(folder_path):
                continue
            for pyfile in glob.glob(os.path.join(folder_path, "*.py")):
                module_name = f"{folder}.{os.path.splitext(os.path.basename(pyfile))[0]}"
                try:
                    module = importlib.import_module(module_name)
                except Exception:
                    continue
                for obj in vars(module).values():
                    if not isinstance(obj, type):
                        continue
                    try:
                        if hasattr(obj, "define_schema"):
                            schema = obj.define_schema()
                            schemas[schema.node_id] = [
                                {
                                    "id": str(item.id),
                                    "kind": "v3",
                                    "spec": dict(item.as_dict()),
                                }
                                for item in schema.inputs
                            ]
                        elif hasattr(obj, "INPUT_TYPES"):
                            declared = obj.INPUT_TYPES()
                            schemas[obj.__name__] = _legacy_schema_rows(declared)
                    except Exception:
                        continue
    finally:
        try:
            sys.path.remove(comfy_root)
        except ValueError:
            pass
    return schemas


def _flatten_params(params: dict) -> dict:
    """Flatten dynamic input dictionaries into comparable dotted parameters."""
    out = {}

    def visit(prefix: str, value):
        if not isinstance(value, dict):
            out[prefix] = value
            return
        if not value:
            return
        leaf = prefix.rsplit(".", 1)[-1]
        for key, child in value.items():
            child_prefix = prefix if str(key) == leaf else f"{prefix}.{key}"
            visit(child_prefix, child)

    for key, value in params.items():
        visit(str(key), value)
    return out


def _normalise_params(inputs: dict) -> dict:
    return _flatten_params(_literal_inputs(inputs))


@contextmanager
def _isolated_otr_nodes(otr_root: str = OTR_ROOT):
    """Temporarily give OTR ownership of the top-level ``nodes`` package."""
    saved = {
        key: value
        for key, value in list(sys.modules.items())
        if key == "nodes" or key.startswith("nodes.")
    }
    for key in saved:
        sys.modules.pop(key, None)
    sys.path.insert(0, otr_root)
    try:
        yield
    finally:
        for key in list(sys.modules):
            if key == "nodes" or key.startswith("nodes."):
                sys.modules.pop(key, None)
        try:
            sys.path.remove(otr_root)
        except ValueError:
            pass
        sys.modules.update(saved)


def _select_concrete_engine(module, registered: Iterable[Any]):
    """Select the one registered adapter implemented by ``module``.

    Bases, helper classes, and merely class-shaped objects are not engines.  A
    module with zero or multiple registered builders is unsupported until the
    caller names a public adapter unambiguously.
    """
    candidates = [
        engine
        for engine in registered
        if type(engine).__module__ == module.__name__
        and callable(getattr(engine, "_build_graph", None))
    ]
    if not candidates:
        raise UnsupportedGraphError(
            f"{module.__name__}: no registered engine exposes _build_graph"
        )
    if len(candidates) != 1:
        # A module may intentionally register a canonical engine plus measured
        # variants (eng_humo -> humo, humo_1.7B, ...).  The public id exactly
        # matching the module stem is an explicit identity, not class-order
        # guessing.  Any module without exactly one such identity still refuses.
        module_id = module.__name__.rsplit(".", 1)[-1].removeprefix("eng_")
        exact = [engine for engine in candidates
                 if str(getattr(engine, "name", "")) == module_id]
        if len(exact) == 1:
            return exact[0]
        names = sorted(str(getattr(engine, "name", type(engine).__name__))
                       for engine in candidates)
        raise UnsupportedGraphError(
            f"{module.__name__}: multiple registered graph builders {names}; "
            "name one concrete engine instead of guessing"
        )
    return candidates[0]


def _declared_canvas(engine) -> tuple[int, int]:
    raw = getattr(type(engine), "render_canvas", None)
    if not (
        isinstance(raw, (tuple, list))
        and len(raw) == 2
        and all(isinstance(value, int) and value > 0 for value in raw)
    ):
        raise UnsupportedGraphError(
            f"{getattr(engine, 'name', type(engine).__name__)}: no positive "
            "two-integer render_canvas declaration; refusing an invented fixture"
        )
    return int(raw[0]), int(raw[1])


def _declared_length(engine) -> int:
    """Choose a legal, ordinary fixture length without inventing a canvas."""
    contract = getattr(engine, "frame_contract", None)
    if callable(contract):
        try:
            contract = contract()
        except TypeError:
            contract = None
    discrete = tuple(getattr(contract, "discrete_frames", ()) or ())
    if discrete:
        values = [int(value) for value in discrete if int(value) > 0]
        if 97 in values:
            return 97
        if values:
            return values[0]
    return 97


def _builder_fixture(engine) -> dict[str, Any]:
    """A declared-canvas request fixture for pure graph construction."""
    width, height = _declared_canvas(engine)
    length = _declared_length(engine)
    plan = {
        "text_prompt": "a vintage radio broadcast scene, subtle natural motion",
        "negative_prompt": "",
        "seed": 42,
        "target_frame_count": length,
        "init_image": "diffomatic.png",
        "audio_path": "diffomatic.wav",
    }
    request = {
        "text_prompt": plan["text_prompt"],
        "negative_prompt": "",
        "audio_ref": {"path": "diffomatic.wav"},
        "asset_refs": {"init_image": "diffomatic.png"},
        "timing": {"target_frame_count": length},
        "seed_bundle": {"request_seed": 42},
        "canvas": {"width": width, "height": height},
        "render_canvas": f"{width}x{height}",
    }
    return {
        "plan": plan,
        "request": request,
        "staged": {"image": "diffomatic.png", "audio": "diffomatic.wav"},
        "image_name": "diffomatic.png",
        "audio_name": "diffomatic.wav",
        "length": length,
        "model_length": length,
        "width": width,
        "height": height,
    }


def _invoke_graph_builder(engine) -> tuple[dict, dict]:
    builder = engine._build_graph
    fixture = _builder_fixture(engine)
    kwargs = {}
    unknown = []
    for name, param in inspect.signature(builder).parameters.items():
        if name == "self" or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if name in fixture:
            kwargs[name] = fixture[name]
        elif param.default is not inspect.Parameter.empty:
            continue
        else:
            unknown.append(name)
    if unknown:
        raise UnsupportedGraphError(
            f"{getattr(engine, 'name', type(engine).__name__)}: _build_graph has "
            f"unknown required arguments {sorted(unknown)}; refusing permissive stubs"
        )
    graph = builder(**kwargs)
    if not isinstance(graph, dict):
        raise UnsupportedGraphError(
            f"{getattr(engine, 'name', type(engine).__name__)}: _build_graph "
            f"returned {type(graph).__name__}, not a dict"
        )
    if not graph:
        raise EmptyGraphError(
            f"{getattr(engine, 'name', type(engine).__name__)}: _build_graph "
            "returned zero nodes",
            counts={"total": 0, "significant": 0},
        )
    return graph, fixture


def _candidate_map(engine) -> dict[str, tuple[str, ...]]:
    methods = [
        (name, getattr(engine, name))
        for name in dir(engine)
        if name.startswith("_node_candidates")
        and callable(getattr(engine, name, None))
    ]
    if not methods:
        raise UnsupportedGraphError(
            f"{getattr(engine, 'name', type(engine).__name__)}: no _node_candidates; "
            "logical node names cannot be resolved authoritatively"
        )
    out = {}
    for method_name, method in methods:
        sig = inspect.signature(method)
        required = [
            name for name, param in sig.parameters.items()
            if name != "self"
            and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
            and param.default is inspect.Parameter.empty
        ]
        if required:
            # A parameterized variant is not safe to invent.  The ordinary
            # no-argument declarations may still fully describe this graph.
            continue
        raw = method()
        if not isinstance(raw, dict):
            raise UnsupportedGraphError(
                f"{getattr(engine, 'name', type(engine).__name__)}: "
                f"{method_name} returned {type(raw).__name__}, not a mapping"
            )
        for logical, names in raw.items():
            if isinstance(names, str):
                names = (names,)
            concrete = tuple(name for name in names if isinstance(name, str) and name)
            if not concrete:
                raise UnsupportedGraphError(
                    f"{getattr(engine, 'name', type(engine).__name__)}: "
                    f"{method_name}[{logical!r}] has no concrete class"
                )
            logical = str(logical)
            previous = out.get(logical)
            if previous is not None and previous != concrete:
                raise UnsupportedGraphError(
                    f"{getattr(engine, 'name', type(engine).__name__)}: "
                    f"candidate declarations disagree for {logical!r}: "
                    f"{previous!r} vs {concrete!r}"
                )
            out[logical] = concrete
    if not out:
        raise UnsupportedGraphError(
            f"{getattr(engine, 'name', type(engine).__name__)}: "
            "no zero-argument _node_candidates declaration returned entries"
        )
    return out


def _internal_class_map(engine) -> dict[str, str]:
    """Read explicit in-adapter additions to the executor's class map.

    OTR's LTX adapters implement fixed sigma injectors as local Python classes,
    not registered ComfyUI nodes.  Their render path names those classes with
    ``classes.setdefault(<logical>, <Class>)``.  That statement is the
    authoritative mapping for this narrow case; an unmapped graph token still
    fails closed.
    """
    method = getattr(engine, "render_clip", None)
    if not callable(method):
        return {}
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    except (OSError, TypeError, SyntaxError):
        return {}
    out = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setdefault"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        target = node.args[1]
        if isinstance(target, ast.Name):
            out[node.args[0].value] = target.id
        elif isinstance(target, ast.Attribute):
            out[node.args[0].value] = target.attr
    return out


def _normalise_dynamic_graph(engine, graph: dict) -> LoadedGraph:
    mapping = _candidate_map(engine)
    internal_mapping = _internal_class_map(engine)
    declared_classes = {name for choices in mapping.values() for name in choices}
    known_ids = {str(node_id) for node_id in graph}
    graph_nodes = []
    edges = []
    for order, (node_id, node) in enumerate(graph.items()):
        node_id = str(node_id)
        if not isinstance(node, dict):
            raise UnsupportedGraphError(
                f"graph node {node_id!r} is {type(node).__name__}, not a dict"
            )
        logical = node.get("class")
        if not isinstance(logical, str) or not logical:
            raise UnsupportedGraphError(
                f"graph node {node_id!r} has no logical class name"
            )
        if logical in mapping:
            class_type = mapping[logical][0]
        elif logical in internal_mapping:
            class_type = internal_mapping[logical]
        elif logical in declared_classes:
            # Some adapters already put a declared concrete name in the graph.
            class_type = logical
        else:
            raise UnsupportedGraphError(
                f"graph node {node_id!r} uses logical class {logical!r}, absent "
                "from the engine's _node_candidates mapping"
            )
        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            raise UnsupportedGraphError(
                f"graph node {node_id!r} inputs are {type(inputs).__name__}, not a dict"
            )
        params, incoming = _split_graph_inputs(node_id, inputs, known_ids)
        graph_nodes.append(GraphNode(node_id, class_type, params, order))
        edges.extend(incoming)

    source = str(getattr(engine, "name", type(engine).__name__))
    width, height = _declared_canvas(engine)
    return _make_loaded_graph(
        source,
        "otr_engine",
        graph_nodes,
        edges,
        scope=source,
        provenance={
            "engine_id": source,
            "engine_class": type(engine).__name__,
            "engine_module": type(engine).__module__,
            "render_canvas": [width, height],
            "builder_signature": str(inspect.signature(engine._build_graph)),
        },
    )


def _build_engine_graph(identifier: str, otr_root: str = OTR_ROOT) -> LoadedGraph:
    match = _ENGINE_ID.fullmatch(identifier or "")
    if not match:
        raise UnsupportedGraphError(f"invalid OTR engine identifier {identifier!r}")
    requested = match.group("identifier")
    requested_kind = match.group("kind")
    kinds = (requested_kind,) if requested_kind else ("video", "image")
    hits = []
    errors = []
    with _isolated_otr_nodes(otr_root):
        for kind in kinds:
            package = f"nodes._otr_{kind}_engines"
            try:
                registry = importlib.import_module(f"{package}.registry")
                names = tuple(registry.all_engine_names())
                registered = [registry.get_engine(name) for name in names]
                if requested.startswith("eng_"):
                    module = importlib.import_module(f"{package}.{requested}")
                    engine = _select_concrete_engine(module, registered)
                else:
                    if requested not in names:
                        raise UnsupportedGraphError(
                            f"{kind} registry has no public engine {requested!r}"
                        )
                    engine = registry.get_engine(requested)
                    if not callable(getattr(engine, "_build_graph", None)):
                        raise UnsupportedGraphError(
                            f"{kind}:{requested} exposes no pure _build_graph"
                        )
                hits.append((kind, engine))
            except ModuleNotFoundError as exc:
                expected = f"{package}.{requested}"
                if exc.name != expected:
                    errors.append(f"{kind}: import failed: {exc}")
                else:
                    errors.append(f"{kind}: no module {requested}")
            except DiffomaticError as exc:
                errors.append(f"{kind}: {exc}")
        if len(hits) != 1:
            detail = "; ".join(errors) or "no registered module"
            if len(hits) > 1:
                detail = "identifier exists in both video and image registries"
            raise UnsupportedGraphError(f"{identifier}: {detail}")
        _kind, engine = hits[0]
        graph, _fixture = _invoke_graph_builder(engine)
        return _normalise_dynamic_graph(engine, graph)


_LEGACY_WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


def _enum_value(value):
    return getattr(value, "value", value)


def _dynamic_options(row: dict) -> list[dict]:
    spec = row.get("spec") or {}
    options = spec.get("options")
    if not isinstance(options, list):
        return []
    return [option for option in options
            if isinstance(option, dict) and "key" in option and "inputs" in option]


def _row_is_widget(row: dict) -> bool:
    spec = row.get("spec") or {}
    if row.get("kind") == "v3":
        return bool(_dynamic_options(row)) or "default" in spec or bool(
            spec.get("control_after_generate")
        ) or (
            isinstance(spec.get("options"), list)
            and not _dynamic_options(row)
        )
    if spec.get("forceInput") or spec.get("force_input"):
        return False
    type_spec = _enum_value(row.get("type"))
    if isinstance(type_spec, (list, tuple)):
        return True
    normalized = str(type_spec).upper().rsplit(".", 1)[-1]
    return normalized in _LEGACY_WIDGET_TYPES or "default" in spec


def _consume_schema_row(
    row: dict, raw: list, cursor: int, out: dict, *, prefix: str = ""
) -> int:
    if not _row_is_widget(row):
        return cursor
    key = f"{prefix}{row['id']}"
    options = _dynamic_options(row)
    if cursor >= len(raw):
        spec = row.get("spec") or {}
        if options or "default" not in spec:
            raise UnsupportedGraphError(
                f"widget array ended before schema input {key!r}"
            )
        # Older official templates legitimately predate newly appended widgets.
        # A trailing, explicit current-schema default is deterministic; a gap
        # or dynamic selector is not and remains unsupported.
        out[key] = _enum_value(spec["default"])
        return cursor
    out[key] = _enum_value(raw[cursor])
    selected = out[key]
    cursor += 1

    if options:
        matching = [
            option for option in options
            if str(_enum_value(option.get("key"))) == str(selected)
        ]
        if len(matching) != 1:
            choices = [str(_enum_value(option.get("key"))) for option in options]
            raise UnsupportedGraphError(
                f"dynamic widget {key!r} selected {selected!r}, not one of {choices}"
            )
        children = _legacy_schema_rows(matching[0].get("inputs") or {})
        for child in children:
            cursor = _consume_schema_row(
                child, raw, cursor, out, prefix=f"{key}."
            )

    spec = row.get("spec") or {}
    if spec.get("control_after_generate"):
        if cursor >= len(raw):
            return cursor
        out[f"{key}.control_after_generate"] = _enum_value(raw[cursor])
        cursor += 1
    return cursor


def _ui_params(node_type: str, node: dict, schemas: dict[str, list[dict]]) -> dict:
    named = node.get("widgets_values_named")
    if isinstance(named, dict) and named:
        return _normalise_params(named)
    raw = node.get("widgets_values")
    if isinstance(raw, dict):
        return _normalise_params(raw)
    if not isinstance(raw, list):
        return {}
    if not raw:
        return {}
    schema_inputs = schemas.get(node_type)
    if not schema_inputs:
        raise UnsupportedGraphError(
            f"{node_type}: {len(raw)} positional widgets but no resolvable schema"
        )
    if node_type.startswith("Primitive"):
        if len(schema_inputs) != 1 or len(raw) not in (1, 2):
            raise UnsupportedGraphError(
                f"{node_type}: primitive widget/schema count mismatch"
            )
        key = schema_inputs[0]["id"]
        out = {key: raw[0]}
        if len(raw) == 2:
            out[f"{key}.control_after_generate"] = raw[1]
        return _normalise_params(out)
    if node_type == "ComfySwitchNode":
        if len(raw) != 1:
            raise UnsupportedGraphError(
                f"{node_type}: switch widget/schema count mismatch"
            )
        return {"switch": raw[0]}
    out = {}
    cursor = 0
    for row in schema_inputs:
        cursor = _consume_schema_row(row, raw, cursor, out)
    # Legacy LoadImage-style schemas expose the upload button as metadata on
    # the image widget rather than as a second input.  Comfy's saved UI graph
    # still appends the literal control marker ``"image"``.  Accept only that
    # exact, schema-declared companion so malformed extra widgets keep failing
    # closed instead of becoming anonymous parameters.
    upload_rows = [
        row for row in schema_inputs
        if (row.get("spec") or {}).get("image_upload")
    ]
    if (
        cursor + 1 == len(raw)
        and len(upload_rows) == 1
        and raw[cursor] == "image"
    ):
        out["upload"] = raw[cursor]
        cursor += 1
    audio_upload_rows = [
        row for row in schema_inputs
        if (row.get("spec") or {}).get("audio_upload")
    ]
    if (
        cursor + 2 == len(raw)
        and len(audio_upload_rows) == 1
        and raw[cursor] is None
        and (raw[cursor + 1] is None or isinstance(raw[cursor + 1], str))
    ):
        # Current official workflows serialize two non-input audio-preview
        # slots after an ``audio_upload`` combo.  Preserve the exact observed
        # shape as ignored UI state; any other arity or value type is an error.
        out["upload"] = raw[cursor:cursor + 2]
        cursor += 2
    if cursor != len(raw):
        raise UnsupportedGraphError(
            f"{node_type}: widget/schema count mismatch; consumed {cursor} of "
            f"{len(raw)} values (refusing anonymous w{cursor} parameters)"
        )
    return _normalise_params(out)


def _node_order(node: dict, fallback: int) -> int:
    value = node.get("order", fallback)
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _api_node_mapping(data: dict) -> tuple[dict, str] | None:
    has_ui = isinstance(data.get("nodes"), list)
    prompt = data.get("prompt")
    has_prompt = isinstance(prompt, dict) and any(
        isinstance(node, dict) and "class_type" in node for node in prompt.values()
    )
    if has_ui and has_prompt:
        raise UnsupportedGraphError(
            "JSON contains UI nodes and an API prompt at the same scope"
        )
    if has_prompt:
        return prompt, "api_prompt"
    if has_ui:
        return None
    if data and all(
        isinstance(node, dict)
        and isinstance(node.get("class_type"), str)
        and isinstance(node.get("inputs"), dict)
        for node in data.values()
    ):
        return data, "api_flat"
    return None


def _normalise_api_graph(
    path: str, mapping: dict, source_kind: str, source_sha256: str
) -> LoadedGraph:
    known_ids = {str(node_id) for node_id in mapping}
    graph_nodes = []
    edges = []
    for fallback, (raw_id, node) in enumerate(mapping.items()):
        node_id = str(raw_id)
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(class_type, str) or not class_type:
            raise UnsupportedGraphError(f"API node {node_id!r} has no class_type")
        if not isinstance(inputs, dict):
            raise UnsupportedGraphError(f"API node {node_id!r} has non-dict inputs")
        params, incoming = _split_graph_inputs(node_id, inputs, known_ids)
        graph_nodes.append(
            GraphNode(node_id, class_type, params, _node_order(node, fallback))
        )
        edges.extend(incoming)
    return _make_loaded_graph(
        path,
        source_kind,
        graph_nodes,
        edges,
        provenance={"source_sha256": source_sha256},
    )


def _select_ui_scope(data: dict) -> tuple[dict, str]:
    definitions = data.get("definitions") or {}
    subgraphs = definitions.get("subgraphs") if isinstance(definitions, dict) else None
    candidates = [
        graph for graph in (subgraphs or [])
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list)
        and graph.get("nodes")
    ]
    if not candidates:
        return data, "root"

    active_root_types = {
        str(node.get("type"))
        for node in data.get("nodes", [])
        if isinstance(node, dict) and node.get("mode", 0) == 0
    }
    invoked = [graph for graph in candidates if str(graph.get("id")) in active_root_types]
    selected = invoked if invoked else candidates
    if len(selected) != 1:
        names = [str(graph.get("name") or graph.get("id")) for graph in selected]
        raise UnsupportedGraphError(
            f"UI workflow has {len(selected)} possible executable subgraphs {names}; "
            "an explicit graph scope is required"
        )
    graph = selected[0]
    return graph, f"subgraph:{graph.get('name') or graph.get('id')}"


def _ui_link_fields(raw) -> tuple[str, str, int, str, int]:
    if isinstance(raw, dict):
        values = (
            raw.get("id"), raw.get("origin_id"), raw.get("origin_slot"),
            raw.get("target_id"), raw.get("target_slot"),
        )
    elif isinstance(raw, list) and len(raw) >= 5:
        values = tuple(raw[:5])
    else:
        raise UnsupportedGraphError(f"unsupported UI link record {raw!r}")
    link_id, source_id, source_port, target_id, target_slot = values
    if (
        isinstance(source_port, bool) or not isinstance(source_port, int)
        or source_port < 0 or isinstance(target_slot, bool)
        or not isinstance(target_slot, int) or target_slot < 0
    ):
        raise UnsupportedGraphError(f"UI link {link_id!r} has invalid port indices")
    return str(link_id), str(source_id), source_port, str(target_id), target_slot


def _link_declares(link_value, link_id: str) -> bool:
    if isinstance(link_value, list):
        return any(str(value) == link_id for value in link_value)
    return link_value is not None and str(link_value) == link_id


def _drop_actively_linked_ui_params(
    node_id: str,
    node: dict,
    params: dict,
    active_targets: set[tuple[str, int]],
) -> dict:
    """Discard serialized widget fallbacks whose sockets have live edges."""
    linked_names = set()
    for slot, input_row in enumerate(node.get("inputs") or []):
        if (node_id, slot) not in active_targets or not isinstance(input_row, dict):
            continue
        name = input_row.get("name")
        widget = input_row.get("widget")
        widget_name = widget.get("name") if isinstance(widget, dict) else None
        linked_names.update(
            str(value) for value in (name, widget_name) if value
        )
    if not linked_names:
        return params
    return {
        key: value for key, value in params.items()
        if not any(key == name or key.startswith(f"{name}.")
                   for name in linked_names)
    }


def _normalise_ui_graph(
    path: str,
    data: dict,
    schemas: dict[str, list[dict]],
    source_sha256: str,
) -> LoadedGraph:
    graph, scope = _select_ui_scope(data)
    raw_nodes = graph.get("nodes")
    raw_links = graph.get("links", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_links, list):
        raise UnsupportedGraphError("UI graph requires list-valued nodes and links")

    active = {}
    inactive_ids = set()
    for fallback, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            raise UnsupportedGraphError("UI node entry is not a dict")
        node_id = str(node.get("id"))
        if node_id == "None" or node_id in active or node_id in inactive_ids:
            raise UnsupportedGraphError(f"UI graph has missing/duplicate node ID {node_id!r}")
        mode = node.get("mode", 0)
        if mode != 0:
            inactive_ids.add(node_id)
            continue
        active[node_id] = (node, fallback)

    normalized_links = [_ui_link_fields(raw_link) for raw_link in raw_links]
    for inactive_id in inactive_ids:
        has_active_input = any(
            target_id == inactive_id and (source_id in active or source_id == "-10")
            for _link_id, source_id, _source_port, target_id, _target_slot
            in normalized_links
        )
        has_active_output = any(
            source_id == inactive_id and (target_id in active or target_id == "-20")
            for _link_id, source_id, _source_port, target_id, _target_slot
            in normalized_links
        )
        if has_active_input and has_active_output:
            raise UnsupportedGraphError(
                f"inactive/bypassed UI node {inactive_id} lies between active nodes; "
                "its runtime rewiring cannot be proven from workflow JSON"
            )

    active_targets = {
        (target_id, target_slot)
        for _link_id, source_id, _source_port, target_id, target_slot
        in normalized_links
        if source_id not in inactive_ids and target_id not in inactive_ids
        and source_id in active and target_id in active
    }

    graph_nodes = []
    for node_id, (node, fallback) in active.items():
        class_type = node.get("type")
        if not isinstance(class_type, str) or not class_type:
            raise UnsupportedGraphError(f"UI node {node_id!r} has no type")
        params = _ui_params(class_type, node, schemas) if _is_significant(class_type) else {}
        params = _drop_actively_linked_ui_params(
            node_id, node, params, active_targets
        )
        graph_nodes.append(
            GraphNode(node_id, class_type, params, _node_order(node, fallback))
        )

    boundary_ids = {}
    edges = []
    seen_links = {}
    inactive_links = set()
    for link_id, source_id, source_port, target_id, target_slot in normalized_links:
        if link_id in seen_links:
            raise UnsupportedGraphError(f"duplicate UI link ID {link_id}")
        seen_links[link_id] = (source_id, source_port, target_id, target_slot)

        if source_id in inactive_ids or target_id in inactive_ids:
            inactive_links.add(link_id)
            continue

        if source_id == "-10":
            boundary_ids[source_id] = "$INPUT"
        elif source_id not in active:
            raise UnsupportedGraphError(
                f"UI link {link_id} has unknown source node {source_id}"
            )
        if target_id == "-20":
            boundary_ids[target_id] = "$OUTPUT"
        elif target_id not in active:
            raise UnsupportedGraphError(
                f"UI link {link_id} has unknown target node {target_id}"
            )

        if target_id in active:
            target_node = active[target_id][0]
            inputs = target_node.get("inputs") or []
            if not isinstance(inputs, list) or target_slot >= len(inputs):
                raise UnsupportedGraphError(
                    f"UI link {link_id} target slot {target_slot} is out of range"
                )
            target_input = inputs[target_slot]
            if not isinstance(target_input, dict):
                raise UnsupportedGraphError(
                    f"UI link {link_id} target input metadata is not a dict"
                )
            if not _link_declares(target_input.get("link"), link_id):
                raise UnsupportedGraphError(
                    f"UI link {link_id} contradicts target node {target_id} input metadata"
                )
            target_name = str(target_input.get("name") or f"input_slot_{target_slot}")
        else:
            outputs = graph.get("outputs") or []
            target_name = (
                str(outputs[target_slot].get("name"))
                if target_slot < len(outputs) and isinstance(outputs[target_slot], dict)
                else f"output_{target_slot}"
            )

        if source_id in active:
            source_node = active[source_id][0]
            outputs = source_node.get("outputs") or []
            if not isinstance(outputs, list) or source_port >= len(outputs):
                raise UnsupportedGraphError(
                    f"UI link {link_id} source slot {source_port} is out of range"
                )
            declared_links = outputs[source_port].get("links")
            if declared_links is not None and not _link_declares(declared_links, link_id):
                raise UnsupportedGraphError(
                    f"UI link {link_id} contradicts source node {source_id} output metadata"
                )
        edges.append(GraphEdge(source_id, source_port, target_id, target_name))

    for node_id, (node, _fallback) in active.items():
        for slot, input_row in enumerate(node.get("inputs") or []):
            if not isinstance(input_row, dict) or input_row.get("link") is None:
                continue
            declared = input_row.get("link")
            declared_ids = declared if isinstance(declared, list) else [declared]
            for raw_id in declared_ids:
                link_id = str(raw_id)
                if link_id in inactive_links:
                    continue
                actual = seen_links.get(link_id)
                if actual is None or actual[2:] != (node_id, slot):
                    raise UnsupportedGraphError(
                        f"UI node {node_id} input {slot} points to missing/mismatched "
                        f"link {link_id}"
                    )

    for boundary_id, class_type in boundary_ids.items():
        graph_nodes.append(
            GraphNode(boundary_id, class_type, {}, -1, boundary=True)
        )
    return _make_loaded_graph(
        path,
        "ui_subgraph" if scope.startswith("subgraph:") else "ui_root",
        graph_nodes,
        edges,
        scope=scope,
        provenance={"source_sha256": source_sha256},
    )


def _load_json_graph(path: str) -> LoadedGraph:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        raise MissingInputError(f"no such file {path}")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MissingInputError(f"cannot read graph {path}: {exc}")
    if not isinstance(data, dict):
        raise UnsupportedGraphError(
            f"{path}: top-level JSON is {type(data).__name__}, not an object"
        )
    source_sha256 = hashlib.sha256(raw).hexdigest()
    provenance = {
        "source_sha256": source_sha256,
        "source_bytes": len(raw),
    }
    normalized_path = os.path.normcase(os.path.abspath(path))
    if "comfyui_workflow_templates_json" in normalized_path:
        try:
            provenance["template_package"] = "comfyui-workflow-templates-json"
            provenance["template_package_version"] = importlib.metadata.version(
                "comfyui-workflow-templates-json"
            )
        except importlib.metadata.PackageNotFoundError:
            provenance["template_package_version"] = "unknown"
    api = _api_node_mapping(data)
    if api is not None:
        mapping, source_kind = api
        loaded = _normalise_api_graph(path, mapping, source_kind, source_sha256)
        loaded.provenance.update(provenance)
        return loaded
    if isinstance(data.get("nodes"), list):
        loaded = _normalise_ui_graph(
            path, data, resolve_node_schemas(), source_sha256
        )
        loaded.provenance.update(provenance)
        return loaded
    raise UnsupportedGraphError(
        f"{path}: JSON is neither a flat/API prompt nor a supported UI workflow"
    )


def load_nodes(source: str) -> LoadedGraph:
    """Load one graph and retain explicit total/significant node counts."""
    if _is_engine_identifier(source):
        return _build_engine_graph(source)
    return _load_json_graph(source)


def _comment_block(lines: list[str], index: int) -> str:
    comments = []
    code = lines[index]
    if "#" in code:
        comments.append(code.split("#", 1)[1].strip())
    cursor = index - 1
    while cursor >= 0 and lines[cursor].lstrip().startswith("#"):
        comments.append(lines[cursor].lstrip()[1:].lstrip(": "))
        cursor -= 1
    comments.reverse()
    return " ".join(part for part in comments if part).strip()


def _parameter_sites(tree: ast.AST, key: str) -> list[tuple[int, set[str], ast.AST]]:
    """Lines that actually assign ``key`` and identifiers they reference."""
    sites = []
    for node in ast.walk(tree):
        value_node = None
        if isinstance(node, ast.Dict):
            for key_node, candidate in zip(node.keys, node.values):
                if isinstance(key_node, ast.Constant) and key_node.value == key:
                    value_node = candidate
                    line = getattr(key_node, "lineno", getattr(node, "lineno", 1))
                    refs = {
                        child.id for child in ast.walk(candidate)
                        if isinstance(child, ast.Name)
                    }
                    refs |= {
                        child.attr for child in ast.walk(candidate)
                        if isinstance(child, ast.Attribute)
                    }
                    sites.append((line, refs, candidate))
        elif isinstance(node, ast.keyword) and node.arg == key:
            value_node = node.value
            refs = {child.id for child in ast.walk(value_node) if isinstance(child, ast.Name)}
            refs |= {child.attr for child in ast.walk(value_node)
                     if isinstance(child, ast.Attribute)}
            sites.append((getattr(node, "lineno", 1), refs, value_node))
    return sites


def _static_eval(node: ast.AST, values: dict[str, Any]):
    if isinstance(node, ast.Name) and node.id in values:
        return values[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _static_eval(node.operand, values)
        return -value if isinstance(node.op, ast.USub) else +value
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return _MISSING


def _assignments(tree: ast.AST) -> dict[str, tuple[int, ast.AST]]:
    out = {}
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                out[target.id] = (getattr(target, "lineno", 1), node.value)
    return out


def find_documentation_for_param(key: str, value, source_files: list[str]) -> str:
    """Return a comment attached to the actual parameter or referenced constant.

    The reported line is the parameter/constant line itself.  Broad substring
    searches and comments up to fifteen lines away were intentionally removed:
    they marked unrelated prose as a recipe decision.
    """
    parsed = []
    for path in source_files:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            tree = ast.parse("\n".join(lines), filename=path)
        except (OSError, SyntaxError, UnicodeError):
            continue
        parsed.append((os.path.abspath(path), lines, tree))

    candidates = []
    for path, lines, tree in parsed:
        assignments = _assignments(tree)
        values = {}
        # A few passes resolve simple constant-to-constant aliases without ever
        # executing recipe code.
        for _ in range(max(1, len(assignments))):
            changed = False
            for name, (_lineno, value_node) in assignments.items():
                resolved = _static_eval(value_node, values)
                if resolved is not _MISSING and values.get(name, _MISSING) != resolved:
                    values[name] = resolved
                    changed = True
            if not changed:
                break
        for lineno, refs, value_node in _parameter_sites(tree, key):
            candidates.append({
                "path": path,
                "lines": lines,
                "lineno": lineno,
                "refs": refs,
                "resolved": _static_eval(value_node, values),
                "assignments": assignments,
                "values": values,
            })

    matching = [row for row in candidates if row["resolved"] == value]
    if len(matching) == 1:
        chosen = matching[0]
    elif len(candidates) == 1 and candidates[0]["resolved"] is _MISSING:
        chosen = candidates[0]
    else:
        # Duplicate parameter names are common across multi-stage recipes.  A
        # comment cannot be attributed safely when value evidence does not
        # identify exactly one site.
        return ""

    comment = _comment_block(chosen["lines"], chosen["lineno"] - 1)
    if comment:
        return f"[{chosen['path']}:{chosen['lineno']}] {comment}"

    for name in sorted(chosen["refs"]):
        assignment = chosen["assignments"].get(name)
        if assignment is None or chosen["values"].get(name, _MISSING) != value:
            continue
        lineno, _value_node = assignment
        comment = _comment_block(chosen["lines"], lineno - 1)
        if comment:
            return f"[{chosen['path']}:{lineno}] {comment}"
    return ""


def extract_documentation(differs: list, recipe_pys: list[str]) -> None:
    for row in differs:
        _class_type, key, _reference, ours, _doc = row
        raw_value = ours[0] if ours else None
        try:
            value = json.loads(raw_value) if raw_value is not None else None
        except (TypeError, json.JSONDecodeError):
            value = raw_value
        row[4] = find_documentation_for_param(key, value, recipe_pys)


def summarise(nodes: Iterable[tuple[str, dict, int]]) -> dict[str, list]:
    """Group by class while retaining every empty structural instance."""
    grouped = defaultdict(list)
    for class_type, params, order in sorted(nodes, key=lambda node: node[2]):
        clean = {
            key: value for key, value in params.items()
            if key not in IGNORE_KEYS and key.rsplit(".", 1)[-1] not in IGNORE_KEYS
        }
        grouped[class_type].append((order, clean))
    return grouped


def _compare(ref: dict, ours: dict) -> dict:
    same, differs, only_ref, only_ours = [], [], [], []
    for class_type in sorted(set(ref) | set(ours)):
        left = ref.get(class_type, [])
        right = ours.get(class_type, [])
        if not right:
            only_ref.append((class_type, left))
            continue
        if not left:
            only_ours.append((class_type, right))
            continue
        if len(left) != len(right):
            if len(left) > len(right):
                only_ref.append((f"{class_type} [x{len(left)} vs our x{len(right)}]", left))
            else:
                only_ours.append((f"{class_type} [our x{len(right)} vs ref x{len(left)}]", right))
        keys = set()
        for _order, entry in left + right:
            keys.update(entry)
        for key in sorted(keys):
            left_values = [json.dumps(entry[key], default=str)
                           for _order, entry in left if key in entry]
            right_values = [json.dumps(entry[key], default=str)
                            for _order, entry in right if key in entry]
            if left_values == right_values:
                same.append((class_type, key, left_values))
            else:
                differs.append([class_type, key, left_values, right_values, ""])
    return {
        "same": same,
        "differs": differs,
        "only_ref": only_ref,
        "only_ours": only_ours,
    }


def _edge_descriptions(graph: LoadedGraph) -> Counter:
    ordered = sorted(
        graph.graph_nodes,
        key=lambda node: (node.order, node.class_type, node.node_id),
    )
    seen = Counter()
    labels = {}
    for node in ordered:
        seen[node.class_type] += 1
        labels[node.node_id] = f"{node.class_type}#{seen[node.class_type]}"
    return Counter(
        f"{labels[edge.source_id]}:{edge.source_port} -> "
        f"{labels[edge.target_id]}.{edge.target_input}"
        for edge in graph.edges
    )


def _graph_receipt(graph: LoadedGraph) -> dict:
    payload = graph.counts()
    payload["provenance"] = graph.provenance
    return payload


def _only_side_receipt(rows: Iterable[tuple[str, list]]) -> list[dict]:
    """Retain complete evidence for node classes found on only one side."""
    return [
        {
            "node": class_type,
            "instance_count": len(entries),
            "instances": [
                {"order": order, "params": params}
                for order, params in entries
            ],
        }
        for class_type, entries in rows
    ]


def _source_manifest(paths: Iterable[str]) -> list[dict]:
    rows = []
    for path in paths:
        absolute = os.path.abspath(path)
        try:
            with open(absolute, "rb") as handle:
                raw = handle.read()
        except OSError:
            rows.append({"path": absolute, "status": "missing"})
            continue
        rows.append({
            "path": absolute,
            "status": "present",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return rows


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _error_payload(exc: DiffomaticError, counts: dict) -> dict:
    merged = dict(counts)
    if exc.counts:
        merged.setdefault("failed_source", exc.counts)
    return {
        "status": "error",
        "error": {"code": exc.code, "message": str(exc)},
        "node_counts": merged,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, help="Official reference graph")
    parser.add_argument("--ours", required=True, help="Our JSON graph or registered eng_* module")
    parser.add_argument("--recipe-py", default="",
                        help="Comma-separated sources carrying our constants")
    parser.add_argument("--json", dest="json_out", default="")
    args = parser.parse_args(argv)

    recipe_pys = [item.strip() for item in args.recipe_py.split(",") if item.strip()]
    counts: dict[str, dict] = {}
    loading_side = "reference"
    try:
        reference = load_nodes(args.template)
        counts["reference"] = reference.counts()
        loading_side = "ours"
        ours = load_nodes(args.ours)
        if recipe_pys:
            recipe_manifest = _source_manifest(recipe_pys)
            missing = [row["path"] for row in recipe_manifest
                       if row["status"] != "present"]
            if missing:
                raise MissingInputError(
                    f"recipe source manifest contains missing files: {missing}"
                )
            ours.provenance["recipe_sources"] = recipe_manifest
        counts["ours"] = ours.counts()

        ref_summary = summarise(reference.nodes)
        our_summary = summarise(ours.nodes)
        if not ref_summary or not our_summary:
            raise EmptyGraphError(
                "one side has no significant node instances; refusing clean 0/0",
                counts=counts,
            )
        result = _compare(ref_summary, our_summary)
        extract_documentation(result["differs"], recipe_pys)
    except DiffomaticError as exc:
        if loading_side not in counts:
            failed_source = args.template if loading_side == "reference" else args.ours
            failure_counts = {
                "source": failed_source,
                "source_kind": "unsupported",
                "total": 0,
                "significant": 0,
            }
            failure_counts.update(exc.counts)
            counts[loading_side] = failure_counts
        payload = _error_payload(exc, counts)
        print(f"ERROR [{exc.code}]: {exc}", file=sys.stderr)
        print(f"node counts: {json.dumps(payload['node_counts'], default=str)}",
              file=sys.stderr)
        if args.json_out:
            _write_json(args.json_out, payload)
            print(f"wrote error receipt {args.json_out}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # defensive receipt: never leak a bare traceback
        wrapped = InternalDiffomaticError(
            f"{loading_side} loader raised {type(exc).__name__}: {exc}"
        )
        if loading_side not in counts:
            failed_source = args.template if loading_side == "reference" else args.ours
            counts[loading_side] = {
                "source": failed_source,
                "source_kind": "internal_error",
                "total": 0,
                "significant": 0,
                "edges": 0,
                "scope": "unknown",
                "topology_digest": "",
            }
        payload = _error_payload(wrapped, counts)
        print(f"ERROR [{wrapped.code}]: {wrapped}", file=sys.stderr)
        if args.json_out:
            _write_json(args.json_out, payload)
            print(f"wrote error receipt {args.json_out}", file=sys.stderr)
        return wrapped.exit_code

    same = result["same"]
    differs = result["differs"]
    only_ref = result["only_ref"]
    only_ours = result["only_ours"]
    ref_edges = _edge_descriptions(reference)
    our_edges = _edge_descriptions(ours)
    ref_only_edges = list((ref_edges - our_edges).elements())
    our_only_edges = list((our_edges - ref_edges).elements())
    topology_equal = (
        reference.counts()["topology_digest"]
        == ours.counts()["topology_digest"]
    )
    print(f"reference : {os.path.basename(args.template)}")
    print(f"ours      : {args.ours}")
    print(
        f"nodes     : reference {reference.significant_nodes}/"
        f"{reference.total_nodes}, ours {ours.significant_nodes}/{ours.total_nodes} "
        "(significant/total)"
    )
    print(
        f"edges     : reference {len(reference.edges)}, ours {len(ours.edges)}; "
        f"topology {'identical' if topology_equal else 'differs'}"
    )
    print(
        f"digests   : {reference.counts()['topology_digest'][:16]} / "
        f"{ours.counts()['topology_digest'][:16]}"
    )
    print(
        f"\n{len(same)} parameters identical, {len(differs)} differ, "
        f"{len(only_ref)} node classes/counts only in the reference, "
        f"{len(only_ours)} only in ours\n"
    )

    if only_ref:
        print("=== NODE CLASSES/INSTANCES THE REFERENCE HAS AND WE DO NOT ===")
        for class_type, entries in only_ref:
            for order, entry in entries:
                rendered = json.dumps(
                    entry, ensure_ascii=False, sort_keys=True, default=str
                )
                print(f"  {class_type:36s} [order={order}] {rendered}")
        print()
    if only_ours:
        print("=== NODE CLASSES/INSTANCES WE HAVE AND THE REFERENCE DOES NOT ===")
        for class_type, entries in only_ours:
            for order, entry in entries:
                rendered = json.dumps(
                    entry, ensure_ascii=False, sort_keys=True, default=str
                )
                print(f"  {class_type:36s} [order={order}] {rendered}")
        print()

    differs.sort(key=lambda row: (bool(row[4]), row[0], row[1]))
    print("=== PARAMETER DIFFERENCES -- UNDOCUMENTED FIRST ===")
    for class_type, key, left, right, doc in differs:
        flag = "DOCUMENTED" if doc else "undocumented"
        print(f"  [{flag:12s}] {class_type}.{key}")
        print(f"      reference : {', '.join(value.strip(chr(34)) for value in left) or '<absent>'}")
        print(f"      ours      : {', '.join(value.strip(chr(34)) for value in right) or '<absent>'}")
        if doc:
            print(f"      reason    : {doc[:240]}")
    if not differs:
        print("  (none; node counts above prove both graphs were parsed)")

    print("\n=== NORMALIZED WIRING DIFFERENCES ===")
    if not ref_only_edges and not our_only_edges:
        print("  (none; edge multisets and topology digests agree)")
    else:
        for edge in ref_only_edges[:30]:
            print(f"  [reference only] {edge}")
        for edge in our_only_edges[:30]:
            print(f"  [ours only     ] {edge}")
        hidden = len(ref_only_edges) + len(our_only_edges) - 60
        if hidden > 0:
            print(f"  ... {hidden} additional edge deltas in JSON receipt")

    print("\nNOTHING HERE IS A RECOMMENDATION. A human owns every recipe decision.")

    if args.json_out:
        payload = {
            "schema_version": 1,
            "status": "ok",
            "reference": _graph_receipt(reference),
            "ours": _graph_receipt(ours),
            "node_counts": counts,
            "comparison": {
                "topology_digest_equal": topology_equal,
                "reference_only_edges": ref_only_edges,
                "ours_only_edges": our_only_edges,
            },
            "identical_parameters": len(same),
            "differences": [
                {
                    "node": class_type,
                    "param": key,
                    "reference": left,
                    "ours": right,
                    "documented": bool(doc),
                    "reason": doc,
                }
                for class_type, key, left, right, doc in differs
            ],
            "only_in_reference": _only_side_receipt(only_ref),
            "only_in_ours": _only_side_receipt(only_ours),
        }
        _write_json(args.json_out, payload)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
