# Whisper多线程并发处理优化方案

## 1. 方案概述

本方案针对Whisper音频转录系统的多线程并发处理进行全面优化，通过智能队列管理、显存预估池、批量任务调度等机制，实现高效的GPU资源利用和任务处理能力。

### 1.1 核心优化目标
- 实现精确的显存预估和动态分配
- 优化任务队列管理和状态转换
- 提升GPU资源利用率和并发处理能力
- 减少任务等待时间和系统空闲时间

### 1.2 系统架构图
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   队列管理器    │────│  显存预估池     │────│  批量调度器     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ 处理中/待处理   │    │ 模型显存校准    │    │ 批量任务执行    │
│ 失败任务重排    │    │ 动态预估更新    │    │ 资源释放管理    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 2. 队列管理优化

### 2.1 任务状态定义

```python
class TaskStatus:
    PENDING = "pending"        # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 处理失败
    RETRYING = "retrying"      # 重试中
```

### 2.2 智能队列管理器

```python
class IntelligentQueueManager:
    def __init__(self):
        self.pending_queue = []     # 待处理队列
        self.processing_queue = []  # 处理中队列
        self.failed_queue = []      # 失败任务队列
        self.queue_lock = threading.Lock()
        self.priority_weights = {
            'high': 3,
            'normal': 2, 
            'low': 1
        }
        
    def add_task(self, task):
        """添加新任务到队列"""
        with self.queue_lock:
            task['status'] = TaskStatus.PENDING
            task['created_time'] = time.time()
            task['retry_count'] = 0
            
            # 按优先级和创建时间排序插入
            self._insert_by_priority(self.pending_queue, task)
            
    def move_to_processing(self, task_id):
        """将任务移动到处理中队列"""
        with self.queue_lock:
            task = self._find_and_remove(self.pending_queue, task_id)
            if task:
                task['status'] = TaskStatus.PROCESSING
                task['start_time'] = time.time()
                self.processing_queue.append(task)
                return task
            return None
            
    def handle_failed_task(self, task_id, error_msg):
        """处理失败任务"""
        with self.queue_lock:
            task = self._find_and_remove(self.processing_queue, task_id)
            if task:
                task['status'] = TaskStatus.FAILED
                task['error'] = error_msg
                task['retry_count'] += 1
                
                # 如果重试次数未超限，加入队列后方
                if task['retry_count'] < MAX_RETRY_COUNT:
                    task['status'] = TaskStatus.RETRYING
                    self.pending_queue.append(task)  # 加入队列后方
                else:
                    self.failed_queue.append(task)
                    
    def complete_task(self, task_id):
        """完成任务，从队列中移除"""
        with self.queue_lock:
            task = self._find_and_remove(self.processing_queue, task_id)
            if task:
                task['status'] = TaskStatus.COMPLETED
                task['end_time'] = time.time()
                # 完成的任务不保留在队列中
                return task
            return None
            
    def get_pending_tasks_by_model(self):
        """按模型分组获取待处理任务"""
        with self.queue_lock:
            model_tasks = {}
            for task in self.pending_queue:
                model = task['model']
                if model not in model_tasks:
                    model_tasks[model] = []
                model_tasks[model].append(task)
            return model_tasks
            
    def _insert_by_priority(self, queue, task):
        """按优先级和时间排序插入任务"""
        priority = self.priority_weights.get(task.get('priority', 'normal'), 2)
        created_time = task['created_time']
        
        # 找到合适的插入位置
        insert_pos = 0
        for i, existing_task in enumerate(queue):
            existing_priority = self.priority_weights.get(
                existing_task.get('priority', 'normal'), 2
            )
            
            # 优先级高的排在前面，同优先级按时间排序
            if (priority > existing_priority or 
                (priority == existing_priority and 
                 created_time < existing_task['created_time'])):
                insert_pos = i
                break
            insert_pos = i + 1
            
        queue.insert(insert_pos, task)
```

## 3. 显存预估池设计

### 3.1 显存校准机制

