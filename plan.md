# 통합 이미지 추출 파이프라인 구현 계획

---

## Plan A — Document Intelligence Layout (주 방안)

### 핵심 전략

**모든 PDF를 페이지별 PNG로 변환한 뒤 DI `prebuilt-layout`에 전송한다.**

실험 결과, PDF 직접 전송 시 PPT 슬라이드처럼 도형(shape) 안에 텍스트가 있는 디지털 PDF는 DI가 2페이지에서 5~11줄밖에 추출하지 못한다. PNG로 변환하면 같은 48페이지에서 730줄을 정상 추출한다. 스캔 PDF도 동일한 PNG 경로를 사용하므로 분기 없이 단일 파이프라인으로 처리한다.

```
PDF 파일
    ↓
페이지별 PNG 렌더링 (PyMuPDF, scale=2.0 → 144dpi)
    ↓
DI prebuilt-layout 전송 (페이지당 1회 API 호출)
    ↓
lines / paragraphs / figures 수신
    ↓
figure bbox로 PIL 이미지에서 크롭 → PNG 저장
    ↓
read.json + figures/ 출력
```

스캔 판별(`is_scan_page`) 로직은 제거한다 — PNG 변환이 스캔/디지털 구분을 불필요하게 만든다.

---

### 데이터 송수신 상세

#### 1. 입력 — DI에 보내는 것

| 항목 | 내용 |
|------|------|
| 전송 단위 | 페이지 1장씩 |
| 포맷 | `image/png` (bytes) |
| 생성 방법 | `fitz.Page.get_pixmap(Matrix(2.0, 2.0))` → `PIL.Image` → `io.BytesIO` |
| 해상도 | 144 dpi (scale=2.0), 필요 시 216 dpi (scale=3.0) |
| 크기 예시 | 1749×1080px, ~200~600 KB/장 |

```python
pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
buf = io.BytesIO(); img.save(buf, format="PNG")
png_bytes = buf.getvalue()

poller = di_client.begin_analyze_document(
    "prebuilt-layout",
    png_bytes,
    content_type="image/png",
)
result = poller.result()
```

#### 2. DI 응답 — 받는 원시 객체

| 필드 | 타입 | 내용 |
|------|------|------|
| `result.pages[0].lines[]` | list | 텍스트 라인. `.content` (문자열), `.polygon` (픽셀 좌표 x,y 반복 리스트) |
| `result.paragraphs[]` | list | 단락. `.role` (title/body/pageHeader/pageFooter 등), `.content` |
| `result.figures[]` | list | 그림. `.bounding_regions[0].polygon` (픽셀 좌표), `.caption.content` (있을 때만) |
| `result.content` | str | 전체 텍스트 이어붙인 문자열 (읽기 순서) |

**polygon 좌표계**: PNG 전송 시 → **픽셀(px)** 단위, `[x0, y0, x1, y0, x1, y1, x0, y1]` 형태 (4꼭짓점 8개 float)

#### 3. 가공 — 우리가 변환하는 것

```
DI polygon (8개 float, px) → bbox [x0, y0, x1, y1] (px, int)

xs = polygon[0::2]; ys = polygon[1::2]
bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
```

figure 최소 면적 필터: `(x1-x0) * (y1-y0) < 50*50 px²` → 제외

figure 크롭:
```
PIL 이미지(메모리에 이미 로드됨).crop((x0, y0, x1, y1)) → PNG 저장
```

---

### 출력 스키마

#### read.json (페이지 배열)

```json
[
  {
    "page": 5,
    "line_count": 18,
    "lines": [
      {
        "content": "정규분포의 성질",
        "bbox": [198, 158, 873, 228]
      }
    ],
    "paragraphs": [
      {
        "role": "body",
        "content": "평균 μ 표준편차 σ"
      }
    ],
    "figures": [
      {
        "img_path": "figures/page005_img00.png",
        "caption": "그림 1. 정규분포 곡선",
        "bbox": [278, 668, 1544, 995]
      }
    ]
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `page` | int | 1-based 페이지 번호 |
| `line_count` | int | lines 배열 길이 |
| `lines[].content` | str | 텍스트 라인 |
| `lines[].bbox` | [x0,y0,x1,y1] int px | PNG 이미지 내 픽셀 좌표 |
| `paragraphs[].role` | str | title / body / pageHeader / pageFooter 등 |
| `paragraphs[].content` | str | 단락 텍스트 |
| `figures[].img_path` | str | 크롭 PNG 상대 경로 |
| `figures[].caption` | str | DI 감지 캡션 (없으면 `""`) |
| `figures[].bbox` | [x0,y0,x1,y1] int px | PNG 이미지 내 픽셀 좌표 |

#### 디렉터리 구조

```
result/
├── read.json          # 전체 페이지 배열
├── content.txt        # 페이지 구분자 포함 전체 텍스트
├── text_result.txt    # 사람이 읽기 좋은 요약
└── figures/
    ├── page005_img00.png
    ├── page018_img00.png
    └── ...
