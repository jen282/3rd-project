# PDF 이미지 추출 실험 요약

## 최종 목표

PDF 문서에서 이미지(차트·도표·사진)를 추출하고, 각 이미지를 **GraphRAG 노드**로 변환한다.  
GraphRAG 노드에는 이미지 bytes, 위치(bbox), 주변 텍스트(surrounding_text), 개념·관계 정보가 포함된다.

---

## 1. 실험한 내용

### 테스트 PDF

| PDF              | 종류       | 페이지   | 특징                                       |
| ---------------- | ---------- | -------- | ------------------------------------------ |
| `국사교과서.pdf` | 스캔 PDF   | 50페이지 | 텍스트 레이어 없음. 각 페이지 = 이미지 1장 |
| `통계기초.pdf`   | 디지털 PDF | 48페이지 | 텍스트 레이어 있음. 차트·그래프 포함       |

### 실험 목록

| #   | 실험                                                             | 위치                     | 대상 PDF                      |
| --- | ---------------------------------------------------------------- | ------------------------ | ----------------------------- |
| 1   | PyMuPDF 방안 1: 래스터 이미지 직접 추출                          | `pymupdf/approach1/`     | 국사교과서, 통계기초          |
| 2   | PyMuPDF 방안 2: 페이지 전체 렌더링                               | `pymupdf/approach2/`     | 국사교과서, 통계기초          |
| 3   | PyMuPDF 방안 3: 이미지 블록 크롭 + 메타데이터                    | `pymupdf/approach3/`     | 국사교과서, 통계기초          |
| 4   | PyMuPDF + GPT-4o Vision: 이미지 → GraphRAG 노드                  | `pymupdf/gpt/`           | 통계기초 (방안 3 결과물 사용) |
| 5   | Document Intelligence + GPT-4o Vision Fallback: 이미지 영역 감지 | `document-intelligence/` | 국사교과서, 통계기초          |
| 6   | Docling: 구조 분석 기반 figure + 표 추출                         | `docling/`               | 통계기초                      |
| 7   | pdfplumber: 벡터 path 분석으로 표 + 벡터 이미지 추출            | `pdfplumber/`            | 통계기초                      |

---

## 2. 실험 방법

### 방안 1 — 래스터 이미지 직접 추출

PDF 내부에 embedded된 래스터 이미지 객체를 xref 기반으로 직접 추출한다.

```python
for xref in doc.get_page_images(page_num):
    base_image = doc.extract_image(xref)
    # → {"image": bytes, "ext": "jpeg", "width": int, "height": int}
```

- bbox 정보 없음
- 벡터 다이어그램(선으로 그린 도형) 추출 불가

### 방안 2 — 페이지 전체 렌더링

각 페이지를 지정 배율로 픽셀 이미지로 렌더링한다.

```python
pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x = 144 dpi
pix.save(f"page_{page_num}.png")
```

- 벡터 선·텍스트 오버레이까지 포함된 완전한 시각 정보 확보
- 어떤 영역이 이미지인지 구분 정보 없음

### 방안 3 — 이미지 블록 크롭 + 메타데이터

PyMuPDF의 `get_text("dict")`로 페이지 블록을 파싱하여 이미지 블록(`type==1`)을 감지하고,  
2x 렌더링 이미지에서 해당 bbox를 크롭한다. 동시에 주변 텍스트 블록을 수집하여 `surrounding_text`로 저장한다.

```
get_text("dict") → 블록 목록
  ├─ type==0 (텍스트 블록) → surrounding_text 수집
  └─ type==1 (이미지 블록) → bbox 기록 + 페이지 렌더링 이미지에서 크롭
```

- bbox + surrounding_text를 함께 획득 → GraphRAG 노드 연결 기반 확보
- 텍스트 레이어 없는 스캔 PDF에서는 surrounding_text가 빈 문자열
- **크롭 기준: PDF 구조(메타데이터)** — PDF가 "여기에 이미지가 있다"고 명시한 래스터 이미지 블록만 감지. 벡터로 그린 차트·도형은 블록으로 등록되지 않아 감지 불가. 대신 좌표가 PDF 메타데이터에서 직접 나오므로 bbox 정밀도 높음

