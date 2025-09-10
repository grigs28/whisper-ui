import os
import torch
import threading
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from config import config
from utils.logger import logger

# 导入显存记录器
from core.memory_recorder import memory_recorder


class MemoryEstimationPool:
    """显存预估池管理器"""
    
    def __init__(self, gpu_manager):
        self.gpu_manager = gpu_manager
        self.gpu_pools: Dict[int, 'GPUMemoryPool'] = {}  # {gpu_id: GPUMemoryPool}
        self.calibration_data = {}  # 校准数据
        self.segment_duration = int(os.getenv('SEGMENT_DURATION', 30))
        # 使用配置文件中的MEMORY_CONFIDENCE_FACTOR参数
        self.confidence_factor = float(os.getenv('MEMORY_CONFIDENCE_FACTOR', config.MEMORY_CONFIDENCE_FACTOR))
        self._sync_lock = threading.Lock()
    
    def initialize_gpu_pool(self, gpu_id: int):
        """初始化GPU显存池"""
        try:
            # 获取GPU信息
            gpu_info_result = self.gpu_manager.get_gpu_info()
            
            if not gpu_info_result.get('success'):
                logger.error(f"无法获取GPU {gpu_id} 的信息")
                return
            
            # 查找指定GPU的信息
            target_gpu_info = None
            for gpu_info in gpu_info_result['gpus']:
                if gpu_info['id'] == gpu_id:
                    target_gpu_info = gpu_info
                    break
            
            if not target_gpu_info:
                logger.error(f"未找到GPU {gpu_id} 的信息")
                return
            
            total_memory = target_gpu_info['total_memory']
            reserved_memory = target_gpu_info.get('reserved_memory', 1.0)
            
            # 导入GPUMemoryPool类
            from core.gpu_manager import GPUMemoryPool
            self.gpu_pools[gpu_id] = GPUMemoryPool(gpu_id, total_memory, reserved_memory)
            
            # 同步当前显存使用情况
            allocated_memory = target_gpu_info.get('allocated_memory', 0)
            self.gpu_pools[gpu_id].allocated_memory = allocated_memory
            
            available_memory = target_gpu_info.get('available_memory', 0)
            logger.info(f"初始化GPU{gpu_id}显存池: 总计{total_memory:.2f}GB, 已分配: {allocated_memory:.2f}GB, 可用: {available_memory:.2f}GB")
        except Exception as e:
            logger.error(f"初始化GPU {gpu_id} 显存池失败: {e}", exc_info=True)
    
    def sync_gpu_status(self):
        """同步GPU状态"""
        try:
            gpu_info = self.gpu_manager.get_gpu_info()
            
            if gpu_info.get('success') and gpu_info.get('gpus'):
                for gpu in gpu_info['gpus']:
                    gpu_id = gpu['id']
                    allocated_memory = gpu['allocated_memory']
                    
                    # 更新显存池中的分配状态
                    if gpu_id in self.gpu_pools:
                        self.gpu_pools[gpu_id].allocated_memory = allocated_memory
                        
        except Exception as e:
            logger.error(f"同步GPU状态失败: {e}", exc_info=True)
    
    def calibrate_model_memory(self, gpu_id: int, model_name: str, actual_usage: float):
        """校准模型显存使用量"""
        try:
            key = f"{gpu_id}_{model_name}"
            
            if key not in self.calibration_data:
                self.calibration_data[key] = {
                    'samples': [],
                    'avg_usage': 0,
                    'std_deviation': 0
                }
                
            # 添加新的校准样本
            self.calibration_data[key]['samples'].append(actual_usage)
            
            # 保持最近50个样本
            sample_size = int(os.getenv('CALIBRATION_SAMPLE_SIZE', 50))
            if len(self.calibration_data[key]['samples']) > sample_size:
                self.calibration_data[key]['samples'].pop(0)
                
            # 重新计算平均值和标准差
            samples = self.calibration_data[key]['samples']
            avg_usage = sum(samples) / len(samples)
            std_dev = (sum((x - avg_usage) ** 2 for x in samples) / len(samples)) ** 0.5
            
            self.calibration_data[key]['avg_usage'] = avg_usage
            self.calibration_data[key]['std_deviation'] = std_dev
            
            # 更新GPU池中的预估值
            estimated_usage = avg_usage + std_dev * self.confidence_factor
            if gpu_id in self.gpu_pools:
                self.gpu_pools[gpu_id].update_model_estimation(model_name, estimated_usage)
            
            logger.info(f"模型{model_name}在GPU{gpu_id}的显存使用校准: "
                       f"平均{avg_usage:.2f}GB, 预估{estimated_usage:.2f}GB")
        except Exception as e:
            logger.error(f"校准模型 {model_name} 在GPU {gpu_id} 的显存使用量失败: {e}", exc_info=True)
                   
    def get_estimated_memory_usage(self, gpu_id: int, model_name: str) -> float:
        """获取模型预估显存使用量 - 直接使用基础值，不进行校准"""
        try:
            # 直接返回基础预估，不使用校准后的值
            return self._get_default_estimation(model_name)
        except Exception as e:
            logger.error(f"获取GPU {gpu_id} 模型 {model_name} 预估显存失败: {e}", exc_info=True)
            return self._get_default_estimation(model_name)
        
    def can_allocate_tasks(self, gpu_id: int, tasks: List[Dict[str, Any]]) -> bool:
        """检查GPU是否可以分配指定任务"""
        try:
            if gpu_id not in self.gpu_pools:
                logger.warning(f"[MEM_CHECK] GPU{gpu_id} 不存在于显存池中")
                return False
                
            total_required = 0
            for task in tasks:
                model_name = task.get('model', task.get('model_name', 'medium'))
                model_memory = self.get_estimated_memory_usage(gpu_id, model_name)
                # 考虑音频时长对显存的影响
                duration_factor = self._calculate_duration_factor(task)
                task_memory = model_memory * duration_factor
                total_required += task_memory
                logger.info(f"[MEM_CHECK] 任务 {task.get('task_id', 'unknown')} 模型 {model_name} 需要显存: {task_memory:.2f}GB")
                
            # 首先检查全局显存是否足够
            gpu_status = self.get_gpu_status()
            if gpu_id not in gpu_status:
                logger.error(f"[MEM_CHECK] 无法获取GPU{gpu_id}状态")
                return False
                
            global_available = gpu_status[gpu_id]['available_memory']
            if global_available < total_required:
                logger.warning(f"[MEM_CHECK] GPU{gpu_id}全局显存不足: 需要{total_required:.2f}GB, 可用{global_available:.2f}GB")
                return False
                
            # 再检查本系统分配的显存是否足够
            available = self.gpu_pools[gpu_id].available_memory
            can_alloc = self.gpu_pools[gpu_id].can_allocate(total_required)
            logger.info(f"[MEM_CHECK] GPU{gpu_id} 总需求: {total_required:.2f}GB, 可用: {available:.2f}GB, 可分配: {can_alloc}")
            return can_alloc
        except Exception as e:
            logger.error(f"[MEM_CHECK] 检查GPU {gpu_id} 任务分配失败: {e}", exc_info=True)
            return False
        
    def allocate_task_memory(self, gpu_id: int, task: Dict[str, Any]) -> bool:
        """为任务分配显存"""
        try:
            task_id = task.get('id', 'unknown')
            logger.info(f"[ALLOC_MEM] 开始为任务 {task_id} 分配显存")
            
            if gpu_id not in self.gpu_pools:
                logger.error(f"[ALLOC_MEM] GPU{gpu_id} 不存在于显存池中")
                return False
                
            model_name = task.get('model', task.get('model_name', 'medium'))
            model_memory = self.get_estimated_memory_usage(gpu_id, model_name)
            duration_factor = self._calculate_duration_factor(task)
            required_memory = model_memory * duration_factor
            
            logger.info(f"[ALLOC_MEM] 任务 {task_id} 需要显存: {required_memory:.2f}GB (模型: {model_memory:.2f}GB × 时长因子: {duration_factor:.2f})")
            
            # 首先检查全局显存是否足够（使用备用机制）
            try:
                gpu_status = self.get_gpu_status()
                if gpu_id not in gpu_status:
                    logger.warning(f"[ALLOC_MEM] 无法获取GPU{gpu_id}状态，使用备用检查")
                    # 使用备用检查：直接检查显存池
                    if self.gpu_pools[gpu_id].available_memory >= required_memory:
                        logger.info(f"[ALLOC_MEM] 备用检查通过，GPU{gpu_id}显存池可用: {self.gpu_pools[gpu_id].available_memory:.2f}GB")
                    else:
                        logger.error(f"[ALLOC_MEM] 备用检查失败，GPU{gpu_id}显存池不足: 需要{required_memory:.2f}GB, 可用{self.gpu_pools[gpu_id].available_memory:.2f}GB")
                        return False
                else:
                    global_available = gpu_status[gpu_id]['available_memory']
                    if global_available < required_memory:
                        logger.error(f"[ALLOC_MEM] GPU{gpu_id}全局显存不足: 需要{required_memory:.2f}GB, 可用{global_available:.2f}GB")
                        return False
            except Exception as status_error:
                logger.warning(f"[ALLOC_MEM] 获取GPU{gpu_id}状态失败: {status_error}，使用备用检查")
                # 使用备用检查：直接检查显存池
                if self.gpu_pools[gpu_id].available_memory >= required_memory:
                    logger.info(f"[ALLOC_MEM] 备用检查通过，GPU{gpu_id}显存池可用: {self.gpu_pools[gpu_id].available_memory:.2f}GB")
                else:
                    logger.error(f"[ALLOC_MEM] 备用检查失败，GPU{gpu_id}显存池不足: 需要{required_memory:.2f}GB, 可用{self.gpu_pools[gpu_id].available_memory:.2f}GB")
                    return False
            
            # 尝试分配显存，添加超时机制
            try:
                if self.gpu_pools[gpu_id].allocate(required_memory):
                    task['allocated_memory'] = required_memory
                    task['allocated_gpu'] = gpu_id
                    logger.info(f"[ALLOC_MEM] 任务 {task_id} 显存分配成功")
                    return True
                else:
                    logger.error(f"[ALLOC_MEM] 任务 {task_id} 显存分配失败")
                    return False
            except Exception as alloc_error:
                logger.error(f"[ALLOC_MEM] 任务 {task_id} 显存分配异常: {alloc_error}")
                return False
                
        except Exception as e:
            logger.error(f"[ALLOC_MEM] 为任务 {task.get('id', 'unknown')} 分配显存失败: {e}", exc_info=True)
            return False
        
    def release_task_memory(self, task: Dict[str, Any]):
        """释放任务显存"""
        try:
            if 'allocated_memory' in task and 'allocated_gpu' in task:
                gpu_id = task['allocated_gpu']
                memory_size = task['allocated_memory']

                # 若没有有效分配信息则跳过释放，避免 GPUNone 等日志
                if gpu_id is None or memory_size is None:
                    logger.debug(f"[MEMORY] 任务 {task.get('id', 'unknown')} 无有效显存分配信息，跳过释放")
                    return
                
                # 处理memory_size为None的情况
                display_gpu = gpu_id if gpu_id is not None else 'unknown'
                if memory_size is not None:
                    logger.info(f"[MEMORY] 开始释放任务 {task.get('id', 'unknown')} 在GPU{display_gpu}的显存 {memory_size:.2f}GB")
                else:
                    logger.info(f"[MEMORY] 开始释放任务 {task.get('id', 'unknown')} 在GPU{display_gpu}的显存 (大小未知)")
                
                if gpu_id in self.gpu_pools:
                    try:
                        if memory_size is not None:
                            self.gpu_pools[gpu_id].release(memory_size)
                        logger.info(f"[MEMORY] 任务 {task.get('id', 'unknown')} 显存释放成功")
                        # 显存释放后，触发调度器重新检查
                        self._trigger_scheduler_recheck()
                    except Exception as pool_error:
                        logger.error(f"[MEMORY] GPU{gpu_id}显存池释放失败: {pool_error}", exc_info=True)
                else:
                    logger.warning(f"[MEMORY] GPU{display_gpu}不存在于显存池中")
                    
                # 清理任务中的分配信息
                try:
                    del task['allocated_memory']
                    del task['allocated_gpu']
                    logger.info(f"[MEMORY] 任务 {task.get('id', 'unknown')} 分配信息已清理")
                except Exception as cleanup_error:
                    logger.error(f"[MEMORY] 清理任务分配信息失败: {cleanup_error}", exc_info=True)
            else:
                logger.debug(f"[MEMORY] 任务 {task.get('id', 'unknown')} 没有分配显存信息")
        except Exception as e:
            logger.error(f"[MEMORY] 释放任务 {task.get('id', 'unknown')} 显存失败: {e}", exc_info=True)
        
    def _calculate_duration_factor(self, task: Dict[str, Any]) -> float:
        """显存影响因子 - 固定为1.0，文件总显存需求等于基础模型显存需求"""
        # 根据需求：文件总显存需求等于基础模型显存需求
        # 不再考虑音频时长对显存的影响
        return 1.0
            
    def _get_default_estimation(self, model_name: str) -> float:
        """获取默认显存预估"""
        try:
            # 从配置文件获取显存需求
            from config import WHISPER_MODEL_MEMORY_REQUIREMENTS
            # 从WHISPER_MODEL_MEMORY_REQUIREMENTS获取基础预估
            # 确保完全基于配置文件中的设置
            estimation = WHISPER_MODEL_MEMORY_REQUIREMENTS.get(model_name, 5.0)
            logger.debug(f"使用默认显存预估 {model_name}: {estimation:.2f}GB")
            return estimation
        except Exception as e:
            logger.error(f"获取默认显存预估失败: {e}", exc_info=True)
            return 5.0

    def estimate_memory_requirement(self, model_name: str, task: Dict[str, Any] = None) -> float:
        """预估模型显存需求 - 直接使用基础值，不进行校准"""
        try:
            # 直接获取基础预估，不应用任何因子
            base_estimation = self._get_default_estimation(model_name)
            
            logger.debug(f"显存预估: 模型{model_name} 基础值{base_estimation:.2f}GB")
            return base_estimation
            
        except Exception as e:
            logger.error(f"预估模型{model_name}显存需求失败: {e}", exc_info=True)
            # 返回默认预估作为备选
            return self._get_default_estimation(model_name)
    
    def get_gpu_status(self) -> Dict[int, Dict[str, float]]:
        """获取所有GPU状态"""
        # 始终使用硬件级显存信息
        try:
            import threading
            import time
            
            # 使用线程安全的超时机制
            result = {'success': False, 'gpus': []}
            exception = None
            
            def get_gpu_info_with_timeout():
                nonlocal result, exception
                try:
                    result = self.gpu_manager.get_gpu_info()
                except Exception as e:
                    exception = e
            
            # 创建线程执行GPU信息获取
            thread = threading.Thread(target=get_gpu_info_with_timeout)
            thread.daemon = True
            thread.start()
            
            # 等待5秒
            thread.join(timeout=5.0)
            
            if thread.is_alive():
                logger.error("获取GPU信息超时")
                return {}
            
            if exception:
                logger.error(f"获取GPU信息异常: {exception}")
                return {}
            
            gpu_info = result
            if not gpu_info.get('success'):
                logger.error("获取GPU信息失败")
                return {}
                
            status = {}
            for gpu in gpu_info['gpus']:
                gpu_id = gpu['id']
                total_memory = gpu['total_memory']
                allocated_memory = gpu['allocated_memory']
                available_memory = gpu['available_memory']
                
                # 计算空闲显存（总显存 - 已分配显存）
                free_memory = total_memory - allocated_memory
                
                status[gpu_id] = {
                    'total_memory': total_memory,
                    'allocated_memory': allocated_memory,
                    'free_memory': free_memory,
                    'available_memory': available_memory,
                    'utilization': gpu.get('utilization', {}),
                    'temperature': gpu.get('temperature')
                }
            return status
                
        except Exception as e:
            logger.error(f"获取GPU状态失败: {e}", exc_info=True)
            return {}
    
    def cleanup(self):
        """清理内存管理器资源"""
        try:
            logger.info("[MEMORY] 开始清理内存管理器资源...")
            
            # 清理GPU显存池
            for gpu_id, pool in self.gpu_pools.items():
                try:
                    if hasattr(pool, 'cleanup'):
                        pool.cleanup()
                    logger.info(f"[MEMORY] GPU{gpu_id}显存池已清理")
                except Exception as e:
                    logger.error(f"[MEMORY] 清理GPU{gpu_id}显存池失败: {e}", exc_info=True)
            
            # 清理校准数据
            self.calibration_data.clear()
            
            # 清理GPU显存池字典
            self.gpu_pools.clear()
            
            logger.info("[MEMORY] 内存管理器资源清理完成")
        except Exception as e:
            logger.error(f"[MEMORY] 清理内存管理器资源失败: {e}", exc_info=True)

    def record_actual_memory_usage(self, gpu_id: int, model_name: str, 
                                 estimated_memory: float, actual_memory: float,
                                 audio_duration: Optional[float] = None,
                                 task_id: Optional[str] = None, success: bool = True):
        """记录实际显存使用情况"""
        try:
            # 记录到显存记录器
            memory_recorder.record_memory_usage(
                gpu_id=gpu_id,
                model_name=model_name,
                estimated_memory=estimated_memory,
                actual_memory=actual_memory,
                audio_duration=audio_duration,
                task_id=task_id,
                success=success
            )
            
            # 更新校准数据
            self.calibrate_model_memory(gpu_id, model_name, actual_memory)
            
            logger.info(f"[MEMORY] 记录显存使用: GPU{gpu_id} 模型{model_name} "
                       f"预估{estimated_memory:.2f}GB 实际{actual_memory:.2f}GB "
                       f"差异{actual_memory - estimated_memory:+.2f}GB")
            
        except Exception as e:
            logger.error(f"[MEMORY] 记录实际显存使用失败: {e}", exc_info=True)

    def get_memory_statistics(self, model_name: str = None, gpu_id: int = None) -> Dict:
        """获取显存使用统计信息"""
        try:
            if model_name:
                return memory_recorder.get_model_statistics(model_name, gpu_id)
            else:
                return memory_recorder.get_all_statistics()
        except Exception as e:
            logger.error(f"[MEMORY] 获取显存统计信息失败: {e}", exc_info=True)
            return {}

    def get_calibration_factor(self, model_name: str, gpu_id: int = 0) -> float:
        """获取模型的校准因子"""
        try:
            return memory_recorder.get_calibration_factor(model_name, gpu_id)
        except Exception as e:
            logger.error(f"[MEMORY] 获取校准因子失败: {e}", exc_info=True)
            return 1.0

    def estimate_memory_with_calibration(self, model_name: str, gpu_id: int = 0, 
                                       task: Dict[str, Any] = None) -> float:
        """使用校准因子进行显存预估"""
        try:
            # 获取基础预估
            base_estimation = self.estimate_memory_requirement(model_name, task)
            
            # 获取校准因子
            calibration_factor = self.get_calibration_factor(model_name, gpu_id)
            
            # 应用校准因子
            calibrated_estimation = base_estimation * calibration_factor
            
            logger.info(f"[MEMORY] 校准显存预估: 模型{model_name} GPU{gpu_id} "
                       f"基础预估{base_estimation:.2f}GB 校准因子{calibration_factor:.3f} "
                       f"校准后预估{calibrated_estimation:.2f}GB")
            
            return calibrated_estimation
            
        except Exception as e:
            logger.error(f"[MEMORY] 校准显存预估失败: {e}", exc_info=True)
            # 返回基础预估作为备选
            return self.estimate_memory_requirement(model_name, task)

    def get_accuracy_analysis(self) -> Dict:
        """获取预估准确性分析"""
        try:
            return memory_recorder.get_accuracy_analysis()
        except Exception as e:
            logger.error(f"[MEMORY] 获取准确性分析失败: {e}", exc_info=True)
            return {}

    def get_recent_memory_records(self, limit: int = 50) -> List[Dict]:
        """获取最近的显存使用记录"""
        try:
            return memory_recorder.get_recent_records(limit)
        except Exception as e:
            logger.error(f"[MEMORY] 获取最近记录失败: {e}", exc_info=True)
            return []
    
    def _trigger_scheduler_recheck(self):
        """触发调度器重新检查待处理任务"""
        try:
            # 通过优化系统实例触发调度器重新检查
            from core.optimized_whisper import get_optimized_system
            system = get_optimized_system()
            if system and hasattr(system, 'batch_scheduler'):
                # 设置一个标志，让调度器知道需要重新检查
                if hasattr(system.batch_scheduler, 'sync_counter'):
                    system.batch_scheduler.sync_counter = 10  # 强制下次循环同步GPU状态
                logger.info("[MEMORY] 已触发调度器重新检查待处理任务")
        except Exception as e:
            logger.error(f"[MEMORY] 触发调度器重新检查失败: {e}", exc_info=True)