```

---

### 구현 대상 함수 (extract_images.py)

| 함수 | 역할 |
|------|------|
| `page_to_png_bytes(page, scale)` | PyMuPDF 페이지 → PIL → PNG bytes |
| `analyze_page(png_bytes)` | DI prebuilt-layout 호출 → lines/paragraphs/figures 반환 |
| `polygon_to_bbox_px(polygon)` | DI 8-float polygon → [x0,y0,x1,y1] px |
| `crop_figure(pil_img, bbox, out_path)` | PIL 크롭 → PNG 저장 |
| `run_pipeline(pdf_path, pages, scale)` | 전체 파이프라인 실행 → read.json + figures/ |

---

### 미결 사항

- figure 최소 면적 threshold 50×50px 적정성 — 아이콘류 오탐 여부 확인 필요
- 페이지당 API 호출 → 48페이지 PDF = 48회 호출. 비용·속도 고려해 배치 처리 검토
- 스캔 PDF(진짜 스캔본)에서 figure caption 추출 품질 — 추가 테스트 필요

---

---

## Plan B — PyMuPDF + DI + Vision 분기 처리 (기존 방안)

### 분기 처리 구조

```
페이지 입력
    ↓
스캔 판별: page.get_text().strip() < 50자
    │
    ├── 스캔 페이지 ──────────────────────────────────────────┐
    │                                                         │
    └── 디지털 페이지                                          │
            ├── [PyMuPDF] 래스터 블록 감지                     │
            └── [DI → Vision fallback]                        │
                    ↓                                         │
                IoU 병합                                       │
                    ↓                                         ↓
                            크롭 저장 + figures.json 출력
```

---

### 분기별 사용 도구

#### 스캔 페이지

| 단계 | 도구 | 출력 |
|------|------|------|
| figure 감지 | Azure Document Intelligence `prebuilt-layout` | bbox, caption |
| DI 실패 시 fallback | GPT-4o Vision | bbox, caption, type |

- `surrounding_text`: 없음 (텍스트 레이어 없음)
- `type`: DI는 항상 `"other"`, Vision은 `photo/chart/diagram/map/other`

#### 디지털 페이지

| 단계 | 도구 | 출력 |
|------|------|------|
| 래스터 이미지 감지 | PyMuPDF `get_text("dict")` type==1 블록 | bbox, surrounding_text |
| 벡터 차트 감지 | Azure Document Intelligence `prebuilt-layout` | bbox, caption |
| DI 실패 시 fallback | GPT-4o Vision | bbox, caption, type |
| 중복 제거 | IoU ≥ 0.3 → 같은 이미지 판정 | 병합 결과 |

병합 규칙:
- IoU ≥ 0.3 → PyMuPDF bbox 유지 + DI/Vision의 caption, type 보완
- IoU < 0.3 → DI/Vision 단독 감지 항목 추가 (벡터 차트)

---

### 출력 스키마 (figures.json)

```json
{
  "page": 17,
  "bbox": [278, 668, 1544, 995],
  "caption": "",
  "type": "other",
  "surrounding_text": "정규분포의 성질 평균 μ 표준편차 σ",
  "img_path": "img/page017_img00.png",
  "source": "PyMuPDF"
}
```

기존 대비 `surrounding_text` 필드 추가. 스캔/DI 경로는 `""`.

---

### 구현 대상 함수 (extract_images.py)

| 함수 | 역할 |
|------|------|
| `is_scan_page(page)` | 텍스트 < 50자 → True |
| `_get_surrounding_text(blocks, img_block)` | y거리 기준 인접 텍스트 블록 수집 |
| `extract_raster_blocks(page, pil_img)` | type==1 블록 → bbox(px) + surrounding_text |
| `iou(a, b)` | bbox IoU 계산 |
| `merge_figures(raster, di)` | IoU 기반 중복 제거 + 병합 |

---

### 미결 사항

- IoU threshold 0.3 적정성 — 실제 테스트 후 조정 필요
- 스캔 판별 threshold 50자 — 혼합 PDF에서 충분한지 확인 필요
