# Contributing to chandra

Thanks for your interest! Issues and pull requests are welcome.

## Reporting a workflow chandra doesn't parse

`chandra` reconstructs a generation recipe by walking the ComfyUI graph embedded in a PNG. Generators
and custom nodes are a moving target, so there will be workflows it doesn't yet handle correctly — a
prompt that comes out empty, a model or LoRA it misses, an exotic loader it doesn't recognize.

If you hit one, please [open an issue](https://github.com/Technologicat/chandra/issues) and **attach
an example image** whose embedded metadata isn't parsed correctly. The metadata *is* the bug report,
so a screenshot or a copy-pasted prompt won't do — we need the actual file with its chunks intact.

> **Attach the PNG inside a `.zip`.** GitHub (like many platforms) may re-encode or strip metadata
> from images you drop straight into the comment box — which would throw away the very chunks we need
> to debug. Zipping the PNG and attaching the `.zip` stores the bytes verbatim. (If you'd like to
> double-check what's in there first, `chandra show --recipe your.png` prints what chandra currently
> makes of it.)

Whether a given workflow ends up supported is a judgment call — some are common enough to be worth a
dedicated code path, others are one-offs that aren't. Either way, a real example is the most useful
thing you can provide, and even the unsupported ones help map the territory.

### Please keep examples SFW

GitHub is a family-friendly platform, and these issues are public, so **safe-for-work examples only,
please** — character art is welcome (it's a major use case in its own right), just no nudes or kink.
And if the case that actually broke happens to be NSFW: the parser only cares how the graph is
*wired*, not what the prompt *says*, so any SFW image through the same workflow reproduces the bug
just as well.

## Pull requests

For code changes, see [`briefs/`](briefs/) for the design rationale behind each engine, and run the
test suite before submitting:

```bash
pdm install
python -m pytest
python -m ruff check chandra/ tests/
```

New behavior should come with a test. Many integration tests read from a local `00_stuff/` scratch
directory that isn't part of the repository; they skip cleanly when it's absent, so a fresh clone's
suite runs green on the synthetic tests alone.
