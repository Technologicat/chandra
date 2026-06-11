# chandra

Tools for working with the metadata that AI image generators embed in their output.

For my stance on AI contributions, see the [collaboration guidelines](https://github.com/Technologicat/substrate-independent/blob/main/collaboration.md).

We use [semantic versioning](https://semver.org/).

## Overview

Everything is one command, **`chandra`**, with these subcommands:

| Command | What it does |
|---|---|
| `chandra show <png…>` | Read a ComfyUI image and **print** the [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui)/[SD-Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge) metadata that `chandra inject` *would* write. Read-only. |
| `chandra inject <png…>` | **Write** that metadata into the image(s), in place, so they're recognized by services and apps that don't analyze ComfyUI graphs — notably, [CivitAI](https://civitai.com) on upload, and [SD Prompt Reader](https://github.com/receyuki/stable-diffusion-prompt-reader) locally. |
| `chandra eject <png…>` | **Remove** that metadata again — the inverse of `inject`. Strips the `parameters` chunk and XMP description chandra wrote, leaving the original ComfyUI graph byte-intact. |
| `chandra search <terms…>` | Search the prompts embedded across a directory tree of generated images. |
| `chandra scrub <png…>` | Strip a ComfyUI image to an anonymized skeleton — graph wiring kept, image/prompts/docs removed — safe to share when reporting a parsing bug. Writes a copy; never modifies the original. |

Reading and writing are deliberately separate commands: `show` never modifies anything, and writing
only happens when you explicitly ask for `inject` (or `eject`, to undo it).

```bash
chandra show image.png                 # preview the synthesized metadata
chandra inject *.png                   # write metadata into a batch, in place
chandra inject imgs/                    # …or hand it a directory (recursed)
chandra eject *.png                     # remove that metadata again (inverse of inject)
chandra search starfleet captain       # find images whose prompt mentions a starfleet captain
chandra search catgirl -d imgs | chandra search -n blurry   # chain searches to refine the result set
chandra search catgirl -d imgs | chandra inject             # inject only the images a search found
```

Every command takes the same inputs: files and/or directories (directories are recursed), or a
list of paths piped in on stdin, one per line — which is what lets a `search` feed `show`, `inject`,
or `eject`. `search` takes its roots with `-d` (its positional arguments are the search terms); the
others take them as positional arguments. With nothing to act on, each command prints a short usage
instead of guessing: bare `chandra search` asks for terms, bare `chandra show` / `inject` / `eject`
ask for paths. The one convenience is that `search` (once it has terms) defaults its search root to
the current directory; the writing commands never default to the cwd — so a bare `chandra inject` or
`chandra eject` can't modify files there by surprise.

Why this is useful: many services and apps such as CivitAI and SD Prompt Reader mostly *punt* on
analyzing ComfyUI workflows — a trivial txt2img graph is sometimes captured, but img2img, inpaint,
edit-mode, LoRA chains, and non-standard loaders are not. `chandra` walks the embedded ComfyUI graph
itself, reconstructs the recipe, and re-expresses it in the one format those tools read robustly.

## Injecting metadata (`inject`)

### Auto-linking resources on CivitAI (`--hash`)

By default the checkpoint and LoRAs are named as plain text — readable by a human and by SD Prompt
Reader, but invisible to CivitAI, which keys its resource detection off hashes and surfaces nothing
without them. Add `--hash` (to `show` or `inject`) and `chandra` computes the AutoV2 hash
(`sha256[:10]`) of each file and emits `Model hash:` and `Lora hashes:`, which CivitAI matches to the
corresponding resource pages on upload:

```bash
chandra inject *.png --hash --models-dir ~/ComfyUI/models
```

Hashing needs the actual files, so you need to tell `chandra` where they live — either with
`--models-dir DIR` (repeatable) or via the **`CHANDRA_MODELS_DIR`** environment variable,
a `PATH`-style list of directories (colon-separated on Linux/macOS, semicolon on Windows):

```bash
export CHANDRA_MODELS_DIR=~/ComfyUI/models:~/extra/loras
chandra inject *.png --hash          # picks up the dirs from the environment
```

On Linux, to set the environment variable persistently, place the `export` command in your `.bashrc`.

The directories are indexed once and hashes are cached (keyed by path, size, and mtime), so a
multi-GB checkpoint shared across a batch is hashed only the first time. Only the checkpoint and
LoRAs auto-link on CivitAI — its detection covers nothing else.

The recipe also records the **VAE** (`VAE:`, plus `VAE hash:` under `--hash`) and any separate
**text encoders** — common on modern models (Flux, Qwen, …), often an LLM — as SD-Forge `Module N`
fields. CivitAI ignores both, but they're standard, faithful metadata that SD Prompt Reader, general
image viewers, and `chandra show --recipe` display; the text encoder in particular materially shapes
the result, so it's worth recording. Text encoders aren't hashed (no standard infotext hash field).

### Seeing the recipe in a general image viewer

`inject` also embeds a clean, human-readable rendering of the recipe — the same information as
`chandra show --recipe` — as an XMP `dc:description`. So a general image viewer that reads standard
metadata (e.g. [Pix](https://github.com/linuxmint/pix), the Linux Mint viewer) shows the prompt and
settings in its **Description** caption, no SD software needed — often enough to skip opening a
dedicated prompt reader just to glance at what made an image. This is on by default; pass `--no-xmp`
to write only the machine-oriented `parameters` chunk. The two layers are independent and both
lossless — the original ComfyUI `prompt`/`workflow` chunks are never touched.

LoRAs differ between the layers, by design. The machine `parameters` chunk renders them in A1111's
inline `<lora:name:strength>` notation — that's the format's idiom, and the only standard place a
LoRA's *strength* is recorded.

ComfyUI itself never writes LoRAs into the prompt text, so the human-readable views keep the prose
clean and list them separately (`LoRA: name (strength X)` in the description and `chandra show --recipe`).
The inlined-into-prompt form is a data interchange convention.

## Undoing an inject (`eject`)

Changed your mind? `chandra eject` is the inverse of `inject`: it removes the `parameters` chunk and
the XMP description, leaving the original ComfyUI `prompt`/`workflow` chunks byte-for-byte intact — an
`inject` followed by an `eject` restores the file exactly (byte-identical to the original, with the
same `md5sum`).

```bash
chandra eject *.png            # remove chandra's metadata from a batch, in place
```

By default `eject` removes **only metadata chandra wrote** — both layers carry a `chandra-rosetta`
stamp (the `Version:` field of the `parameters` chunk and the `x:xmptk` attribute of the XMP packet),
and anything unstamped is left alone, so it won't clobber a `parameters` block from A1111/Forge or an
XMP caption some other tool added. Two flags adjust that: `--no-xmp` removes only the `parameters`
chunk and leaves the XMP description; `--force` removes the `parameters` chunk and XMP regardless of
who wrote them.

## Searching (`search`)

`chandra search` builds boolean queries from three primitives — no special syntax or metacharacters:

| | flag | example |
|---|---|---|
| **AND** | *(default)* | `chandra search cat photo` — prompt contains both fragments |
| **OR**  | `--or` (`--any`) | `chandra search --or captain admiral` — either fragment |
| **NOT** | `--not` (`--invert`, `-v`) | `chandra search --not klingon` — prompt lacks the fragment |

Fragments match as **substrings**, order-independent: `cat photo` also matches `photocatalytic`.

Fragments are **smart-cased**: an all-lowercase fragment is case-insensitive, a fragment with
any uppercase letter is case-sensitive. The flag `-i` forces case-insensitive.

`chandra search` is a *nix-style filter — matching paths go to stdout, and when input is piped,
it reads candidate paths from stdin. So **chaining refines**: each stage filters the previous
stage's results (set intersection), which gives full boolean in conjunctive normal form:

```bash
chandra search starship | chandra search --or captain admiral | chandra search --not klingon
#  →  starship AND (captain OR admiral) AND (NOT klingon)
```

…and results compose with the rest of the shell:

```bash
chandra search wizard -d imgs | wc -l                      # count matches
chandra search cat -d imgs | xargs -d'\n' cp -t picks/     # copy matches elsewhere
chandra search catgirl -d imgs | fzf                       # pick one interactively
```

More flags:

- `-p` / `-n` search the positive / negative prompt only,
- `--exact` matches the whole query as one contiguous phrase instead of fragments),
- `-C` / `--context` prints a highlighted snippet of each match, colorized on a terminal,
- `--dirs-only` prints matching directories instead of files, and
- `-d DIR` sets the search roots, repeatable; default is piped stdin, else the current directory.

## On the names

**`chandra`** is Sanskrit for *the moon* (चन्द्र), the Hindu lunar deity. The metadata this tool
recovers is an image's nocturnal layer — dimmer than the bright pixels, easy to overlook, but there
to be read once you look for it. The name rewards a second glance: the astrophysicist *Subrahmanyan
Chandrasekhar* (of the [Chandrasekhar limit](https://en.wikipedia.org/wiki/Chandrasekhar_limit))
carries the same root — *Chandra·shekhar*, "moon-crested". No relation to the [X-ray Observatory](https://en.wikipedia.org/wiki/Chandra_X-ray_Observatory).

The engines under the hood carry their own names:

- **`rosetta`** powers `show`, `inject`, and `eject`. Named for the
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

## Installation

```bash
pipx install chandra
```

If desired later; to uninstall:

```bash
pipx uninstall chandra
```

## Shell completion (optional)

`chandra` supports tab-completion via [argcomplete](https://github.com/kislyuk/argcomplete). Enable it
once by adding this to your `~/.bashrc` (or `~/.zshrc`):

```bash
eval "$(register-python-argcomplete chandra)"
```

Open a new shell (or `source` the file) and `chandra <TAB>` will complete subcommands and flags.

`register-python-argcomplete` ships with argcomplete. If `chandra` is installed inside a virtualenv, the
helper lives there too — to have it on `PATH` in every shell, install argcomplete globally with
`pipx install argcomplete`.

The *global* `activate-global-python-argcomplete` hook does **not** pick up `chandra`: the installed
console-script wrapper doesn't carry argcomplete's `# PYTHON_ARGCOMPLETE_OK` marker, so per-command
registration as above is the reliable way.

**To disable it:** remove the `eval` line from your shell rc — and, to drop it from the current
shell immediately, run `complete -r chandra`. If you installed argcomplete solely for this,
`pipx uninstall argcomplete`.

## Contributing

Found a workflow `chandra` doesn't parse correctly? Bug reports (with an example image) and pull
requests are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

Two things up front: you can run `chandra scrub your.png` to produce an anonymized skeleton
(no image, no prompt text, just the graph wiring that reproduces the bug) to attach instead
of the original; and please keep any example images **SFW** (character art is fine), since
the issue tracker is public.

If you are interested in the technical design, architectural briefs live under [`briefs/`](briefs/).
