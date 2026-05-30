from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class AiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class AiModelSettings:
    provider: str
    model: str
    base_url: str
    api_key: str
    timeout_seconds: int
    reasoning_effort: str


class AiClient:
    def request_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise NotImplementedError


class OpenAiCodexClient(AiClient):
    def __init__(self, settings: AiModelSettings) -> None:
        self.settings = settings

    def request_json(self, system_prompt: str, user_prompt: str) -> dict:
        if not self.settings.api_key:
            raise AiClientError("未检测到 AI API Key，请先设置环境变量后重试。")

        payload = self._build_payload(system_prompt, user_prompt)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.settings.base_url.rstrip('/')}/responses"
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise AiClientError(f"AI 请求失败（HTTP {exc.code}）: {response_body}") from exc
        except urllib.error.URLError as exc:
            raise AiClientError(f"AI 请求失败（网络异常）: {exc.reason}") from exc

        try:
            payload_json = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AiClientError("AI 返回内容不是合法 JSON。") from exc

        response_text = self._extract_output_text(payload_json)
        try:
            return self._parse_json_text(response_text)
        except json.JSONDecodeError as exc:
            raise AiClientError("AI 返回了文本，但不是可解析的 JSON。") from exc

    def _build_payload(self, system_prompt: str, user_prompt: str) -> dict:
        # 先走 JSON 对象输出，便于稳定解析。
        return {
            "model": self.settings.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text": {"format": {"type": "json_object"}},
            "reasoning": {"effort": self.settings.reasoning_effort},
            "max_output_tokens": 3000,
        }

    def _extract_output_text(self, payload: dict) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        chunks: list[str] = []
        for item in payload.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text", "")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())

        if chunks:
            return "\n".join(chunks)

        raise AiClientError("AI 返回成功，但未提取到文本输出。")

    def _parse_json_text(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            left = text.find("{")
            right = text.rfind("}")
            if left == -1 or right == -1 or right <= left:
                raise
            return json.loads(text[left : right + 1])


class AiClientFactory:
    def create(self, settings: AiModelSettings) -> AiClient:
        if settings.provider == "openai":
            return OpenAiCodexClient(settings)
        raise AiClientError(f"暂不支持的 AI 提供方: {settings.provider}")

