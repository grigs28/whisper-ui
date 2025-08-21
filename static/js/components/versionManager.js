/**
 * 版本管理器
 * 负责处理版本信息显示和版本历史
 */
class VersionManager {
    constructor() {
        this.currentVersion = null;
        this.versionHistory = [];
        this.isShowingHistory = false;
        this.init();
    }

    /**
     * 初始化版本管理器
     */
    init() {
        this.setupEventListeners();
        this.loadVersionInfo();
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 版本历史按钮点击事件
        const showHistoryBtn = document.getElementById('showVersionHistory');
        if (showHistoryBtn) {
            showHistoryBtn.addEventListener('click', () => {
                this.toggleVersionHistory();
            });
        }

        // 版本模态框显示事件
        const versionModal = document.getElementById('versionModal');
        if (versionModal) {
            versionModal.addEventListener('show.bs.modal', () => {
                this.loadVersionInfo();
                this.displayVersionInfo();
                // 重置状态
                this.isShowingHistory = false;
                const showHistoryBtn = document.getElementById('showVersionHistory');
                const versionTitle = document.getElementById('versionTitle');
                if (showHistoryBtn) {
                    showHistoryBtn.innerHTML = '<i class="fas fa-history"></i> 查看版本历史';
                }
                if (versionTitle && this.currentVersion) {
                    versionTitle.textContent = `版本 ${this.currentVersion}`;
                }
            });
        }
    }

    /**
     * 加载版本信息
     */
    async loadVersionInfo() {
        try {
            const response = await fetch('/version');
            const data = await response.json();
            
            if (data.success) {
                this.currentVersion = data.version;
                this.updateVersionDisplay();
            } else {
                statusLogger.error('获取版本信息失败: ' + data.error);
            }
        } catch (error) {
            statusLogger.error('加载版本信息时出错: ' + error.message);
        }
    }

    /**
     * 加载版本历史
     */
    async loadVersionHistory() {
        try {
            const response = await fetch('/version_history');
            const data = await response.json();
            
            if (data.success) {
                this.versionHistory = data.history;
                return data;
            } else {
                statusLogger.error('获取版本历史失败: ' + data.error);
                return null;
            }
        } catch (error) {
            statusLogger.error('加载版本历史时出错: ' + error.message);
            return null;
        }
    }

    /**
     * 更新版本显示
     */
    updateVersionDisplay() {
        const versionNumberElement = document.getElementById('versionNumber');
        if (versionNumberElement && this.currentVersion) {
            versionNumberElement.textContent = this.currentVersion;
        }

        // 更新导航栏中的版本号
        const navVersionNumber = document.getElementById('navVersionNumber');
        if (navVersionNumber && this.currentVersion) {
            navVersionNumber.textContent = `v${this.currentVersion}`;
        }

        // 更新模态框标题
        const versionTitle = document.getElementById('versionTitle');
        if (versionTitle && this.currentVersion) {
            versionTitle.textContent = `版本 ${this.currentVersion}`;
        }
    }

    /**
     * 切换版本历史显示
     */
    async toggleVersionHistory() {
        const showHistoryBtn = document.getElementById('showVersionHistory');
        const versionContent = document.getElementById('versionContent');
        const versionTitle = document.getElementById('versionTitle');
        
        if (!this.isShowingHistory) {
            // 显示版本历史
            const historyData = await this.loadVersionHistory();
            if (historyData) {
                this.displayVersionHistory(historyData);
                showHistoryBtn.innerHTML = '<i class="fas fa-arrow-left"></i> 返回版本信息';
                versionTitle.textContent = '版本历史';
                this.isShowingHistory = true;
            } else {
                // 显示错误信息
                versionContent.innerHTML = `
                    <div class="alert alert-danger text-center">
                        <i class="fas fa-exclamation-triangle"></i>
                        <strong>加载版本历史失败</strong><br>
                        <small class="text-muted">无法获取版本历史数据，请稍后重试</small>
                    </div>
                `;
            }
        } else {
            // 返回版本信息
            this.displayVersionInfo();
            showHistoryBtn.innerHTML = '<i class="fas fa-history"></i> 查看版本历史';
            versionTitle.textContent = `版本 ${this.currentVersion || ''}`;
            this.isShowingHistory = false;
        }
    }

