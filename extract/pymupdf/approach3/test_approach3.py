"""
방안 3. pymupdf 블록 위치 정보 → 이미지 영역만 크롭
페이지에서 이미지 블록(type==1)의 bbox를 읽어 해당 영역만 크롭한다.
위치 메타데이터(bbox, 주변 텍스트)를 함께 저장한다.
벡터로 그린 다이어그램은 type==1로 잡히지 않는다.
"""

import fitz
from PIL import Image
import io
import json
import time
from pathlib import Path

PDF_PATH = "../../data/국사교과서.pdf"
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

SCALE = 2


def _get_surrounding_text(blocks: list, img_block: dict, window: int = 2) -> str:
    """이미지 블록 전후 텍스트 블록을 window 수만큼 모아 반환한다."""
    text_blocks = [b for b in blocks if b["type"] == 0]
    img_bbox = img_block["bbox"]

    # 이미지 y중심 기준으로 가장 가까운 텍스트 블록 선택
    def dist(tb):
        ty = (tb["bbox"][1] + tb["bbox"][3]) / 2
        iy = (img_bbox[1] + img_bbox[3]) / 2
        return abs(ty - iy)

    nearby = sorted(text_blocks, key=dist)[:window * 2]
    texts = []
    for tb in nearby:
        for line in tb.get("lines", []):
            for span in line.get("spans", []):
                texts.append(span.get("text", "").strip())
    return " ".join(t for t in texts if t)


def extract_image_blocks(pdf_path: str, scale: float = SCALE) -> dict:
    start = time.time()
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(scale, scale)

    stats = {
        "pdf_path": pdf_path,
        "total_pages": len(doc),
        "scale": scale,
        "crops": [],
        "errors": [],
    }

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        img_blocks = [b for b in blocks if b["type"] == 1]

        if not img_blocks:
            continue

        # 페이지 전체 렌더링 (크롭용)
        pix = page.get_pixmap(matrix=mat)
        page_img = Image.open(io.BytesIO(pix.tobytes("png")))

        for i, block in enumerate(img_blocks):
            try:
                x0, y0, x1, y1 = [int(v * scale) for v in block["bbox"]]
                # 경계 보정
                x0, y0 = max(0, x0), max(0, y0)
                x1, y1 = min(pix.width, x1), min(pix.height, y1)

                if x1 <= x0 or y1 <= y0:
                    continue

                cropped = page_img.crop((x0, y0, x1, y1))
                out_path = RESULTS_DIR / f"page{page_num:03d}_block{i:02d}.png"
                cropped.save(str(out_path))

                surrounding = _get_surrounding_text(blocks, block)

                crop_info = {
                    "page": page_num,
                    "block_index": i,
                    "bbox_pdf": block["bbox"],
                    "bbox_px": [x0, y0, x1, y1],
                    "width_px": x1 - x0,
                    "height_px": y1 - y0,
                    "surrounding_text": surrounding[:200],
                    "saved_as": str(out_path),
                }
                stats["crops"].append(crop_info)
                print(f"  [page {page_num:3d}] block{i}: bbox={block['bbox']} → {out_path.name}")
                if surrounding:
                    print(f"           주변텍스트: {surrounding[:60]}...")
            except Exception as e:
                err = f"page {page_num} block {i}: {e}"
                stats["errors"].append(err)
                print(f"  ERROR: {err}")

    doc.close()
    elapsed = time.time() - start
    stats["total_crops"] = len(stats["crops"])
    stats["elapsed_sec"] = round(elapsed, 3)
    return stats


def main():
    print("=" * 60)
    print("방안 3: pymupdf 블록 위치 기반 이미지 크롭 + 메타데이터")
    print("=" * 60)
    print(f"대상 PDF : {PDF_PATH}")
    print(f"렌더링 배율: {SCALE}x\n")

    stats = extract_image_blocks(PDF_PATH)

    print(f"\n--- 결과 요약 ---")
    print(f"총 페이지 수       : {stats['total_pages']}")
    print(f"크롭된 이미지 블록 : {stats['total_crops']}개")
    print(f"오류               : {len(stats['errors'])}건")
    print(f"소요 시간          : {stats['elapsed_sec']}초")

    # 주변 텍스트가 있는 블록 수
    with_text = sum(1 for c in stats["crops"] if c["surrounding_text"])
    print(f"주변 텍스트 확보   : {with_text}개 / {stats['total_crops']}개")

    report_path = RESULTS_DIR / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\n상세 리포트        : {report_path}")

    # GraphRAG 노드 구조 미리보기
    if stats["crops"]:
        print(f"\n--- GraphRAG 노드 구조 예시 (첫 번째 크롭) ---")
        sample = stats["crops"][0].copy()
        sample["concept"] = "(GPT-4o Vision으로 채울 필드)"
        sample["relations"] = []
        print(json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
