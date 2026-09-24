// 实时监控渲染：图像绘制、悬浮提示、视图模式、紧凑视图、主渲染

// 监控图像绘制与悬浮提示

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
    const firstValid = data.y.findIndex(v => v != null && Number.isFinite(Number(v)));
    const lastValid = data.y.findLastIndex(v => v != null && Number.isFinite(Number(v)));
    let plotX = data.x;
    let plotY = data.y;
    if (firstValid >= 0 && lastValid >= firstValid) {
        // 左侧零点绑定首个有效采样点，随整段曲线一起向左平移。
        plotX = [data.x[firstValid], ...data.x.slice(firstValid, lastValid + 1), data.x[lastValid]];
        plotY = [0, ...data.y.slice(firstValid, lastValid + 1), 0];
    }
    fn(id, [{
        x: plotX, y: plotY,
        type: 'scatter', mode: 'lines',
        line: { color: tile.color, width: 1.5 },
        fill: 'tozeroy', fillcolor: withAlpha(tile.color, 0.22),
        connectgaps: false,
        // 关闭原生悬浮标签（'none' 保留 hover 事件），改用自定义弹窗显示在点上方
        hoverinfo: 'none',
    }], {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0.28)',
        font: { size: PLOT_FONT_SIZES.base, color: colors.secondary },
        // 四周边距归零：绘图区铺满瓷砖，曲线两端顶到边缘（任务管理器样式）
        margin: { l: 0, r: 0, t: 0, b: 0 },
        showlegend: false,
        xaxis: {
            // 背景网格固定为60秒，曲线从右侧进入后向左移动。
            range: [-(MONITOR_WINDOW - 1), 0],
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
            tip.textContent = formatPlotValue(Number(pt.y), tile) + (tile.unit || '');
            tip.style.left = `${px}px`;
            tip.style.top = `${py - 8}px`;
            tip.classList.add('show');
        });
        el.on('plotly_unhover', hidePlotTooltip);
    }
}

// 监控分类与视图模式切换
function updateMonitorCategoryAvailability(gpuCount) {
    // 首次渲染尚未收到监控数据时，GPU 数量未知，不能先隐藏按钮或改回总览。
    if (!state.metrics || !Array.isArray(state.metrics.gpus)) return;
    const gpuButton = $('[data-monitor-category="gpu"]');
    if (gpuButton) gpuButton.hidden = gpuCount === 0;
    if (gpuCount === 0 && state.monitorCategory === 'gpu') {
        switchMonitorCategory('overview', { replace: true });
    }
}

function updateMonitorViewToggle() {
    const toggle = $('#monitor-view-toggle');
    if (!toggle) return;
    const compactMode = state.monitorViewMode === 'compact';
    toggle.setAttribute('aria-checked', String(compactMode));
    toggle.classList.toggle('active', compactMode);
    const label = $('#monitor-view-toggle-label');
    if (label) label.textContent = compactMode ? '紧凑视图' : '完整视图';
}

function switchMonitorViewMode() {
    state.monitorViewMode = state.monitorViewMode === 'compact' ? 'full' : 'compact';
    try {
        sessionStorage.setItem(MONITOR_VIEW_STORAGE_KEY, state.monitorViewMode);
    } catch { /* 存储不可用时仅保留当前页面状态 */ }
    if (state.activeTab === 'tab-monitor') {
        const targetPath = monitorPathFor(state.monitorCategory, state.monitorViewMode);
        if (location.pathname + location.search !== targetPath) history.pushState({}, '', targetPath);
    }
    updateMonitorViewToggle();
    requestAnimationFrame(renderMonitor);
}

