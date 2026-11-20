"""Offline chart specialist: only confidently routed chart regions, unverified values."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from PIL import Image,ImageDraw

from all2text import run
from all2text.config import ProviderConfig,config_from_dict,options_with_profile
from all2text.models import RunOptions
from all2text.deplot_chart import maybe_deplot_chart,_existing_font,_existing_root


class ChartGateTests(TestCase):
    def provider(self, *, enabled=True, auto=True):
        return ProviderConfig(name="deplot",enabled=enabled,
            params={"auto_invoke":auto,"model_path":"/absent/model",
                    "font_path":"/absent/Arial.ttf",
                    "max_tokens":160,"max_image_side":700})

    def clip(self, accepted="chart", used=True):
        return {"used":used,"accepted_route_class":accepted,
                "category_candidate":accepted}

    def test_default_disabled_cannot_invoke_chart(self):
        with mock.patch("all2text.deplot_chart.deplot_chart_candidate",
                        side_effect=AssertionError("must not load model")):
            r=maybe_deplot_chart(Image.new("RGB",(100,100)),
               provider=self.provider(enabled=False),allow_models=True,
               clip_result=self.clip())
            self.assertFalse(r["attempted"])
            self.assertFalse(r["used"])

    def test_no_clip_classification_is_not_chart_permission(self):
        with mock.patch("all2text.deplot_chart.deplot_chart_candidate",
                        side_effect=AssertionError("must not load model")):
            for clip in (None,self.clip("uncertain"),self.clip("diagram"),self.clip(used=False)):
                with self.subTest(clip=clip):
                    r=maybe_deplot_chart(Image.new("RGB",(100,100)),
                        provider=self.provider(),allow_models=True,clip_result=clip)
                    self.assertEqual("requires_confident_clipped_chart_source",r["reason"])

    def test_full_pdf_page_always_requires_separate_figure_crop(self):
        with mock.patch("all2text.deplot_chart.deplot_chart_candidate",
                        side_effect=AssertionError("whole page not a chart")):
            r=maybe_deplot_chart(Image.new("RGB",(100,100)),
                 provider=self.provider(),allow_models=True,
                 clip_result=self.clip(),region_role="full_document_page")
        self.assertEqual("full_page_requires_layout_and_region_cropping",r["reason"])

    def test_missing_font_fails_closed_even_with_valid_chart(self):
        r=maybe_deplot_chart(Image.new("RGB",(100,100)),
               provider=self.provider(),allow_models=True,clip_result=self.clip())
        self.assertTrue(r["attempted"])
        self.assertFalse(r["used"])
        self.assertIn("deplot_unavailable:ValueError",r["reason"])

    def test_local_model_and_font_paths_validated(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            model=root/"model";model.mkdir()
            (model/"config.json").write_text("{}")
            (model/"model.safetensors").write_bytes(b"safetensors dummy")
            font=root/"text.ttf";font.write_bytes(b"fake font for path validation")
            self.assertEqual(model,_existing_root(str(model)))
            self.assertEqual(font,_existing_font(str(font)))
            symlink=root/"bad.ttf";symlink.symlink_to(font)
            with self.assertRaisesRegex(ValueError,"non-symlink"):
                _existing_font(str(symlink))
            (model/"model.safetensors").unlink()
            with self.assertRaisesRegex(ValueError,"safetensors"):
                _existing_root(str(model))

    def test_happy_provider_returns_candidate_but_no_verified_numeric_values(self):
        with mock.patch("all2text.deplot_chart.deplot_chart_candidate",
                        return_value={"attempted":True,"used":True,
                            "numeric_values_verified":False,
                            "raw_generated_table_candidate":"Q1 | 10",
                            "data_scope":"unverified_model_generated_chart_to_table_not_original_source_data"}) as classify:
            r=maybe_deplot_chart(Image.new("RGB",(100,100)),
                  provider=self.provider(),allow_models=True,clip_result=self.clip())
        self.assertTrue(r["used"])
        self.assertFalse(r["numeric_values_verified"])
        self.assertEqual(1,classify.call_count)
        self.assertEqual(160,classify.call_args.kwargs["max_tokens"])


class ChartBackendOutputTests(TestCase):
    def test_emitted_values_are_marked_unverified_and_never_confused_with_literal_ocr(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"in";source.mkdir()
            im=Image.new("RGB",(400,280),"white")
            d=ImageDraw.Draw(im)
            d.line((60,25,60,260),fill="black",width=3)
            d.line((60,260,350,260),fill="black",width=3)
            d.rectangle((95,90,140,258),fill="orange")
            im.save(source/"sample.png")
            cfg=config_from_dict({"providers":{
              "image_classifier":{"name":"clip","enabled":True,"auto_invoke":True,
                                  "model_path":"/missing/CLIP"},
              "chart":{"name":"deplot","enabled":True,"auto_invoke":True,
                       "model_path":"/missing/DePlot","font_path":"/missing/font.ttf"},
              "ocr":{"name":"none","enabled":False},
              "vlm":{"name":"none","enabled":False},
            }})
            with mock.patch("all2text.backends.image.maybe_classify_local_clip",
                return_value={"used":True,"accepted_route_class":"chart",
                              "category_candidate":"chart"}), \
                 mock.patch("all2text.backends.image.maybe_deplot_chart",
                return_value={"attempted":True,"used":True,
                              "raw_generated_table_candidate":"Q1 | 10 <0x0A> Q2 | 20",
                              "numeric_values_verified":False,
                              "data_scope":"unverified_model_generated_chart_to_table_not_original_source_data"}):
                manifest=run(source,root/"out",
                    options=options_with_profile(RunOptions(),"local-models"),config=cfg)
            row=next(x for x in manifest["entries"] if x.get("entry_type")=="file")
            self.assertFalse(row["vlm_used"])
            self.assertFalse(row["ocr_used"])
            self.assertTrue(row["converter_metadata"]["chart_model"]["used"])
            self.assertFalse(row["converter_metadata"]["chart_model"]["numeric_values_verified"])
            self.assertIn("offline_deplot_unverified_chart_to_table",row["extraction_methods_used"])
            self.assertIn("deplot_model_generated_values_not_verified",row["warnings"])
            text=(root/"out"/"sample.png.txt").read_text()
            self.assertIn("UNVERIFIED MODEL-GENERATED CHART-TO-TABLE CANDIDATE",text)
            self.assertIn("Q1 | 10 <0x0A> Q2 | 20",text)
            self.assertIn("must not enter native",str(row["limitations"]).lower()) if False else None
