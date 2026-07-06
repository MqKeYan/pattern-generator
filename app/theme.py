"""
UI 主题模块
==========
深色科学主题样式系统，基于 ttk 的完整 UI 设计令牌。

设计理念: Dark Mode (OLED) + Analytics Dashboard
色彩策略: 深蓝灰底 + 亮蓝强调 + 琥珀色 CTA

用法:
    colors = DarkScienceTheme.setup_theme(root)
"""

import tkinter as tk
from tkinter import ttk


class DarkScienceTheme:
    """深色科学主题 — 专业数据可视化 UI 样式

    为 ttk 组件提供完整的深色样式定义，包括按钮、输入框、
    下拉框、标签、标签页、滚动条等所有常用控件。

    用法:
        theme_colors = DarkScienceTheme.setup_theme(root)
    """

    @staticmethod
    def setup_theme(root):
        """应用深色主题并返回颜色令牌字典"""
        colors = DarkScienceTheme._define_colors()
        root.configure(bg=colors['bg_root'])
        style = ttk.Style()
        style.theme_use('clam')

        DarkScienceTheme._setup_global_style(style, colors)
        DarkScienceTheme._setup_button_styles(style, colors)
        DarkScienceTheme._setup_entry_styles(style, colors)
        DarkScienceTheme._setup_combobox_styles(style, colors, root)
        DarkScienceTheme._setup_label_styles(style, colors)
        DarkScienceTheme._setup_frame_styles(style, colors)
        DarkScienceTheme._setup_labelframe_styles(style, colors)
        DarkScienceTheme._setup_notebook_styles(style, colors)
        DarkScienceTheme._setup_scrollbar_styles(style, colors)
        DarkScienceTheme._setup_misc_styles(style, colors)

        return colors

    # ── 颜色令牌 ────────────────────────────────────

    @staticmethod
    def _define_colors():
        return {
            'bg_root': '#0B1120',        'bg': '#0F172A',
            'bg_elevated': '#1E293B',     'bg_input': '#1A2332',
            'bg_hover': '#334155',
            'border': '#1E3A5F',          'border_focus': '#3B82F6',
            'border_subtle': '#1A2744',
            'text': '#F1F5F9',            'text_secondary': '#94A3B8',
            'text_muted': '#64748B',      'text_heading': '#E2E8F0',
            'primary': '#3B82F6',         'primary_dark': '#2563EB',
            'primary_light': '#60A5FA',   'primary_glow': '#93C5FD',
            'success': '#22C55E',         'success_dark': '#16A34A',
            'warning': '#F59E0B',         'warning_dark': '#D97706',
            'danger': '#EF4444',
            'purple': '#8B5CF6',          'cyan': '#06B6D4',
        }

    # ── 全局默认 ────────────────────────────────────

    @staticmethod
    def _setup_global_style(style, c):
        style.configure('.',
            background=c['bg'], foreground=c['text'],
            troughcolor=c['bg_root'],
            selectbackground=c['primary'], selectforeground=c['text'],
            fieldbackground=c['bg_input'],
            font=('Microsoft YaHei UI', 10), borderwidth=0)

    # ── 按钮 ────────────────────────────────────────

    @staticmethod
    def _setup_button_styles(style, c):
        # 基础按钮
        style.configure('TButton', padding=(14, 8), relief='flat', borderwidth=1,
                        background=c['bg_elevated'], foreground=c['text'],
                        font=('Microsoft YaHei UI', 10), anchor='center')
        style.map('TButton',
            background=[('active', c['bg_hover']), ('pressed', c['primary_dark']),
                        ('disabled', c['bg_input'])],
            foreground=[('active', c['text']), ('pressed', '#FFFFFF'),
                        ('disabled', c['text_muted'])],
            borderColor=[('active', c['border_focus']), ('focus', c['border_focus'])],
            lightColor=[('active', c['primary'])])

        # Primary
        style.configure('Primary.TButton', background=c['primary'],
                        foreground='#FFFFFF', font=('Microsoft YaHei UI', 10, 'bold'))
        style.map('Primary.TButton',
            background=[('active', c['primary_dark']), ('pressed', '#1D4ED8'),
                        ('disabled', c['bg_hover'])],
            foreground=[('active', '#FFFFFF'), ('pressed', '#FFFFFF'),
                        ('disabled', c['text_muted'])])

        # Success
        style.configure('Success.TButton', background=c['success'],
                        foreground='#FFFFFF', font=('Microsoft YaHei UI', 10, 'bold'))
        style.map('Success.TButton',
            background=[('active', c['success_dark']), ('pressed', '#15803D'),
                        ('disabled', c['bg_hover'])],
            foreground=[('active', '#FFFFFF'), ('pressed', '#FFFFFF'),
                        ('disabled', c['text_muted'])])

        # Warning
        style.configure('Warning.TButton', background=c['warning'],
                        foreground='#0F172A', font=('Microsoft YaHei UI', 10, 'bold'))
        style.map('Warning.TButton',
            background=[('active', c['warning_dark']), ('pressed', '#B45309'),
                        ('disabled', c['bg_hover'])],
            foreground=[('active', '#0F172A'), ('pressed', '#0F172A'),
                        ('disabled', c['text_muted'])])

        # Danger
        style.configure('Danger.TButton', background=c['danger'],
                        foreground='#FFFFFF', font=('Microsoft YaHei UI', 10, 'bold'))
        style.map('Danger.TButton',
            background=[('active', '#DC2626'), ('pressed', '#B91C1C')])

        # Small
        style.configure('Small.TButton', padding=(8, 4),
                        font=('Microsoft YaHei UI', 9))

    # ── 输入框 ──────────────────────────────────────

    @staticmethod
    def _setup_entry_styles(style, c):
        style.configure('TEntry', fieldbackground=c['bg_input'],
                        foreground=c['text'], padding=(8, 6),
                        borderwidth=1, relief='solid',
                        insertcolor=c['text'], insertwidth=1)
        style.map('TEntry',
            fieldbackground=[('focus', c['bg_elevated']), ('disabled', c['bg_root'])],
            bordercolor=[('focus', c['border_focus'])])

    # ── 下拉框 ──────────────────────────────────────

    @staticmethod
    def _setup_combobox_styles(style, c, root):
        style.configure('TCombobox', fieldbackground=c['bg_input'],
                        foreground=c['text'], padding=(8, 6),
                        arrowcolor=c['primary_light'], borderwidth=1,
                        relief='solid', selectbackground=c['bg_input'],
                        selectforeground=c['text'])
        style.map('TCombobox',
            fieldbackground=[('focus', c['bg_elevated']), ('readonly', c['bg_elevated'])],
            bordercolor=[('focus', c['border_focus'])],
            selectbackground=[('focus', c['bg_elevated']), ('!focus', c['bg_elevated'])],
            selectforeground=[('focus', c['text']), ('!focus', c['text'])])
        root.option_add('*TCombobox*Listbox.background', c['bg_elevated'])
        root.option_add('*TCombobox*Listbox.foreground', c['text'])
        root.option_add('*TCombobox*Listbox.selectBackground', c['primary'])
        root.option_add('*TCombobox*Listbox.selectForeground', '#FFFFFF')
        root.option_add('*TCombobox*Listbox.font', ('Microsoft YaHei UI', 10))

    # ── 标签 ────────────────────────────────────────

    @staticmethod
    def _setup_label_styles(style, c):
        style.configure('TLabel', background=c['bg'], foreground=c['text'],
                        font=('Microsoft YaHei UI', 10))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 18, 'bold'),
                        foreground=c['text_heading'], background=c['bg_root'])
        style.configure('Subtitle.TLabel', font=('Microsoft YaHei UI', 11),
                        foreground=c['primary_light'], background=c['bg_root'])
        style.configure('Heading.TLabel', font=('Microsoft YaHei UI', 12, 'bold'),
                        foreground=c['text_heading'])
        style.configure('Info.TLabel', font=('Microsoft YaHei UI', 9),
                        foreground=c['text_secondary'])
        style.configure('Muted.TLabel', font=('Microsoft YaHei UI', 10),
                        foreground=c['text_muted'])
        style.configure('Accent.TLabel', font=('Microsoft YaHei UI', 10),
                        foreground=c['primary_light'])
        style.configure('Success.TLabel', font=('Microsoft YaHei UI', 10),
                        foreground=c['success'])

    # ── 框架 ────────────────────────────────────────

    @staticmethod
    def _setup_frame_styles(style, c):
        style.configure('TFrame', background=c['bg'])
        style.configure('Dark.TFrame', background=c['bg_root'])
        style.configure('Header.TFrame', background=c['bg_root'])

    # ── 标签框架 ────────────────────────────────────

    @staticmethod
    def _setup_labelframe_styles(style, c):
        style.configure('TLabelframe', background=c['bg'],
                        foreground=c['text_secondary'], relief='solid',
                        borderwidth=1, bordercolor=c['border'], padding=12)
        style.configure('TLabelframe.Label', background=c['bg'],
                        foreground=c['primary_light'],
                        font=('Microsoft YaHei UI', 10, 'bold'), padding=(8, 4))

    # ── 笔记本/标签页 ──────────────────────────────

    @staticmethod
    def _setup_notebook_styles(style, c):
        style.configure('TNotebook', background=c['bg_root'],
                        borderwidth=0, tabmargins=[2, 5, 2, 0])
        style.configure('TNotebook.Tab', padding=(18, 8),
                        background=c['bg_elevated'], foreground=c['text_secondary'],
                        borderwidth=1, bordercolor=c['border'], relief='flat',
                        font=('Microsoft YaHei UI', 11))
        style.map('TNotebook.Tab',
            background=[('selected', c['primary']), ('active', c['bg_hover'])],
            foreground=[('selected', '#FFFFFF'), ('active', c['text'])],
            bordercolor=[('selected', c['primary'])],
            expand=[('selected', [1, 1, 1, 0])])

    # ── 滚动条 ──────────────────────────────────────

    @staticmethod
    def _setup_scrollbar_styles(style, c):
        style.configure('TScrollbar', background=c['bg_elevated'],
                        troughcolor=c['bg_root'], borderwidth=0,
                        relief='flat', arrowsize=14, gripcount=0)
        style.map('TScrollbar',
            background=[('active', c['bg_hover']), ('pressed', c['primary_dark'])])

    # ── 杂项 ────────────────────────────────────────

    @staticmethod
    def _setup_misc_styles(style, c):
        style.configure('TProgressbar', background=c['primary'],
                        troughcolor=c['bg_root'], borderwidth=0, thickness=6)
        style.configure('TCheckbutton', background=c['bg'],
                        foreground=c['text'], font=('Microsoft YaHei UI', 10))
        style.map('TCheckbutton',
            background=[('active', c['bg'])], foreground=[('active', c['text'])])
        style.configure('TScale', background=c['bg'], troughcolor=c['bg_input'])
        style.configure('TSeparator', background=c['border_subtle'])
