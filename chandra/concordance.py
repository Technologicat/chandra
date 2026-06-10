"""concordance — the engine behind `chandra search`.

A concordance of a corpus of pictures: find which generated images match given search fragments in
their embedded SD prompts. See `briefs/concordance-search.md`.

The module keeps the name `concordance` (an indexed listing of where words occur — see the README);
the CLI surface is the descriptive verb `chandra search`.

Per image we extract `(positive, negative)`: from an A1111 `parameters` chunk if present (Forge
images, or ones `chandra inject` wrote), otherwise by analyzing the ComfyUI `prompt` graph (so raw,
un-injected ComfyUI images are searchable too), otherwise the concatenated raw text as a fallback.

Boolean search without a query language: AND is the default within a clause (and the pipe between
clauses), `--any` makes a clause OR, and `-v/--invert` negates a clause. Chained through pipes that
is conjunctive normal form with negated clauses — effectively full boolean. Pipe-friendly: stdout
carries only matching paths, so refinement chains as `chandra search A | chandra search B`.
"""

import json
import os
import sys
from pathlib import Path

from . import analyze as _analyze
from . import pngchunks

try:
    import colorama
    from colorama import Fore, Style
except ImportError:  # highlight degrades to plain text without it
    colorama = None

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
                       help="root directory to search (repeatable). Default: read paths from stdin "
                            "when piped, else the current directory")
    try:
        from argcomplete.completers import DirectoriesCompleter
        d.completer = DirectoriesCompleter()
    except ImportError:
        pass
    p.add_argument("--stdin", action="store_true",
                   help="read candidate image paths from stdin, one per line (for chaining: "
                        "`chandra search A | chandra search B`)")
    p.add_argument("--dirs-only", action="store_true",
                   help="print matching directories (deduplicated) instead of individual file paths")
    p.add_argument("-C", "--context", action="store_true",
                   help="show a highlighted snippet of the matching prompt (human display; not for piping)")
    # Boolean combinators (no query DSL): default AND; --any => OR; -v => NOT (per clause).
    p.add_argument("--any", "--or", dest="match_any", action="store_true",
                   help="match if ANY fragment is present (OR) instead of all (AND)")
    p.add_argument("-v", "--invert", "--not", dest="invert", action="store_true",
                   help="invert: match images that do NOT satisfy the clause (chain/--any give NOT/NOR)")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("-p", "--positive", action="store_true", help="match in the positive prompt only")
    scope.add_argument("-n", "--negative", action="store_true", help="match in the negative prompt only")
    p.add_argument("--exact", action="store_true",
                   help="match the whole query as one contiguous string (instead of fragments)")
    p.add_argument("-i", "--ignore-case", action="store_true",
                   help="force case-insensitive matching (overrides per-fragment smart-case)")
    p.set_defaults(func=run, parser=p)
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


def _matches(haystack, fragments, query, exact, ignore_case, match_any=False):
    if exact:
        return _contains(query, haystack, ignore_case)
    combine = any if match_any else all
    return combine(_contains(frag, haystack, ignore_case) for frag in fragments)


# --------------------------------------------------------------------------------
# Highlighted context snippet (grep-style; colorized only on a TTY)

def _merge_spans(spans):
    merged = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _match_spans(text, needles, ignore_case):
    """All (start, end) spans where any needle occurs in text, merged."""
    spans = []
    for needle in needles:
        if not needle:
            continue
        hay, pat = (text.lower(), needle.lower()) if (ignore_case or not _has_upper(needle)) else (text, needle)
        start = 0
        while True:
            i = hay.find(pat, start)
            if i == -1:
                break
            spans.append((i, i + len(pat)))
            start = i + len(pat)
    return _merge_spans(spans)


def _highlight_snippet(haystack, fragments, query, exact, ignore_case, color, width=40):
    """A one-line snippet around the matches, with matched spans highlighted (if color)."""
    norm = " ".join(haystack.split())
    if not norm:
        return ""
    spans = _match_spans(norm, [query] if exact else fragments, ignore_case)
    if not spans:  # e.g. an inverted match — nothing to highlight; show the head
        head = norm[:2 * width]
        return head + ("…" if len(norm) > len(head) else "")
    windows = _merge_spans([(max(0, s - width), min(len(norm), e + width)) for s, e in spans])
    hl, rst = (Fore.RED + Style.BRIGHT, Style.RESET_ALL) if color else ("", "")
    parts = []
    for ws, we in windows:
        seg, cur = "", ws
        for s, e in spans:
            if ws <= s and e <= we:
                seg += norm[cur:s] + hl + norm[s:e] + rst
                cur = e
        seg += norm[cur:we]
        parts.append(("…" if ws > 0 else "") + seg + ("…" if we < len(norm) else ""))
    return " ".join(parts)


# --------------------------------------------------------------------------------
# Input resolution

def _input_paths(args):
    """Yield candidate PNG paths: the `-d` roots (recursed) if given, else stdin when piped, else cwd."""
    if args.dir:
        for root in args.dir:
            yield from sorted(Path(root).rglob("*.png"))
    elif args.stdin or not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                yield Path(line)
    else:
        yield from sorted(Path(".").rglob("*.png"))


# --------------------------------------------------------------------------------
# CLI

def run(args) -> int:
    """`chandra search`: find images whose prompt matches. Exit 0 if any match, 1 if none, 2 on misuse."""
    fragments = " ".join(args.terms).split()
    if not fragments:
        args.parser.print_usage(sys.stderr)
        print(f"{args.parser.prog}: give one or more search terms.", file=sys.stderr)
        return 2
    query = " ".join(args.terms)
    scope = "positive" if args.positive else "negative" if args.negative else "both"
    use_color = (bool(args.context) and colorama is not None
                 and sys.stdout.isatty() and not os.environ.get("NO_COLOR"))
    if use_color:
        colorama.just_fix_windows_console()

    matched_dirs = set()
    found = False
    for png in _input_paths(args):
        try:
            positive, negative = extract_prompts(png)
        except Exception as e:
            print(f"{png}: ERROR: {e}", file=sys.stderr)
            continue
        haystack = {"positive": positive, "negative": negative,
                    "both": positive + "\n" + negative}[scope]
        hit = _matches(haystack, fragments, query, args.exact, args.ignore_case, args.match_any)
        if args.invert:
            hit = not hit
        if not hit:
            continue
        found = True
        if args.dirs_only:
            matched_dirs.add(str(png.parent))
        elif args.context:
            print(png)
            print(f"    {_highlight_snippet(haystack, fragments, query, args.exact, args.ignore_case, use_color)}")
        else:
            print(png, flush=True)  # stream files so `| head` can short-circuit

    if args.dirs_only:
        for d in sorted(matched_dirs):
            print(d)
    return 0 if found else 1
