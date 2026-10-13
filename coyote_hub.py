# -*- coding: utf-8 -*-
"""内置郊狼服务（DG-Lab SOCKET 协议服务端）

把 DG-Lab Coyote Game Hub 的设备侧能力直接内置到本项目：
官方「郊狼」App 通过 SOCKET 控制扫描二维码连接到本服务后，本项目即可直接控制设备，
无需再额外安装 / 运行 Node.js 版 Game Hub。

协议（bind / heartbeat / msg）参考自
https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub ，
本文件是按协议重新实现的（未复制其源码）。
内置波形数据 pulses.json 由该项目 server/data/pulse.json5 转换而来。

⚠️ 许可：该项目的 LICENSE 文件是 GNU GPL v3（package.json 里写的是 MIT，
上游两处不一致）。因此本项目整体按 GPL-3.0 分发 ——
归属声明见 LICENSE-GameHub，许可全文见 LICENSE，第三方组件见 THIRD_PARTY_LICENSES.md。
"""
import asyncio
import json
import logging
import os
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── 协议常量 ────────────────────────────────────────────────────────────────
MSG_HEARTBEAT = "heartbeat"
MSG_BIND = "bind"
MSG_MSG = "msg"
MSG_BREAK = "break"

RET_SUCCESS = "200"
RET_CLIENT_DISCONNECTED = "209"

DG_LAB = "DGLAB"

CHANNEL_A = 1
CHANNEL_B = 2

# strength-<channel>+<operation>+<value>，operation=2 表示直接设置强度
STRENGTH_OP_SET = 2

HEARTBEAT_INTERVAL = 20.0   # 心跳间隔（秒）
BIND_TIMEOUT = 10.0         # 等待设备绑定超时（秒）
PULSE_WINDOW = 0.1          # 每帧波形在设备上的播放时长（秒）
DEFAULT_STRENGTH_LIMIT = 100

FALLBACK_PULSE = {"id": "default", "name": "默认", "pulseData": ["0A0A0A0A00000000"]}
from utils import resource_path

PULSE_FILE = resource_path("pulses.json")


