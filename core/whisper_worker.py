# whisper_worker.py
import os
import time
import threading
import multiprocessing as mp
from typing import Tuple, Dict, Any

# 延迟导入，确保子进程才初始化 CUDA
import torch
import whisper


def _init_worker(gpu_id: int):
    """子进程初始化：隔离显卡"""
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)


def _progress_updater(task_id: str, q: mp.Queue):
    """异步进度生成器"""
    for pct in range(20, 100, 5):
        q.put((task_id, pct))
        time.sleep(1.5)
    q.put((task_id, 100))


def transcribe_one(args: Tuple[int, str, str, str, str]) -> Dict[str, Any]:
    """
    真正的转录工作函数，在 spawn 子进程中运行
    参数: (gpu_id, model_name, file_path, task_id, upload_root)
    """
    gpu_id, model_name, file_path, task_id, upload_root = args

    try:
        # 设置当前进程可见的唯一 GPU
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

        # 拼接完整路径
        full_path = os.path.join(upload_root, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.exists(full_path):
            raise FileNotFoundError(full_path)

        # 启动进度监控线程
        import threading
        import time
        stop_progress = threading.Event()
        
        def progress_updater():
            """进度更新线程"""
            current_progress = 20
            while not stop_progress.is_set() and current_progress < 90:
                time.sleep(2)  # 每2秒更新一次
                if not stop_progress.is_set():
                    current_progress += 5  # 每次增加5%
                    if current_progress > 90:
                        current_progress = 90
                    
                    # 记录进度到日志
                    print(f"[PROGRESS] 任务 {task_id} 进度: {current_progress}%")
        
        # 启动进度监控线程
        progress_thread = threading.Thread(target=progress_updater, daemon=True)
        progress_thread.start()

        try:
            # 加载模型 + 转录
            model = whisper.load_model(model_name, device="cuda")
            result = model.transcribe(full_path)
            del model
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        finally:
            # 停止进度监控
            stop_progress.set()
            progress_thread.join(timeout=1)

        return {"task_id": task_id, "success": True, "result": result, "file_path": full_path}

    except Exception as e:
        return {"task_id": task_id, "success": False, "error": str(e), "file_path": file_path}
    