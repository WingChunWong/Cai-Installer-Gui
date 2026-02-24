"""UI 对话框与小组件"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from typing import List


class SimpleNotepad(tk.Toplevel):
    """简单的文件编辑对话框"""
    
    def __init__(self, parent, filename, content, file_path):
        super().__init__(parent)
        self.transient(parent)
        self.title(f"编辑文件 - {filename}")
        self.file_path = Path(file_path)
        
        self.geometry("800x600")
        self.minsize(600, 400)
        
        # 居中显示
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width - 800) // 2
        y = parent_y + (parent_height - 600) // 2
        self.geometry(f"800x600+{x}+{y}")
        
        # 创建主框架
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # 标题
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        title_label = ttk.Label(header_frame, text=f"文件: {filename}", 
                               font=('Consolas', 12, 'bold'))
        title_label.pack(anchor=tk.W)
        
        # 文本编辑区域
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        
        self.text_widget = scrolledtext.ScrolledText(
            text_frame, 
            wrap=tk.WORD, 
            font=('Consolas', 10),
            relief=tk.FLAT,
            borderwidth=1
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        self.text_widget.insert(tk.END, content)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        save_button = ttk.Button(button_frame, text="保存", command=self.save_file)
        save_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        close_button = ttk.Button(button_frame, text="关闭", command=self.destroy)
        close_button.pack(side=tk.RIGHT)

    def save_file(self):
        """保存编辑的文件"""
        try:
            content = self.text_widget.get("1.0", tk.END)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("成功", "文件已保存。", parent=self)
        except Exception as e:
            messagebox.showerror("失败", f"保存文件失败: {e}", parent=self)


class GameSelectionDialog(tk.Toplevel):
    """游戏选择对话框"""
    
    def __init__(self, parent, games: List[dict], title="选择游戏"):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.games = games
        self.result = None
        
        self.geometry("600x400")
        
        # 居中显示
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width - 600) // 2
        y = parent_y + (parent_height - 400) // 2
        self.geometry(f"600x400+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # 标题
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        title_label = ttk.Label(header_frame, 
                               text=f"找到 {len(games)} 个游戏，请选择一个：",
                               font=('Consolas', 11))
        title_label.pack(anchor=tk.W)
        
        # 列表区域
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        
        self.listbox_frame = ttk.Frame(list_frame)
        self.listbox_frame.pack(fill=tk.BOTH, expand=True)
        
        self.listbox = tk.Listbox(
            self.listbox_frame,
            font=('Consolas', 10),
            relief=tk.FLAT,
            borderwidth=1,
            selectbackground='#0078D4',
            selectforeground='white'
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(self.listbox_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        
        # 填充游戏列表
        for game in games:
            name = game.get("schinese_name") or game.get("name", "N/A")
            appid = game['appid']
            self.listbox.insert(tk.END, f" {name} (AppID: {appid})")
        
        self.listbox.bind("<Double-Button-1>", self.ok)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        ok_button = ttk.Button(button_frame, text="确定", command=self.ok)
        ok_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        cancel_button = ttk.Button(button_frame, text="取消", command=self.destroy)
        cancel_button.pack(side=tk.RIGHT)
    
    def ok(self, event=None):
        """处理选择"""
        selections = self.listbox.curselection()
        if not selections:
            messagebox.showwarning("未选择", "请在列表中选择一个游戏。", parent=self)
            return
        self.result = self.games[selections[0]]
        self.destroy()


class ManualSelectionDialog(tk.Toplevel):
    """手动选择解锁工具对话框"""
    
    def __init__(self, parent, title=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title or "选择解锁工具")
        self.result = None
        
        self.geometry("400x200")
        
        # 居中显示
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width - 400) // 2
        y = parent_y + (parent_height - 200) // 2
        self.geometry(f"400x200+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(self, padding=30)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 提示文本
        ttk.Label(main_frame, 
                 text="未能自动检测到解锁工具。\n请根据您的实际情况选择：",
                 justify=tk.LEFT,
                 font=('Consolas', 11)).pack(pady=(0, 20))
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        steamtools_btn = ttk.Button(button_frame, 
                                     text="我是 SteamTools 用户",
                                     command=lambda: self.ok("steamtools"))
        steamtools_btn.pack(fill=tk.X, pady=(0, 10))
        
        greenluma_btn = ttk.Button(button_frame, 
                                    text="我是 GreenLuma 用户",
                                    command=lambda: self.ok("greenluma"))
        greenluma_btn.pack(fill=tk.X)
        
        self.wait_window(self)
    
    def ok(self, result):
        """处理选择"""
        self.result = result
        self.destroy()
