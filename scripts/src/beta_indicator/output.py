"""输出工具层：时间窗口裁剪与 JSON 序列化。"""

from __future__ import annotations

import ast
from contextlib import contextmanager
from datetime import date, datetime
import json
import re
import sys
from typing import Any

import pandas as pd

# SDK 返回的板块关联字段（dict / list 字符串）→ 标准列名
RELATED_SECTOR_COLUMN_MAP = {
    "indicator_related_sector_type": "sector_type",
    "indicator_related_sector_code": "sector_code",
    "indicator_related_sector": "sector_name",
    "indicator_related_sector_name": "sector_name",
}

# 失效图片引用形态：markdown 行内图片 ![alt](url) 与 HTML img 标签
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_IMAGE_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)


@contextmanager
def redirect_stdout_to_stderr():
    """临时把 Python 层 stdout 重定向到 stderr。

    aibeta SDK 内部的分页读取、缓存重建等流程可能直接 ``print()`` 进度信息
    到 stdout；CLI 在调用 SDK 期间启用本重定向，保证 stdout 始终只输出
    最终 JSON 结果，进度提示进入 stderr。
    """
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = real_stdout


def to_json_safe(value: Any) -> Any:
    """将常见的 pandas / datetime 值转换成可 JSON 序列化的对象。"""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value


def _literal_or_raw(value: Any) -> Any:
    """dict / list 字符串解析成 Python 对象；解析失败或非字符串则原样返回。"""
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    return value


def _single_value(value: Any) -> Any:
    """dict 取第一个值；list 取第一个元素；其余原样返回。"""
    if isinstance(value, dict):
        return next(iter(value.values()), None)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def normalize_related_sector_columns(df: pd.DataFrame) -> pd.DataFrame:
    """把 indicator_related_* 的 dict / list 字符串列解析为标准三列并删除原始列。

    - ``sector_type``：优先取 ``indicator_related_sector_type``（list 字符串取首元素）；
      缺失时从 ``indicator_related_sector_code`` 的 dict key 推导（如 ``{'ETF指数': '000001.SH'}``）。
    - ``sector_code`` / ``sector_name``：取对应 dict 的 value。
    - 新列插入在原第一列的位置，保持输出字段顺序稳定。
    """
    present_columns = [c for c in df.columns if c in RELATED_SECTOR_COLUMN_MAP]
    if not present_columns:
        return df

    result_df = df.copy()
    parsed = {c: result_df[c].map(_literal_or_raw) for c in present_columns}
    insert_at = df.columns.get_loc(present_columns[0])

    if "indicator_related_sector_type" in parsed:
        sector_type = parsed["indicator_related_sector_type"].map(_single_value)
    elif "indicator_related_sector_code" in parsed:
        sector_type = parsed["indicator_related_sector_code"].map(
            lambda v: next(iter(v), None) if isinstance(v, dict) else None
        )
    else:
        sector_type = pd.Series(None, index=df.index, dtype=object)
    if "indicator_related_sector_code" in parsed:
        sector_code = parsed["indicator_related_sector_code"].map(_single_value)
    else:
        sector_code = pd.Series(None, index=df.index, dtype=object)
    if "indicator_related_sector" in parsed:
        sector_name = parsed["indicator_related_sector"].map(_single_value)
    elif "indicator_related_sector_name" in parsed:
        sector_name = parsed["indicator_related_sector_name"].map(_single_value)
    else:
        sector_name = pd.Series(None, index=df.index, dtype=object)

    result_df = result_df.drop(columns=present_columns)
    for offset, (name, series) in enumerate(
        [("sector_type", sector_type), ("sector_code", sector_code), ("sector_name", sector_name)]
    ):
        result_df.insert(min(insert_at + offset, len(result_df.columns)), name, series)
    return result_df


def drop_cache_update_time(df: pd.DataFrame) -> pd.DataFrame:
    """剔除缓存类接口结果中的 ``update_time`` 列（若存在）。

    SDK 衍生接口（list_sector_types / list_sectors / list_indicators_by_sector
    等）基于本地全量缓存快照实现，其 ``update_time`` 是缓存重建时间，并非
    后端数据更新时间；为避免与原子接口（如 list_indicators）返回的后端
    ``update_time`` 混淆，缓存类命令统一不输出该列。
    """
    if "update_time" in df.columns:
        return df.drop(columns=["update_time"])
    return df


