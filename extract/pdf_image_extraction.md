# PDF 처리 목적 및 테스트 방안

## 1. 목적

### 최종 목표
1. **Graph RAG 통합** — 이미지 속 정보를 그래프 노드에 포함
2. **이미지 반환** — 개념 클릭 시 원본 이미지 표시, LLM 검색 시 이미지 첨부 반환

---

## 2. 필요 추출 항목 (5가지)

> 텍스트 추출은 그래프 전체의 기반, 나머지 4가지는 이미지 노드를 그래프에 통합하기 위한 조건

| 항목 | 어디에 쓰는가 | 없으면 |
|------|-------------|--------|
| **텍스트 추출** | 개념·관계 추출 → 그래프 텍스트 노드 생성 | 그래프 자체를 못 만듦 |
| **캡션** | PDF에 캡션이 이미 있으면 LLM 캡셔닝 호출 스킵 → 비용 절약. 없을 때만 AI 생성 | 매번 LLM 호출 필요 (비용 낭비) |
| **이미지 bytes** | GPT-4o Vision / Azure AI Vision에 넘겨서 캡션 생성 → 캡션을 임베딩 → GraphRAG 이미지 노드 벡터화 | 이미지 노드를 텍스트와 같은 벡터 공간에 놓을 수 없음 |
| **이미지 bbox** | 같은 페이지에서 이미지 주변 텍스트를 찾는 기준점. "이 이미지 위아래 N px 안에 있는 텍스트 = surrounding_text" | surrounding_text 없이 캡셔닝 → 맥락 없는 이미지 설명 생성 |
| **텍스트-이미지 연결** | 이미지 노드 ↔ 텍스트 노드를 has_visual 엣지로 연결. 클러스터링 시 이미지가 관련 텍스트와 같은 방에 배치되게 함 | 이미지 노드가 그래프에서 floating → 클러스터링 시 엉뚱한 방에 배치되거나 고아 노드 |

### 항목 간 흐름

```
텍스트 추출  →  텍스트 노드 생성           (그래프 뼈대)
bbox        →  surrounding_text 탐색
bytes       →  VLM 캡션 생성
캡션        →  이미지 노드 벡터화
연결        →  has_visual 엣지            (텍스트 ↔ 이미지 연결)
```

---

## 3. PDF 유형별 처리 전략

| PDF 유형 | 텍스트 레이어 | 처리 방법 |
|---------|------------|---------|
| 디지털 PDF | ✅ 있음 | 텍스트 레이어 직접 추출 |
| 스캔 PDF | ❌ 없음 | 페이지 → 이미지 변환 후 OCR |

---

## 4. 테스트 가능한 도구 전체 목록

### 4-1. 텍스트 추출 (무료, 디지털 PDF)

| 도구 | 설치 | bbox | 특징 |
|------|------|------|------|
| **PyMuPDF** | `pip install pymupdf` | ✅ | 가장 빠름. 이미지 크롭·bbox 동시 가능 |
| **pdfplumber** | `pip install pdfplumber` | ✅ | 표 추출 강함 |

### 4-2. OCR (무료, 스캔 PDF)

| 도구 | 설치 | bbox | 한국어 | GPU | 특징 |
|------|------|------|--------|-----|------|
| **Tesseract** | `apt install tesseract-ocr` | ✅ | ✅ (kor 팩) | ❌ | 가장 범용, CPU 가능 |
| **EasyOCR** | `pip install easyocr` | ✅ | ✅ | 권장 | 정확도 높음 |
| **PaddleOCR** | `pip install paddlepaddle paddleocr` | ✅ | ✅ | 권장 | 한·중 강함 |
| **Surya** | `pip install surya-ocr` | ✅ | ✅ (90개 언어) | △ | Docling 내부 엔진, CPU 가능 |

### 4-3. 문서 파싱 올인원 (무료)

> 디지털 + 스캔 PDF 모두 처리. 내부적으로 OCR 포함.

| 도구 | 설치 | bbox | 한국어 | GPU | 특징 |
|------|------|------|--------|-----|------|
| **Docling** | `pip install docling` | ✅ | ✅ | △ | 레이아웃·표 구조 강함. CPU 가능하나 느림 |
| **Marker** | `pip install marker-pdf` | ✅ | ✅ | △ | Surya 기반. PDF→Markdown 특화. LLM 입력으로 넘기기 편함 |
| **MinerU** | `pip install mineru` | ✅ | ✅ | 권장 | 품질 높음. GPU 없으면 느림 |
| **GOT-OCR 2.0** | HuggingFace | ✅ | ✅ | 필요 | 수식·표·악보까지 처리 |
| **ppstructure** | `pip install paddlepaddle paddleocr` | ✅ | ✅ | 권장 | PaddleOCR 상위. 레이아웃+OCR 통합 |

### 4-4. 로컬 VLM (무료, GPU 필요)

