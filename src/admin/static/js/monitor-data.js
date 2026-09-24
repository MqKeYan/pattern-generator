// 实时监控数据：数值格式化、纵轴上限、图像定义、时间窗序列

// 监控数值格式化与纵轴上限
// 数值紧凑格式：绝对值 ≥100 取整，否则保留 1 位小数
const fmtPlotVal = v => Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10);

function formatPlotValue(value, tile) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '';
    if (tile.unit === '%') {
        const rounded = Math.round(number * 10) / 10;
        return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
    }
    return tile.displayPrecision === 2 ? number.toFixed(2) : fmtPlotVal(number);
}

function adaptPlotUnit(tile, data) {
    if (tile.adaptiveUnit !== 'mb') return { tile, data, scale: 1 };
    const values = data.y.filter(value => value != null && Number.isFinite(Number(value))).map(Number);
    if (!values.length) return { tile, data, scale: 1 };
    const max = Math.max(...values.map(value => Math.abs(value)));
    let unit = 'MB';
    let scale = 1;
    let displayPrecision = null;
    if (max >= 1024 * 1024) {
        unit = 'TB';
        scale = 1 / 1024 / 1024;
        displayPrecision = 2;
    } else if (max >= 1024) {
        unit = 'GB';
        scale = 1 / 1024;
        displayPrecision = 2;
    } else if (max >= 1) {
        unit = 'MB';
    } else if (max >= 1 / 1024) {
        unit = 'KB';
        scale = 1024;
        displayPrecision = 2;
    } else {
        unit = 'B';
        scale = 1024 * 1024;
        displayPrecision = 2;
    }
    if (tile.unit.endsWith('/s')) unit += '/s';
    return {
        tile: {
            ...tile,
            unit,
            ...(displayPrecision == null ? {} : { displayPrecision }),
        },
        data: { ...data, y: data.y.map(value => value == null ? value : Number(value) * scale) },
        scale,
    };
}

// 实时频率按当前60秒窗口动态设置纵轴，并预留10%的顶部空间。
function dynamicAxisMax(values) {
    const valid = values.filter(v => v != null && Number.isFinite(Number(v))).map(Number);
    if (!valid.length) return null;
    const max = Math.max(...valid);
    if (max <= 0) return 1;
    const padded = max * 1.1;
    const step = padded >= 1000 ? 100 : padded >= 100 ? 10 : 1;
    return Math.ceil(padded / step) * step;
}

function staticAxisThreshold(staticMax) {
    if (!Number.isFinite(staticMax)) return NaN;
    const threshold = Math.floor(staticMax / 10) * 10;
    return threshold >= staticMax ? threshold - 10 : threshold;
}

function gpuPowerAxisMax(gpuIndex, gpu, values) {
    const staticMax = Number(gpu?.power_static_cap_w ?? gpu?.power_limit_w);
    const threshold = Number(gpu?.power_dynamic_threshold_w ?? staticAxisThreshold(staticMax));
    const currentPower = Number(gpu?.power_w);
    const key = `${gpuIndex}:${gpu?.name || ''}`;
    let mode = state.gpuPowerAxisModes[key] || 'static';
    if (Number.isFinite(currentPower) && Number.isFinite(threshold) && threshold > 0) {
        mode = currentPower >= threshold ? 'dynamic' : 'static';
    }
    state.gpuPowerAxisModes[key] = mode;
    if (mode === 'dynamic') return dynamicAxisMax(values) ?? (Number.isFinite(staticMax) ? staticMax : null);
    return Number.isFinite(staticMax) ? staticMax : null;
}

function cpuPowerAxisMax(cpuIndex, cpu, values) {
    const staticMax = Number(cpu?.power_static_cap_w);
    const threshold = Number(cpu?.power_dynamic_threshold_w ?? staticAxisThreshold(staticMax));
    const currentPower = Number(cpu?.power_w);
    const key = `${cpuIndex}:${cpu?.index ?? cpuIndex}`;
    let mode = state.cpuPowerAxisModes[key] || 'static';
    if (Number.isFinite(currentPower) && Number.isFinite(threshold) && threshold > 0) {
        mode = currentPower >= threshold ? 'dynamic' : 'static';
    }
    state.cpuPowerAxisModes[key] = mode;
    if (mode === 'dynamic') return dynamicAxisMax(values) ?? (Number.isFinite(staticMax) ? staticMax : null);
    return Number.isFinite(staticMax) ? staticMax : null;
}

function gpuTemperatureAxisMax(gpuIndex, gpu, values) {
    const staticMax = 100;
    const threshold = staticAxisThreshold(staticMax);
    const currentTemperature = Number(gpu?.temp);
    const key = `${gpuIndex}:${gpu?.name || ''}`;
    let mode = state.gpuTemperatureAxisModes[key] || 'static';
    if (Number.isFinite(currentTemperature) && currentTemperature >= threshold) mode = 'dynamic';
    else if (Number.isFinite(currentTemperature)) mode = 'static';
    state.gpuTemperatureAxisModes[key] = mode;
    if (mode === 'dynamic') return dynamicAxisMax(values) ?? staticMax;
    return staticMax;
}

