# whisper_system.py
import os
import time
import threading
import multiprocessing as mp
from typing import List, Dict, Any
from datetime import datetime

# 关键：任何 torch/whisper 都不在这里出现
from core.queue_manager import Task, TaskStatus
from core.transcription_saver import transcription_saver
from core.whisper_worker import transcribe_one, _init_worker
from config import config

# --------------- 进度消费线程 ---------------
# 进度功能已移除，避免Queue对象序列化问题


# --------------- 主系统 ---------------
class OptimizedWhisperSystem:
    _inst = None
    _lock = threading.Lock()

    def __new__(cls, *a, **kw):
        with cls._lock:
            if cls._inst is None:
                cls._inst = super().__new__(cls)
            return cls._inst

    def __init__(self, socketio=None):
        if hasattr(self, "init"):  # 单例只初始化一次
            return
        self.socketio = socketio
        self.init = True

    # ---------------- 对外唯一入口 ----------------
    def submit_task(self, task_data: Dict[str, Any]) -> str:
        """立即返回 task_id，任务进入队列"""
        task_id = task_data.get("task_id") or f"task_{int(time.time()*1000)}"
        # 这里仅做入队，真正的调度在调度器里完成
        # 为演示简洁，省略队列细节，直接调进程池
        return task_id

    def _process_single_task(self, gpu_id: int, tasks: List[Task]) -> List[Dict[str, Any]]:
        """
        被调度器调用：一个 GPU 上批量跑任务
        每个任务一个 spawn 进程，完全隔离 CUDA
        """
        # 在启动子进程前，若模型未就绪则触发“模型下载”弹窗并预下载
        try:
            from core.optimized_whisper import ModelDownloadProgress
            from core.optimized_whisper import get_optimized_system
            system = get_optimized_system()
            socketio = getattr(system, 'socketio', None)
            downloader = ModelDownloadProgress(socketio)

            # 针对本批任务的去重模型名检查
            checked_models = set()
            for task in tasks:
                model_name = task.model
                if model_name in checked_models:
                    continue
                checked_models.add(model_name)

                # 简单判断模型权重文件是否存在
                model_file = os.path.join(config.MODEL_BASE_PATH, f"{model_name}.pt")
                if not os.path.exists(model_file):
                    # 触发下载进度事件并同步下载，配合前端弹窗
                    downloader.download_model_with_progress(model_name=model_name, task_id=task.id, download_root=config.MODEL_BASE_PATH)
        except Exception as pre_dl_err:
            # 预下载失败不阻断任务，让子进程按需再次尝试（仍会触发下载逻辑）
            print(f"[DOWNLOAD] 预下载检查/触发失败: {pre_dl_err}")
        # 更新任务进度到开始处理
        for task in tasks:
            try:
                # 使用全局队列管理器实例
                from core.optimized_whisper import get_optimized_system
                system = get_optimized_system()
                if hasattr(system, 'queue_manager'):
                    system.queue_manager.update_task_progress(task.id, 10, "开始处理任务...")
            except Exception as e:
                print(f"[PROGRESS] 更新任务 {task.id} 进度失败: {e}")
        
        args = [
            (gpu_id, t.model, t.files[0], t.id, config.UPLOAD_FOLDER)
            for t in tasks
        ]
        
        # 为每个任务启动独立的进度监控线程
        import threading
        import time
        stop_progress_events = {}
        progress_threads = []
        
        def transcription_progress_monitor(task):
            """单个任务的转录进度监控线程"""
            task_id = task.id
            current_progress = 20
            
            # 为每个任务添加随机偏移，使进度更真实
            import random
            task_offset = random.uniform(0.5, 2.0)  # 随机偏移0.5-2秒
            update_interval = 1.0 + task_offset  # 每个任务有不同的更新间隔
            progress_increment = random.uniform(2.5, 3.5)  # 每个任务有不同的进度增量
            
            while not stop_progress_events[task_id].is_set() and current_progress < 90:
                time.sleep(update_interval)
                if not stop_progress_events[task_id].is_set():
                    current_progress += progress_increment
                    if current_progress > 90:
                        current_progress = 90
                    
                    # 根据进度阶段显示不同的消息
                    if current_progress < 40:
                        message = f"正在初始化转录引擎... ({int(current_progress)}%)"
                    elif current_progress < 70:
                        message = f"正在分析音频内容... ({int(current_progress)}%)"
                    else:
                        message = f"正在生成转录文本... ({int(current_progress)}%)"
                    
                    # 更新单个任务的进度
                    try:
                        from core.optimized_whisper import get_optimized_system
                        system = get_optimized_system()
                        if hasattr(system, 'queue_manager'):
                            system.queue_manager.update_task_progress(
                                task_id,
                                current_progress,
                                message
                            )
                    except Exception as e:
                        print(f"[PROGRESS] 更新任务 {task_id} 进度失败: {e}")
        
        # 为每个任务启动独立的进度监控线程
        for task in tasks:
            stop_progress_events[task.id] = threading.Event()
            progress_thread = threading.Thread(
                target=transcription_progress_monitor, 
                args=(task,), 
                daemon=True
            )
            progress_thread.start()
            progress_threads.append(progress_thread)
        
        try:
            with mp.Pool(processes=len(args), initializer=_init_worker, initargs=(gpu_id,)) as pool:
                worker_results = pool.map(transcribe_one, args)
        finally:
            # 停止所有任务的进度监控
            for task_id, stop_event in stop_progress_events.items():
                stop_event.set()
            
            # 等待所有进度监控线程结束
            for progress_thread in progress_threads:
                progress_thread.join(timeout=1)

        # 统一保存结果
        finals = []
        for wr in worker_results:
            if wr["success"]:
                # 更新进度到保存结果
                try:
                    # 使用全局队列管理器实例
                    from core.optimized_whisper import get_optimized_system
                    system = get_optimized_system()
                    if hasattr(system, 'queue_manager'):
                        system.queue_manager.update_task_progress(wr["task_id"], 90, "正在保存转录结果...")
                except Exception as e:
                    print(f"[PROGRESS] 更新任务 {wr['task_id']} 进度失败: {e}")
                
                # 构建task_data字典
                file_path = wr["file_path"]
                filename = os.path.basename(file_path)  # 获取文件名
                # 从任务中获取输出格式，如果没有则使用默认格式
                task_output_formats = getattr(tasks[0], 'output_formats', None) if tasks else None
                if not task_output_formats:
                    task_output_formats = ["txt"]  # 默认输出格式
                
                task_data = {
                    "task_id": wr["task_id"],
                    "file_path": file_path,
                    "files": [filename],  # 添加files字段用于文件命名
                    "output_formats": task_output_formats  # 使用任务指定的输出格式
                }
                saved = transcription_saver.save_transcription_result(
                    task_data, wr["result"]
                )
                wr["saved_files"] = saved
                
                # 更新进度到完成
                try:
                    # 使用全局队列管理器实例
                    from core.optimized_whisper import get_optimized_system
                    system = get_optimized_system()
                    if hasattr(system, 'queue_manager'):
                        system.queue_manager.update_task_progress(wr["task_id"], 100, "任务处理完成！")
                except Exception as e:
                    print(f"[PROGRESS] 更新任务 {wr['task_id']} 进度失败: {e}")
            else:
                # 任务失败，更新进度并标记失败
                try:
                    # 使用全局队列管理器实例
                    from core.optimized_whisper import get_optimized_system
                    system = get_optimized_system()
                    if hasattr(system, 'queue_manager'):
                        # 获取文件名信息
                        file_path = wr.get('file_path', '未知文件')
                        filename = os.path.basename(file_path) if file_path != '未知文件' else '未知文件'
                        error_msg = wr.get('error', '未知错误')
                        
                        # 构建详细的错误信息
                        detailed_error = f"文件 {filename} 处理失败: {error_msg}"
                        
                        # 更新进度显示失败状态
                        system.queue_manager.update_task_progress(wr["task_id"], -1, detailed_error)
                        
                        # 标记任务为失败状态
                        system.queue_manager.fail_task(wr["task_id"], detailed_error)
                        
                except Exception as e:
                    print(f"[PROGRESS] 更新任务 {wr['task_id']} 进度失败: {e}")
            
            finals.append(wr)
        return finals


# --------------- 全局单例 ---------------
def get_optimized_system(socketio=None) -> OptimizedWhisperSystem:
    return OptimizedWhisperSystem(socketio)
