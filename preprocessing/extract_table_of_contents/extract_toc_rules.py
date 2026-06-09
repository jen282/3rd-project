"""
Rule-based table of contents extractor for Korean documents.

Detection rules (heading levels):
  L1 - Roman numeral chapter  : "V 조선의 성립과 발전"
  L2 - Numbered section       : "1. 조선의 성립"
  L3 - Numbered subsection    : "1 조선의 성립" or "1\n조선을 세운..."
  L4 - Short standalone title : "조선의 건국", "한양 천도"

Post-extraction filters (공통):
  - 페이지 헤더/푸터    : "130 v. 조선의..."
  - 마크다운 이스케이프 : \-, 1\.
  - 한글 소목록 마커   : 가., 나., 다., 라.
  - 따옴표 단독 인용   : '경국대전'
  - 이미지 캡션        : ~소장
  - 콜론 정의 레이블   : "중심경향성(Central Tendency) :"
  - 콜론+긴 설명       : "신뢰구간 : 모수가 포함될 것으로..."
  - 단독 괄호 내용     : (진통제 개발의 예시)
  - 괄호 목록 마커     : (다) 김상헌...
  - 문장 절단 단편     : "끝났고, 일"
"""
import re
from pathlib import Path


# ── 1. 본문 문장 종결 패턴 ──────────────────────────────────────────────────
BODY_RE = re.compile(
    r'(하였다|이었다|되었다|있다|없다|한다|된다|이다|했다)\s*$'
    r'|(하여|하고|이며|이나|하며|으며|이고)\s*$'
    r'|(임|됨|함|음)\s*$'       # 학문임, 방법됨, 있음, 받음
    r'|(보자|알자|살펴보자)\s*$'
    r'|고\s*$'                   # 연결어미: 끝났고, 이루어졌고
    r'|\.\s*$'
    r'|,\s*$'
)

# ── 2. 연결어/전치어 패턴 (불릿 설명문 식별용, L4에만 적용) ────────────────
CONNECTIVE_RE = re.compile(
    r'로부터|에서\s|하에서|이거나|있을\s*때|찾을\s*때'
    r'|추출하는|나타내는|평가하는|따르는|독립적인|수치화한'
    r'|간의\s|않으면|않을|않는'
    r'|보다\s'                              # 정규 분포보다 뾰족하고...
    r'|로\s*구분|로\s*분류|로\s*나뉨'      # 변수로 구분
    r'|중심으로|기준으로'                   # μ를 중심으로 대칭
    r'|을\s*나타|에\s*따라'
    r'|적인\s'                              # 극단적인 값이..., 독립적인 변수...
    r'|[μσλπ]'                              # 그리스 문자 (수식 불릿)
)

# ── 3. 추출 후 제거할 노이즈 패턴 ──────────────────────────────────────────
_NOISE = [
    re.compile(r'^\d{3}\s'),                # 페이지 헤더: "130 v. 조선의..."
    re.compile(r'\\'),                       # 마크다운 이스케이프: \-, 1\.
    re.compile(r'^[가나다라마바사아자]\.\s'),  # 한글 소목록: "가. 오륜행실도..."
    re.compile(r"^[‘’'][^‘’']+[‘’']$"),  # 따옴표 인용 (곱슬/직선 모두)
    re.compile(r'소장'),                      # 이미지 캡션: ~소장
    re.compile(r'현판'),                      # 이미지 캡션: ~현판
    re.compile(r':\s*$'),                    # 콜론으로 끝나는 정의 레이블
    re.compile(r':\s*.{10,}$'),              # 콜론 뒤 긴 설명 (10자 이상)
    re.compile(r'^\(.+\)$'),                 # 단독 괄호: (진통제 개발의 예시)
    re.compile(r'^\([가나다라마바]\)'),       # 괄호 목록 마커: (다) 김상헌...
    re.compile(r',\s*[가-힣]\s*$'),                  # 문장 절단 단편: "끝났고, 일"
    re.compile(r'^,'),                                # 쉼표로 시작: ", 이항분포..."
    re.compile(r'(\s{2,}[가-힣]).+(\s{2,}[가-힣])'), # 다중 이중공백 열거: "붕당  탕평책  실학..."
    re.compile(r'[가나다라마바]\.\s[가-힣]'),          # 내장 한글 소목록: "요지 가. 조선의..."
    re.compile(r'^.{1,4}의\s*$'),                    # 불완전 소유격 단편: "향약의", "왕조의"
    re.compile(r'\([^)]*$'),                          # 닫는 괄호 없는 줄: "확률밀도함수(Probability Density"
    re.compile(r'[ㄱ-ㅎㅏ-ㅣ]'),                      # 단독 자모 포함: "실사구시 ㅣ" (OCR 오류)
]


