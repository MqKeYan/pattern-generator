// 后台管理中心交互逻辑 —— 复用主界面 i18n 与主题变量

const state = {
    metrics: null,          // 最新监控指标
    history: [],            // 监控历史（3 分钟滚动）
    peaks: {},
    counts: { waiting: 0, running: 0 },
    clientsSummary: {},
    clients: [],
    tasks: { running: [], waiting: [], history: [], dead: [] },
    lists: { blacklist: { ips: [], client_ids: [] }, whitelist: { ips: [], client_ids: [] } },
    logs: [],               // 内存日志缓冲
    clientCountHistory: [], // 在线客户端数曲线（本地滚动）
    ws: null,
    activeTab: 'tab-overview',
    startedAt: null,   // 软件进程启动时间（epoch 毫秒），由服务端 metrics 消息下发
    pausedAccum: 0,    // 断线期间暂停的累计秒数（不计入运行时长）
    pausedAt: null,    // 本次断开的时刻（epoch 毫秒）
    pendingResume: false, // 重连后待判定：软件未重启则从暂停处继续，重启则重新计时
    connected: false,  // 与后台服务的 WS 连接状态：断开时暂停运行时长走字
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---------- API 封装（状态变更接口要求安全头） ----------

async function api(path, { method = 'GET', body = null, raw = false } = {}) {
    const resp = await fetch(path, {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: body !== null ? JSON.stringify(body) : undefined,
    });
    if (raw) {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp;
    }
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(json.error || `HTTP ${resp.status}`);
    return json;
}

function showToast(msg, type = 'info') {
    const container = $('#toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}

function fmtDuration(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return h > 0 ? `${h}时${m}分` : (m > 0 ? `${m}分${s}秒` : `${s}秒`);
}

function esc(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

// HTML 属性值需要额外转义引号，避免外部标识符突破属性边界。
function escAttr(text) {
    return esc(text).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function pathSegment(value) {
    return encodeURIComponent(String(value ?? ''));
}

// ---------- 自定义下拉（复用主界面样式与交互） ----------

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

function bindCustomSelect(customSelect) {
    if (customSelect.dataset.bound) return;
    customSelect.dataset.bound = '1';
    const trigger = customSelect.querySelector('.custom-select-trigger');
    const options = customSelect.querySelector('.custom-select-options');
    const optionItems = customSelect.querySelectorAll('.custom-select-option');
    const selectedText = trigger.querySelector('.selected-text');
    options._trigger = trigger;
    const initialSelected = customSelect.querySelector('.custom-select-option.selected');
    if (initialSelected) {
        customSelect.value = initialSelected.dataset.value;
        selectedText.textContent = initialSelected.textContent;
    } else if (customSelect.getAttribute('value') != null) {
        setCustomSelectValue(customSelect, customSelect.getAttribute('value'));
    }
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
    function closeOptions() {
        options.classList.remove('show');
        trigger.classList.remove('active');
    }
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        $$('.custom-select-options.show').forEach(otherOptions => {
            if (otherOptions !== options) {
                otherOptions.classList.remove('show');
                if (otherOptions._trigger) otherOptions._trigger.classList.remove('active');
            }
        });
        if (options.classList.contains('show')) closeOptions();
        else openOptions();
    });
    optionItems.forEach(option => {
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            optionItems.forEach(opt => opt.classList.remove('selected'));
            option.classList.add('selected');
            selectedText.textContent = option.textContent;
            customSelect.value = option.dataset.value;
            customSelect.dispatchEvent(new Event('change'));
            closeOptions();
        });
    });
    window.addEventListener('scroll', () => {
        if (options.classList.contains('show')) closeOptions();
    }, true);
}

function initCustomSelect() {
    $$('.custom-select').forEach(bindCustomSelect);
    document.addEventListener('click', () => {
        $$('.custom-select-options.show').forEach(options => {
            options.classList.remove('show');
            if (options._trigger) options._trigger.classList.remove('active');
        });
    });
}

// ---------- WebSocket 实时推送（断线每 3 秒自动重连） ----------

function setConnState(text, cls) {
    $('#ws-state').textContent = text;
    $('#ws-state').className = 'ws-state ' + cls;
}

function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    try {
        state.ws = new WebSocket(`${proto}://${location.host}/admin/ws`);
    } catch {
        scheduleReconnect();
        return;
    }
    state.ws.onopen = () => {
        state.connected = true;
        setConnState('实时连接已建立', 'online');
    };
    state.ws.onmessage = (e) => {
        try { handleMessage(JSON.parse(e.data)); } catch (err) { console.error('WS 消息处理失败', err); }
    };
    state.ws.onclose = () => {
        // 断开后立即暂停运行时长走字，并探测软件是否仍在运行
        state.connected = false;
        state.pausedAt = Date.now();
        state.pendingResume = true;
        setConnState('服务已停止，等待软件重新连接...', 'offline');
        scheduleReconnect();
    };
    state.ws.onerror = () => { try { state.ws.close(); } catch { /* ignore */ } };
}