def normalize_theme_index_dates(
    df: pd.DataFrame, column: str = "price_date"
) -> pd.DataFrame:
    """把主题指数的 ``price_date``（YYYYMMDD 格式字符串）统一输出为 ISO 日期字符串（YYYY-MM-DD）。"""
    if column not in df.columns or df.empty:
        return df
    result_df = df.copy()
    parsed_dates = _parse_date_column(result_df[column], column)
    result_df[column] = parsed_dates.dt.strftime("%Y-%m-%d")
    return result_df


def strip_image_references_from_text(text: str) -> str:
    """删除单个字符串中的图片引用（markdown 行内图片与 HTML img 标签）。"""
    cleaned = MARKDOWN_IMAGE_PATTERN.sub("", text)
    return HTML_IMAGE_PATTERN.sub("", cleaned)


def strip_image_references(df: pd.DataFrame) -> pd.DataFrame:
    """移除文本类 DataFrame 所有字符串单元格中的图片引用。

    报告正文里的图片指向服务端内部路径（如 /home/user/project_set/...png），
    用户端无法访问，属于失效引用：统一删除，避免内部路径泄漏与输出膨胀。
    列名以服务端实际返回为准，故对所有字符串列生效。
    """
    if df.empty:
        return df
    result_df = df.copy()
    for column in result_df.columns:
        is_str = result_df[column].map(lambda value: isinstance(value, str))
        if not is_str.any():
            continue
        result_df.loc[is_str, column] = result_df.loc[is_str, column].map(
            strip_image_references_from_text
        )
    return result_df


def dataframe_to_jsonable(df: pd.DataFrame) -> list[dict[str, Any]]:
    """将 DataFrame 转成可安全输出的 JSON 结构（datetime 转 ISO 字符串，NaN 转 null）。"""
    normalized_df = normalize_related_sector_columns(df)
    normalized_df = normalized_df.astype(object).where(pd.notna(normalized_df), None)
    records = normalized_df.to_dict(orient="records")
    return [
        {key: to_json_safe(value) for key, value in record.items()}
        for record in records
    ]


def batch_result_to_jsonable(
    results: dict[str, pd.DataFrame | None]
) -> dict[str, list[dict[str, Any]] | None]:
    """将批量接口结果转成可安全输出的 JSON 结构。"""
    return {
        indicator_id: None if df is None else dataframe_to_jsonable(df)
        for indicator_id, df in results.items()
    }


# 日期入参强制要求的格式：YYYY-MM-DD（严格校验，拒绝 20260901、2026/12/31 等宽松写法）
STRICT_DATE_FORMAT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_date_input(value: Any, field_name: str) -> pd.Timestamp | None:
    """将日期入参标准化为按天比较的 Timestamp。

    字符串入参统一强制 YYYY-MM-DD 严格校验：即使 pandas 可宽松解析的写法
    （如 20260901、2026/12/31）也一律报错，避免静默接受造成日期口径歧义。
    """
    if value is None:
        return None
    if isinstance(value, str):
        if not STRICT_DATE_FORMAT_PATTERN.fullmatch(value.strip()):
            raise ValueError(
                f"{field_name} 必须是 YYYY-MM-DD 格式的日期"
                "（严格校验，不支持 20260901、2026/12/31 等写法），例如 2024-01-31；"
                f"收到：{value!r}"
            )
        value = value.strip()
    try:
        normalized = pd.to_datetime(
            value, format="%Y-%m-%d" if isinstance(value, str) else None, errors="raise"
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} 不是合法的日历日期（YYYY-MM-DD），例如 2024-01-31；收到：{value!r}"
        ) from exc
    if pd.isna(normalized):
        raise ValueError(f"{field_name} 不能为空日期")
    return normalized.normalize()


