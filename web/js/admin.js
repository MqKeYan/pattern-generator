const { createApp, ref, reactive, onMounted, onUnmounted, nextTick } = Vue;

createApp({
  setup() {
    const activePage = ref(0);
    const pages = [
      { name: 'Worker池配置', icon: '⚙' },
      { name: '系统监控', icon: '📊' },
    ];
    const lastUpdate = ref('');

    // Worker 池配置
    const formWorkerCount = ref(2);
    const formUseGpu = ref(true);
    const formMaxIter = ref(20000);
    const currentConfig = ref({ worker_count: 1, use_gpu: true, max_iterations: 20000 });
    const saveMessage = ref('');
    const saveMessageType = ref('ok');

    // 系统监控实时数据
    const liveData = reactive({
      cpu_percent: 0, cpu_per_core: [],
      gpu_percent: 0, gpu_memory_mb: 0, gpu_memory_total_mb: 8192,
      system_memory_mb: 0, system_memory_total_mb: 16384,
      workers: [], queue_length: 0, timestamp: '',
    });

    // 历史数据
    const historyData = reactive({ timestamps: [], cpu: [], gpu: [], memory_mb: [] });

    // Chart.js 实例
    let chartCPU = null, chartGPU = null, chartMem = null;

    // ── Worker 池配置 ──────────────────────────────
    async function fetchPoolConfig() {
      try {
        const res = await fetch('/api/pool/config');
        const data = await res.json();
        currentConfig.value = data;
        formWorkerCount.value = data.worker_count;
        formUseGpu.value = data.use_gpu;
        formMaxIter.value = data.max_iterations;
      } catch (e) { console.error('获取配置失败:', e); }
    }

    async function savePoolConfig() {
      saveMessage.value = '';
      try {
        const res = await fetch('/api/pool/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            worker_count: formWorkerCount.value,
            use_gpu: formUseGpu.value,
            max_iterations: formMaxIter.value,
          }),
        });
        const data = await res.json();
        currentConfig.value = data.config;
        saveMessage.value = '配置已保存，如需生效请重启 Worker 池。';
        saveMessageType.value = 'ok';
      } catch (e) {
        saveMessage.value = '保存失败: ' + e.message;
        saveMessageType.value = 'error';
      }
    }

    async function restartPool() {
      if (!confirm('确定要重启 Worker 池吗？运行中的任务将中断。')) return;
      try {
        await fetch('/api/pool/restart', { method: 'POST' });
        saveMessage.value = 'Worker 池已重启。';
        saveMessageType.value = 'ok';
        await fetchPoolConfig();
      } catch (e) {
        saveMessage.value = '重启失败: ' + e.message;
        saveMessageType.value = 'error';
      }
    }

    // ── WebSocket 监控 ─────────────────────────────
    let ws = null;

    function connectAdminWS() {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${location.host}/ws/system`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          Object.assign(liveData, data);
          lastUpdate.value = '更新: ' + (data.timestamp || '');

          // 更新历史数据（保留最近 200 个点）
          historyData.timestamps.push(data.timestamp || '');
          historyData.cpu.push(data.cpu_percent ?? 0);
          historyData.gpu.push(data.gpu_percent ?? 0);
          historyData.memory_mb.push(data.system_memory_mb ?? 0);
          if (historyData.timestamps.length > 200) {
            historyData.timestamps.shift();
            historyData.cpu.shift();
            historyData.gpu.shift();
            historyData.memory_mb.shift();
          }

          updateCharts();
        } catch (e) { /* ignore */ }
      };
      ws.onclose = () => {
        lastUpdate.value = '连接断开，3秒后重连...';
        setTimeout(connectAdminWS, 3000);
      };
      ws.onerror = () => ws?.close();
    }

    // ── 图表 ────────────────────────────────────────
    function createChart(canvasId, label, color) {
      const ctx = document.getElementById(canvasId)?.getContext('2d');
      if (!ctx) return null;
      return new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label, data: [],
            borderColor: color,
            backgroundColor: color + '20',
            borderWidth: 2, fill: true, tension: 0.3,
            pointRadius: 0,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: { duration: 300 },
          scales: {
            x: { display: false },
            y: {
              beginAtZero: true,
              grid: { color: '#1E293B' },
              ticks: { color: '#64748B', font: { size: 10 } },
            },
          },
          plugins: {
            legend: { labels: { color: '#94A3B8', font: { size: 10 } } },
          },
        },
      });
    }

    function updateCharts() {
      const len = historyData.timestamps.length;
      if (len < 2) return;

      const labels = historyData.timestamps.slice(-60);
      const cpuData = historyData.cpu.slice(-60);
      const gpuData = historyData.gpu.slice(-60);
      const memData = historyData.memory_mb.slice(-60);

      [chartCPU, chartGPU, chartMem].forEach((ch, i) => {
        if (!ch) return;
        const data = [cpuData, gpuData, memData][i];
        ch.data.labels = labels;
        ch.data.datasets[0].data = data;
        ch.update('none');
      });
    }

    // ── 生命周期 ────────────────────────────────────
    onMounted(async () => {
      await fetchPoolConfig();

      await nextTick();
      chartCPU = createChart('chart-cpu', 'CPU %', '#3B82F6');
      chartGPU = createChart('chart-gpu', 'GPU %', '#60A5FA');
      chartMem = createChart('chart-memory', '内存 MB', '#F59E0B');

      // 内存图 Y 轴不设上限
      if (chartMem) {
        chartMem.options.scales.y.max = undefined;
        chartMem.options.scales.y.beginAtZero = false;
      }

      connectAdminWS();
    });

    onUnmounted(() => {
      ws?.close();
      [chartCPU, chartGPU, chartMem].forEach(c => c?.destroy());
    });

    return {
      activePage, pages, lastUpdate,
      formWorkerCount, formUseGpu, formMaxIter,
      currentConfig, saveMessage, saveMessageType,
      liveData,
      fetchPoolConfig, savePoolConfig, restartPool,
    };
  }
}).mount('#admin-app');
