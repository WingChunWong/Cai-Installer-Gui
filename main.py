#!/usr/bin/env python3
"""
Cai Installer GUI - 应用入口
主程序，负责启动 GUI 应用
"""
import sys
from pathlib import Path

# 确保 version.py 存在或设置默认版本
try:
    from version import __version__ as CURRENT_VERSION
except ImportError:
    CURRENT_VERSION = "dev"

# 启用 DPI 感知（Windows）
if sys.platform == 'win32':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# 导入 GUI 应用
from ui.app import CaiInstallGUI


def main():
    """启动应用"""
    try:
        app = CaiInstallGUI()
        app.run()
    except Exception as e:
        print(f"应用启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
