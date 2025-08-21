# Whisper显存管理和任务调度完整解决方案

## 1. 方案概述

本方案旨在为Whisper音频转录系统设计一套完整的显存管理和任务调度机制，通过精细化的资源控制和智能调度算法，实现高效、稳定的多任务并发处理。

### 1.1 核心目标
- 实现精确的GPU显存分配和释放管理
- 提供智能的任务调度和队列管理
- 支持实时显存监控和动态调整
- 确保系统稳定性和资源利用率最大化

### 1.2 技术架构
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   任务调度器    │────│   显存管理器    │────│   转录执行器    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   队列管理      │    │   预留计数器    │    │   模型加载      │
│   轮询线程      │    │   分配算法      │    │   音频处理      │
│   状态转换      │    │   实时监控      │    │   资源释放      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 2. 任务调度模块设计

### 2.1 轮询调度器

#### 2.1.1 核心功能
- 启动独立的轮询线程，持续监控任务队列
- 按优先级和时间顺序处理待处理任务
- 与显存管理器协调，确保资源可用性

#### 2.1.2 实现逻辑
```python
class TaskScheduler:
    def __init__(self):
        self.polling_thread = None
        self.is_running = False
        self.poll_interval = 1.0  # 轮询间隔(秒)
        
    def start_polling(self):
        """启动轮询线程"""
        if not self.is_running:
            self.is_running = True
            self.polling_thread = threading.Thread(target=self._polling_loop)
            self.polling_thread.daemon = True
            self.polling_thread.start()
            
    def _polling_loop(self):
        """轮询主循环"""
        while self.is_running:
            try:
                self._process_pending_tasks()
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"轮询调度器错误: {e}")
                
    def _process_pending_tasks(self):
        """处理待处理任务"""
        with task_lock:
            pending_tasks = [t for t in task_queue if t['status'] == 'pending']
            
        for task in pending_tasks:
            if self._can_schedule_task(task):
                self._schedule_task(task)
```

### 2.2 任务状态管理

#### 2.2.1 状态定义
- `pending`: 等待调度
- `loading`: 模型加载中
- `processing`: 转录处理中
- `completed`: 已完成
- `failed`: 处理失败

#### 2.2.2 状态转换流程
```
pending → (显存申请成功) → loading → processing → completed/failed
   ↓
   └─ (显存申请失败) → pending (重新排队)
```

## 3. 显存管理模块设计

### 3.1 显存预留计数器

#### 3.1.1 数据结构
```python
class MemoryManager:
    def __init__(self):
        self.total_memory = {}      # 总显存 {gpu_id: total_gb}
        self.reserved_memory = {}   # 预留显存 {gpu_id: reserved_gb}
        self.allocated_memory = {}  # 已分配显存 {gpu_id: allocated_gb}
        self.safety_factor = 0.8    # 安全系数
        self.memory_lock = threading.Lock()
        
    @property
    def available_memory(self):
        """计算可分配显存"""
        available = {}
        for gpu_id in self.total_memory:
            total = self.total_memory[gpu_id]
            reserved = self.reserved_memory.get(gpu_id, 0)
            allocated = self.allocated_memory.get(gpu_id, 0)
            
            # 可分配显存 = (总显存 - 预留显存) * 安全系数
            allocatable = (total - reserved) * self.safety_factor
            # 可用显存 = 可分配显存 - 已分配显存
            available[gpu_id] = max(0, allocatable - allocated)
            
        return available
```

### 3.2 显存分配算法

#### 3.2.1 申请流程
```python
def request_memory(self, gpu_id, required_memory, task_id):
    """申请显存"""
    with self.memory_lock:
        available = self.available_memory.get(gpu_id, 0)
        
        if available >= required_memory:
            # 分配成功
            self.allocated_memory[gpu_id] = \
                self.allocated_memory.get(gpu_id, 0) + required_memory
            
            # 记录分配信息
            self.allocations[task_id] = {
                'gpu_id': gpu_id,
                'memory': required_memory,
                'timestamp': time.time()
            }
            
            logger.info(f"显存分配成功: GPU{gpu_id} {required_memory}GB")
            return True
        else:
            logger.warning(f"显存不足: GPU{gpu_id} 需要{required_memory}GB, 可用{available}GB")
            return False
```

