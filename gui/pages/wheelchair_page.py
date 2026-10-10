# gui/pages/wheelchair_page.py
import customtkinter as ctk
from tkinter import messagebox
import threading
import queue
import subprocess
import time
from config import settings
from core.gsi_download import download_gsi_with_progress
from core import mtk_tools
from core.flashing import unified_flash, get_is_userspace, check_fastboot_unlocked
from core.device import get_device_mode, run_command
from core.spd_tools import SpdSession

# 文件对话框：优先使用 CTKFileDialog-plus，没装就退回原生
try:
    from CTkFileDialog import askopenfilename as _ctk_askopenfilename
    _USE_CTK_DIALOG = True
except ImportError:
    _USE_CTK_DIALOG = False


def _ask_open_file(title, filetypes, parent=None):
    if _USE_CTK_DIALOG:
        return _ctk_askopenfilename(title=title, filetypes=filetypes, autocomplete=True)
    else:
        from tkinter import filedialog
        return filedialog.askopenfilename(title=title, filetypes=filetypes, parent=parent)


class WheelchairPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue(maxsize=500)
        self.is_flashing = False
        self.spd_session = SpdSession()
        self.manual_img_path = None

        title = ctk.CTkLabel(self, text="🚀 一键刷机", font=("Arial", 20, "bold"))
        title.pack(pady=10)

        # 选择区
        self.select_frame = ctk.CTkFrame(self)
        self.select_frame.pack(fill="x", padx=20, pady=10)

        self.unlock_frame = ctk.CTkFrame(self.select_frame)
        self.unlock_frame.pack(side="left", padx=10, pady=10, fill="both", expand=True)

        ctk.CTkLabel(self.unlock_frame, text="选择解锁方案：", font=("Arial", 14, "bold")).pack(pady=5)
        self.unlock_var = ctk.StringVar(value="MTK通用解锁")
        self.unlock_menu = ctk.CTkOptionMenu(
            self.unlock_frame,
            values=["MTK-G12NL解锁", "MTK通用解锁", "展讯强解", "展讯公钥解锁", "G12NL FRP解锁"],
            variable=self.unlock_var,
            command=self._on_unlock_plan_change
        )
        self.unlock_menu.pack(fill="x", padx=10, pady=5)

        # 展讯 CPU 型号选择（默认隐藏）
        self.spd_cpu_frame = ctk.CTkFrame(self.unlock_frame, fg_color="transparent")
        ctk.CTkLabel(self.spd_cpu_frame, text="展讯 CPU 型号：", font=("Arial", 12)).pack(side="left", padx=5)
        self.spd_cpu_var = ctk.StringVar(value="T606/T616")
        self.spd_cpu_menu = ctk.CTkOptionMenu(self.spd_cpu_frame, values=["T606/T616", "T610/T618"], variable=self.spd_cpu_var)
        self.spd_cpu_menu.pack(side="left", padx=5)
        self.spd_cpu_frame.pack_forget()

        self.gsi_frame = ctk.CTkFrame(self.select_frame)
        self.gsi_frame.pack(side="right", padx=10, pady=10, fill="both", expand=True)

        ctk.CTkLabel(self.gsi_frame, text="选择GSI镜像：", font=("Arial", 14, "bold")).pack(pady=5)
        self.gsi_var = ctk.StringVar(value=list(settings.GSI_PRESETS.keys())[0])
        self.gsi_menu = ctk.CTkOptionMenu(self.gsi_frame, values=list(settings.GSI_PRESETS.keys()), variable=self.gsi_var)
        self.gsi_menu.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(self.gsi_frame, text="镜像源已在「综合」页面全局设置", font=("Arial", 12), text_color="gray").pack(pady=5)

        self.manual_btn = ctk.CTkButton(self.gsi_frame, text="手动选择system.img", command=self.manual_select_img)
        self.manual_btn.pack(fill="x", padx=10, pady=5)

        self.start_btn = ctk.CTkButton(self, text="🚀 开始刷机", font=("Arial", 16, "bold"), fg_color="green", command=self.start_flash)
        self.start_btn.pack(pady=10)
        # 小游戏按钮
        self.minigame_btn = ctk.CTkButton(
            self, text="无聊吗？来玩玩小游戏吧", fg_color="purple",
            command=self.launch_minigame
        )
        self.minigame_btn.pack(pady=10)

        self.progress_label = ctk.CTkLabel(self, text="准备就绪", font=("Arial", 12))
        self.progress_label.pack(pady=2)
        self.progress_bar = ctk.CTkProgressBar(self, height=15)
        self.progress_bar.pack(fill="x", padx=20, pady=5)
        self.progress_bar.set(0)

        self.log_title = ctk.CTkLabel(self, text="📝 执行日志", font=("Arial", 14, "bold"))
        self.log_title.pack(pady=5)
        self.log_box = ctk.CTkTextbox(self, height=250, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)

        self.after(100, self.poll_queue)

    def _on_unlock_plan_change(self, choice):
        """解锁方案切换时，动态显示/隐藏展讯CPU下拉框"""
        if choice in ["展讯强解", "展讯公钥解锁"]:
            self.spd_cpu_frame.pack(fill="x", padx=10, pady=5, after=self.unlock_menu)
        else:
            self.spd_cpu_frame.pack_forget()

    def log(self, msg, source="一键刷机"):
        from core.logger import global_logger
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
        try:
            line_count = int(self.log_box.index("end-1c").split(".")[0])
            if line_count > 500:
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", f"{line_count - 500}.0")
                self.log_box.configure(state="disabled")
        except Exception:
            pass
        self.after(100, self.poll_queue)

    def manual_select_img(self):
        file = _ask_open_file(
            title="选择system.img",
            filetypes=[("镜像文件", "*.img"), ("所有文件", "*.*")],
            parent=self.winfo_toplevel()
        )
        if file:
            self.gsi_var.set("手动选择")
            self.manual_img_path = file
            self.log(f"已手动选择: {file}")

    def _lock_all(self):
        """锁定本页面所有控件 + 通知主窗口锁定其他页面"""
        self.is_flashing = True
        self.start_btn.configure(state="disabled")
        self.unlock_menu.configure(state="disabled")
        self.gsi_menu.configure(state="disabled")
        self.manual_btn.configure(state="disabled")
        self.spd_cpu_menu.configure(state="disabled")
        # 通知主窗口锁定导航
        parent = self.master
        if hasattr(parent, 'lock_navigation'):
            parent.lock_navigation()

    def _unlock_all(self):
        """解锁本页面所有控件 + 通知主窗口解锁导航"""
        self.is_flashing = False
        self.start_btn.configure(state="normal")
        self.unlock_menu.configure(state="normal")
        self.gsi_menu.configure(state="normal")
        self.manual_btn.configure(state="normal")
        self.spd_cpu_menu.configure(state="normal")
        parent = self.master
        if hasattr(parent, 'unlock_navigation'):
            parent.unlock_navigation()

    def _update_progress(self, percent, text, speed=None, eta=None):
        self.progress_bar.set(percent / 100)
        if speed is not None and eta is not None:
            self.progress_label.configure(text=f"{text} | 速度: {speed:.1f} MB/s | 剩余: {int(eta)}秒")
        else:
            self.progress_label.configure(text=text)

    def _wait_for_confirm(self, title, message):
        """在主线程弹确认框，返回用户选择（线程安全）"""
        result_queue = queue.Queue()
        def show_dialog():
            result = messagebox.askyesno(title, message)
            result_queue.put(result)
        self.after(0, show_dialog)
        return result_queue.get()

    def _wait_adb_open(self):
        """
        提示用户连点30次序列号出现Open，然后检测ADB
        注意：出现Open后ADB已直接激活，无需打开开发者选项或USB调试
        """
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("请在设备上操作：")
        self.log("  进入设置 → 连续点击「序列号」30次")
        self.log("  （注意：是序列号，不是版本号！）")
        self.log("  直到设备显示「Open」字样")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("⚠️ 出现Open后ADB已直接激活，无需打开开发者选项！")
        self.log("⚠️ 无需打开USB调试！直接连接电脑即可！")

        confirmed = self._wait_for_confirm(
            "操作确认",
            "请在设备上连续点击「序列号」30次，直至出现「Open」字样\n\n"
            "注意：\n"
            "• 是序列号，不是版本号\n"
            "• 出现Open后ADB已直接激活\n"
            "• 无需打开开发者选项\n"
            "• 无需打开USB调试\n\n"
            "出现Open后，将设备连接到电脑，点击「确定」开始检测ADB"
        )
        if not confirmed:
            self.log("用户取消操作")
            return False

        self.log("开始检测ADB设备...")
        for _ in range(30):
            if get_device_mode() == "adb":
                self.log("✅ ADB 设备已连接")
                return True
            time.sleep(2)
        self.log("❌ 未检测到ADB设备，请检查连接")
        return False

    def start_flash(self):
        if self.is_flashing:
            return

        unlock_plan = self.unlock_var.get()
        gsi_name = self.gsi_var.get()

        warning_text = (
            "⚠️ 关于 GSI 安卓版本选择的郑重提醒\n\n"
            "为确保设备的最佳兼容性与稳定性，我们强烈建议您选择\n"
            "与设备当前原厂系统相同安卓版本的 GSI 镜像进行刷入。\n\n"
            "选择与出厂版本相同安卓版本的 GSI，是降低兼容性问题概率的最稳妥方案。\n"
            "然而，即便刷入同版本 GSI，也可能因硬件驱动差异、分区结构不同\n"
            "或 GSI 本身的适配问题，出现以下但不限于的异常情况：\n"
            " - 无法正常开机或卡在第一屏\n"
            " - 相机、指纹、蓝牙等硬件功能失效\n"
            " - 无法播放视频或出现图形渲染异常\n"
            " - 系统应用频繁闪退或无法使用\n"
            "若选择刷入更高版本的 GSI（例如在 Android 12 的设备上刷入 Android 13），\n"
            "以上问题出现的概率会显著增加\n\n"
            "⚠️ 绝对禁止刷入比原厂系统安卓版本更低的 GSI\n"
            "（例如在 Android 13 的设备上刷入 Android 12 或更低版本）。\n"
            "此类操作将导致设备 100% 无法开机，且无法通过常规手段恢复。\n\n"
            "请确认设备型号和当前版本后再继续！"
        )

        if not messagebox.askokcancel("风险提示", warning_text):
            return

        self._lock_all()
        self.log(f"开始刷机：GSI={gsi_name}, 解锁={unlock_plan}")
        threading.Thread(target=self._flash_process, args=(gsi_name, unlock_plan), daemon=True).start()

    def _flash_process(self, gsi_name, unlock_plan):
        try:
            # ============ 1. 获取GSI ============
            if gsi_name == "手动选择" and self.manual_img_path:
                gsi_path = self.manual_img_path
            else:
                gsi_info = settings.GSI_PRESETS.get(gsi_name)
                if not gsi_info:
                    self.log("❌ 无效的GSI选择")
                    return
                mirror_prefix = settings.get_active_mirror_prefix()
                self.log(f"开始下载GSI: {gsi_name} (镜像源: {settings.ACTIVE_MIRROR})")
                def progress_cb(percent, text, speed, eta):
                    self.after(0, self._update_progress, percent, text, speed, eta)
                success, result = download_gsi_with_progress(gsi_info["url"], mirror_prefix, progress_cb)
                if not success:
                    self.log(f"❌ GSI下载失败: {result}")
                    return
                gsi_path = result
            self.log(f"✅ GSI准备完成: {gsi_path}")

            # ============ 2. 执行解锁 ============
            self.log("开始执行解锁...")

            if unlock_plan == "MTK-G12NL解锁":
                if not self._unlock_mtk_g12nl():
                    return
                if not self._enter_fbd_from_adb():
                    return

            elif unlock_plan == "MTK通用解锁":
                if not self._unlock_mtk_generic():
                    return
                if not self._enter_fbd_from_adb():
                    return

            elif unlock_plan == "G12NL FRP解锁":
                if not self._unlock_g12nl_frp():
                    return
                if not self._enter_fbd_from_frp():
                    return

            elif unlock_plan == "展讯强解":
                if not self._unlock_spd_force():
                    return
                if not self._enter_fbd_from_spd():
                    return

            elif unlock_plan == "展讯公钥解锁":
                if not self._unlock_spd_pubkey():
                    return
                if not self._enter_fbd_from_spd_pubkey():
                    return

            # ============ 3. 统一刷机流程（从fbd开始）============
            self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log("进入统一刷机流程...")
            self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # 检查解锁状态
            self.log("检查设备解锁状态...")
            unlocked = check_fastboot_unlocked()
            if unlocked is True:
                self.log("✅ 设备已解锁 BL")
            elif unlocked is False:
                self.log("❌ 设备未解锁 BL！无法继续刷机")
                return
            else:
                self.log("⚠️ 无法自动检测解锁状态")
                confirmed = self._wait_for_confirm(
                    "解锁确认",
                    "无法自动检测设备的解锁状态。\n\n"
                    "请确认设备 BL 已解锁：\n"
                    "• 解锁方案是否已执行完成？\n"
                    "• 设备是否已进入 fastbootd？\n\n"
                    "点击「确定」继续刷机，点击「取消」中止"
                )
                if not confirmed:
                    self.log("用户取消刷机")
                    return

            def flash_progress(pct, text):
                self.after(0, lambda v=pct, t=text: self._update_progress(v, t))

            success = unified_flash(
                gsi_path,
                is_spd=(unlock_plan in ["展讯强解", "展讯公钥解锁"]),
                log_callback=self.log,
                progress_callback=flash_progress,
                check_unlocked=False
            )
            if success:
                self.log("🎉 刷机流程完成！")
            else:
                self.log("❌ 刷机流程失败")

        except Exception as e:
            self.log(f"❌ 刷机失败: {e}")
        finally:
            self.after(0, self._unlock_all)

    # ==================== 解锁方法 ====================

    def _unlock_mtk_g12nl(self):
        """MTK G12NL 解锁"""
        self.log("调用G12NL解锁脚本...")
        self.log("👉 请确保设备已进入 BROM 模式")
        self.log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")
        ret, out, err = mtk_tools.run_g12nl_unlock(output_callback=self.log)
        if out: self.log(out)
        if err: self.log(err)
        self.log("✅ 解锁命令已执行完成")
        return True

    def _unlock_mtk_generic(self):
        """MTK 通用解锁"""
        self.log("调用MTK通用解锁脚本...")
        self.log("👉 请确保设备已进入 BROM 模式")
        self.log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")
        ret, out, err = mtk_tools.run_mtk_unlock(output_callback=self.log)
        if out: self.log(out)
        if err: self.log(err)
        if ret != 0:
            self.log(f"❌ MTK通用解锁失败（返回码: {ret}）")
            return False
        self.log("✅ MTK通用解锁完成")
        return True

    def _unlock_g12nl_frp(self):
        """G12NL FRP 解锁"""
        self.log("开始执行 G12NL FRP 解锁...")
        self.log("👉 请确保设备已进入 BROM 模式")
        self.log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")
        ret, msg = mtk_tools.run_g12nl_frp_unlock(output_callback=self.log)
        self.log(msg)
        if not ret:
            self.log("❌ FRP 解锁失败")
            return False
        self.log("✅ FRP 解锁完成")
        return True

    def _unlock_spd_force(self):
        """展讯强解（一键刷机版：只执行解锁脚本，不备份/修复）"""
        cpu_type = self.spd_cpu_var.get()
        self.log(f"展讯强解（{cpu_type}）—— 下载并运行解锁工具...")

        # 下载工具
        tool_config = settings.SPD_UNLOCK_TOOLS.get(cpu_type)
        if not tool_config:
            self.log(f"❌ 未找到 {cpu_type} 的解锁工具配置")
            return False

        zip_path = settings.TEMP_DIR / f"spd_unlock_{cpu_type.replace('/', '_')}.zip"
        if not (zip_path.exists() and zip_path.stat().st_size > 0):
            if not self._download_spd_tool(tool_config["url"], zip_path):
                self.log("❌ 解锁工具下载失败")
                return False
        else:
            self.log("工具包已存在，跳过下载")

        # 解压
        extract_dir = settings.TEMP_DIR / f"spd_unlock_{cpu_type.replace('/', '_')}"
        import zipfile
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
        except Exception as e:
            self.log(f"❌ 解压失败: {e}")
            return False

        # 运行解锁脚本
        bat_name = tool_config["bat_name"]
        bat_full = extract_dir / bat_name
        if not bat_full.exists():
            bat_files = list(extract_dir.rglob("*.bat"))
            if bat_files:
                bat_full = bat_files[0]
            else:
                self.log(f"❌ 找不到解锁脚本: {bat_name}")
                return False

        self.log(f"运行解锁脚本: {bat_full.name}")
        ret, out, err = mtk_tools.run_bat(bat_full, cwd=extract_dir, output_callback=self.log, auto_enter=True)
        if ret != 0:
            self.log(f"⚠️ 解锁脚本执行完成（返回码: {ret}）")
        else:
            self.log("✅ 解锁脚本执行完成")
        return True

    def _unlock_spd_pubkey(self):
        """展讯公钥解锁"""
        cpu_type = self.spd_cpu_var.get()
        self.log(f"展讯公钥解锁（{cpu_type}）—— 发送引导进入FDL2...")
        self.log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")

        try:
            output = self.spd_session.start(cpu_type=cpu_type, output_callback=self.log)
            self.log("✅ 引导发送成功")
        except Exception as e:
            self.log(f"❌ 引导失败: {e}")
            return False

        # reboot-fastboot
        self.log("发送 reboot-fastboot 进入 fastbootd...")
        success, output = self.spd_session.send_command("reboot-fastboot", output_callback=self.log)
        if not success:
            self.log(f"❌ 发送 reboot-fastboot 失败")
            self.spd_session.close()
            return False
        self.spd_session.close()
        time.sleep(10)

        # 等待 fastbootd
        self.log("等待 fastbootd...")
        for _ in range(30):
            if get_device_mode() == "fastboot" and get_is_userspace():
                self.log("✅ Fastbootd 已连接")
                break
            time.sleep(2)
        else:
            self.log("❌ 未检测到 fastbootd")
            return False

        # reboot bootloader
        self.log("重启到 Bootloader...")
        run_command("fastboot reboot bootloader", cwd=settings.PLATFORM_TOOLS)
        time.sleep(10)

        # 等待 fastboot
        self.log("等待 fastboot...")
        for _ in range(30):
            if get_device_mode() == "fastboot":
                self.log("✅ Fastboot 已连接")
                break
            time.sleep(2)
        else:
            self.log("❌ 未检测到 fastboot")
            return False

        # 跑3个bat
        pubkey_dir = settings.PUBKEY_DIR
        for bat_name, step_desc in settings.SPD_PUBKEY_STEPS:
            bat_path = pubkey_dir / bat_name
            if bat_path.exists():
                self.log(f"{step_desc}: 执行 {bat_name}")
                ret, out, err = mtk_tools.run_bat(bat_path, cwd=pubkey_dir, output_callback=self.log, auto_enter=True)
                if ret != 0:
                    self.log(f"⚠️ {bat_name} 执行完成（返回码: {ret}）")
                else:
                    self.log(f"✅ {bat_name} 执行完成")
            else:
                self.log(f"❌ 找不到 {bat_name}")
                return False

        return True

    # ==================== 进入 fbd 的方法 ====================

    def _enter_fbd_from_adb(self):
        """MTK强解后：连点30次序列号→open→检测ADB→adb reboot fastboot→fbd"""
        if not self._wait_adb_open():
            return False
        self.log("正在重启到 fastbootd (adb reboot fastboot)...")
        subprocess.run("adb reboot fastboot", cwd=settings.PLATFORM_TOOLS, shell=True)
        time.sleep(10)
        for _ in range(30):
            if get_device_mode() == "fastboot":
                if get_is_userspace():
                    self.log("✅ Fastbootd 已连接")
                    return True
            time.sleep(2)
        self.log("❌ 未检测到 fastbootd")
        return False

    def _enter_fbd_from_frp(self):
        """改FRP后：连点30次序列号→open→检测ADB→adb reboot bootloader→fastboot flashing unlock→fastboot reboot fastboot→fbd"""
        if not self._wait_adb_open():
            return False
        self.log("正在重启到 bootloader (adb reboot bootloader)...")
        subprocess.run("adb reboot bootloader", cwd=settings.PLATFORM_TOOLS, shell=True)
        time.sleep(10)

        # 等待 fastboot
        self.log("等待 fastboot...")
        for _ in range(15):
            if get_device_mode() == "fastboot":
                self.log("✅ Fastboot 已连接")
                break
            time.sleep(2)
        else:
            self.log("❌ 未检测到 fastboot")
            return False

        # fastboot flashing unlock
        self.log("执行 fastboot flashing unlock ...")
        result = subprocess.run(
            "fastboot flashing unlock",
            cwd=settings.PLATFORM_TOOLS, shell=True,
            capture_output=True, text=True
        )
        if result.returncode == 0:
            self.log("✅ 解锁成功")
        else:
            self.log(f"❌ 解锁失败: {result.stderr}")
            return False

        # fastboot reboot fastboot
        self.log("重启到 fastbootd (fastboot reboot fastboot)...")
        run_command("fastboot reboot fastboot", cwd=settings.PLATFORM_TOOLS)
        time.sleep(10)
        for _ in range(30):
            if get_device_mode() == "fastboot" and get_is_userspace():
                self.log("✅ Fastbootd 已连接")
                return True
            time.sleep(2)
        self.log("❌ 未检测到 fastbootd")
        return False

    def _enter_fbd_from_spd(self):
        """展讯强解后：重新关机进入FDL2→reboot-fastboot→fbd"""
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("展讯强解完成，需要重新进入 FDL2 模式")
        self.log("👉 请将设备关机")
        self.log("👉 然后长按音量减不放，插入数据线进入深刷模式")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        cpu_type = self.spd_cpu_var.get()
        confirmed = self._wait_for_confirm(
            "进入FDL2",
            "请将设备关机后重新进入深刷模式：\n\n"
            "1. 长按电源键关机\n"
            "2. 长按音量减不放\n"
            "3. 插入数据线\n"
            "4. 点击「确定」发送引导\n\n"
            "等待设备进入 FDL2 模式..."
        )
        if not confirmed:
            self.log("用户取消")
            return False

        try:
            output = self.spd_session.start(cpu_type=cpu_type, output_callback=self.log)
            self.log("✅ 引导发送成功")
        except Exception as e:
            self.log(f"❌ 引导失败: {e}")
            return False

        self.log("发送 reboot-fastboot 进入 fastbootd...")
        success, output = self.spd_session.send_command("reboot-fastboot", output_callback=self.log)
        if not success:
            self.log("❌ 发送 reboot-fastboot 失败")
            self.spd_session.close()
            return False
        self.spd_session.close()
        time.sleep(10)

        self.log("等待 fastbootd...")
        for _ in range(30):
            if get_device_mode() == "fastboot" and get_is_userspace():
                self.log("✅ Fastbootd 已连接")
                return True
            time.sleep(2)
        self.log("❌ 未检测到 fastbootd")
        return False

    def _enter_fbd_from_spd_pubkey(self):
        """展讯公钥解锁后已经处于 fastboot，直接切到 fastbootd"""
        self.log("公钥解锁完成，正在切换到 fastbootd...")
        # 此时设备在 fastboot 模式
        if get_is_userspace():
            self.log("✅ 设备已在 fastbootd 模式")
            return True

        self.log("切换到 fastbootd (fastboot reboot fastboot)...")
        run_command("fastboot reboot fastboot", cwd=settings.PLATFORM_TOOLS)
        time.sleep(10)
        for _ in range(30):
            if get_device_mode() == "fastboot" and get_is_userspace():
                self.log("✅ Fastbootd 已连接")
                return True
            time.sleep(2)
        self.log("❌ 未检测到 fastbootd")
        return False

    # ==================== 工具方法 ====================

    def _download_spd_tool(self, url, save_path):
        """下载展讯解锁工具"""
        import requests as req
        mirror_prefix = settings.get_active_mirror_prefix()
        mirror_list = list(settings.GSI_MIRRORS.items())
        active = settings.get_active_mirror_prefix()
        mirror_list.sort(key=lambda x: 0 if x[1] == active else 1)

        for mirror_name, mp in mirror_list:
            full_url = mp + url if mp else url
            self.log(f"使用镜像源: {mirror_name}")
            for retry in range(3):
                if retry > 0:
                    self.log(f"第 {retry + 1} 次重试...")
                    time.sleep(2 ** retry)
                try:
                    response = req.get(full_url, stream=True, timeout=30)
                    response.raise_for_status()
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    pct = downloaded / total_size * 100
                                    if int(pct) % 10 == 0:
                                        self.log(f"下载进度: {pct:.0f}%")
                    return True
                except req.exceptions.RequestException as e:
                    self.log(f"下载失败（第 {retry + 1} 次）: {e}")
            self.log(f"镜像源 {mirror_name} 失败，尝试下一个...")
        return False

    def launch_minigame(self):
        self.log("正在启动植物大战僵尸，请稍候...")
        threading.Thread(target=self._launch_minigame_thread, daemon=True).start()

    def _launch_minigame_thread(self):
        from core.game_download import launch_pvz
        try:
            launch_pvz(log_callback=self.log)
            self.log("植物大战僵尸已启动！")
        except Exception as e:
            self.log(f"启动失败: {e}")
