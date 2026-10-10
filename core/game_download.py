# core/game_download.py
import zipfile
import shutil
import subprocess
import time
from pathlib import Path
from config import settings
import requests


def _build_mirror_list(preferred_prefix: str) -> list:
    """
    构建镜像源尝试列表：优先当前选中的，然后按顺序尝试其他所有镜像
    """
    mirrors = list(settings.GSI_MIRRORS.values())
    # 把首选的放第一个（如果有的话）
    if preferred_prefix and preferred_prefix in mirrors:
        mirrors.remove(preferred_prefix)
        mirrors.insert(0, preferred_prefix)
    # 直连（无前缀）放最后兜底
    if "" not in mirrors:
        mirrors.append("")
    return mirrors


def _resolve_url(raw_url: str, mirror_prefix: str) -> str:
    """根据镜像源前缀拼接完整下载 URL"""
    if not mirror_prefix:
        return raw_url
    if not mirror_prefix.endswith("/"):
        mirror_prefix += "/"
    # GitHub 链接去掉域名后拼到镜像前缀前面
    if raw_url.startswith("https://github.com/"):
        return mirror_prefix + raw_url[len("https://github.com/"):]
    return mirror_prefix + raw_url


def _get_mirror_name(prefix: str) -> str:
    """根据镜像前缀获取镜像源名称"""
    if not prefix:
        return "直连"
    for name, p in settings.GSI_MIRRORS.items():
        if p == prefix:
            return name
    return "未知镜像源"


def download_file_with_progress(raw_url, save_path, preferred_mirror_prefix="", progress_callback=None, max_retries=3):
    """
    通用文件下载：多镜像源自动切换 + 断点续传 + 重试 + 进度回调
    :param raw_url: 原始下载链接（GitHub 直链）
    :param save_path: 保存路径（Path 对象）
    :param preferred_mirror_prefix: 首选镜像源前缀
    :param progress_callback: 进度回调函数 callback(percent, status_text, speed_str, eta_str)
    :param max_retries: 每个镜像源的最大重试次数
    :return: (成功与否, 消息)
    """
    mirror_list = _build_mirror_list(preferred_mirror_prefix)
    tmp_path = save_path.with_suffix(save_path.suffix + ".downloading")
    last_error = "未知错误"

    for mirror_prefix in mirror_list:
        full_url = _resolve_url(raw_url, mirror_prefix)
        mirror_name = _get_mirror_name(mirror_prefix)

        for retry in range(max_retries):
            retry_text = f"（第{retry + 1}次重试）" if retry > 0 else ""
            status_text = f"下载中 [{mirror_name}]{retry_text}"

            # 断点续传：已下载的字节数
            downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
            headers = {}
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"

            try:
                response = requests.get(full_url, stream=True, timeout=30, headers=headers)

                # 服务器不支持断点续传（返回200而不是206），从头下
                if downloaded > 0 and response.status_code == 200:
                    downloaded = 0
                    tmp_path.unlink(missing_ok=True)

                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                if downloaded > 0 and total_size > 0:
                    total_size += downloaded  # Range 请求返回的是剩余大小

                mode = "ab" if downloaded > 0 else "wb"
                start_time = time.time()
                last_update = start_time

                with open(tmp_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # 限流更新，避免UI卡
                            now = time.time()
                            if now - last_update >= 0.3 and progress_callback and total_size > 0:
                                last_update = now
                                pct = downloaded / total_size * 100
                                elapsed = now - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                speed_str = f"{speed / 1024 / 1024:.1f} MB/s"
                                remaining = total_size - downloaded
                                eta = remaining / speed if speed > 0 else 0
                                eta_str = f"{int(eta // 60)}分{int(eta % 60)}秒" if eta > 0 else "--"
                                progress_callback(pct, status_text, speed_str, eta_str)

                # 下载完成，重命名
                tmp_path.rename(save_path)
                if progress_callback:
                    progress_callback(100, f"下载完成 [{mirror_name}]", "0 MB/s", "0秒")
                return True, f"下载成功（镜像源: {mirror_name}）"

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if progress_callback:
                    progress_callback(0, f"[{mirror_name}] 下载失败: {e}", "0", "--")
                # 等一下再重试
                if retry < max_retries - 1:
                    time.sleep(2 ** retry)

        # 这个镜像源不行，试下一个
        if progress_callback:
            progress_callback(0, f"镜像源 {mirror_name} 失败，尝试下一个...", "0", "--")

    return False, f"所有镜像源均失败: {last_error}"


def download_and_install_pvz(log_callback=None, progress_callback=None):
    """
    下载植物大战僵尸，安装字体，返回exe路径
    多镜像源自动切换 + 断点续传 + 重试
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    # 检查是否已存在
    if settings.PVZ_EXE_PATH.exists():
        log("已存在植物大战僵尸，直接启动")
        return str(settings.PVZ_EXE_PATH)

    # 首选镜像源
    preferred_prefix = settings.get_active_mirror_prefix()

    zip_path = settings.PVZ_DIR / "pvz.zip"
    settings.PVZ_DIR.mkdir(parents=True, exist_ok=True)

    # 如果 zip 已经下载完成了就直接解压
    if zip_path.exists() and zip_path.stat().st_size > 0:
        log("安装包已存在，跳过下载")
    else:
        log(f"开始下载植物大战僵尸...")
        success, msg = download_file_with_progress(
            raw_url=settings.PVZ_ZIP_URL,
            save_path=zip_path,
            preferred_mirror_prefix=preferred_prefix,
            progress_callback=progress_callback
        )
        log(msg)
        if not success:
            return None

    log("下载完成，开始解压...")

    # 解压
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(settings.PVZ_DIR)
    except Exception as e:
        log(f"解压失败: {e}")
        return None

    # 安装字体（复制到系统字体目录）
    if settings.PVZ_FONT_PATH.exists():
        log("正在安装游戏字体...")
        font_dest = Path("C:/Windows/Fonts") / settings.PVZ_FONT_PATH.name
        try:
            shutil.copy(settings.PVZ_FONT_PATH, font_dest)
            log("字体安装完成")
        except Exception as e:
            log(f"字体安装失败（不影响游戏运行）: {e}")

    return str(settings.PVZ_EXE_PATH)


def launch_pvz(log_callback=None):
    """启动植物大战僵尸"""
    exe_path = download_and_install_pvz(log_callback=log_callback)
    if exe_path:
        subprocess.Popen(exe_path, cwd=str(settings.PVZ_DIR), shell=True)
    else:
        if log_callback:
            log_callback("❌ 植物大战僵尸下载失败，无法启动")
