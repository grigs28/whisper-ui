/**
 * GPU监控组件
 */

class GPUMonitor {
    constructor() {
        this.gpuInfoInterval = null;
        this.handleClick = this.handleClick.bind(this);
        this.init();
    }

    /**
     * 初始化GPU监控
     */
    init() {
        this.startGPUMonitoring();
        this.setupSmartGPUSelection();
    }

    /**
     * 处理点击事件
     */
    handleClick(event) {
        // 检查点击的元素，避免在特定元素上触发GPU刷新
        const target = event.target;
        const excludeSelectors = [
            'button', 'input', 'select', 'textarea', 'a',
            '.btn', '.form-control', '.dropdown-toggle',
            '#startTranscriptionBtn' // 特别排除转录按钮
        ];
        
        // 检查是否点击了需要排除的元素
        for (const selector of excludeSelectors) {
            if (target.matches(selector) || target.closest(selector)) {
                return; // 不触发GPU刷新
            }
        }
        
        // 刷新GPU信息
        this.fetchGPUInfo();
    }

    /**
     * 开始GPU监控
     */
    startGPUMonitoring() {
        // 立即获取一次GPU信息
        this.fetchGPUInfo();
        
        // 先移除可能存在的旧监听器，避免重复绑定
        document.removeEventListener('click', this.handleClick);
        
        // 添加全局点击事件监听器，点击页面任意位置刷新GPU信息
        document.addEventListener('click', this.handleClick);
    }

    /**
     * 获取GPU信息
     */
    async fetchGPUInfo() {
        try {
            const response = await fetch('/gpu_info');
            const gpuInfo = await response.json();
            
            if (gpuInfo.success) {
                this.updateGPUInfoDisplay(gpuInfo);
                this.updateGPUSelector(gpuInfo);
                statusLogger.gpuInfo('GPU信息获取成功', gpuInfo);
            } else {
                statusLogger.error('获取GPU信息失败', { error: gpuInfo.error });
                console.warn('获取GPU信息失败:', gpuInfo.error);
            }
        } catch (error) {
            statusLogger.error('获取GPU信息时发生错误', { error: error.message });
            console.warn('获取GPU信息时发生错误:', error);
        }
    }

    /**
     * 更新GPU信息显示
     */
    updateGPUInfoDisplay(gpuInfo) {
        // 更新右上角GPU状态显示
        const gpuStatusText = document.getElementById('gpuStatusText');
        const gpuMemoryText = document.getElementById('gpuMemoryText');
        const gpuTempText = document.getElementById('headerGpuTemperature');
        
        if (gpuStatusText && gpuMemoryText) {
            if (gpuInfo.success) {
                if (gpuInfo.memory) {
                    // 显示GPU状态和内存使用情况
                    gpuStatusText.textContent = gpuInfo.device_name || '正常';
                    const total = gpuInfo.memory.total;
                    const used = gpuInfo.memory.used;
                    const percentage = Math.round((used / total) * 100);
                    gpuMemoryText.textContent = `${formatFileSize(used)} / ${formatFileSize(total)} (${percentage}%)`;
                    gpuMemoryText.className = 'badge bg-secondary'; // 默认样式
                } else {
                    gpuStatusText.textContent = '无GPU';
                    gpuMemoryText.textContent = '--';
                    gpuMemoryText.className = 'badge bg-secondary';
                }
            } else {
                gpuStatusText.textContent = '错误';
                gpuMemoryText.textContent = gpuInfo.error || '未知错误';
                gpuMemoryText.className = 'badge bg-danger';
            }
        }
        
        // 更新GPU温度显示
        if (gpuTempText) {
            if (gpuInfo.success && gpuInfo.temperature !== undefined) {
                gpuTempText.textContent = `${gpuInfo.temperature}°C`;
            } else {
                gpuTempText.textContent = '--°C';
            }
        }

        // 保持原有功能不变
        // 更新GPU内存显示
        const gpuMemoryElement = document.getElementById('headerGpuMemory');
        if (gpuMemoryElement) {
            if (gpuInfo.memory) {
                const total = gpuInfo.memory.total;
                const used = gpuInfo.memory.used;
                const percentage = Math.round((used / total) * 100);
                gpuMemoryElement.textContent = `${formatFileSize(used)} / ${formatFileSize(total)} (${percentage}%)`;
            } else {
                gpuMemoryElement.textContent = '--';
            }
        }

        // 更新GPU温度显示
        const gpuTempElement = document.getElementById('headerGpuTemperature');
        if (gpuTempElement) {
            if (gpuInfo.temperature) {
                gpuTempElement.textContent = `${gpuInfo.temperature}°C`;
            } else {
                gpuTempElement.textContent = '--°C';
            }
        }
    }

    /**
     * 停止GPU监控
     */
    stopGPUMonitoring() {
        // 移除点击事件监听器
        document.removeEventListener('click', this.handleClick);
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
    updateGPUSelector(gpuInfo) {
        const gpuSelector = document.getElementById('gpuSelector');
        if (!gpuSelector || !gpuInfo.success || !gpuInfo.gpus) return;
        
        // 清空现有选项（除了CPU选项）
        const cpuOption = gpuSelector.querySelector('option[value=""]');
        gpuSelector.innerHTML = '';
        if (cpuOption) {
            gpuSelector.appendChild(cpuOption);
        } else {
            const newCpuOption = document.createElement('option');
            newCpuOption.value = '';
            newCpuOption.textContent = '使用CPU';
            gpuSelector.appendChild(newCpuOption);
        }
        
        // 添加GPU选项
        gpuInfo.gpus.forEach(gpu => {
            const option = document.createElement('option');
            option.value = gpu.id;
            const freeMemoryGB = (gpu.memory.free / (1024 ** 3)).toFixed(1);
            option.textContent = `GPU ${gpu.id}: ${gpu.name} (空闲: ${freeMemoryGB}GB)`;
            
            // 如果这是推荐的GPU，设为选中
            if (gpu.id === gpuInfo.best_gpu) {
                option.selected = true;
            }
            
            gpuSelector.appendChild(option);
        });
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
                    const response = await fetch('/gpu_info');
                    const gpuInfo = await response.json();
                    
                    if (gpuInfo.success && gpuInfo.gpus) {
                        // 找到满足内存要求的GPU
                        let bestGPU = null;
                        let maxFreeMemory = 0;
                        
                        gpuInfo.gpus.forEach(gpu => {
                            const freeMemoryGB = gpu.memory.free / (1024 ** 3);
                            if (freeMemoryGB >= requiredMemory && freeMemoryGB > maxFreeMemory) {
                                maxFreeMemory = freeMemoryGB;
                                bestGPU = gpu;
                            }
                        });
                        
                        if (bestGPU) {
                            gpuSelector.value = bestGPU.id;
                            statusLogger.info(`已为模型 ${selectedModel} 自动选择GPU ${bestGPU.id} (空闲内存: ${maxFreeMemory.toFixed(1)}GB)`);
                        } else {
                            // 没有合适的GPU，选择CPU
                            gpuSelector.value = '';
                            statusLogger.warn(`模型 ${selectedModel} 需要约 ${requiredMemory}GB 内存，但所有GPU内存都不足。已自动选择CPU。`);
                        }
                    }
                } catch (error) {
                    console.warn('智能选择GPU时发生错误:', error);
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
