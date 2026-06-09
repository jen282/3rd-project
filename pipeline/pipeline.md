# 전처리 파이프라인 설계 문서

## 개요

PDF 문서를 입력받아 Azure Content Understanding API로 텍스트를 추출하고, NLP 전처리 후 OpenAI LLM을 통해 목차를 자동 생성하는 단일 파이프라인.

**입력:** PDF 파일 경로  
**출력:** `llm/result/[pdf이름]_vN/` 폴더

```bash
# 의존성 설치
pip install -r requirements.txt

# 실행
python pipeline.py --pdf "../data/raw/통계기초.pdf"
python pipeline.py --pdf "../data/raw/통계기초.pdf" --debug
```

---

## 파이프라인 단계

```
PDF 입력
  │
  ▼
[STEP 1] API 추출
  │   extract/content-understanding/extract.py 로직 재사용
  │   raw_response.json이 이미 있으면 API 호출 스킵 (비용 절감)
  │   → raw_response.json 저장 (필수)
  │
  ▼
[STEP 2] 텍스트 추출 (메모리)
  │   raw_response.json → contents[].markdown 필드 직접 파싱
  │   테이블, figure, 주석, 수식 블록 제거 → 순수 텍스트 문자열
  │   content.md / txt/content.txt 저장 없음 (--debug 시에만 저장)
  │   테이블 추출 없음
  │
  ▼
[STEP 3] NLP 전처리 (메모리)
  │   preprocessing/refine_by_nlp/run_nlp_refine2.py 의 refine_text() 로직 재사용
  │   4단계 전처리를 메모리에서 순차 실행, 중간 파일 저장 없음
  │   (--debug 시에만 step1~4 파일 저장)
  │
  ▼
[STEP 4] LLM 호출 (OpenAI)
  │   전처리 완료된 최종 텍스트로 목차 5~10개 추출 요청
  │   → toc_result.txt 저장 (필수)
  │
  ▼
결과 저장
    llm/result/[pdf이름]_vN/
```

---

## 저장 파일 전략

### 기본 실행 (저장 최소화)

```
result/통계기초_v1/
├── raw_response.json     ← 필수 (API 재호출 방지)
└── toc_result.txt        ← 필수 (최종 출력)
```

### --debug 실행 (중간 파일 전체 저장)

```
result/통계기초_v1/
├── raw_response.json
├── content.md            ← API 마크다운 원본
├── txt/
│   └── content.txt       ← 테이블·figure 제거 후 텍스트
├── nlp/
│   ├── step1_clean.txt
│   ├── step2_merged.txt
│   ├── step3_kiwi_sents.txt
│   └── step4_spaced.txt  ← 스캔 PDF만 생성
└── toc_result.txt
```

---

## STEP 1 — API 추출

**참조 파일:** `extract/content-understanding/extract.py`

- Azure AI Content Understanding API (버전 `2024-12-01-preview`) 사용
- Analyzer ID: `pdf-content-extractor`
- 환경변수: `.env`의 `CONTENT_UNDERSTANDING_ENDPOINT`, `CONTENT_UNDERSTANDING_KEY`
- PDF를 업로드하고 폴링으로 완료 대기
- **출력:** `raw_response.json` (필수 저장)
- `raw_response.json`이 이미 존재하면 API 재호출 없이 파일에서 로드

---

## STEP 2 — 텍스트 추출 (메모리)

`content.md`를 경유하지 않고 `raw_response.json`에서 직접 텍스트 추출.

```
raw_response.json
  → result.contents[].markdown 필드 합산 (메모리)
  → 테이블(<table>), figure, HTML 주석, 수식 블록 제거
  → 스캔 PDF 아티팩트(파이프 문자 등) 추가 제거
  → 순수 텍스트 문자열 (다음 단계로 전달)
```

**저장:** 기본 없음. `--debug` 시 `content.md`(마크다운 원본), `txt/content.txt`(정제 텍스트) 저장.  
**테이블 추출:** 제외 (추후 필요 시 추가).

---

## STEP 3 — NLP 전처리 (메모리)

**참조 파일:** `preprocessing/refine_by_nlp/run_nlp_refine2.py` — `refine_text()` 함수 (경로: `preprocess/preprocessing/refine_by_nlp/`)

