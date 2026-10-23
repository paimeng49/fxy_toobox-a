"""安装引擎

职责：
  - 按清单顺序执行各安装项（注册表 / INF驱动 / OPLUS / UsbDk / Python）
  - 每项优先使用官方静默参数，同时启动 ClickBot 兜底处理弹窗
  - 完成后做真实校验（注册表 / pnputil 枚举 / 文件存在）
  - 失败自动重试 1 次，超时强制结束进程树
  - 所有进度通过 log_queue 上报给 UI
"""

import os
import queue
import subprocess
import time

from config import settings

from . import msvc
from .automator import spawn

# ------------------------------------------------------------------ 路径
def get_deps_dir() -> str:
    """返回工具箱外置的「支持库及驱动」目录（tools/支持库及驱动）。

    与独立安装器不同：工具箱的 tools 目录外置，不打进 _MEIPASS，
    因此直接使用 settings.DEPS_DIR。
    """
    return str(settings.DEPS_DIR)

# 静默参数模板（各自官方参数）
INNO_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
MSI_ARGS = ["/qn", "/norestart"]
PYTHON_ARGS = ["/quiet", "InstallAllUsers=1", "PrependPath=1",
               "Include_test=0", "Include_launcher=1"]
DPINST_ARGS = ["/SA", "/Q", "/EL"]

# 驱动 INF 清单（暂以现有资源为准）
INF_LIST = [
    "Drivers\\sprdadb.inf",
    "Drivers\\sprdvcom.inf",
    "Drivers\\sprdvmdm.inf",
    "Drivers\\rdavcom.inf",
]

# 每项超时(秒)
TIMEOUT = {
    "reg": 60, "pnp": 300, "dpinst": 300, "inno": 600, "msi": 300, "python": 900,
    "msvc": 5400,
}


# ------------------------------------------------------------------ 校验器
def _run_capture(args, timeout=30):
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def _reg_query(key, value=None):
    cmd = ["reg", "query", key]
    if value:
        cmd.append("/v")
        cmd.append(value)
    rc, out = _run_capture(cmd)
    return rc == 0 and "找不到" not in out


def _file_exists(*parts):
    return os.path.isfile(os.path.join(*parts) if len(parts) > 1 else parts[0])


def _pnputil_has_inf(inf_name):
    rc, out = _run_capture(["pnputil", "/enum-drivers"], timeout=60)
    if rc != 0:
        return None  # 无法判断
    return inf_name in out


def _vs_installed() -> bool:
    """检测 VS BuildTools 是否已装有 MSVC x64/x86 生成工具（>= 一个 VC 工具集）。"""
    vswhere = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if not os.path.isfile(vswhere):
        return False
    rc, out = _run_capture(
        [vswhere, "-latest", "-products", "*",
         "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
         "-property", "installationPath"], timeout=30)
    return rc == 0 and bool(out.strip())


def _msvc_ready():
    """绿色 MSVC 已就绪，或目标机已有真实 VS 的 MSVC 组件，都算已装。"""
    if msvc.is_installed():
        return True
    return _vs_installed()


def _oplus_installed():
    """检测 OPLUS 全家桶是否已装（Google ADB 驱动 android_winusb.inf 属于其内容）。"""
    rc, out = _run_capture(["pnputil", "/enum-drivers"], timeout=60)
    if rc != 0:
        return None
    return "android_winusb.inf" in out or "qusb" in out.lower()


def _verify(kind, payload):
    """按任务类型执行真实校验，返回 (ok, 说明)。"""
    try:
        if kind == "reg":
            ok = _reg_query(payload["key"], payload.get("value"))
            return ok, ("注册表项写入成功" if ok else "注册表项校验未通过")
        if kind == "pnp":
            ok = _pnputil_has_inf(payload)
            return (ok, f"驱动 {payload} 已列入驱动存储")
        if kind == "file":
            return _file_exists(payload), f"{payload} 存在"
        if kind == "python":
            ok = _file_exists(r"C:\Program Files\Python314\python.exe")
            return ok, "Python 已安装到 C:\\Program Files\\Python314"
        if kind == "msi":
            ok = _pnputil_has_inf("usbdk") or _file_exists(
                r"C:\Windows\System32\drivers\usbdk.sys")
            return ok, "UsbDk 驱动文件已部署"
        if kind == "msvc":
            ok = msvc.is_installed()
            return ok, "绿色 MSVC 工具链已就绪" if ok else "未检测到可用的 MSVC 工具链"
    except Exception as e:
        return False, f"校验异常: {e}"
    return True, "安装器返回成功"


