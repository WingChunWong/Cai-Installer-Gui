import sys
import os
import logging
import asyncio
import webbrowser
import tkinter as tk
from tkinter import BOTH, BOTTOM, DISABLED, EW, LEFT, NORMAL, RIGHT, SUNKEN, VERTICAL, W, X, Y, messagebox, scrolledtext
from pathlib import Path
import threading
from typing import List
try:
    import httpx # type: ignore
except ImportError:
    messagebox.showerror("依赖缺失", "错误: httpx 库未安装。\n请在命令行中使用 'pip install httpx' 命令安装后重试。")
    sys.exit(1)
import subprocess

try:
    import ttkbootstrap as ttk # type: ignore
    from ttkbootstrap.constants import * # type: ignore
except ImportError:
    messagebox.showerror("依赖缺失", "错误: ttkbootstrap 库未安装。\n请在命令行中使用 'pip install ttkbootstrap' 命令安装后重试。")
    sys.exit(1)

try:
    from backend_gui import GuiBackend
except ImportError:
    messagebox.showerror("文件缺失", "错误: backend_gui.py 文件缺失。\n请确保主程序和后端文件在同一个目录下。")
    sys.exit(1)

try:
    from version import version
except ImportError:
    version = "dev"

class SimpleNotepad(tk.Toplevel):
    """简单的文件编辑器"""
    def __init__(self, parent, filename, content, file_path):
        super().__init__(parent)
        self.transient(parent)
        self.title(f"编辑文件 - {filename}")
        self.file_path = Path(file_path)
        self.geometry("800x600")
        
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        ttk.Label(main_frame, text=f"文件: {filename}", font=("", 11, 'bold')).pack(pady=(0, 10), anchor=W)
        self.text_widget = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.text_widget.pack(fill=BOTH, expand=True)
        self.text_widget.insert(tk.END, content)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, pady=(15, 0))
        ttk.Button(button_frame, text="保存", command=self.save_file, style='success').pack(side=RIGHT, padx=5)
        ttk.Button(button_frame, text="关闭", command=self.destroy).pack(side=RIGHT)

    def save_file(self):
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
        
        body = ttk.Frame(self, padding=15)
        body.pack(fill=BOTH, expand=True)
        
        ttk.Label(body, text=f"找到 {len(games)} 个游戏，请选择一个：", font=("", 11, 'bold')).pack(pady=(0, 10), anchor=W)
        
        list_frame = ttk.Frame(body)
        list_frame.pack(fill=BOTH, expand=True)
        
        self.listbox = tk.Listbox(list_frame, font=("", 10), height=10)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        
        for game in games:
            name = game.get("schinese_name") or game.get("name", "N/A")
            appid = game['appid']
            self.listbox.insert(tk.END, f" {name} (AppID: {appid})")
        
        self.listbox.bind("<Double-Button-1>", self.ok)
        
        button_frame = ttk.Frame(body)
        button_frame.pack(fill=X, pady=(10, 0))
        ttk.Button(button_frame, text="确定", command=self.ok, style='success').pack(side=RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side=RIGHT)
    
    def ok(self, event=None):
        selections = self.listbox.curselection()
        if not selections:
            messagebox.showwarning("未选择", "请在列表中选择一个游戏。", parent=self)
            return
        self.result = self.games[selections[0]]
        self.destroy()

