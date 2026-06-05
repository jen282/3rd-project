"""
PyMuPDF로 PDF에서 텍스트만 추출한다.
- 국사교과서.pdf (스캔 PDF) → result-scan/
- 통계기초.pdf   (디지털 PDF) → result-digital/
"""

import fitz
import json
import time
from pathlib import Path

DATA_DIR = Path("../data/raw")

TARGETS = [
    {
        "pdf": DATA_DIR / "국사교과서.pdf",
        "out_dir": Path("result-scan"),
    },
    {
        "pdf": DATA_DIR / "통계기초.pdf",
        "out_dir": Path("result-digital"),
    },
]


def extract_text(pdf_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    doc = fitz.open(pdf_path)
    pages = []

    for page_num, page in enumerate(doc):
        text = page.get_text()
        pages.append({"page": page_num, "char_count": len(text), "text": text})

        out_path = out_dir / f"page{page_num:03d}.txt"
        out_path.write_text(text, encoding="utf-8")

    doc.close()
    elapsed = round(time.time() - start, 3)

    total_chars = sum(p["char_count"] for p in pages)
    non_empty = sum(1 for p in pages if p["char_count"] > 0)

    report = {
        "pdf_path": str(pdf_path),
        "total_pages": len(pages),
        "non_empty_pages": non_empty,
        "total_chars": total_chars,
        "elapsed_sec": elapsed,
        "pages": [{"page": p["page"], "char_count": p["char_count"]} for p in pages],
    }

    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main():
    for target in TARGETS:
        pdf_path = target["pdf"]
        out_dir = target["out_dir"]

        print(f"\n{'=' * 60}")
        print(f"PDF  : {pdf_path.name}")
        print(f"출력 : {out_dir}/")
        print("=" * 60)

        if not pdf_path.exists():
            print(f"  [오류] 파일 없음: {pdf_path}")
            continue

        report = extract_text(pdf_path, out_dir)

        print(f"  총 페이지     : {report['total_pages']}")
        print(f"  텍스트 있는 페이지: {report['non_empty_pages']}")
        print(f"  총 문자 수    : {report['total_chars']:,}")
        print(f"  소요 시간     : {report['elapsed_sec']}초")
        print(f"  리포트 저장   : {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