# ------------------------------------------------------------------ 任务
class Task:
    def __init__(self, kind, name, file=None, args=None, verify_payload=None,
                 cwd=None, timeout=None, precheck=None):
        self.kind = kind        # reg | pnp | dpinst | inno | msi | python | vs
        self.name = name        # 显示名称
        self.file = file        # 资源内绝对路径
        self.args = args or []
        self.verify_payload = verify_payload
        self.cwd = cwd
        self.timeout = timeout or TIMEOUT.get(kind, 300)
        self.precheck = precheck  # 可调用() -> bool|None；True=已装跳过

    @property
    def cmdline(self):
        """构造最终命令行（列表形式）。"""
        if self.kind == "reg":
            return ["reg", "import", self.file]
        if self.kind == "pnp":
            return ["pnputil", "/add-driver", self.file, "/install"]
        if self.kind == "msi":
            return ["msiexec", "/i", self.file] + MSI_ARGS
        if self.kind == "msvc":
            return ["(内置绿色 MSVC 部署：官方 CDN 拉取 + 解包 + 注册)"]
        if self.kind in ("inno", "python", "dpinst"):
            return [self.file] + self.args
        return [self.file]


def build_tasks(deps_dir: str = None) -> list:
    """按顺序构造全部安装任务清单。"""
    deps = deps_dir or get_deps_dir()
    tasks = []
    # 1) 注册表 USB 序列号忽略项
    tasks.append(Task("reg", "写入 USB 识别配置 (config.reg)",
                      file=os.path.join(deps, "config.reg"),
                      verify_payload={"key": r"HKLM\SYSTEM\CurrentControlSet\Control\UsbFlags",
                                      "value": "IgnoreHWSerNum17824026"}))
    # 2) 展锐 + 瑞芯微 INF 驱动（逐个 pnputil 静默安装；已入库则跳过）
    for inf in INF_LIST:
        tasks.append(Task("pnp", f"安装驱动: {inf}",
                          file=os.path.join(deps, inf),
                          verify_payload=os.path.basename(inf),
                          precheck=lambda b=os.path.basename(inf): _pnputil_has_inf(b)))
    # 3) OPLUS ADB/Fastboot/高通/联发科 全家桶（Inno，静默 + watchdog）
    tasks.append(Task("inno", "OPLUS ADB/Fastboot/高通/联发科 驱动全家桶",
                      file=os.path.join(deps, "OPLUS ADB Fastboot 高通 联发科 驱动4.0.1.6-2025.1.10无需重启电脑.exe"),
                      args=INNO_ARGS.copy(),
                      precheck=_oplus_installed))
    # 4) UsbDk 虚拟 USB 驱动
    tasks.append(Task("msi", "UsbDk 虚拟 USB 驱动",
                      file=os.path.join(deps, "UsbDk驱动.msi"),
                      verify_payload=None,
                      precheck=lambda: _file_exists(
                          r"C:\Windows\System32\drivers\usbdk.sys")))
    # 5) Python 3.14 运行环境
    tasks.append(Task("python", "Python 3.14 运行环境",
                      file=os.path.join(deps, "python-3.14.7-amd64.exe"),
                      args=PYTHON_ARGS.copy(),
                      verify_payload=None,
                      precheck=lambda: _file_exists(
                          r"C:\Program Files\Python314\python.exe")))
    # 6) Microsoft Visual C++ 生成工具（绿色部署，最后；只装 MSVC x64/x86 + Win11 SDK 26100）
    tasks.append(Task(
        "msvc", "Microsoft Visual C++ 生成工具 (绿色 MSVC)",
        verify_payload=None,
        precheck=_msvc_ready))
    return tasks


