from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import RunConfig
from .git_client import GitClient


class RepositoryUrl:
    def __init__(self, raw_url: str) -> None:
        self.raw_url = raw_url

    def normalized(self) -> str:
        # 将仓库地址规范化为统一的 https 展示格式。
        text = self.raw_url.strip()
        scp_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?/?$", text)
        if scp_match:
            host = scp_match.group(1)
            path = scp_match.group(2).strip("/")
            if "/" not in path:
                raise ValueError(f"仓库地址格式不正确: {self.raw_url}")
            return f"https://{host}/{path}"

        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            path = parsed.path.strip("/")
            if path.endswith(".git"):
                path = path[:-4]
            if "/" not in path:
                raise ValueError(f"仓库地址格式不正确: {self.raw_url}")
            return f"{parsed.scheme}://{parsed.netloc}/{path}"

        raise ValueError(f"仅支持 http/https 或 git@ 形式的仓库地址: {self.raw_url}")

    def identity(self) -> str:
        # 统一远端标识，忽略协议写法差异。
        text = self.raw_url.strip()
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

    def safe_dir_name(self, override: str = "") -> str:
        # 生成安全的本地仓库目录名。
        candidate = override.strip() if override.strip() else self._guess_repo_name()
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-")
        return name or "repo"

    def _guess_repo_name(self) -> str:
        text = self.raw_url.strip()
        scp_match = re.match(r"^git@[^:]+:(.+?)(?:\.git)?/?$", text)
        if scp_match:
            return scp_match.group(1).split("/")[-1]

        parsed = urlparse(text)
        candidate = parsed.path.strip("/").split("/")[-1]
        return candidate.removesuffix(".git") or "repo"


@dataclass(frozen=True)
class RepositoryTarget:
    role: str
    input_url: str
    normalized_url: str
    local_path: Path
    work_branch: str

    @property
    def identity(self) -> str:
        return RepositoryUrl(self.input_url).identity()


@dataclass(frozen=True)
class RepositoryLayoutResult:
    frontend: RepositoryTarget
    backend: RepositoryTarget


class RepositoryLayout:
    def __init__(self, config: RunConfig) -> None:
        self.config = config

    def build(self) -> RepositoryLayoutResult:
        repos_root = self.config.workspace / "repos"
        frontend_url = RepositoryUrl(self.config.frontend)
        backend_url = RepositoryUrl(self.config.backend)

        return RepositoryLayoutResult(
            frontend=RepositoryTarget(
                role="frontend",
                input_url=self.config.frontend,
                normalized_url=frontend_url.normalized(),
                local_path=repos_root / frontend_url.safe_dir_name(self.config.frontend_dir),
                work_branch=f"{self.config.clean_branch_prefix}-frontend-{self.config.run_id}",
            ),
            backend=RepositoryTarget(
                role="backend",
                input_url=self.config.backend,
                normalized_url=backend_url.normalized(),
                local_path=repos_root / backend_url.safe_dir_name(self.config.backend_dir),
                work_branch=f"{self.config.clean_branch_prefix}-backend-{self.config.run_id}",
            ),
        )


class RepositoryBootstrapper:
    def __init__(self, git: GitClient) -> None:
        self.git = git

    def prepare(self, target: RepositoryTarget, base_branch: str) -> None:
        # 只执行仓库拉取和分支切换，不修改业务代码。
        if target.local_path.exists():
            self._validate_existing_repo(target)
            self.git.fetch(target.local_path)
        else:
            target.local_path.parent.mkdir(parents=True, exist_ok=True)
            self.git.clone(target.input_url, target.local_path)

        self.git.fetch(target.local_path, base_branch)
        self.git.checkout_work_branch(target.local_path, target.work_branch, base_branch)

    def _validate_existing_repo(self, target: RepositoryTarget) -> None:
        if not (target.local_path / ".git").exists():
            raise RuntimeError(f"目录已存在但不是 git 仓库: {target.local_path}")

        origin = self.git.origin_url(target.local_path)
        if RepositoryUrl(origin).identity() == target.identity:
            return

        raise RuntimeError(
            "本地仓库 origin 与输入地址不一致，已停止执行。\n"
            f"本地 origin: {origin}\n"
            f"输入地址: {target.input_url}"
        )
