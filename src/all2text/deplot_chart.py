"""Opt-in, offline, CPU-only DePlot chart-to-table candidate.

A chart-shaped image is not enough: only an independently used and accepted
CLIP chart category may request numeric extraction. Every generated number
is unverified model output, never source-authenticated tabular data.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import time
from typing import Any


def _existing_root(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.startswith("/") or len(raw) > 2048:
        raise ValueError("DePlot model path must be a local absolute path")
    root=Path(raw)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("DePlot local model directory missing or symlinked")
    cfg=root/"config.json"
    weights=root/"model.safetensors"
    if not cfg.is_file() or cfg.is_symlink():
        raise ValueError("DePlot config.json missing or symlinked")
    if not weights.is_file() or weights.is_symlink():
        raise ValueError("DePlot requires a local safetensors model weight file")
    return root


def _existing_font(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.startswith("/") or len(raw) > 2048:
        raise ValueError("DePlot requires explicit local absolute font_path")
    path=Path(raw)
    if not path.is_file() or path.is_symlink() or path.suffix.casefold() not in (".ttf",".otf"):
        raise ValueError("DePlot requires a non-symlink local TrueType/OpenType font")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("DePlot font is over 20 MiB")
    return path


@lru_cache(maxsize=1)
def _loaded_model(path: str):
    """Offline-only model cached for one process, with consistent weight hash."""
    import torch
    from transformers import Pix2StructProcessor, Pix2StructForConditionalGeneration
    root=_existing_root(path)
    weights=root/"model.safetensors"
    with weights.open("rb") as stream:
        before=hashlib.file_digest(stream,"sha256").hexdigest()
    torch.set_num_threads(2)
    processor=Pix2StructProcessor.from_pretrained(
        path, local_files_only=True, trust_remote_code=False
    )
    model=Pix2StructForConditionalGeneration.from_pretrained(
        path,local_files_only=True,trust_remote_code=False,low_cpu_mem_usage=True,
    ).to("cpu").eval()
    with weights.open("rb") as stream:
        after=hashlib.file_digest(stream,"sha256").hexdigest()
    if before!=after:
        raise ValueError("DePlot model weights changed during load")
    return processor,model,before


def _resize(image: Any, max_side: int):
    from PIL import Image
    rgb=image.convert("RGB")
    width,height=rgb.size
    longest=max(width,height)
    if longest<=max_side:
        return rgb
    scale=max_side/float(longest)
    return rgb.resize((max(1,round(width*scale)),max(1,round(height*scale))),
                      Image.Resampling.LANCZOS)


def deplot_chart_candidate(image: Any, *, model_path: str, font_path: str,
                           max_tokens: int=160, max_image_side: int=700) -> dict[str,Any]:
    if (type(max_tokens) is not int or not 1<=max_tokens<=256 or
            type(max_image_side) is not int or not 128<=max_image_side<=1024):
        raise ValueError("invalid bounded DePlot generation or image size")
    root=_existing_root(model_path)
    font=_existing_font(font_path)
    start=time.monotonic()
    processor,model,weights_sha=_loaded_model(str(root))
    import torch
    inputs=processor(
        images=_resize(image,max_image_side),
        text="Generate underlying data table of the figure below:",
        return_tensors="pt",
        font_path=str(font), # prevents Pix2Struct Hub Arial.TTF request
    )
    with torch.inference_mode():
        generated=model.generate(
            **inputs,max_new_tokens=max_tokens,
            do_sample=False,num_beams=1,
            pad_token_id=processor.tokenizer.pad_token_id,
            eos_token_id=processor.tokenizer.eos_token_id,
            use_cache=True,
        )
    text=processor.decode(generated[0],skip_special_tokens=True).strip()
    return {
        "attempted":True,
        "used":bool(text),
        "provider":"deplot_local_cpu",
        "model_dir":str(root),
        "model_weights_sha256_at_load":weights_sha,
        "model_config_sha256":hashlib.sha256((root/"config.json").read_bytes()).hexdigest(),
        "font_path":str(font),
        "font_sha256":hashlib.sha256(font.read_bytes()).hexdigest(),
        "device":"cpu",
        "duration_seconds":round(time.monotonic()-start,2),
        "max_new_tokens":max_tokens,
        "max_image_side":max_image_side,
        "raw_generated_table_candidate":text or None,
        "numeric_values_verified":False,
        "data_scope":"unverified_model_generated_chart_to_table_not_original_source_data",
        "limitations":"Model values, axes and labels may be wrong or hallucinated. "
                      "Verify against the original pixels and primary data before KMD indexing.",
    }


def maybe_deplot_chart(image: Any, *, provider: Any, allow_models: bool,
                       clip_result: dict[str,Any] | None,
                       region_role: str="standalone_image") -> dict[str,Any]:
    result={"attempted":False,"used":False,
            "provider":getattr(provider,"name","none"),
            "reason":"not_auto_invoked",
            "numeric_values_verified":False}
    if (not allow_models or not getattr(provider,"enabled",False)
            or provider.name!="deplot"
            or not provider.get("auto_invoke",False)):
        return result
    if region_role=="full_document_page":
        result["reason"]="full_page_requires_layout_and_region_cropping"
        return result
    if (not clip_result or not clip_result.get("used")
            or clip_result.get("accepted_route_class")!="chart"):
        result["reason"]="requires_confident_clipped_chart_source"
        return result
    if image is None:
        result["reason"]="no_decoded_image"
        return result
    try:
        max_tokens=provider.get("max_tokens",160)
        max_side=provider.get("max_image_side",700)
        if isinstance(max_tokens,(int,float)) and not isinstance(max_tokens,bool):
            max_tokens=int(max_tokens)
        if isinstance(max_side,(int,float)) and not isinstance(max_side,bool):
            max_side=int(max_side)
        result=deplot_chart_candidate(
            image,model_path=provider.get("model_path",""),
            font_path=provider.get("font_path",""),
            max_tokens=max_tokens,max_image_side=max_side,
        )
    except (ValueError,RuntimeError,OSError,ImportError,AssertionError) as exc:
        result["attempted"]=True
        result["reason"]=f"deplot_unavailable:{type(exc).__name__}:{str(exc)[:160]}"
    return result
