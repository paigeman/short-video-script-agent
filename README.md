# Short Video Script Agent

第 4 题「短视频脚本 Agent」项目。

**当前已完成基础 Agent 运行时迁移，包括模型适配、工具执行、受限循环、输出校验与修复、补充信息后的继续执行、失败恢复和离线测试。短视频脚本生成、素材检索、时长及品牌规则检查尚未实现，也未进行真实模型业务验收。**

## 环境与安装

使用 Python 3.13+ 和 `uv` 管理项目环境与依赖：

```shell
uv sync --locked
```

运行时依赖为 OpenAI SDK、HTTPX 和 jsonschema，具体版本及传递依赖由 `pyproject.toml` 和 `uv.lock` 管理。`requirements.txt` 是从锁文件导出的运行时兼容清单，推荐使用 `uv`。

## 验证基础运行时

以下入口使用确定性模型替身和本地演示工具，无需密钥，不联网：

```shell
uv run --locked python -m src.agent.demo --scenario normal
uv run --locked python -m src.agent.demo --scenario tool-failure
uv run --locked python -m src.agent.demo --scenario limit
uv run --locked python -m src.agent.demo --scenario capabilities
uv run --locked python -m unittest discover -s tests -v
```

输出包含状态、调用计数和实际执行 Trace，明确标注 `offline_demo`。前三个场景分别演示正常结束、工具失败后继续执行、达到上限后返回未完成。`capabilities` 串联提问、继续执行、结构修复和临时错误重试，并明确标记合成用户回答。这些记录验证运行机制，不能证明真实模型决策或脚本生成效果。

原短视频输入入口保留：

```shell
uv run --locked python -m src.main --input examples/normal.input.json
```

该入口仍返回 `not_implemented`；JSON 文件读取或格式错误返回 `invalid_input` 和非零退出码。短视频业务功能应在基础运行时之上继续实现。

## 模型接入

`src/llm/responses.py` 提供同步 Responses API 适配器。通过 `ResponsesClient.from_env()` 读取进程环境中的 `MODEL`、`API_KEY`，以及可选 `BASE_URL` 和 `MODEL_TIMEOUT_SECONDS`；不自动读取 `.env` 文件。字段说明见 `.env.example`。

适配器已通过真实 SDK 加模拟 HTTP 的离线测试，但没有发送真实生成请求。目标服务需要支持该适配器使用的 Responses API 字段，不能仅凭“兼容接口”认定所有服务都支持。运行时接入示例见 [迁移说明](docs/07-migration.md)。

通用能力、默认限制和业务接入示例见 [Agent 能力说明](docs/08-runtime-capabilities.md)。本地工具超时与取消采用协作方式，内存中的暂停状态不跨进程保存。

## 代码组织

```text
src/
├── main.py                 # 尚待实现的短视频业务入口
├── agent/
│   ├── runner.py           # 循环、输出校验与暂停／继续
│   ├── control.py          # 资源策略与取消信号
│   ├── state.py            # 结果、统计与内存继续执行句柄
│   └── demo.py             # 明确标记的离线演示
├── llm/
│   ├── types.py            # 消息、请求、响应和客户端协议
│   └── responses.py        # 同步 Responses API 适配
├── tools/
│   ├── definition.py       # 工具定义及处理函数
│   ├── protocol.py         # 调用与结果协议
│   ├── registry.py         # 注册表
│   ├── executor.py         # 参数校验、执行和错误回传
│   ├── limits.py           # 次数上限和执行预算
│   └── errors.py           # 工具错误和上限停止原因
└── validation.py           # JSON 解析及 Schema 校验
```

`tests/` 保存迁移回归和集成测试，`examples/` 保存实际离线运行证据，`data/` 保存尚未接入业务工具的合成素材。项目不依赖原仓库的目录、环境或配置文件。

## 开发质量检查

```shell
npm ci --ignore-scripts
npm run format
npm run check
npm test
```

格式化与 lint 使用项目本地的 Prettier、markdownlint-cli2 和 Ruff。规则与分项命令见 [开发指南](docs/06-development.md)。

## 评审导航

| 内容                 | 入口                               |
| -------------------- | ---------------------------------- |
| 用户、目标和成功标准 | [需求](docs/01-requirements.md)    |
| 当前结构及业务待办   | [方案](docs/02-solution.md)        |
| 测试证据及验证边界   | [评估](docs/03-evaluation.md)      |
| AI 辅助和复用记录    | [AI 使用](docs/04-ai-usage.md)     |
| 取舍及后续工作       | [复盘](docs/05-retrospective.md)   |
| 环境、格式化和 lint  | [开发指南](docs/06-development.md) |
| 远程来源和迁移范围   | [迁移说明](docs/07-migration.md)   |

通用 Agent 的完成状态只代表运行与配置的结构校验通过，业务验收由上层负责。

## 来源与交付边界

目录组织参考 [agent-campus-submission-example](https://github.com/lwz1357/agent-campus-submission-example)。基础运行时按需迁移自 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo)，来源 commit 与文件映射见迁移说明。

当前试卷中本项目对应第 4 题。后续仍需完成真实模型业务流程、全部题目验收场景和实际运行证据；最终提交题号、仓库 URL 与最终 commit SHA。禁止提交真实密钥、个人信息或私有业务资料。
