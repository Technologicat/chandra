"""concordance — the engine behind `igmt search`.

A concordance of a corpus of pictures: find which generated images match given search fragments in
their embedded SD prompts. See `briefs/concordance-search.md`.

The module keeps the name `concordance` (an indexed listing of where words occur — see the README);
the CLI surface is the descriptive verb `igmt search`. This module currently provides only the CLI
surface; the search implementation (ported and extended from `metadata-matching-dirs.py`) is under
construction.
"""

__all__ = ["add_subparser", "run"]


def add_subparser(subparsers):
    """Register the `search` subcommand on the dispatcher's subparsers action."""
    p = subparsers.add_parser(
        "search",
        help="search prompts across a directory of images",
        description="Search the prompts embedded across a directory tree of generated images.",
    )
    p.add_argument("terms", nargs="*", metavar="WORD",
                   help="search fragment(s); ANDed, order-independent, substring match (default mode)")
    p.add_argument("-d", "--dir", action="append", metavar="DIR",
                   help="root directory to search (repeatable; default: current directory)")
    p.add_argument("-p", "--positive", action="store_true", help="match in the positive prompt only")
    p.add_argument("-n", "--negative", action="store_true", help="match in the negative prompt only")
    p.add_argument("--exact", action="store_true",
                   help="match the query as one contiguous string (instead of order-independent fragments)")
    p.set_defaults(func=run)
    return p


def run(args) -> int:
    """Handle `igmt search`. Stub: the search is not implemented yet."""
    print("search: under construction — not implemented yet.")
    print(f"  terms={args.terms} dirs={args.dir} positive={args.positive} "
          f"negative={args.negative} exact={args.exact}")
    return 0
