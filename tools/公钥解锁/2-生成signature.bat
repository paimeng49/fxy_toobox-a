@ECHO OFF
cd /d %~dp0
if exist bin (cd bin) else (EXIT)
set path=%cd%;%path%
::将当前目录加入环境变量, 否则sh找不到openssl程序
TITLE [2-生成signature] 展讯公钥签名解锁BL

ECHO.
ECHO.适用: 紫光展锐展讯虎贲SpreadTrum处理器全系, 使用公钥签名的设备.
ECHO.
:A
set identifier_token=
set /p identifier_token=请输入identifier_token: 
if "%identifier_token%"=="" goto A
ECHO.
ECHO.生成signature...
busybox.exe ash unlockbl.sh %identifier_token% sign.pem ..\signature.bin || ECHO.生成失败.
ECHO.
ECHO.如果看到"Identifier sign successfully"提示, 则生成成功. 否则请使用方案2.
ECHO.
ECHO.完成. 按任意键关闭... & pause>nul & EXIT
