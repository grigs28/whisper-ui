/**
 * 文件管理器
 */

class FileManager {
    constructor() {
        this.selectedFiles = new Set(); // 添加选中文件集合
        this.init();
    }

    /**
     * 初始化文件管理器
     */
    init() {
        // 初始化方法，目前为空，可扩展功能
        this.setupEventListeners();
        return this;
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 为上传文件的复选框添加事件监听器（使用事件委托）
        document.addEventListener('change', (event) => {
            if (event.target.classList.contains('uploaded-file-checkbox')) {
                this.handleFileSelection(event.target);
            }
        });
        
        // 为表头中的全选复选框添加事件监听器
        const headerSelectAllCheckbox = document.getElementById('uploadedFileSelectAll');
        if (headerSelectAllCheckbox) {
            headerSelectAllCheckbox.addEventListener('change', () => {
                this.toggleSelectAll('uploaded');
            });
        }
        
        // 为全选按钮添加事件监听器
        const selectAllButton = document.getElementById('selectAllUploaded');
        if (selectAllButton) {
            selectAllButton.addEventListener('click', () => {
                this.toggleSelectAll('uploaded');
            });
        }
        
        // 为删除选中文件按钮添加事件监听器
        const deleteSelectedButton = document.getElementById('deleteSelectedUploaded');
        if (deleteSelectedButton) {
            deleteSelectedButton.addEventListener('click', () => {
                this.deleteSelectedFiles('uploaded');
            });
        }
        
        // 转录按钮事件已在transcriptionController.js中处理，避免重复绑定
        
        // 为输出文件的操作按钮添加事件监听器
        const selectAllOutputButton = document.getElementById('selectAllOutput');
        if (selectAllOutputButton) {
            selectAllOutputButton.addEventListener('click', () => {
                this.toggleSelectAll('output');
            });
        }
        
        const deleteSelectedOutputButton = document.getElementById('deleteSelectedOutput');
        if (deleteSelectedOutputButton) {
            deleteSelectedOutputButton.addEventListener('click', () => {
                this.deleteSelectedFiles('output');
            });
        }
    }

    /**
     * 处理文件选择事件
     */
    handleFileSelection(checkbox) {
        if (checkbox.checked) {
            this.selectedFiles.add(checkbox.value);
        } else {
            this.selectedFiles.delete(checkbox.value);
        }
        this.updateSelectAllButton();
    }

    /**
     * 切换全选
     */
    toggleSelectAll(type) {
        try {
            const checkboxes = document.querySelectorAll(`.${type}-file-checkbox`);
            const selectAllCheckbox = document.querySelector(`#${type}FileSelectAll`);
            const isChecked = selectAllCheckbox?.checked || false;
            
            // 正确的逻辑：如果当前是选中状态，则取消全选；否则全选
            const shouldCheckAll = !isChecked;
            
            checkboxes.forEach(checkbox => {
                checkbox.checked = shouldCheckAll;
                if (type === 'uploaded') {
                    if (shouldCheckAll) {
                        this.selectedFiles.add(checkbox.value);
                    } else {
                        this.selectedFiles.delete(checkbox.value);
                    }
                }
            });
            
            // 更新全选按钮状态
            if (selectAllCheckbox) {
                selectAllCheckbox.checked = shouldCheckAll;
            }
            this.updateSelectAllButton();
        } catch (error) {
            statusLogger.error('切换全选时发生错误', { error: error.message });
        }
    }

    /**
     * 更新全选按钮状态
     */
    updateSelectAllButton() {
        try {
            // 延迟执行，确保DOM完全更新
            setTimeout(() => {
                try {
                    const selectAllCheckbox = document.getElementById('uploadedFileSelectAll');
                    // 检查元素是否存在
                    if (!selectAllCheckbox) {
                        statusLogger.warning('未找到上传文件全选复选框元素');
                        return;
                    }
                    const checkboxes = document.querySelectorAll('.uploaded-file-checkbox');
                    const checkedCount = this.selectedFiles.size;
                    const totalCount = checkboxes.length;

                    if (totalCount > 0) {
                        selectAllCheckbox.checked = checkedCount === totalCount;
                    } else {
                        selectAllCheckbox.checked = false;
                    }
                } catch (error) {
                    statusLogger.error('更新全选按钮状态时发生错误', { error: error.message });
                }
            }, 0);
        } catch (error) {
            statusLogger.error('更新全选按钮状态时发生错误', { error: error.message });
        }
    }

