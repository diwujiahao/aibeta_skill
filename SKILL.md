---
name: "ai_beta_skill"
description: "面向 A 股板块级投研数据的查询与分析技能，数据统一来自 aibeta SDK，提供 CLI 快速查数、图表绘制（plot-series 时序折线图、plot-bar 截面柱状图、plot-scatter 双指标截面散点图，直接输出 PNG/SVG）与 Python SDK 深度分析三种方式。能力覆盖：1) 板块指标库——为 ETF 指数、中信证券行业（聚合及一/二/三级细分行业）、主题概念等六类板块类型提供多维指标：宏观敏感度、景气度、财务（净利润TTM、ROE 等）、估值（市盈率PE、市净率PB、市销率PS、股债相对盈利收益率）、市场参与者预期（一致预测）、资金面（融资融券、ETF资金）、技术面（均线、MACD、RSI、涨跌幅、成交量、交易拥挤度/热度），支持单板块指标历史时序查询、多板块横向截面比较、批量时序拉取与图表绘制；2) 主题分类库——主题库框架、主题成分股（标准池）、主题历史指数点位；3) 文本库——市场日报与策略周报 AI 文本检索（查询某日市场热点、最新策略观点）。当用户需要板块/主题层面的指标数值、历史趋势、趋势图表、跨板块对比、截面比较图、指标相关性、主题体系/成分股/主题指数数据或日报周报文本，或要基于这些数据构建分析脚本时调用本技能；不适用于个股级行情与财务数据查询。"
metadata:
  version: "7.1.0"
  author: "伍老师"
---

# ai_beta_skill

A 股板块级投研数据的查询与分析技能，数据统一来自 aibeta SDK。本文是技能入口：提供功能概览、快速开始、CLI 命令速查与典型查询路径；命令与 SDK 的详细用法见 `references/` 下两本使用手册（阅读路径见下文）。

## 功能概览

- **板块指标库**：为六类板块类型——ETF指数、中信证券行业（聚合口径，行业代码 2/4/6 位对应一/二/三级）、中信证券一级行业、中信证券二级行业、中信证券三级行业、主题概念——提供多维指标：
  - 宏观敏感度 / 景气度 / 财务（净利润TTM、ROE 等）/ 估值（市盈率PE、市净率PB、市销率PS、股债相对盈利收益率）/ 市场参与者预期（一致预测）/ 资金面（融资融券、ETF资金）/ 技术面（均线、MACD、RSI、涨跌幅、成交量、交易拥挤度/热度）
  - 支持单板块指标历史时序查询、多板块横向截面比较、批量时序拉取与图表绘制
- **主题分类库**：主题库框架、主题成分股（标准池）、主题历史指数点位
- **文本库**：市场日报与策略周报 AI 文本（查询某日市场热点、最新策略观点）

## When to Use

- 板块指标库
  - 查询某个板块或指数在某个指标的数值，或分析其历史数值与变化趋势
  - 围绕某个维度或具体指标，对多个板块做横向比较
  - 批量拉取板块指标时序数据，用于跟踪、筛选或对比
  - 基于 beta 指标库构建投资辅助脚本、分析流程或轻量工具
- 文本库
  - 读取市场日报或策略周报的 AI 文本内容
  - 查询某天市场热点，或某个时点（周日）的 A 股市场策略观点
- 主题分类库
  - 查询主题分类体系：主题库框架、包含哪些主题、主题成分股（标准池）、特定主题的历史指数点位

## 使用方式与阅读路径

| 方式 | 适用场景 | 说明 |
| --- | --- | --- |
| 统一 CLI `ai-beta`（推荐默认） | 快速查数 | 返回 JSON，适合直接看数 / 落盘 |
| `plot-*` 绘图命令 | 看趋势 / 做比较 / 看相关性 | 免写代码，直接输出 PNG/SVG 图表文件 |
| Python SDK `aibeta` | 深度分析取数 | 返回 `pandas.DataFrame`，适合后续计算、可视化、建模 |

阅读路径：先由本文「CLI 命令速查」对号入座选命令；**命令参数明细、返回字段、行为约定与排障**见 `references/CLI_使用手册.md`；**SDK 安装、凭证、全部函数签名与返回样例**见 `references/PythonSDK_使用手册.md`。

## 快速开始（首次使用）

本 SKILL 目录视为**只读分发物**：安装与运行均不修改其中文件；CLI 从随附源码（`scripts/` 目录）一次性安装为独立工具，此后与 Skill 目录完全解耦。

