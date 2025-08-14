# Whisper 动态并发处理指南

## 概述

动态并发处理是 Whisper 转录系统的核心功能之一，它能够根据 GPU 显存状态自动调整并发任务数量，实现最优的资源利用和性能表现。

## 核心特性

### 1. 智能并发计算
- **自动显存检测**：实时检测所有可用 GPU 的显存状态
- **精确需求计算**：基于模型类型、分段长度和精度计算单任务显存需求
- **安全边际预留**：预留 20% 显存作为安全缓冲，避免显存溢出
- **动态调整**：根据显存变化自动调整最大并发数

### 2. 智能 GPU 分配
- **负载均衡**：优先选择负载最低的 GPU
- **显存优化**：确保分配的 GPU 有足够显存运行任务
- **实时监控**：持续监控 GPU 负载和显存使用情况

### 3. 任务队列管理
- **无阻塞队列**：使用线程安全的任务队列
- **优先级处理**：支持任务优先级和调度策略
- **状态跟踪**：实时跟踪任务状态和进度

## 使用方法

### 基本使用

```python
from core.transcription_processor import TranscriptionProcessor
from core.queue_manager import QueueManager

# 创建队列管理器
queue_manager = QueueManager()

# 创建转录处理器（自动启用动态并发）
processor = TranscriptionProcessor(queue_manager=queue_manager)

# 添加任务到并发队列
task = {
    'task_id': 'unique_task_id',
    'file_path': '/path/to/audio.wav',
    'output_path': '/path/to/output.txt',
    'model_name': 'base',
    'language': 'zh',
    'gpu_ids': None  # 自动分配
}

processor.add_task_to_concurrent_queue(task)
```

### 获取并发状态

```python
# 获取当前并发状态
status = processor.get_concurrent_status()
print(f"最大并发数: {status['max_concurrent_tasks']}")
print(f"活动任务数: {status['active_tasks']}")
print(f"队列大小: {status['queue_size']}")
```

### 系统状态监控

```python
# 获取完整系统状态
system_status = processor.get_system_status()
print(f"GPU 状态: {system_status['gpu_status']}")
print(f"并发状态: {system_status['concurrent_status']}")
print(f"活动任务: {system_status['active_tasks']}")
```

## 配置参数

### 显存计算参数

```python
# 在 config.py 中配置
SEGMENT_DURATION = 300  # 分段长度（秒）
DEFAULT_PRECISION = "float16"  # 默认精度
MEMORY_SAFETY_MARGIN = 0.2  # 安全边际（20%）
```

### 并发控制参数

```python
# 最大并发任务数限制
MAX_CONCURRENT_LIMIT = 8  # 硬性上限
MIN_CONCURRENT_TASKS = 1  # 最小并发数
```

## 工作原理

### 1. 并发数计算流程

```
1. 检测可用 GPU 数量和显存
2. 计算单任务显存需求
3. 应用安全边际（80% 可用显存）
4. 计算理论最大并发数
5. 应用硬性限制
6. 返回最终并发数
```

### 2. GPU 分配策略

```
1. 获取所有可用 GPU
2. 计算每个 GPU 的当前负载
3. 检查显存可用性
4. 选择负载最低且显存充足的 GPU
5. 更新 GPU 负载记录
```

### 3. 动态调整机制

```
1. 定期检查 GPU 状态变化
2. 重新计算最优并发数
3. 调整线程池大小
4. 通知前端状态变化
```

## 性能优化建议

### 1. 显存优化
- 选择合适的模型大小（tiny/base/small/medium/large）
- 调整分段长度以平衡精度和显存使用
- 使用 float16 精度减少显存占用

### 2. 并发优化
- 根据 GPU 数量和显存大小调整并发数
- 避免过度并发导致的上下文切换开销
- 监控 GPU 利用率，确保充分利用硬件资源

### 3. 任务调度优化
- 合理安排任务优先级
- 避免长时间任务阻塞短任务
- 定期清理已完成的任务

## 故障排除

### 常见问题

1. **并发数为 0**
   - 检查 GPU 是否可用
   - 确认显存是否充足
   - 验证模型配置是否正确

2. **任务分配失败**
   - 检查 GPU 状态
   - 确认显存计算是否准确
   - 查看错误日志

3. **性能不佳**
   - 监控 GPU 利用率
   - 调整并发数设置
   - 优化模型和参数配置

### 调试工具

```python
# 运行简化测试
python test_dynamic_concurrent_simple.py

# 查看详细日志
from utils.logger import log_message
log_message('debug', '调试信息')
```

## 示例代码

### 完整使用示例

```python
import time
from core.transcription_processor import TranscriptionProcessor
from core.queue_manager import QueueManager

def main():
    # 初始化
    queue_manager = QueueManager()
    processor = TranscriptionProcessor(queue_manager=queue_manager)
    
    # 添加多个任务
    tasks = [
        {
            'task_id': f'task_{i}',
            'file_path': f'/path/to/audio_{i}.wav',
            'output_path': f'/path/to/output_{i}.txt',
            'model_name': 'base',
            'language': 'zh'
        }
        for i in range(5)
    ]
    
    # 提交任务
    for task in tasks:
        processor.add_task_to_concurrent_queue(task)
        print(f"已提交任务: {task['task_id']}")
    
    # 监控处理进度
    while True:
        status = processor.get_concurrent_status()
        if status['active_tasks'] == 0 and status['queue_size'] == 0:
            break
        
        print(f"活动任务: {status['active_tasks']}, 队列: {status['queue_size']}")
        time.sleep(2)
    
    print("所有任务完成")
    
    # 清理资源
    processor.cleanup_resources()

if __name__ == '__main__':
    main()
```

## 总结

动态并发处理功能通过智能的资源管理和任务调度，显著提升了 Whisper 转录系统的性能和稳定性。它能够：

- 自动适应不同的硬件配置
- 最大化 GPU 资源利用率
- 确保系统稳定运行
- 提供实时的状态监控

通过合理配置和使用，可以实现最优的转录性能和用户体验。