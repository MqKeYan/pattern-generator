// 通用基础层：DOM 与转义、图表主题、图像字号、界面缩放、轻提示、自定义下拉（前后台共用）

// 通用 DOM 与转义工具（前后台共用）
// DOM元素缓存
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
// HTML 转义（信息卡片等动态插值用）
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// HTML 属性值额外转义引号，避免外部标识符突破属性边界
const escAttr = (s) => esc(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// Plotly 主题：从 CSS 变量读取绘图配色（前后台共用）
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

// 全局图像字号规范，以14px为基准。
window.PLOT_FONT_SIZES = Object.freeze({
    base: 14,
    title: 16,
    axisTitle: 14,
    tick: 14,
    legend: 12,
    annotation: 12,
    tooltip: 14,
    monitorTitle: 14,
    monitorValue: 12,
});

// 根据窗口空间和设备类型选择布局，手机竖屏单独启用触控布局。
(function () {
    let frameId = 0;
    let mobileSidebarExpanded = false;

    function isPhoneBrowser() {
        const uaDataMobile = navigator.userAgentData?.mobile;
        if (uaDataMobile === true) return true;
        const ua = navigator.userAgent || '';
        const isIpad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        if (isIpad) return false;
        return /Android.*Mobile|iPhone|iPod|IEMobile|Opera Mini/i.test(ua);
    }

    function isPortrait() {
        if (screen.orientation?.type) return screen.orientation.type.startsWith('portrait');
        return window.matchMedia('(orientation: portrait)').matches;
    }

    function getDeviceLayout() {
        if (!isPhoneBrowser()) return 'pc';
        return isPortrait() ? 'mobile-portrait' : 'mobile-landscape';
    }

    function getLayoutTier() {
        const { innerWidth: width, innerHeight: height } = window;
        if (width <= 900) return 'compact';
        if (width <= 1366 || height <= 760) return 'compact-desktop';
        if (width < 2200 || height < 1200) return 'hd';
        if (width >= 3300 && height >= 1800) return 'ultra';
        return 'qhd';
    }

    function updateSidebarState() {
        const root = document.documentElement;
        const sidebar = document.getElementById('sidebar');
        const toggle = document.querySelector('[data-mobile-sidebar-toggle]');
        const isMobilePortrait = root.dataset.deviceLayout === 'mobile-portrait';
        if (sidebar) sidebar.classList.toggle('mobile-collapsed', isMobilePortrait && !mobileSidebarExpanded);
        if (toggle) toggle.setAttribute('aria-expanded', String(isMobilePortrait && mobileSidebarExpanded));
    }

    function applyLayout() {
        const tier = getLayoutTier();
        const deviceLayout = getDeviceLayout();
        const root = document.documentElement;
        const changed = root.dataset.layoutTier !== tier || root.dataset.deviceLayout !== deviceLayout;
        root.dataset.layoutTier = tier;
        root.dataset.deviceLayout = deviceLayout;
        if (deviceLayout !== 'mobile-portrait') mobileSidebarExpanded = false;
        updateSidebarState();
        if (changed) window.dispatchEvent(new CustomEvent('ui-layout-change', { detail: { tier, deviceLayout } }));
    }

    function scheduleLayoutUpdate() {
        cancelAnimationFrame(frameId);
        frameId = requestAnimationFrame(applyLayout);
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-mobile-sidebar-toggle]').forEach(toggle => {
            toggle.addEventListener('click', () => {
                mobileSidebarExpanded = !mobileSidebarExpanded;
                updateSidebarState();
                window.dispatchEvent(new CustomEvent('ui-layout-change', { detail: { deviceLayout: document.documentElement.dataset.deviceLayout } }));
            });
        });
        updateSidebarState();
    });

    applyLayout();
    window.addEventListener('resize', scheduleLayoutUpdate, { passive: true });
    window.addEventListener('orientationchange', scheduleLayoutUpdate, { passive: true });
    screen.orientation?.addEventListener?.('change', scheduleLayoutUpdate);
    window.visualViewport?.addEventListener('resize', scheduleLayoutUpdate, { passive: true });
    window.addEventListener('ui-layout-change', () => {
        if (!window.Plotly) return;
        document.querySelectorAll('.chart-box').forEach(chart => {
            if (chart._fullLayout) window.Plotly.Plots.resize(chart);
        });
    });
})();

// 轻提示（前后台共用）
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

// 自定义下拉组件：值与事件绑定（前后台共用）
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

// 空下拉框显示统一的非交互提示，避免展开后只显示空边框。
function syncCustomSelectEmptyState(options) {
    const emptyState = options.querySelector('.custom-select-empty');
    if (options.querySelector('.custom-select-option')) {
        emptyState?.remove();
        return;
    }
    if (!emptyState) {
        const empty = document.createElement('div');
        empty.className = 'custom-select-empty';
        empty.textContent = '暂无可选内容';
        options.appendChild(empty);
    }
}

function bindCustomSelect(customSelect) {
    if (customSelect.dataset.bound) return;
    customSelect.dataset.bound = '1';
    const trigger = customSelect.querySelector('.custom-select-trigger');
    const options = customSelect.querySelector('.custom-select-options');
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
        syncCustomSelectEmptyState(options);
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
    options.addEventListener('click', (e) => {
        const option = e.target.closest('.custom-select-option');
        if (!option || !options.contains(option)) return;
        e.stopPropagation();
        options.querySelectorAll('.custom-select-option').forEach(opt => opt.classList.remove('selected'));
        option.classList.add('selected');
        selectedText.textContent = option.textContent;
        customSelect.value = option.dataset.value;
        customSelect.dispatchEvent(new Event('change'));
        closeOptions();
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
