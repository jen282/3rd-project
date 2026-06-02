# 스캔 PDF 이미지 크롭 — Document Intelligence 전체 페이지 인식 문제 해결

## 원인

스캔 PDF는 페이지 구조가 아래와 같다.

```
페이지
├── 이미지 객체 (전체 크기 1050×1500)  ← 배경 스캔본
└── 이미지 객체 (838×188)              ← 헤더
```

텍스트 레이어가 없고 이미지 객체 하나가 페이지 전체를 덮고 있으면,
Document Intelligence는 레이아웃 분석 대상이 아니라 **"이미지 페이지"** 로 분류한다.
내부의 사진/도표/텍스트를 구분할 근거가 없기 때문이다.

---

## 해결 방법

| 방법                                     | 원리                                                    | 적합도       |
| ---------------------------------------- | ------------------------------------------------------- | ------------ |
| ① `ocrHighResolution` 강제               | Document Intelligence에 OCR 모드 명시                   | ✅ 가장 간단 |
| ② 페이지를 고해상도 PNG로 변환 후 재입력 | PDF가 아닌 이미지로 넣으면 레이아웃 분석 적용           | ✅ 확실      |
| ③ GPT-4o Vision fallback                 | Document Intelligence가 실패한 페이지만 Vision으로 처리 | ✅ 현실적    |

---

## ① OCR 강제

가장 먼저 시도한다.

```python
poller = client.begin_analyze_document(
    "prebuilt-layout",
    analyze_request=f,
    content_type="application/octet-stream",
    features=["ocrHighResolution"]  # 추가
)
```

---

## ② PDF → PNG 변환 후 재입력

PDF 전체가 아니라 **페이지 단위 PNG** 로 넣으면 "전체가 이미지"라는 오인을 피할 수 있다.

```python
import fitz
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

client = DocumentIntelligenceClient(
    endpoint="YOUR_ENDPOINT",
    credential=AzureKeyCredential("YOUR_KEY")
)

doc = fitz.open("sample.pdf")
for page_num, page in enumerate(doc):
    # 고해상도 렌더링 (3x = 216dpi)
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
    png_bytes = pix.tobytes("png")

    # PNG로 Document Intelligence 호출
    poller = client.begin_analyze_document(
        "prebuilt-layout",
        analyze_request=png_bytes,
        content_type="image/png"
    )
    result = poller.result()

    for fig in result.figures:
        print(f"[page {page_num}] bbox: {fig.bounding_regions}")
        print(f"  caption: {fig.caption}")
```

---

## ③ GPT-4o Vision Fallback

Document Intelligence가 `figures`를 못 잡은 페이지만 Vision으로 처리한다.
비용을 최소화하면서 커버리지를 확보하는 현실적인 구조다.

```python
import base64
import json
import io
from PIL import Image

def detect_with_vision(page_img: Image.Image, page_num: int) -> list[dict]:
    buf = io.BytesIO()
    page_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    w, h = page_img.size

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": f"""이 페이지에서 사진, 그림, 도표, 지도 등 이미지 영역을 모두 찾아주세요.
텍스트나 제목은 제외합니다. 이미지 크기는 {w}x{h}픽셀입니다.

아래 JSON 배열로만 응답하세요:
[{{"x0": int, "y0": int, "x1": int, "y1": int, "type": "photo|diagram|chart|map|other", "caption": "근처 캡션 텍스트"}}]
"""}
            ]
        }],
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content)
    return result if isinstance(result, list) else result.get("regions", [])


def extract_figures(page_num: int, doc_intel_result, page_img: Image.Image) -> list[dict]:
    """Document Intelligence 실패 시 Vision으로 fallback"""
    if not doc_intel_result.figures:
        print(f"[page {page_num}] figures 없음 → Vision fallback")
        return detect_with_vision(page_img, page_num)

    return [
        {
            "page": page_num,
            "bbox": fig.bounding_regions,
            "caption": fig.caption,
        }
        for fig in doc_intel_result.figures
    ]
```

---

## 권장 순서

```
② PNG 변환 재입력 먼저 테스트
    └─ 그래도 figures 없는 페이지
           └─ ③ GPT-4o Vision fallback
                  └─ ① ocrHighResolution은 비용 증가하므로 마지막 수단
```

---

## 출력 메타데이터 구조 (GraphRAG 입력용)

```json
{
  "page": 0,
  "bbox": [x0, y0, x1, y1],
  "caption": "그림 3. 조선시대 신분제도",
  "type": "diagram",
  "img_path": "page000_img00.png",
  "source": "Vision | DocumentIntelligence"
}
```

`page` + `bbox` 를 키로 개념 추출 담당자의 텍스트 노드와 조인한다.
