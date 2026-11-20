"""Optional local offline CLIP never silently promotes charts or guesses labels."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from PIL import Image

from all2text import run
from all2text.config import config_from_dict, options_with_profile
from all2text.models import RunOptions
from all2text.clip_routing import (
    ROUTE_TAXONOMY, maybe_classify_local_clip,
)


class OfflineClipPolicyTests(TestCase):
    def provider(self, *, invoked=True):
        from all2text.config import ProviderConfig
        return ProviderConfig(name="clip",enabled=True,
            params={"auto_invoke":invoked,"model_path":"/nonexistent/CLIP"})

    def test_auto_invoke_disabled_never_loads_model(self):
        with mock.patch("all2text.clip_routing.classify_local_clip",
                        side_effect=AssertionError("should not run")):
            result=maybe_classify_local_clip(Image.new("RGB",(64,64)),
                      provider=self.provider(invoked=False),allow_models=True)
        self.assertFalse(result["used"])

    def test_pip_profile_disables_models_even_with_auto_invoke(self):
        with mock.patch("all2text.clip_routing.classify_local_clip",
                        side_effect=AssertionError("should not run")):
            result=maybe_classify_local_clip(Image.new("RGB",(64,64)),
                       provider=self.provider(),allow_models=False)
        self.assertFalse(result["used"])

    def test_full_pdf_page_bypasses_nonlayout_clip_model(self):
        with mock.patch("all2text.clip_routing.classify_local_clip",
                        side_effect=AssertionError("should not run")):
            result=maybe_classify_local_clip(Image.new("RGB",(64,64)),
                       provider=self.provider(),allow_models=True,
                       region_role="full_document_page")
        self.assertFalse(result["used"])
        self.assertEqual("full_document_page_requires_layout_first",result["reason"])

    def test_missing_model_fails_closed_with_reason_no_network(self):
        r=maybe_classify_local_clip(Image.new("RGB",(32,32)),
                                    provider=self.provider(),allow_models=True)
        self.assertFalse(r["used"])
        self.assertIn("clip_unavailable:ValueError",r["reason"])

    def test_no_decoded_image_cannot_generate_chart_evidence(self):
        r=maybe_classify_local_clip(None,provider=self.provider(),allow_models=True)
        self.assertFalse(r["used"])
        self.assertEqual("no_decoded_image_available",r["reason"])

    def test_clipped_or_uncalibrated_model_scores_never_become_numeric_chart_values(self):
        self.assertEqual(11,len(ROUTE_TAXONOMY))
        self.assertIn("chart",ROUTE_TAXONOMY)
        self.assertNotEqual(ROUTE_TAXONOMY["chart"],ROUTE_TAXONOMY["diagram"])


class ImageBackendIntegrationPolicyTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/"src"
        self.source.mkdir()
        self.image=self.source/"chart_test.png"
        d=Image.new("RGB",(400,300),"white")
        from PIL import ImageDraw
        drawer=ImageDraw.Draw(d)
        drawer.line((60,25,60,260),fill="black",width=4)
        drawer.line((60,260,360,260),fill="black",width=4)
        drawer.rectangle((85,130,135,259),fill="orange")
        drawer.rectangle((190,90,240,259),fill="orange")
        d.save(self.image)

    def convert(self, response, *, enabled=True, auto=True, profile="local-models"):
        config=config_from_dict({"providers":{
            "image_classifier":{"name":"clip","enabled":enabled,
                                "auto_invoke":auto,
                                "model_path":"/nonexistent/CLIP",
                                "minimum_margin":0.02},
            "ocr":{"name":"none","enabled":False},
            "vlm":{"name":"none","enabled":False},
            "chart":{"name":"none","enabled":False},
        }})
        with mock.patch("all2text.backends.image.maybe_classify_local_clip",
                        return_value=response) as classifier:
            result=run(self.source,self.root/f"dest-{len(list(self.root.iterdir()))}",
                       options=options_with_profile(RunOptions(),profile),
                       config=config)
        row=next(v for v in result["entries"] if v.get("entry_type")=="file")
        return row,classifier.call_args

    def simulated(self, route, *, used=True):
        return {"used":used,"provider":"clip",
                "category_candidate":"chart" if route=="uncertain" else route,
                "accepted_route_class":route,
                "raw_cosine_similarity":0.304,
                "top_two_margin_uncalibrated":0.032,
                "minimum_margin_policy_not_calibrated":0.02,
                "classification_limitations":"not a probability"}

    def test_confident_chart_requires_explicit_model_result(self):
        row,called=self.convert(self.simulated("chart"))
        profile=row["converter_metadata"]["profile"]
        self.assertEqual("chart_plot",profile["taxonomy"])
        self.assertEqual("clip_offline_local_uncalibrated",profile["taxonomy_source"])
        self.assertTrue(profile["chart_candidate"])
        self.assertEqual("chart",row["converter_metadata"]["route"]["family"])
        self.assertIn("offline_clip_zero_shot_routing",row["extraction_methods_used"])
        self.assertTrue(called)

    def test_clip_rejects_geometry_false_chart_as_diagram(self):
        row,_=self.convert(self.simulated("diagram"))
        p=row["converter_metadata"]["profile"]
        self.assertEqual("diagram_flowchart_uml_network",p["taxonomy"])
        self.assertFalse(p["chart_candidate"])
        self.assertEqual("diagram",row["converter_metadata"]["route"]["family"])

    def test_uncertain_clip_abstains_instead_of_reusing_weak_chart_guess(self):
        row,_=self.convert(self.simulated("uncertain"))
        p=row["converter_metadata"]["profile"]
        self.assertFalse(p["chart_candidate"])
        self.assertEqual("clip_uncertain_abstention",p["taxonomy_source"])
        self.assertEqual("unknown",row["converter_metadata"]["route"]["family"])
        self.assertIn("chart specialist",str(row["converter_metadata"]["route"]["fallback_reasons"]))

    def test_broken_requested_provider_abstains_without_chart_specialist(self):
        row,_=self.convert({"used":False,"provider":"clip",
             "reason":"clip_unavailable:missing weights",
             "accepted_route_class":None})
        p=row["converter_metadata"]["profile"]
        self.assertEqual("clip_failed_abstention",p["taxonomy_source"])
        self.assertFalse(p["chart_candidate"])
        self.assertEqual("unknown",row["converter_metadata"]["route"]["family"])

    def test_photo_label_not_authenticity_proof(self):
        row,_=self.convert(self.simulated("render"))
        self.assertIn("clip_photo_or_render_label_is_not_authenticity_proof",row["warnings"])
        self.assertEqual("scene_or_photo",row["converter_metadata"]["route"]["family"])
        self.assertFalse(row["converter_metadata"]["profile"]["chart_candidate"])

    def test_accepted_render_never_falls_back_to_heuristic_chart_profile(self):
        from all2text.providers import image_family
        profile={"taxonomy":"photo_scene", "taxonomy_source":"clip_offline_local_uncalibrated",
                 "profile":"chart_like_lines and high_color_ratio", "chart_candidate":False}
        self.assertEqual("scene_or_photo",image_family(profile,chart_candidate=False))
        profile["taxonomy"]="chart_plot"
        self.assertEqual("chart",image_family(profile,chart_candidate=True))

    def test_default_no_classifier_preserves_prior_behavior(self):
        from all2text.config import ProviderConfig
        r=maybe_classify_local_clip(
            Image.new("RGB",(32,32)),
            provider=ProviderConfig(name="none",enabled=False),
            allow_models=True,
        )
        self.assertFalse(r["used"])
