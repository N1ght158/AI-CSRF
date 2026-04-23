from __future__ import annotations

import argparse
import datetime as dt
import json
import locale
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def build_run_id() -> str:
    # 用 UTC 时间戳做 run_id，排查问题时更容易对齐日志。
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%SZ")


def normalize_repo_url(url: str) -> str:
    # 统一成可读格式，报告里看起来会更整齐。
    text = url.strip()

    scp_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?/?$", text)
    if scp_match:
        host = scp_match.group(1)
        path = scp_match.group(2).strip("/")
        if "/" not in path:
            raise ValueError(f"仓库地址格式不正确: {url}")
        return f"https://{host}/{path}"

    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if "/" not in path:
            raise ValueError(f"仓库地址格式不正确: {url}")
        return f"{parsed.scheme}://{parsed.netloc}/{path}"

    raise ValueError(f"仅支持 http/https 或 git@ 形式的仓库地址: {url}")


def repo_identity(url: str) -> str:
    # 比较远端是否一致时，只看 host/path，忽略 https 或 git@ 的写法差异。
    text = url.strip()
    scp_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?/?$", text)
    if scp_match:
        host = scp_match.group(1).lower()
        path = scp_match.group(2).strip("/").removesuffix(".git")
        return f"{host}/{path}".lower()

    parsed = urlparse(text)
    if parsed.netloc:
        path = parsed.path.strip("/").removesuffix(".git")
        return f"{parsed.netloc.lower()}/{path}".lower()

    return text.lower()


def safe_repo_dir_name(url: str, override: str) -> str:
    # 目录名支持手动覆盖，不传就从仓库地址里推断。
    if override.strip():
        candidate = override.strip()
    else:
        text = url.strip()
        scp_match = re.match(r"^git@[^:]+:(.+?)(?:\.git)?/?$", text)
        if scp_match:
            candidate = scp_match.group(1).split("/")[-1]
        else:
            parsed = urlparse(text)
            candidate = parsed.path.strip("/").split("/")[-1]
            if candidate.endswith(".git"):
                candidate = candidate[:-4]
        if not candidate:
            candidate = "repo"

    name = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-")
    return name or "repo"


def decode_bytes(raw: bytes | None) -> str:
    # Windows 下 git 输出可能是 UTF-8，也可能是本地代码页，这里做个兜底解码。
    if not raw:
        return ""

    encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030", "cp936"]
    seen: set[str] = set()
    ordered = [enc for enc in encodings if not (enc in seen or seen.add(enc))]

    for enc in ordered:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue

    # 都失败时至少保证不抛异常，日志里还能看到大致内容。
    return raw.decode("utf-8", errors="replace")


def run_command(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    raw = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=False,
        capture_output=True,
        check=False,
    )

    return subprocess.CompletedProcess(
        raw.args,
        raw.returncode,
        decode_bytes(raw.stdout),
        decode_bytes(raw.stderr),
    )


