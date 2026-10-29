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

执行命令及逐项结果见 [评估](../docs/03-evaluation.md)，最新 145 项测试记录见 [补强最终测试结果](strengthening-final-test-results.txt)。此前 144 项中间记录、136 项截点后测试及更早日志均保留为阶段记录。

`checkpoints/three-hour/` 保存不可覆盖的 3 小时真实进度与失败记录。`live/20261029-post-checkpoint/` 保存后续九场景真实验收，每个输入文件包含 request、materials、policy 和故障计划；输出文件保留 Trace。两份 `repair-*.json` 是明确注入的协议诊断，不计入业务路径。结果索引见 [截点后验收](../docs/12-post-checkpoint-acceptance.md)，复现步骤见 [验收指南](../docs/10-live-validation.md)。

`live/20261029-strengthening/` 保存最新十二场景：原始 `manifest.json` 判定为 11/12；教学界面特写被误判，更正验收器后对同批输出的 12/12 复核另存于 `assessment-review.json`。`initial/` 保留首次三场景输出、速览重复讲解的问题记录及原始清单，未被最新结果覆盖。详情见 [审核补强](../docs/13-review-strengthening.md)。

根目录新增的 `revise-existing.input.json`、`style-tutorial.input.json`、`style-teaser.input.json` 是可直接用于业务 CLI 的普通请求，对应上述最新真实场景。已有稿件来源为此前真实正常场景，输入中的原稿没有伪造检查结果；完整来源摘要在真实验收包装快照中。

`runtime-*` 文件是此前通用运行时的实际演示与测试证据，与业务示例分开保存。所有离线模型都是明确标记的替身，不能用于证明真实模型的自主决策效果。
