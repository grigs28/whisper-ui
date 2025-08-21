/**
 * 主应用程序入口
 */

// 等待DOM加载完成后初始化应用
document.addEventListener('DOMContentLoaded', function() {
    // 初始化各个组件
    initializeApp();
});

/**
 * 初始化应用程序
 */
function initializeApp() {
    statusLogger.system('初始化应用程序...');
    
    // 初始化GPU选择器
    if (typeof gpuMonitor !== 'undefined') {
        gpuMonitor.updateGPUSelector();
    }
    
    // 初始化模型内存需求显示
    if (typeof uiManager !== 'undefined') {
        uiManager.updateModelMemoryRequirement();
    }
    
    // 初始化并发设置事件监听器
    initializeConcurrentSettings();
    
    // 确保fileManager已初始化
    if (typeof fileManager !== 'undefined') {
        window.fileManager = fileManager;
        statusLogger.system('FileManager已初始化');
    } else {
        statusLogger.error('FileManager未找到，拖拽上传功能可能不可用');
    }
    
    statusLogger.system('应用程序初始化完成');
}

/**
 * 初始化并发设置相关事件监听器
 */
function initializeConcurrentSettings() {
    // 并发设置按钮点击事件
    const concurrentSettingsBtn = document.getElementById('concurrentSettingsBtn');
    if (concurrentSettingsBtn) {
        concurrentSettingsBtn.addEventListener('click', function() {
            if (typeof queueManager !== 'undefined') {
                queueManager.loadConcurrentSettings();
            }
        });
    }
    
    // 保存并发设置按钮点击事件
    const saveConcurrentSettings = document.getElementById('saveConcurrentSettings');
    if (saveConcurrentSettings) {
        saveConcurrentSettings.addEventListener('click', function() {
            if (typeof queueManager !== 'undefined') {
                queueManager.saveConcurrentSettings();
            }
        });
    }
    
    // 模态框显示时加载当前设置
    const concurrentSettingsModal = document.getElementById('concurrentSettingsModal');
    if (concurrentSettingsModal) {
        concurrentSettingsModal.addEventListener('show.bs.modal', function() {
            if (typeof queueManager !== 'undefined') {
                queueManager.loadConcurrentSettings();
            }
        });
    }
}

// 这个函数已经合并到initializeApp中，避免重复

// 页面加载完成后执行
window.addEventListener('load', function() {
    // 可以在这里添加页面加载后的逻辑
    statusLogger.system('页面加载完成');
});

// 页面卸载前执行
window.addEventListener('beforeunload', function() {
    // 清理资源
    statusLogger.system('页面即将卸载，清理资源...');
});
