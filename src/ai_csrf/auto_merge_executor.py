from __future__ import annotations

from pathlib import Path

from .git_client import CommandRunner


class AutoMergeExecutor:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def execute(
        self,
        run_id: str,
        provider: str,
        strategy: str,
        execute_merge: bool,
        ci_result: dict | None,
        pr_result: dict | None,
    ) -> dict:
        actions: list[dict] = []
        result = {
            "run_id": run_id,
            "mode": "auto-merge",
            "provider": provider,
            "strategy": strategy,
            "execute_merge": execute_merge,
            "status": "skipped",
            "actions": actions,
            "summary": {},
            "message": "",
            "notes": [
                "仅在 auto-merge=on-green 且 CI 闸门通过时允许合并。",
                "默认只评估合并条件，显式传入 --execute-merge 才真正执行合并命令。",
            ],
        }

        if strategy != "on-green":
            result["status"] = "skipped"
            result["message"] = "当前自动合并策略为 off，跳过合并流程。"
            result["summary"] = self._build_summary(actions)
            return result

        if not ci_result:
            result["status"] = "blocked"
            result["message"] = "缺少 CI 闸门结果，无法评估合并条件。"
            result["summary"] = self._build_summary(actions)
            return result

        if not ci_result.get("summary", {}).get("gate_passed", False):
            result["status"] = "blocked"
            result["message"] = "CI 闸门未通过，阻断自动合并。"
            result["summary"] = self._build_summary(actions)
            return result

        if not pr_result:
            result["status"] = "blocked"
            result["message"] = "缺少 PR 结果，无法执行自动合并。"
            result["summary"] = self._build_summary(actions)
            return result

        if provider != "github":
            result["status"] = "manual"
            result["message"] = "当前只支持 GitHub 自动合并，其他平台请手动处理。"
            result["summary"] = self._build_summary(actions)
            return result

        gh_available = self._gh_available()
        for repository in pr_result.get("repositories", []):
            actions.append(self._merge_one(repository, execute_merge, gh_available))

        summary = self._build_summary(actions)
        result["summary"] = summary
        if summary.get("fail", 0) > 0:
            result["status"] = "fail"
            result["message"] = "存在合并失败的 PR。"
        elif summary.get("blocked", 0) > 0:
            result["status"] = "blocked"
            result["message"] = "存在未满足合并条件的 PR。"
        elif summary.get("pass", 0) > 0:
            result["status"] = "pass"
            result["message"] = "自动合并执行成功。"
        elif summary.get("planned", 0) > 0:
            result["status"] = "planned"
            result["message"] = "合并条件已满足，等待执行合并命令。"
        else:
            result["status"] = "skipped"
            result["message"] = "没有可合并的 PR。"
        return result

    def _merge_one(self, repository: dict, execute_merge: bool, gh_available: bool) -> dict:
        action = {
            "role": repository.get("role", ""),
            "pr_url": repository.get("pr_url", ""),
            "status": "blocked",
            "message": "",
        }

        repo_status = repository.get("status", "")
        if repo_status != "pass":
            action["status"] = "blocked"
            action["message"] = f"PR 状态为 {repo_status}，不满足自动合并条件。"
            return action

        pr_url = repository.get("pr_url", "")
        if not pr_url:
            action["status"] = "blocked"
            action["message"] = "PR URL 为空，无法执行自动合并。"
            return action

        if not gh_available:
            action["status"] = "blocked"
            action["message"] = "未检测到 gh 工具，无法执行自动合并。"
            return action

        if not execute_merge:
            action["status"] = "planned"
            action["message"] = "CI 已通过，可执行自动合并。"
            return action

        merge_result = self.runner.run(["gh", "pr", "merge", pr_url, "--squash", "--delete-branch"])
        if merge_result.returncode != 0:
            action["status"] = "fail"
            action["message"] = merge_result.stderr.strip() or merge_result.stdout.strip() or "gh pr merge 执行失败"
            return action

        action["status"] = "pass"
        action["message"] = "PR 已自动合并。"
        return action

    def _gh_available(self) -> bool:
        return self.runner.run(["gh", "--version"]).returncode == 0

    def _build_summary(self, actions: list[dict]) -> dict:
        summary = {"pass": 0, "planned": 0, "blocked": 0, "fail": 0}
        for action in actions:
            status = action["status"]
            summary[status] = summary.get(status, 0) + 1
        return summary
