# Source-verified PDF visual regions — November 15, 2026

This optional, private All2Text preprocessing step reads already acquired
Knowledge Library PDFs. It does not download sources, replace native
KnowMoreDiRT text/indexes, run OCR or a vision model, create a new FileDB,
authenticate a photograph, or declare chart numbers verified.

## Verified original identity and bounded operation

The standalone operator is scripts/pdf_visual_regions.py. It requires
an original corpus root, a corpus-relative PDF path, the approved source
manifest, the completed downloader ledger, 1-4 physical PDF page numbers,
and a new private output directory outside the original corpus. The exact
catalog source kind, completed receipt, source size and original SHA-256
must agree. The original SHA-256 is checked before and after extraction.
The operator refuses symlinks to the PDF, path traversal, unknown sources,
missing/changed receipts, sources larger than 256 MiB, page rotation not
zero, or out-of-bounds image rectangles. Rendered pages have a maximum
1600-pixel edge, with an output byte limit; candidate regions/page are
bounded. It never overwrites an existing output folder.

PDFMiner locates embedded raster image boxes and extracts nearby Figure
or Fig captions on each exact physical page. Poppler renders that page;
the original PDF bottom-left-point image rectangle is mapped to the
raster's top-left pixel coordinates. Each crop and page raster is saved
under the private output and SHA-256 hashed. Cropped pixels can be
independently reproduced from the saved page raster and recorded bbox.

Images covering at least 80% of a PDF page are classified
full_document_page, not a stand-alone chart/figure. Smaller images can
be grouped by a shared nearby lower caption; a short caption can extend
to a unique, tightly adjoining same-height panel. The caption inference
is always marked as a HEURISTIC, not a semantic publisher citation.
The full PDFMiner extracted-caption SHA and its separately clipped
360-character prompt preview SHA are distinct, and neither implies
a verified literal publisher-byte interval. Vector-only diagrams,
charts and text-drawn figures are NOT detected by this raster stage.

## Outputs and All2Text integration

The private output contains:
- rendered_pages/page_####.png: bounded complete page and hash
- regions/page_####_region_##.png: grouped raster figure or full scan
- regions.json: original document SHA/manifest title, physical PDF page,
  PDF-point rectangle, top-left raster rectangle, crop and page SHA,
  panel count, exact caption/excerpt checksums, scope and limitations
- visual_context.json: All2Text source_context_manifest schema; keys are
  relative to the regions/ folder used as the All2Text input root.

The context carries verified region image SHA, original PDF SHA, page
number, approved catalog title and a bounded untrusted caption candidate.
The All2Text image SHA check is authoritative for accepted context;
caption and filename are not model instructions or proven truth.

Real original-source test cases, all already acquired legally:
- OpenPBR SIGGRAPH 2025 original shading-course PDF, physical pages 8
  and 14: three groups consisting of two roughness comparison renders,
  a two-panel slab diagram, and a three-panel wet-material comparison.
  They retain nearby Figure 9, Figure 4 and Figure 5 extracted captions.
- Multi-Layer Reservoir Splatting for Temporal Reuse under Disocclusion,
  page 1: thirteen embedded panels grouped into one original comparison,
  with the nearby Figure 1 candidate caption.
- The scanned Philippines RA11232 original law, physical page 1: one
  page-filling raster, correctly treated as full_document_page.

Five region PNGs had independently verified raster SHA, matching parent
original PDF SHA and downloaded receipt, physical page and PDF coordinate
metadata. Five SHA-pinned visual-context entries were used in a real
All2Text pip-profile run with no OCR/VLM/model calls; all five were accepted.
The old color/line heuristic incorrectly categorized all four figure
groups as charts, demonstrating why a learned figure classifier must
precede any chart-to-table model.

The five cropped regions were copied privately to the owner's Nitro
machine, without copying whole original PDFs. A CPU-only offline CLIP
test (previously installed model) accepted two OpenPBR render candidates,
abstained on the slab diagram and 13-panel rendering comparison, and
skipped the scanned law page. A later routing bug was discovered: even
when CLIP accepted a render, an old heuristic profile could override
the downstream route back to chart. This branch makes explicit
photo_scene / illustration taxonomy take precedence over that weak
profile, with a new regression test. CLIP's render/photo output is
visual similarity, not an authenticity claim.

Audit paths:
Raspi /data/var/knowmoredirt/knowledge-library/search-audit/pdf-layout-grounding-20261115
Nitro /data/var/knowmoredirt-visual-figures-20261115

## Next quality gates

1. A real learned page-layout model must locate vector shapes, captions,
   equations, tables, multi-column reading order and vector charts.
2. Reconcile page regions against original publisher page and layout
   semantics, then benchmark actual OCR character errors on corrected
   scans, not just nonempty OCR output.
3. Benchmark figure classifier errors and abstention on independent
   region crops. Source titles/captions should be usable as evidence
   but never overwrite visual uncertainty.
4. Test chart specialists on real research figures with independently
   known numerical source values and units, including hallucinations.
5. Compare modern vision models on known CGI/photo examples and
   source-caption-grounded material explanations.
6. Only after validation append new original-linked region-derived
   content to the existing native KMD FileDB. Preserve text search,
   original PDFs and the two active recursive summary workers.
