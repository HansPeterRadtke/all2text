"""Conservative reading order from word geometry is evidence, not truth."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from all2text.ocr_layout_candidates import two_column_candidate
from all2text.scanned_pdf_ocr_evidence import _word_records


def fake_word(text, left, top, block, wordnum=1, right=None):
    return {
        "text":text,
        "bbox_pixel_top_left":[left,top,right or left+len(text)*12,top+25],
        "tesseract_confidence_not_calibrated":92.0,
        "line_key":[block,1,1],
        "word_position":wordnum,
    }


class TwoColumnGeometryTests(unittest.TestCase):
    def test_two_columns_before_table_preserves_one_line_once(self):
        raw=[
            fake_word("LEFT1",80,50,1, right=310),
            fake_word("LEFT2",80,100,2,right=305),
            fake_word("RIGHT1",850,50,3,right=1100),
            fake_word("RIGHT2",850,100,4,right=1100),
            fake_word("TABLE",180,800,5,right=500),
        ]
        result=two_column_candidate(words=raw,image_width=1400,image_height=1800)
        self.assertEqual("unverified_two_column_reading_order_candidate",result["status"])
        self.assertEqual("LEFT1\nLEFT2\nRIGHT1\nRIGHT2\nTABLE",result["text_candidate"])
        self.assertTrue(result["do_not_promote_to_native_filedb"])
        self.assertFalse(result["independent_source_ground_truth"])
        self.assertFalse(result["word_boxes_rearranged"])
        self.assertEqual(5,result["line_count"])

    def test_one_column_never_claims_column_proof(self):
        words=[fake_word(f"line {i}",100,50+i*50,i+1,right=400) for i in range(8)]
        r=two_column_candidate(words=words,image_width=1400,image_height=1800)
        self.assertEqual("abstained",r["status"])
        self.assertIsNone(r["text_candidate"])
        self.assertIn("no_repeated_vertical_overlap",r["reason"])

    def test_ambiguous_spanning_heading_abstains(self):
        words=[
            fake_word("LEFT1",80,100,1,right=300),
            fake_word("LEFT2",80,150,2,right=300),
            fake_word("RIGHT1",800,100,3,right=1050),
            fake_word("RIGHT2",800,150,4,right=1040),
            fake_word("CROSSING",500,125,5,right=900),
        ]
        r=two_column_candidate(words=words,image_width=1400,image_height=1800)
        self.assertEqual("abstained",r["status"])
        self.assertIn("spanning",r["reason"])

    def test_inconsistent_boundaries_abstain_not_invent_columns(self):
        words=[
            fake_word("L1",100,100,1,right=290),
            fake_word("L2",100,200,2,right=290),
            fake_word("R1",1100,100,3,right=1200),
            fake_word("R2",700,200,4,right=950),
        ]
        r=two_column_candidate(words=words,image_width=1600,image_height=1800)
        self.assertEqual("abstained",r["status"])
        self.assertIn("inconsistent",r["reason"])

    def test_duplicate_word_index_and_unsafe_budget_rejected(self):
        words=[
            fake_word("ONE",80,100,1,wordnum=1),
            fake_word("TWO",150,100,1,wordnum=1),
        ]
        with self.assertRaisesRegex(ValueError,"repeated Tesseract"):
            two_column_candidate(words=words,image_width=1400,image_height=1800)
        with self.assertRaisesRegex(ValueError,"unbounded"):
            two_column_candidate(words=[],image_width=True,image_height=500)
        with self.assertRaisesRegex(ValueError,"unbounded"):
            two_column_candidate(words=words*20000,image_width=1000,image_height=1000)

    def test_candidate_deep_layout_ambiguity_is_not_automatic_fix(self):
        source=[
            fake_word("Caption",80,100,1,right=300),
            fake_word("A",80,150,2,right=300),
            fake_word("B",850,100,3,right=1100),
            fake_word("C",850,150,4,right=1100),
        ]
        result=two_column_candidate(words=source,image_width=1400,image_height=1800)
        self.assertEqual("unverified_two_column_reading_order_candidate",result["status"])
        self.assertIn("not",result["warning"].lower())
        self.assertTrue(result["do_not_promote_to_native_filedb"])


class RealSyntheticKnownTextTests(unittest.TestCase):
    """Read-only existing benchmark fixtures are NOT assumed to be present."""
    def test_synthetic_two_column_pdf_benchmark_can_be_reordered(self):
        try:
            import reportlab
            from PIL import Image,ImageDraw,ImageFont
        except ImportError:
            self.skipTest("optional reportlab/Pillow fixture dependencies unavailable")
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        font=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        if not font.exists():
            self.skipTest("synthetic reference font not installed")
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            left=["COLUMN ONE","A coating changes a surface reflection.",
                  "Science diagrams contain connected arrows.",
                  "Original images need exact page positions."]
            right=["COLUMN TWO","Chart axes and units must be preserved.",
                   "Some letters are difficult to decipher.",
                   "Every uncertain value needs a warning."]
            table=["TABLE DATA","Month Q1 Q2 Q3",
                   "Output 10 20 30","Input 14 25 36"]
            reference="\n".join(left+right+table)
            im=Image.new("RGB",(1653,2338),"white")
            d=ImageDraw.Draw(im)
            small=ImageFont.truetype(str(font),25)
            medium=ImageFont.truetype(str(font),31)
            for i,txt in enumerate(left):
                d.text((85,145+i*105),txt,font=small,fill="black")
            for i,txt in enumerate(right):
                d.text((850,145+i*105),txt,font=small,fill="black")
            for i,txt in enumerate(table):
                d.text((180,960+i*105),txt,font=medium,fill="black")
            pdf=root/"original.pdf"
            c=canvas.Canvas(str(pdf),pagesize=(595,842))
            c.drawImage(ImageReader(im),0,0,width=595,height=842)
            c.save()
            prefix=root/"raster"
            p=subprocess.run(["pdftoppm","-f","1","-l","1",
                     "-singlefile","-r","220","-gray","-png",
                     str(pdf),str(prefix)],capture_output=True,timeout=30)
            self.assertEqual(0,p.returncode)
            with Image.open(prefix.with_suffix(".png")) as image:
                raster_size=image.size
            q=subprocess.run(["tesseract",str(prefix.with_suffix(".png")),
                         "stdout","-l","eng","--psm","3","tsv"],
                         capture_output=True,text=True,timeout=40)
            self.assertEqual(0,q.returncode)
            words,raw,_=_word_records(q.stdout,*raster_size)
            result=two_column_candidate(
                words=words,image_width=raster_size[0],image_height=raster_size[1])
            self.assertEqual("unverified_two_column_reading_order_candidate",result["status"])
            self.assertEqual(reference, result["text_candidate"])
            self.assertNotEqual(reference,raw)
            self.assertTrue(result["do_not_promote_to_native_filedb"])


if __name__=="__main__":
    unittest.main()
