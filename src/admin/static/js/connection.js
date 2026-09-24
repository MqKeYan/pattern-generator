// 后台 WebSocket 连接、重连、消息分发、状态卡与运行时长

// WebSocket 连接、重连与消息分发
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
        state.ws.send(JSON.stringify({ type: 'language', lang: i18n.getLang() }));
        setConnState('实时连接已建立', 'online');
    };
    state.ws.onmessage = (e) => {
        try { handleMessage(JSON.parse(e.data)); } catch (err) { console.error('WS 消息处理失败', err); }
    };
    state.ws.onclose = () => {
        if (state.pageClosing) return;
        // 断开后立即暂停运行时长走字，并探测软件是否仍在运行
        state.connected = false;
        state.pausedAt = Date.now();
        state.pendingResume = true;
        setConnState('服务已停止，等待软件重新连接...', 'offline');
        scheduleReconnect();
    };
    state.ws.onerror = () => { try { state.ws.close(); } catch { /* ignore */ } };
}

window.addEventListener('app-language-changed', (event) => {
    if (state.ws?.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'language', lang: event.detail?.lang || i18n.getLang() }));
    }
});

window.addEventListener('pagehide', () => {
    state.pageClosing = true;
    const socket = state.ws;
    if (socket && socket.readyState < WebSocket.CLOSING) {
        try { socket.close(1000, '页面关闭'); } catch { /* ignore */ }
    }
});

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
        const metricTimestamp = Number(msg.current?.timestamp);
        if (Number.isFinite(metricTimestamp) && metricTimestamp < state.latestMetricsTimestamp) return;
        if (Number.isFinite(metricTimestamp)) state.latestMetricsTimestamp = metricTimestamp;
        const sa = msg.started_at ? msg.started_at * 1000 : null;
        if (sa && state.persistedMonitorStartedAt && state.persistedMonitorStartedAt !== sa) {
            state.monitorHistory = [];
            state.persistedMonitorStartedAt = null;
            sessionStorage.removeItem(MONITOR_HISTORY_STORAGE_KEY);
        }
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
        state.peaks = msg.peaks || {};
        state.counts = msg.counts || state.counts;
        state.clientsSummary = msg.clients_summary || {};
        appendMonitorSample(msg.current);
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
        // 只有当前显示运行日志时才追加实时日志，历史日志保持文件内容不变。
        if (!state.selectedLogFile || state.selectedLogFile === state.currentLogFile) {
            state.logs.push(...(msg.entries || []));
            if (state.logs.length > 1000) state.logs = state.logs.slice(-1000);
            if (state.activeTab === 'tab-logs') renderLogs();
        }
    }
}

// 侧边栏状态卡与运行时长
// ---------- 侧边栏状态卡 ----------

// 当前展示的运行时长（秒）：真实进程时长扣除断线暂停的累计时长；软件关闭时为 null
function uptimeSeconds() {
    if (!state.startedAt) return null;
    return Math.max(0, (Date.now() - state.startedAt) / 1000 - state.pausedAccum);
}

// 仅在实时监控记录周期内追加数据，页面离开后的收尾阶段仍继续滚动60秒。
function appendMonitorSample(current) {
    if (!current || state.monitorPhase === 'idle') return;
    const timestamp = Number(current.timestamp);
    const lastTimestamp = Number(state.monitorHistory.at(-1)?.timestamp);
    if (!Number.isFinite(timestamp) || timestamp === lastTimestamp) return;

    const sample = {
        ...current,
        online_clients: state.clientsSummary.online_clients || 0,
        running_tasks: state.counts.running || 0,
        waiting_tasks: state.counts.waiting || 0,
    };
    state.monitorHistory = [...state.monitorHistory, sample].slice(-MONITOR_HISTORY_LIMIT);
    persistMonitorHistory();
}

function persistMonitorHistory() {
    try {
        sessionStorage.setItem(MONITOR_HISTORY_STORAGE_KEY, JSON.stringify({
            startedAt: state.startedAt,
            history: state.monitorHistory,
        }));
    } catch { /* 存储不可用时仅保留当前内存缓冲 */ }
}

function restorePersistedMonitorHistory() {
    try {
        const cached = JSON.parse(sessionStorage.getItem(MONITOR_HISTORY_STORAGE_KEY) || 'null');
        const history = Array.isArray(cached?.history) ? cached.history : [];
        state.monitorHistory = history
            .filter(sample => sample && sample.time && Number.isFinite(Number(sample.timestamp)))
            .sort((left, right) => Number(left.timestamp) - Number(right.timestamp))
            .slice(-MONITOR_HISTORY_LIMIT);
        const startedAt = Number(cached?.startedAt);
        state.persistedMonitorStartedAt = Number.isFinite(startedAt) ? startedAt : null;
    } catch {
        sessionStorage.removeItem(MONITOR_HISTORY_STORAGE_KEY);
    }
}

function restoreMonitorViewMode() {
    try {
        const urlMode = monitorViewFromUrl();
        if (urlMode) {
            state.monitorViewMode = urlMode;
            return;
        }
        if (MONITOR_VIEW_MODES.has(window.ADMIN_CONFIG.monitor_default_view)) {
            state.monitorViewMode = window.ADMIN_CONFIG.monitor_default_view;
        } else {
            const savedMode = sessionStorage.getItem(MONITOR_VIEW_STORAGE_KEY);
            if (savedMode === 'compact' || savedMode === 'full') state.monitorViewMode = savedMode;
        }
    } catch { /* 存储不可用时使用默认完整视图 */ }
}

function startMonitorRecording() {
    if (state.monitorStopTimer) {
        clearTimeout(state.monitorStopTimer);
        state.monitorStopTimer = null;
    }
    // 返回页面时保留上一轮缓冲，只把新采样接到右侧。
    state.monitorPhase = 'recording';
    appendMonitorSample(state.metrics);
}

function finishMonitorRecording() {
    if (state.monitorPhase !== 'recording') return;
    state.monitorPhase = 'finishing';
    state.monitorStopTimer = setTimeout(() => {
        state.monitorPhase = 'idle';
        state.monitorStopTimer = null;
    }, MONITOR_WINDOW * 1000);
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
