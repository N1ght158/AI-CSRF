# AI-CSRF

注：本人练手项目。

AI-CSRF 是一个命令行形式的 AI CSRF 自动修复插件/自动化工具。它接收前端仓库和后端仓库地址后，可以自动准备仓库、扫描 CSRF 风险、调用 Codex 生成修复决策和补丁草案，在人工确认后把补丁写入本地工作分支，并支持自动提交、推送和创建 GitHub PR。

## 项目目标

1. 接收前后端仓库地址。
2. 分析 CSRF 防护缺口。
3. 生成修复改动与测试。
4. 自动提交 PR，并在满足策略时合并。

## 当前进展

- 目标 1：已完成。支持前后端仓库地址输入、地址校验、run-id 生成、远端访问检查、`clone/fetch` 和工作分支创建。
- 目标 2：已完成 A版能力。支持静态规则扫描和 Codex 修复决策，能识别前端 CSRF header、token 来源、后端 token 校验、Cookie 安全属性等风险。
- 目标 3：已完成 A版 MVP。支持 Codex 生成补丁草案，支持草案复用，支持人工确认后按白名单写入本地工作分支。
- 目标 4：已完成 A版 PR 流程。当前可以 `git add/commit/push`，并通过 GitHub CLI 自动创建双仓 PR；自动合并仍建议保留人工审批。

## 已验证结果

当前已在简单靶场上完成一轮端到端验证：

- 前端仓库：`https://github.com/N1ght158/simple-web-target`
- 后端仓库：`https://github.com/N1ght158/simple-api-target`
- 前端 PR：`https://github.com/N1ght158/simple-web-target/pull/1`
- 后端 PR：`https://github.com/N1ght158/simple-api-target/pull/1`

本轮验证说明：

- AI 成功生成前后端 CSRF 修复补丁。
- 补丁成功写入本地工作分支。
- 工具成功提交 commit、推送分支并创建 PR。
- 后端本地测试通过。
- 前端本地测试目前未通过，原因是测试脚本只检查 `App.jsx` 中是否直接出现 `X-CSRF-Token`，但本轮 AI 将 CSRF header 封装到了 `src/apiClient.js`，后续需要调整测试口径。

## 常用命令

一条命令重新调用 AI 并创建 PR：

```powershell
python .\src\csrf_autopilot.py run `
  --frontend https://github.com/N1ght158/simple-web-target `
  --backend https://github.com/N1ght158/simple-api-target `
  --provider github `
  --base main `
  --workspace . `
  --run-id simple-onepass-ai-001 `
  --execute-bootstrap `
  --analyze-csrf `
  --ai-decide-fixes `
  --ai-generate-patch `
  --apply-ai-patch `
  --create-pr
```

如需启用本地 CI 验证，可追加：

```powershell
--validate-ai-patch
```

## 使用前准备

需要本机具备：

- Python
- Git
- GitHub CLI：`gh`
- Node.js / npm（用于靶场测试）
- OpenAI API Key（通过 `OPENAI_API_KEY` 环境变量提供）

示例：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$env:OPENAI_API_KEY="你的 OpenAI API Key"
git config --global user.name "N1ght158"
git config --global user.email "你的 GitHub 邮箱"
gh auth login
```

不要把 API Key 写入代码或提交到仓库。

## 目录说明

项目文档见 `docs/` 目录，阶段记录见 `progress/` 目录，运行报告默认输出到 `reports/`，目标仓库默认拉取到 `repos/`。
