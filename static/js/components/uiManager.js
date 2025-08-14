/**
 * UI管理组件
 */

class UIManager {
    constructor() {
        this.init();
    }

    /**
     * 初始化UI管理器
     */
    init() {
        this.setupEventListeners();
        this.loadInitialData();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // README模态框事件
        const readmeModal = document.getElementById('readmeModal');
        if (readmeModal) {
            readmeModal.addEventListener('show.bs.modal', () => {
                this.loadReadmeContent();
            });
        }

        // 版本模态框事件
        const versionModal = document.getElementById('versionModal');
        if (versionModal) {
            versionModal.addEventListener('show.bs.modal', () => {
                this.loadVersionContent();
            });
        }

        // 清除日志按钮
        const clearLogsBtn = document.getElementById('clearLogsBtn');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => {
                this.clearLogs();
            });
        }
        
        // 模型选择变化事件
        const modelSelector = document.getElementById('modelSelector');
        if (modelSelector) {
            modelSelector.addEventListener('change', () => {
                this.updateModelMemoryRequirement();
            });
        }
    }

    /**
     * 加载初始数据
     */
    async loadInitialData() {
        // 可以在这里加载一些初始数据
        this.loadVersionInfo();
    }

    /**
     * 加载README内容
     */
    async loadReadmeContent() {
        const readmeContent = document.getElementById('readmeContent');
        if (!readmeContent) return;

        try {
            // 显示加载指示器
            readmeContent.innerHTML = `
                <div class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">加载中...</span>
                    </div>
                    <p class="mt-2">正在加载README内容...</p>
                </div>
            `;

            // 从服务器获取README内容
            const response = await fetch('/readme');
            const readmeData = await response.json();

            if (readmeData.success) {
                readmeContent.innerHTML = `
                    <div class="markdown-content">
                        ${readmeData.html_content || readmeData.content}
                    </div>
                `;
            } else {
                readmeContent.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle"></i> 加载README内容失败: ${readmeData.error}
                    </div>
                `;
            }
        } catch (error) {
            readmeContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle"></i> 加载README内容时发生错误: ${error.message}
                </div>
            `;
        }
    }

    /**
     * 加载版本信息
     */
    async loadVersionInfo() {
        try {
            const response = await fetch('/version');
            const versionData = await response.json();

            if (versionData.success) {
                const versionNumber = document.getElementById('versionNumber');
                if (versionNumber) {
                    versionNumber.textContent = versionData.version;
                }
            }
        } catch (error) {
            console.warn('加载版本信息失败:', error);
        }
    }

    /**
     * 加载版本内容
     */
    async loadVersionContent() {
        const versionContent = document.getElementById('versionContent');
        if (!versionContent) return;

        try {
            // 显示加载指示器
            versionContent.innerHTML = `
                <div class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">加载中...</span>
                    </div>
                    <p class="mt-2">正在加载版本信息...</p>
                </div>
            `;

            // 从服务器获取版本信息
            const response = await fetch('/version_history');
            const versionData = await response.json();

            if (versionData.success && versionData.history && Array.isArray(versionData.history)) {
                versionContent.innerHTML = `
                    <div class="version-history">
                        ${versionData.history.map(item => `
                            <div class="version-item mb-3 p-3 border rounded">
                                <h6 class="mb-1">
                                    <span class="badge bg-primary">${item.version || '未知版本'}</span>
                                    <small class="text-muted ms-2">${item.date || '未知日期'}</small>
                                </h6>
                                <div class="version-changelog">
                                    ${(item.changes && Array.isArray(item.changes) ? item.changes : []).map(change => `
                                        <p class="mb-1"><i class="fas fa-chevron-right me-2"></i>${change}</p>
                                    `).join('')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            } else {
                versionContent.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle"></i> 加载版本信息失败: ${versionData.error || '版本历史数据格式错误'}
                    </div>
                `;
            }
        } catch (error) {
            versionContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle"></i> 加载版本信息时发生错误: ${error.message}
                </div>
            `;
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
     * 更新模型内存需求显示
     */
    updateModelMemoryRequirement() {
        const modelSelector = document.getElementById('modelSelector');
        const modelMemoryElement = document.getElementById('modelMemoryInfo');
        
        if (modelSelector && modelMemoryElement) {
            const selectedModel = modelSelector.value;
            const modelMemoryRequirements = {
                'tiny': '~1GB',
                'base': '~1GB',
                'small': '~2GB',
                'medium': '~5GB',
                'large': '~10GB',
                'large-v2': '~10GB',
                'large-v3': '~10GB',
                'turbo': '~6GB'
            };
            
            if (modelMemoryRequirements[selectedModel]) {
                modelMemoryElement.textContent = modelMemoryRequirements[selectedModel];
            } else {
                modelMemoryElement.textContent = '--';
            }
        }
    }
}

// 创建全局UI管理器实例
const uiManager = new UIManager();
