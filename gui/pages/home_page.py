# gui/pages/home_page.py
import ctypes
import sys

import customtkinter as ctk
from tkinter import filedialog, Toplevel, messagebox
import threading
import queue
import random
from PIL import Image
from config import settings, constants
from core.easter_eggs import get_random_subtitle
from core.logger import global_logger  # 顶部导入
from core.driver_installer import core as driver_core
from core.driver_installer import automator


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin(window):
    """以管理员身份重启工具箱（源码运行 / exe 运行都支持）。"""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        args = list(sys.argv[1:])
    else:
        exe = sys.executable
        args = [str(settings.BASE_DIR / "main.py")] + list(sys.argv[1:])
    params = " ".join(f'"{a}"' for a in args)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, params, str(settings.BASE_DIR), 1)
    if ret <= 32:
        messagebox.showerror(
            "提权失败",
            "无法以管理员身份启动。\n请手动右键工具箱，选择「以管理员身份运行」。")
        return
    window.log("已以管理员身份启动新实例，当前窗口即将关闭。")
    window.after(300, window.winfo_toplevel().destroy)


class HomePage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        self.install_queue = queue.Queue()
        self._install_running = False
        self._install_completed = 0
        
        # 标题
        title = ctk.CTkLabel(self, text=f"扶小鹰工具箱 {constants.APP_VERSION}", font=("Arial", 24, "bold"))
        title.pack(pady=20)
        
        # 副标题（从subtitle.txt随机读取）
        self.subtitle_label = ctk.CTkLabel(self, text=f"—— {get_random_subtitle()} ——", font=("Arial", 14))
        self.subtitle_label.pack(pady=5)
        
        # 底部固定区：日志 / 赞助 / 作者声明
        # 必须先于内容区 pack 到底部，否则内容区变高后会把它们挤出窗口
        self.log_box = ctk.CTkTextbox(self, height=100, state="disabled")
        self.log_box.pack(side="bottom", fill="x", padx=20, pady=(0, 10))

        self.sponsor_btn = ctk.CTkButton(self, text="赞助二维码", command=self.show_sponsor_qr)
        self.sponsor_btn.pack(side="bottom", pady=(0, 8))

        self.author_frame = ctk.CTkFrame(self)
        self.author_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 10))

        author_title = ctk.CTkLabel(self.author_frame, text="作者声明", font=("Arial", 16, "bold"))
        author_title.pack(pady=(6, 2))

        author_text = ctk.CTkLabel(
            self.author_frame, text=constants.AUTHOR_STATEMENT,
            font=("Arial", 12), justify="left"
        )
        author_text.pack(pady=(0, 8), padx=20)

        # 主内容区（左右分栏，占用剩余空间）
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=(10, 8))
        
        # 左侧：驱动安装区（替代原“下载及性能调整”）
        self.left_frame = ctk.CTkFrame(self.content_frame)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        left_title = ctk.CTkLabel(self.left_frame, text="驱动安装", font=("Arial", 16, "bold"))
        left_title.pack(pady=10)

        # 安装任务清单（由驱动安装引擎统一规划，按顺序静默安装）
        self.driver_tasks = driver_core.build_tasks(str(settings.DEPS_DIR))
        self._install_total = len(self.driver_tasks) or 1

        ctk.CTkLabel(
            self.left_frame,
            text=f"共 {len(self.driver_tasks)} 项任务 · 静默安装 · 已安装项自动跳过",
            font=("Arial", 11), text_color="gray"
        ).pack(pady=(0, 4))

        # 底部固定控件先 pack 到底部，任务清单只占剩余空间，
        # 这样即使任务很多，进度条和安装按钮也不会被挤出界面
        ctk.CTkLabel(
            self.left_frame,
            text="需要管理员权限：点击后如未提权，会提示重启为管理员模式",
            font=("Arial", 11), text_color="gray"
        ).pack(side="bottom", pady=(2, 8))

        self.install_deps_btn = ctk.CTkButton(
            self.left_frame, text="一键安装全部驱动", command=self.install_deps
        )
        self.install_deps_btn.pack(side="bottom", pady=(4, 6), padx=20, fill="x")

        self.driver_progress_txt = ctk.CTkLabel(
            self.left_frame, text=f"0 / {len(self.driver_tasks)}", font=("Arial", 11)
        )
        self.driver_progress_txt.pack(side="bottom", pady=(0, 4))

        self.driver_progress = ctk.CTkProgressBar(self.left_frame, height=12)
        self.driver_progress.set(0)
        self.driver_progress.pack(side="bottom", fill="x", padx=12, pady=(4, 2))

        self.deps_scroll = ctk.CTkScrollableFrame(self.left_frame, height=150)
        self.deps_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        self.driver_task_rows = {}  # {任务名: 图标Label}
        for task in self.driver_tasks:
            row = ctk.CTkFrame(self.deps_scroll, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            icon = ctk.CTkLabel(row, text="  ", width=24)
            icon.pack(side="left")
            ctk.CTkLabel(
                row, text=task.name, anchor="w", justify="left", wraplength=200
            ).pack(side="left", fill="x", expand=True)
            self.driver_task_rows[task.name] = icon
        
        # 右侧：镜像源选择
        self.right_frame = ctk.CTkFrame(self.content_frame)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        right_title = ctk.CTkLabel(self.right_frame, text="GitHub下载镜像源选择", font=("Arial", 16, "bold"))
        right_title.pack(pady=10)
        
        self.mirror_var = ctk.StringVar(value=settings.ACTIVE_MIRROR)
        self.mirror_menu = ctk.CTkOptionMenu(self.right_frame, values=list(settings.GSI_MIRRORS.keys()), variable=self.mirror_var)
        self.mirror_menu.pack(pady=10, padx=20, fill="x")

        # 确认按钮 —— 选完镜像源后点确认才生效
        self.mirror_confirm_btn = ctk.CTkButton(
            self.right_frame, text="✅ 确认切换镜像源",
            command=self.on_mirror_confirm
        )
        self.mirror_confirm_btn.pack(pady=5, padx=20, fill="x")
        
        # 开始轮询队列
        self.after(100, self.poll_queue)
    
    def log(self, msg, source="综合"):
        global_logger.log(msg, source)
        try:
            self.log_queue.put_nowait(msg)
        except queue.Full:
            pass
    
    def poll_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self._poll_install_queue()
        # 限制文本框行数，防止内存暴涨
        try:
            line_count = int(self.log_box.index("end-1c").split(".")[0])
            if line_count > 500:
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", f"{line_count - 500}.0")
                self.log_box.configure(state="disabled")
        except Exception:
            pass
        self.after(100, self.poll_queue)
    
    def on_mirror_confirm(self):
        """确认切换镜像源"""
        selected = self.mirror_var.get()
        if selected == settings.ACTIVE_MIRROR:
            messagebox.showinfo("提示", f"当前镜像源已经是「{selected}」，无需切换")
            return
        settings.ACTIVE_MIRROR = selected
        self.log(f"✅ 全局镜像源已切换为: {selected}")
        messagebox.showinfo("镜像源已切换", f"全局镜像源已切换为:\n{selected}\n\n后续所有 GitHub 下载都将使用此镜像源。")
    
    def install_deps(self):
        """一键安装：静默参数 + UI 自动化兜底 + 真实校验"""
        if self._install_running:
            return

        deps_dir = settings.DEPS_DIR
        if not deps_dir.exists():
            messagebox.showerror("提示", f"找不到驱动资源目录：\n{deps_dir}")
            return

        # 驱动安装必须管理员权限；未提权时询问是否重启为管理员
        if not _is_admin():
            if messagebox.askyesno(
                "需要管理员权限",
                "安装驱动需要管理员权限。\n是否以管理员身份重新启动工具箱？"
            ):
                _relaunch_as_admin(self)
            else:
                self.log("已取消：驱动安装需要管理员权限")
            return

        # MSVC 步骤会监控本进程树，先把自己的窗口排除，避免被自动点击
        automator.ignore_title("扶小鹰工具箱")
        try:
            hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), 2)  # GA_ROOT
            automator.ignore_window(hwnd or self.winfo_id())
        except Exception:
            pass

        self._install_running = True
        self._install_completed = 0
        self.install_deps_btn.configure(state="disabled", text="安装进行中…")
        self.driver_progress.set(0)
        self.driver_progress_txt.configure(text=f"0 / {self._install_total}")
        for icon in self.driver_task_rows.values():
            icon.configure(text="  ", text_color="#ffffff")

        self.log("=" * 40)
        self.log(f"开始执行 {len(self.driver_tasks)} 项驱动/环境安装任务…")
        threading.Thread(target=self._install_thread, daemon=True).start()

    def _install_thread(self):
        engine = driver_core.InstallEngine(self.install_queue, str(settings.DEPS_DIR))
        try:
            engine.run(self.driver_tasks)
        except Exception as e:
            self.install_queue.put(("log", f"❌ 安装流程异常: {e}"))
            self.install_queue.put(("done", []))
        finally:
            self._install_running = False

    def _poll_install_queue(self):
        """处理驱动安装引擎上报的消息（队列跨线程，UI 更新留在主线程）"""
        try:
            while True:
                msg = self.install_queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.log(msg[1])
                elif kind == "status":
                    self._update_task_row(msg[1], msg[2])
                elif kind == "sub":
                    self._update_sub_progress(msg[1], msg[2], msg[3])
                elif kind == "done":
                    self._on_install_done(msg[1])
                elif kind == "debug":
                    self.log("[调试] " + str(msg[1]))
        except queue.Empty:
            pass

    def _update_task_row(self, name, state):
        icon = {"running": "⏳", "ok": "✅", "fail": "❌"}.get(state, "")
        row = self.driver_task_rows.get(name)
        if row:
            color = {"running": "#f5b301", "ok": "#2fbf71", "fail": "#e5484d"}.get(state)
            row.configure(text=f"{icon} ", text_color=color or "#ffffff")
        if state in ("ok", "fail"):
            self._install_completed += 1
            self.driver_progress.set(self._install_completed / self._install_total)
            self.driver_progress_txt.configure(
                text=f"{self._install_completed} / {self._install_total}")

    def _update_sub_progress(self, name, frac, text):
        frac = max(0.0, min(frac, 1.0))
        self.driver_progress.set(
            min((self._install_completed + frac) / self._install_total, 1.0))
        self.driver_progress_txt.configure(text=f"{name} · {text}")

    def _on_install_done(self, summary):
        self.install_deps_btn.configure(state="normal", text="一键安装全部驱动")
        ok_n = sum(1 for _, s, _ in summary if s == "ok")
        fail_n = len(summary) - ok_n
        if fail_n == 0:
            self.log(f"🎉 全部完成：{ok_n} 项安装成功")
        else:
            self.log(f"安装结束：✅ {ok_n} 项成功，❌ {fail_n} 项失败，可再次点击重试")
    
    def show_sponsor_qr(self):
        qr_path = settings.SPONSOR_QR_PATH
        if not qr_path.exists():
            messagebox.showerror("提示", f"找不到赞助二维码文件：\n{qr_path}")
            return
        try:
            img = Image.open(qr_path)
            img.thumbnail((400, 400), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
            top = Toplevel(self)
            top.title("赞助二维码")
            top.geometry(f"{img.width + 20}x{img.height + 40}")
            top.resizable(False, False)
            label = ctk.CTkLabel(top, text="", image=ctk_img)
            label.pack(pady=10)
            ctk.CTkLabel(top, text="感谢您的支持！", font=("Arial", 12)).pack(pady=5)
            self.log("已打开赞助二维码窗口")
        except Exception as e:
            messagebox.showerror("错误", f"加载二维码失败：{e}")
            self.log(f"加载二维码失败: {e}")
