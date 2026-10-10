# core/spd_tools.py
import os
import subprocess
import re
import time
import threading
import queue
from config import settings

# 引导配置
SPD_BOOT_CONFIGS = {
    "T606/T616": {
        "exec_addr": "0x65015f08",
        "fdl1_file": "fdl1-dl-9230.bin",
        "fdl1_addr": "0x65000800",
        "fdl2_file": "fdl2-dl-9230.bin",
        "fdl2_addr": "0x9efffe00",
    },
    "T610/T618": {
        "exec_addr": "0x3ee8",
        "fdl1_file": "fdl1-dl-512.bin",
        "fdl1_addr": "0x5500",
        "fdl2_file": "fdl2-dl-512.bin",
        "fdl2_addr": "0x9efffe00",
    }
}

_ERROR_KEYWORDS = ["error", "fail", "failed", "cannot", "can't", "unable", "not found"]

# FDL2 就绪标志（必须检测到这个）
_FDL2_PROMPT = "FDL2 >"
_FDL2_PROMPT_ALT = "FDL2>"

_QUIET_TIMEOUT_AFTER_PROMPT = 3.0   # 检测到提示符后，等待剩余输出（分区列表等）
_QUIET_TIMEOUT_CMD = 10.0          # 命令执行后，等待输出结束


def _is_output_success(output: str) -> bool:
    lower = output.lower()
    for kw in _ERROR_KEYWORDS:
        if kw in lower:
            return False
    return True


def parse_progress(line: str):
    m = re.search(r'(\d+\.\d+)%', line)
    if m:
        return float(m.group(1))
    return None


def _has_fdl2_prompt(text: str) -> bool:
    """检测文本中是否包含 FDL2 > 或 FDL2>"""
    return _FDL2_PROMPT in text or _FDL2_PROMPT_ALT in text


