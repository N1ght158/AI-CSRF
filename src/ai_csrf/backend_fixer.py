from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExpressFixTarget:
    app_file: Path
    middleware_file: Path
    test_file: Path


class ExpressProjectDetector:
    CANDIDATE_FILES = [
        "app.js",
        "server.js",
        "index.js",
        "src/app.js",
        "src/server.js",
        "src/index.js",
    ]

    def detect(self, backend_root: Path) -> ExpressFixTarget | None:
        package_json = backend_root / "package.json"
        if not package_json.exists() or not self._uses_express(package_json):
            return None

        for relative_path in self.CANDIDATE_FILES:
            app_file = backend_root / relative_path
            if self._is_commonjs_express_app(app_file):
                return ExpressFixTarget(
                    app_file=app_file,
                    middleware_file=app_file.parent / "csrf-autopilot.middleware.js",
                    test_file=app_file.parent / "csrf-autopilot.middleware.test.js",
                )
        return None

    def _uses_express(self, package_json: Path) -> bool:
        try:
            data = json.loads(package_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return False

        dependencies = data.get("dependencies", {})
        dev_dependencies = data.get("devDependencies", {})
        return "express" in dependencies or "express" in dev_dependencies

    def _is_commonjs_express_app(self, app_file: Path) -> bool:
        if not app_file.exists():
            return False

        try:
            text = app_file.read_text(encoding="utf-8-sig")
        except OSError:
            return False

        return "require(" in text and "express" in text and re.search(r"\bapp\s*=\s*express\s*\(", text) is not None


class ExpressCsrfPatch:
    REQUIRE_LINE = 'const { csrfAutopilotProtection } = require("./csrf-autopilot.middleware");'
    USE_LINE = "app.use(csrfAutopilotProtection);"

    def apply(self, target: ExpressFixTarget) -> list[Path]:
        changed_files: list[Path] = []
        if self._write_if_changed(target.middleware_file, self._middleware_content()):
            changed_files.append(target.middleware_file)
        if self._write_if_changed(target.test_file, self._test_content()):
            changed_files.append(target.test_file)
        if self._patch_app_file(target.app_file):
            changed_files.append(target.app_file)
        return changed_files

    def already_applied(self, target: ExpressFixTarget) -> bool:
        if not target.app_file.exists() or not target.middleware_file.exists() or not target.test_file.exists():
            return False
        try:
            app_text = target.app_file.read_text(encoding="utf-8")
        except OSError:
            return False
        return "csrfAutopilotProtection" in app_text

    def _patch_app_file(self, app_file: Path) -> bool:
        original = app_file.read_text(encoding="utf-8")
        patched = self._ensure_require(original)
        patched = self._ensure_middleware_use(patched)
        if patched == original:
            return False
        app_file.write_text(patched, encoding="utf-8", newline="\n")
        return True

    def _ensure_require(self, text: str) -> str:
        if "csrfAutopilotProtection" in text:
            return text

        lines = text.splitlines()
        insert_at = 0
        for index, line in enumerate(lines):
            if "require(" in line:
                insert_at = index + 1
        lines.insert(insert_at, self.REQUIRE_LINE)
        return "\n".join(lines) + "\n"

    def _ensure_middleware_use(self, text: str) -> str:
        if self.USE_LINE in text:
            return text

        lines = text.splitlines()
        insert_at = self._find_middleware_insert_index(lines)
        lines.insert(insert_at, self.USE_LINE)
        return "\n".join(lines) + "\n"

    def _find_middleware_insert_index(self, lines: list[str]) -> int:
        app_init_index = 0
        parser_index = -1
        for index, line in enumerate(lines):
            if re.search(r"\bapp\s*=\s*express\s*\(", line):
                app_init_index = index
            if "app.use(express.json" in line or "app.use(express.urlencoded" in line:
                parser_index = index
        return (parser_index if parser_index >= 0 else app_init_index) + 1

    def _write_if_changed(self, path: Path, content: str) -> bool:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return False
        path.write_text(content, encoding="utf-8", newline="\n")
        return True

    def _middleware_content(self) -> str:
        return """const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function parseCookie(cookieHeader) {
  return cookieHeader
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean)
    .reduce((cookies, item) => {
      const separator = item.indexOf("=");
      if (separator === -1) {
        return cookies;
      }
      const name = decodeURIComponent(item.slice(0, separator));
      const value = decodeURIComponent(item.slice(separator + 1));
      cookies[name] = value;
      return cookies;
    }, {});
}

function readHeader(req, name) {
  if (typeof req.get === "function") {
    return req.get(name);
  }
  return req.headers?.[name.toLowerCase()];
}

function csrfAutopilotProtection(req, res, next) {
  if (SAFE_METHODS.has(req.method)) {
    return next();
  }

  const cookies = parseCookie(req.headers?.cookie || "");
  const headerToken = readHeader(req, "x-csrf-token") || readHeader(req, "x-xsrf-token");
  const cookieToken = cookies["XSRF-TOKEN"] || cookies["CSRF-TOKEN"] || cookies["csrfToken"];

  if (headerToken && cookieToken && headerToken === cookieToken) {
    return next();
  }

  return res.status(403).json({ error: "CSRF token invalid or missing" });
}

module.exports = {
  csrfAutopilotProtection,
  parseCookie,
};
"""

    def _test_content(self) -> str:
        return """const assert = require("assert");
const { csrfAutopilotProtection, parseCookie } = require("./csrf-autopilot.middleware");

function createResponse() {
  return {
    statusCode: 200,
    body: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(payload) {
      this.body = payload;
      return this;
    },
  };
}

assert.deepStrictEqual(parseCookie("XSRF-TOKEN=abc; theme=light"), {
  "XSRF-TOKEN": "abc",
  theme: "light",
});

let nextCalled = false;
csrfAutopilotProtection({ method: "GET", headers: {} }, createResponse(), () => {
  nextCalled = true;
});
assert.strictEqual(nextCalled, true);

nextCalled = false;
csrfAutopilotProtection(
  {
    method: "POST",
    headers: { cookie: "XSRF-TOKEN=abc", "x-csrf-token": "abc" },
  },
  createResponse(),
  () => {
    nextCalled = true;
  }
);
assert.strictEqual(nextCalled, true);

const blocked = createResponse();
csrfAutopilotProtection(
  { method: "POST", headers: { cookie: "XSRF-TOKEN=abc", "x-csrf-token": "wrong" } },
  blocked,
  () => {}
);
assert.strictEqual(blocked.statusCode, 403);

console.log("csrf autopilot middleware tests passed");
"""


class BackendFixer:
    def __init__(
        self,
        detector: ExpressProjectDetector | None = None,
        patch: ExpressCsrfPatch | None = None,
    ) -> None:
        self.detector = detector or ExpressProjectDetector()
        self.patch = patch or ExpressCsrfPatch()

    def apply(self, run_id: str, backend_root: Path) -> dict:
        started_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        result = {
            "run_id": run_id,
            "created_at_utc": started_at,
            "mode": "backend-fix-mvp",
            "backend_path": str(backend_root),
            "status": "skipped",
            "supported_stack": "",
            "changed_files": [],
            "test_command": "",
            "message": "",
            "notes": [
                "当前 MVP 仅支持 Express CommonJS 项目的最小 CSRF 修复。",
                "修复逻辑采用双提交 token 思路，要求写操作请求同时携带 token cookie 和 token header。",
            ],
        }

        if not backend_root.exists():
            result["message"] = "后端仓库目录不存在，请先执行仓库准备。"
            return result

        target = self.detector.detect(backend_root)
        if not target:
            result["status"] = "unsupported"
            result["message"] = "未识别到支持的 Express CommonJS 入口，当前 MVP 未生成改动。"
            return result

        result["supported_stack"] = "Express CommonJS"
        if self.patch.already_applied(target):
            result["status"] = "unchanged"
            result["message"] = "后端 CSRF 修复 MVP 已存在，未重复写入。"
            result["test_command"] = self._test_command(backend_root, target.test_file)
            return result

        changed_files = self.patch.apply(target)
        result["status"] = "changed" if changed_files else "unchanged"
        result["changed_files"] = [path.relative_to(backend_root).as_posix() for path in changed_files]
        result["test_command"] = self._test_command(backend_root, target.test_file)
        result["message"] = "已生成后端 CSRF 修复 MVP 改动和最小测试。"
        return result

    def _test_command(self, backend_root: Path, test_file: Path) -> str:
        return f"node {test_file.relative_to(backend_root).as_posix()}"
