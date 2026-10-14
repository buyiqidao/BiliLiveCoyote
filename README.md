# BiliLiveCoyote · BiliLive 弹幕控制郊狼（DG-Lab）

[![Release](https://img.shields.io/github/v/release/buyiqidao/BiliLiveCoyote?label=release&color=brightgreen)](https://github.com/buyiqidao/BiliLiveCoyote/releases/latest)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](#环境要求)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows&logoColor=white)](#环境要求)
[![Blive_DGLAB 上游](https://img.shields.io/badge/fork%20of-Blived__DGLAB-8a2be2.svg)](https://github.com/xyBakaQAQ/Blive_DGLAB)

> **BiliLiveCoyote** 是一个把 **B 站直播间弹幕/礼物/SC/上舰** 变成 **DG-Lab 郊狼（Coyote）**
> 电击强度的开源控制器：内置郊狼 SOCKET 服务（官方 App 扫码直连，无需 Game Hub）、
> 扫码自动填入直播间、OBS 覆盖层、桌面「紧急停堆」悬浮球，还能一键打包成免装 Python 的单文件 exe。
>
> <sub>**关键词**：BiliLiveCoyote · BiliLive · 郊狼 · DG-Lab · DGLAB · Coyote · 弹幕控制 ·
> B站直播弹幕 · 弹幕触发 · OBS 覆盖层 · 紧急停堆 · Blive_DGLAB（上游）</sub>

> ⚠️ **使用前必读：[SAFETY.md](./SAFETY.md)（使用安全声明与免责声明）**
>
> 这是一个**电刺激设备**的第三方控制程序，弹幕/礼物会让**别人间接影响你身上的电流**。
> 请务必先读安全声明：从最低强度开始、不跨心脏、设好上限与限流、
> **先测试紧急停堆**、随时可以物理断电。**未成年人禁止使用。**
>
> 本项目仅供学习与个人自用，按「现状」提供、**无任何担保**，
> 使用造成的任何后果由使用者自行承担；与 Bilibili、DG-Lab 官方均无关联。

---

## 目录

- [功能特性](#功能特性)
- [环境要求](#环境要求)
- [依赖项目](#依赖项目)
- [快速开始](#快速开始)
  - [测试模式开启方法](#测试模式开启方法)
- [打包成独立 exe](#打包成独立-exe)
- [配置说明](#配置说明)
- [紧急停堆](#紧急停堆)
- [测试模式](#测试模式)
- [内置郊狼服务](#内置郊狼服务)
- [OBS 集成](#obs-集成)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [使用安全与免责声明](#使用安全与免责声明)
- [来源与许可](#来源与许可)
- [许可证](#许可证)
- [致谢](#致谢)

---

## 使用安全与免责声明

> **⚠️ 这里只是摘要，完整内容见 [SAFETY.md](./SAFETY.md)，请务必读完再上手。**

**设备安全（电刺激）**

- **禁止**电极跨心脏 / 贴胸口、头脸眼口鼻、**颈部喉部**、破损或发炎皮肤
- **禁止**人群：装有心脏起搏器等植入设备、心脏病、癫痫、孕妇、未成年人
- **禁止**在饮酒/服药后、疲劳、洗澡或潮湿环境、开车或操作机械、无人看管时使用
- 强度**从最低开始**逐步加；单次别太久；调整电极前先停堆/断开
- 出现心悸、胸闷、头晕、灼痛、肌肉痉挛等任何不适 → **立刻停堆并物理断电**，必要时就医

**直播场景**

- 弹幕/礼物会让**不特定的人间接控制你身上的电流**，请设好设备端上限、限流与单次加值
- 建议**桌面悬浮球常亮**（左键单击立即停堆）；观众感受不到你的体感，别为了效果把上限开高

**软件风险**

- 断网、崩溃、断电等情况下设备可能停在当时的脉冲上，**唯一可靠的保险是物理断电**
- `config.yaml` 存有登录凭证，分享项目前请先清空
- 本程序默认以 `0.0.0.0` 监听（手机扫码需要），**不要在公共网络下开启**

**免责声明**

- 本项目仅供学习与个人自用，按「现状」（AS IS）提供，**不提供任何明示或默示担保**
  （见 [LICENSE](./LICENSE) 的 GPL-3.0 第 15、16 条）
- **使用风险自负**：因使用或无法使用本程序造成的任何人身伤害、健康损害、财产损失、
  设备损坏、直播事故、账号封禁或其他直接/间接损害，**作者与贡献者不承担任何责任**
- 请确保使用行为符合所在地区法律法规与平台规则；请勿用于任何非法或有害用途
- 与 Bilibili、DG-Lab 官方均无关；「Bilibili」「DG-Lab」等商标归各自所有者所有

---

## 功能特性

### 核心功能
- **弹幕触发**：观众发送弹幕时触发强度脉冲
  - 支持舰长/提督/总督额外加成（可选）
  - 支持限流：X分钟内同一用户最多触发X次
- **礼物系统**：根据金瓜子礼物档位触发不同强度和时长
- **醒目留言**：Super Chat 按价格档位触发
- **上舰联动**：用户开通舰长/提督/总督时触发
- **互动事件**：进房、关注、分享、特别关注等事件触发
- **扫码登录**：手机 B 站 App 扫一扫，自动填入 SESSDATA 和你的直播间号（也支持粘贴直播间链接）
- **内置郊狼服务**：官方「郊狼」App 扫码直连本程序，无需再单独运行 Game Hub
- **紧急停堆**：全站悬浮按钮，一键把强度降到 0 并关闭控制（详见下文）

### Web UI 功能
- **实时监控**：分别显示弹幕日志和郊狼控制日志
- **在线配置**：通过 Web 界面修改所有配置，保存后立即生效
- **郊狼控制**：设备状态、扫码连接二维码、手动增减 A/B 通道强度
- **OBS 集成**：提供 OBS 浏览器源页面，实时显示弹幕和郊狼强度信息
- **响应式设计**：侧边栏导航，支持快速定位配置项

---

## 环境要求

用打包好的 exe 时：**Windows 10/11，不需要装任何东西**。

从源码运行：Python 3.11 及以上版本。

郊狼控制有两种模式：

- **内置模式（`mode: embedded`，默认，推荐）**：本项目已内置郊狼 SOCKET 服务，
  官方「郊狼」App 扫码直连即可，**无需**额外安装或运行 Game Hub。
- **外置模式（`mode: remote`）**：连接一个已运行的
  [DG-Lab Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub) HTTP API。

---

## 依赖项目

本项目依赖以下开源项目：

- **[blivedm](https://github.com/xfgryujk/blivedm)** - Bilibili 直播弹幕库，提供直播间事件监听功能
- **[DG-Lab Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub)** - DG-Lab 设备的开源控制中心，提供 HTTP API 接口支持

---

## 快速开始

> **TL;DR**：`pip install -r requirements.txt` → 双击 `启动.bat`（或 `python main.py`）→
> 浏览器自动打开扫码页，用手机 B 站 App 扫一下就能用了。
> 手机扫码后不用再管：程序会连上你的直播间，弹幕/礼物/SC/上舰开始控制郊狼。
> 想先本地空跑：`python main.py --fake`（不连 B 站，见 [测试模式](#测试模式)）。

### 1. 安装依赖

```sh
pip install -r requirements.txt
```

### 2. 配置文件

编辑 `config.yaml` 文件，填写必要信息：

```yaml
# Bilibili 直播间配置
bilibili:
  room_id: 1796101901    # 你的直播间 ID
  sessdata: ""           # 从浏览器获取的 SESSDATA

# DG-Lab 控制器配置
dglab:
  enabled: true          # 是否启用郊狼控制器
  mode: embedded         # embedded=内置郊狼服务，remote=外部 Game Hub
  client_id: blivedglab  # 内置模式下 App 扫码使用的客户端 ID
  channel: A             # 事件（弹幕/礼物/SC/上舰）控制哪个通道：A / B / AB
  pulse_id: d6f83af0     # 内置模式下输出的波形 ID（见 pulses.json）
  # advertise_host: ""   # 可选，扫码地址使用的 IP，留空自动探测局域网 IP
  controller_url: "http://127.0.0.1:8920"   # 仅 remote 模式使用
  controller_id: "all"                      # 仅 remote 模式使用

# WebUI 配置
webui:
  host: "0.0.0.0"        # 监听地址
  port: 17800             # 监听端口
```

### 3. 运行程序

**Windows 一键启动**：双击 `启动.bat`（或 `start.bat`）—— 会自动检查依赖再启动。
批处理刻意写成**纯 ASCII**：中文写在 .bat 里会被 cmd 按代码页错误解析（报「'install' 不是内部或外部命令」这类错）。

命令行方式：

```sh
python main.py
```

> - 想要**桌面悬浮的紧急停堆按钮**：`python main.py --estop`（或单独跑 `python estop_window.py`）
> - 想**边连直播间边注入测试事件**：`python main.py --test`
> - 想**完全不连 Bilibili 本地联调**：`python main.py --fake`（或 `python fake_room.py`）
> - 不想让它**自动弹浏览器**：加 `--no-browser`（只把地址打印出来）
>
> 详见 [测试模式](#测试模式)。

### 4. 访问 Web UI

打开浏览器访问：`http://localhost:17800`

- **首页**：查看日志
- **配置**：修改配置项
- **OBS**：获取 OBS 链接
- **郊狼控制**：查看设备状态、扫码连接、手动调整强度
- **🧪 测试**：注入模拟事件（**只有开启测试模式才会出现**，见下）

### 测试模式开启方法

「测试」页和 `--fake` 模拟直播间都是**主程序的一个开关**（不是另一个进程，不会和正在运行的实例冲突）。
三种开启方式，任选一种：

| 方式 | 怎么开 | 效果 |
| --- | --- | --- |
| **命令行（推荐）** | `python main.py --test` | 连真实直播间 + 多出「🧪 测试」页与 `/api/test/*` 接口 |
| **配置文件（长期开启）** | `config.yaml` 里写 `test: { enabled: true }` | 同上，不用每次加参数（`--test`/`--fake` 会强制开启，优先级更高） |
| **完全不连 B 站** | `python main.py --fake`（等价 `python fake_room.py`） | 只用本地模拟直播间，不连 Bilibili |

开启后打开 **`http://localhost:17800/test.html`**（或点侧边栏「🧪 测试」）：

- 点按钮即可注入弹幕 / 礼物 / SC / 上舰 / 进房 / 关注…，还能连发 N 条压测
- 事件按 B 站**原始协议报文**构造，走完整链路：`原始协议 → blivedm → BilibiliHandler → DGLabController → 郊狼`
- 此时若官方郊狼 App 已扫码连上，**模拟事件会真的控制设备**；只想看日志就在配置页取消勾选「启用郊狼控制器」

> 详细说明（命令行玩法、`--scenario` 脚本化压测）见 [测试模式](#测试模式)。

---

## 打包成独立 exe

> 目标电脑**不需要安装 Python**：`dist/BiliLiveCoyote.exe` 单文件、拷走双击即用。
>
> 📦 **直接下载**：[**Releases → `BiliLiveCoyote_exe.zip`**](https://github.com/buyiqidao/BiliLiveCoyote/releases/latest)
> （exe + LICENSE / NOTICE / SAFETY / README，解压即用）；源码包 `BiliLiveCoyote_src.zip` 也在同一个 Release 里。

`dist/` 下已经生成好一个**单文件 exe**，拷到任意目录双击就能用，目标电脑无需安装 Python：

```
dist/BiliLiveCoyote.exe
```

- 首次运行会在 **exe 旁边自动生成 `config.yaml`**，以后改配置就改它
- 网页、内置波形、配置模板等资源全部打进 exe，**exe 可以单独拷走**
- 想重新打包 / 换图标：`python build.py`（或双击 `build_exe.bat`），需要先 `pip install pyinstaller`
- exe 与源码同源、同样以 **GPL-3.0** 分发：再分发 exe 时请一并带上 `LICENSE`、`LICENSE-MIT`、
  `LICENSE-GameHub` 和 `THIRD_PARTY_LICENSES.md`（打包出来的发布包里就带着这几份）
- 对应源码：<https://github.com/buyiqidao/BiliLiveCoyote>（收到 exe 的人凭这个地址就能拿到完整源码）

打包后「紧急停堆」悬浮球照旧可用：主程序会把**自己**再拉起来当悬浮球用
（内部参数 `--estop-window`），所以不再需要额外附带 `estop_window.py`。

---

## 配置说明

### 直播间配置（每次启动扫码刷新）

**程序启动会自动打开扫码页**，用手机 B 站 App 扫一次即可：

- 刷新登录凭证（SESSDATA / bili_jct / DedeUserID / buvid3 / buvid4 … 整套）
- 自动获取**你自己的直播间号**并填入
- 自动**热切换监听**（不用重启程序）
- 扫完自动跳转到配置页

登录模式可在配置页切换（`config.yaml` → `bilibili.login_mode`）：

| 模式 | 行为 |
| --- | --- |
| **`always`（默认）** | **每次启动都打开扫码页刷新凭证**，凭证永远不会过期失效 |
| `auto` | 只在凭证失效 / 缺失时提示扫码 |
| `off` | 从不提示扫码 |

> **不扫也不影响使用**：扫码页有「跳过，先进入控制台」按钮，程序照常运行。
> 登录凭证会保存到 `config.yaml`，所以偶尔漏扫一次也不会立刻不可用。
> 想手动扫码随时打开 `http://localhost:17800/login.html`。

也可以手动填「直播间 ID」框，支持三种写法，填完点「🔍 解析并切换」：

| 写法 | 例子 |
| --- | --- |
| 真实房间号 | `1796101901` |
| 短号 | `88765` |
| 直播间链接 | `https://live.bilibili.com/1796101901` |

> 不填 `SESSDATA` 也能连上，但只能看到部分消息；扫码登录后数据最完整。

<details>
<summary>手动获取 SESSDATA（不想扫码时）</summary>

1. 登录 Bilibili，打开浏览器开发者工具（F12）→ 存储 / Application
2. 查 Cookies 里的 `SESSDATA` 值，复制到配置页

</details>

### WebUI 监听地址

```yaml
webui:
  host: 0.0.0.0     # 要让手机上的郊狼 App 连进来，必须是 0.0.0.0
  port: 17800
```

### 关掉网页后自动退出

```yaml
webui:
  # 关掉所有网页后自动退出程序（启动后一个网页都没打开过则不会退出）
  exit_when_page_closed: true
  # 只在 OBS「浏览器源」里跑着的 /obs 页面，算不算「网页」
  #   false（默认）：不算 —— 关掉控制面板就退出，哪怕 OBS 里的覆盖层还开着
  #   true        ：算   —— OBS 开着时不会退出，免得直播到一半把程序关掉
  count_obs_pages: false
```

> 自己用**浏览器**打开 `/obs.html`、`/obs/strength` 这些页面（预览 / 摆位）是**照常算**「有人在看」的，
> 不会出现「停在 OBS 页面就被判定成网页全关」的情况。

### 触发配置速查（弹幕 / 礼物 / SC / 上舰）

> 这些都能在**配置页**里点选修改，改完保存即可（大部分**不用重启**）。
> `duration` 支持 `30s` / `1m` / `15m` 这种写法。

| 配置项 | 含义 | 默认 |
| --- | --- | :---: |
| `danmaku.enabled` | 是否启用弹幕触发 | `true` |
| `danmaku.strength_add` | 每条弹幕加多少强度 | `1` |
| `danmaku.duration` | 强度持续时长 | `30s` |
| `danmaku.rate_limit.enabled` | **同一用户限流**开关（防刷） | `true` |
| `danmaku.rate_limit.time_window` | 限流时间窗 | `1m` |
| `danmaku.rate_limit.max_count` | 窗口内最多触发几次 | `5` |
| `danmaku.guard_bonus` | 舰长/提督/总督发弹幕的额外加成 | 见配置 |
| `interact.enter` / `follow` / `share` / `special_follow` | 进房 / 关注 / 分享 / 特别关注 的 `enabled`+`strength_add`+`duration` | 见配置 |
| `gift.enabled`、`gift.tiers[]` | 礼物档位（`min_price` 起，对应 `strength_add` / `duration`） | 7 档 |
| `super_chat.enabled`、`super_chat.tiers[]` | SC 档位 | 4 档 |
| `guard.enabled`、`guard.levels['1'/'2'/'3']` | 总督 / 提督 / 舰长 的加值与时长 | 见配置 |
| `dglab.enabled` | 郊狼总开关（关掉=只显示不输出） | `true` |
| `dglab.mode` | `embedded` 内置 / `remote` 外置 Game Hub | `embedded` |
| `dglab.client_id` | 郊狼 App 扫码用的客户端 ID（可自定义） | `blivedglab` |
| `dglab.channel` | 事件（弹幕/礼物/SC/上舰）作用通道：`A` / `B` / `AB` | `A` |
| `dglab.pulse_id` | 内置波形 ID（见 `pulses.json`） | `d6f83af0`（呼吸） |
| `estop.auto_launch` | 启动主程序时同时拉起桌面停堆悬浮球 | `true` |
| `test.enabled` | 测试模式（出现「🧪 测试」页） | `false` |
| `log.level` | 日志级别 `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |

> ⚠️ 安全提醒：**单次加值 × 弹幕量 × 上限**决定了实际刺激强度，
> 详见 [SAFETY.md](./SAFETY.md) 的「直播场景的特别提醒」。
> 区分方式：页面里如果存在 `window.obsstudio`（OBS 浏览器源会注入它）就当成 OBS 里的覆盖层。

- 每个页面都会偷偷打一个心跳（`/api/page/heartbeat`），关页面时再补一个离开通知，
  所以**关掉最后一个网页约 5 秒后**程序会自己结束（比刷新慢一点点，但不会把刷新误判成关闭）
- 命令行临时改：`--exit-when-page-closed` / `--no-exit-when-page-closed`
- 配置页「WebUI 配置」里也有这两个开关（改完需要重启程序）
- 不想用这个行为，把 `exit_when_page_closed` 改成 `false` 即可；或者启动时加 `--no-browser`，
  一个网页都不打开，自然也不会触发

> 退出前会照常释放郊狼强度、停掉监听，和手动关窗口是一样的。

`127.0.0.1` 只能本机访问，手机永远连不上；`0.0.0.0` 会监听所有网卡，
请把它当成局域网内的私密页面，不要在公共 Wi-Fi 下使用。

### 测试相关配置

```yaml
test:
  enabled: true          # 打开后 WebUI 会出现「测试」页（等效于启动时加 --test）
```

命令行开关与它的关系：`--test` / `--fake` 会**强制开启**，优先级高于配置文件。

---

## 紧急停堆

> 🛑 两种方式，都**不需要打开浏览器**；推荐用桌面悬浮球（主程序不在前台也能点）。

### 方式一：桌面悬浮球（推荐，不依赖 Web）

**默认随主程序一起启动**，一条命令两个都起来：

```sh
python main.py
```

开关（`config.yaml`）：

```yaml
estop:
  auto_launch: true     # false 则不自动拉起悬浮球
```

命令行可以强制覆盖：

```sh
python main.py --estop      # 强制开启
python main.py --no-estop   # 强制关闭（优先级最高）
```

也可以**单独运行**（不启动主程序，纯当遥控器）：

```sh
python estop_window.py              # 自动读取 config.yaml 里的 webui 地址
python estop_window.py --port 18888 # 主程序换了端口
python estop_window.py --url http://192.168.1.5:17800
```

生命周期：主程序正常退出（Ctrl+C）时会把悬浮球一起收掉；如果是被硬杀
（`taskkill /F`）导致来不及收，悬浮球会在**失联 60 秒后自行退出**，不会残留一堆球。

- 一个常驻**桌面最上层**的红色圆球（无边框窗口），可拖到任意位置，位置会记住
- **左键单击 = 立即停堆** —— 停止是安全方向，刻意**不做二次确认**，避免紧急时手忙脚乱
- **右键 = 菜单**：恢复郊狼控制（有二次确认）/ 刷新状态 / 打开控制面板 / 退出
- 球下方实时显示当前强度，如 `A5/20  B0/20`，一眼能看到有没有在放电
- 状态配色：🔴 正常 · ⚫ 已停堆 · 🟠 连不上主程序

**外观细节**

- 玻璃质感球体 + 呼吸光晕，边缘是**抗锯齿**的（用 Pillow 超采样渲染，不是 tkinter 的硬边圆）
- 右下角有颗状态灯：🟢 郊狼设备已连接 · ⚪ 设备未连接 · 🟠 连不上主程序
- 球下面是深色胶囊，第一行是按钮名，第二行是实时强度（`A5/20  B0/20`）
- 悬停时圆环变亮；点下去后变成转圈的加载弧 + 「正在停堆…」
- 跟着系统 DPI 走，150% 缩放的屏幕上会自动放大，不会缩成一小坨
- 需要 Pillow（已在 `requirements.txt` 里）；**没装也能跑**，会自动退回 100% 由 tkinter
  绘制的旧画法（能用，但圆边有锯齿）。想让球好看：`pip install pillow`
- 打包后的 exe 已经把 Pillow 带进去了；自检一眼看出用的是哪种画法：
  `python estop_window.py --self-test`（或 `BiliLiveCoyote.exe --estop-window --estop-selftest`）

> 它本质是个"遥控器"：通过 `http://127.0.0.1:17800/api/hub/emergency-stop` 让主程序执行停堆，
> 所以**主程序必须正在运行**。连不上时圆球会变橙色并提示，不会假装停堆成功。

### 方式二：网页里的悬浮按钮

每个页面（首页 / 配置 / 郊狼控制 / OBS / 测试）右下角也有一个同样的悬浮按钮，
可以像桌宠一样拖动，行为与桌面版一致。

> OBS 浏览器源（`obs-source.html`）**不会**引入这个按钮，不会出现在直播画面里。

### 停堆时到底做了什么

无论用哪种方式，主程序都会按下面的顺序执行（顺序很重要）：

1. **先切断控制权** —— 之后任何弹幕 / 礼物 / SC / 上舰都不会再产生新指令
2. **取消所有正在计时的脉冲** —— 否则它们若干秒后还会补发一次回落指令
3. **A / B 强度立刻归零并清空波形缓冲**（内置模式直接下发 `clear` + `strength-0`）
4. **把 `dglab.enabled: false` 写回 `config.yaml`** —— 即使程序重启也是关闭状态，不会自己恢复

### HTTP 接口（也能给宏按键 / 自动化用）

| 接口 | 说明 |
| --- | --- |
| `POST /api/hub/emergency-stop` | 紧急停堆 |
| `POST /api/hub/resume` | 恢复控制 |

---

## 测试模式

> 🧪 开启方法见 [测试模式开启方法](#测试模式开启方法)（`--test` / `test.enabled` / `--fake` 三选一），
> 下面是细节玩法。

测试工具**不是另一个进程**，而是主程序的一个开关 —— 同一个进程、同一个端口、同一份 `config.yaml`，
不会和正在运行的 BiliLiveCoyote 冲突：

| 启动方式 | 连接 Bilibili | 测试页 / 事件注入 | 用途 |
| --- | :---: | :---: | --- |
| `python main.py` | ✅ | ❌ | 正式使用 |
| `python main.py --test` | ✅ | ✅ | **一边连真实直播间，一边注入测试事件** |
| `python main.py --fake` | ❌ | ✅ | 不连直播间，纯本地联调 |

> `python fake_room.py` 等价于 `python main.py --fake`，两个入口共用同一套实现。
>
> 也可以在 `config.yaml` 里长期打开，不必每次加参数：
> ```yaml
> test:
>   enabled: true
> ```

### 测试页 `/test.html`

`--test` 或 `--fake` 启动后，侧边栏会出现「🧪 测试」入口（普通模式下该入口不会出现，
`/api/test/*` 也一律返回 404）。

- 事件类型选择 + 自定义用户名 / 内容 / 金额 / 等级
- 连发 N 条 + 间隔（压测、验证限流）
- 快捷按钮：弹幕 / 礼物 / SC / 舰长 / 总督 / 进房 / 关注 / 分享 / 随机
- 自动随机刷事件、已发送统计、最近事件列表

注入的事件会以 Bilibili 原始协议报文的格式进入 blivedm 解析器，再走完整触发链路，
和真实直播间的处理路径完全一致：

```
原始协议 → blivedm 模型 → BilibiliHandler → DGLabController → 郊狼设备
```

### 命令行（`--fake` 模式下）

```sh
python main.py --fake
```

| 命令 | 说明 |
| --- | --- |
| `dm 666` | 发一条弹幕 |
| `gift 10 5` | 送 10 个、单价 5 元的礼物 |
| `sc 30 加油` | 发 30 元醒目留言 |
| `guard 1` | 开通总督（1 总督 / 2 提督 / 3 舰长） |
| `enter` `follow` `share` `special` `like` | 发一条互动消息 |
| `random 5` | 随机 5 条事件 |
| `burst danmaku 50 0.02` | 连发 50 条弹幕（压测 / 验证限流） |
| `auto 0.5` / `stop` | 自动随机刷事件 / 停止 |
| `stats` `help` `quit` | 统计 / 帮助 / 退出 |

脚本化（非交互）：

```sh
python main.py --fake --scenario burst --kind danmaku --count 50 --interval 0.02
python main.py --fake --scenario mixed --duration 30 --interval 0.5
python main.py --test --port 0            # 端口被占用时自动挑空闲端口
```

> 如果此时官方郊狼 App 已扫码连上本程序，模拟事件会**真的控制设备**；
> 只想观察日志的话，在配置页取消勾选「启用郊狼控制器」即可。

---

## 内置郊狼服务

> 免装 Node.js 版 Game Hub：官方「郊狼」App 直接扫码连本程序。

> **前提**：手机要能连进来，WebUI 必须监听 `0.0.0.0`（默认已是）。
> 如果你把它改回了 `127.0.0.1`，手机端会提示「服务器连接失败」——
> 在「郊狼控制」页面点「🔓 开启局域网访问」即可恢复。

默认情况下（`dglab.mode: embedded`），本程序自带郊狼 SOCKET 服务，
官方 App 直接扫码连接即可，无需再运行 Node.js 版 Game Hub：

1. 启动程序，打开 `http://localhost:17800/coyote.html`
2. 用下面**任意一种**方式连接（手机需和电脑处于同一局域网）：

   **方式 A：扫码 —— App 里没有「扫一扫」也能用**

   用手机的**相机**或**微信「扫一扫」**去扫页面上的二维码。二维码内容是官方 deep link
   （`https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://...`），
   系统会直接唤起「郊狼」App 并自动填好地址。

   **方式 B：手动填地址 —— 所有版本都适用**

   「郊狼控制」页面上有一行 **SOCKET 地址**（纯 WebSocket 地址），例如：

   ```
   ws://192.168.1.10:17800/dglab_ws/blivedglab
   ```

   复制后粘进 **App → 设备控制 → SOCKET 控制（网络控制）** 的地址输入框即可。
   如果该页面只让填「客户端 ID」，那就填最后一段 `blivedglab`，
   并把二维码内容切到「纯地址」再扫/填。

3. 连接成功后「郊狼控制」页会显示设备状态与实时强度，即可通过弹幕 / 礼物等事件控制

相关配置：

| 配置项 | 说明 |
| --- | --- |
| `dglab.mode` | `embedded` 使用内置服务，`remote` 使用外部 Game Hub |
| `dglab.client_id` | App 扫码使用的客户端 ID，修改后需要重新扫码 |
| `dglab.channel` | 事件控制哪个通道：`A` / `B` / `AB`（默认 `A`；`B` 需设备侧也允许 B 通道输出） |
| `dglab.pulse_id` | 输出波形 ID，内置波形见 `pulses.json`（如 `d6f83af0` 呼吸） |
| `dglab.advertise_host` | 可选，扫码地址对外使用的 IP，留空则自动探测局域网 IP |

> 如果你的电脑有多张网卡、或二维码里的 IP 手机无法访问，请把 `dglab.advertise_host`
> 设置为手机可以访问到的本机 IP（例如 `192.168.1.10`）。

### 切换到外置 Game Hub

把 `dglab.mode` 改为 `remote`，并填写 `controller_url` / `controller_id` 即可，
此时「郊狼控制」页面会直接内嵌外部 Game Hub 的控制台。

---

## OBS 集成

### 方式一：三个独立浏览器源（推荐）

在 OBS 里添加**三个**「浏览器源」，一个填一个地址，位置 / 大小 / 层级**直接用 OBS 自己的
「变换」拖拽**（OBS 标准用法），互不影响：

| 项目 | 地址 |
| --- | --- |
| ⚡ 电流强度 | `http://<本机IP>:17800/obs/strength` |
| 💰 投喂价格表 | `http://<本机IP>:17800/obs/price` |
| 💬 弹幕列表 | `http://<本机IP>:17800/obs/danmaku` |

每个地址只渲染自己那一块，页面背景透明，可以和摄像头、游戏画面自由叠。

> 打开 `http://localhost:17800/obs.html` 可以看到这三个地址，一键复制。

### 方式二：一个源包含全部

地址填 `http://<本机IP>:17800/obs-source.html`，三块内容在同一个源里，
位置用页内的拖拽编辑器调（见「自定义各项目位置」）。

`obs.html` 里勾选要显示的内容后会自动生成带参数的地址，页面下方有实时预览。

### OBS 显示内容

| 模块 | 说明 |
| --- | --- |
| **⚡ 实时电流强度** | A/B 两个通道的强度条 + `当前强度 / 上限`，设备一上报就刷新（WebSocket 推送，非轮询） |
| **💰 投喂价格表** | 自动读取当前 `config.yaml` 里的弹幕 / 礼物 / SC / 上舰档位，改完配置刷新页面即可生效 |
| 弹幕列表 | 从下往上滚动，含头像、用户名、舰长徽章、发送时间 |

> 三个区块的**位置和大小都可以自己拖**，见下一节。

| 触发反馈 | 消息里带本次触发的强度与持续时间 |
| 特殊消息 | 礼物、SC、上舰等 |

> 下面这套**页内排版**只对「方式二」的整页源有效；用独立源的话，位置直接在 OBS 里拖就行。

### 自定义各项目位置（仅方式二）

打开 `http://localhost:17800/obs.html`，页面下方的预览**已经开了编辑模式**，直接拖：

| 操作 | 效果 |
| --- | --- |
| **拖动区块** | 移动位置（百分比定位，改分辨率 / 拉伸窗口都不会跑偏） |
| **拖右下角小方块** | 缩放大小 |
| **双击区块** | 显示 / 隐藏 |
| **💾 保存布局** | 写入 `config.yaml` 的 `obs.layout`，**所有** OBS 源同步生效 |
| **↺ 重置默认** | 一键还原 |

可自由摆放的三个区块：**⚡ 电流强度**、**💰 投喂价格表**、**弹幕列表**。

也可以直接在 OBS 浏览器源里开编辑器：`/obs-source.html?edit=1`。

> 布局存在服务端，所以换场景、重装 OBS，只要地址一样位置就一样。
> 想给不同场景用不同布局，可以复制一份 `config.yaml`，或用下面的 URL 参数控制显隐。

### URL 参数

| 参数 | 说明 |
| --- | --- |
| `?strength=0` | 隐藏实时强度面板 |
| `?table=0` | 隐藏投喂价格表 |
| `?danmaku=0` | 隐藏弹幕列表 |
| `?only=strength` | 只渲染指定区块（等价于 `/obs/strength`） |
| `?edit=1` | 开启布局编辑模式 |

例如只要强度、不要价格表：`.../obs-source.html?table=0`（加号用 `&` 连接）。
两个面板都不需要时，`.../obs-source.html?strength=0&table=0` 就只剩弹幕列表。

---

## 项目结构

<details>
<summary>点开看完整目录树</summary>

```
.
├── main.py              # 主程序入口
├── bilibili.py          # Bilibili 直播监听模块（连接状态 + 自动重连）
├── bili_login.py        # 扫码登录 / 直播间信息解析 / 凭证持久化
├── dglab.py             # DG-Lab 控制器模块（embedded / remote 双模式）
├── coyote_hub.py        # 内置郊狼服务（DG-Lab SOCKET 协议服务端）
├── fake_room.py         # 本地模拟直播间（等价 main.py --fake，可单独运行）
├── estop_window.py      # 桌面「紧急停堆」悬浮球（独立小程序，不依赖浏览器）
├── pulses.json          # 内置波形数据
├── web.py               # Web UI 服务器
├── utils.py             # 工具函数（资源路径 / 时间解析等）
├── config.yaml          # 配置文件（打包后首次运行会复制到 exe 旁边）
├── requirements.txt     # Python 依赖
├── SAFETY.md            # 使用安全声明与免责声明（务必先读）
├── LICENSE              # GPL-3.0（标准全文，GitHub 会自动识别）
├── NOTICE               # 本项目版权与授权声明
├── LICENSE-MIT          # 上游 MIT 许可（fork 合规保留）
├── LICENSE-GameHub      # DG-Lab Coyote Game Hub 归属声明
├── THIRD_PARTY_LICENSES.md  # 第三方组件与许可全文
├── build.py             # 一键打包成 exe
├── build_exe.bat        # 双击打包（Windows）
├── make_icon.py         # 生成程序图标 app.ico
├── app.ico              # 程序图标
├── 启动.bat / start.bat # Windows 一键启动
├── dist/                # 打包产物：BiliLiveCoyote.exe + 上述许可文件
├── html/                # Web UI 前端文件
│   ├── index.html       # 首页
│   ├── config.html      # 配置页面
│   ├── login.html       # 扫码登录页（启动时自动打开）
│   ├── coyote.html      # 郊狼控制页面
│   ├── test.html        # 模拟直播间测试页
│   ├── obs.html         # OBS 页面
│   └── static/          # 静态资源
│       ├── style.css    # 主样式
│       ├── obs.css      # OBS 样式
│       ├── app.js       # 首页脚本
│       ├── config.js    # 配置页脚本
│       ├── coyote.js    # 郊狼控制页脚本
│       ├── test.js      # 测试页脚本
│       ├── login.js     # 扫码登录页脚本
│       ├── obs.js       # OBS 脚本
│       ├── estop.js     # 网页版悬浮停堆按钮
│       └── presence.js  # 页面心跳（关掉所有网页自动退出）
└── blivedm/             # Bilibili 直播弹幕库
```

</details>

---

## 常见问题

### 找不到「测试」页 / 怎么开测试模式？

测试页默认是关着的，三种开启方式任选一种：

```sh
python main.py --test        # 连真实直播间 + 打开测试页（推荐）
python main.py --fake        # 完全不连 B 站，只用模拟直播间
```

或者改 `config.yaml` 长期开启：

```yaml
test:
  enabled: true
```

开启后侧边栏会出现「🧪 测试」入口，也可直接访问 `http://localhost:17800/test.html`。
详见 [测试模式开启方法](#测试模式开启方法)。

### 为什么默认端口不是 8080？

8080 太热门了（Steam、各种开发服务器都爱占），撞上就是启动失败。默认**17800**，
想换随便改 `webui.port`（或 `python main.py --port 8888`、`--port 0` 自动挑空闲端口）。

### 扫码登录成功后程序会自己退出？

已修。原因是「扫码成功 → 自动填房间号 → 热切换直播间」时旧监听会被停掉，
主循环误以为监听彻底结束就跟着收工了。现在切换期间会打标记继续等新客户端，
扫码只会换直播间，不会把程序带走（回归用例见 `room_switch_test`）。

### 配置修改后需要重启吗？

大部分配置（弹幕、礼物、SC、上舰等）保存后立即生效，无需重启。但以下配置需要重启：
- WebUI 的 host 和 port
- Bilibili 的 room_id 和 sessdata

### 如何禁用郊狼控制？

在配置页面取消勾选 **启用郊狼控制器**，或在 `config.yaml` 中设置：

```yaml
dglab:
  enabled: false
```

> 关闭控制器时，程序会先把 A/B 通道强度归零再停止下发指令，不会把设备留在当前强度上；
> 脉冲进行到一半时关闭同样会立即释放。

### 每次启动都让我扫码，太麻烦 / 我想自动启动不弹窗

把登录模式改成 `auto` 或 `off` 即可（配置页「登录模式」下拉框，或 `config.yaml`）：

```yaml
bilibili:
  login_mode: auto    # 只在凭证失效时提示；off 则从不提示
```

> 之所以默认 `always`，是因为 B 站登录凭证会过期，**过期后监听会静默失效**
> （表现为"收不到弹幕"）。每次启动扫一次是最省心的做法；不想扫就改成 `auto`，
> 程序启动时会自动检测，发现失效了才提示你。

### 直播间监听不上 / 一直没有弹幕？

首页「状态」卡片会直接显示**直播间监听**的真实情况（监听中 / 监听异常 + 具体错误 + 重连次数），
先看那里给的错误信息。常见原因：

| 现象 | 处理 |
| --- | --- |
| 首页显示「监听异常」+ `InitError` | 房间号不对，用配置页的「🔍 解析并切换」重新解析一次 |
| 一直「连接中…」但没弹幕 | 房间可能真的没人说话（先发一条弹幕试试）；确认直播间号是你的房间 |
| 收到 `AuthError` / 部分消息缺失 | `SESSDATA` 失效，重新扫码登录 |
| 报 `HTTP 412` / 风控 | 请求被 B 站限流，等几分钟会自动重连；频繁触发请降低重连频率 |
| 聊天区大量「未知命令」 | 正常，B 站新增消息类型，不影响弹幕/礼物 |

程序**遇到断开会自动重连**（5s 起，逐次退避到最多 60s），不会静默卡死。

### 强度加不上去 / 提示「已达强度上限」？

**「上限」是设备侧的软上限**（郊狼 V3 用蓝牙 `BF` 指令写入、断电保存），
而 SOCKET/网络协议只有 `strength` / `pulse` / `clear` 三种消息，**没有修改上限的指令**，
所以程序端无法调整（原版 Game Hub 也是只读）—— 这是安全设计。

要调高上限，请在**郊狼 App** 里操作：

1. 先断开 SOCKET 连接（SOCKET 模式下 App 的强度调节通常会被锁住）
2. 在设备/控制页面把「强度上限」调高（不同版本入口不同：多数是把强度条拖到最高后继续拖，
   或长按强度数值；部分设备需要先按主机上的按键）
3. 重新用 SOCKET 连接，程序会自动读到新的上限

程序侧现在会明确提示，而不是静默不动：

- 「郊狼控制」页面常驻显示当前 A/B 通道上限
- 到达上限时，手动控制区标黄提示「⚠️ 已达强度上限 20，无法继续提升」
- 日志（同样内容 30 秒最多一条）：
  `[郊狼] A 通道已达强度上限 20，无法继续提升（上限由郊狼 App 设置，程序无法修改）`

### 弹幕只加 A 通道 / 怎么控制 B 通道？

事件（弹幕 / 礼物 / SC / 上舰）默认只驱动 **A 通道**。想单独控制 B 通道，或让两个通道一起动，
把 `dglab.channel` 改成 `B` / `AB` 即可（配置页「🎮 DG-Lab → 控制通道」，保存后立即生效）：

```yaml
dglab:
  channel: B    # A（默认）/ B / AB（双通道）
```

> B 通道能否真正输出还取决于设备 / App：内置郊狼服务按官方 SOCKET 协议直接控制 B 通道；
> 若使用外部 Game Hub，需要把它的 `bChannelMode` 设为 `discrete`（独立模式），
> `sync` 模式下 B 跟随 A，`off` 模式则完全关闭 B。
>
> 「郊狼控制」页面里的 **B 通道 +1 / −1 / 归零** 按钮是独立的手动测试，不受该配置影响。

### 郊狼 App 提示「服务器连接失败」怎么办？

按顺序排查：

1. **WebUI 是否监听在 `0.0.0.0`**（最常见）。「郊狼控制」页面顶部若出现红色告警，
   说明只监听了 `127.0.0.1`，手机永远连不上 —— 点页面上的「🔓 开启局域网访问」，
   或把 `config.yaml` 改成下面这样再重启：
   ```yaml
   webui:
     host: 0.0.0.0
   ```
2. **Windows 防火墙**：第一次运行时防火墙弹窗要点「允许访问」。
   如果当时点了取消，去「Windows 安全中心 → 防火墙和网络保护 → 允许应用通过防火墙」
   把 `python.exe` 勾上（专用 + 公用）。
3. **手机和电脑确实在同一个局域网**：手机关掉流量 / VPN，不要连来宾网络
   （很多路由器的访客 Wi-Fi 开了 AP 隔离，设备之间互相不可见）。
4. **地址里的 IP 手机能不能访问**：用**手机浏览器**打开
   `http://<页面上的IP>:17800/api/hub/status`，能出 JSON 说明网络已通。
   出不来就是上面 1~3 的问题。电脑有多张网卡时，用 `dglab.advertise_host` 指定正确的 IP。

### App 的 SOCKET 页面里没有「扫一扫」怎么办？

不用扫 —— 二维码本来就是设计给**手机系统相机 / 微信**扫的：扫完会通过官方 deep link
唤起 App 并自动填好地址。

如果你的 App 只能手动填地址，在「郊狼控制」页面复制那行 **SOCKET 地址**（`ws://...`）
粘进去即可；只让填 ID 的话就填 `blivedglab` 这一段。

### 郊狼 App 扫码后连不上 / 一直没有强度？

1. 确认手机与运行本程序的电脑处于**同一局域网**
2. 打开 `http://<本机IP>:17800/coyote.html`，检查二维码里的 IP 是否为手机能访问到的地址；
   如果电脑有多张网卡，请在 `config.yaml` 里显式设置 `dglab.advertise_host` 为正确的本机 IP
3. 确认「郊狼控制」页面的连接状态为 **已连接**
4. 部分系统 / 杀毒软件会拦截外部设备连接本机端口，请放行 WebUI 的监听端口

### 启动时报「端口已被占用」怎么办？

WebUI 端口（默认 17800，故意避开常被 Steam 等软件占用的 8080）被别的程序占了，最常见的原因是**已经有一个实例在运行**。
不需要再开第二个进程 —— 正在运行的那个实例本身就能提供测试页（用 `--test` 启动的话），
或者直接换个端口启动：

```sh
python main.py --port 0            # 自动挑一个空闲端口
python main.py --port 8081
python main.py --test              # 让正在跑的这个实例提供测试页
```

查看是谁占用了端口（Windows）：

```bat
netstat -ano | findstr ":17800"
tasklist | findstr <上面查到的 PID>
```

### 保存配置后 config.yaml 里的注释没了？

**现在不会了**：

- 写回配置时用 `ruamel.yaml` **保留注释与键顺序** —— 它是 `requirements.txt` 里的依赖，
  **启动时若检测到缺失，日志和配置页都会明确提醒你怎么装**
- 每次写回前都会**自动备份**到 `config.yaml.bak`
- 写回后**自检注释行数**：万一变少了会打 ERROR 并提示备份位置
- 没装 `ruamel.yaml` 时会退回 PyYAML（此时注释确实会丢），但会**明确报错**而不是静默清空

### 内置模式和外部 Game Hub 能同时用吗？

不能。`dglab.mode` 为 `embedded` 时使用内置服务；为 `remote` 时使用外部 Game Hub，
此时「郊狼控制」页面会内嵌 Game Hub 的控制台。

### OBS 页面刷新后没有历史弹幕？

OBS 页面会自动加载最近 50 条弹幕历史记录。如果没有显示，请检查：
1. 程序是否正常运行
2. WebSocket 连接是否正常（查看浏览器控制台）

### 我只是关了个网页，程序怎么就退出了？

这是 `webui.exit_when_page_closed: true`（默认开启）的行为：**关掉所有网页**后程序会自己退出。
不想这样的话：

- 配置页「WebUI 配置」里取消勾选「关掉所有网页后自动退出程序」（重启生效）
- 或者改 `config.yaml`：`webui.exit_when_page_closed: false`
- 或者启动时加 `--no-exit-when-page-closed`

OBS 里的**浏览器源**默认不算「网页」，所以关掉控制面板就会退出；
如果你想让「OBS 还开着」也算，把 `webui.count_obs_pages` 改成 `true`。
（用浏览器自己打开的 `/obs.html`、`/obs/xxx` 页面无论怎么设置都算「有人在看」。）

---

## 来源与许可

- **源码仓库：[buyiqidao/BiliLiveCoyote](https://github.com/buyiqidao/BiliLiveCoyote)**（GPL-3.0 分发 exe 时，指回这个地址即可满足「提供对应源码」）
- 本项目原名叫 **Blive_DGLAB**，**fork 自 [xyBakaQAQ/Blive_DGLAB](https://github.com/xyBakaQAQ/Blive_DGLAB)**（MIT），
  现更名 **BiliLiveCoyote**。在它基础上做了**大量改动与重写**（扫码登录、内置郊狼服务、
  OBS 独立源、本地模拟直播间、桌面紧急停堆悬浮球、单文件 exe 打包等）。
  上游的 MIT 版权与许可声明完整保留在 [LICENSE-MIT](./LICENSE-MIT)。
  （如果你是从上游找过来的：老名字、老配置都能直接用，只是 exe 改叫 `BiliLiveCoyote.exe`。）
- 本项目整体以 **GNU GPL v3** 发布，见 [LICENSE](./LICENSE)；本项目自己的版权与授权声明在 [NOTICE](./NOTICE)。
  之所以是 GPL-3.0：内置的波形数据来自 [DG-Lab Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub)
  （其 `LICENSE` 文件为 GPL-3.0），需要按 GPL 合规分发。
- **[DG-Lab Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub)**（作者 Hyperzlib）：
  本项目的内置郊狼服务参考其 SOCKET 协议**重新实现**，内置波形数据 `pulses.json`
  由其 `server/data/pulse.json5` 转换而来。完整归属声明见 [LICENSE-GameHub](./LICENSE-GameHub)。
- 内嵌的 [blivedm](https://github.com/xfgryujk/blivedm) 以 MIT 分发，许可全文见
  [blivedm/LICENSE](./blivedm/LICENSE)。
- **所有第三方组件、版本与许可全文**见 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)；
  打包好的 exe 同样适用（同源分发）。

---

## 许可证

本项目整体采用 **GNU General Public License v3.0**，详见 [LICENSE](./LICENSE)。

- 本项目自己的版权与授权声明见 [NOTICE](./NOTICE)；GPL-3.0 全文见 [LICENSE](./LICENSE)
  （LICENSE 刻意保持成**未经改动的标准全文**，这样 GitHub 才能自动识别出 GPL-3.0）
- 上游 [xyBakaQAQ/Blive_DGLAB](https://github.com/xyBakaQAQ/Blive_DGLAB) 的 MIT 许可与版权声明
  保留在 [LICENSE-MIT](./LICENSE-MIT)（本项目在其基础上大幅改动）
- [DG-Lab Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub)（Hyperzlib）的归属声明、
  协议与波形数据来源说明见 [LICENSE-GameHub](./LICENSE-GameHub)
- 内嵌库 [blivedm](https://github.com/xfgryujk/blivedm) 的 MIT 许可保留在 [blivedm/LICENSE](./blivedm/LICENSE)
- 其余第三方组件见 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)

GPL-3.0 意味着：你可以自由使用、修改、再分发本项目（包括打包后的 exe），
但**再分发时必须同样以 GPL-3.0 提供完整源码**，并保留上述各项版权声明。

---

## 致谢

感谢以下项目的支持与贡献：

- **[xyBakaQAQ/Blive_DGLAB](https://github.com/xyBakaQAQ/Blive_DGLAB)** - 本项目的上游（MIT）
- **[blivedm](https://github.com/xfgryujk/blivedm)** - Bilibili 直播弹幕库（MIT）
- **[DG-Lab Coyote Game Hub](https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub)** - 内置郊狼服务的协议与波形数据参考（作者 Hyperzlib；该仓库 `LICENSE` 为 GPL-3.0，`package.json` 写 MIT，详见 [LICENSE-GameHub](./LICENSE-GameHub)）
