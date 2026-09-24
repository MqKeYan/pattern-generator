// 后台各功能页：概览、任务队列、客户端、访问控制、告警、日志、系统设置

// 概览页
// ---------- 概览 ----------

function statCard(label, value, unit = '', cls = '') {
    return `<div class="stat-card ${cls}"><div class="stat-label">${label}</div>
        <div><span class="stat-value">${value}</span><span class="stat-unit">${unit}</span></div></div>`;
}

function fmtPercentValue(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return value;
    const rounded = Math.round(number * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function fmtAdaptiveMb(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return { value: '-', unit: '' };
    const absolute = Math.abs(number);
    if (absolute >= 1024 * 1024) return { value: (number / 1024 / 1024).toFixed(2), unit: 'TB' };
    if (absolute >= 1024) return { value: (number / 1024).toFixed(2), unit: 'GB' };
    if (absolute >= 1) return { value: fmtPlotVal(number), unit: 'MB' };
    if (absolute >= 1 / 1024) return { value: (number * 1024).toFixed(2), unit: 'KB' };
    return { value: (number * 1024 * 1024).toFixed(2), unit: 'B' };
}

function renderOverview() {
    const m = state.metrics || {};
    const gpu = (m.gpus && m.gpus[0]) || {};
    const gpuMem = fmtAdaptiveMb(gpu.mem_used_mb);
    const gpuSharedMem = fmtAdaptiveMb(gpu.shared_mem_used_mb);
    const gpuTotalMem = fmtAdaptiveMb(gpu.total_graphics_mem_used_mb);
    const cards1 = [
        statCard('CPU 占用', fmtPercentValue(m.cpu_percent ?? '-'), '%', (m.cpu_percent || 0) > 90 ? 'hot' : ''),
        statCard('内存占用', fmtPercentValue(m.mem_percent ?? '-'), '%', (m.mem_percent || 0) > 90 ? 'hot' : ''),
        statCard('GPU 占用', fmtPercentValue(gpu.util_percent ?? (m.gpus ? '无' : '-')), '%'),
        statCard('GPU 内存', gpuMem.value, gpuMem.unit),
        statCard('GPU 共享内存', gpuSharedMem.value, gpuSharedMem.unit),
        statCard('GPU 总图形内存', gpuTotalMem.value, gpuTotalMem.unit),
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

// 任务队列页
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
    const hist = (state.tasks.history || []).slice(-50).reverse();
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

// 客户端管理页
// ---------- 客户端管理 ----------

function renderClients() {
    const currentIds = new Set((state.clients || []).map(c => c.client_id));
    state.selectedClientIds = new Set(
        [...state.selectedClientIds].filter(clientId => currentIds.has(clientId))
    );
    const allSelected = currentIds.size > 0 &&
        [...currentIds].every(clientId => state.selectedClientIds.has(clientId));
    const rows = (state.clients || []).map(c => `<tr>
        <td><input type="checkbox" class="client-select" value="${escAttr(c.client_id)}" ${state.selectedClientIds.has(c.client_id) ? 'checked' : ''}></td>
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
            <button class="btn btn-outline btn-accent" data-impact="low" data-remark="${escAttr(c.client_id)}" data-remark-val="${escAttr(c.remark || '')}">备注</button>
            ${c.status === 'paused'
                ? `<button class="btn btn-outline btn-success" data-impact="normal" data-resume="${escAttr(c.client_id)}">恢复</button>`
                : `<button class="btn btn-outline btn-warning" data-impact="caution" data-pause="${escAttr(c.client_id)}">暂停</button>`}
            <button class="btn btn-outline btn-danger" data-impact="danger" data-clear-cache="${escAttr(c.client_id)}">清缓存</button>
            <button class="btn btn-outline btn-danger" data-impact="danger" data-kick="${escAttr(c.client_id)}">踢出</button>
            <button class="btn btn-outline btn-danger" data-impact="danger" data-delete="${escAttr(c.client_id)}">删除</button>
        </td></tr>`).join('');
    $('#table-clients').innerHTML = `<tr><th class="client-select-all-cell"><input type="checkbox" id="client-select-all"${allSelected ? ' checked' : ''}></th><th>UUID</th><th>名称</th><th>IP</th><th>状态</th><th>当前任务</th><th>请求</th><th>成功/失败/取消</th><th>在线时长</th><th>标签</th><th>备注</th><th>操作</th></tr>` +
        (rows || '<tr><td colspan="12" style="opacity:.5">暂无客户端</td></tr>');

    const updateSelectAllState = () => {
        const selectAll = $('#client-select-all');
        if (!selectAll) return;
        const selectedCount = [...currentIds].filter(clientId => state.selectedClientIds.has(clientId)).length;
        selectAll.checked = currentIds.size > 0 && selectedCount === currentIds.size;
        selectAll.indeterminate = selectedCount > 0 && selectedCount < currentIds.size;
    };
    const updateSelectedCount = () => {
        updateSelectAllState();
        const count = state.selectedClientIds.size;
        $('#client-selected-count').textContent = `已选 ${count} 个`;
        $$('[data-client-batch]').forEach(button => { button.disabled = count === 0; });
    };
    $$('#table-clients .client-select').forEach(checkbox => checkbox.addEventListener('change', () => {
        if (checkbox.checked) state.selectedClientIds.add(checkbox.value);
        else state.selectedClientIds.delete(checkbox.value);
        updateSelectedCount();
    }));
    $('#client-select-all')?.addEventListener('change', (event) => {
        $$('#table-clients .client-select').forEach(checkbox => {
            checkbox.checked = event.target.checked;
            if (checkbox.checked) state.selectedClientIds.add(checkbox.value);
            else state.selectedClientIds.delete(checkbox.value);
        });
        updateSelectedCount();
    });
    updateSelectedCount();

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

async function runBatchClientAction(action) {
    const clientIds = [...state.selectedClientIds];
    if (!clientIds.length) return;
    if (action === 'kick' && !confirm(`确认踢出并封禁选中的 ${clientIds.length} 个客户端？`)) return;
    if (action === 'delete' && !confirm(`确认删除选中的 ${clientIds.length} 个客户端记录？`)) return;
    const body = action === 'remark' ? { remark: prompt('请输入应用到所选客户端的备注：') } : null;
    if (action === 'remark' && body.remark === null) return;

    const requests = clientIds.map(clientId => {
        const endpoint = action === 'clear-cache' ? 'clear-cache' : action;
        return api(`/admin/api/client/${pathSegment(clientId)}/${endpoint}`, { method: 'POST', body });
    });
    const results = await Promise.allSettled(requests);
    const failed = results.filter(result => result.status === 'rejected').length;
    state.selectedClientIds.clear();
    await refreshAll();
    showToast(failed ? `已完成 ${clientIds.length - failed} 个，失败 ${failed} 个` : `已完成 ${clientIds.length} 个客户端操作`, failed ? 'error' : 'success');
}

// 访问控制页
// ---------- 访问控制 ----------

async function loadAccessLists() {
    try {
        const resp = await api('/admin/api/access-control');
        state.lists = resp.lists;
        state.listsLoaded = true;
        renderLists();
    } catch (err) { showToast(err.message, 'error'); }
}

function renderLists() {
    if (!state.listsLoaded) return;
    for (const target of ['whitelist', 'blacklist']) {
        for (const kind of ['ips', 'client_ids']) {
            const box = $(`#list-${target}-${kind}`);
            if (!box) continue;
            box.innerHTML = (state.lists[target][kind] || []).map(entry =>
                `<span class="list-entry">${esc(entry)}<button data-impact="danger" data-target="${target}" data-kind="${kind}" data-entry="${escAttr(entry)}" title="删除">✕</button></span>`
            ).join('') || '<span class="list-empty"><span class="list-empty-mark" aria-hidden="true"></span><span>尚未添加条目</span></span>';
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
    $('#ac-request-body-mb').value = Math.max(1, Math.round(st.max_request_body_bytes / (1024 * 1024)));
    $('#ac-max-clients').value = st.max_clients;
    $('#ac-max-queue').value = st.max_queue_tasks;
    $('#ac-concurrency').value = st.max_compute_concurrency;
    $('#ac-reserve').value = st.gpu_memory_reserve_mb;
    $('#ac-retry').value = st.task_retry_count;
    $('#ac-timeout').value = st.task_timeout_seconds;
    $('#ac-history-tasks').value = st.max_history_tasks;
    $('#ac-dead-tasks').value = st.max_dead_tasks;
}

// 告警通知页
// ---------- 告警通知 ----------

const ADMIN_BROWSER_NOTIFICATION_STORAGE_KEY = 'admin_browser_alert_notifications';

function getAdminBrowserNotificationSettings() {
    try {
        return { enabled: false, ...JSON.parse(localStorage.getItem(ADMIN_BROWSER_NOTIFICATION_STORAGE_KEY) || '{}') };
    } catch {
        return { enabled: false };
    }
}

function saveAdminBrowserNotificationSettings(settings) {
    localStorage.setItem(ADMIN_BROWSER_NOTIFICATION_STORAGE_KEY, JSON.stringify(settings));
}

async function requestAdminBrowserNotificationPermission() {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission === 'denied') return false;
    return (await Notification.requestPermission()) === 'granted';
}

function notifyAdminBrowserAlerts(alerts, previousAlerts) {
    const settings = getAdminBrowserNotificationSettings();
    if (!settings.enabled || !('Notification' in window) || Notification.permission !== 'granted') return;
    const known = new Set((previousAlerts || []).map(alert => `${alert.time}|${alert.event}|${alert.detail}`));
    alerts.filter(alert => !known.has(`${alert.time}|${alert.event}|${alert.detail}`)).forEach(alert => {
        new Notification(`后台告警：${alert.event}`, {
            body: alert.detail,
            icon: '/static/favicon.ico',
            tag: `pattern-admin-alert-${alert.event}`,
        });
    });
}

async function testAdminBrowserNotification() {
    const settings = getAdminBrowserNotificationSettings();
    if (!settings.enabled) return;
    if (!(await requestAdminBrowserNotificationPermission())) {
        showToast('后台浏览器系统通知权限未授予', 'info');
        return;
    }
    new Notification('后台通知测试', {
        body: '后台告警浏览器系统通知已启用。',
        icon: '/static/favicon.ico',
    });
}

async function loadNotifyTab() {
    const s = await api('/admin/api/settings');
    const n = s.settings.notifications || {};
    $('#nf-toast').checked = !!n.system_toast;
    $('#nf-sound').checked = !!n.system_sound;
    $('#nf-browser').checked = !!getAdminBrowserNotificationSettings().enabled;
    const pushplusTargets = n.pushplus_targets || [];
    const channelTargets = {
        ...(n.extra_channel_targets || {}),
        pushplus_token: pushplusTargets.map(target => ({ ...target, type: 'pushplus_token' })),
    };
    window.fillAdminChannelTargets?.(channelTargets);
    $('#nf-backlog').value = n.queue_backlog_threshold ?? 10;
    $('#nf-gpu-temp').value = n.gpu_temp_threshold ?? 85;
    $('#nf-cpu').value = n.cpu_percent_threshold ?? 95;
    $('#nf-memory').value = n.memory_percent_threshold ?? 90;
    $('#nf-swap').value = n.swap_percent_threshold ?? 80;
    $('#nf-disk').value = n.disk_used_percent_threshold ?? 90;
    $('#nf-gpu-memory').value = n.gpu_memory_percent_threshold ?? 90;
    $('#nf-gpu-power').value = n.gpu_power_percent_threshold ?? 90;
    $('#nf-cpu-power').value = n.cpu_power_percent_threshold ?? 90;
    $$('.nf-event').forEach(cb => { cb.checked = (n.alert_events || []).includes(cb.value); });
    renderAlerts();
}

function renderAlerts() {
    const alerts = state.alerts || [];
    $('#table-alerts').innerHTML = `<tr><th>时间</th><th>事件</th><th>详情</th></tr>` +
        (alerts.slice().reverse().map(a => `<tr><td>${esc(a.time)}</td><td>${esc(a.event)}</td><td>${esc(a.detail)}</td></tr>`).join('')
            || '<tr><td colspan="3" style="opacity:.5">暂无告警</td></tr>');
}

// 日志页
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
}

async function loadLogFile() {
    try {
        const filename = state.selectedLogFile || '';
        const query = filename ? `?filename=${encodeURIComponent(filename)}` : '?since=0';
        const resp = await api(`/admin/api/logs${query}`);
        state.logs = resp.entries || [];
        renderLogs();
    } catch { /* ignore */ }
}

async function loadLogFiles() {
    try {
        const resp = await api('/admin/api/logs/files');
        const select = $('#log-download-file');
        const options = select.querySelector('.custom-select-options');
        options.innerHTML = '';
        (resp.files || []).forEach(file => {
            const option = document.createElement('div');
            option.className = 'custom-select-option';
            option.dataset.value = file.name;
            option.textContent = file.name;
            options.appendChild(option);
        });
        syncCustomSelectEmptyState(options);
        const fileNames = new Set((resp.files || []).map(file => file.name));
        state.currentLogFile = resp.current || state.currentLogFile;
        const selected = fileNames.has(resp.current) ? resp.current : resp.files?.[0]?.name || '';
        if (selected) {
            state.selectedLogFile = selected;
            setCustomSelectValue(select, selected);
            await loadLogFile();
        }
    } catch { /* ignore */ }
}

// 系统设置页
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
    setCustomSelectValue($('#set-monitor-default-view'), st.monitor_default_view || 'full');
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
        monitor_default_view: $('#set-monitor-default-view').value || 'full',
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

function applyMonitorDefaultView(settings) {
    const mode = settings?.monitor_default_view;
    if (!MONITOR_VIEW_MODES.has(mode) || monitorViewFromUrl()) return;
    state.monitorViewMode = mode;
    sessionStorage.setItem(MONITOR_VIEW_STORAGE_KEY, mode);
    updateMonitorViewToggle();
    if (state.activeTab === 'tab-monitor') requestAnimationFrame(renderMonitor);
}
