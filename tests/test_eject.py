"""Tests for `chandra eject` — the inverse of `inject`.

`eject` removes chandra's injected metadata layer (the A1111 `parameters` chunk and the XMP
description), leaving the original ComfyUI `prompt`/`workflow` chunks byte-intact. By default it
removes only metadata chandra wrote (stamped `chandra-rosetta`); `--force` removes any `parameters`/
XMP regardless of origin, and `--no-xmp` removes only the `parameters` chunk.

These run against the committed, anonymized fixtures, so they run everywhere (CI included).
"""

import shutil
from pathlib import Path

import pytest

from chandra import cli, pngchunks

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE = FIXTURES_DIR / "flux2-txt2img.png"


def _fields(path):
    return pngchunks.text_fields(pngchunks.parse_file(path))


@pytest.fixture
def clean(tmp_path):
    """A fixture PNG copied to tmp, not yet injected."""
    if not _FIXTURE.exists():
        pytest.skip(f"{_FIXTURE.name} fixture not present")
    dst = tmp_path / "img.png"
    shutil.copy(_FIXTURE, dst)
    return dst


@pytest.fixture
def injected(clean):
    """A fixture PNG copied to tmp and injected — ready to be ejected."""
    assert cli.main(["inject", str(clean)]) == 0
    return clean


# --------------------------------------------------------------------------------
# The core invariant: inject then eject restores the file exactly

def test_eject_restores_pre_inject_bytes(clean):
    # inject only *adds* the parameters + XMP chunks; eject removes exactly those, so the round trip
    # is byte-for-byte identity (chandra-written PNGs already carry correct CRCs, so serialize is
    # self-healing and the untouched chunks re-serialize unchanged).
    original = clean.read_bytes()
    assert cli.main(["inject", str(clean)]) == 0
    assert clean.read_bytes() != original                  # inject changed something
    assert cli.main(["eject", str(clean)]) == 0
    assert clean.read_bytes() == original                  # eject restored it exactly


def test_eject_removes_both_layers_and_preserves_comfy(injected):
    before = _fields(injected)
    assert "parameters" in before and pngchunks.XMP_KEYWORD in before  # inject wrote both layers

    assert cli.main(["eject", str(injected)]) == 0

    after = _fields(injected)
    assert "parameters" not in after                       # A1111 layer gone
    assert pngchunks.XMP_KEYWORD not in after              # XMP description gone
    assert after["prompt"] == before["prompt"]             # ComfyUI graph untouched
    assert after.get("workflow") == before.get("workflow")


# --------------------------------------------------------------------------------
# Flags: --no-xmp keeps the XMP, nothing-to-eject is a no-op

def test_eject_no_xmp_keeps_the_description(injected):
    assert cli.main(["eject", "--no-xmp", str(injected)]) == 0
    after = _fields(injected)
    assert "parameters" not in after                       # the SD-tool layer is removed
    assert pngchunks.XMP_KEYWORD in after                  # but the XMP description is left in place


def test_eject_nothing_to_do_on_clean_file(clean, capsys):
    before = clean.read_bytes()
    assert cli.main(["eject", str(clean)]) == 0
    assert clean.read_bytes() == before                    # an un-injected file is left untouched
    assert "nothing to eject" in capsys.readouterr().out


# --------------------------------------------------------------------------------
# "Ours only" safety: foreign metadata survives without --force

def test_eject_leaves_foreign_parameters_without_force(clean):
    # A `parameters` chunk chandra didn't write (no `chandra-rosetta` stamp) is left alone by default.
    foreign = pngchunks.set_text_field(
        pngchunks.parse_file(clean), "parameters",
        "a cat\nSteps: 20, Sampler: euler, Version: v1.9.4")
    pngchunks.write_file(clean, foreign)

    assert cli.main(["eject", str(clean)]) == 0
    assert "parameters" in _fields(clean)                  # foreign params untouched by default

    assert cli.main(["eject", "--force", str(clean)]) == 0
    assert "parameters" not in _fields(clean)              # --force removes it regardless


def test_eject_leaves_foreign_xmp_without_force(clean):
    # A third-party XMP packet (no chandra `x:xmptk` stamp) is left alone unless --force is given.
    foreign_packet = '<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"></x:xmpmeta>'
    pngchunks.write_file(clean, pngchunks.set_xmp(pngchunks.parse_file(clean), foreign_packet))

    assert cli.main(["eject", str(clean)]) == 0
    assert pngchunks.XMP_KEYWORD in _fields(clean)         # foreign XMP untouched by default

    assert cli.main(["eject", "--force", str(clean)]) == 0
    assert pngchunks.XMP_KEYWORD not in _fields(clean)     # --force removes it
