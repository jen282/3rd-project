# Document Intelligence Layout — 실험 정리

## 1. 실험 개요

Azure Document Intelligence(DI)의 `prebuilt-read`와 `prebuilt-layout` 모델로 두 가지 PDF를 분석하는 실험.
인풋 형태(PDF 직접 vs PNG 변환)와 모델 선택에 따라 추출 품질이 어떻게 달라지는지 비교한다.

---

## 2. 문서별 특성과 인풋 형태

### 통계기초.pdf

- **성격**: PPT를 PDF로 변환한 슬라이드형 디지털 PDF (48페이지)
- **핵심 문제**: 텍스트가 파워포인트 도형(shape) 안에 있어, PDF 내부에는 텍스트 레이어가 있으나 DI가 PDF 파싱 시 도형 컨테이너를 인식하지 못해 텍스트를 거의 추출하지 못함

| 실험 | 인풋 형태 | 스크립트 | 결과 폴더 |
|---|---|---|---|
| PDF 직접 → prebuilt-read | PDF bytes (`application/pdf`) | `extract_read.py` | `result_read/` |
| PDF 직접 → prebuilt-layout | PDF bytes (`application/pdf`) | `extract_layout.py` | `result_layout/` |
| PNG 변환 → prebuilt-layout | 페이지별 PNG bytes (`image/png`) | `extract_png.py` | `result_png/` |

### 국사교과서.pdf (역사교과서)

- **파일명**: `국사교과서.pdf`
- **성격**: 실물 책을 스캔한 이미지 기반 PDF — PDF 내부에 텍스트 레이어 없음, 순수 이미지
- **인풋 형태**: 페이지별 PNG 변환 후 DI에 이미지(`image/png`)로 전송
- **스크립트**: `extract_png.py --pdf 국사교과서.pdf --model prebuilt-layout`
- **결과 폴더**: `result_scan/`

스캔 PDF는 PDF 직접 전송을 시도하지 않았음 — 이미 이미지이므로 PNG 변환 방식이 유일한 선택지.

---

## 3. 스크립트별 처리 흐름

### 3-1. `extract_read.py` → `result_read/`

```
통계기초.pdf
  └─ read_bytes() → PDF binary
       └─ begin_analyze_document("prebuilt-read", bytes, content_type="application/pdf")
            └─ AnalyzeResult 객체
                 ├─ result.content          → content.txt
                 └─ parse_result()로 가공   → read.json, text_result.txt
```

**코드가 하는 일**
1. PDF 전체를 binary로 읽어 DI에 한 번에 전송
2. `prebuilt-read` 모델 호출 — 텍스트 추출 전용 (표/그림 위치는 무시)
3. `parse_result(result)`: `result.pages`를 순회하며 각 페이지의 `page.lines`와 `result.paragraphs`를 파이썬 dict로 정리
4. 좌표는 `result.pages[n].width` 기준 **인치(inch)** 단위 — `bbox_in` 키로 저장

**결과**: 1페이지 6줄, 2페이지 5줄 — 도형 텍스트 대부분 누락

---

### 3-2. `extract_layout.py` → `result_layout/`

```
통계기초.pdf
  └─ read_bytes() → PDF binary
       └─ begin_analyze_document("prebuilt-layout", bytes, content_type="application/pdf")
            └─ AnalyzeResult 객체
                 ├─ result.content                → content.txt
                 ├─ parse_result() 표/그림 포함   → layout.json, text_result.txt
                 └─ fitz(PyMuPDF)로 그림 크롭     → result_layout/figures/img/*.png
```

**코드가 하는 일**
1. PDF 전체를 binary로 읽어 DI에 한 번에 전송
2. `prebuilt-layout` 모델 호출 — 텍스트 + 표 구조 + 그림 위치까지 추출
3. `parse_result(result, doc)`:
   - `result.paragraphs` → 각 단락의 role(title/body/pageFooter 등)과 content, bbox 추출
   - `result.tables` → 셀 단위로 2D 그리드 재구성, table_NNN.json으로도 개별 저장
   - `result.figures` → bbox 좌표로 PyMuPDF(fitz)를 통해 PDF에서 직접 크롭
