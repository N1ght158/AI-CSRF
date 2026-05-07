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
