# Short Video Script Agent

第 4 题「短视频脚本 Agent」项目。已实现输入校验、素材检索、草稿估时、引用与品牌规则检查，以及模型根据工具结果修订脚本的业务入口。

已完成 DeepSeek `deepseek-flash` 的十二场景验收（十一条真实模型路径与一条本地缺字段路径）及 145 项离线测试。最新补强验证了已有稿件从 14.2 秒压缩到 8.3 秒，并交付不同教学与速览结构。原始判定、更正记录和限制见 [审核补强](docs/13-review-strengthening.md)，此前九场景保留于 [截点后验收](docs/12-post-checkpoint-acceptance.md)。用户报告达到 3 小时时的进度另存于 [冻结快照](docs/11-three-hour-checkpoint.md)，后续成果不计入该截点。

## 安装与快速运行

使用 Python 3.13+ 和 `uv`：

```shell
uv sync --locked
uv run --locked python -m src.main --mode offline --input examples/normal.input.json
uv run --locked python -m src.main --mode offline --input examples/duration-repair.input.json --offline-scenario duration-repair
uv run --locked python -m src.main --mode offline --input examples/tool-failure.input.json
```

输出为 JSON，包含业务状态、可编辑脚本、每个分镜的估计时长与起止时间、素材 ID、实际检查记录和 Trace。示例记录及预期结果见 [评估](docs/03-evaluation.md)。

输入字段为 `topic`、`audience`、`platform`、`duration_seconds`、`style`、`product_id`。目标时长是 1–300 的整数秒上限；本项目额外使用 `product_id` 隔离产品素材。缺字段返回 `needs_input`，字段类型错误返回 `invalid_input`。完整规则见 [业务说明](docs/09-business-rules.md)。

可选 `initial_draft` 用于修改已有稿件。原稿必须重新检索依据、诊断和检查，模型再依据反馈选择压缩或重写。可直接运行 [已有稿件输入](examples/revise-existing.input.json)，或使用 [新手教学](examples/style-tutorial.input.json)与 [功能速览](examples/style-teaser.input.json)输入比较结构。

## 真实模型入口

在进程环境中配置 `MODEL`、`API_KEY`，按需设置服务地址、推理强度、输出 Token 上限与超时。先做不调用模型的配置检查，再启动业务：

```shell
uv run --locked python -m src.config
uv run --locked python -m src.main --mode live --input examples/normal.input.json
```

Python 不会自动读取 `.env`，可在上述 `uv run` 命令中显式增加 `--env-file .env`。无需安装 dotenv。变量与完整复现命令见 [真实模型验收指南](docs/10-live-validation.md)；不要把真实值提交到仓库。服务需要支持 Responses API。默认模式为 `live`，配置错误时明确失败，不会自动切换到 Mock。

运行输出的 `model_settings` 记录配置的模型、请求参数和 JSON 输出模式，不含密钥或完整服务地址。模型返回的 `max_output_tokens` 中断原因会保留在 Trace 中。配置检查与模拟 HTTP 测试都不代表真实模型验收通过。

| CLI 参数                  | 用途                                                                                |
| ------------------------- | ----------------------------------------------------------------------------------- |
| `--input`                 | 必填，请求 JSON 路径                                                                |
| `--mode live\|offline`    | 选择真实适配器或明确标记的离线替身                                                  |
| `--offline-scenario`      | 离线验收场景，例如 `duration-repair`、`rules-repair`、`persistent-failure`、`limit` |
| `--materials` / `--rules` | 指定替代合成素材与品牌规则文件，便于修改数据复验                                    |
| `--interactive`           | 模型发起补充信息请求时，从 stdin 读取回答，提示写到 stderr                          |

缺少必填字段时先修改输入文件再运行；`--interactive` 用于已经启动的模型循环。无素材时可补充合成资料文件后重新运行，用户口述内容不会自动成为已验证的产品事实。输入中的 `simulate_tool_failure` 仅供离线故障验收，真实模式不接受该开关。

退出码：`0` 表示业务检查通过，`3` 表示等待补充信息，`2` 表示输入或配置错误，`1` 表示未完成、模型错误或取消。

## 业务机制