def trim_timeseries_window(
    df: pd.DataFrame,
    *,
    date_column: str,
    last_n: int | None = None,
    start_date: str | date | datetime | pd.Timestamp | None = None,
    end_date: str | date | datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """按日期区间与最近 N 条规则裁剪时序结果。

    - ``date_column``：用于过滤的日期列（指标类时序为 ``data_publish_date``，主题指数为 ``price_date``）。
    - ``start_date`` / ``end_date``：均为包含边界。
    - ``last_n``：组合使用时：先按日期区间过滤，再截取最后 ``last_n`` 条。
    """
    if last_n is not None and (
        isinstance(last_n, bool) or not isinstance(last_n, int) or last_n <= 0
    ):
        raise ValueError("last_n 必须是正整数")

    normalized_start = normalize_date_input(start_date, "start_date")
    normalized_end = normalize_date_input(end_date, "end_date")
    if (
        normalized_start is not None
        and normalized_end is not None
        and normalized_start > normalized_end
    ):
        raise ValueError("start_date 不能晚于 end_date")

    result_df = df
    if normalized_start is not None or normalized_end is not None:
        if date_column not in df.columns:
            raise ValueError(
                f"当前时序结果中缺少 {date_column} 字段，"
                f"现有列为：{', '.join(map(str, df.columns.tolist()))}"
            )
        # 归一到日级（00:00:00），与 normalize_date_input 对齐；否则 --end-date 边界
        # 会因 data_publish_date 带时分秒（如 09:00:00）而被 <= 排除，导致当天记录丢失。
        date_series = _parse_date_column(df[date_column], date_column).dt.normalize()

        date_mask = pd.Series(True, index=df.index)
        if normalized_start is not None:
            date_mask &= date_series >= normalized_start
        if normalized_end is not None:
            date_mask &= date_series <= normalized_end
        result_df = df.loc[date_mask]

    if last_n is not None:
        result_df = result_df.tail(last_n)
    return result_df.reset_index(drop=True)


def _parse_date_column(series: pd.Series, date_column: str) -> pd.Series:
    """解析日期列；数值列（如 20231101）按 YYYYMMDD 解析，避免被误判为纳秒时间戳。"""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_datetime(
            series.astype("Int64").astype(str), format="%Y%m%d", errors="raise"
        )
    try:
        return pd.to_datetime(series, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"列 {date_column} 不是合法的 datetime，无法执行时间窗口过滤"
        ) from exc


def order_reports_latest_first(
    df: pd.DataFrame,
    last_n: int | None = None,
    date_column: str = "view_date",
) -> pd.DataFrame:
    """报告类结果按 ``view_date`` 降序排序（最新在前）；``last_n`` 给定时仅保留最新 N 期。

    - SDK 侧报告按 ``view_date`` 降序返回（最新在前），这里显式排序一次，
      保证输出顺序确定、不依赖 SDK 内部实现；
    - 单篇报告文本可达数十 KB，"取最新 N 期"是高频诉求，对应 ``last_n``。
    """
    if date_column not in df.columns:
        raise ValueError(
            f"当前报告结果中缺少 {date_column} 字段，"
            f"现有列为：{', '.join(map(str, df.columns.tolist()))}"
        )
    sort_column = f"__{date_column}_sort_key"
    keyed_df = df.assign(
        **{sort_column: _parse_date_column(df[date_column], date_column)}
    )
    ordered_df = (
        keyed_df.sort_values(sort_column, ascending=False, kind="stable")
        .drop(columns=[sort_column])
        .reset_index(drop=True)
    )
    if last_n is not None:
        ordered_df = ordered_df.head(last_n).reset_index(drop=True)
    return ordered_df


def print_json(data: Any, *, compact: bool = False) -> None:
    """将结果以 JSON 格式输出到标准输出。

    ``compact=True`` 时输出无缩进单行 JSON（体积最小，适合重定向落盘供程序处理）；
    默认 indent=2，便于人工阅读与 diff。
    """
    json.dump(
        data,
        sys.stdout,
        ensure_ascii=False,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
    )
    sys.stdout.write("\n")


def print_error(message: str) -> None:
    """将错误信息输出到标准错误。"""
    sys.stderr.write(f"{message.rstrip()}\n")
