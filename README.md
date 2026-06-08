# imagegen-metadata-tools

Tools for working with the metadata that image generators embed in their output.

Two command-line tools share this package:

- **`rosetta`** — reads the ComfyUI workflow embedded in a PNG, reconstructs the generation recipe
  by walking the node graph, and injects [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui)/SD-Forge-compatible
  metadata so the image is recognized by services that don't analyze ComfyUI graphs themselves —
  notably [CivitAI](https://civitai.com) on upload and
  [SD Prompt Reader](https://github.com/receyuki/stable-diffusion-prompt-reader) for offline
  inspection. *(In design — see [briefs/rosetta-metadata-injector.md](briefs/rosetta-metadata-injector.md).)*

- **`concordance`** — searches the prompts embedded across a directory tree of generated images, so
  you can find which images from a session match a given description. *(Currently the script
  [`metadata-matching-dirs.py`](metadata-matching-dirs.py); rename and extensions per
  [briefs/concordance-search.md](briefs/concordance-search.md).)*

## On the names

**`rosetta`** — after the [Rosetta Stone](https://en.wikipedia.org/wiki/Rosetta_Stone), which
carries one message in several scripts so that readers of any one of them can understand it. This
tool does the same for a generation recipe: it takes the content ComfyUI wrote in its own dialect
and re-expresses it in the dialect CivitAI and SD Prompt Reader read fluently. (No relation to
Apple's Rosetta.)

**`concordance`** — a [concordance](https://en.wikipedia.org/wiki/Concordance_(publishing)) is an
alphabetical index of the words in a text or corpus together with where each one occurs; biblical
and Shakespearean concordances are the classic examples. Searching the prompts across a folder of
images is the same operation over a corpus of pictures. The tool is read-only by design — its report
goes to your terminal, never into the files — which is why it isn't called `scribe`.

## Status

The design briefs live under [`briefs/`](briefs/). `concordance` exists today as
`metadata-matching-dirs.py`; `rosetta` is being built. This README will grow into usage docs as the
tools land.
