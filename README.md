# FxyToolbox 扶小鹰工具箱

> 面向学习机和自用设备的一键刷机工具箱  
> 作者：派 蒙~ | 邮箱：fdggydh@outlook.com  
> **本工具永久免费，请勿用于商业用途。**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-Free-green)

---

## 项目简介
### 注意：本项目使用AI辅助开发！

FxyToolbox（扶小鹰工具箱）是一款面向学习机（扶小鹰、家教机等）和自用设备的刷机工具箱，集成了从解锁 Bootloader 到刷入 GSI 镜像的全流程操作。工具箱支持联发科（MTK）和展讯（SPD）两大平台，内置多种解锁方案，并提供一键刷机模式——解锁 + 刷机一条龙。

基于 CustomTkinter 构建的现代化 GUI，操作直观，小白也能上手。

---

## 功能特性

### 📱 多平台支持
- **联发科（MTK）**：解锁BL、集成MTKClient
- **展讯（SPD）**：强解（CVE-2022-38694）、公钥解锁、分区读写备份、FDL2 引导

### 🚀 一键刷机
选择解锁方案 + 选择 GSI 镜像 → 自动完成下载、解锁、刷入、擦除、重启全流程

### 🛠️ Fastboot/ADB 工具
- 分区表读取与可视化
- 分区刷写、擦除、格式化
- Userdata 擦除
- APK 批量安装
- 设备重启（多种模式）
- 实时进度显示

### 🔧 其他功能
- **自定义命令**：直接执行 adb / fastboot / spd_dump / mtk 命令
- **实用网站**：聚合 GSI 镜像、ROM 解包、刷机百科等常用网站
- **驱动一键安装**：MTK / 展讯 / ADB 驱动
- **多镜像源切换**：GitHub 加速镜像，国内下载不再慢
- **日志系统**：自动轮转，最多保留 20 个日志文件

---

## 系统要求

| 项目 | 要求 |
| :--- | :--- |
| 操作系统 | Windows 10 / 11（64 位） |
| Python（源码运行） | 3.10 及以上 |
| 数据线 | 建议原装数据线 |
| USB 接口 | 建议主板后置 USB 接口 |

---

## 快速开始

### 方式一：源码运行（推荐开发者）

#### 1. 克隆项目

```bash
git clone https://github.com/paimeng49/fxy_toobox-a.git
cd fxy_toobox-a
```

#### 2. 安装 Python 依赖

```bash
pip install customtkinter requests py7zr just_playback pillow CTkFileDialog-plus
```


#### 3. 准备工具目录

`tools/` 目录包含刷机所需的二进制工具（fastboot、adb、spd_dump、mtkclient 等），**需要单独准备**，不能随源码分发。请自行下载放置：

```
tools/
├── platform-tools/          # Google ADB/Fastboot 工具
├── spd_dump/                # 展讯 spd_dump 工具
├── mtkclient-main/          # MTKClient 原版
├── mtkclient-G12NL-UnlockTools/  # G12NL 修改版解锁工具
├── 公钥解锁/                # 展讯公钥解锁脚本
├── 支持库及驱动/            # 各种驱动安装包
└── Scrcpy/                  # Scrcpy 投屏工具（可选）
```

#### 4. 运行

```bash
python main.py
```

---

### 方式二：编译为 EXE（打包分发）

#### 1. 安装 PyInstaller

```bash
pip install pyinstaller
```

#### 2. 确保资源文件齐全

项目根目录下需要有这些文件（打包时会被嵌入）：

- `app_icon.ico` — 程序图标
- `splash.jpg` — 启动画面
- `bgm.mp3` — 启动音乐
- `subtitle.txt` — 副标题列表
- `pvz.png` — 小游戏预览图（可选，没有也能打包）

#### 3. 执行打包

```bash
pyinstaller 扶小鹰工具箱打包.spec
```

或者直接运行打包脚本：

```bash
打包.bat
```

#### 4. 打包完成

生成的 exe 在 `dist/` 目录下：

