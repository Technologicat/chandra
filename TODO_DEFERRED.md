# Deferred TODOs

## Migrate license metadata to PEP 639 across the fleet

`imagegen-metadata-tools` declares its license the PEP 639 way: a `license = "BSD-2-Clause"` SPDX
expression plus `license-files`, and no legacy `License ::` trove classifier. The rest of the fleet
still uses the deprecated `license = { text = "..." }` form (unpythonic, mcpyrate, pyan, raven, …),
which recent build backends warn on and which is ambiguous for the bare `"BSD"` cases.

After this sprint, migrate the fleet projects to the PEP 639 SPDX form (SPDX expression +
`license-files`, drop the redundant `License ::` classifier).

Discovered during imagegen-metadata-tools setup (2026-06-08).

## rosetta: read-only `--print` mode (dump recipe without modifying the file)

The recipe dump (`analyze.format_recipe`) is useful on its own. Once injection is implemented, add
an explicit read-only mode (e.g. `--print` / `--dump`) that analyzes and prints the recipe without
writing anything — so inspection is a deliberate, non-mutating choice rather than today's
placeholder behavior (where `igmt rosetta` dumps because injection isn't wired yet). The brief
already lists `--print`; this tracks the implementation.

Discovered during the Analyze stage (2026-06-08).
