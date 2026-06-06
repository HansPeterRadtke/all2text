# Open-source extraction research for all2text

Date: 2026-06-06

This report records the current research state for improving `all2text` beyond its deterministic document/text baseline. It combines current web research with the earlier `/data/src/github/devtests/rag_tests` image-analysis work.

The target product is a staged, layered all-file-to-text system. The correct behavior is not to send every file blindly into a giant model. The correct behavior is to identify the file and content, extract deterministic text/metadata first, then route difficult sub-content such as scanned pages, embedded images, charts, audio, video, CAD, scientific arrays, and technical diagrams to specialized providers only when the provider is actually available.

## 1. Current all2text baseline

The current install direction is now correct: from a cloned repository the normal install is `python -m pip install .`, and the normal run is `python -m all2text SOURCE_FOLDER TARGET_FOLDER`. The current Python dependency set covers the practical Python-only base. External binaries and model files are not bundled into pip; they are detected at runtime or configured.

Current strong areas:

- Plain text, source code, Markdown, JSON, JSONL, CSV, TSV, YAML, XML, HTML, RTF, notebooks, GeoJSON/KML, email, SQLite schema, archive listings, and compressed stream summaries.
- Native DOCX, XLSX, PPTX, PDF text-layer, and OpenDocument extraction through Python libraries.
- Image technical metadata and routing status.
- Audio/video metadata when `ffprobe` or Python media libraries are available.
- Honest fallbacks for unknown, binary, unsupported, or specialist formats.

Current weak areas:

- Scanned PDFs and page images need document OCR/layout models.
- Image semantic analysis needs a stronger classification pipeline and optional VLM execution.
- Chart image understanding needs chart-specific models and geometric fallback.
- Audio-to-text needs ASR, voice activity detection, language identification, and optionally diarization.
- Video-to-text needs frame sampling, scene detection, OCR/VLM on frames, subtitles, and audio extraction/transcription.
- CAD/scientific/geospatial/executable/container deep analysis needs specialist libraries and safe output conventions.

## 2. Local devtests image-analysis baseline

The earlier `rag_tests` work has useful image-analysis lessons that should be ported into all2text carefully. Relevant local files include:

- `rag_tests/vision/image_analysis_adapter.py`
- `rag_tests/vision/routing.py`
- `rag_tests/vision/chart_model.py`
- `rag_tests/converters/image_converter.py`
- `tests/test_image_heuristics.py`
- `tests/test_routed_image_pipeline.py`
- `fixtures/technical_image_eval/`

The local design already moved in the right direction. It used layered providers and image-family routing instead of a single generic image prompt. It recognized categories such as chart, document screenshot, map or plan, circuit schematic, diagram, flowchart, network graph, mechanical technical drawing, architectural floor plan, financial chart, heatmap, scatter plot, table screenshot, general scene/photo, and source-title traps. It also handled traps where a file name says “financial chart” but the image content is actually a dog or a plain photo.

The most important local lesson is this: the first image classifier should not be the final semantic answer. It should decide a route. For example, a chart routes to chart extraction, OCR, and VLM synthesis; a schematic routes to technical-diagram OCR/VLM; a table screenshot routes to OCR/table extraction; a photo routes to captioning/VLM; a map routes to map/plan logic; a scanned page routes to document OCR/layout.

The existing devtests chart model hook used DePlot as a local chart-to-table model, but also treated ChartGemma and UniChart as future routes. The all2text implementation should generalize this into provider contracts and not hardwire a single model.

## 3. File identification and staged classification

The first layer should remain deterministic and cheap.

Recommended layers:

1. Path and extension hints.
2. Header and magic-byte signatures.
3. Container inspection for ZIP-based formats such as DOCX, XLSX, PPTX, ODT, ODS, EPUB, JAR, and many app containers.
4. MIME tools such as libmagic/file when available.
5. Learned file-type classifier only when deterministic evidence conflicts or when content is fragmentary.
6. Content-profile classification after decoding or opening the file.

Useful tools and models:

- `file`/libmagic remains the classic OS-level baseline.
- `python-magic` wraps libmagic but still depends on the external libmagic database and platform packaging.
- `filetype.py` is a small dependency-free magic-number library and may be useful as an internal fallback.
- Google Magika is useful as a learned file-type detector for ambiguous files, but it should be optional, not required.
- MimeLens is a very recent research direction for classifying binary fragments without relying only on the file header. It is interesting for future carved/fractured data support, not needed for the first all2text release.

Recommendation for all2text: keep the current deterministic detector as the root. Add optional `filetype.py` or Magika only as extra evidence. Record all signals, including conflicts, instead of hiding them.

Sources:

- https://github.com/ahupp/python-magic
- https://github.com/h2non/filetype.py
- https://opensource.googleblog.com/2024/02/magika-ai-powered-fast-and-efficient.html
- https://arxiv.org/abs/2606.04171

## 4. Documents, PDFs, OCR, layout, and scanned pages

This is the most important area after normal Office/text extraction. The all2text baseline already handles PDF text layers, DOCX, XLSX, PPTX, OpenDocument, structured text, emails, notebooks, and archives. The missing piece is robust scanned/layout-heavy document parsing.

Strong candidates:

