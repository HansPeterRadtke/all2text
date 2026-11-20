# Source-grounded visual conversion: November 15, 2026

Scope: audit All2Text, identify old actual vision models, test classification
on original technical-image fixtures and original-linked Knowledge Library
PDF pages, and implement a bounded, contextual routing pilot. This does not
replace the existing Knowledge Library source text or original native
KnowMoreDiRT FileDB; no models, source documents, or services were modified.

## Original All2Text architecture and actual limitations

The existing All2Text (Raspi /data/src/github/all2text, commit 589088d)
implements scan -> plan -> format-detect -> backend conversion -> mirrored
plain-text outputs/JSON report. It has safe text/Office/HTML/ZIP/metadata
backends, and many potential OCR/VLM/diagram/chart providers, but only a
subset has executable adapters and model weights.

Current PDF backend relies on optional pypdf native text and does not itself
render and understand images. On Raspi pypdf and pytesseract are missing from
both tested Python environments. A November no-install test on local copies
of both visual-only PDFs therefore returned metadata placeholders without
document-text extraction or OCR. The old VLM default was
Qwen2.5-VL-3B-Instruct-Q4-K-M at localhost port 14830 with auto_invoke=false;
the text LLM Qwen2.5-14B was likewise not automatically invoked. A generic
visible-evidence prompt included only image file label and approximate type.
Chart specialist and Docling document-intelligence adapters default to
disabled. The existing geometry/color heuristic labels any page containing
horizontal and vertical dark lines and enough colored pixels as a chart,
which is not an accurate content classification method.

Prior May 2026 RAG image experiments used real BLIP Base captions,
CLIP ViT-B/32 image categories, Google DePlot chart-to-table and Tesseract
OCR on 20 separately labeled technical images: BLIP 20, CLIP 20, DePlot 5,
OCR 17, Qwen VLM actual calls ZERO. Old recorded semantic LLM-judge average
80.45/100 was an internal semantic judge score and is NOT objective visual
description or numerical-chart accuracy. On Nitro those three old BLIP,
CLIP, DePlot model directories still exist (about 945 MB, 581 MB and 2.2GB).
The old devtest code includes specialized chart/technical routing not yet
fully ported to All2Text.

## Independent observed failures

The pre-existing 20-image technical benchmark has human-authored independent
target descriptions. Our November category review assigned five chart-like
images (including a heatmap), seven diagrams, three technical drawings,
two maps, one webpage screenshot and two illustrations. Label boundary
cases require independent secondary annotation and should not be treated
as universal truth. Old All2Text predicted 17 charts, two diagrams and one
document page; this means 5 correct chart hits, 12 false-positive charts
and zero missed charts. Chart precision = 5 / 17 = 29.41% on this specific
nonrepresentative sample. No VLM or OCR ran in the deterministic test.

Nine separate full PDF raster pages from actual first-party articles, a
cloth paper and Philippines scanned law were also evaluated. Before
correction, eight complete pages were called diagrams and one scanned law
page was called a chart. None were isolated chart figures, so this shows
why document layout/page roles must be known before classifying content
within it. Original PDF path/page/SHA and raster SHA are recorded privately.

Tesseract English on separately rendered opening pages at 150 DPI recovered
841 characters from the scanned law and 4199 characters from the cloth
paper. Both remain visual-only extraction exceptions in current KMD.
These numbers do not indicate correct full-page reading order, figure
semantics, full-document text, table values, or verified equations.

## Implemented All2Text pilot

New all2text.visual_prompt creates role-specific evidence-only prompts:
chart requires axes/units/legend and strictly visible numeric values;
diagram requires labeled nodes, arrows and flow relationships; table
requires literal row and column connections; document page requires
layout/reading-order analysis before figure extraction; photo/render scene
requires material roughness, lighting, contact shadows and plausible
image-formation artifacts with uncertainty. It must never infer that a
picture is a real photograph from visual plausibility alone.

Optional per-image context can be supplied through a separate local TOML
config, modules.image.source_context_manifest, containing a JSON
all2text.visual_context.v1 schema. For each original-image-relative path
the manifest supplies image_sha256, region_role, physical_page, document_topic,
section_heading, figure_caption and nearby_text. It is capped at 2 MiB and
10,000 entries, must live outside source and target folder trees, cannot
have unsafe relative paths or symlink target, and requires exact full
image-byte SHA before use. A stale/modified original image does not inherit
its old context; that case is logged as a rejection. Each accepted context
also has its own SHA-256, with an explicit warning that the caption and
topic were supplied by an operator and are NOT independently authenticated
as publisher data. The original deterministic guess remains audit-visible.

A hash-verified full_document_page role suppresses the dangerous chart
heuristic for that entire page; the old guess remains as
deterministic_taxonomy_before_context. In the nine real original-raster
page pilot, all nine then took the known whole-document-page layout route,
and zero were sent to the chart or standalone diagram router. This is
metadata-provenance correction, NOT a model gaining new visual recognition.
No OCR or VLM was invoked. For regular standalone images, old detection
continues until a visual model is independently measured.

