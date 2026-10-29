# Short Video Script Agent

第 4 题「短视频脚本 Agent」的项目骨架。

**当前状态：已完成目录初始化、CLI 输入读取、文档骨架和开发质量工具配置。尚未接入模型，也未实现脚本生成、工具调用或 ReAct 决策。此版本不作为完整交付或业务验收通过的证据。**

## 环境与运行

- Python 3.10+
- CLI 运行时没有第三方依赖，无需密钥或环境变量
- 在仓库根目录运行

```bash
python3 -m src.main --input examples/normal.input.json
```

当前入口只验证文件可读取且输入为 JSON 对象，随后返回 `not_implemented` 状态与空 Trace。退出码 0 仅表示入口正常执行，不表示业务任务完成。输入文件、编码或 JSON 格式有误时，返回 `invalid_input` 和非零退出码。

`missing.input.json` 与 `tool-failure.input.json` 是后续验收输入；当前入口尚未解释缺失的业务字段或模拟失败开关。

## 开发质量检查

Python 开发环境使用 `uv` 管理；Markdown、JSON 和 JSONC 使用项目本地的 Prettier，Markdown lint 使用 markdownlint-cli2，Python 格式化和 lint 使用 Ruff。

```shell
npm ci --ignore-scripts
uv sync --locked
npm run format
npm run check
```

安装要求、规则和分项命令见 [开发与质量检查](docs/06-development.md)。

## 计划实现

模型根据用户要求选择素材检索、脚本编写、时长检查与规则检查动作，观察工具返回后决定修改、补查、请求补充或结束。每次执行设置步数上限，并记录可审查的工具调用与结果。

交付输出计划包含标题、分镜、旁白或字幕、预计时长、素材来源、风险和任务状态。时长估算的假设与误差应单独说明。

## 项目目录

```text
.
├── README.md
├── requirements.txt
├── pyproject.toml
├── uv.lock
├── package.json
├── package-lock.json
├── AGENTS.md
├── .editorconfig
├── .prettierrc.json
├── .prettierignore
├── .markdownlint-cli2.jsonc
├── .env.example
├── .gitignore
├── src/
│   ├── __init__.py
│   └── main.py
├── scripts/
│   └── check_json.py
├── tests/
│   └── README.md
├── examples/
│   ├── README.md
│   ├── normal.input.json
│   ├── missing.input.json
│   └── tool-failure.input.json
├── data/
│   ├── README.md
│   ├── materials.json
│   └── brand_rules.json
└── docs/
    ├── 01-requirements.md
    ├── 02-solution.md
    ├── 03-evaluation.md
    ├── 04-ai-usage.md
    ├── 05-retrospective.md
    └── 06-development.md
```

## 评审导航

| 内容                       | 入口                               |
| -------------------------- | ---------------------------------- |
| 用户、目标、范围和成功标准 | [需求](docs/01-requirements.md)    |
| 动态决策、模块与取舍       | [方案](docs/02-solution.md)        |
| 验收计划、实际结果与限制   | [评估](docs/03-evaluation.md)      |
| AI 辅助范围与个人验证      | [AI 使用记录](docs/04-ai-usage.md) |
| 学习、问题与改进           | [复盘](docs/05-retrospective.md)   |
| 测试范围                   | [测试说明](tests/README.md)        |
| 输入与运行证据约定         | [示例说明](examples/README.md)     |
| 开发环境、格式化和 lint    | [开发指南](docs/06-development.md) |

## 交付前检查

- 接入真实模型，完成模型根据工具结果调整动作的循环。
- 提供至少两条不同的实际执行路径，并设置执行步数上限。
- 保存至少三组输入、实际输出和 Trace，覆盖正常、信息不足和工具失败，并覆盖全部验收点。
- 添加可执行测试，把实际测试记录和运行证据放入 `examples/`，在评估文档中引用。
- 补全依赖、配置、运行命令、实际用时、个人修改记录和已知限制。
- 提交题号、仓库 URL 与最终 commit SHA；确认评审可读取仓库。
- 仅使用合成资料，不提交真实密钥、个人信息或业务私有数据。

## 参考

目录与文档分类参考 [agent-campus-submission-example](https://github.com/lwz1357/agent-campus-submission-example)。本项目独立编写初始化文件，未复制其离线模板实现。参考仓库展示的是交付组织；其中的题号与当前试卷编号可能不同，本项目使用当前试卷的第 4 题。