1. **确认 `uv` 已安装**：`uv --version`；未安装时先安装（`curl -LsSf https://astral.sh/uv/install.sh | sh`）
2. **一次性申请权限**：执行任何命令前，向用户一次性说明并申请本 SKILL 需要的全部系统权限，不要等具体命令失败后再逐项追加——
   - 网络：安装期下载 CLI 依赖与构建后端（aibeta、pandas、pyarrow、matplotlib 等；本机 uv 缓存已有依赖时免联网）；运行期 SDK 拉取数据（缓存过期时，默认每 3 天一次）
   - 写 uv 目录：工具目录（默认 `~/.local/share/uv/tools/`）、bin 目录（默认 `~/.local/bin/`）、下载缓存（默认 `~/.cache/uv`）
   - 写 SDK 缓存目录：默认 `~/.cache/aibeta/`
3. **检查已装 CLI 版本、不一致时重新构建安装并运行启动前自检**（合并为一次执行，权限审批一轮完成；`<skill 绝对路径>` 替换为本 SKILL 的实际安装路径）：

   ```bash
   V=$(grep -m1 '^version' "<skill 绝对路径>/scripts/pyproject.toml" | cut -d'"' -f2)   # 取版本：全项目唯一版本源是 scripts/pyproject.toml 的 version
   uv tool list | grep -q "beta-indicator-scripts v$V" || uv tool install --force "<skill 绝对路径>/scripts"   # 版本检查：未安装或与 $V 不一致时，加 --force 从 scripts/ 源码重新构建安装
   ai-beta doctor
   command -v ai-beta   # 验证：应输出可执行文件路径
   ai-beta --help       # 验证：应输出命令帮助
   ```

   **版本一致性是首次使用的必要检查**：全项目唯一版本源是 `scripts/pyproject.toml` 的 `version`（发版只改这一处）；安装源是本地目录，uv 不跟踪其内容变化，机器上可能残留旧版 CLI，已装 `beta-indicator-scripts` 的版本与 `$V` 不一致（含未安装）时不得直接使用，必须按上式加 `--force` 覆盖并重新构建安装（安装验证与升级明细见 `references/CLI_使用手册.md` 第 2.4 节）。`ai-beta doctor` 在同一次执行内验证缓存目录可写与网络连通，并提示凭证配置状态；存在 `[FAIL]` 时按报告指引修复后重跑（明细见 `references/CLI_使用手册.md` 第 2 节）

4. **配置凭证环境变量**（凭证需向用户获取；两者都未配置时 SDK 直接报凭证缺失错误）：

   ```bash
   export BETA_INDICATOR_API_APP_KEY="XXX"
   export BETA_INDICATOR_API_SECRET_KEY="XXX"
   ```

5. **SDK 缓存目录重定向（可选）**：`~/.cache` 不可写或需目录隔离时 `export AIBETA_CACHE_DIR="/path/to/dir"`（支持 `~` 与 `$VAR` 展开，需保证每次执行 `ai-beta` 时该变量可见）。仅 Python 脚本可用进程内配置替代环境变量：`aibeta.configuration(app_key=..., secret_key=...)`（**CLI 只支持环境变量方式**）。

受限环境（默认位置不可写）的完整重定向方式、安装验证与升级，见 `references/CLI_使用手册.md` 第 2 节。

## CLI 命令速查

统一入口 `ai-beta`（安装后从任意目录直接调用；不确定子命令名时先执行 `ai-beta --help`）。通用约定：

- 结果 JSON 输出 `stdout`，错误 / 提示 / 规模统计输出 `stderr`；每个子命令均支持 `--compact`（写在子命令之后）输出无缩进单行 JSON，适合 `> result.json` 落盘
- 退出码：`0` 成功（含空结果 `[]`）、`1` 运行失败、`2` 用法错误
- 所有日期入参严格 `YYYY-MM-DD`（`20260901`、`2026/12/31` 直接报错）；字符串入参自动去除首尾空白
- 时序命令支持时间窗口 `--last-n` / `--start-date` / `--end-date`，未传任何窗口参数时默认保留最后 25 条

完整参数、返回字段与行为约定见 `references/CLI_使用手册.md` 第 3、4 节。

### 板块指标库

