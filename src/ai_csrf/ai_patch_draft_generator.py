from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from .ai_client import AiClient, AiClientError, AiClientFactory, AiModelSettings
from .config import RunConfig
from .rules import IGNORE_DIRS, TEXT_SUFFIXES


@dataclass(frozen=True)
class AiPatchContext:
    provider: str
    model: str
    api_key_env: str


class RepositoryContextBuilder:
    CANDIDATE_FILES = [
        "package.json",
        "server.js",
        "app.js",
        "index.js",
        "backend/server.js",
        "backend/app.js",
        "backend/index.js",
        "frontend/package.json",
        "frontend/src/App.jsx",
        "frontend/src/App.js",
        "frontend/src/main.jsx",
        "frontend/src/main.js",
        "src/App.jsx",
        "src/App.js",
        "src/main.jsx",
        "src/main.js",
        "src/api.js",
        "src/request.js",
        "src/http.js",
    ]

    def build(self, role: str, root: Path, decisions: list[dict]) -> dict:
        if not root.exists():
            return {"role": role, "exists": False, "path": str(root), "files": []}

        selected = self._select_files(root, decisions)
        files: list[dict] = []
        for path in selected[:10]:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except OSError:
                continue
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "content": text[:5000],
                    "truncated": len(text) > 5000,
                }
            )
        return {"role": role, "exists": True, "path": str(root), "files": files}

    def _select_files(self, root: Path, decisions: list[dict]) -> list[Path]:
        selected: list[Path] = []
        for decision in decisions:
            for evidence in decision.get("evidence", []):
                file_name = str(evidence.get("file", "")).strip()
                if file_name:
                    self._append_if_valid(selected, root / file_name, root)

        for relative_path in self.CANDIDATE_FILES:
            self._append_if_valid(selected, root / relative_path, root)

        if selected:
            return selected

        for path in root.rglob("*"):
            if len(selected) >= 8:
                break
            self._append_if_valid(selected, path, root)
        return selected

    def _append_if_valid(self, selected: list[Path], path: Path, root: Path) -> None:
        if path in selected or not path.exists() or path.is_dir():
            return
        if not self._should_read(path, root):
            return
        selected.append(path)

    def _should_read(self, path: Path, root: Path) -> bool:
        try:
            relative = path.relative_to(root)
        except ValueError:
            return False
        if any(part in IGNORE_DIRS for part in relative.parts):
            return False
        if path.suffix and path.suffix not in TEXT_SUFFIXES:
            return False
        try:
            return path.stat().st_size <= 120_000
        except OSError:
            return False


class AiPatchPromptBuilder:
    def build_system_prompt(self) -> str:
        return (
            "你是资深应用安全工程师。"
            "请根据 CSRF 修复决策和仓库片段生成补丁草案 JSON。"
            "不要输出 Markdown，只输出 JSON 对象。"
            "补丁只允许最小必要改动；不要删除业务功能；不要输出绝对路径。"
            "files 中每一项必须包含 role、path、action、content、reason。"
            "action 仅允许 upsert 或 replace；content 必须是完整文件内容。"
        )

    def build_user_prompt(self, run_id: str, decision: dict, contexts: list[dict]) -> str:
        return (
            f"run_id: {run_id}\n"
            "请输出结构：status、summary、patches、tests、risks。\n"
            "patches 是数组，每项包含 role、objective、files、notes。\n"
            "files 是数组，每项包含 role、path、action、content、reason。\n"
            f"修复决策: {decision}\n"
            f"仓库上下文: {contexts}"
        )


