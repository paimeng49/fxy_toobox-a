# -*- mode: python ; coding: utf-8 -*-
"""
扶小鹰工具箱 PyInstaller 打包脚本
- 工具目录（tools/）外置，不打进包内，需和 exe 放在同一目录
- 资源文件（图标、音乐、图片、字幕等）打包进 exe
- 第三方库自动收集
"""
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import sys

# 项目根目录
project_root = Path('.').absolute()
pathex = [str(project_root)]

# ============ 第三方库 ============
third_party_libs = [
    'customtkinter',
    'requests',
    'py7zr',
    'just_playback',
    'CTkFileDialog',   # CTKFileDialog-plus（安装后包名是 CTkFileDialog）
    'PIL',
]

datas = []
binaries = []
hiddenimports = []

for lib in third_party_libs:
    try:
        d, b, h = collect_all(lib)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[WARN] 收集 {lib} 失败: {e}")

# ============ 项目内部模块 ============
# 所有 gui/pages 和 core 下的模块都加进去，防止静态分析漏检
project_modules = [
    # config
    'config.settings',
    'config.constants',
    # core
    'core.device',
    'core.mtk_tools',
    'core.spd_tools',
    'core.gsi_download',
    'core.flashing',
    'core.logger',
    'core.easter_eggs',
    'core.custom_cmd',
    'core.game_download',
    # gui
    'gui.main_window',
    'gui.pages.home_page',
    'gui.pages.fastboot_page',
    'gui.pages.spd_page',
    'gui.pages.mtk_page',
    'gui.pages.unlock_page',
    'gui.pages.wheelchair_page',
    'gui.pages.custom_cmd_page',
    'gui.pages.sites_page',
]
hiddenimports += project_modules

# ============ 资源文件（打进包里）============
# 注意：tools/ 目录外置，不打包在这里！
root_resource_files = [
    # 图标
    ('app_icon.ico', '.'),
    # 启动画面
    ('splash.jpg', '.'),
    # 背景音乐
    ('bgm.mp3', '.'),
    ('subtitle.txt', '.'),
    ('pvz.png', '.'),
]

for filename, target_dir in root_resource_files:
    src = project_root / filename
    if src.exists():
        datas.append((str(src), target_dir))

# 图标路径（不存在就用默认图标）
icon_file = project_root / 'app_icon.ico'
icon_path = str(icon_file) if icon_file.exists() else None

# ============ PyInstaller Analysis ============
a = Analysis(
    ['main.py'],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,  # 优化级别：移除断言和 docstring，减小体积
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FxyToolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # 没装 UPX 就保持 False；装了可以改成 True 进一步压缩
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,    # 隐藏控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
