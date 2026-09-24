// 界面交互：标签切换、软件设置弹窗、事件绑定

// 标签页切换与路由
/**
 * 切换标签页
 * @param {string} tabId - 标签页ID
 */
function switchTab(tabId, { replace = false } = {}) {
    // 刷新恢复不播放进入动画，用户主动切换时恢复动效。
    if (!replace) document.body.classList.remove('is-initializing');
    // 记录当前标签，刷新后保持原位置
    sessionStorage.setItem('active_tab', tabId);
    const targetPath = MAIN_TAB_PATHS[tabId];
    if (targetPath && location.pathname !== targetPath) {
        const method = replace ? 'replaceState' : 'pushState';
        history[method]({}, '', targetPath);
    }

    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));

    const btn = document.querySelector(`[data-tab="${tabId}"]`);
    const panel = document.getElementById(tabId);
    if (btn) btn.classList.add('active');
    if (panel) panel.classList.add('active');
    if (tabId === 'tab-anim') syncAnimationLayout();

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

function syncAnimationLayout() {
    const panel = document.getElementById('tab-anim');
    if (!panel || !panel.classList.contains('active')) return;
    if (window.matchMedia('(max-width: 900px)').matches) {
        panel.style.removeProperty('--two-d-row-height');
        panel.style.removeProperty('--animation-evolution-track');
        return;
    }
    // 读取二维页外层网格实际解析后的行间距，不能直接 parseFloat(clamp(...))。
    const twoDPanel = document.getElementById('tab-2d');
    const twoDGap = twoDPanel ? parseFloat(getComputedStyle(twoDPanel).rowGap) || 0 : 0;
    const panelStyle = getComputedStyle(panel);
    const panelHeight = panel.getBoundingClientRect().height;
    const paddingHeight = parseFloat(panelStyle.paddingTop) + parseFloat(panelStyle.paddingBottom);
    const control = panel.querySelector('.anim-control-bar');
    const evolution = panel.querySelector('.chart-full');
    if (!control || !evolution) return;
    const controlStyle = getComputedStyle(control);
    const controlOuterHeight = control.getBoundingClientRect().height + (parseFloat(controlStyle.marginBottom) || 0);
    const evolutionMargin = parseFloat(getComputedStyle(evolution).marginTop || '0') || 0;
    const targetHeight = (panelHeight - paddingHeight - twoDGap) / 2;
    const evolutionTrack = targetHeight + evolutionMargin;
    const patternHeight = panelHeight - paddingHeight - controlOuterHeight - evolutionTrack;
    if (!Number.isFinite(targetHeight) || targetHeight <= 0 || !Number.isFinite(patternHeight) || patternHeight <= 0) return;
    panel.style.setProperty('--two-d-row-height', `${targetHeight}px`);
    panel.style.setProperty('--animation-pattern-height', `${patternHeight}px`);
    panel.style.setProperty('--animation-evolution-track', `${evolutionTrack}px`);
}

window.addEventListener('resize', () => requestAnimationFrame(syncAnimationLayout));

window.addEventListener('popstate', () => {
    if (location.pathname === '/settings') {
        document.getElementById('software-settings')?.click();
        return;
    }
    if (location.pathname === '/pushplus') {
        document.getElementById('settings-modal')?.classList.remove('show');
        document.getElementById('client-channel-editor-modal')?.classList.remove('show');
        document.getElementById('manage-notification-channels')?.click();
        return;
    }
    document.getElementById('settings-modal')?.classList.remove('show');
    document.getElementById('client-notification-settings-modal')?.classList.remove('show');
    document.getElementById('client-channel-editor-modal')?.classList.remove('show');
    const tabId = MAIN_PATH_TABS[location.pathname];
    if (tabId) switchTab(tabId, { replace: true });
});

