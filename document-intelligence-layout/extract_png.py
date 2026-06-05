"""
통계기초.pdf → 페이지별 PNG 변환 → Azure Document Intelligence
PDF 직접 전송 시 도형 텍스트를 못 읽는 문제를 PNG 변환으로 해결한다.
PNG로 전송하면 DI가 이미지 전체를 OCR 대상으로 처리한다.

prebuilt-read  : 텍스트만 추출 (lines, paragraphs)
prebuilt-layout: 텍스트 + 표 + 그림 크롭까지 추출

출력:
  result_png/read.json           페이지별 lines/paragraphs/figures
  result_png/content.txt         전체 텍스트 (페이지 구분자 포함)
  result_png/text_result.txt     페이지별 정리 텍스트
  result_png/figures/            크롭 이미지 (layout 모델 사용 시)

사용법:
  python extract_png.py                           # read 모델, 전체 페이지
  python extract_png.py --pages 1-5              # 앞 5장만
  python extract_png.py --model prebuilt-layout  # 텍스트 + 이미지 크롭
  python extract_png.py --scale 3.0              # 고해상도 (216dpi)
"""

import argparse
import io
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import fitz  # PyMuPDF
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from PIL import Image

load_dotenv(Path(__file__).parent.parent / ".env")

DI_ENDPOINT = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
DI_KEY      = os.environ["DOCUMENT_INTELLIGENCE_KEY"]

_parser = argparse.ArgumentParser()
_parser.add_argument("--pdf",    default="통계기초.pdf")
_parser.add_argument("--pages",  default=None, help="페이지 범위 (예: 1-5)")
_parser.add_argument("--scale",  type=float, default=2.0,
                     help="PNG 렌더링 배율 (기본 2.0 = 144dpi)")
_parser.add_argument("--model",  default="prebuilt-read",
                     choices=["prebuilt-read", "prebuilt-layout"],
                     help="사용할 DI 모델")
_parser.add_argument("--output", default="result_png",
                     help="결과 저장 폴더명 (기본: result_png)")
_args = _parser.parse_args()

PDF_PATH      = Path(__file__).parent.parent / "data" / _args.pdf
RESULT_DIR    = Path(__file__).parent / _args.output
FIG_DIR       = RESULT_DIR / "figures"
READ_JSON     = RESULT_DIR / "read.json"
CONTENT_TXT   = RESULT_DIR / "content.txt"
FORMATTED_TXT = RESULT_DIR / "text_result.txt"

RESULT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

MIN_AREA = 50 * 50  # 너무 작은 figure 제외 (px²)

di_client = DocumentIntelligenceClient(
    endpoint=DI_ENDPOINT,
    credential=AzureKeyCredential(DI_KEY),
)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def page_to_pil(page: fitz.Page, scale: float) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def polygon_to_bbox_px(polygon: list[float]) -> list[int]:
    """DI polygon (픽셀 좌표 x,y 반복) → [x0, y0, x1, y1]"""
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def crop_figure(img: Image.Image, bbox: list[int], out_path: Path) -> None:
    x0, y0, x1, y1 = bbox
    img.crop((x0, y0, x1, y1)).save(out_path, format="PNG")


# ── DI 분석 ──────────────────────────────────────────────────────────────────

def analyze_page(png_bytes: bytes) -> dict:
    poller = di_client.begin_analyze_document(
        _args.model,
        png_bytes,
        content_type="image/png",
    )
    result = poller.result()

    # lines
    lines = []
    if result.pages:
        for line in (result.pages[0].lines or []):
            entry = {"content": line.content}
            if line.polygon:
                entry["bbox"] = polygon_to_bbox_px(line.polygon)
            lines.append(entry)

    # paragraphs
    paragraphs = []
    for para in (result.paragraphs or []):
        paragraphs.append({
            "role":    para.role or "body",
            "content": para.content,
        })

    # figures (layout 모델에서만 반환)
    figures = []
    for fig in (result.figures or []):
        region = fig.bounding_regions[0] if fig.bounding_regions else None
        if not region or not region.polygon:
            continue
        bbox = polygon_to_bbox_px(region.polygon)
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if area < MIN_AREA:
            continue
        caption = (fig.caption.content.strip()
                   if fig.caption and fig.caption.content else "")
        figures.append({"bbox": bbox, "caption": caption})

    return {
        "lines":      lines,
        "paragraphs": paragraphs,
        "figures":    figures,
        "content":    result.content or "",
    }