| 단계 | 처리 내용 | 라이브러리 |
|------|-----------|-----------|
| 1 | 인코딩 교정, HTML/주석 제거, URL 제거, 공백 정규화 | ftfy, regex |
| 2 | 끊긴 문장 병합 (문장 종결 패턴 기반) | regex |
| 3 | 형태소 분석 기반 문장 분리 | kiwipiepy |
| 4 | 띄어쓰기 교정 (스캔 PDF만 적용) | kiwipiepy |

**step4 적용 대상 구분 이유:**  
디지털 PDF는 원문 텍스트 그대로 추출되어 띄어쓰기가 이미 정확하다. `kiwi.space()`를 적용하면 전문용어를 오히려 잘못 분리할 수 있어 품질이 저하된다. 스캔 PDF는 OCR 과정에서 띄어쓰기 정보가 손실되므로 교정이 필요하다. (부하 문제가 아닌 정확도 문제 — Kiwi는 step3에서 이미 로드된 동일 모델이므로 추가 부하 없음)

**LLM 입력으로 사용되는 최종 텍스트:**
- 스캔 PDF → step4 출력
- 디지털 PDF → step3 출력

**저장:** 기본 없음. `--debug` 시 `nlp/step1_clean.txt` ~ `step4_spaced.txt` 저장.

---

## STEP 4 — LLM 호출 (목차 추출)

**환경변수 (`.env`):**
- `OPEN_AI_ENDPOINT`
- `OPEN_AI_KEY`
- `OPEN_AI_DEPLOYMENT_NAME`

**입력:** 전처리 완료된 최종 텍스트 전문  
**요청:** 문서에서 목차 항목 5~10개 추출

**프롬프트 구조:**
```
system: 당신은 한국어 교육 문서를 분석하는 전문가입니다.
        주어진 텍스트에서 문서의 핵심 목차 항목을 추출하세요.

user:   아래는 PDF에서 추출한 텍스트입니다.
        이 문서의 목차 항목을 5개에서 10개 사이로 추출해 주세요.
        각 항목은 번호와 제목을 포함해 주세요.
        텍스트 형식으로 반환하세요.

        [전처리 완료 텍스트]
```

**출력 (`toc_result.txt`):**
```
1. 통계의 기본 개념
2. 자료의 종류와 수집 방법
3. 도수분포와 그래프
...
```

---

## 버전 관리 규칙

- 결과 폴더: `result/[pdf이름]_vN/` (N은 자동 증가)
- 같은 PDF를 재실행하면 새 버전 폴더 생성 (기존 결과 보존)
- 각 실행 후 이 문서 맨 하단 **시도 기록**에 변경사항 추가

---

## 환경 설정

```bash
# 의존성
pip install python-dotenv openai kiwipiepy ftfy

# 실행
python pipeline.py --pdf "path/to/document.pdf"          # 기본 (필수 파일만 저장)
python pipeline.py --pdf "path/to/document.pdf" --debug  # 중간 파일 전체 저장
```

**`.env` 위치:** `c:\Users\USER\ms-project3\preprocess\.env`

---

## 코드 파일 위치 참조

| 역할 | 파일 경로 |
|------|----------|
| API 추출 | `extract/content-understanding/extract.py` |
| NLP 전처리 | `preprocessing/refine_by_nlp/run_nlp_refine2.py` |
| 파이프라인 실행 | `llm/pipeline.py` |

---

## 시도 기록

<!-- 파이프라인 실행 시마다 아래에 기록 추가 -->

---

### v1 — 초기 설계

- 날짜: 2026-06-09
- 변경사항: 초기 파이프라인 설계 문서 작성
- 구성: STEP1(Azure API) → STEP2(텍스트 추출, 메모리) → STEP3(NLP 4단계, 메모리) → STEP4(OpenAI 목차 추출)
- 저장 파일: 기본은 `raw_response.json` + `toc_result.txt`만, `--debug` 시 중간 파일 전체 저장
- 제외: 이미지 크롭, 테이블 추출
- content.md 경유 없이 raw_response.json → 텍스트 직접 추출

---

### v4 — 통계기초.pdf

- 날짜: 2026-06-09
- PDF: 통계기초.pdf (디지털)
- 디버그: X
- 변경사항: (직접 기입)

---

### v2 — 국사교과서.pdf

- 날짜: 2026-06-09
- PDF: 국사교과서.pdf (디지털)
- 디버그: X
- 소요시간: 총 10.5s
  - STEP1 API 추출: 0.7s
  - STEP2 텍스트 추출: 0.0s
  - STEP3 NLP 전처리: 2.6s
  - STEP4 LLM 호출: 7.1s
- 변경사항: (직접 기입)
