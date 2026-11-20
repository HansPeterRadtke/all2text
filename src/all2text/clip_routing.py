"""Optional offline CLIP-only routing: image category evidence, not image understanding.

A learned image family is a *candidate* only. On a 20-image historic technical
set, old CLIP ViT-B32 separated chart versus non-chart better than the original
line/color heuristic. It did not extract labels, numeric values or images.
No model downloads, remote code, GPU use, or model calls unless explicitly
enabled and auto_invoke is true. Defaults remain unchanged.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Any

# Eleven coarse, generally applicable categories. Equal number of prompts
# per category to avoid class-prior inflation; never inject file labels or
# captions as truth into the classifier.
CLASS_PROMPTS: dict[str, tuple[str, str]] = {
    "chart": (
        "a statistical data chart with axes, data series and values",
        "a bar line scatter or pie plot that visualizes numerical measurements",
    ),
    "diagram": (
        "a block diagram or flowchart with boxes, directed arrows or links",
        "a circuit schematic or technical network diagram with connected components",
    ),
    "technical_drawing": (
        "an engineering line drawing showing physical parts and dimensions",
        "a mechanical cross-section architectural blueprint or technical plan",
    ),
    "map": (
        "a geographic map showing land, water or routes with place labels",
        "a historical or modern map of a geographic region",
    ),
    "document_page": (
        "a scanned printed document page with paragraphs and section headings",
        "a page of a scientific paper with text, formulas and layout",
    ),
    "screenshot": (
        "a screenshot of a software application or web user interface",
        "an image of a graphical user interface containing buttons and menus",
    ),
    "illustration": (
        "a stylized educational infographic with decorative visual icons",
        "a conceptual digital illustration combining images and typography",
    ),
    "photo": (
        "a real photograph taken by a camera of an object or a natural scene",
        "a photographic image of a real physical environment",
    ),
    "render": (
        "a computer generated three dimensional render of objects and materials",
        "a synthetic photorealistic CGI scene produced by a rendering engine",
    ),
    "table": (
        "a spreadsheet or data table with rows columns and values",
        "a table screenshot with cell boundaries and column headings",
    ),
    "other": (
        "an abstract image or texture without clear structured content",
        "an ambiguous visual image of a miscellaneous subject",
    ),
}
assert all(len(v) == 2 for v in CLASS_PROMPTS.values())

# Vocabulary accepted by All2Text's deterministic routing. Different
# "render" and "photo" outcomes are only visual impressions, NOT origin proof.
ROUTE_TAXONOMY = {
    "chart": "chart_plot",
    "diagram": "diagram_flowchart_uml_network",
    "technical_drawing": "mechanical_technical_drawing",
    "map": "map_plan_heatmap",
    "document_page": "document_page",
    "screenshot": "screenshot_ui",
    "illustration": "painting_illustration_art",
    "photo": "photo_scene",
    "render": "photo_scene",
    "table": "table_screenshot",
    "other": "unknown",
}
_DEFAULT_MARGIN = 0.02


def _model_dir(path: Any) -> Path:
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 2048:
        raise ValueError("offline CLIP model_path must be an absolute local directory")
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("offline CLIP model_path absent or symlinked")
    config_file = root / "config.json"
    if not config_file.is_file() or config_file.is_symlink():
        raise ValueError("offline CLIP config.json missing or symlinked")
    weights = [
        root / file for file in ("model.safetensors", "pytorch_model.bin")
        if (root / file).is_file() and not (root / file).is_symlink()
    ]
    if not weights:
        raise ValueError("offline CLIP weights missing or symlinked")
    return root


@lru_cache(maxsize=1)
def _load_local_clip(path: str):
    """No network, no remote Python code, CPU-only, one model per process."""
    import torch
    from transformers import CLIPModel, CLIPProcessor

    torch.set_num_threads(2)
    # Hash the exact local weights before loading and again after loading:
    # if this directory changes concurrently, no misleading provenance
    # digest will be published.
    root = _model_dir(path)
    filename = "model.safetensors" if (root / "model.safetensors").is_file() else "pytorch_model.bin"
    weight_file = root / filename
    with weight_file.open("rb") as f:
        weight_hash_before = hashlib.file_digest(f, "sha256").hexdigest()
    model = CLIPModel.from_pretrained(
        path, local_files_only=True, trust_remote_code=False,
        low_cpu_mem_usage=True,
    )
    proc = CLIPProcessor.from_pretrained(
        path, local_files_only=True, trust_remote_code=False,
    )
    model.to("cpu").eval()
    texts = [sentence for pair in CLASS_PROMPTS.values() for sentence in pair]
    inputs = proc(text=texts, return_tensors="pt", padding=True, truncation=True)
    with torch.inference_mode():
        embeddings = model.get_text_features(**inputs)
        embeddings = embeddings / embeddings.norm(dim=1, keepdim=True)
    with weight_file.open("rb") as f:
        weight_hash_after = hashlib.file_digest(f, "sha256").hexdigest()
    if weight_hash_before != weight_hash_after:
        raise ValueError("local CLIP weights changed during model load")
    return model, proc, embeddings, weight_hash_before, filename


def classify_local_clip(image: Any, *, model_path: str,
                        minimum_margin: float = _DEFAULT_MARGIN) -> dict[str, Any]:
    """One image, offline CLIP; explicit abstention on small top-two margins."""
    if type(minimum_margin) is not float or not 0.0 <= minimum_margin <= 0.2:
        raise ValueError("invalid CLIP margin threshold")
    root = _model_dir(model_path)
    model, processor, text_vectors, loaded_weight_sha, weight_filename = _load_local_clip(str(root))
    import torch
    inputs = processor(images=image.convert("RGB"), return_tensors="pt")
    with torch.inference_mode():
        vector = model.get_image_features(pixel_values=inputs["pixel_values"])
        vector = vector / vector.norm(dim=1, keepdim=True)
        similarities = (
            vector @ text_vectors.T
        ).squeeze(0).reshape(len(CLASS_PROMPTS), 2).mean(dim=1)
        scores = [float(x) for x in similarities.tolist()]
    if any(not math.isfinite(x) for x in scores):
        raise ValueError("non-finite CLIP similarity")
    names = list(CLASS_PROMPTS)
    ranked = sorted(range(len(names)), key=lambda i: scores[i], reverse=True)
    first, second = ranked[:2]
    margin = scores[first] - scores[second]
    decision = names[first] if margin >= minimum_margin else "uncertain"
    return {
        "used": True,
        "provider": "clip",
        "model_path": str(root),
        "model_config_sha256": hashlib.sha256((root / "config.json").read_bytes()).hexdigest(),
        "model_weights_filename": weight_filename,
        "model_weights_sha256_at_load": loaded_weight_sha,
        "classifier_prompt_list_sha256": hashlib.sha256(json.dumps(
            CLASS_PROMPTS, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
        "device": "cpu",
        "model_calls": 1,
        "category_candidate": names[first],
        "accepted_route_class": decision,
        "raw_cosine_similarity": round(scores[first], 6),
        "top_two_margin_uncalibrated": round(margin, 6),
        "minimum_margin_policy_not_calibrated": minimum_margin,
        "runner_up": names[second],
        "five_ranked_classes": [
            {"class": names[i], "cosine_similarity": round(scores[i], 6)}
            for i in ranked[:5]
        ],
        "classification_limitations": (
            "CLIP text-image similarity is not a probability. The user-selected "
            "margin is an abstention heuristic, not a validated confidence. "
            "No figure labels or numbers were extracted. Photo versus CGI is "
            "not independently authenticated."
        ),
    }


def maybe_classify_local_clip(image: Any, *, provider: Any,
                              allow_models: bool,
                              region_role: str = "standalone_image") -> dict[str, Any]:
    """Fail safely with explicit provider status; old defaults remain unchanged."""
    result = {
        "used": False,
        "provider": getattr(provider, "name", "none"),
        "reason": "not_auto_invoked",
        "accepted_route_class": None,
        "category_candidate": None,
    }
    if (not allow_models or not getattr(provider, "enabled", False)
            or provider.name != "clip" or not provider.get("auto_invoke", False)):
        return result
    if region_role == "full_document_page":
        result["reason"] = "full_document_page_requires_layout_first"
        return result
    if image is None:
        result["reason"] = "no_decoded_image_available"
        return result
    try:
        margin = provider.get("minimum_margin", _DEFAULT_MARGIN)
        if isinstance(margin, (int, float)) and not isinstance(margin, bool):
            margin = float(margin)
        result = classify_local_clip(
            image, model_path=provider.get("model_path", ""),
            minimum_margin=margin,
        )
    except (ValueError, OSError, RuntimeError, ImportError, AssertionError) as exc:
        result["reason"] = f"clip_unavailable:{type(exc).__name__}:{str(exc)[:170]}"
    return result