#### 3.2.2 释放流程
```python
def release_memory(self, task_id):
    """释放显存"""
    with self.memory_lock:
        if task_id in self.allocations:
            allocation = self.allocations[task_id]
            gpu_id = allocation['gpu_id']
            memory = allocation['memory']
            
            # 释放显存
            self.allocated_memory[gpu_id] = \
                max(0, self.allocated_memory.get(gpu_id, 0) - memory)
            
            # 清除分配记录
            del self.allocations[task_id]
            
            logger.info(f"显存释放成功: GPU{gpu_id} {memory}GB")
            
            # 清理GPU缓存
            self._clear_gpu_cache(gpu_id)
```

### 3.3 实时监控界面

#### 3.3.1 监控数据结构
```python
def get_memory_status(self):
    """获取显存状态"""
    status = {}
    
    for gpu_id in self.total_memory:
        total = self.total_memory[gpu_id]
        reserved = self.reserved_memory.get(gpu_id, 0)
        allocated = self.allocated_memory.get(gpu_id, 0)
        allocatable = (total - reserved) * self.safety_factor
        available = max(0, allocatable - allocated)
        
        status[gpu_id] = {
            'total': f"{total:.1f}GB",
            'allocatable': f"{allocatable:.1f}GB",
            'allocated': f"{allocated:.1f}GB",
            'reserved': f"{reserved:.1f}GB",
            'available': f"{available:.1f}GB",
            'usage_percent': (allocated / allocatable * 100) if allocatable > 0 else 0
        }
    
    return status
```

#### 3.3.2 前端显示组件
```html
<div class="memory-monitor">
    <h4>GPU显存监控</h4>
    <div id="gpu-memory-status">
        <!-- 动态生成GPU状态卡片 -->
    </div>
</div>

<script>
function updateMemoryStatus() {
    fetch('/api/memory_status')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('gpu-memory-status');
            container.innerHTML = '';
            
            Object.entries(data).forEach(([gpuId, status]) => {
                const card = createMemoryCard(gpuId, status);
                container.appendChild(card);
            });
        });
}

function createMemoryCard(gpuId, status) {
    return `
        <div class="gpu-card">
            <h5>GPU ${gpuId}</h5>
            <div class="memory-info">
                <div>总显存: ${status.total}</div>
                <div>可分配: ${status.allocatable}</div>
                <div>已分配: ${status.allocated}</div>
                <div>预留: ${status.reserved}</div>
                <div>可用: ${status.available}</div>
            </div>
            <div class="progress">
                <div class="progress-bar" style="width: ${status.usage_percent}%"></div>
            </div>
        </div>
    `;
}

// 每5秒更新一次
setInterval(updateMemoryStatus, 5000);
</script>
```

## 4. 转录执行模块设计

### 4.1 执行流程控制

#### 4.1.1 模型加载阶段
```python
def load_model_stage(self, task_id, model_name, gpu_id):
    """模型加载阶段"""
    try:
        # 更新任务状态
        self.update_task_status(task_id, 'loading')
        
        # 记录加载开始时间
        start_time = time.time()
        logger.info(f"开始加载模型: {model_name} -> GPU{gpu_id}")
        
        # 加载Whisper模型
        model = whisper.load_model(model_name, device=f"cuda:{gpu_id}")
        
        # 记录加载完成时间
        load_time = time.time() - start_time
        logger.info(f"模型加载完成: {model_name}, 耗时: {load_time:.2f}秒")
        
        return model
        
    except Exception as e:
        logger.error(f"模型加载失败: {e}")
        self.update_task_status(task_id, 'failed')
        raise
```

#### 4.1.2 音频转录阶段
```python
def transcribe_stage(self, task_id, model, audio_files):
    """音频转录阶段"""
    try:
        # 更新任务状态
        self.update_task_status(task_id, 'processing')
        
        results = []
        total_files = len(audio_files)
        
        for i, audio_file in enumerate(audio_files):
            # 记录转录开始时间
            start_time = time.time()
            logger.info(f"开始转录音频: {audio_file}")
            
            # 执行转录
            result = model.transcribe(audio_file)
            
            # 记录转录完成时间
            transcribe_time = time.time() - start_time
            logger.info(f"音频转录完成: {audio_file}, 耗时: {transcribe_time:.2f}秒")
            
            results.append(result)
            
            # 更新进度
            progress = (i + 1) / total_files * 100
            self.update_task_progress(task_id, progress)
            
        return results
        
    except Exception as e:
        logger.error(f"音频转录失败: {e}")
        self.update_task_status(task_id, 'failed')
        raise
```

