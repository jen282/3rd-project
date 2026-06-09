"""
LlamaParse를 사용해 PDF → Markdown 변환 테스트
API 키: 환경변수 LLAMA_CLOUD_API_KEY 또는 스크립트 내 직접 입력
출력: result/llamaparse/<pdf명>.md
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = Path(__file__).parent / "result" / "llamaparse"

PDF_FILES = [
    DATA_DIR / "국사교과서.pdf",
    DATA_DIR / "통계기초.pdf",
]

# API 키: 환경변수 우선, 없으면 아래에 직접 입력
LLAMA_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "")


def convert(pdf_path: Path, parser) -> None:
    print(f"\n[LlamaParse] 변환 시작: {pdf_path.name}")
    documents = parser.load_data(str(pdf_path))
    md_text = "\n\n".join(doc.text for doc in documents)

    out_file = OUTPUT_DIR / f"{pdf_path.stem}.md"
    out_file.write_text(md_text, encoding="utf-8")
    print(f"  → 저장 완료: {out_file}")
    print(f"  → 페이지 수: {len(documents)}, 글자 수: {len(md_text):,}")


def main():
    if not LLAMA_API_KEY:
        print("[오류] LLAMA_CLOUD_API_KEY 환경변수가 설정되지 않았습니다.")
        print("  설정 방법: $env:LLAMA_CLOUD_API_KEY='your-api-key'  (PowerShell)")
        return

    try:
        from llama_parse import LlamaParse
    except ImportError:
        print("[오류] llama-parse 패키지가 없습니다: pip install llama-parse")
        return

    parser = LlamaParse(
        api_key=LLAMA_API_KEY,
        result_type="markdown",
        language="ko",
        verbose=True,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_path in PDF_FILES:
        if not pdf_path.exists():
            print(f"[오류] 파일 없음: {pdf_path}")
            continue
        convert(pdf_path, parser)

    print("\n[LlamaParse] 전체 완료")


if __name__ == "__main__":
    main()
