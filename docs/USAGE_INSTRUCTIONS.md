# Whisper 音频转录系统使用说明

## 功能特性

1. **多文件上传**：支持同时上传多个音频文件
2. **自动文件选择**：开始转录时自动选择所有上传的文件
3. **多语言支持**：支持10种常用语言的转录
4. **GPU加速**：支持GPU加速转录以提高性能
5. **实时监控**：实时显示转录进度和状态

## 使用步骤

### 1. 文件上传
- 在左侧"文件上传"区域，可以通过拖拽或点击选择文件
- 支持的音频格式包括：MP3、WAV、FLAC等
- 上传的文件会显示在"上传的文件"表格中

### 2. 选择转录参数
- **模型选择**：选择Whisper模型（tiny/base/small/medium/large）
- **转录语言**：选择转录语言（支持10种常用语言）
- **GPU选择**：选择使用的GPU（如无GPU则使用CPU）

### 3. 开始转录
- 点击"开始转录"按钮
- 系统会自动选择所有上传的文件进行转录
- 转录进度会在右侧"系统日志"区域实时显示

### 4. 查看结果
- 转录完成后，结果文件会出现在"转录结果"表格中
- 可以点击下载按钮下载转录结果

## 技术细节

### 支持的语言
- 中文 (zh)
- 英语 (en)
- 日语 (ja)
- 韩语 (ko)
- 法语 (fr)
- 德语 (de)
- 西班牙语 (es)
- 俄语 (ru)
- 阿拉伯语 (ar)
- 葡萄牙语 (pt)

### 模型内存需求
- tiny: ~1GB
- base: ~1GB
- small: ~2GB
- medium: ~5GB
- large: ~10GB
- large-v2: ~10GB
- large-v3: ~10GB
- turbo: ~6GB (推荐，速度快)

### GPU支持
- 系统会自动检测可用的GPU
- 可在设置中选择特定GPU进行转录
- 如无GPU则默认使用CPU

## 系统要求

- Python 3.8+
- PyTorch 2.1.0+
- Whisper模型
- 至少1GB内存（推荐4GB以上）

## 部署说明

```bash
# 激活conda环境
D:\APP\env\whisper\Scripts\activate.ps1

# 安装依赖
pip install -r requirements.txt

# 运行应用
python main.py
```

## API接口

### 文件上传
```
POST /upload
Content-Type: multipart/form-data
Files: audio files
```

### 开始转录
```
POST /transcribe
Content-Type: application/json
Body: {
  "files": ["file1.mp3", "file2.wav"],
  "model": "base",
  "language": "zh",
  "gpus": [0]
}
```

### 获取GPU信息
```
GET /gpu_info
```

### 获取队列状态
```
GET /queue_state
