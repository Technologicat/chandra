# imagegen-metadata-tools

Tools for working with the metadata that image generators embed in their output.

Everything is one command, **`igmt`**, with three subcommands:

| Command | What it does |
|---|---|
| `igmt show <png…>` | Read a ComfyUI image and **print** the [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui)/SD-Forge metadata that `igmt inject` *would* write. Read-only. |
| `igmt inject <png…>` | **Write** that metadata into the image(s), in place, so they're recognized by services that don't analyze ComfyUI graphs — notably [CivitAI](https://civitai.com) on upload and [SD Prompt Reader](https://github.com/receyuki/stable-diffusion-prompt-reader). |
| `igmt search <terms…>` | Search the prompts embedded across a directory tree of generated images. |

Reading and writing are deliberately separate commands: `show` never modifies anything, and writing
only happens when you explicitly ask for `inject`.

```bash
igmt show image.png                 # preview the synthesized metadata
igmt inject *.png                   # write metadata into a batch, in place
igmt search starfleet captain       # find images whose prompt mentions a starfleet captain
igmt search catgirl -d imgs | igmt search -n blurry   # chain searches to refine the result set
```

`igmt search` is a Unix filter — it prints matching paths and reads candidate paths from stdin when
piped, so you can refine results by chaining (and pipe them into `wc -l`, `xargs`, `fzf`, …). Within a
stage, fragments are ANDed; `--any`/`--or` makes them OR and `-v`/`--not` negates the stage, so a
pipeline expresses full boolean — e.g. `igmt search starship | igmt search --any captain admiral |
igmt search -v klingon` is *starship AND (captain OR admiral) AND NOT klingon*. Add `-C`/`--context`
for a highlighted snippet of each match.

Why this is useful: CivitAI and SD Prompt Reader both mostly *punt* on analyzing ComfyUI workflows —
a trivial txt2img graph is sometimes captured, but img2img, inpaint, edit-mode, LoRA chains, and
non-standard loaders are not. `igmt` walks the embedded ComfyUI graph itself, reconstructs the
recipe, and re-expresses it in the one format those tools read robustly.

## On the names

The command, `igmt`, is just the project's initials — short to type. The interesting names belong to
the two engines under the hood (you'll meet them in the source):

- **`rosetta`** powers `show` and `inject`. Named for the
  [Rosetta Stone](https://en.wikipedia.org/wiki/Rosetta_Stone), which carries one message in several
  scripts so a reader of any one of them can understand it. This engine does the same for a
  generation recipe: it takes what ComfyUI wrote in its own dialect and re-expresses it in the
  dialect CivitAI and SD Prompt Reader read fluently. (No relation to Apple's Rosetta.)

- **`concordance`** powers `search`. A
  [concordance](https://en.wikipedia.org/wiki/Concordance_(publishing)) is an alphabetical index of
  the words in a text or corpus together with where each one occurs — biblical and Shakespearean
  concordances are the classic examples. Searching the prompts across a folder of images is the same
  operation over a corpus of pictures. It only reads — its report goes to your terminal, never into
  the files — which is why it isn't called `scribe`.

## Status

The design briefs live under [`briefs/`](briefs/). All three subcommands work: `show`/`inject`
through the analyze → synthesize → inject pipeline (with optional `--hash` AutoV2 resource linking),
and `search` with fragment/exact modes and per-fragment smart-case. The standalone
[`metadata-matching-dirs.py`](metadata-matching-dirs.py) is the prototype `search` grew from. This
README will grow into full usage docs as the tools settle.
