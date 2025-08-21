"""
应用配置文件
"""

import os
from pathlib import Path

# 基础配置
BASE_DIR = Path(__file__).parent.absolute()

# 应用配置
class Config:
    # ==================== 安全配置 ====================
    # Flask应用密钥，用于会话加密和安全功能
    # 调用程序: main.py
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # ==================== 服务器配置 ====================
    # 服务器监听地址，0.0.0.0表示监听所有网络接口
    # 调用程序: main.py
    HOST = os.environ.get('HOST') or '127.0.0.1'
    
    # 服务器端口号
    # 调用程序: main.py
    PORT = int(os.environ.get('PORT') or 5552)
    
    # 调试模式开关，生产环境请设置为False
    # 调用程序: main.py
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # ==================== 文件上传配置 ====================
    # 上传文件存储目录
    # 调用程序: main.py, core/file_manager.py
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    
    # 转录结果输出目录
    # 调用程序: main.py, core/file_manager.py
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
    
    # 单个文件最大大小限制(字节)
    # 调用程序: main.py
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 1000)) * 1024 * 1024  # 默认1000MB
    
    # ==================== 日志配置 ====================
    # 日志文件路径
    # 调用程序: main.py, utils/logger.py
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'app.log')
    
    # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
    # 调用程序: main.py, utils/logger.py
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # 是否启用结构化日志
    # 调用程序: utils/logger.py
    ENABLE_STRUCTURED_LOGGING = os.environ.get('ENABLE_STRUCTURED_LOGGING', 'False').lower() == 'true'
    
    # 是否启用性能监控日志
    # 调用程序: utils/logger.py
    ENABLE_PERFORMANCE_MONITORING = os.environ.get('ENABLE_PERFORMANCE_MONITORING', 'False').lower() == 'true'
    
    # 性能监控日志文件路径
    # 调用程序: utils/logger.py
    PERFORMANCE_LOG_FILE = os.path.join(BASE_DIR, 'logs', 'performance.log')
    
    # 日志轮转配置 - 单个日志文件最大大小(MB)
    # 调用程序: utils/logger.py
    LOG_MAX_SIZE = int(os.environ.get('LOG_MAX_SIZE', 10))
    
    # 日志轮转配置 - 保留的备份文件数量
    # 调用程序: utils/logger.py
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))
    
    # 日志轮转配置 - 按时间轮转的备份文件数量
    # 调用程序: utils/logger.py
    TIMED_LOG_BACKUP_COUNT = int(os.environ.get('TIMED_LOG_BACKUP_COUNT', 30))
    
    # ==================== 默认设置 ====================
    # 默认使用的Whisper模型
    # 调用程序: main.py
    DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', 'base')
    
    # 默认语言设置，auto为自动检测
    # 调用程序: main.py
    DEFAULT_LANGUAGE = os.environ.get('DEFAULT_LANGUAGE', 'auto')
    
    # 默认使用的GPU ID
    # 调用程序: main.py
    DEFAULT_GPU_IDS = [int(id) for id in os.environ.get('DEFAULT_GPU_IDS', '').split(',') if id] or []
    
    # ==================== 转录设置 ====================
    # 最大并发转录任务数，根据GPU显存和性能调整
    # 调用程序: main.py
    MAX_CONCURRENT_TRANSCRIPTIONS = int(os.environ.get('MAX_CONCURRENT_TRANSCRIPTIONS', 5))
    
    # 单个转录任务超时时间(秒)
    # 调用程序: main.py
    TRANSCRIPTION_TIMEOUT = int(os.environ.get('TRANSCRIPTION_TIMEOUT', 3600))
    
    # 长音频分段处理时长(秒)
    # 调用程序: main.py
    SEGMENT_DURATION = int(os.environ.get('SEGMENT_DURATION', 30))
    
    # ==================== 文件管理 ====================
    # 文件最大保存天数
    # 调用函数: cleanup_old_files (core/file_manager.py)
    # 删除: MAX_FILE_AGE (在代码中未使用)
    
    # ==================== 安全配置 ====================
    # 允许上传的音频文件扩展名
    # 调用程序: main.py
    ALLOWED_EXTENSIONS = set(os.environ.get('ALLOWED_EXTENSIONS', 'wav,mp3,mp4,avi,mov,m4a,flac,ogg,wma,aac').split(','))
    
    # 文件名最大长度限制
    # 调用程序: main.py
    MAX_FILENAME_LENGTH = int(os.environ.get('MAX_FILENAME_LENGTH', 255))
    
    # ==================== GPU配置 ====================
    # GPU显存使用上限比例(0.1-1.0)
    # 调用程序: main.py
    MAX_GPU_MEMORY = float(os.environ.get('MAX_GPU_MEMORY', 0.8))
    
    # ==================== 内存管理 ====================
    # 显存安全边距，预留给系统的显存比例
    # 调用程序: main.py, core/gpu_manager.py
    MEMORY_SAFETY_MARGIN = float(os.environ.get('MEMORY_SAFETY_MARGIN', 0.1))
    
    # 预留显存大小(GB)，用于系统和其他进程
    # 调用程序: main.py, core/gpu_manager.py, core/optimized_whisper.py
    RESERVED_MEMORY = float(os.environ.get('RESERVED_MEMORY', 0.0))
    
    # ==================== 模型配置 ====================
    # Whisper模型存储基础路径
    # 调用程序: main.py, config.py
    MODEL_BASE_PATH = os.environ.get('MODEL_BASE_PATH') or os.path.join(os.path.expanduser('~'), '.cache', 'whisper')
    
    # 系统支持的模型列表
    # 调用程序: main.py, config.py
    SUPPORTED_MODELS = os.environ.get('SUPPORTED_MODELS', 'tiny,base,small,medium,large,large-v2,large-v3,turbo').split(',')
    
    # ==================== 优化系统配置 ====================
    # 启用优化系统，提供智能队列管理和显存优化
    # 调用程序: main.py
    ENABLE_OPTIMIZATION_SYSTEM = os.environ.get('ENABLE_OPTIMIZATION_SYSTEM', 'True').lower() == 'true'
    
    # 批量任务调度间隔(秒)
    # 调用程序: main.py
    BATCH_SCHEDULE_INTERVAL = float(os.environ.get('BATCH_SCHEDULE_INTERVAL', 2))
    
    # 最大任务重试次数
    # 调用程序: main.py
    MAX_TASK_RETRIES = int(os.environ.get('MAX_TASK_RETRIES', 3))
    
    # 显存校准参数，用于动态调整模型显存预估
    # 调用程序: main.py
    MEMORY_CALIBRATION_FACTOR = float(os.environ.get('MEMORY_CALIBRATION_FACTOR', 1.2))
    
    # 性能监控间隔(秒)
    # 调用程序: main.py
    PERFORMANCE_MONITOR_INTERVAL = int(os.environ.get('PERFORMANCE_MONITOR_INTERVAL', 30))
    
    # 自适应优化开关，根据性能指标自动调整参数
    # 调用程序: main.py
    ENABLE_ADAPTIVE_OPTIMIZATION = os.environ.get('ENABLE_ADAPTIVE_OPTIMIZATION', 'True').lower() == 'true'
    
    # 最小批处理大小
    # 调用程序: main.py, core/batch_scheduler.py
    MIN_BATCH_SIZE = int(os.environ.get('MIN_BATCH_SIZE', 1))
    
    # 最大批处理大小
    # 调用程序: main.py, core/batch_scheduler.py
    MAX_BATCH_SIZE = int(os.environ.get('MAX_BATCH_SIZE', 4))
    
    # ==================== WebSocket配置 ====================
    # WebSocket连接超时时间(秒)
    # 调用程序: main.py
    WEBSOCKET_PING_TIMEOUT = int(os.environ.get('WEBSOCKET_PING_TIMEOUT', 60))
    
    # WebSocket心跳检测间隔(秒)
    # 调用程序: main.py
    WEBSOCKET_PING_INTERVAL = int(os.environ.get('WEBSOCKET_PING_INTERVAL', 25))
    
    # ==================== 性能配置 ====================
    # 工作线程数
    # 调用程序: main.py
    WORKER_THREADS = int(os.environ.get('WORKER_THREADS', 4))
    
    # 自动清理任务执行间隔(秒)
    # 调用程序: core/batch_scheduler.py
    CLEANUP_INTERVAL = int(os.environ.get('CLEANUP_INTERVAL', 3600))
    
    # 内存清理触发阈值
    # 调用程序: main.py
    MEMORY_CLEANUP_THRESHOLD = float(os.environ.get('MEMORY_CLEANUP_THRESHOLD', 0.9))
    
    # ==================== 新增参数 ====================
    # 最大任务数限制，用于防止系统过载
    # 调用程序: main.py, core/gpu_manager.py
    # 新增
    MAX_TASKS_PER_GPU = int(os.environ.get('MAX_TASKS_PER_GPU', 5))
    
    # ==================== 删除参数 ====================
    # 删除: MAX_LOG_SIZE (在代码中未使用)
    # 删除: LOG_BACKUP_COUNT (在代码中未使用)
    # 删除: MAX_FILE_AGE (在代码中未使用)
    
    @staticmethod
    def get_model_path(model_name):
        """获取指定模型的完整路径"""
        return os.path.join(Config.MODEL_BASE_PATH, f'whisper-{model_name}')
    
    @staticmethod
    def ensure_model_directory():
        """确保模型目录存在"""
        os.makedirs(Config.MODEL_BASE_PATH, exist_ok=True)
        # 为每个模型创建目录
        for model in Config.SUPPORTED_MODELS:
            model_dir = Config.get_model_path(model)
            os.makedirs(model_dir, exist_ok=True)
    
    # 数据库配置（如果将来需要）
    SQLALCHEMY_DATABASE_URI = None
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# Whisper相关常量
SUPPORTED_LANGUAGES = [
    ('zh', '中文'),
    ('en', '英语'),
    ('ja', '日语'),
    ('ko', '韩语'),
    ('fr', '法语'),
    ('de', '德语'),
    ('es', '西班牙语'),
    ('ru', '俄语'),
    ('ar', '阿拉伯语'),
    ('pt', '葡萄牙语')
]

WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3', 'turbo']

WHISPER_MODEL_MEMORY_REQUIREMENTS = {
    'tiny': 1.0,
    'base': 1.0,
    'small': 2.0,
    'medium': 5.0,
    'large': 10.0,
    'large-v2': 10.0,
    'large-v3': 10.0,
    'turbo': 6.0
}

# 创建配置实例
config = Config()
