"""AutoV2 resource hashing for CivitAI auto-linking.

CivitAI links a checkpoint/LoRA to its model page by hash. The ComfyUI graph stores only filenames,
so to emit `Model hash:` / `Lora hashes:` we must locate the actual files and hash them.

**AutoV2 = the first 10 hex chars of the file's SHA-256** — confirmed live against CivitAI's public
`by-hash` API (the SD 1.5 checkpoint's `SHA256` is `6CE0161689B385…` and its `AutoV2` is
`6CE0161689`). We use it for both checkpoints and LoRAs (one scheme; LoRA files resolve the same way
via by-hash). Lookups are case-insensitive; we emit lowercase.

Two helpers make batches cheap:

- `ResourceResolver` indexes the configured model directories *once* (basename → paths), so resolving
  a graph name like ``qwen/style/foo.safetensors`` to a file on disk is a dict lookup, not a walk per
  image. The full relative path is preferred when several files share a basename.
- `HashCache` persists `(path, size, mtime) → AutoV2` to disk, so the same multi-GB checkpoint shared
  across hundreds of images is hashed once, ever.

Everything degrades gracefully: a file we can't locate stays name-only (the caller warns, never fails).
"""

import hashlib
import json
import os
from pathlib import Path

__all__ = ["autov2", "ResourceResolver", "HashCache", "apply_hashes", "cache_path"]

_AUTOV2_LEN = 10
_READ_CHUNK = 1024 * 1024


def autov2(file_path) -> str:
    """The AutoV2 hash (first 10 hex chars of SHA-256, lowercase) of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(_READ_CHUNK), b""):
            h.update(block)
    return h.hexdigest()[:_AUTOV2_LEN]


def _basename(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


class ResourceResolver:
    """Resolve a ComfyUI resource name (bare filename or relative path) to a file on disk.

    Indexes the given model directories once. `resolve` prefers a path whose tail matches the full
    relative name; otherwise it falls back to the basename.
    """

    def __init__(self, models_dirs):
        self._by_basename = {}
        for d in models_dirs:
            if not d or not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    self._by_basename.setdefault(fn, []).append(os.path.join(root, fn))

    def resolve(self, name):
        if not name:
            return None
        norm = name.replace("\\", "/")
        candidates = self._by_basename.get(_basename(norm))
        if not candidates:
            return None
        for c in candidates:  # prefer a path that ends with the full relative name
            if c.replace("\\", "/").endswith(norm):
                return c
        return candidates[0]  # basename-only fallback


def cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "chandra" / "hashes.json"


class HashCache:
    """Persistent (path, size, mtime) → AutoV2 cache, so big files are hashed at most once."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else cache_path()
        self._data = {}
        self._dirty = False
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, ValueError):
            self._data = {}

    def autov2(self, file_path):
        """AutoV2 of the file, using the cache when (size, mtime) are unchanged. None if unreadable."""
        p = Path(file_path)
        try:
            st = p.stat()
        except OSError:
            return None
        key = str(p.resolve())
        entry = self._data.get(key)
        if entry and entry.get("size") == st.st_size and entry.get("mtime_ns") == st.st_mtime_ns:
            return entry["autov2"]
        digest = autov2(p)
        self._data[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "autov2": digest}
        self._dirty = True
        return digest

    def save(self):
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f)
        self._dirty = False


def apply_hashes(recipe, resolver: ResourceResolver, cache: HashCache):
    """Fill `recipe.model_hash`, `recipe.vae_hash`, and each `lora.hash` in place. Returns warnings."""
    warnings = []
    if recipe.model:
        path = resolver.resolve(recipe.model)
        if path:
            recipe.model_hash = cache.autov2(path)
        else:
            warnings.append(f"model file not found for hashing: {recipe.model!r}")
    if recipe.vae:
        path = resolver.resolve(recipe.vae)
        if path:
            recipe.vae_hash = cache.autov2(path)
        else:
            warnings.append(f"VAE file not found for hashing: {recipe.vae!r}")
    for lora in recipe.loras:
        if not lora.name:
            continue
        path = resolver.resolve(lora.name)
        if path:
            lora.hash = cache.autov2(path)
        else:
            warnings.append(f"LoRA file not found for hashing: {lora.name!r}")
    return warnings
