import json

import httpx

from app.settings import get_settings


def responses_request(model: str, instructions: str, payload: dict) -> dict:
    return {
        "model": model,
        "instructions": instructions,
        "input": json.dumps(payload),
        "max_output_tokens": 8000,
        "text": {"format": {"type": "json_object"}},
    }


def response_output_text(body: dict) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    parts: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("text"):
                    parts.append(str(content["text"]))
        elif item.get("text"):
            parts.append(str(item["text"]))
    return "".join(parts)


class OpenAIReasoner:
    def complete_json(self, instructions: str, payload: dict) -> dict:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("An OpenAI API key is required for this step.")
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=responses_request(settings.openai_reasoning_model, instructions, payload),
            timeout=90,
        )
        if response.status_code >= 400:
            raise RuntimeError("The reasoning model request failed.")
        text = response_output_text(response.json()).strip()
        return json.loads(text)
