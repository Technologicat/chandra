#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Search SD metadata for given search term, in PNG files in the current directory (recursively).

Find images that match "starfleet captain" in either positive or negative prompt:
    python metadata-matching-dirs.py starfleet captain

Search in positive prompt only:
    python metadata-matching-dirs.py -p starfleet captain

Search in negative prompt only:
    python metadata-matching-dirs.py -n starfleet captain
"""

import argparse
import chardet
import os
import re
import sys
from typing import Dict, List, Tuple

import png  # pip install pypng
import zlib  # pip install zlib

from unpythonic import dyn, make_dynvar  # pip install unpythonic

make_dynvar(current_path="")

# --------------------------------------------------------------------------------
# PNG text chunk scanners
#
# Upgraded to Python 3 from this, and tEXT chunk added:
#   https://stackoverflow.com/questions/37068414/how-to-modify-a-compressed-itxt-record-of-an-existing-file-in-python

def cutASCIIZ(bytestring: bytes) -> Tuple[bytes, bytes]:
    end = bytestring.find(b"\x00")
    if end >= 0:
        return (bytestring[:end], bytestring[end + 1:])
    return (b"", bytestring)

def decode_maybe_utf8(bytestring: bytes) -> str:
    try:
        return bytestring.decode("utf-8")
    except UnicodeDecodeError:
        result = chardet.detect(bytestring)  # {"encoding": ..., "confidence": ...}
        print(f"  WARNING: while reading file '{dyn.fullpath}': non-utf8 text encoding, decoding as {result['encoding']} (confidence {result['confidence']})")
        return bytestring.decode(result["encoding"])

class Chunk_tEXt:
    def __init__(self, chunk_data):
        tmp = cutASCIIZ(chunk_data)
        self.keyword = decode_maybe_utf8(tmp[0])
        self.text = decode_maybe_utf8(tmp[1])

    def pack(self) -> bytes:
        result = self.keyword.encode("utf-8") + b"\x00"
        result += self.text.encode("utf-8")
        return result

    def show(self) -> None:
        print("tEXt chunk contents:")
        print(f"  keyword: '{self.keyword}'")
        print(f"  text: '{self.text}'")

class Chunk_iTXt:
    def __init__(self, chunk_data):
        tmp = cutASCIIZ(chunk_data)
        self.keyword = decode_maybe_utf8(tmp[0])
        if len(tmp[1]):
            self.compressed = int(tmp[1][0])
        else:
            self.compressed = 0
        if len(tmp[1]) > 1:
            self.compressionMethod = int(tmp[1][1])
        else:
            self.compressionMethod = 0
        tmp = tmp[1][2:]
        tmp = cutASCIIZ(tmp)
        self.languageTag = decode_maybe_utf8(tmp[0])
        tmp = tmp[1]
        tmp = cutASCIIZ(tmp)
        self.languageTagTrans = decode_maybe_utf8(tmp[0])
        if self.compressed:
            if self.compressionMethod != 0:
                raise TypeError(f"while reading file '{dyn.fullpath}': Unknown compression method {self.compressionMethod} (valid: 0 = zlib)")
            self.text = decode_maybe_utf8(zlib.decompress(tmp[1]))
        else:
            self.text = decode_maybe_utf8(tmp[1])

    def pack(self) -> bytes:
        result = self.keyword.encode("utf-8") + b"\x00"
        result += bytes([self.compressed])
        result += bytes([self.compressionMethod])
        result += self.languageTag.encode("utf-8") + b"\x00"
        result += self.languageTagTrans.encode("utf-8") + b"\x00"
        if self.compressed:
            if self.compressionMethod != 0:
                raise TypeError(f"While packing, unknown compression method {self.compressionMethod} (valid: 0 = zlib)")
            result += zlib.compress(self.text.encode("utf-8"))
        else:
            result += self.text.encode("utf-8")
        return result

    def show(self) -> None:
        print("iTXt chunk contents:")
        print(f"  keyword: '{self.keyword}'")
        print(f"  compressed: {self.compressed}")
        print(f"  compression method: {self.compressionMethod}")
        print(f"  language: '{self.languageTag}'")
        print(f"  tag translation: '{self.languageTagTrans}'")
        print(f"  text: '{self.text}'")

def get_text_content(png_filename: str) -> List[str]:
    sourceImage = png.Reader(png_filename)
    txtlist = []
    for chunk in sourceImage.chunks():
        if chunk[0] == b"tEXt":
            chunk_data = Chunk_tEXt(chunk[1])
            txtlist.append(chunk_data.text)
    return txtlist

def get_itxt_content(png_filename: str) -> List[str]:
    sourceImage = png.Reader(png_filename)
    txtlist = []
    for chunk in sourceImage.chunks():
        if chunk[0] == b"iTXt":
            chunk_data = Chunk_iTXt(chunk[1])
            txtlist.append(chunk_data.text)
    return txtlist

# --------------------------------------------------------------------------------

def listpng(path: str) -> List[str]:
    return list(sorted(filename for filename in os.listdir(path) if filename.endswith(".png")))

def report(paths: List[str], opts: Dict) -> None:
    search_str = ' '.join(opts.searchterms)
    if opts.ignorecase:
        pattern = re.compile(f"{search_str}", re.IGNORECASE)
    else:
        pattern = re.compile(f"{search_str}")

    neg_pattern = re.compile("Negative prompt:")

    if opts.positive:
        what = "positive prompt only"
    elif opts.negative:
        what = "negative prompt only"
    else:
        what = "both positive and negative prompt"

    print(f"Searching for \"{search_str}\" in filenames and SD metadata ({what}), printing matching files.", file=sys.stderr)  # filenames are searched because `pngcheck -ct` prints them too
    matched_dirs = set()
    for path in paths:
        print(f"Searching in \"{path}\"...", file=sys.stderr)
        results = []
        filenames = listpng(path)
        for filename in filenames:
            fullpath = os.path.join(path, filename)
            with dyn.let(fullpath=fullpath):  # for error messages
                # positive or negative prompt only? (approximate; we just cut where the negative starts and take one half)
                def get_relevant_part(text):
                    if opts.positive or opts.negative:
                        neg_start_match = neg_pattern.search(text)
                        if neg_start_match is not None:
                            neg_start_pos = neg_start_match.start()
                            if opts.positive:
                                text = text[:neg_start_pos]  # positive prompt, up to start of negative prompt
                            else:
                                text = text[neg_start_pos:]  # from start of negative prompt
                        else:
                            if opts.negative:
                                print(f"    WARNING: while reading file '{dyn.fullpath}': -n specified, but did not find start of negative prompt. Skipping file.", file=sys.stderr)
                                return None
                    return text

                matched = False

                # Scan tEXt chunks
                texts = get_text_content(fullpath)
                for text in texts:
                    text = get_relevant_part(text)
                    matches = re.findall(pattern, text)
                    if len(matches):
                        matched = True
                        break

                # Scan iTXt (international text) chunks too, newer versions of Forge use these (sometimes, but not always)
                if not matched:
                    itxts = get_itxt_content(fullpath)
                    for text in itxts:
                        text = get_relevant_part(text)
                        matches = re.findall(pattern, text)
                        if len(matches):
                            matched = True
                            break

                if matched:
                    results.append(fullpath)
                    matched_dirs.add(path)
        for fullpath in sorted(results):
            print(f"{fullpath}")

    print(file=sys.stderr)
    print("Summary of directories containing matches, if any:", file=sys.stderr)
    for directory in sorted(matched_dirs):
        print(f"    {directory}", file=sys.stderr)

def main() -> None:
    parser = argparse.ArgumentParser(description="""Search SD metadata for given search term, in PNG files in the current directory (recursively).""",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(dest="searchterms", nargs="+", default=None, type=str, metavar="word", help="word(s) to search for (exact string, may contain spaces)")
    parser.add_argument("-i", "--ignore-case", dest="ignorecase", action="store_true", default=False, help="case-insensitive search")
    parser.add_argument("-p", "--positive", dest="positive", action="store_true", default=False, help="match in positive prompt only")
    parser.add_argument("-n", "--negative", dest="negative", action="store_true", default=False, help="match in negative prompt only")
    opts = parser.parse_args()

    blacklist = []
    paths = []
    for root, dirs, files in os.walk("."):
        paths.append(root)
        for x in blacklist:
            if x in dirs:
                dirs.remove(x)
    report(sorted(paths), opts)

if __name__ == '__main__':
    main()