| 命令 | 功能 | 关键参数 |
| --- | --- | --- |
| `list-indicator-types` | 查询所有指标类型 | 无 |
| `list-indicators` | 按指标类型查指标列表（约 2 千行/类型，建议先过滤） | 【必填】`--indicator-type`；【可选】`--sector-type`、`--keyword` |
| `get-indicator-value` | 查单个指标的时序数据 | 【必填】`--indicator-id`；【可选】时间窗口 |
| `get-indicator-value-batch` | 批量时序查询（最多 30 个，固定并发 3） | 【必填】`--indicator-id`（可重复）；【可选】时间窗口 |
| `list-sector-types` | 查询所有板块类型（共 6 类） | 无 |
| `list-sectors` | 查板块列表（无过滤约 2.3 千行） | 【可选】`--sector-type`（支持全部 6 类）、`--sector-code`、`--sector-name`、`--keyword` |
| `list-indicators-by-sector` | 按板块代码查该板块全部指标 | 【必填】`--sector-code` |
| `get-indicator-value-latest-by-type-and-sector` | 全板块最新一期截面（跨板块比较，免找 ID；主题概念下约 1.5 千行） | 【必填】`--indicator-type`、`--sector-type`（支持全部 6 类） |

### 主题分类

| 命令 | 功能 | 关键参数 |
| --- | --- | --- |
| `get-theme-framework-daily` | 主题库日度截面（层级框架，取 `theme_id`；约 0.9 千行） | 【必填】`--view-date` |
| `get-theme-index` | 特定主题的历史指数点位 | 【必填】`--theme-id`；【可选】时间窗口 |

### 文本库

| 命令 | 功能 | 关键参数 |
| --- | --- | --- |
| `get-market-daily-report` | 市场日报 AI 文本（按 `view_date` 降序，默认最新 1 期） | 【可选】`--last-n`；`--start-date` + `--end-date`（必须成对） |
| `get-strategy-weekly-report` | 策略周报 AI 文本（规则同市场日报） | 同上 |

### 绘图（图表落盘 PNG/SVG 文件，stdout 输出摘要 JSON）

| 命令 | 功能 | 关键参数 |
| --- | --- | --- |
| `plot-series` | 单指标 / 主题指数时序折线图（默认叠加 MA20/MA60 并标注最新值） | 【二选一】`--indicator-id` / `--theme-id`；【可选】`--indicator-type`（自动图题）、`--ma`、`--no-ma`、`--no-annotate`、`--title`、`--output`/`--format`、时间窗口 |
| `plot-bar` | 单指标多板块最新截面柱状图（标的数 >30 时两端各取 15） | 【必填】`--indicator-type`、`--sector-type`；【可选】`--sort`、`--title`、`--output`/`--format` |
| `plot-scatter` | 双指标截面散点图（同频率校验、按板块对齐且须同一数据日期、MAD 离群点剔除） | 【必填】`--indicator-type`（恰好 2 次：x、y 轴）、`--sector-type`；【可选】`--annotate`、`--skip-frequency-check`、`--title`、`--output`/`--format` |

`--sector-type` 的取值全集共 6 个：ETF指数 / 中信证券行业 / 中信证券一级行业 / 中信证券二级行业 / 中信证券三级行业 / 主题概念（即 `list-sector-types` 的返回全集），适用于 `list-sectors`、`get-indicator-value-latest-by-type-and-sector` 与 `plot-bar` / `plot-scatter`；例外：`list-indicators --sector-type` 按返回记录的 `sector_type` 列精确匹配（板块家族口径，不含中信细分层级）。

### 自检

| 命令 | 功能 | 关键参数 |
| --- | --- | --- |
| `doctor` | 启动前自检：缓存目录可写、网络连通、凭证配置提示 | 无 |

## 典型查询路径

不知道从哪个命令开始时，按目标对号入座：

- **查某板块某个指标的数值**：`list-indicator-types`（确认 `--indicator-type` 取值）→ `list-indicators`（`--keyword` 定位板块，取 `indicator_id`）→ `get-indicator-value --indicator-id ... --last-n ...`
- **多板块横向比较某个指标**：`get-indicator-value-latest-by-type-and-sector`（免找 `indicator_id`，直接取全市场最新截面）；图形化比较用 `plot-bar`
- **看两个指标的相关性**：`plot-scatter --indicator-type A --indicator-type B --sector-type ...`（两指标需同频率）
- **查板块代码 / 名称**：`list-sectors --keyword ...`（取 `sector_code`）；可继续用 `list-indicators-by-sector` 看该板块有哪些指标
- **查主题框架 / 主题指数 / 主题成分股**：`get-theme-framework-daily --view-date ...`（取 `theme_id`）→ `get-theme-index --theme-id ...`；成分股明细无 CLI 命令，需 Python 调 SDK（见 Notes）
- **读报告文本**：`get-market-daily-report` / `get-strategy-weekly-report`（默认最新 1 期，`--last-n N` 取最新 N 期）

