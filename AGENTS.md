# 项目开发规则

## 质量检查

- 按 [开发与质量检查](docs/06-development.md) 使用项目本地工具。Python 虚拟环境、开发依赖和锁文件由 `uv` 管理。
- 修改 Python 后使用 Ruff 格式化和 lint；修改 Markdown、JSON 或 JSONC 后使用 Prettier，Markdown 另需通过 markdownlint-cli2。
- 提交前依次运行 `npm run format` 和 `npm run check`，检查自动修改并重新暂存。
- `npm run check` 只做质量检查，不能替代业务测试或真实模型效果验证。
- 不提交 `.venv/`、`node_modules/`、缓存、`.agent-tmp/`、真实密钥或隐私资料。
- `docs/11-three-hour-checkpoint.md` 与 `examples/checkpoints/three-hour/` 是用户要求冻结的 3 小时阶段记录。后续进度不得覆盖、改写或自动格式化这些已登记内容；事实勘误另建文件引用原记录。

## 提交

提交信息使用英文，标题格式为 `<type>(<scope>): <short summary>`，正文项目符号使用 `-` 后跟一个空格。提交前核对暂存文件和差异，确保包含本次范围内的所有变更，不含临时文件或敏感信息。
