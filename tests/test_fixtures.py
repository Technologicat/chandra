"""Structural integration tests over the committed, anonymized fixtures (`tests/fixtures/`).

These fixtures are `chandra scrub` skeletons of real ComfyUI workflows — graph wiring intact, image
and prompt prose removed (see `briefs/palimpsest-scrub.md`). Unlike the `00_stuff/` content tests
(which assert exact prompt text and only run where that gitignored scratch dir is present), these are
committed, so they run everywhere — giving CI coverage of the parser against real graph *structures*.

What can be asserted here is structure (model resolved, LoRA count, sampler, size, round-trip), not
prose — the prompts are placeholders. Expected values below were verified by eye against the real
workflows at fixture-creation time; they are golden, not derived from the parser under test.
"""

from pathlib import Path

import pytest

from chandra import pngchunks, synthesize
from chandra.rosetta import extract_recipe

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES = sorted(FIXTURES_DIR.glob("*.png"))


def test_fixtures_present():
    # If this fails, the committed fixtures are missing — regenerate with `chandra scrub`.
    assert FIXTURES, f"no fixtures in {FIXTURES_DIR}"


# --------------------------------------------------------------------------------
# The fixtures are properly anonymized (guards against committing a real image by mistake)

@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_is_a_scrubbed_skeleton(path):
    chunks = pngchunks.parse_file(path)
    types = [c.type for c in chunks]
    assert b"IDAT" not in types                         # no pixels
    fields = pngchunks.text_fields(chunks)
    assert "workflow" not in fields                     # no UI graph / notes / prompt copy
    assert "parameters" not in fields                   # not pre-injected
    # Every prompt in the skeleton is a placeholder, never leftover prose.
    recipe = extract_recipe(path)
    for prompt in (recipe.positive or "", recipe.negative or ""):
        assert prompt == "" or prompt.startswith("scrubbed ")


# --------------------------------------------------------------------------------
# Every fixture parses to a usable recipe and round-trips through synthesize

@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_parses_and_synthesizes(path):
    recipe = extract_recipe(path)
    assert recipe.model                                 # a checkpoint/unet was resolved
    assert recipe.sampler_name                          # a sampler was found
    assert recipe.width and recipe.height               # size from IHDR
    params = synthesize.synthesize(recipe)
    assert "Steps:" in params and "Model:" in params    # a valid A1111 parameters string


# --------------------------------------------------------------------------------
# Targeted structural goldens — the distinctive cases (mirrors of the 00_stuff content tests,
# asserting the structure that survives scrubbing rather than the prose that doesn't)

def _recipe(name):
    return extract_recipe(FIXTURES_DIR / name)


def test_multi_lora_chain_structure():
    r = _recipe("qwen2512-txt2img.png")
    assert len(r.loras) == 2
    names = " ".join(lo.name for lo in r.loras)
    assert "Lightning" in names and "illustria" in names


def test_qwen_edit_model_resolves():
    r = _recipe("qwen-edit-2511-basic.png")
    assert "qwen-image-edit" in r.model


def test_inpaint_stitch_resolves():
    # Regression guard for the crop-and-stitch sink->sampler path (structure, not prose).
    r = _recipe("qwen2512-inpaint.png")
    assert r.model and r.sampler_name == "dpmpp_2m"


def test_img2img_has_partial_denoise():
    # img2img runs at denoise < 1.0; the synthesized params carry the Denoising strength field.
    r = _recipe("chroma1-hd-img2img.png")
    assert float(r.denoise) < 1.0
    assert "Denoising strength" in synthesize.synthesize(r)