function scheduleReconnect() {
    setTimeout(async () => {
        try {
            await fetch('/admin/api/metrics', { headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store' });
            connectWS();  // 服务仍在运行：重连 WS，恢复运行时长
        } catch {
            // 软件已关闭：清空本次运行时长记录，继续探测等待软件重新启动
            state.startedAt = null;
            state.pausedAccum = 0;
            state.pendingResume = false;
            $('#stat-uptime').textContent = '-';
            scheduleReconnect();
        }
    }, 3000);
}

async function refreshAll() {
    try {
        const m = await api('/admin/api/metrics');
        handleMessage({ type: 'metrics', started_at: m.started_at, current: m.current, history: m.history, peaks: m.peaks, counts: m.counts, clients_summary: m.clients_summary });
        const c = await api('/admin/api/clients');
        handleMessage({ type: 'clients', data: c.clients });
        const t = await api('/admin/api/tasks');
        handleMessage({ type: 'tasks', running: t.running, waiting: t.waiting, history: t.history, counts: t.counts });
        const d = await api('/admin/api/dead-tasks');
        state.tasks.dead = d.tasks;
        renderDead();
    } catch { /* 服务未就绪时静默 */ }
}

function handleMessage(msg) {
    if (msg.type === 'metrics') {
        const sa = msg.started_at ? msg.started_at * 1000 : null;
        if (sa && state.startedAt && state.pendingResume) {
            // 断线重连：软件未重启（started_at 未变）则从暂停处继续计时，重启则重新计时
            if (sa === state.startedAt) state.pausedAccum += (Date.now() - state.pausedAt) / 1000;
            else state.pausedAccum = 0;
            state.pendingResume = false;
        } else if (sa && !state.startedAt) {
            state.pausedAccum = 0;  // 首次拿到启动时间（或软件重启后清空过）：重新计时
        }
        if (sa) state.startedAt = sa;
        state.metrics = msg.current;
        state.history = msg.history || state.history;
        state.peaks = msg.peaks || {};
        state.counts = msg.counts || state.counts;
        state.clientsSummary = msg.clients_summary || {};
        const sampleTime = Number(msg.current?.timestamp);
        state.clientCountHistory.push({
            t: Number.isFinite(sampleTime) ? sampleTime : Date.now() / 1000,
            n: state.clientsSummary.online_clients || 0,
        });
        if (state.clientCountHistory.length > 120) state.clientCountHistory.shift();
        renderStatusCard();
        if (state.activeTab === 'tab-overview') renderOverview();
        if (state.activeTab === 'tab-monitor') renderMonitor();
    } else if (msg.type === 'clients') {
        state.clients = msg.data || [];
        if (state.activeTab === 'tab-clients') renderClients();
    } else if (msg.type === 'tasks') {
        state.tasks.running = msg.running || [];
        state.tasks.waiting = msg.waiting || [];
        state.tasks.history = msg.history || state.tasks.history;
        state.counts = msg.counts || state.counts;
        if (state.activeTab === 'tab-tasks') renderTasks();
    } else if (msg.type === 'logs') {
        state.logs.push(...(msg.entries || []));
        if (state.logs.length > 1000) state.logs = state.logs.slice(-1000);
        if (msg.file) state.logFile = msg.file;
        if (state.activeTab === 'tab-logs') renderLogs();
    }
}

// ---------- 侧边栏状态卡 ----------

// 当前展示的运行时长（秒）：真实进程时长扣除断线暂停的累计时长；软件关闭时为 null
function uptimeSeconds() {
    if (!state.startedAt) return null;
    return Math.max(0, (Date.now() - state.startedAt) / 1000 - state.pausedAccum);
}

function renderStatusCard() {
    const up = uptimeSeconds();
    $('#stat-uptime').textContent = up == null ? '-' : fmtDuration(up);
    $('#stat-port').textContent = window.ADMIN_CONFIG.port;
    $('#stat-admin-port').textContent = window.ADMIN_CONFIG.admin_port;
    $('#stat-online').textContent = state.clientsSummary.online_clients ?? '-';
    $('#stat-running').textContent = state.counts.running;
    $('#stat-waiting').textContent = state.counts.waiting;
}

// ---------- 标签页切换 ----------

function switchTab(tabId) {
    state.activeTab = tabId;
    $$('.admin-nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
    $$('.tab-panel').forEach(p => p.classList.toggle('active', p.id === tabId));
    if (tabId === 'tab-monitor') requestAnimationFrame(renderMonitor);
    if (tabId === 'tab-tasks') renderTasks(), renderDead();
    if (tabId === 'tab-clients') renderClients();
    if (tabId === 'tab-access') { renderLists(); loadAccessEvents(); }
    if (tabId === 'tab-notify') loadNotifyTab();
    if (tabId === 'tab-logs') renderLogs();
    if (tabId === 'tab-settings') loadSettingsTab();
}

// ---------- 概览 ----------

function statCard(label, value, unit = '', cls = '') {
    return `<div class="stat-card ${cls}"><div class="stat-label">${label}</div>
        <div><span class="stat-value">${value}</span><span class="stat-unit">${unit}</span></div></div>`;
}

function renderOverview() {
    const m = state.metrics || {};
    const gpu = (m.gpus && m.gpus[0]) || {};
    const cards1 = [
        statCard('CPU 占用', m.cpu_percent ?? '-', '%', (m.cpu_percent || 0) > 90 ? 'hot' : ''),
        statCard('内存占用', m.mem_percent ?? '-', '%', (m.mem_percent || 0) > 90 ? 'hot' : ''),
        statCard('GPU 占用', gpu.util_percent ?? (m.gpus ? '无' : '-'), '%'),
        statCard('GPU 显存', gpu.mem_used_mb != null ? gpu.mem_used_mb : '-', 'MB'),
        statCard('GPU 温度', gpu.temp ?? (m.gpus ? '无' : '-'), '℃', (gpu.temp || 0) > 80 ? 'warn' : ''),
        statCard('GPU 功耗', gpu.power_w ?? (m.gpus ? '无' : '-'), 'W'),
    ].join('');
    $('#ov-metric-cards').innerHTML = cards1;

    const s = state.clientsSummary;
    const cards2 = [
        statCard('在线客户端', s.online_clients ?? 0, ''),
        statCard('总客户端', s.total_clients ?? 0, ''),
        statCard('运行中任务', state.counts.running, ''),
        statCard('等待任务', state.counts.waiting, '', state.counts.waiting > 10 ? 'warn' : ''),
        statCard('总请求数', s.total_requests ?? 0, ''),
    ].join('');
    $('#ov-count-cards').innerHTML = cards2;

    const history = state.tasks.history || [];
    const totalCompute = Object.values(history).reduce((acc, t) => {
        if (t.started_at && t.completed_at) acc += t.completed_at - t.started_at;
        return acc;
    }, (s.total_compute_time || 0));
    const waits = history.filter(t => t.started_at && t.created_at).map(t => t.started_at - t.created_at);
    const runs = history.filter(t => t.started_at && t.completed_at).map(t => t.completed_at - t.started_at);
    const avg = arr => arr.length ? (arr.reduce((a, b) => a + b, 0) / arr.length) : 0;
    const cards3 = [
        statCard('累计计算时长', fmtDuration(totalCompute), ''),
        statCard('平均等待时间', avg(waits).toFixed(1), 's'),
        statCard('平均执行时间', avg(runs).toFixed(1), 's'),
    ].join('');
    $('#ov-total-cards').innerHTML = cards3;
}

// ---------- 实时监控 ----------

// 与主界面 app.js 一致的图表主题（读取复用的 style.css 绘图变量）
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

// 数值紧凑格式：绝对值 ≥100 取整，否则保留 1 位小数
const fmtPlotVal = v => Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10);

// 十六进制颜色 → 带 alpha 的 rgba（任务管理器样式的面积填充）
function withAlpha(hex, alpha) {
    const n = parseInt((hex || '#ffffff').slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// 固定 60 秒时间窗（任务管理器模式：曲线从右端出现，随时间向左滚动）
const MONITOR_WINDOW = 60;

// 每个参数独立一张图；get 从单条监控样本取值，无 GPU 环境不生成 GPU 图。
// max 为固定纵轴上限；标注"上限=..."的参数取本机硬件容量（renderMonitor 中动态计算）
function monitorTileDefs(hasGpu) {
    const gpuOf = (h, field) => (h.gpus && h.gpus[0]) ? h.gpus[0][field] : null;
    const tiles = [
        { key: 'cpu', name: 'CPU 占用', unit: '%', color: '#3498db', max: 100, get: h => h.cpu_percent },
        { key: 'mem', name: '内存占用', unit: 'MB', color: '#2ecc71', cap: 'mem_total_mb', get: h => h.mem_used_mb },
        { key: 'proc_mem', name: '进程内存', unit: 'MB', color: '#9b59b6', get: h => h.proc_mem_mb },  // 与磁盘写入一致，纵轴使用 Plotly 自动范围
    ];
    if (hasGpu) {
        tiles.push(
            { key: 'gpu_util', name: 'GPU 利用率', unit: '%', color: '#3498db', max: 100, get: h => gpuOf(h, 'util_percent') },
            { key: 'gpu_mem', name: 'GPU 显存', unit: 'MB', color: '#e67e22', cap: 'mem_total_mb', gpu: true, get: h => gpuOf(h, 'mem_used_mb') },
            { key: 'gpu_temp', name: 'GPU 温度', unit: '℃', color: '#e74c3c', max: 100, get: h => gpuOf(h, 'temp') },
            { key: 'gpu_power', name: 'GPU 功耗', unit: 'W', color: '#f39c12', cap: 'power_limit_w', gpu: true, get: h => gpuOf(h, 'power_w') },
        );
    }
    tiles.push(
        { key: 'disk_read', name: '磁盘读', unit: 'MB/s', color: '#2ecc71', get: h => h.disk_read_mb_s },
        { key: 'disk_write', name: '磁盘写', unit: 'MB/s', color: '#1abc9c', get: h => h.disk_write_mb_s },
        { key: 'net_sent', name: '网络发送', unit: 'MB/s', color: '#3498db', get: h => h.net_sent_mb_s },
        { key: 'net_recv', name: '网络接收', unit: 'MB/s', color: '#9b59b6', get: h => h.net_recv_mb_s },
        { key: 'clients', name: '在线客户端', unit: '', color: '#3498db', integerAxis: true },  // 数据来自本地滚动缓冲，数量使用整数轴
    );
    return tiles;
}

let monitorTilesBuilt = null;

function ensureMonitorTiles(hasGpu) {
    const key = hasGpu ? 'gpu' : 'nogpu';
    if (monitorTilesBuilt === key) return;
    monitorTilesBuilt = key;
    const grid = $('#monitor-grid');
    grid.innerHTML = '';
    monitorTileDefs(hasGpu).forEach(t => {
        const tile = document.createElement('div');
        tile.className = 'chart-tile';
        tile.innerHTML = `<div class="tile-head"><span class="tile-name">${esc(t.name)}</span></div>`
            + `<div class="chart-box" id="tile-chart-${t.key}">`
            + `<span class="tile-corner tl" id="tile-tl-${t.key}"></span>`
            + `<span class="tile-corner tr" id="tile-tr-${t.key}"></span>`
            + `<span class="tile-corner bl" id="tile-bl-${t.key}"></span>`
            + `<span class="tile-corner br" id="tile-br-${t.key}"></span>`
            + `</div>`;
        grid.appendChild(tile);
    });
}

const secOfDay = s => {
    const [hh, mm, ss] = s.split(':').map(Number);
    return hh * 3600 + mm * 60 + ss;
};

const sampleTimeInSeconds = value => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    return secOfDay(String(value));
};

// 固定窗口横坐标：最新样本位于右端（x=0），只保留时间窗内的样本。
// 支持服务端 Unix 时间戳和其他监控图使用的 HH:MM:SS 字符串。
function windowSeries(times, values) {
    if (!times.length) return { x: [], y: [], span: null };
    const base = sampleTimeInSeconds(times[times.length - 1]);
    const inWin = [];
    for (let i = 0; i < times.length; i++) {
        let off = sampleTimeInSeconds(times[i]) - base;
        if (off > 43200) off -= 86400;  // 跨午夜
        if (off >= -(MONITOR_WINDOW - 1)) inWin.push({ off, y: values[i] });
    }
    if (!inWin.length) return { x: [], y: [], span: null };
    return {
        x: inWin.map(p => p.off),
        y: inWin.map(p => p.y),
        span: -inWin[0].off,
    };
}

// 全局悬浮数值弹窗（单例）：显示在鼠标所 points 上方
function ensurePlotTooltip() {
    let tip = document.getElementById('plot-hover-tip');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = 'plot-hover-tip';
        tip.className = 'plot-hover-tip';
        document.body.appendChild(tip);
    }
    return tip;
}

function hidePlotTooltip() {
    const tip = document.getElementById('plot-hover-tip');
    if (tip) tip.classList.remove('show');
}

function plotTile(id, tile, data, ymax) {
    const colors = getPlotTheme();
    const el = document.getElementById(id);
    const fn = el._fullLayout ? Plotly.react : Plotly.newPlot;
    fn(id, [{
        x: data.x, y: data.y,
        type: 'scatter', mode: 'lines',
        line: { color: tile.color, width: 1.5 },
        fill: 'tozeroy', fillcolor: withAlpha(tile.color, 0.22),
        // 关闭原生悬浮标签（'none' 保留 hover 事件），改用自定义弹窗显示在点上方
        hoverinfo: 'none',
    }], {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0.28)',
        // 四周边距归零：绘图区铺满瓷砖，曲线两端顶到边缘（任务管理器样式）
        margin: { l: 0, r: 0, t: 0, b: 0 },
        showlegend: false,
        xaxis: {
            // 范围精确贴合数据跨度：无左缘空白；数据铺满窗口后长度固定
            range: [-(data.span ?? (MONITOR_WINDOW - 1)), 0],
            gridcolor: colors.grid, zeroline: false,
            showticklabels: false, ticks: '', nticks: 12, fixedrange: true,
        },
        yaxis: {
            rangemode: 'tozero', gridcolor: colors.grid, zeroline: false,
            showticklabels: false, ticks: '', nticks: 7, fixedrange: true,
            // 纵轴高度固定为参数最大值（本机硬件容量上限），无上限的参数保持自动
            ...(ymax != null ? { range: [0, ymax] } : {}),
            ...(tile.integerAxis ? { dtick: 1 } : {}),
        },
    }, { responsive: true, displayModeBar: false });

    // 自定义悬浮弹窗：以数据点为锚点显示在其正上方（带箭头、序列色背景，只显示数值）。
    // 鼠标在点下方或同高时弹出；鼠标位于点上方时不弹出（避免遮挡曲线）
    if (!el._tipBound) {
        el._tipBound = true;
        el.on('plotly_hover', ev => {
            const pt = ev.points && ev.points[0];
            if (!pt || !ev.event) { hidePlotTooltip(); return; }
            const rect = el.getBoundingClientRect();
            const scrollX = window.scrollX || 0, scrollY = window.scrollY || 0;
            // 数据点的页面像素坐标（d2p: 数据坐标 → 绘图区像素，_offset: 绘图区在容器内的偏移）
            const px = rect.left + scrollX + pt.xaxis._offset + pt.xaxis.d2p(pt.x);
            const py = rect.top + scrollY + pt.yaxis._offset + pt.yaxis.d2p(pt.y);
            if (ev.event.clientY + scrollY < py) { hidePlotTooltip(); return; }
            const tip = ensurePlotTooltip();
            tip.style.setProperty('--tip-bg', tile.color);
            tip.textContent = fmtPlotVal(Number(pt.y));
            tip.style.left = `${px}px`;
            tip.style.top = `${py - 8}px`;
            tip.classList.add('show');
        });
        el.on('plotly_unhover', hidePlotTooltip);
    }
}

function renderMonitor() {
    // 过滤采样失败的空样本（time 为空会造成 x 缺失、折线断点）
    const hist = (state.history || []).filter(h => h.time);
    const m = state.metrics || {};
    const gpu0 = (m.gpus && m.gpus[0]) || {};
    const hasGpu = !!(m.gpus && m.gpus.length);
    ensureMonitorTiles(hasGpu);
    monitorTileDefs(hasGpu).forEach(tile => {
        let data, last = null;
        if (tile.key === 'clients') {
            const cc = state.clientCountHistory.slice(-MONITOR_WINDOW);
            data = windowSeries(cc.map(p => p.t), cc.map(p => p.n));
            if (cc.length) data.span = MONITOR_WINDOW - 1;
            if (cc.length) last = cc[cc.length - 1].n;
        } else {
            data = windowSeries(hist.map(h => h.time), hist.map(h => tile.get(h)));
            for (let j = data.y.length - 1; j >= 0; j--) {
                if (data.y[j] != null) { last = data.y[j]; break; }
            }
        }
        // 纵轴上限：固定值 > 窗口峰值（winMax） > 本机硬件容量（物理内存 / 显存总量 / 功耗墙） > 自动
        const vals = data.y.filter(v => v != null);
        const winMax = vals.length ? Math.max(...vals) : null;
        let ymax;
        if (tile.max != null) ymax = tile.max;
        else if (tile.winMax) ymax = winMax;
        else if (tile.cap != null) ymax = tile.gpu ? gpu0[tile.cap] : m[tile.cap];
        else if (tile.integerAxis) ymax = Math.max(1, Math.ceil(winMax ?? 0));
        else ymax = null;
        plotTile('tile-chart-' + tile.key, tile, data, ymax ?? null);

        // 四角标注：左上=实时数值（带单位），左下=时间窗，右上=纵轴最大值，右下=纵轴最小值
        $('#tile-tl-' + tile.key).textContent =
            last == null ? '' : fmtPlotVal(last) + (tile.unit || '');
        $('#tile-bl-' + tile.key).textContent = `${MONITOR_WINDOW} 秒`;
        const chartEl = document.getElementById('tile-chart-' + tile.key);
        const range = (chartEl._fullLayout && chartEl._fullLayout.yaxis)
            ? chartEl._fullLayout.yaxis.range : null;
        if (data.y.length && range) {
            $('#tile-tr-' + tile.key).textContent = fmtPlotVal(range[1]) + (tile.unit || '');
            $('#tile-br-' + tile.key).textContent = fmtPlotVal(range[0]);
        } else {
            $('#tile-tr-' + tile.key).textContent = '';
            $('#tile-br-' + tile.key).textContent = '';
        }
    });
}

// ---------- 任务队列 ----------

function taskRow(t, actions) {
    return `<tr>
        <td title="${esc(t.task_id)}">${esc(t.task_id)}</td>
        <td title="${esc(t.client_id)}">${esc(t.client_id.slice(0, 8))}</td>
        <td>${esc(i18n.t('type_' + t.type))}</td>
        <td>${esc(t.model)}</td>
        <td>${esc(t.iterations ?? t.frames ?? '-')}</td>
        <td><span class="status-pill ${t.status}">${esc(i18n.t('status_' + t.status))}</span></td>
        <td class="progress-cell">${t.status === 'running'
            ? `<div class="progress-bar"><div style="width:${t.progress}%"></div></div> ${t.progress}%`
            : (t.status === 'queued' ? `#${t.queue_position || '-'}` : '-')}</td>
        <td>${t.gpu_id != null ? 'GPU' + t.gpu_id : '-'}</td>
        <td>${t.retry_count || 0}</td>
        <td>${t.started_at && t.completed_at ? (t.completed_at - t.started_at).toFixed(1) + 's' : '-'}</td>
        <td class="cell-actions">${actions(t)}</td>
    </tr>`;
}

function renderTasks() {
    const cancelBtn = t => t.status === 'running' || t.status === 'queued'
        ? `<button class="btn btn-outline btn-danger" data-impact="danger" data-cancel="${t.task_id}">取消</button>` : '-';
    $('#table-running').innerHTML = `<tr><th>任务</th><th>客户端</th><th>类型</th><th>模型</th><th>规模</th><th>状态</th><th>进度</th><th>GPU</th><th>重试</th><th>耗时</th><th>操作</th></tr>` +
        (state.tasks.running.map(t => taskRow(t, cancelBtn)).join('') || '<tr><td colspan="11" style="opacity:.5">无</td></tr>');
    $('#table-waiting').innerHTML = $('#table-running').innerHTML ? `<tr><th>任务</th><th>客户端</th><th>类型</th><th>模型</th><th>规模</th><th>状态</th><th>排队位置</th><th>GPU</th><th>重试</th><th>耗时</th><th>操作</th></tr>` +
        (state.tasks.waiting.map(t => taskRow(t, cancelBtn)).join('') || '<tr><td colspan="11" style="opacity:.5">无</td></tr>') : '';
    const hist = (state.tasks.history || []).slice(-100).reverse();
    $('#table-history').innerHTML = `<tr><th>任务</th><th>客户端</th><th>类型</th><th>模型</th><th>规模</th><th>状态</th><th>进度</th><th>GPU</th><th>重试</th><th>耗时</th><th>错误</th></tr>` +
        (hist.map(t => taskRow(t, () => esc(t.error || '-'))).join('') || '<tr><td colspan="11" style="opacity:.5">无</td></tr>');
    bindTaskButtons();
}

function renderDead() {
    const dead = state.tasks.dead || [];
    $('#table-dead').innerHTML = `<tr><th>任务</th><th>客户端</th><th>类型</th><th>模型</th><th>状态</th><th>重试</th><th>错误</th><th>操作</th></tr>` +
        (dead.map(t => `<tr>
            <td title="${esc(t.task_id)}">${esc(t.task_id)}</td>
            <td>${esc(t.client_id.slice(0, 8))}</td><td>${esc(i18n.t('type_' + t.type))}</td><td>${esc(t.model)}</td>
            <td><span class="status-pill ${t.status}">${esc(i18n.t('status_' + t.status))}</span></td>
            <td>${t.retry_count}</td><td style="max-width:260px;white-space:normal">${esc(t.error || '')}</td>
            <td class="cell-actions">
                <button class="btn btn-outline btn-success" data-impact="normal" data-retry="${t.task_id}">重试</button>
                <button class="btn btn-outline btn-danger" data-impact="danger" data-del-dead="${t.task_id}">删除</button>
            </td></tr>`).join('') || '<tr><td colspan="8" style="opacity:.5">空</td></tr>');
    $$('#table-dead [data-retry]').forEach(b => b.addEventListener('click', async () => {
        try { await api(`/admin/api/task/${pathSegment(b.dataset.retry)}/retry`, { method: 'POST' }); showToast('已重新排队', 'success'); await refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
    $$('#table-dead [data-del-dead]').forEach(b => b.addEventListener('click', async () => {
        try { await api(`/admin/api/task/${pathSegment(b.dataset.delDead)}`, { method: 'DELETE' }); await refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
}

function bindTaskButtons() {
    $$('#table-running [data-cancel], #table-waiting [data-cancel]').forEach(b => b.addEventListener('click', async () => {
        try { await api(`/admin/api/task/${pathSegment(b.dataset.cancel)}/cancel`, { method: 'POST' }); showToast('取消请求已发送'); }
        catch (err) { showToast(err.message, 'error'); }
    }));
}

// ---------- 客户端管理 ----------

function renderClients() {
    const rows = (state.clients || []).map(c => `<tr>
        <td title="${esc(c.client_id)}">${esc(c.client_id)}</td>
        <td>${esc(c.client_name || '-')}</td>
        <td>${esc(c.ip)}</td>
        <td><span class="status-pill ${c.status}">${esc(i18n.t('client_' + c.status))}</span></td>
        <td title="${esc(c.current_task_id || '')}">${c.current_task_id ? esc(c.current_task_id.slice(0, 8)) : '-'}</td>
        <td>${c.total_requests}</td>
        <td>${c.success_count}/${c.failed_count}/${c.cancelled_count}</td>
        <td>${fmtDuration(c.online_duration_seconds)}</td>
        <td>${esc(c.tags.join(', ') || '-')}</td>
        <td>${esc(c.remark || '-')}</td>
        <td class="cell-actions">
            ${c.status === 'paused'
                ? `<button class="btn btn-outline btn-success" data-impact="normal" data-resume="${escAttr(c.client_id)}">恢复</button>`
                : `<button class="btn btn-outline btn-warning" data-impact="caution" data-pause="${escAttr(c.client_id)}">暂停</button>`}
            <button class="btn btn-outline btn-danger" data-impact="danger" data-kick="${escAttr(c.client_id)}">踢出</button>
            <button class="btn btn-outline btn-info" data-impact="caution" data-clear-cache="${escAttr(c.client_id)}">清缓存</button>
            <button class="btn btn-outline btn-white" data-impact="low" data-remark="${escAttr(c.client_id)}" data-remark-val="${escAttr(c.remark || '')}">备注</button>
            <button class="btn btn-outline btn-danger" data-impact="danger" data-delete="${escAttr(c.client_id)}">删除</button>
        </td></tr>`).join('');
    $('#table-clients').innerHTML = `<tr><th>UUID</th><th>名称</th><th>IP</th><th>状态</th><th>当前任务</th><th>请求</th><th>成功/失败/取消</th><th>在线时长</th><th>标签</th><th>备注</th><th>操作</th></tr>` +
        (rows || '<tr><td colspan="11" style="opacity:.5">暂无客户端</td></tr>');

    $$('#table-clients [data-pause]').forEach(b => b.addEventListener('click', async () => {
        try { await api(`/admin/api/client/${pathSegment(b.dataset.pause)}/pause`, { method: 'POST' }); showToast('已暂停'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
    $$('#table-clients [data-resume]').forEach(b => b.addEventListener('click', async () => {
        try { await api(`/admin/api/client/${pathSegment(b.dataset.resume)}/resume`, { method: 'POST' }); showToast('已恢复'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
    $$('#table-clients [data-kick]').forEach(b => b.addEventListener('click', async () => {
        if (!confirm('确认踢出该客户端？其 IP 将同时加入黑名单。')) return;
        try { await api(`/admin/api/client/${pathSegment(b.dataset.kick)}/kick`, { method: 'POST' }); showToast('已踢出并封禁', 'success'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
    $$('#table-clients [data-clear-cache]').forEach(b => b.addEventListener('click', async () => {
        try { await api(`/admin/api/client/${pathSegment(b.dataset.clearCache)}/clear-cache`, { method: 'POST' }); showToast('缓存已清理'); }
        catch (err) { showToast(err.message, 'error'); }
    }));
    $$('#table-clients [data-remark]').forEach(b => b.addEventListener('click', async () => {
        const remark = prompt('备注内容：', b.dataset.remarkVal);
        if (remark === null) return;
        try { await api(`/admin/api/client/${pathSegment(b.dataset.remark)}/remark`, { method: 'POST', body: { remark } }); showToast('备注已保存'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
    $$('#table-clients [data-delete]').forEach(b => b.addEventListener('click', async () => {
        if (!confirm('确认删除该客户端？将断开其页面连接并取消其任务，同时删除统计记录（不封禁 IP 与 UUID）。')) return;
        try { await api(`/admin/api/client/${pathSegment(b.dataset.delete)}/delete`, { method: 'POST' }); showToast('记录已删除', 'success'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    }));
}

// ---------- 访问控制 ----------

async function loadAccessLists() {
    try {
        const resp = await api('/admin/api/access-control');
        state.lists = resp.lists;
        renderLists();
    } catch (err) { showToast(err.message, 'error'); }
}

function renderLists() {
    for (const target of ['whitelist', 'blacklist']) {
        for (const kind of ['ips', 'client_ids']) {
            const box = $(`#list-${target}-${kind}`);
            if (!box) continue;
            box.innerHTML = (state.lists[target][kind] || []).map(entry =>
                `<span class="list-entry">${esc(entry)}<button data-impact="danger" data-target="${target}" data-kind="${kind}" data-entry="${escAttr(entry)}" title="删除">✕</button></span>`
            ).join('') || '<span style="opacity:.5;font-size:12px">空</span>';
        }
    }
    $$('.list-items button[data-entry]').forEach(b => b.addEventListener('click', async () => {
        try {
            await api('/admin/api/access-control', { method: 'POST', body: { action: 'remove', list: b.dataset.target, kind: b.dataset.kind, entry: b.dataset.entry } });
            showToast('已删除');
            await loadAccessLists();
        } catch (err) { showToast(err.message, 'error'); }
    }));
}

