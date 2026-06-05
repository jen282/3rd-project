# 텍스트 정제 계획서 (Rule-based Noise Removal)

## 1. 정제의 목적

PDF에서 추출된 원시 텍스트는 OCR/파싱 과정에서 다양한 비의미적 노이즈를 포함한다.  
이를 규칙 기반(정규식) 방식으로 정제하여 다음 단계의 입력으로 적합한 고품질 텍스트를 구성하는 것이 목적이다.

- **활용 목적**: GraphRAG 인풋으로 넣을 데이터 정제
- **단위**: `--- page N ---` 구분자를 기준으로 한 페이지 단위 청크
- **접근 방식**: 추출 단계 필터링 → 라이브러리 정규화 → 정규식 제거 → 한국어 특화 처리

---

## 2. 현 상황

### 대상 파일

| 파일 | 출처 | 설명 |
|---|---|---|
| `data/processed/교안_page구분.txt` | 통계 기초 강의 교안 (디지털 PDF) | 슬라이드 형식, 수식·차트 포함 |
| `data/processed/역사_page구분.txt` | 국사편찬위원회 역사 교과서 (스캔 PDF) | 이미지·지도·사진 캡션 포함 |

### 공통 구조

- 페이지 구분자: `--- page N ---` 형식으로 각 페이지 시작
- 페이지 내부에 본문과 노이즈가 혼재

---

### 2-1. 교안 (통계 기초 교안) 노이즈 패턴

| 유형 | 예시 | 발생 위치 |
|---|---|---|
| 저작권 고지 | `이 자료는 Elixirr의 사전 서면 승인 없이...할 수 없습니다.` | page 1 (1회) |
| 저작권 표시 | `Copyright Elixir` | page 1 (1회) |
| 저자명 | `강명호` | page 1 (1회) |
| 목차 탐색 바 | `통계의 기본 개념 기술 통계 확률과 분포 추정과 가설검정 상관분석` | page 2, 7, 21 (반복) |
| 수식 파편 | `02 == (xi-M)2 N 1`, `σν 2π 1 (x-μ)2`, `1.1 1`, `1+2+3` | 수식이 있는 페이지 전반 |
| 차트 레이블 | `Positive Skew`, `Symmetrical Distribution`, `Median`, `Mean Mode` | 시각화 페이지 |
| 분포 이름 목록 | `Uniform`, `Bernoulli`, `Binomial`, ... | 차트 이미지 내부 텍스트 |
| URL | `https://365datascience.com/...`, `https://medium.com/...` | 출처 페이지 |

**핵심 문제**: 슬라이드 수식이 깨진 채로 파싱되어 단편적 수식 문자열이 곳곳에 흩어져 있음.  
수식 자체는 의미를 가지나, 파편화된 형태로는 오히려 노이즈로 작용함.

---

### 2-2. 역사 (교과서) 노이즈 패턴

| 유형 | 예시 | 발생 위치 |
|---|---|---|
| 반복 헤더 | `국사편찬위원회` | 매 페이지 시작 |
| 페이지 번호+챕터 푸터 | `124 V. 조선의 성립과 발전`, `130 v. 조선의 성립과 발전` | 매 페이지 끝 |
| 절 번호+페이지 푸터 | `1. 조선의 성립 127`, `1. 조선의 성립 \|129` | 매 페이지 끝 |
| 한자/한문 단독 줄 | `門南鎮`, `圖全善首`, `天 官者`, `灸無春秋節記注` | 고문서·비문 이미지 |
| 지도 파편 텍스트 | `모스크바 공국`, `카진 한국`, `바이칼 호`, `D`, `白`, `●`, `0` | 지도 이미지 |
| 단일 문자/기호 줄 | `D`, `0`, `Op`, `多`, `ON`, `美`, `中`, `#`, `製 ~` | 이미지 내부 OCR |
| 사진 캡션 | `해시계(앙부일구) 세종 때 처음 만들어...`, `교지 왕이 신하에게 벼슬...` | 사진 아래 설명 |
| 학습 목표 질문 | `1 조선을 세운 사람들의 국가 운영 방향은 ?` | 절 시작 |

**핵심 문제**: 스캔 PDF의 OCR 특성상 이미지(지도·고문서·사진) 내부 텍스트가 본문과 섞여 있음.  
지도의 경우 짧은 지명들이 단독 줄로 파편화되어 있으며, 한자 줄은 의미 복원이 어려움.

---

## 3. 정제 계획

### 결과 저장 구조

각 단계가 끝날 때마다 중간 결과를 `preprocessing/result/` 하위 폴더에 저장한다.  
단계별 결과를 보존함으로써 특정 단계에서 문제 발생 시 해당 단계부터 재실행할 수 있다.

