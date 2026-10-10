# main.py
import sys
import os
from pathlib import Path
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