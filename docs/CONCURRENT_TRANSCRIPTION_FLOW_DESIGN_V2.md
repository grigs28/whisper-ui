# 并发转录流程设计方案（修订版）

## 1. 设计目标

设计一个基于GPU剩余显存动态决策的并发转录流程，考虑到Whisper的限制：
- 一个模型只能处理一个转录文件
- 模型加载与转录过程分离
- 转录结束后及时释放显存
- 动态选择下一个可加载的模型

## 2. 限制条件说明

### 2.1 Whisper核心限制
- **模型-文件一对一**：每个模型实例只能处理一个音频文件
- **模型独占性**：同一模型在任一时刻只能被一个任务使用
- **显存占用**：模型加载后会占用相应显存直到任务完成

### 2.2 系统约束
- **并发控制**：需要控制同时运行的模型数量
- **资源管理**：合理分配GPU资源避免冲突
- **任务调度**：在有限资源下最大化吞吐量

## 3. 流程设计原理

### 3.1 核心思想
- **模型级并发**：以模型为单位进行并发控制
- **任务级调度**：以任务为单位进行排队和调度
- **资源感知调度**：根据可用显存决定任务执行顺序

### 3.2 关键要素
1. **模型状态管理**：跟踪哪些模型正在使用中
2. **任务队列管理**：按优先级和资源需求组织任务
3. **显存动态评估**：实时评估显存状况
4. **任务分配策略**：合理分配任务到可用模型

## 4. 详细流程设计

### 4.1 任务状态机（修正版）

```
[Pending] → [Loading] → [Processing] → [Completed/Failed]
    ↑           ↑           ↑
    |           |           |
    └───[Resource Check]───[Release Resource]
```

### 4.2 模型使用状态管理（简化版）

由于取消模型复用，不再需要复杂的模型状态跟踪，因此简化为：
- 每个任务独立加载自己的模型实例
- 不再跟踪模型是否已被其他任务使用
- 简化了并发控制逻辑
```

### 4.3 显存决策流程（修正版）

#### 步骤1：任务到达
```
1. 任务进入等待队列
2. 检查当前运行任务数
3. 检查是否有模型正在加载
4. 进入资源评估阶段
```

#### 步骤2：资源评估
```
1. 获取GPU实时显存信息
2. 计算当前可用显存（考虑安全边际）
3. 预估任务所需显存
4. 检查模型是否可复用
5. 决策是否可以立即执行
```

#### 步骤3：模型加载决策（简化版）
```
输入：任务信息、GPU显存状态
输出：是否可以执行、分配的GPU

决策逻辑：
1. 如果当前无运行任务：
   - 检查显存是否足够加载任务模型
   - 如果足够，立即加载并执行
   - 如果不足，等待或排队

2. 如果已有运行任务：
   - 检查显存是否足够加载新模型
   - 如果可以，启动新任务
   - 如果不可以，排队等待
```

#### 步骤4：转录执行（修正版）
```
1. 检查模型是否需要加载
2. 如果需要加载，执行模型加载
3. 发送loading状态更新
4. 启动转录任务
5. 实时监控转录进度
6. 转录完成后进入释放阶段
```

#### 步骤5：资源释放与下一任务决策
```
1. 转录任务完成
2. 释放相关模型显存
3. 标记模型为非活跃状态
4. 检查队列中是否有等待任务
5. 根据新资源状况决定是否启动新任务
6. 重复决策循环
```

## 5. 核心算法实现（修订版）

### 5.1 模型可用性检查算法（简化版）

```python
def check_model_availability(model_name, gpu_info, safety_margin=0.1):
    """
    检查模型是否可以加载
    
    Args:
        model_name: 模型名称
        gpu_info: GPU信息
        safety_margin: 安全边际比例
    
    Returns:
        tuple: (是否可以加载, 建议GPU, 可用显存)
    """
    # 简化版：不检查模型复用，直接检查显存是否足够
    required_memory = get_model_memory_requirement(model_name)
    
    for gpu in gpu_info['gpus']:
        available_memory = gpu['memory']['free']
        safe_available = available_memory * (1 - safety_margin)
        
        if safe_available >= required_memory:
            return True, gpu['id'], safe_available
    
    return False, None, 0
