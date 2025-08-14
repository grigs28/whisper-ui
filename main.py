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

from flask import Flask, render_template, request, jsonify, send_file, abort
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

class ProgressCapture:
    """捕获tqdm进度条输出并通过WebSocket发送"""
    def __init__(self, task_id=None, model_name=None):
        self.task_id = task_id
        self.model_name = model_name
        self.buffer = ""
        self.download_started = False
        
    def write(self, text):
        if text.strip():
            # 检查是否是tqdm进度条输出
            if '%' in text and ('|' in text or 'MB' in text or 'B/s' in text):
                # 如果是第一次检测到下载，发送开始信号
                if not self.download_started and self.task_id:
                    self.download_started = True
                    socketio.emit('download_progress', {
                        'task_id': self.task_id,
                        'progress': 0,
                        'message': '开始下载模型...',
                        'model_name': self.model_name,
                        'status': 'started'
                    })
                    logger.info(f"开始下载模型: {self.model_name}")
                
                # 提取进度信息
                try:
                    # 查找百分比
                    import re
                    percent_match = re.search(r'(\d+)%', text)
                    if percent_match:
                        percent = int(percent_match.group(1))
                        # 通过WebSocket发送进度更新
                        if self.task_id:
                            socketio.emit('download_progress', {
                                'task_id': self.task_id,
                                'progress': percent,
                                'message': f'模型下载进度: {percent}%',
                                'model_name': self.model_name,
                                'status': 'downloading'
                            })
                        logger.info(f"模型下载进度: {percent}%")
                except:
                    pass
        return len(text)
    
    def flush(self):
        pass

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# 确保必要的目录存在
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

# 支持的语言列表（10种常用语言）
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

# 支持的Whisper模型
WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3', 'turbo']

# GPU信息缓存
gpu_info_cache = {}
last_gpu_info_time = 0
GPU_INFO_CACHE_DURATION = 30  # 缓存30秒

# 任务队列
task_queue = []
task_lock = threading.Lock()

# 当前运行的任务
running_tasks = {}

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

def get_gpu_info():
    """获取GPU信息"""
    global gpu_info_cache, last_gpu_info_time
    
    # 检查缓存
    current_time = time.time()
    if current_time - last_gpu_info_time < GPU_INFO_CACHE_DURATION:
        return gpu_info_cache
    
    gpu_info = {
        'success': False,
        'error': '未检测到GPU',
        'memory': None,
        'temperature': None,
        'gpus': [],
        'best_gpu': None
    }
    
    try:
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            if device_count > 0:
                gpus = []
                best_gpu_id = 0
                max_free_memory = 0
                
                # 获取所有GPU的信息
                for i in range(device_count):
                    gpu_name = torch.cuda.get_device_name(i)
                    memory_info = torch.cuda.mem_get_info(i)
                    memory_total = memory_info[1]  # 总内存
                    memory_free = memory_info[0]   # 空闲内存
                    memory_used = memory_total - memory_free  # 已使用内存
                    
                    gpu_data = {
                        'id': i,
                        'name': gpu_name,
                        'memory': {
                            'total': memory_total,
                            'used': memory_used,
                            'free': memory_free
                        }
                    }
                    gpus.append(gpu_data)
                    
                    # 找到空闲内存最多的GPU
                    if memory_free > max_free_memory:
                        max_free_memory = memory_free
                        best_gpu_id = i
                
                # 获取主GPU（第一个）的信息用于兼容性
                main_gpu = gpus[0]
                
                # 获取温度（如果可用）
                temperature = None
                try:
                    # 注意：PyTorch本身不提供温度信息，这里模拟
                    # 实际应用中可能需要使用nvidia-smi等工具
                    temperature = 65  # 模拟温度
                except:
                    pass
                
                gpu_info = {
                    'success': True,
                    'device_count': device_count,
                    'device_name': main_gpu['name'],
                    'memory': main_gpu['memory'],
                    'temperature': temperature,
                    'gpus': gpus,
                    'best_gpu': best_gpu_id
                }
        else:
            gpu_info['error'] = 'CUDA不可用'
            
    except Exception as e:
        logger.error(f"获取GPU信息时出错: {str(e)}")
        gpu_info['error'] = str(e)
    
    # 更新缓存
    gpu_info_cache = gpu_info
    last_gpu_info_time = current_time
    
    return gpu_info

