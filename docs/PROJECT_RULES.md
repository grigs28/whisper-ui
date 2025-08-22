# 项目规则文件

## 项目概述

Whisper音频转录系统 - 基于OpenAI Whisper的现代化音频转录系统，提供直观的Web界面，支持多文件批量处理、实时进度监控和GPU加速。

## 环境要求

### 必需环境
- **Python**: 3.8+
- **Conda**: 用于环境管理
- **FFmpeg**: 音频处理依赖
- **CUDA**: GPU加速支持（可选）

### 环境激活
```bash
# 必须使用whisper环境
conda activate whisper
```

## 启动规范

### 程序启动命令
```bash
# 标准启动命令
conda activate whisper
python main.py
```

### 启动参数
- **默认端口**: 5552
- **默认地址**: 127.0.0.1
- **调试模式**: 通过环境变量DEBUG控制

### 启动日志
```bash
# 创建启动日志（可选）
python main.py 2>&1 | tee logs/startup.log
```

## 文件组织规范

### 目录结构
```
whisper-ui/
├── main.py                    # 主程序入口
├── config.py                  # 配置文件
├── requirements.txt           # 依赖列表
├── README.md                  # 项目说明
├── version.md                 # 版本信息
├── .gitignore                 # Git忽略规则
├── docs/                      # 文档目录
│   ├── WEBSOCKET_FIX_SUMMARY.md
│   ├── SIMPLIFIED_CHINESE_OUTPUT_SUMMARY.md
│   ├── DEVELOPMENT_GUIDELINES.md
│   └── ...
├── logs/                      # 日志目录
│   ├── app.log               # 主应用日志
│   ├── app_timed.log         # 时间轮转日志
│   ├── startup.log           # 启动日志
│   └── .gitkeep
├── test/                      # 测试目录（不提交Git）
│   ├── README.md             # 测试说明
│   ├── websocket/            # WebSocket测试
│   ├── output_formats/       # 输出格式测试
│   └── ...
├── core/                      # 核心模块
├── utils/                     # 工具模块
├── static/                    # 静态资源
├── templates/                 # 模板文件
├── uploads/                   # 上传文件目录
├── outputs/                   # 输出文件目录
└── models/                    # 模型文件目录
```

### 文件命名规范

#### 代码文件
- **Python文件**: 使用小写字母和下划线，如 `main.py`, `config.py`
- **模块文件**: 使用描述性名称，如 `transcription_saver.py`
- **类文件**: 使用PascalCase，如 `GPUManager.py`

#### 文档文件
- **技术文档**: 使用英文大写和下划线，如 `WEBSOCKET_FIX_SUMMARY.md`
- **使用说明**: 使用英文，如 `USAGE_INSTRUCTIONS.md`
- **开发指南**: 使用英文，如 `DEVELOPMENT_GUIDELINES.md`

#### 日志文件
- **应用日志**: `app.log`
- **时间轮转日志**: `app_timed.log`
- **启动日志**: `startup.log`
- **性能日志**: `performance.log`

## Git管理规范

### 忽略规则
```gitignore
# 日志文件
logs/*
!logs/.gitkeep

# 测试目录
test/
test_*.py
*_test.py
test_results/
test_outputs/

# 上传和输出文件
uploads/*
!uploads/.gitkeep
outputs/*
!outputs/.gitkeep

# 模型文件
*.pt
*.bin
*.safetensors
models/

# Python缓存
__pycache__/
*.py[cod]

# 环境文件
.env
venv/
env/
```

### 提交规范
```bash
# 功能开发
git commit -m "feat: 添加WebSocket连接修复功能"

# 问题修复
git commit -m "fix: 修复F5刷新后的WebSocket错误"

# 文档更新
git commit -m "docs: 更新项目规则文件"

# 测试相关
git commit -m "test: 添加输出格式转换测试"
```

## 开发规范

### 代码风格
- **Python**: 遵循PEP 8规范
- **JavaScript**: 使用ES6+语法
- **HTML/CSS**: 使用Bootstrap框架

