/**
 * i18n 翻译模块 - 根据操作系统语言自动适配界面文字
 * 支持：简体中文(默认)、繁体中文、英文（非中文系统一律显示英文）
 */
const i18n = (() => {
    // 翻译字典
    const translations = {
        'zh-CN': {
            app_title: '斑图形成可视化系统',
            loading: '加载中...',
            model_select: '模型选择',
            params_setting: '参数设置',
            reset_params: '重置参数',
            init_range: '初始值范围',
            x_min: 'X 最小值',
            x_max: 'X 最大值',
            y_min: 'Y 最小值',
            y_max: 'Y 最大值',
            apply_best_init: '应用最佳初始值',
            track_points: '时间演化跟踪点',
            coord_x: 'X坐标',
            coord_y: 'Y坐标',
            add: '添加',
            clear: '清空',
            iterations: '迭代次数',
            reset_iters: '重置推荐值',
            anim_setting: '动画设置',
            anim_start: '起始迭代',
            anim_end: '结束迭代',
            anim_frames: '帧数',
            control_panel: '控制面板',
            run_sim: '运行模拟',
            run_anim: '开始动画',
            reset_all: '重置所有',
            clean_cache: '清理缓存',
            status_ready: '就绪，请选择参数运行模拟',
            tab_2d: '二维斑图',
            tab_3d: '三维斑图',
            tab_anim: '动画演示',
            play: '播放',
            pause: '暂停',
            speed: '速度',
            computing: '计算中...',
            point_range_error: '坐标必须在0~99之间',
            point_exists: '点({x},{y})已存在',
            simulating: '模拟计算中，请稍候...',
            simulating_status: '模拟进行中...',
            sim_complete: '模拟完成 — {model}，迭代{iters}次',
            sim_done: '模拟完成！',
            sim_failed: '模拟失败: {msg}',
            init_failed: '初始化失败',
            restored_sim: '已恢复上次模拟结果',
            restored_toast: '已恢复上次结果，刷新无忧',
            reset_done: '所有设置已重置',
            clean_failed: '清理失败: {msg}',
            need_anim: '请先运行动画计算',
            anim_ready: '动画数据准备完成',
            anim_ready_status: '动画数据就绪，点击播放',
            anim_failed: '动画准备失败: {msg}',
            anim_failed_status: '动画准备失败',
            anim_preparing: '准备动画数据...',
            track_list_center: '当前跟踪点: 中心点(50,50)',
            track_list_custom: '当前跟踪点: 中心点(50,50), {pts}',
            frame_count: '帧: {current} / {total}',
            x_population: 'X种群',
            y_population: 'Y种群',
            combined_pattern: '合并斑图',
            iterations_axis: '迭代次数',
            density_axis: '种群密度',
            axis_x: 'X轴',
            axis_y: 'Y轴',
            center_evo_title: '中心点时间演化',
            center_x: 'X种群-中心点',
            center_y: 'Y种群-中心点',
            density: '密度',
            anim_title_x: 'X种群 - 迭代 {iter}',
            anim_title_y: 'Y种群 - 迭代 {iter}',
            anim_title_combined: '合并斑图 - 迭代 {iter}',
            model_1: '模型1·R-M型',
            model_2: '模型2·Holling II型',
            model_3: '模型3·比值依赖型',
            model_4: '模型4·对称竞争',
            model_5: '模型5·连续化离散型',
        },
        'zh-TW': {
            app_title: '斑圖形成可視化系統',
            loading: '載入中...',
            model_select: '模型選擇',
            params_setting: '參數設置',
            reset_params: '重置參數',
            init_range: '初始值範圍',
            x_min: 'X 最小值',
            x_max: 'X 最大值',
            y_min: 'Y 最小值',
            y_max: 'Y 最大值',
            apply_best_init: '套用最佳初始值',
            track_points: '時間演化追蹤點',
            coord_x: 'X座標',
            coord_y: 'Y座標',
            add: '新增',
            clear: '清空',
            iterations: '疊代次數',
            reset_iters: '重置建議值',
            anim_setting: '動畫設置',
            anim_start: '起始疊代',
            anim_end: '結束疊代',
            anim_frames: '幀數',
            control_panel: '控制面板',
            run_sim: '執行模擬',
            run_anim: '開始動畫',
            reset_all: '全部重置',
            clean_cache: '清理快取',
            status_ready: '就緒，請選擇參數執行模擬',
            tab_2d: '二維斑圖',
            tab_3d: '三維斑圖',
            tab_anim: '動畫演示',
            play: '播放',
            pause: '暫停',
            speed: '速度',
            computing: '計算中...',
            point_range_error: '座標必須在0~99之間',
            point_exists: '點({x},{y})已存在',
            simulating: '模擬計算中，請稍候...',
            simulating_status: '模擬進行中...',
            sim_complete: '模擬完成 — {model}，疊代{iters}次',
            sim_done: '模擬完成！',
            sim_failed: '模擬失敗: {msg}',
            init_failed: '初始化失敗',
            restored_sim: '已恢復上次模擬結果',
            restored_toast: '已恢復上次結果，重新整理無憂',
            reset_done: '所有設置已重置',
            clean_failed: '清理失敗: {msg}',
            need_anim: '請先執行動畫計算',
            anim_ready: '動畫資料準備完成',
            anim_ready_status: '動畫資料就緒，點擊播放',
            anim_failed: '動畫準備失敗: {msg}',
            anim_failed_status: '動畫準備失敗',
            anim_preparing: '準備動畫資料...',
            track_list_center: '目前追蹤點: 中心點(50,50)',
            track_list_custom: '目前追蹤點: 中心點(50,50), {pts}',
            frame_count: '幀: {current} / {total}',
            x_population: 'X種群',
            y_population: 'Y種群',
            combined_pattern: '合併斑圖',
            iterations_axis: '疊代次數',
            density_axis: '種群密度',
            axis_x: 'X軸',
            axis_y: 'Y軸',
            center_evo_title: '中心點時間演化',
            center_x: 'X種群-中心點',
            center_y: 'Y種群-中心點',
            density: '密度',
            anim_title_x: 'X種群 - 疊代 {iter}',
            anim_title_y: 'Y種群 - 疊代 {iter}',
            anim_title_combined: '合併斑圖 - 疊代 {iter}',
            model_1: '模型1·R-M型',
            model_2: '模型2·Holling II型',
            model_3: '模型3·比值依賴型',
            model_4: '模型4·對稱競爭',
            model_5: '模型5·連續化離散型',
        },
        'en': {
            app_title: 'Pattern Formation Visualization System',
            loading: 'Loading...',
            model_select: 'Model Selection',
            params_setting: 'Parameter Settings',
            reset_params: 'Reset Parameters',
            init_range: 'Initial Value Range',
            x_min: 'X Min',
            x_max: 'X Max',
            y_min: 'Y Min',
            y_max: 'Y Max',
            apply_best_init: 'Apply Best Initial Values',
            track_points: 'Evolution Tracking Points',
            coord_x: 'X Coordinate',
            coord_y: 'Y Coordinate',
            add: 'Add',
            clear: 'Clear',
            iterations: 'Iterations',
            reset_iters: 'Reset Recommended',
            anim_setting: 'Animation Settings',
            anim_start: 'Start Iteration',
            anim_end: 'End Iteration',
            anim_frames: 'Frames',
            control_panel: 'Control Panel',
            run_sim: 'Run Simulation',
            run_anim: 'Start Animation',
            reset_all: 'Reset All',
            clean_cache: 'Clear Cache',
            status_ready: 'Ready, select parameters to run',
            tab_2d: '2D Pattern',
            tab_3d: '3D Pattern',
            tab_anim: 'Animation',
            play: 'Play',
            pause: 'Pause',
            speed: 'Speed',
            computing: 'Computing...',
            point_range_error: 'Coordinates must be between 0 and 99',
            point_exists: 'Point ({x},{y}) already exists',
            simulating: 'Simulating, please wait...',
            simulating_status: 'Simulation in progress...',
            sim_complete: 'Simulation complete — {model}, {iters} iterations',
            sim_done: 'Simulation complete!',
            sim_failed: 'Simulation failed: {msg}',
            init_failed: 'Initialization failed',
            restored_sim: 'Previous simulation result restored',
            restored_toast: 'Previous result restored',
            reset_done: 'All settings have been reset',
            clean_failed: 'Cleanup failed: {msg}',
            need_anim: 'Please run animation first',
            anim_ready: 'Animation data ready',
            anim_ready_status: 'Animation ready, click play',
            anim_failed: 'Animation preparation failed: {msg}',
            anim_failed_status: 'Animation preparation failed',
            anim_preparing: 'Preparing animation data...',
            track_list_center: 'Tracking: center (50,50)',
            track_list_custom: 'Tracking: center (50,50), {pts}',
            frame_count: 'Frame: {current} / {total}',
            x_population: 'X Population',
            y_population: 'Y Population',
            combined_pattern: 'Combined Pattern',
            iterations_axis: 'Iterations',
            density_axis: 'Population Density',
            axis_x: 'X Axis',
            axis_y: 'Y Axis',
            center_evo_title: 'Center Point Evolution',
            center_x: 'X Population - Center',
            center_y: 'Y Population - Center',
            density: 'Density',
            anim_title_x: 'X Population - Iteration {iter}',
            anim_title_y: 'Y Population - Iteration {iter}',
            anim_title_combined: 'Combined Pattern - Iteration {iter}',
            model_1: 'Model 1·R-M',
            model_2: 'Model 2·Holling II',
            model_3: 'Model 3·Ratio-Dependent',
            model_4: 'Model 4·Symmetric Competition',
            model_5: 'Model 5·Continuous-Discrete',
        },
    };

    // 当前语言（zh-CN / zh-TW / en）
    const lang = detectLang();

    /**
     * 检测系统语言
     * @returns {string} 语言代码
     */
    function detectLang() {
        const nav = (navigator.language || 'zh-CN').toLowerCase();
        if (nav.startsWith('zh')) {
            // 繁体中文系统（台湾/香港/澳门）用繁体
            if (nav.startsWith('zh-tw') || nav.startsWith('zh-hk') || nav.startsWith('zh-mo')) return 'zh-TW';
            return 'zh-CN';
        }
        return 'en';  // 非中文系统一律显示英文
    }

    /**
     * 翻译函数，支持 {变量} 占位符
     * @param {string} key - 字典键
     * @param {Object} params - 替换参数
     * @returns {string} 翻译后的文本
     */
    function t(key, params) {
        let text = translations[lang][key] || translations['zh-CN'][key] || key;
        if (params) {
            for (const k in params) {
                text = text.replaceAll(`{${k}}`, params[k]);
            }
        }
        return text;
    }

    /**
     * 应用到页面：替换data-i18n元素的文本，设置html lang和标题
     */
    function applyTranslations() {
        document.documentElement.lang = lang;
        document.querySelectorAll('[data-i18n]').forEach(el => {
            el.textContent = t(el.dataset.i18n);
        });
        document.title = t('app_title');
    }

    return { t, applyTranslations, lang };
})();

// DOM加载完成后立即应用翻译（在app.js的init之前执行）
document.addEventListener('DOMContentLoaded', () => i18n.applyTranslations());
