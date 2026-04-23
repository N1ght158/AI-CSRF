# 执行计划 encoding-fix-dry

## 输入参数
- 前端仓库: `https://github.com/N1ght158/AI-CSRF--1`
- 后端仓库: `https://github.com/N1ght158/AI-CSRF--2`
- 平台: `github`
- 目标分支: `main`
- 自动合并: `off`
- 执行模式: `dry-run`

## 仓库准备
- 前端本地目录: `C:\Users\Ye yj\Desktop\AI-CSRF\repos\AI-CSRF--1`
- 后端本地目录: `C:\Users\Ye yj\Desktop\AI-CSRF\repos\AI-CSRF--2`
- 前端工作分支: `ai/csrf-fix-frontend-encoding-fix-dry`
- 后端工作分支: `ai/csrf-fix-backend-encoding-fix-dry`

## 检查结果
- git 命令: `pass` - git version 2.46.0.windows.1
- 令牌检查: `warn` - 未检测到令牌变量；若仓库是私有库，后续访问可能失败
- 前端远端访问: `skipped` - 未执行远端访问检查（dry-run）
- 后端远端访问: `skipped` - 未执行远端访问检查（dry-run）

## 计划步骤
1. 校验参数与本地运行环境
2. 检查令牌变量与远端访问能力
3. 准备前后端仓库（clone/fetch）
4. 创建工作分支并切换到目标基线
5. 输出后续修复流程的执行计划

## 备注
- 当前仅生成执行计划，不会拉取远端仓库
- 如需执行仓库准备，请追加 --execute-bootstrap

生成时间(UTC): `2026-04-23T10:37:43Z`