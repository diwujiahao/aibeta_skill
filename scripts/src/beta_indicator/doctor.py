"""启动前自检（ai-beta doctor）：缓存目录可写、网络连通、凭证配置提示。

设计目的：aibeta SDK 运行期依赖"网络访问"与"本地缓存目录写入"两类系统权限，
当前者由安装命令触发、后者由首次真实查询触发时，权限会被分两次发现、分两次
审批。``ai-beta doctor`` 在同一次命令执行内同时触发两类行为（探针文件写入 +
API 主机 TCP 握手），把权限验证收敛到启动前一轮完成，避免首次查询中途失败。
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlsplit

# aibeta 1.1.0 _client.py 的内部类属性（name mangling）；缺失时回退默认主机
_BASE_URL_ATTR = "_IndicatorLibraryClient__BASE_URL"
_DEFAULT_BASE_URL = "https://research.citics.com"
# 与 SDK 默认缓存目录保持一致（~/.cache/aibeta）
_DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~/.cache"), "aibeta")
_NETWORK_TIMEOUT_SECONDS = 5
_PROBE_FILE_NAME = ".ai_beta_doctor_probe"

_LEVEL_TAG = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}


def _report(level: str, label: str, detail: str) -> None:
    """向 stdout 输出一行自检结果。"""
    print(f"{_LEVEL_TAG[level]} {label}：{detail}")


def resolve_cache_dir() -> str:
    """解析生效的 SDK 缓存目录（与 runtime.py 的重定向口径一致）。"""
    raw_value = os.environ.get("AIBETA_CACHE_DIR")
    if raw_value and raw_value.strip():
        return os.path.expandvars(os.path.expanduser(raw_value.strip()))
    return _DEFAULT_CACHE_DIR


def check_cache_dir_writable() -> tuple[bool, str]:
    """检查缓存目录可写：创建目录并写入/删除探针文件（无需凭证）。"""
    cache_dir = resolve_cache_dir()
    from_env = bool(os.environ.get("AIBETA_CACHE_DIR", "").strip())
    try:
        os.makedirs(cache_dir, exist_ok=True)
        probe_path = os.path.join(cache_dir, _PROBE_FILE_NAME)
        with open(probe_path, "w", encoding="utf-8") as probe_file:
            probe_file.write("probe")
        os.remove(probe_path)
    except OSError as exc:
        return False, (
            f"{cache_dir} 不可写（{exc}）；"
            "可设置 AIBETA_CACHE_DIR 重定向到可写目录后重试"
            "（见 references/CLI_使用手册.md 第 2.1 节）"
        )
    source = "（AIBETA_CACHE_DIR）" if from_env else ""
    return True, f"{cache_dir}（探针文件写入/删除成功）{source}"


def _resolve_api_host_port() -> tuple[str, int]:
    """从 SDK 内部读取 API 主机与端口；属性缺失时回退默认值。"""
    base_url = _DEFAULT_BASE_URL
    try:
        from aibeta import _client as aibeta_client

        base_url = str(
            getattr(aibeta_client.IndicatorLibraryClient, _BASE_URL_ATTR, _DEFAULT_BASE_URL)
        )
    except Exception:  # noqa: BLE001 — SDK 内部结构变化时静默回退，不中断自检
        pass
    parts = urlsplit(base_url)
    host = parts.hostname or _DEFAULT_BASE_URL
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port


def check_network() -> tuple[bool, str]:
    """检查 API 主机网络连通：TCP 握手即可，不消耗凭证、不发起数据请求。"""
    host, port = _resolve_api_host_port()
    try:
        with socket.create_connection((host, port), timeout=_NETWORK_TIMEOUT_SECONDS):
            pass
    except socket.gaierror as exc:
        return False, f"{host}:{port} DNS 解析失败（{exc}）；请检查网络与代理配置后重试"
    except OSError as exc:
        return False, f"{host}:{port} 连接失败（{exc}）；请检查网络连通性、防火墙或代理后重试"
    return True, f"{host}:{port} TCP 握手成功（{_NETWORK_TIMEOUT_SECONDS}s 超时）"


def check_credentials() -> tuple[bool, str]:
    """检查凭证环境变量是否已配置；未配置仅为提示，不影响自检结论。"""
    app_key = os.environ.get("BETA_INDICATOR_API_APP_KEY", "").strip()
    secret_key = os.environ.get("BETA_INDICATOR_API_SECRET_KEY", "").strip()
    if app_key and secret_key:
        return True, "BETA_INDICATOR_API_APP_KEY / BETA_INDICATOR_API_SECRET_KEY 已配置"
    return False, (
        "未配置 BETA_INDICATOR_API_APP_KEY / BETA_INDICATOR_API_SECRET_KEY；"
        "查询前请向用户获取凭证并 export（CLI 仅支持环境变量方式，"
        "配置后重跑本命令可见 [OK]）"
    )


def run_doctor() -> int:
    """执行启动前自检并输出报告，返回退出码：0 通过，1 存在 [FAIL] 项。"""
    print("[ai-beta] 启动前自检：")
    cache_ok, cache_detail = check_cache_dir_writable()
    _report("ok" if cache_ok else "fail", "缓存目录可写", cache_detail)
    network_ok, network_detail = check_network()
    _report("ok" if network_ok else "fail", "网络连通", network_detail)
    credentials_ok, credentials_detail = check_credentials()
    _report("ok" if credentials_ok else "warn", "凭证配置", credentials_detail)

    if not (cache_ok and network_ok):
        print("[ai-beta] 自检未通过：请按上述 [FAIL] 项的指引修复后重跑 ai-beta doctor。")
        return 1
    if not credentials_ok:
        print("[ai-beta] 网络与缓存目录自检通过；凭证为提示项，配置后即可开始查询。")
        return 0
    print("[ai-beta] 自检全部通过，可以开始查询。")
    return 0
