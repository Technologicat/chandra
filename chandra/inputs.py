"""Shared CLI input resolution — one input model across `show`, `inject`, and `search`.

All three subcommands resolve their image inputs the same way, which is what lets them compose
(`chandra search … | chandra inject`):

  1. explicit files and/or directories given on the command line — directories are recursed for PNGs;
  2. otherwise, when stdin is piped (or ``--stdin`` is passed), paths read from stdin, one per line;
  3. otherwise, a per-command fallback: `search` recurses the current directory; `show`/`inject`
     report "give some inputs" instead, since silently recursing the whole cwd to *write into* every
     image is too sharp an edge to arm by default.

The only surface difference is where the explicit inputs come from: `show`/`inject` take them as a
positional argument, while `search` takes them via ``-d``/``--dir`` because its positional slot is
already spoken for by the search terms. The recursion and stdin behaviour are identical.
"""

import sys
from pathlib import Path

__all__ = ["expand_path", "iter_image_paths"]


def expand_path(path):
    """Yield image paths for a single input: a directory recurses to its PNGs (sorted), a file is itself."""
    path = Path(path)
    if path.is_dir():
        yield from sorted(path.rglob("*.png"))
    else:
        yield path


def iter_image_paths(explicit, *, use_stdin=False, default_cwd=False):
    """Resolve the shared input model into a stream of candidate image paths.

    `explicit` — files/directories from the command line (positional for show/inject, ``-d`` for search).
    `use_stdin` — force reading paths from stdin even when it's a TTY (the ``--stdin`` flag).
    `default_cwd` — when neither explicit inputs nor piped stdin are present, recurse the current
                    directory (search only; show/inject leave this False and report no inputs).

    Yields lazily, so `| head` upstream and short-circuiting downstream both work.
    """
    if explicit:
        for item in explicit:
            yield from expand_path(item)
    elif use_stdin or not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                yield from expand_path(line)
    elif default_cwd:
        yield from expand_path(".")
