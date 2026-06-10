"""Minimal XMP packet construction, for embedding human-readable metadata in images.

`inject` writes the synthesized A1111 `parameters` chunk for the SD tools; it *also* embeds an XMP
`dc:description` so that general image viewers — Pix/gThumb, and anything else that reads metadata
through exiv2 — show the recipe without any SD software installed. We build the packet by hand (a
tiny, fixed RDF document) rather than pull in a metadata library: an XMP packet is just UTF-8 XML,
and chandra already does its own lossless PNG chunk surgery (see `pngchunks`).

The packet is carried in a PNG `iTXt` chunk keyed `XML:com.adobe.xmp` — the standard place for XMP in
a PNG; `pngchunks.set_xmp` handles the chunk side. Viewers resolve their "Description" caption from a
tagset headed by `Iptc.Application2.Caption`, then `Xmp.dc.description`; with no IPTC block present,
our `dc:description` is the value they surface.
"""

from xml.sax.saxutils import escape

__all__ = ["build"]

# The XMP packet wrapper (XMP spec, part 1). The U+FEFF in the begin PI is the spec's byte-order
# marker for the packet; end="w" marks the packet writable (in-place editable by other tools).
_XPACKET_BEGIN = '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
_XPACKET_END = '<?xpacket end="w"?>'


def build(description: str) -> str:
    """Return an XMP packet (a UTF-8 XML string) carrying `description` as `dc:description`.

    `dc:description` is a language alternative, so the text is wrapped in an `rdf:Alt` / `rdf:li`
    with `xml:lang="x-default"` — the shape exiv2 and other readers expect for a localizable text
    property. The text goes in element content, so escaping `& < >` is sufficient.
    """
    text = escape(description)
    return (
        f"{_XPACKET_BEGIN}\n"
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "   <dc:description>\n"
        "    <rdf:Alt>\n"
        f'     <rdf:li xml:lang="x-default">{text}</rdf:li>\n'
        "    </rdf:Alt>\n"
        "   </dc:description>\n"
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        f"{_XPACKET_END}"
    )
