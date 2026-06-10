"""palimpsest — the engine behind `chandra scrub`.

Strips a ComfyUI PNG down to an anonymized *structural skeleton*: the graph wiring that the parser
needs, with the identifying content scraped off. A palimpsest is a manuscript scraped clean of its
original text and written over — and that's exactly the transform here: we remove the prompt text,
the rendered image, and any note nodes, but the structure still shows faintly through. The
strongest identifier in a shared image is the *prompt text* (prose style is a stylometric
fingerprint), so removing it is the main win; what remains is only the weak, structural trace of how
someone wires a graph. See `briefs/rosetta-metadata-injector.md`.

Two uses, one transform:

- **Sharing a misparse.** A contributor whose workflow `chandra` parses wrong can `scrub` it and post
  the result to a public issue — no rendered image (which might be NSFW), no personal prompt text,
  but enough graph structure to reproduce the bug. See `CONTRIBUTING.md`.
- **Test fixtures.** The same skeletons are what the test suite checks the parser against in CI,
  without committing anyone's branded images or prompts.

What it does to a PNG:

- keeps only `IHDR` (for the image size the recipe reports), the scrubbed `prompt` graph, and `IEND`;
- drops the pixels (`IDAT`), the `workflow` UI chunk (which holds any Note / MarkdownNote nodes, any
  muted / bypassed nodes, *and* a second copy of the prompt text in its widget values — the executable
  `prompt` graph has none of these), and any injected `parameters` / XMP description;
- neutralizes free-text in the `prompt` graph — prompt strings become ``scrubbed positive prompt`` /
  ``scrubbed negative prompt`` (a readability label; the role comes from `analyze.conditioning_roles`,
  the same node-level traversal the recipe parser uses, so inpaint and passthrough cases resolve
  correctly; a text node off the sampler's conditioning path falls back to ``scrubbed prompt
  (node <id>)``), and user file references (SaveImage prefix, LoadImage path) become ``scrubbed``;
- replaces checkpoint and LoRA names with ``scrubbed-checkpoint`` / ``scrubbed-lora`` — a user-chosen
  weight's name can itself be NSFW or identifying (a niche concept LoRA, the reporter's own upload);
- keeps the wiring, the LoRA count / order / strengths, and the VAE / CLIP / text-encoder names
  (public infrastructure, useful context, never identifying).

The neutralization is conservative — keyed on input names plus a long-free-text safety net — but not a
formal guarantee; a custom node could stash text under an unexpected key. Review a scrubbed file with
`chandra show` before posting it anywhere.
"""

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

from . import analyze as _analyze
from . import inputs as _inputs
from . import pngchunks

__all__ = ["add_subparser", "run", "scrub_graph", "scrub_chunks", "ScrubReport"]

# Input names that carry user prompt text across the common encoder nodes.
_PROMPT_KEYS = frozenset({
    "text", "prompt", "positive", "negative", "string",
    "text_g", "text_l", "text_positive", "text_negative",
    "wildcard", "wildcard_text", "populated_text",
})
# Input names that carry user file references (not model files — those are kept for the parser).
_PATH_KEYS = frozenset({"filename_prefix", "image"})

# A string is "filename-like" (a model/LoRA/path we keep) if it has a path separator or an extension.
_FILENAME_RE = re.compile(r"[\\/]|\.[A-Za-z0-9]{2,5}$")
# Free-text longer than this, under a non-structural key, is neutralized even if its key isn't known
# (the safety net for prompts stashed under custom-node input names).
_FREETEXT_MIN_LEN = 40


class ScrubReport(NamedTuple):
    """Summary of one scrub: which chunk kinds were dropped, and how many text fields were neutralized."""
    dropped: tuple
    neutralized: int


def _is_freetext(value: str) -> bool:
    return len(value) >= _FREETEXT_MIN_LEN and not _FILENAME_RE.search(value)


def _is_prompt_field(key: str, value) -> bool:
    """Does this (key, value) carry user prompt text — by a known key, or the long-free-text net?"""
    return isinstance(value, str) and (key in _PROMPT_KEYS or _is_freetext(value))


def scrub_graph(graph: dict) -> tuple[dict, int]:
    """Neutralize identifying free-text in a ComfyUI `prompt` graph, in place. Returns (graph, count).

    Prompt strings become ``scrubbed positive prompt`` / ``scrubbed negative prompt`` — the role comes
    from `analyze.conditioning_roles` (the same traversal the recipe parser uses, so the label matches
    how the prompt is read, and the inpaint/passthrough cases resolve correctly). A text node not on a
    sampler's conditioning path falls back to ``scrubbed prompt (node <id>)``. User file references
    become ``scrubbed``; checkpoint and LoRA names become ``scrubbed-checkpoint`` / ``scrubbed-lora``
    (a user-chosen weight's name can be NSFW or identifying). VAE / CLIP names, samplers, numbers, and
    the wiring are left untouched. `count` is the number of prompt fields neutralized.
    """
    roles = _analyze.conditioning_roles(graph)
    count = 0
    for nid, node in graph.items():
        node_inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(node_inputs, dict):
            continue
        for key, value in node_inputs.items():
            if not isinstance(value, str):
                continue  # links are [node, slot] lists; numbers/bools aren't text
            if key in _PATH_KEYS:
                node_inputs[key] = "scrubbed"
            elif "lora" in key.lower():
                node_inputs[key] = "scrubbed-lora"
            elif _analyze._is_base_loader_field(key):
                # Checkpoint / UNet / diffusion-model names. Scrubbed with LoRA names because a
                # user-chosen weight's *name* can be NSFW or identifying; reused from `analyze` so the
                # two stay in sync. VAE / CLIP / text-encoder names are kept (public infrastructure).
                node_inputs[key] = "scrubbed-checkpoint"
            elif _is_prompt_field(key, value):
                role = roles.get(nid)
                node_inputs[key] = f"scrubbed {role} prompt" if role else f"scrubbed prompt (node {nid})"
                count += 1
    return graph, count


