from __future__ import annotations

import datetime as dt
from pathlib import Path


class AiPatchPathPolicy:
    def __init__(self, allowlist: str) -> None:
        self.allowed_prefixes = [item.strip().replace("\\", "/").strip("/") for item in allowlist.split(",") if item.strip()]

    def validate(self, relative_path: str) -> tuple[bool, str]:
        text = relative_path.replace("\\", "/").strip()
        if not text:
            return False, "路径为空"
        if text.startswith("/") or ":" in text:
            return False, "不允许绝对路径"
        parts = [part for part in text.split("/") if part]
        if any(part == ".." for part in parts):
            return False, "不允许路径回退"
        if any(part in {".git", "node_modules", "dist", "build", "coverage"} for part in parts):
            return False, "不允许写入忽略目录"
        if self._is_allowed(text):
            return True, ""
        return False, "不在 AI 补丁白名单内"

    def _is_allowed(self, relative_path: str) -> bool:
        if not self.allowed_prefixes:
            return False
        for prefix in self.allowed_prefixes:
            if prefix == ".":
                return True
            if relative_path == prefix or relative_path.startswith(prefix.rstrip("/") + "/"):
                return True
        return False


class AiPatchApplier:
    def __init__(self, allowlist: str) -> None:
        self.policy = AiPatchPathPolicy(allowlist)

    def apply(self, run_id: str, draft: dict, frontend_root: Path, backend_root: Path, confirmed: bool) -> dict:
        result = {
            "run_id": run_id,
            "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "mode": "ai-patch-apply",
            "status": "planned",
            "confirmed": confirmed,
            "changed_files": [],
            "skipped_files": [],
            "message": "",
            "notes": [
                "只有显式确认后才会写入 AI 补丁草案。",
                "写入前会校验相对路径、忽略目录和白名单前缀。",
            ],
        }

        if not confirmed:
            result["message"] = "未传入 --apply-ai-patch，补丁草案未落盘。"
            return result

        patches = draft.get("patches", [])
        if not patches:
            result["status"] = "skipped"
            result["message"] = "没有可落地的 AI 补丁草案。"
            return result

        for patch in patches:
            for file_patch in patch.get("files", []):
                self._apply_file_patch(result, file_patch, frontend_root, backend_root)

        if result["changed_files"]:
            result["status"] = "changed"
            result["message"] = "AI 补丁已按白名单写入本地工作分支。"
        elif result["skipped_files"]:
            result["status"] = "skipped"
            result["message"] = "AI 补丁未产生写入，详情见 skipped_files。"
        else:
            result["status"] = "unchanged"
            result["message"] = "AI 补丁内容与现有文件一致。"
        return result

    def _apply_file_patch(self, result: dict, file_patch: dict, frontend_root: Path, backend_root: Path) -> None:
        role = str(file_patch.get("role", "")).strip()
        relative_path = str(file_patch.get("path", "")).replace("\\", "/").strip()
        content = str(file_patch.get("content", ""))

        repo_root = self._repo_root(role, frontend_root, backend_root)
        if not repo_root:
            result["skipped_files"].append({"role": role, "path": relative_path, "reason": "未知仓库角色"})
            return
        if not repo_root.exists():
            result["skipped_files"].append({"role": role, "path": relative_path, "reason": "仓库目录不存在"})
            return

        ok, reason = self.policy.validate(relative_path)
        if not ok:
            result["skipped_files"].append({"role": role, "path": relative_path, "reason": reason})
            return
        if content == "":
            result["skipped_files"].append({"role": role, "path": relative_path, "reason": "补丁内容为空"})
            return

        target = repo_root / relative_path
        try:
            target.relative_to(repo_root)
        except ValueError:
            result["skipped_files"].append({"role": role, "path": relative_path, "reason": "目标路径越界"})
            return

        old_content = target.read_text(encoding="utf-8") if target.exists() else None
        if old_content == content:
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        result["changed_files"].append({"role": role, "path": relative_path, "reason": file_patch.get("reason", "")})

    def _repo_root(self, role: str, frontend_root: Path, backend_root: Path) -> Path | None:
        if role == "frontend":
            return frontend_root
        if role == "backend":
            return backend_root
        return None