```python
class MemoryEstimationPool:
    def __init__(self):
        self.gpu_pools = {}  # {gpu_id: GPUMemoryPool}
        self.calibration_data = {}  # 校准数据
        self.segment_duration = int(os.getenv('SEGMENT_DURATION', 30))
        
    def initialize_gpu_pool(self, gpu_id):
        """初始化GPU显存池"""
        gpu_info = self._get_gpu_info(gpu_id)
        self.gpu_pools[gpu_id] = GPUMemoryPool(
            gpu_id=gpu_id,
            total_memory=gpu_info['total_memory'],
            reserved_memory=gpu_info['reserved_memory']
        )
        
    def calibrate_model_memory(self, gpu_id, model_name, actual_usage):
        """校准模型显存使用量"""
        key = f"{gpu_id}_{model_name}"
        
        if key not in self.calibration_data:
            self.calibration_data[key] = {
                'samples': [],
                'avg_usage': 0,
                'std_deviation': 0,
                'confidence_factor': 1.2  # 安全系数
            }
            
        # 添加新的校准样本
        self.calibration_data[key]['samples'].append(actual_usage)
        
        # 保持最近50个样本
        if len(self.calibration_data[key]['samples']) > 50:
            self.calibration_data[key]['samples'].pop(0)
            
        # 重新计算平均值和标准差
        samples = self.calibration_data[key]['samples']
        avg_usage = sum(samples) / len(samples)
        std_dev = (sum((x - avg_usage) ** 2 for x in samples) / len(samples)) ** 0.5
        
        self.calibration_data[key]['avg_usage'] = avg_usage
        self.calibration_data[key]['std_deviation'] = std_dev
        
        # 更新GPU池中的预估值
        estimated_usage = avg_usage + std_dev * self.calibration_data[key]['confidence_factor']
        self.gpu_pools[gpu_id].update_model_estimation(model_name, estimated_usage)
        
        logger.info(f"模型{model_name}在GPU{gpu_id}的显存使用校准: "
                   f"平均{avg_usage:.2f}GB, 预估{estimated_usage:.2f}GB")
                   
    def get_estimated_memory_usage(self, gpu_id, model_name):
        """获取模型预估显存使用量"""
        if gpu_id in self.gpu_pools:
            return self.gpu_pools[gpu_id].get_model_estimation(model_name)
        return self._get_default_estimation(model_name)
        
    def can_allocate_tasks(self, gpu_id, tasks):
        """检查GPU是否可以分配指定任务"""
        if gpu_id not in self.gpu_pools:
            return False
            
        total_required = 0
        for task in tasks:
            model_memory = self.get_estimated_memory_usage(gpu_id, task['model'])
            # 考虑音频时长对显存的影响
            duration_factor = self._calculate_duration_factor(task)
            total_required += model_memory * duration_factor
            
        return self.gpu_pools[gpu_id].can_allocate(total_required)
        
    def _calculate_duration_factor(self, task):
        """根据音频时长计算显存影响因子"""
        total_duration = sum(self._get_audio_duration(f) for f in task['files'])
        
        # 基于标准分段时长计算因子
        if total_duration <= self.segment_duration:
            return 1.0
        
        return 1.0 + (total_duration / self.segment_duration - 1) * 0.3
            
class GPUMemoryPool:
    def __init__(self, gpu_id, total_memory, reserved_memory):
        self.gpu_id = gpu_id
        self.total_memory = total_memory
        self.reserved_memory = reserved_memory
        self.allocated_memory = 0
        self.model_estimations = {}  # {model_name: estimated_memory}
        self.safety_margin = 0.1
        
    @property
    def available_memory(self):
        """计算可用显存"""
        usable = self.total_memory - self.reserved_memory
        return max(0, usable * (1 - self.safety_margin) - self.allocated_memory)
        
    def can_allocate(self, required_memory):
        """检查是否可以分配指定显存"""
        return self.available_memory >= required_memory
        
    def allocate(self, memory_size):
        """分配显存"""
        if self.can_allocate(memory_size):
            self.allocated_memory += memory_size
            return True
        return False
        
    def release(self, memory_size):
        """释放显存"""
        self.allocated_memory = max(0, self.allocated_memory - memory_size)
        
    def update_model_estimation(self, model_name, estimated_memory):
        """更新模型显存预估"""
        self.model_estimations[model_name] = estimated_memory
        
    def get_model_estimation(self, model_name):
        """获取模型显存预估"""
        return self.model_estimations.get(model_name, 
                                        self._get_default_estimation(model_name))
```

## 4. 批量任务调度器

### 4.1 智能批量调度

