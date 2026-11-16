#!/usr/bin/env python3
"""Known-ground-truth offline Tesseract benchmark, no publisher PDF downloaded.

Synthetic raster pages are generated from independent string ground truth,
then embedded as images in a PDF and rasterized anew with Poppler. Model
inputs contain only pixels. CER and WER measure literal transcription,
not clinical/legal correctness, layout generality or chart understanding.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from all2text.scanned_pdf_ocr_evidence import _word_records, _source_sha, _tesseract_binary_info
from PIL import Image,ImageDraw,ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def normalize(text:str)->str:
    norm=unicodedata.normalize("NFKC",text).casefold()
    return re.sub(r"\s+"," ",norm).strip()


def edit_distance(a:list|str,b:list|str)->int:
    """Strict Levenshtein distance with two bounded rows of memory."""
    if len(b)>len(a):
        a,b=b,a
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):
            cur.append(min(cur[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=cur
    return prev[-1]


def make_synthetic_pdf(path:Path, font_file:Path) -> dict:
    base=Image.new("RGB",(1653,2338),"white")
    draw=ImageDraw.Draw(base)
    title=ImageFont.truetype(str(font_file),43)
    normal=ImageFont.truetype(str(font_file),31)
    lines1=[
        "DOCUMENT OCR VALIDATION",
        "The source original must remain unchanged.",
        "Material roughness affects highlights and reflections.",
        "A scanned page can contain diagrams and charts.",
        "Only visible numeric values should be extracted.",
        "An uncertain label is better than an invented fact.",
    ]
    for i,line in enumerate(lines1):
        draw.text((96,160+i*120),line,font=title if i==0 else normal,fill="black")
    rows2_left=[
        "COLUMN ONE",
        "A coating changes a surface reflection.",
        "Science diagrams contain connected arrows.",
        "Original images need exact page positions.",
    ]
    rows2_right=[
        "COLUMN TWO",
        "Chart axes and units must be preserved.",
        "Some letters are difficult to decipher.",
        "Every uncertain value needs a warning.",
    ]
    second=Image.new("RGB",(1653,2338),"white")
    d=ImageDraw.Draw(second)
    font27=ImageFont.truetype(str(font_file),25)
    for row,text in enumerate(rows2_left):
        d.text((85,145+row*105),text,font=font27,fill="black")
    for row,text in enumerate(rows2_right):
        d.text((850,145+row*105),text,font=font27,fill="black")
    table=[
        "TABLE DATA",
        "Month Q1 Q2 Q3",
        "Output 10 20 30",
        "Input 14 25 36",
    ]
    for row,text in enumerate(table):
        d.text((180,960+row*105),text,font=normal,fill="black")
    pdf=canvas.Canvas(str(path),pagesize=(595,842))
    for picture in (base,second):
        pdf.drawImage(ImageReader(picture),0,0,width=595,height=842)
        pdf.showPage()
    pdf.save()
    return {
        "pages":[{"page":1,"layout":"single_column","text":"\n".join(lines1)},
                 {"page":2,"layout":"two_columns_and_table","text":"\n".join([*rows2_left,*rows2_right,*table])}],
        "generator":"Pillow exact text -> ReportLab embedded full-page image",
        "font_sha256":_source_sha(font_file),
        "source_pdf_sha256":_source_sha(path),
        "text_ground_truth_is_independent_of_ocr":True,
    }


def run_benchmark(output:Path, dpi_options:list[int], psm_options:list[int]) -> dict:
    if output.exists():
        raise ValueError("refuse to overwrite a previous synthetic OCR benchmark")
    if any(x not in (150,220,260) for x in dpi_options) or any(x not in (3,4,6,11) for x in psm_options):
        raise ValueError("unsupported benchmark DPI or page segmentation")
    output.mkdir(mode=0o700,parents=True)
    font=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not font.is_file():
        raise ValueError("local synthetic benchmark font missing")
    pdf=output/"synthetic_scanned_pages.pdf"
    reference=make_synthetic_pdf(pdf,font)
    provider=_tesseract_binary_info("eng")
    (output/"independent_ground_truth.json").write_text(json.dumps(reference,ensure_ascii=False,indent=2)+"\n")
    runs=[]
    for page in reference["pages"]:
        n=page["page"]
        gt=page["text"]
        for dpi in dpi_options:
            raster=output/f"p{n}_dpi{dpi}.png"
            prefix=output/f"p{n}_dpi{dpi}"
            p=subprocess.run(
                ["pdftoppm","-f",str(n),"-l",str(n),
                 "-singlefile","-r",str(dpi),"-gray","-png",
                 str(pdf),str(prefix)],
                capture_output=True,timeout=40)
            if p.returncode!=0:
                raise RuntimeError("Poppler synthetic benchmark raster failed")
            with Image.open(raster) as im:
                w,h=im.size
            for psm in psm_options:
                start=time.monotonic()
                q=subprocess.run(
                    ["tesseract",str(raster),"stdout","-l","eng",
                     "--psm",str(psm),"tsv"],
                    capture_output=True,timeout=75,
                    env={**os.environ,"OMP_THREAD_LIMIT":"1"},
                )
                if q.returncode:
                    raise RuntimeError("Tesseract synthetic benchmark invocation failed")
                txt=q.stdout.decode("utf-8","replace")
                words,out,stats=_word_records(txt,w,h)
                name=f"p{n}_dpi{dpi}_psm{psm}"
                (output/(name+".tsv")).write_text(txt)
                (output/(name+".txt")).write_text(out+"\n")
                a=normalize(gt)
                b=normalize(out)
                cer=edit_distance(a,b)/max(1,len(a))
                wer=edit_distance(a.split(),b.split())/max(1,len(a.split()))
                result={
                    "page":n,"layout":page["layout"],"dpi":dpi,"psm":psm,
                    "ground_truth_chars_normalized":len(a),
                    "recognized_chars_normalized":len(b),
                    "CER":round(cer,6),"WER":round(wer,6),
                    "word_boxes":stats["word_count"],
                    "tesseract_mean_confidence_not_accuracy":stats["mean_word_confidence_not_calibrated"],
                    "image_sha256":_source_sha(raster),
                    "transcript_sha256":_source_sha(output/(name+".txt")),
                    "raw_TSV_sha256":_source_sha(output/(name+".tsv")),
                    "elapsed_seconds":round(time.monotonic()-start,2),
                }
                runs.append(result)
                print("MEASURE",result,flush=True)
    payload={
        "schema":"all2text.synthetic_ocr_cer_wer_benchmark.v1",
        "source":reference,"provider":provider,
        "psms_tested":psm_options,"dpis_tested":dpi_options,
        "runs":runs,
        "limitations":[
            "Synthetic text-on-white pages are not representative of real scanned legislation or scientific figures",
            "Two-column and table reading order may score poorly even when individual characters are legible",
            "Tesseract confidence is not a calibrated accuracy score; CER/WER are relative to our separately authored source text only",
            "No real-world scanned PDF is promoted into KMD or declared extracted by this test",
        ],
    }
    result=output/"ocr_benchmark.json"
    result.write_text(json.dumps(payload,indent=2)+"\n")
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--dpi",action="append",type=int)
    p.add_argument("--psm",action="append",type=int)
    args=p.parse_args()
    d=run_benchmark(args.output,args.dpi or [150,220],args.psm or [3,4,6,11])
    print("BENCHMARK_RUNS",len(d["runs"]),"OUTPUT",args.output)


if __name__=="__main__":
    main()
