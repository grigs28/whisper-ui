/**
 * 定时器管理类 - 用于统一管理应用中的所有定时器
 */
class TimerManager {
    constructor() {
        this.timers = new Map();
        this.interval = 5000; // 默认5秒间隔
        this.isRunning = false;
        this.mainTimer = null;

        // 在页面卸载时停止所有定时器
        window.addEventListener('beforeunload', () => {
            this.stop();
        });
    }

    /**
     * 启动定时器管理器
     * @param {number} interval - 时间间隔(毫秒)
     */
    start(interval = this.interval) {
        if (this.isRunning) {
            statusLogger.warning('定时器管理器已在运行中');
            return;
        }

        this.interval = interval;
        this.isRunning = true;

        statusLogger.system(`定时器管理器已启动，间隔: ${this.interval}ms`);

        // 立即执行一次所有任务
        this.executeAllTasks();

        // 设置主定时器
        this.mainTimer = setInterval(() => {
            this.executeAllTasks();
        }, this.interval);
    }

    /**
     * 停止定时器管理器
     */
    stop() {
        if (!this.isRunning) {
            statusLogger.warning('定时器管理器未运行');
            return;
        }

        clearInterval(this.mainTimer);
        this.mainTimer = null;
        this.isRunning = false;

        statusLogger.system('定时器管理器已停止');
    }

    /**
     * 添加任务到定时器
     * @param {string} taskId - 任务唯一ID
     * @param {Function} taskFn - 任务函数
     * @param {number} frequency - 执行频率(相对于主间隔的倍数)
     */
    addTask(taskId, taskFn, frequency = 1) {
        if (this.timers.has(taskId)) {
            statusLogger.warning(`任务ID ${taskId} 存在，将被覆盖`);
        }

        this.timers.set(taskId, {
            fn: taskFn,
            frequency: frequency,
            counter: 0
        });

        statusLogger.system(`已添加任务: ${taskId}, 频率: ${frequency}x`);
    }

    /**
     * 移除任务
     * @param {string} taskId - 任务ID
     */
    removeTask(taskId) {
        if (this.timers.delete(taskId)) {
            statusLogger.system(`已移除任务: ${taskId}`);
        } else {
            statusLogger.warning(`未找到任务: ${taskId}`);
        }
    }

    /**
     * 执行所有任务
     */
    executeAllTasks() {
        this.timers.forEach((task, taskId) => {
            task.counter += 1;
            if (task.counter >= task.frequency) {
                try {
                    task.fn();
                    task.counter = task.counter % task.frequency;
                } catch (error) {
                    statusLogger.error(`执行任务 ${taskId} 时出错: ${error.message}`);
                }
            }
        });
    }
}

/**
 * 创建全局定时器管理器实例
 */
const timerManager = new TimerManager();

export default timerManager;