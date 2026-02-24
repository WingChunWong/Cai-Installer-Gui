"""UI 模块 - GUI 界面和用户交互层"""
# 导出主要的 GUI 应用
try:
    from .app import CaiInstallGUI, UpdateManager
    from .widgets import SimpleNotepad, GameSelectionDialog, ManualSelectionDialog
    __all__ = ['CaiInstallGUI', 'UpdateManager', 'SimpleNotepad', 'GameSelectionDialog', 'ManualSelectionDialog']
except ImportError:
    # 防止循环导入或模块加载失败
    __all__ = []

