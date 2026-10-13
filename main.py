# -*- coding: utf-8 -*-
"""主程序入口

运行模式（互不冲突，同一个进程里可同时具备）：

    python main.py            连接真实直播间，正常控制郊狼
    python main.py --test     连接真实直播间 + 打开「测试」页，可手动注入模拟事件
    python main.py --fake     不连接 Bilibili，只用模拟事件（本地联调）

`fake_room.py` 是 `--fake` 的快捷方式，二者等价。

许可：GNU GPL v3（见 LICENSE）；上游 xyBakaQAQ/Blive_DGLAB 的 MIT 声明见 LICENSE-MIT；
第三方组件与许可全文见 THIRD_PARTY_LICENSES.md。
"""
import argparse
import asyncio
import http.cookies
import logging
import logging.handlers
import os
import sys
import webbrowser

import aiohttp
import yaml

import blivedm
from bili_login import apply_cookies, check_login, parse_room_input
import bili_login
from bilibili import BilibiliHandler
from coyote_hub import CoyoteHub
from dglab import DGLabController
from utils import (app_dir, ensure_config_file, install_asyncio_exception_filter,
                   is_frozen, print_port_conflict_hint, ruamel_available,
                   setup_console_encoding)
from web import PortInUseError, WebUI

# ── 配置加载 ──────────────────────────────────────────────────────────────────
# 打包成 exe 后，配置文件放在 exe 旁边；首次运行会从内置模板复制一份出来
CONFIG_PATH = ensure_config_file()
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}

logger = logging.getLogger(__name__)


def want_qr_login(login_mode: str, logged_in: bool,
                  fake: bool = False, no_webui: bool = False) -> bool:
    """启动时要不要打开扫码页

    - always：每次都扫码刷新（避免凭证过期导致监听不可用）
    - auto  ：只在凭证失效 / 缺失时提示扫码
    - off   ：从不提示
    """
    if fake or no_webui:
        return False
    mode = str(login_mode or "auto").lower()
    if mode == "always":
        return True
    if mode == "auto":
        return not logged_in
    return False


def wants_estop(args, cfg: dict) -> bool:
    """是否启动桌面紧急停堆悬浮球

    优先级：--no-estop > --estop > config.yaml 的 estop.auto_launch
    """
    if getattr(args, "no_estop", False):
        return False
    if getattr(args, "estop", False):
        return True
    return bool((cfg or {}).get("estop", {}).get("auto_launch", False))


def launch_estop_window(port: int, exit_when_lost: int = 60):
    """把「紧急停堆」悬浮窗作为独立进程拉起来（它不依赖浏览器）"""
    import subprocess

    if is_frozen():
        # 打包成 exe：没有单独的 .py，直接再拉一个自己，用内部参数进悬浮窗模式
        cmd = [sys.executable, "--estop-window",
               "--estop-url", f"http://127.0.0.1:{port}",
               "--estop-exit", str(exit_when_lost)]
    else:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estop_window.py")
        if not os.path.exists(script):
            logger.warning("找不到 estop_window.py，跳过启动紧急停堆悬浮窗")
            return None
        cmd = [sys.executable, script, "--port", str(port),
               "--exit-when-lost", str(exit_when_lost)]

    try:
        kwargs = {}
        if sys.platform == "win32":
            # 独立进程 + 独立进程组：主程序退出/被 Ctrl+C 时悬浮窗不受影响
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        logger.info("已启动「紧急停堆」桌面悬浮按钮（左键单击 = 立即停堆）")
        return proc
    except Exception as e:
        logger.warning(f"启动紧急停堆悬浮窗失败：{e}（可手动运行 python estop_window.py）")
        return None


LOG_FILE = None


