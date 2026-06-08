# Brief: ComfyUI → CivitAI/A1111 metadata injector

*The tool is named `rosetta` (analyzer/injector); its companion prompt-search tool is `concordance`
(its own brief: `briefs/concordance-search.md`). This document is the design brief; it precedes
implementation.*

## Problem

ComfyUI embeds its generation recipe in a PNG as two non-standard `tEXt` chunks: `prompt`
(the API-format execution graph) and `workflow` (the UI graph). The services we care about —
**CivitAI** (on upload) and **SD Prompt Reader** (offline prompt inspection) — both *punt* on
analyzing arbitrary ComfyUI graphs. A trivial txt2img graph is sometimes captured; anything with
img2img, inpaint, an edit model, LoRA chains, or non-standard loaders is not.

The standard remedy — drop a "save metadata" node into the workflow — is brittle: for any given
graph there is usually some node whose inputs/outputs don't line up with what the metadata node
expects, so it can't be wired in.

**Our approach:** do the graph analysis *ourselves* — walk the links backward from the output
node, gathering the recipe — and emit the result in the one format both targets read robustly:
the AUTOMATIC1111 / SD-Forge `parameters` string. We then inject it as a `tEXt` chunk, leaving
the original `prompt`/`workflow` chunks untouched.

## Core insight: the `parameters` chunk is a priority override

SD Prompt Reader's format detector checks for an A1111 `parameters` chunk **before** it ever
considers ComfyUI's `prompt`/`workflow` (`image_data_reader.py:71-83`):

```python
if "parameters" in self._info:
    ...
    else:
        if "prompt" in self._info:
            self._tool = "ComfyUI\n(A1111 compatible)"   # both chunks present
        else:
            self._tool = "A1111 webUI"
        self._parser = A1111(info=self._info)
# the ComfyUI parser only runs when there is NO `parameters` chunk
```

It even has a dedicated label, `"ComfyUI (A1111 compatible)"`, for precisely the case we create:
an A1111 `parameters` chunk *plus* the original ComfyUI chunks. CivitAI behaves the same way in
practice — the A1111 string is its robust path; its own ComfyUI parsing is the flaky one.

So by adding a `parameters` chunk we (a) route both targets onto their reliable code path, (b)
keep the image fully reopenable in ComfyUI, and (c) inherit the "A1111 compatible" label for free.

> **Verification owed:** the CivitAI half of this claim is from experience, not from reading their
> code. Before declaring success we upload a real injected image to CivitAI and confirm it detects
> prompt, settings, and (with hashing on) resources. See *Verification plan*.

## The target format: A1111 / SD-Forge `parameters`

A single newline-structured string:

```
<positive prompt>
Negative prompt: <negative prompt>
Steps: 4, Sampler: dpmpp_2m, Scheduler: sgm_uniform, CFG scale: 1, Seed: 384881030039906, Size: 896x1152, Model: flux-2-klein-9b-Q4_K_M, Denoising strength: 1, Version: <tool name>
```

Rules SD Prompt Reader's `A1111` parser imposes (`format/a1111.py`):
- The settings block begins at the first `\nSteps:`. Everything before it (minus a
  `Negative prompt:` section) is the positive prompt.
- Settings are parsed as comma-separated `Key: value` pairs via `r"\s*([^:,]+):\s*([^,]+)"`.
  **Consequence: a value may not contain a comma or colon** or it will be mis-split. Values that
  can contain commas (model paths, LoRA lists) go in quoted forms CivitAI understands, or last.
- `Size` is parsed as `WxH`.

CivitAI additionally recognizes (subset, to confirm during verification):
- `Model hash: <autov2>` + `Model: <name>` — links the checkpoint to its CivitAI page.
- `Lora hashes: "name1: hash1, name2: hash2"` — links LoRAs.
- `Hashes: {json}` — alternative resource-hash carrier.
- `Denoising strength`, `Version`, and arbitrary extra `Key: value` fields (shown as-is).

