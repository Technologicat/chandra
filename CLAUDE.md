# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Fleet-wide conventions live in the global `~/.claude/CLAUDE.md`; this file holds only what's specific
to chandra.

## What is chandra

A single command-line tool, `chandra`, for the metadata AI image generators embed in their PNG output.
It walks the ComfyUI workflow graph a PNG carries, reconstructs the generation recipe, and re-expresses
it in the AUTOMATIC1111 / SD-Forge `parameters` format that services and apps (CivitAI, SD Prompt
Reader) read robustly — covering the img2img, inpaint, edit-mode, LoRA-chain, and non-standard-loader
graphs those tools mostly punt on.

**Architecture — three engines behind descriptive CLI verbs** (`chandra/`):

- **`rosetta`** — `show` / `inject` / `eject`. Reads the ComfyUI `prompt` graph and re-expresses the
  recipe in A1111 format (it re-renders one recipe in a script other tools read). Built on
  `analyze` (the role-based graph walk → `Recipe`), `synthesize` (`Recipe` → A1111 `parameters`
  string), `xmp` (the `dc:description` packet general viewers show), `pngchunks` (PNG chunk read/write),
  and `hashing` (AutoV2 for CivitAI auto-linking, `--hash`).
- **`concordance`** — `search`. Boolean prompt search across a directory tree of images.
- **`palimpsest`** — `scrub`. Strips a PNG to an anonymized structural skeleton for safe sharing.

`cli.py` is the dispatcher; `inputs.py` is the shared path/stdin iterator. The module keeps the engine
names (`rosetta`/`concordance`/`palimpsest`); the CLI surface is the plain verbs.

**The briefs are the design source of truth.** Each engine has a design brief in `briefs/`
(`rosetta-metadata-injector.md`, `concordance-search.md`, `palimpsest-scrub.md`) carrying the rationale,
the observed ComfyUI-graph patterns, the format contracts (e.g. SD Prompt Reader's A1111 parser rules),
and the verification plan. Read the relevant brief before changing engine behavior, and update it when
the behavior changes.

## Core principle: honest reporting

`rosetta` never guesses. A field it can't resolve from the graph is omitted (or left `None`), never
filled with a plausible default — a wrong value that *looks* authoritative is worse than an absent one.
This shapes the whole analyzer: scalar resolution returns `None` on anything it can't resolve honestly;
fractional dynamic-step counts are truncated to the integer that actually ran (not rounded); and a
ComfyUI image that isn't a generation (no sampler) is described by its actual operation pipeline rather
than dressed up as an empty recipe. When extending the analyzer, keep this bar: resolve or abstain.

## Privacy by design

chandra is interop-first, but every choice minimizes added exposure (see the README's "Privacy by
design" section — keep it true): it makes **no network calls and has no telemetry** (even `--hash`
computes AutoV2 locally; CivitAI matches on its side at upload); writing is opt-in and reversible
(`inject`/`eject` leave the original ComfyUI graph byte-intact, and never default to the cwd); and the
metadata it synthesizes surfaces only the recipe already embedded — for non-generation workflows it
reports operation `class_type`s only, never user-controlled free text such as `SaveImage`
`filename_prefix` (which can carry usernames/paths). That last line is the same privacy boundary
`scrub` draws, and the description honors it deliberately.

## Build and development

PDM with `pdm-backend`, Python 3.11+. chandra is an **application**, so it **commits `pdm.lock`**
(per the fleet lockfile policy). Dev tooling lives in the `dev` dependency group in `pyproject.toml`
(pytest, coverage, ruff, flake8, …) — add tools there, not via ad-hoc `pip install`.

```bash
python runtests.py            # run the suite (pytest under the hood)
coverage run -m runtests      # with coverage (what CI's Coverage workflow runs)
python -m ruff check chandra/ tests/
```

**Linting:** ruff is the authority (`select = E, W, F, SIM`, line length 130 — configured in
`pyproject.toml`). `flake8rc` exists only for Emacs flycheck; ruff is what CI gates on. Suppress at the
use site with `# noqa: CODE -- reason`, never per-file.

## Tests and fixtures — two distinct corpora

This is the non-obvious part. Test image data comes from two places with opposite trust/availability:

- **`00_stuff/`** — gitignored local scratch holding **real, brand-bearing** generated PNGs. The
  content tests (exact prompt text, model names) live here and **skip when the dir is absent** (so CI,
  which never sees it, skips them cleanly). Never commit anything from `00_stuff/`.
- **`tests/fixtures/`** — committed, anonymized `chandra scrub` skeletons (no pixels, prompts
  neutralized, model names scrubbed). These **run everywhere including CI**, giving coverage of the
  parser against real graph *structures* without shipping real images. Their golden values were
  verified by eye against the originals at fixture-creation time; they are golden, not derived from the
  parser under test. Regenerate a fixture with `chandra scrub <original> -o tests/fixtures/`.

**Fixture/sample naming convention:** non-generation workflows (no sampler — background removers, pose
detectors, …) are named `tools-*.png`. The gen-analysis parametrized tests filter these out
(`GEN_FIXTURES` / `GEN_SAMPLES`); the non-gen tests pick them up (`NONGEN_*`). When adding a fixture,
follow the prefix so it lands in the right test bucket.

**Brand separation:** keep the CivitAI and GitHub brands disjoint in test data, and keep any CivitAI
presence out of version-controlled docs/fixtures. The scrubbed fixtures carry no brand by construction;
preserve that.

## Releases

- **Tags are bare** (`0.1.1`, not `v0.1.1`) — check `git tag --list` before tagging.
- PyPI publishing is **CI-driven** via trusted publishing on tag push; no manual `twine upload`.
- Changelog (`CHANGELOG.md`) is **user-facing** and follows the fleet compact style: one or two
  sentences per entry, what changed from the user's perspective; an `Internal` subsection per version
  for refactors/CI/test changes. Only document changes since the last tagged release — a bug introduced
  and fixed within an unreleased dev window never reached a user (note it in the commit message
  instead). Write the entry alongside the fix, not at release time.
- Post-release: bump to `X.Y.Z.dev0`, add a `## X.Y.Z (in progress)` changelog stub.

## Voice and naming

chandra follows the fleet's "reward the curious reader without punishing the casual one" sensibility.
The names carry a coherent **decipherment / astronomy** palette: `chandra` (Sanskrit *moon*; also
Chandrasekhar, the Chandra X-ray Observatory — reading what's present but unseen), `rosetta`,
`concordance`, `palimpsest`. New component names should fit that register and work on their surface
meaning regardless. Easter eggs are welcome where they don't cost clarity, and delivery stays deadpan —
the README's `search` examples quietly assemble Star Trek boolean queries; the joke is for the reader to
find, never pointed at.

The load-bearing XMP packet BOM in `xmp.py` is written as an explicit `'\uFEFF'` escape (invisible
character → escape, not a pasted glyph), per the fleet rule.
