# 板块分析数据服务 Python SDK 使用手册

板块分析数据服务 API SDK，提供以下数据服务的统一查询接口。

- 主题分类体系
- 板块指标库
- 文本库（AI 报告文本）

## 1. 安装 Python SDK

独立环境（本 skill 之外）使用时：

```bash
pip install aibeta -i https://pypi.org/simple
```

在本 skill 环境中运行自建分析脚本，推荐 PEP 723 内联依赖 + `uv run` 方式执行，uv 会自动构建隔离环境，无需手动安装（见第 3.2 节）。

## 2. 配置凭证

SDK 需要 `app_key` / `secret_key` 两个凭证，二选一方式提供：

```python
import aibeta
# 方式一：代码内配置（对当前进程有效）
aibeta.configuration(app_key="XXX", secret_key="XXX")
```

或通过环境变量配置（不调用 `configuration` 时自动读取）：

```bash
# 方式二：通过环境变量配置（长期有效）
export BETA_INDICATOR_API_APP_KEY="XXX"
export BETA_INDICATOR_API_SECRET_KEY="XXX"
```

## 3. 快速上手

### 3.1 最小示例

```python
import aibeta

# 配置app-key，app-secret (避免设置环境变量，对单次程序运行有效)
aibeta.configuration(app_key='XXX', secret_key='XXX')

# 板块指标库模块：读取所有指标类型
aibeta.beta_indicator.list_indicator_types()
```

### 3.2 脚本执行方式（PEP 723 + uv run）

在本 skill 环境中，自建分析脚本在文件头部加 PEP 723 内联依赖声明，保存后用 `uv run` 执行：uv 依据声明在 uv 自身缓存目录构建隔离环境，不写入 Skill 目录，也无需手动 pip 安装。

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "aibeta==1.1.0",
# ]
# ///
import aibeta

