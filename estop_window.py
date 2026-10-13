# -*- coding: utf-8 -*-
"""紧急停堆 · 桌面悬浮按钮（独立小程序，不依赖浏览器）

一个常驻桌面最上层的悬浮圆球，左键单击立刻把郊狼强度降到 0 并关闭控制。
它只做一件事：调用主程序本机 HTTP 接口，因此不需要开浏览器、也不需要看任何页面。

用法：
    python estop_window.py                  # 自动读取 config.yaml 里的 webui 地址
    python estop_window.py --port 8081      # 主程序换了端口
    python estop_window.py --url http://192.168.1.5:17800

交互（安全性优先）：
    左键单击  = 立即停堆（停止是安全方向，不做二次确认）
    按住拖动  = 移动位置（位置会记住）
    右键单击  = 菜单：恢复控制 / 打开控制面板 / 退出
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

try:
    from utils import config_path as _config_path, resource_path as _resource_path
    CONFIG_PATH = _config_path()
    resource_path = _resource_path
except Exception:   # 极端情况下（被单独拷走）退回本目录
    CONFIG_PATH = os.environ.get("BLIVE_CONFIG") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"
    )

    def resource_path(*parts):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, *parts)
POS_PATH = os.path.join(os.path.expanduser("~"), ".blive_dglab_estop.json")

POLL_INTERVAL = 3.0      # 状态轮询间隔（秒）
HTTP_TIMEOUT = 3.0


# ── HTTP / 配置（与 GUI 解耦，方便单测）─────────────────────────────────
def resolve_base_url(cli_url: str = None, cli_host: str = None, cli_port: int = None,
                     config_path: str = CONFIG_PATH) -> str:
    """决定要连哪个主程序：命令行 > config.yaml > 127.0.0.1:17800"""
    if cli_url:
        return cli_url.rstrip("/")

    host, port = "127.0.0.1", 17800
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        webui = cfg.get("webui", {}) or {}
        host = str(webui.get("host") or host)
        port = int(webui.get("port") or port)
    except Exception:
        pass

    if cli_host:
        host = cli_host
    if cli_port:
        port = int(cli_port)
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"     # 监听所有网卡时，本机访问走回环即可
    return f"http://{host}:{port}"


def api_request(base_url: str, path: str, method: str = "GET", timeout: float = HTTP_TIMEOUT) -> dict:
    """调用主程序接口，返回解析后的 JSON"""
    url = base_url.rstrip("/") + path
    data = b"{}" if method == "POST" else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_pos() -> dict:
    try:
        with open(POS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_pos(x: int, y: int) -> None:
    try:
        with open(POS_PATH, "w", encoding="utf-8") as f:
            json.dump({"x": int(x), "y": int(y)}, f)
    except Exception:
        pass


# ── 配色 ────────────────────────────────────────────────────────────────────
# 状态主色（外圈 / 光晕 / 文字强调）、深色（球体边缘）、浅色（高光）
ACCENT = {"ok": "#ff4d6d", "hover": "#ff7089", "stopped": "#94a3b8", "offline": "#f59e0b"}
DEEP = {"ok": "#6d0b20", "hover": "#8c1129", "stopped": "#1e293b", "offline": "#7c2d12"}
PALE = {"ok": "#ffc2ce", "hover": "#ffd8df", "stopped": "#e2e8f0", "offline": "#fde68a"}
# 右下角小圆点：设备连着 = 绿，没连 = 灰
DOT = {"ok": "#22c55e", "offline": "#f59e0b", "stopped": "#64748b"}
# 旧名字保留（兜底画法仍会用）
PALETTES = {"ok": (PALE["ok"], DEEP["ok"]), "hover": (PALE["hover"], DEEP["hover"]),
            "stopped": (PALE["stopped"], DEEP["stopped"]), "offline": (PALE["offline"], DEEP["offline"])}
GLOW_COLORS = ACCENT
C_BG = "#0b0f18"
TEXT = "#ffffff"
TEXT_DIM = "#c7cbd8"
# Windows 的透明色：用纯黑，渲染时光晕也是往纯黑淡出 → 边缘自然，不会有彩边
TRANSPARENT = "#000000"

# ── 外观尺寸（逻辑像素，会按屏幕 DPI 整体放大）──
WIN_W, WIN_H = 112, 138
BALL_CX, BALL_CY, BALL_R = 56, 54, 38
PILL_CY, PILL_W, PILL_H = 116, 96, 34
GLOW_FRAMES = 8          # 呼吸光晕 / 加载弧的帧数
CSS = 3                  # 超采样倍数（渲染完缩小 = 抗锯齿）


class EstopWindow:
    """桌面悬浮按钮本体（tkinter）"""

    SIZE = 104          # 圆形直径
    PAD = 6
    STATUS_H = 22       # 下方状态条高度

    def __init__(self, base_url: str, open_page: bool = True, exit_when_lost: float = 0):
        import tkinter as tk
        self.tk = tk
        self.base_url = base_url
        self.open_page = open_page
        # 主程序失联超过这个秒数就自动退出（0 = 一直留着）
        self.exit_when_lost = float(exit_when_lost or 0)
        self._last_ok = time.monotonic()

        self.state = "unknown"        # ok / stopped / offline
        self.status_text = "连接中…"
        self.strength_text = ""
        self.device_online = False     # 郊狼设备连上了没（右下角小圆点）
        self.busy = False

        self.root = tk.Tk()
        self.root.title("紧急停堆")
        self._set_window_icon()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.96)
        except tk.TclError:
            pass

        # 跟着屏幕缩放走：150% 缩放的屏幕上按钮也大一圈，不会缩成一小坨
        try:
            self.ui_scale = max(1.0, min(3.0, self.root.winfo_fpixels("1i") / 96.0))
        except Exception:
            self.ui_scale = 1.0
        sc = self.ui_scale

        self.canvas_bg = TRANSPARENT
        self._img_bg = (0, 0, 0)       # 图片合成到「透明色」上（纯黑 = 被抠掉）
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            # 系统不支持透明色时退化成深色小卡片（这时别再用纯黑当底）
            self.canvas_bg = C_BG
            self._img_bg = tuple(int(C_BG[i:i + 2], 16) for i in (1, 3, 5))

        w = int(WIN_W * sc)
        h = int(WIN_H * sc)
        self.root.geometry(f"{w}x{h}")

        self.canvas = tk.Canvas(self.root, width=w, height=h,
                                highlightthickness=0, bd=0, bg=self.canvas_bg)
        self.canvas.pack()

        # 兼容旧字段（没装 Pillow 时用纯 tkinter 兜底画法）
        self.cx = BALL_CX * sc
        self.cy = BALL_CY * sc
        self.radius = BALL_R * sc

        self.hover = False
        self.scale = 1.0          # 悬停缩放动画（兜底画法用）
        self._target_scale = 1.0
        self._phase = 0.0         # 呼吸光环相位（兜底画法用）
        self._frame = 0           # 当前动画帧（Pillow 画法用）
        self._img_cache = {}
        self.ball = None          # 最外圈 / 图片项（供状态读取）

        try:
            from PIL import Image, ImageDraw, ImageFilter, ImageTk
            self._pil = (Image, ImageDraw, ImageFilter, ImageTk)
        except Exception:
            self._pil = None      # 没装 Pillow：自动退回 tkinter 画法

        self.icon = None
        self.label = None
        self.status = None
        self.glow = self.canvas.create_oval(0, 0, 0, 0, outline=ACCENT["ok"],
                                            width=2, state="hidden")

        self._ball_img = None
        if self._pil is not None:
            # 整块画面（球 + 光晕 + 胶囊）用图片画，才有抗锯齿
            self._ball_img = self.canvas.create_image(0, 0, anchor="nw", image=None)
            self.ball = self._ball_img
        self._draw_ball()

        self.icon = self.canvas.create_text(
            self.cx, self.cy - 1 * sc, text="停", fill="#ffffff",
            font=("Microsoft YaHei UI", max(12, int(23 * sc)), "bold"),
        )
        self.label = self.canvas.create_text(
            self.cx, (PILL_CY - 7) * sc, text="紧急停堆", fill="#f1f5f9",
            font=("Microsoft YaHei UI", max(7, int(10 * sc)), "bold"),
        )
        self.status = self.canvas.create_text(
            self.cx, (PILL_CY + 8) * sc, text=self.status_text, fill="#94a3b8",
            font=("Microsoft YaHei UI", max(6, int(8 * sc))),
        )

        # 拖动 / 点击判定
        self._drag_start = None
        self._moved = False

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Enter>", lambda e: self._set_hover(True))
        self.canvas.bind("<Leave>", lambda e: self._set_hover(False))

        self._build_menu()
        self._restore_pos()
        self._render()

        # 后台轮询状态，避免界面卡顿
        self._alive = True
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.root.after(50, self._animate)   # 呼吸光环 / 悬停缓动

    # ── 界面 ────────────────────────────────────────────────────────────
    def _build_menu(self):
        m = self.tk.Menu(self.root, tearoff=0)
        m.add_command(label="🔄 刷新状态", command=lambda: self._run_async(self._refresh_once))
        m.add_separator()
        m.add_command(label="🔓 恢复郊狼控制", command=self._confirm_resume)
        if self.open_page:
            m.add_command(label="🌐 打开控制面板", command=self._open_page)
        m.add_separator()
        m.add_command(label="✖ 退出", command=self._quit)
        self.menu = m

    # ── 绘制（纯外观）─────────────────────────────────────────────────
    @staticmethod
    def _mix(c1: str, c2: str, t: float) -> str:
        """两个 #rrggbb 之间线性插值，用来伪造径向渐变"""
        t = max(0.0, min(1.0, t))
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def _palette(self):
        if self.state == "stopped":
            return PALETTES["stopped"]
        if self.state == "offline":
            return PALETTES["offline"]
        return PALETTES["hover"] if self.hover else PALETTES["ok"]

    def _state_key(self) -> str:
        if self.state == "stopped":
            return "stopped"
        if self.state == "offline":
            return "offline"
        return "hover" if self.hover else "ok"

    def _draw_ball(self) -> None:
        """更新画面：优先用 Pillow 渲染（抗锯齿），没装就退回纯 tkinter 画法"""
        if self._pil is not None:
            self._draw_ball_pil()
        else:
            self._draw_ball_canvas()

    # ── Pillow 渲染（外观）────────────────────────────────────────────
    def _draw_ball_pil(self) -> None:
        key = (self._state_key(), bool(self.hover), bool(self.busy),
               self._frame % GLOW_FRAMES)
        photo = self._img_cache.get(key)
        if photo is None:
            try:
                photo = self._paint(*key)
            except Exception:
                # 渲染出问题就彻底退回旧画法，保证按钮永远能用
                self._pil = None
                self._draw_ball_canvas()
                return
            if len(self._img_cache) > 64:
                self._img_cache.clear()
            self._img_cache[key] = photo
        try:
            self.canvas.itemconfig(self._ball_img, image=photo)
        except Exception:
            pass
        for item in (self.icon, self.label, self.status):
            if item is not None:
                self.canvas.tag_raise(item)

    @staticmethod
    def _rgb(color: str):
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))

    def _paint(self, state_key: str, hover: bool, busy: bool, frame: int):
        """把整个画面画出来（超采样后缩小 = 抗锯齿）

        透明区域最后会落在纯黑上（TRANSPARENT），所以光晕往外淡出到纯黑即可，
        既不会有彩色描边，又能顺带当个柔和投影。
        """
        Image, ImageDraw, ImageFilter, ImageTk = self._pil
        sc = self.ui_scale
        W, H = int(WIN_W * sc), int(WIN_H * sc)
        k = sc * CSS                                   # 逻辑坐标 → 大图坐标
        big = Image.new("RGBA", (W * CSS, H * CSS), (0, 0, 0, 0))

        accent = self._rgb(ACCENT[state_key])
        deep = self._rgb(DEEP[state_key])
        pale = self._rgb(PALE[state_key])
        core = self._rgb("#111a2b")

        cx, cy, r = BALL_CX * k, BALL_CY * k, BALL_R * k

        def blend():
            return ImageDraw.Draw(big)

        d = blend()
        # 1) 呼吸光晕 / 加载弧
        if busy:
            start = frame / GLOW_FRAMES * 360.0
            d.arc([cx - r * 1.13, cy - r * 1.13, cx + r * 1.13, cy + r * 1.13],
                  start=start, end=start + 240, fill=accent + (255,),
                  width=max(2, int(3.2 * k)))
        elif state_key in ("ok", "hover"):
            t = frame / GLOW_FRAMES
            gr = r * (1.05 + 0.28 * t)
            ga = int(120 * (1.0 - t) ** 1.5) + 18
            glow = Image.new("RGBA", big.size, (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse(
                [cx - gr, cy - gr, cx + gr, cy + gr],
                outline=accent + (ga,), width=max(2, int(3.0 * k)))
            big = Image.alpha_composite(big, glow.filter(
                ImageFilter.GaussianBlur(max(1.0, 4.5 * k))))
            d = blend()

        # 2) 球体：同心圆堆径向渐变（中心偏冷，边缘吃状态色）
        steps = max(20, int(r * 0.55))
        for i in range(steps, 0, -1):
            t = i / steps
            rr = r * t
            col = tuple(int(core[j] + (deep[j] - core[j]) * (t ** 1.35)) for j in range(3))
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (255,))

        # 3) 外圈亮环 + 内侧柔光
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent + (255,),
                  width=max(2, int(2.1 * k)))
        d.ellipse([cx - r * 0.93, cy - r * 0.93, cx + r * 0.93, cy + r * 0.93],
                  outline=pale + (58,), width=max(1, int(1.1 * k)))

        # 4) 左上高光 + 底部反光（玻璃感）
        for box, alpha, blur in (
                ([cx - r * 0.62, cy - r * 0.80, cx - r * 0.02, cy - r * 0.20], 70, 4.2),
                ([cx - r * 0.46, cy + r * 0.36, cx + r * 0.46, cy + r * 0.84], 34, 3.4)):
            layer = Image.new("RGBA", big.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).ellipse(box, fill=(255, 255, 255, alpha))
            big = Image.alpha_composite(big, layer.filter(
                ImageFilter.GaussianBlur(max(1.0, blur * k))))
        d = blend()

        # 5) 右下角状态小点（设备连没连）
        dot = DOT[state_key if state_key != "hover" else "ok"]
        dr = r * 0.17
        dcx, dcy = cx + r * 0.68, cy + r * 0.68
        d.ellipse([dcx - dr - 1.6 * k, dcy - dr - 1.6 * k,
                   dcx + dr + 1.6 * k, dcy + dr + 1.6 * k],
                  fill=(8, 11, 18, 240))
        only = (state_key == "ok" and not self.device_online) or state_key == "stopped"
        if only:
            d.ellipse([dcx - dr, dcy - dr, dcx + dr, dcy + dr],
                      fill=self._rgb(DOT["stopped"]) + (255,))
        elif state_key == "hover" and not self.device_online:
            d.ellipse([dcx - dr, dcy - dr, dcx + dr, dcy + dr],
                      fill=self._rgb(DOT["stopped"]) + (255,))
        else:
            d.ellipse([dcx - dr, dcy - dr, dcx + dr, dcy + dr],
                      fill=self._rgb(dot) + (255,))

        # 6) 下方胶囊：状态文字底
        px, py = PILL_W * k / 2, PILL_H * k / 2
        pcy = PILL_CY * k
        d.rounded_rectangle([cx - px, pcy - py, cx + px, pcy + py],
                            radius=py, fill=(9, 13, 22, 232),
                            outline=accent + (66,), width=max(1, int(1.1 * k)))

        # 7) 缩小回目标尺寸（这一步才是抗锯齿的关键），再合到纯黑上
        small = big.resize((W, H), Image.LANCZOS)
        flat = Image.new("RGB", (W, H), self._img_bg)
        flat.paste(small, (0, 0), small)
        return ImageTk.PhotoImage(flat)

    def _draw_ball_canvas(self) -> None:
        """兜底画法：用同心圆堆出立体感（没有 Pillow 时用）"""
        if self._ball_img is not None:
            try:
                self.canvas.delete(self._ball_img)
            except Exception:
                pass
            self._ball_img = None
        self.canvas.delete("ball")
        cx, cy = self.cx, self.cy
        r = self.radius * self.scale
        light, dark = self._palette()

        outer = None
        steps = 18
        for i in range(steps, 0, -1):
            t = i / steps
            rr = max(1.0, r * t)
            item = self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                           fill=self._mix(light, dark, t), outline="",
                                           tags="ball")
            if outer is None:
                outer = item
        self.ball = outer

        # 左上高光 + 底部反光，让它看起来是个球
        self.canvas.create_oval(cx - r * 0.54, cy - r * 0.64, cx - r * 0.10, cy - r * 0.20,
                                fill="#ffffff", outline="", stipple="gray50", tags="ball")
        self.canvas.create_oval(cx - r * 0.40, cy + r * 0.34, cx + r * 0.40, cy + r * 0.80,
                                fill="#ffffff", outline="", stipple="gray12", tags="ball")

        for item in (getattr(self, "icon", None), getattr(self, "label", None),
                     getattr(self, "status", None)):
            if item is not None:
                self.canvas.tag_raise(item)

    def _set_hover(self, on: bool) -> None:
        self.hover = on
        self._target_scale = 1.08 if on else 1.0
        self._draw_ball()

    def _animate(self) -> None:
        """呼吸光晕 / 加载弧（只影响画面，不影响任何交互逻辑）"""
        if not getattr(self, "_alive", False):
            return
        try:
            if self._pil is not None:
                # Pillow 画法：直接在预渲染好的帧里轮换，省 CPU
                if self.busy or self.state in ("ok", "unknown"):
                    self._frame = (self._frame + 1) % GLOW_FRAMES
                    self._draw_ball()
                return
            # ── 下面是没有 Pillow 时的兜底动画 ──
            if abs(self.scale - self._target_scale) > 0.002:
                self.scale += (self._target_scale - self.scale) * 0.25
                self._draw_ball()

            if self.state in ("ok", "unknown"):
                self._phase = (self._phase + 0.035) % 1.0
                t = self._phase
                rr = self.radius * (1.0 + 0.30 * t)
                stipple = ("gray75" if t < 0.30 else
                           "gray50" if t < 0.55 else
                           "gray25" if t < 0.80 else "gray12")
                self.canvas.coords(self.glow, self.cx - rr, self.cy - rr,
                                   self.cx + rr, self.cy + rr)
                self.canvas.itemconfig(self.glow,
                                       outline=ACCENT["hover" if self.hover else "ok"],
                                       width=max(1, int(3 - 2 * t)),
                                       stipple=stipple, state="normal")
            else:
                self.canvas.itemconfig(self.glow, state="hidden")
        except Exception:
            pass
        finally:
            if self._pil is not None:
                self.root.after(90, self._animate)   # 图已经渲染好，帧率低点也够顺
            else:
                self.root.after(50, self._animate)

    def _render(self):
        stopped = self.state == "stopped"
        offline = self.state == "offline"
        if self.busy:
            self.canvas.itemconfig(self.icon, text="停", fill="#ffffff")
            self.canvas.itemconfig(self.label, text="正在停堆…", fill="#ffd7de")
        else:
            self.canvas.itemconfig(self.icon, text="‖" if stopped else "停",
                                   fill="#e2e8f0" if stopped else "#ffffff")
            self.canvas.itemconfig(self.label, text="已停堆" if stopped else "紧急停堆",
                                   fill="#e2e8f0" if stopped else "#f1f5f9")
        if offline:
            text, color = "无法连接主程序", "#ffb454"
        else:
            text = self.strength_text or self.status_text
            color = ACCENT["stopped"] if stopped else "#94a3b8"
        self.canvas.itemconfig(self.status, text=text, fill=color)
        self._draw_ball()

    def _center_in_screen(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = self.root.winfo_screenwidth() - w - 40
        y = self.root.winfo_screenheight() - h - 90
        self.root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _restore_pos(self):
        pos = load_pos()
        self.root.update_idletasks()
        w = self.root.winfo_width() or 120
        h = self.root.winfo_height() or 140
        if isinstance(pos.get("x"), int) and isinstance(pos.get("y"), int):
            x = min(max(0, pos["x"]), self.root.winfo_screenwidth() - w)
            y = min(max(0, pos["y"]), self.root.winfo_screenheight() - h)
            self.root.geometry(f"+{x}+{y}")
        else:
            self._center_in_screen()

    # ── 拖动 / 点击 ─────────────────────────────────────────────────────
    def _on_press(self, event):
        self._drag_start = (event.x_root, event.y_root,
                            self.root.winfo_x(), self.root.winfo_y())
        self._moved = False

    def _on_motion(self, event):
        if not self._drag_start:
            return
        sx, sy, wx, wy = self._drag_start
        dx, dy = event.x_root - sx, event.y_root - sy
        if not self._moved and abs(dx) < 5 and abs(dy) < 5:
            return
        self._moved = True
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = min(max(0, wx + dx), self.root.winfo_screenwidth() - w)
        y = min(max(0, wy + dy), self.root.winfo_screenheight() - h)
        self.root.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        if self._moved:
            save_pos(self.root.winfo_x(), self.root.winfo_y())
            self._drag_start = None
            return
        self._drag_start = None
        # 没拖动 = 单击 → 立即停堆（安全方向不二次确认）
        self._run_async(self._emergency_stop)

    def _on_right_click(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ── 动作 ────────────────────────────────────────────────────────────
    def _run_async(self, func):
        if self.busy:
            return
        threading.Thread(target=func, daemon=True).start()

    def _refresh_once(self):
        try:
            data = api_request(self.base_url, "/api/hub/status")
            self.state = "stopped" if data.get("enabled") is False else "ok"
            self.device_online = bool(data.get("connected"))
            if data.get("connected"):
                self.strength_text = (f'A{data.get("strength_a", 0)}/{data.get("limit_a", 0)}  '
                                      f'B{data.get("strength_b", 0)}/{data.get("limit_b", 0)}')
            else:
                self.strength_text = "设备未连接"
            self._last_ok = time.monotonic()
        except Exception:
            self.state = "offline"
            self.strength_text = ""
            # 主程序没了这个遥控器也没用了：超过阈值就自己退出，避免残留一堆悬浮球
            if self.exit_when_lost and time.monotonic() - self._last_ok > self.exit_when_lost:
                print(f"主程序已失联超过 {self.exit_when_lost:.0f} 秒，悬浮球退出")
                self._quit()
                return
        self._safe_render()

    def _poll_loop(self):
        while self._alive:
            self._refresh_once()
            time.sleep(POLL_INTERVAL)

    def _safe_render(self):
        try:
            self.root.after(0, self._render)
        except Exception:
            pass

    def _emergency_stop(self):
        self.busy = True
        self._safe_render()          # 立刻切成「正在停堆…」+ 转圈
        try:
            data = api_request(self.base_url, "/api/hub/emergency-stop", method="POST")
            if data.get("success"):
                self.state = "stopped"
                self.strength_text = ""
                self._safe_render()
            else:
                self._toast(f"停堆失败：{data.get('error', '未知错误')}", error=True)
        except Exception as e:
            self.state = "offline"
            self._safe_render()
            self._toast(f"无法连接主程序\n{self.base_url}\n\n{e}", error=True)
        finally:
            self.busy = False
            self._safe_render()

    def _confirm_resume(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
                "恢复郊狼控制",
                "确定要恢复郊狼控制吗？\n\n恢复后，弹幕 / 礼物 / SC / 上舰会重新控制设备。",
                parent=self.root):
            return
        self._run_async(self._resume)

    def _resume(self):
        self.busy = True
        self._safe_render()
        try:
            data = api_request(self.base_url, "/api/hub/resume", method="POST")
            if data.get("success"):
                self.state = "ok"
                self._safe_render()
            else:
                self._toast(f"恢复失败：{data.get('error', '未知错误')}", error=True)
        except Exception as e:
            self._toast(f"无法连接主程序：{e}", error=True)
        finally:
            self.busy = False
            self._safe_render()

    def _open_page(self):
        import webbrowser
        webbrowser.open(self.base_url)

    def _toast(self, text: str, error: bool = False):
        def show():
            from tkinter import messagebox
            (messagebox.showerror if error else messagebox.showinfo)("紧急停堆", text, parent=self.root)
        try:
            self.root.after(0, show)
        except Exception:
            pass

    def _quit(self):
        self._alive = False
        try:
            save_pos(self.root.winfo_x(), self.root.winfo_y())
        except Exception:
            pass
        self.root.destroy()

    def _set_window_icon(self):
        """任务栏/托盘里显示程序图标（没有图标文件就静默跳过）"""
        if sys.platform != "win32":
            return
        try:
            ico = resource_path("app.ico")
            if os.path.exists(ico):
                self.root.iconbitmap(default=ico)
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="estop_window.py",
        description="紧急停堆桌面悬浮按钮（左键单击 = 立即停堆）",
    )
    p.add_argument("--url", help="主程序地址，如 http://127.0.0.1:17800")
    p.add_argument("--host", help="主程序主机（默认读 config.yaml，0.0.0.0 会被换成 127.0.0.1）")
    p.add_argument("--port", type=int, help="主程序端口（默认读 config.yaml）")
    p.add_argument("--no-open-page", action="store_true", help="右键菜单里不提供「打开控制面板」")
    p.add_argument("--exit-when-lost", type=float, default=0, metavar="SECONDS",
                   help="主程序失联超过该秒数后自动退出（默认 0 = 一直留着）")
    p.add_argument("--self-test", action="store_true",
                   help=argparse.SUPPRESS)   # 内部自检：建好窗口但不显示，用于自动化验证
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    base_url = resolve_base_url(args.url, args.host, args.port)

    if args.self_test:
        # 自检：真正创建 Tk 窗口 / 画布 / 字体，但不显示出来
        win = EstopWindow(base_url, open_page=False, exit_when_lost=0)
        win.root.withdraw()
        win.root.update_idletasks()
        win.root.update()
        if win._pil is not None:
            # Pillow 画法：验证真的渲染出了图片
            drawn = (win._ball_img is not None
                     and str(win.canvas.itemcget(win._ball_img, "image")) != "")
            mode = "Pillow 抗锯齿"
        else:
            drawn = win.canvas.itemcget(win.ball, "fill") != ""
            mode = "tkinter 兜底"
        size_ok = win.canvas.winfo_width() > 0 and win.canvas.winfo_height() > 0
        win._alive = False
        win.root.destroy()
        if size_ok and drawn:
            print(f"自检通过：窗口/画布/字体创建正常（{mode}）")
            return 0
        print(f"自检失败：画布尺寸 {size_ok} / 画面 {drawn}")
        return 1

    try:
        EstopWindow(base_url, open_page=not args.no_open_page,
                    exit_when_lost=args.exit_when_lost).run()
    except Exception as e:
        print(f"启动悬浮窗失败：{e}")
        print("（需要图形界面环境；无界面服务器上请直接用 HTTP 接口 /api/hub/emergency-stop）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
