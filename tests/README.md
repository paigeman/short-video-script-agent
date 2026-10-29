# 测试

在仓库根目录执行 `npm test`，或：

```shell
uv run --locked python -m unittest discover -s tests -v
```

全部测试离线，不需要真实密钥。当前 145 项测试包含配置、协议、故障注入及验收记录核对；实际记录见 [最新测试结果](../examples/strengthening-final-test-results.txt)。真实模型验收单独运行，不混入单元测试。

| 测试模块                                                                | 验证范围                                                               |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `test_live_acceptance.py`                                               | 宿主故障注入、拒绝伪造交付、资料变更与验收回执一致性                   |
| `test_video_revision.py`                                                | 九项检查：既有稿件校验和修订、拒绝伪造证据、六种镜头、时间轴与风格判定 |
| `test_video_inputs.py`                                                  | 必填字段、类型、模拟开关边界、资料有效性                               |
| `test_video_tools.py`                                                   | 产品检索、估时、事实覆盖、品牌规则、检查记录与草稿对应                 |
| `test_video_service.py`                                                 | 全部业务路径、修订、最终业务校验、数据变更与 SDK 集成                  |
| `test_video_cli.py`                                                     | 实际 CLI、退出码、交互回答、真实模式配置失败与错误信息                 |
| `test_live_config.py`                                                   | 最小环境配置、非法值、脱敏、本地预检、CLI 参数传递和客户端关闭         |
| `test_agent_runner.py`                                                  | 多轮、批量调用、预算、状态与观察结果                                   |
| `test_runtime_capabilities.py`                                          | 输出修复、暂停继续、跨阶段预算、取消、上下文与时间                     |
| `test_responses_client.py`、`test_model_resilience.py`                  | 模拟 HTTP 下的真实 SDK、协议、上下文、错误、重试、资源关闭             |
| `test_tool_executor.py`、`test_tool_registry.py`、`test_tool_limits.py` | 工具参数、错误、注册与预算                                             |
| `test_validation.py`、`test_runtime_demo.py`                            | JSON 边界和通用演示 CLI                                                |

部分通用测试按需迁移自 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo)，来源映射见 [迁移说明](../docs/07-migration.md)。业务测试为本项目新增。

SDK 测试通过 `httpx.MockTransport` 拦截请求，业务演示通过确定性模型替身观察实际本地工具结果。部分测试执行 live 分支以验证配置接线，但客户端由测试替身或模拟 HTTP 替换，仍然没有真实模型调用。它们不能替代真实模型验收；完整边界见 [评估](../docs/03-evaluation.md)。
