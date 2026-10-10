# gui/main_window.py
import customtkinter as ctk
from PIL import Image
import threading
import time
import ctypes
import sys
from pathlib import Path
from config import settings

from .pages.home_page import HomePage
from .pages.fastboot_page import FastbootPage
from .pages.spd_page import SpdPage
from .pages.mtk_page import MtkPage
from .pages.unlock_page import UnlockPage
from .pages.wheelchair_page import WheelchairPage
from .pages.custom_cmd_page import CustomCmdPage
from .pages.sites_page import SitesPage

class MainWindow(ctk.CTk):
    def __init__(self):
        # 【关键1】必须在此设置AppUserModelID，否则任务栏图标无效
        # 强烈建议将此行移到 main.py 的开头（所有 import 之前）
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.fxytoolbox.app"
        )

        super().__init__()
        self.title("扶小鹰工具箱 v2.0-rc2")
        self.geometry("1150x720")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 注意：图标和任务栏样式的设置已移到主界面显示后
        # 见 _apply_icon_and_taskbar()

        # 显示启动画面 + 后台初始化线程
        self._show_splash()
        threading.Thread(target=self._init_background, daemon=True).start()

    def _apply_icon_and_taskbar(self):
        """在主窗口显示后重新设置图标和任务栏样式（防止启动画面干扰）"""
        # 设置窗口图标（兼容打包路径）
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).parent.parent
        icon_path = base_dir / "app_icon.ico"
        try:
            self.iconbitmap(str(icon_path))
        except Exception as e:
            print(f"图标设置失败: {e}")

        # 强制任务栏使用自定义图标（通过扩展样式）
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW   # 移除工具窗口标志
            style = style | WS_EX_APPWINDOW     # 添加应用窗口标志
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
            # 刷新窗口
            self.update_idletasks()
            # 有时需要重新显示才能生效
            self.withdraw()
            self.after(50, self.deiconify)
        except Exception as e:
            print(f"任务栏图标刷新失败: {e}")

    def _show_splash(self):
        """显示启动画面：无边框置顶窗口，包含启动图和启动中字样"""
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        splash_frame = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=0)
        splash_frame.pack(fill="both", expand=True)

        img_path = getattr(settings, 'SPLASH_IMAGE_PATH', None)
        if img_path and img_path.exists():
            img = Image.open(img_path)
            img.thumbnail((300, 300))
            splash_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
            img_label = ctk.CTkLabel(splash_frame, image=splash_img, text="")
            img_label.pack(pady=30)
        else:
            img_label = ctk.CTkLabel(splash_frame, text="扶小鹰工具箱", font=("Arial", 30, "bold"))
            img_label.pack(pady=30)

        loading_label = ctk.CTkLabel(splash_frame, text="启动中...", font=("Arial", 20))
        loading_label.pack(pady=10)

        self.splash_progress = ctk.CTkProgressBar(splash_frame, mode="indeterminate", width=300)
        self.splash_progress.pack(pady=20)
        self.splash_progress.start()

        self.splash_frame = splash_frame

    def _init_background(self):
        """后台执行耗时初始化"""
        try:
            # 预先导入所有页面，确保模块被加载
            from .pages.home_page import HomePage
            from .pages.fastboot_page import FastbootPage
            from .pages.spd_page import SpdPage
            from .pages.mtk_page import MtkPage
            from .pages.unlock_page import UnlockPage
            from .pages.wheelchair_page import WheelchairPage
            from .pages.custom_cmd_page import CustomCmdPage
            from .pages.sites_page import SitesPage
            time.sleep(0.5)  # 模拟初始化耗时
        except Exception as e:
            print(f"初始化错误: {e}")
        finally:
            self.after(0, self._show_main_ui)

    def _show_main_ui(self):
        """销毁启动画面，构建主界面"""
        self.splash_progress.stop()
        self.splash_frame.destroy()
        # 恢复窗口样式
        self.overrideredirect(False)
        self.attributes("-topmost", False)

        # ========== 关键：在此处应用图标和任务栏样式 ==========
        self._apply_icon_and_taskbar()
        # =====================================================

        # 创建侧边栏
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        title_label = ctk.CTkLabel(self.sidebar, text="扶小鹰工具箱", font=("Arial", 18, "bold"))
        title_label.pack(pady=20)

        self.pages = {}
        nav_items = [
            ("综合", HomePage),
            ("Fastboot/ADB", FastbootPage),
            ("展讯", SpdPage),
            ("联发科", MtkPage),
            ("解锁Bootloader", UnlockPage),
            ("一键刷机", WheelchairPage),
            ("自定义命令", CustomCmdPage),
            ("实用网站", SitesPage),
        ]
        self.nav_buttons = {}
        for name, page_class in nav_items:
            btn = ctk.CTkButton(self.sidebar, text=name, command=lambda n=name: self.show_page(n))
            btn.pack(fill="x", padx=10, pady=5)
            self.pages[name] = page_class(self)
            self.nav_buttons[name] = btn
        self.show_page("综合")

    def show_page(self, name):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)

    def lock_navigation(self):
        """锁定所有导航按钮（操作进行中禁止切换页面）"""
        for btn in self.nav_buttons.values():
            btn.configure(state="disabled")

    def unlock_navigation(self):
        """解锁所有导航按钮"""
        for btn in self.nav_buttons.values():
            btn.configure(state="normal")