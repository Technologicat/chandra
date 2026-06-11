"""Tests for the minimal XMP packet builder (`chandra.xmp`)."""

import xml.etree.ElementTree as ET

from chandra import xmp

_NS = {"x": "adobe:ns:meta/",
       "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
       "dc": "http://purl.org/dc/elements/1.1/"}


def _dc_description(packet: str) -> str:
    """Parse the packet (sans xpacket PIs) and return the dc:description x-default text."""
    body = packet[packet.index("<x:xmpmeta"): packet.index("</x:xmpmeta>") + len("</x:xmpmeta>")]
    root = ET.fromstring(body)
    li = root.find(".//dc:description/rdf:Alt/rdf:li", _NS)
    return li.text


def test_packet_is_well_formed_xml_with_xpacket_wrapper():
    packet = xmp.build("hello")
    assert packet.startswith("<?xpacket begin=")
    assert packet.rstrip().endswith('<?xpacket end="w"?>')
    # The body between the PIs must parse as XML.
    body = packet[packet.index("<x:xmpmeta"): packet.index("</x:xmpmeta>") + len("</x:xmpmeta>")]
    ET.fromstring(body)  # raises on malformed XML


def test_description_round_trips():
    text = "a catgirl, masterpiece\n\nNegative: blurry"
    assert _dc_description(xmp.build(text)) == text  # newlines preserved in element content


def test_xml_special_chars_are_escaped_and_recovered():
    text = 'prompt with <angle> & "ampersand" tokens'
    packet = xmp.build(text)
    assert "<angle>" not in packet  # the literal '<' must be escaped, not left as markup
    assert "&lt;angle&gt;" in packet and "&amp;" in packet
    assert _dc_description(packet) == text  # and it decodes back to the original


def test_uses_x_default_language_alternative():
    assert 'xml:lang="x-default"' in xmp.build("x")


def test_packet_carries_chandra_toolkit_stamp():
    # The `x:xmptk` stamp is what lets `chandra eject` recognize and remove only its own XMP.
    from chandra import TOOL_TAG
    assert f'x:xmptk="{TOOL_TAG}' in xmp.build("x")
