# 测试与评估

## 当前结论

业务实现已完成离线验收。本轮使用确定性模型替身、真实本地工具和模拟 HTTP，没有读取真实模型密钥或执行真实生成请求。离线结果验证业务规则与执行机制，不能证明真实模型决策、文案质量或商业效果。

当前测试套件共 113 项，其中原通用运行时 80 项、业务相关 33 项。最终实际命令与结果见 [业务阶段测试记录](../examples/business-test-results.txt)。原通用能力阶段的 [80 项测试记录](../examples/runtime-test-results.txt)作为阶段记录保留。

## 业务验收结果

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
- 真实 SDK 加模拟 HTTP 驱动完整业务工具链，验证超时长后再次提交草稿。
- 真实 CLI 覆盖退出码、交互回答、错误路径不泄露本机路径，以及真实模式不会静默切换到 Mock。

## 通用运行时记录

此前的 [正常运行](../examples/runtime-normal.output.json)、[工具恢复](../examples/runtime-tool-failure.output.json)、[上限停止](../examples/runtime-limit.output.json)和[通用能力串联](../examples/runtime-capabilities.output.json)仍可单独复现，见 [Agent 能力](08-runtime-capabilities.md)。这些记录不替代本页的业务验收。

## 尚未验证

至少两条真实模型执行路径、所选服务兼容性、实际口播时长，以及创意、主题和风格适配均未验收。后续应使用真实模型分别运行正常与修订路径，保留模型标识、配置、观察结果和实际动作，不把离线替身记录改称为真实模型结果。
