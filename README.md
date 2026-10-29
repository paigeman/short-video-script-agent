# Short Video Script Agent

项目选择第 4 题「短视频脚本 Agent」，用 CLI 接收创作要求，由模型调用素材检索、时长估算和规则检查工具，交付有来源依据的脚本。模型根据工具结果决定继续检索、修改稿件、请求补充信息或停止。

本次总用时登记为 **3h55min**。3h 时的进度保存在[不可覆盖的检查点](docs/11-three-hour-checkpoint.md)，最终完成情况和未完成项另见[最终记录](docs/14-final-completion.md)。仓库公开，交付地址为 [paigeman/short-video-script-agent](https://github.com/paigeman/short-video-script-agent)。

当前有 145 项离线测试，以及十二场景的真实接入验收记录。其中十一条路径实际调用模型，缺字段在本地处理。原始判定为 11/12，更正教学镜头的判定后，同批输出复核为 12/12。具体预期、失败和证据集中在[评估文档](docs/03-evaluation.md)。

## 环境与安装

需要 Python 3.13 或更高版本。运行程序和 Python 测试均不需要 Node.js；只有格式化与 lint 使用 Node.js 和 npm。以下命令按 macOS 或 Linux 的 Bash、Zsh 编写，均在仓库根目录执行。

```shell
git clone https://github.com/paigeman/short-video-script-agent.git
cd short-video-script-agent
```

开发环境使用 uv，依赖版本锁定在 `uv.lock`。安装命令为

```shell
uv sync --locked
```

没有 uv 时，可以用 Python 自带的 venv 和 pip。先确认 `python3 --version` 至少为 3.13，再执行

```shell
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` 由锁文件导出，包含固定版本的运行依赖，也足够执行 Python 测试。它不包含 Ruff 等开发工具。在 Windows PowerShell 中，创建环境可用 `py -3.13 -m venv .venv`，激活命令为 `.venv\Scripts\Activate.ps1`，之后同样使用 `python -m pip` 和 `python -m src.main`。

## 不用密钥的离线运行

用 uv 运行正常、缺字段和工具故障场景

```shell
uv run --locked python -m src.main --mode offline --input examples/normal.input.json
uv run --locked python -m src.main --mode offline --input examples/missing.input.json
uv run --locked python -m src.main --mode offline --input examples/tool-failure.input.json
```

不使用 uv 时，激活前面建立的环境，执行等价命令

```shell
python -m src.main --mode offline --input examples/normal.input.json
python -m src.main --mode offline --input examples/missing.input.json
python -m src.main --mode offline --input examples/tool-failure.input.json
```

输出是 JSON，包含状态、脚本、检查记录和 Trace。缺字段场景返回 `needs_input`，退出码为 3，属于预期行为。离线入口使用明确标记的确定性模型替身，只验证本地流程，真实模型的决策证据另存于 `examples/live/`。

离线复现超时长后的修改，增加场景参数即可

```shell
uv run --locked python -m src.main --mode offline --input examples/duration-repair.input.json --offline-scenario duration-repair
```

无 uv 时去掉命令开头的 `uv run --locked`。该场景由替身触发，不计入真实模型修订结果。

## 真实模型运行

真实验收使用 DeepSeek V4.1 Flash，服务接收的模型 ID 为 `deepseek-flash`。公开配置模板是 [.env.example](.env.example)，包含模型、服务地址、推理强度和超时设置，密钥留空。首次配置时复制模板并在本机填写 `API_KEY`，已有 `.env` 不要覆盖。

```shell
cp -n .env.example .env
```

用 uv 显式加载 `.env`，先检查配置，再调用真实模型

```shell
uv run --locked --env-file .env python -m src.config
uv run --locked --env-file .env python -m src.main --mode live --input examples/normal.input.json
```

不使用 uv 时，在已激活的环境中加载自己填写的 `.env`。模板中的变量带有 `export`，Bash、Zsh 可直接执行

```shell
. ./.env
python -m src.config
python -m src.main --mode live --input examples/normal.input.json
```

PowerShell 需将同一组变量配置到进程环境，例如通过 `$env:MODEL` 和 `$env:API_KEY` 设置，不能直接执行上述 shell 模板。Python 程序本身不会自动读取 `.env`，也没有安装 dotenv。配置检查不发起请求；live 命令会调用服务并产生用量。配置错误时程序明确失败，不会自动转为离线模式。

| 输入文件                                               | 用途                               |
| ------------------------------------------------------ | ---------------------------------- |
| [normal](examples/normal.input.json)                   | 从素材生成脚本                     |
| [revise-existing](examples/revise-existing.input.json) | 将已有 14.2 秒稿件压缩到 10 秒上限 |
| [style-tutorial](examples/style-tutorial.input.json)   | 面向新手组织步骤、演示和回顾       |
| [style-teaser](examples/style-teaser.input.json)       | 面向熟练创作者生成简短功能速览     |

更换 `--input` 即可运行这些请求。完整十二场景验收使用独立入口，输出目录必须尚不存在

```shell
uv run --locked --env-file .env python -m scripts.live_acceptance --output-dir .agent-tmp/my-live-acceptance
```

无 uv 时，先加载环境变量，再执行 `python -m scripts.live_acceptance --output-dir .agent-tmp/my-live-acceptance`。可用重复的 `--case` 参数选择场景。验收快照包含请求、资料和规则，不能直接把它作为普通 CLI 输入。参数说明见[真实验收指南](docs/10-live-validation.md)。

## 输入、输出与限制

输入必填 `topic`、`audience`、`platform`、`duration_seconds`、`style`、`product_id`。时长是 1 至 300 的整数秒上限，`product_id` 用于隔离产品素材。可选 `initial_draft` 接收已有稿件，原稿仍需检索依据和重新检查。

交付包含标题、分镜、旁白与字幕，各镜头有估计时长和起止时间，并附素材 ID、事实原文、风险及最终检查结果。只有同一 `draft_id` 的时长与规则检查都实际通过，业务状态才为 `completed`。

`--materials`、`--rules` 可替换合成资料和品牌规则；`--interactive` 允许模型追问后从终端接收回答。缺少必填字段时，应先补齐输入文件。真实模式不接受输入中的 `simulate_tool_failure` 开关，真实故障验收由独立验收脚本明确注入。

| 退出码 | 含义                   |
| ------ | ---------------------- |
| 0      | 业务检查通过           |
| 3      | 等待补充信息           |
| 2      | 输入或配置错误         |
| 1      | 未完成、模型错误或取消 |

产品文案限于素材原文与获准过渡语，便于逐项核对来源。六种镜头提供编辑示意，估时综合口播、字幕、停留和转场。自由改写、实际配音时长及独立人工创意评价仍有缺口，详见[最终记录](docs/14-final-completion.md)。

## 测试与质量检查

Python 测试全部离线，不需要真实密钥

```shell
uv run --locked python -m unittest discover -s tests -v
```

不使用 uv 时执行

```shell
python -m unittest discover -s tests -v
```

两种入口的实际运行检查保存在[命令验证记录](examples/documentation-command-checks.txt)。Python 直接运行复用了已安装依赖的项目环境，该记录没有宣称重新安装过一套干净的 pip 环境。

开发质量工具另需 Node.js `^22.22.0` 或 `>=24.8.0` 以及 npm，仓库的统一检查命令依赖 uv

```shell
npm ci --ignore-scripts
uv sync --locked
npm run check
npm test
```

没有 uv 时仍可运行前面的业务和 Python 测试。格式化与 lint 的工具职责、按文件执行方法见[开发指南](docs/06-development.md)。冻结快照不参与写入式格式化。

## 评审入口

| 检查内容                       | 入口                                                                                                  |
| ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| 服务对象、目标与成功标准       | [01 需求](docs/01-requirements.md)                                                                    |
| ReAct 决策、调用流程与技术取舍 | [02 方案](docs/02-solution.md)                                                                        |
| 预期、实测、失败与原始 Trace   | [03 评估](docs/03-evaluation.md)                                                                      |
| 个人贡献与 AI 辅助范围         | [04 AI 使用](docs/04-ai-usage.md)                                                                     |
| 最难的问题、学习与下一步       | [05 复盘](docs/05-retrospective.md)                                                                   |
| 复用代码的远程来源和文件映射   | [迁移说明](docs/07-migration.md)                                                                      |
| 运行限制与业务检查细节         | [运行时](docs/08-runtime-capabilities.md) / [业务规则](docs/09-business-rules.md)                     |
| 3h 当时的进度与未完成项        | [冻结检查点](docs/11-three-hour-checkpoint.md)                                                        |
| 截点后的两阶段验收             | [接入修复](docs/12-post-checkpoint-acceptance.md) / [压缩与风格补强](docs/13-review-strengthening.md) |
| 3h55min 的最终状态与交付核对   | [最终完成记录](docs/14-final-completion.md)                                                           |

实现与测试分别位于 `src/` 和 `tests/`，合成资料使用 `data/`，运行证据集中在 `examples/`。目录结构参考[示例仓库](https://github.com/lwz1357/agent-campus-submission-example)，选题编号按当前试卷记为第 4 题。代码复用来源及 AI 协作方式单独披露。

交卷时填写第 4 题、上述公开仓库 URL 和最终 commit SHA。在最终版本根目录执行 `git rev-parse HEAD` 获取完整 SHA，提交后不再修改该版本。仓库记录与考试平台交卷是两个步骤，本文没有表示已经交卷。
