# Document Intelligence 파이프라인 — 통계기초.pdf 결과 요약

## 실행 조건

| 항목 | 값 |
|------|----|
| 대상 PDF | `통계기초.pdf` (디지털 슬라이드 PDF) |
| 총 페이지 | 48페이지 |
| 해상도 | 1920×1080 px (2x 렌더링) |
| 파이프라인 | Document Intelligence prebuilt-layout → (실패 시) GPT-4o Vision fallback |

---

## 수치 결과

| 항목 | 값 |
|------|----|
| 총 추출 이미지 | **23개** |
| Document Intelligence 감지 | **14개** (13개 페이지) |
| GPT-4o Vision fallback 감지 | **9개** (7개 페이지) |
| DI 성공 페이지 | 13페이지 |
| DI 실패 → Vision 감지 페이지 | 7페이지 |
| DI·Vision 모두 0개 페이지 | 28페이지 (텍스트 전용 슬라이드) |

---

## 페이지별 감지 결과

| 페이지 | source | 감지 수 | type | caption |
|--------|--------|---------|------|---------|
| 3 | Vision | 1 | chart | (없음) |
| 4 | DocumentIntelligence | 1 | other | (없음) |
| 17 | DocumentIntelligence | 1 | other | (없음) |
| 18 | DocumentIntelligence | 1 | other | (없음) |
| 24 | DocumentIntelligence | 1 | other | (없음) |
| 25 | DocumentIntelligence | 1 | other | (없음) |
| 26 | DocumentIntelligence | 1 | other | (없음) |
| 27 | DocumentIntelligence | 1 | other | (없음) |
| 28 | DocumentIntelligence | 1 | other | (없음) |
| 29 | DocumentIntelligence | 1 | other | (없음) |
| 30 | DocumentIntelligence | 1 | other | (없음) |
| 34 | DocumentIntelligence | 1 | other | (없음) |
| 35 | DocumentIntelligence | 1 | other | (없음) |
| 38 | Vision | 1 | chart | (없음) |
| 39 | Vision | 1 | chart | "가설 검정 방법" |
| 40 | Vision | 1 | chart | "가설 검정 방법 – t 검정" |
| 41 | Vision | 1 | chart | (없음) |
| 42 | Vision | 1 | chart | "분산 분석 개요 및 예시" |
| 44 | DocumentIntelligence | 2 | other | (없음) |
| 47 | Vision | 3 | chart | "τ = 0.2" / "τ = 1" / "τ = -1" |

---

## PyMuPDF 방안 3과 비교

| 항목 | 방안 3 (PyMuPDF) | DI + Vision |
|------|:---------------:|:-----------:|
| 총 추출 수 | 14개 | **23개** |
| 캡션 | ❌ | △ (Vision만, 6개) |
| 이미지 type 분류 | ❌ | △ (Vision만) |
| 벡터 차트 감지 | ❌ | ✅ (Vision fallback으로 보완) |
| surrounding_text | ✅ (100%) | ❌ |
| bbox 정밀도 | 높음 | 중간 (Vision은 낮음) |

**공통 감지 페이지**: 17, 18, 24, 25, 26, 27, 28, 29, 30, 34, 44, 47  
**DI+Vision만 추가 감지**: page 3, 4, 35, 38, 39, 40, 41, 42  
→ 방안 3이 놓친 9개는 PDF에 래스터 이미지 블록(type==1)으로 존재하지 않는 **벡터 기반 차트** 영역

---

## 이슈 및 한계

### 1. DI 캡션 미추출 (14개 전부 `caption: ""`)
슬라이드 기반 PDF는 교과서와 달리 이미지 바로 아래에 명시적 캡션 텍스트가 없음.  
DI가 레이아웃 구조에서 캡션을 연결하지 못한 것.

### 2. DI type 모두 `"other"`
DI `prebuilt-layout`은 이미지 타입을 분류하지 않음. 반면 Vision fallback은 `"chart"`로 정확히 분류.

### 3. Vision bbox 정밀도 낮음
- page 39: `[0, 0, 1920, 1080]` → 페이지 전체를 이미지로 감지
- Vision은 픽셀 단위 정밀도를 보장하지 않음

### 4. DI fallback 빈도 높음 (35/48 페이지 = 73%)
슬라이드 PDF의 차트는 래스터 이미지가 아닌 벡터 도형으로 구성되는 경우가 많아 DI가 figure로 인식하지 못함.  
→ 이 PDF 유형에서는 Vision이 실질적인 주요 감지 수단

---

## 결론

Document Intelligence 파이프라인은 통계기초.pdf(디지털 슬라이드)에서 **동작은 하지만 최적 도구는 아님**.

- 방안 3(PyMuPDF)보다 9개 더 감지하여 커버리지는 우수
- 그러나 캡션·타입 정보는 Vision fallback에서만 부분적으로 생성됨
- 슬라이드 PDF에서 DI 단독으로는 벡터 차트를 잡지 못해 Vision fallback 의존도가 높음
- 방안 3 + GPT-4o Vision(방안 4) 조합이 `surrounding_text`까지 확보하므로 디지털 PDF에서는 더 유리
