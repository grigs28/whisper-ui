import os
import time
import threading
import torch
import pynvml
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from config import config
from utils.logger import logger

@dataclass
class GPUInfo:
    id: int
    name: str
    total_memory: float  # GB
    allocated_memory: float  # GB
    reserved_memory: float  # GB
    free_memory: float  # GB
    available_memory: float  # GB
    temperature: Optional[int] = None
    utilization: Optional[Dict[str, int]] = None


class EnhancedGPUManager:
    """增强版GPU管理器，集成NVIDIA ML库"""
    
    def __init__(self):
        # 添加GPU锁字典
        self.gpu_locks: Dict[int, threading.Lock] = {}
        # 初始化时创建所有GPU的锁
        device_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        for i in range(device_count):            
            self.gpu_locks[i] = threading.Lock()
        self.gpu_pools: Dict[int, 'GPUMemoryPool'] = {}
        self.max_tasks_per_gpu = config.MAX_TASKS_PER_GPU
        self.memory_safety_margin = config.MEMORY_SAFETY_MARGIN
        self.nvml_initialized = False
        self._initialize_nvml()
    
    def _initialize_nvml(self):
        """初始化NVIDIA ML库"""
        try:
            pynvml.nvmlInit()
            self.nvml_initialized = True
            logger.info("NVIDIA ML库初始化成功")
        except Exception as e:
            logger.error(f"NVIDIA ML库初始化失败: {e}", exc_info=True)
            self.nvml_initialized = False
    
    def get_detailed_gpu_info(self, gpu_id: int, reserved_memory: float = 1.0) -> Optional[GPUInfo]:
        """获取详细的GPU信息"""
        try:
            if not self.nvml_initialized:
                logger.warning("NVIDIA ML库未初始化")
                return None
                
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
            
            # 获取GPU名称
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            
            # 获取内存信息
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total_memory = mem_info.total / (1024**3)
            allocated_memory = mem_info.used / (1024**3)
            free_memory = mem_info.free / (1024**3)
            
            # 计算可用内存（考虑预留和安全边际）
            safety_reserved = total_memory * self.memory_safety_margin
            available_memory = max(0, free_memory - reserved_memory - safety_reserved)
            
            # 获取温度
            temperature = None
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                temperature = temp
            except Exception as e:
                logger.debug(f"获取GPU {gpu_id} 温度失败: {e}")
            
            # 获取利用率
            utilization = None
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                utilization = {
                    'gpu': util.gpu,
                    'memory': util.memory
                }
            except Exception as e:
                logger.debug(f"获取GPU {gpu_id} 利用率失败: {e}")
            
            return GPUInfo(
                id=gpu_id,
                name=name,
                total_memory=total_memory,
                allocated_memory=allocated_memory,
                reserved_memory=reserved_memory,
                free_memory=free_memory,
                available_memory=available_memory,
                temperature=temperature,
                utilization=utilization
            )
        except Exception as e:
            logger.error(f"获取GPU {gpu_id} 详细信息失败: {e}", exc_info=True)
            return None
    
    def get_all_gpu_info(self) -> List[GPUInfo]:
        """获取所有GPU的详细信息"""
        try:
            gpu_info_list = []
            if not torch.cuda.is_available():
                logger.warning("CUDA不可用，无法获取GPU信息")
                return gpu_info_list
                
            # 获取预留显存设置
            reserved_memory = config.RESERVED_MEMORY
            
            for i in range(torch.cuda.device_count()):
                gpu_info = self.get_detailed_gpu_info(i, reserved_memory)
                if gpu_info:
                    gpu_info_list.append(gpu_info)
            
            return gpu_info_list
        except Exception as e:
            logger.error(f"获取所有GPU信息失败: {e}", exc_info=True)
            return []
    
    def acquire_gpu_lock(self, gpu_id: int, timeout: float = 5.0) -> bool:
        """获取GPU锁"""
        try:
            if gpu_id not in self.gpu_locks:
                self.gpu_locks[gpu_id] = threading.Lock()
            
            acquired = self.gpu_locks[gpu_id].acquire(timeout=timeout)
            if acquired:
                logger.debug(f"成功获取GPU {gpu_id} 锁")
            else:
                logger.warning(f"获取GPU {gpu_id} 锁超时")
            return acquired
        except Exception as e:
            logger.error(f"获取GPU {gpu_id} 锁失败: {e}", exc_info=True)
            return False
        
    def release_gpu_lock(self, gpu_id: int):
        """释放GPU锁"""
        try:
            if gpu_id in self.gpu_locks:
                try:
                    self.gpu_locks[gpu_id].release()
                    logger.debug(f"成功释放GPU {gpu_id} 锁")
                except RuntimeError:
                    # 锁未被占用
                    logger.debug(f"GPU {gpu_id} 锁未被占用")
            else:
                logger.warning(f"GPU {gpu_id} 不存在于锁字典中")
        except Exception as e:
            logger.error(f"释放GPU {gpu_id} 锁失败: {e}", exc_info=True)
    
    def get_gpu_info(self):
        """获取GPU信息（仅使用NVML方案）"""
        try:
            gpu_info_list = self.get_all_gpu_info()
            
            # 格式化GPU信息
            formatted_gpus = []
            for gpu_info in gpu_info_list:
                formatted_gpus.append(self._format_gpu_info(gpu_info))
            
            return {
                'success': True,
                'gpus': formatted_gpus
            }
        except Exception as e:
            logger.error(f"获取GPU信息失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'gpus': []
            }
    
    def _format_gpu_info(self, gpu_info):
        """格式化单个GPU的信息"""
        try:
            # 确保GPU内存池已初始化或更新
            if gpu_info.id not in self.gpu_pools:
                self.gpu_pools[gpu_info.id] = GPUMemoryPool(
                    gpu_info.id, 
                    gpu_info.total_memory, 
                    gpu_info.reserved_memory
                )
            else:
                # 更新现有内存池信息
                pool = self.gpu_pools[gpu_info.id]
                pool.total_memory = gpu_info.total_memory
                pool.reserved_memory = gpu_info.reserved_memory
            
            # 获取内存池实例
            pool = self.gpu_pools[gpu_info.id]
            
            return {
                'id': gpu_info.id,
                'name': gpu_info.name,
                'total_memory': gpu_info.total_memory,
                'allocated_memory': gpu_info.allocated_memory,
                'reserved_memory': gpu_info.reserved_memory,
                'free_memory': gpu_info.free_memory,
                'available_memory': gpu_info.available_memory,
                'temperature': gpu_info.temperature,
                'utilization': gpu_info.utilization or {}
            }
        except Exception as e:
            logger.error(f"格式化GPU {gpu_info.id} 信息失败: {e}", exc_info=True)
            return {}
    
    def get_available_gpus(self):
        """获取可用的GPU列表"""
        try:
            gpu_info = self.get_gpu_info()
            if gpu_info.get('success'):
                return [gpu['id'] for gpu in gpu_info['gpus'] if gpu['available_memory'] > 0]
            logger.warning("获取GPU信息失败，返回空列表")
            return []
        except Exception as e:
            logger.error(f"获取可用GPU列表失败: {str(e)}", exc_info=True)
            return []
    
    def get_gpu_list_for_selector(self):
        """获取GPU选择器列表"""
        try:
            gpu_info = self.get_gpu_info()
            if not gpu_info.get('success'):
                # 返回默认CPU选项
                logger.warning("获取GPU信息失败，返回默认CPU选项")
                return [{
                    'id': 'cpu',
                    'name': 'CPU',
                    'type': 'cpu',
                    'memory_info': 'CPU处理'
                }]
            
            gpu_list = []
            # 添加CPU选项
            gpu_list.append({
                'id': 'cpu',
                'name': 'CPU',
                'type': 'cpu',
                'memory_info': 'CPU处理'
            })
            
            # 添加GPU选项
            for gpu in gpu_info['gpus']:
                gpu_list.append({
                    'id': f"gpu_{gpu['id']}",
                    'name': gpu['name'],
                    'type': 'gpu',
                    'memory_info': f"{gpu['available_memory']:.1f}GB可用",
                    'memory_free': gpu['available_memory'],
                    'temperature': gpu.get('temperature')
                })
            
            return gpu_list
        except Exception as e:
            logger.error(f"获取GPU选择器列表失败: {str(e)}", exc_info=True)
            # 出错时返回默认CPU选项
            return [{
                'id': 'cpu',
                'name': 'CPU',
                'type': 'cpu',
                'memory_info': 'CPU处理'
            }]
    
    def get_best_available_gpu(self):
        """获取最佳可用GPU（空闲内存最多的GPU）"""
        try:
            gpu_info = self.get_gpu_info()
            if not gpu_info.get('success'):
                logger.warning("获取GPU信息失败，无法确定最佳GPU")
                return None
            
            best_gpu = None
            max_free_memory = 0
            
            for gpu in gpu_info['gpus']:
                if gpu['available_memory'] > max_free_memory:
                    max_free_memory = gpu['available_memory']
                    best_gpu = gpu['id']
            
            logger.debug(f"最佳可用GPU: {best_gpu} (可用内存: {max_free_memory:.2f}GB)")
            return best_gpu
        except Exception as e:
            logger.error(f"获取最佳GPU失败: {str(e)}", exc_info=True)
            return None


