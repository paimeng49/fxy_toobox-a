import customtkinter as ctk
import threading
import queue
from core.custom_cmd import execute_custom_command
from core.logger import global_logger  # 顶部导入

class CustomCmdPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        
        title = ctk.CTkLabel(self, text="自定义命令", font=("Arial", 20, "bold"))
        title.pack(pady=10)
        
        # 日志区（上）
        self.log_box = ctk.CTkTextbox(self, height=300)
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 输入区（下）
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(fill="x", padx=20, pady=10)
        
        self.input_entry = ctk.CTkEntry(self.input_frame, placeholder_text="输入命令（adb/fastboot/mtk.py/spd_dump）...")
        self.input_entry.pack(side="left", fill="x", expand=True, padx=10)
        
        self.send_btn = ctk.CTkButton(self.input_frame, text="发送", command=self.send_command)
        self.send_btn.pack(side="right", padx=10)
        
        # 回车发送绑定
        self.input_entry.bind("<Return>", lambda e: self.send_command())
        
        self.after(100, self.poll_queue)
        
    def log(self, msg, source="自定义命令"):
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
        
    def send_command(self):
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