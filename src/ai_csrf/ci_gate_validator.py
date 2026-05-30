from __future__ import annotations

import json
from pathlib import Path

from .git_client import CommandRunner


class CiGateValidator:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def validate(self, run_id: str, frontend_path: Path, backend_path: Path) -> dict:
        repositories = [
            self._validate_repository("frontend", frontend_path),
            self._validate_repository("backend", backend_path),
        ]
        summary = self._build_summary(repositories)
        return {
            "run_id": run_id,
            "mode": "ci-gate",
            "repositories": repositories,
            "summary": summary,
            "notes": [
                "CI 闸门只在显式传入 --run-ci-gate 时执行。",
                "当前策略是任一仓库检查失败即阻断后续自动合并。",
            ],
        }

    def _validate_repository(self, role: str, repo_path: Path) -> dict:
        result = {
            "role": role,
            "path": str(repo_path),
            "status": "skipped",
            "detected_commands": [],
            "runs": [],
            "message": "",
        }

        if not repo_path.exists():
            result["status"] = "blocked"
            result["message"] = "仓库目录不存在，请先执行仓库准备。"
            return result

        commands = self._detect_commands(repo_path)
        result["detected_commands"] = [" ".join(command) for command in commands]
        if not commands:
            result["status"] = "skipped"
            result["message"] = "未识别到可执行的 CI 检查命令。"
            return result

        has_fail = False
        for command in commands:
            run = self._execute_command(command, repo_path)
            result["runs"].append(run)
            if run["status"] != "pass":
                has_fail = True

        result["status"] = "fail" if has_fail else "pass"
        result["message"] = "检查未通过" if has_fail else "检查通过"
        return result

    def _detect_commands(self, repo_path: Path) -> list[list[str]]:
        commands: list[list[str]] = []

        package_json = repo_path / "package.json"
        if package_json.exists():
            scripts = self._read_package_scripts(package_json)
            if "lint" in scripts:
                commands.append(["npm", "run", "lint"])
            if "test:ci" in scripts:
                commands.append(["npm", "run", "test:ci"])
            elif "test" in scripts:
                commands.append(["npm", "run", "test"])

        has_python_manifest = (repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists()
        if has_python_manifest and (repo_path / "tests").exists():
            commands.append(["python", "-m", "pytest", "-q"])

        if (repo_path / "mvnw.cmd").exists() and (repo_path / "pom.xml").exists():
            commands.append([".\\mvnw.cmd", "-q", "test"])

        return commands

    def _read_package_scripts(self, package_json: Path) -> dict:
        try:
            data = json.loads(package_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        scripts = data.get("scripts", {})
        return scripts if isinstance(scripts, dict) else {}

    def _execute_command(self, command: list[str], repo_path: Path) -> dict:
        raw = self.runner.run(command, cwd=repo_path)
        return {
            "command": " ".join(command),
            "status": "pass" if raw.returncode == 0 else "fail",
            "return_code": raw.returncode,
            "stdout_tail": self._tail(raw.stdout),
            "stderr_tail": self._tail(raw.stderr),
        }

    def _tail(self, text: str, max_lines: int = 20) -> str:
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        return "\n".join(lines[-max_lines:])

    def _build_summary(self, repositories: list[dict]) -> dict:
        summary = {
            "pass": 0,
            "fail": 0,
            "skipped": 0,
            "blocked": 0,
            "gate_passed": False,
        }
        for repository in repositories:
            status = repository["status"]
            summary[status] = summary.get(status, 0) + 1

        summary["gate_passed"] = summary["fail"] == 0 and summary["blocked"] == 0 and summary["pass"] > 0
        return summary