> 캡션 생성 용도. bbox 없음 → PyMuPDF로 크롭 후 캡션 생성 조합으로 사용.

| 도구 | VRAM | 한국어 | 특징 |
|------|------|--------|------|
| **Qwen2-VL** | 8GB+ | ✅ | 문서 이해 강함 |
| **InternVL2** | 8GB+ | ✅ | OCR+VLM 통합, 문서 특화 |
| **Phi-3.5-vision** | 4GB+ | △ | 경량, Microsoft 출시 |
| **LLaVA** | 8GB+ | △ | 범용 VLM |

### 4-5. 클라우드 API (유료, 단 무료 티어 있음)

| 도구 | 무료 범위 | bbox | 캡션 | 특징 |
|------|-----------|------|------|------|
| **Google Cloud Vision** | 월 1,000회 | ✅ | △ | 무료 티어로 테스트 가능 |
| **AWS Textract** | 월 1,000p (90일) | ✅ | ❌ | 표 추출 강함 |
| **Naver Clova OCR** | 월 100회 | ✅ | ❌ | 한국어 특화 |
| **Mistral OCR 3** | 없음 ($2/1K p) | ✅ | ✅ | bbox+캡션 동시. 유일한 유료 올인원 |
| **Azure Document Intelligence** | 없음 ($1.5/1K p) | ✅ | ❌ | 캡션은 별도 VLM 필요. 이미 스택에 있음 |
| **GPT-4o-mini Vision** | 없음 (~$0.001/img) | ❌ | ✅ | 가장 저렴한 유료 캡션 생성 |

---

## 5. 도구별 추출 가능 항목

> ✅ 가능 / △ 조건부 가능 / ❌ 불가

| 도구 | 텍스트 추출 | 이미지 bytes | 이미지 bbox | 캡션 | 텍스트-이미지 연결 | 비고 |
|------|:---------:|:-----------:|:-----------:|:----:|:-----------------:|------|
| **PyMuPDF** | ✅ | ✅ | ✅ | ❌ | △ | 디지털 PDF만. 연결은 bbox 기반으로 직접 구현 필요 |
| **pdfplumber** | ✅ | ✅ | ✅ | ❌ | △ | 디지털 PDF만. 표 추출 강함 |
| **Tesseract** | ✅ | ❌ | ✅ (텍스트) | ❌ | ❌ | 텍스트 bbox만. 이미지 블록 인식 없음 |
| **EasyOCR** | ✅ | ❌ | ✅ (텍스트) | ❌ | ❌ | 텍스트 bbox만 |
| **PaddleOCR** | ✅ | ❌ | ✅ (텍스트) | ❌ | ❌ | 텍스트 bbox만 |
| **Surya** | ✅ | ❌ | ✅ (텍스트) | ❌ | ❌ | 텍스트 bbox만 |
| **Docling** | ✅ | ✅ | ✅ | ❌ | ✅ | 레이아웃 구조로 텍스트-이미지 연결 제공 |
| **Marker** | ✅ | ✅ | △ | ❌ | △ | Markdown 출력. bbox 정밀도 낮음. 연결은 문서 구조 기반 |
| **MinerU** | ✅ | ✅ | ✅ | ❌ | ✅ | 레이아웃 분석으로 연결 제공. GPU 권장 |
| **GOT-OCR 2.0** | ✅ | ❌ | △ | ❌ | ❌ | 텍스트 위주. 이미지 블록 분리 약함 |
| **ppstructure** | ✅ | ✅ | ✅ | ❌ | ✅ | 레이아웃+OCR 통합. 연결 구조 제공 |
| **Qwen2-VL** | ✅ | ❌ | ❌ | ✅ | ❌ | 캡션 생성 전용. bbox 없음 |
| **InternVL2** | ✅ | ❌ | ❌ | ✅ | ❌ | 캡션 생성 전용. bbox 없음 |
| **Phi-3.5-vision** | ✅ | ❌ | ❌ | ✅ | ❌ | 캡션 생성 전용. bbox 없음 |
| **LLaVA** | ✅ | ❌ | ❌ | ✅ | ❌ | 캡션 생성 전용. bbox 없음 |
| **Google Cloud Vision** | ✅ | ❌ | ✅ | △ | ❌ | 캡션은 label detection 수준. 문맥 없음 |
| **AWS Textract** | ✅ | ❌ | ✅ (텍스트) | ❌ | ❌ | 텍스트·표 bbox만 |
| **Naver Clova OCR** | ✅ | ❌ | ✅ (텍스트) | ❌ | ❌ | 한국어 특화. 텍스트 bbox만 |
| **Mistral OCR 3** | ✅ | ✅ | ✅ | ✅ | ✅ | 5가지 전부 가능. 유일한 유료 올인원 |
| **Azure Document Intelligence** | ✅ | ✅ | ✅ | ❌ | △ | 캡션 없음. 연결은 레이아웃 기반 부분 제공 |
| **GPT-4o-mini Vision** | ✅ | ❌ | ❌ | ✅ | ❌ | 캡션 생성 전용. bbox 없음 |

