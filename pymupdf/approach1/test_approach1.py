"""
방안 1. pymupdf 기본 — 래스터 이미지 추출
PDF에 포함된 래스터 이미지(jpeg, png 등)를 직접 추출한다.
벡터 그래픽은 추출되지 않는다.
"""

import fitz
import json
import time
from pathlib import Path

PDF_PATH = "../../data/국사교과서.pdf"
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def extract_raster_images(pdf_path: str) -> dict:
    start = time.time()
    doc = fitz.open(pdf_path)

    stats = {
        "pdf_path": pdf_path,
        "total_pages": len(doc),
        "images_found": [],
        "total_images": 0,
        "errors": [],
    }

    for page_num, page in enumerate(doc):
        images = page.get_images()
        for img_index, img in enumerate(images):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                ext = base_image["ext"]
                width = base_image["width"]
                height = base_image["height"]
                size_bytes = len(base_image["image"])

                out_path = RESULTS_DIR / f"page{page_num:03d}_img{img_index:02d}.{ext}"
                with open(out_path, "wb") as f:
                    f.write(base_image["image"])

                stats["images_found"].append({
                    "page": page_num,
                    "img_index": img_index,
                    "xref": xref,
                    "ext": ext,
                    "width": width,
                    "height": height,
                    "size_bytes": size_bytes,
                    "saved_as": str(out_path),
                })
                print(f"  [page {page_num:3d}] img{img_index}: {ext} {width}x{height} ({size_bytes:,} bytes) → {out_path.name}")
            except Exception as e:
                err = f"page {page_num} img_index {img_index} xref {xref}: {e}"
                stats["errors"].append(err)
                print(f"  ERROR: {err}")

    doc.close()
    elapsed = time.time() - start
    stats["total_images"] = len(stats["images_found"])
    stats["elapsed_sec"] = round(elapsed, 3)
    return stats


def main():
    print("=" * 60)
    print("방안 1: pymupdf 래스터 이미지 추출")
    print("=" * 60)
    print(f"대상 PDF: {PDF_PATH}\n")

    stats = extract_raster_images(PDF_PATH)

    print(f"\n--- 결과 요약 ---")
    print(f"총 페이지 수  : {stats['total_pages']}")
    print(f"추출된 이미지 : {stats['total_images']}개")
    print(f"오류          : {len(stats['errors'])}건")
    print(f"소요 시간     : {stats['elapsed_sec']}초")

    # 확장자별 통계
    ext_count: dict[str, int] = {}
    for img in stats["images_found"]:
        ext_count[img["ext"]] = ext_count.get(img["ext"], 0) + 1
    if ext_count:
        print(f"확장자 분포   : {ext_count}")

    # 결과를 JSON으로 저장
    report_path = RESULTS_DIR / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\n상세 리포트   : {report_path}")


if __name__ == "__main__":
    main()