```
dist/
└── FxyToolbox.exe          # 单文件 exe
```

#### 5. 分发

将 `FxyToolbox.exe` 和 `tools/` 目录放在一起即可使用：

```
FxyToolbox/
├── FxyToolbox.exe
└── tools/                  # 工具目录（必须和 exe 同级）
    ├── platform-tools/
    ├── spd_dump/
    └── ...
```

> **注意**：`tools/` 目录外置，不会被打进 exe。这样做的好处是工具可以单独更新，不用重新打包。

---

### 方式三：直接使用预编译版（普通用户）

下载 Release 中的压缩包，解压后双击 `FxyToolbox.exe` 即可运行，无需安装 Python。

首次使用请先在「综合」页面安装驱动。

---

## 使用指南

### 1. 安装驱动

打开工具箱 → 「综合」页面 → 勾选需要的驱动 → 点击「一键安装所选驱动」。

通常需要安装：
- 展讯 USB 驱动（展讯设备）
- MTK USB 驱动（联发科设备）
- Google ADB/Fastboot 驱动

### 2. 选择镜像源

在「综合」页面右侧选择 GitHub 下载镜像源，点击「确认切换镜像源」。国内用户建议选择加速镜像（如 `gh.gitwarp.top`、`gh-proxy.org` 等）。

### 3. 解锁 Bootloader

进入「解锁 Bootloader」页面，选择对应的解锁方案，点击「执行」。

#### 支持的解锁方案

| 方案 | 适用平台 | 说明 |
| :--- | :--- | :--- |
| MTK-G12NL 解锁 | 联发科 G12NL | 修改版 mtkclient 解锁（seccfg/wrong length 为假报错） |
| MTK 通用解锁 | 联发科通用 | mtkclient 原版解锁 |
| 展讯强解 | 展讯 T606/T616/T610/T618 | CVE-2022-38694 漏洞强制解锁，带修复功能 |
| 展讯公钥解锁 | 展讯通用 | 公钥解锁脚本三步解锁 |
| G12NL FRP 解锁 | 联发科 G12NL | 清除 FRP 锁定 |

### 4. 一键刷机

进入「一键刷机」页面：

1. 选择解锁方案
2. 选择 GSI 镜像（内置安卓 11/12/13，或手动选择本地 `system.img`）
3. 点击「开始刷机」
4. 按照提示操作即可

#### 一键刷机流程

```
选择方案 → 下载GSI → 解锁BL → 检查解锁状态 → 切换fastbootd
→ 刷vbmeta → 刷GSI → 重启Bootloader → 擦userdata → 重启开机
```

---

## 项目结构

```
FxyToolbox/
├── main.py                 # 程序入口
├── config/                 # 配置
│   ├── settings.py         # 全局设置（路径、镜像源等）
│   └── constants.py        # 常量（作者声明、GSI 预设等）
├── core/                   # 核心逻辑
│   ├── device.py           # 设备检测、命令执行
│   ├── flashing.py         # 统一刷机流程
│   ├── mtk_tools.py        # 联发科解锁工具封装
│   ├── spd_tools.py        # 展讯工具封装
│   ├── gsi_download.py     # GSI 镜像下载与解压
│   ├── error_watchdog.py   # 错误看门狗
│   ├── logger.py           # 日志系统
│   ├── easter_eggs.py      # 彩蛋功能
│   ├── custom_cmd.py       # 自定义命令执行
│   └── game_download.py    # 小游戏下载
├── gui/                    # 界面
│   ├── main_window.py      # 主窗口
│   └── pages/              # 各功能页面
│       ├── home_page.py        # 综合页
│       ├── fastboot_page.py    # Fastboot/ADB
│       ├── spd_page.py         # 展讯
│       ├── mtk_page.py         # 联发科
│       ├── unlock_page.py      # 解锁Bootloader
│       ├── wheelchair_page.py  # 一键刷机
│       ├── custom_cmd_page.py  # 自定义命令
│       └── sites_page.py       # 实用网站
├── tools/                  # 刷机工具（外置，不打包进 exe）
│   ├── platform-tools/     # ADB/Fastboot
│   ├── spd_dump/           # 展讯工具
│   ├── mtkclient-main/     # MTKClient
│   └── ...
├── GSI/                    # GSI 镜像缓存目录
├── app_icon.ico            # 程序图标
├── splash.jpg              # 启动画面
├── bgm.mp3                 # 启动音乐
├── subtitle.txt            # 副标题列表
├── 扶小鹰工具箱打包.spec   # PyInstaller 打包配置
└── 打包.bat                # 打包脚本
```

