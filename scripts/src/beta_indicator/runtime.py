"""运行时环境适配：aibeta SDK 缓存目录重定向（AIBETA_CACHE_DIR）。

aibeta SDK 在模块导入时把本地快照缓存目录固化为 ``~/.cache/aibeta/``（类属性，
未提供配置入口）。当 ``~/.cache`` 不可写或需要目录隔离时，CLI 侧通过
``AIBETA_CACHE_DIR`` 环境变量在首次 SDK 调用前重写其内部类属性，把缓存重定向
到任意可写目录，避免运行期固定写入用户主目录。
"""

from __future__ import annotations

import os
import sys

# 以下属性名与 aibeta 1.1.0 _client.py 的内部实现（类属性名 name mangling）对应；
# SDK 升级后若属性缺失，本模块会输出 stderr 警告并回退默认路径，不中断查询。
_CACHE_DIR_ATTR = "_IndicatorLibraryClient__CACHE_DIR"
_CACHE_FILE_ATTR = "_IndicatorLibraryClient__CACHE_DATA_FILE_PATH"
# SDK 默认缓存文件名：重定向目录时沿用同名文件，保持缓存格式与加载逻辑不变
_CACHE_FILE_NAME = "beta_indicator_cache.parquet"


def apply_cache_dir_override() -> str | None:
    """按环境变量 ``AIBETA_CACHE_DIR`` 重定向 aibeta SDK 的本地缓存目录。

    - 未设置（或为空白）时为无操作，返回 ``None``；
    - 必须在第一次 SDK 数据调用之前执行（SDK 客户端为懒加载，此处满足时序）；
    - 支持 ``~`` 与 ``$VAR`` 展开；
    - 失败（SDK 内部结构不兼容、目录不可创建等）时输出 stderr 警告并保持
      默认目录，不抛异常、不中断查询。

    返回实际生效的缓存目录；未设置或重定向失败时返回 ``None``。
    """
    raw_value = os.environ.get("AIBETA_CACHE_DIR")
    if raw_value is None or not raw_value.strip():
        return None
    cache_dir = os.path.expandvars(os.path.expanduser(raw_value.strip()))
    try:
        from aibeta import _client as aibeta_client

        client_cls = aibeta_client.IndicatorLibraryClient
        if not (
            hasattr(client_cls, _CACHE_DIR_ATTR)
            and hasattr(client_cls, _CACHE_FILE_ATTR)
        ):
            raise AttributeError(
                "aibeta SDK 内部缓存属性缺失（SDK 版本不兼容），无法重定向缓存目录"
            )
        # 预创建目录，把"不可写"问题提前暴露为可读的错误信息
        os.makedirs(cache_dir, exist_ok=True)
        setattr(client_cls, _CACHE_DIR_ATTR, cache_dir)
        setattr(
            client_cls,
            _CACHE_FILE_ATTR,
            os.path.join(cache_dir, _CACHE_FILE_NAME),
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[ai-beta] 警告：AIBETA_CACHE_DIR={raw_value!r} 未生效（{exc}），"
            "SDK 将使用默认缓存目录 ~/.cache/aibeta/。\n"
        )
        return None
    sys.stderr.write(
        f"[ai-beta] SDK 缓存目录已按 AIBETA_CACHE_DIR 重定向到：{cache_dir}\n"
    )
    return cache_dir
