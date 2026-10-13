# -*- coding: utf-8 -*-
"""DG-Lab 郊狼控制器模块

支持两种运行模式：

- ``embedded``：使用本项目内置的郊狼服务（:mod:`coyote_hub`），官方 App 直接扫码连接到本程序，
  无需再单独运行 DG-Lab Coyote Game Hub。
- ``remote``：调用外部 DG-Lab Coyote Game Hub 的 HTTP API（保持旧行为）。
"""
import asyncio
import logging
import time

import aiohttp

from utils import parse_duration

logger = logging.getLogger(__name__)


class DGLabController:
    """DG-Lab 郊狼控制器"""

    def __init__(self, config: dict, session: aiohttp.ClientSession = None, hub=None):
        self.config = config
        self.session = session
        self.hub = hub
        # 独立记录“上一次的启用状态”，因为 WebUI 保存配置时会先整体替换 config，
        # 若直接读 self.cfg 会拿不到旧值，导致关闭时无法触发释放。
        self._enabled_snapshot = bool(self.cfg.get("enabled", True))
        self._last_log: dict = {}
        # 正在“计时中”的脉冲任务（紧急停堆要能一次性取消它们）
        self._pulse_tasks: set = set()

    # ── 配置 ────────────────────────────────────────────────────────────
    @property
    def cfg(self) -> dict:
        return self.config.setdefault("dglab", {})

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", True))

    @enabled.setter
    def enabled(self, value: bool) -> None:
        was_enabled = self._enabled_snapshot
        value = bool(value)
        self.cfg["enabled"] = value
        self._enabled_snapshot = value
        if was_enabled and not value:
            # 从“启用”切到“禁用”时，必须把设备强度释放掉，
            # 否则设备会停在当前强度上，且下次启用后强度会不断累加。
            self._schedule_release()

    @property
    def mode(self) -> str:
        return str(self.cfg.get("mode", "remote")).strip().lower()

    @property
    def controller_url(self) -> str:
        return str(self.cfg.get("controller_url", "")).rstrip("/")

    @property
    def controller_id(self) -> str:
        return str(self.cfg.get("controller_id", "all"))

    @property
    def client_id(self) -> str:
        return str(self.cfg.get("client_id") or "blivedglab")

    # ── 控制 ────────────────────────────────────────────────────────────
    async def strength(self, *, add: int = 0, sub: int = 0, force: bool = False) -> bool:
        """调整强度，返回是否真正下发成功

        force=True 时忽略 enabled 开关（用于把强度降回去，避免强度卡在高位）。
        """
        if not self.enabled and not force:
            logger.debug("[DGLab] 已禁用，跳过强度调整")
            return False

        if self.mode == "embedded":
            return await self._strength_embedded(add=add, sub=sub)
        return await self._strength_remote(add=add, sub=sub)

    async def _strength_embedded(self, *, add: int = 0, sub: int = 0) -> bool:
        if self.hub is None:
            logger.error("[DGLab] 内置郊狼服务未初始化，无法调整强度")
            return False
        delta = int(add) if add else -int(sub)
        if delta == 0:
            return True
        result = await self.hub.change_strength(delta)
        if not result.get("ok"):
            self._log_throttled("offline", logging.INFO,
                                "[DGLab] 郊狼设备未连接，强度调整已跳过（30 秒内只提示一次）")
            return False
        return True

    async def _strength_remote(self, *, add: int = 0, sub: int = 0, set_value=None) -> bool:
        url = f"{self.controller_url}/api/v2/game/{self.controller_id}/strength"
        if set_value is not None:
            payload = {"strength": {"set": int(set_value)}}
        else:
            payload = {"strength": {"add": add} if add else {"sub": sub}}
        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                if data.get("status") != 1:
                    logger.warning(f"[DGLab] 接口异常: {data}")
                    return False
                return True
        except Exception as e:
            logger.error(f"[DGLab] 请求失败: {e}")
            return False

    async def release(self) -> bool:
        """把郊狼强度归零（关闭控制器 / 程序退出时调用）"""
        if self.mode == "embedded":
            if self.hub is None:
                return False
            if not await self.hub.release():
                logger.info("[DGLab] 郊狼设备未连接，无需释放")
                return False
            logger.info("[DGLab] 已将郊狼强度归零")
            return True
        ok = await self._strength_remote(set_value=0)
        if ok:
            logger.info("[DGLab] 已请求外部 Game Hub 将强度归零")
        return ok

    async def pulse(self, add: int, duration):
        """脉冲：增加强度，持续一段时间后减少"""
        if not self.enabled:
            logger.debug("[DGLab] 已禁用，跳过脉冲")
            return

        # 先解析时长：如果时长非法，必须在“加强度”之前就放弃，
        # 否则会只加不减，把强度留在高位。
        try:
            seconds = parse_duration(duration)
        except Exception as e:
            logger.error(f"[DGLab] 时长解析失败，已跳过本次脉冲: {e}")
            return

        if not await self.strength(add=add):
            return

        current = asyncio.current_task()
        if current is not None:
            self._pulse_tasks.add(current)
        try:
            await asyncio.sleep(seconds)
        finally:
            if current is not None:
                self._pulse_tasks.discard(current)
            # 无论正常结束、被取消（紧急停堆 / 退出），还是期间被禁用，
            # 都必须把强度降回去 —— 保证「任何退出路径强度都会回落」这个不变量。
            # 紧急停堆会另外显式归零一次，两者幂等，不会冲突。
            try:
                await self.strength(sub=add, force=True)
            except Exception as e:
                logger.error(f"[DGLab] 强度回落失败: {e}")

    async def emergency_stop(self) -> dict:
        """紧急停堆：立即切断控制并把强度归零

        顺序很重要：
          1. 先关控制权 —— 之后任何弹幕/礼物都不会再产生新指令
          2. 取消所有正在计时的脉冲 —— 否则它们若干秒后还会补发一次回落指令
          3. 立刻把 A/B 强度归零（内置模式同时清空波形缓冲）
        """
        self.cfg["enabled"] = False
        self._enabled_snapshot = False

        cancelled = 0
        for task in list(self._pulse_tasks):
            if not task.done():
                task.cancel()
                cancelled += 1
        self._pulse_tasks.clear()

        ok = await self.release()
        logger.warning(
            f"[DGLab] 紧急停堆：郊狼控制已关闭、强度已归零"
            + (f"（取消了 {cancelled} 个进行中的脉冲）" if cancelled else "")
        )
        return {"ok": ok, "cancelled": cancelled, "released": ok}

    async def resume(self) -> bool:
        """恢复郊狼控制（紧急停堆的逆操作）"""
        self.cfg["enabled"] = True
        self._enabled_snapshot = True
        logger.info("[DGLab] 已恢复郊狼控制")
        return True

    # ── 内部 ────────────────────────────────────────────────────────────
    def _log_throttled(self, key: str, level: int, message: str, interval: float = 30.0) -> None:
        """同一个 key 的日志在 interval 秒内只输出一次"""
        now = time.monotonic()
        if now - self._last_log.get(key, 0.0) < interval:
            return
        self._last_log[key] = now
        logger.log(level, message)

    def _schedule_release(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._safe_release())

    async def _safe_release(self) -> None:
        try:
            await self.release()
        except Exception as e:
            logger.error(f"[DGLab] 释放强度失败: {e}")
