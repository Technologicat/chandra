# Brief: ComfyUI → CivitAI/A1111 metadata injector

*Working title for the tool: TBD (bikeshed at end). This document is the design brief; it
precedes implementation.*

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
- Values we cannot resolve are reported as absent, never guessed. We do **not** fall back to the
  filename prefix (it encodes seed/model/sampler/steps/cfg, but a rename destroys it).

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
     (`TextEncodeQwenImageEditPlus`, which also ingests the reference image);
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
   Prompt Reader itself uses. No need to trace latent-image nodes.

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

A sampler scalar (`steps`, `denoise`, `cfg`, `seed`, …) may be a literal or a link. In img2img the
`Evaluate*` nodes implement SD-Forge-style **dynamic step scaling** — effective steps ≈
`steps × denoise` — so the value reaching the sampler is the *effective* count it actually ran.

> **Reporting choice:** we report the **effective** steps (the resolved sampler input = what
> executed), not a separate configured-steps + denoise pair. This diverges from SD Forge's metadata
> convention (which reports configured steps), but it is what the graph actually contains and what
> the image actually used — consistent with the honest-reporting principle. Denoise is still
> reported alongside.

Resolution:

1. **Literal** → use it.
2. **Link to a Primitive role** (`PrimitiveInt`/`PrimitiveFloat`/…) → read `value`.
3. **Link to an `Evaluate Integers`/`Evaluate Floats` role** → it carries
   `python_expression` (e.g. `'a * b'`) over operands `a`/`b`/`c` that are themselves
   literals-or-links. Resolve operands recursively, then evaluate the expression in a **sandboxed
   arithmetic evaluator** (Python `ast`, numeric/operator nodes only — no names, calls, or
   attributes).
4. **Otherwise** → unresolved → field reported absent (honest fallback).

Recursion is depth-bounded with cycle detection (graphs are DAGs, but a malformed file shouldn't
hang us).

## Resource hashing (CivitAI auto-linking) — optional

Decision: **name + settings always; hashing is opt-in.**

- Default: emit `Model:` and LoRA names as text. CivitAI shows them; it cannot auto-link without
  hashes.
- `--hash`: compute **AutoV2** hashes from the actual model/LoRA files and emit `Model hash:` /
  `Lora hashes:`, enabling CivitAI page links. Requires the files to be locally accessible.
  - A configurable models directory (or several) is scanned to resolve a `ckpt_name`/`lora_name`
    (a bare filename in the graph) to a file on disk.
  - A persistent **hash cache** keyed by (path, size, mtime) — hashing multi-GB files is slow and
    we process batches of hundreds of images sharing the same few models.
  - Graceful fallback: a file we can't locate → that resource stays name-only; we warn, we don't
    fail.

> **Verification owed:** the exact AutoV2 spec (which hash, how many hex chars, model vs. LoRA
> field) is to be confirmed against CivitAI before we ship hashing. Stated belief: AutoV2 = first N
> hex chars of the file's SHA-256. Confirm N and the `Lora hashes`/`Hashes` field formats with a
> live upload.

## CLI design

- **Default output: in-place, no backup** (per user decision). The chunk insertion is lossless
  surgery (below); the original image bytes and existing chunks are preserved verbatim.
- Batch-first: accept files and/or directories (recurse), mirroring the existing
  `metadata-matching-dirs.py` ergonomics for sessions of hundreds of images.
- Idempotent: re-running on an already-injected image replaces the `parameters` chunk, doesn't
  stack duplicates.
- Flags (initial): `--hash` (+ `--models-dir`), `--dry-run` (print the synthesized string, write
  nothing), `--force`/skip-if-present policy, verbosity. A `--print`/inspect mode that dumps the
  parsed `Recipe` aids debugging and doubles as the analysis entry point.

## PNG chunk surgery (lossless injection)

We do **not** re-encode via Pillow (that recompresses IDAT and drops/rewrites text chunks).
Instead we operate at the chunk level — the approach already proven in `metadata-matching-dirs.py`:
read the chunk stream, and splice a new `tEXt` chunk (keyword `parameters`) immediately before
`IEND`, recomputing its CRC. Image data and the `prompt`/`workflow` chunks are byte-for-byte
untouched. On re-injection, replace an existing `parameters` chunk in place.

(The `workflow` chunk, which the user annotates with Markdown comments documenting model/quant
choices, is thereby preserved — those comments survive injection.)

## Verification plan

1. **Round-trip through SD Prompt Reader** (it's installed at `~/stable-diffusion-prompt-reader/`):
   feed each injected sample through its `ImageDataReader`, assert tool = "ComfyUI (A1111
   compatible)" and that positive/negative/settings match the `Recipe`. This is automatable in the
   test suite against the parser directly.
2. **Live CivitAI upload** of a representative injected image per family/mode; confirm prompt,
   settings, and (with `--hash`) resource links are detected. Manual, but the acceptance gate.
3. **PNG integrity:** `pngcheck` (installed) on every output; assert no warnings and that
   `prompt`/`workflow`/IDAT are unchanged.

## Tests & fixtures

- Promote a curated subset of `00_stuff/` into `tests/fixtures/` (one PNG per family×mode). The
  full `00_stuff/` dump (~28 MB) stays out of version control.
- Unit tests on `Recipe` extraction per fixture (the invariant: this graph → these fields),
  the scalar resolver (literal/primitive/evaluate/unresolved), and chunk surgery (insert, replace,
  idempotency, `pngcheck` clean).
- Integration test through SD Prompt Reader's parser as in *Verification plan* step 1.

## Non-goals (v1)

- No metadata for non-ComfyUI sources (we read ComfyUI `prompt`/`workflow`; A1111-origin images
  already have `parameters`).
- No JPEG/WEBP output (PNG-first; the EXIF path exists in SD Prompt Reader if needed later).
- No editing/round-tripping of the ComfyUI graph itself — we only *read* it and *add* a chunk.
- No attempt to faithfully evaluate arbitrary `Evaluate*` Python expressions beyond sandboxed
  arithmetic; exotic expressions resolve to "absent".

## Project shape

Pure-Python PDM project (per the fleet's standard setup). The existing `metadata-matching-dirs.py`
becomes one tool in the package; the new injector is the second. Shared PNG-chunk code is factored
into a common module. Lint/style/CI per the fleet conventions.

## Bikeshed: name

The tool reconstructs the generation recipe from the graph and re-expresses it in a script both
external readers understand — same content, different writing system. Candidates:

- **`rosetta`** — Rosetta Stone: one message, multiple scripts, mutually legible. Surface meaning
  holds (it makes the workflow legible to outside tools), layered reference rewards the curious.
- **`civitize`** — verb, "make CivitAI-readable." Clear, but brand-tethered and narrower than what
  it does (it also serves SD Prompt Reader / any A1111 reader).
- plain **`comfy2a1111`** — does what it says; no charm.

Leaning `rosetta` for the analyzer/injector command; package name `imagegen-metadata-tools` stays.
Final call is the user's.
