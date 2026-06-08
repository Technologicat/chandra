"""Tests for AutoV2 resource hashing: digest, cache, resolver, and the `--hash` CLI path."""

import hashlib
from pathlib import Path

import pytest

from igmt import cli, hashing
from igmt.analyze import Lora, Recipe
from igmt.synthesize import synthesize

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "00_stuff"


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_autov2_is_sha256_first10(tmp_path):
    f = _write(tmp_path / "m.safetensors", b"some weights")
    assert hashing.autov2(f) == hashlib.sha256(b"some weights").hexdigest()[:10]
    assert len(hashing.autov2(f)) == 10


# --------------------------------------------------------------------------------
# HashCache

def test_cache_hit_skips_recompute(tmp_path):
    f = _write(tmp_path / "big.gguf", b"x" * 100)
    cache = hashing.HashCache(tmp_path / "cache.json")
    cache.autov2(f)  # populate the cache
    # Poke the stored value; an unchanged (size, mtime) file must return the cached value verbatim.
    cache._data[str(f.resolve())]["autov2"] = "DEADBEEF00"
    assert cache.autov2(f) == "DEADBEEF00"


def test_cache_invalidates_on_change(tmp_path):
    f = _write(tmp_path / "m.gguf", b"v1")
    cache = hashing.HashCache(tmp_path / "cache.json")
    h1 = cache.autov2(f)
    _write(f, b"v2 longer content")  # different size → entry invalid
    h2 = cache.autov2(f)
    assert h2 != h1
    assert h2 == hashlib.sha256(b"v2 longer content").hexdigest()[:10]


def test_cache_persists_and_reloads(tmp_path):
    f = _write(tmp_path / "m.gguf", b"data")
    p = tmp_path / "cache.json"
    c1 = hashing.HashCache(p)
    c1.autov2(f)
    c1.save()
    c2 = hashing.HashCache(p)
    assert str(f.resolve()) in c2._data


def test_unreadable_file_returns_none(tmp_path):
    assert hashing.HashCache(tmp_path / "c.json").autov2(tmp_path / "nope.gguf") is None


# --------------------------------------------------------------------------------
# ResourceResolver

def test_resolver_basename_and_suffix(tmp_path):
    (tmp_path / "loras" / "sub").mkdir(parents=True)
    (tmp_path / "checkpoints").mkdir()
    lora = _write(tmp_path / "loras" / "sub" / "foo.safetensors", b"a")
    ckpt = _write(tmp_path / "checkpoints" / "model.gguf", b"b")
    r = hashing.ResourceResolver([str(tmp_path)])
    assert r.resolve("model.gguf") == str(ckpt)
    assert r.resolve("foo.safetensors") == str(lora)
    assert r.resolve("sub/foo.safetensors") == str(lora)      # full relative path matches
    assert r.resolve("anything/model.gguf") == str(ckpt)      # basename fallback
    assert r.resolve("missing.safetensors") is None


def test_resolver_prefers_full_relative_path(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _write(tmp_path / "a" / "x.safetensors", b"a")
    want = _write(tmp_path / "b" / "x.safetensors", b"b")
    r = hashing.ResourceResolver([str(tmp_path)])
    assert r.resolve("b/x.safetensors") == str(want)


# --------------------------------------------------------------------------------
# apply_hashes + synthesis

def test_apply_hashes_fills_model_and_loras(tmp_path):
    model = _write(tmp_path / "ckpt.gguf", b"the model")
    lora = _write(tmp_path / "style.safetensors", b"the lora")
    recipe = Recipe(positive="x", steps=4, sampler_name="euler", seed=1, width=8, height=8,
                    model="ckpt.gguf", loras=[Lora("style.safetensors", 1.0), Lora("absent.safetensors", 0.5)])
    resolver = hashing.ResourceResolver([str(tmp_path)])
    cache = hashing.HashCache(tmp_path / "c.json")
    warnings = hashing.apply_hashes(recipe, resolver, cache)

    assert recipe.model_hash == hashing.autov2(model)
    assert recipe.loras[0].hash == hashing.autov2(lora)
    assert recipe.loras[1].hash is None                 # not found on disk
    assert any("absent.safetensors" in w for w in warnings)

    s = synthesize(recipe)
    assert f"Model hash: {recipe.model_hash}" in s
    assert f'Lora hashes: "style: {recipe.loras[0].hash}"' in s


# --------------------------------------------------------------------------------
# CLI --hash end-to-end (dummy files named like the sample's resources)

@pytest.fixture
def qwen_sample():
    p = SAMPLES_DIR / "qwen2512-txt2img.png"
    if not p.exists():
        pytest.skip("qwen2512-txt2img.png not present")
    return p


def test_cli_hash_emits_hashes(qwen_sample, tmp_path, capsys):
    from igmt.rosetta import extract_recipe
    recipe = extract_recipe(qwen_sample)
    models = tmp_path / "models"
    models.mkdir()
    # Create dummy files named after the resources the recipe references.
    _write(models / Path(recipe.model).name, b"checkpoint-bytes")
    for lora in recipe.loras:
        _write(models / Path(lora.name).name, b"lora-" + lora.name.encode()[:8])

    assert cli.main(["show", "--hash", "--models-dir", str(models), str(qwen_sample)]) == 0
    out = capsys.readouterr().out
    assert "Model hash: " in out
    assert "Lora hashes: " in out


def test_cli_hash_without_models_dir_warns_and_omits(qwen_sample, capsys):
    assert cli.main(["show", "--hash", str(qwen_sample)]) == 0
    captured = capsys.readouterr()
    assert "Model hash:" not in captured.out      # nothing hashed
    assert "--models-dir" in captured.err          # but we said why
