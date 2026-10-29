# 测试与评估

离线回归和真实模型验收分开记录。当前 145 项离线测试通过；最新十二场景中，十一条路径调用了 DeepSeek `deepseek-flash`，缺字段在本地返回。七个场景交付脚本，三个请求补充信息，两个明确未完成。

最新一轮的原始自动判定为 11/12。教学场景用了界面特写，验收器当时只接受完整界面镜头，造成误判。修正验收器后，对同一批输出复核为 12/12，模型结果没有重写。原始[清单](../examples/live/20261029-strengthening/manifest.json)与[更正记录](../examples/live/20261029-strengthening/assessment-review.json)分别保留。

## 测试预期

题目要求正常生成、缺关键信息、无素材、工具失败和超时长处理五类验收。本次另加更换素材、无依据效果数字、持续故障和风格结构等场景。

生成场景只有在脚本结构完整、来源成立、时长不超限且同稿件检查通过时才算交付。资料不足应追问或明确停止，无法满足约束应保留原因。工具失败须留下真实错误，不能伪造恢复或检查成功。次数上限另用离线测试核对。

真实决策证据至少需要两条依据不同观察调整动作的路径。记录应能核对步骤、工具参数、返回摘要、后续动作和简短理由；固定离线分支不计作这类证据。

## 实际结果

下面每个输入快照都含请求、素材、规则和故障计划，每个输出都含实际状态与 Trace。需要直接运行业务 CLI 时使用根目录的普通输入，或从快照中取出 `request`；完整复现命令见 [README](../README.md) 与[验收指南](10-live-validation.md)。

| 场景         | 预期                         | 实际结果                                               | 输入                                                                          | 输出与 Trace                                                                   |
| ------------ | ---------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 正常生成     | 来源与检查一致，时长不超限   | 交付 16.7 秒脚本，上限 30 秒                           | [输入](../examples/live/20261029-strengthening/normal.input.json)             | [记录](../examples/live/20261029-strengthening/normal.output.json)             |
| 缺关键信息   | 指出缺失字段                 | 缺少 platform，返回 `needs_input`，没有模型调用        | [输入](../examples/live/20261029-strengthening/missing.input.json)            | [记录](../examples/live/20261029-strengthening/missing.output.json)            |
| 无素材       | 改写检索或请求资料，不能编造 | 六次检索仍无依据，模型请求补充资料                     | [输入](../examples/live/20261029-strengthening/no-materials.input.json)       | [记录](../examples/live/20261029-strengthening/no-materials.output.json)       |
| 一次工具故障 | 观察错误后恢复或明确停止     | 首次检索异常，模型改用 P01 查询，交付 14.9 秒脚本      | [输入](../examples/live/20261029-strengthening/tool-failure.input.json)       | [记录](../examples/live/20261029-strengthening/tool-failure.output.json)       |
| 旧稿超时长   | 压缩后复检或明确失败         | 原稿 14.2 秒超过 10 秒，修订至 8.3 秒并通过复检        | [输入](../examples/live/20261029-strengthening/duration-repair.input.json)    | [记录](../examples/live/20261029-strengthening/duration-repair.output.json)    |
| 缩短时长     | 遵守新的 10 秒上限           | 首稿 6.6 秒直接通过，单独记为时长变化用例              | [输入](../examples/live/20261029-strengthening/short-duration.input.json)     | [记录](../examples/live/20261029-strengthening/short-duration.output.json)     |
| 1 秒上限     | 无法满足时明确未完成         | 返回 `cannot_meet_constraints`，未交付脚本             | [输入](../examples/live/20261029-strengthening/unrepairable.input.json)       | [记录](../examples/live/20261029-strengthening/unrepairable.output.json)       |
| 无依据的 80% | 不添加没有资料支持的效果数字 | 请求澄清，未交付虚假文案                               | [输入](../examples/live/20261029-strengthening/unsupported-claim.input.json)  | [记录](../examples/live/20261029-strengthening/unsupported-claim.output.json)  |
| 持续工具故障 | 停止并保留错误               | 返回 `tool_failure`，未伪造检查通过                    | [输入](../examples/live/20261029-strengthening/persistent-failure.input.json) | [记录](../examples/live/20261029-strengthening/persistent-failure.output.json) |
| 替换素材     | 输出与来源随资料变化         | 使用“支持调整字幕显示位置”，修订检查后交付 13.1 秒脚本 | [输入](../examples/live/20261029-strengthening/changed-materials.input.json)  | [记录](../examples/live/20261029-strengthening/changed-materials.output.json)  |
| 新手教学     | 步骤、界面展示和回顾         | 修正规则问题后交付 17.8 秒脚本，使用步骤卡、特写与回顾 | [输入](../examples/live/20261029-strengthening/style-tutorial.input.json)     | [记录](../examples/live/20261029-strengthening/style-tutorial.output.json)     |
| 熟练受众速览 | 简短、突出功能，避免重复讲解 | 四镜头共 15.2 秒，两条事实各集中在一个镜头             | [输入](../examples/live/20261029-strengthening/style-teaser.input.json)       | [记录](../examples/live/20261029-strengthening/style-teaser.output.json)       |