```
preprocessing/result/
├── step1_di_role/          # DI role 필터링 결과
│   ├── 교안_step1.txt
│   └── 역사_step1.txt
├── step2_ftfy/             # 유니코드 복원 결과
│   ├── 교안_step2.txt
│   └── 역사_step2.txt
├── step3_nfc/              # NFC 정규화 결과
│   ├── 교안_step3.txt
│   └── 역사_step3.txt
├── step4_regex/            # 정규식 제거 결과
│   ├── 교안_step4.txt
│   └── 역사_step4.txt
├── step5_cjk_lang/         # CJK 필터 + 언어 감지 결과
│   ├── 교안_step5.txt
│   └── 역사_step5.txt
├── step6_dedup/            # 중복 제거 결과
│   ├── 교안_step6.txt
│   └── 역사_step6.txt
├── step7_korean/           # (선택) 한국어 특화 처리 결과
│   ├── 교안_step7.txt
│   └── 역사_step7.txt
└── final/                  # GraphRAG 인풋 최종 결과
    ├── 교안.txt
    └── 역사.txt
```

각 단계의 저장은 아래 공통 함수를 사용한다.

```python
from pathlib import Path

RESULT_ROOT = Path('preprocessing/result')

def save_step(text: str, filename: str, step: str):
    out_dir = RESULT_ROOT / step
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    out_path.write_text(text, encoding='utf-8')
    print(f"[{step}] 저장 완료: {out_path}  ({len(text.splitlines())}줄)")
```

---

### 처리 흐름

```
PDF 추출 단계
  └── 1단계: DI paragraph role 기반 헤더/푸터 차단   → result/step1_di_role/
        └── 2단계: ftfy — 깨진 유니코드·수식 문자 복원  → result/step2_ftfy/
              └── 3단계: unicodedata — NFC 정규화       → result/step3_nfc/
                    └── 4단계: re — 정규식 제거          → result/step4_regex/
                          └── 5단계: CJK 필터 + langdetect → result/step5_cjk_lang/
                                └── 6단계: 중복 줄 제거    → result/step6_dedup/
                                      └── 7단계: (선택) 한국어 특화 처리 → result/step7_korean/
                                            └── 8단계: GraphRAG 포맷 변환 → result/final/
```

---

### 1단계: DI paragraph role 활용 — 추출 단계 차단

Azure Document Intelligence `prebuilt-layout`은 각 단락에 `role` 속성을 부여한다.  
정규식으로 사후 제거하기 전에, **추출 시점에 role 기반 필터링**을 적용하면 헤더·푸터 노이즈의 대부분을 원천 차단할 수 있다.

| role 값 | 의미 | 처리 방침 |
|---|---|---|
| `pageHeader` | 페이지 상단 반복 텍스트 (예: `국사편찬위원회`) | 제거 |
| `pageFooter` | 페이지 하단 반복 텍스트 (예: `124 V. 조선의 성립과 발전`) | 제거 |
| `pageNumber` | 단독 페이지 번호 | 제거 |
| `title` | 섹션 제목 | 보존 |
| `body` | 본문 단락 | 보존 |
| `None` | role 미분류 | 보존 (규칙으로 추가 처리) |

```python
EXCLUDE_ROLES = {"pageHeader", "pageFooter", "pageNumber"}

body_paragraphs = [
    p.content for p in result.paragraphs
    if p.role not in EXCLUDE_ROLES
]
text = '\n'.join(body_paragraphs)
save_step(text, '교안_step1.txt', 'step1_di_role')
```

> role이 `None`인 단락도 본문일 수 있으므로 제거하지 않고 이후 단계로 넘긴다.

---

### 2단계: `ftfy` — 깨진 유니코드·수식 문자 정상화

- **용도**: PDF 파싱 과정에서 잘못 인코딩된 특수문자·수학 기호를 올바른 유니코드로 복원
- **설치**: `pip install ftfy`

```python
import ftfy

text = ftfy.fix_text(text)
# "σν 2Ï€" → "σν 2π"
# "â€œquoteâ€" → '"quote"'
save_step(text, '교안_step2.txt', 'step2_ftfy')
```

주요 처리 대상:
- 수식 기호 깨짐: `Ï€` → `π`, `Î±` → `α`, `â‰¤` → `≤`
- mojibake(인코딩 혼용): CP1252 → UTF-8 오변환 복원
- 불필요한 BOM, 제어 문자 제거

> `ftfy` 적용 후에도 의미 없는 수식 파편(예: `1 1 + 2 + 3`)이 남을 수 있으며, 이는 4단계 `re`에서 처리한다.

---

### 3단계: `unicodedata` — NFC 정규화

- **용도**: 동일 문자가 NFD/NFC 등 다른 유니코드 형태로 표현된 경우 통일. 이후 `re` 정규식 매칭이 형태에 따라 달라지는 문제를 사전 차단
- **설치**: 표준 라이브러리

