// 引入定时器管理器
import timerManager from '../utils/timerManager.js';

// GPU监控组件
class GPUMonitor {
    /**
     * 构造函数
     */
    constructor() {
        // 绑定方法上下文
        this.init = this.init.bind(this);
        this.startGPUMonitoring = this.startGPUMonitoring.bind(this);
        this.fetchGPUInfo = this.fetchGPUInfo.bind(this);
        this.updateGPUInfoDisplay = this.updateGPUInfoDisplay.bind(this);
        this.handleClick = this.handleClick.bind(this);
        this.stopGPUMonitoring = this.stopGPUMonitoring.bind(this);
        this.setupSmartGPUSelection = this.setupSmartGPUSelection.bind(this);
        this.updateGPUSelector = this.updateGPUSelector.bind(this);
        this.smartSelectGPU = this.smartSelectGPU.bind(this);

        // 初始化状态
        this.isMonitoring = false;
        this.clickHandler = null;

        // 初始化GPU监控
        this.init();
    }

    /**
     * 初始化GPU监控
     */
    init() {
        console.log('初始化GPU监控...');

        // 启动GPU监控
        this.startGPUMonitoring();

        // 设置智能GPU选择功能
        this.setupSmartGPUSelection();

        // 添加点击事件监听器
        this.clickHandler = this.handleClick.bind(this);
        document.addEventListener('click', this.clickHandler);
    }

    /**
     * 处理点击事件
     */
    handleClick(event) {
        // 检查点击的元素是否在GPU状态区域之外
        const gpuStatusContainer = document.querySelector('.gpu-status-container');
        if (gpuStatusContainer && !gpuStatusContainer.contains(event.target)) {
            // 点击在GPU状态区域之外，刷新GPU信息
            this.fetchGPUInfo();
        }
    }

    /**
     * 开始GPU监控
     */
    startGPUMonitoring() {
        if (this.isMonitoring) {
            console.warn('GPU监控已在运行中');
            return;
        }

        console.log('开始GPU监控...');
        this.isMonitoring = true;

        // 立即获取一次GPU信息
        this.fetchGPUInfo();

        // 使用定时器管理器添加GPU监控任务
        timerManager.addTask('gpuMonitoring', () => {
            this.fetchGPUInfo();
        }, 1); // 每1个主周期执行一次(5秒)

        // 确保定时器管理器已启动
        if (!timerManager.isRunning) {
            timerManager.start(5000); // 设置5秒间隔
        }
    }

    /**
     * 获取GPU信息
     */
    async fetchGPUInfo() {
        try {
            const response = await fetch('/gpu_info');
            const gpuInfo = await response.json();

            // 更新GPU信息显示
            this.updateGPUInfoDisplay(gpuInfo);

            // 更新GPU选择器
            this.updateGPUSelector(gpuInfo);
        } catch (error) {
            console.error('获取GPU信息时出错:', error);

            // 显示错误信息
            this.updateGPUInfoDisplay({
                success: false,
                error: error.message
            });
        }
    }

