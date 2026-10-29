# 测试与评估

## 当前结论

最新验收覆盖十二场景，其中十一条路径实际调用 DeepSeek `deepseek-flash`，一条为缺字段的本地校验。七个场景交付脚本，其余按预期追问或明确未完成。原始判定为 11/12；更正教学镜头判定后，对同一批输出复核为 12/12，原始结果未覆盖。完整记录见 [审核补强](13-review-strengthening.md)，此前九场景结果保留于 [3 小时之后的真实验收](12-post-checkpoint-acceptance.md)。

用户报告达到 3 小时的当时进度与未完成事项已保存为 [不可覆盖的快照](11-three-hour-checkpoint.md)。后续修复和验收不计入该时间点。

当前 145 项离线测试通过，最新命令与结果见 [补强测试记录](../examples/strengthening-final-test-results.txt)。此前的 [136 项截点后测试](../examples/post-checkpoint-test-results.txt)、[125 项接入准备](../examples/live-readiness-test-results.txt)、[113 项业务阶段](../examples/business-test-results.txt)和 [80 项通用能力](../examples/runtime-test-results.txt)保持各自的历史证据性质。离线测试不会调用真实服务，不能代替真实模型决策证据。

本轮新增真实证据为已有稿件在更短上限下从 14.2 秒压缩到 8.3 秒，保留两条产品事实；新手教学为 17.8 秒，熟练受众速览为 15.2 秒。速览初稿冗长的问题和教学验收误判均单独保留于补强记录。风格检查针对明确的结构偏好，不等于独立人工创意评分。

## 离线业务验收结果

以下命令均在项目根目录，以 `uv run --locked python -m src.main --mode offline` 开头。输出文件内同时包含实际 Trace、完整业务工具记录、候选草稿与最终检查结果。

| 场景         | 命令后缀                                                                         | 实际结果                                                          | 输入                                           | 输出与 Trace                                       |
| ------------ | -------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------- |
| 正常生成     | `--input examples/normal.input.json`                                             | 通过，18.4 秒，不超过 30 秒；4 次模型请求、3 次工具执行           | [输入](../examples/normal.input.json)          | [记录](../examples/normal.output.json)             |
| 缺关键信息   | `--input examples/missing.input.json`                                            | 请求补充 platform，0 次模型与工具调用                             | [输入](../examples/missing.input.json)         | [记录](../examples/missing.output.json)            |
| 无素材       | `--input examples/no-materials.input.json`                                       | 改用产品 ID 再检索，仍为空后请求补充                              | [输入](../examples/no-materials.input.json)    | [记录](../examples/no-materials.output.json)       |
| 工具失败     | `--input examples/tool-failure.input.json`                                       | 首次检索真实抛出模拟异常，观察错误后重试成功并交付                | [输入](../examples/tool-failure.input.json)    | [记录](../examples/tool-failure.output.json)       |
| 超时长后修正 | `--input examples/duration-repair.input.json --offline-scenario duration-repair` | 首稿 24.4 秒超出 10 秒；修改后 2.0 秒并重新检查通过               | [输入](../examples/duration-repair.input.json) | [记录](../examples/duration-repair.output.json)    |
| 品牌规则修正 | `--input examples/rules-repair.input.json --offline-scenario rules-repair`       | 首稿包含无依据的 80% 与保证表述，被拒绝后修改、重新估时和检查通过 | [输入](../examples/rules-repair.input.json)    | [记录](../examples/rules-repair.output.json)       |
| 无法满足时长 | `--input examples/unrepairable.input.json --offline-scenario unrepairable`       | 4.9 秒修订为 2.0 秒，仍超过 1 秒上限，明确未完成                  | [输入](../examples/unrepairable.input.json)    | [记录](../examples/unrepairable.output.json)       |
| 持续工具故障 | `--input examples/normal.input.json --offline-scenario persistent-failure`       | 两次检索故障后返回 tool_failure，保留错误记录                     | [输入](../examples/normal.input.json)          | [记录](../examples/persistent-failure.output.json) |
| 达到调用上限 | `--input examples/normal.input.json --offline-scenario limit`                    | 10 个工具轮次后停止，返回 incomplete                              | [输入](../examples/normal.input.json)          | [记录](../examples/limit.output.json)              |

`needs_input` 和 `incomplete` 是这些场景的预期结果，不计为成功交付脚本。测试日志中的工具失败日志来自故障注入，测试套件结果以记录末尾为准。超时长修订示例优先保留可验证的事实并压缩内容，不证明叙事质量或目标时长利用率最优。

## 边界与回归检查

- 每个必填字段缺失、空值、非法类型及额外字段都单独验证；布尔值和字符串数字不会冒充时长。
- 同一产品的中文查询、改写与 ID 查询，以及错误产品与无结果路径。
- 口播、字幕、停留与转场逐项计算，向上取整及边界通过条件。
- 伪造事实 ID、跨产品引用、未检索引用、引用未实际使用、无依据数字和保证表述。
- 标题、旁白和字幕分别检查，数值变造与小数点差异不能被规范化掩盖。
- 不同草稿标识、未检查修订稿、失败记录复用与草稿内容被修改时都拒绝交付。
- 模型最终声称成功但没有工具检查，运行时可以结束，业务状态必须仍为未完成。
- 替换素材原文后，生成内容与引用随之改变。
- 既有稿件仍须验证；首稿直接通过、虚构原稿超限、篡改镜头和起止时间均不能被记为有效修订证据。
- 六种镜头保持同一事实规则，累计转场取整后时间轴末端与总时长一致；教学展示与速览去重有独立回归检查。
- 真实 SDK 加模拟 HTTP 驱动完整业务工具链，验证超时长后再次提交草稿。
- 真实 CLI 覆盖退出码、交互回答、错误路径不泄露本机路径，以及真实模式不会静默切换到 Mock。

## 通用运行时记录

此前的 [正常运行](../examples/runtime-normal.output.json)、[工具恢复](../examples/runtime-tool-failure.output.json)、[上限停止](../examples/runtime-limit.output.json)和[通用能力串联](../examples/runtime-capabilities.output.json)仍可单独复现，见 [Agent 能力](08-runtime-capabilities.md)。这些记录不替代本页的业务验收。

## 尚未验证

实际口播时长、长期服务稳定性、多样真实素材上的泛化能力，以及独立人工评价的受众、风格和创意质量仍未验证。本轮对合成样例做了主题与来源一致性核对，不能由此推断商业效果。原始失败与真实复验均保留，不把离线替身记录改称为真实结果。
