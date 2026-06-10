# Brief: `palimpsest` — scrub a ComfyUI PNG to an anonymized skeleton

*Companion to `rosetta` (see `briefs/rosetta-metadata-injector.md`). `palimpsest` is the engine
module name; the CLI verb is **`chandra scrub`** (descriptive verbs on the surface, layered names in
the source — see the README).*

**Status: implemented** (`chandra/palimpsest.py`, `chandra scrub`) — reduces a PNG to `IHDR` +
scrubbed `prompt` + `IEND`; drops the image pixels, the `workflow` UI chunk, and any injected
`parameters`/XMP; neutralizes prompt text (role-tagged) and user file references; shared CLI input
model (files/dirs/stdin, no cwd default — it writes files); `-o`/`--output-dir`; never modifies the
source. Grep-style per-file summary on stdout.

## Purpose

Two needs, one transform:

1. **Privacy-safe bug reports.** When `chandra` parses someone's workflow wrong, the most useful
   thing they can send is the graph that reproduces it. But the PNG also carries a rendered image
   (possibly not safe for a public, family-friendly tracker) and the prompt text (whose prose style
   is a stylometric fingerprint). `scrub` removes both and keeps the wiring, so the example is safe
   to attach in the open. See `CONTRIBUTING.md`.

2. **Test fixtures.** The committed test corpus is built by scrubbing real ComfyUI images, so CI can
   exercise the parser against real *graph structures* without committing anyone's images or prose.
   The development corpus lives in the gitignored `00_stuff/`; the scrubbed skeletons are what ship.

The same skeleton serves both — there is one transform, not two.

## What it removes / keeps

Keep only `IHDR` (so the recipe still reports the image size), the scrubbed `prompt` graph, and
`IEND`. Everything else goes:

- **`IDAT` (pixels)** — drops the rendered image entirely. This is the bulk of the file (~1.6 MB →
  a few KB) and removes any not-safe-for-work or otherwise sensitive picture in one move.
- **`workflow` chunk** — the ComfyUI *UI* graph. Any Note / MarkdownNote nodes live here, as do any
  muted or bypassed nodes, and so does a second copy of the prompt text (in each node's widget
  values); the executable `prompt` graph has none of these — neither the notes, nor the skipped
  nodes, nor that duplication. The parser never reads `workflow`, so dropping it costs nothing — and
  it's also what stops the prompts leaking via the back door while we scrub the `prompt` chunk.
- **`parameters` / XMP** — any metadata a prior `chandra inject` wrote (we want to test that the
  parser *synthesizes* these, not read a baked-in copy).

In the surviving `prompt` graph:

- **Prompt text → `scrubbed positive prompt` / `scrubbed negative prompt`.** The role is read by
  tracing the sampler's `positive` / `negative` conditioning links back to the text nodes, *in this
  module*, independent of the recipe parser. So if `analyze` later mis-assigns the roles, a scrubbed
  example exposes the disagreement (its tag won't match `show --recipe`). Text not reachable from a
  sampler falls back to `scrubbed prompt (node <id>)`. (The two paths share only the ComfyUI
  convention that the sampler inputs are *named* `positive`/`negative`; beyond that they differ.)
- **User file references → `scrubbed`.** SaveImage `filename_prefix`, LoadImage `image`.
- **Checkpoint / LoRA names → `scrubbed-checkpoint` / `scrubbed-lora`.** A user-chosen weight's *name*
  can itself be NSFW or identifying (a niche concept LoRA, the reporter's own upload), so the names go
  — but the LoRA count, order, and strengths are kept, so the chain structure is intact.
- **Kept:** the link wiring, VAE / CLIP / text-encoder names (public infrastructure, useful context,
  never identifying), sampler/scheduler tokens, and all numeric settings.

## Neutralization rule

Targeted key sets plus a safety net, applied per input value (strings only — links are
`[node, slot]` lists, numbers/bools aren't text):

- known user-path keys (`filename_prefix`, `image`) → `scrubbed`;
- any key containing `lora` → `scrubbed-lora`;
- the base-loader name fields (`ckpt_name` / `gguf_name` / `unet_name` / `model_path`, via
  `analyze._is_base_loader_field`, reused so the two stay in sync) → `scrubbed-checkpoint`;
- known prompt keys (`text`, `prompt`, `positive`, `negative`, `string`, SDXL `text_g`/`text_l`, …)
  → role-tagged placeholder;
- **safety net:** any remaining string ≥ 40 chars that isn't filename-like (no path separator, no
  extension) → placeholder. Catches prompts stashed under a custom node's unexpected input name,
  while leaving the kept filenames (which have extensions) and short tokens alone.

It's conservative, not a formal guarantee — a custom node could hide text somewhere the heuristic
misses. The verb's output is reviewable with `chandra show`, and `CONTRIBUTING.md` tells reporters to
glance at the result before posting.

## What necessarily remains

The graph *structure* — which nodes, wired how — is the whole point (it's what the parser is tested
against, and what reproduces a bug). Structure is also a faint authorship trace, and there is no way
to remove it without destroying the artifact's usefulness. That residue is accepted; the strong,
content-level identifier (the prose) is gone.

## Naming

CLI verb: **`chandra scrub`** (plain, in the `show`/`inject`/`search` register). Engine module:
**`palimpsest`** — a manuscript scraped clean of its original writing and reused, with the earlier
text still faintly legible underneath. Exactly this transform: the identifying content is scraped
off, the structural trace remains. Full rationale in the project `README.md`.

## Non-goals

- Not a general metadata redactor: it targets the ComfyUI `prompt` graph, not arbitrary EXIF/XMP.
- No round-trip: a scrubbed PNG is a metadata skeleton (no pixels), not a viewable image. That's
  intentional — it exists to carry structure, and it travels best zipped.
- No formal anonymity guarantee (see the neutralization rule).
