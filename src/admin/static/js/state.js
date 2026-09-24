// 后台状态、路由常量、API 封装、通用工具与入口

// 后台全局状态与路由常量
// 后台管理中心交互逻辑 —— 复用主界面 i18n 与主题变量

const state = {
    metrics: null,          // 最新监控指标
    monitorHistory: [],     // 实时监控页面专用的图像缓冲
    peaks: {},
    counts: { waiting: 0, running: 0 },
    clientsSummary: {},
    clients: [],
    tasks: { running: [], waiting: [], history: [], dead: [] },
    lists: { blacklist: { ips: [], client_ids: [] }, whitelist: { ips: [], client_ids: [] } },
    listsLoaded: false,
    logs: [],               // 内存日志缓冲
    selectedLogFile: '',    // 当前日志显示与下载的文件
    currentLogFile: '',     // 当前运行日志文件名
    alerts: [],             // 后台告警缓冲
    alertsInitialized: false, // 首次加载历史告警时不重复弹出浏览器通知
    monitorCategory: 'overview', // 实时监控当前性能分类
    monitorViewMode: 'full', // full / compact：完整视图或紧凑视图
    monitorPhase: 'idle',   // idle / recording / finishing
    monitorStopTimer: null, // 离开实时监控页面后的60秒收尾计时器
    gpuPowerAxisModes: {},  // GPU 功耗图纵轴模式：静态 / 动态
    cpuPowerAxisModes: {},  // CPU 功耗图纵轴模式：静态 / 动态
    gpuTemperatureAxisModes: {}, // GPU 温度图纵轴模式：静态 / 动态
    latestMetricsTimestamp: 0, // 已接收的最新监控采样时间，避免乱序全量同步回档
    pageClosing: false, // 刷新或关闭页面时不再为旧连接安排重连
    ws: null,
    activeTab: 'tab-overview',
    startedAt: null,   // 软件进程启动时间（epoch 毫秒），由服务端 metrics 消息下发
    pausedAccum: 0,    // 断线期间暂停的累计秒数（不计入运行时长）
    pausedAt: null,    // 本次断开的时刻（epoch 毫秒）
    pendingResume: false, // 重连后待判定：软件未重启则从暂停处继续，重启则重新计时
    connected: false,  // 与后台服务的 WS 连接状态：断开时暂停运行时长走字
    persistedMonitorStartedAt: null, // 刷新前缓冲所属的软件运行实例
    selectedClientIds: new Set(), // 客户端批量操作选中的客户端
};

const MONITOR_WINDOW = 60;
const MONITOR_HISTORY_LIMIT = MONITOR_WINDOW;
const MONITOR_HISTORY_STORAGE_KEY = 'admin_monitor_history';
const ADMIN_TAB_STORAGE_KEY = 'admin_active_tab';
const MONITOR_CATEGORY_STORAGE_KEY = 'admin_monitor_category';
const MONITOR_VIEW_STORAGE_KEY = 'admin_monitor_view_mode';
const MONITOR_VIEW_PATHS = {
    full: '/admin/monitor/full',
    compact: '/admin/monitor/compact',
};
const MONITOR_VIEW_MODES = new Set(Object.keys(MONITOR_VIEW_PATHS));
const MONITOR_CATEGORY_PATHS = {
    overview: '/admin/monitor',
    cpu: '/admin/monitor/cpu',
    memory: '/admin/monitor/memory',
    gpu: '/admin/monitor/gpu',
    disk: '/admin/monitor/disk',
    network: '/admin/monitor/network',
    service: '/admin/monitor/service',
};
const MONITOR_PATH_CATEGORIES = Object.fromEntries(
    Object.entries(MONITOR_CATEGORY_PATHS).map(([category, path]) => [path, category])
);

function monitorViewFromUrl() {
    const pathMode = Object.entries(MONITOR_VIEW_PATHS).find(([, path]) => location.pathname === path)?.[0];
    if (pathMode) return pathMode;
    const queryMode = new URLSearchParams(location.search).get('view');
    return MONITOR_VIEW_MODES.has(queryMode) ? queryMode : null;
}

function monitorPathFor(category, mode) {
    const view = MONITOR_VIEW_MODES.has(mode) ? mode : 'full';
    if (category === 'overview') return MONITOR_VIEW_PATHS[view];
    return `${MONITOR_CATEGORY_PATHS[category]}?view=${encodeURIComponent(view)}`;
}
const ADMIN_TAB_PATHS = {
    'tab-overview': '/admin/',
    'tab-monitor': '/admin/monitor',
    'tab-tasks': '/admin/tasks',
    'tab-clients': '/admin/clients',
    'tab-access': '/admin/access',
    'tab-notify': '/admin/notify',
    'tab-logs': '/admin/logs',
    'tab-settings': '/admin/settings',
};
const ADMIN_PATH_TABS = {
    ...Object.fromEntries(Object.entries(ADMIN_TAB_PATHS).map(([tab, path]) => [path, tab])),
    '/admin/pushplus': 'tab-notify',
    ...Object.fromEntries(Object.values(MONITOR_CATEGORY_PATHS).map(path => [path, 'tab-monitor'])),
    ...Object.fromEntries(Object.values(MONITOR_VIEW_PATHS).map(path => [path, 'tab-monitor'])),
};

// 后台 API 请求封装（状态变更接口带安全头）
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

// 通用工具
function fmtDuration(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return h > 0 ? `${h}时${m}分` : (m > 0 ? `${m}分${s}秒` : `${s}秒`);
}
function pathSegment(value) {
    return encodeURIComponent(String(value ?? ''));
}

// 后台入口
async function loadAlerts() {
    // 告警缓冲通过设置接口旁路获取成本高，这里以独立轻量端点不可行——复用 metrics 轮询
    try {
        const resp = await api('/admin/api/alerts');
        const alerts = resp.alerts || [];
        if (state.alertsInitialized) notifyAdminBrowserAlerts(alerts, state.alerts);
        state.alerts = alerts;
        state.alertsInitialized = true;
        renderAlerts();
    } catch { /* ignore */ }
}

document.addEventListener('DOMContentLoaded', () => {
    renderServiceInfo();
    initCustomSelect();
    restoreMonitorViewMode();
    bindNav();
    bindActions();
    restorePersistedMonitorHistory();
    const savedTab = ADMIN_PATH_TABS[location.pathname] || sessionStorage.getItem(ADMIN_TAB_STORAGE_KEY);
    const monitorCategory = MONITOR_PATH_CATEGORIES[location.pathname]
        || sessionStorage.getItem(MONITOR_CATEGORY_STORAGE_KEY)
        || 'overview';
    if (MONITOR_CATEGORY_PATHS[monitorCategory]) state.monitorCategory = monitorCategory;
    if (savedTab && document.getElementById(savedTab)) switchTab(savedTab, { replace: true });
    if (state.activeTab === 'tab-monitor') {
        switchMonitorCategory(state.monitorCategory, { replace: true });
    }
    if (location.pathname === '/admin/pushplus') window.openAdminNotificationChannels?.();
    connectWS();
    refreshAll();
    loadAccessLists();
    loadAccessSettings();
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
