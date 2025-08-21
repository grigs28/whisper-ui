import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
import json

from flask import send_file, abort
from werkzeug.utils import secure_filename

from config import config
from utils.logger import logger


class FileManager:
    """文件管理器，负责上传文件、输出文件的管理和清理"""
    
    def __init__(self):
        self.upload_folder = config.UPLOAD_FOLDER
        self.output_folder = config.OUTPUT_FOLDER
        
        # 清理间隔配置（秒）
        self.cleanup_interval = int(os.environ.get('CLEANUP_INTERVAL', 3600))
        
        # 确保目录存在
        os.makedirs(self.upload_folder, exist_ok=True)
        os.makedirs(self.output_folder, exist_ok=True)
    
    def get_uploaded_files(self):
        """获取已上传的文件列表"""
        try:
            files = []
            if os.path.exists(self.upload_folder):
                for filename in os.listdir(self.upload_folder):
                    # 跳过以'.'开头的隐藏文件
                    if filename.startswith('.'):
                        continue
                    file_path = os.path.join(self.upload_folder, filename)
                    if os.path.isfile(file_path):
                        stat = os.stat(file_path)
                        modified_time = datetime.fromtimestamp(stat.st_mtime)
                        files.append({
                            'name': filename,
                            'size': stat.st_size,
                            'modified': modified_time,
                            'modified_timestamp': stat.st_mtime
                        })
            
            # 按修改时间排序（最新的在前）
            files.sort(key=lambda x: x['modified_timestamp'], reverse=True)
            logger.debug(f"获取上传文件列表成功，共 {len(files)} 个文件")
            return files
        except Exception as e:
            logger.error(f"获取上传文件列表时出错: {str(e)}", exc_info=True)
            return []
    
    def get_output_files(self):
        """获取输出文件列表"""
        try:
            files = []
            if os.path.exists(self.output_folder):
                for filename in os.listdir(self.output_folder):
                    # 跳过以'.'开头的隐藏文件
                    if filename.startswith('.'):
                        continue
                    file_path = os.path.join(self.output_folder, filename)
                    if os.path.isfile(file_path):
                        stat = os.stat(file_path)
                        modified_time = datetime.fromtimestamp(stat.st_mtime)
                        files.append({
                            'name': filename,
                            'size': stat.st_size,
                            'modified': modified_time,
                            'modified_timestamp': stat.st_mtime
                        })
            
            # 按修改时间排序（最新的在前）
            files.sort(key=lambda x: x['modified_timestamp'], reverse=True)
            logger.debug(f"获取输出文件列表成功，共 {len(files)} 个文件")
            return files
        except Exception as e:
            logger.error(f"获取输出文件列表时出错: {str(e)}", exc_info=True)
            return []
    
    def _cleanup_folder(self, folder_path, cutoff_time, folder_type):
        """清理指定文件夹中的旧文件"""
        try:
            if not os.path.exists(folder_path):
                logger.warning(f"清理文件夹不存在: {folder_path}")
                return
            
            deleted_count = 0
            total_size = 0
            
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff_time:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        deleted_count += 1
                        total_size += file_size
                        logger.info(f"删除旧{folder_type}: {filename}")
            
            if deleted_count > 0:
                size_mb = total_size / (1024 * 1024)
                logger.info(f"清理完成: 删除了 {deleted_count} 个{folder_type}，释放空间 {size_mb:.2f} MB")
            else:
                logger.debug(f"没有需要清理的{folder_type}文件")
        except Exception as e:
            logger.error(f"清理{folder_type}时出错: {str(e)}", exc_info=True)
    
    def delete_uploaded_file(self, filename):
        """删除上传的文件"""
        try:
            # 安全检查文件名
            safe_filename = secure_filename(filename)
            file_path = os.path.join(self.upload_folder, safe_filename)
            
            # 检查文件是否存在且在正确的目录中
            if not os.path.exists(file_path):
                logger.warning(f"尝试删除不存在的上传文件: {filename}")
                return {'success': False, 'error': '文件不存在'}
            
            # 确保文件路径在上传目录内（防止路径遍历攻击）
            if not os.path.commonpath([file_path, self.upload_folder]) == self.upload_folder:
                logger.warning(f"文件路径越界: {filename}")
                return {'success': False, 'error': '无效的文件路径'}
            
            os.remove(file_path)
            logger.info(f"删除上传文件: {filename}")
            return {'success': True}
        
        except Exception as e:
            error_msg = f"删除上传文件失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {'success': False, 'error': error_msg}
    
    def delete_output_file(self, filename):
        """删除输出文件"""
        try:
            # 安全检查文件名
            safe_filename = secure_filename(filename)
            file_path = os.path.join(self.output_folder, safe_filename)
            
            # 检查文件是否存在且在正确的目录中
            if not os.path.exists(file_path):
                logger.warning(f"尝试删除不存在的输出文件: {filename}")
                return {'success': False, 'error': '文件不存在'}
            
            # 确保文件路径在输出目录内（防止路径遍历攻击）
            if not os.path.commonpath([file_path, self.output_folder]) == self.output_folder:
                logger.warning(f"文件路径越界: {filename}")
                return {'success': False, 'error': '无效的文件路径'}
            
            os.remove(file_path)
            logger.info(f"删除输出文件: {filename}")
            return {'success': True}
        
        except Exception as e:
            error_msg = f"删除输出文件失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {'success': False, 'error': error_msg}
    
    def get_uploaded_file_path(self, filename):
        """获取上传文件的完整路径"""
        try:
            safe_filename = secure_filename(filename)
            file_path = os.path.join(self.upload_folder, safe_filename)
            
            # 安全检查
            if not os.path.exists(file_path):
                logger.warning(f"上传文件不存在: {filename}")
                return None
            
            # 确保文件路径在上传目录内
            if not os.path.commonpath([file_path, self.upload_folder]) == self.upload_folder:
                logger.warning(f"上传文件路径越界: {filename}")
                return None
            
            logger.debug(f"获取上传文件路径成功: {filename}")
            return file_path
        except Exception as e:
            logger.error(f"获取上传文件路径失败: {filename}, 错误: {str(e)}", exc_info=True)
            return None
    
    def get_output_file_path(self, filename):
        """获取输出文件的完整路径"""
        try:
            safe_filename = secure_filename(filename)
            file_path = os.path.join(self.output_folder, safe_filename)
            
            # 安全检查
            if not os.path.exists(file_path):
                logger.warning(f"输出文件不存在: {filename}")
                return None
            
            # 确保文件路径在输出目录内
            if not os.path.commonpath([file_path, self.output_folder]) == self.output_folder:
                logger.warning(f"输出文件路径越界: {filename}")
                return None
            
            logger.debug(f"获取输出文件路径成功: {filename}")
            return file_path
        except Exception as e:
            logger.error(f"获取输出文件路径失败: {filename}, 错误: {str(e)}", exc_info=True)
            return None
    
    def save_uploaded_file(self, file, filename=None):
        """保存上传的文件"""
        try:
            if filename is None:
                filename = file.filename
            
            # 安全检查文件名
            safe_filename = secure_filename(filename)
            if not safe_filename:
                logger.warning(f"上传文件名无效: {filename}")
                return {'success': False, 'error': '无效的文件名'}
            
            # 检查文件扩展名
            allowed_extensions = {'.wav', '.mp3', '.mp4', '.avi', '.mov', '.mkv', '.flv', '.m4a', '.aac', '.ogg'}
            file_ext = os.path.splitext(safe_filename)[1].lower()
            if file_ext not in allowed_extensions:
                logger.warning(f"不支持的文件格式: {file_ext} (文件: {filename})")
                return {'success': False, 'error': f'不支持的文件格式: {file_ext}'}
            
            # 生成唯一文件名（如果文件已存在）
            file_path = os.path.join(self.upload_folder, safe_filename)
            counter = 1
            base_name, ext = os.path.splitext(safe_filename)
            
            while os.path.exists(file_path):
                new_filename = f"{base_name}_{counter}{ext}"
                file_path = os.path.join(self.upload_folder, new_filename)
                safe_filename = new_filename
                counter += 1
            
            # 保存文件
            file.save(file_path)
            
            # 获取文件信息
            file_size = os.path.getsize(file_path)
            
            logger.info(f"文件上传成功: {safe_filename}, 大小: {file_size} bytes")
            
            return {
                'success': True,
                'filename': safe_filename,
                'size': file_size,
                'path': file_path
            }
        
        except Exception as e:
            error_msg = f"保存上传文件失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {'success': False, 'error': error_msg}
    
    def get_file_info(self, file_path):
        """获取文件信息"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"尝试获取不存在的文件信息: {file_path}")
                return None
            
            stat = os.stat(file_path)
            return {
                'name': os.path.basename(file_path),
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            }
        
        except Exception as e:
            logger.error(f"获取文件信息时出错: {str(e)}", exc_info=True)
            return None
    
    def get_folder_size(self, folder_path):
        """获取文件夹大小"""
        try:
            total_size = 0
            file_count = 0
            
            if os.path.exists(folder_path):
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    if os.path.isfile(file_path):
                        total_size += os.path.getsize(file_path)
                        file_count += 1
            
            size_mb = total_size / (1024 * 1024)
            logger.debug(f"文件夹 {folder_path} 大小: {file_count} 个文件, {size_mb:.2f} MB")
            return {
                'total_size': total_size,
                'file_count': file_count,
                'size_mb': size_mb
            }
        
        except Exception as e:
            logger.error(f"获取文件夹大小时出错: {str(e)}", exc_info=True)
            return {'total_size': 0, 'file_count': 0, 'size_mb': 0}
    
    def get_storage_info(self):
        """获取存储信息"""
        try:
            upload_info = self.get_folder_size(self.upload_folder)
            output_info = self.get_folder_size(self.output_folder)
            
            total_size_mb = upload_info['size_mb'] + output_info['size_mb']
            logger.debug(f"存储信息 - 上传文件夹: {upload_info['file_count']} 个文件, {upload_info['size_mb']:.2f} MB; 输出文件夹: {output_info['file_count']} 个文件, {output_info['size_mb']:.2f} MB; 总计: {total_size_mb:.2f} MB")
            
            return {
                'upload_folder': {
                    'path': self.upload_folder,
                    'file_count': upload_info['file_count'],
                    'total_size_mb': upload_info['size_mb']
                },
                'output_folder': {
                    'path': self.output_folder,
                    'file_count': output_info['file_count'],
                    'total_size_mb': output_info['size_mb']
                },
                'total_size_mb': total_size_mb
            }
        
        except Exception as e:
            logger.error(f"获取存储信息时出错: {str(e)}", exc_info=True)
            return {
                'upload_folder': {'path': self.upload_folder, 'file_count': 0, 'total_size_mb': 0},
                'output_folder': {'path': self.output_folder, 'file_count': 0, 'total_size_mb': 0},
                'total_size_mb': 0
            }
