// 主界面核心：状态、客户端标识、本地存储、请求、在线连接、加载提示、任务、入口

// 主界面全局状态与路由常量
// 全局状态管理
const state = {
    currentModel: '模型1',  // 当前选择的模型
    modelConfigs: {},      // 模型配置信息
    initRanges: {},        // 初始值范围
    trackPoints: [],       // 跟踪点列表
    animationData: null,  // 动画数据
    animTimer: null,       // 动画计时器
    animFrame: 0,         // 当前动画帧
    animPlaying: false,   // 动画播放状态
    clientId: '',         // 服务器分配的客户端号
    clientSessionId: '',  // 当前页面会话标识
    presenceSocket: null, // 前台在线连接
    presenceReconnectTimer: null, // 在线连接重连计时器
    pageClosing: false,   // 页面是否正在关闭
    clientName: '',       // 客户端自定义名称
    lastViz2d: null,       // 最近一次二维斑图数据
    animationRestorePromise: null, // 动画缓存恢复请求
    lastViz3d: null,       // 最近一次三维图数据（懒渲染用）
    rendered3d: false,     // 三维图是否已渲染
    render3dToken: 0,      // 三维图渲染序号，避免旧绘制完成后覆盖新状态
    currentTaskId: null,   // 进行中的任务 ID
    taskCancelRequested: false, // 用户已请求取消
    pollTimer: null,       // 任务状态轮询计时器
};

const MAIN_TAB_PATHS = {
    'tab-2d': '/2d',
    'tab-3d': '/3d',
    'tab-anim': '/animation',
};
const MAIN_PATH_TABS = {
    '/': 'tab-2d',
    '/2d': 'tab-2d',
    '/3d': 'tab-3d',
    '/animation': 'tab-anim',
};

// 访问端标识：令牌、会话 ID 与名称校验
/**
 * 获取访问端令牌
 * 令牌持久保存在浏览器中，用于识别同一访问端
 */
function getClientToken() {
    let token = localStorage.getItem('client_token') || localStorage.getItem('client_id');
    if (!token) {
        token = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
        localStorage.setItem('client_token', token);
    }
    return token;
}

// 客户端名称支持多语言文字、数字、空格和常见标点，不支持表情及控制字符。
const clientNamePattern = /^[\p{L}\p{N}\p{Zs}.,!?;:'"()[\]{}\-_/\\@#%&+=·，。！？；：、“”‘’（）【】《》、…]+$/u;

function isSupportedClientName(value) {
    return !value || clientNamePattern.test(value);
}

function createClientSessionId() {
    let sessionId = sessionStorage.getItem('client_session_id');
    if (!sessionId) {
        sessionId = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
        sessionStorage.setItem('client_session_id', sessionId);
    }
    return sessionId;
}

// 本地设置持久化
/**
 * 保存本地设置
 * 将当前参数和设置保存到localStorage
 */
function saveSettings() {
    const settings = {
        model: state.currentModel,
        trackPoints: state.trackPoints,
        iterations: $('#iter-value')?.value,
        animStart: $('#anim-start')?.value,
        animEnd: $('#anim-end')?.value,
        animFrames: $('#anim-frames')?.value,
        xMin: $('#x-min')?.value,
        xMax: $('#x-max')?.value,
        yMin: $('#y-min')?.value,
        yMax: $('#y-max')?.value,
        params: Array.from($$('.param-input')).map(inp => inp.value),
    };
    localStorage.setItem('app_settings', JSON.stringify(settings));
}

/**
 * 加载本地设置
 * 从localStorage读取保存的设置
 * @returns {Object|boolean} 设置对象或false
 */
function loadSettings() {
    try {
        const raw = localStorage.getItem('app_settings');
        if (!raw) return false;
        return JSON.parse(raw);
    } catch { return false; }
}

// 主界面 API 请求封装
/**
 * API调用封装
 * @param {string} url - API地址
 * @param {Object} data - 请求数据
 * @returns {Promise} API响应
 */
async function apiCall(url, data) {
    data.client_id = state.clientId;
    data.client_session_id = state.clientSessionId;
    data.lang = i18n.getLang();  // 传当前语言给后端，用于图表标题和日志翻译
    const resp = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify(data),
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || '请求失败');
    return json;
}

