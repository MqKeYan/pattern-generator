const { createApp, ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } = Vue;

createApp({
  setup() {
    // ── 导航 ─────────────────────────────────────────
    const activeMain = ref('pool');       // pool | monitor
    const activeSub = ref('overview');    // overview | worker-N
    function selectPage(key) {
      if (key === 'pool') {
        activeMain.value = 'pool';
        activeSub.value = '';
        return;
      }
      activeMain.value = 'monitor';
      activeSub.value = key;
    }

    function selectWorker(wid) {
      activeMain.value = 'monitor';
      activeSub.value = 'worker-' + wid;
    }

    const lastUpdate = ref('');

    // ── Worker 池配置 ────────────────────────────────
    const formWorkerCount = ref(2);
    const formUseGpu = ref(true);
    const formMaxIter = ref(20000);
    const currentConfig = ref({ worker_count: 1, use_gpu: true, max_iterations: 20000 });
    const saveMessage = ref('');
    const saveMessageType = ref('ok');

    // 硬件信息
    const hardware = ref({
      rec_min: 1, rec_max: 4, has_gpu: false,
      gpu_count: 0, gpu_name: '', vram_total_gb: 0, cpu_physical: 1,
    });

    // ── 实时数据 ──────────────────────────────────────
    const liveData = reactive({
      cpu_percent: 0, cpu_temp: null,
      gpu_percent: 0, gpu_temp: null,
      gpu_memory_mb: 0, gpu_memory_total_mb: 8192,
      system_memory_mb: 0, system_memory_total_mb: 16384, system_memory_avail_mb: 0,
      disk_used_mb: 0, disk_total_gb: 0, disk_free_gb: 0,
      jobs_total: 0, jobs_completed: 0, jobs_queued: 0, jobs_failed: 0,
      workers: [], queue_length: 0, timestamp: '',
    });

    // ── 历史数据 ──────────────────────────────────────
    const historyData = reactive({
      timestamps: [], cpu: [], gpu: [],
      memory_mb: [], disk_used_mb: [],
    });

    // ── 计算属性 ────────────────────────────────────
    const hardwareInfo = computed(() => {
      const h = hardware.value;
      if (h.has_gpu) {
        return `推荐 ${h.rec_min}-${h.rec_max} Worker（${h.gpu_count} GPU · ${h.vram_total_gb}GB 显存 · ${h.cpu_physical} 核 CPU）`;
      }
      return `推荐 ${h.rec_min}-${h.rec_max} Worker（${h.cpu_physical} 核 CPU）`;
    });

    const workerWarning = computed(() => {
      if (formWorkerCount.value > hardware.value.rec_max) {
        return `已超出推荐最大值 ${hardware.value.rec_max}，可能导致显存/内存不足`;
      }
      return '';
    });

    // ── Chart.js 实例 ────────────────────────────────
    let chartCPU = null, chartGPU = null, chartMem = null, chartDisk = null;
    let chartsReady = false;

    async function initCharts() {
      if (chartsReady) {
        [chartCPU, chartGPU, chartMem, chartDisk].forEach(c => c?.resize());
        return;
      }
      await nextTick();
      chartCPU = createChart('chart-cpu', 'CPU占用', '#3B82F6', { max: undefined });
      chartGPU = createChart('chart-gpu', 'GPU占用', '#60A5FA', { max: undefined });
      chartMem = createChart('chart-memory', '内存', '#F59E0B', { max: undefined, _memFmt: true });
      chartDisk = createChart('chart-disk', '磁盘', '#94A3B8', { max: undefined, _memFmt: true });
      chartsReady = true;
    }

    // ── Worker 池 API ────────────────────────────────
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

    // ── WebSocket ─────────────────────────────────────
    let ws = null;

    function connectAdminWS() {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${location.host}/ws/system`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          Object.assign(liveData, data);
          lastUpdate.value = data.timestamp || '';

          historyData.timestamps.push(data.timestamp || '');
          historyData.cpu.push(data.cpu_percent ?? 0);
          historyData.gpu.push(data.gpu_percent ?? 0);
          historyData.memory_mb.push(data.system_memory_mb ?? 0);
          historyData.disk_used_mb.push(data.disk_used_mb ?? 0);
          if (historyData.timestamps.length > 200) {
            ['timestamps','cpu','gpu','memory_mb','disk_used_mb']
              .forEach(k => historyData[k].shift());
          }

          updateCharts();
        } catch (e) { /* ignore */ }
      };
      ws.onclose = () => {
        lastUpdate.value = '--:--:--';
        setTimeout(connectAdminWS, 3000);
      };
      ws.onerror = () => ws?.close();
    }

    // ── 图表 ──────────────────────────────────────────
    function createChart(canvasId, label, color, yConfig = {}) {
      const ctx = document.getElementById(canvasId)?.getContext('2d');
      if (!ctx) return null;
      return new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label, data: [],
            borderColor: color,
            borderWidth: 2, fill: false, tension: 0.3,
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
              max: 100,
              ...yConfig,
              grid: { color: '#1E293B' },
              ticks: {
                color: '#64748B', font: { size: 11 },
                callback: yConfig._memFmt ? (v) => v >= 1024 ? (v/1024).toFixed(1)+'G' : v.toFixed(0)+'M' : undefined,
              },
            },
          },
          plugins: {
            legend: { labels: { color: '#94A3B8', font: { size: 11 }, boxWidth: 0 } },
          },
        },
      });
    }

    function updateCharts() {
      const len = historyData.timestamps.length;
      if (len < 2) return;

      const labels = historyData.timestamps.slice(-60);
      const charts = [chartCPU, chartGPU, chartMem, chartDisk];
      const allData = [
        historyData.cpu.slice(-60),
        historyData.gpu.slice(-60),
        historyData.memory_mb.slice(-60),
        historyData.disk_used_mb.slice(-60),
      ];
      charts.forEach((ch, i) => {
        if (!ch) return;
        ch.data.labels = labels;
        ch.data.datasets[0].data = allData[i];
        ch.update('none');
      });
    }

    // ── 格式化 ──────────────────────────────────────
    function formatMemory(mb) {
      if (mb == null) return '--';
      if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB';
      return mb.toFixed(0) + ' MB';
    }

    // ── 硬件检测 ──────────────────────────────────────
    async function fetchHardware() {
      try {
        const res = await fetch('/api/system/hardware');
        hardware.value = await res.json();
      } catch (e) { /* ignore */ }
    }

    // ── 生命周期 ──────────────────────────────────────
    onMounted(async () => {
      await fetchPoolConfig();
      await fetchHardware();
      connectAdminWS();
    });

    // 切换到系统监控时初始化图表
    watch(activeSub, (val) => {
      if (val === 'overview') initCharts();
    });

    onUnmounted(() => {
      ws?.close();
      [chartCPU, chartGPU, chartMem, chartDisk]
        .forEach(c => c?.destroy());
    });

    return {
      activeMain, activeSub,
      selectPage, selectWorker,
      lastUpdate,
      formWorkerCount, formUseGpu, formMaxIter,
      currentConfig, saveMessage, saveMessageType,
      hardwareInfo, workerWarning,
      liveData,
      formatMemory,
      fetchPoolConfig, savePoolConfig, restartPool,
    };
  }
}).mount('#admin-app');
