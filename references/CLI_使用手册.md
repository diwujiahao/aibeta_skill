# CLI 使用手册

本文档是统一 CLI（`ai-beta`）的详细使用手册，覆盖安装与运行环境、通用约定（输出 / 退出码 / 时间窗口 / 日期口径 / CLI-Python 接口对照）、子命令明细与排障。Python SDK 的详细用法见同目录 `PythonSDK_使用手册.md`。

数据统一来自 [aibeta SDK](https://pypi.org/project/aibeta/)（`aibeta==1.3.1`）：网络请求、Token 管理、重试与本地快照缓存全部由 SDK 托管，本 skill 仅提供薄封装的统一 CLI。

## 1. 概述与运行边界

CLI 以 SKILL 目录下随附的源码包（`scripts/` 目录）为分发物，通过 `uv tool install` 一次性安装为独立工具后，运行期与 Skill 目录完全解耦：

- 统一 CLI 入口：`ai-beta`（安装后从任意目录直接调用）
- **Skill 目录视为只读**：安装与运行均不修改 Skill 目录中的任何文件，不在其中产生 `.venv`、`*.egg-info` 等运行时产物
- `scripts/` 是 CLI 源码目录（同时是 `uv tool install` 的安装源），运行期不执行、不写入

数据来源与缓存：

- 所有数据接口均直调 aibeta SDK 对应函数，skill 内不再维护任何业务缓存文件
- SDK 会在缓存目录维护指标库的全量快照缓存（元数据：指标类型 / 板块 / 指标 ID 映射等），默认每 3 天自动重建一次；默认目录为 `~/.cache/aibeta/`，可通过 `AIBETA_CACHE_DIR` 重定向（见第 2.1 节）
- 单指标查询不会触发全量缓存重建；只有依赖元数据缓存的接口（如 `list-sectors`、`list-indicators-by-sector`）才会按需加载或刷新缓存
- 如果缓存目录不可写且未重定向，SDK 会明确报错，请先申请用户批准或设置 `AIBETA_CACHE_DIR` 后再继续执行

## 2. 安装与运行环境

运行前请确认：

- 已安装 `uv`（未安装时：`curl -LsSf https://astral.sh/uv/install.sh | sh`）
- 已完成一次性安装并通过启动前自检（见下方命令块）
- 已配置环境变量 `BETA_INDICATOR_API_APP_KEY` / `BETA_INDICATOR_API_SECRET_KEY`（凭证需向用户获取；两者都未配置时 SDK 会直接报凭证缺失错误。**CLI 只支持环境变量方式**，Python 脚本可用 `aibeta.configuration(app_key=..., secret_key=...)` 进程内配置）

一次性安装 + 启动前自检（建议合并为一次执行，把权限审批收敛为一轮）：

```bash
uv tool install "<skill 绝对路径>/scripts" && ai-beta doctor

# 验证：命令可用、自检通过
command -v ai-beta
ai-beta --help
```

安装后 CLI 成为独立工具，无需再进入 Skill 目录或使用 `uv run`，从任意目录直接执行 `ai-beta <子命令>`。安装成功的标志与升级方式见第 2.4 节；受限环境的写入位置与重定向见第 2.1 节。

### 2.1 写入位置与受限环境处理

安装与运行涉及的默认可写位置（均不在 Skill 目录内）：

| 阶段 | 默认位置 | 环境变量重定向 |
| --- | --- | --- |
| 安装（工具隔离环境） | `~/.local/share/uv/tools/` | `UV_TOOL_DIR` |
| 安装（可执行文件链接） | `~/.local/bin/` | `UV_TOOL_BIN_DIR` |
| 安装（依赖下载缓存） | `~/.cache/uv` | `UV_CACHE_DIR` |
| 运行（SDK 快照缓存） | `~/.cache/aibeta/` | `AIBETA_CACHE_DIR` |

任一默认位置不可写时的处理：

- **安装阶段**：为上表前三个变量显式指定可写目录后重试安装，例如：

```bash
UV_TOOL_DIR=/tmp/uv-tools \
UV_TOOL_BIN_DIR=/tmp/uv-bin \
UV_CACHE_DIR=/tmp/uv-cache \
  uv tool install "<skill>/scripts"
```

- **运行阶段**：用 `AIBETA_CACHE_DIR` 重定向 SDK 缓存目录（支持 `~` 与 `$VAR` 展开；需保证每次执行 `ai-beta` 时该环境变量可见）：

```bash
export AIBETA_CACHE_DIR=/tmp/aibeta-cache
ai-beta list-indicator-types
```

设置成功时 CLI 会在 `stderr` 输出一行确认（`SDK 缓存目录已按 AIBETA_CACHE_DIR 重定向到 …`）；若 SDK 版本不兼容导致重定向失败，CLI 会输出警告并回退默认目录 `~/.cache/aibeta/`，不中断查询。

### 2.2 首次安装的联网要求

- 联网需求集中在**安装阶段**：首次 `uv tool install` 需下载源码声明的依赖与构建后端（aibeta、pandas、pyarrow、matplotlib、requests、tqdm、hatchling 等）；本机 uv 缓存中已有依赖时不需要联网
- 安装完成后，日常查询不再下载依赖；仅在 SDK 缓存过期（默认 3 天）时按需联网拉取数据
- 如果网络受限、代理不可用，或当前环境禁止外网访问，应在第一次安装前向用户一次性说明并申请所需权限（网络 + 第 2.1 节列出的写入位置），避免运行查询时逐项审批（权限申请的完整说明见 `SKILL.md`「快速开始」）

### 2.3 启动前自检（ai-beta doctor）

首次安装完成后、进入查询前，运行一次启动前自检：

```bash
ai-beta doctor
```

一条命令内依次完成三项检查，报告以纯文本输出到 `stdout`（是本 CLI"stdout 只输出 JSON"约定的唯一例外）：

| 检查项 | 内容 | 级别 |
| --- | --- | --- |
| 缓存目录可写 | 按第 2.1 节确定生效目录（`AIBETA_CACHE_DIR` 或默认 `~/.cache/aibeta/`），实际创建目录并写入/删除探针文件 | `[FAIL]`（失败影响退出码） |
| 网络连通 | 对 aibeta API 主机（默认 `research.citics.com:443`）做 TCP 握手（5s 超时），不消耗凭证、不发起数据请求 | `[FAIL]`（失败影响退出码） |
| 凭证配置 | 检查 `BETA_INDICATOR_API_APP_KEY` / `BETA_INDICATOR_API_SECRET_KEY` 是否已设置 | `[WARN]`（仅提示，不影响退出码） |

退出码：`0` = 缓存与网络两项全部通过；`1` = 存在 `[FAIL]` 项。

设计目的：aibeta SDK 运行期依赖"网络访问"与"缓存目录写入"两类权限，若分别由安装命令与首次真实查询触发，会被分两次发现、分两次审批。doctor 在**同一次命令执行内**同时触发两类行为，把权限验证收敛到启动前一轮完成。

`[FAIL]` 项修复指引：

- 缓存目录不可写：按第 2.1 节设置 `export AIBETA_CACHE_DIR=<可写目录>` 后重跑
- 网络不通：确认网络/代理可用后重跑；doctor 仅验证 TCP 连通性，需要凭证的鉴权与数据请求问题在首次查询时才会暴露
- 凭证未配置：`[WARN]` 提示，向用户获取凭证并 export 后重跑可见 `[OK]`

自检可随时重跑用于排障。

### 2.4 安装验证与升级

安装成功的标志：

- `command -v ai-beta` 输出可执行文件路径（默认 `~/.local/bin/ai-beta`）
- `uv tool list` 中出现 `beta-indicator-scripts v<版本>`
- `ai-beta doctor` 无 `[FAIL]` 项（见第 2.3 节）

升级 / 覆盖安装：安装源是本地目录，uv 不跟踪其内容变化；更新 Skill 内的 `scripts/` 源码后用 `--force` 覆盖安装：

```bash
uv tool install --force "<skill 绝对路径>/scripts"
```

## 3. CLI 通用约定

### 3.1 输出约定

- 正常结果：输出 JSON 到 `stdout`
- 其他信息（错误、进度、规模统计、提示）：输出到 `stderr`

这意味着：

- 可以直接用 `> result.json` 保存正常结果
- 凭证错误、网络错误不会污染 JSON 输出
- SDK 内部执行期间的进度提示（如分页读取、缓存重建）会输出到 `stderr`；`stdout` 始终只包含最终 JSON 结果
- 每次成功执行后，CLI 会在 `stderr` 输出一行结果规模统计（如 `[ai-beta] list-sectors 返回 3 行记录`）；记录数超过 1000 行时，会附加"建议落盘 / 缩小范围"的提示，便于决定是否改用重定向或时间窗口参数重跑
- **所有命令均支持 `--compact`**：以无缩进单行 JSON 输出（体积最小），落盘场景推荐加该参数，如 `ai-beta list-indicators --indicator-type "市盈率PE" --compact > indicators.json`；默认输出 indent=2 的多行 JSON，便于人工阅读
- **例外：`plot-*` 绘图命令**：图表落盘为 PNG/SVG 文件，`stdout` 输出绘图结果摘要 JSON（含图片绝对路径、数据点数、均线窗口/标的数、最新值/截面日期等），供脚本/对话直接引用；规模统计同样输出到 `stderr`
- **例外：`doctor`**：自检报告为纯文本，直接输出到 `stdout`

### 3.2 退出码约定

| 退出码 | 含义 | `stdout` |
| --- | --- | --- |
| `0` | 成功（含窗口过滤后无剩余数据的空结果 `[]`） | 完整 JSON（`plot-*` 绘图命令为结果摘要） |
| `1` | 运行失败：凭证缺失、网络/服务端错误、参数校验失败，或 `get-indicator-value` / `get-theme-index` 的 ID 不存在或暂无数据，或 `plot-series` 的 ID 不存在 / 暂无数据 / 窗口过滤后无剩余时序，或 `plot-bar` / `plot-scatter` 的类型不存在、（scatter）频率不一致或频率元数据不可得（未加 `--skip-frequency-check` 时）/ 日期无法对齐或对齐后截面日期不唯一（原因与建议在 `stderr`） | 无 JSON 输出 |
| `2` | 用法错误（argparse：未知命令、缺少必填参数等） | 无 JSON 输出 |

脚本化场景据此判断：退出码非零即失败，无需解析 `stdout`；`[]` 且退出码为 `0` 表示查询成功但区间内没有数据。

### 3.3 时间窗口参数

适用于：`get-indicator-value`、`get-indicator-value-batch`、`get-theme-index`、`plot-series`。

- `--last-n N`：仅保留最后 `N` 条记录（**推荐优先使用**，理由见 3.5 节）
- `--start-date YYYY-MM-DD` / `--end-date YYYY-MM-DD`：按日期过滤，均为包含边界
- **所有日期入参统一强制 YYYY-MM-DD 严格校验**：只接受形如 `2024-01-31` 的完整写法；`20260901`、`2026/12/31`、`2024-1-1` 等即使 pandas 能宽松解析，也会直接报错退出，不会静默接受
- 组合使用时：先按日期区间过滤，再截取最后 `N` 条
- 未传任何时间窗口参数时，默认 `--last-n 25`（防止全量历史撑爆输出）；传了任意一个窗口参数则关闭默认截取
- 指标类时序的日期口径为返回结果中的 `data_publish_date`（数据发布日期，例如 12-31 年报可能滞后到次年 04-30 发布）；主题指数的日期口径为 `price_date`
- 日期过滤在本地对 SDK 返回的全量历史执行，不会减少 API 调用

### 3.4 重要：日期口径是 data_publish_date（发布日），不是 data_date（观测日）

指标类时序命令的 `--start-date` / `--end-date` 过滤的是 **`data_publish_date`（数据发布日期）**，而不是 `data_date`（观测日期）。两者含义不同：

| 字段 | 含义 | 样例 |
| --- | --- | --- |
| `data_date` | 观测日期：指标值对应的市场/报告期日期 | `2019-01-04` |
| `data_publish_date` | 发布日期：该条记录实际可得的日期 | `2019-01-05 09:00:00` |

`data_publish_date` 通常晚于 `data_date`（上例相差 1 天；年报类指标可能滞后数月，如 12-31 年报可能次年 04-30 才发布）。因此按"数据日期"的直觉使用日期区间会得到偏移结果：例如想取 2019-01-04 观测的记录而传 `--start-date 2019-01-04 --end-date 2019-01-04`，命中的是"发布日为该日"的记录，其观测日实际更早。

如确需按 `data_date`（观测日）过滤，请先用 `--last-n` 或放宽的日期区间取回数据，再在下游按返回结果中的 `data_date` 列自行过滤。

> 主题指数 `get-theme-index` 不受此影响：其日期口径 `price_date` 即指数价格日期本身。

### 3.5 推荐：优先用 --last-n，而不是 --start-date/--end-date

时序取数建议优先使用 `--last-n` 控制范围：

- 无日期口径歧义："最后 N 条"语义直观，不会误触 3.4 节所述的发布日/观测日偏差
- 结合指标频率（`list-indicators` 返回的 `indicator_frequency`），`N` 可直接换算取了多久的历史：

| 指标频率 | 约一年历史 | 约两年历史 |
| --- | --- | --- |
| 日频 | `--last-n 250` | `--last-n 500` |
| 周频 | `--last-n 52` | `--last-n 104` |
| 月频 | `--last-n 12` | `--last-n 24` |

- 仅在确需"截到某个发布日为止"等场景才使用 `--start-date` / `--end-date`，并注意 3.4 节的口径说明；两者可组合使用（先区间过滤，再截取最后 N 条）

### 3.6 CLI / Python 接口对照

除批量接口外，CLI 与 Python（aibeta SDK）的"记录结构"一一对应，只是承载容器不同（CLI 为 `list[dict]`，Python 为 `pandas.DataFrame`）：

| CLI 子命令 | aibeta SDK 调用 |
| --- | --- |
| `list-indicator-types` | `aibeta.beta_indicator.list_indicator_types()` |
| `list-indicators` | `aibeta.beta_indicator.list_indicators(indicator_type)` |
| `get-indicator-value` | `aibeta.beta_indicator.get_indicator_value(indicator_id)` |
| `get-indicator-value-batch` | `aibeta.beta_indicator.get_indicator_value_batch(indicator_ids)` |
| `list-sector-types` | `aibeta.beta_indicator.list_sector_types()` |
| `list-sectors` | `aibeta.beta_indicator.list_sectors(sector_type)` |
| `list-indicators-by-sector` | `aibeta.beta_indicator.list_indicators_by_sector(sector_code)` |
| `get-indicator-value-latest-by-type-and-sector` | `aibeta.beta_indicator.get_indicator_value_latest_by_type_and_sector(indicator_type, sector_type)` |
| `get-theme-framework-daily` | `aibeta.theme_classification.get_theme_classification_framework_daily(view_date)` |
| `get-theme-index` | `aibeta.theme_classification.get_theme_classification_index_by_id(theme_id)` |
| `get-market-daily-report` | `aibeta.text_analysis.get_information_ai_report_market_daily(start_date, end_date)` |
| `get-strategy-weekly-report` | `aibeta.text_analysis.get_information_ai_report_strategy_weekly(start_date, end_date)` |
| `plot-series`（指标模式） | `aibeta.beta_indicator.get_indicator_value(indicator_id)` |
| `plot-series`（主题模式） | `aibeta.theme_classification.get_theme_classification_index_by_id(theme_id)` |
| `plot-bar` | `aibeta.beta_indicator.get_indicator_value_latest_by_type_and_sector(indicator_type, sector_type)` |
| `plot-scatter` | 同上调用 2 次（两个指标类型）按 `sector_code` 对齐；另调 `list_indicators(indicator_type)` 校验频率与取单位 |

约定说明：

- CLI 的 `null` 对应 Python 的 `None`
- CLI 中每条记录的字段名与 Python `DataFrame` 列名保持一致，以下三类 CLI 侧统一增强除外：
  - SDK 返回的 `indicator_related_sector_type`（list 字符串）/ `indicator_related_sector_code`（dict 字符串）/ `indicator_related_sector`（dict 字符串）会被解析为标准三列 `sector_type` / `sector_code` / `sector_name`，原始列不再输出；`sector_type` 缺失时从 code 的 dict key 推导
  - 主题指数的 `price_date`（`YYYYMMDD` 格式字符串）统一输出为 ISO 日期字符串（`YYYY-MM-DD`）
  - 缓存类命令（`list-sector-types` / `list-sectors` / `list-indicators-by-sector`）不输出 `update_time`：SDK 衍生接口基于本地缓存快照实现，其 `update_time` 是缓存重建时间而非后端数据更新时间，为避免与原子接口（如 `list-indicators`）的 `update_time` 混淆，CLI 统一剔除该列
- 所有字符串入参（含批量命令的 ID 列表）会自动去除首尾空白，避免空白字符导致匹配失败
- 当前 CLI 不额外包裹 `data`、`meta` 等顶层信封，便于直接重定向成 JSON 文件继续处理
- 如果需要解释某个具体指标的统计边界或计算口径，应优先读取接口返回中的 `indicator_caliber`
- 以下大数据量 SDK 接口**不提供 CLI 命令**（单次输出达数万~数十万行，JSON 可达数十 MB，无法用参数收敛）：`list_indicators_by_sector_type`（数万~十万行级）、`get_indicator_value_by_type_and_sector`（数万行级以上）、`get_theme_classification_portfolio_daily`（单日约十万行级）。需要这些数据时按第 6 节写 Python 脚本调用并落盘处理

## 4. 子命令明细

以下命令的通用规则（输出、退出码、时间窗口与日期口径、CLI/Python 字段对照）见第 3 节；排障见第 5 节。

### 4.1 板块指标库

#### 查询所有指标类型

```bash
ai-beta list-indicator-types
```

返回字段：`indicator_type`。

#### 查询某个指标类型下的指标列表

```bash
ai-beta list-indicators --indicator-type "市盈率PE"
```

可选过滤参数（客户端过滤，用于缩小输出规模）：

```bash
# 按板块类型精确过滤
ai-beta list-indicators \
  --indicator-type "市盈率PE" \
  --sector-type "ETF指数"

# 按关键字模糊过滤（同时匹配 indicator_name、sector_name 与 sector_code）
ai-beta list-indicators \
  --indicator-type "市盈率PE" \
  --keyword "上证"
```

返回字段：`indicator_id`, `indicator_type`, `indicator_name`, `indicator_unit`, `indicator_frequency`, `indicator_caliber`, `sector_type`, `sector_code`, `sector_name`, `update_time`。

说明：

- 每类约 2 千行，建议先用过滤参数缩小范围
- `indicator_name` 是系统拼接的长名称（含指标类型、关联板块、统计口径、频率、单位等信息，如 `市盈率PE__['ETF指数']__{...}__当期__周__无单位`），定位目标板块时以解析出的 `sector_name` / `sector_code` 列（或 `--keyword`）为准，实际取数只使用 `indicator_id`
- `--sector-type` 是 CLI 本地过滤参数（SDK `list_indicators` 无此入参，见第 3.6 节对照表），按返回记录的 `sector_type` 列精确匹配；该列恒为板块家族口径（ETF指数 / 中信证券行业 / 主题概念），传中信一/二/三级行业会得到空结果，需要细分层级截面请改用 `get-indicator-value-latest-by-type-and-sector`

#### 查询单个指标的时序数据

```bash
ai-beta get-indicator-value --indicator-id "7023d2fa62ec5163b4d70dfb9f4ad3348beddf5580cf0118d97af7d7a838d76c"
```

可选时间窗口参数（规则见第 3.3–3.5 节）。

**推荐用 `--last-n` 控制取数范围**：语义直观、无日期口径歧义，且结合指标频率可直接换算历史跨度（如周频指标 `--last-n 52` 约一年）：

```bash
ai-beta get-indicator-value \
  --indicator-id "7023d2fa62ec5163b4d70dfb9f4ad3348beddf5580cf0118d97af7d7a838d76c" \
  --last-n 52
```

也可用日期区间过滤，但**注意：区间按发布日 `data_publish_date` 过滤，而非观测日 `data_date`**，详见第 3.4 节：

```bash
ai-beta get-indicator-value \
  --indicator-id "7023d2fa62ec5163b4d70dfb9f4ad3348beddf5580cf0118d97af7d7a838d76c" \
  --start-date "2024-01-01" \
  --end-date "2024-06-30" \
  --last-n 20
```

返回字段：`data_id`, `indicator_id`, `data_value`, `data_date`, `data_publish_date`, `update_time`。

#### 批量查询多个指标的时序数据

```bash
ai-beta get-indicator-value-batch \
  --indicator-id "f05d22906036b430fae3854635e8015b3384d04bcba38593c67c7e5d5b4aefee" \
  --indicator-id "831a95f5e39492edfd8a98397869a9c50496152faefba1e4bfbc0bab7abe227f"
```

说明：

- 返回 JSON 对象，以 `indicator_id` 为 key，每个 value 的字段同 `get-indicator-value`
- 固定使用并发数 `3`，CLI 不暴露并发参数；`--indicator-id` 最多 30 个，超出直接报错
- 重复传入的 `--indicator-id` 会自动去重，并在 `stderr` 输出提示
- 若批量中某些指标读取失败（网络、鉴权或服务端错误）、指标不存在或暂无数据、或应用时间窗口后没有剩余数据，该指标在 JSON 中返回 `null`，具体原因逐条输出到 `stderr`（三类空结果语义见第 5.3 节）

#### 查询所有板块类型

```bash
ai-beta list-sector-types
```

返回字段：`sector_type`（不输出 `update_time`，原因见第 3.6 节）。

共 6 类：ETF指数 / 中信证券行业 / 中信证券一级行业 / 中信证券二级行业 / 中信证券三级行业 / 主题概念；中信家族按"聚合 → 一级 → 二级 → 三级"排序。

#### 查询板块列表

```bash
# 查询全部板块（约 2.3 千行，建议搭配过滤或落盘）
ai-beta list-sectors

# 按板块类型过滤
ai-beta list-sectors --sector-type "ETF指数"

# 按关键字模糊过滤（同时匹配板块名称与代码）
ai-beta list-sectors --keyword "沪深300"

# 按板块代码或板块名称精确查询
ai-beta list-sectors --sector-code "000300.SH"
ai-beta list-sectors --sector-name "沪深300指数"
```

返回字段：`sector_type`, `sector_code`, `sector_name`（不输出 `update_time`，原因见第 3.6 节）。

`--sector-type` 支持全部 6 类板块类型（含中信证券一/二/三级行业细分，传入细分类型时仅返回对应层级的板块）。

#### 按板块代码查询关联指标列表

```bash
ai-beta list-indicators-by-sector --sector-code "000001.SH"
```

返回字段：`indicator_type`, `sector_type`, `sector_code`, `sector_name`, `indicator_id`, `indicator_unit`, `indicator_frequency`（不输出 `update_time`，原因见第 3.6 节）。

#### 按指标类型+板块类型查询所有板块的最新一期指标值

```bash
ai-beta get-indicator-value-latest-by-type-and-sector \
  --indicator-type "市盈率PE" \
  --sector-type "ETF指数"
```

返回字段：`data_id`, `indicator_id`, `sector_type`, `sector_code`, `sector_name`, `data_value`, `data_date`, `data_publish_date`, `update_time`。

适合做跨板块截面比较；如需单指标历史时序，改用 `get-indicator-value`，需要全板块历史值时按第 6 节用 Python 调用 SDK。

注意：本命令返回所有板块的最新一期截面（每板块一行），在"主题概念"板块类型下约 1.5 千行，建议搭配重定向落盘使用。

`--sector-type` 支持全部 6 类板块类型（含中信证券一/二/三级行业细分，传入细分类型时仅返回对应层级的板块）；传"中信证券行业"为聚合口径，等价三级并集。

### 4.2 主题分类

#### 查询主题库日度截面数据

```bash
ai-beta get-theme-framework-daily --view-date "2026-06-30"
```

返回字段：`level_1_name`, `level_2_name`, `theme_id`, `theme_name`, `create_time`, `delete_time`, `sys_update_time`（约 0.9 千行）。`theme_id` 供 `get-theme-index` 使用。

如需主题成分股（标准池）明细，因单日数据量约十万行，不提供 CLI 命令，请按第 6 节用 Python 调用 `get_theme_classification_portfolio_daily` 并落盘处理。

#### 查询特定主题的历史指数点位

```bash
ai-beta get-theme-index --theme-id "66f3c5b8..."
```

支持时间窗口参数（按 `price_date` 过滤）：

```bash
ai-beta get-theme-index \
  --theme-id "66f3c5b8..." \
  --start-date "2026-01-01" \
  --end-date "2026-06-30" \
  --last-n 20
```

返回字段：`theme_id`, `index_name`, `index_external_code`, `price_date`, `close_price`；输出的 `price_date` 为 ISO 日期字符串（`YYYY-MM-DD`）。

### 4.3 文本库

#### 读取市场日报文本

```bash
# 默认：不传任何参数，返回最新 1 期
ai-beta get-market-daily-report

# 推荐：返回最新 N 期（单篇报告数十 KB，N 不宜过大）
ai-beta get-market-daily-report --last-n 5

# 按日期区间（严格 YYYY-MM-DD，start/end 必须同时提供）
ai-beta get-market-daily-report --start-date "2026-06-01" --end-date "2026-06-30"
```

返回字段：`data_id`, `insert_time`, `update_time`, `view_date`, `report`（markdown 正文）。

说明：

- 结果**按 `view_date` 降序排列（最新在前）**
- `--last-n` 与日期区间组合使用时：先按区间过滤，再取区间内最新 `N` 期
- 仅传 `--last-n`（不传日期区间）时，CLI 以宽日期区间向服务端取数后在本地截取最新 `N` 期
- 正文中指向服务端内部路径的图片引用（markdown 行内图片与 HTML img 标签）由 CLI 自动删除，避免内部路径泄漏与输出膨胀

#### 读取策略周报文本

参数规则与返回字段同市场日报（默认最新 1 期；`--last-n` 取最新 N 期；或传日期区间），结果同样按 `view_date` 降序排列：

```bash
ai-beta get-strategy-weekly-report --last-n 4
```

### 4.4 时序折线图（plot-series）

把单指标 / 主题指数的历史时序直接绘制为图表文件（PNG/SVG），默认叠加 MA20/MA60 均线并在图上标注最新值，无需编写分析脚本：

```bash
# 指标模式：上证综合指数最近一年的市盈率PE趋势图（自动图题 + MA20/MA60 + 最新值标注，PNG 落盘当前目录）
ai-beta plot-series \
  --indicator-id "7023d2fa62ec5163b4d70dfb9f4ad3348beddf5580cf0118d97af7d7a838d76c" \
  --indicator-type "市盈率PE" \
  --last-n 52

# 主题模式：主题指数近半年走势，输出 SVG 到指定路径
ai-beta plot-series \
  --theme-id "66f3c5b8..." \
  --last-n 120 \
  -o /tmp/theme_trend.svg
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `--indicator-id` / `--theme-id` | 【二选一必填】绘图对象；指标时序或主题指数点位 |
| `--indicator-type` | 【可选】指标类型名称；提供后自动查询元数据生成图题（"指标类型 · 板块名（频率 · 口径 · 单位）"）、y 轴单位与图例（指标类型名），省略时图题为 indicator_id、图例为"指标值" |
| `--title` | 【可选】自定义图题，覆盖自动图题 |
| `--ma` | 【可选】均线窗口（期数，逗号分隔，默认 `20,60`）；窗口长于数据点数时自动跳过并在 `stderr` 提示 |
| `--no-ma` / `--no-annotate` | 【可选】分别关闭均线与最新值标注 |
| `--output` / `-o` | 【可选】输出路径，支持 `.png`（默认）与 `.svg`；缺省扩展名按 `--format` 补全；未提供时当前目录自动命名 `plot_series_<ID前8位>_<时间戳>.png` |
| `--format` | 【可选】`png` / `svg`；省略时按 `--output` 扩展名推断，仍无法确定时为 `png` |
| 时间窗口参数 | 同第 3.3–3.5 节；指标模式按 `data_publish_date` 过滤、主题模式按 `price_date` 过滤，与对应查询命令一致 |

行为约定：

- 图表横轴为观测日（指标模式 `data_date`、主题模式 `price_date`），时间窗口过滤口径仍按第 3.3–3.5 节执行
- `stdout` 输出结果摘要 JSON：`output`（图片绝对路径）、`format`、`title`、`data_points`、`ma_windows_applied`、`latest`（`date` + `value`）；均线被跳过时附 `ma_windows_skipped`；`stderr` 输出一行生成统计
- ID 不存在、暂无数据或窗口过滤后无剩余时序时视为失败（退出码 `1`）

### 4.5 截面柱状图（plot-bar）

把一个指标类型在多个板块上的**最新一期截面**值绘制为柱状图，适合跨板块横向比较：

```bash
# 市盈率PE 在全部 ETF 指数上的最新截面（标的 ≤ 30 全部绘制，更多时两端各取 15；横轴为标的名称，柱顶带数值标签）
ai-beta plot-bar --indicator-type "市盈率PE" --sector-type "ETF指数"

# 升序、输出 SVG
ai-beta plot-bar --indicator-type "市盈率PE" --sector-type "ETF指数" \
  --sort asc -o /tmp/pe_bar.svg
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `--indicator-type` | 【必填】指标类型名称 |
| `--sector-type` | 【必填】板块类型名称，可选全集：ETF指数 / 中信证券行业 / 中信证券一级行业 / 中信证券二级行业 / 中信证券三级行业 / 主题概念 |
| `--sort` | 【可选】`desc`（默认）/ `asc` |
| `--title` / `--output` / `--format` | 同第 4.4 节；自动命名前缀为 `plot_bar_` |

行为约定：

- 截面取**最新一期**，不支持时间窗口参数；各标的最新数据日期不一致时（如月频指标各板块报告期不同）`stderr` 提示，柱高为各自最新值
- 图题默认为 `指标类型 · 板块类型（截面日期 · 频率 · 单位）`（截面日期取占比最高者）；横轴刻度为标的名称
- 「中信证券一/二/三级行业」为细分层级（一级代码 2 位、二级 4 位、三级 6 位），仅返回对应层级的板块；细分层级无数据时报错退出（退出码 `1`）
- 标的数 ≤ 30 时全部绘制；超过 30 时按排序方向两端各取 15（Top15 + Bottom15，共 30 根柱），中间以"省略 N 个"跳跃刻度提示并在 `stderr` 说明；`stdout` 摘要 JSON 含 `bars`（绘制柱数）、`sectors_total`（截面标的总数）、`data_dates`（截面涉及的去重观测日期），两端截取时附 `omitted_sectors`（被省略标的数）
- 类型取值不存在或截面无有效数值 → 退出码 `1`

### 4.6 双指标截面散点图（plot-scatter）

把两个**同频率**指标类型在多个板块上的最新截面值绘制为散点图，每点一个板块，用于观察两个指标的相关性与离群板块：

```bash
# 市盈率PE（x 轴）vs 市净率PB（y 轴），板块类型为 ETF 指数
ai-beta plot-scatter \
  --indicator-type "市盈率PE" \
  --indicator-type "市净率PB" \
  --sector-type "ETF指数"

# 逐点标注板块名称（点多时文字会重叠，建议仅在标的较少时使用）
ai-beta plot-scatter --indicator-type "市盈率PE" --indicator-type "市净率PB" \
  --sector-type "ETF指数" --annotate -o /tmp/pe_pb.png
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `--indicator-type` | 【必填】重复传入恰好 2 次：第 1 次为 x 轴，第 2 次为 y 轴；两者必须不同 |
| `--sector-type` | 【必填】板块类型名称，可选全集同第 4.5 节（含中信证券一/二/三级行业层级拆分） |
| `--annotate` | 【可选】逐点标注板块名称（默认不标注） |
| `--skip-frequency-check` | 【可选】跳过同频率自动校验（频率不一致或频率元数据不可得时默认失败；确认两指标频率口径一致后可显式跳过） |
| `--title` / `--output` / `--format` | 同第 4.4 节；自动命名前缀为 `plot_scatter_` |

行为约定：

- **同频率自动校验（fail closed）**：两指标类型的频率元数据不一致时直接失败（如 周频 × 日频）；频率元数据不可得时同样失败，退出码 `1`。确认两指标频率口径一致后，可加 `--skip-frequency-check` 显式跳过校验
- **日期对齐（严格同一数据日期）**：两截面按 `sector_code` 内连接，仅保留两侧 `data_date` 相同的板块；被剔除数量在 `stderr` 提示（摘要 JSON 附 `date_mismatch_dropped`），全部无法对齐则失败；对齐后若仍含多个不同数据日期，无法构成同一日横截面，直接失败（退出码 `1`）并逐日期提示板块数，拒绝出图
- 「中信证券一/二/三级行业」为细分层级（一级 2 位、二级 4 位、三级 6 位），截面仅含对应层级的板块，再进行日期对齐与离群点剔除
- **离群点剔除**：对齐后任一坐标偏离该轴中位数超过 20×1.4826×MAD（即 29.652×MAD 稳健标准差）的板块整点剔除，避免极端值压缩主体散点；剔除数量在 `stderr` 提示并附于摘要 JSON `outliers_dropped`，某轴 MAD 为 0（半数以上取值相同）时跳过该轴剔除
- x/y 轴标签自动带指标单位；`stdout` 摘要 JSON 含 `points`、`data_date`（截面数据日期，对齐后唯一）、`x_indicator_type`、`y_indicator_type`、`date_mismatch_dropped`（发生日期剔除时）、`outliers_dropped`（发生离群点剔除时）

字体与渲染环境（三个绘图命令通用）：

- 中文字体自动探测（华为鸿蒙 HarmonyOS Sans 优先，其后为 Noto Sans CJK / Source Han Sans / 微软雅黑 / SimHei / 文泉驿等常见字体），命中即用；缺失时 `stderr` 警告一次并继续出图（图内中文可能显示为方块），安装系统字体（如 `fonts-noto-cjk`）后重试即可
- 渲染固定使用 Agg 后端（无显示环境友好）；matplotlib 配置/字体缓存固定重定向到 `~/.cache/matplotlib`，不触碰 `~/.config`

## 5. 典型错误与排障

### 5.1 凭证缺失

如果未配置以下环境变量，CLI 会直接失败，并在 `stderr` 输出详细提示：

- `BETA_INDICATOR_API_APP_KEY`
- `BETA_INDICATOR_API_SECRET_KEY`

### 5.2 网络请求失败

SDK 请求失败（网络不通、服务端异常等）会抛出带原因说明的错误，CLI 将其输出到 `stderr` 并以非零退出码结束。可先运行 `ai-beta doctor` 快速区分网络连通问题（`[FAIL]`）与凭证未配置问题（`[WARN]`）。

### 5.3 批量接口中的空结果

批量查询中单个 `indicator_id` 未返回有效数据时，CLI 会逐条向 `stderr` 输出原因，该指标在 JSON 结果中返回 `null`。原因分三类：

- **读取失败**：网络、鉴权或服务端错误等请求级失败；Python API 中对应的值为 `None`
- **服务端无数据**：指标 ID 不存在或暂无数据；Python API 返回空 `DataFrame`，并非 `None`
- **时间窗口过滤后无剩余**：原始数据存在，但 `--start-date` / `--end-date` / `--last-n` 过滤后为空；仅发生在 CLI 侧

这样可以避免把"空结果"误判成"成功但只是没有展示内容"，也避免把"指标不存在"误判成"窗口过滤导致无数据"。

### 5.4 空结果提示与日期参数校验

- 列表 / 截面类命令返回空结果（`[]`）时，CLI 会在 `stderr` 输出对应的排障提示，建议先运行 `list-indicator-types` / `list-sector-types` / `list-sectors` 确认可用取值
- `get-indicator-value` / `get-theme-index` 传入的 ID 不存在或暂无数据（服务端未返回任何记录）时视为**失败**：`stderr` 报错并提示查找有效 ID 的途径（`list-indicators` / `get-theme-framework-daily`），以退出码 `1` 结束，`stdout` 不输出 JSON；若只是时间窗口过滤后没有剩余数据，则查询仍算成功，返回 `[]` 并以退出码 `0` 结束，`stderr` 提示放宽窗口参数
- `get-theme-framework-daily` 的 `--view-date` 晚于当前日期时，CLI 会在 `stderr` 警告：服务端将返回最新一期截面数据，而非该日数据
- `get-market-daily-report` / `get-strategy-weekly-report` 会校验 `--start-date` / `--end-date`：非 YYYY-MM-DD 严格格式（如 `20260901`、`2026/12/31`）或 `start_date` 晚于 `end_date` 时直接报错，与时间窗口命令的行为一致

### 5.5 命令未找到（ai-beta: command not found）

说明尚未安装，或安装目录不在 `PATH`：

- 确认安装状态：`uv tool list`（应出现 `beta-indicator-scripts v<版本>`，版本号以 `scripts/pyproject.toml` 的 `version` 为准，可执行文件为 `ai-beta`）
- 未安装或需重装：按第 2 节执行 `uv tool install`
- PATH 问题：`export PATH="$HOME/.local/bin:$PATH"` 后重试（或按第 2.1 节用 `UV_TOOL_BIN_DIR` 把可执行文件装到已列入 PATH 的目录）

### 5.6 图表中文显示为方块（plot-*）

`plot-*` 运行时若 `stderr` 输出"未检测到中文字体"警告，说明当前环境没有任何中文字体（headless 服务器 / 精简容器常见），图内的中文标题、标注会显示为方块，但命令本身仍成功退出（退出码 `0`）：

- 修复：安装任一常见中文字体后重跑，例如 Debian/Ubuntu `apt-get install fonts-noto-cjk`，随后无需任何配置即可被自动探测
- matplotlib 配置/字体缓存位于 `~/.cache/matplotlib`；如该目录异常可删除后让其自动重建

## 6. Python 脚本取数

复杂分析、大数据量接口（见第 3.6 节）与主题成分股明细不提供 CLI 命令，需写 Python 脚本直接调用 aibeta SDK：

- CLI 子命令与 SDK 函数的对照关系见第 3.6 节
- SDK 安装、凭证配置、全部函数签名与返回样例见同目录 `PythonSDK_使用手册.md`
- 脚本执行方式（PEP 723 内联依赖声明 + `uv run`，在 uv 自身缓存目录构建隔离环境、不写入 Skill 目录）见 `PythonSDK_使用手册.md` 第 3 节
