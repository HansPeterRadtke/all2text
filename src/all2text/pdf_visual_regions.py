"""Source-hash-pinned PDF figure regions, captions and document-page crops.

A deterministic, optional pre-VLM layout stage. It never runs OCR/models,
rewrites originals or asserts the truth of nearby captions. It only handles
embedded raster images with PDFMiner-reported physical bounding boxes.
Vector-only charts/diagrams require a separate figure layout detector.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

MAX_PDF_BYTES = 256 * 1024**2
MAX_CATALOG_BYTES = 32 * 1024**2
MAX_PAGES = 4
MAX_REGIONS_PER_PAGE = 24
MAX_PAGE_IMAGE_EDGE = 1600
MIN_IMAGE_PAGE_FRACTION = 0.0025
MIN_UNCAPTIONED_FRACTION = 0.012
SCANNED_PAGE_FRACTION = 0.80
CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?\.?|table)\s*\d+[.:]?\s+", re.I)


def _source_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 1600:
        raise ValueError("invalid relative original path")
    p = PurePosixPath(value)
    if (p.is_absolute() or "\\" in value or
            any(part in ("", ".", "..") for part in value.split("/")) or
            p.suffix.casefold() != ".pdf"):
        raise ValueError("unsafe original PDF relative path")
    return p.as_posix()


def verify_original(
    source_root: Path, relative_path: str,
    manifest_path: Path, ledger_path: Path,
) -> tuple[Path, dict[str, Any]]:
    """Both approved catalog AND completed download receipt identify source."""
    relative = _safe_relative_path(relative_path)
    root = Path(source_root).resolve()
    original = root / relative
    if original.is_symlink() or not original.is_file() or not original.resolve().is_relative_to(root):
        raise ValueError("canonical approved original missing or unsafe")
    if original.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("original PDF exceeds bounded single-source scan size")
    records=[]
    for file, key in ((manifest_path, "sources"), (ledger_path, "items")):
        p=Path(file)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_CATALOG_BYTES:
            raise ValueError("approved catalog or original receipt absent or unsafe")
        content=json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or not isinstance(content.get(key), list):
            raise ValueError("invalid catalog or receipt schema")
        matching=[x for x in content[key]
                  if isinstance(x, dict) and x.get("path")==relative]
        if len(matching)!=1:
            raise ValueError("original not uniquely identified by approved catalog and receipt")
        records.append(matching[0])
    catalog, receipt = records
    if (catalog.get("kind")!="pdf" or receipt.get("status")!="complete"
            or receipt.get("sha256") is None
            or not re.fullmatch(r"[0-9a-f]{64}",str(receipt["sha256"]))
            or original.stat().st_size != receipt.get("bytes_received")):
        raise ValueError("publisher source kind/completed bytes/sha receipt mismatch")
    actual=_source_sha(original)
    if actual!=receipt["sha256"]:
        raise ValueError("canonical original SHA-256 does not match download receipt")
    return original, {
        "relative_path":relative,
        "source_sha256":actual,
        "source_bytes":original.stat().st_size,
        "approved_catalog_title":str(catalog.get("title") or "")[:200],
        "approved_catalog_url":str(catalog.get("url") or "")[:500],
        "rights_note":str(catalog.get("rights_note") or "")[:350],
        "catalog_kind":"pdf",
        "download_receipt_status":"complete",
        "download_receipt_sha256":receipt["sha256"],
    }


def _rect_ok(rect: tuple[float,float,float,float],
             page_width: float,page_height: float) -> bool:
    if len(rect)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in rect):
        return False
    x0,y0,x1,y1=rect
    return (page_width>0 and page_height>0 and
            0<=x0<x1<=page_width+0.1 and 0<=y0<y1<=page_height+0.1)


def _overlap_fraction(left:tuple[float,float,float,float],
                      right:tuple[float,float,float,float]) -> float:
    intersection=max(0.0,min(left[2],right[2])-max(left[0],right[0]))
    return intersection/max(0.0001,left[2]-left[0])


def _select_caption(
    box: tuple[float,float,float,float],
    captions: list[dict[str,Any]],
) -> int | None:
    """Nearest plausible BELOW-image caption; no semantic attribution claim."""
    matches=[]
    for index, cap in enumerate(captions):
        rect=cap["bbox"]
        below_gap=box[1]-rect[3]
        if -1.0 <= below_gap <= 130.0 and _overlap_fraction(box,rect)>=0.25:
            matches.append((max(0.0,below_gap),index))
    if not matches:
        return None
    return min(matches)[1]


def _candidate_groups(
    page_width:float,page_height:float,
    images:list[dict[str, Any]],captions:list[dict[str, Any]],
    *, min_fraction:float=MIN_IMAGE_PAGE_FRACTION,
    max_regions:int=MAX_REGIONS_PER_PAGE,
) -> tuple[list[dict[str,Any]],dict[str,int]]:
    """Group embedded image panels by nearby caption; admit scanned full page.

    Does NOT create vector diagram/chart figures or claim the caption is
    logically correct for a region. Returns a visible skip accounting.
    """
    if (not 0.0 < min_fraction <= .15 or type(max_regions) is not int
            or not 1 <= max_regions <= MAX_REGIONS_PER_PAGE):
        raise ValueError("invalid bounded figure candidate policy")
    candidates=[]
    rejected={"tiny_embedded_images":0,"invalid_rectangles":0,
              "uncaptioned_decorative_images":0}
    for idx,img in enumerate(images):
        box=tuple(img["bbox"])
        if not _rect_ok(box,page_width,page_height):
            rejected["invalid_rectangles"]+=1
            continue
        area=((box[2]-box[0])*(box[3]-box[1])/(page_width*page_height))
        if area<min_fraction:
            rejected["tiny_embedded_images"]+=1
            continue
        role="full_document_page" if area>=SCANNED_PAGE_FRACTION else "figure_crop"
        caption_index=None if role=="full_document_page" else _select_caption(box,captions)
        if role!="full_document_page" and caption_index is None and area<MIN_UNCAPTIONED_FRACTION:
            rejected["uncaptioned_decorative_images"]+=1
            continue
        candidates.append({"image_index":idx,"pdf_bbox":box,"role":role,
                           "caption_index":caption_index,"page_fraction":area})
    # A short caption often sits under only the left panel of two adjacent
    # same-row images. One *unique* nearby caption may be inherited by an
    # otherwise unmatched panel, but never by dissimilar-height rows, distant
    # images, or conflicting captions. This is layout evidence, not proof of
    # the actual semantic figure-to-caption relationship.
    for candidate in candidates:
        if candidate["role"]!="figure_crop" or candidate["caption_index"] is not None:
            continue
        x0,y0,x1,y1=candidate["pdf_bbox"]
        matches=set()
        for neighbor in candidates:
            caption=neighbor["caption_index"]
            if caption is None or neighbor is candidate or neighbor["role"]!="figure_crop":
                continue
            a0,b0,a1,b1=neighbor["pdf_bbox"]
            similar_heights=(abs(y0-b0)<=5.0 and abs(y1-b1)<=5.0)
            x_gap=min(abs(x0-a1),abs(a0-x1))
            horizontally_adjacent=(x1<=a0+1 or a1<=x0+1) and x_gap<=15.0
            if similar_heights and horizontally_adjacent:
                matches.add(caption)
        if len(matches)==1:
            candidate["caption_index"]=next(iter(matches))
            candidate["caption_inferred_from_aligned_neighbor"]=True
    bundles: dict[tuple[str,int],list[dict]]={}
    for item in candidates:
        key=("caption",item["caption_index"]) if item["caption_index"] is not None else ("image",item["image_index"])
        bundles.setdefault(key,[]).append(item)
    result=[]
    for parts in bundles.values():
        x0=min(p["pdf_bbox"][0] for p in parts)
        y0=min(p["pdf_bbox"][1] for p in parts)
        x1=max(p["pdf_bbox"][2] for p in parts)
        y1=max(p["pdf_bbox"][3] for p in parts)
        role="full_document_page" if any(p["role"]=="full_document_page" for p in parts) else "figure_crop"
        result.append({
            "region_role":role,
            "bbox_pdf_points":[round(v,3) for v in (x0,y0,x1,y1)],
            "caption_index":parts[0]["caption_index"],
            "embedded_image_indices":[p["image_index"] for p in parts],
            "embedded_image_count":len(parts),
            "bbox_fraction_of_page":round((x1-x0)*(y1-y0)/(page_width*page_height),5),
            "caption_association":"nearest_below_or_aligned_neighbor_heuristic_not_semantically_verified",
            "caption_inherited_by_panel_alignment":any(p.get("caption_inferred_from_aligned_neighbor",False) for p in parts),
        })
    result.sort(key=lambda z:(-z["bbox_pdf_points"][3],z["bbox_pdf_points"][0]))
    if len(result)>max_regions:
        raise ValueError("page has more than allowed image candidates; manual/layout-model review required")
    return result,rejected


def _pdf_layout(original:Path, page_number:int):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTImage, LTTextContainer
    layouts=list(extract_pages(str(original),page_numbers=[page_number-1],
                               laparams=LAParams()))
    if len(layouts)!=1:
        raise ValueError("requested physical PDF page not found")
    layout=layouts[0]
    images=[]
    captions=[]
    def walk(item:Any):
        if isinstance(item,LTImage):
            images.append({"name":str(item.name)[:80],"bbox":item.bbox})
            return
        if isinstance(item,LTTextContainer):
            text=item.get_text()
            if CAPTION_RE.match(text):
                captions.append({"text":text,"bbox":item.bbox})
            return
        if hasattr(item,"__iter__"):
            for child in item:
                walk(child)
    walk(layout)
    return layout.width,layout.height,images,captions


def _box_to_pixels(box:list[float],page_w:float,page_h:float,
                   raster_w:int,raster_h:int) -> tuple[int,int,int,int]:
    """Poppler raster top-left origin from PDFMiner PDF bottom-left points."""
    if not _rect_ok(tuple(box),page_w,page_h):
        raise ValueError("PDF figure rectangle outside physical page")
    x0,y0,x1,y1=box
    left=max(0,round(x0*raster_w/page_w)-3)
    right=min(raster_w,round(x1*raster_w/page_w)+3)
    top=max(0,round((page_h-y1)*raster_h/page_h)-3)
    bottom=min(raster_h,round((page_h-y0)*raster_h/page_h)+3)
    if right-left<8 or bottom-top<8:
        raise ValueError("collapsed PDF-to-pixel region")
    return left,top,right,bottom


def _render_bounded_page(original: Path,number:int,
                         dest:Path,max_edge:int) -> None:
    if type(max_edge) is not int or not 500<=max_edge<=MAX_PAGE_IMAGE_EDGE:
        raise ValueError("invalid page raster maximum edge")
    args=["pdftoppm","-f",str(number),"-l",str(number),
          "-singlefile","-scale-to",str(max_edge),"-png",
          str(original),str(dest.with_suffix(""))]
    try:
        result=subprocess.run(args,capture_output=True,timeout=40,check=False)
    except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
        raise ValueError("bounded Poppler page raster unavailable") from exc
    if result.returncode!=0 or not dest.is_file():
        raise ValueError(f"Poppler page raster failed (status {result.returncode})")
    if dest.stat().st_size>16*1024**2:
        raise ValueError("page raster exceeded output byte guard")


def _physical_page_rotation(original:Path,number:int) -> int:
    try:
        res=subprocess.run(["pdfinfo","-f",str(number),"-l",str(number),
                            "-box",str(original)],capture_output=True,
                           text=True,timeout=15)
    except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
        raise ValueError("PDF page rotation metadata unavailable") from exc
    if res.returncode:
        raise ValueError("PDF info unavailable or invalid PDF")
    match=re.search(rf"^Page\s+{number}\s+rot:\s*(\d+)",res.stdout,re.M)
    if not match:
        raise ValueError("physical PDF page rotation information missing")
    rotation=int(match.group(1))
    if rotation!=0:
        raise ValueError("rotated PDF page refused pending coordinate parity test")
    return rotation


def _parse_page_list(pages: list[int]) -> list[int]:
    if (not isinstance(pages,list) or not 1<=len(pages)<=MAX_PAGES
            or len(set(pages))!=len(pages)
            or any(type(p) is not int or p<1 or p>20000 for p in pages)):
        raise ValueError("invalid bounded physical page list")
    return pages


def extract_verified_pdf_regions(
    *, source_root:Path,relative_pdf_path:str,
    approved_manifest:Path, completed_ledger:Path,
    physical_pages:list[int], output_dir:Path,
    max_edge:int=MAX_PAGE_IMAGE_EDGE,
) -> dict[str,Any]:
    """Safely produce private crop PNGs and checked downstream context JSON."""
    from PIL import Image
    physical_pages=_parse_page_list(physical_pages)
    original,info=verify_original(source_root,relative_pdf_path,
                                   approved_manifest,completed_ledger)
    output=Path(output_dir).expanduser().resolve()
    root=Path(source_root).resolve()
    if output.is_relative_to(root):
        raise ValueError("cannot write figure results into original corpus")
    if output.exists():
        raise ValueError("private output folder already exists; refuse overwrite")
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    image_dir=output/"regions"
    page_dir=output/"rendered_pages"
    image_dir.mkdir(mode=0o700)
    page_dir.mkdir(mode=0o700)
    regions=[]
    context={}
    processed=[]
    for number in physical_pages:
        _physical_page_rotation(original,number)
        page_w,page_h,images,captions=_pdf_layout(original,number)
        if not 25<=page_w<=5000 or not 25<=page_h<=5000:
            raise ValueError("unsupported PDF physical page dimensions")
        groups,skipped=_candidate_groups(page_w,page_h,images,captions)
        record={
            "physical_pdf_page":number,
            "page_pdf_size_points":[round(page_w,3),round(page_h,3)],
            "embedded_image_count":len(images),
            "layout_caption_candidates":len(captions),
            "detected_regions":len(groups),
            "skip_counts":skipped,
            "extraction_scope":"embedded raster image regions only; vector charts are not discovered",
        }
        if not groups:
            processed.append(record)
            continue
        png=page_dir/(f"page_{number:04d}.png")
        _render_bounded_page(original,number,png,max_edge)
        with Image.open(png) as im:
            im.load()
            iw,ih=im.size
            if iw*ih>MAX_PAGE_IMAGE_EDGE**2:
                raise ValueError("page render pixel budget exceeded")
            if abs((iw/ih)/(page_w/page_h)-1)>0.025:
                raise ValueError("PDF page/raster size coordinate parity mismatch")
            page_sha=_source_sha(png)
            for ix,group in enumerate(groups,1):
                region_name=f"page_{number:04d}_region_{ix:02d}.png"
                key=f"regions/{region_name}"
                pixels=_box_to_pixels(group["bbox_pdf_points"],page_w,page_h,iw,ih)
                crop=im.crop(pixels)
                region_dest=image_dir/region_name
                crop.save(region_dest,format="PNG")
                raw_sha=_source_sha(region_dest)
                bbox=group["bbox_pdf_points"]
                cap=captions[group["caption_index"]] if group["caption_index"] is not None else None
                # Keep full extracted-text SHA distinct from the bounded
                # portion shown in a vision prompt. Publisher-byte identity
                # is NOT implied by either digest.
                caption_text=cap["text"].strip() if cap else ""
                caption_preview=caption_text[:360]
                item={
                    "source_relative_path":info["relative_path"],
                    "original_pdf_sha256":info["source_sha256"],
                    "physical_pdf_page":number,
                    "physical_page_rotation":0,
                    "pdf_page_size_points":[page_w,page_h],
                    "pdf_image_bbox_bottom_left_points":bbox,
                    "rendered_page_sha256":page_sha,
                    "rendered_page_path":png.relative_to(output).as_posix(),
                    "raster_region_pixel_bbox_top_left":list(pixels),
                    "region_path":key,
                    "region_png_sha256":raw_sha,
                    "region_pixels":list(crop.size),
                    "region_role":group["region_role"],
                    "embedded_image_count":group["embedded_image_count"],
                    "embedded_image_indices":group["embedded_image_indices"],
                    "bbox_fraction_of_page":group["bbox_fraction_of_page"],
                    "caption_extraction":"pdfminer_from_same_original_page" if cap else "none",
                    "caption_association":group["caption_association"] if cap else "none",
                    "caption_inherited_by_panel_alignment":group["caption_inherited_by_panel_alignment"],
                    "caption_full_extracted_text_sha256":hashlib.sha256(caption_text.encode()).hexdigest() if cap else None,
                    "caption_full_extracted_text_characters":len(caption_text),
                    "caption_preview_sha256":hashlib.sha256(caption_preview.encode()).hexdigest() if cap else None,
                    "caption_preview_is_truncated":len(caption_text)>len(caption_preview),
                    "caption_pdf_bbox_points":[round(v,3) for v in cap["bbox"]] if cap else None,
                    "caption_is_literal_publisher_bytes":False,
                    "caption_text_for_prompt":caption_preview,
                    "source_catalog_title":info["approved_catalog_title"],
                    "model_or_ocr_used":False,
                    "figure_category_not_determined":True,
                }
                regions.append(item)
                # The separate `regions/` directory is the All2Text input
                # root; visual-context keys are relative to that root, not to
                # the wider provenance/audit output directory.
                context[region_name]={
                    "image_sha256":raw_sha,
                    "region_role":group["region_role"],
                    "physical_page":number,
                    "document_topic":info["approved_catalog_title"][:160],
                    "figure_caption":caption_preview,
                    "parent_pdf_relative_path":info["relative_path"],
                    "parent_pdf_sha256":info["source_sha256"],
                    "source_metadata_scope":"operator supplied from current catalog and PDFMiner text; caption association heuristic only",
                }
        processed.append(record)
    if _source_sha(original)!=info["source_sha256"]:
        raise ValueError("source original revision changed during visual extraction")
    report={
        "schema":"all2text.verified_pdf_visual_regions.v1",
        "original":info,
        "pages":processed,
        "regions":regions,
        "limitations":[
            "No OCR/VLM was invoked; figure type, chart values, photo/render and text truth unverified",
            "Only embedded raster images are detected; vector figures and compound vector/raster diagrams require a separate layout model",
            "Nearby PDFMiner caption association is a heuristic; caption text is extracted text not original publisher-byte proof",
            "A page-filling image means a scanned document page, not an isolated statistical figure",
            "All figure content remains untrusted source data; the parent SHA and physical page/rectangle/crop SHA are independently reproducible",
        ],
    }
    visual={"schema":"all2text.visual_context.v1","entries":context}
    for name,payload in (("regions.json",report),("visual_context.json",visual)):
        path=output/name
        path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        path.chmod(0o600)
    return report
