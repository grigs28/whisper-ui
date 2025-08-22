"""
转录结果保存模块
负责将转录结果保存为不同格式的文件，并支持繁体中文转简体中文
"""

import os
import json
import opencc
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from config import config
from utils.logger import logger


class TranscriptionSaver:
    """转录结果保存器"""
    
    def __init__(self):
        """初始化转录结果保存器"""
        self.output_folder = config.OUTPUT_FOLDER
        
        # 确保输出目录存在
        os.makedirs(self.output_folder, exist_ok=True)
        
        # 初始化繁体转简体转换器
        try:
            self.converter = opencc.OpenCC('t2s')  # 繁体转简体
            logger.info("繁体转简体转换器初始化成功")
        except Exception as e:
            logger.warning(f"繁体转简体转换器初始化失败: {e}")
            self.converter = None
    
    def convert_to_simplified(self, text: str) -> str:
        """将繁体中文转换为简体中文"""
        if not self.converter or not text:
            return text
        
        try:
            return self.converter.convert(text)
        except Exception as e:
            logger.warning(f"繁体转简体转换失败: {e}")
            return text
    
    def save_transcription_result(self, task_data: Dict[str, Any], transcription_result: Dict[str, Any]) -> List[str]:
        """
        保存转录结果到不同格式的文件
        
        Args:
            task_data: 任务数据，包含文件名、输出格式等信息
            transcription_result: 转录结果，包含text、segments等信息
            
        Returns:
            List[str]: 保存的文件路径列表
        """
        try:
            saved_files = []
            
            # 获取任务信息
            filename = task_data.get('files', ['unknown'])[0]
            output_format = task_data.get('output_format', 'txt')
            task_id = task_data.get('task_id', 'unknown')
            
            # 获取不带扩展名的文件名
            base_filename = os.path.splitext(filename)[0]
            
            # 转换繁体为简体
            text = self.convert_to_simplified(transcription_result.get('text', ''))
            segments = transcription_result.get('segments', [])
            
            # 转换segments中的文本
            if segments:
                for segment in segments:
                    if 'text' in segment:
                        segment['text'] = self.convert_to_simplified(segment['text'])
            
            # 根据输出格式保存文件
            if output_format == 'txt':
                saved_file = self._save_txt(base_filename, text, task_id)
                saved_files.append(saved_file)
                
            elif output_format == 'srt':
                saved_file = self._save_srt(base_filename, segments, task_id)
                saved_files.append(saved_file)
                
            elif output_format == 'vtt':
                saved_file = self._save_vtt(base_filename, segments, task_id)
                saved_files.append(saved_file)
                
            elif output_format == 'json':
                # 更新转录结果中的文本
                transcription_result['text'] = text
                transcription_result['segments'] = segments
                saved_file = self._save_json(base_filename, transcription_result, task_id)
                saved_files.append(saved_file)
            
            else:
                # 默认保存为txt格式
                logger.warning(f"未知的输出格式: {output_format}，默认保存为txt格式")
                saved_file = self._save_txt(base_filename, text, task_id)
                saved_files.append(saved_file)
            
            logger.info(f"转录结果已保存: {len(saved_files)} 个文件")
            return saved_files
            
        except Exception as e:
            logger.error(f"保存转录结果失败: {e}", exc_info=True)
            return []
    
    def _save_txt(self, base_filename: str, text: str, task_id: str) -> str:
        """保存为TXT格式"""
        output_filename = f"{base_filename}.txt"
        output_path = os.path.join(self.output_folder, output_filename)
        
        # 如果文件已存在，添加时间戳避免覆盖
        if os.path.exists(output_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{base_filename}_{timestamp}.txt"
            output_path = os.path.join(self.output_folder, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        logger.info(f"TXT文件已保存: {output_filename}")
        return output_path
    
    def _save_srt(self, base_filename: str, segments: List[Dict], task_id: str) -> str:
        """保存为SRT字幕格式"""
        output_filename = f"{base_filename}.srt"
        output_path = os.path.join(self.output_folder, output_filename)
        
        # 如果文件已存在，添加时间戳避免覆盖
        if os.path.exists(output_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{base_filename}_{timestamp}.srt"
            output_path = os.path.join(self.output_folder, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                start_time = self._format_time_srt(segment.get('start', 0))
                end_time = self._format_time_srt(segment.get('end', 0))
                text = segment.get('text', '').strip()
                
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
        
        logger.info(f"SRT文件已保存: {output_filename}")
        return output_path
    
    def _save_vtt(self, base_filename: str, segments: List[Dict], task_id: str) -> str:
        """保存为VTT字幕格式"""
        output_filename = f"{base_filename}.vtt"
        output_path = os.path.join(self.output_folder, output_filename)
        
        # 如果文件已存在，添加时间戳避免覆盖
        if os.path.exists(output_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{base_filename}_{timestamp}.vtt"
            output_path = os.path.join(self.output_folder, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            
            for segment in segments:
                start_time = self._format_time_vtt(segment.get('start', 0))
                end_time = self._format_time_vtt(segment.get('end', 0))
                text = segment.get('text', '').strip()
                
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
        
        logger.info(f"VTT文件已保存: {output_filename}")
        return output_path
    
    def _save_json(self, base_filename: str, transcription_result: Dict, task_id: str) -> str:
        """保存为JSON格式"""
        output_filename = f"{base_filename}.json"
        output_path = os.path.join(self.output_folder, output_filename)
        
        # 如果文件已存在，添加时间戳避免覆盖
        if os.path.exists(output_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{base_filename}_{timestamp}.json"
            output_path = os.path.join(self.output_folder, output_filename)
        
        # 添加元数据
        output_data = {
            'metadata': {
                'task_id': task_id,
                'created_at': datetime.now().isoformat(),
                'filename': f"{base_filename}",
                'format': 'json'
            },
            'transcription': transcription_result
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON文件已保存: {output_filename}")
        return output_path
    
    def _format_time_srt(self, seconds: float) -> str:
        """格式化时间为SRT格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def _format_time_vtt(self, seconds: float) -> str:
        """格式化时间为VTT格式 (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
    
    def get_output_files(self) -> List[Dict[str, Any]]:
        """获取输出目录中的所有文件"""
        try:
            files = []
            if os.path.exists(self.output_folder):
                for filename in os.listdir(self.output_folder):
                    if filename.startswith('.'):
                        continue
                    
                    file_path = os.path.join(self.output_folder, filename)
                    if os.path.isfile(file_path):
                        stat = os.stat(file_path)
                        modified_time = datetime.fromtimestamp(stat.st_mtime)
                        
                        files.append({
                            'name': filename,
                            'size': stat.st_size,
                            'modified': modified_time.isoformat(),
                            'path': file_path
                        })
            
            # 按修改时间排序，最新的在前
            files.sort(key=lambda x: x['modified'], reverse=True)
            return files
            
        except Exception as e:
            logger.error(f"获取输出文件列表失败: {e}", exc_info=True)
            return []


# 创建全局实例
transcription_saver = TranscriptionSaver()







