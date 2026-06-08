# Deferred TODOs

## Migrate license metadata to PEP 639 across the fleet

`imagegen-metadata-tools` declares its license the PEP 639 way: a `license = "BSD-2-Clause"` SPDX
expression plus `license-files`, and no legacy `License ::` trove classifier. The rest of the fleet
still uses the deprecated `license = { text = "..." }` form (unpythonic, mcpyrate, pyan, raven, …),
which recent build backends warn on and which is ambiguous for the bare `"BSD"` cases.

After this sprint, migrate the fleet projects to the PEP 639 SPDX form (SPDX expression +
`license-files`, drop the redundant `License ::` classifier).

Discovered during imagegen-metadata-tools setup (2026-06-08).

## Toolkit / command name (the `igmt` placeholder)

`igmt` is the initialism of imagegen-metadata-tools — fine as a short command, but not evocative.
Before publishing, consider an evocative rename (the project philosophy favors layered names). Theme
floated: an interpreter / seer of hidden lore — the tool reveals the true generation metadata that
services fail to read. Candidate: "Cassandra" (utters true readings; fitting that they go unheeded
until translated) — but mind the heavy collision with Apache Cassandra (search/PyPI confusion).
Decide just before publishing; a rename would touch the dispatcher command, the distribution name,
the console-script entry point, the README, and the argcomplete registration.

Discovered during the verb-subcommand rename (2026-06-08).
