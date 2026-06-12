"""Render a `Recipe` as an AUTOMATIC1111 / SD-Forge `parameters` string.

This is what gets injected as the PNG `parameters` chunk, so CivitAI and SD Prompt Reader read the
recipe via their robust A1111 path instead of their flaky ComfyUI path. The format is dictated by
SD Prompt Reader's `A1111` parser (`format/a1111.py`):

    <positive prompt>
    Negative prompt: <negative>
    Steps: N, Sampler: ..., Schedule type: ..., CFG scale: ..., Seed: ..., Size: WxH, Model: ..., Version: ...

Rules that shape the output: the settings block is found by the first ``\\nSteps:``; the negative is
delimited by ``\\nNegative prompt:``; settings are comma-separated ``Key: value`` pairs parsed as
``([^:,]+):\\s*([^,]+)`` — so a value may contain neither a comma nor (in the key) a colon. We keep
values comma-free (model/LoRA names are basenamed; commas don't occur in them in practice).

Honest reporting: negatives are emitted even at CFG 1 (turbo models run there with an inert
negative); fields we couldn't resolve are omitted, never guessed.
"""

from . import TOOL_TAG, __version__
from .analyze import format_steps

__all__ = ["synthesize"]

# Extensions stripped from model/LoRA filenames for the displayed name (A1111 convention).
_MODEL_EXTS = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin")


def _basename_no_ext(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1]
    low = base.lower()
    for ext in _MODEL_EXTS:
        if low.endswith(ext):
            return base[:-len(ext)]
    return base


def _num(x) -> str:
    """Format a number compactly: drop a trailing .0 (7.0 -> '7'), keep real fractions (4.5)."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def synthesize(recipe, version: str = None) -> str:
    """Render `recipe` as an A1111/SD-Forge `parameters` string."""
    if version is None:
        version = __version__

    # Positive prompt, with any LoRAs expressed in A1111's inline `<lora:name:weight>` idiom
    # (appended to the last prompt line, not dangling on a new line after a trailing newline).
    positive = (recipe.positive or "").rstrip()
    lora_tags = "".join(
        f" <lora:{_basename_no_ext(lora.name)}:{_num(lora.strength) if lora.strength is not None else '1'}>"
        for lora in recipe.loras if lora.name
    )
    parts = [(positive + lora_tags).strip()]

    if recipe.negative:  # emit even when inert (cfg 1) — honest; omit only when truly absent/empty
        parts.append(f"Negative prompt: {recipe.negative}")

    # Settings line. Steps must come first: SD Prompt Reader locates the block by "\nSteps:".
    settings = []
    if recipe.steps is not None:
        settings.append(f"Steps: {format_steps(recipe.steps)}")
    if recipe.sampler_name:
        settings.append(f"Sampler: {recipe.sampler_name}")
    if recipe.scheduler:
        settings.append(f"Schedule type: {recipe.scheduler}")
    if recipe.cfg is not None:
        settings.append(f"CFG scale: {_num(recipe.cfg)}")
    if recipe.seed is not None:
        settings.append(f"Seed: {recipe.seed}")
    if recipe.width and recipe.height:
        settings.append(f"Size: {recipe.width}x{recipe.height}")
    if recipe.model:
        if recipe.model_hash:  # AutoV2 — lets CivitAI link the checkpoint to its page
            settings.append(f"Model hash: {recipe.model_hash}")
        settings.append(f"Model: {_basename_no_ext(recipe.model)}")
    # VAE: its own A1111-standard pair (the slot SD Prompt Reader and humans read). Name always; hash
    # only with --hash — mirroring Model hash:/Model:. CivitAI doesn't auto-link VAEs from the hash as
    # it does checkpoints/LoRAs (tested), but the hash stays for file identity and consistency.
    if recipe.vae:
        if recipe.vae_hash:
            settings.append(f"VAE hash: {recipe.vae_hash}")
        settings.append(f"VAE: {_basename_no_ext(recipe.vae)}")
    # Text encoders → Forge's `Module N` (1-indexed, basename without extension). Modern models load
    # the text encoder from its own file — often an LLM — which a plain `Model:` field has no slot for;
    # there's no standard hash field for these, so they go name-only (the VAE has its own pair above).
    for i, name in enumerate(recipe.text_encoders):
        settings.append(f"Module {i + 1}: {_basename_no_ext(name)}")
    # Denoising strength: emit only when it actually reduced denoise (Forge omits it at 1.0 / txt2img).
    if recipe.denoise is not None and float(recipe.denoise) != 1.0:
        settings.append(f"Denoising strength: {_num(recipe.denoise)}")
    # Lora hashes: A1111's quoted form. The value carries commas/colons, so it goes late (after the
    # fields SDPR displays); SDPR's simple parser mangles it into ignored keys, while CivitAI's
    # quote-aware parser reads it and links each LoRA.
    hashed = [(_basename_no_ext(lora.name), lora.hash) for lora in recipe.loras if lora.name and lora.hash]
    if hashed:
        settings.append('Lora hashes: "' + ", ".join(f"{name}: {h}" for name, h in hashed) + '"')
    settings.append(f"Version: {TOOL_TAG} {version}")

    if settings:
        parts.append(", ".join(settings))
    return "\n".join(parts)
