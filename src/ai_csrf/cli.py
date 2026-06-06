from __future__ import annotations

import argparse
import sys

from .config import RunConfig
from .csrf_autopilot_app import CsrfAutopilotApp


class CliParserFactory:
    def build(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="CSRF 自动化命令")
        subparsers = parser.add_subparsers(dest="command", required=True)

        run_parser = subparsers.add_parser("run", help="生成执行计划，或执行仓库准备")
        run_parser.add_argument("--frontend", required=True, help="前端仓库地址")
        run_parser.add_argument("--backend", required=True, help="后端仓库地址")
        run_parser.add_argument("--provider", default="github", choices=["github", "gitlab"], help="平台类型")
        run_parser.add_argument("--base", default="main", help="目标分支")
        run_parser.add_argument("--auto-merge", default="off", choices=["off", "on-green"], help="自动合并策略")
        run_parser.add_argument("--workspace", default=".", help="工作目录")
        run_parser.add_argument("--run-id", default="", help="指定运行 ID")
        run_parser.add_argument("--branch-prefix", default="ai/csrf-fix", help="工作分支前缀")
        run_parser.add_argument("--frontend-dir", default="", help="前端仓库本地目录名（可选）")
        run_parser.add_argument("--backend-dir", default="", help="后端仓库本地目录名（可选）")
        run_parser.add_argument("--execute-bootstrap", action="store_true", help="执行 clone/fetch 与分支准备")
        run_parser.add_argument("--require-token", action="store_true", help="若未检测到令牌则直接失败")
        run_parser.add_argument("--analyze-csrf", action="store_true", help="扫描仓库并生成 CSRF 风险识别报告")
        run_parser.add_argument("--decide-fixes", action="store_true", help="基于扫描结果生成修复决策报告")
        run_parser.add_argument("--apply-backend-fix", action="store_true", help="生成后端 CSRF 修复 MVP 改动")
        run_parser.add_argument("--apply-frontend-fix", action="store_true", help="生成前端 CSRF 修复 MVP 改动")
        run_parser.add_argument("--run-ci-gate", action="store_true", help="执行 CI 闸门检查")
        run_parser.add_argument("--create-pr", action="store_true", help="自动提交改动并创建 PR")
        run_parser.add_argument("--execute-merge", action="store_true", help="执行自动合并命令（需 on-green）")

        run_parser.add_argument("--ai-provider", default="openai", choices=["openai"], help="AI 提供方")
        run_parser.add_argument("--ai-model", default="gpt-5.1-codex-mini", help="AI 模型名称")
        run_parser.add_argument("--ai-base-url", default="https://api.openai.com/v1", help="AI 接口地址")
        run_parser.add_argument("--ai-api-key-env", default="OPENAI_API_KEY", help="保存 API Key 的环境变量名")
        run_parser.add_argument("--ai-timeout-seconds", type=int, default=120, help="AI 请求超时时间（秒）")
        run_parser.add_argument(
            "--ai-reasoning-effort",
            default="low",
            choices=["none", "minimal", "low", "medium", "high", "xhigh"],
            help="AI 推理强度",
        )
        run_parser.add_argument("--ai-decide-fixes", action="store_true", help="使用 AI 生成修复决策")
        run_parser.add_argument("--ai-generate-patch", action="store_true", help="使用 AI 生成补丁草案")
        run_parser.add_argument("--apply-ai-patch", action="store_true", help="确认并落地 AI 补丁草案")
        run_parser.add_argument("--validate-ai-patch", action="store_true", help="AI 补丁落地后执行 CI 闸门验证")
        run_parser.add_argument(
            "--ai-patch-allowlist",
            default="frontend,backend,src,server.js,app.js,index.js,package.json,test,tests,middleware",
            help="允许 AI 补丁写入的相对路径前缀，逗号分隔",
        )
        run_parser.add_argument("--ai-patch-draft-file", default="", help="读取已有 AI 补丁草案 JSON 并复用")
        return parser


class CliApplication:
    def __init__(self, parser_factory: CliParserFactory | None = None) -> None:
        self.parser_factory = parser_factory or CliParserFactory()

    def run(self, argv: list[str] | None = None) -> int:
        parser = self.parser_factory.build()
        args = parser.parse_args(argv)

        try:
            if args.command == "run":
                config = RunConfig.from_args(args)
                return CsrfAutopilotApp(config).run()
            parser.error("不支持的命令")
            return 2
        except (ValueError, RuntimeError) as exc:
            print(f"执行失败: {exc}", file=sys.stderr)
            return 1


def main(argv: list[str] | None = None) -> int:
    return CliApplication().run(argv)
