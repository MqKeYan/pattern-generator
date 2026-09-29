// 动画：帧与演化曲线渲染、播放控制

function setAnimationData(animation) {
    if (!animation?.frames && (animation?.format !== 'float32-chunks-v1' || !animation.cache_id)) {
        throw new Error(i18n.t('anim_failed_status'));
    }
    pauseAnimation();
    state.animationData = animation;
    state.animationChunks = new Map();
    state.animationChunkRequests = new Map();
    state.animationLoadPromise = null;
    state.animRenderedFor = null;
    state.animRenderToken++;
}

async function prepareAnimationData(animation) {
    setAnimationData(animation);
    const loading = loadAllAnimationChunks(animation);
    state.animationLoadPromise = loading;
    try {
        await loading;
    } catch (err) {
        if (state.animationData === animation) state.animationData = null;
        throw err;
    } finally {
        if (state.animationLoadPromise === loading) state.animationLoadPromise = null;
    }
}

async function loadAllAnimationChunks(animation) {
    if (animation.frames) return; // 旧缓存已随恢复响应完整载入
    const workers = Math.min(4, animation.chunk_count);
    await Promise.all(Array.from({ length: workers }, (_, worker) => (async () => {
        for (let index = worker; index < animation.chunk_count; index += workers) {
            if (state.animationData !== animation) return;
            await loadAnimationChunk(animation, index);
        }
    })()));
    if (state.animationData === animation && state.animationChunks.size !== animation.chunk_count) {
        throw new Error(i18n.t('anim_failed_status'));
    }
}

async function loadAnimationChunk(animation, index) {
    const chunks = state.animationChunks;
    const requests = state.animationChunkRequests;
    const cached = chunks.get(index);
    if (cached) return cached;
    if (requests.has(index)) return requests.get(index);

    const url = `/api/animation/chunk/${encodeURIComponent(animation.cache_id)}/${index}?client_id=${encodeURIComponent(state.clientId)}`;
    const request = fetch(url).then(async response => {
        if (!response.ok) throw new Error(i18n.t('anim_failed_status'));
        const buffer = await response.arrayBuffer();
        const frameCount = Math.min(animation.chunk_size, animation.total_frames - index * animation.chunk_size);
        const [height, width] = animation.shape;
        if (buffer.byteLength !== frameCount * 2 * height * width * 4) {
            throw new Error(i18n.t('anim_failed_status'));
        }
        const values = new Float32Array(buffer);
        if (state.animationData === animation) {
            chunks.set(index, values);
        }
        return values;
    }).finally(() => requests.delete(index));
    requests.set(index, request);
    return request;
}

async function getAnimationFrame(animation, frameIdx) {
    if (animation.frames) return animation.frames[frameIdx]; // 兼容尚未转换的旧缓存
    const chunkIndex = Math.floor(frameIdx / animation.chunk_size);
    const values = await loadAnimationChunk(animation, chunkIndex);
    const [height, width] = animation.shape;
    const planeSize = height * width;
    const offset = (frameIdx - chunkIndex * animation.chunk_size) * 2 * planeSize;
    const grid = start => Array.from({ length: height }, (_, row) =>
        Array.from(values.subarray(start + row * width, start + (row + 1) * width)));
    return { x_data: grid(offset), y_data: grid(offset + planeSize) };
}

// 动画帧与演化曲线渲染
/**
 * 渲染动画帧
 * @param {number} frameIdx - 帧索引
 */