### Honest reporting

We report what the graph contains, we do not editorialize:
- Negative prompts are emitted even when `cfg == 1` (turbo/step-distilled models bake in CFG and
  run at 1, making the negative inert). The placeholder text the user feeds in acts like a code
  comment; suppressing it would hide a real fact about the graph.
- Values we cannot resolve are reported as absent, never guessed.
- **Seed is reliably present** — the `prompt` chunk is the *executed* graph, so it carries the
  concrete seed actually used, even when the UI widget shows `-1`/randomize (that governs only the
  *next* run and is a `workflow`-graph artifact). Confirmed across all samples (concrete integer
  seeds, never `-1`), so the seed needs no special recovery.
- **Filename as a validated last resort (optional, low priority).** The image's own filename is
  normally the SaveImage `filename_prefix` plus `_NNNNN_`, and that prefix bakes in
  `timestamp-seed-model-sampler-steps-cfg`. If the actual filename still matches that template, the
  file is provably un-renamed, so prefix-encoded values may be trusted for any field genuinely
  absent from the graph — a *validated read*, not a guess (nobody renames a file to inject false
  values; renames give descriptive names). Gated on the template match; off by default. Since the
  seed is already in `prompt`, this is belt-and-suspenders, not a primary path.

## Architecture

Four stages, each a small, independently testable unit:

1. **Read** — parse PNG chunks, extract `prompt` (preferred) and `workflow` JSON. Reuse the
   `tEXt`/`iTXt` machinery already in `metadata-matching-dirs.py`.
2. **Analyze** — role-based backward walk of the API graph → a normalized `Recipe`
   (positive, negative, sampler params, model, LoRAs, vae, size, extras).
3. **Synthesize** — render `Recipe` → the A1111 `parameters` string (+ optional resource hashes).
4. **Inject** — splice a `parameters` `tEXt` chunk into the PNG, losslessly, in place.

The `Recipe` dataclass is the seam: analysis produces it, synthesis consumes it, tests assert on
it. Adding a new model family is "teach the walker new node roles"; it never touches synthesis.

## The graph-walk algorithm (heart of the tool)

We traverse the **`prompt` (API) graph**: `{node_id: {"class_type": str, "inputs": {...}}}`, where
each input value is either a literal or a `[node_id, slot]` link. Node ids are **opaque strings**
(ComfyUI subgraphs produce ids like `"172:77"` — never assume integers).

**The `prompt` graph is the *executed* graph — this is why we walk it, not `workflow`.** ComfyUI
omits bypassed (Ctrl+B, mode 4), muted (mode 2), and UI-only nodes (`MarkdownNote`, reroutes) from
`prompt` entirely, reconnecting links through bypassed passthroughs. Verified on the samples:
`flux2-edit.png` has 26 `workflow` nodes, 7 of them bypassed (the toggled-off extra reference-image
subgraphs plus an unused LoRA) — *none* appear in its 14-node `prompt`. So toggling LoRAs or
reference-image chains off (the common edit-mode habit — quicker than rewiring when the count
changes) needs no special handling: the walk only ever sees what actually ran.

Identification is **by role, not by node id or exact class name**. Node ids are incidental (the
sample set happens to reuse id `127` for the sampler only because the workflows descend from a
shared template — the algorithm never keys on an id). Class names proliferate across node packs,
but the *input-name contract* is stable, so we match on that. The walk:

1. **Find the sink.** A node of a Save-Image role (class matches `SaveImage`/`Image Save`/… or has
   an `images` input). If several, pick the one with the largest upstream subgraph; warn on
   ambiguity.
2. **Find the sampler.** Follow `images` → producing node. If it's a VAE-decode role, follow its
   `samples`; if it's a sampler (does its own decode, like `KSampler (Efficient)` whose image is
   output slot 5), stop. The **sampler role** = a node exposing the sampler input contract
   (`seed`/`noise_seed`, `steps`, `cfg`, `sampler_name`, `scheduler`, `denoise`) and/or a class
   name containing `sampler`.
