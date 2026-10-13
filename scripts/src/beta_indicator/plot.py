"""plot-* 子命令：时序折线图（plot-series）、截面柱状图（plot-bar）、
双指标截面散点图（plot-scatter），统一输出 PNG / SVG。

设计要点：
- matplotlib 惰性导入：仅 plot-* 命令触发导入，其余查询命令零开销；
- 无显示环境友好：固定 Agg 后端，图表落盘为文件，stdout 仍输出结果摘要 JSON；
- 中文字体自动探测：按候选列表选择首个可用字体，缺失时 stderr 警告但不中断；
- plot-series 默认叠加 MA20/MA60 均线与最新值标注，--no-ma / --no-annotate 可关闭。
"""

from __future__ import annotations

import argparse
import os
import re
import warnings
from datetime import datetime
from typing import Any

import aibeta
import pandas as pd

from .output import normalize_related_sector_columns, print_error

# 中文字体候选（按优先级排序；命中即用，均为常见 Linux 发行版 / 办公环境可获得的字体；华为鸿蒙字体优先）
CJK_FONT_CANDIDATES = [
    "HarmonyOS Sans SC",
    "HarmonyOS Sans",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "PingFang SC",
    "Microsoft YaHei",
    "SimHei",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "Hiragino Sans GB",
    "Arial Unicode MS",
]

# 默认均线窗口（期数，随数据频率含义不同：日频≈月线/季线，周频≈半年线/年线）
DEFAULT_MA_WINDOWS = "20,60"

# PNG 输出分辨率
PLOT_DPI = 150

# 柱状图两端截取：标的数超过阈值时展示两端各 KEEP 根柱（Top15 + Bottom15），
# 中间以跳跃刻度提示被省略的标的，兼顾极值两端与整体可读性
BAR_TWO_ENDS_THRESHOLD = 30
BAR_TWO_ENDS_KEEP = 15

# 散点图离群点剔除：20 倍稳健标准差（MAD 口径）。1.4826 为正态一致性系数，
# 判定式 |x − median(x)| > 20 × 1.4826 × MAD，等价于偏离 29.652×MAD 以上
MAD_OUTLIER_SCALE = 20.0
MAD_NORMAL_CONSISTENCY = 1.4826

# plot-series 时间窗口口径说明（两种模式口径不同，与对应查询命令一致）
PLOT_DATE_WINDOW_NOTE = (
    "指标模式（--indicator-id）按 data_publish_date（发布日）过滤，"
    "主题模式（--theme-id）按 price_date（价格日）过滤，"
    "口径分别与 get-indicator-value / get-theme-index 一致。"
)


def parse_ma_windows(value: str) -> list[int]:
    """解析 --ma 参数：逗号分隔的正整数窗口列表，去重保序。"""
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--ma 不能为空；如需关闭均线请使用 --no-ma")
    windows: list[int] = []
    for part in parts:
        try:
            window = int(part)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"--ma 窗口必须是正整数，收到：{part!r}"
            ) from exc
        if window <= 0:
            raise argparse.ArgumentTypeError(
                f"--ma 窗口必须是正整数，收到：{part!r}"
            )
        if window not in windows:
            windows.append(window)
    return windows