```python
class BatchTaskScheduler:
    def __init__(self, queue_manager, memory_pool):
        self.queue_manager = queue_manager
        self.memory_pool = memory_pool
        self.max_concurrent_tasks = int(os.getenv('MAX_CONCURRENT_TRANSCRIPTIONS', 3))
        self.scheduler_thread = None
        self.is_running = False
        
    def start_scheduler(self):
        """启动批量调度器"""
        if not self.is_running:
            self.is_running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
            
    def _scheduler_loop(self):
        """调度器主循环"""
        while self.is_running:
            try:
                self._schedule_batch_tasks()
                time.sleep(2)  # 调度间隔
            except Exception as e:
                logger.error(f"批量调度器错误: {e}")
                
    def _schedule_batch_tasks(self):
        """批量任务调度"""
        # 检查当前处理中的任务数
        current_processing = len(self.queue_manager.processing_queue)
        
        if current_processing >= self.max_concurrent_tasks:
            return  # 已达到最大并发数
            
        # 获取按模型分组的待处理任务
        model_tasks = self.queue_manager.get_pending_tasks_by_model()
        
        if not model_tasks:
            return  # 没有待处理任务
            
        # 为每个GPU计算最优任务批次
        for gpu_id in self.memory_pool.gpu_pools.keys():
            available_slots = self.max_concurrent_tasks - current_processing
            if available_slots <= 0:
                break
                
            batch = self._calculate_optimal_batch(gpu_id, model_tasks, available_slots)
            
            if batch:
                self._execute_batch(gpu_id, batch)
                current_processing += len(batch)
                
    def _calculate_optimal_batch(self, gpu_id, model_tasks, max_tasks):
        """计算最优任务批次"""
        batch = []
        total_memory = 0
        
        # 按模型优先级排序（优先选择已加载的模型）
        sorted_models = self._sort_models_by_priority(gpu_id, model_tasks.keys())
        
        for model_name in sorted_models:
            tasks = model_tasks[model_name]
            model_memory = self.memory_pool.get_estimated_memory_usage(gpu_id, model_name)
            
            # 计算该模型可以并发的任务数
            for task in tasks:
                if len(batch) >= max_tasks:
                    break
                    
                duration_factor = self.memory_pool._calculate_duration_factor(task)
                required_memory = model_memory * duration_factor
                
                if self.memory_pool.gpu_pools[gpu_id].can_allocate(total_memory + required_memory):
                    batch.append(task)
                    total_memory += required_memory
                else:
                    break  # 显存不足，停止添加任务
                    
        return batch
        
    def _sort_models_by_priority(self, gpu_id, model_names):
        """按优先级排序模型"""
        # 优先级：已加载模型 > 小模型 > 大模型
        loaded_models = self._get_loaded_models(gpu_id)
        
        def model_priority(model_name):
            if model_name in loaded_models:
                return 0  # 最高优先级
            else:
                # 按模型大小排序，小模型优先
                model_sizes = {
                    'tiny': 1, 'base': 2, 'small': 3, 'medium': 4,
                    'large': 5, 'large-v2': 6, 'large-v3': 7, 'turbo': 3.5
                }
                return model_sizes.get(model_name, 10)
                
        return sorted(model_names, key=model_priority)
        
    def _execute_batch(self, gpu_id, batch):
        """执行批量任务"""
        logger.info(f"GPU{gpu_id}开始执行批量任务，共{len(batch)}个任务")
        
        # 预分配显存
        total_memory = 0
        for task in batch:
            model_memory = self.memory_pool.get_estimated_memory_usage(gpu_id, task['model'])
            duration_factor = self.memory_pool._calculate_duration_factor(task)
            required_memory = model_memory * duration_factor
            
            if self.memory_pool.gpu_pools[gpu_id].allocate(required_memory):
                task['allocated_memory'] = required_memory
                total_memory += required_memory
            else:
                logger.error(f"任务{task['id']}显存分配失败")
                continue
                
        # 启动批量处理线程
        batch_thread = threading.Thread(
            target=self._process_batch,
            args=(gpu_id, batch)
        )
        batch_thread.daemon = True
        batch_thread.start()
        
    def _process_batch(self, gpu_id, batch):
        """处理批量任务"""
        try:
            # 按模型分组处理
            model_groups = {}
            for task in batch:
                model = task['model']
                if model not in model_groups:
                    model_groups[model] = []
                model_groups[model].append(task)
                
            # 逐个模型处理任务组
            for model_name, tasks in model_groups.items():
                self._process_model_tasks(gpu_id, model_name, tasks)
                
        except Exception as e:
            logger.error(f"批量任务处理失败: {e}")
        finally:
            # 释放所有分配的显存
            self._release_batch_memory(gpu_id, batch)
            
    def _process_model_tasks(self, gpu_id, model_name, tasks):
        """处理同一模型的任务组"""
        model = None
        try:
            # 加载模型
            start_time = time.time()
            model = whisper.load_model(model_name, device=f"cuda:{gpu_id}")
            load_time = time.time() - start_time
            
            logger.info(f"模型{model_name}加载完成，耗时{load_time:.2f}秒")
            
            # 并发处理任务
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                futures = []
                
                for task in tasks:
                    # 移动任务到处理中队列
                    self.queue_manager.move_to_processing(task['id'])
                    
                    # 提交任务到线程池
                    future = executor.submit(
                        self._process_single_task,
                        model, task, gpu_id
                    )
                    futures.append((future, task))
                    
                # 等待所有任务完成
                for future, task in futures:
                    try:
                        result = future.result(timeout=3600)  # 1小时超时
                        self.queue_manager.complete_task(task['id'])
                        
                        # 校准显存使用量
                        actual_memory = self._measure_actual_memory_usage(gpu_id)
                        self.memory_pool.calibrate_model_memory(
                            gpu_id, model_name, actual_memory
                        )
                        
                    except Exception as e:
                        logger.error(f"任务{task['id']}处理失败: {e}")
                        self.queue_manager.handle_failed_task(task['id'], str(e))
                        
        except Exception as e:
            logger.error(f"模型{model_name}处理失败: {e}")
            # 标记所有任务为失败
            for task in tasks:
                self.queue_manager.handle_failed_task(task['id'], str(e))
        finally:
            # 清理模型和GPU缓存
            if model:
                del model
            torch.cuda.empty_cache()
            
    def _release_batch_memory(self, gpu_id, batch):
        """释放批量任务的显存"""
        for task in batch:
            if 'allocated_memory' in task:
                self.memory_pool.gpu_pools[gpu_id].release(task['allocated_memory'])
                
        logger.info(f"GPU{gpu_id}批量任务显存释放完成")
```

