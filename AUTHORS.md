# Authors

*By fleet policy, both human and AI authors are listed.*

Juha Jeronen (@Technologicat):

- Author and maintainer: original concept, design, and architecture.
- Domain expertise: the ComfyUI / [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui) / [SD-Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge) metadata formats, the structure of ComfyUI workflow graphs, and CivitAI's resource auto-detection behavior (mapped by live testing).
- Direction, review of all AI-authored changesets, and live verification (CivitAI uploads, SD Prompt Reader, Pix).

Claude Opus 4.8 (Anthropic), as AI pair programmer:

- Implementation of the `chandra` CLI and its three engines — `rosetta` (`show`/`inject`/`eject`), `concordance` (`search`), and `palimpsest` (`scrub`).
- The dependency-free PNG chunk surgery, the recipe graph-walk and synthesizer, AutoV2 resource hashing, XMP description embedding, and the scrub anonymizer.
- The test suite and the documentation (README and design briefs).
