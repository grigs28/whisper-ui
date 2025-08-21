/**
 * 音频播放器组件
 */

class AudioPlayer {
    constructor() {
        this.currentFile = null;
        this.audioElement = null;
        this.init();
    }

    /**
     * 初始化音频播放器
     */
    init() {
        // 等待DOM加载完成后再设置事件监听器
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.setupEventListeners();
            });
        } else {
            this.setupEventListeners();
        }
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 可以在这里添加其他全局事件监听器
        // 例如键盘快捷键等
    }

    /**
     * 播放音频文件
     * @param {string} filename - 音频文件名
     */
    playAudio(filename) {
        this.currentFile = filename;
        const audioSrc = `/download/upload/${encodeURIComponent(filename)}`;
        
        // 动态创建或获取音频元素
        if (!this.audioElement) {
            this.createAudioElement();
        }
        
        if (this.audioElement) {
            // 设置音频源
            this.audioElement.src = audioSrc;
            
            // 更新文件名显示
            if (this.fileNameElement) {
                this.fileNameElement.innerHTML = `<i class="fas fa-music me-2"></i>${filename}`;
            }
            
            // 显示播放器
            this.showPlayer();
            
            // 自动播放音频
            this.audioElement.play().catch(error => {
                statusLogger.error('自动播放失败: ' + error.message);
            });
        }
    }

    /**
     * 动态创建音频播放器元素
     */
    createAudioElement() {
        if (!document.getElementById('floatingAudioPlayer')) {
            // 创建浮动播放器容器
            const playerContainer = document.createElement('div');
            playerContainer.id = 'floatingAudioPlayer';
            playerContainer.className = 'position-fixed bg-white border rounded shadow-lg';
            playerContainer.style.cssText = `
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                z-index: 1055;
                min-width: 400px;
                display: none;
            `;
            
            // 创建标题栏
            const titleBar = document.createElement('div');
            titleBar.className = 'bg-primary text-white p-2 rounded-top d-flex justify-content-between align-items-center';
            
            // 创建文件名显示
            const fileName = document.createElement('span');
            fileName.id = 'audioPlayerFileName';
            fileName.className = 'fw-bold';
            fileName.innerHTML = '<i class="fas fa-music me-2"></i>音频播放器';
            
            // 创建关闭按钮
            const closeButton = document.createElement('button');
            closeButton.type = 'button';
            closeButton.className = 'btn-close btn-close-white';
            closeButton.onclick = () => this.hidePlayer();
            
            // 添加到标题栏
            titleBar.appendChild(fileName);
            titleBar.appendChild(closeButton);
            
            // 创建播放器内容区域
            const playerBody = document.createElement('div');
            playerBody.className = 'p-3';
            
            // 创建音频元素
            const audioElement = document.createElement('audio');
            audioElement.id = 'modalAudioPlayer';
            audioElement.controls = true;
            audioElement.className = 'w-100';
            audioElement.innerHTML = '您的浏览器不支持音频播放。';
            
            // 添加到播放器内容区域
            playerBody.appendChild(audioElement);
            
            // 添加到容器中
            playerContainer.appendChild(titleBar);
            playerContainer.appendChild(playerBody);
            
            // 添加到页面中
            document.body.appendChild(playerContainer);
            
            // 更新引用
            this.audioElement = audioElement;
            this.playerContainer = playerContainer;
            this.fileNameElement = fileName;
            
            // 添加事件监听器
            this.audioElement.addEventListener('ended', () => {
                this.onAudioEnded();
            });
        } else {
            this.audioElement = document.getElementById('modalAudioPlayer');
            this.playerContainer = document.getElementById('floatingAudioPlayer');
            this.fileNameElement = document.getElementById('audioPlayerFileName');
        }
    }

    /**
     * 显示播放器
     */
    showPlayer() {
        if (this.playerContainer) {
            this.playerContainer.style.display = 'block';
        }
    }

    /**
     * 隐藏播放器
     */
    hidePlayer() {
        if (this.playerContainer) {
            this.playerContainer.style.display = 'none';
        }
        this.stopAudio();
        // 重置所有播放按钮的状态
        this.resetAllPlayButtons();
    }

    /**
     * 音频播放结束处理
     */
    onAudioEnded() {
        // 播放结束后可以做一些清理工作
        this.currentFile = null;
        this.resetAllPlayButtons();
        this.hidePlayer();
    }

    /**
     * 重置所有播放按钮的状态
     */
    resetAllPlayButtons() {
        const playButtons = document.querySelectorAll('.play-btn');
        playButtons.forEach(button => {
            button.innerHTML = '<i class="fas fa-play"></i> ';
        });
    }

    /**
     * 停止音频播放
     */
    stopAudio() {
        if (this.audioElement && !this.audioElement.paused) {
            this.audioElement.pause();
            this.audioElement.currentTime = 0;
        }
    }
}

// 创建全局音频播放器实例
const audioPlayer = new AudioPlayer();

// 全局函数用于播放音频
function playAudio(filename) {
    audioPlayer.playAudio(filename);
}

// 为播放按钮添加切换功能
document.addEventListener('DOMContentLoaded', function() {
    // 监听播放按钮点击事件
    document.addEventListener('click', function(e) {
        if (e.target.closest('.play-btn')) {
            const button = e.target.closest('.play-btn');
            const filename = button.getAttribute('data-filename');
            
            // 如果当前正在播放的文件与点击的文件相同，则停止播放
            if (audioPlayer.currentFile === filename && audioPlayer.audioElement && !audioPlayer.audioElement.paused) {
                audioPlayer.stopAudio();
                // 更新按钮文本为"播放"
                button.innerHTML = '<i class="fas fa-play"></i> ';
            } else {
                // 否则播放新的文件
                playAudio(filename);
                // 更新按钮文本为"停止"
                button.innerHTML = '<i class="fas fa-stop"></i> ';
            }
        }
    });
});