def _ensure_mpl_config_dir() -> None:
    """把 matplotlib 配置/字体缓存目录预置到 ``~/.cache/matplotlib``。

    matplotlib 默认写 ``~/.config/matplotlib``：在受限环境（root 沙箱、只读
    home）下该位置常不可写，会触发 mkdir 报错并退回一次性临时目录（每次
    导入都重建字体缓存，慢且输出警告）。提前指向稳定可写目录可消除该问题；
    设置失败时静默跳过，由 matplotlib 自行回退。
    """
    config_dir = os.path.join(os.path.expanduser("~"), ".cache", "matplotlib")
    try:
        os.makedirs(config_dir, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", config_dir)
    except OSError:
        pass


def _configure_chinese_fonts() -> str | None:
    """选择首个可用的中文字体并写入 rcParams；返回字体名，缺失时返回 None。"""
    import matplotlib
    from matplotlib import font_manager

    installed_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in CJK_FONT_CANDIDATES:
        if candidate in installed_fonts:
            matplotlib.rcParams["font.sans-serif"] = [candidate, "DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return candidate
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


def _format_value(value: float) -> str:
    """图表标注用的数值格式化：大数加千分位，小数保留有效数字。"""
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:.6g}"


def _mad_outlier_mask(values: pd.Series, axis_label: str) -> pd.Series:
    """按 20 倍稳健标准差（MAD 口径）标记离群点，返回布尔掩码。

    判定式：``|x − median(x)| > 20 × 1.4826 × MAD``，等价于
    ``x < median − 29.652×MAD`` 或 ``x > median + 29.652×MAD``。
    MAD 为 0（半数以上取值相同）时阈值退化为 0，会误杀全部非中位数
    取值，此时整轴跳过剔除并提示，返回全 False 掩码。
    """
    median = values.median()
    mad = (values - median).abs().median()
    if mad == 0:
        print_error(
            f"提示：{axis_label}MAD 为 0（半数以上取值相同），跳过该轴离群点剔除。"
        )
        return pd.Series(False, index=values.index)
    deviation = (values - median).abs()
    return deviation > MAD_OUTLIER_SCALE * MAD_NORMAL_CONSISTENCY * mad


def _lookup_indicator_meta(
    indicator_type: str, indicator_id: str
) -> dict[str, Any] | None:
    """从指标类型的指标列表中查找元数据，用于自动生成图题与 y 轴单位。

    查找失败（类型错误 / ID 不在该类型下 / 查询异常）时输出 stderr 提示并
    返回 None，调用方退化为用 indicator_id 作图题，不视为失败。
    """
    try:
        meta_df = aibeta.beta_indicator.list_indicators(indicator_type)
    except Exception as exc:  # noqa: BLE001
        print_error(f"提示：查询指标元数据失败（{exc}），图题退化为指标 ID。")
        return None
    if meta_df.empty:
        return None
    meta_df = normalize_related_sector_columns(meta_df)
    matched = meta_df.loc[meta_df["indicator_id"] == indicator_id]
    if matched.empty:
        print_error(
            f"提示：指标类型 {indicator_type} 下未找到 {indicator_id} 的元数据，"
            "图题退化为指标 ID。"
        )
        return None
    row = matched.iloc[0]
    return {
        "sector_name": row.get("sector_name"),
        "indicator_unit": row.get("indicator_unit"),
        "indicator_frequency": row.get("indicator_frequency"),
        "indicator_caliber": row.get("indicator_caliber"),
    }


def _lookup_type_meta(indicator_type: str) -> dict[str, Any] | None:
    """查询指标类型的代表元数据（单位、频率），用于轴标签与散点图频率校验。

    取该类型下指标列表首行；查询异常或空表时 stderr 提示并返回 None，
    调用方降级处理（单位留空、跳过频率校验），不视为失败。
    """
    try:
        meta_df = aibeta.beta_indicator.list_indicators(indicator_type)
    except Exception as exc:  # noqa: BLE001
        print_error(f"提示：查询指标类型 {indicator_type} 元数据失败（{exc}）。")
        return None
    if meta_df.empty:
        return None
    meta_df = normalize_related_sector_columns(meta_df)
    row = meta_df.iloc[0]
    return {
        "indicator_unit": row.get("indicator_unit"),
        "indicator_frequency": row.get("indicator_frequency"),
    }


def _build_indicator_title(args: argparse.Namespace) -> tuple[str, str]:
    """指标模式的图题与 y 轴标签。

    图题自动拼接规则：``指标类型 · 板块名（频率 · 口径）``，元数据缺失时
    逐级退化（板块名缺失→仅类型；元数据不可得→indicator_id）；y 轴标签取
    indicator_unit（"无单位" 留空）。``--title`` 提供时覆盖自动图题。
    """
    title = args.indicator_id
    ylabel = ""
    if args.indicator_type:
        meta = _lookup_indicator_meta(args.indicator_type, args.indicator_id)
        if meta:
            parts = [args.indicator_type]
            sector_name = str(meta.get("sector_name") or "").strip()
            if sector_name:
                parts.append(sector_name)
            qualifiers = [
                str(meta.get(field)).strip()
                for field in (
                    "indicator_frequency",
                    "indicator_caliber",
                    "indicator_unit",
                )
                if meta.get(field) is not None
                and str(meta.get(field)).strip() not in ("", "无")
            ]
            suffix = f"（{' · '.join(qualifiers)}）" if qualifiers else ""
            title = f"{' · '.join(parts)}{suffix}"
            unit = str(meta.get("indicator_unit") or "").strip()
            ylabel = "" if unit in ("", "无单位") else unit
    if args.title:
        title = args.title
    return title, ylabel


def _build_theme_title(
    df: pd.DataFrame, theme_id: str, title_override: str | None
) -> tuple[str, str]:
    """主题指数模式的图题与 y 轴标签：优先 index_name，--title 可覆盖。"""
    if not df.empty and "index_name" in df.columns:
        index_name = str(df["index_name"].iloc[0] or "").strip()
    else:
        index_name = ""
    title = title_override or index_name or theme_id
    return title, "指数点位"


def resolve_output_path(
    output_arg: str | None,
    format_arg: str | None,
    series_key: str,
    prefix: str = "plot_series",
) -> tuple[str, str]:
    """解析输出路径与格式，返回 (绝对路径, 格式)。

    优先级：--output 扩展名 > --format > 默认 png；--output 无扩展名时按
    格式补全；未提供 --output 时在当前目录自动命名
    （<prefix>_<ID前8位>_<时间戳>.<格式>，prefix 随命令取 plot_series /
    plot_bar / plot_scatter）。
    """
    fmt = (format_arg or "").strip().lower()
    output = (output_arg or "").strip()
    if output:
        root, ext = os.path.splitext(output)
        ext = ext.lower()
        if ext in (".png", ".svg"):
            if fmt and fmt != ext.lstrip("."):
                raise ValueError(
                    f"--format {fmt} 与 --output 扩展名 {ext} 不一致，请修正后重试"
                )
            fmt = ext.lstrip(".")
            resolved = output
        elif ext:
            raise ValueError(
                f"--output 仅支持 .png / .svg 扩展名，收到：{ext}"
            )
        else:
            fmt = fmt or "png"
            resolved = f"{output}.{fmt}"
    else:
        fmt = fmt or "png"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        key = re.sub(r"[^A-Za-z0-9]+", "", series_key)[:8] or "series"
        resolved = f"{prefix}_{key}_{stamp}.{fmt}"
    return os.path.abspath(resolved), fmt


def _setup_matplotlib():
    """初始化 matplotlib 渲染环境：Agg 后端 + 中文字体，返回 pyplot 模块。"""
    import matplotlib

    matplotlib.use("Agg")  # 无显示环境：必须在导入 pyplot 前固定后端
    font_name = _configure_chinese_fonts()
    if font_name is None:
        print_error(
            "警告：未检测到中文字体，图中中文可能显示为方块；"
            "可安装 Noto Sans CJK 字体（如 apt-get install fonts-noto-cjk）后重试。"
        )
    from matplotlib import pyplot as plt

    return plt


def render_series_chart(
    dates: pd.Series,
    values: pd.Series,
    *,
    title: str,
    ylabel: str,
    series_label: str,
    ma_windows: list[int],
    annotate_latest: bool,
    output_path: str,
) -> tuple[list[int], list[int]]:
    """渲染时序折线图并保存，返回 (已绘制均线窗口, 数据不足被跳过的窗口)。

    横轴 ``dates`` 可为 datetime（主题指数日度数据）或原始字符串（指标
    data_date，如 "2026-08" / "2026Q2" / "2026"）；字符串横轴按类目等距
    绘制，最新值标注直接展示原始值。
    """
    plt = _setup_matplotlib()

    applied: list[int] = []
    skipped: list[int] = []
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=PLOT_DPI)
    ax.plot(dates, values, linewidth=1.8, color="#1f77b4", label=series_label)
    for window in ma_windows:
        if len(values) < window:
            skipped.append(window)
            continue
        moving_average = values.rolling(window).mean()
        ax.plot(dates, moving_average, linewidth=1.2, label=f"MA{window}")
        applied.append(window)

    last_date = dates.iloc[-1]
    last_value = values.iloc[-1]
    # 原始字符串日期（如 "2026Q2"）直接展示；datetime 格式化为 ISO 日期
    last_date_text = (
        last_date if isinstance(last_date, str) else f"{last_date:%Y-%m-%d}"
    )
    if annotate_latest:
        ax.scatter([last_date], [last_value], s=28, color="#d62728", zorder=5)
        ax.annotate(
            f"最新 {_format_value(float(last_value))}（{last_date_text}）",
            xy=(last_date, last_value),
            xytext=(-10, 14),
            textcoords="offset points",
            ha="right",
            fontsize=9,
            color="#d62728",
        )

    ax.set_title(title, fontsize=13)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    if applied:
        ax.legend(loc="best", frameon=False)
    fig.autofmt_xdate()
    # 字体缺失时 matplotlib 会对每个缺字字形输出 UserWarning（刷屏）；
    # 上方已输出过一条中文字体警告，这里静默字形级警告保持 stderr 干净
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Glyph .* missing from font", category=UserWarning
        )
        fig.tight_layout()
        fig.savefig(output_path)
    plt.close(fig)
    return applied, skipped


