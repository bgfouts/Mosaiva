import json

import httpx

from app.settings import get_settings


class OpenAIReasoner:
    def complete_json(self, instructions: str, payload: dict) -> dict:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("An OpenAI API key is required for this step.")
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_reasoning_model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            },
            timeout=90,
        )
        if response.status_code >= 400:
            raise RuntimeError("The reasoning model request failed.")
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