class SpdSession:
    def __init__(self):
        self.proc = None
        self.lock = threading.RLock()
        self._closed = False
        self._reader_thread = None
        self._read_queue: queue.Queue = queue.Queue()

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, cpu_type: str = "T606/T616", output_callback=None) -> str:
        """发送引导，等待完整的 FDL2 > 提示符出现"""
        self.close()
        cfg = SPD_BOOT_CONFIGS.get(cpu_type)
        if not cfg:
            raise ValueError(f"未知的 CPU 型号: {cpu_type}")

        spd_exe_path = str(settings.SPD_DUMP_DIR / "spd_dump.exe")
        cmd_str = (
            f'"{spd_exe_path}" --wait 300 '
            f'exec_addr {cfg["exec_addr"]} '
            f'fdl {cfg["fdl1_file"]} {cfg["fdl1_addr"]} '
            f'fdl {cfg["fdl2_file"]} {cfg["fdl2_addr"]} '
            f'exec'
        )

        print(f"【调试】 cwd: {settings.SPD_DUMP_DIR}")
        print(f"【调试】 cmd: {cmd_str}")

        self.proc = subprocess.Popen(
            cmd_str,
            cwd=str(settings.SPD_DUMP_DIR),
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,  # 无缓冲，确保提示符即时到达
        )
        self._closed = False

        self._read_queue = queue.Queue()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        # 关键：等待 FDL2 > 提示符出现
        output = self._read_until_prompt(timeout=300, output_callback=output_callback)

        if not _has_fdl2_prompt(output):
            self.close()
            raise RuntimeError("引导失败：未检测到 FDL2 >，请检查设备连接和驱动")

        # 检测到提示符后，再读一小段剩余输出（分区列表等）
        remaining = self._read_until_quiet(quiet_timeout=_QUIET_TIMEOUT_AFTER_PROMPT,
                                           output_callback=output_callback,
                                           stop_on_prompt=True)
        output += remaining

        return output

    def _reader_loop(self):
        fd = self.proc.stdout.fileno()
        try:
            while True:
                raw = os.read(fd, 4096)
                if not raw:
                    self._read_queue.put(None)
                    break
                self._read_queue.put(raw)
        except Exception as e:
            print(f"【spd_dump 读取线程异常】 {e}")
            self._read_queue.put(None)

    def _read_until_prompt(self, timeout: int = 300, output_callback=None) -> str:
        """
        读取输出直到出现 FDL2 > 提示符。
        逐字符扫描，不依赖换行。
        """
        output: list[str] = []
        current_line: str = ""
        start_time = time.time()

        while True:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                # 超时，但可能已经积累了一些内容
                if current_line:
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                print("【调试】 等待 FDL2 > 超时")
                break

            try:
                raw = self._read_queue.get(timeout=remaining)
            except queue.Empty:
                if current_line:
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                print("【调试】 等待 FDL2 > 超时")
                break

            if raw is None:
                if current_line:
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                break

            text = raw.decode('utf-8', errors='replace')

            for ch in text:
                current_line += ch
                if ch == '\n':
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                    current_line = ""

                # 实时检测 FDL2 >
                if _has_fdl2_prompt(current_line):
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                    print("【调试】 检测到 FDL2 >")
                    return "".join(output)

        return "".join(output)

    def _read_until_quiet(self, quiet_timeout: float = 5.0, output_callback=None,
                          stop_on_prompt: bool = True) -> str:
        """
        读取输出直到：
        - 检测到 FDL2 > （如果 stop_on_prompt=True）
        - 或者空闲超时
        - 或者 EOF
        """
        output: list[str] = []
        current_line: str = ""
        start_time = time.time()

        while True:
            # 如果已经检测到 FDL2 >，再等待一小段剩余输出（如分区列表），然后结束
            if stop_on_prompt and _has_fdl2_prompt("".join(output)):
                # 再读一小段，让分区列表完整
                try:
                    raw = self._read_queue.get(timeout=quiet_timeout)
                except queue.Empty:
                    break
                if raw is None:
                    break
                text = raw.decode('utf-8', errors='replace')
                for ch in text:
                    current_line += ch
                    if ch == '\n':
                        output.append(current_line)
                        print(f"【spd_dump输出】 {current_line.rstrip()}")
                        if output_callback:
                            output_callback(current_line.rstrip())
                        current_line = ""
                continue

            try:
                raw = self._read_queue.get(timeout=quiet_timeout)
            except queue.Empty:
                # 静默超时，结束
                if current_line:
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                print("【调试】 静默超时，判定输出结束")
                break

            if raw is None:
                if current_line:
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                print("【调试】 EOF")
                break

            text = raw.decode('utf-8', errors='replace')

            for ch in text:
                current_line += ch
                if ch == '\n':
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                    current_line = ""

                if _has_fdl2_prompt(current_line):
                    output.append(current_line)
                    print(f"【spd_dump输出】 {current_line.rstrip()}")
                    if output_callback:
                        output_callback(current_line.rstrip())
                    # 已经检测到提示符，继续收集剩余分区列表（如果有），直到静默
                    # 这里不立即返回，而是切换到静默模式等待剩余输出
                    # 但为了简化，直接返回当前内容，让调用方再读一次
                    # 这里我们直接返回，因为调用方已经知道有提示符了
                    return "".join(output)

        return "".join(output)

    def send_command(self, cmd: str, timeout: int = 1200, output_callback=None):
        """向 FDL2 会话发送命令，读取结果直到出现 FDL2 > 提示符"""
        if not self.is_alive():
            self.proc = None
            return False, "进程未运行或已退出"

        with self.lock:
            try:
                print(f"【调试】 发送命令: {cmd}")
                self.proc.stdin.write((cmd + "\n").encode('utf-8'))
                self.proc.stdin.flush()

                output = self._read_until_prompt(timeout=timeout,
                                                 output_callback=output_callback)
                success = _is_output_success(output)
                return success, output
            except Exception as e:
                return False, f"发送命令失败: {e}"

    def close(self):
        if self._closed:
            return
        self._closed = True

        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    try:
                        self.proc.stdin.write(b"poweroff\n")
                        self.proc.stdin.flush()
                        time.sleep(0.5)
                    except Exception:
                        pass
            finally:
                if self.proc.poll() is None:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    pass
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
                try:
                    self.proc.stdout.close()
                except Exception:
                    pass
                self.proc = None


def parse_spd_partitions(output_text: str) -> list[dict]:
    partitions: list[dict] = []
    pattern = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\S+)\s*$")
    lines = output_text.splitlines()
    in_partition_list = False

    for line in lines:
        stripped = line.strip()
        if "Reading Partition List" in stripped or "dump_partition" in stripped:
            in_partition_list = True
            continue

        if in_partition_list:
            match = pattern.match(line)
            if match:
                name = match.group(2)
                size = match.group(3)
                partitions.append({"name": name, "size": size})
            elif (stripped.startswith("standard gpt table")
                  or stripped.startswith("skip saving")
                  or stripped.startswith("partition list saved")
                  or stripped.startswith("Total number")):
                break
    return partitions