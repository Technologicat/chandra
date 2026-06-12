# Deferred TODOs

## Pix writes a `.comments` sidecar dir for chandra-injected images

Once an image carries our XMP `dc:description`, Pix automatically creates a `.comments/` sidecar
directory alongside it (its own comment cache) when it ingests the file. The metadata itself shows
correctly in Pix's Comment panel and XMP Embedded → Description; the sidecar is purely a Pix-side
behavior, and no Pix setting was found to disable it. Investigate whether our XMP packet can be
shaped to avoid triggering Pix's sidecar cache (or document it as expected Pix behavior).

Discovered during live testing (2026-06-11).
