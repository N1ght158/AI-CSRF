from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrontendFixTarget:
    request_file: Path
    helper_file: Path
    test_file: Path
    module_style: str
    axios_name: str


class AxiosProjectDetector:
    CANDIDATE_FILES = [
        "src/api.js",
        "src/request.js",
        "src/http.js",
        "src/services/api.js",
        "src/services/request.js",
        "src/lib/api.js",
        "src/lib/request.js",
        "src/utils/api.js",
        "src/utils/request.js",
        "api.js",
        "request.js",
        "http.js",
    ]

    def detect(self, frontend_root: Path) -> FrontendFixTarget | None:
        package_json = frontend_root / "package.json"
        if not package_json.exists() or not self._uses_axios(package_json):
            return None

        for relative_path in self._candidate_paths():
            request_file = frontend_root / relative_path
            style = self._detect_module_style(request_file)
            if not style:
                continue

            axios_name = self._detect_axios_instance(request_file) or "axios"
            helper_name = "csrf-autopilot.client.mjs" if style == "esm" else "csrf-autopilot.client.js"
            test_name = "csrf-autopilot.client.test.mjs" if style == "esm" else "csrf-autopilot.client.test.js"
            return FrontendFixTarget(
                request_file=request_file,
                helper_file=request_file.parent / helper_name,
                test_file=request_file.parent / test_name,
                module_style=style,
                axios_name=axios_name,
            )
        return None

    def _candidate_paths(self) -> list[str]:
        paths: list[str] = []
        for item in self.CANDIDATE_FILES:
            paths.append(item)
            if item.endswith(".js"):
                paths.append(item[:-3] + ".ts")
                paths.append(item[:-3] + ".jsx")
                paths.append(item[:-3] + ".tsx")
        return paths

    def _uses_axios(self, package_json: Path) -> bool:
        try:
            data = json.loads(package_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return False

        dependencies = data.get("dependencies", {})
        dev_dependencies = data.get("devDependencies", {})
        return "axios" in dependencies or "axios" in dev_dependencies

    def _detect_module_style(self, request_file: Path) -> str:
        if not request_file.exists():
            return ""

        try:
            text = request_file.read_text(encoding="utf-8-sig")
        except OSError:
            return ""

        if re.search(r"import\s+axios\s+from\s+['\"]axios['\"]", text):
            return "esm"
        if re.search(r"(?:const|let|var)\s+axios\s*=\s*require\(['\"]axios['\"]\)", text):
            return "commonjs"
        return ""

    def _detect_axios_instance(self, request_file: Path) -> str:
        try:
            text = request_file.read_text(encoding="utf-8-sig")
        except OSError:
            return ""

        match = re.search(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*axios\.create\s*\(", text)
        if match:
            return match.group(1)
        return "axios"


class AxiosCsrfPatch:
    def apply(self, target: FrontendFixTarget) -> list[Path]:
        changed_files: list[Path] = []
        helper_content = self._helper_content(target.module_style)
        test_content = self._test_content(target.module_style, target.helper_file.name)

        if self._write_if_changed(target.helper_file, helper_content):
            changed_files.append(target.helper_file)
        if self._write_if_changed(target.test_file, test_content):
            changed_files.append(target.test_file)
        if self._patch_request_file(target):
            changed_files.append(target.request_file)
        return changed_files

    def already_applied(self, target: FrontendFixTarget) -> bool:
        if not target.request_file.exists() or not target.helper_file.exists() or not target.test_file.exists():
            return False
        try:
            text = target.request_file.read_text(encoding="utf-8")
        except OSError:
            return False
        return "attachCsrfToken" in text

    def _patch_request_file(self, target: FrontendFixTarget) -> bool:
        original = target.request_file.read_text(encoding="utf-8-sig")
        if "attachCsrfToken" in original:
            return False

        lines = original.splitlines()
        if target.module_style == "esm":
            import_line = f'import {{ attachCsrfToken }} from "./{target.helper_file.name}";'
            lines = self._insert_after_imports(lines, import_line)
        else:
            require_line = f'const {{ attachCsrfToken }} = require("./{target.helper_file.name}");'
            lines = self._insert_after_requires(lines, require_line)

        attach_line = f"attachCsrfToken({target.axios_name});"
        lines = self._insert_attach_line(lines, target.axios_name, attach_line)
        patched = "\n".join(lines) + "\n"
        target.request_file.write_text(patched, encoding="utf-8", newline="\n")
        return patched != original

    def _insert_after_imports(self, lines: list[str], import_line: str) -> list[str]:
        insert_at = 0
        for index, line in enumerate(lines):
            if line.strip().startswith("import "):
                insert_at = index + 1
        lines.insert(insert_at, import_line)
        return lines

    def _insert_after_requires(self, lines: list[str], require_line: str) -> list[str]:
        insert_at = 0
        for index, line in enumerate(lines):
            if "require(" in line:
                insert_at = index + 1
        lines.insert(insert_at, require_line)
        return lines

    def _insert_attach_line(self, lines: list[str], axios_name: str, attach_line: str) -> list[str]:
        create_pattern = re.compile(rf"\b{re.escape(axios_name)}\s*=\s*axios\.create\s*\(")
        for index, line in enumerate(lines):
            if create_pattern.search(line):
                lines.insert(index + 1, attach_line)
                return lines

        for index, line in enumerate(lines):
            if "axios" in line and ("import" in line or "require(" in line):
                lines.insert(index + 1, attach_line)
                return lines

        lines.insert(0, attach_line)
        return lines

    def _write_if_changed(self, path: Path, content: str) -> bool:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return False
        path.write_text(content, encoding="utf-8", newline="\n")
        return True

    def _helper_content(self, module_style: str) -> str:
        body = """const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const DEFAULT_COOKIE_NAMES = ["XSRF-TOKEN", "CSRF-TOKEN", "csrfToken"];
const DEFAULT_HEADER_NAME = "X-CSRF-Token";

function readCookie(name, cookieSource) {
  return cookieSource
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean)
    .reduce((value, item) => {
      if (value !== "") {
        return value;
      }
      const separator = item.indexOf("=");
      if (separator === -1) {
        return "";
      }
      const cookieName = decodeURIComponent(item.slice(0, separator));
      if (cookieName !== name) {
        return "";
      }
      return decodeURIComponent(item.slice(separator + 1));
    }, "");
}

function readCsrfToken(cookieSource, cookieNames = DEFAULT_COOKIE_NAMES) {
  const source = cookieSource || (typeof document !== "undefined" ? document.cookie : "");
  for (const name of cookieNames) {
    const value = readCookie(name, source);
    if (value) {
      return value;
    }
  }
  return "";
}

function setHeader(headers, name, value) {
  if (typeof headers.set === "function") {
    headers.set(name, value);
    return headers;
  }
  headers[name] = value;
  return headers;
}

function attachCsrfToken(axiosInstance, options = {}) {
  if (!axiosInstance || !axiosInstance.interceptors || !axiosInstance.interceptors.request) {
    return axiosInstance;
  }
  if (axiosInstance.__csrfAutopilotAttached) {
    return axiosInstance;
  }

  axiosInstance.interceptors.request.use((config) => {
    const method = String(config.method || "GET").toUpperCase();
    if (SAFE_METHODS.has(method)) {
      return config;
    }

    const token = readCsrfToken(options.cookieSource, options.cookieNames);
    if (!token) {
      return config;
    }

    config.headers = setHeader(config.headers || {}, options.headerName || DEFAULT_HEADER_NAME, token);
    return config;
  });
  axiosInstance.__csrfAutopilotAttached = true;
  return axiosInstance;
}
"""
        if module_style == "esm":
            return body + """
export {
  attachCsrfToken,
  readCookie,
  readCsrfToken,
  setHeader,
};
"""
        return body + """
module.exports = {
  attachCsrfToken,
  readCookie,
  readCsrfToken,
  setHeader,
};
"""

    def _test_content(self, module_style: str, helper_name: str) -> str:
        if module_style == "esm":
            return f"""import assert from "assert";
import {{ attachCsrfToken, readCookie, readCsrfToken }} from "./{helper_name}";

assert.strictEqual(readCookie("XSRF-TOKEN", "XSRF-TOKEN=abc; theme=light"), "abc");
assert.strictEqual(readCsrfToken("CSRF-TOKEN=def"), "def");

const handlers = [];
const axiosInstance = {{
  interceptors: {{
    request: {{
      use(handler) {{
        handlers.push(handler);
      }},
    }},
  }},
}};

attachCsrfToken(axiosInstance, {{ cookieSource: "XSRF-TOKEN=abc" }});
const nextConfig = handlers[0]({{ method: "POST", headers: {{}} }});
assert.strictEqual(nextConfig.headers["X-CSRF-Token"], "abc");

console.log("csrf autopilot frontend tests passed");
"""
        return f"""const assert = require("assert");
const {{ attachCsrfToken, readCookie, readCsrfToken }} = require("./{helper_name}");

assert.strictEqual(readCookie("XSRF-TOKEN", "XSRF-TOKEN=abc; theme=light"), "abc");
assert.strictEqual(readCsrfToken("CSRF-TOKEN=def"), "def");

const handlers = [];
const axiosInstance = {{
  interceptors: {{
    request: {{
      use(handler) {{
        handlers.push(handler);
      }},
    }},
  }},
}};

attachCsrfToken(axiosInstance, {{ cookieSource: "XSRF-TOKEN=abc" }});
const nextConfig = handlers[0]({{ method: "POST", headers: {{}} }});
assert.strictEqual(nextConfig.headers["X-CSRF-Token"], "abc");

console.log("csrf autopilot frontend tests passed");
"""


class FrontendFixer:
    def __init__(
        self,
        detector: AxiosProjectDetector | None = None,
        patch: AxiosCsrfPatch | None = None,
    ) -> None:
        self.detector = detector or AxiosProjectDetector()
        self.patch = patch or AxiosCsrfPatch()

    def apply(self, run_id: str, frontend_root: Path) -> dict:
        started_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        result = {
            "run_id": run_id,
            "created_at_utc": started_at,
            "mode": "frontend-fix-mvp",
            "frontend_path": str(frontend_root),
            "status": "skipped",
            "supported_stack": "",
            "changed_files": [],
            "test_command": "",
            "message": "",
            "notes": [
                "当前 MVP 仅支持 Axios 请求封装的前端项目。",
                "修复逻辑会在非安全方法请求中自动注入 CSRF token header。",
            ],
        }

        if not frontend_root.exists():
            result["message"] = "前端仓库目录不存在，请先执行仓库准备。"
            return result

        target = self.detector.detect(frontend_root)
        if not target:
            result["status"] = "unsupported"
            result["message"] = "未识别到支持的 Axios 请求封装入口，当前 MVP 未生成改动。"
            return result

        result["supported_stack"] = f"Axios {target.module_style}"
        if self.patch.already_applied(target):
            result["status"] = "unchanged"
            result["message"] = "前端 CSRF 修复 MVP 已存在，未重复写入。"
            result["test_command"] = self._test_command(frontend_root, target.test_file)
            return result

        changed_files = self.patch.apply(target)
        result["status"] = "changed" if changed_files else "unchanged"
        result["changed_files"] = [path.relative_to(frontend_root).as_posix() for path in changed_files]
        result["test_command"] = self._test_command(frontend_root, target.test_file)
        result["message"] = "已生成前端 CSRF 修复 MVP 改动和最小测试。"
        return result

    def _test_command(self, frontend_root: Path, test_file: Path) -> str:
        return f"node {test_file.relative_to(frontend_root).as_posix()}"
