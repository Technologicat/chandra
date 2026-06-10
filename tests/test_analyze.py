"""Tests for the graph-walk Analyze stage.

Synthetic-graph unit tests exercise the resolver and traversal logic and always run. Integration
tests run the analyzer over the real `00_stuff/` samples and skip when that local scratch dir is
absent (e.g. in CI).
"""

from pathlib import Path

import pytest

from chandra import analyze
from chandra.analyze import Recipe
from chandra.rosetta import extract_recipe

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "00_stuff"
SAMPLES = sorted(SAMPLES_DIR.glob("*.png")) if SAMPLES_DIR.exists() else []


# --------------------------------------------------------------------------------
# Synthetic graphs — the building blocks, no sample data needed.

def _txt2img_graph():
    return {
        "save": {"class_type": "SaveImage", "inputs": {"images": ["ks", 5]}},
        "ks": {"class_type": "KSampler (Efficient)", "inputs": {
            "seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal",
            "denoise": 1.0, "model": ["ckpt", 0], "positive": ["pos", 0], "negative": ["neg", 0],
            "latent_image": ["lat", 0], "optional_vae": ["vae", 0]}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["ckpt", 1]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["ckpt", 1]}},
        "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "lat": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.pt"}},
    }


def test_analyze_minimal_txt2img():
    r = analyze.analyze(_txt2img_graph(), 512, 512)
    assert r.positive == "a cat" and r.negative == "blurry"
    assert r.seed == 42 and r.steps == 20 and r.cfg == 7.0 and r.denoise == 1.0
    assert r.sampler_name == "euler" and r.scheduler == "normal"
    assert r.model == "model.safetensors" and r.vae == "vae.pt"
    assert r.width == 512 and r.height == 512
    assert r.warnings == []


def test_resolve_literal_primitive_and_evaluate():
    graph = {
        "ev": {"class_type": "Evaluate Floats",
               "inputs": {"python_expression": "a * b", "a": ["pf", 0], "b": 40, "c": 0.0}},
        "pf": {"class_type": "PrimitiveFloat", "inputs": {"value": 0.5}},
    }
    assert analyze._resolve_value(graph, 12) == 12                  # literal
    assert analyze._resolve_value(graph, ["pf", 0]) == 0.5          # Primitive.value
    assert analyze._resolve_value(graph, ["ev", 0]) == 20.0         # 0.5 * 40
    assert analyze._resolve_value(graph, ["nope", 0]) is None       # unresolved → None


def test_evaluate_with_whitelisted_function():
    graph = {"ev": {"class_type": "Evaluate Integers",
                    "inputs": {"python_expression": "int(ceil(a * b))", "a": 0.3, "b": 21, "c": 0}}}
    assert analyze._resolve_value(graph, ["ev", 0]) == 7           # ceil(6.3) -> 7


def test_trace_conditioning_through_inpaint_dual_output():
    graph = {
        "imc": {"class_type": "InpaintModelConditioning",
                "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                           "vae": ["v", 0], "pixels": ["p", 0], "mask": ["m", 0]}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": "POS"}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": "NEG"}},
    }
    assert analyze._trace_conditioning(graph, ["imc", 0]) == "POS"  # slot 0 -> positive branch
    assert analyze._trace_conditioning(graph, ["imc", 1]) == "NEG"  # slot 1 -> negative branch


def test_trace_conditioning_through_reference_latent():
    graph = {
        "ref": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["enc", 0], "latent": ["x", 0]}},
        "enc": {"class_type": "CLIPTextEncode", "inputs": {"text": "edit this"}},
    }
    assert analyze._trace_conditioning(graph, ["ref", 0]) == "edit this"


def test_walk_model_collects_lora_chain():
    # Three chained LoRAs -> base loader: the walk handles arbitrary depth, in order.
    graph = {
        "l1": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"lora_name": "accel.safetensors", "strength_model": 1.0, "model": ["l2", 0]}},
        "l2": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"lora_name": "style.safetensors", "strength_model": 0.8, "model": ["l3", 0]}},
        "l3": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"lora_name": "detail.safetensors", "strength_model": 0.5, "model": ["base", 0]}},
        "base": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "base.gguf"}},
    }
    model, loras = analyze._walk_model(graph, ["l1", 0])
    assert model == "base.gguf"
    assert [(lo.name, lo.strength) for lo in loras] == [
        ("accel.safetensors", 1.0), ("style.safetensors", 0.8), ("detail.safetensors", 0.5)]


