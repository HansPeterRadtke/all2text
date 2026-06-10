from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any

from all2text.capabilities import resolve_external_tool
from all2text.backends.text import decode_text_bytes
from all2text.config import ProviderConfig, config_for_context, effective_provider
from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.providers import (
    call_openai_compatible_vision,
    image_to_png_bytes,
    plan_image_route,
    provider_statuses,
)
from all2text.utils import read_header


class ImageAnalysisBackend:
    name = "image_analysis_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "image"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        cfg = config_for_context(ctx.config)
        image_metadata = image_metadata_light(path, classification, ctx)
        profile, profile_warnings, pil_image = image_profile(
            path,
            classification,
            image_metadata,
            allow_optional_python=ctx.options.allow_optional_python and ctx.options.auto_detect_python,
            profile_name=ctx.options.profile,
            optional_python_disabled_reason=(
                f"disabled_by_profile:{ctx.options.profile}"
                if not ctx.options.allow_optional_python
                else "disabled_by_run.auto_detect_python=false"
            ),
        )
        statuses = provider_statuses(cfg, family="image")

        warnings = list(profile_warnings)
        methods = ["image_magic_metadata", "deterministic_image_profile", "provider_status_routing"]
        ocr_provider = provider_with_tool_path(
            effective_provider(cfg, "ocr"),
            "tesseract_cmd",
            resolve_external_tool(cfg, "tesseract").get("source"),
        )
        ocr_result = run_ocr_if_configured(pil_image, ocr_provider)
        warnings.extend(ocr_result["warnings"])
        ocr_used = bool(ocr_result["used"])
        if ocr_result["attempted"]:
            methods.append("configured_ocr_provider")

        chart_candidate = bool(profile.get("chart_candidate"))
        route = plan_image_route(
            profile,
            statuses,
            ocr_attempted=bool(ocr_result["attempted"]),
            chart_candidate=chart_candidate,
        )
        vlm_text, vlm_warnings, vlm_meta = maybe_call_vlm(
            path,
            pil_image,
            effective_provider(cfg, "vlm"),
            rel_path,
            profile,
        )
        warnings.extend(vlm_warnings)
        vlm_used = bool(vlm_text)
        if vlm_meta:
            methods.append("configured_vlm_provider_status")
        if vlm_used:
            methods.append("openai_compatible_vlm_caption")

        chart_analysis = build_chart_analysis_schema(
            profile,
            statuses,
            candidate=chart_candidate,
            ocr_result=ocr_result,
        )
        document_hooks = {
            "document_intelligence": next((status.to_dict() for status in statuses if status.name == "document_intelligence"), None),
            "screenshot_or_document_candidate": route.family in {"document", "screenshot"},
        }

        rendered = render_image_analysis(
            classification=classification,
            image_metadata=image_metadata,
            profile=profile,
            provider_statuses=[status.to_dict() for status in statuses],
            route=route.to_dict(),
            ocr_result=ocr_result,
            vlm_text=vlm_text,
            vlm_meta=vlm_meta,
            chart_analysis=chart_analysis,
            document_hooks=document_hooks,
        )
        limitations = [
            "Image extraction is evidence/report oriented unless configured OCR, VLM, chart, or document providers return content."
        ]
        if chart_candidate:
            limitations.append("Chart candidate detected from image/profile evidence, but no specialist chart values are fabricated.")
        if classification.concrete_format.upper() == "SVG" and bool(metadata.get("looks_text")):
            raw = path.read_bytes()
            svg_text, decode_meta, decode_warnings = decode_text_bytes(raw)
            warnings.extend(decode_warnings)
            rendered += "\nSVG textual markup preserved below:\n" + svg_text
            methods.append("svg_text_preservation")
            extra_metadata = {"svg_decode": decode_meta}
        else:
            extra_metadata = {}
        return ConversionResult(
            text=rendered if rendered.endswith("\n") else rendered + "\n",
            converter_used=self.name,
            extraction_methods_used=methods,
            warnings=warnings,
            metadata={
                "image": image_metadata,
                "profile": profile,
                "provider_statuses": [status.to_dict() for status in statuses],
                "route": route.to_dict(),
                "ocr": ocr_result,
                "vlm": {"text": vlm_text, **vlm_meta},
                "chart_analysis": chart_analysis,
                "document_hooks": document_hooks,
                **extra_metadata,
            },
            limitations=limitations,
            ocr_used=ocr_used,
            vlm_used=vlm_used,
        )