async function loadAccessEvents() {
    try {
        const resp = await api('/admin/api/access-events');
        const events = resp.events || [];
        $('#table-access-events').innerHTML = `<tr><th>时间</th><th>IP</th><th>client_id</th><th>原因</th></tr>` +
            (events.slice().reverse().map(e => `<tr><td>${esc(e.time)}</td><td>${esc(e.ip)}</td><td>${esc(e.client_id)}</td><td>${esc(e.reason)}</td></tr>`).join('')
                || '<tr><td colspan="4" style="opacity:.5">无记录</td></tr>');
    } catch { /* ignore */ }
}

async function loadAccessSettings() {
    const s = await api('/admin/api/settings');
    const st = s.settings;
    $('#ac-rate-limit').value = st.request_rate_limit;
    $('#ac-rate-window').value = st.request_rate_window_seconds;
    $('#ac-concurrency').value = st.max_compute_concurrency;
    $('#ac-retry').value = st.task_retry_count;
    $('#ac-reserve').value = st.gpu_memory_reserve_mb;
}

// ---------- 告警通知 ----------

async function loadNotifyTab() {
    const s = await api('/admin/api/settings');
    const n = s.settings.notifications || {};
    $('#nf-toast').checked = !!n.system_toast;
    $('#nf-sound').checked = !!n.system_sound;
    $('#nf-pushplus').checked = !!n.pushplus_enabled;
    $('#nf-token').value = '';
    $('#nf-token').placeholder = n.pushplus_token_configured ? '已配置，留空表示保持不变' : '请输入 PushPlus Token';
    $('#nf-topic').value = n.pushplus_topic || '';
    $('#nf-backlog').value = n.queue_backlog_threshold ?? 10;
    $('#nf-gpu-temp').value = n.gpu_temp_threshold ?? 85;
    $$('.nf-event').forEach(cb => { cb.checked = (n.alert_events || []).includes(cb.value); });
    renderAlerts();
}

