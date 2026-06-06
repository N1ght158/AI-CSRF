from __future__ import annotations

from pathlib import Path

from .ai_patch_applier import AiPatchApplier
from .ai_patch_draft_generator import AiPatchDraftGenerator, AiPatchDraftLoader
from .ai_repair_decision_engine import AiRepairDecisionEngine
from .auto_merge_executor import AutoMergeExecutor
from .backend_fixer import BackendFixer
from .checks import EnvironmentChecker
from .ci_gate_validator import CiGateValidator
from .config import RunConfig
from .csrf_analyzer import CsrfAnalyzer
from .frontend_fixer import FrontendFixer
from .git_client import GitClient
from .plan_builder import PlanBuilder
from .pull_request_creator import PullRequestCreator
from .repository import RepositoryBootstrapper, RepositoryLayout, RepositoryLayoutResult
from .repair_decision import RepairDecisionEngine
from .reports import (
    AiPatchApplyReportWriter,
    AiPatchDraftReportWriter,
    BackendFixReportWriter,
    CiGateReportWriter,
    CsrfAnalysisReportWriter,
    ExecutionPlanReportWriter,
    FrontendFixReportWriter,
    MergeExecutionReportWriter,
    PullRequestReportWriter,
    RepairDecisionReportWriter,
)


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

        plan_json, plan_md = ExecutionPlanReportWriter(self.config.workspace).write(self.config.run_id, plan)
        self._print_plan_outputs(plan_json, plan_md)

        analysis: dict | None = None
        if self._need_analysis():
            analysis = self._build_analysis(layout)
            analysis_json, analysis_md = self._write_analysis(analysis)
            print(f"analysis_json: {analysis_json}")
            print(f"analysis_markdown: {analysis_md}")

        decision_result: dict | None = None
        if analysis and self._need_decision():
            decision_result, decision_json, decision_md = self._write_repair_decision(analysis)
            print(f"decision_json: {decision_json}")
            print(f"decision_markdown: {decision_md}")

        ai_patch_draft: dict | None = None
        if self._need_ai_patch_draft() and (decision_result or self._has_ai_patch_draft_file()):
            ai_patch_draft, draft_json, draft_md = self._write_ai_patch_draft(decision_result, layout)
            print(f"ai_patch_draft_json: {draft_json}")
            print(f"ai_patch_draft_markdown: {draft_md}")

        ai_patch_apply: dict | None = None
        if ai_patch_draft and self.config.apply_ai_patch:
            ai_patch_apply, apply_json, apply_md = self._apply_ai_patch(ai_patch_draft, layout)
            print(f"ai_patch_apply_json: {apply_json}")
            print(f"ai_patch_apply_markdown: {apply_md}")

        if self.config.apply_backend_fix:
            backend_json, backend_md = self._apply_backend_fix(layout)
            print(f"backend_fix_json: {backend_json}")
            print(f"backend_fix_markdown: {backend_md}")

        if self.config.apply_frontend_fix:
            frontend_json, frontend_md = self._apply_frontend_fix(layout)
            print(f"frontend_fix_json: {frontend_json}")
            print(f"frontend_fix_markdown: {frontend_md}")

        ci_result: dict | None = None
        if self.config.run_ci_gate or self.config.validate_ai_patch:
            ci_result = CiGateValidator().validate(self.config.run_id, layout.frontend.local_path, layout.backend.local_path)
            ci_json, ci_md = CiGateReportWriter(self.config.workspace).write(self.config.run_id, ci_result)
            print(f"ci_gate_json: {ci_json}")
            print(f"ci_gate_markdown: {ci_md}")

        pr_result: dict | None = None
        if self.config.create_pr:
            pr_result = PullRequestCreator(self.git).create(
                self.config.run_id,
                self.config.provider,
                self.config.base,
                layout.frontend,
                layout.backend,
                ai_evidence={
                    "decision": decision_result,
                    "patch_draft": ai_patch_draft,
                    "patch_apply": ai_patch_apply,
                    "ci_result": ci_result,
                },
            )
            pr_json, pr_md = PullRequestReportWriter(self.config.workspace).write(self.config.run_id, pr_result)
            print(f"pr_json: {pr_json}")
            print(f"pr_markdown: {pr_md}")

        if self.config.auto_merge == "on-green" or self.config.execute_merge:
            merge_result = AutoMergeExecutor().execute(
                self.config.run_id,
                self.config.provider,
                self.config.auto_merge,
                self.config.execute_merge,
                ci_result,
                pr_result,
            )
            merge_json, merge_md = MergeExecutionReportWriter(self.config.workspace).write(self.config.run_id, merge_result)
            print(f"merge_json: {merge_json}")
            print(f"merge_markdown: {merge_md}")

        self._print_status()
        return 0

    def _need_analysis(self) -> bool:
        return (
            self.config.analyze_csrf
            or self.config.decide_fixes
            or self.config.ai_decide_fixes
            or self.config.ai_generate_patch
            or (self.config.apply_ai_patch and not self._has_ai_patch_draft_file())
            or self.config.apply_backend_fix
            or self.config.apply_frontend_fix
            or self.config.run_ci_gate
            or self.config.create_pr
            or self.config.auto_merge == "on-green"
            or self.config.execute_merge
        )

    def _need_decision(self) -> bool:
        return (
            self.config.decide_fixes
            or self.config.ai_decide_fixes
            or self.config.ai_generate_patch
            or (self.config.apply_ai_patch and not self._has_ai_patch_draft_file())
            or self.config.apply_backend_fix
            or self.config.apply_frontend_fix
            or self.config.create_pr
            or self.config.auto_merge == "on-green"
            or self.config.execute_merge
        )

    def _need_ai_patch_draft(self) -> bool:
        return self.config.ai_generate_patch or self.config.apply_ai_patch or self._has_ai_patch_draft_file()

    def _has_ai_patch_draft_file(self) -> bool:
        return bool(self.config.ai_patch_draft_file.strip())

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
        plan["checks"]["remote_frontend"] = {"status": "skipped", "message": "未执行远端访问检查"}
        plan["checks"]["remote_backend"] = {"status": "skipped", "message": "未执行远端访问检查"}
        if self._has_followup_actions():
            plan["notes"].append("未执行仓库准备，后续步骤会使用已有本地仓库目录")
        else:
            plan["notes"].append("当前仅生成执行计划，不会拉取远端仓库")
        plan["notes"].append("如需执行仓库准备，请追加 --execute-bootstrap")

    def _has_followup_actions(self) -> bool:
        return (
            self._need_analysis()
            or self._need_ai_patch_draft()
            or self.config.apply_backend_fix
            or self.config.apply_frontend_fix
            or self.config.run_ci_gate
            or self.config.validate_ai_patch
            or self.config.create_pr
            or self.config.auto_merge == "on-green"
            or self.config.execute_merge
        )

    def _build_analysis(self, layout: RepositoryLayoutResult) -> dict:
        return self.analyzer.analyze(
            self.config.run_id,
            layout.frontend.local_path,
            layout.backend.local_path,
        )

    def _write_analysis(self, analysis: dict) -> tuple[Path, Path]:
        return CsrfAnalysisReportWriter(self.config.workspace).write(self.config.run_id, analysis)

    def _write_repair_decision(self, analysis: dict) -> tuple[dict, Path, Path]:
        if self.config.ai_decide_fixes:
            decision = AiRepairDecisionEngine.from_config(self.config).build(self.config.run_id, analysis)
        else:
            decision = RepairDecisionEngine().build(self.config.run_id, analysis)
        json_path, md_path = RepairDecisionReportWriter(self.config.workspace).write(self.config.run_id, decision)
        return decision, json_path, md_path

    def _write_ai_patch_draft(self, decision: dict | None, layout: RepositoryLayoutResult) -> tuple[dict, Path, Path]:
        if self._has_ai_patch_draft_file():
            draft = AiPatchDraftLoader().load(
                self.config.run_id,
                self.config.ai_patch_draft_file,
                self.config.workspace,
            )
        elif decision is not None:
            draft = AiPatchDraftGenerator.from_config(self.config).build(
                self.config.run_id,
                decision,
                layout.frontend.local_path,
                layout.backend.local_path,
            )
        else:
            raise ValueError("缺少修复决策，无法生成 AI 补丁草案。")

        json_path, md_path = AiPatchDraftReportWriter(self.config.workspace).write(self.config.run_id, draft)
        return draft, json_path, md_path

    def _apply_ai_patch(self, draft: dict, layout: RepositoryLayoutResult) -> tuple[dict, Path, Path]:
        result = AiPatchApplier(self.config.ai_patch_allowlist).apply(
            self.config.run_id,
            draft,
            layout.frontend.local_path,
            layout.backend.local_path,
            confirmed=self.config.apply_ai_patch,
        )
        json_path, md_path = AiPatchApplyReportWriter(self.config.workspace).write(self.config.run_id, result)
        return result, json_path, md_path

    def _apply_backend_fix(self, layout: RepositoryLayoutResult) -> tuple[Path, Path]:
        result = BackendFixer().apply(self.config.run_id, layout.backend.local_path)
        return BackendFixReportWriter(self.config.workspace).write(self.config.run_id, result)

    def _apply_frontend_fix(self, layout: RepositoryLayoutResult) -> tuple[Path, Path]:
        result = FrontendFixer().apply(self.config.run_id, layout.frontend.local_path)
        return FrontendFixReportWriter(self.config.workspace).write(self.config.run_id, result)

    def _print_plan_outputs(self, json_path: Path, md_path: Path) -> None:
        print(f"run_id: {self.config.run_id}")
        print(f"json: {json_path}")
        print(f"markdown: {md_path}")

    def _print_status(self) -> None:
        if self.config.execute_bootstrap:
            print("状态: 仓库准备完成（clone/fetch + 分支创建）")
        elif self._has_followup_actions():
            print("状态: 未执行仓库准备（使用已有本地仓库目录）")
        else:
            print("状态: 已生成执行计划（dry-run）")
        if self._need_analysis():
            print("状态: 已生成 CSRF 风险识别报告")
        if self._need_decision():
            print("状态: 已生成修复决策报告")
        if self.config.ai_decide_fixes:
            print(f"状态: 已接入 AI 决策（{self.config.ai_provider}/{self.config.ai_model}）")
        if self.config.ai_generate_patch:
            print("状态: 已生成 AI 补丁草案")
        if self.config.apply_ai_patch:
            print("状态: 已处理 AI 补丁落地")
        if self.config.apply_backend_fix:
            print("状态: 已处理后端修复 MVP")
        if self.config.apply_frontend_fix:
            print("状态: 已处理前端修复 MVP")
        if self.config.run_ci_gate or self.config.validate_ai_patch:
            print("状态: 已执行 CI 闸门检查")
        if self.config.create_pr:
            print("状态: 已执行自动提 PR 流程")
        if self.config.auto_merge == "on-green" or self.config.execute_merge:
            print("状态: 已执行自动合并评估")
