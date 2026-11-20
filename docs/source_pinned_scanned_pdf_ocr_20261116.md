# Source-pinned scanned PDF OCR, 2026-11-16

Purpose: a bounded, source-revision-verifiable and quality-labelled OCR
PREVIEW, not replacement of the Knowledge Library, no new native index,
no full source transcription claim and no modification of original PDFs.

## Current actual source gap

The canonical Raspi original library has 17,717 approved downloaded
sources, with 17,715 original text extractions marked complete and
two explicitly image-only source-map exceptions:
- 2025 Ray-Wave Hybrid Shading cloth rendering paper: 16 pages, about
  12.9 MB, original SHA starts 61d0820e3fef.
- Philippines Revised Corporation Code original RA11232: 53 pages,
  about 30.3 MB, original SHA starts c5eafee3eeb7.

The Infra extractor has a 25 MiB and 14-page OCR bound, so these
documents were deliberately left in source-map error state rather than
generating unverified full-document text. This sidecar does not bypass
those production safety limits or alter the source-map.

## Source proofs and safe conversion

scripts/source_pinned_scanned_ocr.py uses the actual All2Text publisher
source validator. It requires one approved original PDF, exactly one
completed download ledger receipt, matching file size and full original
SHA-256, and a read-only canonical source-map entry with an original
SHA match and the explicit image-only exception reason. Previously
extracted files are refused. Each invocation processes no more than
three distinct 1-based physical pages of an original no more than 100
pages long. It does not permit a blind folder-wide scan or full
reconversion of a 53-page law book.

Poppler renders selected pages to grayscale PNG with bounded DPI
(120-260) and pixel/byte limits. It preserves the original page
number and the PDF /Rotate value. For a physically rotated page,
Tesseract word boxes are referenced explicitly to the *rendered
top-left pixel coordinates after Poppler orientation*, never
pretended to be original unrotated PDF-point locations. The original
full-file SHA is checked again before manifest publication.

Tesseract local 5.3.0 uses only installed English/German tessdata
and a 1-thread child process, with no remote APIs or model downloads.
For each page it preserves the rendered raster SHA, exact raw TSV SHA,
OCR text candidate SHA, each recognized word and its pixel bbox,
line grouping, individual uncalibrated engine confidence and
traineddata SHA. Source text is untrusted data and is not executed
as a model instruction. All page candidates remain in a new private
output folder outside the original/derived/native database trees.
An existing output is never overwritten. The final manifest explicitly
marks full_original_extracted=false and
do_not_promote_as_completed_original=true.

Optional --compare-psm 4 runs an independent segmentation of the
same SHA-verified image. The tool records a token-bag overlap and
token-sequence alignment between PSM3 and PSM4, each with its
own checksummed output. When the word set agrees but sequence differs
strongly, this flags probable reading-order ambiguity. When both
differ, it flags mixed recognition/ordering disagreement. This
does not decide which transcript is correct. Two agreeing OCR engines
or modes would still not constitute accuracy evidence.

## Actual local results

Four real physical pages were sampled, all 220 DPI, English Tesseract,
with PSM3 plus comparison PSM4:
- Philippines law page 1 (physical /Rotate=0): 134 OCR words,
  25 lines, mean Tesseract word confidence 91.99. The two modes
  largely agree in order (sequence ratio 0.996), yet the text has
  visible errors, including "Metra Manila" and the Republic Act header.
  Neither mode is independently verified as accurate.
- Philippines law page 2 (/Rotate=90): 618 OCR words, 73 lines,
  mean confidence 95.82. It was previously refused due to unhandled
  rotation. With physical rotation preserved and raster word boxes
  correctly scoped, OCR succeeds. The alternative mode recovers much
  the same word set (overlap 0.958), but orders it differently
  (sequence ratio 0.573). It must be reviewed before indexing.
- Cloth rendering paper page 1: 591 words, 65 lines, mean confidence
  95.74, but 0.733 sequence agreement between page-layout modes
  despite 0.962 word-bag overlap. It includes material shading text,
  figure caption, and multi-column paper content.
- Cloth rendering paper page 8: 792 words, 89 lines, mean confidence
  88.03 and 82 words below Tesseract's confidence 60. The modes
  overlap 0.878 by word bag but have sequence ratio 0.532, alongside
  visibly poor diagram/equation fragments. A first audit wrongly
  marked this as no major disagreement because the threshold
  missed the 0.85-0.90 overlap interval. That bug was corrected and
  separately reconciled against the stored hash-verified OCR outputs;
  original audit files were preserved, not overwritten.

These figures are observations from OCR on four pages. They are
not true-source CER/WER measurements, full OCR completion, correct
legal transcriptions, or proof of mathematical equation accuracy.

## Synthetic independent-text benchmark

The scripts/benchmark_scanned_ocr_modes.py benchmark generates two
raster-only PDF pages from separately authored known text, not from
Tesseract output. It measures exact character error rate and word
error rate using Levenshtein distance. It sweeps 150/220 DPI and
PSM 3/4/6/11. All 16 run variants save their source PDF and reference
SHA, per-image SHA, recognized text/TSV and exact quality measures.

The simple single-column page achieved 0% CER and WER for all
variants. The page with two columns and a table scored 35.3%-45.2%
CER even with Tesseract mean word confidence typically around
95-96%. The error is mainly *reading order* (table and right column
interleaved/misordered), not a failure to recognize the letters. The
two-column score is against the deliberately specified source
reading order; different physical layouts may need other reading
rules. This small, clean synthetic benchmark cannot establish
general OCR accuracy on the legal or graphics PDFs.