function renderAlerts() {
    const alerts = state.alerts || [];
    $('#table-alerts').innerHTML = `<tr><th>时间</th><th>事件</th><th>详情</th></tr>` +
        (alerts.slice().reverse().map(a => `<tr><td>${esc(a.time)}</td><td>${esc(a.event)}</td><td>${esc(a.detail)}</td></tr>`).join('')
            || '<tr><td colspan="3" style="opacity:.5">暂无告警</td></tr>');
}

// ---------- 日志 ----------

function renderLogs() {
    const level = $('#log-level').value;
    const search = ($('#log-search').value || '').toLowerCase();
    const box = $('#log-stream');
    const filtered = state.logs.filter(l => {
        if (level && !l.message.includes(`[${level}]`)) return false;
        if (search && !l.message.toLowerCase().includes(search)) return false;
        return true;
    });
    box.innerHTML = filtered.map(l => `<div class="log-line lv-${l.message.includes('[ERROR]') ? 'ERROR' : l.message.includes('[WARNING]') ? 'WARNING' : ''}">${esc(l.message)}</div>`).join('');
    box.scrollTop = box.scrollHeight;
    $('#log-file-path').textContent = `本次日志文件：${state.logFile || '未知'}`;
}

async function loadLogFile() {
    try {
        const resp = await api('/admin/api/logs?since=0');
        state.logs = resp.entries || [];
        state.logFile = resp.file;
        renderLogs();
    } catch { /* ignore */ }
}