// 前台在线连接（WebSocket presence）
/**
 * 前台在线连接：由 WebSocket 连接状态代表页面是否在线。
 */
function startPresenceSocket() {
    const connect = () => {
        if (state.pageClosing) return;
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        let socket;
        try {
            socket = new WebSocket(`${proto}://${location.host}/api/presence`);
        } catch {
            state.presenceReconnectTimer = setTimeout(connect, 3000);
            return;
        }
        state.presenceSocket = socket;
        socket.onopen = () => {
            if (state.pageClosing) {
                socket.close();
                return;
            }
            socket.send(JSON.stringify({
                type: 'presence',
                client_id: state.clientId,
                client_session_id: state.clientSessionId,
                client_name: state.clientName,
                lang: i18n.getLang(),
            }));
        };
        socket.onclose = () => {
            if (state.presenceSocket !== socket || state.pageClosing) return;
            state.presenceReconnectTimer = setTimeout(connect, 3000);
        };
        socket.onerror = () => socket.close();
    };

    window.addEventListener('app-language-changed', (event) => {
        const socket = state.presenceSocket;
        if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'language', lang: event.detail?.lang || i18n.getLang() }));
        }
    });

    window.addEventListener('pagehide', () => {
        state.pageClosing = true;
        clearTimeout(state.presenceReconnectTimer);
        if (state.presenceSocket && state.presenceSocket.readyState < WebSocket.CLOSING) {
            state.presenceSocket.close();
        }
    });
    connect();
}

// 加载遮罩与状态提示
/**
 * 显示加载动画
 * @param {string} text - 加载提示文本
 * @param {boolean} cancellable - 是否显示取消任务按钮
 */
function showLoading(text = '计算中...', cancellable = false) {
    $('#loading-overlay').classList.add('show');
    $('#loading-text').textContent = text;
    $('#loading-cancel').style.display = cancellable ? '' : 'none';
}

/**
 * 隐藏加载动画
 */
function hideLoading() {
    $('#loading-overlay').classList.remove('show');
    $('#loading-cancel').style.display = 'none';
    if (state.pollTimer) {
        clearTimeout(state.pollTimer);
        state.pollTimer = null;
    }
}

/**
 * 设置状态消息
 * @param {string} msg - 消息内容
 * @param {string} type - 消息类型
 */
function setStatus(msg, type = '') {
    const el = $('#status-msg');
    el.textContent = msg;
    el.className = 'status-text status-log-trigger ' + type;
}

function clientStatusStorageKey() {
    return `client_status_notice:${state.clientId || 'pending'}`;
}

function setClientOperationStatus(key, type = 'success', persist = false) {
    setStatus(i18n.t(key), type);
    if (persist) sessionStorage.setItem(clientStatusStorageKey(), JSON.stringify({ key, type }));
}

function restoreClientOperationStatus() {
    try {
        const saved = JSON.parse(sessionStorage.getItem(clientStatusStorageKey()) || 'null');
        if (!saved?.key) return;
        sessionStorage.removeItem(clientStatusStorageKey());
        setStatus(i18n.t(saved.key), saved.type || '');
    } catch { /* 临时状态无效时保持当前状态。 */ }
}

function closeClientTaskLogModal() {
    const modal = $('#client-task-log-modal');
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
}

function summarizeClientTaskLog(entry) {
    const message = String(entry.message || '');
    const matched = message.match(/^\[([^\]]+)\]\s+\[[^\]]+\]\s+([^：:]+)[：:]/);
    if (!matched) return message;
    const time = matched[1].match(/\d{2}:\d{2}:\d{2}$/)?.[0] || matched[1];
    return `${time} · ${matched[2]}`;
}

// 主界面任务日志与左下角状态提示共用这套颜色语义。
const CLIENT_TASK_LOG_TONES = {
    task_completed: 'success',
    task_failed: 'error',
    task_dead_letter: 'error',
    task_timeout: 'error',
    task_dispatch_failed: 'error',
    task_result_persist_failed: 'error',
    task_result_release_failed: 'error',
    task_queued: 'info',
    task_started: 'info',
    task_retry: 'info',
    task_dead_retry: 'info',
    dead_task_retry: 'info',
    task_cancel_requested: 'info',
    task_cancelled: 'info',
    task_cancel_action: 'info',
    task_submit: 'info',
    task_result_expired: 'info',
    task_result_memory_pending: 'info',
};

