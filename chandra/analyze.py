"""Analyze a ComfyUI `prompt` graph into a normalized `Recipe`.

This is the heart of `rosetta`. Both CivitAI and SD Prompt Reader punt on non-trivial ComfyUI
graphs; we walk the graph ourselves and reduce it to the generation recipe, which synthesis then
renders as an A1111 `parameters` string. See `briefs/rosetta-metadata-injector.md`.

The walk is **role-based**, never keyed on node id or exact class name (those vary across node packs
and templates): we recognize a node by the shape of its inputs. We traverse the API-format `prompt`
graph — `{node_id: {"class_type", "inputs"}}`, each input either a literal or a `[node_id, slot]`
link — which is the *executed* graph (bypassed/muted/UI-only nodes are already absent), so toggled-off
LoRAs and reference chains need no special handling.

Strategy: find the Save-Image sink → walk to the sampler feeding it → read the sampler's scalars
(resolving literals, `Primitive*` values, and `Evaluate*` expressions) → trace its positive/negative
conditioning back through passthrough nodes to the text encoders → walk its model link through the
LoRA chain to the base loader. Image size comes from the PNG `IHDR`, not the graph (the most reliable
source, and Flux.2's latent geometry differs from older models / inpaint sizes are crop regions).
"""

import math
from dataclasses import dataclass, field
from typing import Optional

try:
    from simpleeval import simple_eval
except ImportError:  # resolver degrades gracefully without it
    simple_eval = None

__all__ = ["Lora", "Recipe", "analyze", "format_recipe"]

_MAX_DEPTH = 64  # guard against cycles/pathological graphs (the graph is a DAG, but a file may lie)

# Whitelisted functions for Evaluate* expressions, on top of simpleeval's safe arithmetic.
_SAFE_FUNCS = {
    "int": int, "float": float, "round": round, "abs": abs,
    "min": min, "max": max, "ceil": math.ceil, "floor": math.floor, "pow": pow,
}


@dataclass
class Lora:
    name: str
    strength: Optional[float] = None
    hash: Optional[str] = None          # AutoV2, filled in by the hashing step (--hash)


@dataclass
class Recipe:
    """The generation recipe extracted from a ComfyUI graph. Fields are None when unresolved."""
    positive: Optional[str] = None
    negative: Optional[str] = None
    seed: Optional[object] = None          # int in practice; kept loose for odd graphs
    steps: Optional[object] = None
    cfg: Optional[object] = None
    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None
    denoise: Optional[object] = None
    model: Optional[str] = None
    model_hash: Optional[str] = None    # AutoV2, filled in by the hashing step (--hash)
    loras: list = field(default_factory=list)
    vae: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sampler_class: Optional[str] = None
    warnings: list = field(default_factory=list)


# --------------------------------------------------------------------------------
# Role predicates — recognize a node by the shape of its inputs, not its exact class name.

def _inputs(node) -> dict:
    return node.get("inputs", {}) if node else {}


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _is_sampler(node) -> bool:
    ins = _inputs(node)
    has_contract = "steps" in ins and ("cfg" in ins or "sampler_name" in ins)
    return has_contract or "sampler" in node.get("class_type", "").lower()


def _is_save(node) -> bool:
    ct = node.get("class_type", "").lower()
    return "save" in ct and "image" in ct


def _is_base_loader_field(name: str) -> bool:
    return name in ("ckpt_name", "gguf_name", "unet_name", "model_path")


# --------------------------------------------------------------------------------
# Scalar resolution: literal | Primitive*.value | Evaluate* expression.

def _resolve_value(graph, v, depth=0):
    """Resolve a scalar input to a concrete value, or None if it can't be resolved honestly."""
    if not _is_link(v):
        return v  # already a literal
    if depth > _MAX_DEPTH:
        return None
    node = graph.get(v[0])
    if node is None:
        return None
    ins = _inputs(node)
    ct = node.get("class_type", "")

    if "python_expression" in ins:  # Evaluate Integers / Evaluate Floats (and kin)
        if simple_eval is None:
            return None
        names = {name: _resolve_value(graph, ins.get(name, 0), depth + 1) for name in ("a", "b", "c")}
        if any(val is None for val in names.values()):
            return None
        try:
            return simple_eval(ins["python_expression"], names=names, functions=_SAFE_FUNCS)
        except Exception:
            return None

    if ct.startswith("Primitive") or "value" in ins:  # PrimitiveInt/Float/String → value
        return _resolve_value(graph, ins.get("value"), depth + 1)

    return None  # unknown scalar source → unresolved (honest fallback)


