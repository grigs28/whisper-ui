/**
 * 主应用程序入口
 */

// 等待DOM加载完成后初始化应用
document.addEventListener('DOMContentLoaded', function() {
    // 初始化各个组件
    initializeApp();
    
    // 初始化模型内存需求显示
    if (typeof uiManager !== 'undefined') {
        uiManager.updateModelMemoryRequirement();
    }
});

/**
 * 初始化应用程序
 */
function initializeApp() {
    // 初始化WebSocket连接
    console.log('初始化WebSocket连接...');
    // WebSocket连接已经在WebSocketManager构造函数中初始化了
    // 无需再次调用initWebSocket，因为该函数未定义
    // 初始化文件管理器
    console.log('初始化文件管理器...');
    // 文件管理器会在init()方法中自动初始化
    // fileManager.init(); // 不需要手动调用，因为构造函数中已经调用了
    // 但我们需要确保在DOM加载后初始化
    if (typeof fileManager !== 'undefined') {
        // fileManager.init(); // 不需要重复调用
    }
    
    // 初始化音频播放器
    console.log('初始化音频播放器...');
    // audioPlayer.init(); // 不需要手动调用，因为构造函数中已经调用了
    if (typeof audioPlayer !== 'undefined') {
        // audioPlayer.init(); // 不需要重复调用
    }
    
    // 初始化转录控制器
    console.log('初始化转录控制器...');
    // transcriptionController.init(); // 不需要手动调用，因为构造函数中已经调用了
    if (typeof transcriptionController !== 'undefined') {
        // transcriptionController.init(); // 不需要重复调用
    }
    
    // 初始化GPU监控
    console.log('初始化GPU监控...');
    // gpuMonitor.init(); // 不需要手动调用，因为构造函数中已经调用了
    if (typeof gpuMonitor !== 'undefined') {
        // gpuMonitor.init(); // 不需要重复调用
    }
    
    // 初始化队列管理器
    console.log('初始化队列管理器...');
    // queueManager.init(); // 不需要手动调用，因为构造函数中已经调用了
    if (typeof queueManager !== 'undefined') {
        // queueManager.init(); // 不需要重复调用
    }
    
    // 初始化UI管理器
    console.log('初始化UI管理器...');
    // uiManager.init(); // 不需要手动调用，因为构造函数中已经调用了
    if (typeof uiManager !== 'undefined') {
        // uiManager.init(); // 不需要重复调用
    }
    
    // 初始化版本管理器
    console.log('初始化版本管理器...');
    if (typeof versionManager !== 'undefined') {
        // versionManager.init(); // 不需要重复调用
    }
    
    // 显示应用初始化完成
    statusLogger.system('应用程序初始化完成');
    console.log('应用程序已准备就绪');
}

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
