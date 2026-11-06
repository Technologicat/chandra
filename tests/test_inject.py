"""Tests for `chandra inject` — writing the `parameters` chunk and the XMP packet.

These run against the committed, anonymized fixtures, so they run everywhere (CI included).
"""

import shutil
from pathlib import Path

import pytest

from chandra import TOOL_TAG, cli, pngchunks

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE = FIXTURES_DIR / "flux2-txt2img.png"

_FOREIGN_PARAMETERS = "a cat\nSteps: 20, Sampler: euler, Version: v1.9.4"
_FOREIGN_XMP = '<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"></x:xmpmeta>'


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


def _stamp_foreign(path, *, parameters=None, xmp=None):
    chunks = pngchunks.parse_file(path)
    if parameters is not None:
        chunks = pngchunks.set_text_field(chunks, "parameters", parameters)
    if xmp is not None:
        chunks = pngchunks.set_xmp(chunks, xmp)
    pngchunks.write_file(path, chunks)


# --------------------------------------------------------------------------------
# Foreign metadata survives without --force

def test_inject_writes_both_layers(clean):
    assert cli.main(["inject", str(clean)]) == 0
    fields = _fields(clean)
    assert f"Version: {TOOL_TAG}" in fields["parameters"]
    assert f'x:xmptk="{TOOL_TAG}' in fields[pngchunks.XMP_KEYWORD]


def test_inject_overwrites_its_own_output(clean):
    assert cli.main(["inject", str(clean)]) == 0
    once = clean.read_bytes()
    assert cli.main(["inject", str(clean)]) == 0
    assert clean.read_bytes() == once                      # re-inject replaces, doesn't stack


def test_inject_leaves_foreign_parameters_without_force(clean, capsys):
    _stamp_foreign(clean, parameters=_FOREIGN_PARAMETERS)
    assert cli.main(["inject", str(clean)]) == 0
    fields = _fields(clean)
    assert fields["parameters"] == _FOREIGN_PARAMETERS     # foreign layer untouched...
    assert f'x:xmptk="{TOOL_TAG}' in fields[pngchunks.XMP_KEYWORD]  # ...the other one still written
    assert "non-chandra `parameters`" in capsys.readouterr().err

    assert cli.main(["inject", "--force", str(clean)]) == 0
    assert f"Version: {TOOL_TAG}" in _fields(clean)["parameters"]   # --force overwrites it


def test_inject_leaves_foreign_xmp_without_force(clean, capsys):
    _stamp_foreign(clean, xmp=_FOREIGN_XMP)
    assert cli.main(["inject", str(clean)]) == 0
    fields = _fields(clean)
    assert fields[pngchunks.XMP_KEYWORD] == _FOREIGN_XMP
    assert f"Version: {TOOL_TAG}" in fields["parameters"]
    assert "non-chandra XMP" in capsys.readouterr().err

    assert cli.main(["inject", "--force", str(clean)]) == 0
    assert f'x:xmptk="{TOOL_TAG}' in _fields(clean)[pngchunks.XMP_KEYWORD]


def test_inject_with_both_layers_foreign_writes_nothing(clean, capsys):
    _stamp_foreign(clean, parameters=_FOREIGN_PARAMETERS, xmp=_FOREIGN_XMP)
    before = clean.read_bytes()
    assert cli.main(["inject", str(clean)]) == 0
    assert clean.read_bytes() == before
    assert "nothing injected" in capsys.readouterr().out