- Docling: strong open-source document conversion toolkit, MIT-licensed, designed for structured document conversion, PDF understanding, tables, formulas, reading order, OCR integration, and AI workflows. It is an excellent high-level provider candidate for PDF/Office/document conversion where we want structured output, not just raw text.
- Marker: strong PDF/image/Office-to-Markdown/JSON/HTML converter with table, equation, link, reference, code block, and image handling. It is a strong quality candidate but license and resource requirements need review before making it a default dependency.
- MinerU: strong document parsing system for PDF, images, DOCX, PPTX, XLSX to Markdown/JSON, with OCR, table conversion, reading order, and visualization. It is powerful but heavier and should be optional/provider-level.
- Surya: OCR/layout/reading-order/table/LaTeX OCR toolkit, useful for scanned page and document image pipelines. License/resource concerns should be checked before defaulting.
- PaddleOCR/PaddleOCR-VL: very important because it is open, efficient, multilingual, and document-focused. PaddleOCR 3.0 includes PP-OCRv5, PP-StructureV3, and PP-ChatOCRv4; PaddleOCR-VL is a compact 0.9B document parsing VLM aimed at text, tables, formulas, and charts, with 109-language support. This is one of the best candidates for the scanned-document OCR/layout provider.
- olmOCR: open-source PDF OCR/linearization toolkit from AllenAI; useful for high-quality PDF-to-text, reading order, tables, equations, handwriting, and difficult scans. It is heavier because it uses a 7B VLM family, but it is a strong optional provider for high-quality document OCR.
- Tesseract: mature OCR engine and still useful as a lightweight external OCR fallback, but weaker on layout, tables, handwriting, and modern complex pages than newer document VLM/OCR stacks.

Recommended all2text document stack:

Layer 0: existing deterministic text/native Office/PDF extraction.

Layer 1: PDF/image classification: text-layer PDF, scanned PDF, mixed PDF, garbled text PDF, form-heavy PDF, table-heavy PDF, equation-heavy PDF, handwritten, multi-column, figure-heavy, chart-heavy.

Layer 2: use native extractors first. If native text is good, do not OCR the page. If text is absent/garbled, route page images to OCR/layout.

Layer 3: use Docling or PaddleOCR-VL as the first integrated document-layout provider. Docling is the best general document conversion framework candidate. PaddleOCR-VL is the best compact document-VLM/OCR candidate. Tesseract remains fallback. olmOCR is a high-quality heavier OCR provider.

Layer 4: for per-page embedded elements, route tables to table extraction, charts to chart pipeline, images/figures to image pipeline, equations to LaTeX OCR/model if available.

Sources:

- https://github.com/docling-project/docling
- https://arxiv.org/html/2501.17887v1
- https://www.docling.ai/
- https://github.com/datalab-to/marker
- https://github.com/opendatalab/MinerU
- https://github.com/datalab-to/surya
- https://github.com/PaddlePaddle/PaddleOCR
- https://arxiv.org/abs/2507.05595
- https://arxiv.org/html/2510.14528v1
- https://huggingface.co/PaddlePaddle/PaddleOCR-VL
- https://github.com/allenai/olmocr
- https://olmocr.allenai.org/
- https://arxiv.org/abs/2502.18443
- https://arxiv.org/abs/2510.19817

## 5. Tables

Tables appear as XLSX sheets, HTML tables, Markdown tables, PDF text-layer tables, scanned tables, image tables, screenshots, and embedded document figures.

Current all2text already does strong XLSX extraction and safe CSV/TSV/HTML/Markdown extraction. The missing piece is visual/PDF table structure extraction.

Strong candidates:

- Native XLSX/openpyxl remains best for actual spreadsheets.
- pdfplumber/Camelot/Tabula-style approaches can help text-layer PDFs, but they do not solve scanned/image tables.
- Docling and PaddleOCR-VL are high-level table-capable document providers.
- Microsoft Table Transformer (TATR) and PubTables-1M remain important for table detection and structure recognition from PDFs/images.
- PubTables-v2/POTATR is a newer direction for full-page and multi-page table extraction, but as of this research it is more research/benchmark route than immediate production dependency.
- PdfTable integrates multiple open-source table recognition/OCR/layout models and is useful as a research reference for provider design.

Recommended all2text table route:

- Prefer structured source data: XLSX, CSV, HTML, Markdown, SQLite, JSON.
- For text-layer PDF tables, try Docling/table-aware PDF path first.
- For scanned/image tables, route through PaddleOCR-VL or Surya/Docling table recognition.
- For table images in documents, classify as table screenshot/document table and output both OCR text and detected table grid if provider supports it.
- Always label table confidence and source: native spreadsheet, text-layer table, OCR table, model-inferred table, or fallback.

Sources:

- https://github.com/microsoft/table-transformer
- https://arxiv.org/abs/2110.00061
- https://arxiv.org/abs/2512.10888
- https://arxiv.org/abs/2409.05125
- https://github.com/PaddlePaddle/PaddleOCR
- https://github.com/docling-project/docling

## 6. Image classification and image-to-text

The image pipeline should not be one monolithic “describe image” step. It should be a hierarchy:

1. Technical metadata: format, dimensions, colorspace, EXIF, frames, alpha, aspect ratio, blank/dark/bright/grayscale-like, image entropy, text density hints.
2. Rough category: photo, screenshot, scan/document, chart/plot, table screenshot, diagram, technical drawing, map/plan, painting/illustration, abstract/texture, AI-generated/artistic, icon/logo/UI, medical/scientific image, unknown.
3. Specialist subcategory: chart type, document page type, diagram type, drawing type, UI type, map/plan type.
4. Route-specific extraction: OCR, table extraction, chart extraction, VLM captioning, figure captioning, map/plan description, technical drawing metadata.
5. Synthesis with source-specific evidence and confidence.

Useful models/tools:

- CLIP or SigLIP/SigLIP 2 for zero-shot or few-shot image family routing. SigLIP 2 is a modern multilingual vision-language encoder family and should be considered a newer classification backbone.
- DINOv2 or OpenCLIP-style embeddings for clustering/dedup/similarity, but promptable VLM-classification through CLIP/SigLIP is more directly useful for route decisions.
- Qwen2.5-VL is a strong open vision-language model family with document parsing, object localization, and long-video comprehension. It is a strong local VLM route for image descriptions, screenshots, UI, charts, OCR help, and technical images when resources allow.
- SmolVLM2 is useful as a smaller local VLM/video-capable option for weaker hardware.
- Molmo2 is a 2026 open-weight/data family for image/video understanding and grounding; it looks very promising for future high-quality local VLM provider work.
- Tesseract remains a simple OCR route.
- PaddleOCR-VL/Docling/Surya are better for document-like images and scanned pages.

