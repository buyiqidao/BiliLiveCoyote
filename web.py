# -*- coding: utf-8 -*-
"""Web UI 模块"""
import asyncio
import io as _io
import json
import logging
import os
import socket
import sys
import time
from collections import deque
from datetime import datetime

import yaml
from aiohttp import web

import bili_login
from coyote_hub import CoyoteHub, CHANNEL_A, CHANNEL_B
from utils import config_path, resource_path

logger = logging.getLogger(__name__)


# OBS 覆盖层默认布局（坐标/宽高均为百分比，0 表示自动）
DEFAULT_OBS_LAYOUT = {
    "strength": {"x": 1, "y": 1, "w": 0, "h": 0, "visible": True},
    "price": {"x": 18, "y": 1, "w": 0, "h": 0, "visible": True},
    "danmaku": {"x": 1, "y": 36, "w": 30, "h": 62, "visible": True},
}

OBS_LAYOUT_FIELDS = ("x", "y", "w", "h")

# ── 「关掉所有网页就退出」相关 ──────────────────────────────────────────
# 每个页面都会定时打一次心跳；超过 STALE 秒没动静就当成已经关掉了
# （后台标签页会被浏览器降频到大约 1 分钟一次，所以窗口给得宽松一点）
PAGE_STALE_SECONDS = 90.0
# 最后一个页面关掉后再等一会儿才退出，避免刷新 / 跳页误判
PAGE_EXIT_GRACE_SECONDS = 5.0
PRESENCE_SCRIPT = '<script src="/static/presence.js"></script>'


def inject_presence(html: str) -> str:
    """把「页面心跳」脚本塞进每个页面（服务端统一注入，免得漏掉某个页面）"""
    if PRESENCE_SCRIPT in html:
        return html
    idx = html.rfind("</body>")
    if idx == -1:
        return html + "\n" + PRESENCE_SCRIPT
    return html[:idx] + PRESENCE_SCRIPT + "\n" + html[idx:]


def sanitize_obs_layout(raw: dict) -> dict:
    """把前端传来的布局洗成合法值（百分比 0~100），缺项用默认值补齐"""
    raw = raw if isinstance(raw, dict) else {}
    layout = {}
    for key, default in DEFAULT_OBS_LAYOUT.items():
        item = raw.get(key) if isinstance(raw.get(key), dict) else {}
        out = dict(default)
        for field in OBS_LAYOUT_FIELDS:
            if field in item:
                try:
                    value = float(item[field])
                except (TypeError, ValueError):
                    continue
                out[field] = max(0.0, min(100.0, value))
        if "visible" in item:
            out["visible"] = bool(item["visible"])
        layout[key] = out
    return layout


class PortInUseError(RuntimeError):
    """WebUI 监听端口已被占用"""

    def __init__(self, host: str, port: int):
        super().__init__(f"端口 {host}:{port} 已被占用")
        self.host = host
        self.port = port

