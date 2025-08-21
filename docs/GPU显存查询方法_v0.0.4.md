# GPU剩余显存获取方法详解

## 1. 概述

获取GPU剩余显存是实现动态显存决策的基础。在Whisper音频转录系统中，我们需要实时监控GPU显存使用情况，以便做出正确的任务调度决策。

## 2. 显存查询技术方案

### 2.1 使用PyTorch API（推荐方案）

```python
import torch

def get_pytorch_gpu_memory():
    """
    使用PyTorch API获取GPU显存信息
    """
    if not torch.cuda.is_available():
        return {'success': False, 'error': 'CUDA不可用'}
    
    gpu_info = []
    for i in range(torch.cuda.device_count()):
        # 获取设备属性
        props = torch.cuda.get_device_properties(i)
        
        # 获取内存信息
        torch.cuda.set_device(i)
        total_memory = props.total_memory  # 总显存(字节)
        allocated_memory = torch.cuda.memory_allocated(i)  # 已分配显存(字节)
        cached_memory = torch.cuda.memory_reserved(i)  # 已保留显存(字节)
        free_memory = total_memory - allocated_memory  # 可用显存(字节)
        
        gpu_info.append({
            'id': i,
            'name': props.name,
            'memory': {
                'total': total_memory / (1024**3),  # 转换为GB
                'allocated': allocated_memory / (1024**3),
                'cached': cached_memory / (1024**3),
                'free': free_memory / (1024**3)
            }
        })
    
    return {'success': True, 'gpus': gpu_info}
```

### 2.2 使用pynvml库（NVIDIA Management Library）

```python
import pynvml

def get_nvidia_ml_gpu_memory():
    """
    使用NVIDIA ML库获取GPU显存信息
    """
    try:
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        
        gpu_info = []
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            
            # 获取设备名称
            name = pynvml.nvmlDeviceGetName(handle)
            
            # 获取内存信息
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            
            # 获取温度
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except:
                temp = None
            
            gpu_info.append({
                'id': i,
                'name': name,
                'memory': {
                    'total': mem_info.total / (1024**3),  # 转换为GB
                    'used': mem_info.used / (1024**3),
                    'free': mem_info.free / (1024**3)
                },
                'temperature': temp
            })
        
        return {'success': True, 'gpus': gpu_info}
    except Exception as e:
        return {'success': False, 'error': str(e)}
```

### 2.3 综合查询方法（系统级）

```python
import torch
import time
from config import config

class GPUInfoManager:
    """
    GPU信息管理器，提供统一的显存查询接口
    """
    
    def __init__(self):
        self.gpu_info_cache = {}
        self.last_query_time = 0
        self.cache_duration = 30  # 缓存30秒
    
    def get_gpu_memory_info(self, use_cache=True):
        """
        获取GPU显存信息
        
        Args:
            use_cache: 是否使用缓存
            
        Returns:
            dict: GPU信息
        """
        current_time = time.time()
        
        # 检查缓存
        if (use_cache and 
            current_time - self.last_query_time < self.cache_duration and 
            self.gpu_info_cache):
            return self.gpu_info_cache
        
        # 查询GPU信息
        gpu_info = self._query_gpu_info()
        
        # 更新缓存
        if gpu_info['success']:
            self.gpu_info_cache = gpu_info
            self.last_query_time = current_time
        
        return gpu_info
    
    def _query_gpu_info(self):
        """
        实际查询GPU信息的方法
        """
        # 优先使用PyTorch API
        if torch.cuda.is_available():
            return self._query_with_pytorch()
        else:
            # 备用方案：尝试pynvml
            try:
                return self._query_with_nvidia_ml()
            except:
                return self._fallback_query()
    
    def _query_with_pytorch(self):
        """
        使用PyTorch查询GPU信息
        """
        gpus = []
        for i in range(torch.cuda.device_count()):
            try:
                props = torch.cuda.get_device_properties(i)
                torch.cuda.set_device(i)
                
                # 获取内存信息
                total_memory = props.total_memory
                allocated_memory = torch.cuda.memory_allocated(i)
                cached_memory = torch.cuda.memory_reserved(i)
                free_memory = total_memory - allocated_memory
                
                gpus.append({
                    'id': i,
                    'name': props.name,
                    'memory': {
                        'total': total_memory / (1024**3),
                        'allocated': allocated_memory / (1024**3),
                        'cached': cached_memory / (1024**3),
                        'free': free_memory / (1024**3)
                    },
                    'compute_capability': f"{props.major}.{props.minor}"
                })
            except Exception as e:
                print(f"查询GPU {i} 信息失败: {e}")
                continue
        
        return {'success': len(gpus) > 0, 'gpus': gpus}
    
    def _query_with_nvidia_ml(self):
        """
        使用NVIDIA ML查询GPU信息
        """
        # 实现NVIDIA ML查询逻辑
        # 注意：此方法需要安装pynvml库
        pass
    
    def _fallback_query(self):
        """
        备用查询方法
        """
        return {
            'success': False,
            'error': '无法获取GPU信息',
            'gpus': []
        }
    
    def get_available_memory(self, gpu_id, safety_margin=0.1):
        """
        获取指定GPU的可用显存（考虑安全边际）
        
        Args:
            gpu_id: GPU ID
            safety_margin: 安全边际比例
            
        Returns:
            float: 可用显存(GB)
        """
        gpu_info = self.get_gpu_memory_info()
        
        if not gpu_info['success']:
            return 0.0
        
        for gpu in gpu_info['gpus']:
            if gpu['id'] == gpu_id:
                available_memory = gpu['memory']['free']
                safe_available = available_memory * (1 - safety_margin)
                return safe_available
        
        return 0.0
```