def is_noise(text):
    return any(pat.search(text) for pat in _NOISE)


# ── 핵심 로직 ───────────────────────────────────────────────────────────────

def split_paragraphs(text):
    return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]


def heading_level(para):
    """Return heading level (1-4) or None."""
    lines = [l.strip() for l in para.splitlines() if l.strip()]
    if not lines:
        return None

    first = lines[0]

    # L1: 로마자 챕터  e.g. "V 조선의 성립과 발전"
    if re.match(r'^[IVXLCDM]{1,4}\s+[가-힣]', first) and len(first) < 40:
        return 1

    # L2: 번호+마침표 절  e.g. "1. 조선의 성립"
    # - 25자 이하, 종결어미 없음, 줄 중간에 가./나. 소목록 없음
    if re.match(r'^\d+\.\s+[가-힣]', first):
        if (len(first) <= 25
                and not BODY_RE.search(first)
                and not re.search(r'[가나다라마바]\.\s', first[3:])):
            return 2

    # L3-a: 2줄 블록 "1\n조선을 세운 사람들의..."
    if len(lines) == 2 and re.match(r'^\d$', lines[0]):
        return 3

    # L3-b: "1 조선의 성립" (짧은 단일 줄, 종결어미 없음)
    if re.match(r'^\d\s+[가-힣]', first) and len(first) < 35:
        if not BODY_RE.search(first):
            return 3

    # L4: 짧은 단독 명사구 (3–30자)
    if len(lines) == 1 and 3 <= len(first) <= 30:
        if not BODY_RE.search(first):
            if re.search(r'[가-힣]', first):
                if not re.match(r'^[\d\s\.,\(\)]+$', first):
                    if not CONNECTIVE_RE.search(first):
                        return 4

    return None


def para_to_text(para):
    lines = [l.strip() for l in para.splitlines() if l.strip()]
    # "1\ntitle" 패턴 → 두 번째 줄이 실제 제목
    if len(lines) == 2 and re.match(r'^\d$', lines[0]):
        return lines[1]
    return lines[0]


def extract_toc(text):
    """Return list of (level, heading_text) — filtered and deduplicated."""
    seen = set()
    results = []
    for para in split_paragraphs(text):
        level = heading_level(para)
        if level is None:
            continue
        heading = para_to_text(para)
        if is_noise(heading):
            continue
        if heading in seen:          # 중복 제거 (슬라이드 반복 제목 등)
            continue
        seen.add(heading)
        results.append((level, heading))
    return results


def format_toc(items):
    return '\n'.join('  ' * (level - 1) + text for level, text in items)


def process_file(src_path, dst_path):
    text = src_path.read_text(encoding='utf-8')
    items = extract_toc(text)
    dst_path.write_text(format_toc(items), encoding='utf-8')
    print(f"[done] {src_path.name}  →  {len(items)} 항목  →  {dst_path.name}")


def main():
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent.parent / 'data' / 'processed'
    out_dir = script_dir / 'result' / 'rule_based'
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        '스캔_줄바꿈해결.txt': '스캔_toc.txt',
        '교안_줄바꿈해결.txt': '교안_toc.txt',
    }

    for src_name, dst_name in targets.items():
        src = data_dir / src_name
        if not src.exists():
            print(f"[skip] {src_name} 파일 없음")
            continue
        process_file(src, out_dir / dst_name)


if __name__ == '__main__':
    main()