Recommended all2text image taxonomy:

- photo/scene
- portrait/person/object/product
- screenshot/UI/webpage/app
- document scan/page
- table screenshot
- chart/plot
- diagram/flowchart/UML/network graph
- circuit/electrical schematic
- mechanical technical drawing
- architectural floor plan/building plan
- map/geospatial plan/heat map
- scientific/medical image
- painting/illustration/art
- abstract/texture/pattern
- logo/icon
- unknown/ambiguous

The devtests already covered many of these categories. all2text should port that taxonomy, but keep it extensible through config and provider labels.

Sources:

- https://arxiv.org/html/2502.14786v1
- https://docs.openvino.ai/2024/notebooks/siglip-zero-shot-image-classification-with-output.html
- https://arxiv.org/abs/2502.13923
- https://qwen.ai/blog?id=qwen2.5-vl
- https://huggingface.co/blog/vlms-2025
- https://blog.roboflow.com/local-vision-language-models/
- https://arxiv.org/abs/2601.10611

## 7. Charts and plots

Charts need specialized handling because a generic caption like “a bar chart” is not enough. The desired text output should include chart type, title, axes, legend, categories, series, values where recoverable, trends, limitations, and source confidence.

Chart subcategories should include:

- line chart
- scatter plot
- bar chart horizontal/vertical/grouped/stacked
- pie/donut chart
- area chart
- histogram
- box plot
- heat map
- bubble chart
- radar/spider chart
- candlestick/financial chart
- network graph
- Sankey/alluvial
- timeline/Gantt
- mixed/multi-panel chart
- infographic with multiple charts

Useful models/tools:

- DePlot translates chart images into linearized tables and is a practical chart-to-data provider. It is an older but still useful baseline and is already reflected in devtests.
- UniChart is a lightweight chart-specific VLM that handles ChartQA, chart-to-table, summarization, and open-ended QA. It is a strong candidate for a small specialist provider.
- ChartGemma is a chart-specific model built over PaliGemma for chart understanding and reasoning in the wild. It is a strong candidate for semantic chart summaries and question-answering.
- ChartOCR and DeepRule-style pipelines are useful for rule+deep hybrid extraction of chart primitives. They are more engineering-heavy but valuable for numeric fidelity.
- LineFormer/ChartDete-style line chart pipelines are useful for extracting line coordinates, but need axis/OCR integration to produce real values.
- OneChart, ChartAssistant, ChartCoder, Chart2Code/CharLuMA represent newer chart-to-structure or chart-to-code research directions. These should be tracked, but they may need more implementation work before being practical in all2text.

Recommended all2text chart route:

1. Decide whether image is chart versus table versus diagram versus screenshot. Use heuristic geometry, OCR text, CLIP/SigLIP route classifier, and VLM evidence.
2. If chart, classify chart type.
3. Run OCR for title, axes, legend, ticks, labels.
4. If chart specialist available, run DePlot/UniChart/ChartGemma depending on model availability and resource profile.
5. If geometric chart type is simple, run deterministic fallback: bar detection, line detection, pie segments, axis/tick extraction where possible.
6. Emit structured text: chart_type, title, axes, series, labels, values/table if available, trend summary, evidence, confidence, provider, limitations.
7. For embedded charts in XLSX/PPTX/DOCX/PDF, prefer original structured data when available. Image-only chart extraction is a fallback.

Sources:

- https://huggingface.co/google/deplot
- https://huggingface.co/docs/transformers/model_doc/deplot
- https://arxiv.org/abs/2212.10505
- https://github.com/vis-nlp/UniChart
- https://arxiv.org/html/2305.14761
- https://aclanthology.org/2025.coling-industry.54/
- https://arxiv.org/html/2407.04172v1
- https://www.microsoft.com/en-us/research/publication/chartocr-data-extraction-from-charts-images-via-a-deep-hybrid-framework/
- https://openaccess.thecvf.com/content/WACV2021/papers/Luo_ChartOCR_Data_Extraction_From_Charts_Images_via_a_Deep_Hybrid_WACV_2021_paper.pdf
- https://github.com/khuangaf/Awesome-Chart-Understanding
- https://github.com/TheJaeLal/LineFormer
- https://arxiv.org/abs/2501.06598
- https://arxiv.org/abs/2604.24559

## 8. Audio-to-text and audio classification

Audio should be handled in layers:

1. Container/codec metadata through Python libraries and `ffprobe`.
2. Audio kind classification: silence, noise, music, speech, mixed speech+music, environmental sound, unknown.
3. Voice activity detection.
4. Language identification.
5. Transcription.
6. Optional diarization: who spoke when.
7. Optional translation.
8. Output with time-coded segments, confidence, language, provider, and limitations.

Recommended tools/models:

- `ffprobe` for duration, streams, codec, sample rate, channels, tags, and container metadata.
- Whisper/openai-whisper as the classic multilingual ASR baseline with transcription, translation, and language identification.
- whisper.cpp for a cross-platform local binary option with low dependency burden; very good for a user-installable external tool route.
- faster-whisper for Python/CTranslate2 high-throughput ASR; good when Python dependencies and model downloads are acceptable.
- WhisperX for word-level timestamps and diarization integration; useful as a high-detail provider but heavier.
- NVIDIA Parakeet TDT 0.6B v2/v3 for high-quality English/multilingual ASR; strong newer ASR candidate, especially if NVIDIA hardware is available.
- pyannote.audio for speaker diarization, with the caveat that Hugging Face access/model gating can complicate fully automatic use.
- YAMNet, PANNs, OpenBEATs, LAION CLAP, and AudioSet-style classifiers for speech/music/noise/environmental classification before transcription. For the first version, YAMNet or PANNs are good simple classifiers; CLAP/OpenBEATs are better semantic audio embeddings for later.

Recommended all2text audio route:

