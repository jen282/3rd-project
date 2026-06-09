"""
LlamaIndex를 사용해 PDF → 텍스트 추출 테스트 (로컬, API 키 불필요)
출력: result/llamaindex/<pdf명>.md
설치: pip install llama-index-readers-file
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = Path(__file__).parent / "result" / "llamaindex"

PDF_FILES = [
    DATA_DIR / "국사교과서.pdf",
    DATA_DIR / "통계기초.pdf",
]


def convert(pdf_path: Path, reader) -> None:
    print(f"\n[LlamaIndex] 변환 시작: {pdf_path.name}")
    documents = reader.load_data(file=pdf_path)
    text = "\n\n".join(doc.text for doc in documents)

    out_file = OUTPUT_DIR / f"{pdf_path.stem}.md"
    out_file.write_text(text, encoding="utf-8")
    print(f"  → 저장 완료: {out_file}")
    print(f"  → 페이지 수: {len(documents)}, 글자 수: {len(text):,}")


def main():
    try:
        from llama_index.readers.file import PDFReader
    except ImportError:
        print("[오류] llama-index-readers-file 패키지가 없습니다.")
        print("  설치: pip install llama-index-readers-file")
        return

    reader = PDFReader()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_path in PDF_FILES:
        if not pdf_path.exists():
            print(f"[오류] 파일 없음: {pdf_path}")
            continue
        convert(pdf_path, reader)

    print("\n[LlamaIndex] 전체 완료")


if __name__ == "__main__":
    main()
