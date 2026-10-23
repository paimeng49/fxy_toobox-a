"""UI 全自动点击引擎

职责：监控安装器进程树产生的所有窗口，自动点掉向导/协议/重启类弹窗，
     使用户全程无需手动点击。配合静默参数实现完全无人值守。

策略：
  1. 优先静默参数（core.py 负责），本引擎只负责"意外弹窗"兜底
  2. 每隔 0.3s 枚举目标进程树的所有可见窗口
  3. 按按钮词库匹配并点击（中英文 + 快捷键符号 &X）
  4. 匹配不到按钮时回退"默认按钮 + 回车"（模拟用户按 Enter）
  5. 同窗口同按钮 8s 内去重，避免死循环连点
  6. 只点击安全按钮，绝不在安装中途点"取消/否"
"""

import ctypes
import queue
import threading
import time
from ctypes import wintypes

try:
    import psutil
except ImportError:      # 工具箱未装 psutil 时，自动化兜底降级为不扫描
    psutil = None

# ------------------------------------------------------------------ Win32 API
user32 = ctypes.windll.user32

_EnumWndProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.SendMessageW.restype = wintypes.LPARAM
user32.SetForegroundWindow.restype = wintypes.BOOL

ENUM_PROC = _EnumWndProc(lambda h, _: (None))  # 实际在函数内重新构造
BM_CLICK = 0x00F5

# 无点击时也定期上报一次存活状态，避免日志长时间空白看着像卡死
HEARTBEAT_INTERVAL = 30.0

# ------------------------------------------------------------------ 按钮词库
# 每类: (匹配关键字元组, 动作名, 说明)。顺序=优先级。
# 关键字的写法兼容"下一步(N)"、"Next >"、"&同意" 等常见画法（匹配时去 & 全小写）
BUTTON_RULES = [
    # 1) 收尾/不重启（最优先，避免误触发重启耽误用户使用）
    (("稍后", "以后", "稍候重启", "不重启", "restart later", "reboot later",
      "will restart later", "later", "not now", "no, i will restart later"),
     "close", "重启推迟/收尾"),
    (("完成", "finish", "close", "退出", "exit", "关闭"), "ok", "完成/关闭"),
    # 2) 协议与许可
    (("我接受", "我同意", "同意", "接受", "同意并继续", "接受许可", "i accept",
      "i agree", "agree", "accept", "agree and continue", "accept license",
      "aceptar", "accepter"), "agree", "接受协议"),
    # 3) 流程推进
    (("下一步", "继续", "next", "continue", "weiter", "siguiente", "suivant",
      "next >"), "next", "向导下一步"),
    (("立即安装", "开始安装", "开始", "安装", "install", "install now", "更新",
      "升级", "upgrade", "update", "重新安装", "reinstall"), "install", "开始安装"),
    (("确定", "好", "ok", "yes", "是", "&ok"), "ok", "确定/确认"),
]

# 绝不自动点击的按钮（避免误操作/中断安装）
FORBIDDEN_BUTTONS = (
    "取消", "cancel", "abort", "否", "no", "skip", "跳过", "关闭程序",
    "不要安装", "don't install", "不安装",
)

# 含这些词的窗口标题无需处理
IGNORE_TITLE_KEYWORDS = ["输入法", "悬停", "通知", "volume", "音量", "explorer"]

# 含这些词的标题提示"装完提示重启"——优先点"稍后"
RESTART_TITLE_KEYWORDS = ("重启", "重新启动", "restart", "reboot", "installation complete")

# 需要无条件忽略的窗口句柄（例如本程序自己的界面），由调用方登记
IGNORED_HWNDS = set()


def ignore_window(hwnd) -> None:
    """登记一个永不点击的窗口句柄。

    用于把本程序自身的界面排除在外：它同样带有"退出/安装"这类按钮，
    若不排除就会被点中，导致安装中途把自己关掉。
    """
    try:
        IGNORED_HWNDS.add(int(hwnd))
    except (TypeError, ValueError):
        pass


