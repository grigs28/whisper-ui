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
            transports: ['websocket', 'polling'],  // 支持多种传输方式
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: this.reconnectDelay,
            reconnectionDelayMax: 5000,  // 最大重连延迟5秒
            timeout: 20000,  // 增加超时时间到20秒
            pingTimeout: 120000,  // 120秒ping超时
            pingInterval: 30000,   // 30秒ping间隔
            forceNew: true,  // 强制新连接
            autoConnect: true  // 自动连接
        });

        this.setupEventListeners();
        
        // 启动连接健康监控
        this.startHealthMonitor();
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
            // console.log('WebSocket connected'); // 已通过statusLogger.system记录
        });

        this.socket.on('connection_ack', (data) => {
            // 收到服务器连接确认
            statusLogger.success('WebSocket连接已确认', { 
                status: data.status,
                timestamp: new Date().toISOString()
            });
        });

        this.socket.on('disconnect', (reason) => {
            this.isConnected = false;
            statusLogger.warning('WebSocket连接已断开', { 
                reason, 
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            
            // 分析断开原因
            this.analyzeDisconnectReason(reason);
            
            // console.log('WebSocket disconnected:', reason); // 已通过statusLogger.warning记录
        });

        this.socket.on('connect_error', (error) => {
            statusLogger.error('WebSocket连接错误', { 
                error: error.message,
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            
            // 如果是页面刷新导致的错误，尝试重新连接
            if (error.message.includes('500') || error.message.includes('write()')) {
                setTimeout(() => {
                    this.reconnect();
                }, 1000);
            }
            
            // console.error('WebSocket connection error:', error); // 已通过statusLogger.error记录
        });

        this.socket.on('reconnect', (attemptNumber) => {
            this.reconnectAttempts = attemptNumber;
            statusLogger.success('WebSocket重新连接成功', { 
                attempt: attemptNumber,
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            // console.log('WebSocket reconnected after', attemptNumber, 'attempts'); // 已通过statusLogger.success记录
        });

        this.socket.on('reconnect_attempt', (attemptNumber) => {
            statusLogger.warning('尝试重新连接WebSocket', { 
                attempt: attemptNumber,
                timestamp: new Date().toISOString(),
                host: window.location.host
            });
            // console.log('WebSocket reconnect attempt', attemptNumber); // 已通过statusLogger.warning记录
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

        this.socket.on('server_heartbeat', (data) => {
            // 收到服务器心跳，回复确认
            this.emit('heartbeat_ack', { 
                timestamp: Date.now(),
                server_timestamp: data.timestamp 
            });
        });

        this.socket.on('heartbeat_response', (data) => {
            // 收到心跳响应
            const latency = Date.now() - data.timestamp;
            if (latency > 5000) {  // 如果延迟超过5秒
                statusLogger.warning(`WebSocket心跳延迟较高: ${latency}ms`);
            }
        });
    }

    /**
     * 处理任务更新
     */
    handleTaskUpdate(data) {
        // 更新任务状态
        if (typeof updateTaskStatus === 'function') {
            updateTaskStatus(data);
        } else {
            statusLogger.warning('updateTaskStatus函数未定义，无法更新任务状态', data);
        }
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

    /**
     * 分析断开原因
     */
    analyzeDisconnectReason(reason) {
        let message = '';
        switch(reason) {
            case 'io server disconnect':
                message = '服务器主动断开连接';
                break;
            case 'io client disconnect':
                message = '客户端主动断开连接';
                break;
            case 'ping timeout':
                message = '心跳超时，网络连接不稳定';
                break;
            case 'transport close':
                message = '传输层连接关闭';
                break;
            case 'transport error':
                message = '传输层错误';
                break;
            default:
                message = `未知原因: ${reason}`;
        }
        statusLogger.error(`WebSocket断开原因: ${message}`, { reason });
    }

    /**
     * 检查WebSocket连接状态
     */
    getConnectionStatus() {
        return this.socket && this.socket.connected;
    }

    /**
     * 检查WebSocket连接状态（兼容性方法）
     */
    isConnected() {
        return this.getConnectionStatus();
    }

    /**
     * 监控WebSocket连接健康状态
     */
    startHealthMonitor() {
        // 每60秒检查一次连接状态，进一步减少频率
        setInterval(() => {
            if (!this.getConnectionStatus()) {
                statusLogger.warning('WebSocket连接已断开，尝试重新连接...');
                this.reconnect();
            } else {
                // 发送心跳测试，但进一步减少频率
                this.emit('heartbeat_test', { timestamp: Date.now() });
            }
        }, 60000);  // 增加到60秒，进一步减少请求频率
    }

    /**
     * 重新连接
     */
    reconnect() {
        if (this.socket) {
            try {
                this.socket.disconnect();
                setTimeout(() => {
                    this.socket.connect();
                }, 1000);
            } catch (error) {
                statusLogger.error('WebSocket重连失败', { error: error.message });
            }
        }
    }
}

// 创建全局WebSocket管理器实例
const wsManager = new WebSocketManager();
