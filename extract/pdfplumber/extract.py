"""
pdfplumber: 디지털 PDF 표 + 벡터 이미지 추출
- 표: find_tables()로 구조 추출 + 크롭 이미지
- 벡터 이미지: 표 영역 제외한 벡터 path 밀집 구역 → 크롭 이미지
렌더링은 PyMuPDF를 사용하고, 좌표 탐지는 pdfplumber를 사용한다.
"""

import pdfplumber
import fitz
from PIL import Image
import io
import json
import time
from pathlib import Path

PDF_PATH = "../data/통계기초.pdf"
RESULTS_DIR = Path("result-digital")
IMG_DIR = RESULTS_DIR / "img"

SCALE = 2
MIN_VECTOR_AREA = 4000   # 벡터 클러스터 최소 면적 (points²)
CLUSTER_MARGIN = 20      # 클러스터 병합 마진 (points)
MIN_VECTOR_OBJ = 3       # 클러스터 내 최소 오브젝트 수
SURROUND_WIN = 60        # 주변 텍스트 수집 범위 (points)
PAD = 4                  # 크롭 패딩 (points)


# ── 유틸 ───────────────────────────────────────────────

def _in_any_bbox(ob, bboxes, margin=2):
    ox0, oy0, ox1, oy1 = ob
    for tx0, ty0, tx1, ty1 in bboxes:
        if ox0 >= tx0 - margin and oy0 >= ty0 - margin and ox1 <= tx1 + margin and oy1 <= ty1 + margin:
            return True
    return False


def _overlaps(a, b, margin=0):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 - margin <= bx1 and bx0 - margin <= ax1 and ay0 - margin <= by1 and by0 - margin <= ay1


def _merge_bboxes(bboxes, margin):
    """인접/겹치는 bbox를 하나로 병합. 안정될 때까지 반복."""
    boxes = list(bboxes)
    changed = True
    while changed:
        changed = False
        result = []
        used = [False] * len(boxes)
        for i in range(len(boxes)):
            if used[i]:
                continue
            x0, y0, x1, y1 = boxes[i]
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                if _overlaps((x0, y0, x1, y1), boxes[j], margin):
                    bx0, by0, bx1, by1 = boxes[j]
                    x0, y0 = min(x0, bx0), min(y0, by0)
                    x1, y1 = max(x1, bx1), max(y1, by1)
                    used[j] = True
                    changed = True
            result.append((x0, y0, x1, y1))
        boxes = result
    return boxes


def _surrounding_text(plumber_page, bbox):
    """bbox 위·아래 영역 텍스트를 수집해 반환."""
    x0, top, x1, bottom = bbox
    w, h = plumber_page.width, plumber_page.height
    texts = []

    if top > 5:
        above = plumber_page.within_bbox(
            (0, max(0.0, top - SURROUND_WIN), w, top)
        ).extract_text() or ""
        if above.strip():
            texts.append(above.strip())

    if bottom < h - 5:
        below = plumber_page.within_bbox(
            (0, bottom, w, min(h, bottom + SURROUND_WIN))
        ).extract_text() or ""
        if below.strip():
            texts.append(below.strip())

    return " | ".join(texts)[:300]


def _crop_fitz(fitz_page, bbox):
    """pdfplumber bbox → PyMuPDF 렌더링 → PIL Image.
    두 라이브러리 모두 top-left origin 좌표계를 사용한다.
    """
    x0, top, x1, bottom = bbox
    ph, pw = fitz_page.rect.height, fitz_page.rect.width
    clip = fitz.Rect(
        max(0, x0 - PAD),
        max(0, top - PAD),
        min(pw, x1 + PAD),
        min(ph, bottom + PAD),
    )
    pix = fitz_page.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), clip=clip)
    return Image.open(io.BytesIO(pix.tobytes("png")))


# ── 표 추출 ────────────────────────────────────────────

