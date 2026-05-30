param(
  [Parameter(Mandatory = $true)][string]$Frontend,         # 前端仓库地址（必填）
  [Parameter(Mandatory = $true)][string]$Backend,          # 后端仓库地址（必填）
  [ValidateSet("github", "gitlab")][string]$Provider = "github",  # 平台，默认 github
  [string]$Base = "main",                                  # 基础分支，默认 main
  [ValidateSet("off", "on-green")][string]$AutoMerge = "off",     # 自动合并策略
  [string]$Workspace = ".",                                # 工作目录，默认当前目录
  [string]$RunId = "",                                     # 运行 ID，可选
  [string]$BranchPrefix = "ai/csrf-fix",                   # 工作分支前缀
  [string]$FrontendDir = "",                               # 前端本地目录名，可选
  [string]$BackendDir = "",                                # 后端本地目录名，可选
  [switch]$ExecuteBootstrap,                                # 是否执行 clone/fetch 和分支准备
  [switch]$RequireToken,                                    # 是否强制要求检测到令牌
  [switch]$AnalyzeCsrf,                                     # 是否生成 CSRF 风险识别报告
  [switch]$DecideFixes,                                     # 是否生成修复决策报告
  [switch]$ApplyBackendFix,                                 # 是否生成后端 CSRF 修复 MVP 改动
  [switch]$ApplyFrontendFix,                                # 是否生成前端 CSRF 修复 MVP 改动
  [switch]$RunCiGate,                                       # 是否执行 CI 闸门
  [switch]$CreatePr,                                        # 是否执行自动提 PR
  [switch]$ExecuteMerge,                                    # 是否执行自动合并命令
  [ValidateSet("openai")][string]$AiProvider = "openai",                      # AI 提供方
  [string]$AiModel = "gpt-5.1-codex-mini",                                   # AI 模型
  [string]$AiBaseUrl = "https://api.openai.com/v1",                          # AI 接口地址
  [string]$AiApiKeyEnv = "OPENAI_API_KEY",                                   # API Key 环境变量名
  [ValidateSet("none", "minimal", "low", "medium", "high", "xhigh")][string]$AiReasoningEffort = "low",  # AI 推理强度
  [int]$AiTimeoutSeconds = 120,                                                # AI 请求超时秒数
  [switch]$AiDecideFixes                                                       # 是否启用 AI 决策
)

# 获取项目根目录（当前脚本目录的上一级）
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

# 定位 Python 入口文件
$entry = Join-Path $projectRoot "src/csrf_autopilot.py"

# 如果入口文件不存在，则报错退出
if (-not (Test-Path $entry)) {
  Write-Error "未找到入口文件: $entry"
  exit 1
}

# 组织命令行参数
$argsList = @(
  $entry,
  "run",
  "--frontend", $Frontend,
  "--backend", $Backend,
  "--provider", $Provider,
  "--base", $Base,
  "--auto-merge", $AutoMerge,
  "--workspace", $Workspace,
  "--branch-prefix", $BranchPrefix,
  "--ai-provider", $AiProvider,
  "--ai-model", $AiModel,
  "--ai-base-url", $AiBaseUrl,
  "--ai-api-key-env", $AiApiKeyEnv,
  "--ai-reasoning-effort", $AiReasoningEffort,
  "--ai-timeout-seconds", $AiTimeoutSeconds
)

# 如果传入了 RunId，则追加对应参数
if ($RunId -ne "") {
  $argsList += @("--run-id", $RunId)
}

# 如果传入了目录名，则追加对应参数
if ($FrontendDir -ne "") {
  $argsList += @("--frontend-dir", $FrontendDir)
}
if ($BackendDir -ne "") {
  $argsList += @("--backend-dir", $BackendDir)
}

# 开关参数按需追加
if ($ExecuteBootstrap) {
  $argsList += "--execute-bootstrap"
}
if ($RequireToken) {
  $argsList += "--require-token"
}
if ($AnalyzeCsrf) {
  $argsList += "--analyze-csrf"
}
if ($DecideFixes) {
  $argsList += "--decide-fixes"
}
if ($ApplyBackendFix) {
  $argsList += "--apply-backend-fix"
}
if ($ApplyFrontendFix) {
  $argsList += "--apply-frontend-fix"
}
if ($RunCiGate) {
  $argsList += "--run-ci-gate"
}
if ($CreatePr) {
  $argsList += "--create-pr"
}
if ($ExecuteMerge) {
  $argsList += "--execute-merge"
}
if ($AiDecideFixes) {
  $argsList += "--ai-decide-fixes"
}

# 执行 Python 脚本
python @argsList

# 返回 Python 的退出状态码
exit $LASTEXITCODE