## 5. 性能监控和优化

### 5.1 实时性能监控

```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'task_throughput': [],      # 任务吞吐量
            'gpu_utilization': {},      # GPU利用率
            'memory_efficiency': {},    # 显存效率
            'queue_wait_time': [],      # 队列等待时间
            'batch_processing_time': [] # 批处理时间
        }
        
    def record_task_completion(self, task):
        """记录任务完成指标"""
        if 'start_time' in task and 'end_time' in task:
            processing_time = task['end_time'] - task['start_time']
            wait_time = task['start_time'] - task['created_time']
            
            self.metrics['queue_wait_time'].append(wait_time)
            
            # 计算吞吐量（任务数/小时）
            current_hour = int(time.time() // 3600)
            throughput_key = f"hour_{current_hour}"
            
            if throughput_key not in self.metrics['task_throughput']:
                self.metrics['task_throughput'][throughput_key] = 0
            self.metrics['task_throughput'][throughput_key] += 1
            
    def get_performance_report(self):
        """生成性能报告"""
        report = {
            'avg_wait_time': self._calculate_average(self.metrics['queue_wait_time']),
            'current_throughput': self._get_current_throughput(),
            'gpu_utilization': self._get_gpu_utilization(),
            'memory_efficiency': self._calculate_memory_efficiency(),
            'recommendations': self._generate_recommendations()
        }
        return report
        
    def _generate_recommendations(self):
        """生成优化建议"""
        recommendations = []
        
        avg_wait = self._calculate_average(self.metrics['queue_wait_time'])
        if avg_wait > 300:  # 等待时间超过5分钟
            recommendations.append("建议增加并发任务数或优化显存分配策略")
            
        gpu_util = self._get_gpu_utilization()
        if gpu_util < 0.7:  # GPU利用率低于70%
            recommendations.append("GPU利用率较低，建议增加批处理大小")
            
        memory_eff = self._calculate_memory_efficiency()
        if memory_eff < 0.6:  # 显存效率低于60%
            recommendations.append("显存利用效率较低，建议优化模型加载策略")
            
        return recommendations
```

### 5.2 自适应参数调整

