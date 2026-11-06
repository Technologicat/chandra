# Brief: AI-provenance marking via IPTC Digital Source Type

*An extension to `rosetta` (`inject` / `eject` / `show`). This document is the design brief; it precedes implementation. Read `briefs/design/rosetta-metadata-injector.md` first, since this builds on its XMP layer.*

## Problem

A chandra-injected image carries its recipe in two layers: the A1111 `parameters` chunk and an XMP `dc:description`. Neither of them says *in a standard, machine-readable way* that the image was made with generative AI. Tools and platforms that look for that signal read a different field. Google recommends that creators of AI-generated images set it, and Wikimedia now extracts it. The ComfyUI graph in the file already proves the image is generated, but nothing outside the SD ecosystem can read that proof.

## The standard

- **Property:** `Iptc4xmpExt:DigitalSourceType`, in the IPTC Extension namespace `http://iptc.org/std/Iptc4xmpExt/2008-02-29/`. Its value is a URI from the IPTC Digital Source Type vocabulary. (exiftool calls it `XMP-iptcExt:DigitalSourceType`; Exiv2 calls it `Xmp.iptcExt.DigitalSourceType`.)
- **Relevant terms** (base `http://cv.iptc.org/newscodes/digitalsourcetype/`):
  - `trainedAlgorithmicMedia`: "Created using Generative AI".
  - `compositeWithTrainedAlgorithmicMedia`: "Edited using Generative AI". The vocabulary names inpainting and outpainting as examples; it has no separate term for either.
- C2PA reuses the same vocabulary in its actions, so the value carries over if C2PA support is ever added.
- **Newer and in scope to evaluate:** IPTC Photo Metadata Standard 2025.1 (Nov 2025) added *AI Prompt Information*, *AI Prompt Writer Name*, *AI System Used* and *AI System Version Used*. rosetta already resolves the prompt and the model, so these would be a natural second step. Their exact XMP property names and value types must come from the published spec. **Verify them before writing any code**; don't infer them from the display names.

## Mapping: resolve or abstain

The stamp follows rosetta's core principle. It's written only when the graph proves it, and otherwise left out.

| Graph | Value |
|---|---|
| Sampler with no input image feeding the latent or edit conditioning (txt2img) | `trainedAlgorithmicMedia` |
| Sampler with a loaded input image as the starting latent, an inpaint/outpaint mask, or edit-model conditioning | `compositeWithTrainedAlgorithmicMedia` |
| No sampler (background remover, pose detector, upscale-only, …) | **abstain**: write nothing |
| Anything the analyzer can't classify with confidence | **abstain** |

Two notes on the table:
- An img2img source that was itself AI-generated is still correctly "edited using Generative AI". chandra can't know where the input came from and doesn't need to.
- Don't reach for `algorithmicallyEnhanced` for the non-generative tool graphs. Background removal by segmentation isn't the camera-style enhancement that term describes, and guessing a nearby term breaks the abstain rule.

## Behaviour

- **`inject`** adds the property to the existing XMP packet, in the same `rdf:Description`, declaring the `Iptc4xmpExt` namespace. It's covered by the existing `chandra-rosetta` toolkit stamp.
- **`show`** displays the resolved value, or states that it abstained and why. Extend `--recipe` the same way.
- **`eject`** removes it together with the rest of chandra's XMP. The md5-identical inject→eject round trip must still hold.
- **Foreign values:** if the image already carries a `DigitalSourceType` written by another tool, leave it alone (the same rule as an unstamped `parameters` chunk), and overwrite it only under `--force`.

## Default: on (decided 2026-11-06)

On by default, with `--no-mark-ai` to turn it off, mirroring `--no-xmp`. If `--no-xmp` is given, this property is skipped too.

Rationale:
- It adds no information the file doesn't already reveal, since the embedded graph and the `parameters` chunk already show the image is generated. It's the honest-reporting principle applied to provenance.
- It matches platform guidance.
- The legislative environment points the same way. The EU AI Act's Article 50 transparency obligations ask for machine-readable marking of synthetic content. That obligation falls on providers, not on chandra's users, but it shows which way the default should go.

## Not in scope

