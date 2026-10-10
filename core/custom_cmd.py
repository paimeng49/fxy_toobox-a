# core/custom_cmd.py
import subprocess
import os
from config import settings

# 全局变量：当前工作目录，默认为项目根目录
# 必须转成 str，避免 Path 对象传入 subprocess 时编码出错
current_cwd = str(settings.BASE_DIR)

def execute_custom_command(cmd):
    global current_cwd

    stripped_cmd = cmd.strip()

    # 处理 cd 命令（修复跨进程 cd 无效的问题）
    if stripped_cmd.lower().startswith("cd "):
        target_dir = stripped_cmd[3:].strip().strip('"')
        if target_dir:
            # 支持相对路径和绝对路径
            resolved = os.path.abspath(os.path.join(current_cwd, target_dir))
            if os.path.isdir(resolved):
                current_cwd = resolved
                return 0, f"已切换目录: {current_cwd}", ""
            else:
                return -1, f"目录不存在: {resolved}", ""
        else:
            return 0, current_cwd, ""  # 输出当前目录

    # 1. 处理 mtkclient 命令 (py mtk.py / python mtk.py / mtk.py)
    if stripped_cmd.startswith("py mtk.py ") or stripped_cmd.startswith("python mtk.py ") or stripped_cmd.startswith("mtk.py "):
        if stripped_cmd.startswith("py "):
            args_part = stripped_cmd[2:].strip()
        elif stripped_cmd.startswith("python "):
            args_part = stripped_cmd[6:].strip()
        else:
            args_part = stripped_cmd
        args_part = args_part.replace("mtk.py ", "", 1).strip()
        args_list = args_part.split() if args_part else []
        
        # 调用 mtk_tools 通过 bat 执行
        from core import mtk_tools
        return mtk_tools.run_mtk_command(args_list)

    # 2. 处理 spd_dump 命令
    elif stripped_cmd.startswith("spd_dump"):
        # 强制转换为字符串，防止 Windows 路径编码问题
        cwd = str(settings.SPD_DUMP_DIR)
        try:
            result = subprocess.run(stripped_cmd, cwd=cwd, capture_output=True, text=True, shell=True, encoding='gbk', errors='replace', timeout=60)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "命令执行超时"

    # 3. 处理 adb / fastboot 命令
    elif stripped_cmd.startswith("adb") or stripped_cmd.startswith("fastboot"):
        # 强制转换为字符串，防止 Windows 路径编码问题
        cwd = str(settings.PLATFORM_TOOLS)
        try:
            result = subprocess.run(stripped_cmd, cwd=cwd, capture_output=True, text=True, shell=True, encoding='gbk', errors='replace', timeout=60)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "命令执行超时"

    # 4. 其他命令（dir、del、echo 等），在当前工作目录执行
    else:
        try:
            result = subprocess.run(stripped_cmd, cwd=current_cwd, capture_output=True, text=True, shell=True, encoding='gbk', errors='replace', timeout=60)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "命令执行超时"
        except Exception as e:
            return -1, "", str(e)