    /**
     * 更新GPU信息显示
     */
    updateGPUInfoDisplay(gpuInfo) {
        // 获取DOM元素
        const gpuCardsContainer = document.getElementById('gpuCardsContainer');

        // 检查元素是否存在
        if (!gpuCardsContainer) {
            console.warn('GPU状态显示容器未找到');
            return;
        }

        if (gpuInfo.success && gpuInfo.gpus && gpuInfo.gpus.length > 0) {
            // 清空现有内容
            gpuCardsContainer.innerHTML = '';

            // 为每个GPU创建单独的卡片
            gpuInfo.gpus.forEach((gpu, index) => {
                // 正确获取GPU利用率
                let gpuUtilization = 0;
                if (gpu.utilization && typeof gpu.utilization === 'object') {
                    gpuUtilization = gpu.utilization.gpu !== undefined ? gpu.utilization.gpu : 0;
                } else if (typeof gpu.utilization === 'number') {
                    gpuUtilization = gpu.utilization;
                }

                const allocatedMemoryGB = gpu.allocated_memory.toFixed(1);
                const totalMemoryGB = gpu.total_memory.toFixed(1);
                const availableMemoryGB = gpu.available_memory.toFixed(1);

                // 获取温度和利用率数据
                const temperature = gpu.temperature !== undefined ? gpu.temperature : '数据不可用';
                // 计算显存使用百分比
                const memoryUtilizationPercent = totalMemoryGB > 0 ? ((allocatedMemoryGB / totalMemoryGB) * 100).toFixed(1) : '0.0';
                // GPU利用率已经是百分比值，不需要再乘以100
                const gpuUtilizationRate = gpuUtilization.toFixed(1);

                // 确定显存使用徽章颜色
                let memoryBadgeColor = 'badge-memory';
                if (memoryUtilizationPercent > 90) {
                    memoryBadgeColor = 'badge-temperature';
                } else if (memoryUtilizationPercent > 70) {
                    memoryBadgeColor = 'badge-available';
                }

                // 确定GPU利用率徽章颜色
                let utilizationBadgeColor = 'badge-utilization';
                if (gpuUtilizationRate === 'NaN') {
                    utilizationBadgeColor = 'badge-secondary';
                } else if (parseFloat(gpuUtilizationRate) > 90) {
                    utilizationBadgeColor = 'badge-temperature';
                } else if (parseFloat(gpuUtilizationRate) > 70) {
                    utilizationBadgeColor = 'badge-available';
                }

                // 确定可用显存徽章颜色
                const availablePercent = (availableMemoryGB / totalMemoryGB * 100).toFixed(1);
                let availableBadgeColor = 'badge-utilization';
                if (availablePercent < 10) {
                    availableBadgeColor = 'badge-temperature';
                } else if (availablePercent < 30) {
                    availableBadgeColor = 'badge-available';
                }

                // 确定温度徽章颜色
                let tempBadgeColor = 'badge-utilization';
                if (typeof temperature === 'string') {
                    tempBadgeColor = 'badge-secondary';
                } else if (temperature > 80) {
                    tempBadgeColor = 'badge-temperature';
                } else if (temperature > 60) {
                    tempBadgeColor = 'badge-available';
                }

                // 创建GPU信息卡片
                const gpuCard = document.createElement('div');
                gpuCard.className = 'gpu-card';

                // 设置GPU信息
                gpuCard.innerHTML = `
                <div class="gpu-card-content">
                    <span class="gpu-id-badge">GPU ${gpu.id}</span>
                    <span class="gpu-info-badge ${memoryBadgeColor}" title="已使用 ${allocatedMemoryGB}G / 总共 ${totalMemoryGB}G (${memoryUtilizationPercent}%)">
                        ${allocatedMemoryGB}G/${totalMemoryGB}G (${memoryUtilizationPercent}%)
                    </span>
                    <span class="gpu-info-badge ${utilizationBadgeColor}" title="GPU利用率: ${gpuUtilizationRate}%">
                        利用率: ${gpuUtilizationRate}%
                    </span>
                    <span class="gpu-info-badge ${availableBadgeColor}" title="空闲显存: ${gpu.free_memory ? gpu.free_memory.toFixed(1) : 'N/A'}G">
                        空闲: ${gpu.free_memory ? gpu.free_memory.toFixed(1) : 'N/A'}G
                    </span>
                    <span class="gpu-info-badge ${availableBadgeColor}" title="实际可用显存: ${gpu.available_memory ? gpu.available_memory.toFixed(1) : 'N/A'}G">
                        可用: ${gpu.available_memory ? gpu.available_memory.toFixed(1) : 'N/A'}G
                    </span>
                    <span class="gpu-info-badge ${tempBadgeColor}" title="GPU温度: ${temperature}${typeof temperature === 'string' ? '' : '°C'}">
                        温度: ${temperature}${typeof temperature === 'string' ? '' : '°C'}
                    </span>
                </div>
            `;

                // 将GPU卡片添加到容器
                gpuCardsContainer.appendChild(gpuCard);
            });
        } else if (gpuInfo.success && (!gpuInfo.gpus || gpuInfo.gpus.length === 0)) {
            // 清空卡片容器并显示提示信息
            gpuCardsContainer.innerHTML = '<div class="alert alert-info">未检测到GPU设备</div>';
        } else {
            // 显示错误信息
            gpuCardsContainer.innerHTML = '<div class="alert alert-danger">获取GPU信息失败: ' + (gpuInfo.error || '未知错误') + '</div>';
        }
    }

    /**
     * 停止GPU监控
     */
    stopGPUMonitoring() {
        // 移除点击事件监听器
        document.removeEventListener('click', this.handleClick);

        // 从定时器管理器中移除任务
        timerManager.removeTask('gpuMonitoring');

        this.isMonitoring = false;
    }

