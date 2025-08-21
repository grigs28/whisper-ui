import asyncio
import threading
import time
import logging
import os
import json
import opencc
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import torch

from utils.logger import logger
from core.queue_manager import IntelligentQueueManager, Task, TaskStatus, TaskPriority
from core.memory_manager import MemoryEstimationPool
from core.batch_scheduler import BatchTaskScheduler
from core.gpu_manager import EnhancedGPUManager, GPUMemoryPool
from core.transcription_saver import transcription_saver
from config import config


class OptimizedWhisperSystem:
    """优化版Whisper系统"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, socketio=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self, socketio=None):
        # 防止重复初始化
        if hasattr(self, 'initialized'):
            # 如果传入了新的socketio实例，更新它
            if socketio is not None:
                self.socketio = socketio
            return
            
        try:
            # 设置SocketIO实例
            self.socketio = socketio
            
            # 初始化核心组件
            self.gpu_manager = EnhancedGPUManager()
            self.memory_pool = MemoryEstimationPool(self.gpu_manager)  # 传入gpu_manager实例
            self.queue_manager = IntelligentQueueManager()
            self.batch_scheduler = BatchTaskScheduler(self.queue_manager, self.memory_pool)
            
            # 初始化GPU显存池
            self._initialize_gpu_pools()
            
            # 设置任务处理器
            self.batch_scheduler.set_task_processor(self._process_single_task)
            
            # 任务进度回调
            self.progress_callbacks: List[Callable] = []
            self.queue_manager.add_status_callback(self._on_task_status_change)
            
            # 系统状态
            self.initialized = True
            self.running = False
        except Exception as e:
            logger.error(f"初始化优化Whisper系统失败: {e}", exc_info=True)
            raise
        
    def _initialize_gpu_pools(self):
        """初始化GPU显存池"""
        try:
            gpu_info_result = self.gpu_manager.get_gpu_info()
            # 检查GPU信息获取是否成功
            if not gpu_info_result.get('success', False):
                logger.error("[SYSTEM] 获取GPU信息失败")
                return
                
            gpu_info_list = gpu_info_result.get('gpus', [])
            for gpu in gpu_info_list:
                gpu_id = gpu['id']
                self.memory_pool.initialize_gpu_pool(gpu_id)
            logger.info(f"[SYSTEM] 初始化了 {len(gpu_info_list)} 个GPU显存池")
        except Exception as e:
            logger.error(f"[SYSTEM] 初始化GPU显存池失败: {e}", exc_info=True)
            
    def start_system(self):
        """启动系统"""
        if self.running:
            logger.warning("[SYSTEM] 系统已在运行中")
            return
            
        try:
            self.batch_scheduler.start_scheduler()
            self.running = True
            logger.info("[SYSTEM] Whisper系统已启动")
        except Exception as e:
            logger.error(f"[SYSTEM] 启动系统失败: {e}", exc_info=True)
            raise
            
    def stop_system(self):
        """停止系统"""
        if not self.running:
            logger.warning("[SYSTEM] 系统未在运行")
            return
            
        try:
            self.batch_scheduler.stop_scheduler()
            self.running = False
            logger.info("[SYSTEM] Whisper系统已停止")
        except Exception as e:
            logger.error(f"[SYSTEM] 停止系统失败: {e}", exc_info=True)
            
    def shutdown(self):
        """优雅关闭系统"""
        logger.info("[SYSTEM] 开始优雅关闭系统...")
        try:
            # 停止系统
            if self.running:
                self.stop_system()
            
            # 清理队列管理器资源
            if hasattr(self, 'queue_manager'):
                try:
                    # 确保所有锁都被释放
                    if hasattr(self.queue_manager, '_lock'):
                        # 尝试获取锁以确保没有死锁
                        with self.queue_manager._lock:
                            logger.info("[SYSTEM] 队列管理器锁已释放")
                except Exception as e:
                    logger.error(f"[SYSTEM] 释放队列管理器锁失败: {e}", exc_info=True)
            
            # 清理GPU资源
            if hasattr(self, 'memory_pool'):
                try:
                    self.memory_pool.cleanup()
                    logger.info("[SYSTEM] GPU显存池已清理")
                except Exception as e:
                    logger.error(f"[SYSTEM] 清理GPU显存池失败: {e}", exc_info=True)
            
            # 清理GPU管理器
            if hasattr(self, 'gpu_manager'):
                try:
                    self.gpu_manager.cleanup()
                    logger.info("[SYSTEM] GPU管理器已清理")
                except Exception as e:
                    logger.error(f"[SYSTEM] 清理GPU管理器失败: {e}", exc_info=True)
            
            # 清理调度器
            if hasattr(self, 'batch_scheduler'):
                try:
                    self.batch_scheduler.cleanup()
                    logger.info("[SYSTEM] 批量调度器已清理")
                except Exception as e:
                    logger.error(f"[SYSTEM] 清理批量调度器失败: {e}", exc_info=True)
            
            # 清理回调函数
            if hasattr(self, 'progress_callbacks'):
                self.progress_callbacks.clear()
                logger.info("[SYSTEM] 进度回调已清理")
            
            # 重置单例实例
            OptimizedWhisperSystem._instance = None
            logger.info("[SYSTEM] 系统优雅关闭完成")
            
        except Exception as e:
            logger.error(f"[SYSTEM] 系统关闭过程中发生错误: {e}", exc_info=True)
            raise
            
    def submit_task(self, task_data: Dict[str, Any]) -> str:
        """提交转录任务"""
        try:
            # 创建任务对象
            task = Task(
                id=task_data.get('task_id') or f"task_{int(time.time() * 1000)}",
                user_id=task_data.get('user_id', 'unknown'),
                files=task_data.get('files', []),
                model=task_data.get('model', 'medium'),
                task_type=task_data.get('task_type', 'transcription'),
                priority=TaskPriority(task_data.get('priority', 2)),  # 默认NORMAL
                status=TaskStatus.PENDING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                max_retries=task_data.get('max_retries', 3)
            )
            
            # 添加到队列
            if self.queue_manager.add_task(task):
                logger.info(f"[SYSTEM] 任务 {task.id} 已提交到队列")
                return task.id
            else:
                raise Exception("添加任务到队列失败")
                
        except Exception as e:
            logger.error(f"[SYSTEM] 提交任务失败: {e}", exc_info=True)
            raise
            
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        try:
            task = self.queue_manager.get_task(task_id)
            return task.to_dict() if task else None
        except Exception as e:
            logger.error(f"[SYSTEM] 获取任务 {task_id} 状态失败: {e}", exc_info=True)
            return None
        
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            return self.queue_manager.remove_task(task_id)
        except Exception as e:
            logger.error(f"[SYSTEM] 取消任务 {task_id} 失败: {e}", exc_info=True)
            return False
        
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            # 获取GPU选择器列表和最佳GPU ID
            gpu_list = self.gpu_manager.get_gpu_list_for_selector()
            best_gpu = self.gpu_manager.get_best_available_gpu()
            
            return {
                'running': self.running,
                'gpu_status': self.memory_pool.get_gpu_status(),
                'queue_stats': self.queue_manager.get_queue_stats(),
                'scheduler_status': self.batch_scheduler.get_scheduler_status(),
                'gpu_selector': gpu_list,
                'best_gpu_id': best_gpu
            }
        except Exception as e:
            logger.error(f"[SYSTEM] 获取系统状态失败: {e}", exc_info=True)
            return {}
        
    def add_progress_callback(self, callback: Callable):
        """添加进度回调"""
        try:
            self.progress_callbacks.append(callback)
        except Exception as e:
            logger.error(f"[SYSTEM] 添加进度回调失败: {e}", exc_info=True)
        
    def _on_task_status_change(self, task_info: Dict[str, Any]):
        """任务状态变更回调"""
        try:
            # 通知前端任务状态变更
            if self.socketio:
                try:
                    # 使用非阻塞方式发送消息
                    self.socketio.emit('task_update', task_info, namespace='/')
                    logger.debug(f"[SYSTEM] 发送任务状态更新: {task_info.get('id')} -> {task_info.get('status')}")
                except Exception as socket_error:
                    logger.warning(f"[SYSTEM] SocketIO发送消息失败: {socket_error}")
            else:
                logger.debug(f"[SYSTEM] SocketIO未设置，跳过任务状态更新")
        except Exception as e:
            logger.error(f"[SYSTEM] 通知任务状态变更失败: {e}", exc_info=True)
        
    def _process_single_task(self, gpu_id: int, tasks: List[Task]) -> List[Dict[str, Any]]:
        """处理单个任务（实际的转录处理）"""
        try:
            results = []
            
            # 设置设备
            device = f"cuda:{gpu_id}" if gpu_id >= 0 else "cpu"
            
            # 加载模型（可以缓存以提高效率）
            model_name = tasks[0].model if tasks else "medium"
            task_id = tasks[0].id if tasks else None
            model = self._load_model(model_name, device, task_id)
            
            for task in tasks:
                try:
                    logger.info(f"[PROCESSOR] 开始处理任务 {task.id} on {device}")
                    
                    # 更新任务状态为处理中
                    self.queue_manager.update_task_progress(task.id, 10)
                    
                    # 处理每个文件
                    transcriptions = []
                    for file_path in task.files:
                        # 读取音频文件
                        audio = self._load_audio(file_path)
                        
                        # 转录
                        result = model.transcribe(audio)
                        transcriptions.append(result)
                        
                        # 更新进度
                        progress = 10 + (80 * (task.files.index(file_path) + 1) / len(task.files))
                        self.queue_manager.update_task_progress(task.id, progress)
                    
                    # 组装结果
                    result = {
                        'text': "\n".join([t.get('text', '') for t in transcriptions]),
                        'segments': [seg for t in transcriptions for seg in t.get('segments', [])],
                        'language': transcriptions[0].get('language', 'unknown') if transcriptions else 'unknown',
                        'task_id': task.id
                    }
                    
                    # 保存转录结果到outputs目录
                    try:
                        saved_files = transcription_saver.save_transcription_result(task.__dict__, result)
                        if saved_files:
                            logger.info(f"[PROCESSOR] 任务 {task.id} 转录结果已保存到: {saved_files}")
                            # 将保存的文件路径添加到结果中
                            result['saved_files'] = saved_files
                        else:
                            logger.warning(f"[PROCESSOR] 任务 {task.id} 转录结果保存失败")
                    except Exception as save_error:
                        logger.error(f"[PROCESSOR] 保存转录结果失败 {task.id}: {save_error}")
                    
                    # 将成功结果添加到results列表
                    results.append(result)
                    logger.info(f"[PROCESSOR] 任务 {task.id} 处理完成")
                    
                except Exception as e:
                    logger.error(f"[PROCESSOR] 处理任务 {task.id} 失败: {e}", exc_info=True)
                    results.append({'error': str(e), 'task_id': task.id})
            
            # 释放模型显存
            del model
            if device.startswith('cuda'):
                torch.cuda.empty_cache()
            
            return results
        except Exception as e:
            logger.error(f"[PROCESSOR] 处理任务组失败: {e}", exc_info=True)
            # 确保在异常时也释放模型
            if 'model' in locals():
                del model
                if device.startswith('cuda'):
                    torch.cuda.empty_cache()
            # 返回包含错误的默认结果
            return [{'error': str(e), 'task_id': 'unknown'} for _ in tasks]

    def _load_model(self, model_name: str, device: str, task_id: str = None):
        """加载Whisper模型"""
        try:
            # 检查模型是否需要下载
            import whisper
            from pathlib import Path
            
            # 获取模型路径
            model_path = config.get_model_path(model_name)
            model_file = os.path.join(model_path, f"{model_name}.pt")
            
            # 如果模型文件不存在，需要下载
            if not os.path.exists(model_file):
                logger.info(f"[PROCESSOR] 模型 {model_name} 不存在，开始下载...")
                
                # 发送下载开始事件
                if hasattr(self, 'socketio') and self.socketio and task_id:
                    self.socketio.emit('download_progress', {
                        'task_id': task_id,
                        'model_name': model_name,
                        'progress': 0,
                        'message': f'开始下载模型 {model_name}...'
                    })
                
                # 创建模型目录
                os.makedirs(model_path, exist_ok=True)
                
                # 模拟下载进度（实际下载由whisper库处理）
                for progress in [10, 30, 50, 70, 90]:
                    if hasattr(self, 'socketio') and self.socketio and task_id:
                        self.socketio.emit('download_progress', {
                            'task_id': task_id,
                            'model_name': model_name,
                            'progress': progress,
                            'message': f'正在下载模型 {model_name}... ({progress}%)'
                        })
                    time.sleep(0.5)  # 模拟下载时间
            
            # 加载模型
            model = whisper.load_model(model_name, device=device, download_root=config.MODEL_BASE_PATH)
            
            # 发送下载完成事件
            if hasattr(self, 'socketio') and self.socketio and task_id:
                self.socketio.emit('download_progress', {
                    'task_id': task_id,
                    'model_name': model_name,
                    'progress': 100,
                    'message': f'模型 {model_name} 下载完成'
                })
            
            logger.info(f"[PROCESSOR] 成功加载模型 {model_name} 到 {device}")
            return model
        except Exception as e:
            logger.error(f"[PROCESSOR] 加载模型 {model_name} 到 {device} 失败: {e}", exc_info=True)
            raise
    


    def _load_audio(self, file_path: str):
        """加载音频文件"""
        try:
            # 如果文件路径不是绝对路径，则添加uploads目录前缀
            if not os.path.isabs(file_path):
                full_path = os.path.join(config.UPLOAD_FOLDER, file_path)
            else:
                full_path = file_path
            
            # 检查文件是否存在
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"音频文件不存在: {full_path}")
            
            # 实现音频加载逻辑
            import whisper
            audio = whisper.load_audio(full_path)
            logger.info(f"[PROCESSOR] 成功加载音频文件: {full_path}")
            return audio
        except Exception as e:
            logger.error(f"[PROCESSOR] 加载音频文件 {file_path} 失败: {e}", exc_info=True)
            raise
        
    def calibrate_model_memory(self, gpu_id: int, model_name: str, actual_usage: float):
        """校准模型显存使用量"""
        try:
            self.memory_pool.calibrate_model_memory(gpu_id, model_name, actual_usage)
        except Exception as e:
            logger.error(f"[SYSTEM] 校准模型 {model_name} 在GPU {gpu_id} 的显存使用量失败: {e}", exc_info=True)
        
    def __enter__(self):
        """上下文管理器入口"""
        try:
            self.start_system()
            return self
        except Exception as e:
            logger.error(f"[SYSTEM] 进入上下文管理器失败: {e}", exc_info=True)
            raise
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        try:
            self.stop_system()
        except Exception as e:
            logger.error(f"[SYSTEM] 退出上下文管理器失败: {e}", exc_info=True)
        

def get_optimized_system(socketio=None) -> OptimizedWhisperSystem:
    """获取优化Whisper系统单例"""
    return OptimizedWhisperSystem(socketio)