# ------------------------------------------------------------------ 引擎
class InstallEngine:
    def __init__(self, log_queue: "queue.Queue", res_root: str | None = None):
        self.log = log_queue
        self.res_root = res_root or get_deps_dir()
        self._tasks: list[tuple[Task, str]] = []   # (task, state)

    def _emit(self, msg):
        self.log.put(msg)

    def _kill_tree(self, pid):
        import psutil
        try:
            p = psutil.Process(pid)
            for c in p.children(recursive=True):
                try:
                    c.kill()
                except Exception:
                    pass
            p.kill()
        except Exception:
            pass

    def run(self, tasks: list, dry_run: bool = False, extra_pause: float = 0.0):
        """顺序执行任务清单；dry_run=True 只规划不执行。返回汇总。"""
        summary = []
        total = len(tasks)
        for i, t in enumerate(tasks, 1):
            tag = f"[{i}/{total}]"
            self._emit(("status", t.name, "running"))
            self._emit(("log", f"{tag} 开始：{t.name}"))

            if dry_run:
                self._emit(("log", f"{tag} [预演] 命令：{' '.join(t.cmdline)}"))
                self._emit(("status", t.name, "ok"))
                summary.append((t.name, "ok", "预演通过"))
                if extra_pause:
                    time.sleep(extra_pause)
                continue

            # 环境检测：目标环境已安装则跳过，不再重复安装
            if t.precheck is not None:
                try:
                    if t.precheck():
                        self._emit(("status", t.name, "ok"))
                        self._emit(("log", f"{tag} ⏭ 检测到已安装，跳过：{t.name}"))
                        summary.append((t.name, "ok", "已安装，跳过"))
                        continue
                except Exception:
                    pass

            if t.kind == "msvc":
                ok, detail = self._execute_msvc(t)
            else:
                ok, detail = self._execute_one(t)
            st = "ok" if ok else "fail"
            self._emit(("status", t.name, st))
            self._emit(("log", f"{tag} {'✅ 成功' if ok else '❌ 失败'}：{detail}"))
            summary.append((t.name, st, detail))
        self._emit(("done", summary))
        return summary

    def _execute_one(self, t: Task):
        """执行单个任务：静默参数启动 + ClickBot 兜底 + 超时 + 校验。"""
        cmd = t.cmdline
        detail = "未知错误"
        for attempt in (1, 2):  # 失败自动重试一次
            proc = None
            bot = None
            try:
                proc = subprocess.Popen(
                    cmd, cwd=t.cwd or self.res_root,
                    creationflags=0x00000008,  # DETACHED_PROCESS 不占用控制台
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # 启动 UI 自动化兜底
                bot = spawn(proc.pid, self.log)
                rc = proc.wait(timeout=t.timeout)
                if bot:
                    bot.stop()
                if rc == 0:
                    # 校验真实安装效果
                    ok, vd = _verify(t.kind, t.verify_payload)
                    if ok:
                        return True, vd
                    detail = f"返回码0但校验未通过: {vd}"
                else:
                    detail = f"安装器返回码 {rc}"
                    # 常见可恢复场景：Inno 检测到旧版提示重启/任务占用
            except subprocess.TimeoutExpired:
                detail = f"超时 {t.timeout}s，已强制结束"
                self._kill_tree(proc.pid if proc else 0)
            finally:
                if bot:
                    bot.stop()
            self._emit(("log", f"  第{attempt}次尝试失败：{detail}，重试..."))
            time.sleep(2)
        return False, detail

    def _execute_msvc(self, t: Task):
        """绿色 MSVC 没有命令行，直接调用内置部署模块并转发进度。

        这一步会大量调用 msiexec，而这些子进程挂在当前进程树下，所以这里
        也挂上 ClickBot：一旦冒出意外弹窗（例如 msiexec 的用法对话框）会被
        自动点掉，不会再像以前那样堆满桌面且关不掉。
        """
        gate = {"pct": -5}
        bot = None

        def emit_log(msg):
            self._emit(("log", "    " + str(msg)))

        def emit_progress(frac, text):
            self._emit(("sub", t.name, frac, text))
            pct = int(frac * 100)
            if pct >= gate["pct"] + 5 or pct >= 100:
                gate["pct"] = pct
                self._emit(("log", "    %s（%d%%）" % (text, pct)))

        try:
            bot = spawn(os.getpid(), self.log)
            cl = msvc.install(emit_log, emit_progress)
        except Exception as e:
            return False, "绿色 MSVC 部署失败: %s" % e
        finally:
            if bot:
                bot.stop()
        if not msvc.is_installed():
            return False, "部署流程结束但校验未通过"
        msvc.cleanup(emit_log)
        return True, "绿色 MSVC 已就绪，cl.exe 位于 " + cl