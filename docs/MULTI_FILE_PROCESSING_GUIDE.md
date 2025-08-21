# 多文件处理指南

## 概述

本指南详细介绍Whisper音频转录系统中的多文件处理功能。系统支持同时上传和处理多个音频文件，大大提高了批量转录的效率。

## 核心功能

### 1. 多文件上传
- 支持同时选择和上传多个音频文件
- 支持拖拽上传方式
- 文件格式支持：MP3、WAV、FLAC等常见音频格式

### 2. 自动文件选择
- 开始转录时自动选择所有已上传的文件
- 无需手动勾选每个文件
- 提高批量处理效率

### 3. 并行处理
- 利用动态并发机制同时处理多个文件
- 智能分配GPU资源
- 实时监控处理进度

## 使用方法

### 1. 文件上传
在网页界面的"文件上传"区域：
- 点击"拖拽文件到这里或点击选择文件"区域
- 或者直接拖拽多个文件到指定区域
- 上传的文件会显示在"上传的文件"表格中

### 2. 开始批量转录
- 确保所有需要转录的文件都已上传
- 选择适当的转录参数（模型、语言、GPU）
- 点击"开始转录"按钮
- 系统会自动选择所有上传的文件进行转录

### 3. 监控处理进度
- 在右侧"系统日志"区域查看实时进度
- 任务队列会显示当前处理状态
- 转录完成后可在"转录结果"区域查看结果

## 技术实现

### 前端实现

```javascript
// transcriptionController.js 中的关键方法
/**
 * 开始转录
 */
async startTranscription() {
    // 获取选中的上传文件
    const selectedFiles = this.getSelectedFiles();
    
    // 如果没有选中任何文件，则自动选择所有上传的文件
    let filesToTranscribe = selectedFiles;
    if (filesToTranscribe.length === 0) {
        // 自动选择所有上传的文件
        filesToTranscribe = this.selectAllUploadedFiles();
        if (filesToTranscribe.length === 0) {
            showNotification('没有找到可转录的文件', 'warning');
            return;
        }
        showNotification('已自动选择所有上传的文件', 'info');
    }

    // 获取设置参数
    const settings = this.getSettings();
    
    // 构建转录请求数据
    const requestData = {
        files: filesToTranscribe,
        ...settings
    };

    // 发送转录请求到服务器
    const response = await fetch('/transcribe', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    });
}
```

### 后端实现

```python
# main.py 中的关键处理逻辑
@app.route('/transcribe', methods=['POST'])
def start_transcription():
    """开始转录任务"""
    try:
        data = request.get_json()
        files = data.get('files', [])
        model = data.get('model', config.DEFAULT_MODEL)
        language = data.get('language', config.DEFAULT_LANGUAGE)
        gpus = data.get('gpus', config.DEFAULT_GPU_IDS)
        
        if not files:
            return jsonify({'success': False, 'error': '没有选择文件'}), 400
        
        # 创建任务ID
        task_id = str(uuid.uuid4())
        
        # 添加到任务队列
        with task_lock:
            task_queue.append({
                'id': task_id,
                'files': files,
                'model': model,
                'language': language,
                'gpus': gpus,
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'progress': 0
            })
        
        # 启动后台任务
        thread = threading.Thread(target=process_transcription_task, args=(task_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id
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
        
        # 发送任务开始通知
        socketio.emit('task_update', {
            'id': task_id,
            'status': 'processing',
            'progress': 0,
            'message': '开始处理...'
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
                    'message': f'处理文件 {i+1}/{total_files}: {filename}'
                })
                
                # 构建文件路径
                filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                
                # 执行转录
                result = transcribe_audio(filepath, task['model'], task['language'], task['gpus'])
                
                if not result['success']:
                    task['status'] = 'failed'
                    task['error'] = result['error']
                    socketio.emit('task_update', {
                        'id': task_id,
                        'status': 'failed',
                        'progress': progress,
                        'message': f'转录失败: {result["error"]}'
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
                    'message': f'处理文件失败: {str(e)}'
                })
                return
        
        # 完成任务
        task['status'] = 'completed'
        task['progress'] = 100
        socketio.emit('task_update', {
            'id': task_id,
            'status': 'completed',
            'progress': 100,
            'message': '转录完成'
        })
        
        # 从运行任务中移除
        with task_lock:
            if task_id in running_tasks:
                del running_tasks[task_id]
        
        logger.info(f"转录任务完成: {task_id}")
        
    except Exception as e:
        logger.error(f"处理任务失败 {task_id}: {str(e)}")
        task['status'] = 'failed'
        task['error'] = str(e)
        socketio.emit('task_update', {
            'id': task_id,
            'status': 'failed',
            'progress': 0,
            'message': f'任务处理失败: {str(e)}'
        })
```

## 支持的语言

系统支持以下10种常用语言的转录：

| 语言代码 | 语言名称 |
|---------|---------|
| zh | 中文 |
| en | 英语 |
| ja | 日语 |
| ko | 韩语 |
| fr | 法语 |
| de | 德语 |
| es | 西班牙语 |
| ru | 俄语 |
| ar | 阿拉伯语 |
| pt | 葡萄牙语 |

## 性能优化建议

### 1. 文件管理
- 合理组织上传文件，避免单次上传过多文件导致内存压力
- 定期清理不需要的上传文件和转录结果

### 2. 并发控制
- 根据系统资源合理设置并发数
- 对于大量文件，考虑分批处理

### 3. 资源利用
- 选择合适的Whisper模型大小
- 合理分配GPU资源，避免资源争抢

## 故障排除

### 常见问题

1. **文件无法上传**
   - 检查文件格式是否支持
   - 确认文件大小是否超过限制
   - 查看浏览器控制台是否有错误信息

2. **批量转录失败**
   - 检查单个文件是否能正常转录
   - 确认GPU资源是否充足
   - 查看系统日志获取详细错误信息

3. **进度显示异常**
   - 确认WebSocket连接是否正常
   - 检查网络连接状况
   - 刷新页面重新获取状态

## API接口

### 批量转录接口

```http
POST /transcribe
Content-Type: application/json

{
  "files": ["file1.mp3", "file2.wav", "file3.flac"],
  "model": "base",
  "language": "zh",
  "gpus": [0]
}
```

### 响应示例

```json
{
  "success": true,
  "task_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

## 最佳实践

### 1. 批量处理流程
1. 准备待转录的音频文件
2. 上传所有文件到系统
3. 设置转录参数（模型、语言等）
4. 点击"开始转录"按钮
5. 监控处理进度直到完成
6. 下载转录结果文件

### 2. 资源规划
- 根据文件数量和大小预估所需资源
- 对于大量文件，建议分批次处理
- 定期监控系统资源使用情况

### 3. 结果管理
- 转录完成后及时下载结果文件
- 定期清理临时文件和旧结果
- 建立合理的文件命名规范

## 总结

多文件处理功能使Whisper音频转录系统能够高效地处理批量音频转录任务。通过自动文件选择、并行处理和实时监控等功能，用户可以轻松地对多个音频文件进行批量转录，大大提高工作效率。
