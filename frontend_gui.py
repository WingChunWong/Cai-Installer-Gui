from datetime import datetime, timedelta
from pathlib import Path
import sys
import os
import logging
import asyncio
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
from typing import List
import subprocess
import tempfile
import re   

# 版本信息
try:
    from version import __version__ as CURRENT_VERSION
except ImportError:
    CURRENT_VERSION = "dev"

try:
    import httpx
except ImportError:
    messagebox.showerror("依赖缺失", "错误: httpx 库未安装。\n请在命令行中使用 'pip install httpx' 命令安装后重试。")
    sys.exit(1)

try:
    from backend_gui import GuiBackend
except ImportError:
    messagebox.showerror("文件缺失", "错误: backend_gui.py 文件缺失。\n请确保主程序和后端文件在同一个目录下。")
    sys.exit(1)

# 设置Windows系统主题
if sys.platform == 'win32':
    try:
        from ctypes import windll, byref, sizeof, c_int
        # 启用深色模式支持
        windll.user32.SetProcessDPIAware()
    except:
        pass

class ModernButton(ttk.Button):
    """现代化按钮样式"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Modern.TButton')

class ModernEntry(ttk.Entry):
    """现代化输入框"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Modern.TEntry')

class ModernCombobox(ttk.Combobox):
    """现代化下拉框"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Modern.TCombobox')

class ModernCheckbutton(ttk.Checkbutton):
    """现代化复选框"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style='Modern.TCheckbutton')

class SimpleNotepad(tk.Toplevel):
    def __init__(self, parent, filename, content, file_path):
        super().__init__(parent)
        self.transient(parent)
        self.title(f"编辑文件 - {filename}")
        self.file_path = Path(file_path)
        
        # 设置窗口大小和位置
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
        
        # 使用系统按钮样式
        save_button = ttk.Button(button_frame, text="保存", 
                                command=self.save_file,
                                style='Accent.TButton')
        save_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        close_button = ttk.Button(button_frame, text="关闭", 
                                 command=self.destroy)
        close_button.pack(side=tk.RIGHT)

    def save_file(self):
        try:
            content = self.text_widget.get("1.0", tk.END)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("成功", "文件已保存。", parent=self)
        except Exception as e:
            messagebox.showerror("失败", f"保存文件失败: {e}", parent=self)

class GameSelectionDialog(tk.Toplevel):
    def __init__(self, parent, games: List[dict], title="选择游戏"):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.games = games
        self.result = None
        
        # 设置窗口大小
        self.geometry("600x400")
        self.minsize(800, 500)
        
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
        
        # 创建列表和滚动条
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
        
        ok_button = ttk.Button(button_frame, text="确定", 
                              command=self.ok,
                              style='')
        ok_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        cancel_button = ttk.Button(button_frame, text="取消", 
                                  command=self.destroy)
        cancel_button.pack(side=tk.RIGHT)
    
    def ok(self, event=None):
        selections = self.listbox.curselection()
        if not selections:
            messagebox.showwarning("未选择", "请在列表中选择一个游戏。", parent=self)
            return
        self.result = self.games[selections[0]]
        self.destroy()

class CaiInstallGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Cai Install GUI v{CURRENT_VERSION}")
        
        # 设置窗口初始大小和位置
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # 设置窗口图标（如果有）
        try:
            icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass
        
        # 设置协议
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.processing_lock = threading.Lock()
        
        # 设置样式
        self.setup_styles()
        
        # 创建控件
        self.create_widgets()
        
        # 设置日志系统
        self.log = self.setup_logging()
        
        # 初始化后端
        self.backend = GuiBackend(self.log)
        
        # 创建菜单
        self.create_menu()
        
        # 最大化窗口
        self.root.state('zoomed')
        
        # 文件面板显示状态
        self.show_file_panel = True
        
        # 延迟初始化
        self.root.after(100, self.initialize_app)
        
        # 更新检查状态
        self.update_check_done = False
        
        # 启动时后台检查更新
        threading.Thread(target=self.background_check_update, daemon=True).start()

    def setup_styles(self):
        """设置现代化样式"""
        style = ttk.Style()
        
        # 尝试使用系统主题
        available_themes = style.theme_names()
        if 'vista' in available_themes:
            style.theme_use('vista')
        elif 'winnative' in available_themes:
            style.theme_use('winnative')
        
        # 配置现代化按钮样式
        style.configure('Modern.TButton',
                       padding=8,
                       relief='flat',
                       font=('Consolas', 10))
        
        style.configure('Accent.TButton',
                       padding=8,
                       relief='flat',
                       font=('Consolas', 10, 'bold'))
        
        # 配置输入框样式
        style.configure('Modern.TEntry',
                       padding=5,
                       relief='flat',
                       font=('Consolas', 10))
        
        # 配置下拉框样式
        style.configure('Modern.TCombobox',
                       padding=5,
                       font=('Consolas', 10))
        
        # 配置复选框样式
        style.configure('Modern.TCheckbutton',
                       font=('Consolas', 10))
        
        # 配置标签样式
        style.configure('Header.TLabel',
                       font=('Consolas', 12, 'bold'))
        
        style.configure('Subheader.TLabel',
                       font=('Consolas', 10, 'bold'))

    def setup_logging(self):
        """设置日志系统"""
        logger = logging.getLogger('CaiInstallGUI')
        logger.setLevel(logging.INFO)
        
        class GuiHandler(logging.Handler):
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
                msg = self.format(record)
                level = record.levelname
                self.text_widget.after(0, self.update_log_text, msg, level)
            
            def update_log_text(self, msg, level):
                try:
                    self.text_widget.configure(state='normal')
                    self.text_widget.insert(tk.END, msg + '\n', level.upper())
                    self.text_widget.configure(state='disabled')
                    self.text_widget.see(tk.END)
                except tk.TclError:
                    pass
        
        gui_handler = GuiHandler(self.log_text_widget)
        logger.addHandler(gui_handler)
        return logger

    def create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="退出", command=self.on_closing)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="编辑配置", command=self.show_settings_dialog)
        
        # 工具菜单
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="重启Steam", command=self.restart_steam)
        tools_menu.add_command(label="清理临时文件", command=self.cleanup_temp_files)
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="项目主页", command=lambda: webbrowser.open('https://github.com/WingChunWong/Cai-Installer-GUI'))
        help_menu.add_command(label="禁止倒卖", command=lambda: webbrowser.open('https://docs.qq.com/doc/DTUp3Z2Fkd2pVRGtX?dver='))
        help_menu.add_separator()
        help_menu.add_command(label="检查更新", command=self.check_for_updates)
        help_menu.add_command(label="关于", command=self.show_about_dialog)

    def create_widgets(self):
        """创建主界面控件"""
        # 创建主框架
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # 分割为左右两部分
        paned_window = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # 左侧面板
        left_panel = ttk.Frame(paned_window)
        paned_window.add(left_panel, weight=3)
        
        # 右侧面板（文件管理）
        self.right_panel = self.create_file_panel()
        paned_window.add(self.right_panel, weight=1)
        
        # 左侧内容区域
        self.create_left_content(left_panel)
        
        # 状态栏
        self.create_status_bar(main_container)

    def create_left_content(self, parent):
        """创建左侧内容区域"""
        # 顶部标题区域
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        title_label = ttk.Label(header_frame, 
                               text=f"Cai Install GUI v{CURRENT_VERSION}",
                               style='Header.TLabel')
        title_label.pack(anchor=tk.W)
        
        # 搜索区域
        search_frame = ttk.LabelFrame(parent, text="快速搜索", padding=15)
        search_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        search_container = ttk.Frame(search_frame)
        search_container.pack(fill=tk.X)
        
        ttk.Label(search_container, text="AppID或游戏名称:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.appid_entry = ModernEntry(search_container, width=40)
        self.appid_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.search_button = ModernButton(search_container, 
                                         text="搜索",
                                         command=self.start_game_search,
                                         width=10)
        self.search_button.pack(side=tk.LEFT)
        
        # 安装模式区域
        mode_frame = ttk.LabelFrame(parent, text="安装模式", padding=15)
        mode_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        # 创建选项卡
        self.notebook = ttk.Notebook(mode_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 选项卡1：指定库安装
        tab1 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab1, text="从指定库安装")
        
        repo_container = ttk.Frame(tab1)
        repo_container.pack(fill=tk.X)
        
        ttk.Label(repo_container, text="选择清单库:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.repo_options = [
            ("SWA V2 (printedwaste)", "swa"), 
            ("Cysaw", "cysaw"), 
            ("Furcate", "furcate"), 
            ("CNGS (assiw)", "cngs"),
            ("SteamDatabase", "steamdatabase"), 
            ("Walftech", "walftech"),
            ("GitHub - Auiowu/ManifestAutoUpdate", "Auiowu/ManifestAutoUpdate"),
            ("GitHub - SteamAutoCracks/ManifestHub", "SteamAutoCracks/ManifestHub"),
        ]
        
        self.repo_combobox = ModernCombobox(repo_container, state="readonly", width=40)
        self.repo_combobox['values'] = [name for name, _ in self.repo_options]
        self.repo_combobox.current(0)
        self.repo_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 选项卡2：搜索所有库
        tab2 = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(tab2, text="搜索所有GitHub库")
        
        info_label = ttk.Label(tab2, 
                              text="此模式将自动搜索所有已知的GitHub清单库，\n并选择最新的清单进行安装。",
                              font=('Consolas', 10))
        info_label.pack(anchor=tk.W)
        
        # 处理按钮区域
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        self.process_button = ModernButton(button_frame,
                                          text="开始处理",
                                          command=self.start_processing,
                                          style='Accent.TButton')
        self.process_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # 日志区域
        log_frame = ttk.LabelFrame(parent, text="日志输出", padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # 日志工具栏
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(0, 10))
        
        clear_btn = ModernButton(log_toolbar, text="清空日志", command=self.clear_log)
        clear_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        copy_btn = ModernButton(log_toolbar, text="复制日志", command=self.copy_log)
        copy_btn.pack(side=tk.LEFT)
        
        # 日志文本框
        self.log_text_widget = scrolledtext.ScrolledText(
            log_frame, 
            wrap=tk.WORD, 
            state='disabled',
            font=('Consolas', 10),
            height=15,
            relief=tk.FLAT,
            borderwidth=1
        )
        self.log_text_widget.pack(fill=tk.BOTH, expand=True)

    def create_file_panel(self):
        """创建右侧文件管理面板"""
        panel = ttk.LabelFrame(self.root, text="入库管理", padding=15)
        
        # 工具栏按钮
        toolbar = ttk.Frame(panel)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        buttons = [
            ("刷新", self.refresh_file_list, ''),
            ("查看", self.view_selected_file, ''),
            ("删除", self.delete_selected_file, ''),
            ("重启Steam", self.restart_steam,'')
        ]
        
        for i, (text, command, style) in enumerate(buttons):
            btn = ttk.Button(toolbar, text=text, command=command, style=style, width=10)
            btn.grid(row=0, column=i, padx=(0, 5) if i < 3 else 0)
        
        # 文件列表
        list_frame = ttk.Frame(panel)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_list = tk.Listbox(
            list_frame,
            font=('Consolas', 9),
            selectmode=tk.EXTENDED,
            relief=tk.FLAT,
            borderwidth=1
        )
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.config(yscrollcommand=scrollbar.set)
        
        self.file_list.bind("<Double-Button-1>", lambda e: self.view_selected_file())
        
        return panel

    def create_status_bar(self, parent):
        """创建状态栏"""
        self.status_bar = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=1)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_label = ttk.Label(self.status_bar, text="正在初始化...", relief=tk.FLAT)
        self.status_label.pack(side=tk.LEFT, padx=10, pady=3)
        
        # 添加版本信息
        version_label = ttk.Label(self.status_bar, text=f"版本: {CURRENT_VERSION}", relief=tk.FLAT)
        version_label.pack(side=tk.RIGHT, padx=10, pady=3)

    # 以下方法保持原有功能，但使用新的控件样式
    def clear_log(self):
        self.log_text_widget.configure(state='normal')
        self.log_text_widget.delete(1.0, tk.END)
        self.log_text_widget.configure(state='disabled')
    
    def copy_log(self):
        content = self.log_text_widget.get(1.0, tk.END)
        if content.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("成功", "日志内容已复制到剪贴板")

    def refresh_file_list(self):
        self.file_list.delete(0, tk.END)
        
        if not self.backend.steam_path or not self.backend.steam_path.exists():
            self.file_list.insert(tk.END, " 未找到Steam安装路径")
            return
        
        plugin_dir = self.backend.steam_path / "config" / "stplug-in"
        if not plugin_dir.exists():
            self.file_list.insert(tk.END, " 插件目录不存在")
            return
        
        try:
            lua_files = [f for f in os.listdir(plugin_dir) if f.endswith(".lua")]
            if not lua_files:
                self.file_list.insert(tk.END, " 暂无入库文件")
                return
            
            lua_files.sort(key=lambda f: (plugin_dir / f).stat().st_mtime, reverse=True)
            for file in lua_files:
                self.file_list.insert(tk.END, f" {file}")
        except Exception as e:
            self.file_list.insert(tk.END, f" 读取失败: {e}")

    def get_selected_files(self):
        selected_indices = self.file_list.curselection()
        if not selected_indices:
            return []
        return [self.file_list.get(i).strip() for i in selected_indices]

    def delete_selected_file(self):
        filenames = self.get_selected_files()
        if not filenames:
            messagebox.showinfo("提示", "请先在列表中选择要删除的文件。", parent=self.root)
            return
        
        msg = f"确定要删除这 {len(filenames)} 个文件吗？\n此操作不可恢复！" if len(filenames) > 1 else f"确定要删除 {filenames[0]} 吗？\n此操作不可恢复！"
        
        if not messagebox.askyesno("确认删除", msg, parent=self.root):
            return
        
        plugin_dir = self.backend.steam_path / "config" / "stplug-in"
        deleted_count, failed_files = 0, []
        
        for filename in filenames:
            try:
                file_path = plugin_dir / filename
                if file_path.exists():
                    os.remove(file_path)
                    deleted_count += 1
                else:
                    failed_files.append(f"{filename} (不存在)")
            except Exception as e:
                failed_files.append(f"{filename} ({e})")
        
        if deleted_count > 0:
            self.log.info(f"成功删除 {deleted_count} 个文件")
            self.auto_restart_steam("文件删除")
        
        self.refresh_file_list()
        
        if failed_files:
            messagebox.showwarning("部分失败", "以下文件删除失败:\n" + "\n".join(failed_files), parent=self.root)

    def view_selected_file(self):
        filenames = self.get_selected_files()
        if not filenames:
            messagebox.showinfo("提示", "请选择一个文件进行查看。", parent=self.root)
            return
        
        if len(filenames) > 1:
            messagebox.showinfo("提示", "请只选择一个文件进行查看。", parent=self.root)
            return
        
        filename = filenames[0]
        try:
            file_path = self.backend.steam_path / "config" / "stplug-in" / filename
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                SimpleNotepad(self.root, filename, content, str(file_path))
            else:
                messagebox.showerror("错误", "文件不存在。", parent=self.root)
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}", parent=self.root)

    def initialize_app(self):
        self.print_banner()
        self.log.info("Cai Installer GUI版 - 正在初始化...")
        self.backend.load_config()
        self.update_unlocker_status()
        
        self.refresh_file_list()
        
        self.log.info("软件作者: pvzcxw 二改: WingChunWong")
        self.log.info("本项目采用GNU GPLv3开源许可证，完全免费，请勿用于商业用途。")

    def print_banner(self):
        """保留原有的艺术字"""
        banner = [
            r"   ____           _     ___                 _             _   _               ",
            r"  / ___|   __ _  (_)   |_ _|  _ __    ___  | |_    __ _  | | | |   ___   _ __ ",
            r" | |      / _` | | |    | |  | '_ \  / __| | __|  / _` | | | | |  / _ \ | '__|",
            r" | |___  | (_| | | |    | |  | | | | \__ \ | |_  | (_| | | | | | |  __/ | |   ",
            r"  \____|  \__,_| |_|   |___| |_| |_| |___/  \__|  \__,_| |_| |_|  \___| |_|   ",
            r"==============================================================================",
            r"              Cai Installer GUI  原作者: pvzcxw  二改: WingChunWong            ",
        ]
        for line in banner:
            self.log.info(line)

    def update_unlocker_status(self):
        steam_path = self.backend.detect_steam_path()
        if not steam_path.exists():
            self.status_label.config(text="Steam路径未找到！请在设置中指定。")
            messagebox.showerror('Steam未找到', "无法自动检测到Steam路径。\n请在\"设置\"->\"编辑配置\"中手动指定路径。")
            return
        
        status = self.backend.detect_unlocker()
        if status == "conflict":
            messagebox.showerror("环境冲突", "错误: 同时检测到 SteamTools 和 GreenLuma！\n请手动卸载其中一个以避免冲突，然后重启本程序。")
            self.process_button.config(state=tk.DISABLED)
            self.status_label.config(text="环境冲突！请解决后重启。")
        elif status == "none":
            self.handle_manual_selection()
        
        if self.backend.unlocker_type:
            self.status_label.config(text=f"Steam路径: {steam_path} | 解锁方式: {self.backend.unlocker_type.title()}")

    def handle_manual_selection(self):
        dialog = ManualSelectionDialog(self.root, title="选择解锁工具")
        self.root.wait_window(dialog)
        
        if dialog.result in ["steamtools", "greenluma"]:
            self.backend.unlocker_type = dialog.result
            self.log.info(f"已手动选择解锁方式: {dialog.result.title()}")
            self.update_unlocker_status()
        else:
            self.log.error("未选择解锁工具，部分功能可能无法正常工作。")
            self.status_label.config(text="未选择解锁工具！")
            self.process_button.config(state=tk.DISABLED)

    def start_game_search(self):
        if not self.processing_lock.acquire(blocking=False):
            self.log.warning("已在处理中，请等待当前任务完成。")
            return

        search_term = self.appid_entry.get().strip()
        if not search_term:
            self.log.error("搜索框不能为空！")
            self.processing_lock.release()
            return
        
        def thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            client = httpx.AsyncClient(verify=False, timeout=60.0)
            
            try:
                games = loop.run_until_complete(self.backend.search_games_by_name(client, search_term))
                self.root.after(0, self.show_game_selection_dialog, games)
            finally:
                loop.run_until_complete(client.aclose())
                loop.close()
                self.processing_lock.release()
                self.root.after(0, self.search_finished)
        
        self.search_button.config(state=tk.DISABLED, text="搜索中...")
        threading.Thread(target=thread_target, daemon=True).start()
    
    def search_finished(self):
        self.search_button.config(state=tk.NORMAL, text="搜索")
    
    def show_game_selection_dialog(self, games):
        if not games:
            self.log.warning("未找到匹配的游戏。")
            messagebox.showinfo("未找到", "未找到与搜索词匹配的游戏。", parent=self.root)
            return
        
        dialog = GameSelectionDialog(self.root, games=games)
        if dialog.result:
            selected_game = dialog.result
            self.appid_entry.delete(0, tk.END)
            self.appid_entry.insert(0, selected_game['appid'])
            name = selected_game.get("schinese_name") or selected_game.get("name", "N/A")
            self.log.info(f"已选择游戏: {name} (AppID: {selected_game['appid']})")

    def start_processing(self):
        if not self.backend.unlocker_type:
            messagebox.showerror("错误", "未确定解锁工具！\n请先通过设置或重启程序解决解锁工具检测问题。")
            return
        
        if not self.processing_lock.acquire(blocking=False):
            self.log.warning("已在处理中，请等待当前任务完成。")
            return
        
        is_st_auto_update_mode = self.backend.is_steamtools() and self.backend.app_config.get("steamtools_only_lua", False)
        if is_st_auto_update_mode:
            self.backend.st_lock_manifest_version = False
            self.log.info("SteamTools自动更新模式已启用，将使用浮动版本。")
        
        notebook_tab = self.notebook.index('current')
        
        def thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            client = httpx.AsyncClient(verify=False, timeout=60.0)
            
            try:
                success = loop.run_until_complete(self.run_async_tasks(client, notebook_tab))
                if success:
                    self.root.after(0, self.auto_restart_steam, "游戏入库")
            finally:
                loop.run_until_complete(client.aclose())
                loop.close()
                self.processing_lock.release()
                self.root.after(0, self.processing_finished)
        
        self.process_button.config(state=tk.DISABLED, text="正在处理...")
        self.appid_entry.config(state=tk.DISABLED)
        self.search_button.config(state=tk.DISABLED)
        self.status_label.config(text="正在处理...")
        
        threading.Thread(target=thread_target, daemon=True).start()
    
    def processing_finished(self):
        self.process_button.config(state=tk.NORMAL, text="开始处理")
        self.appid_entry.config(state=tk.NORMAL)
        self.search_button.config(state=tk.NORMAL)
        self.status_label.config(text="处理完成，准备就绪。")
        self.log.info("=" * 60 + "\n处理完成！您可以开始新的任务。")
    
    async def run_async_tasks(self, client: httpx.AsyncClient, tab_index: int):
        user_input = self.appid_entry.get().strip()
        if not user_input:
            self.log.error("输入不能为空！")
            return False
        
        app_id_inputs = [item.strip() for item in user_input.split(',')]
        
        try:
            if tab_index == 0:
                repo_name, repo_val = self.repo_options[self.repo_combobox.current()]
                self.log.info(f"选择了清单库: {repo_name}")
                success = await self.backend.process_from_specific_repo(client, app_id_inputs, repo_val)
                return success
            elif tab_index == 1:
                self.log.info("模式: 搜索所有GitHub库")
                github_repos = [val for _, val in self.repo_options if val not in ["swa", "cysaw", "furcate", "cngs", "steamdatabase", "walftech"]]
                success = await self.backend.process_by_searching_all(client, app_id_inputs, github_repos)
                return success
            return False
        finally:
            await self.backend.cleanup_temp_files()

    def on_closing(self):
        if self.processing_lock.locked():
            if messagebox.askyesno("退出", "正在处理任务，确定要强制退出吗？"):
                os._exit(0)
        else:
            self.root.destroy()

    def show_about_dialog(self):
        about_text = f"""Cai Install GUI

一个用于Steam游戏清单获取和导入的工具

版本: {CURRENT_VERSION}
作者: pvzcxw
二改: WingChunWong

本项目采用GNU GPLv3开源许可证
完全免费，请勿用于商业用途。"""
        
        messagebox.showinfo("关于", about_text)

    def show_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑配置")
        dialog.transient(self.root)
        
        # 设置窗口大小和位置
        dialog.geometry("500x350")
        dialog.minsize(800, 400)
        
        # 居中显示
        dialog.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        x = parent_x + (parent_width - 500) // 2
        y = parent_y + (parent_height - 350) // 2
        dialog.geometry(f"500x350+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # GitHub Token
        ttk.Label(main_frame, text="GitHub Personal Token:", 
                 style='Subheader.TLabel').grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        token_entry = ModernEntry(main_frame, width=40)
        token_entry.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 15))
        token_entry.insert(0, self.backend.app_config.get("Github_Personal_Token", ""))
        
        # Steam路径
        ttk.Label(main_frame, text="自定义Steam路径:", 
                 style='Subheader.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        
        path_frame = ttk.Frame(main_frame)
        path_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(0, 15))
        
        path_entry = ModernEntry(path_frame)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        path_entry.insert(0, self.backend.app_config.get("Custom_Steam_Path", ""))
        
        browse_btn = ModernButton(path_frame, text="浏览...", width=8,
                                 command=lambda: self.browse_steam_path(path_entry))
        browse_btn.pack(side=tk.RIGHT)
        
        # 选项
        options_frame = ttk.Frame(main_frame)
        options_frame.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 20))
        
        st_lua_only_var = tk.BooleanVar(value=self.backend.app_config.get("steamtools_only_lua", False))
        st_lua_only_check = ModernCheckbutton(options_frame, 
                                             text="使用SteamTools自动更新模式",
                                             variable=st_lua_only_var)
        st_lua_only_check.pack(anchor=tk.W)
        
        auto_restart_var = tk.BooleanVar(value=self.backend.app_config.get("auto_restart_steam", True))
        auto_restart_check = ModernCheckbutton(options_frame, 
                                              text="入库后自动重启Steam",
                                              variable=auto_restart_var)
        auto_restart_check.pack(anchor=tk.W, pady=(5, 0))
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        def save_and_close():
            self.backend.app_config["Github_Personal_Token"] = token_entry.get().strip()
            self.backend.app_config["Custom_Steam_Path"] = path_entry.get().strip()
            self.backend.app_config["steamtools_only_lua"] = st_lua_only_var.get()
            self.backend.app_config["auto_restart_steam"] = auto_restart_var.get()
            self.backend.save_config()
            self.log.info("配置已保存。")
            if self.backend.app_config.get("steamtools_only_lua"):
                self.log.info("已启用 [SteamTools自动更新] 模式。")
            dialog.destroy()
        
        save_btn = ModernButton(button_frame, text="保存", 
                               command=save_and_close,
                               style='Accent.TButton')
        save_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        cancel_btn = ModernButton(button_frame, text="取消", 
                                 command=dialog.destroy)
        cancel_btn.pack(side=tk.RIGHT)
        
        # 配置网格权重
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0)

    def browse_steam_path(self, entry_widget):
        """浏览Steam安装路径"""
        from tkinter import filedialog
        path = filedialog.askdirectory(title="选择Steam安装目录")
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)

    def restart_steam(self):
        if not self.backend.steam_path or not self.backend.steam_path.exists():
            messagebox.showerror("错误", "未找到Steam安装路径！", parent=self.root)
            return
        
        steam_exe = self.backend.steam_path / "Steam.exe"
        if not steam_exe.exists():
            messagebox.showerror("错误", f"未找到Steam.exe文件！", parent=self.root)
            return
        
        if not messagebox.askyesno("确认重启", "确定要重启Steam吗？", parent=self.root):
            return
        
        self._perform_steam_restart("手动重启")
    
    def auto_restart_steam(self, reason="操作完成"):
        if not self.backend.app_config.get("auto_restart_steam", True):
            self.log.info(f"自动重启功能已禁用，请手动重启Steam以使{reason}生效。")
            return
            
        if not self.backend.steam_path or not self.backend.steam_path.exists():
            self.log.error("未找到Steam安装路径，无法自动重启！")
            return
        
        steam_exe = self.backend.steam_path / "Steam.exe"
        if not steam_exe.exists():
            self.log.error(f"未找到Steam.exe文件，无法自动重启！")
            return
        
        self.log.info(f"{reason}成功，正在自动重启Steam...")
        threading.Thread(target=self._perform_steam_restart, args=(reason,), daemon=True).start()
    
    def _perform_steam_restart(self, reason):
        try:
            steam_exe = self.backend.steam_path / "Steam.exe"
            
            try:
                subprocess.run(['taskkill', '/F', '/IM', 'steam.exe', '/T'],
                             capture_output=True, shell=True, text=True)
            except Exception:
                pass
            
            import time
            time.sleep(3)
            
            subprocess.Popen([str(steam_exe)], shell=True)
            self.log.info(f"{reason}完成，已重新启动Steam")
            
            self.root.after(0, lambda: messagebox.showinfo("Steam重启", 
                "Steam已自动重启！\n请等待Steam完全启动后检查库中游戏。", parent=self.root))
            
        except Exception as e:
            self.log.error(f"重启Steam失败: {e}")
            self.root.after(0, lambda: messagebox.showerror("重启失败", 
                f"重启Steam失败:\n{e}\n请手动重启Steam。", parent=self.root))

    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            if hasattr(self.backend, 'temp_dir') and self.backend.temp_dir.exists():
                import shutil
                shutil.rmtree(self.backend.temp_dir, ignore_errors=True)
                self.log.info("临时文件清理完成。")
            else:
                self.log.info("没有需要清理的临时文件。")
        except Exception as e:
            self.log.error(f"清理临时文件失败: {e}")

    def background_check_update(self):
        """后台检查更新"""
        async def check():
            await self._check_update_async(show_no_update=False)
        
        asyncio.run(check())

    def check_for_updates(self):
        """手动检查更新"""
        threading.Thread(target=lambda: asyncio.run(self._check_update_async(show_no_update=True)), daemon=True).start()
    
    async def _check_update_async(self, show_no_update: bool):
        """异步检查更新"""
        self.root.after(0, lambda: self.status_label.config(text="正在检查更新..."))
        
        result = await self.backend.check_for_updates(CURRENT_VERSION)
        
        self.root.after(0, lambda: self.status_label.config(text="就绪"))
        self.update_check_done = True
        
        if result.get('has_update'):
            self.root.after(0, lambda: self.show_update_dialog(result))
        elif show_no_update:
            self.root.after(0, lambda: messagebox.showinfo("检查更新", f"当前已是最新版本: {CURRENT_VERSION}"))

    def show_update_dialog(self, update_info):
        """显示更新对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("发现新版本")
        dialog.transient(self.root)
        
        # 设置窗口大小
        dialog.geometry("650x600")
        dialog.minsize(1000, 700)
        
        # 居中显示
        dialog.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        x = parent_x + (parent_width - 800) // 2
        y = parent_y + (parent_height - 650) // 2
        dialog.geometry(f"650x600+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, 
                            text="发现新版本！",
                            font=('Consolas', 14, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # 版本信息
        version_frame = ttk.Frame(main_frame)
        version_frame.pack(fill=tk.X, pady=(0, 15))
        
        current_label = ttk.Label(version_frame, 
                                text=f"当前版本: {update_info['current_version']}",
                                font=('Consolas', 10))
        current_label.pack(anchor=tk.W)
        
        latest_label = ttk.Label(version_frame, 
                                text=f"最新版本: {update_info['latest_version']}",
                                font=('Consolas', 11, 'bold'))
        latest_label.pack(anchor=tk.W, pady=(2, 0))
        
        # 网络和地区信息
        network_frame = ttk.Frame(version_frame)
        network_frame.pack(anchor=tk.W, pady=(5, 0))
        
        # 获取地区信息
        region = "未知"
        if hasattr(self.backend, 'last_detected_region'):
            region = self.backend.last_detected_region
        
        # 格式化地区显示
        if region == 'cn':
            region_display = "中国大陆"
        elif region.startswith('not_cn_'):
            region_display = region.replace('not_cn_', '')
        else:
            region_display = region
        
        # 根据地区决定使用的源
        if os.environ.get('IS_CN') == 'yes':
            network_text = f"检测地区: {region_display}，使用镜像源"
            network_color = 'green'
        else:
            network_text = f"检测地区: {region_display}，使用GitHub源"
            network_color = 'blue'
        
        network_label = ttk.Label(network_frame,
                                text=network_text,
                                font=('Consolas', 9),
                                foreground=network_color)
        network_label.pack(anchor=tk.W)
        
        # 更新时间 (UTC+8)
        if update_info.get('published_at'):
            try:
                pub_time = update_info['published_at']
                
                # 解析UTC时间并转换为UTC+8（北京时间）
                if 'Z' in pub_time:
                    # ISO格式带Z表示UTC时间
                    utc_time = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
                else:
                    utc_time = datetime.fromisoformat(pub_time)
                
                # 转换为UTC+8（北京时间）
                beijing_time = utc_time + timedelta(hours=8)
                pub_date = beijing_time.strftime('%Y-%m-%d %H:%M UTC+8')
                
                time_label = ttk.Label(network_frame,
                                    text=f"发布时间: {pub_date}",
                                    font=('Consolas', 8),
                                    foreground='gray')
                time_label.pack(anchor=tk.W, pady=(2, 0))
            except Exception as e:
                self.log.debug(f"解析发布时间失败: {e}")
        
        # 更新内容标题
        ttk.Label(main_frame, 
                text="更新内容:",
                font=('Consolas', 11, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        
        # 创建文本区域，并配置Markdown样式
        notes_text = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            height=12,
            font=('Consolas', 10),
            relief=tk.FLAT,
            borderwidth=1,
            background='#f9f9f9'
        )
        notes_text.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 配置Markdown样式标签
        self._setup_markdown_tags(notes_text)
        
        # 插入Markdown内容
        release_notes = update_info.get('release_notes', '暂无更新说明')
        self._insert_markdown_content(notes_text, release_notes)
        
        notes_text.configure(state='disabled')
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        cancel_btn = ModernButton(button_frame, text="稍后提醒", command=dialog.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        details_btn = ModernButton(button_frame, text="查看详情", 
                                command=lambda: webbrowser.open(update_info['release_url']))
        details_btn.pack(side=tk.RIGHT, padx=5)
        
        update_btn = ModernButton(button_frame, text="立即更新", 
                                command=lambda: self.start_update(dialog, update_info['download_url']),
                                style='Accent.TButton')
        update_btn.pack(side=tk.RIGHT)

    def _setup_markdown_tags(self, text_widget):
        """配置Markdown标签样式"""
        # 标题样式
        text_widget.tag_configure('h1', font=('Consolas', 14, 'bold'), foreground='#2c3e50', spacing3=10)
        text_widget.tag_configure('h2', font=('Consolas', 12, 'bold'), foreground='#34495e', spacing3=8)
        text_widget.tag_configure('h3', font=('Consolas', 11, 'bold'), foreground='#7f8c8d', spacing3=6)
        
        # 文本样式
        text_widget.tag_configure('bold', font=('Consolas', 10, 'bold'))
        text_widget.tag_configure('italic', font=('Consolas', 10, 'italic'))
        text_widget.tag_configure('bold_italic', font=('Consolas', 10, 'bold italic'))
        
        # 内联代码 - 使用背景色和边距模拟效果，但移除不支持的padding
        text_widget.tag_configure('code', font=('Consolas', 9), background='#e8e8e8',
                                borderwidth=1, relief='solid')
        
        # 代码块 - 移除不支持的padding，使用边距和背景
        text_widget.tag_configure('code_block', font=('Consolas', 9), background='#f5f5f5',
                                lmargin1=20, lmargin2=20, rmargin=20,
                                borderwidth=1, relief='solid', spacing1=5, spacing3=5)
        
        # 链接样式
        text_widget.tag_configure('link', font=('Consolas', 10, 'underline'), foreground='#3498db')
        
        # 列表样式
        text_widget.tag_configure('bullet', lmargin1=20, lmargin2=40)
        text_widget.tag_configure('numbered', lmargin1=20, lmargin2=40)
        
        # 引用样式 - 移除padding，使用边距
        text_widget.tag_configure('blockquote', font=('Consolas', 10, 'italic'), 
                                foreground='#7f8c8d', lmargin1=30, lmargin2=50,
                                borderwidth=0, selectbackground='#f0f0f0')

    def _insert_markdown_content(self, text_widget, markdown_text):
        """插入并渲染Markdown内容"""
        if not markdown_text:
            text_widget.insert(tk.END, "暂无更新说明")
            return
        
        lines = markdown_text.split('\n')
        in_code_block = False
        code_block_content = []
        list_level = 0
        numbered_list_counter = 1
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # 处理代码块
            if line_stripped.startswith('```'):
                if not in_code_block:
                    # 开始代码块
                    in_code_block = True
                    code_block_content = []
                    # 添加空行
                    if i > 0:
                        text_widget.insert(tk.END, '\n')
                else:
                    # 结束代码块
                    in_code_block = False
                    if code_block_content:
                        # 插入代码块内容
                        text_widget.insert(tk.END, '\n'.join(code_block_content) + '\n', 'code_block')
                    continue
            
            if in_code_block:
                code_block_content.append(line)
                continue
            
            # 处理空行
            if not line_stripped:
                text_widget.insert(tk.END, '\n')
                list_level = 0
                numbered_list_counter = 1
                continue
            
            # 处理标题
            if line_stripped.startswith('#'):
                heading_level = 0
                while heading_level < len(line) and line[heading_level] == '#':
                    heading_level += 1
                
                heading_text = line[heading_level:].strip()
                if heading_level <= 3:
                    tag = f'h{heading_level}'
                    if i > 0:
                        text_widget.insert(tk.END, '\n')
                    text_widget.insert(tk.END, heading_text + '\n', tag)
                else:
                    # 四级及以下标题当作普通文本
                    text_widget.insert(tk.END, heading_text + '\n')
                continue
            
            # 处理引用
            if line_stripped.startswith('>'):
                quote_text = line[1:].strip()
                text_widget.insert(tk.END, quote_text + '\n', 'blockquote')
                continue
            
            # 处理列表
            if line_stripped.startswith('- ') or line_stripped.startswith('* '):
                bullet_text = line_stripped[2:]
                text_widget.insert(tk.END, '• ' + bullet_text + '\n', 'bullet')
                list_level = 1
                continue
            
            if re.match(r'^\d+\.\s+', line_stripped):
                # 移除数字前缀
                match = re.match(r'^(\d+)\.\s+(.*)', line_stripped)
                if match:
                    item_text = match.group(2)
                    text_widget.insert(tk.END, f'{numbered_list_counter}. {item_text}\n', 'numbered')
                    numbered_list_counter += 1
                    list_level = 1
                continue
            
            # 处理普通段落（应用内联样式）
            self._insert_inline_styled_text(text_widget, line, list_level > 0)
            text_widget.insert(tk.END, '\n')
        
        # 确保末尾有空行
        text_widget.insert(tk.END, '\n')

    def _insert_inline_styled_text(self, text_widget, text, in_list=False):
        """插入带内联样式的文本"""
        # 处理内联代码、粗体、斜体、链接等
        patterns = [
            (r'`([^`]+)`', 'code'),  # 内联代码
            (r'\*\*\*([^*]+)\*\*\*', 'bold_italic'),  # 粗斜体
            (r'\*\*([^*]+)\*\*', 'bold'),  # 粗体
            (r'\*([^*]+)\*', 'italic'),  # 斜体
            (r'!\[([^\]]+)\]\(([^)]+)\)', 'image'),  # 图片（暂不处理）
            (r'\[([^\]]+)\]\(([^)]+)\)', 'link'),  # 链接
        ]
        
        # 如果需要列表缩进
        if in_list:
            text_widget.insert(tk.END, '  ')
        
        # 解析并应用样式
        last_pos = 0
        i = 0
        
        while i < len(text):
            matched = False
            
            for pattern, tag in patterns:
                regex = re.compile(pattern)
                match = regex.match(text, i)
                
                if match:
                    # 插入之前的普通文本
                    if i > last_pos:
                        plain_text = text[last_pos:i]
                        text_widget.insert(tk.END, plain_text)
                    
                    # 插入带样式的文本
                    if tag == 'link':
                        link_text = match.group(1)
                        link_url = match.group(2)
                        text_widget.insert(tk.END, link_text, tag)
                        # 这里可以添加点击事件，但需要更复杂的处理
                    elif tag == 'image':
                        # 跳过图片
                        pass
                    else:
                        styled_text = match.group(1)
                        text_widget.insert(tk.END, styled_text, tag)
                    
                    last_pos = i + len(match.group(0))
                    i = last_pos
                    matched = True
                    break
            
            if not matched:
                i += 1
        
        # 插入剩余的普通文本
        if last_pos < len(text):
            plain_text = text[last_pos:]
            text_widget.insert(tk.END, plain_text)

    def start_update(self, dialog, download_url):
        """开始更新过程"""
        dialog.destroy()
        
        if not download_url:
            messagebox.showerror("更新失败", "无法获取下载链接，请手动下载。", parent=self.root)
            return
        
        # 显示进度对话框
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("正在更新")
        progress_dialog.transient(self.root)
        progress_dialog.geometry("400x180")
        progress_dialog.resizable(False, False)
        
        # 居中显示
        progress_dialog.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        x = parent_x + (parent_width - 400) // 2
        y = parent_y + (parent_height - 180) // 2
        progress_dialog.geometry(f"400x180+{x}+{y}")
        
        main_frame = ttk.Frame(progress_dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 网络状态显示
        network_status = "使用镜像下载" if os.environ.get('IS_CN') == 'yes' else "使用GitHub官方源"
        status_label = ttk.Label(main_frame, text=f"正在下载更新文件 ({network_status})...")
        status_label.pack(anchor=tk.W, pady=(0, 10))
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(main_frame, variable=progress_var, maximum=100, mode="determinate")
        progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        progress_text = ttk.Label(main_frame, text="准备下载...")
        progress_text.pack()
        
        # 进度回调函数
        def update_progress(current, total):
            if total > 0:
                percent = (current / total) * 100
                progress_var.set(percent)
                progress_text.config(text=f"{current / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB ({percent:.1f}%)")
                progress_dialog.update()
        
        # 在新线程中执行下载
        def download_and_install():
            try:
                # 创建临时文件
                temp_dir = tempfile.gettempdir()
                exe_path = os.path.join(temp_dir, f"Cai-Installer-Gui-Update-{int(time.time())}.exe")
                
                # 下载更新 - 使用优化后的下载方法
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    self.root.after(0, lambda: status_label.config(text="开始下载..."))
                    
                    success = loop.run_until_complete(
                        self.backend.download_update_with_mirror(download_url, exe_path, update_progress)
                    )
                    
                    if success:
                        self.log.info("更新文件下载成功")
                        self.root.after(0, lambda: status_label.config(text="下载完成，准备安装..."))
                        time.sleep(1)  # 给用户看到完成状态
                        self.root.after(0, progress_dialog.destroy)
                        self.root.after(0, lambda: self.launch_updater(exe_path))
                    else:
                        self.log.error("更新文件下载失败")
                        self.root.after(0, lambda: messagebox.showerror(
                            "更新失败", 
                            "无法下载更新文件，请稍后重试或手动下载。\n"
                            "您也可以前往项目主页手动下载最新版本：\n"
                            "https://github.com/WingChunWong/Cai-Installer-GUI/releases",
                            parent=self.root
                        ))
                        self.root.after(0, progress_dialog.destroy)
                except Exception as e:
                    self.log.error(f"更新下载过程中出现异常: {str(e)}")
                    self.root.after(0, lambda: messagebox.showerror(
                        "更新异常", 
                        f"更新过程中出现异常:\n{str(e)}\n"
                        "请尝试手动下载更新。",
                        parent=self.root
                    ))
                    self.root.after(0, progress_dialog.destroy)
                finally:
                    loop.close()
            except Exception as e:
                self.log.error(f"更新过程出错: {str(e)}")
                self.root.after(0, lambda: messagebox.showerror(
                    "更新失败", 
                    f"更新过程中发生错误:\n{str(e)}\n"
                    "请手动下载更新：https://github.com/WingChunWong/Cai-Installer-GUI/releases",
                    parent=self.root
                ))
                self.root.after(0, progress_dialog.destroy)
        
        threading.Thread(target=download_and_install, daemon=True).start()

    def launch_updater(self, exe_path):
        """启动更新程序并退出当前应用"""
        try:
            # 显示提示
            messagebox.showinfo("准备更新", "更新文件已下载完成，即将安装新版本。应用程序将关闭。")
            
            # 启动更新程序
            subprocess.Popen([exe_path])
            
            # 退出当前应用
            self.on_closing()
        except Exception as e:
            self.log.error(f"启动更新程序失败: {str(e)}")
            messagebox.showerror("启动失败", f"无法启动更新程序，请手动运行:\n{exe_path}")

    def run(self):
        """运行应用程序"""
        self.root.mainloop()

class ManualSelectionDialog(tk.Toplevel):
    def __init__(self, parent, title=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title or "选择解锁工具")
        self.result = None
        
        # 设置窗口大小
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
        
        steamtools_btn = ModernButton(button_frame, 
                                     text="我是 SteamTools 用户",
                                     command=lambda: self.ok("steamtools"),
                                     style='Accent.TButton')
        steamtools_btn.pack(fill=tk.X, pady=(0, 10))
        
        greenluma_btn = ModernButton(button_frame, 
                                    text="我是 GreenLuma 用户",
                                    command=lambda: self.ok("greenluma"))
        greenluma_btn.pack(fill=tk.X)
        
        self.wait_window(self)
    
    def ok(self, result):
        self.result = result
        self.destroy()

if __name__ == '__main__':
    # 启用DPI感知（仅Windows）
    if sys.platform == 'win32':
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    
    # 创建并运行应用
    app = CaiInstallGUI()
    app.run()