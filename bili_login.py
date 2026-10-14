# -*- coding: utf-8 -*-
"""Bilibili 扫码登录 / 直播间信息获取

把「填房间号 + 手动复制 SESSDATA」这套麻烦流程换成**扫码**：
    生成二维码 → 手机 B 站 App 扫码 → 自动拿到 cookie → 自动填入直播间号

用到的都是 B 站公开的 web 接口，请求必须带正常的 User-Agent / Referer，
否则会被风控拦成 HTTP 412。
"""
import io
import json
import logging
import re
from typing import Optional

import aiohttp

import aiohttp_compat  # noqa: F401  # aiohttp / brotli 多版本兼容补丁（导入即生效）

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

BASE_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
LIVE_INFO = "https://api.live.bilibili.com/xlive/web-ucenter/user/live_info"
ROOM_INIT = "https://api.live.bilibili.com/room/v1/Room/room_init"
ROOM_INFO = "https://api.live.bilibili.com/room/v1/Room/get_info"
COOKIE_URL = "https://www.bilibili.com/"

# 扫码状态码
QR_OK = 0           # 登录成功
QR_EXPIRED = 86038  # 二维码已失效
QR_SCANNED = 86090  # 已扫码，等待确认
QR_WAITING = 86101  # 未扫码

QR_STATUS_TEXT = {
    QR_WAITING: "等待扫码",
    QR_SCANNED: "已扫码，请在手机上确认",
    QR_EXPIRED: "二维码已过期，请刷新",
    QR_OK: "登录成功",
}


class BiliLoginError(RuntimeError):
    """扫码 / 接口调用失败"""


async def _read_json(resp, what: str) -> dict:
    text = await resp.text()
    if resp.status != 200:
        raise BiliLoginError(f"{what}失败：HTTP {resp.status}（可能被风控拦截）")
    try:
        return json.loads(text)
    except Exception:
        head = (text or "").strip()[:80]
        raise BiliLoginError(f"{what}失败：返回的不是 JSON（{head}）")