    /**
     * 选择新上传的文件（只选择新上传的文件）
     */
    selectNewlyUploadedFiles(filenames) {
        // 清空之前的选择
        this.selectedFiles.clear();
        
        // 选择新上传的文件
        const checkboxes = document.querySelectorAll('.uploaded-file-checkbox');
        let selectedCount = 0;
        checkboxes.forEach(checkbox => {
            if (filenames.includes(checkbox.value)) {
                checkbox.checked = true;
                this.selectedFiles.add(checkbox.value);
                selectedCount++;
            } else {
                checkbox.checked = false;
            }
        });
        this.updateSelectAllButton();
        statusLogger.system(`Selected ${selectedCount} newly uploaded files: ${filenames.join(', ')}`);
    }

    /**
     * 处理文件上传
     */
    async handleFiles(files) {
        if (files.length === 0) return;

        const uploadProgress = document.getElementById('uploadProgress');
        const progressBar = uploadProgress?.querySelector('.progress-bar');
        const progressText = uploadProgress?.querySelector('.progress-text');
        
        // 初始化进度条
        if (uploadProgress) {
            uploadProgress.style.display = 'block';
        }
        if (progressBar) {
            progressBar.style.width = '0%';
        }
        if (progressText) {
            progressText.textContent = '0%';
        }

        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }

