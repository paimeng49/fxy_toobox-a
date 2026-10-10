# core/device.py
import subprocess
import re
from config import settings

def run_command(cmd, cwd=None, capture=True, timeout=None):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True,
                                shell=True, encoding='utf-8', errors='replace',
                                timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令执行超时"
    except Exception as e:
        return -1, "", str(e)

def get_device_mode():
    """
    检测当前设备连接模式
    返回: "adb" | "fastboot" | "none"
    """
    # 先检测 fastboot（速度快）
    ret, out, err = run_command("fastboot devices", cwd=settings.PLATFORM_TOOLS)
    if ret == 0:
        for line in (out + err).strip().splitlines():
            parts = line.split()
            # fastboot devices 输出格式: 序列号 fastboot
            if len(parts) >= 2 and parts[1] == "fastboot":
                return "fastboot"

    # 再检测 adb
    ret, out, _ = run_command("adb devices", cwd=settings.PLATFORM_TOOLS)
    if ret == 0:
        for line in out.strip().splitlines():
            if "List of devices" in line:
                continue
            parts = line.split()
            # adb devices 输出格式: 序列号 device/offline/unauthorized/...
            if len(parts) >= 2 and parts[1] == "device":
                return "adb"
    return "none"

def get_fastboot_all_data():
    ret, out, err = run_command("fastboot getvar all", cwd=settings.PLATFORM_TOOLS)
    combined_output = out + err  # 核心：合并 stdout 和 stderr

    info = {}
    partitions = []

    if ret != 0:
        info["错误"] = "无法获取设备信息"
        return info, partitions

    # 解析设备信息
    for line in combined_output.splitlines():
        line = line.strip()
        if line.startswith("(bootloader)"):
            data = line[len("(bootloader)"):].strip()
            if ":" in data:
                key, value = data.split(":", 1)
                info[key.strip()] = value.strip()

    # 解析分区表
    # 兼容两种格式：
    #   (bootloader) partition-size:boot:0x4000000        (无空格)
    #   (bootloader) partition-size: switch: 0x2000       (有空格)
    pattern = re.compile(r"\(bootloader\)\s+partition-size:\s*([^:]+):\s*([0-9a-fA-FxX]+)")
    size_map = {}
    for line in combined_output.splitlines():
        match = pattern.search(line)
        if match:
            name = match.group(1).strip()
            size_hex = match.group(2).strip()
            size_map[name] = size_hex

    # 如果上面没匹配到，尝试无 (bootloader) 前缀的格式
    if not size_map:
        pattern2 = re.compile(r"partition-size:\s*([^:]+):\s*([0-9a-fA-FxX]+)")
        for line in combined_output.splitlines():
            match = pattern2.search(line)
            if match:
                name = match.group(1).strip()
                size_hex = match.group(2).strip()
                size_map[name] = size_hex

    for name in sorted(size_map.keys()):
        partitions.append({"name": name, "size": format_size(size_map[name])})

    if "serialno" in info: info["设备序列号"] = info["serialno"]
    if "product" in info: info["产品型号"] = info["product"]
    if "unlocked" in info: info["解锁状态"] = ("已解锁" if info["unlocked"] == "yes" else "已锁定")
    if "current-slot" in info: info["当前槽位"] = info["current-slot"]
    if "secure" in info: info["安全启动"] = ("开启" if info["secure"] == "yes" else "关闭")

    return info, partitions

def format_size(hex_str):
    try:
        size = int(hex_str, 16)
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    except:
        return hex_str