# 日志系统优化说明

## 概述

本次优化对whisper-ui的日志系统进行了全面升级，实现了以下功能：

1. **日志级别标准化** - 统一日志级别和格式
2. **性能监控日志** - 自动监控关键操作的性能
3. **日志轮转** - 支持按大小和时间轮转日志文件
4. **结构化日志** - 支持JSON格式的结构化日志输出

## 新增功能

### 1. 日志级别标准化

- 统一使用标准日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
- 为不同类型的操作添加了专门的日志方法：
  - `logger.system()` - 系统消息
  - `logger.user()` - 用户操作
  - `logger.error_msg()` - 错误消息
  - `logger.warning_msg()` - 警告消息
  - `logger.transcription()` - 转录任务状态
  - `logger.file_op()` - 文件操作
  - `logger.gpu_info()` - GPU信息
  - `logger.client_connected()` / `logger.client_disconnected()` - 客户端连接状态

### 2. 性能监控日志

#### 自动性能监控（装饰器）
```python
from utils.logger import performance_monitor_decorator

class MyService:
    @performance_monitor_decorator("服务处理")
    def process_data(self, data):
        # 你的业务逻辑
        return result
```

#### 手动性能监控
```python
from utils.logger import performance_monitor
import time

start_time = time.time()
# 执行操作
result = some_operation()
duration = time.time() - start_time

# 记录性能数据
performance_monitor(
    operation="some_operation",
    duration=duration,
    task_id="task_123",
    user_id="user_456"
)
```

### 3. 日志轮转

系统现在支持两种日志轮转方式：

#### 按大小轮转
- 当日志文件达到配置的大小时自动轮转
- 默认大小：10MB
- 保留备份文件数量：5个

#### 按时间轮转
- 每天午夜自动创建新的日志文件
- 保留30天的历史日志

### 4. 结构化日志

```python
from utils.logger import structured_log

# 记录结构化日志
structured_log(
    level="info",
    message="任务处理完成",
    task_id="task_123",
    operation="transcription",
    duration=1.5,
    status="success"
)
```

结构化日志以JSON格式输出，包含以下字段：
- `timestamp` - 时间戳
- `level` - 日志级别
- `logger` - 日志记录器名称
- `message` - 日志消息
- `module` - 模块名称
- `function` - 函数名称
- `line` - 行号
- `performance` - 性能数据（如果有）
- `task_id` - 任务ID（如果有）
- `user_id` - 用户ID（如果有）

## 配置选项

在 `config.py` 中新增了以下配置选项：

```python
# 是否启用结构化日志
ENABLE_STRUCTURED_LOGGING = True

# 是否启用性能监控日志
ENABLE_PERFORMANCE_MONITORING = True

# 性能监控日志文件路径
PERFORMANCE_LOG_FILE = os.path.join(BASE_DIR, 'logs', 'performance.log')

# 日志轮转配置 - 单个日志文件最大大小(MB)
LOG_MAX_SIZE = 10

# 日志轮转配置 - 保留的备份文件数量
LOG_BACKUP_COUNT = 5

# 日志轮转配置 - 按时间轮转的备份文件数量
TIMED_LOG_BACKUP_COUNT = 30
```

## 日志文件结构

优化后的系统会生成以下日志文件：

```
logs/
├── app.log                    # 主日志文件（按大小轮转）
├── app.log.1                 # 轮转备份文件
├── app.log.2                 # 轮转备份文件
├── app_timed.log             # 按时间轮转的日志文件
├── app_timed.log.2024-01-01  # 按日期轮转的备份文件
├── app_structured.json       # 结构化日志文件（JSON格式）
└── performance.log           # 性能监控日志文件
```

## 使用示例

完整的示例代码请参考 `examples/logging_example.py`。

### 基本使用
```python
from utils.logger import logger

# 记录不同类型的日志
logger.system("系统启动")
logger.user("用户登录")
logger.error_msg("处理失败", exception)
logger.transcription("转录任务开始", task_id="123", status="started")
```

### 性能监控
```python
from utils.logger import performance_monitor_decorator, performance_monitor

# 使用装饰器
@performance_monitor_decorator("数据处理")
def process_data(data):
    return data.upper()

# 手动监控
start_time = time.time()
result = process_data("test")
duration = time.time() - start_time
performance_monitor("数据处理", duration, task_id="123")
```

### 结构化日志
```python
from utils.logger import structured_log

structured_log(
    level="info",
    message="任务完成",
    task_id="123",
    operation="transcription",
    duration=1.5,
    status="success"
)
```

## WebSocket日志推送

系统仍然支持通过WebSocket将日志实时推送到前端，新增了对性能监控和结构化日志的支持：

- 性能监控日志以 `performance` 级别推送
- 结构化日志会自动解析并推送到前端
- 保持了原有的颜色编码和级别映射

## 注意事项

1. **性能影响**：结构化日志和性能监控会产生额外的性能开销，建议在生产环境中根据需要启用。

2. **磁盘空间**：日志轮转配置需要根据磁盘空间和日志量进行调整，避免日志文件占用过多磁盘空间。

3. **敏感信息**：结构化日志中不要包含敏感信息，如密码、密钥等。

4. **配置生效**：修改配置后需要重启应用才能生效。

## 故障排除

### 日志文件未生成
- 检查 `logs` 目录是否存在且有写入权限
- 检查配置文件中的路径是否正确
- 确认相应的日志功能是否启用

### 性能监控不工作
- 检查 `ENABLE_PERFORMANCE_MONITORING` 配置是否为 `True`
- 确认装饰器或手动调用是否正确
- 查看主日志文件中的错误信息

### 结构化日志格式错误
- 检查传入的参数是否可序列化为JSON
- 确认 `ENABLE_STRUCTURED_LOGGING` 配置是否为 `True`

## 迁移指南

现有的日志记录代码无需修改，新功能是向后兼容的。建议逐步采用新的日志方法来获得更好的日志管理体验。