// 紧凑视图监控渲染
function renderCpuPackageSections(cpus) {
    const container = $('#cpu-package-sections');
    const visible = state.monitorCategory === 'cpu' && cpus.length > 0;
    container.hidden = !visible;
    if (!visible) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = cpus.map((cpu, cpuIndex) => {
        const logical = cpu.logical_processors || [];
        const cells = logical.map((processor, logicalIndex) => {
            const usage = Number(processor.util_percent);
            const safeUsage = Number.isFinite(usage) ? Math.min(100, Math.max(0, usage)) : 0;
            const usageText = Number.isFinite(usage) ? `${fmtPercentValue(usage)}%` : '-';
            const frequency = Number(processor.freq_mhz);
            const frequencyText = Number.isFinite(frequency) ? `${fmtPlotVal(frequency)} MHz` : '暂无频率数据';
            return `<div class="cpu-core-cell" style="--cpu-load:${safeUsage}%" title="${escAttr(frequencyText)}">`
                + `<span class="cpu-core-name">逻辑处理器 ${logicalIndex + 1}</span>`
                + `<span class="cpu-core-value">${usageText}</span></div>`;
        }).join('');
        const cpuLabel = cpus.length > 1 ? `CPU ${cpuIndex + 1} ` : 'CPU ';
        return `<section class="cpu-package-panel">`
            + `<div class="cpu-package-head"><span>${cpuLabel}逻辑处理器负载</span>`
            + `<span>${logical.length} 个逻辑处理器</span></div>`
            + `<div class="cpu-core-grid">${cells}</div></section>`;
    }).join('');
}

function compactTileAxisMax(tile, source, data, displayScale) {
    const values = data.y.filter(value => value != null && Number.isFinite(Number(value))).map(Number);
    const windowMax = values.length ? Math.max(...values) : null;
    let max;
    if (tile.max != null) max = tile.max;
    else if (tile.dynamicMax) max = dynamicAxisMax(data.y);
    else if (tile.powerAxis) max = tile.cpuIndex != null
        ? cpuPowerAxisMax(tile.cpuIndex, source, data.y)
        : gpuPowerAxisMax(tile.gpuIndex, source, data.y);
    else if (tile.temperatureAxis) max = gpuTemperatureAxisMax(tile.gpuIndex, source, data.y);
    else if (tile.cap != null) max = source?.[tile.cap] ?? null;
    else if (tile.integerAxis) max = Math.max(1, Math.ceil(windowMax ?? 0));
    else max = dynamicAxisMax(data.y);
    return max == null ? null : max * displayScale;
}

function renderCompactMonitorTiles(tiles, history, current) {
    const latest = history.at(-1) || current;
    tiles.forEach(tile => {
        const rawValue = tile.get(latest) ?? tile.get(current);
        const rawData = { x: [0], y: [rawValue], span: 0 };
        const display = adaptPlotUnit(tile, rawData);
        const displayValue = display.data.y[0];
        const source = tile.cpuIndex != null
            ? current.cpus?.[tile.cpuIndex]
            : tile.gpuIndex != null ? current.gpus?.[tile.gpuIndex] : current;
        const max = compactTileAxisMax(tile, source, {
            y: history.map(sample => tile.get(sample)),
        }, display.scale);
        const value = Number(displayValue);
        const fill = Number.isFinite(value) && Number.isFinite(max) && max > 0
            ? Math.min(100, Math.max(0, value / max * 100)) : 0;
        const chart = document.getElementById('tile-chart-' + tile.key);
        if (!chart) return;
        chart.classList.add('compact-metric-box');
        chart.innerHTML = `<div class="compact-metric-card" style="--metric-fill:${fill}%">`
            + `<span class="compact-metric-name">${esc(tile.name)}</span>`
            + `<span class="compact-metric-value">${displayValue == null || !Number.isFinite(Number(displayValue)) ? '暂无数据' : esc(formatPlotValue(displayValue, display.tile) + (display.tile.unit || ''))}</span>`
            + `</div>`;
    });
}

