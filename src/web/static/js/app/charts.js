// 图表渲染：二维斑图、时间演化曲线、三维斑图

// Plotly 图表通用工具
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

function appendPlotEdgeLabels(chartId, title, yLabel, xLabel) {
    const chart = document.getElementById(chartId);
    if (!chart) return;
    chart.querySelectorAll('.plot-edge-label').forEach(label => label.remove());
    [
        ['title', title],
        ['y-axis', yLabel],
        ['x-axis', xLabel],
    ].forEach(([kind, text]) => {
        const label = document.createElement('span');
        label.className = `plot-edge-label plot-edge-label-${kind}`;
        label.textContent = text;
        chart.appendChild(label);
    });
}

// 二维斑图渲染
/**
 * 渲染二维斑图
 * 包括X种群、Y种群热力图和合并斑图
 * @param {Object} vizData - 可视化数据
 */
function render2DPatterns(vizData) {
    const colors = getPlotTheme();
    const evolutionInset = 48;
    const xPop = vizData['2d_patterns'].x_population;
    const yPop = vizData['2d_patterns'].y_population;
    const combined = vizData.combined_pattern;
    const evolution = vizData.evolution_curves;

    // X种群热力图
    Plotly.newPlot('chart-x-pop', [{
        z: xPop.data,
        type: 'heatmap',
        colorscale: 'Viridis',
        hoverinfo: 'skip',
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], {
        title: { text: '' },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 50, r: 50, t: 50, b: 70 },
        xaxis: { title: '', range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: '', range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: true, displayModeBar: false });
    appendPlotEdgeLabels('chart-x-pop', xPop.title, i18n.t('axis_y'), i18n.t('axis_x'));

    // Y种群热力图
    Plotly.newPlot('chart-y-pop', [{
        z: yPop.data,
        type: 'heatmap',
        colorscale: 'Plasma',
        hoverinfo: 'skip',
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], {
        title: { text: '' },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 50, r: 50, t: 50, b: 70 },
        xaxis: { title: '', range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: '', range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: true, displayModeBar: false });
    appendPlotEdgeLabels('chart-y-pop', yPop.title, i18n.t('axis_y'), i18n.t('axis_x'));

    // 合并斑图
    const xNorm = combined.x_normalized;
    const yNorm = combined.y_normalized;

    Plotly.newPlot('chart-combined', [{
        z: xNorm.map((row, i) => row.map((v, j) => v + yNorm[i][j])),
        type: 'heatmap',
        hoverinfo: 'skip',
        colorscale: [
            [0, 'rgb(0,30,0)'],
            [0.25, 'rgb(180,0,0)'],
            [0.5, 'rgb(200,180,0)'],
            [0.75, 'rgb(0,180,0)'],
            [1, 'rgb(0,200,200)'],
        ],
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], {
        title: { text: '' },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 50, r: 50, t: 50, b: 70 },
        xaxis: { title: '', range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: '', range: [0, 100], tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: true, displayModeBar: false });
    appendPlotEdgeLabels('chart-combined', combined.title, i18n.t('axis_y'), i18n.t('axis_x'));

    // 跟踪点标记（在合并图上）
    if (combined.track_points && combined.track_points.length > 0) {
        const annotations = combined.track_points.map(p => ({
            x: p.y, y: p.x,
            xref: 'x', yref: 'y',
            text: `(${p.x},${p.y})`,
            showarrow: true,
            arrowhead: 0,
            font: { color: '#fff', size: PLOT_FONT_SIZES.annotation },
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
        hoverinfo: 'skip',
        line: { color: c.color, width: c.line_width, dash: c.dash, simplify: true },
        visible: c.visible ? true : 'legendonly',
    }));
    const curveXValues = curveTraces.flatMap(c => c.x).filter(Number.isFinite);
    const xMin = curveXValues.length ? Math.min(...curveXValues) : 0;
    const xMax = curveXValues.length ? Math.max(...curveXValues) : 0;

    Plotly.newPlot('chart-evolution', curveTraces, {
        title: { text: '' },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 96, r: 112, t: evolutionInset, b: evolutionInset },
        dragmode: 'pan',
        yaxis: { title: '', gridcolor: colors.grid, zeroline: false, fixedrange: true },
        legend: {
            font: { size: PLOT_FONT_SIZES.legend },
            bgcolor: 'rgba(0, 0, 0, 0)',
            bordercolor: colors.border,
            x: 1,
            xanchor: 'left',
            y: 1,
            yanchor: 'top',
        },
        hovermode: 'closest',
        xaxis: {
            title: '',
            gridcolor: colors.grid,
            zeroline: false,
            // 使用双端范围条调整曲线的显示起点和终点
            rangeslider: {
                visible: true,
                range: [xMin, xMax],
                thickness: 0.06,
                bgcolor: 'rgba(25, 35, 53, 0.72)',
                bordercolor: colors.border,
                borderwidth: 1,
            },
        },
    }, { responsive: true, displayModeBar: false });

    // 主图拖动与范围条交互（见 charts/evolution.js）
    const evoChart = document.getElementById('chart-evolution');
    appendPlotEdgeLabels('chart-evolution', evolution.title, i18n.t('density_axis'), i18n.t('iterations_axis'));
    initEvolutionInteraction(evoChart, xMin, xMax);
}

// 时间演化曲线：范围钳制、主图平移与缩略图滑块交互
function initEvolutionInteraction(evoChart, xMin, xMax) {
    // 缩略图滑块最小间距：选择框在缩略图上至少 40px 宽，避免缩小到找不到
    const minWindowWidth = () => {
        const sliderW = evoChart.querySelector('.rangeslider-bg')?.getBoundingClientRect().width;
        if (!sliderW || sliderW <= 0) return 0;
        return (xMax - xMin) * 40 / sliderW;
    };
    // 钳制：窗口不越数据左右边界，宽度不小于最小间距；无需调整时返回 null
    const clampEvoRange = (range, preserveSliderSize = false) => {
        if (!Array.isArray(range)) return null;
        let r0 = range[0], r1 = range[1];
        if (!Number.isFinite(r0) || !Number.isFinite(r1)) return null;
        const span = xMax - xMin;
        if (span <= 0) return null;
        let width = r1 - r0;
        const minW = Math.min(Math.max(minWindowWidth(), 1e-9), span);
        if (!preserveSliderSize && width < minW) {
            // 窗口过窄：扩宽到最小间距（保持右缘，右缘贴界则向左扩）
            r0 = (r1 - minW < xMin) ? xMin : r1 - minW;
            r1 = r0 + minW;
            width = minW;
        }
        if (r0 < xMin) {
            r0 = xMin;
            r1 = xMin + width;
        } else if (r1 > xMax) {
            r1 = xMax;
            r0 = xMax - width;
        }
        if (r1 - r0 >= span - 1e-9) { r0 = xMin; r1 = xMax; }
        return (r0 === range[0] && r1 === range[1]) ? null : [r0, r1];
    };
    let evoSyncFrame = 0;
    let pendingEvoRange = null;
    let evoSliderDragging = false;
    const syncEvoRange = (range) => {
        pendingEvoRange = range;
        if (evoSyncFrame) return;
        evoSyncFrame = requestAnimationFrame(() => {
            evoSyncFrame = 0;
            const nextRange = pendingEvoRange;
            pendingEvoRange = null;
            if (!nextRange) return;
            // 拖动期间实时联动缩略图：固定其总范围，选择框随主图移动
            Plotly.relayout(evoChart, {
                'xaxis.range': nextRange,
                'xaxis.rangeslider.range': [xMin, xMax],
            }).catch(() => {});
        });
    };
    const onEvoRelayout = (evt) => {
        let range = evt?.['xaxis.range'];
        if (!Array.isArray(range)) {
            const r0 = evt?.['xaxis.range[0]'];
            const r1 = evt?.['xaxis.range[1]'];
            if (!Number.isFinite(r0) && !Number.isFinite(r1)) return;
            const cur = evoChart._fullLayout?.xaxis?.range || [xMin, xMax];
            range = [Number.isFinite(r0) ? r0 : cur[0], Number.isFinite(r1) ? r1 : cur[1]];
        }
        const next = clampEvoRange(range, evoSliderDragging);
        if (!next) return;
        // 越界或缩得过窄：结束本轮原生交互（范围条拖动/滚轮缩放）再钳制，避免被后续事件覆盖
        const dragCover = evoChart.querySelector('.dragcover');
        if (dragCover) dragCover.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        Plotly.relayout(evoChart, {
            'xaxis.range': next,
            // 固定缩略图总范围，只让其中的小显示框随主图移动
            'xaxis.rangeslider.range': [xMin, xMax],
        }).catch(() => {});
    };
    const onMainPanStart = (event) => {
        if (event.button !== 0 || !event.target.classList.contains('nsewdrag')) return;
        const startRange = evoChart._fullLayout?.xaxis?.range?.slice();
        const plotW = evoChart._fullLayout?.xaxis?._length;
        const span = xMax - xMin;
        if (!startRange || !plotW || plotW <= 0 || span <= 0) return;
        // 禁止事件继续传给 Plotly 原生 pan（越界会压缩成缩放）
        event.preventDefault();
        event.stopImmediatePropagation();
        const startX = event.clientX;
        const onMove = (moveEvent) => {
            // 内容跟随鼠标：鼠标向右移动，显示窗口相应向左平移
            const shift = (moveEvent.clientX - startX) / plotW * span;
            const next = clampEvoRange([startRange[0] - shift, startRange[1] - shift]);
            syncEvoRange(next || [startRange[0] - shift, startRange[1] - shift]);
        };
        const onEnd = () => {
            document.removeEventListener('mousemove', onMove, true);
            document.removeEventListener('mouseup', onEnd, true);
        };
        document.addEventListener('mousemove', onMove, true);
        document.addEventListener('mouseup', onEnd, true);
    };
    // 缩略图交互：只保留滑块（含两端握柄）平移，禁用空白处（遮罩/背景）长按拖动重构窗口
    const sliderParts = '.rangeslider-slidebox, .rangeslider-grabber-min, .rangeslider-grabber-max, .rangeslider-handle-min, .rangeslider-handle-max, .rangeslider-grabarea-min, .rangeslider-grabarea-max';
    const onEvoSliderStart = (event) => {
        if (event.button !== 0) return;
        if (event.target.classList.contains('rangeslider-slidebox')) {
            const sliderRect = evoChart.querySelector('.rangeslider-bg')?.getBoundingClientRect();
            const sliderWidth = sliderRect?.width;
            const span = xMax - xMin;
            let range = evoChart._fullLayout?.xaxis?.range?.slice();
            if (!sliderWidth || span <= 0 || !range) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            evoSliderDragging = true;
            let previousX = Math.max(sliderRect.left, Math.min(sliderRect.right, event.clientX));
            const minWidth = Math.min(Math.max(minWindowWidth(), 1e-9), span);
            const onSliderMove = (moveEvent) => {
                // 以按下点为基准累计位移；指针越出缩略图边缘后不再缩小。
                const pointerX = Math.max(sliderRect.left, Math.min(sliderRect.right, moveEvent.clientX));
                const shift = (pointerX - previousX) / sliderWidth * span;
                previousX = pointerX;
                if (!shift) return;
                let left = Math.max(xMin, range[0] + shift);
                let right = Math.min(xMax, range[1] + shift);
                // 碰到边缘后以缩小的当前范围继续移动，回拖时保持新宽度。
                if (right - left < minWidth) {
                    if (shift < 0) right = left + minWidth;
                    else left = right - minWidth;
                }
                range = [left, right];
                syncEvoRange(range);
            };
            const onSliderEnd = () => {
                document.removeEventListener('mousemove', onSliderMove, true);
                document.removeEventListener('mouseup', onSliderEnd, true);
                requestAnimationFrame(() => { evoSliderDragging = false; });
            };
            document.addEventListener('mousemove', onSliderMove, true);
            document.addEventListener('mouseup', onSliderEnd, true);
            return;
        }
        if (event.target.closest(sliderParts)) {
            evoSliderDragging = true;
            const onSliderEnd = () => {
                document.removeEventListener('mouseup', onSliderEnd, true);
                requestAnimationFrame(() => { evoSliderDragging = false; });
            };
            document.addEventListener('mouseup', onSliderEnd, true);
            return;
        }
        const cls = event.target.className?.baseVal || event.target.className || '';
        if (!cls.startsWith('rangeslider-')) return;
        event.preventDefault();
        event.stopImmediatePropagation();
    };
    // 主图水平拖动 + 范围条/滚轮缩放的越界与最小间距钳制
    evoChart.addEventListener('mousedown', onMainPanStart, true);
    evoChart.addEventListener('mousedown', onEvoSliderStart, true);
    evoChart.on('plotly_relayouting', onEvoRelayout);
    evoChart.on('plotly_relayout', onEvoRelayout);
}

// 三维斑图渲染与相机稳定
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
    // 刻度文本：保留4位有效数字并去除多余零
    const fmtTick = v => String(Number((v / 100 * zRange + zMin).toPrecision(4)));
    // Z轴刻度，起点不标避免与XY轴原点重叠
    const zTickVals = [20, 40, 60, 80, 100];
    const zTickText = zTickVals.map(fmtTick);
    // 颜色条刻度覆盖全范围，映射真实值
    const cbarTickVals = [0, 20, 40, 60, 80, 100];
    const cbarTickText = cbarTickVals.map(fmtTick);

    const surfaceTrace = {
        z: zScaled,
        type: 'surface',
        colorscale: 'Viridis',
        colorbar: {
            title: { text: i18n.t('density'), font: { size: PLOT_FONT_SIZES.axisTitle, color: colors.secondary } },
            tickfont: { size: PLOT_FONT_SIZES.tick, color: colors.muted },
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
        title: { text: vizData.title, font: { size: PLOT_FONT_SIZES.title, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        scene: {
            xaxis: {
                title: { text: i18n.t('axis_x'), standoff: 25, font: { size: PLOT_FONT_SIZES.axisTitle, color: colors.text } },
                showgrid: true, gridcolor: colors.grid, gridwidth: 1,
                color: colors.secondary,
                tickfont: { size: PLOT_FONT_SIZES.tick, color: colors.muted },
                showline: true, linecolor: colors.axis, linewidth: 3,
                ticks: 'outside', tickcolor: colors.axis, ticklen: 8,
                range: [0, 100], tickangle: 0,
                tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100],
            },
            yaxis: {
                title: { text: i18n.t('axis_y'), standoff: 25, font: { size: PLOT_FONT_SIZES.axisTitle, color: colors.text } },
                showgrid: true, gridcolor: colors.grid, gridwidth: 1,
                color: colors.secondary,
                tickfont: { size: PLOT_FONT_SIZES.tick, color: colors.muted },
                showline: true, linecolor: colors.axis, linewidth: 3,
                ticks: 'outside', tickcolor: colors.axis, ticklen: 8,
                range: [0, 100], tickangle: 0,
                tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100],
            },
            zaxis: {
                title: { text: i18n.t('density_axis'), standoff: 25, font: { size: PLOT_FONT_SIZES.axisTitle, color: colors.text } },
                showgrid: true, gridcolor: colors.grid, gridwidth: 1,
                color: colors.secondary,
                tickfont: { size: PLOT_FONT_SIZES.tick, color: colors.muted },
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
