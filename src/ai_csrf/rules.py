from __future__ import annotations

from dataclasses import dataclass


IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "target",
    ".next",
    ".nuxt",
}

TEXT_SUFFIXES = {
    ".cs",
    ".go",
    ".gradle",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".scala",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class CsrfRule:
    role: str
    rule_id: str
    title: str
    patterns: list[str]
    suggestion: str
    risk_if_missing: str = ""
    risk_if_present: str = ""


CSRF_RULES = [
    CsrfRule(
        role="backend",
        rule_id="backend_csrf_token",
        title="后端 CSRF token 校验",
        risk_if_missing="high",
        patterns=[r"\bcsrf\b", r"X-CSRF-Token", r"X-XSRF-TOKEN", r"\bcsurf\b", r"csrfToken"],
        suggestion="后端需要确认是否对状态变更请求校验 CSRF token。",
    ),
    CsrfRule(
        role="backend",
        rule_id="backend_origin_referer",
        title="后端 Origin/Referer 校验",
        risk_if_missing="medium",
        patterns=[r"\bOrigin\b", r"\bReferer\b", r"same-origin", r"allowedOrigins"],
        suggestion="建议对敏感写操作补充 Origin/Referer 校验，作为 token 之外的防护。",
    ),
    CsrfRule(
        role="backend",
        rule_id="backend_cookie_policy",
        title="后端 Cookie 安全属性",
        risk_if_missing="medium",
        patterns=[r"SameSite", r"sameSite", r"HttpOnly", r"httpOnly", r"\bSecure\b", r"setSecure"],
        suggestion="建议检查会话 Cookie 是否设置 SameSite、HttpOnly、Secure 等属性。",
    ),
    CsrfRule(
        role="backend",
        rule_id="backend_csrf_disabled",
        title="疑似关闭 CSRF 防护",
        risk_if_present="high",
        patterns=[r"csrf\(\)\.disable", r"csrf\.disable", r"csrf\s*:\s*false", r"disableCsrf"],
        suggestion="如果确实关闭了 CSRF，需要确认是否有等价防护或白名单边界。",
    ),
    CsrfRule(
        role="frontend",
        rule_id="frontend_csrf_header",
        title="前端 CSRF header 注入",
        risk_if_missing="high",
        patterns=[r"X-CSRF-Token", r"X-XSRF-TOKEN", r"xsrfHeaderName", r"csrf-token", r"csrfToken"],
        suggestion="前端请求封装层需要确认是否统一带上 CSRF token header。",
    ),
    CsrfRule(
        role="frontend",
        rule_id="frontend_token_source",
        title="前端 token 来源",
        risk_if_missing="medium",
        patterns=[r"xsrfCookieName", r"document\.cookie", r"getCookie", r"meta.*csrf", r"csrf-token"],
        suggestion="需要明确前端从 Cookie、meta 标签或接口中读取 token 的方式。",
    ),
    CsrfRule(
        role="frontend",
        rule_id="frontend_credentials",
        title="前端携带凭据配置",
        risk_if_missing="low",
        patterns=[r"withCredentials", r"credentials\s*:\s*['\"]include['\"]", r"credentials\s*:\s*['\"]same-origin['\"]"],
        suggestion="如果系统依赖 Cookie 会话，需要确认请求层是否按预期携带凭据。",
    ),
]
