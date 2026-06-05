"""
방안 2. pymupdf 페이지 렌더링 — 벡터 포함 전체 캡처
페이지 전체를 PNG로 렌더링한다. 벡터 다이어그램, 수식, 표까지 모두 포함된다.
어떤 영역이 이미지인지 구분하지 않는다.
"""

import fitz
import json
import time
from pathlib import Path

PDF_PATH = "../../data/국사교과서.pdf"
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

# 렌더링 배율 (2 = 144dpi, 3 = 216dpi)
SCALE = 2


def render_pages(pdf_path: str, scale: float = SCALE) -> dict:
    start = time.time()
    doc = fitz.open(pdf_path)

    stats = {
        "pdf_path": pdf_path,
        "total_pages": len(doc),
        "scale": scale,
        "dpi": int(72 * scale),
        "pages_rendered": [],
        "errors": [],
    }

    mat = fitz.Matrix(scale, scale)

    for page_num, page in enumerate(doc):
        try:
            pix = page.get_pixmap(matrix=mat)
            out_path = RESULTS_DIR / f"page_{page_num:03d}.png"
            pix.save(str(out_path))

            page_stat = {
                "page": page_num,
                "width_px": pix.width,
                "height_px": pix.height,
                "size_bytes": len(pix.tobytes("png")),
                "saved_as": str(out_path),
            }
            stats["pages_rendered"].append(page_stat)
            print(f"  [page {page_num:3d}] {pix.width}x{pix.height}px → {out_path.name}")
        except Exception as e:
            err = f"page {page_num}: {e}"
            stats["errors"].append(err)
            print(f"  ERROR: {err}")

    doc.close()
    elapsed = time.time() - start
    stats["total_rendered"] = len(stats["pages_rendered"])
    stats["elapsed_sec"] = round(elapsed, 3)
    return stats


def main():
    print("=" * 60)
    print("방안 2: pymupdf 페이지 전체 렌더링 (벡터 포함)")
    print("=" * 60)
    print(f"대상 PDF : {PDF_PATH}")
    print(f"렌더링 배율: {SCALE}x ({int(72 * SCALE)} dpi)\n")

    stats = render_pages(PDF_PATH)

    print(f"\n--- 결과 요약 ---")
    print(f"총 페이지 수    : {stats['total_pages']}")
    print(f"렌더링 완료     : {stats['total_rendered']}페이지")
    print(f"오류            : {len(stats['errors'])}건")
    print(f"소요 시간       : {stats['elapsed_sec']}초")

    if stats["pages_rendered"]:
        sizes = [p["size_bytes"] for p in stats["pages_rendered"]]
        print(f"평균 파일 크기  : {sum(sizes) // len(sizes):,} bytes")
        print(f"최대 파일 크기  : {max(sizes):,} bytes")

    report_path = RESULTS_DIR / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\n상세 리포트     : {report_path}")


if __name__ == "__main__":
    main()
