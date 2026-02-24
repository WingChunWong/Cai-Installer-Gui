"""应用目录与配置管理"""
import sys
from pathlib import Path

# 默认配置
DEFAULT_CONFIG = {
    "Github_Personal_Token": "",
    "Custom_Steam_Path": "",
    "steamtools_only_lua": False,
    "auto_restart_steam": True
}


def get_app_dir():
    """
    获取应用程序的根目录（存放config.json的位置）。
    兼容开发环境、Nuitka、PyInstaller、cx_Freeze等常见打包工具。
    """
    # 方案1: 如果存在 '_MEIPASS' 属性，说明是 PyInstaller 单文件模式
    if getattr(sys, '_MEIPASS', None):
        # sys._MEIPASS 是解压临时目录，我们需要可执行文件所在的真实目录
        app_dir = Path(sys.executable).resolve().parent
    
    # 方案2: 如果存在 '__compiled__' 属性，说明是 Nuitka 打包
    elif '__compiled__' in globals():
        # 对于Nuitka，sys.argv[0] 就是可执行文件路径
        app_dir = Path(sys.argv[0]).resolve().parent
    
    # 方案3: 如果 sys.frozen 属性为 True，可能是 cx_Freeze 或其他工具
    elif getattr(sys, 'frozen', False):
        # 对于 cx_Freeze, sys.executable 就是可执行文件路径
        app_dir = Path(sys.executable).resolve().parent
    
    # 方案4: 普通开发环境
    else:
        # 使用当前脚本文件所在的目录
        app_dir = Path(__file__).resolve().parent.parent
    
    # 返回之前，确保路径是绝对路径且标准化（处理掉 '..' 和符号链接等）
    return app_dir