def load_pulse_list(path: str = PULSE_FILE) -> list:
    """读取内置波形列表"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        pulses = [
            p for p in data
            if isinstance(p, dict) and p.get("pulseData") and p.get("id")
        ]
        if pulses:
            return pulses
    except Exception as e:
        logger.warning(f"[郊狼] 读取内置波形失败：{e}")
    return [FALLBACK_PULSE]


class DGDeviceSession:
    """一个已连接的郊狼设备（官方 App 的 SOCKET 连接）"""

    def __init__(self, client_id: str, ws, hub: "CoyoteHub"):
        self.client_id = client_id
        self.ws = ws
        self.hub = hub

        self.target_id = ""
        self.bound = False
        self.ready = False   # 复位完成、可以接受控制指令
        self.closed = False

        # 设备上报的实时强度 / 上限
        self.strength = {CHANNEL_A: 0, CHANNEL_B: 0}
        self.limit = {CHANNEL_A: 0, CHANNEL_B: 0}

        # 本机维护的“目标强度”，用于叠加多次 add / sub
        self.target_strength = {CHANNEL_A: 0, CHANNEL_B: 0}

        self.connected_at = time.time()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._pulse_task: Optional[asyncio.Task] = None

    # ── 发送 ────────────────────────────────────────────────────────────
    async def send(self, message_type: str, message) -> bool:
        if self.closed:
            return False
        payload = json.dumps({
            "type": message_type,
            "clientId": self.client_id,
            "targetId": self.target_id,
            "message": str(message),
        }, ensure_ascii=False)
        try:
            await self.ws.send_str(payload)
            return True
        except Exception as e:
            logger.debug(f"[郊狼] 发送失败：{e}")
            self.closed = True
            return False

    async def set_strength(self, channel: int, value: int) -> bool:
        value = max(0, int(value))
        return await self.send(MSG_MSG, f"strength-{channel}+{STRENGTH_OP_SET}+{value}")

    async def send_pulse(self, channel: int, pulse_data: list) -> bool:
        channel_name = "A" if channel == CHANNEL_A else "B"
        return await self.send(MSG_MSG, f"pulse-{channel_name}:{json.dumps(pulse_data)}")

    async def clear_pulse(self, channel: int) -> bool:
        return await self.send(MSG_MSG, f"clear-{channel}")

    # ── 生命周期 ────────────────────────────────────────────────────────
    async def initialize(self) -> bool:
        # 1) 请求绑定（message="targetId"，与 Game Hub 一致）
        await self.send(MSG_BIND, "targetId")

        deadline = time.monotonic() + BIND_TIMEOUT
        while not self.bound and not self.closed and time.monotonic() < deadline:
            await asyncio.sleep(0.1)

        if not self.bound:
            logger.warning(f"[郊狼] 设备 {self.client_id} 绑定超时")
            return False

        logger.info(f"[郊狼] 设备已绑定：{self.client_id} → {self.target_id}")

        # 2) 复位两个通道后立即就绪。WebSocket 本身保序，后续指令一定排在复位之后，
        #    这里不需要再 sleep，否则这段窗口内的事件会被判为“设备未连接”而丢弃。
        await self.reset()

        # 3) 启动心跳与波形输出
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._pulse_task = asyncio.create_task(self._pulse_loop())
        self.ready = True
        self.hub.notify()
        return True

    async def reset(self) -> None:
        for channel in (CHANNEL_A, CHANNEL_B):
            self.target_strength[channel] = 0
            await self.clear_pulse(channel)
        await self.set_strength(CHANNEL_A, 0)
        await self.set_strength(CHANNEL_B, 0)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.ready = False

        for task in (self._heartbeat_task, self._pulse_task):
            if task:
                task.cancel()

        try:
            await self.send(MSG_BREAK, RET_CLIENT_DISCONNECTED)
        except Exception:
            pass
        try:
            await self.ws.close()
        except Exception:
            pass

        logger.info(f"[郊狼] 设备已断开：{self.client_id}")
        self.hub.notify()

    # ── 后台任务 ────────────────────────────────────────────────────────
    async def _heartbeat_loop(self) -> None:
        try:
            while not self.closed:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not await self.send(MSG_HEARTBEAT, RET_SUCCESS):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[郊狼] 心跳异常：{e}")

    async def _pulse_loop(self) -> None:
        """持续下发波形数据，让设备在强度 > 0 时真正有输出"""
        pulse_id = None
        pulse_data = list(FALLBACK_PULSE["pulseData"])
        frame_time = 0.2
        next_send = 0.0
        try:
            while not self.closed:
                now = time.monotonic()
                active = [ch for ch in (CHANNEL_A, CHANNEL_B) if self.target_strength.get(ch, 0) > 0]
                if not active:
                    next_send = 0.0
                    await asyncio.sleep(0.1)
                    continue

                # 实时读取波形配置：改配置后无需重连即可生效
                pulse = self.hub.current_pulse()
                if pulse.get("id") != pulse_id:
                    pulse_id = pulse.get("id")
                    pulse_data = list(pulse.get("pulseData") or FALLBACK_PULSE["pulseData"])
                    frame_time = max(len(pulse_data) * PULSE_WINDOW, 0.2)

                # 提前半个周期补发，保证设备缓冲里始终有数据，避免整段播完后出现空档
                if now >= next_send:
                    for channel in active:
                        if not await self.send_pulse(channel, pulse_data):
                            return
                    next_send = now + frame_time * 0.5
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[郊狼] 波形下发异常：{e}")

    # ── 收发 ────────────────────────────────────────────────────────────
    async def handle_message(self, raw) -> None:
        try:
            message = json.loads(raw)
        except Exception:
            logger.debug(f"[郊狼] 收到非法消息：{raw!r}")
            return

        msg_type = message.get("type", "")
        body = str(message.get("message", ""))

        if msg_type == MSG_BIND:
            if body == DG_LAB:
                self.target_id = str(message.get("targetId") or self.target_id or self.client_id)
                self.bound = True
                await self.send(MSG_BIND, RET_SUCCESS)
            else:
                logger.warning(f"[郊狼] 绑定失败：{body}")

        elif msg_type == MSG_HEARTBEAT:
            if body != DG_LAB:
                logger.debug(f"[郊狼] 心跳异常：{body}")

        elif msg_type == MSG_MSG:
            if body.startswith("strength-"):
                self._handle_strength_report(body)
            elif body.startswith("feedback-"):
                logger.info(f"[郊狼] 收到设备按键反馈：{body}")

        elif msg_type == MSG_BREAK:
            logger.info(f"[郊狼] 设备主动断开：{body}")
            self.closed = True

    def _handle_strength_report(self, body: str) -> None:
        """解析 strength-<A>+<B>+<Alimit>+<Blimit>"""
        try:
            parts = body.split("-", 1)[1].split("+")
            if len(parts) < 4:
                return
            self.strength[CHANNEL_A] = int(parts[0])
            self.strength[CHANNEL_B] = int(parts[1])
            self.limit[CHANNEL_A] = int(parts[2])
            self.limit[CHANNEL_B] = int(parts[3])
            self.hub.notify()
        except Exception:
            logger.debug(f"[郊狼] 无法解析强度上报：{body}")

    # ── 控制 ────────────────────────────────────────────────────────────
    def channel_limit(self, channel: int) -> int:
        return self.limit.get(channel) or DEFAULT_STRENGTH_LIMIT

    async def change_strength(self, delta: int, channel: int = CHANNEL_A) -> dict:
        """按增量调整强度，返回本次调整的详细结果（含是否被上限截断）"""
        current = self.target_strength.get(channel, 0)
        limit = self.channel_limit(channel)
        want = current + int(delta)
        target = max(0, min(want, limit))
        self.target_strength[channel] = target
        await self.set_strength(channel, target)
        return {
            "ok": True,
            "channel": channel,
            "current": current,
            "target": target,
            "limit": limit,
            "clamped": want > limit,
        }


class CoyoteHub:
    """内置郊狼服务：管理设备连接 + 对外提供控制接口"""

    def __init__(self, config: dict):
        self.config = config
        self.pulses = load_pulse_list()
        self.sessions: dict = {}
        self._log_times: dict = {}
        # 状态变化回调（WebUI 用它把实时强度推给 OBS）
        self._listeners: list = []

    # ── 状态变化通知 ────────────────────────────────────────────────────
    def add_listener(self, callback) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def notify(self) -> None:
        """状态（强度 / 上限 / 连接）发生变化时通知监听者"""
        for callback in list(self._listeners):
            try:
                callback()
            except Exception as e:
                logger.debug(f"[郊狼] 状态回调异常：{e}")

    # ── 配置 ────────────────────────────────────────────────────────────
    @property
    def cfg(self) -> dict:
        return self.config.setdefault("dglab", {})

    @property
    def client_id(self) -> str:
        return str(self.cfg.get("client_id") or "blivedglab")

    @property
    def pulse_id(self) -> str:
        return str(self.cfg.get("pulse_id") or "")

    def current_pulse(self) -> dict:
        for pulse in self.pulses:
            if pulse["id"] == self.pulse_id:
                return pulse
        return self.pulses[0] if self.pulses else FALLBACK_PULSE

    def get_pulse(self, pulse_id: str) -> Optional[dict]:
        for pulse in self.pulses:
            if pulse["id"] == pulse_id:
                return pulse
        return None

    # ── 状态 ────────────────────────────────────────────────────────────
    def primary(self) -> Optional[DGDeviceSession]:
        """返回已完成初始化的设备连接"""
        for session in self.sessions.values():
            if session.bound and session.ready and not session.closed:
                return session
        return None

    @property
    def connected(self) -> bool:
        return self.primary() is not None

    def status(self) -> dict:
        session = self.primary()
        if session is None:
            return {
                "connected": False,
                "client_id": self.client_id,
                "target_id": "",
                "strength_a": 0,
                "strength_b": 0,
                "limit_a": 0,
                "limit_b": 0,
                "target_a": 0,
                "target_b": 0,
                "pulse": self.current_pulse().get("name", ""),
            }
        return {
            "connected": True,
            "client_id": session.client_id,
            "target_id": session.target_id,
            "strength_a": session.strength[CHANNEL_A],
            "strength_b": session.strength[CHANNEL_B],
            "limit_a": session.limit[CHANNEL_A],
            "limit_b": session.limit[CHANNEL_B],
            # 程序侧维护的目标强度：与“设备上报强度”是两个不同的量，
            # 分开暴露以免用户看到两套数字时困惑。
            "target_a": session.target_strength.get(CHANNEL_A, 0),
            "target_b": session.target_strength.get(CHANNEL_B, 0),
            "pulse": self.current_pulse().get("name", ""),
        }

    # ── 设备接入 ────────────────────────────────────────────────────────
    @staticmethod
    async def _read_loop(session: DGDeviceSession, ws) -> None:
        """持续读取设备消息（必须与初始化并行，否则收不到绑定回执）"""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await session.handle_message(msg.data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.debug(f"[郊狼] WebSocket 错误：{msg.data}")
                break
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                break

    async def serve(self, ws, client_id: str) -> None:
        """处理一条来自官方 App 的 SOCKET 连接"""
        old = self.sessions.get(client_id)
        if old is not None:
            # 同 ID 重复连接：踢掉旧的
            await old.close()

        session = DGDeviceSession(client_id, ws, self)
        self.sessions[client_id] = session
        reader: Optional[asyncio.Task] = None

        try:
            reader = asyncio.create_task(self._read_loop(session, ws))
            if not await session.initialize():
                return
            await reader
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[郊狼] 连接处理异常：{e}")
        finally:
            if reader is not None and not reader.done():
                reader.cancel()
            await session.close()
            if self.sessions.get(client_id) is session:
                self.sessions.pop(client_id, None)

    # ── 控制接口（供 DGLabController 调用）──────────────────────────────
    async def release(self) -> bool:
        """把 A/B 两个通道都归零"""
        session = self.primary()
        if session is None:
            return False
        for channel in (CHANNEL_A, CHANNEL_B):
            session.target_strength[channel] = 0
            # 除了把强度归零，顺手清空波形缓冲，确保设备彻底安静
            await session.clear_pulse(channel)
            await session.set_strength(channel, 0)
        self.notify()
        return True

    async def change_strength(self, delta: int, channel: int = CHANNEL_A) -> dict:
        if not delta:
            return {"ok": True, "channel": channel, "clamped": False, "limit": 0, "target": 0}
        session = self.primary()
        if session is None:
            # 上层 DGLabController 会做限流提示，这里只留调试信息避免重复刷屏
            logger.debug("[郊狼] 设备未连接，忽略强度调整")
            return {"ok": False, "reason": "offline", "channel": channel, "clamped": False,
                    "limit": 0, "target": 0}
        result = await session.change_strength(delta, channel)
        self.notify()
        if result.get("clamped"):
            self._log_throttled(
                f"limit-{channel}",
                f"[郊狼] {'A' if channel == CHANNEL_A else 'B'} 通道已达强度上限 {result['limit']}，"
                f"无法继续提升（上限由郊狼 App 设置，程序无法修改）"
            )
        return result

    async def set_strength(self, value: int, channel: int = CHANNEL_A) -> dict:
        session = self.primary()
        if session is None:
            logger.debug("[郊狼] 设备未连接，忽略强度设置")
            return {"ok": False, "reason": "offline", "channel": channel, "clamped": False,
                    "limit": 0, "target": 0}
        limit = session.channel_limit(channel)
        want = int(value)
        target = max(0, min(want, limit))
        session.target_strength[channel] = target
        await session.set_strength(channel, target)
        self.notify()
        return {"ok": True, "channel": channel, "target": target, "limit": limit,
                "clamped": want > limit}

    def _log_throttled(self, key: str, message: str, interval: float = 30.0) -> None:
        """同一 key 的日志在 interval 秒内只输出一次（到达上限时弹幕会持续触发）"""
        now = time.monotonic()
        if now - self._log_times.get(key, 0.0) < interval:
            return
        self._log_times[key] = now
        logger.info(message)

    # 官方 App 的 deep link 前缀：扫码/点击后会唤起 App 并填入后面的 ws 地址
    DEEP_LINK_PREFIX = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"

    def ws_url(self, host: str, port: int) -> str:
        """纯 WebSocket 地址，适合在 App 里手动输入"""
        return f"ws://{host}:{port}/dglab_ws/{self.client_id}"

    def connect_url(self, host: str, port: int, raw: bool = False) -> str:
        """连接地址；raw=True 返回纯 ws:// 地址，否则返回官方 deep link"""
        ws = self.ws_url(host, port)
        return ws if raw else f"{self.DEEP_LINK_PREFIX}{ws}"
