from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path


class RunIdFactory:
    def build(self, explicit_run_id: str = "") -> str:
        # 优先使用显式 run_id，用于复现执行过程。
        if explicit_run_id.strip():
            return explicit_run_id.strip()
        return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%SZ")


@dataclass(frozen=True)
class RunConfig:
    frontend: str
    backend: str
    provider: str
    base: str
    auto_merge: str
    workspace: Path
    run_id: str
    branch_prefix: str
    frontend_dir: str
    backend_dir: str
    execute_bootstrap: bool
    require_token: bool
    analyze_csrf: bool
    decide_fixes: bool
    apply_backend_fix: bool
    apply_frontend_fix: bool
    run_ci_gate: bool
    create_pr: bool
    execute_merge: bool
    ai_provider: str
    ai_model: str
    ai_base_url: str
    ai_api_key_env: str
    ai_timeout_seconds: int
    ai_reasoning_effort: str
    ai_decide_fixes: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RunConfig":
        factory = RunIdFactory()
        return cls(
            frontend=args.frontend,
            backend=args.backend,
            provider=args.provider,
            base=args.base,
            auto_merge=args.auto_merge,
            workspace=Path(args.workspace).resolve(),
            run_id=factory.build(args.run_id),
            branch_prefix=args.branch_prefix,
            frontend_dir=args.frontend_dir,
            backend_dir=args.backend_dir,
            execute_bootstrap=args.execute_bootstrap,
            require_token=args.require_token,
            analyze_csrf=args.analyze_csrf,
            decide_fixes=args.decide_fixes,
            apply_backend_fix=args.apply_backend_fix,
            apply_frontend_fix=args.apply_frontend_fix,
            run_ci_gate=args.run_ci_gate,
            create_pr=args.create_pr,
            execute_merge=args.execute_merge,
            ai_provider=args.ai_provider,
            ai_model=args.ai_model,
            ai_base_url=args.ai_base_url,
            ai_api_key_env=args.ai_api_key_env,
            ai_timeout_seconds=max(int(args.ai_timeout_seconds), 5),
            ai_reasoning_effort=args.ai_reasoning_effort,
            ai_decide_fixes=args.ai_decide_fixes,
        )

    @property
    def clean_branch_prefix(self) -> str:
        # 清理分支名前缀中的特殊字符。
        cleaned = re.sub(r"[^A-Za-z0-9/_-]+", "-", self.branch_prefix.strip())
        return cleaned.strip("-") or "ai/csrf-fix"

    @property
    def ai_api_key(self) -> str:
        return os.getenv(self.ai_api_key_env, "").strip()
