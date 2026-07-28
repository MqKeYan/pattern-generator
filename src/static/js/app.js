/**
 * 斑图形成可视化系统 - 前端交互逻辑
 * 主要功能：模型参数设置、模拟计算、动画展示、数据可视化
 */

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
};

// DOM元素缓存
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

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
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3500);
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
 * 初始化应用
 * 加载配置、恢复设置、初始化UI
 */
async function init() {
    state.clientId = getClientId();

    try {
        const resp = await fetch('/api/config');
        const config = await resp.json();

        state.modelConfigs = config.models;
        state.initRanges = config.init_ranges;
        state.paramNames = config.param_names;
        state.modelDisplayNames = config.display_names || {};

        // 硬件信息
        $('#hardware-badge').textContent = ' ' + config.hardware_info;

        // 构建模型选择器
        const select = $('#model-select');
        select.innerHTML = Object.keys(config.models).map(m =>
            `<option value="${m}">${state.modelDisplayNames[m] || m}</option>`
        ).join('');

        // 恢复本地设置
        const saved = loadSettings();
        if (saved) {
            if (saved.model) {
                // 保存并设置模型值
                state.currentModel = saved.model;
                select.value = saved.model;
            }
            if (saved.trackPoints) state.trackPoints = saved.trackPoints;
            updateTrackList();
        }

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

        // 尝试恢复服务端缓存的图表
        const cachedResp = await apiCall('/api/restore', {});
        if (cachedResp.success && cachedResp.cached) {
            const cache = cachedResp.cached;
            if (cache.type === 'simulation' && cache.viz_2d) {
                render2DPatterns(cache.viz_2d);
                if (cache.viz_3d) render3DPattern(cache.viz_3d);
                setStatus('已恢复上次模拟结果', 'success');
                showToast('已恢复上次结果，刷新无忧');
            }
            if (cache.anim && cache.anim.animation) {
                state.animationData = cache.anim.animation;
                state.animStart = parseInt($('#anim-start').value) || 0;
                state.animEnd = parseInt($('#anim-end').value) || cache.anim.animation.total_frames;
                state.animFrame = 0;
                state.animPlaying = false;
                $('#anim-slider').max = cache.anim.animation.total_frames - 1;
                $('#anim-slider').value = 0;
                $('#anim-frame-info').textContent = `帧: 0 / ${cache.anim.animation.total_frames}`;
                renderAnimFrame(0);
                renderAnimEvolution();
            }
        } else {
            setStatus('就绪，请选择参数运行模拟');
        }
    } catch (err) {
        console.error('初始化失败:', err);
        setStatus('初始化失败', 'error');
    }
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
        showToast('坐标必须在0~99之间', 'error');
        return;
    }
    if (state.trackPoints.some(p => p.x === x && p.y === y)) {
        showToast(`点(${x},${y})已存在`, 'info');
        return;
    }
    state.trackPoints.push({ x, y });
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
        el.textContent = '当前跟踪点: 中心点(50,50)';
    } else {
        const pts = state.trackPoints.map(p => `点(${p.x},${p.y})`).join(', ');
        el.textContent = `当前跟踪点: 中心点(50,50), ${pts}`;
    }
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

    showLoading('模拟计算中，请稍候...');
    setStatus(' 模拟进行中...', 'info');

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
        render2DPatterns(resp.viz_2d);
        // 渲染三维斑图
        render3DPattern(resp.viz_3d);

        setStatus(` 模拟完成 — ${resp.model}，迭代${resp.iterations}次`, 'success');
        showToast('模拟完成！', 'success');
    } catch (err) {
        console.error('模拟失败:', err);
        setStatus(' 模拟失败: ' + err.message, 'error');
        showToast('模拟失败: ' + err.message, 'error');
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
    const xPop = vizData['2d_patterns'].x_population;
    const yPop = vizData['2d_patterns'].y_population;
    const combined = vizData.combined_pattern;
    const evolution = vizData.evolution_curves;

    // X种群热力图
    Plotly.newPlot('chart-x-pop', [{
        z: xPop.data,
        type: 'heatmap',
        colorscale: 'Viridis',
        colorbar: { title: '密度', len: 0.8 },
    }], {
        title: { text: xPop.title, font: { size: 14, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#0a0e14',
        font: { color: '#b0bed0', size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 40 },
        xaxis: { title: 'X轴', scaleanchor: 'y' },
        yaxis: { title: 'Y轴' },
    }, { responsive: true, displayModeBar: false });

    // Y种群热力图
    Plotly.newPlot('chart-y-pop', [{
        z: yPop.data,
        type: 'heatmap',
        colorscale: 'Plasma',
        colorbar: { title: '密度', len: 0.8 },
    }], {
        title: { text: yPop.title, font: { size: 14, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#0a0e14',
        font: { color: '#b0bed0', size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 40 },
        xaxis: { title: 'X轴', scaleanchor: 'y' },
        yaxis: { title: 'Y轴' },
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
        colorbar: { title: '密度', len: 0.8 },
    }], {
        title: { text: combined.title, font: { size: 14, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#0a0e14',
        font: { color: '#b0bed0', size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 40 },
        xaxis: { title: 'X轴', scaleanchor: 'y' },
        yaxis: { title: 'Y轴' },
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
        title: { text: evolution.title, font: { size: 15, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#1a1f2b',
        font: { color: '#b0bed0', size: 11 },
        margin: { l: 60, r: 30, t: 40, b: 50 },
        xaxis: { title: '迭代次数', gridcolor: '#3a4558', zeroline: false },
        yaxis: { title: '种群密度', gridcolor: '#3a4558', zeroline: false },
        legend: { font: { size: 9 }, bgcolor: '#131820', bordercolor: '#3a4558' },
        hovermode: 'closest',
    }, { responsive: true, displayModeBar: false });
}

/**
 * 渲染三维斑图
 * @param {Object} vizData - 可视化数据
 */
function render3DPattern(vizData) {
    Plotly.newPlot('chart-3d', [{
        z: vizData.z,
        type: 'surface',
        colorscale: 'Viridis',
        contours: {
            z: { show: true, usecolormap: true, highlightcolor: 'rgba(255,255,255,0.4)', project: { z: true } },
        },
    }], {
        title: { text: vizData.title, font: { size: 15, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        scene: {
            xaxis: {
                title: { text: 'X轴', standoff: 15, font: { size: 12, color: '#c0cce0' } },
                gridcolor: '#3a4558',
                color: '#b0bed0',
                tickfont: { size: 9, color: '#8895aa' },
                showline: true, linecolor: '#5a6880', linewidth: 1,
                ticks: 'outside', tickcolor: '#5a6880', ticklen: 4,
            },
            yaxis: {
                title: { text: 'Y轴', standoff: 15, font: { size: 12, color: '#c0cce0' } },
                gridcolor: '#3a4558',
                color: '#b0bed0',
                tickfont: { size: 9, color: '#8895aa' },
                showline: true, linecolor: '#5a6880', linewidth: 1,
                ticks: 'outside', tickcolor: '#5a6880', ticklen: 4,
            },
            zaxis: {
                title: { text: '种群密度', standoff: 15, font: { size: 12, color: '#c0cce0' } },
                gridcolor: '#3a4558',
                color: '#b0bed0',
                tickfont: { size: 9, color: '#8895aa' },
                showline: true, linecolor: '#5a6880', linewidth: 1,
                ticks: 'outside', tickcolor: '#5a6880', ticklen: 4,
            },
            bgcolor: '#0a0e14',
            camera: { eye: { x: 1.5, y: 1.5, z: 1.2 } },
        },
        margin: { l: 0, r: 0, t: 40, b: 0 },
    }, { responsive: true, displayModeBar: false });
}

/**
 * 运行动画
 * 生成动画数据并初始化动画界面
 */
async function runAnimation() {
    showLoading('准备动画数据...');

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
        $('#anim-frame-info').textContent = `帧: 0 / ${resp.animation.total_frames}`;

        // 渲染第一帧
        renderAnimFrame(0);

        // 渲染中心点时间序列
        renderAnimEvolution();

        hideLoading();
        showToast('动画数据准备完成', 'success');
        setStatus('动画数据就绪，点击播放', 'success');
    } catch (err) {
        console.error('动画准备失败:', err);
        hideLoading();
        showToast('动画准备失败: ' + err.message, 'error');
        setStatus('动画准备失败', 'error');
    }
}

/**
 * 渲染动画帧
 * @param {number} frameIdx - 帧索引
 */
function renderAnimFrame(frameIdx) {
    const data = state.animationData;
    const frame = data.frames[frameIdx];
    const displayFrames = data.total_frames;
    const iterNum = (state.animStart || 0) + frameIdx;

    // X种群帧
    Plotly.react('chart-anim-x', [{
        z: frame.x_data,
        type: 'heatmap',
        colorscale: 'Viridis',
        colorbar: { title: '', len: 0.7, thickness: 15, x: 1.02, showticklabels: false },
    }], {
        title: { text: `X种群 - 迭代 ${iterNum}`, font: { size: 13, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#0a0e14',
        font: { color: '#b0bed0', size: 10 },
        margin: { l: 40, r: 35, t: 35, b: 35 },
        xaxis: { range: [0, 99], autorange: false, fixedrange: true, scaleanchor: 'y' },
        yaxis: { range: [0, 99], autorange: false, fixedrange: true },
    }, { responsive: false, displayModeBar: false });

    // Y种群帧
    Plotly.react('chart-anim-y', [{
        z: frame.y_data,
        type: 'heatmap',
        colorscale: 'Plasma',
        colorbar: { title: '', len: 0.7, thickness: 15, x: 1.02, showticklabels: false },
    }], {
        title: { text: `Y种群 - 迭代 ${iterNum}`, font: { size: 13, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#0a0e14',
        font: { color: '#b0bed0', size: 10 },
        margin: { l: 40, r: 35, t: 35, b: 35 },
        xaxis: { range: [0, 99], autorange: false, fixedrange: true, scaleanchor: 'y' },
        yaxis: { range: [0, 99], autorange: false, fixedrange: true },
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

    Plotly.react('chart-anim-combined', [{
        z: combined,
        type: 'heatmap',
        colorscale: [
            [0, 'rgb(0,30,0)'],
            [0.25, 'rgb(180,0,0)'],
            [0.5, 'rgb(200,180,0)'],
            [0.75, 'rgb(0,180,0)'],
            [1, 'rgb(0,200,200)'],
        ],
        colorbar: { title: '', len: 0.7, thickness: 15, x: 1.02, showticklabels: false },
    }], {
        title: { text: `合并斑图 - 迭代 ${iterNum}`, font: { size: 13, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#0a0e14',
        font: { color: '#b0bed0', size: 10 },
        margin: { l: 40, r: 35, t: 35, b: 35 },
        xaxis: { range: [0, 99], autorange: false, fixedrange: true, scaleanchor: 'y' },
        yaxis: { range: [0, 99], autorange: false, fixedrange: true },
    }, { responsive: false, displayModeBar: false });

    $('#anim-slider').value = frameIdx;
    $('#anim-frame-info').textContent = `帧: ${frameIdx} / ${displayFrames}`;
}

/**
 * 渲染动画演化曲线
 */
function renderAnimEvolution() {
    const data = state.animationData;
    const cs = data.center_series;

    // 使用实际的起始迭代次数调整时间轴
    const actualStartTime = state.animStart || 0;
    const adjustedTime = cs.time.map(t => t + actualStartTime);

    Plotly.react('chart-anim-evo', [
        { x: adjustedTime, y: cs.x, type: 'scatter', mode: 'lines', name: 'X种群-中心点',
          line: { color: '#3498DB', width: 2 } },
        { x: adjustedTime, y: cs.y, type: 'scatter', mode: 'lines', name: 'Y种群-中心点',
          line: { color: '#E74C3C', width: 2 } },
    ], {
        title: { text: '中心点时间演化', font: { size: 13, color: '#e0e4ec' } },
        paper_bgcolor: '#0a0e14',
        plot_bgcolor: '#1a1f2b',
        font: { color: '#b0bed0', size: 10 },
        margin: { l: 50, r: 20, t: 35, b: 40 },
        xaxis: {
            title: '迭代次数',
            gridcolor: '#3a4558',
            // 设置x轴范围，显示从起始迭代到结束迭代的完整范围
            range: [actualStartTime, actualStartTime + cs.time.length - 1]
        },
        yaxis: { title: '种群密度', gridcolor: '#3a4558' },
        legend: { font: { size: 9 }, bgcolor: '#131820', bordercolor: '#3a4558' },
    }, { responsive: true, displayModeBar: false });
}

/**
 * 播放动画
 */
function playAnimation() {
    if (!state.animationData) {
        showToast('请先运行动画计算', 'error');
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
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));

    const btn = document.querySelector(`[data-tab="${tabId}"]`);
    const panel = document.getElementById(tabId);
    if (btn) btn.classList.add('active');
    if (panel) panel.classList.add('active');

    // 切换后触发所有图表resize
    setTimeout(() => {
        const panel = document.getElementById(tabId);
        if (panel) {
            panel.querySelectorAll('.chart-box').forEach(el => Plotly.Plots.resize(el));
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
        showToast('所有设置已重置');
    });
    $('#clean-cache').addEventListener('click', async () => {
        try {
            const resp = await apiCall('/api/cleanup', {});
            showToast(resp.message, 'success');
        } catch (err) {
            showToast('清理失败: ' + err.message, 'error');
        }
    });

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