ImagePlaceholderBackend = ImageAnalysisBackend


def provider_with_tool_path(provider: ProviderConfig, key: str, source: object | None) -> ProviderConfig:
    if not source:
        return provider
    params = dict(provider.params)
    params[key] = str(source)
    return ProviderConfig(name=provider.name, enabled=provider.enabled, params=params)


def image_metadata_light(path: Path, classification: Classification, ctx: ConversionContext) -> dict[str, Any]:
    header = read_header(path, max(ctx.options.max_header_bytes, 128))
    fmt = classification.concrete_format.upper()
    try:
        if fmt == "PNG" and len(header) >= 24:
            width, height = struct.unpack(">II", header[16:24])
            return {"format": "PNG", "width": width, "height": height}
        if fmt == "GIF" and len(header) >= 10:
            width, height = struct.unpack("<HH", header[6:10])
            return {"format": "GIF", "width": width, "height": height}
        if fmt == "BMP" and len(header) >= 26:
            width, height = struct.unpack("<II", header[18:26])
            return {"format": "BMP", "width": width, "height": height}
        if fmt == "JPEG":
            dims = jpeg_dimensions(path)
            return {"format": "JPEG", **dims} if dims else {"format": "JPEG"}
        if fmt == "SVG":
            text = header.decode("utf-8", errors="replace")
            return svg_dimensions(text)
    except Exception as exc:
        return {"metadata_error": str(exc)}
    return {}


def image_profile(
    path: Path,
    classification: Classification,
    image_metadata: dict[str, Any],
    *,
    allow_optional_python: bool = True,
    profile_name: str = "pip",
    optional_python_disabled_reason: str = "",
) -> tuple[dict[str, Any], list[str], Any | None]:
    warnings: list[str] = []
    fmt = classification.concrete_format.upper()
    pil_image = None
    width = image_metadata.get("width")
    height = image_metadata.get("height")
    mode = None
    dominant: list[str] = []
    non_white_ratio = None
    color_count_estimate = None
    structure: dict[str, Any] = {}
    if not allow_optional_python:
        if fmt not in {"SVG"}:
            reason = optional_python_disabled_reason or f"disabled_by_profile:{profile_name}"
            warnings.append(f"pil_image_profile_disabled:{reason}")
    else:
        try:
            from PIL import Image

            with Image.open(path) as opened:
                pil_image = opened.convert("RGB")
                width, height = pil_image.size
                mode = opened.mode
                dominant, non_white_ratio, color_count_estimate = sampled_color_profile(pil_image)
                structure = image_structure_profile(pil_image)
        except Exception as exc:
            if fmt not in {"SVG"}:
                warnings.append(f"pil_image_profile_unavailable:{exc}")

    aspect = round(float(width) / float(height), 3) if width and height else None
    profile = classify_profile(
        fmt=fmt,
        width=int(width) if width else None,
        height=int(height) if height else None,
        aspect=aspect,
        non_white_ratio=non_white_ratio,
        color_count_estimate=color_count_estimate,
        structure=structure,
        path=path,
    )
    chart_candidate = bool(profile.get("chart_candidate"))
    profile_dict = {
        "profile": profile.get("profile"),
        "taxonomy": profile.get("taxonomy"),
        "taxonomy_source": profile.get("taxonomy_source"),
        "taxonomy_evidence": profile.get("taxonomy_evidence"),
        "source_hint_taxonomy": profile.get("source_hint_taxonomy"),
        "format": fmt,
        "dimensions": {"width": width, "height": height},
        "aspect_ratio": aspect,
        "mode": mode,
        "dominant_color_names": dominant,
        "non_white_ratio": round(non_white_ratio, 4) if isinstance(non_white_ratio, float) else None,
        "color_count_estimate": color_count_estimate,
        "structure": structure,
        "chart_candidate": chart_candidate,
        "profile_source": "deterministic_header_pil_sampling" if pil_image is not None else "deterministic_header_only",
    }
    profile_dict["rough_content"] = image_rough_content(profile_dict)
    return (
        profile_dict,
        warnings,
        pil_image,
    )


