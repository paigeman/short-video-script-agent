# 输入与运行证据

业务示例使用合成产品资料，全部输出来自实际执行的离线入口。每个 `*.output.json` 包含业务结果、Trace、完整工具参数与返回，以及各版草稿。

| 文件前缀             | 场景                               | 预期状态    |
| -------------------- | ---------------------------------- | ----------- |
| `normal`             | 正常生成并检查                     | completed   |
| `missing`            | 缺平台信息                         | needs_input |
| `no-materials`       | 检索无结果，改写后仍无依据         | needs_input |
| `tool-failure`       | 一次检索故障后的恢复               | completed   |
| `duration-repair`    | 估时超限后修订与复检               | completed   |
| `rules-repair`       | 无依据量化与保证表述修订           | completed   |
| `unrepairable`       | 修订后仍无法满足时长               | incomplete  |
| `persistent-failure` | 持续工具故障，使用 normal 输入     | incomplete  |
| `limit`              | 持续调用达到上限，使用 normal 输入 | incomplete  |

执行命令及逐项结果见 [评估](../docs/03-evaluation.md)，最新测试记录见 [真实接入准备阶段测试结果](live-readiness-test-results.txt)。此前的 [业务阶段测试结果](business-test-results.txt)保留为阶段记录。真实模型执行记录尚未生成，接入步骤见 [验收指南](../docs/10-live-validation.md)。

`runtime-*` 文件是此前通用运行时的实际演示与测试证据，与业务示例分开保存。所有离线模型都是明确标记的替身，不能用于证明真实模型的自主决策效果。
