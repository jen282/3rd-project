# 스캔 PDF — 이미지 / 캡션 / bbox 추출 방법 정리

## 스캔 PDF의 구조적 문제

```
디지털 PDF          스캔 PDF
───────────         ───────────────────────────────
텍스트 레이어 ✅     텍스트 레이어 ❌
이미지 블록 ✅       페이지 전체 = 래스터 이미지 1장
bbox 메타데이터 ✅   bbox 메타데이터 ❌
```

→ pymupdf `get_text()`, `get_text("dict")`로는 텍스트·캡션·bbox 모두 빈값  
→ 별도 분석 레이어가 반드시 필요

---

## 1. 이미지 추출

### 방법 A — pymupdf 방안 1 (embedded raster 직접 추출)
```python
base_image = doc.extract_image(xref)
# → {"image": bytes, "ext": "jpeg", "width": int, "height": int}
```
- 국사교과서.pdf: 각 페이지에 1050×1500 JPEG 1장 + 헤더 이미지 1장
- **한계**: 페이지 전체가 이미지 1장이라 내부 사진·도표 영역을 구분 못 함

### 방법 B — pymupdf 방안 2 (페이지 재렌더링)
```python
pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 144dpi
pix.save(f"page_{page_num}.png")
```
- 원하는 해상도로 렌더링 → OCR·Vision 입력용으로 적합
- 내부 이미지 영역 분리는 다음 단계에서 처리

---

## 2. 이미지 캡션 추출

스캔 PDF에서 캡션은 이미지 근처에 인쇄된 텍스트 → OCR 없이는 접근 불가

### 방법 A — pymupdf + tesseract (현재 구현)
```python
pix.save(tmp_path)
text = pytesseract.image_to_string(tmp_path, lang="kor+eng")
```
- 페이지 전체 텍스트는 뽑히지만 어느 텍스트가 캡션인지 구분 어려움
- **국사교과서 실측**: 평균 85.3% 신뢰도, 페이지당 약 592자 추출

### 방법 B — tesseract 레이아웃 분석으로 캡션 후보 추출
```python
data = pytesseract.image_to_data(tmp_path, lang="kor+eng",
                                  output_type=pytesseract.Output.DICT)
# 각 단어별 left, top, width, height, conf, text 반환
# → 이미지 bbox 바로 아래/위 텍스트 블록 = 캡션 후보
```
- 텍스트 블록 위치(픽셀)를 알 수 있어 이미지 bbox와 거리 계산 가능
- **한계**: 이미지 영역 자체의 bbox는 직접 주지 않음 (텍스트 없는 영역으로 역추정)

### 방법 C — GPT-4o Vision (가장 정확)
```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": """
이 페이지에서 이미지(사진/도표/그림)를 찾고 각각의 캡션을 추출하세요.
JSON으로만 응답:
{"images": [{"caption": "캡션 텍스트", "position": "top|middle|bottom"}]}
"""}
        ]
    }],
    response_format={"type": "json_object"}
)
```
- 캡션 자동 인식 정확도 높음
- **한계**: 호출 비용 (페이지당 1회)

---

## 3. 이미지 bbox 추출

스캔 페이지 안에서 사진·도표 영역의 좌표를 찾는 것이 핵심 과제

### 방법 A — tesseract 역추정 (텍스트 없는 영역 = 이미지)
```python
data = pytesseract.image_to_data(tmp_path, ..., output_type=Output.DICT)

# 텍스트 블록들의 y범위를 수집
text_rows = set()
for i, text in enumerate(data["text"]):
    if text.strip():
        y, h = data["top"][i], data["height"][i]
        text_rows.update(range(y, y + h))

# 텍스트 없는 연속 행 → 이미지 영역으로 간주
```
- 추가 비용 없음
- **한계**: 부정확 (여백, 빈 줄도 이미지로 오인), 복잡한 레이아웃에서 신뢰도 낮음

### 방법 B — GPT-4o Vision bbox 요청
```python
{"type": "text", "text": """
이미지 영역의 bbox를 0~1 사이 상대좌표로 반환하세요.
{"images": [{"bbox": [x0, y0, x1, y1], "caption": "..."}]}
"""}
```
- Vision 모델이 레이아웃을 이해해 bbox 반환
- **한계**: 픽셀 정밀도 보장 안 됨, 상대좌표라 변환 필요

### 방법 C — Unstructured hi_res (detectron2 기반) ← 가장 정교
```python
from unstructured.partition.pdf import partition_pdf

elements = partition_pdf(
    filename="국사교과서.pdf",
    extract_images_in_pdf=True,
    extract_image_block_types=["Image", "Table"],
    strategy="hi_res",   # detectron2 레이아웃 분석
)
# element.metadata.coordinates → 정확한 bbox
```
- Image / Table / NarrativeText 자동 분류 + bbox 정확도 가장 높음
- **한계**: detectron2 등 무거운 의존성 (설치 난이도 ⭐⭐⭐⭐)

---

## 방법 비교

| 항목 | tesseract 역추정 | GPT-4o Vision | Unstructured hi_res |
|---|---|---|---|
| 이미지 추출 | △ (역추정) | ✅ | ✅ |
| 캡션 추출 | △ (후처리 필요) | ✅ | ✅ |
| bbox 정확도 | 낮음 | 중간 | **높음** |
| 추가 비용 | 없음 | 호출 비용 | 없음 |
| 설치 난이도 | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ |

---

## 권장 조합 (스캔 PDF 기준)

```
pymupdf 방안 2 (페이지 렌더링)
    +
GPT-4o Vision
  → 이미지 bbox + 캡션 동시 추출
  → GraphRAG 노드로 직접 변환
```

Unstructured hi_res는 로컬 환경 구축이 부담스러울 때 GPT-4o Vision으로 대체 가능.  
비용 최소화가 목표라면 tesseract 레이아웃 분석으로 후보를 좁힌 뒤 GPT-4o를 선별 호출하는 방식이 효율적.
