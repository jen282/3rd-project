# 통합 이미지 추출 파이프라인 구현 계획

## 분기 처리 구조

```
페이지 입력
    ↓
스캔 판별: page.get_text().strip() < 50자
    │
    ├── 스캔 페이지 ──────────────────────────────────────────┐
    │                                                         │
    └── 디지털 페이지                                          │
            ├── [PyMuPDF] 래스터 블록 감지                     │
            └── [DI → Vision fallback]                        │
                    ↓                                         │
                IoU 병합                                       │
                    ↓                                         ↓
                            크롭 저장 + figures.json 출력
```

---

## 분기별 사용 도구

### 스캔 페이지

| 단계 | 도구 | 출력 |
|------|------|------|
| figure 감지 | Azure Document Intelligence `prebuilt-layout` | bbox, caption |
| DI 실패 시 fallback | GPT-4o Vision | bbox, caption, type |

- `surrounding_text`: 없음 (텍스트 레이어 없음)
- `type`: DI는 항상 `"other"`, Vision은 `photo/chart/diagram/map/other`

### 디지털 페이지

| 단계 | 도구 | 출력 |
|------|------|------|
| 래스터 이미지 감지 | PyMuPDF `get_text("dict")` type==1 블록 | bbox, surrounding_text |
| 벡터 차트 감지 | Azure Document Intelligence `prebuilt-layout` | bbox, caption |
| DI 실패 시 fallback | GPT-4o Vision | bbox, caption, type |
| 중복 제거 | IoU ≥ 0.3 → 같은 이미지 판정 | 병합 결과 |

병합 규칙:
- IoU ≥ 0.3 → PyMuPDF bbox 유지 + DI/Vision의 caption, type 보완
- IoU < 0.3 → DI/Vision 단독 감지 항목 추가 (벡터 차트)

---

## 출력 스키마 (figures.json)

```json
{
  "page": 17,
  "bbox": [278, 668, 1544, 995],
  "caption": "",
  "type": "other",
  "surrounding_text": "정규분포의 성질 평균 μ 표준편차 σ",
  "img_path": "img/page017_img00.png",
  "source": "PyMuPDF"
}
```

기존 대비 `surrounding_text` 필드 추가. 스캔/DI 경로는 `""`.

---

## 구현 대상 함수 (extract_images.py)

| 함수 | 역할 |
|------|------|
| `is_scan_page(page)` | 텍스트 < 50자 → True |
| `_get_surrounding_text(blocks, img_block)` | y거리 기준 인접 텍스트 블록 수집 |
| `extract_raster_blocks(page, pil_img)` | type==1 블록 → bbox(px) + surrounding_text |
| `iou(a, b)` | bbox IoU 계산 |
| `merge_figures(raster, di)` | IoU 기반 중복 제거 + 병합 |

---

## 미결 사항

- IoU threshold 0.3 적정성 — 실제 테스트 후 조정 필요
- 스캔 판별 threshold 50자 — 혼합 PDF에서 충분한지 확인 필요