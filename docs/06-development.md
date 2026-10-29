# 开发与质量检查

## 工具选择

质量体系参考 [FadeDemo/AI-demo](https://github.com/FadeDemo/AI-demo) 的仓库级 Prettier、markdownlint-cli2 和 Python 项目的 Ruff 配置。

| 范围       | 格式化      | Lint 或内容校验                         |
| ---------- | ----------- | --------------------------------------- |
| Python     | Ruff format | Ruff check                              |
| Markdown   | Prettier    | markdownlint-cli2                       |
| JSON       | Prettier    | Python 标准库解析、重复键与非有限数检查 |
| JSONC 配置 | Prettier    | markdownlint-cli2 加载配置时校验        |

Node.js 仅用于开发质量工具；基础运行时依赖 OpenAI SDK、HTTPX 和 jsonschema。Python 开发环境由 `uv` 管理，不依赖其他仓库中的虚拟环境或全局 Ruff。

## 安装

需要 Python 3.13+、`uv`，以及满足 `package.json` 中版本范围的 Node.js 和 npm。

```shell
npm ci --ignore-scripts
uv sync --locked
```

`npm ci` 使用 `package-lock.json` 创建项目内的 `node_modules/`。`uv sync` 使用 `uv.lock` 创建项目内的 `.venv/` 并安装开发依赖。当前锁定 Prettier 3.9.5、markdownlint-cli2 0.23.2 和 Ruff 0.16.1；依赖更新应同时提交声明与锁文件。

## 常用命令

```shell
# 全仓格式化；仅用于没有冻结记录且全部文件属于修改范围的情况
npm run format

# 只检查格式
npm run format:check

# 分别进行 Markdown、Python 和 JSON 检查
npm run lint

# 一次完成格式检查和 lint，不自动修改源文件
npm run check

# 按需自动修复 Python lint 问题，执行后检查 diff
npm run lint:python:fix
```

本仓库已有冻结记录，提交前应仅格式化当前修改文件，再执行只读的 `npm run check`，随后检查并暂存自动修改。不要对 `docs/11-three-hour-checkpoint.md` 或 `examples/checkpoints/three-hour/` 执行写入式格式化。按文件运行示例：

```shell
npm exec -- prettier --write README.md
npm exec -- markdownlint-cli2 README.md
uv run --locked ruff format src/main.py
uv run --locked ruff check src/main.py
```

## 规则与配置

- `.editorconfig`：UTF-8、LF、文件末尾换行和空格缩进；Python 使用四个空格，其他文件默认两个空格。
- `.prettierrc.json`：沿用 100 列配置，保留中文段落现有换行，使用 LF。
- `.markdownlint-cli2.jsonc`：开启默认规则，关闭中文不适用的固定行长检查；同级标题不能重复，使用围栏代码块和星号强调。
- `pyproject.toml`：Ruff 以 Python 3.13 为目标，88 列、双引号，开启基础错误、导入排序、常见缺陷、现代语法、简化与 Ruff 规则。注释和文档字符串中的正常中文标点排除 `RUF002`、`RUF003`。
- `scripts/check_json.py`：校验根目录 JSON 配置及 `data/`、`examples/` 下的 JSON，拒绝重复键与 `NaN`、`Infinity` 等非法 JSON 常量；不替代业务 Schema 验证。
- 忽略虚拟环境、依赖、缓存、构建产物和 `.agent-tmp/`，避免质量检查扫描生成文件。

基础运行时与短视频业务测试均可通过 `npm test` 执行，真实模型验收另行记录。质量检查通过只表明格式、静态规则和 JSON 有效性满足配置要求。业务验收仍按 [评估](03-evaluation.md) 单独执行。
