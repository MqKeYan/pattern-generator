// 全局状态管理
const state = {
    currentModel: '模型1',  // 当前选择的模型
    modelConfigs: {},      // 模型配置信息
    initRanges: {},        // 初始值范围
    modelDisplayNames: {}, // 模型显示名称
    trackPoints: [],       // 跟踪点列表
    animationData: null,  // 动画数据
    animTimer: null,       // 动画计时器
    animFrame: 0,         // 当前动画帧
    animPlaying: false,   // 动画播放状态
    clientId: '',         // 客户端ID
    lastViz2d: null,       // 最近一次二维斑图数据
    animationRestorePromise: null, // 动画缓存恢复请求
    lastViz3d: null,       // 最近一次三维图数据（懒渲染用）
    rendered3d: false,     // 三维图是否已渲染
    render3dToken: 0,      // 三维图渲染序号，避免旧绘制完成后覆盖新状态
    zMaxLocked: null,      // z轴最大值锁定值（首次渲染后固定）
};

// DOM元素缓存
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function getPlotTheme() {
    const styles = getComputedStyle(document.documentElement);
    const color = name => styles.getPropertyValue(name).trim();
    const plotText = color('--color-plot-text') || '#ffffff';
    return {
        text: plotText,
        secondary: plotText,
        muted: plotText,
        grid: color('--color-plot-grid') || 'rgba(164, 190, 232, 0.12)',
        axis: color('--color-plot-axis') || '#7a8aa0',
        border: color('--color-border') || 'rgba(164, 190, 232, 0.2)',
    };
}

/**
 * 动画图表首次创建，后续帧更新，避免空容器执行无效react比较。
 */
function renderAnimationPlot(id, data, layout, config) {
    const chart = document.getElementById(id);
    if (chart?._fullLayout) {
        return Plotly.react(chart, data, layout, config);
    }
    return Plotly.newPlot(chart, data, layout, config);
}

/**
 * 获取客户端ID
 * 区分页面刷新和重新打开，确保唯一性
 */
function getClientId() {
    // 使用sessionStorage判断是刷新还是重开
    const isReopen = !sessionStorage.getItem('_active');
    sessionStorage.setItem('_active', '1');

    if (isReopen) {
        // 关闭后重开：清除旧缓存，生成新ID
        localStorage.removeItem('client_id');
        localStorage.removeItem('app_settings');
    }

    let cid = localStorage.getItem('client_id');
    if (!cid) {
        cid = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
        localStorage.setItem('client_id', cid);
    }
    return cid;
}

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

/**
 * 显示提示消息
 * @param {string} msg - 消息内容
 * @param {string} type - 消息类型
 */
function showToast(msg, type = 'info') {
    const container = $('#toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 5000);
}

/**
 * 显示加载动画
 * @param {string} text - 加载提示文本
 */
function showLoading(text = '计算中...') {
    $('#loading-overlay').classList.add('show');
    $('#loading-text').textContent = text;
}

/**
 * 隐藏加载动画
 */
function hideLoading() {
    $('#loading-overlay').classList.remove('show');
}

/**
 * 设置状态消息
 * @param {string} msg - 消息内容
 * @param {string} type - 消息类型
 */
function setStatus(msg, type = '') {
    const el = $('#status-msg');
    el.textContent = msg;
    el.className = 'status-text ' + type;
}

/**
 * API调用封装
 * @param {string} url - API地址
 * @param {Object} data - 请求数据
 * @returns {Promise} API响应
 */
async function apiCall(url, data) {
    data.client_id = state.clientId;
    data.lang = i18n.lang;  // 传语言给后端，用于图表标题翻译
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || '请求失败');
    return json;
}

/**
 * 设置自定义下拉组件的选中值
 * @param {Element} customSelect - 自定义下拉组件
 * @param {string} value - 选中的值
 */
function setCustomSelectValue(customSelect, value) {
    const optionItems = customSelect.querySelectorAll('.custom-select-option');
    const selectedText = customSelect.querySelector('.selected-text');
    const target = customSelect.querySelector(`.custom-select-option[data-value="${value}"]`);
    if (target) {
        optionItems.forEach(opt => opt.classList.remove('selected'));
        target.classList.add('selected');
        selectedText.textContent = target.textContent;
        customSelect.value = value;
    }
}

/**
 * 绑定自定义下拉组件事件
 * @param {Element} customSelect - 自定义下拉组件
 */
