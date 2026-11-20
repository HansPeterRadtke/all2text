"""A context hint is usable only against the exact original image hash."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image

from all2text import run
from all2text.config import config_from_dict, options_with_profile
from all2text.models import RunOptions
from all2text.visual_prompt import (
    load_source_context_manifest, verified_image_context,
)


class VisualContextManifestTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.input=self.root/"input"
        self.input.mkdir()
        self.image=self.input/"chart.png"
        im=Image.new("RGB",(300,200),"white")
        from PIL import ImageDraw
        drawing=ImageDraw.Draw(im)
        drawing.line((30,10,30,178),fill="black",width=2)
        drawing.line((30,178,260,178),fill="black",width=2)
        drawing.rectangle((55,60,85,177),fill="#A04040")
        drawing.rectangle((110,40,140,177),fill="#A04040")
        im.save(self.image)
        self.digest=hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.manifest=self.root/"context.json"

    def write_manifest(self, *, sha=None, role="full_document_page"):
        self.manifest.write_text(json.dumps({
            "schema":"all2text.visual_context.v1",
            "entries":{"chart.png":{
                "image_sha256":sha or self.digest,
                "region_role":role,
                "physical_page":7,
                "document_topic":"Research paper on physically based rendering",
                "section_heading":"Experimental comparison",
                "figure_caption":"A separate chart should be extracted from its page",
                "nearby_text":"The figure is one of several regions of a page",
            }},
        }))
        return self.manifest

    def test_exact_sha_pinned_context_overrides_page_vs_chart_route(self):
        manifest=self.write_manifest()
        config=config_from_dict({"modules":{"image":{
            "backend":"image_analysis_backend",
            "source_context_manifest":str(manifest)}}})
        out=self.root/"output"
        data=run(self.input,out,options=options_with_profile(RunOptions(),"pip"),config=config)
        row=next(x for x in data["entries"] if x["entry_type"]=="file")
        profile=row["converter_metadata"]["profile"]
        route=row["converter_metadata"]["route"]
        self.assertEqual("document_page",profile["taxonomy"])
        self.assertEqual("sha256_verified_full_document_page_context",profile["taxonomy_source"])
        self.assertEqual("document",route["family"])
        self.assertEqual(False,profile["chart_candidate"])
        self.assertEqual("sha256_verified_image_context",row["converter_metadata"]["source_context_evidence"]["status"])
        self.assertFalse(row["vlm_used"])
        self.assertFalse(row["ocr_used"])
        self.assertNotIn("Research paper on physically based rendering",
                         json.dumps(row["converter_metadata"]["source_context_evidence"]))

    def test_stale_context_cannot_change_routing(self):
        self.write_manifest(sha="1"*64)
        config=config_from_dict({"modules":{"image":{
            "backend":"image_analysis_backend",
            "source_context_manifest":str(self.manifest)}}})
        x=run(self.input,self.root/"out",options=options_with_profile(RunOptions(),"pip"),config=config)
        row=next(y for y in x["entries"] if y["entry_type"]=="file")
        self.assertEqual("rejected_context_source_identity",row["converter_metadata"]["source_context_evidence"]["status"])
        self.assertTrue(any("visual_context_rejected" in w for w in row["warnings"]))
        self.assertNotEqual("sha256_verified_full_document_page_context",row["converter_metadata"]["profile"]["taxonomy_source"])

    def test_invalid_and_unsafe_manifests_fail_before_conversion(self):
        self.write_manifest()
        self.assertEqual(1,len(load_source_context_manifest(self.manifest)))
        bad=json.loads(self.manifest.read_text())
        bad["entries"]["../other.png"]=bad["entries"].pop("chart.png")
        self.manifest.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"unsafe visual"):
            load_source_context_manifest(self.manifest)
        self.write_manifest()
        with self.image.open("ab") as f:
            f.write(b"source revision has changed")
        with self.assertRaisesRegex(ValueError,"does not match"):
            verified_image_context(self.image,load_source_context_manifest(self.manifest)["chart.png"])

    def test_source_role_is_not_inferred_from_filename(self):
        self.write_manifest(role="figure_crop")
        config=config_from_dict({"modules":{"image":{
            "backend":"image_analysis_backend","source_context_manifest":str(self.manifest)}}})
        x=run(self.input,self.root/"figure_out",options=options_with_profile(RunOptions(),"pip"),config=config)
        row=next(y for y in x["entries"] if y["entry_type"]=="file")
        profile=row["converter_metadata"]["profile"]
        self.assertNotEqual("sha256_verified_full_document_page_context",profile["taxonomy_source"])
        self.assertEqual("sha256_verified_image_context",row["converter_metadata"]["source_context_evidence"]["status"])
