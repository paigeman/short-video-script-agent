# AI 使用记录

## 初始化阶段

Codex 根据已阅读的公开示例仓库及选定项目方向，辅助建立目录、CLI 骨架、合成输入、素材和五类文档。当前没有生成真实模型业务输出或验收通过结论。

公开参考：[agent-campus-submission-example](https://github.com/lwz1357/agent-campus-submission-example)。参考其目录分类和交付组织，本项目初始化文件独立编写。

## 开发质量工具

Codex 参考 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo) 配置了 Prettier、markdownlint-cli2、Ruff、统一 npm 命令及 JSON 校验脚本。Python 虚拟环境和 Ruff 依赖由 `uv` 管理；开发依赖版本记录在 `package-lock.json` 和 `uv.lock`。这些工具用于开发质量检查，不能证明 Agent 业务效果。

## 基础运行时迁移

按用户确定的范围，Codex 从 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo) 的固定提交迁移工具定义、协议、执行与测试，提取同步模型适配和循环，并补充 Trace、离线演示及集成验证。具体文件、裁剪范围和新写部分见 [迁移说明](07-migration.md)。

当前 46 项测试通过，证据见 [实际测试记录](../examples/runtime-test-results.txt)。未读取原项目的个人密钥，也未执行真实模型业务评估。复用代码与 AI 辅助内容应在后续个人贡献说明中如实区分。

## 后续记录方式

每次重要实现或修改，记录以下实际发生的内容：

- AI 参与的范围及所用工具。
- 本人检查后发现的具体问题。
- 本人作出的设计选择或修改。
- 验证命令、实际结果和对应证据文件。

当前尚未填写个人实现、修改或验证贡献。后续须根据真实工作补充，不能将 AI 产出直接记为个人独立完成，也不能把计划验证记为实际结果。无需提交全部聊天记录。
