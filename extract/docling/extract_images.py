"""
Docling 기반 이미지 추출 테스트
- 스캔 PDF / 디지털 PDF 구분 없이 단일 파이프라인
- figure bbox + 이미지 bytes + surrounding_text + 캡션 추출
- 표(table)는 이미지와 분리하여 별도 JSON 기록

사용법:
  python extract_images.py --pdf 국사교과서.pdf --max-pages 15
  python extract_images.py --pdf 통계기초.pdf
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
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--pdf",        default="국사교과서.pdf")
parser.add_argument("--max-pages",  type=int, default=None)
parser.add_argument("--ocr",        action="store_true", help="OCR 활성화 (스캔 PDF용)")
parser.add_argument("--result-dir", default=None, help="결과 저장 폴더명 (기본: PDF명 기반 자동 설정)")
args = parser.parse_args()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "data"

PDF_PATH  = DATA_DIR / args.pdf
MAX_PAGES = args.max_pages

# 결과 폴더: 명시적으로 지정하지 않으면 PDF 이름 기반으로 자동 결정
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

# ── Docling 설정 ──────────────────────────────────────────────────────────────
pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr                  = args.ocr  # --ocr 플래그로 활성화
pipeline_options.do_table_structure      = True      # 표 구조 분석
pipeline_options.images_scale            = 2.0    # 크롭 이미지 해상도
pipeline_options.generate_picture_images = True   # figure 이미지 생성

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
            backend=PyPdfiumDocumentBackend,
        )
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
    """PictureItem 이미지를 PNG로 저장. 성공 여부 반환."""
    # 방법 1: pic.image.pil_image
    try:
        if pic.image and pic.image.pil_image:
            pic.image.pil_image.save(path, format="PNG")
            return True
    except Exception:
        pass

    # 방법 2: pic.get_image(doc) — 일부 버전
    try:
        img = pic.get_image()
        if img:
            img.save(path, format="PNG")
            return True
    except Exception:
        pass

    return False


def get_caption(pic: PictureItem, doc) -> str:
    """캡션 텍스트 추출."""
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
    """
    같은 페이지에서 bbox 중심과 수직 거리 window_pt 포인트 이내
    텍스트 아이템을 수집한다.
    """
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
        dist = abs((tb.t + tb.b) / 2 - img_cy)
        if dist <= window_pt:
            t = (item.text or "").strip()
            if t:
                texts.append(t)

    return " ".join(texts)[:300]


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    print(f"PDF     : {PDF_PATH.name}")
    print(f"최대 페이지: {MAX_PAGES or '전체'}")
    print()

    start = time.time()

    convert_kwargs = {}
    if MAX_PAGES:
        convert_kwargs["max_num_pages"] = MAX_PAGES

    result   = converter.convert(str(PDF_PATH), **convert_kwargs)
    doc      = result.document
    elapsed  = round(time.time() - start, 2)
    print(f"변환 완료: {elapsed}초\n")

    figures   = []
    tables    = []
    fig_count = 0

    # ── figure ───────────────────────────────────────────────────────────────
    for item, _ in doc.iterate_items():
        if not isinstance(item, PictureItem):
            continue

        prov    = item.prov[0] if item.prov else None
        page_no = prov.page_no if prov else None
        bbox    = prov.bbox    if prov else None

        img_name = f"page{page_no:03d}_fig{fig_count:02d}.png"
        img_path = IMG_DIR / img_name
        saved    = save_picture(item, img_path)

        caption    = get_caption(item, doc)
        surr_text  = get_surrounding_text(doc, page_no, bbox)

        figures.append({
            "page":             page_no,
            "bbox":             bbox_to_list(bbox),
            "caption":          caption,
            "surrounding_text": surr_text,
            "img_path":         f"img/{img_name}" if saved else "",
            "img_saved":        saved,
        })

        label = f"page={page_no}  bbox={bbox_to_list(bbox)}"
        print(f"  [figure {fig_count:02d}] {label}  →  {'저장' if saved else '이미지 없음'}")
        if caption:
            print(f"             caption: {caption[:60]}")
        if surr_text:
            print(f"             surr   : {surr_text[:60]}...")

        fig_count += 1

    # ── table ────────────────────────────────────────────────────────────────
    for item, _ in doc.iterate_items():
        if not isinstance(item, TableItem):
            continue
        prov    = item.prov[0] if item.prov else None
        page_no = prov.page_no if prov else None
        bbox    = prov.bbox    if prov else None
        tables.append({
            "page": page_no,
            "bbox": bbox_to_list(bbox),
        })
        print(f"  [table]  page={page_no}  bbox={bbox_to_list(bbox)}")

    elapsed_total = round(time.time() - start, 2)

    # ── JSON 저장 ─────────────────────────────────────────────────────────────
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