### 방안 4 — GPT-4o Vision → GraphRAG 노드 변환

방안 3의 출력(`report.json` + 크롭 이미지)을 입력으로 받아,  
GPT-4o Vision에 이미지와 surrounding_text를 함께 전달하여 GraphRAG 노드 정보를 추출한다.

```
report.json (crop 목록)
    ↓
이미지 base64 인코딩
    ↓
GPT-4o Vision 호출 (이미지 + surrounding_text)
    ↓
JSON 응답: { concept, description, relations, type }
    ↓
GraphRAG 노드 저장 (source: page, bbox 포함)
```

- Azure OpenAI(`gpt-4o`) 사용
- `response_format: json_object`로 구조화 출력 강제

### 방안 5 — Document Intelligence + GPT-4o Vision Fallback

스캔 PDF 페이지를 고해상도 PNG로 변환 후 Azure Document Intelligence(`prebuilt-layout`)로 분석한다.  
`figures` 검출에 실패한 페이지만 GPT-4o Vision으로 재분석(fallback)한다.

```
페이지 PNG
    ↓
Document Intelligence prebuilt-layout
    ├─ figures 있음 → bbox·캡션 추출
    └─ figures 없음 → GPT-4o Vision fallback → bbox·캡션·type 추출
```

- DI: bbox·캡션 제공, 이미지 타입 미제공 (`type = "other"` 고정)
- GPT: bbox·캡션·타입 동시 제공 (`photo`, `diagram`, `chart`, `map`, `other`)
- **크롭 기준: 시각적 레이아웃 분석** — 렌더링된 페이지 이미지를 AI로 분석해 figure처럼 보이는 영역을 감지. 래스터·벡터 구분 없이 감지 가능하나 AI 판단이므로 bbox 정밀도는 방안 3보다 낮음

---

## 3. 실험 단계 (파이프라인)

### 디지털 PDF 파이프라인

```
디지털 PDF
    │
    ├─ [방안 3] PyMuPDF 블록 크롭
    │       → 크롭 이미지 + bbox + surrounding_text
    │       → report.json
    │
    └─ [방안 4] GPT-4o Vision
            → { concept, description, relations, type }
            → GraphRAG 노드 (graph_nodes.json)
```

### 스캔 PDF 파이프라인 (Document Intelligence 활용)

```
스캔 PDF
    │
    ├─ [방안 2] PyMuPDF 페이지 렌더링 (2x PNG)
    │
    └─ [방안 5] Document Intelligence + GPT-4o Vision Fallback
            → figures.json (page, bbox, caption, type, img_path, source)
```

### GraphRAG 최종 노드 구조

```json
{
  "concept": "정규분포",
  "description": "평균을 중심으로 좌우 대칭인 종 모양 확률분포",
  "relations": [{ "relation": "포함", "target": "68-95-99.7 규칙" }],
  "type": "diagram",
  "source": {
    "page": 17,
    "bbox": [140.2, 334.1, 770.6, 540.0],
    "image_path": "approach3/result_digital/page017_block00.png"
  }
}
```

---

## 4. 실험 결과 요약

### PyMuPDF 방안 1·2·3 수치 비교

| 방안             | 국사교과서(스캔) 추출 수 | 통계기초(디지털) 추출 수 | 소요 시간(국사) | 소요 시간(통계) |
| ---------------- | ------------------------ | ------------------------ | --------------- | --------------- |
| 1. 래스터 추출   | 100개 JPEG               | 14개 JPEG/PNG            | **0.037초**     | 0.05초          |
| 2. 페이지 렌더링 | 50개 PNG (1191×1684)     | 48개 PNG (1920×1080)     | 8.727초         | 2.987초         |
| 3. 블록 크롭     | 100개 PNG                | 14개 PNG                 | 7.437초         | 0.636초         |

### 방안 5 (Document Intelligence + Vision Fallback) 수치 비교