        try {
            statusLogger.info(`开始上传 ${files.length} 个文件...`);
            
            // 使用Promise包装XMLHttpRequest以支持进度条
            const result = await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                
                // 监听上传进度
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percent = Math.round((e.loaded / e.total) * 100);
                        if (progressBar) {
                            progressBar.style.width = `${percent}%`;
                        }
                        if (progressText) {
                            progressText.textContent = `${percent}%`;
                        }
                    }
                });
                
                // 监听请求完成
                xhr.addEventListener('load', () => {
                    if (xhr.status === 200) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            resolve(response);
                        } catch (e) {
                            reject(new Error('响应解析失败'));
                        }
                    } else {
                        reject(new Error(`上传失败: ${xhr.status}`));
                    }
                });
                
                // 监听错误
                xhr.addEventListener('error', () => {
                    reject(new Error('网络错误'));
                });
                
                xhr.open('POST', '/upload');
                xhr.send(formData);
            });

            if (result.success) {
                statusLogger.success(`成功上传 ${result.filenames.length} 个文件`, result);
                showNotification(`成功上传 ${result.filenames.length} 个文件`, 'success');
                
                // 隐藏进度条
                if (uploadProgress) {
                    uploadProgress.style.display = 'none';
                }
                
                // 清空文件输入框
                document.getElementById('fileInput').value = '';
                
                // 重新加载文件列表（使用AJAX方式，而不是刷新页面）
                await this.refreshFileList('uploaded');
                
                // 在列表刷新后选择新上传的文件
                this.selectNewlyUploadedFiles(result.filenames);
                
                // 刷新任务队列框，显示队列中的文件
                if (typeof queueManager !== 'undefined') {
                    queueManager.loadQueueState();
                }
            } else {
                statusLogger.error('文件上传失败', result);
                showNotification(`上传失败: ${result.error}`, 'danger');
                if (uploadProgress) {
                    uploadProgress.style.display = 'none';
                }
            }
        } catch (error) {
            statusLogger.error('上传过程中发生错误', { error: error.message });
            showNotification('上传过程中发生错误', 'danger');
            if (uploadProgress) {
                uploadProgress.style.display = 'none';
            }
        }
    }

    /**
     * 删除选中的文件
     */
    async deleteSelectedFiles(type) {
        const checkboxes = document.querySelectorAll(`.${type}-file-checkbox:checked`);
        const filenames = Array.from(checkboxes).map(cb => cb.value);
        
        if (filenames.length === 0) {
            showNotification('请先选择要删除的文件', 'warning');
            return;
        }

        if (!confirm(`确定要删除选中的 ${filenames.length} 个文件吗？`)) {
            return;
        }

        try {
            statusLogger.system(`开始批量删除${type === 'uploaded' ? '上传' : '输出'}文件`, { filenames });
            
            // 批量删除文件，提高效率
            const deletePromises = filenames.map(async (filename) => {
                try {
                    const response = await fetch(`/delete_${type}/${encodeURIComponent(filename)}`, {
                        method: 'DELETE'
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        statusLogger.success(`${type === 'uploaded' ? '上传' : '输出'}文件已删除`, { filename });
                        return { filename, success: true };
                    } else {
                        statusLogger.error(`${type === 'uploaded' ? '上传' : '输出'}文件删除失败`, { filename, error: result.error });
                        return { filename, success: false, error: result.error };
                    }
                } catch (error) {
                    statusLogger.error(`${type === 'uploaded' ? '上传' : '输出'}文件删除时发生错误`, { filename, error: error.message });
                    return { filename, success: false, error: error.message };
                }
            });
            
            // 等待所有删除操作完成
            const results = await Promise.all(deletePromises);
            
            // 检查是否有删除失败的文件
            const failedDeletes = results.filter(result => !result.success);
            const successDeletes = results.filter(result => result.success);
            
            if (failedDeletes.length > 0) {
                statusLogger.warning(`删除操作完成，成功删除 ${successDeletes.length} 个文件，失败 ${failedDeletes.length} 个文件`, { failedFiles: failedDeletes });
                showNotification(`删除完成：成功 ${successDeletes.length} 个，失败 ${failedDeletes.length} 个`, 'warning');
            } else {
                statusLogger.success(`成功删除 ${filenames.length} 个文件`, { filenames });
                showNotification(`成功删除 ${filenames.length} 个文件`, 'success');
            }
            
            // 从选中文件集合中移除已删除的文件
            if (type === 'uploaded') {
                successDeletes.forEach(result => {
                    this.selectedFiles.delete(result.filename);
                });
            }
            
            // 重新加载文件列表 - 只刷新一次，提高性能
            await this.refreshFileList(type);
            
            // 清空选中文件集合
            this.selectedFiles.clear();
            // 更新全选按钮状态
            this.updateSelectAllButton();
            
            statusLogger.system(`批量删除${type === 'uploaded' ? '上传' : '输出'}文件完成`, { successCount: successDeletes.length, failCount: failedDeletes.length });
            
        } catch (error) {
            statusLogger.error('删除文件时发生错误', { error: error.message });
            showNotification('删除文件时发生错误，请重试', 'danger');
            // 即使发生错误也要尝试刷新列表，确保UI同步
            try {
                await this.refreshFileList(type);
            } catch (refreshError) {
                statusLogger.error('刷新文件列表失败', { error: refreshError.message });
            }
        }
    }

    /**
     * 刷新文件列表
     */
    async refreshFileList(type) {
        try {
            statusLogger.system(`开始刷新${type === 'uploaded' ? '上传' : '输出'}文件列表`);
            console.log(`[FileManager] 开始刷新${type === 'uploaded' ? '上传' : '输出'}文件列表`);
            
            // 根据类型获取对应的文件列表
            const response = await fetch(`/${type === 'uploaded' ? 'uploaded' : 'output'}_files`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            // 更新对应的文件列表
            if (type === 'uploaded') {
                statusLogger.system('准备更新上传文件列表');
                await this.updateUploadedFileList(result.files || []);
                statusLogger.system('上传文件列表更新完成');
            } else {
                statusLogger.system('准备更新输出文件列表');
                await this.updateOutputFileList(result.files || []);
                statusLogger.system('输出文件列表更新完成');
            }
            
            // 更新页面标题中的文件数量
            this.updateFileCountBadges();
            
            statusLogger.system(`${type === 'uploaded' ? '上传' : '输出'}文件列表刷新完成`);
        } catch (error) {
            statusLogger.error('刷新文件列表失败', { error: error.message });
            showNotification('刷新文件列表失败，请刷新页面重试', 'danger');
        }
    }
    
    /**
     * 更新文件数量徽章
     */
    updateFileCountBadges() {
        try {
            // 更新上传文件数量徽章
            const uploadedBadge = document.querySelector('.col-md-6:first-child .card-header .badge');
            const uploadedCheckboxes = document.querySelectorAll('.uploaded-file-checkbox');
            if (uploadedBadge) {
                uploadedBadge.textContent = uploadedCheckboxes.length;
            }
            
            // 更新输出文件数量徽章
            const outputBadge = document.querySelector('.col-md-6:last-child .card-header .badge');
            const outputCheckboxes = document.querySelectorAll('.output-file-checkbox');
            if (outputBadge) {
                outputBadge.textContent = outputCheckboxes.length;
            }
        } catch (error) {
            statusLogger.error('更新文件数量徽章失败', { error: error.message });
        }
    }

    /**
     * 更新上传文件列表
     */
    updateUploadedFileList(files) {
        try {
            // 查找上传文件表格的容器
            const uploadedContainer = document.querySelector('.col-md-6:first-child .card-body');
            if (!uploadedContainer) {
                statusLogger.error('未能找到上传文件容器');
                return;
            }
            
            statusLogger.system('找到上传文件容器，开始更新内容');
            
            // 保留操作按钮区域
            const operationButtons = uploadedContainer.querySelector('.d-flex.justify-content-between');
            
            // 清空除操作按钮外的内容
            uploadedContainer.innerHTML = '';
            if (operationButtons) {
                uploadedContainer.appendChild(operationButtons);
            }
            
            if (files.length === 0) {
                const emptyDiv = document.createElement('div');
                emptyDiv.className = 'text-center py-4';
                emptyDiv.innerHTML = `
                    <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                    <p class="text-muted">暂无上传的文件</p>
                `;
                uploadedContainer.appendChild(emptyDiv);
                statusLogger.system('上传文件列表为空');
                return;
            }
            
            // 创建表格容器
            const tableContainer = document.createElement('div');
            tableContainer.className = 'table-responsive';
            tableContainer.style.maxHeight = '300px';
            tableContainer.style.overflowY = 'auto';
            
            // 创建表格
            const table = document.createElement('table');
            table.id = 'uploadedFilesTable';
            table.className = 'table table-hover mb-0';
            
            // 创建表头
            table.innerHTML = `
                <thead>
                    <tr>
                        <th width="5%">
                            <input type="checkbox" id="uploadedFileSelectAll">
                        </th>
                        <th>文件名</th>
                        <th>大小</th>
                        <th>修改时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody></tbody>
            `;
            
            const tableBody = table.querySelector('tbody');
            
            // 添加新的文件行
            files.forEach(file => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><input type="checkbox" class="uploaded-file-checkbox" value="${file.name}"></td>
                    <td>${file.name}</td>
                    <td>${this.formatFileSize(file.size)}</td>
                    <td>${file.modified}</td>
                    <td>
                        <div class="btn-group btn-group-sm" role="group">
                            <button class="btn btn-outline-primary play-btn" data-filename="${file.name}">
                                <i class="fas fa-play"></i> 
                            </button>
                            <a href="/download/upload/${file.name}" class="btn btn-outline-success">
                                <i class="fas fa-download"></i>
                            </a>
                            <button class="btn btn-outline-danger" onclick="deleteUploadedFile('${file.name}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>
                `;
                tableBody.appendChild(row);
            });
            
            tableContainer.appendChild(table);
            uploadedContainer.appendChild(tableContainer);
            
            statusLogger.system(`成功更新上传文件列表，共 ${files.length} 个文件`);
            
            // 重新绑定全选复选框事件 - 增加安全检查
            setTimeout(() => {
                try {
                    const newSelectAllCheckbox = document.getElementById('uploadedFileSelectAll');
                    if (newSelectAllCheckbox) {
                        newSelectAllCheckbox.addEventListener('change', () => {
                            this.toggleSelectAll('uploaded');
                        });
                    }
                } catch (e) {
                    statusLogger.error('重新绑定全选复选框事件时发生错误', { error: e.message });
                }
            }, 0);
        } catch (error) {
            statusLogger.error('更新上传文件列表时发生错误', { error: error.message });
        }
    }

    /**
     * 更新输出文件列表
     */
    updateOutputFileList(files) {
        try {
            // 查找输出文件表格的容器
            const outputContainer = document.querySelector('.col-md-6:last-child .card-body');
            if (!outputContainer) {
                statusLogger.error('未能找到输出文件容器');
                return;
            }
            
            statusLogger.system('找到输出文件容器，开始更新内容');
            
            // 保留操作按钮区域
            const operationButtons = outputContainer.querySelector('.d-flex.justify-content-between');
            
            // 清空除操作按钮外的内容
            outputContainer.innerHTML = '';
            if (operationButtons) {
                outputContainer.appendChild(operationButtons);
            }
            
            if (files.length === 0) {
                const emptyDiv = document.createElement('div');
                emptyDiv.className = 'text-center py-4';
                emptyDiv.innerHTML = `
                    <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                    <p class="text-muted">暂无转录结果</p>
                `;
                outputContainer.appendChild(emptyDiv);
                statusLogger.system('输出文件列表为空');
                return;
            }
            
            // 创建表格容器
            const tableContainer = document.createElement('div');
            tableContainer.className = 'table-responsive';
            tableContainer.style.maxHeight = '300px';
            tableContainer.style.overflowY = 'auto';
            
            // 创建表格
            const table = document.createElement('table');
            table.id = 'outputFilesTable';
            table.className = 'table table-hover mb-0';
            
            // 创建表头
            table.innerHTML = `
                <thead>
                    <tr>
                        <th width="5%">
                            <input type="checkbox" id="outputFileSelectAll">
                        </th>
                        <th>文件名</th>
                        <th>大小</th>
                        <th>修改时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody></tbody>
            `;
            
            const tableBody = table.querySelector('tbody');
            
            // 添加新的文件行
            files.forEach(file => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><input type="checkbox" class="output-file-checkbox" value="${file.name}"></td>
                    <td>${file.name}</td>
                    <td>${this.formatFileSize(file.size)}</td>
                    <td>${file.modified}</td>
                    <td>
                        <div class="btn-group btn-group-sm" role="group">
                            <a href="/download/output/${file.name}" class="btn btn-outline-success">
                                <i class="fas fa-download"></i>
                            </a>
                            <button class="btn btn-outline-danger" onclick="deleteOutputFile('${file.name}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>
                `;
                tableBody.appendChild(row);
            });
            
            tableContainer.appendChild(table);
            outputContainer.appendChild(tableContainer);
            
            statusLogger.system(`成功更新输出文件列表，共 ${files.length} 个文件`);
            console.log(`[FileManager] 成功更新输出文件列表，共 ${files.length} 个文件`);
            
            // 重新绑定全选复选框事件 - 增加安全检查
            setTimeout(() => {
                try {
                    const newSelectAllCheckbox = document.getElementById('outputFileSelectAll');
                    if (newSelectAllCheckbox) {
                        newSelectAllCheckbox.addEventListener('change', () => {
                            this.toggleSelectAll('output');
                        });
                    }
                } catch (e) {
                    statusLogger.error('重新绑定全选复选框事件时发生错误', { error: e.message });
                }
            }, 0);
        } catch (error) {
            statusLogger.error('更新输出文件列表时发生错误', { error: error.message });
        }
    }

    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * 加载文件列表
     */
    async loadFiles() {
        try {
            // 这里可以实现从服务器获取文件列表的逻辑
            // 目前只是示例代码
            return true;
        } catch (error) {
            statusLogger.error('加载文件列表失败', { error: error.message });
            throw error;
        }
    }

    /**
     * 开始转录
     */
    async startTranscription() {
        // 获取选中的文件
        const selectedFiles = Array.from(this.selectedFiles);
        if (selectedFiles.length === 0) {
            showNotification('请至少选择一个文件进行转录', 'warning');
            return;
        }

        // 获取转录设置
        const model = document.getElementById('modelSelector')?.value || 'base';
        const language = document.getElementById('languageSelector')?.value || 'zh';
        const gpu = document.getElementById('gpuSelector')?.value || '';

        try {
            statusLogger.info('开始转录任务...', { files: selectedFiles, model, language, gpu });
            
            const response = await fetch('/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    files: selectedFiles,
                    model: model,
                    language: language,
                    gpus: gpu ? [gpu] : [] // 确保传递数组格式
                })
            });

            const result = await response.json();

            if (result.success) {
                statusLogger.success('转录任务已启动', result);
                showNotification('转录任务已启动', 'success');
                // 清空选中文件集合
                this.selectedFiles.clear();
                // 更新UI
                this.updateSelectAllButton();
            } else {
                statusLogger.error('转录任务启动失败', result);
                showNotification(`转录失败: ${result.error}`, 'danger');
            }
        } catch (error) {
            statusLogger.error('转录过程中发生错误', { error: error.message });
            showNotification('转录过程中发生错误', 'danger');
        }
    }
}

