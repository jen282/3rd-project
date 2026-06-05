"""
Docling 기반 이미지 추출 — OCR 항상 활성화 버전
- 스캔 PDF / 디지털 PDF 구분 없이 동작
- PyPdfiumDocumentBackend 사용 (호환성 우선)
- OCR 강제 활성화로 스캔 PDF "not valid" 오류 방지

사용법:
  python extract_images_ocr.py --pdf 국사교과서.pdf --max-pages 15
  python extract_images_ocr.py --pdf 통계기초.pdf
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.document import PictureItem, TableItem, TextItem

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--pdf",        default="국사교과서.pdf")
parser.add_argument("--max-pages",  type=int, default=None)
parser.add_argument("--result-dir", default=None)
args = parser.parse_args()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "data"

PDF_PATH  = DATA_DIR / args.pdf
MAX_PAGES = args.max_pages

if args.result_dir:
    result_dir_name = args.result_dir
elif "국사" in args.pdf:
    result_dir_name = "result-scan"
elif "통계" in args.pdf:
    result_dir_name = "result-digital"
else:
    result_dir_name = "result"

RESULT_DIR = BASE_DIR / result_dir_name
IMG_DIR    = RESULT_DIR / "img"

IMG_DIR.mkdir(parents=True, exist_ok=True)

# ── Docling 설정 (OCR 항상 ON) ────────────────────────────────────────────────
pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr                  = True
pipeline_options.do_table_structure      = True
pipeline_options.images_scale            = 2.0
pipeline_options.generate_picture_images = True

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def bbox_to_list(bbox) -> list:
    if bbox is None:
        return []
    try:
        return [round(bbox.l, 1), round(bbox.t, 1),
                round(bbox.r, 1), round(bbox.b, 1)]
    except Exception:
        return []


def save_picture(pic: PictureItem, path: Path) -> bool:
    try:
        if pic.image and pic.image.pil_image:
            pic.image.pil_image.save(path, format="PNG")
            return True
    except Exception:
        pass
    try:
        img = pic.get_image()
        if img:
            img.save(path, format="PNG")
            return True
    except Exception:
        pass
    return False


def get_caption(pic: PictureItem, doc) -> str:
    try:
        return pic.caption_text(doc) or ""
    except Exception:
        pass
    try:
        if pic.captions:
            return " ".join(c.text for c in pic.captions if hasattr(c, "text"))
    except Exception:
        pass
    return ""


def get_surrounding_text(doc, page_no: int, bbox, window_pt: float = 80.0) -> str:
    if page_no is None or bbox is None:
        return ""
    img_cy = (bbox.t + bbox.b) / 2
    texts  = []
    for item, _ in doc.iterate_items():
        if not isinstance(item, TextItem):
            continue
        if not item.prov:
            continue
        prov = item.prov[0]
        if prov.page_no != page_no:
            continue
        tb = prov.bbox
        if tb is None:
            continue
        if abs((tb.t + tb.b) / 2 - img_cy) <= window_pt:
            t = (item.text or "").strip()
            if t:
                texts.append(t)
    return " ".join(texts)[:300]


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    print(f"PDF     : {PDF_PATH.name}")
    print(f"OCR     : ON (항상 활성화)")
    print(f"최대 페이지: {MAX_PAGES or '전체'}")
    print()

    start = time.time()

    convert_kwargs = {}
    if MAX_PAGES:
        convert_kwargs["page_range"] = (1, MAX_PAGES)

    result  = converter.convert(str(PDF_PATH), **convert_kwargs)
    doc     = result.document
    elapsed = round(time.time() - start, 2)
    print(f"변환 완료: {elapsed}초\n")

    figures   = []
    tables    = []
    fig_count = 0

    for item, _ in doc.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        prov    = item.prov[0] if item.prov else None
        page_no = prov.page_no if prov else None
        bbox    = prov.bbox    if prov else None

        img_name = f"page{page_no:03d}_fig{fig_count:02d}.png"
        saved    = save_picture(item, IMG_DIR / img_name)
        caption  = get_caption(item, doc)
        surr     = get_surrounding_text(doc, page_no, bbox)

        figures.append({
            "page":             page_no,
            "bbox":             bbox_to_list(bbox),
            "caption":          caption,
            "surrounding_text": surr,
            "img_path":         f"img/{img_name}" if saved else "",
            "img_saved":        saved,
        })

        print(f"  [figure {fig_count:02d}] page={page_no}  bbox={bbox_to_list(bbox)}  → {'저장' if saved else '이미지 없음'}")
        if caption:
            print(f"             caption: {caption[:60]}")
        if surr:
            print(f"             surr   : {surr[:60]}...")
        fig_count += 1

    for item, _ in doc.iterate_items():
        if not isinstance(item, TableItem):
            continue
        prov    = item.prov[0] if item.prov else None
        page_no = prov.page_no if prov else None
        bbox    = prov.bbox    if prov else None
        tables.append({"page": page_no, "bbox": bbox_to_list(bbox)})
        print(f"  [table]  page={page_no}  bbox={bbox_to_list(bbox)}")

    elapsed_total = round(time.time() - start, 2)

    stem = PDF_PATH.stem
    (RESULT_DIR / f"{stem}_figures.json").write_text(
        json.dumps(figures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RESULT_DIR / f"{stem}_tables.json").write_text(
        json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RESULT_DIR / f"{stem}_meta.json").write_text(
        json.dumps({
            "pdf":           PDF_PATH.name,
            "max_pages":     MAX_PAGES,
            "total_figures": len(figures),
            "img_saved":     sum(1 for f in figures if f["img_saved"]),
            "total_tables":  len(tables),
            "elapsed_sec":   elapsed_total,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n{'─'*50}")
    print(f"figure  : {len(figures)}개  (이미지 저장 {sum(1 for f in figures if f['img_saved'])}개)")
    print(f"table   : {len(tables)}개")
    print(f"소요 시간: {elapsed_total}초")
    print(f"저장 경로: {RESULT_DIR}")


if __name__ == "__main__":
    main()