class AiPatchDraftNormalizer:
    def normalize(self, raw: dict, run_id: str, context: AiPatchContext) -> dict:
        patches: list[dict] = []
        for patch in raw.get("patches", []):
            if not isinstance(patch, dict):
                continue
            files = self._normalize_files(patch.get("files", []))
            patches.append(
                {
                    "role": str(patch.get("role", "")).strip(),
                    "objective": str(patch.get("objective", "")).strip(),
                    "files": files,
                    "notes": self._normalize_text_list(patch.get("notes", [])),
                }
            )

        return {
            "run_id": run_id,
            "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mode": "ai-codex-patch-draft",
            "provider": context.provider,
            "model": context.model,
            "status": str(raw.get("status", "drafted")).strip() or "drafted",
            "summary": str(raw.get("summary", "")).strip(),
            "patches": patches,
            "tests": self._normalize_text_list(raw.get("tests", [])),
            "risks": self._normalize_text_list(raw.get("risks", [])),
            "notes": [
                "补丁草案默认不落盘，只有显式传入 --apply-ai-patch 才会写入目标仓库。",
                f"AI 配置: provider={context.provider}, model={context.model}, key_env={context.api_key_env}",
            ],
        }

    def fallback(self, run_id: str, context: AiPatchContext, reason: str) -> dict:
        return {
            "run_id": run_id,
            "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mode": "ai-codex-patch-draft-fallback",
            "provider": context.provider,
            "model": context.model,
            "status": "blocked",
            "summary": "AI 补丁草案生成失败，未产生可落地改动。",
            "patches": [],
            "tests": [],
            "risks": [],
            "notes": [
                f"失败原因: {reason}",
                "可先检查 API Key、模型权限和网络连通性。",
                f"AI 配置: provider={context.provider}, model={context.model}, key_env={context.api_key_env}",
            ],
        }

    def _normalize_files(self, raw_files: list) -> list[dict]:
        files: list[dict] = []
        for item in raw_files:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            action = str(item.get("action", "upsert")).strip().lower()
            if action not in {"upsert", "replace"}:
                action = "upsert"
            files.append(
                {
                    "role": role,
                    "path": str(item.get("path", "")).strip(),
                    "action": action,
                    "content": str(item.get("content", "")),
                    "reason": str(item.get("reason", "")).strip(),
                }
            )
        return files

    def _normalize_text_list(self, value: list) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()][:10]


class AiPatchDraftLoader:
    def load(self, run_id: str, draft_file: str, workspace: Path) -> dict:
        path = Path(draft_file)
        if not path.is_absolute():
            path = workspace / path
        if not path.exists():
            raise ValueError(f"未找到 AI 补丁草案文件: {path}")

        try:
            draft = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError("AI 补丁草案不是合法 JSON。") from exc

        if not isinstance(draft, dict):
            raise ValueError("AI 补丁草案内容必须是 JSON 对象。")

        loaded = dict(draft)
        loaded["run_id"] = run_id
        loaded["source_draft_file"] = str(path)
        notes = list(loaded.get("notes", [])) if isinstance(loaded.get("notes", []), list) else []
        notes.append("本次复用已有 AI 补丁草案，不重复调用模型。")
        loaded["notes"] = notes
        return loaded


class AiPatchDraftGenerator:
    def __init__(
        self,
        client: AiClient,
        context: AiPatchContext,
        repo_context_builder: RepositoryContextBuilder | None = None,
    ) -> None:
        self.client = client
        self.context = context
        self.repo_context_builder = repo_context_builder or RepositoryContextBuilder()
        self.prompt_builder = AiPatchPromptBuilder()
        self.normalizer = AiPatchDraftNormalizer()

    @classmethod
    def from_config(cls, config: RunConfig) -> "AiPatchDraftGenerator":
        settings = AiModelSettings(
            provider=config.ai_provider,
            model=config.ai_model,
            base_url=config.ai_base_url,
            api_key=config.ai_api_key,
            timeout_seconds=config.ai_timeout_seconds,
            reasoning_effort=config.ai_reasoning_effort,
        )
        client = AiClientFactory().create(settings)
        context = AiPatchContext(
            provider=config.ai_provider,
            model=config.ai_model,
            api_key_env=config.ai_api_key_env,
        )
        return cls(client=client, context=context)

    def build(self, run_id: str, decision: dict, frontend_root: Path, backend_root: Path) -> dict:
        frontend_decisions = [item for item in decision.get("decisions", []) if item.get("repo_role") == "frontend"]
        backend_decisions = [item for item in decision.get("decisions", []) if item.get("repo_role") == "backend"]
        contexts = [
            self.repo_context_builder.build("frontend", frontend_root, frontend_decisions),
            self.repo_context_builder.build("backend", backend_root, backend_decisions),
        ]
        system_prompt = self.prompt_builder.build_system_prompt()
        user_prompt = self.prompt_builder.build_user_prompt(run_id, decision, contexts)

        try:
            raw = self.client.request_json(system_prompt, user_prompt)
        except AiClientError as exc:
            return self.normalizer.fallback(run_id, self.context, str(exc))

        return self.normalizer.normalize(raw, run_id, self.context)