async function loadLogFiles() {
    try {
        const resp = await api('/admin/api/logs/files');
        const select = $('#log-download-file');
        select.innerHTML = '';
        (resp.files || []).forEach(file => {
            const option = document.createElement('option');
            option.value = file.name;
            option.textContent = file.name;
            select.appendChild(option);
        });
        if (resp.current) select.value = resp.current;
    } catch { /* ignore */ }
}

// ---------- 系统设置 ----------

function renderServiceInfo() {
    const info = window.ADMIN_CONFIG.service_info || {};
    const target = $('#service-info');
    if (!target) return;
    target.innerHTML = [
        ['软件版本', window.ADMIN_CONFIG.version],
        ['Python 版本', info.python],
        ['CUDA 版本', info.cuda],
        ['Pytorch 版本', info.torch],
        ['CPU 型号', info.cpu],
        ['GPU 型号', info.gpu],
        ['计算硬件', info.hardware],
    ].map(([k, v]) => `<span class="status-k">${k}</span><span class="status-v">${esc(v ?? '-')}</span>`).join('');
}

async function loadSettingsTab() {
    const s = await api('/admin/api/settings');
    const st = s.settings;
    $('#set-port').value = st.port;
    $('#set-admin-port').value = st.admin_port;
    $('#set-auto-browser').checked = !!st.auto_open_browser;
    $('#set-auto-admin-browser').checked = !!st.auto_open_admin_browser;
    $('#set-timeout').value = st.task_timeout_seconds;
    $('#set-retry').value = st.task_retry_count;
    $('#set-rate-limit').value = st.request_rate_limit;
    $('#set-rate-window').value = st.request_rate_window_seconds;
    $('#set-concurrency').value = st.max_compute_concurrency;
    $('#set-reserve').value = st.gpu_memory_reserve_mb;
    $('#set-result-ttl').value = st.task_result_ttl_minutes;
    $('#set-cache-limit').value = st.max_cache_mb;
}

