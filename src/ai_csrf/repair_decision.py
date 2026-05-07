from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class RepairTemplate:
    priority: str
    target_phase: str
    action: str
    goal: str
    steps: list[str]


class RepairTemplateCatalog:
    def __init__(self) -> None:
        self.templates = {
            "backend_csrf_token": RepairTemplate(
                priority="P0",
                target_phase="阶段4",
                action="fix",
                goal="在后端写操作请求中启用 CSRF token 校验。",
                steps=[
                    "定位后端鉴权或安全配置入口。",
                    "为状态变更请求增加 CSRF token 校验。",
                    "补充 token 缺失、错误和合法三类测试。",
                ],
            ),
            "backend_origin_referer": RepairTemplate(
                priority="P1",
                target_phase="阶段4",
                action="fix",
                goal="为敏感写操作补充 Origin/Referer 校验。",
                steps=[
                    "确认允许访问的前端域名来源。",
                    "在后端请求入口增加 Origin/Referer 白名单校验。",
                    "补充跨站来源被拒绝的测试。",
                ],
            ),
            "backend_cookie_policy": RepairTemplate(
                priority="P1",
                target_phase="阶段4",
                action="fix",
                goal="补齐会话 Cookie 的安全属性。",
                steps=[
                    "定位会话 Cookie 设置位置。",
                    "检查并设置 SameSite、HttpOnly、Secure 属性。",
                    "补充 Cookie 属性断言或配置检查。",
                ],
            ),
            "backend_csrf_disabled": RepairTemplate(
                priority="P0",
                target_phase="阶段4",
                action="review",
                goal="确认 CSRF 防护关闭是否合理，并决定恢复防护或限定白名单。",
                steps=[
                    "定位关闭 CSRF 的配置位置。",
                    "判断关闭范围是否只覆盖必要接口。",
                    "优先恢复默认防护，无法恢复时补充等价校验。",
                ],
            ),
            "frontend_csrf_header": RepairTemplate(
                priority="P0",
                target_phase="阶段5",
                action="fix",
                goal="在前端请求封装层统一注入 CSRF header。",
                steps=[
                    "定位 fetch、axios 或其他请求封装入口。",
                    "读取 CSRF token 并写入统一请求 header。",
                    "补充请求 header 注入测试。",
                ],
            ),
            "frontend_token_source": RepairTemplate(
                priority="P1",
                target_phase="阶段5",
                action="fix",
                goal="明确前端 CSRF token 的读取来源。",
                steps=[
                    "确认 token 来自 Cookie、meta 标签还是接口。",
                    "封装统一的 token 读取方法。",
                    "补充 token 不存在时的降级处理。",
                ],
            ),
            "frontend_credentials": RepairTemplate(
                priority="P2",
                target_phase="阶段5",
                action="review",
                goal="确认前端请求是否需要携带 Cookie 凭据。",
                steps=[
                    "梳理依赖 Cookie 会话的接口。",
                    "确认 credentials 或 withCredentials 的使用边界。",
                    "避免对无关跨域请求默认携带凭据。",
                ],
            ),
        }

    def get(self, rule_id: str) -> RepairTemplate | None:
        return self.templates.get(rule_id)


class RepairDecisionEngine:
    def __init__(self, catalog: RepairTemplateCatalog | None = None) -> None:
        self.catalog = catalog or RepairTemplateCatalog()

    def build(self, run_id: str, analysis: dict) -> dict:
        decisions = self._collect_decisions(analysis)
        return {
            "run_id": run_id,
            "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mode": "rule-guided-ai-decision",
            "summary": self._summarize(decisions),
            "decisions": decisions,
            "next_actions": self._build_next_actions(decisions),
            "notes": [
                "当前阶段生成修复决策和 AI 执行提示，不直接修改仓库代码。",
                "后续阶段会根据决策结果生成补丁、测试和 PR。",
            ],
        }

    def _collect_decisions(self, analysis: dict) -> list[dict]:
        decisions: list[dict] = []
        for repo in analysis["repositories"]:
            if not repo["exists"]:
                decisions.append(self._missing_repo_decision(repo))
                continue

            for check in repo["checks"]:
                decision = self._decide_check(repo, check)
                if decision:
                    decisions.append(decision)

        return sorted(decisions, key=self._sort_key)

    def _decide_check(self, repo: dict, check: dict) -> dict | None:
        template = self.catalog.get(check["id"])
        if not template:
            return None

        should_fix_missing = check["status"] == "missing" and check["id"] != "backend_csrf_disabled"
        should_review_present = check["status"] == "found" and check["id"] == "backend_csrf_disabled"
        if not (should_fix_missing or should_review_present):
            return None

        return {
            "id": f"{repo['role']}:{check['id']}",
            "repo_role": repo["role"],
            "source_check": check["id"],
            "source_title": check["title"],
            "priority": template.priority,
            "target_phase": template.target_phase,
            "action": template.action,
            "reason": check["suggestion"],
            "repair_goal": template.goal,
            "suggested_steps": template.steps,
            "evidence": check["evidence"][:5],
            "ai_instruction": self._build_ai_instruction(repo, check, template),
        }

    def _missing_repo_decision(self, repo: dict) -> dict:
        return {
            "id": f"{repo['role']}:repository_missing",
            "repo_role": repo["role"],
            "source_check": "repository_missing",
            "source_title": "本地仓库目录不存在",
            "priority": "P0",
            "target_phase": "阶段2",
            "action": "block",
            "reason": "本地仓库不存在，无法进行修复判断。",
            "repair_goal": "先完成仓库 clone/fetch 和工作分支准备。",
            "suggested_steps": ["执行 --execute-bootstrap 拉取仓库。", "确认 repos 目录下存在前后端仓库。"],
            "evidence": [],
            "ai_instruction": "先停止修复生成，完成仓库准备后重新执行扫描和决策。",
        }

    def _build_ai_instruction(self, repo: dict, check: dict, template: RepairTemplate) -> str:
        return (
            f"请在 {repo['role']} 仓库中处理「{check['title']}」。"
            f"目标：{template.goal}"
            f"优先级：{template.priority}。"
            "要求：先定位相关安全配置或请求封装，再生成最小必要改动，并补充对应测试。"
        )

    def _summarize(self, decisions: list[dict]) -> dict:
        summary = {
            "total": len(decisions),
            "by_priority": {},
            "by_action": {},
            "by_target_phase": {},
        }
        for decision in decisions:
            self._increase(summary["by_priority"], decision["priority"])
            self._increase(summary["by_action"], decision["action"])
            self._increase(summary["by_target_phase"], decision["target_phase"])
        return summary

    def _build_next_actions(self, decisions: list[dict]) -> list[str]:
        if not decisions:
            return ["暂未生成修复任务，可以进入人工复核或继续扩大扫描规则。"]

        if any(item["action"] == "block" for item in decisions):
            return ["先完成仓库准备，再重新执行 CSRF 扫描和修复决策。"]

        actions = ["优先处理 P0 修复决策。"]
        if any(item["target_phase"] == "阶段4" for item in decisions):
            actions.append("先进入阶段4，实现后端侧 CSRF 修复 MVP。")
        if any(item["target_phase"] == "阶段5" for item in decisions):
            actions.append("后端修复稳定后，再进入阶段5处理前端 token 注入流程。")
        return actions

    def _increase(self, data: dict, key: str) -> None:
        data[key] = data.get(key, 0) + 1

    def _sort_key(self, decision: dict) -> tuple[int, str, str]:
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        return (
            priority_order.get(decision["priority"], 99),
            decision["target_phase"],
            decision["id"],
        )
