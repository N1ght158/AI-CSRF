from __future__ import annotations

import locale
import subprocess
from dataclasses import dataclass
from pathlib import Path


class TextDecoder:
    def __init__(self) -> None:
        encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030", "cp936"]
        seen: set[str] = set()
        self.encodings = [item for item in encodings if not (item in seen or seen.add(item))]

    def decode(self, raw: bytes | None) -> str:
        # 兼容 Windows 下不同编码的命令输出。
        if not raw:
            return ""

        for encoding in self.encodings:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue

        return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(self, decoder: TextDecoder | None = None) -> None:
        self.decoder = decoder or TextDecoder()

    def run(self, cmd: list[str], cwd: Path | None = None) -> CommandResult:
        raw = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=False,
            capture_output=True,
            check=False,
        )
        return CommandResult(
            args=list(raw.args),
            returncode=raw.returncode,
            stdout=self.decoder.decode(raw.stdout),
            stderr=self.decoder.decode(raw.stderr),
        )


class GitClient:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def run(self, args: list[str], cwd: Path | None = None) -> CommandResult:
        return self.runner.run(["git", *args], cwd=cwd)

    def run_or_raise(self, args: list[str], cwd: Path | None = None) -> CommandResult:
        result = self.run(args, cwd=cwd)
        if result.returncode == 0:
            return result

        joined = " ".join(["git", *args])
        raise RuntimeError(
            f"{joined} 执行失败\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def version(self) -> CommandResult:
        return self.run(["--version"])

    def ls_remote_head(self, repo_url: str) -> CommandResult:
        return self.run(["ls-remote", repo_url, "HEAD"])

    def clone(self, repo_url: str, local_path: Path) -> None:
        self.run_or_raise(["clone", repo_url, str(local_path)])

    def fetch(self, local_path: Path, branch: str | None = None) -> None:
        args = ["fetch", "origin"]
        if branch:
            args.append(branch)
        self.run_or_raise(args, cwd=local_path)

    def origin_url(self, local_path: Path) -> str:
        return self.run_or_raise(["remote", "get-url", "origin"], cwd=local_path).stdout.strip()

    def checkout_work_branch(self, local_path: Path, work_branch: str, base_branch: str) -> None:
        self.run_or_raise(["checkout", "-B", work_branch, f"origin/{base_branch}"], cwd=local_path)
