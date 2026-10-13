# -*- coding: utf-8 -*-
"""生成 app.ico（程序图标）。

只在需要重做图标时跑一次：python make_icon.py
"""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
SIZE = 256
SS = 4          # 超采样倍数，画完再缩小，边缘才不锯齿


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def gradient(size, top=(0x3B, 0x82, 0xF6), bottom=(0x1D, 0x3F, 0x9E)):
    img = Image.new("RGB", (1, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        d.point((0, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img.resize((size, size), Image.BILINEAR)


def main():
    n = SIZE * SS
    img = gradient(n)
    img = img.convert("RGBA")
    img.putalpha(rounded_mask(n, int(n * 0.22)))

    d = ImageDraw.Draw(img)
    s = n / 256.0

    # 闪电：紧急停堆 / 高压电
    bolt = [(152, 20), (74, 146), (120, 146), (100, 236), (186, 106), (138, 106)]
    d.polygon([(x * s, y * s) for x, y in bolt], fill=(255, 255, 255, 255))

    # 一点点光晕，让图标不至于太扁
    glow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([int(n * 0.16), int(n * 0.16), int(n * 0.84), int(n * 0.84)],
                                 fill=(255, 255, 255, 26))
    img = Image.alpha_composite(img, glow)

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img.save(OUT, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    # 需要 PNG 预览图就把下面这行放开
    # img.save(os.path.join(os.path.dirname(OUT), "app.png"))
    print("已生成：", OUT)


if __name__ == "__main__":
    main()