端到端示例（查上证综合指数最近一年的市盈率PE；周频指标 `--last-n 52` ≈ 一年）：

```bash
ai-beta list-indicators --indicator-type "市盈率PE" --sector-type "ETF指数" --keyword "上证综合"
# 从返回中找到 sector_name 为"上证综合指数"的行，取其 indicator_id
ai-beta get-indicator-value --indicator-id "<indicator_id>" --last-n 52
# 直接画趋势图：自动图题、MA20/MA60 均线与最新值标注，PNG 落盘当前目录
ai-beta plot-series --indicator-id "<indicator_id>" --indicator-type "市盈率PE" --last-n 52
```

## Python SDK 简介

深度分析、建模，或使用无 CLI 命令的大数据量接口（见 Notes）时，直接导入 aibeta SDK：

```python
import aibeta

# 方式一：依赖环境变量 BETA_INDICATOR_API_APP_KEY / BETA_INDICATOR_API_SECRET_KEY
df = aibeta.beta_indicator.list_indicator_types()

# 方式二：代码内配置（对当前进程有效，避免设置环境变量）
aibeta.configuration(app_key="XXX", secret_key="XXX")
```

- 数据类接口统一返回 `pandas.DataFrame`；例外：`get_indicator_value_batch` 返回 `dict[str, DataFrame | None]`
- 自建脚本用 PEP 723 内联依赖声明 + `uv run your_script.py` 执行（模板见 `references/PythonSDK_使用手册.md` 第 3 节）
- 安装、凭证、全部函数签名与返回样例、板块指标库覆盖指标清单，见 `references/PythonSDK_使用手册.md`

## Directory Guide

- `SKILL.md`：本文件，SKILL 的入口与使用说明
- `references/CLI_使用手册.md`：CLI 详细用法（安装与环境、通用约定、子命令明细、排障）
- `references/PythonSDK_使用手册.md`：Python SDK 详细用法（安装、凭证、脚本执行、函数签名与返回样例、指标覆盖清单）
- `scripts/`：CLI 源码，同时是 `uv tool install` 的安装来源（运行期不执行、不写入）
  - `pyproject.toml`：包定义与构建配置（hatchling）
  - `src/beta_indicator/`：统一 CLI 的薄封装源码
- 数据与缓存完全由 aibeta SDK 托管（SDK 缓存默认位于 `~/.cache/aibeta/`，可用 `AIBETA_CACHE_DIR` 重定向，每 3 天自动重建），skill 内不维护任何业务缓存文件

## Notes

- **详细规则以两本手册为准**：命令参数、返回字段、输出 / 退出码 / 时间窗口约定与排障见 `references/CLI_使用手册.md`（第 3–5 节）；Python 函数签名与返回样例见 `references/PythonSDK_使用手册.md`
- **时序取数优先用 `--last-n` 控制范围**（而非 `--start-date`/`--end-date`）：语义直观、无日期口径歧义，结合指标频率（`list-indicators` 返回的 `indicator_frequency`）可直接换算历史跨度（日频 N=250 / 周频 N=52 / 月频 N=12 约一年）
- **指标类时序的 `--start-date`/`--end-date` 按 `data_publish_date`（发布日）过滤，而非 `data_date`（观测日）**：发布日通常晚于观测日（如 data_date=2019-01-04 的记录发布日为 2019-01-05），按"数据日期"直觉过滤会得到偏移结果；确需按观测日过滤时，取回数据后按 `data_date` 列自行过滤。主题指数按 `price_date` 过滤，不受影响（详见 `references/CLI_使用手册.md` 第 3.4 节）
- **超大数据量接口不提供 CLI 命令**：`list_indicators_by_sector_type`（数万~十万行级）、`get_indicator_value_by_type_and_sector`（数万行级以上）、`get_theme_classification_portfolio_daily`（主题成分股，单日约十万行级）。需要这些数据时写 Python 脚本调 SDK 并落盘（`to_parquet` / `to_csv`）后按条件过滤处理，不要整体打印
- **运行期不修改 Skill 目录（视为只读）**：CLI 经 `uv tool install` 从 `scripts/` 源码目录安装为独立工具（一次性，安装期需联网并写 uv 目录，构建过程不向 Skill 目录写入任何产物）；Python 脚本经 `uv run`（PEP 723）在 uv 自身缓存目录构建隔离环境；Skill 目录内不产生 `.venv` / `*.egg-info` 等运行时产物
