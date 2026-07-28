"""可视化模块 - 生成前端渲染所需的数据格式"""

import numpy as np
import json

class PatternVisualizer:
    """可视化数据生成器 - 为前端Plotly.js提供图表数据"""

    def __init__(self):
        # 颜色配置
        self.color_palette = {
            'x_center': '#3498DB',
            'y_center': '#E74C3C',
            'x_custom': '#2ECC71',
            'y_custom': '#F39C12',
            'x_secondary': '#9B59B6',
            'y_secondary': '#1ABC9C',
        }

    def _make_json_safe(self, data):
        """将numpy数据转换为JSON安全格式"""
        if isinstance(data, np.ndarray):
            return data.tolist()
        if isinstance(data, (np.integer,)):
            return int(data)
        if isinstance(data, (np.floating,)):
            return float(data)
        if isinstance(data, dict):
            return {k: self._make_json_safe(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._make_json_safe(v) for v in data]
        return data

    def create_comprehensive_plot(self, x_data, y_data, evolution_data, track_points=None, title="斑图可视化"):
        """生成综合图表数据 - 二维斑图 + 时间演化曲线"""
        result = {
            '2d_patterns': self._gen_2d_data(x_data, y_data, title),
            'combined_pattern': self._gen_combined_data(x_data, y_data, track_points, title),
            'evolution_curves': self._gen_evolution_data(evolution_data, track_points),
        }
        return self._make_json_safe(result)

    def _gen_2d_data(self, x_data, y_data, title):
        """生成2D热力图数据"""
        return {
            'x_population': {
                'data': x_data.tolist() if isinstance(x_data, np.ndarray) else x_data,
                'title': f'{title} - X种群',
                'colorscale': 'Viridis',
            },
            'y_population': {
                'data': y_data.tolist() if isinstance(y_data, np.ndarray) else y_data,
                'title': f'{title} - Y种群',
                'colorscale': 'Plasma',
            },
        }

    def _gen_combined_data(self, x_data, y_data, track_points, title):
        """生成合并斑图数据"""
        x_arr = np.array(x_data) if not isinstance(x_data, np.ndarray) else x_data
        y_arr = np.array(y_data) if not isinstance(y_data, np.ndarray) else y_data

        x_norm = (x_arr - x_arr.min()) / (x_arr.max() - x_arr.min() + 1e-10)
        y_norm = (y_arr - y_arr.min()) / (y_arr.max() - y_arr.min() + 1e-10)

        result = {
            'x_normalized': x_norm.tolist(),
            'y_normalized': y_norm.tolist(),
            'title': f'{title} - 合并斑图',
        }

        if track_points:
            result['track_points'] = track_points

        return result

    def _gen_evolution_data(self, evolution_data, track_points=None, start_iteration=0):
        """生成时间演化曲线数据"""
        center_data = evolution_data.get('center', {'x': [], 'y': []})
        # 时间轴从起始迭代开始，对应实际迭代次数
        time = [start_iteration + i for i in range(len(center_data['x']))]

        curves = [
            {
                'name': '中心点-X种群',
                'x': time,
                'y': center_data['x'],
                'color': self.color_palette['x_center'],
                'line_width': 2,
                'dash': 'solid',
                'visible': True,
                'type': 'center',
            },
            {
                'name': '中心点-Y种群',
                'x': time,
                'y': center_data['y'],
                'color': self.color_palette['y_center'],
                'line_width': 2,
                'dash': 'solid',
                'visible': True,
                'type': 'center',
            },
        ]

        # 自定义跟踪点曲线
        if track_points:
            custom_colors = ['#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C', '#34495E', '#7F8C8D']
            for i, point in enumerate(track_points):
                point_key = f"point_{point['x']}_{point['y']}"
                if point_key in evolution_data:
                    color_x = custom_colors[i % len(custom_colors)]
                    color_y = custom_colors[(i + 1) % len(custom_colors)]

                    curves.append({
                        'name': f"点({point['x']},{point['y']})-X",
                        'x': time,
                        'y': evolution_data[point_key]['x'],
                        'color': color_x,
                        'line_width': 1.5,
                        'dash': 'dash',
                        'visible': True,
                        'type': 'custom',
                    })
                    curves.append({
                        'name': f"点({point['x']},{point['y']})-Y",
                        'x': time,
                        'y': evolution_data[point_key]['y'],
                        'color': color_y,
                        'line_width': 1.5,
                        'dash': 'dash',
                        'visible': True,
                        'type': 'custom',
                    })

        return {
            'curves': curves,
            'title': '多点时间演化曲线',
            'x_label': '迭代次数',
            'y_label': '种群密度',
        }

    def create_3d_pattern(self, data, title="三维斑图"):
        """生成3D表面图数据"""
        arr = np.array(data) if not isinstance(data, np.ndarray) else data

        x = np.arange(arr.shape[0])
        y = np.arange(arr.shape[1])

        return self._make_json_safe({
            'x': x.tolist(),
            'y': y.tolist(),
            'z': arr.tolist(),
            'title': f'{title} - X种群 三维表面',
            'colorscale': 'Viridis',
        })

    def create_animation_frames(self, x_history, y_history, start_iteration=0):
        """生成动画帧数据"""
        frames = []
        for i in range(len(x_history)):
            x_frame = np.array(x_history[i]) if not isinstance(x_history[i], np.ndarray) else x_history[i]
            y_frame = np.array(y_history[i]) if not isinstance(y_history[i], np.ndarray) else y_history[i]

            # 中心点值
            center_x = x_frame.shape[0] // 2
            center_y = x_frame.shape[1] // 2

            frames.append({
                'frame': i,
                'x_data': x_frame.tolist(),
                'y_data': y_frame.tolist(),
                'center_x_val': float(x_frame[center_x, center_y]),
                'center_y_val': float(y_frame[center_x, center_y]),
            })

        # 中心点时间序列
        center_series_x = [f['center_x_val'] for f in frames]
        center_series_y = [f['center_y_val'] for f in frames]

        return self._make_json_safe({
            'frames': frames,
            'total_frames': len(frames),
            'center_series': {
                'x': center_series_x,
                'y': center_series_y,
                'time': list(range(len(frames))),  # 动画内部从0开始，前端会调整
            },
        })