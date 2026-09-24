// 侧栏：模型选择、参数设置、时间演化跟踪点

// 模型切换：同步参数、初始值、迭代与动画默认值
/**
 * 模型切换处理
 * 更新参数面板和初始值设置
 */
function onModelChange() {
    const model = $('#model-select').value;
    state.currentModel = model;
    const cfg = state.modelConfigs[model];
    const initRange = state.initRanges[model];

    // 更新参数
    renderParams(cfg.params, cfg.defaults);

    // 更新初始值
    $('#x-min').value = initRange.x_range[0];
    $('#x-max').value = initRange.x_range[1];
    $('#y-min').value = initRange.y_range[0];
    $('#y-max').value = initRange.y_range[1];
    $('#init-desc').textContent = initRange.description;

    // 更新迭代次数
    $('#iter-range').min = cfg.min_iterations;
    $('#iter-range').max = cfg.max_iterations;
    $('#iter-range').value = cfg.recommended_iterations;
    $('#iter-value').value = cfg.recommended_iterations;

    // 更新动画设置：让默认迭代次数位于动画中间
    const recommendedIters = cfg.recommended_iterations;
    const animFrames = 300; // 默认帧数
    const halfFrames = Math.floor(animFrames / 2);

    // 计算起始和结束迭代，确保不小于0
    const animStart = Math.max(0, recommendedIters - halfFrames);
    const animEnd = animStart + animFrames;

    // 设置动画默认值
    $('#anim-start').value = animStart;
    $('#anim-end').value = animEnd;
    $('#anim-frames').value = animFrames;
}

// 参数面板：渲染与取值
/**
 * 渲染参数面板
 * @param {Array} names - 参数名称数组
 * @param {Array} defaults - 默认值数组
 */
function renderParams(names, defaults) {
    const container = $('#params-container');
    container.innerHTML = names.map((name, i) => {
        const cnName = (state.paramNames && state.paramNames[name]) || '';
        return `
        <div class="param-row">
            <span class="param-name">${name} ${cnName}：</span>
            <input type="number" class="num-input param-input" data-index="${i}"
                   value="${defaults[i]}" step="any">
            <button class="param-reset" data-impact="caution" data-index="${i}" data-default="${defaults[i]}">重置</button>
        </div>`;
    }).join('');

    // 绑定重置按钮
    container.querySelectorAll('.param-reset').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = btn.dataset.index;
            const defVal = btn.dataset.default;
            container.querySelector(`.param-input[data-index="${idx}"]`).value = defVal;
        });
    });
}

/**
 * 获取当前参数值
 * @returns {Array} 参数值数组
 */
function getParams() {
    const inputs = $$('.param-input');
    return Array.from(inputs).map(inp => parseFloat(inp.value) || 0);
}

/**
 * 获取初始值范围
 * @returns {Object} x和y的范围
 */
function getInitRanges() {
    return {
        x_min: parseFloat($('#x-min').value) || 0.5,
        x_max: parseFloat($('#x-max').value) || 1.0,
        y_min: parseFloat($('#y-min').value) || 0.5,
        y_max: parseFloat($('#y-max').value) || 1.0,
    };
}

/**
 * 获取迭代次数
 * @returns {number} 迭代次数
 */
function getIterations() {
    return parseInt($('#iter-value').value) || 9000;
}

// 时间演化跟踪点管理
/**
 * 添加跟踪点
 * 验证坐标并更新跟踪点列表
 */
function addTrackPoint() {
    const x = parseInt($('#track-x').value);
    const y = parseInt($('#track-y').value);
    if (isNaN(x) || isNaN(y) || x < 0 || x > 99 || y < 0 || y > 99) {
        showToast(i18n.t('point_range_error'), 'error');
        return;
    }
    if (state.trackPoints.some(p => p.x === x && p.y === y)) {
        showToast(i18n.t('point_exists', { x, y }), 'info');
        return;
    }
    // 为跟踪点分配颜色（8 种可选颜色循环使用）
    const colors = ['#2ecc71', '#1abc9c', '#3498db', '#9b59b6', '#e74c3c', '#f39c12', '#e67e22', '#34495e'];
    const colorIndex = state.trackPoints.length % colors.length;
    state.trackPoints.push({ id: createTrackPointId(), x, y, color: colors[colorIndex] });
    updateTrackList();
}

function createTrackPointId() {
    return `point-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * 清除所有跟踪点
 */
function clearTrackPoints() {
    state.trackPoints = [];
    updateTrackList();
}

/**
 * 更新跟踪点列表显示
 */
function updateTrackList() {
    const el = $('#track-list');
    if (state.trackPoints.length === 0) {
        el.textContent = i18n.t('track_list_center');
    } else {
        renderTrackPoints();
    }
}

/**
 * 渲染跟踪点列表
 */
function renderTrackPoints() {
    const el = $('#track-list');
    el.innerHTML = '';
    state.trackPoints.forEach(p => {
        // 旧版持久化数据没有 id，渲染时补齐以支持后续编辑和删除。
        if (!p.id) p.id = createTrackPointId();
        // 确保每个跟踪点都有颜色（兼容旧数据）
        if (!p.color) {
            const colors = ['#2ecc71', '#1abc9c', '#3498db', '#9b59b6', '#e74c3c', '#f39c12', '#e67e22', '#34495e'];
            p.color = colors[state.trackPoints.indexOf(p) % colors.length];
        }
        const li = document.createElement('li');
        li.className = 'track-item';

        // 颜色圆点，与演化曲线颜色一致
        const dot = document.createElement('span');
        dot.className = 'track-dot';
        dot.style.background = p.color;

        const label = document.createElement('span');
        label.className = 'track-label';
        label.textContent = `(${p.x},${p.y})`;

        // 操作按钮：编辑 / 删除
        const ops = document.createElement('span');
        ops.className = 'track-ops';
        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn-outline btn-accent';
        editBtn.textContent = i18n.t('edit');
        editBtn.addEventListener('click', () => startEditTrack(p.id));
        const delBtn = document.createElement('button');
        delBtn.className = 'btn btn-outline btn-danger';
        delBtn.textContent = i18n.t('delete');
        delBtn.addEventListener('click', () => { deleteTrackPoint(p.id); saveSettings(); });
        ops.appendChild(editBtn);
        ops.appendChild(delBtn);

        li.appendChild(dot);
        li.appendChild(label);
        li.appendChild(ops);
        el.appendChild(li);
    });
}

/**
 * 编辑跟踪点
 * 将跟踪点的坐标填入输入框
 */
function startEditTrack(id) {
    const p = state.trackPoints.find(pt => pt.id === id);
    if (!p) return;
    $('#track-x').value = p.x;
    $('#track-y').value = p.y;
    // 删除原跟踪点，添加新跟踪点（保持颜色不变）
    deleteTrackPoint(id);
    saveSettings();
}

/**
 * 删除跟踪点
 * 根据 ID 删除跟踪点
 */
function deleteTrackPoint(id) {
    state.trackPoints = state.trackPoints.filter(p => p.id !== id);
    updateTrackList();
}
