"""Dependency-free, byte-level PNG chunk surgery.

Both tools sit on this. `rosetta` reads the ComfyUI `prompt`/`workflow` text chunks and the image
size, and splices in a `parameters` chunk losslessly; `concordance` reads the embedded prompt text.
We deliberately avoid Pillow: a PNG is a trivial container and re-encoding through an imaging library
would recompress `IDAT` and rewrite/drop text chunks. Operating on the raw chunk stream lets us
insert one chunk and leave every existing byte (image data, `prompt`, `workflow`) untouched.

PNG layout (see the spec, https://www.w3.org/TR/png/):

    signature (8 bytes: 89 50 4E 47 0D 0A 1A 0A)
    then a sequence of chunks, each:
        length  (4 bytes, big-endian, length of `data` only)
        type    (4 bytes, ASCII, e.g. b"IHDR", b"tEXt")
        data    (`length` bytes)
        crc     (4 bytes, big-endian CRC-32 of type+data)

Text chunks carry a NUL-terminated Latin-1 *keyword* as their first field, identically across the
three forms, so keyword extraction is uniform:

    tEXt:  keyword \x00 text(Latin-1)
    zTXt:  keyword \x00 method(1) zlib(text)                         # text is Latin-1
    iTXt:  keyword \x00 cflag(1) method(1) lang \x00 transkw \x00 text(UTF-8, zlib if cflag)

Image size lives in `IHDR`: width and height are its first two big-endian uint32s.
"""

import zlib
from typing import NamedTuple, Optional

__all__ = [
    "PNG_SIGNATURE",
    "TEXT_CHUNK_TYPES",
    "Chunk",
    "read_chunks",
    "parse_file",
    "serialize",
    "write_file",
    "image_size",
    "keyword_of",
    "decode_text_chunk",
    "text_fields",
    "get_text_field",
    "make_text_chunk",
    "set_text_field",
    "remove_text_fields",
]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# The three textual chunk types, treated uniformly for keyword extraction and replacement.
TEXT_CHUNK_TYPES = (b"tEXt", b"zTXt", b"iTXt")


class Chunk(NamedTuple):
    """One PNG chunk. The CRC is not stored; it is (re)computed from type+data on serialization."""
    type: bytes   # 4-byte chunk type, e.g. b"tEXt"
    data: bytes   # the chunk's data payload (CRC excluded)


# --------------------------------------------------------------------------------
# Reading

def read_chunks(blob: bytes) -> list[Chunk]:
    """Parse a PNG byte string into its chunk sequence (up to and including `IEND`).

    CRCs are not verified — many real-world generator outputs carry quirks, and we want to read them
    anyway. `serialize` recomputes correct CRCs, so a read/write round-trip is self-healing.
    """
    if blob[:8] != PNG_SIGNATURE:
        raise ValueError("not a PNG (bad signature)")
    chunks = []
    pos, n = 8, len(blob)
    while pos < n:
        if pos + 8 > n:
            raise ValueError("truncated PNG: incomplete chunk header")
        length = int.from_bytes(blob[pos:pos + 4], "big")
        ctype = blob[pos + 4:pos + 8]
        pos += 8
        if pos + length + 4 > n:
            raise ValueError(f"truncated PNG: chunk {ctype!r} claims {length} bytes, past end of file")
        data = blob[pos:pos + length]
        pos += length + 4  # skip data and the 4-byte CRC
        chunks.append(Chunk(ctype, data))
        if ctype == b"IEND":
            break  # the image ends here; ignore any trailing bytes
    return chunks


def parse_file(path) -> list[Chunk]:
    """Read a PNG file and return its chunk sequence."""
    with open(path, "rb") as f:
        return read_chunks(f.read())


# --------------------------------------------------------------------------------
# Writing

def _chunk_crc(chunk: Chunk) -> int:
    return zlib.crc32(chunk.type + chunk.data) & 0xFFFFFFFF


def serialize(chunks) -> bytes:
    """Serialize a chunk sequence back to PNG bytes, recomputing each chunk's CRC.

    For a valid PNG with correct CRCs, `serialize(read_chunks(blob)) == blob` byte-for-byte (the
    losslessness the injection relies on).
    """
    out = bytearray(PNG_SIGNATURE)
    for ch in chunks:
        out += len(ch.data).to_bytes(4, "big")
        out += ch.type
        out += ch.data
        out += _chunk_crc(ch).to_bytes(4, "big")
    return bytes(out)


def write_file(path, chunks) -> None:
    """Serialize `chunks` and write them to `path`."""
    with open(path, "wb") as f:
        f.write(serialize(chunks))


# --------------------------------------------------------------------------------
# IHDR / image size

