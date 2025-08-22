# 🎵 Whisper 音频转录系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![OpenAI Whisper](https://img.shields.io/badge/OpenAI-Whisper-orange.svg)](https://github.com/openai/whisper)
[![Flask](https://img.shields.io/badge/Flask-2.0+-red.svg)](https://flask.palletsprojects.com/)

一个基于 OpenAI Whisper 的现代化音频转录系统，提供直观的 Web 界面，支持多文件批量处理、实时进度监控和 GPU 加速。

## 🤖 开发历程

本项目在 [grigs28/whisper-web-transcriber](https://github.com/grigs28/whisper-web-transcriber) 的基础上进行了深度重构与拓展，新增了多线程处理机制。在开发过程中，我们采用了前沿的 AI 辅助开发模式：

1. **🎯 需求分析与架构设计**：由 **Trae AI** 生成详细的开发提示词和技术规范
2. **🏗️ 基础代码生成**：使用本地部署的 **cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-8bit** 模型创建项目文件和目录结构
3. **✨ 精细化调优**：由 **Trae AI** 完成界面优化、功能完善和用户体验提升
4. **🤖 AI助手集成**：由 **Cursor** 提供智能代码生成、问题诊断和开发指导支持

[English](#english) | [简体中文](#简体中文)

## ✨ 功能特性

- 🎯 **智能转录**: 基于OpenAI Whisper的高精度语音识别
- 📁 **批量处理**: 支持多文件上传和批量转录
- 🌍 **多语言支持**: 支持中文、英文、日文等10+种常见语言
- ⚡ **GPU加速**: 自动检测NVIDIA GPU并启用加速
- 📊 **实时监控**: 任务队列状态和GPU使用情况实时监控
- 🎨 **现代界面**: 响应式设计，支持拖拽上传
- 🔄 **WebSocket通信**: 实时进度更新
- 📝 **详细日志**: 完整的操作日志和错误追踪



## 🚀 快速开始

### 📋 环境要求

- Python 3.8+
- pip
- FFmpeg（音频处理依赖）
- （可选）NVIDIA GPU + CUDA 支持

#### FFmpeg 安装

**openEuler、Ubuntu 或 Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Arch Linux:**
```bash
sudo pacman -S ffmpeg
```

**macOS (使用 Homebrew):**
```bash
brew install ffmpeg
```

**Windows (使用 Chocolatey):**
```bash
choco install ffmpeg
```

**Windows (使用 Scoop):**
```bash
scoop install ffmpeg
```

### 🔧 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/grigs28/whisper-ui.git
   cd whisper-ui
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **启动应用**
   ```bash
   python main.py
   ```

4. **访问应用**
   
   在浏览器中打开: `http://localhost:5552`

## 📖 使用说明

### 🎯 基本操作

1. **上传音频文件**
   - 支持格式：MP3, WAV, M4A, FLAC, OGG
   - 可拖拽文件到上传区域
   - 支持多文件同时上传

2. **选择转录参数**
   - 模型选择：tiny, base, small, medium, large, large-v2, large-v3, turbo
   - 语言选择：自动检测或手动指定
   - 输出格式：TXT, SRT, VTT, JSON

3. **开始转录**
   - 点击"开始转录"按钮
   - 实时查看转录进度
   - 转录完成后自动下载结果

### 🔧 高级功能

- **批量转录**: 一次性处理多个音频文件
- **任务队列**: 查看当前转录任务状态
- **GPU监控**: 实时显示GPU使用情况
- **日志查看**: 查看详细的操作日志

## 🌍 支持的语言

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

## 🏗️ 技术架构

### 🔧 后端技术栈

- **Flask**: Web框架
- **OpenAI Whisper**: 语音识别引擎
- **WebSocket**: 实时通信
- **Threading**: 多线程任务处理
- **Logging**: 日志系统

### 🎨 前端技术栈

- **Bootstrap 5**: UI框架
- **JavaScript**: 交互逻辑
- **WebSocket**: 实时通信
- **Drag & Drop API**: 文件拖拽上传

### 🛠️ 开发工具

- **Cursor**: AI驱动的智能开发助手
  - 代码生成和优化
  - 项目规范维护
  - 问题诊断和解决
  - 开发效率提升
- **Git**: 版本控制
- **Conda**: 环境管理
- **FFmpeg**: 音频处理

### 📁 项目结构

```
whisper-ui/
├── main.py              # 主程序入口
├── requirements.txt     # 依赖列表
├── .cursor/             # Cursor AI助手配置
│   ├── rules/          # AI助手规则文件
│   └── settings.json   # Cursor配置文件
├── static/             # 静态资源
│   ├── css/           # 样式文件
│   └── js/            # JavaScript文件
├── templates/          # HTML模板
├── uploads/           # 上传文件目录
├── outputs/           # 输出文件目录
├── logs/              # 日志文件目录
└── test/              # 测试目录（本地开发）
```

## 🔧 故障排除

### ❓ 常见问题

1. **模型下载失败**
   - 检查网络连接
   - 尝试使用代理
   - 手动下载模型文件

2. **GPU未被识别**
   - 确认已安装CUDA
   - 检查PyTorch GPU支持
   - 查看系统日志

3. **转录速度慢**
   - 使用更小的模型（如tiny或base）
   - 推荐使用turbo模型（平衡速度和精度）
   - 确保GPU正常工作
   - 检查系统资源使用情况

### 📋 日志查看

应用运行时会在 `logs/` 目录下生成详细的日志文件，可以通过查看日志来诊断问题。

### ⚡ GPU支持
如果系统有NVIDIA GPU且已安装CUDA，程序会自动检测并使用GPU加速转录。否则将使用CPU进行转录。

## 🔍 GPU信息获取

系统提供了多种方式来获取GPU信息：

1. **HTTP API接口**：访问 `/gpu_info` 接口可获取当前GPU的详细信息，包括名称、总内存、已分配内存、可用内存等。

2. **前端页面**：Web界面会自动加载并显示GPU使用情况。

3. **后端调用**：在代码中可通过以下方式获取GPU信息：
   - `gpu_manager.get_gpu_info()` 方法
   - `optimized_whisper_system.get_system_status()` 方法，其中包含 `gpu_status` 字段

## 🤝 贡献指南

欢迎贡献代码！请随时提交 Pull Request。

1. Fork 本项目
2. 创建您的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系方式

如果您有任何问题或建议，请通过以下方式联系我们：

- 提交 [Issue](https://github.com/grigs28/whisper-ui/issues)

---

## English
**🎵 Whisper Audio Transcription System**

A modern audio transcription system based on OpenAI Whisper, featuring an intuitive web interface with multi-file batch processing, real-time progress monitoring, and GPU acceleration.

**🤖 Development History**

This project is built upon [grigs28/whisper-web-transcriber](https://github.com/grigs28/whisper-web-transcriber) with extensive refactoring and enhancements, including the addition of multi-threading processing capabilities. During development, we adopted cutting-edge AI-assisted development methodologies:

1. **🎯 Requirements Analysis & Architecture Design**: Detailed development prompts and technical specifications generated by **Trae AI**
2. **🏗️ Base Code Generation**: Project files and directory structure created using locally deployed **cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-8bit** model
3. **✨ Fine-tuning & Optimization**: Interface optimization, feature enhancement, and user experience improvements completed by **Trae AI**

This AI-collaborative development approach ensures the perfect balance between code quality and development efficiency.

**✨ Key Features**

- 🎯 **Smart Transcription**: High-accuracy speech recognition powered by OpenAI Whisper
- 📁 **Batch Processing**: Support for multiple file uploads and batch transcription
- 🌍 **Multi-language Support**: Support for 10+ common languages
- ⚡ **GPU Acceleration**: Automatic NVIDIA GPU detection and utilization
- 📊 **Real-time Monitoring**: Live task queue status and GPU usage monitoring
- 🎨 **Modern Interface**: Responsive design with drag-and-drop upload
- 🔄 **WebSocket Communication**: Real-time progress updates
- 📝 **Comprehensive Logging**: Detailed operation logs and error tracking

**📋 Requirements**

- Python 3.8+
- pip
- FFmpeg (audio processing dependency)
- (Optional) NVIDIA GPU + CUDA support

**FFmpeg Installation**

**openEuler, Ubuntu or Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Arch Linux:**
```bash
sudo pacman -S ffmpeg
```

**macOS (using Homebrew):**
```bash
brew install ffmpeg
```

**Windows (using Chocolatey):**
```bash
choco install ffmpeg
```

**Windows (using Scoop):**
```bash
scoop install ffmpeg
```

**🚀 Quick Start**

1. **Clone the repository**
   ```bash
   git clone https://github.com/grigs28/whisper-ui.git
   cd whisper-ui
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python main.py
   ```

4. **Access the application**
   
   Open your browser and visit: `http://localhost:5552`

**📖 Documentation**

For detailed documentation, please refer to the [docs](docs/) directory.

**🤝 Contributing**

Contributions are welcome! Please feel free to submit a Pull Request.

**📄 License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

⭐ **如果这个项目对您有帮助，请给我们一个 Star！**

⭐ **If this project helps you, please give us a Star!**
