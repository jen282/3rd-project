"""
Azure AI Content Understanding으로 PDF에서 텍스트, 이미지, 표, 다이어그램 추출

결과 폴더:
  result-scan/    ← 국사교과서.pdf (스캔 PDF)
  result-digital/ ← 통계기초.pdf  (디지털 PDF)

각 결과 폴더 구조:
  raw_response.json  ← API 전체 응답
  content.md         ← 추출된 마크다운 (텍스트 + 표 + <figure> 태그 포함)
  summary.json       ← 추출 요약 (페이지 수, figure 수 등)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).parent.parent.parent / ".env")

ENDPOINT    = os.environ["CONTENT_UNDERSTANDING_ENDPOINT"].rstrip("/")
KEY         = os.environ["CONTENT_UNDERSTANDING_KEY"]
API_VER     = "2024-12-01-preview"
ANALYZER_ID = "pdf-content-extractor"

_BASE_HDR = {"Ocp-Apim-Subscription-Key": KEY}
_JSON_HDR = {**_BASE_HDR, "Content-Type": "application/json"}

TARGETS = [
    {
        "pdf":   Path(__file__).parent.parent.parent / "data/raw/국사교과서.pdf",
        "out":   Path(__file__).parent / "result-scan",
        "label": "국사교과서 (스캔)",
    },
    {
        "pdf":   Path(__file__).parent.parent.parent / "data/raw/통계기초.pdf",
        "out":   Path(__file__).parent / "result-digital",
        "label": "통계기초 (디지털)",
    },
]


# ── 분석기 관리 ────────────────────────────────────────────────────────────────

def create_analyzer() -> None:
    """분석기 생성. 409(이미 존재)는 정상으로 처리."""
    url  = f"{ENDPOINT}/contentunderstanding/analyzers/{ANALYZER_ID}?api-version={API_VER}"
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
    if resp.status_code in (200, 201):
        print(f"  분석기 생성 완료 (HTTP {resp.status_code})")
    elif resp.status_code == 409:
        print("  분석기 이미 존재 (HTTP 409), 기존 분석기 사용")
    else:
        print(f"  분석기 생성 응답 HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()


# ── 분석 요청 ──────────────────────────────────────────────────────────────────

def submit_analyze(pdf_path: Path) -> str:
    """PDF 바이너리를 직접 전송 → Operation-Location URL 반환."""
    url  = f"{ENDPOINT}/contentunderstanding/analyzers/{ANALYZER_ID}:analyze?api-version={API_VER}"
    hdrs = {**_BASE_HDR, "Content-Type": "application/pdf"}
    resp = requests.post(url, headers=hdrs, data=pdf_path.read_bytes(), timeout=120)
    if not resp.ok:
        print(f"  분석 요청 실패 HTTP {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    result_url = resp.headers.get("Operation-Location")
    if not result_url:
        raise RuntimeError(f"Operation-Location 헤더 없음: {dict(resp.headers)}")
    return result_url


# ── 폴링 ──────────────────────────────────────────────────────────────────────

def poll_for_result(result_url: str, timeout: int = 900) -> dict:
    """분석 완료까지 5초 간격으로 폴링."""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(result_url, headers=_BASE_HDR, timeout=30)
        resp.raise_for_status()
        data    = resp.json()
        status  = data.get("status", "unknown")
        elapsed = int(time.time() - start)
        print(f"  상태: {status:12s}  ({elapsed}s 경과)", end="\r", flush=True)
        if status == "Succeeded":
            print()
            return data
        if status in ("Failed", "Canceled"):
            raise RuntimeError(f"분석 실패: {json.dumps(data, ensure_ascii=False)[:500]}")
        time.sleep(5)
    raise TimeoutError(f"{timeout}초 초과 — URL: {result_url}")


# ── 결과 저장 ─────────────────────────────────────────────────────────────────

def save_results(data: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # raw_response.json
    (out_dir / "raw_response.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result   = data.get("result", {})
    contents = result.get("contents", [])

    md_parts    = []
    all_figures = []

    for content in contents:
        start_p = content.get("startPageNumber", "?")
        end_p   = content.get("endPageNumber",   "?")
        md      = content.get("markdown", "") or content.get("markdownContent", "")
        if md:
            md_parts.append(f"<!-- page {start_p}–{end_p} -->\n{md}")

        for fig in content.get("figures", []):
            all_figures.append(fig)

        for page in content.get("pages", []):
            for fig in page.get("figures", []):
                all_figures.append(fig)

    # content.md — 텍스트 + 표(<table>) + 다이어그램(<figure>) 마크다운
    (out_dir / "content.md").write_text(
        "\n\n---\n\n".join(md_parts) if md_parts else "(내용 없음)",
        encoding="utf-8",
    )

    # summary.json — figure 위치 메타데이터 (source 좌표 포함)
    summary = {
        "total_content_blocks": len(contents),
        "total_figures":        len(all_figures),
        "figures": [
            {
                "id":      f.get("id"),
                "source":  f.get("source", ""),  # D(page, x0,y0,x1,y1,...) in inches
                "caption": f.get("caption", ""),
            }
            for f in all_figures
        ],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"  저장 완료 → {out_dir}")
    print(f"    콘텐츠 블록: {len(contents)}  |  figure 감지: {len(all_figures)}")


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    print("분석기 생성/확인 중...")
    create_analyzer()

    for target in TARGETS:
        pdf_path = target["pdf"]
        out_dir  = target["out"]
        label    = target["label"]
        size_kb  = pdf_path.stat().st_size / 1024

        print(f"\n{'=' * 55}")
        print(f"[{label}]  {pdf_path.name}  ({size_kb:.0f} KB)")
        print("=" * 55)

        print("  업로드 및 분석 요청 중...")
        result_url = submit_analyze(pdf_path)
        print(f"  Operation-Location: {result_url}")

        print("  결과 대기 중...")
        data = poll_for_result(result_url)

        save_results(data, out_dir)

    print("\n전체 완료")


if __name__ == "__main__":
    main()
