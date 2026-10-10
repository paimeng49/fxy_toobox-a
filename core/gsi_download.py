# core/gsi_download.py
import os
import time
import requests
import lzma
import zipfile
import shutil
from pathlib import Path
from config import settings

# 下载重试次数
_MAX_RETRIES = 3
# 重试间隔（秒），指数退避
_RETRY_DELAY_BASE = 2
# 下载块大小（1MB）
_CHUNK_SIZE = 1024 * 1024


def _format_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读形式"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024):.1f} MB"
    else:
        return f"{size_bytes / (1024*1024*1024):.2f} GB"


def _build_mirror_list(selected_prefix: str) -> list[str]:
    """
    构建镜像源尝试列表：优先当前选中的，然后按顺序尝试其他镜像
    返回镜像前缀列表（空字符串代表官方直连）
    """
    mirrors = list(settings.GSI_MIRRORS.values())
    # 去重并把选中的放第一个
    result = [selected_prefix] if selected_prefix else []
    for m in mirrors:
        if m not in result:
            result.append(m)
    # 确保官方直连（空字符串）也在列表里
    if "" not in result:
        result.append("")
    return result


def _resolve_url(raw_url: str, mirror_prefix: str) -> str:
    """根据镜像源前缀拼接完整下载 URL"""
    if not mirror_prefix:
        return raw_url
    if not mirror_prefix.endswith("/"):
        mirror_prefix += "/"
    if raw_url.startswith("https://github.com/"):
        return mirror_prefix + raw_url[len("https://github.com/"):]
    return mirror_prefix + raw_url


# ============== 旧接口兼容层（给一键刷机页面用） ==============

def download_gsi_with_progress(raw_url: str, mirror_prefix: str, progress_callback=None):
    """
    旧版接口：下载并解压 GSI 镜像（兼容一键刷机页面的调用方式）
    :param raw_url: 原始 GitHub 下载链接
    :param mirror_prefix: 镜像源前缀
    :param progress_callback: 进度回调 func(percent, text, speed, eta)
    :return: (success: bool, result: str) — 成功返回 (True, 文件路径)，失败返回 (False, 错误信息)
    """
    save_dir = settings.GSI_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    # 从 URL 提取文件名
    file_name = raw_url.split("/")[-1]
    # URL 解码
    from urllib.parse import unquote
    file_name = unquote(file_name)

    # 最终解压后的目标路径（先假设是 img，后面按压缩格式调整）
    extracted_path = _guess_extracted_path(save_dir, file_name)

    # 如果解压后的文件已存在，直接返回成功
    if extracted_path and extracted_path.exists() and extracted_path.stat().st_size > 0:
        if progress_callback:
            progress_callback(100, "文件已存在，跳过下载", "0", "0")
        return True, str(extracted_path)

    # 压缩包临时文件路径
    temp_file = save_dir / (file_name + ".downloading")
    final_archive = save_dir / file_name

    mirror_list = _build_mirror_list(mirror_prefix)
    last_error = ""

    for attempt_prefix in mirror_list:
        full_url = _resolve_url(raw_url, attempt_prefix)
        mirror_name = _get_mirror_name(attempt_prefix)

        for retry in range(_MAX_RETRIES):
            retry_text = f"（第 {retry + 1} 次重试）" if retry > 0 else ""
            status_text = f"使用镜像源: {mirror_name} {retry_text}"
            if progress_callback:
                progress_callback(0, status_text, "0", "--")

            try:
                # 断点续传
                downloaded = 0
                mode = "wb"
                if temp_file.exists():
                    downloaded = temp_file.stat().st_size
                    mode = "ab"

                headers = {}
                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"

                start_time = time.time()

                with requests.get(
                    full_url,
                    stream=True,
                    timeout=30,
                    headers=headers,
                    allow_redirects=True,
                ) as response:
                    # 416 = 已经下完了
                    if response.status_code == 416:
                        temp_file.rename(final_archive)
                        break

                    response.raise_for_status()

                    total_size = int(response.headers.get("content-length", 0))
                    if downloaded > 0 and response.status_code == 200:
                        downloaded = 0
                        mode = "wb"

                    overall_total = downloaded + total_size if total_size > 0 else 0

                    with open(temp_file, mode) as f:
                        for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                                # 计算速度和 ETA
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                speed_text = _format_size(int(speed)) + "/s"

                                if overall_total > 0:
                                    pct = downloaded / overall_total * 100
                                    remaining = overall_total - downloaded
                                    eta_sec = remaining / speed if speed > 0 else 0
                                    eta_text = f"{int(eta_sec // 60)}分{int(eta_sec % 60)}秒" if eta_sec > 60 else f"{int(eta_sec)}秒"
                                    status_text = f"下载中: {_format_size(downloaded)} / {_format_size(overall_total)}"
                                else:
                                    pct = 0
                                    eta_text = "--"
                                    status_text = f"下载中: {_format_size(downloaded)}"

                                if progress_callback:
                                    progress_callback(pct, status_text, speed_text, eta_text)

                # 下载完成
                temp_file.rename(final_archive)

                if progress_callback:
                    progress_callback(100, "下载完成，开始解压...", "0", "0")

                # 解压
                success, result = _extract_archive_compat(final_archive, save_dir, progress_callback)
                if success:
                    return True, result
                else:
                    last_error = result
                    # 解压失败也算这个源失败，继续试下一个
                    continue

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if progress_callback:
                    progress_callback(0, f"下载失败（第 {retry + 1} 次）: {e}", "0", "--")
                if retry < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY_BASE ** retry)
                continue

        # 这个镜像源失败了，试下一个
        if progress_callback:
            progress_callback(0, f"镜像源 {mirror_name} 失败，尝试下一个...", "0", "--")

    return False, f"GSI下载失败: {last_error}"