- Always extract metadata first.
- If audio is very short/silent/noise, do not transcribe; summarize technical evidence.
- If classifier says speech or mixed speech, run ASR if provider configured/found.
- If multiple speakers are likely or diarization enabled, run diarization after VAD/ASR.
- If music, output tags/style/metadata if classifier supports it, but do not force speech transcription.
- If speech language is unknown, run ASR language detection or a language ID step.

Sources:

- https://github.com/openai/whisper
- https://github.com/ggml-org/whisper.cpp
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/m-bain/whisperx
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- https://github.com/pyannote/pyannote-audio
- https://huggingface.co/pyannote/speaker-diarization-community-1
- https://ai.google.dev/edge/mediapipe/solutions/audio/audio_classifier
- https://github.com/LAION-AI/CLAP
- https://arxiv.org/abs/2507.14129

## 9. Video-to-text and video understanding

Video should not be treated as a single giant model call. It should combine metadata, audio extraction, subtitle extraction, scene/keyframe sampling, OCR/VLM on frames, and optional video VLM.

Recommended layers:

1. Container metadata with `ffprobe`.
2. Embedded subtitle extraction if present.
3. Audio stream route into audio pipeline.
4. Scene detection or interval sampling.
5. Frame classification: slide/screen recording, document camera, lecture, UI demo, chart/table, scene/photo/video, animation, mixed.
6. OCR on relevant frames.
7. VLM descriptions on selected keyframes only.
8. Optional video-native VLM for short clips if available.
9. Output timeline with metadata, subtitles, ASR segments, OCR frame evidence, visual summary, and limitations.

Useful tools/models:

- `ffprobe` and `ffmpeg` are essential external tools for metadata, audio extraction, subtitles, and frame extraction.
- PySceneDetect or OpenCV can provide scene/keyframe detection.
- Qwen2.5-VL supports long-video comprehension and can be a strong local VLM route where resources allow.
- Qwen2.5-Omni/vLLM examples show multimodal inference for audio/image/video, interesting for future server-provider route.
- SmolVLM2 is a small model option for multi-image/video understanding.
- Molmo2 is a strong 2026 open-weight/data video/image VLM candidate with grounding and video understanding, worth tracking for higher-quality local video providers.
- For now, a frame-based pipeline plus audio pipeline is more deterministic and debuggable than relying only on a video VLM.

Recommended all2text video route:

- Implement subtitle extraction and audio extraction first.
- Implement keyframe sampling with explicit limits.
- Run OCR/VLM only on selected frames, not every frame.
- For screen recordings or slide decks, favor OCR and slide/frame deduplication.
- For lectures, favor audio ASR plus occasional frame OCR.
- For camera footage, favor scene/keyframe VLM summaries plus audio ASR if speech exists.

Sources:

- https://ffmpeg.org/
- https://github.com/Breakthrough/PySceneDetect
- https://arxiv.org/abs/2502.13923
- https://docs.vllm.ai/en/v0.22.1/examples/generate/multimodal/
- https://blog.roboflow.com/local-vision-language-models/
- https://arxiv.org/abs/2601.10611

## 10. CAD, BIM, technical drawings, and engineering files

CAD and technical files split into several subproblems:

- Text-based CAD formats such as DXF can be parsed and summarized with Python libraries.
- Binary DWG is harder and often requires specialized tools or commercial/proprietary components.
- IFC/BIM has a strong open-source route through IfcOpenShell.
- STEP/STL/OBJ and mesh/solid files need CAD/geometry libraries or FreeCAD/OpenCascade routes.
- Image-only technical drawings need the image/diagram pipeline, not CAD parsing.

Useful tools:

- ezdxf for DXF reading/writing and metadata/entity extraction.
- IfcOpenShell for IFC/BIM reading, writing, modification, and geometry support.
- FreeCAD/OpenCascade/CadQuery for STEP/IGES/solid/mesh workflows, usually external/heavy.
- OCR/VLM/diagram routing for image-only floor plans, mechanical drawings, circuit schematics, and maps.

Recommended all2text CAD route:

- Detect text-based DXF and parse entity layers, block names, text annotations, dimensions, units, bounding boxes, and entity counts.
- Detect IFC and use IfcOpenShell if installed to list project/site/building/storeys/elements/properties/materials/geometry summary.
- For STEP/STL/OBJ, output metadata and geometry counts if libraries exist; otherwise safe summary.
- For DWG, treat as binary CAD unless a configured converter exists. Do not fake geometry extraction.
- For image technical drawings, use image taxonomy and route to OCR/VLM/diagram provider.

Sources:

- https://ezdxf.readthedocs.io/en/stable/introduction.html
- https://ifcopenshell.org/
- https://github.com/IfcOpenShell/IfcOpenShell

## 11. Scientific, geospatial, and specialist data

The goal here is usually not “semantic narrative” first. The goal is metadata, schema, dimensions, variables, coordinate systems, columns, array shapes, units, and sample values.

Scientific formats:

- HDF5: h5py/h5netcdf/PyTables-style hierarchy, groups, datasets, shapes, dtypes, attributes.
- NetCDF: variables, dimensions, coordinates, attributes, units, global metadata.
- FITS: astropy for astronomy image/table headers and HDUs.
- Parquet/Arrow: pyarrow schema, row groups, columns, statistics.
- NumPy/NPZ/MAT: array names, shapes, dtypes, min/max/sample where safe.

Geospatial formats:

- Shapefile/GeoJSON/KML: geometry types, CRS, fields, feature counts, bounds, sample features.
- GeoTIFF/raster: CRS, transform, bands, dimensions, nodata, stats.
- GDAL/Rasterio/Fiona/GeoPandas/pyogrio are powerful but can be difficult to install everywhere; pyproj, shapely, pyshp are lighter pieces.

Recommendation:

- Add a scientific provider that never dumps giant arrays by default. It emits schema and sampled statistics.
- Add a geospatial provider that emits CRS, bounds, layer names, feature counts, field schema, geometry types, and sample features.
- Keep heavy GDAL/Rasterio/Fiona optional/external/advanced due to packaging difficulty.

Sources:

