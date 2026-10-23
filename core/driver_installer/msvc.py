"""绿色 MSVC 工具链部署（无需 VS 安装器）。

流程：官方 CDN 解析清单 -> 按需下载 -> 原地解包 -> 落盘 -> 注册表登记。
不写系统目录、不调用 vs_BuildTools.exe、不改动已有 VS 安装。

落盘布局刻意对齐真实 VS 安装，使 setuptools 的 _find_vc2015 能直接命中：
    <ROOT>\\VC\\Tools\\MSVC\\<ver>\\bin\\Hostx64\\x64\\cl.exe
    <ROOT>\\VC\\Auxiliary\\Build\\vcvarsall.bat      <- 本模块自写
    <ROOT>\\Windows Kits\\10\\Include\\<sdkver>\\...
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CHANNEL_URL = "https://aka.ms/vs/17/release/channel"
MANIFEST_ID = "Microsoft.VisualStudio.Manifests.VisualStudio"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

ROOT = r"C:\MSVC"
WORK_DIR = r"C:\MSVC\_work"
VS7_KEY = r"HKLM\Software\Microsoft\VisualStudio\SxS\VC7"
VS7_VALUE = "14.0"

COMPONENTS = (
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
    "Microsoft.VisualStudio.Component.Windows11SDK.26100",
)

# 链接期必备库。曾因裁剪掉 CRT.Store 包导致它们缺失，
# 表现为 LNK1104: cannot open file 'OLDNAMES.lib'，故纳入健康检查。
REQUIRED_LIBS = (
    ("lib", "x64", "oldnames.lib"),
    ("lib", "x64", "msvcrt.lib"),
    ("lib", "x86", "oldnames.lib"),
    ("lib", "x86", "msvcrt.lib"),
)

DOWNLOAD_THREADS = 8
DL_ROUNDS = 5            # 整批重试轮数：扛 DNS/网络瞬时故障（getaddrinfo failed）
DL_FILE_ATTEMPTS = 3     # 单个文件在一轮内的尝试次数

EXCLUDE_PAYLOADS = ("vc_redist.x64.exe", "vc_redist.x86.exe", "vc_redist.arm64.exe")

# 各阶段占整体进度的区间。下载占大头，解包分掉其余部分，
# 保证进度条单调递增——早期版本下载到 100% 后又被解包打回 50%。
PHASE_DOWNLOAD = (0.00, 0.70)
PHASE_VSIX = (0.70, 0.85)
PHASE_MSI = (0.85, 1.00)


def _mb(n):
    return n / 1048576.0


def _scale(phase, frac):
    lo, hi = phase
    frac = max(0.0, min(frac, 1.0))
    return lo + frac * (hi - lo)


class MsvcError(RuntimeError):
    pass


def _request(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)


def _get_json(url, timeout=60):
    with _request(url, timeout) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def resolve_manifest_url():
    """从官方 channel 清单里拿到 vsman 主清单地址。"""
    channel = _get_json(CHANNEL_URL)
    for item in channel.get("channelItems", []):
        if item.get("id") == MANIFEST_ID:
            payloads = item.get("payloads") or []
            if payloads and payloads[0].get("url"):
                return payloads[0]["url"]
    raise MsvcError("官方 channel 清单里没有找到 " + MANIFEST_ID)


def _closure(packages, roots):
    """展开依赖闭包。dependencies 是 {包id: 版本范围} 字典，不是数组。"""
    index = {}
    for pkg in packages:
        index.setdefault(pkg["id"], pkg)

    seen, stack = set(), list(roots)
    while stack:
        pkg_id = stack.pop()
        if pkg_id in seen:
            continue
        seen.add(pkg_id)
        pkg = index.get(pkg_id)
        if not pkg:
            continue
        deps = pkg.get("dependencies")
        if isinstance(deps, dict):
            stack.extend(deps.keys())
    return seen, index


def _payload_path(pkg_id, file_name):
    """落盘相对路径：<包id>/<fileName>。

    不能直接用 fileName——清单里多个不同的包会共用同一个名字
    （例如多个包的文件名都叫 payload.vsix），直接落盘会互相覆盖，
    并发下载时表现为 WinError 32「另一个程序正在使用此文件」。
    """
    safe_pkg = re.sub(r"[^A-Za-z0-9._-]", "_", pkg_id)
    return "%s/%s" % (safe_pkg, file_name.replace("\\", "/"))


def collect_payloads(manifests):
    """汇总所有需要下载的 payload，用包 id 隔离，保留 fileName 里的相对子目录。"""
    seen, index = _closure(manifests.get("packages", []), COMPONENTS)
    items = []
    used = set()
    for pkg_id in seen:
        pkg = index.get(pkg_id)
        if not pkg:
            continue
        for payload in pkg.get("payloads") or []:
            url = payload.get("url")
            name = payload.get("fileName") or ""
            if not url or not name:
                continue
            if os.path.basename(name.replace("\\", "/")).lower() in EXCLUDE_PAYLOADS:
                continue
            rel = _payload_path(pkg_id, name)
            if rel in used:
                continue
            used.add(rel)
            items.append({
                "file": rel,
                "url": url,
                "size": int(payload.get("size") or 0),
            })
    return items


def _safe_join(base, relative):
    target = os.path.normpath(os.path.join(base, relative))
    base_norm = os.path.normpath(base)
    if not target.startswith(base_norm + os.sep):
        raise MsvcError("清单里的路径越界: " + relative)
    return target


def download_all(items, dest, log, progress):
    """并发下载，按 MB 上报进度，并做整批重试以扛住 DNS/网络抖动。

    进度按「已完成文件字节 + 在途字节」统计，重试不会重复计数，进度条也不倒退。
    """
    os.makedirs(dest, exist_ok=True)
    total = sum(x["size"] for x in items) or 1
    state = {"done": 0, "pct": -1}
    inflight = {}
    lock = threading.Lock()

    def report():
        with lock:
            cur = min(state["done"] + sum(inflight.values()), total)
            pct = int(cur * 100 / total)
            if pct == state["pct"]:
                return
            state["pct"] = pct
        progress(_scale(PHASE_DOWNLOAD, cur / total),
                 "下载 %.1f / %.1f MB" % (_mb(cur), _mb(total)))

    def settle(item):
        with lock:
            inflight.pop(item["file"], None)
            state["done"] += item["size"]
        report()

    def fetch(item):
        path = _safe_join(dest, item["file"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if item["size"] and os.path.isfile(path) and os.path.getsize(path) == item["size"]:
            settle(item)
            return
        tmp = path + ".part"
        for attempt in range(DL_FILE_ATTEMPTS):
            try:
                with _request(item["url"], timeout=120) as resp, open(tmp, "wb") as fh:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                        with lock:
                            inflight[item["file"]] = fh.tell()
                        report()
                break
            except Exception:
                with lock:
                    inflight.pop(item["file"], None)
                report()
                if attempt == DL_FILE_ATTEMPTS - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        for _ in range(5):
            try:
                os.replace(tmp, path)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise MsvcError("无法落盘（文件被占用）: " + path)
        settle(item)

    remaining = list(items)
    for round_no in range(1, DL_ROUNDS + 1):
        failed = []
        with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as pool:
            futures = {pool.submit(fetch, x): x for x in remaining}
            for fut in as_completed(futures):
                item = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    failed.append((item, e))
        if not failed:
            break
        if round_no < DL_ROUNDS:
            wait = 6 * round_no
            log("本轮 %d 个文件失败（网络/DNS 抖动），%d 秒后重试（第 %d/%d 轮）"
                % (len(failed), wait, round_no + 1, DL_ROUNDS))
            time.sleep(wait)
            remaining = [i for i, _ in failed]
            continue
        raise MsvcError(
            "下载失败：%d 个文件重试 %d 轮后仍失败，首个错误：%s。"
            "已完成 %.1f / %.1f MB，直接重跑会从断点继续（勿删 %s）"
            % (len(failed), DL_ROUNDS, failed[0][1],
               _mb(state["done"]), _mb(total), WORK_DIR))

    progress(_scale(PHASE_DOWNLOAD, 1.0),
             "下载 %.1f / %.1f MB" % (_mb(total), _mb(total)))
    log("组件下载完成，共 %d 个文件 / %.1f MB" % (len(items), _mb(total)))


def extract_vsix(path, root, log):
    """VSIX 即 zip，Contents/ 下的路径直接映射到安装根目录。"""
    import zipfile
    count = 0
    with zipfile.ZipFile(path) as zf:
        for member in zf.namelist():
            if not member.startswith("Contents/"):
                continue
            relative = member[len("Contents/"):]
            if not relative or member.endswith("/"):
                continue
            out = _safe_join(root, relative)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with zf.open(member) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def extract_msi(path, root, msi_log, log):
    """管理安装（/a）= 只解包不注册，产物直接落在 TARGETDIR 下。

    /l 的标志组与日志路径必须是两个独立参数。粘成一个 token 时，
    msiexec 会把日志路径的首字符当成非法标志，从而调用 /help 弹出用法
    对话框；该判定发生在 /qn 生效之前，静默参数压不住，且每调一次弹一个。
    """
    cmd = [
        "msiexec", "/a", path, "/qn", "/norestart",
        "TARGETDIR=" + root, "REBOOT=ReallySuppress",
        "/l*v+", msi_log,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise MsvcError("解包超时: " + os.path.basename(path))
    if proc.returncode != 0:
        raw = (proc.stdout or b"") + (proc.stderr or b"")
        text = " ".join(raw.decode("mbcs", "replace").split())
        if "msiexec /Option" in text or "Installer. V " in text:
            log("!! msiexec 判定命令行非法并弹出用法说明（%s）"
                % os.path.basename(path))
        elif text:
            log("msiexec 返回码 %d（%s）输出: %s"
                % (proc.returncode, os.path.basename(path), text[:300]))
        else:
            log("msiexec 返回码 %d（%s）无输出"
                % (proc.returncode, os.path.basename(path)))
    return proc.returncode


def _detect_versions(root):
    msvc_ver = None
    tools = os.path.join(root, "VC", "Tools", "MSVC")
    if os.path.isdir(tools):
        cands = [d for d in os.listdir(tools) if d.startswith("14.")]
        if cands:
            msvc_ver = sorted(cands)[-1]

    sdk_ver = None
    inc = os.path.join(root, "Windows Kits", "10", "Include")
    if os.path.isdir(inc):
        cands = [d for d in os.listdir(inc) if re.match(r"^10\.\d", d)]
        if cands:
            sdk_ver = sorted(cands)[-1]
    return msvc_ver, sdk_ver


VCVARS_TEMPLATE = r"""@echo off
set "VCROOT={root}\VC"
set "VCTOOLS=%VCROOT%\Tools\MSVC\{msvc}"
set "SDKROOT={root}\Windows Kits\10"
set "SDKVER={sdk}"

