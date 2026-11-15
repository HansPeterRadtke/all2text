"""Routing evaluation must use reviewed labels rather than filenames or predictions."""
from unittest import TestCase
from all2text.visual_evaluation import evaluate_routing


class RoutingEvaluationTests(TestCase):
    def row(self, path, category):
        return {
            "entry_type":"file","relative_path":path,
            "converter_used":"image_analysis_backend",
            "converter_metadata":{"profile":{"taxonomy":category,
                                     "taxonomy_source":"deterministic_content_features"}},
        }

    def test_false_chart_routes_identified_despite_misleading_filenames(self):
        manifest={"entries":[
            self.row("chart_named_photo.jpg","chart_plot"),
            self.row("diagram.png","chart_plot"),
            self.row("unknown.png","diagram_flowchart_uml_network"),
        ]}
        labels={"label_source":"independent image reviews",
                "labels":{"chart_named_photo.jpg":"photo",
                          "diagram.png":"diagram","unknown.png":"chart"}}
        x=evaluate_routing(manifest,labels)
        self.assertEqual({"true_positive":0,"false_positive":2,"false_negative":1,
                          "true_negative":0,"precision":0.0,"recall":0.0},
                         x["chart_binary"])
        self.assertEqual(3,x["sample_count"])
        self.assertFalse(x["model_evaluated"])

    def test_only_whole_exact_population_can_be_scored(self):
        manifest={"entries":[self.row("chart.png","chart_plot")]}
        with self.assertRaisesRegex(ValueError,"mismatch"):
            evaluate_routing(manifest,{"labels":{"different.png":"chart"}})
        with self.assertRaisesRegex(ValueError,"unrecognized"):
            evaluate_routing(manifest,{"labels":{"chart.png":"nonsense"}})
        with self.assertRaisesRegex(ValueError,"invalid bounded"):
            evaluate_routing(manifest,{"labels":{}})
        with self.assertRaisesRegex(ValueError,"duplicated"):
            evaluate_routing({"entries":manifest["entries"]*2},{"labels":{"chart.png":"chart"}})

    def test_correct_classifications_count_true_positives_negatives(self):
        manifest={"entries":[self.row("chart.png","chart_plot"),
                            self.row("page.png","document_page"),
                            self.row("photo.png","photo_scene")]}
        x=evaluate_routing(manifest,{"labels":{"chart.png":"chart",
                                           "page.png":"document_page","photo.png":"photo"}})
        self.assertEqual(1.0,x["chart_binary"]["precision"])
        self.assertEqual(1.0,x["chart_binary"]["recall"])
        self.assertEqual(2,x["chart_binary"]["true_negative"])