def test_find_sampler_through_inpaint_stitch():
    graph = {
        "save": {"class_type": "SaveImage", "inputs": {"images": ["stitch", 0]}},
        "stitch": {"class_type": "InpaintStitchImproved",
                   "inputs": {"stitcher": ["crop", 0], "inpainted_image": ["ks", 5]}},
        "ks": {"class_type": "KSampler", "inputs": {"steps": 4, "sampler_name": "euler", "cfg": 1.0}},
        "crop": {"class_type": "InpaintCropImproved", "inputs": {"image": ["load", 0]}},
    }
    warnings = []
    assert analyze._find_sampler(graph, "save", warnings) == "ks"
    assert warnings == []


def test_find_sampler_through_vae_decode():
    graph = {
        "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["v", 0]}},
        "ks": {"class_type": "KSampler", "inputs": {"steps": 4, "sampler_name": "euler", "cfg": 1.0}},
    }
    assert analyze._find_sampler(graph, "save", []) == "ks"


def test_no_sampler_warns():
    graph = {"save": {"class_type": "SaveImage", "inputs": {"images": ["x", 0]}},
             "x": {"class_type": "SomethingElse", "inputs": {}}}
    r = analyze.analyze(graph, 64, 64)
    assert r.sampler_class is None
    assert any("sampler" in w for w in r.warnings)


# --------------------------------------------------------------------------------
# Integration over the real samples.

@pytest.mark.parametrize("png", SAMPLES, ids=lambda p: p.name)
def test_every_sample_fully_analyzes(png):
    r = extract_recipe(png)
    assert r.warnings == [], f"{png.name}: {r.warnings}"
    assert r.sampler_name == "dpmpp_2m" and r.scheduler == "sgm_uniform"
    assert r.model, "model unresolved"
    assert r.positive, "positive prompt unresolved"
    assert isinstance(r.seed, int)
    assert r.width and r.height


def _recipe(name) -> Recipe:
    p = SAMPLES_DIR / name
    if not p.exists():
        pytest.skip(f"{name} not present")
    return extract_recipe(p)


def test_img2img_evaluate_resolved_steps():
    r = _recipe("flux2-img2img.png")
    assert r.denoise == 0.7
    assert r.steps == pytest.approx(5.6)  # 0.7 * base steps, via the Evaluate* dynamic-steps chain


def test_multi_lora_chain_from_sample():
    r = _recipe("qwen2512-txt2img.png")
    assert len(r.loras) == 2
    names = " ".join(lo.name for lo in r.loras)
    assert "Lightning" in names and "illustria" in names


def test_edit_mode_reference_latent_prompt():
    r = _recipe("flux2-edit.png")
    assert r.positive.startswith('Change the text on the sign')


def test_qwen_edit_fused_encoder_prompt():
    r = _recipe("qwen-edit-2511-basic.png")
    assert "outfit" in r.positive
    assert "qwen-image-edit" in r.model


def test_inpaint_stitch_sample_resolves():
    # Regression guard for the crop-and-stitch sink->sampler path.
    r = _recipe("qwen2512-inpaint.png")
    assert r.model and r.sampler_name == "dpmpp_2m"
    assert "in-paint" in r.positive


# --------------------------------------------------------------------------------
# format_description (clean rendering for the embedded XMP description)

def test_format_description_is_clean_text_not_repr():
    r = Recipe(positive="a catgirl\nmasterpiece", negative="blurry", seed=1, steps=20, cfg=4.0,
               sampler_name="euler", scheduler="normal", denoise=1.0, model="m.gguf", width=8, height=8)
    out = analyze.format_description(r)
    assert "Positive:\na catgirl\nmasterpiece" in out  # real newlines, no repr quoting
    assert "'a catgirl" not in out and "\\n" not in out  # not repr()-style
    assert "Negative:\nblurry" in out
    assert "Size:     8x8" in out and "Model:    m.gguf" in out


def test_format_description_omits_empty_sections():
    r = Recipe(positive="x", negative="", seed=1, steps=4, sampler_name="euler",
               scheduler="normal", model="m", width=8, height=8)
    out = analyze.format_description(r)
    assert "Negative:" not in out  # empty negative is omitted, not shown blank
    assert "VAE:" not in out and "LoRA:" not in out


def test_format_description_includes_loras_and_vae():
    from chandra.analyze import Lora
    r = Recipe(positive="x", seed=1, steps=4, sampler_name="euler", scheduler="normal", model="m",
               vae="ae.safetensors", loras=[Lora(name="style.safetensors", strength=0.8)],
               width=8, height=8)
    out = analyze.format_description(r)
    assert "LoRA:     style.safetensors (strength 0.8)" in out
    assert "VAE:      ae.safetensors" in out
