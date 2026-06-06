from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


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

        candidates = self._extract_output_candidates(payload_json)
        for text in candidates:
            try:
                return self._parse_json_text(text)
            except json.JSONDecodeError:
                continue

        if candidates:
            raise AiClientError("AI 返回了文本，但不是可解析的 JSON。")
        raise AiClientError(self._build_empty_output_message(payload_json))

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
            "max_output_tokens": 6000,
        }

    def _extract_output_candidates(self, payload: dict) -> list[str]:
        candidates: list[str] = []
        self._append_candidate(candidates, payload.get("output_text"))
        self._append_chat_candidates(candidates, payload)
        self._append_response_candidates(candidates, payload)
        self._append_json_like_candidates(candidates, payload)
        return self._dedupe(candidates)

    def _append_chat_candidates(self, candidates: list[str], payload: dict) -> None:
        # 兼容部分 OpenAI-compatible 响应格式，后续扩展模型时可以复用。
        for choice in payload.get("choices", []):
            if not isinstance(choice, dict):
                continue
            message = choice.get("message", {})
            if isinstance(message, dict):
                self._append_candidate(candidates, message.get("content"))
            self._append_candidate(candidates, choice.get("text"))

    def _append_response_candidates(self, candidates: list[str], payload: dict) -> None:
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, str):
                    self._append_candidate(candidates, content)
                    continue
                if not isinstance(content, dict):
                    continue
                self._append_candidate(candidates, content.get("text"))
                self._append_candidate(candidates, content.get("output_text"))
                parsed = content.get("parsed")
                if isinstance(parsed, dict):
                    self._append_candidate(candidates, json.dumps(parsed, ensure_ascii=False))

    def _append_json_like_candidates(self, candidates: list[str], payload: Any) -> None:
        # 少数情况下文本会嵌在较深字段里，这里只收集看起来像 JSON 的片段。
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in {"input", "usage", "metadata", "error"}:
                    continue
                if isinstance(value, dict) and self._looks_like_result_object(value):
                    self._append_candidate(candidates, json.dumps(value, ensure_ascii=False))
                self._append_json_like_candidates(candidates, value)
            return
        if isinstance(payload, list):
            for item in payload:
                self._append_json_like_candidates(candidates, item)
            return
        if isinstance(payload, str) and self._looks_like_json_text(payload):
            self._append_candidate(candidates, payload)

    def _looks_like_result_object(self, value: dict) -> bool:
        return any(key in value for key in {"status", "patches", "decisions", "summary", "tests", "risks"})

    def _looks_like_json_text(self, text: str) -> bool:
        stripped = text.strip()
        return "{" in stripped and "}" in stripped and len(stripped) <= 2_000_000

    def _append_candidate(self, candidates: list[str], value: object) -> None:
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    def _dedupe(self, candidates: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _build_empty_output_message(self, payload: dict) -> str:
        status = payload.get("status", "")
        incomplete = payload.get("incomplete_details", {})
        if status == "incomplete" and isinstance(incomplete, dict):
            reason = incomplete.get("reason", "未知原因")
            return f"AI 返回未完成，原因: {reason}"
        return "AI 返回成功，但未提取到文本输出。"

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