def render_cross_section_bar(
    names: pd.Series,
    values: pd.Series,
    *,
    title: str,
    ylabel: str,
    output_path: str,
    gap_after: int | None = None,
    gap_label: str | None = None,
) -> int:
    """渲染截面柱状图并保存，返回绘制柱数。

    ``gap_after`` 提供时（两端截取模式）在第 ``gap_after`` 根柱后留出
    跳跃空位，空位中点放置 ``gap_label`` 刻度（如“…… 省略 N 个 ……”），
    提示中间被省略的标的。
    """
    plt = _setup_matplotlib()

    name_labels = [str(name) for name in names]
    total = len(values)
    if gap_after is not None and 0 < gap_after < total:
        # 两端柱群之间留 2 个柱位的跳跃空位，空位中点放置省略提示刻度
        positions = list(range(gap_after)) + [
            gap_after + 2 + offset for offset in range(total - gap_after)
        ]
        tick_positions = (
            positions[:gap_after] + [gap_after + 0.5] + positions[gap_after:]
        )
        tick_labels = (
            name_labels[:gap_after] + [gap_label or "……"] + name_labels[gap_after:]
        )
    else:
        positions = list(range(total))
        tick_positions = positions
        tick_labels = name_labels

    fig, ax = plt.subplots(
        figsize=(14, 6.5) if total > 20 else (12, 6.5), dpi=PLOT_DPI
    )
    bar_container = ax.bar(positions, values, color="#1f77b4", width=0.65)
    ax.bar_label(
        bar_container,
        labels=[_format_value(float(value)) for value in values],
        fontsize=8,
        padding=2,
    )
    ax.set_title(title, fontsize=13)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.3)
    # 横轴刻度写上标的名称（默认只显示数字序号，无分析意义）；
    # 两端截取时中间为“省略 N 个”跳跃刻度
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=9)
    # 字体缺失时 matplotlib 会对每个缺字字形输出 UserWarning（刷屏）；
    # _setup_matplotlib 已输出过一条中文字体警告，这里静默字形级警告保持 stderr 干净
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Glyph .* missing from font", category=UserWarning
        )
        fig.tight_layout()
        fig.savefig(output_path)
    plt.close(fig)
    return len(values)


