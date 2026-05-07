from __future__ import annotations

import argparse
import datetime as dt
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
        )

    @property
    def clean_branch_prefix(self) -> str:
        # 清理分支名前缀中的特殊字符。
        cleaned = re.sub(r"[^A-Za-z0-9/_-]+", "-", self.branch_prefix.strip())
        return cleaned.strip("-") or "ai/csrf-fix"