def _resolve_string(graph, ref, depth=0):
    """A text field may be a literal or a link to an upstream string-bearing node."""
    if isinstance(ref, str):
        return ref
    if not _is_link(ref) or depth > _MAX_DEPTH:
        return None
    node = graph.get(ref[0])
    ins = _inputs(node)
    for key in ("value", "text", "string", "prompt"):
        if key in ins:
            return _resolve_string(graph, ins[key], depth + 1)
    return None


# --------------------------------------------------------------------------------
# Graph navigation

def _subgraph_size(graph, start_id):
    """Count nodes reachable upstream from start_id (for picking the dominant sink)."""
    seen, stack = set(), [start_id]
    while stack:
        nid = stack.pop()
        if nid in seen or nid not in graph:
            continue
        seen.add(nid)
        for v in _inputs(graph[nid]).values():
            if _is_link(v):
                stack.append(v[0])
    return len(seen)


def _pick_sink(graph, warnings):
    saves = [nid for nid, node in graph.items() if _is_save(node)]
    if not saves:
        # Fallback: no Save-Image node — treat the largest sampler subgraph as the endpoint.
        samplers = [nid for nid, node in graph.items() if _is_sampler(node)]
        if not samplers:
            warnings.append("no Save-Image or sampler node found")
            return None
        warnings.append("no Save-Image node; using the largest sampler subgraph")
        return max(samplers, key=lambda nid: _subgraph_size(graph, nid))
    if len(saves) > 1:
        warnings.append(f"{len(saves)} Save-Image nodes; using the one with the largest subgraph")
    return max(saves, key=lambda nid: _subgraph_size(graph, nid))


# Inputs to follow on the produced-image path from the sink toward the sampler, in priority order.
# (Latent/sample path first, then composited-image inputs — e.g. inpaint crop-and-stitch.)
_IMAGE_PATH_KEYS = ("samples", "latent", "inpainted_image", "stitched_image", "image", "images")


def _next_image_ref(ins):
    """The link to follow toward the sampler: a known image/latent input, else a generic one.

    Source-side inputs (mask, vae, the original `pixels`/`stitcher`) are excluded so we follow the
    *produced* image, not the inputs that fed the inpaint/img2img region.
    """
    for key in _IMAGE_PATH_KEYS:
        if _is_link(ins.get(key)):
            return ins[key]
    for k, v in ins.items():
        kl = k.lower()
        if _is_link(v) and any(t in kl for t in ("image", "latent", "sample")) \
                and not any(t in kl for t in ("mask", "vae", "pixel", "stitch")):
            return v
    return None


def _find_sampler(graph, sink_id, warnings):
    """From the sink, follow the produced-image path until a sampler-role node is reached."""
    node = graph.get(sink_id)
    if _is_sampler(node):  # sink fallback was itself a sampler
        return sink_id
    ref = _inputs(node).get("images") if node else None
    seen = set()
    while _is_link(ref) and ref[0] not in seen:
        nid = ref[0]
        seen.add(nid)
        cur = graph.get(nid)
        if cur is None:
            break
        if _is_sampler(cur):
            return nid
        ref = _next_image_ref(_inputs(cur))
    warnings.append("could not locate a sampler upstream of the sink")
    return None


def _trace_conditioning(graph, ref, depth=0):
    """Follow a conditioning link back to a text encoder; return the prompt text or None.

    Handles direct encoders (`text`/`prompt`), single-conditioning passthroughs (`ReferenceLatent`,
    …), and dual-output passthroughs (`InpaintModelConditioning`, `ControlNetApplyAdvanced`) where
    the slot index of the incoming link selects the positive (0) or negative (1) branch.
    """
    if not _is_link(ref) or depth > _MAX_DEPTH:
        return None
    nid, slot = ref
    node = graph.get(nid)
    if node is None:
        return None
    ins = _inputs(node)

    if "text" in ins:
        return _resolve_string(graph, ins["text"], depth + 1)
    if "prompt" in ins:
        return _resolve_string(graph, ins["prompt"], depth + 1)
    if "positive" in ins and "negative" in ins:
        branch = "positive" if slot == 0 else "negative"
        return _trace_conditioning(graph, ins.get(branch), depth + 1)
    if "conditioning" in ins:
        return _trace_conditioning(graph, ins["conditioning"], depth + 1)
    return None