All outputs, benchmark references, live mode-comparison reconciliation,
initial rejected rotation/flag attempts and source checksums are private
under Raspi:

/data/var/knowmoredirt/knowledge-library/search-audit/scanned-page-ocr-20261116/

## Next independent quality gate

A trustworthy layout-aware document pipeline is still required. Official
PaddleOCR documentation describes PP-OCRv6 Medium (June 2026, 34.5M
parameters, geared to CPU inference) for recognition, and
PaddleOCR-VL-1.6 (0.9B, with PP-DocLayoutV3) for richer page,
table, equation and chart structure. These vendor benchmark claims
were NOT locally measured in this task. No new model was installed
because shared models and the active KMD summary workers take
precedence, and no new dependency/model weights were needed for
this bounded Tesseract evidence pilot. Before production ingestion,
benchmark a current trained layout model against independently
corrected legal and scientific pages, assess text CER, table cells,
reading order, equation/figure labeling and provenance, and only
then add approved original-linked representations to the *one*
existing native KMD FileDB.

Official references checked November 16:
https://github.com/PaddlePaddle/PaddleOCR/releases
https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/index.en.md

No complete PDF has been marked recovered; originals, existing
KnowMoreDiRT indexes and the two running recursive summary workers
were not changed.

## Final native identity and mode comparison acceptance

The operator now additionally requires the EXISTING canonical native
KnowMoreDiRT FileDB in read-only mode and insists on exactly one file
entry with the approved original-relative path. It reports the current
number of chunks/embeddings and never creates a new database or adds
rows. On the real original corpus, the scanned law is FileDB entry
9913 and the cloth research paper entry 19057; both had zero chunks
before this preview and remained source-map errors afterward.

The final source-linked candidate sets are in the private audit's
final_law_page1_2 and final_cloth_page1_8 directories. All four pages
were reprocessed with PSM3 and PSM4, at 220 DPI, with independently
hashed raster, word-level TSV, text candidate, OCR language data and
same original SHA identities. The comparison classifies law page 1
as no major mode disagreement but STILL not verified; law page 2,
cloth page 1 and cloth page 8 all require layout/OCR review. The law
page 2 /Rotate=90 was explicitly recorded and word coordinates refer
to the Poppler-orientated top-left raster, not PDF point coordinates.

The corrected mode-comparison logic was validated against the saved
originals and then replayed without overwriting earlier audit files.
The first attempt falsely cleared cloth page 8 despite 0.532 sequence
similarity and 0.878 word-bag overlap. The corrected rule flags that
as mixed reading-order/recognition disagreement and the synthetic
regression case specifically prevents the prior false all-clear.
Output is always untrusted machine OCR; this task does NOT claim
verified legal text or full-document extraction.

## November 19 continuation: separately hashed two-column order candidate

The earlier real PDFs and synthetic two-column benchmark revealed that
Tesseract's highly confident individual WORDS do not establish the correct
reading ORDER. The prior source program exposed only the original PSM3 and
alternate PSM4 text, whose ordering can differ significantly. A separate
bounded, opt-in and **never authoritative** candidate is now available via
`--propose-column-order`. Its implementation reuses the exact source-PDF
SHA, original physical page/rotation and the same Tesseract TSV word and
pixel bounding boxes as the primary OCR; it does not run an extra model or
rewrite the primary transcript.

It only proposes an ordering after at least two independent vertically
overlapping and horizontally separated pairs of text lines corroborate
two columns with stable starts, a real gap, and no cross-column text
inside the two-column band. It conservatively sorts preceding full-width
headers, left-column text, right-column text, and later full-width text
such as a table. It preserves all original OCR words and their exact
bounding boxes and separately saves a SHA-256-linked text candidate. If
there is any ambiguous crossing, inconsistent column starts, too many
lines or insufficient evidence, it **abstains**. It never changes the
original-word-box TSV or source text and marks
`do_not_promote_to_native_filedb=true`, even when the candidate looks good.

Independent, model-free synthetic source-text acceptance used the existing
two-page scan with known authored text, Tesseract versions and exact
raster/TSV proofs. On the first, single-column page, the candidate correctly
abstained and the original PSM3 already achieved zero CER/WER. On the
second page, the initial PSM3 output put the table between the two columns,
so it measured **35.29% character error** and **51.85% word error** against
the authored source reading order. At both 150 and 220 DPI, an independently
saved two-column candidate preserved the same OCR words but changed their
sequence to achieve **zero CER and zero WER on this one synthetic page**.
PSM11 also produced a near-exact alternative (0.31% CER), while PSM4/6
abstained because they had interleaved lines that cannot safely be split
from these boxes. Eight one-column combinations abstained; the original
OCR was unchanged in all sixteen benchmark variants.

The same optional candidate was applied to three real, original-revision-
verified PDF pages: the rotated second page of the Philippine RA11232 law,
and pages one and eight of the cloth-rendering paper. **All three
abstained** for conflicting line geometry or inconsistent column origins.
This is an intended conservative outcome. It would be false to claim that
high-confidence legal text, scientific formulae, page captions or table
cells have been repaired. A proper trained layout detector and independent
source transcription are still needed before KMD indexing.

The new generated receipts, including original source-map/FileDB identity,
original-PDF SHA, independent synthetic ground truth, each primary text
SHA, separate candidate SHA or explicit abstention reason, are under
Raspi's private `search-audit/scanned-page-ocr-20261116/` directory,
in the November 19-specific subfolders. No source originals or canonical
FileDB records changed and both source-disjoint KMD summary workers ran
throughout the test.
