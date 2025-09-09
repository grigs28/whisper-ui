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
        this.addCustomStyles();
    }

    /**
     * 添加自定义样式
     */
    addCustomStyles() {
        // 检查是否已经添加过样式
        if (document.getElementById('queue-manager-styles')) {
            return;
        }

        const style = document.createElement('style');
        style.id = 'queue-manager-styles';
        style.textContent = `
            .queue-item {
                transition: all 0.3s ease;
                border: 1px solid #e9ecef;
            }
            
            .queue-item:hover {
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                transform: translateY(-1px);
            }
            
            .queue-item .badge {
                transition: all 0.2s ease;
            }
            
            .queue-item .badge:hover {
                transform: scale(1.05);
            }
            
            .queue-item .transcription-time {
                background: linear-gradient(45deg, #17a2b8, #138496) !important;
                color: white !important;
                font-weight: 500;
            }
            
            .queue-item .processing-transcription {
                background: linear-gradient(45deg, #dc3545, #c82333) !important;
                color: white !important;
                font-weight: 600;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.7; }
                100% { opacity: 1; }
            }
            
            .queue-item .processing-time {
                background: linear-gradient(45deg, #ffc107, #e0a800) !important;
                color: #212529 !important;
                font-weight: 500;
            }
            
            .queue-item .language-badge {
                background: linear-gradient(45deg, #28a745, #20c997) !important;
                color: white !important;
                font-weight: 500;
            }
            
            .queue-item .model-badge {
                background: linear-gradient(45deg, #6c757d, #495057) !important;
                color: white !important;
                font-weight: 500;
            }
            
            .queue-item .time-badge {
                background: linear-gradient(45deg, #6c757d, #495057) !important;
                color: white !important;
                font-weight: 500;
            }
            
            .queue-item .status-badge {
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .queue-item .progress {
                height: 8px;
                border-radius: 4px;
                background-color: #f8f9fa;
                overflow: hidden;
            }
            
            .queue-item .progress-bar {
                background: linear-gradient(45deg, #007bff, #0056b3);
                border-radius: 4px;
                transition: width 0.3s ease;
            }
        `;
        document.head.appendChild(style);
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
        // 启动时间更新定时器
        this.startTimeUpdateTimer();
        
        // 添加实时时间更新定时器 - 每5秒更新一次，降低频率
        this.realTimeUpdateInterval = setInterval(() => {
            this.updateTimeDisplays();
        }, 5000);
        
        // 使用定时器管理器添加时间更新任务 - 减少频率
        timerManager.addTask('queueTimeUpdate', () => {
            const hasProcessingTasks = this.queueItems.some(item => item.status === 'processing');
            if (hasProcessingTasks) {
                // 只在有处理中任务时更新，减少更新频率
                this.updateQueueDisplay(this.queueItems);
            }
        }, 0.5); // 每0.5个主周期执行一次(5秒)

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
        
        // 停止实时时间更新定时器
        if (this.realTimeUpdateInterval) {
            clearInterval(this.realTimeUpdateInterval);
            this.realTimeUpdateInterval = null;
        }
    }

    /**
     * 启动定期刷新
     */
    startPeriodicRefresh() {
        // 每5秒刷新一次队列状态，降低更新频率
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
     * 更新队列显示 - 优化版本，使用文档片段减少DOM操作
     */
    updateQueueDisplay(items) {
        const queueItemsContainer = document.getElementById('queueItems');
        const queueInfo = document.getElementById('queueInfo');

        if (!queueItemsContainer) return;

        // 使用文档片段批量更新DOM，减少回流和重绘
        const fragment = document.createDocumentFragment();

        if (items.length === 0) {
            // 显示空闲标签
            if (queueInfo) {
                queueInfo.style.display = 'block';
                queueInfo.innerHTML = '<span class="badge bg-success"><i class="fas fa-check-circle"></i> 空闲</span>';
            }

            // 创建空状态元素
            const emptyElement = document.createElement('div');
            emptyElement.className = 'text-center py-4';
            emptyElement.innerHTML = `
                <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                <p class="text-muted">队列为空</p>
            `;
            fragment.appendChild(emptyElement);
            
            // 清空容器并添加新内容
            queueItemsContainer.innerHTML = '';
            queueItemsContainer.appendChild(fragment);
            return;
        }

        // 有任务时隐藏空闲标签
        if (queueInfo) {
            queueInfo.style.display = 'none';
        }

        // 对任务进行排序：处理中的任务优先显示
        const sortedItems = this.sortQueueItems(items);

        // 添加每个项目（包括排队和处理中的任务）
        sortedItems.forEach(item => {
            const itemElement = this.createQueueItemElement(item);
            fragment.appendChild(itemElement);
        });

        // 清空容器并批量添加新内容
        queueItemsContainer.innerHTML = '';
        queueItemsContainer.appendChild(fragment);
    }

    /**
     * 对队列项目进行排序
     */
    sortQueueItems(items) {
        return [...items].sort((a, b) => {
            // 处理中的任务优先
            if (a.status === 'processing' && b.status !== 'processing') {
                return -1;
            }
            if (a.status !== 'processing' && b.status === 'processing') {
                return 1;
            }
            
            // 同状态的任务按创建时间排序（新的在前）
            if (a.created_at && b.created_at) {
                return new Date(b.created_at) - new Date(a.created_at);
            }
            
            return 0;
        });
    }

    /**
     * 创建队列项元素
     */
    createQueueItemElement(item) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'queue-item card mb-2';
        itemDiv.setAttribute('data-task-id', item.id); // 添加任务ID属性，便于快速定位

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
            'ar': '阿拉伯语', 'pt': '葡萄牙语', 'auto': '自动检测'
        };
        
        // 如果语言是auto，尝试从结果中获取实际检测到的语言
        let languageDisplay = languageMap[item.language] || '自动检测';
        if (item.language === 'auto' && item.result && item.result.language) {
            const detectedLanguage = languageMap[item.result.language] || item.result.language;
            languageDisplay = detectedLanguage;
        }

        // 计算转录时间
        let transcriptionTime = '';
        
        // 修正：添加更健壮的时间计算逻辑，考虑start_time可能尚未设置的情况
        if (item.start_time && item.end_time) {
            // 任务已完成：显示总转录时间
            const startTime = new Date(item.start_time);
            const endTime = new Date(item.end_time);
            const duration = Math.round((endTime - startTime) / 1000);
            const minutes = Math.floor(duration / 60);
            const seconds = duration % 60;
            transcriptionTime = `${minutes}分${seconds}秒`;
        } else if (item.start_time && (item.status === 'processing' || item.status === 'loading')) {
            // 任务处理中：显示当前转录时间
            const startTime = new Date(item.start_time);
            const now = new Date();
            const duration = Math.round((now - startTime) / 1000);
            const minutes = Math.floor(duration / 60);
            const seconds = duration % 60;
            transcriptionTime = `${minutes}分${seconds}秒`;
        } else if (item.status === 'processing' && !item.start_time) {
            // 任务状态为processing但start_time尚未设置时，显示等待时间
            transcriptionTime = '等待中...';
        }

        // 格式化时间显示
        let timeDisplay = '';
        
        if (item.created_at) {
            const createdTime = new Date(item.created_at);
            const now = new Date();
            const timeDiff = now - createdTime;
            
            if (timeDiff < 60000) { // 小于1分钟
                timeDisplay = '刚刚';
            } else if (timeDiff < 3600000) { // 小于1小时
                const minutes = Math.floor(timeDiff / 60000);
                timeDisplay = `${minutes}分钟前`;
            } else if (timeDiff < 86400000) { // 小于1天
                const hours = Math.floor(timeDiff / 3600000);
                timeDisplay = `${hours}小时前`;
            } else {
                const days = Math.floor(timeDiff / 86400000);
                timeDisplay = `${days}天前`;
            }
        }

        itemDiv.innerHTML = `
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">
                            <i class="fas fa-file-audio text-primary me-1"></i>
                            ${displayName}
                        </h6>
                        <div class="d-flex align-items-center flex-wrap gap-2 mb-2">
                            <span class="badge model-badge" style="font-size: 0.75rem; padding: 0.25rem 0.5rem; display: inline-flex; align-items: center;">
                                <i class="fas fa-brain me-1" style="display: inline-block; width: 14px; text-align: center;"></i>
                                <span>${item.model || 'base'}</span>
                            </span>
                            <span class="badge language-badge" style="font-size: 0.75rem; padding: 0.25rem 0.5rem; display: inline-flex; align-items: center;">
                                <i class="fas fa-language me-1" style="display: inline-block; width: 14px; text-align: center;"></i>
                                <span>${languageDisplay}</span>
                            </span>
                            ${item.created_at ? `
                            <span class="badge bg-light text-dark border" style="font-size: 0.7rem; padding: 0.2rem 0.4rem; display: inline-flex; align-items: center;" title="${new Date(item.created_at).toLocaleString()}">
                                <i class="fas fa-calendar-alt me-1 text-muted" style="display: inline-block; width: 14px; text-align: center;"></i>
                                <span>${new Date(item.created_at).toLocaleTimeString()}</span>
                            </span>
                            ` : ''}
                            ${transcriptionTime ? `
                            <span class="badge transcription-time ${item.status === 'processing' ? 'processing-transcription' : ''}" 
                                  style="font-size: 0.75rem; padding: 0.25rem 0.5rem; background-color: #dc3545; color: white; display: inline-flex; align-items: center;"
                                  data-transcription-time="${item.start_time}"
                                  data-task-status="${item.status}">
                                <i class="fas fa-stopwatch me-1" style="display: inline-block; width: 14px; text-align: center;"></i>
                                <span>${transcriptionTime}</span>
                                ${item.status === 'processing' ? ' <span>(进行中)</span>' : ''}
                            </span>
                            ` : ''}
                            ${timeDisplay ? `
                            <span class="badge time-badge" style="font-size: 0.75rem; padding: 0.25rem 0.5rem; display: inline-flex; align-items: center;">
                                <i class="fas fa-clock me-1" style="display: inline-block; width: 14px; text-align: center;"></i>
                                <span data-time-timestamp="${item.created_at}">${timeDisplay}</span>
                            </span>
                            ` : ''}
                        </div>
                    </div>
                    <div class="d-flex align-items-center">
                        <span class="badge bg-${this.getStatusBadgeClass(item.status)} status-badge" style="font-size: 0.8rem; padding: 0.3rem 0.6rem;">
                            ${this.getStatusText(item.status)}
                        </span>
                    </div>
                </div>
                ${item.status === 'processing' ? `
                <div class="progress mb-2" style="height: 10px; border-radius: 5px; background-color: #f8f9fa;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                         role="progressbar" 
                         style="width: ${item.progress || 0}%; background: linear-gradient(45deg, #007bff, #0056b3); border-radius: 5px; transition: width 0.3s ease;"
                         aria-valuenow="${item.progress || 0}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <small class="text-muted fw-medium">
                        <i class="fas fa-cog fa-spin me-1"></i>
                        ${item.message || '处理中...'}
                    </small>
                    <small class="text-primary fw-bold">${Math.round(item.progress || 0)}%</small>
                </div>
                ` : ''}
                ${item.download_progress && item.status === 'processing' ? `
                <div class="mt-2 p-2 bg-light rounded">
                    <div class="d-flex align-items-center mb-1">
                        <i class="fas fa-download text-info me-2"></i>
                        <small class="text-info fw-medium">模型下载进度</small>
                    </div>
                    <div class="progress mb-1" style="height: 8px; border-radius: 4px; background-color: #e9ecef;">
                        <div class="progress-bar bg-info progress-bar-striped progress-bar-animated" 
                             role="progressbar" 
                             style="width: ${item.download_progress}%; border-radius: 4px; transition: width 0.3s ease;"
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
            case 'retrying':
                return '重试中';
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
     * 更新任务状态 - 优化版本，避免不必要的完整重渲染
     */
    updateTaskStatus(taskData) {
        statusLogger.system('***【updateTaskStatus】更新本地队列状态 ***');
        
        // 更新本地队列状态
        const index = this.queueItems.findIndex(item => item.id === taskData.id);
        if (index !== -1) {
            // 如果是进度更新，使用平滑过渡
            if (taskData.type === 'progress_update' && this.queueItems[index].progress !== taskData.progress) {
                this.smoothProgressUpdate(this.queueItems[index], taskData);
                return; // 进度更新已经处理完毕，不需要后续步骤
            } else {
                this.queueItems[index] = { ...this.queueItems[index], ...taskData };
            }
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
                    window.fileManager.refreshFileList('output').then(() => {
                        statusLogger.system('【updateTaskStatus】输出文件列表自动刷新完成');
                    }).catch((error) => {
                        statusLogger.error('【updateTaskStatus】输出文件列表刷新失败', { error: error.message });
                    });
                } else {
                    statusLogger.error('【updateTaskStatus】FileManager未找到，无法自动刷新输出文件列表');
                }
                break;

            case 'failed':
                statusLogger.error('【updateTaskStatus】转录任务失败', { task_id: taskData.id, error: taskData.error });
                break;
            case 'retrying':
                statusLogger.warning('【updateTaskStatus】转录任务正在重试', { task_id: taskData.id, retry_count: taskData.retry_count });
                break;
        }

        // 只在必要时更新显示，避免频繁重渲染
        if (this.shouldUpdateDisplay(taskData)) {
            // 立即更新显示
            this.updateQueueDisplay(this.queueItems);
        }
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
     * 判断是否需要更新显示 - 优化策略
     */
    shouldUpdateDisplay(taskData) {
        // 对于简单的状态变更，如进度更新，不立即重绘整个列表
        if (taskData.type === 'progress_update') {
            // 只更新单个任务项，而不是整个列表
            this.updateSingleTaskElement(taskData);
            return false;
        }
        
        // 对于状态变更（非进度更新），需要更新整个列表以保持一致性
        // 特别是对于重试状态，需要确保UI正确显示
        if (taskData.status === 'retrying' || taskData.status === 'failed' || taskData.status === 'completed') {
            return true;
        }
        
        // 对于新增任务、任务完成或失败等情况，需要更新整个列表
        return true;
    }
    
    /**
     * 更新单个任务元素 - 节省内存和性能
     */
    updateSingleTaskElement(taskData) {
        const itemElement = document.querySelector(`[data-task-id="${taskData.id}"]`);
        if (itemElement) {
            // 对于重试状态，避免完全替换元素，只更新必要的内容
            if (taskData.status === 'retrying') {
                // 只更新状态徽章
                const statusBadge = itemElement.querySelector('.status-badge');
                if (statusBadge) {
                    statusBadge.textContent = this.getStatusText(taskData.status);
                    statusBadge.className = `badge bg-${this.getStatusBadgeClass(taskData.status)} status-badge`;
                }
                
                // 更新转录时间显示
                const transcriptionTimeElement = itemElement.querySelector('[data-transcription-time]');
                if (transcriptionTimeElement) {
                    transcriptionTimeElement.innerHTML = `
                        <i class="fas fa-stopwatch me-1" style="display: inline-block; width: 14px; text-align: center;"></i>
                        <span>等待中...</span>
                        <span>(重试中)</span>
                    `;
                }
            } else {
                // 其他状态使用完整更新
                const updatedElement = this.createQueueItemElement(taskData);
                itemElement.parentNode.replaceChild(updatedElement, itemElement);
            }
        }
    }

    /**
     * 平滑进度更新
     */
    smoothProgressUpdate(taskItem, newData) {
        const oldProgress = taskItem.progress || 0;
        const newProgress = newData.progress || 0;
        
        // 如果进度变化很小，直接更新
        if (Math.abs(newProgress - oldProgress) < 2) {
            Object.assign(taskItem, newData);
            return;
        }
        
        // 平滑过渡动画
        const duration = 500; // 500ms过渡时间
        const startTime = Date.now();
        const startProgress = oldProgress;
        const progressDiff = newProgress - oldProgress;
        
        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // 使用缓动函数
            const easeProgress = this.easeInOutQuad(progress);
            const currentProgress = startProgress + (progressDiff * easeProgress);
            
            taskItem.progress = Math.round(currentProgress * 10) / 10;
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                // 动画完成，设置最终值
                Object.assign(taskItem, newData);
            }
            
            // 更新显示
            this.updateQueueDisplay(this.queueItems);
        };
        
        requestAnimationFrame(animate);
    }

    /**
     * 缓动函数 - 二次方缓入缓出
     */
    easeInOutQuad(t) {
        return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    }

    /**
     * 格式化相对时间
     */
    formatRelativeTime(timestamp) {
        if (!timestamp) return '';
        
        const createdTime = new Date(timestamp);
        const now = new Date();
        const timeDiff = now - createdTime;
        
        if (timeDiff < 60000) { // 小于1分钟
            return '刚刚';
        } else if (timeDiff < 3600000) { // 小于1小时
            const minutes = Math.floor(timeDiff / 60000);
            return `${minutes}分钟前`;
        } else if (timeDiff < 86400000) { // 小于1天
            const hours = Math.floor(timeDiff / 3600000);
            return `${hours}小时前`;
        } else {
            const days = Math.floor(timeDiff / 86400000);
            return `${days}天前`;
        }
    }

    /**
     * 启动时间更新定时器
     */
    startTimeUpdateTimer() {
        // 每分钟更新一次时间显示
        setInterval(() => {
            this.updateTimeDisplays();
        }, 60000); // 60秒更新一次
    }

    /**
     * 更新所有时间显示 - 添加节流机制
     */
    updateTimeDisplays() {
        // 节流：避免过于频繁的时间更新
        if (this.lastUpdateTime && Date.now() - this.lastUpdateTime < 1000) {
            return;
        }
        this.lastUpdateTime = Date.now();
        
        const queueItemsContainer = document.getElementById('queueItems');
        if (!queueItemsContainer) return;

        // 优化：只更新处理中的任务时间显示，减少DOM操作
        const processingTasks = Array.from(queueItemsContainer.querySelectorAll('.queue-item'))
            .filter(item => {
                const statusBadge = item.querySelector('.status-badge');
                return statusBadge && statusBadge.textContent.trim() === '处理中';
            });
        
        // 更新所有任务卡片中的时间显示
        const timeElements = queueItemsContainer.querySelectorAll('[data-time-timestamp]');
        timeElements.forEach(element => {
            const timestamp = element.getAttribute('data-time-timestamp');
            if (timestamp) {
                const relativeTime = this.formatRelativeTime(timestamp);
                element.textContent = relativeTime;
            }
        });

        // 优化：只更新处理中任务的处理时间显示
        processingTasks.forEach(item => {
            const processingTimeElements = item.querySelectorAll('[data-processing-time]');
            processingTimeElements.forEach(element => {
                const startTime = element.getAttribute('data-processing-time');
                if (startTime) {
                    const startDate = new Date(startTime);
                    const now = new Date();
                    const processingTime = Math.round((now - startDate) / 1000);
                    const minutes = Math.floor(processingTime / 60);
                    const seconds = processingTime % 60;
                    element.textContent = `${minutes}分${seconds}秒`;
                }
            });
        });

        // 更新转录时间显示 - 实时更新处理中任务的转录时间
        const transcriptionTimeElements = queueItemsContainer.querySelectorAll('[data-transcription-time]');
        transcriptionTimeElements.forEach(element => {
            const startTime = element.getAttribute('data-transcription-time');
            const status = element.getAttribute('data-task-status');
            
            if (startTime && (status === 'processing' || status === 'loading')) {
                const startDate = new Date(startTime);
                const now = new Date();
                const transcriptionTime = Math.round((now - startDate) / 1000);
                const minutes = Math.floor(transcriptionTime / 60);
                const seconds = transcriptionTime % 60;
                
                // 查找时间文本的span元素，只更新文本内容，保留图标
                const timeSpan = element.querySelector('span');
                if (timeSpan) {
                    timeSpan.textContent = `${minutes}分${seconds}秒`;
                } else {
                    // 如果没有找到span元素，则更新整个元素内容（包含图标）
                    element.innerHTML = `
                        <i class="fas fa-stopwatch me-1" style="display: inline-block; width: 14px; text-align: center;"></i>
                        <span>${minutes}分${seconds}秒</span>
                        ${status === 'processing' ? ' <span>(进行中)</span>' : ''}
                    `;
                }
            }
        });
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
