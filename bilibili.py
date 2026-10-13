# -*- coding: utf-8 -*-
"""哔哩哔哩直播间监听模块"""
import asyncio
import logging
from typing import Optional

import blivedm
import blivedm.models.web as web_models

from utils import parse_duration, fmt_duration, to_int

logger = logging.getLogger(__name__)

# ── 限流器 ────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, time_window: float, max_count: int, enabled: bool = True):
        self._time_window = time_window
        self._max_count = max_count
        self._enabled = enabled
        self._user_records: dict[int, list[float]] = {}

    def allow(self, uid: int) -> bool:
        """检查用户是否允许触发"""
        if not self._enabled:
            return True
        
        now = asyncio.get_event_loop().time()
        timestamps = [t for t in self._user_records.get(uid, []) if now - t < self._time_window]
        
        if len(timestamps) >= self._max_count:
            self._user_records[uid] = timestamps
            return False
        
        timestamps.append(now)
        self._user_records[uid] = timestamps
        return True

# ── 事件处理器 ────────────────────────────────────────────────────────────────
GUARD_NAME = {1: "总督", 2: "提督", 3: "舰长"}


def spawn(coro, what: str = "后台任务"):
    """创建后台任务并记录异常

    asyncio 的后台任务如果抛异常，默认只会静默丢失（Task exception was never retrieved），
    这里统一挂一个回调，把异常打到日志里，避免控制链路出错时“看起来什么都没发生”。
    """
    task = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task):
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(f"[{what}] 执行异常: {exc!r}")

    task.add_done_callback(_on_done)
    return task


def get_level_config(mapping, level):
    """按舰队等级从配置中取值

    YAML 里等级键是字符串 '1'/'2'/'3'，而推送里的等级可能是 int 也可能是
    str，这里把 level 和 str(int(level)) 都试一遍。
    """
    if not isinstance(mapping, dict):
        return None
    for key in (level, to_int(level), str(level)):
        if key in mapping:
            return mapping[key]
    return None

