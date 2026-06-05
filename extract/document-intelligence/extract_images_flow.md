# extract_images.py — 처리 흐름 정리

## 목적

국사교과서 PDF에서 이미지 영역(사진·도표·지도 등)을 자동으로 감지·크롭하고,
각 이미지의 메타데이터를 `figures.json`으로 저장한다.

---

## 추출 필드

| 필드 | 설명 |
|------|------|
| `page` | 페이지 번호 (0-based) |
| `bbox` | 픽셀 좌표 `[x0, y0, x1, y1]` |
| `caption` | 이미지 근처 캡션 텍스트 |
| `type` | `photo` / `diagram` / `chart` / `map` / `other` |
| `img_path` | 저장된 크롭 이미지 경로 |
| `source` | `DocumentIntelligence` 또는 `Vision` |

---

## 단계별 처리 흐름

### 1. 초기 설정

- `.env` 파일에서 Azure 자격증명 로드
  - `DOCUMENT_INTELLIGENCE_ENDPOINT` / `KEY`
  - `OPEN_AI_ENDPOINT` / `KEY` / `DEPLOYMENT_NAME`
- 경로 설정: `data/국사교과서.pdf` → `result/img/` 크롭 저장, `result/figures.json` 출력
- 상수 설정: `MAX_PAGES=15`, `SCALE=2.0` (144 dpi), `MIN_AREA=2500 px²`

---

### 2. PDF 페이지 → 고해상도 PNG 변환

```
fitz.open(PDF) → page.get_pixmap(scale=2.0) → PIL.Image (RGB)
```

- PyMuPDF로 각 페이지를 2배 배율로 렌더링
- DI API의 50MB 파일 제한을 고려한 배율 선택

---

### 3. 1차 분석 — Azure Document Intelligence

```
PNG bytes → DI prebuilt-layout API → result.figures
```

- `prebuilt-layout` 모델로 페이지 이미지 분석
- 반환된 `figures` 리스트에서 각 figure의 `bounding_regions.polygon` 추출
- polygon(x,y 반복 좌표) → `[x0, y0, x1, y1]` bbox로 변환
- `fig.caption.content`가 있으면 캡션 텍스트 저장
- `MIN_AREA`(2500 px²)보다 작은 영역은 제외
- DI는 이미지 타입을 제공하지 않으므로 `type = "other"` 고정

---

### 4. 2차 분석 — GPT-4o Vision (DI 결과 없을 때 fallback)

DI에서 `figures`가 0개이면 Vision 모델로 재분석

```
PIL.Image → base64 PNG → GPT-4o Vision API → JSON 파싱
```

- 이미지를 base64 인코딩 후 `data:image/png;base64,...` URL로 전달
- 프롬프트에서 JSON 배열(`x0, y0, x1, y1, type, caption`) 형식으로만 응답 요청
- 응답에서 마크다운 코드블록(` ```json ``` `) 제거 후 `json.loads()` 파싱
- 응답이 dict인 경우 `regions` 또는 `figures` 키에서 리스트 추출
- `type` 필드는 Vision이 직접 분류 (`photo`, `diagram`, `chart`, `map`, `other`)

---

### 5. 크롭 이미지 저장

```
PIL.Image.crop(bbox) → result/img/page{NNN}_img{NN}.png
```

- 페이지·이미지 인덱스 기반 파일명으로 크롭 이미지 저장

---

### 6. 결과 JSON 저장

```json
[
  {
    "page": 0,
    "bbox": [x0, y0, x1, y1],
    "caption": "캡션 텍스트",
    "type": "photo",
    "img_path": "img/page000_img00.png",
    "source": "DocumentIntelligence"
  },
  ...
]
```

- 모든 페이지의 figure 목록을 `result/figures.json`에 UTF-8로 저장

---

## 전체 흐름 요약

```
PDF
 └─ [페이지별 반복]
      ├─ PyMuPDF → 고해상도 PNG
      ├─ Document Intelligence prebuilt-layout 분석
      │    ├─ figures 있음 → bbox·캡션 추출 (type=other)
      │    └─ figures 없음 → GPT-4o Vision fallback → bbox·캡션·type 추출
      └─ 각 figure: 크롭 이미지 저장 + 메타데이터 수집
 └─ figures.json 저장
```
