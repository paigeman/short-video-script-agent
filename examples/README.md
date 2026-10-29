# 输入与运行证据

根目录的业务示例使用合成产品资料，输出来自实际执行的离线入口。每个 `*.output.json` 包含业务结果、Trace、完整工具参数与返回，以及各版草稿。

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

执行命令及逐项结果见 [评估](../docs/03-evaluation.md)，最新 136 项测试记录见 [截点后测试结果](post-checkpoint-test-results.txt)。此前的接入准备和业务测试日志保留为阶段记录。

`checkpoints/three-hour/` 保存不可覆盖的 3 小时真实进度与失败记录。`live/20261029-post-checkpoint/` 保存后续九场景真实验收，每个输入文件包含 request、materials、policy 和故障计划；输出文件保留 Trace。两份 `repair-*.json` 是明确注入的协议诊断，不计入业务路径。结果索引见 [截点后验收](../docs/12-post-checkpoint-acceptance.md)，复现步骤见 [验收指南](../docs/10-live-validation.md)。

`runtime-*` 文件是此前通用运行时的实际演示与测试证据，与业务示例分开保存。所有离线模型都是明确标记的替身，不能用于证明真实模型的自主决策效果。
