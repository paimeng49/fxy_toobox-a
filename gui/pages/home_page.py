# gui/pages/home_page.py
import customtkinter as ctk
from tkinter import filedialog, Toplevel, messagebox
import threading
import queue
import subprocess
import random
from PIL import Image
from config import settings, constants
from core.easter_eggs import get_random_subtitle
from core.logger import global_logger  # 顶部导入

class HomePage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        
        # 标题
        title = ctk.CTkLabel(self, text=f"扶小鹰工具箱 {constants.APP_VERSION}", font=("Arial", 24, "bold"))
        title.pack(pady=20)
        
        # 副标题（从subtitle.txt随机读取）
        self.subtitle_label = ctk.CTkLabel(self, text=f"—— {get_random_subtitle()} ——", font=("Arial", 14))
        self.subtitle_label.pack(pady=5)
        
        # 主内容区（左右分栏）
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 左侧：驱动安装区（替代原“下载及性能调整”）
        self.left_frame = ctk.CTkFrame(self.content_frame)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        left_title = ctk.CTkLabel(self.left_frame, text="驱动安装", font=("Arial", 16, "bold"))
        left_title.pack(pady=10)
        
        # 显示驱动列表（可滚动，多选）
        self.deps_scroll = ctk.CTkScrollableFrame(self.left_frame, height=250)
        self.deps_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.deps_checkboxes = {}  # 存储 {文件路径: BooleanVar}
        self.load_deps_list()
        
        # 安装按钮
        self.install_deps_btn = ctk.CTkButton(self.left_frame, text="一键安装所选驱动", command=self.install_deps)
        self.install_deps_btn.pack(pady=10, padx=20, fill="x")
        
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
        
        # 作者声明
        self.author_frame = ctk.CTkFrame(self)
        self.author_frame.pack(fill="x", padx=20, pady=10)
        
        author_title = ctk.CTkLabel(self.author_frame, text="作者声明", font=("Arial", 16, "bold"))
        author_title.pack(pady=5)
        
        author_text = ctk.CTkLabel(self.author_frame, text=constants.AUTHOR_STATEMENT, font=("Arial", 12), justify="left")
        author_text.pack(pady=5, padx=20)
        
        # 赞助二维码按钮
        self.sponsor_btn = ctk.CTkButton(self, text="赞助二维码", command=self.show_sponsor_qr)
        self.sponsor_btn.pack(pady=10)
        
        # 日志区（只读）
        self.log_box = ctk.CTkTextbox(self, height=100, state="disabled")
        self.log_box.pack(fill="x", padx=20, pady=10)
        
        # 开始轮询队列
        self.after(100, self.poll_queue)
    
    def load_deps_list(self):
        """读取支持库及驱动目录下的exe/msi文件，并生成复选框（默认全选）"""
        deps_dir = settings.DEPS_DIR
        if not deps_dir.exists():
            self.log(f"⚠️ 找不到驱动文件夹: {deps_dir}")
            return
        
        # 清空旧内容
        for widget in self.deps_scroll.winfo_children():
            widget.destroy()
        self.deps_checkboxes.clear()
        
        # 收集所有 exe 和 msi 文件
        deps_files = list(deps_dir.glob("*.exe")) + list(deps_dir.glob("*.msi"))
        if not deps_files:
            self.log("⚠️ 驱动文件夹内没有 .exe 或 .msi 文件")
            return
        
        for file in deps_files:
            var = ctk.BooleanVar(value=True)  # 默认全选
            chk = ctk.CTkCheckBox(self.deps_scroll, text=file.name, variable=var)
            chk.pack(fill="x", padx=10, pady=2)
            self.deps_checkboxes[str(file)] = var
        
        self.log(f"已加载 {len(deps_files)} 个驱动文件，默认全选。")
    
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
        """安装勾选的驱动"""
        selected = [path for path, var in self.deps_checkboxes.items() if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请至少勾选一个驱动文件")
            return
        
        self.log(f"开始安装 {len(selected)} 个驱动...")
        threading.Thread(target=self._install_thread, args=(selected,), daemon=True).start()
    
    def _install_thread(self, selected):
        # 检查管理员权限（可选，驱动安装通常需要管理员）
        # 如果你需要，可以调用 is_admin 检查，这里暂不强制
        for file_path in selected:
            self.log(f"正在安装: {file_path}")
            try:
                # 使用 subprocess 运行安装程序（路径带双引号防空格）
                result = subprocess.run(
                    f'"{file_path}"',
                    cwd=settings.DEPS_DIR,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                if result.returncode == 0:
                    self.log(f"✅ 安装成功: {file_path}")
                else:
                    self.log(f"❌ 安装可能失败: {file_path} (返回码 {result.returncode})")
            except Exception as e:
                self.log(f"❌ 安装异常: {file_path} - {e}")
        self.log("所有驱动安装流程结束。")
    
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
