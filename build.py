# -*- coding: utf-8 -*-
"""一键打包：python build.py

产物：dist/BiliLiveCoyote.exe（单文件，双击即用，不需要装 Python）
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "BiliLiveCoyote"

# 打进 exe 的只读资源：源文件 -> exe 内的相对目录
DATAS = [
    ("html", "html"),            # 网页（控制台 / OBS / 登录页）
    ("pulses.json", "."),        # 内置波形库
    ("config.yaml", "."),        # 默认配置模板（首次运行复制到 exe 旁边）
    ("app.ico", "."),            # 悬浮窗图标
    ("README.md", "."),
]

HIDDEN = ["ruamel.yaml", "qrcode", "aiohttp"]

# 用不到的大块头，排除掉能小好几 MB
# 注意：PIL 不能排除 —— 悬浮球的抗锯齿画面靠它渲染
EXCLUDE = ["numpy", "matplotlib", "pandas", "pytest", "setuptools"]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("没有安装 PyInstaller，请先执行：pip install pyinstaller")
        return 1

    sep = ";" if os.name == "nt" else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", NAME,
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", os.path.join(ROOT, "build"),
        "--collect-submodules", "blivedm",
    ]
    icon = os.path.join(ROOT, "app.ico")
    if os.path.exists(icon):
        args += ["--icon", icon]
    for h in HIDDEN:
        args += ["--hidden-import", h]
    for e in EXCLUDE:
        args += ["--exclude-module", e]
    for src, dest in DATAS:
        path = os.path.join(ROOT, src)
        if not os.path.exists(path):
            print(f"跳过缺失的资源：{src}")
            continue
        args += ["--add-data", f"{path}{sep}{dest}"]
    args.append(os.path.join(ROOT, "main.py"))

    print("开始打包，第一次会比较慢（一两分钟）……")
    print(" ".join(args))
    ret = subprocess.call(args, cwd=ROOT)
    if ret != 0:
        print("打包失败。")
        return ret

    # 随 exe 一起放好许可与说明（GPL-3.0 要求再分发时带上）
    for doc in ("LICENSE", "NOTICE", "LICENSE-MIT", "LICENSE-GameHub",
                "THIRD_PARTY_LICENSES.md", "README.md", "SAFETY.md"):
        src = os.path.join(ROOT, doc)
        if os.path.exists(src):
            try:
                shutil.copyfile(src, os.path.join(ROOT, "dist", doc))
            except Exception as e:
                print(f"复制 {doc} 失败：{e}")

    exe = os.path.join(ROOT, "dist", NAME + (".exe" if os.name == "nt" else ""))
    if os.path.exists(exe):
        size = os.path.getsize(exe) / 1024.0 / 1024.0
        print(f"\n打包完成：{exe}（{size:.1f} MB）")
        print("dist 里除了 exe 还放了 LICENSE / LICENSE-MIT / THIRD_PARTY_LICENSES.md，"
              "再分发时请一起带上（GPL-3.0 要求）。")
        print("把 exe 单独拷到任意目录双击就能用；")
        print("首次运行会在 exe 旁边自动生成 config.yaml。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