def run_git_or_raise(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = run_command(["git", *args], cwd=cwd)
    if result.returncode != 0:
        joined = " ".join(["git", *args])
        raise RuntimeError(
            f"{joined} 执行失败\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def check_git_cli() -> dict:
    result = run_command(["git", "--version"])
    if result.returncode == 0:
        return {"status": "pass", "message": result.stdout.strip()}
    return {"status": "fail", "message": result.stderr.strip() or "未检测到可用的 git 命令"}


def check_token(provider: str) -> dict:
    env_map = {
        "github": ["GITHUB_TOKEN", "GH_TOKEN"],
        "gitlab": ["GITLAB_TOKEN", "GLAB_TOKEN"],
    }
    checked = env_map[provider]
    found = [name for name in checked if os.getenv(name)]

    if found:
        return {
            "status": "pass",
            "checked_env": checked,
            "found_env": found,
            "message": f"检测到令牌变量: {', '.join(found)}",
        }

    return {
        "status": "warn",
        "checked_env": checked,
        "found_env": [],
        "message": "未检测到令牌变量；若仓库是私有库，后续访问可能失败",
    }


def check_remote_access(repo_url: str) -> dict:
    # 用 ls-remote 做最轻量的连通性检查，不会改仓库内容。
    result = run_command(["git", "ls-remote", repo_url, "HEAD"])
    if result.returncode == 0:
        return {"status": "pass", "message": "远端可访问"}
    message = result.stderr.strip() or result.stdout.strip() or "未知错误"
    return {"status": "fail", "message": message}


def ensure_repo_ready(repo_url: str, local_path: Path, base_branch: str, work_branch: str) -> None:
    # 这个步骤只做拉取和切分支，不写业务代码。
    if local_path.exists():
        if not (local_path / ".git").exists():
            raise RuntimeError(f"目录已存在但不是 git 仓库: {local_path}")

        origin = run_git_or_raise(["remote", "get-url", "origin"], cwd=local_path).stdout.strip()
        if repo_identity(origin) != repo_identity(repo_url):
            raise RuntimeError(
                "本地仓库 origin 与输入地址不一致，已停止执行。\n"
                f"本地 origin: {origin}\n"
                f"输入地址: {repo_url}"
            )

        run_git_or_raise(["fetch", "origin"], cwd=local_path)
    else:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        run_git_or_raise(["clone", repo_url, str(local_path)])

    run_git_or_raise(["fetch", "origin", base_branch], cwd=local_path)
    run_git_or_raise(["checkout", "-B", work_branch, f"origin/{base_branch}"], cwd=local_path)


def build_plan_base(args: argparse.Namespace, run_id: str, frontend_repo: str, backend_repo: str) -> dict:
    created_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "run_id": run_id,
        "created_at_utc": created_at,
        "mode": "bootstrap" if args.execute_bootstrap else "dry-run",
        "inputs": {
            "frontend_repo": frontend_repo,
            "backend_repo": backend_repo,
            "provider": args.provider,
            "base_branch": args.base,
            "auto_merge": args.auto_merge,
        },
        "repo_setup": {},
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


def write_outputs(workspace: Path, run_id: str, plan: dict) -> tuple[Path, Path]:
    reports_dir = workspace / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / f"run-plan-{run_id}.json"
    md_path = reports_dir / f"run-plan-{run_id}.md"

    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 执行计划 {run_id}",
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
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def run_pipeline(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    run_id = args.run_id or build_run_id()

    frontend_repo = normalize_repo_url(args.frontend)
    backend_repo = normalize_repo_url(args.backend)

    repos_root = workspace / "repos"
    frontend_local = repos_root / safe_repo_dir_name(args.frontend, args.frontend_dir)
    backend_local = repos_root / safe_repo_dir_name(args.backend, args.backend_dir)

    branch_prefix = args.branch_prefix.strip() or "ai/csrf-fix"
    branch_prefix = re.sub(r"[^A-Za-z0-9/_-]+", "-", branch_prefix).strip("-") or "ai/csrf-fix"
    frontend_branch = f"{branch_prefix}-frontend-{run_id}"
    backend_branch = f"{branch_prefix}-backend-{run_id}"

    plan = build_plan_base(args, run_id, frontend_repo, backend_repo)
    plan["repo_setup"] = {
        "frontend_local_path": str(frontend_local),
        "backend_local_path": str(backend_local),
        "frontend_branch": frontend_branch,
        "backend_branch": backend_branch,
    }

    plan["checks"]["git_cli"] = check_git_cli()
    plan["checks"]["token"] = check_token(args.provider)

    if args.execute_bootstrap:
        if plan["checks"]["git_cli"]["status"] != "pass":
            raise ValueError("未检测到可用的 git 命令，无法执行仓库准备")
        if args.require_token and plan["checks"]["token"]["status"] != "pass":
            raise ValueError("已启用 require-token，但未检测到可用令牌变量")

        plan["checks"]["remote_frontend"] = check_remote_access(args.frontend)
        plan["checks"]["remote_backend"] = check_remote_access(args.backend)

        if plan["checks"]["remote_frontend"]["status"] != "pass":
            raise ValueError(f"前端仓库访问失败: {plan['checks']['remote_frontend']['message']}")
        if plan["checks"]["remote_backend"]["status"] != "pass":
            raise ValueError(f"后端仓库访问失败: {plan['checks']['remote_backend']['message']}")

        ensure_repo_ready(args.frontend, frontend_local, args.base, frontend_branch)
        ensure_repo_ready(args.backend, backend_local, args.base, backend_branch)
        plan["notes"].append("仓库准备已执行：前后端仓库已完成 clone/fetch 与分支切换")
    else:
        plan["checks"]["remote_frontend"] = {"status": "skipped", "message": "未执行远端访问检查（dry-run）"}
        plan["checks"]["remote_backend"] = {"status": "skipped", "message": "未执行远端访问检查（dry-run）"}
        plan["notes"].append("当前仅生成执行计划，不会拉取远端仓库")
        plan["notes"].append("如需执行仓库准备，请追加 --execute-bootstrap")

    json_path, md_path = write_outputs(workspace, run_id, plan)

    print(f"run_id: {run_id}")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    if args.execute_bootstrap:
        print("状态: 仓库准备完成（clone/fetch + 分支创建）")
    else:
        print("状态: 已生成执行计划（dry-run）")
    return 0


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "run":
            return run_pipeline(args)
        parser.error("不支持的命令")
        return 2
    except (ValueError, RuntimeError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
