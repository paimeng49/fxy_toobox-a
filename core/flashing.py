# core/flashing.py
import os
import re
import time
import subprocess
from pathlib import Path
from config import settings
from core.device import get_device_mode, run_command

def get_is_userspace():
    """检测是否处于 userspace fastboot (fastbootd) 模式"""
    ret, out, err = run_command("fastboot getvar is-userspace", cwd=settings.PLATFORM_TOOLS, timeout=10)
    combined = (out + err).lower()
    if ret == 0 and "yes" in combined:
        return True
    return False

def check_fastboot_unlocked():
    """检查设备是否已解锁 BL"""
    ret, out, err = run_command("fastboot getvar unlocked", cwd=settings.PLATFORM_TOOLS, timeout=10)
    combined = (out + err).lower()
    if ret == 0 and "yes" in combined:
        return True
    if ret == 0 and "no" in combined:
        return False
    return None

def run_fastboot_with_progress(cmd: str, cwd, log_callback=None, progress_callback=None) -> int:
    """
    运行 fastboot 命令，实时捕获进度。
    fastboot 进度用 \\r（回车）更新同一行，用 os.read() 读原始字节，
    按 \\r 和 \\n 分割，才能抓到中间进度。
    进度行节流：只在百分比变化 >= 10% 时才写日志。
    """
    process = subprocess.Popen(
        cmd, cwd=cwd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
    )

    fd = process.stdout.fileno()
    buffer = ""
    last_logged_pct = -1.0

    while True:
        raw = os.read(fd, 4096)
        if not raw:
            break

        text = raw.decode('utf-8', errors='replace')
        buffer += text

        parts = re.split(r'[\r\n]', buffer)
        buffer = parts[-1]

        for line in parts[:-1]:
            line = line.strip()
            if not line:
                continue

            pct_match = re.search(r'\((\d+\.\d+)%\)', line)
            if pct_match:
                pct = float(pct_match.group(1))
                if progress_callback:
                    progress_callback(pct, line)
                if log_callback and (pct - last_logged_pct >= 10.0 or pct >= 100.0):
                    log_callback(line)
                    last_logged_pct = pct
            else:
                block_match = re.search(r'(\d+)/(\d+)', line)
                if block_match and progress_callback:
                    current_block = int(block_match.group(1))
                    total_blocks = int(block_match.group(2))
                    if total_blocks > 0:
                        pct = current_block / total_blocks * 100
                        progress_callback(pct, line)
                        if log_callback and (pct - last_logged_pct >= 10.0 or pct >= 100.0):
                            log_callback(line)
                            last_logged_pct = pct
                elif log_callback:
                    log_callback(line)

    if buffer.strip():
        if log_callback:
            log_callback(buffer.strip())
        pct_match = re.search(r'\((\d+\.\d+)%\)', buffer)
        if pct_match and progress_callback:
            progress_callback(float(pct_match.group(1)), buffer.strip())

    process.wait()
    return process.returncode


def unified_flash(gsi_path: str, is_spd: bool = False, log_callback=None, progress_callback=None, check_unlocked=True):
    """
    统一刷机流程（从 fastbootd 开始）：
    1. 检测设备是否在 fastbootd
    2. 不是就 adb/fastboot reboot fastboot 切到 fastbootd
    3. 在 fastbootd 写 system（刷入 GSI）
    4. 重启到 bootloader（fastboot reboot bootloader）
    5. 擦 userdata
    6. 重启开机
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not gsi_path or not Path(gsi_path).exists():
        log("❌ GSI 文件不存在")
        return False

    log("🔹 进入统一刷机阶段...")

    # ---- 步骤0：检查解锁状态 ----
    if check_unlocked:
        log("检查设备解锁状态...")
        unlocked = check_fastboot_unlocked()
        if unlocked is True:
            log("✅ 设备已解锁 BL")
        elif unlocked is False:
            log("❌ 设备未解锁 BL！无法继续刷机")
            return False
        else:
            log("⚠️ 无法自动检测解锁状态，请自行确认设备已解锁 BL")
            if log_callback:
                # 通知调用方让用户手动确认
                pass  # 一键刷机页面会处理这个

    # ---- 步骤1：检测 fastbootd ----
    mode = get_device_mode()
    if mode != "fastboot":
        log("❌ 设备未处于 fastboot 模式，请确保设备已连接")
        return False

    if get_is_userspace():
        log("✅ 设备已在 fastbootd 模式")
    else:
        log("⚠️ 设备处于 bootloader 模式，正在切换到 fastbootd...")
        run_command("fastboot reboot fastboot", cwd=settings.PLATFORM_TOOLS)
        for _ in range(30):
            time.sleep(2)
            mode = get_device_mode()
            if mode == "fastboot" and get_is_userspace():
                log("✅ 已成功切换到 fastbootd")
                break
        else:
            log("❌ 无法切换到 fastbootd，请手动重启到 fastbootd")
            return False

    # ---- 步骤2：刷入 vbmeta（关闭 AVB） ----
    vbmeta_path = settings.BASE_DIR / "vbmeta.img"
    if vbmeta_path.exists():
        log("刷入 vbmeta 关闭 AVB...")
        run_command(
            f"fastboot flash vbmeta --disable-verity --disable-verification \"{vbmeta_path}\"",
            cwd=settings.PLATFORM_TOOLS
        )
    else:
        log("⚠️ 未找到 vbmeta.img，跳过 AVB 处理")

    # ---- 步骤3：在 fastbootd 写 system ----
    log(f"准备刷写 GSI: {gsi_path}")
    log(f"镜像大小: {Path(gsi_path).stat().st_size / (1024 * 1024):.1f} MB")

    ret = run_fastboot_with_progress(
        f"fastboot flash system \"{gsi_path}\"",
        cwd=settings.PLATFORM_TOOLS,
        log_callback=log,
        progress_callback=progress_callback,
    )
    if ret != 0:
        log(f"❌ GSI 刷入失败（返回码: {ret}）")
        return False
    log("✅ GSI 刷入成功！")

    # ---- 步骤4：重启到 bootloader ----
    log("重启到 Bootloader（fastboot reboot bootloader）...")
    run_command("fastboot reboot bootloader", cwd=settings.PLATFORM_TOOLS)
    for _ in range(30):
        time.sleep(2)
        mode = get_device_mode()
        if mode == "fastboot":
            log("✅ 已进入 Bootloader 模式")
            break
    else:
        log("❌ 未检测到 Bootloader 模式")
        return False

    # ---- 步骤5：擦除 userdata ----
    log("正在擦除 userdata...")
    ret_erase, _, _ = run_command(
        "fastboot erase userdata", cwd=settings.PLATFORM_TOOLS, capture=True
    )
    if ret_erase != 0:
        log("❌ userdata 擦除失败，降级到 Recovery 手动清除...")
        run_command("fastboot reboot recovery", cwd=settings.PLATFORM_TOOLS)
        log("请在 Recovery 中手动清除数据后重启")
        return False
    log("✅ userdata 擦除成功！")

    # ---- 步骤6：重启开机 ----
    log("✅ 刷机完成！正在重启到系统...")
    run_command("fastboot reboot", cwd=settings.PLATFORM_TOOLS)
    log("⚠️ 首次开机可能需要 5-10 分钟，请耐心等待。")
    return True
