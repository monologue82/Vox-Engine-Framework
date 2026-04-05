console.log('Script started loading...');
        
        // Handle image loading errors
        function handleImageError(img) {
            // Set a fallback icon based on the image name
            const imgName = img.src.split('/').pop().split('.')[0];
            
            // Use emoji as fallback for different models
            const fallbackEmojis = {
                'deepseek': '🤖',
                'qwen': '🧠',
                'llama': '🦙',
                'mistral': '💨',
                'phi': '🔷',
                'vllm': '⚡',
                'gradio': '🎨',
                'huggingface': '🤗',
                'modelscope': '🔬',
                'ollama': '🐙',
                'lmstudio': '🏠',
                'vosk': '🎤'
            };
            
            // Create a span with emoji as fallback
            const fallbackSpan = document.createElement('span');
            fallbackSpan.className = 'fallback-icon';
            fallbackSpan.textContent = fallbackEmojis[imgName] || '📱';
            
            // Replace the image with the fallback span
            if (img.parentNode) {
                img.parentNode.replaceChild(fallbackSpan, img);
            }
        }
        
        // System Monitor - Initialize on page load
        const SystemMonitor = {
            // Configuration
            checkInterval: 30000, // 30 seconds
            checkIntervalId: null,
            
            // Status tracking
            status: {
                server: 'loading',
                llamacpp: 'loading',
                vosk: 'loading',
                audio: 'loading',
                websocket: 'disconnected'
            },
            
            // Resource tracking
            resources: {
                memory: { total: 0, used: 0, percent: 0 },
                cpu: 0,
                gpu: { available: false, vram_total: 0, vram_used: 0, percent: 0, util: 0 }
            },
            
            // Initialize system monitor
            init() {
                this.cacheDOM();
                this.bindEvents();
                this.startMonitoring();
                this.checkAllSystems();
            },
            
            // Cache DOM elements
            cacheDOM() {
                this.dom = {
                    serverStatus: document.getElementById('server-status'),
                    llamacppStatus: document.getElementById('llamacpp-status'),
                    voskStatus: document.getElementById('vosk-status'),
                    audioStatus: document.getElementById('audio-status'),
                    websocketStatus: document.getElementById('websocket-status'),
                    apiEndpoint: document.getElementById('api-endpoint'),
                    lastCheckTime: document.getElementById('last-check-time'),
                    refreshBtn: document.getElementById('monitor-refresh-btn'),
                    // Resource elements
                    memoryBar: document.getElementById('memory-bar'),
                    memoryUsed: document.getElementById('memory-used'),
                    memoryTotal: document.getElementById('memory-total'),
                    memoryPercent: document.getElementById('memory-percent'),
                    cpuBar: document.getElementById('cpu-bar'),
                    cpuUsage: document.getElementById('cpu-usage'),
                    vramBar: document.getElementById('vram-bar'),
                    vramUsed: document.getElementById('vram-used'),
                    vramTotal: document.getElementById('vram-total'),
                    vramPercent: document.getElementById('vram-percent'),
                    gpuUtilBar: document.getElementById('gpu-util-bar'),
                    gpuUtilization: document.getElementById('gpu-utilization'),
                    gpuResourceCard: document.getElementById('gpu-resource-card'),
                    gpuUtilCard: document.getElementById('gpu-util-card')
                };
            },
            
            // Bind events
            bindEvents() {
                if (this.dom.refreshBtn) {
                    this.dom.refreshBtn.addEventListener('click', () => {
                        this.checkAllSystems();
                    });
                }
                
                // Update WebSocket status on connect/disconnect
                const originalSocket = window.socket;
                if (originalSocket) {
                    originalSocket.on('connect', () => this.updateWebSocketStatus('connected'));
                    originalSocket.on('disconnect', () => this.updateWebSocketStatus('disconnected'));
                }
            },
            
            // Start periodic monitoring
            startMonitoring() {
                this.checkIntervalId = setInterval(() => {
                    this.checkAllSystems();
                }, this.checkInterval);
            },
            
            // Check all systems
            async checkAllSystems() {
                this.setRefreshBtnSpinning(true);
                
                try {
                    await Promise.all([
                        this.checkServerStatus(),
                        this.checkLlamaCppStatus(),
                        this.checkVoskStatus(),
                        this.checkAudioStatus()
                    ]);
                    
                    this.updateLastCheckTime();
                } catch (error) {
                    console.error('System check failed:', error);
                } finally {
                    this.setRefreshBtnSpinning(false);
                }
            },
            
            // Check server status
            async checkServerStatus() {
                try {
                    const response = await fetch('/api/health', {
                        method: 'GET',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        this.updateServerStatus('online', `Online v${data.version || '0.3.0'}`);
                        this.dom.apiEndpoint.textContent = window.location.origin;
                        
                        // Update resource usage
                        if (data.memory) {
                            this.updateResourceUsage('memory', data.memory);
                        }
                        if (data.cpu_percent !== undefined) {
                            this.updateResourceUsage('cpu', data.cpu_percent);
                        }
                        if (data.gpu) {
                            this.updateResourceUsage('gpu', data.gpu);
                        }
                    } else {
                        throw new Error('Server returned error');
                    }
                } catch (error) {
                    this.updateServerStatus('offline', 'Offline');
                    console.warn('Server health check failed:', error);
                }
            },
            
            // Check llama.cpp status
            async checkLlamaCppStatus() {
                try {
                    const response = await fetch('/api/llama-cpp/health', {
                        method: 'GET',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        if (data.status === 'healthy') {
                            this.updateLlamaCppStatus('online', 'Healthy');
                        } else {
                            this.updateLlamaCppStatus('warning', 'Warning');
                        }
                    } else if (response.status === 503) {
                        // llama.cpp service not running or module not installed
                        const data = await response.json();
                        if (data.error === 'llama.cpp module not installed') {
                            this.updateLlamaCppStatus('offline', 'Not Installed');
                        } else if (data.error === 'llama.cpp service not running') {
                            this.updateLlamaCppStatus('warning', 'Service Not Running');
                        } else {
                            this.updateLlamaCppStatus('offline', data.status === 'unavailable' ? 'Not Available' : 'Unhealthy');
                        }
                    } else {
                        throw new Error('llama.cpp returned error');
                    }
                } catch (error) {
                    this.updateLlamaCppStatus('offline', 'Not Available');
                    console.warn('llama.cpp health check failed:', error);
                }
            },
            
            // Check Vosk models status
            async checkVoskStatus() {
                try {
                    const response = await fetch('/api/vosk-models', {
                        method: 'GET',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    if (response.ok) {
                        const models = await response.json();
                        const count = Array.isArray(models) ? models.length : 0;
                        if (count > 0) {
                            this.updateVoskStatus('online', `${count} Model${count !== 1 ? 's' : ''}`);
                        } else {
                            this.updateVoskStatus('warning', 'No Models Found');
                        }
                    } else {
                        throw new Error('Failed to fetch Vosk models');
                    }
                } catch (error) {
                    this.updateVoskStatus('offline', 'Error');
                    console.warn('Vosk status check failed:', error.message);
                }
            },
            
            // Check audio devices status
            async checkAudioStatus() {
                try {
                    const response = await fetch('/api/microphones', {
                        method: 'GET',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    if (response.ok) {
                        const devices = await response.json();
                        const count = Array.isArray(devices) ? devices.length : 0;
                        const statusText = count > 0 ? `${count} Device${count !== 1 ? 's' : ''}` : 'No Devices';
                        this.updateAudioStatus(count > 0 ? 'online' : 'warning', statusText);
                    } else {
                        throw new Error('Failed to fetch audio devices');
                    }
                } catch (error) {
                    this.updateAudioStatus('offline', 'Error');
                    console.warn('Audio status check failed:', error);
                }
            },
            
            // Update server status UI
            updateServerStatus(status, text) {
                this.status.server = status;
                if (this.dom.serverStatus) {
                    this.dom.serverStatus.innerHTML = `
                        <span class="status-dot ${status}"></span>
                        <span class="status-text">${text}</span>
                    `;
                }
            },
            
            // Update llama.cpp status UI
            updateLlamaCppStatus(status, text) {
                this.status.llamacpp = status;
                if (this.dom.llamacppStatus) {
                    this.dom.llamacppStatus.innerHTML = `
                        <span class="status-dot ${status}"></span>
                        <span class="status-text">${text}</span>
                    `;
                }
            },
            
            // Update Vosk status UI
            updateVoskStatus(status, text) {
                this.status.vosk = status;
                if (this.dom.voskStatus) {
                    this.dom.voskStatus.innerHTML = `
                        <span class="status-dot ${status}"></span>
                        <span class="status-text">${text}</span>
                    `;
                }
            },
            
            // Update audio status UI
            updateAudioStatus(status, text) {
                this.status.audio = status;
                if (this.dom.audioStatus) {
                    this.dom.audioStatus.innerHTML = `
                        <span class="status-dot ${status}"></span>
                        <span class="status-text">${text}</span>
                    `;
                }
            },
            
            // Update WebSocket status UI
            updateWebSocketStatus(status) {
                this.status.websocket = status;
                if (this.dom.websocketStatus) {
                    const statusText = status.charAt(0).toUpperCase() + status.slice(1);
                    this.dom.websocketStatus.innerHTML = `
                        <span class="connection-status ${status}">${statusText}</span>
                    `;
                }
            },
            
            // Update last check time
            updateLastCheckTime() {
                if (this.dom.lastCheckTime) {
                    const now = new Date();
                    this.dom.lastCheckTime.textContent = now.toLocaleTimeString();
                }
            },
            
            // Set refresh button spinning animation
            setRefreshBtnSpinning(spinning) {
                if (this.dom.refreshBtn) {
                    if (spinning) {
                        this.dom.refreshBtn.classList.add('spinning');
                    } else {
                        this.dom.refreshBtn.classList.remove('spinning');
                    }
                }
            },
            
            // Update resource usage
            updateResourceUsage(type, data) {
                if (type === 'memory' && this.dom.memoryBar) {
                    const percent = data.percent || 0;
                    this.resources.memory = {
                        total: data.total_gb || 0,
                        used: data.used_gb || 0,
                        percent: percent
                    };
                    
                    this.dom.memoryBar.style.width = `${percent}%`;
                    this.dom.memoryUsed.textContent = `${data.used_gb || 0} GB`;
                    this.dom.memoryTotal.textContent = `${data.total_gb || 0} GB`;
                    this.dom.memoryPercent.textContent = `${percent}%`;
                    
                    // Update bar color based on usage
                    this.dom.memoryBar.classList.remove('warning', 'danger');
                    if (percent > 90) {
                        this.dom.memoryBar.classList.add('danger');
                    } else if (percent > 70) {
                        this.dom.memoryBar.classList.add('warning');
                    }
                }
                
                if (type === 'cpu' && this.dom.cpuBar) {
                    this.resources.cpu = data;
                    this.dom.cpuBar.style.width = `${data}%`;
                    this.dom.cpuUsage.textContent = `${data}%`;
                    
                    // Update bar color based on usage
                    this.dom.cpuBar.classList.remove('warning', 'danger');
                    if (data > 90) {
                        this.dom.cpuBar.classList.add('danger');
                    } else if (data > 70) {
                        this.dom.cpuBar.classList.add('warning');
                    }
                }
                
                if (type === 'gpu' && data.available) {
                    this.resources.gpu = {
                        available: data.available,
                        vram_total: data.vram_total_gb || 0,
                        vram_used: data.vram_used_gb || 0,
                        percent: data.vram_percent || 0,
                        util: data.gpu_util_percent || 0
                    };
                    
                    // Update VRAM
                    if (this.dom.vramBar) {
                        const vramPercent = data.vram_percent || 0;
                        this.dom.vramBar.style.width = `${vramPercent}%`;
                        this.dom.vramUsed.textContent = `${data.vram_used_gb || 0} GB`;
                        this.dom.vramTotal.textContent = `${data.vram_total_gb || 0} GB`;
                        this.dom.vramPercent.textContent = `${vramPercent}%`;
                        
                        // Update bar color based on usage
                        this.dom.vramBar.classList.remove('warning', 'danger');
                        if (vramPercent > 90) {
                            this.dom.vramBar.classList.add('danger');
                        } else if (vramPercent > 70) {
                            this.dom.vramBar.classList.add('warning');
                        }
                    }
                    
                    // Update GPU Utilization
                    if (this.dom.gpuUtilBar) {
                        const gpuUtil = data.gpu_util_percent || 0;
                        this.dom.gpuUtilBar.style.width = `${gpuUtil}%`;
                        this.dom.gpuUtilization.textContent = `${gpuUtil}%`;
                        
                        // Update bar color based on usage
                        this.dom.gpuUtilBar.classList.remove('warning', 'danger');
                        if (gpuUtil > 90) {
                            this.dom.gpuUtilBar.classList.add('danger');
                        } else if (gpuUtil > 70) {
                            this.dom.gpuUtilBar.classList.add('warning');
                        }
                    }
                    
                    // Show GPU cards
                    if (this.dom.gpuResourceCard) {
                        this.dom.gpuResourceCard.style.display = 'flex';
                    }
                    if (this.dom.gpuUtilCard) {
                        this.dom.gpuUtilCard.style.display = 'flex';
                    }
                } else if (type === 'gpu' && !data.available) {
                    // Hide GPU cards if GPU not available
                    if (this.dom.gpuResourceCard) {
                        this.dom.gpuResourceCard.style.display = 'none';
                    }
                    if (this.dom.gpuUtilCard) {
                        this.dom.gpuUtilCard.style.display = 'none';
                    }
                }
            }
        };

        // Theme toggle functionality
        document.addEventListener('DOMContentLoaded', function() {
            const themeToggle = document.getElementById('theme-toggle');
            const themeMenu = document.getElementById('theme-menu');
            const themeOptions = document.querySelectorAll('.theme-option[data-theme]');
            
            // Initialize system monitor
            SystemMonitor.init();
            
            // Add error handlers to all vendor logos
            const vendorLogos = document.querySelectorAll('.vendor-logo');
            vendorLogos.forEach(img => {
                img.onerror = function() {
                    handleImageError(this);
                };
            });
            
            // Load saved theme from localStorage
            const savedTheme = localStorage.getItem('theme') || 'light';
            setTheme(savedTheme);
            
            // Toggle theme menu
            themeToggle.addEventListener('click', function() {
                themeMenu.classList.toggle('show');
            });
            
            // Close menu when clicking outside
            document.addEventListener('click', function(event) {
                if (!themeToggle.contains(event.target) && !themeMenu.contains(event.target)) {
                    themeMenu.classList.remove('show');
                }
            });
            
            // Theme selection
            themeOptions.forEach(option => {
                option.addEventListener('click', function() {
                    const theme = this.getAttribute('data-theme');
                    setTheme(theme);
                    themeMenu.classList.remove('show');
                });
            });
        });
        
        function setTheme(theme) {
            const body = document.body;
            const themeToggle = document.getElementById('theme-toggle');
            const themeOptions = document.querySelectorAll('.theme-option[data-theme]');
            
            // Remove all active classes
            themeOptions.forEach(option => option.classList.remove('active'));
            
            // Add active class to selected theme
            const selectedThemeOption = document.querySelector(`.theme-option[data-theme="${theme}"]`);
            if (selectedThemeOption) {
                selectedThemeOption.classList.add('active');
            }
            
            // Set data-theme attribute
            body.setAttribute('data-theme', theme);
            
            // Update theme toggle icon
            if (themeToggle) {
                themeToggle.textContent = theme === 'dark' ? '🌙' : '☀️';
            }
            
            // Save theme to localStorage
            localStorage.setItem('theme', theme);
        }
        
        const socket = io({
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            reconnectionAttempts: 100,
            timeout: 20000
        });
        console.log('Socket initialized');
        
        let socketReconnectCount = 0;
        let lastHealthCheck = Date.now();
        const HEALTH_CHECK_INTERVAL = 60000;  // 1 minute
        
        // Make socket available globally for system monitor
        window.socket = socket;
        
        socket.on('connect', () => {
            console.log('Socket connected');
            socketReconnectCount = 0;
            // Update system monitor if available
            if (typeof SystemMonitor !== 'undefined') {
                SystemMonitor.updateWebSocketStatus('connected');
            }
        });
        
        socket.on('disconnect', (reason) => {
            console.log('Socket disconnected:', reason);
            stopStreamingTTS();
            isProcessing = false;
            // Update system monitor if available
            if (typeof SystemMonitor !== 'undefined') {
                SystemMonitor.updateWebSocketStatus('disconnected');
            }
        });
        
        socket.on('connect_error', (error) => {
            console.log('Socket connection error:', error);
            socketReconnectCount++;
            if (socketReconnectCount > 5) {
                showToast('warning', 'Connection Issue', 'Reconnecting to server...');
            }
            // Update system monitor if available
            if (typeof SystemMonitor !== 'undefined') {
                SystemMonitor.updateWebSocketStatus('disconnected');
            }
        });
        
        socket.on('reconnect', () => {
            console.log('Socket reconnected');
            // Update system monitor if available
            if (typeof SystemMonitor !== 'undefined') {
                SystemMonitor.updateWebSocketStatus('connected');
            }
        });
        
        async function performHealthCheck() {
            try {
                const response = await fetch('/api/system/health');
                if (response.ok) {
                    const health = await response.json();
                    console.log('System health:', health);
                }
            } catch (error) {
                console.error('Health check failed:', error);
            }
        }
        
        setInterval(() => {
            const now = Date.now();
            if (now - lastHealthCheck > HEALTH_CHECK_INTERVAL) {
                lastHealthCheck = now;
                performHealthCheck();
            }
        }, 30000);
        
        let isProcessing = false;
        let currentRecognition = '';
        let currentTranslation = '';
        let currentPrompt = '';
        let lastRecognizedTexts = [];  // 用于去重的历史记录
        const MAX_HISTORY = 10;  // 保留最近10条记录用于去重
        let translationStyles = { system_presets: [], user_presets: [] };
        let languages = {};
        let currentLanguage = localStorage.getItem('language') || 'zh-CN';

        // TTS variables
        let ttsAudio = null;
        let ttsVoices = {};
        let isTTSPlaying = false;
        let autoPlayTTS = true;
        let ttsMode = 'gsv';
        let selectedVoiceSample = null;
        let voiceCloneAvailable = false;
        let gsvTtsAvailable = false;
        let audioOutputDevices = [];
        let currentDownloadSource = localStorage.getItem('downloadSource') || 'github';
        let currentAudioOutputDevice = '';
        let gsvTtsDownloadProgress = {};
        
        async function loadLanguages() {
            try {
                const response = await fetch('/api/languages');
                if (response.ok) {
                    languages = await response.json();
                    updatePageLanguage(currentLanguage);
                    
                    // Set active state for current language
                    const languageOptions = document.querySelectorAll('.language-option');
                    languageOptions.forEach(option => {
                        if (option.getAttribute('data-language') === currentLanguage) {
                            option.classList.add('active');
                        } else {
                            option.classList.remove('active');
                        }
                    });
                }
            } catch (error) {
                console.error('Error loading languages:', error);
            }
        }

        async function loadTranslationStyles() {
            try {
                const response = await fetch('/api/translation/styles');
                if (response.ok) {
                    translationStyles = await response.json();
                    populateStylePresets();
                }
            } catch (error) {
                console.error('Error loading translation styles:', error);
            }
        }
        
        function populateStylePresets() {
            const select = document.getElementById('translation-style-preset');
            if (!select) return;
            
            // Clear existing options
            select.innerHTML = '<option value="">Select a preset...</option>';
            
            // Add system presets
            if (translationStyles.system_presets) {
                const systemOptgroup = document.createElement('optgroup');
                systemOptgroup.label = 'System Presets';
                translationStyles.system_presets.forEach(preset => {
                    const option = document.createElement('option');
                    option.value = preset.id;
                    option.textContent = preset.name;
                    systemOptgroup.appendChild(option);
                });
                select.appendChild(systemOptgroup);
            }
            
            // Add user presets
            if (translationStyles.user_presets && translationStyles.user_presets.length > 0) {
                const userOptgroup = document.createElement('optgroup');
                userOptgroup.label = 'User Presets';
                translationStyles.user_presets.forEach(preset => {
                    const option = document.createElement('option');
                    option.value = preset.id;
                    option.textContent = preset.name;
                    userOptgroup.appendChild(option);
                });
                select.appendChild(userOptgroup);
            }
        }
        
        async function optimizeTranslationStyle() {
            const input = document.getElementById('translation-style').value.trim();
            if (!input) {
                showToast('warning', 'Input Required', 'Please enter a style or occasion');
                return;
            }
            
            showToast('info', 'Optimizing', 'Optimizing your style input...');
            
            try {
                const response = await fetch('/api/translation/style/optimize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ input: input })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    document.getElementById('translation-style').value = result.optimized_style;
                    showToast('success', 'Optimized', 'Your style input has been optimized');
                } else {
                    const error = await response.json();
                    showToast('error', 'Error', error.error || 'Failed to optimize style');
                }
            } catch (error) {
                console.error('Optimization error:', error);
                showToast('error', 'Error', 'Failed to optimize style');
            }
        }
        
        function editTranslation() {
            const content = document.getElementById('translation-content');
            const currentText = content.textContent.trim();
            
            const textarea = document.createElement('textarea');
            textarea.value = currentText;
            textarea.style.width = '100%';
            textarea.style.minHeight = '100px';
            textarea.style.padding = '12px';
            textarea.style.border = '2px solid var(--primary-color)';
            textarea.style.borderRadius = '8px';
            textarea.style.background = 'var(--input-bg)';
            textarea.style.color = 'var(--text-color)';
            textarea.style.fontSize = '14px';
            textarea.style.resize = 'vertical';
            textarea.style.boxSizing = 'border-box';
            
            const originalContent = content.innerHTML;
            content.innerHTML = '';
            content.appendChild(textarea);
            textarea.focus();
            
            // Add save button
            const saveBtn = document.createElement('button');
            saveBtn.textContent = 'Save';
            saveBtn.style.marginTop = '8px';
            saveBtn.style.padding = '8px 16px';
            saveBtn.style.background = 'var(--primary-color)';
            saveBtn.style.color = 'white';
            saveBtn.style.border = 'none';
            saveBtn.style.borderRadius = '8px';
            saveBtn.style.cursor = 'pointer';
            saveBtn.style.fontSize = '14px';
            
            saveBtn.onclick = function() {
                currentTranslation = textarea.value;
                content.innerHTML = currentTranslation;
                showToast('success', 'Saved', 'Translation edited successfully');
            };
            
            content.appendChild(saveBtn);
        }
        
        function editPrompt() {
            const content = document.getElementById('prompt-content');
            const currentText = content.textContent.trim();
            
            const textarea = document.createElement('textarea');
            textarea.value = currentText;
            textarea.style.width = '100%';
            textarea.style.minHeight = '120px';
            textarea.style.padding = '12px';
            textarea.style.border = '2px solid var(--primary-color)';
            textarea.style.borderRadius = '8px';
            textarea.style.background = 'var(--input-bg)';
            textarea.style.color = 'var(--text-color)';
            textarea.style.fontFamily = 'monospace';
            textarea.style.fontSize = '12px';
            textarea.style.resize = 'vertical';
            textarea.style.boxSizing = 'border-box';
            
            const originalContent = content.innerHTML;
            content.innerHTML = '';
            content.appendChild(textarea);
            textarea.focus();
            
            // Add save button
            const saveBtn = document.createElement('button');
            saveBtn.textContent = 'Save';
            saveBtn.style.marginTop = '8px';
            saveBtn.style.padding = '8px 16px';
            saveBtn.style.background = 'var(--primary-color)';
            saveBtn.style.color = 'white';
            saveBtn.style.border = 'none';
            saveBtn.style.borderRadius = '8px';
            saveBtn.style.cursor = 'pointer';
            saveBtn.style.fontSize = '14px';
            
            saveBtn.onclick = function() {
                currentPrompt = textarea.value;
                content.textContent = currentPrompt;
                showToast('success', 'Saved', 'Prompt edited successfully');
            };
            
            content.appendChild(saveBtn);
        }
        
        function saveAsPreset() {
            const prompt = currentPrompt;
            if (!prompt) {
                showToast('warning', 'No Prompt', 'Please generate a translation first');
                return;
            }
            
            const name = prompt('Enter a name for this preset:');
            if (!name) return;
            
            const description = prompt('Enter a description (optional):');
            
            saveUserPreset(name, description || '', prompt);
        }
        
        async function saveUserPreset(name, description, promptTemplate) {
            try {
                const response = await fetch('/api/translation/preset/save', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: name,
                        description: description,
                        prompt_template: promptTemplate
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    showToast('success', 'Saved', 'Preset saved successfully');
                    loadTranslationStyles(); // Reload presets
                } else {
                    const error = await response.json();
                    showToast('error', 'Error', error.error || 'Failed to save preset');
                }
            } catch (error) {
                console.error('Save preset error:', error);
                showToast('error', 'Error', 'Failed to save preset');
            }
        }
        
        function setDownloadSource(source) {
            currentDownloadSource = source;
            localStorage.setItem('downloadSource', source);
            
            const sourceNames = {
                'github': 'GitHub',
                'ghproxy': 'GHProxy',
                'ghapi': 'GHAPI'
            };
            
            document.querySelectorAll('[id^="download-source-"]').forEach(btn => {
                btn.style.background = 'rgba(255, 255, 255, 0.1)';
                btn.style.color = 'var(--glass-text)';
                btn.style.borderColor = 'rgba(255, 255, 255, 0.2)';
            });
            
            const activeBtn = document.getElementById(`download-source-${source}`);
            if (activeBtn) {
                activeBtn.style.background = 'rgba(59, 130, 246, 0.3)';
                activeBtn.style.color = '#3b82f6';
                activeBtn.style.borderColor = 'rgba(59, 130, 246, 0.5)';
            }
            
            showToast('info', '下载源切换', `已切换到 ${sourceNames[source]}`);
            loadGSVTTSRecommendedModels();
        }
        
        async function downloadGSVTTSModel(modelId, modelName) {
            if (gsvTtsDownloadProgress[modelId]) {
                showToast('warning', 'Download in progress', `${modelName} is already downloading`);
                return;
            }
            
            try {
                showToast('info', 'Starting download', `Starting download of ${modelName}`);
                
                const response = await fetch('/api/gsv-tts/download-model', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model_id: modelId,
                        source: currentDownloadSource
                    })
                });
                
                const result = await response.json();
                
                if (!response.ok) {
                    throw new Error(result.error || 'Failed to start download');
                }
                
                pollDownloadProgress(modelId, modelName);
                
            } catch (error) {
                console.error('Download error:', error);
                showToast('error', 'Download failed', error.message);
            }
        }
        
        async function pollDownloadProgress(modelId, modelName) {
            gsvTtsDownloadProgress[modelId] = {
                status: 'starting',
                progress: 0,
                downloaded: 0,
                total: 0,
                speed: 0
            };
            loadGSVTTSRecommendedModels();
            
            const pollInterval = setInterval(async () => {
                try {
                    const response = await fetch(`/api/gsv-tts/download-progress/${modelId}`);
                    
                    if (response.status === 404) {
                        clearInterval(pollInterval);
                        delete gsvTtsDownloadProgress[modelId];
                        loadGSVTTSRecommendedModels();
                        showToast('success', 'Download complete', `${modelName} downloaded successfully!`);
                        return;
                    }
                    
                    const progress = await response.json();
                    gsvTtsDownloadProgress[modelId] = progress;
                    
                    if (progress.status === 'error') {
                        clearInterval(pollInterval);
                        delete gsvTtsDownloadProgress[modelId];
                        loadGSVTTSRecommendedModels();
                        showToast('error', 'Download failed', progress.error);
                        return;
                    }
                    
                    if (progress.status === 'completed') {
                        clearInterval(pollInterval);
                        delete gsvTtsDownloadProgress[modelId];
                        loadGSVTTSRecommendedModels();
                        showToast('success', 'Download complete', `${modelName} downloaded and extracted successfully!`);
                        return;
                    }
                    
                    loadGSVTTSRecommendedModels();
                    
                } catch (error) {
                    console.error('Progress poll error:', error);
                }
            }, 500);
        }
        
        async function checkGSVTTSModelStatus(modelId) {
            try {
                const response = await fetch(`/api/gsv-tts/model-status/${modelId}`);
                const status = await response.json();
                return status.installed;
            } catch (error) {
                console.error('Status check error:', error);
                return false;
            }
        }
        
        // Streaming TTS variables
        let streamingTTS = false;
        let ttsQueue = [];
        let currentSentenceIndex = 0;
        let accumulatedTranslation = '';
        let lastProcessedLength = 0;
        let ttsProcessing = false;
        let currentStreamingAudio = null;
        let sentenceTimeout = null;
        let preloadedAudio = {};
        let preloadKeys = [];
        const MAX_PRELOADED = 15;  // Increased from 10
        let lastCacheCleanup = Date.now();
        const CACHE_CLEANUP_INTERVAL = 1800000;
        let ttsGenerationQueue = [];  // Queue for parallel TTS generation
        let isGeneratingTTS = false;

        function splitIntoSentences(text) {
            // 主动断句策略：多级标点分割 + 智能处理
            if (!text || text.trim().length === 0) return [];
            
            // 常见英文缩写保护列表
            const abbreviations = [
                'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'st.',
                'ave.', 'blvd.', 'rd.', 'no.', 'vol.', 'vols.', 'inc.',
                'ltd.', 'co.', 'corp.', 'plc.', 'llc.',
                'jan.', 'feb.', 'mar.', 'apr.', 'jun.', 'jul.', 'aug.',
                'sep.', 'oct.', 'nov.', 'dec.',
                'mon.', 'tue.', 'wed.', 'thu.', 'fri.', 'sat.', 'sun.',
                'a.m.', 'p.m.', 'e.g.', 'i.e.', 'etc.', 'vs.',
                'fig.', 'et al.', 'ph.d.', 'b.a.', 'm.a.', 'm.d.',
                'u.s.', 'u.k.', 'u.n.', 'a.d.', 'b.c.'
            ];
            
            // 保护缩写：临时替换缩写中的点
            let protectedText = text;
            const protections = [];
            
            abbreviations.forEach(abbr => {
                const regex = new RegExp(`\\b${abbr.replace(/\./g, '\\.')}`, 'gi');
                protectedText = protectedText.replace(regex, (match) => {
                    const id = `__PROTECT_${protections.length}__`;
                    protections.push(match);
                    return id;
                });
            });
            
            // 保护小数点（数字。数字）
            protectedText = protectedText.replace(/(\d)\.(\d)/g, '$1__DOT__$2');
            
            // 多级分割策略
            const sentences = [];
            
            // 第一级：强结束标点（句号、问号、感叹号）
            const strongEndings = /[.!?。！？]/g;
            let lastIndex = 0;
            let match;
            
            while ((match = strongEndings.exec(protectedText)) !== null) {
                // 检查是否是缩写（已经被保护的跳过）
                if (match[0] === '.' && protectedText.substring(0, match.index).match(/__PROTECT_\d+__$/)) {
                    continue;
                }
                
                const sentence = protectedText.substring(lastIndex, match.index + 1).trim();
                if (sentence.length >= 3) {
                    sentences.push(sentence);
                }
                lastIndex = match.index + 1;
            }
            
            // 处理剩余部分
            const remaining = protectedText.substring(lastIndex).trim();
            if (remaining.length >= 3) {
                // 如果没有强结束标点，按逗号等分割
                if (!/[.!?。！？]$/.test(remaining)) {
                    const subSentences = remaining.split(/[,,;,]/);
                    subSentences.forEach(sub => {
                        if (sub.trim().length >= 3) {
                            sentences.push(sub.trim());
                        }
                    });
                } else {
                    sentences.push(remaining);
                }
            }
            
            // 恢复被保护的字符
            return sentences.map(s => {
                let result = s;
                protections.forEach((orig, i) => {
                    result = result.replace(`__PROTECT_${i}__`, orig);
                });
                return result.replace(/__DOT__/g, '.');
            });
        }

        function cleanupPreloadCache() {
            const now = Date.now();
            if (now - lastCacheCleanup < CACHE_CLEANUP_INTERVAL) {
                return;
            }
            
            lastCacheCleanup = now;
            
            if (preloadKeys.length > MAX_PRELOADED) {
                const keysToRemove = preloadKeys.slice(0, preloadKeys.length - MAX_PRELOADED);
                keysToRemove.forEach(key => {
                    if (preloadedAudio[key]) {
                        delete preloadedAudio[key];
                    }
                });
                preloadKeys = preloadKeys.slice(-MAX_PRELOADED);
            }
        }

        async function preloadTTSAudio(sentence) {
            cleanupPreloadCache();
            
            const cacheKey = sentence.substring(0, 50);
            if (preloadedAudio[cacheKey]) {
                const index = preloadKeys.indexOf(cacheKey);
                if (index !== -1) {
                    preloadKeys.splice(index, 1);
                }
                preloadKeys.push(cacheKey);
                return preloadedAudio[cacheKey];
            }
            
            try {
                const audioBlob = await generateTTSAudio(sentence);
                
                if (preloadKeys.length >= MAX_PRELOADED) {
                    const oldestKey = preloadKeys.shift();
                    if (preloadedAudio[oldestKey]) {
                        delete preloadedAudio[oldestKey];
                    }
                }
                
                preloadedAudio[cacheKey] = audioBlob;
                preloadKeys.push(cacheKey);
                return audioBlob;
            } catch (error) {
                console.error('Preload error:', error);
                return null;
            }
        }

        async function parallelPreloadTTS(sentences) {
            if (!sentences || sentences.length === 0) return;
            
            const promises = sentences.slice(0, 5).map(sentence => {
                const cacheKey = sentence.substring(0, 50);
                if (!preloadedAudio[cacheKey]) {
                    return preloadTTSAudio(sentence);
                }
                return Promise.resolve(preloadedAudio[cacheKey]);
            });
            
            Promise.allSettled(promises);
        }

        async function processStreamingTTS() {
            if (ttsProcessing || ttsQueue.length === 0) return;
            
            ttsProcessing = true;
            const sentence = ttsQueue.shift();
            
            console.log(`Processing TTS for: "${sentence}"`);
            console.log(`Selected voice sample: ${selectedVoiceSample}`);
            
            try {
                updateTTSStatus(`Synthesizing sentence ${currentSentenceIndex + 1}...`, 'processing');
                
                const cacheKey = sentence.substring(0, 50);
                let audioBlob = preloadedAudio[cacheKey];
                
                if (!audioBlob) {
                    audioBlob = await generateTTSAudio(sentence);
                }
                
                console.log(`Received audio blob: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
                
                const audioUrl = URL.createObjectURL(audioBlob);
                console.log(`Created audio URL: ${audioUrl}`);
                
                const audio = new Audio(audioUrl);
                currentStreamingAudio = audio;
                console.log(`Audio element created, duration: ${audio.duration}`);
                
                await setAudioOutputDevice(audio, currentAudioOutputDevice);
                
                audio.onended = () => {
                    console.log('Audio playback ended');
                    URL.revokeObjectURL(audioUrl);
                    currentSentenceIndex++;
                    ttsProcessing = false;
                    currentStreamingAudio = null;
                    
                    if (ttsQueue.length > 0) {
                        processStreamingTTS();
                    } else {
                        updateTTSStatus('Streaming playback finished', 'active');
                        isTTSPlaying = false;
                        document.getElementById('tts-play-btn').classList.remove('playing');
                        document.getElementById('tts-play-btn').disabled = false;
                        document.getElementById('tts-stop-btn').disabled = true;
                    }
                };
                
                audio.onerror = (e) => {
                    console.error('TTS playback error:', e);
                    URL.revokeObjectURL(audioUrl);
                    ttsProcessing = false;
                    currentStreamingAudio = null;
                    showToast('error', 'TTS Error', 'Failed to play audio');
                    processStreamingTTS();
                };
                
                console.log('Starting audio playback...');
                await audio.play();
                console.log('Audio playback started successfully');
                document.getElementById('tts-stop-btn').disabled = false;
                
                if (ttsQueue.length > 0) {
                    parallelPreloadTTS(ttsQueue.slice(0, 4));
                }
                
            } catch (error) {
                console.error('Streaming TTS error:', error);
                showToast('error', 'TTS Error', error.message);
                ttsProcessing = false;
                currentStreamingAudio = null;
                processStreamingTTS();
            }
        }

        async function generateTTSAudio(text) {
            const cacheKey = text.substring(0, 50);
            
            // Check cache first
            if (preloadedAudio[cacheKey]) {
                return preloadedAudio[cacheKey];
            }
            
            const apiUrl = '/api/gsv-tts/generate';
            const referenceText = document.getElementById('gsv-reference-text')?.value?.trim();
            const requestBody = {
                text: text,
                speaker_wav: selectedVoiceSample,
                reference_text: referenceText || undefined
            };
            
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
                signal: AbortSignal.timeout(30000)  // 30s timeout
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to generate GSV-TTS-Lite voice');
            }
            
            const blob = await response.blob();
            
            // Cache the result
            if (preloadKeys.length >= MAX_PRELOADED) {
                const oldestKey = preloadKeys.shift();
                delete preloadedAudio[oldestKey];
            }
            preloadedAudio[cacheKey] = blob;
            preloadKeys.push(cacheKey);
            
            return blob;
        }

        function handleStreamingTranslation(translation) {
            if (!streamingTTS) return;
            
            accumulatedTranslation = translation;
            
            const newContent = translation.substring(lastProcessedLength);
            if (newContent.length < 2) return;
            
            const fullTextToProcess = translation.substring(lastProcessedLength);
            const sentences = splitIntoSentences(fullTextToProcess);
            
            if (sentences.length === 0) {
                if (sentenceTimeout) {
                    clearTimeout(sentenceTimeout);
                }
                sentenceTimeout = setTimeout(() => {
                    if (newContent.length > 4) {
                        ttsQueue.push(newContent.trim());
                        lastProcessedLength = translation.length;
                        
                        if (!isTTSPlaying) {
                            isTTSPlaying = true;
                            document.getElementById('tts-play-btn').classList.add('playing');
                            processStreamingTTS();
                        }
                        
                        // Parallel preload next sentences
                        if (ttsQueue.length > 1) {
                            parallelPreloadTTS(ttsQueue.slice(1, 4));
                        }
                    }
                    sentenceTimeout = null;
                }, 800);  // Reduced from 1200ms
                return;
            }
            
            if (sentenceTimeout) {
                clearTimeout(sentenceTimeout);
                sentenceTimeout = null;
            }
            
            let processedLength = lastProcessedLength;
            
            for (let i = 0; i < sentences.length; i++) {
                const sentence = sentences[i];
                const isLast = i === sentences.length - 1;
                const isComplete = /[。！？.!?]/.test(sentence);
                
                if (isLast && !isComplete) {
                    break;
                }
                
                ttsQueue.push(sentence);
                processedLength += sentence.length;
            }
            
            if (processedLength > lastProcessedLength) {
                lastProcessedLength = processedLength;
                
                if (!isTTSPlaying && ttsQueue.length > 0) {
                    isTTSPlaying = true;
                    document.getElementById('tts-play-btn').classList.add('playing');
                    processStreamingTTS();
                }
                
                // Parallel preload next sentences
                if (ttsQueue.length > 1) {
                    parallelPreloadTTS(ttsQueue.slice(1, 4));
                }
            }
            
            if (sentences.length > 0 && !/[。！？.!?]/.test(sentences[sentences.length - 1])) {
                const remainingText = translation.substring(processedLength);
                if (remainingText.length > 0) {
                    sentenceTimeout = setTimeout(() => {
                        if (translation.substring(lastProcessedLength).length > 4) {
                            ttsQueue.push(remainingText.trim());
                            lastProcessedLength = translation.length;
                            
                            if (!isTTSPlaying) {
                                isTTSPlaying = true;
                                document.getElementById('tts-play-btn').classList.add('playing');
                                processStreamingTTS();
                            }
                            
                            // Parallel preload next sentences
                            if (ttsQueue.length > 1) {
                                parallelPreloadTTS(ttsQueue.slice(1, 4));
                            }
                        }
                        sentenceTimeout = null;
                    }, 800);  // Reduced from 1200ms
                }
            }
        }

        function stopStreamingTTS() {
            streamingTTS = false;
            ttsQueue = [];
            currentSentenceIndex = 0;
            accumulatedTranslation = '';
            lastProcessedLength = 0;
            ttsProcessing = false;
            preloadedAudio = {};
            
            if (sentenceTimeout) {
                clearTimeout(sentenceTimeout);
                sentenceTimeout = null;
            }
            
            if (currentStreamingAudio) {
                currentStreamingAudio.pause();
                currentStreamingAudio.currentTime = 0;
                currentStreamingAudio = null;
            }
            
            if (ttsAudio) {
                ttsAudio.pause();
                ttsAudio.currentTime = 0;
                ttsAudio = null;
            }
            
            isTTSPlaying = false;
            document.getElementById('tts-play-btn').classList.remove('playing');
            document.getElementById('tts-play-btn').disabled = false;
            document.getElementById('tts-stop-btn').disabled = true;
            updateTTSStatus('', 'idle');
        }

        async function enumerateAudioOutputDevices() {
            try {
                if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
                    console.warn('enumerateDevices not supported');
                    return;
                }
                
                const devices = await navigator.mediaDevices.enumerateDevices();
                audioOutputDevices = devices.filter(device => device.kind === 'audiooutput');
                
                const select = document.getElementById('audio-output-select');
                select.innerHTML = '<option value="">Default Device</option>';
                
                audioOutputDevices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.textContent = device.label || `Speaker ${audioOutputDevices.indexOf(device) + 1}`;
                    select.appendChild(option);
                });
                
                select.addEventListener('change', function() {
                    currentAudioOutputDevice = this.value;
                    if (ttsAudio && ttsAudio.setSinkId) {
                        ttsAudio.setSinkId(currentAudioOutputDevice || 'default')
                            .then(() => console.log('Audio output device changed'))
                            .catch(err => console.error('Failed to change audio output:', err));
                    }
                });
                
            } catch (error) {
                console.error('Failed to enumerate audio devices:', error);
            }
        }

        async function setAudioOutputDevice(audioElement, deviceId) {
            if (!audioElement || !audioElement.setSinkId) {
                return;
            }
            
            try {
                await audioElement.setSinkId(deviceId || 'default');
                console.log('Audio output set to:', deviceId || 'default');
            } catch (error) {
                console.error('Failed to set audio output device:', error);
            }
        }

        function setTTSMode(mode) {
            ttsMode = mode;
            document.getElementById('tts-mode-gsv').classList.toggle('active', mode === 'gsv');
            document.getElementById('voice-clone-panel').style.display = 'block';
            
            const badge = document.getElementById('current-engine-badge');
            const desc = document.getElementById('current-engine-desc');
            const langHint = document.getElementById('tts-language-hint');
            const langSelect = document.getElementById('tts-language-select');
            const voiceSelect = document.getElementById('tts-voice-select');
            const voiceSelectLabel = document.querySelector('label[for="tts-voice-select"]');
            
            badge.className = 'tts-engine-badge';
            
            badge.classList.add('gsv');
            badge.textContent = 'GSV-TTS-Lite';
            desc.textContent = 'High-performance inference engine for GPT-SoVITS';
            langHint.style.display = 'block';
            langSelect.disabled = true;
            
            // Hide preset TTS voice select for GSV-TTS-Lite
            if (voiceSelect) {
                voiceSelect.style.display = 'none';
            }
            if (voiceSelectLabel) {
                voiceSelectLabel.style.display = 'none';
            }
            
            loadVoiceSamples();
        }

        async function checkVoiceCloneAvailability() {
            try {
                const response = await fetch('/api/tts/status');
                const data = await response.json();
                gsvTtsAvailable = data.gsv_tts_available;
                
                if (!gsvTtsAvailable) {
                    document.getElementById('tts-mode-gsv').title = 'GSV-TTS-Lite not available. Install gsv-tts-lite: pip install gsv-tts-lite==0.3.5';
                    document.getElementById('tts-mode-gsv').style.opacity = '0.5';
                }
            } catch (error) {
                console.error('Failed to check voice clone availability:', error);
            }
        }

        async function loadVoiceSamples() {
            try {
                const response = await fetch('/api/voice-clone/list');
                const data = await response.json();
                
                const listEl = document.getElementById('voice-samples-list');
                
                if (!data.success || data.samples.length === 0) {
                    listEl.innerHTML = '<div class="no-samples">No voice samples uploaded yet</div>';
                    return;
                }
                
                // Auto-select first sample if none selected
                if (!selectedVoiceSample && data.samples.length > 0) {
                    selectedVoiceSample = data.samples[0].filename;
                    document.getElementById('selected-voice-info').style.display = 'block';
                    document.getElementById('selected-voice-name').textContent = selectedVoiceSample;
                    console.log('Auto-selected voice sample:', selectedVoiceSample);
                }
                
                listEl.innerHTML = data.samples.map(sample => `
                    <div class="voice-sample-item ${selectedVoiceSample === sample.filename ? 'selected' : ''}" 
                         onclick="selectVoiceSample('${sample.filename}')">
                        <div class="voice-sample-info">
                            <div class="voice-sample-name">${sample.filename}</div>
                            <div class="voice-sample-meta">${formatFileSize(sample.size)} • ${formatDate(sample.created)}</div>
                        </div>
                        <div class="voice-sample-actions">
                            <button class="voice-sample-btn play" onclick="event.stopPropagation(); playVoiceSample('${sample.filename}')">▶</button>
                            <button class="voice-sample-btn delete" onclick="event.stopPropagation(); deleteVoiceSample('${sample.filename}')">✕</button>
                        </div>
                    </div>
                `).join('');
                
            } catch (error) {
                console.error('Failed to load voice samples:', error);
            }
        }

        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function formatDate(isoString) {
            const date = new Date(isoString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }

        function selectVoiceSample(filename) {
            selectedVoiceSample = filename;
            loadVoiceSamples();
            
            document.getElementById('selected-voice-info').style.display = 'block';
            document.getElementById('selected-voice-name').textContent = filename;
        }

        function playVoiceSample(filename) {
            const audio = new Audio(`/voice_samples/${filename}`);
            audio.play();
        }

        async function deleteVoiceSample(filename) {
            if (!confirm(`Delete voice sample "${filename}"?`)) return;
            
            try {
                const response = await fetch(`/api/voice-clone/delete/${encodeURIComponent(filename)}`, {
                    method: 'DELETE'
                });
                const data = await response.json();
                
                if (data.success) {
                    showToast('success', 'Deleted', 'Voice sample deleted');
                    if (selectedVoiceSample === filename) {
                        selectedVoiceSample = null;
                        document.getElementById('selected-voice-info').style.display = 'none';
                    }
                    loadVoiceSamples();
                } else {
                    showToast('error', 'Error', data.error);
                }
            } catch (error) {
                showToast('error', 'Error', 'Failed to delete voice sample');
            }
        }

        async function handleVoiceUpload(file) {
            if (!file) return;
            
            const validExtensions = ['.wav', '.mp3', '.ogg', '.flac', '.m4a'];
            const fileExt = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!validExtensions.includes(fileExt)) {
                showToast('error', 'Invalid File', 'Please upload a valid audio file');
                return;
            }
            
            if (file.size > 10 * 1024 * 1024) {
                showToast('error', 'File Too Large', 'Maximum file size is 10MB');
                return;
            }
            
            const formData = new FormData();
            formData.append('audio', file);
            
            try {
                showToast('info', 'Uploading', 'Uploading voice sample...');
                
                const response = await fetch('/api/voice-clone/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showToast('success', 'Uploaded', 'Voice sample uploaded successfully');
                    selectVoiceSample(data.filename);
                    loadVoiceSamples();
                } else {
                    showToast('error', 'Upload Failed', data.error);
                }
            } catch (error) {
                showToast('error', 'Upload Failed', 'Failed to upload voice sample');
            }
            
            document.getElementById('voice-file-input').value = '';
        }

        const uploadArea = document.getElementById('voice-upload-area');
        if (uploadArea) {
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
            
            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });
            
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const file = e.dataTransfer.files[0];
                handleVoiceUpload(file);
            });
        }

        // TTS functions
        async function loadTTSVoices() {
            try {
                const response = await fetch('/api/tts/voices');
                const data = await response.json();
                
                if (!data.available) {
                    document.getElementById('tts-voice-select').innerHTML = '<option value="">TTS not available</option>';
                    document.getElementById('tts-play-btn').disabled = true;
                    return;
                }
                
                ttsVoices = data.voices;
                updateTTSVoiceSelect('english');
            } catch (error) {
                console.error('Failed to load TTS voices:', error);
                document.getElementById('tts-voice-select').innerHTML = '<option value="">Failed to load</option>';
            }
        }

        function updateTTSVoiceSelect(language) {
            const select = document.getElementById('tts-voice-select');
            const voices = ttsVoices[language] || [];
            
            select.innerHTML = '';
            
            if (voices.length === 0) {
                select.innerHTML = '<option value="">No voices available</option>';
                return;
            }
            
            voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.id;
                option.textContent = `${voice.name} (${voice.gender})`;
                select.appendChild(option);
            });
        }

        document.getElementById('tts-language-select').addEventListener('change', function() {
            updateTTSVoiceSelect(this.value);
        });

        document.getElementById('tts-rate').addEventListener('input', function() {
            const value = parseInt(this.value);
            const sign = value >= 0 ? '+' : '';
            document.getElementById('tts-rate-value').textContent = `${sign}${value}%`;
        });

        async function playTTS(text = null) {
            const textToPlay = text || currentTranslation.trim();
            
            if (!textToPlay) {
                showToast('warning', 'No Text', 'No translation to play');
                return;
            }
            
            if (streamingTTS) {
                stopStreamingTTS();
                return;
            }
            
            await playClonedVoice(textToPlay);
        }

        async function playPresetVoice(textToPlay) {
            const voice = document.getElementById('tts-voice-select').value;
            if (!voice) {
                showToast('warning', 'No Voice', 'Please select a TTS voice');
                return;
            }
            
            const rateValue = parseInt(document.getElementById('tts-rate').value);
            const rate = `${rateValue >= 0 ? '+' : ''}${rateValue}%`;
            const autoPlay = document.getElementById('auto-play-tts').checked;
            
            try {
                stopTTS();
                
                updateTTSStatus('Generating audio...', 'processing');
                document.getElementById('tts-play-btn').disabled = true;
                
                const response = await fetch('/api/tts/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        text: textToPlay,
                        voice: voice,
                        rate: rate
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to generate TTS');
                }
                
                const blob = await response.blob();
                const audioUrl = URL.createObjectURL(blob);
                
                ttsAudio = new Audio(audioUrl);
                isTTSPlaying = true;
                
                await setAudioOutputDevice(ttsAudio, currentAudioOutputDevice);
                
                ttsAudio.onended = () => {
                    isTTSPlaying = false;
                    document.getElementById('tts-play-btn').classList.remove('playing');
                    document.getElementById('tts-play-btn').disabled = false;
                    document.getElementById('tts-stop-btn').disabled = true;
                    updateTTSStatus('Playback finished', 'active');
                    URL.revokeObjectURL(audioUrl);
                };
                
                ttsAudio.onerror = (e) => {
                    isTTSPlaying = false;
                    document.getElementById('tts-play-btn').classList.remove('playing');
                    document.getElementById('tts-play-btn').disabled = false;
                    updateTTSStatus('Playback error', 'error');
                    showToast('error', 'TTS Error', 'Failed to play audio');
                };
                
                if (autoPlay) {
                    document.getElementById('tts-play-btn').classList.add('playing');
                    await ttsAudio.play();
                    document.getElementById('tts-stop-btn').disabled = false;
                    updateTTSStatus('Playing...', 'active');
                    showToast('success', 'TTS', 'Playing translation');
                } else {
                    document.getElementById('tts-play-btn').disabled = false;
                    updateTTSStatus('Ready to play (click Play button)', 'idle');
                    showToast('info', 'TTS Ready', 'Audio generated. Click Play to start.');
                }
                
            } catch (error) {
                console.error('TTS Error:', error);
                document.getElementById('tts-play-btn').classList.remove('playing');
                document.getElementById('tts-play-btn').disabled = false;
                document.getElementById('tts-status').textContent = 'Error: ' + error.message;
                showToast('error', 'TTS Error', error.message);
            }
        }

        async function playClonedVoice(textToPlay) {
            if (!selectedVoiceSample) {
                showToast('warning', 'No Voice Sample', 'Please upload and select a voice sample first');
                return;
            }
            
            if (!gsvTtsAvailable) {
                showToast('error', 'Not Available', 'GSV-TTS-Lite is not available. Please install gsv-tts-lite: pip install gsv-tts-lite==0.3.5');
                return;
            }
            
            const autoPlay = document.getElementById('auto-play-tts').checked;
            
            try {
                stopTTS();
                
                const engineName = 'GSV-TTS-Lite';
                updateTTSStatus(`Generating ${engineName} voice (this may take a while)...`, 'processing');
                document.getElementById('tts-play-btn').disabled = true;
                
                const apiUrl = '/api/gsv-tts/generate';
                const referenceText = document.getElementById('gsv-reference-text')?.value?.trim();
                const requestBody = {
                    text: textToPlay,
                    speaker_wav: selectedVoiceSample,
                    reference_text: referenceText || undefined
                };
                
                const response = await fetch(apiUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestBody)
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to generate cloned voice');
                }
                
                const blob = await response.blob();
                const audioUrl = URL.createObjectURL(blob);
                
                ttsAudio = new Audio(audioUrl);
                isTTSPlaying = true;
                
                await setAudioOutputDevice(ttsAudio, currentAudioOutputDevice);
                
                ttsAudio.onended = () => {
                    isTTSPlaying = false;
                    document.getElementById('tts-play-btn').classList.remove('playing');
                    document.getElementById('tts-play-btn').disabled = false;
                    document.getElementById('tts-stop-btn').disabled = true;
                    updateTTSStatus('Playback finished', 'active');
                    URL.revokeObjectURL(audioUrl);
                };
                
                ttsAudio.onerror = (e) => {
                    isTTSPlaying = false;
                    document.getElementById('tts-play-btn').classList.remove('playing');
                    document.getElementById('tts-play-btn').disabled = false;
                    updateTTSStatus('Playback error', 'error');
                    showToast('error', 'TTS Error', 'Failed to play audio');
                };
                
                if (autoPlay) {
                    document.getElementById('tts-play-btn').classList.add('playing');
                    await ttsAudio.play();
                    document.getElementById('tts-stop-btn').disabled = false;
                    updateTTSStatus(`Playing ${engineName} voice...`, 'active');
                    showToast('success', 'Voice Clone', `Playing with ${engineName}`);
                } else {
                    document.getElementById('tts-play-btn').disabled = false;
                    updateTTSStatus('Ready to play (click Play button)', 'idle');
                    showToast('info', 'Voice Clone Ready', 'Audio generated. Click Play to start.');
                }
                
            } catch (error) {
                console.error('Voice Clone Error:', error);
                document.getElementById('tts-play-btn').classList.remove('playing');
                document.getElementById('tts-play-btn').disabled = false;
                updateTTSStatus('Error: ' + error.message, 'error');
                showToast('error', 'Voice Clone Error', error.message);
            }
        }

        function updateTTSStatus(text, state = 'idle') {
            const indicator = document.getElementById('tts-status-indicator');
            const statusText = document.getElementById('tts-status-text');
            
            statusText.textContent = text;
            
            indicator.className = 'tts-status-indicator';
            if (state !== 'idle') {
                indicator.classList.add(state);
            }
        }

        function stopTTS() {
            if (streamingTTS) {
                stopStreamingTTS();
                return;
            }
            
            if (currentStreamingAudio) {
                currentStreamingAudio.pause();
                currentStreamingAudio.currentTime = 0;
                currentStreamingAudio = null;
            }
            
            if (ttsAudio) {
                ttsAudio.pause();
                ttsAudio.currentTime = 0;
                ttsAudio = null;
            }
            
            if (sentenceTimeout) {
                clearTimeout(sentenceTimeout);
                sentenceTimeout = null;
            }
            
            isTTSPlaying = false;
            document.getElementById('tts-play-btn').classList.remove('playing');
            document.getElementById('tts-play-btn').disabled = false;
            document.getElementById('tts-stop-btn').disabled = true;
            updateTTSStatus('', 'idle');
        }

        // Toast notification system
        function showToast(type, title, message, duration = 3000) {
            const container = document.getElementById('toast-container');
            if (!container) return;

            // Create toast element
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            
            // Get icon based on type
            const icons = {
                success: '✓',
                error: '✗',
                warning: '⚠',
                info: 'ℹ'
            };

            toast.innerHTML = `
                <div class="toast-icon">${icons[type] || icons.info}</div>
                <div class="toast-content">
                    <div class="toast-title">${title}</div>
                    <div class="toast-message">${message}</div>
                </div>
                <button class="toast-close" onclick="removeToast(this.parentElement)">×</button>
            `;

            // Add click to remove
            toast.addEventListener('click', function() {
                removeToast(this);
            });

            // Add to container
            container.appendChild(toast);

            // Auto remove after duration
            setTimeout(() => {
                if (toast.parentElement) {
                    removeToast(toast);
                }
            }, duration);
        }

        function removeToast(toast) {
            if (!toast) return;

            // Add removing class to start fade out animation
            toast.classList.add('removing');

            // Animate height to 0 and collapse
            toast.style.height = toast.offsetHeight + 'px';
            toast.style.overflow = 'hidden';
            toast.style.marginBottom = '0';
            toast.style.marginTop = '0';
            toast.style.paddingTop = '0';
            toast.style.paddingBottom = '0';

            // Force reflow
            toast.offsetHeight;

            // Start animation
            toast.style.height = '0';
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';

            // Wait for animation to complete
            setTimeout(() => {
                if (toast.parentElement) {
                    toast.parentElement.removeChild(toast);
                }
            }, 500);
        }

        function updatePageLanguage(lang) {
            if (!languages[lang] || !languages[lang].app) return;
            
            const langData = languages[lang].app;
            
            // Update app title and subtitle - keep Vox Engine as title
            const headerH1 = document.getElementById('app-title');
            if (headerH1) headerH1.textContent = 'Vox Engine';
            const headerP = document.getElementById('app-subtitle');
            if (headerP) headerP.textContent = langData.subtitle || 'Intelligent Speech Processing • Real-time Translation • AI-Powered';
            
            // Update navigation
            const navRecognition = document.querySelector('#nav-recognition .nav-text');
            if (navRecognition) navRecognition.textContent = langData.nav?.recognition || 'Recognition';
            const navModels = document.querySelector('#nav-models .nav-text');
            if (navModels) navModels.textContent = langData.nav?.models || 'Model Manager';
            
            // Update input configuration
            const micLabel = document.querySelector('label[for="microphone-select"]');
            if (micLabel) micLabel.textContent = langData.input?.microphone || 'Microphone';
            const speechModelLabel = document.querySelector('label[for="vosk-model-select"]');
            if (speechModelLabel) speechModelLabel.textContent = langData.input?.speechModel || 'Speech Model';
            
            // Update translation configuration
            const providerLabel = document.querySelector('label[for="translation-provider"]');
            if (providerLabel) providerLabel.textContent = langData.translation?.provider || 'Provider';
            const modelLabel = document.querySelector('label[for="model-select"]');
            if (modelLabel) modelLabel.textContent = langData.translation?.model || 'Translation Model';
            const stylePresetLabel = document.querySelector('label[for="translation-style-preset"]');
            if (stylePresetLabel) stylePresetLabel.textContent = langData.translation?.stylePreset || 'Style Preset';
            const customStyleLabel = document.querySelector('label[for="translation-style"]');
            if (customStyleLabel) customStyleLabel.textContent = langData.translation?.customStyle || 'Custom Style';
            const optimizeBtn = document.querySelector('#optimize-style-btn');
            if (optimizeBtn) optimizeBtn.textContent = langData.translation?.optimize || 'Optimize';
            const controlHints = document.querySelectorAll('.control-hint');
            controlHints.forEach((hint, index) => {
                if (index === 0 && langData.translation?.hint) {
                    hint.textContent = langData.translation.hint;
                }
            });
            
            // Update TTS configuration
            const voiceLabel = document.querySelector('label[for="tts-voice-select"]');
            if (voiceLabel) voiceLabel.textContent = langData.tts?.voice || 'Voice (Speaker)';
            const langLabel = document.querySelector('label[for="tts-language-select"]');
            if (langLabel) langLabel.textContent = langData.tts?.language || 'Language';
            const rateLabel = document.querySelector('.tts-rate-control');
            if (rateLabel && rateLabel.previousElementSibling) {
                rateLabel.previousElementSibling.textContent = langData.tts?.rate || 'Speech Rate';
            }
            
            // Update buttons
            const startBtn = document.querySelector('#start-btn');
            if (startBtn) startBtn.innerHTML = `<span><i class="fas fa-microphone"></i></span> ${langData.buttons?.start || 'Start Recognition'}`;
            const stopBtn = document.querySelector('#stop-btn');
            if (stopBtn) stopBtn.innerHTML = `<span><i class="fas fa-stop"></i></span> ${langData.buttons?.stop || 'Stop'}`;
            const ttsPlayBtn = document.querySelector('#tts-play-btn');
            if (ttsPlayBtn) ttsPlayBtn.innerHTML = `<span><i class="fas fa-volume-up"></i></span> ${langData.buttons?.play || 'Play Translation'}`;
            const ttsStopBtn = document.querySelector('#tts-stop-btn');
            if (ttsStopBtn) ttsStopBtn.innerHTML = `<span><i class="fas fa-stop"></i></span> ${langData.buttons?.stop || 'Stop'}`;
            const editTranslationBtn = document.querySelector('#edit-translation-btn');
            if (editTranslationBtn) editTranslationBtn.innerHTML = `<span><i class="fas fa-edit"></i></span> ${langData.buttons?.edit || 'Edit'}`;
            const copyPromptBtn = document.querySelector('#copy-prompt-btn');
            if (copyPromptBtn) copyPromptBtn.innerHTML = `<span><i class="fas fa-copy"></i></span> ${langData.buttons?.copy || 'Copy Prompt'}`;
            const editPromptBtn = document.querySelector('#edit-prompt-btn');
            if (editPromptBtn) editPromptBtn.innerHTML = `<span><i class="fas fa-edit"></i></span> ${langData.buttons?.edit || 'Edit Prompt'}`;
            const savePresetBtn = document.querySelector('#save-preset-btn');
            if (savePresetBtn) savePresetBtn.innerHTML = `<span><i class="fas fa-save"></i></span> ${langData.buttons?.savePreset || 'Save as Preset'}`;
            
            // Update results
            const resultCards = document.querySelectorAll('.result-card h2');
            if (resultCards[0]) resultCards[0].textContent = langData.results?.recognition || 'Speech Recognition Results';
            if (resultCards[1]) resultCards[1].textContent = langData.results?.translation || 'Translation Results';
            if (resultCards[2]) resultCards[2].textContent = langData.results?.prompt || 'Optimized Prompt';
            
            // Update status
            const statusText = document.querySelector('.status-text');
            if (statusText) statusText.textContent = langData.status?.ready || 'System ready, please select microphone and model to start';
            
            // Update stats
            const statLabels = document.querySelectorAll('.stat-label');
            if (statLabels[0]) statLabels[0].textContent = langData.results?.time || 'Total Time';
            if (statLabels[1]) statLabels[1].textContent = langData.results?.segments || 'Segments';
            if (statLabels[2]) statLabels[2].textContent = langData.results?.time || 'Translation Time';
            if (statLabels[3]) statLabels[3].textContent = langData.results?.chars || 'Characters';
            
            // Update auto-play toggle
            const autoPlayToggles = document.querySelectorAll('.auto-play-toggle span');
            if (autoPlayToggles[0]) autoPlayToggles[0].textContent = langData.tts?.autoPlay || 'Auto-play after synthesis';
            if (autoPlayToggles[1]) autoPlayToggles[1].textContent = langData.tts?.streaming || 'Streaming TTS (sentence-by-sentence)';
            
            // Update voice cloning section
            const voiceCloneH3 = document.querySelector('.voice-clone-section h3');
            if (voiceCloneH3) voiceCloneH3.innerHTML = `<span><i class="fas fa-microphone-alt"></i></span> ${langData.voiceClone?.title || 'Voice Cloning (Custom Speaker)'}`;
            
            // Update audio output section
            const audioOutputLabel = document.querySelector('label[for="audio-output-select"]');
            if (audioOutputLabel) audioOutputLabel.innerHTML = `<i class="fas fa-headphones"></i> ${langData.tts?.outputDevice || 'Output Device:'}`;
            
            // Update FRP management section
            const navFrp = document.querySelector('#nav-frp .nav-text');
            if (navFrp) navFrp.textContent = langData.nav?.frp || 'FRP Management';
            
            // Update FRP page header
            const frpPageTitle = document.getElementById('frp-page-title');
            if (frpPageTitle) frpPageTitle.innerHTML = `<span class="header-icon"><i class="fas fa-network-wired"></i></span> ${langData.frp?.title || 'FRP Management'}`;
            
            const frpPageSubtitle = document.getElementById('frp-page-subtitle');
            if (frpPageSubtitle) frpPageSubtitle.textContent = langData.frp?.description || 'Manage mefrp tunnels for remote access';
            
            const frpGuideText = document.getElementById('frp-guide-text');
            if (frpGuideText) {
                const guideText = langData.frp?.guide || '1. Register at www.mefrp.com 2. Create a tunnel 3. Copy the start command 4. Paste it below and save';
                frpGuideText.innerHTML = `<strong>${currentLanguage === 'zh-CN' ? '使用说明：' : 'How to use:'}</strong> 1. <a href="https://www.mefrp.com" target="_blank">www.mefrp.com</a> ${guideText}`;
            }
            
            // Update Add Tunnel card
            const addTunnelTitle = document.getElementById('add-tunnel-title');
            if (addTunnelTitle) addTunnelTitle.textContent = langData.frp?.addTunnel || 'Add New Tunnel';
            
            const tunnelNameLabel = document.getElementById('tunnel-name-label');
            if (tunnelNameLabel) tunnelNameLabel.textContent = langData.frp?.tunnelName || 'Tunnel Name';
            
            const tunnelNameInput = document.getElementById('tunnel-name');
            if (tunnelNameInput) tunnelNameInput.placeholder = langData.frp?.tunnelNamePlaceholder || 'Enter a name for your tunnel';
            
            const tunnelCommandLabel = document.getElementById('tunnel-command-label');
            if (tunnelCommandLabel) tunnelCommandLabel.textContent = langData.frp?.startCommand || 'Start Command';
            
            const tunnelCommandInput = document.getElementById('tunnel-command');
            if (tunnelCommandInput) tunnelCommandInput.placeholder = langData.frp?.startCommandPlaceholder || 'Paste the mefrpc start command here';
            
            const saveTunnelBtn = document.getElementById('save-tunnel-btn');
            if (saveTunnelBtn) saveTunnelBtn.innerHTML = `<span><i class="fas fa-save"></i></span> ${langData.frp?.saveTunnel || 'Save Tunnel'}`;
            
            // Update Saved Tunnels card
            const savedTunnelsTitle = document.getElementById('saved-tunnels-title');
            if (savedTunnelsTitle) savedTunnelsTitle.textContent = langData.frp?.savedTunnels || 'Saved Tunnels';
            
            const loadingTunnels = document.getElementById('loading-tunnels-text');
            if (loadingTunnels) loadingTunnels.textContent = langData.frp?.loadingTunnels || 'Loading tunnels...';
            
            // Update Tunnel Output card
            const tunnelOutputTitle = document.getElementById('tunnel-output-title');
            if (tunnelOutputTitle) tunnelOutputTitle.textContent = langData.frp?.tunnelOutput || 'Tunnel Output';
            
            const outputPlaceholder = document.getElementById('output-placeholder-text');
            if (outputPlaceholder) outputPlaceholder.textContent = langData.frp?.outputPlaceholder || 'Tunnel output will appear here...';
            
            // Update Loaded Models section
            const loadedModelsTitle = document.getElementById('loaded-models-title');
            if (loadedModelsTitle) loadedModelsTitle.textContent = langData.models?.loadedModels || 'Loaded Models';
            
            const unloadAllText = document.getElementById('unload-all-text');
            if (unloadAllText) unloadAllText.textContent = langData.models?.unloadAllModels || 'Unload All Models';
            
            const memoryInfoTitle = document.getElementById('memory-info-title');
            if (memoryInfoTitle) memoryInfoTitle.textContent = langData.models?.memoryInfo || 'Memory Information';
            
            const gpuModelsLabel = document.getElementById('gpu-models-label');
            if (gpuModelsLabel) gpuModelsLabel.textContent = langData.models?.gpuModels || 'GPU Models:';
            
            const gpuModelsDesc = document.getElementById('gpu-models-desc');
            if (gpuModelsDesc) gpuModelsDesc.textContent = langData.models?.gpuModelsDesc || 'Models loaded in GPU (faster, uses VRAM)';
            
            const cpuModelsLabel = document.getElementById('cpu-models-label');
            if (cpuModelsLabel) cpuModelsLabel.textContent = langData.models?.cpuModels || 'CPU Models:';
            
            const cpuModelsDesc = document.getElementById('cpu-models-desc');
            if (cpuModelsDesc) cpuModelsDesc.textContent = langData.models?.cpuModelsDesc || 'Models loaded in CPU (slower, uses RAM)';
            
            const tipLabel = document.getElementById('tip-label');
            if (tipLabel) tipLabel.textContent = langData.models?.tip || 'Tip:';
            
            const tipDesc = document.getElementById('tip-desc');
            if (tipDesc) tipDesc.textContent = langData.models?.tipDesc || 'Unloading unused models frees up memory for other tasks.';
            
            // Update Model Tabs
            const tabVoskText = document.getElementById('tab-vosk-text');
            if (tabVoskText) tabVoskText.textContent = langData.models?.voskModels || 'Vosk Models';
            
            const tabVllmText = document.getElementById('tab-vllm-text');
            if (tabVllmText) tabVllmText.textContent = langData.models?.vllmModels || 'vLLM Models';
            
            const tabGsvTtsText = document.getElementById('tab-gsv-tts-text');
            if (tabGsvTtsText) tabGsvTtsText.textContent = langData.models?.gsvTtsModels || 'GSV-TTS-Lite';
            
            const tabLoadedText = document.getElementById('tab-loaded-text');
            if (tabLoadedText) tabLoadedText.textContent = langData.models?.loadedModels || 'Loaded Models';
            
            // Update vLLM Card
            const vllmCardTitle = document.getElementById('vllm-card-title');
            if (vllmCardTitle) vllmCardTitle.textContent = langData.models?.vllmTranslationModels || 'vLLM Translation Models';
            
            const vllmCardSubtitle = document.getElementById('vllm-card-subtitle');
            if (vllmCardSubtitle) vllmCardSubtitle.textContent = langData.models?.largeLanguageModels || 'Large Language Models';
            
            const vllmStatusText = document.getElementById('vllm-status-text');
            if (vllmStatusText) vllmStatusText.textContent = langData.models?.ready || 'Ready';
        }

        function initLanguageSelector() {
            const languageSelector = document.querySelector('.theme-selector');
            const languageToggle = document.getElementById('language-toggle');
            const languageMenu = document.getElementById('language-menu');

            if (languageToggle && languageMenu) {
                languageToggle.addEventListener('click', function(e) {
                    e.stopPropagation();
                    languageMenu.classList.toggle('show');
                });

                // Close menu when clicking outside
                document.addEventListener('click', function(e) {
                    if (languageSelector && !languageSelector.contains(e.target)) {
                        languageMenu.classList.remove('show');
                    }
                });
            }

            // Add click event listeners to language options
            const languageOptions = document.querySelectorAll('[data-language]');
            languageOptions.forEach(option => {
                option.addEventListener('click', function() {
                    const language = this.getAttribute('data-language');
                    setLanguage(language, true);
                    if (languageMenu) {
                        languageMenu.classList.remove('show');
                    }
                });
            });
        }

        function setLanguage(language, showNotification = false) {
            currentLanguage = language;
            localStorage.setItem('language', language);
            updatePageLanguage(language);

            // Update active state of language options
            const languageOptions = document.querySelectorAll('.language-option');
            languageOptions.forEach(option => {
                if (option.getAttribute('data-language') === language) {
                    option.classList.add('active');
                } else {
                    option.classList.remove('active');
                }
            });

            if (showNotification) {
                const languageNames = {
                    'zh-CN': '中文',
                    'en-US': 'English'
                };
                showToast('info', 'Language Changed', `Switched to ${languageNames[language] || language} language`);
            }
        }

        // Initialize theme selector when DOM is loaded

                document.addEventListener('DOMContentLoaded', () => {

                    console.log('DOMContentLoaded event fired');

                    initLanguageSelector();

                    // Check canvas element on page load

                    const canvas = document.getElementById('audio-waveform');

                    console.log('Page load canvas check:', canvas);

                    if (canvas) {

                        console.log('Canvas is ready:', canvas.width, 'x', canvas.height);

                    }

                    // Test button functionality

                    const testBtn = document.getElementById('start-btn');

                    if (testBtn) {

                        console.log('Start button found');

                    } else {

                        console.error('Start button not found!');

                    }

                    // Initialize download source button style
                    setTimeout(() => {
                        setDownloadSource(currentDownloadSource);
                    }, 100);

                    // Load all dropdown options after DOM is ready

                    loadAllOptions();

                });

                function loadAllOptions() {

                    console.log('Starting to load all dropdown options...');

                    // Initialize TTS mode to GSV-TTS-Lite
                    setTTSMode('gsv');

                    // Load languages
                    console.log('Loading languages...');
                    loadLanguages();

                    // Load microphone list

                    console.log('Loading microphones...');

                    fetch('/api/microphones')

                        .then(response => {

                            console.log('Microphone API response status:', response.status);

                            if (!response.ok) {

                                throw new Error(`HTTP error! status: ${response.status}`);

                            }

                            return response.json();

                        })

                        .then(microphones => {

                            console.log('Microphones loaded:', microphones);

                            const select = document.getElementById('microphone-select');

                            if (!select) {

                                console.error('Microphone select element not found');

                                return;

                            }

                            select.innerHTML = '';

                            if (microphones.length === 0) {

                                const option = document.createElement('option');

                                option.value = '';

                                option.textContent = 'No microphones found';

                                select.appendChild(option);

                                showToast('warning', 'No Microphones', 'No microphone devices detected');

                            } else {

                                microphones.forEach((mic, index) => {

                                    const option = document.createElement('option');

                                    option.value = mic.index;

                                    option.textContent = mic.name;

                                    select.appendChild(option);

                                });

                                showToast('success', 'Microphones Loaded', `Found ${microphones.length} microphone devices`);

                            }

                        })

                        .catch(error => {

                            console.error('Failed to load microphones:', error);

                            const select = document.getElementById('microphone-select');

                            if (select) {

                                select.innerHTML = '<option value="">Failed to load</option>';

                            }

                            showToast('error', 'Error', `Failed to load microphones: ${error.message}`, 5000);

                        });

                    // Load Vosk model list

                    console.log('Loading Vosk models...');

                    fetch('/api/vosk-models')

                        .then(response => {

                            console.log('Vosk models API response status:', response.status);

                            if (!response.ok) {

                                throw new Error(`HTTP error! status: ${response.status}`);

                            }

                            return response.json();

                        })

                        .then(models => {

                            console.log('Vosk models loaded:', models);

                            const select = document.getElementById('vosk-model-select');

                            if (!select) {

                                console.error('Vosk model select element not found');

                                return;

                            }

                            select.innerHTML = '';

                            if (models.length === 0) {

                                const option = document.createElement('option');

                                option.value = '';

                                option.textContent = 'No models found';

                                select.appendChild(option);

                                showToast('warning', 'No Models', 'No speech recognition models found');

                            } else {

                                models.forEach(model => {

                                    const option = document.createElement('option');

                                    option.value = model.path;

                                    option.textContent = model.name;

                                    select.appendChild(option);

                                });

                                showToast('success', 'Models Loaded', `Found ${models.length} speech recognition models`);

                            }

                        })

                        .catch(error => {

                            console.error('Failed to load Vosk models:', error);

                            const select = document.getElementById('vosk-model-select');

                            if (select) {

                                select.innerHTML = '<option value="">Failed to load</option>';

                            }

                            showToast('error', 'Error', `Failed to load Vosk models: ${error.message}`, 5000);

                        });

                    // Load translation models based on selected provider
                    function loadTranslationModels() {
                        const provider = document.getElementById('translation-provider').value;
                        const select = document.getElementById('model-select');
                        
                        if (!select) {
                            console.error('Model select element not found');
                            return;
                        }
                        
                        select.innerHTML = '<option value="">Loading...</option>';
                        
                        console.log(`Loading ${provider} models...`);
                        
                        fetch(`/api/models?provider=${provider}`)
                            .then(response => {
                                console.log(`${provider} models API response status:`, response.status);
                                if (!response.ok) {
                                    throw new Error(`HTTP error! status: ${response.status}`);
                                }
                                return response.json();
                            })
                            .then(models => {
                                console.log(`${provider} models loaded:`, models);
                                
                                select.innerHTML = '';
                                
                                if (models.length === 0) {
                                    const option = document.createElement('option');
                                    option.value = '';
                                    option.textContent = 'No models found';
                                    select.appendChild(option);
                                    showToast('warning', 'No Models', `No translation models found. Please ensure ${provider} is running.`);
                                } else {
                                    models.forEach(model => {
                                        const option = document.createElement('option');
                                        option.value = model;
                                        option.textContent = model;
                                        select.appendChild(option);
                                    });
                                    showToast('success', 'Translation Models Loaded', `Found ${models.length} ${provider} models`);
                                }
                            })
                            .catch(error => {
                                console.error(`Failed to load ${provider} models:`, error);
                                if (select) {
                                    select.innerHTML = '<option value="">Failed to load</option>';
                                }
                                showToast('error', 'Error', `Failed to load ${provider} models: ${error.message}`, 5000);
                            });
                    }
                    
                    // Load initial models
                    loadTranslationModels();
                    
                    // Add event listener for provider change
                    document.getElementById('translation-provider').addEventListener('change', loadTranslationModels);

                    // Load TTS voices
                    console.log('Loading TTS voices...');
                    loadTTSVoices();
                    checkVoiceCloneAvailability();
                    enumerateAudioOutputDevices();

                                }

                                // Socket event handling

                                socket.on('connected', (data) => {

                                            showToast('success', 'Connected', 'Successfully connected to server');

                                        });

                                        socket.on('status', (data) => {
            const statusEl = document.getElementById('status');
            const statusTextEl = statusEl.querySelector('.status-text');
            statusTextEl.textContent = data.message;
            statusEl.className = 'status';
            
            // Force status class application
            console.log('Status changed to:', data.status);
            console.log('Status element classes before:', statusEl.className);
            
            switch(data.status) {
                case 'listening':
                    statusEl.classList.add('status-listening');
                    showToast('info', 'Listening', 'Speech recognition started');
                    
                    // Force canvas to be visible after a small delay
                    setTimeout(() => {
                        const canvas = document.getElementById('audio-waveform');
                        if (canvas) {
                            canvas.style.display = 'block';
                            console.log('Canvas display forced after status change');
                        }
                    }, 100);
                    
                    break;
                case 'translating':
                    statusEl.classList.add('status-translating');
                    showToast('info', 'Translating', 'Translation in progress');
                    break;
                case 'stopped':
                    statusEl.classList.add('status-idle');
                    showToast('warning', 'Stopped', 'Recognition stopped');
                    break;
                default:
                    statusEl.classList.add('status-idle');
            }
            
            console.log('Status element classes after:', statusEl.className);
        });

        let lastPartialUpdate = 0;
        const PARTIAL_UPDATE_INTERVAL = 200; // Increased to 200ms to reduce DOM operations
        let recognitionContentEl = document.getElementById('recognition-content'); // Cache DOM element

        socket.on('recognition_partial', (data) => {
            const now = Date.now();
            if (now - lastPartialUpdate < PARTIAL_UPDATE_INTERVAL) {
                return; // Throttle updates
            }
            
            lastPartialUpdate = now;
            if (recognitionContentEl) {
                recognitionContentEl.innerHTML = `<span class="result-partial">${data.text}</span>`;
            }
        });

        socket.on('recognition_result', (data) => {
            const newText = data.text.trim();
            
            if (!newText) {
                return;
            }
            
            // 优化：检查是否与最近识别的文本重复（只检查最近几条）
            const recentTexts = lastRecognizedTexts.slice(-3); // 只检查最近3条
            let isDuplicate = false;
            
            for (let i = 0; i < recentTexts.length; i++) {
                const historyText = recentTexts[i];
                // 完全相同，跳过
                if (newText === historyText) {
                    console.log('Duplicate recognition (exact match), skipping:', newText);
                    isDuplicate = true;
                    break;
                }
                // 新文本是历史文本的一部分，跳过
                if (historyText.includes(newText) && newText.length < historyText.length) {
                    console.log('Duplicate recognition (substring), skipping:', newText);
                    isDuplicate = true;
                    break;
                }
            }
            
            if (isDuplicate) {
                return;
            }
            
            // 添加到历史记录
            lastRecognizedTexts.push(newText);
            if (lastRecognizedTexts.length > MAX_HISTORY) {
                lastRecognizedTexts.shift();
            }
            
            // 追加到当前识别结果
            currentRecognition += newText + ' ';
            
            // 优化：减少DOM操作，使用textContent
            if (recognitionContentEl) {
                recognitionContentEl.textContent = currentRecognition;
                
                // 自动滚动到底部
                recognitionContentEl.scrollTop = recognitionContentEl.scrollHeight;
            }
        });

        socket.on('recognition_complete', (data) => {
            document.getElementById('stt-time').textContent = data.total_time;
            document.getElementById('stt-segments').textContent = data.segments;
            showToast('success', 'Recognition Complete', `Recognized ${data.segments} segments in ${data.total_time}`);
        });

        let lastTranslationUpdate = 0;
        const TRANSLATION_UPDATE_INTERVAL = 50; // Reduced to 50ms for smoother streaming
        let translationContentEl = document.getElementById('translation-content');
        let autoPlayTTSCheckbox = document.getElementById('auto-play-tts');
        let streamingTTSCheckbox = document.getElementById('streaming-tts');
        let pendingTranslationUpdate = null;
        let translationRAF = null;

        function updateTranslationDisplay(data) {
            if (translationContentEl) {
                translationContentEl.textContent = data.translation;
                currentTranslation = data.translation;
                
                const autoPlay = autoPlayTTSCheckbox?.checked || false;
                const streamingEnabled = streamingTTSCheckbox?.checked || false;
                
                if (autoPlay && streamingEnabled) {
                    handleStreamingTranslation(data.translation);
                }
                
                if (data.char_count === data.chunk.length) {
                    showToast('info', 'Translation Started', 'Translation is streaming...');
                }
                
                translationContentEl.scrollTop = translationContentEl.scrollHeight;
            }
        }

        socket.on('translation_chunk', (data) => {
            const now = Date.now();
            
            // Use requestAnimationFrame for smoother updates
            if (now - lastTranslationUpdate >= TRANSLATION_UPDATE_INTERVAL) {
                lastTranslationUpdate = now;
                if (translationRAF) {
                    cancelAnimationFrame(translationRAF);
                }
                translationRAF = requestAnimationFrame(() => updateTranslationDisplay(data));
            } else {
                // Store latest data for next update
                pendingTranslationUpdate = data;
            }
        });

        socket.on('translation_prompt', (data) => {
            const promptContent = document.getElementById('prompt-content');
            if (promptContent) {
                promptContent.textContent = data.prompt;
                currentPrompt = data.prompt;
                document.getElementById('edit-prompt-btn').style.display = 'inline-block';
                document.getElementById('save-preset-btn').style.display = 'inline-block';
            }
        });

        // Handle complete sentences from vLLM for streaming TTS
        socket.on('translation_sentence_complete', (data) => {
            console.log('🎯 Complete sentence received:', data);
            
            const autoPlay = document.getElementById('auto-play-tts').checked;
            const streamingEnabled = document.getElementById('streaming-tts')?.checked || false;
            
            // Only process if auto-play and streaming TTS are enabled
            if (autoPlay && streamingEnabled && data.sentence) {
                const sentence = data.sentence.trim();
                
                // Avoid duplicate sentences
                if (sentence.length > 3 && !ttsQueue.includes(sentence)) {
                    console.log('🎯 Adding sentence to TTS queue:', sentence);
                    ttsQueue.push(sentence);
                    
                    // Start playing if not already playing
                    if (!isTTSPlaying) {
                        isTTSPlaying = true;
                        document.getElementById('tts-play-btn').classList.add('playing');
                        processStreamingTTS();
                    }
                    
                    // Preload next sentences for smoother playback
                    if (ttsQueue.length > 1) {
                        parallelPreloadTTS(ttsQueue.slice(1, 4));
                    }
                }
            }
        });

        socket.on('translation_complete', (data) => {
            document.getElementById('translation-time').textContent = data.total_time;
            document.getElementById('translation-chars').textContent = data.chars;
            
            // Enable TTS play button
            document.getElementById('tts-play-btn').disabled = false;
            document.getElementById('edit-translation-btn').style.display = 'inline-block';
            
            // Auto-play TTS if enabled and there's translation text
            const autoPlay = document.getElementById('auto-play-tts').checked;
            const streamingEnabled = document.getElementById('streaming-tts')?.checked || false;
            
            if (autoPlay && !streamingEnabled && currentTranslation.trim()) {
                // Ensure voice sample is selected before auto-playing
                if (selectedVoiceSample) {
                    setTimeout(() => {
                        playTTS();
                    }, 500);
                } else {
                    // Try to load voice samples and auto-select one
                    loadVoiceSamples().then(() => {
                        if (selectedVoiceSample) {
                            setTimeout(() => {
                                playTTS();
                            }, 500);
                        } else {
                            showToast('warning', 'No Voice Sample', 'Please upload and select a voice sample to enable auto-play');
                        }
                    });
                }
            }
            
            // Process remaining text before resetting streaming TTS
            if (streamingEnabled) {
                if (sentenceTimeout) {
                    clearTimeout(sentenceTimeout);
                    sentenceTimeout = null;
                }
                
                const remainingText = currentTranslation.substring(lastProcessedLength);
                if (remainingText.trim().length > 2) {
                    ttsQueue.push(remainingText.trim());
                    if (!isTTSPlaying) {
                        isTTSPlaying = true;
                        document.getElementById('tts-play-btn').classList.add('playing');
                        processStreamingTTS();
                    }
                }
                
                streamingTTS = false;
            }
            
            // Show performance metrics
            let message = `Translated ${data.chars} characters in ${data.total_time}`;
            if (data.first_chunk_time && data.first_chunk_time !== 'N/A') {
                message += ` (first response: ${data.first_chunk_time})`;
            }
            if (data.sentences) {
                message += ` | ${data.sentences} sentences`;
            }
            showToast('success', 'Translation Complete', message);
        });

        socket.on('error', (data) => {
            showToast('error', 'Error', data.message, 5000);
            stopRecognition();
        });

        // GSV-TTS-Lite model loading status
        socket.on('gsv_tts_status', (data) => {
            console.log('GSV-TTS-Lite status:', data);
            
            // Update TTS status indicator
            updateTTSStatus(data.message, data.status === 'loaded' ? 'active' : 'processing');
            
            // Show toast notification
            if (data.status === 'loading') {
                showToast('info', 'Model Loading', data.message, 10000);
            } else if (data.status === 'loading_gpt') {
                showToast('info', 'Model Loading', data.message, 5000);
            } else if (data.status === 'loading_sovits') {
                showToast('info', 'Model Loading', data.message, 5000);
            } else if (data.status === 'loaded') {
                showToast('success', 'Model Ready', data.message, 3000);
            }
        });

        // Start recognition
        function startRecognition() {
            const micIndex = document.getElementById('microphone-select').value;
            const voskModelPath = document.getElementById('vosk-model-select').value;
            const provider = document.getElementById('translation-provider').value;
            const modelName = document.getElementById('model-select').value;
            const presetId = document.getElementById('translation-style-preset').value;
            const customStyle = document.getElementById('translation-style').value.trim();

            if (!micIndex) {
                showToast('warning', 'Warning', 'Please select a microphone');
                return;
            }

            if (!voskModelPath) {
                showToast('warning', 'Warning', 'Please select a speech recognition model');
                return;
            }

            if (!modelName) {
                showToast('warning', 'Warning', 'Please select a translation model');
                return;
            }

            isProcessing = true;
            currentRecognition = '';
            currentTranslation = '';
            currentPrompt = '';
            lastRecognizedTexts = [];  // 清空去重历史记录

            // Initialize streaming TTS
            const streamingEnabled = document.getElementById('streaming-tts')?.checked || false;
            if (streamingEnabled) {
                streamingTTS = true;
                ttsQueue = [];
                currentSentenceIndex = 0;
                accumulatedTranslation = '';
                lastProcessedLength = 0;
                ttsProcessing = false;
            }

            showToast('info', 'Starting Recognition', 'Initializing speech recognition...');

            document.getElementById('start-btn').disabled = true;
            document.getElementById('stop-btn').disabled = false;
            document.getElementById('recognition-content').innerHTML = '<span class="result-partial">Listening...</span>';
            document.getElementById('translation-content').innerHTML = '<span class="result-partial">Waiting for translation...</span>';
            document.getElementById('prompt-content').innerHTML = '<span class="result-partial">Prompt will appear here...</span>';
            document.getElementById('edit-translation-btn').style.display = 'none';
            document.getElementById('edit-prompt-btn').style.display = 'none';
            document.getElementById('save-preset-btn').style.display = 'none';
            document.getElementById('stt-time').textContent = '-';
            document.getElementById('stt-segments').textContent = '-';
            document.getElementById('translation-time').textContent = '-';
            document.getElementById('translation-chars').textContent = '-';

            socket.emit('start_recognition', {
                mic_index: parseInt(micIndex),
                vosk_model_path: voskModelPath,
                provider: provider,
                model_name: modelName,
                preset_id: presetId || undefined,
                translation_style: customStyle || undefined
            });
        }

        // Stop recognition
        function stopRecognition() {
            isProcessing = false;
            document.getElementById('start-btn').disabled = false;
            document.getElementById('stop-btn').disabled = true;
            showToast('info', 'Recognition Stopped', 'Speech recognition has been stopped');
            socket.emit('stop_recognition');
        }

        // Page Navigation
        function switchPage(page) {
            const recognitionPage = document.getElementById('page-recognition');
            const modelsPage = document.getElementById('page-models');
            const frpPage = document.getElementById('page-frp');
            const navRecognition = document.getElementById('nav-recognition');
            const navModels = document.getElementById('nav-models');
            const navFRP = document.getElementById('nav-frp');

            if (page === 'recognition') {
                // Fade out models page
                modelsPage.classList.add('hidden');
                if (frpPage) frpPage.classList.add('hidden');
                setTimeout(() => {
                    modelsPage.style.display = 'none';
                    modelsPage.classList.remove('hidden');
                    if (frpPage) {
                        frpPage.style.display = 'none';
                        frpPage.classList.remove('hidden');
                    }
                    
                    // Show recognition page with animation
                    recognitionPage.style.display = 'block';
                    recognitionPage.style.opacity = '0';
                    recognitionPage.style.transform = 'translateY(20px)';
                    
                    setTimeout(() => {
                        recognitionPage.style.opacity = '1';
                        recognitionPage.style.transform = 'translateY(0)';
                    }, 50);
                }, 500);

                navRecognition.classList.add('active');
                navModels.classList.remove('active');
                if (navFRP) navFRP.classList.remove('active');
            } else if (page === 'models') {
                // Fade out recognition page
                recognitionPage.style.opacity = '0';
                recognitionPage.style.transform = 'translateY(20px)';
                if (frpPage) frpPage.classList.add('hidden');
                
                setTimeout(() => {
                    recognitionPage.style.display = 'none';
                    if (frpPage) {
                        frpPage.style.display = 'none';
                        frpPage.classList.remove('hidden');
                    }
                    
                    // Show models page with animation
                    modelsPage.style.display = 'block';
                    modelsPage.classList.remove('hidden');
                    
                    // Load model data
                    loadModelData();
                }, 500);

                navRecognition.classList.remove('active');
                navModels.classList.add('active');
                if (navFRP) navFRP.classList.remove('active');
            } else if (page === 'frp') {
                // Fade out other pages
                recognitionPage.style.opacity = '0';
                recognitionPage.style.transform = 'translateY(20px)';
                modelsPage.classList.add('hidden');
                
                setTimeout(() => {
                    recognitionPage.style.display = 'none';
                    modelsPage.style.display = 'none';
                    modelsPage.classList.remove('hidden');
                    
                    // Show FRP page with animation
                    frpPage.style.display = 'block';
                    frpPage.style.opacity = '0';
                    frpPage.style.transform = 'translateY(20px)';
                    
                    setTimeout(() => {
                        frpPage.style.opacity = '1';
                        frpPage.style.transform = 'translateY(0)';
                        loadFRPTunnels();
                        startFRPOutputPolling();
                    }, 50);
                }, 500);

                navRecognition.classList.remove('active');
                navModels.classList.remove('active');
                if (navFRP) navFRP.classList.add('active');
            }
        }

        // Model Tab Switching
        function switchModelTab(tab) {
            const availableContainer = document.getElementById('available-models-container');
            const vllmContainer = document.getElementById('vllm-models-container');
            const gsvTTSContainer = document.getElementById('gsv-tts-container');
            const loadedContainer = document.getElementById('loaded-models-container');
            const tabs = document.querySelectorAll('.model-tab');

            tabs.forEach(t => t.classList.remove('active'));

            // Hide all containers
            availableContainer.style.display = 'none';
            vllmContainer.style.display = 'none';
            gsvTTSContainer.style.display = 'none';
            loadedContainer.style.display = 'none';

            if (tab === 'available') {
                availableContainer.style.display = 'block';
                tabs[0].classList.add('active');
                loadModelData();
            } else if (tab === 'vllm') {
                vllmContainer.style.display = 'block';
                tabs[1].classList.add('active');
                loadVLLMModels();
            } else if (tab === 'gsv-tts') {
                gsvTTSContainer.style.display = 'block';
                tabs[2].classList.add('active');
                loadGSVTTSRecommendedModels();
                loadGSVTTSSystemInfo();
            } else if (tab === 'loaded') {
                loadedContainer.style.display = 'block';
                tabs[3].classList.add('active');
                loadLoadedModels();
            }
        }

        // Load loaded models
        async function loadLoadedModels() {
            const container = document.getElementById('loaded-models-list');
            container.innerHTML = '<div class="loading-spinner">Loading loaded models...</div>';
            
            try {
                const response = await fetch('/api/vllm-models/loaded');
                const data = await response.json();
                
                if (data.total === 0) {
                    container.innerHTML = `
                        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                            <div style="font-size: 48px; margin-bottom: 15px;">💾</div>
                            <div>No models currently loaded</div>
                            <div style="font-size: 12px; margin-top: 10px;">Models will appear here when loaded</div>
                        </div>
                    `;
                } else {
                    let html = '';
                    
                    // vLLM models
                    if (data.vllm && data.vllm.length > 0) {
                        html += `
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: var(--primary-color); margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                                    <img src="/static/icons/vllm.png" alt="vLLM" style="width: 20px; height: 20px;">
                                    vLLM Models
                                </h4>
                                <div style="display: flex; flex-direction: column; gap: 8px;">
                        `;
                        
                        data.vllm.forEach(model => {
                            html += createLoadedModelCard(model);
                        });
                        
                        html += `</div></div>`;
                    }
                    
                    // GSV-TTS models
                    if (data.gsv_tts && data.gsv_tts.length > 0) {
                        html += `
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: var(--primary-color); margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                                    <img src="/static/icons/gradio.png" alt="GSV-TTS" style="width: 20px; height: 20px;">
                                    GSV-TTS Models
                                </h4>
                                <div style="display: flex; flex-direction: column; gap: 8px;">
                        `;
                        
                        data.gsv_tts.forEach(model => {
                            html += createLoadedModelCard(model);
                        });
                        
                        html += `</div></div>`;
                    }
                    
                    // Vosk models
                    if (data.vosk && data.vosk.length > 0) {
                        html += `
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: var(--primary-color); margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                                    <img src="/static/icons/vosk.ico" alt="Vosk" style="width: 20px; height: 20px;">
                                    Vosk Models
                                </h4>
                                <div style="display: flex; flex-direction: column; gap: 8px;">
                        `;
                        
                        data.vosk.forEach(model => {
                            html += createLoadedModelCard(model);
                        });
                        
                        html += `</div></div>`;
                    }
                    
                    container.innerHTML = html;
                }
            } catch (error) {
                console.error('Failed to load loaded models:', error);
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                        <div style="font-size: 48px; margin-bottom: 15px;">❌</div>
                        <div>Failed to load loaded models</div>
                        <div style="font-size: 12px; margin-top: 10px;">Please try again later</div>
                    </div>
                `;
            }
        }

        // Create loaded model card
        function createLoadedModelCard(model) {
            const locationIcon = model.location === 'GPU' ? '🟢' : '⚪';
            const locationClass = model.location === 'GPU' ? 'gpu-location' : 'cpu-location';
            const typeIcon = getModelTypeIcon(model.type);
            
            return `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: var(--glass-bg); border-radius: 8px; border: 1px solid var(--glass-border);">
                    <div style="flex: 1; display: flex; align-items: center; gap: 12px;">
                        <div style="width: 32px; height: 32px; background: var(--glass-bg); border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                            ${typeIcon}
                        </div>
                        <div>
                            <div style="font-weight: 600; color: var(--text-primary);">${model.name}</div>
                            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">
                                <span style="margin-right: 10px;">${model.type.toUpperCase()}</span>
                                <span class="${locationClass}" style="display: flex; align-items: center; gap: 4px;">
                                    ${locationIcon} ${model.location}
                                </span>
                            </div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); padding: 4px 8px; background: rgba(78, 205, 196, 0.1); border-radius: 4px;">
                        ${model.status}
                    </div>
                </div>
            `;
        }

        // Get model type icon
        function getModelTypeIcon(type) {
            const icons = {
                'vllm': '<img src="/static/icons/vllm.png" style="width: 16px; height: 16px;">',
                'gsv-tts': '<img src="/static/icons/gradio.png" style="width: 16px; height: 16px;">',
                'vosk': '<img src="/static/icons/vosk.ico" style="width: 16px; height: 16px;">'
            };
            return icons[type] || '📦';
        }

        // Unload all models
        async function unloadAllModels() {
            if (!confirm('Are you sure you want to unload all models? This will free up memory but may slow down subsequent operations.')) {
                return;
            }
            
            const button = document.getElementById('unload-all-btn');
            button.disabled = true;
            button.innerHTML = '<span><i class="fas fa-spinner fa-spin"></i></span> Unloading...';
            
            try {
                const response = await fetch('/api/vllm-models/unload-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    showToast('success', 'Success', data.message);
                    // Reload loaded models list
                    setTimeout(() => {
                        loadLoadedModels();
                    }, 1000);
                } else {
                    showToast('error', 'Error', data.message);
                }
            } catch (error) {
                console.error('Failed to unload models:', error);
                showToast('error', 'Error', 'Failed to unload models');
            } finally {
                button.disabled = false;
                button.innerHTML = '<span><i class="fas fa-trash-alt"></i></span> Unload All Models';
            }
        }

        // vLLM Model Management
        let vllmDownloadProgress = {};



        async function loadVLLMModels() {
            // Load installed models
            try {
                const response = await fetch('/api/vllm-models');
                const data = await response.json();
                
                const container = document.getElementById('installed-vllm-models');
                document.getElementById('installed-vllm-count').textContent = `(${data.count})`;
                
                if (data.count === 0) {
                    container.innerHTML = `
                        <div style="text-align: center; padding: 30px; color: var(--text-secondary);">
                            <div style="font-size: 48px; margin-bottom: 15px;">📭</div>
                            <div>No vLLM models installed</div>
                            <div style="font-size: 12px; margin-top: 10px;">Download a model from the recommended list below</div>
                        </div>
                    `;
                } else {
                    let html = '<div style="display: flex; flex-direction: column; gap: 10px;">';
                    data.models.forEach(model => {
                        html += `
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; color: var(--glass-text);">${model.name}</div>
                                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                                        Size: ${model.size} | Modified: ${new Date(model.modified).toLocaleDateString()}
                                    </div>
                                </div>
                                <button onclick="deleteVLLMModel('${model.name}')" class="btn btn-danger" style="padding: 6px 12px; font-size: 12px;">
                                    🗑️ Delete
                                </button>
                            </div>
                        `;
                    });
                    html += '</div>';
                    container.innerHTML = html;
                }
            } catch (error) {
                console.error('Error loading vLLM models:', error);
                document.getElementById('installed-vllm-models').innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #ff6b6b;">
                        Error loading installed models
                    </div>
                `;
            }

            // Load recommended models
            try {
                const response = await fetch('/api/vllm-models/recommended');
                const data = await response.json();
                
                const container = document.getElementById('recommended-vllm-models');
                
                // Vendor selector tabs
                let html = `
                    <div style="margin-bottom: 15px;">
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;" id="vllm-vendor-tabs">
                `;
                
                // Add vendor tabs
                Object.keys(data.vendors).forEach((vendorKey, index) => {
                    const vendor = data.vendors[vendorKey];
                    const isActive = index === 0;
                    html += `
                        <button onclick="selectVLLMVendor('${vendorKey}')" 
                                class="vllm-vendor-tab ${isActive ? 'active' : ''}" 
                                data-vendor="${vendorKey}"
                                style="background: ${isActive ? 'rgba(57, 197, 187, 0.3)' : 'rgba(255,255,255,0.1)'}; 
                                       color: ${isActive ? '#39c5bb' : 'var(--glass-text)'}; 
                                       border: 1px solid ${isActive ? 'rgba(57, 197, 187, 0.5)' : 'rgba(255,255,255,0.2)'}; 
                                       border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer; 
                                       transition: all 0.3s ease; display: flex; align-items: center; gap: 6px;">
                            <span>${vendor.icon}</span>
                            <span>${vendor.name}</span>
                            <span style="background: rgba(255,255,255,0.2); padding: 2px 6px; border-radius: 4px; font-size: 11px;">${vendor.models.length}</span>
                        </button>
                    `;
                });
                
                html += `
                        </div>
                    </div>
                    <div id="vllm-vendor-content">
                `;
                
                // Add vendor content sections
                Object.keys(data.vendors).forEach((vendorKey, index) => {
                    const vendor = data.vendors[vendorKey];
                    const isVisible = index === 0;
                    
                    html += `
                        <div class="vllm-vendor-section" data-vendor="${vendorKey}" style="display: ${isVisible ? 'block' : 'none'};">
                            <div style="margin-bottom: 15px; padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; border-left: 3px solid #39c5bb;">
                                <div style="font-weight: 600; color: var(--glass-text); margin-bottom: 4px;">${vendor.icon} ${vendor.name}</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">${vendor.description}</div>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;">
                    `;
                    
                    vendor.models.forEach(model => {
                        const isInstalled = model.installed;
                        const isDownloading = vllmDownloadProgress[model.id] && 
                                             vllmDownloadProgress[model.id].status === 'downloading';
                        
                        let statusBadge = '';
                        let actionButton = '';
                        
                        if (isInstalled) {
                            statusBadge = '<span style="background: rgba(57, 197, 187, 0.3); color: #39c5bb; padding: 3px 6px; border-radius: 4px; font-size: 10px;">✓</span>';
                            actionButton = `<button disabled class="btn btn-secondary" style="padding: 6px 12px; font-size: 11px; opacity: 0.5;">已安装</button>`;
                        } else if (isDownloading) {
                            const progress = vllmDownloadProgress[model.id];
                            statusBadge = `<span style="background: rgba(255, 193, 7, 0.3); color: #ffc107; padding: 3px 6px; border-radius: 4px; font-size: 10px;">${progress.progress.toFixed(0)}%</span>`;
                            actionButton = `<button onclick="cancelVLLMDownload('${model.id}')" class="btn btn-danger" style="padding: 6px 12px; font-size: 11px;">取消</button>`;
                        } else {
                            statusBadge = '';
                            actionButton = `<button onclick="downloadVLLMModel('${model.id}')" class="btn btn-primary" style="padding: 6px 12px; font-size: 11px;">⬇️ 下载</button>`;
                        }
                        
                        // Highlight recommended models
                        const isRecommended = model.tags && model.tags.includes('recommended');
                        const borderStyle = isRecommended ? 'border: 1px solid rgba(57, 197, 187, 0.5);' : 'border: 1px solid rgba(255,255,255,0.1);';
                        
                        // Quantized model badge
                        const quantBadge = model.tags && model.tags.includes('quantized') 
                            ? '<span style="background: rgba(255, 107, 107, 0.3); color: #ff6b6b; padding: 2px 5px; border-radius: 3px; font-size: 9px; margin-left: 4px;">量化</span>' 
                            : '';
                        
                        const tagsHtml = model.tags ? model.tags.slice(0, 3).map(tag => 
                            `<span style="background: rgba(255,255,255,0.1); padding: 2px 5px; border-radius: 3px; font-size: 9px; margin-right: 3px;">${tag}</span>`
                        ).join('') : '';
                        
                        html += `
                            <div style="background: rgba(0,0,0,0.2); border-radius: 10px; padding: 12px; ${borderStyle}">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                                    <div style="font-weight: 600; color: var(--glass-text); font-size: 13px;">
                                        ${model.name}${quantBadge}
                                    </div>
                                    ${statusBadge}
                                </div>
                                <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; min-height: 32px; line-height: 1.4;">${model.description}</div>
                                <div style="display: flex; flex-wrap: wrap; gap: 8px; font-size: 10px; color: var(--text-secondary); margin-bottom: 8px;">
                                    <span title="模型大小">📦 ${model.size}</span>
                                    <span title="参数量">🔢 ${model.params}</span>
                                    ${model.vram ? `<span title="显存需求">💾 ${model.vram}</span>` : ''}
                                    <span title="语言">🌐 ${model.language}</span>
                                </div>
                                <div style="margin-bottom: 8px;">${tagsHtml}</div>
                                ${isDownloading ? `
                                    <div style="margin-bottom: 8px;">
                                        <div style="background: rgba(255,255,255,0.1); height: 3px; border-radius: 2px; overflow: hidden;">
                                            <div style="background: linear-gradient(90deg, #39c5bb, #ff7bac); height: 100%; width: ${vllmDownloadProgress[model.id].progress}%; transition: width 0.3s;"></div>
                                        </div>
                                    </div>
                                ` : ''}
                                <div style="display: flex; justify-content: flex-end;">
                                    ${actionButton}
                                </div>
                            </div>
                        `;
                    });
                    
                    html += `
                            </div>
                        </div>
                    `;
                });
                
                html += '</div>';
                container.innerHTML = html;
                
                // Start polling for download progress
                if (Object.values(vllmDownloadProgress).some(p => p.status === 'downloading')) {
                    setTimeout(() => pollVLLMDownloadProgress(), 2000);
                }
            } catch (error) {
                console.error('Error loading recommended vLLM models:', error);
                document.getElementById('recommended-vllm-models').innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #ff6b6b;">
                        Error loading recommended models
                    </div>
                `;
            }
        }

        function selectVLLMVendor(vendorKey) {
            // Update tab styles
            document.querySelectorAll('.vllm-vendor-tab').forEach(tab => {
                if (tab.dataset.vendor === vendorKey) {
                    tab.style.background = 'rgba(57, 197, 187, 0.3)';
                    tab.style.color = '#39c5bb';
                    tab.style.borderColor = 'rgba(57, 197, 187, 0.5)';
                    tab.classList.add('active');
                } else {
                    tab.style.background = 'rgba(255,255,255,0.1)';
                    tab.style.color = 'var(--glass-text)';
                    tab.style.borderColor = 'rgba(255,255,255,0.2)';
                    tab.classList.remove('active');
                }
            });
            
            // Show/hide vendor sections
            document.querySelectorAll('.vllm-vendor-section').forEach(section => {
                section.style.display = section.dataset.vendor === vendorKey ? 'block' : 'none';
            });
        }

        async function downloadVLLMModel(modelId) {
            const sourceMap = {
                'huggingface': 'huggingface',
                'hf-mirror': 'huggingface',
                'modelscope': 'modelscope'
            };
            
            // Determine if using official HuggingFace (not mirror)
            const useOfficial = currentVLLMDownloadSource === 'huggingface';
            
            try {
                const response = await fetch('/api/vllm-models/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model_id: modelId,
                        source: sourceMap[currentVLLMDownloadSource] || 'huggingface',
                        use_official: useOfficial
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    showToast('success', 'Download Started', `Downloading ${modelId}...`);
                    vllmDownloadProgress[modelId] = { status: 'downloading', progress: 0, speed: 0 };
                    loadVLLMModels();
                    pollVLLMDownloadProgress();
                } else {
                    showToast('error', 'Download Failed', data.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error starting download:', error);
                showToast('error', 'Download Failed', error.message);
            }
        }

        async function downloadCustomVLLMModel() {
            const modelId = document.getElementById('custom-vllm-model-id').value.trim();
            if (!modelId) {
                showToast('warning', 'Invalid Input', 'Please enter a model ID');
                return;
            }
            
            await downloadVLLMModel(modelId);
            document.getElementById('custom-vllm-model-id').value = '';
        }

        async function pollVLLMDownloadProgress() {
            const downloadingModels = Object.keys(vllmDownloadProgress).filter(
                id => vllmDownloadProgress[id].status === 'downloading'
            );
            
            if (downloadingModels.length === 0) return;
            
            for (const modelId of downloadingModels) {
                try {
                    const response = await fetch(`/api/vllm-models/download-progress/${modelId}`);
                    if (response.ok) {
                        const data = await response.json();
                        vllmDownloadProgress[modelId] = data;
                        
                        if (data.status === 'completed') {
                            showToast('success', 'Download Complete', `${modelId} has been downloaded successfully`);
                            loadVLLMModels();
                        } else if (data.status === 'error') {
                            showToast('error', 'Download Failed', data.error || 'Unknown error');
                        }
                    }
                } catch (error) {
                    console.error('Error polling download progress:', error);
                }
            }
            
            // Update UI
            loadVLLMModels();
            
            // Continue polling if still downloading
            if (Object.values(vllmDownloadProgress).some(p => p.status === 'downloading')) {
                setTimeout(() => pollVLLMDownloadProgress(), 2000);
            }
        }

        async function cancelVLLMDownload(modelId) {
            try {
                const response = await fetch('/api/vllm-models/cancel-download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_id: modelId })
                });
                
                if (response.ok) {
                    delete vllmDownloadProgress[modelId];
                    showToast('info', 'Download Cancelled', `Download of ${modelId} has been cancelled`);
                    loadVLLMModels();
                }
            } catch (error) {
                console.error('Error cancelling download:', error);
            }
        }

        async function deleteVLLMModel(modelName) {
            if (!confirm(`Are you sure you want to delete ${modelName}?\n\nThis action cannot be undone.`)) {
                return;
            }
            
            try {
                const response = await fetch('/api/vllm-models/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_name: modelName })
                });
                
                if (response.ok) {
                    showToast('success', 'Model Deleted', `${modelName} has been deleted`);
                    loadVLLMModels();
                } else {
                    const data = await response.json();
                    showToast('error', 'Delete Failed', data.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error deleting model:', error);
                showToast('error', 'Delete Failed', error.message);
            }
        }

        // Listen for download complete events
        socket.on('vllm_model_download_complete', (data) => {
            console.log('vLLM model download complete:', data);
            delete vllmDownloadProgress[data.model_id];
            showToast('success', 'Download Complete', `${data.model_id} is ready to use`);
            loadVLLMModels();
        });

        // Load GSV-TTS-Lite Recommended Models
        function loadGSVTTSRecommendedModels() {
            const container = document.getElementById('gsv-tts-recommended-models');
            container.innerHTML = '<div class="loading-spinner">Loading recommended models...</div>';

            fetch('/api/gsv-tts/recommended-models')
                .then(response => response.json())
                .then(data => {
                    let html = '';
                    
                    function getDownloadUrl(model) {
                        if (model.download_urls && model.download_urls[currentDownloadSource]) {
                            return model.download_urls[currentDownloadSource];
                        }
                        return model.download_url;
                    }
                    
                    function getModelCard(model, modelType) {
                        const isDownloading = gsvTtsDownloadProgress[model.id];
                        let progressInfo = '';
                        let buttonHtml = '';
                        
                        if (isDownloading) {
                            const progress = gsvTtsDownloadProgress[model.id] || {};
                            const progressPercent = progress.progress || 0;
                            const statusText = {
                                'starting': 'Starting...',
                                'downloading': `Downloading... ${progressPercent.toFixed(1)}%`,
                                'extracting': 'Extracting...',
                                'completed': 'Completed',
                                'error': 'Error'
                            }[progress.status] || 'Processing...';
                            
                            progressInfo = `
                                <div style="margin-top: 8px;">
                                    <div style="display: flex; justify-content: space-between; font-size: 0.75em; color: var(--glass-text); margin-bottom: 4px;">
                                        <span>${statusText}</span>
                                        <span>${progress.speed ? progress.speed.toFixed(1) + ' MB/s' : ''}</span>
                                    </div>
                                    <div style="width: 100%; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: ${progressPercent}%; height: 100%; background: linear-gradient(90deg, var(--primary-color), #60a5fa); border-radius: 3px; transition: width 0.3s ease;"></div>
                                    </div>
                                </div>
                            `;
                            
                            buttonHtml = `<button disabled style="color: var(--glass-text); text-decoration: none; font-size: 0.85em; display: inline-flex; align-items: center; gap: 4px; padding: 6px 12px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; cursor: not-allowed; opacity: 0.6;">
                                <span>⏳</span> ${statusText}
                            </button>`;
                        } else {
                            buttonHtml = `<button onclick="downloadGSVTTSModel('${model.id}', '${model.name.replace(/'/g, "\\'")}')" style="color: var(--primary-color); text-decoration: none; font-size: 0.85em; display: inline-flex; align-items: center; gap: 4px; padding: 6px 12px; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 6px; transition: all 0.3s ease; cursor: pointer;">
                                <span>⬇️</span> Download
                            </button>`;
                        }
                        
                        return `
                            <div style="background: rgba(0, 0, 0, 0.2); border-radius: 8px; padding: 12px; border: 1px solid rgba(255, 255, 255, 0.1);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                    <strong style="color: var(--primary-color);">${model.name}</strong>
                                    ${model.required ? '<span style="background: rgba(251, 146, 60, 0.2); color: #fb923c; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 600;">Required</span>' : ''}
                                </div>
                                <div style="font-size: 0.85em; color: var(--glass-text); margin-bottom: 8px;">${model.description}</div>
                                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                    <span style="font-size: 0.8em; color: var(--glass-text); opacity: 0.7;">${model.size}</span>
                                    ${buttonHtml}
                                </div>
                                ${progressInfo}
                            </div>
                        `;
                    }
                    
                    if (data.base_models && data.base_models.length > 0) {
                        html += '<div style="margin-bottom: 20px;">';
                        html += '<h5 style="color: var(--primary-color); margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">';
                        html += '<span>🔧</span> Base Models';
                        html += '</h5>';
                        html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px;">';
                        
                        data.base_models.forEach(model => {
                            html += getModelCard(model, 'base');
                        });
                        
                        html += '</div></div>';
                    }
                    
                    if (data.gpt_models && data.gpt_models.length > 0) {
                        html += '<div style="margin-bottom: 20px;">';
                        html += '<h5 style="color: var(--primary-color); margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">';
                        html += '<span>🧠</span> GPT Models';
                        html += '</h5>';
                        html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px;">';
                        
                        data.gpt_models.forEach(model => {
                            html += getModelCard(model, 'gpt');
                        });
                        
                        html += '</div></div>';
                    }
                    
                    if (data.sovits_models && data.sovits_models.length > 0) {
                        html += '<div>';
                        html += '<h5 style="color: var(--primary-color); margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">';
                        html += '<span>🎵</span> SoVITS Models';
                        html += '</h5>';
                        html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px;">';
                        
                        data.sovits_models.forEach(model => {
                            html += getModelCard(model, 'sovits');
                        });
                        
                        html += '</div></div>';
                    }
                    
                    container.innerHTML = html;
                })
                .catch(error => {
                    console.error('Failed to load recommended models:', error);
                    container.innerHTML = `
                        <div style="padding: 20px; background: rgba(255, 0, 0, 0.1); border-radius: 12px; color: #ff6b6b;">
                            <div style="font-size: 24px; margin-bottom: 10px;">❌</div>
                            <div>Failed to load recommended models: ${error.message}</div>
                        </div>
                    `;
                });
        }

        // Load GSV-TTS-Lite System Info
        function loadGSVTTSSystemInfo() {
            const container = document.getElementById('gsv-available-models');
            container.innerHTML = '<div class="loading-spinner">Loading GSV-TTS-Lite system info...</div>';

            // Load available models status
            fetch('/api/gsv-tts/available-models')
                .then(response => response.json())
                .then(data => {
                    // Map model names to display names
                    const modelNameMap = {
                        'chinese_hubert': 'Chinese HuBERT',
                        'g2p': 'G2P',
                        'speaker_verification': 'Speaker Verification',
                        'gpt': 'GPT',
                        'sovits': 'SoVITS',
                        'chinese_roberta': 'Chinese RoBERTa'
                    };
                    
                    // Format file size
                    const formatSize = (bytes) => {
                        if (bytes === 0) return '0 B';
                        const k = 1024;
                        const sizes = ['B', 'KB', 'MB', 'GB'];
                        const i = Math.floor(Math.log(bytes) / Math.log(k));
                        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
                    };
                    
                    container.innerHTML = `
                        <div style="padding: 20px; background: var(--glass-bg); border-radius: 12px;">
                            <!-- 存储信息 -->
                            <div style="margin-bottom: 20px; padding: 15px; background: rgba(0, 0, 0, 0.2); border-radius: 8px;">
                                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                                    <span style="font-size: 20px;">💾</span>
                                    <strong style="color: var(--primary-color);">存储信息</strong>
                                </div>
                                <div style="font-size: 0.9em; color: var(--glass-text);">
                                    <div>模型目录: <span style="word-break: break-all;">${data.models_dir}</span></div>
                                    <div style="margin-top: 5px;">总大小: ${data.total_size_mb.toFixed(2)} MB</div>
                                </div>
                            </div>
                            
                            <!-- 基础模型 -->
                            <div style="margin-bottom: 20px;">
                                <strong style="color: var(--primary-color); display: flex; align-items: center; gap: 8px;">
                                    <span>🔧</span> 基础模型
                                </strong>
                                <ul style="list-style: none; padding: 0; margin: 10px 0 0 0;">
                                    ${Object.entries(data.available_models).filter(([key]) => !['gpt', 'sovits'].includes(key)).map(([key, model]) => `
                                        <li style="padding: 12px 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--glass-border);">
                                            <div style="display: flex; align-items: center; gap: 10px;">
                                                <span style="font-size: 16px;">${model.available ? '✅' : '❌'}</span>
                                                <span style="font-weight: 600; color: var(--glass-text);">${modelNameMap[key] || key.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                                            </div>
                                            <div>
                                                ${model.available ? `
                                                    <button onclick="deleteGSVModel('${key}', 'base')" style="background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid rgba(255, 107, 107, 0.3); border-radius: 6px; padding: 6px 12px; font-size: 0.85em; cursor: pointer; transition: all 0.3s ease; font-weight: 600;">
                                                        删除
                                                    </button>
                                                ` : '<span style="color: #ff6b6b; font-size: 0.85em;">未安装</span>'}
                                            </div>
                                        </li>
                                    `).join('')}
                                </ul>
                            </div>
                            
                            <!-- GPT模型 -->
                            <div style="margin-bottom: 20px;">
                                <strong style="color: var(--primary-color); display: flex; align-items: center; gap: 8px;">
                                    <span>🧠</span> GPT 模型
                                </strong>
                                <div style="margin-top: 10px;">
                                    ${data.available_models.gpt.available ? `
                                        <ul style="list-style: none; padding: 0; margin: 0;">
                                            ${data.available_models.gpt.models.map(model => `
                                                <li style="padding: 10px 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--glass-border);">
                                                    <div style="display: flex; align-items: center; gap: 10px;">
                                                        <span style="font-size: 16px;">✅</span>
                                                        <span style="font-weight: 500; color: var(--glass-text);">${model}</span>
                                                    </div>
                                                    <button onclick="deleteGSVModel('${model}', 'gpt')" style="background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid rgba(255, 107, 107, 0.3); border-radius: 6px; padding: 6px 12px; font-size: 0.85em; cursor: pointer; transition: all 0.3s ease; font-weight: 600;">
                                                        删除
                                                    </button>
                                                </li>
                                            `).join('')}
                                        </ul>
                                    ` : '<div style="color: #ff6b6b; padding: 10px;">未安装 GPT 模型</div>'}
                                </div>
                            </div>
                            
                            <!-- SoVITS模型 -->
                            <div style="margin-bottom: 20px;">
                                <strong style="color: var(--primary-color); display: flex; align-items: center; gap: 8px;">
                                    <span>🎵</span> SoVITS 模型
                                </strong>
                                <div style="margin-top: 10px;">
                                    ${data.available_models.sovits.available ? `
                                        <ul style="list-style: none; padding: 0; margin: 0;">
                                            ${data.available_models.sovits.models.map(model => `
                                                <li style="padding: 10px 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--glass-border);">
                                                    <div style="display: flex; align-items: center; gap: 10px;">
                                                        <span style="font-size: 16px;">✅</span>
                                                        <span style="font-weight: 500; color: var(--glass-text);">${model}</span>
                                                    </div>
                                                    <button onclick="deleteGSVModel('${model}', 'sovits')" style="background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid rgba(255, 107, 107, 0.3); border-radius: 6px; padding: 6px 12px; font-size: 0.85em; cursor: pointer; transition: all 0.3s ease; font-weight: 600;">
                                                        删除
                                                    </button>
                                                </li>
                                            `).join('')}
                                        </ul>
                                    ` : '<div style="color: #ff6b6b; padding: 10px;">未安装 SoVITS 模型</div>'}
                                </div>
                            </div>
                            
                            <!-- 参考音频 -->
                            <div style="margin-bottom: 20px;">
                                <strong style="color: var(--primary-color); display: flex; align-items: center; gap: 8px;">
                                    <span>🎤</span> 参考音频 (${data.reference_audios.length}个)
                                </strong>
                                <div style="margin-top: 10px;">
                                    ${data.reference_audios.length > 0 ? `
                                        <ul style="list-style: none; padding: 0; margin: 0;">
                                            ${data.reference_audios.map(audio => `
                                                <li style="padding: 10px 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--glass-border);">
                                                    <div style="display: flex; align-items: center; gap: 10px;">
                                                        <span style="font-size: 16px;">🎵</span>
                                                        <div>
                                                            <div style="font-weight: 500; color: var(--glass-text);">${audio.name}</div>
                                                            <div style="font-size: 0.8em; color: var(--glass-text); opacity: 0.7;">${formatSize(audio.size)}</div>
                                                        </div>
                                                    </div>
                                                    <button onclick="deleteGSVModel('${audio.name}', 'reference')" style="background: rgba(255, 107, 107, 0.2); color: #ff6b6b; border: 1px solid rgba(255, 107, 107, 0.3); border-radius: 6px; padding: 6px 12px; font-size: 0.85em; cursor: pointer; transition: all 0.3s ease; font-weight: 600;">
                                                        删除
                                                    </button>
                                                </li>
                                            `).join('')}
                                        </ul>
                                    ` : '<div style="color: #ff6b6b; padding: 10px;">未上传参考音频</div>'}
                                </div>
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    console.error('Failed to load GSV-TTS-Lite system info:', error);
                    container.innerHTML = `
                        <div style="padding: 20px; background: rgba(255, 0, 0, 0.1); border-radius: 12px; color: #ff6b6b;">
                            <div style="font-size: 24px; margin-bottom: 10px;">❌</div>
                            <div>加载 GSV-TTS-Lite 系统信息失败: ${error.message}</div>
                        </div>
                    `;
                });

            // Load model download links
            const modelsListContainer = document.getElementById('gsv-tts-models-list');
            modelsListContainer.innerHTML = '<div class="loading-spinner">加载模型下载链接...</div>';

            fetch('/api/gsv-tts-info')
                .then(response => response.json())
                .then(data => {
                    modelsListContainer.innerHTML = `
                        <ul style="list-style: none; padding: 0; margin: 0;">
                            ${data.required_models.map(model => `
                                <li style="padding: 15px 0; border-bottom: 1px solid var(--glass-border); transition: all 0.3s ease;">
                                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                        <span style="font-size: 18px;">📦</span>
                                        <strong style="color: var(--primary-color); font-size: 1.05em;">${model.name}</strong>
                                    </div>
                                    <div style="font-size: 0.9em; color: var(--glass-text); margin-left: 30px; margin-bottom: 8px; line-height: 1.5;">
                                        ${model.description}
                                    </div>
                                    <div style="margin-left: 30px;">
                                        <a href="${model.download_url}" target="_blank" style="color: var(--primary-color); text-decoration: none; font-size: 0.95em; display: inline-flex; align-items: center; gap: 5px; padding: 8px 16px; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 8px; transition: all 0.3s ease;">
                                            <span>⬇️</span> 下载
                                        </a>
                                    </div>
                                </li>
                            `).join('')}
                        </ul>
                    `;
                })
                .catch(error => {
                    console.error('Failed to load GSV-TTS-Lite model info:', error);
                    modelsListContainer.innerHTML = `
                        <div style="padding: 20px; background: rgba(255, 0, 0, 0.1); border-radius: 12px; color: #ff6b6b;">
                            <div style="font-size: 24px; margin-bottom: 10px;">❌</div>
                            <div>加载模型下载链接失败: ${error.message}</div>
                        </div>
                    `;
                });
        }

        // Handle GSV Model Upload
        async function handleGSVModelUpload(file) {
            if (!file) return;

            if (!file.name.endsWith('.zip')) {
                showToast('error', '文件格式错误', '请上传 ZIP 格式的模型文件');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                showToast('info', '正在上传', '正在上传并解压模型文件...');

                const response = await fetch('/api/gsv-tts/upload-model', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.status === 'success') {
                    showToast('success', '上传成功', data.message);
                    loadGSVTTSSystemInfo();
                } else {
                    throw new Error(data.error || '上传模型失败');
                }
            } catch (error) {
                console.error('模型上传失败:', error);
                showToast('error', '上传失败', error.message);
            }

            document.getElementById('gsv-model-file-input').value = '';
        }

        // Handle GSV Reference Audio Upload
        async function handleGSVReferenceUpload(file) {
            if (!file) return;

            const allowedExtensions = ['.wav', '.mp3', '.ogg', '.flac', '.m4a'];
            const fileExt = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!allowedExtensions.includes(fileExt)) {
                showToast('error', '文件格式错误', '请上传音频文件 (WAV, MP3, OGG, FLAC, M4A)');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                showToast('info', '正在上传', '正在上传参考音频...');

                const response = await fetch('/api/gsv-tts/upload-reference', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.status === 'success') {
                    showToast('success', '上传成功', data.message);
                    loadGSVTTSSystemInfo();
                } else {
                    throw new Error(data.error || '上传参考音频失败');
                }
            } catch (error) {
                console.error('参考音频上传失败:', error);
                showToast('error', '上传失败', error.message);
            }

            document.getElementById('gsv-reference-file-input').value = '';
        }

        // Delete GSV-TTS-Lite Model
        async function deleteGSVModel(modelName, modelType = 'base') {
            // Map model names to display names for better user experience
            const modelNameMap = {
                'chinese_hubert': 'Chinese HuBERT',
                'g2p': 'G2P',
                'speaker_verification': 'Speaker Verification',
                'gpt': 'GPT',
                'sovits': 'SoVITS',
                'chinese_roberta': 'Chinese RoBERTa'
            };
            
            const typeMap = {
                'base': '基础模型',
                'gpt': 'GPT模型',
                'sovits': 'SoVITS模型',
                'reference': '参考音频'
            };
            
            const displayName = modelNameMap[modelName] || modelName;
            const typeDisplay = typeMap[modelType] || modelType;
            
            if (!confirm(`确定要删除 ${typeDisplay} "${displayName}" 吗？此操作无法撤销。`)) {
                return;
            }

            try {
                showToast('warning', '正在删除', `正在删除 ${displayName}...`);

                const response = await fetch('/api/gsv-tts/delete-model', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ 
                        model_name: modelName,
                        type: modelType
                    })
                });

                const data = await response.json();

                if (data.status === 'success') {
                    showToast('success', '删除成功', data.message);
                    loadGSVTTSSystemInfo();
                } else {
                    throw new Error(data.error || 'Failed to delete model');
                }
            } catch (error) {
                console.error('Model deletion failed:', error);
                showToast('error', 'Deletion Failed', error.message);
            }
        }

        // Add drag and drop support for GSV model upload
        const gsvUploadArea = document.querySelector('#gsv-tts-container .voice-upload-area');
        if (gsvUploadArea) {
            gsvUploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                gsvUploadArea.classList.add('dragover');
            });

            gsvUploadArea.addEventListener('dragleave', () => {
                gsvUploadArea.classList.remove('dragover');
            });

            gsvUploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                gsvUploadArea.classList.remove('dragover');
                const file = e.dataTransfer.files[0];
                handleGSVModelUpload(file);
            });
        }

        // Load Model Data
        function loadModelData() {
            loadStorageInfo();
            loadAvailableModels();
            loadInstalledModels();
        }

        // Load Storage Information
        function loadStorageInfo() {
            fetch('/api/models-directory-size')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('total-storage').textContent = `${data.total_size_gb} GB`;
                })
                .catch(error => {
                    console.error('Failed to load storage info:', error);
                    document.getElementById('total-storage').textContent = 'Error';
                });
        }

        // Load Available Models
        function loadAvailableModels() {
            const container = document.getElementById('available-models-list');
            container.innerHTML = '<div class="loading-spinner">Loading available models...</div>';

            fetch('/api/available-vosk-models')
                .then(response => response.json())
                .then(models => {
                    container.innerHTML = '';
                    
                    const availableModels = models.filter(m => !m.installed && !m.downloading);
                    
                    if (availableModels.length === 0) {
                        container.innerHTML = `
                            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--glass-text);">
                                <div style="font-size: 48px; margin-bottom: 15px;">✅</div>
                                <div>All available models are installed!</div>
                            </div>
                        `;
                        return;
                    }

                    availableModels.forEach(model => {
                        const card = createModelCard(model, 'available');
                        container.appendChild(card);
                    });

                    // Update installed count
                    const installedCount = models.filter(m => m.installed).length;
                    document.getElementById('installed-count').textContent = `${installedCount} models`;
                })
                .catch(error => {
                    console.error('Failed to load available models:', error);
                    container.innerHTML = `
                        <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #ff6b6b;">
                            <div style="font-size: 48px; margin-bottom: 15px;">❌</div>
                            <div>Failed to load models: ${error.message}</div>
                        </div>
                    `;
                });
        }

        // Load Installed Models
        function loadInstalledModels() {
            const container = document.getElementById('installed-models-list');
            container.innerHTML = '<div class="loading-spinner">Loading installed models...</div>';

            fetch('/api/vosk-models')
                .then(response => response.json())
                .then(models => {
                    container.innerHTML = '';

                    if (models.length === 0) {
                        container.innerHTML = `
                            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--glass-text);">
                                <div style="font-size: 48px; margin-bottom: 15px;">📦</div>
                                <div>No models installed yet. Go to "Available Models" to download some!</div>
                            </div>
                        `;
                        return;
                    }

                    models.forEach(model => {
                        const card = createModelCard(model, 'installed');
                        container.appendChild(card);
                    });
                })
                .catch(error => {
                    console.error('Failed to load installed models:', error);
                    container.innerHTML = `
                        <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #ff6b6b;">
                            <div style="font-size: 48px; margin-bottom: 15px;">❌</div>
                            <div>Failed to load models: ${error.message}</div>
                        </div>
                    `;
                });
        }

        // Create Model Card
        function createModelCard(model, type) {
            const card = document.createElement('div');
            card.className = 'model-card glow-effect';
            card.dataset.modelName = model.name;

            const isInstalled = type === 'installed';
            const statusClass = isInstalled ? 'installed' : 'available';
            const statusText = isInstalled ? 'Installed' : 'Available';

            card.innerHTML = `
                <div class="model-card-header">
                    <div class="model-card-title">
                        <div class="model-name">${model.name}</div>
                        <span class="model-language">${model.language}</span>
                    </div>
                    <div class="model-status ${statusClass}">
                        <span>${isInstalled ? '✓' : '↓'}</span>
                        ${statusText}
                    </div>
                </div>
                <div class="model-description">${model.description || `Speech recognition model for ${model.language}`}</div>
                <div class="model-info">
                    <div class="model-info-item">
                        <span>💾</span>
                        ${model.size || 'Unknown'}
                    </div>
                </div>
                <div class="model-actions">
                    ${isInstalled ? `
                        <button class="model-btn model-btn-delete" onclick="deleteModel('${model.name}')" ${model.name === 'vosk-model-small-cn-0.22' ? 'disabled' : ''}>
                            <span>🗑️</span> Delete
                        </button>
                    ` : `
                        <button class="model-btn model-btn-download" onclick="downloadModel('${model.name}')">
                            <span>⬇️</span> Download
                        </button>
                    `}
                </div>
                <div class="download-progress" style="display: none;"></div>
            `;

            return card;
        }

        // Download Model
        function downloadModel(modelName) {
            const card = document.querySelector(`.model-card[data-model-name="${modelName}"]`);
            if (!card) return;

            const downloadBtn = card.querySelector('.model-btn-download');
            const progressContainer = card.querySelector('.download-progress');

            // Update button state
            downloadBtn.disabled = true;
            downloadBtn.innerHTML = '<span>⏳</span> Starting...';

            // Show progress container
            progressContainer.style.display = 'block';
            progressContainer.innerHTML = `
                <div class="progress-bar">
                    <div class="progress-fill" style="width: 0%"></div>
                </div>
                <div class="progress-info">
                    <span>Connecting...</span>
                    <span>0%</span>
                </div>
            `;

            fetch('/api/download-model', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ model_name: modelName })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'started') {
                    showToast('success', 'Download Started', `Downloading ${modelName}...`);
                    startProgressPolling(modelName);
                } else {
                    throw new Error(data.error || 'Failed to start download');
                }
            })
            .catch(error => {
                console.error('Download failed:', error);
                showToast('error', 'Download Failed', error.message);
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<span>⬇️</span> Download';
                progressContainer.style.display = 'none';
            });
        }

        // Start Progress Polling
        function startProgressPolling(modelName) {
            const pollInterval = setInterval(() => {
                fetch(`/api/download-progress/${modelName}`)
                    .then(response => {
                        if (response.status === 404) {
                            clearInterval(pollInterval);
                            return null;
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (!data) {
                            // Download completed or failed
                            loadModelData();
                            clearInterval(pollInterval);
                            return;
                        }

                        const card = document.querySelector(`.model-card[data-model-name="${modelName}"]`);
                        if (!card) {
                            clearInterval(pollInterval);
                            return;
                        }

                        const progressContainer = card.querySelector('.download-progress');
                        const progressFill = progressContainer.querySelector('.progress-fill');
                        const progressInfo = progressContainer.querySelector('.progress-info');

                        if (data.status === 'downloading') {
                            const progress = data.progress || 0;
                            const downloadedMB = (data.downloaded / (1024 * 1024)).toFixed(1);
                            const totalMB = (data.total / (1024 * 1024)).toFixed(1);

                            progressFill.style.width = `${progress}%`;
                            progressInfo.innerHTML = `
                                <span>${downloadedMB} MB / ${totalMB} MB (${data.speed.toFixed(1)} MB/s)</span>
                                <span>${progress.toFixed(0)}%</span>
                            `;
                        } else if (data.status === 'extracting') {
                            progressInfo.innerHTML = '<span>Extracting files...</span><span>90%</span>';
                        } else if (data.status === 'completed') {
                            showToast('success', 'Download Complete', `${modelName} has been installed successfully!`);
                            clearInterval(pollInterval);
                            loadModelData();
                        } else if (data.status === 'error') {
                            showToast('error', 'Download Failed', data.error);
                            clearInterval(pollInterval);
                            loadModelData();
                        }
                    })
                    .catch(error => {
                        console.error('Progress polling failed:', error);
                        clearInterval(pollInterval);
                    });
            }, 500);
        }

        // Delete Model
        function deleteModel(modelName) {
            if (!confirm(`Are you sure you want to delete ${modelName}? This action cannot be undone.`)) {
                return;
            }

            showToast('warning', 'Deleting Model', `Deleting ${modelName}...`);

            fetch('/api/delete-model', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ model_name: modelName })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showToast('success', 'Model Deleted', `${modelName} has been deleted successfully`);
                    loadModelData();
                } else {
                    throw new Error(data.error || 'Failed to delete model');
                }
            })
            .catch(error => {
                console.error('Delete failed:', error);
                showToast('error', 'Delete Failed', error.message);
            });
        }

        // Initialize page
        document.addEventListener('DOMContentLoaded', () => {
            // Add page container to recognition page
            const recognitionContent = document.querySelector('.results');
            if (recognitionContent && !recognitionContent.closest('.page-container')) {
                const pageContainer = document.createElement('div');
                pageContainer.className = 'page-container';
                pageContainer.id = 'page-recognition';
                pageContainer.style.display = 'block';
                
                // Move recognition content into page container
                const parent = recognitionContent.parentElement;
                parent.insertBefore(pageContainer, recognitionContent);
                pageContainer.appendChild(recognitionContent);
            }
            
            // Load translation styles
            loadTranslationStyles();
        });

        // vLLM Download Functionality
        let currentVLLMDownloadSource = localStorage.getItem('vllmDownloadSource') || 'hf-mirror';

        function setVLLMDownloadSource(source) {
            currentVLLMDownloadSource = source;
            localStorage.setItem('vllmDownloadSource', source);
            
            const sourceNames = {
                'huggingface': 'HuggingFace Official',
                'hf-mirror': 'HF-Mirror (China)',
                'modelscope': 'ModelScope'
            };
            
            document.querySelectorAll('[id^="vllm-source-"]').forEach(btn => {
                btn.classList.remove('active');
            });
            
            const activeBtn = document.getElementById(`vllm-source-${source}`);
            if (activeBtn) {
                activeBtn.classList.add('active');
            }
            
            document.getElementById('vllm-source-desc').textContent = `Using ${sourceNames[source]} - ${source === 'hf-mirror' ? 'Recommended for China users' : 'Official source'}`;
            showToast('info', 'Download Source Changed', `Switched to ${sourceNames[source]}`);
        }

        // Test download source speed
        async function testVLLMDownloadSources() {
            const testBtn = document.getElementById('test-vllm-sources-btn');
            if (testBtn) {
                testBtn.disabled = true;
                testBtn.textContent = '📊 测试中...';
            }

            showToast('info', 'Testing Sources', 'Testing download source speeds...');

            try {
                const response = await fetch('/api/vllm-models/test-sources');
                const data = await response.json();

                if (response.ok) {
                    displayVLLMSourceTestResults(data);
                } else {
                    showToast('error', 'Test Failed', data.error || 'Failed to test sources');
                }
            } catch (error) {
                console.error('Error testing sources:', error);
                showToast('error', 'Test Error', error.message);
            } finally {
                if (testBtn) {
                    testBtn.disabled = false;
                    testBtn.textContent = '📊 测试下载源';
                }
            }
        }

        // Display source test results
        function displayVLLMSourceTestResults(data) {
            const resultsDiv = document.getElementById('vllm-source-test-results');
            if (!resultsDiv) return;

            let html = '<div style="margin-top: 15px; padding: 15px; background: var(--glass-bg); border-radius: 8px; border: 1px solid var(--glass-border);">';
            html += '<h4 style="margin: 0 0 10px 0; color: var(--primary-color);">📊 下载源测试结果</h4>';
            html += '<div style="display: flex; flex-direction: column; gap: 8px;">';

            data.sources.forEach((source, index) => {
                const isRecommended = source.name === data.recommended;
                const statusColor = source.status === 'available' ? '#4CAF50' : 
                                   source.status === 'timeout' ? '#ff9800' : '#f44336';
                const statusIcon = source.status === 'available' ? '✅' : 
                                  source.status === 'timeout' ? '⏱️' : '❌';
                const speedText = source.speed_kbps ? `${source.speed_kbps} KB/s` : 'N/A';
                const recommendBadge = isRecommended ? '<span style="background: #4ECDC4; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 8px;">推荐</span>' : '';

                html += `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 6px; ${isRecommended ? 'border: 1px solid #4ECDC4;' : ''}">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span>${statusIcon}</span>
                            <div>
                                <div style="font-weight: 600;">${source.description}${recommendBadge}</div>
                                <div style="font-size: 12px; color: var(--text-secondary);">${source.endpoint}</div>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="color: ${statusColor}; font-weight: 600;">${source.status === 'available' ? speedText : source.error || source.status}</div>
                            ${source.response_time_ms ? `<div style="font-size: 11px; color: var(--text-secondary);">${source.response_time_ms}ms</div>` : ''}
                        </div>
                    </div>
                `;
            });

            html += '</div>';

            // Add auto-select button
            if (data.recommended) {
                html += `
                    <div style="margin-top: 10px; text-align: center;">
                        <button onclick="setVLLMDownloadSource('${data.recommended}')" class="btn btn-primary" style="padding: 8px 16px; font-size: 13px;">
                            🚀 使用推荐源 (${data.recommended})
                        </button>
                    </div>
                `;
            }

            html += '</div>';
            resultsDiv.innerHTML = html;
            resultsDiv.classList.add('active');

            showToast('success', 'Test Complete', `Recommended source: ${data.recommended || 'None'}`);
        }

        let vllmDownloadInterval = null;

        async function downloadVLLMModelFromSource(source) {
            // Ask user for model ID
            const modelId = prompt('Enter vLLM model ID (e.g., Qwen/Qwen2.5-7B-Instruct):');
            if (!modelId) return;

            const progressDiv = document.getElementById('vllm-download-progress');
            progressDiv.innerHTML = `
                <div class="progress-info">Downloading ${modelId} from ${source}...</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: 0%"></div>
                </div>
                <div class="progress-info" id="vllm-progress-details">Starting download...</div>
            `;
            progressDiv.classList.add('active');

            try {
                const response = await fetch('/api/vllm/download', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model_id: modelId,
                        source: source
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to start download');
                }

                const result = await response.json();
                const taskId = result.task_id;

                // Start polling for progress
                vllmDownloadInterval = setInterval(async () => {
                    try {
                        const progressResponse = await fetch(`/api/vllm/download-progress/${taskId}`);
                        
                        if (progressResponse.status === 404) {
                            clearInterval(vllmDownloadInterval);
                            progressDiv.innerHTML = `
                                <div class="progress-info" style="color: var(--success-color);">Download completed successfully!</div>
                            `;
                            showToast('success', 'Download Complete', `${modelId} downloaded successfully`);
                            loadInstalledVLLMModels();
                            return;
                        }

                        const progress = await progressResponse.json();
                        
                        if (progress.status === 'error') {
                            clearInterval(vllmDownloadInterval);
                            progressDiv.innerHTML = `
                                <div class="progress-info" style="color: var(--error-color);">Error: ${progress.error}</div>
                            `;
                            showToast('error', 'Download Failed', progress.error);
                            return;
                        }

                        // Update progress
                        const progressFill = progressDiv.querySelector('.progress-fill');
                        const progressDetails = progressDiv.querySelector('#vllm-progress-details');
                        
                        if (progressFill && progressDetails) {
                            const percentage = Math.round((progress.downloaded / progress.total) * 100);
                            progressFill.style.width = `${percentage}%`;
                            progressDetails.textContent = `Downloaded ${formatFileSize(progress.downloaded)} of ${formatFileSize(progress.total)} (${percentage}%)`;
                        }

                    } catch (error) {
                        console.error('Progress poll error:', error);
                    }
                }, 1000);

            } catch (error) {
                console.error('Download error:', error);
                progressDiv.innerHTML = `
                    <div class="progress-info" style="color: var(--error-color);">Error: ${error.message}</div>
                `;
                showToast('error', 'Download Failed', error.message);
            }
        }

        async function loadInstalledVLLMModels() {
            try {
                const response = await fetch('/api/vllm/models');
                const models = await response.json();
                
                const container = document.getElementById('installed-vllm-models');
                if (!container) return;
                
                if (models.length === 0) {
                    container.innerHTML = '<div class="no-models">No vLLM models installed yet</div>';
                    document.getElementById('installed-vllm-count').textContent = '(0)';
                    return;
                }
                
                document.getElementById('installed-vllm-count').textContent = `(${models.length})`;
                
                container.innerHTML = models.map(model => `
                    <div class="model-item">
                        <div class="model-item-name">${model.name}</div>
                        <div class="model-item-meta">Size: ${formatFileSize(model.size)}</div>
                        <div class="model-item-actions">
                            <button onclick="useVLLMModel('${model.name}')" class="btn btn-secondary btn-small">Use</button>
                            <button onclick="deleteVLLMModel('${model.name}')" class="btn btn-danger btn-small">Delete</button>
                        </div>
                    </div>
                `).join('');
            } catch (error) {
                console.error('Failed to load installed models:', error);
            }
        }

        function useVLLMModel(modelName) {
            document.getElementById('model-select').value = modelName;
            showToast('success', 'Model Selected', `Using ${modelName}`);
        }

        async function deleteVLLMModel(modelName) {
            if (!confirm(`Delete model ${modelName}?`)) return;
            
            try {
                const response = await fetch(`/api/vllm/delete/${encodeURIComponent(modelName)}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    showToast('success', 'Deleted', `Model ${modelName} deleted`);
                    loadInstalledVLLMModels();
                } else {
                    const error = await response.json();
                    showToast('error', 'Error', error.error || 'Failed to delete model');
                }
            } catch (error) {
                console.error('Delete error:', error);
                showToast('error', 'Error', 'Failed to delete model');
            }
        }

        // Test download sources availability with speed test
        async function testDownloadSources() {
            const resultsDiv = document.getElementById('source-test-results');
            resultsDiv.innerHTML = '<div class="loading-spinner">Testing download sources...</div>';
            resultsDiv.classList.add('active');

            showToast('info', 'Testing Sources', 'Testing download source speeds...');

            try {
                const response = await fetch('/api/vllm-models/test-sources');
                const data = await response.json();

                if (response.ok) {
                    // Display detailed results with speed
                    resultsDiv.innerHTML = `
                        <div style="margin-bottom: 10px; font-weight: 600; color: var(--primary-color);">
                            📊 Download Source Speed Test Results
                        </div>
                        ${data.sources.map(source => {
                            const isRecommended = source.name === data.recommended;
                            const statusClass = source.status === 'available' ? 'available' : 'unavailable';
                            const statusText = source.status === 'available' ? 
                                `✓ ${source.speed_kbps} KB/s (${source.response_time_ms}ms)` : 
                                `✗ ${source.error || source.status}`;
                            const recommendBadge = isRecommended ? 
                                '<span style="background: #4ECDC4; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 8px;">推荐</span>' : '';
                            
                            return `
                                <div class="source-test-item" style="${isRecommended ? 'border: 1px solid #4ECDC4; border-radius: 4px; padding: 4px;' : ''}">
                                    <span>${source.description}${recommendBadge}</span>
                                    <span class="source-test-status ${statusClass}">${statusText}</span>
                                </div>
                            `;
                        }).join('')}
                        ${data.recommended ? `
                            <div style="margin-top: 10px; text-align: center;">
                                <button onclick="setVLLMDownloadSource('${data.recommended}')" class="btn btn-primary" style="padding: 6px 12px; font-size: 12px;">
                                    🚀 使用推荐源
                                </button>
                            </div>
                        ` : ''}
                    `;
                    showToast('success', 'Test Complete', `Recommended: ${data.recommended || 'None'}`);
                } else {
                    throw new Error(data.error || 'Failed to test sources');
                }
            } catch (error) {
                console.error('Error testing sources:', error);
                resultsDiv.innerHTML = `<div style="color: #f44336;">Error: ${error.message}</div>`;
                showToast('error', 'Test Error', error.message);
            }
        }

        // Test function to verify JavaScript is working
        console.log('Script loaded successfully. JavaScript is working!');

        // FRP Management
        let frpTunnels = [];
        let frpOutputPollInterval = null;
        let isFRPRunning = false;

        async function loadFRPTunnels() {
            try {
                const response = await fetch('/api/frp/tunnels');
                if (response.ok) {
                    const data = await response.json();
                    frpTunnels = data.tunnels || [];
                    isFRPRunning = data.is_running || false;
                    renderFRPTunnels();
                }
            } catch (error) {
                console.error('Failed to load FRP tunnels:', error);
            }
        }

        function renderFRPTunnels() {
            const tunnelList = document.getElementById('tunnel-list');
            if (!tunnelList) return;

            const langData = languages[currentLanguage]?.app || {};
            const frpLang = langData.frp || {};

            if (frpTunnels.length === 0) {
                tunnelList.innerHTML = `<div class="no-tunnels">${frpLang.noTunnels || 'No tunnels saved yet. Add a new tunnel to get started.'}</div>`;
                return;
            }

            tunnelList.innerHTML = frpTunnels.map(tunnel => `
                <div class="tunnel-item">
                    <div class="tunnel-info">
                        <h4>${tunnel.name}</h4>
                        <div class="tunnel-command">${tunnel.command}</div>
                        <div class="tunnel-meta">Created: ${new Date(tunnel.created_at).toLocaleString()}</div>
                    </div>
                    <div class="tunnel-actions">
                        <button class="btn btn-primary btn-small ${isFRPRunning ? 'disabled' : ''}" onclick="startFRPTunnel('${tunnel.id}')">
                            <i class="fas fa-play"></i> ${frpLang.start || 'Start'}
                        </button>
                        <button class="btn btn-secondary btn-small" onclick="deleteFRPTunnel('${tunnel.id}')">
                            <i class="fas fa-trash"></i> ${frpLang.delete || 'Delete'}
                        </button>
                    </div>
                </div>
            `).join('');

            // Add stop button if tunnel is running
            if (isFRPRunning) {
                const tunnelListContainer = tunnelList.parentElement;
                // Remove existing stop button if any
                const existingStopButton = tunnelListContainer.querySelector('.stop-tunnel-container');
                if (existingStopButton) {
                    existingStopButton.remove();
                }
                const stopButton = document.createElement('div');
                stopButton.className = 'stop-tunnel-container';
                stopButton.innerHTML = `
                    <button class="btn btn-danger" onclick="stopFRPTunnel()">
                        <i class="fas fa-stop"></i> ${frpLang.stop || 'Stop'} Running Tunnel
                    </button>
                `;
                tunnelListContainer.appendChild(stopButton);
            }
        }

        async function addTunnel() {
            const langData = languages[currentLanguage]?.app || {};
            const frpLang = langData.frp || {};
            const toastLang = langData.toasts || {};
            
            const tunnelName = document.getElementById('tunnel-name').value.trim();
            const tunnelCommand = document.getElementById('tunnel-command').value.trim();

            if (!tunnelName || !tunnelCommand) {
                showToast('warning', toastLang.warning || 'Warning', 'Please enter both tunnel name and command');
                return;
            }

            try {
                const response = await fetch('/api/frp/tunnels', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: tunnelName,
                        command: tunnelCommand
                    })
                });

                if (response.ok) {
                    const result = await response.json();
                    showToast('success', frpLang.saved || 'Tunnel Added', 'Tunnel added successfully');
                    document.getElementById('tunnel-name').value = '';
                    document.getElementById('tunnel-command').value = '';
                    loadFRPTunnels();
                } else {
                    const error = await response.json();
                    showToast('error', toastLang.error || 'Error', error.error || 'Failed to add tunnel');
                }
            } catch (error) {
                console.error('Failed to add tunnel:', error);
                showToast('error', toastLang.error || 'Error', 'Failed to add tunnel');
            }
        }

        async function startFRPTunnel(tunnelId) {
            const langData = languages[currentLanguage]?.app || {};
            const frpLang = langData.frp || {};
            const toastLang = langData.toasts || {};
            
            try {
                const response = await fetch('/api/frp/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        tunnel_id: tunnelId
                    })
                });

                if (response.ok) {
                    const result = await response.json();
                    showToast('success', frpLang.started || 'Tunnel Started', frpLang.started || 'Tunnel started successfully');
                    isFRPRunning = true;
                    renderFRPTunnels();
                    updateFRPOutput();
                } else {
                    const error = await response.json();
                    showToast('error', toastLang.error || 'Error', error.error || 'Failed to start tunnel');
                }
            } catch (error) {
                console.error('Failed to start tunnel:', error);
                showToast('error', toastLang.error || 'Error', 'Failed to start tunnel');
            }
        }

        async function stopFRPTunnel() {
            const langData = languages[currentLanguage]?.app || {};
            const frpLang = langData.frp || {};
            const toastLang = langData.toasts || {};
            
            try {
                const response = await fetch('/api/frp/stop', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    const result = await response.json();
                    showToast('success', frpLang.stoppedMsg || 'Tunnel Stopped', frpLang.stoppedMsg || 'Tunnel stopped successfully');
                    isFRPRunning = false;
                    renderFRPTunnels();
                    updateFRPOutput();
                } else {
                    const error = await response.json();
                    showToast('error', toastLang.error || 'Error', error.error || 'Failed to stop tunnel');
                }
            } catch (error) {
                console.error('Failed to stop tunnel:', error);
                showToast('error', toastLang.error || 'Error', 'Failed to stop tunnel');
            }
        }

        async function deleteFRPTunnel(tunnelId) {
            const langData = languages[currentLanguage]?.app || {};
            const frpLang = langData.frp || {};
            const toastLang = langData.toasts || {};
            
            if (!confirm('Are you sure you want to delete this tunnel?')) {
                return;
            }

            try {
                const response = await fetch(`/api/frp/tunnels/${tunnelId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    const result = await response.json();
                    showToast('success', frpLang.deleted || 'Tunnel Deleted', frpLang.deleted || 'Tunnel deleted successfully');
                    loadFRPTunnels();
                } else {
                    const error = await response.json();
                    showToast('error', toastLang.error || 'Error', error.error || 'Failed to delete tunnel');
                }
            } catch (error) {
                console.error('Failed to delete tunnel:', error);
                showToast('error', toastLang.error || 'Error', 'Failed to delete tunnel');
            }
        }

        async function updateFRPOutput() {
            try {
                const response = await fetch('/api/frp/output');
                if (response.ok) {
                    const data = await response.json();
                    const output = data.output || [];
                    const isRunning = data.is_running || false;

                    const outputElement = document.getElementById('tunnel-output');
                    if (outputElement) {
                        if (output.length === 0) {
                            outputElement.innerHTML = '<div class="output-placeholder">Tunnel output will appear here...</div>';
                        } else {
                            outputElement.innerHTML = output.map(line => `<div class="output-line">${line}</div>`).join('');
                            outputElement.scrollTop = outputElement.scrollHeight;
                        }
                    }

                    // Update running status
                    isFRPRunning = isRunning;
                }
            } catch (error) {
                console.error('Failed to update FRP output:', error);
            }
        }

        function startFRPOutputPolling() {
            if (frpOutputPollInterval) {
                clearInterval(frpOutputPollInterval);
            }

            frpOutputPollInterval = setInterval(updateFRPOutput, 2000);
        }

        function stopFRPOutputPolling() {
            if (frpOutputPollInterval) {
                clearInterval(frpOutputPollInterval);
                frpOutputPollInterval = null;
            }
        }