def image_rough_content(profile: dict[str, Any]) -> dict[str, Any]:
    taxonomy = str(profile.get("taxonomy") or "unknown")
    taxonomy_source = str(profile.get("taxonomy_source") or "unknown")
    evidence = list(profile.get("taxonomy_evidence") or [])
    source_hint = profile.get("source_hint_taxonomy")
    mapping = {
        "photo_scene": ("image_photo_or_scene", "low"),
        "screenshot_ui": ("image_screenshot_or_ui", "medium"),
        "document_page": ("image_document_or_scan", "medium"),
        "table_screenshot": ("image_table_or_spreadsheet", "medium"),
        "chart_plot": ("image_chart_or_plot", "medium"),
        "diagram_flowchart_uml_network": ("image_diagram_or_line_drawing", "medium"),
        "circuit_schematic": ("image_circuit_or_schematic", "medium"),
        "mechanical_technical_drawing": ("image_mechanical_or_technical_drawing", "medium"),
        "architectural_floor_plan": ("image_floorplan_or_architectural_drawing", "medium"),
        "map_plan_heatmap": ("image_map_plan_or_heatmap", "medium"),
        "scientific_medical_image": ("image_scientific_or_medical", "low"),
        "painting_illustration_art": ("image_illustration_or_art", "low"),
        "abstract_texture": ("image_abstract_or_texture", "low"),
        "logo_icon": ("image_logo_or_icon", "medium"),
        "unknown": ("image_unknown_visual_content", "low"),
    }
    label, confidence = mapping.get(taxonomy, ("image_unknown_visual_content", "low"))
    if taxonomy_source == "default_low_confidence" and taxonomy == "photo_scene":
        confidence = "low"
        evidence = [*evidence, "default_photo_scene_when_no_specific_evidence"]
    if source_hint and taxonomy_source == "weak_source_filename_hint":
        evidence = [*evidence, f"filename_hint:{source_hint}"]
    return {
        "kind": label,
        "taxonomy": taxonomy,
        "confidence": confidence,
        "source": taxonomy_source,
        "evidence": evidence,
        "limits": "Coarse deterministic image-content label only; detailed scene/object understanding requires OCR/VLM/chart providers.",
    }


def sampled_color_profile(image: Any) -> tuple[list[str], float, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    step = max(1, int((width * height / 5000) ** 0.5))
    counts: dict[str, int] = {}
    non_white = 0
    total = 0
    unique_sample: set[tuple[int, int, int]] = set()
    for y in range(0, height, step):
        for x in range(0, width, step):
            pixel = tuple(int(v) for v in rgb.getpixel((x, y))[:3])
            total += 1
            unique_sample.add(pixel)
            if any(channel < 245 for channel in pixel):
                non_white += 1
                name = color_name(pixel)
                counts[name] = counts.get(name, 0) + 1
    dominant = [name for name, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]]
    return dominant, (non_white / total if total else 0.0), len(unique_sample)


def image_structure_profile(image: Any) -> dict[str, Any]:
    try:
        import numpy as np
    except Exception as exc:
        return {"available": False, "error": f"numpy_unavailable:{exc}"}
    rgb = image.convert("RGB")
    rgb.thumbnail((512, 512))
    arr = np.asarray(rgb)
    if arr.size == 0:
        return {"available": False, "error": "empty_image_array"}
    gray = arr.mean(axis=2)
    non_white = np.any(arr < 245, axis=2)
    dark = gray < 80
    row_ink = non_white.mean(axis=1)
    col_ink = non_white.mean(axis=0)
    row_dark = dark.mean(axis=1)
    col_dark = dark.mean(axis=0)
    horizontal_lines = int(((row_ink > 0.55) | (row_dark > 0.35)).sum())
    vertical_lines = int(((col_ink > 0.55) | (col_dark > 0.35)).sum())
    estimated_text_rows = int(((row_dark > 0.03) & (row_dark < 0.45)).sum())
    colored = non_white & ~dark
    return {
        "available": True,
        "sampled_width": int(arr.shape[1]),
        "sampled_height": int(arr.shape[0]),
        "horizontal_line_rows": horizontal_lines,
        "vertical_line_columns": vertical_lines,
        "grid_like": horizontal_lines >= 3 and vertical_lines >= 3,
        "sparse_linework": bool((horizontal_lines + vertical_lines) >= 4 and float(non_white.mean()) < 0.35),
        "estimated_text_line_rows": estimated_text_rows,
        "colored_non_white_ratio": round(float(colored.mean()), 4),
    }


