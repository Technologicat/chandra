# Changelog

All notable user-visible changes to **chandra** are documented here.

This project adheres to [semantic versioning](https://semver.org/). Dates are ISO 8601 (YYYY-MM-DD).

---

## 0.4.0 (in progress)

### Added

- PyPy is now supported and tested, on both Python versions stable PyPy implements: 3.11 and 3.12.
- **`chandra inject` marks images as AI-generated with the IPTC Digital Source Type**, the standard field platforms read (`Iptc4xmpExt:DigitalSourceType`, in the XMP packet).
  - `trainedAlgorithmicMedia` ("Created using Generative AI") for a generation from an empty latent; `compositeWithTrainedAlgorithmicMedia` ("Edited using Generative AI") when an input image is encoded into the latent (img2img, inpainting), conditions an edit model, or is composited with the generated image after sampling.
  - An input image that only guides the generation (ControlNet, IP-Adapter, Flux Redux) still counts as created.
  - Where the graph doesn't prove either — no sampler, or an input image used some other way, such as a colour-match reference — nothing is written.
  - Also written, from IPTC Photo Metadata 2025.1: **AI Prompt Information** (the prompts, labelled `Positive:` / `Negative:`) and **AI System Used** (the generator, VAE and text encoder files, named as in the `parameters` chunk).
  - `chandra show` prints the source type, or why it abstained, and the AI system; `show --recipe` prints the source type too.
  - On by default. `--no-mark-ai` leaves all of them out.
  - An unsigned signal, not proof: any metadata tool can change or strip it.

### Changed

- `chardet` is no longer installed as a dependency; chandra never used it.
- **`chandra inject` now leaves metadata written by another tool in place.**
  - Up to v0.3.0, `inject` overwrote any existing `parameters` chunk, and replaced any existing XMP packet wholesale — destroying whatever another tool had put there (captions, rights information).
  - Each layer is now checked separately for chandra's stamp, like `eject` already did; a foreign one is skipped with a warning, and the other layer is still written.
  - `--force` overwrites them anyway.

### Fixed

- **A separate VAE is now named in stock ComfyUI graphs**, where a plain `KSampler` feeds a `VAEDecode`.
  - Up to v0.3.0 the VAE was found only on samplers that decode their own output (`KSampler (Efficient)`), so elsewhere `VAE:` was missing from the `parameters` chunk and the description.
- **A generated image composited onto another after sampling is now analyzed as a generation.**
  - Up to v0.3.0, a graph that pasted or blended its output into a loaded image (`ImageCompositeMasked`, or `ImageBlend` with the generated image second) was reported as having no sampler, so `show`/`inject` gave no recipe.

---

## 0.3.0 — First light — 2026-08-18

### Added

- Python 3.15 is now supported and tested.

---

## 0.2.0 — Earthshine — 2026-06-16

### Added

- ComfyUI images that aren't generations — background removers, pose detectors, upscalers, mask
  extractors, anything with no sampler — are now handled instead of rejected. There's no recipe to
  extract, so `chandra show`/`inject` describe the workflow's operation pipeline — one line per
  output image, since one workflow can write several (a background remover emits both the cut-out and
  its mask, by different paths):

  ```
  LoadImage → InspyrenetRembg → SaveImage
  LoadImage → InspyrenetRembg → MaskToImage → SaveImage
  ```

  That goes into both the `parameters` text and the XMP description, so SD Prompt Reader / CivitAI and
  general viewers (Pix) show something useful rather than nothing.

### Fixed

- `chandra inject` no longer crashes on a ComfyUI image with no resolvable prompt (a non-generation
  workflow, or a generation whose conditioning can't be traced). The XMP-description step raised
  `TypeError` on the missing prompt text.

---

## 0.1.1 — 2026-06-13

### Fixed

- `chandra inject`: the XMP description (the recipe general image viewers such as Pix show) now
  reports the same step count as the `parameters` chunk the SD tools read. A dynamic-steps chain that
  resolves to a fraction (e.g. 5.6) is truncated to the integer that actually ran (5); previously the
  `parameters` chunk truncated but the XMP showed the raw fraction, so the two layers disagreed.

### Internal

- CI hardened: all GitHub Actions pinned to commit SHAs and `GITHUB_TOKEN` scoped to least privilege.
- `chandra/xmp.py`: the XMP packet's byte-order-mark is now written as an explicit `\uFEFF` escape
  in the source rather than a literal (invisible) character. Output bytes are unchanged.

---

## 0.1.0 — 2026-06-11

Initial release.

`chandra` is a single command for the metadata AI image generators embed in their output. It walks
the ComfyUI workflow graph a PNG carries, reconstructs the generation recipe, and re-expresses it in
the AUTOMATIC1111 / SD-Forge `parameters` format that services and apps read robustly — covering the
img2img, inpaint, edit-mode, LoRA-chain, and non-standard-loader graphs those tools mostly punt on.

Subcommands:

- `chandra show` — read a ComfyUI image and print the A1111/CivitAI metadata `inject` would write.
  Read-only.
- `chandra inject` — write that metadata into the image(s) in place and losslessly: a machine-readable
  `parameters` chunk (for CivitAI on upload and SD Prompt Reader) and an XMP `dc:description` (for
  general image viewers). The original ComfyUI `prompt`/`workflow` chunks are never touched.
  `--hash` adds AutoV2 checkpoint/LoRA hashes so CivitAI auto-links the resources.
- `chandra eject` — remove that metadata again, the inverse of `inject`, leaving the original
  ComfyUI graph byte-intact.
- `chandra search` — search the prompts embedded across a directory tree of images; results pipe into
  `show`/`inject`/`eject` to act on exactly the matches.
- `chandra scrub` — strip an image to an anonymized structural skeleton (graph wiring kept; image,
  prompts, and identifying text removed), safe to share when reporting a parsing bug. Writes a copy.

Dependency-free PNG chunk surgery; the recipe synthesizer, graph walker, and scrub anonymizer are
pure Python. Tested on Linux, macOS, and Windows.
