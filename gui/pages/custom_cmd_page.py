# gui/pages/custom_cmd_page.py
"""
自定义命令页 —— 基于 mono-term 的内嵌终端

重要：mono 有两个内置缺陷，必须在 import mono 之后立刻 patch：
  1. Terminal._insert 被 _write_loop 后台线程直接调用 tkinter，
     tkinter 不是线程安全的，会导致输出丢失 / 换行错乱。
     → patch：用 text.after(0, ...) 把插入操作丢回主线程。
  2. Terminal._write_loop 的 ANSI / 换行解析：
     - replace_newline 只处理 \\x1b[<n>;1H（cursor home），
       但 cmd.exe 在 ANSI 模式下用 \\x1b[4;41H 这类 cursor 移动码来回填命令，
       这些没被处理，导致 echo 跟输出粘在一行。
     - 然后 splitlines 在 \\r\\n 上切，但 \\x1b]0;... 这种 OSC 标题码没提前剥掉，
       也会让换行错位。
     → patch：先剥全部 ANSI（用 mono 自带的 strip_ansi_escape_sequences），
       再把 \\r\\n 和裸 \\r 统一换成 \\n，整体作为一段文本 append。
"""
import os
import re

import customtkinter as ctk

from config import settings

# ============ 先尝试导入 mono，成功则立刻 patch ============
_HAS_MONO = False
try:
    import tkinter as _tk
    from mono import Terminals as _MonoTerminals
    import mono.terminal as _mono_terminal
    from mono.ansi import strip_ansi_escape_sequences as _strip_ansi

    _HAS_MONO = True

    # ---------- Patch 1: _insert 改走主线程（mono 0.35.0 / 0.36.0） ----------
    def _patched_insert(self, output, tag=''):
        def _do():
            self.text.insert(_tk.END, output, tag)
            self.text.see(_tk.END)
            self.text.mark_set('input', 'insert')
        try:
            self.text.after(0, _do)
        except Exception:
            pass  # 终端已销毁时 after 会报错，直接忽略

    _mono_terminal.Terminal._insert = _patched_insert

    # ---------- Patch 2: _write_loop 修正 ANSI / 换行解析（mono 0.35.0 / 0.36.0） ----------
    _OSC_RE = re.compile(r'\x1b\][^\x07]*(?:\x1b\\|\x07)')

    def _patched_write_loop(self):
        while self.alive:
            if buf := self.p.read():
                # 先剥 OSC 标题码（\x1b]0;...\\ 或 \x1b]0;...\x07）
                cleaned = _OSC_RE.sub('', buf)
                # 剥所有 ANSI SGR / cursor / ED / EL 等控制码
                cleaned = _strip_ansi(cleaned)
                # 把 \r\n 和裸 \r 统一换成 \n
                cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
                # 一次性 append 到 text widget
                _patched_insert(self, cleaned)

    _mono_terminal.Terminal._write_loop = _patched_write_loop

except Exception:
    _HAS_MONO = False


# ============ 回退实现（无 mono 时的日志 + 输入框） ============
if not _HAS_MONO:
    import threading
    import queue
    from core.custom_cmd import execute_custom_command
    from core.logger import global_logger


def _ensure_tool_path():
    """
    把工具箱的各个工具目录永久加入 PATH。
    mono 的 PTY 在 spawn 时继承 Python 进程的 os.environ。
    避免重复 prepend（多次打开终端可能重复调用）。
    """
    tool_dirs = [
        settings.PLATFORM_TOOLS,
        settings.SPD_DUMP_DIR,
        settings.MTKCLIENT_DIR,
        settings.UNLOCK_MTK_DIR,
    ]
    extra = os.pathsep.join(str(p) for p in tool_dirs if p.exists())
    if not extra:
        return os.environ.get("PATH", "")

    existing = os.environ.get("PATH", "")
    if extra in existing.split(os.pathsep):
        return existing

    os.environ["PATH"] = (extra + os.pathsep + existing) if existing else extra
    return os.environ["PATH"]


class CustomCmdPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.terminals = None
        self._build_header()

        if _HAS_MONO:
            try:
                self._build_terminal_ui()
            except Exception as e:
                print(f"mono 终端初始化失败，回退到简易命令框: {e}")
                for child in self.winfo_children():
                    child.destroy()
                self._build_header()
                self._build_fallback_ui()
        else:
            self._build_fallback_ui()

    def _build_header(self):
        ctk.CTkLabel(self, text="自定义命令", font=("Arial", 20, "bold")).pack(pady=10)

    # ==================== mono 内嵌终端 ====================

    def _build_terminal_ui(self):
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(
            toolbar,
            text="内置终端（已注入 tools 路径，支持 ↑↓ 历史记录，直接敲回车运行）",
            font=("Arial", 12),
            text_color="gray"
        ).pack(side="left", padx=6)

        ctk.CTkButton(toolbar, text="清屏", width=70, command=self._clear_terminal).pack(side="right", padx=4)
        ctk.CTkButton(toolbar, text="新建终端", width=90, command=self._new_terminal).pack(side="right", padx=4)

        # 永久注入 PATH（PTY spawn 时会继承当前 Python 进程的环境变量）
        _ensure_tool_path()

        # main.py 已经 os.chdir 到项目根，PTY 自然继承正确的 cwd
        # 不需要 run_command 发 cd（mono 那个有命令拼接 bug）
        self.terminals = _MonoTerminals(self, cwd=str(settings.BASE_DIR))
        self.terminals.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self.terminals.add_default_terminal()

    def _clear_terminal(self):
        if self.terminals:
            self.terminals.clear_terminal()

    def _new_terminal(self):
        if not self.terminals:
            return
        _ensure_tool_path()
        self.terminals.open_another_terminal()

    # ==================== 回退实现（无 mono） ====================

    def _build_fallback_ui(self):
        self.log_queue = queue.Queue(maxsize=500)

        self.log_box = ctk.CTkTextbox(self, height=300, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)

        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(fill="x", padx=20, pady=10)

        self.input_entry = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="输入命令（adb/fastboot/mtk.py/spd_dump）..."
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=10)
        self.input_entry.bind("<Return>", lambda e: self._send_command())

        self.send_btn = ctk.CTkButton(self.input_frame, text="发送", command=self._send_command)
        self.send_btn.pack(side="right", padx=10)

        ctk.CTkLabel(
            self,
            text="提示：安装 mono-term（pip install mono-term）后可使用内嵌终端",
            font=("Arial", 12),
            text_color="gray"
        ).pack(pady=(0, 10))

        self.after(100, self._poll_queue)

    def log(self, msg, source="自定义命令"):
        global_logger.log(msg, source)
        try:
            self.log_queue.put_nowait(msg)
        except queue.Full:
            pass

    def _poll_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass

        try:
            line_count = int(self.log_box.index("end-1c").split(".")[0])
            if line_count > 500:
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", f"{line_count - 500}.0")
                self.log_box.configure(state="disabled")
        except Exception:
            pass

        self.after(100, self._poll_queue)

    def _send_command(self):
        cmd = self.input_entry.get().strip()
        if not cmd:
            return
        self.log(f"> {cmd}")
        self.input_entry.delete(0, "end")
        threading.Thread(target=self._execute, args=(cmd,), daemon=True).start()

    def _execute(self, cmd):
        ret, out, err = execute_custom_command(cmd)
        if out:
            self.log(out.rstrip())
        if err:
            self.log(err.rstrip())
        if ret != 0:
            self.log(f"返回码: {ret}")
