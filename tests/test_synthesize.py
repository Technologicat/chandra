"""Tests for synthesis (Recipe → A1111 parameters string) and the `igmt inject` round-trip.

`a1111_parse` encodes the A1111 `parameters` format *contract* — the de-facto standard that SD Prompt
Reader (`format/a1111.py`) and CivitAI both consume. It's the always-run acceptance gate: if our
output parses under those rules, those tools read it. `test_real_sdpr_reads_injected` additionally
checks the *actual* SD Prompt Reader parser when importable (it self-skips otherwise — see the
verification recipe in `briefs/rosetta-metadata-injector.md`). Integration tests over `00_stuff/`
skip when absent.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from igmt import cli, pngchunks
from igmt.analyze import Lora, Recipe
from igmt.rosetta import extract_recipe
from igmt.synthesize import synthesize

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "00_stuff"
SAMPLES = sorted(SAMPLES_DIR.glob("*.png")) if SAMPLES_DIR.exists() else []


def a1111_parse(raw):
    """The A1111 `parameters` format contract, encoded as a parser (mirrors SD Prompt Reader's
    `format/a1111.py` and CivitAI's A1111 path). If our output parses here, those tools read it."""
    steps_index = raw.find("\nSteps:")
    positive = negative = setting = ""
    if steps_index != -1:
        positive = raw[:steps_index].strip()
        setting = raw[steps_index:].strip()
    if "Negative prompt:" in raw:
        pi = raw.find("\nNegative prompt:")
        if steps_index != -1:
            negative = raw[pi + len("Negative prompt:") + 1:steps_index].strip()
        else:
            negative = raw[pi + len("Negative prompt:") + 1:].strip()
        positive = raw[:pi].strip()
    elif steps_index == -1:
        positive = raw
    settings = {}
    for k, v in re.findall(r"\s*([^:,]+):\s*([^,]+)", setting):
        settings.setdefault(k, v)
    return positive, negative, settings


# --------------------------------------------------------------------------------
# Unit: format details

def test_synthesize_basic_roundtrips_through_sdpr_rules():
    r = Recipe(positive="a cat", negative="blurry", seed=42, steps=20, cfg=7.0,
               sampler_name="euler", scheduler="normal", denoise=1.0,
               model="sd_xl.safetensors", width=1024, height=768)
    s = synthesize(r, version="9.9")
    pos, neg, sett = a1111_parse(s)
    assert pos == "a cat"
    assert neg == "blurry"
    assert sett == {
        "Steps": "20", "Sampler": "euler", "Schedule type": "normal", "CFG scale": "7",
        "Seed": "42", "Size": "1024x768", "Model": "sd_xl", "Version": "igmt-rosetta 9.9",
    }


def test_denoise_omitted_at_one_emitted_below():
    base = dict(positive="x", steps=10, sampler_name="euler", cfg=1.0, seed=1,
                model="m.safetensors", width=64, height=64)
    assert "Denoising strength" not in synthesize(Recipe(denoise=1.0, **base))
    assert "Denoising strength: 0.5" in synthesize(Recipe(denoise=0.5, **base))


def test_negative_emitted_even_at_cfg_one():
    s = synthesize(Recipe(positive="x", negative="unused at cfg1", cfg=1.0, steps=4,
                          sampler_name="euler", seed=1, model="m.gguf", width=8, height=8))
    assert "Negative prompt: unused at cfg1" in s


def test_no_negative_omits_the_line():
    s = synthesize(Recipe(positive="x", steps=4, sampler_name="euler", seed=1,
                          model="m.gguf", width=8, height=8))
    assert "Negative prompt:" not in s


def test_lora_tags_appended_to_positive():
    r = Recipe(positive="a cat", steps=4, sampler_name="euler", seed=1, model="m.gguf",
               width=8, height=8,
               loras=[Lora("path/to/MyLora.safetensors", 0.8), Lora("accel.gguf", 1.0)])
    pos, _, _ = a1111_parse(synthesize(r))
    assert pos == "a cat <lora:MyLora:0.8> <lora:accel:1>"


def test_cfg_and_steps_formatting():
    s = synthesize(Recipe(positive="x", steps=5.6, cfg=4.5, sampler_name="euler", seed=1,
                          model="m.gguf", width=8, height=8))
    _, _, sett = a1111_parse(s)
    assert sett["Steps"] == "6"        # 5.6 -> nearest whole step
    assert sett["CFG scale"] == "4.5"  # real fraction kept


# --------------------------------------------------------------------------------
# Integration: every sample synthesizes to SDPR-parseable output

@pytest.mark.parametrize("png", SAMPLES, ids=lambda p: p.name)
def test_sample_synthesis_parses_back(png):
    recipe = extract_recipe(png)
    raw = synthesize(recipe)
    pos, neg, sett = a1111_parse(raw)

    assert recipe.positive.strip() in pos               # prompt preserved (LoRA tags may follow)
    assert neg == (recipe.negative or "").strip()       # negative round-trips
    assert sett["Sampler"] == recipe.sampler_name
    assert sett["Seed"] == str(recipe.seed)
    assert sett["Size"] == f"{recipe.width}x{recipe.height}"
    assert sett["Model"]                                # a model name is present
    assert "Steps" in sett
    for lora in recipe.loras:                            # each LoRA shows up as a <lora:...> tag
        from igmt.synthesize import _basename_no_ext
        assert f"<lora:{_basename_no_ext(lora.name)}:" in pos


# --------------------------------------------------------------------------------
# --inject round-trip

@pytest.fixture
def a_sample():
    p = SAMPLES_DIR / "flux2-img2img.png"
    if not p.exists():
        pytest.skip("flux2-img2img.png not present")
    return p


def test_inject_writes_parameters_and_preserves_existing(a_sample, tmp_path):
    dst = tmp_path / "img.png"
    shutil.copy(a_sample, dst)
    before = pngchunks.text_fields(pngchunks.parse_file(dst))

    assert cli.main(["inject", str(dst)]) == 0

    after_chunks = pngchunks.parse_file(dst)
    after = pngchunks.text_fields(after_chunks)
    assert after["parameters"] == synthesize(extract_recipe(dst))
    assert after["prompt"] == before["prompt"]          # ComfyUI chunks untouched
    assert after["workflow"] == before["workflow"]
    assert "parameters" not in before


def test_inject_is_idempotent(a_sample, tmp_path):
    dst = tmp_path / "img.png"
    shutil.copy(a_sample, dst)
    cli.main(["inject", str(dst)])
    cli.main(["inject", str(dst)])
    params = [c for c in pngchunks.parse_file(dst) if pngchunks.keyword_of(c) == "parameters"]
    assert len(params) == 1


@pytest.mark.skipif(shutil.which("pngcheck") is None, reason="pngcheck not installed")
def test_injected_file_is_pngcheck_clean(a_sample, tmp_path):
    dst = tmp_path / "img.png"
    shutil.copy(a_sample, dst)
    cli.main(["inject", str(dst)])
    result = subprocess.run(["pngcheck", "-q", str(dst)], capture_output=True, text=True)
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"


# --------------------------------------------------------------------------------
# Optional: the real SD Prompt Reader parser (self-skips unless importable).
# Install headless without the GUI stack:  pip install --no-deps sd-prompt-reader pillow piexif

def _sdpr_reader():
    try:
        from sd_prompt_reader.image_data_reader import ImageDataReader
        return ImageDataReader
    except Exception:
        return None


@pytest.mark.skipif(_sdpr_reader() is None,
                    reason="sd-prompt-reader parser not importable (see brief's verification recipe)")
def test_real_sdpr_reads_injected(a_sample, tmp_path):
    ImageDataReader = _sdpr_reader()
    dst = tmp_path / "img.png"
    shutil.copy(a_sample, dst)
    cli.main(["inject", str(dst)])
    recipe = extract_recipe(dst)
    with open(dst, "rb") as fh:
        r = ImageDataReader(fh)
    assert r.tool == "ComfyUI\n(A1111 compatible)"
    assert r.status.name == "READ_SUCCESS"
    assert recipe.positive.strip()[:30] in r.positive
    assert r.negative.strip() == (recipe.negative or "").strip()
