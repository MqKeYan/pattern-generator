// 后台标签与监控分类切换、导航与操作按钮绑定

// 标签页与监控分类切换
// ---------- 标签页切换 ----------

function switchMonitorCategory(category, { replace = false } = {}) {
    const targetPath = monitorPathFor(category, state.monitorViewMode);
    if (!targetPath) return;
    state.monitorCategory = category;
    sessionStorage.setItem(MONITOR_CATEGORY_STORAGE_KEY, category);
    $$('.monitor-category-btn').forEach(button => {
        button.classList.toggle('active', button.dataset.monitorCategory === category);
    });
    if (state.activeTab === 'tab-monitor' && location.pathname !== targetPath) {
        const method = replace ? 'replaceState' : 'pushState';
        history[method]({}, '', targetPath);
    }
    clearMonitorTiles();
    requestAnimationFrame(renderMonitor);
}

function switchTab(tabId, { replace = false } = {}) {
    const enteringMonitor = state.activeTab !== 'tab-monitor' && tabId === 'tab-monitor';
    const leavingMonitor = state.activeTab === 'tab-monitor' && tabId !== 'tab-monitor';
    if (leavingMonitor) finishMonitorRecording();
    if (enteringMonitor) startMonitorRecording();
    const monitorCategory = MONITOR_PATH_CATEGORIES[location.pathname];
    const currentMonitorPath = monitorCategory || monitorViewFromUrl();
    const monitorPath = monitorPathFor('overview', state.monitorViewMode);
    const targetPath = tabId === 'tab-notify' && location.pathname === '/admin/pushplus'
        ? location.pathname
        : (tabId === 'tab-monitor' && replace && currentMonitorPath
        ? `${location.pathname}${location.search}`
        : (tabId === 'tab-monitor' ? monitorPath : ADMIN_TAB_PATHS[tabId]));
    if (targetPath && location.pathname + location.search !== targetPath) {
        const method = replace ? 'replaceState' : 'pushState';
        history[method]({}, '', targetPath);
    }
    sessionStorage.setItem(ADMIN_TAB_STORAGE_KEY, tabId);
    state.activeTab = tabId;
    $$('.admin-nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
    $$('.tab-panel').forEach(p => p.classList.toggle('active', p.id === tabId));
    if (tabId === 'tab-monitor') requestAnimationFrame(renderMonitor);
    if (tabId === 'tab-overview') renderOverview();
    if (tabId === 'tab-tasks') renderTasks(), renderDead();
    if (tabId === 'tab-clients') renderClients();
    if (tabId === 'tab-access') { renderLists(); loadAccessEvents(); }
    if (tabId === 'tab-notify') loadNotifyTab();
    if (tabId === 'tab-logs') renderLogs();
    if (tabId === 'tab-settings') loadSettingsTab();
}

// 导航绑定
// ---------- 初始化与事件绑定 ----------

function bindNav() {
    $$('.admin-nav-btn').forEach(b => b.addEventListener('click', () => {
        if (b.dataset.tab === 'tab-monitor') {
            state.monitorCategory = 'overview';
            sessionStorage.setItem(MONITOR_CATEGORY_STORAGE_KEY, 'overview');
            $$('.monitor-category-btn').forEach(button => {
                button.classList.toggle('active', button.dataset.monitorCategory === 'overview');
            });
            monitorTilesBuilt = null;
        }
        switchTab(b.dataset.tab);
    }));
    $$('.monitor-category-btn').forEach(button => {
        button.addEventListener('click', () => switchMonitorCategory(button.dataset.monitorCategory));
    });
    $('#monitor-view-toggle')?.addEventListener('click', switchMonitorViewMode);
    updateMonitorViewToggle();
}

window.addEventListener('popstate', () => {
    if (location.pathname === '/admin/pushplus') {
        const tabId = ADMIN_PATH_TABS[location.pathname];
        if (tabId) switchTab(tabId, { replace: true });
        window.openAdminNotificationChannels?.();
        return;
    }
    window.closeAdminNotificationChannels?.();
    const tabId = ADMIN_PATH_TABS[location.pathname];
    if (!tabId) return;
    switchTab(tabId, { replace: true });
    const category = MONITOR_PATH_CATEGORIES[location.pathname];
    if (category) switchMonitorCategory(category, { replace: true });
});

// 操作按钮事件绑定
function bindActions() {
    const notificationModal = document.getElementById('admin-notification-channel-modal');
    const notificationContent = document.querySelector('#admin-notification-channel-modal .admin-notification-channel-modal-content');
    const notificationHeader = document.querySelector('#admin-notification-channel-modal .admin-notification-channel-header');
    const channelEditorModal = document.getElementById('admin-channel-editor-modal');
    const channelEditorContent = document.querySelector('#admin-channel-editor-modal .admin-pushplus-target-editor-modal-content');
    const channelEditorHeader = document.getElementById('admin-channel-editor-header');
    let notificationDragging = false;
    let notificationOffsetX = 0;
    let notificationOffsetY = 0;
    let notificationPosition = null;
    const channelDefinitions = {
        pushplus_token: { label: 'PushPlus Token', required: ['token'], fields: [{ key: 'token', label: 'PushPlus Token', type: 'password', secret: true }] },
        webhook: { label: '通用 Webhook', required: ['url'], fields: [{ key: 'url', label: 'Webhook 地址', type: 'url', secret: true }] },
        email: { label: 'SMTP 邮件', required: ['host', 'recipient'], fields: [{ key: 'host', label: 'SMTP 服务器', type: 'text' }, { key: 'port', label: 'SMTP 端口', type: 'number' }, { key: 'ssl', label: 'SSL 加密', type: 'checkbox' }, { key: 'starttls', label: 'STARTTLS', type: 'checkbox' }, { key: 'username', label: 'SMTP 用户名', type: 'text' }, { key: 'password', label: 'SMTP 密码', type: 'password', secret: true }, { key: 'sender', label: '发件地址', type: 'email' }, { key: 'recipient', label: '收件地址', type: 'email' }] },
        telegram: { label: 'Telegram', required: ['token', 'chat_id'], fields: [{ key: 'token', label: 'Bot Token', type: 'password', secret: true }, { key: 'chat_id', label: 'Chat ID', type: 'text' }] },
        discord: { label: 'Discord', required: ['url'], fields: [{ key: 'url', label: 'Webhook 地址', type: 'url', secret: true }] },
        dingtalk: { label: '钉钉机器人', required: ['url'], fields: [{ key: 'url', label: 'Webhook 地址', type: 'url', secret: true }, { key: 'secret', label: '签名密钥', type: 'password', secret: true }] },
        feishu: { label: '飞书机器人', required: ['url'], fields: [{ key: 'url', label: 'Webhook 地址', type: 'url', secret: true }, { key: 'secret', label: '签名密钥', type: 'password', secret: true }] },
        wecom: { label: '企业微信机器人', required: ['url'], fields: [{ key: 'url', label: 'Webhook 地址', type: 'url', secret: true }] },
    };
    let channelTargets = [];
    let editingChannelTargetId = null;
    let channelEditorDragging = false;
    let channelEditorOffsetX = 0;
    let channelEditorOffsetY = 0;
    let channelEditorPosition = null;

    const newChannelTargetId = () => `ct_${crypto.randomUUID().replace(/-/g, '')}`;
    const flattenChannelTargets = grouped => Object.entries(grouped || {}).flatMap(([type, targets]) => (Array.isArray(targets) ? targets : []).map(target => ({ ...target, type })));
    const groupChannelTargets = targets => {
        const grouped = {};
        Object.keys(channelDefinitions).forEach(type => { grouped[type] = []; });
        targets.forEach(({ type, ...target }) => { if (grouped[type]) grouped[type].push(target); });
        return grouped;
    };
    const targetDefinition = target => channelDefinitions[target.type] || channelDefinitions.pushplus_token;
    const fieldConfigured = (target, field) => String(target[field.key] || '').trim() || !!target[`${field.key}_configured`];
    const resetChannelEditor = (type = 'pushplus_token') => {
        editingChannelTargetId = null;
        $('#nf-channel-editor-title').textContent = '新增第三方推送目标';
        $('#nf-channel-name').value = '';
        setCustomSelectValue($('#nf-channel-type'), type);
        renderChannelFields();
    };
    const renderChannelFields = target => {
        const type = $('#nf-channel-type').value || 'pushplus_token';
        const definition = channelDefinitions[type];
        $('#nf-channel-fields').innerHTML = definition.fields.map(field => field.type === 'checkbox'
            ? `<label class="settings-checkbox"><input type="checkbox" id="nf-channel-field-${field.key}"${target?.[field.key] !== false ? ' checked' : ''}><span>${esc(field.label)}</span></label>`
            : `<label><span>${esc(field.label)}</span><input type="${field.type}" id="nf-channel-field-${field.key}" class="num-input"></label>`).join('');
        definition.fields.forEach(field => {
            const input = $(`#nf-channel-field-${field.key}`);
            if (!input) return;
            if (field.type === 'checkbox') return;
            input.value = target?.[field.key] || (field.key === 'port' ? 465 : '');
            if (field.secret && target?.[`${field.key}_configured`]) input.placeholder = '已配置，留空表示保持不变';
        });
    };
    const renderChannelTargets = () => {
        const list = $('#nf-channel-list');
        if (!channelTargets.length) { list.innerHTML = '<div class="admin-pushplus-empty">暂无第三方推送目标</div>'; return; }
        list.innerHTML = `<table class="admin-pushplus-table"><thead><tr><th>平台</th><th>目标名称</th><th>状态</th><th>配置</th><th>操作</th></tr></thead><tbody>${channelTargets.map(target => {
            const definition = targetDefinition(target);
            const configured = definition.required.every(key => fieldConfigured(target, definition.fields.find(field => field.key === key) || { key }));
            return `<tr><td>${esc(definition.label)}</td><td>${esc(target.name)}</td><td><label class="admin-pushplus-target-toggle"><input type="checkbox" data-channel-action="toggle" data-target-id="${escAttr(target.id)}"${target.enabled ? ' checked' : ''}><span>${target.enabled ? '启用' : '停用'}</span></label></td><td>${configured ? '已配置' : '未配置'}</td><td class="admin-pushplus-target-actions"><button type="button" data-channel-action="edit" data-target-id="${escAttr(target.id)}">编辑</button><button type="button" data-channel-action="delete" data-target-id="${escAttr(target.id)}">删除</button></td></tr>`;
        }).join('')}</tbody></table>`;
    };
    function closeChannelEditor() { channelEditorModal?.classList.remove('show'); channelEditorModal?.setAttribute('aria-hidden', 'true'); }
    function openChannelEditor(target = null, type = 'pushplus_token') {
        resetChannelEditor(target?.type || type);
        if (target) { editingChannelTargetId = target.id; $('#nf-channel-editor-title').textContent = '编辑第三方推送目标'; $('#nf-channel-name').value = target.name; setCustomSelectValue($('#nf-channel-type'), target.type); renderChannelFields(target); }
        if (channelEditorPosition) { channelEditorContent.style.left = channelEditorPosition.left + 'px'; channelEditorContent.style.top = channelEditorPosition.top + 'px'; channelEditorContent.style.transform = 'none'; }
        else { channelEditorContent.style.left = ''; channelEditorContent.style.top = ''; channelEditorContent.style.transform = ''; }
        channelEditorModal?.classList.add('show'); channelEditorModal?.setAttribute('aria-hidden', 'false'); $('#nf-channel-name').focus();
    }

    function closeAdminNotificationChannels() {
        closeChannelEditor();
        notificationModal?.classList.remove('show');
        notificationModal?.setAttribute('aria-hidden', 'true');
        if (location.pathname === '/admin/pushplus') history.replaceState({}, '', '/admin/notify');
    }

    function openAdminNotificationChannels() {
        if (location.pathname !== '/admin/pushplus') history.pushState({}, '', '/admin/pushplus');
        if (notificationPosition) {
            notificationContent.style.left = notificationPosition.left + 'px';
            notificationContent.style.top = notificationPosition.top + 'px';
            notificationContent.style.transform = 'none';
        } else {
            notificationContent.style.left = '';
            notificationContent.style.top = '';
            notificationContent.style.transform = '';
        }
        notificationModal.classList.add('show');
        notificationModal.setAttribute('aria-hidden', 'false');
        closeChannelEditor();
        loadNotifyTab();
    }

    notificationHeader?.addEventListener('mousedown', event => {
        if (event.button !== 0) return;
        notificationDragging = true;
        const rect = notificationContent.getBoundingClientRect();
        notificationOffsetX = event.clientX - rect.left;
        notificationOffsetY = event.clientY - rect.top;
        notificationContent.style.cursor = 'grabbing';
        event.preventDefault();
    });
    document.addEventListener('mousemove', event => {
        if (!notificationDragging) return;
        const left = event.clientX - notificationOffsetX;
        const top = event.clientY - notificationOffsetY;
        notificationContent.style.left = left + 'px';
        notificationContent.style.top = top + 'px';
        notificationContent.style.transform = 'none';
        notificationPosition = { left, top };
    });
    document.addEventListener('mouseup', () => {
        if (!notificationDragging) return;
        notificationDragging = false;
        notificationContent.style.cursor = '';
        notificationHeader.style.cursor = 'move';
    });
    notificationModal?.addEventListener('click', event => {
        if (event.target === notificationModal) closeAdminNotificationChannels();
    });
    channelEditorHeader?.addEventListener('mousedown', event => {
        if (event.button !== 0) return;
        channelEditorDragging = true;
        const rect = channelEditorContent.getBoundingClientRect();
        channelEditorOffsetX = event.clientX - rect.left;
        channelEditorOffsetY = event.clientY - rect.top;
        channelEditorContent.style.cursor = 'grabbing';
        event.preventDefault();
    });
    document.addEventListener('mousemove', event => {
        if (!channelEditorDragging) return;
        const left = event.clientX - channelEditorOffsetX;
        const top = event.clientY - channelEditorOffsetY;
        channelEditorContent.style.left = left + 'px';
        channelEditorContent.style.top = top + 'px';
        channelEditorContent.style.transform = 'none';
        channelEditorPosition = { left, top };
    });
    document.addEventListener('mouseup', () => {
        if (!channelEditorDragging) return;
        channelEditorDragging = false;
        channelEditorContent.style.cursor = '';
        channelEditorHeader.style.cursor = 'move';
    });
    channelEditorModal?.addEventListener('click', event => {
        if (event.target === channelEditorModal) closeChannelEditor();
    });
    $('#nf-open-channels').addEventListener('click', openAdminNotificationChannels);
    $('#nf-channel-cancel').addEventListener('click', closeAdminNotificationChannels);
    $('#nf-channel-restore').addEventListener('click', () => {
        channelTargets = [];
        renderChannelTargets();
        resetChannelEditor();
        closeChannelEditor();
        showToast('第三方推送目标已恢复默认', 'success');
    });
    $('#nf-channel-add').addEventListener('click', () => openChannelEditor());
    $('#nf-channel-editor-cancel').addEventListener('click', closeChannelEditor);
    $('#nf-channel-type').addEventListener('change', () => renderChannelFields());
    $('#nf-channel-target-save').addEventListener('click', () => {
        const type = $('#nf-channel-type').value || 'pushplus_token';
        const definition = channelDefinitions[type];
        const name = $('#nf-channel-name').value.trim();
        const existing = channelTargets.find(target => target.id === editingChannelTargetId);
        const target = { ...(existing || {}), id: editingChannelTargetId || newChannelTargetId(), type, name: name.slice(0, 40), enabled: existing?.enabled ?? true };
        definition.fields.forEach(field => { const input = $(`#nf-channel-field-${field.key}`); target[field.key] = field.type === 'checkbox' ? !!input.checked : input.value.trim().slice(0, 1024); });
        const configured = definition.required.every(key => fieldConfigured(target, definition.fields.find(field => field.key === key) || { key }));
        if (!name || !configured) { showToast('请填写目标名称并完成平台配置', 'error'); return; }
        if (!editingChannelTargetId && channelTargets.length >= 20) { showToast('最多可配置20个第三方推送目标', 'error'); return; }
        const index = channelTargets.findIndex(item => item.id === target.id); if (index >= 0) channelTargets[index] = { ...existing, ...target }; else channelTargets.push(target);
        renderChannelTargets(); closeChannelEditor();
    });
    $('#nf-channel-list').addEventListener('click', event => {
        const addButton = event.target.closest('[data-channel-add-type]');
        if (addButton) { openChannelEditor(null, addButton.dataset.channelAddType); return; }
        const button = event.target.closest('[data-channel-action]');
        if (!button) return;
        const index = channelTargets.findIndex(target => target.id === button.dataset.targetId);
        if (index < 0) return;
        if (button.dataset.channelAction === 'toggle') {
            channelTargets[index].enabled = button.checked;
            renderChannelTargets();
            return;
        }
        if (button.dataset.channelAction === 'edit') openChannelEditor(channelTargets[index]);
        if (button.dataset.channelAction === 'delete') {
            channelTargets.splice(index, 1);
            renderChannelTargets();
            closeChannelEditor();
        }
    });
    window.fillAdminChannelTargets = grouped => {
        channelTargets = flattenChannelTargets(grouped);
        renderChannelTargets();
        resetChannelEditor();
    };
    window.readAdminChannelTargets = () => groupChannelTargets(channelTargets);
    window.openAdminNotificationChannels = openAdminNotificationChannels;
    window.closeAdminNotificationChannels = closeAdminNotificationChannels;

    $('#nf-channel-settings-save').addEventListener('click', async () => {
        try {
            const grouped = window.readAdminChannelTargets();
            const pushplusTargets = grouped.pushplus_token || [];
            const extraTargets = { ...grouped };
            delete extraTargets.pushplus_token;
            await api('/admin/api/settings', {
                method: 'POST',
                body: { notifications: { extra_channel_targets: extraTargets, pushplus_targets: pushplusTargets } },
            });
            showToast('第三方推送设置已保存', 'success');
            closeChannelEditor();
            closeAdminNotificationChannels();
        } catch (err) { showToast(err.message, 'error'); }
    });

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
    const retryAllDead = async () => {
        await refreshAll();
        const dead = [...(state.tasks.dead || [])];
        if (!dead.length) {
            showToast('当前没有失败任务');
            return;
        }
        if (!confirm(`确认重试全部 ${dead.length} 个失败任务？`)) return;
        const results = await Promise.allSettled(dead.map(task =>
            api(`/admin/api/task/${pathSegment(task.task_id)}/retry`, { method: 'POST' })
        ));
        const failed = results.filter(result => result.status === 'rejected').length;
        showToast(failed ? `已重试 ${dead.length - failed} 个，失败 ${failed} 个` : `已重试 ${dead.length} 个失败任务`, failed ? 'error' : 'success');
        await refreshAll();
    };
    const clearDead = async () => {
        await refreshAll();
        const dead = [...(state.tasks.dead || [])];
        if (!dead.length) {
            showToast('当前没有死信任务');
            return;
        }
        if (!confirm(`确认删除全部 ${dead.length} 个死信任务？此操作不可恢复。`)) return;
        const results = await Promise.allSettled(dead.map(task =>
            api(`/admin/api/task/${pathSegment(task.task_id)}`, { method: 'DELETE' })
        ));
        const failed = results.filter(result => result.status === 'rejected').length;
        showToast(failed ? `已删除 ${dead.length - failed} 个，失败 ${failed} 个` : `已删除 ${dead.length} 个死信任务`, failed ? 'error' : 'success');
        await refreshAll();
    };
    $('#task-retry-dead').addEventListener('click', retryAllDead);
    $('#task-clear-dead').addEventListener('click', clearDead);
    $('#client-refresh').addEventListener('click', refreshAll);

    $$('[data-client-batch]').forEach(button => button.addEventListener('click', async () => {
        try { await runBatchClientAction(button.dataset.clientBatch); }
        catch (err) { showToast(err.message, 'error'); }
    }));

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

    const accessLimitDefaults = {
        '#ac-rate-limit': 10,
        '#ac-rate-window': 60,
        '#ac-request-body-mb': 2,
        '#ac-max-clients': 1024,
        '#ac-max-queue': 100,
        '#ac-concurrency': 1,
        '#ac-reserve': 512,
        '#ac-retry': 1,
        '#ac-timeout': 300,
        '#ac-history-tasks': 500,
        '#ac-dead-tasks': 100,
    };
    const saveAccessSettings = async (message) => {
        try {
            await api('/admin/api/settings', {
                method: 'POST',
                body: {
                    request_rate_limit: parseInt($('#ac-rate-limit').value) || 10,
                    request_rate_window_seconds: parseInt($('#ac-rate-window').value) || 60,
                    max_request_body_bytes: (parseInt($('#ac-request-body-mb').value) || 2) * 1024 * 1024,
                    max_clients: parseInt($('#ac-max-clients').value) || 1024,
                    max_queue_tasks: parseInt($('#ac-max-queue').value) || 100,
                    max_compute_concurrency: parseInt($('#ac-concurrency').value) || 1,
                    gpu_memory_reserve_mb: parseInt($('#ac-reserve').value) || 0,
                    task_retry_count: parseInt($('#ac-retry').value) || 0,
                    task_timeout_seconds: parseInt($('#ac-timeout').value) || 300,
                    max_history_tasks: parseInt($('#ac-history-tasks').value) || 500,
                    max_dead_tasks: parseInt($('#ac-dead-tasks').value) || 100,
                },
            });
            showToast(message, 'success');
        } catch (err) { showToast(err.message, 'error'); }
    };
    $('#ac-save').addEventListener('click', () => saveAccessSettings('限制设置已保存（部分项需重启生效）'));
    $('#ac-reset').addEventListener('click', async () => {
        if (!confirm('确认恢复请求限制默认值？')) return;
        Object.entries(accessLimitDefaults).forEach(([selector, value]) => { $(selector).value = value; });
        await saveAccessSettings('请求限制已恢复默认值（部分项需重启生效）');
    });

    $('#nf-save').addEventListener('click', async () => {
        try {
            const notifications = {
                system_toast: $('#nf-toast').checked,
                system_sound: $('#nf-sound').checked,
                queue_backlog_threshold: parseInt($('#nf-backlog').value) || 10,
                gpu_temp_threshold: parseInt($('#nf-gpu-temp').value) || 85,
                alert_events: Array.from($$('.nf-event')).filter(cb => cb.checked).map(cb => cb.value),
                cpu_percent_threshold: parseInt($('#nf-cpu').value) || 95,
                memory_percent_threshold: parseInt($('#nf-memory').value) || 90,
                swap_percent_threshold: parseInt($('#nf-swap').value) || 80,
                disk_used_percent_threshold: parseInt($('#nf-disk').value) || 90,
                gpu_memory_percent_threshold: parseInt($('#nf-gpu-memory').value) || 90,
                gpu_power_percent_threshold: parseInt($('#nf-gpu-power').value) || 90,
                cpu_power_percent_threshold: parseInt($('#nf-cpu-power').value) || 90,
            };
            const browserSettings = { enabled: $('#nf-browser').checked };
            if (browserSettings.enabled && !(await requestAdminBrowserNotificationPermission())) {
                showToast('后台浏览器系统通知权限未授予', 'info');
            }
            saveAdminBrowserNotificationSettings(browserSettings);
            await api('/admin/api/settings', {
                method: 'POST',
                body: { notifications },
            });
            showToast('通知设置已保存', 'success');
            closeAdminNotificationChannels();
        } catch (err) { showToast(err.message, 'error'); }
    });
    $('#nf-test').addEventListener('click', async () => {
        try {
            await api('/admin/api/notifications/test', { method: 'POST' });
            await testAdminBrowserNotification();
            showToast('测试推送已发送');
        }
        catch (err) { showToast(err.message, 'error'); }
    });

    $('#log-level').addEventListener('change', renderLogs);
    $('#log-search').addEventListener('input', renderLogs);
    $('#log-clear-view').addEventListener('click', () => { state.logs = []; renderLogs(); });
    $('#log-download-file').addEventListener('change', async () => {
        state.selectedLogFile = $('#log-download-file').value || '';
        await loadLogFile();
    });
    $('#log-download').addEventListener('click', async () => {
        const filename = $('#log-download-file').value || '';
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

    $$('[data-settings-save-all]').forEach(button => button.addEventListener('click', async () => {
        try {
            const resp = await api('/admin/api/settings', { method: 'POST', body: collectSettings() });
            applyMonitorDefaultView(resp.settings);
            showToast(resp.restart_required ? '已保存，端口等启动项需重启生效' : '已保存', 'success');
        } catch (err) { showToast(err.message, 'error'); }
    }));
    $$('[data-settings-reset-section]').forEach(button => button.addEventListener('click', async () => {
        if (!confirm('确认恢复当前卡片默认设置？')) return;
        try {
            const resp = await api('/admin/api/settings/reset-section', {
                method: 'POST',
                body: { section: button.dataset.settingsResetSection },
            });
            applyMonitorDefaultView(resp.settings);
            showToast(resp.restart_required ? '当前卡片已恢复默认，端口设置需重启生效' : '当前卡片已恢复默认', 'success');
            await loadSettingsTab();
        } catch (err) { showToast(err.message, 'error'); }
    }));
    $$('[data-settings-reset-all]').forEach(button => button.addEventListener('click', async () => {
        if (!confirm('确认恢复默认设置？')) return;
        try {
            const resp = await api('/admin/api/settings/reset', { method: 'POST' });
            applyMonitorDefaultView(resp.settings);
            showToast('已恢复默认，重启后完全生效', 'success');
            await loadSettingsTab();
        } catch (err) { showToast(err.message, 'error'); }
    }));
}