def _guess_extracted_path(save_dir: Path, file_name: str):
    """根据压缩文件名猜测解压后的目标路径"""
    lower = file_name.lower()
    if lower.endswith(".img.xz"):
        return save_dir / file_name[:-3]
    elif lower.endswith(".img.gz"):
        return save_dir / file_name[:-3]
    elif lower.endswith(".7z") or lower.endswith(".zip"):
        # zip/7z 里面的文件名不确定，返回 None 让解压函数自己处理
        return None
    elif lower.endswith(".img"):
        return save_dir / file_name
    return None


def _get_mirror_name(prefix: str) -> str:
    """根据镜像前缀获取镜像源名称"""
    if not prefix:
        return "GitHub官方直连"
    for name, p in settings.GSI_MIRRORS.items():
        if p == prefix:
            return name
    return "未知镜像源"


def _extract_archive_compat(archive_path: Path, save_dir: Path, progress_callback=None):
    """
    解压各种格式的压缩包（兼容旧接口）
    :return: (success, result_path_or_error)
    """
    file_name = archive_path.name
    lower = file_name.lower()

    try:
        if lower.endswith(".xz"):
            # xz 格式（通常是单文件 .img.xz）
            if progress_callback:
                progress_callback(0, "正在解压 xz 文件...", "0", "--")

            out_name = file_name[:-3]  # 去掉 .xz
            out_path = save_dir / out_name
            total_size = archive_path.stat().st_size
            processed = 0
            start_time = time.time()

            with lzma.open(archive_path, "rb") as f_in:
                with open(out_path, "wb") as f_out:
                    while True:
                        chunk = f_in.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        processed += len(chunk)
                        if total_size > 0 and progress_callback:
                            pct = min(processed / total_size * 100, 99.9)
                            elapsed = time.time() - start_time
                            speed = processed / elapsed if elapsed > 0 else 0
                            speed_text = _format_size(int(speed)) + "/s"
                            progress_callback(pct, f"解压中: {_format_size(processed)} / {_format_size(total_size)}", speed_text, "--")

            if progress_callback:
                progress_callback(100, "解压完成", "0", "0")
            return True, str(out_path)

        elif lower.endswith(".zip"):
            # zip 格式
            if progress_callback:
                progress_callback(0, "正在解压 zip 文件...", "0", "--")

            with zipfile.ZipFile(archive_path, 'r') as zf:
                # 找里面最大的 .img 文件
                img_files = [n for n in zf.namelist() if n.lower().endswith(".img")]
                if not img_files:
                    return False, "zip 包中找不到 .img 文件"

                # 选最大的 img 文件作为 GSI
                largest = max(img_files, key=lambda n: zf.getinfo(n).file_size)
                out_path = save_dir / Path(largest).name

                # 解压（带进度）
                total = zf.getinfo(largest).file_size
                processed = 0
                start_time = time.time()

                with zf.open(largest) as src, open(out_path, 'wb') as dst:
                    while True:
                        chunk = src.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        dst.write(chunk)
                        processed += len(chunk)
                        if total > 0 and progress_callback:
                            pct = min(processed / total * 100, 99.9)
                            elapsed = time.time() - start_time
                            speed = processed / elapsed if elapsed > 0 else 0
                            speed_text = _format_size(int(speed)) + "/s"
                            progress_callback(pct, f"解压中: {_format_size(processed)} / {_format_size(total)}", speed_text, "--")

            if progress_callback:
                progress_callback(100, "解压完成", "0", "0")
            return True, str(out_path)

        elif lower.endswith(".7z"):
            # 7z 格式 — Python 标准库不支持，尝试用 py7zr，如果没有就返回错误
            try:
                import py7zr
            except ImportError:
                return False, "不支持 7z 格式解压（缺少 py7zr 库），请手动解压或安装 py7zr"

            if progress_callback:
                progress_callback(0, "正在解压 7z 文件...", "0", "--")

            with py7zr.SevenZipFile(archive_path, mode='r') as z:
                z.extractall(path=save_dir)
                # 找解压出来的 .img 文件
                img_files = list(save_dir.glob("*.img"))
                if img_files:
                    # 选最大的
                    largest = max(img_files, key=lambda p: p.stat().st_size)
                    if progress_callback:
                        progress_callback(100, "解压完成", "0", "0")
                    return True, str(largest)

            return False, "7z 解压完成但找不到 .img 文件"

        elif lower.endswith(".img"):
            # 已经是 img 了
            return True, str(archive_path)

        else:
            return False, f"不支持的压缩格式: {file_name}"

    except Exception as e:
        return False, f"解压失败: {e}"