#### 4.1.3 资源释放阶段
```python
def cleanup_stage(self, task_id, gpu_id):
    """资源释放阶段"""
    try:
        # 释放显存分配
        memory_manager.release_memory(task_id)
        
        # 清理GPU缓存
        torch.cuda.empty_cache()
        if gpu_id is not None:
            with torch.cuda.device(gpu_id):
                torch.cuda.empty_cache()
        
        # 更新模型使用计数
        self.release_model_usage(task_id)
        
        logger.info(f"任务资源释放完成: {task_id}")
        
    except Exception as e:
        logger.error(f"资源释放失败: {e}")
```

## 5. 系统集成和优化

### 5.1 配置参数

#### 5.1.1 显存管理配置
```python
# config.py
class MemoryConfig:
    # 安全系数 (0.7-0.9)
    MEMORY_SAFETY_FACTOR = 0.8
    
    # 预留显存 (GB)
    RESERVED_MEMORY = {
        0: 2.0,  # GPU 0 预留2GB
        1: 1.5,  # GPU 1 预留1.5GB
    }
    
    # 模型显存需求 (GB)
    MODEL_MEMORY_REQUIREMENTS = {
        'tiny': 1.0,
        'base': 1.0,
        'small': 2.0,
        'medium': 5.0,
        'large': 10.0,
        'large-v2': 10.0,
        'large-v3': 10.0,
        'turbo': 6.0
    }
    
    # 推理额外显存系数
    INFERENCE_MEMORY_MULTIPLIER = 1.5
```

#### 5.1.2 调度器配置
```python
class SchedulerConfig:
    # 轮询间隔 (秒)
    POLL_INTERVAL = 1.0
    
    # 最大并发任务数
    MAX_CONCURRENT_TASKS = 4
    
    # 任务超时时间 (秒)
    TASK_TIMEOUT = 3600
    
    # 重试次数
    MAX_RETRIES = 3
    
    # 优先级权重
    PRIORITY_WEIGHTS = {
        'high': 3,
        'normal': 2,
        'low': 1
    }
```

### 5.2 性能优化策略

#### 5.2.1 模型预加载
```python
class ModelPreloader:
    def __init__(self):
        self.preloaded_models = {}
        
    def preload_common_models(self):
        """预加载常用模型"""
        common_models = ['base', 'small', 'medium']
        
        for model_name in common_models:
            if self._should_preload(model_name):
                self._preload_model(model_name)
                
    def _should_preload(self, model_name):
        """判断是否应该预加载模型"""
        # 检查显存是否充足
        required_memory = MODEL_MEMORY_REQUIREMENTS[model_name]
        available_memory = memory_manager.get_max_available_memory()
        
        return available_memory >= required_memory * 1.2
```

#### 5.2.2 智能GPU选择
```python
def select_optimal_gpu(self, model_name, task_priority='normal'):
    """智能选择最优GPU"""
    required_memory = self.calculate_required_memory(model_name)
    available_gpus = memory_manager.get_available_gpus(required_memory)
    
    if not available_gpus:
        return None
        
    # 按多个因素排序选择最优GPU
    scored_gpus = []
    
    for gpu_id in available_gpus:
        score = self._calculate_gpu_score(gpu_id, required_memory, task_priority)
        scored_gpus.append((gpu_id, score))
    
    # 选择得分最高的GPU
    scored_gpus.sort(key=lambda x: x[1], reverse=True)
    return scored_gpus[0][0]

def _calculate_gpu_score(self, gpu_id, required_memory, priority):
    """计算GPU得分"""
    gpu_info = memory_manager.get_gpu_info(gpu_id)
    
    # 可用显存比例 (40%权重)
    memory_ratio = gpu_info['available'] / gpu_info['total']
    memory_score = memory_ratio * 0.4
    
    # 当前负载 (30%权重)
    load_score = (1 - gpu_info['utilization']) * 0.3
    
    # 温度因素 (20%权重)
    temp_score = max(0, (85 - gpu_info['temperature']) / 85) * 0.2
    
    # 优先级加权 (10%权重)
    priority_score = PRIORITY_WEIGHTS.get(priority, 2) / 3 * 0.1
    
    return memory_score + load_score + temp_score + priority_score
```

