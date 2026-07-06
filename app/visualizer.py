"""
可视化模块
==========
基于 matplotlib 的深色科学主题可视化组件。

功能:
    - 综合图表（2D 斑图 + 合并图 + 时间演化曲线）
    - 三维曲面图
    - 动画帧生成与更新
    - 图例点击交互
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.animation as animation
import matplotlib.ticker as ticker
import matplotlib.colors as mcolors


class PatternVisualizer:
    """斑图可视化器 — 深色科学主题

    提供多维度的数据可视化：
    - create_comprehensive_plot: 2D 热力图 + 时间演化
    - create_3d_pattern: 三维曲面图
    - create_animation_figure / update_animation: 动画

    属性:
        fig: 当前图表引用
        animation: 动画对象
        is_animating: 动画播放状态
        curve_visibility: 曲线可见性映射
    """

    def __init__(self):
        self.fig = None
        self.animation = None
        self.is_animating = False
        self.curve_visibility = {}
        self.curves = {}
        self.legend_map = {}

        # 深色科学主题配色
        self.theme = {
            'bg': '#0F172A',
            'bg_plot': '#1E293B',
            'bg_elevated': '#1E293B',
            'grid': '#334155',
            'text': '#F1F5F9',
            'text_sub': '#94A3B8',
        }

        # 曲线颜色
        self.color_palette = {
            'x_center': '#60A5FA',
            'y_center': '#F87171',
            'x_custom': '#34D399',
            'y_custom': '#FBBF24',
            'x_secondary': '#A78BFA',
            'y_secondary': '#22D3EE',
        }

    # ================================================================
    #  综合图表
    # ================================================================

    def create_comprehensive_plot(self, x_data, y_data, evolution_data,
                                  track_points=None, title="斑图可视化"):
        """创建综合图表：2D 斑图 + 合并图 + 时间演化曲线"""
        fig = Figure(figsize=(16, 16))
        fig.patch.set_facecolor(self.theme['bg'])

        gs = fig.add_gridspec(2, 3, height_ratios=[1, 1.2])

        # ── 第一行：二维斑图 ──
        # X 种群
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.set_facecolor(self.theme['bg_plot'])
        im1 = ax1.imshow(x_data, cmap='viridis', origin='lower')
        self._style_2d_axes(ax1, f'{title} - X种群')
        cbar1 = fig.colorbar(im1, ax=ax1, label='种群密度', shrink=0.8)
        cbar1.ax.yaxis.label.set_color(self.theme['text_sub'])
        cbar1.ax.tick_params(colors=self.theme['text_sub'])

        # Y 种群
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.set_facecolor(self.theme['bg_plot'])
        y_plot = np.copy(y_data)
        y_min, y_max = y_plot.min(), y_plot.max()
        norm = mcolors.PowerNorm(gamma=0.6, vmin=y_min, vmax=max(y_max, y_min + 0.001))
        im2 = ax2.imshow(y_plot, cmap=plt.cm.plasma, norm=norm, origin='lower')
        self._style_2d_axes(ax2, f'{title} - Y种群')
        cbar2 = fig.colorbar(im2, ax=ax2, label='种群密度', shrink=0.8)
        cbar2.ax.yaxis.label.set_color(self.theme['text_sub'])
        cbar2.ax.tick_params(colors=self.theme['text_sub'])

        # 合并图
        ax3 = fig.add_subplot(gs[0, 2])
        ax3.set_facecolor(self.theme['bg_plot'])
        x_norm = (x_data - x_data.min()) / (x_data.max() - x_data.min() + 1e-10)
        y_norm = (y_plot - y_plot.min()) / (y_plot.max() - y_plot.min() + 1e-10)
        combined = np.zeros((x_data.shape[0], x_data.shape[1], 3))
        combined[:, :, 0] = x_norm
        combined[:, :, 1] = y_norm
        im3 = ax3.imshow(combined, origin='lower')
        self._style_2d_axes(ax3, f'{title} - 合并斑图')
        cbar3 = fig.colorbar(im3, ax=ax3, label='种群密度', shrink=0.8)
        cbar3.ax.yaxis.label.set_color(self.theme['text_sub'])
        cbar3.ax.tick_params(colors=self.theme['text_sub'])

        # 标记跟踪点
        if track_points:
            for pt in track_points:
                ax3.plot(pt['y'], pt['x'], 'wo', markersize=8,
                         markeredgecolor='black', markeredgewidth=1)
                ax3.text(pt['y'] + 2, pt['x'] + 2,
                         f"({pt['x']},{pt['y']})", color='white',
                         fontsize=8, fontweight='bold',
                         bbox=dict(boxstyle='round,pad=0.3',
                                   facecolor='black', alpha=0.7))

        # ── 第二行：时间演化 ──
        ax4 = fig.add_subplot(gs[1, :])
        time = np.arange(len(evolution_data['center']['x']))

        self.curve_visibility = {'center_x': True, 'center_y': True}
        self.curves = {}

        # 中心点
        self.curves['center_x'], = ax4.plot(
            time, evolution_data['center']['x'], '-',
            label='中心点-X种群', linewidth=2,
            color=self.color_palette['x_center'], alpha=0.8)
        self.curves['center_y'], = ax4.plot(
            time, evolution_data['center']['y'], '-',
            label='中心点-Y种群', linewidth=2,
            color=self.color_palette['y_center'], alpha=0.8)

        # 自定义点
        custom_lines = []
        if track_points:
            palette = ['#34D399', '#FBBF24', '#A78BFA', '#22D3EE', '#F472B6', '#FB923C']
            for i, pt in enumerate(track_points):
                key = f"point_{pt['x']}_{pt['y']}"
                if key not in evolution_data:
                    continue
                kx, ky = f"point_{i}_x", f"point_{i}_y"
                cx, cy = palette[i % len(palette)], palette[(i + 1) % len(palette)]

                self.curves[kx], = ax4.plot(
                    time, evolution_data[key]['x'], '--',
                    label=f"点({pt['x']},{pt['y']})-X",
                    linewidth=1.5, color=cx, alpha=0.7)
                self.curves[ky], = ax4.plot(
                    time, evolution_data[key]['y'], '--',
                    label=f"点({pt['x']},{pt['y']})-Y",
                    linewidth=1.5, color=cy, alpha=0.7)
                self.curve_visibility[kx] = True
                self.curve_visibility[ky] = True
                custom_lines.extend([self.curves[kx], self.curves[ky]])

        ax4.set_title('多点时间演化曲线', fontsize=12, fontweight='bold',
                      color=self.theme['text'], pad=15)
        ax4.set_xlabel('迭代次数', fontsize=10, color=self.theme['text_sub'])
        ax4.set_ylabel('种群密度', fontsize=10, color=self.theme['text_sub'])
        ax4.tick_params(axis='both', which='major', labelsize=9, colors=self.theme['text_sub'])
        ax4.xaxis.set_major_formatter(ticker.ScalarFormatter(useOffset=False))
        ax4.yaxis.set_major_formatter(ticker.ScalarFormatter(useOffset=False))
        ax4.grid(True, alpha=0.15, linestyle='--', linewidth=0.5, color=self.theme['grid'])
        ax4.set_facecolor(self.theme['bg_plot'])

        # 可点击图例
        ncol = 2 if track_points and len(track_points) > 1 else 1
        legend = ax4.legend(loc='upper right', fontsize=8, frameon=True,
                            fancybox=True, shadow=True,
                            facecolor=self.theme['bg_elevated'],
                            labelcolor=self.theme['text_sub'], ncol=ncol)

        self.legend_map = {}
        all_line_artists = [self.curves['center_x'], self.curves['center_y']] + custom_lines
        for leg_line, orig_line in zip(legend.get_lines(), all_line_artists):
            self.legend_map[leg_line] = orig_line
            leg_line.set_picker(True)
            leg_line.set_pickradius(10)

        fig.canvas.mpl_connect('pick_event', self._on_legend_pick)
        fig.tight_layout(pad=3.0)
        self.fig = fig
        self.ax4 = ax4
        return fig

    def _style_2d_axes(self, ax, title):
        """统一设置二维子图样式"""
        ax.set_title(title, fontsize=11, fontweight='bold', color=self.theme['text'])
        ax.set_xlabel('X轴', fontsize=9, color=self.theme['text_sub'])
        ax.set_ylabel('Y轴', fontsize=9, color=self.theme['text_sub'])
        ax.tick_params(axis='both', which='major', labelsize=8, colors=self.theme['text_sub'])
        ax.grid(True, alpha=0.15, linestyle='--', linewidth=0.5, color=self.theme['grid'])
        ax.xaxis.set_major_formatter(ticker.ScalarFormatter(useOffset=False))
        ax.yaxis.set_major_formatter(ticker.ScalarFormatter(useOffset=False))

    # ================================================================
    #  图例交互
    # ================================================================

    def _on_legend_pick(self, event):
        """点击图例切换曲线可见性"""
        leg_line = event.artist
        if leg_line not in self.legend_map:
            return
        orig = self.legend_map[leg_line]
        visible = not orig.get_visible()
        orig.set_visible(visible)
        leg_line.set_alpha(1.0 if visible else 0.2)

        for key, curve in self.curves.items():
            if curve == orig:
                self.curve_visibility[key] = visible
                break
        self.fig.canvas.draw()

    # ================================================================
    #  三维斑图
    # ================================================================

    def create_3d_pattern(self, data, title="三维斑图"):
        """创建三维曲面图"""
        fig = Figure(figsize=(10, 8))
        fig.patch.set_facecolor(self.theme['bg'])
        ax = fig.add_subplot(111, projection='3d')
        ax.set_facecolor(self.theme['bg'])

        X, Y = np.meshgrid(np.arange(data.shape[0]), np.arange(data.shape[1]))
        d_min, d_max = data.min(), data.max()
        norm = mcolors.PowerNorm(gamma=0.7, vmin=d_min, vmax=max(d_max, d_min + 0.001))

        surf = ax.plot_surface(X, Y, np.copy(data), cmap=plt.cm.viridis, norm=norm,
                               linewidth=0, antialiased=True, alpha=0.85)

        ax.set_title(f'{title} - X种群', fontsize=12, fontweight='bold',
                     color=self.theme['text'], pad=15)
        for label, method in [('set_xlabel', 'X轴'), ('set_ylabel', 'Y轴'),
                               ('set_zlabel', '种群密度')]:
            getattr(ax, label)(method, fontsize=10, color=self.theme['text_sub'])

        for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
            axis.set_major_formatter(ticker.ScalarFormatter(useOffset=False))
        ax.tick_params(axis='both', which='major', labelsize=8, colors=self.theme['text_sub'])
        ax.view_init(elev=25, azim=45)

        cbar = fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, label='种群密度')
        cbar.ax.yaxis.label.set_color(self.theme['text_sub'])
        cbar.ax.tick_params(colors=self.theme['text_sub'])

        for pane in [ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane]:
            pane.fill = False
            pane.set_edgecolor(self.theme['grid'])
        ax.grid(True, alpha=0.15, color=self.theme['grid'])

        fig.tight_layout()
        return fig

    # ================================================================
    #  动画
    # ================================================================

    def create_animation_figure(self):
        """创建动画图表框架（三列并排）"""
        fig = Figure(figsize=(14, 6))
        fig.patch.set_facecolor(self.theme['bg'])
        self.ax1 = fig.add_subplot(131)
        self.ax2 = fig.add_subplot(132)
        self.ax3 = fig.add_subplot(133)
        fig.tight_layout(pad=3.0)
        return fig

    def update_animation(self, frame, x_history, y_history):
        """更新动画帧"""
        for ax in [self.ax1, self.ax2, self.ax3]:
            ax.clear()
            self._style_2d_axes(ax, '')
            ax.set_facecolor(self.theme['bg_plot'])

        # X 种群
        im1 = self.ax1.imshow(x_history[frame], cmap='viridis', origin='lower')
        self.ax1.set_title(f'X种群 - 迭代 {frame}', fontsize=11, fontweight='bold',
                           color=self.theme['text'])

        # Y 种群
        y_frame = y_history[frame]
        y_min, y_max = y_frame.min(), y_frame.max()
        norm = mcolors.PowerNorm(gamma=0.6, vmin=y_min, vmax=max(y_max, y_min + 0.001))
        im2 = self.ax2.imshow(y_frame, cmap=plt.cm.plasma, norm=norm, origin='lower')
        self.ax2.set_title(f'Y种群 - 迭代 {frame}', fontsize=11, fontweight='bold',
                           color=self.theme['text'])

        # 时间演化
        t = np.arange(frame + 1)
        cx, cy = x_history.shape[1] // 2, x_history.shape[2] // 2
        self.ax3.plot(t, x_history[:frame + 1, cx, cy], '-',
                      label='X种群', linewidth=2, color=self.color_palette['x_center'])
        self.ax3.plot(t, y_history[:frame + 1, cx, cy], '-',
                      label='Y种群', linewidth=2, color=self.color_palette['y_center'])
        self.ax3.set_title('中心点时间演化', fontsize=11, fontweight='bold',
                           color=self.theme['text'])
        self.ax3.legend(loc='upper right', fontsize=8, frameon=True, fancybox=True,
                        facecolor=self.theme['bg_plot'], labelcolor=self.theme['text_sub'])

        if frame > 0:
            xv = x_history[:frame + 1, cx, cy]
            yv = y_history[:frame + 1, cx, cy]
            lo = min(np.percentile(xv, 5), np.percentile(yv, 5)) * 0.9
            hi = max(np.percentile(xv, 95), np.percentile(yv, 95)) * 1.1
            self.ax3.set_ylim(lo, hi)

        return [im1, im2]