def render_scatter(
    x_values: pd.Series,
    y_values: pd.Series,
    labels: pd.Series,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    annotate: bool,
    output_path: str,
) -> int:
    """渲染截面散点图并保存，返回绘制点数。"""
    plt = _setup_matplotlib()

    fig, ax = plt.subplots(figsize=(9, 7), dpi=PLOT_DPI)
    ax.scatter(x_values, y_values, s=28, alpha=0.6, color="#1f77b4")
    if annotate:
        for x, y, label in zip(x_values, y_values, labels):
            ax.annotate(
                str(label),
                xy=(x, y),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=7,
                color="#444444",
            )
    ax.set_title(title, fontsize=13)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(True, alpha=0.3)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Glyph .* missing from font", category=UserWarning
        )
        fig.tight_layout()
        fig.savefig(output_path)
    plt.close(fig)
    return len(x_values)


def run_plot_series(args: argparse.Namespace) -> dict[str, Any]:
    """plot-series 主流程：取数 → 窗口裁剪 → 渲染落盘 → 返回结果摘要。"""
    # 惰性导入 cli（cli 也惰性导入本模块），避免包级循环导入
    from .cli import VALUE_NOT_FOUND_HINTS, THEME_INDEX_DATE_COLUMN, trim_indicator_series
    from .output import _parse_date_column, normalize_theme_index_dates

    # 先于 matplotlib 导入重定向其配置/字体缓存目录（受限环境友好）
    _ensure_mpl_config_dir()

    # 本地参数先行校验：输出路径合法性（扩展名 / --format 一致性）先于 SDK 调用
    series_key = args.indicator_id or args.theme_id
    output_path, fmt = resolve_output_path(args.output, args.format, series_key)

    if args.indicator_id:
        raw_df = aibeta.beta_indicator.get_indicator_value(args.indicator_id)
        trimmed_df = trim_indicator_series(
            raw_df,
            args,
            empty_label=f"指标 {args.indicator_id}",
            not_found_hint=VALUE_NOT_FOUND_HINTS["get-indicator-value"],
        )
        if trimmed_df.empty:
            raise ValueError(
                "时间窗口过滤后没有任何剩余时序数据，无法绘图；"
                "可尝试放宽 --last-n / --start-date / --end-date。"
            )
        date_column, value_column = "data_date", "data_value"
        title, ylabel = _build_indicator_title(args)
        # 图例用指标名称（指标类型），未提供 --indicator-type 时退化为“指标值”
        series_label = args.indicator_type or "指标值"
    else:
        raw_df = aibeta.theme_classification.get_theme_classification_index_by_id(
            args.theme_id
        )
        trimmed_df = trim_indicator_series(
            raw_df,
            args,
            date_column=THEME_INDEX_DATE_COLUMN,
            empty_label=f"主题 {args.theme_id}",
            not_found_hint=VALUE_NOT_FOUND_HINTS["get-theme-index"],
        )
        if trimmed_df.empty:
            raise ValueError(
                "时间窗口过滤后没有任何剩余时序数据，无法绘图；"
                "可尝试放宽 --last-n / --start-date / --end-date。"
            )
        trimmed_df = normalize_theme_index_dates(trimmed_df)
        date_column, value_column = "price_date", "close_price"
        title, ylabel = _build_theme_title(trimmed_df, args.theme_id, args.title)
        series_label = "收盘点位"

    # 横轴用观测日（data_date / price_date），而非发布日：绘图展示经济时间轴。
    # 指标模式 data_date 保留原始字符串：月/季/年频为 "2026-08" / "2026Q2" /
    # "2026"，原始值直接可读，且字典序即时间序（格式定长零填充 / 定长季度号）；
    # 解析成 Timestamp 反而会把季度改写为季初日期（2026Q2 → 2026-04-01），
    # 与业务所属期口径不一致。主题模式 price_date 为标准日度日期，仍解析为 datetime。
    if args.indicator_id:
        dates = trimmed_df[date_column].astype("string")
    else:
        dates = _parse_date_column(trimmed_df[date_column], date_column)
    values = pd.to_numeric(trimmed_df[value_column], errors="coerce")
    plot_df = (
        pd.DataFrame({"date": dates, "value": values})
        .dropna()
        .sort_values("date")
        .reset_index(drop=True)
    )
    dropped_count = len(trimmed_df) - len(plot_df)
    if dropped_count > 0:
        print_error(
            f"提示：{dropped_count} 条记录的日期为空或数值无法解析，已在图中忽略。"
        )
    if plot_df.empty:
        raise ValueError(f"列 {value_column} 无法解析出有效数值，无法绘图。")

    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    ma_windows = [] if args.no_ma else list(args.ma)
    applied, skipped = render_series_chart(
        plot_df["date"],
        plot_df["value"],
        title=title,
        ylabel=ylabel,
        series_label=series_label,
        ma_windows=ma_windows,
        annotate_latest=not args.no_annotate,
        output_path=output_path,
    )
    if skipped:
        print_error(
            f"提示：均线窗口 {', '.join(map(str, skipped))} 长于数据点数"
            f"（{len(plot_df)}），已跳过。"
        )

    latest_date = plot_df["date"].iloc[-1]
    latest_value = float(plot_df["value"].iloc[-1])
    # 指标模式 latest_date 为原始字符串（如 "2026Q2"），直接展示不格式化
    latest_date_text = (
        latest_date if isinstance(latest_date, str) else f"{latest_date:%Y-%m-%d}"
    )
    result: dict[str, Any] = {
        "output": output_path,
        "format": fmt,
        "title": title,
        "data_points": int(len(plot_df)),
        "ma_windows_applied": applied,
        "latest": {"date": latest_date_text, "value": latest_value},
    }
    if skipped:
        result["ma_windows_skipped"] = skipped

    ma_text = f"；均线：{'、'.join(f'MA{w}' for w in applied)}" if applied else ""
    print_error(
        f"[ai-beta] plot-series 已生成 {output_path}"
        f"（{len(plot_df)} 个数据点{ma_text}；"
        f"最新值 {_format_value(latest_value)} @ {latest_date_text}）"
    )
    return result