// 监控页面主渲染
function renderMonitor() {
    // 刷新首帧等待完整监控快照，避免先按空数据创建临时图像后再次重排。
    if (!state.metrics) return;
    // 过滤采样失败的空样本（time 为空会造成 x 缺失、折线断点）
    const hist = (state.monitorHistory || []).filter(h => h.time);
    const m = state.metrics || {};
    const gpuCount = Array.isArray(m.gpus) ? m.gpus.length : 0;
    const cpus = Array.isArray(m.cpus) ? m.cpus : [];
    const cpuCount = cpus.length;
    const diskCount = Array.isArray(m.disks) ? m.disks.length : 0;
    const volumes = Array.isArray(m.volumes) ? m.volumes : [];
    const volumeCount = volumes.length;
    const compactMode = state.monitorViewMode === 'compact';
    const grid = $('#monitor-grid');
    updateMonitorCategoryAvailability(gpuCount);
    updateMonitorViewToggle();
    if (grid) {
        grid.hidden = false;
        grid.classList.toggle('compact-monitor-grid', compactMode);
    }
    const monitorPanel = $('#tab-monitor');
    monitorPanel?.classList.toggle('compact-monitor-mode', compactMode);
    renderCpuPackageSections(cpus);
    ensureMonitorTiles(gpuCount, cpuCount, diskCount, volumeCount, volumes);
    if (compactMode) {
        renderCompactMonitorTiles(
            visibleMonitorTileDefs(gpuCount, cpuCount, diskCount, volumeCount, volumes),
            hist,
            m,
        );
        return;
    }
    visibleMonitorTileDefs(gpuCount, cpuCount, diskCount, volumeCount, volumes).forEach(tile => {
        let data, last = null;
        const rawData = windowSeries(hist.map(h => h.time), hist.map(h => tile.get(h)));
        const display = adaptPlotUnit(tile, rawData);
        data = display.data;
        const displayTile = display.tile;
        for (let j = data.y.length - 1; j >= 0; j--) {
            if (data.y[j] != null) { last = data.y[j]; break; }
        }
        // 纵轴上限：固定值 > 窗口峰值（winMax） > 本机硬件容量（物理内存 / 显存总量 / 功耗墙） > 自动
        const vals = data.y.filter(v => v != null);
        const winMax = vals.length ? Math.max(...vals) : null;
        let ymax;
        if (tile.max != null) ymax = tile.max;
        else if (tile.dynamicMax) ymax = dynamicAxisMax(data.y);
        else if (tile.winMax) ymax = winMax;
        else if (tile.powerAxis) ymax = tile.cpuIndex != null
            ? cpuPowerAxisMax(tile.cpuIndex, m.cpus?.[tile.cpuIndex], data.y)
            : gpuPowerAxisMax(tile.gpuIndex, m.gpus?.[tile.gpuIndex], data.y);
        else if (tile.temperatureAxis) ymax = gpuTemperatureAxisMax(tile.gpuIndex, m.gpus?.[tile.gpuIndex], data.y);
        else if (tile.cap != null) {
            const source = tile.gpuIndex != null ? m.gpus?.[tile.gpuIndex] : m;
            ymax = source?.[tile.cap];
            if (ymax != null && display.scale !== 1) ymax *= display.scale;
        }
        else if (tile.integerAxis) ymax = Math.max(1, Math.ceil(winMax ?? 0));
        else ymax = null;
        plotTile('tile-chart-' + tile.key, displayTile, data, ymax ?? null);

        // 四角标注：左上=实时数值（带单位），左下=时间窗，右上=纵轴最大值，右下=纵轴最小值
        $('#tile-tl-' + tile.key).textContent =
            last == null ? (displayTile.unavailableText || '') : formatPlotValue(last, displayTile) + (displayTile.unit || '');
        $('#tile-bl-' + tile.key).textContent = `${MONITOR_WINDOW} 秒`;
        const chartEl = document.getElementById('tile-chart-' + tile.key);
        const range = (chartEl._fullLayout && chartEl._fullLayout.yaxis)
            ? chartEl._fullLayout.yaxis.range : null;
        if (data.y.length && range) {
            $('#tile-tr-' + tile.key).textContent = formatPlotValue(range[1], displayTile) + (displayTile.unit || '');
            $('#tile-br-' + tile.key).textContent = formatPlotValue(range[0], displayTile);
        } else {
            $('#tile-tr-' + tile.key).textContent = '';
            $('#tile-br-' + tile.key).textContent = '';
        }
    });
}
