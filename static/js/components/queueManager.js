// 引入定时器管理器
import timerManager from '../utils/timerManager.js';

/**
 * 任务队列管理组件
 */

class QueueManager {
    constructor() {
        this.queueItems = [];
        this.init();
    }

    /**
     * 初始化队列管理器
     */
    init() {
        this.setupEventListeners();
        this.loadQueueState();
        this.startTimeUpdater();
        this.startPeriodicRefresh();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 任务更新事件（由WebSocket接收）
        // 这部分将在WebSocket组件中处理
    }

    /**
     * 启动时间更新器
     */
    startTimeUpdater() {
        // 使用定时器管理器添加时间更新任务
        timerManager.addTask('queueTimeUpdate', () => {
            const hasProcessingTasks = this.queueItems.some(item => item.status === 'processing');
            if (hasProcessingTasks) {
                this.updateQueueDisplay(this.queueItems);
            }
        }, 0.5); // 每0.5个主周期执行一次(2.5秒)

        // 确保定时器管理器已启动
        if (!timerManager.isRunning) {
            timerManager.start(5000); // 设置5秒间隔
        }
    }

    /**
     * 停止时间更新器
     */
    stopTimeUpdater() {
        // 从定时器管理器中移除任务
        timerManager.removeTask('queueTimeUpdate');
    }