// 创建全局文件管理器实例
const fileManager = new FileManager();
// 将fileManager设置为全局变量，以便其他模块访问
window.fileManager = fileManager;

// 这些函数已移动到templates/index.html中，避免重复定义

// 全局函数用于删除上传的文件
async function deleteUploadedFile(filename) {
    if (!confirm('确定要删除这个文件吗？')) {
        return;
    }
    
    try {
        statusLogger.system('开始删除上传文件', { filename });
        
        const response = await fetch(`/delete_uploaded/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            statusLogger.success('上传文件已删除', { filename });
            showNotification('文件已删除', 'success');
            
            // 从选中文件集合中移除已删除的文件
            if (fileManager && fileManager.selectedFiles) {
                fileManager.selectedFiles.delete(filename);
            }
            
            // 重新加载文件列表 - 使用刷新方法
            if (fileManager) {
                await fileManager.refreshFileList('uploaded');
                // 更新全选按钮状态
                fileManager.updateSelectAllButton();
            }
            
            statusLogger.system('上传文件删除完成', { filename });
        } else {
            statusLogger.error('文件删除失败', { filename, error: result.error });
            showNotification(`删除失败: ${result.error}`, 'danger');
        }
    } catch (error) {
        statusLogger.error('删除文件时发生错误', { filename, error: error.message });
        showNotification('删除文件时发生错误，请重试', 'danger');
    }
}

// 全局函数用于删除输出文件
async function deleteOutputFile(filename) {
    if (!confirm('确定要删除这个文件吗？')) {
        return;
    }
    
    try {
        statusLogger.system('开始删除输出文件', { filename });
        
        const response = await fetch(`/delete_output/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            statusLogger.success('输出文件已删除', { filename });
            showNotification('文件已删除', 'success');
            
            // 重新加载文件列表 - 使用刷新方法
            if (fileManager) {
                await fileManager.refreshFileList('output');
            }
            
            statusLogger.system('输出文件删除完成', { filename });
        } else {
            statusLogger.error('输出文件删除失败', { filename, error: result.error });
            showNotification(`删除失败: ${result.error}`, 'danger');
        }
    } catch (error) {
        statusLogger.error('删除输出文件时发生错误', { filename, error: error.message });
        showNotification('删除输出文件时发生错误，请重试', 'danger');
    }
}



// 全局函数：自动选择上传的文件
function autoSelectUploadedFiles() {
    // 选择所有上传的文件
    const checkboxes = document.querySelectorAll('.uploaded-file-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = true;
    });
}

// 页面加载完成后执行初始化
document.addEventListener('DOMContentLoaded', function() {
    // 如果页面中有上传的文件，可以在这里初始化选中状态
    // 但为了避免干扰，我们不在这里自动选择所有文件
});
