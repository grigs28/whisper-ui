import asyncio
import threading
import time
import logging
import os
import json
import opencc
import numpy as np
import multiprocessing as mp
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime

# 关键：在任何torch导入之前设置spawn模式
mp.set_start_method("spawn", force=True)

# 延迟导入torch和whisper，避免父进程CUDA初始化
torch = None
whisper = None

from utils.logger import logger
from core.queue_manager import IntelligentQueueManager, Task, TaskStatus, TaskPriority
from core.memory_manager import MemoryEstimationPool
from core.batch_scheduler import BatchTaskScheduler
from core.gpu_manager import EnhancedGPUManager, GPUMemoryPool
from core.transcription_saver import transcription_saver
from core.whisper_system import OptimizedWhisperSystem as WhisperSystem
from config import config


# ==================== SPAWN进程工作函数 ====================
def _transcribe_file_worker(args: tuple) -> Dict[str, Any]:
    """
    顶层工作函数，在spawn进程中执行转录
    关键：这里才第一次import torch/whisper，避免父进程CUDA初始化
    """
    gpu_id, model_name, file_path, task_id, upload_folder = args
    
    try:
        # 设置CUDA可见设备
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
        
        # 关键：在子进程中才第一次import torch/whisper
        import torch
        import whisper
        
        # 设置CUDA设备（对子进程就是0）
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        
        logger.info(f"[WORKER] 子进程开始处理任务 {task_id}，模型: {model_name}，文件: {file_path}")
        
        # 构建完整文件路径
        if not os.path.isabs(file_path):
            full_file_path = os.path.join(upload_folder, file_path)
        else:
            full_file_path = file_path
            
        # 检查文件是否存在
        if not os.path.exists(full_file_path):
            raise FileNotFoundError(f"文件不存在: {full_file_path}")
        
        # 加载模型
        model = whisper.load_model(model_name, device="cuda:0")
        logger.info(f"[WORKER] 模型 {model_name} 加载成功")
        
        # 转录
        result = model.transcribe(full_file_path)
        
        # 清理模型
        del model
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        
        logger.info(f"[WORKER] 任务 {task_id} 转录完成")
        
        return {
            'task_id': task_id,
            'success': True,
            'result': result,
            'file_path': full_file_path
        }
        
    except Exception as e:
        logger.error(f"[WORKER] 任务 {task_id} 处理失败: {e}", exc_info=True)
        return {
            'task_id': task_id,
            'success': False,
            'error': str(e),
            'file_path': file_path
        }


def _worker_init(gpu_id: int):
    """工作进程初始化函数"""
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    logger.info(f"[WORKER] 工作进程初始化，GPU: {gpu_id}")


