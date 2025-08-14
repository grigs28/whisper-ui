/**
 * WebSocket 连接管理组件
 */

class WebSocketManager {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.init();
    }

    /**
     * 初始化WebSocket连接
     */
    init() {
        // 连接到当前域名的WebSocket服务器
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}`;
        
        this.socket = io(wsUrl, {
            transports: ['websocket'],
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: this.reconnectDelay,
            timeout: 10000
        });

        this.setupEventListeners();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        this.socket.on('connect', () => {
            this.isConnected = true;
            this.reconnectAttempts = 0;
            statusLogger.system('WebSocket连接已建立', { 
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            console.log('WebSocket connected');
        });

        this.socket.on('disconnect', (reason) => {
            this.isConnected = false;
            statusLogger.warning('WebSocket连接已断开', { 
                reason, 
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            console.log('WebSocket disconnected:', reason);
        });

        this.socket.on('connect_error', (error) => {
            statusLogger.error('WebSocket连接错误', { 
                error: error.message,
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            console.error('WebSocket connection error:', error);
        });

        this.socket.on('reconnect', (attemptNumber) => {
            this.reconnectAttempts = attemptNumber;
            statusLogger.success('WebSocket重新连接成功', { 
                attempt: attemptNumber,
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            console.log('WebSocket reconnected after', attemptNumber, 'attempts');
        });

        this.socket.on('reconnect_attempt', (attemptNumber) => {
            statusLogger.warning('尝试重新连接WebSocket', { 
                attempt: attemptNumber,
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            console.log('WebSocket reconnect attempt', attemptNumber);
        });

        this.socket.on('task_update', (data) => {
            this.handleTaskUpdate(data);
        });

        this.socket.on('download_progress', (data) => {
            this.handleDownloadProgress(data);
        });

        this.socket.on('log_message', (data) => {
            this.handleLogMessage(data);
        });
    }

    /**
     * 处理任务更新
     */
    handleTaskUpdate(data) {
        // 更新任务状态
        updateTaskStatus(data);
        statusLogger.info('任务状态更新', data);
    }

    /**
     * 处理下载进度
     */
    handleDownloadProgress(data) {
        // 显示下载进度消息
        statusLogger.info(data.message, {
            task_id: data.task_id,
            progress: data.progress,
            type: 'download_progress'
        });
        
        // 显示下载进度弹窗
        this.showDownloadProgressModal(data);
        
        // 如果有队列管理器，也通知它
        if (window.queueManager) {
            queueManager.updateDownloadProgress(data);
        }
    }

    /**
     * 显示下载进度弹窗
     */
    showDownloadProgressModal(data) {
        const modal = document.getElementById('downloadProgressModal');
        const progressBar = document.getElementById('downloadProgressBar');
        const progressText = document.getElementById('downloadProgressText');
        const downloadStatus = document.getElementById('downloadStatus');
        const downloadModelName = document.getElementById('downloadModelName');
        
        if (!modal || !progressBar || !progressText || !downloadStatus) return;
        
        // 更新进度条
        const progress = data.progress || 0;
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', progress);
        progressText.textContent = `${progress}%`;
        
        // 更新状态信息
        downloadStatus.textContent = data.message || '下载中...';
        
        // 更新模型名称（如果有的话）
        if (data.model_name) {
            downloadModelName.textContent = `正在下载模型: ${data.model_name}`;
        }
        
        // 显示弹窗（如果还没显示）
        const bootstrapModal = bootstrap.Modal.getInstance(modal) || new bootstrap.Modal(modal);
        if (!modal.classList.contains('show')) {
            bootstrapModal.show();
        }
        
        // 如果下载完成，隐藏弹窗
        if (progress >= 100) {
            setTimeout(() => {
                bootstrapModal.hide();
                statusLogger.success('模型下载完成，开始转录...', {
                    task_id: data.task_id,
                    type: 'download_complete'
                });
            }, 1500); // 1.5秒后隐藏
        }
    }
    
    /**
     * 处理日志消息
     */
    handleLogMessage(data) {
        // 根据日志级别添加到前端日志显示
        switch(data.level) {
            case 'info':
                statusLogger.info(data.message);
                break;
            case 'warning':
                statusLogger.warning(data.message);
                break;
            case 'error':
                statusLogger.error(data.message);
                break;
            case 'debug':
                statusLogger.info(`[DEBUG] ${data.message}`);
                break;
            case 'system':
                statusLogger.system(data.message);
                break;
            case 'success':
                statusLogger.success(data.message);
                break;
            case 'processing':
                statusLogger.processing(data.message);
                break;
            case 'failed':
                statusLogger.failed(data.message);
                break;
            case 'gpu':
                statusLogger.gpuInfo(data.message);
                break;
            default:
                statusLogger.info(data.message);
        }
    }

    /**
     * 发送消息
     */
    emit(event, data) {
        if (this.isConnected && this.socket) {
            this.socket.emit(event, data);
        } else {
            statusLogger.warning('WebSocket未连接，无法发送消息', { event, data });
        }
    }

    /**
     * 获取连接状态
     */
    getStatus() {
        return {
            connected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts
        };
    }
}

// 创建全局WebSocket管理器实例
const wsManager = new WebSocketManager();
