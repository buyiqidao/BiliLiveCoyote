# -*- coding: utf-8 -*-
"""本地模拟直播间（联调 / 压测工具）

不连接 Bilibili，而是直接构造 Bilibili 直播推送的**原始协议报文**，再交给 blivedm 的解析器
和 BilibiliHandler 处理，因此完整覆盖：

    原始协议 → blivedm 模型 → BilibiliHandler → DGLabController → 郊狼设备

本模块既可以在 `main.py --fake` 下作为库使用，也可以直接运行（等价于 `main.py --fake`）：

    python fake_room.py                                  # WebUI(含测试页) + 交互式控制台
    python main.py --fake                                # 同上，统一入口
    python main.py --test                                # 连真实直播间，同时打开测试页注入事件
    python fake_room.py --scenario mixed --duration 20   # 自动随机事件

交互式命令见控制台里的 `help`。
"""
import asyncio
import base64
import logging
import os
import random
import sys
import threading
import time
import uuid
from collections import Counter, deque

from bilibili import BilibiliHandler
from blivedm.models import pb as pb_models
from web import WebUI

logger = logging.getLogger("fake_room")

GUARD_NAMES = {1: "总督", 2: "提督", 3: "舰长"}

# 与 blivedm.models.web.InteractWordV2Message 的 msg_type 对应
INTERACT_TYPES = {"enter": 1, "follow": 2, "share": 3, "special_follow": 4, "like": 6}
INTERACT_NAMES = {1: "进入房间", 2: "关注", 3: "分享", 4: "特别关注", 6: "点赞"}

FAKE_USERS = [
    "测试观众甲", "路过的猫", "氪金大佬", "白嫖怪", "新来的", "老粉丝",
    "舰长大人", "提督阁下", "总督大人", "夜猫子", "吃瓜群众", "手滑的键盘",
]

# (礼物名, 单价/元) —— 覆盖 config.yaml 里的各个礼物档位
FAKE_GIFTS = [
    ("小心心", 0.1), ("辣条", 0.1), ("亿圆", 1), ("牛哇牛哇", 5),
    ("干杯", 10), ("小花花", 30), ("飞船", 50), ("火箭", 100),
]

SC_PRICES = [30, 50, 100, 500]
DANMAKU_TEXTS = [
    "666", "哈哈哈哈", "这也太强了吧", "主播牛啊", "1", "打卡", "来了来了",
    "笑死我了", "再抽一次", "加大力度",
]

_uid_cache: dict = {}


def _uid_for(name: str) -> int:
    """按用户名生成稳定的假 UID（限流是按 UID 统计的）"""
    if name not in _uid_cache:
        _uid_cache[name] = random.randint(10_000, 99_999_999)
    return _uid_cache[name]