- https://www.h5py.org/
- https://h5netcdf.org/index.html
- https://github-pages.ucl.ac.uk/rsd-engineeringcourse/ch02data/070hdf5.html
- https://geopandas.org/en/latest/docs/user_guide/reproject_fiona.html
- https://martinfleischmann.net/geopandas-1.0-and-beyond/

## 12. Executables, libraries, disk images, and containers

These formats should be handled carefully. all2text should not behave like a malware sandbox, but it can emit safe metadata and static summaries.

Useful tools:

- pefile for Windows PE metadata.
- macholib for macOS Mach-O metadata.
- LIEF for cross-format binary parsing if installable and stable on target platforms.
- capa for capability detection from executables. Good for security triage, but should be optional because output can be large and domain-specific.
- radare2/rabin2 for deeper static analysis. External tool route only, never default in a normal conversion unless explicitly enabled.

Recommended output:

- File type, architecture, entry point, imports/exports, sections, strings sample, signatures if available, compilation metadata, warnings.
- Do not disassemble everything by default.
- Do not execute anything.

Sources:

- https://mandiant.github.io/capa/
- https://radare2.com/
- https://github.com/radareorg/radare2

## 13. Recommended all2text provider architecture

The all2text core should remain deterministic and auditable. Providers should be swappable.

Required provider states:

- configured
- auto-detected
- executable/model/library found
- endpoint reachable
- dependency missing
- disabled by config
- attempted
- used
- failed
- skipped by classifier
- skipped by resource limit

Recommended provider interfaces:

- `FileTypeProvider`: libmagic/filetype/Magika.
- `DocumentProvider`: Docling, Marker, MinerU, PaddleOCR-VL, olmOCR, Tesseract fallback.
- `TableProvider`: native spreadsheet, Docling/PaddleOCR-VL, TATR/PubTables, PdfTable.
- `ImageClassifierProvider`: deterministic image stats, CLIP/SigLIP, local image_analysis categories.
- `OCRProvider`: Tesseract, PaddleOCR, Surya, PaddleOCR-VL.
- `VLMProvider`: llama.cpp/OpenAI-compatible Qwen2.5-VL, SmolVLM2, Molmo2, other local servers.
- `ChartProvider`: DePlot, UniChart, ChartGemma, ChartOCR/DeepRule, geometric fallback.
- `AudioProvider`: ffprobe, YAMNet/PANNs/OpenBEATs/CLAP classifier, Whisper/whisper.cpp/faster-whisper/Parakeet ASR, pyannote/DiariZen diarization.
- `VideoProvider`: ffprobe/ffmpeg, PySceneDetect/OpenCV, frame OCR, frame VLM, video VLM.
- `CADProvider`: ezdxf, IfcOpenShell, FreeCAD/OpenCascade route.
- `ScientificProvider`: h5py/h5netcdf/netCDF4/astropy/pyarrow/scipy.
- `BinaryProvider`: pefile/macholib/LIEF/capa/rabin2.

Every provider result should include output text, structured metadata, confidence/evidence, warnings, limitations, resource usage, and whether file content was sent to a model.

## 14. Implementation priority

Phase 1: Provider discovery and doctor command hardening.

- Improve `all2text doctor` into a full capability report: Python libraries, external tools, running model endpoints, suspected llama.cpp processes, versions, paths, and blockers.
- Add Windows and Linux discovery backends for tools and llama.cpp processes.
- Keep config overrides for everything.

Phase 2: Document OCR/layout provider.

- Add Docling provider first if install/resource behavior is acceptable.
- Add PaddleOCR-VL provider as compact document parser.
- Keep Tesseract fallback.
- Add page-level routing for scanned PDFs and embedded document images.

Phase 3: Image taxonomy and routing.

- Port devtests taxonomy into all2text.
- Add deterministic image stats and route classifier.
- Add optional CLIP/SigLIP provider for route classification.
- Add VLM provider hooks for image descriptions.

Phase 4: Charts.

- Add chart classifier and output schema.
- Add DePlot provider as first chart-to-table path.
- Add UniChart/ChartGemma as optional providers.
- Add deterministic fallback for simple bar/line/pie charts.

Phase 5: Audio.

- Add ffprobe + mutagen metadata baseline.
- Add audio kind classifier route.
- Add whisper.cpp/faster-whisper/Parakeet provider interface.
- Add diarization provider route.

Phase 6: Video.

- Add subtitle/audio extraction and frame sampling with ffmpeg.
- Add scene/keyframe selection.
- Route frames to OCR/VLM/image classification.
- Add video VLM provider as optional high-resource route.

Phase 7: CAD/scientific/geospatial/binary.

- Add schema/metadata providers first.
- Avoid dumping huge arrays or disassembly.
- Keep specialist heavy dependencies optional and explicit.

## 15. Tool/model shortlist

Recommended immediate candidates:

- Docling: general document conversion provider.
- PaddleOCR-VL: scanned documents, OCR, tables, formulas, charts in documents.
- Tesseract: simple OCR fallback.
- Qwen2.5-VL: local VLM provider for image/document/chart/video snippets.
- DePlot: chart-to-table baseline provider.
- UniChart or ChartGemma: chart-specific VLM provider.
- whisper.cpp or faster-whisper: speech transcription provider.
- Parakeet TDT v3: newer multilingual ASR candidate.
- pyannote.audio: diarization provider.
- YAMNet/PANNs/OpenBEATs/CLAP: audio kind classification provider.
- ffprobe/ffmpeg: media metadata and extraction.
- PySceneDetect/OpenCV: video keyframe/scene route.
- ezdxf: DXF route.
- IfcOpenShell: IFC/BIM route.
- h5py/netCDF4/astropy/pyarrow/scipy: scientific schema route.
- pefile/macholib/capa/radare2: binary metadata/security route.

## 16. Main conclusion

The all2text core should not become one enormous model wrapper. It should become a routing and evidence system. The winning architecture is layered: deterministic extraction first, specialized parser second, OCR/VLM/ASR only for content that needs it, and clear truthfulness everywhere. The next implementation work should therefore build provider contracts and provider-specific output schemas before chasing every model at once.