| 항목                 | 국사교과서 (스캔) |   통계기초 (디지털)   |
| -------------------- | :---------------: | :-------------------: |
| 총 추출 이미지       |         —         |       **23개**        |
| DI 단독 감지         |         —         |    14개 (13페이지)    |
| Vision fallback 감지 |         —         |     9개 (7페이지)     |
| DI 실패율            |         —         | **73%** (35/48페이지) |
| 캡션 추출 (DI)       |         —         |    0개 (모두 `""`)    |
| 캡션 생성 (Vision)   |         —         |          6개          |
| type 분류 (DI)       |         —         |     모두 `other`      |
| type 분류 (Vision)   |         —         |     모두 `chart`      |

> 국사교과서는 result/ 폴더에 결과 있음 (스캔 PDF라 DI가 헤더·배경 이미지 위주 감지)

### PDF 유형별 방안 3 surrounding_text 확보율

| PDF               | surrounding_text 확보율 | 원인               |
| ----------------- | ----------------------- | ------------------ |
| 국사교과서 (스캔) | **0%**                  | 텍스트 레이어 없음 |
| 통계기초 (디지털) | **100%** (14/14)        | 텍스트 레이어 있음 |

### 방안별 기능 비교

| 항목               | 방안 1 | 방안 2 | 방안 3 |  방안 4   |    방안 5    |
| ------------------ | :----: | :----: | :----: | :-------: | :----------: |
| 이미지 bytes       |   ✅   |   ✅   |   ✅   | ✅ (입력) |      ✅      |
| 이미지 bbox        |   ❌   |   ❌   |   ✅   |    ✅     |      ✅      |
| 캡션/개념          |   ❌   |   ❌   |   ❌   |    ✅     | △ (Vision만) |
| surrounding_text   |   ❌   |   ❌   |   ✅   | ✅ (활용) |      ❌      |
| 텍스트-이미지 연결 |   ❌   |   ❌   |   △    |    ✅     |      △       |
| 벡터 차트 감지     |   ❌   |   ✅   |   ❌   |    ❌     | ✅ (Vision)  |
| 스캔 PDF 대응      |   △    |   ✅   |   △    |     △     |      ✅      |
| 비용               |  무료  |  무료  |  무료  |   유료    |     유료     |

### 주요 발견 사항

1. **스캔 PDF의 구조적 한계**: 국사교과서는 각 페이지가 이미지 1장으로 구성되어 방안 1·3 모두 페이지 전체를 이미지로 추출함. 내부 사진·도표 구분 불가.

2. **방안 3의 강점은 디지털 PDF에서만 발휘**: `surrounding_text` 확보율이 디지털 PDF에서 100%였으나 스캔 PDF에서는 0%.

3. **Document Intelligence 단독으로 스캔 PDF figures 검출 실패 가능**: 페이지 전체가 이미지인 경우 레이아웃 분석이 동작하지 않아 GPT-4o Vision fallback이 현실적 보완책.

4. **방안 5는 디지털 슬라이드 PDF에서 커버리지 우수하나 최적은 아님**: 통계기초.pdf 기준 23개 감지(방안 3의 14개 대비 9개 추가). 추가 9개는 벡터 기반 차트로 방안 3이 놓친 영역. 단, DI 실패율 73%로 Vision fallback 의존도가 높고, 캡션·타입은 Vision 경로에서만 부분 제공됨.

5. **방안 3 vs 방안 5 (통계기초 기준)**:
   - 방안 3: 14개, surrounding_text 100%, 캡션 없음, 래스터 이미지만 감지
   - 방안 5: 23개, surrounding_text 없음, 캡션 일부 생성, 벡터 차트까지 감지

6. **권장 파이프라인**:
   - 디지털 PDF → **방안 3 + 방안 4** (surrounding_text 활용 GraphRAG 노드 변환)
   - 스캔 PDF → **방안 5** (Document Intelligence + GPT-4o Vision Fallback)

### 방안 6 (Docling) 수치 비교 — 통계기초.pdf

