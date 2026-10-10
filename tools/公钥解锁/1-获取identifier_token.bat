@ECHO OFF
cd /d %~dp0
if exist bin (cd bin) else (EXIT)
TITLE [1-获取identifier_token] 展讯公钥签名解锁BL

ECHO.
ECHO.适用: 紫光展锐展讯虎贲SpreadTrum处理器全系, 使用公钥签名的设备.
ECHO.
ECHO.请将设备进入Fastboot模式, 然后按任意键继续... & pause>nul
ECHO.
ECHO.获取identifier_token(长时间卡住说明设备未连接或驱动未安装)... & fastboot_sprd.exe oem get_identifier_token 1>..\identifier_token.txt 2>&1
type ..\identifier_token.txt
start ..\identifier_token.txt
ECHO.
ECHO.注: 如果identifier_token换行显示, 则应合并换行前后的部分.
ECHO.完成. 按任意键关闭... & pause>nul & EXIT