// 十六进制颜色 → 带 alpha 的 rgba（任务管理器样式的面积填充）
function withAlpha(hex, alpha) {
    const n = parseInt((hex || '#ffffff').slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// 监控图像定义与时间窗序列
// 每个参数独立一张图，按使用关联性排列；无 GPU 环境不生成 GPU 图。
// max 为固定纵轴上限；CPU/GPU 功耗图按当前功耗在静态上限和动态上限之间切换。
function monitorTileDefs(gpuCount, cpuCount, diskCount = 0, volumeCount = 0, volumes = []) {
    const cpuTiles = [];
    const cpuGroupCount = Math.max(1, cpuCount);
    const multiCpu = cpuCount > 1;
    if (multiCpu) {
        cpuTiles.push(
            { key: 'cpu_system_util', category: 'cpu', overview: true, name: '系统 CPU 占用率', unit: '%', color: '#3498db', max: 100, get: h => h.cpu_percent },
        );
    }
    for (let i = 0; i < cpuGroupCount; i++) {
        const label = multiCpu ? `CPU ${i + 1} ` : '';
        cpuTiles.push(
            { key: `cpu_${i}_util`, category: 'cpu', overview: true, name: multiCpu ? `${label}占用率` : '系统 CPU 占用率', unit: '%', color: '#3498db', max: 100, get: h => h.cpus?.[i]?.util_percent ?? (i === 0 ? h.cpu_percent : null) },
            { key: `cpu_${i}_freq`, category: 'cpu', overview: true, name: multiCpu ? `${label}工作频率` : 'CPU 工作频率', unit: 'MHz', color: '#48c9b0', dynamicMax: true, get: h => h.cpus?.[i]?.freq_mhz ?? (i === 0 ? h.cpu_freq_mhz : null) },
            { key: `cpu_${i}_power`, category: 'cpu', overview: true, name: multiCpu ? `${label}功耗` : 'CPU 功耗', unit: 'W', color: '#f39c12', cpuIndex: i, powerAxis: true, get: h => h.cpus?.[i]?.power_w },
        );
    }
    const tiles = [
        { key: 'proc_cpu', category: 'cpu', overview: true, name: '软件 CPU 占用率', unit: '%', color: '#5dade2', max: 100, get: h => h.proc_cpu_percent },
        ...cpuTiles,
        { key: 'mem', category: 'memory', overview: true, name: '系统内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#2ecc71', cap: 'mem_total_mb', get: h => h.mem_used_mb },
        { key: 'proc_mem', category: 'memory', name: '进程内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#9b59b6', get: h => h.proc_mem_mb },
        { key: 'swap', category: 'memory', name: '交换分区使用率', unit: '%', color: '#f1c40f', max: 100, get: h => h.swap_percent },
    ];
    if (gpuCount > 0) {
        tiles.push(
            { key: 'proc_gpu_util', category: 'gpu', overview: true, name: '软件 GPU 使用率', unit: '%', color: '#5dade2', max: 100 * gpuCount, unavailableText: '暂不可用', get: h => h.proc_gpu_util_percent },
            { key: 'proc_gpu_mem', category: 'gpu', overview: true, name: '软件 GPU 内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#e67e22', cap: 'gpu_total_mem_total_mb', unavailableText: '暂不可用', get: h => h.proc_gpu_mem_used_mb },
            { key: 'proc_gpu_shared_mem', category: 'gpu', overview: true, name: '软件 GPU 共享内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#9b59b6', cap: 'gpu_total_shared_mem_total_mb', unavailableText: '暂不可用', get: h => h.proc_gpu_shared_mem_used_mb },
            { key: 'proc_gpu_total_mem', category: 'gpu', overview: true, name: '软件 GPU 总图形内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#1abc9c', cap: 'gpu_total_total_graphics_mem_total_mb', unavailableText: '暂不可用', get: h => h.proc_gpu_total_graphics_mem_used_mb },
        );
    }
    if (gpuCount > 1) {
        tiles.push(
            { key: 'gpu_total_util', category: 'gpu', overview: true, name: 'GPU 使用率', unit: '%', color: '#3498db', max: 100 * gpuCount, get: h => h.gpu_total_util_percent },
            { key: 'gpu_total_mem', category: 'gpu', overview: true, name: 'GPU 内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#e67e22', cap: 'gpu_total_mem_total_mb', get: h => h.gpu_total_mem_used_mb },
            { key: 'gpu_total_shared_mem', category: 'gpu', overview: true, name: 'GPU 共享内存使用量', unit: 'MB', adaptiveUnit: 'mb', unavailableText: '暂不可用', color: '#9b59b6', cap: 'gpu_total_shared_mem_total_mb', get: h => h.gpu_total_shared_mem_used_mb },
            { key: 'gpu_total_power', category: 'gpu', overview: true, name: 'GPU 功耗', unit: 'W', color: '#f39c12', cap: 'gpu_total_power_static_cap_w', get: h => h.gpu_total_power_w },
        );
        for (let i = 0; i < gpuCount; i++) {
            tiles.push(
                { key: `gpu_${i}_util`, category: 'gpu', overview: true, name: `GPU ${i + 1} 使用率`, unit: '%', color: '#3498db', max: 100, gpuIndex: i, get: h => h.gpus?.[i]?.util_percent },
                { key: `gpu_${i}_mem`, category: 'gpu', overview: true, name: `GPU ${i + 1} 内存使用量`, unit: 'MB', adaptiveUnit: 'mb', color: '#e67e22', gpuIndex: i, cap: 'mem_total_mb', get: h => h.gpus?.[i]?.mem_used_mb },
                { key: `gpu_${i}_temp`, category: 'gpu', overview: true, name: `GPU ${i + 1} 温度`, unit: '℃', color: '#e74c3c', gpuIndex: i, temperatureAxis: true, get: h => h.gpus?.[i]?.temp },
                { key: `gpu_${i}_power`, category: 'gpu', overview: true, name: `GPU ${i + 1} 功耗`, unit: 'W', color: '#f39c12', gpuIndex: i, powerAxis: true, get: h => h.gpus?.[i]?.power_w },
            );
        }
    } else {
        for (let i = 0; i < gpuCount; i++) {
            tiles.push(
                { key: `gpu_${i}_util`, category: 'gpu', overview: true, name: 'GPU 使用率', unit: '%', color: '#3498db', max: 100, gpuIndex: i, get: h => h.gpus?.[i]?.util_percent },
                { key: `gpu_${i}_mem`, category: 'gpu', overview: true, name: 'GPU 内存使用量', unit: 'MB', adaptiveUnit: 'mb', color: '#e67e22', gpuIndex: i, cap: 'mem_total_mb', get: h => h.gpus?.[i]?.mem_used_mb },
                { key: `gpu_${i}_shared_mem`, category: 'gpu', overview: true, name: 'GPU 共享内存使用量', unit: 'MB', adaptiveUnit: 'mb', unavailableText: '暂不可用', color: '#9b59b6', gpuIndex: i, cap: 'shared_mem_total_mb', get: h => h.gpus?.[i]?.shared_mem_used_mb },
                { key: `gpu_${i}_total_mem`, category: 'gpu', overview: true, name: 'GPU 总图形内存使用量', unit: 'MB', adaptiveUnit: 'mb', unavailableText: '暂不可用', color: '#1abc9c', gpuIndex: i, cap: 'total_graphics_mem_total_mb', get: h => h.gpus?.[i]?.total_graphics_mem_used_mb ?? (h.gpus?.[i]?.mem_used_mb != null && h.gpus?.[i]?.shared_mem_used_mb != null ? h.gpus[i].mem_used_mb + h.gpus[i].shared_mem_used_mb : null) },
                { key: `gpu_${i}_temp`, category: 'gpu', overview: true, name: 'GPU 温度', unit: '℃', color: '#e74c3c', gpuIndex: i, temperatureAxis: true, get: h => h.gpus?.[i]?.temp },
                { key: `gpu_${i}_power`, category: 'gpu', overview: true, name: 'GPU 功耗', unit: 'W', color: '#f39c12', gpuIndex: i, powerAxis: true, get: h => h.gpus?.[i]?.power_w },
            );
        }
    }
    tiles.push(
        { key: 'disk_util', category: 'disk', overview: true, name: '软件磁盘 I/O 使用率', unit: '%', color: '#f1c40f', max: 100, get: h => h.disk_io_util_percent },
        { key: 'disk_latency', category: 'disk', overview: true, name: '软件磁盘平均响应延迟', unit: 'ms', color: '#e67e22', get: h => h.disk_latency_ms },
        { key: 'disk_queue', category: 'disk', overview: true, name: '软件磁盘队列长度', unit: '', color: '#e74c3c', get: h => h.disk_queue_length },
        { key: 'disk_read', category: 'disk', overview: true, name: '软件磁盘读取速度', unit: 'MB/s', adaptiveUnit: 'mb', color: '#2ecc71', get: h => h.disk_read_mb_s },
        { key: 'disk_write', category: 'disk', overview: true, name: '软件磁盘写入速度', unit: 'MB/s', adaptiveUnit: 'mb', color: '#1abc9c', get: h => h.disk_write_mb_s },
        { key: 'net_total', category: 'network', overview: true, name: '网络总吞吐速度', unit: 'MB/s', adaptiveUnit: 'mb', color: '#16a085', get: h => (h.net_sent_mb_s || 0) + (h.net_recv_mb_s || 0) },
        { key: 'net_packets', category: 'network', name: '网络数据包速率', unit: '包/s', color: '#16a085', get: h => (h.net_sent_packets_s || 0) + (h.net_recv_packets_s || 0) },
        { key: 'net_sent', category: 'network', name: '网络发送速度', unit: 'MB/s', adaptiveUnit: 'mb', color: '#3498db', get: h => h.net_sent_mb_s },
        { key: 'net_recv', category: 'network', name: '网络接收速度', unit: 'MB/s', adaptiveUnit: 'mb', color: '#9b59b6', get: h => h.net_recv_mb_s },
        { key: 'clients', category: 'service', overview: true, name: '在线客户端数量', unit: '', color: '#3498db', integerAxis: true, get: h => h.online_clients },
        { key: 'running_tasks', category: 'service', name: '运行中任务数量', unit: '', color: '#2ecc71', integerAxis: true, get: h => h.running_tasks },
        { key: 'waiting_tasks', category: 'service', name: '等待中任务数量', unit: '', color: '#f39c12', integerAxis: true, get: h => h.waiting_tasks },
    );
    return tiles;
}

function visibleMonitorTileDefs(gpuCount, cpuCount, diskCount = 0, volumeCount = 0, volumes = []) {
    const tiles = monitorTileDefs(gpuCount, cpuCount, diskCount, volumeCount, volumes);
    return state.monitorCategory === 'overview'
        ? tiles
        : tiles.filter(tile => tile.category === state.monitorCategory);
}

let monitorTilesBuilt = null;

function clearMonitorTiles() {
    const grid = $('#monitor-grid');
    if (!grid) return;
    grid.querySelectorAll('.chart-box').forEach(chart => {
        if (chart._fullLayout) Plotly.purge(chart);
    });
    grid.innerHTML = '';
    monitorTilesBuilt = null;
}

function ensureMonitorTiles(gpuCount, cpuCount, diskCount, volumeCount, volumes) {
    const tiles = visibleMonitorTileDefs(gpuCount, cpuCount, diskCount, volumeCount, volumes);
    const volumeKey = volumes.map(volume => volume.mountpoint || '').join('|');
    const key = `${state.monitorCategory}-mode-${state.monitorViewMode}-cpu-${cpuCount}-gpu-${gpuCount}-disk-${diskCount}-volume-${volumeKey}`;
    if (monitorTilesBuilt === key) return;
    monitorTilesBuilt = key;
    const grid = $('#monitor-grid');
    grid.querySelectorAll('.chart-box').forEach(chart => {
        if (chart._fullLayout) Plotly.purge(chart);
    });
    grid.innerHTML = '';
    tiles.forEach(t => {
        const tile = document.createElement('div');
        const compact = state.monitorViewMode === 'compact';
        tile.className = compact ? 'chart-tile compact-tile' : 'chart-tile';
        tile.innerHTML = (compact ? '' : `<div class="tile-head"><span class="tile-name">${esc(t.name)}</span></div>`)
            + `<div class="chart-box" id="tile-chart-${t.key}">`
            + `<span class="tile-corner tl" id="tile-tl-${t.key}"></span>`
            + `<span class="tile-corner tr" id="tile-tr-${t.key}"></span>`
            + `<span class="tile-corner bl" id="tile-bl-${t.key}"></span>`
            + `<span class="tile-corner br" id="tile-br-${t.key}"></span>`
            + `</div>`;
        grid.appendChild(tile);
    });
}

const secOfDay = s => {
    const [hh, mm, ss] = s.split(':').map(Number);
    return hh * 3600 + mm * 60 + ss;
};

const sampleTimeInSeconds = value => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    return secOfDay(String(value));
};

// 固定窗口横坐标：最新样本位于右端（x=0），只保留时间窗内的样本。
// 支持服务端 Unix 时间戳和其他监控图使用的 HH:MM:SS 字符串。
function windowSeries(times, values) {
    if (!times.length) return { x: [], y: [], span: null };
    const base = sampleTimeInSeconds(times[times.length - 1]);
    const inWin = [];
    for (let i = 0; i < times.length; i++) {
        let off = sampleTimeInSeconds(times[i]) - base;
        if (off > 43200) off -= 86400;  // 跨午夜
        if (off >= -(MONITOR_WINDOW - 1)) inWin.push({ off, y: values[i] });
    }
    if (!inWin.length) return { x: [], y: [], span: null };
    return {
        x: inWin.map(p => p.off),
        y: inWin.map(p => p.y),
        span: -inWin[0].off,
    };
}
