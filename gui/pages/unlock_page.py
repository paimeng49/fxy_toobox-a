# gui/pages/unlock_page.py
import customtkinter as ctk
from tkinter import messagebox
import threading
import queue
import subprocess
import zipfile
import time
from config import settings
from core import mtk_tools
from core.logger import global_logger
from core.spd_tools import SpdSession
from core.device import get_device_mode, run_command
from core.error_watchdog import ErrorWatchdog


class UnlockPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.log_queue = queue.Queue()
        self.spd_session = SpdSession()

        title = ctk.CTkLabel(self, text="🔓 解锁 Bootloader", font=("Arial", 20, "bold"))
        title.pack(pady=15)

        # 方案选择区
        self.select_frame = ctk.CTkFrame(self)
        self.select_frame.pack(fill="x", padx=20, pady=10)

        select_label = ctk.CTkLabel(self.select_frame, text="选择解锁方案：", font=("Arial", 14))
        select_label.pack(side="left", padx=10)

        self.plan_var = ctk.StringVar(value="MTK-G12NL解锁")
        self.plan_menu = ctk.CTkOptionMenu(self.select_frame, values=[
            "MTK-G12NL解锁",
            "MTK通用解锁",
            "展讯强解",
            "展讯公钥解锁",
            "G12NL FRP解锁"
        ], variable=self.plan_var, command=self._on_plan_change)
        self.plan_menu.pack(side="left", padx=10)

        # SOC 型号选择（仅展讯方案显示）
        self.cpu_frame = ctk.CTkFrame(self.select_frame, fg_color="transparent")
        ctk.CTkLabel(self.cpu_frame, text="SOC型号：", font=("Arial", 12)).pack(side="left", padx=5)
        self.cpu_var = ctk.StringVar(value="T606/T616")
        self.cpu_menu = ctk.CTkOptionMenu(self.cpu_frame, values=["T606/T616", "T610/T618"], variable=self.cpu_var)
        self.cpu_menu.pack(side="left", padx=5)
        # 初始不显示
        self.cpu_frame.pack_forget()

        # 执行按钮
        self.execute_btn = ctk.CTkButton(self.select_frame, text="执行", command=self.execute_unlock)
        self.execute_btn.pack(side="left", padx=10)

        # 日志区
        self.log_title = ctk.CTkLabel(self, text="📝 执行日志", font=("Arial", 14, "bold"))
        self.log_title.pack(pady=5)
        self.log_box = ctk.CTkTextbox(self, height=350, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)

        self.after(100, self.poll_queue)

    def _on_plan_change(self, choice):
        """解锁方案切换时，动态显示/隐藏 SOC 下拉框"""
        if choice in ["展讯强解", "展讯公钥解锁"]:
            self.cpu_frame.pack(side="left", padx=10, after=self.plan_menu)
        else:
            self.cpu_frame.pack_forget()

    def log(self, msg, source="解锁"):
        global_logger.log(msg, source)
        try:
            self.log_queue.put_nowait(msg)
        except queue.Full:
            pass

    def _on_watchdog_error(self):
        """错误看门狗触发：解锁按钮并通知用户"""
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("❌❌❌ 检测到错误且操作已停滞！")
        self.log("操作可能已失败，请检查日志获取详细信息")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.after(0, self._unlock_controls)

    def _make_watchdog_log(self):
        """创建一个带错误监控的 log 回调"""
        # 先重置旧的 watchdog，防止残留 timer 误触发
        if hasattr(self, '_watchdog') and self._watchdog:
            self._watchdog.reset()
        self._watchdog = ErrorWatchdog(
            on_error=self._on_watchdog_error,
            on_output=self.log
        )
        return self._watchdog.feed

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
        self.after(100, self.poll_queue)

    def _lock_controls(self):
        self.execute_btn.configure(state="disabled")
        self.plan_menu.configure(state="disabled")
        self.cpu_menu.configure(state="disabled")

    def _unlock_controls(self):
        self.execute_btn.configure(state="normal")
        self.plan_menu.configure(state="normal")
        self.cpu_menu.configure(state="normal")

    def execute_unlock(self):
        plan = self.plan_var.get()
        confirm = messagebox.askyesno("确认", f"确定执行「{plan}」吗？\n此操作可能清除数据，请谨慎！")
        if not confirm:
            return

        self._lock_controls()
        self.log(f"开始执行: {plan}")
        threading.Thread(target=self._run_unlock, args=(plan,), daemon=True).start()

    def _run_unlock(self, plan):
        try:
            watchdog_log = self._make_watchdog_log()
            if plan == "MTK-G12NL解锁":
                self._run_mtk_g12nl_unlock(watchdog_log)
            elif plan == "MTK通用解锁":
                self._run_mtk_unlock(watchdog_log)
            elif plan == "展讯强解":
                self._run_spd_force_unlock(watchdog_log)
            elif plan == "展讯公钥解锁":
                self._run_spd_pubkey_unlock(watchdog_log)
            elif plan == "G12NL FRP解锁":
                self._run_g12nl_frp_unlock(watchdog_log)
        except Exception as e:
            self.log(f"❌ 解锁失败: {e}")
        finally:
            if hasattr(self, '_watchdog'):
                self._watchdog.reset()
            self.after(0, self._unlock_controls)

    # ==================== MTK 解锁 ====================

    def _run_mtk_g12nl_unlock(self, log_cb=None):
        self.log("调用 MTK G12NL 专属解锁脚本...")
        ret, out, err = mtk_tools.run_g12nl_unlock(output_callback=log_cb or self.log)
        if out: self.log(out)
        if err: self.log(err)
        self.log("✅ G12NL 解锁流程执行完成")

    def _run_mtk_unlock(self, log_cb=None):
        self.log("调用 MTK 通用解锁脚本...")
        ret, out, err = mtk_tools.run_mtk_unlock(output_callback=log_cb or self.log)
        if out: self.log(out)
        if err: self.log(err)
        self.log("✅ MTK 通用解锁流程执行完成")

    # ==================== 展讯强解 ====================

    def _run_spd_force_unlock(self, log_cb=None):
        """
        展讯强解完整流程：
        1. 下载对应SOC的解锁工具并解压
        2. 通过内置spddump发送引导，备份splloader/uboot_a/uboot_b
        3. 关机
        4. 提示用户拔掉数据线
        5. 运行解锁脚本bat
        6. 询问是否需要修复（部分机器强解后会黑砖）
        7. 修复：写入splloader到splloader和splloader_bak，写回uboot_a/uboot_b，开机
        """
        log = log_cb or self.log
        cpu_type = self.cpu_var.get()
        tool_config = settings.SPD_UNLOCK_TOOLS.get(cpu_type)
        if not tool_config:
            log(f"❌ 未找到 {cpu_type} 的解锁工具配置")
            return

        # ---- 步骤1：下载解锁工具 ----
        log(f"展讯强解（{cpu_type}）—— 步骤1/4：下载解锁工具...")
        zip_path = settings.TEMP_DIR / f"spd_unlock_{cpu_type.replace('/', '_')}.zip"
        if zip_path.exists() and zip_path.stat().st_size > 0:
            log("工具包已存在，跳过下载")
        else:
            if not self._download_file(tool_config["url"], zip_path):
                log("❌ 解锁工具下载失败")
                return

        # 解压
        log("解压工具包...")
        extract_dir = settings.TEMP_DIR / f"spd_unlock_{cpu_type.replace('/', '_')}"
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
        except Exception as e:
            log(f"❌ 解压失败: {e}")
            return
        log("✅ 工具包解压完成")

        # ---- 步骤2：发送引导 + 备份分区 ----
        log(f"步骤2/4：发送引导并备份分区...")
        log("━━━ 请确保设备已进入深刷模式 ━━━")
        log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")
        log("等待设备进入 FDL2 模式...")

        backup_dir = settings.TEMP_DIR / "spd_backup"
        backup_dir.mkdir(exist_ok=True)

        try:
            output = self.spd_session.start(cpu_type=cpu_type, output_callback=log)
            log("✅ 引导发送成功，已进入 FDL2 模式")
        except Exception as e:
            log(f"❌ 引导失败: {e}")
            log("检查：① 是否进入深刷模式（关机+长按音量减+插USB）；② 是否已安装展讯驱动")
            return

        # 设置备份路径
        success, output = self.spd_session.send_command(
            f'path "{backup_dir}"', output_callback=log
        )
        if not success:
            log("❌ 设置备份路径失败")
            self.spd_session.close()
            return

        # 备份分区
        backup_parts = settings.SPD_BACKUP_PARTITIONS
        backup_success = True
        for part in backup_parts:
            log(f"正在备份分区: {part}")
            success, output = self.spd_session.send_command(f"r {part}", output_callback=log)
            if success:
                log(f"✅ 备份成功: {part}")
            else:
                log(f"❌ 备份失败: {part}")
                backup_success = False
                if "进程未运行" in output:
                    log("❌ 会话已断开，停止备份")
                    break

        if not backup_success:
            log("⚠️ 部分分区备份失败，修复时可能无法完整恢复")

        # ---- 步骤3：关机 ----
        log("步骤3/4：关机...")
        self.spd_session.send_command("poweroff", output_callback=log)
        self.spd_session.close()
        log("✅ 设备已关机")

        # ---- 步骤4：运行解锁脚本 ----
        log("步骤4/4：运行解锁脚本...")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("⚠️ 请现在拔掉数据线！")
        log("然后等待设备完全关机后，重新进入深刷模式")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        bat_name = tool_config["bat_name"]
        bat_full = extract_dir / bat_name
        if not bat_full.exists():
            bat_files = list(extract_dir.rglob("*.bat"))
            if bat_files:
                bat_full = bat_files[0]
                log(f"使用找到的 bat: {bat_full.name}")
            else:
                log(f"❌ 找不到解锁脚本: {bat_name}")
                return

        # 等待用户确认
        if not self._wait_for_confirm(
            "展讯强解",
            "请按以下步骤操作：\n\n"
            "1. 拔掉数据线\n"
            "2. 等待设备完全关机\n"
            "3. 长按音量减不放，插入数据线进入深刷模式\n"
            "4. 点击「确定」开始运行解锁脚本\n\n"
            "⚠️ 解锁脚本运行期间请勿断开数据线！"
        ):
            log("用户取消解锁脚本执行")
            return

        log(f"运行解锁脚本: {bat_full.name}")
        from core.mtk_tools import run_bat
        ret, out, err = run_bat(bat_full, cwd=extract_dir, output_callback=log, auto_enter=True)
        if ret != 0:
            log(f"⚠️ 解锁脚本执行完成（返回码: {ret}）")
        else:
            log("✅ 解锁脚本执行完成")

        # ---- 询问是否修复 ----
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("部分机器强解后可能出现黑砖（无法开机）")
        log("如需修复，工具将写回备份的 splloader 和 uboot")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if not self._wait_for_confirm(
            "修复确认",
            "是否进入修复流程？\n\n"
            "修复将执行以下操作：\n"
            "1. 重新发送引导进入 FDL2\n"
            "2. 将备份的 splloader 写入 splloader 和 splloader_bak\n"
            "3. 将备份的 uboot_a、uboot_b 写回\n"
            "4. 重启设备\n\n"
            "如果设备能正常开机，可以选择「取消」跳过修复。"
        ):
            log("用户跳过修复流程，展讯强解完成")
            return

        self._run_spd_repair(cpu_type, backup_dir, log)

    def _run_spd_repair(self, cpu_type, backup_dir, log=None):
        """展讯强解后的修复流程"""
        log = log or self.log
        log("开始修复流程...")

        # 重新发送引导
        log("重新发送引导进入 FDL2...")
        log("👉 请重新进入深刷模式（关机 + 长按音量减 + 插USB）")
        if not self._wait_for_confirm(
            "修复 - 发送引导",
            "请重新进入深刷模式：\n\n"
            "1. 设备关机\n"
            "2. 长按音量减不放\n"
            "3. 插入数据线\n"
            "4. 点击「确定」发送引导\n\n"
            "等待设备进入 FDL2 模式..."
        ):
            log("用户取消修复")
            return

        try:
            output = self.spd_session.start(cpu_type=cpu_type, output_callback=log)
            log("✅ 引导发送成功")
        except Exception as e:
            log(f"❌ 引导失败: {e}")
            return

        # 写入分区
        repair_map = settings.SPD_REPAIR_PARTITIONS
        for target_part, backup_name in repair_map.items():
            backup_file = backup_dir / f"{backup_name}.bin"
            if not backup_file.exists():
                backup_file = backup_dir / backup_name
            if not backup_file.exists():
                log(f"⚠️ 找不到备份文件: {backup_name}，跳过 {target_part}")
                continue

            log(f"写入 {target_part} ← {backup_file.name}")
            success, output = self.spd_session.send_command(
                f'w {target_part} "{backup_file}"',
                output_callback=log
            )
            if success:
                log(f"✅ 写入成功: {target_part}")
            else:
                log(f"❌ 写入失败: {target_part}")

        # 重启
        log("修复完成，正在重启设备...")
        self.spd_session.send_command("reset", output_callback=log)
        self.spd_session.close()
        log("✅ 修复流程完成，设备正在重启")

    # ==================== 展讯公钥解锁 ====================

    def _run_spd_pubkey_unlock(self, log_cb=None):
        """
        展讯公钥解锁完整流程：
        1. 用户选择SOC，发送引导进入FDL2
        2. reboot-fastboot 进入 fastbootd
        3. fastboot reboot bootloader 重启到 Bootloader
        4. 跑公钥解锁的3个bat（获取解锁码、制作解锁令牌、正式解锁）
        5. fastboot reboot 重启
        """
        log = log_cb or self.log
        cpu_type = self.cpu_var.get()
        log(f"展讯公钥解锁（{cpu_type}）—— 发送引导进入 FDL2...")
        log("━━━ 请确保设备已进入深刷模式 ━━━")
        log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")

        try:
            output = self.spd_session.start(cpu_type=cpu_type, output_callback=log)
            log("✅ 引导发送成功，已进入 FDL2 模式")
        except Exception as e:
            log(f"❌ 引导失败: {e}")
            log("检查：① 是否进入深刷模式（关机+长按音量减+插USB）；② 是否已安装展讯驱动")
            return

        # 进入 fastbootd
        log("发送 reboot-fastboot 命令，进入 fastbootd...")
        success, output = self.spd_session.send_command("reboot-fastboot", output_callback=log)
        if not success:
            log(f"❌ 发送 reboot-fastboot 失败: {output[:200]}")
            self.spd_session.close()
            return
        self.spd_session.close()

        # 等待 fastbootd
        log("等待设备进入 fastbootd...")
        for _ in range(30):
            if get_device_mode() == "fastboot":
                from core.flashing import get_is_userspace
                if get_is_userspace():
                    log("✅ 已进入 fastbootd")
                    break
            time.sleep(2)
        else:
            log("❌ 未检测到 fastbootd 设备")
            return

        # 重启到 Bootloader
        log("重启到 Bootloader（fastboot reboot bootloader）...")
        run_command("fastboot reboot bootloader", cwd=settings.PLATFORM_TOOLS)
        time.sleep(10)

        # 等待 fastboot
        log("等待设备进入 fastboot 模式...")
        for _ in range(30):
            if get_device_mode() == "fastboot":
                log("✅ Fastboot 设备已连接")
                break
            time.sleep(2)
        else:
            log("❌ 未检测到 fastboot 设备")
            return

        # 跑公钥解锁3个bat
        pubkey_dir = settings.PUBKEY_DIR
        for bat_name, step_desc in settings.SPD_PUBKEY_STEPS:
            bat_path = pubkey_dir / bat_name
            if bat_path.exists():
                log(f"{step_desc}: 执行 {bat_name}")
                ret, out, err = mtk_tools.run_bat(
                    bat_path, cwd=pubkey_dir,
                    output_callback=log, auto_enter=True
                )
                if ret != 0:
                    log(f"⚠️ {bat_name} 执行完成（返回码: {ret}）")
                else:
                    log(f"✅ {bat_name} 执行完成")
            else:
                log(f"❌ 找不到 {bat_name}")
                return

        # fastboot reboot 重启
        log("执行 fastboot reboot 重启设备...")
        run_command("fastboot reboot", cwd=settings.PLATFORM_TOOLS)
        log("✅ 展讯公钥解锁流程完成，设备正在重启")

    # ==================== G12NL FRP 解锁 ====================

    def _run_g12nl_frp_unlock(self, log_cb=None):
        log = log_cb or self.log
        log("开始执行 G12NL FRP 解锁...")
        log("请确保平板已进入 BROM 模式")
        log("👉 操作方法：关机状态下，长按音量减不放，同时插入数据线")
        ret, msg = mtk_tools.run_g12nl_frp_unlock(output_callback=log)
        log(msg)
        if ret:
            log("✅ FRP 解锁执行完成")
            log("下一步：请长按电源键手动开机")
        else:
            log("❌ FRP 解锁失败")

    # ==================== 工具方法 ====================

    def _download_file(self, url, save_path):
        """使用全局镜像源下载文件，支持多源切换和重试"""
        import requests as req
        mirror_prefix = settings.get_active_mirror_prefix()
        full_url = mirror_prefix + url if mirror_prefix else url
        mirror_list = list(settings.GSI_MIRRORS.items())
        active = settings.get_active_mirror_prefix()
        mirror_list.sort(key=lambda x: 0 if x[1] == active else 1)

        success = False
        last_error = ""
        for mirror_name, mirror_prefix in mirror_list:
            full_url = mirror_prefix + url if mirror_prefix else url
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
                    success = True
                    break
                except req.exceptions.RequestException as e:
                    last_error = str(e)
                    self.log(f"下载失败（第 {retry + 1} 次）: {e}")
            if success:
                break
            self.log(f"镜像源 {mirror_name} 失败，尝试下一个...")
        return success

    def _wait_for_confirm(self, title, message):
        """在主线程弹确认框，返回用户选择（线程安全）"""
        result_queue = queue.Queue()
        def show_dialog():
            result = messagebox.askyesno(title, message)
            result_queue.put(result)
        self.after(0, show_dialog)
        return result_queue.get()
