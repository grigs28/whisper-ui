# 并发转录流程设计方案

## 1. 设计目标

设计一个基于GPU剩余显存动态决策的并发转录流程，实现：
- 根据实时显存状况决定模型加载时机
- 模型加载与转录过程分离
- 转录结束后及时释放显存
- 动态选择下一个可加载的模型

## 2. 流程设计原理

### 2.1 核心思想
- **显存驱动决策**：以GPU显存剩余量作为核心决策依据
- **生命周期管理**：模型加载→转录执行→显存释放的完整生命周期
- **动态调度**：根据显存变化动态调整任务执行顺序

### 2.2 关键要素
1. **显存监控**：实时监控GPU显存使用情况
2. **模型预估**：准确预估各模型所需显存
3. **任务排队**：根据显存状况对任务进行排队
4. **状态机管理**：任务在不同状态间的流转

## 3. 详细流程设计

### 3.1 任务状态机

```
[Pending] → [Loading] → [Processing] → [Completed/Failed]
    ↑           ↑           ↑
    |           |           |
    └───[Memory Check]───[Release Memory]
```

### 3.2 显存决策流程

#### 步骤1：任务到达
```
1. 任务进入等待队列
2. 检查当前运行任务数
3. 检查是否有模型正在加载
4. 进入显存评估阶段
```

#### 步骤2：显存评估
```
1. 获取GPU实时显存信息
2. 计算当前可用显存（考虑安全边际）
3. 预估任务所需显存
4. 决策是否可以立即执行
```

#### 步骤3：模型加载决策
```
输入：任务信息、GPU显存状态
输出：是否加载模型、加载哪个模型

决策逻辑：
1. 如果当前无运行任务：
   - 检查显存是否足够加载任务模型
   - 如果足够，立即加载并执行
   - 如果不足，等待或排队

2. 如果已有运行任务：
   - 检查是否可以共享现有模型
   - 检查显存是否足够加载新模型
   - 如果可以，启动新任务
   - 如果不可以，排队等待
```

#### 步骤4：转录执行
```
1. 模型加载完成
2. 发送loading状态更新
3. 启动转录任务
4. 实时监控转录进度
5. 转录完成后进入释放阶段
```

#### 步骤5：显存释放与下一任务决策
```
1. 转录任务完成
2. 释放相关模型显存
3. 检查队列中是否有等待任务
4. 根据新显存状况决定是否启动新任务
5. 重复决策循环
```

## 4. 核心算法实现

### 4.1 显存评估算法

```python
def evaluate_memory_availability(required_memory, gpu_info, safety_margin=0.1):
    """
    评估显存可用性
    
    Args:
        required_memory: 所需显存大小(GB)
        gpu_info: GPU信息
        safety_margin: 安全边际比例
    
    Returns:
        tuple: (是否足够, 可用显存, 建议GPU)
    """
    for gpu in gpu_info['gpus']:
        available_memory = gpu['memory']['free']
        safe_available = available_memory * (1 - safety_margin)
        
        if safe_available >= required_memory:
            return True, safe_available, gpu['id']
    
    return False, 0, None
```

### 4.2 动态任务调度算法

```python
def dynamic_task_scheduling(pending_tasks, running_tasks, gpu_info, memory_pool):
    """
    动态任务调度算法
    
    Args:
        pending_tasks: 等待任务列表
        running_tasks: 运行中任务列表
        gpu_info: GPU信息
        memory_pool: 显存池
    
    Returns:
        list: 可以立即执行的任务列表
    """
    available_tasks = []
    
    # 检查是否有任务可以立即执行
    for task in pending_tasks:
        model_name = task.get('model_name', task.get('model', 'medium'))
        
        # 检查是否可以加载模型
        required_memory = memory_pool.get_estimated_memory_usage(
            task.get('assigned_gpu', 0), model_name
        )
        
        # 检查显存是否足够
        can_allocate, available_memory, gpu_id = evaluate_memory_availability(
            required_memory, gpu_info
        )
        
        if can_allocate:
            # 为任务分配GPU
            task['assigned_gpu'] = gpu_id
            available_tasks.append(task)
    
    return available_tasks
```

