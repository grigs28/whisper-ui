# Whisper 显存计算指南

本指南详细说明了如何根据模型大小、分段长度等参数精确计算 Whisper 模型的显存占用。

## 功能概述

新的显存计算系统提供了以下功能：

1. **精确显存计算**：基于模型参数、分段长度、批处理大小和精度类型
2. **详细显存分解**：显示各组件的显存占用情况
3. **智能优化建议**：根据配置提供显存优化建议
4. **GPU兼容性检查**：检查当前GPU是否满足显存需求

## 显存计算公式

### 基础计算组件

```
总显存需求 = 基础模型显存 + 音频处理显存 + 批处理开销 + PyTorch开销
推荐配置 = 总显存需求 × 1.2 (20%安全边际)
```

### 详细计算方法

#### 1. 基础模型显存

根据模型大小和精度类型计算：

| 模型 | 参数量 | Float32 | Float16 | Int8 | Int4 |
|------|--------|---------|---------|------|------|
| tiny | 39M | 1.5GB | 0.8GB | 0.4GB | 0.2GB |
| base | 74M | 2.0GB | 1.0GB | 0.5GB | 0.25GB |
| small | 244M | 3.0GB | 1.5GB | 0.75GB | 0.375GB |
| medium | 769M | 5.0GB | 2.5GB | 1.25GB | 0.625GB |
| large/large-v2/large-v3 | 1550M | 10.0GB | 5.0GB | 2.5GB | 1.25GB |

#### 2. 音频处理显存

```
音频处理显存 = 基础模型显存 × 0.15 × (分段长度 / 30秒)
```

- Whisper 标准处理 30 秒音频段
- 音频处理显存约为基础模型显存的 15%
- 与分段长度线性相关

#### 3. 批处理开销

```
批处理显存 = 0.2GB (固定开销) + 音频处理显存 × 批处理大小
```

#### 4. PyTorch 开销

```
PyTorch开销 = (基础模型显存 + 批处理显存) × 0.25
```

## 使用方法

### 1. 基础显存计算

```python
from core.gpu_manager import gpu_manager

# 计算 medium 模型的显存需求
result = gpu_manager.calculate_memory_usage("medium")
print(f"总需求: {result['total_required']:.2f}GB")
print(f"推荐配置: {result['recommended']:.2f}GB")
```

### 2. 自定义参数计算

```python
# 计算 large 模型，600秒分段，批大小2，int8精度
result = gpu_manager.calculate_memory_usage(
    model_name="large",
    segment_duration=600,
    batch_size=2,
    precision="int8"
)

# 查看详细分解
for component, memory in result['breakdown'].items():
    print(f"{component}: {memory:.2f}GB")
```

### 3. GPU 显存充足性检查

```python
# 检查 GPU 是否满足显存需求
result = gpu_manager.check_gpu_memory_sufficient(
    model_name="medium",
    gpu_ids=[0],
    segment_duration=300,
    batch_size=1,
    precision="float16"
)

if result['sufficient']:
    print("显存充足")
else:
    print(f"显存不足: {result['message']}")
    print("优化建议:")
    for tip in result['optimization_suggestions']:
        print(f"  • {tip}")
```

## 优化策略

### 1. 减少显存占用

#### 选择合适的模型
- **tiny/base**: 适合资源受限环境，显存需求 < 2GB
- **small**: 平衡性能和资源，显存需求 2-3GB
- **medium**: 较好性能，显存需求 5-8GB
- **large**: 最佳性能，显存需求 10-20GB

#### 调整分段长度
```python
# 不同分段长度的显存影响
segment_durations = [30, 60, 120, 300, 600]
for duration in segment_durations:
    calc = gpu_manager.calculate_memory_usage("medium", segment_duration=duration)
    print(f"{duration}秒: {calc['recommended']:.1f}GB")
```

#### 使用低精度
```python
# 精度对显存的影响
precisions = ["float32", "float16", "int8", "int4"]
for precision in precisions:
    calc = gpu_manager.calculate_memory_usage("large", precision=precision)
    print(f"{precision}: {calc['recommended']:.1f}GB")
```

### 2. 并发控制策略

#### 基于显存的任务调度
```python
def can_run_concurrent_task(model_name, current_tasks):
    """检查是否可以运行新的并发任务"""
    # 计算新任务的显存需求
    new_task_memory = gpu_manager.calculate_memory_usage(model_name)
    
    # 计算当前任务的总显存占用
    current_memory = sum(
        gpu_manager.calculate_memory_usage(task['model'])['recommended']
        for task in current_tasks
    )
    
    # 获取GPU可用显存
    gpu_info = gpu_manager.get_gpu_memory_info()
    available_memory = gpu_info['gpus'][0]['free']
    
    return (current_memory + new_task_memory['recommended']) <= available_memory
```

#### 智能任务分配
```python
def assign_optimal_model(available_memory):
    """根据可用显存选择最优模型"""
    models = ["large", "medium", "small", "base", "tiny"]
    
    for model in models:
        calc = gpu_manager.calculate_memory_usage(model)
        if calc['recommended'] <= available_memory:
            return model
    
    return "tiny"  # 最小模型
```

## 实际应用示例

### 1. 不同GPU配置的建议

| GPU型号 | 显存 | 推荐模型 | 最大分段 | 并发数 |
|---------|------|----------|----------|--------|
| GTX 1660 | 6GB | small | 300秒 | 1 |
| RTX 3060 | 8GB | medium | 300秒 | 1 |
| RTX 3070 | 8GB | medium | 600秒 | 1 |
| RTX 3080 | 10GB | medium | 600秒 | 1-2 |
| RTX 3090 | 24GB | large | 600秒 | 2-3 |
| RTX 4090 | 24GB | large | 1200秒 | 2-3 |

### 2. 性能优化配置

```python
# 高性能配置 (RTX 3090, 24GB)
high_performance = {
    "model": "large",
    "segment_duration": 600,
    "batch_size": 1,
    "precision": "float16",
    "max_concurrent": 2
}

# 平衡配置 (RTX 3070, 8GB)
balanced = {
    "model": "medium",
    "segment_duration": 300,
    "batch_size": 1,
    "precision": "float16",
    "max_concurrent": 1
}

# 节能配置 (GTX 1660, 6GB)
efficient = {
    "model": "small",
    "segment_duration": 120,
    "batch_size": 1,
    "precision": "int8",
    "max_concurrent": 1
}
```

## 注意事项

1. **显存计算是估算值**：实际显存占用可能因驱动版本、CUDA版本等因素有所差异
2. **预留安全边际**：建议预留20%的显存作为安全边际
3. **动态监控**：在实际使用中应动态监控显存使用情况
4. **及时释放**：任务完成后及时释放模型内存

## 故障排除

### 常见问题

1. **显存不足错误**
   - 减少分段长度
   - 使用更小的模型
   - 降低精度
   - 减少并发任务数

2. **显存泄漏**
   - 检查模型是否正确释放
   - 强制垃圾回收
   - 清空CUDA缓存

3. **性能下降**
   - 检查是否使用了过小的分段
   - 确认精度设置是否合适
   - 监控GPU利用率

### 调试命令

```python
# 获取详细的GPU信息
gpu_info = gpu_manager.get_cuda_debug_info()
print(json.dumps(gpu_info, indent=2, ensure_ascii=False))

# 强制释放所有显存
gpu_manager.release_all_memory()

# 检查当前显存使用
memory_info = gpu_manager.get_gpu_memory_info()
print(f"已用显存: {memory_info['gpus'][0]['used']:.2f}GB")
print(f"可用显存: {memory_info['gpus'][0]['free']:.2f}GB")
```