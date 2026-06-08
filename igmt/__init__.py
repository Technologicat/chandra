"""imagegen-metadata-tools — tools for the metadata image generators embed in their output.

Two CLI tools, dispatched through a single `igmt` entry point:

- ``igmt rosetta``      — inject A1111/CivitAI-compatible metadata derived from an embedded
                          ComfyUI workflow, so the image is recognized by services that don't
                          analyze ComfyUI graphs themselves.
- ``igmt concordance``  — search the prompts embedded across a directory tree of generated images.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("imagegen-metadata-tools")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
