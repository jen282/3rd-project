# GPT-4o Vision → GraphRAG 노드 변환 계획

## 전체 흐름

```
방안 3 결과물 (report.json + 크롭 이미지)
        ↓
  base64 인코딩
        ↓
  GPT-4o Vision 호출
  (이미지 + surrounding_text를 프롬프트에 포함)
        ↓
  JSON 응답 파싱
  {concept, description, relations, type}
        ↓
  GraphRAG 노드로 저장
  (source: page, bbox 위치 메타데이터 포함)
```

---

## 입력: 방안 3 결과물

`approach3/result_digital/report.json` 의 각 crop 항목:

```json
{
  "page": 17,
  "bbox_pdf": [140.2, 334.1, 770.6, 540.0],
  "width_px": 1261,
  "height_px": 411,
  "surrounding_text": "평균이 중앙값보다 작음. 분포의 꼬리가 왼쪽(음의 방향)으로...",
  "saved_as": "result_digital/page017_block00.png"
}
```

---

## GPT-4o 프롬프트 구조

```
[system]
당신은 PDF 이미지를 분석해 GraphRAG 노드로 변환하는 전문가입니다.
반드시 JSON만 반환하세요.

[user]
이미지 + 다음 텍스트 컨텍스트: {surrounding_text}

아래 JSON 형식으로만 응답하세요:
{
  "concept": "이미지가 나타내는 핵심 개념",
  "description": "한 문장 설명",
  "relations": [{"relation": "관계명", "target": "연결 개념"}],
  "type": "diagram|chart|table|illustration|other"
}
```

---

## 출력: GraphRAG 노드

```json
{
  "concept": "정규분포",
  "description": "평균을 중심으로 좌우 대칭인 종 모양 확률분포",
  "relations": [
    {"relation": "포함", "target": "68-95-99.7 규칙"},
    {"relation": "특수케이스", "target": "표준정규분포"}
  ],
  "type": "diagram",
  "source": {
    "page": 17,
    "bbox": [140.2, 334.1, 770.6, 540.0],
    "image_path": "approach3/result_digital/page017_block00.png"
  }
}
```

---

## 사용 모델 및 환경

| 항목 | 값 |
|---|---|
| 모델 | GPT-4o (`gpt-4o`) |
| API 형식 | Azure OpenAI |
| 엔드포인트 | `.env` → `OPEN_AI_ENDPOINT` |
| 배포명 | `.env` → `OPEN_AI_DEPLOYMENT_NAME` |
| `response_format` | `json_object` |

---

## 비용 추정 (통계기초.pdf 기준)

- 크롭 이미지 14개 × GPT-4o Vision 1회 = **14회 호출**
- 이미지 토큰: 크기에 따라 약 85~340 토큰/장
- 텍스트 토큰: 프롬프트 약 200~300 토큰/호출
- 총 예상: 약 **5,000~7,000 토큰** (수 센트 수준)

---

## 파일 구성

```
pymupdf/gpt/
├── plan.md              ← 이 파일
├── vision_node.py       ← GPT-4o Vision 호출 + 노드 변환 코드
└── graph_nodes.json     ← 실행 후 생성되는 노드 결과
```
