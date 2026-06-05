"""
통계기초.pdf → Azure Document Intelligence prebuilt-read
prebuilt-layout과 달리 도형(shape) 안 텍스트까지 추출한다.
표/그림 크롭은 지원하지 않는다.

출력:
  result_read/read.json        페이지별 lines + paragraphs
  result_read/content.txt      DI 원본 텍스트 (읽기 순서)
  result_read/text_result.txt  페이지별 정리 텍스트

사용법:
  python extract_read.py
  python extract_read.py --pdf 통계기초.pdf --pages 1-10
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

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

PDF_PATH      = Path(__file__).parent.parent / "data" / _args.pdf
RESULT_DIR    = Path(__file__).parent / "result_read"
READ_JSON     = RESULT_DIR / "read.json"
CONTENT_TXT   = RESULT_DIR / "content.txt"
FORMATTED_TXT = RESULT_DIR / "text_result.txt"

RESULT_DIR.mkdir(parents=True, exist_ok=True)

di_client = DocumentIntelligenceClient(
    endpoint=DI_ENDPOINT,
    credential=AzureKeyCredential(DI_KEY),
)


def polygon_to_bbox_inches(polygon: list[float]) -> list[float]:
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def parse_result(result) -> list[dict]:
    # paragraphs를 (page_number, content) 로 빠르게 조회하기 위한 맵
    para_map: dict[int, list[dict]] = {}
    for para in (result.paragraphs or []):
        for region in (para.bounding_regions or []):
            pn = region.page_number
            para_map.setdefault(pn, []).append({
                "role":    para.role or "body",
                "content": para.content,
                "bbox_in": polygon_to_bbox_inches(region.polygon),
            })

    pages_data = []
    for page in (result.pages or []):
        pn = page.page_number  # 1-based

        # lines: 도형 텍스트를 포함한 모든 텍스트 라인
        lines = []
        for line in (page.lines or []):
            entry = {"content": line.content}
            if line.polygon:
                entry["bbox_in"] = polygon_to_bbox_inches(line.polygon)
            lines.append(entry)

        pages_data.append({
            "page":       pn,
            "width_in":   page.width,
            "height_in":  page.height,
            "line_count": len(lines),
            "lines":      lines,
            "paragraphs": para_map.get(pn, []),
        })

    return pages_data


def build_text_result(pages_data: list[dict]) -> str:
    parts = [
        "=" * 60,
        "Document Intelligence READ result",
        f"PDF: {PDF_PATH.name}",
        "=" * 60,
    ]
    for page in pages_data:
        pn = page["page"]
        parts.append(
            f"\n[page {pn}]  lines={page['line_count']}  "
            f"paragraphs={len(page['paragraphs'])}"
        )
        parts.append("-" * 50)
        for line in page["lines"]:
            parts.append(line["content"])
    return "\n".join(parts)


def main():
    print(f"PDF  : {PDF_PATH.name}")
    if _args.pages:
        print(f"범위 : {_args.pages}")

    pdf_bytes = PDF_PATH.read_bytes()

    print("prebuilt-read 분석 중...")
    kwargs = {}
    if _args.pages:
        kwargs["pages"] = _args.pages

    poller = di_client.begin_analyze_document(
        "prebuilt-read",
        pdf_bytes,
        content_type="application/pdf",
        **kwargs,
    )
    result = poller.result()

    total_pages = len(result.pages) if result.pages else 0
    print(f"인식 완료 : {total_pages}페이지")

    pages_data = parse_result(result)

    READ_JSON.write_text(
        json.dumps(pages_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if result.content:
        CONTENT_TXT.write_text(result.content, encoding="utf-8")

    FORMATTED_TXT.write_text(
        build_text_result(pages_data),
        encoding="utf-8",
    )

    total_lines = sum(p["line_count"] for p in pages_data)
    total_para  = sum(len(p["paragraphs"]) for p in pages_data)

    print(f"\n결과 저장 -> {RESULT_DIR}")
    print(f"  라인 {total_lines}개  |  단락 {total_para}개")
    print(f"  read.json       : {READ_JSON}")
    print(f"  content.txt     : {CONTENT_TXT}")
    print(f"  text_result.txt : {FORMATTED_TXT}")


if __name__ == "__main__":
    main()
