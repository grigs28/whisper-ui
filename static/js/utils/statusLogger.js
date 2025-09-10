/**
 * 状态日志记录器
 */

class StatusLogger {
    constructor(containerId) {
        // 修正：使用正确的容器ID
        if (containerId === 'statusLogs') {
            containerId = 'logContainer';
        }
        this.container = document.getElementById(containerId);
        this.logs = [];
        this.maxLogs = 1000;
        this.isCollapsed = true; // 默认折叠状态
        this.enableConsoleLog = true; // 默认启用控制台日志
        this.init();
    }

    /**
     * 初始化日志记录器
     */
    async init() {
        // 从服务器获取配置参数
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const config = await response.json();
                // 修正：正确处理布尔值转换，支持字符串"True"/"False"
                // 首先检查是否为布尔值
                if (typeof config.enable_browser_console_log === 'boolean') {
                    this.enableConsoleLog = config.enable_browser_console_log;
                } else if (typeof config.enable_browser_console_log === 'string') {
                    // 如果是字符串，转换为布尔值
                    this.enableConsoleLog = config.enable_browser_console_log.toLowerCase() === 'true';
                } else {
                    // 默认值
                    this.enableConsoleLog = false;
                }
            }
        } catch (error) {
            console.warn('无法获取日志配置，使用默认设置:', error);
        }
        return this;
    }

    /**
     * 添加日志条目
     */
    addLog(level, message, data = null) {
        const timestamp = new Date();
        const logEntry = {
            timestamp: timestamp,
            level: level,
            message: message,
            data: data
        };

        this.logs.push(logEntry);

        // 保持日志数量在限制内
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }

        // 如果日志面板折叠，只记录到内存，不渲染到DOM
        if (this.isCollapsed) {
            // 折叠状态下只输出到控制台，不进行DOM操作
            this.logToConsole(logEntry);
            return;
        }

        // 1. 输出到UI日志面板（展开状态下）
        this.renderLog(logEntry);
        
        // 2. 输出到浏览器控制台
        this.logToConsole(logEntry);
        
        // 3. 输出到WebSocket（新增）- 只在启用时发送
        if (this.enableConsoleLog) {
            this.sendToWebSocket(logEntry);
        }
    }

    /**
     * 渲染单个日志条目
     */
    renderLog(logEntry) {
        if (!this.container) return;

        const logDiv = document.createElement('div');
        logDiv.className = `log-entry ${logEntry.level}`;
        // 根据日志级别生成彩色标志
        let levelSymbol = '';
        let levelColor = '';
        switch(logEntry.level) {
            case 'error':
                levelSymbol = '❌';
                levelColor = '#dc3545';
                break;
            case 'warning':
                levelSymbol = '⚠️';
                levelColor = '#ffc107';
                break;
            case 'info':
                levelSymbol = 'ℹ️';
                levelColor = '#007bff';
                break;
            case 'system':
                levelSymbol = '⚙️';
                levelColor = '#28a745';
                break;
            case 'success':
                levelSymbol = '✅';
                levelColor = '#28a745';
                break;
            case 'processing':
                levelSymbol = '🔄';
                levelColor = '#6f42c1';
                break;
            case 'failed':
                levelSymbol = '❌';
                levelColor = '#dc3545';
                break;
            case 'gpu':
                levelSymbol = '🖥️';
                levelColor = '#17a2b8';
                break;
            case 'client':
                levelSymbol = '👤';
                levelColor = '#6f42c1';
                break;
            case 'file':
                levelSymbol = '📄';
                levelColor = '#28a745';
                break;
            case 'transcription':
                levelSymbol = '📝';
                levelColor = '#007bff';
                break;
            default:
                levelSymbol = '📝';
                levelColor = '#6c757d';
        }

        logDiv.innerHTML = `
            <span class="log-symbol" style="color: ${levelColor}; margin-right: 10px; font-size: 1.1em;">${levelSymbol}</span>
            <span class="log-timestamp" style="min-width: 80px; margin-right: 10px;">${logEntry.timestamp.toLocaleTimeString()}</span>
            <span class="log-message" style="flex-grow: 1; word-break: break-word;">${logEntry.message}</span>
        `;

        // 将新日志插入到容器的最前面，使最新消息显示在最上方
        if (this.container.firstChild) {
            this.container.insertBefore(logDiv, this.container.firstChild);
        } else {
            this.container.appendChild(logDiv);
        }
        
        // 滚动到底部以确保最新消息可见
        this.container.scrollTop = 0;
    }

    /**
     * 清除所有日志
     */
    clear() {
        if (this.container) {
            this.container.innerHTML = '';
        }
        this.logs = [];
    }

    /**
     * 切换日志面板的折叠/展开状态
     */
    toggleCollapse() {
        const logPanel = document.getElementById('logPanel');
        const toggleIcon = document.getElementById('logToggleIcon');
        
        if (this.isCollapsed) {
            // 展开
            logPanel.classList.remove('collapsed');
            logPanel.classList.add('expanded');
            toggleIcon.classList.remove('fa-chevron-up');
            toggleIcon.classList.add('fa-chevron-down');
            
            // 展开时重新渲染所有日志
            this.renderAllLogs();
        } else {
            // 折叠
            logPanel.classList.remove('expanded');
            logPanel.classList.add('collapsed');
            toggleIcon.classList.remove('fa-chevron-down');
            toggleIcon.classList.add('fa-chevron-up');
            
            // 折叠时清空DOM中的日志显示
            if (this.container) {
                this.container.innerHTML = '';
            }
        }
        this.isCollapsed = !this.isCollapsed;
    }
    
    /**
     * 重新渲染所有日志（展开时使用）
     */
    renderAllLogs() {
        if (!this.container) return;
        
        // 清空容器
        this.container.innerHTML = '';
        
        // 重新渲染所有日志
        this.logs.forEach(logEntry => {
            this.renderLog(logEntry);
        });
    }

    /**
     * 记录系统信息
     */
    system(message, data = {}) {
        this.addLog('system', message, data);
    }

    /**
     * 记录成功信息
     */
    success(message, data = {}) {
        this.addLog('success', message, data);
    }

    /**
     * 记录处理中信息
     */
    processing(message, data = {}) {
        this.addLog('processing', message, data);
    }

    /**
     * 记录失败信息
     */
    failed(message, data = {}) {
        this.addLog('failed', message, data);
    }

    /**
     * 记录GPU信息
     */
    gpuInfo(message, data = {}) {
        this.addLog('gpu', message, data);
    }

    /**
     * 记录客户端连接信息
     */
    clientConnected(message, data = {}) {
        this.addLog('client', message, data);
    }

    /**
     * 记录客户端断开连接信息
     */
    clientDisconnected(message, data = {}) {
        this.addLog('client', message, data);
    }

    /**
     * 记录文件上传信息
     */
    fileUploaded(message, data = {}) {
        this.addLog('file', message, data);
    }

    /**
     * 记录文件删除信息
     */
    fileDeleted(message, data = {}) {
        this.addLog('file', message, data);
    }

    /**
     * 记录转录任务状态
     */
    transcriptionStatus(message, data = {}) {
        this.addLog('transcription', message, data);
    }

    /**
     * 记录错误信息
     */
    error(message, data = {}) {
        this.addLog('error', message, data);
    }

    /**
     * 记录警告信息
     */
    warning(message, data = {}) {
        this.addLog('warning', message, data);
    }

    /**
     * 记录调试信息
     */
    debug(message, data = {}) {
        this.addLog('debug', message, data);
    }

    /**
     * 记录普通信息
     */
    info(message, data = {}) {
        this.addLog('info', message, data);
    }

    /**
     * 记录完成信息
     */
    completed(message, data = {}) {
        this.addLog('completed', message, data);
    }

    /**
     * 输出到浏览器控制台
     */
    logToConsole(logEntry) {
        if (!this.enableConsoleLog) {
            return; // 如果禁用，则不输出到控制台
        }
        const consoleMethod = this.getConsoleMethod(logEntry.level);
        const timestamp = logEntry.timestamp.toLocaleTimeString();
        const message = `[${timestamp}] [${logEntry.level.toUpperCase()}] ${logEntry.message}`;
        
        if (logEntry.data) {
            consoleMethod(message, logEntry.data);
        } else {
            consoleMethod(message);
        }
    }

    /**
     * 输出到WebSocket
     */
    sendToWebSocket(logEntry) {
        if (typeof websocketManager !== 'undefined' && websocketManager.isConnected()) {
            websocketManager.emit('client_log', {
                level: logEntry.level,
                message: logEntry.message,
                data: logEntry.data,
                timestamp: logEntry.timestamp.toISOString()
            });
        }
    }

    /**
     * 获取对应的控制台方法
     */
    getConsoleMethod(level) {
        const methodMap = {
            'error': console.error,
            'warning': console.warn,
            'info': console.info,
            'debug': console.debug,
            'system': console.log,
            'success': console.log,
            'processing': console.log,
            'failed': console.error,
            'gpu': console.log,
            'client': console.log,
            'file': console.log,
            'transcription': console.log,
            'completed': console.log
        };
        return methodMap[level] || console.log;
    }
}

// 创建全局实例
const statusLogger = new StatusLogger('logContainer');

// 全局函数用于切换日志面板
function toggleLogPanel() {
    statusLogger.toggleCollapse();
}

// 页面加载完成后初始化日志面板为折叠状态
document.addEventListener('DOMContentLoaded', function() {
    // 页面加载时默认折叠日志面板
    const logPanel = document.getElementById('logPanel');
    if (logPanel) {
        logPanel.classList.add('collapsed');
    }
});
