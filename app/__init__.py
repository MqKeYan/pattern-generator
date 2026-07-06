"""
斑图生成器 (Pattern Generator)
"""

from .config import MODEL_CONFIGS, GRID_SIZE, MODEL_INIT_RANGES, PARAM_MEANINGS
from .models import MODEL_FUNCS, laplacian
from .simulator import PatternSimulator
from .visualizer import PatternVisualizer
from .theme import DarkScienceTheme
from .app_window import PatternVisualizationApp
from .version import current_version, bump_patch, bump_minor, bump_major
from .environment import setup_environment, setup_chinese_fonts

__version__ = "1.2.0"