```python
class AdaptiveOptimizer:
    def __init__(self, scheduler, monitor):
        self.scheduler = scheduler
        self.monitor = monitor
        self.adjustment_history = []
        
    def optimize_parameters(self):
        """自适应参数优化"""
        report = self.monitor.get_performance_report()
        
        # 根据性能指标调整参数
        if report['avg_wait_time'] > 300 and report['gpu_utilization'] < 0.8:
            # 等待时间长且GPU利用率低，增加并发数
            self._adjust_concurrent_tasks(1)
            
        elif report['memory_efficiency'] < 0.6:
            # 显存效率低，减少并发数
            self._adjust_concurrent_tasks(-1)
            
        # 调整批处理大小
        if report['current_throughput'] < self._get_target_throughput():
            self._adjust_batch_size(1)
            
    def _adjust_concurrent_tasks(self, delta):
        """调整并发任务数"""
        current = self.scheduler.max_concurrent_tasks
        new_value = max(1, min(10, current + delta))
        
        if new_value != current:
            self.scheduler.max_concurrent_tasks = new_value
            logger.info(f"并发任务数调整: {current} -> {new_value}")
            
            self.adjustment_history.append({
                'timestamp': time.time(),
                'parameter': 'concurrent_tasks',
                'old_value': current,
                'new_value': new_value,
                'reason': 'performance_optimization'
            })
```

## 6. 配置和部署

### 6.1 配置参数优化

```python
# 在.env文件中添加新的配置项

# ==================== 并发优化配置 ====================
# 最大重试次数
MAX_RETRY_COUNT=3

# 批量调度间隔(秒)
BATCH_SCHEDULE_INTERVAL=2

# 显存校准样本数
CALIBRATION_SAMPLE_SIZE=50

# 显存安全系数
MEMORY_CONFIDENCE_FACTOR=1.2

# 性能监控间隔(秒)
PERFORMANCE_MONITOR_INTERVAL=60

# 自适应优化间隔(秒)
ADAPTIVE_OPTIMIZATION_INTERVAL=300

# GPU利用率目标
TARGET_GPU_UTILIZATION=0.85

# 显存效率目标
TARGET_MEMORY_EFFICIENCY=0.75
```

### 6.2 系统集成

```python
class OptimizedWhisperSystem:
    def __init__(self):
        self.queue_manager = IntelligentQueueManager()
        self.memory_pool = MemoryEstimationPool()
        self.scheduler = BatchTaskScheduler(self.queue_manager, self.memory_pool)
        self.monitor = PerformanceMonitor()
        self.optimizer = AdaptiveOptimizer(self.scheduler, self.monitor)
        
    def initialize(self):
        """系统初始化"""
        # 初始化GPU显存池
        available_gpus = self._get_available_gpus()
        for gpu_id in available_gpus:
            self.memory_pool.initialize_gpu_pool(gpu_id)
            
        # 启动调度器
        self.scheduler.start_scheduler()
        
        # 启动监控和优化
        self._start_monitoring()
        self._start_optimization()
        
        logger.info("优化版Whisper系统初始化完成")
        
    def submit_transcription_task(self, files, model, language, priority='normal'):
        """提交转录任务"""
        task = {
            'id': str(uuid.uuid4()),
            'files': files,
            'model': model,
            'language': language,
            'priority': priority,
            'created_time': time.time()
        }
        
        self.queue_manager.add_task(task)
        return task['id']
        
    def get_system_status(self):
        """获取系统状态"""
        return {
            'queue_status': {
                'pending': len(self.queue_manager.pending_queue),
                'processing': len(self.queue_manager.processing_queue),
                'failed': len(self.queue_manager.failed_queue)
            },
            'gpu_status': {
                gpu_id: {
                    'total_memory': pool.total_memory,
                    'allocated_memory': pool.allocated_memory,
                    'available_memory': pool.available_memory
                }
                for gpu_id, pool in self.memory_pool.gpu_pools.items()
            },
            'performance': self.monitor.get_performance_report()
        }
```

## 7. 总结和效果预期

### 7.1 优化效果

1. **显存利用率提升**: 通过精确的显存预估和校准，预期显存利用率提升30-50%
2. **任务吞吐量增加**: 批量调度和智能队列管理，预期吞吐量提升40-60%
3. **等待时间减少**: 优先级队列和自适应调度，预期等待时间减少50-70%
4. **系统稳定性**: 完善的错误处理和重试机制，显著提升系统可靠性

### 7.2 关键特性

- **智能显存管理**: 基于实际使用情况的动态校准
- **批量任务处理**: 最大化GPU资源利用效率
- **自适应优化**: 根据性能指标自动调整参数
- **完善监控**: 实时性能监控和优化建议

### 7.3 部署建议

1. **分阶段部署**: 先在测试环境验证，再逐步推广到生产环境
2. **参数调优**: 根据实际硬件配置和使用场景调整配置参数
3. **监控告警**: 建立完善的监控告警机制，及时发现和处理问题
4. **性能测试**: 定期进行性能测试，验证优化效果

通过实施本优化方案，Whisper系统将具备更强的并发处理能力、更高的资源利用效率和更好的用户体验。