def run_plot_bar(args: argparse.Namespace) -> dict[str, Any]:
    """plot-bar 主流程：取最新截面 → 清洗排序限流 → 渲染柱状图 → 返回结果摘要。"""
    # 先于 matplotlib 导入重定向其配置/字体缓存目录（受限环境友好）
    _ensure_mpl_config_dir()

    # 本地参数先行校验：输出路径合法性（扩展名 / --format 一致性）先于 SDK 调用
    output_path, fmt = resolve_output_path(
        args.output, args.format, f"bar_{args.indicator_type}", prefix="plot_bar"
    )

    # 细分层级（如中信一/二/三级行业）的转译与层级过滤由 SDK 内部完成
    raw_df = aibeta.beta_indicator.get_indicator_value_latest_by_type_and_sector(
        args.indicator_type, args.sector_type
    )
    if raw_df.empty:
        raise ValueError(
            f"指标类型 {args.indicator_type} × 板块类型 {args.sector_type} "
            "未返回任何截面数据（取值可能不存在，或暂无数据）；"
            "可先运行 list-indicator-types / list-sector-types 确认可用取值。"
        )
    # SDK 原始列含 indicator_related_*（dict/list 字符串），先解析为标准三列
    raw_df = normalize_related_sector_columns(raw_df)

    clean_df = pd.DataFrame(
        {
            "sector_code": raw_df["sector_code"],
            "sector_name": raw_df["sector_name"].astype("string"),
            "value": pd.to_numeric(raw_df["data_value"], errors="coerce"),
            "data_date": raw_df["data_date"],
        }
    ).dropna(subset=["sector_code", "sector_name", "value"])
    if clean_df.empty:
        raise ValueError("截面数据中没有任何有效数值，无法绘图。")

    ascending = args.sort == "asc"
    clean_df = clean_df.sort_values(
        "value", ascending=ascending, kind="stable"
    ).reset_index(drop=True)
    sectors_total = len(clean_df)
    # 标的过多时不做单端截断，改为按排序方向取两端各 15 个（Top15 + Bottom15，
    # 共 30 根柱），中间以“省略 N 个”跳跃刻度提示，兼顾极值两端与整体可读性
    gap_after: int | None = None
    gap_label: str | None = None
    if sectors_total > BAR_TWO_ENDS_THRESHOLD:
        plot_df = pd.concat(
            [clean_df.head(BAR_TWO_ENDS_KEEP), clean_df.tail(BAR_TWO_ENDS_KEEP)]
        )
        gap_after = BAR_TWO_ENDS_KEEP
        gap_label = f"…… 省略 {sectors_total - 2 * BAR_TWO_ENDS_KEEP} 个 ……"
        print_error(
            f"提示：共 {sectors_total} 个标的，已展示两端各 {BAR_TWO_ENDS_KEEP} 个"
            f"（Top15 + Bottom15），中间省略 {sectors_total - 2 * BAR_TWO_ENDS_KEEP} 个。"
        )
    else:
        plot_df = clean_df

    # 各标的"最新一期"的观测日期可能不同（如月频指标各板块报告期不一），需提示；
    # data_date 保留原始字符串（"2026-08" / "2026Q2" / "2026"），直接可读，
    # 字典序即时间序，不解析为 Timestamp（季度会被改写为季初日期）
    date_series = clean_df["data_date"].dropna().astype("string")
    unique_dates = sorted(date_series.unique().tolist())
    if len(unique_dates) > 1:
        print_error(
            f"提示：各标的最新数据日期不一致（{len(unique_dates)} 个日期，"
            f"{unique_dates[0]} ~ {unique_dates[-1]}），"
            "柱高为各自最新值。"
        )

    meta = _lookup_type_meta(args.indicator_type)
    unit = str((meta or {}).get("indicator_unit") or "").strip()
    freq = str((meta or {}).get("indicator_frequency") or "").strip()
    ylabel = "" if unit in ("", "无单位") else unit
    # 图题标注当期指标日期（取占比最高的截面日期，多日期时 stderr 已另行提示）；
    # 原始字符串直接进图题（如 "2026Q2"），与业务所属期口径一致
    date_counts = date_series.value_counts()
    main_date = str(date_counts.index[0])
    qualifiers = [main_date]
    if freq:
        qualifiers.append(freq)
    if unit:
        qualifiers.append(unit)
    suffix = f"（{' · '.join(qualifiers)}）" if qualifiers else ""
    title = args.title or f"{args.indicator_type} · {args.sector_type}{suffix}"

    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    plotted = render_cross_section_bar(
        plot_df["sector_name"],
        plot_df["value"],
        title=title,
        ylabel=ylabel,
        output_path=output_path,
        gap_after=gap_after,
        gap_label=gap_label,
    )
    result: dict[str, Any] = {
        "output": output_path,
        "format": fmt,
        "title": title,
        "bars": int(plotted),
        "sectors_total": int(sectors_total),
        "data_dates": list(unique_dates),
    }
    if gap_after is not None:
        result["omitted_sectors"] = sectors_total - 2 * BAR_TWO_ENDS_KEEP
    print_error(
        f"[ai-beta] plot-bar 已生成 {output_path}"
        f"（{plotted} 个标的，值区间 {_format_value(float(plot_df['value'].min()))}"
        f" ~ {_format_value(float(plot_df['value'].max()))}）"
    )
    return result