## 17. Revision pass: ranked candidate sets and confidence

This revision pass was added after a broader search. The conclusion changed from a simple shortlist to a ranked candidate set. For several areas there is no single provable best open-source model. The correct all2text plan is therefore to support two or three strong providers per hard task and benchmark them on our own data.

### 17.1 Document OCR and document parsing

Confidence: high that these are the right candidates; low that one universal winner exists.

Tier 1 candidates:

- PaddleOCR-VL / PaddleOCR-VL-1.5 / PaddleOCR-VL-1.6. This is currently one of the strongest compact open document parsing families. The 2026 PaddleOCR documentation reports PaddleOCR-VL-1.5 at 94.5% on OmniDocBench v1.5, and the PaddleOCR-VL-1.6 paper reports 96.33% on OmniDocBench v1.6. It is especially attractive because it is document-specific and compact rather than a huge general VLM.
- GLM-OCR. This is another strong compact document OCR/parser candidate. The GLM-OCR technical report describes a 0.9B multimodal OCR model with a two-stage document parsing pipeline and strong performance on document parsing, text, formulas, tables, and key information extraction. Independent model pages also report high throughput around 1.86 PDF pages per second.
- olmOCR 2. This is a strong PDF/OCR candidate trained with verifiable unit-test rewards. It is especially relevant for natural reading order, math formulas, tables, and multi-column layouts.
- Docling. This remains the best general integration framework candidate because it is not just an OCR model. It provides document conversion, layout, reading order, tables, formulas, and a unified document representation.

Tier 2 candidates:

- Chandra OCR 2. The project claims state-of-the-art structured OCR to HTML/Markdown/JSON. It should be tested, not blindly trusted.
- DeepSeek-OCR / DeepSeek-OCR-2. It is interesting because of efficient visual-token compression, but a 2026 analysis warns that its apparent OCR quality may rely heavily on language priors and can collapse under semantic perturbation. It should be treated as a speed/compression candidate, not the most trustworthy extraction provider.
- Marker, MinerU, Surya. These remain good document-stack alternatives, especially for Markdown/JSON conversion and layout/OCR, but the first implementation target should be Docling plus one or two OCR-specific providers.

Implementation decision:

- Implement Docling as the first high-level document provider if install/runtime behavior is acceptable.
- Implement PaddleOCR-VL and GLM-OCR as OCR/layout provider candidates.
- Keep olmOCR2 as a heavier high-quality PDF OCR provider candidate.
- Keep Tesseract as lightweight fallback only, not as final quality target.
- Build a local benchmark: scanned PDF, phone-photo document, multi-column scientific article, table-heavy PDF, invoice/form, low-quality scan, handwritten page, equation-heavy page, and multilingual page.

Why we need local benchmarking:

OmniDocBench and related document benchmarks are now under pressure. PureDocBench claims OmniDocBench rankings are affected by annotation quality and contamination risk, and Real5-OmniDocBench shows a large gap between clean digital benchmarks and real physical scans. That means all2text must not choose a winner from one leaderboard only.

Sources:

- https://paddlepaddle.github.io/PaddleOCR/main/en/index.html
- https://arxiv.org/abs/2606.03264
- https://arxiv.org/abs/2601.21957
- https://arxiv.org/abs/2603.10910
- https://huggingface.co/zai-org/GLM-OCR
- https://arxiv.org/abs/2510.19817
- https://olmocr.allenai.org/
- https://github.com/allenai/olmocr
- https://docling-project.github.io/docling/
- https://github.com/datalab-to/chandra
- https://github.com/deepseek-ai/DeepSeek-OCR/
- https://arxiv.org/abs/2601.03714
- https://arxiv.org/abs/2605.07492
- https://arxiv.org/abs/2603.04205

### 17.2 Tables

Confidence: medium. Native table data is easy; image/PDF table reconstruction is still not solved.

Best practical candidates:

- Native spreadsheet extraction remains the first choice for XLSX/XLS/ODS/CSV/HTML/Markdown tables.
- Docling / TableFormer-style table extraction is the best general open-source integration candidate for PDFs and document pages.
- PaddleOCR-VL and GLM-OCR are strong candidates for visual table extraction inside scanned documents.
- Microsoft Table Transformer trained on PubTables-1M remains a core specialist table detection/structure candidate.
- PubTables-v2/POTATR is important because it targets full-page and multi-page table extraction, a known gap.
- pdfplumber and Camelot are still useful for text-layer PDFs, especially when custom heuristics are needed, but they do not solve image/scanned tables.
- PdfTable is a useful research/engineering reference because it combines multiple OCR, table recognition, and layout-analysis routes.

Implementation decision:

- Keep native spreadsheets as source-of-truth when available.
- For PDFs, try text-layer extraction first, then Docling/table provider, then OCR/VLM table provider.
- For image tables, use PaddleOCR-VL/GLM-OCR/Docling/Surya-style table provider candidates and output confidence/source.
- Add multi-page table merging as a separate phase; do not pretend single-page table extraction solves it.

Sources:

- https://github.com/microsoft/table-transformer
- https://arxiv.org/abs/2110.00061
- https://arxiv.org/abs/2512.10888
- https://arxiv.org/abs/2409.05125
- https://arxiv.org/abs/2603.18652
- https://www.llamaindex.ai/insights/best-ai-for-pdf-table-extraction

### 17.3 Image classification and image understanding

Confidence: medium-high for route classification candidates; lower for final semantic descriptions.

Route classification candidates:

- SigLIP 2 should be the first modern zero-shot image route classifier candidate. It is designed for multilingual image-text encoding and zero-shot classification, and current references say it improves over older SigLIP models across core capabilities.
- CLIP/OpenCLIP remains the fallback because it is simple, widely supported, and easy to run locally.
- DINOv2/DINO-family embeddings are useful for clustering, deduplication, and similarity, but less directly useful for prompt-label routing than SigLIP/CLIP.