    /**
     * 显示版本信息
     */
    displayVersionInfo() {
        const versionContent = document.getElementById('versionContent');
        if (!versionContent) return;

        versionContent.innerHTML = `
            <div class="text-center">
                <p class="text-muted mb-3">点击上方按钮查看完整的版本历史记录</p>
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i>
                    <strong>当前版本功能：</strong><br>
                    支持多文件上传、音频转录、GPU加速等功能
                </div>
            </div>
        `;
    }

    /**
     * 显示版本历史
     */
    displayVersionHistory(historyData) {
        const versionContent = document.getElementById('versionContent');
        if (!versionContent) return;
        
        // 检查数据有效性
        if (!historyData || !historyData.history || !Array.isArray(historyData.history)) {
            versionContent.innerHTML = `
                <div class="alert alert-danger text-center">
                    <i class="fas fa-exclamation-triangle"></i>
                    <strong>加载版本信息时发生错误</strong><br>
                    <small class="text-muted">版本历史数据格式错误或为空</small>
                </div>
            `;
            return;
        }

        let historyHtml = '<div class="version-history">';
        
        historyData.history.forEach((version, index) => {
            const isLatest = index === 0;
            historyHtml += `
                <div class="card mb-3 ${isLatest ? 'border-primary' : ''}">
                    <div class="card-header ${isLatest ? 'bg-primary text-white' : 'bg-light'}">
                        <h6 class="mb-0">
                            <i class="fas fa-tag"></i> 
                            版本 ${version.version}
                            ${isLatest ? '<span class="badge bg-light text-primary ms-2">最新</span>' : ''}
                            <small class="float-end">${version.date}</small>
                        </h6>
                    </div>
                    <div class="card-body">
                        ${version.description ? `<p class="text-muted mb-3">${version.description}</p>` : ''}
                        
                        ${version.features && Array.isArray(version.features) && version.features.length > 0 ? `
                            <div class="mb-3">
                                <h6 class="text-success"><i class="fas fa-plus-circle"></i> 新增功能</h6>
                                <ul class="list-unstyled ms-3">
                                    ${version.features.map(feature => `<li><i class="fas fa-check text-success"></i> ${feature}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                        
                        ${version.improvements && Array.isArray(version.improvements) && version.improvements.length > 0 ? `
                            <div class="mb-3">
                                <h6 class="text-info"><i class="fas fa-wrench"></i> 改进内容</h6>
                                <ul class="list-unstyled ms-3">
                                    ${version.improvements.map(improvement => `<li><i class="fas fa-arrow-up text-info"></i> ${improvement}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                        
                        ${version.changes && Array.isArray(version.changes) && version.changes.length > 0 ? `
                            <div class="mb-3">
                                <h6 class="text-primary"><i class="fas fa-list"></i> 更新内容</h6>
                                <ul class="list-unstyled ms-3">
                                    ${version.changes.map(change => `<li><i class="fas fa-dot-circle text-primary"></i> ${change}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                        
                        ${version.fixes && Array.isArray(version.fixes) && version.fixes.length > 0 ? `
                            <div class="mb-3">
                                <h6 class="text-warning"><i class="fas fa-bug"></i> 修复内容</h6>
                                <ul class="list-unstyled ms-3">
                                    ${version.fixes.map(fix => `<li><i class="fas fa-check-circle text-warning"></i> ${fix}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        });
        
        historyHtml += '</div>';
        versionContent.innerHTML = historyHtml;
    }
}

// 创建全局版本管理器实例
const versionManager = new VersionManager();