df = aibeta.beta_indicator.list_indicator_types()
```

```bash
uv run your_script.py
```

> 提示：时间窗口裁剪（`trim_timeseries_window`）与板块关联列解析（`normalize_related_sector_columns`）是本 skill CLI 的本地增强，SDK 本身不提供；自定义脚本需要同等能力时可参考 `../scripts/src/beta_indicator/output.py`。

## 4. 接口说明

数据类接口统一返回 `pandas.DataFrame`（`get_indicator_value_batch` 除外）。凭证配置见上方「配置凭证」。

函数索引（各函数的参数与返回样例见下方分节）：

| 模块 | 函数 | 功能 |
| --- | --- | --- |
| 全局 | `aibeta.configuration(...)` | 配置当前进程的凭证与超时参数 |
| `beta_indicator` | `list_indicator_types()` | 读取所有指标类型 |
| `beta_indicator` | `list_indicators(indicator_type)` | 按指标类型读取指标列表 |
| `beta_indicator` | `get_indicator_value(indicator_id)` | 按指标 ID 读取该指标全部数值记录 |
| `beta_indicator` | `get_indicator_value_inc(view_date)` | 按日期增量读取所有指标值 |
| `beta_indicator` | `get_indicator_value_batch(indicator_ids, max_workers=3)` | 并发批量读取多个指标的数值记录（≤30） |
| `beta_indicator` | `list_sector_types()` | 读取所有板块类型 |
| `beta_indicator` | `list_sectors(sector_type=None)` | 读取板块列表 |
| `beta_indicator` | `list_indicators_by_sector_type(sector_type)` | 按板块类型读取全部指标列表（数万~十万行级） |
| `beta_indicator` | `list_indicators_by_sector(sector_code)` | 按板块代码读取该板块全部指标列表 |
| `beta_indicator` | `get_indicator_value_by_type_and_sector(indicator_type, sector_type)` | 读取所有板块的历史指标值（数万行级以上） |
| `beta_indicator` | `get_indicator_value_latest_by_type_and_sector(indicator_type, sector_type)` | 读取所有板块的最新一期指标值 |
| `theme_classification` | `get_theme_classification_framework_inc(view_date)` | 主题库日度增量数据 |
| `theme_classification` | `get_theme_classification_framework_daily(view_date)` | 主题库日度截面数据 |
| `theme_classification` | `get_theme_classification_portfolio_inc(view_date)` | 主题成分股（标准池）日度增量数据 |
| `theme_classification` | `get_theme_classification_portfolio_daily(view_date)` | 主题成分股（标准池）日度截面数据（单日约十万行级） |
| `theme_classification` | `get_theme_classification_index_inc(view_date)` | 主题指数点位日度增量数据 |
| `theme_classification` | `get_theme_classification_index_by_id(theme_id)` | 查询特定主题的历史指数点位 |
| `text_analysis` | `get_information_ai_report_market_daily(start_date, end_date)` | 根据时间范围读取市场日报文本 |
| `text_analysis` | `get_information_ai_report_strategy_weekly(start_date, end_date)` | 根据时间范围读取策略周报文本 |

### 4.1、全局配置

**`configuration`**

- **调用方式**：`aibeta.configuration(...)`
- **功能简介**：配置当前进程的凭证与超时参数
- **参数**：`app_key` / `secret_key` / `timeout`，均可选

### 4.2、主题分类 `theme_classification`

**`get_theme_classification_framework_inc`**

- **调用方式**：`theme_classification.get_theme_classification_framework_inc(view_date)`
- **功能简介**：主题库日度增量数据
- **参数**：`view_date: str`，查询日期

**返回样例**：

| level_1_name | level_2_name   | theme_id              | theme_name | create_time         | delete_time | sys_update_time     |
| ------------ | -------------- | --------------------- | ---------- | ------------------- | ----------- | ------------------- |
| 产业主题     | 制造类主题     | `70b59e45…d8a5f5`  | 电网概念   | 2026-06-26 18:54:16 | None        | 2026-06-26 18:54:28 |
| 产业主题     | 医药健康类主题 | `4ab53eda…d94f1c0` | 精准诊断   | 2026-06-26 18:57:48 | None        | 2026-06-26 18:57:59 |
| 产业主题     | 科技类主题     | `7d8d049f…673ab38` | MLCC       | 2019-02-28 00:00:00 | None        | 2026-06-26 18:58:00 |

---

**`get_theme_classification_framework_daily`**

- **调用方式**：`theme_classification.get_theme_classification_framework_daily(view_date)`
- **功能简介**：主题库日度截面数据
- **参数**：`view_date: str`，查询日期

**返回样例**：

| level_1_name | level_2_name     | theme_id              | theme_name   | create_time         | delete_time | sys_update_time     |
| ------------ | ---------------- | --------------------- | ------------ | ------------------- | ----------- | ------------------- |
| 事件主题     | 地缘事件主题     | `b7d49308…a941bc`  | 俄乌冲突概念 | 2022-03-31 00:00:00 | None        | 2024-09-26 17:04:21 |
| 事件主题     | 宏观事件主题     | `b4c27ae6…6882af2` | 煤价下跌受益 | 2018-01-31 00:00:00 | None        | 2024-09-26 17:04:21 |
| 事件主题     | 社会活动事件主题 | `09782039…0adb25c` | 进口博览会   | 2018-08-31 00:00:00 | None        | 2024-09-26 17:04:21 |

---

**`get_theme_classification_portfolio_inc`**

- **调用方式**：`theme_classification.get_theme_classification_portfolio_inc(view_date)`
- **功能简介**：主题成分股（标准池）日度增量数据
- **参数**：`view_date: str`，查询日期

**返回样例**：

| theme_id              | stock_code | create_time         | delete_time         |
| --------------------- | ---------- | ------------------- | ------------------- |
| `195ad447…7042e7`  | 600599.SH  | 2018-01-31 23:30:00 | 2026-06-26 00:00:00 |
| `1dc6c207…4e960c1` | 600599.SH  | 2018-01-31 23:30:00 | 2026-06-26 00:00:00 |
| `91c32f41…01cebc8` | 600599.SH  | 2025-05-31 23:30:00 | 2026-06-26 00:00:00 |

---

**`get_theme_classification_portfolio_daily`**

- **调用方式**：`theme_classification.get_theme_classification_portfolio_daily(view_date)`
- **功能简介**：主题成分股（标准池）日度截面数据
- **参数**：`view_date: str`，查询日期
- **规模提示**：单日返回全部主题×成分股明细（约十万行级），建议直接落盘（如 `to_parquet` / `to_csv`）后按 `theme_id` 过滤处理，不要整体打印

**返回样例**：

| theme_id              | stock_code | create_time         | delete_time |
| --------------------- | ---------- | ------------------- | ----------- |
| `1b9d818e…f50e804` | 002727.SZ  | 2018-01-31 23:30:00 | None        |
| `4bf5576e…c0f6236` | 300003.SZ  | 2018-01-31 23:30:00 | None        |
| `b47d4a32…491b517` | 000969.SZ  | 2018-01-31 23:30:00 | None        |

---

**`get_theme_classification_index_inc`**

- **调用方式**：`theme_classification.get_theme_classification_index_inc(view_date)`
- **功能简介**：主题指数点位日度增量数据
- **参数**：`view_date: str`，查询日期

**返回样例**：

| theme_id               | index_name        | index_external_code | price_date | close_price | upddate_time        |
| ---------------------- | ----------------- | ------------------- | ---------- | ----------- | ------------------- |
| `66f3c5b8…81ef14`   | 液冷超充_主题指数 | CIS05816            | "20260630" | 2795.85     | 2026-06-30 23:00:02 |
| `279d8e2d…10bf73b`  | 健康中国_主题指数 | CIS05451            | "20260630" | 929.5       | 2026-06-30 23:00:02 |
| `33f156e4…8d4bd29a` | 氢能_主题指数     | CIS05588            | "20260630" | 1653.0      | 2026-06-30 23:00:02 |

> `price_date` 为 `YYYYMMDD` 格式的字符串（如 `"20260630"`），并非整数。
>
> **列名拼写说明**：更新时间列的实际列名为 `upddate_time`（少一个 `a`，非 `update_time`）。这是服务端返回的真实列名，并非本手册笔误；脚本中按列名取该列时请使用 `upddate_time`，不要改成 `update_time`。该列仅出现在本接口（`get_theme_classification_index_inc`），`get_theme_classification_index_by_id` 不返回该列。

---

**`get_theme_classification_index_by_id`**

- **调用方式**：`theme_classification.get_theme_classification_index_by_id(theme_id)`
- **功能简介**：查询特定主题的历史指数点位
- **参数**：`theme_id: str`，主题 ID

**返回样例**：

| theme_id             | index_name        | index_external_code | price_date | close_price |
| -------------------- | ----------------- | ------------------- | ---------- | ----------- |
| `66f3c5b8…81ef14` | 液冷超充_主题指数 | CIS05816            | "20231101" | 1000.00     |
| `66f3c5b8…81ef14` | 液冷超充_主题指数 | CIS05816            | "20231102" | 976.71      |
| `66f3c5b8…81ef14` | 液冷超充_主题指数 | CIS05816            | "20231103" | 995.99      |

> `price_date` 为 `YYYYMMDD` 格式的字符串（如 `"20231101"`），并非整数。

### 4.3、板块指标库 `beta_indicator`

**`list_indicator_types`**

- **调用方式**：`beta_indicator.list_indicator_types()`
- **功能简介**：读取所有指标类型（如市盈率 PE、市净率 PB 等）
- **参数**：无

**返回样例**：

| indicator_type                             |
| ------------------------------------------ |
| 主题基础池下一年一致预测双周变化综合打分   |
| 主题基础池净利润下一年增速一致预测         |
| 主题基础池净利润下一年增速一致预测双周变化 |

---

**`list_indicators`**

- **调用方式**：`beta_indicator.list_indicators(indicator_type)`
- **功能简介**：按指标类型读取指标列表
- **参数**：`indicator_type: str`，指标类型名称

**返回样例**：

| indicator_id         | indicator_type | indicator_name                                                              | indicator_unit | indicator_frequency | indicator_caliber | indicator_related_sector_type | indicator_related_sector       | indicator_related_sector_code | update_time         |
| -------------------- | -------------- | --------------------------------------------------------------------------- | -------------- | ------------------- | ----------------- | ----------------------------- | ------------------------------ | ----------------------------- | ------------------- |
| `7023d2fa…38d76c` | 市盈率PE       | 市盈率PE__['ETF指数']__{'ETF指数': '000001.SH'}__…__当期__周__无单位 | 无单位         | 周                  | 当期              | `['ETF指数']`              | `{'ETF指数': '上证综合指数'}` | `{'ETF指数': '000001.SH'}` | 2026-02-12 13:37:38 |
| `e5527daa…425804` | 市盈率PE       | 市盈率PE__['ETF指数']__{'ETF指数': '000009.SH'}__…__当期__周__无单位 | 无单位         | 周                  | 当期              | `['ETF指数']`              | `{'ETF指数': '上证380指数'}`  | `{'ETF指数': '000009.SH'}` | 2026-02-12 13:37:38 |
| `97591188…31dd4a` | 市盈率PE       | 市盈率PE__['ETF指数']__{'ETF指数': '000010.SH'}__…__当期__周__无单位 | 无单位         | 周                  | 当期              | `['ETF指数']`              | `{'ETF指数': '上证180指数'}`  | `{'ETF指数': '000010.SH'}` | 2026-02-12 13:37:38 |

> `indicator_related_sector_type` 为 list 字符串，`indicator_related_sector` / `indicator_related_sector_code` 为 dict 字符串，描述该指标关联的板块。

---

**`get_indicator_value`**

- **调用方式**：`beta_indicator.get_indicator_value(indicator_id)`
- **功能简介**：按指标 ID 读取该指标全部数值记录
- **参数**：`indicator_id: str`，指标唯一标识

**返回样例**：

| data_id                          | indicator_id         | data_value | data_date  | data_publish_date   | update_time         |
| -------------------------------- | -------------------- | ---------- | ---------- | ------------------- | ------------------- |
| `7023d2fa…38d76c__2019-01-04` | `7023d2fa…38d76c` | 11.09      | 2019-01-04 | 2019-01-05 09:00:00 | 2026-02-12 13:37:38 |
| `7023d2fa…38d76c__2019-01-11` | `7023d2fa…38d76c` | 11.25      | 2019-01-11 | 2019-01-12 09:00:00 | 2026-02-12 14:07:26 |
| `7023d2fa…38d76c__2019-01-18` | `7023d2fa…38d76c` | 11.46      | 2019-01-18 | 2019-01-19 09:00:00 | 2026-02-12 14:44:34 |

> **注意：`data_date` 与 `data_publish_date` 含义不同，按日期过滤时切勿混淆。** `data_date` 是观测日期（指标值对应的市场/报告期日期）；`data_publish_date` 是发布日期（该条记录实际可得的日期），通常晚于 `data_date`（如上例 data_date=2019-01-04 的记录，发布日为 2019-01-05；年报类指标可能滞后数月）。CLI 的 `--start-date`/`--end-date` 即按 `data_publish_date` 过滤，自定义脚本自行过滤时也请注意口径（详见 `CLI_使用手册.md` 第 3.4 节）。

---

**`get_indicator_value_inc`**

- **调用方式**：`beta_indicator.get_indicator_value_inc(view_date)`
- **功能简介**：按日期增量读取所有指标值
- **参数**：`view_date: str`，查询日期

**返回样例**：

| data_id                          | indicator_id         | data_value    | data_date  | data_publish_date   | update_time         |
| -------------------------------- | -------------------- | ------------- | ---------- | ------------------- | ------------------- |
| `00014458…b8be4b__2026-08-14` | `00014458…b8be4b` | 18821959.0    | 2026-08-14 | 2026-08-14 00:00:00 | 2026-08-17 12:01:36 |
| `0002e4db…f5c437__2026-08-14` | `0002e4db…f5c437` | 66757527744.0 | 2026-08-14 | 2026-08-14 00:00:00 | 2026-08-17 12:01:36 |
| `00035dc7…676c90__2026-08-14` | `00035dc7…676c90` | 0.0           | 2026-08-14 | 2026-08-14 00:00:00 | 2026-08-17 12:01:41 |

---

**`list_sector_types`**

- **调用方式**：`beta_indicator.list_sector_types()`
- **功能简介**：读取所有板块类型（如 ETF 指数、中信证券行业等）
- **参数**：无

> **注意（衍生接口的 `update_time` 语义）**：`list_indicators_by_sector_type` / `list_indicators_by_sector` 等衍生接口基于 SDK 本地全量缓存快照实现，其返回的 `update_time` 是**本地缓存重建时间**，并非后端数据更新时间；与原子接口（如 `list_indicators`、`get_indicator_value`）返回的后端 `update_time` 含义不同，请勿混用。本 skill 的 CLI 已对缓存类命令统一剔除该列。

**返回样例**：

| sector_type  |
| ------------ |
| ETF指数      |
| 中信证券行业 |
| 主题概念     |

---

**`list_sectors`**

- **调用方式**：`beta_indicator.list_sectors(sector_type=None)`
- **功能简介**：读取板块列表，可选按板块类型过滤
- **参数**：`sector_type: str | None`，传 `None` 返回全部

**返回样例**（`sector_type="ETF指数"`）：

| sector_type | sector_code | sector_name  |
| ----------- | ----------- | ------------ |
| ETF指数     | 000001.SH   | 上证综合指数 |
| ETF指数     | 000009.SH   | 上证380指数  |
| ETF指数     | 000010.SH   | 上证180指数  |

---

**`list_indicators_by_sector_type`**

- **调用方式**：`beta_indicator.list_indicators_by_sector_type(sector_type)`
- **功能简介**：按板块类型读取该板块类型的全部指标列表
- **参数**：`sector_type: str`，板块类型名称（如 `中信证券行业`）
- **规模提示**：返回该板块类型下"指标×板块"的展开结果（数万~十万行级，如中信证券行业约 3 万行），建议落盘后按 `sector_code` / `indicator_type` 过滤处理；查询单个板块的指标请改用 `list_indicators_by_sector`

**返回样例**（`sector_type="中信证券行业"`）：

| indicator_type                             | sector_type  | sector_code | sector_name | indicator_id   | indicator_unit | indicator_frequency | update_time         |
| ------------------------------------------ | ------------ | ----------- | ----------- | -------------- | -------------- | ------------------- | ------------------- |
| 主题基础池净利润下一年增速一致预测双周变化 | 中信证券行业 | 10          | 石油石化    | `4294331d…` | %              | 周                  | 2026-08-31 09:33:02 |
| 主题基础池净利润下一年增速一致预测双周变化 | 中信证券行业 | 1010        | 石油开采Ⅱ  | `6aeecb1c…` | %              | 周                  | 2026-08-31 09:33:02 |
| 主题基础池净利润下一年增速一致预测双周变化 | 中信证券行业 | 101010      | 石油开采Ⅲ  | `a628e746…` | %              | 周                  | 2026-08-31 09:33:02 |

---

**`list_indicators_by_sector`**

- **调用方式**：`beta_indicator.list_indicators_by_sector(sector_code)`
- **功能简介**：按板块代码读取该板块全部指标列表
- **参数**：`sector_code: str`，板块代码（如 `000001.SH`）

**返回样例**（`sector_code="000001.SH"`）：

| indicator_type                             | sector_type | sector_code | sector_name  | indicator_id         | indicator_unit | indicator_frequency | update_time         |
| ------------------------------------------ | ----------- | ----------- | ------------ | -------------------- | -------------- | ------------------- | ------------------- |
| 主题基础池净利润下一年增速一致预测双周变化 | ETF指数     | 000001.SH   | 上证综合指数 | `831a95f5…be227f` | %              | 周                  | 2026-08-19 10:26:12 |
| 主题基础池净利润下一年增速一致预测         | ETF指数     | 000001.SH   | 上证综合指数 | `45168a2f…adbe83` | %              | 周                  | 2026-08-19 10:26:12 |
| 主题基础池下一年一致预测双周变化综合打分   | ETF指数     | 000001.SH   | 上证综合指数 | `f05d2290…4aefee` | %              | 周                  | 2026-08-19 10:26:12 |

---

**`get_indicator_value_batch`**

- **调用方式**：`beta_indicator.get_indicator_value_batch(indicator_ids, max_workers=3)`
- **功能简介**：并发批量读取多个指标的数值记录
- **参数**：`indicator_ids: list[str]`，指标 ID 列表（≤30）；`max_workers: int`，最大并发数，默认 3

**返回样例**：

```text
{
  "f05d2290…4aefee": DataFrame(398 行 × 6 列),
  "831a95f5…be227f": DataFrame(398 行 × 6 列)
}
```

其中 `f05d2290…4aefee` 前 3 行：

| data_id                          | indicator_id         | data_value | data_date  | data_publish_date   | update_time         |
| -------------------------------- | -------------------- | ---------- | ---------- | ------------------- | ------------------- |
| `f05d2290…4aefee__2019-01-04` | `f05d2290…4aefee` | -0.24      | 2019-01-04 | 2019-01-04 00:00:00 | 2026-02-12 13:34:27 |
| `f05d2290…4aefee__2019-01-11` | `f05d2290…4aefee` | -0.22      | 2019-01-11 | 2019-01-11 00:00:00 | 2026-02-12 14:04:43 |
| `f05d2290…4aefee__2019-01-18` | `f05d2290…4aefee` | 0.11       | 2019-01-18 | 2019-01-18 00:00:00 | 2026-02-12 14:42:35 |

> 返回类型：`get_indicator_value_batch` 返回 `dict[str, DataFrame | None]`（key 为指标 ID；仅请求级失败对应 `None`，指标 ID 不存在或暂无数据时返回空 `DataFrame`），其余均返回 `DataFrame`。

---

**`get_indicator_value_by_type_and_sector`**

- **调用方式**：`beta_indicator.get_indicator_value_by_type_and_sector(indicator_type, sector_type)`
- **功能简介**：根据指标类型和板块类型，读取所有板块的历史指标值
- **参数**：`indicator_type: str`，指标类型名称；`sector_type: str`，板块类型名称（如 `ETF指数`）
- **规模提示**：返回所有板块的全量历史（数万行级以上），建议落盘后按 `indicator_related_sector_code` / 日期窗口过滤处理；仅需最新一期截面请改用 `get_indicator_value_latest_by_type_and_sector`，仅需单指标时序请改用 `get_indicator_value`

**返回样例**：

| data_id              | indicator_id         | indicator_related_sector_code | indicator_related_sector        | data_value | data_date  | data_publish_date   | update_time         |
| -------------------- | -------------------- | ----------------------------- | ------------------------------- | ---------- | ---------- | ------------------- | ------------------- |
| `7023d2fa…38d76c` | `7023d2fa…38d76c` | `{'ETF指数': '000001.SH'}`  | `{'ETF指数': '上证综合指数'}` | 11.09      | 2019-01-04 | 2019-01-05 09:00:00 | 2026-02-12 13:37:38 |
| `7023d2fa…38d76c` | `7023d2fa…38d76c` | `{'ETF指数': '000001.SH'}`  | `{'ETF指数': '上证综合指数'}` | 11.25      | 2019-01-11 | 2019-01-12 09:00:00 | 2026-02-12 14:07:26 |
| `7023d2fa…38d76c` | `7023d2fa…38d76c` | `{'ETF指数': '000001.SH'}`  | `{'ETF指数': '上证综合指数'}` | 11.46      | 2019-01-18 | 2019-01-19 09:00:00 | 2026-02-12 14:44:34 |

---

**`get_indicator_value_latest_by_type_and_sector`**

- **调用方式**：`beta_indicator.get_indicator_value_latest_by_type_and_sector(indicator_type, sector_type)`
- **功能简介**：根据指标类型和板块类型，读取所有板块的最新一期指标值
- **参数**：`indicator_type: str`，指标类型名称；`sector_type: str`，板块类型名称（如 `ETF指数`）

**返回样例**：

| data_id              | indicator_id         | indicator_related_sector_code | indicator_related_sector        | data_value | data_date  | data_publish_date   | update_time         |
| -------------------- | -------------------- | ----------------------------- | ------------------------------- | ---------- | ---------- | ------------------- | ------------------- |
| `7023d2fa…38d76c` | `7023d2fa…38d76c` | `{'ETF指数': '000001.SH'}`  | `{'ETF指数': '上证综合指数'}` | 16.94      | 2026-08-28 | 2026-08-29 09:00:00 | 2026-08-29 10:27:44 |
| `e5527daa…425804` | `e5527daa…425804` | `{'ETF指数': '000009.SH'}`  | `{'ETF指数': '上证380指数'}`  | 30.77      | 2026-08-28 | 2026-08-29 09:00:00 | 2026-08-29 10:27:44 |
| `97591188…31dd4a` | `97591188…31dd4a` | `{'ETF指数': '000010.SH'}`  | `{'ETF指数': '上证180指数'}`  | 12.27      | 2026-08-28 | 2026-08-29 09:00:00 | 2026-08-29 10:27:44 |

### 4.4、文本库 `text_analysis`

**`get_information_ai_report_market_daily`**

- **调用方式**：`text_analysis.get_information_ai_report_market_daily(start_date, end_date)`
- **功能简介**：根据时间范围读取市场日报文本
- **参数**：`start_date: str`，开始日期；`end_date: str`，结束日期

**返回样例**：

| data_id | insert_time         | update_time         | view_date  | report                                   |
| ------- | ------------------- | ------------------- | ---------- | ---------------------------------------- |
| 288     | 2026-07-15 22:27:27 | 2026-07-22 09:06:33 | 2026-06-30 | "\n# AI日度市场简报（2026-06-30）…" |

> `report` 为完整的 Markdown 文本（此处截断展示）；每行代表一条日报记录。
>
> **排序说明**：返回记录按 `view_date` 降序排列（最新一期在最前）。因此"取最新一期报告"无需传宽日期区间试探，直接取返回的第一行即可（本 skill 的 CLI `get-market-daily-report` 命令已提供 `--last-n` 参数，可直接取最新 N 期）。

---

**`get_information_ai_report_strategy_weekly`**

- **调用方式**：`text_analysis.get_information_ai_report_strategy_weekly(start_date, end_date)`
- **功能简介**：根据时间范围读取策略周报文本
- **参数**：`start_date: str`，开始日期；`end_date: str`，结束日期

**返回样例**（字段与市场日报一致）：

| data_id | insert_time         | update_time         | view_date  | report                             |
| ------- | ------------------- | ------------------- | ---------- | ---------------------------------- |
| 2       | 2026-07-16 21:11:15 | 2026-07-22 23:21:44 | 2026-06-28 | "\n# 国内权益市场后市展望…" |

> 排序说明同市场日报：返回记录按 `view_date` 降序排列（最新一期在最前）。

> 说明：SDK 中还存在内部接口 `get_information_ai_extract_ticker_notes_flow`（ETF 信息文本），本手册**暂不收录**：其 `notes_type` 合法取值未公开，传入任意取值都会静默返回空结果且无法排障。请勿在生产脚本中使用该接口；待数据方补充取值枚举与确认返回结构后，再补充使用文档。

## 5、依赖

- Python >= 3.10
- pandas、pyarrow、requests、tqdm

> 缓存说明：SDK 会在用户缓存目录（`~/.cache/aibeta/`）维护指标库的全量快照缓存，默认每 3 天自动重建一次。SDK 本身未提供缓存目录配置入口；`~/.cache` 不可写或需目录隔离时，可设置环境变量 `AIBETA_CACHE_DIR` 重定向（本 skill 的 CLI `ai-beta` 已支持该变量，支持 `~` 与 `$VAR` 展开），直接使用 Python SDK 的自定义脚本不受该变量控制。

## 6、板块指标库覆盖指标列表

指标持续扩充中，以下指标数据统计截止 2026-08-19 。

| 指标分类                                        | 指标名称                                   |
| ----------------------------------------------- | ------------------------------------------ |
| 板块_宏观面_状态_宏观敏感度                     | 宏观敏感度                                 |
| 板块_景气面_中观景气度_景气度                   | 景气度                                     |
| 板块_基本面_估值_股债相对盈利收益率             | 股债相对盈利收益率                         |
| 板块_基本面_估值_周度PEPBPS                     | 市盈率PE                                   |
| 板块_基本面_估值_周度PEPBPS                     | 市净率PB                                   |
| 板块_基本面_估值_周度PEPBPS                     | 市销率PS                                   |
| 板块_基本面_预期_上市公司年报预期乐观度         | 主题基础池企业年报展望乐观度               |
| 板块_情绪面_主题关注度_Choice热度指数统计       | 板块个股访问指数                           |
| 板块_情绪面_主题关注度_Choice热度指数统计       | 板块社区活跃指数                           |
| 板块_情绪面_主题关注度_Choice热度指数统计       | 板块新闻阅读指数                           |
| 板块_情绪面_主题关注度_Choice热度指数统计       | 板块公告阅读指数                           |
| 板块_情绪面_主题关注度_Choice热度指数统计       | 板块研报阅读指数                           |
| 板块_技术面_价格_MACD                           | MACD-DIF线                                 |
| 板块_技术面_价格_MACD                           | MACD-DEA线                                 |
| 板块_技术面_价格_MACD                           | MACD-柱状图                                |
| 板块_技术面_价格_RSI                            | RSI                                        |
| 板块_技术面_价格_周度涨跌幅统计                 | 近1周涨跌幅                                |
| 板块_技术面_价格_周度涨跌幅统计                 | 近4周涨跌幅                                |
| 板块_技术面_价格_周度涨跌幅统计                 | 本年度涨跌幅                               |
| 板块_技术面_价格_均线指标                       | 1日均线                                    |
| 板块_技术面_价格_均线指标                       | 5日均线                                    |
| 板块_技术面_价格_均线指标                       | 10日均线                                   |
| 板块_技术面_价格_均线指标                       | 20日均线                                   |
| 板块_技术面_价格_均线指标                       | 60日均线                                   |
| 板块_技术面_成交量_当日成交量                   | 当日成交量                                 |
| 板块_技术面_成交量_当日成交量                   | 当日成交金额                               |
| 板块_技术面_拥挤度_主题交易拥挤度               | 交易拥挤度指标                             |
| 板块_技术面_热度_主题交易热度                   | 交易热度指标                               |
| 板块_报告_算法决策_收入一致预测双周变化         | 主题基础池净利润下一年增速一致预测         |
| 板块_报告_算法决策_收入一致预测双周变化         | 主题基础池营收下一年增速一致预测           |
| 板块_报告_算法决策_收入一致预测双周变化         | 主题基础池净利润下一年增速一致预测双周变化 |
| 板块_报告_算法决策_收入一致预测双周变化         | 主题基础池营收下一年增速一致预测双周变化   |
| 板块_报告_算法决策_收入一致预测双周变化         | 主题基础池下一年一致预测双周变化综合打分   |
| 板块_报告_算法决策_政策文本提及热度             | 政策提及热度                               |
| 板块_报告_算法决策_机构调研热度                 | 主题基础池机构调研综合热度                 |
| 板块_报告_算法决策_研报情绪综合得分             | 主题基础池研报情绪综合得分                 |
| 板块_政策面_情绪_政策新闻情绪                   | 政策情绪                                   |
| 板块_资金面_ETF资金_ETF净值变化对板块的影响拆解 | ETF资金影响                                |
| 板块_资金面_两融资金_板块融资融券统计           | 融资余额                                   |
| 板块_资金面_两融资金_板块融资融券统计           | 融资买入额                                 |
| 板块_资金面_两融资金_板块融资融券统计           | 融资偿还额                                 |
| 板块_资金面_两融资金_板块融资融券统计           | 融券余额                                   |
| 板块_资金面_两融资金_板块融资融券统计           | 融券卖出额                                 |
| 板块_资金面_两融资金_板块融资融券统计           | 融券偿还额                                 |
| 板块_风险_风险偏好_收益波动秩相关系数           | 近20交易日收益与波动秩相关系数             |
| 板块_基本面_财务_主题基本财务指标               | 净利润TTM                                  |
| 板块_基本面_财务_主题基本财务指标               | 营业总收入TTM                              |
| 板块_基本面_财务_主题基本财务指标               | 营业总成本TTM                              |
| 板块_基本面_财务_主题基本财务指标               | 营业利润TTM                                |
| 板块_基本面_财务_主题基本财务指标               | 资产总计                                   |
| 板块_基本面_财务_主题基本财务指标               | 应收账款                                   |
| 板块_基本面_财务_主题基本财务指标               | 存货                                       |
| 板块_基本面_财务_主题基本财务指标               | 流动资产合计                               |
| 板块_基本面_财务_主题基本财务指标               | 流动负债合计                               |
| 板块_基本面_财务_主题基本财务指标               | 负债合计                                   |
| 板块_基本面_财务_主题基本财务指标               | 经营活动现金流入小计                       |
| 板块_基本面_财务_主题基本财务指标               | 经营活动现金流出小计                       |
| 板块_基本面_财务_主题基本财务指标               | 当日净资产                                 |
| 板块_基本面_财务_主题基本财务指标               | 企业自由现金流FCFF                         |
| 板块_基本面_财务_主题基本财务指标               | 总市值                                     |
| 板块_基本面_财务_主题基本财务指标               | 近12个月股息率                             |
| 板块_基本面_财务_主题基本财务指标               | 净资产收益率ROE                            |
| 板块_基本面_财务_主题基本财务指标               | 资产回报率ROA                              |
| 板块_基本面_财务_主题基本财务指标               | 毛利率                                     |
| 板块_基本面_财务_主题基本财务指标               | 净利率                                     |
| 板块_基本面_财务_主题基本财务指标               | 经营活动现金流净额                         |
| 板块_基本面_财务_主题基本财务指标               | 资产负债率                                 |
| 板块_基本面_财务_主题基本财务指标               | 流动比率                                   |
| 板块_基本面_财务_主题基本财务指标               | 速动比率                                   |
| 板块_基本面_财务_主题基本财务指标               | 营业收入增长率                             |
| 板块_基本面_财务_主题基本财务指标               | 净利润增长率                               |
| 板块_基本面_财务_主题基本财务指标               | 自由流通市值加权EPS                        |
| 板块_基本面_财务_主题基本财务指标               | 营业利润增长率                             |
| 板块_基本面_财务_主题基本财务指标               | 总资产周转率                               |
| 板块_基本面_财务_主题基本财务指标               | 应收账款周转率                             |
| 板块_基本面_财务_主题基本财务指标               | 存货周转率                                 |