# ── 扫码登录 ────────────────────────────────────────────────────────────────
async def generate_qrcode(session: aiohttp.ClientSession) -> dict:
    """申请一个登录二维码，返回 {url, key}"""
    async with session.get(QR_GENERATE, headers=BASE_HEADERS,
                           timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await _read_json(resp, "生成二维码")
    payload = data.get("data") or {}
    url, key = payload.get("url"), payload.get("qrcode_key")
    if not url or not key:
        raise BiliLoginError(f"生成二维码失败：{data.get('message') or data}")
    return {"url": url, "key": key}


def extract_cookies(session: aiohttp.ClientSession) -> dict:
    """从会话 cookie 罐里取出 bilibili 的 cookie"""
    out = {}
    try:
        from yarl import URL
        for name, morsel in session.cookie_jar.filter_cookies(URL(COOKIE_URL)).items():
            out[name] = morsel.value
    except Exception as e:
        logger.debug(f"读取 cookie 失败：{e}")
    return out


async def poll_qrcode(session: aiohttp.ClientSession, key: str) -> dict:
    """查询扫码状态；登录成功后 cookie 会自动进到 session 里"""
    async with session.get(QR_POLL, params={"qrcode_key": key}, headers=BASE_HEADERS,
                           timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await _read_json(resp, "查询扫码状态")

    payload = data.get("data") or {}
    code = payload.get("code")
    result = {
        "status_code": code,
        "status": {v: k for k, v in QR_STATUS_TEXT.items()}.get(
            QR_STATUS_TEXT.get(code, ""), "unknown") if code in QR_STATUS_TEXT else "unknown",
        "message": payload.get("message") or QR_STATUS_TEXT.get(code, ""),
        "ok": code == QR_OK,
    }
    if code == QR_OK:
        cookies = extract_cookies(session)
        result["cookies"] = cookies
        result["sessdata"] = cookies.get("SESSDATA", "")
        result["logged_in"] = bool(result["sessdata"])
    return result


# ── 直播间信息 ──────────────────────────────────────────────────────────────
def parse_room_input(value) -> Optional[int]:
    """从「房间号 / 短号 / 直播间链接」里抠出数字

    支持：1796101901、'https://live.bilibili.com/1796101901?x=1'、'live.bilibili.com/123'
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    m = re.search(r"(\d{2,})", text)
    return int(m.group(1)) if m else None


async def resolve_room_id(session: aiohttp.ClientSession, value) -> dict:
    """把用户填的任意形式解析成真实房间号（短号也能用）"""
    room_id = parse_room_input(value)
    if room_id is None:
        raise BiliLoginError(f"没能从「{value}」里识别出房间号")
    async with session.get(ROOM_INIT, params={"id": room_id}, headers=BASE_HEADERS,
                           timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await _read_json(resp, "解析房间号")
    if data.get("code") != 0:
        raise BiliLoginError(f"房间不存在或解析失败：{data.get('message') or data.get('msg') or data}")
    payload = data.get("data") or {}
    return {
        "room_id": payload.get("room_id"),
        "short_id": payload.get("short_id") or 0,
        "uid": payload.get("uid"),
        "input": str(value),
    }


async def fetch_room_info(session: aiohttp.ClientSession, room_id: int) -> dict:
    """公开接口获取房间基本信息（不需要登录）"""
    async with session.get(ROOM_INFO, params={"room_id": room_id}, headers=BASE_HEADERS,
                           timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await _read_json(resp, "获取房间信息")
    if data.get("code") != 0:
        raise BiliLoginError(f"获取房间信息失败：{data.get('message') or data}")
    d = data.get("data") or {}
    return {
        "room_id": d.get("room_id"),
        "title": d.get("title"),
        "uname": d.get("uname"),
        "uid": d.get("uid"),
        "live_status": d.get("live_status"),
        "online": d.get("online"),
    }


async def fetch_live_room(session: aiohttp.ClientSession) -> dict:
    """登录后获取「自己的直播间」（扫码登录后自动填入用的就是它）"""
    async with session.get(LIVE_INFO, params={"login": 1}, headers=BASE_HEADERS,
                           timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await _read_json(resp, "获取自己的直播间")
    if data.get("code") != 0:
        raise BiliLoginError(f"获取直播间失败：{data.get('message') or data}")
    d = data.get("data") or {}
    return {
        "room_id": d.get("room_id"),
        "uid": d.get("uid"),
        "uname": d.get("uname"),
        "title": d.get("title"),
        "live_status": d.get("live_status"),
    }


# ── 二维码图片 ──────────────────────────────────────────────────────────────
def make_qr_svg(text: str) -> str:
    """生成 SVG 二维码（复用 qrcode 依赖）"""
    import qrcode
    import qrcode.image.svg
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    buf = io.BytesIO()
    image.save(buf)
    return buf.getvalue().decode("utf-8")


# ── 登录态持久化 / 检查 ─────────────────────────────────────────────────────
NAV_API = "https://api.bilibili.com/x/web-interface/nav"

# 需要持久化的 cookie（B 站登录态相关；buvid 系是设备指纹，缺了会被当新设备）
PERSIST_COOKIE_KEYS = (
    "SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5",
    "buvid3", "buvid4", "b_nut", "sid", "CURRENT_FNVAL", "CURRENT_QUALITY",
)


def pick_persist_cookies(cookies: dict) -> dict:
    """从会话里挑出值得持久化的 cookie"""
    return {k: v for k, v in (cookies or {}).items() if k in PERSIST_COOKIE_KEYS and v}


def apply_cookies(session: aiohttp.ClientSession, cookies: dict) -> int:
    """把保存下来的 cookie 灌回会话（重启后恢复登录态，不用重新扫码）"""
    import http.cookies as _http_cookies

    if not cookies:
        return 0
    jar = _http_cookies.SimpleCookie()
    for name, value in cookies.items():
        if not value:
            continue
        try:
            jar[name] = value
            # 同时给 .bilibili.com 覆盖 passport / live / api 各子域
            jar[name]["domain"] = ".bilibili.com"
            jar[name]["path"] = "/"
        except Exception as e:
            logger.debug(f"恢复 cookie {name} 失败：{e}")
    try:
        session.cookie_jar.update_cookies(jar)
        return len(jar)
    except Exception as e:
        logger.warning(f"恢复 cookie 失败：{e}")
        return 0


async def check_login(session: aiohttp.ClientSession) -> dict:
    """检查当前登录态（未登录不抛异常，返回 is_login=False）"""
    try:
        async with session.get(NAV_API, headers=BASE_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await _read_json(resp, "检查登录状态")
    except Exception as e:
        return {"is_login": False, "error": str(e), "uname": "", "mid": None}

    d = data.get("data") or {}
    return {
        "is_login": bool(d.get("isLogin")),
        "uname": d.get("uname") or "",
        "mid": d.get("mid"),
        "code": data.get("code"),
        "message": data.get("message") or "",
    }