# 添加模型下载进度监控类
class ModelDownloadProgress:
    """模型下载进度监控器"""
    
    def __init__(self, socketio=None):
        self.socketio = socketio
        # 使用正确的Whisper模型下载URL（这些URL需要从whisper库中获取）
        # 由于URL可能会变化，我们使用动态获取的方式
        self.download_urls = {}
    
    def download_model_with_progress(self, model_name: str, task_id: str = None, download_root: str = None):
        """带进度监控的模型下载 - 使用改进的进度显示"""
        import os
        
        if download_root is None:
            download_root = config.MODEL_BASE_PATH
            
        # 确保下载目录存在
        os.makedirs(download_root, exist_ok=True)
        
        # 发送下载开始事件
        if self.socketio and task_id:
            self.socketio.emit('download_progress', {
                'task_id': task_id,
                'model_name': model_name,
                'progress': 0,
                'message': f'开始下载模型 {model_name}...'
            })
        
        try:
            # 使用改进的进度显示方法
            # 由于whisper.load_model()内部下载过程无法直接监控，
            # 我们使用基于时间的进度估算，但比原来的虚假进度更准确
            
            import whisper
            import threading
            import time
            
            # 创建进度更新线程
            progress_thread = None
            stop_progress = threading.Event()
            
            def progress_updater():
                """进度更新线程 - 使用更平滑和智能的进度显示"""
                progress = 0
                update_interval = 0.3  # 每0.3秒更新一次，更频繁
                
                # 根据模型大小调整进度增量
                model_sizes = {
                    'tiny': 3,      # 39MB
                    'base': 2.5,    # 74MB
                    'small': 2,     # 244MB
                    'medium': 1.5,  # 769MB
                    'large': 1      # 1550MB
                }
                
                # 获取模型对应的增量，默认为1.5
                increment = model_sizes.get(model_name, 1.5)
                
                # 使用非线性进度，开始时快，结束时慢
                while not stop_progress.is_set() and progress < 95:
                    time.sleep(update_interval)
                    
                    # 非线性进度：开始时增长快，接近95%时增长慢
                    if progress < 30:
                        # 前30%增长较快
                        current_increment = increment * 1.5
                    elif progress < 70:
                        # 30%-70%正常增长
                        current_increment = increment
                    else:
                        # 70%-95%增长较慢
                        current_increment = increment * 0.7
                    
                    progress += current_increment
                    if progress > 95:
                        progress = 95
                    
                    if self.socketio and task_id:
                        self.socketio.emit('download_progress', {
                            'task_id': task_id,
                            'model_name': model_name,
                            'progress': int(progress),  # 确保是整数
                            'message': f'正在下载模型 {model_name}... ({int(progress)}%)'
                        })
            
            # 启动进度更新线程
            progress_thread = threading.Thread(target=progress_updater, daemon=True)
            progress_thread.start()
            
            try:
                # 实际下载模型（这会触发whisper的下载）
                model = whisper.load_model(model_name, download_root=download_root)
                
                # 停止进度更新
                stop_progress.set()
                if progress_thread:
                    progress_thread.join(timeout=1)
                
                # 发送下载完成事件
                if self.socketio and task_id:
                    self.socketio.emit('download_progress', {
                        'task_id': task_id,
                        'model_name': model_name,
                        'progress': 100,
                        'message': f'模型 {model_name} 下载完成'
                    })
                
                logger.info(f"[DOWNLOAD] 模型 {model_name} 下载完成")
                return model
                
            except Exception as e:
                # 停止进度更新
                stop_progress.set()
                if progress_thread:
                    progress_thread.join(timeout=1)
                raise
                
        except Exception as e:
            logger.error(f"[DOWNLOAD] 模型 {model_name} 下载失败: {e}")
            # 发送下载失败事件
            if self.socketio and task_id:
                self.socketio.emit('download_progress', {
                    'task_id': task_id,
                    'model_name': model_name,
                    'progress': -1,
                    'message': f'模型 {model_name} 下载失败: {str(e)}'
                })
            raise
    


