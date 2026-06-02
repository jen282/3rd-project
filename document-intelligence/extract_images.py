"""
PDF에서 이미지 영역을 크롭하고 4가지 정보를 파싱한다.
  - page      : 페이지 번호 (0-based)
  - bbox      : 픽셀 좌표 [x0, y0, x1, y1]
  - caption   : 이미지 근처 캡션 텍스트
  - type      : photo | diagram | chart | map | other
  - img_path  : 저장된 크롭 이미지 경로
  - source    : DocumentIntelligence | Vision

흐름:
  1. 페이지를 고해상도 PNG로 변환 → Document Intelligence prebuilt-layout
  2. figures 없으면 GPT-4o Vision fallback

사용법:
  python extract_images.py                          # 기본값 (국사교과서, result/)
  python extract_images.py --pdf 통계기초.pdf --result-dir result_digital
"""

import argparse
import base64
import io
import json
import os
import re
from pathlib import Path

import fitz  # PyMuPDF
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from openai import AzureOpenAI
from PIL import Image

# ── 설정 ─────────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

DI_ENDPOINT = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
DI_KEY      = os.environ["DOCUMENT_INTELLIGENCE_KEY"]
OAI_ENDPOINT = os.environ["OPEN_AI_ENDPOINT"].rstrip("/").removesuffix("/openai/v1")
OAI_KEY      = os.environ["OPEN_AI_KEY"]
OAI_DEPLOY   = os.environ["OPEN_AI_DEPLOYMENT_NAME"]

_parser = argparse.ArgumentParser()
_parser.add_argument("--pdf",        default="국사교과서.pdf")
_parser.add_argument("--result-dir", default="result")
_parser.add_argument("--max-pages",  type=int, default=15)
_args = _parser.parse_args()

PDF_PATH   = Path(__file__).parent.parent / "data" / _args.pdf
RESULT_DIR = Path(__file__).parent / _args.result_dir
IMG_DIR    = RESULT_DIR / "img"
JSON_PATH  = RESULT_DIR / "figures.json"

MAX_PAGES  = _args.max_pages
SCALE      = 2.0         # 렌더링 배율 (2x ≈ 144 dpi) — DI 50MB 제한 대응
MIN_AREA   = 50 * 50     # 너무 작은 영역 제외 (px²)

IMG_DIR.mkdir(parents=True, exist_ok=True)

# ── 클라이언트 ────────────────────────────────────────────────────────────────
di_client = DocumentIntelligenceClient(
    endpoint=DI_ENDPOINT,
    credential=AzureKeyCredential(DI_KEY),
)
oai_client = AzureOpenAI(
    azure_endpoint=OAI_ENDPOINT,
    api_key=OAI_KEY,
    api_version="2025-01-01-preview",
)


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def page_to_pil(page: fitz.Page, scale: float = SCALE) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def crop_and_save(img: Image.Image, bbox: list[int], path: Path) -> None:
    x0, y0, x1, y1 = bbox
    region = img.crop((x0, y0, x1, y1))
    region.save(path, format="PNG")


def polygon_to_bbox(polygon: list[float]) -> list[int]:
    """Document Intelligence polygon (픽셀 좌표 x,y 반복) → [x0, y0, x1, y1]"""
    xs = [polygon[i]     for i in range(0, len(polygon), 2)]
    ys = [polygon[i + 1] for i in range(0, len(polygon), 2)]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


# ── Document Intelligence 처리 ───────────────────────────────────────────────
def analyze_with_di(png_bytes: bytes) -> list[dict]:
    poller = di_client.begin_analyze_document(
        "prebuilt-layout",
        io.BytesIO(png_bytes),
        content_type="image/png",
    )
    result = poller.result()

    if not result.figures:
        return []

    records = []

    for fig in result.figures:
        region = fig.bounding_regions[0] if fig.bounding_regions else None
        if region is None or not region.polygon:
            continue

        bbox = polygon_to_bbox(region.polygon)
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if area < MIN_AREA:
            continue

        caption_text = ""
        if fig.caption and fig.caption.content:
            caption_text = fig.caption.content.strip()

        records.append({
            "bbox":    bbox,
            "caption": caption_text,
            "type":    "other",  # DI는 타입 미제공 → Vision fallback 없이 other
            "source":  "DocumentIntelligence",
        })

    return records


# ── GPT-4o Vision fallback ───────────────────────────────────────────────────
_VISION_PROMPT = """\
이 교과서 페이지에서 사진, 그림, 도표, 지도 등 이미지 영역을 모두 찾아주세요.
텍스트나 제목만 있는 영역은 제외합니다. 이미지 크기는 {w}x{h}픽셀입니다.

아래 JSON 배열로만 응답하세요 (설명 없이):
[{{"x0":int,"y0":int,"x1":int,"y1":int,"type":"photo|diagram|chart|map|other","caption":"근처 캡션 텍스트 (없으면 빈 문자열)"}}]
"""


def analyze_with_vision(pil_img: Image.Image) -> list[dict]:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    w, h = pil_img.size

    response = oai_client.chat.completions.create(
        model=OAI_DEPLOY,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text",      "text": _VISION_PROMPT.format(w=w, h=h)},
            ],
        }],
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()
    # 마크다운 코드블록 제거
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [Vision] JSON 파싱 실패: {raw[:120]}")
        return []

    if isinstance(items, dict):
        items = items.get("regions", items.get("figures", []))

    records = []
    for it in items:
        bbox = [int(it["x0"]), int(it["y0"]), int(it["x1"]), int(it["y1"])]
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if area < MIN_AREA:
            continue
        records.append({
            "bbox":    bbox,
            "caption": it.get("caption", "").strip(),
            "type":    it.get("type", "other"),
            "source":  "Vision",
        })
    return records


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    doc = fitz.open(str(PDF_PATH))
    total = min(MAX_PAGES, len(doc))
    print(f"PDF: {PDF_PATH.name}  |  처리 페이지: {total}")

    all_figures: list[dict] = []

    for page_num in range(total):
        page    = doc[page_num]
        pil_img = page_to_pil(page)
        w, h    = pil_img.size

        # PNG bytes for Document Intelligence
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        print(f"\n[page {page_num:02d}] {w}x{h}px", end="  ")

        records = analyze_with_di(png_bytes)

        if records:
            print(f"DI: {len(records)} figures")
        else:
            print("DI: 0 → Vision fallback")
            records = analyze_with_vision(pil_img)
            print(f"  Vision: {len(records)} figures")

        for idx, rec in enumerate(records):
            img_name = f"page{page_num:03d}_img{idx:02d}.png"
            img_path = IMG_DIR / img_name

            crop_and_save(pil_img, rec["bbox"], img_path)

            all_figures.append({
                "page":     page_num,
                "bbox":     rec["bbox"],
                "caption":  rec["caption"],
                "type":     rec["type"],
                "img_path": f"img/{img_name}",
                "source":   rec["source"],
            })

    doc.close()

    JSON_PATH.write_text(
        json.dumps(all_figures, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n완료: {len(all_figures)}개 이미지 저장 → {RESULT_DIR}")
    print(f"JSON: {JSON_PATH}")


if __name__ == "__main__":
    main()
