# -*- coding: utf-8 -*-
"""工具函数模块"""
import asyncio
import logging

import aiohttp_compat  # noqa: F401  # aiohttp / brotli 多版本兼容补丁（导入即生效）
import os
import re
import shutil
import sys

logger = logging.getLogger(__name__)


def parse_duration(value) -> float:
    """
    解析时间字符串为秒数
    支持格式: "30s" / "2m" / "1m30s" / 纯数字（秒）
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    m_min = re.search(r'(\d+(?:\.\d+)?)\s*m', s)
    m_sec = re.search(r'(\d+(?:\.\d+)?)\s*s', s)
    total = (float(m_min.group(1)) if m_min else 0.0) * 60 + (float(m_sec.group(1)) if m_sec else 0.0)
    if total <= 0:
        raise ValueError(f"无法解析时间：{value!r}，支持格式如 '30s' '2m' '1m30s'")
    return total


def fmt_duration(value) -> str:
    """
    格式化时间为可读字符串
    例如: 90 -> "1m30s", 60 -> "1m", 30 -> "30s"
    """
    m, s = divmod(int(parse_duration(value)), 60)
    if m and s:
        return f"{m}m{s}s"
    return f"{m}m" if m else f"{s}s"


def setup_console_encoding() -> None:
    """Windows 控制台默认是 GBK，遇到 ¥ 等字符时 print 会直接抛 UnicodeEncodeError。

    这里把不可编码字符降级成占位符，避免日志/控制台输出把程序打断。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def print_port_conflict_hint(host: str, port: int, extra: str = None) -> None:
    """端口被占用时打印可操作的处理指引（避免甩一堆 traceback）"""
    print()
    print("=" * 68)
    print(f"✗ 无法启动 WebUI：端口 {host}:{port} 已被占用")
    print()
    print("常见原因是已经有一个实例在运行（main.py / fake_room.py 只能开一个），")
    print("请先在它的窗口按 Ctrl+C 退出，或者换个端口：")
    print(f"  python main.py --port 0        # 自动挑一个空闲端口")
    print(f"  python main.py --port 8081")
    if extra:
        print()
        print(extra)
    print()
    print("查看谁占用了端口（Windows）：")
    print(f'  netstat -ano | findstr ":{port}"')
    print("=" * 68)


def to_int(value, default: int = 0) -> int:
    """把推送里的数字字段安全转成 int。

    真实 Bilibili 推送并不保证类型：比如 USER_TOAST_MSG_V2 的 guard_level
    实测会是字符串 "1"，直接拿去比 dict 的 int 键就会取不到值、显示成兜底文案。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def install_asyncio_exception_filter() -> None:
    """屏蔽 Windows 上已知且无法处理的噪音异常。

    Windows 的 ProactorEventLoop 在对端 RST 断开连接时，
    ``_ProactorBasePipeTransport._call_connection_lost()`` 里调用
    ``sock.shutdown(SHUT_RDWR)`` 会抛 ConnectionResetError，asyncio 会把它打成::

        Exception in callback _ProactorBasePipeTransport._call_connection_lost()

    这既不是本程序的 bug，也没法在业务代码里捕获，这里降级成 DEBUG 日志，
    避免刷屏掩盖真正的问题。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    previous = loop.get_exception_handler()

    def handler(loop, context):
        exc = context.get("exception")
        message = str(context.get("message", ""))
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError))                 and "_call_connection_lost" in message:
            logger.debug("连接被对端重置，已忽略：%s", exc)
            return
        if previous is not None:
            previous(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出来的 exe 里"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """「程序所在目录」

    - 源码运行：本文件所在目录
    - 打包成 exe：exe 所在目录（配置文件就放这里，用户要能改）
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts) -> str:
    """只读资源路径（html/、pulses.json 等）

    打包后这些资源被解压到 sys._MEIPASS，源码运行时就在项目目录。
    """
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def config_path() -> str:
    """配置文件路径。

    - 打包后：exe 旁边的 config.yaml
    - 源码运行：项目目录下的 config.yaml
    - 都可用环境变量 ``BLIVE_CONFIG`` 覆盖（测试脚本靠它指向临时文件）
    """
    env = os.environ.get("BLIVE_CONFIG")
    if env:
        return env
    return os.path.join(app_dir(), "config.yaml")


def ensure_config_file() -> str:
    """确保配置文件存在：没有就从内置模板复制一份出来（首次运行 exe 时会用到）"""
    path = config_path()
    if not os.path.exists(path):
        template = resource_path("config.yaml")
        try:
            if os.path.exists(template) and os.path.abspath(template) != os.path.abspath(path):
                shutil.copyfile(template, path)
        except Exception as e:
            logging.getLogger(__name__).warning(f"创建默认配置文件失败：{e}")
    return path


def ruamel_available() -> bool:
    """是否装了 ruamel.yaml（装了才能「保存配置不丢注释」）"""
    try:
        import ruamel.yaml  # noqa: F401
        return True
    except Exception:
        return False


RUAMEL_HINT = "安装它可让保存配置时保留注释：pip install ruamel.yaml"