### 注释规范
```python
def convert_to_simplified(self, text: str) -> str:
    """将繁体中文转换为简体中文
    
    Args:
        text: 需要转换的文本
        
    Returns:
        转换后的简体中文文本
    """
    if not self.converter or not text:
        return text
    
    try:
        return self.converter.convert(text)
    except Exception as e:
        logger.warning(f"繁体转简体转换失败: {e}")
        return text
```

### 日志规范
```python
# 系统日志
logger.system("系统启动成功")

# 错误日志
logger.error(f"处理失败: {str(e)}")

# 信息日志
logger.info("任务已提交")

# 调试日志
logger.debug("详细调试信息")
```

## 功能规范

### WebSocket连接
- **自动重连**: 支持断线自动重连
- **错误处理**: 完善的错误恢复机制
- **心跳检测**: 定期心跳保持连接

### 输出格式
- **支持格式**: TXT, SRT, VTT, JSON
- **简体转换**: 所有格式自动转换为简体中文
- **编码格式**: UTF-8编码

### 文件处理
- **上传限制**: 最大1000MB
- **格式支持**: MP3, WAV, FLAC, M4A, OGG
- **批量处理**: 支持多文件同时上传

## 测试规范

### 测试目录结构
```
test/
├── README.md                 # 测试说明
├── websocket/               # WebSocket测试
│   ├── connection_test.py   # 连接测试
│   └── results/             # 测试结果
├── output_formats/          # 输出格式测试
│   ├── format_test.py       # 格式转换测试
│   └── results/             # 测试结果
└── integration/             # 集成测试
    ├── full_workflow_test.py # 完整工作流测试
    └── results/             # 测试结果
```

### 测试脚本规范
```python
#!/usr/bin/env python3
"""
测试脚本说明
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_function():
    """测试函数"""
    print("开始测试...")
    # 测试逻辑
    print("测试完成")

if __name__ == "__main__":
    test_function()
```

## 部署规范

### 生产环境
```bash
# 设置环境变量
export DEBUG=False
export HOST=0.0.0.0
export PORT=5552

# 启动应用
conda activate whisper
python main.py
```

### 开发环境
```bash
# 设置环境变量
export DEBUG=True
export HOST=127.0.0.1
export PORT=5552

# 启动应用
conda activate whisper
python main.py
```

## 维护规范

### 日志管理
- **定期清理**: 定期清理过期的日志文件
- **日志轮转**: 使用日志轮转避免文件过大
- **错误监控**: 监控错误日志及时处理问题

### 性能优化
- **GPU管理**: 合理分配GPU资源
- **内存管理**: 监控内存使用情况
- **并发控制**: 根据系统资源调整并发数

### 安全规范
- **文件上传**: 验证文件类型和大小
- **路径安全**: 防止路径遍历攻击
- **环境变量**: 敏感信息使用环境变量

## 问题处理

### 常见问题
1. **WebSocket连接错误**: 检查网络和防火墙设置
2. **GPU显存不足**: 调整并发数或使用CPU模式
3. **文件上传失败**: 检查文件大小和格式
4. **转录失败**: 检查音频文件完整性

### 调试方法
1. **查看日志**: `tail -f logs/app.log`
2. **检查状态**: 访问 `/gpu_info` 接口
3. **测试连接**: 使用测试脚本验证功能
4. **监控资源**: 使用系统监控工具

## 更新记录

### 版本历史
- **v1.0.0**: 基础功能实现
- **v1.1.0**: 添加WebSocket修复
- **v1.2.0**: 添加简体中文转换
- **v1.3.0**: 优化文件组织结构

### 变更记录
- 2025-08-22: 创建项目规则文件
- 2025-08-22: 修复WebSocket连接问题
- 2025-08-22: 实现输出格式简体转换
- 2025-08-22: 优化文件目录结构

---

**注意**: 本规则文件应定期更新，确保与项目发展保持一致。