set "TGT=x86"
set "HOSTDIR=Hostx86\x86"
if /i "%~1"=="x86_amd64" (
  set "TGT=x64"
  set "HOSTDIR=Hostx64\x64"
)
if /i "%~1"=="x64" (
  set "TGT=x64"
  set "HOSTDIR=Hostx64\x64"
)
if /i "%~1"=="amd64" (
  set "TGT=x64"
  set "HOSTDIR=Hostx64\x64"
)

set "PATH=%VCTOOLS%\bin\%HOSTDIR%;%SDKROOT%\bin\%SDKVER%\%TGT%;%PATH%"
set "INCLUDE=%VCTOOLS%\include;%SDKROOT%\Include\%SDKVER%\ucrt;%SDKROOT%\Include\%SDKVER%\um;%SDKROOT%\Include\%SDKVER%\shared;%SDKROOT%\Include\%SDKVER%\winrt;%INCLUDE%"
set "LIB=%VCTOOLS%\lib\%TGT%;%SDKROOT%\Lib\%SDKVER%\ucrt\%TGT%;%SDKROOT%\Lib\%SDKVER%\um\%TGT%;%LIB%"
set "VCINSTALLDIR=%VCROOT%"
set "VCToolsInstallDir=%VCTOOLS%"
set "WindowsSdkDir=%SDKROOT%"
set "UniversalCRTSdkDir=%SDKROOT%"
set "UCRTVersion=%SDKVER%"
set "VSCMD_ARG_TGT_ARCH=%TGT%"
"""


def write_vcvarsall(root, msvc_ver, sdk_ver, log):
    """vcvarsall.bat 不能带 setlocal，否则环境变量无法传回 setuptools 的 cmd。"""
    target = os.path.join(root, "VC", "Auxiliary", "Build")
    os.makedirs(target, exist_ok=True)
    body = VCVARS_TEMPLATE.format(root=root, msvc=msvc_ver, sdk=sdk_ver)
    path = os.path.join(target, "vcvarsall.bat")
    with open(path, "w", encoding="mbcs", newline="\r\n") as fh:
        fh.write(body)
    log("已生成 vcvarsall.bat -> " + path)
    return path


def register(root, log):
    """写 SxS\\VC7，值名必须是能被 int(float()) 解析且 >= 14 的版本号。"""
    cmd = [
        "reg", "add", VS7_KEY, "/v", VS7_VALUE, "/t", "REG_SZ",
        "/d", os.path.join(root, "VC", "Auxiliary", "Build"), "/f", "/reg:32",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise MsvcError("注册表写入失败: " + proc.stderr.decode("mbcs", "replace"))
    log("注册表已登记: %s\\%s" % (VS7_KEY, VS7_VALUE))


def unregister(log):
    subprocess.run(["reg", "delete", VS7_KEY, "/v", VS7_VALUE, "/f", "/reg:32"],
                   capture_output=True)
    log("注册表登记已移除")


def is_installed():
    """四项齐备才算已装：cl.exe、链接期库、vcvarsall.bat、注册表值。

    只查 cl.exe 是不够的——曾出现过"编译能过、链接必挂"的残缺安装，
    所以把 oldnames/msvcrt 这类链接期库也纳入判定，残缺时会自动重装。
    """
    msvc_ver, sdk_ver = _detect_versions(ROOT)
    if not msvc_ver or not sdk_ver:
        return False
    tools = os.path.join(ROOT, "VC", "Tools", "MSVC", msvc_ver)
    if not os.path.isfile(os.path.join(tools, "bin", "Hostx64", "x64", "cl.exe")):
        return False
    for rel in REQUIRED_LIBS:
        if not os.path.isfile(os.path.join(tools, *rel)):
            return False
    if not os.path.isfile(os.path.join(ROOT, "VC", "Auxiliary", "Build", "vcvarsall.bat")):
        return False
    proc = subprocess.run(
        ["reg", "query", VS7_KEY, "/v", VS7_VALUE, "/reg:32"],
        capture_output=True)
    return proc.returncode == 0


def install(log, progress):
    """完整安装流程，返回 cl.exe 路径。"""
    log("解析微软官方清单 ...")
    manifest_url = resolve_manifest_url()
    log("主清单: " + os.path.basename(manifest_url))
    manifests = _get_json(manifest_url, timeout=300)

    items = collect_payloads(manifests)
    total_mb = sum(x["size"] for x in items) / 1024 / 1024
    log("已解析依赖闭包：%d 个待下载文件 / %.1f MB" % (len(items), total_mb))

    os.makedirs(ROOT, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)
    download_all(items, WORK_DIR, log, progress)

    vsix = [x for x in items if x["file"].lower().endswith(".vsix")]
    msi = [x for x in items if x["file"].lower().endswith(".msi")]
    log("解包 VSIX %d 个 -> %s" % (len(vsix), ROOT))
    vsix_total = sum(x["size"] for x in vsix) or 1
    done = 0
    for item in vsix:
        extract_vsix(_safe_join(WORK_DIR, item["file"]), ROOT, log)
        done += item["size"]
        progress(_scale(PHASE_VSIX, done / vsix_total),
                 "解包工具集 %.1f / %.1f MB" % (_mb(done), _mb(vsix_total)))

    msi_log = os.path.join(WORK_DIR, "msi_install.log")
    log("管理安装 MSI %d 个（只解包不注册）..." % len(msi))
    msi_total = sum(x["size"] for x in msi) or 1
    done = 0
    failed = []
    streak = 0
    for item in msi:
        rc = extract_msi(_safe_join(WORK_DIR, item["file"]), ROOT, msi_log, log)
        done += item["size"]
        if rc != 0:
            failed.append((os.path.basename(item["file"]), rc))
            streak += 1
            if streak >= 3:
                raise MsvcError(
                    "连续 %d 个 MSI 解包失败，已中止以免成批弹窗；"
                    "请把上方 msiexec 的输出发我" % streak)
        else:
            streak = 0
        progress(_scale(PHASE_MSI, done / msi_total),
                 "管理安装 SDK %.1f / %.1f MB" % (_mb(done), _mb(msi_total)))
    if failed:
        log("有 %d 个 MSI 返回非零（通常可忽略）" % len(failed))
        for name, rc in failed[:5]:
            log("  - %s -> %d" % (name, rc))

    msvc_ver, sdk_ver = _detect_versions(ROOT)
    if not msvc_ver:
        raise MsvcError("未找到 MSVC 工具集目录，解包可能失败")
    if not sdk_ver:
        raise MsvcError("未找到 Windows SDK 目录，解包可能失败")
    log("检测到 MSVC 工具集 %s / SDK %s" % (msvc_ver, sdk_ver))

    write_vcvarsall(ROOT, msvc_ver, sdk_ver, log)
    register(ROOT, log)

    progress(1.0, "MSVC 工具链就绪")
    return os.path.join(ROOT, "VC", "Tools", "MSVC", msvc_ver, "bin", "Hostx64", "x64", "cl.exe")


def cleanup(log):
    if os.path.isdir(WORK_DIR):
        shutil.rmtree(WORK_DIR, ignore_errors=True)
        log("已清理下载缓存 " + WORK_DIR)


def uninstall(log):
    unregister(log)
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT, ignore_errors=True)
        log("已删除 " + ROOT)


if __name__ == "__main__":
    def _p(frac, text):
        print("[%5.1f%%] %s" % (frac * 100, text))

    install(print, _p)