def _log_file_handler():
    """日志同时写一份到 logs/blive.log

    打包成 exe 后窗口一关日志就没了，出问题时没法排查，所以留一份文件日志。
    """
    global LOG_FILE
    try:
        log_dir = os.path.join(app_dir(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        LOG_FILE = os.path.join(log_dir, "blive.log")
        h = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        return h
    except Exception:
        LOG_FILE = None
        return None


def wants_page_exit(args, cfg: dict) -> bool:
    """关掉所有网页后要不要自动退出

    优先级：--no-exit-when-page-closed > --exit-when-page-closed > config.yaml
    """
    if getattr(args, "no_exit_when_page_closed", False):
        return False
    if getattr(args, "exit_when_page_closed", False):
        return True
    return bool((cfg.get("webui") or {}).get("exit_when_page_closed", False))


async def wait_listening(state: dict) -> None:
    """等直播间监听结束

    state = {"client": 当前客户端, "shutting_down": bool, "switching": bool}

    热切换直播间时会先停掉旧客户端，`await client.join()` 因此立刻返回 ——
    那**不代表**监听结束。而且 join() 返回得可能比「新客户端建好」还早
    （中间隔着 `await client.stop_and_close()`），只看 client 有没有换过会漏判，
    所以 apply_room_change 会先立一个 switching 旗：
    扫码登录（自动填房间号 + 热切换）就靠它避免把程序带退出。
    """
    while True:
        current = state.get("client")
        if current is None:
            return
        await current.join()

        if state.get("shutting_down"):
            return
        if state.get("switching"):
            # 正在切直播间：等切换流程收尾（新客户端会被写回 state）
            while state.get("switching") and not state.get("shutting_down"):
                await asyncio.sleep(0.05)
            continue
        if state.get("client") is current:
            return
        logger.debug("直播间已切换，继续等待新的客户端")


async def wait_or_page_exit(coro, page_exit_event=None, enabled: bool = True) -> bool:
    """等主循环结束；这期间如果所有网页都关掉了，就提前收工

    返回 True 表示「因为网页全关了而退出」，False 表示主循环自己结束的。
    """
    if not enabled or page_exit_event is None:
        await coro
        return False

    main_task = asyncio.ensure_future(coro)
    stop_task = asyncio.ensure_future(page_exit_event.wait())
    try:
        done, pending = await asyncio.wait(
            {main_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        for t in (main_task, stop_task):
            t.cancel()
        raise
    for t in pending:
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    if main_task in done:
        main_task.result()      # 主循环自己的异常照常抛出去
        return False
    return True


def setup_logging(level: str = None) -> None:
    handlers = [logging.StreamHandler()]
    fh = _log_file_handler()
    if fh is not None:
        handlers.append(fh)
    logging.basicConfig(
        level=getattr(logging, (level or config.get("log", {}).get("level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    # 注意：不要再把 blivedm 静音成 CRITICAL —— 那样连不上直播间时用户什么都看不到。
    # 只有在显式要求 DEBUG 时才让它说细节，否则保留 WARNING 以上。
    level = (level or config.get("log", {}).get("level", "INFO")).upper()
    logging.getLogger("blivedm").setLevel(logging.DEBUG if level == "DEBUG" else logging.WARNING)


def parse_args(argv=None, default_fake: bool = False) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Bilibili 直播弹幕 DG-Lab 控制器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python main.py --test                 连直播间，同时打开测试页注入模拟事件\n"
            "  python main.py --fake                 不连 Bilibili，只用模拟事件\n"
            "  python main.py --fake --scenario burst --kind danmaku --count 50\n"
            "  python main.py --port 0               端口被占用时自动挑一个空闲端口\n"
        ),
    )
    parser.add_argument("--host", help="WebUI 监听地址（默认取 config.yaml）")
    parser.add_argument("--port", type=int, help="WebUI 监听端口，0 表示自动选择（默认取 config.yaml）")
    parser.add_argument("--log-level", help="日志级别，如 DEBUG")
    parser.add_argument("--no-webui", action="store_true", help="不启动 WebUI")
    parser.add_argument("--no-browser", action="store_true",
                        help="启动时不自动打开浏览器页面（只打印地址）")
    parser.add_argument("--estop", action="store_true",
                        help="同时启动桌面「紧急停堆」悬浮按钮（默认由 config.yaml 的 estop.auto_launch 决定）")
    parser.add_argument("--no-estop", action="store_true",
                        help="不启动桌面「紧急停堆」悬浮按钮")
    parser.add_argument("--exit-when-page-closed", action="store_true",
                        help="关掉所有网页后自动退出程序（默认由 config.yaml 的 webui.exit_when_page_closed 决定）")
    parser.add_argument("--no-exit-when-page-closed", action="store_true",
                        help="关掉网页后不退出（配合 config.yaml 开着该选项时使用）")

    group = parser.add_argument_group("测试模式")
    group.add_argument("--test", action="store_true",
                       help="连接真实直播间的同时，开放「测试」页与模拟事件注入接口")
    group.add_argument("--fake", action="store_true", default=default_fake,
                       help="不连接 Bilibili，只使用本地模拟直播间")
    group.add_argument("--scenario", choices=["burst", "mixed"], help="--fake 下的非交互场景")
    group.add_argument("--kind", default="danmaku", help="burst 场景的事件类型")
    group.add_argument("--count", type=int, default=20, help="burst 场景的条数")
    group.add_argument("--interval", type=float, default=0.05, help="事件间隔（秒）")
    group.add_argument("--duration", type=float, default=30, help="mixed 场景的持续秒数")

    # 内部参数：打包成 exe 后，主程序靠这些参数把「自己」再拉起来当悬浮窗用
    group.add_argument("--estop-window", action="store_true", help=argparse.SUPPRESS)
    group.add_argument("--estop-url", help=argparse.SUPPRESS)
    group.add_argument("--estop-exit", type=float, default=60, help=argparse.SUPPRESS)
    group.add_argument("--estop-selftest", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


async def main(args) -> int:
    setup_console_encoding()

    if getattr(args, "estop_window", False):
        # 打包后没有独立脚本，主程序用这个内部参数把自己当悬浮窗拉起来。
        # 注意：这里在 setup_logging 之前返回 —— 悬浮窗不需要文件日志，
        # 免得和主程序抢同一个 logs/blive.log。
        import estop_window
        argv = []
        if getattr(args, "estop_url", None):
            argv += ["--url", args.estop_url]
        argv += ["--exit-when-lost", str(getattr(args, "estop_exit", 60) or 0)]
        if getattr(args, "estop_selftest", False):
            argv.append("--self-test")     # 排查「悬浮球为啥不好看」用
        return estop_window.main(argv)

    setup_logging(args.log_level)

    if not ruamel_available():
        logger.warning("未安装 ruamel.yaml —— 保存配置时会把注释丢掉（会自动备份 config.yaml.bak）。"
                       "建议执行：pip install -r requirements.txt（或 pip install ruamel.yaml）")
    logger.info(f"配置文件：{CONFIG_PATH}")
    if LOG_FILE:
        logger.info(f"日志文件：{LOG_FILE}")
    # Windows 上对端 RST 时 asyncio 会打一堆 ConnectionResetError，属于噪音，过滤掉
    install_asyncio_exception_filter()

    # 测试注入：命令行 --test / --fake 或 config.yaml 的 test.enabled 任一开启即可
    test_enabled = bool(args.test or args.fake or config.get("test", {}).get("enabled", False))

    if args.scenario and not args.fake:
        logger.warning("--scenario 只在 --fake 模式下生效，已忽略（如需模拟事件请加 --fake）")
    if args.no_webui and test_enabled:
        logger.warning("--no-webui 下没有 Web 服务，测试页无法访问；事件仍可通过控制台发送")
    if args.no_webui and (args.estop or config.get("estop", {}).get("auto_launch", False)):
        logger.warning("--no-webui 时不启动紧急停堆悬浮窗（它需要 WebUI 接口）")
    # 桌面紧急停堆悬浮球的子进程（主程序退出时一并收掉）
    estop_proc = None

    # ── Bilibili cookies ──
    cookies = http.cookies.SimpleCookie()
    cookies["SESSDATA"] = config["bilibili"]["sessdata"]
    cookies["SESSDATA"]["domain"] = "bilibili.com"

    session = aiohttp.ClientSession()
    session.cookie_jar.update_cookies(cookies)

    # ── 恢复上次扫码登录的整套 cookie ──
    # 只靠 config 里的 SESSDATA 是不够的：B 站还会校验 buvid 等设备指纹 cookie，
    # 缺失就会被当成新设备 → 表现成「每次打开都要重新扫码」。
    bili_cfg = config.setdefault("bilibili", {})
    saved_cookies = bili_login.pick_persist_cookies(bili_cfg.get("cookies") or {})
    if not saved_cookies and bili_cfg.get("sessdata"):
        saved_cookies = {"SESSDATA": bili_cfg["sessdata"]}   # 兼容老配置
    if saved_cookies:
        count = apply_cookies(session, saved_cookies)
        logger.info(f"已恢复 B 站登录状态（{count} 项 cookie）")

    logged_in = False
    if not args.fake:
        try:
            state = await asyncio.wait_for(check_login(session), timeout=8)
            logged_in = bool(state.get("is_login"))
            if logged_in:
                logger.info(f"B 站登录状态：已登录（{state.get('uname')}）")
            elif saved_cookies:
                logger.warning("B 站登录状态：已失效，请重新扫码登录")
            else:
                logger.info("B 站登录状态：未登录（不影响基础弹幕，扫码登录后数据更完整）")
        except Exception as e:
            logger.debug(f"检查登录状态失败：{e}")

    # 需不需要弹扫码页：always 每次都弹；auto 只在凭证失效时弹
    login_mode = str(bili_cfg.get("login_mode", "auto") or "auto").lower()
    need_login = want_qr_login(login_mode, logged_in, fake=args.fake, no_webui=args.no_webui)
    if need_login:
        logger.info("将在浏览器打开扫码登录页，扫码后自动刷新登录凭证")

    # ── 内置郊狼服务 ──
    hub = CoyoteHub(config)
    dglab = DGLabController(config, session=session, hub=hub)

    # ── WebUI ──
    webui_config = config.get("webui", {})
    webui_host = args.host or webui_config.get("host", "0.0.0.0")
    webui_port = args.port if args.port is not None else webui_config.get("port", 17800)
    webui = WebUI(config, dglab, host=webui_host, port=webui_port, hub=hub, session=session)

    # 「关掉所有网页后自动退出」：网页里注入心跳脚本，全部关掉就 set 这个事件
    page_exit_enabled = (not args.no_webui) and wants_page_exit(args, config)
    page_exit_event = asyncio.Event()
    if page_exit_enabled:
        webui.exit_when_page_closed = True
        webui.count_obs_pages = bool(webui_config.get("count_obs_pages", False))
        webui.page_exit_event = page_exit_event

    # ── 事件处理器 ──
    handler = BilibiliHandler(config, dglab, webui)
    webui.bili_handler = handler

    # ── 模拟直播间（测试注入） ──
    room = None
    fake_room_api = None
    if test_enabled:
        import fake_room as fake_room_api
        room = fake_room_api.FakeLiveRoom(handler, webui)
        webui.fake_room = room

    # ── Bilibili 客户端（--fake 时不连接） ──
    client = None
    # 房间号允许填短号 / 直播间链接，这里统一抠出数字
    room_input = config["bilibili"]["room_id"]
    room_id = parse_room_input(room_input)
    if room_id is None:
        logger.error(f"房间号「{room_input}」无法识别，请填数字或直播间链接")
        room_id = room_input
    elif str(room_id) != str(room_input).strip():
        logger.info(f"房间号已归一化：{room_input} → {room_id}")
    if not args.fake:
        client = blivedm.BLiveClient(room_id, session=session)

    # ── 启动 WebUI ──
    if not args.no_webui:
        try:
            await webui.start()
        except PortInUseError as e:
            print_port_conflict_hint(
                e.host, e.port,
                extra="如果那个实例已经开着，直接用它上面的页面即可（启动时加 --test 会多出「测试」页）。",
            )
            await session.close()
            return 2

        browser_host = "localhost" if webui_host == "0.0.0.0" else webui_host
        webui_url = f"http://{browser_host}:{webui.port}"
        if need_login:
            # 直接打开扫码页：扫一次就把凭证刷新掉，避免过期导致监听不可用
            if not args.no_browser:
                webbrowser.open(f"{webui_url}/login.html")
            print(f"扫码登录：{webui_url}/login.html   ← 刷新登录凭证（不扫也能继续用）")
        elif not args.no_browser:
            webbrowser.open(webui_url)
        else:
            print(f"控制面板：{webui_url}")

        if wants_estop(args, config):
            estop_proc = launch_estop_window(webui.port)
        else:
            logger.info("未启动桌面紧急停堆悬浮球（可用 --estop 手动开启）")
        if test_enabled:
            print(f"测试页：  {webui_url}/test.html")
        if dglab.enabled and dglab.mode == "embedded":
            print(f"郊狼扫码：{webui.hub_connect_url()}")

    if args.fake:
        print("\n=== 模拟直播间已就绪（不会连接 Bilibili）===")
    else:
        print(f"\n=== 正在连接直播间 {room_id} ===")
    if dglab.enabled and dglab.mode == "embedded":
        print("提示：用官方郊狼 App 扫码连上后，事件就会真的控制设备。\n")

    # 用一个可变标记表示“正在退出”：切换直播间的协程可能在退出过程中才恢复执行，
    # 那时不能再 attach/start 新客户端，否则会在退出时触发一次无意义的重连。
    # client 也放在这里，方便 wait_listening() 判断「是不是换了客户端」。
    lifecycle = {"shutting_down": False, "switching": False, "client": client}

    async def apply_room_change(new_room_id) -> None:
        """房间号变了就热重启监听，不用重启整个程序（扫码后自动调用）"""
        nonlocal client, room_id
        try:
            new_room_id = int(new_room_id)
        except (TypeError, ValueError):
            return
        if lifecycle["shutting_down"]:
            logger.debug("程序正在退出，忽略切换直播间请求")
            return
        if client is not None and new_room_id == room_id and client.is_running:
            return

        # 立「正在切换」旗：旧客户端一停，主循环的 join() 就会返回，
        # 没有这个旗它会以为监听结束了，直接把程序带走。
        lifecycle["switching"] = True
        try:
            handler.set_stopping()      # 先掐掉自动重连，免得旧客户端又被拉起来
            if client is not None:
                try:
                    await client.stop_and_close()
                except Exception as e:
                    logger.warning(f"关闭旧监听失败：{e}")
            room_id = new_room_id
            if args.fake:
                return
            if lifecycle["shutting_down"]:
                return
            client = blivedm.BLiveClient(room_id, session=session)
            client.set_handler(handler)
            handler.attach_client(client)
            lifecycle["client"] = client    # 让 wait_listening() 知道换了客户端
            client.start()
            logger.info(f"已切换到直播间 {room_id}")
        finally:
            lifecycle["switching"] = False  # 旗子要在新客户端就绪之后再落

    webui.bili_restart = apply_room_change
    if client is not None:
        handler.attach_client(client)

    try:
        if args.fake:
            if args.scenario:
                await wait_or_page_exit(fake_room_api.run_scenario(room, args),
                                        page_exit_event, page_exit_enabled)
            else:
                await fake_room_api.run_console(
                    room, stop_event=page_exit_event if page_exit_enabled else None)
        else:
            client.set_handler(handler)
            client.start()
            logger.info(f"已连接到直播间 {room_id}")
            if dglab.enabled and dglab.mode == "embedded":
                logger.info(f"郊狼内置服务已就绪，App 扫码地址：{webui.hub_connect_url()}")
            elif dglab.enabled:
                logger.info(f"郊狼控制已启用（外部 Game Hub）：{dglab.controller_url}")
            await wait_or_page_exit(wait_listening(lifecycle), page_exit_event, page_exit_enabled)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        lifecycle["shutting_down"] = True   # 先立旗：正在退出的中途切换请求一律忽略
        handler.set_stopping()      # 再停掉自动重连，否则退出时会立刻又连一次
        if room is not None:
            room.stop_auto()
        # 退出前把强度释放掉，避免设备停在当前强度上
        try:
            await dglab.release()
        except Exception as e:
            logger.error(f"释放郊狼强度失败: {e}")
        if client is not None:
            await client.stop_and_close()
        if not args.no_webui:
            await webui.stop()
        # 收掉桌面悬浮球（硬杀时它会在失联 60 秒后自行退出）
        if estop_proc is not None:
            try:
                if estop_proc.poll() is None:
                    estop_proc.terminate()
            except Exception:
                pass
        await session.close()
        logger.info("已退出")
    return 0


def run(argv=None, default_fake: bool = False) -> int:
    args = parse_args(argv, default_fake=default_fake)
    try:
        return asyncio.run(main(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(run())
