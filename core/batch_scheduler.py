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
    """批量任务调度器"""
    
    def __init__(self, queue_manager: IntelligentQueueManager, memory_pool: MemoryEstimationPool, whisper_system: OptimizedWhisperSystem = None):
        self.queue_manager = queue_manager
        self.memory_pool = memory_pool
        self.whisper_system = whisper_system
        
        # 调度器状态
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        
        # 批量处理配置
        self.batch_timeout = float(int(os.getenv('BATCH_TIMEOUT', 5)))  # 批量超时时间(秒)
        self.max_batch_size = int(os.getenv('MAX_BATCH_SIZE', 3))       # 最大批量大小
        self.min_batch_size = int(os.getenv('MIN_BATCH_SIZE', 1))       # 最小批量大小
        
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
                logger.info("[SCHEDULER] 批量任务调度器已启动")
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
                
                logger.info("[SCHEDULER] 批量任务调度器已停止")
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
        """为指定GPU调度任务"""
        try:
            # 获取等待中的任务
            pending_tasks = self._get_pending_tasks()
            if not pending_tasks:
                logger.debug(f"[SCHEDULER] GPU{gpu_id}没有待处理任务")
                return
                
            logger.debug(f"[SCHEDULER] GPU{gpu_id}找到{len(pending_tasks)}个待处理任务")
                
            # 按模型分组任务
            tasks_by_model = defaultdict(list)
            for task in pending_tasks:
                tasks_by_model[task.model].append(task)
                
            # 为每个模型尝试批量调度
            for model_name, tasks in tasks_by_model.items():
                logger.debug(f"[SCHEDULER] GPU{gpu_id}尝试调度{model_name}模型的{len(tasks)}个任务")
                if not self.running:
                    break
                    
                # 尝试构建最优任务批次
                batch_tasks = self._build_optimal_batch(gpu_id, model_name, tasks)
                if batch_tasks:
                    logger.info(f"[SCHEDULER] 为GPU{gpu_id}模型{model_name}构建批次: {len(batch_tasks)}个任务")
                    self._execute_batch_tasks(gpu_id, model_name, batch_tasks)
                    
        except Exception as e:
            logger.error(f"[SCHEDULER] GPU{gpu_id}任务调度出错: {e}", exc_info=True)
    
    def _ensure_pending_tasks_status(self, gpu_id: int, gpu_status: Dict[str, float]):
        """确保显存不足或达到最大并发时队列中的任务保持待处理状态"""
        try:
            # 获取等待中的任务
            pending_tasks = self._get_pending_tasks()
            if not pending_tasks:
                return
            
            # 检查是否有任务状态不正确
            for task in pending_tasks:
                if task.status != TaskStatus.PENDING:
                    if gpu_id == -1:
                        # 全局检查（达到最大并发）
                        logger.info(f"[SCHEDULER] 达到最大并发任务数，重置任务 {task.id} 状态为待处理")
                    else:
                        # GPU特定检查（显存不足）
                        logger.info(f"[SCHEDULER] GPU{gpu_id}显存不足，重置任务 {task.id} 状态为待处理")
                    
                    # 只有非重试状态的任务才重置为待处理
                    # 重试状态的任务应该保持重试状态，等待资源释放后重新调度
                    if task.status != TaskStatus.RETRYING:
                        task.status = TaskStatus.PENDING
                        task.updated_at = datetime.now()
                        # 通知状态变更
                        self.queue_manager._notify_status_change(task)
                    else:
                        logger.info(f"[SCHEDULER] 任务 {task.id} 处于重试状态，保持重试状态等待资源释放")
                    
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
                pending_count = len([t for t in pending_tasks if t.status == TaskStatus.PENDING])
                retry_count = len([t for t in pending_tasks if t.status == TaskStatus.RETRYING])
                processing_count = len([t for t in pending_tasks if t.status == TaskStatus.PROCESSING])
                logger.info(f"[SCHEDULER] 找到 {len(pending_tasks)} 个等待中的任务 (待处理: {pending_count}, 重试: {retry_count}, 处理中: {processing_count})")
            return pending_tasks
        except Exception as e:
            logger.error(f"[SCHEDULER] 获取等待任务失败: {e}", exc_info=True)
            return []
        
    def _build_optimal_batch(self, gpu_id: int, model_name: str, available_tasks: List[Task]) -> List[Task]:
        """构建最优任务批次 - 多文件并行处理，每个文件对应一个模型"""
        try:
            if not available_tasks:
                return []
                
            # 按优先级和状态排序任务（重试任务优先，然后按优先级排序）
            sorted_tasks = sorted(available_tasks, key=lambda t: (
                t.status == TaskStatus.RETRYING,  # 重试任务优先
                t.priority.value  # 然后按优先级排序
            ), reverse=True)
            
            # 多文件并行处理：为每个任务分配独立模型
            batch_tasks = []
            total_estimated_memory = 0.0
            
            for task in sorted_tasks:
                # 验证任务只有一个文件
                if len(task.files) != 1:
                    logger.warning(f"[SCHEDULER] 任务 {task.id} 文件数量不为1，跳过: {len(task.files)}")
                    continue
                
                # 将Task对象转换为字典格式，以便memory_pool使用
                task_dict = task.to_dict()
                
                # 使用校准后的显存预估进行判断
                estimated_memory = self.memory_pool.get_estimated_memory_usage(gpu_id, task.model)
                logger.info(f"[SCHEDULER] 任务 {task.id} 预估显存: {estimated_memory:.2f}GB")
                
                # 检查是否可以分配显存（使用校准后的预估值）
                if self.memory_pool.allocate_task_memory(gpu_id, task_dict):
                    # 更新Task对象的分配信息
                    task.allocated_memory = task_dict.get('allocated_memory')
                    task.allocated_gpu = task_dict.get('allocated_gpu')
                    batch_tasks.append(task)
                    total_estimated_memory += estimated_memory
                    
                    logger.info(f"[SCHEDULER] 任务 {task.id} 已分配显存，使用独立模型处理")
                    
                    # 检查是否达到最大批次大小限制
                    if len(batch_tasks) >= self.max_batch_size:
                        logger.info(f"[SCHEDULER] 达到最大批次大小限制: {self.max_batch_size}")
                        break
                else:
                    # 显存不足，停止添加更多任务，但确保任务保持待处理状态
                    logger.info(f"[SCHEDULER] GPU{gpu_id}显存不足，无法为任务 {task.id} 分配显存，任务保持待处理状态")
                    # 确保任务状态为待处理
                    if task.status != TaskStatus.PENDING:
                        task.status = TaskStatus.PENDING
                        task.updated_at = datetime.now()
                        logger.info(f"[SCHEDULER] 任务 {task.id} 状态已重置为待处理")
                    # 显存不足时停止尝试调度后续任务
                    break
                    
            if batch_tasks:
                logger.info(f"[SCHEDULER] 为GPU{gpu_id}构建批次: {len(batch_tasks)}个任务，总预估显存: {total_estimated_memory:.2f}GB")
                    
            return batch_tasks
        except Exception as e:
            logger.error(f"[SCHEDULER] 构建任务批次失败: {e}", exc_info=True)
            return []
        
    def _execute_batch_tasks(self, gpu_id: int, model_name: str, batch_tasks: List[Task]):
        """执行批量任务 - 多文件并行处理，每个文件对应一个模型"""
        try:
            logger.info(f"[SCHEDULER] 开始为GPU{gpu_id}执行{model_name}模型的{len(batch_tasks)}个任务（多文件并行处理）")
            
            # 将任务移动到处理中状态
            successful_tasks = []
            failed_tasks = []
            for task in batch_tasks[:]:  # 使用副本避免在迭代时修改列表
                task_status_info = f"状态: {task.status.value}"
                if task.status == TaskStatus.RETRYING:
                    task_status_info += f" (重试第{task.retry_count}次)"
                logger.info(f"[SCHEDULER] 尝试将任务 {task.id} 移动到处理状态 - {task_status_info}")
                
                if not self.queue_manager.move_task_to_processing(task):
                    # 如果移动失败，释放显存并记录失败任务
                    logger.warning(f"[SCHEDULER] 无法将任务 {task.id} 移动到处理状态，释放已分配的显存")
                    task_dict = task.to_dict()
                    self.memory_pool.release_task_memory(task_dict)
                    failed_tasks.append(task)
                    batch_tasks.remove(task)
                    logger.warning(f"[SCHEDULER] 已从批次中移除任务 {task.id}")
                else:
                    logger.info(f"[SCHEDULER] 成功将任务 {task.id} 移动到处理状态，开始转录流程")
                    successful_tasks.append(task)
            
            # 处理移动失败的任务 - 不标记为失败，保持待处理状态
            for task in failed_tasks:
                        logger.info(f"[SCHEDULER] 任务 {task.id} 无法移动到处理状态，保持待处理状态等待资源释放")
                        file_path = task.files[0] if task.files else '未知文件'
                        filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                        
                        # 确保任务保持待处理状态，不标记为失败
                        if task.status != TaskStatus.PENDING:
                            task.status = TaskStatus.PENDING
                            task.updated_at = datetime.now()
                            logger.info(f"[SCHEDULER] 任务 {task.id} 状态已重置为待处理")
                        
                        # 任务已经在队列中，不需要重新加入
                        logger.info(f"[SCHEDULER] 任务 {task.id} 保持在队列中等待下次调度")
                    
            if not successful_tasks:
                logger.warning(f"[SCHEDULER] 没有任务成功移动到处理状态，批次执行中止")
                return
                
            # 记录GPU分配
            with self._lock:
                for task in successful_tasks:
                    self.gpu_allocations[gpu_id].append(task.id)
                    logger.info(f"[SCHEDULER] 记录GPU{gpu_id}分配任务 {task.id}")
                    
            logger.info(f"[SCHEDULER] GPU{gpu_id}开始处理{model_name}模型的{len(successful_tasks)}个任务: {[t.id for t in successful_tasks]}")
            
            # 使用whisper_system进行多文件并行处理
            logger.info(f"[SCHEDULER] 检查转录执行条件: whisper_system={self.whisper_system is not None}, task_processor={self.task_processor is not None}")
            
            if self.whisper_system and self.task_processor:
                logger.info(f"[SCHEDULER] 使用whisper_system进行多文件并行处理")
                # 在单独的线程中执行任务处理，避免阻塞调度器
                processing_thread = threading.Thread(
                    target=self._process_model_tasks,
                    args=(gpu_id, model_name, successful_tasks),
                    daemon=True
                )
                processing_thread.start()
                
                # 记录处理线程
                with self._thread_lock:
                    self.processing_threads[processing_thread.ident] = processing_thread
                
                logger.info(f"[SCHEDULER] 处理线程已启动，线程ID: {processing_thread.ident}")
            else:
                logger.error(f"[SCHEDULER] 未设置whisper_system或任务处理器 - whisper_system: {self.whisper_system is not None}, task_processor: {self.task_processor is not None}")
                # 释放显存并标记任务失败
                for task in successful_tasks:
                    try:
                        # 检查任务是否已经在处理中状态
                        if task.id in self.queue_manager.processing_tasks:
                            logger.warning(f"[SCHEDULER] 任务 {task.id} 已在处理中，跳过处理器未设置的处理")
                            continue
                        
                        task_dict = task.to_dict()
                        logger.warning(f"[SCHEDULER] 释放任务 {task.id} 的显存")
                        self.memory_pool.release_task_memory(task_dict)
                        logger.warning(f"[SCHEDULER] 标记任务 {task.id} 为失败")
                        file_path = task.files[0] if task.files else '未知文件'
                        filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                        detailed_error = f"文件 {filename} 处理器未设置"
                        
                        self.queue_manager.fail_task(task.id, detailed_error)
                    except Exception as e:
                        logger.error(f"[SCHEDULER] 处理任务 {task.id} 时出错: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"[SCHEDULER] 执行批次任务出错: {e}", exc_info=True)
            # 只对未成功移动到处理状态的任务进行清理，不标记为失败
            for task in batch_tasks:
                try:
                    # 检查任务是否已经在处理中状态
                    if task.id in self.queue_manager.processing_tasks:
                        logger.warning(f"[SCHEDULER] 任务 {task.id} 已在处理中，跳过异常处理")
                        continue
                    
                    task_dict = task.to_dict()
                    logger.info(f"[SCHEDULER] 异常处理: 释放任务 {task.id} 的显存")
                    self.memory_pool.release_task_memory(task_dict)
                    logger.info(f"[SCHEDULER] 异常处理: 任务 {task.id} 保持待处理状态等待资源释放")
                    
                    # 确保任务保持待处理状态，不标记为失败
                    if task.status != TaskStatus.PENDING:
                        task.status = TaskStatus.PENDING
                        task.updated_at = datetime.now()
                        logger.info(f"[SCHEDULER] 任务 {task.id} 状态已重置为待处理")
                    
                    # 任务已经在队列中，不需要重新加入
                    logger.info(f"[SCHEDULER] 任务 {task.id} 保持在队列中等待下次调度")
                        
                except Exception as inner_e:
                    logger.error(f"[SCHEDULER] 清理任务 {task.id} 时发生内部错误: {inner_e}", exc_info=True)
                                
    def _process_model_tasks(self, gpu_id: int, model_name: str, tasks: List[Task]):
        """处理模型任务组 - 多文件并行处理"""
        current_thread = threading.current_thread()
        try:
            logger.info(f"[PROCESSOR] 开始处理GPU{gpu_id}上的{model_name}模型任务组，任务数: {len(tasks)}")
            logger.info(f"[PROCESSOR] 线程ID: {current_thread.ident}, 线程名: {current_thread.name}")
            
            # 使用whisper_system进行多文件并行处理
            logger.info(f"[PROCESSOR] 检查处理器状态: whisper_system={self.whisper_system is not None}, task_processor={self.task_processor is not None}")
            
            if self.whisper_system and self.task_processor:
                logger.info(f"[PROCESSOR] 使用whisper_system进行多文件并行处理")
                # 传递GPU ID和任务列表给处理器
                results = self.task_processor(gpu_id, tasks)
                
                logger.info(f"[PROCESSOR] 处理器返回结果: {len(results) if results else 0}个结果")
                
                # 处理结果
                self._handle_task_results(tasks, results)
            else:
                # 处理器未设置，标记所有任务失败
                logger.error(f"[PROCESSOR] whisper_system或任务处理器未设置 - whisper_system: {self.whisper_system is not None}, task_processor: {self.task_processor is not None}")
                for task in tasks:
                    file_path = task.files[0] if task.files else '未知文件'
                    filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                    detailed_error = f"文件 {filename} 处理器未设置"
                    
                    self.queue_manager.fail_task(task.id, detailed_error)
                    
        except Exception as e:
            logger.error(f"[PROCESSOR] 处理模型任务组出错: {e}", exc_info=True)
            # 标记所有任务失败
            for task in tasks:
                file_path = task.files[0] if task.files else '未知文件'
                filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                detailed_error = f"文件 {filename} 任务处理错误: {str(e)}"
                
                self.queue_manager.fail_task(task.id, detailed_error)
            
        finally:
            # 确保释放GPU分配记录和显存
            try:
                self._cleanup_task_allocations(gpu_id, tasks)
            except Exception as e:
                logger.error(f"[PROCESSOR] 清理任务分配时出错: {e}", exc_info=True)
            
            # 清理线程记录
            try:
                with self._thread_lock:
                    if current_thread.ident in self.processing_threads:
                        del self.processing_threads[current_thread.ident]
                        logger.debug(f"[PROCESSOR] 清理处理线程记录: {current_thread.ident}")
            except Exception as e:
                logger.error(f"[PROCESSOR] 清理线程记录时出错: {e}", exc_info=True)
                
    def _handle_task_results(self, tasks: List[Task], results: List[Any]):
        """处理任务结果"""
        try:
            logger.info(f"[PROCESSOR] 开始处理 {len(tasks)} 个任务的结果")
            
            for i, task in enumerate(tasks):
                try:
                    if i < len(results):
                        result = results[i]
                        if isinstance(result, dict) and result.get('error'):
                            # 任务处理出错
                            error_msg = result['error']
                            file_path = result.get('file_path', '未知文件')
                            filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                            
                            # 构建详细的错误信息
                            detailed_error = f"文件 {filename} 处理失败: {error_msg}"
                            
                            logger.warning(f"[PROCESSOR] 任务 {task.id} 处理出错: {detailed_error}")
                            self.queue_manager.fail_task(task.id, detailed_error)
                        else:
                            # 任务处理成功
                            logger.info(f"[PROCESSOR] 任务 {task.id} 处理成功，标记为完成")
                            self.queue_manager.complete_task(task.id, result)
                    else:
                        # 没有对应结果，标记为失败
                        file_path = task.files[0] if task.files else '未知文件'
                        filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                        detailed_error = f"文件 {filename} 处理无结果返回"
                        
                        logger.warning(f"[PROCESSOR] 任务 {task.id} 无结果返回，标记为失败")
                        self.queue_manager.fail_task(task.id, detailed_error)
                        
                except Exception as e:
                    logger.error(f"[PROCESSOR] 处理任务{task.id}结果出错: {e}", exc_info=True)
                    try:
                        file_path = task.files[0] if task.files else '未知文件'
                        filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                        detailed_error = f"文件 {filename} 结果处理错误: {str(e)}"
                        
                        self.queue_manager.fail_task(task.id, detailed_error)
                    except Exception as inner_e:
                        logger.error(f"[PROCESSOR] 标记任务{task.id}失败时出错: {inner_e}", exc_info=True)
            
            logger.info(f"[PROCESSOR] 任务结果处理完成")
        except Exception as e:
            logger.error(f"[PROCESSOR] 处理任务结果时出错: {e}", exc_info=True)
                
    def _cleanup_task_allocations(self, gpu_id: int, tasks: List[Task]):
        """清理任务分配记录"""
        try:
            with self._lock:
                # 从GPU分配记录中移除任务
                task_ids = [task.id for task in tasks]
                self.gpu_allocations[gpu_id] = [
                    tid for tid in self.gpu_allocations[gpu_id] 
                    if tid not in task_ids
                ]
                
            # 释放任务显存
            for task in tasks:
                task_dict = task.to_dict()
                self.memory_pool.release_task_memory(task_dict)
        except Exception as e:
            logger.error(f"[SCHEDULER] 清理任务分配时出错: {e}", exc_info=True)
    
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
                'batch_config': {
                    'timeout': self.batch_timeout,
                    'max_size': self.max_batch_size,
                    'min_size': self.min_batch_size
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
