"""
显存记录器（MemoryRecorder）
用于记录和分析模型加载时的实际显存使用情况，为显存预估校准提供数据支持
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class MemoryUsageRecord:
    """显存使用记录数据结构"""
    timestamp: float              # 记录时间戳
    gpu_id: int                  # GPU设备ID
    model_name: str              # 模型名称
    estimated_memory: float      # 预估显存 (GB)
    actual_memory: float         # 实际显存 (GB)
    difference: float            # 差异 (实际 - 预估)
    audio_duration: Optional[float] = None  # 音频时长 (秒)
    task_id: Optional[str] = None  # 任务ID
    success: bool = True         # 任务是否成功
    calibration_factor: float = 1.0  # 校准因子


class MemoryRecorder:
    """显存使用记录器主类"""
    
    def __init__(self, data_file: str = "data/memory_usage.json"):
        self.data_file = data_file
        self.records: List[MemoryUsageRecord] = []
        self._lock = threading.Lock()
        self._save_pending = False
        
        # 确保数据目录存在
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        
        # 加载现有记录
        self._load_records()
        
        logger.info(f"显存记录器初始化完成，数据文件: {data_file}")
    
    def _load_records(self):
        """加载现有记录"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.records = [MemoryUsageRecord(**record) for record in data.get('records', [])]
                logger.info(f"加载显存使用记录: {len(self.records)} 条")
            else:
                logger.info("显存使用记录文件不存在，将创建新文件")
        except Exception as e:
            logger.error(f"加载显存使用记录失败: {e}")
            self.records = []
    
    def _save_records(self):
        """保存记录到文件"""
        try:
            with self._lock:
                data = {
                    'last_updated': datetime.now().isoformat(),
                    'total_records': len(self.records),
                    'records': [asdict(record) for record in self.records]
                }
                
                # 创建临时文件
                temp_file = f"{self.data_file}.tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 原子性替换文件
                os.replace(temp_file, self.data_file)
                
                logger.debug(f"显存使用记录已保存: {len(self.records)} 条记录")
                
        except Exception as e:
            logger.error(f"保存显存使用记录失败: {e}")
    
    def _async_save(self):
        """异步保存记录"""
        if not self._save_pending:
            self._save_pending = True
            threading.Thread(target=self._save_records_async, daemon=True).start()
    
    def _save_records_async(self):
        """异步保存记录的具体实现"""
        try:
            self._save_records()
        finally:
            self._save_pending = False
    
    def record_memory_usage(self, gpu_id: int, model_name: str, 
                          estimated_memory: float, actual_memory: float,
                          audio_duration: Optional[float] = None,
                          task_id: Optional[str] = None, success: bool = True):
        """记录显存使用情况"""
        try:
            # 计算校准因子
            calibration_factor = actual_memory / estimated_memory if estimated_memory > 0 else 1.0
            
            record = MemoryUsageRecord(
                timestamp=time.time(),
                gpu_id=gpu_id,
                model_name=model_name,
                estimated_memory=estimated_memory,
                actual_memory=actual_memory,
                difference=actual_memory - estimated_memory,
                audio_duration=audio_duration,
                task_id=task_id,
                success=success,
                calibration_factor=calibration_factor
            )
            
            with self._lock:
                self.records.append(record)
                
                # 保持最近1000条记录
                max_records = 1000
                if len(self.records) > max_records:
                    self.records = self.records[-max_records:]
            
            # 异步保存
            self._async_save()
            
            logger.info(f"记录显存使用: GPU{gpu_id} 模型{model_name} "
                       f"预估{estimated_memory:.2f}GB 实际{actual_memory:.2f}GB "
                       f"差异{record.difference:+.2f}GB 校准因子{calibration_factor:.3f}")
            
        except Exception as e:
            logger.error(f"记录显存使用失败: {e}")
    
    def get_model_statistics(self, model_name: str, gpu_id: Optional[int] = None) -> Dict:
        """获取模型显存使用统计"""
        try:
            with self._lock:
                # 过滤记录
                filtered_records = self.records
                if gpu_id is not None:
                    filtered_records = [r for r in filtered_records if r.gpu_id == gpu_id]
                filtered_records = [r for r in filtered_records if r.model_name == model_name]
                
                if not filtered_records:
                    return {
                        'model_name': model_name,
                        'gpu_id': gpu_id,
                        'total_records': 0,
                        'avg_estimated': 0,
                        'avg_actual': 0,
                        'avg_difference': 0,
                        'calibration_factor': 1.0,
                        'accuracy_rate': 0.0
                    }
                
                # 计算统计信息
                total_records = len(filtered_records)
                avg_estimated = sum(r.estimated_memory for r in filtered_records) / total_records
                avg_actual = sum(r.actual_memory for r in filtered_records) / total_records
                avg_difference = sum(r.difference for r in filtered_records) / total_records
                avg_calibration_factor = sum(r.calibration_factor for r in filtered_records) / total_records
                
                # 计算预估准确率（差异在10%以内算准确）
                accurate_count = sum(1 for r in filtered_records if abs(r.difference / r.estimated_memory) <= 0.1)
                accuracy_rate = (accurate_count / total_records) * 100 if total_records > 0 else 0
                
                return {
                    'model_name': model_name,
                    'gpu_id': gpu_id,
                    'total_records': total_records,
                    'avg_estimated': round(avg_estimated, 2),
                    'avg_actual': round(avg_actual, 2),
                    'avg_difference': round(avg_difference, 2),
                    'calibration_factor': round(avg_calibration_factor, 3),
                    'accuracy_rate': round(accuracy_rate, 1),
                    'last_updated': datetime.fromtimestamp(filtered_records[-1].timestamp).isoformat()
                }
                
        except Exception as e:
            logger.error(f"获取模型统计信息失败: {e}")
            return {}
    
    def get_all_statistics(self) -> Dict:
        """获取所有模型的统计信息"""
        try:
            with self._lock:
                # 获取所有唯一的模型和GPU组合
                model_gpu_combinations = set()
                for record in self.records:
                    model_gpu_combinations.add((record.model_name, record.gpu_id))
                
                statistics = {}
                for model_name, gpu_id in model_gpu_combinations:
                    # 直接在这里计算统计信息，避免再次获取锁
                    filtered_records = [r for r in self.records if r.gpu_id == gpu_id and r.model_name == model_name]
                    
                    if not filtered_records:
                        stats = {
                            'model_name': model_name,
                            'gpu_id': gpu_id,
                            'total_records': 0,
                            'avg_estimated': 0,
                            'avg_actual': 0,
                            'avg_difference': 0,
                            'calibration_factor': 1.0,
                            'accuracy_rate': 0.0
                        }
                    else:
                        # 计算统计信息
                        total_records = len(filtered_records)
                        avg_estimated = sum(r.estimated_memory for r in filtered_records) / total_records
                        avg_actual = sum(r.actual_memory for r in filtered_records) / total_records
                        avg_difference = sum(r.difference for r in filtered_records) / total_records
                        avg_calibration_factor = sum(r.calibration_factor for r in filtered_records) / total_records
                        
                        # 计算预估准确率（差异在10%以内算准确）
                        accurate_count = sum(1 for r in filtered_records if abs(r.difference / r.estimated_memory) <= 0.1)
                        accuracy_rate = (accurate_count / total_records) * 100 if total_records > 0 else 0
                        
                        stats = {
                            'model_name': model_name,
                            'gpu_id': gpu_id,
                            'total_records': total_records,
                            'avg_estimated': round(avg_estimated, 2),
                            'avg_actual': round(avg_actual, 2),
                            'avg_difference': round(avg_difference, 2),
                            'calibration_factor': round(avg_calibration_factor, 3),
                            'accuracy_rate': round(accuracy_rate, 1),
                            'last_updated': datetime.fromtimestamp(filtered_records[-1].timestamp).isoformat()
                        }
                    
                    key = f"{model_name}_gpu{gpu_id}"
                    statistics[key] = stats
                
                return statistics
                
        except Exception as e:
            logger.error(f"获取所有统计信息失败: {e}")
            return {}
    
    def get_recent_records(self, limit: int = 50) -> List[Dict]:
        """获取最近的记录"""
        try:
            with self._lock:
                recent_records = self.records[-limit:] if len(self.records) > limit else self.records
                return [asdict(record) for record in recent_records]
        except Exception as e:
            logger.error(f"获取最近记录失败: {e}")
            return []
    
    def clear_old_records(self, days: int = 30):
        """清理指定天数之前的旧记录"""
        try:
            cutoff_time = time.time() - (days * 24 * 3600)
            
            with self._lock:
                original_count = len(self.records)
                self.records = [r for r in self.records if r.timestamp >= cutoff_time]
                removed_count = original_count - len(self.records)
            
            if removed_count > 0:
                self._async_save()
                logger.info(f"清理了 {removed_count} 条旧记录（{days}天前）")
            
        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
    
    def get_calibration_factor(self, model_name: str, gpu_id: int = 0) -> float:
        """获取模型的校准因子"""
        try:
            stats = self.get_model_statistics(model_name, gpu_id)
            return stats.get('calibration_factor', 1.0)
        except Exception as e:
            logger.error(f"获取校准因子失败: {e}")
            return 1.0
    
    def get_accuracy_analysis(self) -> Dict:
        """获取预估准确性分析"""
        try:
            with self._lock:
                if not self.records:
                    return {
                        'total_records': 0,
                        'overall_accuracy': 0.0,
                        'model_accuracy': {},
                        'gpu_accuracy': {}
                    }
                
                # 总体准确率
                total_records = len(self.records)
                accurate_count = sum(1 for r in self.records if abs(r.difference / r.estimated_memory) <= 0.1)
                overall_accuracy = (accurate_count / total_records) * 100
                
                # 按模型统计准确率
                model_accuracy = {}
                for record in self.records:
                    model_name = record.model_name
                    if model_name not in model_accuracy:
                        model_accuracy[model_name] = {'total': 0, 'accurate': 0}
                    
                    model_accuracy[model_name]['total'] += 1
                    if abs(record.difference / record.estimated_memory) <= 0.1:
                        model_accuracy[model_name]['accurate'] += 1
                
                # 计算每个模型的准确率
                for model_name in model_accuracy:
                    total = model_accuracy[model_name]['total']
                    accurate = model_accuracy[model_name]['accurate']
                    model_accuracy[model_name] = round((accurate / total) * 100, 1)
                
                # 按GPU统计准确率
                gpu_accuracy = {}
                for record in self.records:
                    gpu_id = record.gpu_id
                    if gpu_id not in gpu_accuracy:
                        gpu_accuracy[gpu_id] = {'total': 0, 'accurate': 0}
                    
                    gpu_accuracy[gpu_id]['total'] += 1
                    if abs(record.difference / record.estimated_memory) <= 0.1:
                        gpu_accuracy[gpu_id]['accurate'] += 1
                
                # 计算每个GPU的准确率
                for gpu_id in gpu_accuracy:
                    total = gpu_accuracy[gpu_id]['total']
                    accurate = gpu_accuracy[gpu_id]['accurate']
                    gpu_accuracy[gpu_id] = round((accurate / total) * 100, 1)
                
                return {
                    'total_records': total_records,
                    'overall_accuracy': round(overall_accuracy, 1),
                    'model_accuracy': model_accuracy,
                    'gpu_accuracy': gpu_accuracy
                }
                
        except Exception as e:
            logger.error(f"获取准确性分析失败: {e}")
            return {}


# 全局记录器实例
memory_recorder = MemoryRecorder()