4. 좌표는 **인치** 단위 (`bbox_in`), DI가 PDF 페이지 크기(인치)를 기준으로 반환

**결과**: 도형 텍스트 여전히 누락 — prebuilt-layout도 PDF 파싱 기반이라 동일 문제

---

### 3-3. `extract_png.py` → `result_png/` (통계기초, PNG 변환)

```
통계기초.pdf
  └─ fitz.open() → 페이지별 렌더링 (2.0x = 144dpi)
       └─ PIL Image (RGB) → PNG bytes (in-memory)
            └─ begin_analyze_document("prebuilt-layout", png_bytes, content_type="image/png")
                 └─ AnalyzeResult 객체 (1페이지짜리)
                      ├─ result.pages[0].lines
                      ├─ result.paragraphs
                      └─ result.figures → PIL로 bbox 크롭 → figures/pageNNN_imgNN.png
```

**코드가 하는 일**
1. PyMuPDF(fitz)로 PDF 페이지를 PNG 이미지로 렌더링 (기본 144dpi, `--scale 3.0`으로 216dpi 가능)
2. 페이지마다 개별 DI API 호출 — 1장씩 이미지로 전송하므로 응답도 1페이지짜리 결과
3. `analyze_page(png_bytes)`:
   - `result.pages[0].lines` → lines 목록
   - `result.paragraphs` → 단락 목록
   - `result.figures` → bbox (픽셀 좌표), MIN_AREA(50×50px) 미만 필터링
4. figure 크롭은 PIL(`Image.crop`)으로 PNG 이미지에서 bbox 잘라내기 — PDF 렌더링 이미지 기준이므로 좌표가 **픽셀**
5. 전체 페이지 결과를 모아 파일 저장

**결과**: 48페이지, 730라인, 600단락, 14페이지에서 그림 18장 — 도형 텍스트까지 전부 추출 성공

---

### 3-4. `extract_png.py` → `result_scan/` (국사교과서, 스캔 PDF)

```
국사교과서.pdf
  └─ fitz.open() → 페이지별 렌더링 (2.0x = 144dpi)
       └─ PNG bytes → begin_analyze_document("prebuilt-layout", png_bytes, "image/png")
            └─ AnalyzeResult 객체 (1페이지짜리)
                 ├─ result.pages[0].lines (OCR 결과)
                 ├─ result.paragraphs
                 └─ result.figures → PIL 크롭 → figures/pageNNN_imgNN.png
```

`extract_png.py`를 동일하게 사용하되 `--pdf 국사교과서.pdf --model prebuilt-layout`으로 실행.
스캔 이미지를 DI에 보내면 DI가 OCR을 수행하여 텍스트를 인식한다.

**통계기초 PNG 방식과 차이점**
- 통계기초: 디지털 PDF에 텍스트 레이어가 있으나 도형 안에 있어 DI가 PDF 파싱으로 못 읽음 → PNG로 변환해 OCR 강제
- 국사교과서: 애초에 이미지 스캔이므로 텍스트 레이어 자체가 없음 → PNG 변환 후 OCR이 유일한 방법

---

## 4. API 응답 구조

DI API는 `poller.result()`로 `AnalyzeResult` 파이썬 객체를 반환한다. 이 객체를 직접 JSON으로 직렬화하는 것은 불가능 — `json.dumps()`가 SDK 전용 타입을 처리하지 못함.

### AnalyzeResult 주요 필드

