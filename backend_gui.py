import os
import sys
import traceback
import asyncio
import re
try:
    import aiofiles
except ImportError:
    raise ImportError("aiofiles 库未安装。请使用 'pip install aiofiles' 安装。")
try:
    import httpx
except ImportError:
    raise ImportError("httpx 库未安装。请使用 'pip install httpx' 安装。")
import winreg
try:
    import vdf
except ImportError:
    raise ImportError("vdf 库未安装。请使用 'pip install vdf' 安装。")
import json
import zipfile
import shutil
import struct
import zlib
import time
from pathlib import Path
from typing import Tuple, List, Dict, Literal

DEFAULT_CONFIG = {
    "Github_Personal_Token": "",
    "Custom_Steam_Path": "",
    "steamtools_only_lua": False,
    "auto_restart_steam": True,
    "QA1": "温馨提示: Github_Personal_Token(个人访问令牌)可在Github设置的最底下开发者选项中找到, 详情请看教程。",
    "QA2": "温馨提示: 勾选'使用SteamTools进行清单更新'后，对于ST用户，程序将仅下载和更新LUA脚本，而不再下载清单文件(.manifest)。"
}

def get_app_dir():
    if getattr(sys, '_MEIPASS', None):
        app_dir = Path(sys.executable).resolve().parent
    elif '__compiled__' in globals():
        app_dir = Path(sys.argv[0]).resolve().parent
    elif getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent
    return app_dir

app_dir = get_app_dir()

class STConverter:
    def __init__(self, logger):
        self.logger = logger

    def convert_file(self, st_path: str) -> str:
        try:
            content, _ = self.parse_st_file(st_path)
            return content
        except Exception as e:
            self.logger.error(f'ST文件转换失败: {st_path} - {e}')
            raise

    def parse_st_file(self, st_file_path: str) -> Tuple[str, dict]:
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
            raise ValueError(f"数据长度不足")
        data = bytearray(encrypted_data)
        for i in range(len(data)):
            data[i] ^= xorkey
        decompressed_data = zlib.decompress(data)
        content_str = decompressed_data[512:].decode('utf-8')
        metadata = {'original_xorkey': xorkey, 'size': size}
        return content_str, metadata

