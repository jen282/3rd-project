import json
import re
import unicodedata
from pathlib import Path

import ftfy
from langdetect import detect, LangDetectException

RESULT_ROOT = Path('preprocessing/result')

DI_JSON = {
    '교안': Path('extract/document-intelligence-layout/result_png/read.json'),
    '역사': Path('extract/document-intelligence-layout/result_scan/read.json'),
}

EXCLUDE_ROLES = {'pageHeader', 'pageFooter', 'pageNumber'}

REGEX_RULES = [
    (r'https?://\S+',                                        ''),
    (r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', ''),
    (r'^\s*[^\w가-힣]{0,3}\s*$',                             None),  # 특수기호만 있는 줄
    (r'^\s*.{1}\s*$',                                        None),  # 1글자 이하 단독 줄 (2글자 한글 키워드 보존)
    (r'^\s*[\d\s\+\-\=\(\)\.\^\/\*σνπμωΣ²₂]{1,25}\s*$',   None),  # 수식 파편
    (r'^\s*[●○◆◇★☆■□▲△▼◎⊙。▷®▶]\s*\S.{0,6}\s*$',         None),  # 지도 기호+짧은 지명 (예: ●회령, ○갑산) — •(불릿) 제외
    (r'.*[ㄱ-ㅎㅏ-ㅣ].*',                                    None),  # 자음/모음 단독 포함 줄 (예: 경성 ㅇ)
]


# ── 공통 유틸 ──────────────────────────────────────────────

def save_step(text: str, filename: str, step: str) -> str:
    out_dir = RESULT_ROOT / step
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    out_path.write_text(text, encoding='utf-8')
    non_empty = len([l for l in text.splitlines() if l.strip()])
    print(f'  [{step}] {filename} 저장 ({non_empty}줄)')
    return text


def is_page_sep(line: str) -> bool:
    return bool(re.match(r'^--- page \d+ ---$', line))


# ── 단계별 함수 ────────────────────────────────────────────

def step1_di_role(name: str) -> str:
    """DI paragraph role 기반 헤더/푸터 차단."""
    data = json.load(open(DI_JSON[name], encoding='utf-8'))
    out = []
    for page in data:
        out.append(f"--- page {page['page']} ---")
        paragraphs = page.get('paragraphs') or []
        if paragraphs:
            for p in paragraphs:
                if p.get('role') not in EXCLUDE_ROLES:
                    out.append(p['content'])
        else:
            for line in page.get('lines', []):
                out.append(line['content'])
        out.append('')
    return save_step('\n'.join(out), f'{name}_step1.txt', 'step1_di_role')


def step2_ftfy(text: str, name: str) -> str:
    """깨진 유니코드·수식 문자 복원."""
    return save_step(ftfy.fix_text(text), f'{name}_step2.txt', 'step2_ftfy')


def step3_nfc(text: str, name: str) -> str:
    """NFC 정규화 — re 적용 전 문자 표현 통일."""
    return save_step(unicodedata.normalize('NFC', text), f'{name}_step3.txt', 'step3_nfc')


def step4_regex(text: str, name: str) -> str:
    """URL·이메일·특수기호·수식 파편 정규식 제거."""
    cleaned = []
    for line in text.splitlines():
        if is_page_sep(line) or line.strip() == '':
            cleaned.append(line)
            continue
        skip = False
        for pattern, replacement in REGEX_RULES:
            if replacement is None:
                if re.fullmatch(pattern, line):
                    skip = True
                    break
            else:
                line = re.sub(pattern, replacement, line)
        if not skip:
            cleaned.append(line)
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(cleaned))
    return save_step(text, f'{name}_step4.txt', 'step4_regex')


def is_hanja_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    cjk = sum(1 for c in stripped if '一' <= c <= '鿿')
    return cjk / len(stripped) > 0.6


def is_non_korean(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 10:
        return False
    # 한글 음절이 2개 이상이면 영문 병기 표현이어도 한국어 줄로 간주
    korean_syllables = sum(1 for c in stripped if '가' <= c <= '힣')
    if korean_syllables >= 2:
        return False
    try:
        return detect(stripped) != 'ko'
    except LangDetectException:
        return True


def step5_cjk_lang(text: str, name: str) -> str:
    """CJK 비율 필터 + langdetect 비한국어 줄 제거."""
    lines = [
        l for l in text.splitlines()
        if is_page_sep(l) or l.strip() == ''
        or (not is_hanja_noise(l) and not is_non_korean(l))
    ]
    return save_step('\n'.join(lines), f'{name}_step5.txt', 'step5_cjk_lang')


def step6_dedup(text: str, name: str) -> str:
    """페이지 간 중복 줄 제거 (페이지 구분자 제외)."""
    seen: set = set()
    deduped = []
    for line in text.splitlines():
        if is_page_sep(line) or line.strip() == '' or line not in seen:
            deduped.append(line)
            seen.add(line)
    return save_step('\n'.join(deduped), f'{name}_step6.txt', 'step6_dedup')


def step8_graphrag(text: str, name: str) -> str:
    """페이지 구분자 제거 후 GraphRAG 인풋용 단일 txt 저장."""
    clean = re.sub(r'--- page \d+ ---\n?', '', text).strip()
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    return save_step(clean, f'{name}.txt', 'final')


# ── 파이프라인 ─────────────────────────────────────────────

def run(name: str):
    print(f'\n{"=" * 50}')
    print(f'[{name}] 정제 시작')
    print('=' * 50)
    text = step1_di_role(name)
    text = step2_ftfy(text, name)
    text = step3_nfc(text, name)
    text = step4_regex(text, name)
    text = step5_cjk_lang(text, name)
    text = step6_dedup(text, name)
    step8_graphrag(text, name)
    print(f'[{name}] 완료')


if __name__ == '__main__':
    run('교안')
    run('역사')
