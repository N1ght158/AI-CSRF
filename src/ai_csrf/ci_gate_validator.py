from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .git_client import CommandRunner
from .rules import IGNORE_DIRS


@dataclass(frozen=True)
class DetectedCiCommand:
    command: list[str]
    cwd: Path
    label: str


class CiProjectFinder:
    def find(self, repo_path: Path) -> list[Path]:
        if not repo_path.exists():
            return []

        projects: list[Path] = []
        self._append_if_project(projects, repo_path)
        for manifest in self._find_manifests(repo_path):
            self._append_if_project(projects, manifest.parent)
        return projects

    def _find_manifests(self, repo_path: Path) -> list[Path]:
        manifests: list[Path] = []
        for path in repo_path.rglob("*"):
            if len(manifests) >= 12:
                break
            if not path.is_file() or path.name not in {"package.json", "requirements.txt", "pyproject.toml", "pom.xml"}:
                continue
            relative = path.relative_to(repo_path)
            if any(part in IGNORE_DIRS or part in {".git", "node_modules", "dist", "build", "coverage"} for part in relative.parts):
                continue
            manifests.append(path)
        return manifests

    def _append_if_project(self, projects: list[Path], path: Path) -> None:
        if path not in projects and self._has_manifest(path):
            projects.append(path)

    def _has_manifest(self, path: Path) -> bool:
        return any((path / name).exists() for name in {"package.json", "requirements.txt", "pyproject.toml", "pom.xml"})


class NpmCommandResolver:
    def command(self) -> str:
        # Windows 下直接执行 npm 可能会碰到 npm.ps1 策略限制，npm.cmd 更稳定。
        return "npm.cmd" if os.name == "nt" else "npm"


class CiCommandDetector:
    def __init__(
        self,
        project_finder: CiProjectFinder | None = None,
        npm_resolver: NpmCommandResolver | None = None,
    ) -> None:
        self.project_finder = project_finder or CiProjectFinder()
        self.npm_resolver = npm_resolver or NpmCommandResolver()

    def find_projects(self, repo_path: Path) -> list[Path]:
        return self.project_finder.find(repo_path)

    def detect(self, repo_path: Path, projects: list[Path] | None = None) -> list[DetectedCiCommand]:
        commands: list[DetectedCiCommand] = []
        for project_path in projects if projects is not None else self.project_finder.find(repo_path):
            commands.extend(self._detect_for_project(repo_path, project_path))
        return commands

    def _detect_for_project(self, repo_path: Path, project_path: Path) -> list[DetectedCiCommand]:
        commands: list[DetectedCiCommand] = []

        package_json = project_path / "package.json"
        if package_json.exists():
            scripts = self._read_package_scripts(package_json)
            npm = self.npm_resolver.command()
            if "lint" in scripts:
                commands.append(self._command(repo_path, project_path, [npm, "run", "lint"]))
            if "test:ci" in scripts:
                commands.append(self._command(repo_path, project_path, [npm, "run", "test:ci"]))
            elif "test" in scripts:
                commands.append(self._command(repo_path, project_path, [npm, "run", "test"]))

        has_python_manifest = (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists()
        if has_python_manifest and (project_path / "tests").exists():
            commands.append(self._command(repo_path, project_path, ["python", "-m", "pytest", "-q"]))

        if (project_path / "mvnw.cmd").exists() and (project_path / "pom.xml").exists():
            commands.append(self._command(repo_path, project_path, [".\\mvnw.cmd", "-q", "test"]))

        return commands

    def _command(self, repo_path: Path, cwd: Path, command: list[str]) -> DetectedCiCommand:
        relative = self._relative_label(repo_path, cwd)
        label = " ".join(command) if relative == "." else f"{relative}> {' '.join(command)}"
        return DetectedCiCommand(command=command, cwd=cwd, label=label)

    def _relative_label(self, repo_path: Path, cwd: Path) -> str:
        try:
            relative = cwd.relative_to(repo_path)
        except ValueError:
            return str(cwd)
        return relative.as_posix() if relative.parts else "."

    def _read_package_scripts(self, package_json: Path) -> dict:
        try:
            data = json.loads(package_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        scripts = data.get("scripts", {})
        return scripts if isinstance(scripts, dict) else {}


class CiGateValidator:
    def __init__(self, runner: CommandRunner | None = None, detector: CiCommandDetector | None = None) -> None:
        self.runner = runner or CommandRunner()
        self.detector = detector or CiCommandDetector()

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
                "CI 闸门只在显式传入 --run-ci-gate 或 --validate-ai-patch 时执行。",
                "当前策略是任一仓库检查失败即阻断后续自动合并。",
            ],
        }

    def _validate_repository(self, role: str, repo_path: Path) -> dict:
        result = {
            "role": role,
            "path": str(repo_path),
            "status": "skipped",
            "detected_commands": [],
            "detected_projects": [],
            "runs": [],
            "message": "",
        }

        if not repo_path.exists():
            result["status"] = "blocked"
            result["message"] = "仓库目录不存在，请先执行仓库准备。"
            return result

        projects = self.detector.find_projects(repo_path)
        commands = self.detector.detect(repo_path, projects)
        result["detected_projects"] = [self._relative_label(repo_path, project) for project in projects]
        result["detected_commands"] = [command.label for command in commands]
        if not commands:
            result["status"] = "skipped"
            if projects:
                result["message"] = "已识别项目目录，但未发现 lint/test/test:ci 等可执行检查脚本。"
            else:
                result["message"] = "未识别到可执行的 CI 检查命令。"
            return result

        has_fail = False
        for command in commands:
            run = self._execute_command(command)
            result["runs"].append(run)
            if run["status"] != "pass":
                has_fail = True

        result["status"] = "fail" if has_fail else "pass"
        result["message"] = "检查未通过" if has_fail else "检查通过"
        return result

    def _relative_label(self, repo_path: Path, path: Path) -> str:
        try:
            relative = path.relative_to(repo_path)
        except ValueError:
            return str(path)
        return relative.as_posix() if relative.parts else "."

    def _execute_command(self, command: DetectedCiCommand) -> dict:
        raw = self.runner.run(command.command, cwd=command.cwd)
        return {
            "command": command.label,
            "cwd": str(command.cwd),
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