### 5.3 错误处理和恢复

#### 5.3.1 异常处理机制
```python
class ErrorHandler:
    def __init__(self):
        self.retry_counts = {}
        self.max_retries = 3
        
    def handle_task_error(self, task_id, error, stage):
        """处理任务错误"""
        retry_count = self.retry_counts.get(task_id, 0)
        
        if retry_count < self.max_retries:
            # 尝试重试
            self.retry_counts[task_id] = retry_count + 1
            logger.warning(f"任务{task_id}在{stage}阶段失败，尝试第{retry_count + 1}次重试")
            
            # 清理资源后重新调度
            self._cleanup_failed_task(task_id)
            self._reschedule_task(task_id)
            
        else:
            # 超过重试次数，标记为失败
            logger.error(f"任务{task_id}重试{self.max_retries}次后仍然失败")
            self._mark_task_failed(task_id, error)
            
    def _cleanup_failed_task(self, task_id):
        """清理失败任务的资源"""
        try:
            # 释放显存
            memory_manager.release_memory(task_id)
            
            # 清理GPU缓存
            torch.cuda.empty_cache()
            
            # 更新任务状态
            task_manager.update_task_status(task_id, 'pending')
            
        except Exception as e:
            logger.error(f"清理失败任务资源时出错: {e}")
```

## 6. 部署和监控

### 6.1 系统部署

#### 6.1.1 环境要求
- Python 3.8+
- PyTorch 1.9+
- CUDA 11.0+
- 显存 >= 8GB (推荐16GB+)

#### 6.1.2 启动流程
```python
def initialize_system():
    """系统初始化"""
    # 1. 初始化显存管理器
    memory_manager.initialize()
    
    # 2. 启动任务调度器
    task_scheduler.start_polling()
    
    # 3. 预加载常用模型
    model_preloader.preload_common_models()
    
    # 4. 启动监控服务
    monitoring_service.start()
    
    logger.info("Whisper显存管理系统启动完成")
```

### 6.2 监控和告警

#### 6.2.1 关键指标监控
- GPU显存使用率
- 任务队列长度
- 平均处理时间
- 错误率和重试率
- 系统吞吐量

#### 6.2.2 告警规则
```python
class AlertManager:
    def __init__(self):
        self.alert_rules = {
            'high_memory_usage': {'threshold': 0.9, 'duration': 300},
            'long_queue': {'threshold': 10, 'duration': 600},
            'high_error_rate': {'threshold': 0.1, 'duration': 300},
        }
        
    def check_alerts(self):
        """检查告警条件"""
        # 检查显存使用率
        memory_usage = memory_manager.get_usage_ratio()
        if memory_usage > self.alert_rules['high_memory_usage']['threshold']:
            self.send_alert('high_memory_usage', f"显存使用率过高: {memory_usage:.1%}")
            
        # 检查队列长度
        queue_length = task_manager.get_queue_length()
        if queue_length > self.alert_rules['long_queue']['threshold']:
            self.send_alert('long_queue', f"任务队列过长: {queue_length}")
```

## 7. 总结

本方案提供了一套完整的Whisper显存管理和任务调度解决方案，具有以下特点：

### 7.1 核心优势
1. **精确的显存管理**: 通过预留计数器和分配算法，实现精确的显存控制
2. **智能任务调度**: 基于资源可用性和优先级的智能调度机制
3. **实时监控**: 提供详细的显存使用情况和系统状态监控
4. **高可靠性**: 完善的错误处理和恢复机制
5. **高性能**: 模型预加载和智能GPU选择优化

### 7.2 适用场景
- 多用户并发音频转录服务
- 大规模音频处理任务
- 资源受限的GPU环境
- 需要高可靠性的生产环境

### 7.3 扩展性
- 支持多GPU环境
- 可配置的调度策略
- 模块化设计便于扩展
- 标准化的API接口

通过实施本方案，可以显著提升Whisper系统的资源利用效率、处理能力和稳定性，为用户提供更好的音频转录服务体验。