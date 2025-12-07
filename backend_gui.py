import os
import sys
import traceback
import asyncio
import re
import json
import zipfile
import shutil
import struct
import zlib
import time
from pathlib import Path
from typing import Tuple, List, Dict, Optional, Any
import logging

# 延迟导入依赖库
try:
    import aiofiles
    import httpx
    import vdf
except ImportError as e:
    raise ImportError(f"缺少依赖库: {e}. 请使用 'pip install aiofiles httpx vdf' 安装。")

try:
    import winreg
except ImportError:
    winreg = None  # 非Windows系统

# 默认配置
DEFAULT_CONFIG = {
    "Github_Personal_Token": "",
    "Custom_Steam_Path": "",
    "steamtools_only_lua": False,
    "auto_restart_steam": True
}

def get_app_dir() -> Path:
    """获取应用程序目录"""
    if getattr(sys, '_MEIPASS', None):  # PyInstaller打包
        return Path(sys.executable).resolve().parent
    elif getattr(sys, 'frozen', False):  # 其他打包方式
        return Path(sys.executable).resolve().parent
    else:  # 源码运行
        return Path(__file__).resolve().parent

app_dir = get_app_dir()

class STConverter:
    """ST文件转换器"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def convert_file(self, st_path: str) -> str:
        """转换ST文件为LUA内容"""
        try:
            content, _ = self.parse_st_file(st_path)
            return content
        except Exception as e:
            self.logger.error(f'ST文件转换失败: {st_path} - {e}')
            raise
    
    def parse_st_file(self, st_file_path: str) -> Tuple[str, dict]:
        """解析ST文件"""
        try:
            with open(st_file_path, 'rb') as stfile:
                content = stfile.read()
            
            if len(content) < 12:
                raise ValueError("文件头长度不足")
            
            header = content[:12]
            xorkey, size, _ = struct.unpack('III', header)
            xorkey ^= 0xFFFEA4C8
            xorkey &= 0xFF
            
            encrypted_data = content[12:12 + size]
            if len(encrypted_data) < size:
                raise ValueError(f"数据长度不足，期望{size}字节，实际{len(encrypted_data)}字节")
            
            data = bytearray(encrypted_data)
            for i in range(len(data)):
                data[i] ^= xorkey
            
            decompressed_data = zlib.decompress(data)
            content_str = decompressed_data[512:].decode('utf-8')
            
            metadata = {'original_xorkey': xorkey, 'size': size}
            return content_str, metadata
            
        except (struct.error, zlib.error, UnicodeDecodeError) as e:
            raise ValueError(f"ST文件解析失败: {e}")

class GuiBackend:
    """GUI后端处理类"""
    
    def __init__(self, logger: logging.Logger):
        self.log = logger
        self.st_converter = STConverter(self.log)
        self.app_config = DEFAULT_CONFIG.copy()
        self.steam_path = Path()
        self.unlocker_type: Optional[str] = None
        self.temp_dir = app_dir / 'temp_cai_install'
        self.st_lock_manifest_version = False
        self._client_cache: Optional[httpx.AsyncClient] = None
        self.last_detected_region: Optional[str] = None
        self.current_country: Optional[str] = None
    
    def stack_error(self, e: Exception) -> str:
        """获取完整的异常堆栈信息"""
        return ''.join(traceback.format_exception(type(e), e, e.__traceback__))
    
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
        try:
            config_path = app_dir / "config.json"
            self.log.info(f"生成配置文件: {config_path}")
            
            with open(config_path, mode="w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            
            self.app_config = DEFAULT_CONFIG.copy()
            self.log.info('配置文件已生成，请在"设置"中填写。')
            
        except Exception as e:
            self.log.error(f'配置文件生成失败: {config_path}, 错误={self.stack_error(e)}')
    
    def save_config(self) -> bool:
        """保存配置文件"""
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
            
            # 自动检测（仅Windows）
            if winreg is not None:
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
                    steam_path_str = winreg.QueryValueEx(key, 'SteamPath')[0]
                    self.steam_path = Path(steam_path_str).resolve()
                    self.log.info(f"自动检测到Steam路径: {self.steam_path}")
                    return self.steam_path
                except (OSError, FileNotFoundError) as e:
                    self.log.warning(f"注册表查询失败: {e}")
            else:
                self.log.warning("非Windows系统，无法自动检测Steam路径")
            
            # 尝试常见路径
            common_paths = [
                Path("C:/Program Files (x86)/Steam"),
                Path("C:/Program Files/Steam"),
                Path.home() / ".steam" / "steam",
                Path.home() / ".local/share/Steam",
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
    
    def get_github_headers(self) -> Dict[str, str]:
        """获取GitHub请求头"""
        token = self.app_config.get("Github_Personal_Token", "").strip()
        if token:
            return {'Authorization': f'token {token}'}
        return {}
    
    async def get_client(self) -> httpx.AsyncClient:
        """获取或创建HTTP客户端"""
        if self._client_cache is None:
            self._client_cache = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={'User-Agent': 'Cai-Installer-GUI/1.0'}
            )
        return self._client_cache
    
    async def close_client(self) -> None:
        """关闭HTTP客户端"""
        if self._client_cache:
            await self._client_cache.aclose()
            self._client_cache = None
    
    async def check_github_api_rate_limit(self, client: httpx.AsyncClient, headers: dict) -> bool:
        """检查GitHub API速率限制"""
        if headers:
            self.log.info("已配置Github Token。")
        else:
            self.log.warning("未配置Github Token，API请求次数有限，建议在设置中添加。")
        
        try:
            r = await client.get('https://api.github.com/rate_limit', headers=headers)
            r.raise_for_status()
            
            rate = r.json().get('resources', {}).get('core', {})
            remaining = rate.get('remaining', 0)
            limit = rate.get('limit', 60)
            
            if remaining == 0:
                reset_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(rate.get('reset', 0)))
                self.log.warning(f"GitHub API请求数已用尽，将在 {reset_time} 重置。")
                return False
            
            self.log.info(f'GitHub API 剩余请求次数: {remaining}/{limit}')
            return True
            
        except Exception as e:
            self.log.error(f'检查GitHub API速率时出错: {e}')
            return False
    
    async def checkcn(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """检测是否在中国大陆"""
        temp_client = None
        current_region = None
        current_country = None
        
        try:
            if client is None:
                temp_client = httpx.AsyncClient(timeout=10)
                client_to_use = temp_client
            else:
                client_to_use = client
            
            # 地理位置检测API
            check_apis = [
                {"url": "https://mips.kugou.com/check/iscn?format=json", 
                 "parser": lambda data: ("cn", "CN") if data.get('flag', False) else 
                                        (f"not_cn_{data.get('country', 'Unknown')}", 
                                         data.get('country', 'Unknown'))},
                {"url": "https://api.ip.sb/geoip", 
                 "parser": lambda data: ("cn", "CN") if data.get('country_code') == 'CN' else 
                                        (f"not_cn_{data.get('country', 'Unknown')}", 
                                         data.get('country', 'Unknown'))},
            ]
            
            # 尝试每个API
            for api_info in check_apis:
                try:
                    self.log.debug(f"尝试地理位置API: {api_info['url'].split('/')[2]}")
                    r = await client_to_use.get(api_info['url'], timeout=5, follow_redirects=True)
                    
                    if r.status_code == 200:
                        data = r.json()
                        region_result, country_result = api_info['parser'](data)
                        
                        if region_result and country_result:
                            current_region = region_result
                            current_country = country_result
                            break
                except Exception:
                    continue
            
            # 处理检测结果
            if current_region is None:
                current_region = 'cn'
                current_country = 'CN'
                if self.last_detected_region != current_region:
                    self.log.warning('所有地理位置API均失败，默认使用国内镜像')
            
            # 统一格式：所有地区都显示IP归属地
            if current_region != self.last_detected_region:
                if current_region == 'cn':
                    self.log.info(f"IP归属地为{current_country}\n将会使用镜像源")
                else:
                    if current_country == 'Unknown':
                        self.log.info(f"检测到非中国大陆地区\n将会使用GitHub源")
                    else:
                        self.log.info(f"IP归属地为{current_country}\n将会使用GitHub源")
            
            # 更新存储的信息
            if current_region != self.last_detected_region:
                self.last_detected_region = current_region
                self.current_country = current_country
                os.environ['IS_CN'] = 'yes' if current_region == 'cn' else 'no'
            elif 'IS_CN' not in os.environ:
                os.environ['IS_CN'] = 'yes' if current_region == 'cn' else 'no'
            
            # 确保current_country有值
            if self.current_country is None:
                self.current_country = current_country or ('CN' if current_region == 'cn' else 'Unknown')
                    
        except Exception as e:
            if self.last_detected_region is None:
                self.log.warning(f'地理位置检测异常: {e}，默认使用国内镜像')
                current_region = 'cn'
                current_country = 'CN'
            else:
                self.log.warning(f'地理位置检测异常: {e}，保持之前的设置')
            
            # 设置环境变量
            if 'IS_CN' not in os.environ:
                os.environ['IS_CN'] = 'yes' if current_region == 'cn' else 'no'
            if self.last_detected_region is None:
                self.last_detected_region = current_region
                self.current_country = current_country
            elif self.current_country is None:
                self.current_country = 'CN' if current_region == 'cn' else 'Unknown'
        finally:
            if temp_client:
                await temp_client.aclose()
    
    def get_current_country(self) -> str:
        """获取当前检测到的国家代码"""
        if self.current_country:
            return self.current_country
        elif self.last_detected_region:
            if self.last_detected_region == 'cn':
                return 'CN'
            elif self.last_detected_region.startswith('not_cn_'):
                # 从region中提取国家信息
                country_from_region = self.last_detected_region.replace('not_cn_', '')
                return country_from_region
        
        return 'Unknown'
    
    async def fetch_branch_info(self, client: httpx.AsyncClient, url: str, headers: dict) -> Optional[Dict[str, Any]]:
        """获取分支信息"""
        try:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                self.log.error(f"404 Not Found: {url}")
            elif status_code == 403:
                self.log.error("403 Forbidden: GitHub API速率限制")
            elif status_code == 429:
                self.log.error("429 Too Many Requests: API请求过多")
            else:
                self.log.error(f"HTTP错误 {status_code}: {url}")
            return None
        except Exception as e:
            self.log.error(f'获取信息失败: {self.stack_error(e)}')
            return None
    
    async def get_from_url(self, client: httpx.AsyncClient, sha: str, path: str, repo: str) -> bytes:
        """从URL下载内容"""
        if os.environ.get('IS_CN') == 'yes':
            urls = [
                f'https://cdn.jsdmirror.com/gh/{repo}@{sha}/{path}',
                f'https://raw.gitmirror.com/{repo}/{sha}/{path}',
            ]
        else:
            urls = [f'https://raw.githubusercontent.com/{repo}/{sha}/{path}']
        
        last_error = None
        for url in urls:
            try:
                self.log.info(f"尝试下载: {path} from {url.split('/')[2]}")
                r = await client.get(url, timeout=30)
                
                if r.status_code == 200:
                    return r.content
                else:
                    self.log.warning(f"下载失败 (状态码 {r.status_code}) from {url.split('/')[2]}")
            except Exception as e:
                last_error = e
                self.log.warning(f"下载时连接错误 from {url.split('/')[2]}: {e}")
                continue
        
        raise Exception(f'所有下载源均失败: {path}, 最后错误: {last_error}')
    
    def extract_app_id(self, user_input: str) -> Optional[str]:
        """从输入中提取AppID"""
        patterns = [
            r"store\.steampowered\.com/app/(\d+)",
            r"steamdb\.info/app/(\d+)",
            r"steamcommunity\.com/app/(\d+)"
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, user_input):
                return match.group(1)
        
        # 检查是否为纯数字
        if user_input.isdigit():
            return user_input
        
        return None
    
    async def resolve_appids(self, inputs: List[str]) -> List[str]:
        """解析多个AppID"""
        resolved_ids = []
        
        for item in inputs:
            item = item.strip()
            if not item:
                continue
                
            if app_id := self.extract_app_id(item):
                resolved_ids.append(app_id)
            else:
                self.log.warning(f"输入项 '{item}' 不是有效的AppID或链接，已跳过。")
        
        # 去重并保持原始顺序
        seen = set()
        unique_ids = []
        for app_id in resolved_ids:
            if app_id not in seen:
                seen.add(app_id)
                unique_ids.append(app_id)
        
        return unique_ids
    
    async def search_all_repos(self, client: httpx.AsyncClient, app_id: str, repos: List[str]) -> List[Dict[str, Any]]:
        """在所有仓库中搜索"""
        results = []
        
        for repo in repos:
            self.log.info(f"搜索仓库: {repo}")
            headers = self.get_github_headers()
            
            branch_url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
            branch_info = await self.fetch_branch_info(client, branch_url, headers)
            
            if not branch_info:
                continue
            
            if 'commit' not in branch_info:
                continue
            
            tree_url = branch_info['commit']['commit']['tree']['url']
            tree_info = await self.fetch_branch_info(client, tree_url, headers)
            
            if not tree_info or 'tree' not in tree_info:
                continue
            
            results.append({
                'repo': repo,
                'sha': branch_info['commit']['sha'],
                'tree': tree_info['tree'],
                'update_date': branch_info['commit']['commit']['author']['date']
            })
            self.log.info(f"在仓库 {repo} 中找到清单。")
        
        return results
    
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
                if isinstance(res, Exception):
                    self.log.error(f"下载/处理文件时出错: {res}")
                    continue
                if res:
                    collected_depots.extend(res)
            
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
        for app_id in app_ids:
            self.log.info(f"--- 正在处理 App ID: {app_id} ---")
            success = False
            
            # 根据仓库类型处理
            if repo_val == "swa":
                success = await self._process_zip_based_manifest(
                    client, app_id, f'https://api.printedwaste.com/gfk/download/{app_id}', "SWA V2"
                )
            elif repo_val == "cysaw":
                success = await self._process_zip_based_manifest(
                    client, app_id, f'https://cysaw.top/uploads/{app_id}.zip', "Cysaw"
                )
            elif repo_val == "furcate":
                success = await self._process_zip_based_manifest(
                    client, app_id, f'https://furcate.eu/files/{app_id}.zip', "Furcate"
                )
            elif repo_val == "cngs":
                success = await self._process_zip_based_manifest(
                    client, app_id, f'https://assiw.cngames.site/qindan/{app_id}.zip', "CNGS"
                )
            elif repo_val == "steamdatabase":
                success = await self._process_zip_based_manifest(
                    client, app_id, f'https://steamdatabase.s3.eu-north-1.amazonaws.com/{app_id}.zip', 
                    "SteamDatabase"
                )
            elif repo_val == "walftech":
                success = await self._process_zip_based_manifest(
                    client, app_id, 
                    f'https://walftech.com/proxy.php?url=https%3A%2F%2Fsteamgames554.s3.us-east-1.amazonaws.com%2F{app_id}.zip', 
                    "Walftech"
                )
            else:
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
            
            if not games:
                games = await self._search_steamspy(client, game_name)
            
            self.log.info(f"找到 {len(games)} 个匹配的游戏。")
            return games[:20]  # 限制返回数量
            
        except Exception as e:
            self.log.error(f"搜索游戏失败: {e}")
            return []
    
    async def _search_steam_store(self, client: httpx.AsyncClient, game_name: str) -> List[Dict[str, Any]]:
        """搜索Steam商店"""
        try:
            url = 'https://store.steampowered.com/api/storesearch/'
            params = {'term': game_name, 'l': 'schinese', 'cc': 'CN'}
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
            
            r = await client.get(url, params=params, headers=headers, timeout=15)
            
            if r.status_code != 200:
                return []
            
            data = r.json()
            games = []
            
            for item in data.get('items', []):
                games.append({
                    'appid': item['id'],
                    'name': item['name'],
                    'schinese_name': item['name'],
                    'type': 'Game'
                })
            
            return games
            
        except Exception:
            return []
    
    async def _search_steamspy(self, client: httpx.AsyncClient, game_name: str) -> List[Dict[str, Any]]:
        """备用搜索方案：SteamSpy"""
        try:
            url = 'https://steamspy.com/api.php'
            params = {'request': 'search', 'search': game_name}
            
            r = await client.get(url, params=params, timeout=30)
            
            if r.status_code != 200:
                return []
            
            data = r.json()
            games = []
            
            for appid, game_info in list(data.items())[:20]:
                games.append({
                    'appid': int(appid),
                    'name': game_info.get('name', ''),
                    'schinese_name': game_info.get('name', ''),
                    'type': 'Game'
                })
            
            return games
            
        except Exception:
            return []
    
    async def check_for_updates(self, current_version: str) -> Dict[str, Any]:
        """检查更新"""
        try:
            headers = self.get_github_headers()
            
            async with httpx.AsyncClient() as client:
                await self.checkcn(client)
                
                # 获取最新发布信息
                url = "https://api.github.com/repos/WingChunWong/Cai-Installer-GUI/releases/latest"
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                release_info = response.json()
                latest_version = release_info.get('tag_name', '').lstrip('v')
                
                # 比较版本
                if self.is_newer_version(latest_version, current_version):
                    # 查找exe文件
                    download_url = ''
                    for asset in release_info.get('assets', []):
                        if asset['name'].endswith('.exe'):
                            download_url = asset['browser_download_url']
                            break
                    
                    # 生成镜像地址
                    mirror_url = ''
                    if os.environ.get('IS_CN') == 'yes' and download_url:
                        mirror_url = self.convert_github_to_mirror(download_url)
                    
                    return {
                        'has_update': True,
                        'latest_version': latest_version,
                        'current_version': current_version,
                        'release_url': release_info.get('html_url', ''),
                        'download_url': download_url,
                        'mirror_url': mirror_url,
                        'release_notes': release_info.get('body', ''),
                        'published_at': release_info.get('published_at', '')
                    }
                
                return {'has_update': False}
                
        except Exception as e:
            self.log.error(f"检查更新失败: {self.stack_error(e)}")
            return {'has_update': False, 'error': str(e)}
    
    def is_newer_version(self, latest: str, current: str) -> bool:
        """比较版本号"""
        try:
            latest_clean = latest.lstrip('v').strip()
            current_clean = current.lstrip('v').strip()
            
            latest_parts = list(map(int, latest_clean.split('.')))
            current_parts = list(map(int, current_clean.split('.')))
            
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            
            return latest_parts > current_parts
            
        except Exception as e:
            self.log.error(f"版本号比较失败: {e}")
            return False
    
    def convert_github_to_mirror(self, github_url: str) -> str:
        """转换为国内镜像地址"""
        if not github_url:
            return ""
        
        mirrors = [
            f'https://ghfast.top/{github_url}',
            f'https://wget.la/{github_url}'
        ]
        
        return mirrors[0] if mirrors else ""
    
    async def download_update_direct(self, url: str, dest_path: str, progress_callback=None) -> bool:
        """直接下载更新文件"""
        try:
            self.log.info(f"下载更新: {url}")
            
            async with httpx.AsyncClient(
                timeout=60,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0'}
            ) as client:
                # 获取文件大小
                head_response = await client.head(url, follow_redirects=True)
                total_size = int(head_response.headers.get('content-length', 0))
                
                if total_size:
                    self.log.info(f"文件大小: {total_size / 1024 / 1024:.2f} MB")
                
                # 下载文件
                async with client.stream('GET', url) as response:
                    response.raise_for_status()
                    
                    downloaded_size = 0
                    
                    with open(dest_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # 更新进度
                            if progress_callback and total_size > 0:
                                progress_callback(downloaded_size, total_size)
                    
                    self.log.info(f"下载完成: {dest_path} ({downloaded_size} 字节)")
                    return True
                    
        except httpx.HTTPStatusError as e:
            self.log.error(f"HTTP错误: {e.response.status_code}")
            return False
        except Exception as e:
            self.log.error(f"下载失败: {self.stack_error(e)}")
            return False