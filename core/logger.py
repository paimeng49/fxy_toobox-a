# core/logger.py
import time
import threading
from pathlib import Path
from config import settings

# 单个日志文件最大大小（10MB），超过就新建
_MAX_LOG_SIZE = 10 * 1024 * 1024
# 最多保留多少个日志文件
_MAX_LOG_FILES = 20


class GlobalLogger:
    """
    全局日志管理器：
    - 统一收集各个模块的日志输出
    - 自动添加时间戳
    - 可选择是否自动保存为 .log 文件
    - 线程安全（所有页面都能并发调用）
    - 日志文件大小限制 + 自动轮转
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.log_dir = settings.BASE_DIR / "logs"
        self.log_dir.mkdir(exist_ok=True)
        # 默认保存所有日志（可通过主界面切换）
        self.auto_save = True
        self.current_log_file = None  # 当前日志文件路径
        self._file_handle = None      # 保持文件句柄打开，避免频繁 IO
        self._current_size = 0        # 当前文件已写入字节数
        self._open_log_file()

    def _open_log_file(self):
        """根据当前日期时间创建新的日志文件"""
        self._close_file_handle()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.current_log_file = self.log_dir / f"toolbox_{timestamp}.log"
        self._file_handle = open(self.current_log_file, 'a', encoding='utf-8', buffering=8192)
        self._current_size = 0
        # 写入文件头
        header = f"===== 扶小鹰工具箱日志启动于 {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
        self._file_handle.write(header)
        self._file_handle.flush()
        self._current_size += len(header.encode('utf-8'))
        # 清理旧日志
        self._cleanup_old_logs()

    def _close_file_handle(self):
        """安全关闭当前文件句柄"""
        if self._file_handle:
            try:
                self._file_handle.flush()
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

    def _cleanup_old_logs(self):
        """清理旧日志文件，只保留最新的 _MAX_LOG_FILES 个"""
        try:
            log_files = sorted(
                self.log_dir.glob("toolbox_*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if len(log_files) > _MAX_LOG_FILES:
                for old_file in log_files[_MAX_LOG_FILES:]:
                    try:
                        old_file.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def _write_to_file(self, msg):
        """安全写入日志文件（保持句柄打开，性能更好）"""
        if not self.auto_save or not self._file_handle:
            return
        try:
            line = msg + "\n"
            self._file_handle.write(line)
            self._file_handle.flush()
            self._current_size += len(line.encode('utf-8'))

            # 超过大小限制，新建日志文件
            if self._current_size >= _MAX_LOG_SIZE:
                self._open_log_file()
        except Exception as e:
            # 写入失败不要打断主程序
            print(f"【日志文件写入失败】 {e}")

    def log(self, message, source="通用"):
        """
        统一日志接口
        :param message: 日志内容
        :param source: 来源模块（如"Fastboot"、"展讯"、"解锁"等）
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{source}] {message}"

        # 1. 实时打印到终端（用于调试）
        print(log_line)

        # 2. 写入 .log 文件（线程安全）
        with self.lock:
            self._write_to_file(log_line)

    def set_auto_save(self, enabled: bool):
        """主界面调用：开启/关闭自动保存到文件"""
        with self.lock:
            self.auto_save = enabled
        print(f"【日志保存已{'开启' if enabled else '关闭'}】")

    def get_current_log_path(self):
        """返回当前日志文件路径（用于主界面显示）"""
        return str(self.current_log_file)

    def close(self):
        """程序退出时调用，安全关闭文件"""
        with self.lock:
            self._close_file_handle()


# 全局单例（所有模块 import 这个实例使用）
global_logger = GlobalLogger()