# 创建全局下载进度监控器实例
model_downloader = ModelDownloadProgress()


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
            
            # 初始化whisper_system
            self.whisper_system = WhisperSystem(socketio)
            
            # 初始化批量调度器，传入whisper_system
            self.batch_scheduler = BatchTaskScheduler(self.queue_manager, self.memory_pool, self.whisper_system)
            
            # 初始化GPU显存池
            self._initialize_gpu_pools()
            
            # 设置whisper_system作为任务处理器
            self.batch_scheduler.set_whisper_system(self.whisper_system)
            
            # 启动批量调度器
            self.batch_scheduler.start_scheduler()
            
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
        """提交转录任务 - 一个文件对应一个模型，支持多文件并行处理"""
        try:
            # 验证任务数据
            files = task_data.get('files', [])
            if len(files) != 1:
                raise ValueError(f"每个任务只能包含一个文件，当前包含 {len(files)} 个文件")
            
            # 创建任务对象
            task = Task(
                id=task_data.get('task_id') or f"task_{int(time.time() * 1000)}",
                user_id=task_data.get('user_id', 'unknown'),
                files=files,  # 确保只有一个文件
                model=task_data.get('model', 'medium'),
                task_type=task_data.get('task_type', 'transcription'),
                priority=TaskPriority(task_data.get('priority', 2)),  # 默认NORMAL
                status=TaskStatus.PENDING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                max_retries=task_data.get('max_retries', 3),
                output_formats=task_data.get('output_formats', ['txt'])  # 添加输出格式
            )
            
            # 添加到待处理队列
            if self.queue_manager.add_task(task):
                logger.info(f"[SYSTEM] 任务 {task.id} 已添加到待处理队列，文件: {files[0]}")
            else:
                raise Exception("添加任务到队列失败")
            
            return task.id
                
        except Exception as e:
            logger.error(f"[SYSTEM] 提交任务失败: {e}", exc_info=True)
            raise
    
    # 任务处理相关函数已删除，现在使用批量调度器处理
    
    def _process_single_file(self, task: Task, gpu_id: int) -> Dict[str, Any]:
        """处理单个文件 - 一个文件对应一个模型"""
        try:
            device = f"cuda:{gpu_id}" if gpu_id >= 0 else "cpu"
            file_path = task.files[0]  # 只有一个文件
            
            # 处理文件路径，确保是完整路径
            if not os.path.isabs(file_path):
                full_file_path = os.path.join(config.UPLOAD_FOLDER, file_path)
            else:
                full_file_path = file_path
            
            # 检查文件是否存在
            if not os.path.exists(full_file_path):
                raise FileNotFoundError(f"音频文件不存在: {full_file_path}")
            
            logger.info(f"[PROCESSOR] 开始处理文件 {full_file_path}，使用设备 {device}")
            
            # 加载模型
            model = self._load_model(task.model, device, task.id)
            
            # 记录模型加载后的显存使用情况
            if device.startswith('cuda'):
                try:
                    torch.cuda.synchronize()
                    actual_memory_usage = torch.cuda.memory_allocated(gpu_id) / (1024**3)  # 转换为GB
                    estimated_memory = self.memory_pool.get_estimated_memory_usage(gpu_id, task.model)
                    logger.info(f"[PROCESSOR] 记录模型显存使用: {task.model} 预估{estimated_memory:.2f}GB 实际{actual_memory_usage:.2f}GB")
                    
                    # 动态校准模型显存使用量
                    self.calibrate_model_memory(gpu_id, task.model, actual_memory_usage)
                except Exception as e:
                    logger.warning(f"[PROCESSOR] 记录模型显存使用失败: {e}")
            
            try:
                # 更新进度到20% - 开始转录
                self.queue_manager.update_task_progress(task.id, 20, "正在转录...")
                
                # 启动转录进度监控线程
                import threading
                import time
                stop_progress = threading.Event()
                
                def transcription_progress_monitor():
                    """转录进度监控线程"""
                    current_progress = 20
                    while not stop_progress.is_set() and current_progress < 90:
                        time.sleep(2)  # 每2秒更新一次
                        if not stop_progress.is_set():
                            current_progress += 5  # 每次增加5%
                            if current_progress > 90:
                                current_progress = 90
                            
                            self.queue_manager.update_task_progress(
                                task.id,
                                current_progress,
                                f"正在转录文件: {os.path.basename(full_file_path)} ({int(current_progress)}%)"
                            )
                
                # 启动进度监控线程
                progress_thread = threading.Thread(target=transcription_progress_monitor, daemon=True)
                progress_thread.start()
                
                try:
                    # 执行转录
                    result = model.transcribe(full_file_path)
                finally:
                    # 停止进度监控
                    stop_progress.set()
                    progress_thread.join(timeout=1)
                
                # 更新进度到90% - 开始保存结果
                self.queue_manager.update_task_progress(task.id, 90, "正在保存转录结果...")
                
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
                
                # 更新进度到100% - 任务完成
                self.queue_manager.update_task_progress(task.id, 100, "任务处理完成！")
                
                return {
                    'success': True,
                    'task_id': task.id,
                    'file_path': full_file_path,
                    'result': result
                }
                
            finally:
                # 释放模型
                del model
                if device.startswith('cuda'):
                    self._safe_cuda_cleanup(gpu_id)
                
        except Exception as e:
            logger.error(f"[PROCESSOR] 处理文件失败: {e}", exc_info=True)
            raise
    
    # 资源清理和结果保存功能已移至批量调度器处理
            
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
    
    # 任务调度器已删除，现在使用批量调度器
    
    def _safe_cuda_cleanup(self, gpu_id: int):
        """安全的CUDA清理，不影响其他正在运行的任务"""
        try:
            # 只清理当前GPU的缓存，不改变全局设备设置
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            
            # 强制垃圾回收
            import gc
            gc.collect()
            
            # 再次清理缓存
            torch.cuda.empty_cache()
            
            logger.info(f"[PROCESSOR] GPU {gpu_id} 缓存已安全清理")
            
        except Exception as e:
            logger.warning(f"[PROCESSOR] GPU {gpu_id} 缓存清理出现警告: {e}")
            # 不抛出异常，避免影响其他任务
        
    def _process_single_task(self, gpu_id: int, tasks: List[Task]) -> List[Dict[str, Any]]:
        """
        使用whisper_system进行多文件并行处理
        关键：每个任务在独立的spawn进程中执行，避免CUDA上下文冲突
        """
        try:
            logger.info(f"[PROCESSOR] 开始使用whisper_system处理 {len(tasks)} 个任务，GPU: {gpu_id}")
            
            # 验证所有任务都只有一个文件
            valid_tasks = []
            for task in tasks:
                if len(task.files) != 1:
                    logger.error(f"[PROCESSOR] 任务 {task.id} 文件数量不为1: {len(task.files)}")
                    continue
                valid_tasks.append(task)
            
            if not valid_tasks:
                logger.warning(f"[PROCESSOR] 没有有效的任务")
                return []
            
            # 使用whisper_system进行多文件并行处理
            if self.whisper_system:
                logger.info(f"[PROCESSOR] 使用whisper_system进行多文件并行处理")
                results = self.whisper_system._process_single_task(gpu_id, valid_tasks)
                logger.info(f"[PROCESSOR] whisper_system处理完成，成功: {sum(1 for r in results if r.get('success', False))}/{len(results)}")
                return results
            else:
                logger.error(f"[PROCESSOR] whisper_system未初始化")
                return [{'error': 'whisper_system未初始化', 'task_id': task.id} for task in valid_tasks]
            
        except Exception as e:
            logger.error(f"[PROCESSOR] 处理任务组失败: {e}", exc_info=True)
            return [{'error': str(e), 'task_id': task.id} for task in tasks]

    def _load_model(self, model_name: str, device: str, task_id: str = None):
        """加载模型到指定设备 - 多文件处理优化版本"""
        try:
            # 从设备字符串中提取GPU ID
            gpu_id = 0
            if device.startswith('cuda:'):
                gpu_id = int(device.split(':')[1])
            
            logger.info(f"[PROCESSOR] 开始加载模型 {model_name} 到 {device} (任务: {task_id})")
            
            # 多文件处理的关键：为每个任务创建独立的CUDA上下文
            if device.startswith('cuda'):
                try:
                    # 1. 清理CUDA缓存
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    
                    # 2. 设置设备
                    torch.cuda.set_device(gpu_id)
                    
                    # 3. 再次清理和同步
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    
                    # 4. 验证设备设置
                    current_device = torch.cuda.current_device()
                    if current_device != gpu_id:
                        logger.warning(f"[PROCESSOR] GPU设备不匹配: 期望{gpu_id}, 实际{current_device}")
                        torch.cuda.set_device(gpu_id)
                        torch.cuda.synchronize()
                    
                    logger.info(f"[PROCESSOR] CUDA上下文准备完成，设备: {torch.cuda.current_device()}")
                    
                except Exception as cuda_error:
                    logger.error(f"[PROCESSOR] CUDA上下文准备失败: {cuda_error}")
                    raise RuntimeError(f"CUDA上下文异常: {cuda_error}")
            
            # 加载模型 - 使用独立的上下文
            import whisper
            try:
                # 关键：为每个任务创建独立的模型实例
                model = whisper.load_model(model_name, device=device)
                logger.info(f"[PROCESSOR] 模型 {model_name} 加载成功到 {device}")
                
            except Exception as load_error:
                # 特殊处理CUDA设备端断言错误
                if "device-side assert triggered" in str(load_error):
                    logger.error(f"[PROCESSOR] CUDA设备端断言错误，尝试恢复")
                    try:
                        # 强制重置CUDA状态
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        torch.cuda.set_device(gpu_id)
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        
                        # 等待一段时间让GPU状态稳定
                        import time
                        time.sleep(0.1)
                        
                        # 重新尝试加载
                        model = whisper.load_model(model_name, device=device)
                        logger.info(f"[PROCESSOR] 模型 {model_name} 恢复加载成功")
                        
                    except Exception as recovery_error:
                        logger.error(f"[PROCESSOR] 模型恢复加载失败: {recovery_error}")
                        raise RuntimeError(f"CUDA设备端断言错误，无法恢复: {load_error}")
                else:
                    raise load_error
            
            # 验证模型权重（简化验证，避免过度检查）
            try:
                # 只做基本检查，避免触发CUDA错误
                if hasattr(model, 'encoder') and hasattr(model.encoder, 'blocks'):
                    logger.info(f"[PROCESSOR] 模型 {model_name} 结构验证通过")
                else:
                    logger.warning(f"[PROCESSOR] 模型 {model_name} 结构可能异常")
            except Exception as validation_error:
                logger.warning(f"[PROCESSOR] 模型验证失败，但继续使用: {validation_error}")
            
            logger.info(f"[PROCESSOR] 成功加载模型 {model_name} 到 {device} (任务: {task_id})")
            return model
            
        except Exception as e:
            logger.error(f"[PROCESSOR] 加载模型 {model_name} 失败 (任务: {task_id}): {e}", exc_info=True)
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
