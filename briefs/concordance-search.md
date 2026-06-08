# Brief: `concordance` — prompt search across image corpora

*Companion to `rosetta` (see `briefs/rosetta-metadata-injector.md`). This is the existing
`metadata-matching-dirs.py` tool, renamed into the scheme and extended.*

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

## Search target

Match against the prompt text the existing reader already extracts (positive and/or negative, per
scoping). Filenames are also searched today (because `pngcheck -ct` surfaced them) — keep or drop
deliberately; if kept, document it, since filename matches can surprise a fragment search.

## Naming

`concordance` — the scholarly term for an indexed listing of every occurrence of words in a corpus
with their locations, which is exactly what this produces. Read-only by design (its report goes to
stdout, never into the files) — which is why *not* `scribe`. Full rationale in the project
`README.md`.

## Non-goals

- No writing into image files (read-only).
- No regex mode in v1 (fragment + exact cover the use cases; the original used `re` internally, but
  the user-facing contract is substring fragments, not regex — avoid surprising metacharacters).
