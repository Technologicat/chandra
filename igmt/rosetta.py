"""rosetta — inject A1111/CivitAI-compatible metadata derived from an embedded ComfyUI workflow.

Walks the ComfyUI `prompt` graph embedded in a PNG, reconstructs the generation recipe, and injects
an AUTOMATIC1111 / SD-Forge `parameters` text chunk so that services which don't analyze ComfyUI
graphs (CivitAI, SD Prompt Reader) recognize the image. See `briefs/rosetta-metadata-injector.md`.

Current status: the read → analyze pipeline is wired — `igmt rosetta <png...>` prints the extracted
recipe. Synthesis (Recipe → parameters string) and injection are the next slices.
"""

import json
import sys
from pathlib import Path

from . import analyze as _analyze
from . import pngchunks

__all__ = ["add_subparser", "run", "extract_recipe", "iter_png_paths"]


def add_subparser(subparsers):
    """Register the `rosetta` subcommand on the dispatcher's subparsers action."""
    p = subparsers.add_parser(
        "rosetta",
        help="inject A1111/CivitAI metadata from a ComfyUI workflow",
        description=__doc__.strip().splitlines()[0],
    )
    paths = p.add_argument("paths", nargs="*", metavar="PNG", help="PNG file(s) and/or directories to process")
    # Restrict file-argument completion to PNGs when argcomplete is available.
    try:
        from argcomplete.completers import FilesCompleter
        paths.completer = FilesCompleter(("png", "PNG"))
    except ImportError:
        pass
    p.add_argument("--dry-run", action="store_true",
                   help="print the synthesized parameters string; write nothing (forthcoming)")
    p.add_argument("--hash", action="store_true",
                   help="compute AutoV2 hashes for model/LoRA resources (forthcoming)")
    p.add_argument("--models-dir", action="append", metavar="DIR",
                   help="directory to search for model/LoRA files when hashing (repeatable)")
    p.set_defaults(func=run)
    return p


def iter_png_paths(paths):
    """Expand the given files/directories into PNG paths (directories recursed)."""
    for p in paths:
        path = Path(p)
        if path.is_dir():
            yield from sorted(path.rglob("*.png"))
        else:
            yield path


def extract_recipe(png_path):
    """Read a PNG, pull its ComfyUI `prompt` graph + size, and analyze it into a Recipe."""
    chunks = pngchunks.parse_file(png_path)
    fields = pngchunks.text_fields(chunks)
    prompt_json = fields.get("prompt")
    if prompt_json is None:
        raise ValueError("no ComfyUI `prompt` chunk (not a ComfyUI image, or workflow-only)")
    graph = json.loads(prompt_json)
    width, height = pngchunks.image_size(chunks)
    return _analyze.analyze(graph, width, height)


def run(args) -> int:
    """Handle `igmt rosetta`: read → analyze → print the recipe for each PNG."""
    paths = list(iter_png_paths(args.paths))
    if not paths:
        print("rosetta: no PNG files given.", file=sys.stderr)
        return 2
    status = 0
    for path in paths:
        try:
            recipe = extract_recipe(path)
        except Exception as e:
            print(f"{path}: ERROR: {e}", file=sys.stderr)
            status = 1
            continue
        print(f"=== {path} ===")
        print(_analyze.format_recipe(recipe))
        print()
    print("(rosetta: showing extracted recipes; synthesis → parameters string and injection are "
          "not implemented yet.)", file=sys.stderr)
    return status
