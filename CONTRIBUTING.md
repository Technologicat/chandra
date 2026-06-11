# Contributing to chandra

Issues and pull requests are welcome.

## Reporting a workflow chandra doesn't parse

`chandra` reconstructs a generation recipe by walking the ComfyUI graph embedded in a PNG. Generators
and custom nodes are a moving target, so there will always be workflows it doesn't yet handle correctly
— a prompt that comes out empty, a model or LoRA it misses, or an exotic loader it doesn't recognize,
to mention a few.

If you hit one, please [open an issue](https://github.com/Technologicat/chandra/issues) and **attach
an example** whose embedded metadata isn't parsed correctly. The metadata *is* the bug report, so a
screenshot or a copy-pasted prompt won't do — we need the graph structure with its chunks intact.

**The easy, privacy-safe way: `chandra scrub your.png`.** This writes a `your.scrubbed.png` reduced to
an anonymized skeleton — the rendered image is gone, prompt text is replaced with placeholders, and
any notes you've added to the workflow (Note / Markdown Note nodes) are dropped, but the graph wiring
remains. It's small, it carries nothing personal, and there's no image to worry about. If you want to
make sure, Have a look with `chandra show --recipe your.scrubbed.png` before posting — and if some
custom node tucked text somewhere unexpected, mention it on the issue.

> **If you want to attach the full PNG instead, put it inside a `.zip`.** GitHub (like many platforms)
> may re-encode or strip metadata from images you drop straight into the comment box — which would throw
> away the very chunks we need for debugging. Zipping the PNG stores the bytes verbatim. (A scrubbed PNG,
> being metadata-only, should be zipped too.)

Whether a given workflow ends up supported is a judgment call. Some are common enough to be worth a
dedicated code path, others are one-offs that aren't. Either way, a real example is the most useful
thing you can provide, and even the unsupported ones help map the territory.

### Please keep examples SFW

GitHub is a family-friendly platform, and these issues are public, so **safe-for-work examples only,
please** — character art is welcome, just no nudes or kink. And if the case that actually broke
happens to be NSFW: the parser only cares how the graph is *wired*, not what the prompt *says*,
so any SFW image through the same workflow reproduces the bug just as well.

## Pull requests

For code changes, see [`briefs/`](briefs/) for the design rationale behind each engine, and run the
test suite before submitting:

```bash
pdm install
$(pdm venv activate)
python -m pytest
python -m ruff check chandra/ tests/
```

New behavior should come with a test. The suite runs green on a fresh clone: unit tests, plus
structural tests over the committed, anonymized fixtures in `tests/fixtures/` (`chandra scrub`
skeletons of real workflows — graph wiring kept, image and prompt prose removed). A second tier of
integration tests reads from a local `00_stuff/` scratch directory that isn't in the repository;
those assert exact prompt text and skip cleanly when it's absent.
