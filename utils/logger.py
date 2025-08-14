"""
应用日志工具
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from config import config

# 创建日志目录
os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

# 创建logger
logger = logging.getLogger('whisper_app')
logger.setLevel(getattr(logging, config.LOG_LEVEL))

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建文件处理器
file_handler = RotatingFileHandler(
    config.LOG_FILE, 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setLevel(getattr(logging, config.LOG_LEVEL))

# 创建格式器
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 添加格式器到处理器
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# 添加处理器到logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 添加一个自定义方法用于系统消息
def system_message(message):
    """记录系统消息"""
    logger.info(f"[SYSTEM] {message}")

# 添加一个自定义方法用于用户操作
def user_action(message):
    """记录用户操作"""
    logger.info(f"[USER] {message}")

# 添加一个自定义方法用于错误
def error_message(message, exception=None):
    """记录错误消息"""
    if exception:
        logger.error(f"[ERROR] {message} - Exception: {exception}")
    else:
        logger.error(f"[ERROR] {message}")

# 添加一个自定义方法用于警告
def warning_message(message):
    """记录警告消息"""
    logger.warning(f"[WARNING] {message}")

# 添加一个自定义方法用于转录任务状态
def transcription_status(message, task_id=None, status=None):
    """记录转录任务状态"""
    if task_id and status:
        logger.info(f"[TRANSCRIPTION] [{task_id}] {status}: {message}")
    else:
        logger.info(f"[TRANSCRIPTION] {message}")

# 添加一个自定义方法用于文件操作
def file_operation(message, operation_type, filename=None):
    """记录文件操作"""
    if filename:
        logger.info(f"[FILE] [{operation_type}] {filename}: {message}")
    else:
        logger.info(f"[FILE] [{operation_type}] {message}")

# 添加一个自定义方法用于GPU信息
def gpu_info(message, gpu_data=None):
    """记录GPU信息"""
    if gpu_data:
        logger.info(f"[GPU] {message} - Data: {gpu_data}")
    else:
        logger.info(f"[GPU] {message}")

# 添加一个自定义方法用于客户端连接
def client_connected(message):
    """记录客户端连接"""
    logger.info(f"[CLIENT] CONNECTED: {message}")

# 添加一个自定义方法用于客户端断开
def client_disconnected(message):
    """记录客户端断开"""
    logger.info(f"[CLIENT] DISCONNECTED: {message}")

# 添加一个自定义方法用于转录任务开始
def transcription_started(message, task_id):
    """记录转录任务开始"""
    logger.info(f"[TRANSCRIPTION] STARTED [{task_id}]: {message}")

# 添加一个自定义方法用于转录任务完成
def transcription_completed(message, task_id):
    """记录转录任务完成"""
    logger.info(f"[TRANSCRIPTION] COMPLETED [{task_id}]: {message}")

# 添加一个自定义方法用于转录任务失败
def transcription_failed(message, task_id, error=None):
    """记录转录任务失败"""
    if error:
        logger.error(f"[TRANSCRIPTION] FAILED [{task_id}]: {message} - Error: {error}")
    else:
        logger.error(f"[TRANSCRIPTION] FAILED [{task_id}]: {message}")

# 添加一个自定义方法用于处理中
def processing(message, task_id=None):
    """记录处理中状态"""
    if task_id:
        logger.info(f"[PROCESSING] [{task_id}]: {message}")
    else:
        logger.info(f"[PROCESSING] {message}")

# 添加一个自定义方法用于完成
def completed(message, task_id=None):
    """记录完成状态"""
    if task_id:
        logger.info(f"[COMPLETED] [{task_id}]: {message}")
    else:
        logger.info(f"[COMPLETED] {message}")

# 添加一个自定义方法用于调试信息
def debug(message, *args, **kwargs):
    """记录调试信息"""
    logger.debug(f"[DEBUG] {message}", *args, **kwargs)

# 添加一个自定义方法用于详细信息
def info(message, *args, **kwargs):
    """记录详细信息"""
    logger.info(f"[INFO] {message}", *args, **kwargs)

# 添加一个自定义方法用于成功信息
def success(message, *args, **kwargs):
    """记录成功信息"""
    logger.info(f"[SUCCESS] {message}", *args, **kwargs)

# 为logger添加这些方法
logger.system = system_message
logger.user = user_action
logger.error_msg = error_message
logger.warning_msg = warning_message
logger.transcription = transcription_status
logger.file_op = file_operation
logger.gpu_info = gpu_info
logger.client_connected = client_connected
logger.client_disconnected = client_disconnected
logger.transcription_started = transcription_started
logger.transcription_completed = transcription_completed
logger.transcription_failed = transcription_failed
logger.processing = processing
logger.completed = completed
logger.debug = debug

# 导出logger以便其他模块使用
__all__ = ['logger']

# 添加WebSocket日志处理器
class WebSocketHandler(logging.Handler):
    """WebSocket日志处理器，用于将日志发送到前端"""
    def __init__(self, socketio):
        super().__init__()
        self.socketio = socketio

    def emit(self, record):
        try:
            # 解析日志消息，提取时间戳和级别信息
            message = record.getMessage()
            level = record.levelname.lower()
            
            # 根据日志级别设置颜色
            level_colors = {
                'debug': 'gray',
                'info': 'blue',
                'warning': 'orange',
                'error': 'red',
                'critical': 'red'
            }
            
            # 将日志消息按空格分割，提取时间戳和消息内容
            # 由于我们已经修改了格式，应该能正确解析
            log_entry = {
                'level': level,
                'message': message,
                'timestamp': datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
            }
            # 通过WebSocket发送日志到前端
            if self.socketio:
                self.socketio.emit('log_message', log_entry)
                
            # 同时在终端输出带时间戳的消息
            timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {message}")
        except Exception:
            # 避免日志处理错误导致程序崩溃
            pass

# 在应用启动时添加WebSocket处理器（需要在main.py中初始化）