# ── 페이지 범위 파싱 ──────────────────────────────────────────────────────────

def parse_pages_arg(pages_arg: str, total: int) -> list[int]:
    if not pages_arg:
        return list(range(1, total + 1))
    result = []
    for part in pages_arg.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-")
            result.extend(range(int(s), int(e) + 1))
        else:
            result.append(int(part))
    return [p for p in result if 1 <= p <= total]


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    print(f"PDF   : {PDF_PATH.name}")
    print(f"모델  : {_args.model}")
    print(f"배율  : {_args.scale}x ({int(_args.scale * 72)}dpi)")

    doc       = fitz.open(str(PDF_PATH))
    page_nums = parse_pages_arg(_args.pages, len(doc))
    print(f"페이지: {len(page_nums)}장 처리\n")

    pages_data   = []
    all_contents = []

    for pn in page_nums:
        pil_img   = page_to_pil(doc[pn - 1], _args.scale)
        png_bytes = pil_to_png_bytes(pil_img)

        print(f"  [page {pn:03d}] {pil_img.width}x{pil_img.height}px "
              f"{len(png_bytes) // 1024}KB → DI...", end=" ")

        page_result = analyze_page(png_bytes)

        n_lines = len(page_result["lines"])
        n_para  = len(page_result["paragraphs"])
        n_fig   = len(page_result["figures"])
        print(f"lines={n_lines}  para={n_para}  figures={n_fig}")

        # figure 크롭 저장
        fig_records = []
        for idx, fig in enumerate(page_result["figures"]):
            img_name = f"page{pn:03d}_img{idx:02d}.png"
            crop_figure(pil_img, fig["bbox"], FIG_DIR / img_name)
            fig_records.append({
                "img_path": f"figures/{img_name}",
                "caption":  fig["caption"],
                "bbox":     fig["bbox"],
            })

        pages_data.append({
            "page":       pn,
            "line_count": n_lines,
            "lines":      page_result["lines"],
            "paragraphs": page_result["paragraphs"],
            "figures":    fig_records,
        })
        all_contents.append(f"--- page {pn} ---\n{page_result['content']}")

    doc.close()

    # ── JSON ────────────────────────────────────────────────────────────────
    READ_JSON.write_text(
        json.dumps(pages_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── content.txt ─────────────────────────────────────────────────────────
    CONTENT_TXT.write_text("\n\n".join(all_contents), encoding="utf-8")

    # ── text_result.txt ─────────────────────────────────────────────────────
    parts = [
        "=" * 60,
        f"Document Intelligence PNG result  [{_args.model}]",
        f"PDF: {PDF_PATH.name}",
        "=" * 60,
    ]
    for page in pages_data:
        pn = page["page"]
        parts.append(
            f"\n[page {pn}]  lines={page['line_count']}  "
            f"paragraphs={len(page['paragraphs'])}  "
            f"figures={len(page['figures'])}"
        )
        parts.append("-" * 50)
        for line in page["lines"]:
            parts.append(line["content"])
        for fig in page["figures"]:
            cap = f"  caption: {fig['caption']}" if fig["caption"] else ""
            parts.append(f"\n  [figure] {fig['img_path']}{cap}")

    FORMATTED_TXT.write_text("\n".join(parts), encoding="utf-8")

    total_lines = sum(p["line_count"] for p in pages_data)
    total_figs  = sum(len(p["figures"]) for p in pages_data)

    print(f"\n완료  : 라인 {total_lines}개  그림 {total_figs}개 추출")
    print(f"  read.json       : {READ_JSON}")
    print(f"  content.txt     : {CONTENT_TXT}")
    print(f"  text_result.txt : {FORMATTED_TXT}")
    if total_figs:
        print(f"  figures/        : {total_figs}개 PNG  ({FIG_DIR})")


if __name__ == "__main__":
    main()
