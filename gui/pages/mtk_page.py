# gui/pages/mtk_page.py
import customtkinter as ctk
import threading
import queue
from core import mtk_tools
from core.logger import global_logger  # 顶部导入

class MtkPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        
        title = ctk.CTkLabel(self, text="🔧 联发科（MTK）工具", font=("Arial", 20, "bold"))
        title.pack(pady=20)
        
        self.open_gui_btn = ctk.CTkButton(self, text="打开 MTKClient 官方 GUI", font=("Arial", 14, "bold"), command=self.open_gui)
        self.open_gui_btn.pack(pady=10)
        
        self.install_deps_btn = ctk.CTkButton(self, text="安装MTK依赖库", command=self.install_deps)
        self.install_deps_btn.pack(pady=10)
        
        self.log_title = ctk.CTkLabel(self, text="📝 执行日志", font=("Arial", 14, "bold"))
        self.log_title.pack(pady=5)
        self.log_box = ctk.CTkTextbox(self, height=300, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.after(100, self.poll_queue)
    
    def log(self, msg, source="联发科"):
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
    
    def open_gui(self):
        self.log("正在启动 MTKClient GUI...")
        threading.Thread(target=self._open_gui_thread, daemon=True).start()
    
    def _open_gui_thread(self):
        # 【关键】传入 self.log 作为 output_callback
        ret, out, err = mtk_tools.open_mtk_gui(output_callback=self.log)
        if out: self.log(out)
        if err: self.log(err)
        self.log("GUI 已启动，若关闭窗口后日志停止输出，属正常现象。")
    
    def install_deps(self):
        self.log("开始安装MTK依赖库...")
        threading.Thread(target=self._install_deps_thread, daemon=True).start()
    
    def _install_deps_thread(self):
        ret, out, err = mtk_tools.run_install_deps(output_callback=self.log)
        if out: self.log(out)
        if err: self.log(err)
        self.log("依赖安装完成。")