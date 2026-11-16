#!/usr/bin/env python3
"""Bounded original-SHA-verified private OCR previews on unresolved scanned PDFs."""
import argparse
import json
from pathlib import Path
import sys


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",type=Path,required=True)
    p.add_argument("--relative-pdf-path",required=True)
    p.add_argument("--approved-manifest",type=Path,required=True)
    p.add_argument("--completed-ledger",type=Path,required=True)
    p.add_argument("--source-map-db",type=Path,required=True)
    p.add_argument("--filedb",type=Path,required=True)
    p.add_argument("--page",action="append",type=int,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--dpi",type=int,default=220)
    p.add_argument("--psm",type=int,default=3)
    p.add_argument("--compare-psm",type=int,default=None,
                   help="Optional second page segmentation mode for source reading-order disagreement only")
    p.add_argument("--lang",default="eng")
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
    from all2text.scanned_pdf_ocr_evidence import extract_ocr_preview
    report=extract_ocr_preview(
        source_root=args.source_root,relative_pdf_path=args.relative_pdf_path,
        approved_manifest=args.approved_manifest,completed_ledger=args.completed_ledger,
        source_map_db=args.source_map_db,native_filedb=args.filedb,
        physical_pages=args.page,
        output_dir=args.output_dir,dpi=args.dpi,psm=args.psm,language=args.lang,
        comparison_psm=args.compare_psm,
    )
    print(json.dumps({
        "source":report["source"]["relative_path"],
        "source_sha256":report["source"]["source_sha256"],
        "pages_processed":report["physical_pages_processed"],
        "canonical_native_entry_id":report["canonical_native_filedb"]["filesystem_entry_id"],
        "existing_native_chunk_count":report["canonical_native_filedb"]["existing_native_chunk_count"],
        "pages_in_original":report["source_pdf_total_pages"],
        "ocr_candidates_unverified":True,
        "output_dir":str(args.output_dir),
        "ocr_stats":[p["ocr_stats"] for p in report["pages"]],
        "comparison_mode_disagreements":[
            p["comparison_ocr_mode"]["mode_disagreement"] if p["comparison_ocr_mode"] else None
            for p in report["pages"]
        ],
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
