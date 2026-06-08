"""concordance — the engine behind `igmt search`.

A concordance of a corpus of pictures: find which generated images match given search fragments in
their embedded SD prompts. See `briefs/concordance-search.md`.

The module keeps the name `concordance` (an indexed listing of where words occur — see the README);
the CLI surface is the descriptive verb `igmt search`.

Per image we extract `(positive, negative)`: from an A1111 `parameters` chunk if present (Forge
images, or ones `igmt inject` wrote), otherwise by analyzing the ComfyUI `prompt` graph (so raw,
un-injected ComfyUI images are searchable too), otherwise the concatenated raw text as a fallback.
"""

import json
import sys
from pathlib import Path

from . import analyze as _analyze
from . import pngchunks

__all__ = ["add_subparser", "run", "extract_prompts"]


def add_subparser(subparsers):
    """Register the `search` subcommand on the dispatcher's subparsers action."""
    p = subparsers.add_parser(
        "search",
        help="search prompts across a directory of images",
        description="Search the prompts embedded across a directory tree of generated images.")
    p.add_argument("terms", nargs="*", metavar="WORD",
                   help="search fragment(s): ANDed, order-independent, substring match (default mode)")
    d = p.add_argument("-d", "--dir", action="append", metavar="DIR",
                       help="root directory to search (repeatable; default: current directory)")
    try:
        from argcomplete.completers import DirectoriesCompleter
        d.completer = DirectoriesCompleter()
    except ImportError:
        pass
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("-p", "--positive", action="store_true", help="match in the positive prompt only")
    scope.add_argument("-n", "--negative", action="store_true", help="match in the negative prompt only")
    p.add_argument("--exact", action="store_true",
                   help="match the whole query as one contiguous string (instead of fragments)")
    p.add_argument("-i", "--ignore-case", action="store_true",
                   help="force case-insensitive matching (overrides per-fragment smart-case)")
    p.set_defaults(func=run)
    return p


# --------------------------------------------------------------------------------
# Prompt extraction

def _split_a1111(text):
    """Split an A1111 `parameters` string into (positive, negative) — just the prompt halves."""
    neg_marker = "\nNegative prompt:"
    steps_index = text.find("\nSteps:")
    end = steps_index if steps_index != -1 else len(text)
    if neg_marker in text:
        ni = text.find(neg_marker)
        return text[:ni].strip(), text[ni + len(neg_marker):end].strip()
    return text[:end].strip(), ""


def extract_prompts(png_path):
    """Return (positive, negative) for a PNG. Never raises on content; only on unreadable files."""
    chunks = pngchunks.parse_file(png_path)
    fields = pngchunks.text_fields(chunks)
    params = fields.get("parameters")
    if params is not None:
        return _split_a1111(params)
    prompt_json = fields.get("prompt")
    if prompt_json is not None:
        try:
            graph = json.loads(prompt_json)
            width, height = pngchunks.image_size(chunks)
            recipe = _analyze.analyze(graph, width, height)
            return (recipe.positive or "", recipe.negative or "")
        except Exception:
            pass
    return ("\n".join(fields.values()), "")  # fallback: nothing structured, search everything


# --------------------------------------------------------------------------------
# Matching (smart-case: a fragment with an uppercase letter is case-sensitive)

def _has_upper(s):
    return any(c.isupper() for c in s)


def _contains(needle, haystack, ignore_case):
    if ignore_case or not _has_upper(needle):
        return needle.lower() in haystack.lower()
    return needle in haystack


def _matches(haystack, fragments, query, exact, ignore_case):
    if exact:
        return _contains(query, haystack, ignore_case)
    return all(_contains(frag, haystack, ignore_case) for frag in fragments)


# --------------------------------------------------------------------------------
# CLI

def run(args) -> int:
    """`igmt search`: find images whose prompt matches. Exit 0 if any match, 1 if none, 2 on misuse."""
    fragments = " ".join(args.terms).split()
    if not fragments:
        print("search: no search terms given.", file=sys.stderr)
        return 2
    query = " ".join(args.terms)
    roots = args.dir or ["."]
    scope = "positive" if args.positive else "negative" if args.negative else "both"

    where = {"positive": "positive prompt", "negative": "negative prompt", "both": "either prompt"}[scope]
    mode = "exact phrase" if args.exact else "fragments"
    print(f"Searching {where} for {mode}: {fragments if not args.exact else query!r}", file=sys.stderr)

    matched_dirs = set()
    found = False
    for root in roots:
        for png in sorted(Path(root).rglob("*.png")):
            try:
                positive, negative = extract_prompts(png)
            except Exception as e:
                print(f"{png}: ERROR: {e}", file=sys.stderr)
                continue
            haystack = {"positive": positive, "negative": negative,
                        "both": positive + "\n" + negative}[scope]
            if _matches(haystack, fragments, query, args.exact, args.ignore_case):
                print(png)
                matched_dirs.add(str(png.parent))
                found = True

    if matched_dirs:
        print("\nDirectories with matches:", file=sys.stderr)
        for d in sorted(matched_dirs):
            print(f"    {d}", file=sys.stderr)
    else:
        print("No matches.", file=sys.stderr)
    return 0 if found else 1
