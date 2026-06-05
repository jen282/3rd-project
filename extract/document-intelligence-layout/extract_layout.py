"""
통계기초.pdf → Azure Document Intelligence prebuilt-layout
단락(paragraphs), 표(tables), 그림(figures) 전체를 추출해 JSON으로 저장한다.

PDF를 직접 업로드하므로 PNG 변환 불필요 (디지털 PDF 전용).
그림 크롭은 PyMuPDF로 처리한다.

사용법:
  python extract_layout.py
  python extract_layout.py --pdf 통계기초.pdf --pages 1-10
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import fitz  # PyMuPDF
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DI_ENDPOINT = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
DI_KEY      = os.environ["DOCUMENT_INTELLIGENCE_KEY"]

_parser = argparse.ArgumentParser()
_parser.add_argument("--pdf",   default="통계기초.pdf")
_parser.add_argument("--pages", default=None, help="페이지 범위 (예: 1-10 또는 1,3,5-10)")
_args = _parser.parse_args()

PDF_PATH    = Path(__file__).parent.parent / "data" / _args.pdf
RESULT_DIR  = Path(__file__).parent / "result_layout"
TABLES_DIR  = RESULT_DIR / "tables"
FIG_DIR     = RESULT_DIR / "figures" / "img"
LAYOUT_JSON   = RESULT_DIR / "layout.json"
CONTENT_TXT   = RESULT_DIR / "content.txt"       # DI 원본 텍스트 (읽기 순서)
FORMATTED_TXT = RESULT_DIR / "text_result.txt"   # 페이지/역할별 정리 텍스트

SCALE = 2.0  # figure 크롭 해상도 배율 (2x ≈ 144 dpi)

di_client = DocumentIntelligenceClient(
    endpoint=DI_ENDPOINT,
    credential=AzureKeyCredential(DI_KEY),
)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def polygon_to_bbox_inches(polygon: list[float]) -> list[float]:
    """DI polygon (inch 좌표 x,y 반복) → [x0, y0, x1, y1] in inches"""
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def crop_and_save(doc: fitz.Document, page_num_0based: int,
                  polygon: list[float], out_path: Path) -> None:
    """DI inch 좌표 → PyMuPDF 크롭 → PNG 저장"""
    x0, y0, x1, y1 = polygon_to_bbox_inches(polygon)
    rect = fitz.Rect(x0 * 72, y0 * 72, x1 * 72, y1 * 72)  # inch → point
    page = doc[page_num_0based]
    pix  = page.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), clip=rect)
    pix.save(str(out_path))


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def parse_result(result, doc: fitz.Document) -> list[dict]:
    pages: dict[int, dict] = {}

    def get_page(page_number: int) -> dict:  # page_number: 1-based (DI 기준)
        if page_number not in pages:
            pages[page_number] = {
                "page":       page_number,
                "paragraphs": [],
                "tables":     [],
                "figures":    [],
            }
        return pages[page_number]

    # ── 단락 ────────────────────────────────────────────────────────────────
    for para in (result.paragraphs or []):
        for region in (para.bounding_regions or []):
            entry = {
                "role":    para.role or "body",
                "content": para.content,
                "bbox_in": polygon_to_bbox_inches(region.polygon),
            }
            get_page(region.page_number)["paragraphs"].append(entry)

    # ── 표 ──────────────────────────────────────────────────────────────────
    for t_idx, table in enumerate(result.tables or []):
        page_num = (
            table.bounding_regions[0].page_number
            if table.bounding_regions else 1
        )

        grid = [[""] * table.column_count for _ in range(table.row_count)]
        for cell in (table.cells or []):
            grid[cell.row_index][cell.column_index] = cell.content

        table_rec = {
            "table_index": t_idx,
            "page":        page_num,
            "rows":        table.row_count,
            "cols":        table.column_count,
            "data":        grid,
        }

        (TABLES_DIR / f"table_{t_idx:03d}.json").write_text(
            json.dumps(table_rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        get_page(page_num)["tables"].append(table_rec)

    # ── 그림 ────────────────────────────────────────────────────────────────
    fig_count: dict[int, int] = {}
    for fig in (result.figures or []):
        region = fig.bounding_regions[0] if fig.bounding_regions else None
        if not region or not region.polygon:
            continue

        pn  = region.page_number
        idx = fig_count.get(pn, 0)
        fig_count[pn] = idx + 1

        img_name = f"page{pn:03d}_img{idx:02d}.png"
        crop_and_save(doc, pn - 1, region.polygon, FIG_DIR / img_name)

        caption = (fig.caption.content.strip()
                   if fig.caption and fig.caption.content else "")

        get_page(pn)["figures"].append({
            "img_path": f"figures/img/{img_name}",
            "caption":  caption,
            "bbox_in":  polygon_to_bbox_inches(region.polygon),
        })

    return [v for _, v in sorted(pages.items())]


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    print(f"PDF : {PDF_PATH.name}")
    if _args.pages:
        print(f"페이지 범위: {_args.pages}")

    pdf_bytes = PDF_PATH.read_bytes()

    print("Document Intelligence 분석 중 (전체 PDF 전송)...")
    kwargs = {}
    if _args.pages:
        kwargs["pages"] = _args.pages

    poller = di_client.begin_analyze_document(
        "prebuilt-layout",
        pdf_bytes,
        content_type="application/pdf",
        **kwargs,
    )
    result = poller.result()

    total_pages = len(result.pages) if result.pages else 0
    print(f"인식 완료 — {total_pages}페이지")

    doc        = fitz.open(str(PDF_PATH))
    pages_data = parse_result(result, doc)
    doc.close()

    LAYOUT_JSON.write_text(
        json.dumps(pages_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── content.txt: DI 원본 텍스트 (읽기 순서 그대로) ──────────────────────
    if result.content:
        CONTENT_TXT.write_text(result.content, encoding="utf-8")

    # ── text_result.txt: 페이지/역할별 정리 텍스트 ──────────────────────────
    lines = [
        "=" * 60,
        f"Document Intelligence text extraction result",
        f"PDF: {PDF_PATH.name}",
        "=" * 60,
    ]
    for page in pages_data:
        pn    = page["page"]
        paras = page["paragraphs"]
        tabs  = page["tables"]
        figs  = page["figures"]
        lines.append(f"\n[page {pn}] paragraphs={len(paras)}  tables={len(tabs)}  figures={len(figs)}")
        lines.append("-" * 50)
        for para in paras:
            lines.append(f"[{para['role']}] {para['content']}")
        for t in tabs:
            lines.append(f"\n  [table {t['table_index']}]  {t['rows']}행 x {t['cols']}열")
            for row in t["data"]:
                lines.append("  | " + " | ".join(row) + " |")
        for fig in figs:
            caption = f"  caption: {fig['caption']}" if fig["caption"] else ""
            lines.append(f"\n  [figure] {fig['img_path']}{caption}")

    FORMATTED_TXT.write_text("\n".join(lines), encoding="utf-8")

    n_para  = sum(len(p["paragraphs"]) for p in pages_data)
    n_table = sum(len(p["tables"])     for p in pages_data)
    n_fig   = sum(len(p["figures"])    for p in pages_data)

    print(f"\n결과 저장 → {RESULT_DIR}")
    print(f"  단락 {n_para}개  |  표 {n_table}개  |  그림 {n_fig}개")
    print(f"  layout.json     : {LAYOUT_JSON}")
    print(f"  content.txt     : {CONTENT_TXT}  (DI 원본 텍스트)")
    print(f"  text_result.txt : {FORMATTED_TXT}  (페이지/역할별 정리)")
    if n_table:
        print(f"  tables/         : table_000.json ~ table_{n_table - 1:03d}.json")
    if n_fig:
        print(f"  figures/img/    : {n_fig}개 PNG")


if __name__ == "__main__":
    main()