def classify_profile(
    *,
    fmt: str,
    width: int | None,
    height: int | None,
    aspect: float | None,
    non_white_ratio: float | None,
    color_count_estimate: int | None,
    structure: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    if fmt == "SVG":
        return _profile_result(
            "vector_document_or_diagram",
            "diagram_flowchart_uml_network",
            "content_signature",
            ["svg_vector_markup"],
            source_hint_taxonomy(path),
            chart_candidate=False,
        )
    hint = source_hint_taxonomy(path)
    taxonomy, evidence = content_taxonomy_for(
        width=width,
        height=height,
        aspect=aspect,
        non_white_ratio=non_white_ratio,
        color_count_estimate=color_count_estimate,
        structure=structure,
    )
    if hint == "screenshot_ui" and taxonomy in {"diagram_flowchart_uml_network", "unknown"}:
        return _profile_result(
            "screenshot_ui",
            "screenshot_ui",
            "filename_hint_over_weak_linework",
            [*evidence, "filename_hint:screenshot_ui"],
            hint,
            chart_candidate=False,
        )
    if taxonomy != "unknown":
        return _profile_result(
            taxonomy,
            taxonomy,
            "deterministic_content_features",
            evidence,
            hint,
            chart_candidate=taxonomy == "chart_plot",
        )
    if hint:
        return _profile_result(
            hint,
            hint,
            "weak_source_filename_hint",
            [f"weak_filename_hint:{hint}"],
            hint,
            chart_candidate=False,
        )
    return _profile_result(
        "general_image_metadata_profile",
        "photo_scene",
        "default_low_confidence",
        ["no_specific_deterministic_route_evidence"],
        hint,
        chart_candidate=False,
    )


def _profile_result(
    profile: str,
    taxonomy: str,
    taxonomy_source: str,
    evidence: list[str],
    source_hint: str | None,
    *,
    chart_candidate: bool,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "taxonomy": taxonomy,
        "taxonomy_source": taxonomy_source,
        "taxonomy_evidence": evidence,
        "source_hint_taxonomy": source_hint,
        "chart_candidate": chart_candidate,
    }


def content_taxonomy_for(
    *,
    width: int | None,
    height: int | None,
    aspect: float | None,
    non_white_ratio: float | None,
    color_count_estimate: int | None,
    structure: dict[str, Any],
) -> tuple[str, list[str]]:
    if structure.get("available"):
        h_lines = int(structure.get("horizontal_line_rows") or 0)
        v_lines = int(structure.get("vertical_line_columns") or 0)
        colored_ratio = float(structure.get("colored_non_white_ratio") or 0.0)
        if h_lines >= 1 and v_lines >= 1 and colored_ratio > 0.01:
            return "chart_plot", [
                f"horizontal_line_rows:{h_lines}",
                f"vertical_line_columns:{v_lines}",
                f"colored_non_white_ratio:{colored_ratio}",
            ]
        if structure.get("grid_like"):
            return "table_screenshot", [
                f"horizontal_line_rows:{h_lines}",
                f"vertical_line_columns:{v_lines}",
                "grid_like_structure",
            ]
        if structure.get("sparse_linework") and (h_lines + v_lines) >= 6:
            return "diagram_flowchart_uml_network", [
                f"horizontal_line_rows:{h_lines}",
                f"vertical_line_columns:{v_lines}",
                "sparse_linework",
            ]
        if int(structure.get("estimated_text_line_rows") or 0) >= 20 and (non_white_ratio or 0) < 0.45:
            return "document_page", [
                f"estimated_text_line_rows:{structure.get('estimated_text_line_rows')}",
                f"non_white_ratio:{non_white_ratio}",
            ]
    if width and height and width >= 1200 and height >= 700 and color_count_estimate and color_count_estimate < 512:
        return "screenshot_ui", [f"dimensions:{width}x{height}", f"color_count_estimate:{color_count_estimate}"]
    if width and height and width >= 1000 and height >= 600 and (non_white_ratio or 0) < 0.25:
        return "screenshot_ui", [f"dimensions:{width}x{height}", f"non_white_ratio:{non_white_ratio}"]
    if aspect and (aspect >= 2.2 or aspect <= 0.45) and color_count_estimate and color_count_estimate < 128:
        return "diagram_flowchart_uml_network", [f"aspect_ratio:{aspect}", f"color_count_estimate:{color_count_estimate}"]
    if non_white_ratio is not None and non_white_ratio < 0.015:
        return "abstract_texture", [f"mostly_blank_non_white_ratio:{non_white_ratio}"]
    return "unknown", []


def source_hint_taxonomy(path: Path) -> str | None:
    name = path.stem.casefold()
    rules = [
        ("table_screenshot", ("table", "spreadsheet")),
        ("chart_plot", ("chart", "plot", "graph", "scatter", "heatmap", "candlestick")),
        ("circuit_schematic", ("circuit", "schematic", "electrical")),
        ("architectural_floor_plan", ("floorplan", "floor_plan", "floor-plan", "architectural")),
        ("mechanical_technical_drawing", ("mechanical", "technical_drawing", "blueprint", "drawing")),
        ("map_plan_heatmap", ("map", "plan", "route", "geospatial")),
        ("diagram_flowchart_uml_network", ("diagram", "flowchart", "uml", "network")),
        ("document_page", ("document", "scan", "page", "invoice", "receipt")),
        ("screenshot_ui", ("screenshot", "screen", "ui", "webpage", "slide")),
        ("scientific_medical_image", ("scientific", "medical", "microscopy", "xray", "mri")),
        ("painting_illustration_art", ("painting", "illustration", "art")),
        ("logo_icon", ("logo", "icon")),
        ("photo_scene", ("photo", "scene", "portrait")),
    ]
    for taxonomy, tokens in rules:
        if any(token in name for token in tokens):
            return taxonomy
    return None


IMAGE_TAXONOMY_LABELS = [
    "photo_scene",
    "screenshot_ui",
    "document_page",
    "table_screenshot",
    "chart_plot",
    "diagram_flowchart_uml_network",
    "circuit_schematic",
    "mechanical_technical_drawing",
    "architectural_floor_plan",
    "map_plan_heatmap",
    "scientific_medical_image",
    "painting_illustration_art",
    "abstract_texture",
    "logo_icon",
    "unknown",
]


def run_ocr_if_configured(image: Any | None, provider: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": False,
        "used": False,
        "text": "",
        "candidate_text": "",
        "raw_text_preview": "",
        "warnings": [],
        "provider": getattr(provider, "name", "none"),
        "language": str(provider.get("language", "eng") if provider is not None else "eng"),
        "config": str(provider.get("config", provider.get("tesseract_config", "")) if provider is not None else ""),
        "confidence": None,
        "word_count": 0,
        "accepted_word_count": 0,
        "min_confidence": provider.get("min_confidence", 35) if provider is not None else 35,
        "min_characters": provider.get("min_characters", 4) if provider is not None else 4,
        "min_alnum_ratio": provider.get("min_alnum_ratio", 0.35) if provider is not None else 0.35,
        "discard_reason": "ocr_disabled_or_not_auto_invoked",
    }
    if not getattr(provider, "enabled", False) or provider.name != "tesseract" or not bool(provider.get("auto_invoke", False)):
        return result
    result["attempted"] = True
    if image is None:
        result["warnings"].append("ocr_skipped_no_decodable_image")
        result["discard_reason"] = "no_decodable_image"
        return result
    try:
        import pytesseract

        if provider.get("tesseract_cmd"):
            pytesseract.pytesseract.tesseract_cmd = str(provider.get("tesseract_cmd"))
        ocr_image = preprocess_ocr_image(image, str(provider.get("preprocess", "none") or "none"))
        language = str(provider.get("language", "eng") or "eng")
        config = str(provider.get("config", provider.get("tesseract_config", "")) or "")
        timeout = int(provider.get("timeout_seconds", 30))
        min_confidence = float(provider.get("min_confidence", 35) or 0)
        try:
            data = pytesseract.image_to_data(
                ocr_image,
                lang=language,
                config=config,
                timeout=timeout,
                output_type=pytesseract.Output.DICT,
            )
            parsed = parse_tesseract_data(data, min_confidence=min_confidence)
            text = parsed["text"]
            raw_text = parsed["raw_text"]
            result["confidence"] = parsed["mean_confidence"]
            result["word_count"] = parsed["word_count"]
            result["accepted_word_count"] = parsed["accepted_word_count"]
        except Exception as exc:
            result["warnings"].append(f"ocr_confidence_data_unavailable:{exc}")
            text = pytesseract.image_to_string(
                ocr_image,
                lang=language,
                config=config,
                timeout=timeout,
            )
            raw_text = text
    except Exception as exc:
        result["warnings"].append(f"ocr_failed:{exc}")
        result["discard_reason"] = "provider_failed"
        return result
    cleaned = text.strip()
    raw_cleaned = raw_text.strip()
    result["candidate_text"] = cleaned
    result["raw_text_preview"] = raw_cleaned[:1000]
    min_characters = int(provider.get("min_characters", 4) or 1)
    min_alnum_ratio = float(provider.get("min_alnum_ratio", 0.35) or 0)
    if not cleaned:
        result["discard_reason"] = "empty_or_below_confidence_ocr_result" if raw_cleaned else "empty_ocr_result"
        return result
    if len(cleaned) < min_characters:
        result["discard_reason"] = f"below_min_characters:{len(cleaned)}<{min_characters}"
        return result
    alnum_ratio = ocr_alnum_ratio(cleaned)
    result["alnum_ratio"] = round(alnum_ratio, 4)
    if alnum_ratio < min_alnum_ratio:
        result["discard_reason"] = f"below_min_alnum_ratio:{alnum_ratio:.3f}<{min_alnum_ratio:.3f}"
        return result
    result["text"] = cleaned
    result["used"] = True
    result["discard_reason"] = None
    return result


def preprocess_ocr_image(image: Any, mode: str) -> Any:
    normalized = mode.strip().casefold()
    if normalized in {"", "none"}:
        return image
    if normalized == "grayscale":
        return image.convert("L")
    if normalized in {"threshold", "binary"}:
        gray = image.convert("L")
        return gray.point(lambda value: 255 if value >= 180 else 0)
    return image


def parse_tesseract_data(data: dict[str, Any], *, min_confidence: float) -> dict[str, Any]:
    texts = list(data.get("text") or [])
    confidences = list(data.get("conf") or [])
    block_nums = list(data.get("block_num") or [])
    par_nums = list(data.get("par_num") or [])
    line_nums = list(data.get("line_num") or [])
    raw_words: list[str] = []
    accepted_confidences: list[float] = []
    lines: dict[tuple[int, int, int], list[str]] = {}
    line_order: list[tuple[int, int, int]] = []
    for index, text_value in enumerate(texts):
        word = str(text_value or "").strip()
        if not word:
            continue
        raw_words.append(word)
        confidence = parse_ocr_confidence(confidences[index] if index < len(confidences) else None)
        if confidence is not None and confidence < min_confidence:
            continue
        if confidence is not None:
            accepted_confidences.append(confidence)
        key = (
            int(block_nums[index]) if index < len(block_nums) and str(block_nums[index]).isdigit() else 0,
            int(par_nums[index]) if index < len(par_nums) and str(par_nums[index]).isdigit() else 0,
            int(line_nums[index]) if index < len(line_nums) and str(line_nums[index]).isdigit() else index,
        )
        if key not in lines:
            lines[key] = []
            line_order.append(key)
        lines[key].append(word)
    accepted_lines = [" ".join(lines[key]) for key in line_order if lines.get(key)]
    mean_confidence = (
        round(sum(accepted_confidences) / len(accepted_confidences), 2)
        if accepted_confidences
        else None
    )
    return {
        "text": "\n".join(accepted_lines),
        "raw_text": " ".join(raw_words),
        "mean_confidence": mean_confidence,
        "word_count": len(raw_words),
        "accepted_word_count": sum(len(lines[key]) for key in line_order),
    }


def parse_ocr_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return confidence if confidence >= 0 else None


def ocr_alnum_ratio(text: str) -> float:
    visible = [char for char in text if not char.isspace()]
    if not visible:
        return 0.0
    alnum = sum(1 for char in visible if char.isalnum())
    return alnum / len(visible)


def maybe_call_vlm(
    path: Path,
    image: Any | None,
    provider: Any,
    rel_path: Path,
    profile: dict[str, Any],
) -> tuple[str | None, list[str], dict[str, Any]]:
    image_bytes = image_to_png_bytes(image) if image is not None else None
    mime_type = "image/png"
    if image_bytes is None:
        try:
            image_bytes = path.read_bytes()
            mime_type = "image/svg+xml" if path.suffix.casefold() == ".svg" else "application/octet-stream"
        except Exception as exc:
            return None, [f"vlm_image_read_failed:{exc}"], {}
    prompt = (
        "Describe the image using only visible evidence. Report uncertainty. "
        "If it is a chart, do not invent labels or values that are not visible. "
        f"File label: {rel_path.as_posix()}. Deterministic profile: {profile.get('profile')}."
    )
    return call_openai_compatible_vision(image_bytes, provider, prompt=prompt, mime_type=mime_type)


def render_image_analysis(
    *,
    classification: Classification,
    image_metadata: dict[str, Any],
    profile: dict[str, Any],
    provider_statuses: list[dict[str, Any]],
    route: dict[str, Any],
    ocr_result: dict[str, Any],
    vlm_text: str | None,
    vlm_meta: dict[str, Any],
    chart_analysis: dict[str, Any],
    document_hooks: dict[str, Any],
) -> str:
    lines = [
        f"Format: {classification.concrete_format}",
        "Conversion: image metadata, deterministic profile, and configured provider routing.",
        "Limitation: OCR, VLM, chart, and document-image conclusions are only used when configured providers return evidence.",
        "",
        "Image metadata:",
        f"- {image_metadata or {}}",
        "",
        "Image profile:",
        f"- rough_content: {profile.get('rough_content')}",
        f"- profile: {profile.get('profile')}",
        f"- taxonomy: {profile.get('taxonomy')}",
        f"- taxonomy_source: {profile.get('taxonomy_source')}",
        f"- taxonomy_evidence: {profile.get('taxonomy_evidence')}",
        f"- dimensions: {profile.get('dimensions')}",
        f"- aspect_ratio: {profile.get('aspect_ratio')}",
        f"- dominant_color_names: {profile.get('dominant_color_names')}",
        f"- chart_candidate: {profile.get('chart_candidate')}",
        "",
        "Provider route:",
        f"- family: {route.get('family')}",
        f"- primary_route: {route.get('primary_route')}",
        f"- provider_sequence: {route.get('provider_sequence')}",
        f"- fallback_reasons: {route.get('fallback_reasons')}",
        "",
        "Provider statuses:",
    ]
    lines.extend(f"- {status}" for status in provider_statuses)
    lines.extend(
        [
            "",
            "OCR:",
            f"- attempted: {ocr_result.get('attempted')}",
            f"- used: {ocr_result.get('used')}",
            f"- discard_reason: {ocr_result.get('discard_reason')}",
            f"- text: {ocr_result.get('text') or '<none>'}",
            "",
            "VLM:",
            f"- attempted: {bool(vlm_meta)}",
            f"- used: {bool(vlm_text)}",
            f"- text: {vlm_text or '<none>'}",
            "",
            "Chart analysis hooks:",
            f"- {chart_analysis}",
            "",
            "Document/screenshot hooks:",
            f"- {document_hooks}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_chart_analysis_schema(
    profile: dict[str, Any],
    statuses: list[Any],
    *,
    candidate: bool,
    ocr_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structure = profile.get("structure") if isinstance(profile.get("structure"), dict) else {}
    chart_type = "unknown_chart"
    if candidate:
        if int(structure.get("horizontal_line_rows") or 0) >= 1 and int(structure.get("vertical_line_columns") or 0) >= 1:
            chart_type = "axis_based_chart_or_plot"
    status = next((status.to_dict() for status in statuses if status.name == "chart"), None)
    ocr_used = bool((ocr_result or {}).get("used"))
    ocr_text = str((ocr_result or {}).get("text") or "")
    ocr_source = "tesseract_ocr_text" if ocr_used else "unavailable"
    if ocr_used and not candidate:
        ocr_source = "ocr_text_available_but_not_chart_candidate"
    return {
        "schema": "all2text.chart_analysis.v1",
        "candidate": candidate,
        "attempted": False,
        "used": False,
        "status": status,
        "chart_type": {
            "value": chart_type if candidate else None,
            "source": "deterministic_geometry" if candidate else "not_chart_candidate",
            "confidence": "low" if candidate else "none",
        },
        "title": {"value": None, "source": ocr_source},
        "axes": {
            "x": {"label": None, "ticks": [], "source": ocr_source},
            "y": {"label": None, "ticks": [], "source": ocr_source},
        },
        "legend": {"labels": [], "source": ocr_source},
        "series": [],
        "table": {"rows": [], "source": "unavailable"},
        "values": {"recoverable": False, "source": "unavailable", "caveat": "No chart provider returned numeric values."},
        "ocr": {
            "attempted": bool((ocr_result or {}).get("attempted")),
            "used": ocr_used,
            "text": ocr_text,
            "confidence": (ocr_result or {}).get("confidence"),
            "limitation": "OCR text is evidence only; no chart layout/value reconstruction is inferred.",
        },
        "evidence": {
            "taxonomy": profile.get("taxonomy"),
            "taxonomy_source": profile.get("taxonomy_source"),
            "taxonomy_evidence": profile.get("taxonomy_evidence"),
            "structure": structure,
            "dimensions": profile.get("dimensions"),
            "dominant_color_names": profile.get("dominant_color_names"),
        },
        "limitations": [
            "No chart specialist provider produced table/series values.",
            "Geometry/profile evidence is reported without invented chart labels or values.",
            "OCR text is not converted into axes, legend, or values without a layout/chart provider.",
        ],
    }


def color_name(pixel: tuple[int, int, int]) -> str:
    red, green, blue = pixel
    if red > 235 and green > 235 and blue > 235:
        return "white"
    if red < 40 and green < 40 and blue < 40:
        return "black"
    if abs(red - green) < 18 and abs(green - blue) < 18:
        return "gray"
    if red > 180 and green > 120 and blue < 90:
        return "orange"
    if red > 170 and green < 100 and blue < 100:
        return "red"
    if green > 140 and red < 140 and blue < 140:
        return "green"
    if blue > 150 and red < 140:
        return "blue"
    if red > 150 and blue > 130 and green < 130:
        return "purple"
    if red > 150 and green > 150 and blue < 90:
        return "yellow"
    if red > 120 and green > 70 and blue < 70:
        return "brown"
    return "mixed"


def jpeg_dimensions(path: Path) -> dict[str, int] | None:
    try:
        data = path.read_bytes()[:1024 * 1024]
    except Exception:
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 > len(data):
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return {"width": width, "height": height}
        index += length
    return None


def svg_dimensions(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"format": "SVG"}
    for attr in ("width", "height", "viewBox"):
        match = re.search(rf"\b{attr}\s*=\s*['\"]([^'\"]+)['\"]", text[:4096], flags=re.IGNORECASE)
        if match:
            result[attr] = match.group(1)
    return result
