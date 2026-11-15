#!/usr/bin/env python3
"""Extract bounded, original-SHA-linked private PDF image regions."""
import argparse
import json
from pathlib import Path
import sys

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--relative-pdf-path',required=True)
    p.add_argument('--approved-manifest',type=Path,required=True)
    p.add_argument('--completed-ledger',type=Path,required=True)
    p.add_argument('--page',type=int,action='append',required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--max-edge',type=int,default=1600)
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
    from all2text.pdf_visual_regions import extract_verified_pdf_regions
    d=extract_verified_pdf_regions(source_root=args.source_root,
      relative_pdf_path=args.relative_pdf_path,approved_manifest=args.approved_manifest,
      completed_ledger=args.completed_ledger,physical_pages=args.page,
      output_dir=args.output_dir,max_edge=args.max_edge)
    print(json.dumps({'original':d['original']['relative_path'],
      'source_sha256':d['original']['source_sha256'],'pages':len(d['pages']),
      'regions':len(d['regions']),'output_dir':str(args.output_dir)},indent=2))

if __name__=='__main__': main()
