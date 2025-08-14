"""
应用配置文件
"""

import os
from pathlib import Path

# 基础配置
BASE_DIR = Path(__file__).parent.absolute()

# 应用配置
class Config:
    # 安全配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # 服务器配置
    HOST = os.environ.get('HOST') or '127.0.0.1'
    PORT = int(os.environ.get('PORT') or 5000)
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
    MAX_CONTENT_LENGTH = 1000 * 1024 * 1024  # 1000MB max file size
    
    # 日志配置
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'app.log')
    LOG_LEVEL = 'INFO'
    
    # 默认设置
    DEFAULT_MODEL = 'base'
    DEFAULT_LANGUAGE = 'auto'
    DEFAULT_GPU_IDS = []
    
    # 模型配置
    MODEL_BASE_PATH = os.environ.get('MODEL_BASE_PATH') or os.path.join(os.path.expanduser('~'), '.cache', 'whisper')
    SUPPORTED_MODELS = os.environ.get('SUPPORTED_MODELS', 'tiny,base,small,medium,large,large-v2,large-v3').split(',')
    
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

# 创建配置实例
config = Config()
