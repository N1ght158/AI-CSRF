from __future__ import annotations

import os

from .git_client import GitClient


class EnvironmentChecker:
    TOKEN_ENV = {
        "github": ["GITHUB_TOKEN", "GH_TOKEN"],
        "gitlab": ["GITLAB_TOKEN", "GLAB_TOKEN"],
    }

    def __init__(self, git: GitClient) -> None:
        self.git = git

    def check_git_cli(self) -> dict:
        result = self.git.version()
        if result.returncode == 0:
            return {"status": "pass", "message": result.stdout.strip()}
        return {"status": "fail", "message": result.stderr.strip() or "未检测到可用的 git 命令"}

    def check_token(self, provider: str) -> dict:
        checked = self.TOKEN_ENV[provider]
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

    def check_remote_access(self, repo_url: str) -> dict:
        # 使用 ls-remote 做远端连通性检查。
        result = self.git.ls_remote_head(repo_url)
        if result.returncode == 0:
            return {"status": "pass", "message": "远端可访问"}

        message = result.stderr.strip() or result.stdout.strip() or "未知错误"
        return {"status": "fail", "message": message}
