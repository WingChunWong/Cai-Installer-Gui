"""GUI 日志处理实用工具"""
import tkinter as tk
import logging


class GuiHandler(logging.Handler):
    """将日志消息发送到 Tkinter Text 组件的处理器"""
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter('%(message)s'))
        
        # 配置标签颜色
        self.text_widget.tag_config('INFO', foreground='#333333')
        self.text_widget.tag_config('WARNING', foreground='#ff6b35')
        self.text_widget.tag_config('ERROR', foreground='#dc3545')
        self.text_widget.tag_config('DEBUG', foreground='#17a2b8')
        self.text_widget.tag_config('SUCCESS', foreground='#28a745')
    
    def emit(self, record):
        """处理日志记录"""
        msg = self.format(record)
        level = record.levelname
        self.text_widget.after(0, self.update_log_text, msg, level)
    
    def update_log_text(self, msg, level):
        """更新日志文本显示"""
        try:
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n', level.upper())
            self.text_widget.configure(state='disabled')
            self.text_widget.see(tk.END)
        except tk.TclError:
            pass