## 3. 实际应用示例

### 3.1 在任务处理器中的应用

```python
class TaskProcessor:
    def __init__(self, task_manager, socketio=None, optimized_whisper_system=None, 
                 transcription_processor=None, gpu_manager=None):
        self.gpu_manager = gpu_manager
        # ... 其他初始化代码
    
    def check_memory_sufficient(self, model_name, required_memory, gpu_id=None):
        """
        检查显存是否足够
        """
        if self.gpu_manager:
            # 使用GPU管理器获取最新显存信息
            gpu_info = self.gpu_manager.get_gpu_info()
        else:
            # 备用方案
            gpu_info = self._get_gpu_info_fallback()
        
        if not gpu_info['success']:
            return False, 0, 0
        
        # 计算可用显存
        if gpu_id is not None:
            # 检查指定GPU
            for gpu in gpu_info['gpus']:
                if gpu['id'] == gpu_id:
                    available_memory = gpu['memory']['free']
                    safe_available = available_memory * (1 - config.MEMORY_SAFETY_MARGIN)
                    return safe_available >= required_memory, safe_available, gpu_id
        else:
            # 检查所有GPU
            for gpu in gpu_info['gpus']:
                available_memory = gpu['memory']['free']
                safe_available = available_memory * (1 - config.MEMORY_SAFETY_MARGIN)
                if safe_available >= required_memory:
                    return True, safe_available, gpu['id']
        
        return False, 0, None
```

### 3.2 在显存预估池中的应用

```python
class MemoryEstimationPool:
    def get_estimated_memory_usage(self, gpu_id, model_name):
        """
        获取模型预估显存使用量
        """
        # 从预估表中获取基础值
        base_memory = self._get_default_estimation(model_name)
        
        # 可以在这里加入动态调整逻辑
        # 比如根据GPU型号、当前负载等调整预估值
        
        return base_memory
    
    def can_allocate_model(self, gpu_id, model_name, required_memory):
        """
        检查是否可以在指定GPU上分配模型
        """
        # 获取当前GPU的可用显存
        available_memory = self.gpu_info_manager.get_available_memory(
            gpu_id, 
            config.MEMORY_SAFETY_MARGIN
        )
        
        return available_memory >= required_memory
```

## 4. 显存查询的最佳实践

### 4.1 缓存机制
```python
# 避免频繁查询GPU信息，使用缓存机制
class CachedGPUQuery:
    def __init__(self, cache_duration=30):
        self.cache_duration = cache_duration
        self.cache = {}
        self.last_update = {}
    
    def get_memory_info(self):
        current_time = time.time()
        
        # 检查缓存是否有效
        if (current_time - self.last_update.get('memory', 0) < self.cache_duration and
            'memory' in self.cache):
            return self.cache['memory']
        
        # 查询新数据
        memory_info = self._query_memory()
        self.cache['memory'] = memory_info
        self.last_update['memory'] = current_time
        return memory_info
```

### 4.2 错误处理
```python
def safe_get_gpu_memory():
    """
    安全获取GPU内存信息
    """
    try:
        return get_pytorch_gpu_memory()
    except Exception as e:
        print(f"获取GPU内存信息失败: {e}")
        # 返回默认值或备用方案
        return {'success': False, 'error': str(e), 'gpus': []}
```

## 5. 性能考虑

### 5.1 查询频率控制
- 避免过于频繁的查询（建议每30秒一次）
- 在关键节点才进行查询（如任务启动前）
- 使用异步查询避免阻塞主线程

### 5.2 内存使用监控
```python
def monitor_memory_usage():
    """
    监控内存使用情况
    """
    # 定期记录内存使用情况
    # 用于性能分析和优化
    pass
```

## 6. 实际部署建议

1. **生产环境**：建议使用PyTorch API + 缓存机制
2. **开发环境**：可以使用简化版本的查询方法
3. **混合方案**：结合多种查询方法提高可靠性
4. **监控告警**：设置显存使用率阈值告警

通过以上方法，我们可以准确获取GPU的剩余显存信息，为动态显存决策提供可靠的数据支撑。