3. **Extract scalars** from the sampler by input name, each via the **scalar resolver** (below).
4. **Extract prompts.** From the sampler's `positive` / `negative` links, recurse through
   conditioning-passthrough roles until a text-encoder role is reached:
   - text-encoder roles expose a text field: `text` (`CLIPTextEncode`) or `prompt`
     (`TextEncodeQwenImageEditPlus`, which also ingests the reference image). ComfyUI lets that text
     field itself be a *link* (converted to a string input — fed by primitive string nodes, "Text
     Multiline", prompt stylers, string-concat nodes); when it is a link, keep walking upstream
     until reaching the node that actually holds the literal string (SD Prompt Reader handles this
     case too, e.g. `format/comfyui.py`'s `isinstance(inputs["text"], list)` branch);
   - passthrough roles expose a `conditioning`/`positive`/`negative` input we follow by *name*
     (`ReferenceLatent`, `InpaintModelConditioning` — note it bundles positive/negative/latent on
     output slots 0/1/2, but we recurse into its *inputs* named `positive`/`negative` —
     `ControlNetApplyAdvanced`, `ConditioningCombine`, etc.).
5. **Extract model + LoRAs.** From the sampler's `model` link, walk the model-passthrough chain,
   collecting **every** LoRA node encountered (`LoraLoaderModelOnly`/`LoraLoader` →
   `lora_name`, `strength_model`, follow `model`). Real workflows chain several; the loop runs
   until a base-loader role: `CheckpointLoaderSimple.ckpt_name`, `LoaderGGUF`/`UnetLoaderGGUF`
   (`gguf_name`/`unet_name`), `unCLIPCheckpointLoader`, etc.
6. **Extract VAE** (extra): the sampler's `optional_vae` or the VAE-decode node's `vae` → a
   VAE-loader role (`vae_name`). Recorded as an extra field, not required.
7. **Size:** taken from the PNG's own width × height — the most reliable source, and what SD
   Prompt Reader itself uses. Tracing latent nodes would be actively wrong here: Flux.2's latent
   tile geometry differs from earlier models (feeding an old empty-latent node to Flux.2 *doubles*
   the output pixel size), and in inpaint/edit-inpaint the
   size set in the workflow is the *inpaint-region crop* (SD-Forge-style whole-canvas-to-region),
   not the final image. The PNG's own dimensions sidestep all of it.

### Observed patterns (from the 23 sample workflows)

All current samples are the user's own and share conventions, but the roles generalize:

| Mode            | positive/negative feed                              | latent feed                         |
|-----------------|-----------------------------------------------------|-------------------------------------|
| txt2img         | direct `CLIPTextEncode`                             | `Empty*LatentImage`                 |
| img2img         | direct `CLIPTextEncode`                             | `VAEEncode` ← scaled `LoadImage`    |
| inpaint         | `InpaintModelConditioning` (slots 0/1/2)           | same node, slot 2                   |
| edit (Flux.2)   | `ReferenceLatent` → `CLIPTextEncode`               | `Empty*LatentImage` + ref latents   |
| edit (Qwen)     | fused `TextEncodeQwenImageEditPlus.prompt`         | encoder also populates ref latents  |

| Role            | Class names seen                                                              | Field(s)                       |
|-----------------|------------------------------------------------------------------------------|--------------------------------|
| sampler         | `KSampler (Efficient)` (all samples); also plain `KSampler*`                  | the scalar contract            |
| base loader     | `CheckpointLoaderSimple`, `LoaderGGUF`, `UnetLoaderGGUF`                      | `ckpt_name`/`gguf_name`/`unet_name` |
| lora            | `LoraLoaderModelOnly`, `LoraLoader`                                           | `lora_name`, `strength_model`  |
| vae loader      | `VAELoader`, `VaeGGUF`                                                        | `vae_name`                     |
| clip loader     | `CLIPLoader`, `ClipLoaderGGUF`/`CLIPLoaderGGUF`                              | `clip_name` (extra)            |
| text encoder    | `CLIPTextEncode`, `TextEncodeQwenImageEditPlus`                              | `text`/`prompt`                |
| cond passthrough| `ReferenceLatent`, `InpaintModelConditioning`, `ControlNetApplyAdvanced`, …  | `conditioning`/`positive`/`negative` |

### The scalar resolver (linked-scalar wrinkle)

A sampler scalar (`steps`, `denoise`, `cfg`, `seed`, …) may be a literal or a link. In img2img and
inpaint the `Evaluate*` nodes implement SD-Forge-style **dynamic step scaling** — effective steps ≈
`steps × denoise` — so the value reaching the sampler is the *effective* count it actually ran.
(Edit-inpaint is the exception: edit mode requires `denoise = 1.0`, a full redraw of the region, so
there is no scaling.)

> **Reporting choice:** we report the **effective** steps (the resolved sampler input = what
> executed), not a separate configured-steps + denoise pair. This diverges from SD Forge's metadata
> convention (which reports configured steps), but it is what the graph actually contains and what
> the image actually used — consistent with the honest-reporting principle. Denoise is still
> reported alongside.

Resolution:

1. **Literal** → use it.
2. **Link to a Primitive role** (`PrimitiveInt`/`PrimitiveFloat`/…) → read `value`.
3. **Link to an `Evaluate Integers`/`Evaluate Floats` role** → it carries a free-form
   `python_expression` (e.g. `'a * b'`, but also `int()`, `ceil()`, `min`/`max`) over operands
   `a`/`b`/`c` that are themselves literals-or-links. Resolve operands recursively to plain
   numbers, then evaluate via **[`simpleeval`](https://github.com/danthedeckie/simpleeval)** with
   `names={'a':…,'b':…,'c':…}` plus a small whitelisted math-function set. `simpleeval` is the
   right tool here — it is purpose-built for evaluating an untrusted expression with injected
   variables, hardened against the obvious attacks, and supports the function calls these nodes
   actually use (a bare arithmetic AST-walk would reject them, and reimplementing its whitelist
   would just be reimplementing `simpleeval`). The expression text comes from a parsed PNG, i.e.
   untrusted input — `simpleeval`'s sandbox is the point.
4. **Otherwise** (including any expression `simpleeval` refuses) → unresolved → field reported
   absent (honest fallback).

Recursion is depth-bounded with cycle detection (graphs are DAGs, but a malformed file shouldn't
hang us).

## Resource hashing (CivitAI auto-linking) — optional

Decision: **name + settings always; hashing is opt-in.**

- Default: emit `Model:` and LoRA names as text. CivitAI shows them; it cannot auto-link without
  hashes.
- `--hash`: compute **AutoV2** hashes (= `sha256(file)[:10]`, confirmed below) from the actual
  model/LoRA files and emit `Model hash:` / `Lora hashes:`, enabling CivitAI page links. Requires
  the files to be locally accessible.
  - A configurable models directory (or several) is scanned to resolve a `ckpt_name`/`lora_name`
    (a bare filename in the graph) to a file on disk.
  - A persistent **hash cache** keyed by (path, size, mtime) — hashing multi-GB files is slow and
    we process batches of hundreds of images sharing the same few models.
  - Graceful fallback: a file we can't locate → that resource stays name-only; we warn, we don't
    fail.

> **Confirmed (2026-06-08), live against CivitAI's API, no auth required.**
> `GET /api/v1/model-versions/by-hash/{hash}` is a public endpoint: queried unauthenticated, a bogus
> hash returns `404 {"error":"Model not found"}` and the SD 1.5 hash `6ce0161689` returns `200` with
> full JSON. Its `files[].hashes` object exposes `AutoV1`/`AutoV2`/`SHA256`/`CRC32`/`BLAKE3`; for
> that file `SHA256 = 6CE0161689B385…` and `AutoV2 = 6CE0161689`, so **AutoV2 = `sha256(file)[:10]`**
> (lookup is case-insensitive). Algorithm: SHA-256 the file, take the first 10 hex chars, emit as
> `Model hash:`. **Still to confirm at build:** the exact `Lora hashes:` field string A1111 readers
> expect (10- vs 12-char shorthash, quoting) — check the A1111 LoRA extra-networks source. The
> public by-hash endpoint also gives us an optional self-check (does our computed hash resolve to
> the right model page?).

## CLI design

- **Two verbs, a read/write split.** `igmt show <png...>` analyzes and prints (the synthesized
  `parameters` string, or the parsed `Recipe` with `--recipe`), writing nothing. `igmt inject
  <png...>` writes the `parameters` chunk in place. Writing is its *own command*, never a side effect
  of the read path — so a stray `igmt show .` can't mutate anything, and you opt into writing by
  *typing* `inject`. (This replaced an earlier `rosetta [--inject]` flag model; the split makes the
  destructive action even more explicit. The engine module is still named `rosetta`.)
- **`inject` writes in place, no backup.** The chunk insertion is lossless surgery (below) — the
  original image bytes and existing chunks are preserved verbatim — so an in-place rewrite is safe
  and a backup is just clutter.
- Batch-first: both verbs accept files and/or directories (recurse), mirroring the existing
  `metadata-matching-dirs.py` ergonomics for sessions of hundreds of images.
- Idempotent: re-running `inject` on an already-injected image replaces the existing `parameters`
  chunk in place and emits exactly one — see the chunk-surgery rules below for the tEXt/iTXt detail.
- Other flags: `--hash` (+ `--models-dir`) for resource hashing (on both verbs — `show` previews
  what `inject` would write); a skip-if-present / `--force` policy; verbosity.

## PNG chunk surgery (lossless injection)

We do **not** re-encode via Pillow (that recompresses IDAT and drops/rewrites text chunks).
Instead we operate at the chunk level — the approach already proven in `metadata-matching-dirs.py`:
read the chunk stream, splice in our `parameters` chunk immediately before `IEND`, and recompute
its CRC. Image data and the `prompt`/`workflow` chunks stay byte-for-byte untouched.

**tEXt vs iTXt.** `tEXt` is Latin-1 only; `iTXt` is UTF-8. Both targets read both transparently:
SD Prompt Reader via PIL's `info` dict, and CivitAI ingests Forge images — where **newer Forge
appears to write `iTXt` unconditionally**, even for Latin-1 content (that's what silently broke
`metadata-matching-dirs.py` until `iTXt` reading was added), so `iTXt` is demonstrably accepted
downstream. Default rule (matching classic A1111/PIL behavior, and keeping the common case
greppable without decompression): **write `tEXt` when the `parameters` string is Latin-1-encodable,
otherwise `iTXt` (UTF-8)**. Because Forge proves `iTXt` is universally accepted, an always-`iTXt`
mode is a safe simplification if we ever want it; the read path handles both regardless.

**Idempotent replacement.** Before writing, scan for an existing `parameters` chunk in *either*
`tEXt` *or* `iTXt` form (a previously-injected image, or one from a Forge/Comfy save-metadata
node, could carry either) and remove it. Exactly one `parameters` chunk is ever present
afterward — we never stack a second.

**Both `prompt` and `workflow` chunks survive** — we only add/replace `parameters`, never touching
them — so the image stays fully reopenable in ComfyUI, and the Markdown-comment annotations the user
keeps in the `workflow` (documenting model/quant choices) are preserved.

## Verification plan

1. **A1111 format contract (in-suite, always runs).** `tests/test_synthesize.py` re-parses our
   output with `a1111_parse`, a faithful encoding of the A1111 `parameters` format that SD Prompt
   Reader (`format/a1111.py`) and CivitAI both consume — if our string parses under those rules,
   they read it. We do *not* add `sd-prompt-reader` as a dev dep: it's a desktop app that drags the
   whole GUI stack (customtkinter, tkinterdnd2, …), disproportionate for a ~15-line parser, and there
   is no single authoritative version to pin (installed copies drift; PyPI is at 1.3.5).
2. **Real SD Prompt Reader (optional / occasional).** Only the parser is needed — install it headless
   without the GUI stack:

       python -m pip install --no-deps sd-prompt-reader pillow piexif

   `test_real_sdpr_reads_injected` then feeds an injected sample through the *current* `ImageDataReader`
   and asserts `tool == "ComfyUI\n(A1111 compatible)"`, `READ_SUCCESS`, and matching prompts (it
   self-skips when the parser isn't importable). Confirmed green against PyPI 1.3.5 (2026-06-08).
3. **Live CivitAI upload** of a representative injected image per family/mode; confirm prompt,
   settings, and (with `--hash`) resource links are detected. Manual, but the ultimate acceptance
   gate — current CivitAI is confirmed to fail on the user's un-injected ComfyUI uploads, which is
   the whole motivation.
4. **PNG integrity:** `pngcheck` on every output; assert no warnings and that `prompt`/`workflow`/IDAT
   are unchanged (covered by the chunk-surgery tests).

## Tests & fixtures

- The fixtures we want are *embedded chunks*, not pixels — and `00_stuff/` is already one PNG per
  family×mode; it's only large (~28 MB) because each is a full-resolution render. The user will
  render a fresh, **minimal-resolution** set with the same workflows embedded (the chunks are a few
  KB each; tiny IDAT shrinks the files to a committable size). Those go in `tests/fixtures/` and are
  tracked; `00_stuff/` stays the gitignored reference (or is dropped once fixtures exist).
- The committed fixtures are **generated fresh for publication** (a further reason `00_stuff/`
  stays untracked). So during the sprint we develop against `00_stuff/`; the tracked
  `tests/fixtures/` set is created at publish time.
- Unit tests on `Recipe` extraction per fixture (the invariant: this graph → these fields),
  the scalar resolver (literal/primitive/evaluate/unresolved), and chunk surgery (insert, replace,
  idempotency, `pngcheck` clean).
- Injection tests are destructive, so each operates on a fresh copy. pytest's
  `tmp_path`/`tmp_path_factory` fixtures hand every test a clean dir under the system temp — which
  on these machines *is* the `/tmp` ramdisk — so "copy fixture → mutate → assert → auto-cleaned"
  is the built-in pattern; no manual ramdisk handling. Assert tEXt vs iTXt selection (Latin-1 vs
  non-Latin-1 content) and replace-either-form idempotency explicitly.
- Integration test through SD Prompt Reader's parser as in *Verification plan* step 1.

## Non-goals (v1)

- No metadata for non-ComfyUI sources (we read ComfyUI `prompt`/`workflow`; A1111-origin images
  already have `parameters`).
- No JPEG/WEBP *output* in v1 (PNG-first; the EXIF path exists in SD Prompt Reader if needed later).
  This is about the image container — within PNG we may write several textual fields (see
  "Human-readable metadata for general viewers").
- No editing/round-tripping of the ComfyUI graph itself — we only *read* it and *add* a chunk.
- No attempt to evaluate `Evaluate*` expressions beyond what `simpleeval` safely supports;
  anything it refuses resolves to "absent".

## Human-readable metadata for general viewers (Pix)

`parameters` serves the SD tools, but it does nothing for a general Linux image viewer like **Pix**
(the Linux Mint viewer, a gThumb fork) — yet the prompt should be visible there too, without any SD
software. Pix/gThumb read standard metadata: for PNG, a `Description`/`Comment` textual chunk, and
XMP `dc:description`. So, optionally (likely on by default), we *also* write a **human-readable
summary** (positive/negative prompt + key settings) into a `Description` `tEXt`/`iTXt` chunk
(and/or XMP), distinct from the machine-oriented `parameters` string.

> **Verification owed:** confirm which field Pix actually surfaces — open an injected output in Pix
> and check whether it reads PNG `Description`, `Comment`, or XMP `dc:description`, then write the
> field(s) Pix honors. The user has Pix installed and is the natural verifier.

## Project shape

Pure-Python PDM project (per the fleet's standard setup); developed on Python 3.14 with
`requires-python >= 3.11`. It's an app (CLI), so it **commits `pdm.lock`**.

**One dispatcher entry point: `igmt`.** A single console script with argparse subparsers routes to
three descriptive verbs — `igmt search`, `igmt show`, `igmt inject`. One PATH entry no matter how
many subcommands we add; `igmt --help` lists them; verbs are self-documenting (descriptive beats
evocative as subcommands — `git commit`, not `git rosetta`). The engine modules keep their layered
names — `rosetta` powers `show`/`inject`, `concordance` powers `search` (lineage in the README).
Each module registers its subparser(s) via `add_subparser` and sets an `args.func`; the dispatcher
routes. Tools are unit-tested by driving the dispatcher: `cli.main(["show", ...])`. (Distribution
name stays `imagegen-metadata-tools`; the *import* package is the short `igmt`, matching the
command — the Pillow→`PIL` pattern. The `igmt` command name itself is a placeholder pending a
pre-publish rename — see `TODO_DEFERRED.md`.)

- **`rosetta`** (engine for `show` / `inject`) — the analyzer/injector (this brief's subject).
- **`concordance`** (engine for `search`) — the prompt-search tool (currently
  `metadata-matching-dirs.py`), gaining a directory argument and fragment/exact search modes. See
  `briefs/concordance-search.md`.

**Tab completion via `argcomplete`.** The `igmt` entry script carries `# PYTHON_ARGCOMPLETE_OK` and
calls `argcomplete.autocomplete(parser)` before `parse_args()`. Completion derives from the live
parser (no static script to drift): `igmt <tab>` offers `search`/`show`/`inject` (and any future
subcommand automatically), `igmt show --<tab>` lists its flags. A custom completer restricts file
arguments to `*.png`. Users enable it once — globally (`activate-global-python-argcomplete`) or
per-command (`eval "$(register-python-argcomplete igmt)"` in their shell rc); bash and zsh.
Documented in the README.

**Lean dependencies (no Pillow).** We read everything from raw PNG chunks ourselves:
`prompt`/`workflow`/text from `tEXt`/`iTXt`, and image size straight from `IHDR` (width/height are
its first 8 data bytes). So the shared **`pngchunks`** module is a small dependency-free byte-level
read/splice/CRC implementation (CRC via `zlib.crc32`); it replaces the pypng usage in the current
script, and both tools import it. Runtime deps reduce to `simpleeval` (rosetta scalar resolver),
`argcomplete` (completion), and `chardet` (concordance's defensive non-UTF-8 decode). The
distribution ships both tools and the README. Lint/style/CI per the fleet conventions.

## Naming

The CLI surface is three descriptive verbs: **`igmt search`**, **`igmt show`**, **`igmt inject`**
(descriptive beats evocative for subcommands). The layered names live on as the *engine* modules:
**`rosetta`** (behind `show`/`inject`) and **`concordance`** (behind `search`, its own brief:
`briefs/concordance-search.md`). The full human-facing rationale — the Rosetta Stone, the deadpan
"no relation to Apple's Rosetta", and what a concordance is — lives in the project `README.md`,
where a reader will look for it. In short: `rosetta` makes a workflow legible to outside tools (one
message, many scripts); `concordance` indexes and searches the text inscribed across a corpus of
images, and is read-only by design (hence *not* `scribe`).

The toolkit/command name `igmt` (the project's initials) is a placeholder pending a pre-publish
evocative rename (see `TODO_DEFERRED.md`). Distribution name `imagegen-metadata-tools` stays.