工具异常由本地故障计划注入，模型回复来自真实服务。旧稿来自此前真实运行，在新时长要求下重新检查；原稿来源及摘要随输入保存。首稿直接通过的 6.6 秒案例不计作压缩成功。

## 怎样核对 ReAct 与交付

[方案](02-solution.md)列出了四条可直接查看的动作变化。记录中的 `reason` 是简短动作目的，`tool_records` 保存执行参数和完整回执，`trace` 记录步骤与后续动作。无素材时继续检索后追问、工具失败后改查产品 ID、超时长后修改并复检，都能沿记录核对。

验收器重新计算时长与事实规则，并核对最终 `draft_id`、来源、镜头类型和起止时间。旧稿修订还要验证先检查的是原稿，后检查的是不同稿件。模型自己声称成功不能替代这些回执。

## 离线回归与复现

```shell
uv run --locked python -m unittest discover -s tests -v
```

不使用 uv 时，安装 `requirements.txt` 并激活 Python 环境，执行 `python -m unittest discover -s tests -v`。最新业务补强的 [145 项日志](../examples/strengthening-final-test-results.txt)保留；本次文档整理又核对两种运行入口，结果见[命令验证记录](../examples/documentation-command-checks.txt)。

测试覆盖输入类型与缺失字段，检索产品隔离，以及时长、事实和品牌检查。还覆盖未检查修改稿、伪造成功、篡改时间轴、临时错误、模型协议、澄清继续和次数上限。具体模块见[测试索引](../tests/README.md)。SDK 集成测试使用模拟 HTTP，不能算真实模型调用。

已有的离线证据包括[正常输入](../examples/normal.input.json)与[输出](../examples/normal.output.json)、[缺字段输入](../examples/missing.input.json)与[输出](../examples/missing.output.json)、[工具失败输入](../examples/tool-failure.input.json)与[输出](../examples/tool-failure.output.json)。[达到上限的记录](../examples/limit.output.json)验证十个工具轮次后返回未完成，[对应输入](../examples/normal.input.json)通过 `--offline-scenario limit` 运行。

## 失败与修复

| 发现的问题                     | 处理结果                                    | 保留的证据                                                                               |
| ------------------------------ | ------------------------------------------- | ---------------------------------------------------------------------------------------- |
| 3h 时格式修复触发 HTTP 400     | 修改反馈回合并重跑真实诊断和业务场景        | [冻结检查点](11-three-hour-checkpoint.md) / [接入修复](12-post-checkpoint-acceptance.md) |
| 验收器把合理停止判为失败       | 更正 1 秒上限等场景的判定边界，原始失败保留 | [阶段记录](12-post-checkpoint-acceptance.md)                                             |
| 速览初稿用了七个镜头，重复事实 | 调整提示和去重验收，新稿收敛为四镜头        | [初稿问题记录](../examples/live/20261029-strengthening/initial/style-teaser.review.json) |
| 教学特写未被验收器认可         | 接受两种实际界面展示，同批输出重新核对      | [判定更正](../examples/live/20261029-strengthening/assessment-review.json)               |

上述更正没有覆盖原始输出和失败记录，过程见[审核补强](13-review-strengthening.md)。

## 已知限制

十二场景的结论只适用于这批合成资料和本次运行。实际口播时长、长期服务稳定性、多样真实资料上的表现，以及独立人工评价的创意质量都未验证。这些结果不用于推算商业收益或普遍成功率。最终用时和未完成清单见[完成记录](14-final-completion.md)。
