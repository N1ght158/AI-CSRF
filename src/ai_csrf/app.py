from __future__ import annotations

import datetime as dt
from pathlib import Path

from .checks import EnvironmentChecker
from .config import RunConfig
from .csrf_analyzer import CsrfAnalyzer
from .git_client import GitClient
from .repository import RepositoryBootstrapper, RepositoryLayout, RepositoryLayoutResult
from .reports import CsrfAnalysisReportWriter, ExecutionPlanReportWriter


class PlanBuilder:
    def build(self, config: RunConfig, layout: RepositoryLayoutResult) -> dict:
        created_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return {
            "run_id": config.run_id,
            "created_at_utc": created_at,
            "mode": "bootstrap" if config.execute_bootstrap else "dry-run",
            "inputs": {
                "frontend_repo": layout.frontend.normalized_url,
                "backend_repo": layout.backend.normalized_url,
                "provider": config.provider,
                "base_branch": config.base,
                "auto_merge": config.auto_merge,
                "analyze_csrf": config.analyze_csrf,
            },
            "repo_setup": {
                "frontend_local_path": str(layout.frontend.local_path),
                "backend_local_path": str(layout.backend.local_path),
                "frontend_branch": layout.frontend.work_branch,
                "backend_branch": layout.backend.work_branch,
            },
            "checks": {},
            "plan_steps": [
                "校验参数与本地运行环境",
                "检查令牌变量与远端访问能力",
                "准备前后端仓库（clone/fetch）",
                "创建工作分支并切换到目标基线",
                "输出后续修复流程的执行计划",
            ],
            "notes": [],
        }


class CsrfAutopilotApp:
    def __init__(
        self,
        config: RunConfig,
        git: GitClient | None = None,
        analyzer: CsrfAnalyzer | None = None,
    ) -> None:
        self.config = config
        self.git = git or GitClient()
        self.checker = EnvironmentChecker(self.git)
        self.bootstrapper = RepositoryBootstrapper(self.git)
        self.analyzer = analyzer or CsrfAnalyzer()
        self.plan_builder = PlanBuilder()

    def run(self) -> int:
        layout = RepositoryLayout(self.config).build()
        plan = self.plan_builder.build(self.config, layout)
        self._fill_common_checks(plan)

        if self.config.execute_bootstrap:
            self._prepare_repositories(plan, layout)
        else:
            self._mark_dry_run(plan)

        json_path, md_path = ExecutionPlanReportWriter(self.config.workspace).write(self.config.run_id, plan)
        self._print_plan_outputs(json_path, md_path)

        if self.config.analyze_csrf:
            analysis_json, analysis_md = self._write_analysis(layout)
            print(f"analysis_json: {analysis_json}")
            print(f"analysis_markdown: {analysis_md}")

        self._print_status()
        return 0

    def _fill_common_checks(self, plan: dict) -> None:
        plan["checks"]["git_cli"] = self.checker.check_git_cli()
        plan["checks"]["token"] = self.checker.check_token(self.config.provider)

    def _prepare_repositories(self, plan: dict, layout: RepositoryLayoutResult) -> None:
        if plan["checks"]["git_cli"]["status"] != "pass":
            raise ValueError("未检测到可用的 git 命令，无法执行仓库准备")
        if self.config.require_token and plan["checks"]["token"]["status"] != "pass":
            raise ValueError("已启用 require-token，但未检测到可用令牌变量")

        plan["checks"]["remote_frontend"] = self.checker.check_remote_access(layout.frontend.input_url)
        plan["checks"]["remote_backend"] = self.checker.check_remote_access(layout.backend.input_url)

        if plan["checks"]["remote_frontend"]["status"] != "pass":
            raise ValueError(f"前端仓库访问失败: {plan['checks']['remote_frontend']['message']}")
        if plan["checks"]["remote_backend"]["status"] != "pass":
            raise ValueError(f"后端仓库访问失败: {plan['checks']['remote_backend']['message']}")

        self.bootstrapper.prepare(layout.frontend, self.config.base)
        self.bootstrapper.prepare(layout.backend, self.config.base)
        plan["notes"].append("仓库准备已执行：前后端仓库已完成 clone/fetch 与分支切换")

    def _mark_dry_run(self, plan: dict) -> None:
        plan["checks"]["remote_frontend"] = {"status": "skipped", "message": "未执行远端访问检查（dry-run）"}
        plan["checks"]["remote_backend"] = {"status": "skipped", "message": "未执行远端访问检查（dry-run）"}
        plan["notes"].append("当前仅生成执行计划，不会拉取远端仓库")
        plan["notes"].append("如需执行仓库准备，请追加 --execute-bootstrap")

    def _write_analysis(self, layout: RepositoryLayoutResult) -> tuple[Path, Path]:
        analysis = self.analyzer.analyze(
            self.config.run_id,
            layout.frontend.local_path,
            layout.backend.local_path,
        )
        return CsrfAnalysisReportWriter(self.config.workspace).write(self.config.run_id, analysis)

    def _print_plan_outputs(self, json_path: Path, md_path: Path) -> None:
        print(f"run_id: {self.config.run_id}")
        print(f"json: {json_path}")
        print(f"markdown: {md_path}")

    def _print_status(self) -> None:
        if self.config.execute_bootstrap:
            print("状态: 仓库准备完成（clone/fetch + 分支创建）")
        else:
            print("状态: 已生成执行计划（dry-run）")
        if self.config.analyze_csrf:
            print("状态: 已生成 CSRF 风险识别报告")