def extract_tables(plumber_page, fitz_page, page_num, items):
    tables = plumber_page.find_tables()
    if not tables:
        return []

    table_bboxes = []
    for i, table in enumerate(tables):
        bbox = table.bbox
        table_bboxes.append(bbox)  # bbox는 필터 여부 무관하게 수집 (벡터 제외용)

        data = table.extract()
        rows = len(data)
        cols = max((len(r) for r in data), default=0)

        # 실제 표가 아닌 경우(1열 텍스트 블록) 이미지/JSON 저장 생략
        if cols < 2:
            continue

        surrounding = _surrounding_text(plumber_page, bbox)

        img_name = f"page{page_num:03d}_table{i:02d}.png"
        _crop_fitz(fitz_page, bbox).save(str(IMG_DIR / img_name))

        items.append({
            "type": "table",
            "page": page_num,
            "bbox": list(bbox),
            "rows": rows,
            "cols": cols,
            "data": data,
            "surrounding_text": surrounding,
            "img_path": f"img/{img_name}",
        })
        print(f"  [p{page_num:03d}] table  {i}: {rows}행 × {cols}열  →  {img_name}")

    return table_bboxes


# ── 벡터 이미지 추출 ───────────────────────────────────

def extract_vector_images(plumber_page, fitz_page, page_num, table_bboxes, items):
    pw, ph = plumber_page.width, plumber_page.height
    page_area = pw * ph

    # rects + lines + curves 에서 표 내부 오브젝트 제외
    raw = []
    for obj in plumber_page.rects + plumber_page.lines + plumber_page.curves:
        ob = (obj["x0"], obj["top"], obj["x1"], obj["bottom"])
        if _in_any_bbox(ob, table_bboxes):
            continue
        w = obj["x1"] - obj["x0"]
        h = obj["bottom"] - obj["top"]
        # 점·선 굵기 수준(2pt 미만) 무시
        if w < 2 and h < 2:
            continue
        # 페이지 너비/높이의 90% 이상을 차지하는 배경·테두리 오브젝트 무시
        if w > pw * 0.9 or h > ph * 0.9:
            continue
        # 개별 오브젝트 면적이 페이지의 50% 이상이면 배경 요소로 간주
        if w * h > page_area * 0.5:
            continue
        raw.append(ob)

    if not raw:
        return

    clusters = _merge_bboxes(raw, CLUSTER_MARGIN)

    for i, cluster in enumerate(clusters):
        x0, top, x1, bottom = cluster
        area = (x1 - x0) * (bottom - top)
        if area < MIN_VECTOR_AREA:
            continue
        # 클러스터가 페이지의 70% 이상을 덮으면 배경/전체 레이아웃으로 간주
        if area > page_area * 0.7:
            continue

        count = sum(1 for ob in raw if _overlaps(ob, cluster))
        if count < MIN_VECTOR_OBJ:
            continue

        surrounding = _surrounding_text(plumber_page, cluster)
        img_name = f"page{page_num:03d}_vector{i:02d}.png"
        _crop_fitz(fitz_page, cluster).save(str(IMG_DIR / img_name))

        items.append({
            "type": "vector_image",
            "page": page_num,
            "bbox": [round(v, 1) for v in cluster],
            "area_pts": round(area, 1),
            "vector_obj_count": count,
            "surrounding_text": surrounding,
            "img_path": f"img/{img_name}",
        })
        print(f"  [p{page_num:03d}] vector {i}: area={area:.0f}pts², objs={count}  →  {img_name}")


# ── 메인 ───────────────────────────────────────────────

def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    IMG_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("pdfplumber: 표 + 벡터 이미지 추출")
    print("=" * 60)
    print(f"대상 PDF : {PDF_PATH}")
    print(f"배율     : {SCALE}x\n")

    start = time.time()
    items = []

    with pdfplumber.open(PDF_PATH) as pdf:
        fitz_doc = fitz.open(PDF_PATH)
        for page_num, plumber_page in enumerate(pdf.pages):
            fitz_page = fitz_doc[page_num]
            table_bboxes = extract_tables(plumber_page, fitz_page, page_num, items)
            extract_vector_images(plumber_page, fitz_page, page_num, table_bboxes, items)
        fitz_doc.close()

    elapsed = time.time() - start
    tables = [r for r in items if r["type"] == "table"]
    vectors = [r for r in items if r["type"] == "vector_image"]

    print(f"\n{'=' * 60}")
    print(f"총 표           : {len(tables)}개")
    print(f"총 벡터 이미지  : {len(vectors)}개")
    print(f"소요 시간       : {elapsed:.3f}초")

    report = {
        "pdf_path": PDF_PATH,
        "scale": SCALE,
        "total_tables": len(tables),
        "total_vector_images": len(vectors),
        "elapsed_sec": round(elapsed, 3),
        "items": items,
    }
    report_path = RESULTS_DIR / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"리포트          : {report_path}")


if __name__ == "__main__":
    main()
