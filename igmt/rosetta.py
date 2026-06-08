"""rosetta — inject A1111/CivitAI-compatible metadata derived from an embedded ComfyUI workflow.

Walks the ComfyUI `prompt` graph embedded in a PNG, reconstructs the generation recipe, and injects
an AUTOMATIC1111 / SD-Forge `parameters` text chunk so that services which don't analyze ComfyUI
graphs (CivitAI, SD Prompt Reader) recognize the image. See `briefs/rosetta-metadata-injector.md`.

This module currently provides only the CLI surface; the analysis/injection pipeline is under
construction.
"""

__all__ = ["add_subparser", "run"]


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
                   help="print the synthesized parameters string; write nothing")
    p.add_argument("--hash", action="store_true",
                   help="compute AutoV2 hashes for model/LoRA resources (requires the model files locally)")
    p.add_argument("--models-dir", action="append", metavar="DIR",
                   help="directory to search for model/LoRA files when hashing (repeatable)")
    p.set_defaults(func=run)
    return p


def run(args) -> int:
    """Handle `igmt rosetta`. Stub: the pipeline is not implemented yet."""
    print("rosetta: under construction — graph walk and injection not implemented yet.")
    print(f"  paths={args.paths} dry_run={args.dry_run} hash={args.hash} models_dir={args.models_dir}")
    return 0