---

## 常见问题

### Q：打开软件提示找不到驱动 / 设备无法识别？

先去「综合」页面安装驱动。如果安装后仍无法识别：
- 换一根数据线（很多线只能充电不能传数据）
- 换一个 USB 接口（建议主机后置接口）
- 打开设备管理器看看有没有黄色感叹号
- 展讯设备需要进入深刷模式才能识别（关机 → 长按音量减 → 插入数据线）

### Q：G12NL 解锁时报 "seccfg write failure" 或 "Wrong length" 错误？

这是修改版解锁工具的**已知假报错**，实际上 BL 已经成功解锁了。看到「解锁命令已执行完成」就说明流程跑完了。

### Q：展讯强解后设备黑屏 / 黑砖了？

部分机器强解后会出现黑砖。工具箱内置了修复功能，强解完成后会询问是否需要修复。如果跳过了修复，重新进入解锁页面跑一遍强解流程即可。

### Q：下载 GSI 镜像特别慢 / 下载失败？

- 去「综合」页面切换 GitHub 加速镜像源
- 也可以手动下载 GSI 镜像后，在一键刷机页面点「手动选择 system.img」

### Q：刷完机后一直卡在开机画面？

首次开机可能需要 5-10 分钟（系统在初始化）。如果超过 10 分钟还没进去：
- 长按电源键 10 秒强制关机，再重新开机
- 可能 GSI 镜像和设备不兼容，换一个镜像试试
- 确保刷机前擦除了 userdata

### Q：软件会被杀毒软件报毒吗？

因为是 PyInstaller 打包的 Python 程序，部分杀毒软件可能误报。可以添加信任名单。本工具不含任何恶意代码，源码可自行审计。

### Q：展讯设备怎么进入深刷模式（FDL2）？

关机状态下，**长按音量减键不放**，同时插入数据线。如果按了没反应：
- 确保设备已完全关机
- 长按音量减不放，再插线，插线后继续按住 3-5 秒
- 检查驱动是否安装正确

---

## 注意事项

1. **刷机会清除数据**：解锁 BL 和擦除 userdata 都会清空设备内所有数据，请提前备份
2. **操作期间不要断开数据线**：刷写过程中断线可能导致设备变砖
3. **设备电量**：建议设备电量在 30% 以上再操作
4. **不要同时运行多个实例**：同时操作多个设备时，fastboot/adb 命令会冲突
5. **日志文件**：日志保存在程序目录下，单文件 10MB 自动轮转，最多保留 20 个

---

## 支持的 GSI 镜像

| 镜像名称 | 安卓版本 | 来源 | 压缩格式 |
| :--- | :--- | :--- | :--- |
| LineageOS 18.1 | 安卓 11 | LineageOS 官方 | xz |
| LineageOS 19.1 | 安卓 12 | LineageOS 官方 | 7z |
| MikuUI TDA 1.0.1 | 安卓 13 | MikuUI | zip |

也可以手动下载其他 GSI 镜像，在一键刷机页面点「手动选择 system.img」。

---

## 免责声明

本工具仅供学习和研究使用。使用者需自行承担刷机带来的一切风险，包括但不限于设备损坏、数据丢失、保修失效等。作者不对任何因使用本工具造成的损失负责。

**刷机有风险，开刷需谨慎。**

---

## 致谢

- **群友们** — 提供的 bug 日志和测试
- 所有开源项目的贡献者们

---

—— 派 蒙~  2026.10