模型可以调用 `search_materials`、`estimate_duration`、`check_rules` 和通用 `ask_user`。程序没有为真实模型规定固定分支路径，模型依据实际观察选择改写检索、修订草稿、继续检查、追问或停止。

每份候选脚本有按内容计算的 `draft_id`。只有同一份草稿的估时与规则检查均实际通过，程序才组装 `script` 并返回业务 `completed`。模型自行声称成功、伪造检查字段或提交未检查的修改稿都不会绕过最后检查。

采用保守的文案规则：产品表述使用引用素材的完整原文，可以组合获准过渡语和标点；不接受任意自由改写。画面描述由六种可编辑镜头类型映射生成，包括界面特写、步骤卡和回顾卡。它能明确检查引用覆盖与数值变造，但限制创意表达，不是通用语义事实核查器。

时长使用口播单位、字幕阅读、画面停留与转场进行确定性估算，不代表实际录制时长。本轮已核对合成案例的主题与引用，受众、风格及创意质量仍缺少独立人工评估。

## 代码组织

```text
src/
├── config.py            # 轻量真实模型配置、校验和脱敏参数记录
├── main.py              # 业务 CLI，明确区分 live 和 offline
├── video/
│   ├── schemas.py       # 请求、草稿和最终动作结构
│   ├── catalog.py       # 合成资料、规则加载及检索
│   ├── checks.py        # 时长、事实引用、品牌规则
│   ├── tools.py         # 工具、草稿与检查记录
│   ├── service.py       # 模型接入、业务结果校验
│   └── offline.py       # 明确标记的离线模型替身
├── agent/               # 通用循环、恢复、预算与运行记录
├── llm/                 # Responses API 与模型协议
├── tools/               # 通用注册、参数校验与工具执行
└── validation.py        # 严格 JSON 与 Schema 校验
```

业务层没有新增第三方依赖。OpenAI SDK、HTTPX、jsonschema 和开发工具版本由 `pyproject.toml`、`uv.lock` 管理。`requirements.txt` 为锁文件导出的兼容清单。

## 开发与验证

```shell
npm ci --ignore-scripts
npm exec -- prettier --write README.md
npm run check
npm test
```

质量工具使用本地 Prettier、markdownlint-cli2 和 Ruff。按修改范围格式化，不能对冻结快照执行写入式格式化；完整命令见 [开发指南](docs/06-development.md)。基础运行时仍可单独执行 `python -m src.agent.demo --scenario capabilities`；它与短视频业务入口分开。

| 内容                  | 入口                                              |
| --------------------- | ------------------------------------------------- |
| 用户、范围和成功标准  | [需求](docs/01-requirements.md)                   |
| 动态决策与实现结构    | [方案](docs/02-solution.md)                       |
| 实际结果、失败与限制  | [评估](docs/03-evaluation.md)                     |
| AI 辅助及个人贡献边界 | [AI 使用](docs/04-ai-usage.md)                    |
| 取舍与后续工作        | [复盘](docs/05-retrospective.md)                  |
| 开发工具              | [开发指南](docs/06-development.md)                |
| 远程代码来源          | [迁移说明](docs/07-migration.md)                  |
| 通用运行时接口        | [Agent 能力](docs/08-runtime-capabilities.md)     |
| 检索、时长与品牌规则  | [业务说明](docs/09-business-rules.md)             |
| 真实模型配置与执行    | [验收指南](docs/10-live-validation.md)            |
| 3 小时进度与未完成项  | [冻结快照](docs/11-three-hour-checkpoint.md)      |
| 截点后修复及真实结果  | [后续验收](docs/12-post-checkpoint-acceptance.md) |
| 压缩与风格补强证据    | [审核补强](docs/13-review-strengthening.md)       |

目录组织参考 [agent-campus-submission-example](https://github.com/lwz1357/agent-campus-submission-example)，基础运行时按需迁移自 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo)。迁移文档记录固定 commit 与文件映射；本轮业务实现独立编写。

最终交卷仍需填写题号、仓库 URL、最终 commit SHA、真实用时与个人贡献，并区分 3 小时截点和后续改进。不要提交真实密钥、个人信息或私有业务资料。