def _rand_user() -> str:
    return random.choice(FAKE_USERS) + random.choice(["", "", "1", "2", "3", "小号"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _face(name: str) -> str:
    return f"https://i0.hdslb.com/bfs/face/{abs(hash(name)) % 10 ** 12}.jpg"


# ── 原始协议报文构造 ────────────────────────────────────────────────────────
def build_danmaku(message: str, username: str = None, guard_level: int = 0,
                  medal_level: int = 0) -> dict:
    """构造 DANMU_MSG 报文（字段下标严格对齐 DanmakuMessage.from_command）"""
    username = username or _rand_user()
    info = [None] * 17
    # info[0]: 弹幕元信息，[15] 是 mode_info，里层取用户头像
    info[0] = [0, 1, 25, 16777215, _now_ms(), 0, "0", "", 0, 0, 0, 0, 0, "", "",
               {"user": {"base": {"face": _face(username)}}}, {}]
    info[1] = message                                   # 弹幕内容
    info[2] = [_uid_for(username), username, 0, 0, 0, 10000, 0, ""]  # 用户信息
    info[3] = [medal_level, "粉丝", "主播", 12345, 6067854, ""] if medal_level else []
    info[4] = [random.randint(1, 40), 0, 0, ">50000"]   # 用户等级
    info[5] = []                                        # 头衔
    info[7] = guard_level                               # 舰队等级
    info[16] = [0]                                      # 荣耀等级
    return {"cmd": "DANMU_MSG", "info": info}


def build_gift(gift_name: str = "辣条", count: int = 1, price: float = 0.1,
               username: str = None, guard_level: int = 0, coin_type: str = "gold") -> dict:
    """构造 SEND_GIFT 报文（价格单位：元/个）"""
    username = username or _rand_user()
    unit_coin = int(round(price * 1000))
    data = {
        "giftName": gift_name,
        "num": count,
        "uname": username,
        "face": _face(username),
        "guard_level": guard_level,
        "uid": _uid_for(username),
        "timestamp": int(time.time()),
        "giftId": abs(hash(gift_name)) % 10000,
        "giftType": 0,
        "gift_info": {"img_basic": ""},
        "action": "赠送",
        "price": unit_coin,
        "rnd": uuid.uuid4().hex,
        "coin_type": coin_type,              # gold=金瓜子（会触发），silver=银瓜子（忽略）
        "total_coin": unit_coin * count,
        "tid": uuid.uuid4().hex,
    }
    return {"cmd": "SEND_GIFT", "data": data}


def build_super_chat(price: int = 30, message: str = "测试醒目留言", username: str = None) -> dict:
    """构造 SUPER_CHAT_MESSAGE 报文（价格单位：元）"""
    username = username or _rand_user()
    now = int(time.time())
    data = {
        "price": int(price),
        "message": message,
        "message_trans": "",
        "start_time": now,
        "end_time": now + 60,
        "time": 60,
        "id": random.randint(1, 10 ** 6),
        "gift": {"gift_id": 12000, "gift_name": "醒目留言"},
        "uid": _uid_for(username),
        "user_info": {
            "uname": username, "face": _face(username),
            "guard_level": 0, "user_level": random.randint(1, 40),
        },
        "background_bottom_color": "#2A60B2",
        "background_color": "#EDF5FF",
        "background_icon": "",
        "background_image": "",
        "background_price_color": "#7497CD",
    }
    return {"cmd": "SUPER_CHAT_MESSAGE", "data": data}


def build_guard(level: int = 3, username: str = None, source: int = 0) -> dict:
    """构造 USER_TOAST_MSG_V2 报文（source=0 付费，source=2 赠送——项目会忽略）"""
    username = username or _rand_user()
    level = int(level)
    price = {1: 1000 * 2000, 2: 1000 * 200, 3: 1000 * 50}.get(level, 1000 * 50)
    now = int(time.time())
    data = {
        "sender_uinfo": {"uid": _uid_for(username), "base": {"name": username}},
        "guard_info": {"guard_level": level, "start_time": now, "end_time": now + 30 * 86400},
        "pay_info": {"num": 1, "price": price, "unit": "月"},
        "gift_info": {"gift_id": 1000},
        "option": {"source": source},
        "toast_msg": f"{username} 在主播的直播间开通了{GUARD_NAMES.get(level, '舰长')}",
    }
    return {"cmd": "USER_TOAST_MSG_V2", "data": data}


def build_interact(action: str = "enter", username: str = None) -> dict:
    """构造 INTERACT_WORD_V2 报文（pb 字段是 base64 的 protobuf）"""
    username = username or _rand_user()
    msg_type = INTERACT_TYPES.get(action, 1)
    proto = pb_models.InteractWordV2(
        uid=_uid_for(username),
        uname=username,
        msg_type=msg_type,
        timestamp=int(time.time()),
        uinfo=pb_models.InteractWordV2UserInfo(
            base=pb_models.InteractWordV2UserBaseInfo(face=_face(username)),
        ),
    )
    return {"cmd": "INTERACT_WORD_V2", "data": {"pb": base64.b64encode(proto.dumps()).decode()}}


# ── 模拟直播间 ──────────────────────────────────────────────────────────────
class FakeLiveRoom:
    """把构造好的原始报文喂给真实的 BilibiliHandler"""

    def __init__(self, handler: BilibiliHandler, webui: WebUI = None):
        self.handler = handler
        self.webui = webui
        self.room_id = 0                      # blivedm 打日志时会用到 client.room_id
        self.stats = Counter()
        self.recent = deque(maxlen=50)
        self.auto_interval = 1.0
        self._auto_task = None

    # ── 基础 ────────────────────────────────────────────────────────────
    def emit(self, command: dict) -> dict:
        """把一条原始报文交给真实处理器"""
        cmd = command.get("cmd", "?")
        self.stats[cmd] += 1
        summary = self._summarize(command)
        self.recent.appendleft({
            "time": time.strftime("%H:%M:%S"),
            "cmd": cmd,
            "summary": summary,
        })
        try:
            self.handler.handle(self, command)
        except Exception as e:
            logger.exception(f"[模拟直播间] 处理 {cmd} 失败")
            return {"ok": False, "error": str(e), "summary": summary}
        return {"ok": True, "cmd": cmd, "summary": summary}

    @staticmethod
    def _summarize(command: dict) -> str:
        cmd = command.get("cmd")
        if cmd == "DANMU_MSG":
            info = command["info"]
            return f'{info[2][1]}：{info[1]}'
        if cmd == "SEND_GIFT":
            d = command["data"]
            return f'{d["uname"]} 送 {d["giftName"]} x{d["num"]}（{d["total_coin"] / 1000:.2f} 元）'
        if cmd == "SUPER_CHAT_MESSAGE":
            d = command["data"]
            return f'{d["user_info"]["uname"]} SC {d["price"]} 元：{d["message"]}'
        if cmd == "USER_TOAST_MSG_V2":
            d = command["data"]
            return f'{d["sender_uinfo"]["base"]["name"]} 开通{GUARD_NAMES.get(d["guard_info"]["guard_level"], "舰长")}'
        if cmd == "INTERACT_WORD_V2":
            return "互动消息"
        return cmd or "?"

    # ── 各类事件 ────────────────────────────────────────────────────────
    def danmaku(self, message: str = None, username: str = None,
                guard_level: int = 0, medal_level: int = 0) -> dict:
        return self.emit(build_danmaku(
            message or random.choice(DANMAKU_TEXTS), username,
            guard_level=guard_level, medal_level=medal_level))

    def gift(self, count: int = 1, price: float = None, gift_name: str = None,
             username: str = None, coin_type: str = "gold") -> dict:
        if gift_name is None or price is None:
            gift_name, price = random.choice(FAKE_GIFTS)
        return self.emit(build_gift(gift_name, count, price, username, coin_type=coin_type))

    def super_chat(self, price: int = None, message: str = None, username: str = None) -> dict:
        return self.emit(build_super_chat(
            price or random.choice(SC_PRICES), message or "测试醒目留言", username))

    def guard(self, level: int = 3, username: str = None, source: int = 0) -> dict:
        return self.emit(build_guard(level, username, source=source))

    def interact(self, action: str = "enter", username: str = None) -> dict:
        return self.emit(build_interact(action, username))

    def random_event(self) -> dict:
        """随机产生一条事件（权重贴近真实直播间的消息比例）"""
        roll = random.random()
        if roll < 0.70:
            return self.danmaku()
        if roll < 0.85:
            return self.gift(count=random.choice([1, 1, 1, 5, 10]))
        if roll < 0.92:
            return self.interact(random.choice(list(INTERACT_TYPES)))
        if roll < 0.97:
            return self.super_chat()
        return self.guard(random.choice([1, 2, 3]))

    def emit_event(self, payload: dict) -> dict:
        """WebUI 测试页调用：把 JSON 转成对应事件"""
        kind = str(payload.get("type", "danmaku")).lower()
        username = (payload.get("username") or "").strip() or None
        if kind == "danmaku":
            return self.danmaku(
                message=(payload.get("message") or "").strip() or None,
                username=username,
                guard_level=int(payload.get("guard_level") or 0),
                medal_level=int(payload.get("medal_level") or 0),
            )
        if kind == "gift":
            return self.gift(
                count=int(payload.get("count") or 1),
                price=float(payload["price"]) if payload.get("price") not in (None, "") else None,
                gift_name=(payload.get("gift_name") or "").strip() or None,
                username=username,
                coin_type=payload.get("coin_type") or "gold",
            )
        if kind == "super_chat":
            return self.super_chat(
                price=int(payload.get("price") or 30),
                message=(payload.get("message") or "").strip() or None,
                username=username,
            )
        if kind == "guard":
            return self.guard(level=int(payload.get("level") or 3), username=username)
        if kind == "interact":
            return self.interact(action=payload.get("action") or "enter", username=username)
        if kind == "random":
            return self.random_event()
        raise ValueError(f"未知事件类型：{kind}")

    # ── 批量 / 自动 ──────────────────────────────────────────────────────
    async def burst(self, kind: str = "danmaku", count: int = 10,
                    interval: float = 0.05, payload: dict = None) -> int:
        """连发 N 条事件，用于压测与限流验证"""
        sent = 0
        for i in range(max(1, int(count))):
            data = dict(payload or {})
            data["type"] = kind
            if kind == "danmaku":
                base = data.get("message") or random.choice(DANMAKU_TEXTS)
                data["message"] = f"{base} #{i + 1}"
            try:
                self.emit_event(data)
                sent += 1
            except Exception as e:
                logger.warning(f"[模拟直播间] 第 {i + 1} 条发送失败：{e}")
            if interval > 0:
                await asyncio.sleep(interval)
        return sent

    @property
    def auto_running(self) -> bool:
        return self._auto_task is not None and not self._auto_task.done()

    def start_auto(self, interval: float = 1.0) -> None:
        self.stop_auto()
        self.auto_interval = max(0.05, float(interval))
        self._auto_task = asyncio.create_task(self._auto_loop())

    def stop_auto(self) -> None:
        if self._auto_task is not None:
            self._auto_task.cancel()
            self._auto_task = None

    async def _auto_loop(self) -> None:
        try:
            while True:
                self.random_event()
                await asyncio.sleep(self.auto_interval)
        except asyncio.CancelledError:
            pass

    # ── 状态 ────────────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "enabled": True,
            "total": sum(self.stats.values()),
            "stats": dict(self.stats),
            "auto": self.auto_running,
            "auto_interval": self.auto_interval,
            "recent": list(self.recent)[:30],
        }


# ── 命令行 ──────────────────────────────────────────────────────────────────
HELP_TEXT = """可用命令：
  dm <内容>            发一条弹幕，例：dm 666
  gift [数量] [单价]   送礼物（单价为元），例：gift 10 5
  sc [金额] [内容]     发醒目留言，例：sc 30 加油
  guard [1|2|3]        开通总督/提督/舰长
  enter|follow|share|special|like   发一条互动消息
  random [n]           随机事件 n 次（默认 1）
  burst <种类> <数量> [间隔]        连发，例：burst danmaku 20 0.05
  auto [间隔]          自动随机刷事件（默认 1 秒一次）
  stop                 停止自动模式
  stats                查看已发送统计
  help / quit
"""


def _print_event(result: dict) -> None:
    if result.get("ok"):
        print(f"   -> {result.get('summary')}")
    else:
        print(f"   x  {result.get('error')}")


async def run_console(room: "FakeLiveRoom", stop_event=None) -> None:
    """交互式控制台

    stop_event：被 set 时立刻退出（主程序用它实现「关掉所有网页就退出」）。
    输入由单独的守护线程负责，这样退出时不会因为 input() 还阻塞着而卡住进程。
    """
    print(HELP_TEXT)
    loop = asyncio.get_running_loop()
    lines: "asyncio.Queue" = asyncio.Queue()

    def _reader():
        # 注意：这里刻意读 dup 出来的流而不是 sys.stdin ——
        # 退出时本线程可能还阻塞在输入上，直接用 sys.stdin 会触发
        # 「Fatal Python error: _enter_buffered_busy ... due to daemon threads」。
        stream = None
        try:
            encoding = getattr(sys.stdin, "encoding", None) or "utf-8"
            stream = os.fdopen(os.dup(0), "r", encoding=encoding, errors="replace")
        except Exception:
            stream = None
        while True:
            try:
                if stream is not None:
                    print("fake-room> ", end="", flush=True)
                    text = stream.readline()
                    if text == "":          # 输入结束
                        text = None
                else:
                    text = input("fake-room> ")
            except (EOFError, KeyboardInterrupt):
                text = None
            except Exception:
                text = None
            try:
                loop.call_soon_threadsafe(lines.put_nowait, text)
            except RuntimeError:        # 事件循环已关闭（正在退出）
                return
            if text is None:
                return

    threading.Thread(target=_reader, daemon=True, name="fake-room-stdin").start()

    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            line = await asyncio.wait_for(lines.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        except (EOFError, KeyboardInterrupt):
            break
        if line is None:
            break
        line = line.strip()
        if not line:
            continue

        parts = line.split(" ", 1)
        cmd = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        args = rest.split()

        if cmd in ("quit", "exit", "q"):
            break
        elif cmd in ("help", "?", "h"):
            print(HELP_TEXT)
        elif cmd in ("dm", "danmaku"):
            _print_event(room.danmaku(rest or None))
        elif cmd == "gift":
            count = int(args[0]) if args else 1
            price = float(args[1]) if len(args) > 1 else None
            _print_event(room.gift(count=count, price=price))
        elif cmd == "sc":
            price = int(args[0]) if args else 30
            msg = " ".join(args[1:]) if len(args) > 1 else None
            _print_event(room.super_chat(price=price, message=msg))
        elif cmd == "guard":
            _print_event(room.guard(int(args[0]) if args else 3))
        elif cmd in INTERACT_TYPES:
            _print_event(room.interact(cmd))
        elif cmd == "random":
            for _ in range(int(args[0]) if args else 1):
                _print_event(room.random_event())
                await asyncio.sleep(0.1)
        elif cmd == "burst":
            if len(args) < 2:
                print("用法：burst <danmaku|gift|sc|guard|interact|random> <数量> [间隔秒]")
            else:
                kind = args[0]
                count = int(args[1])
                interval = float(args[2]) if len(args) > 2 else 0.05
                sent = await room.burst(kind, count, interval)
                print(f"   -> 已发送 {sent} 条 {kind}")
        elif cmd == "auto":
            room.start_auto(float(args[0]) if args else 1.0)
            print(f"   -> 自动模式已开启，间隔 {room.auto_interval}s（stop 停止）")
        elif cmd == "stop":
            room.stop_auto()
            print("   -> 自动模式已停止")
        elif cmd == "stats":
            for name, value in room.stats.most_common():
                print(f"   {name}: {value}")
            print(f"   合计: {sum(room.stats.values())}")
        else:
            print(f"未知命令：{cmd}（输入 help 查看用法）")


async def run_scenario(room: "FakeLiveRoom", args) -> None:
    """非交互式场景（便于脚本化）"""
    name = args.scenario
    if name == "burst":
        sent = await room.burst(args.kind, args.count, args.interval)
        print(f"已发送 {sent} 条 {args.kind}")
    elif name == "mixed":
        interval = max(0.05, args.interval)
        end_at = time.monotonic() + max(1, args.duration)
        print(f"随机事件模式：持续 {args.duration}s，间隔 {interval}s（Ctrl+C 结束）")
        while time.monotonic() < end_at:
            _print_event(room.random_event())
            await asyncio.sleep(interval)
    else:
        raise SystemExit(f"未知场景：{name}")
    await asyncio.sleep(0.5)


if __name__ == "__main__":
    # 独立运行等价于 `python main.py --fake`，避免两套实现
    import sys

    from main import run

    sys.exit(run(default_fake=True))