Exact page/source binding beyond the raster must be provided by an upstream
PDF layout detector with original PDF SHA, page and region coordinates.
The current pilot pins raster identity, not the parent PDF by itself.
Existing conversion behavior without the optional manifest is preserved.

## Recommended full architecture

1. Scan originals once; keep source SHA, file metadata and incremental
   changes. Native text, CSV, HTML, spreadsheets and legible PDF text are
   deterministic. Never replace proven text with a vague VLM caption.
2. Document layout first: separate heading/paragraph/formula/table/picture
   regions, reading order, two-column layout, figure boxes and captions.
   Crop figures by page and rectangle, not a whole PDF page. Pin
   original PDF source SHA, physical page, crop rectangle, crop image SHA,
   and source section+caption offsets.
3. First classify the actual cropped figure; distinguish genuine chart,
   table, diagram, circuit, plan, map, rendered scene, photograph,
   scientific microscopy, screenshot or uncertain. Benchmark low-confidence
   and conflicting classes rather than forcing a type.
4. For documents and OCR, compare PaddleOCR-VL-1.6 (0.9B, Apache-2.0,
   vendor reports 96.33 on OmniDocBench v1.6), GLM-OCR (~0.9B, MIT,
   vendor reports 94.62 on older OmniDocBench v1.5) and Tesseract.
   MinerU2.5-Pro-2604-1.2B is another optional coarse-to-fine parser.
   Published scores on different benchmark versions are not comparable
   local results. Measure CER/WER, reading order, table cell coordinates
   and equation fidelity on our original documents.
5. For chart figures, verify a candidate with a trained classifier,
   e.g. Docling DocumentFigureClassifier-v2.5 or a calibrated SigLIP2
   classifier. Benchmark IBM Granite Vision 4.1 4B with specific tasks
   chart2csv, chart2summary, chart2code and compare it against DePlot and
   PaddleOCR-VL chart recognition. Numbers, ticks, legends and units must
   be correct, not merely a fluent plot description. Extract from native
   XLSX/PPTX structured data when that exists.
6. For flowcharts/circuits/mathematical and scientific diagrams, use a
   specialist/local VLM with the *actual* source topic, figure caption,
   legend, and section context. Require faithful node/arrow direction,
   units/variable labels, and explicit missing visual evidence.
7. For CG rendering versus genuine photographs, benchmark Qwen3.5-9B
   and a compact VLM on known ground-truth paired photos/renders. Ask
   about observable material BRDF, Fresnel/roughness, contact shadows,
   highlights, geometric repetition and lighting inconsistencies, but
   never make confident binary authenticity claims without ground truth.
8. Store successful extraction products as distinct auditable derivatives:
   page crop SHA, original PDF SHA, extracted text, region type, model
   name/version/weights license/prompt hash, numeric outputs and
   confidence/calibration. Append source-revision-linked representations
   to the original canonical KnowMoreDiRT FileDB; retain ordinary text
   search and continuously running hierarchical summaries. The full
   DRT/DSPG reasoning layer should sit above these grounded representations.
   Do not create a second conflicting live indexing database.

Near-term pilot: two scanned original PDFs with selected text and figure
pages, technical image 20-case benchmark, 4 true charts with independently
known numeric source tables, 4 diagrams, OpenPBR/CG figure crops and
known photos of comparable objects. Judge source truth, OCR CER, chart
numbers, arrow topology, rendering-vs-photo uncertainty, hallucination,
latency, and resident memory. Only after selecting models through that
benchmark should mass conversion be considered.

## Available machines and status

Raspi: active library index, orchestration, original PDF and Tesseract.
Thor: high GPU use serving existing KMD models; never steal model memory.
Nitro: RTX 3060 6GiB, approximately 2.9GiB unallocated GPU memory at
inspection. Jetson Xavier: 30GiB total, about 17GiB RAM available,
but /data 96% occupied; preinstalled Docling 2.91 CPU environment.
No current high-quality vision model has been downloaded or tested in
this pilot, and no server or worker was stopped. The small PaddleOCR
or GLM-OCR is the first candidate for a resource-budgeted model trial.

Upstream references verified November 15, 2026:
https://github.com/PaddlePaddle/PaddleOCR/releases
https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6
https://github.com/zai-org/GLM-OCR
https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B
https://docling-project.github.io/docling/usage/vision_models/
https://github.com/docling-project/docling/blob/main/docs/usage/model_catalog.md
https://huggingface.co/ibm-granite/granite-vision-4.1-4b
https://huggingface.co/Qwen/Qwen3.5-9B
https://huggingface.co/google/siglip2-base-patch16-224

This is an audited extraction and context-routing advance, not a claim of
full OCR, chart digitization or truth-grounded visual reasoning.