    /**
     * 启动定期刷新
     */
    startPeriodicRefresh() {
        // 每5秒刷新一次队列状态
        this.refreshInterval = setInterval(() => {
            this.loadQueueState();
        }, 5000);

        // 当页面失去焦点时停止刷新，获得焦点时恢复刷新
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (this.refreshInterval) {
                    clearInterval(this.refreshInterval);
                    this.refreshInterval = null;
                }
            } else {
                if (!this.refreshInterval) {
                    this.refreshInterval = setInterval(() => {
                        this.loadQueueState();
                    }, 5000);
                }
            }
        });
    }

    /**
     * 停止定期刷新
     */
    stopPeriodicRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    /**
     * 加载队列状态
     */
    async loadQueueState() {
        try {
            const response = await fetch('/queue_state');
            const queueState = await response.json();

            if (queueState.success) {
                this.updateQueueDisplay(queueState.items);
                this.updateQueueBadge(queueState.items.length);
                this.updateConcurrentInfo(queueState);
            }
        } catch (error) {
            statusLogger.warning('加载队列状态失败: ' + error.message);
        }
    }

    /**
     * 更新并发信息显示
     */
    updateConcurrentInfo(queueState) {
        const currentConcurrentEl = document.getElementById('currentConcurrent');
        const maxConcurrentEl = document.getElementById('maxConcurrent');

        if (currentConcurrentEl && queueState.current_running_tasks !== undefined) {
            currentConcurrentEl.textContent = queueState.current_running_tasks;
        }

        if (maxConcurrentEl && queueState.max_concurrent_tasks !== undefined) {
            maxConcurrentEl.textContent = queueState.max_concurrent_tasks;
        }
    }

    /**
     * 加载并发设置
     */
    async loadConcurrentSettings() {
        try {
            const response = await fetch('/concurrent_settings');
            const settings = await response.json();

            if (settings.success) {
                const maxConcurrentInput = document.getElementById('maxConcurrentInput');
                const modalCurrentRunning = document.getElementById('modalCurrentRunning');
                const modalQueueWaiting = document.getElementById('modalQueueWaiting');

                if (maxConcurrentInput) {
                    maxConcurrentInput.value = settings.max_concurrent_tasks;
                    maxConcurrentInput.min = settings.min_concurrent_tasks;
                    maxConcurrentInput.max = settings.max_limit;
                }

                if (modalCurrentRunning) {
                    modalCurrentRunning.textContent = settings.current_running_tasks;
                }

                // 计算等待中的任务数
                const queueResponse = await fetch('/queue_state');
                const queueState = await queueResponse.json();
                if (queueState.success && modalQueueWaiting) {
                    const waitingTasks = queueState.items.filter(item => item.status === 'pending').length;
                    modalQueueWaiting.textContent = waitingTasks;
                }
            }
        } catch (error) {
            statusLogger.error('加载并发设置失败: ' + error.message);
        }
    }

    /**
     * 保存并发设置
     */
    async saveConcurrentSettings() {
        try {
            const maxConcurrentInput = document.getElementById('maxConcurrentInput');
            const maxConcurrentTasks = parseInt(maxConcurrentInput.value);

            if (isNaN(maxConcurrentTasks) || maxConcurrentTasks < 1 || maxConcurrentTasks > 20) {
                alert('请输入有效的并发任务数（1-20）');
                return;
            }

            const response = await fetch('/concurrent_settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    max_concurrent_tasks: maxConcurrentTasks
                })
            });

            const result = await response.json();

            if (result.success) {
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('concurrentSettingsModal'));
                if (modal) {
                    modal.hide();
                }

                // 刷新队列状态
                this.loadQueueState();

                // 显示成功消息
                this.showMessage('并发设置已保存', 'success');
            } else {
                alert('保存失败: ' + result.error);
            }
        } catch (error) {
            statusLogger.error('保存并发设置失败: ' + error.message);
            alert('保存失败: ' + error.message);
        }
    }

    /**
     * 显示消息
     */
    showMessage(message, type = 'info') {
        // 创建临时消息提示
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alertDiv);

        // 3秒后自动移除
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.parentNode.removeChild(alertDiv);
            }
        }, 3000);
    }

    /**
     * 更新队列显示
     */
    updateQueueDisplay(items) {
        const queueItemsContainer = document.getElementById('queueItems');
        const queueInfo = document.getElementById('queueInfo');

        if (!queueItemsContainer) return;

        // 清空现有项目
        queueItemsContainer.innerHTML = '';

        if (items.length === 0) {
            // 显示空闲标签
            if (queueInfo) {
                queueInfo.style.display = 'block';
                queueInfo.innerHTML = '<span class="badge bg-success"><i class="fas fa-check-circle"></i> 空闲</span>';
            }

            queueItemsContainer.innerHTML = `
                <div class="text-center py-4">
                    <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                    <p class="text-muted">队列为空</p>
                </div>
            `;
            return;
        }

        // 有任务时隐藏空闲标签
        if (queueInfo) {
            queueInfo.style.display = 'none';
        }

        // 添加每个项目（包括排队和处理中的任务）
        items.forEach(item => {
            const itemElement = this.createQueueItemElement(item);
            queueItemsContainer.appendChild(itemElement);
        });
    }

    /**
     * 创建队列项元素
     */
    createQueueItemElement(item) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'queue-item card mb-2';

        // 使用filename字段或从files数组中提取文件名
        let displayName = '未知文件';
        if (item.filename) {
            displayName = item.filename;
        } else if (item.files && item.files.length > 0) {
            // 从文件路径中提取文件名
            const fileName = item.files[0].split('/').pop().split('\\').pop();
            displayName = fileName;
        }

        // 获取语言显示名称
        const languageMap = {
            'zh': '中文', 'en': '英语', 'ja': '日语', 'ko': '韩语',
            'fr': '法语', 'de': '德语', 'es': '西班牙语', 'ru': '俄语',
            'ar': '阿拉伯语', 'pt': '葡萄牙语'
        };
        const languageDisplay = languageMap[item.language] || item.language || '自动检测';

        // 计算转录时间
        let transcriptionTime = '';
        if (item.start_time && item.end_time) {
            const startTime = new Date(item.start_time);
            const endTime = new Date(item.end_time);
            const duration = Math.round((endTime - startTime) / 1000);
            const minutes = Math.floor(duration / 60);
            const seconds = duration % 60;
            transcriptionTime = `${minutes}分${seconds}秒`;
        } else if (item.start_time && item.status === 'processing') {
            const startTime = new Date(item.start_time);
            const now = new Date();
            const duration = Math.round((now - startTime) / 1000);
            const minutes = Math.floor(duration / 60);
            const seconds = duration % 60;
            transcriptionTime = `${minutes}分${seconds}秒`;
        }

        itemDiv.innerHTML = `
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">
                            <i class="fas fa-file-audio text-primary me-1"></i>
                            ${displayName}
                        </h6>
                        <div class="d-flex align-items-center text-muted small">
                            <span class="me-3">
                                <i class="fas fa-brain me-1"></i>
                                ${item.model || 'base'}
                            </span>
                            <span class="me-3">
                                <i class="fas fa-language me-1"></i>
                                ${languageDisplay}
                            </span>
                            ${transcriptionTime ? `
                            <span>
                                <i class="fas fa-stopwatch me-1"></i>
                                ${transcriptionTime}
                            </span>
                            ` : ''}
                        </div>
                    </div>
                    <div class="d-flex align-items-center">
                        <span class="badge bg-${this.getStatusBadgeClass(item.status)} me-2">
                            ${this.getStatusText(item.status)}
                        </span>
                    </div>
                </div>
                ${item.status === 'processing' ? `
                <div class="progress mb-1" style="height: 8px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                         role="progressbar" 
                         style="width: ${item.progress || 0}%"
                         aria-valuenow="${item.progress || 0}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center">
                    <small class="text-muted">${item.download_message || item.message || '处理中...'}</small>
                    <small class="text-muted">${item.download_progress || item.progress || 0}%</small>
                </div>
                ` : ''}
                ${item.download_progress && item.status === 'processing' ? `
                <div class="mt-2">
                    <div class="progress mb-1" style="height: 6px;">
                        <div class="progress-bar bg-info" 
                             role="progressbar" 
                             style="width: ${item.download_progress}%"
                             aria-valuenow="${item.download_progress}" 
                             aria-valuemin="0" 
                             aria-valuemax="100">
                        </div>
                    </div>
                    <small class="text-info">${item.download_message}</small>
                </div>
                ` : ''}
            </div>
        `;
        return itemDiv;
    }

    /**
     * 获取状态对应的徽章样式
     */
    getStatusBadgeClass(status) {
        switch (status) {
            case 'pending':
                return 'warning';
            case 'loading':
                return 'warning';
            case 'processing':
                return 'primary';
            case 'completed':
                return 'success';
            case 'failed':
                return 'danger';
            default:
                return 'secondary';
        }
    }

    /**
     * 获取状态文本
     */
    getStatusText(status) {
        switch (status) {
            case 'pending':
                return '待处理';
            case 'loading':
                return '加载中';
            case 'processing':
                return '处理中';
            case 'completed':
                return '已完成';
            case 'failed':
                return '失败';
            default:
                return status;
        }
    }

    /**
     * 更新队列徽章
     */
    updateQueueBadge(count) {
        const badge = document.getElementById('queueBadge');
        if (badge) {
            badge.textContent = count;
            badge.className = count > 0 ? 'badge bg-warning' : 'badge bg-secondary';
        }
    }

    /**
     * 更新任务状态
     */
    updateTaskStatus(taskData) {
        statusLogger.system('***【updateTaskStatus】更新本地队列状态 ***');
        // 更新本地队列状态
        const index = this.queueItems.findIndex(item => item.id === taskData.id);
        if (index !== -1) {
            this.queueItems[index] = { ...this.queueItems[index], ...taskData };
        } else {
            this.queueItems.push(taskData);
        }

        // 记录任务状态变化
        switch (taskData.status) {
            case 'pending':
                statusLogger.system('【updateTaskStatus】转录任务已加入队列', { task_id: taskData.id, files: taskData.files });
                break;
            case 'loading':
                statusLogger.info('【updateTaskStatus】正在加载模型', { task_id: taskData.id, model: taskData.model, message: taskData.message });
                break;
            case 'processing':
                statusLogger.system('【updateTaskStatus】转录任务开始处理', { task_id: taskData.id, files: taskData.files });
                break;
            case 'completed':
                statusLogger.success('【updateTaskStatus】转录任务完成', { task_id: taskData.id, files: taskData.files });
                // 转录完成后自动刷新输出文件列表
                if (window.fileManager) {
                    statusLogger.system('【updateTaskStatus】开始自动刷新输出文件列表');
                    // 直接调用已验证有效的刷新方法
                    window.fileManager.refreshFileList('output');
                    statusLogger.system('【updateTaskStatus】输出文件列表自动刷新完成');
                } else {
                    statusLogger.error('【updateTaskStatus】FileManager未找到，无法自动刷新输出文件列表');
                }
                break;

            case 'failed':
                statusLogger.error('【updateTaskStatus】转录任务失败', { task_id: taskData.id, error: taskData.error });
                break;
        }

        // 立即更新显示
        this.updateQueueDisplay(this.queueItems);
        this.updateQueueBadge(this.queueItems.length);

        // 如果任务完成或失败，5秒后从本地列表中移除
        if (taskData.status === 'completed' || taskData.status === 'failed') {
            setTimeout(() => {
                this.removeTaskFromLocalList(taskData.id);
            }, 5000);
        }

        // 同时从服务器刷新最新状态，确保数据同步
        this.loadQueueState();
    }

    /**
     * 从本地列表中移除任务
     */
    removeTaskFromLocalList(taskId) {
        const index = this.queueItems.findIndex(item => item.id === taskId);
        if (index !== -1) {
            this.queueItems.splice(index, 1);
            this.updateQueueDisplay(this.queueItems);
            this.updateQueueBadge(this.queueItems.length);
        }
    }

    /**
     * 更新下载进度
     */
    updateDownloadProgress(progressData) {
        const existingIndex = this.queueItems.findIndex(item => item.task_id === progressData.task_id);

        if (existingIndex !== -1) {
            // 更新任务的下载进度信息
            this.queueItems[existingIndex] = {
                ...this.queueItems[existingIndex],
                download_progress: progressData.progress,
                download_message: progressData.message,
                updated_at: new Date().toISOString()
            };

            // 更新显示
            this.updateQueueDisplay(this.queueItems);
        }
    }
}

// 创建全局队列管理器实例
const queueManager = new QueueManager();

// 全局函数用于更新任务状态
function updateTaskStatus(taskData) {
    queueManager.updateTaskStatus(taskData);
}

// 将函数暴露到全局作用域，确保其他模块可以调用
window.updateTaskStatus = updateTaskStatus;
window.queueManager = queueManager;