def image_size(chunks) -> tuple[int, int]:
    """Return (width, height) read from the `IHDR` chunk."""
    for ch in chunks:
        if ch.type == b"IHDR":
            if len(ch.data) < 8:
                raise ValueError("malformed IHDR (shorter than 8 bytes)")
            width = int.from_bytes(ch.data[0:4], "big")
            height = int.from_bytes(ch.data[4:8], "big")
            return (width, height)
    raise ValueError("no IHDR chunk")


# --------------------------------------------------------------------------------
# Text chunks

def _decode_latin1_or_utf8(raw: bytes) -> str:
    """Decode bytes that are *nominally* Latin-1 (tEXt/zTXt) but in the wild are often UTF-8.

    Try UTF-8 first (covers ComfyUI's ASCII/JSON and tools that cheat by storing UTF-8 in tEXt);
    fall back to Latin-1, which maps all 256 byte values and so never raises.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def keyword_of(chunk: Chunk) -> Optional[str]:
    """The keyword of a text chunk (the leading NUL-terminated Latin-1 field), or None if not text."""
    if chunk.type not in TEXT_CHUNK_TYPES:
        return None
    return chunk.data.split(b"\x00", 1)[0].decode("latin-1")


def decode_text_chunk(chunk: Chunk) -> Optional[tuple[str, str]]:
    """Decode a text chunk to (keyword, text), handling tEXt/zTXt/iTXt. None if not a text chunk."""
    if chunk.type not in TEXT_CHUNK_TYPES:
        return None
    keyword_b, _, rest = chunk.data.partition(b"\x00")
    keyword = keyword_b.decode("latin-1")

    if chunk.type == b"tEXt":
        return (keyword, _decode_latin1_or_utf8(rest))

    if chunk.type == b"zTXt":
        # rest = method(1) + zlib(text); method 0 is the only defined value (zlib/deflate).
        compressed = rest[1:]
        return (keyword, _decode_latin1_or_utf8(zlib.decompress(compressed)))

    # iTXt: cflag(1) method(1) lang \x00 transkw \x00 text(UTF-8, zlib-compressed iff cflag==1)
    cflag = rest[0]
    text_section = rest[2:]                              # drop cflag and method
    _lang, _, text_section = text_section.partition(b"\x00")
    _transkw, _, text_bytes = text_section.partition(b"\x00")
    if cflag == 1:
        text_bytes = zlib.decompress(text_bytes)
    return (keyword, text_bytes.decode("utf-8"))


def text_fields(chunks) -> dict[str, str]:
    """All text chunks as a {keyword: text} dict. On duplicate keywords, the later chunk wins."""
    fields = {}
    for ch in chunks:
        decoded = decode_text_chunk(ch)
        if decoded is not None:
            fields[decoded[0]] = decoded[1]
    return fields


def get_text_field(chunks, keyword: str) -> Optional[str]:
    """The text of the (last) text chunk with this keyword, or None if absent."""
    return text_fields(chunks).get(keyword)


def make_text_chunk(keyword: str, text: str) -> Chunk:
    """Build a text chunk for (keyword, text), choosing the encoding by content.

    `tEXt` when the text is Latin-1-encodable (the common case, and greppable without
    decompression); otherwise `iTXt` (UTF-8, uncompressed) so non-Latin-1 content survives. This
    mirrors what Pillow and SD-Forge do, and both CivitAI and SD Prompt Reader read either form.
    """
    kw = keyword.encode("latin-1")  # PNG keywords are Latin-1
    if not 1 <= len(kw) <= 79:
        raise ValueError(f"PNG keyword must be 1-79 bytes, got {len(kw)}")
    try:
        return Chunk(b"tEXt", kw + b"\x00" + text.encode("latin-1"))
    except UnicodeEncodeError:
        # iTXt, uncompressed (cflag=0, method=0), empty language tag and translated keyword.
        return Chunk(b"iTXt", kw + b"\x00" + b"\x00\x00" + b"\x00" + b"\x00" + text.encode("utf-8"))


def remove_text_fields(chunks, keyword: str) -> list[Chunk]:
    """Return `chunks` with every text chunk (tEXt/zTXt/iTXt) of this keyword removed."""
    return [c for c in chunks if keyword_of(c) != keyword]


def set_text_field(chunks, keyword: str, text: str) -> list[Chunk]:
    """Return `chunks` with exactly one text chunk for `keyword`, holding `text`.

    Any pre-existing text chunk of this keyword (in *any* of the three forms) is removed first, so
    re-running is idempotent — we never stack a second `parameters`. The new chunk is inserted
    immediately before `IEND` (a valid position for ancillary text chunks).
    """
    result = remove_text_fields(chunks, keyword)
    new_chunk = make_text_chunk(keyword, text)
    for i, c in enumerate(result):
        if c.type == b"IEND":
            result.insert(i, new_chunk)
            return result
    # No IEND (malformed input): append rather than lose the field.
    result.append(new_chunk)
    return result