    /**
     * 设置智能GPU选择功能
     */
    setupSmartGPUSelection() {
        // 监听模型选择变化，智能推荐GPU
        const modelSelector = document.getElementById('modelSelector');
        if (modelSelector) {
            modelSelector.addEventListener('change', () => {
                this.smartSelectGPU();
            });
        }
    }

    /**
     * 更新GPU选择器
     */
    async updateGPUSelector(gpuInfo = null) {
        const gpuSelector = document.getElementById('gpuSelector');
        if (!gpuSelector) return;

        try {
            // 获取GPU选择器数据
            const response = await fetch('/gpu_selector');
            const selectorData = await response.json();

            if (!selectorData.success) {
                statusLogger.warning('获取GPU选择器数据失败: ' + selectorData.error);
                return;
            }

            // 清空现有选项
            gpuSelector.innerHTML = '';

            // 添加所有选项（包括CPU和GPU）
            selectorData.gpus.forEach(gpu => {
                const option = document.createElement('option');
                option.value = gpu.id;

                if (gpu.type === 'cpu') {
                    option.textContent = gpu.name;
                } else {
                    option.textContent = `${gpu.name} - ${gpu.memory_info}`;

                    // 添加温度信息（如果可用）
                    if (gpu.temperature !== null && gpu.temperature !== undefined) {
                        option.textContent += ` (${gpu.temperature}°C)`;
                    }
                }

                gpuSelector.appendChild(option);
            });

            // 设置默认选择
            if (selectorData.default_selection) {
                gpuSelector.value = selectorData.default_selection;

                // 记录自动选择的信息
                if (selectorData.best_gpu_id !== null) {
                    statusLogger.info(`已自动选择显存剩余最多的GPU: GPU ${selectorData.best_gpu_id}`);
                } else {
                    statusLogger.info('未检测到可用GPU，已选择CPU处理');
                }
            }

        } catch (error) {
            statusLogger.error('更新GPU选择器时出错: ' + error.message);

            // 出错时提供基本的CPU选项
            gpuSelector.innerHTML = '';
            const cpuOption = document.createElement('option');
            cpuOption.value = 'cpu';
            cpuOption.textContent = 'CPU';
            gpuSelector.appendChild(cpuOption);
        }
    }

    /**
     * 智能选择GPU
     */
    async smartSelectGPU() {
        const modelSelector = document.getElementById('modelSelector');
        const gpuSelector = document.getElementById('gpuSelector');
        const modelMemoryRequirements = {
            'tiny': 1.0,  // GB
            'base': 1.0,
            'small': 2.0,
            'medium': 5.0,
            'large': 10.0,
            'large-v2': 10.0,
            'large-v3': 10.0,
            'turbo': 6.0
        };

        if (modelSelector && gpuSelector) {
            const selectedModel = modelSelector.value;
            const requiredMemory = modelMemoryRequirements[selectedModel];

            if (requiredMemory) {
                try {
                    const response = await fetch('/gpu_selector');
                    const selectorData = await response.json();

                    if (selectorData.success && selectorData.gpus) {
                        // 找到满足内存要求的GPU
                        let bestGPU = null;
                        let maxFreeMemory = 0;

                        selectorData.gpus.forEach(gpu => {
                            if (gpu.type === 'gpu' && gpu.memory_free >= requiredMemory) {
                                if (gpu.memory_free > maxFreeMemory) {
                                    maxFreeMemory = gpu.memory_free;
                                    bestGPU = gpu;
                                }
                            }
                        });

                        if (bestGPU) {
                            gpuSelector.value = bestGPU.id;
                            statusLogger.info(`已为模型 ${selectedModel} 自动选择${bestGPU.name} (空闲内存: ${maxFreeMemory.toFixed(1)}GB)`);
                        } else {
                            // 没有合适的GPU，选择CPU
                            gpuSelector.value = 'cpu';
                            statusLogger.warn(`模型 ${selectedModel} 需要约 ${requiredMemory}GB 内存，但所有GPU内存都不足。已自动选择CPU。`);
                        }
                    } else {
                        // 获取失败，默认选择CPU
                        gpuSelector.value = 'cpu';
                        statusLogger.info('无法获取GPU信息，已选择CPU处理');
                    }
                } catch (error) {
                    statusLogger.warning('智能选择GPU时发生错误: ' + error.message);
                    gpuSelector.value = 'cpu';
                }
            }
        }
    }
}

// 创建全局GPU监控实例
const gpuMonitor = new GPUMonitor();

// 在页面卸载时停止监控
window.addEventListener('beforeunload', () => {
    gpuMonitor.stopGPUMonitoring();
});