function bindCustomSelect(customSelect) {
    if (customSelect.dataset.bound) return;
    customSelect.dataset.bound = '1';

    const trigger = customSelect.querySelector('.custom-select-trigger');
    const options = customSelect.querySelector('.custom-select-options');
    const optionItems = customSelect.querySelectorAll('.custom-select-option');
    const selectedText = trigger.querySelector('.selected-text');
    // 记录触发器引用（options 移入 body 后，关闭时需用它移除 active 类）
    options._trigger = trigger;

    // 打开下拉：移入 body 脱离卡片 stacking context，fixed 定位到触发器下方
    function openOptions() {
        document.body.appendChild(options);
        const rect = trigger.getBoundingClientRect();
        options.style.position = 'fixed';
        options.style.left = rect.left + 'px';
        options.style.top = (rect.bottom + 4) + 'px';
        options.style.width = rect.width + 'px';
        options.style.maxHeight = (window.innerHeight - rect.bottom - 8) + 'px';
        options.style.marginTop = '0';
        options.classList.add('show');
        trigger.classList.add('active');
    }

    // 关闭下拉
    function closeOptions() {
        options.classList.remove('show');
        trigger.classList.remove('active');
    }

    // 点击触发器显示/隐藏选项
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        // 关闭其他下拉
        $$('.custom-select-options.show').forEach(otherOptions => {
            if (otherOptions !== options) {
                otherOptions.classList.remove('show');
                if (otherOptions._trigger) otherOptions._trigger.classList.remove('active');
            }
        });
        if (options.classList.contains('show')) closeOptions();
        else openOptions();
    });

    // 点击选项
    optionItems.forEach(option => {
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            // 更新选中状态
            optionItems.forEach(opt => opt.classList.remove('selected'));
            option.classList.add('selected');
            // 更新显示文本
            selectedText.textContent = option.textContent;
            // 触发 change 事件
            customSelect.value = option.dataset.value;
            customSelect.dispatchEvent(new Event('change'));
            closeOptions();
        });
    });

    // 滚动时关闭（fixed 位置基于视口，滚动后位置会错位）
    window.addEventListener('scroll', () => {
        if (options.classList.contains('show')) closeOptions();
    }, true);
}

/**
 * 初始化所有自定义下拉组件
 */
function initCustomSelect() {
    $$('.custom-select').forEach(bindCustomSelect);
    // 点击外部关闭所有下拉
    document.addEventListener('click', () => {
        $$('.custom-select-options.show').forEach(options => {
            options.classList.remove('show');
            if (options._trigger) options._trigger.classList.remove('active');
        });
    });
}

/**
 * 初始化应用
 * 加载配置、恢复设置、初始化UI
 */
async function init() {
    state.clientId = getClientId();

    try {
        // 同步读取服务端内联配置，刷新首帧即渲染完整侧边栏
        const config = window.INIT_CONFIG;
        if (!config) throw new Error('INIT_CONFIG 缺失');

        state.modelConfigs = config.models;
        state.initRanges = config.init_ranges;
        state.paramNames = config.param_names;
        state.modelDisplayNames = config.display_names || {};

        // 硬件信息：去掉 GPU:/CPU: 前缀，统一显示"计算硬件: 型号"
        $('#hardware-badge').textContent = '计算硬件: ' + config.hardware_info.replace(/^(GPU|CPU):\s*/, '');

        // 客户端名称
        $('#client-badge').textContent = '客户端: ' + state.clientId;

        // 构建模型选择器（模型名按语言翻译）
        const select = $('#model-select');
        const optionsBox = select.querySelector('.custom-select-options');
        optionsBox.innerHTML = Object.keys(config.models).map(m =>
            `<div class="custom-select-option" data-value="${m}" data-i18n="model_${m.replace('模型', '')}">${i18n.t('model_' + m.replace('模型', ''))}</div>`
        ).join('');

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
        const activeTab = sessionStorage.getItem('active_tab') || 'tab-2d';
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
    const saved = sessionStorage.getItem('active_tab');
    if (saved && document.getElementById(saved)) {
        switchTab(saved);
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
            state.animEnd = parseInt($('#anim-end').value) || animation.total_frames;
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

/**
 * 模型切换处理
 * 更新参数面板和初始值设置
 */
function onModelChange() {
    const model = $('#model-select').value;
    state.currentModel = model;
    const cfg = state.modelConfigs[model];
    const initRange = state.initRanges[model];

    // 更新参数
    renderParams(cfg.params, cfg.defaults);

    // 更新初始值
    $('#x-min').value = initRange.x_range[0];
    $('#x-max').value = initRange.x_range[1];
    $('#y-min').value = initRange.y_range[0];
    $('#y-max').value = initRange.y_range[1];
    $('#init-desc').textContent = initRange.description;

    // 更新迭代次数
    $('#iter-range').min = cfg.min_iterations;
    $('#iter-range').max = cfg.max_iterations;
    $('#iter-range').value = cfg.recommended_iterations;
    $('#iter-value').value = cfg.recommended_iterations;

    // 更新动画设置：让默认迭代次数位于动画中间
    const recommendedIters = cfg.recommended_iterations;
    const animFrames = 300; // 默认帧数
    const halfFrames = Math.floor(animFrames / 2);

    // 计算起始和结束迭代，确保不小于0
    const animStart = Math.max(0, recommendedIters - halfFrames);
    const animEnd = animStart + animFrames;

    // 设置动画默认值
    $('#anim-start').value = animStart;
    $('#anim-end').value = animEnd;
    $('#anim-frames').value = animFrames;
}

/**
 * 渲染参数面板
 * @param {Array} names - 参数名称数组
 * @param {Array} defaults - 默认值数组
 */
function renderParams(names, defaults) {
    const container = $('#params-container');
    container.innerHTML = names.map((name, i) => {
        const cnName = (state.paramNames && state.paramNames[name]) || '';
        return `
        <div class="param-row">
            <span class="param-name">${name} ${cnName}：</span>
            <input type="number" class="num-input param-input" data-index="${i}"
                   value="${defaults[i]}" step="any">
            <button class="param-reset" data-index="${i}" data-default="${defaults[i]}">重置</button>
        </div>`;
    }).join('');

    // 绑定重置按钮
    container.querySelectorAll('.param-reset').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = btn.dataset.index;
            const defVal = btn.dataset.default;
            container.querySelector(`.param-input[data-index="${idx}"]`).value = defVal;
        });
    });
}

