const { createApp, ref, reactive, computed, watch, onMounted } = Vue;

createApp({
  setup() {
    // ── 状态 ─────────────────────────────────────────
    const models = ref([]);
    const modelConfigs = ref({});
    const initRangesAll = ref({});
    const paramMeanings = ref({});

    const currentModel = ref('模型1');
    const params = ref([]);
    const iterations = ref(9000);
    const frames = ref(300);
    const initDesc = ref('');

    // 初始值范围
    const xMin = ref(0.95);
    const xMax = ref(1.05);
    const yMin = ref(0.80);
    const yMax = ref(1.0);

    // 跟踪点
    const trackX = ref(50);
    const trackY = ref(50);
    const trackPoints = ref([]);

    // 任务
    const currentJobId = ref(null);
    const jobStatus = ref(null);
    const jobProgress = ref(0);
    const jobResult = ref(null);
    const isSimulating = computed(() =>
      jobStatus.value === 'running' || jobStatus.value === 'queued'
    );

    // 系统状态
    const appVersion = ref('');

    const uptime = ref('00:00:00');
    const cpuPercent = ref(0);
    const gpuPercent = ref(0);
    const memMb = ref(0);
    const workersBusy = ref(0);
    const workersTotal = ref(0);
    const queueLength = ref(0);

    const activeTab = ref(0);
    const tabs = ['二维斑图', '三维斑图', '动画演示'];

    // ── session ──────────────────────────────────────
    const sessionId = ref(
      localStorage.getItem('pattern_session_id') || crypto.randomUUID()
    );
    localStorage.setItem('pattern_session_id', sessionId.value);

    // ── 计算属性 ────────────────────────────────────
    const currentParams = computed(() => {
      const config = modelConfigs.value[currentModel.value];
      if (!config) return [];
      return config.params.map((name, i) => ({
        name: (paramMeanings.value[currentModel.value]?.[name] || `参数${i + 1}`) + ':',
        key: name,
      }));
    });

    const statusSegments = computed(() => [
      '版本号: ' + (appVersion.value || '...'),
      '运行时间: ' + uptime.value,
      'CPU: ' + cpuPercent.value + '%',
      'GPU: ' + gpuPercent.value + '%',
      '内存: ' + Math.round(memMb.value) + ' MB',
      'Workers: ' + workersBusy.value + '/' + workersTotal.value + ' 忙',
      '队列: ' + queueLength.value,
    ]);

    const jobStatusText = computed(() => {
      if (jobStatus.value === 'queued') return '排队中...';
      if (jobStatus.value === 'running') return '运行中 ' + jobProgress.value + '%';
      if (jobStatus.value === 'completed') return '已完成';
      if (jobStatus.value === 'error') return '出错了';
      return '';
    });

    const initRanges = computed(() => [
      { label: 'X 最小值', value: xMin, key: 'x_min' },
      { label: 'X 最大值', value: xMax, key: 'x_max' },
      { label: 'Y 最小值', value: yMin, key: 'y_min' },
      { label: 'Y 最大值', value: yMax, key: 'y_max' },
    ]);

    const trackDisplay = computed(() => {
      if (!trackPoints.value.length) return '已添加点';
      return trackPoints.value.map(p => `(${p.x},${p.y})`).join(' ');
    });

    // ── 方法 ─────────────────────────────────────────
    async function fetchModels() {
      try {
        const res = await fetch('/api/models');
        const data = await res.json();
        models.value = data.models;
        modelConfigs.value = data.configs;
        initRangesAll.value = data.init_ranges;
        paramMeanings.value = data.param_meanings;
        syncModelDefaults();
      } catch (e) {
        console.error('加载模型失败:', e);
      }
    }

    function syncModelDefaults() {
      const config = modelConfigs.value[currentModel.value];
      if (!config) return;
      params.value = [...config.defaults];
      iterations.value = config.recommended_iterations;
      const ir = initRangesAll.value[currentModel.value];
      if (ir) {
        xMin.value = ir.x_range[0];
        xMax.value = ir.x_range[1];
        yMin.value = ir.y_range[0];
        yMax.value = ir.y_range[1];
        initDesc.value = ir.description || '';
      }
    }

    function onModelChange() {
      if (isSimulating.value) {
        alert('模拟进行中，请等待完成');
        return;
      }
      syncModelDefaults();
    }

    function resetParam(index) {
      const config = modelConfigs.value[currentModel.value];
      if (config) params.value[index] = config.defaults[index];
    }

    function resetAllParams() {
      const config = modelConfigs.value[currentModel.value];
      if (config) params.value = [...config.defaults];
    }

    function resetInit(key) {
      const ir = initRangesAll.value[currentModel.value];
      if (!ir) return;
      const map = {
        x_min: [ir.x_range[0], xMin],
        x_max: [ir.x_range[1], xMax],
        y_min: [ir.y_range[0], yMin],
        y_max: [ir.y_range[1], yMax],
      };
      if (map[key]) map[key][1].value = map[key][0];
    }

    function applyBestInit() {
      const ir = initRangesAll.value[currentModel.value];
      if (ir) {
        xMin.value = ir.x_range[0];
        xMax.value = ir.x_range[1];
        yMin.value = ir.y_range[0];
        yMax.value = ir.y_range[1];
      }
    }

    function addTrackPoint() {
      const x = Number(trackX.value);
      const y = Number(trackY.value);
      if (x < 0 || x >= 100 || y < 0 || y >= 100) {
        alert('坐标必须在 0-99 之间');
        return;
      }
      if (trackPoints.value.some(p => p.x === x && p.y === y)) {
        alert('该点已存在');
        return;
      }
      trackPoints.value.push({ x, y });
    }

    function clearTrackPoints() {
      trackPoints.value = [];
    }

    function resetAll() {
      resetAllParams();
      applyBestInit();
      const config = modelConfigs.value[currentModel.value];
      if (config) iterations.value = config.recommended_iterations;
    }

    // ── 任务提交与轮询 ─────────────────────────────
    async function runSimulation() {
      if (isSimulating.value) return;

      currentJobId.value = null;
      jobStatus.value = null;
      jobProgress.value = 0;
      jobResult.value = null;

      const config = modelConfigs.value[currentModel.value];
      if (!config) return;

      const payload = {
        session_id: sessionId.value,
        job_type: 'simulate',
        model: currentModel.value,
        params: params.value,
        iterations: iterations.value,
        init_x_range: [xMin.value, xMax.value],
        init_y_range: [yMin.value, yMax.value],
        track_points: trackPoints.value.map(p => ({ x: p.x, y: p.y })),
      };

      try {
        const res = await fetch('/api/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        currentJobId.value = data.job_id;
        jobStatus.value = 'queued';
        pollJobStatus(data.job_id);
      } catch (e) {
        console.error('提交任务失败:', e);
        jobStatus.value = 'error';
      }
    }

    async function pollJobStatus(jobId) {
      while (true) {
        try {
          const res = await fetch(`/api/jobs/${jobId}`);
          const data = await res.json();
          jobStatus.value = data.status;
          jobProgress.value = data.progress || 0;

          if (data.status === 'completed') {
            jobResult.value = data.result;
            render2D(data.result);
            return;
          }
          if (data.status === 'error' || data.status === 'cancelled') {
            return;
          }
        } catch (e) {
          console.error('轮询失败:', e);
          return;
        }
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    // ── 动画 ─────────────────────────────────────────
    function startAnimation() {
      if (jobResult.value) {
        activeTab.value = 2;
      }
    }

    // ── 渲染 ─────────────────────────────────────────
    function normalize2D(arr) {
      let mn = Infinity, mx = -Infinity;
      arr.forEach(r => r.forEach(v => { if (v < mn) mn = v; if (v > mx) mx = v; }));
      const rng = mx - mn || 1;
      return arr.map(r => r.map(v => (v - mn) / rng));
    }

    function render2D(result) {
      activeTab.value = 0;
      const container = document.getElementById('plot-container');
      container.innerHTML = '<div id="plot-2d" class="w-full h-full"></div>';

      const xData = result.x_data;
      const yData = result.y_data;
      const evo = result.evolution;

      const traces = [];

      // X种群热力图
      traces.push({
        z: xData, type: 'heatmap', colorscale: 'Viridis',
        name: 'X种群',
        xaxis: 'x', yaxis: 'y',
        colorbar: { len: 0.28, y: 0.72, title: { text: '密度', font: { size: 8 } } }
      });

      // Y种群热力图
      traces.push({
        z: yData, type: 'heatmap', colorscale: 'Plasma',
        name: 'Y种群',
        xaxis: 'x2', yaxis: 'y2',
        colorbar: { len: 0.28, y: 0.72, title: { text: '密度', font: { size: 8 } } }
      });

      // 合并斑图
      const xNorm = normalize2D(xData);
      const yNorm = normalize2D(yData);
      const combined = xData.map((row, i) => row.map((_, j) => [
        xNorm[i][j], yNorm[i][j], 0
      ]));
      traces.push({
        z: combined, type: 'heatmap',
        name: '合并斑图',
        xaxis: 'x3', yaxis: 'y3',
        colorbar: { len: 0.28, y: 0.72, title: { text: '', font: { size: 8 } } }
      });

      // 演化曲线
      const time = evo.center.x.map((_, i) => i);
      traces.push({
        x: time, y: evo.center.x, type: 'scatter', mode: 'lines',
        name: '中心点-X', line: { color: '#60A5FA', width: 2 },
        xaxis: 'x4', yaxis: 'y4',
      });
      traces.push({
        x: time, y: evo.center.y, type: 'scatter', mode: 'lines',
        name: '中心点-Y', line: { color: '#F87171', width: 2 },
        xaxis: 'x4', yaxis: 'y4',
      });

      // 自定义跟踪点
      const palette = ['#34D399', '#FBBF24', '#A78BFA', '#22D3EE', '#F472B6', '#FB923C'];
      trackPoints.value.forEach((pt, i) => {
        const key = `point_${pt.x}_${pt.y}`;
        const data = evo[key];
        if (!data) return;
        const c = palette[i % palette.length];
        traces.push({
          x: time, y: data.x, type: 'scatter', mode: 'lines',
          name: `(${pt.x},${pt.y})-X`, line: { color: c, width: 1.5, dash: 'dash' },
          xaxis: 'x4', yaxis: 'y4',
        });
        traces.push({
          x: time, y: data.y, type: 'scatter', mode: 'lines',
          name: `(${pt.x},${pt.y})-Y`,
          line: { color: palette[(i + 1) % palette.length], width: 1.5, dash: 'dash' },
          xaxis: 'x4', yaxis: 'y4',
        });
      });

      const layout = {
        grid: { rows: 2, columns: 3, pattern: 'independent', roworder: 'top to bottom' },
        paper_bgcolor: '#0F172A', plot_bgcolor: '#0F172A',
        font: { color: '#94A3B8', size: 10 },
        margin: { t: 20, r: 10, b: 40, l: 50 },
        // 上排: 3 个热力图
        xaxis: { domain: [0, 0.33], anchor: 'y', showgrid: false, zeroline: false, showticklabels: false },
        yaxis: { domain: [0.4, 1], anchor: 'x', showgrid: false, zeroline: false, showticklabels: false, scaleanchor: 'x', title: { text: 'X种群', font: { size: 10, color: '#94A3B8' } } },
        xaxis2: { domain: [0.34, 0.66], anchor: 'y2', showgrid: false, zeroline: false, showticklabels: false },
        yaxis2: { domain: [0.4, 1], anchor: 'x2', showgrid: false, zeroline: false, showticklabels: false, title: { text: 'Y种群', font: { size: 10, color: '#94A3B8' } } },
        xaxis3: { domain: [0.67, 1], anchor: 'y3', showgrid: false, zeroline: false, showticklabels: false },
        yaxis3: { domain: [0.4, 1], anchor: 'x3', showgrid: false, zeroline: false, showticklabels: false, title: { text: '合并', font: { size: 10, color: '#94A3B8' } } },
        // 下排: 时间演化
        xaxis4: { domain: [0.05, 0.95], title: { text: '迭代次数', font: { size: 10 } }, anchor: 'y4', gridcolor: '#1E293B' },
        yaxis4: { domain: [0, 0.32], title: { text: '种群密度', font: { size: 10 } }, anchor: 'x4', gridcolor: '#1E293B' },
        showlegend: true,
        legend: { x: 1.02, y: 1, font: { size: 9 }, bgcolor: '#1E293B' },
        hovermode: 'closest',
      };

      Plotly.newPlot('plot-2d', traces, layout, { responsive: true, displaylogo: false });
    }

    // ── WebSocket 状态 ──────────────────────────────
    let ws = null;

    function connectStatusWS() {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${location.host}/ws/status`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          uptime.value = data.uptime || '00:00:00';
          cpuPercent.value = data.cpu_percent || 0;
          gpuPercent.value = data.gpu_percent || 0;
          memMb.value = data.memory_mb || 0;
          workersBusy.value = data.workers_busy || 0;
          workersTotal.value = data.workers_total || 0;
          queueLength.value = data.queue_length || 0;
        } catch (e) { /* ignore */ }
      };
      ws.onclose = () => setTimeout(connectStatusWS, 3000);
      ws.onerror = () => ws?.close();
    }

    // ── 生命周期 ────────────────────────────────────
    onMounted(async () => {
      fetchModels();
      connectStatusWS();
      try {
        const vr = await fetch('/api/version');
        const vd = await vr.json();
        appVersion.value = vd.version;
      } catch (e) { /* ignore */ }
    });

    return {
      models, modelConfigs, initRangesAll, paramMeanings,
      currentModel, params, iterations, frames, initDesc,
      xMin, xMax, yMin, yMax,
      trackX, trackY, trackPoints, trackDisplay,
      sessionId,
      currentJobId, jobStatus, jobProgress, jobResult, isSimulating,
      appVersion, uptime, cpuPercent, gpuPercent, memMb,
      workersBusy, workersTotal, queueLength,
      activeTab, tabs,
      currentParams, statusSegments, jobStatusText, initRanges,
      fetchModels, onModelChange,
      resetParam, resetAllParams, resetInit, applyBestInit,
      addTrackPoint, clearTrackPoints, resetAll,
      runSimulation, startAnimation,
    };
  }
}).mount('#app');
