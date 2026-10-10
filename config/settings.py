from pathlib import Path
import sys

# 程序所在目录
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent.absolute()
else:
    BASE_DIR = Path(__file__).parent.parent.absolute()

# 工具目录
TOOLS_DIR = BASE_DIR / "tools"
PLATFORM_TOOLS = TOOLS_DIR / "platform-tools"
MTKCLIENT_DIR = TOOLS_DIR / "mtkclient-main"
UNLOCK_MTK_DIR = TOOLS_DIR / "mtkclient-G12NL-UnlockTools"
SPD_DUMP_DIR = TOOLS_DIR / "spd_dump"
PUBKEY_DIR = TOOLS_DIR / "公钥解锁"
DEPS_DIR = TOOLS_DIR / "支持库及驱动"
SCRCPY_DIR = TOOLS_DIR / "Scrcpy"
TEMP_DIR = BASE_DIR / "临时文件"
GSI_DIR = BASE_DIR / "GSI"
MUSIC_FILE = BASE_DIR / "bgm.mp3"
SUBTITLE_FILE = BASE_DIR / "subtitle.txt"
PVZ_ICON = BASE_DIR / "pvz.png"
SPONSOR_QR_PATH = TOOLS_DIR / "1788422639995.jpg"
# 启动画面图片（splash.jpg，放在项目根目录）
SPLASH_IMAGE_PATH = BASE_DIR / "splash.jpg"
# 在文件末尾添加
# 植物大战僵尸彩蛋
PVZ_ZIP_URL = "https://github.com/paimeng49/fuckwjhnmsl_tool_box_packages/releases/download/%E7%A5%9E%E7%A7%98%E5%B0%8F%E6%B8%B8%E6%88%8F/pvz.zip"  # 替换为真实链接
PVZ_DIR = BASE_DIR / "植物大战僵尸"
PVZ_EXE_PATH = PVZ_DIR / "PlantsVsZombies.exe"  # 根据实际exe名修改
PVZ_FONT_PATH = PVZ_DIR / "方正少儿体.ttf"  # 字体文件（已放在游戏目录）

# 创建必要目录
TEMP_DIR.mkdir(exist_ok=True)
GSI_DIR.mkdir(exist_ok=True)

# GSI 镜像源
GSI_MIRRORS = {
    "GitHub官方直连": "",
    "gh.gitwarp.top": "https://gh.gitwarp.top/",
    "gh-proxy.org": "https://gh-proxy.org/",
    "v6.gh-proxy.org": "https://v6.gh-proxy.org/",
    "gh.xmly.dev": "https://gh.xmly.dev/",
    "api.gitproxy.dev": "https://api.gitproxy.dev/",
}

# GSI 预设镜像
# config/settings.py 中的 GSI_PRESETS 部分（修正后）

# GSI 预设镜像（使用最新 GitHub 原始链接，无加速前缀）
GSI_PRESETS = {
    "安卓11 (LineageOS 18.1)": {
        "url": "https://github.com/paimeng49/fuckwjhnmsl_tool_box_packages/releases/download/%E5%88%B7%E6%9C%BA%E5%8C%85/lineage-18.1-20220715-UNOFFICIAL-arm64_bvS.img.xz",
        "compress": "xz",
        "version": 11
    },
    "安卓12 (LineageOS 19.1)": {
        "url": "https://github.com/paimeng49/fuckwjhnmsl_tool_box_packages/releases/download/%E5%88%B7%E6%9C%BA%E5%8C%85/lineage-19.1-20231017-UNOFFICIAL-arm64_bvN.img.7z",
        "compress": "7z",
        "version": 12
    },
    "安卓13 (MikuUI TDA)": {
        "url": "https://github.com/xiaoleGun/treble_build_miku/releases/download/TDA-1.0.1/MikuUI-TDA-1.0.1-arm64-ab-gapps-20231104-UNOFFICIAL.zip",
        "compress": "zip",
        "version": 13
    }
}