- C2PA manifests and signing. The IPTC property is unsigned: any XMP writer can change it and any XMP-stripping tool removes it. Say so in the README section; it's a signal, not proof.
- Network lookups of any kind (the privacy-by-design rule stands).

## Verification

- Unit tests over the committed fixtures, one per row of the mapping table, including abstention on the `tools-*` fixtures.
- Round trip: inject → eject is byte-identical, with and without the new property.
- External readers: `exiftool -XMP-iptcExt:DigitalSourceType <png>` returns the full URI; check one viewer that surfaces it, if one is available locally.
- Foreign-value test: pre-stamp a fixture with a different `DigitalSourceType`, then confirm `inject` keeps it and `--force` replaces it.

## Docs

Add a short README subsection under "Injecting metadata", "Marking images as AI-generated", covering the two values, the abstain cases, and the unsigned-signal caveat. Add a changelog entry.

## Outcome (built 2026-11-06)

- **Foreign values went through a prerequisite change.** `inject` had no "leave unstamped alone" rule to mirror: it overwrote any `parameters` chunk and replaced any XMP packet wholesale. It now checks each layer for chandra's stamp, as `eject` does, skips a foreign one with a warning, and overwrites under a new `inject --force`. A foreign `DigitalSourceType` lives in a foreign packet, so it survives by the same rule. Merging our properties into a foreign packet was rejected: it needs a real XMP editor, and `eject` could no longer remove our part by dropping the chunk, which breaks the md5 round trip.
- **Classifier** (`analyze._classify_source`), in order:
  1. Follow the sampler's starting latent upstream (through further samplers, latent and pixel transforms, encoders). Reaching a loaded image → edited.
  2. An edit-conditioning node on any sampler of that chain whose upstream holds a loaded image → edited. Recognized by shape: `conditioning` + `latent` (`ReferenceLatent`); a text encoder with `image*` inputs (`TextEncodeQwenImageEdit*`); `positive` + `pixels` (`InpaintModelConditioning`, `InstructPixToPixConditioning`).
  3. The latent trail ended somewhere other than an empty-latent generator (a node with `batch_size`) → abstain.
  4. Any loaded image upstream of the output used other than as a guide (a post-sampling composite, say) → abstain, naming the consuming node's `class_type`. Guides are recognized by shape: a `control_net`, `ipadapter` or `style_model` input (ControlNet, IP-Adapter, Flux Redux), and the walk enters them only through the conditioning or model they pass on.
  5. Otherwise → created, the reason naming any guidance nodes.
- **Image guidance counts as created** (decided 2026-11-06): the guide image doesn't become part of the output, which is a regular generated image. Initially built to abstain, on the grounds that a tile ControlNet re-rendering a photo is closer to an edit; that case is accepted as "created".
- **Known gap:** an image source whose class name doesn't contain both "load" and "image", feeding only the conditioning, would read as "created". On the latent path the same node ends the trail without a `batch_size`, so that case abstains.
- **External readers:** exiftool isn't installed on the dev machine, so the exiftool test skips there; it runs wherever exiftool is present.
- **IPTC 2025.1 AI fields**, built as the second step the same day. Verified against the published spec (IPTC Photo Metadata Standard 2025.1 rev 1, 2025-11-26): all four are simple `Text`, cardinality 0..1, in the `Iptc4xmpExt` namespace above, with no IIM equivalent.
  - `Iptc4xmpExt:AIPromptInformation`: the prompts as labelled blocks, `Positive:` then `Negative:`, each only when non-empty (the spec's user note allows both). Decided 2026-11-06, over the A1111 `Negative prompt:` form, for readability without SD knowledge.
  - `Iptc4xmpExt:AISystemUsed`: the checkpoint name as the `parameters` chunk's `Model:` field shows it (`synthesize.display_name`). Decided 2026-11-06, over "ComfyUI" or "ComfyUI, <model>".
  - `Iptc4xmpExt:AIPromptWriterName`: never written; no graph records it. A user-supplied `--prompt-writer` was declined (2026-11-06), which keeps chandra from writing personal names into files.
  - `Iptc4xmpExt:AISystemVersionUsed`: never written; no graph records a version of anything.
  - All under the same `--no-mark-ai`. Written independently of the source type: a generation whose source type abstains still has a prompt and a model.