class WebUI:
    """Web UI 服务器"""
    
    def __init__(self, config: dict, dglab_controller, host: str = "0.0.0.0", port: int = 17800,
                 hub=None, session=None):
        self.config = config
        self.dglab = dglab_controller
        self.host = host
        self.port = port
        # 复用一个 aiohttp 会话（扫码登录等外部请求用）
        self.session = session or getattr(dglab_controller, "session", None)
        # 由 main.py 注入：直播间监听处理器 / 热切换房间的回调
        self.bili_handler = None
        self.bili_restart = None
        # 内置郊狼服务（embedded 模式），与 DGLabController 共用同一个实例
        self.hub = hub if hub is not None else CoyoteHub(config)
        self.app = web.Application()
        self.runner = None
        self.site = None
        
        # 日志缓冲区（最多保存 200 条）
        self.log_buffer = deque(maxlen=200)
        self.danmaku_log_buffer = deque(maxlen=100)  # 弹幕日志
        self.dglab_log_buffer = deque(maxlen=100)    # 郊狼日志
        self.obs_history = deque(maxlen=50)  # OBS 历史记录（最近50条）
        self.websockets = set()
        self.obs_websockets = set()  # OBS 专用 WebSocket 连接

        # 「关掉所有网页就退出」的状态（由 main.py 按配置打开）
        #   page_exit_event：所有网页都关了时 set()，主循环据此退出
        #   count_obs_pages：OBS 里的浏览器源（embed）算不算「网页」
        self.exit_when_page_closed = False
        self.count_obs_pages = False
        self.page_exit_event = None
        self.pages = {}          # page_id -> {"last": 时间, "obs": 是否 OBS 页面}
        self._seen_page = False  # 启动后至少有过一个「算数」的页面，否则永不自动退出
        self._empty_since = None
        self._page_task = None
        self._request_shutdown = False
        # 本地模拟直播间（由 fake_room.py 注入），为 None 时测试接口不可用
        self.fake_room = None

        # 设置路由
        self._setup_routes()
        
        # 设备状态变化 → 推给 OBS（合并高频更新）
        self.hub.add_listener(self._on_hub_state_changed)
        self._strength_task = None
        self._strength_dirty = False

        # 添加日志处理器
        self._setup_logging()
    
    def _setup_routes(self):
        """设置路由"""
        # 静态文件
        html_dir = resource_path("html")
        self.app.router.add_static('/static', os.path.join(html_dir, 'static'))
        
        # 页面路由
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/config.html', self.handle_config_page)
        self.app.router.add_get('/obs.html', self.handle_obs_page)
        self.app.router.add_get('/obs-source.html', self.handle_obs_source_page)
        # 三个「独立浏览器源」：各自一个链接，在 OBS 里分别摆放
        self.app.router.add_get('/obs/strength', self.handle_obs_source_page)
        self.app.router.add_get('/obs/price', self.handle_obs_source_page)
        self.app.router.add_get('/obs/danmaku', self.handle_obs_source_page)
        self.app.router.add_get('/coyote.html', self.handle_coyote_page)
        self.app.router.add_get('/login.html', self.handle_login_page)
        self.app.router.add_get('/test.html', self.handle_test_page)

        # 本地模拟直播间（测试工具）
        self.app.router.add_get('/api/test/status', self.handle_test_status)
        self.app.router.add_post('/api/test/event', self.handle_test_event)
        self.app.router.add_post('/api/test/auto', self.handle_test_auto)

        # 内置郊狼服务
        self.app.router.add_get('/dglab_ws/{client_id}', self.handle_dglab_ws)
        self.app.router.add_route('*', '/dglab_ws', self.handle_dglab_ws_no_id)
        self.app.router.add_route('*', '/dglab_ws/', self.handle_dglab_ws_no_id)
        self.app.router.add_get('/api/hub/status', self.handle_hub_status)
        self.app.router.add_get('/api/hub/qrcode', self.handle_hub_qrcode)
        self.app.router.add_post('/api/hub/strength', self.handle_hub_strength)
        self.app.router.add_post('/api/hub/allow-lan', self.handle_hub_allow_lan)
        self.app.router.add_post('/api/hub/emergency-stop', self.handle_emergency_stop)
        self.app.router.add_post('/api/hub/resume', self.handle_resume)
        
        # API 路由
        self.app.router.add_get('/api/config', self.handle_get_config)
        self.app.router.add_get('/api/config/full', self.handle_get_full_config)
        self.app.router.add_post('/api/config/save', self.handle_save_config)
        self.app.router.add_get('/api/logs', self.handle_get_logs)
        self.app.router.add_get('/api/obs/history', self.handle_get_obs_history)
        self.app.router.add_get('/api/obs/live', self.handle_get_obs_live)
        self.app.router.add_get('/api/obs/price-table', self.handle_get_price_table)
        # Bilibili 扫码登录 / 房间号解析 / 总状态
        self.app.router.add_post('/api/bilibili/qrcode', self.handle_bili_qrcode)
        self.app.router.add_get('/api/bilibili/login', self.handle_bili_login_state)
        self.app.router.add_get('/api/bilibili/qrcode/status', self.handle_bili_qrcode_status)
        self.app.router.add_post('/api/bilibili/room/resolve', self.handle_bili_resolve_room)
        self.app.router.add_post('/api/page/heartbeat', self.handle_page_heartbeat)
        self.app.router.add_post('/api/page/leave', self.handle_page_leave)
        self.app.router.add_get('/api/status', self.handle_status)
        self.app.router.add_get('/api/health', self.handle_health)

        self.app.router.add_get('/api/obs/layout', self.handle_get_obs_layout)
        self.app.router.add_post('/api/obs/layout', self.handle_save_obs_layout)
        self.app.router.add_get('/ws', self.handle_websocket)
        self.app.router.add_get('/ws/obs', self.handle_obs_websocket)
    
    def _setup_logging(self):
        """设置日志处理器以捕获日志"""
        class WebLogHandler(logging.Handler):
            def __init__(self, webui):
                super().__init__()
                self.webui = webui
            
            def emit(self, record):
                try:
                    message = self.format(record)
                    log_entry = {
                        'time': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
                        'level': record.levelname,
                        'message': message
                    }
                    
                    # 添加到总日志
                    self.webui.log_buffer.append(log_entry)
                    
                    # 检查是否有运行中的事件循环
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        # 没有运行的事件循环，跳过广播
                        return
                    
                    # 根据消息内容分类
                    if any(keyword in message for keyword in ['[弹幕', '[礼物', '[SC', '[上舰', '[进入', '[关注', '[分享']):
                        self.webui.danmaku_log_buffer.append(log_entry)
                        asyncio.create_task(self.webui.broadcast_log(log_entry, 'danmaku'))
                    elif '[DGLab]' in message or '[郊狼]' in message or '[手动控制]' in message:
                        self.webui.dglab_log_buffer.append(log_entry)
                        asyncio.create_task(self.webui.broadcast_log(log_entry, 'dglab'))
                    else:
                        # 其他日志广播到全部
                        asyncio.create_task(self.webui.broadcast_log(log_entry, 'all'))
                except Exception:
                    # 忽略日志处理中的错误，避免影响程序退出
                    pass
        
        handler = WebLogHandler(self)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(handler)
        self.log_handler = handler
    
    async def broadcast_log(self, log_entry, log_type='all'):
        """广播日志到所有 WebSocket 连接"""
        if self.websockets:
            message = json.dumps({'type': 'log', 'log_type': log_type, 'data': log_entry})
            await asyncio.gather(
                *[ws.send_str(message) for ws in self.websockets],
                return_exceptions=True
            )
    
    def _read_page(self, name: str) -> str:
        with open(resource_path("html", name), 'r', encoding='utf-8') as f:
            return f.read()

    def _page_response(self, html: str) -> web.Response:
        """返回页面（自动注入「页面心跳」脚本）"""
        if not self.exit_when_page_closed:
            return web.Response(text=html, content_type='text/html')
        return web.Response(text=inject_presence(html), content_type='text/html')

    async def handle_index(self, request):
        """首页"""
        return self._page_response(self._read_page("index.html"))

    async def handle_config_page(self, request):
        """配置页面"""
        return self._page_response(self._read_page("config.html"))

    async def handle_obs_page(self, request):
        """OBS 页面"""
        return self._page_response(self._read_page("obs.html"))
    
    # 可以单独渲染的区块（对应 /obs/<name> 与 ?only=<name>）
    OBS_BLOCKS = ("strength", "price", "danmaku")

    def _resolve_obs_block(self, request) -> str:
        """从路径或查询参数里解析出「只渲染哪个区块」"""
        name = ""
        path = request.path.rstrip("/")
        if path.startswith("/obs/"):
            name = path[len("/obs/"):].lower()
        if name not in self.OBS_BLOCKS:
            name = ""
        if not name:
            query = (request.query.get("only") or "").lower()
            name = query if query in self.OBS_BLOCKS else ""
        return name

    async def handle_obs_source_page(self, request):
        """OBS 浏览器源页面

        /obs/strength、/obs/price、/obs/danmaku 只渲染对应区块（供 OBS 单独摆位），
        其余情况渲染完整组合页面。
        """
        only = self._resolve_obs_block(request)
        html = self._read_page("obs-source.html")
        if only:
            # 服务端直接把模式写进 <body>，CSS 立刻生效，避免首帧闪出三个区块
            html = html.replace(
                "<body>", f'<body class="obs-single" data-only="{only}">', 1
            )
            # OBS 新增浏览器源时会拿页面标题当源名字，这里按区块给个能认出来的标题
            label = {"strength": "电流强度", "price": "投喂价格表", "danmaku": "弹幕列表"}.get(only)
            if label:
                html = html.replace("<title>OBS 覆盖层 · BiliLiveCoyote</title>",
                                    f"<title>BiliLiveCoyote · {label}</title>", 1)
        return self._page_response(html)

    async def handle_login_page(self, request):
        """扫码登录页（启动时自动打开，用于刷新登录凭证）"""
        return self._page_response(self._read_page("login.html"))

    async def handle_test_page(self, request):
        """模拟直播间测试页"""
        return self._page_response(self._read_page("test.html"))

    # ── 本地模拟直播间 ──────────────────────────────────────────────────
    def _fake_room_or_404(self):
        if self.fake_room is None:
            raise web.HTTPNotFound(text="测试工具未启用（请使用 python fake_room.py 启动）")
        return self.fake_room

    async def handle_test_status(self, request):
        """测试页状态；未启用时返回 enabled=false，前端据此给出提示"""
        if self.fake_room is None:
            return web.json_response({"enabled": False})
        data = self.fake_room.status()
        data["dglab_enabled"] = self.dglab.enabled
        data["dglab_mode"] = self.dglab.mode
        return web.json_response(data)

    async def handle_test_event(self, request):
        """发送一条 / 一批模拟事件"""
        room = self._fake_room_or_404()
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({'success': False, 'error': '请求体必须是 JSON'}, status=400)

        count = int(payload.get("count") or 1)
        interval = float(payload.get("interval") or 0)
        try:
            if count > 1:
                sent = await room.burst(
                    kind=str(payload.get("type", "danmaku")),
                    count=count,
                    interval=max(0.0, interval),
                    payload=payload,
                )
                return web.json_response({'success': True, 'sent': sent, 'status': room.status()})
            result = room.emit_event(payload)
            return web.json_response({'success': bool(result.get('ok')),
                                      'result': result,
                                      'status': room.status()})
        except Exception as e:
            logger.error(f"模拟事件失败: {e}")
            return web.json_response({'success': False, 'error': str(e)}, status=400)

    async def handle_test_auto(self, request):
        """开关自动随机事件"""
        room = self._fake_room_or_404()
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if payload.get("enabled"):
            room.start_auto(float(payload.get("interval") or 1.0))
        else:
            room.stop_auto()
        logger.info(f"[模拟直播间] 自动模式 {'开启' if room.auto_running else '关闭'}")
        return web.json_response({'success': True, 'status': room.status()})

    async def handle_coyote_page(self, request):
        """郊狼控制页面"""
        return self._page_response(self._read_page("coyote.html"))

    # ── 页面心跳（「关掉所有网页就退出」）──────────────────────────────
    async def handle_page_heartbeat(self, request):
        """页面还开着：记一下时间

        - `obs=1`：这是 /obs/... 覆盖层页面
        - `embed=1`：它跑在 OBS 的浏览器源里（不是人盯着的浏览器标签页）

        `count_obs_pages: false` 只把**OBS 浏览器源**排除在外；
        自己用浏览器打开 /obs/... 预览时必须照常算「有人在看网页」，
        否则停在 OBS 页面上会被误判成「网页都关了」。
        """
        pid = request.query.get("id") or ""
        if pid:
            obs = request.query.get("obs") == "1"
            embed = request.query.get("embed") == "1"
            counted = bool(self.count_obs_pages) or not embed
            self.pages[pid] = {"last": time.monotonic(), "obs": obs,
                               "embed": embed, "counted": counted}
            if counted:
                self._seen_page = True
        return web.json_response({"success": True, "count": len(self.pages)})

    async def handle_page_leave(self, request):
        """页面关掉了（pagehide / unload 的 sendBeacon）"""
        pid = request.query.get("id") or ""
        self.pages.pop(pid, None)
        return web.json_response({"success": True, "count": len(self.pages)})

    def pages_alive(self) -> int:
        """还活着的「算数」页面数量"""
        now = time.monotonic()
        for pid, info in list(self.pages.items()):
            if now - info["last"] > PAGE_STALE_SECONDS:
                self.pages.pop(pid, None)
        count = 0
        for info in self.pages.values():
            if "counted" in info:
                count += 1 if info["counted"] else 0
            else:   # 老记录（没有 counted 字段）
                count += 1 if (self.count_obs_pages or not info.get("obs")) else 0
        return count

    async def _page_watch_loop(self) -> None:
        """盯着页面数量：启动后曾经有过页面，且现在一个都不剩 → 到点退出"""
        while True:
            await asyncio.sleep(1.0)
            try:
                alive = self.pages_alive()
            except Exception:
                continue
            now = time.monotonic()
            if not self._seen_page or alive > 0:
                self._empty_since = None
                continue
            if self._empty_since is None:
                self._empty_since = now
                logger.info(f"检测到所有网页都已关闭，{PAGE_EXIT_GRACE_SECONDS:.0f} 秒后自动退出"
                            "（不想这样可设置 webui.exit_when_page_closed: false）")
                continue
            if now - self._empty_since >= PAGE_EXIT_GRACE_SECONDS:
                logger.info("所有网页已关闭，程序自动退出")
                if self.page_exit_event is not None:
                    self.page_exit_event.set()
                else:
                    self._request_shutdown = True
                return

    def start_page_watch(self) -> None:
        """启动页面数量监视（只在开启「关掉所有网页就退出」时调用）"""
        if self._page_task is None or self._page_task.done():
            self._page_task = asyncio.ensure_future(self._page_watch_loop())

    # ── 内置郊狼服务 ────────────────────────────────────────────────────
    @property
    def bound_addresses(self) -> list:
        """WebUI 实际绑定的地址列表"""
        try:
            return [sock.getsockname()[0]
                    for sock in (getattr(self.site, "_server", None).sockets or [])]
        except Exception:
            return [self.host]

    @property
    def lan_ready(self) -> bool:
        """是否监听在非回环地址上（手机等局域网设备能否连进来）"""
        return any(addr not in ("127.0.0.1", "::1", "localhost") for addr in self.bound_addresses)

    @staticmethod
    def _lan_ip() -> str:
        """获取本机在局域网中的 IP（用于生成 App 扫码地址）"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def hub_connect_host(self) -> str:
        """对外广播使用的主机名/IP"""
        host = str(self.config.get("dglab", {}).get("advertise_host") or "").strip()
        if not host:
            host = self._lan_ip() if self.host in ("", "0.0.0.0", "127.0.0.1", "localhost") else self.host
        return host

    def hub_connect_url(self, raw: bool = False) -> str:
        """官方 App 连接地址（默认 deep link，raw=True 时为纯 ws:// 地址）"""
        return self.hub.connect_url(self.hub_connect_host(), self.port, raw=raw)

    async def handle_dglab_ws(self, request):
        """官方郊狼 App 的 SOCKET 连接入口"""
        client_id = request.match_info.get('client_id', '') or 'default'
        peer = request.transport.get_extra_info('peername') if request.transport else None
        ua = request.headers.get('User-Agent', '-')
        logger.info(f"[郊狼] 收到设备连接请求：client_id={client_id} 来自 {peer} UA={ua}")

        ws = web.WebSocketResponse(heartbeat=None)
        try:
            await ws.prepare(request)
        except Exception as e:
            logger.warning(
                f"[郊狼] 来自 {peer} 的请求不是合法的 WebSocket（{e}）"
                f"——如果这是浏览器或 HTTP 工具直接访问，属于正常现象"
            )
            raise
        try:
            await self.hub.serve(ws, client_id)
        finally:
            if not ws.closed:
                await ws.close()
        return ws

    async def handle_dglab_ws_no_id(self, request):
        """地址漏了客户端 ID 时的兜底提示"""
        peer = request.transport.get_extra_info('peername') if request.transport else None
        logger.warning(
            f"[郊狼] 来自 {peer} 的连接缺少客户端 ID：{request.path}"
            f"（正确格式为 /dglab_ws/<客户端ID>）"
        )
        return web.json_response(
            {'status': 0, 'code': 'ERR::INVALID_CLIENT_ID',
             'message': '缺少客户端 ID，正确地址形如 ws://<ip>:<port>/dglab_ws/blivedglab'},
            status=400,
        )

    async def handle_hub_status(self, request):
        """内置郊狼服务状态"""
        status = self.hub.status()
        status['mode'] = self.dglab.mode
        status['enabled'] = self.dglab.enabled
        status['server_url'] = self.hub_connect_url()
        status['ws_url'] = self.hub_connect_url(raw=True)
        status['connect_host'] = self.hub_connect_host()
        status['connect_port'] = self.port
        status['bind_host'] = self.host
        status['bound_addresses'] = self.bound_addresses
        status['lan_ready'] = self.lan_ready
        status['controller_url'] = self.dglab.controller_url
        status['pulses'] = [{'id': p['id'], 'name': p.get('name', '')} for p in self.hub.pulses]
        status['pulse_id'] = self.hub.current_pulse().get('id', '')
        return web.json_response(status)

    # ── 紧急停堆 ────────────────────────────────────────────────────────
    async def handle_emergency_stop(self, request):
        """紧急停堆：强度归零 + 关闭控制，并把 dglab.enabled=false 写回配置

        写回配置是刻意的：紧急停堆后即使程序重启，也仍然是「关闭」状态，不会自己恢复。
        """
        try:
            already = self.dglab.enabled is False
            result = await self.dglab.emergency_stop()
            self.config.setdefault("dglab", {})["enabled"] = False
            # 已经处于停堆状态（例如连点两次 / 两个悬浮球）就不再重复写配置文件，
            # 避免重复落盘和无意义的备份/告警。
            if already:
                logger.info("[紧急停堆] 已处于停堆状态，仅重复确认归零，不再写配置")
            else:
                try:
                    self._write_config_file()
                except Exception as e:
                    logger.warning(f"紧急停堆：配置写回失败（不影响本次生效）：{e}")

            # 立刻让 OBS / 页面看到状态变化
            self._on_hub_state_changed()
            status = self.hub.status()
            logger.warning("[紧急停堆] 强度已归零、郊狼控制已关闭；"
                           "恢复请再点一次悬浮按钮，或到配置页重新勾选「启用郊狼控制器」")
            return web.json_response({
                'success': True,
                'enabled': False,
                'cancelled': result.get('cancelled', 0),
                'status': status,
                'message': ('已紧急停堆：强度归零、控制关闭'
                            + (f'（取消了 {result["cancelled"]} 个进行中的脉冲）'
                               if result.get('cancelled') else '')),
            })
        except Exception as e:
            logger.error(f"紧急停堆失败: {e}")
            return web.json_response({'success': False, 'error': str(e)}, status=500)

    async def handle_resume(self, request):
        """恢复郊狼控制（紧急停堆的逆操作）"""
        try:
            await self.dglab.resume()
            self.config.setdefault("dglab", {})["enabled"] = True
            try:
                self._write_config_file()
            except Exception as e:
                logger.warning(f"恢复控制：配置写回失败（不影响本次生效）：{e}")
            self._on_hub_state_changed()
            status = self.hub.status()
            logger.info("[紧急停堆] 已恢复郊狼控制")
            return web.json_response({
                'success': True,
                'enabled': True,
                'status': status,
                'message': '已恢复郊狼控制，弹幕/礼物会重新控制设备',
            })
        except Exception as e:
            logger.error(f"恢复控制失败: {e}")
            return web.json_response({'success': False, 'error': str(e)}, status=500)

    async def handle_hub_allow_lan(self, request):
        """把 WebUI 从回环地址重新绑定到 0.0.0.0，让手机能连进来"""
        if self.lan_ready:
            return web.json_response({'success': True, 'message': '已经在监听所有网卡',
                                      'status': self.hub.status()})
        old_host = self.host
        try:
            await self.site.stop()
        except Exception:
            pass
        try:
            self.host = "0.0.0.0"
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
        except Exception as e:
            # 失败则回滚，避免把服务弄挂
            logger.error(f"切换监听地址失败，正在回滚：{e}")
            self.host = old_host
            try:
                self.site = web.TCPSite(self.runner, self.host, self.port)
                await self.site.start()
            except Exception as e2:
                logger.error(f"回滚失败：{e2}")
            return web.json_response({'success': False, 'error': str(e)}, status=500)

        self.port = self._resolve_bound_port()
        self.config.setdefault("webui", {})["host"] = "0.0.0.0"
        try:
            self._write_config_file()
        except Exception as e:
            logger.warning(f"配置写回失败（不影响本次运行）：{e}")

        logger.info(f"WebUI 已改为监听 0.0.0.0:{self.port}，局域网内可访问")
        status = self.hub.status()
        status['bind_host'] = self.host
        status['bound_addresses'] = self.bound_addresses
        status['lan_ready'] = self.lan_ready
        return web.json_response({'success': True, 'message': '已开启局域网访问', 'status': status})

    @staticmethod
    def _merge_config(doc: dict, new: dict) -> None:
        """把 new 合并进 doc（原地改），保留 doc 里已有的注释 / 键顺序

        注意：**不能整体替换列表**。ruamel.yaml 会把「列表后面那段注释」
        挂在这个列表对象上，一旦 `doc[key] = [...新建的普通列表...]`，
        注释就跟着没了（gift.tiers / super_chat.tiers 后面就各有一段）。
        """
        for key in list(doc.keys()):
            if key not in new:
                del doc[key]
        for key, value in new.items():
            current = doc.get(key)
            if isinstance(value, dict) and isinstance(current, dict):
                WebUI._merge_config(current, value)
            elif isinstance(value, list) and isinstance(current, list):
                # 逐项原地更新，尽量不动列表对象本身
                shared = min(len(current), len(value))
                for i in range(shared):
                    c_item, v_item = current[i], value[i]
                    if isinstance(c_item, dict) and isinstance(v_item, dict):
                        WebUI._merge_config(c_item, v_item)
                    else:
                        current[i] = v_item
                if len(value) > len(current):
                    for v_item in value[shared:]:
                        current.append(v_item)
                elif len(value) < len(current):
                    del current[shared:]
            else:
                doc[key] = value

    @staticmethod
    def _count_comments(text: str) -> int:
        return sum(1 for line in (text or "").splitlines() if line.strip().startswith("#"))

    def _write_config_file(self) -> str:
        """把内存里的配置写回 config.yaml

        优先用 ruamel.yaml —— 它能**保留注释和键顺序**；
        没有装的话退回 PyYAML（保持键顺序，但注释会丢，会打 ERROR 并留 .bak）。

        另外写了自检：如果注释行数变少（说明被洗了），直接报错并保留备份，
        避免像之前那样"悄无声息地把配置文件注释清空"。
        """
        path = config_path()

        # 读旧内容 + 备份，供自检和善后
        before = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                before = f.read()
        except Exception:
            pass
        before_comments = self._count_comments(before)

        # 备份策略：只保留「注释最全」的那一份。
        # 否则第一次写回洗掉注释后，第二次写回会把 .bak 也覆盖成没注释的版本，
        # 好备份就再也找不回来了。
        backup = path + ".bak"
        try:
            old_backup_comments = -1
            if os.path.exists(backup):
                with open(backup, "r", encoding="utf-8") as f:
                    old_backup_comments = self._count_comments(f.read())
            if before.strip() and before_comments >= old_backup_comments:
                with open(backup, "w", encoding="utf-8") as f:
                    f.write(before)
        except Exception:
            pass

        try:
            from ruamel.yaml import YAML
            rt = YAML()
            rt.preserve_quotes = True
            rt.width = 4096
            with open(path, "r", encoding="utf-8") as f:
                doc = rt.load(f)
            if doc is None:
                raise ValueError("配置文件为空")
            self._merge_config(doc, self.config)
            with open(path, "w", encoding="utf-8") as f:
                rt.dump(doc, f)
            return self._verify_config_write(path, before_comments)
        except ImportError:
            logger.debug("未安装 ruamel.yaml，回退到 PyYAML（注释会丢失）")
        except Exception as e:
            logger.warning(f"用 ruamel.yaml 写回失败，改用 PyYAML：{e}")

        if before_comments:
            logger.error(
                "未安装 ruamel.yaml，写回配置会丢失 %d 行注释（已备份到 %s.bak，"
                "建议执行 pip install ruamel.yaml）", before_comments, path
            )
        try:
            with open(path, "w", encoding="utf-8") as f:
                if before_comments:
                    f.write("# 本次保存由 PyYAML 回退写入，原有注释已丢失。" + chr(10)
                            + f"# 带注释的历史版本见：{os.path.basename(path)}.bak" + chr(10)
                            + "# 执行 pip install ruamel.yaml 后即可正常保留注释。" + chr(10))
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False,
                          sort_keys=False)
        except Exception as e:
            logger.error(f"写回配置失败：{e}")
        return self._verify_config_write(path, before_comments)

    def _verify_config_write(self, path: str, before_comments: int) -> str:
        """写回后自检：注释不能凭空变少，否则报警并指出备份位置"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                after = f.read()
        except Exception:
            return path
        after_comments = self._count_comments(after)
        if before_comments and after_comments < before_comments:
            logger.error(
                "配置写回后注释从 %d 行变成 %d 行！已保留写回前版本：%s.bak（"
                "安装 ruamel.yaml 可避免此问题）", before_comments, after_comments, path
            )
        return path

    async def handle_hub_qrcode(self, request):
        """生成 App 扫码用的二维码（SVG）

        ?format=raw 时二维码内容为纯 ws:// 地址（部分 App 版本只认这个）。
        """
        raw = request.query.get('format', 'link').lower() in ('raw', 'ws', 'plain')
        url = self.hub_connect_url(raw=raw)
        try:
            import qrcode
            import qrcode.image.svg
            image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2)
            buf = _io.BytesIO()
            image.save(buf)
            return web.Response(
                body=buf.getvalue(),
                content_type='image/svg+xml',
                headers={'Cache-Control': 'no-store'},
            )
        except Exception as e:
            logger.warning(f"生成二维码失败：{e}")
            return web.json_response({'success': False, 'error': str(e), 'url': url}, status=500)

    async def handle_hub_strength(self, request):
        """手动调整强度（郊狼控制页面使用）"""
        if not self.dglab.enabled:
            return web.json_response({'success': False, 'error': '郊狼控制器已禁用'})
        if self.dglab.mode != 'embedded':
            return web.json_response({'success': False, 'error': '当前为外部 Game Hub 模式，请使用外部控制台'})

        try:
            data = await request.json()
            channel = CHANNEL_B if str(data.get('channel', 'A')).upper() == 'B' else CHANNEL_A
            if data.get('add') is not None:
                result = await self.hub.change_strength(int(data['add']), channel)
            elif data.get('sub') is not None:
                result = await self.hub.change_strength(-int(data['sub']), channel)
            else:
                result = await self.hub.set_strength(int(data.get('set', 0)), channel)

            status = self.hub.status()
            if not result.get('ok'):
                return web.json_response({'success': False, 'error': '设备未连接', 'status': status})

            message = ''
            if result.get('clamped'):
                message = (f"已达强度上限 {result['limit']}，无法继续提升。"
                           f"上限来自郊狼设备（由 App 设置），程序无法修改。")
            logger.info(
                f"[手动控制] {'B' if channel == CHANNEL_B else 'A'} 通道 → "
                f"A:{status['strength_a']}/{status['limit_a']} B:{status['strength_b']}/{status['limit_b']}"
                + (f"（{message}）" if message else "")
            )
            return web.json_response({
                'success': True,
                'status': status,
                'clamped': bool(result.get('clamped')),
                'limit': result.get('limit'),
                'target': result.get('target'),
                'message': message,
            })
        except Exception as e:
            logger.error(f"手动控制失败: {e}")
            return web.json_response({'success': False, 'error': str(e)})
    
    async def handle_get_config(self, request):
        """获取基本配置"""
        safe_config = {
            'bilibili': {
                'room_id': self.config['bilibili']['room_id']
            },
            'dglab': {
                'enabled': self.config['dglab'].get('enabled', True),
                'controller_id': self.config['dglab']['controller_id']
            }
        }
        return web.json_response(safe_config)
    
    async def handle_get_full_config(self, request):
        """获取完整配置"""
        return web.json_response(self.config)
    
    async def handle_save_config(self, request):
        """保存配置"""
        try:
            new_config = await request.json()
            
            # 更新内存中的配置
            self.config.clear()
            self.config.update(new_config)

            # 保存到 config.yaml
            self._write_config_file()
            
            # 更新 DGLab 控制器的启用状态
            self.dglab.enabled = new_config['dglab'].get('enabled', True)
            
            logger.info("配置已保存并重新加载")
            return web.json_response({'success': True, 'message': '配置已保存并生效！'})
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return web.json_response({'success': False, 'error': str(e)})
    
    async def handle_get_logs(self, request):
        """获取历史日志"""
        log_type = request.query.get('type', 'all')
        if log_type == 'danmaku':
            return web.json_response(list(self.danmaku_log_buffer))
        elif log_type == 'dglab':
            return web.json_response(list(self.dglab_log_buffer))
        else:
            return web.json_response(list(self.log_buffer))
    
    async def handle_websocket(self, request):
        """WebSocket 连接"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websockets.add(ws)
        
        try:
            async for msg in ws:
                pass  # 暂不处理客户端消息
        finally:
            self.websockets.discard(ws)
        
        return ws
    
    async def handle_obs_websocket(self, request):
        """OBS WebSocket 连接"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.obs_websockets.add(ws)
        
        try:
            async for msg in ws:
                pass
        finally:
            self.obs_websockets.discard(ws)
        
        return ws
    
    async def broadcast_to_obs(self, message_type: str, data: dict, history: bool = True):
        """广播消息到 OBS WebSocket（history=False 时不写入历史记录）"""
        # 保存到历史记录
        if history:
            self.obs_history.append({'type': message_type, 'data': data})
        
        # 广播到所有连接的 OBS 客户端
        if self.obs_websockets:
            message = json.dumps({'type': message_type, 'data': data})
            await asyncio.gather(
                *[ws.send_str(message) for ws in self.obs_websockets],
                return_exceptions=True
            )
    
    async def handle_get_obs_history(self, request):
        """获取 OBS 历史记录"""
        return web.json_response(list(self.obs_history))

    # ── OBS 实时数据 ────────────────────────────────────────────────────
    def _on_hub_state_changed(self) -> None:
        """设备状态变化回调（可能在事件循环里被高频调用，这里做合并）

        注意：不能简单地"有任务在跑就丢弃"，否则广播 await 期间到达的变化会永久丢失
        （设备上报就是在广播过程中回来的）。这里用 dirty 标记保证"最终一定会推一次最新值"。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._strength_dirty = True
        if self._strength_task is not None and not self._strength_task.done():
            return
        self._strength_task = loop.create_task(self._push_strength_loop())

    async def _push_strength_loop(self) -> None:
        """一直推到没有新变化为止（合并高频更新，同时不丢最后一次更新）"""
        while self._strength_dirty:
            self._strength_dirty = False
            await asyncio.sleep(0)   # 让出一轮，把同一批变化合并成一条消息
            try:
                await self.broadcast_to_obs('strength', self.obs_live_data(), history=False)
            except Exception as e:
                logger.debug(f"推送实时强度失败：{e}")

    def obs_live_data(self) -> dict:
        """OBS 覆盖层需要的实时数据"""
        status = self.hub.status()
        status['enabled'] = self.dglab.enabled
        status['mode'] = self.dglab.mode
        return status

    async def handle_get_obs_live(self, request):
        """OBS 页面初次加载时拉一次实时状态"""
        return web.json_response(self.obs_live_data())

    # ── Bilibili 扫码登录 / 房间号 ──────────────────────────────────────
    def _http_session(self):
        session = self.session or getattr(self.dglab, "session", None)
        if session is None:
            raise RuntimeError("没有可用的 HTTP 会话")
        return session

    async def handle_bili_qrcode(self, request):
        """生成登录二维码（前端拿到 qr_svg 直接内嵌显示）"""
        try:
            qr = await bili_login.generate_qrcode(self._http_session())
            return web.json_response({
                "success": True,
                "key": qr["key"],
                "url": qr["url"],
                "qr_svg": bili_login.make_qr_svg(qr["url"]),
            })
        except Exception as e:
            logger.warning(f"生成登录二维码失败：{e}")
            return web.json_response({"success": False, "error": str(e)}, status=502)

    async def handle_bili_login_state(self, request):
        """当前 B 站登录态（配置页用来显示「已登录 xxx / 未登录 / 已失效」）"""
        bili_cfg = self.config.get("bilibili") or {}
        has_saved = bool(bili_cfg.get("cookies") or bili_cfg.get("sessdata"))
        try:
            state = await bili_login.check_login(self._http_session())
        except Exception as e:
            state = {"is_login": False, "error": str(e)}
        state["has_saved_cookie"] = has_saved
        state["cookie_count"] = len(bili_cfg.get("cookies") or {})
        state["success"] = True
        return web.json_response(state)

    async def handle_bili_qrcode_status(self, request):
        """轮询扫码状态；登录成功后自动写入 SESSDATA + 直播间号并热切换监听"""
        key = request.query.get("key", "")
        if not key:
            return web.json_response({"success": False, "error": "缺少 key"}, status=400)
        try:
            state = await bili_login.poll_qrcode(self._http_session(), key)
        except Exception as e:
            logger.warning(f"查询扫码状态失败：{e}")
            return web.json_response({"success": False, "error": str(e)}, status=502)

        if not state.get("ok"):
            return web.json_response({
                "success": True, "login": False,
                "state": state.get("status"), "message": state.get("message"),
                "expired": state.get("status_code") == bili_login.QR_EXPIRED,
            })

        # ── 登录成功 ──
        sessdata = state.get("sessdata") or ""
        bili_cfg = self.config.setdefault("bilibili", {})
        if sessdata:
            bili_cfg["sessdata"] = sessdata
        # 关键：把整登录态 cookie 都存下来（含 buvid3/buvid4 等设备指纹），
        # 只存 SESSDATA 的话重启后容易被当成新设备，导致「每次打开都要重新扫码」
        persist = bili_login.pick_persist_cookies(state.get("cookies") or {})
        if persist:
            bili_cfg["cookies"] = persist
            logger.info(f"已保存 B 站登录 cookie {len(persist)} 项（重启后自动恢复）")
        logger.info("Bilibili 扫码登录成功")

        room = None
        try:
            room = await bili_login.fetch_live_room(self._http_session())
            room_id_new = (room or {}).get("room_id")
            if room_id_new:
                bili_cfg["room_id"] = room_id_new
                # live_info 接口不返回 uname/title，再补一次公开的房间信息
                try:
                    info = await bili_login.fetch_room_info(self._http_session(), room_id_new)
                    for key in ("uname", "title", "live_status"):
                        if not room.get(key) and info.get(key) is not None:
                            room[key] = info[key]
                except Exception as e:
                    logger.debug(f"补充房间信息失败：{e}")
                logger.info(f"已获取到你的直播间：{room.get('uname') or '未知主播'} / {room_id_new}"
                            + (f"（{room.get('title')}）" if room.get("title") else ""))
        except Exception as e:
            logger.warning(f"登录成功但获取直播间信息失败：{e}")

        try:
            self._write_config_file()
        except Exception as e:
            logger.warning(f"保存登录信息失败：{e}")

        switched = False
        if room and room.get("room_id") and self.bili_restart:
            try:
                await self.bili_restart(room["room_id"])
                switched = True
            except Exception as e:
                logger.warning(f"切换直播间失败：{e}")

        return web.json_response({
            "success": True, "login": True,
            "sessdata_saved": bool(sessdata),
            "room": room, "switched": switched,
            "message": "登录成功，直播间信息已自动填入",
        })

    async def handle_bili_resolve_room(self, request):
        """把用户填的房间号 / 短号 / 直播链接解析成真实房间号并热切换"""
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        value = (payload.get("room") or "").strip()
        if not value:
            return web.json_response({"success": False, "error": "请输入房间号或直播间链接"}, status=400)
        try:
            resolved = await bili_login.resolve_room_id(self._http_session(), value)
            room_id = resolved.get("room_id")
            self.config.setdefault("bilibili", {})["room_id"] = room_id
            self._write_config_file()
            switched = False
            if self.bili_restart:
                await self.bili_restart(room_id)
                switched = True
            info = {}
            try:
                info = await bili_login.fetch_room_info(self._http_session(), room_id)
            except Exception:
                pass
            return web.json_response({"success": True, "room": {**resolved, **info},
                                      "switched": switched})
        except Exception as e:
            logger.warning(f"解析房间号失败：{e}")
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_health(self, request):
        """运行环境自检（配置页据此提示缺失依赖）"""
        from utils import ruamel_available
        if not ruamel_available():
            logger.debug("健康检查：缺少 ruamel.yaml")
        return web.json_response({
            "success": True,
            "ruamel": ruamel_available(),
            "python": sys.version.split()[0],
        })

    async def handle_status(self, request):
        """总状态：直播间监听 + 郊狼 + 测试模式"""
        bili = self.bili_handler.status() if self.bili_handler else {}
        dglab = self.hub.status()
        dglab["enabled"] = self.dglab.enabled
        dglab["mode"] = self.dglab.mode
        return web.json_response({
            "bilibili": bili,
            "dglab": dglab,
            "test_mode": self.fake_room is not None,
        })

    def on_bilibili_state_changed(self) -> None:
        """直播间连接状态变化时通知（目前用于立即刷新页面）"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.broadcast_to_obs('bili_state', self.bili_handler.status(), history=False))

    async def handle_get_obs_layout(self, request):
        """OBS 覆盖层布局（元素位置/大小，百分比）"""
        saved = (self.config.get("obs") or {}).get("layout")
        return web.json_response({
            "layout": sanitize_obs_layout(saved),
            "default": DEFAULT_OBS_LAYOUT,
            "customized": bool(saved),
        })

    async def handle_save_obs_layout(self, request):
        """保存 OBS 覆盖层布局到 config.yaml"""
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({'success': False, 'error': '请求体必须是 JSON'}, status=400)

        raw = payload.get("layout") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            return web.json_response({'success': False, 'error': '缺少 layout 字段'}, status=400)

        layout = sanitize_obs_layout(raw)
        self.config.setdefault("obs", {})["layout"] = layout
        try:
            self._write_config_file()
        except Exception as e:
            logger.warning(f"OBS 布局写回失败（本次已生效）：{e}")

        logger.info("OBS 布局已更新："
                    + ", ".join(f"{k}=({v['x']:.0f}%,{v['y']:.0f}%)" for k, v in layout.items()))
        return web.json_response({'success': True, 'layout': layout})

    async def handle_get_price_table(self, request):
        """投喂价格表（直接来自 config.yaml，改完配置刷新页面即可生效）"""
        cfg = self.config
        danmaku = cfg.get("danmaku", {})
        table = {
            'danmaku': ({
                'enabled': True,
                'strength_add': danmaku.get('strength_add', 0),
                'duration': danmaku.get('duration', ''),
            } if danmaku.get('enabled', True) else {'enabled': False}),
            'gift': [],
            'super_chat': [],
            'guard': [],
            'interact': [],
        }

        gift = cfg.get("gift", {})
        if gift.get('enabled', True):
            table['gift'] = sorted(
                [{'min_price': t.get('min_price', 0), 'strength_add': t.get('strength_add', 0),
                  'duration': t.get('duration', '')} for t in gift.get('tiers', [])],
                key=lambda t: t['min_price'],
            )

        sc = cfg.get("super_chat", {})
        if sc.get('enabled', True):
            table['super_chat'] = sorted(
                [{'min_price': t.get('min_price', 0), 'strength_add': t.get('strength_add', 0),
                  'duration': t.get('duration', '')} for t in sc.get('tiers', [])],
                key=lambda t: t['min_price'],
            )

        guard = cfg.get("guard", {})
        if guard.get('enabled', True):
            names = {1: '总督', 2: '提督', 3: '舰长'}
            for level in (3, 2, 1):   # 由低到高
                lv = str(level)
                if lv in guard.get('levels', {}):
                    item = guard['levels'][lv]
                    table['guard'].append({
                        'level': level, 'name': names[level],
                        'strength_add': item.get('strength_add', 0),
                        'duration': item.get('duration', ''),
                    })

        interact = cfg.get("interact", {})
        interact_names = {'enter': '进入房间', 'follow': '关注', 'share': '分享', 'special_follow': '特别关注'}
        for key, name in interact_names.items():
            item = interact.get(key, {})
            if item.get('enabled'):
                table['interact'].append({
                    'name': name,
                    'strength_add': item.get('strength_add', 0),
                    'duration': item.get('duration', ''),
                })

        return web.json_response(table)
    
    async def start(self):
        """启动 Web 服务器"""
        # 禁用 aiohttp 访问日志
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        try:
            await self.site.start()
        except OSError as e:
            try:
                await self.runner.cleanup()
            except Exception:
                pass
            self.runner = None
            self.site = None
            # 48=Linux/macOS EADDRINUSE，98=部分平台，10048=Windows WSAEADDRINUSE
            if getattr(e, "errno", None) in (48, 98, 10048) or "10048" in str(e):
                raise PortInUseError(self.host, self.port) from e
            raise

        self.port = self._resolve_bound_port()
        display_host = "localhost" if self.host == "0.0.0.0" else self.host
        logger.info(f"WebUI 已启动: http://{display_host}:{self.port}")

        if self.exit_when_page_closed:
            self.start_page_watch()
            self._request_shutdown = False
            logger.info("已开启「关掉所有网页后自动退出」"
                        f"（OBS 里的浏览器源{'算' if self.count_obs_pages else '不算'}网页，"
                        "浏览器里打开的 /obs 页面照常算）")

        # 内置郊狼服务需要手机连进来，只监听回环地址时手机必然连不上
        if self.dglab.mode == "embedded" and not self.lan_ready:
            logger.warning(
                "WebUI 只监听 %s，手机等局域网设备无法访问郊狼服务；"
                "请把 config.yaml 的 webui.host 改成 0.0.0.0 后重启，"
                "或在「郊狼控制」页面点击「开启局域网访问」", self.host
            )

    def _resolve_bound_port(self) -> int:
        """端口传 0 时由系统随机分配，这里把真实端口读回来"""
        try:
            sockets = getattr(getattr(self.site, "_server", None), "sockets", None) or []
            if sockets:
                return int(sockets[0].getsockname()[1])
        except Exception:
            pass
        return self.port
    
    async def stop(self):
        """停止 Web 服务器"""
        if self._page_task is not None:
            self._page_task.cancel()
            try:
                await self._page_task
            except (asyncio.CancelledError, Exception):
                pass
            self._page_task = None

        # 关闭已连接的郊狼设备
        for session in list(self.hub.sessions.values()):
            try:
                await session.close()
            except Exception:
                pass
        self.hub.sessions.clear()

        # 移除日志处理器，避免退出时的错误
        if hasattr(self, 'log_handler'):
            logging.getLogger().removeHandler(self.log_handler)
        
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("WebUI 已停止")
