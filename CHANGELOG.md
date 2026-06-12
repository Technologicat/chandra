# Changelog

All notable user-visible changes to **chandra** are documented here.

This project adheres to [semantic versioning](https://semver.org/). Dates are ISO 8601 (YYYY-MM-DD).

---

## 0.2.0 (in progress)

*No user-visible changes yet.*

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