```python
import unicodedata

text = unicodedata.normalize('NFC', text)
save_step(text, '교안_step3.txt', 'step3_nfc')
```

---

### 4단계: `re` — 기본 특수문자·이메일·URL 정규식 제거

- **용도**: URL, 이메일 주소, 특수기호 줄, 짧은 노이즈 줄 등 패턴이 명확한 노이즈를 정규식으로 일괄 제거
- **설치**: 표준 라이브러리 (별도 설치 불필요)

```python
import re

rules = [
    (r'https?://\S+',                                              ''),    # URL 제거
    (r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',       ''),    # 이메일 제거
    (r'^\s*[^\w가-힣]{0,3}\s*$',                                  None),  # 특수기호만 있는 줄 삭제
    (r'^\s*.{1}\s*$',                                             None),  # 1글자 이하 단독 줄 삭제 — 2글자 한글 키워드 오탐 방지
    (r'^\s*[\d\s\+\-\=\(\)\.\^\/\*σνπμωΣ²₂]{1,25}\s*$',         None),  # 수식 파편 삭제
    (r'^\s*[●○◆◇★☆■□▲△▼◎⊙。▷®▶]\s*\S.{0,6}\s*$',              None),  # 지도 기호+짧은 지명 — •(불릿) 제외
    (r'.*[ㄱ-ㅎㅏ-ㅣ].*',                                         None),  # 자음/모음 단독 포함 줄
    (r'\n{3,}',                                                   '\n\n'),# 연속 빈 줄 정리
]

def apply_rules(text):
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if line.startswith('--- page'):  # 페이지 구분자 보존
            cleaned.append(line)
            continue
        skip = False
        for pattern, replacement in rules:
            if replacement is None:
                if re.fullmatch(pattern, line):
                    skip = True
                    break
            else:
                line = re.sub(pattern, replacement, line)
        if not skip:
            cleaned.append(line)
    return '\n'.join(cleaned)

text = apply_rules(text)
save_step(text, '교안_step4.txt', 'step4_regex')
```

| 규칙 | 정규식 | 처리 |
|---|---|---|
| URL 제거 | `https?://\S+` | 인라인 치환 |
| 이메일 제거 | `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}` | 인라인 치환 |
| 특수기호 줄 제거 | `^\s*[^\w가-힣]{0,3}\s*$` | 줄 삭제 |
| **1글자 이하** 단독 줄 제거 | `^\s*.{1}\s*$` | 줄 삭제 — 2글자 한글 키워드(`목적`·`개요`) 보존 |
| 수식 파편 줄 제거 | `^\s*[\d\s\+\-\=\(\)\.\^\/\*σνπμωΣ²₂]{1,25}\s*$` | 줄 삭제 |
| 지도 기호+짧은 지명 | `^\s*[●○◆◇★☆■□▲△▼◎⊙。▷®▶]\s*\S.{0,6}\s*$` | 줄 삭제 — `•`(불릿) 제외 |
| 자음/모음 단독 포함 줄 | `.*[ㄱ-ㅎㅏ-ㅣ].*` | 줄 삭제 |
| 연속 빈 줄 정리 | `\n{3,}` | `\n\n`으로 치환 |

---

### 5단계: `unicodedata` CJK 필터 + `langdetect` — 언어 필터

#### `unicodedata` — CJK 비율 필터

- **용도**: 한자(CJK) 비율 계산으로 한자·한문 단독 줄 제거. 4단계 이후 남은 줄에만 적용하여 불필요한 연산 최소화

```python
def is_hanja_noise(line):
    stripped = line.strip()
    if not stripped:
        return False
    cjk_count = sum(1 for c in stripped if '一' <= c <= '鿿')
    return cjk_count / len(stripped) > 0.6  # 한자 비율 60% 초과 → 노이즈
```

#### `langdetect` — 언어 감지 기반 비한국어 줄 필터

- **용도**: 줄 단위 언어 감지로 한국어가 아닌 줄(고문서 한문, 외국어 파편)을 필터링
- **설치**: `pip install langdetect`

```python
from langdetect import detect, LangDetectException

def is_non_korean(line):
    stripped = line.strip()
    if len(stripped) < 10:
        return False
    # 한글 음절 2개 이상이면 영문 병기 표현이어도 한국어 줄로 간주
    # — 예: '모집단 (Population)' → 한글 음절 3개 → 보존
    korean_syllables = sum(1 for c in stripped if '가' <= c <= '힣')
    if korean_syllables >= 2:
        return False
    try:
        return detect(stripped) != 'ko'
    except LangDetectException:
        return True  # 감지 실패 = 노이즈 가능성 높음

lines = text.splitlines()
text = '\n'.join(
    l for l in lines
    if not is_hanja_noise(l) and not is_non_korean(l)
)
save_step(text, '교안_step5.txt', 'step5_cjk_lang')
```

