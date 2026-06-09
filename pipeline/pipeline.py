"""
전처리 파이프라인: PDF → Azure Content Understanding → NLP → OpenAI 목차 추출

실행 예시:
  python pipeline.py --pdf "data/raw/통계기초.pdf"
  python pipeline.py --pdf "data/raw/통계기초.pdf" --debug
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    import ftfy
except ImportError:
    ftfy = None

try:
    from kiwipiepy import Kiwi
except ImportError:
    Kiwi = None

try:
    import fitz  # pymupdf
except ImportError:
    fitz = None

# ── 경로 설정 ──────────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).parent
RESULT_DIR  = SCRIPT_DIR / "result"
ENV_PATH    = SCRIPT_DIR.parent / ".env"
PIPELINE_MD = SCRIPT_DIR / "pipeline.md"

load_dotenv(ENV_PATH)

CU_ENDPOINT    = os.environ.get("CONTENT_UNDERSTANDING_ENDPOINT", "").rstrip("/")
CU_KEY         = os.environ.get("CONTENT_UNDERSTANDING_KEY", "")
OAI_ENDPOINT   = os.environ.get("OPEN_AI_ENDPOINT", "").rstrip("/")
OAI_KEY        = os.environ.get("OPEN_AI_KEY", "")
OAI_DEPLOYMENT = os.environ.get("OPEN_AI_DEPLOYMENT_NAME", "")

API_VER     = "2024-12-01-preview"
ANALYZER_ID = "pdf-content-extractor"
_BASE_HDR   = {"Ocp-Apim-Subscription-Key": CU_KEY}
_JSON_HDR   = {**_BASE_HDR, "Content-Type": "application/json"}

MAX_TEXT_CHARS      = 40000  # LLM 입력 최대 길이 (토큰 한도 대응)
SCAN_DETECT_PAGES   = 5      # 스캔 여부 판단에 사용할 페이지 수
SCAN_CHAR_THRESHOLD = 100    # 페이지당 평균 글자 수가 이 값 미만이면 스캔으로 판단


# ── 스캔 PDF 자동 감지 ────────────────────────────────────────────────────────

def detect_scan(pdf_path: Path) -> bool:
    """페이지당 평균 추출 글자 수로 스캔 여부 판단. pymupdf 없으면 None 반환."""
    if not fitz:
        return None

    doc   = fitz.open(str(pdf_path))
    pages = min(SCAN_DETECT_PAGES, len(doc))
    total = sum(len(doc[i].get_text().strip()) for i in range(pages))
    doc.close()

    avg = total / pages if pages else 0
    return avg < SCAN_CHAR_THRESHOLD


# ── 버전 관리 ──────────────────────────────────────────────────────────────────

def get_output_dir(pdf_name: str) -> tuple[Path, str]:
    """새 버전 폴더 생성. 이미 존재하면 번호 증가."""
    stem = Path(pdf_name).stem
    v = 1
    while True:
        out = RESULT_DIR / f"{stem}_v{v}"
        if not out.exists():
            out.mkdir(parents=True)
            return out, f"v{v}"
        v += 1


def find_existing_raw(pdf_name: str) -> Path | None:
    """이전 버전 폴더에서 raw_response.json 검색 (최신 버전 우선)."""
    stem = Path(pdf_name).stem
    found = None
    v = 1
    while True:
        folder = RESULT_DIR / f"{stem}_v{v}"
        if not folder.exists():
            break
        raw = folder / "raw_response.json"
        if raw.exists():
            found = raw
        v += 1
    return found


# ── STEP 1: API 추출 ───────────────────────────────────────────────────────────

def _ensure_analyzer() -> None:
    url  = f"{CU_ENDPOINT}/contentunderstanding/analyzers/{ANALYZER_ID}?api-version={API_VER}"
    body = {
        "description": "PDF 텍스트·이미지·표·다이어그램 추출기",
        "scenario": "document",
        "config": {
            "returnDetails": True,
            "enableOcr":     True,
            "enableLayout":  True,
            "enableBarcode": False,
            "enableFormula": True,
        },
    }
    resp = requests.put(url, headers=_JSON_HDR, json=body, timeout=60)
    if resp.status_code not in (200, 201, 409):
        resp.raise_for_status()


def _submit_analyze(pdf_path: Path) -> str:
    url  = f"{CU_ENDPOINT}/contentunderstanding/analyzers/{ANALYZER_ID}:analyze?api-version={API_VER}"
    hdrs = {**_BASE_HDR, "Content-Type": "application/pdf"}
    resp = requests.post(url, headers=hdrs, data=pdf_path.read_bytes(), timeout=120)
    resp.raise_for_status()
    result_url = resp.headers.get("Operation-Location")
    if not result_url:
        raise RuntimeError(f"Operation-Location 헤더 없음: {dict(resp.headers)}")
    return result_url


def _poll(result_url: str, timeout: int = 900) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        resp    = requests.get(result_url, headers=_BASE_HDR, timeout=30)
        resp.raise_for_status()
        data    = resp.json()
        status  = data.get("status", "unknown")
        elapsed = int(time.time() - start)
        print(f"  상태: {status:12s}  ({elapsed}s 경과)", end="\r", flush=True)
        if status == "Succeeded":
            print()
            return data
        if status in ("Failed", "Canceled"):
            raise RuntimeError(f"분석 실패: {json.dumps(data, ensure_ascii=False)[:300]}")
        time.sleep(5)
    raise TimeoutError(f"{timeout}초 초과")


def step1_extract(pdf_path: Path, out_dir: Path) -> dict:
    print("\n[STEP 1] API 추출")

    # 이전 버전에 raw_response.json이 있으면 재사용
    existing = find_existing_raw(pdf_path.name)
    if existing:
        print(f"  기존 raw_response.json 재사용 → {existing}")
        data = json.loads(existing.read_text(encoding="utf-8"))
        # 현재 버전 폴더에도 복사 저장
        (out_dir / "raw_response.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return data

    print("  Azure API 호출 중...")
    _ensure_analyzer()
    result_url = _submit_analyze(pdf_path)
    data = _poll(result_url)
    (out_dir / "raw_response.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  → raw_response.json 저장")
    return data


# ── STEP 2: 텍스트 추출 (메모리) ──────────────────────────────────────────────

def step2_extract_text(data: dict, out_dir: Path, is_scan: bool, debug: bool) -> str:
    print("\n[STEP 2] 텍스트 추출")

    contents = data.get("result", {}).get("contents", [])
    md_parts = []
    for c in contents:
        md = c.get("markdown") or c.get("markdownContent", "")
        if md:
            s = c.get("startPageNumber", "?")
            e = c.get("endPageNumber",   "?")
            md_parts.append(f"<!-- page {s}–{e} -->\n{md}")

    combined_md = "\n\n---\n\n".join(md_parts)

    if debug:
        (out_dir / "content.md").write_text(combined_md, encoding="utf-8")
        print("  [debug] content.md 저장")

    # 텍스트 정제
    text = combined_md
    text = re.sub(r'<table>.*?</table>',   '', text, flags=re.DOTALL)
    text = re.sub(r'<figure>.*?</figure>', '', text, flags=re.DOTALL)
    text = re.sub(r'<!--\s*PageBreak\s*-->', '\n\n', text)  # PageBreak → 단락 구분 (먼저 처리)
    text = re.sub(r'<!--.*?-->',           '', text, flags=re.DOTALL)
    text = re.sub(r'^---$',               '',  text, flags=re.MULTILINE)  # 페이지 구분자 제거
    text = re.sub(r'\$\$.*?\$\$',         '', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$\n]+?\$',        '', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[•·]\s*',   '', text, flags=re.MULTILINE)
    if is_scan:
        text = re.sub(r'[|]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    if debug:
        txt_dir = out_dir / "txt"
        txt_dir.mkdir(exist_ok=True)
        (txt_dir / "content.txt").write_text(text, encoding="utf-8")
        print("  [debug] txt/content.txt 저장")

    print(f"  추출 완료 ({len(text):,} chars)")
    return text


# ── STEP 3: NLP 전처리 (메모리) ───────────────────────────────────────────────

def step3_nlp(text: str, out_dir: Path, is_scan: bool, debug: bool) -> str:
    print("\n[STEP 3] NLP 전처리")

    nlp_dir = out_dir / "nlp"
    if debug:
        nlp_dir.mkdir(exist_ok=True)

    # 1단계: 인코딩 교정 + 노이즈 제거
    if ftfy:
        text = ftfy.fix_text(text)
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'<!--.*?-->',  '',  text, flags=re.DOTALL)  # PageBreak는 step2에서 처리됨
    text = re.sub(r'<[^>]+>',    ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'[ \t]+', ' ', text)

    if debug:
        (nlp_dir / "step1_clean.txt").write_text(text, encoding="utf-8")

    # 2단계: 끊긴 문장 병합
    skip_merge = re.compile(r'^(\s*#|\s*\*|\s*-|\s*>|\|)')
    end_pat    = re.compile(r'(다|요|까|\.|\?|!|:)\s*$')
    lines, merged_lines, current = text.split('\n'), [], ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                merged_lines.append(current)
                current = ""
            merged_lines.append("")
            continue
        if skip_merge.match(stripped):
            if current:
                merged_lines.append(current)
                current = ""
            merged_lines.append(stripped)
            continue
        current = (current + " " + stripped) if current else stripped
        if end_pat.search(current):
            merged_lines.append(current)
            current = ""

    if current:
        merged_lines.append(current)
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(merged_lines))

    if debug:
        (nlp_dir / "step2_merged.txt").write_text(text, encoding="utf-8")

    # 3단계: Kiwi 문장 분리
    if not Kiwi:
        print("  [주의] kiwipiepy 없음 → 3·4단계 스킵")
        return text

    kiwi      = Kiwi()
    sentences = []
    for para in text.split('\n'):
        if not para.strip():
            sentences.append("")
            continue
        if re.match(r'^(#|\|)', para.strip()):
            sentences.append(para.strip())
        else:
            for s in kiwi.split_into_sents(para):
                sentences.append(s.text)
    text = '\n'.join(sentences)

    if debug:
        (nlp_dir / "step3_kiwi_sents.txt").write_text(text, encoding="utf-8")

    # 4단계: 띄어쓰기 교정 (스캔 PDF만)
    if is_scan:
        print("  [4단계] 띄어쓰기 교정 (스캔 PDF)")
        spaced = []
        for s in sentences:
            if not s.strip() or re.match(r'^(#|\|)', s.strip()):
                spaced.append(s)
            elif len(s) > 5:
                spaced.append(kiwi.space(s, reset_whitespace=True))
            else:
                spaced.append(s)
        text = '\n'.join(spaced)
        if debug:
            (nlp_dir / "step4_spaced.txt").write_text(text, encoding="utf-8")
    else:
        print("  [4단계 생략] 디지털 PDF")

    print(f"  전처리 완료 ({len(text):,} chars)")
    return text


# ── STEP 4: LLM 호출 ──────────────────────────────────────────────────────────

def step4_llm(text: str, pdf_name: str, out_dir: Path) -> None:
    print("\n[STEP 4] LLM 호출 (목차 추출)")

    from openai import OpenAI

    client = OpenAI(
        base_url=OAI_ENDPOINT,
        api_key=OAI_KEY,
    )

    if len(text) > MAX_TEXT_CHARS:
        raise RuntimeError(
            f"[중단] 텍스트가 {MAX_TEXT_CHARS:,}자를 초과했습니다 (현재 {len(text):,}자). "
            "전처리 결과를 확인하거나 MAX_TEXT_CHARS 값을 조정하세요."
        )
    input_text = text

    system_msg = (
        "당신은 한국어 교육 문서를 분석하는 전문가입니다. "
        "주어진 텍스트에서 문서의 핵심 목차 항목을 추출하세요."
    )
    user_msg = (
        f"아래는 '{pdf_name}'에서 추출한 텍스트입니다.\n"
        "이 문서의 목차 항목을 5개에서 10개 사이로 추출해 주세요.\n"
        "번호와 제목만 간결하게 작성해 주세요.\n"
        "예시 형식:\n1. 통계의 기본 개념\n2. 자료의 수집과 정리\n\n"
        f"[텍스트]\n{input_text}"
    )

    response = client.chat.completions.create(
        model=OAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=800,
    )

    result = response.choices[0].message.content.strip()
    (out_dir / "toc_result.txt").write_text(result, encoding="utf-8")
    print(f"  → toc_result.txt 저장")
    print("\n[목차 추출 결과]")
    print(result)


# ── 시도 기록 (pipeline.md 업데이트) ─────────────────────────────────────────

def append_attempt_log(version: str, pdf_name: str, is_scan: bool, debug: bool, timings: dict) -> None:
    today = date.today().isoformat()
    total = sum(timings.values())
    timing_lines = "\n".join(
        f"  - {label}: {secs:.1f}s" for label, secs in timings.items()
    )
    entry = (
        f"\n---\n\n"
        f"### {version} — {pdf_name}\n\n"
        f"- 날짜: {today}\n"
        f"- PDF: {pdf_name} ({'스캔' if is_scan else '디지털'})\n"
        f"- 디버그: {'O (중간 파일 저장)' if debug else 'X'}\n"
        f"- 소요시간: 총 {total:.1f}s\n"
        f"{timing_lines}\n"
        f"- 변경사항: (직접 기입)\n"
    )
    with open(PIPELINE_MD, 'a', encoding='utf-8') as f:
        f.write(entry)
    print(f"\n시도 기록 → pipeline.md 업데이트")


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PDF 전처리 파이프라인")
    parser.add_argument("--pdf",   required=True,      help="PDF 파일 경로")
    parser.add_argument("--scan",  action="store_true", help="스캔 PDF 강제 지정 (미지정 시 자동 감지)")
    parser.add_argument("--debug", action="store_true", help="중간 파일 전체 저장")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[오류] PDF 파일 없음: {pdf_path}")
        sys.exit(1)

    # 스캔 여부 결정: --scan 명시 > 자동 감지 > 경고 후 디지털로 간주
    if args.scan:
        is_scan = True
        scan_source = "수동 지정"
    else:
        detected = detect_scan(pdf_path)
        if detected is None:
            print("[주의] pymupdf 없음 → 스캔 자동 감지 불가. 디지털로 간주합니다. (--scan 으로 직접 지정 가능)")
            is_scan = False
            scan_source = "기본값 (감지 불가)"
        else:
            is_scan = detected
            scan_source = "자동 감지"

    out_dir, version = get_output_dir(pdf_path.name)

    print(f"\n{'='*55}")
    print(f"PDF    : {pdf_path.name}")
    print(f"출력   : {out_dir}")
    print(f"유형   : {'스캔' if is_scan else '디지털'} ({scan_source})")
    print(f"디버그 : {'O' if args.debug else 'X'}")
    print(f"{'='*55}")

    timings = {}
    try:
        t = time.time(); data = step1_extract(pdf_path, out_dir);                          timings["STEP1 API 추출"]    = time.time() - t
        t = time.time(); text = step2_extract_text(data, out_dir, is_scan, args.debug);    timings["STEP2 텍스트 추출"] = time.time() - t
        t = time.time(); text = step3_nlp(text, out_dir, is_scan, args.debug);             timings["STEP3 NLP 전처리"]  = time.time() - t
        t = time.time(); step4_llm(text, pdf_path.name, out_dir);                          timings["STEP4 LLM 호출"]    = time.time() - t
    except (RuntimeError, TimeoutError) as e:
        print(f"\n{e}")
        sys.exit(1)
    append_attempt_log(version, pdf_path.name, is_scan=is_scan, debug=args.debug, timings=timings)

    print(f"\n{'='*55}")
    print(f"완료 → {out_dir}")
    print(f"{'='*55}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