/**
 * 获取当前参数值
 * @returns {Array} 参数值数组
 */
function getParams() {
    const inputs = $$('.param-input');
    return Array.from(inputs).map(inp => parseFloat(inp.value) || 0);
}

/**
 * 获取初始值范围
 * @returns {Object} x和y的范围
 */
function getInitRanges() {
    return {
        x_min: parseFloat($('#x-min').value) || 0.5,
        x_max: parseFloat($('#x-max').value) || 1.0,
        y_min: parseFloat($('#y-min').value) || 0.5,
        y_max: parseFloat($('#y-max').value) || 1.0,
    };
}

/**
 * 获取迭代次数
 * @returns {number} 迭代次数
 */
function getIterations() {
    return parseInt($('#iter-value').value) || 9000;
}

/**
 * 添加跟踪点
 * 验证坐标并更新跟踪点列表
 */
function addTrackPoint() {
    const x = parseInt($('#track-x').value);
    const y = parseInt($('#track-y').value);
    if (isNaN(x) || isNaN(y) || x < 0 || x > 99 || y < 0 || y > 99) {
        showToast(i18n.t('point_range_error'), 'error');
        return;
    }
    if (state.trackPoints.some(p => p.x === x && p.y === y)) {
        showToast(i18n.t('point_exists', { x, y }), 'info');
        return;
    }
    // 为跟踪点分配颜色（8 种可选颜色循环使用）
    const colors = ['#2ecc71', '#1abc9c', '#3498db', '#9b59b6', '#e74c3c', '#f39c12', '#e67e22', '#34495e'];
    const colorIndex = state.trackPoints.length % colors.length;
    state.trackPoints.push({ x, y, color: colors[colorIndex] });
    updateTrackList();
}

/**
 * 清除所有跟踪点
 */
function clearTrackPoints() {
    state.trackPoints = [];
    updateTrackList();
}

/**
 * 更新跟踪点列表显示
 */
function updateTrackList() {
    const el = $('#track-list');
    if (state.trackPoints.length === 0) {
        el.textContent = i18n.t('track_list_center');
    } else {
        renderTrackPoints();
    }
}

/**
 * 渲染跟踪点列表
 */
function renderTrackPoints() {
    const el = $('#track-list');
    el.innerHTML = '';
    state.trackPoints.forEach(p => {
        // 确保每个跟踪点都有颜色（兼容旧数据）
        if (!p.color) {
            const colors = ['#2ecc71', '#1abc9c', '#3498db', '#9b59b6', '#e74c3c', '#f39c12', '#e67e22', '#34495e'];
            p.color = colors[state.trackPoints.indexOf(p) % colors.length];
        }
        const li = document.createElement('li');
        li.className = 'track-item';

        // 颜色圆点，与演化曲线颜色一致
        const dot = document.createElement('span');
        dot.className = 'track-dot';
        dot.style.background = p.color;

        const label = document.createElement('span');
        label.className = 'track-label';
        label.textContent = `(${p.x},${p.y})`;

        // 操作按钮：编辑 / 删除
        const ops = document.createElement('span');
        ops.className = 'track-ops';
        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn-outline btn-accent';
        editBtn.textContent = i18n.t('edit');
        editBtn.addEventListener('click', () => startEditTrack(p.id));
        const delBtn = document.createElement('button');
        delBtn.className = 'btn btn-outline btn-danger';
        delBtn.textContent = i18n.t('delete');
        delBtn.addEventListener('click', () => { deleteTrackPoint(p.id); saveSettings(); });
        ops.appendChild(editBtn);
        ops.appendChild(delBtn);

        li.appendChild(dot);
        li.appendChild(label);
        li.appendChild(ops);
        el.appendChild(li);
    });
}

/**
 * 编辑跟踪点
 * 将跟踪点的坐标填入输入框
 */
function startEditTrack(id) {
    const p = state.trackPoints.find(pt => pt.id === id);
    if (!p) return;
    $('#track-x').value = p.x;
    $('#track-y').value = p.y;
    // 删除原跟踪点，添加新跟踪点（保持颜色不变）
    deleteTrackPoint(id);
    saveSettings();
}

/**
 * 删除跟踪点
 * 根据 ID 删除跟踪点
 */
function deleteTrackPoint(id) {
    state.trackPoints = state.trackPoints.filter(p => p.id !== id);
    updateTrackList();
}

/**
 * 运行模拟
 * 发送模拟请求并渲染结果
 */
async function runSimulation() {
    // 如果当前在动画演示页，跳回二维斑图
    if ($('.tab-btn.active')?.dataset?.tab === 'tab-anim') {
        switchTab('tab-2d');
    }

    showLoading(i18n.t('simulating'));
    setStatus(i18n.t('simulating_status'), 'info');

    try {
        const params = getParams();
        const initRanges = getInitRanges();
        const iterations = getIterations();

        const resp = await apiCall('/api/simulate', {
            model: state.currentModel,
            params,
            iterations,
            x_min: initRanges.x_min,
            x_max: initRanges.x_max,
            y_min: initRanges.y_min,
            y_max: initRanges.y_max,
            track_points: state.trackPoints,
            auto_clean: true,
        });

        // 渲染二维斑图
        state.lastViz2d = resp.viz_2d;
        render2DPatterns(resp.viz_2d);
        // 三维斑图懒渲染：仅当三维标签可见时立即渲染，否则等切换时再渲染
        state.lastViz3d = resp.viz_3d;
        if ($('.tab-btn.active')?.dataset?.tab === 'tab-3d') {
            render3DPattern(resp.viz_3d);
        } else {
            state.rendered3d = false;
        }

        setStatus(i18n.t('sim_complete', { model: resp.model, iters: resp.iterations }), 'success');
        showToast(i18n.t('sim_done'), 'success');
    } catch (err) {
        console.error('模拟失败:', err);
        setStatus(i18n.t('sim_failed', { msg: err.message }), 'error');
        showToast(i18n.t('sim_failed', { msg: err.message }), 'error');
    } finally {
        hideLoading();
    }
}

