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
