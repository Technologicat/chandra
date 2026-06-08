"""Tests for `igmt search` (the concordance engine)."""

from pathlib import Path

import pytest

from igmt import cli, pngchunks
from igmt.concordance import _contains, _matches, _split_a1111, extract_prompts

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "00_stuff"


def _make_png(path: Path, parameters: str) -> Path:
    """A minimal valid-enough PNG carrying a `parameters` text chunk (no real IDAT needed for reads)."""
    ihdr = pngchunks.Chunk(b"IHDR", (8).to_bytes(4, "big") + (8).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
    chunks = [ihdr, pngchunks.make_text_chunk("parameters", parameters), pngchunks.Chunk(b"IEND", b"")]
    pngchunks.write_file(path, chunks)
    return path


# --------------------------------------------------------------------------------
# Unit: A1111 split, smart-case, matching

def test_split_a1111():
    text = "a starfleet captain\nNegative prompt: blurry, bad\nSteps: 4, Sampler: euler"
    assert _split_a1111(text) == ("a starfleet captain", "blurry, bad")


def test_split_a1111_no_negative():
    assert _split_a1111("just a cat\nSteps: 4, Seed: 1") == ("just a cat", "")


def test_smart_case_contains():
    assert _contains("cat", "a Cat sat", ignore_case=False)      # lowercase frag → case-insensitive
    assert not _contains("Cat", "a cat sat", ignore_case=False)  # uppercase present → case-sensitive
    assert _contains("Cat", "a Cat sat", ignore_case=False)
    assert _contains("Cat", "a cat sat", ignore_case=True)       # -i overrides


def test_fragment_match_is_anded_order_independent_substring():
    # "cat photo" matches "photocatalytic" — both fragments occur as substrings, order-free.
    assert _matches("photocatalytic art", ["cat", "photo"], "cat photo", exact=False, ignore_case=False)
    assert _matches("a photo of a cat", ["cat", "photo"], "cat photo", exact=False, ignore_case=False)
    assert not _matches("a photo only", ["cat", "photo"], "cat photo", exact=False, ignore_case=False)


def test_exact_match():
    assert _matches("a cat photo here", [], "cat photo", exact=True, ignore_case=False)
    assert not _matches("a photo of a cat", [], "cat photo", exact=True, ignore_case=False)


# --------------------------------------------------------------------------------
# extract_prompts

def test_extract_prompts_from_parameters(tmp_path):
    png = _make_png(tmp_path / "a.png", "a wizard\nNegative prompt: ugly\nSteps: 4, Seed: 1")
    assert extract_prompts(png) == ("a wizard", "ugly")


def test_extract_prompts_from_comfy_graph():
    p = SAMPLES_DIR / "flux2-txt2img.png"
    if not p.exists():
        pytest.skip("sample not present")
    positive, _negative = extract_prompts(p)
    assert "catgirl" in positive.lower()


# --------------------------------------------------------------------------------
# CLI

@pytest.fixture
def corpus(tmp_path):
    _make_png(tmp_path / "captain.png", "a starfleet Captain on the bridge\nNegative prompt: blurry\nSteps: 4")
    _make_png(tmp_path / "wizard.png", "an old wizard\nNegative prompt: lowres, blurry\nSteps: 4")
    (tmp_path / "sub").mkdir()
    _make_png(tmp_path / "sub" / "cat.png", "a photo of a catgirl\nNegative prompt: monochrome\nSteps: 4")
    return tmp_path


def test_search_finds_matches(corpus, capsys):
    rc = cli.main(["search", "wizard", "-d", str(corpus)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wizard.png" in out
    assert "captain.png" not in out


def test_search_recurses_subdirs(corpus, capsys):
    rc = cli.main(["search", "catgirl", "-d", str(corpus)])
    assert rc == 0
    assert "sub/cat.png" in capsys.readouterr().out


def test_search_fragments_anded(corpus, capsys):
    # "photo cat" matches the catgirl image (both substrings), order-independent.
    assert cli.main(["search", "photo", "cat", "-d", str(corpus)]) == 0
    assert "cat.png" in capsys.readouterr().out


def test_search_smart_case(corpus, capsys):
    # "captain" (lowercase) matches "Captain"; "Captain" (uppercase) is case-sensitive.
    assert cli.main(["search", "captain", "-d", str(corpus)]) == 0
    assert "captain.png" in capsys.readouterr().out
    assert cli.main(["search", "captain", "-d", str(corpus)]) == 0  # control
    # An uppercase fragment not present verbatim should miss:
    assert cli.main(["search", "CAPTAIN", "-d", str(corpus)]) == 1


def test_search_negative_scope(corpus, capsys):
    # "blurry" is only in negatives → -n finds it, -p does not.
    assert cli.main(["search", "blurry", "-n", "-d", str(corpus)]) == 0
    assert cli.main(["search", "blurry", "-p", "-d", str(corpus)]) == 1


def test_search_exact_vs_fragment(corpus, capsys):
    assert cli.main(["search", "--exact", "starfleet Captain", "-d", str(corpus)]) == 0  # contiguous
    capsys.readouterr()
    assert cli.main(["search", "--exact", "Captain starfleet", "-d", str(corpus)]) == 1  # wrong order


def test_search_no_terms_is_usage_error():
    assert cli.main(["search"]) == 2


def test_search_no_match_returns_one(corpus):
    assert cli.main(["search", "dragon", "-d", str(corpus)]) == 1


def test_search_dirs_only(corpus, capsys):
    rc = cli.main(["search", "blurry", "-n", "--dirs-only", "-d", str(corpus)])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    # blurry is in captain.png and wizard.png (both in corpus root) -> one deduped directory
    assert out == [str(corpus)]


def test_search_reads_paths_from_stdin(corpus, capsys, monkeypatch):
    import io
    # Feed an explicit candidate list on stdin (the chaining mechanism); filter it.
    candidates = "\n".join(str(p) for p in sorted(corpus.rglob("*.png")))
    monkeypatch.setattr("sys.stdin", io.StringIO(candidates))
    rc = cli.main(["search", "--stdin", "wizard"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wizard.png" in out and "captain.png" not in out


def test_search_pipeline_intersection(corpus, capsys, monkeypatch):
    import io
    # Stage 1: everything with "blurry" in the negative; Stage 2: narrow to those mentioning "wizard".
    all_pngs = sorted(corpus.rglob("*.png"))
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(str(p) for p in all_pngs)))
    assert cli.main(["search", "--stdin", "-n", "blurry"]) == 0
    piped = capsys.readouterr().out  # captain.png + wizard.png

    monkeypatch.setattr("sys.stdin", io.StringIO(piped))
    assert cli.main(["search", "--stdin", "wizard"]) == 0
    final = capsys.readouterr().out
    assert "wizard.png" in final and "captain.png" not in final
