"""
主应用窗口模块
==============
斑图生成器的顶层业务编排类。
负责模拟执行、可视化渲染、动画控制和生命周期管理。

通过多重继承组合 UI 组件层 (UIMixin) 实现关注点分离:
    - UIMixin (ui_widgets.py): 界面构建与控件管理
    - PatternVisualizationApp: 模拟/可视化/动画业务逻辑
"""

import os
import tkinter as tk
from tkinter import messagebox
import numpy as np
import gc
import torch
import time
import ctypes
from datetime import datetime
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.animation as animation

from .config import MODEL_CONFIGS, GRID_SIZE
from .simulator import PatternSimulator
from .visualizer import PatternVisualizer
from .theme import DarkScienceTheme
from .environment import setup_chinese_fonts
from .ui_widgets import UIMixin


class PatternVisualizationApp(UIMixin):
    """斑图生成器主应用程序

    组合 UI 组件层 (UIMixin) 和业务逻辑层，管理完整的应用生命周期。

    职责:
        - 应用初始化与主题配置
        - 模拟执行编排
        - 可视化结果渲染
        - 动画控制
        - 内存/缓存管理
    """

    def __init__(self, root):
        self.root = root
        self.root.title("斑图生成器")
        self.root.geometry("1600x1000")
        self.root.minsize(1200, 800)

        # 系统初始化
        self._set_dark_titlebar()
        self.theme_colors = DarkScienceTheme.setup_theme(root)
        self._setup_fonts()

        # 计算引擎
        use_cuda = torch.cuda.is_available()
        self.simulator = PatternSimulator(grid_size=GRID_SIZE, use_cuda=use_cuda)
        print(f"使用设备: {'CUDA' if use_cuda else 'CPU'}")
        self.visualizer = PatternVisualizer()
        print("Visualizer 初始化完成")

        # 状态变量
        self.auto_clean_enabled = tk.BooleanVar(value=True)
        self.clean_count = 0
        self.last_clean_time = None
        self.track_points = []

        self.current_model = "模型1"
        self.current_params = MODEL_CONFIGS["模型1"]["defaults"]
        self.x_data = self.y_data = None
        self.x_history = self.y_history = None
        self.evolution_data = None

        self.iter_var = tk.IntVar(value=MODEL_CONFIGS["模型1"]["recommended_iterations"])
        self.iter_entry = None
        self.anim_frames_var = tk.IntVar(value=300)

        self.is_simulating = False
        self.is_switching_model = False
        self.anim_buttons = {}

        self.start_time = time.time()
        self.start_time_str = datetime.now().strftime("%H:%M:%S")
        self._status_update_id = None

        # 构建界面（来自 UIMixin）
        self.create_widgets()

        # 调试监控
        self._add_debug_monitoring()

        print(f"计算硬件: {self.simulator.hardware_info}")

    # ================================================================
    #  初始化辅助
    # ================================================================

    def _set_dark_titlebar(self):
        """设置 Windows 暗色标题栏 (Win10 20H1+)"""
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

    def _setup_fonts(self):
        """配置 matplotlib 中文字体"""
        font_name = setup_chinese_fonts()
        if font_name:
            print(f"已设置中文字体: {font_name}")

    def _add_debug_monitoring(self):
        """添加模型变量变化监控"""
        def _on_change(*args):
            if not self.is_switching_model and not self.is_simulating:
                print(f"模型变量变化: {self.model_var.get()}, 当前模型: {self.current_model}")
        self.model_var.trace('w', _on_change)
        print("调试监控已启用")

    # ================================================================
    #  缓存管理
    # ================================================================

    def clean_cache(self):
        """手动清理内存和 GPU 缓存"""
        try:
            success = self.simulator.clear_memory()
            if success:
                self.clean_count += 1
                self.last_clean_time = time.strftime("%H:%M:%S")

                if hasattr(self, 'clean_count_label'):
                    self.clean_count_label.config(text=f"清理次数: {self.clean_count}")
                if hasattr(self, 'last_clean_label'):
                    self.last_clean_label.config(text=f"上次清理: {self.last_clean_time}")
                if hasattr(self, 'cleanup_status_label'):
                    self.cleanup_status_label.config(
                        text="缓存清理完成", foreground=self.theme_colors['success'])
                print("缓存清理完成")
            return success
        except Exception as e:
            print(f"清理缓存时出错: {str(e)}")
            if hasattr(self, 'cleanup_status_label'):
                self.cleanup_status_label.config(
                    text=f"清理出错: {str(e)}", foreground=self.theme_colors['danger'])
            return False

    # ================================================================
    #  窗口事件
    # ================================================================

    def on_window_resize(self, event=None):
        """窗口大小改变时刷新当前图表"""
        try:
            current_tab = self.notebook.select()
            canvas_attr = {
                str(self.tab_2d): 'canvas_2d',
                str(self.tab_3d): 'canvas_3d',
                str(self.tab_anim): 'canvas_anim',
            }.get(current_tab)
            if canvas_attr and hasattr(self, canvas_attr):
                getattr(self, canvas_attr).draw()
        except Exception:
            pass

    # ================================================================
    #  模拟执行
    # ================================================================

    def run_simulation(self):
        """执行反应-扩散模拟"""
        if self.is_simulating:
            messagebox.showinfo("提示", "模拟正在进行中，请等待完成")
            return

        try:
            self.is_simulating = True

            params = self.get_parameters()
            init_x_range = (self.x_min_var.get(), self.x_max_var.get())
            init_y_range = (self.y_min_var.get(), self.y_max_var.get())
            iterations = int(self.iter_var.get())

            print(f"开始模拟... 模型: {self.current_model}, 迭代次数: {iterations}")
            print(f"初始值范围: X[{init_x_range[0]:.2f}-{init_x_range[1]:.2f}], "
                  f"Y[{init_y_range[0]:.2f}-{init_y_range[1]:.2f}]")

            self._cleanup_canvases()

            actual_model = self.current_model
            print(f"实际模拟使用的模型: {actual_model}")

            if not hasattr(self, 'simulator') or self.simulator is None:
                self.simulator = PatternSimulator(
                    grid_size=GRID_SIZE, use_cuda=torch.cuda.is_available())

            self.x_data, self.y_data, self.evolution_data = self.simulator.simulate(
                actual_model, params, iterations, init_x_range, init_y_range,
                self.track_points.copy(),
            )

            if self.x_data is None or self.y_data is None:
                messagebox.showwarning("警告", "模拟未生成有效数据")
            else:
                self._render_2d()
                self._render_3d()

            if self.auto_clean_enabled.get():
                self.clean_cache()

            print(f"✓ 模拟完成！模型: {actual_model}, 迭代次数: {iterations}")

        except Exception as e:
            messagebox.showerror("错误", f"模拟失败: {str(e)}")
            print(f"✗ 模拟失败: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_simulating = False

    def _cleanup_canvases(self):
        """清理旧画布和动画状态"""
        # 停止动画
        if hasattr(self, 'visualizer') and self.visualizer.animation:
            try:
                if self.visualizer.animation.event_source:
                    self.visualizer.animation.event_source.stop()
                self.visualizer.animation = None
                self.visualizer.is_animating = False
            except AttributeError:
                pass

        # 销毁旧画布
        for attr in ['canvas_2d', 'canvas_3d', 'canvas_anim']:
            if hasattr(self, attr) and getattr(self, attr):
                try:
                    getattr(self, attr).get_tk_widget().destroy()
                except Exception:
                    pass

        self.x_history = self.y_history = None
        self.update_animation_controls()
        gc.collect()
        print("✓ 已清理内存和缓存")

    # ================================================================
    #  可视化渲染
    # ================================================================

    def _render_2d(self):
        """渲染二维综合图表到标签页"""
        try:
            if self.x_data is None or self.y_data is None or self.evolution_data is None:
                return

            for w in self.tab_2d_canvas_frame.winfo_children():
                w.destroy()

            fig = self.visualizer.create_comprehensive_plot(
                self.x_data, self.y_data, self.evolution_data,
                self.track_points, self.current_model,
            )
            if fig is None:
                return

            self.canvas_2d = FigureCanvasTkAgg(fig, self.tab_2d_canvas_frame)
            self.canvas_2d.draw()
            self.canvas_2d.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            NavigationToolbar2Tk(self.canvas_2d, self.tab_2d_canvas_frame).update()
        except Exception as e:
            print(f"显示综合图表时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    def _render_3d(self):
        """渲染三维曲面图到标签页"""
        try:
            if self.x_data is None:
                return

            for w in self.tab_3d_canvas_frame.winfo_children():
                w.destroy()

            fig = self.visualizer.create_3d_pattern(self.x_data, self.current_model)
            if fig is None:
                return

            self.canvas_3d = FigureCanvasTkAgg(fig, self.tab_3d_canvas_frame)
            self.canvas_3d.draw()
            self.canvas_3d.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            NavigationToolbar2Tk(self.canvas_3d, self.tab_3d_canvas_frame).update()
        except Exception as e:
            print(f"显示3D斑图时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    # ================================================================
    #  动画控制
    # ================================================================

    def prepare_animation_data(self):
        """准备动画历史数据"""
        try:
            params = self.get_parameters()
            init_x_range = (self.x_min_var.get(), self.x_max_var.get())
            init_y_range = (self.y_min_var.get(), self.y_max_var.get())

            n_frames = int(self.anim_frames_var.get())
            n_frames = min(n_frames, 1000)
            if n_frames >= 1000:
                self.anim_frames_var.set(1000)
                print("⚠ 动画帧数限制为1000帧")

            print(f"准备动画数据... 帧数: {n_frames}")
            self.x_history, self.y_history = self.simulator.simulate_with_history(
                self.current_model, params, n_frames, init_x_range, init_y_range)
            return True
        except Exception as e:
            messagebox.showerror("错误", f"准备动画数据失败: {str(e)}")
            print(f"✗ 准备动画数据失败: {str(e)}")
            return False

    def start_animation(self):
        """开始动画播放"""
        if not self.prepare_animation_data():
            return

        for w in self.tab_anim_canvas_frame.winfo_children():
            w.destroy()

        fig = self.visualizer.create_animation_figure()

        self.canvas_anim = FigureCanvasTkAgg(fig, self.tab_anim_canvas_frame)
        self.canvas_anim.draw()
        self.canvas_anim.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        NavigationToolbar2Tk(self.canvas_anim, self.tab_anim_canvas_frame).update()

        self.visualizer.animation = animation.FuncAnimation(
            fig, self.visualizer.update_animation,
            frames=len(self.x_history),
            fargs=(self.x_history, self.y_history),
            interval=50, blit=False, repeat=True,
        )

        self.visualizer.is_animating = True
        self.update_animation_controls()
        print(f"▶ 动画开始播放，总帧数: {len(self.x_history)}")

    def pause_animation(self):
        """暂停/继续动画"""
        if not self.visualizer.animation:
            return
        if self.visualizer.is_animating:
            self.visualizer.animation.event_source.stop()
            self.visualizer.is_animating = False
            self.update_animation_controls()
            print("⏸ 动画已暂停")
        else:
            self.visualizer.animation.event_source.start()
            self.visualizer.is_animating = True
            self.update_animation_controls()
            print("▶ 动画继续播放")
