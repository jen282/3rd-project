"""
Azure Document Intelligence prebuilt-layout으로 국사교과서.pdf 텍스트 추출.
스캔 PDF라 OCR이 필요하므로 DI를 사용한다.

출력: result-scan-txt/
  - page000.txt ~ pageNNN.txt  : 페이지별 텍스트
  - report.json                : 페이지별 문자 수 요약
"""

import io
import json
import os
import time
from pathlib import Path

import fitz  # PyMuPDF — 페이지 → PNG 변환용
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

# ── 설정 ─────────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

DI_ENDPOINT = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
DI_KEY      = os.environ["DOCUMENT_INTELLIGENCE_KEY"]

PDF_PATH   = Path(__file__).parent.parent / "data" / "raw" / "국사교과서.pdf"
RESULT_DIR = Path(__file__).parent / "result-scan-txt"
SCALE      = 2.0   # 144 dpi — DI 50 MB 제한 대응

RESULT_DIR.mkdir(parents=True, exist_ok=True)

# ── 클라이언트 ────────────────────────────────────────────────────────────────
di_client = DocumentIntelligenceClient(
    endpoint=DI_ENDPOINT,
    credential=AzureKeyCredential(DI_KEY),
)


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def page_to_png_bytes(page: fitz.Page, scale: float = SCALE) -> bytes:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    buf = io.BytesIO()
    buf.write(pix.tobytes("png"))
    return buf.getvalue()


def analyze_page(png_bytes: bytes) -> str:
    """DI prebuilt-layout으로 한 페이지 분석 → 전체 텍스트 반환."""
    poller = di_client.begin_analyze_document(
        "prebuilt-layout",
        io.BytesIO(png_bytes),
        content_type="image/png",
    )
    result = poller.result()
    return result.content or ""


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    doc = fitz.open(str(PDF_PATH))
    total = len(doc)
    print(f"PDF : {PDF_PATH.name}  ({total} pages)")
    print(f"출력: {RESULT_DIR}/\n")

    report_pages = []
    start_all = time.time()

    for page_num in range(total):
        page      = doc[page_num]
        png_bytes = page_to_png_bytes(page)

        print(f"[page {page_num:03d}/{total-1:03d}] DI 분석 중...", end=" ", flush=True)
        t0   = time.time()
        text = analyze_page(png_bytes)
        elapsed = round(time.time() - t0, 2)

        out_path = RESULT_DIR / f"page{page_num:03d}.txt"
        out_path.write_text(text, encoding="utf-8")

        print(f"{len(text):,} chars  ({elapsed}s)")
        report_pages.append({"page": page_num, "char_count": len(text), "elapsed_sec": elapsed})

    doc.close()

    total_elapsed = round(time.time() - start_all, 2)
    total_chars   = sum(p["char_count"] for p in report_pages)
    non_empty     = sum(1 for p in report_pages if p["char_count"] > 0)

    report = {
        "pdf_path":       str(PDF_PATH),
        "total_pages":    total,
        "non_empty_pages": non_empty,
        "total_chars":    total_chars,
        "elapsed_sec":    total_elapsed,
        "pages":          report_pages,
    }
    (RESULT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n--- 완료 ---")
    print(f"총 페이지        : {total}")
    print(f"텍스트 있는 페이지: {non_empty}")
    print(f"총 문자 수       : {total_chars:,}")
    print(f"소요 시간        : {total_elapsed}s")
    print(f"리포트           : {RESULT_DIR / 'report.json'}")


if __name__ == "__main__":
    main()
