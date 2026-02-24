"""GitHub API 客户端与相关操作"""
import os
import re
import time
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any

try:
    import httpx
except ImportError:
    raise ImportError("缺少 httpx 库，请使用 'pip install httpx' 安装。")


class GithubClient:
    """GitHub API 客户端"""
    
    def __init__(self, logger: logging.Logger, app_config: Dict[str, Any]):
        self.log = logger
        self.app_config = app_config
        self.last_detected_region: Optional[str] = None
        self.current_country: Optional[str] = None
        self._client_cache: Optional[httpx.AsyncClient] = None
    
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
                country_from_region = self.last_detected_region.replace('not_cn_', '')
                return country_from_region
        
        return 'Unknown'
    
    async def fetch_branch_info(self, client: httpx.AsyncClient, url: str, headers: dict) -> Optional[Dict[str, Any]]:
        """获取分支信息"""
        try:
            self.log.debug(f"请求 GitHub API: {url}")
            r = await client.get(url, headers=headers)
            
            if r.status_code == 401:
                self.log.error(f"401 Unauthorized: {url}")
                self.log.error("GitHub Token 无效或过期")
                return None
            elif r.status_code == 404:
                self.log.error(f"404 Not Found: {url}")
                return None
            elif r.status_code == 403:
                if 'X-RateLimit-Remaining' in r.headers:
                    remaining = r.headers.get('X-RateLimit-Remaining', '0')
                    limit = r.headers.get('X-RateLimit-Limit', '60')
                    self.log.error(f"403 Forbidden: GitHub API速率限制 (剩余 {remaining}/{limit})")
                else:
                    self.log.error(f"403 Forbidden: {url}")
                return None
            
            r.raise_for_status()
            return r.json()
            
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            self.log.error(f"HTTP错误 {status_code}: {url}")
            if status_code == 429:
                self.log.error("429 Too Many Requests: API请求过多")
            return None
        except Exception as e:
            self.log.error(f'获取信息失败: {str(e)}')
            return None
    
    async def get_from_url(self, client: httpx.AsyncClient, sha: str, path: str, repo: str) -> bytes:
        """从URL下载内容"""
        if os.environ.get('IS_CN') == 'yes':
            urls = [
                f'https://cdn.jsdelivr.net/gh/{repo}@{sha}/{path}',
                f'https://ghfast.top/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
                f'https://wget.la/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
                f'https://raw.githubusercontent.com/{repo}/{sha}/{path}'
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
            self.log.error(f"检查更新失败: {str(e)}")
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
            self.log.error(f"下载失败: {str(e)}")
            return False
