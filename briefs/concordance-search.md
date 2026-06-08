# Brief: `concordance` — prompt search across image corpora

*Companion to `rosetta` (see `briefs/rosetta-metadata-injector.md`). This is the existing
`metadata-matching-dirs.py` tool, folded into the toolkit and extended. `concordance` is the engine
module name; the CLI verb is **`igmt search`** (descriptive verbs on the surface, layered names in
the source — see the README).*

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

### 5. Chained / refining search (planned)

Beyond ANDing fragments *within* one mode, support chaining searches of *different* modes — e.g.
match an exact phrase, then narrow the result set with a fragment search (or vice versa). The
semantics are a set-intersection over the matched-file sets, each link carrying its own mode and
scoping. CLI shape TBD — likely repeated `--and <expr>` groups, or a small expression syntax. This
covers the workflow of "find the specific phrase, then filter those hits further." Deferred until
after the core single-search modes land.

## Search target

Match against the prompt text the reader extracts (positive and/or negative, per scoping) — only
that. The current code does **not** actually search filenames; the "filenames are searched because
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
