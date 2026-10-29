# 通用 Agent 能力

## 范围

当前项目采用模型选择动作、执行工具、观察结果后再次决策的循环，具备 ReAct 的核心交互方式。本页描述通用运行控制与恢复机制，未加入独立规划器。任务说明、业务工具和最终输出 Schema 由上层提供；当前短视频实现见 [业务说明](09-business-rules.md)。

本页的能力在原迁移基础上实现，原始远程来源与文件映射继续记录在 [迁移说明](07-migration.md)。没有新增依赖，环境仍由 `uv` 管理。

## 能力与默认限制

| 能力             | 接口与行为                                                                                   | 默认值                                          |
| ---------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| 动态工具循环     | 模型决定调用、观察及下一步；串行执行同一批工具                                               | 3 个工具轮次、4 次模型请求、8 次实际工具执行    |
| 结构化结束       | `run(output_schema=...)` 注入 Schema 提示并在本地校验最终 JSON；失败时回传错误类别与字段路径 | 最多 1 次修复                                   |
| 请求补充信息     | 内置 `ask_user` 返回 `needs_input`，调用方提交回答后 `resume`                                | 默认开启，可用 `allow_clarification=False` 关闭 |
| 临时模型错误恢复 | 只重试被适配器标记为临时的错误；重试共享总请求预算                                           | 每次运行累计最多 2 次重试                       |
| 重试等待         | 指数退避与抖动，遵守服务端 `Retry-After`；无法在预算内等待则停止                             | 起始 0.5 秒、单次最多等待 30 秒                 |
| 执行时间         | 累计活跃执行时间，继续执行时保留已耗时，等待用户不计入                                       | 120 秒                                          |
| 取消             | `RunControl.cancel()`，在操作边界检查并可打断重试等待                                        | 返回 `cancelled`                                |
| 上下文限制       | 检查便携请求结构序列化后的 UTF-8 大小；超限明确停止，不裁剪成残缺调用链                      | 128,000 字节                                    |
| 工具输出限制     | 超大结果替换为 `output_too_large` 错误供模型决定下一步，不把截断片段当成功数据               | 32,000 字节                                     |
| 运行证据         | 运行 ID、模型标识、配置、调用计数、修复与重试次数、耗时、已知 Token 用量和 Trace             | `RunResult.to_dict()`                           |

重试、输出修复和用户补充后的执行均受同一组模型请求与工具预算约束。`ask_user` 消耗一个工具轮次，但不计入实际业务工具执行次数。普通工具错误会回传模型，运行时不擅自重放工具。

## 接入方式

```python
from src.agent.control import RunControl, RuntimePolicy
from src.agent.runner import AgentRunner
from src.llm.types import Message, ModelRequest
from src.tools.limits import ToolLoopLimits
from src.tools.registry import ToolRegistry


def run_task(client, registered_tools, prompt, output_schema, read_answer):
    control = RunControl()
    runner = AgentRunner(
        client,
        ToolRegistry(registered_tools),
        ToolLoopLimits(max_model_requests=8),
        policy=RuntimePolicy(max_output_repairs=2),
    )
    result = runner.run(
        ModelRequest([Message("user", prompt)]),
        output_schema=output_schema,
        control=control,
    )
    while result.status == "needs_input":
        answer = read_answer(result.question)
        result = runner.resume(result.checkpoint, answer, control=control)
    return result.to_dict()
```

`client` 可使用 `ResponsesClient.from_env()`；配置方式见 [README](../README.md)。传入 Schema 时，`completed` 表示最终 JSON 通过该 Schema 校验，解析后的数据位于 `data`。不传 Schema 时保留原有文本完成行为。事实正确性、创意质量和业务规则仍需上层工具与验收负责。

内置 `ask_user` 只接受一个非空 `question` 字段。它可以出现在一批调用中。此前工具保留结果，后续工具留在队列；回答按对应 `call_id` 写回后，再执行剩余队列。暂停不会让已经执行的工具重跑。

继续执行句柄只保存在内存中，必须交给原来的 runner，且只能使用一次。空回答、过大回答、错误 runner 不会消费句柄。不要在暂停期间修改 runner 配置或注册表，不要并发执行同一个运行。导出的结果不包含句柄、完整模型上下文或提供方加密上下文；导出 JSON 不能用于进程重启后的恢复。

## 状态与异常

| 状态          | 含义                                                             |
| ------------- | ---------------------------------------------------------------- |
| `completed`   | 模型结束；如果配置了输出 Schema，则已通过本地结构校验            |
| `needs_input` | 等待调用方提供真实用户回答                                       |
| `incomplete`  | 预算耗尽、上下文超限、运行超时、无有效最终结果或模型没有完整结束 |
| `model_error` | 永久模型错误、协议错误或临时错误重试耗尽                         |
| `cancelled`   | 调用方请求取消，运行时已停止后续动作                             |

错误配置与错误的继续执行调用抛出 `ValueError` 或 `SchemaError`，调用方应修正配置。运行中的模型失败会转为明确结果状态；原始服务端错误正文不会写入返回结果。

模型适配器保留 SDK 自动重试关闭，由运行器统一记录和限制重试。401、非法参数及额度或消费上限错误不自动重试；临时连接失败、请求超时、408、409、临时 429、500、502、503、504 可重试。服务端禁止重试的提示优先。处理依据为 [OpenAI 错误说明](https://developers.openai.com/api/docs/guides/error-codes)与[Python SDK 文档](https://developers.openai.com/api/reference/python)，具体兼容性由当前锁定 SDK 的模拟 HTTP 测试验证。

## 时间、上下文和记录的边界

模型请求超时取适配器配置、请求配置和剩余执行时间中的较小值。HTTP 超时按 SDK 的连接、读取等阶段生效，不承诺绝对墙钟截止。运行器在调用返回后再次检查累计时间，超时返回的答案不会标记为完成。

本地工具仍为同步函数。取消和时间上限在调用前后检查，无法强制终止已经阻塞的函数，也不回滚工具已经产生的副作用。未来有网络或长任务工具时，工具本身必须设置超时或支持取消；若需要强制终止，应单独增加进程隔离执行器。本阶段没有用后台线程假装已经停止工具。

上下文字节限制是本地资源限制，不等同于模型 Token 上限，不保证适配所有模型窗口。未加入 Tokenizer、自动摘要或历史裁剪，避免丢失工具调用与结果的对应关系。调用方应按选定模型配置预算。

Trace 的可见文本、参数和结果摘要最多保留 1,000 字符，并标明是否截断；完整结果在限制内继续回传模型。`usage` 仅累计服务端实际提供的用量，有缺失或失败请求时 `usage_complete=false`，不能据此断言总费用。Trace 不是通用脱敏器，真实业务接入后应根据内容决定能否公开保存。

## 离线验证

```shell
uv run --locked python -m src.agent.demo --scenario capabilities
npm test
```

合成演示依次经历提问暂停、注入明确标记的合成回答、执行本地工具、发现最终 JSON 字段类型错误、临时模型错误重试、校验成功。它使用确定性模型替身，未执行真实模型请求，也没有业务逻辑。

[实际演示结果](../examples/runtime-capabilities.output.json)保留暂停和最终状态，[测试记录](../examples/runtime-test-results.txt)记录实际运行命令和结果。其他运行时演示继续保留在 [评估文档](03-evaluation.md)。
