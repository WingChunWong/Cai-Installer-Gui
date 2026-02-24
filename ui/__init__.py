"""UI 模块 - GUI 界面和用户交互层"""
# 导出主要的 GUI 应用
import logging

try:
    from .app import CaiInstallGUI, UpdateManager
    from .widgets import SimpleNotepad, GameSelectionDialog, ManualSelectionDialog
    __all__ = ['CaiInstallGUI', 'UpdateManager', 'SimpleNotepad', 'GameSelectionDialog', 'ManualSelectionDialog']
except ImportError as exc:
    # 防止循环导入或模块加载失败，但仍需要记录错误方便调试
    logging.getLogger(__name__).error(f"UI 模块导入失败: {exc}")
    __all__ = []