def ignore_title(keyword: str) -> None:
    """登记一个永不点击的窗口标题关键字（同样用于排除本程序界面）。"""
    if keyword and keyword not in IGNORE_TITLE_KEYWORDS:
        IGNORE_TITLE_KEYWORDS.append(keyword)


def _norm(text: str) -> str:
    """规范化按钮文本：去 & 快捷键符号、转小写、去空白。"""
    return text.replace("&", " ").strip().lower().replace(" ", "")


class ClickBot:
    """监视某个 pid 的进程树，自动点击其窗口中的按钮。"""

    def __init__(self, pid: int, log_queue: "queue.Queue"):
        self.pid = pid
        self.log = log_queue
        self._stop = threading.Event()
        self._clicked: dict[tuple, float] = {}    # (hwnd, 规范化文本) -> 时间
        self._window_seen: dict[int, float] = {}  # hwnd -> 时间
        self.click_count = 0
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ClickBot")

    # -------------------------------------------------------------- 对外接口
    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _info(self, msg: str):
        self.log.put(("log", f"🖱 {msg}"))

    # -------------------------------------------------------------- 主循环
    def _run(self):
        self._info(f"自动化监控已启动 (pid={self.pid})")
        last_beat = time.time()
        while not self._stop.is_set():
            try:
                self._scan_once()
            except Exception as e:
                self.log.put(("debug", f"[bot] {e}"))
            now = time.time()
            if now - last_beat >= HEARTBEAT_INTERVAL:
                last_beat = now
                self._info("扫描中：目标窗口 %d 个，累计点击 %d 次"
                           % (len(self._window_seen), self.click_count))
            self._stop.wait(0.3)
        self._info(f"自动化监控已结束：累计点击 {self.click_count} 次")

    # -------------------------------------------------------------- 扫描
    def _scan_once(self):
        pids = self._process_tree(self.pid)
        if not pids:
            return
        for hwnd in self._enum_windows():
            if self._stop.is_set():
                return
            if not user32.IsWindowVisible(hwnd):
                continue
            if hwnd in IGNORED_HWNDS:
                continue
            if self._window_pid(hwnd) not in pids:
                continue
            title = self._window_title(hwnd)
            if not title:
                continue
            if any(k.lower() in title.lower() for k in IGNORE_TITLE_KEYWORDS):
                continue
            try:
                self._handle_window(hwnd, title, self._window_class(hwnd))
            except Exception as e:
                self.log.put(("debug", f"[bot!{title[:20]}] {e}"))

    # -------------------------------------------------------------- 单窗口处理
    def _handle_window(self, hwnd, title, cls):
        now = time.time()
        if now - self._window_seen.get(hwnd, 0) < 1.5:
            return
        first_seen = hwnd not in self._window_seen
        self._window_seen[hwnd] = now
        if first_seen:
            self._info(f"发现窗口「{title[:40]}」class={cls or '?'}")

        buttons = self._get_buttons(hwnd)
        if not buttons:
            self._press_enter_fallback(hwnd, title, cls)
            return
        if first_seen:
            self._info("[%s] 枚举到 %d 个按钮: %s"
                       % (title[:26], len(buttons),
                          " / ".join(t for _, t in buttons[:6])))

        target = self._pick_button(buttons, title)
        if target is None:
            label = " / ".join(t for _, t in buttons[:5])
            if label:
                self._info(f"[{title[:26]}] 无可点按钮（已跳过，不误点）: {label}")
            return

        ctrl, text = target
        key = (hwnd, _norm(text))
        if now - self._clicked.get(key, 0) < 8:
            return  # 防连点
        self._clicked[key] = now
        ok = click_button(ctrl)
        if ok:
            self.click_count += 1
            self._info(f"[{title[:26]}] 自动点击「{text}」成功（第 {self.click_count} 次）")
        else:
            self._info(f"[{title[:26]}] 点击「{text}」失败，将重试")

    # -------------------------------------------------------------- 匹配
    def _pick_button(self, buttons, title):
        """按词库挑一个应点击的按钮；返回 (ctrl, text) 或 None。"""
        title_n = _norm(title)
        want_restart_skip = any(k in title_n for k in
                                (_norm(x) for x in RESTART_TITLE_KEYWORDS))
        candidates = []
        for rule_texts, action, _desc in BUTTON_RULES:
            for ctrl, text in buttons:
                t = _norm(text)
                if t in FORBIDDEN_BUTTONS:
                    continue
                if any(x in t for x in (_norm(k) for k in rule_texts)):
                    candidates.append((action, ctrl, text, t))
                    break
            if candidates:
                break
        if not candidates:
            return None
        # 若标题提示"需要重启/完成"，优先返回 close/ok 类动作
        if want_restart_skip:
            for action, ctrl, text, t in candidates:
                if action in ("close", "ok"):
                    return ctrl, text
        action, ctrl, text, t = candidates[0]
        return ctrl, text

    # -------------------------------------------------------------- 按钮枚举
    def _get_buttons(self, hwnd):
        """枚举窗口内按钮控件，返回 [(pywinauto控件, 文本)]，去重。"""
        results = []
        seen = set()
        for backend in ("uia", "win32"):
            if results:
                break
            try:
                from pywinauto import Desktop
                desktop = Desktop(backend=backend)
                win = desktop.window(handle=hwnd)
                for ctrl in win.descendants(control_type="Button"):
                    text = ""
                    try:
                        text = (ctrl.window_text() or "").strip()
                    except Exception:
                        text = ""
                    if text and _norm(text) not in seen and text not in ("", "&"):
                        seen.add(_norm(text))
                        results.append((ctrl, text))
            except Exception:
                continue
        return results

    # -------------------------------------------------------------- 回车兜底
    def _press_enter_fallback(self, hwnd, title, cls):
        """枚举不到按钮时，模拟回车触发对话框默认按钮（一般即"下一步"）。"""
        try:
            from pywinauto import Desktop
            win = Desktop(backend="win32").window(handle=hwnd)
            try:
                if not win.is_active():
                    win.set_focus()
            except Exception:
                pass
            win.send_keystrokes("{ENTER}")
            self._info(f"[{title[:26]}] 无按钮枚举，回车兜底")
        except Exception:
            pass

    # -------------------------------------------------------------- 进程树
    @staticmethod
    def _process_tree(pid):
        if psutil is None:
            return set()
        try:
            p = psutil.Process(pid)
            return {pid} | {c.pid for c in p.children(recursive=True)}
        except psutil.NoSuchProcess:
            return set()

    # -------------------------------------------------------------- Win32 辅助
    @staticmethod
    def _enum_windows():
        hwnds = []

        def cb(h, _):
            hwnds.append(h)
            return True

        user32.EnumWindows(_EnumWndProc(cb), 0)
        return hwnds

    @staticmethod
    def _window_pid(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    @staticmethod
    def _window_title(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    @staticmethod
    def _window_class(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value


def click_button(ctrl):
    """直接对按钮控件发送 BM_CLICK（不依赖鼠标坐标/窗口前台）。

    pywinauto 控件带 .handle 时用 SendMessage 更稳；
    否则退回控件.click()。
    """
    try:
        handle = getattr(getattr(ctrl, "wrapper_object", lambda: ctrl)(), "handle", None)
        if handle:
            user32.SendMessageW(int(handle), BM_CLICK, 0, 0)
            return True
    except Exception:
        pass
    try:
        ctrl.click()
        return True
    except Exception:
        return False


def spawn(pid: int, log_queue: "queue.Queue") -> ClickBot:
    """创建并启动 ClickBot（供 core.py 使用）。"""
    bot = ClickBot(pid, log_queue)
    bot.start()
    return bot