# 测试

在仓库根目录执行：

```shell
uv run --locked python -m unittest discover -s tests -v
```

也可执行 `npm test`。默认测试全部离线，不需要密钥。工具、注册表及预算测试按需迁移自 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo)，详细映射见 [迁移说明](../docs/07-migration.md)。

| 测试模块                   | 验证范围                                                         |
| -------------------------- | ---------------------------------------------------------------- |
| `test_tool_executor.py`    | 参数校验、未知工具、执行错误、预算、JSON 边界                    |
| `test_tool_registry.py`    | 注册顺序、重复名称和未知工具                                     |
| `test_tool_limits.py`      | 执行预算耗尽后禁止额外执行                                       |
| `test_agent_runner.py`     | 多轮与批量调用、观察结果、三类上限、状态、Trace 和输入保护       |
| `test_responses_client.py` | 真实 SDK 与模拟 HTTP、协议映射、上下文回传、错误、超时、资源关闭 |
| `test_validation.py`       | JSON 解析、Schema 校验和错误区别                                 |
| `test_runtime_demo.py`     | 从真实 CLI 入口执行四个离线场景                                  |

新增 `test_runtime_capabilities.py` 验证输出修复、提问后的继续执行、跨阶段预算、取消、时间与上下文限制；`test_model_resilience.py` 验证 HTTP 错误分类、等待提示、请求超时和异常协议。

SDK 测试通过 `httpx.MockTransport` 拦截请求。演示测试使用确定性模型替身，不能替代真实模型决策测试。短视频业务测试尚待实现。实际执行记录见 [测试结果](../examples/runtime-test-results.txt)。
