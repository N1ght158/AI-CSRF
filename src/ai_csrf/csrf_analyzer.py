from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .git_client import TextDecoder
from .rules import CSRF_RULES, IGNORE_DIRS, TEXT_SUFFIXES, CsrfRule


class SourceScanner:
    def __init__(self, decoder: TextDecoder | None = None) -> None:
        self.decoder = decoder or TextDecoder()

    def list_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []

        files: list[Path] = []
        for path in root.rglob("*"):
            if path.is_dir() or not self.should_scan(path):
                continue
            try:
                if path.stat().st_size > 512_000:
                    continue
            except OSError:
                continue
            files.append(path)
        return files

    def should_scan(self, path: Path) -> bool:
        if path.suffix not in TEXT_SUFFIXES:
            return False
        return not any(part in IGNORE_DIRS for part in path.parts)

    def read_text(self, path: Path) -> str:
        try:
            return self.decoder.decode(path.read_bytes())
        except OSError:
            return ""


class StackDetector:
    def __init__(self, scanner: SourceScanner) -> None:
        self.scanner = scanner

    def detect(self, root: Path, files: list[Path]) -> list[str]:
        names = {file.relative_to(root).as_posix().lower() for file in files}
        stacks: set[str] = set()

        if "package.json" in names:
            stacks.add("Node.js / 前端生态")
            package_text = self.scanner.read_text(root / "package.json").lower()
            for key, label in {
                "react": "React",
                "vue": "Vue",
                "express": "Express",
                "next": "Next.js",
                "axios": "Axios",
            }.items():
                if key in package_text:
                    stacks.add(label)

        if "pom.xml" in names or "build.gradle" in names or "build.gradle.kts" in names:
            stacks.add("Java / Spring 生态")
        if "requirements.txt" in names or "pyproject.toml" in names or "manage.py" in names:
            stacks.add("Python Web 生态")
        if "manage.py" in names:
            stacks.add("Django")

        return sorted(stacks) or ["未识别"]


class RuleMatcher:
    def __init__(self, scanner: SourceScanner) -> None:
        self.scanner = scanner

    def collect_hits(self, root: Path, files: list[Path], rule: CsrfRule) -> list[dict]:
        hits: list[dict] = []
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in rule.patterns]

        for file in files:
            text = self.scanner.read_text(file)
            if not text:
                continue

            for line_no, line in enumerate(text.splitlines(), start=1):
                if self._matches_any(compiled, line):
                    hits.append(
                        {
                            "file": file.relative_to(root).as_posix(),
                            "line": line_no,
                            "sample": line.strip()[:180],
                        }
                    )
                if len(hits) >= 20:
                    return hits

        return hits

    def _matches_any(self, patterns: list[re.Pattern], line: str) -> bool:
        return any(pattern.search(line) for pattern in patterns)


class CsrfAnalyzer:
    def __init__(self, scanner: SourceScanner | None = None) -> None:
        self.scanner = scanner or SourceScanner()
        self.stack_detector = StackDetector(self.scanner)
        self.matcher = RuleMatcher(self.scanner)

    def analyze(self, run_id: str, frontend_local: Path, backend_local: Path) -> dict:
        repositories = [
            self.analyze_repository("frontend", frontend_local),
            self.analyze_repository("backend", backend_local),
        ]
        return {
            "run_id": run_id,
            "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mode": "static-rules",
            "summary": self.summarize_risk(repositories),
            "repositories": repositories,
            "notes": [
                "当前阶段只做静态规则扫描，不修改仓库代码。",
                "扫描结果用于定位证据和缺口，后续可交给 AI 辅助判断和修复。",
            ],
        }

    def analyze_repository(self, role: str, root: Path) -> dict:
        result = {
            "role": role,
            "path": str(root),
            "exists": root.exists(),
            "detected_stacks": [],
            "scanned_files": 0,
            "checks": [],
            "risk_items": [],
        }
        if not root.exists():
            result["risk_items"].append(
                {
                    "level": "unknown",
                    "title": "本地仓库目录不存在",
                    "detail": "请先执行 --execute-bootstrap 拉取仓库后再扫描。",
                }
            )
            return result

        files = self.scanner.list_files(root)
        result["scanned_files"] = len(files)
        result["detected_stacks"] = self.stack_detector.detect(root, files)

        for rule in CSRF_RULES:
            if rule.role != role:
                continue
            self._append_rule_result(result, root, files, rule)

        return result

    def summarize_risk(self, repositories: list[dict]) -> dict:
        levels = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for repo in repositories:
            for risk in repo["risk_items"]:
                level = risk.get("level", "unknown")
                levels[level] = levels.get(level, 0) + 1
        return levels

    def _append_rule_result(self, result: dict, root: Path, files: list[Path], rule: CsrfRule) -> None:
        hits = self.matcher.collect_hits(root, files, rule)
        result["checks"].append(
            {
                "id": rule.rule_id,
                "title": rule.title,
                "status": "found" if hits else "missing",
                "evidence": hits,
                "suggestion": rule.suggestion,
            }
        )

        if hits and rule.risk_if_present:
            result["risk_items"].append(
                {
                    "level": rule.risk_if_present,
                    "title": rule.title,
                    "detail": rule.suggestion,
                    "evidence_count": len(hits),
                }
            )
        elif not hits and rule.risk_if_missing:
            result["risk_items"].append(
                {
                    "level": rule.risk_if_missing,
                    "title": rule.title,
                    "detail": rule.suggestion,
                    "evidence_count": 0,
                }
            )
