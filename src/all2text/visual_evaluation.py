"""Read-only routing evaluation against separately authored visual content labels.

The label set is evidence supplied by a benchmark maintainer, never
inferred from filename or the evaluated pipeline. This cannot test
OCR or VLM semantic correctness; only top-level routing quality.
"""
from __future__ import annotations
from typing import Any

ALLOWED = frozenset({"chart", "diagram", "technical_drawing", "map", "document_page",
                     "screenshot", "illustration", "photo", "render", "table", "other"})


def evaluate_routing(manifest: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise ValueError("invalid All2Text manifest")
    if not isinstance(reference, dict):
        raise ValueError("invalid reference labels")
    labels = reference.get("labels")
    if not isinstance(labels, dict) or not 1 <= len(labels) <= 2000:
        raise ValueError("invalid bounded reference labels")
    if any(not isinstance(k, str) or not isinstance(v, str) or v not in ALLOWED
           for k, v in labels.items()):
        raise ValueError("unrecognized reference label")
    rows = [row for row in manifest["entries"] if
            isinstance(row, dict) and row.get("entry_type") == "file"
            and row.get("converter_used") == "image_analysis_backend"]
    observed: dict[str, dict] = {}
    for row in rows:
        path = row.get("relative_path")
        if not isinstance(path, str) or path in observed:
            raise ValueError("missing or duplicated image path")
        observed[path] = row
    if set(observed) != set(labels):
        raise ValueError(f"manifest/label set mismatch: "
                         f"unmatched_manifest={len(set(observed)-set(labels))}, "
                         f"unmatched_reference={len(set(labels)-set(observed))}")
    tp=fp=fn=tn=0
    cases=[]
    for path, row in sorted(observed.items()):
        profile = (row.get("converter_metadata") or {}).get("profile") or {}
        predicted = str(profile.get("taxonomy") or "unknown")
        ref = labels[path]
        is_chart = ref == "chart"
        predicted_chart = predicted == "chart_plot"
        if predicted_chart and is_chart:tp+=1
        elif predicted_chart and not is_chart:fp+=1
        elif is_chart:fn+=1
        else:tn+=1
        cases.append({
            "path":path,"reference_class":ref,"predicted_taxonomy":predicted,
            "taxonomy_source":profile.get("taxonomy_source"),
            "chart_false_positive":predicted_chart and not is_chart,
        })
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    counts={"true_positive":tp,"false_positive":fp,"false_negative":fn,
            "true_negative":tn,"precision":precision,"recall":recall}
    return {
        "evaluation_scope":"Deterministic All2Text image-category routing only; "
                           "not OCR, numeric chart extraction, model accuracy, "
                           "document understanding or real-world truth.",
        "reference_label_source":reference.get("label_source"),
        "model_evaluated":False,
        "sample_count":len(cases),
        "chart_binary":counts,
        "cases":cases,
    }
