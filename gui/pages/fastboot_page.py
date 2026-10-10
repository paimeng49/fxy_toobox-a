# gui/pages/fastboot_page.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import queue
import subprocess
import re
from config import settings
from core.device import get_device_mode, get_fastboot_all_data
from core.flashing import run_fastboot_with_progress
from core.logger import global_logger  # 顶部导入

# 文件对话框：优先使用 CTKFileDialog-plus，没装就退回原生
try:
    from CTkFileDialog import askopenfilename as _ctk_askopenfilename
    from CTkFileDialog import askopenfilenames as _ctk_askopenfilenames
    _USE_CTK_DIALOG = True
except ImportError:
    _USE_CTK_DIALOG = False


def _ask_open_file(title, filetypes, parent=None):
    if _USE_CTK_DIALOG:
        return _ctk_askopenfilename(title=title, filetypes=filetypes, autocomplete=True)
    else:
        return filedialog.askopenfilename(title=title, filetypes=filetypes, parent=parent)


def _ask_open_files(title, filetypes, parent=None):
    if _USE_CTK_DIALOG:
        return _ctk_askopenfilenames(title=title, filetypes=filetypes, autocomplete=True)
    else:
        return filedialog.askopenfilenames(title=title, filetypes=filetypes, parent=parent)

class FastbootPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        self.partition_widgets = {}
        self.partition_files = {}
        self.is_working = False

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 左侧区域
        self.left_frame = ctk.CTkFrame(self, corner_radius=10)
        self.left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(1, weight=1)

        self.left_header = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.left_header.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.title_label = ctk.CTkLabel(self.left_header, text="📋 分区表", font=("Arial", 16, "bold"))
        self.title_label.pack(side="left", padx=10)

        self.partition_scroll = ctk.CTkScrollableFrame(self.left_frame, height=400)
        self.partition_scroll.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.empty_label = ctk.CTkLabel(self.partition_scroll, text="正在读取...", font=("Arial", 14), text_color="gray")
        self.empty_label.pack(pady=50)

        # 进度标签
        self.progress_label = ctk.CTkLabel(self.left_frame, text="准备就绪", font=("Arial", 12))
        self.progress_label.grid(row=2, column=0, padx=10, pady=2, sticky="ew")

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(self.left_frame, height=15)
        self.progress_bar.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)

        self.flash_func_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.flash_func_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        self.flash_func_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.flash_btn = ctk.CTkButton(self.flash_func_frame, text="写入选中分区", fg_color="green", command=self.flash_partition)
        self.flash_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.erase_btn = ctk.CTkButton(self.flash_func_frame, text="擦除选中分区", fg_color="red", command=self.erase_partition)
        self.erase_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.full_erase_btn = ctk.CTkButton(self.flash_func_frame, text="擦除Userdata", fg_color="darkred", command=self.erase_userdata)
        self.full_erase_btn.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # 右侧区域
        self.right_frame = ctk.CTkFrame(self, corner_radius=10)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(1, weight=1)

        self.adb_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.adb_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.adb_title = ctk.CTkLabel(self.adb_frame, text="🛠️ ADB / 系统操作", font=("Arial", 16, "bold"))
        self.adb_title.pack(pady=10)

        self.install_apk_btn = ctk.CTkButton(self.adb_frame, text="批量安装APK", command=self.batch_install_apk)
        self.install_apk_btn.pack(fill="x", padx=10, pady=5)
        self.scrcpy_btn = ctk.CTkButton(self.adb_frame, text="投屏 (Scrcpy)", command=self.start_scrcpy)
        self.scrcpy_btn.pack(fill="x", padx=10, pady=5)

        reboot_label = ctk.CTkLabel(self.adb_frame, text="重启设备到：", font=("Arial", 12))
        reboot_label.pack(pady=5)
        self.reboot_var = ctk.StringVar(value="系统")
        self.reboot_menu = ctk.CTkOptionMenu(self.adb_frame, values=["系统", "Bootloader", "Recovery", "Fastbootd"], variable=self.reboot_var)
        self.reboot_menu.pack(fill="x", padx=10, pady=5)
        self.reboot_btn = ctk.CTkButton(self.adb_frame, text="执行重启", command=self.reboot_device)
        self.reboot_btn.pack(fill="x", padx=10, pady=5)

        self.info_btn = ctk.CTkButton(self.adb_frame, text="读取信息 (Getvar All)", command=self.refresh_all_data)
        self.info_btn.pack(fill="x", padx=10, pady=10)

        self.log_title = ctk.CTkLabel(self.right_frame, text="📝 执行日志", font=("Arial", 14, "bold"))
        self.log_title.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="w")
        self.log_box = ctk.CTkTextbox(self.right_frame, height=300)
        self.log_box.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")

        self.after(100, self.poll_queue)

    # 正确缩进在类内的 log 方法
    def log(self, msg, source="Fastboot"):
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

    def _set_working(self, working: bool):
        """锁定/解锁所有操作按钮 + 通知主窗口锁定/解锁导航"""
        self.is_working = working
        state = "disabled" if working else "normal"
        for btn in [self.flash_btn, self.erase_btn,
                    self.full_erase_btn, self.install_apk_btn, self.scrcpy_btn,
                    self.reboot_btn, self.info_btn, self.reboot_menu]:
            btn.configure(state=state)
        parent = self.master
        if hasattr(parent, 'lock_navigation' if working else 'unlock_navigation'):
            getattr(parent, 'lock_navigation' if working else 'unlock_navigation')()

    def refresh_all_data(self):
        self.log("正在执行 fastboot getvar all ...")
        threading.Thread(target=self._refresh_thread, daemon=True).start()

    def _refresh_thread(self):
        info, partitions = get_fastboot_all_data()
        self.after(0, self._update_ui, info, partitions)

    def _update_ui(self, info, partitions):
        self.log("=" * 30)
        for k, v in info.items():
            self.log(f"{k}: {v}")
        self.log("=" * 30)

        for widget in self.partition_scroll.winfo_children():
            widget.destroy()
        self.partition_widgets.clear()
        self.partition_files.clear()

        if not partitions:
            self.empty_label = ctk.CTkLabel(self.partition_scroll, text="未检测到分区，请检查设备连接", font=("Arial", 14))
            self.empty_label.pack(pady=50)
            self.log("❌ 未读取到分区表")
            return

        header = ctk.CTkFrame(self.partition_scroll, fg_color="gray20")
        header.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header, text="  名称", width=150, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(header, text="  大小", width=100, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(header, text="  选择", width=60, anchor="center").pack(side="left", padx=5)
        ctk.CTkLabel(header, text="  文件名", width=100, anchor="center").pack(side="left", padx=5)

        for part in partitions:
            row = ctk.CTkFrame(self.partition_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            name_lbl = ctk.CTkLabel(row, text=part["name"], width=150, anchor="w")
            name_lbl.pack(side="left", padx=5)
            size_lbl = ctk.CTkLabel(row, text=part["size"], width=100, anchor="w")
            size_lbl.pack(side="left", padx=5)
            var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(row, text="", width=40, variable=var)
            chk.pack(side="left", padx=5)
            self.partition_widgets[part["name"]] = var

            def select_file(part_name=part["name"]):
                file = _ask_open_file(
                    title=f"为 {part_name} 选择镜像文件",
                    filetypes=[("镜像文件", "*.img;*.bin"), ("所有文件", "*.*")],
                    parent=self.winfo_toplevel()
                )
                if file:
                    self.partition_files[part_name] = file
                    self.log(f"已为 {part_name} 选择文件: {file}")

            btn = ctk.CTkButton(row, text="选择文件", width=100, command=select_file)
            btn.pack(side="left", padx=5)

        self.log(f"✅ 读取成功，共 {len(partitions)} 个分区。")

    def flash_partition(self):
        if self.is_working:
            return
        selected = [name for name, var in self.partition_widgets.items() if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请先勾选要写入的分区")
            return
        missing = [name for name in selected if name not in self.partition_files]
        if missing:
            messagebox.showerror("错误", f"{missing[0]} 未指定写入文件，请先指定写入文件！")
            return
        self._set_working(True)
        self.log(f"开始写入分区: {selected}")
        threading.Thread(target=self._flash_thread, args=(selected,), daemon=True).start()

    def _flash_thread(self, partitions):
        try:
            total_partitions = len(partitions)
            completed_partitions = 0

            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)
            self.progress_label.configure(text="开始刷写...")

            for part in partitions:
                file = self.partition_files[part]
                self.log(f"正在写入 {part} ...")

                def on_progress(pct, line):
                    overall = (completed_partitions + pct / 100) / total_partitions
                    self.progress_bar.set(overall)
                    self.progress_label.configure(text=f"{part}: {pct:.1f}%  |  总进度: {overall*100:.1f}%")

                ret = run_fastboot_with_progress(
                    f"fastboot flash {part} \"{file}\"",
                    cwd=settings.PLATFORM_TOOLS,
                    log_callback=lambda msg: self.log(msg),
                    progress_callback=on_progress,
                )

                completed_partitions += 1
                overall_progress = completed_partitions / total_partitions
                self.progress_bar.set(overall_progress)
                self.progress_label.configure(text=f"已完成 {completed_partitions}/{total_partitions} 个分区")

            self.progress_bar.set(1.0)
            self.progress_label.configure(text="全部完成")
            self.log("所有写入操作完成。")
        except Exception as e:
            self.log(f"❌ 刷写异常: {e}")
        finally:
            self.after(0, lambda: self._set_working(False))

    def erase_partition(self):
        if self.is_working:
            return
        selected = [name for name, var in self.partition_widgets.items() if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请先勾选要擦除的分区")
            return
        self._set_working(True)
        self.log(f"开始擦除分区: {selected}")
        threading.Thread(target=self._erase_thread, args=(selected,), daemon=True).start()

    def _erase_thread(self, partitions):
        total = len(partitions)
        completed = 0

        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_label.configure(text="开始擦除...")

        for part in partitions:
            self.log(f"正在擦除 {part} ...")
            try:
                result = subprocess.run(f"fastboot erase {part}", cwd=settings.PLATFORM_TOOLS, capture_output=True, text=True, shell=True, timeout=60)
                if result.returncode == 0:
                    self.log(f"✅ 擦除成功: {part}")
                else:
                    self.log(f"❌ 擦除失败: {part} - {result.stderr}")
            except subprocess.TimeoutExpired:
                self.log(f"❌ 擦除超时: {part}")

            completed += 1
            progress = completed / total
            self.progress_bar.set(progress)
            self.progress_label.configure(text=f"已完成 {completed}/{total} 个分区")

        self.progress_bar.set(1.0)
        self.progress_label.configure(text="全部完成")
        self.after(0, lambda: self._set_working(False))

    def erase_userdata(self):
        if self.is_working:
            return
        confirm = messagebox.askyesno("高危警告", "确定要擦除 userdata 吗？")
        if confirm:
            self._set_working(True)
            threading.Thread(target=self._erase_userdata_thread, daemon=True).start()

    def _erase_userdata_thread(self):
        self.progress_bar.configure(mode="indeterminate")
        self.progress_label.configure(text="正在擦除 userdata ...")
        try:
            result = subprocess.run("fastboot erase userdata", cwd=settings.PLATFORM_TOOLS, capture_output=True, text=True, shell=True, timeout=120)
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(1.0)
            self.progress_label.configure(text="userdata 擦除完成")
            if result.returncode == 0:
                self.log("✅ userdata 擦除成功")
            else:
                self.log(f"❌ 擦除失败: {result.stderr}")
        except subprocess.TimeoutExpired:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(1.0)
            self.progress_label.configure(text="userdata 擦除超时")
            self.log("❌ userdata 擦除超时")
        self.after(0, lambda: self._set_working(False))

    def batch_install_apk(self):
        if self.is_working:
            return
        files = _ask_open_files(
            title="选择APK文件",
            filetypes=[("APK文件", "*.apk")],
            parent=self.winfo_toplevel()
        )
        if files:
            self._set_working(True)
            threading.Thread(target=self._install_apks, args=(files,), daemon=True).start()

    def _install_apks(self, files):
        total = len(files)
        done = 0
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_label.configure(text="开始安装APK...")
        for apk in files:
            try:
                result = subprocess.run(f"adb install -r \"{apk}\"", cwd=settings.PLATFORM_TOOLS, capture_output=True, text=True, shell=True, timeout=120)
                done += 1
                self.progress_bar.set(done / total)
                self.progress_label.configure(text=f"APK {done}/{total} 安装完成")
                if result.returncode == 0:
                    self.log(f"✅ 安装成功: {apk}")
                else:
                    self.log(f"❌ 安装失败: {apk} - {result.stderr}")
            except subprocess.TimeoutExpired:
                done += 1
                self.progress_bar.set(done / total)
                self.progress_label.configure(text=f"APK {done}/{total} 安装超时")
                self.log(f"❌ 安装超时: {apk}")
        self.progress_bar.set(1.0)
        self.progress_label.configure(text="APK安装全部完成")
        self.after(0, lambda: self._set_working(False))

    def start_scrcpy(self):
        scrcpy_exe = settings.SCRCPY_DIR / "scrcpy.exe"
        if scrcpy_exe.exists():
            subprocess.Popen(str(scrcpy_exe), cwd=settings.SCRCPY_DIR, shell=True)
            self.log("已启动 Scrcpy 投屏")
        else:
            self.log("找不到 Scrcpy 工具")

    def reboot_device(self):
        target = self.reboot_var.get()
        mode = get_device_mode()
        if mode == "adb":
            cmd_map = {"系统": "reboot", "Bootloader": "reboot bootloader", "Recovery": "reboot recovery", "Fastbootd": "reboot fastboot"}
            cmd = f"adb {cmd_map[target]}"
        elif mode == "fastboot":
            cmd_map = {"系统": "reboot", "Bootloader": "reboot bootloader", "Recovery": "reboot recovery", "Fastbootd": "reboot fastboot"}
            cmd = f"fastboot {cmd_map[target]}"
        else:
            self.log("未检测到设备")
            return
        self.log(f"执行: {cmd}")
        try:
            subprocess.run(cmd, cwd=settings.PLATFORM_TOOLS, shell=True, timeout=30)
        except subprocess.TimeoutExpired:
            self.log("❌ 命令执行超时")
