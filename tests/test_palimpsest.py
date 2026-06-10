"""Tests for `chandra scrub` (the palimpsest engine): de-branding a ComfyUI PNG to a skeleton."""

import json

from chandra import cli, palimpsest, pngchunks


def _graph():
    """A small ComfyUI `prompt` graph with text, model names, links, and user file references."""
    return {
        "3": {"inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                         "scheduler": "sgm_uniform", "model": ["4", 0],
                         "positive": ["6", 0], "negative": ["7", 0]},
              "class_type": "KSampler", "_meta": {"title": "KSampler"}},
        "4": {"inputs": {"ckpt_name": "models/SomeModel-Q4.gguf"}, "class_type": "CheckpointLoaderSimple"},
        "6": {"inputs": {"text": "a very private positive prompt the user would rather not publish",
                        "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"text": "an equally telling negative prompt full of personal style markers",
                        "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "9": {"inputs": {"filename_prefix": "20260101-1234-MyBrand", "images": ["3", 0]},
              "class_type": "SaveImage"},
    }


_NOTE_TEXT = "secret note: my private workflow documentation"


def _png_chunks(graph):
    ihdr = pngchunks.Chunk(b"IHDR", (8).to_bytes(4, "big") + (8).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
    # The real `workflow` chunk also carries a Note node AND a second copy of the prompt text in its
    # widget values — both must be gone after scrubbing (the back-door leak the `workflow` drop closes).
    pos_text = graph["6"]["inputs"]["text"]
    workflow = json.dumps({"nodes": [
        {"type": "MarkdownNote", "widgets_values": [_NOTE_TEXT]},
        {"type": "CLIPTextEncode", "widgets_values": [pos_text]},
    ]})
    return [
        ihdr,
        pngchunks.make_text_chunk("prompt", json.dumps(graph)),
        pngchunks.make_text_chunk("workflow", workflow),
        pngchunks.Chunk(b"IDAT", b"\x00fake pixels"),
        pngchunks.Chunk(b"IEND", b""),
    ]


# --------------------------------------------------------------------------------
# scrub_graph

def test_neutralizes_prompt_text_but_keeps_structure():
    graph, n = palimpsest.scrub_graph(_graph())
    assert n == 2
    assert graph["6"]["inputs"]["text"] == "scrubbed positive prompt"   # role via analyze.conditioning_roles
    assert graph["7"]["inputs"]["text"] == "scrubbed negative prompt"
    assert graph["4"]["inputs"]["ckpt_name"] == "scrubbed-checkpoint"   # checkpoint name scrubbed
    assert graph["3"]["inputs"]["sampler_name"] == "dpmpp_2m"            # short tokens kept
    assert graph["3"]["inputs"]["positive"] == ["6", 0]                  # link wiring kept
    assert graph["3"]["inputs"]["seed"] == 42                            # numbers kept


def test_neutralizes_user_file_references():
    graph, _ = palimpsest.scrub_graph(_graph())
    assert graph["9"]["inputs"]["filename_prefix"] == "scrubbed"         # SaveImage prefix scrubbed
    assert graph["9"]["inputs"]["images"] == ["3", 0]                    # but the link is kept


def test_freetext_safety_net_catches_unknown_keys():
    # A prompt stashed under a non-standard key is still caught by the long-free-text rule.
    graph = {"1": {"inputs": {"custom_field": "x" * 60}, "class_type": "WeirdNode"}}
    out, n = palimpsest.scrub_graph(graph)
    assert n == 1 and out["1"]["inputs"]["custom_field"] == "scrubbed prompt (node 1)"


def test_scrubs_weights_keeps_infra_names():
    graph = {"1": {"inputs": {"vae_name": "flux_vae.safetensors", "mode": "balanced",
                              "clip_name": "t5xxl_fp8_scaled.safetensors",
                              "lora_name": "chroma/style/SomeConcept-v3.safetensors",
                              "ckpt_name": "SomeCheckpoint-Q4.gguf"},
                   "class_type": "Loader"}}
    out, n = palimpsest.scrub_graph(graph)
    assert n == 0  # no prompts here
    assert out["1"]["inputs"]["lora_name"] == "scrubbed-lora"            # weight name scrubbed
    assert out["1"]["inputs"]["ckpt_name"] == "scrubbed-checkpoint"
    assert out["1"]["inputs"]["vae_name"] == "flux_vae.safetensors"      # infra kept
    assert out["1"]["inputs"]["clip_name"] == "t5xxl_fp8_scaled.safetensors"
    assert out["1"]["inputs"]["mode"] == "balanced"                      # short token kept


# --------------------------------------------------------------------------------
# scrub_chunks

def test_scrub_chunks_reduces_to_skeleton():
    new_chunks, report = palimpsest.scrub_chunks(_png_chunks(_graph()))
    assert [c.type for c in new_chunks] == [b"IHDR", b"tEXt", b"IEND"]
    assert {pngchunks.keyword_of(c) for c in new_chunks if c.type == b"tEXt"} == {"prompt"}
    assert "workflow" in report.dropped and "IDAT" in report.dropped
    assert report.neutralized == 2
    # The kept prompt is the scrubbed one, and still valid JSON.
    graph = json.loads(pngchunks.get_text_field(new_chunks, "prompt"))
    assert graph["6"]["inputs"]["text"] == "scrubbed positive prompt"


def test_scrub_chunks_drops_injected_metadata():
    chunks = _png_chunks(_graph())
    chunks.insert(-1, pngchunks.make_text_chunk("parameters", "a cat\nSteps: 4"))
    chunks = pngchunks.set_xmp(chunks, "<x:xmpmeta/>")
    _, report = palimpsest.scrub_chunks(chunks)
    assert "parameters" in report.dropped and pngchunks.XMP_KEYWORD in report.dropped


def test_no_original_text_survives_in_output_bytes():
    # The privacy invariant: after scrubbing, nothing of the original prose remains anywhere in the
    # file — not the prompts (prompt chunk), not their `workflow` copy, not the note text.
    graph = _graph()
    secrets = [graph["6"]["inputs"]["text"], graph["7"]["inputs"]["text"], _NOTE_TEXT]
    new_chunks, _ = palimpsest.scrub_chunks(_png_chunks(graph))
    blob = pngchunks.serialize(new_chunks)
    for secret in secrets:
        assert secret.encode("utf-8") not in blob
    assert b"scrubbed positive prompt" in blob and b"scrubbed negative prompt" in blob


def test_scrub_chunks_requires_a_prompt_chunk():
    ihdr = pngchunks.Chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
    try:
        palimpsest.scrub_chunks([ihdr, pngchunks.Chunk(b"IEND", b"")])
    except ValueError as e:
        assert "prompt" in str(e)
    else:
        raise AssertionError("expected ValueError for a PNG with no prompt chunk")


# --------------------------------------------------------------------------------
# CLI

def test_scrub_writes_output_without_touching_source(tmp_path, capsys):
    src = tmp_path / "img.png"
    pngchunks.write_file(src, _png_chunks(_graph()))
    before = src.read_bytes()

    assert cli.main(["scrub", str(src)]) == 0
    out = tmp_path / "img.scrubbed.png"
    assert out.exists()
    assert src.read_bytes() == before                          # source untouched
    assert "scrubbed →" in capsys.readouterr().out
    # The scrubbed copy is a valid skeleton.
    fields = pngchunks.text_fields(pngchunks.parse_file(out))
    assert "prompt" in fields and "workflow" not in fields


def test_scrub_output_dir(tmp_path):
    src = tmp_path / "a.png"
    pngchunks.write_file(src, _png_chunks(_graph()))
    out_dir = tmp_path / "fixtures"
    assert cli.main(["scrub", str(src), "-o", str(out_dir)]) == 0
    assert (out_dir / "a.png").exists()


def test_scrub_no_args_prints_usage(capsys, monkeypatch):
    # A bare `chandra scrub` must not spray copies across the cwd; it prints usage instead.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert cli.main(["scrub"]) == 2
    assert "usage:" in capsys.readouterr().err
