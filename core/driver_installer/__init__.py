"""扶小鹰驱动一键安装引擎（已整合进工具箱「综合」页的驱动安装模块）

全自动安装工具的驱动与运行环境：
  - 注册表配置 (config.reg)
  - 展锐/瑞芯微 INF 驱动 (pnputil)
  - OPLUS ADB/Fastboot/高通/联发科 全家桶
  - UsbDk 虚拟 USB 驱动
  - Python 3.14 运行环境
  - 绿色 MSVC 工具链

核心：静默参数优先，UI 自动化 watchdog 兜底，做到完全无人值守。
资源目录使用 toolbox 的 tools/支持库及驱动（settings.DEPS_DIR）。
"""
__version__ = "1.0.0"