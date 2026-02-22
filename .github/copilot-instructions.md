# Project Guidelines

## Code Style

**语言与格式**
- Python 3.8+ 为主要语言
- 中文注释和字符串（面向中文用户）
- 类型注解：使用 `typing` 模块（`List`, `Dict`, `Optional`, `Tuple`）
- 命名约定：
  - 类：`PascalCase`（如 `GuiBackend`, `STConverter`）
  - 函数/方法：`snake_case`（如 `detect_steam_path`, `process_github_repo`）
  - 私有方法：单下划线前缀 `_method_name`
  - 配置键：`Snake_Case`（如 `Github_Personal_Token`）

**参考文件**
- [frontend_gui.py](../frontend_gui.py) - GUI 代码风格示例
- [backend_gui.py](../backend_gui.py) - 业务逻辑和类型注解示例

## Architecture

**前后端分离**
- [frontend_gui.py](../frontend_gui.py): tkinter GUI 层（1458行）
- [backend_gui.py](../backend_gui.py): 业务逻辑层（1275行）
- 通信方式：后端实例化时注入 logger，前端直接调用后端方法

**异步架构三层模型**
```python
# 典型异步任务启动模式 - frontend_gui.py 第832-850行
def start_processing(self):
    if not self.processing_lock.acquire(blocking=False):
        return  # 防止重复任务
    
    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = httpx.AsyncClient(verify=False, timeout=60.0)
        try:
            success = loop.run_until_complete(self.run_async_tasks(client, ...))
        finally:
            loop.run_until_complete(client.aclose())
            loop.close()
            self.processing_lock.release()
    
    threading.Thread(target=thread_target, daemon=True).start()
```

**关键原则**
1. GUI 更新使用 `root.after(0, callback)` 确保线程安全
2. 长任务在独立线程中运行新的 asyncio 事件循环
3. 使用 `threading.Lock()` 防止并发冲突
4. 后端方法统一使用 `async/await`

**数据流向**
```
用户输入 → GUI事件 → 工作线程 → asyncio事件循环 → 后端异步方法 
→ HTTP请求/文件操作 → 结果通过root.after()更新GUI
```

## Build and Test

**依赖安装**
```bash
pip install -r requirements.txt
```

**核心依赖**
- `httpx[http2]`: 异步 HTTP 客户端
- `aiofiles`: 异步文件操作
- `vdf`: Steam 配置文件解析
- `Nuitka`: 打包为独立 exe

**运行开发版本**
```bash
python frontend_gui.py
```

**打包（推测）**
```bash
nuitka --standalone --onefile --windows-disable-console \
  --include-data-files=version.py=version.py \
  frontend_gui.py
```

**路径兼容性**
- 使用 `get_app_dir()` 获取应用根目录（[backend_gui.py#L33](../backend_gui.py#L33)）
- 兼容 Nuitka/PyInstaller/cx_Freeze/开发环境

## Project Conventions

**配置管理**
- 位置：`{app_dir}/config.json`
- 默认配置：[backend_gui.py#L25](../backend_gui.py#L25)
- 自动修复：缺失字段自动补全，损坏时重新生成
- 编辑：GUI 菜单 → 设置 → 编辑配置

**路径处理**
```python
# 统一使用 pathlib.Path
from pathlib import Path
steam_path = Path("C:/Program Files (x86)/Steam")
config_path = steam_path / "config" / "config.vdf"
```

**错误处理三层模式**
```python
try:
    result = await some_operation()
except SpecificError as e:
    self.log.error(f"操作失败: {e}")
    return False
except Exception as e:
    self.log.error(f"未预期的错误: {self.stack_error(e)}")
    return False
finally:
    cleanup_resources()
```

**日志记录**
- 使用注入的 `self.log`
- 级别：`info`（常规）、`warning`（警告）、`error`（错误）
- GUI 中彩色显示（[frontend_gui.py#L382](../frontend_gui.py#L382)）

**版本管理**
- 版本号定义在 [version.py](../version.py)
- 格式：`__version__ = 'X.Y.Z'`
- 变更日志生成：`python scripts/generate_changelog.py`

## Integration Points

**Steam 集成**
- 路径检测：Windows 注册表 `HKEY_CURRENT_USER\Software\Valve\Steam`
- 配置文件：使用 `vdf` 库解析 `config.vdf`
- 进程控制：`taskkill /F /IM steam.exe` + `Steam.exe` 启动
- 双工具支持：
  - **SteamTools**: 生成 `.lua` 脚本到 `{steam}/config/stplug-in/`
  - **GreenLuma**: 修改 `config.vdf` + `AppList/*.txt`

**GitHub API**
- 请求头：[backend_gui.py#L275](../backend_gui.py#L275) - 支持 Personal Token
- 速率限制检查：调用前检查 `rate_limit` API
- 多源回退：国内用户使用 jsdelivr/ghfast/wget.la 镜像
- 分支信息：使用 GitHub Trees API 批量获取文件列表

**文件操作**
- 异步读写：`aiofiles` 库
- 临时目录：`{app_dir}/temp_cai_install`（用后清理）
- 备份策略：修改 `config.vdf` 前创建 `.vdf.bak`

**并行下载模式**
```python
# backend_gui.py 第632-645行
tasks = [self.download_item(client, item) for item in items]
results = await asyncio.gather(*tasks, return_exceptions=True)
for res in results:
    if isinstance(res, Exception):
        self.log.error(f"下载失败: {res}")
```

## Security

**敏感数据**
- GitHub Personal Token 存储在 `config.json`（明文）
- 建议提示用户：设置合理的过期时间，仅授予必要权限（`repo` 范围）

**HTTP 请求**
- 使用 `httpx.AsyncClient(verify=False)` 跳过 SSL 验证（CDN 兼容性）
- 超时设置：30-60秒
- User-Agent：`Cai-Installer-GUI/1.0`

**进程安全**
- Steam 重启前强制终止进程（`/F /T`）
- 等待 3 秒确保进程完全退出

## Common Patterns

**GUI 组件创建**
```python
# 使用 ttk 现代样式
frame = ttk.Frame(parent)
button = ttk.Button(frame, text="按钮", command=self.on_click)
entry = ttk.Entry(frame, textvariable=self.var)
```

**线程安全更新 GUI**
```python
self.root.after(0, self.update_status, "处理完成")
```

**异步文件操作**
```python
async with aiofiles.open(path, 'wb') as f:
    await f.write(content)
```

**日志输出**
```python
self.log.info("正在处理...")
self.log.warning("配置缺失，使用默认值")
self.log.error(f"失败: {e}")
```