def scrub_chunks(chunks) -> tuple[list, ScrubReport]:
    """Reduce a PNG chunk list to a de-branded skeleton: IHDR + scrubbed `prompt` + IEND.

    Raises if there is no IHDR or no ComfyUI `prompt` chunk (nothing to scrub).
    """
    ihdr = next((c for c in chunks if c.type == b"IHDR"), None)
    if ihdr is None:
        raise ValueError("no IHDR chunk")
    prompt_json = pngchunks.get_text_field(chunks, "prompt")
    if prompt_json is None:
        raise ValueError("no ComfyUI `prompt` chunk (not a ComfyUI image, or workflow-only)")

    scrubbed, neutralized = scrub_graph(json.loads(prompt_json))
    new_chunks = [ihdr, pngchunks.make_text_chunk("prompt", json.dumps(scrubbed)), pngchunks.Chunk(b"IEND", b"")]

    # Report what fell away: text chunks by keyword (workflow, parameters, XMP, …), others by type.
    dropped = []
    for c in chunks:
        if c.type in (b"IHDR", b"IEND"):
            continue
        keyword = pngchunks.keyword_of(c)
        if keyword == "prompt":
            continue  # kept (scrubbed)
        dropped.append(keyword if keyword is not None else c.type.decode("latin-1"))
    return new_chunks, ScrubReport(tuple(dict.fromkeys(dropped)), neutralized)


# --------------------------------------------------------------------------------
# CLI

def add_subparser(subparsers):
    """Register the `scrub` subcommand on the dispatcher's subparsers action."""
    p = subparsers.add_parser(
        "scrub",
        help="strip a ComfyUI PNG to an anonymized, shareable skeleton",
        description="Strip a ComfyUI PNG down to an anonymized structural skeleton: drop the image "
                    "pixels, the UI workflow/documentation, and any injected metadata, and neutralize "
                    "prompt text — keeping the graph wiring and model names. For sharing a workflow "
                    "that misparses (privacy-safe) and for generating test fixtures.")
    paths = p.add_argument("paths", nargs="*", metavar="PNG",
                           help="PNG file(s) and/or directories to scrub (directories recursed). "
                                "If none are given, paths are read from stdin when piped")
    try:
        from argcomplete.completers import FilesCompleter
        paths.completer = FilesCompleter(("png", "PNG"))
    except ImportError:
        pass
    p.add_argument("--stdin", action="store_true",
                   help="read image paths from stdin, one per line (for chaining: "
                        "`chandra search … | chandra scrub`)")
    p.add_argument("-o", "--output-dir", metavar="DIR",
                   help="write scrubbed copies into DIR (basenames preserved). "
                        "Default: alongside each source as `<name>.scrubbed.png`")
    p.set_defaults(func=run, parser=p)


def run(args) -> int:
    """`chandra scrub`: write a de-branded skeleton of each input PNG. The source is never modified."""
    # Like inject, scrub does not default to the cwd: it writes files, so a bare command prints usage
    # rather than spraying `.scrubbed.png` copies across the current directory.
    paths = list(_inputs.iter_image_paths(args.paths, use_stdin=args.stdin, default_cwd=False))
    if not paths:
        args.parser.print_usage(sys.stderr)
        print(f"{args.parser.prog}: give one or more PNG files or directories (or pipe paths in).",
              file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir) if args.output_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    status = 0
    for path in paths:
        try:
            new_chunks, report = scrub_chunks(pngchunks.parse_file(path))
        except Exception as e:
            print(f"{path}: ERROR: {e}", file=sys.stderr)
            status = 1
            continue
        out_path = (out_dir / path.name) if out_dir is not None else path.with_suffix(".scrubbed.png")
        if out_path.resolve() == Path(path).resolve():
            print(f"{path}: ERROR: output would overwrite the source; use -o or rename", file=sys.stderr)
            status = 1
            continue
        try:
            pngchunks.write_file(out_path, new_chunks)
        except Exception as e:
            print(f"{path}: ERROR writing {out_path}: {e}", file=sys.stderr)
            status = 1
            continue
        removed = ", ".join(report.dropped) if report.dropped else "nothing"
        print(f"scrubbed → {out_path}  (removed {removed}; neutralized {report.neutralized} prompt(s))")
    return status
