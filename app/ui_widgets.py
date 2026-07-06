"""
UI 组件模块
==========
包含所有界面构建和控件管理方法，以 Mixin 形式组织。
通过多重继承注入到主应用类中，实现 UI 层与业务逻辑层的分离。

包含:
    - 状态栏（版本、运行时间、CPU/GPU/内存监控）
    - 控制面板（模型选择、参数设置、初始值、跟踪点、缓存、控制按钮）
    - 滚动区域事件处理
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
import time
import psutil
import torch
from datetime import datetime

from .config import MODEL_CONFIGS, GRID_SIZE, MODEL_INIT_RANGES, PARAM_MEANINGS


class UIMixin:
    """UI 组件 Mixin — 提供所有界面构建和控件管理方法

    要求宿主类 (PatternVisualizationApp) 提供以下属性:
        - self.root, self.theme_colors
        - self.model_var, self.iter_var, self.iter_entry
        - self.current_model, self.current_params
        - self.track_points, self.param_entries
        - self.x_min_var, self.x_max_var, self.y_min_var, self.y_max_var
        - self.anim_frames_var, self.auto_clean_enabled
        - self.is_simulating, self.is_switching_model
        - self.simulator, self.visualizer
        - self.start_time, self.start_time_str
    """

    # ================================================================
    #  顶层布局
    # ================================================================

    def create_widgets(self):
        """构建完整界面：顶部状态栏 + 左侧控制面板 + 右侧标签页"""
        c = self.theme_colors

        self.create_status_bar()

        # 主体容器
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 2))
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)

        # 左侧控制面板（带滚动条）
        self.control_panel = ttk.Frame(main_container, style='TFrame')
        self.control_panel.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                                padx=(0, 6))

        scrollbar = ttk.Scrollbar(self.control_panel)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(self.control_panel, bg=c['bg_elevated'],
                                highlightthickness=0, yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        scrollbar.config(command=self.canvas.yview)

        self.inner_frame = ttk.Frame(self.canvas, style='TFrame')
        self.inner_frame_id = self.canvas.create_window(
            (0, 0), window=self.inner_frame, anchor="nw", width=270)

        self.inner_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self._build_control_panel()

        # 右侧可视化标签页
        viz_container = ttk.Frame(main_container)
        viz_container.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        viz_container.columnconfigure(0, weight=1)
        viz_container.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(viz_container)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 二维斑图标签页
        self.tab_2d = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_2d, text=" 二维斑图 ")
        self.tab_2d_canvas_frame = ttk.Frame(self.tab_2d)
        self.tab_2d_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tab_2d_canvas_frame.columnconfigure(0, weight=1)
        self.tab_2d_canvas_frame.rowconfigure(0, weight=1)

        # 三维斑图标签页
        self.tab_3d = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_3d, text=" 三维斑图 ")
        self.tab_3d_canvas_frame = ttk.Frame(self.tab_3d)
        self.tab_3d_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tab_3d_canvas_frame.columnconfigure(0, weight=1)
        self.tab_3d_canvas_frame.rowconfigure(0, weight=1)

        # 动画演示标签页
        self.tab_anim = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_anim, text=" 动画演示 ")
        self.tab_anim_canvas_frame = ttk.Frame(self.tab_anim)
        self.tab_anim_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tab_anim_canvas_frame.columnconfigure(0, weight=1)
        self.tab_anim_canvas_frame.rowconfigure(0, weight=1)

        self.update_parameter_widgets()

    # ================================================================
    #  状态栏
    # ================================================================

    def create_status_bar(self):
        """创建顶部状态栏：版本号 | 目录 | 启动时间 | 运行时间 | 硬件 | CPU | GPU | 内存"""
        c = self.theme_colors
        bar = tk.Frame(self.root, bg=c['bg_root'], height=30)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        self.status_labels = []
        FONT = ('Microsoft YaHei UI', 10)
        SEP_FONT = ('Microsoft YaHei UI', 10)

        # 收集状态段
        try:
            from .version import current_version
            ver = current_version()
        except ImportError:
            ver = "1.2.0"

        self._version_text = tk.StringVar(value=f"版本号: {ver}")
        _full_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._dir_text = tk.StringVar(value=f"运行目录: {_full_path}")
        self._start_text = tk.StringVar(value=f"启动时间: {self.start_time_str}")
        self._uptime_text = tk.StringVar(value="运行时间: 00:00:00")
        self._hw_text = tk.StringVar(value=f"计算硬件: {self.simulator.hardware_info}")
        self._cpu_text = tk.StringVar(value="CPU占用率: 0%")
        self._gpu_text = tk.StringVar(value="GPU占用率: 0%" if torch.cuda.is_available() else "GPU占用率: 无")
        self._mem_text = tk.StringVar(value="运行内存: 0 MB")

        segments = [
            self._version_text, self._dir_text, self._start_text,
            self._uptime_text, self._hw_text, self._cpu_text,
            self._gpu_text, self._mem_text,
        ]

        for idx, var in enumerate(segments):
            if idx > 0:
                tk.Label(bar, text="|", font=SEP_FONT,
                        fg=c['border'], bg=c['bg_root']).pack(side=tk.LEFT, padx=4)
            lbl = tk.Label(bar, textvariable=var, font=FONT,
                          fg=c['text_muted'], bg=c['bg_root'])
            lbl.pack(side=tk.LEFT)
            self.status_labels.append((var, lbl))

        self._update_status_bar()

    def _update_status_bar(self):
        """定时刷新状态栏数据（每 3 秒）"""
        try:
            elapsed = int(time.time() - self.start_time)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            self._uptime_text.set(f"运行时间: {h:02d}:{m:02d}:{s:02d}")
        except Exception:
            pass
        try:
            self._cpu_text.set(f"CPU占用率: {psutil.cpu_percent(interval=None):.0f}%")
        except Exception:
            pass
        try:
            if torch.cuda.is_available():
                self._gpu_text.set(f"GPU占用率: {torch.cuda.utilization()}%")
        except Exception:
            pass
        try:
            mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
            self._mem_text.set(f"运行内存: {mem:.0f} MB")
        except Exception:
            pass
        self._status_update_id = self.root.after(3000, self._update_status_bar)

    # ================================================================
    #  控制面板构建
    # ================================================================

    def _build_control_panel(self):
        """构建左侧控制面板的全部卡片"""
        c = self.theme_colors

        # 注册参数编辑框样式
        ttk.Style().configure('Param.TEntry',
            fieldbackground=c['bg_elevated'], foreground=c['text'],
            background=c['border'], borderwidth=1, relief='solid')

        self._build_model_card(c)
        self._build_params_card(c)
        self._build_init_card(c)
        self._build_track_card(c)
        self._build_cache_card(c)
        self._build_ctrl_card(c)

    def _build_model_card(self, c):
        """模型选择卡片"""
        card = ttk.LabelFrame(self.inner_frame, text=" 模型设置 ", padding=8)
        card.pack(fill=tk.X, pady=(0, 8))

        mf = ttk.Frame(card)
        mf.pack(fill=tk.X)
        ttk.Label(mf, text="模型", font=('Microsoft YaHei UI', 9),
                  foreground=c['text_secondary']).pack(side=tk.LEFT, padx=(0, 6))

        self.model_var = tk.StringVar(value=self.current_model)
        combo = ttk.Combobox(mf, textvariable=self.model_var,
                             values=list(MODEL_CONFIGS.keys()), state="readonly",
                             font=('Microsoft YaHei UI', 9), width=8, height=10)
        combo.pack(side=tk.LEFT)

        # 禁用滚轮
        for ev in ['<MouseWheel>', '<Button-4>', '<Button-5>']:
            combo.bind(ev, lambda e: "break")
        combo.bind('<<ComboboxSelected>>',
                   lambda e: self.root.after(100, lambda: self.on_model_changed(e)))

        ttk.Separator(card).pack(fill=tk.X, pady=6)

        grid = ttk.Frame(card)
        grid.pack(fill=tk.X)

        ttk.Label(grid, text="迭代", font=('Microsoft YaHei UI', 9),
                  foreground=c['text_secondary']).grid(row=0, column=0, sticky='w', padx=(0, 6))
        entry = ttk.Entry(grid, textvariable=self.iter_var, width=7, justify=tk.CENTER,
                          font=('Microsoft YaHei UI', 9), style='Param.TEntry')
        entry.grid(row=0, column=1, sticky='w')
        entry.bind('<Return>', self.on_iter_entry_changed)
        if self.iter_entry is None:
            self.iter_entry = entry

        ttk.Label(grid, text="帧数", font=('Microsoft YaHei UI', 9),
                  foreground=c['text_secondary']).grid(
            row=1, column=0, sticky='w', padx=(0, 6), pady=(6, 0))
        ttk.Entry(grid, textvariable=self.anim_frames_var, width=7, justify=tk.CENTER,
                  font=('Microsoft YaHei UI', 9),
                  style='Param.TEntry').grid(row=1, column=1, sticky='w', pady=(6, 0))

    def _build_params_card(self, c):
        """参数设置卡片"""
        card = ttk.LabelFrame(self.inner_frame, text=" 参数设置 ", padding=8)
        card.pack(fill=tk.X, pady=(0, 8))

        grid = ttk.Frame(card)
        grid.pack(fill=tk.X)

        self.param_entries = []
        self._create_parameter_rows(grid)

        self.reset_params_btn = ttk.Button(card, text="重置为默认值",
                                           command=self.reset_parameters,
                                           style='Small.TButton')
        self.reset_params_btn.pack(fill=tk.X, pady=(8, 0))

    def _create_parameter_rows(self, parent):
        """创建 8 行参数输入控件"""
        parent.columnconfigure(0, minsize=140)
        parent.columnconfigure(1, minsize=80)
        parent.columnconfigure(2, minsize=50)

        for i in range(8):
            label_var = tk.StringVar(value=f"参数 {i + 1}:")
            lbl = ttk.Label(parent, textvariable=label_var, anchor=tk.W,
                            font=('Microsoft YaHei UI', 9))
            lbl.grid(row=i, column=0, sticky='w', padx=(0, 4), pady=2)

            entry_var = tk.DoubleVar(value=0.0)
            ent = ttk.Entry(parent, textvariable=entry_var, width=8,
                            font=('Microsoft YaHei UI', 9), style='Param.TEntry')
            ent.grid(row=i, column=1, sticky='w', pady=2)

            btn = ttk.Button(parent, text="重置", width=4, style='Small.TButton')
            btn.grid(row=i, column=2, padx=(4, 0), pady=2)

            self.param_entries.append({
                'label': label_var, 'entry': entry_var,
                'reset_btn': btn, 'widgets': [lbl, ent, btn],
            })

    def _build_init_card(self, c):
        """初始值范围卡片"""
        card = ttk.LabelFrame(self.inner_frame, text=" 初始值范围 ", padding=10)
        card.pack(fill=tk.X, pady=(0, 12))

        self.init_desc_text = tk.StringVar(
            value=MODEL_INIT_RANGES[self.current_model]["description"])
        ttk.Label(card, textvariable=self.init_desc_text, font=('Microsoft YaHei UI', 9),
                  foreground=c['primary_light'], justify=tk.LEFT).pack(fill=tk.X, pady=(0, 8))

        frame = ttk.Frame(card)
        frame.pack(fill=tk.X)

        self.x_min_var = tk.DoubleVar(value=MODEL_INIT_RANGES[self.current_model]["x_range"][0])
        self.x_max_var = tk.DoubleVar(value=MODEL_INIT_RANGES[self.current_model]["x_range"][1])
        self.y_min_var = tk.DoubleVar(value=MODEL_INIT_RANGES[self.current_model]["y_range"][0])
        self.y_max_var = tk.DoubleVar(value=MODEL_INIT_RANGES[self.current_model]["y_range"][1])

        for row, (text, var, vname) in enumerate([
            ("X 最小值", self.x_min_var, 'x_min'), ("X 最大值", self.x_max_var, 'x_max'),
            ("Y 最小值", self.y_min_var, 'y_min'), ("Y 最大值", self.y_max_var, 'y_max'),
        ]):
            ttk.Label(frame, text=text, font=('Microsoft YaHei UI', 9)).grid(
                row=row, column=0, sticky=tk.W, pady=3)
            ttk.Entry(frame, textvariable=var, width=12).grid(
                row=row, column=1, pady=3, padx=6)
            ttk.Button(frame, text="重置", width=4,
                       command=lambda v=vname: self.reset_initial(v),
                       style='Small.TButton').grid(row=row, column=2, pady=3)

        ttk.Button(card, text="应用最佳初始值", command=self.apply_best_initial_values,
                   style='Small.TButton').pack(fill=tk.X, pady=(10, 0))

    def _build_track_card(self, c):
        """跟踪点卡片"""
        card = ttk.LabelFrame(self.inner_frame, text=" 跟踪点 ", padding=8)
        card.pack(fill=tk.X, pady=(0, 8))

        tf = ttk.Frame(card)
        tf.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(tf, text="X", font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT)
        self.track_x_var = tk.IntVar(value=50)
        ttk.Entry(tf, textvariable=self.track_x_var, width=6,
                  font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT, padx=4)
        ttk.Label(tf, text="Y", font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT, padx=(8, 0))
        self.track_y_var = tk.IntVar(value=50)
        ttk.Entry(tf, textvariable=self.track_y_var, width=6,
                  font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT, padx=4)

        ttk.Button(tf, text="+", command=self.add_track_point,
                   style='Small.TButton', width=3).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(tf, text="清空", command=self.clear_track_points,
                   style='Small.TButton').pack(side=tk.LEFT)

        self.track_list_label = ttk.Label(card, text="已添加点",
                                          font=('Microsoft YaHei UI', 10),
                                          foreground=c['text_secondary'])
        self.track_list_label.pack(fill=tk.X)

    def _build_cache_card(self, c):
        """缓存管理卡片"""
        card = ttk.LabelFrame(self.inner_frame, text=" 缓存 ", padding=8)
        card.pack(fill=tk.X, pady=(0, 8))

        row1 = ttk.Frame(card)
        row1.pack(fill=tk.X)

        tk.Checkbutton(row1, text="自动清理", variable=self.auto_clean_enabled,
                       bg=c['bg'], fg=c['text'], selectcolor=c['primary'],
                       activebackground=c['bg'], activeforeground=c['text'],
                       font=('Microsoft YaHei UI', 10)).pack(side=tk.LEFT)

        ttk.Button(row1, text="清理缓存", command=self.clean_cache,
                   style='Small.TButton').pack(side=tk.RIGHT)

        row2 = ttk.Frame(card)
        row2.pack(fill=tk.X, pady=(6, 0))

        self.clean_count_label = ttk.Label(row2, text="清理: 0 次",
                                           font=('Microsoft YaHei UI', 10),
                                           foreground=c['text_muted'])
        self.clean_count_label.pack(side=tk.LEFT, padx=(0, 8))
        self.last_clean_label = ttk.Label(row2, text="上次: 从未",
                                          font=('Microsoft YaHei UI', 10),
                                          foreground=c['text_muted'])
        self.last_clean_label.pack(side=tk.LEFT, padx=(0, 8))
        self.cleanup_status_label = ttk.Label(row2, text="状态正常",
                                              font=('Microsoft YaHei UI', 10),
                                              foreground=c['success'])
        self.cleanup_status_label.pack(side=tk.LEFT)

    def _build_ctrl_card(self, c):
        """控制按钮卡片"""
        card = ttk.LabelFrame(self.inner_frame, text=" 控制 ", padding=8)
        card.pack(fill=tk.X, pady=(0, 8))

        row = ttk.Frame(card)
        row.pack(fill=tk.X)

        ttk.Button(row, text="运行", command=self.run_simulation,
                   style='Small.TButton', width=6).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row, text="重置", command=self.reset_all,
                   style='Small.TButton', width=6).pack(side=tk.LEFT, padx=(0, 4))
        self.tab_play_btn = ttk.Button(row, text="播放", command=self.start_animation,
                                       style='Small.TButton', width=6)
        self.tab_play_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.tab_pause_btn = ttk.Button(row, text="暂停", command=self.pause_animation,
                                        style='Small.TButton', width=6)
        self.tab_pause_btn.pack(side=tk.LEFT)

    # ================================================================
    #  滚动区域事件
    # ================================================================

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        self.canvas.itemconfig(self.inner_frame_id, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    # ================================================================
    #  参数控件管理
    # ================================================================

    def update_parameter_widgets(self):
        """根据当前模型更新参数控件的标签和默认值"""
        config = MODEL_CONFIGS[self.current_model]
        params = config["params"]
        defaults = config["defaults"]
        meanings = PARAM_MEANINGS.get(self.current_model, {})

        for i, entry_data in enumerate(self.param_entries):
            for w in entry_data['widgets']:
                w.grid() if i < len(params) else w.grid_remove()

            if i < len(params):
                pname = params[i]
                hint = meanings.get(pname, "")
                label_text = f"{pname}: {hint}" if hint else f"{pname}:"
                entry_data['label'].set(label_text)
                entry_data['entry'].set(defaults[i])
                entry_data['reset_btn'].config(
                    command=lambda idx=i, val=defaults[i]: self.reset_parameter(idx, val))

        if hasattr(self, 'reset_params_btn'):
            self.reset_params_btn.pack_forget()
            self.reset_params_btn.pack(fill=tk.X, pady=(10, 0))

    def reset_parameter(self, index, default_value):
        """重置单个参数为默认值"""
        self.param_entries[index]['entry'].set(default_value)

    def reset_parameters(self):
        """重置所有参数为默认值"""
        defaults = MODEL_CONFIGS[self.current_model]["defaults"]
        for i, entry_data in enumerate(self.param_entries):
            if i < len(defaults):
                entry_data['entry'].set(defaults[i])
        print("✓ 所有参数已重置为默认值")

    def get_parameters(self):
        """获取用户输入的参数列表"""
        config = MODEL_CONFIGS[self.current_model]
        return [self.param_entries[i]['entry'].get()
                for i in range(len(config["params"]))]

    # ================================================================
    #  模型切换
    # ================================================================

    def on_model_changed(self, event=None):
        """模型下拉框切换事件"""
        if self.is_simulating:
            self.model_var.set(self.current_model)
            messagebox.showinfo("提示", "模拟正在进行中，请等待完成后再切换模型")
            return
        if self.is_switching_model:
            return

        try:
            self.is_switching_model = True
            new_model = self.model_var.get()

            if new_model not in MODEL_CONFIGS:
                print(f"错误: 模型 '{new_model}' 不存在")
                self.model_var.set(self.current_model)
                return

            print(f"切换模型: 从 '{self.current_model}' 到 '{new_model}'")
            self.current_model = new_model
            self.current_params = MODEL_CONFIGS[self.current_model]["defaults"].copy()

            self.update_parameter_widgets()
            self.update_initial_values_for_model()
        except Exception as e:
            print(f"切换模型时出错: {str(e)}")
            self.model_var.set(self.current_model)
        finally:
            self.is_switching_model = False

    # ================================================================
    #  初始值管理
    # ================================================================

    def apply_best_initial_values(self):
        """应用当前模型的最佳初始值范围"""
        init = MODEL_INIT_RANGES[self.current_model]
        self.x_min_var.set(init["x_range"][0])
        self.x_max_var.set(init["x_range"][1])
        self.y_min_var.set(init["y_range"][0])
        self.y_max_var.set(init["y_range"][1])
        print(f"✓ 已应用 {self.current_model} 的最佳初始值范围")

    def reset_initial(self, var_name):
        """重置单个初始值为最佳值"""
        init = MODEL_INIT_RANGES[self.current_model]
        mapping = {
            'x_min': (self.x_min_var, init["x_range"][0]),
            'x_max': (self.x_max_var, init["x_range"][1]),
            'y_min': (self.y_min_var, init["y_range"][0]),
            'y_max': (self.y_max_var, init["y_range"][1]),
        }
        if var_name in mapping:
            var, val = mapping[var_name]
            var.set(val)

    def update_initial_values_for_model(self):
        """根据当前模型更新初始值范围和推荐迭代次数"""
        init = MODEL_INIT_RANGES[self.current_model]
        self.x_min_var.set(init["x_range"][0])
        self.x_max_var.set(init["x_range"][1])
        self.y_min_var.set(init["y_range"][0])
        self.y_max_var.set(init["y_range"][1])
        self.init_desc_text.set(init["description"])

        rec = MODEL_CONFIGS[self.current_model]["recommended_iterations"]
        self.iter_var.set(rec)
        self.iter_entry.delete(0, tk.END)
        self.iter_entry.insert(0, str(rec))
        print(f"✓ 已更新 {self.current_model} 的初始值范围和推荐迭代次数")

    # ================================================================
    #  跟踪点管理
    # ================================================================

    def add_track_point(self):
        """添加跟踪点"""
        try:
            x, y = self.track_x_var.get(), self.track_y_var.get()
            if x < 0 or x >= GRID_SIZE or y < 0 or y >= GRID_SIZE:
                messagebox.showwarning("警告", f"坐标必须在0到{GRID_SIZE - 1}之间")
                return
            if any(p['x'] == x and p['y'] == y for p in self.track_points):
                messagebox.showinfo("提示", f"点({x},{y})已经存在")
                return
            self.track_points.append({'x': x, 'y': y})
            self._update_track_display()
            print(f"✓ 已添加跟踪点: ({x}, {y})")
        except ValueError:
            messagebox.showwarning("警告", "请输入有效的整数坐标")

    def clear_track_points(self):
        """清空所有跟踪点"""
        self.track_points.clear()
        self._update_track_display()
        print("✓ 已清空所有跟踪点")

    def _update_track_display(self):
        """更新跟踪点列表文本"""
        if self.track_points:
            pts = " ".join(f"({p['x']},{p['y']})" for p in self.track_points)
            self.track_list_label.config(text=f"已添加点: {pts}")
        else:
            self.track_list_label.config(text="已添加点")

    # ================================================================
    #  迭代次数管理
    # ================================================================

    def update_iter_label(self, value=None):
        """更新迭代次数输入框"""
        try:
            if value is not None:
                v = int(float(value))
            else:
                v = int(self.iter_var.get()) if self.iter_var.get() else None
            if v is not None:
                self.iter_var.set(v)
                self.iter_entry.delete(0, tk.END)
                self.iter_entry.insert(0, str(v))
        except (ValueError, tk.TclError):
            rec = MODEL_CONFIGS[self.current_model]["recommended_iterations"]
            self.iter_var.set(rec)
            self.iter_entry.delete(0, tk.END)
            self.iter_entry.insert(0, str(rec))

    def on_iter_entry_changed(self, event=None):
        """迭代次数输入验证"""
        try:
            value = int(self.iter_entry.get())
            min_iter = MODEL_CONFIGS[self.current_model].get("min_iterations", 100)
            max_iter = MODEL_CONFIGS[self.current_model].get("max_iterations", 20000)

            if min_iter <= value <= max_iter:
                self.iter_var.set(value)
            else:
                messagebox.showwarning("警告", f"迭代次数必须在{min_iter}到{max_iter}之间")
                rec = MODEL_CONFIGS[self.current_model]["recommended_iterations"]
                self.iter_var.set(rec)
                self.iter_entry.delete(0, tk.END)
                self.iter_entry.insert(0, str(rec))
        except ValueError:
            messagebox.showwarning("警告", "请输入有效的整数")
            rec = MODEL_CONFIGS[self.current_model]["recommended_iterations"]
            self.iter_var.set(rec)
            self.iter_entry.delete(0, tk.END)
            self.iter_entry.insert(0, str(rec))

    # ================================================================
    #  重置方法
    # ================================================================

    def reset_all_initial(self):
        self.update_initial_values_for_model()

    def reset_iterations(self):
        rec = MODEL_CONFIGS[self.current_model]["recommended_iterations"]
        self.iter_var.set(rec)
        self.iter_entry.delete(0, tk.END)
        self.iter_entry.insert(0, str(rec))
        print(f"✓ 迭代次数已重置为推荐值: {rec}")

    def reset_animation_frames(self, default_value=300):
        self.anim_frames_var.set(default_value)

    def reset_all(self):
        """重置所有设置为默认值"""
        self.reset_parameters()
        self.reset_all_initial()
        self.reset_iterations()
        self.reset_animation_frames()
        self.update_animation_controls()
        print("✓ 所有设置已重置为默认值")

    # ================================================================
    #  动画控件状态
    # ================================================================

    def update_animation_controls(self):
        """根据动画状态更新播放/暂停按钮文字"""
        is_anim = (hasattr(self.visualizer, 'is_animating')
                   and self.visualizer.is_animating)
        has_anim = (hasattr(self.visualizer, 'animation')
                    and self.visualizer.animation is not None)

        if hasattr(self, 'tab_play_btn'):
            self.tab_play_btn.config(
                text="继续" if (has_anim and not is_anim) else "播放",
                style='Small.TButton')

        if hasattr(self, 'tab_pause_btn'):
            self.tab_pause_btn.config(text="暂停", style='Small.TButton')
