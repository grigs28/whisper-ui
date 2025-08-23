#!/usr/bin/env python3
"""
Whisper 音频转录系统主程序
"""

import os
import sys
import json
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import uuid
import io
import re
import markdown
from contextlib import redirect_stderr
from io import StringIO

from flask import Flask, render_template, request, jsonify, send_file, abort, send_from_directory
from flask_socketio import SocketIO, emit
import torch
import whisper
from werkzeug.utils import secure_filename
import opencc
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from utils.logger import logger
from utils.logger import WebSocketHandler
from core.optimized_whisper import get_optimized_system, OptimizedWhisperSystem
from core.file_manager import FileManager
from core.gpu_manager import EnhancedGPUManager as GPUManager

# 重定向stdout以添加时间戳到所有输出
class TimestampedStdout:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout
        self.buffer = ""
    
    def write(self, message):
        if message.strip():  # 只处理非空行
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # 对于WebSocket框架消息，添加时间戳
            if ':' in message and 'Sending packet' in message or 'Received packet' in message:
                # 这些是WebSocket框架消息，添加时间戳
                formatted_message = f"[{timestamp}] {message.rstrip()}"
            else:
                # 其他消息保持原样
                formatted_message = f"[{timestamp}] {message.rstrip()}"
            self.original_stdout.write(formatted_message + '\n')
            self.original_stdout.flush()
        else:
            self.original_stdout.write(message)
            self.original_stdout.flush()
    
    def flush(self):
        self.original_stdout.flush()

# ProgressCapture类已移动到core/transcription.py

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# 初始化SocketIO
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    logger=False, 
    engineio_logger=False,
    ping_timeout=120,  # 增加ping超时时间到120秒
    ping_interval=30,  # 增加ping间隔到30秒
    async_mode='threading',  # 使用线程模式
    manage_session=False,  # 禁用会话管理，避免冲突
    always_connect=True,  # 总是尝试连接
    transports=['websocket', 'polling']  # 支持多种传输方式
)

# 添加错误处理中间件
@app.errorhandler(404)
def not_found_error(error):
    """处理404错误"""
    if request.path.endswith('.map'):
        # 对于Source Map文件，返回空响应
        return '', 204
    return '文件未找到', 404

@app.errorhandler(500)
def internal_error(error):
    """处理500错误"""
    logger.error(f'服务器内部错误: {error}')
    return '服务器内部错误', 500

# 添加WebSocket错误处理
@socketio.on_error_default
def default_error_handler(e):
    """默认WebSocket错误处理器"""
    logger.error(f'WebSocket默认错误处理器: {str(e)}')
    return False  # 不阻止错误传播

# 添加请求前处理中间件
@app.before_request
def before_request():
    """请求前处理"""
    # 确保响应头正确设置
    if request.path.startswith('/socket.io/'):
        # 对于WebSocket请求，设置正确的响应头
        pass

# 确保必要的目录存在
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

# 常量已移动到相应的模块中
from config import SUPPORTED_LANGUAGES, WHISPER_MODEL_MEMORY_REQUIREMENTS

# GPU信息缓存
gpu_info_cache = {}
last_gpu_info_time = 0
GPU_INFO_CACHE_DURATION = 30  # 缓存30秒

# 显存安全边际（从配置文件读取）
MEMORY_SAFETY_MARGIN = config.MEMORY_SAFETY_MARGIN

# 优化系统实例
optimized_whisper_system = None

# 任务管理器和处理器实例
task_manager = None
task_processor = None
transcription_processor = None
gpu_manager = None
file_manager = None


# start_pending_tasks函数已移动到TaskProcessor类中
            


