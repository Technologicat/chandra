# Deferred TODOs

## Migrate license metadata to PEP 639 across the fleet

`imagegen-metadata-tools` declares its license the PEP 639 way: a `license = "BSD-2-Clause"` SPDX
expression plus `license-files`, and no legacy `License ::` trove classifier. The rest of the fleet
still uses the deprecated `license = { text = "..." }` form (unpythonic, mcpyrate, pyan, raven, …),
which recent build backends warn on and which is ambiguous for the bare `"BSD"` cases.

After this sprint, migrate the fleet projects to the PEP 639 SPDX form (SPDX expression +
`license-files`, drop the redundant `License ::` classifier).

Discovered during imagegen-metadata-tools setup (2026-06-08).
