from __future__ import annotations

import re
from pathlib import Path

from .git_client import CommandRunner, GitClient
from .repository import RepositoryTarget


class PullRequestCreator:
    def __init__(self, git: GitClient | None = None, runner: CommandRunner | None = None) -> None:
        self.git = git or GitClient()
        self.runner = runner or CommandRunner()

    def create(
        self,
        run_id: str,
        provider: str,
        base_branch: str,
        frontend_target: RepositoryTarget,
        backend_target: RepositoryTarget,
        ai_evidence: dict | None = None,
    ) -> dict:
        repositories = [
            self._create_for_repository(run_id, provider, base_branch, frontend_target, backend_target, ai_evidence),
            self._create_for_repository(run_id, provider, base_branch, backend_target, frontend_target, ai_evidence),
        ]
        return {
            "run_id": run_id,
            "mode": "pr-automation",
            "provider": provider,
            "base_branch": base_branch,
            "repositories": repositories,
            "summary": self._build_summary(repositories),
            "notes": [
                "自动提 PR 只在显式传入 --create-pr 时执行。",
                "若未检测到 gh/glab 工具，会返回手动创建 PR 的命令建议。",
            ],
        }

    def _create_for_repository(
        self,
        run_id: str,
        provider: str,
        base_branch: str,
        target: RepositoryTarget,
        related: RepositoryTarget,
        ai_evidence: dict | None,
    ) -> dict:
        result = {
            "role": target.role,
            "path": str(target.local_path),
            "branch": target.work_branch,
            "status": "skipped",
            "commit_message": "",
            "pr_url": "",
            "manual_pr_command": "",
            "message": "",
        }

        if not target.local_path.exists():
            result["status"] = "blocked"
            result["message"] = "仓库目录不存在，请先执行仓库准备。"
            return result

        changes = self.git.run(["status", "--porcelain"], cwd=target.local_path)
        if changes.returncode != 0:
            result["status"] = "fail"
            result["message"] = changes.stderr.strip() or "无法读取仓库状态"
            return result
        if not changes.stdout.strip():
            result["status"] = "skipped"
            result["message"] = "当前仓库无改动，跳过 PR 创建。"
            return result

        commit_message = f"fix(csrf): {target.role} autopilot updates ({run_id})"
        result["commit_message"] = commit_message

        add_result = self.git.run(["add", "-A"], cwd=target.local_path)
        if add_result.returncode != 0:
            result["status"] = "fail"
            result["message"] = add_result.stderr.strip() or "git add 执行失败"
            return result

        commit_result = self.git.run(["commit", "-m", commit_message], cwd=target.local_path)
        if commit_result.returncode != 0 and "nothing to commit" not in commit_result.stdout.lower():
            result["status"] = "fail"
            result["message"] = commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit 执行失败"
            return result

        push_result = self.git.run(["push", "-u", "origin", target.work_branch], cwd=target.local_path)
        if push_result.returncode != 0:
            result["status"] = "fail"
            result["message"] = push_result.stderr.strip() or "git push 执行失败"
            return result

        pr_title = f"[AI-CSRF] {target.role} csrf fix ({run_id})"
        pr_body = self._build_pr_body(run_id, target, related, ai_evidence)

        if provider == "github":
            return self._create_github_pr(result, target.local_path, base_branch, pr_title, pr_body)

        if provider == "gitlab":
            result["status"] = "manual"
            result["manual_pr_command"] = (
                f"glab mr create --source-branch {target.work_branch} --target-branch {base_branch} "
                f"--title \"{pr_title}\""
            )
            result["message"] = "未自动创建 GitLab MR，请执行手动命令。"
            return result

        result["status"] = "manual"
        result["message"] = "未知平台，无法自动创建 PR。"
        return result

    def _create_github_pr(
        self,
        result: dict,
        repo_path: Path,
        base_branch: str,
        pr_title: str,
        pr_body: str,
    ) -> dict:
        gh_version = self.runner.run(["gh", "--version"], cwd=repo_path)
        if gh_version.returncode != 0:
            result["status"] = "manual"
            result["manual_pr_command"] = (
                f"gh pr create --base {base_branch} --head {result['branch']} "
                f"--title \"{pr_title}\" --body-file <body-file>"
            )
            result["message"] = "未检测到 gh 工具，请执行手动命令创建 PR。"
            return result

        create_cmd = [
            "gh",
            "pr",
            "create",
            "--base",
            base_branch,
            "--head",
            result["branch"],
            "--title",
            pr_title,
            "--body",
            pr_body,
        ]
        create_result = self.runner.run(create_cmd, cwd=repo_path)
        if create_result.returncode != 0:
            result["status"] = "fail"
            result["message"] = create_result.stderr.strip() or create_result.stdout.strip() or "gh pr create 执行失败"
            return result

        url_match = re.search(r"https?://\S+", create_result.stdout)
        result["status"] = "pass"
        result["pr_url"] = url_match.group(0) if url_match else ""
        result["message"] = "PR 创建成功"
        return result

    def _build_pr_body(self, run_id: str, target: RepositoryTarget, related: RepositoryTarget, ai_evidence: dict | None) -> str:
        lines = [
            f"run_id: {run_id}",
            f"role: {target.role}",
            f"branch: {target.work_branch}",
            f"related_{related.role}_branch: {related.work_branch}",
            "generated_by: AI-CSRF autopilot",
        ]
        if ai_evidence:
            lines.extend(["", "AI evidence:"])
            lines.extend(self._format_ai_evidence(ai_evidence))
        return "\n".join(lines)

    def _format_ai_evidence(self, ai_evidence: dict) -> list[str]:
        lines: list[str] = []
        decision = ai_evidence.get("decision") or {}
        draft = ai_evidence.get("patch_draft") or {}
        apply_result = ai_evidence.get("patch_apply") or {}
        ci_result = ai_evidence.get("ci_result") or {}

        if decision:
            lines.append(f"- decision_mode: {decision.get('mode', '')}")
            lines.append(f"- decision_total: {decision.get('summary', {}).get('total', 0)}")
        if draft:
            lines.append(f"- patch_draft_status: {draft.get('status', '')}")
            lines.append(f"- patch_groups: {len(draft.get('patches', []))}")
        if apply_result:
            lines.append(f"- patch_apply_status: {apply_result.get('status', '')}")
            lines.append(f"- changed_files: {len(apply_result.get('changed_files', []))}")
        if ci_result:
            lines.append(f"- ci_gate_passed: {ci_result.get('summary', {}).get('gate_passed', False)}")
        return lines

    def _build_summary(self, repositories: list[dict]) -> dict:
        summary = {"pass": 0, "manual": 0, "fail": 0, "skipped": 0, "blocked": 0}
        for repository in repositories:
            status = repository["status"]
            summary[status] = summary.get(status, 0) + 1
        return summary