# 实用网站列表
USEFUL_SITES = [
    ("萤火虫资源站 - 导航页", "https://www.yhcres.top/"),
    ("萤火虫资源站 - 类原生GSI列表", "https://www.yhcres.top/01-GSI/01-%E7%B1%BB%E5%8E%9F%E7%94%9F"),
    ("Mio Kitchen (ROM解包工具)", "https://www.yhcres.top/00-%E5%B7%A5%E5%85%B7%E9%A9%B1%E5%8A%A8%E6%A8%A1%E5%9D%97/04-%E8%A7%A3%E5%8C%85%E6%89%93%E5%8C%85%E9%80%86%E5%90%91ROM%E7%A7%BB%E6%A4%8D/MIO-KITCHEN%EF%BC%88MKC%E6%96%B0%E5%B7%A5%E5%85%B7%EF%BC%89"),
    ("扶小鹰玩机资源", "https://www.yhcres.top/03-%E5%AD%A6%E4%B9%A0%E6%9C%BA%E3%80%81%E5%AE%B6%E6%95%99%E6%9C%BA%E3%80%81%E5%AD%A6%E7%94%9F%E5%8D%A1%E3%80%81%E5%AD%A6%E7%94%9F%E5%B9%B3%E6%9D%BF%E3%80%81%E5%84%BF%E7%AB%A5%E6%89%8B%E6%9C%BA/%E6%89%B6%E5%B0%8F%E9%B9%B0%E5%AD%A6%E4%B9%A0%E6%9C%BA"),
    ("TrebleDroid GSI列表", "https://github.com/TrebleDroid/treble_experimentations/wiki/Generic-System-Image-%28GSI%29-list"),
    ("柚坛Wiki - 刷机百科", "https://wiki.uotan.cn/index.php?title=%E9%A6%96%E9%A1%B5"),
    ("KoCleo的资源站", "https://kc.fuquan.moe/"),
]

# ===================== 全局镜像源设置 =====================
# 默认使用第一个（即 GitHub 官方直连）
ACTIVE_MIRROR = "GitHub官方直连"

# G12NL FRP 文件
G12NL_FRP_URL = "https://github.com/paimeng49/fuckwjhnmsl_tool_box_packages/releases/download/%E8%A7%A3%E9%94%81%E6%96%87%E4%BB%B6/G12NL.bin"

# ===================== 展讯强解工具下载配置 =====================
SPD_UNLOCK_TOOLS = {
    "T606/T616": {
        "url": "https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader/releases/download/1.72/ums9230_universal_unlock_UFS.dangerous.zip",
        "bat_name": "unlock_autopatch_9230.bat",
    },
    "T610/T618": {
        "url": "https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader/releases/download/1.72/ums9230_universal_unlock_UFS.dangerous.zip",
        "bat_name": "unlock_autopatch_9230.bat",
    },
}

# 展讯强解需要备份的分区
SPD_BACKUP_PARTITIONS = ["splloader", "uboot_a", "uboot_b"]

# 展讯强解修复时需要写入的分区（目标分区名: 备份文件名）
SPD_REPAIR_PARTITIONS = {
    "splloader": "splloader",
    "splloader_bak": "splloader",
    "uboot_a": "uboot_a",
    "uboot_b": "uboot_b",
}

# 展讯公钥解锁脚本目录（已在 tools/公钥解锁/ 中）
# 脚本顺序：获取解锁码 → 制作令牌 → 正式解锁
SPD_PUBKEY_STEPS = [
    ("1-获取identifier_token.bat", "步骤1/3：获取解锁码"),
    ("2-生成signature.bat", "步骤2/3：制作解锁令牌"),
    ("3-解锁BL.bat", "步骤3/3：正式解锁"),
]

def get_active_mirror_prefix():
    """获取当前全局镜像源的前缀（空字符串表示直连）"""
    return GSI_MIRRORS.get(ACTIVE_MIRROR, "")