// 软件设置弹窗：拖动、语言与客户端名称
function initSettingsModal() {
    const settingsModal = $('#settings-modal');
    const modalContent = $('#modal-content');
    const modalHeader = $('.modal-header');
    const languageSelect = $('#language-select');
    const clientNameInput = $('#client-name-input');

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
        if (location.pathname !== '/settings') history.pushState({}, '', '/settings');
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

        // 设置自定义下拉组件的值
        setCustomSelectValue(languageSelect, savedLang);

        clientNameInput.value = state.clientName || state.clientId;
        fillClientTaskNotificationPreferences();
        fillClientTaskNotificationChannels();
        settingsModal.classList.add('show');
    });

    // 关闭设置弹窗
    $('#settings-cancel').addEventListener('click', () => {
        leaveSettingsPage();
    });

    // 点击遮罩关闭弹窗
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            leaveSettingsPage();
        }
    });

    // 保存设置（仅本地项：语言 + 客户端名称，端口等启动项已移至后台管理中心）
    $('#settings-save').addEventListener('click', async () => {
        const newLang = languageSelect.value;
        const enteredClientName = clientNameInput.value.trim();
        const newClientName = enteredClientName === state.clientId ? '' : enteredClientName;

        if (newClientName.length > 40) {
            showToast('客户端名称不能超过40个字符', 'error');
            return;
        }
        if (!isSupportedClientName(newClientName)) {
            showToast('客户端名称包含不支持的字符，请勿使用表情、换行或不可见字符', 'error');
            return;
        }

        state.clientName = newClientName;
        localStorage.setItem('client_name', newClientName);
        i18n.setLang(newLang);

        const notificationSettings = {
            ...getClientTaskNotificationSettings(),
            ...readClientTaskNotificationPreferences(),
        };
        saveClientTaskNotificationSettings(notificationSettings);

        setClientOperationStatus('status_settings_saved');
        showToast(i18n.t('status_settings_saved'), 'success');
        leaveSettingsPage();
    });

    function leaveSettingsPage() {
        document.getElementById('settings-modal')?.classList.remove('show');
        if (location.pathname === '/settings') {
            const tabId = sessionStorage.getItem('active_tab') || 'tab-2d';
            switchTab(tabId, { replace: true });
        } else {
            settingsModal.classList.remove('show');
        }
    }

    // 恢复默认设置
    $('#restore-default').addEventListener('click', () => {
        // 恢复默认语言（检测系统语言）
        const defaultLang = detectSystemLang();

        // 设置自定义下拉组件的值
        setCustomSelectValue(languageSelect, defaultLang);

        clientNameInput.value = '';

        // 清除保存的本地设置
        localStorage.removeItem('app_language');
        state.clientName = '';
        localStorage.removeItem('client_name');
        localStorage.removeItem(clientTaskNotificationStorageKey());
        i18n.setLang(defaultLang);
        fillClientTaskNotificationPreferences();
        fillClientTaskNotificationChannels();

        setClientOperationStatus('status_reset_all');
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

    $('#tn-browser').addEventListener('change', async (event) => {
        if (!event.target.checked) return;
        const availability = clientTaskNotificationAvailability();
        if (availability === 'unsupported') {
            event.target.checked = false;
            showToast(i18n.t('task_notification_unsupported'), 'info');
            return;
        }
        if (availability === 'insecure') {
            event.target.checked = false;
            showToast(i18n.t('task_notification_insecure'), 'info');
            return;
        }
        if (!(await requestClientTaskNotificationPermission())) {
            event.target.checked = false;
            showToast(i18n.t('task_notification_denied'), 'info');
        }
    });
    $('#tn-test').addEventListener('click', testClientTaskNotification);
}

function initClientNotificationSettingsModal() {
    const modal = $('#client-notification-settings-modal');
    const modalContent = $('#client-notification-settings-content');
    const modalHeader = $('#client-notification-settings-header');
    const editorModal = $('#client-channel-editor-modal');
    const editorContent = $('#client-channel-editor-content');
    const editorHeader = $('#client-channel-editor-header');
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;
    let savedModalPos = null;
    let previousPath = location.pathname;
    let channelTargets = [];
    let editingTargetId = null;
    let editorDragging = false;
    let editorOffsetX = 0;
    let editorOffsetY = 0;
    let savedEditorPos = null;

    const newTargetId = () => `ct_${crypto.randomUUID().replace(/-/g, '')}`;
    const flattenTargets = grouped => Object.entries(grouped || {}).flatMap(([type, targets]) =>
        (Array.isArray(targets) ? targets : []).map(target => ({ ...target, type })));
    const groupTargets = targets => {
        const grouped = {};
        Object.keys(CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS).forEach(type => { grouped[type] = []; });
        targets.forEach(({ type, ...target }) => { if (grouped[type]) grouped[type].push(target); });
        return grouped;
    };
    const targetDefinition = target => CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS[target.type] || CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS.webhook;
    const targetConfigured = target => targetDefinition(target).required.every(key => String(target[key] || '').trim());
    const renderFields = target => {
        const type = $('#tn-channel-type').value || 'webhook';
        const definition = CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS[type];
        $('#tn-channel-fields').innerHTML = definition.fields.map(field => field.type === 'checkbox'
            ? `<label class="settings-checkbox"><input type="checkbox" id="tn-channel-field-${field.key}"${target?.[field.key] !== false ? ' checked' : ''}><span>${esc(i18n.t(field.labelKey))}</span></label>`
            : `<label><span>${esc(i18n.t(field.labelKey))}</span><input type="${field.type}" id="tn-channel-field-${field.key}" class="num-input"></label>`
        ).join('');
        definition.fields.forEach(field => {
            const input = $(`#tn-channel-field-${field.key}`);
            if (field.type !== 'checkbox' && input) input.value = target?.[field.key] || (field.key === 'port' ? 465 : '');
        });
    };
    const resetEditor = () => {
        editingTargetId = null;
        $('#tn-channel-editor-title').textContent = i18n.t('task_notification_target_new');
        $('#tn-channel-name').value = '';
        setCustomSelectValue($('#tn-channel-type'), 'webhook');
        renderFields();
    };
    const renderTargets = () => {
        const list = $('#tn-channel-list');
        if (!channelTargets.length) {
            list.innerHTML = `<div class="pushplus-target-empty">${esc(i18n.t('task_notification_target_empty'))}</div>`;
            return;
        }
        list.innerHTML = `<table class="pushplus-target-table"><thead><tr>
            <th>${esc(i18n.t('task_notification_target_type'))}</th><th>${esc(i18n.t('task_notification_target_name'))}</th>
            <th>${esc(i18n.t('task_notification_target_status'))}</th><th>${esc(i18n.t('task_notification_target_config'))}</th>
            <th>${esc(i18n.t('task_notification_target_actions'))}</th></tr></thead><tbody>${channelTargets.map(target => `
            <tr><td>${esc(i18n.t(targetDefinition(target).labelKey))}</td><td>${esc(target.name)}</td>
            <td><label class="pushplus-target-toggle"><input type="checkbox" data-channel-action="toggle" data-target-id="${escAttr(target.id)}"${target.enabled ? ' checked' : ''}><span>${esc(i18n.t(target.enabled ? 'task_notification_target_enabled' : 'task_notification_target_disabled'))}</span></label></td>
            <td>${esc(i18n.t(targetConfigured(target) ? 'task_notification_target_configured' : 'task_notification_target_not_configured'))}</td>
            <td class="pushplus-target-actions"><button type="button" data-channel-action="edit" data-target-id="${escAttr(target.id)}">${esc(i18n.t('pushplus_target_edit'))}</button><button type="button" data-channel-action="delete" data-target-id="${escAttr(target.id)}">${esc(i18n.t('pushplus_target_delete'))}</button></td></tr>
        `).join('')}</tbody></table>`;
    };
    const closeEditor = () => { editorModal.classList.remove('show'); editorModal.setAttribute('aria-hidden', 'true'); };
    const openEditor = target => {
        resetEditor();
        if (target) {
            editingTargetId = target.id;
            $('#tn-channel-editor-title').textContent = i18n.t('task_notification_target_edit_title');
            $('#tn-channel-name').value = target.name;
            setCustomSelectValue($('#tn-channel-type'), target.type);
            renderFields(target);
        }
        if (savedEditorPos) {
            editorContent.style.left = savedEditorPos.left + 'px'; editorContent.style.top = savedEditorPos.top + 'px'; editorContent.style.transform = 'none';
        } else { editorContent.style.left = ''; editorContent.style.top = ''; editorContent.style.transform = ''; }
        editorModal.classList.add('show'); editorModal.setAttribute('aria-hidden', 'false'); $('#tn-channel-name').focus();
    };
    const closeModal = () => {
        closeEditor(); modal.classList.remove('show'); modal.setAttribute('aria-hidden', 'true');
        if (location.pathname !== '/pushplus') return;
        if (previousPath === '/settings') { history.replaceState({}, '', '/settings'); document.getElementById('software-settings')?.click(); return; }
        switchTab(sessionStorage.getItem('active_tab') || 'tab-2d', { replace: true });
    };
    const openModal = () => {
        if (location.pathname !== '/pushplus') { previousPath = location.pathname; history.pushState({}, '', '/pushplus'); }
        $('#settings-modal')?.classList.remove('show');
        if (savedModalPos) { modalContent.style.left = savedModalPos.left + 'px'; modalContent.style.top = savedModalPos.top + 'px'; modalContent.style.transform = 'none'; }
        else { modalContent.style.left = ''; modalContent.style.top = ''; modalContent.style.transform = ''; }
        channelTargets = flattenTargets(getClientTaskNotificationSettings().channelTargets);
        renderTargets(); resetEditor(); closeEditor(); modal.classList.add('show'); modal.setAttribute('aria-hidden', 'false');
    };
    modalHeader.addEventListener('mousedown', event => {
        if (event.button !== 0) return; isDragging = true; const rect = modalContent.getBoundingClientRect();
        dragOffsetX = event.clientX - rect.left; dragOffsetY = event.clientY - rect.top; modalContent.style.cursor = 'grabbing'; event.preventDefault();
    });
    editorHeader.addEventListener('mousedown', event => {
        if (event.button !== 0) return; editorDragging = true; const rect = editorContent.getBoundingClientRect();
        editorOffsetX = event.clientX - rect.left; editorOffsetY = event.clientY - rect.top; editorContent.style.cursor = 'grabbing'; event.preventDefault();
    });
    document.addEventListener('mousemove', event => {
        if (isDragging) { const left = event.clientX - dragOffsetX; const top = event.clientY - dragOffsetY; modalContent.style.left = left + 'px'; modalContent.style.top = top + 'px'; modalContent.style.transform = 'none'; savedModalPos = { left, top }; }
        if (editorDragging) { const left = event.clientX - editorOffsetX; const top = event.clientY - editorOffsetY; editorContent.style.left = left + 'px'; editorContent.style.top = top + 'px'; editorContent.style.transform = 'none'; savedEditorPos = { left, top }; }
    });
    document.addEventListener('mouseup', () => { isDragging = false; editorDragging = false; modalContent.style.cursor = ''; editorContent.style.cursor = ''; });
    $('#tn-channel-type').addEventListener('change', () => renderFields());
    $('#manage-notification-channels').addEventListener('click', openModal);
    $('#notification-settings-cancel').addEventListener('click', closeModal);
    modal.addEventListener('click', event => { if (event.target === modal) closeModal(); });
    editorModal.addEventListener('click', event => { if (event.target === editorModal) closeEditor(); });
    $('#notification-settings-save').addEventListener('click', () => {
        const grouped = groupTargets(channelTargets);
        saveClientTaskNotificationSettings({ ...getClientTaskNotificationSettings(), channelTargets: grouped, pushplusTargets: grouped.pushplus || [] });
        showToast(i18n.t('task_notification_settings_saved'), 'success'); closeModal();
    });
    $('#notification-settings-restore').addEventListener('click', () => {
        const settings = getClientTaskNotificationSettings(); channelTargets = [];
        saveClientTaskNotificationSettings({ ...settings, channelTargets: {}, pushplusTargets: [] }); renderTargets(); closeEditor();
        showToast(i18n.t('task_notification_settings_restored'), 'success');
    });
    $('#tn-channel-add').addEventListener('click', () => openEditor());
    $('#tn-channel-editor-cancel').addEventListener('click', closeEditor);
    $('#tn-channel-target-save').addEventListener('click', () => {
        const type = $('#tn-channel-type').value || 'webhook';
        const definition = CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS[type];
        const name = $('#tn-channel-name').value.trim();
        const target = { id: editingTargetId || newTargetId(), type, name: name.slice(0, 40), enabled: editingTargetId ? channelTargets.find(item => item.id === editingTargetId)?.enabled ?? true : true };
        definition.fields.forEach(field => { const input = $(`#tn-channel-field-${field.key}`); target[field.key] = field.type === 'checkbox' ? !!input.checked : input.value.trim().slice(0, 1024); });
        if (!name || !definition.required.every(key => String(target[key] || '').trim())) { showToast(i18n.t('task_notification_target_required'), 'error'); return; }
        if (!editingTargetId && channelTargets.length >= 20) { showToast(i18n.t('task_notification_target_limit'), 'error'); return; }
        const index = channelTargets.findIndex(item => item.id === target.id); if (index >= 0) channelTargets[index] = target; else channelTargets.push(target);
        renderTargets(); closeEditor();
    });
    $('#tn-channel-list').addEventListener('click', event => {
        const control = event.target.closest('[data-channel-action]'); if (!control) return;
        const index = channelTargets.findIndex(item => item.id === control.dataset.targetId); if (index < 0) return;
        if (control.dataset.channelAction === 'toggle') { channelTargets[index].enabled = control.checked; renderTargets(); return; }
        if (control.dataset.channelAction === 'edit') openEditor(channelTargets[index]);
        if (control.dataset.channelAction === 'delete') { channelTargets.splice(index, 1); renderTargets(); closeEditor(); }
    });
    window.openClientNotificationSettings = openModal;
}

function initClientTaskLogModal() {
    const modalContent = $('#client-task-log-modal .task-log-modal-content');
    const modalHeader = $('#client-task-log-modal .task-log-modal-header');
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;
    let savedModalPos = null;

    // 与软件设置弹窗保持一致：固定定位下记录鼠标相对弹窗左上角的偏移。
    modalHeader.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        isDragging = true;
        const rect = modalContent.getBoundingClientRect();
        dragOffsetX = e.clientX - rect.left;
        dragOffsetY = e.clientY - rect.top;
        modalContent.style.cursor = 'grabbing';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const left = e.clientX - dragOffsetX;
        const top = e.clientY - dragOffsetY;
        modalContent.style.left = left + 'px';
        modalContent.style.top = top + 'px';
        modalContent.style.transform = 'none';
        savedModalPos = { left, top };
    });

    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        modalContent.style.cursor = '';
        modalHeader.style.cursor = 'move';
    });

    window.restoreClientTaskLogModalPosition = () => {
        if (savedModalPos) {
            modalContent.style.left = savedModalPos.left + 'px';
            modalContent.style.top = savedModalPos.top + 'px';
            modalContent.style.transform = 'none';
        } else {
            modalContent.style.left = '';
            modalContent.style.top = '';
            modalContent.style.transform = '';
        }
    };
}

