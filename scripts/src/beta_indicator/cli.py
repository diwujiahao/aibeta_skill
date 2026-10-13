"""ai_beta_skill 的单一 CLI 入口（命令名 ai-beta，基于 aibeta SDK）。"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Callable
from typing import Any

import aibeta
import pandas as pd

from .doctor import run_doctor
from .output import (
    batch_result_to_jsonable,
    dataframe_to_jsonable,
    drop_cache_update_time,
    normalize_date_input,
    normalize_theme_index_dates,
    order_reports_latest_first,
    print_error,
    print_json,
    redirect_stdout_to_stderr,
    strip_image_references,
    trim_timeseries_window,
)
from .plot import DEFAULT_MA_WINDOWS, PLOT_DATE_WINDOW_NOTE, parse_ma_windows
from .runtime import apply_cache_dir_override

# 未传任何时间窗口参数时，时序命令默认仅保留最后 N 条记录，避免全量历史撑爆输出
DEFAULT_LAST_N = 25
# 指标类时序结果的日期过滤列
INDICATOR_DATE_COLUMN = "data_publish_date"
# 主题指数结果的日期过滤列
THEME_INDEX_DATE_COLUMN = "price_date"
# 报告类结果的日期列（排序口径）
REPORT_DATE_COLUMN = "view_date"
# 报告类命令未传任何参数时默认取最新 N 期
REPORT_DEFAULT_LAST_N = 1
# 报告类命令仅传 --last-n 时的默认取数起点（宽区间取数后本地截取最新 N 期）
REPORT_DEFAULT_START_DATE = "2018-01-01"
# 指标类时序 --start-date/--end-date 的日期口径警示：过滤的是发布日而非观测日
INDICATOR_DATE_WINDOW_NOTE = (
    "注意：日期区间按 data_publish_date（发布日期）过滤，而非 data_date（观测日期）；"
    "data_publish_date 通常晚于 data_date，"
    "如 data_date=2019-01-04 的记录其 data_publish_date 为 2019-01-05，"
    "按“数据日期”直觉过滤会得到偏移结果，建议优先使用 --last-n 控制范围。"
)
# 主题指数 --start-date/--end-date 的日期口径说明
THEME_INDEX_DATE_WINDOW_NOTE = "日期区间按指数价格日期 price_date 过滤。"
# 批量查询允许的最大指标数量
BATCH_MAX_INDICATORS = 30
# 结果记录数超过该阈值时，stderr 附加"建议落盘 / 缩小范围"提示
LARGE_OUTPUT_THRESHOLD = 1000
# 各命令空结果的排障提示：按命令类别定制，引导下一步动作
# （报告类→调整日期区间；主题类→查 framework / 调整日期；指标类→查 list-* 确认取值）
EMPTY_RESULT_HINTS: dict[str, str] = {
    # 指标 / 板块类
    "list-indicator-types": "提示：查询结果为空。指标类型列表为空通常是缓存或网络异常，可重试后再确认。",
    "list-sector-types": "提示：查询结果为空。板块类型列表为空通常是缓存或网络异常，可重试后再确认。",
    "list-indicators": (
        "提示：查询结果为空。可先运行 list-indicator-types 确认指标类型取值；"
        "若已带 --sector-type / --keyword 过滤，可放宽过滤条件后重试。"
    ),
    "list-sectors": (
        "提示：查询结果为空。可先运行 list-sector-types 确认板块类型取值；"
        "若已带过滤参数，可放宽 --keyword / --sector-code / --sector-name 后重试。"
    ),
    "list-indicators-by-sector": (
        "提示：查询结果为空。sector_code 可能不存在，可先运行 list-sectors 查看可用板块代码。"
    ),
    "get-indicator-value-latest-by-type-and-sector": (
        "提示：查询结果为空。可先运行 list-indicator-types / list-sector-types "
        "确认指标类型与板块类型的可用取值。"
    ),
    # 主题类
    "get-theme-framework-daily": (
        "提示：查询结果为空。可尝试调整 --view-date（如改用近期交易日）后重试。"
    ),
    # 报告类
    "get-market-daily-report": (
        "提示：查询结果为空。报告数据仅覆盖有限的日期区间，"
        "可尝试调整 --start-date / --end-date（如改用近期日期）后重试。"
    ),
    "get-strategy-weekly-report": (
        "提示：查询结果为空。报告数据仅覆盖有限的日期区间，"
        "可尝试调整 --start-date / --end-date（如改用近期日期）后重试。"
    ),
}
# 时序取值命令“取值不存在”（服务端未返回数据）时的定制提示，由 trim_indicator_series
# 随未返回数据的报错一并输出；窗口过滤后为空的场景不适用，故与 EMPTY_RESULT_HINTS 分开
VALUE_NOT_FOUND_HINTS: dict[str, str] = {
    "get-indicator-value": "提示：indicator_id 可能不存在，可先运行 list-indicators 查找正确的指标 ID。",
    "get-theme-index": "提示：theme_id 可能不存在，可先运行 get-theme-framework-daily 获取有效的 theme_id。",
}


def add_time_window_arguments(
    parser: argparse.ArgumentParser,
    *,
    last_n_help: str | None = None,
    date_window_note: str | None = None,
) -> None:
    """为时序查询命令补充统一的时间窗口参数。

    ``date_window_note`` 用于在 --start-date/--end-date 帮助文本中
    醒目标注该命令的日期过滤口径（指标类为发布日，主题指数为价格日）。
    """
    parser.add_argument(
        "--last-n",
        type=int,
        required=False,
        help=last_n_help
        or "【推荐】仅保留最后 N 条记录，无日期口径歧义；结合数据频率可直观换算"
        "历史跨度（周频 N=52 约一年，日频 N=250 约一年）。"
        "若同时传入日期区间，则在区间过滤后再截取最后 N 条。",
    )
    note = date_window_note or ""
    parser.add_argument(
        "--start-date",
        required=False,
        help=f"起始日期（含边界），严格 YYYY-MM-DD 格式，如 2024-01-31；"
        f"非法格式（如 20260901）直接报错。{note}",
    )
    parser.add_argument(
        "--end-date",
        required=False,
        help=f"结束日期（含边界），严格 YYYY-MM-DD 格式，如 2024-12-31；"
        f"非法格式（如 2026/12/31）直接报错。{note}",
    )


def resolve_time_window(args: argparse.Namespace) -> dict[str, Any]:
    """解析时间窗口参数；未传入任何窗口参数时默认只保留最后 25 条。"""
    window: dict[str, Any] = {
        "last_n": args.last_n,
        "start_date": args.start_date,
        "end_date": args.end_date,
    }
    if args.last_n is None and args.start_date is None and args.end_date is None:
        window["last_n"] = DEFAULT_LAST_N
    return window


def trim_indicator_series(
    df: pd.DataFrame,
    args: argparse.Namespace,
    *,
    date_column: str = INDICATOR_DATE_COLUMN,
    empty_label: str = "查询结果",
    not_found_hint: str | None = None,
) -> pd.DataFrame:
    """对时序查询结果应用统一的时间窗口裁剪。

    先于窗口过滤检测空 DataFrame，区分“取值不存在或暂无数据”与
    “窗口过滤后无剩余”，两者语义不同、退出码也不同：

    - 取值不存在或暂无数据：抛出 ``ValueError``（附 ``not_found_hint``），
      由 main 统一输出到 stderr 并以非零退出码结束，stdout 不输出 JSON。
      单 ID 定位查询找不到目标对脚本而言就是失败，不能用 exit 0 + []
      混同“成功但空”；
    - 窗口过滤后无剩余：查询本身成功，仅向 stderr 提示并返回空表
      （exit 0 + []）。

    ``not_found_hint`` 仅在“取值不存在”场景下随报错输出的定制提示
    （如提示先运行 get-theme-framework-daily 获取 theme_id）。
    """
    if df.empty:
        message = f"{empty_label}：未返回任何数据（取值可能不存在，或暂无数据）。"
        if not_found_hint:
            message += f"\n{not_found_hint}"
        raise ValueError(message)
    trimmed_df = trim_timeseries_window(
        df,
        date_column=date_column,
        **resolve_time_window(args),
    )
    if trimmed_df.empty:
        print_error(
            f"{empty_label}应用时间窗口后没有任何剩余时序数据，"
            "可尝试放宽 --last-n / --start-date / --end-date。"
        )
    return trimmed_df


def warn_future_view_date(view_date: str) -> None:
    """``view_date`` 晚于当天时向 stderr 警告，避免误读为该日数据。"""
    parsed = normalize_date_input(view_date, "view_date")
    if parsed > pd.Timestamp.now().normalize():
        print_error(
            f"警告：view_date {view_date} 晚于当前日期，"
            "服务端将返回最新一期截面数据，而非该日数据。"
        )


def validate_date_range(start_date: str, end_date: str) -> None:
    """校验报告类命令的日期区间：严格 YYYY-MM-DD 格式，且 start 不晚于 end。"""
    start = normalize_date_input(start_date, "start_date")
    end = normalize_date_input(end_date, "end_date")
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")


def run_report_command(
    args: argparse.Namespace,
    fetch_report: Callable[[str, str], pd.DataFrame],
) -> pd.DataFrame:
    """报告类命令共用流程：日期校验、默认窗口、取数并按 view_date 降序输出。

    - 报告结果统一按 ``view_date`` 降序返回（最新在前）；
    - ``--start-date``/``--end-date`` 与 ``--last-n`` 均可省略：都未传时默认取最新 1 期；
    - 仅传 ``--last-n`` 时，使用宽日期区间取数后在本地截取最新 N 期；
    - 日期区间与 ``--last-n`` 组合使用时：先按区间过滤（服务端），再取最新 N 期。
    """
    start_date, end_date, last_n = args.start_date, args.end_date, args.last_n
    if last_n is None and start_date is None and end_date is None:
        last_n = REPORT_DEFAULT_LAST_N
    if (start_date is None) != (end_date is None):
        raise ValueError(
            "--start-date 与 --end-date 必须同时提供；只取最新 N 期时两者都可省略"
        )
    if last_n is not None and last_n <= 0:
        raise ValueError("last_n 必须是正整数")
    if start_date is None:
        # 未提供日期区间：用宽区间向服务端取数，再在本地截取最新 last_n 期
        start_date = REPORT_DEFAULT_START_DATE
        end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    validate_date_range(start_date, end_date)
    report_df = fetch_report(start_date, end_date)
    if report_df.empty:
        return report_df
    return order_reports_latest_first(
        report_df, last_n=last_n, date_column=REPORT_DATE_COLUMN
    )


def filter_sector_records(
    records: list[dict[str, Any]],
    *,
    sector_code: str | None,
    sector_name: str | None,
    keyword: str | None,
) -> list[dict[str, Any]]:
    """对板块列表结果做精确过滤与关键字过滤。"""
    filtered_records = records

    if sector_code:
        filtered_records = [
            record
            for record in filtered_records
            if str(record.get("sector_code", "")).strip() == sector_code
        ]

    if sector_name:
        filtered_records = [
            record
            for record in filtered_records
            if str(record.get("sector_name", "")).strip() == sector_name
        ]

    if keyword:
        normalized_keyword = keyword.casefold()
        filtered_records = [
            record
            for record in filtered_records
            if normalized_keyword in str(record.get("sector_name", "")).casefold()
            or normalized_keyword in str(record.get("sector_code", "")).casefold()
        ]

    return filtered_records


def filter_indicator_records(
    records: list[dict[str, Any]],
    *,
    sector_type: str | None,
    keyword: str | None,
) -> list[dict[str, Any]]:
    """对指标列表结果做板块类型精确过滤与关键字过滤。"""
    filtered_records = records

    if sector_type:
        filtered_records = [
            record
            for record in filtered_records
            if str(record.get("sector_type", "")).strip() == sector_type
        ]

    if keyword:
        normalized_keyword = keyword.casefold()
        filtered_records = [
            record
            for record in filtered_records
            if any(
                normalized_keyword in str(record.get(field) or "").casefold()
                for field in ("indicator_name", "sector_name", "sector_code")
            )
        ]

    return filtered_records


def run_get_indicator_value_batch(args: argparse.Namespace) -> dict[str, Any]:
    """批量查询多个指标的时序数据，并统一应用时间窗口。"""
    if len(args.indicator_ids) > BATCH_MAX_INDICATORS:
        raise ValueError(f"indicator_ids 最多只能包含 {BATCH_MAX_INDICATORS} 个指标")

    id_counts = Counter(args.indicator_ids)
    duplicate_ids = [iid for iid, count in id_counts.items() if count > 1]
    if duplicate_ids:
        print_error(
            "警告：传入的 indicator_id 存在重复，已自动去重：" + "、".join(duplicate_ids)
        )
    unique_ids = list(id_counts)

    raw_results = aibeta.beta_indicator.get_indicator_value_batch(unique_ids)
    window = resolve_time_window(args)

    results: dict[str, pd.DataFrame | None] = {}
    errors: dict[str, str] = {}
    for indicator_id, df in raw_results.items():
        if df is None:
            results[indicator_id] = None
            errors[indicator_id] = "读取失败（网络、鉴权或服务端错误）"
            continue
        if df.empty:
            # 先于窗口过滤区分：空表说明指标不存在或暂无数据，而非窗口过滤所致
            results[indicator_id] = None
            errors[indicator_id] = "服务端未返回任何数据（指标可能不存在或暂无数据）"
            continue
        try:
            trimmed_df = trim_timeseries_window(
                df, date_column=INDICATOR_DATE_COLUMN, **window
            )
        except ValueError as exc:
            results[indicator_id] = None
            errors[indicator_id] = str(exc)
            continue
        if trimmed_df.empty:
            results[indicator_id] = None
            errors[indicator_id] = (
                "应用时间窗口后没有任何剩余时序数据，"
                "可尝试放宽 --last-n / --start-date / --end-date"
            )
            continue
        results[indicator_id] = trimmed_df

    if errors:
        detail_lines = ["以下指标未返回有效数据："]
        for indicator_id, message in errors.items():
            detail_lines.append(f"- {indicator_id}: {message}")
        print_error("\n".join(detail_lines))
    return batch_result_to_jsonable(results)


def build_parser() -> argparse.ArgumentParser:
    """构建单一 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="ai-beta",
        description=(
            "AI Beta 数据 CLI（板块指标库 / 主题分类 / 文本报告，基于 aibeta SDK）。"
            "成功结果输出到 stdout；错误信息、结果规模统计与提示输出到 stderr。"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── 板块指标库 ──────────────────────────────────────────────
    subparsers.add_parser("list-indicator-types", help="查询所有指标类型。")

    parser_list_indicators = subparsers.add_parser(
        "list-indicators", help="按指标类型查询指标列表，可按板块类型、关键字过滤。"
    )
    parser_list_indicators.add_argument(
        "--indicator-type",
        required=True,
        help="指标类型名称，例如“市盈率PE”。",
    )
    parser_list_indicators.add_argument(
        "--sector-type",
        required=False,
        help='板块类型精确过滤，可选，例如 "中信证券行业"、"中信证券一级行业"、"中信证券二级行业"、"中信证券三级行业"、"ETF指数"、"主题概念"。',
    )
    parser_list_indicators.add_argument(
        "--keyword",
        required=False,
        help=(
            "关键字模糊过滤，可选，可同时匹配 indicator_name、sector_name 与 "
            'sector_code，例如 "上证"。'
        ),
    )

    parser_get_indicator_value = subparsers.add_parser(
        "get-indicator-value", help="按指标 ID 查询单个指标时序数据。"
    )
    parser_get_indicator_value.add_argument(
        "--indicator-id",
        required=True,
        help="指标唯一标识。",
    )
    add_time_window_arguments(
        parser_get_indicator_value, date_window_note=INDICATOR_DATE_WINDOW_NOTE
    )

    parser_get_indicator_value_batch = subparsers.add_parser(
        "get-indicator-value-batch",
        help="根据多个指标 ID 批量查询时序数据（固定并发 3）。",
    )
    parser_get_indicator_value_batch.add_argument(
        "--indicator-id",
        dest="indicator_ids",
        action="append",
        required=True,
        help="指标唯一标识。可重复传入多次，最多 30 个。",
    )
    add_time_window_arguments(
        parser_get_indicator_value_batch, date_window_note=INDICATOR_DATE_WINDOW_NOTE
    )

    subparsers.add_parser("list-sector-types", help="查询所有板块类型。")

    parser_list_sectors = subparsers.add_parser(
        "list-sectors", help="查询板块列表，可按板块类型、关键字或精确值过滤。"
    )
    parser_list_sectors.add_argument(
        "--sector-type",
        required=False,
        help="板块类型，可选全集：ETF指数 / 中信证券行业 / 中信证券一级行业 / "
        "中信证券二级行业 / 中信证券三级行业 / 主题概念。",
    )
    parser_list_sectors.add_argument(
        "--sector-code",
        required=False,
        help='板块代码精确查询，可选，例如 "000300.SH"。',
    )
    parser_list_sectors.add_argument(
        "--sector-name",
        required=False,
        help='板块名称精确查询，可选，例如 "沪深300指数"。',
    )
    parser_list_sectors.add_argument(
        "--keyword",
        required=False,
        help='关键字模糊过滤，可同时匹配 sector_name 与 sector_code，例如 "沪深300"。',
    )

    parser_list_indicators_by_sector = subparsers.add_parser(
        "list-indicators-by-sector", help="按板块代码查询关联指标列表。"
    )
    parser_list_indicators_by_sector.add_argument(
        "--sector-code",
        required=True,
        help='板块代码，例如 "000001.SH"。',
    )

    parser_latest_by_type_and_sector = subparsers.add_parser(
        "get-indicator-value-latest-by-type-and-sector",
        help="按指标类型和板块类型查询所有板块的最新一期指标值。",
    )
    parser_latest_by_type_and_sector.add_argument(
        "--indicator-type",
        required=True,
        help='指标类型名称，例如 "市盈率PE"。',
    )
    parser_latest_by_type_and_sector.add_argument(
        "--sector-type",
        required=True,
        help="板块类型名称，可选全集：ETF指数 / 中信证券行业 / 中信证券一级行业 / "
        "中信证券二级行业 / 中信证券三级行业 / 主题概念。",
    )

    # ── 主题分类 ────────────────────────────────────────────────
    parser_theme_framework_daily = subparsers.add_parser(
        "get-theme-framework-daily", help="查询主题库日度截面数据。"
    )
    parser_theme_framework_daily.add_argument(
        "--view-date",
        required=True,
        help="查询日期，严格 YYYY-MM-DD 格式，如 2026-06-30；非法格式（如 2026/6/30）直接报错。",
    )

    parser_theme_index = subparsers.add_parser(
        "get-theme-index", help="查询特定主题的历史指数点位。"
    )
    parser_theme_index.add_argument(
        "--theme-id",
        required=True,
        help="主题 ID。",
    )
    add_time_window_arguments(
        parser_theme_index, date_window_note=THEME_INDEX_DATE_WINDOW_NOTE
    )

    # ── 文本库 ──────────────────────────────────────────────────
    parser_market_daily_report = subparsers.add_parser(
        "get-market-daily-report",
        help="读取市场日报文本（按 view_date 降序返回，默认取最新 1 期）。",
    )
    parser_market_daily_report.add_argument(
        "--start-date",
        required=False,
        help="开始日期，严格 YYYY-MM-DD 格式，如 2026-06-01；非法格式（如 20260601）直接报错。",
    )
    parser_market_daily_report.add_argument(
        "--end-date",
        required=False,
        help="结束日期，严格 YYYY-MM-DD 格式，如 2026-06-30；非法格式（如 2026/6/30）直接报错。",
    )
    parser_market_daily_report.add_argument(
        "--last-n",
        type=int,
        required=False,
        help="仅返回最新 N 期报告（按 view_date 降序取前 N 期）；"
        "未传任何参数时默认取最新 1 期；"
        "与日期区间组合时先按区间过滤再取最新 N 期。"
        "单篇报告数十 KB，N 不宜过大。",
    )

    parser_strategy_weekly_report = subparsers.add_parser(
        "get-strategy-weekly-report",
        help="读取策略周报文本（按 view_date 降序返回，默认取最新 1 期）。",
    )
    parser_strategy_weekly_report.add_argument(
        "--start-date",
        required=False,
        help="开始日期，严格 YYYY-MM-DD 格式，如 2026-06-01；非法格式（如 20260601）直接报错。",
    )
    parser_strategy_weekly_report.add_argument(
        "--end-date",
        required=False,
        help="结束日期，严格 YYYY-MM-DD 格式，如 2026-06-30；非法格式（如 2026/6/30）直接报错。",
    )
    parser_strategy_weekly_report.add_argument(
        "--last-n",
        type=int,
        required=False,
        help="仅返回最新 N 期报告（按 view_date 降序取前 N 期）；"
        "未传任何参数时默认取最新 1 期；"
        "与日期区间组合时先按区间过滤再取最新 N 期。"
        "单篇报告数十 KB，N 不宜过大。",
    )

    # ── 启动前自检 ──────────────────────────────────────────────
    subparsers.add_parser(
        "doctor",
        help="启动前自检：缓存目录可写、网络连通、凭证配置提示。首次安装后立即运行一次。",
    )

    # ── 绘图 ────────────────────────────────────────────────────
    parser_plot_series = subparsers.add_parser(
        "plot-series",
        help="将单指标 / 主题指数时序绘制为图表（PNG/SVG），支持均线与最新值标注。",
    )
    series_group = parser_plot_series.add_mutually_exclusive_group(required=True)
    series_group.add_argument(
        "--indicator-id",
        help="指标唯一标识（与 --theme-id 二选一）。",
    )
    series_group.add_argument(
        "--theme-id",
        help="主题 ID（与 --indicator-id 二选一）。",
    )
    parser_plot_series.add_argument(
        "--indicator-type",
        required=False,
        help="指标类型名称（如 市盈率PE）；提供后自动查询元数据生成图题"
        "（指标类型 · 板块名）与 y 轴单位，省略时图题为 indicator_id。",
    )
    parser_plot_series.add_argument(
        "--title",
        required=False,
        help="自定义图题，覆盖自动生成的图题。",
    )
    parser_plot_series.add_argument(
        "--ma",
        type=parse_ma_windows,
        default=DEFAULT_MA_WINDOWS,
        help="均线窗口（期数），逗号分隔，如 20,60；默认 20,60；"
        "窗口长于数据点数时自动跳过。",
    )
    parser_plot_series.add_argument(
        "--no-ma",
        action="store_true",
        help="不绘制均线（优先于 --ma）。",
    )
    parser_plot_series.add_argument(
        "--no-annotate",
        action="store_true",
        help="不在图上标注最新值。",
    )
    parser_plot_series.add_argument(
        "--output",
        "-o",
        required=False,
        help="输出文件路径，支持 .png（默认）与 .svg 扩展名；缺省扩展名时"
        "按 --format 补全；未提供时在当前目录自动命名。",
    )
    parser_plot_series.add_argument(
        "--format",
        required=False,
        choices=("png", "svg"),
        help="输出格式；省略时按 --output 扩展名推断，仍无法确定时为 png。",
    )
    add_time_window_arguments(
        parser_plot_series, date_window_note=PLOT_DATE_WINDOW_NOTE
    )

    # ── 绘图：截面图（最新一期截面，无时间窗口参数）────────────
    parser_plot_bar = subparsers.add_parser(
        "plot-bar",
        help="将单指标类型在多板块上的最新截面绘制为柱状图（PNG/SVG）；"
        "标的 ≤ 30 时全部绘制，超过 30 时按排序方向两端各取 15。",
    )
    parser_plot_bar.add_argument(
        "--indicator-type",
        required=True,
        help="指标类型名称，例如“市盈率PE”。",
    )
    parser_plot_bar.add_argument(
        "--sector-type",
        required=True,
        help="板块类型名称，可选全集：ETF指数 / 中信证券行业 / 中信证券一级行业 / "
        "中信证券二级行业 / 中信证券三级行业 / 主题概念。",
    )
    parser_plot_bar.add_argument(
        "--sort",
        choices=("desc", "asc"),
        default="desc",
        help="按指标值排序方向：desc 降序（默认）/ asc 升序。",
    )
    parser_plot_bar.add_argument(
        "--title",
        required=False,
        help="自定义图题，覆盖自动生成的图题。",
    )
    parser_plot_bar.add_argument(
        "--output",
        "-o",
        required=False,
        help="输出文件路径，支持 .png（默认）与 .svg 扩展名；缺省扩展名时"
        "按 --format 补全；未提供时在当前目录自动命名。",
    )
    parser_plot_bar.add_argument(
        "--format",
        required=False,
        choices=("png", "svg"),
        help="输出格式；省略时按 --output 扩展名推断，仍无法确定时为 png。",
    )

    parser_plot_scatter = subparsers.add_parser(
        "plot-scatter",
        help="将两个同频率指标类型在多板块上的最新截面绘制为散点图（PNG/SVG），"
        "按板块代码对齐，且要求对齐后为同一数据日期的横截面。",
    )
    parser_plot_scatter.add_argument(
        "--indicator-type",
        dest="indicator_types",
        action="append",
        required=True,
        help="指标类型名称，必须重复传入恰好 2 次：第 1 次为 x 轴，第 2 次为 y 轴；"
        "两者需同频率（自动校验），例如 市盈率PE 与 市净率PB。",
    )
    parser_plot_scatter.add_argument(
        "--sector-type",
        required=True,
        help="板块类型名称，可选全集：ETF指数 / 中信证券行业 / 中信证券一级行业 / "
        "中信证券二级行业 / 中信证券三级行业 / 主题概念。",
    )
    parser_plot_scatter.add_argument(
        "--title",
        required=False,
        help="自定义图题，覆盖自动生成的图题。",
    )
    parser_plot_scatter.add_argument(
        "--annotate",
        action="store_true",
        help="在图上逐点标注板块名称（默认不标注；点多时文字会重叠，"
        "建议仅在标的较少时使用）。",
    )
    parser_plot_scatter.add_argument(
        "--skip-frequency-check",
        action="store_true",
        help="跳过同频率自动校验（默认频率不一致或频率元数据不可得时直接失败；"
        "确认两指标频率口径一致后可用本参数显式跳过）。",
    )
    parser_plot_scatter.add_argument(
        "--output",
        "-o",
        required=False,
        help="输出文件路径，支持 .png（默认）与 .svg 扩展名；缺省扩展名时"
        "按 --format 补全；未提供时在当前目录自动命名。",
    )
    parser_plot_scatter.add_argument(
        "--format",
        required=False,
        choices=("png", "svg"),
        help="输出格式；省略时按 --output 扩展名推断，仍无法确定时为 png。",
    )

    # ── 通用输出选项：所有子命令统一支持 ────────────────────────
    # 落盘场景用 --compact 输出无缩进单行 JSON；默认 indent=2 便于阅读。
    # 在此统一挂载，未来新增子命令自动继承，避免逐命令重复定义。
    for subparser in subparsers.choices.values():
        subparser.add_argument(
            "--compact",
            action="store_true",
            help="输出无缩进单行 JSON（体积最小，适合 `> result.json` 落盘供程序处理）；"
            "默认 indent=2 便于阅读。",
        )

    return parser


def validate_query_arguments(args: argparse.Namespace) -> None:
    """入口统一做本地参数前置校验，先于任何 SDK 调用执行（fail fast）。

    覆盖：严格 YYYY-MM-DD 日期格式（含 view_date）、``--last-n`` 为正整数、
    ``--start-date`` 不晚于 ``--end-date``。保证明显无效的参数不消耗网络、
    鉴权与缓存等待；各查询函数内部仍保留同等校验作为兜底。
    """
    parsed_dates: dict[str, pd.Timestamp | None] = {}
    for field_name in ("start_date", "end_date", "view_date"):
        value = getattr(args, field_name, None)
        parsed_dates[field_name] = (
            normalize_date_input(value, field_name) if value is not None else None
        )
    last_n = getattr(args, "last_n", None)
    if last_n is not None and last_n <= 0:
        raise ValueError("last_n 必须是正整数")
    start, end = parsed_dates["start_date"], parsed_dates["end_date"]
    if start is not None and end is not None and start > end:
        raise ValueError("start_date 不能晚于 end_date")


def run_command(args: argparse.Namespace) -> Any:
    """根据子命令执行具体任务，直调 aibeta SDK。"""
    validate_query_arguments(args)
    # ── 板块指标库 ──
    if args.command == "list-indicator-types":
        return dataframe_to_jsonable(aibeta.beta_indicator.list_indicator_types())
    if args.command == "list-indicators":
        return filter_indicator_records(
            dataframe_to_jsonable(
                aibeta.beta_indicator.list_indicators(args.indicator_type)
            ),
            sector_type=args.sector_type,
            keyword=args.keyword,
        )
    if args.command == "get-indicator-value":
        result_df = aibeta.beta_indicator.get_indicator_value(args.indicator_id)
        return dataframe_to_jsonable(
            trim_indicator_series(
                result_df,
                args,
                empty_label=f"指标 {args.indicator_id}",
                not_found_hint=VALUE_NOT_FOUND_HINTS[args.command],
            )
        )
    if args.command == "get-indicator-value-batch":
        return run_get_indicator_value_batch(args)
    if args.command == "list-sector-types":
        # 缓存类命令：剔除 update_time（本地缓存重建时间，非后端数据更新时间）
        return dataframe_to_jsonable(
            drop_cache_update_time(aibeta.beta_indicator.list_sector_types())
        )
    if args.command == "list-sectors":
        return filter_sector_records(
            dataframe_to_jsonable(
                drop_cache_update_time(
                    aibeta.beta_indicator.list_sectors(args.sector_type)
                )
            ),
            sector_code=args.sector_code,
            sector_name=args.sector_name,
            keyword=args.keyword,
        )
    if args.command == "list-indicators-by-sector":
        return dataframe_to_jsonable(
            drop_cache_update_time(
                aibeta.beta_indicator.list_indicators_by_sector(args.sector_code)
            )
        )
    if args.command == "get-indicator-value-latest-by-type-and-sector":
        return dataframe_to_jsonable(
            aibeta.beta_indicator.get_indicator_value_latest_by_type_and_sector(
                args.indicator_type, args.sector_type
            )
        )
    # ── 主题分类 ──
    if args.command == "get-theme-framework-daily":
        warn_future_view_date(args.view_date)
        return dataframe_to_jsonable(
            aibeta.theme_classification.get_theme_classification_framework_daily(
                args.view_date
            )
        )
    if args.command == "get-theme-index":
        result_df = aibeta.theme_classification.get_theme_classification_index_by_id(
            args.theme_id
        )
        trimmed_df = trim_indicator_series(
            result_df,
            args,
            date_column=THEME_INDEX_DATE_COLUMN,
            empty_label=f"主题 {args.theme_id}",
            not_found_hint=VALUE_NOT_FOUND_HINTS[args.command],
        )
        return dataframe_to_jsonable(normalize_theme_index_dates(trimmed_df))
    # ── 文本库 ──
    if args.command == "get-market-daily-report":
        report_df = run_report_command(
            args, aibeta.text_analysis.get_information_ai_report_market_daily
        )
        return dataframe_to_jsonable(strip_image_references(report_df))
    if args.command == "get-strategy-weekly-report":
        report_df = run_report_command(
            args, aibeta.text_analysis.get_information_ai_report_strategy_weekly
        )
        return dataframe_to_jsonable(strip_image_references(report_df))
    # ── 绘图 ──
    if args.command == "plot-series":
        # 惰性导入：绘图链路才加载 matplotlib，查询命令保持零开销
        from .plot import run_plot_series

        return run_plot_series(args)
    if args.command == "plot-bar":
        from .plot import run_plot_bar

        return run_plot_bar(args)
    if args.command == "plot-scatter":
        from .plot import run_plot_scatter

        return run_plot_scatter(args)
    raise ValueError(f"未知命令：{args.command}")


def strip_string_arguments(args: argparse.Namespace) -> argparse.Namespace:
    """对所有字符串入参做 strip（含批量命令的 ID 列表），避免首尾空白导致匹配失败。"""
    for key, value in vars(args).items():
        if isinstance(value, str):
            setattr(args, key, value.strip())
        elif isinstance(value, list):
            setattr(
                args,
                key,
                [item.strip() if isinstance(item, str) else item for item in value],
            )
    return args


def count_result_records(result: Any) -> int:
    """统计结果记录数：列表命令为长度，批量命令为各组列表长度之和。"""
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        return sum(len(value) for value in result.values() if isinstance(value, list))
    return 0


def emit_output_stats(command: str, record_count: int) -> None:
    """把结果规模输出到 stderr；超过阈值时建议落盘或缩小范围（stdout JSON 不受影响）。"""
    print_error(f"[ai-beta] {command} 返回 {record_count} 行记录")
    if record_count > LARGE_OUTPUT_THRESHOLD:
        print_error(
            f"结果较大（超过 {LARGE_OUTPUT_THRESHOLD} 行），建议："
            "1) 加 --compact 重定向落盘后处理，如 `ai-beta ... --compact > result.json`；"
            "2) 时序命令加 --start-date/--end-date/--last-n 缩小范围；"
            "3) 列表命令用 --sector-type/--keyword 等参数过滤。"
        )


def main() -> int:
    """执行 CLI 主流程。"""
    parser = build_parser()
    args = strip_string_arguments(parser.parse_args())
    # 先于任何 SDK 调用应用 AIBETA_CACHE_DIR 缓存目录重定向
    # （SDK 客户端为懒加载，首次数据调用时才构建，此处满足时序要求）
    apply_cache_dir_override()

    try:
        if args.command == "doctor":
            # 自检报告为纯文本，自行输出到 stdout，不走 JSON 输出与规模统计；
            # 退出码 0/1 承载结论（存在 [FAIL] 项时为 1）
            return run_doctor()
        # SDK 调用期间把 stdout 重定向到 stderr，保证 stdout 只输出最终 JSON
        with redirect_stdout_to_stderr():
            result = run_command(args)
        if args.command.startswith("plot-"):
            # 绘图结果为摘要 JSON（含输出路径），规模统计已由各 plot-* 命令自行输出
            print_json(result, compact=args.compact)
            return 0
        emit_output_stats(args.command, count_result_records(result))
        if isinstance(result, list) and not result:
            # 空结果不静默：按命令类别输出对应的排障提示
            # （get-indicator-value / get-theme-index 的提示由 trim_indicator_series 输出）
            hint = EMPTY_RESULT_HINTS.get(args.command)
            if hint:
                print_error(hint)
        print_json(result, compact=args.compact)
        return 0
    except Exception as exc:  # noqa: BLE001
        print_error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
