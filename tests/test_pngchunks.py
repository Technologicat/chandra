"""Tests for the byte-level PNG chunk layer.

Real-data reads use the local `00_stuff/` samples (gitignored scratch); those tests skip cleanly
when the directory is absent (e.g. in CI). Encode/edge cases use synthetic chunks, and the
`pngcheck`-clean test runs only when the `pngcheck` binary is available.
"""

import json
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

from igmt import pngchunks as pc

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "00_stuff"
SAMPLE_NAME = "flux2-txt2img.png"
SAMPLE_SIZE = (896, 1152)  # known width x height of the sample render


@pytest.fixture
def sample_path() -> Path:
    p = SAMPLES_DIR / SAMPLE_NAME
    if not p.exists():
        pytest.skip(f"sample {p} not present (00_stuff is local scratch)")
    return p


@pytest.fixture
def sample_chunks(sample_path):
    return pc.parse_file(sample_path)


# --------------------------------------------------------------------------------
# Reading / lossless round-trip

def test_read_rejects_non_png():
    with pytest.raises(ValueError):
        pc.read_chunks(b"definitely not a png")


def test_roundtrip_is_byte_exact(sample_path):
    """serialize(read_chunks(blob)) == blob — the losslessness the injection relies on."""
    blob = sample_path.read_bytes()
    assert pc.serialize(pc.read_chunks(blob)) == blob


def test_all_samples_roundtrip():
    """Every available sample round-trips byte-exactly (covers tEXt and iTXt-bearing files)."""
    if not SAMPLES_DIR.exists():
        pytest.skip("00_stuff not present")
    pngs = sorted(SAMPLES_DIR.glob("*.png"))
    if not pngs:
        pytest.skip("no sample PNGs")
    for p in pngs:
        blob = p.read_bytes()
        assert pc.serialize(pc.read_chunks(blob)) == blob, f"round-trip changed bytes for {p.name}"


def test_first_chunk_is_ihdr_last_is_iend(sample_chunks):
    assert sample_chunks[0].type == b"IHDR"
    assert sample_chunks[-1].type == b"IEND"


# --------------------------------------------------------------------------------
# Text fields and image size

def test_reads_comfyui_text_fields(sample_chunks):
    fields = pc.text_fields(sample_chunks)
    assert "prompt" in fields and "workflow" in fields
    # both are JSON; the prompt graph is keyed by node id with class_type/inputs
    graph = json.loads(fields["prompt"])
    assert any(node.get("class_type", "").startswith("KSampler") for node in graph.values())


def test_get_text_field_missing_is_none(sample_chunks):
    assert pc.get_text_field(sample_chunks, "no-such-keyword") is None


def test_image_size(sample_chunks):
    assert pc.image_size(sample_chunks) == SAMPLE_SIZE


