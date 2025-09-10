import asyncio
import threading
import logging
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime
import time

from utils.logger import logger

# 延迟导入，避免循环导入
_optimized_system = None

def _get_optimized_system():
    """获取优化系统实例，使用延迟导入避免循环依赖"""
    global _optimized_system
    if _optimized_system is None:
        try:
            from core.optimized_whisper import OptimizedWhisperSystem
            _optimized_system = OptimizedWhisperSystem()
            logger.info("[QUEUE] 成功创建优化系统实例")
        except ImportError as e:
            logger.error(f"[QUEUE] 导入OptimizedWhisperSystem失败: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"[QUEUE] 创建优化系统实例失败: {e}", exc_info=True)
            return None
    
    if _optimized_system is None:
        logger.warning("[QUEUE] 优化系统实例为None")
        return None
        
    return _optimized_system


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"           # 等待中
    PROCESSING = "processing"     # 处理中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 已失败
    RETRYING = "retrying"        # 重试中


class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    """任务数据结构"""
    id: str
    user_id: str
    files: List[str]
    model: str
    task_type: str
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: float = 0.0
    message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    allocated_memory: Optional[float] = None
    allocated_gpu: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    output_formats: List[str] = None  # 输出格式列表
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'files': self.files,
            'model': self.model,
            'task_type': self.task_type,
            'priority': self.priority.value,
            'status': self.status.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'progress': self.progress,
            'message': self.message,
            'result': self.result,
            'error': self.error,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'allocated_memory': self.allocated_memory,
            'allocated_gpu': self.allocated_gpu,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'output_formats': self.output_formats or ['txt']
        }


