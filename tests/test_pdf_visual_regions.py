"""Original-SHA + physical PDF page + figure crop proof, no source mutation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from all2text.pdf_visual_regions import (
    _safe_relative_path, _parse_page_list, _candidate_groups,
    _box_to_pixels, verify_original, extract_verified_pdf_regions,
)


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


class FigureCandidateUnitTests(unittest.TestCase):
    def test_adjacent_panels_with_one_citation_caption_are_one_region(self):
        imgs=[{"bbox":(80,550,260,680)},{"bbox":(265,550,445,680)},
              {"bbox":(100,75,130,100)}]
        captions=[{"bbox":(75,512,452,542),
                   "text":"Figure 9: Roughness from zero to one in two renderers."}]
        regions,skip=_candidate_groups(612,792,imgs,captions)
        self.assertEqual(1,len(regions))
        self.assertEqual([0,1],regions[0]["embedded_image_indices"])
        self.assertEqual("figure_crop",regions[0]["region_role"])
        self.assertEqual(0,regions[0]["caption_index"])
        self.assertEqual(1,skip["tiny_embedded_images"])
        self.assertEqual([80,550,445,680],regions[0]["bbox_pdf_points"])

    def test_fullpage_scan_is_document_not_chart(self):
        regions,_=_candidate_groups(612,792,[{"bbox":(0,0,612,792)}],[])
        self.assertEqual(1,len(regions))
        self.assertEqual("full_document_page",regions[0]["region_role"])
        self.assertIsNone(regions[0]["caption_index"])

    def test_malformed_rectangles_fail_closed_and_outside_page_not_cropped(self):
        regions,skipped=_candidate_groups(612,792,[
            {"bbox":(-5,0,200,300)},
            {"bbox":(0,50,20,200)},
            {"bbox":(40,500,250,700)},
        ],[])
        self.assertEqual(1,skipped["invalid_rectangles"])
        self.assertEqual(1,skipped["uncaptioned_decorative_images"])
        self.assertEqual(1,len(regions))
        with self.assertRaisesRegex(ValueError,"outside physical"):
            _box_to_pixels([-10,20,50,80],612,792,1224,1584)

    def test_pdf_bottom_left_to_png_top_left(self):
        pix=_box_to_pixels([50,600,150,700],612,792,1224,1584)
        self.assertEqual((97,181,303,387),pix)

    def test_unsafe_paths_page_lists_and_abusive_candidate_counts(self):
        for bad in ("../x.pdf","/mnt/a.pdf","x\\y.pdf",
                    "folder/../x.pdf","x.txt","", "folder//x.pdf"):
            with self.subTest(path=bad),self.assertRaises(ValueError):
                _safe_relative_path(bad)
        for bad in ([],[0],[True],[1,1],[1,2,3,4,5],
                    [20001],[1.0],["1"]):
            with self.subTest(pages=bad),self.assertRaises(ValueError):
                _parse_page_list(bad)
        imgs=[{"bbox":(float(x),500,float(x+50),680)}
              for x in range(20,570,15)]
        with self.assertRaisesRegex(ValueError,"more than allowed"):
            _candidate_groups(612,792,imgs,[],min_fraction=.0005,max_regions=24)


class OriginalRevisionUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/"originals";self.source.mkdir()
        self.src=self.source/"science"/"paper.pdf";self.src.parent.mkdir()
        self.src.write_bytes(b"%PDF-1.4\nsample-approved-by-local-ledger\n%%EOF\n")
        self.digest=sha(self.src)
        self.catalog=self.root/"approved.json"
        self.ledger=self.root/"complete.json"
        self.catalog.write_text(json.dumps({"sources":[{"kind":"pdf","title":"Local paper",
                                                        "path":"science/paper.pdf"}]}))
        self.ledger.write_text(json.dumps({"items":[{"path":"science/paper.pdf",
            "status":"complete","sha256":self.digest,"bytes_received":self.src.stat().st_size}]}))

    def test_requires_both_catalog_and_completed_receipt_and_real_sha(self):
        path,proof=verify_original(self.source,"science/paper.pdf",self.catalog,self.ledger)
        self.assertEqual(self.src,path)
        self.assertEqual(self.digest,proof["source_sha256"])
        self.assertEqual("Local paper",proof["approved_catalog_title"])
        self.src.write_bytes(self.src.read_bytes()+b"changed")
        with self.assertRaisesRegex(ValueError,"receipt"):
            verify_original(self.source,"science/paper.pdf",self.catalog,self.ledger)

    def test_rejects_wrong_kind_unverified_completion_and_unsafe_alias(self):
        self.catalog.write_text(json.dumps({"sources":[{"kind":"html","path":"science/paper.pdf"}]}))
        with self.assertRaisesRegex(ValueError,"receipt mismatch"):
            verify_original(self.source,"science/paper.pdf",self.catalog,self.ledger)
        self.catalog.write_text(json.dumps({"sources":[{"kind":"pdf","path":"science/paper.pdf"}]}))
        self.ledger.write_text(json.dumps({"items":[{"status":"error","path":"science/paper.pdf",
                                      "sha256":self.digest,"bytes_received":self.src.stat().st_size}]}))
        with self.assertRaisesRegex(ValueError,"receipt mismatch"):
            verify_original(self.source,"science/paper.pdf",self.catalog,self.ledger)
        with self.assertRaises(ValueError):
            verify_original(self.source,"../science/paper.pdf",self.catalog,self.ledger)

    def test_duplicate_catalog_source_is_rejected(self):
        self.catalog.write_text(json.dumps({"sources":[
            {"kind":"pdf","path":"science/paper.pdf"},
            {"kind":"pdf","path":"science/paper.pdf"},
        ]}))
        with self.assertRaisesRegex(ValueError,"not uniquely"):
            verify_original(self.source,"science/paper.pdf",self.catalog,self.ledger)


try:
    import reportlab  # type: ignore
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image,ImageDraw
    REPORTLAB_AVAILABLE=True
except ImportError:
    REPORTLAB_AVAILABLE=False


@unittest.skipUnless(REPORTLAB_AVAILABLE,"reportlab required for synthetic PDF visual fixture")
class SourceBoundedEndToEndTests(OriginalRevisionUnitTests):
    def setUp(self):
        super().setUp()
        self.src=self.source/"science"/"paper.pdf"
        pdf=canvas.Canvas(str(self.src),pagesize=(612,792))
        left=Image.new("RGB",(300,150),"red")
        right=Image.new("RGB",(300,150),"blue")
        pdf.drawImage(ImageReader(left),100,535,width=155,height=85)
        pdf.drawImage(ImageReader(right),260,535,width=155,height=85)
        pdf.setFont("Helvetica",9)
        pdf.drawString(80,514,"Figure 1: Red and blue synthetic comparison panels.")
        pdf.showPage()
        page=Image.new("RGB",(612,792),"white")
        draw=ImageDraw.Draw(page)
        draw.line((100,100,512,100),fill="black",width=3)
        draw.text((100,115),"Mock scan not a chart",fill="black")
        pdf.drawImage(ImageReader(page),0,0,width=612,height=792)
        pdf.save()
        self.digest=sha(self.src)
        self.ledger.write_text(json.dumps({"items":[{
            "path":"science/paper.pdf","status":"complete",
            "sha256":self.digest,"bytes_received":self.src.stat().st_size,
        }]}))

    def test_figure_group_and_fullpage_are_separate_true_pdf_crops(self):
        out=self.root/"derived"
        report=extract_verified_pdf_regions(
            source_root=self.source,relative_pdf_path="science/paper.pdf",
            approved_manifest=self.catalog,completed_ledger=self.ledger,
            physical_pages=[1,2],output_dir=out,max_edge=1000,
        )
        self.assertEqual(2,len(report["regions"]))
        first,second=report["regions"]
        self.assertEqual((1,"figure_crop",2),
                         (first["physical_pdf_page"],first["region_role"],
                          first["embedded_image_count"]))
        self.assertIn("Figure 1: Red and blue",first["caption_text_for_prompt"])
        self.assertEqual((2,"full_document_page",1),
                         (second["physical_pdf_page"],second["region_role"],
                          second["embedded_image_count"]))
        self.assertFalse(first["caption_is_literal_publisher_bytes"])
        self.assertEqual(self.digest,first["original_pdf_sha256"])
        context=json.loads((out/"visual_context.json").read_text())
        self.assertEqual(2,len(context["entries"]))
        for region in report["regions"]:
            cropped=out/region["region_path"]
            self.assertEqual(sha(cropped),region["region_png_sha256"])
            self.assertEqual(region["region_png_sha256"],
                             context["entries"][cropped.name]["image_sha256"])
            self.assertEqual(self.digest,
                             context["entries"][cropped.name]["parent_pdf_sha256"])
            page=Image.open(out/region["rendered_page_path"])
            pixels=page.crop(region["raster_region_pixel_bbox_top_left"])
            self.assertEqual(Image.open(cropped).tobytes(),pixels.tobytes())
        self.assertEqual(self.digest,sha(self.src))
        with self.assertRaisesRegex(ValueError,"already exists"):
            extract_verified_pdf_regions(
                source_root=self.source,relative_pdf_path="science/paper.pdf",
                approved_manifest=self.catalog,completed_ledger=self.ledger,
                physical_pages=[1],output_dir=out,
            )
        with self.assertRaisesRegex(ValueError,"into original corpus"):
            extract_verified_pdf_regions(
                source_root=self.source,relative_pdf_path="science/paper.pdf",
                approved_manifest=self.catalog,completed_ledger=self.ledger,
                physical_pages=[1],output_dir=self.source/"another",
            )


if __name__=="__main__":
    unittest.main()
