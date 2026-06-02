"""
방안 3 크롭 이미지 → GPT-4o Vision → GraphRAG 노드 변환
approach3/result_digital/report.json 을 입력으로 사용한다.
"""

import base64
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

# .env는 rag-test/ 루트에 위치
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# .env의 OPEN_AI_ENDPOINT에 /openai/v1 경로가 포함되어 있어 제거
_raw_endpoint = os.environ["OPEN_AI_ENDPOINT"].rstrip("/").removesuffix("/openai/v1")

client = AzureOpenAI(
    api_key=os.environ["OPEN_AI_KEY"],
    azure_endpoint=_raw_endpoint,
    api_version="2024-08-01-preview",
)
DEPLOYMENT = os.environ["OPEN_AI_DEPLOYMENT_NAME"]

REPORT_PATH = Path(__file__).parent.parent / "approach3/result_digital/report.json"
IMAGE_BASE = Path(__file__).parent.parent / "approach3"
OUTPUT_PATH = Path(__file__).parent / "graph_nodes.json"

SYSTEM_PROMPT = (
    "당신은 PDF 이미지를 분석해 GraphRAG 노드로 변환하는 전문가입니다. "
    "반드시 JSON만 반환하세요. 다른 텍스트는 절대 포함하지 마세요."
)

USER_TEMPLATE = """\
이 이미지는 다음 텍스트 근처에 있습니다:
{surrounding_text}

아래 JSON 형식으로만 응답하세요:
{{
  "concept": "이미지가 나타내는 핵심 개념 (한국어)",
  "description": "한 문장 설명 (한국어)",
  "relations": [{{"relation": "관계명", "target": "연결 개념"}}],
  "type": "diagram|chart|table|illustration|other"
}}
"""


def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vision(image_path: Path, surrounding_text: str) -> dict:
    b64 = encode_image(image_path)
    ext = image_path.suffix.lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"

    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": USER_TEMPLATE.format(
                            surrounding_text=surrounding_text or "(텍스트 없음)"
                        ),
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=512,
    )
    return json.loads(response.choices[0].message.content)


def main():
    with open(REPORT_PATH, encoding="utf-8") as f:
        report = json.load(f)

    crops = report["crops"]
    print(f"총 {len(crops)}개 이미지 처리 시작\n")

    graph_nodes = []
    errors = []

    for idx, crop in enumerate(crops):
        image_path = IMAGE_BASE / crop["saved_as"]
        surrounding = crop.get("surrounding_text", "")

        print(f"[{idx+1:2d}/{len(crops)}] page {crop['page']:3d} block {crop['block_index']} → ", end="", flush=True)

        try:
            node = call_vision(image_path, surrounding)
            node["source"] = {
                "page": crop["page"],
                "bbox": crop["bbox_pdf"],
                "image_path": str(image_path),
            }
            graph_nodes.append(node)
            print(f"{node['concept']} ({node['type']})")
        except Exception as e:
            errors.append({"crop": crop, "error": str(e)})
            print(f"ERROR: {e}")

        # Azure OpenAI rate limit 대응
        time.sleep(0.5)

    print(f"\n완료: {len(graph_nodes)}개 노드 생성 / {len(errors)}건 오류")

    result = {
        "source_pdf": report["pdf_path"],
        "total_nodes": len(graph_nodes),
        "nodes": graph_nodes,
        "errors": errors,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {OUTPUT_PATH}")

    # 노드 미리보기
    print("\n--- 노드 미리보기 ---")
    for node in graph_nodes:
        print(f"  [{node['source']['page']}p] {node['concept']} | {node['description'][:40]}...")
        for rel in node.get("relations", [])[:2]:
            print(f"    → {rel['relation']} : {rel['target']}")


if __name__ == "__main__":
    main()
