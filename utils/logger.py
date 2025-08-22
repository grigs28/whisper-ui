"""
应用日志工具
"""

import logging
import os
import json
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from flask_socketio import SocketIO
from typing import Dict, Any, Optional
from config import config

# 创建日志目录
os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

# 创建logger
logger = logging.getLogger('whisper_app')
logger.setLevel(getattr(logging, config.LOG_LEVEL))

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建格式器
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 结构化日志格式器
class StructuredFormatter(logging.Formatter):
    """结构化日志格式器，支持JSON格式输出"""
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # 添加性能监控相关字段
        if hasattr(record, 'performance_data'):
            log_entry['performance'] = record.performance_data
        
        # 添加任务ID相关字段
        if hasattr(record, 'task_id'):
            log_entry['task_id'] = record.task_id
        
        # 添加用户ID相关字段
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
            
        return json.dumps(log_entry, ensure_ascii=False)

# 创建文件处理器 - 支持日志轮转
file_handler = RotatingFileHandler(
    config.LOG_FILE,
    maxBytes=config.LOG_MAX_SIZE * 1024 * 1024,
    backupCount=config.LOG_BACKUP_COUNT
)
file_handler.setLevel(getattr(logging, config.LOG_LEVEL))

# 创建按时间轮转的文件处理器
timed_file_handler = TimedRotatingFileHandler(
    config.LOG_FILE.replace('.log', '_timed.log'),
    when='midnight',
    interval=1,
    backupCount=config.TIMED_LOG_BACKUP_COUNT
)
timed_file_handler.setFormatter(formatter)
timed_file_handler.setLevel(getattr(logging, config.LOG_LEVEL))

# 创建结构化日志处理器（根据配置决定是否启用）
structured_file_handler = None
if config.ENABLE_STRUCTURED_LOGGING:
    structured_file_handler = RotatingFileHandler(
        config.LOG_FILE.replace('.log', '_structured.json'),
        maxBytes=config.LOG_MAX_SIZE * 1024 * 1024,
        backupCount=config.LOG_BACKUP_COUNT
    )
    structured_file_handler.setFormatter(StructuredFormatter())
    structured_file_handler.setLevel(logging.INFO)

# 创建性能监控日志处理器（根据配置决定是否启用）
performance_file_handler = None
if config.ENABLE_PERFORMANCE_MONITORING:
    performance_file_handler = RotatingFileHandler(
        config.PERFORMANCE_LOG_FILE,
        maxBytes=config.LOG_MAX_SIZE * 1024 * 1024,
        backupCount=config.LOG_BACKUP_COUNT
    )
    performance_file_handler.setFormatter(formatter)
    performance_file_handler.setLevel(logging.INFO)

# 添加格式器到处理器
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# 添加处理器到logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.addHandler(timed_file_handler)

# 根据配置添加结构化日志处理器
if structured_file_handler:
    logger.addHandler(structured_file_handler)

# 根据配置添加性能监控日志处理器
if performance_file_handler:
    logger.addHandler(performance_file_handler)

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

# 添加性能监控日志方法
def performance_monitor(operation: str, duration: float, task_id: str = None, 
                       user_id: str = None, **kwargs):
    """记录性能监控信息"""
    if not config.ENABLE_PERFORMANCE_MONITORING:
        return
        
    performance_data = {
        'operation': operation,
        'duration_ms': round(duration * 1000, 2),
        'timestamp': datetime.now().isoformat()
    }
    
    # 添加额外的性能指标
    if kwargs:
        performance_data.update(kwargs)
    
    # 创建自定义日志记录
    log_record = logging.LogRecord(
        name=logger.name,
        level=logging.INFO,
        pathname='',
        lineno=0,
        msg=f"[PERFORMANCE] {operation} took {duration:.3f}s",
        args=(),
        exc_info=None
    )
    
    # 添加性能数据
    log_record.performance_data = performance_data
    if task_id:
        log_record.task_id = task_id
    if user_id:
        log_record.user_id = user_id
    
    logger.handle(log_record)

# 添加结构化日志方法
def structured_log(level: str, message: str, **kwargs):
    """记录结构化日志"""
    if not config.ENABLE_STRUCTURED_LOGGING:
        return
        
    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    
    log_level = level_map.get(level.lower(), logging.INFO)
    
    # 创建自定义日志记录
    log_record = logging.LogRecord(
        name=logger.name,
        level=log_level,
        pathname='',
        lineno=0,
        msg=message,
        args=(),
        exc_info=None
    )
    
    # 添加结构化数据
    for key, value in kwargs.items():
        setattr(log_record, key, value)
    
    logger.handle(log_record)

# 性能监控装饰器
def performance_monitor_decorator(operation_name: str = None):
    """性能监控装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            operation = operation_name or f"{func.__module__}.{func.__name__}"
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                performance_monitor(operation, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                performance_monitor(operation, duration, error=str(e))
                raise
        return wrapper
    return decorator

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
logger.performance = performance_monitor
logger.structured = structured_log
logger.monitor = performance_monitor_decorator

# 导出logger和相关函数以便其他模块使用
__all__ = ['logger', 'performance_monitor', 'structured_log', 'performance_monitor_decorator']
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
            
            # 检查特殊日志类型并映射到相应级别
            if '[GPU_ALLOC]' in message:
                level = 'gpu'
            elif '[GPU_POOL]' in message:
                level = 'gpu'
            elif '[TRANSCRIPTION]' in message:
                level = 'transcription'
            elif '[FILE]' in message:
                level = 'file'
            elif '[CLIENT]' in message:
                level = 'client'
            elif '[SYSTEM]' in message:
                level = 'system'
            elif '[PROCESSING]' in message:
                level = 'processing'
            elif '[COMPLETED]' in message:
                level = 'completed'
            elif '[ERROR]' in message:
                level = 'error'
            elif '[WARNING]' in message:
                level = 'warning'
            elif '[SUCCESS]' in message:
                level = 'success'
            
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
            
            # 通过WebSocket发送日志到前端，添加错误处理
            if self.socketio:
                try:
                    self.socketio.emit('log_message', log_entry)
                except Exception as ws_error:
                    # WebSocket发送失败时不中断程序，只在控制台输出错误
                    print(f"WebSocket日志发送失败: {ws_error}")
                
            # 同时在终端输出带时间戳的消息
            timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {message}")
        except Exception as e:
            # 避免日志处理错误导致程序崩溃，只在控制台输出错误
            print(f"WebSocket日志处理器错误: {e}")
            pass

# 在应用启动时添加WebSocket处理器（需要在main.py中初始化）
