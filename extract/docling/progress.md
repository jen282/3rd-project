# Docling 테스트 진행 기록

## 목표

Docling으로 스캔/디지털 PDF를 구분 없이 처리하는 이미지 추출 파이프라인 검증.
기존 스택(PyMuPDF + Azure DI + GPT-4o Vision)의 대안 가능성 평가.

---

## 파일 구조

```
docling/
├── extract_images.py       # OCR 선택 가능 버전 (--ocr 플래그)
├── extract_images_ocr.py   # OCR 항상 ON 버전 (스캔 PDF 대응)
├── progress.md             # 이 파일
├── result-scan/            # 국사교과서.pdf 결과
│   ├── img/
│   ├── 국사교과서_figures.json
│   ├── 국사교과서_tables.json
│   └── 국사교과서_meta.json
└── result-digital/         # 통계기초.pdf 결과
    ├── img/
    ├── 통계기초_figures.json
    ├── 통계기초_tables.json
    └── 통계기초_meta.json
```

---

## 설정 (extract_images_ocr.py 기준)

| 항목 | 값 |
|------|-----|
| 백엔드 | `PyPdfiumDocumentBackend` (pdfium, Chrome 렌더링 엔진) |
| OCR | 항상 ON (`do_ocr=True`) |
| 표 구조 분석 | ON (`do_table_structure=True`) |
| 이미지 해상도 | 2x (`images_scale=2.0`) |
| figure 이미지 생성 | ON (`generate_picture_images=True`) |

---

## 진행 중 발생한 문제 및 해결

### 1. `ModuleNotFoundError: No module named 'docling'`
- **원인**: docling 미설치
- **해결**: `pip install docling`

### 2. `OSError: [WinError 1314]` — 심볼릭 링크 권한 오류
- **원인**: HuggingFace 모델 캐시 다운로드 시 Windows 심볼릭 링크 생성 실패
- **해결**: Windows 설정 → 개발자 모드 활성화

### 3. `UnicodeEncodeError: 'cp949'`
- **원인**: Windows 터미널 기본 인코딩(cp949)이 한국어/한자 출력 불가
- **해결**: 스크립트 상단에 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` 추가

### 4. `ConversionError: Input document 국사교과서.pdf is not valid`
- **원인**: OCR을 끄면 텍스트 레이어 없는 스캔 PDF를 "유효하지 않은 문서"로 거부
- **해결 시도 1**: `PyPdfiumDocumentBackend`로 전환 → OCR ON/OFF 무관하게 여전히 실패
- **원인 파악**: 처음 작동했던 조건은 기본 백엔드(docling-parse) + `do_ocr=True`. pyfium 백엔드가 이 스캔 PDF와 호환되지 않음
- **해결**: 기본 백엔드(docling-parse) 유지 + OCR 항상 ON (`do_ocr=True`) → `--max-pages` 없이 실행 시 정상 작동 확인

### 5. `--max-pages` 옵션 사용 시 ConversionError
- **원인**: `converter.convert()`에 `max_num_pages=15` kwarg를 넘기면 ConversionError 발생
- **확인**: `convert()` 시그니처 조회 결과 `page_range=(1, N)` 튜플 형태가 올바른 API
- **해결**: `convert_kwargs["page_range"] = (1, MAX_PAGES)` 로 변경 (테스트 중)

---

## 두 백엔드 차이

| | docling-parse (기본) | PyPdfiumDocumentBackend |
|--|--|--|
| 기반 | Docling 자체 파서 | Google PDFium (Chrome 엔진) |
| 정밀도 | 높음 | 중간 |
| 호환성 | 표준 PDF에 최적 | 비표준·스캔 PDF까지 처리 |
| 스캔 PDF | 거부 가능 | 처리 가능 |

---

## 실행 명령

```powershell
# 국사교과서 (스캔, 15페이지)
python extract_images_ocr.py --pdf 국사교과서.pdf --max-pages 15

# 통계기초 (디지털, 전체)
python extract_images_ocr.py --pdf 통계기초.pdf
```

---

## 현재 상태

- [x] 코드 작성 완료
- [x] 환경 문제 해결 (설치, 심볼릭 링크, 인코딩)
- [x] ConversionError 원인 파악 및 OCR 항상 ON 버전 작성
- [ ] 국사교과서.pdf 실행 결과 확인
- [ ] 통계기초.pdf 실행 결과 확인
- [ ] 기존 DI 파이프라인 결과와 비교
