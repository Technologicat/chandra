"""rosetta — the engine behind `chandra show` and `chandra inject`.

Walks the ComfyUI `prompt` graph embedded in a PNG, reconstructs the generation recipe, and renders
an AUTOMATIC1111 / SD-Forge `parameters` string so that services which don't analyze ComfyUI graphs
(CivitAI, SD Prompt Reader) recognize the image. See `briefs/rosetta-metadata-injector.md`.

Two verbs, a deliberate read/write split (writing is never the default):

- `chandra show`   — analyze and print (read-only); `--recipe` dumps the structured recipe instead.
- `chandra inject` — write the synthesized `parameters` chunk into the PNG, in place.

The module keeps the name `rosetta` (it re-expresses one recipe in a script other tools read — see
the README for the lineage); the CLI surface is the descriptive verbs.
"""

import json
import os
import sys

from . import analyze as _analyze
from . import hashing as _hashing
from . import inputs as _inputs
from . import pngchunks
from . import synthesize as _synthesize

__all__ = ["add_subparser", "run_show", "run_inject", "extract_recipe"]


def _add_paths_arg(p):
    """Shared positional + flags for `show` and `inject`."""
    paths = p.add_argument("paths", nargs="*", metavar="PNG",
                           help="PNG file(s) and/or directories to process (directories recursed). "
                                "If none are given, paths are read from stdin when piped")
    # Restrict file-argument completion to PNGs when argcomplete is available.
    try:
        from argcomplete.completers import FilesCompleter
        paths.completer = FilesCompleter(("png", "PNG"))
    except ImportError:
        pass
    p.add_argument("--stdin", action="store_true",
                   help="read image paths from stdin, one per line (for chaining: "
                        "`chandra search … | chandra inject`)")
    p.add_argument("--hash", action="store_true",
                   help="compute AutoV2 hashes for model/LoRA resources (for CivitAI auto-linking)")
    p.add_argument("--models-dir", action="append", metavar="DIR",
                   help="directory to search for model/LoRA files when hashing (repeatable; also "
                        "$CHANDRA_MODELS_DIR, a $PATH-style colon-separated list)")


def add_subparser(subparsers):
    """Register the `show` and `inject` subcommands on the dispatcher's subparsers action."""
    show = subparsers.add_parser(
        "show", help="print the metadata that would be written (read-only)",
        description="Analyze a ComfyUI PNG and print the A1111/CivitAI metadata that `inject` would write.")
    _add_paths_arg(show)
    show.add_argument("--recipe", action="store_true",
                      help="print the structured recipe instead of the parameters string")
    show.set_defaults(func=run_show, parser=show)

    inject = subparsers.add_parser(
        "inject", help="write A1111/CivitAI metadata into the PNG(s)",
        description="Analyze a ComfyUI PNG and write the A1111/CivitAI `parameters` chunk into it, in place.")
    _add_paths_arg(inject)
    inject.set_defaults(func=run_inject, parser=inject)


def _load(png_path):
    """Read a PNG: return (chunks, Recipe). Raises if there is no ComfyUI `prompt` chunk."""
    chunks = pngchunks.parse_file(png_path)
    fields = pngchunks.text_fields(chunks)
    prompt_json = fields.get("prompt")
    if prompt_json is None:
        raise ValueError("no ComfyUI `prompt` chunk (not a ComfyUI image, or workflow-only)")
    graph = json.loads(prompt_json)
    width, height = pngchunks.image_size(chunks)
    return chunks, _analyze.analyze(graph, width, height)


def extract_recipe(png_path):
    """Read a PNG and analyze it into a Recipe (convenience wrapper around `_load`)."""
    return _load(png_path)[1]


def _hashing_context(args):
    """If `--hash` is set and model dirs are available, return (resolver, cache); else None."""
    if not getattr(args, "hash", False):
        return None
    dirs = list(args.models_dir or [])
    env = os.environ.get("CHANDRA_MODELS_DIR")
    if env:
        dirs += [d for d in env.split(os.pathsep) if d]
    if not dirs:
        print("chandra: --hash needs --models-dir (or $CHANDRA_MODELS_DIR); emitting names only.",
              file=sys.stderr)
        return None
    return (_hashing.ResourceResolver(dirs), _hashing.HashCache())


def _process(args, write: bool) -> int:
    """Shared read → analyze → (hash) → synthesize loop for `show` (write=False) and `inject`."""
    # Neither verb defaults to recursing the cwd: a bare `chandra show`/`inject` prints usage rather
    # than acting on an implicit directory-wide set (inject would be a mass write; show stays its
    # sister). Inputs must be given explicitly — as path arguments, or piped in (`search … | show`).
    paths = list(_inputs.iter_image_paths(args.paths, use_stdin=args.stdin, default_cwd=False))
    if not paths:
        args.parser.print_usage(sys.stderr)
        print(f"{args.parser.prog}: give one or more PNG files or directories "
              f"(or pipe paths in).", file=sys.stderr)
        return 2
    ctx = _hashing_context(args)
    status = 0
    for path in paths:
        try:
            chunks, recipe = _load(path)
        except Exception as e:
            print(f"{path}: ERROR: {e}", file=sys.stderr)
            status = 1
            continue
        if ctx is not None:
            for warning in _hashing.apply_hashes(recipe, *ctx):
                print(f"{path}: {warning}", file=sys.stderr)
        params = _synthesize.synthesize(recipe)
        if write:
            try:
                pngchunks.write_file(path, pngchunks.set_text_field(chunks, "parameters", params))
            except Exception as e:
                print(f"{path}: ERROR writing: {e}", file=sys.stderr)
                status = 1
                continue
            print(f"injected → {path}")
        else:
            print(f"=== {path} ===")
            print(_analyze.format_recipe(recipe) if args.recipe else params)
            print()
    if ctx is not None:
        ctx[1].save()
    return status


def run_show(args) -> int:
    """`chandra show`: read → analyze → print (read-only)."""
    return _process(args, write=False)


def run_inject(args) -> int:
    """`chandra inject`: read → analyze → synthesize → write the parameters chunk in place."""
    return _process(args, write=True)