function collectSettings() {
    const num = (id, lo, hi, fallback) => {
        const v = parseInt($(id).value);
        return isNaN(v) ? fallback : Math.min(hi, Math.max(lo, v));
    };
    return {
        port: num('#set-port', 1024, 65535, 5000),
        admin_port: num('#set-admin-port', 1024, 65535, 5001),
        auto_open_browser: $('#set-auto-browser').checked,
        auto_open_admin_browser: $('#set-auto-admin-browser').checked,
        task_timeout_seconds: num('#set-timeout', 10, 86400, 300),
        task_retry_count: num('#set-retry', 0, 10, 1),
        request_rate_limit: num('#set-rate-limit', 1, 100000, 10),
        request_rate_window_seconds: num('#set-rate-window', 1, 3600, 60),
        max_compute_concurrency: num('#set-concurrency', 1, 16, 1),
        gpu_memory_reserve_mb: num('#set-reserve', 0, 8192, 512),
        task_result_ttl_minutes: num('#set-result-ttl', 1, 1440, 30),
        max_cache_mb: num('#set-cache-limit', 64, 65536, 1024),
    };
}

// ---------- 初始化与事件绑定 ----------

function bindNav() {
    $$('.admin-nav-btn').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));
}

function bindActions() {
    $('#op-clear-cache').addEventListener('click', async () => {
        try { await api('/admin/api/clear-all-cache', { method: 'POST' }); showToast('全局缓存已清理', 'success'); }
        catch (err) { showToast(err.message, 'error'); }
    });
    const cancelAll = async () => {
        try { await api('/admin/api/tasks/cancel-all', { method: 'POST' }); showToast('已中断所有任务'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    };
    $('#op-cancel-all').addEventListener('click', cancelAll);
    $('#task-cancel-all').addEventListener('click', cancelAll);
    $('#op-reset-counters').addEventListener('click', async () => {
        if (!confirm('确认重置全部客户端的累计计数（请求数、任务数、成功/失败/取消数、累计计算时长）？客户端记录等其他数据不受影响。')) return;
        try {
            await api('/admin/api/counters/reset', { method: 'POST' });
            showToast('累计计数已重置', 'success');
            refreshAll();
        }
        catch (err) { showToast(err.message, 'error'); }
    });
    $('#op-clear-stats').addEventListener('click', async () => {
        if (!confirm('确认清除全部统计数据（客户端记录、峰值与累计时长）？此操作不可恢复。')) return;
        try {
            await api('/admin/api/stats/clear', { method: 'POST' });
            showToast('统计数据已清除', 'success');
            refreshAll();
        }
        catch (err) { showToast(err.message, 'error'); }
    });
    const shutdown = async () => {
        if (!confirm('确认停止所有服务？')) return;
        try { await api('/admin/api/shutdown', { method: 'POST' }); showToast('服务正在停止...'); }
        catch (err) { showToast(err.message, 'error'); }
    };
    $('#op-shutdown').addEventListener('click', shutdown);
    $('#op-shutdown-2').addEventListener('click', shutdown);

    $('#op-export-report').addEventListener('click', () => {
        const type = $('#report-type').value;
        const format = $('#report-format').value;
        window.open(`/admin/api/reports?type=${type}&format=${format}`, '_blank');
    });

    const clearQueue = async () => {
        if (!confirm('确认清空所有等待中的任务？正在计算的任务不受影响。')) return;
        try {
            const r = await api('/admin/api/tasks/clear-queue', { method: 'POST' });
            showToast(`已清空 ${r.cleared} 个任务`);
            refreshAll();
        } catch (err) { showToast(err.message, 'error'); }
    };
    $('#op-clear-queue').addEventListener('click', clearQueue);
    $('#task-clear-queue').addEventListener('click', clearQueue);
    $('#task-refresh').addEventListener('click', refreshAll);
    $('#client-refresh').addEventListener('click', refreshAll);

    $('#client-clear-all-cache').addEventListener('click', async () => {
        try { await api('/admin/api/clear-all-cache', { method: 'POST' }); showToast('已清空所有缓存', 'success'); }
        catch (err) { showToast(err.message, 'error'); }
    });
    $('#client-clear-stats').addEventListener('click', async () => {
        if (!confirm('确认清除全部统计？此操作不可恢复。')) return;
        try { await api('/admin/api/stats/clear', { method: 'POST' }); showToast('统计已清除', 'success'); refreshAll(); }
        catch (err) { showToast(err.message, 'error'); }
    });

    // 名单添加
    $$('.list-editor').forEach(editor => {
        const input = editor.querySelector('.list-input');
        const btn = editor.querySelector('.list-items + .btn-row button, .btn-row button');
        btn.addEventListener('click', async () => {
            const entry = input.value.trim();
            if (!entry) return;
            try {
                await api('/admin/api/access-control', {
                    method: 'POST',
                    body: { action: 'add', list: editor.dataset.list, kind: editor.dataset.kind, entry },
                });
                input.value = '';
                showToast('已添加', 'success');
                await loadAccessLists();
            } catch (err) { showToast(err.message, 'error'); }
        });
    });

    $('#ac-save').addEventListener('click', async () => {
        try {
            await api('/admin/api/settings', {
                method: 'POST',
                body: {
                    request_rate_limit: parseInt($('#ac-rate-limit').value) || 10,
                    request_rate_window_seconds: parseInt($('#ac-rate-window').value) || 60,
                    max_compute_concurrency: parseInt($('#ac-concurrency').value) || 1,
                    task_retry_count: parseInt($('#ac-retry').value) || 0,
                    gpu_memory_reserve_mb: parseInt($('#ac-reserve').value) || 0,
                },
            });
            showToast('限制设置已保存（部分项需重启生效）', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    });

    $('#nf-save').addEventListener('click', async () => {
        try {
            const notifications = {
                system_toast: $('#nf-toast').checked,
                system_sound: $('#nf-sound').checked,
                pushplus_enabled: $('#nf-pushplus').checked,
                pushplus_topic: $('#nf-topic').value.trim(),
                queue_backlog_threshold: parseInt($('#nf-backlog').value) || 10,
                gpu_temp_threshold: parseInt($('#nf-gpu-temp').value) || 85,
                alert_events: Array.from($$('.nf-event')).filter(cb => cb.checked).map(cb => cb.value),
            };
            const token = $('#nf-token').value.trim();
            if (token) notifications.pushplus_token = token;
            await api('/admin/api/settings', {
                method: 'POST',
                body: { notifications },
            });
            showToast('通知设置已保存', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    });
    $('#nf-test').addEventListener('click', async () => {
        try { await api('/admin/api/notifications/test', { method: 'POST' }); showToast('测试推送已发送'); }
        catch (err) { showToast(err.message, 'error'); }
    });

    $('#log-level').addEventListener('change', renderLogs);
    $('#log-search').addEventListener('input', renderLogs);
    $('#log-clear-view').addEventListener('click', () => { state.logs = []; renderLogs(); });
    $('#log-download').addEventListener('click', async () => {
        const filename = $('#log-download-file').value;
        if (!filename) { showToast('暂无可下载的日志文件', 'error'); return; }
        try {
            const resp = await api(`/admin/api/logs/download?filename=${encodeURIComponent(filename)}`, { raw: true });
            const blob = await resp.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = filename;
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (err) { showToast('下载失败：' + err.message, 'error'); }
    });

    $('#set-save').addEventListener('click', async () => {
        try {
            const resp = await api('/admin/api/settings', { method: 'POST', body: collectSettings() });
            showToast(resp.restart_required ? '已保存，端口等启动项需重启生效' : '已保存', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    });
    $('#set-reset').addEventListener('click', async () => {
        if (!confirm('确认恢复默认设置？')) return;
        try {
            await api('/admin/api/settings/reset', { method: 'POST' });
            showToast('已恢复默认，重启后完全生效', 'success');
            await loadSettingsTab();
        } catch (err) { showToast(err.message, 'error'); }
    });
}

async function loadAlerts() {
    // 告警缓冲通过设置接口旁路获取成本高，这里以独立轻量端点不可行——复用 metrics 轮询
    try {
        const resp = await api('/admin/api/alerts');
        state.alerts = resp.alerts || [];
        renderAlerts();
    } catch { /* ignore */ }
}

document.addEventListener('DOMContentLoaded', () => {
    renderServiceInfo();
    initCustomSelect();
    bindNav();
    bindActions();
    connectWS();
    refreshAll();
    loadAccessLists();
    loadAccessSettings();
    loadLogFile();
    loadLogFiles();
    loadAlerts();
    setInterval(loadAlerts, 10000);
    // 运行时长本地每秒走字；仅在与服务保持连接时增长（断线暂停，软件关闭清空）
    setInterval(() => {
        if (state.connected) {
            const up = uptimeSeconds();
            if (up != null) $('#stat-uptime').textContent = fmtDuration(up);
        }
    }, 1000);
});
