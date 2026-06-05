# pymupdf 방안 1·2·3 테스트 결과

대상 PDF: `../data/국사교과서.pdf` (50페이지, 7.8MB)  
환경: Python 3.14.4 / pymupdf 1.27.2.3 / Pillow 12.2.0

---

## 폴더 구조

```
pymupdf/
├── approach1/
│   ├── test_approach1.py       # 방안 1 테스트 코드
│   └── results/
│       ├── page000_img00.jpeg  # 추출 이미지 (100개)
│       ├── report.json         # 상세 통계
│       └── summary.md          # 결과 요약
├── approach2/
│   ├── test_approach2.py       # 방안 2 테스트 코드
│   └── results/
│       ├── page_000.png        # 렌더링 이미지 (50개)
│       ├── report.json
│       └── summary.md
├── approach3/
│   ├── test_approach3.py       # 방안 3 테스트 코드
│   └── results/
│       ├── page000_block00.png # 크롭 이미지 (100개)
│       ├── report.json
│       └── summary.md
└── README.md                   # 이 파일
```

---

## 수치 비교

| 방안 | 추출 수 | 소요 시간 | 파일 크기(평균) | 오류 |
|---|---|---|---|---|
| 1. 래스터 추출 | 100개 JPEG | **0.037초** | ~150 KB | 0 |
| 2. 페이지 렌더링 | 50개 PNG | 8.727초 | ~1.4 MB | 0 |
| 3. 블록 크롭 | 100개 PNG | 7.437초 | 다양 | 0 |

---

## 기능 비교

| 항목 | 방안 1 | 방안 2 | 방안 3 |
|---|---|---|---|
| 벡터 다이어그램 포함 | ❌ | ✅ | ❌ |
| bbox 위치 메타데이터 | ❌ | ❌ | ✅ |
| 주변 텍스트 컨텍스트 | ❌ | ❌ | ✅ (텍스트 레이어 필요) |
| 원본 이미지 무손실 | ✅ | ❌ (재렌더링) | ❌ (재렌더링) |
| GraphRAG 노드 연결 | 수동 | 수동 | **바로 연결 가능** |
| 속도 | ⭐⭐⭐ | ⭐ | ⭐ |

---

## 이 PDF에서 발견된 특이사항

`국사교과서.pdf`는 **텍스트 레이어 없는 스캔/인쇄 기반 PDF**:
- 각 페이지 = 1050×1500 JPEG 배경 이미지 + 838×188 헤더 이미지
- 방안 3의 `surrounding_text`가 모두 빈 문자열 (텍스트 블록 없음)
- 방안 1·3이 동일한 이미지를 추출함

텍스트 레이어가 있는 PDF(디지털 출력 PDF)에서는 방안 3의 `surrounding_text`가 채워지고
GraphRAG 연결 가치가 극대화된다.

---

## GraphRAG 파이프라인 권장

```
방안 3 (블록 크롭 → 이미지 + bbox + surrounding_text)
    +
방안 4 (GPT-4o Vision → concept / relations 자동 생성)
```

방안 3의 `report.json`이 방안 4의 입력 배치로 바로 사용 가능.