/**
 * 渲染二维斑图
 * 包括X种群、Y种群热力图和合并斑图
 * @param {Object} vizData - 可视化数据
 */
function render2DPatterns(vizData) {
    const colors = getPlotTheme();
    const xPop = vizData['2d_patterns'].x_population;
    const yPop = vizData['2d_patterns'].y_population;
    const combined = vizData.combined_pattern;
    const evolution = vizData.evolution_curves;

    // X种群热力图
    Plotly.newPlot('chart-x-pop', [{
        z: xPop.data,
        type: 'heatmap',
        colorscale: 'Viridis',
        colorbar: { title: i18n.t('density'), len: 0.8 },
    }], {
        title: { text: xPop.title, font: { size: 14, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: true, displayModeBar: false });

    // Y种群热力图
    Plotly.newPlot('chart-y-pop', [{
        z: yPop.data,
        type: 'heatmap',
        colorscale: 'Plasma',
        colorbar: { title: i18n.t('density'), len: 0.8 },
    }], {
        title: { text: yPop.title, font: { size: 14, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: true, displayModeBar: false });

    // 合并斑图
    const xNorm = combined.x_normalized;
    const yNorm = combined.y_normalized;

    Plotly.newPlot('chart-combined', [{
        z: xNorm.map((row, i) => row.map((v, j) => v + yNorm[i][j])),
        type: 'heatmap',
        colorscale: [
            [0, 'rgb(0,30,0)'],
            [0.25, 'rgb(180,0,0)'],
            [0.5, 'rgb(200,180,0)'],
            [0.75, 'rgb(0,180,0)'],
            [1, 'rgb(0,200,200)'],
        ],
        colorbar: { title: i18n.t('density'), len: 0.8 },
    }], {
        title: { text: combined.title, font: { size: 14, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: true, displayModeBar: false });

    // 跟踪点标记（在合并图上）
    if (combined.track_points && combined.track_points.length > 0) {
        const annotations = combined.track_points.map(p => ({
            x: p.y, y: p.x,
            xref: 'x', yref: 'y',
            text: `(${p.x},${p.y})`,
            showarrow: true,
            arrowhead: 0,
            font: { color: '#fff', size: 9 },
            bgcolor: 'rgba(0,0,0,0.7)',
        }));
        Plotly.relayout('chart-combined', { annotations });
    }

    // 时间演化曲线
    const curveTraces = evolution.curves.map(c => ({
        x: c.x,
        y: c.y,
        type: 'scatter',
        mode: 'lines',
        name: c.name,
        line: { color: c.color, width: c.line_width, dash: c.dash },
        visible: c.visible ? true : 'legendonly',
    }));

    Plotly.newPlot('chart-evolution', curveTraces, {
        title: { text: evolution.title, font: { size: 15, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 11 },
        margin: { l: 60, r: 30, t: 40, b: 60 },
        xaxis: { title: i18n.t('iterations_axis'), gridcolor: colors.grid, zeroline: false },
        yaxis: { title: i18n.t('density_axis'), gridcolor: colors.grid, zeroline: false },
        legend: { font: { size: 9 }, bgcolor: 'rgba(0, 0, 0, 0)', bordercolor: colors.border },
        hovermode: 'closest',
    }, { responsive: true, displayModeBar: false });
}

/**
 * 立即结束Plotly底层相机的平滑过渡
 * @param {HTMLElement} chart - 三维图容器
 */
function settle3DCamera(chart) {
    const scene = chart._fullLayout?.scene?._scene;
    const view = scene?.camera?.view;
    if (!view) return;

    const time = view.lastT();
    view.flush(time);
    view.recalcMatrix(time);
    scene.glplot?.redraw?.();
}

/**
 * 渲染三维斑图
 * @param {Object} vizData - 可视化数据
 */
function render3DPattern(vizData) {
    const colors = getPlotTheme();
    const chart = $('#chart-3d');
    const renderToken = ++state.render3dToken;
    const zArr = vizData.z;
    const zMin = Math.min(...zArr.map(r => Math.min(...r)));
    const zMax = Math.max(...zArr.map(r => Math.max(...r)));
    const xEnd = zArr.length - 1;
    const yEnd = zArr[0].length - 1;

    // Z数据归一化到0-100，三轴等物理长度，轴固定不漂移
    const zRange = (zMax - zMin) || 0.001;
    const zScaled = zArr.map(row => row.map(v => (v - zMin) / zRange * 100));
    // Z轴刻度，起点不标避免与XY轴原点重叠
    const zTickVals = [20, 40, 60, 80, 100];
    const zTickText = zTickVals.map(v => (v / 100 * zRange + zMin).toFixed(5));
    // 颜色条刻度覆盖全范围，映射真实值
    const cbarTickVals = [0, 20, 40, 60, 80, 100];
    const cbarTickText = cbarTickVals.map(v => (v / 100 * zRange + zMin).toFixed(7));

    const surfaceTrace = {
        z: zScaled,
        type: 'surface',
        colorscale: 'Viridis',
        colorbar: {
            title: { text: i18n.t('density'), font: { size: 13, color: colors.secondary } },
            tickfont: { size: 13, color: colors.muted },
            tickmode: 'array', tickvals: cbarTickVals, ticktext: cbarTickText,
        },
        contours: {
            z: { show: false },
        },
    };
    // 隐藏曲面只负责绘制底部投影，避免轮廓线出现在真实曲面的其他高度
    const projectionTrace = {
        z: zScaled,
        type: 'surface',
        hidesurface: true,
        showscale: false,
        colorscale: 'Viridis',
        hoverinfo: 'skip',
        contours: {
            z: {
                show: true,
                usecolormap: true,
                highlightcolor: 'rgba(255,255,255,0.4)',
                project: { z: true },
            },
        },
    };
    const trace = [surfaceTrace, projectionTrace];
    const layout = {
        title: { text: vizData.title, font: { size: 15, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        scene: {
            xaxis: {
                title: { text: i18n.t('axis_x'), standoff: 25, font: { size: 15, color: colors.text } },
                showgrid: true, gridcolor: colors.grid, gridwidth: 1,
                color: colors.secondary,
                tickfont: { size: 13, color: colors.muted },
                showline: true, linecolor: colors.axis, linewidth: 3,
                ticks: 'outside', tickcolor: colors.axis, ticklen: 8,
                range: [0, 100], tickangle: 0,
                tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100],
            },
            yaxis: {
                title: { text: i18n.t('axis_y'), standoff: 25, font: { size: 15, color: colors.text } },
                showgrid: true, gridcolor: colors.grid, gridwidth: 1,
                color: colors.secondary,
                tickfont: { size: 13, color: colors.muted },
                showline: true, linecolor: colors.axis, linewidth: 3,
                ticks: 'outside', tickcolor: colors.axis, ticklen: 8,
                range: [0, 100], tickangle: 0,
                tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100],
            },
            zaxis: {
                title: { text: i18n.t('density_axis'), standoff: 25, font: { size: 15, color: colors.text } },
                showgrid: true, gridcolor: colors.grid, gridwidth: 1,
                color: colors.secondary,
                tickfont: { size: 13, color: colors.muted },
                showline: true, linecolor: colors.axis, linewidth: 3,
                ticks: 'outside', tickcolor: colors.axis, ticklen: 8,
                range: [0, 100], tickangle: 0,
                // 刻度位置在0-100，标签映射回真实数据值
                tickmode: 'array', tickvals: zTickVals, ticktext: zTickText,
            },
            // 三轴均0-100，aspectratio 1:1:1等物理长度，轴固定不漂移
            aspectmode: 'manual',
            aspectratio: { x: 1, y: 1, z: 1 },
            bgcolor: 'rgba(0, 0, 0, 0)',
            camera: {
                eye: { x: 1.5, y: 1.5, z: 1.2 },
                center: { x: 0, y: 0, z: -0.2 },
            },
        },
        margin: { l: 0, r: 0, t: 40, b: 0 },
    };
    const config = { responsive: true, displayModeBar: false };

    // 等WebGL场景完成绘制后再显示，避免初始化过程中的中间画面抖动
    chart.style.visibility = 'hidden';
    // 每次完整重建WebGL场景，避免react复用旧轮廓投影
    if (chart._fullLayout) Plotly.purge(chart);
    const plotPromise = Plotly.newPlot(chart, trace, layout, config);
    Promise.resolve(plotPromise).then(() => {
        if (renderToken !== state.render3dToken) return;
        // Plotly绘制完成后相机仍可能处于平滑过渡，必须先固定内部矩阵
        settle3DCamera(chart);
        chart.style.visibility = 'visible';
        state.rendered3d = true;
    }).catch(err => {
        if (renderToken !== state.render3dToken) return;
        chart.style.visibility = 'visible';
        state.rendered3d = false;
        console.error('三维图渲染失败:', err);
    });
}

/**
 * 运行动画
 * 生成动画数据并初始化动画界面
 */
async function runAnimation() {
    showLoading(i18n.t('anim_preparing'));

    try {
        const params = getParams();
        const initRanges = getInitRanges();
        const animStart = parseInt($('#anim-start').value) || 0;
        const animEnd = parseInt($('#anim-end').value) || 300;

        // 生成帧数 = 结束 - 起始，动画需要模拟到结束迭代但只存储范围内的帧
        const displayFrames = animEnd - animStart;
        const resp = await apiCall('/api/animate', {
            model: state.currentModel,
            params,
            frames: displayFrames,
            start_frame: animStart,
            x_min: initRanges.x_min,
            x_max: initRanges.x_max,
            y_min: initRanges.y_min,
            y_max: initRanges.y_max,
        });

        state.animationData = resp.animation;
        state.animStart = resp.start_iteration || animStart;
        state.animEnd = animEnd;
        state.animFrame = 0;
        state.animPlaying = false;

        // 设置滑块
        $('#anim-slider').max = resp.animation.total_frames - 1;
        $('#anim-slider').value = 0;
        $('#anim-frame-info').textContent = i18n.t('frame_count', { current: 0, total: resp.animation.total_frames });

        // 渲染第一帧
        renderAnimFrame(0);

        // 渲染中心点时间序列
        renderAnimEvolution();

        hideLoading();
        showToast(i18n.t('anim_ready'), 'success');
        setStatus(i18n.t('anim_ready_status'), 'success');
    } catch (err) {
        console.error('动画准备失败:', err);
        hideLoading();
        showToast(i18n.t('anim_failed', { msg: err.message }), 'error');
        setStatus(i18n.t('anim_failed_status'), 'error');
    }
}

/**
 * 渲染动画帧
 * @param {number} frameIdx - 帧索引
 */
function renderAnimFrame(frameIdx) {
    const colors = getPlotTheme();
    const data = state.animationData;
    const frame = data.frames[frameIdx];
    const displayFrames = data.total_frames;
    const iterNum = (state.animStart || 0) + frameIdx;

    // X种群帧
    renderAnimationPlot('chart-anim-x', [{
        z: frame.x_data,
        type: 'heatmap',
        colorscale: 'Viridis',
        colorbar: { title: i18n.t('density'), len: 0.8 },
    }], {
        title: { text: i18n.t('anim_title_x', { iter: iterNum }), font: { size: 13, color: colors.text } },
        height: 420,
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 10 },
        margin: { l: 40, r: 35, t: 35, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: false, displayModeBar: false });

    // Y种群帧
    renderAnimationPlot('chart-anim-y', [{
        z: frame.y_data,
        type: 'heatmap',
        colorscale: 'Plasma',
        colorbar: { title: i18n.t('density'), len: 0.8 },
    }], {
        title: { text: i18n.t('anim_title_y', { iter: iterNum }), font: { size: 13, color: colors.text } },
        height: 420,
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 10 },
        margin: { l: 40, r: 35, t: 35, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: false, displayModeBar: false });

    // 合并斑图
    const xArr = frame.x_data;
    const yArr = frame.y_data;
    const xMin = Math.min(...xArr.map(r => Math.min(...r)));
    const xMax = Math.max(...xArr.map(r => Math.max(...r)));
    const yMin = Math.min(...yArr.map(r => Math.min(...r)));
    const yMax = Math.max(...yArr.map(r => Math.max(...r)));
    const xNorm = xArr.map(row => row.map(v => (v - xMin) / (xMax - xMin + 1e-10)));
    const yNorm = yArr.map(row => row.map(v => (v - yMin) / (yMax - yMin + 1e-10)));
    const combined = xNorm.map((row, i) => row.map((v, j) => v + yNorm[i][j]));

    renderAnimationPlot('chart-anim-combined', [{
        z: combined,
        type: 'heatmap',
        colorscale: [
            [0, 'rgb(0,30,0)'],
            [0.25, 'rgb(180,0,0)'],
            [0.5, 'rgb(200,180,0)'],
            [0.75, 'rgb(0,180,0)'],
            [1, 'rgb(0,200,200)'],
        ],
        colorbar: { title: i18n.t('density'), len: 0.8 },
    }], {
        title: { text: i18n.t('anim_title_combined', { iter: iterNum }), font: { size: 13, color: colors.text } },
        height: 420,
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 10 },
        margin: { l: 40, r: 35, t: 35, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: false, displayModeBar: false });

    $('#anim-slider').value = frameIdx;
    $('#anim-frame-info').textContent = i18n.t('frame_count', { current: frameIdx, total: displayFrames });
}

/**
 * 渲染动画演化曲线
 */
function renderAnimEvolution() {
    const colors = getPlotTheme();
    const data = state.animationData;
    const cs = data.center_series;

    // 使用实际的起始迭代次数调整时间轴
    const actualStartTime = state.animStart || 0;
    const adjustedTime = cs.time.map(t => t + actualStartTime);

    renderAnimationPlot('chart-anim-evo', [
        { x: adjustedTime, y: cs.x, type: 'scatter', mode: 'lines', name: i18n.t('center_x'),
          line: { color: '#3498DB', width: 2 } },
        { x: adjustedTime, y: cs.y, type: 'scatter', mode: 'lines', name: i18n.t('center_y'),
          line: { color: '#E74C3C', width: 2 } },
    ], {
        title: { text: i18n.t('center_evo_title'), font: { size: 13, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: 10 },
        margin: { l: 50, r: 20, t: 35, b: 60 },
        xaxis: {
            title: i18n.t('iterations_axis'),
            gridcolor: colors.grid,
            // 设置x轴范围，显示从起始迭代到结束迭代的完整范围
            range: [actualStartTime, actualStartTime + cs.time.length - 1]
        },
        yaxis: { title: i18n.t('density_axis'), gridcolor: colors.grid },
        legend: { font: { size: 9 }, bgcolor: 'rgba(0, 0, 0, 0)', bordercolor: colors.border },
    }, { responsive: true, displayModeBar: false });
}

/**
 * 播放动画
 */
function playAnimation() {
    if (!state.animationData) {
        showToast(i18n.t('need_anim'), 'error');
        return;
    }
    if (state.animPlaying) return;

    state.animPlaying = true;
    const speed = parseInt($('#anim-speed').value) || 200;
    const totalFrames = state.animationData.total_frames;

    function tick() {
        if (!state.animPlaying) return;

        renderAnimFrame(state.animFrame);
        state.animFrame++;
        if (state.animFrame >= totalFrames) state.animFrame = 0;

        state.animTimer = setTimeout(tick, speed);
    }
    tick();
}

/**
 * 暂停动画
 */
function pauseAnimation() {
    state.animPlaying = false;
    if (state.animTimer) {
        clearTimeout(state.animTimer);
        state.animTimer = null;
    }
}

/**
 * 切换标签页
 * @param {string} tabId - 标签页ID
 */
function switchTab(tabId) {
    // 记录当前标签，刷新后保持原位置
    sessionStorage.setItem('active_tab', tabId);

    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));

    const btn = document.querySelector(`[data-tab="${tabId}"]`);
    const panel = document.getElementById(tabId);
    if (btn) btn.classList.add('active');
    if (panel) panel.classList.add('active');

    // 三维标签首次可见时懒渲染（容器尺寸正确，避免左上角放大过渡）
    if (tabId === 'tab-3d' && state.lastViz3d && !state.rendered3d) {
        render3DPattern(state.lastViz3d);
    }

    // 二维斑图只在进入二维标签时恢复，动画页刷新不提前绘制二维图表
    if (tabId === 'tab-2d' && state.lastViz2d && !$('#chart-x-pop')._fullLayout) {
        render2DPatterns(state.lastViz2d);
    }

    // 动画缓存按需加载，避免初始恢复阻塞二维页面
    if (tabId === 'tab-anim' && !state.animationData) {
        restoreAnimationCache();
    }

    // 切换后触发所有图表resize（三维图除外：WebGL自动适配，resize反而引起画布重建闪烁）
    setTimeout(() => {
        const panel = document.getElementById(tabId);
        if (panel) {
            panel.querySelectorAll('.chart-box').forEach(el => {
                if (el.id !== 'chart-3d') Plotly.Plots.resize(el);
            });
        }
    }, 100);
}

/**
 * 绑定事件监听器
 */
function bindEvents() {
    // 所有数字输入框：失去焦点时自动去前导零
    document.addEventListener('change', (e) => {
        if (e.target.type === 'number' && e.target.value) {
            const num = parseFloat(e.target.value);
            if (!isNaN(num)) e.target.value = num;
        }
    });

    // 模型切换
    $('#model-select').addEventListener('change', () => { onModelChange(); saveSettings(); });

    // 参数 - 值变化时自动保存
    $('#params-container').addEventListener('input', () => saveSettings());

    // 参数重置
    $('#reset-params').addEventListener('click', () => {
        const cfg = state.modelConfigs[state.currentModel];
        const inputs = $$('.param-input');
        cfg.defaults.forEach((d, i) => { if (inputs[i]) inputs[i].value = d; });
        saveSettings();
    });

    // 初始值重置
    $('#apply-best-init').addEventListener('click', () => {
        const initRange = state.initRanges[state.currentModel];
        $('#x-min').value = initRange.x_range[0];
        $('#x-max').value = initRange.x_range[1];
        $('#y-min').value = initRange.y_range[0];
        $('#y-max').value = initRange.y_range[1];
        saveSettings();
    });

    // 跟踪点
    $('#add-track').addEventListener('click', () => { addTrackPoint(); saveSettings(); });
    $('#clear-track').addEventListener('click', () => { clearTrackPoints(); saveSettings(); });

    // 迭代次数
    $('#iter-range').addEventListener('input', () => {
        $('#iter-value').value = $('#iter-range').value;
    });
    $('#iter-value').addEventListener('change', () => {
        const val = parseInt($('#iter-value').value);
        const min = parseInt($('#iter-range').min);
        const max = parseInt($('#iter-range').max);
        if (val >= min && val <= max) {
            $('#iter-range').value = val;
        }
        saveSettings();
    });
    $('#reset-iters').addEventListener('click', () => {
        const cfg = state.modelConfigs[state.currentModel];
        $('#iter-range').value = cfg.recommended_iterations;
        $('#iter-value').value = cfg.recommended_iterations;

        // 同时更新动画设置
        const recommendedIters = cfg.recommended_iterations;
        const animFrames = 300;
        const halfFrames = Math.floor(animFrames / 2);
        const animStart = Math.max(0, recommendedIters - halfFrames);
        const animEnd = animStart + animFrames;

        $('#anim-start').value = animStart;
        $('#anim-end').value = animEnd;
        $('#anim-frames').value = animFrames;

        saveSettings();
    });

    // 控制按钮
    $('#run-sim').addEventListener('click', runSimulation);
    $('#run-anim').addEventListener('click', () => {
        switchTab('tab-anim');
        runAnimation();
    });
    $('#reset-all').addEventListener('click', () => {
        onModelChange();
        state.trackPoints = [];
        updateTrackList();
        saveSettings();
        showToast(i18n.t('reset_done'));
    });
    $('#clean-cache').addEventListener('click', async () => {
        try {
            const resp = await apiCall('/api/cleanup', {});
            showToast(resp.message, 'success');
            location.reload();
        } catch (err) {
            showToast(i18n.t('clean_failed', { msg: err.message }), 'error');
        }
    });

    // 软件设置弹窗
    const settingsModal = $('#settings-modal');
    const modalContent = $('#modal-content');
    const modalHeader = $('.modal-header');
    const languageSelect = $('#language-select');
    const portInput = $('#port-input');

    // 初始化自定义下拉组件
    initCustomSelect();

    // 弹窗拖动功能（fixed 定位，left/top 为视口坐标）
    // savedModalPos 记录拖动位置：弹窗关闭重开恢复位置；刷新/软件重启后内存清空，恢复默认居中
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;
    let savedModalPos = null;

    modalHeader.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;  // 仅左键拖动
        isDragging = true;
        const rect = modalContent.getBoundingClientRect();
        dragOffsetX = e.clientX - rect.left;
        dragOffsetY = e.clientY - rect.top;
        modalContent.style.cursor = 'grabbing';
        e.preventDefault();  // 防止拖动时选中文字
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const left = e.clientX - dragOffsetX;
        const top = e.clientY - dragOffsetY;
        modalContent.style.left = left + 'px';
        modalContent.style.top = top + 'px';
        modalContent.style.transform = 'none';  // 取消居中 transform，避免双重偏移
        savedModalPos = { left, top };  // 记住拖动位置
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            modalHeader.style.cursor = 'move';
        }
    });

    // 打开设置弹窗
    $('#software-settings').addEventListener('click', () => {
        // 有拖动记录则恢复位置，否则恢复默认居中
        if (savedModalPos) {
            modalContent.style.left = savedModalPos.left + 'px';
            modalContent.style.top = savedModalPos.top + 'px';
            modalContent.style.transform = 'none';
        } else {
            modalContent.style.left = '';
            modalContent.style.top = '';
            modalContent.style.transform = '';
        }
        // 加载保存的设置
        const savedLang = localStorage.getItem('app_language') || i18n.getLang();
        const savedPort = localStorage.getItem('app_port') || 5000;

        // 设置自定义下拉组件的值
        setCustomSelectValue(languageSelect, savedLang);

        portInput.value = savedPort;
        settingsModal.classList.add('show');
    });

    // 关闭设置弹窗
    $('#settings-cancel').addEventListener('click', () => {
        settingsModal.classList.remove('show');
    });

    // 点击遮罩关闭弹窗
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            settingsModal.classList.remove('show');
        }
    });

    // 保存设置
    $('#settings-save').addEventListener('click', () => {
        const newLang = languageSelect.value;
        const newPort = parseInt(portInput.value);

        if (newPort < 1024 || newPort > 65535) {
            showToast('端口范围: 1024-65535', 'error');
            return;
        }

        // 保存语言设置
        i18n.setLang(newLang);
        // 保存端口设置
        localStorage.setItem('app_port', newPort);

        showToast(i18n.t('reset_done'), 'success');
        settingsModal.classList.remove('show');
    });

    // 恢复默认设置
    $('#restore-default').addEventListener('click', () => {
        // 恢复默认语言（检测系统语言）
        const defaultLang = detectSystemLang();
        // 恢复默认端口
        const defaultPort = 5000;

        // 设置自定义下拉组件的值
        setCustomSelectValue(languageSelect, defaultLang);

        portInput.value = defaultPort;

        // 清除保存的设置
        localStorage.removeItem('app_language');
        localStorage.removeItem('app_port');

        // 应用默认语言
        i18n.setLang(defaultLang);

        showToast(i18n.t('reset_done'), 'success');
        settingsModal.classList.remove('show');
    });

    // 检测系统语言（辅助函数）
    function detectSystemLang() {
        const nav = (navigator.language || 'zh-CN').toLowerCase();
        if (nav.startsWith('zh')) {
            if (nav.startsWith('zh-tw') || nav.startsWith('zh-hk') || nav.startsWith('zh-mo')) return 'zh-TW';
            return 'zh-CN';
        }
        if (nav.startsWith('ja')) return 'ja';
        if (nav.startsWith('ko')) return 'ko';
        return 'en';
    }

    // 标签切换
    $$('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // 动画控制
    $('#anim-play').addEventListener('click', playAnimation);
    $('#anim-pause').addEventListener('click', pauseAnimation);
    $('#anim-slider').addEventListener('input', () => {
        const frame = parseInt($('#anim-slider').value);
        if (state.animationData) {
            state.animFrame = frame;
            renderAnimFrame(frame);
        }
    });

    // 动画起始/结束/帧数联动
    function syncAnimRange(source) {
        const start = parseInt($('#anim-start').value) || 0;
        const end = parseInt($('#anim-end').value) || 300;
        const frames = parseInt($('#anim-frames').value) || 300;
        if (source === 'start') {
            $('#anim-end').value = start + frames;
        } else if (source === 'end') {
            $('#anim-frames').value = Math.max(1, end - start);
        } else if (source === 'frames') {
            $('#anim-end').value = start + frames;
        }
        saveSettings();
    }
    $('#anim-start').addEventListener('input', () => syncAnimRange('start'));
    $('#anim-end').addEventListener('input', () => syncAnimRange('end'));
    $('#anim-frames').addEventListener('input', () => syncAnimRange('frames'));

    // 初始值变化时自动保存
    ['#x-min', '#x-max', '#y-min', '#y-max'].forEach(sel => {
        $(sel)?.addEventListener('input', () => saveSettings());
    });

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            runSimulation();
        }
        if (e.key === ' ' && document.activeElement === document.body) {
            e.preventDefault();
            if (state.animPlaying) pauseAnimation();
            else playAnimation();
        }
    });

}

/**
 * 启动应用
 */
document.addEventListener('DOMContentLoaded', () => {
    init();
    bindEvents();
});
