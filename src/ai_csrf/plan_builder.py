from __future__ import annotations

import datetime as dt

from .config import RunConfig
from .repository import RepositoryLayoutResult


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
                "decide_fixes": config.decide_fixes,
                "ai_decide_fixes": config.ai_decide_fixes,
                "ai_generate_patch": config.ai_generate_patch,
                "apply_ai_patch": config.apply_ai_patch,
                "validate_ai_patch": config.validate_ai_patch,
                "ai_provider": config.ai_provider,
                "ai_model": config.ai_model,
                "ai_patch_draft_file": config.ai_patch_draft_file,
                "apply_backend_fix": config.apply_backend_fix,
                "apply_frontend_fix": config.apply_frontend_fix,
                "run_ci_gate": config.run_ci_gate,
                "create_pr": config.create_pr,
                "execute_merge": config.execute_merge,
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
