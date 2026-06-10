# chandra

Tools for working with the metadata that image generators embed in their output.

Everything is one command, **`chandra`**, with three subcommands:

| Command | What it does |
|---|---|
| `chandra show <png…>` | Read a ComfyUI image and **print** the [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui)/SD-Forge metadata that `chandra inject` *would* write. Read-only. |
| `chandra inject <png…>` | **Write** that metadata into the image(s), in place, so they're recognized by services that don't analyze ComfyUI graphs — notably [CivitAI](https://civitai.com) on upload and [SD Prompt Reader](https://github.com/receyuki/stable-diffusion-prompt-reader). |
| `chandra search <terms…>` | Search the prompts embedded across a directory tree of generated images. |

Reading and writing are deliberately separate commands: `show` never modifies anything, and writing
only happens when you explicitly ask for `inject`.

```bash
chandra show image.png                 # preview the synthesized metadata
chandra inject *.png                   # write metadata into a batch, in place
chandra inject imgs/                    # …or hand it a directory (recursed)
chandra search starfleet captain       # find images whose prompt mentions a starfleet captain
chandra search catgirl -d imgs | chandra search -n blurry   # chain searches to refine the result set
chandra search catgirl -d imgs | chandra inject             # inject only the images a search found
```

All three commands take the same inputs: files and/or directories (directories are recursed), or a
list of paths piped in on stdin, one per line — which is what lets a `search` feed `show` or `inject`.
`search` takes its roots with `-d` (its positional arguments are the search terms); `show` and
`inject` take them as positional arguments. With nothing to act on, each command prints a short usage
instead of guessing: bare `chandra search` asks for terms, bare `chandra show` / `chandra inject` ask
for paths. The one convenience is that `search` (once it has terms) defaults its search root to the
current directory; `show` and `inject` never default to the cwd — so a bare `chandra inject` can't
modify files there by surprise.

Why this is useful: CivitAI and SD Prompt Reader both mostly *punt* on analyzing ComfyUI workflows —
a trivial txt2img graph is sometimes captured, but img2img, inpaint, edit-mode, LoRA chains, and
non-standard loaders are not. `chandra` walks the embedded ComfyUI graph itself, reconstructs the
recipe, and re-expresses it in the one format those tools read robustly.

## Seeing the recipe in a general image viewer

`inject` also embeds a clean, human-readable rendering of the recipe — the same information as
`chandra show --recipe` — as an XMP `dc:description`. So a general image viewer that reads standard
metadata (e.g. [Pix](https://github.com/linuxmint/pix), the Linux Mint viewer) shows the prompt and
settings in its **Description** caption, no SD software needed — often enough to skip opening a
dedicated prompt reader just to glance at what made an image. This is on by default; pass `--no-xmp`
to write only the machine-oriented `parameters` chunk. The two layers are independent and both
lossless — the original ComfyUI `prompt`/`workflow` chunks are never touched.

## Searching

`chandra search` builds boolean queries from three primitives — no special syntax or metacharacters:

| | flag | example |
|---|---|---|
| **AND** | *(default)* | `chandra search cat photo` — prompt contains both fragments |
| **OR**  | `--any` (`--or`) | `chandra search --any captain admiral` — either fragment |
| **NOT** | `-v` (`--invert`, `--not`) | `chandra search -v klingon` — prompt lacks the fragment |

Fragments match as **substrings**, order-independent (`cat photo` also matches `photocatalytic`), and
are **smart-cased**: an all-lowercase fragment is case-insensitive, a fragment with any uppercase
letter is case-sensitive (`-i` forces insensitive).

It's a Unix filter — matching paths go to stdout, and when input is piped it reads candidate paths
from stdin. So **chaining refines**: each stage filters the previous stage's results (set
intersection), which gives full boolean in conjunctive normal form:

```bash
chandra search starship | chandra search --any captain admiral | chandra search -v klingon
#  →  starship AND (captain OR admiral) AND NOT klingon
```

…and results compose with the rest of the shell:

```bash
chandra search wizard -d imgs | wc -l                      # count matches
chandra search cat -d imgs | xargs -d'\n' cp -t picks/     # copy matches elsewhere
chandra search catgirl -d imgs | fzf                       # pick one interactively
```

More flags: `-p` / `-n` (search the positive / negative prompt only), `--exact` (match the whole
query as one contiguous phrase instead of fragments), `-C` / `--context` (print a highlighted snippet
of each match, colorized on a terminal), `--dirs-only` (print matching directories instead of files),
`-d DIR` (search roots, repeatable; default is piped stdin, else the current directory).

## On the names

**`chandra`** is Sanskrit for *the moon* (चन्द्र), the Hindu lunar deity. The metadata this tool
recovers is an image's nocturnal layer — dimmer than the bright pixels, easy to overlook, but there
to be read once you look for it. The name rewards a second glance: the astrophysicist *Subrahmanyan
Chandrasekhar* (of the [Chandrasekhar limit](https://en.wikipedia.org/wiki/Chandrasekhar_limit))
carries the same root — *Chandra·shekhar*, "moon-crested" — and NASA's
[Chandra X-ray Observatory](https://en.wikipedia.org/wiki/Chandra_X-ray_Observatory), named in his
honour, exists to image the **invisible** sky. Reading what's present but unseen is the whole job.

The two engines under the hood keep their own names (you'll meet them in the source):

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

## Shell completion (optional)

`chandra` supports tab-completion via [argcomplete](https://github.com/kislyuk/argcomplete). Enable it
once by adding this to your `~/.bashrc` (or `~/.zshrc`):

```bash
eval "$(register-python-argcomplete chandra)"
```

Open a new shell (or `source` the file) and `chandra <TAB>` will complete subcommands and flags.

`register-python-argcomplete` ships with argcomplete. If `chandra` is installed inside a virtualenv, the
helper lives there too — to have it on `PATH` in every shell, install argcomplete globally with
`pipx install argcomplete`. (The *global* `activate-global-python-argcomplete` hook does **not** pick
up `chandra`: the installed console-script wrapper doesn't carry argcomplete's `# PYTHON_ARGCOMPLETE_OK`
marker, so per-command registration as above is the reliable way.)

**To disable it:** remove the `eval` line from your shell rc — and, to drop it from the current
shell immediately, run `complete -r chandra`. If you installed argcomplete solely for this,
`pipx uninstall argcomplete`.

## Design briefs

The design briefs live under [`briefs/`](briefs/).
