"""Web服务器 - Flask应用，提供RESTful API"""

import os
import sys
import gc
import time
import traceback
import logging
import mimetypes
from threading import Lock

# 注册字体MIME类型，确保浏览器正确加载本地字体
mimetypes.add_type('font/collection', '.ttc')
mimetypes.add_type('font/otf', '.otf')

# 配置日志：输出到stderr（无缓冲），实时显示
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stderr,
)
log = logging.getLogger('server')

# 屏蔽Waitress自带启动日志
logging.getLogger('waitress').setLevel(logging.WARNING)

# 环境变量设置
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from flask import Flask, render_template, jsonify, request
import torch

# 模块导入
from config import MODEL_CONFIGS, GRID_SIZE, MODEL_INIT_RANGES, PARAM_NAMES, MODEL_DISPLAY_NAMES
from version import VERSION
from simulation import PatternSimulator
from visualization import PatternVisualizer

# 获取模板和静态文件路径
if getattr(sys, 'frozen', False):
    # PyInstaller打包后的路径，模板文件在src/templates
    template_folder = os.path.join(sys._MEIPASS, 'src', 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'src', 'static')
else:
    # 开发环境的路径
    base_path = os.path.dirname(__file__)
    template_folder = os.path.join(base_path, 'templates')
    static_folder = os.path.join(base_path, 'static')

# 创建Flask应用，设置模板和静态文件路径
app = Flask(__name__,
            template_folder=template_folder,
            static_folder=static_folder)

# 初始化模拟器和可视化器
use_cuda = torch.cuda.is_available()
simulator = PatternSimulator(grid_size=GRID_SIZE, use_cuda=use_cuda)
visualizer = PatternVisualizer()
log.info(f"使用设备: {'CUDA' if use_cuda else 'CPU'}")
log.info(f"计算硬件: {simulator.hardware_info}")

# 客户端缓存
client_cache = {}

# 计算锁，防止多用户同时使用GPU导致显存冲突
compute_lock = Lock()

@app.route('/')
def index():
    """主页面，配置内联到HTML，刷新首帧即完整渲染侧边栏"""
    init_config = {
        'version': VERSION,
        'models': MODEL_CONFIGS,
        'init_ranges': MODEL_INIT_RANGES,
        'param_names': PARAM_NAMES,
        'display_names': MODEL_DISPLAY_NAMES,
        'grid_size': GRID_SIZE,
        'hardware_info': simulator.hardware_info,
    }
    return render_template('index.html', init_config=init_config)

