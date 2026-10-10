@echo off
chcp 65001 >nul
echo 正在安装 mtkclient 依赖库...
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo 安装失败，请手动执行：pip install -r requirements.txt
) else (
    echo 依赖安装完成！
)
pause