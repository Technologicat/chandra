"""chandra — tools for the metadata image generators embed in their output.

Everything is dispatched through a single `chandra` entry point, with three subcommands:

- ``chandra show``    — print the A1111/CivitAI-compatible metadata derived from an embedded
                        ComfyUI workflow (read-only).
- ``chandra inject``  — write that metadata into the image(s) in place, so they're recognized by
                        services that don't analyze ComfyUI graphs themselves.
- ``chandra search``  — search the prompts embedded across a directory tree of generated images.

Two engines do the work: `rosetta` (analyze + synthesize + inject, behind show/inject) and
`concordance` (behind search). See the README for the naming lore.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("chandra")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