Image/VLM understanding candidates:

- Qwen3-VL is likely the strongest current Qwen-family local VLM candidate where resources allow.
- Qwen2.5-VL remains practical because of existing llama.cpp/Jetson experiments and quantized availability.
- InternVL3.5 is a strong open VLM alternative, especially on reasoning benchmarks.
- Molmo2 is especially interesting for open-weight/data image/video grounding and counting/tracking tasks.
- SmolVLM2 is a good small-resource fallback for lightweight image/video routes.

Implementation decision:

- Do not use a VLM as the first classifier. Use deterministic image features plus SigLIP/CLIP route classification first.
- Then route to OCR, chart, document, technical drawing, map/plan, screenshot/UI, photo, or VLM description providers.
- Keep source-title hints as weak metadata only. Never let a filename override visual evidence.
- Port the devtests taxonomy and tests into all2text.

Recommended image category hierarchy:

- photo/scene
- portrait/person/object/product
- screenshot/UI/webpage/app
- document page/scan
- table screenshot
- chart/plot
- diagram/flowchart/UML/network graph
- circuit/electrical schematic
- mechanical technical drawing
- architectural floor plan/building plan
- map/geospatial plan/heat map
- scientific/medical image
- painting/illustration/art
- abstract/texture/pattern
- logo/icon
- unknown/ambiguous

Sources:

- https://arxiv.org/html/2502.14786v1
- https://huggingface.co/blog/siglip2
- https://docs.openvino.ai/2024/notebooks/siglip-zero-shot-image-classification-with-output.html
- https://www.bentoml.com/blog/multimodal-ai-a-guide-to-open-source-vision-language-models
- https://arxiv.org/html/2508.18265v1
- https://arxiv.org/abs/2601.10611
- https://blog.roboflow.com/local-vision-language-models/

### 17.4 Charts

Confidence: low that any one model is best; high that the right implementation is multi-provider plus benchmark.

Top candidates to test:

- ChartGemma for chart reasoning, summarization, QA, and fact-checking. It was designed specifically for chart reasoning in the wild.
- UniChart for lightweight chart QA, chart-to-table, chart summarization, and open-ended chart QA.
- DePlot / Pix2Struct / MatCha family for chart-to-table baseline extraction. DePlot is still a useful baseline for turning chart images into table-like output.
- ChartCoder for chart-to-code or chart structural reconstruction when code representation is useful.
- ChartOCR / DeepRule-style hybrid pipelines for better numeric fidelity and low-level chart primitive extraction.
- Newer candidates such as ChartVR, ChartSpec, ChartArena/ChartAct benchmark results, and Chart2Code-related work should be watched before locking a final provider.

Important limitation:

Chart understanding is not solved. ChartArena 2026 reports that expert chart parsers remain limited to narrow chart families, diagrammatic structures remain hard, radar charts and hand-drawn scenarios remain difficult, and even leading systems have clear capability gaps. Therefore all2text must not claim “chart extraction” as one solved feature.

Implementation decision:

- Build our own chart benchmark using the devtests technical images plus synthetic charts where ground truth is known.
- Output structured chart evidence with provider source and confidence.
- Use multiple providers: deterministic simple chart extractor, OCR, DePlot/UniChart/ChartGemma, VLM synthesis.
- For embedded Excel charts, prefer workbook source data and chart XML metadata over image reconstruction.

Sources:

- https://arxiv.org/abs/2407.04172
- https://github.com/vis-nlp/ChartQA
- https://github.com/vis-nlp/UniChart
- https://huggingface.co/google/deplot
- https://arxiv.org/abs/2212.10505
- https://arxiv.org/abs/2501.06598
- https://github.com/thunlp/ChartCoder
- https://arxiv.org/abs/2606.01348
- https://arxiv.org/abs/2605.26994
- https://exchart.github.io/
- https://github.com/khuangaf/Awesome-Chart-Understanding

### 17.5 Audio classification, ASR, and diarization

Confidence: medium-high for ASR candidates; medium for universal audio classification; medium-low for diarization because it is still difficult and domain-dependent.

Audio kind classification candidates:

- YAMNet is the easiest lightweight baseline. It predicts 521 AudioSet classes and is suitable for speech/music/noise/environmental routing.
- PANNs and AST are stronger older baselines than YAMNet for many AudioSet-style audio tagging tasks.
- BEATs / EAT / SSLAM / OpenBEATs represent stronger modern audio embedding/classification directions. OpenBEATs is especially attractive because it is fully open and reports strong performance across multi-domain audio tasks.
- CLAP/LAION-CLAP is useful for text-query-based audio classification and retrieval, but should be tested for our routing labels.

ASR candidates:

- Whisper remains the safest multilingual ecosystem baseline, especially through whisper.cpp or faster-whisper.
- Canary-Qwen / NVIDIA Canary is a strong current open ASR accuracy candidate.
- NVIDIA Parakeet TDT v2/v3 is a strong speed and long-form/batch transcription candidate.
- IBM Granite Speech and Qwen3-ASR should be tracked as additional open ASR candidates where licenses/resources fit.

Diarization candidates:

- pyannote.audio is still the most common open-source diarization toolkit and a strong default.
- DiariZen is a serious open-source SOTA candidate; 2026 tutorial/benchmark material treats it as leading or very competitive.
- NVIDIA NeMo SortFormer/MSDD are strong alternatives, especially on NVIDIA hardware.

Important limitation:

No audio classifier can classify “all audio” perfectly. AudioSet/YAMNet-style models cover hundreds of event classes and can route speech/music/noise/environmental sounds, but mixed scenes, rare sounds, overlapping speech/music, and low-quality recordings need confidence thresholds and “mixed/unknown” outputs.

Implementation decision:

- Implement audio route as metadata -> speech/music/noise/mixed classifier -> VAD -> language ID -> ASR -> diarization -> translation.
- Do not transcribe music/noise-only audio unless speech confidence is high.
- Default candidate stack: ffprobe + YAMNet/PANNs/OpenBEATs + whisper.cpp/faster-whisper + optional Parakeet/Canary + optional pyannote/DiariZen.

