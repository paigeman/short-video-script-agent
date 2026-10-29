# 基础运行时迁移

## 来源

源仓库为 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo)，固定来源为 [commit d50aab3](https://github.com/FadeDemo/AI-demo/commit/d50aab30a226e3ce8eeedcad96ec1e6fba460081)。迁移对象位于该提交的 `projects/llm-terminal-assistant/`。来源使用远程仓库地址记录，项目运行不依赖原仓库。

## 文件映射

| 远程源文件                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | 当前位置                                                                      | 处理方式                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| [工具定义](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/definition.py)、[协议](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/protocol.py)、[注册表](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/registry.py) | `src/tools/` 对应文件                                                         | 保留结构和行为，修改导入路径                                           |
| [执行器](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/executor.py)                                                                                                                                                                                                                                                                                                                                                       | `src/tools/executor.py`                                                       | 保留参数校验与错误回传，增加 Schema 自检、严格 JSON 和结果可序列化检查 |
| [限制](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/loop.py)、[错误](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/tools/errors.py)                                                                                                                                                                                       | `src/tools/limits.py`、`errors.py`                                            | 保留三类上限与错误，增加上限参数校验                                   |
| [请求响应类型](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/model.py)、[消息](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/message.py)、[客户端协议](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/client.py)                   | `src/llm/types.py`                                                            | 合并并裁剪为同步调用所需的类型                                         |
| [模型适配](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/adapter/openai_client.py)、[协议转换](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/adapter/protocol_mapping.py)                                                                                                                                                        | `src/llm/responses.py`                                                        | 提取同步 Responses API 路径，保留完整输出用于后续请求                  |
| [连续调用](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/cli.py#L200)、[结果回传](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/conversation.py#L92)                                                                                                                                                                             | `src/agent/runner.py`                                                         | 抽取控制流程，移除终端、历史与 Token 预算耦合，增加运行结果与 Trace    |
| [JSON 解析](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/structured_output/parser.py)、[Schema 校验](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/structured_output/schema_validator.py)                                                                                                                                       | `src/validation.py`                                                           | 保留分阶段校验机制，移除学习卡片业务类型                               |
| [工具执行测试](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/tests/test_tool_executor.py)、[注册表测试](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/tests/test_tool_registry.py)、[预算测试](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/tests/test_tool_loop.py)                                              | `tests/test_tool_executor.py`、`test_tool_registry.py`、`test_tool_limits.py` | 迁移原有回归测试并扩展输入边界                                         |

运行器集成测试、Responses SDK 模拟 HTTP 测试、通用校验测试、演示入口及其 CLI 测试为本项目补充。它们不代表原仓库已有同样的模块结构。

## 范围与依赖

没有迁移流式显示、终端键盘交互、Tokenizer、历史裁剪、多模型档案、采样实验、供应商编码器、学习卡片业务和草稿存储。首版保留单模型、同步请求和串行工具执行。

Python 最低版本统一为 3.13，保留来源使用的类型别名和枚举语法。运行依赖固定为 OpenAI SDK 2.53.0、HTTPX 0.28.1 和 jsonschema 4.26.0，使用 `uv` 管理。

## 协议与完成边界

保留同一次响应中的全部输出项，再追加工具结果，避免丢失工具调用间的提供方上下文。这个处理参考 [OpenAI 函数调用说明](https://developers.openai.com/api/docs/guides/function-calling)与[推理上下文说明](https://developers.openai.com/api/docs/guides/reasoning)。适配器使用 `store=false` 并请求加密上下文，不把提供方上下文导出为 Trace。

工具参数使用本地 JSON Schema 验证，API 工具定义显式使用 `strict=false`，避免假设任意本地 Schema 都满足提供方严格模式要求。跨服务兼容性需要针对选定服务进行验证。

## 程序接入示例

下面展示业务代码如何接入基础运行时。`registered_tools` 由上层工具实现提供；当前业务接入见 `src/video/service.py`。真实调用需提前配置进程环境中的 `MODEL` 和 `API_KEY`；`.env` 不会被自动读取。

```python
from src.agent.runner import AgentRunner
from src.llm.responses import ResponsesClient
from src.llm.types import Message, ModelRequest
from src.tools.registry import ToolRegistry


def run_request(prompt, registered_tools):
    with ResponsesClient.from_env() as client:
        runner = AgentRunner(client, ToolRegistry(registered_tools))
        return runner.run(ModelRequest([Message("user", prompt)]))
```

当前验证使用模型替身与模拟 HTTP，没有加载个人密钥或发起真实生成请求。业务场景仍需按 [评估计划](03-evaluation.md) 完成。

## 后续通用扩展

初次迁移之后补充的输出修复、暂停与继续、重试、运行控制和统计在本项目中实现，未从来源仓库整套复制。当前接口及验证边界见 [通用 Agent 能力](08-runtime-capabilities.md)。

## 真实模型配置迁移

本轮仍以同一远程 commit 为来源，裁剪并改写以下内容：

| 远程源文件                                                                                                                                                                                | 本项目位置             | 迁移与调整                                                                                                 |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| [config.py](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/config.py)                       | `src/config.py`        | 提取 ModelConfig、环境变量读取和数值检查；移除模型档案、流式与预算耦合，增加字段级安全错误和公开参数白名单 |
| [model.py](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/model.py)                         | `src/llm/types.py`     | 按需增加请求推理强度及安全的未完成原因字段                                                                 |
| [openai_client.py](https://github.com/FadeDemo/AI-demo/blob/d50aab30a226e3ce8eeedcad96ec1e6fba460081/projects/llm-terminal-assistant/src/llm_terminal_assistant/adapter/openai_client.py) | `src/llm/responses.py` | 提取 reasoning.effort 传递和 incomplete_details 原因处理，沿用已有同步 SDK 适配                            |

配置预检入口、业务参数接线、脱敏模型设置和新增测试为本项目实现。输出 Token 上限复用已有 `max_output_tokens` 字段；整轮时限复用已有 RuntimePolicy，不新增预算器。使用 uv 显式加载 `.env`，没有迁移 dotenv 或新增依赖。实际用法见 [真实模型验收指南](10-live-validation.md)。
