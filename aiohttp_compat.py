# -*- coding: utf-8 -*-
"""aiohttp / brotli 版本兼容补丁

aiohttp 3.13.x 的 ``BrotliDecompressor.decompress_sync`` 会调用
``obj.process(data, max_length)``（双参数）；只有 ``Brotli >= 1.2.0`` 支持这种写法。
如果环境里装的是 ``Brotli 1.1.0``（例如 mitmproxy 依赖的版本），``process`` 只接受
一个参数，于是当 B 站 / CDN 返回 ``Content-Encoding: br`` 时会抛：

    TypeError: process() takes exactly 1 argument (2 given)

本模块把 ``decompress_sync`` 包一层：先按 aiohttp 期望的方式调用，遇到 TypeError
再退回单参数调用，从而同时兼容新旧两代 brotli 实现。导入时自动生效。
"""
import logging

logger = logging.getLogger(__name__)

_patched = False


def patch_aiohttp_brotli() -> bool:
    """给 aiohttp 的 Brotli 解压器打上多版本兼容补丁（幂等）"""
    global _patched
    if _patched:
        return True
    _patched = True

    try:
        from aiohttp import compression_utils
    except Exception:
        return False

    cls = getattr(compression_utils, "BrotliDecompressor", None)
    if cls is None or not getattr(compression_utils, "HAS_BROTLI", False):
        return False

    original = cls.decompress_sync

    def decompress_sync(self, data, *args, **kwargs):
        obj = getattr(self, "_obj", None)
        if obj is not None:
            method = getattr(obj, "decompress", None) or getattr(obj, "process", None)
            if method is not None:
                if args or kwargs:
                    # 新版 brotli：method(data, max_length)
                    try:
                        return method(data, *args, **kwargs)
                    except TypeError:
                        pass
                    # 旧版 brotli：method(data)
                    try:
                        return method(data)
                    except TypeError:
                        pass
                else:
                    try:
                        return method(data)
                    except TypeError:
                        pass
        # 兜底：交回 aiohttp 原始实现（若它抛错就让它抛）
        return original(self, data, *args, **kwargs)

    cls.decompress_sync = decompress_sync
    logger.debug("[兼容] 已启用 aiohttp brotli 多版本兼容补丁")
    return True


patch_aiohttp_brotli()