class BilibiliHandler(blivedm.BaseHandler):
    def __init__(self, config: dict, dglab_controller, webui=None):
        super().__init__()
        self.config = config
        self.dglab = dglab_controller
        self.webui = webui

        # ── 监听状态（首页 / 测试页 / OBS 都能看到到底连上没有）──
        self.connected = False
        self.last_error = ""
        self.message_count = 0
        self.retry_count = 0
        self._stopping = False
        self._reconnect_task = None
        self._client = None

        # 初始化限流器
        rl_cfg = config["danmaku"].get("rate_limit", {})
        self.rate_limiter = RateLimiter(
            time_window=parse_duration(rl_cfg.get("time_window", "1m")),
            max_count=int(rl_cfg.get("max_count", 5)),
            enabled=bool(rl_cfg.get("enabled", True)),
        )

    def handle(self, client, command: dict):
        if command.get("cmd", "") in self._CMD_CALLBACK_DICT:
            # 能收到消息说明连接是活的
            if not self.connected:
                self.connected = True
                self.retry_count = 0
                logger.info("[B站] 直播间监听已就绪")
            self.message_count += 1
            super().handle(client, command)

    # ── 连接状态与自动重连 ──────────────────────────────────────────────
    def set_stopping(self) -> None:
        """程序退出 / 切换房间前调用，避免退出时还触发重连"""
        self._stopping = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None

    def attach_client(self, client) -> None:
        """登记当前生效的客户端

        切换直播间后，旧客户端的 on_client_stopped 仍会被回调，
        这里用「是不是当前客户端」把它挡掉，避免旧连接被重新拉起来。
        """
        self._client = client
        self._stopping = False
        self.connected = False
        self.last_error = ""
        self.retry_count = 0      # 换了客户端就是一次全新的连接

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "last_error": self.last_error,
            "retry_count": self.retry_count,
            "message_count": self.message_count,
            "room_id": self.config.get("bilibili", {}).get("room_id"),
        }

    def on_client_stopped(self, client, exception) -> None:
        """blivedm 客户端停止时回调（连不上 / 被踢 / 网络断开都走这里）

        以前 main.py 把 blivedm 的日志级别设成 CRITICAL，
        这里出什么事用户完全看不到 —— 所以现在必须显式上报。
        """
        self.connected = False
        if self._stopping:
            return
        if self._client is not None and client is not self._client:
            return   # 已被替换掉的旧客户端，忽略

        self.retry_count += 1
        delay = min(60, 5 * self.retry_count)
        if exception is not None:
            self.last_error = f"{type(exception).__name__}: {exception}"
            logger.error(f"[B站] 直播间监听中断：{self.last_error}（{delay} 秒后自动重连）")
        else:
            self.last_error = "连接被关闭"
            logger.warning(f"[B站] 直播间连接已断开（{delay} 秒后自动重连）")

        if self.webui is not None:
            try:
                self.webui.on_bilibili_state_changed()
            except Exception:
                pass

        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._auto_reconnect(client, delay))

    async def _auto_reconnect(self, client, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if self._stopping:
                return
            logger.info(f"[B站] 第 {self.retry_count} 次重连直播间…")
            client.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.last_error = f"重连失败：{e}"
            logger.error(f"[B站] 重连失败：{e}")

    def _on_danmaku(self, client, message: web_models.DanmakuMessage):
        cfg = self.config["danmaku"]
        if not cfg.get("enabled", True):
            return
        
        if not self.rate_limiter.allow(message.uid):
            logger.info(f"[弹幕] {message.uname}：{message.msg} (已达限流上限)")
            return

        add = cfg["strength_add"]
        duration = cfg["duration"]
        # 真实推送里 privilege_type 可能是字符串，先统一成 int
        guard_level = to_int(message.privilege_type)
        logger.info(f"[弹幕] {message.uname}：{message.msg} → +{add} / {fmt_duration(duration)}")
        spawn(self.dglab.pulse(add, duration), "弹幕脉冲")
        
        # 发送到 OBS
        if self.webui:
            spawn(self.webui.broadcast_to_obs('danmaku', {
                'username': message.uname,
                'face': message.face,
                'message': message.msg,
                'guard_level': guard_level if guard_level in (1, 2, 3) else None,
                'dglab': {
                    'strength': add,
                    'duration': fmt_duration(duration)
                } if self.dglab.enabled else None
            }), "OBS 广播")

        # 舰长额外加成
        guard_bonus_cfg = cfg.get("guard_bonus", {})
        if guard_bonus_cfg.get("enabled", False):
            bonus = get_level_config(guard_bonus_cfg, guard_level)
        else:
            bonus = None
        if bonus:
            badd = bonus["strength_add"]
            name = GUARD_NAME.get(guard_level, "")
            logger.info(f"[弹幕·{name}加成] {message.uname} → +{badd} / {fmt_duration(bonus['duration'])}")
            spawn(self.dglab.pulse(badd, bonus["duration"]), "舰长加成")

    def _on_gift(self, client, message: web_models.GiftMessage):
        cfg = self.config["gift"]
        if not cfg.get("enabled", True) or message.coin_type != "gold":
            return
        
        price = message.total_coin / 1000.0
        tier = self._match_tier(cfg["tiers"], price)
        if tier is None:
            logger.info(f"[礼物] {message.uname} {message.gift_name} x{message.num}（{price:.2f} 元）→ 未达最低档位")
            return
        
        add = tier["strength_add"]
        logger.info(f"[礼物] {message.uname} {message.gift_name} x{message.num}（{price:.2f} 元）→ +{add} / {fmt_duration(tier['duration'])}")
        spawn(self.dglab.pulse(add, tier["duration"]), "礼物/SC 脉冲")
        
        # 发送到 OBS
        if self.webui:
            spawn(self.webui.broadcast_to_obs('gift', {
                'username': message.uname,
                'face': message.face,
                'gift_name': message.gift_name,
                'count': message.num,
                'price': f"{price:.2f}",
                'dglab': {
                    'strength': add,
                    'duration': fmt_duration(tier['duration'])
                } if self.dglab.enabled else None
            }), "OBS 广播")

    def _on_super_chat(self, client, message: web_models.SuperChatMessage):
        cfg = self.config["super_chat"]
        if not cfg.get("enabled", True):
            return
        
        tier = self._match_tier(cfg["tiers"], float(message.price))
        if tier is None:
            logger.info(f"[SC {message.price} 元] {message.uname}：{message.message} → 未达最低档位")
            return
        
        add = tier["strength_add"]
        logger.info(f"[SC {message.price} 元] {message.uname}：{message.message} → +{add} / {fmt_duration(tier['duration'])}")
        spawn(self.dglab.pulse(add, tier["duration"]), "礼物/SC 脉冲")
        
        # 发送到 OBS
        if self.webui:
            spawn(self.webui.broadcast_to_obs('sc', {
                'username': message.uname,
                'face': message.face,
                'message': message.message,
                'price': message.price,
                'dglab': {
                    'strength': add,
                    'duration': fmt_duration(tier['duration'])
                } if self.dglab.enabled else None
            }), "OBS 广播")

    def _on_interact_word_v2(self, client, message: web_models.InteractWordV2Message):
        key_map = {1: "enter", 2: "follow", 3: "share", 4: "special_follow"}
        name_map = {1: "进入房间", 2: "关注", 3: "分享", 4: "特别关注"}
        
        key = key_map.get(message.msg_type)
        if not key:
            return
        
        ecfg = self.config.get("interact", {}).get(key, {})
        if not ecfg.get("enabled", False):
            return
        
        add = ecfg["strength_add"]
        logger.info(f"[{name_map[message.msg_type]}] {message.username} → +{add} / {fmt_duration(ecfg['duration'])}")
        spawn(self.dglab.pulse(add, ecfg["duration"]), "互动脉冲")

    def _on_user_toast_v2(self, client, message: web_models.UserToastV2Message):
        cfg = self.config["guard"]
        if not cfg.get("enabled", True) or message.source == 2:
            return
        
        # 真实推送里 guard_level 可能是字符串 "1"，不归一化会导致「名字显示成舰长、数值却是总督」
        guard_level = to_int(message.guard_level)
        lcfg = get_level_config(cfg.get("levels", {}), guard_level)
        if lcfg is None:
            return
        
        add = lcfg["strength_add"]
        name = GUARD_NAME.get(guard_level, f"等级{guard_level}")
        logger.info(f"[上舰] {message.username} 开通{name} → +{add} / {fmt_duration(lcfg['duration'])}")
        spawn(self.dglab.pulse(add, lcfg["duration"]), "上舰脉冲")
        
        # 发送到 OBS
        if self.webui:
            spawn(self.webui.broadcast_to_obs('guard', {
                'username': message.username,
                'guard_level': guard_level,
                'dglab': {
                    'strength': add,
                    'duration': fmt_duration(lcfg['duration'])
                } if self.dglab.enabled else None
            }), "OBS 广播")

    @staticmethod
    def _match_tier(tiers: list, price: float) -> Optional[dict]:
        sorted_tiers = sorted(tiers, key=lambda t: t["min_price"], reverse=True)
        return next((t for t in sorted_tiers if price >= t["min_price"]), None)
