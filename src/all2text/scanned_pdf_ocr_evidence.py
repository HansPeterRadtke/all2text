"""Opt-in, source-revision-pinned OCR candidates for bounded image-only PDFs.

This is an evidence PREVIEW, not a completed source extraction. Every OCR
word is untrusted machine-generated text. No existing original, source-map,
native FileDB record, KMD summary or original text search is changed.
"""
from __future__ import annotations

import csv
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
import subprocess
from typing import Any

from all2text.pdf_visual_regions import verify_original, _source_sha, _safe_relative_path

MAX_PAGES_PER_RUN=3
MAX_ORIGINAL_PAGES=100
MAX_DPI=260
MAX_PIXELS=12_000_000
MAX_TESSERACT_TSV_BYTES=6*1024*1024
VALID_PSM=frozenset((3,4,6,11))
VALID_LANG=frozenset(("eng","deu","eng+deu"))
_VISUAL_ERROR="Visual-only original not eligible for bounded OCR"


def _with_timeout(argv:list[str], *, timeout:int, cwd:Path|None=None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv,cwd=cwd,capture_output=True,timeout=timeout,
            env={**os.environ,"OMP_THREAD_LIMIT":"1"},
            check=False,
        )
    except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
        raise ValueError("bounded local document OCR utility missing or timed out") from exc


def _source_map_error(source_map_db:Path, relative:str, expected_sha:str) -> dict:
    db=Path(source_map_db)
    if db.is_symlink() or not db.is_file():
        raise ValueError("source-map file unavailable or symlinked")
    with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True) as sql:
        sql.execute("PRAGMA query_only=ON")
        rows=sql.execute(
            "SELECT status,source_sha256,error FROM originals WHERE source_path=?",
            (relative,),
        ).fetchall()
    if len(rows)!=1:
        raise ValueError("no unique original source-map entry")
    status,source_sha,err=rows[0]
    if source_sha!=expected_sha:
        raise ValueError("source-map original SHA mismatch")
    if status!="error" or _VISUAL_ERROR not in (err or ""):
        raise ValueError("source-map original is not an explicitly unresolved image-only PDF")
    return {"status":status,"source_sha256":source_sha,
            "reason":"visual_only_bounded_original_not_yet_extracted"}


