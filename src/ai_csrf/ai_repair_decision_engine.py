from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .ai_client import AiClient, AiClientError, AiClientFactory, AiModelSettings
from .config import RunConfig
from .repair_decision import RepairDecisionEngine


@dataclass(frozen=True)
class AiDecisionContext:
    provider: str
    model: str
    api_key_env: str


class AnalysisBriefBuilder:
    def build(self, analysis: dict) -> dict:
        repositories: list[dict] = []
        for repository in analysis.get("repositories", []):
            repositories.append(
                {
                    "role": repository.get("role", ""),
                    "exists": repository.get("exists", False),
                    "detected_stacks": repository.get("detected_stacks", [])[:6],
                    "risk_items": repository.get("risk_items", [])[:10],
                    "checks": self._trim_checks(repository.get("checks", [])),
                }
            )

        return {
            "summary": analysis.get("summary", {}),
            "repositories": repositories,
        }

    def _trim_checks(self, checks: list[dict]) -> list[dict]:
        trimmed: list[dict] = []
        for check in checks[:20]:
            trimmed.append(
                {
                    "id": check.get("id", ""),
                    "title": check.get("title", ""),
                    "status": check.get("status", ""),
                    "suggestion": check.get("suggestion", ""),
                    "evidence": check.get("evidence", [])[:3],
                }
            )
        return trimmed


class PromptBuilder:
    def build_system_prompt(self) -> str:
        return (
            "你是资深应用安全工程师。"
            "请基于输入的 CSRF 扫描结果，输出修复决策 JSON。"
            "不要输出 Markdown，只输出一个 JSON 对象。"
            "priority 仅允许 P0/P1/P2；action 仅允许 fix/review/block。"
            "target_phase 建议使用 阶段2/阶段4/阶段5。"
        )

    def build_user_prompt(self, run_id: str, analysis_brief: dict) -> str:
        return (
            f"run_id: {run_id}\n"
            "请根据下面的扫描结果给出修复决策。\n"
            "输出结构必须包含 decisions(数组) 和 next_actions(数组)。\n"
            "每个 decision 需要字段:"
            "id, repo_role, source_check, source_title, priority, target_phase, action, reason, repair_goal, suggested_steps, evidence, ai_instruction。\n"
            f"扫描摘要: {analysis_brief}"
        )


