"""
pymupdf + tesseract OCR — 스캔 PDF 텍스트 추출
국사교과서.pdf: 텍스트 레이어 없는 스캔 기반 PDF
"""

import fitz
import pytesseract
from PIL import Image
import io
import json
import tempfile
import time
from pathlib import Path

PDF_PATH = "../../data/국사교과서.pdf"
RESULTS_DIR = Path("result_scan")
SCALE = 2          # 렌더링 배율 (높을수록 OCR 정확도 향상, 속도 저하)
LANG = "kor+eng"   # 한국어 + 영어 혼용 대응
TEST_PAGES = 5     # 전체 처리 시 None


def ocr_page(page, scale: float = SCALE) -> dict:
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)

    # Python 3.14 호환: PIL Image 직접 전달 대신 임시 파일 경유
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        pix.save(tmp_path)

    try:
        text = pytesseract.image_to_string(tmp_path, lang=LANG)
        data = pytesseract.image_to_data(tmp_path, lang=LANG, output_type=pytesseract.Output.DICT)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    confidences = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) >= 0]
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    return {
        "text": text.strip(),
        "char_count": len(text.strip()),
        "avg_confidence": avg_conf,
        "word_count": len([w for w in text.split() if w]),
    }


def main():
    print("=" * 60)
    print("pymupdf + tesseract OCR — 국사교과서.pdf")
    print("=" * 60)
    print(f"언어: {LANG} / 배율: {SCALE}x\n")

    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)
    target_pages = list(range(min(TEST_PAGES, total_pages))) if TEST_PAGES else list(range(total_pages))

    print(f"총 {total_pages}페이지 중 {len(target_pages)}페이지 처리\n")

    stats = {
        "pdf_path": PDF_PATH,
        "total_pages": total_pages,
        "processed_pages": len(target_pages),
        "scale": SCALE,
        "lang": LANG,
        "pages": [],
    }

    start = time.time()

    for page_num in target_pages:
        page = doc[page_num]
        t0 = time.time()
        result = ocr_page(page)
        elapsed = round(time.time() - t0, 2)

        # 텍스트 파일 저장
        txt_path = RESULTS_DIR / f"page{page_num:03d}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result["text"])

        page_stat = {
            "page": page_num,
            "char_count": result["char_count"],
            "word_count": result["word_count"],
            "avg_confidence": result["avg_confidence"],
            "elapsed_sec": elapsed,
            "saved_as": str(txt_path),
        }
        stats["pages"].append(page_stat)

        print(f"  [page {page_num:3d}] {result['char_count']:4d}자 / {result['word_count']:3d}단어 "
              f"/ 신뢰도 {result['avg_confidence']:5.1f}% / {elapsed}초")
        if result["text"]:
            preview = result["text"][:60].replace("\n", " ")
            print(f"           미리보기: {preview}...")

    doc.close()
    total_elapsed = round(time.time() - start, 2)
    stats["total_elapsed_sec"] = total_elapsed

    # 요약 통계
    chars = [p["char_count"] for p in stats["pages"]]
    confs = [p["avg_confidence"] for p in stats["pages"]]
    print(f"\n--- 결과 요약 ---")
    print(f"처리 페이지    : {len(target_pages)}페이지")
    print(f"총 추출 문자   : {sum(chars):,}자")
    print(f"페이지당 평균  : {sum(chars)//len(chars):,}자")
    print(f"평균 신뢰도    : {sum(confs)/len(confs):.1f}%")
    print(f"총 소요 시간   : {total_elapsed}초 (페이지당 {total_elapsed/len(target_pages):.1f}초)")

    with open(RESULTS_DIR / "report.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"리포트 저장    : result_scan/report.json")


if __name__ == "__main__":
    main()