class GuiBackend:
    def __init__(self, logger):
        self.log = logger
        self.st_converter = STConverter(self.log)
        self.app_config = {}
        self.steam_path = Path()
        self.unlocker_type = None
        self.temp_dir = app_dir / 'temp_cai_install'
        self.st_lock_manifest_version = False

    def stack_error(self, e: Exception) -> str:
        return ''.join(traceback.format_exception(type(e), e, e.__traceback__))

    def load_config(self):
        config_path = app_dir / 'config.json'
        if not config_path.exists():
            self.gen_config_file()
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
            self.app_config = DEFAULT_CONFIG.copy()
            self.app_config.update(loaded_config)
        except Exception as e:
            self.log.error(f"配置文件加载失败，将重置: {self.stack_error(e)}")
            if config_path.exists():
                os.remove(config_path)
            self.gen_config_file()
            self.app_config = DEFAULT_CONFIG.copy()
    
    def gen_config_file(self):
        try:
            config_path = app_dir / "config.json"
            self.log.info(f"尝试生成config.json到路径：{config_path}")
            with open(config_path, mode="w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            self.log.info('首次启动或配置重置，已生成config.json，请在"设置"中填写。')
            self.app_config = DEFAULT_CONFIG.copy()
        except Exception as e:
            self.log.error(f'配置文件生成失败: 路径={config_path}, 错误={self.stack_error(e)}')

    def save_config(self):
        try:
            config_path = app_dir / "config.json"
            self.log.info(f"尝试保存config.json到路径：{config_path}")
            with open(config_path, mode="w", encoding="utf-8") as f:
                config_to_save = DEFAULT_CONFIG.copy()
                config_to_save.update(self.app_config)
                json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.error(f'保存配置失败: 路径={config_path}, 错误={self.stack_error(e)}')

    def detect_steam_path(self) -> Path:
        try:
            custom_path = self.app_config.get("Custom_Steam_Path", "").strip()
            if custom_path and Path(custom_path).exists():
                self.steam_path = Path(custom_path)
                self.log.info(f"使用自定义Steam路径: {self.steam_path}")
            else:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
                self.steam_path = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
                self.log.info(f"自动检测到Steam路径: {self.steam_path}")
            return self.steam_path
        except Exception:
            self.log.error('Steam路径获取失败，请检查Steam是否安装或在设置中指定路径。')
            self.steam_path = Path()
            return self.steam_path
            
    def detect_unlocker(self) -> Literal["steamtools", "greenluma", "conflict", "none"]:
        if not self.steam_path.exists():
            return "none"
        is_steamtools = (self.steam_path / 'config' / 'stplug-in').is_dir()
        is_greenluma = any((self.steam_path / dll).exists() for dll in ['GreenLuma_2025_x86.dll', 'GreenLuma_2025_x64.dll'])
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

    def is_steamtools(self):
        return self.unlocker_type == "steamtools"

    def get_github_headers(self):
        token = self.app_config.get("Github_Personal_Token", "")
        return {'Authorization': f'Bearer {token}'} if token else {}

    async def check_github_api_rate_limit(self, client: httpx.AsyncClient, headers: dict):
        if headers:
            self.log.info("已配置Github Token。")
        else:
            self.log.warning("未配置Github Token，API请求次数有限，建议在设置中添加。")
        try:
            r = await client.get('https://api.github.com/rate_limit', headers=headers)
            r.raise_for_status()
            rate = r.json().get('resources', {}).get('core', {})
            remaining = rate.get('remaining', 0)
            if remaining == 0:
                reset_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(rate.get('reset', 0)))
                self.log.warning(f"GitHub API请求数已用尽，将在 {reset_time} 重置。")
                return False
            self.log.info(f'GitHub API 剩余请求次数: {remaining}')
            return True
        except Exception as e:
            self.log.error(f'检查GitHub API速率时出错: {e}')
            return False

    async def checkcn(self, client: httpx.AsyncClient = None): # type: ignore
        """检测是否在中国大陆"""
        try:
            # 如果client为None，创建新的client
            temp_client = None
            try:
                if client is None:
                    temp_client = httpx.AsyncClient(timeout=10)
                    client_to_use = temp_client
                else:
                    client_to_use = client
                
                r = await client_to_use.get('https://mips.kugou.com/check/iscn?&format=json', timeout=5)
                if not bool(r.json().get('flag')):
                    self.log.info(f"检测到您在非中国大陆地区 ({r.json().get('country')})，将使用GitHub官方下载源。")
                    os.environ['IS_CN'] = 'no'
                else:
                    os.environ['IS_CN'] = 'yes'
                    self.log.info("检测到您在中国大陆地区，将使用国内镜像。")
            except Exception:
                os.environ['IS_CN'] = 'yes'
                self.log.warning('检查服务器位置失败，将默认使用国内加速CDN。')
            finally:
                if temp_client:
                    await temp_client.aclose()
        except Exception:
            # 如果检测失败，保守起见使用镜像
            os.environ['IS_CN'] = 'yes'
            self.log.warning('网络检测失败，默认使用国内镜像。')

    async def fetch_branch_info(self, client: httpx.AsyncClient, url: str, headers: dict):
        try:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            self.log.error(f'获取信息失败: {e.request.url} - 状态码 {e.response.status_code}')
            if e.response.status_code == 404:
                self.log.error("404 Not Found: 请检查AppID是否正确，以及该清单是否存在于所选仓库中。")
            elif e.response.status_code == 403:
                self.log.error("403 Forbidden: GitHub API速率限制，请在设置中添加Token或稍后再试。")
            return None
        except Exception as e:
            self.log.error(f'获取信息失败: {self.stack_error(e)}')
            return None

    async def get_from_url(self, client: httpx.AsyncClient, sha: str, path: str, repo: str):
        if os.environ.get('IS_CN') == 'yes':
            urls = [
                f'https://cdn.jsdmirror.com/gh/{repo}@{sha}/{path}',
                f'https://raw.gitmirror.com/{repo}/{sha}/{path}'
            ]
        else:
            urls = [f'https://raw.githubusercontent.com/{repo}/{sha}/{path}']
        
        for url in urls:
            try:
                self.log.info(f"尝试下载: {path} from {url.split('/')[2]}")
                r = await client.get(url, timeout=30)
                if r.status_code == 200:
                    return r.content
                self.log.warning(f"下载失败 (状态码 {r.status_code}) from {url.split('/')[2]}，尝试下一个源...")
            except Exception as e:
                self.log.warning(f"下载时连接错误 from {url.split('/')[2]}: {e}，尝试下一个源...")
        raise Exception(f'所有下载源均失败: {path}')

    def extract_app_id(self, user_input: str):
        for p in [r"store\.steampowered\.com/app/(\d+)", r"steamdb\.info/app/(\d+)"]:
            if m := re.search(p, user_input):
                return m.group(1)
        return user_input if user_input.isdigit() else None

    async def resolve_appids(self, inputs: List[str]) -> List[str]:
        resolved_ids = []
        for item in inputs:
            if app_id := self.extract_app_id(item):
                resolved_ids.append(app_id)
            else:
                self.log.warning(f"输入项 '{item}' 不是有效的AppID或链接，已跳过。")
        return list(dict.fromkeys(resolved_ids))

    async def search_all_repos(self, client: httpx.AsyncClient, app_id: str, repos: List[str]):
        results = []
        for repo in repos:
            self.log.info(f"搜索仓库: {repo}")
            headers = self.get_github_headers()
            branch_url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
            if r1 := await self.fetch_branch_info(client, branch_url, headers):
                if 'commit' in r1 and (r2 := await self.fetch_branch_info(client, r1['commit']['commit']['tree']['url'], headers)):
                    if 'tree' in r2:
                        results.append({
                            'repo': repo,
                            'sha': r1['commit']['sha'],
                            'tree': r2['tree'],
                            'update_date': r1["commit"]["commit"]["author"]["date"]
                        })
                        self.log.info(f"在仓库 {repo} 中找到清单。")
        return results

    async def process_github_repo(self, client: httpx.AsyncClient, app_id: str, repo: str, existing_data: dict = None): # type: ignore
        try:
            headers = self.get_github_headers()
            
            if existing_data:
                sha, tree, date = existing_data['sha'], existing_data['tree'], existing_data['update_date']
            else:
                branch_url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
                if not (r_json := await self.fetch_branch_info(client, branch_url, headers)):
                    return False
                
                sha, date = r_json['commit']['sha'], r_json["commit"]["commit"]["author"]["date"]
                
                if not (r2_json := await self.fetch_branch_info(client, r_json['commit']['commit']['tree']['url'], headers)):
                    return False
                tree = r2_json['tree']
            
            all_manifests_in_repo = [item['path'] for item in tree if item['path'].endswith('.manifest')]
            tasks = [self.get_manifest_from_github(client, sha, item['path'], repo, app_id, all_manifests_in_repo) for item in tree]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            collected_depots = []
            for res in results:
                if isinstance(res, Exception):
                    self.log.error(f"下载/处理文件时出错: {res}")
                    return False
                if res:
                    collected_depots.extend(res) # type: ignore
            
            if not any(isinstance(res, list) and res is not None for res in results) and not collected_depots:
                self.log.error(f'仓库中没有找到有效的清单文件或密钥文件: {app_id}')
                return False
            
            if self.is_steamtools():
                self.log.info('检测到SteamTools，已自动生成并放置解锁文件。')
            elif collected_depots:
                await self.greenluma_add([app_id] + [depot_id for depot_id, _ in collected_depots])
                await self.depotkey_merge({'depots': {depot_id: {'DecryptionKey': key} for depot_id, key in collected_depots}})
            
            self.log.info(f'清单最后更新时间: {date}')
            return True
            
        except Exception as e:
            self.log.error(f"处理GitHub仓库时出错: {str(e)}")
            return False

    async def get_manifest_from_github(self, client: httpx.AsyncClient, sha: str, path: str, repo: str, app_id: str, all_manifests: List[str]):
        is_st_auto_update_mode = self.is_steamtools() and self.app_config.get("steamtools_only_lua", False)
        
        if path.endswith('.manifest') and is_st_auto_update_mode:
            self.log.info(f"ST自动更新模式: 已跳过清单文件下载: {path}")
            return []

        content = await self.get_from_url(client, sha, path, repo)
        depots = []
        stplug = self.steam_path / 'config' / 'stplug-in'
        
        if path.endswith('.manifest') and not is_st_auto_update_mode:
            depot_cache = self.steam_path / 'depotcache'
            cfg_depot_cache = self.steam_path / 'config' / 'depotcache'
            for p in [depot_cache, cfg_depot_cache, stplug]:
                p.mkdir(parents=True, exist_ok=True)
            for p in [depot_cache, cfg_depot_cache]:
                (p / Path(path).name).write_bytes(content)
            self.log.info(f'清单已保存: {path}')
        elif "key.vdf" in path.lower():
            depots_cfg = vdf.loads(content.decode('utf-8'))
            depots = [(depot_id, info['DecryptionKey']) for depot_id, info in depots_cfg.get('depots', {}).items()]
            if self.is_steamtools() and app_id:
                lua_path = stplug / f"{app_id}.lua"
                self.log.info(f'为SteamTools创建Lua脚本: {lua_path}')
                
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
                self.log.info('Lua脚本创建成功。')
        return depots

    async def depotkey_merge(self, depots_config: dict):
        config_path = self.steam_path / 'config' / 'config.vdf'
        if not config_path.exists():
            self.log.error('Steam默认配置(config.vdf)不存在')
            return False
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = vdf.loads(f.read())
            steam = (config.get('InstallConfigStore',{}).get('Software',{}).get('Valve') or 
                     config.get('InstallConfigStore',{}).get('Software',{}).get('valve'))
            if not steam:
                self.log.error('找不到Steam配置节')
                return False
            steam.setdefault('depots', {}).update(depots_config.get('depots', {}))
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(vdf.dumps(config, pretty=True))
            self.log.info('密钥成功合并到 config.vdf。')
            return True
        except Exception as e:
            self.log.error(f'合并密钥失败: {self.stack_error(e)}')
            return False
    
    async def greenluma_add(self, depot_id_list: List[str]):
        try:
            app_list_path = self.steam_path / 'AppList'
            app_list_path.mkdir(parents=True, exist_ok=True)
            for appid in depot_id_list:
                (app_list_path / f'{appid}.txt').write_text(str(appid), encoding='utf-8')
            self.log.info(f"已为GreenLuma添加AppID: {', '.join(depot_id_list)}")
            return True
        except Exception as e:
            self.log.error(f'为GreenLuma添加解锁文件时出错: {e}')
            return False

    async def _process_zip_based_manifest(self, client: httpx.AsyncClient, app_id: str, download_url: str, source_name: str):
        try:
            self.temp_dir.mkdir(exist_ok=True)
            self.log.info(f'[{source_name}] 正在下载清单文件: {download_url}')
            async with client.stream("GET", download_url, timeout=60) as r:
                if r.status_code != 200:
                    self.log.error(f'[{source_name}] 下载失败: 状态码 {r.status_code}')
                    return False
                zip_path = self.temp_dir / f'{app_id}.zip'
                async with aiofiles.open(zip_path, 'wb') as f:
                    async for chunk in r.aiter_bytes():
                        await f.write(chunk)
            
            self.log.info(f'[{source_name}] 正在解压文件...')
            extract_path = self.temp_dir / app_id
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_path)
            
            manifest_files = list(extract_path.glob('*.manifest'))
            lua_files = list(extract_path.glob('*.lua'))
            st_files = list(extract_path.glob('*.st'))

            for st_file in st_files:
                try:
                    lua_path = st_file.with_suffix('.lua')
                    lua_content = self.st_converter.convert_file(str(st_file))
                    async with aiofiles.open(lua_path, 'w', encoding='utf-8') as f:
                        await f.write(lua_content)
                    lua_files.append(lua_path)
                    self.log.info(f'已转换ST文件: {st_file.name}')
                except Exception as e:
                    self.log.error(f'转换ST文件失败: {e} - {self.stack_error(e)}')

            is_st_auto_update_mode = self.is_steamtools() and self.app_config.get("steamtools_only_lua", False)
            is_floating_version = is_st_auto_update_mode and not self.st_lock_manifest_version

            if self.is_steamtools():
                st_plug = self.steam_path / 'config' / 'stplug-in'
                st_plug.mkdir(parents=True, exist_ok=True)
                
                if not is_st_auto_update_mode:
                    self.log.info(f'[{source_name}] 按SteamTools标准模式安装清单文件。')
                    st_depot_path = self.steam_path / 'config' / 'depotcache'
                    gl_depot_path = self.steam_path / 'depotcache'

                    st_depot_path.mkdir(parents=True, exist_ok=True)
                    gl_depot_path.mkdir(parents=True, exist_ok=True)
                    
                    if manifest_files:
                        for f in manifest_files:
                            shutil.copy2(f, st_depot_path)
                            shutil.copy2(f, gl_depot_path)
                        self.log.info(f"[{source_name}] 已复制 {len(manifest_files)} 个清单到 config/depotcache 和 depotcache 两个目录。")
                    else:
                        self.log.info(f"[{source_name}] 未找到 .manifest 文件。")
                else:
                    self.log.info(f"[{source_name}] ST自动更新模式: 已跳过.manifest 文件。")

                lua_filename = f"{app_id}.lua"
                lua_filepath = st_plug / lua_filename
                all_depots = {}
                for lua_f in lua_files:
                    with open(lua_f, 'r', encoding='utf-8') as f_in:
                        for m in re.finditer(r'addappid\((\d+),\s*1,\s*"([^"]+)"\)', f_in.read()):
                            all_depots[m.group(1)] = m.group(2)

                async with aiofiles.open(lua_filepath, 'w', encoding='utf-8') as f:
                    await f.write(f'addappid({app_id}, 1, "None")\n')
                    for depot_id, key in all_depots.items():
                        await f.write(f'addappid({depot_id}, 1, "{key}")\n')
                    
                    for manifest_f in manifest_files:
                        m = re.search(r'(\d+)_(\w+)\.manifest', manifest_f.name)
                        if m:
                            line = f'setManifestid({m.group(1)}, "{m.group(2)}")\n'
                            if is_floating_version:
                                await f.write('--' + line)
                            else:
                                await f.write(line)
                self.log.info(f'[{source_name}] 已为SteamTools生成解锁脚本: {lua_filename}')
                return True
            else:
                self.log.info(f'[{source_name}] 按GreenLuma/标准模式安装。')
                gl_depot = self.steam_path / 'depotcache'
                gl_depot.mkdir(parents=True, exist_ok=True)
                if not manifest_files:
                    self.log.warning(f"[{source_name}] 在GreenLuma/标准模式下未找到可安装的 .manifest 文件。")
                    return False
                
                for f in manifest_files:
                    shutil.copy2(f, gl_depot)
                self.log.info(f"已复制 {len(manifest_files)} 个清单到Steam depotcache目录。")

                all_depots = {}
                for lua_f in lua_files:
                    with open(lua_f, 'r', encoding='utf-8') as f_in:
                         for m in re.finditer(r'addappid\((\d+),\s*"([^"]+)"\)', f_in.read()):
                            all_depots[m.group(1)] = {'DecryptionKey': m.group(2)}
                
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
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def process_from_specific_repo(self, client: httpx.AsyncClient, inputs: List[str], repo_val: str):
        app_ids = await self.resolve_appids(inputs)
        if not app_ids:
            self.log.error("未能解析出任何有效的AppID。")
            return False
        
        self.log.info(f"成功解析的 App IDs: {', '.join(app_ids)}")
        
        is_github = repo_val not in ["swa", "cysaw", "furcate", "cngs", "steamdatabase"]
        if is_github:
            await self.checkcn(client)
            if not await self.check_github_api_rate_limit(client, self.get_github_headers()):
                return False
        
        success_count = 0
        for app_id in app_ids:
            self.log.info(f"--- 正在处理 App ID: {app_id} ---")
            success = False
            
            if repo_val == "swa":
                success = await self._process_zip_based_manifest(client, app_id, f'https://api.printedwaste.com/gfk/download/{app_id}', "SWA V2")
            elif repo_val == "cysaw":
                success = await self._process_zip_based_manifest(client, app_id, f'https://cysaw.top/uploads/{app_id}.zip', "Cysaw")
            elif repo_val == "furcate":
                success = await self._process_zip_based_manifest(client, app_id, f'https://furcate.eu/files/{app_id}.zip', "Furcate")
            elif repo_val == "cngs":
                success = await self._process_zip_based_manifest(client, app_id, f'https://assiw.cngames.site/qindan/{app_id}.zip', "CNGS")
            elif repo_val == "steamdatabase":
                success = await self._process_zip_based_manifest(client, app_id, f'https://steamdatabase.s3.eu-north-1.amazonaws.com/{app_id}.zip', "SteamDatabase")
            elif repo_val == "walftech":
                success = await self._process_zip_based_manifest(client, app_id, f'https://walftech.com/proxy.php?url=https%3A%2F%2Fsteamgames554.s3.us-east-1.amazonaws.com%2F{app_id}.zip', "Walftech")
            else:
                success = await self.process_github_repo(client, app_id, repo_val)
            
            if success:
                self.log.info(f"App ID: {app_id} 处理成功。")
                success_count += 1
            else:
                self.log.error(f"App ID: {app_id} 处理失败。")
        
        return success_count > 0

    async def cleanup_temp_files(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.log.info('临时文件清理完成。')

    async def process_by_searching_all(self, client: httpx.AsyncClient, inputs: List[str], github_repos: List[str]):
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
            
            repo_results.sort(key=lambda x: x['update_date'], reverse=True)
            selected = repo_results[0]
            
            self.log.info(f"找到 {len(repo_results)} 个结果，将使用最新的清单: {selected['repo']} (更新于 {selected['update_date']})")
            
            if await self.process_github_repo(client, app_id, selected['repo'], selected):
                self.log.info(f"App ID: {app_id} 处理成功。")
                success_count += 1
            else:
                self.log.error(f"App ID: {app_id} 处理失败。")
        
        return success_count > 0

    async def search_games_by_name_fallback(self, client: httpx.AsyncClient, game_name: str) -> List[Dict]:
        try:
            self.log.info(f"尝试备用搜索方案: '{game_name}'")
            url = f'https://steamspy.com/api.php'
            params = {
                'request': 'search',
                'search': game_name
            }
            
            r = await client.get(url, params=params, timeout=30)
            if r.status_code == 200:
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
            
            return []
            
        except Exception as e:
            self.log.error(f"备用搜索也失败: {e}")
            return []

    async def search_games_by_name(self, client: httpx.AsyncClient, game_name: str) -> List[Dict]:
        try:
            self.log.info(f"搜索游戏: '{game_name}'")
            url = 'https://store.steampowered.com/api/storesearch/'
            params = {
                'term': game_name,
                'l': 'schinese',
                'cc': 'CN'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://store.steampowered.com/',
                'Origin': 'https://store.steampowered.com',
            }
            
            r = await client.get(url, params=params, headers=headers, timeout=15)
            
            if r.status_code != 200:
                self.log.error(f"API请求失败，状态码: {r.status_code}")
                return await self.search_games_by_name_fallback(client, game_name)
            
            data = r.json()
            games = []
            for item in data.get('items', []):
                game = {
                    'appid': item['id'],
                    'name': item['name'],
                    'schinese_name': item['name'],
                    'type': 'Game'
                }
                games.append(game)
            
            self.log.info(f"找到 {len(games)} 个匹配的游戏。")
            return games[:20]
            
        except httpx.TimeoutException:
            self.log.error("搜索超时，请检查网络连接")
            return []
        except httpx.RequestError as e:
            self.log.error(f"网络请求失败: {e}")
            return []
        except Exception as e:
            self.log.error(f"搜索游戏时出错: {e}")
            try:
                return await self.search_games_by_name_fallback(client, game_name)
            except Exception as e2:
                self.log.error(f"备用搜索也失败: {e2}")
                return []
            
    async def check_for_updates(self, current_version: str) -> dict:
        """检查是否有新版本更新"""
        try:
            headers = self.get_github_headers()
            async with httpx.AsyncClient() as client:
                # 检查网络环境
                await self.checkcn(client)
                
                # 获取最新发布信息
                url = "https://api.github.com/repos/WingChunWong/Cai-Installer-GUI/releases/latest"
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                release_info = response.json()
                latest_version = release_info.get('tag_name', '')
                
                # 比较版本号
                if self.is_newer_version(latest_version, current_version):
                    # 获取下载URL
                    download_url = next(
                        (asset['browser_download_url'] for asset in release_info.get('assets', []) 
                        if asset['name'].endswith('.exe')), 
                        ''
                    )
                    
                    # 如果在中国大陆，生成镜像URL
                    mirror_url = ""
                    if os.environ.get('IS_CN') == 'yes' and download_url:
                        mirror_url = self.convert_github_to_mirror(download_url)
                    
                    return {
                        'has_update': True,
                        'latest_version': latest_version,
                        'current_version': current_version,
                        'release_url': release_info.get('html_url', ''),
                        'download_url': download_url,
                        'mirror_url': mirror_url,  # 添加镜像地址
                        'release_notes': release_info.get('body', '')
                    }
                return {'has_update': False}
        except Exception as e:
            self.log.error(f"检查更新失败: {self.stack_error(e)}")
            return {'has_update': False, 'error': str(e)}

    def is_newer_version(self, latest: str, current: str) -> bool:
        """比较版本号，判断是否有更新"""
        try:
            # 移除版本号中的v前缀并分割成数字列表
            latest_parts = list(map(int, latest.lstrip('v').split('.')))
            current_parts = list(map(int, current.lstrip('v').split('.')))
            
            # 确保两个版本号长度相同
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            
            return latest_parts > current_parts
        except Exception as e:
            self.log.error(f"版本号比较失败: {e}")
            return False

    async def download_update(self, url: str, dest_path: str) -> bool:
        """下载更新文件"""
        try:
            self.log.info(f"开始下载更新: {url}")
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream('GET', url) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    
                    with open(dest_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            # 可以添加进度计算逻辑
                            
            self.log.info(f"更新文件下载完成: {dest_path}")
            return True
        except Exception as e:
            self.log.error(f"更新下载失败: {self.stack_error(e)}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False
        
    async def download_update_with_mirror(self, url: str, dest_path: str) -> bool:
        """根据地区使用镜像或原始地址下载更新"""
        try:
            self.log.info(f"开始下载更新，检测网络环境...")
            
            # 尝试使用镜像方案
            success = await self._try_mirror_download(url, dest_path)
            if success:
                return True
            
            # 如果镜像方案失败，尝试直接下载
            self.log.warning("镜像下载失败，尝试直接下载...")
            return await self.download_update_direct(url, dest_path)
            
        except Exception as e:
            self.log.error(f"更新下载失败: {self.stack_error(e)}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False
    
    async def _try_mirror_download(self, url: str, dest_path: str) -> bool:
        """尝试使用镜像下载"""
        # 检查是否在中国大陆
        if os.environ.get('IS_CN') == 'yes':
            self.log.info("检测到中国大陆网络，尝试使用镜像下载")
            
            # 尝试解析GitHub release URL以获取镜像地址
            mirror_url = self.convert_github_to_mirror(url)
            if mirror_url:
                self.log.info(f"使用镜像地址: {mirror_url}")
                
                # 尝试使用镜像地址下载
                try:
                    return await self.download_update_direct(mirror_url, dest_path)
                except Exception as e:
                    self.log.warning(f"镜像下载失败: {e}")
        
        return False

    def convert_github_to_mirror(self, github_url: str) -> str:
        """将GitHub URL转换为国内镜像地址"""
        try:
            # 解析GitHub release URL
            import re
            
            pattern = r'https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/(.+)'
            match = re.match(pattern, github_url)
            
            if match:
                owner, repo, tag, filename = match.groups()
                
                # 使用jsdelivr镜像 - 支持release文件
                mirror_url = f'https://cdn.jsdelivr.net/gh/{owner}/{repo}@{tag}/{filename}'
                self.log.info(f"GitHub URL转换为镜像: {github_url} -> {mirror_url}")
                return mirror_url
            
            return ""
        except Exception as e:
            self.log.error(f"转换镜像地址失败: {e}")
            return ""
        
    async def download_update_direct(self, url: str, dest_path: str, progress_callback=None) -> bool:
        """直接下载更新文件（不处理镜像），支持进度回调"""
        try:
            self.log.info(f"直接下载更新: {url}")
            
            async with httpx.AsyncClient(
                timeout=60,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
            ) as client:
                # 先获取重定向后的最终URL和文件大小
                head_response = await client.head(url, follow_redirects=True)
                final_url = str(head_response.url)
                total_size = int(head_response.headers.get('content-length', 0))
                
                self.log.info(f"最终下载地址: {final_url.split('?')[0]}")
                if total_size:
                    self.log.info(f"文件大小: {total_size / 1024 / 1024:.2f} MB")
                
                # 下载文件
                async with client.stream('GET', final_url) as response:
                    response.raise_for_status()
                    
                    downloaded_size = 0
                    
                    with open(dest_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # 调用进度回调
                            if progress_callback and total_size:
                                progress_callback(downloaded_size, total_size)
                    
                    self.log.info(f"文件下载完成: {dest_path} ({downloaded_size} 字节)")
                    return True
                    
        except Exception as e:
            self.log.error(f"直接下载失败: {self.stack_error(e)}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False