Sources:

- https://www.tensorflow.org/hub/tutorials/yamnet
- https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/README.md
- https://www.codesota.com/audio/classification
- https://arxiv.org/abs/2507.14129
- https://github.com/openai/whisper
- https://github.com/ggml-org/whisper.cpp
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/m-bain/whisperx
- https://www.gladia.io/blog/best-open-source-speech-to-text-models
- https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks
- https://github.com/pyannote/pyannote-audio
- https://arxiv.org/abs/2509.26177
- https://arxiv.org/abs/2604.21507

### 17.6 Video

Confidence: medium for pipeline design; low that a single open model can solve everything.

Video must be decomposed:

- ffprobe metadata
- embedded subtitle extraction
- audio extraction -> audio pipeline
- scene/keyframe detection
- frame classification
- OCR on text-heavy frames
- VLM on selected frames
- optional video-native VLM for short clips or hard summaries

Best practical tool candidates:

- ffmpeg/ffprobe for metadata, streams, audio extraction, subtitles, and frames.
- PySceneDetect or OpenCV for scene/keyframe detection.
- Whisper/faster-whisper/Parakeet/Canary for audio transcription.
- Tesseract/PaddleOCR-VL/Docling for frame OCR or document/screen frames.
- Qwen3-VL/Qwen2.5-VL/InternVL3.5 for frame or short-video VLM route.
- Molmo2 is a major candidate for video grounding/tracking/counting and should be tested when weights/tooling are usable.
- SmolVLM2 is useful for small-device fallback and low-resource video/image summaries.

Important limitation:

Long-video understanding is not solved. Video-MME-v2 exists because older video benchmarks were becoming saturated and misleading. LongVideoBench and LVBench-style findings show open-source long-video models still lag proprietary systems and fail on detailed retrieval/reasoning. Therefore all2text should use a deterministic timeline pipeline first and VLMs only on selected keyframes or chunks.

Implementation decision:

- First implement subtitles and audio transcription.
- Then implement keyframe sampling and OCR on frames.
- Then add VLM summaries on selected frames.
- Only after that test video-native VLMs.

Sources:

- https://ffmpeg.org/
- https://github.com/Breakthrough/PySceneDetect
- https://www.scenedetect.com/similar/
- https://arxiv.org/abs/2604.05015
- https://github.com/MME-Benchmarks/Video-MME-v2
- https://arxiv.org/abs/2407.15754
- https://arxiv.org/abs/2601.10611
- https://arxiv.org/abs/2606.04351

### 17.7 CAD, BIM, scientific, geospatial, and binary formats

Confidence: high for metadata/schema tools, low for deep semantic “understanding” without domain-specific providers.

CAD/BIM candidates:

- ezdxf for DXF is the first Python implementation route.
- IfcOpenShell is the first IFC/BIM route.
- FreeCAD/OpenCascade/CadQuery are external/heavy routes for STEP/IGES/solid geometry.
- DWG remains a hard binary CAD case. It should stay safe-summary unless a configured converter is present.

Scientific candidates:

- h5py/h5netcdf/netCDF4 for HDF5/NetCDF.
- astropy for FITS.
- pyarrow for Parquet/Arrow.
- scipy/numpy for common array files.
- Zarr should be considered as another array/container provider.

Geospatial candidates:

- pyshp, pyproj, shapely for light geospatial extraction.
- GDAL/Rasterio/Fiona/GeoPandas/pyogrio are powerful but packaging-heavy and should remain optional/external until tested.

Binary/executable candidates:

- pefile for PE metadata.
- macholib for Mach-O metadata.
- LIEF for cross-format binary parsing if installable.
- capa for security capability summaries.
- radare2/rabin2 for external deep static analysis, never default execution.

Implementation decision:

- First output metadata/schema/entity summaries, not huge dumps.
- Never execute binaries.
- Never dump huge arrays by default.
- Keep source offsets, samples, counts, dimensions, dtypes, CRS, layers, entity counts, imports/exports, and warnings.

Sources:

- https://ezdxf.readthedocs.io/en/stable/introduction.html
- https://ifcopenshell.org/
- https://github.com/IfcOpenShell/IfcOpenShell
- https://www.unidata.ucar.edu/software/netcdf/software
- https://www.h5py.org/
- https://h5netcdf.org/index.html
- https://mandiant.github.io/capa/
- https://radare2.com/

## 18. Revised implementation priority after second research pass

1. Strengthen `doctor` and discovery first: tools, Python packages, model endpoints, llama.cpp processes, version checks, and clear blockers.
2. Build an internal benchmark harness before adding many heavy providers. The benchmark must cover scanned documents, tables, charts, images, audio classes, ASR, video, CAD/scientific samples, and binary samples.
3. Add Docling provider and one OCR/parser provider candidate: PaddleOCR-VL or GLM-OCR first.
4. Port the devtests image taxonomy and routing tests into all2text.
5. Add SigLIP2/CLIP route classifier provider.
6. Add chart output schema and then test DePlot, UniChart, ChartGemma, and ChartCoder/ChartOCR candidates.
7. Add audio classifier and ASR provider contracts; test YAMNet/PANNs/OpenBEATs/CLAP and whisper.cpp/faster-whisper/Parakeet/Canary.
8. Add video pipeline using ffmpeg/ffprobe, subtitles, audio route, keyframes, OCR, VLM frames. Test video VLMs later.
9. Add CAD/scientific/geospatial/binary schema providers.

## 19. Revised main conclusion

There is no honest single best provider for everything. Some tasks have likely leaders, but most need provider competition. The best all2text design is therefore a ranked, swappable provider system with local benchmarks. The candidates above are not random first hits; they are the current serious open/free candidates found in a second research pass. The next code work should implement evaluation harnesses and provider contracts before hardwiring any one “best” model.
