# Document Intelligence Layout — 실험 요약

## PNG 변환 방식 (extract_png.py)

### 배경

`통계기초.pdf`는 PPT를 변환한 슬라이드 PDF로, PDF 직접 전송 시 텍스트가 도형(shape) 안에 있어 DI가 거의 추출하지 못했다.

| 방식 | 추출 라인 수 | 문제 |
|---|---|---|
| PDF 직접 → prebuilt-layout | 5줄 (2페이지) | 도형 텍스트 누락 |
| PDF 직접 → prebuilt-read | 11줄 (2페이지) | 도형 텍스트 누락 |
| **PNG 변환 → prebuilt-layout** | **730줄 (48페이지)** | 해결됨 |

### 실험 설정

- **PDF**: `data/통계기초.pdf` (48페이지, 슬라이드형 디지털 PDF)
- **모델**: `prebuilt-layout`
- **PNG 렌더링 배율**: 2.0x (144dpi)
- **스크립트**: `extract_png.py`

### 결과

| 항목 | 수치 |
|---|---|
| 처리 페이지 | 48페이지 |
| 추출 라인 | 730개 |
| 추출 단락 | 600개 |
| 추출 그림 | 14개 |

### 출력 파일 (`result_png/`)

| 파일 | 설명 |
|---|---|
| `read.json` (197KB) | 페이지별 lines / paragraphs / figures (bbox 포함) |
| `content.txt` (28KB) | 페이지 구분자 포함 전체 텍스트 |
| `text_result.txt` (32KB) | 페이지별 정리 텍스트 (사람이 읽기 좋은 포맷) |
| `figures/page*_img*.png` | 크롭된 그림 18장 |

### 관찰 사항

- 슬라이드 내 도형 텍스트, 표, 수식 레이블 등 모두 lines로 추출됨
- 그림은 주로 다이어그램·분포 차트 등 통계 시각화 자료 (14페이지에서 18개 파일)
- 일부 페이지(7, 42 등 섹션 구분 슬라이드)는 lines 수가 적음 — 정상
- 한글이 깨지는 페이지 없음

### 실행 방법

```bash
# 기본 (전체 페이지, prebuilt-read)
python extract_png.py

# 텍스트 + 이미지 크롭
python extract_png.py --model prebuilt-layout

# 일부 페이지만 테스트
python extract_png.py --pages 1-5 --model prebuilt-layout

# 고해상도 (216dpi)
python extract_png.py --scale 3.0 --model prebuilt-layout
```
