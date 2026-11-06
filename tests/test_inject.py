"""Tests for `chandra inject` — writing the `parameters` chunk and the XMP packet.

These run against the committed, anonymized fixtures, so they run everywhere (CI included).
"""

import shutil
import subprocess
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


# --------------------------------------------------------------------------------
# IPTC Digital Source Type in the XMP packet

_DST_URI = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def _xmp(path):
    return _fields(path).get(pngchunks.XMP_KEYWORD)


def test_inject_marks_ai_by_default(clean):
    assert cli.main(["inject", str(clean)]) == 0
    packet = _xmp(clean)
    assert f">{_DST_URI}trainedAlgorithmicMedia<" in packet
    assert ("<Iptc4xmpExt:AIPromptInformation>Positive:\nscrubbed positive prompt\n\n"
            "Negative:\nscrubbed negative prompt</Iptc4xmpExt:AIPromptInformation>") in packet
    assert "<Iptc4xmpExt:AISystemUsed>scrubbed-checkpoint</Iptc4xmpExt:AISystemUsed>" in packet
    assert "AIPromptWriterName" not in packet and "AISystemVersionUsed" not in packet  # never in a graph


def test_inject_no_mark_ai_leaves_the_properties_out(clean):
    assert cli.main(["inject", "--no-mark-ai", str(clean)]) == 0
    packet = _xmp(clean)
    assert "dc:description" in packet and "Iptc4xmpExt" not in packet


def test_inject_no_xmp_skips_the_mark_too(clean):
    assert cli.main(["inject", "--no-xmp", str(clean)]) == 0
    assert _xmp(clean) is None


def test_inject_abstains_on_non_generation(tmp_path):
    png = tmp_path / "tools.png"
    shutil.copy(FIXTURES_DIR / "tools-rembg.png", png)
    assert cli.main(["inject", str(png)]) == 0
    packet = _xmp(png)
    assert "dc:description" in packet and "Iptc4xmpExt" not in packet     # no source type, prompt or model


@pytest.mark.parametrize("flags", [[], ["--no-mark-ai"]], ids=["marked", "unmarked"])
def test_inject_eject_round_trip_is_byte_identical(clean, flags):
    original = clean.read_bytes()
    assert cli.main(["inject", *flags, str(clean)]) == 0
    assert clean.read_bytes() != original
    assert cli.main(["eject", str(clean)]) == 0
    assert clean.read_bytes() == original


def test_foreign_digital_source_type_survives_without_force(clean):
    # A DigitalSourceType another tool wrote lives in that tool's XMP packet, which inject leaves alone.
    foreign = ('<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
               'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
               'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"><Iptc4xmpExt:DigitalSourceType>'
               f'{_DST_URI}digitalCapture</Iptc4xmpExt:DigitalSourceType></rdf:Description></rdf:RDF>'
               '</x:xmpmeta><?xpacket end="w"?>')
    _stamp_foreign(clean, xmp=foreign)
    assert cli.main(["inject", str(clean)]) == 0
    assert _xmp(clean) == foreign

    assert cli.main(["inject", "--force", str(clean)]) == 0
    packet = _xmp(clean)
    assert "digitalCapture" not in packet and f"{_DST_URI}trainedAlgorithmicMedia" in packet


def test_show_reports_the_source_type(capsys):
    assert cli.main(["show", str(FIXTURES_DIR / "flux2-img2img.png")]) == 0
    assert "DigitalSourceType: compositeWithTrainedAlgorithmicMedia (" in capsys.readouterr().out
    assert cli.main(["show", str(FIXTURES_DIR / "tools-rembg.png")]) == 0
    out = capsys.readouterr().out
    assert "DigitalSourceType: abstained (" in out
    assert "AISystemUsed: abstained (not a generation)" in out


def test_show_reports_the_ai_system(capsys):
    assert cli.main(["show", str(FIXTURES_DIR / "flux2-img2img.png")]) == 0
    assert "AISystemUsed: scrubbed-checkpoint\n" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")
def test_exiftool_reads_the_iptc_properties(clean):
    assert cli.main(["inject", str(clean)]) == 0

    def read(tag):
        return subprocess.run(["exiftool", "-s3", f"-XMP-iptcExt:{tag}", str(clean)],
                              capture_output=True, text=True, check=True).stdout.strip()

    assert read("DigitalSourceType") == f"{_DST_URI}trainedAlgorithmicMedia"
    assert read("AISystemUsed") == "scrubbed-checkpoint"
    assert read("AIPromptInformation").startswith("Positive:")
