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

Why this is useful: CivitAI and SD Prompt Reader both mostly *punt* on analyzing ComfyUI workflows —
a trivial txt2img graph is sometimes captured, but img2img, inpaint, edit-mode, LoRA chains, and
non-standard loaders are not. `igmt` walks the embedded ComfyUI graph itself, reconstructs the
recipe, and re-expresses it in the one format those tools read robustly.

## Searching

`igmt search` builds boolean queries from three primitives — no special syntax or metacharacters:

| | flag | example |
|---|---|---|
| **AND** | *(default)* | `igmt search cat photo` — prompt contains both fragments |
| **OR**  | `--any` (`--or`) | `igmt search --any captain admiral` — either fragment |
| **NOT** | `-v` (`--invert`, `--not`) | `igmt search -v klingon` — prompt lacks the fragment |

Fragments match as **substrings**, order-independent (`cat photo` also matches `photocatalytic`), and
are **smart-cased**: an all-lowercase fragment is case-insensitive, a fragment with any uppercase
letter is case-sensitive (`-i` forces insensitive).

It's a Unix filter — matching paths go to stdout, and when input is piped it reads candidate paths
from stdin. So **chaining refines**: each stage filters the previous stage's results (set
intersection), which gives full boolean in conjunctive normal form:

```bash
igmt search starship | igmt search --any captain admiral | igmt search -v klingon
#  →  starship AND (captain OR admiral) AND NOT klingon
```

…and results compose with the rest of the shell:

```bash
igmt search wizard -d imgs | wc -l                      # count matches
igmt search cat -d imgs | xargs -d'\n' cp -t picks/     # copy matches elsewhere
igmt search catgirl -d imgs | fzf                       # pick one interactively
```

More flags: `-p` / `-n` (search the positive / negative prompt only), `--exact` (match the whole
query as one contiguous phrase instead of fragments), `-C` / `--context` (print a highlighted snippet
of each match, colorized on a terminal), `--dirs-only` (print matching directories instead of files),
`-d DIR` (search roots, repeatable; default is piped stdin, else the current directory).

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

## Shell completion (optional)

`igmt` supports tab-completion via [argcomplete](https://github.com/kislyuk/argcomplete). Enable it
once by adding this to your `~/.bashrc` (or `~/.zshrc`):

```bash
eval "$(register-python-argcomplete igmt)"
```

Open a new shell (or `source` the file) and `igmt <TAB>` will complete subcommands and flags.

`register-python-argcomplete` ships with argcomplete. If `igmt` is installed inside a virtualenv, the
helper lives there too — to have it on `PATH` in every shell, install argcomplete globally with
`pipx install argcomplete`. (The *global* `activate-global-python-argcomplete` hook does **not** pick
up `igmt`: the installed console-script wrapper doesn't carry argcomplete's `# PYTHON_ARGCOMPLETE_OK`
marker, so per-command registration as above is the reliable way.)

**To disable it:** remove the `eval` line from your shell rc — and, to drop it from the current
shell immediately, run `complete -r igmt`. If you installed argcomplete solely for this,
`pipx uninstall argcomplete`.

## Status

The design briefs live under [`briefs/`](briefs/). All three subcommands work: `show`/`inject`
through the analyze → synthesize → inject pipeline (with optional `--hash` AutoV2 resource linking),
and `search` with fragment/exact modes and per-fragment smart-case. The standalone
[`metadata-matching-dirs.py`](metadata-matching-dirs.py) is the prototype `search` grew from. This
README will grow into full usage docs as the tools settle.
