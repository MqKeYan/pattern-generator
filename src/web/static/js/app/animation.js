// 动画：帧与演化曲线渲染、播放控制

// 动画帧与演化曲线渲染
/**
 * 渲染动画帧
 * @param {number} frameIdx - 帧索引
 */
function renderAnimFrame(frameIdx) {
    const colors = getPlotTheme();
    const data = state.animationData;
    const frame = data.frames[frameIdx];
    const displayFrames = data.total_frames;
    const iterNum = (state.animStart || 0) + frameIdx;

    // X种群帧
    renderAnimationPlot('chart-anim-x', [{
        z: frame.x_data,
        type: 'heatmap',
        colorscale: 'Viridis',
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], {
        title: { text: i18n.t('anim_title_x', { iter: iterNum }), font: { size: PLOT_FONT_SIZES.title, color: colors.text } },
        height: 420,
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 40, r: 35, t: 35, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: false, displayModeBar: false });

    // Y种群帧
    renderAnimationPlot('chart-anim-y', [{
        z: frame.y_data,
        type: 'heatmap',
        colorscale: 'Plasma',
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], {
        title: { text: i18n.t('anim_title_y', { iter: iterNum }), font: { size: PLOT_FONT_SIZES.title, color: colors.text } },
        height: 420,
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 40, r: 35, t: 35, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
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

    renderAnimationPlot('chart-anim-combined', [{
        z: combined,
        type: 'heatmap',
        colorscale: [
            [0, 'rgb(0,30,0)'],
            [0.25, 'rgb(180,0,0)'],
            [0.5, 'rgb(200,180,0)'],
            [0.75, 'rgb(0,180,0)'],
            [1, 'rgb(0,200,200)'],
        ],
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], {
        title: { text: i18n.t('anim_title_combined', { iter: iterNum }), font: { size: PLOT_FONT_SIZES.title, color: colors.text } },
        height: 420,
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 40, r: 35, t: 35, b: 60 },
        xaxis: { title: i18n.t('axis_x'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], scaleanchor: 'y', constrain: 'domain' },
        yaxis: { title: i18n.t('axis_y'), range: [0, 100], autorange: false, fixedrange: true, tickmode: 'array', tickvals: [0, 20, 40, 60, 80, 100], constrain: 'domain' },
    }, { responsive: false, displayModeBar: false });

    $('#anim-slider').value = frameIdx;
    $('#anim-frame-info').textContent = i18n.t('frame_count', { current: frameIdx, total: displayFrames });
}

/**
 * 渲染动画演化曲线
 */
function renderAnimEvolution() {
    const colors = getPlotTheme();
    const data = state.animationData;
    const cs = data.center_series;

    // 使用实际的起始迭代次数调整时间轴
    const actualStartTime = state.animStart || 0;
    const adjustedTime = cs.time.map(t => t + actualStartTime);

    renderAnimationPlot('chart-anim-evo', [
        { x: adjustedTime, y: cs.x, type: 'scatter', mode: 'lines', name: i18n.t('center_x'),
          line: { color: '#3498DB', width: 2 } },
        { x: adjustedTime, y: cs.y, type: 'scatter', mode: 'lines', name: i18n.t('center_y'),
          line: { color: '#E74C3C', width: 2 } },
    ], {
        title: { text: i18n.t('center_evo_title'), font: { size: PLOT_FONT_SIZES.title, color: colors.text } },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: { l: 50, r: 20, t: 35, b: 60 },
        xaxis: {
            title: i18n.t('iterations_axis'),
            gridcolor: colors.grid,
            // 设置x轴范围，显示从起始迭代到结束迭代的完整范围
            range: [actualStartTime, actualStartTime + cs.time.length - 1]
        },
        yaxis: { title: i18n.t('density_axis'), gridcolor: colors.grid },
        legend: { font: { size: PLOT_FONT_SIZES.legend }, bgcolor: 'rgba(0, 0, 0, 0)', bordercolor: colors.border },
    }, { responsive: true, displayModeBar: false });
}

// 动画任务运行与播放控制
/**
 * 运行动画
 * 提交任务并轮询，完成后初始化动画界面
 */
async function runAnimation() {
    setStatus(i18n.t('anim_preparing'));

    try {
        const params = getParams();
        const initRanges = getInitRanges();
        const animStart = parseInt($('#anim-start').value) || 0;
        const animEnd = parseInt($('#anim-end').value) || 300;

        // 生成帧数 = 结束 - 起始，动画需要模拟到结束迭代但只存储范围内的帧
        const displayFrames = animEnd - animStart;
        const result = await submitAndPoll('/api/animate', {
            model: state.currentModel,
            params,
            frames: displayFrames,
            start_frame: animStart,
            x_min: initRanges.x_min,
            x_max: initRanges.x_max,
            y_min: initRanges.y_min,
            y_max: initRanges.y_max,
        });

        state.animationData = result.animation;
        state.animStart = result.start_iteration || animStart;
        state.animFrame = 0;
        state.animPlaying = false;

        // 设置滑块
        $('#anim-slider').max = result.animation.total_frames - 1;
        $('#anim-slider').value = 0;
        $('#anim-frame-info').textContent = i18n.t('frame_count', { current: 0, total: result.animation.total_frames });

        // 渲染第一帧
        renderAnimFrame(0);

        // 渲染中心点时间序列
        renderAnimEvolution();

        hideLoading();
        showToast(i18n.t('anim_ready'), 'success');
        setStatus(i18n.t('anim_ready_status'), 'success');
    } catch (err) {
        console.error('动画准备失败:', err);
        hideLoading();
        const cancelled = err.message === i18n.t('task_cancelled');
        showToast(err.message, cancelled ? 'info' : 'error');
        if (cancelled) setClientOperationStatus('status_task_cancel_requested', 'info');
        else setStatus(i18n.t('anim_failed_status'), 'error');
    } finally {
        state.currentTaskId = null;
    }
}
/**
 * 播放动画
 */
function playAnimation() {
    if (!state.animationData) {
        showToast(i18n.t('need_anim'), 'error');
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
