# Brief: `concordance` — prompt search across image corpora

*Companion to `rosetta` (see `briefs/rosetta-metadata-injector.md`). This is the existing
`metadata-matching-dirs.py` tool, folded into the toolkit and extended. `concordance` is the engine
module name; the CLI verb is **`igmt search`** (descriptive verbs on the surface, layered names in
the source — see the README).*

**Status: implemented** (`igmt/concordance.py`, `igmt search`) — fragment + exact modes, per-fragment
smart-case, `-p`/`-n` scoping, `-i` override, multi-root `-d`, stdin path input + pipe chaining (§5),
`--dirs-only` output mode; grep-style exit codes (0 match / 1 none / 2 misuse); no-args prints a short
usage. Output is pipe-clean (matching paths to stdout, nothing else). Planned: an opt-in `--context`
highlight mode (colorama) for human display.

## Purpose

Find images in a directory tree by what's written in their SD metadata. After a generative session
of hundreds of images, "which ones have a starship captain?" is answered by searching the
positive/negative prompts embedded in the PNGs — a *concordance* of the corpus (an indexed listing
of where words occur).

## Current state

`metadata-matching-dirs.py` already: walks the current directory recursively, reads positive and
negative prompts from PNG `tEXt` *and* `iTXt` chunks (Forge format), and matches a search term
(optionally restricted to positive `-p` or negative `-n`, case-insensitive `-i`). It prints
matching paths and a summary of matching directories.

## Changes

### 1. Directory argument

Accept one or more root directories as positional arguments; default to the current directory when
none given. (Today the root is hardcoded to `.`.)

### 2. Shared PNG-chunk module

The `tEXt`/`iTXt` read/pack/CRC machinery currently inlined here is extracted into a common module
that both `concordance` and `rosetta` import. `concordance` only needs the *read* side.

### 3. Search modes

**Fragment mode (default).** Split the query into whitespace-separated fragments; each fragment
must occur as a **substring** somewhere in the target text; all fragments must match (**AND**);
**order-independent**. So `cat photo` matches `photocatalytic` (both `cat` and `photo` are present
as substrings), and matches "a photo of a cat" equally. This is the everyday mode — you remember a
few word-fragments, not the exact phrasing.

**Exact mode (`--exact`).** Match the query as a single contiguous string, verbatim. For the rare
case where fragment matching is too loose to be useful (e.g. disambiguating a specific phrase).

### 4. Smart-case (per fragment)

Case sensitivity is inferred per fragment: a fragment containing **at least one uppercase letter**
is matched **case-sensitively**; an **all-lowercase** fragment is matched **case-insensitively**.
So `cat` matches "Cat"/"CAT"/"cat", while `Cat` matches only "Cat". (This generalizes today's
global `-i` flag; an explicit override flag can still force one mode if wanted.)

The positive-only / negative-only scoping (`-p` / `-n`) is retained.

### 5. Chained / refining search — implemented via pipes

`igmt search` is a Unix filter: stdout carries only matching paths, and when stdin is piped (or
`--stdin` is given) it reads candidate paths from stdin instead of walking dirs. So refinement is
just `|`:

    igmt search --exact "starfleet captain" -d ~/imgs | igmt search catgirl | igmt search -n blurry

Each stage applies its own mode/scope; the result is the set-intersection (commutative — pipe order
doesn't change the final set). It composes with the rest of the shell (`| wc -l`, `| head`,
`| xargs -d'\n' cp -t picks/`, `| fzf`). Input precedence: `-d` dirs if given, else piped stdin, else
the current directory. A single-command `--and` form (one dir-walk, all clauses in one invocation)
remains a possible future convenience, but pipes already deliver the capability — and interop with
every other tool for free.

### 6. Output modes

Default stdout is matching file paths, one per line (pipe-clean — no header or summary). `--dirs-only`
prints the deduplicated matching *directories* instead, for the "which folders have hits" question.
Errors go to stderr. Planned: `--context` (opt-in) — print a snippet of the matching prompt with the
matched fragments highlighted (colorama), like `grep`'s context view; opt-in so it never pollutes the
pipe, and colorized only when stdout is a terminal.

## Search target

Match against the prompt text the reader extracts (positive and/or negative, per scoping) — only
that. `extract_prompts` gets `(positive, negative)` from three sources, in order: an A1111
`parameters` chunk (Forge images, or ones `igmt inject` wrote) split into halves; otherwise the
ComfyUI `prompt` graph run through `rosetta`'s `analyze` (so raw, un-injected ComfyUI images — the
user's actual corpus — are searchable, and `-p`/`-n` scoping works on them); otherwise the
concatenated raw text as a fallback. The current code does **not** actually search filenames; the
"filenames are searched because
`pngcheck -ct` prints them too" comment is a relic of the original implementation
(`00_stuff/metadata-matching-dirs-with-pngcheck.py`), which shelled out to `pngcheck -ct` and
grepped its text output (filenames included). The current pypng-based version reads chunks directly
and matches text only. Drop the stale comment during the rename.

## Naming

CLI verb: **`igmt search`** (self-documenting). Engine module: **`concordance`** — the scholarly
term for an indexed listing of every occurrence of words in a corpus with their locations, which is
exactly what this produces. Read-only by design (its report goes to stdout, never into the files) —
which is why *not* `scribe`. Full rationale in the project `README.md`.

## Non-goals

- No writing into image files (read-only).
- No regex mode in v1 (fragment + exact cover the use cases; the original used `re` internally, but
  the user-facing contract is substring fragments, not regex — avoid surprising metacharacters).
