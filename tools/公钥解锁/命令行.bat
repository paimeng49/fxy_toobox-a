@ECHO OFF
cd /d %~dp0
if exist bin (cd bin) else (EXIT)
TITLE [命令行] 展讯公钥签名解锁BL

:A
ECHO.通用fastboot: fastboot
ECHO.展讯专用fastboot: fastboot_sprd
ECHO.展讯获取identifier_token: fastboot_sprd oem get_identifier_token
ECHO.展讯解锁BL: fastboot_sprd flashing unlock_bootloader signature.bin
ECHO.展讯上锁BL: fastboot_sprd flashing lock_bootloader
ECHO.检查adb连接: adb devices
ECHO.开机重启到Fastboot: adb reboot bootloader
ECHO.Fastboot或FastbootD重启到Fastboot: fastboot reboot bootloader
ECHO.
cmd
ECHO.
ECHO.上个会话已经结束.
ECHO.
goto A
