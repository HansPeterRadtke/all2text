# Offline CLIP figure routing experiment — November 15, 2026

This work extends the prior All2Text image-context branch 17986c4,
without changing the production Knowledge Library originals, native
KnowMoreDiRT FileDB, summaries, OCR, or inference services.

## Actual original deficiency

All2Text's color/line image heuristic labeled 17 of the original
20-image technical fixture set as charts. The separately authored RAG
review descriptions classify five as chart-like visualizations and
15 as circuit/flow diagrams, technical drawings, maps, screenshots
or illustrations. The heuristic had 5 true chart positives, 12
false-positive chart routes and zero missed charts: 29.4% chart precision.
The sample is small, non-representative and some class boundaries
need independent secondary annotation.

## Local CLIP measurement

The owner-installed CLIP ViT-B/32 model at
/data/models/rag_tests/vision/openai_clip-vit-base-patch32 was evaluated
fully offline on Nitro, CPU-only, using two threads, the same two
generic category prompts per class for all test images, no file-name
hints or reference target data in prompts, and no GPU resource.
Classes included chart, diagram, technical drawing, map, document page,
screenshot, illustration, photo, render, table and other.

Results were 4/5 true chart detections, zero false-positive charts,
1 missed chart (a housing heat map), 15 true-negative non-charts.
Chart precision was 4/4=100% and chart recall 4/5=80% for this small
sample. Exact top-one eleven-way class matched 13/20 reviewed types.
Cosine-similarity scores are uncalibrated. A conservative default
top-two margin of 0.02 is a policy threshold, NOT learned accuracy.
In a complete All2Text folder conversion, all twenty local model
calls succeeded, four charts passed the gate, zero false charts
passed, and eleven images were explicitly marked uncertain.
No OCR, chart-to-table, VLM caption, model download, or external API call
occurred. There is no justified global accuracy claim from these results.

The private Nitro audit holds the exact labels transferred from Raspi,
image SHA checks, generic prompts, scores, route decisions, run time,
unmodified fixture sources and actual All2Text output manifest:
/data/var/knowmoredirt-clip-visual-route-20261115/

## Implemented opt-in behavior

The pre-existing image_classifier provider configuration name CLIP
was a model/availability contract with no functioning local adapter.
This branch implements a real offline CPU-only CLIP adapter while
leaving its default auto_invoke=false. A successful route requires
a model-capable profile, explicitly enabled provider with
auto_invoke=true and a local absolute model_path. The loader uses
local_files_only and disables remote code. Loaded weight SHA-256,
model config SHA-256, and prompt-list SHA-256 are recorded for audit.
The same model is cached once per process, and its on-disk weight
digest is verified before and after loading.

The old deterministic taxonomy remains in metadata. Strongly
separated CLIP chart/diagram/page candidates change the route;
an ambiguous prediction instead abstains, preventing accidental
chart-specific extraction. An explicitly requested but failing
CLIP model also abstains rather than silently using weak geometric
chart inference. A SHA-pinned full-document-page context still
overrides everything: the page must be segmented before any
figure-specialist interpretation. The photo-versus-CGI route is
only visual similarity; it is not a provenance or authenticity
claim. No image pixel or caption is treated as an instruction.

Example opt-in configuration:

    [run]
    profile = "local-models"

    [providers.image_classifier]
    name = "clip"
    enabled = true
    auto_invoke = true
    model_path = "/data/models/rag_tests/vision/openai_clip-vit-base-patch32"
    minimum_margin = 0.02

    [providers.chart]
    name = "none"
    enabled = false

Run on a small image subset before any larger tree. This remains a
figure-type decision aid, not a text/diagram extractor.

## Next real quality gates

1. Test a true page layout detector and crop by original PDF SHA,
   page, bounding region and figure caption. A full scanned page
   is never assumed to be an isolated diagram/chart.
2. On independent holdouts, evaluate modern SigLIP2 or Docling's
   figure classifier against this old CLIP baseline and calibrate
   abstention rather than relying on generic softmax confidence.
3. Compare local PaddleOCR-VL 1.6 and GLM-OCR against Tesseract on
   selected scanned source pages for text CER, reading order,
   formula and table fidelity, with explicit original page proof.
4. Test DePlot and Granite Vision 4.1 chart-to-CSV against known
   actual numerical source data and verify axes, units, series,
   digitized values and hallucinated values.
5. Assess technical-diagram topology and CGI/photo ambiguity with
   a trained general-purpose VLM and topic-specific prompts.
6. Only source-checked derivatives should be appended to the
   one existing native KnowMoreDiRT FileDB. Keep the original
   texts, ordinary search and ongoing summary workers untouched.

The optional setup test test_capa_uses_detected_newer_python is
known to fail already on the untouched June 11 parent; the exact
regression evidence and all new tests are preserved separately.
