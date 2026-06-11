"""chandra — tools for the metadata image generators embed in their output.

Everything is dispatched through a single `chandra` entry point:

- ``chandra show``    — print the A1111/CivitAI-compatible metadata derived from an embedded
                        ComfyUI workflow (read-only).
- ``chandra inject``  — write that metadata into the image(s) in place, so they're recognized by
                        services that don't analyze ComfyUI graphs themselves.
- ``chandra eject``   — remove that metadata again (the inverse of inject), restoring the image to
                        its pre-inject state.
- ``chandra search``  — search the prompts embedded across a directory tree of generated images.
- ``chandra scrub``   — strip a ComfyUI image to a de-branded, shareable skeleton.

Three engines do the work: `rosetta` (analyze + synthesize + inject/eject, behind show/inject/eject),
`concordance` (behind search), and `palimpsest` (behind scrub). See the README for the naming lore.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("chandra")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.0.0+unknown"

# Signature stamped into everything `inject` writes — the A1111 `Version:` field and the XMP packet's
# `x:xmptk` (toolkit) attribute — so `eject` can recognize chandra's own output and remove only that,
# never a third party's metadata. The `rosetta` suffix names the engine that writes it (README lore).
TOOL_TAG = "chandra-rosetta"

__all__ = ["__version__", "TOOL_TAG"]
