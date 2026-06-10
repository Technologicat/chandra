#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""chandra — dispatcher for the imagegen-metadata-tools CLI toolbox.

Routes subcommands to the individual tools:

    chandra search ...   search prompts across a directory of images
    chandra show ...     print the A1111/CivitAI metadata for a ComfyUI image (read-only)
    chandra inject ...   write that metadata into the image(s)

Each subtool module registers its subparser(s) (``add_subparser``) and sets an ``args.func`` handler,
so the dispatcher only has to wire them up and route. (The modules keep the names ``rosetta`` —
``show``/``inject`` — and ``concordance`` — ``search``; see the README for the lineage.) Tab
completion is provided by argcomplete when installed; it derives the completion set from the live
parser, so new subcommands appear in completion automatically.
"""

import argparse
import sys

try:
    import argcomplete
except ImportError:  # completion is optional; the CLI works without it
    argcomplete = None

from . import __version__
from . import concordance, rosetta

__all__ = ["build_parser", "main"]

# Subtool modules; subcommands appear in `chandra --help` in this order (search, show, inject).
_SUBTOOLS = (concordance, rosetta)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level `chandra` parser with one subparser per subtool."""
    parser = argparse.ArgumentParser(
        prog="chandra",
        description="Tools for the metadata image generators embed in their output.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    # Not required: bare `chandra` prints the command list (see main) rather than erroring.
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for tool in _SUBTOOLS:
        tool.add_subparser(subparsers)
    return parser


def main(argv=None) -> int:
    """Entry point for the `chandra` console script.

    `argv` defaults to `sys.argv[1:]`; pass an explicit list to drive the dispatcher from tests.
    Bare `chandra` (no subcommand) prints the help, which lists the available commands.
    """
    parser = build_parser()
    if argcomplete is not None:
        argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