def test_image_size_from_synthetic_ihdr():
    ihdr = pc.Chunk(b"IHDR", (1234).to_bytes(4, "big") + (567).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
    assert pc.image_size([ihdr, pc.Chunk(b"IEND", b"")]) == (1234, 567)


# --------------------------------------------------------------------------------
# Encoding: tEXt vs iTXt selection

def test_latin1_text_becomes_tEXt():
    ch = pc.make_text_chunk("parameters", "a cat, masterpiece, Steps: 4")
    assert ch.type == b"tEXt"
    assert pc.decode_text_chunk(ch) == ("parameters", "a cat, masterpiece, Steps: 4")


def test_non_latin1_text_becomes_iTXt():
    text = "日本語, café, 🎨 emoji"
    ch = pc.make_text_chunk("parameters", text)
    assert ch.type == b"iTXt"
    assert pc.decode_text_chunk(ch) == ("parameters", text)


def test_keyword_length_validation():
    with pytest.raises(ValueError):
        pc.make_text_chunk("", "x")
    with pytest.raises(ValueError):
        pc.make_text_chunk("k" * 80, "x")


# --------------------------------------------------------------------------------
# Decoding the other text forms (synthetic, since samples only carry tEXt)

def test_decode_ztxt():
    body = b"Comment\x00" + b"\x00" + zlib.compress(b"compressed latin-1 text")
    assert pc.decode_text_chunk(pc.Chunk(b"zTXt", body)) == ("Comment", "compressed latin-1 text")


def test_decode_itxt_compressed_with_lang():
    text = "parameters payload with ünicode"
    body = (b"parameters\x00"
            + b"\x01\x00"          # compressed flag = 1, method = 0
            + b"en\x00"            # language tag
            + b"params\x00"        # translated keyword
            + zlib.compress(text.encode("utf-8")))
    assert pc.decode_text_chunk(pc.Chunk(b"iTXt", body)) == ("parameters", text)


def test_non_text_chunk_decodes_to_none():
    assert pc.decode_text_chunk(pc.Chunk(b"IDAT", b"\x00\x01")) is None
    assert pc.keyword_of(pc.Chunk(b"IDAT", b"\x00")) is None


# --------------------------------------------------------------------------------
# set_text_field: insertion, idempotency, replace-either-form

def _minimal_chunks():
    ihdr = pc.Chunk(b"IHDR", (8).to_bytes(4, "big") + (8).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
    return [ihdr, pc.Chunk(b"IDAT", b"\x00deadbeef"), pc.Chunk(b"IEND", b"")]


def test_set_text_inserts_before_iend():
    out = pc.set_text_field(_minimal_chunks(), "parameters", "Steps: 4")
    assert [c.type for c in out][-2:] == [b"tEXt", b"IEND"]   # inserted just before IEND
    assert pc.get_text_field(out, "parameters") == "Steps: 4"


def test_set_text_is_idempotent_and_updates():
    out = pc.set_text_field(_minimal_chunks(), "parameters", "first")
    out = pc.set_text_field(out, "parameters", "second")
    params = [c for c in out if pc.keyword_of(c) == "parameters"]
    assert len(params) == 1                       # exactly one, never stacked
    assert pc.get_text_field(out, "parameters") == "second"


def test_set_text_replaces_either_chunk_form():
    # Start with a pre-existing `parameters` in BOTH tEXt and iTXt forms.
    itxt = pc.Chunk(b"iTXt", b"parameters\x00\x00\x00\x00\x00old utf8")
    chunks = [
        pc.Chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"),
        pc.make_text_chunk("parameters", "old latin1"),  # tEXt
        itxt,
        pc.Chunk(b"IEND", b""),
    ]
    out = pc.set_text_field(chunks, "parameters", "new")
    params = [c for c in out if pc.keyword_of(c) == "parameters"]
    assert len(params) == 1
    assert pc.get_text_field(out, "parameters") == "new"


def test_set_text_preserves_existing_fields(sample_chunks):
    """Injecting `parameters` must not disturb the ComfyUI prompt/workflow chunks."""
    before = pc.text_fields(sample_chunks)
    out = pc.set_text_field(sample_chunks, "parameters", "Steps: 4, Sampler: dpmpp_2m")
    after = pc.text_fields(out)
    assert after["prompt"] == before["prompt"]
    assert after["workflow"] == before["workflow"]
    assert after["parameters"] == "Steps: 4, Sampler: dpmpp_2m"


def test_remove_text_fields():
    out = pc.set_text_field(_minimal_chunks(), "parameters", "x")
    out = pc.remove_text_fields(out, "parameters")
    assert pc.get_text_field(out, "parameters") is None


# --------------------------------------------------------------------------------
# CRC correctness on real data, via pngcheck

@pytest.mark.skipif(shutil.which("pngcheck") is None, reason="pngcheck not installed")
def test_injected_png_is_pngcheck_clean(sample_path, tmp_path):
    out_path = tmp_path / "injected.png"
    chunks = pc.parse_file(sample_path)
    chunks = pc.set_text_field(chunks, "parameters", "a cat\nNegative prompt: blurry\nSteps: 4, Size: 896x1152")
    pc.write_file(out_path, chunks)
    result = subprocess.run(["pngcheck", "-q", str(out_path)], capture_output=True, text=True)
    assert result.returncode == 0, f"pngcheck failed: {result.stdout}{result.stderr}"
    # and the injected field reads back from the freshly written file
    assert pc.get_text_field(pc.parse_file(out_path), "parameters").startswith("a cat")
