"""
raw_response.json에서 figure 좌표를 읽어 PyMuPDF로 PDF를 크롭하고
각 결과 폴더의 img/ 에 저장한다.

사용법:
  python crop_images.py
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SCALE = 2.0      # 렌더링 배율 (2× = 144 dpi)
MIN_AREA = 30 * 30  # 너무 작은 영역 제외 (px²)

TARGETS = [
    {
        "pdf":   Path(__file__).parent.parent.parent / "data/raw/국사교과서.pdf",
        "out":   Path(__file__).parent / "result-scan",
        "label": "국사교과서 (스캔)",
    },
    {
        "pdf":   Path(__file__).parent.parent.parent / "data/raw/통계기초.pdf",
        "out":   Path(__file__).parent / "result-digital",
        "label": "통계기초 (디지털)",
    },
]


def parse_source(source: str) -> list[dict]:
    """
    'D(page,x0,y0,x1,y1,...);D(...)' → [{"page": int, "bbox": [x0,y0,x1,y1]}, ...]
    좌표는 인치 단위, page는 1-based.
    """
    regions = []
    for m in re.finditer(r"D\((\d+),([\d.,]+)\)", source):
        page = int(m.group(1))
        coords = [float(v) for v in m.group(2).split(",")]
        xs = coords[0::2]
        ys = coords[1::2]
        regions.append({
            "page": page,
            "bbox": [min(xs), min(ys), max(xs), max(ys)],  # inches
        })
    return regions


def to_px(bbox_inch: list[float], scale: float) -> list[int]:
    """인치 좌표 → 픽셀 좌표 (72 points/inch × scale)"""
    dpi = 72.0 * scale
    return [int(v * dpi) for v in bbox_inch]


def safe_crop(pil_img: Image.Image, bbox_px: list[int]) -> Image.Image:
    x0, y0, x1, y1 = bbox_px
    w, h = pil_img.size
    return pil_img.crop((max(0, x0), max(0, y0), min(w, x1), min(h, y1)))


def collect_figures(data: dict) -> list[dict]:
    figures = []
    for content in data.get("result", {}).get("contents", []):
        for fig in content.get("figures", []):
            figures.append(fig)
        for page in content.get("pages", []):
            for fig in page.get("figures", []):
                figures.append(fig)
    return figures


def process_target(pdf_path: Path, out_dir: Path, label: str) -> None:
    raw_path = out_dir / "raw_response.json"
    if not raw_path.exists():
        print(f"  [건너뜀] {raw_path} 없음")
        return
    if not pdf_path.exists():
        print(f"  [건너뜀] {pdf_path} 없음")
        return

    data = json.loads(raw_path.read_text(encoding="utf-8"))
    figures = collect_figures(data)
    if not figures:
        print(f"  [건너뜀] figure 없음")
        return

    img_dir = out_dir / "img"
    img_dir.mkdir(exist_ok=True)

    doc = fitz.open(str(pdf_path))
    page_cache: dict[int, Image.Image] = {}

    saved, skipped = 0, 0
    fig_records = []

    for fig in figures:
        fig_id  = fig.get("id", "")
        source  = fig.get("source", "")
        caption = fig.get("caption") or ""
        if isinstance(caption, dict):
            caption = caption.get("content", "")

        if not source:
            skipped += 1
            continue

        regions = parse_source(source)
        if not regions:
            skipped += 1
            continue

        # figure는 단일 region이 대부분; 여러 region이면 첫 번째 사용
        r = regions[0]
        page_idx = r["page"] - 1  # 0-based
        if page_idx < 0 or page_idx >= len(doc):
            skipped += 1
            continue

        if page_idx not in page_cache:
            pix = doc[page_idx].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE))
            page_cache[page_idx] = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        pil_img  = page_cache[page_idx]
        bbox_px  = to_px(r["bbox"], SCALE)
        area = (bbox_px[2] - bbox_px[0]) * (bbox_px[3] - bbox_px[1])
        if area < MIN_AREA:
            skipped += 1
            continue

        cropped  = safe_crop(pil_img, bbox_px)
        safe_id  = fig_id.replace(".", "_")
        img_name = f"fig_{safe_id}.png"
        cropped.save(img_dir / img_name, format="PNG")
        saved += 1

        fig_records.append({
            "id":       fig_id,
            "page":     r["page"],
            "bbox_inch": r["bbox"],
            "caption":  caption,
            "img_path": f"img/{img_name}",
            "source":   source,
        })

    doc.close()

    # summary.json 덮어쓰기
    summary = {
        "total_figures": len(fig_records),
        "figures":       fig_records,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"  저장: {saved}개  건너뜀: {skipped}개  → {img_dir}")


def main():
    for t in TARGETS:
        print(f"\n[{t['label']}]")
        process_target(t["pdf"], t["out"], t["label"])
    print("\n완료")


if __name__ == "__main__":
    main()
