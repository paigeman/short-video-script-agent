# 示例输入与运行证据

| 输入                      | 计划用途                 | 当前情况                |
| ------------------------- | ------------------------ | ----------------------- |
| `normal.input.json`       | 正常脚本生成             | 仅用于验证 CLI 输入读取 |
| `missing.input.json`      | 缺少平台信息时请求补充   | 业务处理尚未实现        |
| `tool-failure.input.json` | 素材工具失败时的动态处理 | 模拟失败开关尚未实现    |

实现后，还需要补充无素材、超时长修改及执行上限等场景，见 [评估计划](../docs/03-evaluation.md)。

每组实际运行证据采用相同文件前缀，例如 `normal.input.json`、`normal.output.json` 和 `normal.trace.json`。记录模型标识、运行模式、工具参数、返回摘要、后续动作与简要依据；不要记录密钥或模型内部思维过程。

测试命令与实际输出可保存在 `test-results.txt`。当前尚未生成短视频业务输出与真实模型 Trace，后续应从实际执行结果保存，不能手写成成功样例。

## 已生成的运行时证据

- [正常执行](runtime-normal.output.json)：离线模型替身调用本地工具后结束。
- [工具失败后继续执行](runtime-tool-failure.output.json)：观察错误结果后再次调用。
- [达到执行上限](runtime-limit.output.json)：保留已有结果并明确返回未完成。
- [通用能力串联](runtime-capabilities.output.json)：提问、合成回答、继续执行、输出修复和模型错误重试。
- [实际测试结果](runtime-test-results.txt)：80 项离线测试的完整执行记录。

生成命令及结果解释见 [评估](../docs/03-evaluation.md)。这些是基础运行时演示，与上表的短视频业务输入分别记录。