```
AnalyzeResult
├── content: str                     # 전체 텍스트, 읽기 순서로 합친 단일 문자열
├── pages: list[DocumentPage]
│    └── DocumentPage
│         ├── page_number: int       # 1-based
│         ├── width: float           # 인치 (PDF 입력 시) 또는 픽셀 (이미지 입력 시)
│         ├── height: float
│         └── lines: list[DocumentLine]
│              └── DocumentLine
│                   ├── content: str  # 한 줄 텍스트
│                   └── polygon: list[float]  # [x0,y0, x1,y1, x2,y2, x3,y3]
├── paragraphs: list[DocumentParagraph]
│    └── DocumentParagraph
│         ├── role: str | None       # "title", "pageFooter", "body" 등
│         ├── content: str
│         └── bounding_regions: list[BoundingRegion]
│              └── BoundingRegion
│                   ├── page_number: int
│                   └── polygon: list[float]
├── tables: list[DocumentTable]      # prebuilt-layout만 반환
│    └── DocumentTable
│         ├── row_count, column_count: int
│         └── cells: list[DocumentTableCell]
│              └── DocumentTableCell
│                   ├── row_index, column_index: int
│                   └── content: str
└── figures: list[DocumentFigure]    # prebuilt-layout만 반환
     └── DocumentFigure
          ├── caption: DocumentCaption | None
          └── bounding_regions: list[BoundingRegion]
```

### 좌표계 차이

| 인풋 형태 | 좌표 단위 | 저장 키 이름 |
|---|---|---|
| PDF binary (`application/pdf`) | 인치(inch) — PDF 페이지 크기 기준 | `bbox_in` |
| PNG image (`image/png`) | 픽셀(px) — PNG 이미지 크기 기준 | `bbox` |

polygon은 `[x0, y0, x1, y1, x2, y2, x3, y3]` 형태의 8개 값(사각형 4꼭짓점). 코드에서는 `polygon_to_bbox_inches()` / `polygon_to_bbox_px()`로 `[x_min, y_min, x_max, y_max]` 형태로 변환.

---

## 5. 응답 가공 방식

SDK 객체에서 필요한 필드만 직접 꺼내 파이썬 dict로 재구성한 뒤 저장한다. SDK 객체 전체를 JSON으로 덤프하는 게 아니라 수동으로 직렬화 가능한 구조로 변환하는 것.

### extract_read.py의 parse_result()

```python
# SDK 객체 → dict 변환 요약
for page in result.pages:
    lines = [{"content": line.content, "bbox_in": polygon_to_bbox(line.polygon)}
             for line in page.lines]
    paragraphs = [{"role": para.role, "content": para.content, "bbox_in": ...}
                  for para in result.paragraphs if para.bounding_regions.page == page]

pages_data = [{"page": pn, "width_in": ..., "height_in": ..., "lines": lines, "paragraphs": paragraphs}]
```

### extract_layout.py의 parse_result()

```python
# 단락 + 표 + 그림 포함
for para in result.paragraphs:   → {"role", "content", "bbox_in"}
for table in result.tables:      → 2D grid {"data": [[cell, ...], ...], "rows", "cols"}
for fig in result.figures:       → {"img_path", "caption", "bbox_in"} + PyMuPDF 크롭
```

### extract_png.py의 analyze_page()

```python
# 페이지 1장씩 처리
lines      = [{"content", "bbox"}  for line in result.pages[0].lines]
paragraphs = [{"role", "content"}  for para in result.paragraphs]
figures    = [{"bbox", "caption"}  for fig  in result.figures if area >= MIN_AREA]
# 반환값: {"lines", "paragraphs", "figures", "content"}
```

---

## 6. result 파일별 의미

### `result_read/` — 통계기초 PDF 직접, prebuilt-read

| 파일 | 내용 | 출처 |
|---|---|---|
| `read.json` | 페이지별 lines + paragraphs (bbox_in 인치 단위) | `parse_result()` → `json.dumps()` |
| `content.txt` | DI가 읽기 순서로 합친 전체 텍스트 원본 | `result.content` 그대로 저장 |
| `text_result.txt` | `[page N] lines=X paragraphs=Y` 헤더 + 라인 목록 | `build_text_result()` 포맷팅 |

도형 텍스트 누락으로 페이지당 5~11줄 수준 — 슬라이드 본문 대부분 빠짐.

---