def get_available_gpus():
    """获取可用的GPU列表，包含详细信息"""
    gpus = []
    try:
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            for i in range(device_count):
                gpu_name = torch.cuda.get_device_name(i)
                memory_info = torch.cuda.mem_get_info(i)
                memory_total = memory_info[1]
                memory_free = memory_info[0]
                
                gpus.append({
                    'id': i,
                    'name': gpu_name,
                    'memory_total': memory_total,
                    'memory_free': memory_free,
                    'memory_used': memory_total - memory_free
                })
    except Exception as e:
        logger.error(f"获取GPU列表失败: {str(e)}")
    
    return gpus

def get_uploaded_files():
    """获取上传的文件列表"""
    files = []
    if os.path.exists(config.UPLOAD_FOLDER):
        for filename in os.listdir(config.UPLOAD_FOLDER):
            filepath = os.path.join(config.UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime)
                })
    return sorted(files, key=lambda f: f['modified'], reverse=True)

def get_output_files():
    """获取输出的文件列表"""
    files = []
    if os.path.exists(config.OUTPUT_FOLDER):
        for filename in os.listdir(config.OUTPUT_FOLDER):
            filepath = os.path.join(config.OUTPUT_FOLDER, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime)
                })
    return sorted(files, key=lambda f: f['modified'], reverse=True)