### 4.3 模型生命周期管理

```python
class ModelLifecycleManager:
    """
    模型生命周期管理器
    """
    
    def __init__(self):
        self.loaded_models = {}  # {model_name: {gpu_id, timestamp}}
        self.model_memory_usage = {}  # {model_name: memory_usage}
    
    def load_model_if_needed(self, model_name, gpu_id, required_memory):
        """
        按需加载模型
        """
        # 检查模型是否已在指定GPU上加载
        if model_name in self.loaded_models:
            if self.loaded_models[model_name]['gpu_id'] == gpu_id:
                return True  # 已加载，无需重复加载
        
        # 检查显存是否足够
        if self.check_memory_sufficient(required_memory):
            # 加载模型
            self.perform_model_loading(model_name, gpu_id)
            self.loaded_models[model_name] = {
                'gpu_id': gpu_id,
                'timestamp': time.time()
            }
            return True
        
        return False
    
    def release_model_memory(self, model_name):
        """
        释放模型显存
        """
        if model_name in self.loaded_models:
            gpu_id = self.loaded_models[model_name]['gpu_id']
            # 执行显存释放
            self.perform_memory_release(model_name, gpu_id)
            del self.loaded_models[model_name]
            return True
        return False
```

## 5. 流程图示

### 5.1 主流程图

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
显存足够? → 是 → 加载模型
  ↓ 否 → 排队等待
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
检查队列是否有等待任务
  ↓
是 → 根据新显存状况启动新任务
  ↓
否 → 等待新任务到来
  ↓
结束
```

### 5.2 显存决策子流程

```
显存决策开始
  ↓
获取GPU实时显存信息
  ↓
计算安全可用显存
  ↓
获取任务所需模型显存
  ↓
比较显存需求与可用显存
  ↓
显存充足? → 是 → 可以执行
  ↓ 否
检查是否可以共享模型
  ↓
可以共享? → 是 → 启动共享任务
  ↓ 否
排队等待
  ↓
显存释放后重新评估
  ↓
结束
```

## 6. 关键优化点

### 6.1 显存预估优化
- 基于实际音频时长动态调整显存预估
- 考虑模型版本差异对显存需求的影响
- 引入历史数据学习机制优化预估准确性

### 6.2 任务优先级管理
- 支持不同优先级任务的差异化处理
- 高优先级任务可抢占低优先级任务资源
- 实现公平调度避免饥饿现象

### 6.3 并发控制优化
- 动态调整最大并发数
- 根据GPU负载智能调节任务分配
- 实现任务间资源隔离避免冲突

## 7. 实现要点

### 7.1 状态同步保证
- 使用互斥锁确保任务状态一致性
- 实现状态变更的原子性操作
- 增加状态变更日志便于调试

### 7.2 错误处理机制
- 模型加载失败的回退机制
- 转录过程中异常的恢复处理
- 显存释放失败的重试机制

### 7.3 性能监控
- 实时监控显存使用率
- 记录任务执行时间统计
- 提供性能瓶颈分析工具

## 8. 预期效果

1. **提高资源利用率**：通过动态显存分配，最大化利用GPU资源
2. **增强系统稳定性**：避免因显存不足导致的崩溃
3. **改善用户体验**：更合理的任务调度和响应速度
4. **支持高并发处理**：能够同时处理多个转录任务
5. **降低硬件成本**：更高效地利用现有硬件资源

## 9. 后续实施建议

1. **分阶段实现**：先实现基础版本，再逐步增加高级特性
2. **充分测试**：在不同硬件配置下进行压力测试
3. **监控告警**：建立完善的监控和告警机制
4. **文档完善**：详细记录设计思路和实现细节
5. **持续优化**：根据实际使用反馈不断优化算法

这个并发转录流程设计能够有效解决显存管理问题，通过动态决策机制实现更高效的资源利用和任务处理。
