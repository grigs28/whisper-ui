#!/usr/bin/env python3
"""
显存计算示例脚本
演示如何计算不同场景下的显存需求
"""

def calculate_memory_requirement(model_name: str, audio_duration: int, segment_duration: int = 30):
    """
    计算显存需求
    
    Args:
        model_name: 模型名称
        audio_duration: 音频时长（秒）
        segment_duration: 分段时长（秒）
    
    Returns:
        dict: 包含计算结果的字典
    """
    
    # 基础模型显存需求
    model_memory_requirements = {
        'tiny': 1.0,
        'tiny.en': 1.0,
        'base': 1.0,
        'base.en': 1.0,
        'small': 2.0,
        'small.en': 2.0,
        'medium': 5.0,
        'medium.en': 5.0,
        'large': 10.0,
        'large-v1': 10.0,
        'large-v2': 10.0,
        'large-v3': 10.0,
        'large-v3-turbo': 10.0,
        'turbo': 6.0
    }
    
    # 获取基础显存需求
    base_memory = model_memory_requirements.get(model_name, 5.0)
    
    # 计算时长因子
    if audio_duration <= segment_duration:
        duration_factor = 1.0
    else:
        segments = audio_duration / segment_duration
        
        # 长音频额外缓冲（超过5分钟）
        if segments > 10:  # 5分钟 = 10个30秒分段
            extra_buffer = (segments - 10) * 0.08
            duration_factor = 1.0 + extra_buffer
        else:
            duration_factor = 1.0
        
        # 超长音频额外缓冲（超过10分钟）
        if segments > 20:  # 10分钟 = 20个30秒分段
            extra_buffer = (segments - 20) * 0.05
            duration_factor += extra_buffer
    
    # 计算总显存需求
    total_memory = base_memory * duration_factor
    
    return {
        'model_name': model_name,
        'audio_duration': audio_duration,
        'base_memory': base_memory,
        'duration_factor': duration_factor,
        'total_memory': total_memory,
        'segments': audio_duration / segment_duration
    }

def print_memory_calculation(result):
    """打印显存计算结果"""
    print(f"模型: {result['model_name']}")
    print(f"音频时长: {result['audio_duration']}秒 ({result['audio_duration']/60:.1f}分钟)")
    print(f"分段数: {result['segments']:.1f}")
    print(f"基础显存: {result['base_memory']:.1f}GB")
    print(f"时长因子: {result['duration_factor']:.2f}")
    print(f"总显存需求: {result['total_memory']:.1f}GB")
    print("-" * 50)

def main():
    """主函数"""
    print("=" * 60)
    print("显存计算示例")
    print("=" * 60)
    
    # 测试场景
    test_scenarios = [
        # 短音频
        ('tiny', 60),      # 1分钟
        ('small', 180),    # 3分钟
        ('medium', 300),   # 5分钟
        
        # 中等长度音频
        ('medium', 600),   # 10分钟
        ('large', 900),    # 15分钟
        
        # 长音频
        ('medium', 1200),  # 20分钟
        ('large', 1800),   # 30分钟
        
        # 超长音频
        ('large', 3600),   # 60分钟
    ]
    
    for model, duration in test_scenarios:
        result = calculate_memory_requirement(model, duration)
        print_memory_calculation(result)
    
    print("\n" + "=" * 60)
    print("GPU显存池状态示例")
    print("=" * 60)
    
    # GPU显存池状态示例
    gpu_examples = [
        {'gpu_id': 0, 'total_memory': 24.0, 'allocated_memory': 0.0, 'reserved_memory': 1.0, 'safety_margin': 0.1},
        {'gpu_id': 1, 'total_memory': 24.0, 'allocated_memory': 5.0, 'reserved_memory': 1.0, 'safety_margin': 0.1},
        {'gpu_id': 2, 'total_memory': 24.0, 'allocated_memory': 15.0, 'reserved_memory': 1.0, 'safety_margin': 0.1},
    ]
    
    for gpu in gpu_examples:
        # 计算可用显存
        free_memory = max(0, gpu['total_memory'] - gpu['allocated_memory'] - gpu['reserved_memory'])
        available_memory = max(0, free_memory - (gpu['total_memory'] * gpu['safety_margin']))
        utilization = (gpu['allocated_memory'] / gpu['total_memory']) * 100
        
        print(f"GPU {gpu['gpu_id']}:")
        print(f"  总显存: {gpu['total_memory']:.1f}GB")
        print(f"  已分配: {gpu['allocated_memory']:.1f}GB")
        print(f"  预留: {gpu['reserved_memory']:.1f}GB")
        print(f"  空闲: {free_memory:.1f}GB")
        print(f"  可用: {available_memory:.1f}GB")
        print(f"  利用率: {utilization:.1f}%")
        print("-" * 30)
    
    print("\n" + "=" * 60)
    print("任务分配示例")
    print("=" * 60)
    
    # 任务分配示例
    tasks = [
        {'id': 'task1', 'model': 'medium', 'duration': 300},   # 5分钟
        {'id': 'task2', 'model': 'large', 'duration': 600},    # 10分钟
        {'id': 'task3', 'model': 'small', 'duration': 180},    # 3分钟
    ]
    
    gpu_available = 20.0  # 20GB可用显存
    
    print(f"GPU可用显存: {gpu_available:.1f}GB")
    print()
    
    for task in tasks:
        result = calculate_memory_requirement(task['model'], task['duration'])
        can_allocate = result['total_memory'] <= gpu_available
        
        print(f"任务 {task['id']}:")
        print(f"  模型: {task['model']}")
        print(f"  时长: {task['duration']}秒")
        print(f"  需要显存: {result['total_memory']:.1f}GB")
        print(f"  可分配: {'✅' if can_allocate else '❌'}")
        
        if can_allocate:
            gpu_available -= result['total_memory']
            print(f"  分配后剩余: {gpu_available:.1f}GB")
        print("-" * 30)

if __name__ == "__main__":
    main()
