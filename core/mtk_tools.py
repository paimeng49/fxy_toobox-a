# core/mtk_tools.py
import subprocess
import threading
import time
from config import settings

def run_bat(bat_path, cwd=None, interactive=False, output_callback=None, auto_enter=False):
    """
    执行BAT脚本
    :param bat_path: BAT文件路径
    :param cwd: 工作目录
    :param interactive: 是否弹新窗口（True）或实时捕获（False）
    :param output_callback: 每行输出回调
    :param auto_enter: 是否自动向stdin发送回车（用于跳过 pause）
    """
    if not bat_path.exists():
        return -1, "", f"错误：找不到 {bat_path}"
    try:
        if interactive:
            subprocess.Popen(f'start "" "{bat_path}"', cwd=cwd, shell=True)
            return 0, "已启动窗口", ""
        else:
            proc = subprocess.Popen(
                f'cmd /c "{bat_path}"', cwd=cwd, shell=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', bufsize=1
            )

            # 智能 auto_enter：检测到 pause 关键词才发回车
            pause_keywords = ["pause", "按任意键", "press any key", "请按任意键"]

            def reader():
                for line in iter(proc.stdout.readline, ''):
                    if output_callback and line.strip():
                        output_callback(line.rstrip())
                    # 智能 auto_enter：检测到 pause 相关提示后才发回车
                    if auto_enter:
                        lower_line = line.lower()
                        if any(kw in lower_line for kw in pause_keywords):
                            try:
                                proc.stdin.write("\n")
                                proc.stdin.flush()
                            except Exception:
                                pass

            threading.Thread(target=reader, daemon=True).start()

            proc.wait()
            return proc.returncode, "", ""
    except Exception as e:
        return -1, "", str(e)

def open_mtk_gui(output_callback=None):
    bat_path = settings.MTKCLIENT_DIR / "mtk_gui.bat"
    return run_bat(bat_path, cwd=settings.MTKCLIENT_DIR, interactive=False, output_callback=output_callback)

def run_mtk_command(args, output_callback=None):
    import os
    cmd_str = " ".join(args)
    bat_content = f'@echo off\nchcp 65001 >nul\ncd /d "{settings.MTKCLIENT_DIR}"\npy mtk.py {cmd_str}\n'
    bat_path = settings.TEMP_DIR / "_mtk_cmd.bat"
    try:
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        return run_bat(bat_path, cwd=settings.MTKCLIENT_DIR, output_callback=output_callback)
    except Exception as e:
        return -1, "", str(e)
    finally:
        # 用完清理临时文件
        try:
            if bat_path.exists():
                os.remove(bat_path)
        except Exception:
            pass

def run_mtk_unlock(output_callback=None):
    bat_path = settings.MTKCLIENT_DIR / "解锁BL.bat"
    return run_bat(bat_path, cwd=settings.MTKCLIENT_DIR, interactive=False, output_callback=output_callback)


def run_g12nl_unlock(output_callback=None):
    """
    G12NL 专用解锁 —— 使用原版 mtkclient 调整参数解锁（G12NL解锁BL.bat）。
    仅执行解锁脚本，不做成功/失败判断，由用户自行确认结果。
    :return: (returncode, stdout, stderr)
    """
    bat_path = settings.MTKCLIENT_DIR / "G12NL解锁BL.bat"
    if not bat_path.exists():
        if output_callback:
            output_callback(f"❌ 找不到解锁脚本: {bat_path}")
            output_callback("请确认 tools/mtkclient-main/ 目录下有 G12NL解锁BL.bat")
        return -1, "", f"找不到 {bat_path}"
    ret, out, err = run_bat(
        bat_path,
        cwd=settings.MTKCLIENT_DIR,
        interactive=False,
        output_callback=output_callback
    )
    if output_callback:
        output_callback("")
        output_callback("=" * 50)
        output_callback("💡 解锁命令已执行完成")
        output_callback("💡 请检查设备状态，确认 BL 是否解锁成功")
        output_callback("=" * 50)
    return ret, out, err


def open_mtk_g12nl_gui(output_callback=None):
    """
    G12NL 设备唤出 GUI —— 执行 mtk_gui-G12NL.bat
    """
    bat_path = settings.MTKCLIENT_DIR / "mtk_gui-G12NL.bat"
    if not bat_path.exists():
        if output_callback:
            output_callback(f"❌ 找不到脚本: {bat_path}")
        return -1, "", f"找不到 {bat_path}"
    return run_bat(bat_path, cwd=settings.MTKCLIENT_DIR, interactive=False, output_callback=output_callback)


def run_install_deps(output_callback=None):
    bat_path = settings.MTKCLIENT_DIR / "安装依赖.bat"
    return run_bat(bat_path, cwd=settings.MTKCLIENT_DIR, interactive=False, output_callback=output_callback)

# ===================== G12NL FRP 解锁 =====================

def download_frp_file():
    mirror_prefix = settings.get_active_mirror_prefix()
    full_url = mirror_prefix + settings.G12NL_FRP_URL if mirror_prefix else settings.G12NL_FRP_URL
    save_path = settings.MTKCLIENT_DIR / "G12NL.bin"
    if save_path.exists():
        return True, str(save_path)
    import requests
    try:
        response = requests.get(full_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True, str(save_path)
    except Exception as e:
        return False, str(e)

def run_g12nl_frp_unlock(output_callback=None):
    """
    执行“改FRP.bat”写入 FRP 分区，实时输出日志，自动跳过 pause
    """
    status, path = download_frp_file()
    if not status:
        return False, f"FRP 文件下载失败: {path}"
    bat_path = settings.MTKCLIENT_DIR / "改FRP.bat"
    if not bat_path.exists():
        return False, f"错误：找不到 {bat_path}"
    ret, out, err = run_bat(bat_path, cwd=settings.MTKCLIENT_DIR, interactive=False, output_callback=output_callback, auto_enter=True)
    if ret != 0:
        return False, f"改FRP.bat 执行失败: {err or out}"
    return True, "写入完成。请手动开机，然后继续操作。"
