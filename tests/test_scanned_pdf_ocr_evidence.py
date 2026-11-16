"""No indexed text is fabricated from OCR; every candidate remains bounded."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from all2text.scanned_pdf_ocr_evidence import (
    _word_records, _pdf_physical_pages, _source_map_error, _private_out_dir,
    extract_ocr_preview, _tesseract_binary_info, _mode_agreement, _pdf_page_rotation,
)


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def sample_tsv(token="Read",left=22,word_confidence=91.34):
    return (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        f"5\t1\t1\t1\t1\t1\t{left}\t40\t75\t19\t{word_confidence}\t{token}\n"
        "5\t1\t1\t1\t1\t2\t100\t40\t74\t20\t88.20\tcarefully\n"
        "5\t1\t1\t1\t2\t1\t30\t100\t50\t20\t95.0\tAfter\n"
        "5\t1\t1\t1\t2\t2\t84\t100\t48\t20\t96.0\tthis\n"
    )


class OCRProofUnitTests(unittest.TestCase):
    def test_source_word_coordinates_not_fabricated(self):
        words,text,stats=_word_records(sample_tsv(),400,250)
        self.assertEqual(4,len(words))
        self.assertEqual("Read carefully\nAfter this",text)
        self.assertEqual([22,40,97,59],words[0]["bbox_pixel_top_left"])
        self.assertEqual([1,1,1],words[0]["line_key"])
        self.assertFalse("confidence_probability" in words[0])
        self.assertEqual(4,stats["word_count"])
        self.assertTrue(stats["ocr_quality_not_verified"])

    def test_out_of_bounds_word_or_incomplete_tsv_rejected(self):
        with self.assertRaisesRegex(ValueError,"outside rendered physical page"):
            _word_records(sample_tsv(left=390),400,250)
        with self.assertRaisesRegex(ValueError,"confidence"):
            _word_records(sample_tsv(word_confidence=101),400,250)
        with self.assertRaisesRegex(ValueError,"unrecognized Tesseract"):
            _word_records("word\tconfidence\nnot-enough\t93",400,250)
        with self.assertRaisesRegex(ValueError,"unexpectedly long"):
            _word_records(sample_tsv(token="A"*251),400,250)

    def test_distinguishes_two_column_reading_order_from_recognition(self):
        left="COLUMN ONE A coating changes material reflections."
        right="COLUMN TWO The caption may contradict the figure."
        table="TABLE Q1 10 Q2 20"
        primary="\n".join([left,table,right])
        secondary="\n".join([left,right,table])
        proof=_mode_agreement(primary,secondary)
        self.assertEqual(1.0,proof["bag_word_overlap"])
        self.assertTrue(proof["needs_layout_or_ocr_review"])
        self.assertEqual("probable_reading_order_disagreement",proof["status"])
        self.assertTrue(proof["no_ground_truth_accuracy_claim"])
        stable=_mode_agreement(primary,primary)
        self.assertEqual("no_major_mode_disagreement_detected_not_verified",stable["status"])
        self.assertFalse(stable["needs_layout_or_ocr_review"])
        for result in (proof,stable):
            self.assertTrue(result["no_ground_truth_accuracy_claim"])
        # Actual cloth page eight had 0.878 word overlap and 0.532
        # ordering similarity; this must be REVIEW, never an all-clear.
        mixed=_mode_agreement(
            "x y z a b c one two three four five six seven eight nine",
            "one two three four five six seven eight nine x y changed a b c",
        )
        self.assertTrue(mixed["needs_layout_or_ocr_review"])
        self.assertNotEqual("no_major_mode_disagreement_detected_not_verified",mixed["status"])

    def test_missing_languages_fail_without_downloads(self):
        with self.assertRaisesRegex(ValueError,"language not installed"):
            _tesseract_binary_info("zzz")

    def test_original_map_must_be_unresolved_visual_only(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            db=root/"map.sqlite3"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE originals (source_path TEXT,status TEXT,source_sha256 TEXT,error TEXT)")
                c.execute("INSERT INTO originals VALUES('a.pdf','error',?,'Visual-only original not eligible for bounded OCR; human figure interpretation required')",("a"*64,))
            self.assertEqual("error",_source_map_error(db,"a.pdf","a"*64)["status"])
            with self.assertRaisesRegex(ValueError,"SHA mismatch"):
                _source_map_error(db,"a.pdf","b"*64)
            with sqlite3.connect(db) as c:
                c.execute("UPDATE originals SET status='complete'")
            with self.assertRaisesRegex(ValueError,"not an explicitly unresolved"):
                _source_map_error(db,"a.pdf","a"*64)

    def test_bad_page_and_mode_rejected_before_original_access(self):
        args={"source_root":Path("/path/not/here"),"relative_pdf_path":"x.pdf",
              "approved_manifest":Path("/unknown"),"completed_ledger":Path("/unknown"),
              "source_map_db":Path("/unknown"),"native_filedb":Path("/unknown"),
              "physical_pages":[1],
              "output_dir":Path("/unknown")}
        for update in ({"physical_pages":[]},{"physical_pages":[1,1]},
                       {"physical_pages":[0]},{"physical_pages":[1,2,3,4]},
                       {"physical_pages":[True]},{"dpi":500},{"dpi":120.0},
                       {"psm":2},{"psm":True},{"language":"fra"},
                       {"comparison_psm":3},{"comparison_psm":5},{"comparison_psm":True}):
            with self.subTest(case=update),self.assertRaisesRegex(ValueError,"strict bounds"):
                extract_ocr_preview(**(args|update))


try:
    import reportlab
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image,ImageDraw,ImageFont
    HAS_PDF_FIXTURE=True
except ImportError:
    HAS_PDF_FIXTURE=False

REQUIRED_COMMANDS=("pdftoppm","pdfinfo","tesseract")
CAN_RUN=HAS_PDF_FIXTURE and all(shutil.which(cmd) for cmd in REQUIRED_COMMANDS)


@unittest.skipUnless(CAN_RUN,"need locally installed ReportLab, PIL, Poppler and Tesseract")
class SourcePinnedEndToEndOCRTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.corpus=self.root/"originals"
        self.corpus.mkdir()
        self.rel="imagery/synthetic-scan.pdf"
        self.source=self.corpus/self.rel
        self.source.parent.mkdir()
        self.text_lines=[
            "Original documents remain unchanged.",
            "Scientific chart values require source evidence.",
            "The model reports uncertainty when text is unreadable.",
            "Material roughness and lighting affect rendering.",
            "Document layout and reading order matter.",
        ]
        scan=Image.new("RGB",(1653,2338),"white")
        draw=ImageDraw.Draw(scan)
        font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",34)
        for n,line in enumerate(self.text_lines):
            draw.text((95,180+n*98),line,font=font,fill="black")
        pdf=canvas.Canvas(str(self.source),pagesize=(595,842))
        pdf.drawImage(ImageReader(scan),0,0,width=595,height=842)
        pdf.save()
        self.digest=hash_file(self.source)
        self.approved=self.root/"approved.json"
        self.approved.write_text(json.dumps({"sources":[{"kind":"pdf","path":self.rel,
              "title":"Original Synthetic Image Scan"}]}))
        self.ledger=self.root/"ledger.json"
        self.ledger.write_text(json.dumps({"items":[{"status":"complete","path":self.rel,
                "sha256":self.digest,"bytes_received":self.source.stat().st_size}]}))
        self.native=self.root/"native"
        self.native.mkdir()
        self.source_map=self.native/"source-map.sqlite3"
        with sqlite3.connect(self.source_map) as db:
            db.execute("CREATE TABLE originals (source_path TEXT,status TEXT,source_sha256 TEXT,error TEXT)")
            db.execute("INSERT INTO originals VALUES(?,?,?,?)",(self.rel,"error",self.digest,
                         "ValueError: Visual-only original not eligible for bounded OCR; human figure interpretation required"))
        self.filedb=self.native/"filesystem.sqlite3"
        with sqlite3.connect(self.filedb) as db:
            db.execute("CREATE TABLE filesystem_entries(id INTEGER,relative_path_display TEXT,entry_type TEXT)")
            db.execute("CREATE TABLE content_chunks(filesystem_entry_id INTEGER,embedding_blob BLOB)")
            db.execute("INSERT INTO filesystem_entries VALUES (107,?,'file')",(self.rel,))
        self.audit=self.root/"search-audit"
        self.audit.mkdir()

    def call(self,*,psm=3,dpi=220,output=None,source_root=None,compare=None):
        return extract_ocr_preview(
            source_root=source_root or self.corpus,relative_pdf_path=self.rel,
            approved_manifest=self.approved,completed_ledger=self.ledger,
            source_map_db=self.source_map,native_filedb=self.filedb,physical_pages=[1],
            output_dir=output or self.audit/f"psm{psm}_{dpi}",
            dpi=dpi,psm=psm,language="eng",comparison_psm=compare,
        )

    def test_exact_original_identity_word_boxes_and_partial_scope(self):
        before=[hash_file(p) for p in (self.source,self.source_map,self.ledger,self.approved)]
        result=self.call()
        self.assertEqual("error",result["source_map"]["status"])
        self.assertEqual(self.digest,result["source"]["source_sha256"])
        self.assertEqual(107,result["canonical_native_filedb"]["filesystem_entry_id"])
        self.assertEqual(0,result["canonical_native_filedb"]["existing_native_chunk_count"])
        self.assertTrue(result["canonical_native_filedb"]["no_new_native_index_created"])
        self.assertEqual(1,result["physical_pages_processed"])
        self.assertFalse(result["full_original_extracted"])
        self.assertFalse(result["original_pdf_modified"])
        self.assertFalse(result["source_map_modified"])
        page=result["pages"][0]
        self.assertTrue(page["do_not_promote_as_completed_original"])
        self.assertGreaterEqual(page["ocr_stats"]["word_count"],25)
        self.assertGreater(page["ocr_stats"]["mean_word_confidence_not_calibrated"],60)
        self.assertTrue(page["ocr_stats"]["ocr_quality_not_verified"])
        root=self.audit/"psm3_220"
        for kind,name in (("raster_png_sha256","page_0001.png"),
                          ("transcript_candidate_sha256","page_0001.txt"),
                          ("raw_tesseract_tsv_sha256","page_0001.tsv"),
                          ("word_boxes_sha256","page_0001_words.json")):
            self.assertEqual(page[kind],hash_file(root/name))
        words=json.loads((root/"page_0001_words.json").read_text())
        for word in words:
            left,top,right,bottom=word["bbox_pixel_top_left"]
            self.assertGreaterEqual(left,0)
            self.assertLessEqual(right,page["raster_pixels"][0])
            self.assertLessEqual(bottom,page["raster_pixels"][1])
        text=(root/"page_0001.txt").read_text()
        self.assertIn("Original documents remain unchanged",text)
        self.assertIn("Material roughness and lighting affect rendering",text)
        self.assertEqual(before,[hash_file(p) for p in (self.source,self.source_map,self.ledger,self.approved)])
        with self.assertRaisesRegex(ValueError,"overwrit"):
            self.call()

    def test_comparison_modes_have_both_exactly_reproducible_source_raster(self):
        output=self.audit/"compare_psm3_4"
        d=self.call(output=output,compare=4)
        page=d["pages"][0]
        other=page["comparison_ocr_mode"]
        self.assertEqual(4,other["psm"])
        self.assertEqual(other["raster_sha256"],page["raster_png_sha256"])
        self.assertEqual(other["text_candidate_sha256"],
                         hash_file(output/other["text_candidate_file"]))
        self.assertEqual(other["raw_tsv_sha256"],
                         hash_file(output/other["raw_tsv_file"]))
        self.assertEqual(other["word_boxes_sha256"],
                         hash_file(output/other["word_boxes_file"]))
        self.assertTrue(other["mode_disagreement"]["no_ground_truth_accuracy_claim"])
        self.assertFalse(d["full_original_extracted"])

    def test_rotated_source_page_remains_its_own_physical_page_with_raster_coords(self):
        # ReportLab's rotation annotation is independently inspected with
        # pdfinfo, not guessed from the output image width/height.
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from PIL import Image,ImageDraw,ImageFont
        scan=Image.new("RGB",(1653,2338),"white")
        d=ImageDraw.Draw(scan)
        font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",35)
        d.text((100,230),"Rotated physical PDF page evidence.",fill="black",font=font)
        # /Rotate=90 is a display transformation. Counter-rotate the
        # embedded pixels so the visual text is upright in Poppler's
        # rendered coordinate system, as a correctly oriented scan should be.
        pdf=canvas.Canvas(str(self.source),pagesize=(842,595))
        pdf.setPageRotation(90)
        pdf.drawImage(ImageReader(scan.rotate(90,expand=True)),
                      0,0,width=842,height=595)
        pdf.save()
        self.digest=hash_file(self.source)
        self.ledger.write_text(json.dumps({"items":[{"status":"complete", "path":self.rel,
            "sha256":self.digest,"bytes_received":self.source.stat().st_size}]}))
        with sqlite3.connect(self.source_map) as db:
            db.execute("UPDATE originals SET source_sha256=?",(self.digest,))
        self.assertEqual(90,_pdf_page_rotation(self.source,1))
        out=self.audit/"rotated_page"
        result=self.call(output=out)
        page=result["pages"][0]
        self.assertEqual(1,page["physical_pdf_page"])
        self.assertEqual(90,page["physical_pdf_page_rotation_degrees"])
        self.assertIn("Poppler_rendered_page",page["word_box_coordinate_scope"])
        self.assertTrue(page["do_not_promote_as_completed_original"])
        self.assertEqual(page["raster_png_sha256"],hash_file(out/"page_0001.png"))

    def test_duplicate_native_filedb_entry_refuses_ocr_candidate(self):
        with sqlite3.connect(self.filedb) as db:
            db.execute("INSERT INTO filesystem_entries VALUES (108,?,'file')",(self.rel,))
        target=self.audit/"duplicate_native"
        with self.assertRaisesRegex(ValueError,"no unique canonical native"):
            self.call(output=target)
        self.assertFalse(target.exists())

    def test_source_revision_and_stale_catalog_fail_without_creating_result(self):
        before=self.digest
        self.source.write_bytes(self.source.read_bytes()+b"changed")
        outfile=self.audit/"changed_result"
        with self.assertRaisesRegex(ValueError,"receipt"):
            self.call(output=outfile)
        self.assertFalse(outfile.exists())
        self.assertNotEqual(before,hash_file(self.source))

    def test_forbid_original_or_source_map_direct_output(self):
        with self.assertRaisesRegex(ValueError,"cannot write to original"):
            self.call(output=self.corpus/"ocr-preview")
        with self.assertRaisesRegex(ValueError,"cannot write to original"):
            self.call(output=self.native/"ocr-preview")
        self.assertFalse((self.corpus/"ocr-preview").exists())
        self.assertFalse((self.native/"ocr-preview").exists())


if __name__=="__main__":
    unittest.main()
