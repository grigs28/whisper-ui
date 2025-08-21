/**
 * 转录控制器组件
 */

class TranscriptionController {
    constructor() {
        this.isTranscribing = false; // 添加转录状态标志
        this.init();
    }

    /**
     * 初始化
     */
    init() {
        // 绑定开始转录按钮事件
        const startBtn = document.getElementById('startTranscriptionBtn');
        if (startBtn) {
            startBtn.addEventListener('click', () => {
                this.startTranscription();
            });
        }
    }

    /**
     * 开始转录
     */
    async startTranscription() {
        // 防止重复提交
        if (this.isTranscribing) {
            showNotification('转录任务正在进行中，请稍候...', 'warning');
            return;
        }
        
        // 获取选中的文件
        const selectedFiles = Array.from(fileManager.selectedFiles);
        if (selectedFiles.length === 0) {
            showNotification('请至少选择一个文件进行转录', 'warning');
            return;
        }

        // 获取转录设置
        const model = document.getElementById('modelSelector')?.value || 'base';
        const language = document.getElementById('languageSelector')?.value || 'auto';
        const gpu = document.getElementById('gpuSelector')?.value || '';
        const outputFormat = document.getElementById('outputFormatSelector')?.value || 'json';

        try {
            this.isTranscribing = true; // 设置转录状态
            statusLogger.info('开始转录任务...', { files: selectedFiles, model, language, gpu, outputFormat });
            // 发送转录任务到服务器
            const response = await fetch('/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    files: selectedFiles,
                    model: model,
                    language: language,
                    gpus: gpu ? [gpu] : [], // 确保传递数组格式
                    output_format: outputFormat
                })
            });

            const result = await response.json();

            if (result.success) {
                statusLogger.success('转录任务已启动', result);
                showNotification('转录任务已启动', 'success');
                // 清空选中文件集合
                fileManager.selectedFiles.clear();
                // 更新UI
                fileManager.updateSelectAllButton();
                // 刷新任务队列显示
                if (typeof queueManager !== 'undefined') {
                    queueManager.loadQueueState();
                }
            } else {
                statusLogger.error('转录任务启动失败', result);
                showNotification(`转录失败: ${result.error}`, 'danger');
            }
        } catch (error) {
            statusLogger.error('转录过程中发生错误', { error: error.message });
            showNotification('转录过程中发生错误', 'danger');
        } finally {
            this.isTranscribing = false; // 重置转录状态
        }
    }

    /**
     * 提交转录任务
     */
    async submitTranscriptionTask(files, model, language, gpus) {
        try {
            statusLogger.info('提交转录任务', { files, model, language, gpus });
            const response = await fetch('/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    files: files,
                    model: model,
                    language: language,
                    gpus: gpus
                })
            });

            const result = await response.json();
            if (result.success) {
                statusLogger.success('转录任务已提交', result);
                return result;
            } else {
                statusLogger.error('转录任务提交失败', result);
                return result;
            }
        } catch (error) {
            statusLogger.error('提交转录任务时发生错误', { error: error.message });
            throw error;
        }
    }

    /**
     * 获取转录任务状态
     */
    async getTaskStatus(taskId) {
        try {
            const response = await fetch(`/task_status/${taskId}`);
            const result = await response.json();
            if (result.success) {
                // 根据任务状态记录不同级别的日志
                switch(result.status) {
                    case 'processing':
                        statusLogger.processing('转录任务处理中', { taskId, status: result.status });
                        break;
                    case 'completed':
                        statusLogger.success('转录任务已完成', { taskId, status: result.status });
                        break;
                    case 'failed':
                        statusLogger.error('转录任务失败', { taskId, status: result.status, error: result.error });
                        break;
                    default:
                        statusLogger.info('转录任务状态更新', { taskId, status: result.status });
                }
                return result;
            } else {
                statusLogger.error('获取任务状态失败', { taskId, error: result.error });
                return result;
            }
        } catch (error) {
            statusLogger.error('获取任务状态时发生错误', { taskId, error: error.message });
            throw error;
        }
    }

    /**
     * 清除日志
     */
    clearLogs() {
        if (confirm('确定要清除所有日志吗？')) {
            statusLogger.clear();
            statusLogger.info('日志已清除');
        }
    }

    /**
     * 更新任务队列显示
     */
    updateQueueDisplay() {
        // 这里可以实现更新队列显示的逻辑
        // 目前通过刷新页面来更新
        location.reload();
    }
}

// 创建全局转录控制器实例
const transcriptionController = new TranscriptionController();

// 全局函数用于开始转录
function startTranscription() {
    transcriptionController.startTranscription();
}

// 全局函数用于清除日志
function clearLogs() {
    transcriptionController.clearLogs();
}
