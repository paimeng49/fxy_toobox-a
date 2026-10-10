# gui/pages/spd_page.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import queue
from config import settings
from core.spd_tools import SpdSession, parse_spd_partitions, parse_progress
from core.logger import global_logger

# 文件对话框：优先使用 CTKFileDialog-plus（纯CTK实现，不会卡），没装就退回原生
try:
    from CTkFileDialog import askopenfilename as _ctk_askopenfilename
    from CTkFileDialog import askdirectory as _ctk_askdirectory
    _USE_CTK_DIALOG = True
except ImportError:
    _USE_CTK_DIALOG = False


def _ask_open_file(title, filetypes, parent=None):
    """统一的文件选择对话框"""
    if _USE_CTK_DIALOG:
        return _ctk_askopenfilename(title=title, filetypes=filetypes, autocomplete=True)
    else:
        return filedialog.askopenfilename(title=title, filetypes=filetypes, parent=parent)


def _ask_directory(title, parent=None):
    """统一的目录选择对话框"""
    if _USE_CTK_DIALOG:
        return _ctk_askdirectory(title=title, autocomplete=True)
    else:
        return filedialog.askdirectory(title=title, parent=parent)


class SpdPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        self.session = SpdSession()
        self.partition_widgets = {}
        self.partition_files = {}
        self.backup_dir = None
        self.is_working = False  # 统一的工作锁（备份/写入/擦除都用这个）

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
        self.title_label = ctk.CTkLabel(self.left_header, text="📋 展讯分区表（需先发送引导）", font=("Arial", 16, "bold"))
        self.title_label.pack(side="left", padx=10)
        self.refresh_btn = ctk.CTkButton(self.left_header, text="发送引导", width=120, command=self.refresh_partitions)
        self.refresh_btn.pack(side="right", padx=10)

        self.partition_scroll = ctk.CTkScrollableFrame(self.left_frame, height=400)
        self.partition_scroll.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.empty_label = ctk.CTkLabel(self.partition_scroll, text="未连接设备或未发送引导\n请点击右上角发送引导", font=("Arial", 14), text_color="gray")
        self.empty_label.pack(pady=50)

        self.progress_label = ctk.CTkLabel(self.left_frame, text="准备就绪", font=("Arial", 12))
        self.progress_label.grid(row=2, column=0, padx=10, pady=2, sticky="ew")
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
        self.backup_btn = ctk.CTkButton(self.flash_func_frame, text="备份/读取分区\n(不勾选=全部)", command=self.backup_all_partitions)
        self.backup_btn.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # 右侧区域
        self.right_frame = ctk.CTkFrame(self, corner_radius=10)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(1, weight=1)

        self.spd_action_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.spd_action_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.spd_title = ctk.CTkLabel(self.spd_action_frame, text="🛠️ 展讯专用操作", font=("Arial", 16, "bold"))
        self.spd_title.pack(pady=10)

        self.cpu_var = ctk.StringVar(value="T606/T616")
        self.cpu_menu = ctk.CTkOptionMenu(self.spd_action_frame, values=["T606/T616", "T610/T618"], variable=self.cpu_var)
        self.cpu_menu.pack(fill="x", padx=10, pady=5)

        self.select_dir_btn = ctk.CTkButton(self.spd_action_frame, text="选择备份目录", command=self.select_backup_dir)
        self.select_dir_btn.pack(fill="x", padx=10, pady=5)

        reboot_label = ctk.CTkLabel(self.spd_action_frame, text="重启到：", font=("Arial", 12))
        reboot_label.pack(pady=5)
        self.reboot_var = ctk.StringVar(value="系统")
        self.reboot_menu = ctk.CTkOptionMenu(self.spd_action_frame, values=["系统", "Fastbootd", "Recovery", "关机"], variable=self.reboot_var)
        self.reboot_menu.pack(fill="x", padx=10, pady=5)
        self.reboot_btn = ctk.CTkButton(self.spd_action_frame, text="执行重启", command=self.reboot_device)
        self.reboot_btn.pack(fill="x", padx=10, pady=10)

        self.log_title = ctk.CTkLabel(self.right_frame, text="📝 执行日志", font=("Arial", 14, "bold"))
        self.log_title.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="w")
        self.log_box = ctk.CTkTextbox(self.right_frame, height=300, state="disabled")
        self.log_box.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")

        self.after(100, self.poll_queue)

    # ============== 日志相关 ==============

    def log(self, msg, source="展讯"):
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

    # ============== 工具方法 ==============

    def _set_working(self, working: bool):
        """设置工作状态，禁用/启用所有操作按钮 + 锁定/解锁导航"""
        self.is_working = working
        state = "disabled" if working else "normal"
        self.refresh_btn.configure(state=state)
        self.flash_btn.configure(state=state)
        self.erase_btn.configure(state=state)
        self.backup_btn.configure(state=state)
        self.reboot_btn.configure(state=state)
        self.select_dir_btn.configure(state=state)
        # 通知主窗口锁定/解锁导航
        parent = self.master
        if hasattr(parent, 'lock_navigation' if working else 'unlock_navigation'):
            getattr(parent, 'lock_navigation' if working else 'unlock_navigation')()

    def _reset_progress(self):
        """重置进度条"""
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备就绪")

    def _check_session(self) -> bool:
        """检查会话是否可用，不可用则弹出提示并返回 False"""
        if not self.session.is_alive():
            messagebox.showerror("错误", "会话已断开，请先点击「发送引导」重新连接设备！")
            return False
        return True

    # ============== 发送引导 ==============

    def refresh_partitions(self):
        if self.is_working:
            return
        self._set_working(True)
        self.log("正在发送引导并连接设备...")
        for widget in self.partition_scroll.winfo_children():
            widget.destroy()
        self.empty_label = ctk.CTkLabel(self.partition_scroll, text="正在发送引导...", font=("Arial", 14))
        self.empty_label.pack(pady=50)
        threading.Thread(target=self._start_session_thread, daemon=True).start()

    def _start_session_thread(self):
        cpu = self.cpu_var.get()
        try:
            def output_callback(line):
                self.log(line)

            output = self.session.start(cpu, output_callback=output_callback)
            partitions = parse_spd_partitions(output)
            self.after(0, self._render_partitions, partitions)
        except Exception as e:
            self.log(f"引导失败: {e}")
            self.log("检查：① 是否进入深刷模式（关机+音量减+插USB）；② 是否已安装展讯驱动")
            self.after(0, self._show_error)
        finally:
            self.after(0, lambda: self._set_working(False))

    def _show_error(self):
        for widget in self.partition_scroll.winfo_children():
            widget.destroy()
        self.empty_label = ctk.CTkLabel(self.partition_scroll, text="引导失败，请检查设备和驱动", font=("Arial", 14), text_color="red")
        self.empty_label.pack(pady=50)

    def _render_partitions(self, partitions):
        for widget in self.partition_scroll.winfo_children():
            widget.destroy()
        self.partition_widgets.clear()
        self.partition_files.clear()

        if not partitions:
            self.empty_label = ctk.CTkLabel(self.partition_scroll, text="未检测到分区", font=("Arial", 14))
            self.empty_label.pack(pady=50)
            self.log("❌ 未读取到分区")
            return

        header = ctk.CTkFrame(self.partition_scroll, fg_color="gray20")
        header.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header, text="  名称", width=180, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(header, text="  大小", width=100, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(header, text="  选择", width=60, anchor="center").pack(side="left", padx=5)
        ctk.CTkLabel(header, text="  文件名", width=100, anchor="center").pack(side="left", padx=5)

        for part in partitions:
            row = ctk.CTkFrame(self.partition_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)

            name_lbl = ctk.CTkLabel(row, text=part["name"], width=180, anchor="w")
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

        self.log(f"✅ 发送引导成功，共 {len(partitions)} 个分区。")
        self.log("💡 提示：如需直接备份全部分区，无需勾选任何分区，直接点击下方【备份/读取分区】按钮即可。")

    # ============== 备份目录 ==============

    def select_backup_dir(self):
        """选择备份保存目录"""
        directory = _ask_directory(title="选择备份保存目录", parent=self.winfo_toplevel())
        if directory:
            self.backup_dir = directory
            self.log(f"备份目录已设置为: {directory}")

    # ============== 写入分区 ==============

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
        if not self._check_session():
            return
        self.log(f"向 FDL2 会话发送写入命令: {selected}")
        self._set_working(True)
        threading.Thread(target=self._write_thread, args=(selected,), daemon=True).start()

    def _write_thread(self, selected):
        try:
            total = len(selected)
            success_count = 0
            fail_count = 0
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)

            for idx, part in enumerate(selected):
                file = self.partition_files[part]
                self.log(f"正在写入 {part} ...")

                # 包装 output_callback 来捕获进度
                current_part_progress = 0.0

                def output_cb(line, p_idx=idx, p_total=total):
                    nonlocal current_part_progress
                    prog = parse_progress(line)
                    if prog is not None:
                        current_part_progress = prog
                        # 总进度 = (已完成分区 + 当前分区进度/100) / 总分区
                        overall = (p_idx + current_part_progress / 100.0) / p_total * 100
                        self.after(0, lambda v=overall, l=line: self._update_progress(v, f"写入中: {part} ({prog:.1f}%)"))
                    self.log(line)

                success, output = self.session.send_command(
                    f'w {part} "{file}"',
                    output_callback=output_cb
                )

                if success:
                    success_count += 1
                    self.log(f"✅ 写入成功: {part}")
                else:
                    fail_count += 1
                    self.log(f"❌ 写入失败: {part}")
                    # 写入失败也继续下一个，最后统一报告

                # 更新总进度
                overall = (idx + 1) / total * 100
                self.after(0, lambda v=overall: self._update_progress(v, f"已完成 {idx+1}/{total} 个分区"))

            # 最终结果
            self.progress_bar.set(1.0)
            if fail_count == 0:
                self.progress_label.configure(text=f"✅ 全部写入完成（共 {total} 个分区）")
                self.log(f"✅ 所有写入操作完成（成功 {success_count} 个）。")
            else:
                self.progress_label.configure(text=f"⚠️ 写入完成（成功 {success_count}，失败 {fail_count}）")
                self.log(f"⚠️ 写入完成：成功 {success_count} 个，失败 {fail_count} 个。")
        except Exception as e:
            self.log(f"❌ 写入异常: {e}")
        finally:
            self.after(0, lambda: self._set_working(False))

    def _update_progress(self, percent: float, label_text: str):
        """更新进度条和标签（在主线程调用）"""
        self.progress_bar.set(percent / 100.0)
        self.progress_label.configure(text=label_text)

    # ============== 擦除分区 ==============

    def erase_partition(self):
        if self.is_working:
            return
        selected = [name for name, var in self.partition_widgets.items() if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请先勾选要擦除的分区")
            return
        if not messagebox.askyesno("确认擦除", f"确定要擦除以下 {len(selected)} 个分区吗？\n\n{', '.join(selected)}\n\n此操作不可恢复！"):
            return
        if not self._check_session():
            return
        self.log(f"向 FDL2 会话发送擦除命令: {selected}")
        self._set_working(True)
        threading.Thread(target=self._erase_thread, args=(selected,), daemon=True).start()

    def _erase_thread(self, selected):
        try:
            total = len(selected)
            success_count = 0
            fail_count = 0

            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)

            for idx, part in enumerate(selected):
                self.log(f"正在擦除 {part} ...")
                success, output = self.session.send_command(f"e {part}", output_callback=self.log)
                if success:
                    success_count += 1
                    self.log(f"✅ 擦除成功: {part}")
                else:
                    fail_count += 1
                    self.log(f"❌ 擦除失败: {part}")

                progress = (idx + 1) / total * 100
                self.after(0, lambda v=progress, t=f"已完成 {idx+1}/{total} 个分区": self._update_progress(v, t))

            self.progress_bar.set(1.0)
            if fail_count == 0:
                self.progress_label.configure(text=f"✅ 全部擦除完成（共 {total} 个分区）")
                self.log(f"✅ 所有擦除操作完成（成功 {success_count} 个）。")
            else:
                self.progress_label.configure(text=f"⚠️ 擦除完成（成功 {success_count}，失败 {fail_count}）")
                self.log(f"⚠️ 擦除完成：成功 {success_count} 个，失败 {fail_count} 个。")
        except Exception as e:
            self.log(f"❌ 擦除异常: {e}")
        finally:
            self.after(0, lambda: self._set_working(False))

    # ============== 备份分区 ==============

    def backup_all_partitions(self):
        if self.is_working:
            return

        selected = [name for name, var in self.partition_widgets.items() if var.get()]

        # 未勾选就是全部备份
        if not selected:
            self.log("未勾选任何分区，将执行全部分区备份 (r all)")
        else:
            self.log(f"将备份以下勾选分区: {selected}")

        self._set_working(True)
        threading.Thread(target=self._backup_thread, args=(selected,), daemon=True).start()

    def _backup_thread(self, selected):
        try:
            if not self.backup_dir:
                self.after(0, lambda: messagebox.showerror("错误", "请先在右侧选择备份目录！"))
                return

            if not self._check_session_threadsafe():
                return

            self.log(f"设置备份路径: {self.backup_dir}")
            success, output = self.session.send_command(
                f'path "{self.backup_dir}"',
                output_callback=self.log
            )
            if not success:
                self.log("❌ 设置备份路径失败")
                return

            if not selected:
                # r all 模式
                self.log("正在备份全部分区...")

                current_prog = 0.0

                def all_backup_cb(line):
                    nonlocal current_prog
                    prog = parse_progress(line)
                    if prog is not None:
                        current_prog = prog
                        self.after(0, lambda v=prog: self._update_progress(v, f"全盘备份中... {prog:.1f}%"))
                    self.log(line)

                success, output = self.session.send_command("r all", output_callback=all_backup_cb)
                if success:
                    self.log("✅ 全盘备份完成。")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="✅ 全盘备份完成")
                else:
                    self.log("❌ 全盘备份失败。")
                    self.progress_label.configure(text="❌ 备份失败")
            else:
                # 逐个备份
                total = len(selected)
                success_count = 0
                fail_count = 0

                self.progress_bar.configure(mode="determinate")
                self.progress_bar.set(0)

                for idx, part in enumerate(selected):
                    self.log(f"正在备份分区 {part} ...")

                    current_prog = 0.0

                    def part_cb(line, p_idx=idx, p_total=total, p_name=part):
                        nonlocal current_prog
                        prog = parse_progress(line)
                        if prog is not None:
                            current_prog = prog
                            overall = (p_idx + current_prog / 100.0) / p_total * 100
                            self.after(0, lambda v=overall: self._update_progress(v, f"备份中: {p_name} ({prog:.1f}%)"))
                        self.log(line)

                    success, output = self.session.send_command(f"r {part}", output_callback=part_cb)

                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                        # 如果是进程挂了，后面的也不用试了
                        if "进程未运行" in output:
                            self.log("❌ 会话已断开，剩余分区跳过备份")
                            # 把剩余分区都算失败
                            fail_count += (total - idx - 1)
                            break

                    progress = (idx + 1) / total * 100
                    self.after(0, lambda v=progress: self._update_progress(v, f"已备份 {idx+1}/{total} 个分区"))

                # 最终统计
                self.progress_bar.set(1.0)
                if fail_count == 0:
                    self.progress_label.configure(text=f"✅ 备份完成（共 {total} 个分区）")
                    self.log(f"✅ 备份完成（成功 {success_count} 个）。")
                else:
                    self.progress_label.configure(text=f"⚠️ 备份完成（成功 {success_count}，失败 {fail_count}）")
                    self.log(f"⚠️ 备份完成：成功 {success_count} 个，失败 {fail_count} 个。")
        except Exception as e:
            self.log(f"❌ 备份异常: {e}")
        finally:
            self.after(0, lambda: self._set_working(False))

    def _check_session_threadsafe(self) -> bool:
        """线程安全的会话检查（失败了发消息到主线程弹窗）"""
        if not self.session.is_alive():
            self.after(0, lambda: messagebox.showerror("错误", "会话已断开，请先点击「发送引导」重新连接设备！"))
            return False
        return True

    # ============== 重启设备 ==============

    def reboot_device(self):
        if self.is_working:
            return
        target = self.reboot_var.get()
        cmd_map = {"系统": "reset", "Fastbootd": "reboot-fastboot", "Recovery": "reboot-recovery", "关机": "poweroff"}
        cmd = cmd_map[target]

        if not messagebox.askyesno("确认重启", f"确定要将设备重启到「{target}」吗？"):
            return

        if not self._check_session():
            return

        self.log(f"向 FDL2 会话发送重启命令: {cmd}")
        self._set_working(True)
        threading.Thread(target=self._reboot_thread, args=(cmd, target), daemon=True).start()

    def _reboot_thread(self, cmd: str, target_name: str):
        try:
            success, output = self.session.send_command(cmd, output_callback=self.log)
            if success:
                self.log(f"✅ 已发送 {cmd} 命令，设备正在重启...")
            else:
                self.log(f"⚠️ 命令发送可能未完全成功: {output[:200]}")

            # 重启后设备会断开，清理会话
            self.session.close()
            self.log("💡 设备已重启，会话已断开。如需继续操作，请重新发送引导。")

            # 清空分区列表，回到初始状态
            self.after(0, self._clear_partitions_ui)
            self.after(0, self._reset_progress)
        except Exception as e:
            self.log(f"❌ 重启操作异常: {e}")
        finally:
            self.after(0, lambda: self._set_working(False))

    def _clear_partitions_ui(self):
        """清空分区列表 UI，回到初始状态"""
        for widget in self.partition_scroll.winfo_children():
            widget.destroy()
        self.partition_widgets.clear()
        self.partition_files.clear()
        self.empty_label = ctk.CTkLabel(
            self.partition_scroll,
            text="设备已重启\n请重新发送引导",
            font=("Arial", 14),
            text_color="orange"
        )
        self.empty_label.pack(pady=50)