async function renderAnimFrame(frameIdx) {
    const colors = getPlotTheme();
    const data = state.animationData;
    const renderToken = ++state.animRenderToken;
    const frame = await getAnimationFrame(data, frameIdx);
    if (state.animPlotPromise) await state.animPlotPromise.catch(() => {});
    if (data !== state.animationData || renderToken !== state.animRenderToken) return false;
    const displayFrames = data.total_frames;
    const iterNum = (state.animStart || 0) + frameIdx;

    // X种群帧
    const xPlot = renderAnimationPlot('chart-anim-x', [{
        z: frame.x_data,
        type: 'heatmap',
        hoverinfo: 'none',
        colorscale: 'Viridis',
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], patternHeatmapLayout(colors), { responsive: true, displayModeBar: false });

    // Y种群帧
    const yPlot = renderAnimationPlot('chart-anim-y', [{
        z: frame.y_data,
        type: 'heatmap',
        hoverinfo: 'none',
        colorscale: 'Plasma',
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], patternHeatmapLayout(colors), { responsive: true, displayModeBar: false });

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

    const combinedPlot = renderAnimationPlot('chart-anim-combined', [{
        z: combined,
        type: 'heatmap',
        hoverinfo: 'none',
        colorscale: [
            [0, 'rgb(0,30,0)'],
            [0.25, 'rgb(180,0,0)'],
            [0.5, 'rgb(200,180,0)'],
            [0.75, 'rgb(0,180,0)'],
            [1, 'rgb(0,200,200)'],
        ],
        colorbar: { title: i18n.t('density'), len: 0.8, tickformat: '.4g' },
    }], patternHeatmapLayout(colors), { responsive: true, displayModeBar: false });

    const plotting = Promise.all([xPlot, yPlot, combinedPlot]);
    state.animPlotPromise = plotting;
    try {
        await plotting;
    } finally {
        if (state.animPlotPromise === plotting) state.animPlotPromise = null;
    }
    if (data !== state.animationData || renderToken !== state.animRenderToken) return false;
    appendPlotEdgeLabels('chart-anim-x', i18n.t('anim_title_x', { iter: iterNum }), i18n.t('axis_y'), i18n.t('axis_x'));
    appendPlotEdgeLabels('chart-anim-y', i18n.t('anim_title_y', { iter: iterNum }), i18n.t('axis_y'), i18n.t('axis_x'));
    appendPlotEdgeLabels('chart-anim-combined', i18n.t('anim_title_combined', { iter: iterNum }), i18n.t('axis_y'), i18n.t('axis_x'));
    state.animRenderedFor = data;
    $('#anim-slider').value = frameIdx;
    $('#anim-frame-info').textContent = i18n.t('frame_count', { current: frameIdx, total: displayFrames });
    return true;
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

    const evolutionPlot = renderAnimationPlot('chart-anim-evo', [
        { x: adjustedTime, y: cs.x, type: 'scatter', mode: 'lines', name: i18n.t('center_x'),
          line: { color: '#3498DB', width: 2 } },
        { x: adjustedTime, y: cs.y, type: 'scatter', mode: 'lines', name: i18n.t('center_y'),
          line: { color: '#E74C3C', width: 2 } },
    ], {
        title: { text: '' },
        paper_bgcolor: 'rgba(0, 0, 0, 0)',
        plot_bgcolor: 'rgba(0, 0, 0, 0)',
        font: { color: colors.secondary, size: PLOT_FONT_SIZES.base },
        margin: evolutionPlotMargin(),
        xaxis: {
            title: '',
            gridcolor: colors.grid,
            // 设置x轴范围，显示从起始迭代到结束迭代的完整范围
            range: [actualStartTime, actualStartTime + cs.time.length - 1]
        },
        yaxis: { title: '', gridcolor: colors.grid },
        legend: { font: { size: PLOT_FONT_SIZES.legend }, bgcolor: 'rgba(0, 0, 0, 0)', bordercolor: colors.border,
            x: 1, xanchor: 'left', y: 1, yanchor: 'top' },
    }, { responsive: true, displayModeBar: false });
    Promise.resolve(evolutionPlot).then(() =>
        appendPlotEdgeLabels('chart-anim-evo', i18n.t('center_evo_title'), i18n.t('density_axis'), i18n.t('iterations_axis')));
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

        await prepareAnimationData(result.animation);
        state.animStart = result.start_iteration || animStart;
        state.animFrame = 0;
        state.animPlaying = false;

        // 设置滑块
        $('#anim-slider').max = result.animation.total_frames - 1;
        $('#anim-slider').value = 0;
        $('#anim-frame-info').textContent = i18n.t('frame_count', { current: 0, total: result.animation.total_frames });

        // 渲染第一帧
        await renderAnimFrame(0);

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
async function playAnimation() {
    try {
        while (state.animationLoadPromise) {
            await state.animationLoadPromise;
        }
    } catch (err) {
        showToast(err.message, 'error');
        return;
    }
    if (!state.animationData) {
        showToast(i18n.t('need_anim'), 'error');
        return;
    }
    if (state.animPlaying) return;

    state.animPlaying = true;
    const playbackToken = ++state.animPlaybackToken;
    const speed = parseInt($('#anim-speed').value) || 200;
    const totalFrames = state.animationData.total_frames;

    async function tick() {
        if (!state.animPlaying || playbackToken !== state.animPlaybackToken) return;
        const frame = state.animFrame;
        try {
            const rendered = await renderAnimFrame(frame);
            if (!rendered || !state.animPlaying || playbackToken !== state.animPlaybackToken) return;
            state.animFrame = (frame + 1) % totalFrames;
            state.animTimer = setTimeout(tick, speed);
        } catch (err) {
            pauseAnimation();
            showToast(err.message, 'error');
        }
    }
    tick();
}

/**
 * 暂停动画
 */
function pauseAnimation() {
    state.animPlaying = false;
    state.animPlaybackToken++;
    state.animRenderToken++;
    if (state.animTimer) {
        clearTimeout(state.animTimer);
        state.animTimer = null;
    }
}
