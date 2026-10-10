# core/error_watchdog.py
import threading

_ERROR_KEYWORDS = [
    "error", "failed", "fail", "cannot", "can't",
    "unable", "not found", "fatal", "exception",
    "traceback", "denied", "rejected", "timeout",
]

_WATCHDOG_TIMEOUT = 20.0


class ErrorWatchdog:
    """
    输出监控器：检测输出中的错误关键词。
    当检测到错误时，启动 20 秒倒计时；
    如果 20 秒内有新输出，取消倒计时（错误可能是暂时的）；
    如果 20 秒后仍无新输出，判定为真正的错误，触发 on_error 回调。
    """

    def __init__(self, on_error=None, on_output=None):
        self._on_error = on_error
        self._on_output = on_output
        self._timer = None
        self._lock = threading.Lock()
        self._triggered = False
        self._error_detected = False

    def feed(self, line: str):
        """每行输出都经过这里"""
        with self._lock:
            if self._triggered:
                return

            if self._on_output:
                self._on_output(line)

            lower = line.lower()
            has_error = any(kw in lower for kw in _ERROR_KEYWORDS)

            if has_error:
                self._error_detected = True
                if self._timer:
                    self._timer.cancel()
                self._timer = threading.Timer(_WATCHDOG_TIMEOUT, self._fire)
                self._timer.daemon = True
                self._timer.start()
            else:
                if self._error_detected and self._timer:
                    self._timer.cancel()
                    self._timer = None
                    self._error_detected = False

    def _fire(self):
        with self._lock:
            if self._triggered:
                return
            self._triggered = True
        if self._on_error:
            self._on_error()

    def reset(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._triggered = False
            self._error_detected = False
