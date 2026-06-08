#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""igmt — dispatcher for the imagegen-metadata-tools CLI toolbox.

Routes subcommands to the individual tools:

    igmt rosetta ...       inject A1111/CivitAI metadata from a ComfyUI workflow
    igmt concordance ...   search prompts across a directory of images

Each subtool module registers its own subparser (``add_subparser``) and a ``run(args)`` handler,
so the dispatcher only has to wire them up and route to ``args.func``. Tab completion is provided by
argcomplete when it is installed; it derives the completion set from the live parser, so new
subtools appear in completion automatically.
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

# Subtool modules, in the order they should appear in `igmt --help`.
_SUBTOOLS = (rosetta, concordance)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level `igmt` parser with one subparser per subtool."""
    parser = argparse.ArgumentParser(
        prog="igmt",
        description="Tools for the metadata image generators embed in their output.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    for tool in _SUBTOOLS:
        tool.add_subparser(subparsers)
    return parser


def main(argv=None) -> int:
    """Entry point for the `igmt` console script.

    `argv` defaults to `sys.argv[1:]`; pass an explicit list to drive the dispatcher from tests.
    """
    parser = build_parser()
    if argcomplete is not None:
        argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