### 항목별 커버 가능한 도구 요약

| 항목 | 단독으로 가능한 도구 | 조합 필요 |
|------|-------------------|---------|
| 텍스트 추출 | 전부 | - |
| 이미지 bytes | PyMuPDF, pdfplumber, Docling, MinerU, Marker, ppstructure, Mistral OCR 3, Azure DI | OCR 단독 도구는 불가 |
| 이미지 bbox | PyMuPDF, pdfplumber, Docling, MinerU, ppstructure, Mistral OCR 3, Azure DI | OCR/VLM 단독 불가 |
| 캡션 | Mistral OCR 3, 로컬 VLM, GPT-4o-mini | 나머지는 VLM 조합 필요 |
| 텍스트-이미지 연결 | Docling, MinerU, ppstructure, Mistral OCR 3 | 나머지는 bbox 기반 직접 구현 필요 |

---

## 6. 조합별 테스트 매트릭스 (5가지 항목 기준)

| 조합 | 텍스트 | 이미지 bytes | 이미지 bbox | 캡션 | 텍스트-이미지 연결 | 비용 | 난이도 |
|------|:------:|:-----------:|:-----------:|:----:|:-----------------:|------|--------|
| PyMuPDF 단독 | ✅ | ✅ | ✅ | ❌ | △ | 무료 | 쉬움 |
| PyMuPDF + Tesseract | ✅ | ✅ | ✅ | ❌ | △ | 무료 | 쉬움 |
| PyMuPDF + PaddleOCR | ✅ | ✅ | ✅ | ❌ | △ | 무료 | 쉬움 |
| Docling 단독 | ✅ | ✅ | ✅ | ❌ | ✅ | 무료 | 쉬움 |
| Marker 단독 | ✅ | ✅ | △ | ❌ | △ | 무료 | 쉬움 |
| MinerU 단독 | ✅ | ✅ | ✅ | ❌ | ✅ | 무료 | 중간 |
| ppstructure 단독 | ✅ | ✅ | ✅ | ❌ | ✅ | 무료 | 중간 |
| **PyMuPDF + GPT-4o-mini** | ✅ | ✅ | ✅ | ✅ | △ | 최소 | 쉬움 |
| **Docling + GPT-4o-mini** | ✅ | ✅ | ✅ | ✅ | ✅ | 최소 | 쉬움 |
| PyMuPDF + 로컬 VLM | ✅ | ✅ | ✅ | ✅ | △ | 무료 | 중간 |
| **Mistral OCR 3 단독** | ✅ | ✅ | ✅ | ✅ | ✅ | $2/1K | 쉬움 |

---

## 7. 테스트 우선순위

```
1순위  Docling 단독                  무료. 5가지 중 4가지 커버 (캡션 제외)
2순위  PyMuPDF + Tesseract           무료, CPU. 스캔 PDF 기본 검증
3순위  Docling + GPT-4o-mini         5가지 전부 커버. 비용 최소
4순위  MinerU 또는 ppstructure       무료. 연결 구조 품질 비교
5순위  Mistral OCR 3                 유료 올인원 벤치마크 비교용
```

### 평가 항목

| 항목 | 측정 방법 |
|------|---------|
| 텍스트 추출 정확도 | 원본 대비 육안 확인 |
| 이미지 bytes 정상 추출 | 크롭 이미지 파일 확인 |
| 이미지 bbox 정확도 | 크롭 결과 육안 확인 |
| 캡션 품질 | 그래프 노드 연결 가능 여부 |
| 텍스트-이미지 연결 정확도 | 연결된 텍스트가 이미지와 관련 있는지 확인 |
| 한국어 처리 | 한국어 샘플 페이지 테스트 |
| 처리 속도 | 10페이지 기준 소요 시간 |

---

## 8. 최종 파이프라인 (목표 구조)

```
PDF 입력
 ├─ [디지털] PyMuPDF → 텍스트 블록 + 이미지 bbox·bytes
 └─ [스캔]   PyMuPDF(이미지 변환) → PaddleOCR / Docling → 텍스트 + bbox

텍스트 블록 → LLM → 개념·관계 추출 → 텍스트 노드

이미지 블록
 ├─ PDF 캡션 있음 → 캡션 그대로 사용 (LLM 호출 스킵)
 ├─ PDF 캡션 없음 → bbox 주변 텍스트(surrounding_text) 수집
 │                → bytes + surrounding_text → GPT-4o-mini → 캡션 생성
 ├─ 캡션 임베딩 → 이미지 노드 벡터화
 ├─ bytes → S3/로컬 저장 (image_id 발급)
 └─ has_visual 엣지 → 텍스트 노드 ↔ 이미지 노드 연결

검색 시
 └─ 노드 반환 + image_id → 프론트에서 이미지 렌더링
```