class GPUMemoryPool:
    """GPU显存池，管理显存分配和任务调度"""
    
    def __init__(self, gpu_id: int, total_memory: float, reserved_memory: float = 1.0):
        self.gpu_id = gpu_id
        self.total_memory = total_memory
        self.reserved_memory = reserved_memory
        self.allocated_memory = 0.0
        self.model_estimations = {}  # 模型显存预估
        self.safety_margin = config.MEMORY_SAFETY_MARGIN
        self.max_tasks_per_gpu = config.MAX_TASKS_PER_GPU
        self.pool_lock = threading.Lock()
    
    @property
    def free_memory(self) -> float:
        """计算空闲显存(总显存 - 已分配显存 - 预留显存)"""
        with self.pool_lock:
            return max(0, self.total_memory - self.allocated_memory - self.reserved_memory)
    
    @property
    def available_memory(self) -> float:
        """计算可用显存(考虑安全边际)"""
        with self.pool_lock:
            # 直接计算，避免递归调用
            free_memory = max(0, self.total_memory - self.allocated_memory - self.reserved_memory)
            return max(0, free_memory - (self.total_memory * self.safety_margin))
    
    def can_allocate(self, required_memory: float) -> bool:
        """检查是否可以分配指定大小的显存"""
        try:
            available = self.available_memory
            can_alloc = available >= required_memory
            logger.info(f"[GPU_POOL] GPU{self.gpu_id} 显存检查: 需要{required_memory:.2f}GB, 可用{available:.2f}GB, 结果: {can_alloc}")
            return can_alloc
        except Exception as e:
            logger.error(f"[GPU_POOL] GPU{self.gpu_id} 显存检查失败: {e}", exc_info=True)
            return False
    
    def allocate(self, memory_size: float) -> bool:
        """分配显存"""
        try:
            # 添加超时机制，避免死锁
            if not self.pool_lock.acquire(timeout=5.0):  # 5秒超时
                logger.error(f"GPU{self.gpu_id} 获取显存池锁超时，可能存在死锁")
                return False
                
            try:
                # 直接计算可用显存，避免递归调用
                free_memory = max(0, self.total_memory - self.allocated_memory - self.reserved_memory)
                available = max(0, free_memory - (self.total_memory * self.safety_margin))
                
                if available >= memory_size:
                    self.allocated_memory += memory_size
                    free_mem_after = max(0, self.total_memory - self.allocated_memory - self.reserved_memory)
                    remaining = max(0, free_mem_after - (self.total_memory * self.safety_margin))
                    logger.info(f"[GPU_ALLOC] GPU{self.gpu_id} 分配显存成功 {memory_size:.2f}GB，剩余 {remaining:.2f}GB")
                    return True
                else:
                    logger.error(f"[GPU_ALLOC] GPU{self.gpu_id} 分配显存失败，需要 {memory_size:.2f}GB，可用 {available:.2f}GB")
                    return False
            finally:
                self.pool_lock.release()
        except Exception as e:
            logger.error(f"[GPU_ALLOC] GPU{self.gpu_id} 分配显存失败: {e}", exc_info=True)
            # 确保锁被释放
            try:
                if self.pool_lock.locked():
                    self.pool_lock.release()
            except:
                pass
            return False
    
    def release(self, memory_size: float):
        """释放显存"""
        try:
            # 添加超时机制，避免死锁
            import threading
            if not self.pool_lock.acquire(timeout=5.0):  # 5秒超时
                logger.error(f"GPU{self.gpu_id} 获取显存池锁超时，可能存在死锁")
                return
                
            try:
                old_allocated = self.allocated_memory
                self.allocated_memory = max(0, self.allocated_memory - memory_size)
                # 直接计算剩余显存，避免递归调用
                free_memory = max(0, self.total_memory - self.allocated_memory - self.reserved_memory)
                remaining = max(0, free_memory - (self.total_memory * self.safety_margin))
                logger.info(f"GPU{self.gpu_id} 释放显存 {memory_size:.2f}GB，原分配: {old_allocated:.2f}GB，剩余: {remaining:.2f}GB")
            finally:
                self.pool_lock.release()
        except Exception as e:
            logger.error(f"GPU{self.gpu_id} 释放显存失败: {e}", exc_info=True)
            # 确保锁被释放
            try:
                if self.pool_lock.locked():
                    self.pool_lock.release()
            except:
                pass
    
    def update_model_estimation(self, model_name: str, estimated_memory: float):
        """更新模型显存预估"""
        try:
            with self.pool_lock:
                self.model_estimations[model_name] = estimated_memory
                logger.info(f"GPU{self.gpu_id} 更新模型 {model_name} 显存预估: {estimated_memory:.2f}GB")
        except Exception as e:
            logger.error(f"GPU{self.gpu_id} 更新模型 {model_name} 显存预估失败: {e}", exc_info=True)
    
    def get_model_estimation(self, model_name: str) -> float:
        """获取模型显存预估"""
        try:
            with self.pool_lock:
                estimation = self.model_estimations.get(model_name, self._get_default_estimation(model_name))
                logger.debug(f"GPU{self.gpu_id} 获取模型 {model_name} 显存预估: {estimation:.2f}GB")
                return estimation
        except Exception as e:
            logger.error(f"GPU{self.gpu_id} 获取模型 {model_name} 显存预估失败: {e}", exc_info=True)
            return self._get_default_estimation(model_name)
    
    def _get_default_estimation(self, model_name: str) -> float:
        """获取默认显存预估"""
        try:
            default_estimations = {
                'tiny': 1.0, 'base': 1.0, 'small': 2.0, 'medium': 5.0,
                'large': 10.0, 'large-v2': 10.0, 'large-v3': 10.0, 'turbo': 4.5
            }
            estimation = default_estimations.get(model_name, 5.0)
            logger.debug(f"GPU{self.gpu_id} 使用默认显存预估 {model_name}: {estimation:.2f}GB")
            return estimation
        except Exception as e:
            logger.error(f"GPU{self.gpu_id} 获取默认显存预估失败: {e}", exc_info=True)
            return 5.0
    
    def can_schedule_task(self) -> bool:
        """检查是否可以调度新任务（基于任务数限制）"""
        # 这里需要与任务管理器集成来获取当前任务数
        # 简化实现，假设总是可以调度
        return True
    
    def cleanup(self):
        """清理GPU显存池资源"""
        try:
            logger.info(f"[GPU_POOL] 开始清理GPU{self.gpu_id}显存池资源...")
            
            # 重置分配状态
            with self.pool_lock:
                self.allocated_memory = 0.0
                self.model_estimations.clear()
            
            logger.info(f"[GPU_POOL] GPU{self.gpu_id}显存池资源清理完成")
        except Exception as e:
            logger.error(f"[GPU_POOL] 清理GPU{self.gpu_id}显存池资源失败: {e}", exc_info=True)
    
    def cleanup(self):
        """清理GPU管理器资源"""
        try:
            logger.info("[GPU] 开始清理GPU管理器资源...")
            
            # 清理GPU锁
            self.gpu_locks.clear()
            
            # 清理GPU显存池
            for gpu_id, pool in self.gpu_pools.items():
                try:
                    if hasattr(pool, 'cleanup'):
                        pool.cleanup()
                    logger.info(f"[GPU] GPU{gpu_id}显存池已清理")
                except Exception as e:
                    logger.error(f"[GPU] 清理GPU{gpu_id}显存池失败: {e}", exc_info=True)
            
            # 清理GPU显存池字典
            self.gpu_pools.clear()
            
            # 关闭NVIDIA ML库
            if self.nvml_initialized:
                try:
                    pynvml.nvmlShutdown()
                    self.nvml_initialized = False
                    logger.info("[GPU] NVIDIA ML库已关闭")
                except Exception as e:
                    logger.error(f"[GPU] 关闭NVIDIA ML库失败: {e}", exc_info=True)
            
            logger.info("[GPU] GPU管理器资源清理完成")
        except Exception as e:
            logger.error(f"[GPU] 清理GPU管理器资源失败: {e}", exc_info=True)


# 全局GPU管理器实例
_gpu_manager_instance = None
_gpu_manager_lock = threading.Lock()

def get_gpu_manager():
    """获取全局GPU管理器实例"""
    global _gpu_manager_instance
    with _gpu_manager_lock:
        if _gpu_manager_instance is None:
            _gpu_manager_instance = EnhancedGPUManager()
        return _gpu_manager_instance