def _walk_model(graph, ref):
    """Walk the model link through the LoRA chain to the base loader.

    Returns (model_name, [Lora, ...]). Collects every LoRA encountered (chains can be long), then
    reads the base loader's model-name field (ckpt_name/gguf_name/unet_name).
    """
    loras = []
    model_name = None
    seen = set()
    while _is_link(ref) and ref[0] not in seen:
        nid = ref[0]
        seen.add(nid)
        node = graph.get(nid)
        if node is None:
            break
        ins = _inputs(node)
        if "lora_name" in ins:
            loras.append(Lora(name=_resolve_string(graph, ins["lora_name"]),
                              strength=_resolve_value(graph, ins.get("strength_model"))))
            ref = ins.get("model")
            continue
        base_field = next((k for k in ins if _is_base_loader_field(k)), None)
        if base_field is not None:
            model_name = _resolve_string(graph, ins[base_field])
            break
        ref = ins.get("model")  # unknown model-passthrough: keep walking
    return model_name, loras


def _find_vae(graph, sampler_id):
    """Best-effort VAE name from the sampler's optional_vae / vae input."""
    ins = _inputs(graph.get(sampler_id))
    ref = ins.get("optional_vae") or ins.get("vae")
    seen = set()
    while _is_link(ref) and ref[0] not in seen:
        nid = ref[0]
        seen.add(nid)
        node = graph.get(nid)
        if node is None:
            break
        nins = _inputs(node)
        if "vae_name" in nins:
            return _resolve_string(graph, nins["vae_name"])
        ref = nins.get("vae") or nins.get("samples")
    return None


# --------------------------------------------------------------------------------
# Top-level

def analyze(graph: dict, width: Optional[int] = None, height: Optional[int] = None) -> Recipe:
    """Reduce a ComfyUI `prompt` graph (+ PNG dimensions) to a `Recipe`."""
    recipe = Recipe(width=width, height=height)

    sink_id = _pick_sink(graph, recipe.warnings)
    if sink_id is None:
        return recipe
    sampler_id = _find_sampler(graph, sink_id, recipe.warnings)
    if sampler_id is None:
        return recipe

    sampler = graph[sampler_id]
    ins = _inputs(sampler)
    recipe.sampler_class = sampler.get("class_type")

    # Scalars (resolving literals / Primitive* / Evaluate*).
    seed_ref = ins.get("seed", ins.get("noise_seed"))
    recipe.seed = _resolve_value(graph, seed_ref)
    recipe.steps = _resolve_value(graph, ins.get("steps"))
    recipe.cfg = _resolve_value(graph, ins.get("cfg"))
    recipe.sampler_name = _resolve_value(graph, ins.get("sampler_name"))
    recipe.scheduler = _resolve_value(graph, ins.get("scheduler"))
    recipe.denoise = _resolve_value(graph, ins.get("denoise"))

    # Prompts via the conditioning chain.
    recipe.positive = _trace_conditioning(graph, ins.get("positive"))
    recipe.negative = _trace_conditioning(graph, ins.get("negative"))

    # Model + LoRAs, and VAE.
    recipe.model, recipe.loras = _walk_model(graph, ins.get("model"))
    recipe.vae = _find_vae(graph, sampler_id)

    if recipe.positive is None and recipe.negative is None:
        recipe.warnings.append("no prompt text resolved")
    if recipe.model is None:
        recipe.warnings.append("model name unresolved")

    return recipe


def format_recipe(recipe: Recipe) -> str:
    """A readable multi-line dump of a Recipe, for `chandra rosetta --print`."""
    lines = []
    lines.append(f"positive: {recipe.positive!r}")
    lines.append(f"negative: {recipe.negative!r}")
    size = f"{recipe.width}x{recipe.height}" if recipe.width and recipe.height else "?"
    lines.append(f"size:     {size}")
    model_hash = f"  [{recipe.model_hash}]" if recipe.model_hash else ""
    lines.append(f"model:    {recipe.model!r}{model_hash}")
    for lora in recipe.loras:
        lora_hash = f"  [{lora.hash}]" if lora.hash else ""
        lines.append(f"  lora:   {lora.name!r} (strength {lora.strength}){lora_hash}")
    if recipe.vae:
        lines.append(f"vae:      {recipe.vae!r}")
    lines.append(f"sampler:  {recipe.sampler_name!r}  scheduler: {recipe.scheduler!r}  "
                 f"({recipe.sampler_class})")
    lines.append(f"steps:    {recipe.steps}   cfg: {recipe.cfg}   denoise: {recipe.denoise}   "
                 f"seed: {recipe.seed}")
    for w in recipe.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
