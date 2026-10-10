@ECHO OFF
cd /d %~dp0
if exist bin (cd bin) else (EXIT)
TITLE [3-解锁BL] 展讯公钥签名解锁BL

ECHO.
ECHO.适用: 紫光展锐展讯虎贲SpreadTrum处理器全系, 使用公钥签名的设备.
:A
if not exist ..\signature.bin ECHO. & ECHO.找不到signature.bin. 请将signature文件复制到本文件夹 (%cd%) 并重命名为signature.bin. 按任意键重试... & pause>nul & goto A
ECHO.
ECHO.请将设备进入Fastboot模式, 然后按任意键继续... & pause>nul
ECHO.
ECHO.正在解锁BL. 请按设备屏幕提示操作...
fastboot_sprd.exe oem get_identifier_token
fastboot_sprd.exe flashing unlock_bootloader ..\signature.bin
ECHO.
ECHO.完成. 按任意键关闭... & pause>nul & EXIT
