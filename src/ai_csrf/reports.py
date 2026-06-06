from __future__ import annotations

import json
from pathlib import Path


class ReportPathFactory:
    def __init__(self, workspace: Path) -> None:
        self.reports_dir = workspace / "reports"

    def ensure_dir(self) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def json_path(self, prefix: str, run_id: str) -> Path:
        return self.reports_dir / f"{prefix}-{run_id}.json"

    def markdown_path(self, prefix: str, run_id: str) -> Path:
        return self.reports_dir / f"{prefix}-{run_id}.md"


class ExecutionPlanReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, plan: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("run-plan", run_id)
        md_path = self.paths.markdown_path("run-plan", run_id)

        json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(plan)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, plan: dict) -> list[str]:
        lines = [
            f"# 执行计划 {plan['run_id']}",
            "",
            "## 输入参数",
            f"- 前端仓库: `{plan['inputs']['frontend_repo']}`",
            f"- 后端仓库: `{plan['inputs']['backend_repo']}`",
            f"- 平台: `{plan['inputs']['provider']}`",
            f"- 目标分支: `{plan['inputs']['base_branch']}`",
            f"- 自动合并: `{plan['inputs']['auto_merge']}`",
            f"- 执行模式: `{plan['mode']}`",
            "",
            "## 仓库准备",
            f"- 前端本地目录: `{plan['repo_setup']['frontend_local_path']}`",
            f"- 后端本地目录: `{plan['repo_setup']['backend_local_path']}`",
            f"- 前端工作分支: `{plan['repo_setup']['frontend_branch']}`",
            f"- 后端工作分支: `{plan['repo_setup']['backend_branch']}`",
            "",
            "## 检查结果",
            f"- git 命令: `{plan['checks']['git_cli']['status']}` - {plan['checks']['git_cli']['message']}",
            f"- 令牌检查: `{plan['checks']['token']['status']}` - {plan['checks']['token']['message']}",
            f"- 前端远端访问: `{plan['checks']['remote_frontend']['status']}` - {plan['checks']['remote_frontend']['message']}",
            f"- 后端远端访问: `{plan['checks']['remote_backend']['status']}` - {plan['checks']['remote_backend']['message']}",
            "",
            "## 计划步骤",
        ]

        for index, step in enumerate(plan["plan_steps"], start=1):
            lines.append(f"{index}. {step}")

        lines.extend(["", "## 备注"])
        for note in plan["notes"]:
            lines.append(f"- {note}")
        lines.extend(["", f"生成时间(UTC): `{plan['created_at_utc']}`"])
        return lines


class CsrfAnalysisReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, analysis: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("csrf-analysis", run_id)
        md_path = self.paths.markdown_path("csrf-analysis", run_id)

        json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(analysis)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, analysis: dict) -> list[str]:
        lines = [
            f"# CSRF 风险识别报告 {analysis['run_id']}",
            "",
            "## 汇总",
            f"- 高风险: {analysis['summary'].get('high', 0)}",
            f"- 中风险: {analysis['summary'].get('medium', 0)}",
            f"- 低风险: {analysis['summary'].get('low', 0)}",
            f"- 未知: {analysis['summary'].get('unknown', 0)}",
            "",
        ]

        for repo in analysis["repositories"]:
            self._append_repository(lines, repo)

        lines.append("## 说明")
        for note in analysis["notes"]:
            lines.append(f"- {note}")
        lines.extend(["", f"生成时间(UTC): `{analysis['created_at_utc']}`"])
        return lines

    def _append_repository(self, lines: list[str], repo: dict) -> None:
        lines.extend(
            [
                f"## {repo['role']}",
                f"- 本地路径: `{repo['path']}`",
                f"- 目录存在: `{repo['exists']}`",
                f"- 扫描文件数: `{repo['scanned_files']}`",
                f"- 技术栈判断: {', '.join(repo['detected_stacks']) if repo['detected_stacks'] else '未识别'}",
                "",
                "### 风险项",
            ]
        )

        if repo["risk_items"]:
            for risk in repo["risk_items"]:
                lines.append(f"- `{risk['level']}` {risk['title']}：{risk['detail']}")
        else:
            lines.append("- 暂未发现明显风险项")

        lines.extend(["", "### 命中证据"])
        for check in repo["checks"]:
            evidence = check["evidence"][:5]
            if not evidence:
                lines.append(f"- {check['title']}：未命中")
                continue
            lines.append(f"- {check['title']}：命中 {len(check['evidence'])} 处")
            for item in evidence:
                lines.append(f"  - `{item['file']}:{item['line']}` {item['sample']}")
        lines.append("")


class RepairDecisionReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, decision: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("repair-decision", run_id)
        md_path = self.paths.markdown_path("repair-decision", run_id)

        json_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(decision)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, decision: dict) -> list[str]:
        lines = [
            f"# 修复决策报告 {decision['run_id']}",
            "",
            "## 汇总",
            f"- 决策数量: {decision['summary']['total']}",
            f"- 按优先级: {decision['summary']['by_priority']}",
            f"- 按动作: {decision['summary']['by_action']}",
            f"- 按阶段: {decision['summary']['by_target_phase']}",
            "",
            "## 修复决策",
        ]

        for item in decision["decisions"]:
            lines.extend(self._format_decision(item))

        lines.extend(["", "## 下一步"])
        for action in decision["next_actions"]:
            lines.append(f"- {action}")

        lines.extend(["", "## 说明"])
        for note in decision["notes"]:
            lines.append(f"- {note}")
        lines.extend(["", f"生成时间(UTC): `{decision['created_at_utc']}`"])
        return lines

    def _format_decision(self, item: dict) -> list[str]:
        lines = [
            "",
            f"### {item['id']}",
            f"- 仓库角色: `{item['repo_role']}`",
            f"- 优先级: `{item['priority']}`",
            f"- 目标阶段: `{item['target_phase']}`",
            f"- 动作: `{item['action']}`",
            f"- 来源检查: {item['source_title']}",
            f"- 修复目标: {item['repair_goal']}",
            f"- 决策原因: {item['reason']}",
            "- 建议步骤:",
        ]
        for step in item["suggested_steps"]:
            lines.append(f"  - {step}")

        lines.append("- AI 执行提示:")
        lines.append(f"  - {item['ai_instruction']}")

        if item["evidence"]:
            lines.append("- 参考证据:")
            for evidence in item["evidence"]:
                lines.append(f"  - `{evidence['file']}:{evidence['line']}` {evidence['sample']}")
        return lines


class BackendFixReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("backend-fix", run_id)
        md_path = self.paths.markdown_path("backend-fix", run_id)

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# 后端修复报告 {result['run_id']}",
            "",
            "## 汇总",
            f"- 状态: `{result['status']}`",
            f"- 后端路径: `{result['backend_path']}`",
            f"- 支持栈: `{result['supported_stack'] or '未识别'}`",
            f"- 说明: {result['message']}",
            "",
            "## 改动文件",
        ]

        if result["changed_files"]:
            for file in result["changed_files"]:
                lines.append(f"- `{file}`")
        else:
            lines.append("- 无")

        lines.extend(["", "## 测试命令"])
        lines.append(f"- `{result['test_command'] or '无'}`")

        lines.extend(["", "## 说明"])
        for note in result["notes"]:
            lines.append(f"- {note}")
        lines.extend(["", f"生成时间(UTC): `{result['created_at_utc']}`"])
        return lines


class FrontendFixReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("frontend-fix", run_id)
        md_path = self.paths.markdown_path("frontend-fix", run_id)

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# 前端修复报告 {result['run_id']}",
            "",
            "## 汇总",
            f"- 状态: `{result['status']}`",
            f"- 前端路径: `{result['frontend_path']}`",
            f"- 支持栈: `{result['supported_stack'] or '未识别'}`",
            f"- 说明: {result['message']}",
            "",
            "## 改动文件",
        ]

        if result["changed_files"]:
            for file in result["changed_files"]:
                lines.append(f"- `{file}`")
        else:
            lines.append("- 无")

        lines.extend(["", "## 测试命令"])
        lines.append(f"- `{result['test_command'] or '无'}`")

        lines.extend(["", "## 说明"])
        for note in result["notes"]:
            lines.append(f"- {note}")
        lines.extend(["", f"生成时间(UTC): `{result['created_at_utc']}`"])
        return lines


class CiGateReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("ci-gate", run_id)
        md_path = self.paths.markdown_path("ci-gate", run_id)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# CI 闸门报告 {result['run_id']}",
            "",
            "## 汇总",
            f"- 通过: {result['summary'].get('pass', 0)}",
            f"- 失败: {result['summary'].get('fail', 0)}",
            f"- 跳过: {result['summary'].get('skipped', 0)}",
            f"- 阻断: {result['summary'].get('blocked', 0)}",
            f"- 闸门通过: {result['summary'].get('gate_passed', False)}",
            "",
        ]
        for repository in result.get("repositories", []):
            lines.append(f"## {repository['role']}")
            lines.append(f"- 状态: `{repository['status']}`")
            lines.append(f"- 目录: `{repository['path']}`")
            lines.append(f"- 说明: {repository['message']}")
            if repository.get("detected_projects"):
                lines.append("- 项目目录:")
                for project in repository["detected_projects"]:
                    lines.append(f"  - `{project}`")
            if repository.get("detected_commands"):
                lines.append("- 检查命令:")
                for command in repository["detected_commands"]:
                    lines.append(f"  - `{command}`")
            lines.append("")
        lines.append("## 说明")
        for note in result.get("notes", []):
            lines.append(f"- {note}")
        return lines


class PullRequestReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("pr-automation", run_id)
        md_path = self.paths.markdown_path("pr-automation", run_id)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# 自动提 PR 报告 {result['run_id']}",
            "",
            "## 汇总",
            f"- 成功: {result['summary'].get('pass', 0)}",
            f"- 手动: {result['summary'].get('manual', 0)}",
            f"- 失败: {result['summary'].get('fail', 0)}",
            f"- 跳过: {result['summary'].get('skipped', 0)}",
            f"- 阻断: {result['summary'].get('blocked', 0)}",
            "",
        ]
        for repository in result.get("repositories", []):
            lines.append(f"## {repository['role']}")
            lines.append(f"- 状态: `{repository['status']}`")
            lines.append(f"- 分支: `{repository['branch']}`")
            lines.append(f"- 说明: {repository['message']}")
            if repository.get("detected_projects"):
                lines.append("- 项目目录:")
                for project in repository["detected_projects"]:
                    lines.append(f"  - `{project}`")
            if repository.get("pr_url"):
                lines.append(f"- PR: {repository['pr_url']}")
            if repository.get("manual_pr_command"):
                lines.append(f"- 手动命令: `{repository['manual_pr_command']}`")
            lines.append("")
        lines.append("## 说明")
        for note in result.get("notes", []):
            lines.append(f"- {note}")
        return lines


class MergeExecutionReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("merge-execution", run_id)
        md_path = self.paths.markdown_path("merge-execution", run_id)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# 自动合并报告 {result['run_id']}",
            "",
            "## 汇总",
            f"- 状态: `{result['status']}`",
            f"- 策略: `{result['strategy']}`",
            f"- 执行命令: `{result['execute_merge']}`",
            f"- 说明: {result['message']}",
            "",
        ]
        summary = result.get("summary", {})
        if summary:
            lines.append("## 统计")
            lines.append(f"- 成功: {summary.get('pass', 0)}")
            lines.append(f"- 计划中: {summary.get('planned', 0)}")
            lines.append(f"- 阻断: {summary.get('blocked', 0)}")
            lines.append(f"- 失败: {summary.get('fail', 0)}")
            lines.append("")

        for action in result.get("actions", []):
            lines.append(f"## {action['role']}")
            lines.append(f"- 状态: `{action['status']}`")
            lines.append(f"- PR: {action.get('pr_url', '')}")
            lines.append(f"- 说明: {action['message']}")
            lines.append("")

        lines.append("## 说明")
        for note in result.get("notes", []):
            lines.append(f"- {note}")
        return lines


class AiPatchDraftReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("ai-patch-draft", run_id)
        md_path = self.paths.markdown_path("ai-patch-draft", run_id)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# AI 补丁草案 {result['run_id']}",
            "",
            "## 汇总",
            f"- 状态: `{result.get('status', '')}`",
            f"- 模型: `{result.get('provider', '')}/{result.get('model', '')}`",
            f"- 说明: {result.get('summary', '')}",
            "",
            "## 补丁文件",
        ]
        patches = result.get("patches", [])
        if not patches:
            lines.append("- 无")
        for patch in patches:
            lines.append(f"- 目标: {patch.get('objective', '')}")
            for file_item in patch.get("files", []):
                lines.append(f"- `{file_item.get('role', '')}:{file_item.get('path', '')}` {file_item.get('reason', '')}")

        lines.extend(["", "## 建议测试"])
        tests = result.get("tests", [])
        if not tests:
            lines.append("- 无")
        for item in tests:
            lines.append(f"- {item}")

        lines.extend(["", "## 风险提示"])
        risks = result.get("risks", [])
        if not risks:
            lines.append("- 无")
        for item in risks:
            lines.append(f"- {item}")

        lines.extend(["", "## 说明"])
        for note in result.get("notes", []):
            lines.append(f"- {note}")
        return lines


class AiPatchApplyReportWriter:
    def __init__(self, workspace: Path) -> None:
        self.paths = ReportPathFactory(workspace)

    def write(self, run_id: str, result: dict) -> tuple[Path, Path]:
        self.paths.ensure_dir()
        json_path = self.paths.json_path("ai-patch-apply", run_id)
        md_path = self.paths.markdown_path("ai-patch-apply", run_id)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("\n".join(self._build_markdown(result)), encoding="utf-8")
        return json_path, md_path

    def _build_markdown(self, result: dict) -> list[str]:
        lines = [
            f"# AI 补丁落地 {result['run_id']}",
            "",
            "## 汇总",
            f"- 状态: `{result.get('status', '')}`",
            f"- 已确认: `{result.get('confirmed', False)}`",
            f"- 说明: {result.get('message', '')}",
            "",
            "## 已写入文件",
        ]
        changed_files = result.get("changed_files", [])
        if not changed_files:
            lines.append("- 无")
        for item in changed_files:
            lines.append(f"- `{item.get('role', '')}:{item.get('path', '')}` {item.get('reason', '')}")

        lines.extend(["", "## 跳过文件"])
        skipped_files = result.get("skipped_files", [])
        if not skipped_files:
            lines.append("- 无")
        for item in skipped_files:
            lines.append(f"- `{item.get('role', '')}:{item.get('path', '')}` {item.get('reason', '')}")

        lines.extend(["", "## 说明"])
        for note in result.get("notes", []):
            lines.append(f"- {note}")
        return lines
