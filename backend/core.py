import os
import sys
import traceback
import asyncio
import re
import json
import zipfile
import shutil
import time
from pathlib import Path
from typing import Tuple, List, Dict, Optional, Any
import logging
import winreg

# 延迟导入依赖库
try:
    import aiofiles
    import httpx
    import vdf
except ImportError as e:
    raise ImportError(f"缺少依赖库: {e}. 请使用 'pip install aiofiles httpx vdf' 安装。")

# 从 backend 包导入
from .io import get_app_dir, DEFAULT_CONFIG
from .stconverter import STConverter
from .github import GithubClient

app_dir = get_app_dir()

class GuiBackend:
    """GUI后端处理类"""
    
    def __init__(self, logger: logging.Logger):
        self.log = logger
        self.st_converter = STConverter(self.log)
        self.github_client = GithubClient(self.log, DEFAULT_CONFIG)
        self.app_config = DEFAULT_CONFIG.copy()
        self.github_client.app_config = self.app_config  # 使用相同的配置引用
        self.steam_path = Path()
        self.unlocker_type: Optional[str] = None
        self.temp_dir = app_dir / 'temp_cai_install'
        self.st_lock_manifest_version = False
    
    def stack_error(self, e: Exception) -> str:
        """获取完整的异常堆栈信息"""
        return ''.join(traceback.format_exception(type(e), e, e.__traceback__))
    
    # ========== GitHub 客户端委托方法 ==========
    def get_github_headers(self) -> Dict[str, str]:
        """委托给 github_client（获取GitHub请求头）"""
        return self.github_client.get_github_headers()
    
    async def get_client(self) -> httpx.AsyncClient:
        """委托给 github_client（获取或创建HTTP客户端）"""
        return await self.github_client.get_client()
    
    async def close_client(self) -> None:
        """委托给 github_client（关闭HTTP客户端）"""
        return await self.github_client.close_client()
    
    async def check_github_api_rate_limit(self, client: httpx.AsyncClient, headers: dict) -> bool:
        """委托给 github_client（检查GitHub API速率限制）"""
        return await self.github_client.check_github_api_rate_limit(client, headers)
    
    async def checkcn(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """委托给 github_client（检测是否在中国大陆）"""
        return await self.github_client.checkcn(client)
    
    def get_current_country(self) -> str:
        """委托给 github_client（获取当前检测到的国家代码）"""
        return self.github_client.get_current_country()
    
    async def fetch_branch_info(self, client: httpx.AsyncClient, url: str, headers: dict) -> Optional[Dict[str, Any]]:
        """委托给 github_client（获取分支信息）"""
        return await self.github_client.fetch_branch_info(client, url, headers)
    
    async def get_from_url(self, client: httpx.AsyncClient, sha: str, path: str, repo: str) -> bytes:
        """委托给 github_client（从URL下载内容）"""
        return await self.github_client.get_from_url(client, sha, path, repo)
    
    def extract_app_id(self, user_input: str) -> Optional[str]:
        """委托给 github_client（从输入中提取AppID）"""
        return self.github_client.extract_app_id(user_input)
    
    async def resolve_appids(self, inputs: List[str]) -> List[str]:
        """委托给 github_client（解析多个AppID）"""
        return await self.github_client.resolve_appids(inputs)
    
    async def search_all_repos(self, client: httpx.AsyncClient, app_id: str, repos: List[str]) -> List[Dict[str, Any]]:
        """委托给 github_client（在所有仓库中搜索）"""
        return await self.github_client.search_all_repos(client, app_id, repos)
    
    async def check_for_updates(self, current_version: str) -> Dict[str, Any]:
        """委托给 github_client（检查更新）"""
        return await self.github_client.check_for_updates(current_version)
    
    def is_newer_version(self, latest: str, current: str) -> bool:
        """委托给 github_client（比较版本号）"""
        return self.github_client.is_newer_version(latest, current)
    
    def convert_github_to_mirror(self, github_url: str) -> str:
        """委托给 github_client（转换为国内镜像地址）"""
        return self.github_client.convert_github_to_mirror(github_url)
    
    async def download_update_direct(self, url: str, dest_path: str, progress_callback=None) -> bool:
        """委托给 github_client（直接下载更新文件）"""
        return await self.github_client.download_update_direct(url, dest_path, progress_callback)

    def load_config(self) -> None:
        """加载配置文件"""
        config_path = app_dir / 'config.json'
        
        if not config_path.exists():
            self.gen_config_file()
            return
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
            
            # 验证配置完整性
            for key, value in DEFAULT_CONFIG.items():
                if key not in loaded_config:
                    loaded_config[key] = value
            
            self.app_config = loaded_config
            
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.log.error(f"配置文件格式错误，将重置: {e}")
            config_path.unlink(missing_ok=True)
            self.gen_config_file()
        except Exception as e:
            self.log.error(f"配置文件加载失败，将重置: {self.stack_error(e)}")
            config_path.unlink(missing_ok=True)
            self.gen_config_file()
    
    def gen_config_file(self) -> None:
        """生成默认配置文件"""
        # 提前绑定变量，避免在异常处理时引用未定义的名称
        config_path = app_dir / "config.json"
        try:
            self.log.info(f"生成配置文件: {config_path}")

            with open(config_path, mode="w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)

            self.app_config = DEFAULT_CONFIG.copy()
            self.log.info('配置文件已生成，请在"设置"中填写。')

        except Exception as e:
            # config_path 已在函数开始处定义，可安全引用
            self.log.error(f'配置文件生成失败: {config_path}, 错误={self.stack_error(e)}')
    
    def save_config(self) -> bool:
        """保存配置文件"""
        # 预先绑定一个安全的默认值，避免在 except 中引用未定义变量
        config_path: Path = Path()
        try:
            config_path = app_dir / "config.json"
            self.log.info(f"保存配置文件: {config_path}")
            
            # 创建备份
            if config_path.exists():
                backup_path = config_path.with_suffix('.json.bak')
                shutil.copy2(config_path, backup_path)
            
            with open(config_path, mode="w", encoding="utf-8") as f:
                json.dump(self.app_config, f, indent=2, ensure_ascii=False)
            
            self.log.info('配置文件保存成功。')
            return True
            
        except Exception as e:
            # 在此处安全引用 config_path
            self.log.error(f'保存配置失败: {config_path}, 错误={self.stack_error(e)}')
            return False
    
    def detect_steam_path(self) -> Path:
        """检测Steam安装路径"""
        try:
            custom_path = self.app_config.get("Custom_Steam_Path", "").strip()
            
            # 优先使用自定义路径
            if custom_path:
                custom_path_obj = Path(custom_path)
                if custom_path_obj.exists():
                    self.steam_path = custom_path_obj.resolve()
                    self.log.info(f"使用自定义Steam路径: {self.steam_path}")
                    return self.steam_path
                else:
                    self.log.warning(f"自定义Steam路径不存在: {custom_path}")

            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
                steam_path_str = winreg.QueryValueEx(key, 'SteamPath')[0]
                self.steam_path = Path(steam_path_str).resolve()
                self.log.info(f"自动检测到Steam路径: {self.steam_path}")
                return self.steam_path
            except (OSError, FileNotFoundError) as e:
                self.log.warning(f"注册表查询失败: {e}")

                
                # 尝试常见路径
                common_paths = [
                    Path("C:/Program Files (x86)/Steam"),
                    Path("C:/Program Files/Steam"),
                ]
            
            for path in common_paths:
                if path.exists():
                    self.steam_path = path.resolve()
                    self.log.info(f"找到Steam路径: {self.steam_path}")
                    return self.steam_path
            
            self.log.error('Steam路径获取失败，请检查Steam是否安装或在设置中指定路径。')
            self.steam_path = Path()
            return self.steam_path
            
        except Exception as e:
            self.log.error(f'Steam路径检测失败: {self.stack_error(e)}')
            self.steam_path = Path()
            return self.steam_path
    
    def detect_unlocker(self) -> str:
        """检测解锁工具类型"""
        if not self.steam_path.exists():
            return "none"
        
        # 检测SteamTools
        steamtools_dir = self.steam_path / 'config' / 'stplug-in'
        is_steamtools = steamtools_dir.is_dir()
        
        # 检测GreenLuma
        greenluma_dlls = ['GreenLuma_2025_x86.dll', 'GreenLuma_2025_x64.dll']
        is_greenluma = any((self.steam_path / dll).exists() for dll in greenluma_dlls)
        
        if is_steamtools and is_greenluma:
            self.log.error("环境冲突：同时检测到SteamTools和GreenLuma！")
            return "conflict"
        elif is_steamtools:
            self.log.info("检测到解锁工具: SteamTools")
            self.unlocker_type = "steamtools"
            return "steamtools"
        elif is_greenluma:
            self.log.info("检测到解锁工具: GreenLuma")
            self.unlocker_type = "greenluma"
            return "greenluma"
        else:
            self.log.warning("未能自动检测到解锁工具。")
            return "none"
    
    def is_steamtools(self) -> bool:
        """是否为SteamTools"""
        return self.unlocker_type == "steamtools"
    

    async def process_github_repo(self, client: httpx.AsyncClient, app_id: str, repo: str, 
                                existing_data: Optional[Dict[str, Any]] = None) -> bool:
        """处理GitHub仓库"""
        try:
            headers = self.get_github_headers()
            
            if existing_data:
                sha = existing_data['sha']
                tree = existing_data['tree']
                date = existing_data['update_date']
            else:
                branch_url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
                branch_info = await self.fetch_branch_info(client, branch_url, headers)
                
                if not branch_info:
                    return False
                
                sha = branch_info['commit']['sha']
                date = branch_info['commit']['commit']['author']['date']
                
                tree_url = branch_info['commit']['commit']['tree']['url']
                tree_info = await self.fetch_branch_info(client, tree_url, headers)
                
                if not tree_info:
                    return False
                
                tree = tree_info['tree']
            
            # 获取所有清单文件
            all_manifests = [item['path'] for item in tree if item['path'].endswith('.manifest')]
            
            if not all_manifests:
                self.log.error(f'仓库中没有找到清单文件: {app_id}')
                return False
            
            # 并行下载和处理文件
            tasks = []
            for item in tree:
                tasks.append(
                    self.get_manifest_from_github(client, sha, item['path'], repo, app_id, all_manifests)
                )
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            collected_depots = []
            for res in results:
                # 如果是异常，记录错误并继续
                if isinstance(res, Exception):
                    self.log.error(f"下载/处理文件时出错: {res}")
                    continue
                
                # 确保 res 是列表类型（来自 get_manifest_from_github 的返回值）
                if isinstance(res, list):
                    collected_depots.extend(res)
                elif res:  # 如果 res 不是列表也不是None，可能有问题
                    self.log.warning(f"忽略非列表类型的返回结果: {type(res)}")
            
            if not collected_depots:
                self.log.error(f'未能收集到任何密钥信息: {app_id}')
                return False
            
            # 根据解锁工具类型处理
            if self.is_steamtools():
                self.log.info('检测到SteamTools，已自动生成并放置解锁文件。')
            else:
                depot_ids = [app_id] + [depot_id for depot_id, _ in collected_depots]
                await self.greenluma_add(depot_ids)
                
                depot_config = {'depots': {depot_id: {'DecryptionKey': key} 
                                        for depot_id, key in collected_depots}}
                await self.depotkey_merge(depot_config)
            
            self.log.info(f'清单最后更新时间: {date}')
            return True
            
        except Exception as e:
            self.log.error(f"处理GitHub仓库时出错: {self.stack_error(e)}")
            return False
    
    async def get_manifest_from_github(self, client: httpx.AsyncClient, sha: str, path: str, 
                                     repo: str, app_id: str, all_manifests: List[str]) -> List[Tuple[str, str]]:
        """从GitHub获取清单文件"""
        is_st_auto_update_mode = self.is_steamtools() and self.app_config.get("steamtools_only_lua", False)
        
        # 跳过清单文件下载（如果启用了ST自动更新模式）
        if path.endswith('.manifest') and is_st_auto_update_mode:
            self.log.info(f"ST自动更新模式: 已跳过清单文件下载: {path}")
            return []
        
        try:
            content = await self.get_from_url(client, sha, path, repo)
        except Exception as e:
            self.log.error(f"下载文件失败: {path} - {e}")
            return []
        
        depots = []
        stplug = self.steam_path / 'config' / 'stplug-in'
        
        # 处理清单文件
        if path.endswith('.manifest') and not is_st_auto_update_mode:
            depot_cache = self.steam_path / 'depotcache'
            cfg_depot_cache = self.steam_path / 'config' / 'depotcache'
            
            for p in [depot_cache, cfg_depot_cache, stplug]:
                p.mkdir(parents=True, exist_ok=True)
            
            for p in [depot_cache, cfg_depot_cache]:
                manifest_path = p / Path(path).name
                manifest_path.write_bytes(content)
            
            self.log.info(f'清单已保存: {path}')
        
        # 处理密钥文件
        elif "key.vdf" in path.lower():
            try:
                depots_cfg = vdf.loads(content.decode('utf-8'))
                depots = [(depot_id, info['DecryptionKey']) 
                         for depot_id, info in depots_cfg.get('depots', {}).items()]
                
                # 为SteamTools创建LUA脚本
                if self.is_steamtools() and app_id:
                    lua_path = stplug / f"{app_id}.lua"
                    is_floating_version = is_st_auto_update_mode and not self.st_lock_manifest_version
                    
                    with open(lua_path, "w", encoding="utf-8") as f:
                        f.write(f'addappid({app_id}, 1, "None")\n')
                        for depot_id, key in depots:
                            f.write(f'addappid({depot_id}, 1, "{key}")\n')
                        
                        for mf_path in all_manifests:
                            if m := re.search(r'(\d+)_(\w+)\.manifest', mf_path):
                                line = f'setManifestid({m.group(1)}, "{m.group(2)}")\n'
                                if is_floating_version:
                                    f.write('--' + line)
                                else:
                                    f.write(line)
                    
                    self.log.info(f'Lua脚本创建成功: {lua_path}')
                    
            except (UnicodeDecodeError, KeyError) as e:
                self.log.error(f"解析密钥文件失败: {path} - {e}")
        
        return depots
    
    async def depotkey_merge(self, depots_config: Dict[str, Any]) -> bool:
        """合并密钥到config.vdf"""
        config_path = self.steam_path / 'config' / 'config.vdf'
        
        if not config_path.exists():
            self.log.error('Steam默认配置(config.vdf)不存在')
            return False
        
        try:
            # 读取现有配置
            with open(config_path, 'r', encoding='utf-8') as f:
                config = vdf.loads(f.read())
            
            # 查找Steam配置节
            steam_section = (config.get('InstallConfigStore', {})
                                       .get('Software', {})
                                       .get('Valve') or 
                            config.get('InstallConfigStore', {})
                                   .get('Software', {})
                                   .get('valve'))
            
            if not steam_section:
                self.log.error('找不到Steam配置节')
                return False
            
            # 合并密钥
            if 'depots' not in steam_section:
                steam_section['depots'] = {}
            
            steam_section['depots'].update(depots_config.get('depots', {}))
            
            # 写入配置（创建备份）
            backup_path = config_path.with_suffix('.vdf.bak')
            if not backup_path.exists():
                shutil.copy2(config_path, backup_path)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(vdf.dumps(config, pretty=True))
            
            self.log.info('密钥成功合并到 config.vdf。')
            return True
            
        except Exception as e:
            self.log.error(f'合并密钥失败: {self.stack_error(e)}')
            return False
    
    async def greenluma_add(self, depot_id_list: List[str]) -> bool:
        """为GreenLuma添加解锁文件"""
        try:
            app_list_path = self.steam_path / 'AppList'
            app_list_path.mkdir(parents=True, exist_ok=True)
            
            for appid in depot_id_list:
                if not appid.isdigit():
                    self.log.warning(f"跳过非数字AppID: {appid}")
                    continue
                    
                file_path = app_list_path / f'{appid}.txt'
                file_path.write_text(str(appid), encoding='utf-8')
            
            self.log.info(f"已为GreenLuma添加 {len(depot_id_list)} 个AppID")
            return True
            
        except Exception as e:
            self.log.error(f'为GreenLuma添加解锁文件时出错: {e}')
            return False
    
    async def _process_zip_based_manifest(self, client: httpx.AsyncClient, app_id: str, 
                                        download_url: str, source_name: str) -> bool:
        """处理基于ZIP的清单文件"""
        try:
            # 清理并创建临时目录
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir.mkdir(exist_ok=True)
            
            self.log.info(f'[{source_name}] 正在下载清单文件: {download_url}')
            
            # 下载ZIP文件
            async with client.stream("GET", download_url, timeout=60) as r:
                if r.status_code != 200:
                    self.log.error(f'[{source_name}] 下载失败: 状态码 {r.status_code}')
                    return False
                
                zip_path = self.temp_dir / f'{app_id}.zip'
                async with aiofiles.open(zip_path, 'wb') as f:
                    async for chunk in r.aiter_bytes():
                        await f.write(chunk)
            
            self.log.info(f'[{source_name}] 正在解压文件...')
            
            # 解压文件
            extract_path = self.temp_dir / app_id
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_path)
            
            # 查找各种文件
            manifest_files = list(extract_path.glob('*.manifest'))
            lua_files = list(extract_path.glob('*.lua'))
            st_files = list(extract_path.glob('*.st'))
            
            # 转换ST文件为LUA
            for st_file in st_files:
                try:
                    lua_path = st_file.with_suffix('.lua')
                    lua_content = self.st_converter.convert_file(str(st_file))
                    
                    async with aiofiles.open(lua_path, 'w', encoding='utf-8') as f:
                        await f.write(lua_content)
                    
                    lua_files.append(lua_path)
                    self.log.info(f'已转换ST文件: {st_file.name}')
                    
                except Exception as e:
                    self.log.error(f'转换ST文件失败: {st_file.name} - {e}')
            
            # 处理模式
            is_st_auto_update_mode = self.is_steamtools() and self.app_config.get("steamtools_only_lua", False)
            is_floating_version = is_st_auto_update_mode and not self.st_lock_manifest_version
            
            # SteamTools模式
            if self.is_steamtools():
                st_plug = self.steam_path / 'config' / 'stplug-in'
                st_plug.mkdir(parents=True, exist_ok=True)
                
                # 标准模式：复制清单文件
                if not is_st_auto_update_mode:
                    st_depot_path = self.steam_path / 'config' / 'depotcache'
                    gl_depot_path = self.steam_path / 'depotcache'
                    
                    st_depot_path.mkdir(parents=True, exist_ok=True)
                    gl_depot_path.mkdir(parents=True, exist_ok=True)
                    
                    if manifest_files:
                        for manifest_file in manifest_files:
                            shutil.copy2(manifest_file, st_depot_path)
                            shutil.copy2(manifest_file, gl_depot_path)
                        
                        self.log.info(f"[{source_name}] 已复制 {len(manifest_files)} 个清单文件")
                    else:
                        self.log.warning(f"[{source_name}] 未找到 .manifest 文件")
                
                # 自动更新模式
                else:
                    self.log.info(f"[{source_name}] ST自动更新模式: 已跳过.manifest 文件")
                
                # 创建或合并LUA脚本
                lua_filename = f"{app_id}.lua"
                lua_filepath = st_plug / lua_filename
                
                all_depots = {}
                for lua_file in lua_files:
                    try:
                        with open(lua_file, 'r', encoding='utf-8') as f_in:
                            content = f_in.read()
                            
                        # 提取密钥信息
                        for m in re.finditer(r'addappid\((\d+),\s*1,\s*"([^"]+)"\)', content):
                            all_depots[m.group(1)] = m.group(2)
                    except Exception as e:
                        self.log.error(f"读取LUA文件失败: {lua_file} - {e}")
                
                # 写入LUA脚本
                async with aiofiles.open(lua_filepath, 'w', encoding='utf-8') as f:
                    await f.write(f'addappid({app_id}, 1, "None")\n')
                    
                    for depot_id, key in all_depots.items():
                        await f.write(f'addappid({depot_id}, 1, "{key}")\n')
                    
                    # 添加清单版本信息
                    for manifest_file in manifest_files:
                        if m := re.search(r'(\d+)_(\w+)\.manifest', manifest_file.name):
                            line = f'setManifestid({m.group(1)}, "{m.group(2)}")\n'
                            if is_floating_version:
                                await f.write('--' + line)
                            else:
                                await f.write(line)
                
                self.log.info(f'[{source_name}] 已为SteamTools生成解锁脚本: {lua_filename}')
                return True
            
            # GreenLuma/标准模式
            else:
                self.log.info(f'[{source_name}] 按GreenLuma/标准模式安装。')
                gl_depot = self.steam_path / 'depotcache'
                gl_depot.mkdir(parents=True, exist_ok=True)
                
                if not manifest_files:
                    self.log.error(f"[{source_name}] 未找到 .manifest 文件")
                    return False
                
                # 复制清单文件
                for manifest_file in manifest_files:
                    shutil.copy2(manifest_file, gl_depot)
                
                self.log.info(f"已复制 {len(manifest_files)} 个清单文件")
                
                # 提取密钥并合并
                all_depots = {}
                for lua_file in lua_files:
                    try:
                        with open(lua_file, 'r', encoding='utf-8') as f_in:
                            content = f_in.read()
                            
                        for m in re.finditer(r'addappid\((\d+),\s*"([^"]+)"\)', content):
                            all_depots[m.group(1)] = {'DecryptionKey': m.group(2)}
                    except Exception as e:
                        self.log.error(f"读取LUA文件失败: {lua_file} - {e}")
                
                # 合并密钥和添加AppID
                if all_depots:
                    await self.depotkey_merge({'depots': all_depots})
                    await self.greenluma_add([app_id] + list(all_depots.keys()))
                else:
                    await self.greenluma_add([app_id])
                
                return True
                
        except Exception as e:
            self.log.error(f'[{source_name}] 处理清单时出错: {self.stack_error(e)}')
            return False
        finally:
            # 清理临时文件
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    async def process_from_specific_repo(self, client: httpx.AsyncClient, inputs: List[str], 
                                    repo_val: str) -> bool:
        """处理特定仓库"""
        app_ids = await self.resolve_appids(inputs)
        
        if not app_ids:
            self.log.error("未能解析出任何有效的AppID。")
            return False
        
        self.log.info(f"成功解析的 App IDs: {', '.join(app_ids)}")
        
        # 检查是否为GitHub仓库
        is_github = repo_val not in ["swa", "cysaw", "furcate", "cngs", "steamdatabase", "walftech"]
        
        if is_github:
            await self.checkcn(client)
            if not await self.check_github_api_rate_limit(client, self.get_github_headers()):
                return False
        
        success_count = 0
        
        # 定义仓库URL映射函数
        def get_repo_config(repo_name: str, app_id: str):
            """获取仓库配置"""
            configs = {
                "swa": {
                    "url": f'https://api.printedwaste.com/gfk/download/{app_id}',
                    "source_name": "SWA V2"
                },
                "cysaw": {
                    "url": f'https://cysaw.top/uploads/{app_id}.zip',
                    "source_name": "Cysaw"
                },
                "furcate": {
                    "url": f'https://furcate.eu/files/{app_id}.zip',
                    "source_name": "Furcate"
                },
                "cngs": {
                    "url": f'https://assiw.cngames.site/qindan/{app_id}.zip',
                    "source_name": "CNGS"
                },
                "steamdatabase": {
                    "url": f'https://steamdatabase.s3.eu-north-1.amazonaws.com/{app_id}.zip',
                    "source_name": "SteamDatabase"
                },
                "walftech": {
                    "url": f'https://walftech.com/proxy.php?url=https%3A%2F%2Fsteamgames554.s3.us-east-1.amazonaws.com%2F{app_id}.zip',
                    "source_name": "Walftech"
                }
            }
            return configs.get(repo_name)
        
        for app_id in app_ids:
            self.log.info(f"--- 正在处理 App ID: {app_id} ---")
            success = False
            
            # 根据仓库类型处理
            repo_config = get_repo_config(repo_val, app_id)
            if repo_config:
                # ZIP仓库处理
                success = await self._process_zip_based_manifest(
                    client, app_id, repo_config["url"], repo_config["source_name"]
                )
            else:
                # GitHub仓库处理
                success = await self.process_github_repo(client, app_id, repo_val)
            
            if success:
                self.log.info(f"App ID: {app_id} 处理成功。")
                success_count += 1
            else:
                self.log.error(f"App ID: {app_id} 处理失败。")
        
        return success_count > 0

    
    async def cleanup_temp_files(self) -> None:
        """清理临时文件"""
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.log.info('临时文件清理完成。')
            except Exception as e:
                self.log.warning(f'清理临时文件时出错: {e}')
    
    async def process_by_searching_all(self, client: httpx.AsyncClient, inputs: List[str], 
                                     github_repos: List[str]) -> bool:
        """搜索所有仓库处理"""
        app_ids = await self.resolve_appids(inputs)
        
        if not app_ids:
            self.log.error("未能解析出任何有效的AppID。")
            return False
        
        await self.checkcn(client)
        
        if not await self.check_github_api_rate_limit(client, self.get_github_headers()):
            return False
        
        success_count = 0
        for app_id in app_ids:
            self.log.info(f"--- 正在为 App ID: {app_id} 搜索所有GitHub库 ---")
            
            repo_results = await self.search_all_repos(client, app_id, github_repos)
            
            if not repo_results:
                self.log.error(f"在所有GitHub库中均未找到 {app_id} 的清单。")
                continue
            
            # 按更新时间排序，选择最新的
            repo_results.sort(key=lambda x: x['update_date'], reverse=True)
            selected = repo_results[0]
            
            self.log.info(f"找到 {len(repo_results)} 个结果，将使用最新的清单: "
                         f"{selected['repo']} (更新于 {selected['update_date']})")
            
            if await self.process_github_repo(client, app_id, selected['repo'], selected):
                self.log.info(f"App ID: {app_id} 处理成功。")
                success_count += 1
            else:
                self.log.error(f"App ID: {app_id} 处理失败。")
        
        return success_count > 0
    
    async def search_games_by_name(self, client: httpx.AsyncClient, game_name: str) -> List[Dict[str, Any]]:
        """通过名称搜索游戏"""
        try:
            self.log.info(f"搜索游戏: '{game_name}'")
            
            # 尝试Steam商店搜索
            games = await self._search_steam_store(client, game_name)
            
            self.log.info(f"找到 {len(games)} 个匹配的游戏。")
            return games
            
        except Exception as e:
            self.log.error(f"搜索游戏失败: {e}")
            return []
    
    async def _search_steam_store(self, client: httpx.AsyncClient, game_name: str) -> List[Dict[str, Any]]:
        """搜索Steam商店"""
        try:
            games = []
            
            # 同时搜索国区和美区
            cn_games = await self._search_with_region(client, game_name, 'CN')
            us_games = await self._search_with_region(client, game_name, 'US')
            
            # 合并结果，去重
            seen_ids = set()
            
            # 先添加国区结果
            for game in cn_games:
                if game['appid'] not in seen_ids:
                    game['region'] = 'CN'
                    games.append(game)
                    seen_ids.add(game['appid'])
            
            # 再添加美区结果
            for game in us_games:
                if game['appid'] not in seen_ids:
                    game['region'] = 'US'
                    games.append(game)
                    seen_ids.add(game['appid'])
            
            return games[:20]
            
        except Exception as e:
            self.log.error(f"Steam商店搜索失败: {e}")
            return []
    
    async def _search_with_region(self, client: httpx.AsyncClient, game_name: str, country_code: str) -> List[Dict[str, Any]]:
        """使用指定地区搜索Steam商店"""
        try:
            url = 'https://store.steampowered.com/api/storesearch/'
            # 根据地区选择语言，默认为 english
            language_map = {
                'CN': 'schinese',
                'US': 'english',
            }
            language = language_map.get(country_code, 'english')

            params = {'term': game_name, 'l': language, 'cc': country_code}
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }
            
            r = await client.get(url, params=params, headers=headers, timeout=15)
            
            if r.status_code != 200:
                return []
            
            data = r.json()
            games = []
            
            for item in data.get('items', []):
                if item.get('type') in ['bundle', 'sub', 'dlc']:
                    continue
                    
                games.append({
                    'appid': item['id'],
                    'name': item['name'],
                    'schinese_name': item['name'],
                    'type': item.get('type', 'Game'),
                    'region': country_code
                })
            
            return games
            
        except Exception:
            return []
    