def run_plot_scatter(args: argparse.Namespace) -> dict[str, Any]:
    """plot-scatter 主流程：双指标截面取数 → 同频率校验与日期对齐（须同一数据日期）
    → 渲染散点图 → 返回结果摘要。"""
    # 先于 matplotlib 导入重定向其配置/字体缓存目录（受限环境友好）
    _ensure_mpl_config_dir()

    types = list(args.indicator_types)
    if len(types) != 2:
        raise ValueError(
            f"--indicator-type 需要恰好传入 2 次（x 轴与 y 轴各一次），收到 {len(types)} 次"
        )
    x_type, y_type = types
    if x_type == y_type:
        raise ValueError("两个指标类型必须不同：同类型指标散点图（y=x）没有分析意义")

    # 本地参数先行校验：输出路径合法性（扩展名 / --format 一致性）先于任何
    # SDK 调用（含下方的频率元数据查询），避免无效参数先消耗网络与鉴权等待
    output_path, fmt = resolve_output_path(
        args.output,
        args.format,
        f"scatter_{x_type}_{y_type}",
        prefix="plot_scatter",
    )

    # 前置校验"同频率"（fail closed）：两类型频率元数据不一致时直接失败（数据误用）；
    # 元数据不可得时同样失败，仅当用户以 --skip-frequency-check 显式跳过时放行
    x_meta = _lookup_type_meta(x_type)
    y_meta = _lookup_type_meta(y_type)
    x_freq = str((x_meta or {}).get("indicator_frequency") or "").strip()
    y_freq = str((y_meta or {}).get("indicator_frequency") or "").strip()
    if args.skip_frequency_check:
        print_error(
            "提示：已按 --skip-frequency-check 跳过同频率校验，"
            "请自行确认两个指标的数据频率口径一致。"
        )
    elif not (x_freq and y_freq):
        missing_types = "、".join(
            type_name
            for type_name, freq in ((x_type, x_freq), (y_type, y_freq))
            if not freq
        )
        raise ValueError(
            f"无法获取指标类型 {missing_types} 的频率元数据，同频率校验无法执行；"
            "请先运行 list-indicators 确认指标类型取值后重试，"
            "或确认两指标频率一致后加 --skip-frequency-check 显式跳过校验。"
        )
    elif x_freq != y_freq:
        raise ValueError(
            f"两个指标类型频率不一致：{x_type} 为{x_freq}频，{y_type} 为{y_freq}频；"
            "散点图要求两个指标同频率（截面日期口径一致），请更换指标组合，"
            "或确认口径后加 --skip-frequency-check 显式跳过校验。"
        )

    def _fetch_latest(indicator_type: str) -> pd.DataFrame:
        # 细分层级（如中信一/二/三级行业）的转译与层级过滤由 SDK 内部完成
        df = aibeta.beta_indicator.get_indicator_value_latest_by_type_and_sector(
            indicator_type, args.sector_type
        )
        if df.empty:
            raise ValueError(
                f"指标类型 {indicator_type} × 板块类型 {args.sector_type} "
                "未返回任何截面数据（取值可能不存在，或暂无数据）；"
                "可先运行 list-indicator-types / list-sector-types 确认可用取值。"
            )
        # SDK 原始列含 indicator_related_*（dict/list 字符串），先解析为标准三列
        return normalize_related_sector_columns(df)

    x_df = _fetch_latest(x_type)
    y_df = _fetch_latest(y_type)

    # data_date 保留原始字符串：同频率指标格式一致，字符串相等即同日，
    # 字典序即时间序；不解析为 Timestamp（季度 "2026Q2" 会被改写为季初日期）
    x_clean = pd.DataFrame(
        {
            "sector_code": x_df["sector_code"],
            "sector_name": x_df["sector_name"].astype("string"),
            "x_value": pd.to_numeric(x_df["data_value"], errors="coerce"),
            "x_date": x_df["data_date"].astype("string"),
        }
    ).dropna(subset=["sector_code", "x_value", "x_date"])
    y_clean = pd.DataFrame(
        {
            "sector_code": y_df["sector_code"],
            "y_value": pd.to_numeric(y_df["data_value"], errors="coerce"),
            "y_date": y_df["data_date"].astype("string"),
        }
    ).dropna(subset=["sector_code", "y_value", "y_date"])

    merged = x_clean.merge(y_clean, on="sector_code", how="inner")
    if merged.empty:
        raise ValueError(
            f"两个指标类型在板块类型 {args.sector_type} 下没有共同板块，无法绘制散点图。"
        )

    # 前置校验"同日期"：仅保留两侧观测日相同的板块，其余剔除并提示
    total_matched = len(merged)
    aligned = merged.loc[merged["x_date"] == merged["y_date"]].reset_index(drop=True)
    dropped = total_matched - len(aligned)
    if dropped > 0:
        print_error(
            f"提示：{dropped} 个板块两侧最新数据日期不一致，已剔除（仅保留同日期板块）。"
        )
    if aligned.empty:
        x_dates = sorted(merged["x_date"].unique().tolist())
        y_dates = sorted(merged["y_date"].unique().tolist())
        raise ValueError(
            "两个指标类型没有任何板块的数据日期能对齐，无法绘制散点图："
            f"{x_type} 最新截面日期范围 {x_dates[0]} ~ {x_dates[-1]}，"
            f"{y_type} 最新截面日期范围 {y_dates[0]} ~ {y_dates[-1]}；"
            "请更换同日期口径的指标组合。"
        )

    # 严格校验"同一数据日期"：对齐仅保证各板块两侧日期一致，不同板块之间
    # 仍可能来自多个日期。若截面含多个日期，则无法构成同一日横截面，直接
    # 拒绝绘图（图题只能标注单一日期，混合时点会被误读为当日截面）
    date_counts = aligned["x_date"].value_counts()
    if len(date_counts) > 1:
        date_detail = "、".join(
            f"{date}（{count} 个板块）"
            for date, count in date_counts.items()
        )
        raise ValueError(
            f"对齐后的截面仍含 {len(date_counts)} 个不同数据日期（{date_detail}），"
            "无法构成同一日横截面，已拒绝绘图以避免混合时点数据被误读为单日截面；"
            "请更换数据日期一致的指标组合，或待两侧截面日期对齐后重试。"
        )
    main_date = str(date_counts.index[0])

    # 离群点剔除（20 倍稳健标准差，MAD 口径）：任一坐标越界即整点剔除，
    # 避免极端值把主体散点压缩到图的一角；剔除数量通知 stderr 与结果摘要
    outlier_mask = _mad_outlier_mask(aligned["x_value"], "x 轴") | _mad_outlier_mask(
        aligned["y_value"], "y 轴"
    )
    outliers_dropped = int(outlier_mask.sum())
    if outliers_dropped > 0:
        aligned = aligned.loc[~outlier_mask].reset_index(drop=True)
        print_error(
            f"提示：已剔除 {outliers_dropped} 个离群点"
            "（任一坐标偏离中位数超过 20×1.4826×MAD，即 29.652×MAD 稳健标准差）。"
        )
    if aligned.empty:
        raise ValueError("剔除离群点后没有任何剩余板块，无法绘制散点图。")

    def _axis_label(indicator_type: str, meta: dict[str, Any] | None) -> str:
        unit = str((meta or {}).get("indicator_unit") or "").strip()
        return f"{indicator_type}（{unit}）" if unit not in ("", "无单位") else indicator_type

    annotate = bool(args.annotate)
    if not annotate and len(aligned) > 30:
        print_error(
            f"提示：{len(aligned)} 个点未标注板块名称；需要时加 --annotate "
            "强制标注（点多时文字会重叠，建议仅在标的较少时使用）。"
        )
    title = args.title or (
        f"{x_type} vs {y_type} · {args.sector_type}（{main_date}）"
    )

    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    points = render_scatter(
        aligned["x_value"],
        aligned["y_value"],
        aligned["sector_name"],
        title=title,
        xlabel=_axis_label(x_type, x_meta),
        ylabel=_axis_label(y_type, y_meta),
        annotate=annotate,
        output_path=output_path,
    )
    result: dict[str, Any] = {
        "output": output_path,
        "format": fmt,
        "title": title,
        "points": int(points),
        "data_date": main_date,
        "x_indicator_type": x_type,
        "y_indicator_type": y_type,
    }
    if dropped > 0:
        result["date_mismatch_dropped"] = int(dropped)
    if outliers_dropped > 0:
        result["outliers_dropped"] = outliers_dropped
    print_error(
        f"[ai-beta] plot-scatter 已生成 {output_path}"
        f"（{points} 个板块，截面日期 {main_date}）"
    )
    return result