class CaiInstallGUI(ttk.Window):
    """主GUI类"""
    def __init__(self):
        super().__init__(themename="darkly", title=f"Cai Install GUI v{version}")
        self.geometry("1000x700")
        self.minsize(800, 600)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.processing_lock = threading.Lock()
        
        self.create_widgets()
        self.log = self.setup_logging()
        self.backend = GuiBackend(self.log)
        self.create_menu()
        
        # 设置为最大化
        self.state('zoomed')
        
        # 默认展开入库管理面板
        self.show_file_panel = True
        self.after(100, self.initialize_app)
    
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
                self.text_widget.tag_config('INFO', foreground='white')
                self.text_widget.tag_config('WARNING', foreground='yellow')
                self.text_widget.tag_config('ERROR', foreground='red')
                self.text_widget.tag_config('DEBUG', foreground='cyan')
            
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
        menu_bar = ttk.Menu(self)
        self.config(menu=menu_bar)
        
        settings_menu = ttk.Menu(menu_bar, tearoff=False)
        menu_bar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="编辑配置", command=self.show_settings_dialog)
        settings_menu.add_separator()
        settings_menu.add_command(label="退出", command=self.on_closing)
        
        help_menu = ttk.Menu(menu_bar, tearoff=False)
        menu_bar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="倒卖公告", command=lambda: webbrowser.open('https://docs.qq.com/doc/DTUp3Z2Fkd2pVRGtX?dver='))
        help_menu.add_command(label="项目地址", command=lambda: webbrowser.open('https://github.com/WingChunWong/Cai-Installer-GUI'))
        help_menu.add_command(label="关于", command=self.show_about_dialog)
    
    def create_widgets(self):
        """创建主界面控件"""
        # 主容器
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=BOTH, expand=True)
        
        # 左侧面板
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        
        # 输入区域
        input_frame = ttk.Labelframe(left_frame, text="游戏搜索与安装", padding=10)
        input_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(input_frame, text="AppID或游戏名称:").grid(row=0, column=0, sticky=W, pady=5)
        self.appid_entry = ttk.Entry(input_frame, font=("", 10))
        self.appid_entry.grid(row=0, column=1, sticky=EW, padx=5, pady=5)
        
        self.search_button = ttk.Button(input_frame, text="搜索", command=self.start_game_search, width=8)
        self.search_button.grid(row=0, column=2, pady=5)
        
        # 选项卡
        notebook = ttk.Notebook(left_frame)
        notebook.pack(fill=X, pady=5)
        
        # 保存notebook引用，供其他方法使用
        self.notebook = notebook
        
        # 指定库安装
        tab1 = ttk.Frame(notebook, padding=10)
        notebook.add(tab1, text="从指定库安装")
        
        ttk.Label(tab1, text="选择清单库:").pack(side=LEFT, padx=(0, 10))
        self.repo_options = [("SWA V2 (printedwaste)", "swa"), 
                             ("Cysaw", "cysaw"), 
                             ("Furcate", "furcate"), 
                             ("CNGS (assiw)", "cngs"),
                             ("SteamDatabase", "steamdatabase"), 
                             ("Walftech", "walftech"),
                             ("GitHub - Auiowu/ManifestAutoUpdate", "Auiowu/ManifestAutoUpdate"),
                             ("GitHub - SteamAutoCracks/ManifestHub", "SteamAutoCracks/ManifestHub"),
                             ]
        self.repo_combobox = ttk.Combobox(tab1, state="readonly", values=[name for name, _ in self.repo_options])
        self.repo_combobox.pack(side=LEFT, fill=X, expand=True)
        self.repo_combobox.current(0)
        
        # 搜索所有库
        tab2 = ttk.Frame(notebook, padding=10)
        notebook.add(tab2, text="搜索所有Github库")
        ttk.Label(tab2, text="此模式将搜索所有已知的GitHub清单库").pack(fill=X)
        
        # 按钮区域
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=X, pady=10)
        
        self.process_button = ttk.Button(button_frame, text="开始处理", command=self.start_processing, style='success')
        self.process_button.pack(side=LEFT, padx=(0, 10))
        
        self.manager_button = ttk.Button(button_frame, text="入库管理", command=self.toggle_file_panel, style='info')
        self.manager_button.pack(side=LEFT)
        
        # 日志区域
        log_frame = ttk.Labelframe(left_frame, text="日志输出", padding=10)
        log_frame.pack(fill=BOTH, expand=True)
        
        # 日志工具栏
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=X, pady=(0, 5))
        ttk.Button(log_toolbar, text="清空日志", command=self.clear_log).pack(side=LEFT)
        ttk.Button(log_toolbar, text="复制日志", command=self.copy_log).pack(side=LEFT, padx=5)
        
        self.log_text_widget = scrolledtext.ScrolledText(
            log_frame, 
            wrap=tk.WORD, 
            state='disabled', 
            font=("Consolas", 10)  # 这里修改字体和大小
        )
        self.log_text_widget.pack(fill=BOTH, expand=True)
        
        # 状态栏
        self.status_bar = ttk.Label(self, text="正在初始化...", relief=SUNKEN, anchor=W, padding=5)
        self.status_bar.pack(side=BOTTOM, fill=X)
        
        # 入库管理面板
        self.file_panel = self.create_file_panel(main_frame)
        # 默认展开入库管理面板
        self.file_panel.pack(side=RIGHT, fill=Y)
        
        # 设置按钮样式为选中状态 - 使用bootstyle而不是style
        self.manager_button.configure(bootstyle="info-outline")
    
    def create_file_panel(self, parent):
        """创建入库管理面板"""
        panel = ttk.Labelframe(parent, text="入库管理", padding=10)
        
        # 按钮工具栏
        button_frame = ttk.Frame(panel)
        button_frame.pack(fill=X, pady=(0, 5))
        
        ttk.Button(button_frame, text="🔄刷新", command=self.refresh_file_list, bootstyle="info").grid(row=0, column=0, padx=(0, 2), sticky=EW)
        ttk.Button(button_frame, text="📝查看", command=self.view_selected_file, bootstyle="success").grid(row=0, column=1, padx=2, sticky=EW)
        ttk.Button(button_frame, text="❌删除", command=self.delete_selected_file, bootstyle="danger").grid(row=0, column=2, padx=2, sticky=EW)
        ttk.Button(button_frame, text="🔄重启Steam", command=self.restart_steam, bootstyle="warning").grid(row=0, column=3, padx=(2, 0), sticky=EW)
        
        for i in range(4):
            button_frame.columnconfigure(i, weight=1)
        
        # 文件列表
        list_frame = ttk.Frame(panel)
        list_frame.pack(fill=BOTH, expand=True, pady=(5, 0))
        
        self.file_list = tk.Listbox(list_frame, font=("Consolas", 9), selectmode=tk.EXTENDED)
        self.file_list.pack(side=LEFT, fill=BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.file_list.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.file_list.config(yscrollcommand=scrollbar.set)
        
        self.file_list.bind("<Double-Button-1>", lambda e: self.view_selected_file())
        
        return panel
    
    def clear_log(self):
        """清空日志"""
        self.log_text_widget.configure(state='normal')
        self.log_text_widget.delete(1.0, tk.END)
        self.log_text_widget.configure(state='disabled')
    
    def copy_log(self):
        """复制日志内容到剪贴板"""
        content = self.log_text_widget.get(1.0, tk.END)
        if content.strip():
            self.clipboard_clear()
            self.clipboard_append(content)
            messagebox.showinfo("成功", "日志内容已复制到剪贴板")
    
    def toggle_file_panel(self):
        """切换入库管理面板显示"""
        if self.file_panel.winfo_ismapped():
            self.file_panel.pack_forget()
            self.geometry("800x700")
            self.manager_button.configure(bootstyle="info")
            self.show_file_panel = False
        else:
            self.file_panel.pack(side=RIGHT, fill=Y)
            self.geometry("1000x700")
            self.manager_button.configure(bootstyle="info-outline")
            self.show_file_panel = True
            self.refresh_file_list()
    
    def refresh_file_list(self):
        """刷新文件列表"""
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
        """获取选中的文件列表"""
        selected_indices = self.file_list.curselection()
        if not selected_indices:
            return []
        return [self.file_list.get(i).strip() for i in selected_indices]
    
    def delete_selected_file(self):
        """删除选中的文件"""
        filenames = self.get_selected_files()
        if not filenames:
            messagebox.showinfo("提示", "请先在列表中选择要删除的文件。", parent=self)
            return
        
        msg = f"确定要删除这 {len(filenames)} 个文件吗？\n此操作不可恢复！" if len(filenames) > 1 else f"确定要删除 {filenames[0]} 吗？\n此操作不可恢复！"
        
        if not messagebox.askyesno("确认删除", msg, parent=self):
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
            messagebox.showwarning("部分失败", "以下文件删除失败:\n" + "\n".join(failed_files), parent=self)
    
    def view_selected_file(self):
        """查看选中的文件"""
        filenames = self.get_selected_files()
        if not filenames:
            messagebox.showinfo("提示", "请选择一个文件进行查看。", parent=self)
            return
        
        if len(filenames) > 1:
            messagebox.showinfo("提示", "请只选择一个文件进行查看。", parent=self)
            return
        
        filename = filenames[0]
        try:
            file_path = self.backend.steam_path / "config" / "stplug-in" / filename
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                SimpleNotepad(self, filename, content, str(file_path))
            else:
                messagebox.showerror("错误", "文件不存在。", parent=self)
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}", parent=self)
    
    def initialize_app(self):
        """初始化应用"""
        self.print_banner()
        self.log.info("Cai Installer GUI版 - 正在初始化...")
        self.backend.load_config()
        self.update_unlocker_status()
        
        # 刷新文件列表
        if self.show_file_panel:
            self.refresh_file_list()
        
        self.log.info("软件作者: pvzcxw 二改: WingChunWong")
        self.log.info("本项目采用GNU GPLv3开源许可证，完全免费，请勿用于商业用途。")
    
    def print_banner(self):
        """打印欢迎横幅"""
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
        """更新解锁工具状态"""
        steam_path = self.backend.detect_steam_path()
        if not steam_path.exists():
            self.status_bar.config(text="Steam路径未找到！请在设置中指定。")
            messagebox.showerror('Steam未找到', "无法自动检测到Steam路径。\n请在\"设置\"->\"编辑配置\"中手动指定路径。")
            return
        
        status = self.backend.detect_unlocker()
        if status == "conflict":
            messagebox.showerror("环境冲突", "错误: 同时检测到 SteamTools 和 GreenLuma！\n请手动卸载其中一个以避免冲突，然后重启本程序。")
            self.process_button.config(state=DISABLED)
            self.status_bar.config(text="环境冲突！请解决后重启。")
        elif status == "none":
            self.handle_manual_selection()
        
        if self.backend.unlocker_type:
            self.status_bar.config(text=f"Steam路径: {steam_path} | 解锁方式: {self.backend.unlocker_type.title()}")
    
    def handle_manual_selection(self):
        """手动选择解锁工具"""
        dialog = ManualSelectionDialog(self, title="选择解锁工具")
        self.wait_window(dialog)
        
        if dialog.result in ["steamtools", "greenluma"]:
            self.backend.unlocker_type = dialog.result
            self.log.info(f"已手动选择解锁方式: {dialog.result.title()}")
            self.update_unlocker_status()
        else:
            self.log.error("未选择解锁工具，部分功能可能无法正常工作。")
            self.status_bar.config(text="未选择解锁工具！")
            self.process_button.config(state=DISABLED)
    
    def start_game_search(self):
        """开始游戏搜索"""
        if not self.processing_lock.acquire(blocking=False):
            self.log.warning("已在处理中，请等待当前任务完成。")
            return
        
        async def process_by_searching_all(self, client, app_id_inputs, github_repos):
            raise NotImplementedError

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
                self.after(0, self.show_game_selection_dialog, games)
            finally:
                loop.run_until_complete(client.aclose())
                loop.close()
                self.processing_lock.release()
                self.after(0, self.search_finished)
        
        self.search_button.config(state=DISABLED, text="搜索中...")
        threading.Thread(target=thread_target, daemon=True).start()
    
    def search_finished(self):
        """搜索完成后的回调"""
        self.search_button.config(state=NORMAL, text="搜索")
    
    def show_game_selection_dialog(self, games):
        """显示游戏选择对话框"""
        if not games:
            self.log.warning("未找到匹配的游戏。")
            messagebox.showinfo("未找到", "未找到与搜索词匹配的游戏。", parent=self)
            return
        
        dialog = GameSelectionDialog(self, games=games)
        if dialog.result:
            selected_game = dialog.result
            self.appid_entry.delete(0, tk.END)
            self.appid_entry.insert(0, selected_game['appid'])
            name = selected_game.get("schinese_name") or selected_game.get("name", "N/A")
            self.log.info(f"已选择游戏: {name} (AppID: {selected_game['appid']})")
    
    def start_processing(self):
        """开始处理任务"""
        if not self.backend.unlocker_type:
            messagebox.showerror("错误", "未确定解锁工具！\n请先通过设置或重启程序解决解锁工具检测问题。")
            return
        
        if not self.processing_lock.acquire(blocking=False):
            self.log.warning("已在处理中，请等待当前任务完成。")
            return
        
        # 当ST自动更新模式启用时，默认使用浮动版本
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
                    self.after(0, self.auto_restart_steam, "游戏入库")
            finally:
                loop.run_until_complete(client.aclose())
                loop.close()
                self.processing_lock.release()
                self.after(0, self.processing_finished)
        
        self.process_button.config(state=DISABLED, text="正在处理...")
        self.appid_entry.config(state=DISABLED)
        self.search_button.config(state=DISABLED)
        self.status_bar.config(text="正在处理...")
        
        threading.Thread(target=thread_target, daemon=True).start()
    
    def processing_finished(self):
        """处理完成后的回调"""
        self.process_button.config(state=NORMAL, text="开始处理")
        self.appid_entry.config(state=NORMAL)
        self.search_button.config(state=NORMAL)
        self.status_bar.config(text="处理完成，准备就绪。")
        self.log.info("=" * 60 + "\n处理完成！您可以开始新的任务。")
    
    async def run_async_tasks(self, client: httpx.AsyncClient, tab_index: int):
        """运行异步任务"""
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
                github_repos = [val for _, val in self.repo_options if val not in ["swa", "cysaw", "furcate", "cngs", "steamdatabase"]]
                success = await self.backend.process_by_searching_all(client, app_id_inputs, github_repos)
                return success
            return False
        finally:
            await self.backend.cleanup_temp_files()
    
    def on_closing(self):
        """关闭窗口时的处理"""
        if self.processing_lock.locked():
            if messagebox.askyesno("退出", "正在处理任务，确定要强制退出吗？"):
                os._exit(0)
        else:
            self.destroy()
    
    def show_about_dialog(self):
        """显示关于对话框"""
        messagebox.showinfo("关于", "Cai Install GUI\n\n一个用于Steam游戏清单获取和导入的工具\n\n作者: pvzcxw\n二改: WingChunWong")
    
    def show_settings_dialog(self):
        """显示设置对话框"""
        dialog = ttk.Toplevel(self) # type: ignore
        dialog.title("编辑配置")
        dialog.geometry("500x250")
        dialog.transient(self)
        
        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=BOTH, expand=True)
        
        ttk.Label(frame, text="GitHub Personal Token:").grid(row=0, column=0, sticky=W, pady=5)
        token_entry = ttk.Entry(frame, width=40)
        token_entry.grid(row=0, column=1, sticky=EW, pady=5)
        token_entry.insert(0, self.backend.app_config.get("Github_Personal_Token", ""))
        
        ttk.Label(frame, text="自定义Steam路径:").grid(row=1, column=0, sticky=W, pady=5)
        path_entry = ttk.Entry(frame, width=40)
        path_entry.grid(row=1, column=1, sticky=EW, pady=5)
        path_entry.insert(0, self.backend.app_config.get("Custom_Steam_Path", ""))
        
        st_lua_only_var = tk.BooleanVar(value=self.backend.app_config.get("steamtools_only_lua", False))
        st_lua_only_check = ttk.Checkbutton(frame, text="使用SteamTools自动更新模式", variable=st_lua_only_var)
        st_lua_only_check.grid(row=2, column=0, columnspan=2, sticky=W, pady=10)
        
        auto_restart_var = tk.BooleanVar(value=self.backend.app_config.get("auto_restart_steam", True))
        auto_restart_check = ttk.Checkbutton(frame, text="入库后自动重启Steam", variable=auto_restart_var)
        auto_restart_check.grid(row=3, column=0, columnspan=2, sticky=W, pady=5)
        
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=15)
        
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
        
        ttk.Button(button_frame, text="保存", command=save_and_close, bootstyle="success").pack(side=LEFT, padx=10)
        ttk.Button(button_frame, text="取消", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT)
        
        frame.columnconfigure(1, weight=1)
    
    def restart_steam(self):
        """手动重启Steam"""
        if not self.backend.steam_path or not self.backend.steam_path.exists():
            messagebox.showerror("错误", "未找到Steam安装路径！", parent=self)
            return
        
        steam_exe = self.backend.steam_path / "Steam.exe"
        if not steam_exe.exists():
            messagebox.showerror("错误", f"未找到Steam.exe文件！", parent=self)
            return
        
        if not messagebox.askyesno("确认重启", "确定要重启Steam吗？", parent=self):
            return
        
        self._perform_steam_restart("手动重启")
    
    def auto_restart_steam(self, reason="操作完成"):
        """自动重启Steam"""
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
        """执行Steam重启"""
        try:
            steam_exe = self.backend.steam_path / "Steam.exe"
            
            # 结束Steam进程
            try:
                subprocess.run(['taskkill', '/F', '/IM', 'steam.exe', '/T'],
                             capture_output=True, shell=True, text=True)
            except Exception:
                pass
            
            import time
            time.sleep(3)
            
            # 重新启动Steam
            subprocess.Popen([str(steam_exe)], shell=True)
            self.log.info(f"{reason}完成，已重新启动Steam")
            
            self.after(0, lambda: messagebox.showinfo("Steam重启", 
                "Steam已自动重启！\n请等待Steam完全启动后检查库中游戏。", parent=self))
            
        except Exception as e:
            self.log.error(f"重启Steam失败: {e}")
            self.after(0, lambda: messagebox.showerror("重启失败", 
                f"重启Steam失败:\n{e}\n请手动重启Steam。", parent=self))

class ManualSelectionDialog(tk.Toplevel):
    """手动选择解锁工具对话框"""
    def __init__(self, parent, title=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.result = None
        
        body = ttk.Frame(self, padding=20)
        body.pack()
        
        ttk.Label(body, text="未能自动检测到解锁工具。\n请根据您的实际情况选择：", justify=LEFT).pack(pady=10)
        
        ttk.Button(body, text="我是 SteamTools 用户", command=lambda: self.ok("steamtools")).pack(fill=X, pady=5)
        ttk.Button(body, text="我是 GreenLuma 用户", command=lambda: self.ok("greenluma")).pack(fill=X, pady=5)
        
        self.geometry(f"+{parent.winfo_rootx()+50}+{parent.winfo_rooty()+50}")
        self.wait_window(self)
    
    def ok(self, result):
        self.result = result
        self.destroy()

if __name__ == '__main__':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    
    app = CaiInstallGUI()
    app.mainloop()