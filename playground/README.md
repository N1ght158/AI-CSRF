# 简单靶场

这个目录提供两个最小靶场，用于测试 AI-CSRF 的扫描、AI 决策、补丁草案、补丁落地和自动 PR 流程。

- `simple-web-target/`：前端靶场，模拟使用 Cookie 登录态发起修改邮箱请求。
- `simple-api-target/`：后端靶场，模拟 Cookie Session 登录态和一个缺少 CSRF 防护的写接口。

## 使用方式

建议把两个目录分别上传成两个 GitHub 仓库：

- `simple-web-target` 上传为前端靶场仓库。
- `simple-api-target` 上传为后端靶场仓库。

然后在 AI-CSRF 项目根目录运行：

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

## 本地测试说明

两个靶场都提供了最小 `npm test` 脚本。

```powershell
cd .\repos\simple-web-target
npm.cmd run test

cd ..\simple-api-target
npm.cmd run test
```

当前验证结果：

- 后端测试通过。
- 前端测试失败，原因是测试脚本只在 `App.jsx` 里查找 `X-CSRF-Token`，但当前 AI 补丁把 header 逻辑封装到了 `src/apiClient.js`。这属于测试断言口径问题，后续需要把前端测试改成同时检查封装层。

## 说明

靶场代码故意保留安全缺口，方便观察插件修复前后的变化。它适合演示 A版能力，但不代表真实业务系统的完整安全测试集。
