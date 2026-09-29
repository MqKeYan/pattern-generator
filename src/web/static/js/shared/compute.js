/* Administrator-only global compute engine settings. */
window.ComputeUI = (() => {
    let root, inventory, engineSelect, deviceSelect, status, details, loading = false;

    function option(select, value, label, disabled = false) {
        const item = document.createElement('option');
        item.value = value;
        item.textContent = label;
        item.disabled = disabled;
        select.append(item);
    }

    function selectedEngine() {
        if (!inventory) return null;
        if (engineSelect.value === 'auto') {
            return ['pytorch', 'cupy', 'warp', 'taichi', 'pyopencl', 'numba', 'numpy']
                .map(id => inventory.engines.find(item => item.id === id && item.usable))
                .find(Boolean);
        }
        return inventory.engines.find(item => item.id === engineSelect.value);
    }

    function renderDevices(value) {
        deviceSelect.replaceChildren();
        option(deviceSelect, 'auto', '自动选择');
        for (const device of selectedEngine()?.devices || []) {
            option(deviceSelect, device.id, device.gpu ? 'GPU' : 'CPU');
        }
        if (![...deviceSelect.options].some(item => item.value === value)) {
            option(deviceSelect, value, value + ' · 不可用');
        }
        deviceSelect.value = value;
    }

    function render(engine, device) {
        engineSelect.replaceChildren();
        option(engineSelect, 'auto', '自动选择');
        for (const item of inventory?.engines || []) {
            option(engineSelect, item.id,
                item.name + ' · ' + (item.version || '-') + ' · ' + (item.usable ? '可用' : '不可用'),
                !item.usable && item.id !== engine);
        }
        if (![...engineSelect.options].some(item => item.value === engine)) {
            option(engineSelect, engine, engine + ' · 不可用');
        }
        engineSelect.value = engine;
        renderDevices(device);
        status.textContent = inventory?.error || inventory?.selection_error ||
            ('当前引擎：' + (inventory?.selected
                ? inventory.selected.engine_name + ' · ' + (inventory.selected.gpu ? 'GPU' : 'CPU') : '-'));
        details.replaceChildren();
        for (const item of inventory?.engines || []) {
            const line = document.createElement('div');
            line.textContent = item.name + ': ' + (item.errors.length ? item.errors.join('; ') : '可用');
            details.append(line);
        }
    }

    async function load(refresh = false, defaults = null) {
        if (!root || loading) return;
        loading = true;
        status.textContent = '检测中…';
        const previous = defaults
            ? {engine: defaults.compute_engine, device: defaults.compute_device}
            : {engine: engineSelect.value, device: deviceSelect.value};
        try {
            const response = await fetch('/admin/api/compute-engines' + (refresh ? '/refresh' : ''),
                refresh ? {method: 'POST', headers: {'X-Requested-With': 'XMLHttpRequest'}} : {});
            const body = await response.json();
            if (!response.ok || body.ok === false) throw new Error(body.error || '检测失败');
            inventory = body.data || body;
            render(previous.engine || inventory.default_engine || 'auto',
                previous.device || inventory.default_device || 'auto');
        } catch (error) {
            inventory = null;
            status.textContent = error.message;
        } finally {
            loading = false;
        }
    }

    function init() {
        if (root) return;
        root = document.getElementById('compute-controls');
        if (!root) return;
        const title = document.createElement('h3');
        title.className = 'card-title';
        title.textContent = '计算引擎';
        root.append(title);
        function field(labelText, id, tag) {
            const label = document.createElement('label');
            label.textContent = labelText;
            label.htmlFor = id;
            root.append(label);
            const control = document.createElement(tag);
            control.id = id;
            control.className = 'num-input';
            root.append(control);
            return control;
        }
        engineSelect = field('计算引擎', 'compute-engine', 'select');
        deviceSelect = field('计算设备', 'compute-device', 'select');
        option(engineSelect, 'auto', '自动选择');
        option(deviceSelect, 'auto', '自动选择');
        const path = field('外部 Python 路径', 'compute-python', 'input');
        path.placeholder = 'auto';
        path.autocomplete = 'off';
        const note = document.createElement('p');
        note.textContent = '所有客户端使用这里保存的同一个引擎和设备。保存路径后刷新检测；留空使用系统 Python。更改引擎或设备后重启软件，最大并发计算数量才会重新识别。';
        root.append(note);
        const actions = document.createElement('div');
        actions.className = 'settings-actions';
        const refresh = document.createElement('button');
        refresh.type = 'button';
        refresh.className = 'btn btn-outline btn-refresh';
        refresh.dataset.impact = 'low';
        refresh.textContent = '刷新检测';
        refresh.onclick = () => load(true);
        actions.append(refresh);
        root.append(actions);
        status = document.createElement('p');
        status.setAttribute('role', 'status');
        root.append(status);
        details = document.createElement('div');
        details.className = 'compute-details';
        root.append(details);
        const install = document.createElement('details');
        const heading = document.createElement('summary');
        const body = document.createElement('pre');
        heading.textContent = '依赖安装说明';
        body.textContent = '使用已选解释器的绝对路径，手动安装所需引擎：\n& "…\\python.exe" -m pip install "numpy>=2.4,<2.6"\n其他引擎的版本和安装来源见 requirements.txt 的双语注释清单。\n发行包中的清单位于 _internal\\requirements.txt。\nPyTorch CPU/CUDA 与 CuPy CUDA 12/13 各自只能选择一个变体。\nPyOpenCL 另需系统 OpenCL 驱动；GPU 驱动须按引擎版本核对。\n软件不会自动安装或修改计算引擎依赖。';
        install.append(heading, body);
        root.append(install);
        engineSelect.onchange = () => renderDevices('auto');
    }

    document.addEventListener('DOMContentLoaded', init);
    return {
        async settings(saved) {
            if (!root) init();
            if (!root) return;
            document.getElementById('compute-python').value = saved.compute_python || 'auto';
            render(saved.compute_engine || 'auto', saved.compute_device || 'auto');
            await load(false, saved);
        },
        collect() {
            return {
                compute_engine: engineSelect.value,
                compute_device: deviceSelect.value,
                compute_python: document.getElementById('compute-python').value.trim() || 'auto',
            };
        },
    };
})();
