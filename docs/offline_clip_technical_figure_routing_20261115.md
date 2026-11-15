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

## Follow-up: optional offline DePlot chart-to-table candidate

The earlier RAG fixture model google/deplot was still present on Nitro.
A first 2026-11-15 offline attempt failed even though the local DePlot
model/processor/weights loaded successfully. The actual failure was in
Pix2StructImageProcessor rendering its text header: by default it tried
to download ybelkada/fonts Arial.TTF from Hugging Face. We reproduced
the exact missing-font exception in a bounded local traceback. An
explicit existing local LiberationSans-Regular.ttf prevents this
automatic remote request, and both model loading and generation then
succeeded in the offline, CPU-only environment.

The two separate synthetic known-data plots were:
- Quarterly Ticket Counts, Q1=10, Q2=20, Q3=30
- Workshop Temperature, time 0=20C, 1=30C, 2=40C, 3=35C

Direct DePlot generated exact titles, corresponding x/y columns, and
all seven original category-value pairs. Each figure needed about
22 seconds on Nitro CPU. These charts are simple and their source data
was generated in the test; 7/7 exact pair matching does not establish
accuracy on scientific papers, distorted plots, difficult axes, tiny
legend labels or partial OCR.

This branch now offers an explicit local chart specialist adapter
for the already-declared chart provider name deplot. Required:
- A model-capable run profile, chart.enabled=true,
  chart.auto_invoke=true, and an absolute existing model_path
  with safetensors weights.
- Explicit absolute local font_path to a TTF/OTF, never a default
  Hub font download. DePlot output records the font and model SHA.
- A genuinely used and confidently accepted CLIP classifier chart
  decision. Weak image geometry, a tiny CLIP margin, an unavailable
  CLIP model, an unrelated diagram or a complete original PDF page
  are insufficient to invoke numeric extraction.
- CPU inference, one cached model per process, bounded image size and
  generated token count; the optional adapter is disabled by default.

The generated table is always marked UNVERIFIED MODEL-GENERATED
CHART-TO-TABLE CANDIDATE in text and converter metadata. The
numeric_values_verified field stays false, even if the table looks
plausible or the model's output includes a polished explanation.
No chart values are promoted as verified FileDB facts automatically.
The independent two-chart test compares the candidate output against
known source data and confirms all seven values; this test evidence
does not carry over to unverified future images.

Example additional opt-in configuration:

    [providers.chart]
    name = "deplot"
    enabled = true
    auto_invoke = true
    model_path = "/data/models/rag_tests/vision/google_deplot"
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    max_tokens = 160
    max_image_side = 700

The private reproducibility folder contains the source-data figures,
original data, SHA checks, the first font failure and traceback,
corrected direct DePlot output, integrated All2Text manifests, a strict
row-by-row comparison and regression log:
/data/var/knowmoredirt-clip-visual-route-20261115

Do not enable batch chart extraction on the 94.5GiB library yet.
First run independent numeric holdouts, validate figure segmentation,
supply parent original PDF SHA/page/bounding box/caption, and measure
precision, numerical errors and hallucinations against primary data.
The adapter's generation is synchronous and not an isolated
service with an enforced wall-clock timeout; a production deployment
requires a timeout-bounded worker and resource broker reservation.
