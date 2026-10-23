# main.py
import sys
import os
from pathlib import Path

# 强制把 Python 进程的 cwd 设为项目根目录。
# mono 的 PTY 终端会继承这个 cwd，这样用户打开终端就直接在工具箱目录里了，
# 不需要再用 run_command 去调用 cd（run_command 在连续调用时有命令拼接 bug）。
os.chdir(str(Path(__file__).resolve().parent))

sys.path.insert(0, str(Path(__file__).parent))

from gui.main_window import MainWindow
from core.easter_eggs import init_music, is_april_fools, check_april_fools_and_trigger
from core.logger import global_logger

def main():
    global_logger.log("程序启动，开始初始化...", source="Main")

    # 启动时初始化音乐（背景音乐，愚人节则播放Rickroll）
    init_music()

    app = MainWindow()

    # 如果是愚人节，延迟触发彩蛋弹窗
    if is_april_fools():
        check_april_fools_and_trigger(app)

    app.mainloop()

if __name__ == "__main__":
    main()