function clientTaskLogTone(entry) {
    const action = String(entry?.action || '');
    if (CLIENT_TASK_LOG_TONES[action]) return CLIENT_TASK_LOG_TONES[action];
    const message = String(entry?.message || '');
    if (message.includes('[ERROR]')) return 'error';
    if (message.includes('[WARNING]')) return 'error';
    return '';
}

async function openClientTaskLogModal() {
    const modal = $('#client-task-log-modal');
    const stream = $('#client-task-log-stream');
    window.restoreClientTaskLogModalPosition?.();
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    stream.textContent = i18n.t('client_task_log_loading');
    try {
        const response = await fetch(`/api/client-task-logs?client_id=${encodeURIComponent(state.clientId)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '加载失败');
        const entries = data.entries || [];
        stream.innerHTML = entries.length
            ? entries.map(entry => {
                const tone = clientTaskLogTone(entry);
                const toneClass = tone ? ` ${tone}` : '';
                return `<div class="task-log-line${toneClass}">${esc(summarizeClientTaskLog(entry))}</div>`;
            }).join('')
            : `<div class="task-log-empty">${esc(i18n.t('client_task_log_empty'))}</div>`;
        stream.scrollTop = stream.scrollHeight;
    } catch {
        stream.innerHTML = `<div class="task-log-empty">${esc(i18n.t('client_task_log_empty'))}</div>`;
    }
}

// 任务提交、轮询、取消与模拟运行
// 队列位置从 1 开始，提示文案需要的是当前任务前面的数量。
function queueAheadCount(position) {
    return Math.max(0, Number(position || 0) - 1);
}

/**
 * 提交任务并轮询直至完成
 * @param {string} url - 提交端点
 * @param {Object} payload - 任务参数
 * @returns {Promise<Object>} 任务结果
 */
async function submitAndPoll(url, payload) {
    payload.client_notifications = clientTaskNotificationPayload();
    const resp = await apiCall(url, payload);
    state.currentTaskId = resp.task_id;
    state.taskCancelRequested = false;
    if (resp.paused) showToast(i18n.t('task_paused'), 'info');
    showLoading(i18n.t('task_queued', { n: queueAheadCount(resp.queue_position) }), true);
    return pollTask(resp.task_id);
}

/**
 * 轮询任务状态：执行中 1 秒一次，排队中 3 秒一次
 * @param {string} taskId - 任务 ID
 * @returns {Promise<Object>} 任务结果
 */
function pollTask(taskId) {
    return new Promise((resolve, reject) => {
        async function poll() {
            if (state.taskCancelRequested) {
                reject(new Error(i18n.t('task_cancelled')));
                return;
            }
            try {
                const resp = await fetch(`/api/task/${taskId}`);
                const task = await resp.json();
                if (!resp.ok) throw new Error(task.error || i18n.t('task_not_found'));
                if (task.status === 'queued') {
                    showLoading(i18n.t('task_queued', { n: queueAheadCount(task.queue_position) }), true);
                    state.pollTimer = setTimeout(poll, 1000);
                } else if (task.status === 'running') {
                    showLoading(i18n.t('task_running', { p: task.progress ?? 0 }), true);
                    state.pollTimer = setTimeout(poll, 400);
                } else if (task.status === 'completed') {
                    notifyCurrentClientTask('completed', task);
                    resolve(task.result);
                } else if (task.status === 'cancelled') {
                    notifyCurrentClientTask('cancelled', task);
                    reject(new Error(i18n.t('task_cancelled')));
                } else if (task.status === 'timeout') {
                    notifyCurrentClientTask('timeout', task);
                    reject(new Error(i18n.t('task_timeout_status')));
                } else if (task.status === 'expired') {
                    reject(new Error(i18n.t('task_expired_status')));
                } else {
                    if (task.status === 'failed') notifyCurrentClientTask('failed', task);
                    reject(new Error(task.error || i18n.t('task_failed_status', { msg: task.status })));
                }
            } catch (err) {
                reject(err);
            }
        }
        poll();
    });
}

/**
 * 取消当前任务（由加载遮罩上的取消按钮触发）
 */
async function cancelCurrentTask() {
    const taskId = state.currentTaskId;
    if (!taskId || state.taskCancelRequested) return;
    state.taskCancelRequested = true;
    try {
        await apiCall(`/api/task/${taskId}/cancel`, {});
        hideLoading();
        setClientOperationStatus('status_task_cancel_requested', 'info');
    } catch (err) {
        // 取消失败时继续轮询，任务可能刚好已开始收尾
        state.taskCancelRequested = false;
        showToast(i18n.t('task_cancel_failed', { msg: err.message }), 'error');
    }
}

/**
 * 运行模拟
 * 提交任务并轮询，完成后渲染结果
 */
async function runSimulation() {
    // 如果当前在动画演示页，跳回二维斑图
    if ($('.tab-btn.active')?.dataset?.tab === 'tab-anim') {
        switchTab('tab-2d');
    }

    setStatus(i18n.t('simulating_status'), 'info');

    try {
        const params = getParams();
        const initRanges = getInitRanges();
        const iterations = getIterations();

        const result = await submitAndPoll('/api/simulate', {
            model: state.currentModel,
            params,
            iterations,
            x_min: initRanges.x_min,
            x_max: initRanges.x_max,
            y_min: initRanges.y_min,
            y_max: initRanges.y_max,
            track_points: state.trackPoints,
        });

        // 渲染二维斑图
        state.lastViz2d = result.viz_2d;
        render2DPatterns(result.viz_2d);
        // 三维斑图懒渲染：仅当三维标签可见时立即渲染，否则等切换时再渲染
        state.lastViz3d = result.viz_3d;
        if ($('.tab-btn.active')?.dataset?.tab === 'tab-3d') {
            render3DPattern(result.viz_3d);
        } else {
            state.rendered3d = false;
        }

        setStatus(i18n.t('sim_complete', { model: result.model, iters: result.iterations }), 'success');
        showToast(i18n.t('sim_done'), 'success');
    } catch (err) {
        console.error('模拟失败:', err);
        const cancelled = err.message === i18n.t('task_cancelled');
        if (cancelled) setClientOperationStatus('status_task_cancel_requested', 'info');
        else setStatus(i18n.t('sim_failed', { msg: err.message }), 'error');
        showToast(err.message, cancelled ? 'info' : 'error');
    } finally {
        hideLoading();
        state.currentTaskId = null;
    }
}

// 主界面入口：初始化、缓存恢复与标签恢复
/**
 * 初始化应用
 * 加载配置、恢复设置、初始化UI
 */
async function init() {
    state.clientId = getClientToken();
    state.clientSessionId = createClientSessionId();
    state.clientName = localStorage.getItem('client_name') || '';
    startPresenceSocket();

    try {
        // 同步读取服务端内联配置，刷新首帧即渲染完整侧边栏
        const config = window.INIT_CONFIG;
        if (!config) throw new Error('INIT_CONFIG 缺失');

        state.modelConfigs = config.models;
        state.initRanges = config.init_ranges;
        state.paramNames = config.param_names;

        // 信息卡片：标签按语言翻译（data-i18n，切换语言时自动更新），数值为动态内容
        const info = config.service_info || {};
        const infoRows = [
            ['info_version', config.version],
            ['info_client_id', state.clientId],
            ['info_python', info.python],
            ['info_cuda', info.cuda],
            ['info_pytorch', info.torch],
            ['info_cpu', info.cpu],
            ['info_gpu', info.gpu],
            ['info_hardware', info.hardware],
        ];
        $('#info-grid').innerHTML = infoRows.map(([k, v]) =>
            `<span class="status-k" data-i18n="${k}">${i18n.t(k)}</span><span class="status-v" title="${esc(v)}">${esc(v ?? '-')}</span>`).join('');

        // 构建模型选择器（模型名按语言翻译）
        const select = $('#model-select');
        const optionsBox = select.querySelector('.custom-select-options');
        optionsBox.innerHTML = Object.keys(config.models).map(m =>
            `<div class="custom-select-option" data-value="${m}" data-i18n="model_${m.replace('模型', '')}">${i18n.t('model_' + m.replace('模型', ''))}</div>`
        ).join('');
        syncCustomSelectEmptyState(optionsBox);

        // 恢复本地设置
        const saved = loadSettings();
        if (saved && saved.model) {
            // 保存并设置模型值
            state.currentModel = saved.model;
            setCustomSelectValue(select, saved.model);
        } else {
            // 无保存设置时默认选择第一个模型
            const firstModel = Object.keys(config.models)[0];
            state.currentModel = firstModel;
            setCustomSelectValue(select, firstModel);
        }
        if (saved && saved.trackPoints) state.trackPoints = saved.trackPoints;
        updateTrackList();

        // 加载模型参数面板
        onModelChange();

        // 恢复输入值（必须在onModelChange之后，否则会被覆盖）
        if (saved) {
            if (saved.iterations) { $('#iter-value').value = saved.iterations; $('#iter-range').value = saved.iterations; }
            if (saved.animFrames) $('#anim-frames').value = saved.animFrames;
            if (saved.animStart) $('#anim-start').value = saved.animStart;
            if (saved.animEnd) $('#anim-end').value = saved.animEnd;
            if (saved.xMin) $('#x-min').value = saved.xMin;
            if (saved.xMax) $('#x-max').value = saved.xMax;
            if (saved.yMin) $('#y-min').value = saved.yMin;
            if (saved.yMax) $('#y-max').value = saved.yMax;
            if (saved.params) {
                const inputs = $$('.param-input');
                saved.params.forEach((v, i) => { if (inputs[i]) inputs[i].value = v; });
            }
        }

        // 字体加载完成后再恢复图表，避免字体切换导致页面布局二次变化
        const fontsReady = document.fonts?.ready || Promise.resolve();
        const activeTab = MAIN_PATH_TABS[location.pathname] || sessionStorage.getItem('active_tab') || 'tab-2d';
        const cachedResp = await apiCall('/api/restore', { include_animation: false });
        await fontsReady;
        if (cachedResp.success && cachedResp.cached) {
            const cache = cachedResp.cached;
            if (cache.type === 'simulation' && cache.viz_2d) {
                state.lastViz2d = cache.viz_2d;
                if (activeTab === 'tab-2d') render2DPatterns(cache.viz_2d);
                // 三维图懒渲染：恢复时默认在二维标签，等切换到三维标签时再渲染
                state.lastViz3d = cache.viz_3d || null;
                state.rendered3d = false;
                setStatus(i18n.t('restored_sim'), 'success');
                showToast(i18n.t('restored_toast'));
            }
        } else {
            setStatus(i18n.t('status_ready'));
        }

        restoreClientOperationStatus();

        // 确保跟踪点列表正确显示（无论是否有缓存）
        updateTrackList();

        // 恢复刷新前的标签页位置（三维标签会触发懒渲染）
        restoreTab();
    } catch (err) {
        console.error('初始化失败:', err);
        setStatus(i18n.t('init_failed'), 'error');
    }
}

/**
 * 恢复刷新前的标签页位置
 * 从sessionStorage读取保存的标签并激活，刷新网页不回主页
 */
function restoreTab() {
    if (location.pathname === '/settings') return;
    const saved = MAIN_PATH_TABS[location.pathname] || sessionStorage.getItem('active_tab');
    if (saved && document.getElementById(saved)) {
        switchTab(saved, { replace: true });
    }
}

/**
 * 按需恢复动画缓存，避免二维页面刷新时解析全部动画帧。
 */
async function restoreAnimationCache() {
    if (state.animationData) return;
    if (state.animationRestorePromise) return state.animationRestorePromise;

    state.animationRestorePromise = apiCall('/api/restore', { include_animation: true })
        .then(resp => {
            const animation = resp.cached?.anim?.animation;
            if (!animation) return;

            state.animationData = animation;
            state.animStart = parseInt($('#anim-start').value) || 0;
            state.animFrame = 0;
            state.animPlaying = false;
            $('#anim-slider').max = animation.total_frames - 1;
            $('#anim-slider').value = 0;
            $('#anim-frame-info').textContent = `帧: 0 / ${animation.total_frames}`;

            if ($('.tab-btn.active')?.dataset?.tab === 'tab-anim') {
                renderAnimFrame(0);
                renderAnimEvolution();
            }
        })
        .catch(err => console.error('恢复动画缓存失败:', err))
        .finally(() => { state.animationRestorePromise = null; });

    return state.animationRestorePromise;
}
// 启动应用
document.addEventListener('DOMContentLoaded', () => {
    init();
    bindEvents();
    if (location.pathname === '/settings') $('#software-settings')?.click();
    if (location.pathname === '/pushplus') $('#manage-notification-channels')?.click();
});
