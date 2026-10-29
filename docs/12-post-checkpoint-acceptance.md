# 3 小时之后的真实模型验收

本页记录用户要求继续执行的后续工作，不计入 3 小时内完成情况。[3 小时快照](11-three-hour-checkpoint.md)及其原始证据已经单独提交为 `3d4f6dd`，保持不变。

## 验收结论

2026-10-29 17:02:53–17:03:58（Asia/Shanghai）执行最终一轮验收，九个场景均符合预期。其中八个场景实际调用 DeepSeek `deepseek-flash`，缺字段场景在本地停止。四个场景交付脚本，两个请求补充信息，三个明确未完成；“通过验收”不等于所有请求都成功生成脚本。

本轮共 30 次模型请求、31 次本地业务工具执行，服务返回的合计用量为 91,761 Token，所有运行的用量信息均完整。该数字只对应本轮，不包含基线、失败尝试和诊断请求，不能当作整个项目的总成本。输出上限 8192、推理强度 high、单请求超时 120 秒、整轮上限 600 秒；业务请求使用 JSON object 输出模式。

完整 [执行清单](../examples/live/20261029-post-checkpoint/manifest.json)记录实际时间、配置和源文件 SHA-256。`base_commit` 是运行时的已提交基线，`files_sha256` 标识其上的实际执行代码；不得将基线 commit 误当成全部修复已在该版本中。每个输入快照同时保存请求、资料、品牌规则和故障计划。没有导出密钥、服务认证信息或提供方内部推理文本。

## 题目要求与实际结果

下表每个输出均包含原始 Trace、完整工具记录、候选草稿和最终状态。模型自主选择动作；故障用例只对本地检索工具注入异常，没有预设模型回复或分支。

| 场景         | 输入快照                                                                        | 输出与 Trace                                                                     | 实际结果                                                                 |
| ------------ | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 正常生成     | [输入](../examples/live/20261029-post-checkpoint/normal.input.json)             | [记录](../examples/live/20261029-post-checkpoint/normal.output.json)             | 两次检索、估时和规则检查后交付 14.2 秒脚本，上限 30 秒                   |
| 缺关键信息   | [输入](../examples/live/20261029-post-checkpoint/missing.input.json)            | [记录](../examples/live/20261029-post-checkpoint/missing.output.json)            | 请求补充 platform，零次模型调用                                          |
| 无素材       | [输入](../examples/live/20261029-post-checkpoint/no-materials.input.json)       | [记录](../examples/live/20261029-post-checkpoint/no-materials.output.json)       | 改写检索仍无结果，返回 no_materials                                      |
| 缩短目标时长 | [输入](../examples/live/20261029-post-checkpoint/short-duration.input.json)     | [记录](../examples/live/20261029-post-checkpoint/short-duration.output.json)     | 改变分镜停留，交付 9.4 秒脚本，上限 10 秒                                |
| 无法满足时长 | [输入](../examples/live/20261029-post-checkpoint/unrepairable.input.json)       | [记录](../examples/live/20261029-post-checkpoint/unrepairable.output.json)       | 实测最简候选 2.0 秒超过 1 秒，返回 cannot_meet_constraints               |
| 无依据的 80% | [输入](../examples/live/20261029-post-checkpoint/unsupported-claim.input.json)  | [记录](../examples/live/20261029-post-checkpoint/unsupported-claim.output.json)  | 明确缺少效果数据，询问是否移除主张，没有交付虚假文案                     |
| 一次工具故障 | [输入](../examples/live/20261029-post-checkpoint/tool-failure.input.json)       | [记录](../examples/live/20261029-post-checkpoint/tool-failure.output.json)       | 首次检索异常，模型重试恢复，交付 26.7 秒脚本                             |
| 持续工具故障 | [输入](../examples/live/20261029-post-checkpoint/persistent-failure.input.json) | [记录](../examples/live/20261029-post-checkpoint/persistent-failure.output.json) | 四次检索异常后返回 tool_failure，未伪造检查成功                          |
| 替换素材     | [输入](../examples/live/20261029-post-checkpoint/changed-materials.input.json)  | [记录](../examples/live/20261029-post-checkpoint/changed-materials.output.json)  | 只改变素材为“支持调整字幕显示位置”，交付 10.8 秒脚本，正文和来源同步变化 |

已覆盖正常、缺输入、无素材、工具失败、超时长明确停止等必验场景，提供超过两条真实模型路径与三组输入/输出/Trace。10 秒用例首稿已经合规，不能把它描述成超时长后修订；真实规则修订证据保留在 [3 小时正常运行](../examples/checkpoints/three-hour/normal.output.json)中。

## 真实发现与修复

1. **最终格式修复触发 HTTP 400。** 截点时，10 秒草稿已通过工具检查，但最终答案带 Markdown。修复提示以 system 消息接在已完成的工具回合之后，服务在部分返回结构下要求继续提供 `reasoning_text`，导致 400。保留的[错误诊断](../examples/live/20261029-post-checkpoint/repair-error-detail.json)记录了服务返回的错误句，已移除请求标识。
2. **修复回合边界并约束输出。** 格式修复改用新的 user 回合，保留原有提供方上下文；业务入口同时启用 `text.format=json_object`，仍使用本地 Schema 和业务最终检查。关闭 JSON 模式、刻意触发一次格式修复的[独立真实诊断](../examples/live/20261029-post-checkpoint/repair-fix-diagnostic.json)也成功完成。这类明确注入的诊断不计为业务路径。JSON 模式支持情况见 [DeepSeek 官方文档](https://api-docs.deepseek.com/guides/responses_api/)。
3. **验收器误把合理停止判失败。** 1 秒用例不再被要求必须先生成超时长草稿，明确无法满足也是题目允许的结果；完整最终轮仍实际观察到 2.0 秒超限。原来的资料替换用例把编辑换为导出，模型请求澄清合理；新增与编辑主题兼容的替换资料验证正文确实随数据变化。原失败和原输入保留在冻结目录。
4. **补全可复现的故障验收。** 新增独立验收脚本和宿主端故障计划，故障次数与作用范围写入结果。普通业务输入不能开启真实故障注入。验收器重算时长和规则，核对最终草稿、来源、分镜与实际工具回执，并修复资料替换后失效引用导致的检查器异常。

本轮未新增依赖，也未迁移本地 Token 预算器或 DeepSeek prompt encoder。

## 回归与人工核对边界

`npm test` 的 136 项离线测试全部通过，实际日志见 [截点后测试记录](../examples/post-checkpoint-test-results.txt)。新增覆盖故障计划权限与参数、缺失或被篡改的验收回执、资料变更后的旧引用、JSON 输出参数和工具回合结束后的格式修复。

对本轮已交付脚本逐项复核了主题与所用事实、旁白/字幕、分镜时间与转场之和、来源原文和最终检查一致性。正常与缩短时长的输出不同，替换资料后的输出不再使用旧事实。这是 Codex 对合成场景的内容核对，没有冒充考生本人或外部评审的打分。

仍有明确限制：文案采用原文与获准过渡语，正常 30 秒上限用例只用了 14.2 秒，叙事、受众和风格优化有限；三种镜头类型只是可编辑示意。估时未经实际配音校准；一次完整验收不代表长期稳定性、通用文案质量或商业收益。个人贡献与实际用时仍需考生据实填写，最终考试提交由考生完成。