class IntelligentQueueManager:
    """智能任务队列管理器"""
    
    def __init__(self, max_concurrent_tasks: int = None):
        # 按模型分组的任务队列
        self.queues: Dict[str, deque] = defaultdict(deque)  # {model_name: deque[Task]}
        # 任务ID到队列的映射
        self._task_queue_mapping: Dict[str, deque] = {}  # {task_id: queue}
        # 正在处理的任务
        self.processing_tasks: Dict[str, Task] = {}  # {task_id: Task}
        # 任务状态回调
        self.status_callbacks: List[Callable] = []
        
        # 并发控制
        from config import config
        self.max_concurrent_tasks = max_concurrent_tasks or config.MAX_CONCURRENT_TRANSCRIPTIONS
        self.current_tasks = 0
        self._lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            'total_added': 0,
            'total_completed': 0,
            'total_failed': 0,
            'total_retried': 0
        }
        
    def add_task(self, task: Task) -> bool:
        """添加任务到队列"""
        with self._lock:
            try:
                self.queues[task.model].append(task)
                # 添加到映射
                self._task_queue_mapping[task.id] = self.queues[task.model]
                self.stats['total_added'] += 1
                logger.info(f"[QUEUE] 添加任务 {task.id} 到 {task.model} 队列, 当前队列长度: {len(self.queues[task.model])}")
                self._notify_status_change(task)
                return True
            except Exception as e:
                logger.error(f"[QUEUE] 添加任务 {task.id} 失败: {e}", exc_info=True)
                return False
                
    def get_next_task(self, model_name: str) -> Optional[Task]:
        """获取指定模型的下一个任务"""
        with self._lock:
            try:
                if model_name in self.queues and self.queues[model_name]:
                    task = self.queues[model_name].popleft()
                    # 从映射中移除
                    if task.id in self._task_queue_mapping:
                        del self._task_queue_mapping[task.id]
                    logger.debug(f"[QUEUE] 从 {model_name} 队列获取任务 {task.id}")
                    return task
                logger.debug(f"[QUEUE] {model_name} 队列为空或不存在")
                return None
            except Exception as e:
                logger.error(f"[QUEUE] 获取任务失败: {e}", exc_info=True)
                return None
            
    def get_tasks_by_model(self, model_name: str) -> List[Task]:
        """获取指定模型的所有任务"""
        with self._lock:
            return list(self.queues.get(model_name, []))
            
    def move_task_to_processing(self, task: Task) -> bool:
        """将任务移动到处理中状态"""
        with self._lock:
            try:
                if self.current_tasks >= self.max_concurrent_tasks:
                    logger.warning(f"[QUEUE] 达到最大并发任务数 {self.max_concurrent_tasks}")
                    return False
                
                # 从原队列中移除任务
                if task.model in self.queues:
                    try:
                        self.queues[task.model].remove(task)
                        logger.debug(f"[QUEUE] 从 {task.model} 队列中移除任务 {task.id}")
                    except ValueError:
                        logger.warning(f"[QUEUE] 任务 {task.id} 不在 {task.model} 队列中")
                
                # 从映射中移除
                if task.id in self._task_queue_mapping:
                    del self._task_queue_mapping[task.id]
                    
                task.status = TaskStatus.PROCESSING
                task.start_time = datetime.now()  # 设置开始时间
                task.updated_at = datetime.now()
                self.processing_tasks[task.id] = task
                self.current_tasks += 1
                self._notify_status_change(task)
                logger.info(f"[QUEUE] 任务 {task.id} 进入处理状态, 当前处理中任务数: {self.current_tasks}")
                return True
            except Exception as e:
                logger.error(f"[QUEUE] 移动任务到处理状态失败: {e}", exc_info=True)
                return False
            
    def complete_task(self, task_id: str, result: Any = None) -> bool:
        """标记任务为完成"""
        logger.info(f"[QUEUE] 开始完成任务 {task_id}")
        with self._lock:
            try:
                if task_id not in self.processing_tasks:
                    logger.warning(f"[QUEUE] 尝试完成不存在的任务 {task_id}")
                    return False
                    
                task = self.processing_tasks[task_id]
                logger.info(f"[QUEUE] 找到任务 {task_id}，开始处理")
                
                # 显存释放交由处理器与调度器路径负责，完成阶段不再重复释放
                logger.debug(f"[QUEUE] 任务 {task_id} 完成阶段跳过显存释放（已由处理器/调度器负责）")
                
                # 更新任务状态为完成
                try:
                    logger.info(f"[QUEUE] 更新任务 {task_id} 状态为完成")
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.progress = 100.0
                    task.end_time = datetime.now()  # 设置结束时间
                    task.updated_at = datetime.now()
                except Exception as e:
                    logger.error(f"[QUEUE] 更新任务 {task_id} 状态失败: {e}", exc_info=True)
                    return False
                
                # 从处理中队列移除
                try:
                    logger.info(f"[QUEUE] 从处理中队列移除任务 {task_id}")
                    del self.processing_tasks[task_id]
                    self.current_tasks -= 1
                    self.stats['total_completed'] += 1
                    logger.info(f"[QUEUE] 任务 {task_id} 完成, 剩余处理中任务数: {self.current_tasks}")
                except Exception as e:
                    logger.error(f"[QUEUE] 从处理中队列移除任务 {task_id} 失败: {e}", exc_info=True)
                    return False
                
                # 异步通知状态变更，避免阻塞
                try:
                    logger.info(f"[QUEUE] 开始通知任务 {task_id} 状态变更")
                    self._notify_status_change(task)
                    logger.info(f"[QUEUE] 任务 {task_id} 状态变更通知完成")
                    
                    # 显存释放后，触发调度器重新评估待处理任务
                    self._trigger_scheduler_recheck()
                    
                    # 尝试自动调度待处理任务
                    self._try_schedule_pending_tasks()
                    
                except Exception as notify_error:
                    logger.warning(f"[QUEUE] 通知任务状态变更失败: {notify_error}")
                    # 通知失败不影响任务完成
                
                logger.info(f"[QUEUE] 任务 {task_id} 完成处理结束")
                return True
            except Exception as e:
                logger.error(f"[QUEUE] 完成任务失败: {e}", exc_info=True)
                return False
            
    def fail_task(self, task_id: str, error: str, should_retry: bool = True) -> bool:
        """标记任务为失败"""
        with self._lock:
            try:
                # 先检查处理中任务
                if task_id in self.processing_tasks:
                    task = self.processing_tasks[task_id]
                else:
                    # 检查队列中的任务
                    task = self._find_task_in_queues(task_id)
                    if not task:
                        logger.warning(f"[QUEUE] 尝试失败不存在的任务 {task_id}")
                        return False
                
                # 检查任务当前状态，避免重复处理已完成的任务
                if task.status == TaskStatus.COMPLETED:
                    logger.warning(f"[QUEUE] 任务 {task_id} 已完成，跳过失败处理")
                    return True
                elif task.status == TaskStatus.FAILED:
                    logger.warning(f"[QUEUE] 任务 {task_id} 已失败，跳过重复失败处理")
                    return True
                
                # 释放任务显存
                try:
                    # 通过优化系统实例释放显存
                    system = _get_optimized_system()
                    if system and hasattr(system, 'memory_pool') and hasattr(system.memory_pool, 'release_task_memory'):
                        task_dict = task.to_dict()
                        system.memory_pool.release_task_memory(task_dict)
                        logger.info(f"[QUEUE] 失败任务 {task_id} 显存已释放")
                except Exception as e:
                    logger.error(f"[QUEUE] 释放失败任务 {task_id} 显存失败: {e}", exc_info=True)
                    # 继续执行，不因为显存释放失败而中断任务失败流程
                
                # 更新任务状态
                try:
                    task.error = error
                    task.updated_at = datetime.now()
                except Exception as e:
                    logger.error(f"[QUEUE] 更新失败任务 {task_id} 状态失败: {e}", exc_info=True)
                    return False
                
                # 判断是否为转录错误，只有转录错误才重试
                is_transcription_error = self._is_transcription_error(error)
                
                # 只有转录错误且重试次数未达上限才重试
                if should_retry and is_transcription_error and task.retry_count < task.max_retries:
                    try:
                        task.status = TaskStatus.PENDING  # 修复：重试任务应该设为PENDING状态
                        task.retry_count += 1
                        self.stats['total_retried'] += 1
                        
                        # 重新加入队列尾部（按要求修改）
                        if task.id in self.processing_tasks:
                            del self.processing_tasks[task.id]
                            self.current_tasks -= 1
                        self.queues[task.model].append(task)
                        # 更新映射
                        self._task_queue_mapping[task.id] = self.queues[task.model]
                        logger.info(f"[QUEUE] 任务 {task_id} 失败, 将重试 (第{task.retry_count}次)")
                    except Exception as e:
                        logger.error(f"[QUEUE] 重试任务 {task_id} 失败: {e}", exc_info=True)
                        return False
                else:
                    try:
                        task.status = TaskStatus.FAILED
                        # 从处理中队列移除
                        if task.id in self.processing_tasks:
                            del self.processing_tasks[task.id]
                            self.current_tasks -= 1
                        self.stats['total_failed'] += 1
                        logger.info(f"[QUEUE] 任务 {task_id} 失败, 达到最大重试次数")
                    except Exception as e:
                        logger.error(f"[QUEUE] 标记任务 {task_id} 为失败状态失败: {e}", exc_info=True)
                        return False
                    
                # 通知状态变更
                try:
                    self._notify_status_change(task)
                except Exception as notify_error:
                    logger.warning(f"[QUEUE] 通知失败任务状态变更失败: {notify_error}")
                    # 通知失败不影响任务失败流程
                
                return True
            except Exception as e:
                logger.error(f"[QUEUE] 标记任务失败失败: {e}", exc_info=True)
                return False
    
    def _is_transcription_error(self, error: str) -> bool:
        """判断是否为转录错误，只有转录错误才重试"""
        if not error:
            return False
        
        # 转录相关的错误关键词
        transcription_error_keywords = [
            '转录', 'transcribe', 'whisper', '模型', 'model', 'audio', '音频',
            'cuda', 'gpu', 'memory', '显存', 'out of memory', 'cuda out of memory',
            'timeout', '超时', 'connection', '连接'
        ]
        
        # 非转录错误关键词（这些错误不应该重试）
        non_retry_keywords = [
            '文件不存在', 'file not found', '无法移动到处理状态', '处理器未设置',
            '调度执行错误', '结果处理错误', '处理无结果返回', '无法分配显存',
            '显存不足', 'memory insufficient', 'invalid file', '不支持的文件格式'
        ]
        
        error_lower = error.lower()
        
        # 先检查是否为非重试错误
        for keyword in non_retry_keywords:
            if keyword.lower() in error_lower:
                logger.info(f"[QUEUE] 检测到非重试错误: {keyword}")
                return False
        
        # 再检查是否为转录错误
        for keyword in transcription_error_keywords:
            if keyword.lower() in error_lower:
                logger.info(f"[QUEUE] 检测到转录错误: {keyword}")
                return True
        
        # 默认不重试
        logger.info(f"[QUEUE] 未识别的错误类型，不重试: {error}")
        return False
            
    def retry_task(self, task_id: str) -> bool:
        """重试任务"""
        with self._lock:
            try:
                # 从失败状态中移除任务并重新加入队列
                task = None
                # 查找处理中任务
                if task_id in self.processing_tasks:
                    task = self.processing_tasks[task_id]
                # 查找队列中的任务
                if not task:
                    task = self._find_task_in_queues(task_id)
                    
                if not task:
                    logger.warning(f"[QUEUE] 尝试重试不存在的任务 {task_id}")
                    return False
                    
                # 重置任务状态
                task.status = TaskStatus.PENDING
                task.error = None
                task.updated_at = datetime.now()
                task.retry_count += 1
                
                # 确保任务在队列中
                if task_id in self.processing_tasks:
                    del self.processing_tasks[task_id]
                    self.current_tasks -= 1
                    
                # 如果任务不在队列中，则添加到队列尾部（按要求修改）
                if task not in self.queues[task.model]:
                    self.queues[task.model].append(task)
                    # 更新映射
                    self._task_queue_mapping[task.id] = self.queues[task.model]
                    
                self.stats['total_retried'] += 1
                self._notify_status_change(task)
                logger.info(f"[QUEUE] 任务 {task_id} 重新排队等待处理")
                return True
            except Exception as e:
                logger.error(f"[QUEUE] 重试任务失败: {e}", exc_info=True)
                return False
            
    def update_task_progress(self, task_id: str, progress: float, message: str = None):
        """更新任务进度 - 支持平滑进度更新"""
        with self._lock:
            try:
                task = self.processing_tasks.get(task_id)
                if task:
                    # 确保进度在有效范围内
                    progress = max(0.0, min(100.0, progress))
                    
                    # 只有当进度有显著变化时才更新（降低阈值，提高响应性）
                    if abs(task.progress - progress) >= 0.1 or progress >= 100.0:
                        task.progress = progress
                        task.updated_at = datetime.now()
                        
                        # 如果有消息，更新任务消息
                        if message:
                            task.message = message
                        
                        # 发送进度更新通知
                        self._notify_progress_update(task)
                        
                        logger.debug(f"[QUEUE] 任务 {task_id} 进度更新: {progress:.1f}%")
                        
            except Exception as e:
                logger.error(f"[QUEUE] 更新任务进度失败: {e}", exc_info=True)
    
    def _notify_progress_update(self, task: Task):
        """通知任务进度更新"""
        try:
            # 构建进度更新消息
            progress_data = {
                'id': task.id,
                'status': task.status.value,
                'progress': task.progress,
                'message': getattr(task, 'message', None),
                'updated_at': task.updated_at.isoformat(),
                'type': 'progress_update'
            }
            
            # 通知所有状态回调
            for callback in self.status_callbacks:
                try:
                    callback(progress_data)
                except Exception as e:
                    logger.error(f"[QUEUE] 进度更新回调执行失败: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"[QUEUE] 通知进度更新失败: {e}", exc_info=True)
    
    def _trigger_scheduler_recheck(self):
        """触发调度器重新检查待处理任务"""
        try:
            # 通过优化系统实例触发调度器重新检查
            system = _get_optimized_system()
            if system and hasattr(system, 'batch_scheduler'):
                # 设置一个标志，让调度器知道需要重新检查
                if hasattr(system.batch_scheduler, 'sync_counter'):
                    system.batch_scheduler.sync_counter = 10  # 强制下次循环同步GPU状态
                logger.info("[QUEUE] 已触发调度器重新检查待处理任务")
        except Exception as e:
            logger.error(f"[QUEUE] 触发调度器重新检查失败: {e}", exc_info=True)
    
    def _try_schedule_pending_tasks(self):
        """尝试自动调度待处理任务"""
        try:
            # 检查是否还有可用的处理槽位
            if self.current_tasks >= self.max_concurrent_tasks:
                logger.info(f"[QUEUE] 当前处理中任务数已达上限 {self.max_concurrent_tasks}，跳过自动调度")
                return
            
            # 获取待处理任务
            pending_tasks = []
            for model_name, queue in self.queues.items():
                pending_tasks.extend(list(queue))
            
            if not pending_tasks:
                logger.info("[QUEUE] 没有待处理任务，跳过自动调度")
                return
            
            # 按优先级排序
            pending_tasks.sort(key=lambda t: t.priority.value, reverse=True)
            
            # 尝试调度任务
            scheduled_count = 0
            for task in pending_tasks:
                if self.current_tasks >= self.max_concurrent_tasks:
                    break
                
                # 检查显存是否足够
                if self._check_memory_availability(task):
                    # 尝试移动到处理状态
                    if self.move_task_to_processing(task):
                        scheduled_count += 1
                        logger.info(f"[QUEUE] 自动调度任务 {task.id} 到处理状态")
                    else:
                        logger.warning(f"[QUEUE] 自动调度任务 {task.id} 失败")
                else:
                    logger.info(f"[QUEUE] 任务 {task.id} 显存不足，跳过调度")
                    break  # 显存不足时停止尝试调度后续任务
            
            if scheduled_count > 0:
                logger.info(f"[QUEUE] 自动调度完成，成功调度 {scheduled_count} 个任务")
                
        except Exception as e:
            logger.error(f"[QUEUE] 自动调度待处理任务失败: {e}", exc_info=True)
    
    def _check_memory_availability(self, task: Task) -> bool:
        """检查任务是否有足够的显存"""
        try:
            from core.optimized_whisper import get_optimized_system
            system = get_optimized_system()
            if system and hasattr(system, 'memory_pool'):
                # 获取GPU状态
                gpu_status = system.memory_pool.get_gpu_status()
                if not gpu_status:
                    return False
                
                # 检查是否有GPU有足够显存
                for gpu_id, status in gpu_status.items():
                    if status['available_memory'] > 1.0:  # 保留1GB安全边际
                        # 估算任务所需显存
                        estimated_memory = system.memory_pool.get_estimated_memory_usage(gpu_id, task.model)
                        if status['available_memory'] >= estimated_memory:
                            return True
                
                return False
            else:
                return True  # 如果无法检查显存，默认允许调度
                
        except Exception as e:
            logger.error(f"[QUEUE] 检查显存可用性失败: {e}", exc_info=True)
            return True  # 出错时默认允许调度
                
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        with self._lock:
            model_stats = {}
            for model_name, queue in self.queues.items():
                model_stats[model_name] = {
                    'pending': len(queue),
                    'processing': len([t for t in self.processing_tasks.values() if t.model == model_name])
                }
                
            return {
                'models': model_stats,
                'total_pending': sum(len(q) for q in self.queues.values()),
                'total_processing': self.current_tasks,
                'stats': self.stats.copy()
            }
            
    def add_status_callback(self, callback: Callable):
        """添加状态变更回调"""
        with self._lock:
            self.status_callbacks.append(callback)
            
    def _notify_status_change(self, task: Task):
        """通知任务状态变更"""
        for callback in self.status_callbacks:
            try:
                callback(task.to_dict())
            except Exception as e:
                logger.error(f"[QUEUE] 状态回调执行失败: {e}", exc_info=True)
                
    def _find_task_in_queues(self, task_id: str) -> Optional[Task]:
        """在所有队列中查找任务"""
        try:
            # 使用映射快速查找
            if task_id in self._task_queue_mapping:
                queue = self._task_queue_mapping[task_id]
                return next((t for t in queue if t.id == task_id), None)
            
            # 回退到遍历查找（用于处理映射不一致的情况）
            for queue in self.queues.values():
                for task in queue:
                    if task.id == task_id:
                        # 修复映射
                        self._task_queue_mapping[task_id] = queue
                        return task
            return None
        except Exception as e:
            logger.error(f"[QUEUE] 查找任务失败: {e}", exc_info=True)
            return None
        
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务信息"""
        with self._lock:
            try:
                # 先查找处理中的任务
                if task_id in self.processing_tasks:
                    return self.processing_tasks[task_id]
                # 再查找队列中的任务
                return self._find_task_in_queues(task_id)
            except Exception as e:
                logger.error(f"[QUEUE] 获取任务信息失败: {e}", exc_info=True)
                return None
            
    def remove_task(self, task_id: str) -> bool:
        """移除任务"""
        with self._lock:
            try:
                # 从处理中任务移除
                if task_id in self.processing_tasks:
                    del self.processing_tasks[task_id]
                    self.current_tasks -= 1
                    # 从映射中移除
                    if task_id in self._task_queue_mapping:
                        del self._task_queue_mapping[task_id]
                    return True
                    
                # 从队列中移除
                if task_id in self._task_queue_mapping:
                    queue = self._task_queue_mapping[task_id]
                    task = next((t for t in queue if t.id == task_id), None)
                    if task:
                        queue.remove(task)
                        del self._task_queue_mapping[task_id]
                        return True
                        
                return False
            except Exception as e:
                logger.error(f"[QUEUE] 移除任务失败: {e}", exc_info=True)
                return False
