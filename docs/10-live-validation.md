# 真实模型验收指南

## 当前状态

真实模型所需的配置和参数传递已接通，并通过本地工具、模型替身及模拟 HTTP 测试。本次没有读取真实模型密钥或发起真实生成请求，也没有生成真实模型通过记录。

## 最小配置

使用进程环境变量，或在本机被 Git 忽略的 `.env` 中填写配置。Python 只读取进程环境，`.env` 由 `uv run --env-file .env` 显式加载，不增加 dotenv 依赖。不要复用或复制其他仓库的真实密钥文件到提交中。

| 变量                    | 必需 | 默认值与用途                                                                      |
| ----------------------- | ---- | --------------------------------------------------------------------------------- |
| `MODEL`                 | 是   | 服务接受的模型 ID；不要求登记本地模型档案                                         |
| `API_KEY`               | 是   | 对应服务的凭据；不写入 Trace、配置展示或验收参数                                  |
| `BASE_URL`              | 否   | 不设置时使用 SDK 默认地址；自定义值须为 HTTP(S) URL，不含用户密码、查询参数或片段 |
| `MODEL_TIMEOUT_SECONDS` | 否   | 30，单次请求超时；还会受整轮剩余时间限制                                          |
| `MAX_OUTPUT_TOKENS`     | 否   | 4096，每次请求的输出上限，必须为正整数                                            |
| `REASONING_EFFORT`      | 否   | 不发送，由服务使用模型默认值；可填 none/minimal/low/medium/high/xhigh/max/ultra   |
| `MAX_RUN_SECONDS`       | 否   | 180，整轮活跃时间上限；不包含暂停等待用户回答的时间                               |

推理强度会原样传递到 `reasoning.effort`，本地不根据模型名猜测或转换。允许的枚举并不表示每个模型都支持全部取值；应根据所选服务文档设置，不需要时省略变量。空字符串、非法数值、非有限超时会在请求前被拒绝。

输出上限包含模型推理等不可见输出，不能只按最终 JSON 长度设定。过低可能导致 `incomplete`，过高可能增加用量；默认值只是本项目的起点。真实请求仍受次数上限约束。参见 [OpenAI 官方推理说明](https://developers.openai.com/api/docs/guides/reasoning)。

## 本地配置检查

```shell
uv run --locked --env-file .env python -m src.config
```

此命令只校验配置并输出允许公开的字段，不创建模型客户端，不验证密钥是否有效、网络是否可用或服务是否接受该模型。成功退出码为 0，配置错误为 2；错误只指出变量名，不回显其值。

若已由系统设置进程环境变量，可省略 `--env-file .env`。离线模式不加载 `ModelConfig`，不会因真实模型配置缺失而失败。

## 实际运行路径

下面的命令会发起真实模型请求，应在确认服务、模型和本机凭据后执行。每次输出为完整 JSON，包含配置参数、业务结果、工具记录、草稿和 Trace。

```shell
uv run --locked --env-file .env python -m src.main --mode live --input examples/normal.input.json
uv run --locked --env-file .env python -m src.main --mode live --input examples/no-materials.input.json
uv run --locked --env-file .env python -m src.main --mode live --input examples/duration-repair.input.json
```

第一条检查正常检索、估时和规则检查；第二条观察模型在无素材时是否改写查询、追问或明确停止；第三条使用 10 秒上限，观察真实模型是否需要修订。第三条不保证首稿超限，只有 Trace 确实出现失败后修改和复检时，才能记为真实修订路径。不要在真实模式使用 `--offline-scenario` 制造模型行为。

缺字段会在本地直接返回，不算一条真实模型执行路径。`needs_input` 退出码为 3，未完成或模型失败为 1，不应因为退出码非零就丢弃验收记录。需要交互时增加 `--interactive`；用户回答不会直接成为可信产品素材。

## 核对记录

- `model_settings` 保存请求模型、推理强度、输出上限、超时和整轮时限。完整服务地址不导出，只记录 `custom` 或 `sdk_default`；服务身份需在本机另行确认，公开前再审查。
- `runtime` 保存请求次数、重试、工具轮次、用量、耗时和运行限制。`usage_complete=false` 表示用量信息不完整，不能据此声称完整成本。
- `trace` 中模型事件会记录 `incomplete_reason`，目前保留 `max_output_tokens`、`content_filter`，其他值归为 `unknown`。不导出提供方原始错误文本或内部推理上下文。
- 顶层 `status=completed` 还需通过同一草稿的业务最终检查；配置有效、HTTP 成功或运行时结束均不等于脚本交付成功。
- 验收记录应同时保留输入、资料版本、代码 commit 和实际输出。只有真实执行才标记为真实证据，不能把 Mock 结果改名使用。

运行输出仍包含请求、素材、工具参数和模型可见文案，配置脱敏不等于全文隐私脱敏。公开前需检查这些内容。可先保存到被忽略的 `.agent-tmp/` 中，在确认内容适合公开后再整理至 `examples/`。

## DeepSeek 与迁移边界

DeepSeek 官方当前提供 Responses API，可复用本项目客户端；配置对应的 `BASE_URL` 和模型即可进入验证。其 `reasoning` 输入使用明文 `content`，不支持加密推理内容；`include` 等不支持的请求参数按其文档忽略。当前客户端会保留完整提供方输出供后续工具轮次使用，测试分别覆盖明文和加密上下文。真实服务兼容性仍需实际执行确认。参见 [DeepSeek 官方兼容性说明](https://api-docs.deepseek.com/guides/responses_api/)。

只迁移 AI-demo 的最小配置与请求参数处理，不引入模型档案、DeepSeek prompt encoder、HuggingFace Tokenizer、本地 Token 预算器或流式终端。配置来源和固定版本见 [迁移说明](07-migration.md)。