def cleanup_old_files():
    """清理超过30天的文件"""
    cutoff_date = datetime.now() - timedelta(days=30)
    
    # 清理上传文件夹
    if os.path.exists(config.UPLOAD_FOLDER):
        for filename in os.listdir(config.UPLOAD_FOLDER):
            filepath = os.path.join(config.UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                modified_date = datetime.fromtimestamp(stat.st_mtime)
                if modified_date < cutoff_date:
                    try:
                        os.remove(filepath)
                        logger.info(f"已清理过期文件: {filename}")
                    except Exception as e:
                        logger.error(f"清理文件失败 {filename}: {str(e)}")
    
    # 清理输出文件夹
    if os.path.exists(config.OUTPUT_FOLDER):
        for filename in os.listdir(config.OUTPUT_FOLDER):
            filepath = os.path.join(config.OUTPUT_FOLDER, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                modified_date = datetime.fromtimestamp(stat.st_mtime)
                if modified_date < cutoff_date:
                    try:
                        os.remove(filepath)
                        logger.info(f"已清理过期输出文件: {filename}")
                    except Exception as e:
                        logger.error(f"清理输出文件失败 {filename}: {str(e)}")

def transcribe_audio(file_path, model_name, language, gpu_ids, task_id=None, output_format='json'):
    """执行音频转录"""
    try:
        # 构建设备字符串
        if gpu_ids and len(gpu_ids) > 0:
            device = f"cuda:{gpu_ids[0]}"
        else:
            device = "cpu"
        
        # 加载模型
        logger.info(f"加载模型 {model_name} 到 {device}")
        
        # 创建进度捕获器
        progress_capture = ProgressCapture(task_id, model_name)
        
        # 设置模型下载路径
        model_path = config.get_model_path(model_name)
        os.environ['WHISPER_CACHE_DIR'] = config.MODEL_BASE_PATH
        
        # 在GPU环境下使用FP16精度，CPU环境下使用FP32
        if device.startswith('cuda'):
            # 使用torch.autocast来实现FP16推理，而不是直接转换模型
            with redirect_stderr(progress_capture):
                model = whisper.load_model(model_name, device=device, download_root=model_path)
            logger.info(f"GPU环境下将使用FP16自动混合精度")
        else:
            with redirect_stderr(progress_capture):
                model = whisper.load_model(model_name, device=device, download_root=model_path)
            logger.info(f"CPU环境下使用FP32精度")
        
        logger.info(f"模型已从 {model_path} 加载")
        
        # 处理语言参数
        transcribe_language = None
        if language == 'auto':
            # 自动检测时，不传递language参数，让whisper自动检测
            transcribe_language = None
            logger.info(f"使用自动语言检测转录文件: {file_path}")
        else:
            # 指定语言时，传递language参数
            transcribe_language = language
            logger.info(f"使用指定语言 {language} 转录文件: {file_path}")
        
        # 执行转录
        if device.startswith('cuda'):
            # 在GPU环境下使用FP16自动混合精度
            with torch.autocast(device_type='cuda', dtype=torch.float16):
                if transcribe_language:
                    # 对于中文，明确指定使用简体中文
                    if transcribe_language == 'zh':
                        result = model.transcribe(file_path, language='zh-CN', initial_prompt="以下是普通话句子。", task='transcribe')
                    else:
                        result = model.transcribe(file_path, language=transcribe_language)
                else:
                    result = model.transcribe(file_path)
        else:
            # CPU环境下正常执行
            if transcribe_language:
                # 对于中文，明确指定使用简体中文
                if transcribe_language == 'zh':
                    result = model.transcribe(file_path, language='zh-CN', initial_prompt="以下是普通话句子。", task='transcribe')
                else:
                    result = model.transcribe(file_path, language=transcribe_language)
            else:
                result = model.transcribe(file_path)
        
        # 对于中文转录结果，进行繁体到简体的转换
        if (transcribe_language == 'zh' or result.get('language') == 'zh') and result.get('text'):
            try:
                # 初始化OpenCC转换器（繁体到简体）
                converter = opencc.OpenCC('t2s')  # Traditional to Simplified
                # 转换主文本
                result['text'] = converter.convert(result['text'])
                # 转换分段文本
                if 'segments' in result:
                    for segment in result['segments']:
                        if 'text' in segment:
                            segment['text'] = converter.convert(segment['text'])
                logger.info("已将繁体中文转换为简体中文")
            except Exception as e:
                logger.warning(f"繁体到简体转换失败: {str(e)}，保持原文本")
        
        # 保存结果
        base_filename = Path(file_path).stem
        
        # 根据输出格式确定文件扩展名
        if output_format == 'txt':
            extension = '.txt'
        elif output_format == 'js':
            extension = '.js'
        else:
            extension = '.json'
        
        # 生成输出文件名，如果文件已存在则添加时间戳
        output_filename = f"{base_filename}{extension}"
        output_path = os.path.join(config.OUTPUT_FOLDER, output_filename)
        
        # 检查文件是否存在，如果存在则添加时间戳
        if os.path.exists(output_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"{base_filename}_{timestamp}{extension}"
            output_path = os.path.join(config.OUTPUT_FOLDER, output_filename)
        
        # 根据格式保存文件
        if output_format == 'txt':
            # 保存为纯文本格式
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result['text'])
        elif output_format == 'js':
            # 保存为JavaScript格式
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"// 转录结果\n")
                f.write(f"// 文件: {Path(file_path).name}\n")
                f.write(f"// 模型: {model_name}\n")
                f.write(f"// 语言: {result.get('language', 'unknown')}\n")
                f.write(f"// 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"const transcriptionResult = {json.dumps(result, ensure_ascii=False, indent=2)};\n\n")
                f.write(f"// 转录文本\n")
                f.write(f"const transcriptionText = {json.dumps(result['text'], ensure_ascii=False)};\n")
        else:
            # 保存为JSON格式（默认）
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        
        detected_language = result.get('language', 'unknown')
        logger.info(f"转录完成: {output_filename}, 检测到的语言: {detected_language}")
        return {
            'success': True,
            'output_file': output_filename,
            'result': result
        }
        
    except Exception as e:
        logger.error(f"转录失败 {file_path}: {str(e)}")
        if task_id:
            logger.transcription_failed("转录失败", task_id, str(e))
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/')
def index():
    """主页路由"""
    # 获取GPU信息
    gpus = get_available_gpus()
    gpu_info = get_gpu_info()
    
    # 确定默认GPU选择
    default_gpu_id = None
    if gpus and gpu_info.get('success'):
        # 选择空闲内存最多的GPU
        best_gpu_id = gpu_info.get('best_gpu')
        if best_gpu_id is not None:
            default_gpu_id = best_gpu_id
    
    # 获取文件列表
    uploaded_files = get_uploaded_files()
    output_files = get_output_files()
    
    # 获取模型内存需求（根据指南计算的精确值）
    model_memory_requirements = {
        'tiny': '~1GB',
        'base': '~1GB',
        'small': '~2GB',
        'medium': '~5GB',
        'large': '~10GB',
        'large-v2': '~10GB',
        'large-v3': '~10GB',
        'turbo': '~6GB'
    }
    
    return render_template(
        'index.html',
        gpus=gpus,
        default_gpu_id=default_gpu_id,
        uploaded_files=uploaded_files,
        output_files=output_files,
        languages=SUPPORTED_LANGUAGES,
        whisper_models=WHISPER_MODELS,
        model_memory_requirements=model_memory_requirements
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
        
        # 为每个文件创建单独的任务
        with task_lock:
            for filename in files:
                task_id = str(uuid.uuid4())
                task_queue.append({
                    'id': task_id,
                    'files': [filename],  # 每个任务只处理一个文件
                    'filename': filename,  # 添加文件名字段便于显示
                    'model': model,
                    'language': language,
                    'gpus': gpus,
                    'output_format': output_format,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat(),
                    'progress': 0,
                    'start_time': None,
                    'end_time': None
                })
                task_ids.append(task_id)
        
        # 为每个任务启动后台线程
        for task_id in task_ids:
            thread = threading.Thread(target=process_transcription_task, args=(task_id,))
            thread.daemon = True
            thread.start()
        
        logger.info(f"转录任务已提交: {len(task_ids)}个文件")
        return jsonify({
            'success': True,
            'task_ids': task_ids,
            'count': len(task_ids)
        })
        
    except Exception as e:
        logger.error(f"启动转录任务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def process_transcription_task(task_id):
    """处理转录任务"""
    global task_queue, running_tasks
    
    try:
        # 从队列中获取任务
        task = None
        with task_lock:
            for i, t in enumerate(task_queue):
                if t['id'] == task_id:
                    task = t
                    task['status'] = 'processing'
                    task['progress'] = 0
                    running_tasks[task_id] = task
                    break
        
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return
        
        # 记录转录任务开始
        task['start_time'] = datetime.now().isoformat()
        logger.transcription_started("转录任务开始处理", task_id)
        logger.processing("转录任务正在处理中", task_id)
        # 发送任务开始通知
        socketio.emit('task_update', {
            'id': task_id,
            'status': 'processing',
            'progress': 0,
            'message': '开始处理...',
            'files': task['files'],
            'model': task['model'],
            'language': task['language'],
            'start_time': task['start_time']
        })
        # 处理每个文件
        total_files = len(task['files'])
        for i, filename in enumerate(task['files']):
            try:
                # 更新进度
                progress = int(((i + 1) / total_files) * 100)
                task['progress'] = progress
                
                # 发送进度更新
                socketio.emit('task_update', {
                    'id': task_id,
                    'status': 'processing',
                    'progress': progress,
                    'message': f'处理文件 {i+1}/{total_files}: {filename}',
                    'files': task['files']
                })
                
                # 构建文件路径
                filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                
                # 执行转录
                result = transcribe_audio(filepath, task['model'], task['language'], task['gpus'], task_id, task.get('output_format', 'json'))
                
                if not result['success']:
                    task['status'] = 'failed'
                    task['error'] = result['error']
                    socketio.emit('task_update', {
                        'id': task_id,
                        'status': 'failed',
                        'progress': progress,
                        'message': f'转录失败: {result["error"]}',
                        'files': task['files']
                    })
                    return
                    
            except Exception as e:
                logger.error(f"处理文件失败 {filename}: {str(e)}")
                task['status'] = 'failed'
                task['error'] = str(e)
                socketio.emit('task_update', {
                    'id': task_id,
                    'status': 'failed',
                    'progress': progress,
                    'message': f'处理文件失败: {str(e)}',
                    'files': task['files']
                })
                return
        
        # 完成任务
        task['status'] = 'completed'
        task['progress'] = 100
        task['end_time'] = datetime.now().isoformat()
        socketio.emit('task_update', {
            'id': task_id,
            'status': 'completed',
            'progress': 100,
            'message': '转录完成',
            'files': task['files'],
            'model': task['model'],
            'language': task['language'],
            'start_time': task['start_time'],
            'end_time': task['end_time']
        })
        
        # 从运行任务中移除
        with task_lock:
            if task_id in running_tasks:
                del running_tasks[task_id]
            # 从任务队列中移除已完成的任务
            for i, t in enumerate(task_queue):
                if t['id'] == task_id:
                    del task_queue[i]
                    break
        
        logger.info(f"转录任务完成: {task_id}")
        
    except Exception as e:
        logger.error(f"处理任务失败 {task_id}: {str(e)}")
        task['status'] = 'failed'
        task['error'] = str(e)
        socketio.emit('task_update', {
            'id': task_id,
            'status': 'failed',
            'progress': 0,
            'message': f'任务处理失败: {str(e)}',
            'files': task.get('files', []) if 'task' in locals() else []
        })

@app.route('/gpu_info')
def get_gpu_info_endpoint():
    """获取GPU信息接口"""
    gpu_info = get_gpu_info()
    return jsonify(gpu_info)

@app.route('/queue_state')
def get_queue_state():
    """获取队列状态"""
    with task_lock:
        # 合并排队任务和正在运行的任务
        all_tasks = []
        
        # 添加排队中的任务（pending状态）
        for task in task_queue:
            if task['status'] == 'pending':
                all_tasks.append(task)
        
        # 添加正在处理的任务
        for task_id, task in running_tasks.items():
            all_tasks.append(task)
        
        return jsonify({
            'success': True,
            'items': all_tasks
        })

@app.route('/readme')
def get_readme():
    """获取README内容"""
    try:
        readme_path = os.path.join('docs', 'DEVELOPMENT_PROMPT.md')
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
        files = get_uploaded_files()
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
        files = get_output_files()
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
        # 从 Markdown 文件获取版本历史
        version_data = parse_version_md()
        if version_data:
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

@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    logger.client_connected('客户端已连接')
    logger.system('客户端已连接')

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    logger.client_disconnected('客户端已断开连接')
    logger.system('客户端已断开连接')

if __name__ == '__main__':
    # 启动时清理旧文件
    cleanup_old_files()
    
    # 确保模型目录存在
    config.ensure_model_directory()
    logger.system(f"模型存储路径: {config.MODEL_BASE_PATH}")
    
    # 启动应用
    logger.system("启动Whisper音频转录系统")
    logger.system(f"服务器地址: http://{config.HOST}:{config.PORT}")
    logger.system(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")  
    logger.system("应用已启动并准备就绪")
    
    # 添加WebSocket日志处理器
    websocket_handler = WebSocketHandler(socketio)
    logger.addHandler(websocket_handler)
    
    try:
        socketio.run(app, host=config.HOST, port=config.PORT, debug=config.DEBUG)
    except KeyboardInterrupt:
        logger.system("接收到中断信号，正在优雅关闭...")
        print("\n程序已收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"应用运行时发生错误: {str(e)}")
        raise
