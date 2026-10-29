# 输入与运行证据

所有示例使用合成产品资料。真实模型、离线替身和协议诊断分别存放，不能互相替代效果证据。最终结果与用时见[完成记录](../docs/14-final-completion.md)，预期与实际结果见[评估](../docs/03-evaluation.md)。

## 真实模型记录

| 位置                                                 | 内容                                                          |
| ---------------------------------------------------- | ------------------------------------------------------------- |
| `checkpoints/three-hour/`                            | 不可覆盖的 3h 进度、失败与原始输入输出                        |
| `live/20261029-post-checkpoint/`                     | 格式修复后的九场景验收，两份 `repair-*.json` 是单独的协议诊断 |
| `live/20261029-strengthening/`                       | 最新十二场景输入、输出和 Trace，原始清单判定为 11/12          |
| `live/20261029-strengthening/assessment-review.json` | 教学镜头判定更正后，对同批输出复核为 12/12                    |
| `live/20261029-strengthening/initial/`               | 首次三场景输出与速览重复讲解的问题记录                        |

真实验收的 `*.input.json` 是包装快照，包含 `request`、`materials`、`policy` 和故障计划，不能直接作为普通 CLI 请求。`duration-repair` 还记录历史原稿的来源和 SHA-256。`*.output.json` 含实际状态、Trace、工具回执和各版草稿。

根目录的 `revise-existing.input.json`、`style-tutorial.input.json`、`style-teaser.input.json` 可直接用于业务 CLI，分别对应已有稿件压缩、新手教学和功能速览。运行方法见 [README](../README.md)。

## 离线记录

根目录早期业务 `*.output.json` 来自实际执行的确定性模型替身，保留为阶段证据，输出结构可能早于新增的分镜时间轴。

| 文件前缀             | 场景                           | 预期状态    |
| -------------------- | ------------------------------ | ----------- |
| `normal`             | 正常生成与检查                 | completed   |
| `missing`            | 缺平台信息                     | needs_input |
| `no-materials`       | 改写检索后仍无资料             | needs_input |
| `tool-failure`       | 一次检索故障后恢复             | completed   |
| `duration-repair`    | 替身首稿超时长后修订           | completed   |
| `rules-repair`       | 修正无依据数字与保证表述       | completed   |
| `unrepairable`       | 修订后仍无法满足 1 秒上限      | incomplete  |
| `persistent-failure` | 持续检索故障，使用 normal 输入 | incomplete  |
| `limit`              | 达到调用上限，使用 normal 输入 | incomplete  |

指定 `--mode offline`；需要对应行为时增加同名 `--offline-scenario`。`runtime-*` 保存通用运行时的演示及测试，与业务证据分开。

## 测试日志

[145 项业务补强回归](strengthening-final-test-results.txt)记录最近一次实现修改后的完整测试。[文档命令验证](documentation-command-checks.txt)记录 uv 与直接 Python 的入口检查，以及直接 Python 运行的 145 项测试。

此前 144 项中间记录、136 项截点后测试，以及 125 项接入准备等日志保留各自的阶段含义。旧文件不被后续成功结果覆盖。