class AiDecisionNormalizer:
    def normalize(self, raw: dict, run_id: str) -> dict:
        decisions: list[dict] = []
        for index, item in enumerate(raw.get("decisions", []), start=1):
            if not isinstance(item, dict):
                continue

            repo_role = str(item.get("repo_role", "unknown")).strip() or "unknown"
            source_check = str(item.get("source_check", "custom_check")).strip() or "custom_check"
            decision_id = str(item.get("id", "")).strip() or f"{repo_role}:{source_check}:{index}"
            priority = self._normalize_priority(str(item.get("priority", "P1")))
            action = self._normalize_action(str(item.get("action", "review")))
            target_phase = str(item.get("target_phase", "")).strip() or self._default_phase(repo_role)

            decisions.append(
                {
                    "id": decision_id,
                    "repo_role": repo_role,
                    "source_check": source_check,
                    "source_title": str(item.get("source_title", "")).strip() or source_check,
                    "priority": priority,
                    "target_phase": target_phase,
                    "action": action,
                    "reason": str(item.get("reason", "")).strip() or "需要进一步处理该风险项。",
                    "repair_goal": str(item.get("repair_goal", "")).strip() or "补齐 CSRF 防护并保留业务行为。",
                    "suggested_steps": self._normalize_steps(item.get("suggested_steps", [])),
                    "evidence": self._normalize_evidence(item.get("evidence", [])),
                    "ai_instruction": str(item.get("ai_instruction", "")).strip() or "请按最小改动原则完成修复并补充测试。",
                }
            )

        next_actions = self._normalize_actions(raw.get("next_actions", []), decisions)
        summary = self._build_summary(decisions)

        return {
            "run_id": run_id,
            "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mode": "ai-codex-decision",
            "summary": summary,
            "decisions": decisions,
            "next_actions": next_actions,
            "notes": [],
        }

    def _normalize_priority(self, value: str) -> str:
        normalized = value.upper().strip()
        if normalized in {"P0", "P1", "P2"}:
            return normalized
        return "P1"

    def _normalize_action(self, value: str) -> str:
        normalized = value.lower().strip()
        if normalized in {"fix", "review", "block"}:
            return normalized
        return "review"

    def _default_phase(self, repo_role: str) -> str:
        if repo_role == "backend":
            return "阶段4"
        if repo_role == "frontend":
            return "阶段5"
        return "阶段4"

    def _normalize_steps(self, raw_steps: list) -> list[str]:
        steps = [str(step).strip() for step in raw_steps if str(step).strip()]
        return steps[:6] if steps else ["定位风险相关代码并生成最小修复。"]

    def _normalize_evidence(self, raw_evidence: list) -> list[dict]:
        evidences: list[dict] = []
        for item in raw_evidence[:6]:
            if not isinstance(item, dict):
                continue
            line_raw = item.get("line", 0)
            try:
                line = int(line_raw)
            except (TypeError, ValueError):
                line = 0
            evidences.append(
                {
                    "file": str(item.get("file", "")).strip(),
                    "line": max(line, 0),
                    "sample": str(item.get("sample", "")).strip(),
                }
            )
        return evidences

    def _normalize_actions(self, raw_actions: list, decisions: list[dict]) -> list[str]:
        actions = [str(action).strip() for action in raw_actions if str(action).strip()]
        if actions:
            return actions[:6]

        if not decisions:
            return ["当前没有生成修复任务，可先复核扫描规则或补充样本。"]

        if any(item["priority"] == "P0" for item in decisions):
            return ["优先处理 P0 风险并补齐测试，再继续后续任务。"]

        return ["先处理阶段4任务，再处理阶段5任务。"]

    def _build_summary(self, decisions: list[dict]) -> dict:
        summary = {
            "total": len(decisions),
            "by_priority": {},
            "by_action": {},
            "by_target_phase": {},
        }
        for item in decisions:
            self._increase(summary["by_priority"], item["priority"])
            self._increase(summary["by_action"], item["action"])
            self._increase(summary["by_target_phase"], item["target_phase"])
        return summary

    def _increase(self, data: dict, key: str) -> None:
        data[key] = data.get(key, 0) + 1


class AiRepairDecisionEngine:
    def __init__(
        self,
        client: AiClient,
        context: AiDecisionContext,
        fallback_engine: RepairDecisionEngine | None = None,
    ) -> None:
        self.client = client
        self.context = context
        self.fallback_engine = fallback_engine or RepairDecisionEngine()
        self.brief_builder = AnalysisBriefBuilder()
        self.prompt_builder = PromptBuilder()
        self.normalizer = AiDecisionNormalizer()

    @classmethod
    def from_config(cls, config: RunConfig) -> "AiRepairDecisionEngine":
        settings = AiModelSettings(
            provider=config.ai_provider,
            model=config.ai_model,
            base_url=config.ai_base_url,
            api_key=config.ai_api_key,
            timeout_seconds=config.ai_timeout_seconds,
            reasoning_effort=config.ai_reasoning_effort,
        )
        client = AiClientFactory().create(settings)
        context = AiDecisionContext(
            provider=config.ai_provider,
            model=config.ai_model,
            api_key_env=config.ai_api_key_env,
        )
        return cls(client=client, context=context)

    def build(self, run_id: str, analysis: dict) -> dict:
        brief = self.brief_builder.build(analysis)
        system_prompt = self.prompt_builder.build_system_prompt()
        user_prompt = self.prompt_builder.build_user_prompt(run_id, brief)

        try:
            raw = self.client.request_json(system_prompt, user_prompt)
        except AiClientError as exc:
            fallback = self.fallback_engine.build(run_id, analysis)
            fallback["mode"] = "rule-guided-ai-decision-fallback"
            fallback.setdefault("notes", []).append("AI 决策失败，已回退到规则决策。")
            fallback["notes"].append(f"失败原因: {exc}")
            fallback["notes"].append(
                f"AI 配置: provider={self.context.provider}, model={self.context.model}, key_env={self.context.api_key_env}"
            )
            return fallback

        decision = self.normalizer.normalize(raw, run_id)
        decision["notes"] = [
            "当前结果由 AI 决策生成，建议在进入自动修复前先做人工抽检。",
            f"AI 配置: provider={self.context.provider}, model={self.context.model}, key_env={self.context.api_key_env}",
        ]
        return decision