@app.route('/api/simulate', methods=['POST'])
def run_simulation():
    """执行模拟"""
    try:
        data = request.get_json()
        model_name = data.get('model', '模型1')
        iterations = int(data.get('iterations', 9000))
        params = [float(v) for v in data.get('params', MODEL_CONFIGS[model_name]['defaults'])]

        init_x_range = (
            float(data.get('x_min', MODEL_INIT_RANGES[model_name]['x_range'][0])),
            float(data.get('x_max', MODEL_INIT_RANGES[model_name]['x_range'][1])),
        )
        init_y_range = (
            float(data.get('y_min', MODEL_INIT_RANGES[model_name]['y_range'][0])),
            float(data.get('y_max', MODEL_INIT_RANGES[model_name]['y_range'][1])),
        )

        # 日志：开始模拟
        t0 = time.time()
        log.info(f"→ 开始模拟：{model_name}，迭代{iterations}次，"
              f"X[{init_x_range[0]:.2f}~{init_x_range[1]:.2f}] "
              f"Y[{init_y_range[0]:.2f}~{init_y_range[1]:.2f}]")
        track_points = data.get('track_points', [])

        # 验证模型存在
        if model_name not in MODEL_CONFIGS:
            return jsonify({'error': f'模型 "{model_name}" 不存在'}), 400

        # 加锁执行GPU计算，防止多用户并发冲突
        with compute_lock:
            # 清理之前的模拟状态
            gc.collect()
            if use_cuda:
                torch.cuda.empty_cache()

            # 执行模拟
            x_data, y_data, evolution_data = simulator.simulate(
                model_name, params, iterations, init_x_range, init_y_range, track_points
            )

            # 自动清理缓存
            if data.get('auto_clean', True):
                simulator.clear_memory()

        # 生成可视化数据（CPU操作，无需锁），按语言翻译图表标题
        lang = data.get('lang', 'zh-CN')
        viz_data = visualizer.create_comprehensive_plot(
            x_data, y_data, evolution_data, track_points, model_name, lang=lang
        )
        viz_3d = visualizer.create_3d_pattern(x_data, model_name, lang=lang)

        # 日志：模拟完成
        elapsed = time.time() - t0
        log.info(f"← 模拟完成：{model_name}，耗时 {elapsed:.1f}s")

        # 存入客户端缓存
        client_id = data.get('client_id', '')
        if client_id:
            client_cache[client_id] = {
                'type': 'simulation',
                'viz_2d': viz_data,
                'viz_3d': viz_3d,
                'model': model_name,
                'iterations': iterations,
            }

        return jsonify({
            'success': True,
            'viz_2d': viz_data,
            'viz_3d': viz_3d,
            'model': model_name,
            'iterations': iterations,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/animate', methods=['POST'])
def run_animation():
    """运行动画模拟"""
    try:
        data = request.get_json()
        model_name = data.get('model', '模型1')
        frames = int(data.get('frames', 300))
        start_frame = int(data.get('start_frame', 0))
        params = [float(v) for v in data.get('params', MODEL_CONFIGS[model_name]['defaults'])]

        init_x_range = (
            float(data.get('x_min', MODEL_INIT_RANGES[model_name]['x_range'][0])),
            float(data.get('x_max', MODEL_INIT_RANGES[model_name]['x_range'][1])),
        )
        init_y_range = (
            float(data.get('y_min', MODEL_INIT_RANGES[model_name]['y_range'][0])),
            float(data.get('y_max', MODEL_INIT_RANGES[model_name]['y_range'][1])),
        )

        # 日志：开始动画
        t0 = time.time()
        total_iterations = frames + start_frame
        log.info(f"→ 开始动画：{model_name}，总计{total_iterations}次迭代，存储{frames}帧，"
              f"X[{init_x_range[0]:.2f}~{init_x_range[1]:.2f}] "
              f"Y[{init_y_range[0]:.2f}~{init_y_range[1]:.2f}]")

        # 加锁执行GPU计算，防止多用户并发冲突
        with compute_lock:
            # 执行带历史的模拟，从start_frame开始存储，运行total帧
            total_iterations = frames + start_frame
            x_history, y_history = simulator.simulate_with_history(
                model_name, params, total_iterations, start_from=start_frame,
                init_x_range=init_x_range, init_y_range=init_y_range
            )

            gc.collect()
            if use_cuda:
                torch.cuda.empty_cache()

        # 生成动画数据（CPU操作，无需锁）
        anim_data = visualizer.create_animation_frames(x_history, y_history, start_iteration=start_frame)

        # 日志：动画完成
        elapsed = time.time() - t0
        log.info(f"← 动画完成：{model_name}，耗时 {elapsed:.1f}s")

        # 存入客户端缓存
        client_id = data.get('client_id', '')
        if client_id:
            if client_id not in client_cache:
                client_cache[client_id] = {}
            client_cache[client_id]['anim'] = {
                'type': 'animation',
                'animation': anim_data,
                'model': model_name,
            }

        return jsonify({
            'success': True,
            'animation': anim_data,
            'model': model_name,
            'start_iteration': start_frame,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    """清理缓存"""
    try:
        client_id = request.get_json().get('client_id', '') if request.get_json() else ''
        if client_id and client_id in client_cache:
            del client_cache[client_id]
        success = simulator.clear_memory()
        log.info(f"→ 清理缓存：{'完成' if success else '失败'}")
        return jsonify({
            'success': success,
            'message': '缓存清理完成' if success else '缓存清理失败',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore', methods=['POST'])
def restore():
    """恢复客户端缓存的图表数据"""
    client_id = request.get_json().get('client_id', '')
    if client_id and client_id in client_cache:
        cache_type = client_cache[client_id].get('type', '未知')
        log.info(f"→ 恢复缓存：客户端 {client_id[:8]}...，类型={cache_type}")
        return jsonify({
            'success': True,
            'cached': client_cache[client_id],
        })
    return jsonify({'success': False, 'cached': None})