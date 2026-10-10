@ECHO OFF
cd /d %~dp0
if exist bin (cd bin) else (EXIT)
TITLE [4-检查是否解锁成功] 展讯公钥签名解锁BL

ECHO.
ECHO.适用: 紫光展锐展讯虎贲SpreadTrum处理器全系, 使用公钥签名的设备.
:A
if not exist ..\signature.bin ECHO. & ECHO.找不到signature.bin. 请将signature文件复制到本文件夹(%cd%)并重命名为signature.bin. 按任意键重试... & pause>nul & goto A
ECHO.
ECHO.请将设备进入Fastboot模式, 然后按任意键继续... & pause>nul
ECHO.
ECHO.如果看到"Bootloader can not been unlocked repeatly"提示, 则解锁成功. 如果报其他错误, 则解锁失败. 若再次进入解锁程序，说明可以解锁但上次没有确认解锁, 请按提示重新确认解锁.
ECHO.
ECHO.正在检查是否解锁成功...
fastboot_sprd.exe oem get_identifier_token
fastboot_sprd.exe flashing unlock_bootloader ..\signature.bin
ECHO.
ECHO.完成. 按任意键关闭... & pause>nul & EXIT

::上锁BL
::fastboot flashing lock_bootloader
