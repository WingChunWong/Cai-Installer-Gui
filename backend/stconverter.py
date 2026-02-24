"""ST 文件转换器 (SteamTools 支持)"""
import struct
import zlib
import logging
from typing import Tuple


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