// 主界面事件绑定
/**
 * 绑定事件监听器
 */
function bindEvents() {
    // Plotly范围条释放事件偶尔落到覆盖层之外，兜底清理残留拖动态
    function releasePlotlyDrag(event) {
        const dragCover = $('.dragcover');
        if (!dragCover || event?.target === dragCover) return;
        dragCover.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    }
    document.addEventListener('mouseup', releasePlotlyDrag);
    document.addEventListener('pointerup', releasePlotlyDrag);
    window.addEventListener('blur', () => releasePlotlyDrag());

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
        if (val > max) {
            // 超出上限时弹窗提醒并自动修正为上限
            showToast(i18n.t('iter_max_warning', { max }), 'error');
            $('#iter-value').value = max;
            $('#iter-range').value = max;
        } else if (val < min) {
            $('#iter-value').value = min;
            $('#iter-range').value = min;
        } else {
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

    // 软件设置弹窗
    initSettingsModal();
    initClientNotificationSettingsModal();
    initClientTaskLogModal();

    // 当前客户端任务日志
    $('#status-msg').addEventListener('click', openClientTaskLogModal);
    $('#client-task-log-modal').addEventListener('click', (event) => {
        if (event.target.id === 'client-task-log-modal') closeClientTaskLogModal();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && $('#client-task-log-modal').classList.contains('show')) {
            closeClientTaskLogModal();
        }
    });

    // 控制按钮
    $('#run-sim').addEventListener('click', runSimulation);
    $('#run-anim').addEventListener('click', () => {
        switchTab('tab-anim');
        runAnimation();
    });
    // 加载遮罩上的取消任务按钮
    $('#loading-cancel').addEventListener('click', cancelCurrentTask);
    $('#reset-all').addEventListener('click', () => {
        onModelChange();
        state.trackPoints = [];
        updateTrackList();
        saveSettings();
        setClientOperationStatus('status_reset_all');
        showToast(i18n.t('reset_done'));
    });
    $('#clean-cache').addEventListener('click', async () => {
        try {
            const resp = await apiCall('/api/cleanup', {});
            setClientOperationStatus('status_cache_cleared', 'success', true);
            showToast(resp.message, 'success');
            location.reload();
        } catch (err) {
            setClientOperationStatus('status_cache_clear_failed', 'error');
            showToast(i18n.t('clean_failed', { msg: err.message }), 'error');
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