```

### 5.2 任务调度算法（简化版）

```python
def smart_task_scheduling(pending_tasks, running_tasks, gpu_info):
    """
    智能任务调度算法（取消模型复用）
    
    Args:
        pending_tasks: 等待任务列表
        running_tasks: 运行中任务列表
        gpu_info: GPU信息
    
    Returns:
        list: 可以立即执行的任务列表
    """
    available_tasks = []
    
    # 按照优先级排序任务
    sorted_tasks = sorted(pending_tasks, key=lambda t: t.get('priority', 'normal'))
    
    # 检查是否有任务可以立即执行
    for task in sorted_tasks:
        model_name = task.get('model_name', task.get('model', 'medium'))
        
        # 检查模型是否可以加载（简化版：不检查模型复用）
        can_load, gpu_id, available_memory = check_model_availability(
            model_name, gpu_info
        )
        
        if can_load:
            # 为任务分配GPU
            task['assigned_gpu'] = gpu_id
            available_tasks.append(task)
    
    return available_tasks
```

### 5.3 并发控制算法

```python
class ConcurrentControlManager:
    """
    并发控制管理器
    """
    
    def __init__(self, max_concurrent_models=5):
        self.max_concurrent_models = max_concurrent_models
        self.active_model_count = 0
        self.model_lock = threading.Lock()
    
    def can_start_new_model(self):
        """
        检查是否可以启动新模型
        """
        with self.model_lock:
            return self.active_model_count < self.max_concurrent_models
    
    def increment_model_count(self):
        """
        增加活跃模型计数
        """
        with self.model_lock:
            self.active_model_count += 1
    
    def decrement_model_count(self):
        """
        减少活跃模型计数
        """
        with self.model_lock:
            self.active_model_count = max(0, self.active_model_count - 1)
```

## 6. 修订后的流程图

### 6.1 主流程图（修订版）

```
开始
  ↓
任务入队
  ↓
检查运行中任务数
  ↓
是否无运行任务? → 是 → 检查显存是否足够?
  ↓ 否
检查是否有模型加载中?
  ↓
是 → 等待模型加载完成
  ↓
否 → 检查是否可以启动新任务
  ↓
显存足够? → 是 → 检查模型是否可复用?
  ↓ 否 → 排队等待
  ↓
可以复用? → 是 → 启动复用任务
  ↓ 否 → 加载新模型
  ↓
模型加载完成
  ↓
启动转录任务
  ↓
转录进行中
  ↓
转录完成
  ↓
释放模型显存
  ↓
减少活跃模型计数
  ↓
检查队列是否有等待任务
  ↓
是 → 根据新资源状况启动新任务
  ↓
否 → 等待新任务到来
  ↓
结束
```

### 6.2 模型加载决策子流程（修订版）

```
模型加载决策开始
  ↓
获取GPU实时显存信息
  ↓
计算安全可用显存
  ↓
获取任务所需模型显存
  ↓
检查是否已有相同模型运行
  ↓
是 → 可以复用，启动任务
  ↓ 否
检查显存是否足够
  ↓
显存充足? → 是 → 可以加载新模型
  ↓ 否
排队等待
  ↓
显存释放后重新评估
  ↓
结束
```

## 7. 关键优化点（简化版）

### 7.1 简化并发控制
- 取消模型复用机制，每个任务独立加载模型
- 简化并发控制逻辑
- 降低系统复杂度

### 7.2 资源感知调度
- 根据显存状况动态调整任务执行
- 避免显存不足导致的阻塞
- 提高资源利用率

### 7.3 并发度控制
- 控制同时运行的模型数量
- 防止GPU资源过度竞争
- 保证系统稳定性

## 8. 实现要点（修订版）

### 8.1 状态同步保证
- 使用互斥锁确保模型状态一致性
- 实现状态变更的原子性操作
- 增加状态变更日志便于调试

### 8.2 错误处理机制
- 模型加载失败的回退机制
- 转录过程中异常的恢复处理
- 显存释放失败的重试机制

### 8.3 性能监控
- 实时监控显存使用率
- 记录模型加载时间统计
- 提供性能瓶颈分析工具

## 9. 预期效果（简化版）

1. **符合Whisper限制**：严格遵守一个模型一个文件的原则
2. **简化系统复杂度**：取消模型复用机制，降低系统复杂性
3. **增强系统稳定性**：简化并发控制逻辑，减少潜在冲突
4. **改善用户体验**：更清晰的任务执行流程
5. **支持高并发处理**：在限制条件下最大化并发能力

## 10. 后续实施建议

1. **分阶段实现**：先实现基础版本，再逐步增加优化特性
2. **充分测试**：在不同硬件配置下进行压力测试
3. **监控告警**：建立完善的监控和告警机制
4. **文档完善**：详细记录设计思路和实现细节
5. **持续优化**：根据实际使用反馈不断优化算法

这个修订版的并发转录流程设计完全考虑了Whisper的限制条件，通过模型复用和智能调度，在保证系统稳定性的前提下最大化并发处理能力。