def parse_version_md():
    """解析 Markdown 版本文件"""
    try:
        version_path = 'version.md'
        if not os.path.exists(version_path):
            return None
            
        with open(version_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析版本历史
        versions = []
        current_version = None
        
        lines = content.split('\n')
        for line in lines:
            # 匹配版本号标题 (## v0.0.1 (2025-08-13))
            version_match = re.match(r'^## v([\d\.]+)\s*\(([^)]+)\)', line)
            if version_match:
                if current_version:
                    versions.append(current_version)
                current_version = {
                    'version': version_match.group(1),
                    'date': version_match.group(2),
                    'features': [],
                    'improvements': [],
                    'description': ''
                }
            elif current_version:
                # 解析功能和改进
                if line.startswith('- '):
                    item = line[2:].strip()
                    if '### 新增功能' in ''.join(lines[max(0, lines.index(line)-5):lines.index(line)]):
                        current_version['features'].append(item)
                    elif '### 改进' in ''.join(lines[max(0, lines.index(line)-5):lines.index(line)]) or '### 改进内容' in ''.join(lines[max(0, lines.index(line)-5):lines.index(line)]):
                        current_version['improvements'].append(item)
                elif line.startswith('### 项目描述'):
                    # 获取下一行作为描述
                    try:
                        desc_line = lines[lines.index(line) + 1]
                        current_version['description'] = desc_line.strip()
                    except IndexError:
                        pass
        
        if current_version:
            versions.append(current_version)
        
        return {
            'latest_version': versions[0]['version'] if versions else '1.0.0',
            'versions': versions,
            'content': content
        }
    except Exception as e:
        logger.error(f"解析版本文件失败: {str(e)}")
        return None

@app.route('/')
def index():
    """主页路由"""
    # 获取GPU信息
    gpu_info = gpu_manager.get_gpu_info() if gpu_manager else {'success': False, 'error': 'GPU管理器未初始化', 'gpus': []}
    gpus = []
    
    # 确定默认GPU选择
    default_gpu_id = None
    if gpu_info.get('success') and gpu_info.get('gpus'):
        # 使用完整的GPU信息列表
        gpus = gpu_info['gpus']
        # 选择空闲内存最多的GPU
        best_gpu_id = gpu_info.get('best_gpu')
        if best_gpu_id is not None:
            default_gpu_id = best_gpu_id
    
    # 获取文件列表
    uploaded_files = file_manager.get_uploaded_files() if file_manager else []
    output_files = file_manager.get_output_files() if file_manager else []
    
    # 动态获取whisper模型列表
    whisper_models = config.get_whisper_models()
    
    # 获取模型内存需求（显示格式）
    model_memory_requirements = config.get_model_memory_requirements_display()
    
    return render_template(
        'index.html',
        gpus=gpus,
        default_gpu_id=default_gpu_id,
        uploaded_files=uploaded_files,
        output_files=output_files,
        languages=SUPPORTED_LANGUAGES,
        whisper_models=whisper_models,
        model_memory_requirements=model_memory_requirements,
        default_model=config.DEFAULT_MODEL
    )

@app.route('/upload', methods=['POST'])
def upload_files():
    """文件上传接口"""
    try:
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': '没有文件被上传'}), 400
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'success': False, 'error': '没有选择文件'}), 400
        
        uploaded_filenames = []
        
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                
                # 检查文件是否已存在
                if os.path.exists(filepath):
                    # 如果文件已存在，添加格式化时间戳避免覆盖
                    name, ext = os.path.splitext(filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{name}_{timestamp}{ext}"
                    filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                
                file.save(filepath)
                uploaded_filenames.append(filename)
                logger.file_op(f"文件已上传: {filename}", "UPLOAD", filename)
        
        return jsonify({
            'success': True,
            'filenames': uploaded_filenames,
            'count': len(uploaded_filenames)
        })
        
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/delete_uploaded/<path:filename>', methods=['DELETE'])
def delete_uploaded_file(filename):
    """删除上传的文件"""
    try:
        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.file_op(f"已删除上传文件: {filename}", "DELETE", filename)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '文件不存在'}), 404
            
    except Exception as e:
        logger.error(f"删除文件失败 {filename}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/delete_output/<path:filename>', methods=['DELETE'])
def delete_output_file(filename):
    """删除输出的文件"""
    try:
        filepath = os.path.join(config.OUTPUT_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.file_op(f"已删除输出文件: {filename}", "DELETE", filename)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '文件不存在'}), 404
            
    except Exception as e:
        logger.error(f"删除文件失败 {filename}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download/upload/<path:filename>')
def download_uploaded_file(filename):
    """下载上传的文件"""
    try:
        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            abort(404)
    except Exception as e:
        logger.error(f"下载文件失败 {filename}: {str(e)}")
        abort(500)

@app.route('/download/output/<path:filename>')
def download_output_file(filename):
    """下载输出的文件"""
    try:
        filepath = os.path.join(config.OUTPUT_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            abort(404)
    except Exception as e:
        logger.error(f"下载文件失败 {filename}: {str(e)}")
        abort(500)

@app.route('/transcribe', methods=['POST'])
def start_transcription():
    """开始转录任务"""
    try:
        data = request.get_json()
        files = data.get('files', [])
        model = data.get('model', config.DEFAULT_MODEL)
        language = data.get('language', config.DEFAULT_LANGUAGE)
        gpus = data.get('gpus', config.DEFAULT_GPU_IDS)
        output_format = data.get('output_format', 'json')
        
        if not files:
            return jsonify({'success': False, 'error': '没有选择文件'}), 400
        
        task_ids = []
        
        # 使用优化系统提交任务
        if optimized_whisper_system:
            # 为每个文件创建单独的任务
            for filename in files:
                task_id = str(uuid.uuid4())
                task_data = {
                    'task_id': task_id,
                    'files': [filename],
                    'model': model,
                    'language': language,
                    'gpus': gpus,
                    'output_format': output_format,
                    'user_id': 'web_user'  # 默认用户ID
                }
                
                # 提交任务到优化系统
                optimized_whisper_system.submit_task(task_data)
                task_ids.append(task_id)
                
                # 通过WebSocket推送任务状态
                socketio.emit('task_update', {
                    'id': task_id,
                    'status': 'pending',
                    'progress': 0,
                    'message': '等待处理...',
                    'files': [filename],
                    'filename': filename,
                    'model': model,
                    'language': language,
                    'created_at': datetime.now().isoformat()
                })
        else:
            return jsonify({'success': False, 'error': '优化系统未初始化'}), 500
        
        logger.info(f"转录任务已提交: {len(task_ids)}个文件")
        return jsonify({
            'success': True,
            'task_ids': task_ids,
            'count': len(task_ids)
        })
        
    except Exception as e:
        logger.error(f"启动转录任务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# process_transcription_task 函数已迁移至 TaskProcessor 类中

@app.route('/gpu_info')
def get_gpu_info_endpoint():
    """获取GPU信息接口"""
    try:
        # 使用优化系统的GPU管理器
        if optimized_whisper_system:
            system_status = optimized_whisper_system.get_system_status()
            gpu_status = system_status.get('gpu_status', {})
            # 转换为前端期望的格式
            gpus = []
            for gpu_id, status in gpu_status.items():
                gpu_info = {
                    'id': gpu_id,
                    'name': status.get('name', f'GPU {gpu_id}'),
                    'total_memory': status.get('total_memory', 0),
                    'allocated_memory': status.get('allocated_memory', 0),
                    'free_memory': status.get('free_memory', 0),
                    'available_memory': status.get('available_memory', 0),
                    'utilization': status.get('utilization', 0)
                }
                # 如果有温度信息也加上
                if 'temperature' in status:
                    gpu_info['temperature'] = status['temperature']
                gpus.append(gpu_info)
            
            gpu_info = {
                'success': True,
                'gpus': gpus
            }
        else:
            # 使用传统的GPU管理器
            gpu_info = gpu_manager.get_gpu_info()
        return jsonify(gpu_info)
    except Exception as e:
        logger.error(f"获取GPU信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/gpu_selector')
def get_gpu_selector_endpoint():
    """获取GPU选择器列表接口"""
    try:
        # 使用优化系统的GPU管理器
        if optimized_whisper_system:
            system_status = optimized_whisper_system.get_system_status()
            gpu_list = system_status.get('gpu_selector', [])
            best_gpu = system_status.get('best_gpu_id')
        else:
            # 使用传统的GPU管理器
            gpu_list = gpu_manager.get_gpu_list_for_selector()
            best_gpu = gpu_manager.get_best_available_gpu()
        
        # 确定默认选择
        default_selection = 'cpu'  # 默认CPU
        if best_gpu is not None:
            default_selection = f'gpu_{best_gpu}'
        
        return jsonify({
            'success': True,
            'gpus': gpu_list,
            'default_selection': default_selection,
            'best_gpu_id': best_gpu
        })
    except Exception as e:
        logger.error(f"获取GPU选择器信息时出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'gpus': [{
                'id': 'cpu',
                'name': 'CPU',
                'type': 'cpu',
                'memory_info': 'CPU处理'
            }],
            'default_selection': 'cpu',
            'best_gpu_id': None
        })

@app.route('/queue_state')
def get_queue_state():
    """获取队列状态"""
    # 使用优化系统的队列管理
    if optimized_whisper_system:
        system_status = optimized_whisper_system.get_system_status()
        # 获取任务信息需要从队列管理器获取
        all_tasks = []
        if hasattr(optimized_whisper_system, 'queue_manager'):
            # 从队列管理器获取所有任务
            queue_manager = optimized_whisper_system.queue_manager
            # 获取所有等待中的任务
            for model_name in queue_manager.queues:
                for task in queue_manager.queues[model_name]:
                    all_tasks.append(task.to_dict())
            # 获取所有处理中的任务
            for task in queue_manager.processing_tasks.values():
                all_tasks.append(task.to_dict())
        current_running_tasks = system_status.get('queue_stats', {}).get('total_processing', 0)
    else:
        all_tasks = []
        current_running_tasks = 0
    
    return jsonify({
        'success': True,
        'items': all_tasks,
        'max_concurrent_tasks': config.MAX_CONCURRENT_TRANSCRIPTIONS,
        'current_running_tasks': current_running_tasks
    })

@app.route('/concurrent_settings', methods=['GET', 'POST'])
def concurrent_settings():
    """获取或设置并发设置"""
    if request.method == 'GET':
        # 获取当前运行任务数
        current_running = 0
        if optimized_whisper_system and hasattr(optimized_whisper_system, 'queue_manager'):
            queue_stats = optimized_whisper_system.queue_manager.get_queue_stats()
            current_running = queue_stats.get('total_processing', 0)
        
        return jsonify({
            'success': True,
            'max_concurrent_tasks': config.MAX_CONCURRENT_TRANSCRIPTIONS,
            'current_running_tasks': current_running,
            'min_concurrent_tasks': 1,
            'max_limit': 20
        })
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            max_tasks = data.get('max_concurrent_tasks')
            
            if max_tasks is None:
                return jsonify({'success': False, 'error': '缺少max_concurrent_tasks参数'}), 400
            
            if not isinstance(max_tasks, int) or max_tasks < 1 or max_tasks > 20:
                return jsonify({'success': False, 'error': '并发任务数必须在1-20之间'}), 400
            
            new_max = max_tasks
            
            # 获取当前运行任务数
            current_running = 0
            if optimized_whisper_system and hasattr(optimized_whisper_system, 'queue_manager'):
                queue_stats = optimized_whisper_system.queue_manager.get_queue_stats()
                current_running = queue_stats.get('total_processing', 0)
            
            # 如果增加了并发数，尝试启动等待中的任务
            if new_max > current_running:
                # 优化系统会自动调度任务，不需要手动启动
                pass
            
            return jsonify({
                'success': True,
                'max_concurrent_tasks': new_max,
                'current_running_tasks': current_running
            })
            
        except Exception as e:
            logger.error(f"设置并发任务数失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/readme')
def get_readme():
    """获取README内容"""
    try:
        readme_path = 'README.md'
        if os.path.exists(readme_path):
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 将 Markdown 转换为 HTML
            html_content = markdown.markdown(content, extensions=['codehilite', 'fenced_code', 'tables'])
            return jsonify({
                'success': True,
                'content': content,
                'html_content': html_content
            })
        else:
            return jsonify({
                'success': False,
                'error': 'README文件不存在'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/version')
def get_version():
    """获取版本信息"""
    try:
        # 优先使用 Markdown 版本文件
        version_data = parse_version_md()
        if version_data:
            return jsonify({
                'success': True,
                'version': version_data['latest_version']
            })
        
        # 回退到 JSON 版本文件
        version_path = 'version.json'
        if os.path.exists(version_path):
            with open(version_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            return jsonify({
                'success': True,
                'version': json_data.get('version', 'unknown')
            })
        else:
            return jsonify({
                'success': True,
                'version': '1.0.0'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/uploaded_files')
def get_uploaded_files_api():
    """获取上传文件列表"""
    try:
        files = file_manager.get_uploaded_files()
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/output_files')
def get_output_files_api():
    """获取输出文件列表"""
    try:
        files = file_manager.get_output_files()
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/version_history')
def get_version_history():
    """获取版本历史"""
    try:
        # 尝试从version.md文件读取版本历史
        version_file = os.path.join(os.path.dirname(__file__), 'version.md')
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析版本历史（这里简化处理，实际可能需要更复杂的解析）
            version_data = {
                'versions': [
                    {
                        'version': '1.0.0',
                        'date': '2025-01-13',
                        'changes': [
                            '初始版本发布',
                            '支持多文件上传',
                            '支持多种语言转录',
                            '支持GPU加速',
                            '实时任务监控'
                        ]
                    }
                ],
                'content': content
            }
            
            return jsonify({
                'success': True,
                'history': version_data['versions'],
                'content': version_data['content']
            })
        
        # 回退到默认版本历史
        return jsonify({
            'success': True,
            'history': [
                {
                    'version': '1.0.0',
                    'date': '2025-08-13',
                    'changes': [
                        '初始版本发布',
                        '支持多文件上传',
                        '支持多种语言转录',
                        '支持GPU加速',
                        '实时任务监控'
                    ]
                }
            ]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/config')
def get_config():
    """获取客户端配置信息"""
    try:
        config_data = {
            'enable_browser_console_log': config.ENABLE_BROWSER_CONSOLE_LOG,
            'debug_mode': config.DEBUG,
            'log_level': config.LOG_LEVEL
        }
        return jsonify(config_data)
    except Exception as e:
        logger.error(f'获取配置信息时出错: {str(e)}')
        return jsonify({
            'enable_browser_console_log': True,  # 默认值
            'debug_mode': False,
            'log_level': 'INFO'
        }), 500

@app.route('/memory_statistics')
def get_memory_statistics():
    """获取显存使用统计信息"""
    try:
        if optimized_whisper_system and hasattr(optimized_whisper_system, 'memory_pool'):
            # 获取所有统计信息
            all_stats = optimized_whisper_system.memory_pool.get_memory_statistics()
            accuracy_analysis = optimized_whisper_system.memory_pool.get_accuracy_analysis()
            recent_records = optimized_whisper_system.memory_pool.get_recent_memory_records(20)
            
            return jsonify({
                'success': True,
                'statistics': all_stats,
                'accuracy_analysis': accuracy_analysis,
                'recent_records': recent_records,
                'total_records': len(recent_records)
            })
        else:
            return jsonify({'success': False, 'error': '显存管理器未初始化'}), 500
    except Exception as e:
        logger.error(f"获取显存统计信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/memory_statistics/<model_name>')
def get_model_memory_statistics(model_name):
    """获取指定模型的显存使用统计信息"""
    try:
        if optimized_whisper_system and hasattr(optimized_whisper_system, 'memory_pool'):
            # 获取指定模型的统计信息
            model_stats = optimized_whisper_system.memory_pool.get_memory_statistics(model_name)
            calibration_factor = optimized_whisper_system.memory_pool.get_calibration_factor(model_name)
            
            return jsonify({
                'success': True,
                'model_name': model_name,
                'statistics': model_stats,
                'calibration_factor': calibration_factor
            })
        else:
            return jsonify({'success': False, 'error': '显存管理器未初始化'}), 500
    except Exception as e:
        logger.error(f"获取模型{model_name}显存统计信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/test')
def test_page():
    """测试页面"""
    return send_from_directory('.', 'test_logging.html')

@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    try:
        logger.client_connected('客户端已连接')
        logger.system('客户端已连接')
        # 发送连接确认
        emit('connection_ack', {'status': 'connected', 'timestamp': time.time()})
    except Exception as e:
        logger.error(f'处理WebSocket连接时出错: {str(e)}')

@socketio.on('disconnect')
def handle_disconnect(data=None):
    """处理客户端断开连接"""
    try:
        logger.client_disconnected('客户端已断开连接')
        logger.system('客户端已断开连接')
    except Exception as e:
        logger.error(f'处理WebSocket断开连接时出错: {str(e)}')

@socketio.on('client_log')
def handle_client_log(data):
    """处理客户端日志消息"""
    try:
        level = data.get('level', 'info')
        message = data.get('message', '')
        log_data = data.get('data', {})
        timestamp = data.get('timestamp', '')
        
        # 构建日志消息
        log_message = f"[客户端日志] [{level.upper()}] {message}"
        if log_data:
            log_message += f" | 数据: {log_data}"
        if timestamp:
            log_message += f" | 时间: {timestamp}"
        
        # 根据日志级别输出到服务器终端
        if level == 'error':
            logger.error(log_message)
        elif level == 'warning':
            logger.warning(log_message)
        elif level == 'debug':
            logger.debug(log_message)
        else:
            logger.info(log_message)
            
    except Exception as e:
        logger.error(f'处理客户端日志时出错: {str(e)}')

@socketio.on_error()
def error_handler(e):
    """处理WebSocket错误"""
    try:
        logger.error(f'WebSocket错误: {str(e)}')
    except Exception as error:
        print(f'处理WebSocket错误时出错: {str(error)}')

@socketio.on('connect_error')
def handle_connect_error(data):
    """处理连接错误"""
    try:
        logger.error(f'WebSocket连接错误: {data}')
        logger.system(f'WebSocket连接错误: {data}')
    except Exception as e:
        logger.error(f'处理WebSocket连接错误时出错: {str(e)}')

@socketio.on('ping')
def handle_ping():
    """处理心跳ping"""
    try:
        logger.debug('收到WebSocket心跳ping')
        emit('pong', {'timestamp': time.time()})
    except Exception as e:
        logger.error(f'处理WebSocket ping时出错: {str(e)}')

@socketio.on('pong')
def handle_pong():
    """处理心跳pong"""
    try:
        logger.debug('收到WebSocket心跳pong')
    except Exception as e:
        logger.error(f'处理WebSocket pong时出错: {str(e)}')

@socketio.on('heartbeat_test')
def handle_heartbeat_test(data):
    """处理心跳测试"""
    try:
        logger.debug(f'收到心跳测试: {data}')
        # 回复心跳确认
        emit('heartbeat_response', {
            'timestamp': data.get('timestamp'), 
            'server_time': time.time(),
            'status': 'ok'
        })
    except Exception as e:
        logger.error(f'处理心跳测试失败: {e}')
        # 发送错误响应
        emit('heartbeat_response', {
            'timestamp': data.get('timestamp') if data else None,
            'server_time': time.time(),
            'status': 'error',
            'error': str(e)
        })

@socketio.on('heartbeat_ack')
def handle_heartbeat_ack(data):
    """处理心跳确认"""
    try:
        logger.debug(f'收到心跳确认: {data}')
        # 可以在这里记录连接状态
    except Exception as e:
        logger.error(f'处理心跳确认时出错: {str(e)}')

def start_websocket_heartbeat():
    """启动WebSocket心跳线程"""
    def heartbeat_loop():
        while True:
            try:
                # 每10秒发送一次心跳
                # 使用socketio的emit方法，但需要确保在正确的上下文中
                with app.app_context():
                    socketio.emit('server_heartbeat', {
                        'timestamp': time.time(),
                        'message': 'Server heartbeat'
                    })
                time.sleep(10)
            except Exception as e:
                logger.error(f'WebSocket心跳发送失败: {e}')
                time.sleep(5)
    
    # 暂时禁用WebSocket心跳线程，避免500错误
    # import threading
    # heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    # heartbeat_thread.start()
    # logger.info('WebSocket心跳线程已启动')
    logger.info('WebSocket心跳线程已禁用，避免500错误')

if __name__ == '__main__':
    # 初始化GPU管理器
    gpu_manager = GPUManager()
    logger.system("GPU管理器初始化成功")
    
    # 初始化文件管理器
    file_manager = FileManager()
    logger.system("文件管理器初始化成功")
    
    # 确保模型目录存在
    config.ensure_model_directory()
    logger.system(f"模型存储路径: {config.MODEL_BASE_PATH}")
    
    # 初始化优化系统
    try:
        optimized_whisper_system = get_optimized_system(socketio)
        optimized_whisper_system.start_system()
        
        # 验证系统启动状态
        if optimized_whisper_system.running and optimized_whisper_system.batch_scheduler.running:
            logger.system("优化系统初始化成功")
            logger.system("调度器已启动并运行正常")
        else:
            logger.error("优化系统启动失败：系统或调度器未运行")
            optimized_whisper_system = None
            
    except Exception as e:
        logger.error(f"优化系统初始化失败: {str(e)}")
        optimized_whisper_system = None
    
    # 检查优化系统状态
    if optimized_whisper_system is None:
        logger.error("优化系统初始化失败，程序无法继续运行")
        sys.exit(1)
    
    # 移除了旧的task_processor依赖函数设置
    
    # 启动应用
    logger.system("启动Whisper音频转录系统")
    logger.system(f"服务器地址: http://{config.HOST}:{config.PORT}")
    logger.system(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")  
    logger.system("应用已启动并准备就绪")
    
    # 添加WebSocket日志处理器
    websocket_handler = WebSocketHandler(socketio)
    logger.addHandler(websocket_handler)
    
    # 启动WebSocket心跳线程
    start_websocket_heartbeat()
    
    try:
        # 配置SocketIO运行参数
        socketio.run(
            app, 
            host=config.HOST, 
            port=config.PORT, 
            debug=config.DEBUG,
            use_reloader=False,  # 禁用自动重载，避免重复启动
            log_output=False,  # 禁用默认日志输出
            allow_unsafe_werkzeug=True  # 允许不安全的Werkzeug版本
        )
    except KeyboardInterrupt:
        logger.system("接收到中断信号，正在优雅关闭...")
        if optimized_whisper_system:
            optimized_whisper_system.shutdown()
        print("\n程序已收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"应用运行时发生错误: {str(e)}")
        raise
