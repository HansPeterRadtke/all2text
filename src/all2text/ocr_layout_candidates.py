"""Experimental, conservative two-column reading-order candidates from OCR boxes.

No model or original PDF is modified. A candidate exists only if >=2
independently resolved pairs of adjacent text lines provide corroborating
column geometry. Multicolumn text, equations, captions and tables can defy
this rule; the output is not declared true and is never automatically
promoted to a searchable original representation.
"""
from __future__ import annotations

import math
import statistics
from typing import Any


def _line_nodes(words:list[dict])->list[dict]:
    grouped:dict[tuple[int,...],list[dict]]={}
    for w in words:
        key=w.get("line_key")
        coords=w.get("bbox_pixel_top_left")
        pos=w.get("word_position")
        if (not isinstance(key,list) or len(key)!=3 or
                not all(type(x) is int and x>=0 for x in key) or
                not isinstance(coords,list) or len(coords)!=4 or
                not all(type(x) is int for x in coords) or
                type(pos) is not int or pos<0 or
                not isinstance(w.get("text"),str)):
            raise ValueError("OCR word geometry or line identity invalid")
        grouped.setdefault(tuple(key),[]).append(w)
    lines=[]
    for key,group in grouped.items():
        if len({w["word_position"] for w in group})!=len(group):
            raise ValueError("ambiguous repeated Tesseract word position")
        left=min(w["bbox_pixel_top_left"][0] for w in group)
        top=min(w["bbox_pixel_top_left"][1] for w in group)
        right=max(w["bbox_pixel_top_left"][2] for w in group)
        bottom=max(w["bbox_pixel_top_left"][3] for w in group)
        lines.append({"key":list(key),"bbox":[left,top,right,bottom],
                      "text":" ".join(w["text"] for w in
                              sorted(group,key=lambda x:x["word_position"]))})
    return lines


def _overlap_y(a:dict,b:dict)->float:
    y0=max(a["bbox"][1],b["bbox"][1])
    y1=min(a["bbox"][3],b["bbox"][3])
    return max(0,y1-y0)/max(1,min(
        a["bbox"][3]-a["bbox"][1],b["bbox"][3]-b["bbox"][1]))


def two_column_candidate(
    *, words:list[dict[str,Any]], image_width:int, image_height:int,
)->dict[str,Any]:
    """Return a separately labeled reading-order guess, or explicit abstention."""
    if (type(image_width) is not int or type(image_height) is not int or
            image_width<400 or image_height<400 or
            not isinstance(words,list) or len(words)>30000):
        raise ValueError("unbounded OCR reading-order input")
    nodes=_line_nodes(words)
    default={"status":"abstained","text_candidate":None,
             "word_boxes_rearranged":False,
             "source_word_count":len(words),"line_count":len(nodes),
             "independent_source_ground_truth":False,
             "do_not_promote_to_native_filedb":True,
             "warning":"Column geometry is heuristic and cannot validate captions, equations, numeric tables or correct reading order."}
    if len(nodes)<4 or len(nodes)>400:
        return {**default,"reason":"too_few_or_too_many_lines"}
    pairs=[]
    for i,a in enumerate(nodes):
        for b in nodes[i+1:]:
            left,right=(a,b) if a["bbox"][0]<b["bbox"][0] else (b,a)
            gap=right["bbox"][0]-left["bbox"][2]
            if (gap<0.06*image_width or
                    right["bbox"][0]-left["bbox"][0]<0.25*image_width or
                    _overlap_y(left,right)<0.5):
                continue
            pairs.append((left,right))
    if len(pairs)<2:
        return {**default,"reason":"no_repeated_vertical_overlap_between_disjoint_columns"}
    # One sample per *left* line; prevent a dense chart legend from
    # inventing dozens of supporting column votes.
    unique={}
    for left,right in pairs:
        token=tuple(left["key"])
        candidate=(right["bbox"][0]-left["bbox"][2],left,right)
        if token not in unique or candidate[0]<unique[token][0]:
            unique[token]=candidate
    best=list(unique.values())
    if len(best)<2:
        return {**default,"reason":"only_one_independent_column_pair"}
    # Lines have different *lengths*: their right endpoints need not
    # align, so do not require their midpoint-gaps to be constant.
    # Column beginnings are much more stable than line endings.
    origins_left=[left["bbox"][0] for _,left,right in best]
    origins_right=[right["bbox"][0] for _,left,right in best]
    if (max(origins_left)-min(origins_left)>0.10*image_width or
            max(origins_right)-min(origins_right)>0.10*image_width):
        return {**default,"reason":"inconsistent_column_line_origins"}
    max_left_end=max(left["bbox"][2] for _,left,right in best)
    min_right_start=min(right["bbox"][0] for _,left,right in best)
    if min_right_start-max_left_end < 0.05*image_width:
        return {**default,"reason":"no_clear_separator_between_column_body_text"}
    med=(max_left_end+min_right_start)/2
    first=min(min(left["bbox"][1],right["bbox"][1]) for _,left,right in best)
    last=max(max(left["bbox"][3],right["bbox"][3]) for _,left,right in best)
    heights=[n["bbox"][3]-n["bbox"][1] for n in nodes]
    tolerance=max(8,statistics.median(heights))
    above=[];below=[];left_lines=[];right_lines=[]
    for n in nodes:
        mid=(n["bbox"][1]+n["bbox"][3])/2
        if mid<first-tolerance:above.append(n)
        elif mid>last+tolerance:below.append(n)
        elif n["bbox"][2] <= med-0.02*image_width:
            left_lines.append(n)
        elif n["bbox"][0] >= med+0.02*image_width:
            right_lines.append(n)
        else:
            return {**default,"reason":"spanning_or_unclear_lines_between_columns"}
    if min(len(left_lines),len(right_lines))<2:
        return {**default,"reason":"one_column_has_too_few_lines"}
    def order(seq:list[dict]):
        return sorted(seq,key=lambda node:(node["bbox"][1],node["bbox"][0],
                                            node["key"]))
    result=order(above)+order(left_lines)+order(right_lines)+order(below)
    if len(result)!=len(nodes) or len({tuple(n["key"]) for n in result})!=len(nodes):
        raise ValueError("column candidate failed conservation of OCR line identity")
    text="\n".join(n["text"] for n in result)
    return {
        **default,
        "status":"unverified_two_column_reading_order_candidate",
        "reason":"repeated_disjoint_lines_on_similar_rows",
        "text_candidate":text,
        "column_separator_pixel_x":round(med,2),
        "vertical_band_pixel_top_bottom":[first,last],
        "independent_line_pairs":len(best),
        "left_lines":len(left_lines),"right_lines":len(right_lines),
        "preamble_lines":len(above),"following_lines":len(below),
        "word_boxes_rearranged":False,
        "conservation_of_ocr_line_text":True,
    }