| 항목 | 값 |
|------|-----|
| 총 추출 figure | **15개** (모두 저장) |
| 총 감지 표 | **9개** (별도 JSON) |
| surrounding_text 확보 | **10/15 (67%)** |
| 캡션 | 0개 |
| 소요 시간 | 43.51초 (OCR OFF) |
| OCR 엔진 | 기본 (EasyOCR 기반) |

> 국사교과서(스캔) 테스트 미완료 — OCR 속도 문제로 진행 중

**방안 3 / 방안 5 / 방안 6 비교 (통계기초 기준)**

| 항목 | 방안 3 (PyMuPDF) | 방안 5 (DI+Vision) | 방안 6 (Docling) |
|------|:---------------:|:-----------------:|:---------------:|
| 총 figure 수 | 14개 | **23개** | 15개 |
| 표 감지 | ❌ | ❌ | ✅ 9개 |
| surrounding_text | ✅ 100% | ❌ | △ 67% |
| 캡션 | ❌ | △ (6개, Vision만) | ❌ |
| 벡터 차트 감지 | ❌ | ✅ | △ (일부) |
| 비용 | 무료 | 유료 | 무료 |
| 소요 시간 | 0.636초 | — | 43.51초 |

**주요 관찰:**
- figure 커버리지는 DI+Vision(23개) > Docling(15개) > 방안 3(14개)
- surrounding_text는 방안 3(100%) > Docling(67%) > DI+Vision(없음)
- Docling만 표를 figure와 분리해서 별도 감지
- bbox 좌표계가 PDF 원점(좌하단) 기준이라 y값이 반전됨 — 크롭 시 변환 필요
- OCR 없이도 디지털 PDF는 처리 가능하나 속도는 방안 3 대비 68배 느림

### 비용 추정 (통계기초.pdf 기준, 방안 4)

- 크롭 이미지 14개 × GPT-4o Vision 1회 = 14회 호출
- 이미지 토큰: 약 85~340 토큰/장
- 텍스트 토큰: 약 200~300 토큰/호출
- 총 예상: **약 5,000~7,000 토큰 (수 센트 수준)**

## 5. 요소 판별 전략

### 판별 흐름

```
PDF 페이지
├── 스캔 판별 (텍스트 < 50자 + 이미지 존재)
│   └── 스캔 PDF → OCR + 비전 LLM으로 전체 처리
│
└── 디지털 PDF
    ├── 텍스트 블록 → 직접 추출
    ├── 벡터 path 존재?
    │   ├── pdfplumber 표 추출 성공 → 표
    │   └── 실패 → 다이어그램 → 비전 LLM 캡션 생성
    └── 래스터 이미지 존재?
        └── 비전 LLM으로 분류 (표/다이어그램/사진)
```

### 요소별 처리 전략 요약

| 상황            | 표                     | 다이어그램         | 이미지(사진)       |
| --------------- | ---------------------- | ------------------ | ------------------ |
| 디지털 + 벡터   | pdfplumber로 구조 추출 | 비전 LLM 캡션 생성 | 비전 LLM 캡션 생성 |
| 디지털 + 래스터 | 비전 LLM 분류 후 추출  | 비전 LLM 캡션 생성 | 비전 LLM 캡션 생성 |
| 스캔            | OCR + 비전 LLM         | 비전 LLM 캡션 생성 | 비전 LLM 캡션 생성 |

### 핵심 포인트

- **벡터 기반 표만** pdfplumber로 구조적 추출 가능
- 나머지 모든 경우는 **비전 LLM 투입** 필요
- 스캔 PDF는 **OCR이 전처리의 전부**

---

## 4. 사용 도구 정리

| 도구                         | 용도                                    |
| ---------------------------- | --------------------------------------- |
| `pymupdf (fitz)`             | 텍스트/이미지/벡터 path 추출, 스캔 판별 |
| `pdfplumber`                 | 벡터 기반 표 구조 추출                  |
| `tesseract` / `easyocr`      | 스캔 PDF OCR 처리                       |
| 비전 LLM (Claude, GPT-4o 등) | 래스터 이미지 분류 및 캡션 생성         |