def _canonical_native_file_link(filedb:Path,relative:str)->dict[str,Any]:
    """Read-only, exact native FileDB identity; never create a second index."""
    file=Path(filedb)
    if file.is_symlink() or not file.is_file():
        raise ValueError("canonical native FileDB file unavailable or symlinked")
    with sqlite3.connect(file.resolve().as_uri()+"?mode=ro",uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        identities=db.execute(
            "SELECT id FROM filesystem_entries "
            "WHERE relative_path_display=? AND entry_type='file'",
            (relative,),
        ).fetchall()
        if len(identities)!=1:
            raise ValueError("no unique canonical native FileDB original entry")
        index_id=identities[0][0]
        row=db.execute(
            "SELECT count(*),sum(embedding_blob is not null) "
            "FROM content_chunks WHERE filesystem_entry_id=?",
            (index_id,),
        ).fetchone()
    return {
        "filesystem_entry_id":index_id,
        "existing_native_chunk_count":int(row[0] or 0),
        "existing_embedded_chunk_count":int(row[1] or 0),
        "original_entry_link_verified":True,
        "no_new_native_index_created":True,
    }


def _pdf_physical_pages(original:Path)->int:
    ret=_with_timeout(["pdfinfo",str(original)],timeout=15)
    if ret.returncode:
        raise ValueError("cannot verify original physical PDF page count")
    text=ret.stdout.decode("utf-8","replace")
    match=re.search(r"^Pages:\s*(\d+)\s*$",text,re.M)
    if not match:
        raise ValueError("missing exact physical PDF page count")
    count=int(match.group(1))
    if not 1<=count<=MAX_ORIGINAL_PAGES:
        raise ValueError("visual OCR original outside bounded page count")
    return count


def _pdf_page_rotation(original:Path,number:int)->int:
    ret=_with_timeout(["pdfinfo","-f",str(number),"-l",str(number),
                       "-box",str(original)],timeout=15)
    if ret.returncode:
        raise ValueError("unable to inspect original physical PDF page")
    match=re.search(rf"^Page\s+{number}\s+rot:\s*(\d+)\s*$",
                    ret.stdout.decode("utf-8","replace"),re.M)
    if not match:
        raise ValueError("physical PDF page rotation missing")
    rotation=int(match.group(1))
    # OCR word boxes are in the produced raster's top-left coordinates,
    # NOT asserted to be unrotated PDF-point rectangles. Poppler already
    # honors the PDF's /Rotate annotation when rasterizing. Preserve it.
    if rotation not in (0,90,180,270):
        raise ValueError("unrecognized PDF page rotation")
    return rotation


def _tesseract_binary_info(language:str)->dict:
    result=_with_timeout(["tesseract","--version"],timeout=10)
    if result.returncode:
        raise ValueError("local Tesseract not available")
    version=(result.stdout or result.stderr).decode("utf-8","replace").splitlines()[0][:130]
    available=_with_timeout(["tesseract","--list-langs"],timeout=10)
    if available.returncode:
        raise ValueError("local OCR language list unavailable")
    langs=set(available.stdout.decode("utf-8","replace").splitlines()+
              available.stderr.decode("utf-8","replace").splitlines())
    required=language.split("+")
    if not all(lang in langs for lang in required):
        raise ValueError("requested Tesseract language not installed locally")
    traineddata={}
    for lang in required:
        # Debian/Ubuntu's verified locally installed Tessdata directory.
        path=Path("/usr/share/tesseract-ocr/5/tessdata")/(lang+".traineddata")
        if path.is_symlink() or not path.is_file():
            raise ValueError("OCR traineddata unavailable or symlinked")
        traineddata[lang]={"sha256":_source_sha(path),"file_bytes":path.stat().st_size}
    return {"binary_version":version,"traineddata":traineddata,
            "provider":"tesseract_local_cpu_only"}


def _word_records(tsv_text:str, width:int,height:int)->tuple[list[dict],str,dict]:
    """Parse exact TSV word boxes and rebuild lines without invented prose."""
    if len(tsv_text.encode("utf-8"))>MAX_TESSERACT_TSV_BYTES:
        raise ValueError("OCR output exceeded bounded TSV size")
    reader=csv.DictReader(io.StringIO(tsv_text),delimiter="\t")
    required={"level","page_num","block_num","par_num","line_num",
              "word_num","left","top","width","height","conf","text"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("unrecognized Tesseract TSV schema")
    words=[]
    lines={}
    for row in reader:
        if len(words)>=30000:
            raise ValueError("OCR yielded excessive word bounding boxes")
        if row["level"]!="5":
            continue
        token=(row.get("text") or "").strip()
        if not token:
            continue
        if len(token)>250:
            raise ValueError("OCR word unexpectedly long")
        try:
            left,top,w,h=[int(row[x]) for x in ("left","top","width","height")]
            confidence=float(row["conf"])
            nums=tuple(int(row[x]) for x in ("page_num","block_num","par_num","line_num","word_num"))
        except (TypeError,ValueError) as exc:
            raise ValueError("invalid OCR word position or confidence") from exc
        if (not 0<=left<width or not 0<=top<height or
                w<1 or h<1 or left+w>width or top+h>height
                or not 0<=confidence<=100 or nums[0]!=1):
            raise ValueError("OCR word outside rendered physical page or impossible confidence")
        word={"text":token,"bbox_pixel_top_left":[left,top,left+w,top+h],
              "tesseract_confidence_not_calibrated":round(confidence,2),
              "line_key":[*nums[1:4]],"word_position":nums[4]}
        words.append(word)
        line_key=nums[1:4]
        lines.setdefault(line_key,[]).append((nums[4],token))
    output="\n".join(" ".join(token for _,token in sorted(v))
                     for _,v in sorted(lines.items()))
    stats={
        "word_count":len(words),
        "reconstructed_line_count":len(lines),
        "mean_word_confidence_not_calibrated":round(
            sum(w["tesseract_confidence_not_calibrated"] for w in words)/len(words),2,
        ) if words else None,
        "low_confidence_words_below_60":sum(
            w["tesseract_confidence_not_calibrated"]<60 for w in words
        ),
        "recognized_characters":len(output),
        "ocr_quality_not_verified":True,
    }
    return words,output,stats


def _mode_agreement(primary_text:str,secondary_text:str)->dict[str,Any]:
    """Two OCR page layouts, no ground truth and no automatic acceptance.

    A high word overlap but differing word sequence suggests that the
    reading order is ambiguous even when OCR token confidences are high.
    This deliberately never asserts which order is correct.
    """
    def tokens(text:str)->list[str]:
        normalized=unicodedata.normalize("NFKC",text).casefold()
        return re.findall(r"\S+",normalized)[:30000]
    a=tokens(primary_text)
    b=tokens(secondary_text)
    ca=Counter(a);cb=Counter(b)
    overlap=2*sum((ca & cb).values())/max(1,len(a)+len(b))
    # Limit SequenceMatcher quadratic input for corrupted OCR outputs.
    # High-volume pages are *unverified*, not falsely marked agreement.
    if max(len(a),len(b))>5000:
        return {
            "status":"comparison_too_many_tokens_for_bounded_alignment",
            "primary_words":len(a),"comparison_words":len(b),
            "bag_word_overlap":round(overlap,6),
            "sequence_similarity":None,"needs_layout_or_ocr_review":True,
            "no_ground_truth_accuracy_claim":True,
        }
    order=SequenceMatcher(None,a,b,autojunk=False).ratio() if a or b else 1.0
    if overlap>=.9 and order<.85:
        status="probable_reading_order_disagreement"
    elif order<.85:
        # Mixed cases must never fall through to a false all-clear merely
        # because the word-bag overlap lies between .85 and .90.
        status="mixed_recognition_and_reading_order_disagreement"
    elif overlap<.9:
        status="recognition_or_segmentation_disagreement"
    else:
        status="no_major_mode_disagreement_detected_not_verified"
    return {
        "status":status,"primary_words":len(a),"comparison_words":len(b),
        "bag_word_overlap":round(overlap,6),
        "sequence_similarity":round(order,6),
        "needs_layout_or_ocr_review":status!="no_major_mode_disagreement_detected_not_verified",
        "no_ground_truth_accuracy_claim":True,
        "warning":"Different OCR configurations on the SAME pixels; agreement is not accuracy and neither reading order is automatically trusted.",
    }


def _private_out_dir(where:Path,orig_root:Path,source_map_db:Path) -> Path:
    dest=Path(where).expanduser()
    if dest.exists() or dest.is_symlink():
        raise ValueError("refuse overwriting prior OCR evidence")
    if not dest.parent.is_dir() or dest.parent.is_symlink():
        raise ValueError("OCR output parent absent or symlinked")
    parent=dest.parent.resolve(strict=True)
    protected=Path(orig_root).resolve(strict=True)
    source_map=Path(source_map_db).resolve(strict=True)
    if (parent.is_relative_to(protected) or
            parent==source_map.parent or
            dest.resolve(strict=False)==source_map):
        raise ValueError("OCR preview output cannot write to original or native source-map data")
    if parent.is_relative_to(source_map.parent.parent):
        # The KMD root's private search-audit subtree is permitted; other
        # semantic or native-database directories are not.
        root=source_map.parent.parent
        if not parent.is_relative_to(root/"search-audit"):
            raise ValueError("OCR evidence under KMD data must use search-audit")
    return parent/dest.name


def extract_ocr_preview(
    *, source_root:Path, relative_pdf_path:str,
    approved_manifest:Path, completed_ledger:Path, source_map_db:Path,
    native_filedb:Path,physical_pages:list[int], output_dir:Path,
    dpi:int=220, psm:int=3, language:str="eng",
    comparison_psm:int|None=None,
)->dict[str,Any]:
    from PIL import Image
    if (type(dpi) is not int or not 120<=dpi<=MAX_DPI
            or type(psm) is not int or psm not in VALID_PSM
            or language not in VALID_LANG
            or (comparison_psm is not None
                and (type(comparison_psm) is not int
                     or comparison_psm not in VALID_PSM
                     or comparison_psm==psm))
            or not isinstance(physical_pages,list)
            or not 1<=len(physical_pages)<=MAX_PAGES_PER_RUN
            or any(type(n) is not int or n<1 or n>MAX_ORIGINAL_PAGES for n in physical_pages)
            or len(set(physical_pages))!=len(physical_pages)):
        raise ValueError("OCR source selection, page, dpi, PSM or language outside strict bounds")
    root=Path(source_root).resolve(strict=True)
    original,source=verify_original(
        root,relative_pdf_path,approved_manifest,completed_ledger)
    source_status=_source_map_error(
        Path(source_map_db),source["relative_path"],source["source_sha256"])
    native_link=_canonical_native_file_link(Path(native_filedb),source["relative_path"])
    pages_in_original=_pdf_physical_pages(original)
    if max(physical_pages)>pages_in_original:
        raise ValueError("OCR requested physical page beyond publisher original")
    provider=_tesseract_binary_info(language)
    output=_private_out_dir(Path(output_dir),root,Path(source_map_db))
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    pages=[]
    for num in physical_pages:
        rotation=_pdf_page_rotation(original,num)
        stem=f"page_{num:04d}"
        raster=output/(stem+".png")
        base=output/stem
        poppler=_with_timeout(
            ["pdftoppm","-f",str(num),"-l",str(num),
             "-singlefile","-r",str(dpi),"-gray","-png",
             str(original),str(base)],
            timeout=45)
        if poppler.returncode or not raster.is_file():
            raise ValueError("bounded source PDF page raster failed")
        if raster.stat().st_size>20*1024*1024:
            raise ValueError("OCR page raster exceeds 20MiB output guard")
        with Image.open(raster) as im:
            im.verify()
        with Image.open(raster) as im:
            w,h=im.size
        if w*h>MAX_PIXELS or w<400 or h<400:
            raise ValueError("unexpected source page pixel budget")
        png_sha=_source_sha(raster)
        tess=_with_timeout(["tesseract",str(raster),"stdout","-l",language,
                            "--psm",str(psm),"tsv"],timeout=110)
        if tess.returncode:
            raise ValueError("bounded local Tesseract OCR failed")
        raw=tess.stdout
        if len(raw)>MAX_TESSERACT_TSV_BYTES:
            raise ValueError("OCR returned excessive TSV")
        tsv=raw.decode("utf-8","replace")
        words,plain,stats=_word_records(tsv,w,h)
        if not plain.strip():
            raise ValueError("OCR produced no recognized source text")
        textpath=output/(stem+".txt")
        tsvpath=output/(stem+".tsv")
        wordpath=output/(stem+"_words.json")
        textpath.write_text(plain+"\n",encoding="utf-8")
        tsvpath.write_text(tsv,encoding="utf-8")
        wordpath.write_text(json.dumps(words,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        for p in (textpath,tsvpath,wordpath):
            p.chmod(0o600)
        comparison=None
        if comparison_psm is not None:
            other=_with_timeout(
                ["tesseract",str(raster),"stdout","-l",language,
                 "--psm",str(comparison_psm),"tsv"],timeout=110)
            if other.returncode:
                raise ValueError("comparison OCR mode failed on identical source raster")
            other_tsv=other.stdout.decode("utf-8","replace")
            compared_words,compared_text,compared_stats=_word_records(
                other_tsv,w,h)
            if not compared_text.strip():
                raise ValueError("comparison OCR mode returned no readable words")
            alt_stem=f"{stem}_comparison_psm{comparison_psm}"
            alt_text=output/(alt_stem+".txt")
            alt_tsv=output/(alt_stem+".tsv")
            alt_words=output/(alt_stem+"_words.json")
            alt_text.write_text(compared_text+"\n",encoding="utf-8")
            alt_tsv.write_text(other_tsv,encoding="utf-8")
            alt_words.write_text(json.dumps(compared_words,
                                             ensure_ascii=False,indent=2)+"\n",
                                 encoding="utf-8")
            for a in (alt_text,alt_tsv,alt_words):
                a.chmod(0o600)
            comparison={
                "psm":comparison_psm,
                "raster_sha256":png_sha,
                "text_candidate_file":alt_text.name,
                "text_candidate_sha256":_source_sha(alt_text),
                "word_boxes_file":alt_words.name,
                "word_boxes_sha256":_source_sha(alt_words),
                "raw_tsv_file":alt_tsv.name,
                "raw_tsv_sha256":_source_sha(alt_tsv),
                "ocr_stats":compared_stats,
                "mode_disagreement":_mode_agreement(plain,compared_text),
                "independent_source_authenticity":False,
                "different_OCR_not_ground_truth":True,
            }
        pages.append({
            "physical_pdf_page":num,"original_total_physical_pages":pages_in_original,
            "source_pdf_sha256":source["source_sha256"],
            "physical_pdf_page_rotation_degrees":rotation,
            "word_box_coordinate_scope":"top_left_pixels_of_Poppler_rendered_page_with_PDF_rotation_applied_not_PDF_point_coordinates",
            "raster_png_sha256":png_sha,"raster_pixels":[w,h],
            "raster_dpi":dpi,"poppler_renderer":"pdftoppm_gray",
            "ocr_psm":psm,"ocr_language":language,
            "transcript_candidate_path":textpath.name,
            "transcript_candidate_sha256":_source_sha(textpath),
            "word_boxes_path":wordpath.name,"word_boxes_sha256":_source_sha(wordpath),
            "raw_tesseract_tsv_path":tsvpath.name,"raw_tesseract_tsv_sha256":_source_sha(tsvpath),
            "ocr_stats":stats,
            "comparison_ocr_mode":comparison,
            "evidence_scope":"unverified_local_OCR_candidate_from_source_pinned_physical_PDF_page",
            "do_not_promote_as_completed_original":True,
        })
    if _source_sha(original)!=source["source_sha256"]:
        raise ValueError("original changed during OCR preview")
    result={
        "schema":"all2text.verified_scanned_pdf_ocr_preview.v1",
        "source":source,"source_map":source_status,
        "canonical_native_filedb":native_link,
        "provider":provider,
        "ocr_comparison_psm":comparison_psm,
        "method":"bounded local image-only PDF OCR preview; not a verified transcript",
        "source_pdf_total_pages":pages_in_original,
        "physical_pages_processed":len(pages),
        "full_original_extracted":False,
        "production_KMD_FileDB_modified":False,
        "source_map_modified":False,
        "original_pdf_modified":False,
        "limitations":[
            "No ground-truth accuracy for source pages; mean OCR confidence is not calibrated text correctness",
            "Scanned image text and word boxes are untrusted data; OCR may misread words, formulas, figures or ordering",
            "Unprocessed original pages are not represented; this is NOT complete document extraction",
            "Do not use for legal assertions or model training without independent source and rights validation",
        ],
        "pages":pages,
    }
    manifest=output/"ocr_preview.json"
    manifest.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    manifest.chmod(0o600)
    return result