### `result_layout/` — 통계기초 PDF 직접, prebuilt-layout

| 파일 | 내용 | 출처 |
|---|---|---|
| `layout.json` | 페이지별 paragraphs + tables + figures (bbox_in 인치) | `parse_result()` → `json.dumps()` |
| `content.txt` | DI 원본 전체 텍스트 | `result.content` 그대로 저장 |
| `text_result.txt` | `[role] content` + 표를 `|`로 그린 그리드 + 그림 경로 | 포맷팅 |
| `tables/table_NNN.json` | 개별 표를 JSON으로 별도 저장 | — |
| `figures/img/*.png` | 그림 위치를 PyMuPDF로 PDF에서 크롭 | `crop_and_save(fitz)` |

도형 텍스트 누락 동일 — prebuilt-layout도 PDF 파싱 기반이므로 같은 문제.
단, 단락 role(title/pageFooter 등) 정보가 추가로 붙음.

---

### `result_png/` — 통계기초 PDF → PNG, prebuilt-layout

| 파일 | 내용 | 출처 |
|---|---|---|
| `read.json` | 페이지별 lines + paragraphs + figures (bbox 픽셀 단위) | `pages_data` → `json.dumps()` |
| `content.txt` | 페이지 구분자(`--- page N ---`) 포함 전체 텍스트 | `result.content` 페이지별 합산 |
| `text_result.txt` | 라인 목록 + 그림 경로 포맷팅 | 포맷팅 |
| `clean_text.txt` | 페이지 구분자만 있고 단락 내용 그대로 (content.txt와 유사) | — |
| `figures/pageNNN_imgNN.png` | DI가 감지한 figure bbox를 PNG 이미지에서 PIL로 크롭 | `Image.crop()` |

**가장 많이 추출**: 48페이지, 730라인, 600단락, 그림 18장.
bbox가 픽셀 단위인 이유: PNG 이미지를 보낸 경우 DI는 이미지 픽셀 좌표로 응답.

---

### `result_scan/` — 국사교과서 PDF → PNG, prebuilt-layout

| 파일 | 내용 | 출처 |
|---|---|---|
| `read.json` | 페이지별 lines + paragraphs + figures (bbox 픽셀 단위) | `pages_data` → `json.dumps()` |
| `content.txt` | 페이지 구분자 포함 OCR 결과 텍스트 | `result.content` 페이지별 합산 |
| `text_result.txt` | 라인 목록 + 그림 경로 포맷팅 | 포맷팅 |
| `figures/pageNNN_imgNN.png` | 사진/도표 등 figure 크롭 이미지 | `Image.crop()` |

스캔 이미지 OCR이므로 페이지당 lines/paragraphs가 통계기초 PNG보다 많음(페이지 1에서만 lines=11, para=8).
교과서 특성상 그림(figures)이 페이지마다 2~4개씩 다수 포함.

---

## 7. 핵심 발견 — 도형 텍스트 문제

```
PDF 직접 전송: DI가 PDF 텍스트 레이어를 파싱
  → PPT 도형(shape) 안의 텍스트는 레이어에 있어도 DI가 도형 컨테이너를 무시
  → 슬라이드 본문의 95% 이상 누락

PNG 변환 후 전송: DI가 이미지 전체를 OCR 처리
  → 도형/배경 구분 없이 화면에 보이는 텍스트를 모두 인식
  → 누락 없음
```

| 방식 | 2페이지 라인 수 | 비고 |
|---|---|---|
| PDF → prebuilt-layout | 5줄 | 도형 텍스트 누락 |
| PDF → prebuilt-read | 11줄 | 도형 텍스트 누락 |
| PNG → prebuilt-layout | 730줄 (48페이지 합계) | 해결됨 |

결론: 슬라이드형 디지털 PDF나 스캔 PDF 모두 **PNG 변환 → DI 이미지 입력** 방식이 필요.
디지털 PDF에서 텍스트 레이어가 도형 밖에 있는 경우에만 PDF 직접 전송이 유효하다.
