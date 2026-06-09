"""
Docling을 사용해 PDF → Markdown 변환 테스트
출력: result/docling/<pdf명>.md
"""
from pathlib import Path

from docling.document_converter import DocumentConverter

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = Path(__file__).parent / "result" / "docling"

PDF_FILES = [
    DATA_DIR / "국사교과서.pdf",
    DATA_DIR / "통계기초.pdf",
]


def convert(pdf_path: Path) -> None:
    print(f"\n[Docling] 변환 시작: {pdf_path.name}")
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    md_text = result.document.export_to_markdown()

    out_file = OUTPUT_DIR / f"{pdf_path.stem}.md"
    out_file.write_text(md_text, encoding="utf-8")
    print(f"  → 저장 완료: {out_file}")
    print(f"  → 글자 수: {len(md_text):,}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_path in PDF_FILES:
        if not pdf_path.exists():
            print(f"[오류] 파일 없음: {pdf_path}")
            continue
        convert(pdf_path)

    print("\n[Docling] 전체 완료")


if __name__ == "__main__":
    main()