---

### 6단계: 중복 줄 제거

- **용도**: 동일 줄이 여러 페이지에 반복 등장하는 경우(예: 교안 목차 탐색 바, 교과서 헤더 잔류분) GraphRAG 그래프 구성 시 같은 내용이 중복 노드로 생성되는 것을 방지
- 페이지 구분자(`--- page N ---`)는 중복 제거 대상에서 제외

```python
seen = set()
deduped = []
for line in text.splitlines():
    if line.startswith('--- page') or line not in seen:
        deduped.append(line)
        seen.add(line)

text = '\n'.join(deduped)
save_step(text, '교안_step6.txt', 'step6_dedup')
```

---

### 보존 대상 (삭제하지 않을 패턴)

- `--- page N ---`: 페이지 청크 기준으로 활용하므로 유지 (8단계에서 최종 처리)
- 학습 목표 질문 (`1 조선을 세운 사람들의...`): 내용과 연관성이 있으므로 우선 보존
- 사진 캡션: 문화재·유물 설명은 내용적 가치 있음 → **별도 태그** 부착 검토
- 박스형 보충 설명 (`| 한양 천도 |`, `| 직전법 |`): 본문 보완 정보 → 보존

---

### 7단계 (선택): 한국어 특화 라이브러리

앞선 단계로 해결되지 않는 경우에만 적용. 처리 비용이 높으므로 마지막 우선순위.

| 라이브러리 | 용도 | 설치 |
|---|---|---|
| **`kiwipiepy`** | 형태소 분석 → 명사·동사가 0개인 줄을 노이즈로 판단 | `pip install kiwipiepy` |
| **`PyKoSpacing`** | OCR로 붙어 나온 띄어쓰기 복원 | `pip install pykosspacing` |
| **`kss`** | 문장 경계 분리 (페이지 내 문장 단위 청크 구성 시) | `pip install kss` |

```python
from kiwipiepy import Kiwi

kiwi = Kiwi()

def has_meaningful_morpheme(line):
    tokens = kiwi.analyze(line)[0][0]
    pos_tags = {t.tag for t in tokens}
    return bool(pos_tags & {'NNG', 'NNP', 'NNB', 'VV', 'VA'})

lines = [l for l in text.splitlines() if l.startswith('--- page') or has_meaningful_morpheme(l)]
text = '\n'.join(lines)
save_step(text, '교안_step7.txt', 'step7_korean')
```

---

### 8단계: GraphRAG 인풋 포맷 변환

- **용도**: GraphRAG는 `.txt` 파일 단위로 문서를 읽음. `--- page N ---` 구분자를 그대로 두면 일반 텍스트로 처리되어 그래프 구성에 노이즈가 됨
- 페이지 구분자를 제거하고, 단일 파일 또는 페이지별 파일로 분리해 저장

```python
# 옵션 A: 구분자 제거 후 단일 txt 저장 (GraphRAG가 자체 청킹 담당)
clean_text = re.sub(r'--- page \d+ ---\n?', '', text).strip()
save_step(clean_text, '교안.txt', 'final')

# 옵션 B: 페이지별 개별 txt 분리 (페이지 단위가 청크 기준)
pages = re.split(r'--- page \d+ ---\n?', text)
for i, page_text in enumerate(pages, start=1):
    if page_text.strip():
        save_step(page_text.strip(), f'교안_page{i:03d}.txt', 'final')
```

> **옵션 A vs B**: GraphRAG 청킹 전략에 따라 선택.  
> 단일 파일이면 GraphRAG가 토큰 기준으로 자동 분할하고, 페이지별 분리 시 페이지 경계가 청크 경계가 됨.

---

## 4. 불확실 케이스 및 향후 과제

| 이슈 | 설명 | 대응 방향 |
|---|---|---|
| 수식 보존 여부 | 파편화된 수식은 노이즈지만, 수식 자체는 본문 내용 | LaTeX 변환 파이프라인 별도 검토 |
| 사진 캡션 구분 | 본문과 캡션을 자동 구분하는 규칙이 불명확 | `(소장)`, `이다.`로 끝나는 짧은 서술형 문장 패턴 활용 |
| 지도 텍스트 | 일부는 역사적 지명으로 의미 있음 | 지명 사전 기반 필터링 검토 |
| 한자 줄 | 고문서 이미지에서 파생, 의미 복원 불가 | 전량 삭제 (복원 비용 > 이익) |
| DI role 미분류 | `None` role 단락 중 실제 헤더·푸터가 섞일 수 있음 | 정규식 규칙으로 보완 |
