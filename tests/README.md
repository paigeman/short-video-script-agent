# 测试

在仓库根目录执行 `npm test`，或：

```shell
uv run --locked python -m unittest discover -s tests -v
```

全部测试离线，不需要密钥。当前 113 项测试包含通用运行时 80 项和业务 33 项；实际记录见 [业务阶段测试结果](../examples/business-test-results.txt)。

| 测试模块                                                                | 验证范围                                                   |
| ----------------------------------------------------------------------- | ---------------------------------------------------------- |
| `test_video_inputs.py`                                                  | 必填字段、类型、模拟开关边界、资料有效性                   |
| `test_video_tools.py`                                                   | 产品检索、估时、事实覆盖、品牌规则、检查记录与草稿对应     |
| `test_video_service.py`                                                 | 全部业务路径、修订、最终业务校验、数据变更与 SDK 集成      |
| `test_video_cli.py`                                                     | 实际 CLI、退出码、交互回答、真实模式配置失败与错误信息     |
| `test_agent_runner.py`                                                  | 多轮、批量调用、预算、状态与观察结果                       |
| `test_runtime_capabilities.py`                                          | 输出修复、暂停继续、跨阶段预算、取消、上下文与时间         |
| `test_responses_client.py`、`test_model_resilience.py`                  | 模拟 HTTP 下的真实 SDK、协议、上下文、错误、重试、资源关闭 |
| `test_tool_executor.py`、`test_tool_registry.py`、`test_tool_limits.py` | 工具参数、错误、注册与预算                                 |
| `test_validation.py`、`test_runtime_demo.py`                            | JSON 边界和通用演示 CLI                                    |

部分通用测试按需迁移自 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo)，来源映射见 [迁移说明](../docs/07-migration.md)。业务测试为本项目新增。

SDK 测试通过 `httpx.MockTransport` 拦截请求，业务演示通过确定性模型替身观察实际本地工具结果。它们不能替代真实模型验收；完整边界见 [评估](../docs/03-evaluation.md)。
