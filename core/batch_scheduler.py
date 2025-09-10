import asyncio
import threading
import time
import logging
import os
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from collections import defaultdict
import torch

from utils.logger import logger
from core.queue_manager import IntelligentQueueManager, Task, TaskStatus
from core.memory_manager import MemoryEstimationPool
from core.whisper_system import OptimizedWhisperSystem


class BatchTaskScheduler:
    """单文件任务调度器 - 已移除批次处理，改为按文件处理"""
    
    def __init__(self, queue_manager: IntelligentQueueManager, memory_pool: MemoryEstimationPool, whisper_system: OptimizedWhisperSystem = None):
        self.queue_manager = queue_manager
        self.memory_pool = memory_pool
        self.whisper_system = whisper_system
        
        # 调度器状态
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        
        # 单文件处理配置 - 移除批次相关配置
        from config import Config
        self.processing_timeout = Config.PROCESSING_TIMEOUT  # 单文件处理超时时间(秒)
        
        # GPU分配
        self.gpu_allocations: Dict[int, List[str]] = defaultdict(list)  # {gpu_id: [task_ids]}
        
        # 任务处理回调
        self.task_processor: Optional[Callable] = None
        
        # 线程同步
        self._lock = threading.RLock()
        self._scheduler_lock = threading.Lock()
        
        # 状态同步计数器
        self.sync_counter = 0
        
        # 处理线程管理
        self.processing_threads: Dict[int, threading.Thread] = {}  # {thread_id: thread}
        self._thread_lock = threading.Lock()
        
    def start_scheduler(self):
        """启动调度器"""
        with self._scheduler_lock:
            try:
                if self.running:
                    logger.warning("[SCHEDULER] 调度器已在运行中")
                    return
                    
                self.running = True
                self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
                self.scheduler_thread.start()
                logger.info("[SCHEDULER] 单文件任务调度器已启动")
            except Exception as e:
                logger.error(f"[SCHEDULER] 启动调度器失败: {e}", exc_info=True)
                raise
            
    def stop_scheduler(self):
        """停止调度器"""
        with self._scheduler_lock:
            try:
                if not self.running:
                    logger.warning("[SCHEDULER] 调度器未在运行")
                    return
                    
                self.running = False
                
                # 等待调度器线程结束
                if self.scheduler_thread:
                    self.scheduler_thread.join(timeout=5)
                
                # 等待所有处理线程结束
                logger.info("[SCHEDULER] 等待处理线程结束...")
                with self._thread_lock:
                    active_threads = list(self.processing_threads.values())
                
                for thread in active_threads:
                    if thread.is_alive():
                        thread.join(timeout=2)
                        if thread.is_alive():
                            logger.warning(f"[SCHEDULER] 处理线程 {thread.ident} 未能正常结束")
                
                # 清理线程记录
                with self._thread_lock:
                    self.processing_threads.clear()
                
                logger.info("[SCHEDULER] 单文件任务调度器已停止")
            except Exception as e:
                logger.error(f"[SCHEDULER] 停止调度器失败: {e}", exc_info=True)
            
    def set_task_processor(self, processor: Callable):
        """设置任务处理器"""
        self.task_processor = processor
        
    def set_whisper_system(self, whisper_system: OptimizedWhisperSystem):
        """设置Whisper系统实例"""
        self.whisper_system = whisper_system
        # 自动设置任务处理器
        if whisper_system:
            self.task_processor = whisper_system._process_single_task
        
    def _scheduler_loop(self):
        """调度器主循环"""
        logger.info("[SCHEDULER] 调度器主循环开始")
        
        while self.running:
            try:
                # 每10次循环同步一次GPU状态
                if self.sync_counter >= 10:
                    self.memory_pool.sync_gpu_status()
                    self.sync_counter = 0
                else:
                    self.sync_counter += 1
                
                # 获取所有可用的GPU状态
                gpu_status = self.memory_pool.get_gpu_status()
                logger.debug(f"[SCHEDULER] 获取GPU状态: {gpu_status}")
                
                # 为每个GPU调度任务
                for gpu_id, status in gpu_status.items():
                    if not self.running:
                        break
                        
                    # 检查该GPU是否有可用显存
                    if status['available_memory'] > 1.0:  # 保留1GB安全边际
                        logger.debug(f"[SCHEDULER] GPU{gpu_id}显存充足({status['available_memory']:.2f}GB)，开始调度任务")
                        self._schedule_tasks_for_gpu(gpu_id, status)
                    else:
                        # 显存不足时，确保队列中的任务保持待处理状态
                        logger.debug(f"[SCHEDULER] GPU{gpu_id}显存不足({status['available_memory']:.2f}GB)，确保任务保持待处理状态")
                        self._ensure_pending_tasks_status(gpu_id, status)
                
                # 检查是否达到最大并发任务数
                if self.queue_manager.current_tasks >= self.queue_manager.max_concurrent_tasks:
                    # 达到最大并发时，确保所有待处理任务保持待处理状态
                    logger.debug(f"[SCHEDULER] 达到最大并发任务数({self.queue_manager.max_concurrent_tasks})，确保任务保持待处理状态")
                    self._ensure_pending_tasks_status(-1, {'available_memory': 0})  # 使用-1表示全局检查
                        
                # 短暂休眠避免过度占用CPU，同时确保WebSocket心跳正常
                time.sleep(1.0)  # 增加休眠时间，减少CPU占用，给WebSocket更多响应时间
                
            except Exception as e:
                logger.error(f"[SCHEDULER] 调度循环出错: {e}", exc_info=True)
                time.sleep(1)  # 出错后等待更长时间
                
        logger.info("[SCHEDULER] 调度器主循环结束")
        
    def _schedule_tasks_for_gpu(self, gpu_id: int, gpu_status: Dict[str, float]):
        """为指定GPU调度任务 - 单文件处理，处理中的文件开始转录后才判断下个文件"""
        try:
            # 检查当前是否有处理中的任务已经开始转录
            current_processing_tasks = list(self.queue_manager.processing_tasks.values())
            transcription_started = False
            
            for task in current_processing_tasks:
                # 检查任务是否已经在GPU分配中（表示已经开始转录）
                task_in_gpu = any(task.id in gpu_tasks for gpu_tasks in self.gpu_allocations.values())
                if task_in_gpu:
                    transcription_started = True
                    logger.debug(f"[SCHEDULER] 发现任务 {task.id} 已开始转录")
                    break
            
            # 只有当没有任务在转录时，才考虑调度新任务
            if not transcription_started and current_processing_tasks:
                logger.debug(f"[SCHEDULER] GPU{gpu_id}有处理中任务但未开始转录，等待转录开始")
                return
            
            # 获取等待中的任务
            pending_tasks = self._get_pending_tasks()
            if not pending_tasks:
                logger.debug(f"[SCHEDULER] GPU{gpu_id}没有待处理任务")
                return
                
            logger.debug(f"[SCHEDULER] GPU{gpu_id}找到{len(pending_tasks)}个待处理任务")
            
            # 按优先级和状态排序任务（重试任务优先，然后按优先级排序）
            sorted_tasks = sorted(pending_tasks, key=lambda t: (
                t.status == TaskStatus.RETRYING,  # 重试任务优先
                t.priority.value  # 然后按优先级排序
            ), reverse=True)
                
            # 单文件处理：逐个处理任务
            for task in sorted_tasks:
                if not self.running:
                    break
                    
                logger.debug(f"[SCHEDULER] GPU{gpu_id}尝试调度任务 {task.id} (模型: {task.model})")
                
                # 检查是否可以分配显存
                task_dict = task.to_dict()
                estimated_memory = self.memory_pool.get_estimated_memory_usage(gpu_id, task.model)
                
                if self.memory_pool.allocate_task_memory(gpu_id, task_dict):
                    # 更新Task对象的分配信息
                    task.allocated_memory = task_dict.get('allocated_memory')
                    task.allocated_gpu = task_dict.get('allocated_gpu')
                    
                    logger.info(f"[SCHEDULER] 为GPU{gpu_id}调度任务 {task.id}，预估显存: {estimated_memory:.2f}GB")
                    self._execute_single_task(gpu_id, task)
                    break  # 一次只处理一个任务
                else:
                    # 显存不足，继续尝试下一个任务
                    logger.info(f"[SCHEDULER] GPU{gpu_id}显存不足，无法为任务 {task.id} 分配显存，尝试下一个任务")
                    continue  # 继续尝试下一个任务
                    
        except Exception as e:
            logger.error(f"[SCHEDULER] GPU{gpu_id}任务调度出错: {e}", exc_info=True)
    
    def _ensure_pending_tasks_status(self, gpu_id: int, gpu_status: Dict[str, float]):
        """确保显存不足或达到最大并发时队列中的任务保持待处理状态"""
        try:
            # 只检查真正的待处理任务，不包括处理中的任务
            queue_stats = self.queue_manager.get_queue_stats()
            for model_name in queue_stats.get('models', {}).keys():
                model_tasks = self.queue_manager.get_tasks_by_model(model_name)
                
                # 只检查待处理和重试状态的任务
                for task in model_tasks:
                    if task.status == TaskStatus.PENDING:
                        # 确保待处理任务保持待处理状态
                        if task.status != TaskStatus.PENDING:
                            logger.warning(f"[SCHEDULER] 重置任务 {task.id} 状态为待处理")
                            task.status = TaskStatus.PENDING
                            task.updated_at = datetime.now()
                            self.queue_manager._notify_status_change(task)
                    elif task.status == TaskStatus.FAILED:
                        # 失败的任务应该转到重试状态
                        logger.info(f"[SCHEDULER] 失败任务 {task.id} 转到重试状态")
                        task.status = TaskStatus.RETRYING
                        task.updated_at = datetime.now()
                        self.queue_manager._notify_status_change(task)
                    elif task.status not in [TaskStatus.RETRYING, TaskStatus.PROCESSING, TaskStatus.COMPLETED]:
                        # 其他未知状态，重置为待处理
                        logger.warning(f"[SCHEDULER] 重置未知状态任务 {task.id} ({task.status.value}) 为待处理")
                        task.status = TaskStatus.PENDING
                        task.updated_at = datetime.now()
                        self.queue_manager._notify_status_change(task)
                    
        except Exception as e:
            if gpu_id == -1:
                logger.error(f"[SCHEDULER] 确保待处理任务状态出错: {e}", exc_info=True)
            else:
                logger.error(f"[SCHEDULER] GPU{gpu_id}确保待处理任务状态出错: {e}", exc_info=True)
            
    def _get_pending_tasks(self) -> List[Task]:
        """获取所有等待中的任务（包括待处理和重试状态）"""
        try:
            pending_tasks = []
            
            # 获取队列统计信息
            queue_stats = self.queue_manager.get_queue_stats()
            
            # 遍历所有模型的队列
            for model_name in queue_stats.get('models', {}).keys():
                # 获取该模型的所有任务
                model_tasks = self.queue_manager.get_tasks_by_model(model_name)
                
                # 筛选出等待中的任务（包括待处理和重试状态）
                for task in model_tasks:
                    if task.status in [TaskStatus.PENDING, TaskStatus.RETRYING]:
                        pending_tasks.append(task)
            
            # 同时检查处理中的任务，看是否有需要启动转录的
            processing_tasks = list(self.queue_manager.processing_tasks.values())
            for task in processing_tasks:
                # 检查任务是否已经在GPU分配中（表示已经开始转录）
                task_in_gpu = any(task.id in gpu_tasks for gpu_tasks in self.gpu_allocations.values())
                if not task_in_gpu:
                    # 任务在处理中状态但没有在GPU分配中，需要启动转录
                    pending_tasks.append(task)
                    logger.info(f"[SCHEDULER] 发现处理中但未启动转录的任务 {task.id}")
            
            if pending_tasks:
                # 分别统计不同状态的任务数量
                actual_pending_count = len([t for t in pending_tasks if t.status == TaskStatus.PENDING])
                retry_count = len([t for t in pending_tasks if t.status == TaskStatus.RETRYING])
                processing_count = len([t for t in pending_tasks if t.status == TaskStatus.PROCESSING])
                logger.info(f"[SCHEDULER] 找到 {len(pending_tasks)} 个等待中的任务 (待处理: {actual_pending_count}, 重试: {retry_count}, 处理中: {processing_count})")
            return pending_tasks
        except Exception as e:
            logger.error(f"[SCHEDULER] 获取等待任务失败: {e}", exc_info=True)
            return []
        
    def _execute_single_task(self, gpu_id: int, task: Task):
        """执行单个任务 - 单文件处理"""
        try:
            logger.info(f"[SCHEDULER] 开始为GPU{gpu_id}执行任务 {task.id} (模型: {task.model})")
            
            # 将任务移动到处理中状态
            if not self.queue_manager.move_task_to_processing(task):
                logger.warning(f"[SCHEDULER] 无法将任务 {task.id} 移动到处理状态，释放已分配的显存")
                task_dict = task.to_dict()
                self.memory_pool.release_task_memory(task_dict)
                return
            
            logger.info(f"[SCHEDULER] 成功将任务 {task.id} 移动到处理状态，开始转录流程")
            
            # 记录GPU分配
            self.gpu_allocations[gpu_id].append(task.id)
            
            # 创建处理线程
            thread = threading.Thread(
                target=self._process_task_thread,
                args=(gpu_id, task),
                daemon=True
            )
            
            # 记录处理线程
            with self._thread_lock:
                self.processing_threads[task.id] = thread
            
            # 启动处理线程
            thread.start()
            logger.info(f"[SCHEDULER] 任务 {task.id} 处理线程已启动")
            
        except Exception as e:
            logger.error(f"[SCHEDULER] 执行任务 {task.id} 失败: {e}", exc_info=True)
            # 清理资源
            self._cleanup_task_resources(gpu_id, task)
        
    def _process_task_thread(self, gpu_id: int, task: Task):
        """任务处理线程 - 单文件处理"""
        try:
            logger.info(f"[SCHEDULER] 开始处理任务 {task.id} (GPU: {gpu_id})")
            
            # 调用任务处理器
            if self.task_processor:
                result = self.task_processor(task, gpu_id)
                logger.info(f"[SCHEDULER] 任务 {task.id} 处理完成")
                
                # 根据处理结果更新任务状态
                if result and result.get('success', False):
                    # 处理成功，标记为完成
                    self.queue_manager.complete_task(task.id, result)
                    logger.info(f"[SCHEDULER] 任务 {task.id} 已标记为完成")
                else:
                    # 处理失败，标记为失败
                    error_msg = result.get('error', '未知错误') if result else '处理失败'
                    self.queue_manager.fail_task(task.id, error_msg)
                    logger.info(f"[SCHEDULER] 任务 {task.id} 已标记为失败: {error_msg}")
            else:
                logger.error(f"[SCHEDULER] 任务处理器未设置，无法处理任务 {task.id}")
                self.queue_manager.fail_task(task.id, '任务处理器未设置')
            
        except Exception as e:
            logger.error(f"[SCHEDULER] 任务 {task.id} 处理过程中发生错误: {e}", exc_info=True)
            self.queue_manager.fail_task(task.id, str(e))
        finally:
            # 清理资源
            self._cleanup_task_resources(gpu_id, task)
    
    def _cleanup_task_resources(self, gpu_id: int, task: Task):
        """清理任务资源"""
        try:
            # 从GPU分配中移除
            if task.id in self.gpu_allocations[gpu_id]:
                self.gpu_allocations[gpu_id].remove(task.id)
            
            # 释放显存
            task_dict = task.to_dict()
            self.memory_pool.release_task_memory(task_dict)
            
            # 从处理线程记录中移除
            with self._thread_lock:
                if task.id in self.processing_threads:
                    del self.processing_threads[task.id]
            
            logger.info(f"[SCHEDULER] 任务 {task.id} 资源已清理")
            
        except Exception as e:
            logger.error(f"[SCHEDULER] 清理任务 {task.id} 资源失败: {e}", exc_info=True)
    
    def cleanup(self):
        """清理调度器资源"""
        try:
            logger.info("[SCHEDULER] 开始清理调度器资源...")
            
            # 停止调度器
            self.stop_scheduler()
            
            # 清理GPU分配记录
            with self._lock:
                self.gpu_allocations.clear()
            
            # 清理处理线程记录
            with self._thread_lock:
                self.processing_threads.clear()
            
            logger.info("[SCHEDULER] 调度器资源清理完成")
        except Exception as e:
            logger.error(f"[SCHEDULER] 清理调度器资源失败: {e}", exc_info=True)
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        with self._lock:
            with self._thread_lock:
                active_threads = len([t for t in self.processing_threads.values() if t.is_alive()])
                total_threads = len(self.processing_threads)
            
            return {
                'running': self.running,
                'processing_config': {
                    'timeout': self.processing_timeout
                },
                'gpu_allocations': dict(self.gpu_allocations),
                'thread_alive': self.scheduler_thread.is_alive() if self.scheduler_thread else False,
                'processing_threads': {
                    'active': active_threads,
                    'total': total_threads
                }
            }
            
    def __del__(self):
        """析构函数，确保调度器停止"""
        if hasattr(self, '_scheduler_lock'):
            self.stop_scheduler()
