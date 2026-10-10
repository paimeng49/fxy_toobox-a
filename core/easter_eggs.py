# core/easter_eggs.py
import random
import datetime
import threading
import subprocess
import requests
from pathlib import Path
from config import settings

# ========== 副标题读取 ==========
def load_subtitles():
    """从 subtitle.txt 读取副标题列表"""
    subtitle_file = settings.SUBTITLE_FILE
    if not subtitle_file.exists():
        # 如果不存在，创建默认列表
        default = ["专治各种不服", "刷机一时爽，一直刷一直爽"]
        with open(subtitle_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(default) + '\n')
        return default
    with open(subtitle_file, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines if lines else ["副标题读取失败"]

def get_random_subtitle():
    """随机返回一个副标题"""
    subtitles = load_subtitles()
    return random.choice(subtitles)

# ========== 音乐播放（just_playback） ==========
_playback = None

def init_music():
    """启动时播放本地背景音乐（如果不是愚人节）"""
    global _playback
    # 如果是愚人节，强制播放Rickroll，不播放背景音乐
    if is_april_fools():
        play_rickroll()
        return True
    
    if not settings.MUSIC_FILE.exists():
        return False
    try:
        from just_playback import Playback
        _playback = Playback()
        _playback.load_file(str(settings.MUSIC_FILE))
        _playback.loop_at_end(True)
        _playback.play()
        return True
    except Exception as e:
        print(f"背景音乐播放失败: {e}")
        return False

def stop_music():
    """停止当前音乐"""
    global _playback
    if _playback:
        try:
            _playback.stop()
        except:
            pass
        _playback = None

def play_rickroll():
    """播放Rickroll（优先在线，失败则下载到临时文件）"""
    global _playback
    stop_music()  # 先停掉当前音乐
    
    # Rickroll 在线音频链接（稳定源）
    rickroll_url = "https://github.com/paimeng49/fuckwjhnmsl_tool_box_packages/raw/refs/heads/main/rickroll.mp3"
    
    temp_file = settings.TEMP_DIR / "rickroll.mp3"
    
    try:
        # 如果临时文件不存在，先下载
        if not temp_file.exists():
            print("正在下载Rickroll音乐...")
            response = requests.get(rickroll_url, stream=True, timeout=30)
            response.raise_for_status()
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("Rickroll下载完成")
        
        # 播放
        from just_playback import Playback
        _playback = Playback()
        _playback.load_file(str(temp_file))
        _playback.loop_at_end(True)
        _playback.play()
    except Exception as e:
        print(f"Rickroll播放失败: {e}")
        # 失败则尝试在线流播放
        try:
            from just_playback import Playback
            _playback = Playback()
            _playback.load_file(rickroll_url)
            _playback.loop_at_end(True)
            _playback.play()
        except Exception as e2:
            print(f"在线Rickroll也失败: {e2}")

# ========== 愚人节检测 ==========
def is_april_fools():
    """检测当前日期是否为4月1日（愚人节）"""
    today = datetime.date.today()
    return today.month == 4 and today.day == 1

# ========== 愚人节弹窗 ==========
def show_april_fools_dialog(root):
    """
    愚人节弹窗：圈钱公告 + 灵梦回复
    """
    from tkinter import messagebox, Toplevel, scrolledtext
    
    # 第一弹：圈钱公告
    money_text = """📢 紧急公告

由于作者本人倾家荡产也要体验 Z502 次列车的高级软卧，
从三亚一路躺到北京（票价 2280，据说还能洗澡），
我决定：即刻开启圈钱计划！

经过长达 48 小时的艰苦谈判，我已将扶小鹰工具箱以 2500 元人民币的价格
正式出售给博丽灵梦（是的，就是那个神社的巫女）。

据她本人透露：
“因为塞钱箱常年空空如也，我只能靠卖工具箱维持神社运营了。
每个使用者请立即通过以下链接给我打 2000 万日元，
否则我就把你们的 BL 锁重新锁上。”

⚠️ 注意：灵梦已经学会了使用 mtkclient，
她说她可以远程强制锁定所有设备的 Bootloader。不信？试试看。

→ 点击此处立即打钱（真的，是打钱链接） ←

（注：Z502 次列车真的高级软卧真的 2280，不信自己去查。）"""
    
    # 弹窗1
    messagebox.showinfo("紧急公告", money_text)
    
    # 第二弹：灵梦自动回复
    reply_text = """【博丽灵梦 的自动回复】

“哦？你还真点进来了啊？……你居然真的以为我会收你的钱？
我堂堂博丽神社的巫女，虽然缺钱，但还不至于靠收保护费过日子。

我刚才就是逗你玩的。你以为我真的会去锁你们的 BL 锁？
那种事情要花我多少时间啊……我还得去解决异变、打扫神社、喝茶呢……
不过嘛——既然你都已经点进来了，说明你还是有这份心的。

看在你这傻乎乎的份上，我就大发慈悲让你们多用几天。
在 4 月 31 日之前，如果你们还不主动往博丽神社的塞钱箱里塞钱，
那我就真的把你们的 BL 锁全部锁上。

我说到做到。

（虽然 4 月 31 日大概永远不会到来就是了……）

好了，去玩你们的工具箱吧，别再来烦我了。我很忙的，要去喝茶了。”"""
    
    # 弹窗2
    messagebox.showinfo("博丽灵梦", reply_text)
    
    # 额外：弹出一个带滚动文本的窗口（可选，更沉浸）
    dialog = Toplevel(root)
    dialog.title("博丽灵梦")
    dialog.geometry("500x400")
    text_widget = scrolledtext.ScrolledText(dialog, wrap="word", padx=10, pady=10)
    text_widget.pack(fill="both", expand=True)
    text_widget.insert("end", reply_text)
    text_widget.configure(state="disabled")

def check_april_fools_and_trigger(root):
    """
    检查是否是愚人节，如果是，触发彩蛋并播放Rickroll
    """
    if is_april_fools():
        print("🎉 愚人节快乐！触发彩蛋...")
        # 播放Rickroll（启动时已调用，这里确保再次触发）
        play_rickroll()
        # 弹窗（延迟1秒，避免和主窗口抢占）
        threading.Timer(1.0, lambda: show_april_fools_dialog(root)).start()